"""Pruebas de la versión en la nube: usuarios y perfiles, modo nube, puente y copia de la base (datos inventados)."""
import sqlite3
from contextlib import closing

import openpyxl
import pytest
from fastapi.testclient import TestClient

from calidad import config, datos, usuarios, web
from test_calidad import SALUD, fila


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    """Toda la herramienta trabaja en una carpeta temporal, sin base en la nube."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    original = config.cargar
    monkeypatch.setattr(config, "cargar", lambda: {**original(), "carpeta_datos": str(tmp_path)})
    return tmp_path


def cliente(monkeypatch, nube=False, admin=""):
    """Cliente de la página. admin='clave' crea el usuario admin y entra con él."""
    monkeypatch.setenv("CALIDAD_NUBE", "1" if nube else "")
    web._ultima_sincronizacion = 9e18
    usuarios.olvidar()
    c = TestClient(web.app, base_url="https://testserver")   # en la nube la cookie es solo https
    if admin:
        with closing(datos.conectar()) as con:
            usuarios.asegurar_admin(con, admin)
        entrar(c, "admin", admin)
    return c


def entrar(c, usuario, clave, volver="/"):
    return c.post("/login", data={"usuario": usuario, "clave": clave, "volver": volver}, follow_redirects=False)


def test_sin_usuarios_en_el_pc_no_pide_inicio_de_sesion(carpeta, monkeypatch):
    c = cliente(monkeypatch)
    assert c.get("/guia").status_code == 200
    # Pero la Administración no: solo la ve el usuario admin.
    assert c.get("/admin").status_code == 403
    assert "Administración" not in c.get("/guia").text


def test_con_usuarios_exige_inicio_de_sesion(carpeta, monkeypatch):
    c = cliente(monkeypatch, nube=True)
    r = c.get("/datos?lugar=PLANTA%202", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?volver=/datos")
    assert c.get("/salud").status_code == 200   # Render la usa sin clave
    with closing(datos.conectar()) as con:
        usuarios.asegurar_admin(con, "Prueba123*")
    r = entrar(c, "admin", "mala", "/datos")
    assert "error=1" in r.headers["location"] and "calidad_sesion" not in r.cookies
    r = entrar(c, "ADMIN ", "Prueba123*", "/datos")   # el usuario no distingue mayúsculas ni espacios
    assert r.headers["location"] == "/datos"
    assert c.get("/datos", follow_redirects=False).status_code == 200
    # Cambiar la clave del usuario cierra sus sesiones abiertas.
    with closing(datos.conectar()) as con:
        usuarios.asegurar_admin(con, "OtraClave1")
    assert c.get("/datos", follow_redirects=False).status_code == 303


def test_login_no_redirige_a_otro_sitio(carpeta, monkeypatch):
    c = cliente(monkeypatch, nube=True, admin="Prueba123*")
    c.cookies.clear()
    r = entrar(c, "admin", "Prueba123*", "//sitio-malo.com")
    assert r.headers["location"] == "/"


def test_admin_crea_perfiles_y_usuarios_con_permisos(carpeta, monkeypatch):
    c = cliente(monkeypatch, nube=True, admin="Prueba123*")
    pagina = c.get("/admin", follow_redirects=False)
    assert pagina.status_code == 200 and "Crear usuario" in pagina.text
    # Perfil nuevo que solo ve el Tablero; 'admin' no se puede asignar aunque se envíe.
    r = c.post("/admin/perfil", data={"nombre": "Supervisores", "nuevo": "1", "permisos": ["tablero", "admin"]})
    assert "Perfil Supervisores guardado" in r.text
    r = c.post("/admin/usuario/nuevo", data={"usuario": "Ana Mal", "nombre": "Ana", "perfil": "Supervisores",
                                              "clave": "clave123"})
    assert "minúsculas" in r.text   # usuario con espacio: no se crea
    r = c.post("/admin/usuario/nuevo", data={"usuario": "ana.p", "nombre": "Ana P", "perfil": "Supervisores",
                                              "clave": "corta"})
    assert "al menos 8" in r.text
    c.post("/admin/usuario/nuevo", data={"usuario": "ana.p", "nombre": "Ana P", "perfil": "Supervisores",
                                         "clave": "clave123"})
    with closing(datos.conectar()) as con:
        guardada = con.execute("SELECT clave FROM usuarios WHERE usuario='ana.p'").fetchone()[0]
    assert guardada.startswith("pbkdf2$") and "clave123" not in guardada

    ana = cliente(monkeypatch, nube=True)
    assert entrar(ana, "ana.p", "clave123").status_code == 303
    assert ana.get("/", follow_redirects=False).headers["location"] == "/tablero"   # su primera sección
    assert ana.get("/tablero", follow_redirects=False).status_code == 200
    menu = ana.get("/tablero").text
    assert "Ana P" in menu and 'href="/datos"' not in menu and 'href="/admin"' not in menu
    assert ana.get("/datos").status_code == 403
    assert ana.get("/admin").status_code == 403
    assert ana.post("/admin/usuario/borrar", data={"usuario": "admin"}).status_code == 403

    # El perfil con usuarios no se borra; el admin no se borra ni se desactiva.
    assert "tiene usuarios" in c.post("/admin/perfil/borrar", data={"nombre": "Supervisores"}).text
    assert "no se puede borrar" in c.post("/admin/usuario/borrar", data={"usuario": "admin"}).text
    c.post("/admin/usuario/editar", data={"usuario": "admin", "nombre": "Admin", "perfil": "Consulta"})
    assert c.get("/admin").status_code == 200

    # Desactivar a Ana cierra su sesión.
    c.post("/admin/usuario/editar", data={"usuario": "ana.p", "nombre": "Ana P", "perfil": "Supervisores"})
    assert ana.get("/tablero", follow_redirects=False).status_code == 303
    assert entrar(ana, "ana.p", "clave123").headers["location"].startswith("/login")


def test_modo_nube_no_lee_excel_ni_ofrece_correo(carpeta, monkeypatch):
    con = datos.conectar()
    datos.guardar(con, fila(1, fecha="2026-10-20 08:00:00")); con.commit(); con.close()
    monkeypatch.setattr(datos, "sincronizar", lambda *a, **k: pytest.fail("en la nube no se leen los Excel"))
    c = cliente(monkeypatch, nube=True, admin="Prueba123*")
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


def test_fila_completa_se_guarda_compacta_y_se_lee_igual(carpeta):
    con = datos.conectar()
    original = fila(5, obs="Gripa")
    datos.guardar(con, original)
    texto = con.execute("SELECT crudo FROM respuestas WHERE id=5").fetchone()[0]
    assert "OBSERVACIONES" not in texto            # los nombres de columna no se repiten en cada fila
    assert datos.crudos(con, [5])[5]["OBSERVACIONES"] == "Gripa"
    assert datos.crudos(con, [5])[5]["Hora de finalización"] == "2026-10-20 08:00:00"


def test_compactar_pasa_el_formato_antiguo(carpeta):
    import json
    con = datos.conectar()
    viejo = {"Id": 9, "NOMBRE1": "Ana", "OBSERVACIONES": "Gripa"}
    con.execute("INSERT INTO respuestas VALUES (9,'2026-10-20 08:00:00','2026-10-20','Ana','ana','PLANTA 1','R',"
                "'Gripa',?,?)", (json.dumps([{"tipo": "salud", "clave": "respiratorio"}]), json.dumps(viejo)))
    con.commit()
    assert datos.compactar(con) == 1 and datos.compactar(con) == 0
    texto, novedades = con.execute("SELECT crudo, novedades FROM respuestas WHERE id=9").fetchone()
    assert texto.startswith("[") and '": ' not in novedades
    assert datos.crudos(con, [9])[9] == viejo


def test_puente_no_se_conecta_si_el_excel_no_cambio(carpeta):
    excel = carpeta / "flujo.xlsx"
    cfg = {**config.cargar(), "excel_flujo": str(excel)}
    _excel(excel, [fila(1)])
    assert datos.hay_cambios(cfg)
    con = datos.conectar(cfg)
    datos.sincronizar(con, cfg)
    assert not datos.hay_cambios(cfg)
    _excel(excel, [fila(1), fila(2, nombre="Nueva")])
    import os
    os.utime(excel, (excel.stat().st_atime, excel.stat().st_mtime + 5))
    assert datos.hay_cambios(cfg)


def test_ia_solo_consulta_los_casos_nuevos(carpeta, monkeypatch):
    import json
    import httpx
    from calidad import analisis, ia
    from test_calidad import CFG
    con = datos.conectar()
    datos.guardar(con, fila(1, nombre="Ana Uno", obs="Congestión"))
    enviados = []

    def falso_post(url, json=None, **kw):
        texto = json["contents"][0]["parts"][0]["text"]
        casos = __import__("json").loads(texto.split("CASOS DEL DÍA:\n")[1])
        enviados.append(texto)
        respuesta = {"resumen_dia": "r", "casos": [{"codigo": c["codigo"], "consejos": [f"consejo {c['codigo']}"]}
                                                   for c in casos]}
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(respuesta)}]}}]})

    monkeypatch.setattr("calidad.config.clave_ia", lambda cfg=None: "clave")
    monkeypatch.setattr(ia.httpx, "post", falso_post)
    _, casos = analisis.novedades_del_dia(con, "2026-10-20")
    ia.consejos_del_dia(con, "2026-10-20", casos, CFG)
    # Llega un caso nuevo que se ordena antes (los códigos C1, C2 cambian).
    datos.guardar(con, fila(2, nombre="Aaron Dos", **{SALUD["diarrea"]: "SI"}))
    _, casos = analisis.novedades_del_dia(con, "2026-10-20")
    r = ia.consejos_del_dia(con, "2026-10-20", casos, CFG)
    assert len(enviados) == 2
    segundo = enviados[1].split("CASOS DEL DÍA:\n")[1]
    assert len(json.loads(segundo)) == 1 and "Diarrea" in segundo        # solo el caso nuevo
    assert "CASOS YA REVISADOS HOY" in enviados[1]
    assert "CONSEJO INMEDIATO respiratorio" not in enviados[1]            # la guía solo trae lo que aplica
    ana = next(c["codigo"] for c in casos if c["nombre"] == "Ana Uno")
    assert r["casos"][ana]["consejos"] == ["consejo C1"]                   # se conservó lo de la primera consulta
    # Sin cambios: no se vuelve a consultar.
    ia.consejos_del_dia(con, "2026-10-20", casos, CFG)
    assert len(enviados) == 2


def test_paginas_comprimidas_y_estilos_en_cache(carpeta, monkeypatch):
    c = cliente(monkeypatch)
    r = c.get("/guia", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip" and "no-store" in r.headers["cache-control"]
    assert "logo.svg" in r.text
    assert "immutable" in c.get("/static/estilo.css").headers["cache-control"]


def test_nombre_numerado_es_la_misma_persona(carpeta):
    from calidad import reglas
    assert reglas.clave_persona("12. Dayana Salcedo") == reglas.clave_persona("dayana  salcedo") == "dayana salcedo"
    assert reglas.clave_persona("7.Candelaria Morales") == "candelaria morales"
    con = datos.conectar()
    datos.guardar(con, fila(1, nombre="12. Dayana Salcedo"))
    assert con.execute("SELECT nombre FROM respuestas WHERE id=1").fetchone()[0] == "Dayana Salcedo"
    con.execute("UPDATE respuestas SET nombre='5. Aurora Lazo', persona='5. aurora lazo' WHERE id=1")
    assert datos.unificar_personas(con) == 1
    assert con.execute("SELECT persona FROM respuestas WHERE id=1").fetchone()[0] == "aurora lazo"


def test_tablero_busca_por_parte_del_nombre_y_muestra_la_ficha(carpeta, monkeypatch):
    con = datos.conectar()
    datos.guardar(con, fila(1, nombre="Ana Gómez", obs="Gripa", fecha="2026-10-18 08:00:00"))
    datos.guardar(con, fila(2, nombre="9. Ana Gómez", fecha="2026-10-20 08:00:00",
                            **{"Criterios BPM.Uso adecuado cofia": "No cumple", "CRITERIOS EPP .Tapaoídos": "NO"}))
    datos.guardar(con, fila(3, nombre="Beto Gómez", fecha="2026-10-20 09:00:00"))
    con.commit(); con.close()
    c = cliente(monkeypatch)
    ficha = c.get("/tablero?persona=ana").text
    assert "Ficha de persona" in ficha and "2026-10-18" in ficha and "Uso adecuado cofia" in ficha
    assert "Tapaoídos" in ficha and ">2<" in ficha   # dos chequeos: el nombre numerado es la misma persona
    assert "Varias personas" in c.get("/tablero?persona=gomez").text
    general = c.get("/tablero").text
    assert "personas</span>" in general and "Criterios BPM incumplidos" in general
    assert c.get("/persona/ana%20gomez", follow_redirects=False).headers["location"].startswith("/tablero?persona=")


def test_ruta_de_windows_se_respeta_en_el_servidor():
    # Debe quedar igual a la que guardó el PC puente, también cuando la página corre en Linux.
    assert str(config.ruta_excel("C:\\Users\\x\\flujo.xlsx")) == "C:\\Users\\x\\flujo.xlsx"


def _como_conector(f):
    """Así devuelve la fila el conector de Excel de Power Automate: todo texto, vacíos como "", con metadatos."""
    salida = {"@odata.etag": "", "ItemInternalId": "abc-123"}
    for k, v in f.items():
        salida[k] = "" if v is None else (v.isoformat(sep=" ") if hasattr(v, "isoformat") else str(v))
    return salida


def test_flujo_envia_respuestas_directo(carpeta, monkeypatch):
    llamadas = []
    monkeypatch.setattr("calidad.flujo.consejos_ia", lambda dias: llamadas.append(dias))
    c = cliente(monkeypatch, nube=True)
    nueva = _como_conector(fila(70, obs="", fecha="2026-11-09 08:02:00", **{SALUD["diarrea"]: "SI"},
                                **{"Correo electrónico": None}))

    monkeypatch.delenv("CALIDAD_TOKEN_FLUJO", raising=False)
    assert c.post("/api/respuesta", json=nueva, headers={"x-token": ""}).status_code == 401   # entrada apagada
    monkeypatch.setenv("CALIDAD_TOKEN_FLUJO", "token-de-prueba")
    assert c.post("/api/respuesta", json=nueva, headers={"x-token": "otro"}).status_code == 401
    assert c.post("/api/respuesta", json=nueva).status_code == 401
    assert c.post("/api/respuesta", json={"NOMBRE1": "x"}, headers={"x-token": "token-de-prueba"}).status_code == 400

    r = c.post("/api/respuesta", json=nueva, headers={"x-token": "token-de-prueba"})
    assert r.status_code == 200 and r.json()["guardadas"] == [{"id": 70, "fecha": "2026-11-09 08:02:00",
                                                                "novedades": True}]
    assert llamadas == [["2026-11-09"]]   # la IA se pide después de responder, solo si hay novedades
    sin_novedad = _como_conector(fila(71, fecha="2026-11-09 08:05:00"))
    c.post("/api/respuesta", json={"filas": [sin_novedad]}, headers={"x-token": "token-de-prueba"})
    assert len(llamadas) == 1

    with closing(datos.conectar()) as con:
        guardada = con.execute("SELECT crudo, novedades, persona FROM respuestas WHERE id=70").fetchone()
        assert "diarrea" in guardada[1] and guardada[2] == "persona prueba"
        completa = datos.crudo(con, guardada[0])
        assert "ItemInternalId" not in completa and "@odata.etag" not in completa
        assert completa["Correo electrónico"] is None and completa["Id"] == 70
        # Si después llega la misma respuesta por el PC puente, se actualiza la misma fila: no se duplica.
        datos.guardar(con, fila(70, fecha="2026-11-09 08:02:00", **{SALUD["diarrea"]: "SI"},
                                **{"Correo electrónico": None}))
        con.commit()
        assert con.execute("SELECT count(*) FROM respuestas").fetchone()[0] == 2
