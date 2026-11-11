# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Cuenca de estudio de hidro: tres salidas, todas guardadas en  <proyecto>/cuenca/<sello>_<origen>/  (nada se sobrescribe).

  1. cargar_shape   la persona entrega el polígono (shp, gpkg, geojson): se valida y se normaliza.
  2. delinear_mdt   delineación automática desde el MDT del proyecto (relleno de depresiones por inundación con prioridad,
                    direcciones D8, acumulación) hacia el punto de salida elegido; red de ríos opcional «quemada» en el MDT.
  3. malla_chirps   malla de cálculo con las celdas de CHIRPS (0,05° ≈ 5,5 km). NO es una cuenca hidrográfica.

Cada resultado lleva su rótulo de estado: «cargada por la persona», «delineación automática SIN REVISAR» o «malla de cálculo».
Ningún parámetro se inventa: los de algoritmo (radio de ajuste, profundidad de quema) se declaran en resumen.json.
"""
import heapq
import json
import math
import time
from pathlib import Path

import threading

import numpy as np

_BLOQUEO_PNG = threading.Lock()            # matplotlib no es seguro entre hilos

CHIRPS_PASO = 0.05           # grados; los bordes de celda CHIRPS caen en múltiplos de 0,05°
ETQ = {"shape": "Cuenca cargada por la persona (polígono propio, sin editar)",
       "mdt": "Delineación automática desde el MDT · SIN REVISAR por la persona",
       "malla": "Malla de cálculo CHIRPS 0,05° · NO es una cuenca hidrográfica"}


class CuencaError(Exception):
    pass


def _gp():
    import geopandas as gpd
    return gpd


def _crs_utm(datos):
    return datos.get("crs") or "EPSG:32717"


def _carpeta_nueva(carpeta, origen):
    base = Path(carpeta) / "cuenca"
    base.mkdir(parents=True, exist_ok=True)
    for k in range(60):
        d = base / f"{time.strftime('%Y%m%d_%H%M%S')}{'' if k == 0 else f'_{k}'}_{origen}"
        try:
            d.mkdir(); return d
        except FileExistsError:
            time.sleep(0.05)
    raise CuencaError("no se pudo crear la carpeta de la cuenca")


def _escribir(carpeta, datos, gdf_utm, origen, extra=None, aviso=None):
    """Guarda capas (shp UTM + shp WGS84 + gpkg) y tabla (csv + xlsx), resumen.json y marca la salida como activa."""
    import pandas as pd
    d = _carpeta_nueva(carpeta, origen)
    gdf_utm = gdf_utm.copy(); gdf_utm["geometry"] = gdf_utm.geometry.make_valid()
    gw = gdf_utm.to_crs(4326)
    gdf_utm.to_file(d / "cuenca_utm.shp"); gw.to_file(d / "cuenca_wgs84.shp"); gdf_utm.to_file(d / "cuenca.gpkg", layer="cuenca", driver="GPKG")
    area = float(gdf_utm.geometry.area.sum() / 1e6)
    cx = gw.geometry.unary_union.centroid
    resumen = {"origen": origen, "etiqueta": ETQ[origen], "area_km2": round(area, 3), "n_poligonos": int(len(gdf_utm)), "crs_utm": str(gdf_utm.crs),
               "centroide_lonlat": [round(cx.x, 5), round(cx.y, 5)], "creada": time.strftime("%Y-%m-%dT%H:%M:%S"), "avisos": list(aviso or []), **(extra or {})}
    tabla = pd.DataFrame([{k: v for k, v in resumen.items() if not isinstance(v, (list, dict))}])
    tabla.to_csv(d / "resumen.csv", index=False, encoding="utf-8-sig"); tabla.to_excel(d / "resumen.xlsx", index=False)
    (d / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    resumen["carpeta"] = str(d.relative_to(carpeta)).replace("\\", "/")
    act = Path(carpeta) / "cuenca" / "activa.json"
    # la delineación automática NO se activa sola (la persona debe aceptarla); la malla solo si no hay otra activa
    resumen["activa"] = origen == "shape" or (origen == "malla" and not act.exists())
    if not resumen["activa"]:
        return resumen
    act.write_text(json.dumps({"carpeta": resumen["carpeta"], "origen": origen, "etiqueta": resumen["etiqueta"], "area_km2": resumen["area_km2"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen


def _punto(datos):
    import re
    m = re.search(r"lon\s*(-?\d+(?:\.\d+)?)\D+lat\s*(-?\d+(?:\.\d+)?)", str(datos.get("ubicacion", "")))
    return (float(m.group(1)), float(m.group(2))) if m else None


# ------------------------------------------------------------------------------------------------ 1. shape propio
def cargar_shape(carpeta, datos, ruta, crs_si_falta=None):
    gpd = _gp()
    ruta = Path(ruta)
    if not ruta.exists():
        raise CuencaError(f"No existe el archivo: {ruta}")
    try:
        g = gpd.read_file(ruta)
    except Exception as e:
        raise CuencaError(f"No pude leer el archivo vectorial: {str(e)[:200]}")
    if g.empty:
        raise CuencaError("El archivo no contiene entidades.")
    if g.crs is None:
        if not crs_si_falta:
            raise CuencaError("El archivo no declara sistema de coordenadas (falta .prj). Indica el CRS (por ejemplo EPSG:32717 o EPSG:4326); no lo adivino.")
        g = g.set_crs(crs_si_falta)
    g = g[g.geometry.notna() & g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if g.empty:
        raise CuencaError("El archivo no tiene polígonos (¿son líneas o puntos?).")
    utm = _crs_utm(datos)
    g = g.to_crs(utm)
    union = g.geometry.make_valid().unary_union
    if union.is_empty:
        raise CuencaError("Los polígonos quedaron vacíos tras corregir su geometría.")
    gdf = gpd.GeoDataFrame({"id": [1], "origen": ["shape_propio"], "archivo": [ruta.name]}, geometry=[union], crs=utm)
    avisos = []
    area = union.area / 1e6
    if area < 0.01:
        avisos.append(f"Área muy pequeña ({area:.4f} km²): ¿unidades o CRS equivocados?")
    if area > 200000:
        avisos.append(f"Área enorme ({area:.0f} km²): revisa el CRS.")
    if len(g) > 1:
        avisos.append(f"El archivo tenía {len(g)} polígonos; se unieron en uno. Si son subcuencas separadas, cárgalas por separado.")
    p = _punto(datos); extra = {"archivo_origen": str(ruta), "sitio_en_cuenca": None}
    if p:
        import shapely.geometry as sg
        pt = gpd.GeoSeries([sg.Point(p)], crs=4326).to_crs(utm).iloc[0]
        dist = float(union.distance(pt)) / 1000
        extra["sitio_en_cuenca"] = bool(union.contains(pt)); extra["dist_sitio_a_cuenca_km"] = round(dist, 3)
        if dist > 5:
            avisos.append(f"El sitio del proyecto queda a {dist:.1f} km de esta cuenca: ¿es la cuenca de aporte correcta?")
    return _escribir(carpeta, datos, gdf, "shape", extra, avisos)


# ------------------------------------------------------------------------------------------------ 2. delineación desde el MDT
def _inundacion_prioridad(z, valido):
    """Relleno priority-flood con epsilon (Barnes et al., 2014) y luego D8 por pendiente sobre el MDT rellenado.
    Devuelve (orden de aguas abajo a aguas arriba, receptora) en índices planos del ráster con anillo; salidas con receptora -1."""
    h, w = z.shape
    W = w + 2
    zz = np.full((h + 2, W), np.inf); zz[1:-1, 1:-1] = np.where(valido, z, np.inf)
    v = np.zeros((h + 2, W), bool); v[1:-1, 1:-1] = valido
    borde = np.zeros_like(v)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                borde |= v & ~np.roll(np.roll(v, dy, 0), dx, 1)
    zl = zz.ravel().tolist(); vl = v.ravel().tolist()
    seen = bytearray(v.size); recv = [-1] * v.size
    pila = []
    for i in np.flatnonzero(borde.ravel()).tolist():
        seen[i] = 1; heapq.heappush(pila, (zl[i], i))
    offs = (-W - 1, -W, -W + 1, -1, 1, W - 1, W, W + 1)
    orden = []
    eps = 1e-4
    pop, push = heapq.heappop, heapq.heappush
    while pila:
        zc, i = pop(pila); orden.append(i)
        for o in offs:
            j = i + o
            if vl[j] and not seen[j]:
                seen[j] = 1; zj = zl[j]
                if zj <= zc:
                    zj = zc + eps; zl[j] = zj
                push(pila, (zj, j))
    # D8 sobre el MDT rellenado: receptora = vecina con mayor pendiente (caída / distancia; diagonal = √2·celda).
    zf = np.array(zl, dtype=np.float64).reshape(h + 2, W)
    mejor = np.zeros((h + 2, W)); rec = np.full((h + 2, W), -1, dtype=np.int64)
    idx = np.arange((h + 2) * W, dtype=np.int64).reshape(h + 2, W)
    for o, (dy, dx) in zip(offs, ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))):
        vec = np.roll(np.roll(zf, -dy, 0), -dx, 1)
        with np.errstate(invalid="ignore"):
            pend = (zf - vec) / (math.sqrt(2.0) if dy and dx else 1.0)
        pend = np.where(np.isfinite(pend), pend, -np.inf)
        m = pend > mejor
        mejor = np.where(m, pend, mejor); rec = np.where(m, idx + o, rec)
    rec[~v] = -1
    validos = np.flatnonzero(v.ravel())
    orden = validos[np.argsort(zf.ravel()[validos], kind="stable")].tolist()      # de aguas abajo a aguas arriba
    return orden, rec.ravel().tolist(), W, h, w


def delinear_mdt(carpeta, datos, lon, lat, mdt=None, snap_m=500.0, rios=None, quema_m=5.0, max_celdas=6_000_000, remuestrear=True):
    """Delinea la cuenca aguas arriba del punto (lon, lat) con el MDT del proyecto.
    snap_m: la salida se mueve a la celda de mayor acumulación dentro de ese radio (parámetro declarado). rios: shp/gpkg de líneas (opcional)
    que se «queman» restando quema_m metros a las celdas que cruzan (parámetro declarado); sin él NO se quema nada."""
    import rasterio
    from rasterio import features
    from rasterio.windows import Window
    gpd = _gp()
    carpeta = Path(carpeta)
    cfg = json.loads((carpeta / datos.get("config_climanet", "config_climanet.json")).read_text(encoding="utf-8"))
    ruta = Path(mdt) if mdt else carpeta / (cfg.get("dem") or "")
    if not cfg.get("dem") and not mdt:
        raise CuencaError("El proyecto no tiene MDT registrado. Descárgalo en el módulo 2 · Datos / GEE.")
    if not ruta.exists():
        raise CuencaError(f"No existe el MDT: {ruta}")
    utm = _crs_utm(datos)
    with rasterio.open(ruta) as src:
        if src.crs is None or not src.crs.is_projected:
            raise CuencaError("El MDT debe estar en un CRS proyectado (UTM). Reproyéctalo en el módulo Terreno.")
        f = 1
        if src.width * src.height > max_celdas:
            if not remuestrear:
                raise CuencaError(f"El MDT tiene {src.width * src.height / 1e6:.1f} millones de celdas (máximo {max_celdas / 1e6:.0f}).")
            f = math.ceil(math.sqrt(src.width * src.height / max_celdas))
        from rasterio.enums import Resampling
        z = src.read(1, masked=True, out_shape=(src.height // f, src.width // f), resampling=Resampling.average if f > 1 else Resampling.nearest).astype("float64")
        T = src.transform * src.transform.scale(src.width / z.shape[1], src.height / z.shape[0]); crs = src.crs; res = abs(T.a)
        valido = ~np.ma.getmaskarray(z) & np.isfinite(z.filled(np.nan)); zdat = z.filled(np.nan)
    import shapely.geometry as sg
    pt = gpd.GeoSeries([sg.Point(lon, lat)], crs=4326).to_crs(crs).iloc[0]
    col, row = ~T * (pt.x, pt.y); col, row = int(col), int(row)
    if not (0 <= row < zdat.shape[0] and 0 <= col < zdat.shape[1]) or not valido[row, col]:
        raise CuencaError("El punto de salida cae fuera del MDT o sobre una celda sin dato.")
    avisos = [f"MDT agregado por promedio a {res:.0f} m (factor {f}) para caber en memoria y tiempo; se declara." ] if f > 1 else []
    if rios:
        r = gpd.read_file(rios)
        if r.crs is None:
            raise CuencaError("La red de ríos no declara CRS.")
        r = r.to_crs(crs); r = r[r.geometry.notna()]
        m = features.rasterize([(g, 1) for g in r.geometry], out_shape=zdat.shape, transform=T, all_touched=True, dtype="uint8").astype(bool)
        zdat = np.where(m & valido, zdat - float(quema_m), zdat)
        avisos.append(f"Red de ríos «quemada»: {int(m.sum())} celdas bajadas {quema_m} m (parámetro declarado).")
    else:
        avisos.append("Sin red de ríos: el MDT no se modificó (no hay quema).")
    orden, recv, W, h, w = _inundacion_prioridad(zdat, valido)
    n = len(recv)
    acc = [0] * n
    for i in orden:
        acc[i] += 1
    for i in reversed(orden):
        r_ = recv[i]
        if r_ >= 0:
            acc[r_] += acc[i]
    accn = np.array(acc, dtype=np.int64).reshape(h + 2, W)[1:-1, 1:-1]
    rad = max(1, int(round(snap_m / res)))
    r0, r1, c0, c1 = max(0, row - rad), min(h, row + rad + 1), max(0, col - rad), min(w, col + rad + 1)
    yy, xx = np.mgrid[r0:r1, c0:c1]
    sub = np.where(valido[r0:r1, c0:c1] & ((yy - row) ** 2 + (xx - col) ** 2 <= rad * rad), accn[r0:r1, c0:c1], -1)
    k = int(np.argmax(sub)); rr, cc = divmod(k, sub.shape[1]); rr += r0; cc += c0
    salida = (rr + 1) * W + (cc + 1)
    dist_snap = math.hypot(rr - row, cc - col) * res
    en = bytearray(n); en[salida] = 1
    for i in orden:                                     # de aguas abajo a aguas arriba: la receptora siempre se procesa antes
        if recv[i] >= 0 and en[recv[i]]:
            en[i] = 1
    mascara = np.frombuffer(bytes(en), dtype=np.uint8).reshape(h + 2, W)[1:-1, 1:-1].astype("uint8")
    if mascara.sum() < 4:
        raise CuencaError("La cuenca resultante tiene menos de 4 celdas: el punto de salida está sobre una divisoria. Muévelo a un cauce.")
    geoms = [sg.shape(g) for g, vv in features.shapes(mascara, mask=mascara.astype(bool), transform=T) if vv == 1]
    from shapely.ops import unary_union
    cuenca = unary_union(geoms)
    toca_borde = bool(mascara[0, :].any() or mascara[-1, :].any() or mascara[:, 0].any() or mascara[:, -1].any())
    if toca_borde:
        avisos.append("La cuenca toca el borde del MDT: probablemente está RECORTADA. Descarga un MDT más amplio.")
    if dist_snap > 0:
        avisos.append(f"La salida se movió {dist_snap:.0f} m a la celda de mayor acumulación (radio declarado {snap_m:.0f} m).")
    area = float(mascara.sum()) * res * res / 1e6
    avisos.append("Delineación automática: revísala sobre la imagen y acéptala o corrige el punto de salida antes de usarla.")
    gdf = gpd.GeoDataFrame({"id": [1], "origen": ["mdt_d8"]}, geometry=[cuenca], crs=crs).to_crs(utm)
    sal = gpd.GeoSeries([sg.Point(*(T * (cc + 0.5, rr + 0.5)))], crs=crs).to_crs(4326).iloc[0]
    try:
        mdt_txt = str(ruta.resolve().relative_to(carpeta.resolve())).replace("\\", "/")
    except ValueError:
        mdt_txt = str(ruta)
    extra = {"mdt": mdt_txt, "resolucion_m": res, "salida_pedida_lonlat": [lon, lat],
             "salida_ajustada_lonlat": [round(sal.x, 6), round(sal.y, 6)], "snap_m": snap_m, "dist_snap_m": round(dist_snap, 1), "acumulacion_celdas": int(accn[rr, cc]),
             "area_acumulada_km2": round(int(accn[rr, cc]) * res * res / 1e6, 3), "toca_borde_mdt": toca_borde, "quema_m": float(quema_m) if rios else None,
             "metodo": "Relleno priority-flood con epsilon (Barnes et al. 2014) + D8 por pendiente (caída/distancia) sobre el MDT rellenado"}
    out = _escribir(carpeta, datos, gdf, "mdt", extra, avisos)
    try:                                                 # ráster de acumulación (km²) para revisar la red de drenaje
        d = Path(carpeta) / out["carpeta"]
        prof = {"driver": "GTiff", "height": h, "width": w, "count": 1, "dtype": "float32", "crs": crs, "transform": T, "nodata": -1, "compress": "deflate"}
        with rasterio.open(d / "acumulacion_km2.tif", "w", **prof) as dst:
            dst.write(np.where(valido, accn * res * res / 1e6, -1).astype("float32"), 1)
    except Exception as e:
        out["avisos"].append(f"No se pudo guardar el ráster de acumulación: {str(e)[:80]}")
    return out


# ------------------------------------------------------------------------------------------------ 3. malla de celdas CHIRPS
def malla_chirps(carpeta, datos, medio_km=None):
    """Celdas CHIRPS 0,05° que cubren la cuenca activa (si hay una), o el recuadro AOI de la configuración, o ±medio_km del sitio."""
    gpd = _gp()
    import shapely.geometry as sg
    carpeta = Path(carpeta); utm = _crs_utm(datos)
    ref = None; base = "sitio"
    act = carpeta / "cuenca" / "activa.json"
    if act.exists():
        a = json.loads(act.read_text(encoding="utf-8"))
        if a.get("origen") != "malla":
            ref = gpd.read_file(carpeta / a["carpeta"] / "cuenca.gpkg").to_crs(4326).geometry.unary_union; base = "cuenca activa"
    if ref is None:
        cfgp = carpeta / datos.get("config_climanet", "config_climanet.json")
        cfg = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
        if cfg.get("aoi") and not medio_km:
            x0, x1, y0, y1 = cfg["aoi"]; ref = gpd.GeoSeries([sg.box(x0, y0, x1, y1)], crs=utm).to_crs(4326).iloc[0]; base = "recuadro AOI del proyecto"
        else:
            p = _punto(datos)
            if not p:
                raise CuencaError("El proyecto no tiene sitio (lon/lat) ni cuenca activa.")
            km = float(medio_km or 20)
            ref = gpd.GeoSeries([sg.Point(p).buffer(1)], crs=4326).to_crs(utm).iloc[0].centroid.buffer(km * 1000, cap_style=3)
            ref = gpd.GeoSeries([ref], crs=utm).to_crs(4326).iloc[0]; base = f"±{km:g} km del sitio"
    x0, y0, x1, y1 = ref.bounds
    i0, i1 = math.floor(x0 / CHIRPS_PASO + 1e-9), math.ceil(x1 / CHIRPS_PASO - 1e-9)
    j0, j1 = math.floor(y0 / CHIRPS_PASO + 1e-9), math.ceil(y1 / CHIRPS_PASO - 1e-9)
    filas = []
    for i in range(i0, i1):
        for j in range(j0, j1):
            c = sg.box(i * CHIRPS_PASO, j * CHIRPS_PASO, (i + 1) * CHIRPS_PASO, (j + 1) * CHIRPS_PASO)
            if c.intersects(ref):
                filas.append({"id": f"c{i - i0:02d}_{j - j0:02d}", "lon_c": round((i + 0.5) * CHIRPS_PASO, 4), "lat_c": round((j + 0.5) * CHIRPS_PASO, 4), "frac_ref": float(c.intersection(ref).area / c.area), "geometry": c})
    if not filas:
        raise CuencaError("Ninguna celda CHIRPS intersecta la zona de referencia.")
    g = gpd.GeoDataFrame(filas, crs=4326)
    gu = g.to_crs(utm); g["area_km2"] = (gu.geometry.area / 1e6).round(3)
    avisos = [f"Celdas que intersectan la {base}. Es una malla de cálculo: no representa una cuenca hidrográfica ni sirve para calibrar contra un aforo.",
              f"CHIRPS 0,05° ≈ {0.05 * 111.32:.1f} km: los bordes de celda se alinean a múltiplos de 0,05° (convención de CHIRPS); verifica contra tu ráster si lo tienes."]
    extra = {"n_celdas": int(len(g)), "referencia": base, "paso_grados": CHIRPS_PASO}
    return _escribir(carpeta, datos, g.to_crs(utm), "malla", extra, avisos)


# ------------------------------------------------------------------------------------------------ estado
def estado(carpeta):
    carpeta = Path(carpeta); act = carpeta / "cuenca" / "activa.json"
    hist = []
    for d in sorted((carpeta / "cuenca").glob("*_*")) if (carpeta / "cuenca").exists() else []:
        rj = d / "resumen.json"
        if rj.exists():
            r = json.loads(rj.read_text(encoding="utf-8")); ch = r.get("contraste_hydrosheds") or {}
            ah = ch.get("area_hydrosheds_km2") if isinstance(ch, dict) else None
            dif = (r["area_km2"] / ah - 1) * 100 if ah else None                       # Eta (punto 5): diferencia con HydroSHEDS, visible antes de aceptar
            hist.append({"carpeta": d.name, "origen": r["origen"], "etiqueta": r["etiqueta"], "area_km2": r["area_km2"], "creada": r["creada"], "avisos": r["avisos"],
                         "area_hydrosheds_km2": ah, "dif_hydrosheds_pct": None if dif is None else round(dif, 1), "toca_borde_mdt": r.get("toca_borde_mdt")})
    return {"activa": json.loads(act.read_text(encoding="utf-8")) if act.exists() else None, "historial": hist[::-1]}


def activar(carpeta, nombre, persona=None):
    """Marca como activa una cuenca ya guardada (la persona acepta o vuelve a una anterior). No borra nada."""
    carpeta = Path(carpeta); d = carpeta / "cuenca" / nombre
    if not (d / "resumen.json").exists():
        raise CuencaError("Esa cuenca no existe en el proyecto.")
    r = json.loads((d / "resumen.json").read_text(encoding="utf-8"))
    etq = r["etiqueta"]
    if r["origen"] == "mdt":                                   # al activarla, la persona la acepta: se registra quién y cuándo
        etq = f"Delineación automática desde el MDT · ACEPTADA por {persona or 'la persona usuaria'} el {time.strftime('%Y-%m-%d %H:%M')}"
        r.setdefault("aceptaciones", []).append({"persona": persona or "", "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")})
        (d / "resumen.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    act = {"carpeta": f"cuenca/{nombre}", "origen": r["origen"], "etiqueta": etq, "area_km2": r["area_km2"]}
    (carpeta / "cuenca" / "activa.json").write_text(json.dumps(act, ensure_ascii=False, indent=2), encoding="utf-8")
    return act


def mapa_png(carpeta, nombre=None):
    """Vista rápida para revisar: cuenca sobre sombreado del MDT (si hay) y punto de salida. Devuelve bytes PNG."""
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    gpd = _gp()
    carpeta = Path(carpeta)
    if nombre is None:
        a = json.loads((carpeta / "cuenca" / "activa.json").read_text(encoding="utf-8")); d = carpeta / a["carpeta"]
    else:
        d = carpeta / "cuenca" / nombre
    r = json.loads((d / "resumen.json").read_text(encoding="utf-8"))
    g = gpd.read_file(d / "cuenca.gpkg")
    with _BLOQUEO_PNG:
        return _png(carpeta, d, r, g, plt)


def _png(carpeta, d, r, g, plt):
    import io
    gpd = _gp()
    fig, ax = plt.subplots(figsize=(6.4, 5.4), dpi=110)
    try:
        import rasterio
        cfg = json.loads((carpeta / "config_climanet.json").read_text(encoding="utf-8"))
        m = Path(r["mdt"]) if r.get("mdt") else Path(cfg["dem"])
        with rasterio.open(m if m.is_absolute() else carpeta / m) as s:
            fz = max(1, int(max(s.width, s.height) / 900))
            z = s.read(1, masked=True, out_shape=(s.height // fz, s.width // fz))
            ax.imshow(z, extent=(s.bounds.left, s.bounds.right, s.bounds.bottom, s.bounds.top), cmap="Greys", alpha=0.8)
    except Exception:
        pass
    try:
        rios = ultima_descarga(carpeta, "rios", "rios_hydrosheds.gpkg")
        if rios:
            x0, y0, x1, y1 = g.total_bounds; rr = gpd.read_file(rios).to_crs(g.crs).cx[x0:x1, y0:y1]
            rr.plot(ax=ax, color="#3a86ff", linewidth=(0.3 + rr["RIV_ORD"].rsub(9).clip(0, 6) * 0.35).tolist(), alpha=0.8)
    except Exception:
        pass
    g.boundary.plot(ax=ax, color="#0b66c3" if r["origen"] != "malla" else "#0b66c3", linewidth=1.6)
    if r["origen"] == "malla":
        g.plot(ax=ax, facecolor="none", edgecolor="#0b66c3", linewidth=0.8)
    if r.get("salida_ajustada_lonlat"):
        s = gpd.GeoSeries(gpd.points_from_xy([r["salida_ajustada_lonlat"][0]], [r["salida_ajustada_lonlat"][1]]), crs=4326).to_crs(g.crs)
        s.plot(ax=ax, color="#d62828", markersize=40, zorder=5)
    x0, y0, x1, y1 = g.total_bounds; mg = max(0.25 * max(x1 - x0, y1 - y0), 3000.0)
    ax.set_xlim(x0 - mg, x1 + mg); ax.set_ylim(y0 - mg, y1 + mg)
    ax.set_title(f"{r['etiqueta']}\n{r['area_km2']:.1f} km²", fontsize=9); ax.set_aspect("equal"); ax.tick_params(labelsize=7)
    b = io.BytesIO(); fig.tight_layout(); fig.savefig(b, format="png"); plt.close(fig)
    return b.getvalue()


# ------------------------------------------------------------------------------------------------ descargas de apoyo (Earth Engine) y tarea en segundo plano
def _ee():
    from . import gee_chirps as G
    from .descargas import DescargaError
    info, ee = G.iniciar()
    if not info.get("autenticado"):
        raise DescargaError("Earth Engine no está conectado en este equipo (módulo 2 · Datos / GEE). " + str(info.get("error"))[:120])
    return ee


def _caja(lon, lat, medio_km):
    dlat = medio_km / 110.57; dlon = medio_km / (111.32 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def fuente_mdt_cuenca(destino, p, progreso):
    """MDT AMPLIO para delinear cuencas grandes (Copernicus GLO-30 agregado a `escala_m`, por defecto 90 m). No reemplaza el MDT del proyecto."""
    import requests
    from .descargas import DescargaError, utm_epsg
    lon, lat = float(p["lon"]), float(p["lat"]); medio = float(p.get("medio_km", 60)); escala = float(p.get("escala_m", 90))
    if not (5 <= medio <= 150):
        raise DescargaError("medio_km debe estar entre 5 y 150 (lado de 10 a 300 km).")
    if not (30 <= escala <= 250):
        raise DescargaError("escala_m debe estar entre 30 y 250 m.")
    if (2 * medio * 1000 / escala) ** 2 > 9e6:
        raise DescargaError(f"Con {2 * medio:.0f} km de lado a {escala:.0f} m el ráster supera 9 millones de celdas: sube escala_m.")
    ee = _ee(); epsg = utm_epsg(lon, lat)
    region = ee.Geometry.Rectangle(_caja(lon, lat, medio))
    col = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("DEM")
    img = col.mosaic().setDefaultProjection(col.first().projection()).reduceResolution(ee.Reducer.mean(), maxPixels=1024).clip(region)
    progreso(0.2, f"pidiendo a Earth Engine un MDT de {2 * medio:.0f} km a {escala:.0f} m")
    try:
        url = img.getDownloadURL({"region": region, "scale": escala, "crs": f"EPSG:{epsg}", "format": "GEO_TIFF"})
    except Exception as e:
        raise DescargaError("Earth Engine rechazó la petición: " + str(e)[:200]) from e
    progreso(0.4, "descargando el MDT amplio")
    r = requests.get(url, timeout=90)
    if r.status_code != 200 or len(r.content) < 2000:
        raise DescargaError(f"Falló la descarga (HTTP {r.status_code}) Earth Engine dijo: " + (r.text or "")[:300].replace("\n", " ") + ". Si el área es muy grande (más de unos 200 km de lado a 90 m), baja la resolución o el tamaño.")
    c = r.content
    if c[:2] == b"PK":
        import io, zipfile
        z = zipfile.ZipFile(io.BytesIO(c)); c = z.read(next(n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))))
    f = destino / f"mdt_cuenca_glo30_{int(2 * medio)}km_{int(escala)}m_utm{epsg}.tif"; f.write_bytes(c)
    progreso(0.9, "MDT amplio guardado")
    return {"archivos": [f.name], "fuente": "Copernicus GLO-30 vía Earth Engine, agregado por promedio", "escala_m": escala, "medio_km": medio, "punto": [lon, lat],
            "nota": "Solo para delinear la cuenca. Es un DSM global (incluye vegetación); el MDT del proyecto no se reemplaza."}


def fuente_rios(destino, p, progreso):
    """Red de ríos HydroSHEDS (WWF/HydroSHEDS/v1/FreeFlowingRivers) en la caja indicada: shp WGS84 + UTM + gpkg + csv."""
    from .descargas import DescargaError, utm_epsg
    gpd = _gp()
    lon, lat = float(p["lon"]), float(p["lat"]); medio = float(p.get("medio_km", 60)); umbral = float(p.get("area_min_km2", 10))
    ee = _ee()
    progreso(0.2, "pidiendo la red de ríos HydroSHEDS")
    fc = ee.FeatureCollection("WWF/HydroSHEDS/v1/FreeFlowingRivers").filterBounds(ee.Geometry.Rectangle(_caja(lon, lat, medio))).filter(ee.Filter.gte("UPLAND_SKM", umbral))
    n = fc.size().getInfo()
    if n == 0:
        raise DescargaError("No hay tramos HydroSHEDS en la zona con ese umbral de área.")
    if n > 5000:
        raise DescargaError(f"{n} tramos: sube area_min_km2 o reduce medio_km.")
    progreso(0.5, f"descargando {n} tramos")
    js = fc.select(["REACH_ID", "UPLAND_SKM", "DIS_AV_CMS", "RIV_ORD", "LENGTH_KM"]).getInfo()
    g = gpd.GeoDataFrame.from_features(js["features"], crs=4326)
    epsg = utm_epsg(lon, lat)
    g.to_file(destino / "rios_hydrosheds_wgs84.shp"); g.to_crs(epsg).to_file(destino / "rios_hydrosheds_utm.shp"); g.to_file(destino / "rios_hydrosheds.gpkg", driver="GPKG")
    g.drop(columns="geometry").to_csv(destino / "rios_hydrosheds.csv", index=False, encoding="utf-8-sig")
    return {"archivos": ["rios_hydrosheds_wgs84.shp", "rios_hydrosheds_utm.shp", "rios_hydrosheds.gpkg", "rios_hydrosheds.csv"], "n_tramos": int(n), "area_min_km2": umbral,
            "fuente": "HydroSHEDS Free-Flowing Rivers (Grill et al., 2019) vía Earth Engine",
            "nota": "UPLAND_SKM es el área aportante de HydroSHEDS (15 arcsec) y DIS_AV_CMS un caudal medio MODELADO (WaterGAP): referencias, no observaciones."}


def ultima_descarga(carpeta, fuente, archivo_sufijo):
    ds = sorted((Path(carpeta) / "datos_descargados").glob(f"{fuente}_2*"))
    for d in ds[::-1]:
        est = d / "estado.json"
        if est.exists() and json.loads(est.read_text(encoding="utf-8")).get("estado") == "completado":
            f = next(iter(sorted(d.glob(f"*{archivo_sufijo}"))), None)
            if f:
                return f
    return None


def contraste_hydrosheds(rios, salida_lonlat, area_km2, radio_m=1500.0):
    """Busca el tramo HydroSHEDS de área más parecida (Delta, G10; Gamma tomaba el de mayor área) a ≤ radio de la salida y compara su área aportante con la delineada."""
    gpd = _gp()
    import shapely.geometry as sg
    r = gpd.read_file(rios)
    if r.empty or "UPLAND_SKM" not in r.columns:
        return None
    utm = r.estimate_utm_crs()
    pt = gpd.GeoSeries([sg.Point(salida_lonlat)], crs=4326).to_crs(utm).iloc[0]
    ru = r.to_crs(utm); d = ru.distance(pt)
    cerca = ru[d <= radio_m]
    if cerca.empty:
        return {"tramo": None, "nota": f"Ningún tramo HydroSHEDS a menos de {radio_m:.0f} m de la salida."}
    t = cerca.loc[(np.log(cerca["UPLAND_SKM"].clip(lower=1e-6) / float(area_km2))).abs().idxmin()]   # G10 (Delta): área más parecida, no la mayor
    return {"reach_id": int(t["REACH_ID"]), "area_hydrosheds_km2": round(float(t["UPLAND_SKM"]), 2), "caudal_medio_modelado_m3s": round(float(t["DIS_AV_CMS"]), 3),
            "dist_m": round(float(d[t.name]), 1), "diferencia_area_pct": round(100 * (area_km2 / float(t["UPLAND_SKM"]) - 1), 2),
            "nota": "Tramo de área aportante más parecida a ≤ 1,5 km de la salida. HydroSHEDS es una referencia global (~500 m), no la verdad."}


def salida_en_rio(rios, lon, lat, radio_m):
    """Punto más cercano sobre el tramo HydroSHEDS de MAYOR área aportante a ≤ radio del punto dado."""
    gpd = _gp()
    import shapely.geometry as sg
    from shapely.ops import nearest_points
    r = gpd.read_file(rios); utm = r.estimate_utm_crs(); ru = r.to_crs(utm)
    pt = gpd.GeoSeries([sg.Point(lon, lat)], crs=4326).to_crs(utm).iloc[0]
    d = ru.distance(pt); cerca = ru[d <= radio_m]
    if cerca.empty:
        raise CuencaError(f"No hay tramos HydroSHEDS a menos de {radio_m / 1000:.1f} km del punto.")
    t = cerca.loc[cerca["UPLAND_SKM"].idxmax()]
    q = nearest_points(t.geometry, pt)[0]
    ll = gpd.GeoSeries([q], crs=utm).to_crs(4326).iloc[0]
    return {"lonlat": [ll.x, ll.y], "reach_id": int(t["REACH_ID"]), "area_km2": float(t["UPLAND_SKM"]), "dist_m": float(q.distance(pt))}


def fuente_delinear(destino, p, progreso):
    """Delineación como tarea en segundo plano (progreso y cancelación del gestor de descargas)."""
    carpeta = Path(p["proyecto"])
    datos = json.loads((carpeta / "proyecto_uceclima.json").read_text(encoding="utf-8"))
    mdt = p.get("mdt") or None
    if p.get("usar_mdt_amplio", True) and not mdt:
        f = ultima_descarga(carpeta, "mdt_cuenca", ".tif"); mdt = str(f) if f else None
    rios = p.get("rios") or None
    if p.get("quemar_rios") and not rios:
        f = ultima_descarga(carpeta, "rios", "rios_hydrosheds.gpkg"); rios = str(f) if f else None
        if not rios:
            from .descargas import DescargaError
            raise DescargaError("Pediste quemar ríos pero no hay red descargada: usa primero «Descargar ríos HydroSHEDS».")
    lon, lat = float(p["lon"]), float(p["lat"]); movida = None
    if float(p.get("snap_rio_km") or 0) > 0:                     # llevar la salida al tramo HydroSHEDS de mayor área cercano (lo elige la persona)
        ref = ultima_descarga(carpeta, "rios", "rios_hydrosheds.gpkg")
        if not ref:
            from .descargas import DescargaError
            raise DescargaError("Para ajustar la salida al río primero descarga la red HydroSHEDS.")
        movida = salida_en_rio(ref, lon, lat, float(p["snap_rio_km"]) * 1000)
        lon, lat = movida["lonlat"]
    progreso(0.1, "rellenando depresiones y calculando direcciones de flujo" + (" (MDT amplio)" if mdt else " (MDT del proyecto)"))
    r = delinear_mdt(carpeta, datos, lon, lat, mdt=mdt, snap_m=float(p.get("snap_m", 500)), rios=rios, quema_m=float(p.get("quema_m", 5)))
    if movida:
        r["avisos"].insert(0, f"Salida llevada {movida['dist_m']:.0f} m al tramo HydroSHEDS {movida['reach_id']} ({movida['area_km2']:.0f} km² aportantes), a pedido de la persona.")
        r["salida_en_rio"] = movida
    progreso(0.9, "comparando con HydroSHEDS")
    ref = ultima_descarga(carpeta, "rios", "rios_hydrosheds.gpkg")
    if ref:
        c = contraste_hydrosheds(ref, r["salida_ajustada_lonlat"], r["area_km2"])
        if c:
            r["contraste_hydrosheds"] = c
            rj = carpeta / r["carpeta"] / "resumen.json"; rr = json.loads(rj.read_text(encoding="utf-8")); rr["contraste_hydrosheds"] = c
            rj.write_text(json.dumps(rr, ensure_ascii=False, indent=2), encoding="utf-8")
    (destino / "resultado.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"archivos": ["resultado.json"], "cuenca": r["carpeta"], "area_km2": r["area_km2"], "avisos": r["avisos"], "contraste_hydrosheds": r.get("contraste_hydrosheds")}


def fuente_chirps_cuenca(destino, p, progreso):
    """Lluvia CHIRPS diaria PROMEDIADA sobre la cuenca activa (media ponderada por área de las celdas de 0,05°)."""
    import pandas as pd
    from .descargas import DescargaError, CHIRPS_V2, CHIRPS_V3
    gpd = _gp()
    carpeta = Path(p["proyecto"]); act = carpeta / "cuenca" / "activa.json"
    if not act.exists():
        raise DescargaError("No hay cuenca activa: carga un shape, acepta una delineación o crea la malla CHIRPS.")
    a = json.loads(act.read_text(encoding="utf-8"))
    g = gpd.read_file(carpeta / a["carpeta"] / "cuenca.gpkg").to_crs(4326)
    poli = g.geometry.unary_union.simplify(0.002)
    ini, fin = pd.Timestamp(p.get("inicio") or "1981-01-01"), pd.Timestamp(p.get("fin") or pd.Timestamp.today().normalize())
    ee = _ee()
    asset, version = CHIRPS_V3, "CHIRPS v3 (DAILY_SAT)"
    try:
        ee.ImageCollection(CHIRPS_V3).size().getInfo()
    except Exception:
        asset, version = CHIRPS_V2, "CHIRPS v2"
    geom = ee.Geometry(poli.__geo_interface__)
    filas = []; anios = list(range(ini.year, fin.year + 1))
    for k, y in enumerate(anios):
        a0 = max(ini, pd.Timestamp(y, 1, 1)); b0 = min(fin, pd.Timestamp(y, 12, 31))
        col = ee.ImageCollection(asset).filterDate(a0.strftime("%Y-%m-%d"), (b0 + pd.Timedelta(days=1)).strftime("%Y-%m-%d")).select("precipitation")
        f = col.map(lambda im: ee.Feature(None, {"t": im.date().format("YYYY-MM-dd"), "m": im.reduceRegion(ee.Reducer.mean(), geom, 5566).get("precipitation")}))
        for intento in range(3):
            try:
                feats = f.getInfo()["features"]; break
            except Exception as e:
                if intento == 2:
                    raise DescargaError(f"Earth Engine falló en {y}: {str(e)[:160]}") from e
                time.sleep(3)
        filas += [(x["properties"]["t"], x["properties"].get("m")) for x in feats]
        progreso((k + 1) / len(anios), f"CHIRPS sobre la cuenca · {y}")
    df = pd.DataFrame(filas, columns=["fecha", "lluvia_cuenca_mm"]).drop_duplicates("fecha").sort_values("fecha")
    df.to_csv(destino / "chirps_cuenca_diario.csv", index=False)
    return {"archivos": ["chirps_cuenca_diario.csv"], "fuente": asset, "version": version, "n_dias": int(len(df)), "periodo": [df["fecha"].min(), df["fecha"].max()],
            "cuenca": a["carpeta"], "area_km2": a.get("area_km2"),
            "nota": "Media areal diaria de CHIRPS sobre el polígono de la cuenca activa (escala 5566 m; contorno simplificado ~200 m). Es lluvia estimada por satélite, no medida."}


def extension_activa(carpeta, crs, margen_m=1000.0):
    """(x0, y0, x1, y1) de la cuenca activa en `crs` con margen, y su caja en lon/lat; None si no hay cuenca activa (o es la malla)."""
    act = Path(carpeta) / "cuenca" / "activa.json"
    if not act.exists():
        return None
    a = json.loads(act.read_text(encoding="utf-8"))
    if a.get("origen") == "malla":
        return None
    g = _gp().read_file(Path(carpeta) / a["carpeta"] / "cuenca.gpkg")
    x0, y0, x1, y1 = g.to_crs(crs).total_bounds
    ll = g.to_crs(4326).total_bounds
    return {"xy": (x0 - margen_m, y0 - margen_m, x1 + margen_m, y1 + margen_m), "lonlat": tuple(float(v) for v in ll), "area_km2": a.get("area_km2")}
