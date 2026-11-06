# Guía de pasos a seguir · Estado de salud y prácticas del personal manipulador

Guía que usa la herramienta de chequeo diario para orientar a Calidad. **No es un diagnóstico ni reemplaza la valoración médica ni la de SST.** El texto que usa el sistema está en `calidad/guia.py`; este documento explica de dónde sale cada paso.

## Fuentes

| Código | Documento | Copia |
|---|---|---|
| [PI] | Procedimiento interno de Calidad: síntomas de alerta de posible ETA | (tabla interna) |
| [R2674] | Ministerio de Salud y Protección Social, **Resolución 2674 de 2013**, arts. 11, 12, 13 y 14 | `fuentes/MinSalud - Resolucion 2674 de 2013.pdf` |
| [INVIMA] | INVIMA, **Circular Externa DAB 400-1396-17**: orientación técnica para la verificación de situaciones que pueden indicar enfermedad y/o evidencias de lesiones en manipuladores de alimentos | `fuentes/INVIMA - Circular Externa DAB 400-1396-17.pdf` |
| [FDA] | U.S. FDA, **Food Code 2022**, §2-201.11, §2-201.12 y §2-201.13 (el "Código Federal" que cita el procedimiento interno) | `fuentes/FDA - Food Code 2022.pdf` (pp. 50-59) |
| [CODEX] | Codex Alimentarius (FAO/OMS), **CXC 1-1969 Principios generales de higiene de los alimentos**, rev. 2022, sección 12 "Higiene personal" | `fuentes/Codex - CXC 1-1969 ….pdf` (pp. 18-19) |
| [INS] | Instituto Nacional de Salud, **Protocolo de vigilancia de brotes de ETA**, código 349, versión 4 (14/09/2022) | `fuentes/INS - Protocolo 349 ….pdf` |

### Documentos revisados que no aplican al chequeo de personal
| Documento | Por qué no se incluye |
|---|---|
| Decreto 1500 de 2007 | Solo aplica a plantas de beneficio, desposte, desprese y derivados cárnicos. Se incluiría si la planta procesa carne. |
| Resoluciones 5109 de 2005 y 2492 de 2022 | Etiquetado y rotulado nutricional: no tratan del personal. |
| Guía de verificación de BPM farmacéutica (OPS/OMS) | Es para la industria farmacéutica. |
| Lineamientos para certificados BPM del INVIMA | Son requisitos del trámite de certificación, no de la verificación diaria del personal. |
| Actas de inspección sanitaria con enfoque de riesgo del INVIMA (Res. 2015048290 de 2015) | Aplican, pero el bloque de personal verifica los mismos requisitos de la Res. 2674 (arts. 11-14) que ya están en esta guía. No se encontró una versión pública en texto para citarla. |

## 1. Síntomas de alerta de posible ETA [PI]

| Síntoma | Explicación | Acción | Reintegro |
|---|---|---|---|
| Ictericia | Ojos y piel amarilla | Exclusión del área de producción | Orden médica o 24 horas asintomático |
| Vómito | Vómito repetido que impida la ingesta de líquidos o alimentos | Exclusión del área de producción | Orden médica o 24 horas asintomático |
| Dolor de garganta y fiebre | Ambos síntomas juntos | Exclusión del área de producción | Orden médica o 24 horas asintomático |
| Herida infectada | Evidencia de infección | Exclusión del área de producción | Orden médica o 24 horas asintomático |
| Diarrea | Más de 3 deposiciones en menos de 24 horas | Exclusión del área de producción | Orden médica o 24 horas asintomático |

El vómito por embarazo no es riesgoso ni es una alerta de posible ETA [PI].

### Pasos que da la herramienta

1. **Retirar a la persona del área de producción.**
   - [R2674] art. 11 num. 5: *"La empresa es responsable de tomar las medidas necesarias para que no se permita contaminar los alimentos directa o indirectamente por una persona que se sepa o sospeche que padezca de una enfermedad susceptible de transmitirse por los alimentos (…) o que presente heridas infectadas, irritaciones cutáneas infectadas o diarrea."*
   - Art. 14 num. 12: *"El personal que presente afecciones de la piel o enfermedad infectocontagiosa debe ser excluido de toda actividad directa de manipulación de alimentos."*
