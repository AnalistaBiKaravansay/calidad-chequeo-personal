"""Página web: reporte del día, tablero histórico, tabla de datos, guía y administración de usuarios.

En la nube (CALIDAD_NUBE=1) no lee Excel: los datos los sube el PC puente a la base, o los envía Power
Automate directamente a /api/respuesta (flujo.py). Se entra con usuario y
clave; cada usuario ve solo las secciones de su perfil (usuarios.py).
"""
import asyncio
import csv
import hashlib
import hmac
import io
import time
from contextlib import asynccontextmanager, closing
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analisis, config, datos, diario, flujo, guia, ia, reglas, reporte, usuarios

ESTATICOS = Path(__file__).parent / "static"
# Cambia cuando cambian el estilo o el logo: el navegador los guarda un año y los vuelve a pedir solo entonces.
VERSION_ESTATICOS = hashlib.sha1(b"".join(p.read_bytes() for p in sorted(ESTATICOS.iterdir()) if p.is_file())
                                 ).hexdigest()[:8]

@asynccontextmanager
async def _al_arrancar(_app):
    """En Render: crea el usuario admin la primera vez si se configuró CALIDAD_ADMIN_CLAVE."""
    try:
        with closing(datos.conectar()) as con:
            usuarios.admin_desde_entorno(con)
    except Exception as e:   # la página debe arrancar aunque la base tarde en despertar
        print("No se pudo revisar el usuario admin:", e)
    yield


app = FastAPI(title="Calidad Karavansay", docs_url=None, redoc_url=None, lifespan=_al_arrancar)
app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")
app.add_middleware(GZipMiddleware, minimum_size=800)   # las páginas viajan comprimidas (unas 5 veces menos)
_ultima_sincronizacion = 0.0

COOKIE = "calidad_sesion"
DURACION_SESION = 30 * 24 * 3600   # 30 días
# Qué permiso pide cada ruta (ver usuarios.PERMISOS). Las que no están solo piden haber entrado.
PERMISO_DE_RUTA = {"/": "hoy", "/tablero": "tablero", "/persona": "tablero", "/datos": "datos",
                   "/datos.csv": "datos", "/guia": "guia", "/ia": "acciones", "/valorar": "acciones",
                   "/enviar": "acciones", "/admin": "admin"}
LIBRES = ("/login", "/salud", "/salir", "/api/respuesta")   # /api/respuesta se protege con su propio token
# Orden del menú: (ruta, plantilla, texto, permiso)
MENU = [("/", "hoy.html", "Reporte del día", "hoy"), ("/tablero", "tablero.html", "Tablero", "tablero"),
        ("/datos", "datos.html", "Datos", "datos"), ("/guia", "guia.html", "Guía", "guia"),
        ("/admin", "admin.html", "Administración", "admin")]


def _firma(usuario, expira, sello):
    # Incluye el sello del usuario: si cambia su clave o se desactiva, sus sesiones dejan de valer.
    texto = f"{usuario}|{expira}|{sello}"
    return hmac.new(config.secreto_sesion().encode(), texto.encode(), hashlib.sha256).hexdigest()


def _usuario_de_sesion(valor):
    """Devuelve el usuario si la cookie es válida y el usuario sigue activo; si no, None."""
    try:
        usuario, expira, firma = valor.split(":")
        u = usuarios.buscar(None, usuario)
        if u and u["activo"] and int(expira) > time.time() and hmac.compare_digest(
                firma, _firma(usuario, expira, usuarios.sello(u))):
            return u
    except (AttributeError, ValueError):
        pass
    return None


def _inicio_permitido(permisos):
    return next((ruta for ruta, _, _, p in MENU if p in permisos), "")


