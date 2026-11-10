"""Pruebas con datos inventados (nunca datos reales)."""
import json
from datetime import datetime

import httpx
import pytest

from calidad import analisis, datos, ia, reglas, reporte

SALUD = {
    "ictericia": "CRITERIOS ESTADO DE SALUD.Icteria (Ojos y piel amarilla)",
    "vomito": "CRITERIOS ESTADO DE SALUD.Vómito (Que impida la ingesta de líquidos o alimentos)",
    "fiebre": "CRITERIOS ESTADO DE SALUD.Fiebre + dolor de garganta (Ambos síntomas juntos)",
    "herida": "CRITERIOS ESTADO DE SALUD.Herida infectada",
    "diarrea": "CRITERIOS ESTADO DE SALUD.Diarrea (Más de 3 deposiciones en menos de 24 h)",
}


def fila(id_=1, nombre="Persona Prueba", obs="", fecha="2026-10-20 08:00:00", lugar="PLANTA 1", **cambios):
    f = {"Id": id_, "Hora de finalización": datetime.fromisoformat(fecha), "NOMBRE1": nombre, "LUGAR": lugar,
         "OBSERVACIONES": obs, "RESPONSABLE DEL CHEQUEO": "Responsable",
         "Criterios BPM.Uso adecuado cofia": "Cumple", "Criterios BPM.Uniforme limpio, bata limpia": "Cumple",
         "CRITERIOS EPP .Tapaoídos": "SI", "GAFAS.Usa gafas": "NO", "GAFAS.Tiene cordón para las gafas": "NO"}
    f.update({h: "NO" for h in SALUD.values()})
    f.update(cambios)
    return f


def claves(f):
    return {n["clave"]: n["tipo"] for n in reglas.novedades(f)}


def test_pregunta_de_salud_en_si_es_alerta_eta():
    assert claves(fila(**{SALUD["diarrea"]: "SI"})) == {"diarrea": "eta"}


def test_observacion_sola_no_es_alerta_eta_sino_mencion():
    n = reglas.novedades(fila(obs="Ganas de vomitar pero no ha vomitado, deposición dos veces"))
    vomito = next(x for x in n if x["clave"] == "vomito")
    assert vomito["tipo"] == "salud" and vomito["etiqueta"].startswith("Mencionado")


def test_pregunta_y_observacion_se_unen():
    n = reglas.novedades(fila(obs="Diarrea desde ayer", **{SALUD["diarrea"]: "SI"}))
    assert [(x["clave"], x["tipo"], x["origen"]) for x in n] == [("diarrea", "eta", "pregunta y observación")]


def test_vomito_por_embarazo_no_es_alerta():
    c = claves(fila(obs="Embarazo, vómito en la mañana", **{SALUD["vomito"]: "SI"}))
    assert c["vomito"] == "salud" and "embarazo" in c


@pytest.mark.parametrize("obs,esperado", [
    ("Uniforme sin marcar, no tiene gorro pirata", {"uniforme": "dotacion", "gorro": "dotacion"}),
    ("Dolor de cabeza", {"dolor_cabeza": "salud"}),
    ("Gripa", {"respiratorio": "salud"}),
    ("Dolor de garganta", {"garganta": "salud"}),
    ("Fiebre y dolor de garganta", {"fiebre_garganta": "salud"}),
    ("Dolor de cintura", {"dolor_muscular": "salud"}),
    ("No presenta tos ni síntomas gripales", {}),
    ("Botas rotas y dolor en pierna", {"botas": "dotacion", "dolor_muscular": "salud"}),
    ("Dedo lesionado por machucón, se coloca cura y guante", {"lesion": "lesion", "elementos": "dotacion"}),
    ("Herida infectada con pus en la mano", {"herida_infectada": "salud"}),
    ("Trabaja con TCC", {"revisar": "revisar"}),
])
def test_observaciones(obs, esperado):
    assert claves(fila(obs=obs)) == esperado


def test_bpm_y_epp_y_gafas():
    c = claves(fila(**{"Criterios BPM.Uso adecuado cofia": "No cumple", "CRITERIOS EPP .Tapaoídos": "NO",
                       "GAFAS.Usa gafas": "SI"}))
    assert c == {"bpm:Uso adecuado cofia": "bpm", "epp:Tapaoídos": "epp", "epp:gafas_cordon": "epp"}


