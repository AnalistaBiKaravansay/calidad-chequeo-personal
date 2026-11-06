"""Guía de pasos a seguir. Es la única base que usan el reporte y la IA.

Fuentes (copias en docs/fuentes):
  [PI]     Procedimiento interno de Calidad (tabla de síntomas de alerta de ETA).
  [R2674]  Ministerio de Salud y Protección Social, Resolución 2674 de 2013, arts. 11, 12 y 14.
  [INVIMA] INVIMA, Circular Externa DAB 400-1396-17 (manipuladores con signos de enfermedad).
  [FDA]    FDA Food Code 2022, secciones 2-201.11, 2-201.12 y 2-201.13 (citado por el procedimiento interno).
  [CODEX]  Codex Alimentarius (FAO/OMS) CXC 1-1969, rev. 2022, sección 12 "Higiene personal".
  [INS]    Instituto Nacional de Salud, Protocolo de vigilancia de brotes de ETA, código 349, versión 4 (2022).
"""

AVISO = ("Estas recomendaciones orientan a Calidad sobre qué hacer y registrar. "
         "No son un diagnóstico ni reemplazan la valoración médica ni la de SST.")

FUENTES = {
    "PI": "Procedimiento interno de Calidad: síntomas de alerta de posible ETA",
    "R2674": "Resolución 2674 de 2013 (MinSalud), arts. 11, 12 y 14",
    "INVIMA": "Circular Externa INVIMA DAB 400-1396-17",
    "FDA": "FDA Food Code 2022, §2-201.11 a §2-201.13",
    "CODEX": "Codex Alimentarius CXC 1-1969 (FAO/OMS), sección 12 Higiene personal",
    "INS": "Instituto Nacional de Salud, Protocolo de vigilancia de brotes de ETA (código 349, v4 2022)",
}

# Tabla del procedimiento interno, con lo que añaden las fuentes oficiales.
ETA = {
    "ictericia": {
        "explicacion": "Ojos y piel amarilla.",
        "nota": "El FDA Food Code (§2-201.12(B) y §2-201.13(B)) es más estricto: excluir si la ictericia empezó en "
                "los últimos 7 días y reintegrar con documento médico que descarte hepatitis A. "
                "Se sugiere exigir siempre orden médica para este síntoma.",
    },
    "vomito": {
        "explicacion": "Vómito repetido que impida la ingesta de líquidos o alimentos.",
        "nota": "El vómito por embarazo no es riesgoso ni es alerta de posible ETA [PI]. "
                "El FDA Food Code también exceptúa los síntomas de origen no infeccioso (§2-201.12(A)).",
    },
    "fiebre_garganta": {
        "explicacion": "Dolor de garganta y fiebre, ambos síntomas juntos.",
        "nota": "El FDA Food Code (§2-201.13(H)) pide documento médico para reintegrar (por ejemplo, más de 24 h "
                "de tratamiento antibiótico o prueba negativa de estreptococo).",
    },
    "herida_infectada": {
        "explicacion": "Evidencia de infección (pus, supuración, enrojecimiento y calor).",
        "nota": "El FDA Food Code (§2-201.13(I)) permite volver a trabajar cuando la herida está bien cubierta: en "
                "mano o muñeca, protección impermeable y guante desechable encima; en brazo, protección impermeable; "
                "en otra parte, vendaje seco y ajustado.",
    },
    "diarrea": {
        "explicacion": "Más de 3 deposiciones en menos de 24 horas.",
        "nota": "Si el reintegro es por 24 h sin síntomas, confirmar con la persona que no ha tenido deposiciones "
                "líquidas en ese tiempo [FDA §2-201.13(A)(1)].",
    },
}

ACCION_ETA = "Exclusión del área de producción."
REINTEGRO_ETA = "Orden médica o 24 horas asintomático."

