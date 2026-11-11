# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Estaciones INAMHI de referencia más cercanas a un sitio: meteorológicas (libro de intensidades) e hidrométricas (anuarios hidrológicos)."""
import math
from pathlib import Path

import pandas as pd

HIDRO = Path(__file__).parent / "datos_referencia" / "estaciones_hidrometricas_inamhi.csv"


def _km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2); dp = p2 - p1; dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def cercanas(lat, lon, n=5):
    lat, lon = float(lat), float(lon)
    import uceclima  # noqa: F401  (fija la ruta del núcleo)
    from climanet import inamhi
    _, est, _ = inamhi._cargar()
    m = est.dropna(subset=["lat", "lon"]).copy()
    m["dist_km"] = [_km(lat, lon, a, b) for a, b in zip(m.lat, m.lon)]
    m = m.sort_values("dist_km").head(n)
    meteo = [{"codigo": r.codigo, "nombre": str(r.nombre), "tipo": "pluviográfica" if str(r.tipo).startswith("pluviografica") else "pluviométrica",
              "dist_km": round(float(r.dist_km), 1), "z_msnm": None if pd.isna(r.z_msnm) else float(r.z_msnm), "anios": None if pd.isna(r.n_anios) else int(r.n_anios)} for r in m.itertuples()]
    hidro = []
    if HIDRO.exists():
        h = pd.read_csv(HIDRO)
        h["dist_km"] = [_km(lat, lon, a, b) for a, b in zip(h.lat, h.lon)]
        hidro = [{"codigo": r.codigo, "nombre": str(r.nombre), "tipo": "hidrométrica", "dist_km": round(float(r.dist_km), 1), "z_msnm": None if pd.isna(r.z_msnm) else float(r.z_msnm),
                  "lon": float(r.lon), "lat": float(r.lat)} for r in h.sort_values("dist_km").head(n).itertuples()]
    return {"meteorologicas": meteo, "hidrometricas": hidro, "fuente": "INAMHI: libro de intensidades (meteorológicas) y anuarios hidrológicos 2010–2013 (hidrométricas)"}
