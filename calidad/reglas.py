"""Convierte cada respuesta del Forms en una lista de novedades.

Tipos de novedad (de mayor a menor prioridad):
  eta       -> síntoma de alerta de posible ETA marcado SI en el formulario (protocolo de exclusión)
  salud     -> otro síntoma a vigilar (gripa, dolor de cabeza, cólicos...)
  lesion    -> herida, golpe o cortada sin signos de infección
  revisar   -> observación escrita que las reglas no reconocen (la lee la IA y Calidad)
  bpm       -> criterio BPM marcado "No cumple"
  dotacion  -> uniforme, botas, gorro... en mal estado o faltante
  epp       -> elemento de protección marcado "NO"
"""
import re
import unicodedata

PRIORIDAD = {"eta": 0, "salud": 1, "lesion": 2, "revisar": 3, "bpm": 4, "dotacion": 5, "epp": 6}

ETIQUETAS = {
    "ictericia": "Ictericia (ojos y piel amarilla)",
    "vomito": "Vómito",
    "fiebre_garganta": "Fiebre + dolor de garganta",
    "herida_infectada": "Herida infectada",
    "diarrea": "Diarrea",
    "respiratorio": "Síntomas respiratorios / gripa",
    "garganta": "Dolor de garganta (sin fiebre reportada)",
    "fiebre": "Fiebre",
    "digestivo": "Malestar digestivo (cólicos, dolor de estómago, náuseas)",
    "dolor_cabeza": "Dolor de cabeza",
    "malestar": "Malestar general, mareo o escalofrío",
    "dolor_muscular": "Dolor muscular, articular u otro",
    "ojos": "Molestia en los ojos",
    "piel": "Afección de la piel o manos",
    "incapacidad": "Incapacidad o recuperación médica mencionada",
    "otros_sintomas": "Otros síntomas mencionados",
    "bpm:unas_obs": "Uñas largas o sin limar (observación)",
    "bpm:afeitar_obs": "Sin afeitar (observación)",
    "revisar": "Observación por revisar",
    "elementos": "Gafas o guantes dañados o faltantes",
    "embarazo": "Embarazo mencionado",
    "lesion": "Herida, golpe o cortada",
    "uniforme": "Uniforme (roto, sin marcar, sucio)",
    "botas": "Botas / calzado",
    "gorro": "Gorro o cofia",
    "peto": "Peto",
}

# Pregunta cerrada de salud -> clave (se busca por palabra dentro del encabezado).
PREGUNTAS_SALUD = [("icter", "ictericia"), ("vomito", "vomito"), ("fiebre", "fiebre_garganta"),
                   ("herida", "herida_infectada"), ("diarrea", "diarrea")]

# Palabras en OBSERVACIONES (texto ya sin tildes y en minúscula).
PALABRAS = [
    ("eta", "diarrea", r"diarrea|soltura|deposicion"),
    ("eta", "vomito", r"vomit"),
    ("eta", "ictericia", r"icteri|(?:piel|ojos) amarill"),
    ("eta", "herida_infectada", r"infectad|\bpus\b|supura|purulent"),
    ("salud", "fiebre", r"fiebre|febril|temperatura alta"),
    ("salud", "garganta", r"garganta|afonic|ronquera|faring|amigdal"),
    ("salud", "respiratorio", r"grip|\btos\b|congesti|flema|resfri|moco|estornud|rinitis|sinusitis|nasal"),
    ("salud", "digestivo", r"colico|estomag|estomacal|nausea|gastritis|gastroenter|indigest|acidez|abdom|reflujo"),
    ("salud", "dolor_cabeza", r"dolor de cabeza|cefalea|migran|jaqueca"),
    ("salud", "malestar", r"malestar|mareo|escalofri|fatiga|cansancio|desaliento|hormigueo|calambre|dormid"),
    # Cualquier otro dolor; se descarta si la misma frase ya es cabeza, garganta, estómago u ojos.
    ("salud", "dolor_muscular", r"\bdolor|\bduele|molestia|inflamad|hinchaz|esguince|lumbago|torticolis|espasmo"),
    ("salud", "ojos", r"ojos? (?:rojo|irritad)|conjuntiv|molestia en (?:el |los )?ojo"),
    ("salud", "piel", r"alergia|ronchas|sarpullido|brotes?\b|dermatitis|hongo|irritacion en la piel|reseque|mezquino|mes quino|verruga|pican?\b|manchas rojas|pela"),
    ("salud", "incapacidad", r"incapacid|incapacit|cirugia"),
    ("salud", "otros_sintomas", r"sintoma|cistitis|sistitis"),
    ("salud", "embarazo", r"embaraz|gestacion"),
    ("lesion", "lesion", r"herida|cortad|\bcorte\b|machuc|golpe|quemad|lesion|lastim|resbal|\bcura\b|curita|vendaje|venda\b|raspon|ampolla|fractura|caida"),
    ("bpm", "bpm:unas_obs", r"\bunas\b"),
    ("bpm", "bpm:afeitar_obs", r"afeit"),
    ("dotacion", "uniforme", r"uniforme|uniorme|u informe|\bbata\b|dotacion|percudid|descos|descoc|pantalon|overol|camisa|chaqueta|bolsillo|cremallera|\broto\b|\brota\b|sin marcar"),
    ("dotacion", "botas", r"\bbotas?\b|bostas|calzado|calazado|zapato"),
    ("dotacion", "gorro", r"gorro|cofia|malla"),
    ("dotacion", "peto", r"\bpeto\b|\bpero roto"),
    ("dotacion", "elementos", r"gafas|\blente|guantes?"),
]
SALUD_ESPECIFICA = {"garganta", "digestivo", "dolor_cabeza", "ojos", "piel"}

