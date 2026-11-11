# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""IDF oficiales INAMHI (libro de intensidades) como fuente de Climanet.

Método del libro: i(Tr,t) = K * Idtr(Tr) * t^-n  (i mm/h, t min, Idtr = intensidad máx. 24 h).
  estacion : cuadro IDF exacto de la pluviográfica de referencia (usar si el sitio está a <= radio_km)
  escalada : cuadro de la estación * Idtr_sitio / Idtr_ref
  sitio    : ecuaciones de la zona con Idtr interpolado (IDW) al sitio
Siempre devuelve la condición HISTÓRICA (cc = 1). El cambio climático se aplica aparte (idf.apply_climate)
y solo después de que la línea base haya pasado la compuerta (ver baseline.py).
"""
import math
from pathlib import Path
import numpy as np
import pandas as pd

D = Path(__file__).resolve().parent / "data" / "inamhi"
DUR = [5, 10, 15, 20, 30, 60, 120, 360, 1440]
TRS = [2, 5, 10, 25, 50, 100]
TRC = [f"TR{t}" for t in TRS]
_c = {}


def _cargar():
    if not _c:
        _c["zon"] = pd.read_csv(D / "zonas_ecuaciones_inamhi.csv", encoding="utf-8-sig")
        _c["est"] = pd.read_csv(D / "estaciones_inamhi_todas.csv", encoding="utf-8-sig")
        _c["tab"] = pd.read_csv(D / "idf_tablas_72_estaciones.csv", encoding="utf-8-sig")
    return _c["zon"], _c["est"], _c["tab"]


def _hav(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def idf_estacion(codigo):
    """Cuadro IDF oficial de una pluviográfica (p. ej. 'M0037' Milagro-Ingenio Valdez). Filas Tr, columnas min."""
    _, _, tab = _cargar()
    t = tab[tab.codigo == codigo].pivot(index="tr_anios", columns="duracion_min", values="intensidad_mmh")
    if t.empty:
        raise KeyError(f"{codigo} no tiene cuadro IDF en el libro (solo pluviográficas)")
    return t.reindex(index=TRS, columns=DUR)


def _idtr_sitio(lat, lon, k=3, p=2.0):
    _, est, _ = _cargar()
    e = est[(est.fuente_idtr == "Tabla 3") & est.lat.notna() & ~est.coord_revisar].copy()
    e["dist_km"] = [_hav(lat, lon, a, b) for a, b in zip(e.lat, e.lon)]
    n = e.sort_values("dist_km").head(k)
    w = np.array([1.0] + [0.0] * (len(n) - 1)) if n.dist_km.iloc[0] < 0.05 else 1.0 / n.dist_km.values ** p
    w = w / w.sum()
    return pd.Series({c: float((n[c].values * w).sum()) for c in TRC})


def _eval_zona(cod, idtr):
    zon, _, _ = _cargar()
    z = zon[zon.codigo == cod].sort_values("t_desde_min")
    out = pd.DataFrame(index=TRS, columns=DUR, dtype=float)
    for t in DUR:
        r = z[(z.t_desde_min <= t + 1e-9) & (z.t_hasta_min >= t - 1e-9)]
        r = r.iloc[0] if len(r) else z.iloc[-1]
        for tr in TRS:
            out.loc[tr, t] = r.K * idtr[f"TR{tr}"] * t ** (-r.n)
    return out


def idf_sitio(lat, lon, modo="auto", radio_km=10.0, estacion=None):
    """IDF oficial para cualquier punto. Devuelve (tabla, info). `estacion` fuerza la pluviográfica de referencia."""
    _, est, _ = _cargar()
    pl = est.dropna(subset=["lat", "lon"]).copy()
    pl = pl[~pl.coord_revisar & pl.tipo.str.startswith("pluviografica")]
    pl["dist_km"] = [_hav(lat, lon, a, b) for a, b in zip(pl.lat, pl.lon)]
    ref = pl.sort_values("dist_km").iloc[0] if estacion is None else est[est.codigo == estacion].iloc[0]
    d_ref = float(ref.dist_km) if estacion is None else _hav(lat, lon, ref.lat, ref.lon)
    idtr = _idtr_sitio(lat, lon)
    est_tab = idf_estacion(ref.codigo)
    sitio = _eval_zona(ref.codigo, idtr)
    escalada = est_tab.mul([idtr[f"TR{t}"] / ref[f"TR{t}"] for t in TRS], axis=0) if ref.fuente_idtr == "Tabla 3" else None
    if modo == "auto":
        modo = "estacion" if d_ref <= radio_km else ("escalada" if escalada is not None else "sitio")
    tabla = {"estacion": est_tab, "escalada": escalada, "sitio": sitio}[modo]
    info = {"fuente": "INAMHI libro de intensidades", "modo": modo, "estacion_ref": ref.codigo, "nombre_ref": ref.nombre,
            "dist_ref_km": round(d_ref, 2), "cc_factor": 1.0, "avisos": []}
    if d_ref > 60:
        info["avisos"].append(f"pluviográfica de referencia a {d_ref:.0f} km: revisar zonificación del libro")
    return tabla.round(2), info
