"""Base de datos con las respuestas del Forms, sincronizada desde los Excel.

La base es PostgreSQL en la nube si hay dirección configurada (bd_nube.txt o DATABASE_URL), si no SQLite local.
El PC puente lee los Excel y escribe en la nube; la página en Render solo lee y guarda marcas y consejos.
"""
import json
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.utils.datetime import from_excel

from . import bd, config, reglas

# excel_historico: copia descargada; excel_forms: libro vinculado al Forms;
# excel_flujo: tabla que llena Power Automate con cada respuesta nueva.
FUENTES = ("excel_historico", "excel_forms", "excel_flujo")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS respuestas(
  id BIGINT PRIMARY KEY,           -- columna Id del Forms
  fecha TEXT NOT NULL,             -- hora de finalización, AAAA-MM-DD HH:MM:SS
  dia TEXT NOT NULL,
  nombre TEXT NOT NULL,
  persona TEXT NOT NULL,           -- nombre normalizado (sin tildes, minúsculas)
  lugar TEXT,
  responsable TEXT,
  observacion TEXT,
  novedades TEXT NOT NULL,         -- JSON calculado con reglas.py
  crudo TEXT NOT NULL              -- fila completa del Excel
);
CREATE INDEX IF NOT EXISTS ix_dia ON respuestas(dia);
CREATE INDEX IF NOT EXISTS ix_persona ON respuestas(persona, dia);
CREATE TABLE IF NOT EXISTS fuentes(ruta TEXT PRIMARY KEY, firma TEXT, ultima_respuesta TEXT, revisado TEXT);
CREATE TABLE IF NOT EXISTS ia(dia TEXT PRIMARY KEY, entrada TEXT, respuesta TEXT, modelo TEXT, creado TEXT);
CREATE TABLE IF NOT EXISTS envios(dia TEXT PRIMARY KEY, destinatarios TEXT, enviado TEXT);
-- Marcas de Calidad sobre los consejos de la IA (👍/👎 y corrección). Se usan como ejemplos en la consulta diaria.
CREATE TABLE IF NOT EXISTS valoraciones(
  id {AUTO},
  dia TEXT NOT NULL,
  respuesta_id BIGINT NOT NULL,
  situacion TEXT NOT NULL,         -- novedades y observación del caso, sin nombre
  consejo TEXT NOT NULL,           -- lo que dijo la IA
  voto INTEGER,                    -- 1 útil, -1 no sirve
  correccion TEXT,                 -- cómo lo diría Calidad (sin nombres)
  creado TEXT NOT NULL,
  UNIQUE(respuesta_id, consejo)
);
"""

# "Insertar o actualizar" que sirve igual en SQLite y PostgreSQL.
GUARDAR_RESPUESTA = """
INSERT INTO respuestas(id, fecha, dia, nombre, persona, lugar, responsable, observacion, novedades, crudo)
VALUES (?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(id) DO UPDATE SET fecha=excluded.fecha, dia=excluded.dia, nombre=excluded.nombre,
  persona=excluded.persona, lugar=excluded.lugar, responsable=excluded.responsable,
  observacion=excluded.observacion, novedades=excluded.novedades, crudo=excluded.crudo
"""
GUARDAR_FUENTE = """
INSERT INTO fuentes(ruta, firma, ultima_respuesta, revisado) VALUES (?,?,?,?)
ON CONFLICT(ruta) DO UPDATE SET firma=excluded.firma, ultima_respuesta=excluded.ultima_respuesta,
  revisado=excluded.revisado
"""


def conectar(cfg=None):
    url = config.url_bd(cfg)
    con = bd.abrir(url, config.carpeta_datos(cfg) / "calidad.db")
    auto = "BIGSERIAL PRIMARY KEY" if con.postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    con.script(ESQUEMA.replace("{AUTO}", auto))
    return con


def _texto(valor):
    return "" if valor is None else str(valor).strip()


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, (int, float)):
        # Excel convirtió el texto que escribió Power Automate en número de fecha.
        return from_excel(valor)
    texto = _texto(valor)
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return datetime.strptime(texto, "%d/%m/%Y %H:%M:%S")


def _copia_local(ruta, intentos=6, espera=10):
    """Copia el Excel a una carpeta temporal. OneDrive o Excel pueden bloquearlo unos segundos mientras
    sincronizan; se reintenta antes de rendirse."""
    destino = Path(tempfile.mkdtemp()) / "fuente.xlsx"
    for intento in range(intentos):
        try:
            shutil.copy2(ruta, destino)
            return destino
        except PermissionError:
            if intento == intentos - 1:
                raise
            time.sleep(espera)


def leer_excel(ruta):
    """Devuelve las filas del Forms como dicts encabezado -> valor."""
    copia = _copia_local(ruta)
    wb = openpyxl.load_workbook(copia, read_only=True, data_only=True)
    try:
        filas = wb.worksheets[0].iter_rows(values_only=True)
        encabezados = [_texto(h) for h in next(filas)]
        for valores in filas:
            fila = dict(zip(encabezados, valores))
            if fila.get("Id") is not None:
                yield fila
    finally:
        wb.close()
        shutil.rmtree(copia.parent, ignore_errors=True)


def valores(fila):
    """Tupla lista para GUARDAR_RESPUESTA a partir de una fila del Excel."""
    fecha = _fecha(fila.get("Hora de finalización") or fila.get("Hora de inicio"))
    nombre = " ".join(_texto(fila.get("NOMBRE1")).split()) or "(sin nombre)"
    crudo = {k: (v.isoformat(sep=" ") if isinstance(v, datetime) else v) for k, v in fila.items()}
    return (int(fila["Id"]), fecha.strftime("%Y-%m-%d %H:%M:%S"), fecha.strftime("%Y-%m-%d"), nombre,
            reglas.clave_persona(nombre), _texto(fila.get("LUGAR")) or "Sin lugar",
            _texto(fila.get("RESPONSABLE DEL CHEQUEO")), _texto(fila.get("OBSERVACIONES")),
            json.dumps(reglas.novedades(fila), ensure_ascii=False), json.dumps(crudo, ensure_ascii=False, default=str))


def guardar(con, fila):
    con.execute(GUARDAR_RESPUESTA, valores(fila))


def sincronizar(con, cfg=None, forzar=False):
    """Lee cada Excel configurado solo si cambió y guarda solo las respuestas nuevas o modificadas
    (importante cuando la base está en la nube). Devuelve el estado de cada fuente."""
    cfg = cfg or config.cargar()
    estado = []
    # En este orden: si una respuesta está en varios archivos, gana el último (el del flujo).
    for nombre in FUENTES:
        if not cfg.get(nombre):
            continue
        ruta = config.ruta_excel(cfg[nombre])
        info = {"fuente": nombre, "ruta": str(ruta), "ok": False}
        estado.append(info)
        if not ruta.exists():
            info["error"] = "No se encuentra el archivo."
            continue
        st = ruta.stat()
        firma = f"{st.st_size}-{int(st.st_mtime)}"
        previa = con.execute("SELECT firma, ultima_respuesta FROM fuentes WHERE ruta=?", (str(ruta),)).fetchone()
        info["modificado"] = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        if previa and previa["firma"] == firma and not forzar:
            info.update(ok=True, ultima_respuesta=previa["ultima_respuesta"], leidas=0, guardadas=0)
            continue
        try:
            nuevas = [valores(f) for f in leer_excel(ruta)]
            ultima = max((v[1][:16] for v in nuevas), default="")
            if nuevas:
                ids = [v[0] for v in nuevas]
                existentes = {r[0]: r[1] for r in con.execute(
                    "SELECT id, crudo FROM respuestas WHERE id BETWEEN ? AND ?", (min(ids), max(ids)))}
                nuevas_o_cambiadas = [v for v in nuevas if existentes.get(v[0]) != v[9]]
            else:
                nuevas_o_cambiadas = []
            with con:
                if nuevas_o_cambiadas:
                    con.executemany(GUARDAR_RESPUESTA, nuevas_o_cambiadas)
                con.execute(GUARDAR_FUENTE, (str(ruta), firma, ultima, datetime.now().isoformat(timespec="seconds")))
            info.update(ok=True, ultima_respuesta=ultima, leidas=len(nuevas), guardadas=len(nuevas_o_cambiadas))
        except (OSError, ValueError, KeyError, StopIteration) as e:
            # Excel abierto, sincronizando o con formato inesperado: se conserva lo ya guardado.
            info["error"] = f"No se pudo leer: {e}"
    return estado


def recalcular(con):
    """Vuelve a aplicar reglas.py a todo el histórico (útil si cambian las reglas)."""
    cambios = [(json.dumps(reglas.novedades(json.loads(r["crudo"])), ensure_ascii=False), r["id"])
               for r in con.execute("SELECT id, crudo FROM respuestas").fetchall()]
    with con:
        con.executemany("UPDATE respuestas SET novedades=? WHERE id=?", cambios)


def subir(origen_sqlite, destino):
    """Copia todo lo de una base SQLite local (versión anterior) a la base de destino, sin duplicar.
    Devuelve cuántas filas se copiaron por tabla."""
    origen = sqlite3.connect(origen_sqlite)
    origen.row_factory = sqlite3.Row
    columnas = {
        "respuestas": ("id", "fecha", "dia", "nombre", "persona", "lugar", "responsable", "observacion",
                       "novedades", "crudo"),
        "fuentes": ("ruta", "firma", "ultima_respuesta", "revisado"),
        "ia": ("dia", "entrada", "respuesta", "modelo", "creado"),
        "envios": ("dia", "destinatarios", "enviado"),
        "valoraciones": ("dia", "respuesta_id", "situacion", "consejo", "voto", "correccion", "creado"),
    }
    llaves = {"respuestas": "id", "fuentes": "ruta", "ia": "dia", "envios": "dia", "valoraciones": "respuesta_id, consejo"}
    copiadas = {}
    try:
        for tabla, cols in columnas.items():
            if not origen.execute("SELECT 1 FROM sqlite_master WHERE name=?", (tabla,)).fetchone():
                continue
            filas_origen = [tuple(r[c] for c in cols) for r in origen.execute(f"SELECT {', '.join(cols)} FROM {tabla}")]
            actualizar = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in llaves[tabla].split(", "))
            sql = (f"INSERT INTO {tabla}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
                   f"ON CONFLICT({llaves[tabla]}) DO UPDATE SET {actualizar}")
            with destino:
                for inicio in range(0, len(filas_origen), 1000):   # por lotes, para no saturar la conexión
                    destino.executemany(sql, filas_origen[inicio:inicio + 1000])
            copiadas[tabla] = len(filas_origen)
    finally:
        origen.close()
    return copiadas


def filas(con, sql, *args):
    resultado = []
    for r in con.execute(sql, args):
        d = dict(r)
        if "novedades" in d:
            d["novedades"] = json.loads(d["novedades"])
        resultado.append(d)
    return resultado


def ultima_sincronizacion(con):
    r = con.execute("SELECT max(revisado) FROM fuentes").fetchone()[0]
    return r or ""


def ultima_respuesta(con):
    return con.execute("SELECT max(fecha) FROM respuestas").fetchone()[0] or ""