PASOS_ETA = [
    "Retirar de inmediato a la persona del área de producción: no debe manipular alimentos, empaques ni superficies "
    "en contacto con alimentos [PI] [R2674 art. 11 num. 5 y art. 14 num. 12].",
    "Registrar el caso con la fecha y hora de inicio de los síntomas e informar al responsable de Calidad y a SST "
    "[INVIMA] [FDA §2-201.11(A)] [CODEX 12.1].",
    "Remitir a valoración médica para que se defina su aptitud para manipular alimentos [R2674 art. 11 num. 2 y 3] "
    "[INVIMA].",
    "Reintegrar solo con orden médica o tras 24 horas sin síntomas, y dejar la evidencia en el registro [PI]. "
    "Si hubo incapacidad, pedir el certificado de aptitud al volver [R2674 art. 11 num. 4].",
    "Si otras personas de la misma planta o área tienen síntomas parecidos, avisar a Calidad como posible brote. "
    "Para la autoridad, un brote de ETA son dos o más personas con una enfermedad similar tras consumir alimentos o "
    "agua del mismo origen; la investigación se hace en las primeras 24 horas y puede incluir muestras a los "
    "manipuladores. Tener a mano el registro de chequeos y seguimientos [INS].",
]

PASOS = {
    "salud": [
        "Preguntar si además tiene fiebre, vómito, diarrea, ictericia o una herida infectada. Si es así, aplicar el "
        "protocolo de síntomas de alerta de ETA [PI].",
        "Dar el consejo inmediato de cada caso y registrar el seguimiento. Si la persona está muy afectada, se puede "
        "cambiar de actividad por el día [INVIMA]. La cita médica solo se sugiere cuando el síntoma persiste mucho más "
        "de lo normal en la planta.",
    ],
    "lesion": [
        "Revisar si hay signos de infección (pus, supuración, enrojecimiento, calor). Si los hay, aplicar el protocolo "
        "de herida infectada [PI].",
        "Cubrir bien la lesión: en manos, protección impermeable y guante desechable encima; en otras zonas, vendaje "
        "seco y ajustado [FDA §2-201.11(A)(1)(e)]. El apósito debe ser resistente al agua y de un color que contraste "
        "con el alimento; si es necesario, asignar una tarea sin contacto directo con alimentos [CODEX 12.2].",
        "Si ocurrió en el trabajo, informar a SST para que se registre como incidente o accidente.",
    ],
    "revisar": [
        "Leer la observación y decidir si es un tema de salud, BPM o dotación. Si menciona síntomas, aplicar la "
        "guía correspondiente.",
    ],
    "bpm": [
        "Pedir la corrección antes de ingresar al área y verificar que se cumpla [R2674 art. 14].",
        "Registrar el incumplimiento. Si se repite, reforzar la capacitación de la persona [R2674 art. 12 y 13].",
    ],
    "dotacion": [
        "Gestionar el cambio o reposición de la dotación. La empresa debe entregar vestimenta suficiente, de color "
        "claro y en buen estado [R2674 art. 14 num. 2].",
        "Calzado cerrado, resistente e impermeable; cabello totalmente cubierto [R2674 art. 14 num. 5 y 9].",
    ],
    "epp": [
        "Verificar si el elemento aplica a la tarea que realiza. Si aplica, entregarlo y exigir su uso; si no aplica, "
        "marcar N/A en el formulario.",
        "Si usa gafas, deben estar aseguradas a la cabeza con cordón o banda [R2674 art. 14 num. 8].",
    ],
}

