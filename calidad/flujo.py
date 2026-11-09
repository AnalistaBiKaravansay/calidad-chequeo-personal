"""Entrada directa desde Power Automate (sin PC puente).

El flujo de Forms, justo después de "Agregar una fila a una tabla" del Excel, envía con la acción HTTP la fila
que acaba de escribir (body de esa acción): las mismas columnas del Excel. Aquí se guarda igual que la guarda
el puente (datos.guardar), así que los dos caminos pueden convivir: si una respuesta llega por ambos, se
actualiza la misma fila (misma Id) y no se duplica.

Protección: encabezado "x-token" igual a CALIDAD_TOKEN_FLUJO (Render lo genera). Sin ese valor configurado,
la entrada está apagada.
"""
import gzip
import hmac
import json
import os
import re
import threading
from contextlib import closing

from . import datos, reporte

# El conector de Excel escribe algunos caracteres de los encabezados en código: "BPM_x002e_Uso" = "BPM.Uso".
_CODIGO = re.compile(r"_x([0-9A-Fa-f]{4})_")
# Columnas que agrega el conector de Excel y que no son del formulario.
_AJENAS = ("ItemInternalId",)
_ia_candado = threading.Lock()
_ia_pendientes = set()


def token():
    return os.environ.get("CALIDAD_TOKEN_FLUJO", "").strip()


def token_valido(recibido):
    esperado = token()
    return bool(esperado) and hmac.compare_digest((recibido or "").strip().encode(), esperado.encode())


def leer_cuerpo(crudo, encabezados):
    """Bytes recibidos -> JSON. Acepta gzip y textos en UTF-8 (con o sin BOM) o Latin-1."""
    if crudo[:2] == bytes([0x1F, 0x8B]) or "gzip" in encabezados.get("content-encoding", ""):
        crudo = gzip.decompress(crudo)
    if not crudo.strip():
        # Para diagnosticar: nombres de los encabezados recibidos y los de tamaño/tipo (nunca el token).
        vistos = {k: v for k, v in encabezados.items()
                  if k.lower() in ("content-type", "content-length", "transfer-encoding", "content-encoding", "expect")}
        raise ValueError(f"Llegó el cuerpo vacío. Encabezados: {sorted(k.lower() for k in encabezados.keys())}; "
                         f"{vistos}. En la acción HTTP, el Body debe ser body('Nombre_de_la_accion_de_Excel').")
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    try:
        return json.loads(texto)
    except ValueError:
        raise ValueError(f"El cuerpo no es JSON ({len(crudo)} bytes, Content-Type: "
                         f"{encabezados.get('content-type', '-')}, empieza por {texto[:1]!r}).")


def _encabezado(nombre):
    return " ".join(_CODIGO.sub(lambda m: chr(int(m.group(1), 16)), str(nombre)).split(" ")).strip()


def limpiar(fila):
    """Deja la fila como la lee el puente del Excel: sin metadatos del conector, vacíos como None, Id numérica."""
    if isinstance(fila, str):   # el flujo envió el JSON como texto
        try:
            fila = json.loads(fila)
        except ValueError:
            raise ValueError("El cuerpo es texto, no la fila del Excel. Use la expresión body('Nombre_de_la_accion').")
    if isinstance(fila, dict) and "Id" not in fila and isinstance(fila.get("body"), dict):
        fila = fila["body"]   # se envió outputs(...) en vez de body(...)
    if not isinstance(fila, dict):
        raise ValueError("Cada respuesta debe ser un objeto con las columnas del Excel.")
    limpia = {}
    for k, v in fila.items():
        if str(k).startswith("@") or k in _AJENAS:
            continue
        limpia[_encabezado(k)] = None if (v is None or (isinstance(v, str) and not v.strip())) else v
    if limpia.get("Id") in (None, ""):
        # Solo los nombres de las columnas (nunca los valores, que pueden ser datos de salud).
        raise ValueError("Falta la columna Id. Columnas recibidas: " + ", ".join(list(limpia)[:40]))
    try:
        limpia["Id"] = int(float(str(limpia["Id"]).strip()))
    except ValueError:
        raise ValueError(f"La Id no es un número: {limpia['Id']!r}")
    if not (limpia.get("Hora de finalización") or limpia.get("Hora de inicio")):
        raise ValueError("Falta la columna 'Hora de finalización'.")
    return limpia


def recibir(cuerpo):
    """Guarda una respuesta (objeto) o varias (lista, o {"filas": [...]}). Devuelve el resumen y los días con
    novedades, para pedir los consejos de la IA."""
    if isinstance(cuerpo, dict) and isinstance(cuerpo.get("filas"), list):
        cuerpo = cuerpo["filas"]
    filas = [limpiar(f) for f in (cuerpo if isinstance(cuerpo, list) else [cuerpo])]
    guardadas, dias_ia = [], set()
    with closing(datos.conectar()) as con:
        with con:
            for f in filas:
                v = datos.valores(f)   # también valida la fecha antes de escribir nada
                datos.guardar(con, f)
                guardadas.append({"id": v[0], "fecha": v[1], "novedades": v[8] != "[]"})
                if v[8] != "[]":
                    dias_ia.add(v[2])
    return {"ok": True, "guardadas": guardadas}, sorted(dias_ia)


def consejos_ia(dias):
    """Se ejecuta después de responder al flujo. Pide a la IA solo los casos nuevos de esos días (los ya
    respondidos se conservan). Si llegan varias respuestas seguidas, se hace una sola consulta por día."""
    _ia_pendientes.update(dias)
    while _ia_pendientes:
        if not _ia_candado.acquire(blocking=False):
            return   # ya hay una consulta en curso; tomará estos días al terminar
        try:
            while _ia_pendientes:
                dia = _ia_pendientes.pop()
                try:
                    with closing(datos.conectar()) as con:
                        estado = reporte.construir(con, dia)["ia"]["estado"]
                    print(f"IA {dia}: {estado}")
                except Exception as e:   # la respuesta ya quedó guardada; la IA se puede pedir luego en la página
                    print(f"IA {dia}: no se pudo consultar: {e}")
        finally:
            _ia_candado.release()
