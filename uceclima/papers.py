# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Zeta Z5 · Lo mejor de los papers 1–3 (Quishpe Landeta y Palacios, 2026) llevado al programa.

  P1 · Tiempo de emergencia (ToE) de la lluvia en Ecuador: las celdas de los modelos subestiman ~½ la variabilidad interanual de las estaciones,
       así que el ToE con el ruido del MODELO sale demasiado temprano → se ofrece el ToE con ruido medido en la ESTACIÓN.
  P2 · Calibración de CHIRPS que preserva la varianza: el mapeo de cuantiles (EQM) infla la variabilidad interanual (×1,41) y casi nada emerge;
       el reescalado mes-año a la referencia conserva la varianza (razón 0,96) sin perder extremos → `reescalar_mes_anio` + `razon_varianza`.
       Para lluvia de diseño, EQM es casi insesgado pero puede errar 34 % a T100; el reescalado subestima la cola (−25 %).
  P3 · Composición del forzamiento: los errores de línea base de 34 modelos equivalen a ~1 modelo independiente; > 8 modelos no mejora;
       anclar CHIRPS a estaciones ayuda con red DENSA pero no con red DISPERSA → `n_efectivo` y la receta según la red.

`receta(uso, red)` devuelve la combinación recomendada con su cita y el error esperado; `ejecutar(proyecto, …)` calcula los diagnósticos con los datos del
proyecto y deja todo en <proyecto>/papers/receta_<sello>/ (CSV, figuras, JSON e informe). Nada se calibra a escondidas: son diagnósticos y recomendaciones
declaradas; la decisión es de la persona."""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

CITAS = {"P1": "Quishpe Landeta y Palacios (2026a), tiempo de emergencia de la lluvia en Ecuador (MDPI Hydrometeorology, en revisión)",
         "P2": "Quishpe Landeta y Palacios (2026b), calibración de CHIRPS que preserva la varianza (borrador)",
         "P3": "Quishpe Landeta y Palacios (2026c), composición del forzamiento: estaciones, CHIRPS y 34 CMIP6 (borrador)"}
USOS = ("diseno", "emergencia", "balance")


def receta(uso, red="densa"):
    """Combinación recomendada según el USO de la lluvia y la red de estaciones («densa»: varias estaciones dentro o junto a la cuenca; «dispersa»: 0-1 o lejanas)."""
    if uso not in USOS:
        raise ValueError("uso debe ser: " + ", ".join(USOS))
    densa = red == "densa"
    R = {
        "diseno": {"referencia_cmip6": "estación (QQM histórico + QDM futuro)" if densa else "CHIRPS crudo de la celda (no anclado)",
                   "lluvia_observada": "estación; IDF oficial o Gumbel/GEV de máximos anuales de la estación",
                   "correccion_satelite": "EQM con estaciones vecinas (casi insesgado en la media de máximos)" if densa else "sin corrección: CHIRPS crudo",
                   "modelos": "ensamble ClimWIP; ≥ 8 modelos basta (P3)",
                   "error_esperado": "EQM: hasta 34 % a T100; reescalado: −25 % en la cola (P2). Declarar la banda.",
                   "citas": ["P2", "P3"]},
        "emergencia": {"referencia_cmip6": "estación" if densa else "CHIRPS crudo",
                       "lluvia_observada": "estación (series largas; tendencia observada no reproducible por ninguna corrección, P1-P2)",
                       "correccion_satelite": "reescalado mes-año (preserva la varianza; razón ≈ 0,96)",
                       "ruido_toe": "variabilidad interanual de la ESTACIÓN (no la del modelo, que la subestima ~½)",
                       "modelos": "ensamble ClimWIP; informar el ToE de la media Y de los miembros (Jensen: la media emerge ~40 años antes)",
                       "error_esperado": "EQM infla el ruido ×1,41 y oculta la emergencia (6 vs 26 de 50 estaciones, P2)",
                       "citas": ["P1", "P2", "P3"]},
        "balance": {"referencia_cmip6": "estación" if densa else "CHIRPS crudo",
                    "lluvia_observada": "estación + CHIRPS anclado (red densa) o CHIRPS crudo (red dispersa)",
                    "correccion_satelite": "reescalado mes-año (conserva totales mensuales y su variabilidad)" if densa else "CHIRPS crudo (anclar empeora con red dispersa, P3)",
                    "modelos": "ensamble ClimWIP",
                    "error_esperado": "anclar CHIRPS: 28,5 → 14,5–17,8 % con red densa; en red dispersa CHIRPS crudo fue 12,3 % mejor (P3)",
                    "citas": ["P3"]}}[uso]
    return {"uso": uso, "red": red, **R, "citas_texto": [CITAS[c] for c in R["citas"]],
            "nota": "Recomendación basada en Ecuador andino (64 estaciones) y una red costera/amazónica; en otras regiones es una hipótesis a verificar con los diagnósticos."}


def reescalar_mes_anio(sat, ref, min_dias=20):
    """P2 · Reescalado mes-año: cada mes de cada año, la serie satelital (CHIRPS) se multiplica por total_ref/total_sat de ESE mes.
    Conserva el reparto diario del satélite y los totales mensuales de la referencia (y por tanto su variabilidad interanual). Meses sin referencia: NaN (no se rellena)."""
    s, r = sat.astype(float).copy(), ref.astype(float)
    ms = s.resample("MS").sum(min_count=min_dias); mr = r.resample("MS").sum(min_count=min_dias)
    f = (mr / ms).replace([np.inf, -np.inf], np.nan)
    f[(ms <= 0) & (mr <= 0)] = 1.0
    fd = f.reindex(s.index, method="ffill")
    fd[~s.index.to_period("M").isin(f.dropna().index.to_period("M"))] = np.nan
    out = s * fd
    out[(ms.reindex(s.index, method="ffill") <= 0) & (mr.reindex(s.index, method="ffill") > 0)] = np.nan   # satélite seco y referencia húmeda: no se inventa el reparto
    return out, f


def razon_varianza(serie, obs, minimo=330):
    """P2 · Diagnóstico: desviación estándar interanual de la serie corregida / la de la observación (totales anuales y Rx1day). Ideal ≈ 1; > 1,2 infla el ruido."""
    def anual(x, how):
        g = x.groupby(x.index.year); ok = g.count() >= minimo
        return (g.sum() if how == "sum" else g.max())[ok]
    out = {}
    for k, how in (("PRCPTOT", "sum"), ("Rx1day", "max")):
        a, b = anual(serie, how), anual(obs, how); comunes = a.index.intersection(b.index)
        if len(comunes) < 8:
            out[k] = {"razon": None, "n_anios": int(len(comunes))}; continue
        sa, sb = float(a[comunes].std(ddof=1)), float(b[comunes].std(ddof=1))
        r = sa / sb if sb > 0 else None
        out[k] = {"razon": None if r is None else round(r, 3), "sd_serie": round(sa, 2), "sd_obs": round(sb, 2), "n_anios": int(len(comunes)),
                  "lectura": None if r is None else ("infla la variabilidad (oculta la emergencia)" if r > 1.2 else ("la reduce" if r < 0.8 else "conserva la variabilidad"))}
    return out


def n_efectivo(errores):
    """P3 · Número efectivo de modelos independientes a partir de sus errores de línea base (DataFrame: filas = meses/años, columnas = modelos).
    N_eff = (Σλ)² / Σλ² de los autovalores de la matriz de correlación (participation ratio). 34 modelos idénticos → 1; independientes → 34."""
    E = pd.DataFrame(errores).dropna(axis=1, how="all").dropna()
    if E.shape[1] < 2 or E.shape[0] < 3:
        return {"n_modelos": int(E.shape[1]), "n_eff": None}
    C = np.corrcoef(E.values.T); C = np.nan_to_num(C, nan=0.0); np.fill_diagonal(C, 1.0)
    lam = np.clip(np.linalg.eigvalsh(C), 0, None)
    return {"n_modelos": int(E.shape[1]), "n_eff": round(float(lam.sum() ** 2 / (lam ** 2).sum()), 2), "n_filas": int(E.shape[0]),
            "lectura": "los errores de línea base están muy correlacionados: más modelos no aportan independencia (P3)"}


def toe_con_ruido(series_ind, pesos, sigma_int, ventana=20, umbral=1.0):
    """P1 · ToE del ensamble con el ruido interno FIJADO en `sigma_int` (p. ej., la desviación interanual sin tendencia de la ESTACIÓN), más la dispersión entre modelos."""
    from . import toe as T
    A, w = {}, {}
    for m, s in series_ind.items():
        try:
            an, _, _ = T._anomalia(s, ventana, T.BASE)
        except T.ToEError:
            continue
        A[m], w[m] = an, float(pesos.get(m, 1.0))
    D = pd.DataFrame(A).dropna(how="any")
    if D.empty:
        return {"toe": None, "nota": "sin años comunes"}
    W = np.array([w[m] for m in D.columns]); W = W / W.sum(); S = D.values @ W
    N = np.sqrt(sigma_int ** 2 + ((D.values - S[:, None]) ** 2) @ W)
    sn = pd.Series(S / N, index=D.index); toe, signo = T._emergencia(sn, umbral)
    return {"toe": toe, "signo": signo, "sn": sn}


def _serie_estacion(P, ide):
    f = P / "datos" / "estaciones" / f"{ide}.csv"
    if not f.exists():
        raise ValueError(f"No existe la estación {ide} en el proyecto.")
    x = pd.read_csv(f, parse_dates=["fecha"]); x["fecha"] = x["fecha"].dt.tz_localize(None).dt.normalize()
    return x.groupby("fecha")["lluvia_mm"].sum(min_count=1).asfreq("D")


def _serie_chirps(P):
    c = sorted(P.glob("datos_descargados/*/chirps/chirps_diario.csv")) + sorted(P.glob("datos_descargados/chirps_*/chirps_diario.csv"))
    if not c:
        return None, None
    d = pd.read_csv(c[-1], parse_dates=["fecha"]).set_index("fecha")
    col = next((k for k in ("celda_nex_mm", "media_caja_mm", "centro_mm") if k in d.columns), d.select_dtypes("number").columns[0])
    return d[col].astype(float).asfreq("D"), f"{c[-1].relative_to(P)}:{col}"


def _estilo_claro():
    """Las figuras de los papers siempre en estilo claro (fondo blanco), aunque otro módulo haya puesto un estilo oscuro en el servidor."""
    import matplotlib
    return matplotlib.rc_context({k: v for k, v in matplotlib.rcParamsDefault.items() if k != "backend"})


def cmip6_hallazgos(proyecto, salida=None, carpeta=None):
    with _estilo_claro():
        return _cmip6_hallazgos(proyecto, salida, carpeta)


def _cmip6_hallazgos(proyecto, salida=None, carpeta=None):
    """Zeta · los hallazgos de los papers 1–3 aplicados al análisis CMIP6 del proyecto, en lenguaje sencillo y con una infografía:
      1) ¿Cuándo emerge la señal? ToE del ensamble con el ruido de los MODELOS (método anterior) frente al ruido de la REFERENCIA observada (estación o CHIRPS; P1).
      2) Efecto Jensen (P3): ToE de la serie MEDIA del ensamble frente a la mediana del ToE de cada modelo.
      3) ¿Cuántos modelos independientes? número efectivo a partir de sus errores de línea base (P3).
      4) ¿La corrección infla el ruido? razón de varianza interanual de los modelos corregidos frente a la referencia (P2).
      5) Banda del factor de cambio de la lluvia de diseño (Tr 100, 24 h): p10–mediana–p90 por horizonte (los papers piden reportar la banda, no solo la mediana)."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from . import toe as T, cmip6_sesgo as SB
    P = Path(proyecto)
    cars = sorted((P / "registro" / "cmip6").glob("analisis_*"))
    if not cars and not carpeta:
        raise ValueError("Primero evalúa los modelos CMIP6 (módulo 9).")
    car = Path(carpeta) if carpeta else cars[-1]; res_a = json.loads((car / "resumen_analisis.json").read_text(encoding="utf-8")); ref = res_a.get("referencia", "chirps:celda_nex_mm")
    obs = SB.referencia_larga(P, ref, "2014-12-31").astype(float)
    cal = SB._cargar_cal(car); met = pd.read_csv(car / "metricas_modelos.csv").set_index("modelo")
    pesos = {m: float(met.loc[m, "peso"]) if m in met.index and "peso" in met.columns else 1.0 for m in cal}
    dh = SB._carpeta_dl(P, "cmip6_historico"); clim_obs = obs.groupby(obs.index.month).mean()
    errores, varr, ind_m = {}, {}, {}
    for m in cal:
        q = SB.QQM(); q.m = cal[m]; hr = SB._leer(dh / f"{m}_historical.csv"); h = q.transform(hr)
        errores[m] = h["1981":"2014"].groupby(h["1981":"2014"].index.month).mean() - clim_obs
        varr[m] = razon_varianza(h["1981":"2014"], obs)["PRCPTOT"]["razon"]
        fut = SB.leer_futuro(P, m)
        if fut is not None:
            cont = pd.concat([h, q.transform_qdm(fut, hr)]).sort_index(); ind_m[m] = T.indices_anuales(cont[~cont.index.duplicated()])
    out = Path(salida) if salida else P / "registro" / "cmip6" / f"hallazgos_papers_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True, exist_ok=False)
    neff = n_efectivo(pd.DataFrame(errores)); rv = pd.Series(varr, dtype=float).dropna()
    ref_txt = ("estación " + ref.split(":", 1)[1]) if ref.startswith("est:") else "CHIRPS (sin estaciones)"
    io = T.indices_anuales(obs.asfreq("D")) if len(obs) else None
    filas = []
    for ind in ("PRCPTOT", "Rx1day", "Rx5day"):
        if not ind_m or io is None:
            break
        ser = {m: d[ind] for m, d in ind_m.items()}
        try:
            e_mod = T.toe_ensamble(ser, pesos)
        except T.ToEError:
            continue
        b = io[ind][(io.index >= T.BASE[0]) & (io.index <= T.BASE[1])].dropna()
        s_ref = T._ruido_base(b) if len(b) >= 15 else None
        e_ref = toe_con_ruido(ser, pesos, s_ref) if s_ref else {"toe": None}
        miembros = []
        for m, s in ser.items():
            try:
                r = T.toe_serie(s)
                if r["toe"] and r["signo"] == (e_mod["signo"] or e_mod["signo_final"]):
                    miembros.append(r["toe"])
            except T.ToEError:
                pass
        media = pd.DataFrame(ser).mul(pd.Series(pesos)).sum(axis=1, min_count=1) / pd.Series(pesos)[list(ser)].sum()
        try:
            toe_media = T.toe_serie(media.dropna())["toe"]
        except T.ToEError:
            toe_media = None
        filas.append({"indice": ind, "toe_ruido_modelos": e_mod["toe"], "toe_ruido_referencia": e_ref["toe"], "ruido_modelos": round(e_mod["ruido_interno"], 2),
                      "ruido_referencia": None if s_ref is None else round(s_ref, 2), "toe_serie_media": toe_media,
                      "toe_mediana_miembros": int(np.median(miembros)) if miembros else None, "n_miembros_emergen": len(miembros), "acuerdo_signo": round(e_mod["acuerdo_signo"], 2),
                      "signo": T._texto_signo(ind, e_mod["signo"] or e_mod["signo_final"])})
    F = pd.read_csv(car / "factores_cc.csv") if (car / "factores_cc.csv").exists() else pd.DataFrame()
    banda = []
    for hor in ("2040-2069", "2071-2100"):
        r = F[(F.get("horizonte") == hor) & (F.get("version") == "QQM/QDM") & (F.get("metrica") == "Tr100 de 24 h")] if len(F) else F
        if len(r):
            banda.append({"horizonte": hor, "p10": round(float(r.iloc[0]["p10"]), 3), "mediana": round(float(r.iloc[0]["mediana_ponderada"]), 3), "p90": round(float(r.iloc[0]["p90"]), 3)})
    T_ = pd.DataFrame(filas); T_.to_csv(out / "toe_papers.csv", index=False)
    pd.DataFrame(banda).to_csv(out / "banda_factor_tr100.csv", index=False)
    lect = []
    for f in filas:
        a, b_ = f["toe_ruido_modelos"], f["toe_ruido_referencia"]
        lect.append(f"{f['indice']} ({f['signo']}): con el ruido de los modelos {('emerge en ' + str(a)) if a else 'no emerge antes de 2100'}; con el ruido real de la referencia, {('emerge en ' + str(b_)) if b_ else 'no emerge antes de 2100'}"
                    + (" — la referencia retrasa la emergencia, como predice el paper 1." if (a and (not b_ or b_ > a)) else
                       (" — aquí la referencia tiene MENOS variabilidad que los modelos" + (": CHIRPS suaviza los años extremos; con estaciones locales la emergencia probablemente sería más tardía (papers 1-2)." if not ref.startswith("est:") else ".")
                        if (b_ and (not a or b_ < a)) else ".")))
        if f["toe_serie_media"] and f["toe_mediana_miembros"]:
            lect.append(f"  Efecto Jensen ({f['indice']}): la serie media emerge en {f['toe_serie_media']} y los modelos uno a uno en {f['toe_mediana_miembros']} (mediana): promediar adelanta la emergencia {f['toe_mediana_miembros'] - f['toe_serie_media']} años.")
    if neff.get("n_eff"):
        lect.append(f"Los {neff['n_modelos']} modelos equivalen a {neff['n_eff']} modelos independientes en sus errores de línea base (paper 3): más modelos no reducen la incertidumbre.")
    if len(rv):
        lect.append(f"La corrección de sesgo deja la variabilidad interanual en {rv.median():.2f} veces la observada (mediana; ideal 1). Si supera 1,2, la emergencia queda oculta (paper 2).")
    for bnd in banda:
        lect.append(f"Lluvia de diseño Tr 100 (24 h), {bnd['horizonte']}: ×{bnd['mediana']:.2f} (p10–p90: ×{bnd['p10']:.2f} a ×{bnd['p90']:.2f}). Reportar la banda, no solo la mediana.")
    # infografía
    fig, ax = plt.subplots(2, 2, figsize=(13, 8.5)); azul, mag, gris = "#1F4E79", "#C2185B", "#9DC3E6"
    a0 = ax[0, 0]
    if filas:
        y = np.arange(len(filas)); fin = 2100
        for i, f in enumerate(filas):
            for k, (col, c, dy) in enumerate((("toe_ruido_modelos", mag, -0.18), ("toe_ruido_referencia", azul, 0.18))):
                v = f[col]; a0.barh(i + dy, (v or fin) - 2015, left=2015, height=0.32, color=c if v else "white", edgecolor=c, hatch=None if v else "//")
                a0.text((v or fin) + 1, i + dy, str(v) if v else "no emerge", va="center", fontsize=8, color=c)
        a0.set_yticks(y); a0.set_yticklabels([f["indice"] for f in filas]); a0.set_xlim(2015, 2112)
        a0.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=mag), plt.Rectangle((0, 0), 1, 1, color=azul)], labels=["ruido de los modelos (antes)", f"ruido real: {ref_txt} (paper 1)"], fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2, frameon=False)
    a0.set_title("1 · ¿Cuándo emerge la señal del cambio?", loc="left", fontsize=11, color=azul)
    a1 = ax[0, 1]
    if neff.get("n_eff"):
        a1.bar(["modelos usados", "independientes (N efectivo)"], [neff["n_modelos"], neff["n_eff"]], color=[gris, azul])
        for i, v in enumerate([neff["n_modelos"], neff["n_eff"]]):
            a1.text(i, v, f"{v:g}", ha="center", va="bottom", fontsize=11)
    a1.set_title("2 · ¿Cuántos modelos independientes hay? (paper 3)", loc="left", fontsize=11, color=azul)
    a2 = ax[1, 0]
    if len(rv):
        a2.hist(rv.values, bins=12, color=gris, edgecolor="white"); a2.axvline(1, color="k", lw=1); a2.axvspan(0.8, 1.2, color="#eaf1fb", zorder=0)
        a2.axvline(rv.median(), color=azul, lw=2); a2.text(rv.median(), a2.get_ylim()[1] * 0.92, f" mediana {rv.median():.2f}", color=azul, fontsize=9)
        a2.set_xlabel("variabilidad interanual corregida / observada (ideal 1)")
    a2.set_title("3 · ¿La corrección infla el ruido? (paper 2)", loc="left", fontsize=11, color=azul)
    a3 = ax[1, 1]
    if banda:
        for i, bnd in enumerate(banda):
            a3.plot([bnd["p10"], bnd["p90"]], [i, i], color=mag, lw=8, alpha=0.35, solid_capstyle="round"); a3.plot(bnd["mediana"], i, "o", color=mag, ms=11)
            a3.text(bnd["p90"] + 0.01, i, f"×{bnd['mediana']:.2f}  ({bnd['p10']:.2f}–{bnd['p90']:.2f})", va="center", fontsize=9)
        lo = min([1.0] + [b_["p10"] for b_ in banda]); hi = max([1.0] + [b_["p90"] for b_ in banda]); pad = 0.08 * (hi - lo + 0.1)
        a3.set_xlim(lo - pad, hi + 3.5 * pad)
        a3.axvline(1, color=azul, lw=1.5); a3.text(1, -0.55, " X: hoy (×1)", color=azul, fontsize=9, va="bottom")
        a3.set_yticks(range(len(banda))); a3.set_yticklabels([b_["horizonte"] for b_ in banda]); a3.set_ylim(-0.6, len(banda) - 0.4); a3.set_xlabel("factor sobre la lluvia de diseño Tr 100 (24 h)")
    a3.set_title("4 · Cambio en la lluvia de diseño: banda, no solo mediana", loc="left", fontsize=11, color=mag)
    fig.suptitle(f"Hallazgos de los papers aplicados a CMIP6 · SSP5-8.5 · referencia: {ref_txt}", fontsize=12, color=azul)
    fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(out / "infografia_cmip6_papers.png", dpi=150); plt.close(fig)
    resumen = {"creado": time.strftime("%Y-%m-%dT%H:%M:%S"), "analisis": car.name, "referencia": ref, "referencia_texto": ref_txt, "toe": filas, "n_efectivo": neff,
               "razon_varianza_mediana": None if not len(rv) else round(float(rv.median()), 3), "banda_factor_tr100": banda, "lectura": lect,
               "citas": [CITAS[c] for c in ("P1", "P2", "P3")], "nota": "Proyecciones SSP5-8.5; no son predicciones. Línea base según la decisión registrada del usuario."}
    (out / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "informe.md").write_text("# Hallazgos de los papers aplicados a CMIP6\n\n" + "\n".join(f"- {l}" for l in lect) + "\n\n![infografía](infografia_cmip6_papers.png)\n\nFuentes:\n" + "\n".join(f"- {c}" for c in resumen["citas"]), encoding="utf-8")
    return {"carpeta": str(out.relative_to(P)).replace("\\", "/"), **resumen}


