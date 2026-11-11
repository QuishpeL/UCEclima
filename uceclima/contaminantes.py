# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Epsilon · maqueta isométrica de dispersión de contaminantes (BASE pedagógica, se desarrollará en el doctorado).
Derrame instantáneo de una masa M en un tramo de río rectangular (ancho B, calado h, pendiente S, Manning n):
  U = (1/n) R^(2/3) S^(1/2) con R = B·h/(B + 2h)           velocidad media (Manning)
  u* = √(g R S)                                            velocidad de corte
  K  = coeficiente de dispersión longitudinal (a elegir):
       Elder (1959)                  K = 5,93 h u*
       Fischer (1975)                K = 0,011 U² B² / (h u*)
       Seo y Cheong (1998)           K = 5,915 (B/h)^0,620 (U/u*)^1,428 h u*
       Deng, Singh y Bengtsson (2001) K = (0,15 / (8 εt0)) (U/u*)² (B/h)^(5/3) h u*,  εt0 = 0,145 + (1/3520)(U/u*)(B/h)^1,38
       Kashefipour y Falconer (2002) K = 10,612 h U (U/u*)
  εt = 0,6 h u*                                            mezcla transversal (Fischer et al. 1979; orden de magnitud para ríos naturales)
  C(x, y, t) = M / (4π t h √(K εt)) · exp(−(x − x0 − U t)² / (4 K t)) · Σ_imágenes exp(−(y − y_img)² / (4 εt t)) · exp(−k t)
               solución de advección–dispersión 2D promediada en la vertical, con orillas reflejantes (método de imágenes) y decaimiento de primer orden k.
