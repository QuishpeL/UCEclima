# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Forzamientos de lluvia intercambiables: estaciones locales, CHIRPS, mezcla y tormenta de diseño IDF.

Todos los proveedores devuelven lluvia (mm) por paso de tiempo para un punto o un polígono (subcuenca),
así el resto del modelo no depende de la fuente.
"""
from abc import ABC, abstractmethod
from pathlib import Path
import numpy as np
import pandas as pd


def _utc(x):
    """Marca de tiempo con zona; sin zona se interpreta como UTC de forma explícita."""
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


class RainfallProvider(ABC):
    @abstractmethod
    def at(self, x, y, start=None, end=None):
        """Serie pd.Series (mm por paso) indexada por fecha en el punto (x, y) en el CRS del proyecto."""


class StationRain(RainfallProvider):
    """Estaciones locales (INAMHI, GAD, FONAG, EPMAPS, propias).

    catalogo CSV: id,nombre,x,y,tipo   (x,y en el CRS del proyecto, p.ej. UTM 17S)
    datos CSV (largo): id,fecha,lluvia_mm   (cualquier paso: 5 min, horario, diario)
    Interpolación espacial: IDW (potencia p) con control de calidad simple.
    """
    def __init__(self, catalogo_csv, datos_csv, p=2.0, max_mm_paso=None, zona_horaria="America/Guayaquil"):
        self.cat = pd.read_csv(catalogo_csv).set_index("id")
        d = pd.read_csv(datos_csv, parse_dates=["fecha"])
        if d["fecha"].dt.tz is None:   # sin zona: se interpreta en la zona declarada y se lleva a UTC
            d["fecha"] = d["fecha"].dt.tz_localize(zona_horaria).dt.tz_convert("UTC")
        else:
            d["fecha"] = d["fecha"].dt.tz_convert("UTC")
        if d["fecha"].dt.tz is None:       # las fechas sin zona se interpretan en la zona declarada y se llevan a UTC
            d["fecha"] = d["fecha"].dt.tz_localize(zona_horaria).dt.tz_convert("UTC")
        else:
            d["fecha"] = d["fecha"].dt.tz_convert("UTC")
        # Duplicados: idénticos se descartan; contradictorios son un error (no se suman).
        dup = d.duplicated(["id", "fecha"], keep=False)
        if dup.any():
            g = d[dup].groupby(["id", "fecha"])["lluvia_mm"].nunique(dropna=False)
            if (g > 1).any():
                raise ValueError(f"Registros duplicados con valores distintos: {g[g > 1].index.tolist()[:5]}")
            d = d.drop_duplicates(["id", "fecha"])
        # Banderas de calidad; el valor invalidado queda NaN (ausencia), nunca 0.
        d["bandera"] = np.where(d.lluvia_mm.isna(), "ausente", "ok")
        neg = d.lluvia_mm < 0
        d.loc[neg, "bandera"] = "negativo"
        if max_mm_paso:
            alto = d.lluvia_mm > max_mm_paso
            d.loc[alto, "bandera"] = "excede_max"
            neg = neg | alto
        d.loc[neg, "lluvia_mm"] = np.nan
        self.flags = d[["id", "fecha", "bandera"]]
        self.df = d.pivot(index="fecha", columns="id", values="lluvia_mm").sort_index()
        self.p = p

    def cobertura(self):
        """Fracción de registros válidos por estación y resumen de banderas."""
        return {"por_estacion": self.df.notna().mean().to_dict(),
                "banderas": self.flags.bandera.value_counts().to_dict()}

    def at(self, x, y, start=None, end=None):
        df = self.df.loc[_utc(start) if start else None:_utc(end) if end else None] if (start or end) else self.df
        ids = [i for i in df.columns if i in self.cat.index]
        d = np.hypot(self.cat.loc[ids, "x"].values - x, self.cat.loc[ids, "y"].values - y)
        w = 1.0 / np.maximum(d, 1.0) ** self.p
        v = df[ids].values
        ok = np.isfinite(v)
        num = np.nansum(np.where(ok, v, 0) * w, axis=1)
        den = np.sum(ok * w, axis=1)
        return pd.Series(np.where(den > 0, num / np.where(den > 0, den, 1), np.nan), index=df.index, name="lluvia_mm")


class CHIRPSRain(RainfallProvider):
    """CHIRPS diario: carpeta con chirps-v2.0.YYYY.MM.DD.tif (ya descomprimidos)."""
    def __init__(self, carpeta, crs_proyecto="EPSG:32717"):
        self.files = {}
        for f in Path(carpeta).glob("chirps*.tif"):
            y, m, d = f.stem.split(".")[-3:]
            self.files[pd.Timestamp(int(y), int(m), int(d), tz="UTC")] = f
        self.crs = crs_proyecto

    def at(self, x, y, start=None, end=None):
        import rasterio
        from rasterio.warp import transform
        out = {}
        for t in sorted(self.files):
            if (start and t < _utc(start)) or (end and t > _utc(end)):
                continue
            with rasterio.open(self.files[t]) as s:
                lon, lat = transform(self.crs, s.crs, [x], [y])
                v = next(s.sample([(lon[0], lat[0])]))[0]
                out[t] = np.nan if v < 0 else float(v)
        return pd.Series(out, name="lluvia_mm")


class MergedRain(RainfallProvider):
    """Mezcla estaciones + satélite: CHIRPS corregido por sesgo con las estaciones (factor multiplicativo
    móvil); donde hay medición local se prioriza la medición local."""
    def __init__(self, estaciones: StationRain, satelite: RainfallProvider, ventana_dias=30):
        self.e, self.s, self.w = estaciones, satelite, ventana_dias

    def at(self, x, y, start=None, end=None):
        loc = self.e.at(x, y, start, end).resample("D").sum(min_count=1)
        sat = self.s.at(x, y, start, end)
        j = pd.concat([loc, sat], axis=1, keys=["loc", "sat"]).sort_index()
        a = j.dropna()
        f = (a["loc"].rolling(self.w, min_periods=5).sum() / a["sat"].rolling(self.w, min_periods=5).sum())
        f = f.reindex(j.index).ffill().clip(0.3, 3.0).fillna(1.0)
        return j["loc"].fillna(j["sat"] * f).rename("lluvia_mm")


class DesignStorm(RainfallProvider):
    """Tormenta de diseño IDF (+ factor de cambio climático) como serie a paso fijo. Fecha sintética (no es un evento)."""
    sintetico = True
    def __init__(self, idf, tr, duracion_min, factor=1.0, bloque_min=5):
        from .idf import design_storm
        self.edges, self.blocks = design_storm(idf, tr, duracion_min, factor, bloque_min)
        self.bloque = bloque_min

    def at(self, x=None, y=None, start=None, end=None):
        idx = pd.date_range("2000-01-01", periods=len(self.blocks), freq=f"{self.bloque}min", tz="UTC")
        return pd.Series(self.blocks, index=idx, name="lluvia_mm")
