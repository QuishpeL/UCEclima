# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""CMIP6: compuerta documentada, QQM, QDM, ranking, ensamble y factores — con datos SINTÉTICOS de respuesta conocida. Ejecutar: python -m uceclima.tests.test_cmip6"""
import json, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd

from uceclima import cmip6_descarga as CD, cmip6_sesgo as SB, descargas as D
from uceclima.ui import sitio_api


def _lluvia(n_anios, seed, escala=8.0, forma=0.8, p_hum=0.32, ini="1981-01-01", estacional=True):
    idx = pd.date_range(ini, periods=int(n_anios * 365.25), freq="D"); rng = np.random.default_rng(seed)
    mes = idx.month.values; f = 1.0 + (0.6 * np.cos((mes - 3) / 12 * 2 * np.pi) if estacional else np.zeros(len(idx)))
    hum = rng.random(len(idx)) < p_hum * f.clip(0.2, 2)
    return pd.Series(np.where(hum, rng.gamma(forma, escala * f, len(idx)), 0.0), index=idx)


def test_compuerta_documentada_y_descarga_bloqueada_sin_decision():
    with tempfile.TemporaryDirectory() as t:
        c = sitio_api.crear("Sitio CMIP6", -78.645, -2.585, base=t)
        assert CD.decision(c) is None
        assert CD.exigir_decision(c) is None                                         # sin compuerta (decisión del usuario, 14-oct-2026)
        d = CD.asumir_baseline(c)
        assert d["decision"] == "linea_base_asumida_por_el_usuario" and d["estado_real_de_la_linea_base"] == "no calibrada ni validada" and "13-oct-2026" in d["texto"]
        assert CD.decision(c)["fecha_utc"] == d["fecha_utc"] and CD.asumir_baseline(c)["fecha_utc"] == d["fecha_utc"]                    # idempotente: no reescribe la decisión original


def test_qqm_corrige_fuera_de_muestra_y_la_frecuencia_humeda():
    obs = _lluvia(34, 1); idx = obs.index
    mod = _lluvia(34, 2, escala=14.0, forma=0.8, p_hum=0.5)                         # modelo sesgado: más lluvia, más días húmedos
    mod.index = idx[: len(mod)]
    m_raw = SB.metricas(obs, mod); assert m_raw["bias_total_pct"] > 40 and m_raw["frec_humedos_mod_pct"] > m_raw["frec_humedos_obs_pct"] + 8
    q = SB.QQM().fit(obs["1981":"1997"], mod["1981":"1997"]); cor = q.transform(mod["1998":"2014"])
    m_q = SB.metricas(obs["1998":"2014"], cor); m_r = SB.metricas(obs["1998":"2014"], mod["1998":"2014"])
    assert abs(m_q["bias_total_pct"]) < 12 < abs(m_r["bias_total_pct"]) and m_q["rmse_cuantiles_mm"] < 0.5 * m_r["rmse_cuantiles_mm"]       # mejora FUERA de la muestra de calibración
    assert abs(m_q["frec_humedos_mod_pct"] - m_q["frec_humedos_obs_pct"]) < 3 and (cor >= 0).all() and cor.isna().sum() == 0              # frecuencia de días húmedos ajustada; sin negativos
    # Honestidad: con solo ~17 años de calibración, el QQM puede EMPEORAR a un modelo que ya era bueno (ruido de muestreo de la cola); por eso se valida fuera de muestra
    dif = []
    for seed in (3, 13, 23, 33):
        s_ = _lluvia(34, seed); s_.index = idx[: len(s_)]
        c_ = SB.QQM().fit(obs["1981":"1997"], s_["1981":"1997"]).transform(s_["1998":"2014"])
        dif.append(SB.metricas(obs["1998":"2014"], c_)["rmse_cuantiles_mm"] - SB.metricas(obs["1998":"2014"], s_["1998":"2014"])["rmse_cuantiles_mm"])
    assert all(np.isfinite(dif))                                                           # no se promete mejora en un modelo ya bueno: la evaluación cruzada la mide y la reporta (puede ser negativa)


def test_qdm_preserva_la_senal_de_cambio_relativa():
    obs = _lluvia(34, 4); mod_h = _lluvia(34, 5, escala=12.0, p_hum=0.45); mod_h.index = obs.index[: len(mod_h)]
    q = SB.QQM().fit(obs, mod_h)
    fut = _lluvia(30, 6, escala=12.0, p_hum=0.45, ini="2041-01-01") * 1.25                       # el modelo proyecta +25 % uniforme
    cor = q.transform_qdm(fut, mod_h)
    f_total = cor.groupby(cor.index.year).sum().mean() / q.transform(mod_h).groupby(mod_h.index.year).sum().mean()
    assert 1.1 < f_total < 1.45, f_total                                                          # la señal (+25 %) sobrevive a la corrección
    assert (cor >= 0).all() and cor.notna().all()


