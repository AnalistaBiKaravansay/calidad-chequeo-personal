"""Base de datos con las respuestas del Forms, sincronizada desde los Excel.

La base es PostgreSQL en la nube si hay dirección configurada (bd_nube.txt o DATABASE_URL), si no SQLite local.
El PC puente lee los Excel y escribe en la nube; la página en Render solo lee y guarda marcas y consejos.

Para gastar poco espacio y pocas consultas:
- La fila completa del Excel (crudo) se guarda como lista de valores: [id_columnas, v1, v2...]. Los nombres de
  las columnas (largos, iguales en todas las filas) se guardan una sola vez en la tabla columnas.
- El puente recuerda en este equipo la firma (tamaño y fecha) de cada Excel: si no cambió, ni se conecta a la base.
- La página guarda en memoria las respuestas (sin crudo) y solo las vuelve a pedir cuando cambian los datos.
"""
import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
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
  crudo TEXT NOT NULL              -- fila completa del Excel: [id_columnas, valores...]
);
CREATE INDEX IF NOT EXISTS ix_dia ON respuestas(dia);
CREATE INDEX IF NOT EXISTS ix_persona ON respuestas(persona, dia);
-- Nombres de las columnas del Excel, una vez por cada versión del formulario.
CREATE TABLE IF NOT EXISTS columnas(id TEXT PRIMARY KEY, nombres TEXT NOT NULL);
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
GUARDAR_COLUMNAS = "INSERT INTO columnas(id, nombres) VALUES (?,?) ON CONFLICT(id) DO NOTHING"

_esquema_listo = set()   # bases a las que ya se les creó el esquema en este proceso
_escrituras = 0          # sube con cada escritura de este proceso (invalida la memoria de registros)


def conectar(cfg=None):
    url = config.url_bd(cfg)
    con = bd.abrir(url, config.carpeta_datos(cfg) / "calidad.db")
    if con.ident not in _esquema_listo:   # una sola vez por proceso: ahorra una consulta en cada página
        auto = "BIGSERIAL PRIMARY KEY" if con.postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        con.script(ESQUEMA.replace("{AUTO}", auto))
        _esquema_listo.add(con.ident)
    return con


def _compacto(valor):
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"), default=str)


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


# --- Fila completa del Excel en formato compacto -------------------------------------------------------------

def columnas_de(fila):
    """(id, nombres) de las columnas de una fila. El id sale de los nombres: igual en todas las bases."""
    nombres = _compacto(list(fila.keys()))
    return hashlib.sha1(nombres.encode()).hexdigest()[:12], nombres


_nombres_columnas = {}   # id -> lista de nombres (no cambian nunca: se guardan para todo el proceso)


def crudo(con, texto):
    """Fila completa del Excel como dict encabezado -> valor (acepta también el formato antiguo, un dict)."""
    valor = json.loads(texto)
    if isinstance(valor, dict):
        return valor
    ident, *valores = valor
    if ident not in _nombres_columnas:
        r = con.execute("SELECT nombres FROM columnas WHERE id=?", (ident,)).fetchone()
        _nombres_columnas[ident] = json.loads(r[0]) if r else []
    return dict(zip(_nombres_columnas[ident], valores))


def valores(fila):
    """Tupla lista para GUARDAR_RESPUESTA a partir de una fila del Excel."""
    fecha = _fecha(fila.get("Hora de finalización") or fila.get("Hora de inicio"))
    nombre = " ".join(_texto(fila.get("NOMBRE1")).split()) or "(sin nombre)"
    lista = [v.isoformat(sep=" ") if isinstance(v, datetime) else v for v in fila.values()]
    return (int(fila["Id"]), fecha.strftime("%Y-%m-%d %H:%M:%S"), fecha.strftime("%Y-%m-%d"), nombre,
            reglas.clave_persona(nombre), _texto(fila.get("LUGAR")) or "Sin lugar",
            _texto(fila.get("RESPONSABLE DEL CHEQUEO")), _texto(fila.get("OBSERVACIONES")),
            _compacto(reglas.novedades(fila)), _compacto([columnas_de(fila)[0], *lista]))


def guardar(con, fila):
    global _escrituras
    con.execute(GUARDAR_COLUMNAS, columnas_de(fila))
    con.execute(GUARDAR_RESPUESTA, valores(fila))
    _escrituras += 1


