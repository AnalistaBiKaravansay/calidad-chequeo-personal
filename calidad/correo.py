"""Envío del reporte. Dos formas (config.json -> "envio"):

  "onedrive": deja el reporte como archivo .html en una carpeta de OneDrive y un flujo de Power Automate
              lo envía por correo (el asunto es el nombre del archivo). Funciona con el nuevo Outlook.
  "outlook":  usa el Outlook clásico instalado y configurado en el equipo (el nuevo Outlook no lo permite).
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

COMANDO = (
    "$o = New-Object -ComObject Outlook.Application; $m = $o.CreateItem(0); "
    "$m.To = $env:CORREO_PARA; $m.Subject = $env:CORREO_ASUNTO; "
    "$m.HTMLBody = [IO.File]::ReadAllText($env:CORREO_ARCHIVO, [Text.Encoding]::UTF8); $m.Send()"
)


def enviar(cfg, asunto, html):
    """Devuelve un texto que describe cómo quedó el envío."""
    if cfg.get("envio", "onedrive") == "outlook":
        _outlook(cfg["correo_destino"], asunto, html)
        return "enviado por Outlook a " + ", ".join(cfg["correo_destino"])
    archivo = _onedrive(cfg, asunto, html)
    return f"dejado en {archivo} para que Power Automate lo envíe"


def _onedrive(cfg, asunto, html):
    if not cfg.get("carpeta_envio"):
        raise RuntimeError('Falta "carpeta_envio" en config.json (carpeta de OneDrive que vigila Power Automate).')
    carpeta = Path(cfg["carpeta_envio"])
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / (re.sub(r'[<>:"/\\|?*]', "-", asunto).strip() + ".html")
    archivo.write_text(html, encoding="utf-8")
    return archivo


def _outlook(destinatarios, asunto, html):
    with tempfile.TemporaryDirectory() as carpeta:
        cuerpo = Path(carpeta) / "reporte.html"
        cuerpo.write_text(html, encoding="utf-8")
        entorno = {**os.environ, "CORREO_PARA": "; ".join(destinatarios), "CORREO_ASUNTO": asunto,
                   "CORREO_ARCHIVO": str(cuerpo)}
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", COMANDO],
                           env=entorno, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("Outlook no pudo enviar el correo (¿Outlook clásico configurado?): "
                           + (r.stderr or r.stdout).strip()[:300])