2. **Registrar e informar a Calidad y SST.** La Circular [INVIMA] indica que los manipuladores con síntomas *"deberán informar de inmediato al responsable para que se valore la necesidad de someter a la persona a examen médico y/o suspenderlo de la zona de manipulación"*. [FDA] §2-201.11(A) pide registrar la fecha de inicio de los síntomas.
3. **Remitir a valoración médica.** [R2674] art. 11 num. 2 y 3: reconocimiento médico *"cada vez que se considere necesario por razones clínicas y epidemiológicas"*, con certificado de aptitud o no para manipular alimentos.
4. **Reintegrar con orden médica o tras 24 h sin síntomas** [PI]. El establecimiento *"debe llevar el control y seguimiento al manipulador cuando ha superado su enfermedad y deba reincorporarse"* [INVIMA]. Si hubo tratamiento, el médico expide el certificado de aptitud al finalizar [R2674 art. 11 num. 4].
5. **Varias personas con síntomas parecidos:** avisar a Calidad como posible brote. El [INS] define brote de ETA como un *"episodio en el cual dos o más personas presentan una enfermedad similar después de ingerir alimentos, incluida el agua, del mismo origen"* (Tabla 1). La investigación epidemiológica de campo se hace *"dentro de las primeras 24 horas siguientes a la notificación del brote"*, con informes a las 24 horas, a las 72 horas y uno final (máximo 6 semanas). Durante la investigación *"se deberán recolectar muestras biológicas (…) a los manipuladores de alimentos"* (7.3). Por eso conviene tener a mano el registro de chequeos y seguimientos de la herramienta.

### Lo que añade el Codex Alimentarius [CODEX 12.1-12.4]
- **12.1 Estado de salud:** quien padece o porta una enfermedad que probablemente se transmita por alimentos *"no debería ingresar a ninguna área de manipulación de alimentos"* y *"debería comunicar inmediatamente a la dirección la enfermedad o los síntomas"*.
- **12.2 Síntomas que se deben comunicar** para valorar exclusión o examen médico: ictericia, diarrea, vómitos, **fiebre**, dolor de garganta y fiebre, lesiones cutáneas visiblemente infectadas, y **secreción de los oídos, ojos o nariz**. Los cortes y heridas se cubren con *"apósitos adecuados resistentes al agua"*, de un color que contraste con el alimento; si es necesario, se asigna a la persona una zona sin contacto directo con alimentos.
- **12.3 Limpieza personal:** lavado de manos al empezar, al volver de descansos, después de usar el baño y después de manipular material contaminado. El desinfectante de manos no reemplaza el lavado.
- **12.4 Conducta personal:** no fumar ni vapear, no escupir, no comer ni beber en las zonas de manipulación. No llevar joyas, relojes, alfileres, *"uñas o pestañas postizas"*.

La herramienta usa el punto 12.2 para los pasos de "otros síntomas" y de "lesiones", y el 12.4 para el criterio de pestañas postizas.

### Diferencias entre el procedimiento interno y el FDA Food Code (para revisar el procedimiento)

| Síntoma | Procedimiento interno | FDA Food Code 2022 |
|---|---|---|
| Vómito / diarrea | Orden médica o 24 h asintomático | Igual: 24 h asintomático o documento médico que indique causa no infecciosa (§2-201.13(A)(1)) |
| Ictericia | Orden médica o 24 h asintomático | Excluir si empezó en los últimos 7 días; reintegrar con aprobación de la autoridad y documento médico que descarte hepatitis A, o más de 7 días con ictericia (§2-201.12(B), §2-201.13(B)) |
| Fiebre + dolor de garganta | Orden médica o 24 h asintomático | Restricción (exclusión si atiende población muy susceptible); reintegro solo con documento médico: más de 24 h de antibiótico para estreptococo, cultivo negativo u otra determinación médica (§2-201.12(H), §2-201.13(H)) |
| Herida infectada | Exclusión | Restricción: puede volver si la herida está bien cubierta (mano/muñeca: protección impermeable + guante desechable; brazo: protección impermeable; otra zona: vendaje seco y ajustado) (§2-201.12(I), §2-201.13(I)) |

