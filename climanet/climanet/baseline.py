# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Compuerta de línea base: el cambio climático NO se aplica hasta que la condición existente esté bien modelada.

Verificaciones automáticas sobre la corrida histórica (resumen.json) + validación contra evidencia observada.
Una corrida con cambio climático solo se permite si `aprobada(...)` es True (o se fuerza explícitamente).
"""
import numpy as np
import pandas as pd
import rasterio

CHEQUEOS_AUTOMATICOS = {
    "balance_masa": lambda s: s["error_balance_max_pct"] < 0.01,
    "cfl": lambda s: s["CFL_max"] <= 0.35 + 1e-9,
    "estado_completo": lambda s: s["estado"] == "final_completo",
    "fuente_idf_oficial": lambda s: s.get("idf_fuente", "").startswith("INAMHI"),
    "factor_cc_unitario": lambda s: abs(s.get("factor_cc", 1.0) - 1.0) < 1e-9,
}


def validar_contra_observaciones(hmax_tif, puntos_csv, metadatos, tol_m=0.3, minimo_pares=5):
    """Compara calado modelado vs. evidencia de inundación (x, y, calado_obs_m; 0 = punto seco).

    `metadatos` es obligatorio: {'evento': str, 'fecha': 'AAAA-MM-DD', 'crs': 'EPSG:32717', 'unidades': 'm'}.
    Se excluyen puntos fuera del ráster, en celdas nodata o con observación no finita; si quedan menos de `minimo_pares`
    la evaluación se DETIENE (un ráster vacío o un solo punto seco no pueden producir un 100 % de aciertos)."""
    faltan = [k for k in ("evento", "fecha", "crs", "unidades") if not metadatos.get(k)]
    if faltan:
        raise ValueError(f"Metadatos de validación incompletos: faltan {faltan}.")
    if str(metadatos["unidades"]).lower() not in ("m", "metros"):
        raise ValueError("Las observaciones deben estar en metros.")
    p = pd.read_csv(puntos_csv)
    if not {"x", "y", "calado_obs_m"} <= set(p.columns):
        raise ValueError("El CSV de observaciones requiere x, y, calado_obs_m.")
    with rasterio.open(hmax_tif) as s:
        if s.crs is None or s.crs != rasterio.crs.CRS.from_string(metadatos["crs"]):
            raise ValueError(f"CRS del ráster ({s.crs}) distinto del declarado para las observaciones ({metadatos['crs']}).")
        pts = list(zip(p.x, p.y))
        mod = np.full(len(p), np.nan)
        dentro = np.array([s.bounds.left <= x <= s.bounds.right and s.bounds.bottom <= y <= s.bounds.top for x, y in pts])
        if dentro.any():
            vals = np.array([v[0] for v in s.sample([q for q, d in zip(pts, dentro) if d])], float)
            vals[(vals == s.nodata) | ~np.isfinite(vals)] = np.nan
            mod[dentro] = vals
    obs = p.calado_obs_m.values.astype(float)
    ok = np.isfinite(mod) & np.isfinite(obs)
    if ok.sum() < minimo_pares:
        raise ValueError(f"Solo {int(ok.sum())} pares válidos (mínimo {minimo_pares}); {int((~dentro).sum())} puntos fuera del dominio, "
                         f"{int((dentro & ~np.isfinite(mod)).sum())} en celdas sin dato. No se puede validar.")
    m, o_ = mod[ok], obs[ok]
    io, im = o_ >= 0.05, m >= 0.05
    return {"evento": metadatos["evento"], "fecha": metadatos["fecha"], "n_pares_validos": int(ok.sum()),
            "n_excluidos": int((~ok).sum()), "MAE_m": float(np.mean(np.abs(m - o_))), "RMSE_m": float(np.sqrt(np.mean((m - o_) ** 2))),
            "sesgo_m": float(np.mean(m - o_)), "aciertos_pct": float(np.mean(io == im) * 100),
            "aciertos": int((io & im).sum()), "omisiones": int((io & ~im).sum()), "falsas_alarmas": int((~io & im).sum()),
            "dentro_tolerancia_pct": float(np.mean(np.abs(m - o_) <= tol_m) * 100)}


def evaluar(resumen, validacion=None, minimo_aciertos=70.0):
    """resumen: dict de la corrida histórica. validacion: salida de validar_contra_observaciones o None.
    Devuelve (aprobada, detalle)."""
    det = {k: bool(f(resumen)) for k, f in CHEQUEOS_AUTOMATICOS.items()}
    if validacion is None:
        det["validacion_observada"] = None  # pendiente
    else:
        det["validacion_observada"] = validacion["aciertos_pct"] >= minimo_aciertos
    ok = all(v is True for v in det.values())
    return ok, det
