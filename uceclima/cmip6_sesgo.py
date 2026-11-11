# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""CMIP6 · selección de modelos (ClimWIP), corrección de sesgo (QQM/QDM), validación cruzada impar/par, ensamble por quintiles y factores de cambio — sobre lluvia DIARIA de una celda.

Metodología (ver MODULO_CMIP6.md): Brunner et al. 2020 (ClimWIP: pesos por desempeño e independencia), Cannon et al. 2015 (QDM: la corrección preserva el cambio relativo de los cuantiles),
Thrasher et al. 2022 (NEX-GDDP-CMIP6 ya corregido por BCSD; extremos subestimados por difusión), Song, Shiru & Chung 2025 (ensamble multimodelo por quintiles) y el flujo de las entregas de
Machala/Gualaquiza (ranking por RMSE de climatología vs CHIRPS, EQM mensual, IDF oficial × factor de cambio por Tr, ensamble ClimWIP). NO se calcula RMSE día a día. Todo queda rotulado:
línea base asumida por decisión del usuario (no calibrada ni validada); proyecciones, no predicciones."""
import json, math
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

UMBRAL_HUMEDO = 1.0
PROBS = np.r_[np.arange(0.01, 0.99, 0.01), 0.99, 0.995]
NIV_QQ = np.r_[np.arange(0.5, 0.99, 0.05), 0.99, 0.995]
PLIEGUES = (("1981-01-01", "1997-12-31"), ("1998-01-01", "2014-12-31"))
HORIZONTES = {"2040-2069": ("2040-01-01", "2069-12-31"), "2071-2100": ("2071-01-01", "2100-12-31")}      # 2040–2069 = la ventana de las entregas previas (centrada en 2055)


class SesgoError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ utilidades
SUPUESTO_IDF = ("SUPUESTO EXPLORATORIO de cambio uniforme por duración: el factor sale de los máximos DIARIOS (24 h) de la celda de 0,25° y se aplica igual a todas las duraciones de la IDF oficial. "
                "Los máximos diarios no demuestran cómo cambian las intensidades subdiarias (que pueden cambiar más o menos que las de 24 h). La IDF resultante NO está validada y el mapa/hidrograma que "
                "se obtenga con ella NO es una predicción: es un escenario de sensibilidad bajo la línea base asumida por decisión del usuario (no calibrada ni validada).")
MIN_COBERTURA = 0.9                 # fracción mínima de días esperados con dato válido para aceptar un año (máximos anuales) o un mes (climatología)
MIN_ANIOS_GUMBEL = 8                # por debajo no se estima
MIN_ANIOS_CERTIFICABLE = 30         # un nivel de retorno solo se «certifica» si Tr <= n años efectivos y n >= 30; de lo contrario es extrapolación


def _gumbel(x, tr):
    """Nivel de retorno de Tr años por Gumbel (máxima verosimilitud, como en las entregas previas; si falla, método de momentos). Valor puntual: la incertidumbre está en `_gumbel_info`."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < MIN_ANIOS_GUMBEL:
        return np.nan
    try:
        from scipy import stats
        loc, sc = stats.gumbel_r.fit(x)
        return float(stats.gumbel_r.ppf(1 - 1 / tr, loc=loc, scale=sc))
    except Exception:
        a = math.sqrt(6) / math.pi * x.std(ddof=1); u = x.mean() - 0.5772 * a
        return float(u - a * math.log(-math.log(1 - 1 / tr)))


def _boot_gumbel_momentos(x, tr, n_boot=500, seed=12345):
    """Remuestreo de los máximos con Gumbel por momentos (rápido, vectorizado). Devuelve n_boot niveles de retorno; sirve SOLO para dimensionar la incertidumbre, no sustituye al ajuste MLE."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]; rng = np.random.default_rng(seed)
    M = x[rng.integers(0, len(x), (n_boot, len(x)))]; a = math.sqrt(6) / math.pi * M.std(axis=1, ddof=1); u = M.mean(axis=1) - 0.5772 * a
    return u - a * math.log(-math.log(1 - 1 / tr))


def _gumbel_info(x, tr):
    """Nivel de retorno con años efectivos, intervalo de incertidumbre (bootstrap p5–p95) y estado. NUNCA «certificable» si Tr > n años efectivos o n < 30: se trata de extrapolación."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]; n = int(len(x))
    if n < MIN_ANIOS_GUMBEL:
        return {"valor": np.nan, "anios_efectivos": n, "tr": tr, "ic90_inf": np.nan, "ic90_sup": np.nan, "certificable": False, "estado": f"no estimable: {n} máximos anuales (mínimo {MIN_ANIOS_GUMBEL})"}
    v = _gumbel(x, tr); b = _boot_gumbel_momentos(x, tr); lo, hi = float(np.nanpercentile(b, 5)), float(np.nanpercentile(b, 95))
    lo, hi = min(lo, v), max(hi, v)
    cert = bool(n >= MIN_ANIOS_CERTIFICABLE and tr <= n)
    if n < MIN_ANIOS_CERTIFICABLE:
        est = f"no certificable: solo {n} años efectivos (<{MIN_ANIOS_CERTIFICABLE}); estimación puntual muy incierta"
    elif tr > n:
        est = f"extrapolación (Tr {tr} > {n} años efectivos): no certificada; usar el intervalo y la sensibilidad a la distribución"
    else:
        est = "dentro del periodo de registro"
    return {"valor": v, "anios_efectivos": n, "tr": tr, "ic90_inf": lo, "ic90_sup": hi, "certificable": cert, "estado": est}


# ---- completitud temporal: se evalúa contra el calendario ESPERADO del producto (incluye fechas ausentes), nunca contra los registros presentes
def _calendario(s):
    """'noleap' (365 días, p. ej. NEX-GDDP) si en ningún año bisiesto hay dato válido el 29 de febrero teniendo el 28-feb y el 1-mar; si no, 'gregoriano'. (Los calendarios de 360 días no caben en un índice de fechas.)"""
    v = s.dropna()
    if v.empty:
        return "gregoriano"
    if ((v.index.month == 2) & (v.index.day == 29)).any():
        return "gregoriano"
    anios = [a for a in sorted(set(v.index.year)) if pd.Timestamp(year=a, month=1, day=1).is_leap_year]
    tiene = lambda a: pd.Timestamp(a, 2, 28) in v.index and pd.Timestamp(a, 3, 1) in v.index
    return "noleap" if anios and all(tiene(a) for a in anios) else "gregoriano"


def _esperado(s, calendario=None):
    """Índice diario esperado entre el primer y el último AÑO tocados por la serie (los años parciales del borde quedan incompletos)."""
    cal = calendario or _calendario(s); a0, a1 = int(s.index.min().year), int(s.index.max().year)
    idx = pd.date_range(f"{a0}-01-01", f"{a1}-12-31", freq="D")
    return idx[~((idx.month == 2) & (idx.day == 29))] if cal == "noleap" else idx


def _cobertura(s, por="anio", calendario=None):
    """Tabla (esperados, validos, cobertura) por año o por (año, mes) contra el calendario esperado; las fechas ausentes cuentan como faltantes igual que los NaN."""
    idx = _esperado(s, calendario); v = s.reindex(idx).notna()
    clave = [idx.year] if por == "anio" else [idx.year, idx.month]
    esp = pd.Series(1, index=idx).groupby(clave).sum(); val = v.groupby(clave).sum()
    return pd.DataFrame({"esperados": esp, "validos": val, "cobertura": val / esp})


def _ams_info(s, minimo=MIN_COBERTURA, calendario=None):
    """Máximos anuales de los años con cobertura ≥ `minimo` del calendario esperado. Devuelve valores, años incluidos/excluidos (con su cobertura) y la cobertura efectiva global."""
    c = _cobertura(s, "anio", calendario); ok = c["cobertura"] >= minimo; mx = s.groupby(s.index.year).max()
    return {"valores": mx.reindex(c.index[ok]).dropna().values, "anios": [int(a) for a in c.index[ok]],
            "excluidos": [{"anio": int(a), "cobertura": float(r.cobertura), "validos": int(r.validos), "esperados": int(r.esperados)} for a, r in c[~ok].iterrows()],
            "cobertura_efectiva": float(c["validos"].sum() / c["esperados"].sum())}


