# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Regresión matemática de cmip6_sesgo (casos que la revisión de Codex marcó como débiles): completitud temporal, pesos degenerados, QDM/extremos, Tr100 y transferencia a IDF.
Datos SINTÉTICOS de respuesta conocida; sin red ni descargas. Ejecutar: python -m uceclima.tests.test_cmip6_matematica"""
import sys, traceback
import numpy as np
import pandas as pd

from uceclima import cmip6_sesgo as SB


def _serie(a0, a1, seed=1, escala=8.0, p=0.35):
    idx = pd.date_range(f"{a0}-01-01", f"{a1}-12-31", freq="D"); rng = np.random.default_rng(seed)
    return pd.Series(np.where(rng.random(len(idx)) < p, rng.gamma(0.8, escala, len(idx)), 0.0), index=idx)


# ------------------------------------------------------------------ 1. completitud temporal
def test_ams_rechaza_anio_con_un_solo_dia_y_reporta():
    s = _serie(2000, 2009)
    s = s[~((s.index.year == 2004) & (s.index.dayofyear > 1))]                    # 2004: un solo día presente (fechas ausentes, no NaN)
    ams = SB._ams(s)
    assert len(ams) == 9, f"el año con un día no debe aceptarse: {len(ams)} máximos"
    info = SB._ams_info(s)
    assert [e["anio"] for e in info["excluidos"]] == [2004] and info["excluidos"][0]["cobertura"] < 0.01
    assert 0.85 < info["cobertura_efectiva"] < 0.95


def test_ams_cuenta_fechas_ausentes_en_medio_del_anio_y_nan():
    s = _serie(2000, 2005)
    s = s[~((s.index.year == 2002) & (s.index.month.isin(range(3, 12))))]         # faltan 9 meses (fechas ausentes)
    s.loc["2003-01-01":"2003-12-31"] = np.where(np.arange(365) < 200, np.nan, s.loc["2003-01-01":"2003-12-31"].values)   # 2003: 55 % NaN
    info = SB._ams_info(s)
    assert sorted(e["anio"] for e in info["excluidos"]) == [2002, 2003] and len(SB._ams(s)) == 4


def test_ams_primer_anio_parcial_no_cuenta_como_completo():
    s = _serie(2000, 2005); s = s["2000-11-15":]
    assert len(SB._ams(s)) == 5 and SB._ams_info(s)["excluidos"][0]["anio"] == 2000


def test_calendario_noleap_no_penaliza_el_29_de_febrero():
    s = _serie(2000, 2009); s = s[~((s.index.month == 2) & (s.index.day == 29))]    # producto de 365 días
    assert SB._calendario(s) == "noleap" and len(SB._ams(s)) == 10
    assert SB._calendario(_serie(2000, 2009)) == "gregoriano"


def test_clim_exige_mes_completo_y_normaliza_el_parcial():
    s = _serie(2000, 2009, p=1.0, escala=1.0)
    full = SB._clim(s)
    s2 = s.copy(); s2.loc["2005-06-10":"2005-06-30"] = np.nan                  # junio 2005: 9/30 días (30 % → excluido)
    c2 = SB._clim(s2)
    assert np.isfinite(c2).all() and abs(c2[5] - SB._clim(s[s.index.year != 2005])[5]) < 1e-9, "el mes con 30 % de cobertura debe excluirse, no sumarse parcial"
    s3 = s.copy(); s3.loc["2005-06-27":"2005-06-30"] = np.nan                  # 26/30 = 87 % <90 %: excluido
    assert abs(SB._clim(s3)[5] - SB._clim(s[s.index.year != 2005])[5]) < 1e-9
    assert abs(full[5] - SB._clim(s)[5]) < 1e-12


def test_metricas_no_oculta_huecos_eliminando_nan():
    o = _serie(1981, 2000, seed=3); g = _serie(1981, 2000, seed=4)
    g2 = g.copy(); g2.loc["1990-01-01":"1990-12-31"] = np.nan; g2 = g2[~((g2.index.year == 1995) & (g2.index.dayofyear > 3))]
    m = SB.metricas(o, g2)
    assert sorted(m["anios_excluidos"]) == [1990, 1995] and 0.85 < m["cobertura_efectiva_pct"] / 100 < 0.97
    m0 = SB.metricas(o, g)
    assert m0["anios_excluidos"] == [] and m0["cobertura_efectiva_pct"] > 99.9


# ------------------------------------------------------------------ 2. pesos del ensamble
def _chk(pw):
    p = pw["peso"].values
    assert np.isfinite(p).all() and (p >= 0).all() and abs(p.sum() - 1) < 1e-9, p


def test_climwip_modelo_unico_peso_uno():
    pw, info = SB.climwip(pd.Series([0.7], index=["a"]), {"a": np.arange(12.)})
    _chk(pw); assert pw["peso"].iloc[0] == 1.0 and any("único" in r for r in info["reglas"])


def test_climwip_desempeno_perfecto_y_modelos_identicos():
    CH = {m: np.arange(12.) + k for k, m in enumerate("abc")}
    pw, info = SB.climwip(pd.Series([0.0, 0.0, 0.0], index=list("abc")), CH); _chk(pw)       # todos perfectos: mediana 0
    assert any("perfecto" in r for r in info["reglas"]) and np.allclose(pw["w_desempeno"], 1)
    pw, info = SB.climwip(pd.Series([0.0, 1.0, 2.0], index=list("abc")), CH); _chk(pw)       # uno perfecto, mediana 1
    assert pw["peso"].idxmax() == "a"
    ident = {m: np.arange(12.) for m in "abc"}                                               # modelos idénticos: sin distancias positivas
    pw, info = SB.climwip(pd.Series([1.0, 2.0, 3.0], index=list("abc")), ident); _chk(pw)
    assert any("idénticos" in r for r in info["reglas"]) and np.allclose(pw["w_independencia"], 1 / 3)


def test_climwip_mediana_cero_con_mayoria_perfecta():
    CH = {m: np.arange(12.) * (k + 1) for k, m in enumerate("abcd")}
    pw, info = SB.climwip(pd.Series([0.0, 0.0, 0.0, 5.0], index=list("abcd")), CH); _chk(pw)
    assert pw.loc["d", "peso"] < pw.loc["a", "peso"] and any("σ_D" in r for r in info["reglas"])


def test_climwip_no_finito_no_se_sustituye():
    CH = {m: np.arange(12.) + k for k, m in enumerate("ab")}
    for D, C in ((pd.Series([np.nan, 1.0], index=list("ab")), CH), (pd.Series([np.inf, 1.0], index=list("ab")), CH),
                 (pd.Series([1.0, 2.0], index=list("ab")), {"a": np.full(12, np.nan), "b": np.arange(12.)})):
        try:
            SB.climwip(D, C); raise AssertionError("debía rechazar valores no finitos")
        except SB.SesgoError as e:
            assert "no finit" in str(e)


def test_climwip_desbordamiento_no_da_suma_cero():
    CH = {m: np.arange(12.) + 3 * k for k, m in enumerate("abc")}
    pw, info = SB.climwip(pd.Series([1.0, 1.0, 1e6], index=list("abc")), CH); _chk(pw)       # exp(-(1e6/σ)²) = 0 en doble precisión
    assert pw.loc["c", "peso"] >= 0


def test_percentil_ponderado_valida_pesos():
    assert abs(SB.pesos_ponderados_percentil([1, 2, 3], [1, 1, 1], 0.5) - 1.5) < 1e-9
    for w in ([0, 0, 0], [1, -1, 1], [1, np.nan, 1]):
        try:
            SB.pesos_ponderados_percentil([1, 2, 3], w, 0.5); raise AssertionError("debía rechazar pesos inválidos")
        except SB.SesgoError:
            pass


# ------------------------------------------------------------------ 3. transferencia diaria → IDF
def test_idf_etiqueta_supuesto_exploratorio():
    t = SB.SUPUESTO_IDF.lower()
    assert "exploratorio" in t and "duraci" in t and "no está validada" in t and "no es una predicci" in t


# ------------------------------------------------------------------ 4. QDM y extremos
def _cal(obs_esc=5.0, mod_esc=8.0):
    o = _serie(1981, 2014, seed=11, escala=obs_esc); g = _serie(1981, 2014, seed=12, escala=mod_esc)
    return o, g, SB.QQM().fit(o, g)


def test_qdm_preserva_senal_conocida():
    o, g, q = _cal()
    fut = (g * 1.0).copy(); fut.index = fut.index + pd.DateOffset(years=60); fut = fut * 1.25                      # señal conocida: +25 % multiplicativo
    ch, cf = q.transform(g), q.transform_qdm(fut, g)
    for p in (0.5, 0.75, 0.9, 0.95):
        a, b = np.quantile(ch[ch >= 1], p), np.quantile(cf[cf >= 1], p)
        assert 1.15 < b / a < 1.40, (p, b / a)


def test_qdm_sin_senal_equivale_a_qqm():
    o, g, q = _cal(); fut = g.copy(); fut.index = fut.index + pd.DateOffset(years=60)
    ch, cf = q.transform(g), q.transform_qdm(fut, g)
    assert abs(cf.sum() / ch.sum() - 1) < 0.05


def test_qdm_mes_seco_y_ausencia_de_muestras_humedas():
    o, g, q = _cal(); h = g.copy(); h[h.index.month == 7] = 0.0                         # el modelo histórico no llueve en julio
    fut = g.copy(); fut.index = fut.index + pd.DateOffset(years=60)
    out = q.transform_qdm(fut, h)
    assert np.isfinite(out.values).all() and (out >= 0).all(), "sin muestras húmedas históricas no puede haber NaN/∞/negativos"
    assert q.avisos.get(7, 0) > 0, "debe quedar registrado que julio no tuvo señal de cambio utilizable"
    seca = fut.copy(); seca[seca.index.month == 3] = 0.0                                # futuro sin lluvia en marzo
    o2 = q.transform_qdm(seca, g); assert (o2[o2.index.month == 3] == 0).all()
    todo_seco = fut * 0.0; assert (q.transform_qdm(todo_seco, g) == 0).all()


def test_qdm_extremo_fuera_del_soporte_es_finito_y_monotono():
    o, g, q = _cal(); fut = g.copy(); fut.index = fut.index + pd.DateOffset(years=60)
    mx = float(g.max()); fut.iloc[100] = 3 * mx; fut.iloc[101] = 6 * mx; fut.iloc[102] = 10 * mx
    out = q.transform_qdm(fut, g)
    v = out.iloc[100:103].values
    assert np.isfinite(v).all() and v[0] > 0, v
    mes = fut.index.month.values
    if mes[100] == mes[101] == mes[102]:
        assert v[0] <= v[1] <= v[2], "no monótono fuera del soporte"
    assert np.isfinite(out.values).all()
    # el EQM del agente acota la cola al máximo observado (documentado): QQM/QDM no
    e = SB.EQMAgente().fit(o, g); acot = e.transform(pd.Series([3 * mx], index=pd.to_datetime(["2000-06-15"]))).iloc[0]
    assert acot <= o.max() + 1e-9


def test_qdm_ceros_y_denominador_cero():
    o, g, q = _cal(); fut = g.copy(); fut.index = fut.index + pd.DateOffset(years=60)
    z = fut.copy(); z[:] = 0.0; z.iloc[5] = 40.0
    out = q.transform_qdm(z, g); assert np.isfinite(out.values).all() and (out >= 0).all()
    assert (out.drop(out.index[5]) == 0).all()


def test_gumbel_info_anios_efectivos_e_incertidumbre():
    rng = np.random.default_rng(0); x8 = rng.gumbel(60, 15, 8); x40 = rng.gumbel(60, 15, 40)
    a = SB._gumbel_info(x8, 100); b = SB._gumbel_info(x40, 100)
    assert a["anios_efectivos"] == 8 and a["certificable"] is False and "no certific" in a["estado"].lower()
    assert b["anios_efectivos"] == 40 and b["certificable"] is False and "extrapolaci" in b["estado"].lower()
    for r in (a, b):
        assert r["ic90_inf"] < r["valor"] < r["ic90_sup"] or r["ic90_inf"] <= r["valor"] <= r["ic90_sup"]
    assert (a["ic90_sup"] - a["ic90_inf"]) > (b["ic90_sup"] - b["ic90_inf"]), "con 8 años la incertidumbre debe ser mayor que con 40"
    assert np.isnan(SB._gumbel_info(x8[:5], 100)["valor"]) and SB._gumbel_info(x40, 10)["certificable"] is True
    assert abs(SB._gumbel(x40, 100) - b["valor"]) < 1e-9


if __name__ == "__main__":
    fallos = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK", n)
            except Exception:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=3, file=sys.stdout)
    sys.exit(1 if fallos else 0)
