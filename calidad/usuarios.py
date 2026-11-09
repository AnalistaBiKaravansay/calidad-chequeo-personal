"""Usuarios y perfiles de la página.

Cada usuario tiene un perfil; el perfil dice qué secciones puede ver. Las claves se guardan cifradas con
PBKDF2 (nunca en texto). El usuario 'admin' es el único con el perfil Administrador fijo y no se puede borrar.

Para ahorrar consultas, la lista de usuarios y perfiles se guarda en memoria y se relee cada 60 segundos o
cuando se cambia algo desde la pantalla de administración.
"""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from contextlib import closing
from datetime import datetime

# Secciones que un perfil puede tener. El orden es el del menú.
PERMISOS = {
    "hoy": "Reporte del día",
    "tablero": "Tablero",
    "datos": "Datos y descarga a Excel",
    "guia": "Guía",
    "acciones": "Pedir consejos a la IA, marcar consejos y enviar el correo",
    "admin": "Administración de usuarios y perfiles",
}
# Permisos que se pueden dar a un perfil. 'admin' no está: Administración la ve solo el usuario admin.
ASIGNABLES = {k: v for k, v in PERMISOS.items() if k != "admin"}
ADMIN = "admin"
PERFIL_ADMIN = "Administrador"
ITERACIONES = 240_000
USUARIO_VALIDO = re.compile(r"^[a-z0-9._-]{3,40}$")

_memoria = {"hasta": 0.0, "usuarios": {}, "perfiles": {}}
_candado = threading.Lock()


# ---------- claves ----------

def cifrar(clave):
    sal = secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, ITERACIONES)
    return f"pbkdf2${ITERACIONES}${sal.hex()}${resumen.hex()}"


def clave_correcta(clave, guardada):
    try:
        _, iteraciones, sal, resumen = guardada.split("$")
        calculado = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), int(iteraciones))
        return hmac.compare_digest(calculado.hex(), resumen)
    except (AttributeError, ValueError):
        return False


def problema_clave(clave):
    """Devuelve el motivo si la clave es débil; vacío si sirve."""
    if len(clave) < 8:
        return "La clave debe tener al menos 8 caracteres."
    if clave.isalpha() or clave.isdigit():
        return "La clave debe combinar letras con números o símbolos."
    return ""


# ---------- lectura (con memoria) ----------

def olvidar():
    _memoria["hasta"] = 0.0


def _cargar(con=None):
    """con=None: abre la base solo si la memoria ya venció (la mayoría de páginas no hacen ninguna consulta)."""
    from . import config
    base = config.url_bd() or str(config.carpeta_datos() / "calidad.db")
    with _candado:
        if time.time() < _memoria["hasta"] and _memoria.get("base") == base:
            return _memoria
        _memoria["base"] = base
        if con is None:
            from . import datos
            with closing(datos.conectar()) as propia:
                return _leer(propia)
        return _leer(con)


def _leer(con):
    perfiles = {f["nombre"]: set(filter(None, f["permisos"].split(",")))
                for f in con.execute("SELECT nombre, permisos FROM perfiles")}
    usuarios = {f["usuario"]: dict(f) for f in con.execute(
        "SELECT usuario, nombre, perfil, clave, activo, creado, ultimo_ingreso FROM usuarios")}
    _memoria.update(usuarios=usuarios, perfiles=perfiles, hasta=time.time() + 60)
    return _memoria


def hay_usuarios(con=None):
    return bool(_cargar(con)["usuarios"])


def buscar(con, usuario):
    return _cargar(con)["usuarios"].get((usuario or "").strip().lower())


def permisos(con, usuario):
    """Secciones que puede ver el usuario (vacío si no existe o está desactivado)."""
    u = buscar(con, usuario)
    if not u or not u["activo"]:
        return set()
    if u["usuario"] == ADMIN:
        return set(PERMISOS)   # el admin siempre lo ve todo, aunque alguien edite su perfil
    return _cargar(con)["perfiles"].get(u["perfil"], set()) & set(ASIGNABLES)


def sello(u):
    """Cambia si cambia la clave o se desactiva el usuario: así se cierran sus sesiones abiertas."""
    return (u["clave"][-16:] + str(u["activo"])) if u else ""


def lista(con):
    m = _cargar(con)
    usuarios = sorted(m["usuarios"].values(), key=lambda u: (u["usuario"] != ADMIN, u["usuario"]))
    perfiles = [{"nombre": n, "permisos": p, "usuarios": sum(u["perfil"] == n for u in usuarios)}
                for n, p in sorted(m["perfiles"].items(), key=lambda x: (x[0] != PERFIL_ADMIN, x[0]))]
    return [{k: v for k, v in u.items() if k != "clave"} for u in usuarios], perfiles


# ---------- cambios (desde la pantalla de administración) ----------

def _ahora():
    return datetime.now().isoformat(timespec="seconds")


