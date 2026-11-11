# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""CN y Manning PROPIOS de la persona (GeoTIFF desde su PC). Tienen prioridad sobre los estimados con Earth Engine.
Se copian al proyecto (los originales no se tocan), se revisan (CRS, rango físico, cobertura sobre el área del modelo) y se registran con su fuente.
La configuración anterior queda en un .bak con sello de tiempo."""
import json
import shutil
import time
from pathlib import Path

import numpy as np

RANGO = {"cn": (1.0, 100.0), "manning": (0.005, 1.0)}


def _revisar(ruta, tipo, crs_proyecto, aoi):
    import rasterio
    from rasterio.windows import from_bounds
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ValueError(f"No existe el archivo de {tipo}: {ruta}")
    with rasterio.open(ruta) as s:
        if s.crs is None:
            raise ValueError(f"El ráster de {tipo} no tiene CRS: asígnalo en QGIS (p. ej. {crs_proyecto}).")
        avisos = []
        if s.crs.to_string() != crs_proyecto and f"EPSG:{s.crs.to_epsg()}" != crs_proyecto:
            avisos.append(f"{tipo}: CRS {s.crs} distinto del proyecto ({crs_proyecto}); el modelo lo remuestrea a su malla (vecino más cercano).")
        a = s.read(1, masked=True)
        if aoi and f"EPSG:{s.crs.to_epsg()}" == crs_proyecto:
            x0, x1, y0, y1 = aoi
            b = s.bounds
            if b.left > x0 or b.right < x1 or b.bottom > y0 or b.top < y1:
                avisos.append(f"{tipo}: no cubre toda el área de estudio del modelo; las celdas sin dato quedarán fuera.")
            try:
                a = s.read(1, masked=True, window=from_bounds(max(x0, b.left), max(y0, b.bottom), min(x1, b.right), min(y1, b.top), s.transform))
            except Exception:
                pass
        v = a.compressed()
        if v.size == 0:
            raise ValueError(f"El ráster de {tipo} no tiene valores válidos en el área.")
        lo, hi = RANGO[tipo]
        fuera = int(((v < lo) | (v > hi)).sum())
        if fuera:
            raise ValueError(f"{tipo}: {fuera} celdas fuera del rango físico [{lo}, {hi}] (mín {v.min():.4g}, máx {v.max():.4g}). ¿Unidades o archivo equivocado?")
        return {"min": float(v.min()), "max": float(v.max()), "media": round(float(v.mean()), 4), "res": abs(s.transform.a), "crs": str(s.crs)}, avisos


def registrar(carpeta, datos, cn, manning, fuente="", persona=""):
    if not str(fuente).strip():
        raise ValueError("Declara la fuente de tus CN y Manning (estudio, institución, año).")
    carpeta = Path(carpeta)
    cp = carpeta / datos.get("config_climanet", "config_climanet.json")
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    crs = datos.get("crs") or "EPSG:32717"
    info, avisos = {}, []
    for tipo, ruta in (("cn", cn), ("manning", manning)):
        info[tipo], av = _revisar(ruta, tipo, crs, cfg.get("aoi")); avisos += av
    sello = time.strftime("%Y%m%d_%H%M%S")
    dest = carpeta / "datos" / f"parametros_propios_{sello}"; dest.mkdir(parents=True)
    rel = {}
    for tipo, ruta in (("cn", cn), ("manning", manning)):
        f = dest / f"{tipo}_propio{Path(ruta).suffix.lower()}"; shutil.copy2(ruta, f)
        rel[tipo] = str(f.relative_to(carpeta)).replace("\\", "/")
    (cp.parent / f"{cp.name}.{sello}.bak").write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    cfg.update({"cn_tif": rel["cn"], "manning_tif": rel["manning"], "cn_origen": "usuario", "manning_origen": "usuario"})
    cp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    reg = {"fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "fuente": fuente, "persona": persona, "originales": {"cn": str(cn), "manning": str(manning)}, "copias": rel, "estadisticas": info, "avisos": avisos}
    (dest / "registro.json").write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"texto": f"CN y Manning propios registrados (fuente: {fuente}). Tienen prioridad sobre los de Earth Engine. CN {info['cn']['min']:g}–{info['cn']['max']:g}, Manning {info['manning']['min']:g}–{info['manning']['max']:g}.",
            "carpeta": str(dest.relative_to(carpeta)).replace("\\", "/"), "avisos": avisos, "estadisticas": info}
