"""Novedades del día con historial por persona, alertas de patrones y cifras del tablero."""
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import guia
from .datos import filas
from .reglas import ETIQUETAS, PRIORIDAD

SALUD = ("eta", "salud")
GRUPOS = {
    "gastrointestinales": {"diarrea", "vomito", "digestivo"},
    "respiratorios": {"fiebre_garganta", "fiebre", "garganta", "respiratorio"},
    "de ictericia": {"ictericia"},
    "de piel o heridas infectadas": {"herida_infectada", "piel"},
}
# Posible brote: personas del mismo lugar, el mismo día, con síntomas parecidos (descripción, claves, mínimo).
# El INS define brote de ETA desde 2 personas; para síntomas más comunes (cólicos, gripa) se exige 3.
BROTE = [
    ("diarrea o vómito", {"diarrea", "vomito"}, 2),
    ("ictericia", {"ictericia"}, 2),
    ("síntomas gastrointestinales", GRUPOS["gastrointestinales"], 3),
    ("síntomas respiratorios", GRUPOS["respiratorios"], 3),
    ("síntomas de piel o heridas infectadas", GRUPOS["de piel o heridas infectadas"], 3),
]
SECCIONES = [
    ("eta", "Alertas de salud: posible ETA", {"eta"}),
    ("salud", "Otros síntomas, lesiones y observaciones por revisar", {"salud", "lesion", "revisar"}),
    ("bpm", "Incumplimientos BPM", {"bpm"}),
    ("dotacion", "Dotación", {"dotacion"}),
    ("epp", "Elementos de protección (EPP) marcados NO", {"epp"}),
]


def _dia(texto):
    return date.fromisoformat(texto)


def _restar(dia, dias):
    return (_dia(dia) - timedelta(days=dias)).isoformat()


def _es_salud(novedad):
    return novedad["tipo"] in SALUD and novedad["clave"] != "embarazo"


def historial(con, dia, dias):
    """persona -> {clave: [días], '_salud': {días con algún síntoma}} antes del día indicado."""
    h = defaultdict(lambda: defaultdict(set))
    for r in filas(con, "SELECT dia, persona, novedades FROM respuestas WHERE dia>=? AND dia<?", _restar(dia, dias), dia):
        for n in r["novedades"]:
            h[r["persona"]][n["clave"]].add(r["dia"])
            if _es_salud(n):
                h[r["persona"]]["_salud"].add(r["dia"])
    return h


# Escalera para síntomas que no son alerta ETA: los límites salen de los datos de la propia planta.
NIVEL_SEGUIMIENTO, NIVEL_MEDICO = 0.75, 0.90      # percentiles
MINIMO_SEGUIMIENTO, MINIMO_MEDICO = 3, 5          # días en 30, aunque los datos digan menos
_umbrales = {}


def umbrales(con, hasta):
    """clave -> (días para seguimiento, días para sugerir cita médica), según el último año de la planta.

    Para cada reporte de un síntoma se cuenta en cuántos días de los últimos 30 lo tuvo la misma persona.
    Seguimiento = percentil 75 de esos conteos; cita médica = percentil 90.
    """
    llave = (hasta, con.execute("SELECT count(*) FROM respuestas").fetchone()[0])
    if llave in _umbrales:
        return _umbrales[llave]
    dias = defaultdict(set)
    for r in filas(con, "SELECT dia, persona, novedades FROM respuestas WHERE dia>? AND dia<=?",
                   _restar(hasta, 365), hasta):
        for n in r["novedades"]:
            if n["tipo"] in ("salud", "lesion"):
                dias[(r["persona"], n["clave"])].add(r["dia"])
    conteos = defaultdict(list)
    for (_, clave), ds in dias.items():
        ds = sorted(ds)
        for d in ds:
            inicio = _restar(d, 29)
            conteos[clave].append(sum(1 for x in ds if inicio <= x <= d))
    percentil = lambda v, q: sorted(v)[min(len(v) - 1, int(q * len(v)))]
    resultado = defaultdict(lambda: (MINIMO_SEGUIMIENTO, MINIMO_MEDICO))
    for clave, v in conteos.items():
        if len(v) >= 15:
            seg = max(MINIMO_SEGUIMIENTO, percentil(v, NIVEL_SEGUIMIENTO))
            resultado[clave] = (seg, max(MINIMO_MEDICO, seg + 1, percentil(v, NIVEL_MEDICO)))
    _umbrales[llave] = resultado
    return resultado