**Sugerencia:** para **ictericia** y **fiebre + dolor de garganta**, el criterio de "24 horas asintomático" es más flexible que la fuente que cita el propio procedimiento. Conviene que Calidad/SST evalúe exigir **siempre orden médica** para esos dos síntomas.

## 2. Otros síntomas (gripa, dolor de cabeza, cólicos, dolor muscular…)

1. Preguntar si además tiene fiebre, vómito, diarrea, ictericia o una herida infectada. Si es así, aplicar el punto 1 [PI].
2. Dar el **consejo inmediato** del síntoma (tabla en la pestaña Guía y en `calidad/guia.py`). Por ejemplo, para gripa: tapabocas bien puesto, lavado de manos y, si hay mucha secreción, una tarea sin contacto directo con alimentos [R2674 art. 14 num. 4 y 6] [CODEX 12.2-12.4]. Para dolor muscular: pausa activa, revisar postura y carga, rotar de tarea.
3. **Escalera según cuánto se repite**, comparando con lo normal en la planta (último año):
   - **Consejo inmediato:** lo habitual.
   - **Seguimiento:** más días que 3 de cada 4 casos de ese síntoma (mínimo 3 días en 30). Hablar con la persona; si es dolor muscular o lesión, SST revisa el puesto.
   - **Sugerir cita con la EPS:** más días que 9 de cada 10 casos (mínimo 5 días en 30) [R2674 art. 11 num. 2]. Se sugiere el día en que se cruza el límite; los días siguientes se pide confirmar si pidió la cita o si está en tratamiento.

   Con los datos de octubre de 2026, por ejemplo: la gripa pasa a seguimiento a los 5 días y a cita a los 9; el dolor muscular, a los 9 y a los 15.

El motivo de la escalera: en una planta de manufactura, remitir al médico cada síntoma repetido no es práctico ni lo exige la norma. La Res. 2674 pide reconocimiento médico *"cada vez que se considere necesario por razones clínicas y epidemiológicas"* (art. 11 num. 2), y la escalera marca justamente cuándo un caso se sale de lo normal.

## 3. Heridas, golpes o cortadas sin infección

1. Revisar signos de infección (pus, supuración, enrojecimiento, calor). Si los hay, aplicar el punto 1.
2. Cubrir bien la lesión [FDA §2-201.11(A)(1)(e)].
3. Si ocurrió en el trabajo, informar a SST (incidente o accidente laboral).

## 4. BPM, dotación y EPP [R2674 art. 14]

| Criterio | Requisito | Numeral |
|---|---|---|
| Uniforme | Color claro, cierres en lugar de botones, sin bolsillos sobre la cintura; la empresa entrega dotación suficiente | num. 2 |
| No salir con la vestimenta | No salir ni ingresar al establecimiento con la vestimenta de trabajo | num. 3 |
| Cofia / gorro | Cabello recogido y cubierto totalmente; barba cubierta; sin maquillaje | num. 5 |
| Tapabocas | Cubriendo nariz y boca según el riesgo | num. 6 |
| Uñas | Cortas, limpias y sin esmalte | num. 7 |
| Joyas y gafas | Sin reloj, anillos, aretes ni accesorios; los lentes asegurados a la cabeza | num. 8 |
| Calzado | Cerrado, resistente, impermeable y de tacón bajo | num. 9 |
| Guantes | Limpios, sin roturas; no eximen del lavado de manos | num. 10 |

Incumplimientos repetidos: reforzar la capacitación. [R2674] art. 12 exige un plan de capacitación continuo de **al menos 10 horas anuales**.