@pytest.fixture
def con(tmp_path):
    c = datos.conectar({"carpeta_datos": str(tmp_path)})
    yield c
    c.close()


CFG = {"dias_historial": 30, "correo_destino": ["prueba@ejemplo.com"], "ia_modelos": ["bueno", "basico"],
       "excel_forms": ""}


def test_repeticiones_y_posible_brote(con):
    for i, dia in enumerate(["2026-10-10", "2026-10-15", "2026-10-20"], 1):
        datos.guardar(con, fila(i, obs="Dolor de cabeza", fecha=dia + " 08:00:00"))
    for i, nombre in enumerate(["Ana Uno", "Beto Dos", "Ciro Tres"], 10):
        datos.guardar(con, fila(i, nombre=nombre, lugar="PLANTA 2", fecha="2026-10-20 07:00:00",
                                **{SALUD["diarrea"]: "SI"}))
    _, casos = analisis.novedades_del_dia(con, "2026-10-20")
    repetido = next(c for c in casos if c["nombre"] == "Persona Prueba")
    assert repetido["items"][0]["repeticiones"] == 2
    assert repetido["items"][0]["nivel"] == 2   # 3 días: seguimiento, todavía no cita médica
    assert not any("EPS" in p for p in repetido["items"][0]["pasos"])
    alertas = analisis.alertas_patrones(con, "2026-10-20")
    assert any("PLANTA 2" in a["texto"] and a["nivel"] == "alta" for a in alertas)


def test_escalera_gripa(con):
    dias = ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-20"]
    for i, dia in enumerate(dias, 1):
        datos.guardar(con, fila(i, obs="Congestión", fecha=dia + " 08:00:00"))
    niveles = []
    for dia in dias:
        _, casos = analisis.novedades_del_dia(con, dia)
        item = casos[0]["items"][0]
        niveles.append(item["nivel"])
        if item["nivel"] < 3:
            assert not any("EPS" in p for p in item["pasos"])
    assert niveles == [1, 1, 2, 2, 3]
    assert any("tapabocas" in p.lower() for p in item["pasos"]) and any("EPS" in p for p in item["pasos"])


def test_ia_no_recibe_nombres_ni_dotacion(con):
    datos.guardar(con, fila(1, nombre="Rosa Pérez", obs="Rosa con gripa. Uniforme roto"))
    datos.guardar(con, fila(2, nombre="Solo Epp", **{"CRITERIOS EPP .Tapaoídos": "NO"}))
    _, casos = analisis.novedades_del_dia(con, "2026-10-20")
    entrada = ia.preparar(casos)
    texto = json.dumps(entrada, ensure_ascii=False)
    assert "Rosa" not in texto and "Pérez" not in texto and "Solo" not in texto
    assert len(entrada) == 1 and all(n["tipo"] == "salud" for n in entrada[0]["novedades"])


