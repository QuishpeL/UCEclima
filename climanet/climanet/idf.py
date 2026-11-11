# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Curvas IDF, escenarios de cambio climático y tormentas de diseño."""
import numpy as np
import pandas as pd
from .hydrology import alternating_blocks

# Por ahora SOLO condición de diseño con IDF histórica (factor 1). Los escenarios de cambio climático están
# desactivados hasta aprobar la línea base: load_scenarios exige un CSV con procedencia (fuente, modelo, periodo).
DEFAULT_SCENARIOS = {"diseno_idf_historica": 1.00}


def load_idf(path):
    """CSV con filas = Tr (años), columnas = duración (min), valores = intensidad (mm/h)."""
    idf = pd.read_csv(path, index_col=0)
    idf.columns = idf.columns.astype(int)
    idf.index = idf.index.astype(int)
    return idf


def load_scenarios(path=None):
    """Sin `path`: solo diseño histórico. Con CSV: columnas escenario,factor,fuente (la fuente es obligatoria)."""
    if path is None:
        return dict(DEFAULT_SCENARIOS)
    df = pd.read_csv(path)
    if not {"escenario", "factor", "fuente"} <= set(df.columns) or df["fuente"].isna().any():
        raise ValueError("El CSV de escenarios requiere escenario,factor,fuente (trazabilidad obligatoria).")
    return {**DEFAULT_SCENARIOS, **{str(r.escenario): float(r.factor) for r in df.itertuples()}}


def apply_climate(idf, factor):
    return idf * float(factor)


def design_storm(idf, tr, duration_min, factor=1.0, block_min=5):
    """Hietograma de bloques alternos. Devuelve (límites_s, mm por bloque)."""
    row = idf.loc[tr] * factor
    return alternating_blocks(idf.columns.astype(float), row.values, duration_min, block_min)


def fit_power_idf(durations_min, intensities_mmh):
    """Ajuste i = a / (d + b)^c por mínimos cuadrados (para extrapolar duraciones)."""
    from scipy.optimize import curve_fit
    f = lambda d, a, b, c: a / (d + b) ** c
    p, _ = curve_fit(f, durations_min, intensities_mmh, p0=[500, 10, .8], maxfev=20000)
    return p