def cmip6_hallazgos_ultimo(proyecto):
    c = sorted((Path(proyecto) / "registro" / "cmip6").glob("hallazgos_papers_*/resumen.json"))
    return ({"carpeta": str(c[-1].parent.relative_to(proyecto)).replace("\\", "/"), **json.loads(c[-1].read_text(encoding="utf-8"))}) if c else None


def red_auto(proyecto):
    """«densa» si el proyecto tiene ≥ 3 estaciones de lluvia registradas; si no, «dispersa» (receta por defecto: CHIRPS)."""
    d = Path(proyecto) / "datos" / "estaciones"
    n = len([f for f in d.glob("*.csv") if f.name != "catalogo.csv"]) if d.exists() else 0
    return ("densa" if n >= 3 else "dispersa"), n


def ejecutar(proyecto, estacion=None, uso="emergencia", red="auto", salida=None):
    with _estilo_claro():
        return _ejecutar(proyecto, estacion, uso, red, salida)


def _ejecutar(proyecto, estacion=None, uso="emergencia", red="auto", salida=None):
    """Diagnósticos de los papers con los datos del proyecto. Escribe papers/receta_<sello>/ y devuelve el resumen.
    Zeta: SIN estación (caso por defecto en cualquier lugar del mundo) la referencia es CHIRPS de la celda del proyecto y la red se toma como «dispersa»."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from . import toe as T
    P = Path(proyecto); out = Path(salida) if salida else P / "papers" / f"receta_{time.strftime('%Y%m%d_%H%M%S')}"
    if red in (None, "", "auto"):
        red, n_est = red_auto(P)
    ch, ch_id = _serie_chirps(P)
    if not estacion and ch is None:
        raise ValueError("Sin estación y sin CHIRPS descargado: descarga CHIRPS (módulo 3) o registra una estación.")
    out.mkdir(parents=True, exist_ok=False)
    if estacion:
        obs = _serie_estacion(P, estacion); ref_txt = f"estación {estacion}"
    else:
        obs = ch; ref_txt = f"CHIRPS ({ch_id}) · sin estaciones: receta por defecto de los papers"
    res = {"estacion": estacion, "referencia": ref_txt, "red": red, "receta": receta(uso, red), "avisos": []}
    if not estacion:
        res["avisos"].append("Referencia CHIRPS: según P1-P2, CHIRPS no reproduce los máximos anuales (subestima ~31 % los niveles de retorno en Ecuador) y su ruido interanual puede ser menor que el de una estación; "
                             "el ToE con este ruido es una cota temprana. Con estaciones locales, repite con ellas.")
    figs = []
    if ch is not None and estacion:
        rs, fac = reescalar_mes_anio(ch, obs)
        pd.DataFrame({"chirps": ch, "chirps_reescalado_mes_anio": rs, "estacion": obs}).to_csv(out / "chirps_reescalado_mes_anio.csv", index_label="fecha")
        fac.rename("factor_mes").to_csv(out / "factores_mes_anio.csv", index_label="mes")
        res["chirps"] = {"serie": ch_id, "razon_varianza_crudo": razon_varianza(ch, obs), "razon_varianza_reescalado": razon_varianza(rs, obs)}
        try:                                                                         # EQM de referencia (P2): mapeo empírico de cuantiles en días húmedos
            from .cmip6_sesgo import QQM
            comun = obs.dropna().index.intersection(ch.dropna().index)
            q = QQM(); q.fit(obs[comun], ch[comun])
            res["chirps"]["razon_varianza_eqm"] = razon_varianza(q.transform(ch), obs)
        except Exception as e:
            res["avisos"].append("EQM de referencia no calculado: " + str(e)[:120])
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
        an = pd.DataFrame({"estación": obs, "CHIRPS": ch, "CHIRPS reescalado mes-año": rs}).resample("YS").sum(min_count=330)
        an.index = an.index.year; an.plot(ax=ax[0], marker="o", ms=3, color=["#1F4E79", "#9DC3E6", "#2E75B6"]); ax[0].set_ylabel("mm/año"); ax[0].set_title("Totales anuales (P2)", loc="left", fontsize=10)
        k = ["PRCPTOT", "Rx1day"]; v = {"CHIRPS crudo": res["chirps"]["razon_varianza_crudo"], "reescalado": res["chirps"]["razon_varianza_reescalado"]}
        if "razon_varianza_eqm" in res["chirps"]:
            v["EQM"] = res["chirps"]["razon_varianza_eqm"]
        x = np.arange(len(k)); wbar = 0.8 / len(v)
        for i, (nom, d) in enumerate(v.items()):
            ax[1].bar(x + i * wbar, [d[j]["razon"] or 0 for j in k], wbar, label=nom, color=["#9DC3E6", "#2E75B6", "#C00000"][i])
        ax[1].axhline(1, color="k", lw=.8); ax[1].axhspan(0.8, 1.2, color="#eaf1fb", zorder=0); ax[1].set_xticks(x + wbar * (len(v) - 1) / 2); ax[1].set_xticklabels(k)
        ax[1].set_title("Razón de varianza interanual frente a la estación (ideal 1)", loc="left", fontsize=10); ax[1].legend(fontsize=8)
        fig.tight_layout(); fig.savefig(out / "fig_P2_varianza.png", dpi=150); plt.close(fig); figs.append("fig_P2_varianza.png")
    elif ch is None:
        res["avisos"].append("El proyecto no tiene CHIRPS descargado: sin diagnóstico P2.")
    # P1 + P3 con CMIP6 (si hay análisis y futuro)
    try:
        from . import cmip6_sesgo as SB
        cars = sorted((P / "registro" / "cmip6").glob("analisis_*"))
        if not cars:
            raise ValueError("sin análisis CMIP6")
        car = cars[-1]; cal = SB._cargar_cal(car); met = pd.read_csv(car / "metricas_modelos.csv").set_index("modelo")
        pesos = {m: float(met.loc[m, "peso"]) if m in met.index and "peso" in met.columns else 1.0 for m in cal}
        dh = SB._carpeta_dl(P, "cmip6_historico"); clim_obs = obs["1981":"2014"].groupby(obs["1981":"2014"].index.month).mean()
        errores, ind_m, varr = {}, {}, {}
        for m in cal:
            q = SB.QQM(); q.m = cal[m]; h = q.transform(SB._leer(dh / f"{m}_historical.csv"))
            errores[m] = h["1981":"2014"].groupby(h["1981":"2014"].index.month).mean() - clim_obs
            varr[m] = razon_varianza(h["1981":"2014"], obs["1981":"2014"])["PRCPTOT"]["razon"]
            fut = SB.leer_futuro(P, m)
            if fut is not None:
                cont = pd.concat([h, q.transform_qdm(fut, SB._leer(dh / f"{m}_historical.csv"))]).sort_index()
                ind_m[m] = T.indices_anuales(cont[~cont.index.duplicated()])
        res["P3_n_efectivo"] = n_efectivo(pd.DataFrame(errores))
        rv = pd.Series(varr, dtype=float).dropna(); res["P2_razon_varianza_modelos_corregidos"] = {"mediana": round(float(rv.median()), 3) if len(rv) else None, "n": int(len(rv))}
        pd.DataFrame(errores).to_csv(out / "errores_climatologia_mensual_por_modelo.csv", index_label="mes")
        if ind_m:
            io = T.indices_anuales(obs); filas = []
            for ind in ("PRCPTOT", "Rx1day"):
                b = io[ind][(io.index >= T.BASE[0]) & (io.index <= T.BASE[1])].dropna()
                if len(b) < 15:
                    res["avisos"].append(f"{ind}: la estación tiene {len(b)} años en 1981–2014 (< 15): ToE con ruido de estación no calculado."); continue
                s_obs = T._ruido_base(b); ser = {m: d[ind] for m, d in ind_m.items()}
                e_mod = T.toe_ensamble(ser, pesos); e_est = toe_con_ruido(ser, pesos, s_obs)
                filas.append({"indice": ind, "ruido_estacion": round(s_obs, 2), "ruido_interno_modelos": round(e_mod["ruido_interno"], 2),
                              "razon_ruido_modelo_estacion": round(e_mod["ruido_interno"] / s_obs, 2) if s_obs else None,
                              "toe_ruido_modelos": e_mod["toe"], "toe_ruido_estacion": e_est["toe"], "acuerdo_signo": round(e_mod["acuerdo_signo"], 2)})
                fig, ax = plt.subplots(figsize=(7, 3.6)); e_mod["sn"].plot(ax=ax, color="#C2185B", label="ruido de los modelos (Omega)"); e_est["sn"].plot(ax=ax, color="#1F4E79", label=("ruido de la estación (P1, Zeta)" if estacion else "ruido de CHIRPS (referencia por defecto)"))
                ax.axhline(1, ls="--", color="k", lw=.7); ax.axhline(-1, ls="--", color="k", lw=.7); ax.set_ylabel("S/N"); ax.legend(fontsize=8); ax.set_title(f"{ind}: señal/ruido SSP5-8.5", loc="left", fontsize=10)
                fig.tight_layout(); fig.savefig(out / f"fig_P1_toe_{ind}.png", dpi=150); plt.close(fig); figs.append(f"fig_P1_toe_{ind}.png")
            pd.DataFrame(filas).to_csv(out / "toe_ruido_modelo_vs_estacion.csv", index=False); res["P1_toe"] = filas
        else:
            res["avisos"].append("Sin futuro CMIP6 descargado: sin ToE (P1).")
    except Exception as e:
        res["avisos"].append("CMIP6: " + str(e)[:160])
    res["figuras"] = figs
    (out / "resumen_papers.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    r = res["receta"]
    md = [f"# Receta de los papers · uso «{uso}» · red {red}", "", f"Referencia observada: **{ref_txt}**", "", "## Recomendación", ""] + [f"- **{k.replace('_', ' ')}**: {v}" for k, v in r.items() if isinstance(v, str) and k not in ("uso", "red")]
    md += ["", "## Diagnósticos con los datos de este proyecto", "", "```json", json.dumps({k: v for k, v in res.items() if k not in ("receta",)}, ensure_ascii=False, indent=1, default=str)[:6000], "```", "", "## Fuentes", ""] + [f"- {c}" for c in r["citas_texto"]]
    (out / "informe.md").write_text("\n".join(md), encoding="utf-8")
    try:
        rel = str(out.resolve().relative_to(P.resolve())).replace("\\", "/")
    except ValueError:
        rel = str(out)
    return {"carpeta": rel, **res}


# ------------------------------------------------------------------------------------------------ Zeta · CMIP6 «versión de frontera» (método de los papers), EN EVALUACIÓN
FRONTERA_NOTA = ("Versión de frontera de CMIP6 (método de los papers 1–3), en evaluación: se calcula APARTE (registro/cmip6_frontera) y no reemplaza el método "
                 "de referencia (Omega: QQM/QDM contra CHIRPS crudo, ToE con ruido de los modelos), que sigue siendo el que usan la IDF y el 2D. "
                 "Contar con ambas versiones es parte de la evaluación del software. No calibrado ni validado; proyecciones SSP5-8.5, no predicciones.")


def frontera(proyecto, estacion=None, red="auto", k=5):
    """Cadena CMIP6 completa con el método de los papers, en una carpeta propia que no toca el análisis de referencia:
      1) Referencia de la corrección (receta P2/P3): con estación y red DENSA → CHIRPS de la celda reescalado mes-año a la estación (P2, conserva la varianza);
         con red dispersa o sin estación → CHIRPS crudo (P3: anclar a una red dispersa empeora).
      2) Evaluación QQM + ClimWIP y factores QQM/QDM contra esa referencia (mismo motor que Omega).
      3) ToE «oficial» de frontera = con el ruido interanual de la referencia observada (P1); N efectivo de modelos y razón de varianza (P2-P3).
    Escribe registro/cmip6_frontera/analisis_<sello>/ (nunca sobrescribe) con frontera.json."""
    from . import cmip6_sesgo as SB
    P = Path(proyecto)
    if red in (None, "", "auto"):
        red, _ = red_auto(P)
    ch, ch_id = _serie_chirps(P)
    if ch is None:
        raise ValueError("La versión de frontera necesita CHIRPS descargado en el proyecto (módulo 3).")
    if estacion and red == "densa":
        obs = _serie_estacion(P, estacion)
        rs, fac = reescalar_mes_anio(ch, obs)
        if rs.notna().sum() < 365 * 10:
            raise ValueError("El CHIRPS reescalado a la estación tiene menos de 10 años: la estación no cubre 1981–2014 lo suficiente.")
        d = P / "datos" / "papers"; d.mkdir(parents=True, exist_ok=True)
        slug = f"chirps_reescalado_{estacion}_{time.strftime('%Y%m%d_%H%M%S')}"
        pd.DataFrame({"fecha": rs.index.strftime("%Y-%m-%d"), "valor": rs.values}).to_csv(d / f"{slug}.csv", index=False)
        ref, ref_txt = f"papers:{slug}", f"CHIRPS reescalado mes-año a la estación {estacion} (P2, red densa)"
    else:
        ref = "chirps:celda_nex_mm"
        ref_txt = ("CHIRPS crudo: red dispersa, anclar empeora (P3)" if estacion else "CHIRPS crudo (sin estación; por defecto en el mundo)")
    ev = SB.evaluar(P, ref, k, salida=P / "registro" / "cmip6_frontera")
    car = Path(ev["carpeta"])
    fac = SB.factores(P, carpeta_analisis=car)
    hall = cmip6_hallazgos(P, salida=car / "hallazgos", carpeta=car)
    F = fac["factores"]; tr = F[(F["version"] == "QQM/QDM") & (F["metrica"] == "Tr100 de 24 h")]
    res = {"creado": time.strftime("%Y-%m-%dT%H:%M:%S"), "metodo": "frontera_papers", "en_evaluacion": True, "referencia": ref, "referencia_texto": ref_txt, "red": red,
           "estacion": estacion, "carpeta": str(car.relative_to(P)).replace("\\", "/"),
           "factor_tr100": [{"horizonte": r["horizonte"], "mediana": round(float(r["mediana_ponderada"]), 3), "p10": round(float(r["p10"]), 3), "p90": round(float(r["p90"]), 3)} for _, r in tr.iterrows()],
           "toe_oficial": [{"indice": f["indice"], "signo": f["signo"], "toe": f["toe_ruido_referencia"], "toe_metodo_referencia": f["toe_ruido_modelos"]} for f in hall.get("toe", [])],
           "n_efectivo": hall.get("n_efectivo"), "razon_varianza_mediana": hall.get("razon_varianza_mediana"),
           "citas": [CITAS[c] for c in ("P1", "P2", "P3")], "nota": FRONTERA_NOTA}
    (car / "frontera.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return res


def frontera_ultima(proyecto):
    c = sorted((Path(proyecto) / "registro" / "cmip6_frontera").glob("analisis_*/frontera.json"))
    return json.loads(c[-1].read_text(encoding="utf-8")) if c else None


def comparar_versiones(proyecto):
    """Factor Tr 100 (24 h) del método de referencia (Omega) frente a la versión de frontera, por horizonte."""
    P = Path(proyecto); fr = frontera_ultima(P); filas = []
    cars = sorted((P / "registro" / "cmip6").glob("analisis_*/factores_cc.csv"))
    ref = pd.read_csv(cars[-1]) if cars else pd.DataFrame()
    for hor in ("2040-2069", "2071-2100"):
        r = ref[(ref["horizonte"] == hor) & (ref["version"] == "QQM/QDM") & (ref["metrica"] == "Tr100 de 24 h")] if len(ref) else ref
        f = next((x for x in (fr or {}).get("factor_tr100", []) if x["horizonte"] == hor), None)
        filas.append({"horizonte": hor, "referencia_omega": None if not len(r) else round(float(r.iloc[0]["mediana_ponderada"]), 3),
                      "referencia_p10_p90": None if not len(r) else [round(float(r.iloc[0]["p10"]), 3), round(float(r.iloc[0]["p90"]), 3)],
                      "frontera": f and f["mediana"], "frontera_p10_p90": f and [f["p10"], f["p90"]]})
    return {"filas": filas, "frontera": fr, "nota": FRONTERA_NOTA}
