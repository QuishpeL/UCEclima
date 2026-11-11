# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Fase 2 · R2 (editar sitio), R3 (sufijo ucec, renombrar, listar), C17 (historial terreno), C19 (CN para la 2D), C23 (punto IDF), C24/C25 (entrega). Sin red.
Ejecutar: python -m uceclima.tests.test_fase2b"""
import json, shutil, sys, tempfile, threading, traceback, urllib.request, urllib.error
from pathlib import Path
import numpy as np

import uceclima
from uceclima.ui import servidor as SV, sitio_api
from uceclima import proyecto_sitio as PS, entregas as ENT

TMP = Path(tempfile.mkdtemp(prefix="uceclima_fase2b_"))
SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{SV.ESTADO.puerto}"


def post(r, c):
    q = urllib.request.Request(B + r, data=json.dumps(c).encode(), method="POST", headers={"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token})
    try:
        with urllib.request.urlopen(q, timeout=120) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())


def get(r):
    try:
        with urllib.request.urlopen(urllib.request.Request(B + r, headers={"X-UCECLIMA-TOKEN": SV.ESTADO.token}), timeout=120) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())


def _abierto(nombre, lon=-78.4678, lat=-0.1807):
    car = sitio_api.crear(nombre, lon, lat, base=str(TMP)); assert post("/api/proyecto/abrir", {"ruta": str(car)})[0] == 200
    return Path(car)


def test_r3_sufijo_ucec_y_lista():
    car = _abierto("quitocc")
    assert car.name == "quitoccucec" and (car / "proyecto_uceclima.json").exists()
    assert sitio_api.crear("otro ucec", -78.4, -0.2, base=str(TMP)).name == "otro_ucec"           # ya termina en ucec: no se duplica
    nombres = [p["nombre"] for p in PS.listar(TMP)]; assert "quitocc" in nombres


def test_r3_renombrar_sin_perder_historial():
    car = _abierto("renombrar")
    (car / "registro").mkdir(exist_ok=True); (car / "registro" / "algo.txt").write_text("historial", encoding="utf-8")
    c, r = post("/api/proyecto/renombrar", {"nombre": "Chalpi Grande"}); assert c == 200, r
    nueva = Path(r["carpeta"]); assert nueva.name == "chalpi_grandeucec" and not car.exists() and (nueva / "registro" / "algo.txt").exists()
    d = json.loads((nueva / "proyecto_uceclima.json").read_text(encoding="utf-8")); assert d["nombre"] == "Chalpi Grande" and d["procedencia"]["renombrado"][0]["antes"] == "renombrar"


def test_r2_cambiar_sitio_marca_desactualizadas_y_guarda_el_anterior():
    car = _abierto("sitio")
    for n in ("mdt_20260101_000000", "suelo_20260101_000000", "chirps_20260101_000000"):
        (car / "datos_descargados" / n).mkdir(parents=True)
    c, r = post("/api/proyecto/sitio", {"lon": "-78,0968", "lat": "-0.2998"}); assert c == 200, r
    d = json.loads((car / "proyecto_uceclima.json").read_text(encoding="utf-8"))
    assert d["ubicacion"] == "lon -78.0968, lat -0.2998" and d["procedencia"]["sitios_anteriores"][0]["lon"] == -78.4678
    assert set(r["descargas_desactualizadas"]) == {"mdt_20260101_000000", "suelo_20260101_000000"} and r["idf_desactualizada"]           # CHIRPS no depende del sitio
    cfg = json.loads((car / "config_climanet.json").read_text(encoding="utf-8")); assert abs(cfg["idf_inamhi"]["lon"] + 78.0968) < 1e-9
    assert get("/api/proyecto/desactualizadas")[1]["desactualizadas"]["sitio_nuevo"]["lat"] == -0.2998
    c, r = post("/api/proyecto/sitio", {"lon": "-60", "lat": "60"}); assert c == 400                       # Zeta Z1: fuera de la cobertura de CHIRPS (antes: fuera de Ecuador)


def test_r2_centrar_en_la_cuenca_activa():
    import geopandas as gpd, shapely.geometry as sg
    car = _abierto("centrar")
    shp = TMP / "chalpi.shp"; gpd.GeoDataFrame({"n": [1]}, geometry=[sg.Point(-78.0851, -0.3552).buffer(0.04, cap_style=3)], crs=4326).to_file(shp)
    assert post("/api/cuenca/shape", {"ruta": str(shp)})[0] == 200
    c, r = post("/api/proyecto/sitio", {"centrar_cuenca": True}); assert c == 200
    assert abs(r["sitio_nuevo"]["lon"] + 78.0851) < 0.01 and abs(r["sitio_nuevo"]["lat"] + 0.3552) < 0.01


def test_c5_salidas_aforo_por_la_api():
    _abierto("salidas", -78.0851, -0.3552)
    c, r = get("/api/cuenca/salidas"); assert c == 200 and any("H" in x["nombre"] for x in r["salidas"]), r


def test_c17_historial_de_registro_del_terreno_con_errores():
    _abierto("hist")
    c, r = post("/api/terreno/registrar", {"archivo": str(TMP / "no_existe.tif"), "tipo_terreno": "DSM", "datum": "no verificado"}); assert c == 400
    h = get("/api/terreno/historial")[1]["historial"]; assert h and h[0]["resultado"] == "error"


def test_c19_cn_para_la_2d_y_c23_punto_idf():
    car = _abierto("cn2d")
    c, r = post("/api/config", {"modulo": "corrida", "valores": {"cn_fuente": "calibrado"}}); assert c == 200
    c, r = post("/api/corrida/iniciar", {}); assert c in (400, 422)                                          # sin MDT o sin calibración aceptada: no corre
    c, r = get("/api/idf/x?punto=cuenca"); assert c == 400 and "cuenca" in r["error"]                          # sin cuenca activa lo dice


def test_c24_entrega_incluye_hidro_y_cuenca():
    import geopandas as gpd, shapely.geometry as sg
    car = _abierto("entrega")
    shp = TMP / "ent.shp"; gpd.GeoDataFrame({"n": [1]}, geometry=[sg.Point(-78.47, -0.18).buffer(0.02, cap_style=3)], crs=4326).to_file(shp)
    post("/api/cuenca/shape", {"ruta": str(shp)})
    (car / "observaciones").mkdir(); (car / "observaciones" / "aforos_caudal.csv").write_text("fecha,caudal_m3s,identidad_confirmada\n2020-01-01,1,si\n", encoding="utf-8")
    datos = json.loads((car / "proyecto_uceclima.json").read_text(encoding="utf-8"))
    raiz, man = ENT.construir(car, datos)
    rutas = [a["ruta"] for a in man["archivos"]]
    assert any(r.startswith("01_resultados/shapes/cuenca_activa/") for r in rutas) and any("hidro_calibracion/observaciones/aforos_caudal.csv" in r for r in rutas)


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=5, file=sys.stdout)
    SRV.shutdown(); shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
