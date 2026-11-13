"""Consejos de la IA (Google Gemini) para las novedades del día.

- Una sola consulta por día con todos los casos (la capa gratuita tiene pocas consultas diarias).
- Se prueban los modelos gratuitos de config.json en orden (del mejor al más básico); si uno está saturado
  o sin cuota, se pasa al siguiente.
- A la IA NO se le envía el nombre: cada persona va como C1, C2... con su lugar, novedades e historial.
- La IA solo complementa: la acción obligatoria sale siempre de guia.py, aunque la IA falle. Se le envían los
  pasos de la guía que el reporte ya muestra para que no los repita.
- "Entrenamiento": Calidad marca cada consejo (👍/👎 o corrección) y las marcas recientes van como ejemplos
  en la consulta diaria (sin nombres), sin consultas extra.
- Ahorro: cada caso se identifica por su contenido. Si llegan casos nuevos durante el día, solo esos se
  consultan; los ya respondidos se conservan. De la guía solo van las partes que aplican a esos casos, y el JSON
  va sin espacios.
"""
import hashlib
import json
import re
from datetime import datetime
from difflib import SequenceMatcher

import httpx

from . import config, guia

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

INSTRUCCIONES = """Eres un asistente del área de Calidad de una planta de alimentos en Colombia.
Cada día recibes las novedades del chequeo de personal (sin nombres) y debes dar a la persona de Calidad
consejos prácticos sobre qué hacer con cada caso.

MUY IMPORTANTE: el reporte YA le muestra a Calidad los pasos de la guía de cada caso (campo "ya_indicado").
NO los repitas ni los digas con otras palabras. Tu valor está en lo que la guía NO dice para ESTE caso:
- qué preguntarle a la persona según lo que escribió en la observación (por ejemplo, desde cuándo, si mejora,
  si pasa en una tarea concreta);
- qué patrón ves en sus fechas anteriores (por ejemplo, todos los lunes, empeora, alterna con otro síntoma);
- qué verificar o con quién coordinar (SST, jefe de área) y cómo priorizar este caso frente a los demás.
Si no tienes nada nuevo que aportar a un caso, devuelve "consejos": [] para ese caso.

Reglas:
- Usa SOLO la GUÍA de abajo como base. Cita la fuente entre corchetes cuando aplique, por ejemplo [R2674 art. 14 num. 2].
  Usa solo los códigos de FUENTES (PI, R2674, INVIMA, FDA, CODEX, INS); no inventes otros.
- No diagnostiques enfermedades, no recetes medicamentos y no decidas la aptitud laboral: eso es del médico o de SST.
- No contradigas la acción obligatoria de la guía (por ejemplo, la exclusión ante síntomas de alerta de ETA).
- Es una planta de manufactura: prioriza consejos INMEDIATOS y prácticos que Calidad pueda aplicar en el turno
  (tapabocas, lavado de manos, pausa, hidratación, rotar de tarea, revisar el puesto con SST).
- Para síntomas que no son alerta ETA mira el campo "nivel": 1 = consejo inmediato, 2 = seguimiento con la persona,
  3 = persiste mucho más de lo normal. NO sugieras ir al médico ni a la EPS salvo en nivel 3 o en alerta ETA.
  Tener gripa o dolor unos pocos días es normal en la planta y no es motivo de cita médica.
- Si la observación sugiere algo que la guía considera alerta (por ejemplo, "soltura" frecuente), señálalo.
- Escribe en español sencillo, frases cortas, de 0 a 3 consejos por caso.
- Habla solo de las novedades que recibes en cada caso; no menciones EPP ni dotación (eso se maneja aparte).
- "resumen_dia": 2 o 3 frases sobre lo más importante del día para Calidad.

Responde únicamente con JSON con esta forma:
{"resumen_dia": "...", "casos": [{"codigo": "C1", "consejos": ["...", "..."], "atencion": "frase corta opcional"}]}
"""


def _sin_nombre(texto, nombre):
    for parte in (p for p in nombre.split() if len(p) > 2):
        texto = re.sub(re.escape(parte), "[persona]", texto, flags=re.IGNORECASE)
    return texto