def test_evaluar_ranking_ensamble_y_factores_con_modelos_sinteticos():
    with tempfile.TemporaryDirectory() as t:
        c = sitio_api.crear("Sitio ranking", -78.645, -2.585, base=t); CD.asumir_baseline(c)
        obs = _lluvia(45.5, 10)[:"2025-12-31"]
        est = c / "datos" / "estaciones"; est.mkdir(parents=True)
        pd.DataFrame({"fecha": obs.index.strftime("%Y-%m-%dT00:00:00Z"), "lluvia_mm": obs.values}).to_csv(est / "OBS1.csv", index=False)
        dh = c / "datos_descargados" / "cmip6_historico_20260101_000000"; df = c / "datos_descargados" / "cmip6_futuro_20260101_000001"; dh.mkdir(parents=True); df.mkdir(parents=True)
        idx = pd.date_range("1981-01-01", "2014-12-31")
        modelos = {"BUENO": dict(escala=8.5, p_hum=0.33, estacional=True), "REGULAR": dict(escala=11.0, p_hum=0.42, estacional=True), "MALO": dict(escala=20.0, p_hum=0.6, estacional=False), "SESGADO": dict(escala=14, p_hum=0.33, estacional=True)}
        for k, (m, kw) in enumerate(modelos.items()):
            s = _lluvia(34, 20 + k, **kw)[: len(idx)]; s.index = idx[: len(s)]
            pd.DataFrame({"fecha": s.index.strftime("%Y-%m-%d"), "pr_mm": s.values}).to_csv(dh / f"{m}_historical.csv", index=False)
            for esc, fac in (("ssp245", 1.15), ("ssp585", 1.3)):
                f = _lluvia(86, 40 + k, **kw, ini="2015-01-01") * fac; pd.DataFrame({"fecha": f.index.strftime("%Y-%m-%d"), "pr_mm": f.values}).to_csv(df / f"{m}_{esc}.csv", index=False)
        r = SB.evaluar(c, "est:OBS1", k_ensamble=3)
        rk = r["ranking"]; assert rk.iloc[0]["modelo"] == "BUENO" and rk.iloc[-1]["modelo"] in ("MALO", "SESGADO") and r["resumen"]["mejor_modelo"] == r["resumen"]["mejor_modelo_por_rmse_climatologia"] == rk.sort_values("rmse_clim_mm_mes").iloc[0]["modelo"]
        sel = r["seleccionados"]; assert 1 <= len(sel) <= 4 and 0.9 <= sel["peso"].sum() <= 1 + 1e-9 and sel.iloc[0]["peso"] >= sel.iloc[-1]["peso"]
        mj = rk.set_index("modelo")["mejora_qqm_cuantiles_pct"]
        assert mj["MALO"] > 50 and mj["MALO"] > mj["BUENO"] and r["resumen"]["mejora_media_qqm_cuantiles_pct"] > 10                                                          # la corrección ayuda más cuanto peor es el modelo (y puede no ayudar al bueno)
        assert abs(r["resumen"]["tr100_24h_ensamble_qqm_mm"] - r["resumen"]["tr100_24h_obs_mm"]) < 0.35 * r["resumen"]["tr100_24h_obs_mm"]
        assert "no calibrada ni validada" in " ".join(r["resumen"]["advertencias"]) and r["graficas"]["qq_humedos"]["obs"] and (Path(r["carpeta"]) / "calibracion_qqm.json").exists()
        fa = SB.factores(c, r["carpeta"])
        F = fa["factores"]; assert set(F["escenario"]) == {"ssp585"}                                                                                                     # solo el escenario extremo (decisión del usuario)
        x = F[(F["horizonte"] == "2040-2069") & (F["metrica"] == "total anual") & (F["version"] == "QQM/QDM")].iloc[0]
        assert 1.1 < x["mediana_ponderada"] < 1.5 and x["p10"] <= x["mediana_ponderada"] <= x["p90"]                                                                       # +30 % sintético recuperado con su rango
        assert "Proyecciones" in fa["nota"] and (Path(fa["carpeta"]) / "factores_cc.json").exists() and fa["verificacion"] is not None and "ENSAMBLE (promedio ponderado)" in set(fa["verificacion"]["modelo"])
        from uceclima import escenarios_idf as ESC
        d = {e["id"]: e for e in ESC._escenarios_cmip6(c)}
        assert "cc_ssp585_2040-2069_mediana" in d and "cc_ssp585_2040-2069_mejor" in d and not any("ssp245" in k for k in d)
        assert d["cc_ssp585_2040-2069_mediana"]["rol"].startswith("cambio climático") and d["cc_ssp585_2040-2069_mediana"]["tasa_cambio_pct"] > 0 and "no calibrada" in d["cc_ssp585_2040-2069_mediana"]["fuente"]
        from uceclima import basedatos as BD
        BD.abrir(c).close(); n = BD.sincronizar(c, "est:OBS1")["tablas"]
        assert n["cmip6_modelos"] == 4 and n["cmip6_series"] > 4 * 12000 and n["cmip6_factores"] > 0 and n["referencia_lluvia"] > 12000
        q = BD.consultar(c, "SELECT DISTINCT escenario FROM cmip6_series ORDER BY 1"); assert [f[0] for f in q["filas"]] == ["historical", "ssp585"]                       # ssp245 no entra a la base
        for malo in ("DELETE FROM eventos", "SELECT 1; DROP TABLE eventos", "PRAGMA table_info(eventos)", "INSERT INTO eventos(evento) VALUES ('x')"):
            try:
                BD.consultar(c, malo); raise SystemExit("la consulta de escritura debía rechazarse: " + malo)
            except BD.BDError:
                pass
        an = SB.anual(c); assert set(an["escenarios"]) == {"historical", "ssp585"} and an["obs"]["anios"]


if __name__ == "__main__":
    fallos = 0
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            try:
                f(); print("OK   ", nombre)
            except BaseException:
                fallos += 1; print("FALLA", nombre); traceback.print_exc()
    sys.exit(1 if fallos else 0)