def _ams(s, minimo=MIN_COBERTURA, calendario=None):
    return _ams_info(s, minimo, calendario)["valores"]


def _clim_info(s, minimo=MIN_COBERTURA, calendario=None):
    """Climatología mensual (mm/mes). Un mes entra solo con cobertura ≥ `minimo` de sus días esperados; el total de un mes aceptado con huecos se NORMALIZA (suma × esperados/válidos) y se cuenta como normalizado."""
    c = _cobertura(s, "mes", calendario); idx = _esperado(s, calendario); suma = s.reindex(idx).groupby([idx.year, idx.month]).sum()
    ok = c["cobertura"] >= minimo; tot = (suma / c["cobertura"].where(c["cobertura"] > 0)).where(ok)
    clim = tot.unstack().mean().reindex(range(1, 13)).values
    return {"clim": clim, "meses_incluidos": int(ok.sum()), "meses_excluidos": int((~ok).sum()), "meses_normalizados": int((ok & (c["cobertura"] < 1)).sum())}


def _clim(s, minimo=MIN_COBERTURA, calendario=None):
    return _clim_info(s, minimo, calendario)["clim"]


def _cuantiles_humedos(s, niveles=NIV_QQ):
    h = s[s >= UMBRAL_HUMEDO].dropna()
    return np.quantile(h.values, niveles) if len(h) >= 30 else np.full(len(niveles), np.nan)


def _rmse(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float); m = np.isfinite(a) & np.isfinite(b)
    return float(np.sqrt(np.mean((a[m] - b[m]) ** 2))) if m.any() else np.nan


def _corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float); m = np.isfinite(a) & np.isfinite(b)
    return float(np.corrcoef(a[m], b[m])[0, 1]) if m.sum() > 2 else np.nan


def metricas(obs, mod):
    """obs y mod: Series diarias. Se comparan solo los días con dato válido en AMBAS, pero la cobertura se juzga contra el calendario esperado (si algún producto es de 365 días, el 29-feb no se espera);
    los años/meses incompletos se excluyen de máximos anuales, climatología y totales, y se reportan (`anios_excluidos`, `cobertura_efectiva_pct`, `meses_*`)."""
    o, g = obs.align(mod, join="inner")
    if len(o) == 0:
        raise SesgoError("Sin fechas en común.")
    cal = "noleap" if "noleap" in (_calendario(o), _calendario(g)) else "gregoriano"
    full = _esperado(o, cal); o, g = o.reindex(full), g.reindex(full); par = o.notna() & g.notna(); o, g = o.where(par), g.where(par)       # periodo coincidente con dato válido en ambas
    if int(par.sum()) < 365 * 5:
        raise SesgoError("Muy pocos días en común para evaluar (menos de 5 años).")
    io, ig = _ams_info(o, calendario=cal), _ams_info(g, calendario=cal); ao, ag = io["valores"], ig["valores"]; n = min(len(ao), len(ag))
    co, cg = _clim_info(o, calendario=cal), _clim_info(g, calendario=cal)
    cob = _cobertura(o, "anio", cal); anios_ok = cob.index[cob["cobertura"] >= MIN_COBERTURA]
    def tot(s):
        t = s.groupby(s.index.year).sum().reindex(anios_ok) / cob.loc[anios_ok, "cobertura"]; return float(t.mean())             # años completos (o ≥90 %, normalizados)
    ov, gv = o.dropna(), g.dropna()
    return {"dias": int(par.sum()), "calendario": cal, "cobertura_efectiva_pct": 100 * float(par.sum() / len(full)), "anios_excluidos": sorted({e["anio"] for e in io["excluidos"]} | {e["anio"] for e in ig["excluidos"]}),
            "meses_excluidos": int(max(co["meses_excluidos"], cg["meses_excluidos"])), "meses_normalizados": int(max(co["meses_normalizados"], cg["meses_normalizados"])),
            "bias_total_pct": 100 * (tot(g) / tot(o) - 1), "bias_p99_pct": 100 * (float(np.quantile(gv, .99)) / max(float(np.quantile(ov, .99)), 1e-9) - 1),
            "frec_humedos_obs_pct": 100 * float((ov >= UMBRAL_HUMEDO).mean()), "frec_humedos_mod_pct": 100 * float((gv >= UMBRAL_HUMEDO).mean()),
            "rmse_clim_mm_mes": _rmse(co["clim"], cg["clim"]), "rmse_cuantiles_mm": _rmse(_cuantiles_humedos(ov), _cuantiles_humedos(gv)),
            "rmse_max_anuales_mm": _rmse(np.sort(ao)[-n:] if n else [], np.sort(ag)[-n:] if n else []), "corr_clim": _corr(co["clim"], cg["clim"]),
            "tr100_24h_obs_mm": _gumbel(ao, 100), "tr100_24h_mod_mm": _gumbel(ag, 100), "anios_efectivos_max": int(min(len(ao), len(ag)))}


# ------------------------------------------------------------------------------------------------ QQM mensual y QDM
class QQM:
    """Mapeo de cuantiles empírico por mes, con ajuste de frecuencia de días húmedos. fit(obs, mod) en la misma ventana."""
    def fit(self, obs, mod):
        o, g = obs.align(mod, join="inner"); ok = o.notna() & g.notna(); o, g = o[ok], g[ok]
        self.m = {}; self.avisos = {}
        for mes in range(1, 13):
            om, gm = o[o.index.month == mes].values, g[g.index.month == mes].values
            if len(om) < 100 or len(gm) < 100:
                raise SesgoError(f"Pocos datos en el mes {mes} para calibrar.")
            seco_obs = float((om < UMBRAL_HUMEDO).mean())
            umbral_mod = float(np.quantile(gm, min(max(seco_obs, 0.0), 0.995)))              # el modelo se «seca» tanto como lo observado
            ow = np.sort(om[om >= UMBRAL_HUMEDO]); gw = np.sort(gm[gm > umbral_mod]); ventana = 0
            while (len(ow) < 20 or len(gw) < 20) and ventana < 3:                       # G26 (Costa, estación seca): ventana móvil estacional ±1…±3 meses solo para los cuantiles de días húmedos
                ventana += 1; ms = [(mes - 1 + d) % 12 + 1 for d in range(-ventana, ventana + 1)]
                ov_, gv_ = o[o.index.month.isin(ms)].values, g[g.index.month.isin(ms)].values
                um_ = {m_: float(np.quantile(g[g.index.month == m_].values, min(max(float((o[o.index.month == m_].values < UMBRAL_HUMEDO).mean()), 0.0), 0.995))) for m_ in ms}
                gmes = g[g.index.month.isin(ms)]; gw = np.sort(gmes.values[gmes.values > np.array([um_[m_] for m_ in gmes.index.month])])
                ow = np.sort(ov_[ov_ >= UMBRAL_HUMEDO])
            if len(ow) < 20 or len(gw) < 20:
                raise SesgoError(f"Pocos días húmedos en el mes {mes} aun con ventana estacional de ±3 meses.")
            if ventana:
                self.avisos[mes] = f"cuantiles de días húmedos con ventana estacional ±{ventana} mes(es) (pocos días húmedos en el mes)"
            self.m[mes] = {"umbral": umbral_mod, "qo": np.quantile(ow, PROBS), "qg": np.quantile(gw, PROBS), "ventana": ventana}
        return self

    def transform(self, mod):
        out = np.full(len(mod), np.nan)
        meses = mod.index.month.values; v = mod.values
        for mes, p in self.m.items():
            i = (meses == mes) & np.isfinite(v); x = v[i]
            y = np.interp(x, p["qg"], p["qo"])
            y = np.where(x > p["qg"][-1], x * (p["qo"][-1] / max(p["qg"][-1], 1e-9)), y)         # cola: razón constante en el último cuantil
            out[i] = np.where(x <= p["umbral"], 0.0, y)
        return pd.Series(out, index=mod.index)

    def transform_qdm(self, fut, ref_hist):
        """QDM multiplicativo mensual: preserva el cambio relativo del modelo entre `ref_hist` (periodo base del modelo) y `fut`."""
        out = np.full(len(fut), np.nan); meses = fut.index.month.values; v = fut.values; mh = ref_hist.index.month.values; self.avisos = {}
        for mes, p in self.m.items():
            i = (meses == mes) & np.isfinite(v); x = v[i]
            if not len(x):
                continue
            hist = np.sort(ref_hist.values[(mh == mes) & np.isfinite(ref_hist.values)])
            if not (hist > p["umbral"]).any():
                # El modelo no tiene días húmedos históricos este mes: el cambio relativo no está definido (división por cero). Regla: sin señal de cambio, se aplica solo el QQM
                # del mes (corrección de sesgo) y queda registrado en `avisos` para no presentar ese mes como proyección con señal.
                self.avisos[mes] = int(len(x)); out[i] = self.transform(pd.Series(x, index=fut.index[i])).values; continue
            fw = np.sort(x[x > p["umbral"]])
            tau = np.clip((np.searchsorted(fw, x, side="right") - 0.5) / max(len(fw), 1), 0.005, 0.995)
            qh = np.quantile(hist[hist > p["umbral"]], tau); qo = np.interp(tau, PROBS, p["qo"]) if len(qh) else np.nan
            qo = np.where(tau > PROBS[-1], p["qo"][-1], qo)
            delta = np.where(qh > 0, x / np.maximum(qh, 1e-9), 1.0)
            y = qo * delta
            out[i] = np.where(x <= p["umbral"], 0.0, y)
        return pd.Series(out, index=fut.index)


