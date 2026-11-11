# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""R4 · gráficas y tablas de comparación de la calibración (para la combinación seleccionada y la aceptada; en pantalla y en la entrega).

1. Mosaico de hidrogramas por evento: observado vs simulado, lluvia areal invertida arriba, color por rol; excluidos en gris.
2. Dispersión observado vs simulado de caudal pico y de volumen directo, con línea 1:1, por rol.
3. Sensibilidad del barrido: KGE de ajuste y de validación vs CN, una curva por λ (mejor lag/PRF/k para cada CN), óptimo marcado; aviso de borde.
4. Curva de duración de caudales observada y balance anual lluvia vs escorrentía (años incoherentes marcados, C15).
5. Tablas de métricas por evento y global (KGE, NSE, PBIAS, error de pico, error de volumen), ajuste y validación lado a lado.
Las métricas globales se calculan con la MISMA función del barrido (`_evaluar`) sobre los MISMOS eventos (`preparar`): deben coincidir con la fila del barrido.
La validación nunca ordena nada.
"""
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import calibracion as K

COL = {"ajuste": "#2f7fd0", "validacion": "#e07b00", "excluido": "#7a828c", "obs": "#2b2b2b"}


def _params(fila):
    k = fila.get("k_rec_d", np.nan)
    h = fila.get("humedad", "ninguna"); h = "ninguna" if (h is None or (isinstance(h, float) and pd.isna(h))) else h
    return (float(fila["CN"]), float(fila["lag_h"]), float(fila["PRF"]), float(fila["lambda"]), None if pd.isna(k) else float(k), h)


def _metricas_evento(o, s, b):
    m = K._metricas(o, s)
    m["error_pico_pct"] = 100 * (s.max() / o.max() - 1) if o.max() > 0 else np.nan
    vo = float((o - b).clip(min=0).sum()); vs = float((s - b).sum())
    m["error_volumen_pct"] = 100 * (vs / vo - 1) if vo > 0 else np.nan
    return m, vo, vs


def balance_anual(q, p, area_km2):
    """Lluvia y escorrentía anuales (mm) en años con ≥ 90 % de días en ambas series; incoherente si escorrentía ≥ lluvia o coeficiente < 0,05."""
    d = pd.concat({"q": q, "p": p}, axis=1).dropna()
    g = d.groupby(d.index.year)
    filas = []
    for y, x in g:
        if len(x) < 0.9 * 365:
            continue
        lluvia = float(x["p"].sum()); esc = float(x["q"].mean() * 86400 * 365.25 / (area_km2 * 1e3))
        coef = esc / lluvia if lluvia > 0 else np.nan
        motivo = "escorrentía ≥ lluvia" if coef >= 1 else ("coeficiente < 0,05" if coef < 0.05 else "")
        filas.append({"anio": int(y), "lluvia_mm": round(lluvia, 1), "escorrentia_mm": round(esc, 1), "coeficiente": round(coef, 3), "incoherente": bool(motivo), "motivo": motivo})
    return pd.DataFrame(filas)


def comparar(carpeta, barrido_id, combo_id, salida=None):
    carpeta = Path(carpeta); d = carpeta / "calibracion" / "barridos" / barrido_id
    if not (d / "resultados.csv").exists():
        raise K.CalibracionError("Barrido no encontrado.")
    out = Path(salida) if salida else d / f"comparacion_{int(combo_id)}"
    if (out / "comparacion.json").exists():
        return json.loads((out / "comparacion.json").read_text(encoding="utf-8"))
    res = pd.read_csv(d / "resultados.csv"); cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    ev_tab = pd.read_csv(d / "eventos.csv").fillna("").to_dict("records")
    fila = res[res["id"] == int(combo_id)]
    if fila.empty:
        raise K.CalibracionError("Combinación no encontrada.")
    fila = fila.iloc[0].to_dict(); prm = _params(fila)
    evs, excluidos, area, q, p, a, mq, mp_, _ = K.preparar(carpeta, ev_tab)
    dt_h = float(cfg.get("dt_h", 24.0))
    glob = K._evaluar(evs, prm, area, dt_h)
    por_ev, simulados = [], {}
    for e in evs:
        sim = K.simular_e(e, area, prm, dt_h); b = K.caudal_base(e["q"][0], len(e["q"]), dt_h, prm[4])
        m, vo, vs = _metricas_evento(e["q"], sim, b); simulados[e["evento"]] = (e, sim)
        por_ev.append({"evento": e["evento"], "rol": e["rol"], "inicio": e["inicio"], "pico": e["pico"], "Q_pico_obs": round(float(e["q"].max()), 3), "Q_pico_sim": round(float(sim.max()), 3),
                       "V_directo_obs_m3": round(vo * dt_h * 3600, 0), "V_directo_sim_m3": round(vs * dt_h * 3600, 0), "P_total_mm": round(float(np.nansum(e["p"])), 1),
                       **{k: (round(v, 4) if isinstance(v, float) and np.isfinite(v) else None) for k, v in m.items()}})
    E = pd.DataFrame(por_ev)
    G = pd.DataFrame([{"metrica": k, "ajuste": (glob["ajuste"] or {}).get(k), "validacion": (glob["validacion"] or {}).get(k)} for k in ("KGE", "NSE", "PBIAS_pct", "error_pico_medio_abs_pct", "error_volumen_directo_medio_pct", "n_eventos")])
    # sensibilidad: mejor KGE de ajuste para cada (CN, λ) sobre lag, PRF y k
    res = res.copy(); res["lambda"] = res["lambda"].astype(float)
    sens = res.loc[res.groupby(["CN", "lambda"])["KGE_ajuste"].idxmax().dropna()].sort_values(["lambda", "CN"])[["CN", "lambda", "lag_h", "PRF", "KGE_ajuste", "KGE_validacion"]]
    borde = []
    for clave, k_ in (("CN", "CN"), ("lag_h", "lag_h")):
        rg = (cfg.get("rangos") or {}).get(clave)
        if rg and len(rg) >= 3 and int(rg[2]) > 1 and (abs(fila[k_] - rg[0]) < 1e-9 or abs(fila[k_] - rg[1]) < 1e-9):
            borde.append(f"{k_} = {fila[k_]:g} en el borde del rango [{rg[0]:g}, {rg[1]:g}]")
    qs = np.sort(q.dropna().values)[::-1]; exc = np.arange(1, len(qs) + 1) / (len(qs) + 1) * 100
    idx = np.unique(np.linspace(0, len(qs) - 1, min(len(qs), 400)).astype(int))
    dur = pd.DataFrame({"excedencia_pct": exc[idx].round(3), "caudal_m3s": qs[idx].round(4)})
    bal = balance_anual(q, p, area)
    out.mkdir(parents=True, exist_ok=True)
    for nombre, df in (("metricas_por_evento", E), ("metricas_globales", G), ("sensibilidad", sens), ("curva_duracion", dur), ("balance_anual", bal)):
        df.to_csv(out / f"{nombre}.csv", index=False, encoding="utf-8-sig")
    figs = _figuras(simulados, ev_tab, excluidos, q, p, E, sens, fila, borde, dur, bal, cfg)
    for k_, b_ in figs.items():
        (out / k_).write_bytes(b_)
    r = {"barrido": barrido_id, "combinacion": {k: (None if (isinstance(v, float) and not np.isfinite(v)) else v) for k, v in fila.items()},
         "globales": G.replace({np.nan: None}).to_dict("records"), "por_evento": E.replace({np.nan: None}).to_dict("records"),
         "excluidos": excluidos, "borde": borde, "balance_anual": bal.to_dict("records"), "anios_incoherentes": bal[bal["incoherente"]]["anio"].tolist() if len(bal) else [],
         "figuras": sorted(figs), "carpeta": str(out.relative_to(carpeta)).replace("\\", "/") if str(out).startswith(str(carpeta)) else str(out),
         "nota": "Métricas con la misma función y los mismos eventos del barrido. La validación no se usa para ordenar ni elegir."}
    (out / "comparacion.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return r


def _figuras(simulados, ev_tab, excluidos, q, p, E, sens, fila, borde, dur, bal, cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .cuenca import _BLOQUEO_PNG
    out = {}
    def png(fig):
        b = io.BytesIO(); fig.savefig(b, format="png", dpi=110, bbox_inches="tight"); plt.close(fig); return b.getvalue()
    with _BLOQUEO_PNG, plt.style.context("default"), plt.rc_context({"font.size": 7, "figure.facecolor": "white", "axes.facecolor": "white"}):
        # 1 · mosaico
        todos = [e for e in ev_tab]
        n = len(todos); cols = min(5, max(n, 1)); filas = int(np.ceil(n / cols))
        fig, axs = plt.subplots(filas, cols, figsize=(3.1 * cols, 2.5 * filas), squeeze=False)
        qd = q.asfreq("D"); pdd = p.asfreq("D")
        for k, ev in enumerate(todos):
            ax = axs[k // cols][k % cols]; nom = ev["evento"]
            if nom in simulados:
                e, sim = simulados[nom]; t = e["fechas"]
                ax.plot(t, e["q"], color=COL["obs"], lw=1.2, label="observado"); ax.plot(t, sim, color=COL[e["rol"]], lw=1.3, label="simulado")
                ax2 = ax.twinx(); ax2.bar(t, e["p"], color="#6cc4ec", alpha=0.6, width=0.8); ax2.set_ylim(max(np.nanmax(e["p"]), 1) * 3, 0); ax2.tick_params(labelsize=5)
                ax.set_title(f"{nom} · {ev['rol']}", color=COL[e["rol"]], fontsize=7)
            else:
                i, f = pd.Timestamp(ev["inicio"]), pd.Timestamp(ev["fin"]); qq = qd[i:f]
                ax.plot(qq.index, qq.values, color=COL["excluido"], lw=1); ax.set_facecolor("#f0f0f0")
                ax.set_title(f"{nom} · excluido", color=COL["excluido"], fontsize=7)
            ax.tick_params(labelsize=5); ax.xaxis.set_major_locator(plt.MaxNLocator(3))
        for k in range(n, filas * cols):
            axs[k // cols][k % cols].axis("off")
        fig.suptitle(f"Hidrogramas por evento · CN {fila['CN']:g} · lag {fila['lag_h']:g} h · PRF {fila['PRF']:g} · λ {fila['lambda']:g}" + (f" · k {fila['k_rec_d']:g} d" if not pd.isna(fila.get('k_rec_d', np.nan)) else ""), fontsize=9)
        fig.tight_layout(rect=(0, 0, 1, 0.97)); out["1_hidrogramas_por_evento.png"] = png(fig)
        # 2 · dispersión
        fig, axs = plt.subplots(1, 2, figsize=(10, 4.4))
        for ax, (o, s, tit) in zip(axs, (("Q_pico_obs", "Q_pico_sim", "Caudal pico (m³/s)"), ("V_directo_obs_m3", "V_directo_sim_m3", "Volumen directo (m³)"))):
            for rol in ("ajuste", "validacion"):
                x = E[E["rol"] == rol]; ax.scatter(x[o], x[s], color=COL[rol], label=rol, s=22)
            lim = [0, max(E[o].max(), E[s].max()) * 1.05 if len(E) else 1]; ax.plot(lim, lim, color="#555", lw=0.8, ls="--", label="1:1")
            ax.set_xlim(lim); ax.set_ylim(lim); ax.set_xlabel("observado"); ax.set_ylabel("simulado"); ax.set_title(tit); ax.legend(); ax.grid(alpha=0.2)
        fig.tight_layout(); out["2_dispersion_pico_volumen.png"] = png(fig)
        # 3 · sensibilidad
        fig, ax = plt.subplots(figsize=(8, 4.2))
        for lam, g in sens.groupby("lambda"):
            ax.plot(g["CN"], g["KGE_ajuste"], marker="o", ms=3, label=f"ajuste · λ {lam:g}")
            ax.plot(g["CN"], g["KGE_validacion"], marker="o", ms=3, ls="--", label=f"validación · λ {lam:g}")
        ax.scatter([fila["CN"]], [fila["KGE_ajuste"]], s=120, facecolors="none", edgecolors="#d62828", lw=2, zorder=5, label="óptimo elegido")
        ax.set_xlabel("CN"); ax.set_ylabel("KGE (mejor lag/PRF para cada CN)"); ax.grid(alpha=0.2); ax.legend(fontsize=6, ncol=2)
        ax.set_title("Sensibilidad del barrido" + (" · ⚠ " + "; ".join(borde) if borde else ""), color="#d62828" if borde else "black")
        fig.tight_layout(); out["3_sensibilidad_kge_cn.png"] = png(fig)
        # 4 · duración y balance anual
        fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
        axs[0].semilogy(dur["excedencia_pct"], dur["caudal_m3s"].clip(lower=1e-3), color=COL["obs"]); axs[0].set_xlabel("excedencia (%)"); axs[0].set_ylabel("caudal (m³/s)")
        axs[0].set_title("Curva de duración de caudales observada"); axs[0].grid(alpha=0.2, which="both")
        if len(bal):
            x = np.arange(len(bal)); axs[1].bar(x - 0.2, bal["lluvia_mm"], 0.4, color="#6cc4ec", label="lluvia")
            axs[1].bar(x + 0.2, bal["escorrentia_mm"], 0.4, color=["#d62828" if v else "#2f7fd0" for v in bal["incoherente"]], label="escorrentía (rojo = incoherente)")
            axs[1].set_xticks(x); axs[1].set_xticklabels(bal["anio"], rotation=90, fontsize=6); axs[1].legend(fontsize=6)
        axs[1].set_title("Balance anual lluvia vs escorrentía (mm)"); axs[1].grid(alpha=0.2, axis="y")
        fig.tight_layout(); out["4_duracion_y_balance_anual.png"] = png(fig)
    return out
