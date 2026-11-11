# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Lambda 9.2 · módulo 13 · visor de partículas «lluvia a caudal» (prototipo del 7-nov-2026 llevado al programa).

Prepara, desde UNA corrida terminada, lo que el visor anima: terreno (MDT de la corrida), evolución del calado (evolucion_calado.npz, tal como la
guardó el núcleo), volumen y área mojada, y el hietograma de la corrida (hietograma.csv) para la cortina de lluvia. No calcula ni inventa nada:
el calado se cuantiza a 8 bits con raíz cuadrada (resolución fina en calados someros) y el terreno a 16 bits. Es una visualización: la dirección de
las partículas sale de la pendiente de la superficie (cota + calado), no de velocidades guardadas. Sin calibrar ni validar."""
import base64
import json
import zlib
from pathlib import Path

import numpy as np


class ParticulasError(Exception):
    pass


def _b64(a):
    return base64.b64encode(zlib.compress(np.ascontiguousarray(a).tobytes(), 9)).decode()


def datos(carpeta_corrida, cada=5, max_celdas=1_500_000):
    import rasterio
    from rasterio.warp import reproject, Resampling
    run = Path(carpeta_corrida)
    npzs = sorted(run.glob("salida/*/evolucion_calado.npz"))
    if not npzs:
        raise ParticulasError("Esta corrida no guardó la evolución del calado (evolucion_calado.npz): vuelve a correrla con Lambda para verla en el visor de partículas.")
    npz = npzs[0]; carpeta = npz.parent
    ent = json.loads((run / "entrada.json").read_text(encoding="utf-8")) if (run / "entrada.json").exists() else {}
    cfg = ent.get("config") or {}
    d = np.load(npz); ny, nx = [int(v) for v in d["shape"]]
    if ny * nx > max_celdas:
        raise ParticulasError(f"La malla tiene {ny * nx:,} celdas: el visor de partículas admite hasta {max_celdas:,} (se pondría lento).".replace(",", "."))
    idx, h, t, V, A = d["idx"], d["h_mm"], d["t_s"], d["volumen_m3"], d["area_mojada_m2"]
    if len(idx) == 0 or len(t) < 2:
        raise ParticulasError("La corrida no tiene celdas mojadas que animar.")
    # La corrida no guarda calados < umbral (1 cm): se recorta a la crecida. Todas las fotos desde poco antes del primer volumen apreciable
    # hasta 90 fotos después y, luego, una de cada `cada`.
    i0 = max(0, int(np.argmax(V > 100)) - 6); i1 = min(len(t) - 1, i0 + 90)
    sel = np.unique(np.concatenate([np.arange(i0, i1 + 1), np.arange(i1, len(t), max(1, int(cada))), [len(t) - 1]]))
    hh = h[sel].astype(np.float32) / 1000.0; hmax = float(hh.max())
    if hmax <= 0:
        raise ParticulasError("La corrida no tiene calados mayores que cero.")
    q = np.round(255 * np.sqrt(hh / hmax)).astype(np.uint8)
    ref_f = carpeta / "hmax.tif"
    if not ref_f.exists():
        raise ParticulasError("Falta hmax.tif en la corrida.")
    dem_f = Path(str(cfg.get("dem") or ""))
    if dem_f and not dem_f.is_absolute():
        dem_f = run.parents[1] / dem_f                                           # rutas del proyecto relativas a su carpeta
    with rasterio.open(ref_f) as ref:
        T, crs, res = ref.transform, ref.crs, float(ref.res[0])
        hm = ref.read(1).ravel()[idx]
    z = np.full((ny, nx), np.nan, np.float32)
    if dem_f and dem_f.exists():
        with rasterio.open(dem_f) as s:
            reproject(s.read(1).astype(np.float32), z, src_transform=s.transform, src_crs=s.crs, src_nodata=s.nodata, dst_transform=T, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    if not np.isfinite(z).any():
        raise ParticulasError("No se encontró el MDT de la corrida para dibujar el terreno.")
    zmin, zmax = float(np.nanmin(z)), float(np.nanmax(z)); z = np.where(np.isfinite(z), z, zmin)
    zq = np.round((z - zmin) / max(zmax - zmin, 1e-6) * 65535).astype(np.uint16)
    hieto = None
    fh = next(iter(sorted(run.rglob("hietograma.csv"))), None)
    if fh:
        import pandas as pd
        dh = pd.read_csv(fh)
        if {"inicio_s", "fin_s", "lluvia_mm"} <= set(dh.columns):
            hieto = {"inicio_s": dh["inicio_s"].astype(float).tolist(), "fin_s": dh["fin_s"].astype(float).tolist(), "lluvia_mm": dh["lluvia_mm"].astype(float).round(3).tolist()}
    esc = ent.get("escenario")
    return {"proyecto": ent.get("proyecto") or run.parents[1].name, "corrida": run.name, "escenario": esc.get("nombre") if isinstance(esc, dict) else esc,
            "Tr": cfg.get("Tr"), "storm_min": cfg.get("storm_min"), "nx": nx, "ny": ny, "dx": res, "zmin": zmin, "zmax": zmax, "hmax": hmax,
            "t": [float(x) for x in t[sel]], "V": [round(float(x), 1) for x in V[sel]], "A": [round(float(x), 1) for x in A[sel]],
            "nf": int(len(sel)), "nc": int(len(idx)), "idx": _b64(idx.astype(np.uint32)), "q": _b64(q), "z": _b64(zq), "hieto": hieto,
            "control": {"max_fotos_m": round(float(hh.max()), 3), "max_hmax_tif_m": round(float(np.nanmax(hm)), 3)},
            "aviso": "Visualización de una corrida no calibrada ni validada. La dirección de las partículas sale de la pendiente de la superficie (cota + calado), no de velocidades guardadas."}