NO está calibrado ni validado: es un escenario ilustrativo. Los coeficientes son los publicados en cada artículo (ver REFERENCIAS); verifícalos antes de un uso profesional.
En el doctorado: U, h y B desde una corrida 2D de UCEclima, sustancias reales, ensayos con trazador para calibrar K."""
import json
import math
import time
from pathlib import Path

import numpy as np

G = 9.81
METODOS = ("seo_cheong_1998", "kashefipour_falconer_2002", "deng_2001", "fischer_1975", "elder_1959")
REFERENCIAS = [
    {"clave": "taylor_1954", "texto": "Taylor, G.I. The dispersion of matter in turbulent flow through a pipe. Proc. R. Soc. Lond. A 1954, 223, 446–468.", "doi": "10.1098/rspa.1954.0130", "uso": "origen de la dispersión longitudinal"},
    {"clave": "elder_1959", "texto": "Elder, J.W. The dispersion of marked fluid in turbulent shear flow. J. Fluid Mech. 1959, 5, 544–560.", "doi": "10.1017/S0022112059000374", "uso": "K = 5,93 h u*"},
    {"clave": "seo_cheong_1998", "texto": "Seo, I.W.; Cheong, T.S. Predicting longitudinal dispersion coefficient in natural streams. J. Hydraul. Eng. 1998, 124, 25–32.", "doi": "10.1061/(ASCE)0733-9429(1998)124:1(25)", "uso": "K empírico para ríos naturales"},
    {"clave": "deng_2001", "texto": "Deng, Z.-Q.; Singh, V.P.; Bengtsson, L. Longitudinal dispersion coefficient in straight rivers. J. Hydraul. Eng. 2001, 127, 919–927.", "doi": "10.1061/(ASCE)0733-9429(2001)127:11(919)", "uso": "K teórico con mezcla transversal"},
    {"clave": "kashefipour_falconer_2002", "texto": "Kashefipour, S.M.; Falconer, R.A. Longitudinal dispersion coefficients in natural channels. Water Res. 2002, 36, 1596–1608.", "doi": "10.1016/S0043-1354(01)00351-7", "uso": "K empírico (Water Research, Q1)"},
    {"clave": "disley_2015", "texto": "Disley, T.; Gharabaghi, B.; Mahboubi, A.A.; McBean, E.A. Predictive equation for longitudinal dispersion coefficient. Hydrol. Process. 2015, 29, 161–172.", "doi": "10.1002/hyp.10139", "uso": "revisión y ecuación más reciente (pendiente de incorporar)"},
    {"clave": "fischer_1979", "texto": "Fischer, H.B.; List, E.J.; Koh, R.C.Y.; Imberger, J.; Brooks, N.H. Mixing in Inland and Coastal Waters; Academic Press: New York, NY, USA, 1979.", "doi": "libro (sin DOI verificado)", "uso": "εt ≈ 0,6 h u*; K de Fischer (1975); solución con imágenes"},
]


class ContaminanteError(ValueError):
    pass


def hidraulica(B, h, S, n):
    if min(B, h, S, n) <= 0:
        raise ContaminanteError("Ancho, calado, pendiente y Manning deben ser positivos.")
    R = B * h / (B + 2 * h); U = (1 / n) * R ** (2 / 3) * math.sqrt(S); us = math.sqrt(G * R * S)
    return {"U_ms": U, "Q_m3s": U * B * h, "u_estrella_ms": us, "R_m": R, "Froude": U / math.sqrt(G * h)}


def coef_K(metodo, U, us, B, h):
    if metodo == "elder_1959":
        return 5.93 * h * us
    if metodo == "fischer_1975":
        return 0.011 * U ** 2 * B ** 2 / (h * us)
    if metodo == "seo_cheong_1998":
        return 5.915 * (B / h) ** 0.620 * (U / us) ** 1.428 * h * us
    if metodo == "deng_2001":
        et0 = 0.145 + (1 / 3520) * (U / us) * (B / h) ** 1.38
        return (0.15 / (8 * et0)) * (U / us) ** 2 * (B / h) ** (5 / 3) * h * us
    if metodo == "kashefipour_falconer_2002":
        return 10.612 * h * U * (U / us)
    raise ContaminanteError("Método de K no reconocido: " + ", ".join(METODOS))


def escenario(M_kg, B, h, S, n, L_m, t_h, metodo="seo_cheong_1998", k_dia=0.0, y0_frac=0.0, x0_m=0.0, nx=90, ny=14, nt=40, umbral_mg_l=None, venas=True, irregularidad=0.15):
    """Concentración (mg/L) en una malla nx × ny del tramo [0, L] × [0, B] para nt instantes hasta t_h. y0_frac: 0 = orilla, 0,5 = centro."""
    if M_kg <= 0 or L_m <= 0 or t_h <= 0:
        raise ContaminanteError("Masa, longitud del tramo y tiempo deben ser positivos.")
    hd = hidraulica(B, h, S, n); U, us = hd["U_ms"], hd["u_estrella_ms"]
    K = coef_K(metodo, U, us, B, h); et = 0.6 * h * us; kd = k_dia / 86400.0
    x = (np.arange(nx) + 0.5) * L_m / nx; y = (np.arange(ny) + 0.5) * B / ny; y0 = float(np.clip(y0_frac, 0, 1)) * B
    ts = np.linspace(t_h * 3600 / nt, t_h * 3600, nt); M_mg = M_kg * 1e6
    frames, cmax, xpico = [], [], []
    X, Y = np.meshgrid(x, y)
    for t in ts:
        fx = np.exp(-(X - x0_m - U * t) ** 2 / (4 * K * t))
        fy = sum(np.exp(-(Y - (2 * m * B + s * y0)) ** 2 / (4 * et * t)) for m in range(-3, 4) for s in (1, -1))      # orillas reflejantes
        C = M_mg / (4 * math.pi * t * h * math.sqrt(K * et)) * fx * fy * math.exp(-kd * t) / 1000.0                    # mg/m³ → mg/L
        frames.append(np.round(C, 6).tolist()); cmax.append(float(C.max())); xpico.append(float(x0_m + U * t))
    L_mezcla = (0.4 if y0_frac in (0, 1) else 0.1) * U * B ** 2 / et                                                    # Fischer et al. (1979)
    res = {"entradas": {"M_kg": M_kg, "B_m": B, "h_m": h, "S": S, "n": n, "L_m": L_m, "t_h": t_h, "metodo_K": metodo, "k_dia": k_dia, "y0_frac": y0_frac, "x0_m": x0_m},
           "hidraulica": {k: round(v, 4) for k, v in hd.items()}, "K_m2s": round(K, 4), "epsilon_t_m2s": round(et, 5),
           "K_todos_m2s": {m: round(coef_K(m, U, us, B, h), 3) for m in METODOS},
           "distancia_mezcla_transversal_m": round(L_mezcla, 1), "Peclet": round(U * L_m / K, 1),
           "x_m": np.round(x, 2).tolist(), "y_m": np.round(y, 3).tolist(), "t_s": np.round(ts, 1).tolist(), "C_mg_l": frames,
           "C_max_mg_l": cmax, "x_pico_m": xpico, "llega_al_final_h": round((L_m - x0_m) / U / 3600, 2) if U > 0 else None,
           "referencias": REFERENCIAS,
           "aviso": "Escenario ilustrativo: canal rectangular uniforme, derrame instantáneo, sin calibrar ni validar. No es una predicción ni un estudio de impacto."}
    if venas:
        res["venas"] = particulas(B, h, S, n, L_m, t_h, y0_frac=y0_frac, x0_m=x0_m, nt=nt, irregularidad=irregularidad)
    if umbral_mg_l:
        res["umbral_mg_l"] = umbral_mg_l
        res["tramo_sobre_umbral_m"] = [float(L_m / nx * (np.asarray(f).max(axis=0) > umbral_mg_l).sum()) for f in frames]
    return res


def guardar(carpeta, params, persona=""):
    """Guarda el escenario (entradas y resumen, sin la malla) en registro/contaminantes/ del proyecto. Nada se sobrescribe."""
    r = escenario(**params); d = Path(carpeta) / "registro" / "contaminantes"; d.mkdir(parents=True, exist_ok=True)
    f = d / f"escenario_{time.strftime('%Y%m%d_%H%M%S')}.json"
    r.pop("C_mg_l", None); v = r.pop("venas", None)
    if v: r["venas_resumen"] = {k: v[k] for k in ("N", "K_particulas_m2s", "tiempo_zona_advectiva_s", "irregularidad", "nota")}
    f.write_text(json.dumps({"persona": persona, **r}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"archivo": str(f.relative_to(carpeta)).replace("\\", "/")}

def particulas(B, h, S, n, L_m, t_h, y0_frac=0.0, x0_m=0.0, N=1500, nt=40, irregularidad=0.15, potencia=2.0, semilla=7):
    """«Venas» de la zona advectiva: partículas con velocidad según su posición transversal (rápidas al centro, lentas en las orillas,
    con una irregularidad del lecho de amplitud `irregularidad` que forma varias venas) y mezcla turbulenta aleatoria (εt = 0,6 h u*;
    difusión longitudinal local igual a εt). Al mezclarse a lo ancho, la nube pasa de venas a la mancha gaussiana (dispersión de
    Taylor 1954 / Elder 1959). Devuelve posiciones por instante y el K efectivo que producen las partículas (para contrastar con la fórmula)."""
    hd = hidraulica(B, h, S, n); U, us = hd["U_ms"], hd["u_estrella_ms"]; et = 0.6 * h * us
    rng = np.random.default_rng(semilla); fases = rng.uniform(0, 2 * np.pi, 4); ondas = np.array([3, 5, 7, 11])
    def perfil(y):
        eta = np.clip(2 * y / B - 1, -1, 1); f = (1 - np.abs(eta) ** potencia) * (potencia + 1) / potencia      # media = 1 en [0, B]
        f = f * (1 + irregularidad * np.sum([np.sin(k_ * np.pi * y / B + ph) for k_, ph in zip(ondas, fases)], axis=0) / 2)
        return U * np.maximum(f, 0.02)
    y0 = float(np.clip(y0_frac, 0, 1)) * B
    y = np.clip(y0 + rng.normal(0, 0.03 * B, N), 0, B); x = x0_m + rng.normal(0, 0.005 * L_m, N)
    ts = np.linspace(t_h * 3600 / nt, t_h * 3600, nt); dt_max = min(5.0, 0.05 * B * B / max(et, 1e-6) / 200); t = 0.0
    xs, ys, vs, var = [], [], [], []
    for T in ts:
        while t < T - 1e-9:
            dt = min(dt_max, T - t)
            x += perfil(y) * dt + np.sqrt(2 * et * dt) * rng.normal(size=N)
            y += np.sqrt(2 * et * dt) * rng.normal(size=N); y = np.abs(y); y = np.where(y > B, 2 * B - y, y)       # orillas reflejantes
            t += dt
        xs.append(np.round(x, 1).tolist()); ys.append(np.round(y, 2).tolist()); vs.append(np.round(perfil(y) / U, 2).tolist()); var.append(float(np.var(x)))
    n2 = max(2, nt // 2); K_part = float((var[-1] - var[n2 - 1]) / (2 * (ts[-1] - ts[n2 - 1]))) if nt > 2 else None
    return {"N": N, "t_s": np.round(ts, 1).tolist(), "x_m": xs, "y_m": ys, "v_rel": vs, "K_particulas_m2s": None if K_part is None else round(K_part, 2),
            "tiempo_zona_advectiva_s": round(0.4 * B ** 2 / et, 0), "irregularidad": irregularidad,
            "nota": "Venas: ilustración de la zona advectiva (perfil transversal de velocidad + irregularidad del lecho declarada). Tras ~0,4 B²/εt la nube se vuelve gaussiana."}



def _camino_d8(z, T, r0, c0, L_m):
    """Recorrido aguas abajo por máxima pendiente (D8) desde la celda (r0, c0) sobre un MDT ya sin depresiones, hasta L_m metros."""
    ny, nx = z.shape; dx = abs(T.a); camino = [(r0, c0)]; s = 0.0; vistos = {(r0, c0)}
    while s < L_m:
        r, c = camino[-1]; mejor, sig = 0.0, None
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                rr, cc = r + a, c + b
                if (a or b) and 0 <= rr < ny and 0 <= cc < nx and (rr, cc) not in vistos and np.isfinite(z[rr, cc]):
                    d = dx * math.hypot(a, b); p = (z[r, c] - z[rr, cc]) / d
                    if p > mejor or (sig is None and p >= 0 and mejor == 0):
                        mejor, sig = p, (rr, cc)
        if sig is None:
            break
        s += dx * math.hypot(sig[0] - r, sig[1] - c); camino.append(sig); vistos.add(sig)
    return camino


def planta(carpeta, lon, lat, params, exagerar_ancho=8.0, instantes=(0.25, 0.5, 0.75, 1.0)):
    """Vista en planta sobre imagen satelital: la mancha del escenario se dibuja a lo largo del cauce real (D8 desde el punto del derrame
    sobre el MDT del proyecto). El ancho se exagera para que se vea (se declara). Devuelve la figura PNG con 4 instantes."""
    import rasterio
    from rasterio.windows import from_bounds
    from pyproj import Transformer
    import contextily as cx
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, LogNorm
    from climanet import terrain
    carpeta = Path(carpeta); cfg = json.loads(next(carpeta.glob("config_climanet.json")).read_text(encoding="utf-8"))
    dem = Path(cfg["dem"]) if Path(cfg["dem"]).is_absolute() else carpeta / cfg["dem"]
    p = {k: v for k, v in params.items() if k in ("M_kg", "B", "h", "S", "n", "L_m", "t_h", "metodo", "k_dia", "y0_frac", "umbral_mg_l")}
    r = escenario(**p, venas=False, nx=120, ny=10, nt=40)
    with rasterio.open(dem) as s_:
        crs = s_.crs; x0, y0 = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(float(lon), float(lat))
        m = float(p["L_m"]) * 1.3 + 500
        win = from_bounds(x0 - m, y0 - m, x0 + m, y0 + m, s_.transform); z = s_.read(1, window=win, boundless=True, fill_value=np.nan).astype("float64"); T = s_.window_transform(win)
    if not np.isfinite(z).any():
        raise ContaminanteError("El punto del derrame queda fuera del MDT del proyecto.")
    zf = terrain.fill_sinks(z); inv = ~T; c0, r0 = inv * (x0, y0)
    camino = _camino_d8(zf, T, int(r0), int(c0), float(p["L_m"]))
    if len(camino) < 3:
        raise ContaminanteError("No se pudo trazar el cauce aguas abajo desde ese punto (¿está en una cresta o en el borde del MDT?).")
    xy = np.array([T * (c + 0.5, rr + 0.5) for rr, c in camino]); seg = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    to3857 = Transformer.from_crs(crs, 3857, always_xy=True); X3, Y3 = to3857.transform(xy[:, 0], xy[:, 1])
    tang = np.gradient(np.c_[X3, Y3], axis=0); tang /= np.linalg.norm(tang, axis=1)[:, None] + 1e-12; nrm = np.c_[-tang[:, 1], tang[:, 0]]
    xs_r = np.asarray(r["x_m"]); ys_r = np.asarray(r["y_m"]); B = float(p["B"]); W = B * exagerar_ancho
    cmap = LinearSegmentedColormap.from_list("cont", ["#d9dadb", "#9ea0a2", "#545456", "#1c1c1d"])      # Omega O4: carboncillo
    cmax0 = max(r["C_max_mg_l"][0], 1e-9); vmin = max((p.get("umbral_mg_l") or cmax0 / 100) / 10, cmax0 / 1e4)
    fig, axs = plt.subplots(2, 2, figsize=(13, 12), dpi=150); pad = max(seg[-1] * 0.15, 300)
    for ax, fr in zip(axs.ravel(), instantes):
        k = min(len(r["t_s"]) - 1, int(round(fr * (len(r["t_s"]) - 1)))); C = np.asarray(r["C_mg_l"][k])
        ax.set_xlim(X3.min() - pad, X3.max() + pad); ax.set_ylim(Y3.min() - pad, Y3.max() + pad); ax.set_aspect("equal")
        try:
            cx.add_basemap(ax, source=cx.providers.Esri.WorldImagery, attribution=False)
        except Exception:
            pass
        ax.plot(X3, Y3, color="#f2f2f2", lw=0.9, alpha=0.85)
        for j in range(len(xs_r)):
            sj = xs_r[j]
            if sj > seg[-1]: break
            i = int(np.searchsorted(seg, sj)); i = min(i, len(seg) - 1)
            for q in range(len(ys_r)):
                c = C[q, j]
                if c <= vmin: continue
                off = (ys_r[q] / B - (0.0 if p.get("y0_frac", 0) == 0 else 0.5)) * W
                ax.scatter(X3[i] + nrm[i, 0] * off, Y3[i] + nrm[i, 1] * off, s=10, c=[cmap(LogNorm(vmin, cmax0)(c))], edgecolors="none", alpha=0.9)
        ax.scatter([X3[0]], [Y3[0]], marker="v", s=90, c="#ffffff", edgecolors="#1c1c1d", linewidths=1.0, zorder=5)
        ax.set_title(f"t = {r['t_s'][k] / 3600:.2f} h · C máx {r['C_max_mg_l'][k]:.2f} mg/L", fontsize=10); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"Derrame de {p['M_kg']:g} kg · K {r['K_m2s']:.1f} m²/s ({p.get('metodo', 'seo_cheong_1998')}) · cauce trazado por D8 sobre el MDT del proyecto · ancho exagerado ×{exagerar_ancho:g}\n"
                 "Escenario ilustrativo sin calibrar: canal equivalente uniforme a lo largo del cauce real; no es un estudio de impacto.", fontsize=11, color="#1F4E79")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    d = carpeta / "registro" / "contaminantes"; d.mkdir(parents=True, exist_ok=True); f = d / f"planta_{time.strftime('%Y%m%d_%H%M%S')}.png"; fig.savefig(f); plt.close(fig)
    return {"figura": str(f.relative_to(carpeta)).replace("\\", "/"), "longitud_cauce_trazado_m": round(float(seg[-1]), 0), "celdas_camino": len(camino), "K_m2s": r["K_m2s"]}