# ------------------------------------------------------------------------------------------------ EQM del agente (Machala/Gualaquiza) — comparador
class EQMAgente:
    """Mapeo empírico de cuantiles MENSUAL como en las entregas de Machala/Gualaquiza (`11_cmip6_seleccion_biascorr_indices.py`): 200 cuantiles sobre TODOS los días, sin ajuste de frecuencia
    de días húmedos y con la cola acotada al máximo observado (np.interp con right=1). Se conserva solo para COMPARAR con QQM/QDM (la cola acotada atenúa los extremos futuros)."""
    def fit(self, obs, mod):
        o, g = obs.align(mod, join="inner"); ok = o.notna() & g.notna(); o, g = o[ok], g[ok]; q = np.linspace(0, 1, 200); self.q = q; self.m = {}
        for mes in range(1, 13):
            self.m[mes] = (np.quantile(o[o.index.month == mes].values, q), np.quantile(g[g.index.month == mes].values, q))
        return self

    def transform(self, mod):
        out = np.full(len(mod), np.nan); meses = mod.index.month.values; v = mod.values
        for mes, (oq, mq) in self.m.items():
            i = (meses == mes) & np.isfinite(v)
            out[i] = np.clip(np.interp(np.interp(v[i], mq, self.q, left=0, right=1), self.q, oq), 0, None)
        return pd.Series(out, index=mod.index)


# ------------------------------------------------------------------------------------------------ carga
def _leer(f):
    d = pd.read_csv(f, parse_dates=["fecha"])
    return d.drop_duplicates("fecha").set_index("fecha")["pr_mm"].astype(float).sort_index()


def _carpeta_dl(proyecto, fuente):
    b = Path(proyecto) / "datos_descargados"
    c = sorted(b.glob(f"{fuente}_*"))
    return c[-1] if c else None


def leer_futuro(proyecto, modelo, esc="ssp585"):
    """Serie futura de un modelo: se busca en TODAS las descargas de futuro (la más reciente primero); varias descargas pueden cubrir periodos distintos."""
    for d in sorted((Path(proyecto) / "datos_descargados").glob("cmip6_futuro_*"), reverse=True):
        f = d / f"{modelo}_{esc}.csv"
        if f.exists():
            return _leer(f)
    return None


def referencia_larga(proyecto, id_serie, fin="2025-12-31"):
    """Toda la serie observada completa 1981–2025 (CHIRPS: más de 40 años). Se calibra con 1981–2014 y se verifica de forma independiente con 2015–2025."""
    from . import series_api as SER
    s = SER._serie(proyecto, id_serie)
    s = s[(s.index >= "1981-01-01") & (s.index <= fin)]
    return s.reindex(pd.date_range("1981-01-01", fin, freq="D"))


def referencia(proyecto, id_serie):
    return referencia_larga(proyecto, id_serie, "2014-12-31")


# ------------------------------------------------------------------------------------------------ ClimWIP (Brunner et al. 2020) y ensamble por quintiles
def _sigma(valores, reglas, nombre):
    """Anchura gaussiana = mediana de los valores POSITIVOS cuando la mediana global es 0 (más de la mitad perfectos); None si no hay ninguno positivo (todos perfectos/idénticos)."""
    v = np.asarray(valores, float); m = float(np.median(v))
    if m > 0:
        return m
    pos = v[v > 0]
    if len(pos):
        reglas.append(f"{nombre}: la mediana es 0 (más de la mitad coincide exactamente); se usa la mediana de los valores positivos")
        return float(np.median(pos))
    return None


def climwip(D, CH):
    """Pesos de desempeño × independencia (Brunner et al. 2020). D: Series (modelo → distancia de desempeño ≥ 0), CH: dict modelo → vector de climatología mensual.
    w_i = exp(-(D_i/σ_D)²) · 1/(1+Σ_{j≠i} exp(-(d_ij/σ_S)²)), normalizado. σ_D = mediana de D; σ_S = mediana de las distancias positivas entre modelos (anchuras heurísticas de las entregas previas,
    NO la calibración de σ del ClimWIP original). Casos degenerados, con regla explícita (se devuelve `info['reglas']`; nada se rellena con valores arbitrarios):
      · valores no finitos (NaN/∞) en D o CH → SesgoError (el modelo debe excluirse y reportarse antes, no sustituirse);
      · un solo modelo → peso 1 (no hay ensamble ni independencia que evaluar);
      · desempeño perfecto: σ_D = 0 → se usa la mediana de los D positivos; si todos son 0, el desempeño no discrimina (w_desempeño = 1 para todos);
      · modelos idénticos (ninguna distancia positiva) → σ_S = ∞, cada modelo comparte su peso con todas sus copias (w_independencia = 1/n);
      · desbordamiento (exp → 0) → se opera en escala logarítmica, de modo que la suma de pesos nunca es 0;
      · al final se exige: pesos finitos, ≥ 0 y suma 1 (si no, SesgoError)."""
    mods = list(D.index); n = len(mods); reglas = []
    if n == 0:
        raise SesgoError("climwip: no hay modelos.")
    dv = np.asarray(D.values, float)
    malos = [m for m, d in zip(mods, dv) if not np.isfinite(d) or d < 0] + [m for m in mods if m in CH and not np.isfinite(np.asarray(CH[m], float)).all()]
    if malos:
        raise SesgoError(f"climwip: valores no finitos o negativos en {sorted(set(malos))}: excluir y reportar esos modelos antes de ponderar.")
    if n == 1:
        reglas.append("modelo único: peso 1 (sin ensamble ni independencia)")
        pw = pd.DataFrame({"w_desempeno": [1.0], "w_independencia": [1.0], "peso": [1.0]}, index=mods)
        return pw, {"sigma_D": float("nan"), "sigma_S": float("nan"), "reglas": reglas}
    X = np.array([np.asarray(CH[m], float) for m in mods])
    dij = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).mean(axis=2)); pos = dij[np.triu_indices(n, 1)]; pos = pos[pos > 0]
    sD = _sigma(dv, reglas, "σ_D")
    if sD is None:
        reglas.append("desempeño perfecto en todos los modelos: el desempeño no discrimina (w_desempeño = 1)")
        logwp = np.zeros(n)
    else:
        logwp = -(dv / sD) ** 2
    if len(pos) == 0:
        reglas.append("modelos idénticos (ninguna distancia positiva entre climatologías): σ_S = ∞ y cada modelo comparte su peso con sus copias (w_independencia = 1/n)")
        sS = float("inf"); S = np.ones((n, n))
    else:
        sS = float(np.median(pos)); S = np.exp(-(dij / sS) ** 2)
    wi = 1.0 / (1.0 + (S.sum(axis=1) - np.diag(S)))
    lw = logwp + np.log(wi); lw -= lw.max()                                        # escala logarítmica: el mejor modelo vale 1, la suma nunca es 0
    if (lw < -700).any():
        reglas.append("algún peso < e⁻⁷⁰⁰ queda en 0 (desempeño muy inferior al resto)")
    w = np.exp(lw); w = w / w.sum()
    if not (np.isfinite(w).all() and (w >= 0).all() and abs(w.sum() - 1) < 1e-9):
        raise SesgoError("climwip: los pesos no son finitos, no negativos y normalizados.")
    return pd.DataFrame({"w_desempeno": np.exp(logwp), "w_independencia": wi, "peso": w}, index=mods), {"sigma_D": sD if sD is not None else 0.0, "sigma_S": sS, "reglas": reglas}


