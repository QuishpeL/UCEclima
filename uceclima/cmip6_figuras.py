# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Epsilon · gráficas principales del módulo CMIP6 (no cambian ningún cálculo; leen lo ya guardado y escriben PNG nuevos).
 1) bondad_qqm.png       Bondad de la corrección de sesgo del mejor modelo (RMSE más bajo) con validación cruzada impar/par:
                         ciclo anual (izq.) y Q-Q de totales mensuales (der.). La corrección ajusta la distribución histórica;
                         no crea procesos que el modelo no simula (Maraun 2013).
 2) toe_indicadores.png  Time of Emergence por indicador (total anual, CDD, Rx1day): valores anuales del mejor modelo corregido,
                         señal = media móvil de 11 años, bandas ±1σ y ±2σ de la base 1981–2014, franja magenta = p10–p90 de la
                         señal de todos los modelos, línea vertical = año actual.
 3) toe_sn_grande.png    La figura S/N del ensamble (magenta = cada modelo, blanco = ensamble) en tamaño grande, 4 × 3 paneles.
Todo bajo SSP5-8.5; proyección, no predicción."""
import io
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import cmip6_sesgo as SB, toe as T

PRINCIPALES = {"PRCPTOT": "Total anual (mm)", "CDD": "Racha seca máxima CDD (días)", "Rx1day": "Máximo de 1 día (mm)"}
FONDO, PANEL, TXT, GR = "#0f1724", "#131d2b", "#e6edf3", "#8b95a3"


class FiguraError(ValueError):
    pass


IDIOMA = {"v": "es"}                                                     # «en» solo para las figuras de los papers (regla del usuario)
RESTOS = []


def _guardar(fig, out, **kw):
    """Guarda la figura en español (programa) y, si IDIOMA es «en», además una copia _en.png traducida para los papers."""
    fig.savefig(out, **kw)
    if IDIOMA["v"] == "en":
        from .figuras_idioma import traducir, restos
        traducir(fig); fig.savefig(Path(out).with_name(Path(out).stem + "_en.png"), **kw); RESTOS.extend(f"{Path(out).name}: {r}" for r in restos(fig))


def _ultimo(base, patron):
    l = sorted(Path(base).glob(patron)) if Path(base).exists() else []
    return l[-1] if l else None


def _mejor_modelo(car):
    r = car / "resumen_analisis.json"
    if r.exists():
        j = json.loads(r.read_text(encoding="utf-8"))
        for k in ("mejor_modelo", "mejor", "mejor_rmse"):
            if isinstance(j.get(k), str):
                return j[k]
    m = pd.read_csv(car / "metricas_modelos.csv")
    m = m[m.get("estado", "ok") == "ok"] if "estado" in m.columns else m
    return str(m.sort_values("rmse_clim_mm_mes").iloc[0]["modelo"])


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def bondad_qqm(proyecto, id_serie="chirps:celda_nex_mm", modelo=None):
    """Figura 1. Devuelve dict con la ruta y los RMSE del ciclo anual (crudo y corregido con validación cruzada)."""
    proyecto = Path(proyecto); car = _ultimo(proyecto / "registro" / "cmip6", "analisis_*")
    if car is None:
        raise FiguraError("Primero evalúa los modelos (CMIP6 · paso 2).")
    modelo = modelo or _mejor_modelo(car)
    dh = SB._carpeta_dl(proyecto, "cmip6_historico"); f = dh / f"{modelo}_historical.csv" if dh else None
    if not f or not f.exists():
        raise FiguraError(f"No está la serie histórica de {modelo}.")
    obs = SB.referencia(proyecto, id_serie); mod = SB._leer(f).reindex(obs.index)
    cv = SB.pliegues_impar_par(obs, mod, SB.QQM)                                 # cada año corregido con un ajuste que NO lo incluye
    mens = lambda s: s.resample("MS").sum(min_count=20)
    mo, mm, mc = mens(obs), mens(mod), mens(cv)
    ok = mo.notna() & mm.notna() & mc.notna(); mo, mm, mc = mo[ok], mm[ok], mc[ok]
    ciclo = lambda s: s.groupby(s.index.month).mean().reindex(range(1, 13))
    co, cm, cc = ciclo(mo), ciclo(mm), ciclo(mc)
    rmse = lambda a, b: float(np.sqrt(np.nanmean((a - b) ** 2)))
    r_crudo, r_corr = rmse(cm.values, co.values), rmse(cc.values, co.values)
    plt = _plt()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 6), dpi=150, gridspec_kw={"width_ratios": [1.25, 1]})
    meses = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]; x = np.arange(1, 13)
    a1.plot(x, co.values, "-o", color="#1565c0", lw=3.0, ms=8, mfc="#64b5f6", mec="white", mew=1.2, label="CHIRPS (obs)", zorder=5)
    a1.plot(x, cm.values, "--s", color="#c0392b", lw=1.8, ms=7, label=f"{modelo} crudo")
    a1.plot(x, cc.values, "-^", color="#1e8449", lw=2.2, ms=7, label=f"{modelo} + QQM (validación cruzada)")
    a1.set_xticks(x); a1.set_xticklabels(meses); a1.set_ylabel("P mensual (mm)"); a1.grid(alpha=0.3); a1.legend(loc="upper right", fontsize=10)
    a1.text(0.02, 0.97, f"RMSE ciclo anual\ncrudo {r_crudo:.1f} → QQM {r_corr:.1f} mm", transform=a1.transAxes, va="top", fontsize=10.5,
            bbox=dict(boxstyle="square", fc="white", ec="0.5"))
    a1.set_title("Ciclo anual: corrección de sesgo QQM\nvalidación cruzada impar/par", fontweight="bold")
    p = np.linspace(0.01, 0.99, 60); qo = np.quantile(mo, p); a2.plot(qo, np.quantile(mm, p), "s", color="#c0392b", ms=5, label="crudo")
    a2.plot(qo, np.quantile(mc, p), "^", color="#1e8449", ms=6, label="QQM"); lim = max(qo.max(), np.quantile(mm, .99), np.quantile(mc, .99)) * 1.08
    a2.plot([0, lim], [0, lim], color="0.2", lw=1); a2.set_xlim(0, lim); a2.set_ylim(0, lim)
    a2.set_xlabel("cuantiles CHIRPS (mm)"); a2.set_ylabel("cuantiles modelo (mm)"); a2.grid(alpha=0.3); a2.legend(loc="upper left")
    a2.set_title("Q-Q antes / después (totales mensuales)", fontweight="bold")
    fig.text(0.01, 0.005, f"{proyecto.name}: 1981–2014, lluvia de referencia {id_serie}. Mejor modelo = RMSE más bajo del ranking ({car.name}). "
             "Validación cruzada: calibra con años impares y evalúa en pares (y al revés). La corrección ajusta la distribución histórica; no crea procesos que el modelo no simula (Maraun 2013).",
             fontsize=8, color="0.35", wrap=True)
    fig.tight_layout(rect=(0, 0.05, 1, 1)); out = car / "bondad_qqm.png"; _guardar(fig, out); plt.close(fig)
    info = {"figura": str(out.relative_to(proyecto)).replace("\\", "/"), "modelo": modelo, "rmse_ciclo_crudo_mm": round(r_crudo, 2), "rmse_ciclo_qqm_validado_mm": round(r_corr, 2),
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (car / "bondad_qqm.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def _toe_solo(senal, mu, sd, desde=2015):
    """Primer año ≥ desde a partir del cual la señal queda SIEMPRE fuera de ±1σ (mismo lado). None si no ocurre."""
    s = senal[senal.index >= desde].dropna()
    fuera = (s - mu).abs() > sd; lado = np.sign(s - mu)
    for i, a in enumerate(s.index):
        if fuera.iloc[i:].all() and (lado.iloc[i:] == lado.iloc[i]).all():
            return int(a)
    return None


def toe_indicadores(proyecto, modelo=None, ventana=11, anio_actual=None):
    """Figura 2 (las tres gráficas principales del ToE)."""
    proyecto = Path(proyecto); base = proyecto / "registro" / "cmip6"; dt = _ultimo(base, "toe_*"); car = _ultimo(base, "analisis_*")
    if dt is None or not (dt / "indices_anuales_por_modelo.csv").exists():
        raise FiguraError("Primero calcula el Time of Emergence (CMIP6 · ToE).")
    D = pd.read_csv(dt / "indices_anuales_por_modelo.csv", encoding="utf-8-sig")
    modelo = modelo or (_mejor_modelo(car) if car else D.modelo.iloc[0])
    if modelo not in set(D.modelo):
        modelo = D.modelo.iloc[0]
    anio_actual = anio_actual or int(time.strftime("%Y"))
    plt = _plt()
    fig, axs = plt.subplots(1, 3, figsize=(19, 6.2), dpi=150)
    res = {}
    for ax, (ind, nom) in zip(axs, PRINCIPALES.items()):
        s = D[D.modelo == modelo].set_index("anio")[ind].astype(float).sort_index()
        b = s[(s.index >= T.BASE[0]) & (s.index <= T.BASE[1])]; mu, sd = float(b.mean()), float(b.std())
        senal = s.rolling(ventana, center=True, min_periods=ventana).mean()
        todas = D.pivot_table(index="anio", columns="modelo", values=ind).rolling(ventana, center=True, min_periods=ventana).mean()
        ax.axhspan(mu - 2 * sd, mu + 2 * sd, color="#dbe7f3", alpha=0.55, lw=0, label="±2σ (base 1981–2014)")
        ax.axhspan(mu - sd, mu + sd, color="#b9cfe6", alpha=0.75, lw=0, label="±1σ")
        ax.fill_between(todas.index, todas.quantile(0.1, axis=1), todas.quantile(0.9, axis=1), color="#ff4da6", alpha=0.22, lw=0, label=f"p10–p90 de {todas.shape[1]} modelos")
        ax.scatter(s.index, s.values, s=14, color="0.6", alpha=0.85, zorder=3)
        ax.plot(senal.index, senal.values, color="#c0182a", lw=2.4, zorder=4, label=f"señal ({ventana} años)")
        ax.axhline(mu, color="0.25", lw=1); ax.axvline(anio_actual, color="0.45", lw=1)
        toe = _toe_solo(senal, mu, sd)
        if toe:
            ax.axvline(toe, color="#d4147f", lw=2, ls="--")
        ax.set_title(f"{nom}\n" + (f"ToE solo-modelo ±1σ: {toe}" if toe else "no sale de ±1σ de forma permanente"), fontsize=12)
        ax.grid(alpha=0.3); ax.set_xlim(1979, 2101)
        res[ind] = {"media_base": round(mu, 2), "sigma_base": round(sd, 2), "toe_solo_modelo": toe}
    axs[0].legend(loc="lower left", fontsize=8.5, framealpha=0.9)
    fig.suptitle(f"Time of Emergence — cuándo el cambio supera la variabilidad natural (SSP5-8.5) · serie solo-modelo: {modelo} corregido", fontsize=13.5, y=0.99)
    fig.text(0.01, 0.005, "Puntos grises: valor anual del mejor modelo corregido (QQM/QDM). Franja magenta: dispersión de la señal entre modelos. "
             "Es un diagnóstico de UN modelo; el ToE del ensamble (ruido interno + entre modelos) está en toe_sn_grande.png.", fontsize=8.5, color="0.35")
    fig.tight_layout(rect=(0, 0.035, 1, 0.95)); out = dt / "toe_indicadores.png"; _guardar(fig, out); plt.close(fig)
    info = {"figura": str(out.relative_to(proyecto)).replace("\\", "/"), "modelo": modelo, "ventana_anios": ventana, "indicadores": res}
    (dt / "toe_indicadores.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def toe_sn_grande(proyecto):
    """Figura 3: S/N de cada modelo (magenta) y del ensamble (blanco), 4 × 3 paneles grandes."""
    proyecto = Path(proyecto); dt = _ultimo(proyecto / "registro" / "cmip6", "toe_*")
    if dt is None or not (dt / "toe_resumen.json").exists():
        raise FiguraError("Primero calcula el Time of Emergence (CMIP6 · ToE).")
    d = json.loads((dt / "toe_resumen.json").read_text(encoding="utf-8"))
    R = pd.DataFrame(d["ensamble"]); R = R[R.umbral_sn == 1.0].set_index("indice")
    plt = _plt(); plt.rcParams.update({"font.size": 12})
    fig, axs = plt.subplots(4, 3, figsize=(17, 18), dpi=130, facecolor=FONDO)
    for ax in axs.ravel()[len(T.INDICES):]:
        ax.axis("off")
    for ax, (ind, nom) in zip(axs.ravel(), T.INDICES.items()):
        ax.set_facecolor(PANEL)
        for m, s in (d["sn"].get(ind) or {}).items():
            ax.plot(s["anios"], [np.nan if v is None else v for v in s["sn"]], color="#ff4da6", lw=0.9, alpha=0.45)
        e = d["sn_ensamble"].get(ind)
        if e:
            ax.plot(e["anios"], e["sn"], color="#ffffff", lw=3.0)
        for u in (1, 2):
            ax.axhline(u, color="#ffd166", lw=1.1, ls="--"); ax.axhline(-u, color="#ffd166", lw=1.1, ls="--")
        ax.axhline(0, color=GR, lw=0.8)
        if ind in R.index:
            r = R.loc[ind]; toe = r.get("toe_ensamble")
            tt = f"ToE {int(toe)} · {r.signo}" if pd.notna(toe) else "no emerge"
            if pd.notna(toe):
                ax.axvline(toe, color="#d4147f", lw=2.5)
            ax.set_title(f"{nom}\n{tt} · acuerdo de signo {r.acuerdo_signo:.2f}" if pd.notna(r.acuerdo_signo) else f"{nom}\n{tt}", color=TXT, fontsize=13)
        ax.tick_params(colors=GR, labelsize=11, labelbottom=True); ax.grid(alpha=0.18); [s_.set_color("#2a3647") for s_ in ax.spines.values()]
    for ax in axs[:, 0]:
        ax.set_ylabel("señal / ruido", color=GR, fontsize=12)
    fig.suptitle(f"{proyecto.name} · Time of Emergence del ensamble · {len(d['meta']['modelos'])} modelos CMIP6 · SSP5-8.5", color=TXT, fontsize=17, x=0.02, ha="left")
    fig.text(0.5, 0.004, "Magenta: S/N de cada modelo (trayectorias plausibles) · Blanco: S/N del ensamble (ruido interno + entre modelos) · Líneas amarillas: |S/N| = 1 y 2",
             color=TXT, ha="center", fontsize=12)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97)); out = dt / "toe_sn_grande.png"; _guardar(fig, out, facecolor=FONDO); plt.close(fig)
    return {"figura": str(out.relative_to(proyecto)).replace("\\", "/")}


def todas(proyecto, idioma="es"):
    """Genera las tres; cada una informa su error sin impedir las otras. idioma="en" guarda además copias _en.png (solo para papers)."""
    IDIOMA["v"] = idioma; RESTOS.clear(); out = {}
    try:
        for k, f in (("toe_cabeza", toe_cabeza), ("bondad_qqm", bondad_qqm), ("toe_indicadores", toe_indicadores), ("toe_sn_grande", toe_sn_grande)):
            try:
                out[k] = f(proyecto)
            except Exception as e:
                out[k] = {"error": str(e)[:300]}
    finally:
        IDIOMA["v"] = "es"
    if idioma == "en":
        out["textos_sin_traducir"] = sorted(set(RESTOS))
    return out

CABEZA = {"PRCPTOT": "Precipitación total anual (mm)", "CDD": "Días secos consecutivos · CDD (días < 1 mm)", "Rx1day": "Lluvia máxima en 24 h · Rx1day (mm)"}


def toe_cabeza(proyecto, modelo=None, ventana=11, anio_actual=None):
    """Las tres gráficas PRINCIPALES del ToE, cada una en su propia figura grande y de alta resolución (toe_cabeza_<índice>.png).
    Mismo contenido que toe_indicadores (serie solo-modelo, señal de 11 años, ±1σ/±2σ, franja magenta de todos los modelos y su mediana)."""
    proyecto = Path(proyecto); base = proyecto / "registro" / "cmip6"; dt = _ultimo(base, "toe_*"); car = _ultimo(base, "analisis_*")
    if dt is None or not (dt / "indices_anuales_por_modelo.csv").exists():
        raise FiguraError("Primero calcula el Time of Emergence (CMIP6 · ToE).")
    D = pd.read_csv(dt / "indices_anuales_por_modelo.csv", encoding="utf-8-sig")
    modelo = modelo or (_mejor_modelo(car) if car else D.modelo.iloc[0])
    if modelo not in set(D.modelo):
        modelo = D.modelo.iloc[0]
    anio_actual = anio_actual or int(time.strftime("%Y")); plt = _plt(); out = {}
    for ind, nom in CABEZA.items():
        s = D[D.modelo == modelo].set_index("anio")[ind].astype(float).sort_index()
        b = s[(s.index >= T.BASE[0]) & (s.index <= T.BASE[1])]; mu, sd = float(b.mean()), float(b.std())
        senal = s.rolling(ventana, center=True, min_periods=ventana).mean()
        todas = D.pivot_table(index="anio", columns="modelo", values=ind).rolling(ventana, center=True, min_periods=ventana).mean()
        fig, ax = plt.subplots(figsize=(13, 6.6), dpi=220)
        ax.axhspan(mu - 2 * sd, mu + 2 * sd, color="#dbe7f3", alpha=0.6, lw=0, label="±2σ de la base 1981–2014")
        ax.axhspan(mu - sd, mu + sd, color="#b9cfe6", alpha=0.8, lw=0, label="±1σ (variabilidad natural)")
        ax.fill_between(todas.index, todas.quantile(0.1, axis=1), todas.quantile(0.9, axis=1), color="#ff4da6", alpha=0.25, lw=0, label=f"p10–p90 de {todas.shape[1]} modelos CMIP6")
        ax.plot(todas.index, todas.median(axis=1), color="#d4147f", lw=2.2, ls="--", label="mediana de los modelos")
        ax.scatter(s.index, s.values, s=26, color="0.55", alpha=0.85, zorder=3, label=f"valor anual · {modelo} corregido")
        ax.plot(senal.index, senal.values, color="#c0182a", lw=3.4, zorder=4, label=f"señal ({ventana} años) · {modelo}")
        ax.axhline(mu, color="0.2", lw=1.3); ax.axvline(anio_actual, color="0.4", lw=1.3); y0_, y1_ = ax.get_ylim(); ax.text(anio_actual - 0.8, y0_ + 0.04 * (y1_ - y0_), f"hoy ({anio_actual}) ", ha="right", va="bottom", fontsize=12, color="0.3")
        toe = _toe_solo(senal, mu, sd)
        if toe:
            ax.axvline(toe, color="#d4147f", lw=2.6, ls=":"); ax.text(toe + 0.8, ax.get_ylim()[0], f" ToE {toe}", va="bottom", fontsize=13, color="#d4147f", fontweight="bold")
        ax.set_title(f"{nom}\nTime of Emergence bajo SSP5-8.5 · " + (f"la señal sale de ±1σ desde {toe}" if toe else "la señal no sale de ±1σ de forma permanente"), fontsize=16, fontweight="bold")
        ax.set_xlim(1979, 2101); ax.grid(alpha=0.3); ax.tick_params(labelsize=13); ax.set_xlabel("año", fontsize=13); ax.set_ylabel(nom.split("·")[-1].strip(), fontsize=13)
        ax.legend(loc="upper left", fontsize=10.5, framealpha=0.92, ncol=2)
        fig.text(0.01, 0.005, f"{proyecto.name} · proyección con sesgo corregido (QQM/QDM), no predicción. El ToE del ensamble (ruido interno + entre modelos) está en toe_sn_grande.png.", fontsize=10, color="0.35")
        fig.tight_layout(rect=(0, 0.03, 1, 1)); f = dt / f"toe_cabeza_{ind}.png"; _guardar(fig, f); plt.close(fig)
        out[ind] = {"figura": str(f.relative_to(proyecto)).replace("\\", "/"), "toe_solo_modelo": toe}
    return {"modelo": modelo, "figuras": out}

