# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Importar un MDT/DSM de dron (GeoTIFF) a un proyecto: inspección de calidad y registro. El ráster NO se copia ni se modifica (puede pesar gigabytes);
el proyecto lo referencia por ruta absoluta y hash. El tipo (MDT/DSM) y el datum los declara la persona: aquí no se adivinan."""
import json, math
from datetime import datetime
from pathlib import Path
import numpy as np
import rasterio

from .ui import proyecto as P

CELDAS_MAX = 250_000                                  # mismo tope que la interfaz usa para una corrida


class TerrenoError(ValueError):
    pass


def inspeccionar(ruta):
    p = Path(ruta)
    if not p.is_file():
        raise TerrenoError("No existe el archivo. Indica la ruta completa a un GeoTIFF.")
    try:
        s = rasterio.open(p)
    except Exception as e:
        raise TerrenoError(f"No se pudo abrir como ráster: {str(e)[:160]}") from e
    with s:
        if s.crs is None:
            raise TerrenoError("El ráster no tiene CRS. Asigna uno (p. ej. EPSG:32717) en QGIS antes de importarlo.")
        epsg = s.crs.to_epsg()
        avisos = []
        if s.crs.is_geographic:
            avisos.append("El CRS es geográfico (grados): el modelo necesita metros. Reproyecta a UTM (p. ej. EPSG:32717 para Ecuador continental).")
        if s.count > 1:
            avisos.append(f"Tiene {s.count} bandas; se usará la banda 1.")
        res = abs(s.res[0])
        if res < 0.05 and not s.crs.is_geographic:
            avisos.append("Resolución muy fina (< 5 cm): se remuestreará a la resolución del modelo.")
        paso = max(1, int(math.sqrt(s.width * s.height / 1_000_000)))                     # estadísticas por muestreo: no se lee todo el ráster
        a = s.read(1, out_shape=(max(1, s.height // paso), max(1, s.width // paso)), resampling=rasterio.enums.Resampling.nearest, masked=True)
        z = np.ma.filled(a.astype(float), np.nan)
        ok = np.isfinite(z) & (z > -1e3) & (z < 1e4)
        v = z[ok]
        if v.size < 100:
            raise TerrenoError("El ráster no tiene suficientes celdas con elevación válida.")
        pct = float(ok.mean() * 100)
        if pct < 70:
            avisos.append(f"Solo {pct:.0f} % de celdas válidas: hay muchos huecos/NoData.")
        rango = (float(np.percentile(v, 0.5)), float(np.percentile(v, 99.5)))
        if rango[1] - rango[0] > 3000:
            avisos.append("Rango de elevación inusual (> 3 000 m): ¿unidades en cm/mm o valores centinela?")
        b = s.bounds
        return {"archivo": str(p), "tamano_mb": round(p.stat().st_size / 1e6, 1), "crs": f"EPSG:{epsg}" if epsg else s.crs.to_string(), "geografico": bool(s.crs.is_geographic),
                "res_m": res, "ancho_px": s.width, "alto_px": s.height, "extension": {"x0": b.left, "x1": b.right, "y0": b.bottom, "y1": b.top},
                "ancho_m": (b.right - b.left), "alto_m": (b.top - b.bottom), "nodata": s.nodata, "dtype": s.dtypes[0], "validas_pct": round(pct, 1),
                "z_min": float(v.min()), "z_max": float(v.max()), "z_p05_p995": [round(rango[0], 2), round(rango[1], 2)],
                "avisos": avisos, "apto": not s.crs.is_geographic}


def _sitio_en_crs(estado):
    """(x, y) del sitio del proyecto (lon/lat de `ubicacion`) en el CRS del proyecto, o None si el proyecto no declara un punto."""
    import re
    from rasterio.warp import transform
    m = re.search(r"lon\s*(-?\d+(?:\.\d+)?)\D+lat\s*(-?\d+(?:\.\d+)?)", str(estado.datos.get("ubicacion", "")))
    if not m:
        return None
    x, y = transform("EPSG:4326", estado.datos["crs"], [float(m.group(1))], [float(m.group(2))])
    return float(x[0]), float(y[0])


def _bbox_en(crs_origen, e, crs_destino):
    from rasterio.warp import transform_bounds
    x0, y0, x1, y1 = transform_bounds(crs_origen, crs_destino, e["x0"], e["y0"], e["x1"], e["y1"], densify_pts=21)
    return [x0, x1, y0, y1]


def _area(b):
    return max(0.0, b[1] - b[0]) * max(0.0, b[3] - b[2])


def _inter(a, b):
    return [max(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3])]


def coincidencia(ins, estado):
    """¿El MDT subido cae en la zona de trabajo? Compara, en el CRS del proyecto, la extensión del ráster con (1) el sitio del proyecto, (2) el área de estudio (AOI) y (3) el terreno regional de Earth Engine
    (Copernicus GLO-30 ya descargado). No modifica nada. Veredicto: coincide / parcial / no coincide, con la distancia y pistas de causa (CRS, zona UTM, hemisferio)."""
    crs = estado.datos["crs"]; e = _bbox_en(ins["crs"], ins["extension"], crs); sitio = _sitio_en_crs(estado); out = {"crs_proyecto": crs, "mdt": e, "sitio": list(sitio) if sitio else None, "pistas": []}
    carpeta = Path(estado.carpeta)
    try:
        cfg = json.loads((carpeta / estado.datos["config_climanet"]).read_text(encoding="utf-8")); aoi = cfg.get("aoi")
    except Exception:
        aoi = None
    out["aoi"] = [float(v) for v in aoi] if aoi else None
    gee = None
    for tif in sorted(list(carpeta.glob("datos_descargados/*/mdt/*.tif")) + list(carpeta.glob("datos_descargados/mdt_*/*.tif")), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            with rasterio.open(tif) as s:
                gee = _bbox_en(s.crs, {"x0": s.bounds.left, "x1": s.bounds.right, "y0": s.bounds.bottom, "y1": s.bounds.top}, crs); out["gee_archivo"] = tif.name
            break
        except Exception:
            continue
    out["gee"] = gee
    if sitio:
        dx = max(e[0] - sitio[0], 0, sitio[0] - e[1]); dy = max(e[2] - sitio[1], 0, sitio[1] - e[3]); out["contiene_sitio"] = bool(dx == 0 and dy == 0); out["distancia_al_sitio_km"] = round(math.hypot(dx, dy) / 1000, 2)
    else:
        out["contiene_sitio"] = None; out["distancia_al_sitio_km"] = None
    ref = out["aoi"] or None
    out["cobertura_aoi_pct"] = round(100 * _area(_inter(e, ref)) / _area(ref), 1) if ref and _area(ref) > 0 else None
    out["mdt_dentro_gee_pct"] = round(100 * _area(_inter(e, gee)) / _area(e), 1) if gee and _area(e) > 0 else None
    try:                                                                                   # C16: ¿el MDT cubre la cuenca activa?
        from .cuenca import extension_activa
        ext = extension_activa(carpeta, crs, margen_m=0.0)
        if ext:
            x0, y0, x1, y1 = ext["xy"]; cb = (x0, x1, y0, y1)
            out["cuenca_dentro_mdt_pct"] = round(100 * _area(_inter(cb, e)) / _area(cb), 1) if _area(cb) > 0 else None
            if out["cuenca_dentro_mdt_pct"] is not None and out["cuenca_dentro_mdt_pct"] < 100:
                out["pistas"].append(f"El MDT cubre solo el {out['cuenca_dentro_mdt_pct']:g} % del recuadro de la cuenca activa.")
    except Exception:
        pass
    if ins["crs"] != crs:
        out["pistas"].append(f"El CRS del MDT ({ins['crs']}) difiere del proyecto ({crs}): para esta comparación se reproyectó la extensión; para modelar hay que reproyectar el ráster.")
    if ins.get("geografico"):
        out["pistas"].append("El MDT está en grados (CRS geográfico): reproyecta a UTM en metros.")
    ok_sitio = out["contiene_sitio"]; cob = out["cobertura_aoi_pct"]
    if ok_sitio is None:
        out["veredicto"] = "sin_sitio"; out["mensaje"] = "El proyecto no declara un punto de sitio; no se puede comprobar la coincidencia con la zona de trabajo."
    elif ok_sitio and (cob is None or cob >= 95):
        out["veredicto"] = "coincide"; out["mensaje"] = "El MDT cubre el sitio del proyecto" + (f" y el {cob:.0f} % del área de estudio actual." if cob is not None else ".")
    elif ok_sitio or (cob or 0) > 0:
        out["veredicto"] = "parcial"; out["mensaje"] = "El MDT cubre el sitio solo en parte" + (f" ({cob:.0f} % del área de estudio actual)." if cob is not None else ".") + " Al registrar, el área de estudio se centrará en el sitio y se recortará al ráster."
    else:
        out["veredicto"] = "no_coincide"; d = out["distancia_al_sitio_km"]
        out["mensaje"] = f"El MDT NO cubre la zona de trabajo: queda a {d:g} km del sitio."
        if d is not None and d > 100:
            out["pistas"].append("Más de 100 km: revisa la zona UTM (en Ecuador 17S = EPSG:32717; 18S = EPSG:32718), el hemisferio sur (falso norte 10 000 000 m) y que X/Y no estén invertidos.")
        elif d is not None:
            out["pistas"].append("Revisa el datum horizontal (PSAD56/SIRGAS/WGS84 difieren en decenas a cientos de metros) y la georreferenciación del dron.")
    out["base_gee"] = ("Se superpone al terreno regional de Earth Engine (Copernicus GLO-30)" if (out["mdt_dentro_gee_pct"] or 0) > 0 else "No se superpone al terreno regional de Earth Engine descargado") \
        + (f": {out['mdt_dentro_gee_pct']:g} % del MDT cae dentro de su extensión." if out["mdt_dentro_gee_pct"] is not None else ". No hay terreno regional descargado para comparar.")
    return out


def aoi_sugerida(ins, res_modelo, centro=None, lado_m=None):
    """Caja de estudio centrada, limitada al tope de celdas del modelo. Devuelve [x0, x1, y0, y1]."""
    e = ins["extension"]; lado_max = math.sqrt(CELDAS_MAX) * res_modelo
    lado = min(lado_m or 600.0, lado_max, ins["ancho_m"], ins["alto_m"])
    cx, cy = centro or ((e["x0"] + e["x1"]) / 2, (e["y0"] + e["y1"]) / 2)
    return [round(cx - lado / 2, 1), round(cx + lado / 2, 1), round(cy - lado / 2, 1), round(cy + lado / 2, 1)]


def aoi_en_extension(aoi, e):
    return len(aoi) == 4 and e["x0"] <= aoi[0] < aoi[1] <= e["x1"] and e["y0"] <= aoi[2] < aoi[3] <= e["y1"]


def _ajustar(aoi, e):
    """Desplaza (sin cambiar su tamaño) una caja sugerida para que quede dentro del ráster cuando el sitio está cerca de un borde."""
    w, h = aoi[1] - aoi[0], aoi[3] - aoi[2]; x0 = min(max(aoi[0], e["x0"]), e["x1"] - w); y0 = min(max(aoi[2], e["y0"]), e["y1"] - h)
    return [round(x0, 1), round(x0 + w, 1), round(y0, 1), round(y0 + h, 1)]


def filtrar_picos(ruta, umbral_m=3.0, ventana=5, destino=None):
    """Omega O2 · Filtro DECLARADO de picos (edificios, árboles o ruido que sobresalen en un DSM): una celda que supera la mediana de su ventana
    (impar, en celdas) en más de `umbral_m` se reemplaza por esa mediana. Escribe un GeoTIFF NUEVO (el original no se toca) y un informe.
    No es un MDT de suelo desnudo: es una corrección declarada para quitar obstáculos puntuales."""
    import json as _j
    import rasterio
    from scipy.ndimage import median_filter
    umbral_m, ventana = float(umbral_m), int(ventana)
    if not 0.5 <= umbral_m <= 50 or ventana < 3 or ventana % 2 == 0 or ventana > 31:
        raise TerrenoError("Filtro de picos: umbral entre 0,5 y 50 m y ventana impar entre 3 y 31 celdas.")
    p = Path(ruta)
    with rasterio.open(p) as s:
        a = s.read(1).astype("float64"); nd = s.nodata; meta = s.profile
    v = np.isfinite(a) & ((a != nd) if nd is not None else True)
    rel = np.where(v, a, np.nanmedian(a[v]))
    med = median_filter(rel, size=ventana, mode="nearest")
    pico = v & (a - med > umbral_m)
    b = np.where(pico, med, a)
    out = Path(destino) if destino else p.with_name(p.stem + f"_sinpicos_u{umbral_m:g}m_v{ventana}.tif")
    if out.exists():
        raise TerrenoError(f"{out.name} ya existe; no se sobrescribe.")
    meta.update(dtype="float32")
    with rasterio.open(out, "w", **meta) as d:
        d.write(np.where(v, b, nd if nd is not None else np.nan).astype("float32"), 1)
    dz = (a - b)[pico]
    inf = {"origen": str(p), "salida": str(out), "umbral_m": umbral_m, "ventana_celdas": ventana, "celdas_corregidas": int(pico.sum()), "pct_celdas": round(100 * float(pico.sum()) / max(int(v.sum()), 1), 3),
           "descenso_max_m": round(float(dz.max()), 2) if dz.size else 0.0, "descenso_medio_m": round(float(dz.mean()), 2) if dz.size else 0.0,
           "nota": "Corrección DECLARADA: se reemplazan por la mediana local las celdas que sobresalen más que el umbral. Quita obstáculos puntuales; no convierte un DSM en suelo desnudo."}
    out.with_suffix(".json").write_text(_j.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
    return inf


def rios_merge(ruta_mdt, rios, destino, area_min_km2=10.0, tol_m=150.0, sigma=1.5):
    """Omega O9 · Ríos merge MDT + guía (HydroSHEDS): ruta de máxima acumulación D8 del MDT entre los extremos de cada tramo, con costo
    (1/acumulación^0,6)·(1 + (d_guía/(tol/2))²) para no saltar a otro cauce; suavizado gaussiano. Escribe un GeoPackage nuevo e informa
    cuánto se movió cada tramo. Usar el MDT de suelo desnudo SIN quemar (la quema se hace después sobre estas líneas)."""
    import json as _j
    import geopandas as gpd
    from shapely.geometry import LineString, box
    from shapely.ops import linemerge
    from rasterio.features import rasterize
    from scipy.ndimage import distance_transform_edt, gaussian_filter1d
    from scipy.spatial import cKDTree
    from skimage.graph import route_through_array
    from skimage.morphology import reconstruction
    with rasterio.open(ruta_mdt) as s:
        dem = s.read(1).astype("float64"); nd = s.nodata; tr = s.transform; crs = s.crs; b = s.bounds
    v = np.isfinite(dem) & ((dem != nd) if nd is not None else True); dem = np.where(v, dem, np.nanmedian(dem[v])); ny, nx = dem.shape; res = abs(tr.a)
    seed = dem.copy(); seed[1:-1, 1:-1] = dem.max(); filled = reconstruction(seed, dem, method="erosion")
    zf = (filled + np.arange(ny * nx).reshape(ny, nx) * 1e-7).ravel(); order = np.argsort(-zf); acc = np.ones(ny * nx)
    dr = np.array([-1, -1, -1, 0, 0, 1, 1, 1]); dc = np.array([-1, 0, 1, -1, 1, -1, 0, 1])
    for k in order:
        r, c = divmod(int(k), nx); best, bz = -1, zf[k]
        for a_, b_ in zip(dr, dc):
            rr, cc = r + a_, c + b_
            if 0 <= rr < ny and 0 <= cc < nx and zf[rr * nx + cc] < bz: bz, best = zf[rr * nx + cc], rr * nx + cc
        if best >= 0: acc[best] += acc[k]
    acc = acc.reshape(ny, nx)
    g = gpd.read_file(rios).to_crs(crs)
    if "UPLAND_SKM" in g: g = g[g["UPLAND_SKM"] >= float(area_min_km2)]
    g = g[g.intersects(box(b.left, b.bottom, b.right, b.top))]; g["geometry"] = g.intersection(box(b.left + res, b.bottom + res, b.right - res, b.top - res))
    rc = lambda x, y: (int((y - tr.f) / tr.e), int((x - tr.c) / tr.a)); xy = lambda r, c: (tr.c + (c + 0.5) * tr.a, tr.f + (r + 0.5) * tr.e)
    out, info = [], []
    for _, fila in g.iterrows():
        geom = fila.geometry; geom = linemerge(geom) if geom.geom_type == "MultiLineString" else geom
        for ln in getattr(geom, "geoms", [geom]):
            if ln.geom_type != "LineString" or ln.length < 3 * res: continue
            (r0, c0), (r1, c1) = rc(*ln.coords[0]), rc(*ln.coords[-1])
            if not (0 <= r0 < ny and 0 <= c0 < nx and 0 <= r1 < ny and 0 <= c1 < nx): continue
            mk = rasterize([(ln, 1)], out_shape=(ny, nx), transform=tr, all_touched=True, fill=0, dtype="uint8").astype(bool)
            dg = distance_transform_edt(~mk) * res; cost = (1.0 / np.maximum(acc, 1.0) ** 0.6) * (1.0 + (dg / (tol_m / 2)) ** 2)
            path, _ = route_through_array(cost, (r0, c0), (r1, c1), fully_connected=True, geometric=True)
            p = np.array([xy(r, c) for r, c in path])
            if len(p) > 8: p[:, 0] = gaussian_filter1d(p[:, 0], sigma, mode="nearest"); p[:, 1] = gaussian_filter1d(p[:, 1], sigma, mode="nearest")
            p = p[np.r_[True, np.any(np.diff(p, axis=0) != 0, axis=1)]]
            if len(p) < 2: continue
            d, _ = cKDTree(np.array(ln.coords)).query(p)
            out.append({"UPLAND_SKM": float(fila.get("UPLAND_SKM", 0)), "REACH_ID": int(fila.get("REACH_ID", 0)), "geometry": LineString(p)})
            info.append({"reach_id": int(fila.get("REACH_ID", 0)), "celdas": len(path), "dist_media_guia_m": round(float(d.mean()), 1), "dist_max_guia_m": round(float(d.max()), 1)})
    if not out:
        raise TerrenoError("No se pudo trazar ningún río sobre el MDT.")
    destino = Path(destino)
    if destino.exists():
        raise TerrenoError(f"{destino.name} ya existe; no se sobrescribe.")
    gpd.GeoDataFrame(out, crs=crs).to_file(destino, driver="GPKG")
    inf = {"mdt": str(ruta_mdt), "guia": str(rios), "salida": str(destino), "tramos": len(out), "tol_m": tol_m, "tramos_info": info,
           "nota": "Ríos merge: estructura de la guía (HydroSHEDS) y posición del talweg del MDT (ruta de máxima acumulación D8), suavizados. No es una medición del cauce."}
    destino.with_suffix(".json").write_text(_j.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
    return inf


def quemar_rios(ruta, rios, profundidad_m=2.0, ancho_celdas=1, area_min_km2=10.0, destino=None):
    """Omega O7 · Graba una red de ríos (líneas) en el MDT con profundidad DECLARADA: en cada celda que cruza la línea (ensanchada a `ancho_celdas`)
    z = mínimo de su ventana 3×3 − profundidad. Así el cauce queda bajo su entorno aunque la línea (p. ej. HydroSHEDS, ~500 m) no caiga en el fondo exacto del valle.
    Escribe un GeoTIFF NUEVO y un informe; no inventa geometría: solo usa las líneas dadas."""
    import json as _j
    import geopandas as gpd
    from rasterio import features
    from scipy.ndimage import minimum_filter, binary_dilation
    profundidad_m, ancho_celdas = float(profundidad_m), int(ancho_celdas)
    if not 0.2 <= profundidad_m <= 10 or not 1 <= ancho_celdas <= 5:
        raise TerrenoError("Quemar ríos: profundidad entre 0,2 y 10 m y ancho entre 1 y 5 celdas.")
    p = Path(ruta)
    with rasterio.open(p) as s:
        a = s.read(1).astype("float64"); nd = s.nodata; meta = s.profile; T = s.transform; crs = s.crs
    v = np.isfinite(a) & ((a != nd) if nd is not None else True)
    g = gpd.read_file(rios).to_crs(crs)
    if "UPLAND_SKM" in g:
        g = g[g["UPLAND_SKM"] >= float(area_min_km2)]
    if not len(g):
        raise TerrenoError("No hay tramos de río para quemar en ese terreno.")
    m = features.rasterize([(geom, 1) for geom in g.geometry], out_shape=a.shape, transform=T, all_touched=True).astype(bool) & v
    if ancho_celdas > 1:
        m = binary_dilation(m, iterations=ancho_celdas - 1) & v
    zmin = minimum_filter(np.where(v, a, np.inf), size=3, mode="nearest")
    b = np.where(m, zmin - profundidad_m, a)
    # O7b · descenso forzado: cada tramo se recorre en el sentido de la línea (aguas arriba → abajo), de menor a mayor área aportante,
    # y cada celda queda al menos 1 mm bajo la anterior: cauce continuo hasta el borde, sin pozas en las confluencias.
    inv = ~T; orden = g.sort_values("UPLAND_SKM").geometry if "UPLAND_SKM" in g else g.geometry; forzadas = 0
    for geom in orden:
        for l in getattr(geom, "geoms", [geom]):
            if l.geom_type != "LineString" or l.length <= 0:
                continue
            n = max(2, int(l.length / (abs(T.a) / 2)) + 1); prev = None; z_ant = None
            for k in range(n):
                pt = l.interpolate(k / (n - 1), normalized=True); cc, rr = inv * (pt.x, pt.y); rr, cc = int(np.floor(rr)), int(np.floor(cc))
                if not (0 <= rr < a.shape[0] and 0 <= cc < a.shape[1]) or not v[rr, cc] or (rr, cc) == prev:
                    continue
                if z_ant is not None and b[rr, cc] > z_ant - 0.001:
                    b[rr, cc] = z_ant - 0.001; forzadas += 1
                z_ant = b[rr, cc]; prev = (rr, cc)
    out = Path(destino) if destino else p.with_name(p.stem + f"_rios{profundidad_m:g}m_desc.tif")
    if out.exists():
        raise TerrenoError(f"{out.name} ya existe; no se sobrescribe.")
    meta.update(dtype="float32")
    with rasterio.open(out, "w", **meta) as d:
        d.write(np.where(v, b, nd if nd is not None else np.nan).astype("float32"), 1)
    inf = {"origen": str(p), "salida": str(out), "rios": str(rios), "profundidad_m": profundidad_m, "ancho_celdas": ancho_celdas, "area_min_km2": float(area_min_km2), "tramos": int(len(g)),
           "celdas_quemadas": int(m.sum()), "celdas_con_descenso_forzado": int(forzadas), "longitud_aprox_km": round(float(m.sum()) * abs(T.a) / 1000, 1),
           "nota": "Cauce grabado con profundidad DECLARADA (z = mínimo 3×3 − profundidad) y descenso forzado aguas abajo (≥ 1 mm por celda). Representa el cauce que el MDT de suelo desnudo suavizó; no es una batimetría medida."}
    out.with_suffix(".json").write_text(_j.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
    return inf


def alinear_aoi(aoi, e, res_raster, res_modelo):
    """G27 · Alinea el área de cálculo a la malla del ráster y la hace múltiplo de la celda del modelo: sin esto el promedio de bloque al cargar
    mezcla celdas vecinas (desfase de hasta media celda) y borra cauces de una celda; y un lado que no es múltiplo deja celdas de 30,03 m en vez de 30."""
    x0, x1, y0, y1 = [float(v) for v in aoi]; rr, rm = float(res_raster), float(res_modelo)
    x0 = e["x0"] + round((x0 - e["x0"]) / rr) * rr; y1 = e["y1"] - round((e["y1"] - y1) / rr) * rr
    nx, ny = int(round((x1 - aoi[0]) / rm)), int(round((y1 - aoi[2]) / rm))
    while x0 + nx * rm > e["x1"] + 1e-6: nx -= 1
    while y1 - ny * rm < e["y0"] - 1e-6: ny -= 1
    return [round(x0, 6), round(x0 + nx * rm, 6), round(y1 - ny * rm, 6), round(y1, 6)]


def _desalineada(aoi, e, rr, rm):
    off = lambda v, o: abs(((v - o) / rr) - round((v - o) / rr)) > 1e-3
    return off(aoi[0], e["x0"]) or off(aoi[3], e["y1"]) or abs((aoi[1] - aoi[0]) / rm - round((aoi[1] - aoi[0]) / rm)) > 1e-3 or abs((aoi[3] - aoi[2]) / rm - round((aoi[3] - aoi[2]) / rm)) > 1e-3


def registrar(estado, ruta, tipo_terreno, datum, res_modelo=10.0, aoi=None):
    """Declara el MDT del proyecto abierto. Deja copias .bak de los archivos que cambia (nada se pierde)."""
    if tipo_terreno not in ("MDT", "DSM", "desconocido"):
        raise TerrenoError("El tipo de terreno debe ser MDT, DSM o desconocido.")
    if not datum or len(str(datum).strip()) < 3:
        raise TerrenoError("Declara el datum vertical (puede ser «no verificado»).")
    ins = inspeccionar(ruta)
    if not ins["apto"]:
        raise TerrenoError("El CRS es geográfico; reproyecta a metros antes de registrarlo.")
    if ins["crs"] != estado.datos["crs"]:
        raise TerrenoError(f"El CRS del ráster ({ins['crs']}) no coincide con el del proyecto ({estado.datos['crs']}). Reproyecta el ráster o crea otro proyecto.")
    res_modelo = max(float(res_modelo), ins["res_m"])
    e = ins["extension"]; sitio = _sitio_en_crs(estado)
    centro = sitio if (sitio and e["x0"] <= sitio[0] <= e["x1"] and e["y0"] <= sitio[1] <= e["y1"]) else None              # por defecto el AOI se centra en el sitio de trabajo, no en el centro del ráster
    if aoi:
        aoi = [float(v) for v in aoi]                                                                   # AOI dado por la persona: se respeta o se rechaza, nunca se desplaza en silencio
    else:
        aoi = _ajustar(aoi_sugerida(ins, res_modelo, centro=centro, lado_m=min(10000.0, ins["ancho_m"], ins["alto_m"])), e)   # por defecto hasta 10 km (igual que el MDT de GEE), dentro del tope de celdas
        aoi = alinear_aoi(aoi, e, ins["res_m"], res_modelo)                                              # G27: sugerida → alineada a la malla del ráster
    if not (len(aoi) == 4 and e["x0"] <= aoi[0] < aoi[1] <= e["x1"] and e["y0"] <= aoi[2] < aoi[3] <= e["y1"]):
        raise TerrenoError("El área de estudio [x0, x1, y0, y1] debe quedar dentro del ráster.")
    celdas = ((aoi[1] - aoi[0]) / res_modelo) * ((aoi[3] - aoi[2]) / res_modelo)
    if celdas > CELDAS_MAX:
        raise TerrenoError(f"El área tendría {celdas:,.0f} celdas a {res_modelo:g} m; el tope de la interfaz es {CELDAS_MAX:,}. Reduce el área o aumenta la resolución.")
    carpeta = Path(estado.carpeta); marca = f"{datetime.now():%Y%m%d_%H%M%S}"
    cfg_path = carpeta / estado.datos["config_climanet"]
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    (cfg_path.parent / f"{cfg_path.name}.{marca}.bak").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    cfg["dem"] = str(Path(ruta).resolve()); cfg["res"] = res_modelo; cfg["aoi"] = aoi
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    datos = json.loads(json.dumps(estado.datos))
    datos["tipo_terreno"] = tipo_terreno; datos["datum_vertical"] = str(datum).strip()
    nota = f"MDT importado {marca}: {Path(ruta).name} ({tipo_terreno}, {ins['res_m']:g} m, {ins['crs']})"
    if _desalineada(aoi, e, ins["res_m"], res_modelo):
        nota += f" · AVISO: el área dada no está alineada a la malla del ráster o su lado no es múltiplo de {res_modelo:g} m; al cargar se promedian celdas vecinas y se pueden borrar cauces de una celda. Alineada sería {alinear_aoi(aoi, e, ins['res_m'], res_modelo)}."
    if isinstance(datos.get("procedencia"), dict):
        datos["procedencia"]["terreno_importado"] = {"archivo": str(Path(ruta).resolve()), "sha256": P.sha256(Path(ruta)), "fecha": datetime.now().isoformat(timespec="seconds"), "nota": nota}
    P.guardar(datos, carpeta, sobrescribir=True)                    # guardar() deja su propio .bak
    estado.abrir(str(carpeta))
    prev = carpeta / "registro" / "terreno_preview.png"
    if prev.exists():
        prev.rename(prev.with_name(f"terreno_preview.{marca}.png"))
    return {"inspeccion": ins, "aoi": aoi, "res_modelo_m": res_modelo, "celdas_modelo": int(celdas), "tipo_terreno": tipo_terreno, "nota": nota}


def sugerencia(ins, tipo_terreno=None):
    """Epsilon E1.5: qué celda, área y solver conviene con este MDT (tope CELDAS_MAX) y qué revisar antes de usarlo."""
    r = float(ins["res_m"]); filas = []
    for celda in sorted({max(r, 1.0), 2.0, 5.0, 10.0, 30.0}):
        if celda < r:
            continue
        lado = math.sqrt(CELDAS_MAX) * celda
        filas.append({"celda_m": celda, "area_max_km2": round(lado * lado / 1e6, 2), "lado_max_m": round(lado)})
    rec = []
    if r <= 2.0:
        rec.append(f"MDT fino ({r:g} m): para áreas mayores a {math.sqrt(CELDAS_MAX) * r / 1000:.1f} × {math.sqrt(CELDAS_MAX) * r / 1000:.1f} km usa el solver subgrid "
                   f"(celda de cálculo 5–10 m, resolución fina {max(r, 1.0):g} m): conserva cauces y bordos sin multiplicar el costo.")
    rec.append("Si el área es un tramo dentro de una cuenca mayor, el agua de aguas arriba no entra sola: agrega un hidrograma de entrada (entradas_hidrograma) en el borde aguas arriba.")
    avisos = ["Un DSM (dron) incluye árboles y casas: el agua choca con ellos como si fueran muros. Mejor un MDT de suelo (filtrado).",
              "Los puentes aparecen como diques que tapan el río: «ábrelos» en el ráster antes de importarlo.",
              "Datum vertical: un dron suele dar alturas elipsoidales y GLO-30 usa EGM2008; pueden diferir decenas de metros. Verifica con un punto GPS.",
              "El dron o el LiDAR no ven el fondo del río: el cauce sale «lleno» y su capacidad se subestima; complétalo con secciones topográficas si puedes."]
    if str(tipo_terreno or "").upper() == "DSM":
        avisos.insert(0, "Declaraste DSM: revisa especialmente árboles, casas y puentes.")
    return {"res_nativa_m": r, "opciones": filas, "recomendaciones": rec, "avisos": avisos, "tope_celdas": CELDAS_MAX}