# Consejo inmediato en planta para síntomas que no son alerta ETA (nivel 1 de la escalera).
CONSEJO_INMEDIATO = {
    "respiratorio": [
        "Tapabocas bien puesto, cubriendo nariz y boca; cambiarlo si se humedece [R2674 art. 14 num. 6].",
        "Lavado de manos frecuente, sobre todo después de sonarse; no toser ni estornudar sobre alimentos o "
        "superficies [CODEX 12.3 y 12.4].",
        "Si hay secreción nasal abundante o fiebre, asignar por hoy una tarea sin contacto directo con alimentos "
        "[CODEX 12.2].",
    ],
    "garganta": [
        "Preguntar si tiene fiebre: dolor de garganta con fiebre es alerta de ETA [PI].",
        "Tapabocas bien puesto y lavado de manos frecuente [R2674 art. 14 num. 4 y 6].",
    ],
    "fiebre": [
        "La fiebre se debe comunicar para valorar la exclusión [CODEX 12.2]: si se confirma, retirarla por hoy de "
        "la manipulación directa de alimentos.",
        "Preguntar si además tiene dolor de garganta, vómito o diarrea: serían alerta de ETA [PI].",
    ],
    "dolor_cabeza": [
        "Preguntar si ha tomado agua y comido; ofrecer una pausa corta e hidratación.",
        "Preguntar si tiene fiebre u otros síntomas; si es así, aplicar la guía correspondiente.",
    ],
    "digestivo": [
        "Preguntar si tiene diarrea o vómito: si es así, es alerta de ETA y se aplica el protocolo [PI].",
        "Permitir hidratación y acceso al baño; recordar el lavado de manos después de ir al baño [CODEX 12.3].",
    ],
    "malestar": [
        "Si hay mareo, retirarla de máquinas, escaleras o alturas y darle una pausa sentada con hidratación.",
        "Preguntar si ha comido y si tiene fiebre u otros síntomas. Si no mejora durante el turno, informar a SST.",
    ],
    "dolor_muscular": [
        "Pausa activa y estiramientos; revisar la postura y el peso que está cargando.",
        "Si la tarea lo permite, rotarla por un rato a una labor con menos esfuerzo.",
        "Si el dolor viene de un golpe o una caída en el trabajo, informar a SST como incidente.",
    ],
    "ojos": [
        "No frotarse los ojos; lavarse las manos antes y después de tocarse la cara [CODEX 12.4].",
        "Si hay secreción, asignar una tarea sin contacto directo con alimentos [CODEX 12.2].",
    ],
    "piel": [
        "Revisar si hay signos de infección (pus, enrojecimiento, calor); si los hay, es alerta de herida "
        "infectada [PI].",
        "Si hay resequedad o grietas, usar guante y revisar con SST el tipo de guantes y jabón "
        "[R2674 art. 14 num. 10].",
        "Si ya está en tratamiento, seguir las indicaciones médicas y dejarlo registrado [R2674 art. 11 num. 4].",
    ],
    "incapacidad": [
        "Verificar que tenga la orden médica o el certificado de aptitud para volver a manipular alimentos "
        "[R2674 art. 11 num. 2 y 4].",
    ],
    "otros_sintomas": ["Preguntar qué síntomas tiene y aplicar la guía correspondiente."],
    "embarazo": [
        "El vómito por embarazo no es alerta de ETA [PI]. Permitir pausas e hidratación y coordinar con SST las "
        "tareas adecuadas.",
    ],
    # Síntoma de alerta escrito solo en la observación ("Mencionado: ...").
    "mencion": [
        "Verificar con la persona si cumple el criterio de alerta (ver la tabla de síntomas de ETA). Si lo cumple, "
        "aplicar el protocolo de exclusión [PI].",
    ],
}

NIVELES = {1: "Consejo inmediato", 2: "Seguimiento", 3: "Sugerir cita médica"}
SEGUIMIENTO = ("Se repite más de lo normal en la planta ({veces} días en 30): hablar con la persona, preguntar si "
               "está mejorando y si la tarea influye, y registrar el seguimiento.")
SEGUIMIENTO_PUESTO = " Pedir a SST que revise el puesto de trabajo (postura, cargas, pausas activas)."
CITA_MEDICA = ("Persiste mucho más de lo normal ({veces} días en 30; en la planta, 9 de cada 10 casos de este "
               "síntoma duran menos de {medico} días): sugerir que pida cita con su EPS para descartar una causa de "
               "fondo [R2674 art. 11 num. 2].")
CITA_YA_SENALADA = ("Caso persistente ya señalado ({veces} días en 30): confirmar si pidió la cita con su EPS o si "
                    "ya está en tratamiento, y registrarlo. Si ya tiene indicaciones médicas, seguirlas "
                    "[R2674 art. 11 num. 4].")

PASO_REPETICION = {
    "eta": "Caso repetido: pedir valoración médica (no basta con 24 horas sin síntomas) y documentar las medidas "
           "tomadas [R2674 art. 11 num. 2].",
    "lesion": "Lesiones repetidas: revisar con SST las condiciones del puesto de trabajo.",
    "revisar": "La misma observación se repite: revisar si requiere seguimiento.",
    "bpm": "Incumplimiento repetido: reforzar la capacitación y dejar registro [R2674 art. 12].",
    "dotacion": "Se repite: confirmar si ya se solicitó o entregó la reposición de dotación.",
    "epp": "Se repite: confirmar con SST si el elemento aplica y si fue entregado.",
}