@app.middleware("http")
async def exigir_sesion(request: Request, siguiente):
    """Todo menos /login, /salud y /static exige haber entrado con usuario y clave, y el permiso de la sección.
    Solo en el PC sin ningún usuario creado (uso local) se entra sin clave, y aun así sin Administración."""
    ruta = request.url.path
    if ruta.startswith("/static"):
        respuesta = await siguiente(request)
        respuesta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return respuesta
    request.state.usuario, request.state.permisos = None, set()
    if ruta in LIBRES:
        return await siguiente(request)
    u = _usuario_de_sesion(request.cookies.get(COOKIE, ""))
    if u:
        request.state.usuario, request.state.permisos = u, usuarios.permisos(None, u["usuario"])
    elif not config.en_nube() and not usuarios.hay_usuarios():
        request.state.permisos = set(usuarios.PERMISOS) - {"admin"}
    else:
        volver = ruta + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?volver={quote(volver)}", status_code=303)
    necesario = PERMISO_DE_RUTA.get("/" + ruta.split("/")[1] if ruta != "/" else "/")
    if necesario and necesario not in request.state.permisos:
        inicio = _inicio_permitido(request.state.permisos)
        if ruta == "/" and inicio:
            return RedirectResponse(inicio, status_code=303)
        return pagina("sin_permiso.html", request, inicio=inicio, status_code=403)
    return await siguiente(request)


@app.get("/login")
def ver_login(request: Request, volver: str = "/", error: str = ""):
    return pagina("login.html", request, volver=volver, error=error)


@app.post("/login")
def entrar(usuario: str = Form(...), clave: str = Form(...), volver: str = Form("/")):
    destino = volver if volver.startswith("/") and not volver.startswith("//") else "/"
    usuarios.olvidar()   # al entrar se relee la lista: así vale un usuario recién creado o desactivado
    u = usuarios.buscar(None, usuario)
    if not (u and u["activo"] and usuarios.clave_correcta(clave, u["clave"])):
        time.sleep(1)   # frena los intentos de adivinar la clave
        return RedirectResponse(f"/login?volver={quote(destino)}&error=1&usuario={quote(usuario.strip())}",
                                status_code=303)
    with closing(datos.conectar()) as con:
        usuarios.registrar_ingreso(con, u["usuario"])
    expira = str(int(time.time()) + DURACION_SESION)
    respuesta = RedirectResponse(destino, status_code=303)
    respuesta.set_cookie(COOKIE, f"{u['usuario']}:{expira}:{_firma(u['usuario'], expira, usuarios.sello(u))}",
                         max_age=DURACION_SESION, httponly=True, samesite="lax", secure=config.en_nube())
    return respuesta


@app.get("/salir")
def salir():
    respuesta = RedirectResponse("/login", status_code=303)
    respuesta.delete_cookie(COOKIE)
    return respuesta


@app.post("/api/respuesta")
async def respuesta_del_flujo(request: Request, tareas: BackgroundTasks):
    """Power Automate envía aquí cada respuesta del Forms (ver flujo.py). Responde enseguida; los consejos de
    la IA se piden después, para que el flujo no espere."""
    if not flujo.token_valido(request.headers.get("x-token")):
        await asyncio.sleep(1)   # frena los intentos de adivinar el token
        return JSONResponse({"ok": False, "error": "Token inválido o entrada apagada."}, status_code=401)
    try:
        cuerpo = flujo.leer_cuerpo(await request.body(), request.headers)
        resultado, dias_ia = await run_in_threadpool(flujo.recibir, cuerpo)
    except ValueError as e:   # JSON mal formado, falta Id o fecha: el flujo lo marca como fallido
        print("Entrada del flujo rechazada:", e)   # queda en los registros (Logs) de Render
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    if dias_ia:
        tareas.add_task(flujo.consejos_ia, dias_ia)
    return resultado


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


