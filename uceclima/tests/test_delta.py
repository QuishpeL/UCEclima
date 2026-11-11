# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Delta · D1 recesión k en el barrido, D2 paso horario, D3 humedad antecedente, D4 control de lluvia, D5 benchmark y D6 (G5, G8, G10, G11, G22).
Respuesta conocida, sin red. Ejecutar: python -m uceclima.tests.test_delta  (desde UCEclima)"""
import json, shutil, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd

from uceclima import calibracion as K, benchmark as BM, cuenca as C, proyecto_sitio as PS
from uceclima.tests.test_cuenca_calibracion import _proyecto_calibrable, VERDAD

TMP = Path(tempfile.mkdtemp(prefix="uceclima_delta_"))


def test_d0_por_defecto_igual_que_gamma():
    d, filas, _ = _proyecto_calibrable("d0")
    a = K.barrido(d, cn=(65, 85, 5), lag_h=(12, 36, 3), prf=(484,), lam=(0.2,), eventos_tabla=filas)
    b = K.barrido(d, cn=(65, 85, 5), lag_h=(12, 36, 3), prf=(484,), lam=(0.2,), eventos_tabla=filas, k_rec=(None,), humedad=("ninguna",))
    for x, y in zip(a["mejores"], b["mejores"]):
        assert abs(x["KGE_ajuste"] - y["KGE_ajuste"]) < 1e-12 and (x.get("humedad") or "ninguna") == "ninguna"
    assert a["dt_h"] == 24.0 and a["mejores"][0]["CN"] == VERDAD[0]


def test_d1_k_auto_y_efecto_en_nse():
    d, filas, _ = _proyecto_calibrable("d1")
    b = K.barrido(d, cn=(75, 75, 1), lag_h=(24, 24, 1), prf=(484,), lam=(0.2,), eventos_tabla=filas, k_rec="auto")
    ks = {m["k_rec_d"] for m in b["mejores"]}
    assert None in ks and len(ks) >= 2, ks                                                  # constante + k estimados
    assert b["efecto_recesion"] is not None and any("recesi" in a.lower() for a in b["avisos"]), b["avisos"]


def test_d2_paso_horario_detectado():
    i = pd.date_range("2020-01-01", periods=200, freq="h")
    assert K.detectar_paso(pd.Series(1.0, i), pd.Series(0.0, i)) == 1.0
    j = pd.date_range("2020-01-01", periods=200, freq="D")
    assert K.detectar_paso(pd.Series(1.0, j), pd.Series(0.0, i)) == 24.0
    q = pd.Series(1.0, i); q.iloc[100:110] = [3, 6, 9, 7, 5, 4, 3, 2, 1.5, 1.2]
    ev = K.eventos(q, pd.Series(0.5, i), percentil=95, dias_antes=1, dias_despues=2, separacion_dias=3)
    assert ev["criterios"]["paso_h"] == 1.0, ev["criterios"]


def test_d3_amc_conversiones_y_umbrales():
    assert abs(K.cn_amc(75, "I") - 75 / (2.281 - 0.01281 * 75)) < 1e-12 and abs(K.cn_amc(75, "III") - 75 / (0.427 + 0.00573 * 75)) < 1e-12
    assert K.cn_efectivo(75, {"p_ant5_mm": 10}, "amc5") < 75 < K.cn_efectivo(75, {"p_ant5_mm": 60}, "amc5")
    assert K.cn_efectivo(75, {"p_ant5_mm": 40}, "amc5") == 75 and K.cn_efectivo(75, {}, "amc5") == 75 and K.cn_efectivo(75, {}, "ninguna") == 75
    assert abs(K.cn_efectivo(75, {"api_mm": 35.6}, "api") - 75) < 1e-9
    d, filas, _ = _proyecto_calibrable("d3")
    b = K.barrido(d, cn=(75, 75, 1), lag_h=(24, 24, 1), prf=(484,), lam=(0.2,), eventos_tabla=filas, humedad=("ninguna", "amc5", "api"))
    assert {m["humedad"] for m in b["mejores"]} == {"ninguna", "amc5", "api"} and b["efecto_humedad"]


def test_d4_lluvia_dudosa():
    i = pd.date_range("2015-01-01", periods=120, freq="D")
    q = pd.Series(1.0, i); q.iloc[50:56] = [20, 60, 40, 20, 10, 5]                         # ≈ 13 mm de escorrentía directa en 9 km²
    p = pd.Series(0.0, i); p.iloc[49:51] = 2.0                                             # 4 mm de lluvia
    ev = K.eventos(q, p, percentil=95, dias_antes=5, dias_despues=10, separacion_dias=20, area_km2=9.0)
    assert any(f.get("lluvia_dudosa") for f in ev["eventos"]), ev["eventos"]


def test_d5_benchmark_pide_etp_y_etiqueta():
    d, filas, _ = _proyecto_calibrable("d5")
    b = K.barrido(d, cn=(70, 80, 3), lag_h=(24, 24, 1), prf=(484,), lam=(0.2,), eventos_tabla=filas)
    try:
        BM.correr(d, None, b["barrido"], 0); assert False, "sin ETP no debe correr"
    except K.CalibracionError as e:
        assert "no la inventa" in str(e)
    r = BM.correr(d, 3.0, b["barrido"], 0, maxiter=3)
    assert r["etiqueta"] == "referencia de comparación, no calibrada por la persona" and len(r["tabla"]) == 3
    assert [t["tipo"] for t in r["tabla"]][1:] == [BM.ETIQUETA] * 2 and (d / r["carpeta"] / "benchmark.csv").exists()
    E = np.full(91, 2.0); q0 = BM.gr4j(np.zeros(91), E, 300, 0, 80, 1.7); q = BM.gr4j(np.r_[np.zeros(30), 50, np.zeros(60)], E, 300, 0, 80, 1.7)
    assert np.all(q >= 0) and np.allclose(q[:30], q0[:30]) and (q - q0)[30:].sum() > 0                    # el pulso de lluvia solo suma caudal después


def test_g22_saltos_de_unidad():
    i = pd.date_range("2014-01-01", "2017-12-31")
    q = pd.Series(np.where(i.year < 2016, 0.3, 280.0), i)                                  # m³/s y luego L/s
    av = K.saltos_de_unidad(q); assert len(av) == 1 and "2015 y 2016" in av[0], av
    assert K.saltos_de_unidad(pd.Series(np.where(i.year < 2016, 0.3, 0.5), i)) == []


def test_g8_puerto_exclusivo():
    from uceclima.ui import servidor as SV
    a = SV.crear_servidor(0); p = a.server_address[1]
    try:
        SV.crear_servidor(p).server_close(); assert False, "dos servidores en el mismo puerto"
    except OSError:
        pass
    finally:
        a.server_close()


def test_g10_contraste_area_mas_parecida():
    import geopandas as gpd, shapely.geometry as sg
    r = gpd.GeoDataFrame({"REACH_ID": [1, 2], "UPLAND_SKM": [345.0, 98.7], "DIS_AV_CMS": [9.0, 3.0]},
                         geometry=[sg.LineString([(-78.20, -0.30), (-78.20, -0.31)]), sg.LineString([(-78.201, -0.30), (-78.201, -0.31)])], crs=4326)
    f = TMP / "rios.gpkg"; r.to_file(f)
    c = C.contraste_hydrosheds(f, (-78.2005, -0.305), 99.07); assert c["reach_id"] == 2, c


def test_g11_descarga_de_cuenca_no_se_marca():
    a = TMP / "mdt_cuenca_20260101_000000"; a.mkdir(); (a / "estado.json").write_text(json.dumps({"parametros": {"ambito": "cuenca"}}), encoding="utf-8")
    b = TMP / "mdt_20260101_000001"; b.mkdir(); (b / "estado.json").write_text(json.dumps({"parametros": {"medio_km": 20}}), encoding="utf-8")
    assert PS._ambito_cuenca(a) and not PS._ambito_cuenca(b)


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