def pesos_ponderados_percentil(v, w, q):
    """Percentil ponderado como en el ensamble de las entregas previas: orden por valor, pesos acumulados e interpolación. Exige valores finitos y pesos finitos, ≥ 0 y de suma > 0."""
    v, w = np.asarray(v, float), np.asarray(w, float)
    if not (np.isfinite(v).all() and np.isfinite(w).all() and (w >= 0).all() and w.sum() > 0):
        raise SesgoError("percentil ponderado: valores/pesos no finitos, pesos negativos o suma de pesos 0.")
    o = np.argsort(v); vs, cw = v[o], np.cumsum(w[o]) / w.sum()
    return float(np.interp(q, cw, vs))


NIVELES_Q = [np.array([.03, .08, .13, .18]), np.array([.23, .28, .33, .38]), np.array([.43, .48, .53, .58]), np.array([.63, .68, .73, .78]), np.array([.82, .86, .90, .94, .97, .99, .995])]
NOM_Q = ["Q1 (0–20 %)", "Q2 (20–40 %)", "Q3 (40–60 %)", "Q4 (60–80 %)", "Q5 (80–100 %, extremos)"]


def _qh(s, niveles):
    h = s[s >= UMBRAL_HUMEDO].dropna()
    return np.quantile(h.values, niveles) if len(h) >= 60 else np.full(len(niveles), np.nan)


def pliegues_impar_par(obs, mod, clase=QQM):
    """(serie corregida validada) con calibración impar→par y par→impar: cada año se corrige con un modelo calibrado en años que NO incluyen a ese año."""
    anios = np.arange(1981, 2015); impar, par = anios[anios % 2 == 1], anios[anios % 2 == 0]
    partes = []
    for cal, val in ((impar, par), (par, impar)):
        c = clase().fit(obs[obs.index.year.isin(cal)], mod[mod.index.year.isin(cal)]); partes.append(c.transform(mod[mod.index.year.isin(val)]))
    return pd.concat(partes).sort_index()


def quintiles_ensamble(obs, corr_por_modelo, w_global, w_ind):
    """QMME-lite (Song, Shiru & Chung 2025, sin XGBoost): pesos por QUINTIL de intensidad de día húmedo = exp(-(e_mq/mediana_q)²)·independencia. Se calculan con una mitad de años y se evalúan en la
    OTRA (sin circularidad), y viceversa. Devuelve pesos finales por quintil y la tabla EMME / WMME (ClimWIP global) / QMME / mejor modelo con su RMSE por quintil."""
    mods = list(corr_por_modelo)
    anios = np.arange(1981, 2015); mitades = (anios[anios % 2 == 1], anios[anios % 2 == 0])
    def errores(mitad):
        o = obs[obs.index.year.isin(mitad)]; E = np.full((len(mods), 5), np.nan); Q = {}
        for i, m in enumerate(mods):
            s = corr_por_modelo[m][corr_por_modelo[m].index.year.isin(mitad)]
            for q in range(5):
                Q[(m, q)] = _qh(s, NIVELES_Q[q]); E[i, q] = _rmse(Q[(m, q)], _qh(o, NIVELES_Q[q]))
        return E, Q, {q: _qh(o, NIVELES_Q[q]) for q in range(5)}
    def pesos(E):
        W = np.zeros_like(E)
        for q in range(5):
            e = E[:, q]; fin = np.isfinite(e)                                         # sin dato en el quintil → peso 0 (regla explícita; no se rellena con el peor error)
            if not fin.any():
                raise SesgoError(f"ensamble por quintiles: ningún modelo tiene dato en el quintil {q + 1}.")
            med = float(np.median(e[fin])); med = med if med > 0 else (float(np.median(e[fin][e[fin] > 0])) if (e[fin] > 0).any() else np.inf)      # error 0 en la mayoría → mediana de los positivos; todos 0 → sin discriminar
            lw = np.where(fin, -(np.where(fin, e, 0.0) / med) ** 2 + np.log(np.asarray(w_ind, float)), -np.inf); lw -= lw.max()
            W[:, q] = np.exp(lw); W[:, q] /= W[:, q].sum()
        if not (np.isfinite(W).all() and (W >= 0).all() and np.allclose(W.sum(axis=0), 1)):
            raise SesgoError("pesos por quintil no finitos/normalizados.")
        return W
    res = {k: np.zeros(5) for k in ("EMME", "WMME", "QMME", "mejor")}; Wf = []
    for k in (0, 1):
        Ea, _, _ = errores(mitades[k]); Wa = pesos(Ea); Wf.append(Wa)
        Eb, Qb, Ob = errores(mitades[1 - k])
        for q in range(5):
            qm = np.array([Qb[(m, q)] for m in mods])
            def ens(wv):                                                          # modelos sin dato en el quintil quedan fuera (no se sustituyen por 0)
                m_ok = np.isfinite(qm).all(axis=1) & (np.asarray(wv, float) > 0); return (wv[m_ok, None] * qm[m_ok]).sum(axis=0) / wv[m_ok].sum()
            res["EMME"][q] += _rmse(ens(np.ones(len(mods))), Ob[q]) / 2; res["WMME"][q] += _rmse(ens(np.asarray(w_global)), Ob[q]) / 2; res["QMME"][q] += _rmse(ens(Wa[:, q]), Ob[q]) / 2
            res["mejor"][q] += _rmse(qm[int(np.nanargmin(Ea[:, q]))], Ob[q]) / 2
    return np.mean(Wf, axis=0), {k: [float(x) for x in v] for k, v in res.items()}