# Versión legible de PALABRAS para la pestaña Guía. Si se cambia un patrón, actualizar aquí también.
EJEMPLOS = {
    "diarrea": "diarrea, soltura, deposición",
    "vomito": "vómito, vomitó, vomitando",
    "ictericia": "ictericia, piel amarilla, ojos amarillos",
    "herida_infectada": "infectada, pus, supura, purulenta",
    "fiebre": "fiebre, febril, temperatura alta",
    "garganta": "garganta, afónica, ronquera, faringitis, amigdalitis",
    "respiratorio": "gripa, gripe, tos, congestión, flema, resfriado, moco, estornudo, rinitis, sinusitis, nasal",
    "digestivo": "cólico, estómago, estomacal, náuseas, gastritis, gastroenteritis, indigestión, acidez, abdomen, "
                 "reflujo",
    "dolor_cabeza": "dolor de cabeza, cefalea, migraña, jaqueca",
    "malestar": "malestar, mareo, escalofrío, fatiga, cansancio, desaliento, hormigueo, calambre, dormido",
    "dolor_muscular": "dolor, duele, molestia, inflamado, hinchazón, esguince, lumbago, tortícolis, espasmo "
                      "(si no es de cabeza, garganta, estómago, ojos o piel)",
    "ojos": "ojos rojos o irritados, conjuntivitis, molestia en el ojo",
    "piel": "alergia, ronchas, sarpullido, brotes, dermatitis, hongos, resequedad, mezquino, verruga, pica, "
            "manchas rojas, se pela",
    "incapacidad": "incapacidad, incapacitada, cirugía",
    "otros_sintomas": "síntoma(s), cistitis",
    "embarazo": "embarazo, gestación",
    "lesion": "herida, cortada, corte, machucón, golpe, quemadura, lesión, se lastimó, resbaló, cura, curita, "
              "vendaje, raspón, ampolla, fractura, caída",
    "bpm:unas_obs": "uñas",
    "bpm:afeitar_obs": "afeitar, no se afeita",
    "uniforme": "uniforme, bata, dotación, roto, rota, descosido, sin marcar, percudido, pantalón, overol, camisa, "
                "chaqueta, bolsillo, cremallera",
    "botas": "botas, calzado, zapatos",
    "gorro": "gorro, cofia, malla",
    "peto": "peto",
    "elementos": "gafas, lentes, guantes",
}
TIPO_OBSERVACION = {"eta": "Mencionado: verificar si es alerta ETA", "salud": "Salud", "lesion": "Lesión",
                    "bpm": "BPM", "dotacion": "Dotación"}

# "no presenta tos", "sin fiebre", "niega diarrea": la mención está negada.
NEGACION = re.compile(r"\b(?:no presenta|no tiene|no reporta|no refiere|sin|niega|ni)\s+(?:\w+\s+){0,2}$")
# Observaciones que dicen explícitamente que no hay novedad: no se mandan a revisar.
SIN_NOVEDAD = re.compile(r"\b(?:no presenta|no reporta|no refiere|niega|sin novedad|sin observacion|ninguna?|"
                         r"todo (?:bien|ok|normal)|cumple)\b")


def normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# El formulario a veces numera los nombres ("12. Dayana Salcedo", "7.Candelaria Morales"): la numeración se quita
# para que la misma persona no aparezca dos veces (y no se partan sus repeticiones de síntomas).
NUMERACION = re.compile(r"^\s*\d+\s*[.\-)_:]*\s*")


def limpiar_nombre(nombre):
    return " ".join(NUMERACION.sub("", str(nombre or "")).split())


