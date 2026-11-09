# Chequeo diario de personal · Calidad (versión en la nube)

Misma herramienta que `PROYECTO-CALIDAD` (reporte del día, tablero, datos, guía, consejos de IA con 👍/👎), publicada en internet con usuario y clave para que Calidad la use desde cualquier lugar.

## Cómo funciona

```
Forms → Power Automate → "Respuestas Forms (flujo).xlsx" en OneDrive
                                   │
                         PC puente (este equipo)
   cada 30 min, de 5:00 a 12:00: sube lo nuevo y pide los consejos de IA de los casos nuevos
                    11:00 (lun-sáb): reporte por correo
                                   │
                 Base de datos en la nube: Neon (PostgreSQL)
                                   │
          Página en la nube: Render (usuario y clave)  ←  Calidad
```

- **El PC puente lee el Excel** del flujo y **escribe en la base de la nube**. Solo sube respuestas nuevas o modificadas.
- **Consejos de IA automáticos:** si en una pasada llegaron respuestas nuevas, el puente pide en ese momento los consejos para los casos nuevos (sin botón). En la página, **Pedir consejos a la IA** queda solo como respaldo si una consulta falló.
- **La página en Render solo lee la base** y guarda las marcas 👍/👎. No lee Excel ni envía correos.
- **Si el PC puente está apagado**, la página sigue funcionando con lo que ya subió, pero no entran respuestas nuevas, no se piden consejos automáticos y no sale el correo de las 11:00 hasta que se encienda. Respuestas que lleguen después de las 12:00 se suben al día siguiente a las 5:00 (o al pulsar Recargar en la versión del PC).
- **Para no depender del PC:** que TI habilite Microsoft Graph (la página leería el Excel directamente) o dejar el puente en un equipo que siempre esté encendido con OneDrive sincronizando.

> **Antes de compartir el enlace:** la página guarda datos de salud del personal (datos sensibles, Ley 1581) en servidores de Neon y Render fuera de Colombia. Se necesita la autorización de la empresa.

## Tablero y ficha por persona

- **Tablero general:** indicadores de los últimos 30 días frente a los 30 anteriores (chequeos y personas, alertas ETA, síntomas o lesión, BPM, EPP, dotación), síntomas por semana, lo más reportado en 90 días (síntomas, criterios BPM, EPP, dotación), quién repite síntomas y quién reincide en BPM/EPP/dotación, cifras por lugar y por responsable del chequeo, y la evolución mes a mes. Al pasar el mouse por una barra se ve el valor exacto.
- **Ficha de persona:** en el buscador del tablero se escribe el nombre **o una parte** ("dayana", "gonzalez"); si coinciden varias personas, se elige de la lista. La ficha muestra chequeos, último chequeo, % sin novedad, días con síntomas (30, 90 y total), y por cada categoría (ETA, síntomas, lesiones, por revisar, BPM, EPP, dotación) **cuántas veces y en qué fechas** tuvo cada novedad (cada fecha abre el reporte de ese día), el mes a mes, las últimas observaciones y el historial completo. Los nombres del reporte y de Datos llevan a esta ficha.
- **Nombres numerados:** el formulario a veces escribe "12. Dayana Salcedo". La numeración se quita al guardar, así que cada persona aparece una sola vez y sus síntomas repetidos se cuentan juntos (antes 238 nombres, ahora 138). Si un nombre se escribe muy distinto (otra ortografía), sigue apareciendo por separado.

## Usuarios, perfiles y Administración

Se entra con **usuario y clave**. Cada usuario tiene un **perfil**, y el perfil dice qué secciones ve; el menú solo muestra esas.

- **Administración** (menú superior): crear, editar, desactivar o borrar usuarios, cambiarles la clave, y crear o editar perfiles marcando sus secciones. **Solo la ve el usuario `admin`**, y ese permiso no se puede dar a ningún perfil.
- **Perfiles iniciales:**

  | Perfil | Ve |
  |---|---|
  | Administrador | Todo (fijo, no se edita) |
  | Calidad | Reporte del día, Tablero, Datos y descarga, Guía, y las acciones (pedir IA, marcar 👍/👎, enviar correo) |
  | Consulta | Reporte del día, Tablero, Guía (sin acciones) |

