# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Datos del visor 3D de resultados: terreno y capas REALES de una corrida (calado máximo, velocidad máxima, duración con calado ≥ 0,3 m).
No calcula nada nuevo: solo lee los rásteres que escribió el núcleo y los entrega como mallas regulares. Una capa que no existe o no coincide con la malla se omite."""
import json
from pathlib import Path
import numpy as np
import rasterio

from . import mapas

CAPAS = [("hmax", "hmax.tif", "Calado máximo", "m", "diseño IDF histórica, no es un evento observado"),
         ("vmax", "vmax.tif", "Velocidad máxima", "m/s", "velocidad de la celda en el instante de máximo, ver CLIMANET"),
         ("duracion", "duracion_h_ge_03m.tif", "Duración con calado ≥ 0,3 m", "h", "horas simuladas con calado ≥ 0,3 m")]


def _lista(a, nd=3):
    a = np.asarray(a, float)
    return [None if not np.isfinite(v) else round(float(v), nd) for v in a.ravel()]


def _rios(estado, t, nx, ny, crs):
    """Omega O3: tramos HydroSHEDS de la última descarga «rios» del proyecto, recortados a la malla, en coordenadas de celda (i = columna, j = fila)."""
    try:
        import geopandas as gpd
        from shapely.geometry import box
        fs = sorted((Path(estado.carpeta) / "datos_descargados").glob("rios_merge_*/rios_merge.gpkg")) or sorted((Path(estado.carpeta) / "datos_descargados").glob("rios_*/rios_hydrosheds.gpkg"))
        if not fs:
            return []
        g = gpd.read_file(fs[-1]).to_crs(str(crs)); x0, y0 = t.c, t.f; dx, dy = t.a, t.e
        caja = box(x0, y0 + dy * ny, x0 + dx * nx, y0); g = g[g.intersects(caja)].copy(); g["geometry"] = g.intersection(caja)
        out = []
        for _, r in g.sort_values("UPLAND_SKM").iterrows():
            geoms = getattr(r.geometry, "geoms", [r.geometry])
            for l in geoms:
                if l.geom_type != "LineString" or l.length < abs(dx):
                    continue
                n = max(2, int(l.length / abs(dx)) + 1)
                pts = [l.interpolate(k / (n - 1), normalized=True) for k in range(n)]
                out.append({"area_km2": round(float(r.get("UPLAND_SKM", 0)), 1), "ij": [[round((p.x - x0) / dx - 0.5, 2), round((p.y - y0) / dy - 0.5, 2)] for p in pts]})
        return out
    except Exception:
        return []


def _osm_lineas(estado, t, nx, ny, crs, archivo):
    """Eta (punto 32): vías (archivo «vias.json») o ríos («rios.json») de OpenStreetMap que bajó el mapa con referencias, en coordenadas de celda."""
    try:
        from pyproj import Transformer
        ds = [d for d in sorted((Path(estado.carpeta) / "datos_descargados").glob("osm_*"), reverse=True) if (d / archivo).exists()]
        if not ds:
            return []
        el = json.loads((ds[0] / archivo).read_text(encoding="utf-8")).get("elements", [])
        tf = Transformer.from_crs("EPSG:4326", str(crs), always_xy=True); x0, y0 = t.c, t.f; dx, dy = t.a, t.e; out = []
        for e in el:
            g = e.get("geometry") or []
            if len(g) < 2:
                continue
            xs, ys = tf.transform([p["lon"] for p in g], [p["lat"] for p in g])
            ij = [[round((x - x0) / dx - 0.5, 2), round((y - y0) / dy - 0.5, 2)] for x, y in zip(xs, ys)]
            if not any(-1 <= i <= nx and -1 <= j <= ny for i, j in ij):
                continue
            tg = e.get("tags") or {}
            out.append({"clase": tg.get("highway") or tg.get("waterway") or "", "nombre": tg.get("name", ""), "ij": ij})
        return out[:4000]
    except Exception:
        return []


def datos(estado, run):
    base = estado.gestor.base / run
    if not base.is_dir():
        raise ValueError("No existe esa corrida.")
    _, cfg = estado.cfg()
    z, meta = mapas._terreno(cfg, estado.carpeta)
    ny, nx = z.shape; t = meta["transform"]
    capas = {}; info = []
    for clave, nombre, titulo, unidad, nota in CAPAS:
        f = next(iter(base.rglob(nombre)), None)
        if not f:
            continue
        with rasterio.open(f) as s:
            a = s.read(1).astype(float)
            if s.nodata is not None:
                a[a == s.nodata] = np.nan
        if a.shape != z.shape:
            continue
        a[a < 0] = np.nan
        vmax = float(np.nanmax(a)) if np.isfinite(a).any() else 0.0
        capas[clave] = _lista(a, 4)
        info.append({"id": clave, "titulo": titulo, "unidad": unidad, "nota": nota, "max": vmax,
                     "celdas_con_valor": int((np.isfinite(a) & (a > 0)).sum())})
    if not capas:
        raise ValueError("Esa corrida no tiene rásteres de resultados (¿terminó bien?).")
    return {"corrida": run, "ny": int(ny), "nx": int(nx), "dx_m": abs(float(t.a)), "origen": [float(t.c), float(t.f)], "crs": str(meta["crs"]),
            "z": _lista(z, 3), "z_min": float(np.nanmin(z)), "z_max": float(np.nanmax(z)), "capas": capas, "capas_info": info,
            "sintetico": estado.datos.get("tipo") == "sintetico", "escenario": (json.loads((base / "entrada.json").read_text(encoding="utf-8")).get("escenario") if (base / "entrada.json").exists() else None), "proyecto": estado.datos.get("nombre", ""),
            "rios": _rios(estado, t, nx, ny, meta["crs"]), "vias": _osm_lineas(estado, t, nx, ny, meta["crs"], "vias.json"), "rios_osm": _osm_lineas(estado, t, nx, ny, meta["crs"], "rios.json"),
            "aviso": ("Evento observado" if (cfg.get("evento_observado") and run.endswith("_real")) else ("Diseño IDF con cambio climático (CMIP6 SSP5-8.5)" if "_cc_" in run else "Diseño IDF histórica")) + " · no calibrado ni validado · el calado es el máximo del modelo, no una huella de inundación observada."}


def capa(estado, run, nombre="hmax"):
    """Solo UNA capa de una corrida (para dibujar «fantasmas» de otros escenarios sobre el visor). Misma malla que datos()."""
    base = estado.gestor.base / run
    if not base.is_dir():
        raise ValueError("No existe esa corrida.")
    clave = {c[0]: c for c in CAPAS}.get(nombre)
    if not clave:
        raise ValueError("Capa desconocida.")
    f = next(iter(base.rglob(clave[1])), None)
    if not f:
        raise ValueError("Esa corrida no tiene esa capa.")
    with rasterio.open(f) as s:
        a = s.read(1).astype(float)
        if s.nodata is not None:
            a[a == s.nodata] = np.nan
    a[a < 0] = np.nan
    ent = {}
    try:
        import json
        ent = json.loads((base / "entrada.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"corrida": run, "capa": nombre, "ny": int(a.shape[0]), "nx": int(a.shape[1]), "v": _lista(a, 3), "max": float(np.nanmax(a)) if np.isfinite(a).any() else 0.0, "escenario": ent.get("escenario")}


def fotos(estado, run):
    """Evolución del calado de una corrida (evolucion_calado.npz que escribe el núcleo): tiempos, celdas que alguna vez se mojan
    y calado en mm de cada foto, más el volumen y el área mojada. Corridas anteriores a Gamma no lo tienen."""
    base = estado.gestor.base / run
    if not base.is_dir():
        raise ValueError("No existe esa corrida.")
    f = next(iter(base.rglob("evolucion_calado.npz")), None)
    if not f:
        raise ValueError("Esta corrida no guardó la evolución en el tiempo (se hizo con una versión anterior a Gamma). Vuelve a correrla.")
    with np.load(f) as d:
        t, idx, h, vol, area, forma = d["t_s"], d["idx"], d["h_mm"], d["volumen_m3"], d["area_mojada_m2"], d["shape"]
    return {"corrida": run, "ny": int(forma[0]), "nx": int(forma[1]), "t_s": [round(float(x), 1) for x in t], "idx": idx.tolist(),
            "h_mm": h.tolist(), "volumen_m3": [round(float(x), 1) for x in vol], "area_mojada_m2": [round(float(x), 1) for x in area],
            "nota": "Calado del modelo en cada instante guardado (cada pocos minutos simulados); no es una observación."}


def solo_terreno(estado):
    """Terreno 3D del MDT registrado, sin capas de resultados (antes de cualquier corrida)."""
    _, cfg = estado.cfg()
    if not cfg.get("dem") or not cfg.get("aoi"):
        raise ValueError("El proyecto aún no tiene MDT registrado (módulo 5 · Terreno).")
    z, meta = mapas._terreno(cfg, estado.carpeta)
    ny, nx = z.shape; t = meta["transform"]
    return {"corrida": "terreno", "ny": int(ny), "nx": int(nx), "dx_m": abs(float(t.a)), "origen": [float(t.c), float(t.f)], "crs": str(meta["crs"]),
            "z": _lista(z, 3), "z_min": float(np.nanmin(z)), "z_max": float(np.nanmax(z)), "capas": {}, "capas_info": [],
            "sintetico": estado.datos.get("tipo") == "sintetico", "escenario": None, "proyecto": estado.datos.get("nombre", ""), "solo_terreno": True, "rios": _rios(estado, t, nx, ny, meta["crs"]), "aviso": "Terreno del proyecto (sin corrida)."}
