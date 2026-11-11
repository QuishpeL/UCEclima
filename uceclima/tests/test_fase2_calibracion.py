# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Fase 2 · C12 (lluvia areal Thiessen/IDW), C13 (recesión del caudal base) y R4 (comparación de la calibración). Respuesta conocida, sin red.
Ejecutar: python -m uceclima.tests.test_fase2_calibracion"""
import json, shutil, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd

import uceclima
from uceclima import calibracion as K, cuenca as C, lluvia_areal as LA, calibracion_graficas as CG
from uceclima.tests.test_cuenca_calibracion import _proyecto, _proyecto_calibrable, X0, Y0, UTM, VERDAD

TMP = Path(tempfile.mkdtemp(prefix="uceclima_fase2_"))


def _cuenca_cuadrada(nombre):
    """Cuenca de 10 × 10 km y tres series del premódulo con coordenadas conocidas."""
    import geopandas as gpd, shapely.geometry as sg
    d, datos = _proyecto(nombre)
    shp = TMP / f"{nombre}.shp"
    gpd.GeoDataFrame({"n": [1]}, geometry=[sg.box(X0, Y0 - 10000, X0 + 10000, Y0)], crs=UTM).to_file(shp)
    C.cargar_shape(d, datos, shp)
    from pyproj import Transformer
    tf = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)
    dest = d / "datos" / "series_premodulo"; dest.mkdir(parents=True)
    fechas = pd.date_range("2010-01-01", periods=10)
    est = {"A": (X0 + 2500, Y0 - 5000, 10.0), "B": (X0 + 7500, Y0 - 2500, 20.0), "C": (X0 + 7500, Y0 - 7500, 40.0)}   # A cubre la mitad izquierda
    idx = []
    for k, (x, y, v) in est.items():
        lon, lat = tf.transform(x, y); vals = np.full(10, v)
        if k == "C":
            vals[3] = np.nan                                                                                         # día 4 sin C: Thiessen dinámico
        pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"), "valor": vals}).to_csv(dest / f"lluvia_{k}.csv", index=False)
        idx.append({"id": f"lluvia:{k}", "slug": f"lluvia_{k}", "nombre": k, "tipo": "lluvia", "archivo": f"lluvia_{k}.csv", "lon": lon, "lat": lat})
    (dest / "indice.json").write_text(json.dumps(idx), encoding="utf-8")
    return d, datos


def test_c12_thiessen_pesos_exactos_y_dinamico():
    d, datos = _cuenca_cuadrada("thiessen")
    s, pesos, info = LA.calcular(d, datos, "thiessen")
    w = dict(zip(pesos["estacion"], pesos["peso_con_todas"]))
    def malla(ests):                                                         # Thiessen por definición: cada punto a su estación más cercana
        gx, gy = np.meshgrid(np.linspace(125, 9875, 400), np.linspace(125, 9875, 400))
        P = {"A": (2500, 5000), "B": (7500, 7500), "C": (7500, 2500)}
        d = np.stack([np.hypot(gx - P[e][0], gy - P[e][1]) for e in ests]); k = d.argmin(0)
        return {e: float((k == i).mean()) for i, e in enumerate(ests)}
    m3 = malla("ABC"); m2 = malla("AB")
    assert all(abs(w[e] - m3[e]) < 0.005 for e in "ABC"), (w, m3)
    v = {"A": 10, "B": 20, "C": 40}
    assert abs(s.iloc[0] - sum(m3[e] * v[e] for e in "ABC")) < 0.15
    assert abs(s.iloc[3] - sum(m2[e] * v[e] for e in "AB")) < 0.15 and info["conjuntos_distintos"] == 2          # sin C: pesos de A y B recalculados
    act = LA.registrar(d, datos, "thiessen")
    p, msg = K.lluvia_cuenca(d); assert "areal" in msg and abs(p.iloc[0] - s.iloc[0]) < 1e-3 and act["tipo_registro"] == "areal"
    K.usar_lluvia(d, "chirps"); K.usar_lluvia(d, "areal"); assert "areal" in K.lluvia_cuenca(d)[1]
    si, _, _ = LA.calcular(d, datos, "idw"); assert 10 < si.iloc[0] < 40


def test_c13_recesion_k_conocido():
    k = 8.0; t = np.arange(60)
    q = pd.Series(50 * np.exp(-t / k), index=pd.date_range("2011-01-01", periods=60))
    r = K.k_recesion(q, pd.Series(0.0, index=q.index)); assert abs(r["k_dias"] - k) < 0.05, r
    b = K.caudal_base(10, 5, 24, 8.0); assert abs(b[0] - 10) < 1e-12 and abs(b[1] - 10 * np.exp(-1 / 8)) < 1e-9
    assert np.allclose(K.caudal_base(10, 5, 24, None), 10)


def test_r4_metricas_globales_coinciden_con_el_barrido():
    d, filas, _ = _proyecto_calibrable("r4")
    b = K.barrido(d, cn=(65, 85, 5), lag_h=(12, 36, 3), prf=(484, 284), lam=(0.2, 0.05), eventos_tabla=filas, k_rec=(None, 10.0))
    for combo in (b["mejores"][0], b["mejores"][7]):
        r = CG.comparar(d, b["barrido"], combo["id"])
        g = {x["metrica"]: x for x in r["globales"]}
        for m in ("KGE", "NSE", "PBIAS_pct"):
            for rol in ("ajuste", "validacion"):
                assert abs(g[m][rol] - combo[f"{m}_{rol}"]) < 1e-4, (m, rol, g[m][rol], combo[f"{m}_{rol}"])
        assert len(r["figuras"]) == 4 and len(r["por_evento"]) == 12
    car = d / r["carpeta"]
    assert all((car / f).exists() for f in ("metricas_por_evento.csv", "metricas_globales.csv", "sensibilidad.csv", "curva_duracion.csv", "balance_anual.csv", "1_hidrogramas_por_evento.png"))
    m0 = b["mejores"][0]; assert (m0["CN"], m0["lag_h"], m0["PRF"], m0["lambda"]) == VERDAD                     # sigue recuperando la verdad con k en el barrido


def test_r4_aviso_de_borde():
    d, filas, _ = _proyecto_calibrable("borde")
    b = K.barrido(d, cn=(55, 75, 3), lag_h=(24, 48, 2), prf=(484,), lam=(0.2,), eventos_tabla=filas)        # la verdad (CN 75, lag 24) queda en el borde
    r = CG.comparar(d, b["barrido"], b["mejores"][0]["id"]); assert r["borde"], r["borde"]
    a = K.aceptar(d, b["barrido"], b["mejores"][0]["id"], "Persona"); assert "BORDE" in a["etiqueta"]


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=5, file=sys.stdout)
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
