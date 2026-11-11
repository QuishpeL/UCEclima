# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""¿El MDT subido coincide con la zona de trabajo y con el terreno regional de Earth Engine? GeoTIFF sintético en EPSG:32717 alrededor del sitio. Ejecutar: python -m uceclima.tests.test_terreno_coincidencia"""
import json, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform

from uceclima import terreno_import as T

CRS = "EPSG:32717"
LON, LAT = -78.645, -2.585


class _Estado:
    def __init__(self, carpeta, aoi):
        self.carpeta = str(carpeta); self.datos = {"crs": CRS, "ubicacion": f"lon {LON:.4f}, lat {LAT:.4f}", "config_climanet": "config_climanet.json"}
        (Path(carpeta) / "config_climanet.json").write_text(json.dumps({"aoi": aoi}), encoding="utf-8")


def _sitio():
    x, y = transform("EPSG:4326", CRS, [LON], [LAT]); return float(x[0]), float(y[0])


def _tif(ruta, x0, y0, ancho_m, alto_m, res=10.0):
    w, h = int(ancho_m / res), int(alto_m / res)
    with rasterio.open(ruta, "w", driver="GTiff", width=w, height=h, count=1, dtype="float32", crs=CRS, transform=from_origin(x0, y0 + alto_m, res, res)) as d:
        d.write((np.random.default_rng(0).random((h, w)) * 5 + 2000).astype("float32"), 1)


def _caso(dx=0.0, dy=0.0, lado=2000.0, gee=True):
    t = tempfile.TemporaryDirectory(); c = Path(t.name); sx, sy = _sitio()
    if gee:
        (c / "datos_descargados" / "sitio_1" / "mdt").mkdir(parents=True); _tif(c / "datos_descargados" / "sitio_1" / "mdt" / "mdt_glo30.tif", sx - 20000, sy - 20000, 40000, 40000, 100.0)
    aoi = [sx - 300, sx + 300, sy - 300, sy + 300]; est = _Estado(c, aoi)
    f = c / "dron.tif"; _tif(f, sx - lado / 2 + dx, sy - lado / 2 + dy, lado, lado); return t, est, T.inspeccionar(str(f))


def test_mdt_centrado_en_el_sitio_coincide_y_se_superpone_a_gee():
    t, est, ins = _caso(); r = T.coincidencia(ins, est)
    assert r["veredicto"] == "coincide" and r["contiene_sitio"] and r["distancia_al_sitio_km"] == 0 and r["cobertura_aoi_pct"] == 100 and r["mdt_dentro_gee_pct"] == 100 and "superpone" in r["base_gee"]
    t.cleanup()


def test_mdt_a_200_km_no_coincide_y_sugiere_zona_utm():
    t, est, ins = _caso(dx=200000.0); r = T.coincidencia(ins, est)
    assert r["veredicto"] == "no_coincide" and not r["contiene_sitio"] and 150 < r["distancia_al_sitio_km"] < 250 and any("zona UTM" in p for p in r["pistas"])
    assert r["mdt_dentro_gee_pct"] == 0 and "No se superpone" in r["base_gee"]
    t.cleanup()


def test_mdt_que_cubre_solo_una_parte_es_parcial():
    t, est, ins = _caso(dx=1150.0, lado=1500.0); r = T.coincidencia(ins, est)                        # el borde oeste del MDT queda a ~400 m al este del sitio: cubre parte del AOI, no el sitio
    assert r["veredicto"] in ("parcial", "no_coincide") and (r["cobertura_aoi_pct"] or 0) < 95
    t.cleanup()


def test_sin_terreno_regional_no_inventa_comparacion():
    t, est, ins = _caso(gee=False); r = T.coincidencia(ins, est)
    assert r["gee"] is None and r["mdt_dentro_gee_pct"] is None and "No hay terreno regional" in r["base_gee"] and r["veredicto"] == "coincide"
    t.cleanup()


def test_aoi_por_defecto_se_ajusta_dentro_del_raster_si_el_sitio_esta_en_el_borde():
    e = {"x0": 0.0, "x1": 1000.0, "y0": 0.0, "y1": 1000.0}
    a = T._ajustar([-100.0, 500.0, 200.0, 800.0], e); assert T.aoi_en_extension(a, e) and abs((a[1] - a[0]) - 600) < 1e-9 and abs((a[3] - a[2]) - 600) < 1e-9
    assert T._ajustar([300, 900, 300, 900], e) == [300, 900, 300, 900] or T.aoi_en_extension(T._ajustar([300, 900, 300, 900], e), e)


if __name__ == "__main__":
    fallos = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except Exception:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=4, file=sys.stdout)
    sys.exit(1 if fallos else 0)
