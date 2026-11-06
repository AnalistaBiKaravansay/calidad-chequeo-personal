"""Uso:
  python -m calidad diario [--fecha AAAA-MM-DD] [--enviar] [--forzar] [--prueba]
  python -m calidad web [--puerto 8766] [--abrir]
  python -m calidad sincronizar [--todo]
  python -m calidad clave-ia
  python -m calidad clave-bd           guarda la dirección de la base en la nube (Neon) en este equipo
  python -m calidad probar-bd          comprueba la conexión con la base
  python -m calidad subir [--desde RUTA]   copia la base local de la versión anterior a la nube
  python -m calidad compactar          pasa las respuestas guardadas al formato que ocupa menos espacio
"""
import argparse
import getpass
import threading
import time
import urllib.request
import webbrowser
from contextlib import closing
from pathlib import Path

from datetime import datetime

from . import config, datos, diario, reporte

BASE_ANTERIOR = Path.home() / "CalidadKaravansay" / "calidad.db"


def main():
    p = argparse.ArgumentParser(prog="calidad")
    sub = p.add_subparsers(dest="orden", required=True)
    d = sub.add_parser("diario", help="Genera el reporte del día y opcionalmente lo envía.")
    d.add_argument("--fecha", help="Día del reporte (por defecto hoy).")
    d.add_argument("--enviar", action="store_true", help="Enviar por correo (una vez por día).")
    d.add_argument("--forzar", action="store_true", help="Reenviar aunque ya se haya enviado.")
    d.add_argument("--prueba", action="store_true", help="Enviar con asunto [PRUEBA] sin marcarlo como enviado.")
    w = sub.add_parser("web", help="Abre la página web interna.")
    # 8766 para no chocar con la versión local (8765) si las dos están abiertas.
    w.add_argument("--puerto", type=int, default=8766)
    w.add_argument("--abrir", action="store_true")
    s = sub.add_parser("sincronizar", help="Lee los Excel configurados.")
    s.add_argument("--todo", action="store_true", help="Releer todo y recalcular novedades.")
    s.add_argument("--ia", action="store_true",
                   help="Si llegaron respuestas nuevas de hoy, pedir a la IA consejos para los casos nuevos.")
    sub.add_parser("clave-ia", help="Guarda la clave de Gemini en este equipo.")
    sub.add_parser("clave-bd", help="Guarda la dirección de la base en la nube en este equipo.")
    sub.add_parser("probar-bd", help="Comprueba la conexión con la base.")
    u = sub.add_parser("subir", help="Copia la base local de la versión anterior a la base configurada.")
    u.add_argument("--desde", default=str(BASE_ANTERIOR))
    sub.add_parser("compactar", help="Pasa las respuestas guardadas al formato compacto y libera el espacio.")
    a = p.parse_args()

    if a.orden == "diario":
        diario.ejecutar(a.fecha, a.enviar or a.prueba, a.forzar, a.prueba)
    elif a.orden == "sincronizar":
        if not a.todo and not datos.hay_cambios():
            # Sin conectarse: así la base en la nube sigue dormida y no gasta horas del plan gratuito.
            print("Los Excel no han cambiado desde la última subida. No se conectó a la base.")
            return
        with closing(datos.conectar()) as con:
            estado = datos.sincronizar(con, forzar=a.todo)
            for f in estado:
                print(f)
            if a.todo:
                datos.recalcular(con)
            print("Respuestas en la base:", con.execute("SELECT count(*) FROM respuestas").fetchone()[0])
            if a.ia and any(f.get("guardadas") for f in estado):
                # Consulta automática: solo se envían a la IA los casos que todavía no tienen consejo.
                hoy = datetime.now().strftime("%Y-%m-%d")
                print("IA:", reporte.construir(con, hoy)["ia"]["estado"])
    elif a.orden == "clave-ia":
        clave = getpass.getpass("Pegue la clave de Gemini (no se mostrará): ").strip()
        archivo = config.carpeta_datos() / "clave_gemini.txt"
        archivo.write_text(clave, encoding="utf-8")
        print("Clave guardada en", archivo)
    elif a.orden == "clave-bd":
        url = getpass.getpass("Pegue la dirección de conexión de Neon, la que empieza por postgresql:// "
                              "(no se mostrará): ").strip()
        if not url.startswith(("postgresql://", "postgres://")):
            print("Eso no parece una dirección de Neon (debe empezar por postgresql://). No se guardó nada.")
            return
        archivo = config.carpeta_datos() / "bd_nube.txt"
        archivo.write_text(url, encoding="utf-8")
        print("Dirección guardada en", archivo, "- ahora ejecute: probar-bd")
    elif a.orden == "probar-bd":
        destino = "la nube (PostgreSQL)" if config.url_bd() else "este equipo (SQLite, no hay dirección de la nube)"
        print("Conectando con", destino, "...")
        with closing(datos.conectar()) as con:
            print("Conexión correcta. Respuestas guardadas:", con.execute("SELECT count(*) FROM respuestas").fetchone()[0],
                  "| última:", datos.ultima_respuesta(con) or "(ninguna)")
    elif a.orden == "subir":
        if not config.url_bd():
            print("Primero guarde la dirección de la base con: clave-bd")
            return
        print("Copiando", a.desde, "a la nube. Puede tardar unos minutos...")
        with closing(datos.conectar()) as con:
            for tabla, n in datos.subir(a.desde, con).items():
                print(f"- {tabla}: {n} filas")
            print("Listo. Respuestas en la nube:", con.execute("SELECT count(*) FROM respuestas").fetchone()[0])
    elif a.orden == "compactar":
        with closing(datos.conectar()) as con:
            print("Respuestas pasadas al formato compacto:", datos.compactar(con))
            if con.postgres:
                # VACUUM FULL reescribe la tabla y devuelve el espacio liberado (no puede ir en una transacción).
                con.cruda.autocommit = True
                for tabla in ("respuestas", "ia"):
                    con.execute(f"VACUUM FULL {tabla}")
                tamano = con.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
                print("Tamaño de la base ahora:", tamano)
    elif a.orden == "web":
        url = f"http://127.0.0.1:{a.puerto}"
        if _responde(url):
            print("La página ya estaba abierta en otra ventana:", url)
            if a.abrir:
                webbrowser.open(url)
            return
        print("Cargando la página, espere unos segundos...")
        if a.abrir:
            threading.Thread(target=_abrir_cuando_responda, args=(url,), daemon=True).start()
        import uvicorn
        uvicorn.run("calidad.web:app", host="127.0.0.1", port=a.puerto, log_level="warning")


def _responde(url):
    try:
        urllib.request.urlopen(url + "/guia", timeout=2)
        return True
    except OSError:
        return False


def _abrir_cuando_responda(url):
    """Desde la carpeta de red el arranque es lento: se abre el navegador solo cuando la página contesta."""
    for _ in range(120):
        if _responde(url):
            print("Listo:", url, "(no cierre esta ventana mientras use la página)")
            webbrowser.open(url)
            return
        time.sleep(1)
    print("La página no respondió en 2 minutos. Cierre esta ventana y vuelva a intentarlo.")


if __name__ == "__main__":
    main()
