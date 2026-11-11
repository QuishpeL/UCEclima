# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Gráficos y tablas de una descarga CHIRPS, guardados DENTRO de la carpeta de esa descarga (dentro de la carpeta del proyecto): totales anuales con tendencia (Mann-Kendall + Sen),
máximos diarios anuales, climatología mensual y curva de excedencia de la lluvia diaria. Solo describe lo descargado: no rellena ni corrige. CHIRPS es un producto de satélite, no una medición de campo."""
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

from . import series_api as SER

COLUMNAS = {"celda_nex_mm": "celda de 0,25° (la de NEX-GDDP)", "media_caja_mm": "media de la caja", "pixel_mm": "píxel del punto"}


def generar(destino, columna="celda_nex_mm"):
    """Escribe en <destino>/graficos/: chirps_anual.png, chirps_climatologia.png, chirps_excedencia.png, chirps_resumen_anual.csv y chirps_resumen.json. Devuelve la lista de archivos."""
    import json
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    destino = Path(destino); f = destino / "chirps_diario.csv"
    if not f.exists():
        raise FileNotFoundError("No hay chirps_diario.csv en esa descarga.")
    d = pd.read_csv(f, parse_dates=["fecha"]).set_index("fecha")
    if columna not in d.columns:
        columna = next(c for c in COLUMNAS if c in d.columns)
    x = d[columna].astype(float); r = SER.lluvia_serie(x, f"chirps:{columna}")
    out = destino / "graficos"; out.mkdir(exist_ok=True)
    plt.rcParams.update({"figure.facecolor": "#0f1b2d", "axes.facecolor": "#14233a", "axes.edgecolor": "#3b4a63", "axes.labelcolor": "#c9d6e6", "xtick.color": "#9fb0c6", "ytick.color": "#9fb0c6",
                         "text.color": "#e6edf5", "grid.color": "#25364f", "font.family": ["Calibri", "Arial", "DejaVu Sans"], "font.size": 10})
    pie = f"CHIRPS ({COLUMNAS[columna]}) · producto de satélite, no medición de campo · {x.index.min():%Y-%m-%d} → {x.index.max():%Y-%m-%d}"
    CIAN, ROSA, AMB = "#6cc4ec", "#ffffff", "#ffd166"
    def cierre(fig, nombre):
        fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.text(0.01, 0.01, pie, fontsize=8, color="#9fb0c6"); fig.savefig(out / nombre, dpi=140); plt.close(fig)
    anios = np.array(r["anios"]); tot = np.array([np.nan if v is None else v for v in r["total_mm"]]); comp = np.array(r["completo"])
    fig, ax = plt.subplots(figsize=(9, 4.2)); ax.bar(anios[comp], tot[comp], color=CIAN, label="año completo"); ax.bar(anios[~comp], tot[~comp], color="#6b7f99", hatch="//", label="año incompleto (fuera de la tendencia)")
    t = r["tendencia_total"]
    if t.get("sen_por_anio") is not None and comp.sum() >= 8:
        a = anios[comp]; y = tot[comp]; b = t["sen_por_anio"]; c0 = np.median(y - b * a); ax.plot(a, c0 + b * a, color=AMB, lw=2, ls="-" if t["p"] < 0.05 else "--",
                                                                                          label=f"Sen {b:+.1f} mm/año (p={t['p']:.2f}{'' if t['p'] < 0.05 else ', no significativa'})")
    ax.set_ylabel("lluvia anual (mm)"); ax.set_title("Totales anuales y tendencia"); ax.grid(alpha=.4, axis="y"); ax.legend(fontsize=8); cierre(fig, "chirps_anual.png")
    cl = r["clima_mensual"]; fig, ax = plt.subplots(figsize=(9, 4)); m = np.array([np.nan if v is None else v for v in cl["media"]]); p25 = np.array([np.nan if v is None else v for v in cl["p25"]]); p75 = np.array([np.nan if v is None else v for v in cl["p75"]])
    ax.bar(cl["mes"], m, color=CIAN, alpha=.85); ax.errorbar(cl["mes"], m, yerr=[np.clip(m - p25, 0, None), np.clip(p75 - m, 0, None)], fmt="none", ecolor=ROSA, capsize=3, lw=1)
    ax.set_xticks(cl["mes"]); ax.set_xticklabels(["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]); ax.set_ylabel("mm/mes (media y rango intercuartil)"); ax.set_title("Climatología mensual"); ax.grid(alpha=.4, axis="y"); cierre(fig, "chirps_climatologia.png")
    v = np.sort(x.dropna().values)[::-1]; ex = 100 * np.arange(1, len(v) + 1) / len(v); fig, ax = plt.subplots(figsize=(7, 4)); h = v >= 1.0
    ax.semilogx(ex[h], v[h], color=CIAN); ax.set_xlabel("% de los días en que se iguala o supera (días ≥ 1 mm)"); ax.set_ylabel("lluvia diaria (mm)"); ax.set_title("Curva de excedencia de la lluvia diaria"); ax.grid(alpha=.4, which="both"); cierre(fig, "chirps_excedencia.png")
    res = pd.DataFrame({"anio": r["anios"], "total_mm": r["total_mm"], "max_dia_mm": r["max_dia_mm"], "dias_con_dato": r["con_dato"], "completo": r["completo"]})
    res.to_csv(out / "chirps_resumen_anual.csv", index=False)
    resumen = {"creado": datetime.now().isoformat(timespec="seconds"), "serie": columna, "descripcion": COLUMNAS[columna], "periodo": [x.index.min().date().isoformat(), x.index.max().date().isoformat()], "anios_completos": r["años_completos"],
               "media_anual_mm": r["media_total_mm"], "tendencia_total": r["tendencia_total"], "tendencia_max_dia": r["tendencia_max_dia"], "nota": r["nota"] + " CHIRPS es un producto de satélite, no una medición de campo."}
    (out / "chirps_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return sorted(p.name for p in out.iterdir())
