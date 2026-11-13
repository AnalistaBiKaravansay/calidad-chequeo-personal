"""Arma el reporte diario (el mismo contenido para el correo y para la página web)."""
from collections import defaultdict
from datetime import date, datetime

from jinja2 import Environment, PackageLoader, select_autoescape

from . import analisis, config, guia, ia

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
# Colores de cada tipo de novedad (paleta de la marca; texto blanco encima con contraste AA).
COLORES = {"eta": "#a43a28", "salud": "#b45309", "lesion": "#b45309", "revisar": "#6b5b95", "bpm": "#7a6200",
           "dotacion": "#57534a", "epp": "#57534a"}
NOMBRE_TIPO = {"eta": "Alerta ETA", "salud": "Salud", "lesion": "Lesión", "revisar": "Revisar", "bpm": "BPM",
               "dotacion": "Dotación", "epp": "EPP"}


def nombre_mes(mes, corto=False):
    """'2026-11' -> 'noviembre 2026' (o 'nov 2026')."""
    n = MESES[int(mes[5:7]) - 1]
    return f"{n[:3] if corto else n} {mes[:4]}"


def fecha_larga(dia):
    d = date.fromisoformat(dia)
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def veces(n):
    return "primera vez en el periodo" if n == 0 else f"{n + 1}.ª vez en 30 días"


plantillas = Environment(loader=PackageLoader("calidad", "templates"), autoescape=select_autoescape())
plantillas.globals.update(COLORES=COLORES, NOMBRE_TIPO=NOMBRE_TIPO, ETA=guia.ETA, ACCION_ETA=guia.ACCION_ETA,
                          REINTEGRO_ETA=guia.REINTEGRO_ETA, AVISO=guia.AVISO, FUENTES=guia.FUENTES,
                          NIVELES=guia.NIVELES, COLOR_NIVEL={1: "#2c6a45", 2: "#7a6200", 3: "#a43a28"})
plantillas.filters.update(fecha_larga=fecha_larga, veces=veces, nombre_mes=nombre_mes)


def estado_forms(con, cfg, dia):
    """Advierte si la fuente en vivo (el flujo, o si no el libro del Forms) no tiene respuestas del día."""
    fuente = "excel_flujo" if cfg.get("excel_flujo") else "excel_forms"
    if not cfg.get(fuente):
        return ""
    nombre = "Excel que llena Power Automate" if fuente == "excel_flujo" else "Excel del Forms en OneDrive"
    ruta = str(config.ruta_excel(cfg[fuente]))
    r = con.execute("SELECT ultima_respuesta FROM fuentes WHERE ruta=?", (ruta,)).fetchone()
    if not r:
        return f"No se ha podido leer el {nombre}. Revise que OneDrive esté sincronizando."
    if r["ultima_respuesta"][:10] < dia:
        hasta = r["ultima_respuesta"] or "(todavía sin respuestas)"
        if fuente == "excel_flujo":
            return (f"El {nombre} tiene respuestas hasta {hasta}. Si hoy sí hubo chequeos, revise que el flujo "
                    "esté activo y que OneDrive esté sincronizando.")
        return (f"El {nombre} solo tiene respuestas hasta el {hasta}. Pueden faltar respuestas de este día: "
                "abra el Excel en línea para que se actualice o configure el flujo de Power Automate (ver README).")
    return ""


def construir(con, dia, cfg=None, consultar_ia=True):
    cfg = cfg or config.cargar()
    respuestas, casos = analisis.novedades_del_dia(con, dia, cfg["dias_historial"])
    consejos = ia.consejos_del_dia(con, dia, casos, cfg, consultar_ia)
    # Los pasos generales se muestran una vez por sección; en cada caso solo los específicos
    # (protocolo ETA completo, consejo inmediato por síntoma, criterio BPM puntual y el paso por nivel o repetición).
    generales = {p for t, pasos in guia.PASOS.items() for p in pasos}
    for c in casos:
        pasos = []
        for i in c["items"]:
            if i["tipo"] not in ("dotacion", "epp"):
                pasos += [p for p in i["pasos"] if p not in pasos and (i["tipo"] == "eta" or p not in generales)]
        c["pasos"] = pasos
        c["ia"] = consejos["casos"].get(c["codigo"])
    secciones = []
    for s, t, tipos in analisis.SECCIONES:
        del_seccion = [c for c in casos if c["seccion"] == s]
        presentes = [x for x in guia.PASOS if x in tipos and x != "eta"
                     and any(i["tipo"] == x for c in del_seccion for i in c["items"])]
        secciones.append({"clave": s, "titulo": t, "casos": del_seccion,
                          "pasos": [p for x in presentes for p in guia.PASOS[x]]})
    # EPP: muchas respuestas lo marcan NO, así que se resume por elemento en lugar de listar cada caso.
    epp = defaultdict(list)
    for c in casos:
        for i in c["items"]:
            if i["tipo"] == "epp":
                epp[i["etiqueta"]].append(c["nombre"] + (f" ({veces(i['repeticiones'])})" if i["repeticiones"] >= 2 else ""))
    return {
        "dia": dia,
        "resumen": analisis.resumen_dia(respuestas, casos),
        "secciones": secciones,
        "alertas": analisis.alertas_patrones(con, dia),
        "mes": analisis.indicadores_mes(con, dia),
        "ia": consejos,
        "aviso_fuente": estado_forms(con, cfg, dia),
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pasos_dotacion": guia.PASOS["dotacion"],
        "pasos_epp": guia.PASOS["epp"],
        "epp": sorted(epp.items(), key=lambda e: -len(e[1])),
    }


def html_correo(contexto):
    return plantillas.get_template("correo.html").render(**contexto)


def asunto(contexto):
    r = contexto["resumen"]
    # Sin ":" ni "/" porque el asunto también se usa como nombre de archivo para Power Automate.
    partes = [f"{r['eta']} alerta(s) ETA"] if r["eta"] else []
    partes.append(f"{r['salud']} con síntomas o lesiones")
    return f"Chequeo de personal {contexto['dia']} - " + ", ".join(partes)