# Tipos de novedad que se consultan a la IA: solo enfermedad (posible ETA, síntomas y lesiones). BPM, EPP,
# dotación y observaciones sin clasificar no se envían: tienen su guía fija y así se ahorran créditos.
TIPOS_IA = ("eta", "salud", "lesion")


def preparar(casos):
    """Datos que se envían a la IA (sin nombres): solo las novedades de enfermedad (TIPOS_IA)."""
    entrada = []
    for c in casos:
        items = [i for i in c["items"] if i["tipo"] in TIPOS_IA]
        if not items:
            continue
        ya_indicado = []
        for i in items:
            ya_indicado += [p for p in i["pasos"] if p not in ya_indicado]
        entrada.append({
            "codigo": c["codigo"],
            "lugar": c["lugar"],
            "hora": c["fecha"][11:16],
            "observacion": _sin_nombre(c["observacion"], c["nombre"]),
            "dias_con_sintomas_30d": c["dias_salud_previos"],
            "novedades": [{"tipo": i["tipo"], "novedad": i["etiqueta"], "dias_en_30d": i["repeticiones"] + 1,
                           "fechas_anteriores": i["dias_previos"],
                           **({"nivel": i["nivel"]} if i.get("nivel") else {}),
                           **({"nota": i["nota"]} if i.get("nota") else {})} for i in items],
            "ya_indicado": ya_indicado,
        })
    return entrada


def _parecido(a, b):
    limpiar = lambda t: re.sub(r"\[[^\]]*\]|[^\w ]", "", t.lower())
    return SequenceMatcher(None, limpiar(a), limpiar(b)).ratio()


def quitar_repetidos(respuesta, entrada, limite=0.6):
    """Elimina consejos de la IA que casi copian un paso que el reporte ya muestra."""
    guia_por_caso = {c["codigo"]: c["ya_indicado"] for c in entrada}
    for codigo, caso in respuesta["casos"].items():
        caso["consejos"] = [x for x in caso["consejos"]
                            if all(_parecido(x, p) < limite for p in guia_por_caso.get(codigo, []))]
    return respuesta


def situacion(fila):
    """Descripción de un caso sin nombre, para guardar junto a la marca de Calidad."""
    novedades = [n["etiqueta"] for n in fila["novedades"] if n["tipo"] not in ("dotacion", "epp")]
    obs = _sin_nombre(fila["observacion"], fila["nombre"])
    return "; ".join(novedades) + (f". Observación: “{obs}”" if obs else "")


def guardar_valoracion(con, respuesta_id, consejo, voto=None, correccion=None):
    """voto: 1 útil, -1 no sirve. correccion: cómo lo diría Calidad. None deja el valor anterior."""
    fila = con.execute("SELECT * FROM respuestas WHERE id=?", (respuesta_id,)).fetchone()
    if not fila:
        raise ValueError("La respuesta no existe.")
    fila = {**dict(fila), "novedades": json.loads(fila["novedades"])}
    if correccion is not None:
        correccion = _sin_nombre(correccion.strip(), fila["nombre"])
    with con:
        con.execute(
            "INSERT INTO valoraciones(dia, respuesta_id, situacion, consejo, voto, correccion, creado) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(respuesta_id, consejo) DO UPDATE SET "
            "voto=coalesce(excluded.voto, valoraciones.voto), "
            "correccion=coalesce(excluded.correccion, valoraciones.correccion), creado=excluded.creado",
            (fila["dia"], respuesta_id, situacion(fila), consejo, voto, correccion,
             datetime.now().isoformat(timespec="seconds")))


def ejemplos(con, cuantos=12):
    """Texto con las marcas más recientes de Calidad, para que la IA imite su estilo y criterio."""
    consulta = lambda where: con.execute(
        f"SELECT situacion, consejo, correccion FROM valoraciones WHERE {where} ORDER BY creado DESC LIMIT ?",
        (cuantos,)).fetchall()
    corregidos = consulta("correccion IS NOT NULL AND correccion<>''")
    utiles = consulta("voto=1 AND (correccion IS NULL OR correccion='')")
    malos = consulta("voto=-1 AND (correccion IS NULL OR correccion='')")
    if not (corregidos or utiles or malos):
        return ""
    lineas = ["APRENDIZAJES DE CALIDAD (marcas reales de la persona de Calidad de esta planta; imita los útiles y "
              "las correcciones y evita lo marcado como no útil):"]
    lineas += [f"- Caso: {r['situacion']} | La IA dijo: {r['consejo']} | Calidad prefiere: {r['correccion']}"
               for r in corregidos]
    lineas += [f"- ÚTIL. Caso: {r['situacion']} | Consejo: {r['consejo']}" for r in utiles]
    lineas += [f"- NO ÚTIL, no repetir este tipo de consejo: {r['consejo']}" for r in malos]
    return "\n".join(lineas)