def test_reporte_sin_clave_ia_muestra_la_guia(con, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("calidad.config.clave_ia", lambda cfg=None: "")
    datos.guardar(con, fila(1, **{SALUD["diarrea"]: "SI"}))
    contexto = reporte.construir(con, "2026-10-20", CFG)
    html = reporte.html_correo(contexto)
    assert contexto["ia"]["estado"] == "sin clave"
    assert "Exclusión del área de producción" in html and "Persona Prueba" in html


@pytest.mark.parametrize("valor", ["2026-10-27 08:15:00", "27/10/2026 08:15:00", 46322.34375])
def test_fecha_de_power_automate(valor):
    assert datos._fecha(valor).strftime("%Y-%m-%d %H:%M") == "2026-10-27 08:15"


def test_cada_regla_tiene_texto_para_la_guia():
    assert {clave for _, clave, _ in reglas.PALABRAS} <= reglas.EJEMPLOS.keys()


def test_ia_pasa_al_siguiente_modelo_y_no_repite_la_guia(con, monkeypatch):
    datos.guardar(con, fila(1, obs="Congestión"))
    _, casos = analisis.novedades_del_dia(con, "2026-10-20")
    paso_guia = casos[0]["items"][0]["pasos"][0]
    usados = []

    def falso_post(url, **kw):
        modelo = url.split("/models/")[1].split(":")[0]
        usados.append(modelo)
        if modelo == "bueno":
            return httpx.Response(503, json={"error": {"message": "saturado"}})
        texto = json.dumps({"resumen_dia": "r", "casos": [{"codigo": "C1", "consejos": [
            paso_guia, "Preguntar desde cuándo tiene la congestión y si empeora en el cuarto frío."]}]})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": texto}]}}]})

    monkeypatch.setattr("calidad.config.clave_ia", lambda cfg=None: "clave")
    monkeypatch.setattr(ia.httpx, "post", falso_post)
    r = ia.consejos_del_dia(con, "2026-10-20", casos, CFG)
    assert usados == ["bueno", "basico"] and r["modelo"] == "basico"
    assert r["casos"]["C1"]["consejos"] == ["Preguntar desde cuándo tiene la congestión y si empeora en el cuarto frío."]


def test_marcas_de_calidad_llegan_a_la_ia_sin_nombres(con, monkeypatch):
    datos.guardar(con, fila(1, nombre="Rosa Pérez", obs="Rosa con dolor de cintura"))
    ia.guardar_valoracion(con, 1, "Remitir a medicina laboral", voto=-1)
    ia.guardar_valoracion(con, 1, "Preguntar si carga cajas", voto=1)
    ia.guardar_valoracion(con, 1, "Preguntar si carga cajas", correccion="Pedirle a Rosa que haga pausa activa cada hora")
    marcas = ia.valoraciones_del_dia(con, "2026-10-20")
    assert marcas[(1, "Preguntar si carga cajas")] == {"voto": 1, "correccion": "Pedirle a [persona] que haga pausa activa cada hora"}
    texto_ejemplos = ia.ejemplos(con)
    assert "Rosa" not in texto_ejemplos and "Pérez" not in texto_ejemplos
    assert "NO ÚTIL" in texto_ejemplos and "Calidad prefiere: Pedirle a [persona]" in texto_ejemplos

    enviado = {}

    def falso_post(url, json=None, **kw):
        enviado["texto"] = json["contents"][0]["parts"][0]["text"]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"resumen_dia": "", "casos": []}'}]}}]})

    monkeypatch.setattr("calidad.config.clave_ia", lambda cfg=None: "clave")
    monkeypatch.setattr(ia.httpx, "post", falso_post)
    datos.guardar(con, fila(2, nombre="Otra Persona", obs="Gripa", fecha="2026-10-21 08:00:00"))
    _, casos = analisis.novedades_del_dia(con, "2026-10-21")
    ia.consejos_del_dia(con, "2026-10-21", casos, CFG)
    assert "APRENDIZAJES DE CALIDAD" in enviado["texto"] and "Rosa" not in enviado["texto"]
    assert ia.resumen_aprendizaje(con)["corregidos"] == 1


def test_ia_valida_respuesta():
    entrada = [{"codigo": "C1"}]
    datos_ia = {"resumen_dia": "ok", "casos": [{"codigo": "C1", "consejos": ["a", "b"]}, {"codigo": "C9", "consejos": ["x"]}]}
    assert ia.validar(datos_ia, entrada)["casos"] == {"C1": {"consejos": ["a", "b"], "atencion": ""}}


def test_no_aplica_nunca_es_alerta():
    # EPP y BPM con N/A no generan alerta.
    assert claves(fila(**{"CRITERIOS EPP .Tapaoídos": "N/A", "CRITERIOS EPP .Gafas": "N/A",
                          "Criterios BPM.No usa pestañas postizas": "N/A"})) == {}
    # Usa gafas y no tiene cordón, pero el EPP de gafas no aplica en su puesto: sin alerta.
    assert claves(fila(**{"GAFAS.Usa gafas": "SI", "GAFAS.Tiene cordón para las gafas": "NO",
                          "CRITERIOS EPP .Gafas": "N/A"})) == {}
    # Si el EPP de gafas sí aplica, el cordón cuenta.
    assert claves(fila(**{"GAFAS.Usa gafas": "SI", "GAFAS.Tiene cordón para las gafas": "NO",
                          "CRITERIOS EPP .Gafas": "SI"})) == {"epp:gafas_cordon": "epp"}
    # No usa gafas: nada del bloque GAFAS es alerta.
    assert claves(fila(**{"GAFAS.Usa gafas": "NO", "GAFAS.Tiene cordón para las gafas": "NO",
                          "GAFAS.Las gafas se encuentran en buen estado (sin rotos, tornillos completos)": "NO",
                          "CRITERIOS EPP .Gafas": "SI"})) == {}
