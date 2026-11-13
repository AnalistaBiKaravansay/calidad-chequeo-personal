"""Novedades del día con historial por persona, alertas de patrones y cifras del tablero.

Todo se calcula sobre datos.registros (las respuestas en memoria): una página no hace consultas grandes a la base.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import guia
from .datos import registros
from .reglas import PRIORIDAD

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


def _entre(con, desde, hasta, incluir_desde=True):
    """Respuestas con desde <= dia <= hasta (o desde < dia si incluir_desde es False)."""
    return [r for r in registros(con)
            if (r["dia"] >= desde if incluir_desde else r["dia"] > desde) and r["dia"] <= hasta]


def historial(con, dia, dias):
    """persona -> {clave: [días], '_salud': {días con algún síntoma}} antes del día indicado."""
    h = defaultdict(lambda: defaultdict(set))
    desde = _restar(dia, dias)
    for r in (r for r in registros(con) if desde <= r["dia"] < dia):
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
    todas = registros(con)
    llave = (hasta, id(todas))   # la lista en memoria cambia cuando cambian los datos
    if llave in _umbrales:
        return _umbrales[llave]
    if len(_umbrales) > 50:
        _umbrales.clear()
    dias = defaultdict(set)
    for r in _entre(con, _restar(hasta, 365), hasta, incluir_desde=False):
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
    respuestas = [r for r in registros(con) if r["dia"] == dia]
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
    del_periodo = _entre(con, _restar(dia, 63), dia, incluir_desde=False)
    con_sintoma = lambda r, claves: any(_es_salud(n) and n["clave"] in claves for n in r["novedades"])
    avisados = set()
    for descripcion, claves, minimo in BROTE:
        hoy = defaultdict(set)
        for r in del_periodo:
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
        for r in del_periodo:
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
            "bpm": personas({"bpm"}), "dotacion": personas({"dotacion", "epp"}),
            "personas": len({r["persona"] for r in respuestas}),
            "sin_novedad": sum(1 for r in respuestas if not r["novedades"])}


# Indicadores del tablero: (clave, título, qué cuenta en cada chequeo, si subir es malo).
INDICADORES = [
    ("chequeos", "Chequeos", lambda r: True, False),
    ("eta", "Con alerta ETA", lambda r: any(n["tipo"] == "eta" for n in r["novedades"]), True),
    ("salud", "Con síntomas o lesión", lambda r: any(_es_salud(n) or n["tipo"] == "lesion" for n in r["novedades"]), True),
    ("bpm", "Incumplen BPM", lambda r: any(n["tipo"] == "bpm" for n in r["novedades"]), True),
    ("epp", "Sin algún EPP", lambda r: any(n["tipo"] == "epp" for n in r["novedades"]), True),
    ("dotacion", "Con novedad de dotación", lambda r: any(n["tipo"] == "dotacion" for n in r["novedades"]), True),
]
# Cumplimiento: chequeos sin ninguna novedad (subir es bueno).
SIN_NOVEDAD = ("sin_novedad", "Sin novedad", lambda r: not r["novedades"], False)
CATEGORIAS = [("eta", "Alertas ETA"), ("salud", "Síntomas"), ("lesion", "Lesiones"), ("revisar", "Observaciones por revisar"),
              ("bpm", "BPM"), ("epp", "EPP"), ("dotacion", "Dotación")]


def _semana(dia):
    return (_dia(dia) - timedelta(days=_dia(dia).weekday())).isoformat()


def _cifras_periodo(filas_):
    """Conteo de chequeos por indicador y personas distintas en un periodo."""
    cifras = {clave: sum(1 for r in filas_ if cuenta(r)) for clave, _, cuenta, _ in INDICADORES}
    cifras["personas"] = len({r["persona"] for r in filas_})
    return cifras


def _kpis(todas, hasta):
    """Últimos 30 días frente a los 30 anteriores."""
    desde30, desde60 = _restar(hasta, 30), _restar(hasta, 60)
    ahora = _cifras_periodo([r for r in todas if desde30 < r["dia"] <= hasta])
    antes = _cifras_periodo([r for r in todas if desde60 < r["dia"] <= desde30])
    kpis = []
    for clave, titulo, _, malo in INDICADORES:
        pct = round(100 * ahora[clave] / ahora["chequeos"], 1) if ahora["chequeos"] and clave != "chequeos" else None
        kpis.append({"clave": clave, "titulo": titulo, "valor": ahora[clave], "antes": antes[clave],
                     "malo_si_sube": malo, "pct": pct, "personas": ahora["personas"] if clave == "chequeos" else 0})
    return kpis


def _pct(parte, total):
    return round(100 * parte / total, 1) if total else 0.0


def indicadores_mes(con, dia, meses_atras=6, lugar=""):
    """Indicadores del mes del día (hasta ese día) frente al mes anterior completo, en % de los chequeos,
    la evolución de los últimos meses y el mes por lugar. Los meses tienen distinto número de chequeos:
    se comparan porcentajes."""
    mes = dia[:7]
    primero = _dia(mes + "-01")
    mes_antes = (primero - timedelta(days=1)).isoformat()[:7]
    por_mes = defaultdict(list)
    for r in registros(con):
        if r["dia"] <= dia and (not lugar or r["lugar"] == lugar):
            por_mes[r["dia"][:7]].append(r)
    indicadores = [SIN_NOVEDAD] + INDICADORES[1:]

    def cifras(filas_):
        n = len(filas_)
        c = {"chequeos": n, "personas": len({r["persona"] for r in filas_}),
             "dias": len({r["dia"] for r in filas_})}
        for clave, _, cuenta, _ in indicadores:
            c[clave] = sum(1 for r in filas_ if cuenta(r))
            c[clave + "_pct"] = _pct(c[clave], n)
        return c

    ahora, antes = cifras(por_mes.get(mes, [])), cifras(por_mes.get(mes_antes, []))
    tarjetas = []
    for clave, titulo, _, malo in indicadores:
        dif = round(ahora[clave + "_pct"] - antes[clave + "_pct"], 1) if antes["chequeos"] else None
        tarjetas.append({"clave": clave, "titulo": titulo, "valor": ahora[clave], "pct": ahora[clave + "_pct"],
                         "pct_antes": antes[clave + "_pct"], "dif": dif,
                         "estado": None if not dif else ("peor" if (dif > 0) == malo else "mejor")})
    historia = [{"mes": m, **cifras(por_mes[m])} for m in sorted(por_mes)[-meses_atras:]]
    for t in tarjetas:
        t["serie"] = [(h["mes"], h[t["clave"] + "_pct"], h[t["clave"]], h["chequeos"]) for h in historia]
    del_lugar = defaultdict(list)
    for r in por_mes.get(mes, []):
        del_lugar[r["lugar"]].append(r)
    lugares = sorted(({"lugar": k, **cifras(v)} for k, v in del_lugar.items()), key=lambda x: -x["chequeos"])
    ahora["por_dia"] = round(ahora["chequeos"] / ahora["dias"], 1) if ahora["dias"] else 0
    return {"mes": mes, "mes_antes": mes_antes, "ahora": ahora, "antes": antes, "tarjetas": tarjetas,
            "historia": historia, "lugares": lugares, "columnas": [(c, t) for c, t, _, _ in indicadores]}


def tablero(con, hasta, lugar=""):
    """Cifras para el tablero histórico de toda la planta (o de un lugar). 'hasta' es el último día con datos."""
    base = registros(con)
    todas = [r for r in base if r["dia"] <= hasta and (not lugar or r["lugar"] == lugar)]

    meses = defaultdict(Counter)
    for r in todas:
        mes = meses[r["dia"][:7]]
        mes["chequeos"] += 1
        for clave, _, cuenta, _ in [SIN_NOVEDAD] + INDICADORES[1:]:
            mes[clave] += cuenta(r)
    por_mes = [{"mes": m, **meses[m]} for m in sorted(meses)][-13:]

    desde90, desde30, desde84 = _restar(hasta, 90), _restar(hasta, 30), _restar(hasta, 84)
    top = {t: Counter() for t, _ in CATEGORIAS}
    lugares, responsables, semanas = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    recurrentes = defaultdict(lambda: {"dias": set(), "claves": Counter(), "nombre": ""})
    incumplen = defaultdict(lambda: Counter(nombre=""))
    for r in todas:
        if r["dia"] > desde84:
            semana = semanas[_semana(r["dia"])]
            semana["chequeos"] += 1
            for grupo, claves in GRUPOS.items():
                if any(_es_salud(n) and n["clave"] in claves for n in r["novedades"]):
                    semana[grupo] += 1
        if r["dia"] <= desde90:
            continue
        con_salud = any(_es_salud(n) for n in r["novedades"])
        lugares[r["lugar"]]["chequeos"] += 1
        lugares[r["lugar"]]["salud"] += con_salud
        lugares[r["lugar"]]["bpm"] += any(n["tipo"] == "bpm" for n in r["novedades"])
        lugares[r["lugar"]]["epp"] += any(n["tipo"] == "epp" for n in r["novedades"])
        quien = r["responsable"] or "Sin dato"
        responsables[quien]["chequeos"] += 1
        responsables[quien]["con_novedad"] += bool(r["novedades"])
        responsables[quien]["salud"] += con_salud
        for n in r["novedades"]:
            if n["clave"] != "embarazo":
                top[n["tipo"]][n["etiqueta"]] += 1
        if r["dia"] > desde30:
            for n in r["novedades"]:
                if _es_salud(n):
                    p = recurrentes[r["persona"]]
                    p["dias"].add(r["dia"]); p["claves"][n["etiqueta"]] += 1; p["nombre"] = r["nombre"]
            tipos = {n["tipo"] for n in r["novedades"]} & {"bpm", "epp", "dotacion"}
            if tipos:
                p = incumplen[r["persona"]]
                p["nombre"] = r["nombre"]
                for t in tipos:
                    p[t] += 1

    personas = sorted(({"persona": k, "nombre": v["nombre"], "dias": len(v["dias"]),
                        "ultimo": max(v["dias"]), "sintomas": ", ".join(f"{e} ({c})" for e, c in v["claves"].most_common(3))}
                       for k, v in recurrentes.items() if len(v["dias"]) >= 2),
                      key=lambda p: (-p["dias"], p["nombre"]))
    reincidentes = sorted(({"persona": k, "nombre": v["nombre"], "bpm": v["bpm"], "epp": v["epp"],
                            "dotacion": v["dotacion"], "total": v["bpm"] + v["epp"] + v["dotacion"]}
                           for k, v in incumplen.items()), key=lambda p: (-p["total"], p["nombre"]))
    return {
        "kpis": _kpis(todas, hasta),
        "por_mes": por_mes,
        "semanas": [{"semana": s, **semanas[s]} for s in sorted(semanas)],
        "grupos": list(GRUPOS),
        "sintomas": (top["eta"] + top["salud"] + top["lesion"]).most_common(10),
        "bpm": top["bpm"].most_common(10),
        "epp": top["epp"].most_common(10),
        "dotacion": top["dotacion"].most_common(10),
        "lugares": sorted(({"lugar": k, **v} for k, v in lugares.items()), key=lambda x: -x["chequeos"]),
        "responsables": sorted(({"responsable": k, **v} for k, v in responsables.items()), key=lambda x: -x["chequeos"]),
        "recurrentes": personas[:20],
        "reincidentes": [p for p in reincidentes if p["total"] >= 2][:20],
        "lista_lugares": base.lugares,
        "lista_personas": base.personas,
    }


def buscar_personas(con, texto):
    """[(clave, nombre)] de las personas cuyo nombre contiene todas las palabras escritas (sin tildes ni
    mayúsculas ni numeración). Si el texto coincide exacto con una persona, solo esa."""
    from .reglas import clave_persona
    buscado = clave_persona(texto)
    if not buscado:
        return []
    nombres = {}
    for r in registros(con):
        nombres[r["persona"]] = max(nombres.get(r["persona"], ""), r["nombre"])
    if buscado in nombres:
        return [(buscado, nombres[buscado])]
    palabras = buscado.split()
    return sorted(((k, v) for k, v in nombres.items() if all(p in k for p in palabras)), key=lambda x: x[1])


def ficha_persona(con, clave, hasta):
    """Todo lo de una persona: indicadores, cuántas veces y en qué fechas tuvo cada novedad, por categoría."""
    filas_ = [r for r in registros(con) if r["persona"] == clave and r["dia"] <= hasta]
    if not filas_:
        return None
    dias = sorted({r["dia"] for r in filas_})
    con_novedad = [r for r in filas_ if r["novedades"]]
    detalle = {t: defaultdict(set) for t, _ in CATEGORIAS}
    for r in filas_:
        for n in r["novedades"]:
            detalle[n["tipo"]][n["etiqueta"]].add(r["dia"])
    categorias = []
    for tipo, titulo in CATEGORIAS:
        items = sorted(({"etiqueta": e, "veces": len(ds), "ultima": max(ds), "fechas": sorted(ds, reverse=True)}
                        for e, ds in detalle[tipo].items()), key=lambda x: (-x["veces"], x["etiqueta"]))
        dias_tipo = {d for i in items for d in i["fechas"]}
        categorias.append({"tipo": tipo, "titulo": titulo, "items": items, "dias": len(dias_tipo),
                           "ultima": max(dias_tipo) if dias_tipo else ""})
    meses = defaultdict(Counter)
    for r in filas_:
        mes = meses[r["dia"][:7]]
        mes["chequeos"] += 1
        for t in {n["tipo"] for n in r["novedades"]}:
            mes[t] += 1
    desde30, desde90 = _restar(hasta, 30), _restar(hasta, 90)
    dias_salud = lambda desde: len({r["dia"] for r in filas_ if r["dia"] > desde
                                    and any(_es_salud(n) for n in r["novedades"])})
    return {
        "nombre": max(r["nombre"] for r in filas_),
        "clave": clave,
        "chequeos": len(filas_),
        "primero": dias[0], "ultimo": dias[-1],
        "chequeos_30": sum(1 for r in filas_ if r["dia"] > desde30),
        "sin_novedad_pct": round(100 * (len(filas_) - len(con_novedad)) / len(filas_)),
        "dias_salud_30": dias_salud(desde30), "dias_salud_90": dias_salud(desde90), "dias_salud_total": dias_salud(""),
        "lugares": Counter(r["lugar"] for r in filas_).most_common(),
        "responsables": Counter(r["responsable"] or "Sin dato" for r in filas_).most_common(3),
        "categorias": categorias,
        "por_mes": [{"mes": m, **meses[m]} for m in sorted(meses)][-13:],
        "historial": list(reversed(con_novedad)),
        "observaciones": [r for r in reversed(filas_) if r["observacion"]][:15],
    }


def tabla(con, desde, hasta, lugar="", persona="", tipo="", texto="", limite=None, desplazamiento=0):
    """Respuestas filtradas para la pestaña Datos. tipo: '' todas, 'con' con alguna novedad, o un tipo de novedad.
    Devuelve (filas, total), de la más reciente a la más antigua. Las filas son copias: se pueden modificar."""
    texto = texto.lower()
    elegidas = [r for r in reversed(registros(con))
                if desde <= r["dia"] <= hasta and (not lugar or r["lugar"] == lugar)
                and (not persona or r["persona"] == persona)
                and (tipo != "con" or r["novedades"])
                and (tipo in ("", "con") or any(n["tipo"] == tipo for n in r["novedades"]))
                and (not texto or texto in (r["observacion"] or "").lower())]
    pagina = elegidas[desplazamiento:desplazamiento + limite] if limite else elegidas
    return [dict(r) for r in pagina], len(elegidas)