def nivel(veces, limites):
    """1 = consejo inmediato, 2 = seguimiento, 3 = sugerir cita médica."""
    seguimiento, medico = limites
    return 3 if veces >= medico else 2 if veces >= seguimiento else 1


def novedades_del_dia(con, dia, dias=30):
    respuestas = filas(con, "SELECT * FROM respuestas WHERE dia=? ORDER BY fecha", dia)
    hist = historial(con, dia, dias)
    limites = umbrales(con, dia)
    casos = []
    for r in respuestas:
        if not r["novedades"]:
            continue
        previo = hist.get(r["persona"], {})
        dias_salud = len(previo.get("_salud", ()))
        items = []
        for n in r["novedades"]:
            repeticiones = len(previo.get(n["clave"], ()))
            extra = {}
            if n["tipo"] in ("salud", "lesion"):
                extra = {"nivel": nivel(repeticiones + 1, limites[n["clave"]]), "limites": limites[n["clave"]]}
            items.append({**n, **extra, "repeticiones": repeticiones,
                          "dias_previos": sorted(previo.get(n["clave"], ()))[-5:],
                          "pasos": guia.pasos_para(n, repeticiones, extra.get("nivel"), extra.get("limites"))})
        principal = min(items, key=lambda i: PRIORIDAD[i["tipo"]])["tipo"]
        casos.append({**r, "items": items, "dias_salud_previos": dias_salud, "prioridad": PRIORIDAD[principal],
                      "seccion": next(s for s, _, tipos in SECCIONES if principal in tipos)})
    casos.sort(key=lambda c: (c["prioridad"], c["nombre"]))
    for i, c in enumerate(casos, 1):
        c["codigo"] = f"C{i}"
    return respuestas, casos


def alertas_patrones(con, dia):
    """Señales de algo anormal: varias personas con síntomas parecidos o un aumento semanal."""
    alertas = []
    registros = filas(con, "SELECT dia, persona, lugar, novedades FROM respuestas WHERE dia>? AND dia<=?",
                      _restar(dia, 63), dia)
    con_sintoma = lambda r, claves: any(_es_salud(n) and n["clave"] in claves for n in r["novedades"])
    avisados = set()
    for descripcion, claves, minimo in BROTE:
        hoy = defaultdict(set)
        for r in registros:
            if r["dia"] == dia and con_sintoma(r, claves):
                hoy[r["lugar"]].add(r["persona"])
        for lugar, personas in sorted(hoy.items()):
            if len(personas) >= minimo and (lugar, frozenset(personas)) not in avisados:
                avisados.add((lugar, frozenset(personas)))
                alertas.append({"nivel": "alta", "texto":
                    f"{len(personas)} personas de {lugar} reportan {descripcion} hoy. Revisar si comparten área, "
                    "turno, agua o alimentos y avisar a Calidad como posible brote."})
    for grupo, claves in GRUPOS.items():
        semana, base = set(), set()
        for r in registros:
            if con_sintoma(r, claves):
                (semana if r["dia"] > _restar(dia, 7) else base).add((r["persona"], r["dia"]))
        promedio = len(base) / 8
        if len(semana) >= 5 and len(semana) >= 2 * max(promedio, 1):
            alertas.append({"nivel": "media", "texto":
                f"Síntomas {grupo}: {len(semana)} casos en los últimos 7 días, frente a un promedio de "
                f"{promedio:.1f} por semana en las 8 semanas anteriores."})
    return alertas


def resumen_dia(respuestas, casos):
    personas = lambda tipos: len({c["persona"] for c in casos if any(i["tipo"] in tipos for i in c["items"])})
    return {"respuestas": len(respuestas), "eta": personas({"eta"}), "salud": personas({"salud", "lesion"}),
            "bpm": personas({"bpm"}), "dotacion": personas({"dotacion", "epp"})}


