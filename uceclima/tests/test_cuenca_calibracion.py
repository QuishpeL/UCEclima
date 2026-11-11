# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Módulos 6 · Cuenca y 10 · Calibración humana: datos sintéticos de respuesta conocida, sin red.
Ejecutar: python -m uceclima.tests.test_cuenca_calibracion"""
import json, shutil, sys, tempfile, threading, time, traceback, urllib.request, urllib.error
from pathlib import Path
import numpy as np
import pandas as pd

import uceclima
from uceclima import cuenca as C, calibracion as K
from uceclima.ui import servidor as SV

TMP = Path(tempfile.mkdtemp(prefix="uceclima_cuenca_"))
UTM = "EPSG:32717"
X0, Y0, RES, N = 760000.0, 9710000.0, 30.0, 120                 # ráster sintético cerca de Mazar


def _proyecto(nombre):
    d = TMP / nombre; d.mkdir()
    datos = {"nombre": nombre, "tipo": "sintetico", "ubicacion": "lon -78.6450, lat -2.5850", "crs": UTM, "config_climanet": "config_climanet.json"}
    (d / "proyecto_uceclima.json").write_text(json.dumps(datos), encoding="utf-8")
    (d / "config_climanet.json").write_text(json.dumps({"aoi": [X0, X0 + N * RES, Y0 - N * RES, Y0]}), encoding="utf-8")
    return d, datos


def _mdt_valle(ruta):
    """Valle en V que drena al centro de la fila inferior: z = 2000 + 0,6·(filas desde abajo) + 1,5·|col − centro|."""
    import rasterio
    from rasterio.transform import from_origin
    f, c = np.mgrid[0:N, 0:N]
    z = 2000 + 0.6 * (N - 1 - f) + 1.5 * np.abs(c - N // 2)
    with rasterio.open(ruta, "w", driver="GTiff", height=N, width=N, count=1, dtype="float32", crs=UTM, transform=from_origin(X0, Y0, RES, RES)) as dst:
        dst.write(z.astype("float32"), 1)
    return ruta


def _poligono(ruta, crs=UTM, prj=True):
    import geopandas as gpd, shapely.geometry as sg
    g = gpd.GeoDataFrame({"n": [1, 2]}, geometry=[sg.box(X0, Y0 - 3000, X0 + 2000, Y0), sg.box(X0 + 2000, Y0 - 3000, X0 + 3000, Y0)], crs=crs)
    g.to_file(ruta)
    if not prj:
        Path(ruta).with_suffix(".prj").unlink()
    return ruta


# ------------------------------------------------------------------ cuenca
def test_shape_propio_se_valida_y_queda_activo():
    d, datos = _proyecto("shape")
    r = C.cargar_shape(d, datos, _poligono(TMP / "c.shp"))
    assert abs(r["area_km2"] - 9.0) < 1e-6 and r["activa"] and r["origen"] == "shape"                       # 2×3 + 1×3 km², unidos en un polígono
    assert any("2 polígonos" in a for a in r["avisos"])
    car = d / r["carpeta"]
    for f in ("cuenca_utm.shp", "cuenca_wgs84.shp", "cuenca.gpkg", "resumen.csv", "resumen.xlsx", "resumen.json"):
        assert (car / f).exists(), f
    assert C.estado(d)["activa"]["origen"] == "shape"


def test_shape_sin_crs_no_se_adivina():
    d, datos = _proyecto("sincrs")
    ruta = _poligono(TMP / "s.shp", prj=False)
    try:
        C.cargar_shape(d, datos, ruta); assert False
    except C.CuencaError as e:
        assert "CRS" in str(e)
    assert abs(C.cargar_shape(d, datos, ruta, crs_si_falta=UTM)["area_km2"] - 9.0) < 1e-6


def test_delineacion_valle_sintetico_y_aceptacion():
    d, datos = _proyecto("valle")
    mdt = _mdt_valle(TMP / "valle.tif")
    import geopandas as gpd, shapely.geometry as sg
    sal = gpd.GeoSeries([sg.Point(X0 + (N // 2 + 0.5) * RES, Y0 - (N - 1 + 0.5) * RES)], crs=UTM).to_crs(4326).iloc[0]
    r = C.delinear_mdt(d, datos, sal.x, sal.y, mdt=str(mdt), snap_m=60)
    total = N * N * RES * RES / 1e6                                              # con D8 por pendiente todo el valle drena a la salida
    assert abs(r["area_km2"] - total) < 1e-6, (r["area_km2"], total)
    assert r["toca_borde_mdt"] and any("RECORTADA" in a for a in r["avisos"])        # la cuenca llega al borde: se avisa
    assert r["activa"] is False and "SIN REVISAR" in r["etiqueta"]                # la delineación no se activa sola
    assert C.estado(d)["activa"] is None
    nombre = r["carpeta"].split("/")[-1]
    a = C.activar(d, nombre, "Persona Prueba")
    assert "ACEPTADA por Persona Prueba" in a["etiqueta"]
    assert (d / r["carpeta"] / "acumulacion_km2.tif").exists()
    assert C.mapa_png(d)[:4] == b"\x89PNG"


def test_delineacion_sobre_divisoria_o_fuera_falla_con_mensaje():
    d, datos = _proyecto("fuera")
    mdt = _mdt_valle(TMP / "valle2.tif")
    try:
        C.delinear_mdt(d, datos, -70.0, 0.0, mdt=str(mdt)); assert False
    except C.CuencaError as e:
        assert "fuera del MDT" in str(e)


def test_malla_chirps_alineada_a_005():
    d, datos = _proyecto("malla")
    r = C.malla_chirps(d, datos)
    import geopandas as gpd
    g = gpd.read_file(d / r["carpeta"] / "cuenca.gpkg").to_crs(4326)
    for geom in g.geometry:
        x0, y0, x1, y1 = geom.bounds
        for v in (x0, y0, x1, y1):
            assert abs(v / 0.05 - round(v / 0.05)) < 1e-6                        # bordes en múltiplos de 0,05°
    assert r["activa"] and "NO es una cuenca" in r["etiqueta"]
    d2, datos2 = _proyecto("malla2")
    C.cargar_shape(d2, datos2, _poligono(TMP / "c2.shp"))
    r2 = C.malla_chirps(d2, datos2)
    assert r2["activa"] is False and C.estado(d2)["activa"]["origen"] == "shape"    # no reemplaza una cuenca ya activa
    assert r2["referencia"] == "cuenca activa"


# ------------------------------------------------------------------ calibración
VERDAD = (75.0, 24.0, 484.0, 0.2)


def _proyecto_calibrable(nombre, tipo="afluente_embalse", confirmado=True):
    d, datos = _proyecto(nombre)
    C.cargar_shape(d, datos, _poligono(TMP / f"{nombre}.shp"))
    area = 9.0
    dias = pd.date_range("2015-01-01", "2016-12-31")
    p = pd.Series(0.0, index=dias); q = pd.Series(5.0, index=dias)
    rng = np.random.default_rng(7); filas = []
    for k, ini in enumerate(pd.date_range("2015-01-10", periods=12, freq="50D")):
        fin = ini + pd.Timedelta(days=25)
        lluvia = np.zeros(26); lluvia[1:6] = rng.uniform(15, 45, 5)              # día 0 seco: el caudal base es el inicial
        p[ini:fin] = lluvia
        q[ini:fin] = K.simular_evento(lluvia, 5.0, area, *VERDAD, 24.0)
        filas.append({"evento": f"E{k + 1:02d}", "inicio": str(ini.date()), "pico": str((ini + pd.Timedelta(days=3)).date()), "fin": str(fin.date()), "rol": "validacion" if k % 3 == 2 else "ajuste"})
    ch = d / "datos_descargados" / "chirps_cuenca_20200101_000000"; ch.mkdir(parents=True)
    pd.DataFrame({"fecha": dias.strftime("%Y-%m-%d"), "lluvia_cuenca_mm": p.values}).to_csv(ch / "chirps_cuenca_diario.csv", index=False)
    (ch / "estado.json").write_text(json.dumps({"estado": "completado"}), encoding="utf-8")
    obs = TMP / f"{nombre}_q.csv"; pd.DataFrame({"Fecha": dias.strftime("%Y-%m-%d"), "Q": q.values}).to_csv(obs, index=False)
    reg = K.registrar_observacion(d, obs, "Fecha", "Q", tipo, "Sintética", "Punto prueba", confirmado=confirmado, persona="Prueba")
    return d, filas, reg


def test_barrido_recupera_parametros_conocidos_y_separa_validacion():
    d, filas, reg = _proyecto_calibrable("cal")
    assert reg["identidad_confirmada"] == "si"
    b = K.barrido(d, cn=(65, 85, 5), lag_h=(12, 36, 3), prf=(484, 284), lam=(0.2, 0.05), eventos_tabla=filas, persona="Prueba")
    m = b["mejores"][0]
    assert (m["CN"], m["lag_h"], m["PRF"], m["lambda"]) == VERDAD, m
    assert m["NSE_ajuste"] > 0.999 and m["NSE_validacion"] > 0.999 and m["n_eventos_validacion"] == 4 and m["n_eventos_ajuste"] == 8
    car = d / "calibracion" / "barridos" / b["barrido"]
    assert all((car / f).exists() for f in ("resultados.csv", "resultados.xlsx", "eventos.csv", "config.json"))
    assert K.figura(d, b["barrido"], 0)[:4] == b"\x89PNG"
    try:
        K.aceptar(d, b["barrido"], 0, ""); assert False
    except K.CalibracionError:
        pass
    a = K.aceptar(d, b["barrido"], 0, "Persona Prueba", "caso sintético")
    assert a["favorable"] and "aceptada por Persona Prueba" in a["etiqueta"]
    assert K.estado(d)["etiqueta"] == a["etiqueta"]
    peor = b["mejores"][-1]
    a2 = K.aceptar(d, b["barrido"], peor["id"], "Persona Prueba")                                   # aceptar no sobrescribe la anterior
    assert len(list((d / "calibracion" / "aceptadas").glob("aceptada_*"))) == 2


def test_validacion_desfavorable_se_rotula():
    d, filas, _ = _proyecto_calibrable("desf")
    b = K.barrido(d, cn=(40, 40, 1), lag_h=(200, 200, 1), prf=(100,), lam=(0.5,), eventos_tabla=filas)
    a = K.aceptar(d, b["barrido"], 0, "Persona Prueba")
    assert not a["favorable"] and "DESFAVORABLE" in a["etiqueta"]


def test_sin_confirmar_o_salida_de_embalse_no_calibra():
    d, filas, reg = _proyecto_calibrable("nocf", confirmado=False)
    assert reg["identidad_confirmada"] == "no" and reg["avisos"]
    try:
        K.barrido(d, eventos_tabla=filas); assert False
    except K.CalibracionError as e:
        assert "identidad" in str(e)
    d2, filas2, reg2 = _proyecto_calibrable("salida", tipo="salida_embalse", confirmado=True)
    assert reg2["identidad_confirmada"] == "no" and "no es apto" in reg2["avisos"][0]


def test_sin_validacion_o_con_malla_no_calibra():
    d, filas, _ = _proyecto_calibrable("sinval")
    try:
        K.barrido(d, eventos_tabla=[{**f, "rol": "ajuste"} for f in filas]); assert False
    except K.CalibracionError as e:
        assert "VALIDACIÓN" in str(e)
    d2, datos2 = _proyecto("solomalla"); C.malla_chirps(d2, datos2)
    (d2 / "observaciones").mkdir()
    pd.DataFrame({"fecha": ["2015-01-01"], "caudal_m3s": [1.0], "identidad_confirmada": ["si"]}).to_csv(d2 / "observaciones" / "aforos_caudal.csv", index=False)
    ch = d2 / "datos_descargados" / "chirps_cuenca_20200101_000000"; ch.mkdir(parents=True)
    pd.DataFrame({"fecha": ["2015-01-01"], "lluvia_cuenca_mm": [1.0]}).to_csv(ch / "chirps_cuenca_diario.csv", index=False); (ch / "estado.json").write_text('{"estado":"completado"}')
    try:
        K.barrido(d2); assert False
    except K.CalibracionError as e:
        assert "malla" in str(e)


def test_registrar_de_nuevo_guarda_copia_bak():
    d, _, _ = _proyecto_calibrable("bak")
    time.sleep(1.1)
    f = next((d / "observaciones" / "originales").iterdir())
    K.registrar_observacion(d, f, "Fecha", "Q", "afluente_embalse", "Sintética", "Punto", confirmado=True, persona="P", umbral_sospechoso=1e9)
    assert len(list((d / "observaciones").glob("aforos_caudal.csv.bak_*"))) == 1
    assert len(json.loads((d / "observaciones" / "registro_observaciones.json").read_text(encoding="utf-8"))) == 2


def test_lluvia_de_estacion_reemplaza_chirps_y_el_balance_avisa():
    d, filas, _ = _proyecto_calibrable("est")
    p, m = K.lluvia_cuenca(d); assert m.startswith("CHIRPS")
    f = TMP / "est_lluvia.csv"
    pd.DataFrame({"fecha": p.index.strftime("%Y-%m-%d"), "estacion": "M9999", "mm": p.values * 0.1}).to_csv(f, index=False, encoding="utf-8-sig")
    a = K.registrar_lluvia(d, f, "fecha", "mm", "M9999", "Sintética", col_estacion="estacion")
    assert a["fuente"] == "estacion" and "PUNTUAL" in a["aviso"]
    p2, m2 = K.lluvia_cuenca(d); assert "M9999" in m2 and abs(p2.sum() - 0.1 * p.sum()) < 1e-6
    b = K.barrido(d, cn=(75, 75, 1), lag_h=(24, 24, 1), prf=(484,), lam=(0.2,), eventos_tabla=filas)
    assert b["balance_anual"]["coef_escorrentia"] > 1 and any("BALANCE IMPOSIBLE" in x for x in b["avisos"])      # lluvia ×0,1: el balance no cierra
    K.usar_lluvia(d, "chirps"); assert K.lluvia_cuenca(d)[1].startswith("CHIRPS")
    try:
        K.usar_lluvia(d, "otra"); assert False
    except K.CalibracionError:
        pass


# ------------------------------------------------------------------ rutas del servidor
def test_rutas_cuenca_y_calibracion():
    SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
    B = f"http://127.0.0.1:{SV.ESTADO.puerto}"

    def get(r):
        try:
            with urllib.request.urlopen(B + r, timeout=60) as x: return x.status, x.read()
        except urllib.error.HTTPError as e: return e.code, e.read()

    def post(r, c):
        q = urllib.request.Request(B + r, data=json.dumps(c).encode(), method="POST", headers={"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token})
        try:
            with urllib.request.urlopen(q, timeout=120) as x: return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    try:
        mods = {m["id"] for m in json.loads(get("/api/estado")[1])["modulos"]}
        assert "hidro" in mods and not ({"cuenca", "calibracion", "hidrologia", "cuencas"} & mods)
        orig = Path(uceclima.__file__).parent / "proyectos" / "mazar"; copia = TMP / "mazar_api"
        shutil.copytree(orig, copia, ignore=shutil.ignore_patterns("resultados", "cmip6_*", "chirps_*"))
        assert post("/api/proyecto/abrir", {"ruta": str(copia)})[0] == 200
        c, e = get("/api/cuenca/estado"); assert c == 200
        c, r = post("/api/cuenca/shape", {"ruta": str(_poligono(TMP / "api.shp"))}); assert c == 200 and abs(r["area_km2"] - 9) < 1e-6, r
        c, png = get("/api/cuenca/mapa.png"); assert c == 200 and png[:4] == b"\x89PNG"
        c, r = post("/api/cuenca/malla", {}); assert c == 200 and r["activa"] is False
        c, r = post("/api/cuenca/activar", {"nombre": "../../x"}); assert c == 400
        c, k = get("/api/calibracion/estado"); k = json.loads(k); assert c == 200 and k["etiqueta"] == "SIMULACIÓN SIN CALIBRAR"
        c, r = post("/api/calibracion/barrido", {}); assert c == 400                    # sin observaciones confirmadas
        c, r = get("/api/calibracion/figura.png?barrido=../x&id=0"); assert c == 400
    finally:
        SRV.shutdown()


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=4, file=sys.stdout)
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
