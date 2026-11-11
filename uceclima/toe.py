# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Time of Emergence (ToE) de la lluvia: año en que la señal de cambio (Y, SSP5-8.5) sale del ruido.

Gamma (21-oct-2026), alineado con el proceso de Machala/Gualaquiza (scripts 22 y 26; Hawkins y Sutton 2012, Lickley et al. 2024):
  · Series diarias por modelo con sesgo corregido: histórico 1981–2014 con QQM y futuro 2015–2100 con QDM (los mismos ajustes del módulo CMIP6).
  · Índices anuales (ETCCDI + sequía): PRCPTOT, Rx1day, Rx5day, R20mm, R95pTOT, SDII, CDD, CWD, SPI-12 mínimo y meses con SPI-3 ≤ −1.
    El umbral de R95pTOT y el ajuste gamma del SPI se calculan en el periodo base de CADA modelo (no se mezcla con la observación).
  · Periodo base 1981–2014. Ruido interno de cada modelo = desviación estándar interanual del índice en la base, SIN tendencia lineal.
  · ENSAMBLE (método de Machala/Gualaquiza): anomalía A_m(t) = media móvil centrada de `ventana` años − media base del modelo.
      Señal S(t) = media ponderada (pesos ClimWIP) de A_m(t).
      Ruido N(t) = √( Σ w·σ_int,m² + Σ w·(A_m(t) − S(t))² )   ← variabilidad interna + dispersión entre modelos.
      ToE = primer año desde el cual |S/N| ≥ umbral en TODOS los años siguientes, con el mismo signo.
    Si los modelos discrepan (unos suben y otros bajan), la dispersión infla el ruido y el ensamble NO emerge: no se promedian
    años de emergencia de signos opuestos (falla G18 de la Beta 3).
  · Diagnóstico por modelo: ToE de cada modelo con su propio ruido; el rango p10–p90 se da SOLO con los modelos del mismo signo que el ensamble.
  · Robustez: fracción del peso cuyo modelo tiene el mismo signo que el ensamble al final del periodo evaluable (≥ 0,66 = acuerdo «probable»).
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE = (1981, 2014)
INDICES = {"PRCPTOT": "Total anual (mm)", "Rx1day": "Máximo de 1 día (mm)", "Rx5day": "Máximo de 5 días (mm)", "R20mm": "Días con ≥ 20 mm",
           "R95pTOT": "Lluvia en días muy húmedos > p95 (mm)", "SDII": "Intensidad media en días de lluvia (mm/día)",
           "CDD": "Racha seca máxima, días < 1 mm (CDD)", "CWD": "Racha húmeda máxima, días ≥ 1 mm (CWD)",
           "SPI12_min": "SPI-12 mínimo del año (sequía)", "SPI3_secos": "Meses con SPI-3 ≤ −1 (sequía)"}
SEQUIA = {"CDD", "SPI3_secos"}                     # en estos un AUMENTO es más seco; en SPI12_min una DISMINUCIÓN es más seco


class ToEError(Exception):
    pass


def _racha(cond, anios):
    """Racha máxima de días consecutivos que cumplen `cond`, asignada al año en que empieza (como el script 22 de Machala)."""
    c = np.asarray(cond, bool); gid = np.cumsum(np.r_[True, c[1:] != c[:-1]])
    d = pd.DataFrame({"c": c, "g": gid, "a": np.asarray(anios)})
    ev = d[d.c].groupby("g").agg(dur=("c", "size"), anio=("a", "first"))
    return ev.groupby("anio").dur.max()


def _spi(mensual, k, base=BASE):
    """SPI-k (McKee et al. 1993): sumas móviles de k meses; gamma ajustada por mes calendario en el periodo base, con probabilidad de cero."""
    from scipy import stats
    x = mensual.rolling(k, min_periods=k).sum(); out = pd.Series(np.nan, index=x.index)
    for mes in range(1, 13):
        sel = x.index.month == mes; v = x[sel]; b = v[(v.index.year >= base[0]) & (v.index.year <= base[1])].dropna()
        if len(b) < 20:
            continue
        q0 = float((b <= 0).mean()); pos = b[b > 0]
        if len(pos) < 10:
            continue
        a, loc, esc = stats.gamma.fit(pos.values, floc=0)
        p = q0 + (1 - q0) * stats.gamma.cdf(np.maximum(v.values, 0), a, loc=0, scale=esc)
        out[sel] = stats.norm.ppf(np.clip(p, 1e-6, 1 - 1e-6))
    return out


