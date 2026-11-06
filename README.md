# Chequeo diario de personal · Calidad (versión en la nube)

Misma herramienta que `PROYECTO-CALIDAD` (reporte del día, tablero, datos, guía, consejos de IA con 👍/👎), publicada en internet con clave compartida para que Calidad la use desde cualquier lugar.

## Cómo funciona

```
Forms → Power Automate → "Respuestas Forms (flujo).xlsx" en OneDrive
                                   │
                         PC puente (este equipo)
         cada 15 min sube las respuestas nuevas · 11:00 reporte con IA
                                   │
                 Base de datos en la nube: Neon (PostgreSQL)
                                   │
          Página en la nube: Render (con clave compartida)  ←  Calidad
```

- **El PC puente lee el Excel** del flujo, como la versión local, y **escribe en la base de la nube**. Solo sube respuestas nuevas o modificadas.
- **La página en Render solo lee la base** y guarda los consejos de IA y las marcas 👍/👎. No lee Excel ni envía correos.
- **Si el PC puente está apagado**, la página sigue funcionando con los datos que ya subió, pero no entran respuestas nuevas hasta que se encienda.
- **Cuando TI habilite Microsoft Graph**, la página podrá leer el Excel directamente y el PC puente dejará de ser necesario.

> **Antes de compartir el enlace:** la página guarda datos de salud del personal (datos sensibles, Ley 1581) en servidores de Neon y Render fuera de Colombia. Se necesita la autorización de la empresa.

## Puesta en marcha

### 1. Base de datos (Neon)
1. Crear una cuenta gratuita en <https://neon.com> y un proyecto (región sugerida: la más cercana, por ejemplo AWS US East).
2. Copiar la **cadena de conexión** (empieza por `postgresql://`). **No pegarla en ningún chat.**
3. En este PC, desde esta carpeta:
   ```
   .venv\Scripts\python.exe -m calidad clave-bd
   .venv\Scripts\python.exe -m calidad probar-bd
   .venv\Scripts\python.exe -m calidad subir
   ```
   `subir` copia a la nube todo lo de la versión local (respuestas, consejos de IA y marcas). Se puede repetir sin duplicar.

### 2. Código en GitHub
Render publica desde un repositorio de GitHub. Crear una cuenta en <https://github.com> y un repositorio **privado**, y subir esta carpeta. El `.gitignore` deja por fuera los Excel, las bases y las claves.

### 3. Página (Render)
1. Crear una cuenta gratuita en <https://render.com> y conectar GitHub.
2. **New → Blueprint** → elegir el repositorio. Render lee `render.yaml`.
3. Escribir los tres valores secretos:
   - `DATABASE_URL`: la cadena de conexión de Neon.
   - `GEMINI_API_KEY`: la clave de Gemini.
   - `CALIDAD_CLAVE`: la clave compartida para entrar a la página.
4. Al terminar, Render da el enlace (`https://….onrender.com`).

En el plan gratuito, Render apaga la página tras 15 minutos sin uso; la primera visita después tarda cerca de un minuto en abrir.

### 4. PC puente
Abrir **Configuracion\PROGRAMAR_ENVIO_DIARIO.cmd** y pulsar Enter (11:00). Crea dos tareas de Windows:
- **Calidad NUBE - subir datos:** cada 15 minutos, de 5:00 a 20:00.
- **Calidad NUBE - reporte diario:** de lunes a sábado a las 11:00 (una sola consulta a la IA).

El detalle de cada ejecución queda en `%USERPROFILE%\CalidadKaravansayNube\registro.txt`.

## Archivos y datos privados
- Datos privados del PC puente: `%USERPROFILE%\CalidadKaravansayNube` (`bd_nube.txt`, `clave_gemini.txt`, reportes). No están en la carpeta de red ni en GitHub.
- **ABRIR_TABLERO.cmd** abre esta versión en el PC (puerto 8766), conectada a la misma base de la nube.
- La versión local (`PROYECTO-CALIDAD`, puerto 8765) sigue funcionando sola y no se modifica.

## Para el desarrollador
```
.venv\Scripts\python.exe -m pytest -q tests
```
| Archivo | Qué hace |
|---|---|
| `calidad/bd.py` | Conexión: PostgreSQL si hay `DATABASE_URL` o `bd_nube.txt`; si no, SQLite local |
| `calidad/datos.py` | Lee los Excel, sube solo lo nuevo o cambiado, y `subir()` copia la base anterior |
| `calidad/web.py` | Página; inicio de sesión con `CALIDAD_CLAVE`; modo nube con `CALIDAD_NUBE=1` |
| `render.yaml` | Configuración de Render |

El resto (reglas, guía, análisis, IA) es igual a la versión local; ver el README de `PROYECTO-CALIDAD`.