def pagina(plantilla, request, status_code=200, **contexto):
    puede = getattr(request.state, "permisos", set())
    html = reporte.plantillas.get_template(plantilla).render(
        request=request, pagina=plantilla, V=VERSION_ESTATICOS, NUBE=config.en_nube(), puede=puede,
        yo=getattr(request.state, "usuario", None), menu=[m for m in MENU if m[3] in puede], **contexto)
    # Datos de salud: el navegador no debe guardar copias de la página.
    return HTMLResponse(html, status_code=status_code, headers={"Cache-Control": "private, no-store"})


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
    """Tablero de la planta; con 'persona' (nombre completo o parte), la ficha de esa persona."""
    persona = persona.strip()
    with closing(conexion()) as con:
        hasta = _ultimo_dia(con)
        coincidencias = analisis.buscar_personas(con, persona) if persona else []
        ficha = analisis.ficha_persona(con, coincidencias[0][0], hasta) if len(coincidencias) == 1 else None
        cifras = analisis.tablero(con, hasta, lugar)
    return pagina("tablero.html", request, hasta=hasta, lugar=lugar, persona=persona, ficha=ficha,
                  coincidencias=coincidencias, CATEGORIAS=analisis.CATEGORIAS, **cifras)


@app.get("/persona/{clave}")
def persona(clave: str):
    """Enlaces antiguos y del reporte: la ficha de la persona está en el tablero."""
    return RedirectResponse(f"/tablero?persona={quote(clave)}", status_code=303)


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


# ---------- Administración (solo el usuario admin) ----------

def _volver_admin(mensaje, error=False):
    return RedirectResponse(f"/admin?{urlencode({'error' if error else 'mensaje': mensaje})}", status_code=303)


def _cambio_admin(funcion, *args, ok=""):
    """Ejecuta un cambio de usuarios o perfiles y vuelve a la pantalla con el resultado."""
    try:
        with closing(datos.conectar()) as con:
            funcion(con, *args)
    except ValueError as e:
        return _volver_admin(str(e), error=True)
    return _volver_admin(ok)


@app.get("/admin")
def ver_admin(request: Request, error: str = ""):
    with closing(datos.conectar()) as con:
        lista_usuarios, perfiles = usuarios.lista(con)
    return pagina("admin.html", request, usuarios_=lista_usuarios, perfiles=perfiles, error=error,
                  ASIGNABLES=usuarios.ASIGNABLES, ADMIN=usuarios.ADMIN, PERFIL_ADMIN=usuarios.PERFIL_ADMIN)


@app.post("/admin/usuario/nuevo")
def admin_crear_usuario(usuario: str = Form(...), nombre: str = Form(""), perfil: str = Form(...),
                        clave: str = Form(...)):
    return _cambio_admin(usuarios.crear_usuario, usuario, nombre, perfil, clave,
                         ok=f"Usuario {usuario.strip().lower()} creado.")


@app.post("/admin/usuario/editar")
def admin_editar_usuario(usuario: str = Form(...), nombre: str = Form(""), perfil: str = Form(...),
                         activo: int = Form(0), clave: str = Form("")):
    clave = clave if clave.strip() else ""   # vacío = no cambiar la clave
    return _cambio_admin(usuarios.editar_usuario, usuario, nombre, perfil, activo, clave,
                         ok=f"Usuario {usuario} actualizado." + (" Se cambió su clave." if clave else ""))


@app.post("/admin/usuario/borrar")
def admin_borrar_usuario(usuario: str = Form(...)):
    return _cambio_admin(usuarios.borrar_usuario, usuario, ok=f"Usuario {usuario} borrado.")


@app.post("/admin/perfil")
def admin_guardar_perfil(nombre: str = Form(...), nuevo: int = Form(0), permisos: List[str] = Form([])):
    return _cambio_admin(usuarios.guardar_perfil, nombre, permisos, bool(nuevo),
                         ok=f"Perfil {' '.join(nombre.split())} guardado.")


@app.post("/admin/perfil/borrar")
def admin_borrar_perfil(nombre: str = Form(...)):
    return _cambio_admin(usuarios.borrar_perfil, nombre, ok=f"Perfil {nombre} borrado.")