def indices_anuales(s, base=BASE):
    """s: Series diaria (mm/día). Devuelve DataFrame por año (solo años con ≥ 90 % de días). Umbral p95 y SPI con el periodo base de la propia serie."""
    s = s.astype(float).sort_index()
    g = s.groupby(s.index.year); ok = g.count() >= 0.9 * 365
    sb = s[(s.index.year >= base[0]) & (s.index.year <= base[1])]
    p95 = float(sb[sb >= 1].quantile(0.95)) if (sb >= 1).sum() > 50 else np.nan
    humedo = s >= 1
    df = pd.DataFrame({"PRCPTOT": g.sum(), "Rx1day": g.max(), "Rx5day": s.rolling(5, min_periods=5).sum().groupby(s.index.year).max(),
                       "R20mm": (s >= 20).groupby(s.index.year).sum(),
                       "R95pTOT": s.where(s > p95, 0).groupby(s.index.year).sum() if np.isfinite(p95) else np.nan,
                       "SDII": s[humedo].groupby(s.index.year[humedo]).mean()})
    v = s.dropna()
    df["CDD"] = _racha(v.values < 1, v.index.year); df["CWD"] = _racha(v.values >= 1, v.index.year)
    df[["CDD", "CWD"]] = df[["CDD", "CWD"]].fillna(0)
    men = s.resample("MS").sum(min_count=25)
    s12, s3 = _spi(men, 12, base), _spi(men, 3, base)
    df["SPI12_min"] = s12.groupby(s12.index.year).min(); df["SPI3_secos"] = (s3 <= -1).groupby(s3.index.year).sum().where(s3.groupby(s3.index.year).count() > 0)
    return df[ok]


def _ruido_base(b):
    """Desviación estándar interanual de la base SIN tendencia lineal (Machala/Gualaquiza)."""
    x = np.asarray(b.index, float); y = b.values.astype(float)
    if np.allclose(y, y[0]):
        return 0.0
    r = y - np.polyval(np.polyfit(x, y, 1), x)
    return float(np.std(r, ddof=2))


