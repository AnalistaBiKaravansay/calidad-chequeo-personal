"""Pruebas de la versión en la nube: inicio de sesión, modo nube, puente y copia de la base (datos inventados)."""
import sqlite3

import openpyxl
import pytest
from fastapi.testclient import TestClient

from calidad import config, datos, web
from test_calidad import SALUD, fila


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    """Toda la herramienta trabaja en una carpeta temporal, sin base en la nube."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    original = config.cargar
    monkeypatch.setattr(config, "cargar", lambda: {**original(), "carpeta_datos": str(tmp_path)})
    return tmp_path


def cliente(monkeypatch, clave="", nube=False):
    monkeypatch.setenv("CALIDAD_CLAVE", clave)
    monkeypatch.setenv("CALIDAD_NUBE", "1" if nube else "")
    web._ultima_sincronizacion = 9e18
    return TestClient(web.app)


def test_sin_clave_no_pide_inicio_de_sesion(carpeta, monkeypatch):
    assert cliente(monkeypatch).get("/guia").status_code == 200


def test_con_clave_exige_inicio_de_sesion(carpeta, monkeypatch):
    c = cliente(monkeypatch, clave="secreta")
    r = c.get("/datos?lugar=PLANTA%202", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?volver=/datos")
    assert c.get("/salud").status_code == 200   # Render la usa sin clave
    r = c.post("/login", data={"clave": "mala", "volver": "/datos"}, follow_redirects=False)
    assert "error=1" in r.headers["location"] and "calidad_sesion" not in r.cookies
    r = c.post("/login", data={"clave": "secreta", "volver": "/datos"}, follow_redirects=False)
    assert r.headers["location"] == "/datos"
    assert c.get("/datos").status_code == 200
    # Cambiar la clave cierra las sesiones abiertas.
    monkeypatch.setenv("CALIDAD_CLAVE", "otra")
    assert c.get("/datos", follow_redirects=False).status_code == 303


def test_login_no_redirige_a_otro_sitio(carpeta, monkeypatch):
    c = cliente(monkeypatch, clave="secreta")
    r = c.post("/login", data={"clave": "secreta", "volver": "//sitio-malo.com"}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_modo_nube_no_lee_excel_ni_ofrece_correo(carpeta, monkeypatch):
    con = datos.conectar()
    datos.guardar(con, fila(1, fecha="2026-10-20 08:00:00")); con.commit(); con.close()
    monkeypatch.setattr(datos, "sincronizar", lambda *a, **k: pytest.fail("en la nube no se leen los Excel"))
    c = cliente(monkeypatch, nube=True)
    assert "Enviar por correo" not in c.get("/?dia=2026-10-20").text
    r = c.post("/recargar", data={"volver": "/"})
    assert "PC puente" in r.text


def _excel(ruta, filas_):
    wb = openpyxl.Workbook(); ws = wb.active
    encabezados = list(filas_[0].keys())
    ws.append(encabezados)
    for f in filas_:
        ws.append([f[h] for h in encabezados])
    wb.save(ruta)


def test_puente_solo_guarda_lo_nuevo_o_cambiado(carpeta):
    excel = carpeta / "flujo.xlsx"
    cfg = {**config.cargar(), "excel_flujo": str(excel)}
    _excel(excel, [fila(1), fila(2, nombre="Otra Persona")])
    con = datos.conectar(cfg)
    assert datos.sincronizar(con, cfg)[0]["guardadas"] == 2
    _excel(excel, [fila(1), fila(2, nombre="Otra Persona", obs="Gripa"), fila(3, nombre="Nueva")])
    estado = datos.sincronizar(con, cfg, forzar=True)[0]
    assert estado["leidas"] == 3 and estado["guardadas"] == 2   # la 2 cambió y la 3 es nueva
    assert con.execute("SELECT observacion FROM respuestas WHERE id=2").fetchone()[0] == "Gripa"


def test_subir_copia_la_base_anterior_sin_duplicar(carpeta, tmp_path):
    anterior = tmp_path / "anterior.db"
    vieja = sqlite3.connect(anterior)
    vieja.executescript("""
      CREATE TABLE respuestas(id INTEGER PRIMARY KEY, fecha TEXT, dia TEXT, nombre TEXT, persona TEXT, lugar TEXT,
        responsable TEXT, observacion TEXT, novedades TEXT, crudo TEXT);
      CREATE TABLE valoraciones(id INTEGER PRIMARY KEY AUTOINCREMENT, dia TEXT, respuesta_id INTEGER, situacion TEXT,
        consejo TEXT, voto INTEGER, correccion TEXT, creado TEXT, UNIQUE(respuesta_id, consejo));
      INSERT INTO respuestas VALUES (7,'2026-10-20 08:00:00','2026-10-20','Ana','ana','PLANTA 1','R','',
        '[]','{}');
      INSERT INTO valoraciones(dia,respuesta_id,situacion,consejo,voto,correccion,creado)
        VALUES ('2026-10-20',7,'Gripa','Tapabocas',1,NULL,'2026-10-20T09:00:00');
    """)
    vieja.close()
    con = datos.conectar()
    assert datos.subir(anterior, con) == {"respuestas": 1, "valoraciones": 1}
    datos.subir(anterior, con)   # repetir no duplica
    assert con.execute("SELECT count(*) FROM respuestas").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM valoraciones").fetchone()[0] == 1


def test_ruta_de_windows_se_respeta_en_el_servidor():
    # Debe quedar igual a la que guardó el PC puente, también cuando la página corre en Linux.
    assert str(config.ruta_excel("C:\\Users\\x\\flujo.xlsx")) == "C:\\Users\\x\\flujo.xlsx"