# Recomendaciones según el criterio BPM incumplido.
BPM_ESPECIFICO = {
    # "ropa debajo" va primero porque ese criterio también contiene la palabra "uniforme".
    "ropa debajo": "Ropa debajo del uniforme distinta a la de consumir alimentos; no salir ni ingresar con la "
                   "vestimenta de trabajo [R2674 art. 14 num. 3].",
    "uniforme": "Uniforme limpio, de color claro y en buen estado [R2674 art. 14 num. 2].",
    "calzado": "Calzado cerrado, resistente, impermeable y de tacón bajo [R2674 art. 14 num. 9].",
    "cofia": "Cabello recogido y totalmente cubierto [R2674 art. 14 num. 5].",
    "unas": "Uñas cortas, limpias y sin esmalte [R2674 art. 14 num. 7].",
    "maquillaje": "Sin maquillaje, joyas ni accesorios; barba cubierta [R2674 art. 14 num. 5 y 8].",
    "pestanas": "Sin pestañas ni uñas postizas: son objetos que pueden caer en el alimento [CODEX 12.4] "
                "[R2674 art. 14 num. 1 y 5].",
    "tapabocas": "Tapabocas que cubra nariz y boca; guantes limpios y sin roturas [R2674 art. 14 num. 6 y 10].",
    "otros": "Heridas cubiertas y reporte de enfermedades a la empresa [R2674 art. 11 num. 5].",
}


def pasos_para(novedad, repeticiones=0, nivel=None, limites=None):
    """Pasos para una novedad. Salud y lesiones usan la escalera (nivel 1-3); el resto, la regla de repetición."""
    from .reglas import normalizar
    tipo = novedad["tipo"]
    if tipo in ("salud", "lesion") and nivel:
        clave = "mencion" if novedad["etiqueta"].startswith("Mencionado") else novedad["clave"]
        pasos = list(CONSEJO_INMEDIATO.get(clave, PASOS["lesion"] if tipo == "lesion" else []))
        veces = repeticiones + 1
        if nivel == 2:
            pasos.append(SEGUIMIENTO.format(veces=veces)
                         + (SEGUIMIENTO_PUESTO if clave in ("dolor_muscular", "lesion") else ""))
        elif nivel == 3 and repeticiones >= limites[1]:
            # Ya estaba en nivel 3 en un reporte anterior: no repetir la sugerencia de cita todos los días.
            pasos.append(CITA_YA_SENALADA.format(veces=veces))
        elif nivel == 3:
            pasos.append(CITA_MEDICA.format(veces=veces, medico=limites[1])
                         + (SEGUIMIENTO_PUESTO if clave in ("dolor_muscular", "lesion") else ""))
        return pasos
    pasos = list(PASOS_ETA if tipo == "eta" else PASOS.get(tipo, []))
    if tipo == "bpm":
        criterio = normalizar(novedad["etiqueta"])
        for palabra, texto in BPM_ESPECIFICO.items():
            if palabra in criterio:
                pasos.insert(0, texto)
                break
    if repeticiones >= 2:
        pasos.append(PASO_REPETICION[tipo])
    return pasos


def texto_para_ia():
    """Versión compacta de la guía que se envía a la IA como única base."""
    lineas = ["FUENTES: " + "; ".join(f"[{k}] {v}" for k, v in FUENTES.items()),
              f"SÍNTOMAS DE ALERTA DE POSIBLE ETA [PI]. Acción: {ACCION_ETA} Reintegro: {REINTEGRO_ETA}"]
    for clave, d in ETA.items():
        lineas.append(f"- {clave}: {d['explicacion']} Nota: {d['nota']}")
    lineas.append("PASOS ETA: " + " | ".join(PASOS_ETA))
    for tipo, pasos in PASOS.items():
        lineas.append(f"PASOS {tipo.upper()}: " + " | ".join(pasos))
    for clave, consejos in CONSEJO_INMEDIATO.items():
        lineas.append(f"CONSEJO INMEDIATO {clave}: " + " | ".join(consejos))
    lineas.append("ESCALERA (síntomas no ETA): nivel 1 = consejo inmediato; nivel 2 = seguimiento con la persona "
                  "(y SST si es dolor muscular o lesión); nivel 3 = sugerir cita con la EPS.")
    lineas.append("BPM: " + " | ".join(BPM_ESPECIFICO.values()))
    lineas.append("REPETICIÓN: " + " | ".join(PASO_REPETICION.values()))
    return "\n".join(lineas)