def crear_usuario(con, usuario, nombre, perfil, clave):
    usuario = usuario.strip().lower()
    if not USUARIO_VALIDO.match(usuario):
        raise ValueError("El usuario debe tener de 3 a 40 letras minúsculas, números, punto, guion o guion bajo, "
                         "sin espacios ni tildes.")
    if buscar(con, usuario):
        raise ValueError(f"Ya existe el usuario {usuario}.")
    if perfil not in _cargar(con)["perfiles"]:
        raise ValueError("Elija un perfil existente.")
    if problema_clave(clave):
        raise ValueError(problema_clave(clave))
    with con:
        con.execute("INSERT INTO usuarios(usuario, nombre, perfil, clave, activo, creado) VALUES (?,?,?,?,1,?)",
                    (usuario, nombre.strip() or usuario, perfil, cifrar(clave), _ahora()))
    olvidar()


def editar_usuario(con, usuario, nombre, perfil, activo, clave=""):
    u = buscar(con, usuario)
    if not u:
        raise ValueError("Ese usuario no existe.")
    if u["usuario"] == ADMIN:
        perfil, activo = PERFIL_ADMIN, 1   # el admin no se puede desactivar ni quitar de su perfil
    if perfil not in _cargar(con)["perfiles"]:
        raise ValueError("Elija un perfil existente.")
    if clave and problema_clave(clave):
        raise ValueError(problema_clave(clave))
    with con:
        con.execute("UPDATE usuarios SET nombre=?, perfil=?, activo=? WHERE usuario=?",
                    (nombre.strip() or u["usuario"], perfil, 1 if activo else 0, u["usuario"]))
        if clave:
            con.execute("UPDATE usuarios SET clave=? WHERE usuario=?", (cifrar(clave), u["usuario"]))
    olvidar()


def borrar_usuario(con, usuario):
    if (usuario or "").strip().lower() == ADMIN:
        raise ValueError("El usuario admin no se puede borrar.")
    with con:
        con.execute("DELETE FROM usuarios WHERE usuario=?", (usuario.strip().lower(),))
    olvidar()


def guardar_perfil(con, nombre, elegidos, nuevo=False):
    nombre = " ".join(nombre.split())
    if not nombre or len(nombre) > 40:
        raise ValueError("Escriba un nombre de perfil (máximo 40 caracteres).")
    if nombre == PERFIL_ADMIN:
        raise ValueError("El perfil Administrador no se puede modificar: siempre tiene todos los permisos.")
    existe = nombre in _cargar(con)["perfiles"]
    if nuevo and existe:
        raise ValueError(f"Ya existe el perfil {nombre}.")
    permisos_ = ",".join(p for p in ASIGNABLES if p in set(elegidos))
    with con:
        if existe:
            con.execute("UPDATE perfiles SET permisos=? WHERE nombre=?", (permisos_, nombre))
        else:
            con.execute("INSERT INTO perfiles(nombre, permisos) VALUES (?,?)", (nombre, permisos_))
    olvidar()


def borrar_perfil(con, nombre):
    if nombre == PERFIL_ADMIN:
        raise ValueError("El perfil Administrador no se puede borrar.")
    if any(u["perfil"] == nombre for u in _cargar(con)["usuarios"].values()):
        raise ValueError(f"El perfil {nombre} tiene usuarios. Cámbielos de perfil antes de borrarlo.")
    with con:
        con.execute("DELETE FROM perfiles WHERE nombre=?", (nombre,))
    olvidar()


def registrar_ingreso(con, usuario):
    with con:
        con.execute("UPDATE usuarios SET ultimo_ingreso=? WHERE usuario=?", (_ahora(), usuario))
    u = buscar(con, usuario)
    if u:
        u["ultimo_ingreso"] = _ahora()


def asegurar_admin(con, clave):
    """Crea el usuario admin si no existe (o le pone esta clave si ya existe)."""
    if problema_clave(clave):
        raise ValueError(problema_clave(clave))
    with con:
        if con.execute("SELECT 1 FROM usuarios WHERE usuario=?", (ADMIN,)).fetchone():
            con.execute("UPDATE usuarios SET clave=?, perfil=?, activo=1 WHERE usuario=?",
                        (cifrar(clave), PERFIL_ADMIN, ADMIN))
        else:
            con.execute("INSERT INTO usuarios(usuario, nombre, perfil, clave, activo, creado) VALUES (?,?,?,?,1,?)",
                        (ADMIN, "Administrador", PERFIL_ADMIN, cifrar(clave), _ahora()))
    olvidar()


def admin_desde_entorno(con):
    """En Render: si se configuró CALIDAD_ADMIN_CLAVE y todavía no hay admin, lo crea al arrancar."""
    clave = os.environ.get("CALIDAD_ADMIN_CLAVE", "").strip()
    if clave and not buscar(con, ADMIN):
        asegurar_admin(con, clave)
