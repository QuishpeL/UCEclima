# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Lambda 9.2 · hidrograma de entrada de un río grande SIN caudales observados, a partir de la simulación retrospectiva de GEOGLOWS v2.

Todo sale de la serie horaria de GEOGLOWS (1940 en adelante) de UN tramo de río; nada se inventa:
  - caudal pico del período de retorno Tr = Gumbel por momentos sobre los máximos HORARIOS anuales (años con ≥ 300 días de datos);
  - forma = promedio de las crecidas anuales de esa misma serie, cada una dividida para su pico (alineadas en el pico);
  - sincronía = el pico del río coincide con el bloque de máxima lluvia de la tormenta de diseño local: caso desfavorable, declarado.
GEOGLOWS es un modelo global (ECMWF): referencia externa, no observación. El resultado no está calibrado ni validado.

El análisis (descarga y estadística) lo hace UCEclima una sola vez; la corrida usa lo guardado y no necesita internet."""
import math

import numpy as np

EULER = 0.5772156649
VENTANA_SUBIDA_H = 48          # horas antes del pico que se miran en cada crecida anual
VENTANA_BAJADA_H = 72          # horas después del pico


def gumbel_momentos(maximos):
    """Parámetros de Gumbel por momentos (igual que la tabla 'gumbel' de GEOGLOWS): media y desviación de los máximos anuales."""
    m = np.asarray([v for v in maximos if np.isfinite(v)], float)
    if len(m) < 10:
        raise ValueError(f"Solo hay {len(m)} máximos anuales válidos: hacen falta al menos 10 para ajustar Gumbel.")
    return {"media": float(m.mean()), "desv": float(m.std(ddof=1)), "n_anios": int(len(m))}


def caudal_tr(gumbel, tr):
    """Caudal de período de retorno Tr (años) con Gumbel por momentos."""
    tr = float(tr)
    if tr <= 1:
        raise ValueError("El período de retorno debe ser mayor que 1 año.")
    k = -math.sqrt(6) / math.pi * (EULER + math.log(math.log(tr / (tr - 1))))
    return max(0.0, gumbel["media"] + k * gumbel["desv"])


def analizar_serie(t, q):
    """Serie horaria (t: datetime64, q: m3/s) → máximos anuales, Gumbel y forma adimensional media de la crecida anual."""
    import pandas as pd
    s = pd.Series(np.asarray(q, float), index=pd.DatetimeIndex(t)).dropna()
    s = s[~s.index.duplicated()].sort_index()
    if s.empty:
        raise ValueError("La serie de GEOGLOWS está vacía.")
    cuenta = s.groupby(s.index.year).count(); anios_ok = cuenta[cuenta >= 24 * 300].index
    s_ok = s[s.index.year.isin(anios_ok)]
    idx_max = s_ok.groupby(s_ok.index.year).idxmax()
    maximos = {int(a): float(s_ok.loc[i]) for a, i in idx_max.items()}
    g = gumbel_momentos(list(maximos.values()))
    rel = np.arange(-VENTANA_SUBIDA_H, VENTANA_BAJADA_H + 1)                       # horas respecto del pico
    formas = []
    for i in idx_max.values:
        pico = float(s.loc[i])
        if pico <= 0:
            continue
        w = s.reindex(pd.DatetimeIndex(i + pd.to_timedelta(rel, unit="h")))
        if w.isna().mean() > 0.1:
            continue
        formas.append((w.interpolate(limit_direction="both").values / pico))
    if len(formas) < 10:
        raise ValueError(f"Solo {len(formas)} crecidas anuales completas: no alcanza para una forma media.")
    forma = np.mean(formas, axis=0); forma = forma / forma[VENTANA_SUBIDA_H]        # el pico vale exactamente 1
    return {"maximos_anuales": maximos, "gumbel": g, "forma": {"t_h": rel.astype(float).tolist(), "q_rel": [round(float(v), 4) for v in forma], "n_crecidas": len(formas)},
            "caudal_medio_m3s": float(s.mean()), "inicio": str(s.index[0])[:19], "fin": str(s.index[-1])[:19], "horas": int(len(s)),
            "tabla_tr_m3s": {str(tr): round(caudal_tr(g, tr), 2) for tr in (2, 5, 10, 25, 50, 100)}}


def hidrograma(e, tr, t_pico_tormenta_s, sim_s, paso_s=300.0):
    """Hidrograma (t_s, q_m3s) de una entrada GEOGLOWS registrada para la corrida de período de retorno `tr`.
    El pico (Gumbel, Tr) cae en el instante de máxima lluvia de la tormenta (t_pico_tormenta_s); se recorta al final de la simulación y termina en Q = 0 (lo exige el solver).
    Devuelve también un informe con lo que se usó."""
    if tr is None:
        raise ValueError(f"Entrada GEOGLOWS {e.get('nombre')}: solo se usa con tormentas de DISEÑO (un evento observado no tiene período de retorno).")
    qp = caudal_tr(e["gumbel"], tr)
    th = np.asarray(e["forma"]["t_h"], float); qr = np.asarray(e["forma"]["q_rel"], float)
    t_pico_s = float(t_pico_tormenta_s) + float(e.get("desfase_h", 0.0)) * 3600.0
    t = np.arange(0.0, float(sim_s) - paso_s + 1e-6, paso_s)
    if len(t) < 3:
        raise ValueError("La simulación es demasiado corta para el hidrograma GEOGLOWS.")
    rel_h = (t - t_pico_s) / 3600.0
    q = qp * np.interp(rel_h, th, qr, left=qr[0], right=qr[-1])                   # fuera de la ventana se mantiene el borde (no se inventa cola)
    vol_completo = float((np.trapezoid if hasattr(np, "trapezoid") else np.trapz)(q, t))
    t = np.r_[t, t[-1] + paso_s]; q = np.r_[q, 0.0]                                # cierre en Q = 0
    inf = {"nombre": e.get("nombre"), "river_id": e.get("river_id"), "Tr": tr, "pico_m3s": round(qp, 2), "t_pico_h": round(t_pico_s / 3600, 2),
           "n_anios_gumbel": e["gumbel"]["n_anios"], "extrapolado": bool(float(tr) > e["gumbel"]["n_anios"]),
           "volumen_m3": round(vol_completo), "duracion_h": round(float(t[-1]) / 3600, 2),
           "nota": "GEOGLOWS v2 (modelo global, ECMWF): pico Gumbel de máximos horarios anuales y forma media de las crecidas anuales; pico sincronizado con el de la tormenta local (caso desfavorable). No calibrado."}
    return t, q, inf