def _anomalia(anual, ventana, base):
    a = anual.dropna().sort_index()
    b = a[(a.index >= base[0]) & (a.index <= base[1])]
    if len(b) < 20:
        raise ToEError("El periodo base tiene menos de 20 años válidos.")
    n = _ruido_base(b)
    if not np.isfinite(n) or n <= 0:
        raise ToEError("Ruido nulo en el periodo base.")
    a = a.reindex(range(int(a.index.min()), int(a.index.max()) + 1))
    m = a.rolling(ventana, center=True, min_periods=int(0.8 * ventana)).mean()
    an = (m - float(b.mean())).dropna()
    return an[an.index > base[1] - ventana // 2], n, float(b.mean())


def _emergencia(sn, umbral):
    if not len(sn):
        return None, 0
    arriba = (sn.abs() >= umbral).values; signos = np.sign(sn.values)
    for i in range(len(sn)):
        if arriba[i:].all() and len(set(signos[i:])) == 1:
            return int(sn.index[i]), int(signos[i])
    return None, 0


def toe_serie(anual, ventana=20, umbral=1.0, base=BASE):
    """ToE de UN modelo con su propio ruido. Devuelve dict con ToE (o None), signo, S/N por año y el ruido."""
    an, n, mb = _anomalia(anual, ventana, base)
    sn = an / n
    toe, signo = _emergencia(sn, umbral)
    return {"toe": toe, "signo": signo, "ruido": n, "media_base": mb, "ultimo_anio": int(sn.index.max()) if len(sn) else None, "sn": sn}


def toe_ensamble(series_ind, pesos, ventana=20, umbral=1.0, base=BASE):
    """series_ind: {modelo: Series anual del índice}; pesos: {modelo: w}. Señal = media ponderada de anomalías; ruido = √(interno² + entre modelos²)."""
    A, sig, w = {}, {}, {}
    for m, s in series_ind.items():
        try:
            an, n, _ = _anomalia(s, ventana, base)
        except ToEError:
            continue
        A[m], sig[m], w[m] = an, n, float(pesos.get(m, 1.0))
    if not A:
        raise ToEError("Ningún modelo tiene base suficiente para este índice.")
    D = pd.DataFrame(A).dropna(how="any")
    if D.empty:
        raise ToEError("Los modelos no tienen años comunes.")
    W = np.array([w[m] for m in D.columns]); W = W / W.sum()
    S = D.values @ W
    var_int = float(np.sum(W * np.array([sig[m] ** 2 for m in D.columns])))
    var_mod = ((D.values - S[:, None]) ** 2) @ W
    N = np.sqrt(var_int + var_mod)
    sn = pd.Series(S / N, index=D.index)
    toe, signo = _emergencia(sn, umbral)
    ult = D.iloc[-1]; acuerdo = float(np.sum(W[np.sign(ult.values) == np.sign(S[-1])])) if S[-1] != 0 else 0.0
    return {"toe": toe, "signo": signo, "sn": sn, "senal": pd.Series(S, index=D.index), "ruido_interno": float(np.sqrt(var_int)),
            "ruido_entre_modelos_final": float(np.sqrt(var_mod[-1])), "acuerdo_signo": acuerdo, "signo_final": int(np.sign(S[-1])), "modelos": list(D.columns)}


def _pct_ponderado(v, w, q):
    o = np.argsort(v); v, w = np.asarray(v)[o], np.asarray(w)[o]; c = np.cumsum(w) / w.sum()
    return float(np.interp(q, c, v))


def _texto_signo(ind, s):
    if not s:
        return ""
    if ind in SEQUIA:
        return "más seco" if s > 0 else "menos seco"
    if ind == "SPI12_min":
        return "más seco" if s < 0 else "más húmedo"
    return "aumento" if s > 0 else "disminución"


def calcular(proyecto, ventana=20, umbrales=(1.0, 2.0), salida=None):
    from . import cmip6_sesgo as SB
    proyecto = Path(proyecto)
    base = proyecto / "registro" / "cmip6"; cars = sorted(base.glob("analisis_*")) if base.exists() else []
    if not cars:
        raise ToEError("Primero evalúa los modelos (CMIP6 · paso 2).")
    car = cars[-1]; cal = SB._cargar_cal(car)
    met = pd.read_csv(car / "metricas_modelos.csv").set_index("modelo")
    pesos = {m: float(met.loc[m, "peso"]) if m in met.index and "peso" in met.columns else 1.0 for m in cal}
    dh = SB._carpeta_dl(proyecto, "cmip6_historico")
    modelos = [m for m in cal if SB.leer_futuro(proyecto, m) is not None]
    if not modelos:
        raise ToEError("Falta el futuro: descarga el futuro de los mejores modelos (CMIP6 · paso 3).")
    filas, series = [], {}
    for m in modelos:
        q = SB.QQM(); q.m = cal[m]
        h_raw = SB._leer(dh / f"{m}_historical.csv"); fut = SB.leer_futuro(proyecto, m)
        cont = pd.concat([q.transform(h_raw), q.transform_qdm(fut, h_raw)]).sort_index()
        series[m] = indices_anuales(cont[~cont.index.duplicated()])
        for ind in INDICES:
            for u in umbrales:
                try:
                    r = toe_serie(series[m][ind], ventana, u)
                except (ToEError, KeyError) as e:
                    r = {"toe": None, "signo": 0, "ruido": np.nan, "media_base": np.nan, "ultimo_anio": None}
                filas.append({"modelo": m, "indice": ind, "umbral_sn": u, "toe": r["toe"], "signo": _texto_signo(ind, r["signo"]), "signo_num": r["signo"],
                              "ruido_sin_tendencia": r["ruido"], "media_base": r["media_base"], "ultimo_anio_evaluable": r["ultimo_anio"], "peso": pesos[m]})
    P = pd.DataFrame(filas)
    res, sn_ens = [], {}
    for ind in INDICES:
        for u in umbrales:
            fila = {"indice": ind, "nombre": INDICES[ind], "umbral_sn": u, "n_modelos": len(modelos)}
            try:
                e = toe_ensamble({m: series[m][ind] for m in modelos}, pesos, ventana, u)
            except ToEError as ex:
                fila.update(toe_ensamble=None, signo=_texto_signo(ind, 0), acuerdo_signo=None, toe_p10=None, toe_p90=None, nota=str(ex)); res.append(fila); continue
            if u == umbrales[0]:
                sn_ens[ind] = e["sn"]
            g = P[(P.indice == ind) & (P.umbral_sn == u) & (P.signo_num == (e["signo"] or e["signo_final"])) & P.toe.notna()]
            fila.update(toe_ensamble=e["toe"], signo=_texto_signo(ind, e["signo"] or e["signo_final"]), acuerdo_signo=round(e["acuerdo_signo"], 2),
                        robustez="probable" if e["acuerdo_signo"] >= 0.66 else "sin acuerdo entre modelos",
                        ruido_interno=round(e["ruido_interno"], 3), ruido_entre_modelos_final=round(e["ruido_entre_modelos_final"], 3),
                        fraccion_peso_mismo_signo_que_emerge=round(float(g.peso.sum() / sum(pesos[m] for m in modelos)), 3),
                        toe_p10=round(_pct_ponderado(g.toe.values, g.peso.values, 0.1)) if len(g) else None,
                        toe_p90=round(_pct_ponderado(g.toe.values, g.peso.values, 0.9)) if len(g) else None)
            fila["toe_mediana"] = fila["toe_ensamble"]                  # compatibilidad con lectores anteriores: ahora es el ToE del ENSAMBLE (S/N total)
            res.append(fila)
    R = pd.DataFrame(res)
    out = Path(salida) if salida else base / f"toe_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True, exist_ok=False)
    P.drop(columns="signo_num").to_csv(out / "toe_por_modelo.csv", index=False, encoding="utf-8-sig"); R.to_csv(out / "toe_ensamble.csv", index=False, encoding="utf-8-sig")
    pd.concat({m: d for m, d in series.items()}, names=["modelo", "anio"]).to_csv(out / "indices_anuales_por_modelo.csv", encoding="utf-8-sig")
    try:
        P.drop(columns="signo_num").to_excel(out / "toe_por_modelo.xlsx", index=False); R.to_excel(out / "toe_ensamble.xlsx", index=False)
    except Exception:
        pass
    sn = {}
    for m, ia in series.items():
        for ind in INDICES:
            try:
                r = toe_serie(ia[ind], ventana, umbrales[0]); x = r["sn"].reindex(range(int(r["sn"].index.min()), int(r["sn"].index.max()) + 1))
                sn.setdefault(ind, {})[m] = {"anios": [int(i) for i in x.index], "sn": [None if not np.isfinite(v) else round(float(v), 3) for v in x.values]}
            except (ToEError, KeyError, ValueError):
                pass
    sn_e = {ind: {"anios": [int(i) for i in s.index], "sn": [round(float(v), 3) for v in s.values]} for ind, s in sn_ens.items()}
    continuos = [m for m, ia in series.items() if all(y in ia.index for y in range(2015, 2040))]
    cobertura = (f"{len(continuos)} de {len(series)} modelos con futuro continuo 2015–2100; el resto solo desde 2040 (descarga por ventanas): "
                 "su S/N empieza en 2040 y el ToE anterior a ~2050 no se puede detectar en ellos. Para un ToE completo, descarga el futuro desde 2015.") if len(continuos) < len(series) else "todos los modelos con futuro continuo 2015–2100"
    meta = {"analisis": car.name, "cobertura_temporal": cobertura, "modelos_futuro_continuo": continuos, "modelos": modelos, "ventana_anios": ventana, "umbrales_sn": list(umbrales),
            "periodo_base": list(BASE), "escenario": "ssp585", "version_metodo": "Gamma · ensamble con ruido total (Machala/Gualaquiza)",
            "metodo": "ensamble: señal = media ponderada ClimWIP de las anomalías (media móvil centrada − media base); ruido = √(variabilidad interna sin tendencia² + dispersión entre modelos²); emerge cuando |S/N| ≥ umbral en todos los años siguientes con el mismo signo. Por modelo: diagnóstico con su propio ruido.",
            "nota": "Proyección bajo SSP5-8.5 con sesgo corregido (QQM/QDM); no es una predicción. Con pocos modelos (p. ej. 3, pedagógico) la dispersión entre modelos está mal estimada."}
    (out / "toe_resumen.json").write_text(json.dumps({"meta": meta, "ensamble": R.replace({np.nan: None}).to_dict("records"), "sn": sn, "sn_ensamble": sn_e}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    try:
        (out / "toe_sn.png").write_bytes(figura(sn, R, umbrales, sn_e))
    except Exception:
        pass
    try:
        rel = str(out.resolve().relative_to(proyecto.resolve())).replace("\\", "/")
    except ValueError:
        rel = str(out)
    return {"carpeta": rel, "meta": meta, "ensamble": R.replace({np.nan: None}).to_dict("records")}


def figura(sn, R, umbrales=(1.0, 2.0), sn_e=None):
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .cuenca import _BLOQUEO_PNG
    sn_e = sn_e or {}
    with _BLOQUEO_PNG:
        fig, axs = plt.subplots(2, 5, figsize=(20, 7.5), dpi=100, facecolor="#0f1724", sharex=True)
        for ax, ind in zip(axs.ravel(), INDICES):
            ax.set_facecolor("#131d2b")
            for m, d in (sn.get(ind) or {}).items():
                ax.plot(d["anios"], [np.nan if v is None else v for v in d["sn"]], color="#ff4da6", lw=0.8, alpha=0.45)
            if ind in sn_e:
                ax.plot(sn_e[ind]["anios"], sn_e[ind]["sn"], color="#ffffff", lw=2.0)
            for u in umbrales:
                ax.axhline(u, color="#ffd166", lw=0.8, ls="--"); ax.axhline(-u, color="#ffd166", lw=0.8, ls="--")
            ax.axhline(0, color="#8b95a3", lw=0.6)
            f = R[(R["indice"] == ind) & (R["umbral_sn"] == umbrales[0])]
            if len(f) and pd.notna(f["toe_ensamble"].iloc[0]):
                t = f.iloc[0]
                if pd.notna(t.get("toe_p10")): ax.axvspan(t["toe_p10"], t["toe_p90"], color="#d4147f", alpha=0.15)
                ax.axvline(t["toe_ensamble"], color="#d4147f", lw=2); tit = f"ToE {int(t['toe_ensamble'])} · {t['signo']} · acuerdo {t['acuerdo_signo']:.2f}"
            else:
                t = f.iloc[0] if len(f) else {}
                tit = "no emerge" + (f" · acuerdo {t['acuerdo_signo']:.2f}" if len(f) and pd.notna(t.get("acuerdo_signo")) else "")
            ax.set_title(INDICES[ind] + "\n" + tit, color="#e6edf3", fontsize=8.5); ax.tick_params(colors="#8b95a3", labelsize=7); ax.grid(alpha=0.15)
            [s_.set_color("#2a3647") for s_ in ax.spines.values()]
        for ax in axs[:, 0]:
            ax.set_ylabel("señal / ruido", color="#8b95a3")
        fig.suptitle("Time of Emergence · SSP5-8.5 · blanco = ensamble (ruido interno + entre modelos) · magenta = cada modelo · franja = p10–p90 de modelos del mismo signo",
                     color="#e6edf3", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.94)); b = io.BytesIO(); fig.savefig(b, format="png", facecolor=fig.get_facecolor()); plt.close(fig)
    return b.getvalue()
