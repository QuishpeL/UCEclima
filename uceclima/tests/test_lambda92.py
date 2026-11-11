# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Pruebas de Lambda 9.2.0: ícono de conexión, JSON sin NaN, cuencas externas automáticas y entradas GEOGLOWS (río grande sin datos).
Sin internet ni Earth Engine: el MDT amplio es sintético, el CN se fija dentro de la prueba y la serie GEOGLOWS es inventada.
Ejecutar: python -m uceclima.tests.test_lambda92"""
import json, math, sys, tempfile, threading, time, traceback, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import uceclima
from uceclima import externas_auto as XA
from uceclima.ui import servidor as SV, demo
from climanet import entradas_geoglows as EG

TMP = Path(tempfile.mkdtemp(prefix="uceclima_lambda92_"))
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
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def esperar_descarga(did, maximo_s=300):
    for _ in range(maximo_s * 2):
        l = next((d for d in get("/api/descargas")["descargas"] if d["id"] == did), None)
        if l and l["estado"] != "en_curso":
            return l
        time.sleep(0.5)
    raise AssertionError("la tarea no terminó")


def esperar_corrida(rid, maximo_s=900):
    for _ in range(maximo_s):
        e = get("/api/corrida/estado?id=" + rid)
        if e["estado"] != "en_curso":
            break
        time.sleep(1)
    for _ in range(100):
        if not get("/api/estado")["corrida_activa"]: break
        time.sleep(0.2)
    return e


def serie_geoglows_inventada(anios=30, semilla=7):
    """Serie horaria INVENTADA (no es GEOGLOWS): base 10 m3/s y una crecida triangular por año con pico conocido."""
    rng = np.random.default_rng(semilla)
    t = pd.date_range("1990-01-01", periods=anios * 365 * 24, freq="h"); q = np.full(len(t), 10.0); picos = 60 + 25 * rng.gumbel(size=anios)
    for k, p in enumerate(picos):
        i = k * 365 * 24 + 4000; sube = np.linspace(0, 1, 13); baja = np.linspace(1, 0, 25)[1:]
        q[i - 12:i + 25] = 10 + (p - 10) * np.r_[sube, baja]
    return t, q, picos


def test_version_marca_e_icono_de_conexion():
    assert uceclima.__version__ == "9.2.0-lambda"
    html = get("/").decode("utf-8")
    assert "Versión 9.2" in html and 'id="conexion"' in html and "externas.js" in html
    assert 'role="alert"' not in html.split('<div id="desconexion"')[1].split(">")[0], "la tarjeta ya no es una alerta que tapa la pantalla"


def test_licencia_cc_by_nc_en_todos_los_encabezados():
    raiz = Path(uceclima.__file__).parents[1]
    gpl = [str(f) for f in list(raiz.joinpath("uceclima").rglob("*.py")) + list(raiz.joinpath("climanet").rglob("*.py")) + list(ESTATICOS.glob("*.js"))
           if f.name != "test_lambda92.py" and "GPL" in f.read_text(encoding="utf-8", errors="replace")]
    assert not gpl, gpl
    assert "CC BY-NC 4.0" in (raiz / "uceclima" / "externas_auto.py").read_text(encoding="utf-8")


def test_json_sin_nan_ni_infinito():
    o = {"a": float("nan"), "b": [1.0, float("inf"), np.float64("nan"), np.float32(2.5)], "c": np.array([1.0, np.nan]), "d": "texto"}
    s = json.dumps(SV._sin_nan(o), allow_nan=False, default=str)
    assert json.loads(s) == {"a": None, "b": [1.0, None, None, 2.5], "c": [1.0, None], "d": "texto"}


def test_gumbel_tabla_y_forma_media():
    t, q, picos = serie_geoglows_inventada()
    a = EG.analizar_serie(t.values, q)
    assert a["gumbel"]["n_anios"] == 30 and abs(a["gumbel"]["media"] - picos.mean()) < 1e-6
    tab = [a["tabla_tr_m3s"][k] for k in ("2", "5", "10", "25", "50", "100")]; assert all(x < y for x, y in zip(tab, tab[1:])), tab
    k = -math.sqrt(6) / math.pi * (EG.EULER + math.log(math.log(100 / 99))); assert abs(a["tabla_tr_m3s"]["100"] - round(picos.mean() + k * picos.std(ddof=1), 2)) < 0.02
    f = a["forma"]; assert f["n_crecidas"] == 30 and f["q_rel"][EG.VENTANA_SUBIDA_H] == 1.0 and max(f["q_rel"]) <= 1.0 + 1e-9


def test_hidrograma_geoglows_pico_en_la_tormenta_y_cierre_en_cero():
    t, q, _ = serie_geoglows_inventada(); a = EG.analizar_serie(t.values, q)
    e = {"nombre": "rio", "gumbel": a["gumbel"], "forma": a["forma"]}
    ts, qs, inf = EG.hidrograma(e, 25, 3600.0, 6 * 3600)
    assert ts[0] == 0 and qs[-1] == 0 and np.all(np.diff(ts) > 0) and np.all(qs >= 0) and ts[-1] <= 6 * 3600
    assert abs(qs.max() - EG.caudal_tr(a["gumbel"], 25)) < 1e-6 and abs(ts[int(np.argmax(qs))] - 3600.0) <= 300 and inf["Tr"] == 25 and not inf["extrapolado"]
    assert EG.hidrograma(e, 100, 3600.0, 6 * 3600)[2]["extrapolado"]                         # 30 años de serie: Tr 100 es extrapolación y se dice
    try:
        EG.hidrograma(e, None, 3600.0, 6 * 3600); raise AssertionError("un evento observado no tiene Tr")
    except ValueError as ex:
        assert "DISEÑO" in str(ex)


def _mdt_amplio_sintetico(carpeta):
    """MDT amplio INVENTADO (90 m, ±6 km) alrededor del área 2D del proyecto sintético: plano hacia el sur con un valle en x = 500 300 que entra por el norte."""
    import rasterio
    from rasterio.transform import from_origin
    res = 90.0; x0, y1 = 500300 - 6000, 9760300 + 6000; n = int(12000 / res)
    X = x0 + (np.arange(n) + .5) * res; Y = y1 - (np.arange(n) + .5) * res; XX, YY = np.meshgrid(X, Y)
    z = 2500 + 0.03 * (YY - 9760300) + 0.08 * np.abs(XX - 500300)
    d = carpeta / "datos_descargados" / f"mdt_cuenca_{datetime.now():%Y%m%d_%H%M%S}"; d.mkdir(parents=True)
    with rasterio.open(d / "mdt_cuenca_sintetico_90m.tif", "w", driver="GTiff", height=n, width=n, count=1, dtype="float32", crs="EPSG:32717", transform=from_origin(x0, y1, res, res), nodata=-9999) as s:
        s.write(z.astype("float32"), 1)
    (d / "estado.json").write_text(json.dumps({"estado": "completado"}), encoding="utf-8")


def test_cuencas_externas_automaticas_y_entrada_geoglows_en_una_corrida():
    c = demo.crear_sintetico(TMP / "sint_ext"); code, _ = post("/api/proyecto/abrir", {"ruta": str(c)}); assert code == 200
    x = get("/api/corrida/externas"); assert x["mdt_amplio"] is None and x["centro_lonlat"] and not x["detecciones"]
    _mdt_amplio_sintetico(c)
    XA._cn_cuencas = lambda destino, chicas, crs, progreso: ({int(i): 70.0 for i in chicas.id}, {int(i): 100.0 for i in chicas.id})   # sin Earth Engine en la prueba
    code, j = post("/api/descargas/iniciar", {"fuente": "externas", "parametros": {"area_min_km2": 1, "area_max_km2": 5000}}); assert code == 200, j
    l = esperar_descarga(j["descarga"]); assert l["estado"] == "completado", l
    x = get("/api/corrida/externas"); det = x["detecciones"][0]; cs = det["cuencas"]
    assert cs and all(cc["tipo"] == "chica" and cc["cn"] == 70.0 and cc["lag_h"] > 0 for cc in cs), cs
    principal = max(cs, key=lambda cc: cc["area_km2"]); assert principal["area_km2"] > 10, cs                  # el valle del norte
    aoi = x["aoi"]; assert aoi[0] <= principal["entrada_xy"][0] <= aoi[1] and aoi[2] <= principal["entrada_xy"][1] <= aoi[3]
    ids = [principal["id"]]
    code, e = post("/api/corrida/externas_registrar", {"deteccion": det["id"], "ids": ids})
    if not principal["en_cauce"]:
        assert code == 400 and "bajo mi responsabilidad" in e["error"], e                                      # no se salta la comprobación sin la decisión de la persona
        code, e = post("/api/corrida/externas_registrar", {"deteccion": det["id"], "ids": ids, "permitir_fuera_de_cauce": True})
    assert code == 200 and len(e["cuencas_externas"]) == 1 and "detección automática" in e["cuencas_externas"][0]["fuente"], e
    assert (c / e["cuencas_externas"][0]["shp"]).exists()
    # entrada GEOGLOWS con un análisis INVENTADO (misma estructura que el real), en el borde oeste del área 2D
    t, q, _ = serie_geoglows_inventada(); a = EG.analizar_serie(t.values, q)
    d = c / "datos_descargados" / f"geoglows_entrada_{datetime.now():%Y%m%d_%H%M%S}"; d.mkdir(parents=True)
    xy = [aoi[0] + 15.0, (aoi[2] + aoi[3]) / 2]
    (d / "analisis_geoglows.json").write_text(json.dumps({"entradas": [{"nombre": "rio_oeste", "xy": xy, "lonlat": [0, 0], "river_id": 1, "origen_tramo": "prueba", "candidatos": [], **a}]}), encoding="utf-8")
    (d / "estado.json").write_text(json.dumps({"estado": "completado"}), encoding="utf-8")
    code, g = post("/api/corrida/entradas_geoglows", {"analisis": d.name}); assert code == 200 and g["entradas_geoglows"][0]["nombre"] == "rio_oeste", g
    assert get("/api/corrida/externas")["entradas_geoglows"][0]["river_id"] == 1
    code, v = post("/api/verificar"); assert v["puede_ejecutar"], v
    code, r = post("/api/corrida/iniciar", {"tr": 25}); assert code == 200, r
    est = esperar_corrida(r["id"]); assert est["estado"] == "completado", est
    res = get("/api/corrida/resultado?id=" + r["id"])["resumen"]
    eg = res["entradas_geoglows"][0]; assert eg["Tr"] == 25 and abs(eg["pico_m3s"] - round(EG.caudal_tr(a["gumbel"], 25), 2)) < 0.01, eg
    assert res["cuencas_externas"] and res["cuencas_externas"][0]["volumen_m3"] > 0 and "rio_oeste" in res["entradas"], res.get("entradas")
    # módulo 13 · visor de partículas sobre esta misma corrida
    p = get("/api/particulas/datos?id=" + r["id"]); assert "error" not in p, p
    assert p["nf"] > 1 and p["nc"] > 0 and p["corrida"] == r["id"], p
    cm = p["control"]; assert 0.9 * cm["max_hmax_tif_m"] <= cm["max_fotos_m"] <= cm["max_hmax_tif_m"] + 0.001, cm   # fotos cada 5 min: el pico entre fotos puede ser algo mayor
    assert p["hieto"] and len(p["hieto"]["lluvia_mm"]) > 1 and abs(sum(p["hieto"]["lluvia_mm"]) - res["P_total_mm"]) < 0.5
    assert "error" in get("/api/particulas/datos?id=..%2Fotra") and "error" in get("/api/particulas/datos?id=no_existe")
    html = get("/static/particulas.html").decode("utf-8"); assert "/api/particulas/datos" in html and "data.js" not in html and "hietoU" in html
    code, e = post("/api/corrida/entradas_geoglows", {"quitar": True}); assert code == 200 and not get("/api/corrida/externas")["entradas_geoglows"]
    code, e = post("/api/corrida/externas_registrar", {"quitar": True}); assert code == 200 and not get("/api/corrida/externas")["cuencas_externas"]


def test_registrar_grande_con_scs_se_rechaza():
    c = TMP / "falso"; d = c / "datos_descargados" / "externas_20260101_000000"; d.mkdir(parents=True)
    (d / "propuesta.json").write_text(json.dumps({"cuencas": [{"id": 1, "nombre": "E1", "tipo": "grande", "area_km2": 500.0, "en_cauce": True}]}), encoding="utf-8")
    import geopandas as gpd, shapely.geometry as sg
    gpd.GeoDataFrame({"id": [1]}, geometry=[sg.box(0, 0, 1, 1)], crs=32717).to_file(d / "cuencas_externas_detectadas.gpkg", driver="GPKG")
    try:
        XA.registrar_externas(c, {}, d.name, [1]); raise AssertionError("una cuenca grande no va con SCS-CN")
    except ValueError as ex:
        assert "GEOGLOWS" in str(ex)


if __name__ == "__main__":
    fallos = 0
    for nombre, f in sorted(globals().items()):
        if nombre.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", nombre)
            except BaseException:
                fallos += 1; print("FALLA", nombre); traceback.print_exc()
    SRV.shutdown(); sys.exit(1 if fallos else 0)