# --- Puente: Excel -> base -----------------------------------------------------------------------------------

def _archivo_firmas(cfg):
    return config.carpeta_datos(cfg) / "firmas.json"


def _firmas_locales(cfg):
    try:
        return json.loads(_archivo_firmas(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _llave_local(cfg, ruta):
    # La firma local se guarda por base: si se cambia de base, se vuelve a leer todo.
    base = hashlib.sha1(config.url_bd(cfg).encode()).hexdigest()[:8]
    return f"{base}|{ruta}"


def _firma(ruta):
    st = ruta.stat()
    return f"{st.st_size}-{int(st.st_mtime)}"


def hay_cambios(cfg=None):
    """True si algún Excel cambió desde la última subida. No toca la base (así Neon puede seguir dormida)."""
    cfg = cfg or config.cargar()
    locales = _firmas_locales(cfg)
    for nombre in FUENTES:
        if cfg.get(nombre):
            ruta = config.ruta_excel(cfg[nombre])
            if ruta.exists() and locales.get(_llave_local(cfg, ruta)) != _firma(ruta):
                return True
    return False


def sincronizar(con, cfg=None, forzar=False):
    """Lee cada Excel configurado solo si cambió y guarda solo las respuestas nuevas o modificadas
    (importante cuando la base está en la nube). Devuelve el estado de cada fuente."""
    global _escrituras
    cfg = cfg or config.cargar()
    estado = []
    locales = _firmas_locales(cfg)
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
        firma = _firma(ruta)
        info["modificado"] = datetime.fromtimestamp(ruta.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        llave = _llave_local(cfg, ruta)
        if locales.get(llave) == firma and not forzar:
            info.update(ok=True, leidas=0, guardadas=0, sin_cambios=True)
            continue
        previa = con.execute("SELECT firma FROM fuentes WHERE ruta=?", (str(ruta),)).fetchone()
        if previa and previa["firma"] == firma and not forzar:
            locales[llave] = firma
            info.update(ok=True, leidas=0, guardadas=0, sin_cambios=True)
            continue
        try:
            filas_excel = list(leer_excel(ruta))
            nuevas = [valores(f) for f in filas_excel]
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
                    con.executemany(GUARDAR_COLUMNAS, list({columnas_de(f) for f in filas_excel}))
                    con.executemany(GUARDAR_RESPUESTA, nuevas_o_cambiadas)
                con.execute(GUARDAR_FUENTE, (str(ruta), firma, ultima, datetime.now().isoformat(timespec="seconds")))
            _escrituras += 1
            locales[llave] = firma
            info.update(ok=True, ultima_respuesta=ultima, leidas=len(nuevas), guardadas=len(nuevas_o_cambiadas))
        except (OSError, ValueError, KeyError, StopIteration) as e:
            # Excel abierto, sincronizando o con formato inesperado: se conserva lo ya guardado.
            info["error"] = f"No se pudo leer: {e}"
    try:
        _archivo_firmas(cfg).write_text(json.dumps(locales, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass   # sin la firma local solo se pierde el ahorro; la próxima vez se compara con la base
    return estado


def recalcular(con):
    """Vuelve a aplicar reglas.py a todo el histórico (útil si cambian las reglas)."""
    global _escrituras
    cambios = [(_compacto(reglas.novedades(crudo(con, r["crudo"]))), r["id"])
               for r in con.execute("SELECT id, crudo FROM respuestas").fetchall()]
    with con:
        con.executemany("UPDATE respuestas SET novedades=? WHERE id=?", cambios)
    _escrituras += 1


def compactar(con):
    """Pasa las respuestas guardadas en el formato antiguo (dict con los nombres de columna en cada fila) al
    formato compacto. Devuelve cuántas filas cambió."""
    global _escrituras
    viejas = con.execute("SELECT id, crudo, novedades FROM respuestas WHERE crudo LIKE '{%' "
                         "OR novedades LIKE '%\": %'").fetchall()
    columnas, cambios = set(), []
    for r in viejas:
        fila = crudo(con, r["crudo"])
        if r["crudo"].startswith("{"):
            columnas.add(columnas_de(fila))
            texto = _compacto([columnas_de(fila)[0], *fila.values()])
        else:
            texto = r["crudo"]
        cambios.append((texto, _compacto(json.loads(r["novedades"])), r["id"]))
    with con:
        if columnas:
            con.executemany(GUARDAR_COLUMNAS, list(columnas))
        for inicio in range(0, len(cambios), 1000):
            con.executemany("UPDATE respuestas SET crudo=?, novedades=? WHERE id=?", cambios[inicio:inicio + 1000])
    _escrituras += 1
    return len(cambios)


def subir(origen_sqlite, destino):
    """Copia todo lo de una base SQLite local (versión anterior) a la base de destino, sin duplicar, y lo deja en
    formato compacto. Devuelve cuántas filas se copiaron por tabla."""
    global _escrituras
    origen = sqlite3.connect(origen_sqlite)
    origen.row_factory = sqlite3.Row
    columnas = {
        "respuestas": ("id", "fecha", "dia", "nombre", "persona", "lugar", "responsable", "observacion",
                       "novedades", "crudo"),
        "columnas": ("id", "nombres"),
        "fuentes": ("ruta", "firma", "ultima_respuesta", "revisado"),
        "ia": ("dia", "entrada", "respuesta", "modelo", "creado"),
        "envios": ("dia", "destinatarios", "enviado"),
        "valoraciones": ("dia", "respuesta_id", "situacion", "consejo", "voto", "correccion", "creado"),
    }
    llaves = {"respuestas": "id", "columnas": "id", "fuentes": "ruta", "ia": "dia", "envios": "dia",
              "valoraciones": "respuesta_id, consejo"}
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
    _escrituras += 1
    compactar(destino)
    return copiadas


# --- Lectura -------------------------------------------------------------------------------------------------

_memoria = {"version": None}
_candado = threading.Lock()


class Registros(list):
    """Todas las respuestas (sin crudo), en orden de fecha, con listas útiles ya calculadas."""
    dias: list
    lugares: list
    personas: list
    ultima: str


def registros(con):
    """Respuestas en memoria. Cuesta una consulta pequeña por página; solo se vuelven a pedir todas cuando
    cambian los datos (subida del PC puente o escritura de este mismo proceso).

    Las novedades idénticas (muy comunes: 'No usa: Tapaoídos'...) comparten el mismo objeto para ocupar menos
    memoria; no se deben modificar."""
    v = con.execute("SELECT (SELECT max(revisado) FROM fuentes), count(*), max(id) FROM respuestas").fetchone()
    version = (con.ident, _escrituras, v[0], v[1], v[2])
    if _memoria["version"] == version:
        return _memoria["registros"]
    with _candado:
        if _memoria["version"] == version:
            return _memoria["registros"]
        leidas = {}
        lista = Registros()
        for r in con.execute("SELECT id, fecha, dia, nombre, persona, lugar, responsable, observacion, novedades "
                             "FROM respuestas ORDER BY fecha"):
            d = dict(r)
            texto = d["novedades"]
            if texto not in leidas:
                leidas[texto] = json.loads(texto)
            d["novedades"] = leidas[texto]
            lista.append(d)
        lista.dias = sorted({r["dia"] for r in lista})
        lista.lugares = sorted({r["lugar"] for r in lista})
        nombres = {}
        for r in lista:
            nombres[r["persona"]] = max(nombres.get(r["persona"], ""), r["nombre"])
        lista.personas = sorted(nombres.values())
        lista.ultima = lista[-1]["fecha"] if lista else ""
        _memoria.update(version=version, registros=lista)
        return lista


def crudos(con, ids):
    """{id: fila completa del Excel} solo para las respuestas pedidas (la pestaña Datos con todas las columnas)."""
    ids, resultado = list(ids), {}
    for inicio in range(0, len(ids), 500):
        parte = ids[inicio:inicio + 500]
        for r in con.execute(f"SELECT id, crudo FROM respuestas WHERE id IN ({','.join('?' * len(parte))})", parte):
            resultado[r[0]] = crudo(con, r[1])
    return resultado


def ultima_sincronizacion(con):
    r = con.execute("SELECT max(revisado) FROM fuentes").fetchone()[0]
    return r or ""


def ultima_respuesta(con):
    return con.execute("SELECT max(fecha) FROM respuestas").fetchone()[0] or ""
