"""Lectura de config.json, rutas de trabajo y datos privados (claves y dirección de la base)."""
import json
import os
import re
from pathlib import Path

PROYECTO = Path(__file__).resolve().parent.parent


def cargar():
    with open(PROYECTO / "config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("correo_destino", [])
    cfg.setdefault("dias_historial", 30)
    # Modelos gratuitos de Gemini, del mejor al más básico. Se usa el primero que responda.
    cfg.setdefault("ia_modelos", ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-lite-latest"])
    return cfg


def en_nube():
    """True cuando corre en el servidor (Render). Ahí no hay Excel ni OneDrive: los datos los sube el PC puente."""
    return os.environ.get("CALIDAD_NUBE", "") == "1"


def carpeta_datos(cfg=None):
    """Carpeta local para reportes y datos privados. Distinta de la versión local para no mezclarlas."""
    cfg = cfg or cargar()
    ruta = Path(cfg.get("carpeta_datos") or Path.home() / "CalidadKaravansayNube")
    (ruta / "reportes").mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_excel(valor):
    """Rutas relativas se toman desde la carpeta del proyecto. Una ruta tipo C:\\... se deja tal cual, también en
    el servidor (Linux), para que coincida con la que guardó el PC puente."""
    if re.match(r"^[A-Za-z]:[\\/]", valor):
        return Path(valor)
    ruta = Path(valor)
    return ruta if ruta.is_absolute() else PROYECTO / ruta


def _privado(variable, archivo, cfg=None):
    valor = os.environ.get(variable, "").strip()
    if valor:
        return valor
    ruta = carpeta_datos(cfg) / archivo
    return ruta.read_text(encoding="utf-8").strip() if ruta.exists() else ""


def clave_ia(cfg=None):
    return _privado("GEMINI_API_KEY", "clave_gemini.txt", cfg)


def url_bd(cfg=None):
    """Dirección de PostgreSQL (Neon). Vacía = base SQLite local."""
    return _privado("DATABASE_URL", "bd_nube.txt", cfg)


def secreto_sesion():
    """Firma las sesiones. En Render lo genera el Blueprint (CALIDAD_SECRETO); en el PC se crea una vez en un
    archivo. Si cambia, todas las sesiones abiertas se cierran."""
    valor = _privado("CALIDAD_SECRETO", "secreto_sesion.txt")
    if not valor:
        import secrets
        valor = secrets.token_hex(32)
        (carpeta_datos() / "secreto_sesion.txt").write_text(valor, encoding="utf-8")
    return valor