def tablero(con, hasta, lugar="", persona=""):
    """Cifras para el tablero histórico. 'hasta' es el último día con datos; 'persona' es la clave normalizada."""
    filtro, args = "", []
    if lugar:
        filtro += " AND lugar=?"; args.append(lugar)
    if persona:
        filtro += " AND persona=?"; args.append(persona)
    todas = filas(con, f"SELECT dia, persona, nombre, lugar, novedades FROM respuestas WHERE dia<=? {filtro}", hasta, *args)

    meses = defaultdict(Counter)
    for r in todas:
        mes = meses[r["dia"][:7]]
        mes["respuestas"] += 1
        for tipo in {n["tipo"] for n in r["novedades"]}:
            mes[tipo] += 1
    por_mes = [{"mes": m, **meses[m]} for m in sorted(meses)][-13:]

    desde90, desde30, desde84 = _restar(hasta, 90), _restar(hasta, 30), _restar(hasta, 84)
    sintomas, problemas, lugares = Counter(), Counter(), defaultdict(Counter)
    semanas = defaultdict(Counter)
    recurrentes = defaultdict(lambda: {"dias": set(), "claves": Counter(), "nombre": ""})
    for r in todas:
        if r["dia"] > desde84:
            semana = (_dia(r["dia"]) - timedelta(days=_dia(r["dia"]).weekday())).isoformat()
            semanas[semana]["respuestas"] += 1
            for grupo, claves in GRUPOS.items():
                if any(_es_salud(n) and n["clave"] in claves for n in r["novedades"]):
                    semanas[semana][grupo] += 1
        if r["dia"] <= desde90:
            continue
        lugares[r["lugar"]]["respuestas"] += 1
        if any(_es_salud(n) for n in r["novedades"]):
            lugares[r["lugar"]]["salud"] += 1
        for n in r["novedades"]:
            if _es_salud(n):
                sintomas[n["etiqueta"]] += 1
            elif n["tipo"] != "salud":
                problemas[n["etiqueta"]] += 1
            if r["dia"] > desde30 and _es_salud(n):
                p = recurrentes[r["persona"]]
                p["dias"].add(r["dia"]); p["claves"][n["etiqueta"]] += 1; p["nombre"] = r["nombre"]

    personas = sorted(({"persona": k, "nombre": v["nombre"], "dias": len(v["dias"]),
                        "ultimo": max(v["dias"]), "sintomas": ", ".join(f"{e} ({c})" for e, c in v["claves"].most_common(3))}
                       for k, v in recurrentes.items() if len(v["dias"]) >= 2),
                      key=lambda p: (-p["dias"], p["nombre"]))
    return {
        "por_mes": por_mes,
        "semanas": [{"semana": s, **semanas[s]} for s in sorted(semanas)],
        "grupos": list(GRUPOS),
        "sintomas": sintomas.most_common(12),
        "problemas": problemas.most_common(12),
        "lugares": sorted(({"lugar": k, **v} for k, v in lugares.items()), key=lambda x: -x["respuestas"]),
        "recurrentes": personas[:25],
        "lista_lugares": [r[0] for r in con.execute("SELECT DISTINCT lugar FROM respuestas ORDER BY lugar")],
        "lista_personas": [r[0] for r in con.execute("SELECT max(nombre) FROM respuestas GROUP BY persona ORDER BY 1")],
    }


def persona(con, clave):
    registros = filas(con, "SELECT * FROM respuestas WHERE persona=? ORDER BY fecha DESC", clave)
    conteo = Counter(n["etiqueta"] for r in registros for n in r["novedades"])
    return registros, conteo.most_common()


def tabla(con, desde, hasta, lugar="", persona="", tipo="", texto="", limite=None, desplazamiento=0):
    """Respuestas filtradas para la pestaña Datos. tipo: '' todas, 'con' con alguna novedad, o un tipo de novedad.
    Devuelve (filas, total)."""
    condiciones, args = ["dia>=?", "dia<=?"], [desde, hasta]
    if lugar:
        condiciones.append("lugar=?"); args.append(lugar)
    if persona:
        condiciones.append("persona=?"); args.append(persona)
    if tipo == "con":
        condiciones.append("novedades<>'[]'")
    elif tipo:
        condiciones.append("novedades LIKE ?"); args.append(f'%"tipo": "{tipo}"%')
    if texto:
        condiciones.append("lower(observacion) LIKE lower(?)"); args.append(f"%{texto}%")
    where = " AND ".join(condiciones)
    total = con.execute(f"SELECT count(*) FROM respuestas WHERE {where}", args).fetchone()[0]
    paginado = f" LIMIT {int(limite)} OFFSET {int(desplazamiento)}" if limite else ""
    return filas(con, f"SELECT * FROM respuestas WHERE {where} ORDER BY fecha DESC{paginado}", *args), total


def etiqueta(clave):
    return ETIQUETAS.get(clave, clave)
