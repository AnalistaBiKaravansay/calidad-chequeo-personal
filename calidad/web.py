"""Página web: reporte del día, tablero histórico, tabla de datos, historial por persona y guía.

En la nube (CALIDAD_NUBE=1) no lee Excel: los datos los sube el PC puente a la base. Si hay CALIDAD_CLAVE,
pide esa clave compartida para entrar.
"""
import csv
import hashlib
import hmac
import io
import time
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analisis, config, datos, diario, guia, ia, reglas, reporte

ESTATICOS = Path(__file__).parent / "static"
# Cambia cuando cambian el estilo o el logo: el navegador los guarda un año y los vuelve a pedir solo entonces.
VERSION_ESTATICOS = hashlib.sha1(b"".join(p.read_bytes() for p in sorted(ESTATICOS.iterdir()) if p.is_file())
                                 ).hexdigest()[:8]

app = FastAPI(title="Calidad Karavansay", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")
app.add_middleware(GZipMiddleware, minimum_size=800)   # las páginas viajan comprimidas (unas 5 veces menos)
_ultima_sincronizacion = 0.0

COOKIE = "calidad_sesion"
DURACION_SESION = 30 * 24 * 3600   # 30 días


def _firma(texto):
    # La firma depende de la clave: si se cambia la clave, todas las sesiones abiertas se cierran.
    secreto = hashlib.sha256(("calidad|" + config.clave_pagina()).encode()).digest()
    return hmac.new(secreto, texto.encode(), hashlib.sha256).hexdigest()


def _sesion_valida(valor):
    try:
        expira, firma = valor.split(".", 1)
        return int(expira) > time.time() and hmac.compare_digest(firma, _firma(expira))
    except (AttributeError, ValueError):
        return False


@app.middleware("http")
async def exigir_clave(request: Request, siguiente):
    """Sin CALIDAD_CLAVE (uso local) no se pide nada. Con clave, todo menos /login y /static exige sesión."""
    ruta = request.url.path
    if ruta.startswith("/static"):
        respuesta = await siguiente(request)
        respuesta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return respuesta
    if (not config.clave_pagina() or ruta in ("/login", "/salud")
            or _sesion_valida(request.cookies.get(COOKIE, ""))):
        return await siguiente(request)
    volver = ruta + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/login?volver={quote(volver)}", status_code=303)


@app.get("/login")
def ver_login(request: Request, volver: str = "/", error: str = ""):
    return pagina("login.html", request, volver=volver, error=error)


@app.post("/login")
def entrar(clave: str = Form(...), volver: str = Form("/")):
    destino = volver if volver.startswith("/") and not volver.startswith("//") else "/"
    if not hmac.compare_digest(clave.encode(), config.clave_pagina().encode()):
        time.sleep(1)   # frena los intentos de adivinar la clave
        return RedirectResponse(f"/login?volver={quote(destino)}&error=1", status_code=303)
    expira = str(int(time.time()) + DURACION_SESION)
    respuesta = RedirectResponse(destino, status_code=303)
    respuesta.set_cookie(COOKIE, f"{expira}.{_firma(expira)}", max_age=DURACION_SESION, httponly=True,
                         samesite="lax", secure=config.en_nube())
    return respuesta


@app.get("/salir")
def salir():
    respuesta = RedirectResponse("/login", status_code=303)
    respuesta.delete_cookie(COOKIE)
    return respuesta


@app.get("/salud")
def salud():
    """Para que Render compruebe que la página está viva (no toca la base)."""
    return {"ok": True}


def conexion():
    """Abre la base. En el PC relee los Excel como máximo cada 2 minutos; en la nube no hay Excel que leer."""
    global _ultima_sincronizacion
    con = datos.conectar()
    if not config.en_nube() and time.time() - _ultima_sincronizacion > 120:
        datos.sincronizar(con)
        _ultima_sincronizacion = time.time()
    return con


def pagina(plantilla, request, **contexto):
    html = reporte.plantillas.get_template(plantilla).render(request=request, pagina=plantilla, V=VERSION_ESTATICOS,
                                                             NUBE=config.en_nube(), **contexto)
    # Datos de salud: el navegador no debe guardar copias de la página.
    return HTMLResponse(html, headers={"Cache-Control": "private, no-store"})


def _ultimo_dia(con):
    return datos.registros(con).ultima[:10] or date.today().isoformat()


@app.get("/")
def hoy(request: Request, dia: str = "", mensaje: str = ""):
    with closing(conexion()) as con:
        dias = datos.registros(con).dias
        hoy_ = date.today().isoformat()
        dia = dia or (hoy_ if hoy_ in dias else (dias[-1] if dias else hoy_))
        previos, siguientes = [d for d in dias if d < dia], [d for d in dias if d > dia]
        contexto = reporte.construir(con, dia, consultar_ia=False)
        enviado = con.execute("SELECT enviado FROM envios WHERE dia=?", (dia,)).fetchone()
        valoraciones = ia.valoraciones_del_dia(con, dia)
    return pagina("hoy.html", request, web=True, valoraciones=valoraciones, anterior=previos[-1] if previos else "",
                  siguiente=siguientes[0] if siguientes else "", enviado=enviado[0] if enviado else "",
                  mensaje=mensaje, **contexto)


@app.post("/ia")
def pedir_ia(dia: str = Form(...)):
    with closing(conexion()) as con:
        estado = reporte.construir(con, dia)["ia"]["estado"]
    return RedirectResponse(f"/?dia={dia}&mensaje=Consejos de IA: {estado}", status_code=303)


@app.post("/valorar")
def valorar(dia: str = Form(...), respuesta_id: int = Form(...), consejo: str = Form(...),
            voto: Optional[int] = Form(None), correccion: Optional[str] = Form(None)):
    """Guarda la marca de Calidad sobre un consejo de la IA (se usará como ejemplo en las próximas consultas)."""
    with closing(datos.conectar()) as con:
        ia.guardar_valoracion(con, respuesta_id, consejo, voto if voto in (1, -1) else None, correccion)
    return RedirectResponse(f"/?dia={dia}#r{respuesta_id}", status_code=303)


@app.post("/enviar")
def enviar(dia: str = Form(...)):
    with closing(conexion()) as con:
        try:
            mensaje = diario.enviar_reporte(con, dia, config.cargar(), forzar=True)
        except RuntimeError as e:
            mensaje = str(e)
    return RedirectResponse(f"/?dia={dia}&mensaje={mensaje}", status_code=303)


@app.get("/tablero")
def tablero(request: Request, lugar: str = "", persona: str = ""):
    persona = persona.strip()
    clave = reglas.clave_persona(persona) if persona else ""
    with closing(conexion()) as con:
        hasta = _ultimo_dia(con)
        cifras = analisis.tablero(con, hasta, lugar, clave)
    return pagina("tablero.html", request, hasta=hasta, lugar=lugar, persona=persona, persona_clave=clave, **cifras)


@app.get("/persona/{clave}")
def persona(request: Request, clave: str):
    with closing(conexion()) as con:
        registros, conteo = analisis.persona(con, clave)
    return pagina("persona.html", request, registros=registros, conteo=conteo,
                  nombre=registros[0]["nombre"] if registros else clave)


@app.post("/recargar")
def recargar(volver: str = Form("/")):
    """En el PC relee los Excel en el momento. En la nube muestra lo último que subió el PC puente."""
    global _ultima_sincronizacion
    with closing(datos.conectar()) as con:
        if config.en_nube():
            mensaje = (f"Datos al día según la última subida del PC puente "
                       f"({datos.ultima_sincronizacion(con)[:16].replace('T', ' ')}). "
                       f"Última respuesta: {datos.ultima_respuesta(con)[:16]}.")
        else:
            antes = con.execute("SELECT count(*) FROM respuestas").fetchone()[0]
            estado = datos.sincronizar(con)
            _ultima_sincronizacion = time.time()
            nuevas = con.execute("SELECT count(*) FROM respuestas").fetchone()[0] - antes
            errores = [f"{f['fuente']}: {f['error']}" for f in estado if not f["ok"]]
            mensaje = (f"Datos actualizados: {nuevas} respuesta(s) nueva(s). "
                       f"Última respuesta: {datos.ultima_respuesta(con)[:16]}."
                       + (" Problemas: " + "; ".join(errores) if errores else ""))
    partes = urlsplit(volver if volver.startswith("/") else "/")   # solo rutas internas
    consulta = [(k, v) for k, v in parse_qsl(partes.query) if k != "mensaje"] + [("mensaje", mensaje)]
    return RedirectResponse(f"{partes.path}?{urlencode(consulta)}", status_code=303)


POR_PAGINA = 100


def _filtros_datos(con, desde, hasta, lugar, persona, tipo, texto):
    hasta = hasta or _ultimo_dia(con)
    desde = desde or (date.fromisoformat(hasta) - timedelta(days=6)).isoformat()
    clave = reglas.clave_persona(persona) if persona.strip() else ""
    return dict(desde=desde, hasta=hasta, lugar=lugar, persona=clave, tipo=tipo, texto=texto.strip())


@app.get("/datos")
def ver_datos(request: Request, desde: str = "", hasta: str = "", lugar: str = "", persona: str = "",
              tipo: str = "", texto: str = "", completa: int = 0, pagina_num: int = 1):
    with closing(conexion()) as con:
        f = _filtros_datos(con, desde, hasta, lugar, persona, tipo, texto)
        pagina_num = max(1, pagina_num)
        registros, total = analisis.tabla(con, **f, limite=POR_PAGINA, desplazamiento=(pagina_num - 1) * POR_PAGINA)
        todos = datos.registros(con)
        lugares, personas = todos.lugares, todos.personas
        # La fila completa del Excel solo se pide a la base si se marcó "todas las columnas", y solo de esta página.
        completos = datos.crudos(con, [r["id"] for r in registros]) if completa and registros else {}
    columnas = list(next(iter(completos.values())).keys()) if completos else []
    for r in registros:
        r["crudo"] = completos.get(r["id"], {})
    consulta = {k: v for k, v in dict(request.query_params).items() if k != "pagina_num"}
    return pagina("datos.html", request, registros=registros, total=total, pagina_num=pagina_num,
                  paginas=max(1, -(-total // POR_PAGINA)), columnas=columnas, completa=completa,
                  lugares=lugares, personas=personas, persona_texto=persona, consulta=urlencode(consulta),
                  tipos=[("", "Todas las respuestas"), ("con", "Con alguna novedad")]
                        + [(t, reporte.NOMBRE_TIPO[t]) for t in reglas.PRIORIDAD], **f)


@app.get("/datos.csv")
def descargar_datos(desde: str = "", hasta: str = "", lugar: str = "", persona: str = "", tipo: str = "",
                    texto: str = "", completa: int = 0):
    with closing(conexion()) as con:
        f = _filtros_datos(con, desde, hasta, lugar, persona, tipo, texto)
        registros, _ = analisis.tabla(con, **f)
        completos = datos.crudos(con, [r["id"] for r in registros]) if completa and registros else {}
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")   # punto y coma: así lo abre bien Excel en español
    columnas = list(next(iter(completos.values())).keys()) if completos else []
    escritor.writerow(["Id", "Fecha", "Persona", "Lugar", "Revisó", "Novedades", "Observación"] + columnas)
    for r in registros:
        crudo = completos.get(r["id"], {})
        escritor.writerow([r["id"], r["fecha"], r["nombre"], r["lugar"], r["responsable"],
                           " | ".join(n["etiqueta"] for n in r["novedades"]), r["observacion"]]
                          + [crudo.get(c, "") for c in columnas])
    nombre = f"chequeos_{f['desde']}_a_{f['hasta']}.csv"
    return Response(salida.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@app.get("/guia")
def ver_guia(request: Request):
    with closing(conexion()) as con:
        limites = dict(analisis.umbrales(con, _ultimo_dia(con)))
        aprendizaje = ia.resumen_aprendizaje(con)
    return pagina("guia.html", request, g=guia, r=reglas, limites=limites, aprendizaje=aprendizaje,
                  minimos=(analisis.MINIMO_SEGUIMIENTO, analisis.MINIMO_MEDICO))
