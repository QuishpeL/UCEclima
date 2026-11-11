# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Pruebas de Lambda 9.1.0: módulo 7b de pronóstico (GFS, ECMWF, NASA IMERG, GEOGLOWS), botón de calado · velocidad · peligro, franja de desconexión y marca.
Los servicios externos se simulan (sin internet). Ejecutar: python -m uceclima.tests.test_lambda"""
import json, sys, tempfile, threading, time, traceback, urllib.request, urllib.error
from pathlib import Path
import numpy as np
import pandas as pd
import uceclima
from uceclima import pronostico as PRO, peligro as PEL
from uceclima.ui import servidor as SV, demo

TMP = Path(tempfile.mkdtemp(prefix="uceclima_lambda_"))
SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SV.ESTADO.puerto}"
ESTATICOS = Path(uceclima.__file__).parent / "ui" / "static"


def get(ruta):
    try:
        with urllib.request.urlopen(BASE + ruta, timeout=60) as r:
            ct = r.headers.get("Content-Type", ""); b = r.read(); return json.loads(b) if "json" in ct else b
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def post(ruta, cuerpo=None):
    req = urllib.request.Request(BASE + ruta, data=json.dumps(cuerpo or {}).encode(), method="POST", headers={"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _falso_open_meteo(lluvia_mm_por_hora):
    """Simula api.open-meteo.com: tantas respuestas como coordenadas pidió el programa."""
    def f(url, timeout=120):
        n = len(url.split("latitude=")[1].split("&")[0].split(","))
        t = pd.date_range("2026-11-05 00:00", periods=len(lluvia_mm_por_hora), freq="1h")
        e = {"latitude": -2.2, "longitude": -81.0, "hourly": {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in t], "precipitation": [float(v) for v in lluvia_mm_por_hora]}}
        return e if n == 1 else [dict(e) for _ in range(n)]
    return f


TORMENTA = np.r_[np.zeros(6), [2, 6, 10, 14, 9, 5, 2], np.zeros(59)]                    # 72 h con 48 mm
SECO = np.zeros(72)


def test_marca_y_menu_de_lambda():
    assert uceclima.__version__ == "9.1.0-lambda"
    html = get("/").decode("utf-8"); assert "<strong>UCEclima Lambda</strong>" in html and "Versión 9.1" in html and "descCerrar" in html and "peligro.js" in html and "pronostico.js" in html
    ids = [m["id"] for m in get("/api/estado")["modulos"]]; assert "pronostico" in ids and ids.index("pronostico") == ids.index("corrida") + 1


def test_franja_de_desconexion_solo_cuando_se_corta():
    js = (ESTATICOS / "app.js").read_text(encoding="utf-8")
    assert "FALLOS_PARA_AVISAR = 6" in js and "SEGUNDOS_SIN_RESPUESTA = 60" in js and "document.hidden" in js and "visibilitychange" in js and "/api/estado" in js and "AbortController" in js
    assert "FALLOS_LATIDO >= 2" not in js                                           # el umbral de Eta (2 fallos = 20 s) ya no existe
    html = (ESTATICOS / "index.html").read_text(encoding="utf-8")
    etiqueta = html[html.index('<div id="desconexion"'):].split(">", 1)[0]
    assert " hidden" in etiqueta and "display:" not in etiqueta, "un display en línea anula el atributo hidden y la franja queda siempre a la vista"
    assert "#desconexion:not([hidden]){display:flex}" in html and "#desconexion[hidden]{display:none}" in html


def test_pronostico_consulta_compara_y_guarda_con_procedencia():
    c = demo.crear_sintetico(TMP / "sint_pron"); post("/api/proyecto/abrir", {"ruta": str(c)})
    PRO._http_json = _falso_open_meteo(TORMENTA)
    code, j = post("/api/pronostico/comparar", {"modelos": ["gfs", "ecmwf"], "dias": 3, "lon": -81.0, "lat": -2.2, "muestreo": "punto", "zona": "UTC"}); assert code == 200, j
    assert set(j["modelos"]) == {"gfs", "ecmwf"} and not j["errores"] and abs(j["modelos"]["gfs"]["total_mm"] - TORMENTA.sum()) < 0.2, j["modelos"]["gfs"]
    assert j["modelos"]["gfs"]["max_1h_mm"] == 14.0 and j["tabla"][0]["dia"] == "2026-11-05" and abs(j["tabla"][0]["gfs"] - TORMENTA[:24].sum()) < 0.2 and "alerta oficial" in j["aviso"]
    carp = Path(j["modelos"]["gfs"]["carpeta"]); assert (carp / "lluvia_horaria_UTC.csv").exists() and (carp / "procedencia.json").exists() and "Open-Meteo" in j["atribucion"]
    lista = get("/api/pronostico/lista"); assert len(lista["consultas"]) == 2 and lista["modelos"]["imerg"]["tipo"] == "satelite"
    ser = get("/api/pronostico/serie?id=" + j["modelos"]["gfs"]["id"]); assert len(ser["hietograma"]) == 72
    PRO._http_json = _falso_open_meteo(TORMENTA)
    code, k = post("/api/pronostico/comparar", {"modelos": ["gfs"], "dias": 3, "lon": -81.0, "lat": -2.2, "muestreo": "area", "zona": "UTC"}); assert code == 200 and k["modelos"]["gfs"]["puntos_pedidos"] > 1, k    # promedio del área 2D
    assert k["modelos"]["gfs"]["id"] not in {j["modelos"]["gfs"]["id"]} and len(get("/api/pronostico/lista")["consultas"]) == 3                       # dos consultas en el mismo segundo no chocan ni se sobrescriben
    assert post("/api/pronostico/consultar", {"modelo": "nasa_inventada", "lon": -81.0, "lat": -2.2})[0] == 400
    assert post("/api/pronostico/consultar", {"modelo": "gfs", "dias": 30, "lon": -81.0, "lat": -2.2})[0] == 400


def test_pronostico_sin_lluvia_no_se_modela_y_errores_de_red_se_dicen():
    c = demo.crear_sintetico(TMP / "sint_seco"); post("/api/proyecto/abrir", {"ruta": str(c)})
    PRO._http_json = _falso_open_meteo(SECO)
    code, j = post("/api/pronostico/consultar", {"modelo": "gfs", "dias": 3, "lon": -81.0, "lat": -2.2, "muestreo": "punto"}); assert code == 200 and j["total_mm"] == 0.0
    code, e = post("/api/pronostico/usar", {"id": j["id"], "horas": 24}); assert code == 400 and "nada que modelar" in e["error"], e
    def sin_red(url, timeout=120):
        raise PRO.PronosticoError("No hay conexión con el servicio de pronóstico (revisa tu internet y vuelve a intentarlo): simulada")
    PRO._http_json = sin_red
    code, e = post("/api/pronostico/consultar", {"modelo": "ecmwf", "lon": -81.0, "lat": -2.2}); assert code == 400 and "No hay conexión" in e["error"], e
    code, e = post("/api/pronostico/comparar", {"modelos": ["gfs", "ecmwf"], "lon": -81.0, "lat": -2.2}); assert code == 400 and "Ningún modelo respondió" in e["error"], e


def test_pronostico_como_forzamiento_rotula_pronostico_y_luego_peligro():
    c = demo.crear_sintetico(TMP / "sint_uso"); post("/api/proyecto/abrir", {"ruta": str(c)})
    PRO._http_json = _falso_open_meteo(TORMENTA)
    code, j = post("/api/pronostico/consultar", {"modelo": "gfs", "dias": 3, "lon": -81.0, "lat": -2.2, "muestreo": "punto"}); assert code == 200, j
    code, u = post("/api/pronostico/usar", {"id": j["id"], "horas": 24}); assert code == 200, u
    assert u["forzamiento_externo"]["tipo"] == "pronostico" and u["estacion"].startswith("PRON_GFS_") and abs(u["P_total_mm"] - TORMENTA[:24].sum()) < 0.2 and "PRONÓSTICO" in u["siguiente_paso"], u
    assert get("/api/proyecto/evento")["evento"]["forzamiento_externo"]["modelo"] == "gfs"
    code, v = post("/api/verificar"); chk = {x["id"]: x for x in v["chequeos"]}; assert "PRONÓSTICO" in chk["evento"]["mensaje"] and "EVENTO OBSERVADO" not in chk["evento"]["mensaje"] and "pronóstico" in chk["idf"]["mensaje"], v
    code, r = post("/api/corrida/iniciar"); assert code == 200, r
    rid = r["id"]
    for _ in range(300):
        e = get("/api/corrida/estado?id=" + rid)
        if e["estado"] != "en_curso": break
        time.sleep(1)
    assert e["estado"] == "completado", e
    res = get("/api/corrida/resultado?id=" + rid)["resumen"]
    assert res["tipo_forzamiento"] == "pronostico" and res["escenario"] == "pronostico_gfs" and "PRONÓSTICO" in res["aviso"] and "OBSERVADO" not in res["aviso"] and res["forzamiento_externo"]["modelo"] == "gfs", res
    assert res["idf_fuente"].startswith("PRONÓSTICO") and res["estado_calibracion"] == "no calibrado"
    for _ in range(100):
        if not get("/api/estado")["corrida_activa"]: break
        time.sleep(0.2)
    # ---- botón de calado, velocidad y peligro (sobre esta misma corrida)
    code, p = post("/api/peligro/generar", {"id": rid}); assert code == 200, p
    c0 = p["corridas"][0]; out = Path(c0["carpeta"]); assert out.parent.name == "13_peligro" and Path(c0["lamina"]).exists() and (out / "resumen_peligro.csv").exists() and (out / "LEEME.md").exists()
    for var, base in (("calado", "calado_max_m"), ("velocidad", "velocidad_max_ms"), ("peligro", "peligro_hv_m2s")):
        assert (out / var / f"{base}.tif").exists() and (out / var / f"{base}.png").exists(), var
    assert any((out / "calado").glob("*.shp")) and any((out / "peligro").glob("*.gpkg")) and len(c0["resumen"]) == 4 and "sin calibrar" in c0["aviso"]
    assert post("/api/peligro/generar", {"id": "corrida_que_no_existe"})[0] == 400
    assert post("/api/peligro/generar", {"id": rid, "zoom": [1, 1, 0, 0]})[0] == 400                                      # el mínimo debe ser menor que el máximo
    assert len(list((Path(c) / "productos" / "13_peligro").glob("*"))) == 1                                              # las pruebas inválidas no dejaron carpetas a medias


def test_peligro_usa_el_terreno_de_la_corrida_y_excluye_el_mar():
    import rasterio
    from rasterio.transform import from_origin
    proy = TMP / "p_peligro"; run = proy / "resultados" / "corrida_20261101_000000_real"; sal = run / "salida" / "ev"; sal.mkdir(parents=True)
    (proy / "proyecto_uceclima.json").write_text(json.dumps({"nombre": "Mar y ladera"}), encoding="utf-8"); (proy / "config_climanet.json").write_text(json.dumps({"dem": "no_es_este.tif"}), encoding="utf-8")
    T = from_origin(500000, 9760000, 30, 30); perfil = dict(driver="GTiff", height=40, width=40, count=1, dtype="float32", crs="EPSG:32717", transform=T)
    dem = np.tile(np.linspace(0, 20, 40, dtype="float32"), (40, 1))                       # columnas 0–1 con cota ≤ 1 m (mar)
    h = np.full((40, 40), 0.5, "float32"); v = np.full((40, 40), 1.0, "float32")                          # h·v = 0,5: clase «niños y autos»
    for nombre, a in (("hmax", h), ("vmax", v)):
        with rasterio.open(sal / f"{nombre}.tif", "w", **perfil) as w: w.write(a, 1)
    with rasterio.open(proy / "dem_de_la_corrida.tif", "w", **perfil) as w: w.write(dem, 1)
    (run / "entrada.json").write_text(json.dumps({"config": {"dem": str(proy / "dem_de_la_corrida.tif")}}), encoding="utf-8")
    r = PEL.generar(proy)["corridas"][0]
    assert r["terreno"] == "dem_de_la_corrida.tif" and r["mar_excluido"] is True and r["area_mar_km2"] > 0            # usó el MDT de la corrida, no el «no_es_este.tif» de la configuración
    clase = {f["clase"]: f["area_tierra_km2"] for f in r["resumen"]}; assert clase["adultos (0,6–1,2)"] == 0 and clase["niños y autos (0,3–0,6)"] > 0 and clase["extremo (> 1,2)"] == 0
    assert PEL.generar(proy, "todas")["corridas"][0]["id"] == run.name
    try:
        PEL.generar(TMP / "p_peligro_vacio"); raise AssertionError("debía fallar sin corridas")
    except PEL.PeligroError as e:
        assert "no tiene corridas" in str(e)


def test_geoglows_forecast_recorta_y_cierra_el_hidrograma():
    c = demo.crear_sintetico(TMP / "sint_geo"); post("/api/proyecto/abrir", {"ruta": str(c)})
    t = pd.date_range("2026-11-05 00:00", periods=40, freq="3h", tz="UTC")
    PRO._http_json = lambda url, timeout=120: {"datetime": [x.strftime("%Y-%m-%dT%H:%M:%S") for x in t], "flow_median": list(np.linspace(10, 90, 40)), "flow_uncertainty_upper": list(np.linspace(12, 140, 40)), "flow_uncertainty_lower": list(np.linspace(8, 60, 40))}
    code, j = post("/api/pronostico/geoglows", {"river_id": 670065959, "horas": 48}); assert code == 200, j
    d = Path(j["carpeta"]); q = pd.read_csv(d / "geoglows_mediana_t_s_Q_m3s.csv")
    assert q["t_s"].iloc[0] == 0 and q["Q_m3s"].iloc[-1] == 0.0 and q["t_s"].iloc[-2] <= 48 * 3600 and j["q_alta_max_m3s"] > j["q_mediana_max_m3s"] and "orden de magnitud" in j["nota"]
    assert post("/api/pronostico/geoglows", {"river_id": "abc"})[0] == 400


def test_chirps_barras_de_error_con_meses_secos():
    import matplotlib; matplotlib.use("Agg")
    from uceclima import chirps_salidas as CS
    import inspect
    src = inspect.getsource(CS.generar); assert "np.clip(m - p25, 0, None)" in src and "np.clip(p75 - m, 0, None)" in src


if __name__ == "__main__":
    fallos = 0
    for nombre, f in sorted(globals().items()):
        if nombre.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", nombre)
            except BaseException:
                fallos += 1; print("FALLA", nombre); traceback.print_exc()
    SRV.shutdown(); sys.exit(1 if fallos else 0)