- El usuario `admin` no se puede borrar ni desactivar. Su clave la tiene Calidad; para cambiarla: Administración → Editar, o `python -m calidad crear-admin`.
- **Desactivar** un usuario (desmarcar *Activo*) le quita el acceso de inmediato y conserva el registro; **cambiarle la clave** cierra sus sesiones abiertas.
- Las claves se guardan cifradas (PBKDF2), nunca en texto. Usuario: minúsculas sin espacios ni tildes (ej. `maria.gomez`). Clave: mínimo 8 caracteres, con letras y números o símbolos.
- La sesión dura 30 días en el mismo navegador. Si alguien entra a una sección que no está en su perfil, ve un aviso y un botón a sus secciones.
- En este PC, si la base no tuviera ningún usuario, la página abre sin clave (pero sin Administración). Con la base de Neon ya hay usuarios, así que siempre pide entrar.

## Ahorro de espacio, consultas y uso de IA

El plan gratuito de Neon limita el espacio (unos 500 MB) y las horas que la base pasa despierta. Por eso:

| Qué | Cómo |
|---|---|
| **Espacio** | La fila completa del Excel se guarda como lista de valores; los nombres de las 33 columnas, una sola vez (tabla `columnas`). La base pasó de 35 MB a 18 MB. |
| **Horas de Neon** | El puente revisa en el PC si el Excel cambió (tamaño y fecha, guardados en `firmas.json`). Si no cambió, **no se conecta**, y la base sigue dormida. |
| **Consultas de la página** | La página guarda en memoria las respuestas (sin la fila completa) y solo las vuelve a pedir cuando cambian los datos. Cada página hace unas pocas consultas pequeñas. La fila completa del Excel se pide solo en Datos con "Todas las columnas", y solo de la página que se ve. |
| **Velocidad** | Render y Neon en la misma zona (AWS US East / Virginia). Páginas comprimidas (gzip); el estilo y el logo quedan guardados en el navegador. |
| **IA** | Cada caso se identifica por su contenido: si llegan casos nuevos, **solo esos** se envían; los ya respondidos se conservan. De la guía solo va la parte que aplica a esos casos. Nunca se envían nombres. |

## Puesta en marcha

### 1. Base de datos (Neon) — hecho
```
.venv\Scripts\python.exe -m calidad clave-bd      (guarda la dirección de Neon sin mostrarla)
.venv\Scripts\python.exe -m calidad probar-bd
.venv\Scripts\python.exe -m calidad subir         (copia la versión local; se puede repetir sin duplicar)
```

### 2. Código en GitHub — hecho
Repositorio **privado** `AnalistaBiKaravansay/calidad-chequeo-personal`. El `.gitignore` deja por fuera los Excel, las bases y las claves.

### 3. Página (Render)
1. Crear una cuenta gratuita en <https://render.com> con **Sign in with GitHub**.
2. **New → Blueprint** → elegir el repositorio. Render lee `render.yaml` (región Virginia, plan gratuito).
3. Escribir los dos valores secretos:
   - `DATABASE_URL`: la cadena de conexión de Neon (está en `%USERPROFILE%\CalidadKaravansayNube\bd_nube.txt`).
   - `GEMINI_API_KEY`: la clave de Gemini (`clave_gemini.txt` en la misma carpeta).

   `CALIDAD_SECRETO` (firma de las sesiones) lo inventa Render solo. Los usuarios están en la base: el usuario `admin` ya está creado en Neon, así que no hay que poner ninguna clave de la página en Render.
4. Al terminar, Render da el enlace (`https://….onrender.com`).

En el plan gratuito, Render apaga la página tras 15 minutos sin uso; la primera visita después tarda cerca de un minuto en abrir. No se pierde nada: los datos están en Neon.

### 4. PC puente
Abrir **Configuracion\PROGRAMAR_ENVIO_DIARIO.cmd** y pulsar Enter (11:00). Crea dos tareas de Windows:
- **Calidad NUBE - subir datos:** cada 30 minutos, de 5:00 a 12:00. Sube lo nuevo y pide los consejos de IA de los casos nuevos.
- **Calidad NUBE - reporte diario:** de lunes a sábado a las 11:00. Envía el correo con los consejos ya guardados.