def clave_persona(nombre):
    return re.sub(r"\s+", " ", normalizar(limpiar_nombre(nombre))).strip()


def _limpio(valor):
    return "" if valor is None else str(valor).strip()


def analizar_observacion(texto):
    """Novedades encontradas en el texto libre."""
    encontradas = {}
    for frase in re.split(r"[.,;\n]| y ", normalizar(texto)):
        en_frase = {}
        for tipo, clave, patron in PALABRAS:
            m = re.search(patron, frase)
            if not m:
                continue
            negada = NEGACION.search(frase[:m.start()])
            # "no tiene botas" sí es novedad de dotación; en salud la negación la anula.
            if negada and tipo in ("eta", "salud"):
                continue
            en_frase[clave] = tipo
        if "dolor_muscular" in en_frase and SALUD_ESPECIFICA & en_frase.keys():
            del en_frase["dolor_muscular"]
        if "otros_sintomas" in en_frase and len([t for t in en_frase.values() if t in ("eta", "salud")]) > 1:
            del en_frase["otros_sintomas"]
        for clave, tipo in en_frase.items():
            encontradas.setdefault(clave, tipo)
    return encontradas


def novedades(fila):
    """fila: dict encabezado -> valor. Devuelve lista de novedades ordenada por prioridad."""
    lista = {}

    def agregar(tipo, clave, origen, etiqueta=None):
        if clave in lista:
            lista[clave]["origen"] = "pregunta y observación"
            return
        lista[clave] = {"tipo": tipo, "clave": clave, "etiqueta": etiqueta or ETIQUETAS.get(clave, clave), "origen": origen}

    usa_gafas = False
    for encabezado, valor in fila.items():
        h, v = normalizar(encabezado), _limpio(valor).upper()
        if h.startswith("criterios estado de salud.") and v in ("SI", "SÍ"):
            for palabra, clave in PREGUNTAS_SALUD:
                if palabra in h:
                    agregar("eta", clave, "pregunta")
        elif h.startswith("criterios bpm.") and v == "NO CUMPLE":
            criterio = encabezado.split(".", 1)[1].strip()
            agregar("bpm", "bpm:" + criterio, "pregunta", criterio)
        elif h.startswith("criterios epp") and v == "NO":
            elemento = encabezado.split(".", 1)[1].strip()
            agregar("epp", "epp:" + elemento, "pregunta", "No usa: " + elemento)
        elif h == "gafas.usa gafas" and v == "SI":
            usa_gafas = True
    if usa_gafas:
        for encabezado, valor in fila.items():
            h, v = normalizar(encabezado), _limpio(valor).upper()
            if h.startswith("gafas.tiene cordon") and v == "NO":
                agregar("epp", "epp:gafas_cordon", "pregunta", "Gafas sin cordón")
            elif h.startswith("gafas.las gafas se encuentran") and v == "NO":
                agregar("epp", "epp:gafas_estado", "pregunta", "Gafas en mal estado")

    observacion = next((v for k, v in fila.items() if normalizar(k) == "observaciones"), "")
    en_observacion = analizar_observacion(observacion)
    if not en_observacion and len(_limpio(observacion)) >= 6 and not SIN_NOVEDAD.search(normalizar(observacion)):
        agregar("revisar", "revisar", "observación")
    for clave, tipo in en_observacion.items():
        if clave == "herida_infectada":
            lista.pop("lesion", None)
        if clave == "lesion" and "herida_infectada" in lista:
            continue
        agregar(tipo, clave, "observación")

    # Procedimiento interno: el vómito por embarazo no es alerta de posible ETA.
    if "embarazo" in lista and "vomito" in lista:
        lista["vomito"]["tipo"] = "salud"
        lista["vomito"]["nota"] = "Asociado a embarazo: según el procedimiento interno no es alerta de ETA."
    if "fiebre" in lista and "garganta" in lista:
        lista.pop("fiebre"); lista.pop("garganta")
        agregar("eta", "fiebre_garganta", "observación")
    # La alerta ETA la da la pregunta del formulario (que trae el criterio, p. ej. más de 3 deposiciones).
    # Si el síntoma solo está escrito en la observación, queda como mención por verificar.
    for n in lista.values():
        if n["tipo"] == "eta" and n["origen"] == "observación":
            n["tipo"] = "salud"
            n["etiqueta"] = "Mencionado: " + n["etiqueta"]
            n["nota"] = "La pregunta de salud no se marcó SI: verificar si cumple el criterio de alerta de ETA."

    return sorted(lista.values(), key=lambda n: (PRIORIDAD[n["tipo"]], n["etiqueta"]))
