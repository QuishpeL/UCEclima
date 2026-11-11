# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Panel «Hidrología y calibración»: métricas solo en períodos coincidentes, rótulo «simulación sin calibrar», conservación de volumen, unidades/fechas y exportación sin sobrescribir.
Datos sintéticos de respuesta conocida + la cuenca Milagro real del núcleo (solo lectura). Ejecutar: python -m uceclima.tests.test_hidrologia"""
import json, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd

from uceclima import hidrologia_api as H


def _idx(n=48, ini="2020-03-01", freq="h", tz="UTC"):
    return pd.date_range(ini, periods=n, freq=freq, tz=tz)


def _hid(i):
    return pd.Series(10 * np.exp(-((np.arange(len(i)) - 20) / 6.0) ** 2), index=i)


def test_metricas_perfectas_y_solo_periodo_coincidente():
    i = _idx(); s = _hid(i); o = s.copy()
    o.iloc[:10] = np.nan; o.iloc[30:34] = np.nan; o = o.drop(o.index[40:44])                    # NaN y fechas ausentes
    m = H.metricas_coincidentes(o, s)
    assert m["calculado"] and m["n_pares"] == 48 - 10 - 4 - 4 and abs(m["NSE"] - 1) < 1e-12 and abs(m["PBIAS_pct"]) < 1e-9 and m["RMSE"] < 1e-12
    assert m["periodo_coincidente"][0] == str(i[10]) and "sin interpolar" in m["criterio"]
    assert abs(m["cobertura_obs_sobre_sim"] - 30 / 48) < 1e-9


def test_metricas_con_sesgo_conocido_y_desfase_del_pico():
    i = _idx(); s = _hid(i); o = (s * 0.8).shift(2).dropna()                                    # obs 20 % menor y pico 2 h después
    m = H.metricas_coincidentes(o, s)
    assert m["calculado"] and m["PBIAS_pct"] > 0 and abs(m["error_tiempo_pico_min"] + 120) < 1e-6, m
    assert m["error_pico_pct"] > 0 and m["NSE"] < 1


def test_sin_pares_suficientes_no_calcula():
    i = _idx(); s = _hid(i); o = pd.Series(np.nan, index=i); o.iloc[3] = 1.0; o.iloc[4] = 2.0
    m = H.metricas_coincidentes(o, s); assert m["calculado"] is False and "mínimo" in m["motivo"] and m["n_pares"] == 2
    o2 = pd.Series(1.0, index=i + pd.Timedelta(minutes=7))                                       # instantes distintos: no se interpola
    m2 = H.metricas_coincidentes(o2, s); assert m2["calculado"] is False and m2["n_pares"] == 0


def test_unidades_y_zona_horaria_explicitas():
    i = _idx(); s = _hid(i)
    for fn in (lambda: H.metricas_coincidentes(s, s, "l/s", "m3/s"), lambda: H.metricas_coincidentes(s, s.tz_localize(None)), lambda: H.metricas_coincidentes(s.reset_index(drop=True), s)):
        try:
            fn(); raise AssertionError("debía rechazarse")
        except H.HidroError:
            pass


def test_etiqueta_sin_calibrar_y_nunca_calibrado_automatico():
    assert H.estado_calibracion(None, None)["etiqueta"] == "SIMULACIÓN SIN CALIBRAR"
    assert H.estado_calibracion(pd.Series([1.0]), {"calculado": False, "motivo": "x"})["calibracion"] == "sin_calibrar"
    e = H.estado_calibracion(pd.Series([1.0]), {"calculado": True, "n_pares": 9})
    assert e["calibracion"] == "comparacion_con_observaciones" and "calibrado" not in e["etiqueta"].lower().replace("calibración", "")


def test_observaciones_solo_con_identidad_confirmada():
    with tempfile.TemporaryDirectory() as t:
        p = Path(t); (p / "observaciones").mkdir()
        cab = "evento_id,estacion_id,nombre_estacion,x,y,crs,fecha,caudal_m3s,nivel_m,datum_vertical,identidad_confirmada,incertidumbre_pct,fuente\n"
        (p / "observaciones" / "aforos_caudal.csv").write_text(cab, encoding="utf-8")
        s, nota = H.leer_observaciones(p, p / "observaciones" / "aforos_caudal.csv"); assert s is None and "no hay" in nota.lower()
        (p / "observaciones" / "aforos_caudal.csv").write_text(cab + "E1,H1,a,0,0,x,2020-03-01T00:00:00Z,5.0,,,si,10,f\nE1,H1,a,0,0,x,2020-03-01T01:00:00Z,6.0,,,no,10,f\nE1,H1,a,0,0,x,2020-03-01T02:00:00Z,,,,si,10,f\n", encoding="utf-8")
        s, nota = H.leer_observaciones(p, p / "observaciones" / "aforos_caudal.csv")
        assert len(s) == 1 and s.iloc[0] == 5.0 and s.index.tz is not None


def _corrida_sintetica(raiz, fecha_inicio=None):
    r = Path(raiz) / "resultados" / "corrida_20260101_000000_prueba"; sal = r / "salida" / "Tr100_prueba"; sal.mkdir(parents=True)
    n, dt, area = 12, 300.0, 1e7
    pd.DataFrame({"inicio_s": np.arange(n) * dt, "fin_s": (np.arange(n) + 1) * dt, "lluvia_mm": np.full(n, 2.0)}).to_csv(sal / "hietograma.csv", index=False)
    t = np.arange(0, n * dt + 1, dt); esc = np.cumsum(np.r_[0, np.full(n, 0.3 * 2.0 / 1000 * area)]); sal_v = np.r_[0, np.cumsum(np.full(n, 150.0 * dt / 20))]      # salida 7,5 m3/s constante
    pd.DataFrame({"tiempo_s": t, "volumen_almacenado_m3": esc - sal_v, "volumen_escorrentia_m3": esc, "volumen_entrada_m3": 0.0, "volumen_salida_m3": sal_v, "ajuste_redondeo_m3": 0.0, "residual_m3": 0.0, "profundidad_max_m": 0.1}).to_csv(sal / "balance_agua.csv", index=False)
    (sal / "resumen.json").write_text(json.dumps({"area_m2": area, "P_total_mm": 24.0, "escenario": "diseno_idf_historica", "tipo_forzamiento": "diseno_idf", "residual_final_m3": 0.0, "error_balance_max_pct": 0.0, "estado": "final_completo"}), encoding="utf-8")
    cfg = {"config": {}}
    if fecha_inicio:
        h = Path(raiz) / "hietograma_observado.csv"; pd.DataFrame({"fecha": pd.date_range(fecha_inicio, periods=n, freq="5min", tz="UTC").astype(str), "lluvia_mm": 2.0}).to_csv(h, index=False)
        cfg = {"config": {"evento_observado": {"hietograma_csv": str(h)}}}
    (r / "entrada.json").write_text(json.dumps(cfg), encoding="utf-8")
    return r.name


def test_corrida_de_diseno_es_sin_calibrar_y_conserva_volumenes():
    with tempfile.TemporaryDirectory() as t:
        rid = _corrida_sintetica(t); d = H.serie_corrida(t, rid)
        q = np.array(d["hidrogramas"][0]["q"]); tq = np.array(d["hidrogramas"][0]["t_s"])
        assert d["estado"]["etiqueta"] == "SIMULACIÓN SIN CALIBRAR" and d["metricas"] is None and d["tiempo"]["referencia"] is None and d["hidrogramas"][0]["fecha"] is None
        assert np.allclose(q, 7.5) and abs(q.sum() * 300 - d["volumenes"]["salida_m3"][-1]) < 1e-6                           # ∫Q dt = volumen de salida
        b = d["balance"][0]; assert abs(b["lluvia_m3"] - 24.0 / 1000 * 1e7) < 1e-6 and abs(b["lluvia_m3"] - b["escorrentia_generada_m3"] - b["perdidas_inferidas_m3"]) < 1e-6
        assert d["hietograma"]["unidad"].startswith("mm") and d["volumenes"]["unidad"] == "m3 acumulados"
        assert "no aplica" in d["transito_nota"].lower() and d["transito"] == []


def test_corrida_con_fechas_y_observaciones_empareja_solo_coincidentes():
    with tempfile.TemporaryDirectory() as t:
        rid = _corrida_sintetica(t, "2020-03-01T00:00:00Z"); ini = pd.Timestamp("2020-03-01T00:00:00Z")
        d0 = H.serie_corrida(t, rid); assert d0["tiempo"]["referencia"] is not None and d0["estado"]["calibracion"] == "sin_calibrar" and "no hay observaciones" in d0["observaciones"]
        tq = (np.arange(12) + 0.5) * 300; obs = pd.Series(7.5, index=pd.DatetimeIndex([ini + pd.Timedelta(seconds=float(x)) for x in tq])).iloc[:8]           # observación solo en los primeros 8 pasos
        d = H.serie_corrida(t, rid, obs); m = d["metricas"]
        assert m["calculado"] and m["n_pares"] == 8 and abs(m["RMSE"]) < 1e-9 and d["estado"]["calibracion"] == "comparacion_con_observaciones"
        assert d["hidrogramas"][1]["tipo"] == "observado" and len(d["hidrogramas"][1]["q"]) == 8


def test_milagro_ya_no_es_fuente_ni_hay_observaciones_de_otro_sitio():
    assert not hasattr(H, "serie_cuenca") and not hasattr(H, "eventos_cuenca")
    with tempfile.TemporaryDirectory() as d:
        s, nota = H.leer_observaciones(d); assert s is None and "CELEC" in nota                       # sin fallback a las plantillas del núcleo/Milagro
        c = H.casos(d); assert "cuenca_milagro" not in c and "Mazar" in c["subcuencas"] and c["etiqueta_por_defecto"] == "SIMULACIÓN SIN CALIBRAR"
        rid = _corrida_sintetica(d)
        try:
            H.exportar(d, "cuenca_hms", "EVT_026C"); raise AssertionError("debía rechazar fuentes que no son corridas del proyecto")
        except H.HidroError:
            pass


def test_exportar_crea_carpeta_nueva_con_tablas_png_y_manifiesto_sin_sobrescribir():
    with tempfile.TemporaryDirectory() as t:
        rid = _corrida_sintetica(t); a = H.exportar(t, "corrida", rid); import time; time.sleep(1.1); b = H.exportar(t, "corrida", rid)
        assert a["carpeta"] != b["carpeta"] and Path(a["carpeta"]).exists() and Path(b["carpeta"]).exists()
        for f in ("hietograma.csv", "hidrogramas.csv", "volumenes_acumulados.csv", "balance.csv", "manifiesto.json", "hietograma.png", "hidrogramas.png", "volumenes_acumulados.png", "balance.png"):
            assert (Path(a["carpeta"]) / f).stat().st_size > 0, f
        man = json.loads((Path(a["carpeta"]) / "manifiesto.json").read_text(encoding="utf-8"))
        assert man["estado"]["etiqueta"] == "SIMULACIÓN SIN CALIBRAR" and man["unidades"]["caudal"] == "m3/s"



if __name__ == "__main__":
    fallos = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except Exception:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=4, file=sys.stdout)
    sys.exit(1 if fallos else 0)