Las tareas corren también con el portátil en batería y, si el equipo estaba apagado a la hora, se ejecutan apenas se encienda. El detalle de cada ejecución queda en `%USERPROFILE%\CalidadKaravansayNube\registro.txt`.

**Si dejan de entrar respuestas:** revisar `registro.txt`. Si no tiene líneas recientes, la tarea no está arrancando: en el Programador de tareas de Windows, ver el "Resultado de la última ejecución" de *Calidad NUBE - subir datos* (0x800710E0 = Windows la rechazó por estar en batería; se arregla volviendo a ejecutar `PROGRAMAR_ENVIO_DIARIO.cmd`). Para subir en el momento: doble clic en `Configuracion\SUBIR_DATOS.cmd`.

## Comandos
| Comando | Qué hace |
|---|---|
| `python -m calidad sincronizar [--ia] [--todo]` | Sube lo nuevo. `--ia`: consejos para los casos nuevos de hoy. `--todo`: relee todo y recalcula novedades. |
| `python -m calidad diario [--enviar]` | Reporte del día (y correo). |
| `python -m calidad web [--abrir]` | Página en este PC (puerto 8766), con la misma base de la nube. |
| `python -m calidad clave-bd` / `clave-ia` | Guarda la dirección de Neon / la clave de Gemini en este PC. |
| `python -m calidad probar-bd` | Comprueba la conexión. |
| `python -m calidad subir` | Copia la base de la versión local a la nube. |
| `python -m calidad crear-admin` | Crea el usuario `admin` o le cambia la clave (la pide sin mostrarla). |
| `python -m calidad compactar` | Pasa respuestas en formato antiguo al compacto, quita la numeración de los nombres y libera el espacio. |

## Archivos y datos privados
- Datos privados del PC puente: `%USERPROFILE%\CalidadKaravansayNube` (`bd_nube.txt`, `clave_gemini.txt`, `secreto_sesion.txt`, `firmas.json`, reportes, `registro.txt`). No están en la carpeta de red ni en GitHub.
- **ABRIR_TABLERO.cmd** abre esta versión en el PC (puerto 8766), conectada a la misma base de la nube.
- La versión local (`PROYECTO-CALIDAD`, puerto 8765) sigue funcionando sola y no se modifica.

## Para el desarrollador
```
Configuracion\INSTALAR.cmd                       (instala requirements-dev.txt: lo del servidor + pytest)
.venv\Scripts\python.exe -m pytest -q tests
```
`requirements.txt` es solo lo que necesita el servidor (Render); `requirements-dev.txt` agrega las pruebas.

| Archivo | Qué hace |
|---|---|
| `calidad/bd.py` | Conexión: PostgreSQL si hay `DATABASE_URL` o `bd_nube.txt`; si no, SQLite local |
| `calidad/datos.py` | Lee los Excel, sube solo lo nuevo, formato compacto, firmas locales y memoria de respuestas (`registros`) |
| `calidad/analisis.py` | Novedades del día, historial, alertas, tablero (`tablero`), búsqueda y ficha de persona (`buscar_personas`, `ficha_persona`), calculados sobre la memoria |
| `calidad/reglas.py` | Detección de novedades; `limpiar_nombre` quita la numeración de los nombres |
| `calidad/ia.py` | Consejos de Gemini por caso (solo los casos nuevos), marcas 👍/👎 |
| `calidad/guia.py` | Pasos de la guía; `texto_para_ia()` envía solo la parte que aplica |
| `calidad/web.py` | Página; inicio de sesión y permiso por sección (`PERMISO_DE_RUTA`), Administración (`/admin`); modo nube con `CALIDAD_NUBE=1`; gzip y caché |
| `calidad/usuarios.py` | Usuarios y perfiles: claves cifradas, permisos, lista en memoria (se relee cada minuto o al cambiar algo) |
| `calidad/templates`, `calidad/static` | Diseño con la paleta de Karavansay (igual que Capacitaciones) y el logo. `_graficas.html`: barras en HTML/CSS; `_ficha.html`: ficha de persona |
| `render.yaml` | Configuración de Render |

Las reglas de detección (`reglas.py`) y la guía son las mismas de la versión local; ver el README de `PROYECTO-CALIDAD`.
