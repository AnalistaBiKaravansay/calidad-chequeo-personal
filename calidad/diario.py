"""Proceso diario: sincronizar, pedir consejos a la IA, guardar el reporte y enviarlo por correo."""
from datetime import datetime

from . import config, correo, datos, reporte


def enviar_reporte(con, dia, cfg, forzar=False, prueba=False):
    """Envía el reporte del día una sola vez (salvo forzar). Devuelve un mensaje para mostrar."""
    if not cfg["correo_destino"]:
        raise RuntimeError("No hay correos de destino en config.json.")
    ya = con.execute("SELECT enviado FROM envios WHERE dia=?", (dia,)).fetchone()
    if ya and not forzar and not prueba:
        return f"El reporte del {dia} ya se envió el {ya[0]}."
    contexto = reporte.construir(con, dia, cfg)
    asunto = ("[PRUEBA] " if prueba else "") + reporte.asunto(contexto)
    resultado = correo.enviar(cfg, asunto, reporte.html_correo(contexto))
    if not prueba:
        with con:
            con.execute("INSERT INTO envios(dia, destinatarios, enviado) VALUES (?,?,?) ON CONFLICT(dia) "
                        "DO UPDATE SET destinatarios=excluded.destinatarios, enviado=excluded.enviado",
                        (dia, ", ".join(cfg["correo_destino"]), datetime.now().strftime("%Y-%m-%d %H:%M")))
    return f"Reporte del {dia} {resultado}."


def ejecutar(dia=None, enviar=False, forzar=False, prueba=False):
    cfg = config.cargar()
    dia = dia or datetime.now().strftime("%Y-%m-%d")
    con = datos.conectar(cfg)
    try:
        for f in datos.sincronizar(con, cfg):
            print(f"- {f['fuente']}: " + (f"ok, última respuesta {f.get('ultima_respuesta')}" if f["ok"] else f["error"]))
        contexto = reporte.construir(con, dia, cfg)
        archivo = config.carpeta_datos(cfg) / "reportes" / f"reporte_{dia}.html"
        archivo.write_text(reporte.html_correo(contexto), encoding="utf-8")
        r = contexto["resumen"]
        print(f"{dia}: {r['respuestas']} chequeos, {r['eta']} alertas ETA, {r['salud']} con síntomas/lesiones, "
              f"{r['bpm']} BPM, {r['dotacion']} dotación/EPP. IA: {contexto['ia']['estado']}.")
        if contexto["aviso_fuente"]:
            print("AVISO:", contexto["aviso_fuente"])
        print("Reporte guardado en", archivo)
        if enviar:
            print(enviar_reporte(con, dia, cfg, forzar, prueba))
    finally:
        con.close()