# ------------------------------------------------------------------------------------------------ evaluación y ranking
def evaluar(proyecto, id_serie="chirps:celda_nex_mm", k_ensamble=5, salida=None):
    from . import cmip6_descarga as CD
    dec = CD.decision(proyecto)                                  # sin compuerta desde el 14-oct-2026 (decisión del usuario); se conserva si existe
    dh = _carpeta_dl(proyecto, "cmip6_historico")
    if not dh:
        raise SesgoError("Aún no hay modelos históricos descargados (fase «histórico»).")
    obs = referencia(proyecto, id_serie)
    if obs.notna().sum() < 365 * 10:
        raise SesgoError("La referencia observada tiene menos de 10 años de datos en 1981–2014.")
    filas, calib, CH, cor_iop, mod_raw, cor_eqm = [], {}, {}, {}, {}, {}
    for f in sorted(dh.glob("*_historical.csv")):
        modelo = f.name.replace("_historical.csv", "")
        try:
            mod = _leer(f).reindex(obs.index)
            if mod.notna().mean() < 0.95:
                raise SesgoError("serie histórica incompleta")
            raw = metricas(obs, mod); mod_raw[modelo] = mod; CH[modelo] = _clim(mod)
            vi_q = pliegues_impar_par(obs, mod, QQM); vi_e = pliegues_impar_par(obs, mod, EQMAgente); cor_iop[modelo] = vi_q; cor_eqm[modelo] = vi_e
            val_raw, val_q, val_e, val_h = metricas(obs, mod), metricas(obs, vi_q), metricas(obs, vi_e), []
            for (a, b), (c, d) in (PLIEGUES, PLIEGUES[::-1]):                                            # mitades 1981–97 ↔ 1998–2014 (prueba más estricta)
                val_h.append(metricas(obs[c:d], QQM().fit(obs[a:b], mod[a:b]).transform(mod[c:d])))
            hq = np.array([_qh(obs, [.9, .95, .99, .995]), _qh(mod, [.9, .95, .99, .995])])
            fila = {"modelo": modelo, **{k: raw[k] for k in ("bias_total_pct", "bias_p99_pct", "frec_humedos_mod_pct", "rmse_clim_mm_mes", "rmse_cuantiles_mm", "rmse_max_anuales_mm", "corr_clim", "tr100_24h_mod_mm")},
                    "cobertura_efectiva_pct": raw["cobertura_efectiva_pct"], "anios_excluidos": ";".join(map(str, raw["anios_excluidos"])), "meses_excluidos": raw["meses_excluidos"], "meses_normalizados": raw["meses_normalizados"], "calendario": raw["calendario"],
                    "frec_humedos_obs_pct": raw["frec_humedos_obs_pct"], "tr100_24h_obs_mm": raw["tr100_24h_obs_mm"], "d_clim": raw["rmse_clim_mm_mes"], "d_frec": abs(raw["frec_humedos_mod_pct"] - raw["frec_humedos_obs_pct"]),
                    "d_extremos": _rmse(hq[0], hq[1])}
            for k in ("rmse_clim_mm_mes", "rmse_cuantiles_mm", "rmse_max_anuales_mm"):
                fila[k + "_val_original"] = val_raw[k]; fila[k + "_val_qqm"] = val_q[k]; fila[k + "_val_eqm_agente"] = val_e[k]; fila[k + "_val_mitades_qqm"] = float(np.nanmean([x[k] for x in val_h]))
            fila["bias_total_pct_val_qqm"] = val_q["bias_total_pct"]; fila["bias_total_pct_val_eqm_agente"] = val_e["bias_total_pct"]
            fila["mejora_qqm_cuantiles_pct"] = 100 * (1 - fila["rmse_cuantiles_mm_val_qqm"] / max(fila["rmse_cuantiles_mm_val_original"], 1e-9))
            fila["mejora_qqm_cuantiles_mitades_pct"] = 100 * (1 - fila["rmse_cuantiles_mm_val_mitades_qqm"] / max(fila["rmse_cuantiles_mm_val_original"], 1e-9))
            fila["estado"] = "ok"; filas.append(fila)
            calib[modelo] = QQM().fit(obs, mod)                                                           # calibración final con todo 1981–2014
        except Exception as e:
            filas.append({"modelo": modelo, "estado": "descartado", "motivo": str(e)[:160]})
    T = pd.DataFrame(filas); ok = T[T["estado"] == "ok"].copy()
    if len(ok) < 2:
        raise SesgoError("Se necesitan al menos 2 modelos válidos para ordenar y ensamblar.")
    # ---- ClimWIP: distancia de desempeño multi-diagnóstico (climatología, frecuencia de días húmedos, extremos), cada una normalizada por su mediana
    for k in ("d_clim", "d_frec", "d_extremos"):
        ok[k + "_n"] = ok[k] / max(float(ok[k].median()), 1e-9)
    ok["distancia_desempeno"] = ok[["d_clim_n", "d_frec_n", "d_extremos_n"]].mean(axis=1)
    mal = ~np.isfinite(ok["distancia_desempeno"].values) | np.array([not np.isfinite(CH[m]).all() for m in ok["modelo"]])           # valores no finitos: se excluyen y se reportan, no se sustituyen
    if mal.any():
        T = pd.concat([T[~T["modelo"].isin(ok[mal]["modelo"])], ok[mal][["modelo"]].assign(estado="descartado", motivo="métrica o climatología no finita (cobertura insuficiente)")], ignore_index=True)
        ok = ok[~mal].copy()
    if len(ok) < 2:
        raise SesgoError("Se necesitan al menos 2 modelos con métricas finitas para ponderar.")
    pw, sig = climwip(ok.set_index("modelo")["distancia_desempeno"], CH)
    ok = ok.merge(pw, left_on="modelo", right_index=True); ok = ok.sort_values("distancia_desempeno").reset_index(drop=True); ok["posicion"] = np.arange(1, len(ok) + 1)
    mejor_rmse_clim = ok.sort_values("rmse_clim_mm_mes").iloc[0]["modelo"]; mejor = mejor_rmse_clim          # mejor modelo = RMSE más bajo (decisión del usuario)
    cum = ok.sort_values("peso", ascending=False); cum["acum"] = cum["peso"].cumsum()
    sel_modelos = cum[cum["acum"] - cum["peso"] < 0.90]["modelo"].tolist()                                # modelos que reúnen ≥ 90 % del peso: los que necesitan futuro
    sel = ok[ok["modelo"].isin(sel_modelos)].copy().sort_values("peso", ascending=False)
    # ---- ensamble por quintiles
    mods = list(ok["modelo"]); w_g = ok.set_index("modelo").loc[mods, "peso"].values; w_i = ok.set_index("modelo").loc[mods, "w_independencia"].values
    Wq, tabla_q = quintiles_ensamble(obs, {m: cor_iop[m] for m in mods}, w_g, w_i)
    for q in range(5):
        ok[f"peso_q{q + 1}"] = Wq[:, q]
    sel = sel.merge(ok[["modelo"] + [f"peso_q{q + 1}" for q in range(5)]], on="modelo", suffixes=("", "_x")); sel = sel[[c for c in sel.columns if not c.endswith("_x")]]
    # ---- curvas para graficar: mejor modelo y ensamble (calibración completa); validación impar/par
    corr_full = {m: calib[m].transform(mod_raw[m]) for m in mods}; o_m = obs
    nm = lambda v: [None if not np.isfinite(x) else round(float(x), 2) for x in v]
    def ens_q(f, w):   # promedio de cuantiles (vincentización) con pesos w por modelo
        M = np.array([f(corr_full[m]) for m in mods]); return (np.asarray(w)[:, None] * M).sum(axis=0) / np.sum(w)
    pesos_top = ok.set_index("modelo").loc[mods, "peso_q5"].values
    ams_o = np.sort(_ams(o_m)); n = len(ams_o); nq = len(NIV_QQ)
    ens_ams = (pesos_top[:, None] * np.array([np.sort(_ams(corr_full[m]))[-n:] for m in mods])).sum(axis=0) / pesos_top.sum()
    ens_clim = (w_g[:, None] * np.array([_clim(corr_full[m]) for m in mods])).sum(axis=0) / w_g.sum()
    ens_qq = np.zeros(nq)
    for j, lv in enumerate(NIV_QQ):
        q = int(np.searchsorted([0.2, 0.4, 0.6, 0.8], lv, side="right")); M = np.array([_qh(corr_full[m], [lv])[0] for m in mods]); ens_qq[j] = (Wq[:, q] * M).sum() / Wq[:, q].sum()
    def mensual_tot(s): return s.resample("MS").sum(min_count=20).dropna()
    qmes = np.linspace(0.02, 0.98, 49)
    graf = {"clim_mensual": {"obs": nm(_clim(o_m)), "mejor_original": nm(CH[mejor]), "mejor_qqm_impar_par": nm(_clim(cor_iop[mejor])), "mejor_eqm_agente_impar_par": nm(_clim(cor_eqm[mejor])), "ensamble_climwip_qqm": nm(ens_clim)},
            "qq_humedos": {"niveles": NIV_QQ.tolist(), "obs": nm(_qh(o_m, NIV_QQ)), "mejor_original": nm(_qh(mod_raw[mejor], NIV_QQ)), "mejor_qqm": nm(_qh(corr_full[mejor], NIV_QQ)), "mejor_qqm_impar_par": nm(_qh(cor_iop[mejor], NIV_QQ)),
                           "mejor_eqm_agente_impar_par": nm(_qh(cor_eqm[mejor], NIV_QQ)), "ensamble_qqm": nm(ens_qq)},
            "qq_mensual": {"obs": nm(np.quantile(mensual_tot(o_m), qmes)), "original": nm(np.quantile(mensual_tot(mod_raw[mejor]), qmes)), "qqm_impar_par": nm(np.quantile(mensual_tot(cor_iop[mejor]), qmes)), "eqm_agente_impar_par": nm(np.quantile(mensual_tot(cor_eqm[mejor]), qmes))},
            "max_anuales": {"obs": nm(ams_o), "mejor_original": nm(np.sort(_ams(mod_raw[mejor]))[-n:]), "mejor_qqm": nm(np.sort(_ams(corr_full[mejor]))[-n:]), "mejor_eqm_agente": nm(np.sort(_ams(EQMAgente().fit(o_m, mod_raw[mejor]).transform(mod_raw[mejor])))[-n:]),
                            "ensamble_cuantiles_q5": nm(ens_ams)},
            "pesos": {m: {"climwip": float(p), "q5": float(q5)} for m, p, q5 in zip(mods, w_g, pesos_top)},
            "quintiles": {"nombres": NOM_Q, **tabla_q}}
    tr_ens = _gumbel(ens_ams, 100); inf_obs, inf_ens = _gumbel_info(ams_o, 100), _gumbel_info(ens_ams, 100)
    rmse_ref = lambda k: float(ok[k].median())
    resumen = {"creado": datetime.now().isoformat(timespec="seconds"), "referencia": id_serie, "periodo": ["1981-01-01", "2014-12-31"], "n_modelos_evaluados": int(len(T)), "n_validos": int(len(ok)), "k_ensamble": int(len(sel)),
               "mejor_modelo": mejor, "mejor_modelo_por_rmse_climatologia": mejor_rmse_clim, "seleccionados": sel["modelo"].tolist(), "peso_acumulado_seleccionados": float(sel["peso"].sum()),
               "pesos": {m: round(float(p), 4) for m, p in zip(sel["modelo"], sel["peso"])}, "sigma": sig,
               "tr100_24h_obs_mm": float(ok.iloc[0]["tr100_24h_obs_mm"]), "tr100_24h_ensamble_qqm_mm": float(tr_ens), "tr100_24h_mejor_original_mm": float(ok.iloc[0]["tr100_24h_mod_mm"]),
               "mejora_media_qqm_cuantiles_pct": float(ok["mejora_qqm_cuantiles_pct"].mean()), "mejora_media_qqm_cuantiles_mitades_pct": float(ok["mejora_qqm_cuantiles_mitades_pct"].mean()),
               "rmse_clim_val": {"original": rmse_ref("rmse_clim_mm_mes_val_original"), "qqm": rmse_ref("rmse_clim_mm_mes_val_qqm"), "eqm_agente": rmse_ref("rmse_clim_mm_mes_val_eqm_agente")},
               "rmse_cuantiles_val": {"original": rmse_ref("rmse_cuantiles_mm_val_original"), "qqm": rmse_ref("rmse_cuantiles_mm_val_qqm"), "eqm_agente": rmse_ref("rmse_cuantiles_mm_val_eqm_agente")},
               "decision": dec, "reglas_pesos": sig.get("reglas", []),
               "cobertura": {"minimo_por_anio_o_mes": MIN_COBERTURA, "cobertura_efectiva_media_pct": float(ok["cobertura_efectiva_pct"].mean()), "calendarios": sorted(set(ok["calendario"])),
                             "anios_excluidos_por_modelo": {m: a for m, a in zip(ok["modelo"], ok["anios_excluidos"]) if a}, "descartados": T[T["estado"] != "ok"].reindex(columns=["modelo", "motivo"]).to_dict("records"),
                             "regla": "un año/mes solo cuenta si tiene ≥ 90 % de los días ESPERADOS del calendario del producto (las fechas ausentes cuentan como faltantes); meses con huecos aceptados se normalizan y se cuentan."},
               "tr100_incertidumbre": {"observado": inf_obs, "ensamble_qqm": inf_ens, "nota": "Tr100 con ≤ 34 años efectivos es extrapolación: no certificable; usar el intervalo (bootstrap p5–p95 por momentos) y no el valor puntual."},
               "metodo": {"seleccion_y_pesos": "ClimWIP (Brunner et al. 2020, Earth Syst. Dyn. 11:995): peso = desempeño × independencia; desempeño = distancia normalizada media de 3 diagnósticos (RMSE de la climatología mensual, "
                                               "|sesgo de frecuencia de días húmedos|, RMSE de cuantiles extremos p90–p99,5) con σ_D = mediana; independencia por distancia entre climatologías con σ_S = mediana (criterio de las entregas de Machala/Gualaquiza).",
                          "correccion": "QQM mensual con ajuste de frecuencia de días húmedos (hist.) y QDM (Cannon et al. 2015, J. Climate 28:6938) para el futuro: preserva el cambio relativo de los cuantiles y evita inflar extremos. "
                                        "NEX-GDDP ya está corregido por NASA (BCSD, cuantiles con ventana ±15 días contra GMFD 1960–2014; Thrasher et al. 2022, Sci. Data 9:262) y subestima extremos por difusión espacial: la corrección local se compara contra el original.",
                          "validacion": "validación cruzada IMPAR/PAR (cada año se corrige con un modelo calibrado en los otros años; como en las entregas previas) y, más estricta, mitades 1981–97 ↔ 1998–2014; verificación independiente 2015–2025.",
                          "ensamble": "dos ensambles: (A) mediana ponderada y p10–p90 de los factores de cada modelo con pesos ClimWIP (criterio de las entregas previas) y (B) ensamble POR QUINTILES de intensidad de día húmedo con promedio de cuantiles "
                                      "(vincentización; QMME de Song, Shiru & Chung 2025, Mach. Learn.: Sci. Technol., versión sin XGBoost): pesos por quintil = exp(−(error_quintil/mediana)²)·independencia, calculados en una mitad de años y evaluados en la otra.",
                          "umbral_humedo_mm": UMBRAL_HUMEDO},
               "advertencias": ["Línea base asumida por decisión del usuario; no calibrada ni validada.", "El producto NEX-GDDP ya está corregido por sesgo (BCSD): se reporta la corrección local contra el modelo original.",
                                "Un modelo climático reproduce la distribución, no el día: no se calcula RMSE día a día.", "Con ~30–34 años, Tr100 por Gumbel es una extrapolación muy incierta y NO certificable (ver tr100_incertidumbre).", SUPUESTO_IDF,
                                "La referencia es CHIRPS (satélite) en la celda de 0,25° del modelo; CHIRPS no es verdad de campo y puede subestimar extremos puntuales."]}
    carpeta = Path(salida or Path(proyecto) / "registro" / "cmip6") / f"analisis_{datetime.now():%Y%m%d_%H%M%S}"
    carpeta.mkdir(parents=True)
    cols_fuera = [c for c in ok.columns if c.endswith("_n")]
    pd.concat([ok.drop(columns=["estado"] + cols_fuera, errors="ignore"), T[T["estado"] != "ok"]]).to_csv(carpeta / "metricas_modelos.csv", index=False)
    sel.to_csv(carpeta / "seleccionados.csv", index=False)
    (carpeta / "resumen_analisis.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    (carpeta / "graficas.json").write_text(json.dumps(graf, ensure_ascii=False), encoding="utf-8")
    (carpeta / "calibracion_qqm.json").write_text(json.dumps({m: {str(k): {"umbral": v["umbral"], "qo": v["qo"].tolist(), "qg": v["qg"].tolist()} for k, v in calib[m].m.items()} for m in mods}), encoding="utf-8")
    return {"carpeta": str(carpeta), "resumen": resumen, "ranking": ok, "seleccionados": sel, "graficas": graf}


# ------------------------------------------------------------------------------------------------ futuro por bloques y verificación independiente
BLOQUES_FUT = (("2015-01-01", "2039-12-31"), ("2040-01-01", "2069-12-31"), ("2070-01-01", "2100-12-31"))


def qdm_por_bloques(q, fut, h_raw):
    """QDM aplicado por bloques de ~30 años (el delta de cada bloque se mide contra el histórico del propio modelo)."""
    partes = [q.transform_qdm(fut[a:b], h_raw) for a, b in BLOQUES_FUT if len(fut[a:b]) > 0]
    return pd.concat(partes)


def _cargar_cal(car):
    return {m: {int(k): {"umbral": v["umbral"], "qo": np.array(v["qo"]), "qg": np.array(v["qg"])} for k, v in d.items()} for m, d in json.loads((Path(car) / "calibracion_qqm.json").read_text(encoding="utf-8")).items()}


def verificacion_independiente(proyecto, car, res, cal):
    """2015–2025 (SSP5-8.5): datos observados que la calibración no vio. Compara el modelo ORIGINAL (NEX), el corregido QQM/QDM y el EQM de las entregas previas con la referencia."""
    dh = _carpeta_dl(proyecto, "cmip6_historico")
    obs = referencia_larga(proyecto, res["referencia"])["2015-01-01":"2025-12-31"]
    if obs.notna().sum() < 365 * 8:
        return None
    filas = []
    for m, w in res["pesos"].items():
        fut = leer_futuro(proyecto, m)
        if fut is None or fut.index.min() > pd.Timestamp("2015-02-01"):
            continue
        h_raw = _leer(dh / f"{m}_historical.csv"); ho = referencia(proyecto, res["referencia"]); q = QQM(); q.m = cal[m]
        e = EQMAgente().fit(ho, h_raw.reindex(ho.index))
        raw = fut["2015-01-01":"2025-12-31"].reindex(obs.index); cor = qdm_por_bloques(q, fut, h_raw)["2015-01-01":"2025-12-31"].reindex(obs.index); eq = e.transform(fut["2015-01-01":"2025-12-31"]).reindex(obs.index)
        for ver, ser in (("original NEX", raw), ("QQM/QDM", cor), ("EQM (método Machala/Gualaquiza)", eq)):
            mt = metricas(obs, ser); filas.append({"modelo": m, "version": ver, "peso": w, **{k: mt[k] for k in ("bias_total_pct", "rmse_clim_mm_mes", "rmse_cuantiles_mm", "rmse_max_anuales_mm")}})
    if not filas:
        return None
    V = pd.DataFrame(filas)
    for ver, g in V.groupby("version"):
        filas.append({"modelo": "ENSAMBLE (promedio ponderado)", "version": ver, "peso": 1.0, **{k: float(np.average(g[k], weights=g["peso"])) for k in ("bias_total_pct", "rmse_clim_mm_mes", "rmse_cuantiles_mm", "rmse_max_anuales_mm")}})
    V = pd.DataFrame(filas).drop(columns=["peso"]); V.to_csv(Path(car) / "verificacion_2015_2025.csv", index=False)
    return V


# ------------------------------------------------------------------------------------------------ factores de cambio
TRS = (2, 5, 10, 25, 50, 100)
VERSIONES = ("QQM/QDM", "QQM/QDM · ensamble de cuantiles", "EQM (método Machala/Gualaquiza)", "original NEX")


SUPUESTO_IDF_CORTO = "supuesto exploratorio: factor de 24 h aplicado a todas las duraciones; IDF no validada"


def _estado_tr(metrica, n):
    if not metrica.startswith("Tr"):
        return ""
    return _gumbel_info(np.arange(n, dtype=float) + 1.0, int(metrica[2:].split()[0]))["estado"]      # el estado depende solo de n y Tr


def _kpis(s):
    am = _ams(s); d = {f"Tr{t} de 24 h": _gumbel(am, t) for t in TRS}
    d["total anual"] = float(s.groupby(s.index.year).sum().mean()); d["percentil 99 diario"] = float(np.quantile(s.dropna(), .99)); return d, am


def factores(proyecto, carpeta_analisis=None, id_serie=None):
    base = Path(proyecto) / "registro" / "cmip6"
    car = Path(carpeta_analisis) if carpeta_analisis else sorted(base.glob("analisis_*"))[-1]
    res = json.loads((car / "resumen_analisis.json").read_text(encoding="utf-8")); cal = _cargar_cal(car)
    dh = _carpeta_dl(proyecto, "cmip6_historico")
    met = pd.read_csv(car / "metricas_modelos.csv"); met = met[met["modelo"].isin(cal)].set_index("modelo")
    obs = referencia(proyecto, res["referencia"])
    por_modelo, vinc = [], {}
    modelos = [m for m in met.index if leer_futuro(proyecto, m) is not None]
    if not modelos:
        raise SesgoError("Aún no hay futuro descargado (fase «futuro»).")
    for m in modelos:
        q = QQM(); q.m = cal[m]; h_raw = _leer(dh / f"{m}_historical.csv"); fut = leer_futuro(proyecto, m); e = EQMAgente().fit(obs, h_raw.reindex(obs.index))
        h_cor = q.transform(h_raw); h_eqm = e.transform(h_raw)
        for hor, (a, b) in HORIZONTES.items():
            fr = fut[a:b]
            if len(fr) < 365 * 25:
                continue
            fc, fe = q.transform_qdm(fr, h_raw), e.transform(fr)
            kh = {"QQM/QDM": _kpis(h_cor), "original NEX": _kpis(h_raw), "EQM (método Machala/Gualaquiza)": _kpis(h_eqm)}
            kf = {"QQM/QDM": _kpis(fc), "original NEX": _kpis(fr), "EQM (método Machala/Gualaquiza)": _kpis(fe)}
            vinc[(hor, m)] = (np.sort(kh["QQM/QDM"][1]), np.sort(kf["QQM/QDM"][1]))
            ne = int(min(len(kh["QQM/QDM"][1]), len(kf["QQM/QDM"][1])))
            for met_ in kh["QQM/QDM"][0]:
                ic = (np.nan, np.nan)
                if met_.startswith("Tr") and ne >= MIN_ANIOS_GUMBEL:
                    tr_ = int(met_[2:].split()[0]); r = _boot_gumbel_momentos(kf["QQM/QDM"][1], tr_) / _boot_gumbel_momentos(kh["QQM/QDM"][1], tr_, seed=54321); ic = (float(np.nanpercentile(r, 5)), float(np.nanpercentile(r, 95)))
                por_modelo.append({"escenario": "ssp585", "horizonte": hor, "metrica": met_, "modelo": m, "peso": float(met.loc[m, "peso"]), "peso_q5": float(met.loc[m, "peso_q5"]) if "peso_q5" in met.columns else float(met.loc[m, "peso"]),
                                   "anios_efectivos": ne, "ic90_factor_inf": ic[0], "ic90_factor_sup": ic[1], "avisos_qdm": int(sum(getattr(q, "avisos", {}).values())),
                                   "factor_corregido": kf["QQM/QDM"][0][met_] / kh["QQM/QDM"][0][met_] if kh["QQM/QDM"][0][met_] else np.nan,
                                   "factor_original": kf["original NEX"][0][met_] / kh["original NEX"][0][met_] if kh["original NEX"][0][met_] else np.nan,
                                   "factor_agente": kf["EQM (método Machala/Gualaquiza)"][0][met_] / kh["EQM (método Machala/Gualaquiza)"][0][met_] if kh["EQM (método Machala/Gualaquiza)"][0][met_] else np.nan})
    P = pd.DataFrame(por_modelo)
    if P.empty:
        raise SesgoError("No hay series futuras completas para las ventanas de análisis.")
    cobertura = float(met.loc[modelos, "peso"].sum() / met["peso"].sum())
    out = []
    colv = {"QQM/QDM": "factor_corregido", "original NEX": "factor_original", "EQM (método Machala/Gualaquiza)": "factor_agente"}
    for (hor, metr), g in P.groupby(["horizonte", "metrica"]):
        for ver, col in colv.items():
            v, w = g[col].values, g["peso"].values; ok = np.isfinite(v)
            if ok.sum() < 2:
                continue
            out.append({"escenario": "ssp585", "horizonte": hor, "metrica": metr, "version": ver, "mediana_ponderada": pesos_ponderados_percentil(v[ok], w[ok], 0.5), "p10": pesos_ponderados_percentil(v[ok], w[ok], 0.10),
                        "p90": pesos_ponderados_percentil(v[ok], w[ok], 0.90), "min": float(v[ok].min()), "max": float(v[ok].max()), "n_modelos": int(ok.sum()), "cobertura_peso": cobertura,
                        "anios_efectivos": int(g["anios_efectivos"].min()), "estado_estimacion": _estado_tr(metr, int(g["anios_efectivos"].min())), "supuesto": SUPUESTO_IDF_CORTO if metr.startswith("Tr") else ""})
    # ensamble de cuantiles (vincentización de los máximos anuales con pesos del quintil extremo)
    for hor in HORIZONTES:
        ms = [m for m in modelos if (hor, m) in vinc]
        if len(ms) < 2:
            continue
        w5 = np.array([P[(P["modelo"] == m) & (P["horizonte"] == hor)]["peso_q5"].iloc[0] for m in ms]); w5 = w5 / w5.sum()
        lv = np.linspace(0.02, 0.98, 30)
        qh = sum(wi * np.interp(lv, (np.arange(len(vinc[(hor, m)][0])) + .5) / len(vinc[(hor, m)][0]), vinc[(hor, m)][0]) for wi, m in zip(w5, ms))
        qf = sum(wi * np.interp(lv, (np.arange(len(vinc[(hor, m)][1])) + .5) / len(vinc[(hor, m)][1]), vinc[(hor, m)][1]) for wi, m in zip(w5, ms))
        for t in TRS:
            fq = _gumbel(qf, t) / _gumbel(qh, t); g = P[(P["horizonte"] == hor) & (P["metrica"] == f"Tr{t} de 24 h")]; v = g["factor_corregido"].values; w = g["peso"].values; ok = np.isfinite(v)
            out.append({"escenario": "ssp585", "horizonte": hor, "metrica": f"Tr{t} de 24 h", "version": "QQM/QDM · ensamble de cuantiles", "mediana_ponderada": float(fq), "p10": pesos_ponderados_percentil(v[ok], w[ok], 0.10),
                        "p90": pesos_ponderados_percentil(v[ok], w[ok], 0.90), "min": float(v[ok].min()), "max": float(v[ok].max()), "n_modelos": len(ms), "cobertura_peso": cobertura,
                        "anios_efectivos": int(g["anios_efectivos"].min()), "estado_estimacion": _estado_tr(f"Tr{t}", int(g["anios_efectivos"].min())), "supuesto": SUPUESTO_IDF_CORTO})
    F = pd.DataFrame(out)
    try:
        V = verificacion_independiente(proyecto, car, res, cal)
    except Exception:
        V = None
    F.to_csv(car / "factores_cc.csv", index=False); P.to_csv(car / "factores_por_modelo.csv", index=False)
    nota = {"supuesto_idf": SUPUESTO_IDF, "nota_tr": "Tr100 con pocos años efectivos es extrapolación: ver anios_efectivos, estado_estimacion y el intervalo ic90_factor_* por modelo (factores_por_modelo.csv); no certificable. ",
            "nota": "Proyecciones, no predicciones. Factor = futuro/histórico del propio modelo, ambos corregidos (QDM preserva la señal relativa). Línea base asumida por decisión del usuario; no calibrada ni validada. "
                    f"Los pesos son ClimWIP (desempeño × independencia); los modelos con futuro descargado reúnen {cobertura * 100:.0f} % del peso total. Tr100 con 30 años es una extrapolación muy incierta: usar el rango p10–p90 y no el valor central solo.",
            "decision": res["decision"], "cobertura_peso": cobertura}
    (car / "factores_cc.json").write_text(json.dumps({**nota, "factores": F.to_dict("records")}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return {"carpeta": str(car), "factores": F, "por_modelo": P, "verificacion": V, **nota}


def idf_ajustada(proyecto, horizonte, estadistico="mediana", version="QQM/QDM", carpeta_analisis=None):
    """Vector de factores por Tr (2…100) de 24 h para ajustar la IDF oficial (IDF_ajustada(Tr, d) = IDF(Tr, d) × factor(Tr)), como en las entregas previas.
    ES UN SUPUESTO EXPLORATORIO (ver SUPUESTO_IDF): cambio uniforme por duración, sin respaldo independiente sobre intensidades subdiarias; la IDF resultante no está validada."""
    base = Path(proyecto) / "registro" / "cmip6"; car = Path(carpeta_analisis) if carpeta_analisis else sorted(base.glob("analisis_*"))[-1]
    F = pd.read_csv(car / "factores_cc.csv"); F = F[(F["horizonte"] == horizonte) & (F["version"] == version)]
    col = {"mediana": "mediana_ponderada", "p10": "p10", "p90": "p90"}[estadistico]
    v = {}
    for t in TRS:
        r = F[F["metrica"] == f"Tr{t} de 24 h"]
        if r.empty:
            raise SesgoError(f"Faltan factores de Tr{t} para {horizonte}.")
        v[t] = float(r.iloc[0][col])
    return v


# ------------------------------------------------------------------------------------------------ agregados anuales desde la base de datos (para graficar crudo vs corregido)
def anual(proyecto, minimo_dias=330):
    from . import basedatos as BD
    c = BD.abrir(proyecto, solo_lectura=True)
    try:
        sel = [r[0] for r in c.execute("SELECT modelo FROM cmip6_modelos WHERE seleccionado=1 ORDER BY posicion")]
        peso = dict(c.execute("SELECT modelo, peso FROM cmip6_modelos WHERE seleccionado=1").fetchall())
        if not sel:
            raise SesgoError("La base de datos aún no tiene el análisis CMIP6 (sincroniza).")
        d = pd.read_sql_query("SELECT modelo, escenario, CAST(substr(fecha,1,4) AS INTEGER) AS anio, SUM(pr_original_mm) AS tot_o, SUM(pr_corregida_mm) AS tot_c, MAX(pr_original_mm) AS max_o, MAX(pr_corregida_mm) AS max_c, COUNT(*) AS n "
                              f"FROM cmip6_series WHERE modelo IN ({','.join('?' * len(sel))}) GROUP BY modelo, escenario, anio", c, params=sel)
        ref = pd.read_sql_query("SELECT fecha, mm FROM referencia_lluvia ORDER BY fecha", c)
    finally:
        c.close()
    d = d[d["n"] >= minimo_dias]
    ref["fecha"] = pd.to_datetime(ref["fecha"]); g = ref.set_index("fecha")["mm"]; g = g.groupby(g.index.year)
    ok = g.count() >= 0.9 * g.size(); obs = {"anios": [int(a) for a in g.sum()[ok].index], "total_mm": [round(float(v), 1) for v in g.sum()[ok]], "max_dia_mm": [round(float(v), 1) for v in g.max()[ok]]}
    out = {"obs": obs, "modelos": sel, "pesos": {m: float(v) for m, v in peso.items()}, "escenarios": {}}
    for esc, e in d.groupby("escenario"):
        piv = lambda col: e.pivot(index="anio", columns="modelo", values=col)
        reg = {"anios": [int(a) for a in sorted(e["anio"].unique())]}
        for col in ("tot_o", "tot_c", "max_o", "max_c"):
            P = piv(col).reindex(reg["anios"])
            reg[col] = {"p10": [None if not np.isfinite(v) else round(float(v), 1) for v in P.quantile(.1, axis=1)], "mediana": [None if not np.isfinite(v) else round(float(v), 1) for v in P.median(axis=1)],
                        "p90": [None if not np.isfinite(v) else round(float(v), 1) for v in P.quantile(.9, axis=1)]}
        out["escenarios"][esc] = reg
    return out