def valoraciones_del_dia(con, dia):
    """{(respuesta_id, consejo): {'voto', 'correccion'}} para mostrar las marcas en la página."""
    return {(r["respuesta_id"], r["consejo"]): {"voto": r["voto"], "correccion": r["correccion"]}
            for r in con.execute("SELECT respuesta_id, consejo, voto, correccion FROM valoraciones WHERE dia=?", (dia,))}


def resumen_aprendizaje(con):
    r = con.execute("SELECT sum(CASE WHEN voto=1 THEN 1 ELSE 0 END), sum(CASE WHEN voto=-1 THEN 1 ELSE 0 END), "
                    "sum(CASE WHEN correccion IS NOT NULL AND correccion<>'' THEN 1 ELSE 0 END) "
                    "FROM valoraciones").fetchone()
    ultimas = con.execute("SELECT dia, situacion, consejo, correccion FROM valoraciones "
                          "WHERE correccion IS NOT NULL AND correccion<>'' ORDER BY creado DESC LIMIT 10").fetchall()
    return {"utiles": int(r[0] or 0), "no_utiles": int(r[1] or 0), "corregidos": int(r[2] or 0),
            "ultimas": [dict(x) for x in ultimas]}


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


def consultar(entrada, clave, modelo, timeout=60, aprendizajes="", tipos=None, claves=None, ya_revisados=None):
    texto = (INSTRUCCIONES + "\nGUÍA:\n" + guia.texto_para_ia(tipos, claves)
             + ("\n\n" + aprendizajes if aprendizajes else "")
             + ("\n\nCASOS YA REVISADOS HOY (solo para el resumen_dia; no los incluyas en \"casos\"):\n"
                + _json(ya_revisados) if ya_revisados else "")
             + "\n\nCASOS DEL DÍA:\n" + _json(entrada))
    r = httpx.post(URL.format(modelo=modelo), headers={"x-goog-api-key": clave}, timeout=timeout, json={
        "contents": [{"role": "user", "parts": [{"text": texto}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    })
    if r.status_code == 429:
        raise RuntimeError("Se alcanzó el límite gratuito de consultas de Gemini por hoy.")
    if r.status_code >= 400:
        detalle = r.json().get("error", {}).get("message", r.text[:200]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
        raise RuntimeError(f"Gemini respondió {r.status_code}: {detalle}")
    partes = r.json()["candidates"][0]["content"]["parts"]
    return quitar_repetidos(validar(json.loads("".join(p.get("text", "") for p in partes)), entrada), entrada)


def validar(datos, entrada):
    codigos = {c["codigo"] for c in entrada}
    casos = {}
    for c in datos.get("casos", []):
        if c.get("codigo") in codigos and isinstance(c.get("consejos"), list):
            casos[c["codigo"]] = {"consejos": [str(x) for x in c["consejos"] if str(x).strip()][:3],
                                  "atencion": str(c.get("atencion") or "")}
    return {"resumen_dia": str(datos.get("resumen_dia") or ""), "casos": casos}


def _firma_caso(caso):
    """Identifica un caso por su contenido (sin el código C1, C2..., que cambia si llegan casos nuevos)."""
    sin_codigo = {k: v for k, v in caso.items() if k != "codigo"}
    return hashlib.sha256(json.dumps(sin_codigo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _guardadas(guardada, entrada, firmas):
    """(respuestas guardadas por firma de caso, resumen) a partir de la fila de la tabla ia."""
    if not guardada:
        return {}, ""
    datos_ia = json.loads(guardada["respuesta"])
    if datos_ia.get("formato") == 2:
        return datos_ia["casos"], datos_ia.get("resumen_dia", "")
    # Formato anterior (por código): sirve solo si los casos del día no cambiaron.
    firma_antigua = hashlib.sha256(json.dumps(entrada, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if guardada["entrada"] != firma_antigua:
        return {}, ""
    return ({firmas[c]: v for c, v in datos_ia.get("casos", {}).items() if c in firmas},
            datos_ia.get("resumen_dia", ""))


def consejos_del_dia(con, dia, casos, cfg=None, consultar_ia=True):
    """Devuelve {'estado', 'resumen_dia', 'casos'}. Reutiliza lo guardado y solo consulta los casos nuevos."""
    cfg = cfg or config.cargar()
    entrada = preparar(casos)
    if not entrada:
        return {"estado": "sin casos", "resumen_dia": "", "casos": {}}
    firmas = {c["codigo"]: _firma_caso(c) for c in entrada}
    guardada = con.execute("SELECT entrada, respuesta, modelo FROM ia WHERE dia=?", (dia,)).fetchone()
    previas, resumen = _guardadas(guardada, entrada, firmas)
    por_codigo = lambda: {c: previas[f] for c, f in firmas.items() if f in previas}
    faltan = [c for c in entrada if firmas[c["codigo"]] not in previas]
    if not faltan:
        return {"estado": "ok", "modelo": guardada["modelo"], "resumen_dia": resumen, "casos": por_codigo()}
    if not consultar_ia:
        return {"estado": "pendiente", "resumen_dia": resumen, "casos": por_codigo()}
    clave = config.clave_ia(cfg)
    if not clave:
        return {"estado": "sin clave", "resumen_dia": resumen, "casos": por_codigo()}
    # Tipos y claves de los casos que se consultan, para enviar solo esa parte de la guía.
    codigos = {c["codigo"] for c in faltan}
    tipos, claves = set(), set()
    for caso in casos:
        if caso.get("codigo") in codigos:
            for i in caso["items"]:
                if i["tipo"] in TIPOS_IA:
                    tipos.add(i["tipo"])
                    claves.add(i["clave"])
                    if i["etiqueta"].startswith("Mencionado"):
                        claves.add("mencion")
    ya_revisados = [{"codigo": c["codigo"], "lugar": c["lugar"], "novedades": [n["novedad"] for n in c["novedades"]]}
                    for c in entrada if c["codigo"] not in codigos]
    errores = []
    aprendizajes = ejemplos(con)
    # Del mejor al más básico: si uno está saturado, sin cuota o no responde, se pasa al siguiente.
    for modelo in cfg["ia_modelos"]:
        try:
            respuesta = consultar(faltan, clave, modelo, aprendizajes=aprendizajes, tipos=tipos, claves=claves,
                                  ya_revisados=ya_revisados)
        except (httpx.HTTPError, RuntimeError, ValueError, KeyError, IndexError) as e:
            errores.append(f"{modelo}: {str(e)[:80]}")
            continue
        vigentes = set(firmas.values())
        previas = {f: v for f, v in previas.items() if f in vigentes}   # se olvidan los casos que ya no están
        for c in faltan:
            previas[firmas[c["codigo"]]] = respuesta["casos"].get(c["codigo"], {"consejos": [], "atencion": ""})
        resumen = respuesta["resumen_dia"] or resumen
        firma_dia = hashlib.sha256("|".join(sorted(vigentes)).encode()).hexdigest()[:16]
        with con:
            con.execute("INSERT INTO ia(dia, entrada, respuesta, modelo, creado) VALUES (?,?,?,?,?) "
                        "ON CONFLICT(dia) DO UPDATE SET entrada=excluded.entrada, respuesta=excluded.respuesta, "
                        "modelo=excluded.modelo, creado=excluded.creado",
                        (dia, firma_dia, _json({"formato": 2, "resumen_dia": resumen, "casos": previas}), modelo,
                         datetime.now().isoformat(timespec="seconds")))
        return {"estado": "ok", "modelo": modelo, "resumen_dia": resumen, "casos": por_codigo()}
    return {"estado": "no disponible: ningún modelo respondió (" + " | ".join(errores) + ")",
            "resumen_dia": resumen, "casos": por_codigo()}
