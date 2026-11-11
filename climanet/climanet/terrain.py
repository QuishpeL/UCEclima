# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Preparación del terreno: remuestreo del DEM, relleno de depresiones, D8, acumulación y cuencas."""
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds as tr_from_bounds
from numba import njit


def load_dem(path, res, aoi=None, cobertura_minima=0.95):
    """Lee el DEM (GeoTIFF grande) a la resolución `res` (m) con promedio de bloque.
    Valida CRS proyectado en metros y cobertura de datos. El datum vertical NO se puede verificar del GeoTIFF:
    queda declarado en `meta['aviso']`. OJO: el promedio a `res` m puede borrar canales y barreras finas."""
    with rasterio.open(path) as s:
        if not s.crs or not s.crs.is_projected or abs(s.crs.linear_units_factor[1] - 1.0) > 1e-9:
            raise ValueError(f"El DEM debe estar en un CRS proyectado en metros (CRS actual: {s.crs}).")
        x0, y0, x1, y1 = (s.bounds if not aoi else (aoi[0], aoi[2], aoi[1], aoi[3]))
        b = s.bounds
        if x0 < b.left or x1 > b.right or y0 < b.bottom or y1 > b.top:
            raise ValueError("El AOI sale de la extensión del DEM.")
        w, h = int((x1 - x0) / res), int((y1 - y0) / res)
        arr = s.read(1, window=from_bounds(x0, y0, x1, y1, s.transform), out_shape=(h, w),
                     resampling=Resampling.average).astype("float64")
        nd, crs = s.nodata, s.crs
    arr[(arr == nd) | (arr < -1e3) | (arr > 1e4) | ~np.isfinite(arr)] = np.nan
    cob = float(np.isfinite(arr).mean())
    if cob < cobertura_minima:
        raise ValueError(f"Cobertura de datos del DEM en el AOI = {cob:.1%} < {cobertura_minima:.0%}.")
    tr = tr_from_bounds(x0, y0, x1, y1, w, h)
    meta = dict(driver="GTiff", height=h, width=w, count=1, dtype="float32", crs=crs, transform=tr,
                nodata=-9999, compress="deflate", cobertura_dem=cob,
                aviso="datum vertical no verificado; remuestreo por promedio puede suavizar canales y barreras")
    return arr, meta


def match_raster(path, meta, shape, resampling=Resampling.nearest, cobertura_minima=0.95):
    """Reproyecta un ráster temático a la malla del modelo declarando nodata. Devuelve NaN donde no hay dato.
    Falla si el solape con el dominio activo es menor que `cobertura_minima` (no se rellena en silencio)."""
    with rasterio.open(path) as s:
        src_nd = s.nodata
        src = s.read(1).astype("float64")
        if src_nd is not None:
            src[src == src_nd] = np.nan
        dst = np.full(shape, np.nan)
        reproject(src, dst, src_transform=s.transform, src_crs=s.crs, src_nodata=np.nan,
                  dst_transform=meta["transform"], dst_crs=meta["crs"], dst_nodata=np.nan, resampling=resampling)
    cob = float(np.isfinite(dst).mean())
    if cob < cobertura_minima:
        raise ValueError(f"{path}: solape/cobertura con el dominio = {cob:.1%} < {cobertura_minima:.0%}.")
    return dst


def fill_sinks(dem):
    """Rellena depresiones. NO usar sobre el dominio hidráulico (borra almacenamiento y barreras reales);
    solo para delimitar cuencas/direcciones de flujo en terreno natural."""
    from skimage.morphology import reconstruction
    active = np.isfinite(dem)
    base = np.where(active, dem, np.nanmin(dem))
    seed = np.full_like(base, base.max())
    seed[0, :], seed[-1, :], seed[:, 0], seed[:, -1] = base[0, :], base[-1, :], base[:, 0], base[:, -1]
    return np.where(active, reconstruction(seed, base, method="erosion"), np.nan)


@njit(cache=True)
def _d8(z, dx):
    ny, nx = z.shape
    ddr = np.array([-1, -1, -1, 0, 0, 1, 1, 1]); ddc = np.array([-1, 0, 1, -1, 1, -1, 0, 1])
    fd = np.full((ny, nx), -1, np.int8)
    for r in range(ny):
        for c in range(nx):
            if np.isnan(z[r, c]):
                continue
            best = 0.0
            for k in range(8):
                rr, cc = r + ddr[k], c + ddc[k]
                if 0 <= rr < ny and 0 <= cc < nx and not np.isnan(z[rr, cc]):
                    d = dx * (1.41421356 if (ddr[k] != 0 and ddc[k] != 0) else 1.0)
                    s = (z[r, c] - z[rr, cc]) / d
                    if s > best:
                        best = s; fd[r, c] = k
    return fd


def flow_accumulation(dem_filled, dx):
    """Acumulación D8 (nº de celdas aportantes) sobre un DEM sin depresiones."""
    fd = _d8(dem_filled, dx)
    ny, nx = dem_filled.shape
    ddr = np.array([-1, -1, -1, 0, 0, 1, 1, 1]); ddc = np.array([-1, 0, 1, -1, 1, -1, 0, 1])
    order = np.argsort(-np.nan_to_num(dem_filled, nan=-1e9), axis=None)
    acc = np.where(np.isfinite(dem_filled), 1.0, 0.0)
    return fd, _accumulate(fd, acc, order, ddr, ddc)


@njit(cache=True)
def _accumulate(fd, acc, order, ddr, ddc):
    ny, nx = fd.shape
    for idx in order:
        r, c = idx // nx, idx % nx
        k = fd[r, c]
        if k >= 0:
            acc[r + ddr[k], c + ddc[k]] += acc[r, c]
    return acc


def slope_deg(dem, dx):
    gy, gx = np.gradient(np.where(np.isfinite(dem), dem, np.nanmean(dem)), dx)
    return np.degrees(np.arctan(np.hypot(gx, gy)))
