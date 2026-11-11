# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""CN y Manning ESTIMADOS desde Earth Engine (por defecto, siempre): cobertura ESA WorldCover v200 (2021) × textura de suelo OpenLandMap (USDA, b0) → grupo hidrológico → CN; Manning por cobertura.
Es el MISMO método y las MISMAS tablas con que CLIMANET preparó los insumos de Milagro (`MILAGROCODEX/prepare_inputs.py`, 2026-10-07): tablas de referencia, NO calibradas ni medidas.
Reglas: la malla es la del MDT registrado del proyecto; no hay valores por defecto silenciosos (si queda un hueco de cobertura, se detiene); los huecos del mapa de suelo se llenan con el vecino más
próximo hasta 2 km y se declara el porcentaje; si el proyecto ya trae CN/Manning detallados del usuario NO se sobrescriben (los de GEE se guardan al lado para comparar)."""
import json
import re
from datetime import datetime
from pathlib import Path
import numpy as np

NMAP = {10: .12, 20: .05, 30: .035, 40: .04, 50: .08, 60: .025, 70: .03, 80: .03, 90: .05, 95: .055, 100: .03}
HSG = {1: 4, 2: 4, 3: 4, 4: 4, 5: 4, 6: 3, 7: 2, 8: 2, 9: 1, 10: 2, 11: 1, 12: 1}
CN = {10: (36, 60, 73, 79), 20: (35, 56, 70, 77), 30: (49, 69, 79, 84), 40: (67, 78, 85, 89), 50: (77, 85, 90, 92), 60: (77, 86, 91, 94), 70: (98, 98, 98, 98),
      80: (100, 100, 100, 100), 90: (98, 98, 98, 98), 95: (98, 98, 98, 98), 100: (49, 69, 79, 84)}
CLASES_WC = {10: "árboles", 20: "arbustos", 30: "pastizal", 40: "cultivos", 50: "construido", 60: "suelo desnudo", 70: "nieve/hielo", 80: "agua", 90: "humedal herbáceo", 95: "manglar", 100: "musgo/líquenes"}


PALETA_WC = {10: "#006400", 20: "#ffbb22", 30: "#ffff4c", 40: "#f096ff", 50: "#fa0000", 60: "#b4b4b4", 70: "#f0f0f0", 80: "#0064c8", 90: "#0096a0", 95: "#00cf75", 100: "#fae6a0"}


def _ultimas_capas(carpeta):
    """(uso_suelo_worldcover.tif, textura_suelo_openlandmap.tif) de la descarga «suelo» más reciente del proyecto, o None."""
    raiz = Path(carpeta) / "datos_descargados"                                         # G14: también la subcarpeta «suelo» de una descarga de sitio
    for d in sorted(list(raiz.glob("suelo_*")) + list(raiz.glob("sitio_*/suelo")), key=lambda x: x.stat().st_mtime, reverse=True):
        a, b = d / "uso_suelo_worldcover.tif", d / "textura_suelo_openlandmap.tif"
        if a.exists() and b.exists():
            return a, b
    return None


def _bajar_capa(img, geom, escala, destino, nombre, progreso, f0, f1, D):
    """Pide UNA capa a Earth Engine en su resolución nativa (EPSG:4326). Tiempo límite de conexión 15 s y de respuesta 90 s por intento, 3 intentos, con aviso de cada intento."""
    import io, zipfile, requests, rasterio
    ultimo = ""
    for k in range(1, 4):
        progreso(f0 + (f1 - f0) * (k - 1) / 3, f"{nombre}: pidiendo a Earth Engine (intento {k} de 3, espera máxima 90 s)")
        try:
            url = img.getDownloadURL({"region": geom, "scale": escala, "crs": "EPSG:4326", "format": "GEO_TIFF", "filePerBand": False})
            r = requests.get(url, timeout=(15, 90)); r.raise_for_status()
            if r.content[:2] == b"PK":
                z = zipfile.ZipFile(io.BytesIO(r.content)); datos = z.read(next(n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))))
            else:
                datos = r.content
            (destino / nombre).write_bytes(datos)
            with rasterio.open(destino / nombre) as s:
                assert s.count >= 1 and s.width > 0 and s.height > 0
            return
        except Exception as e:
            ultimo = str(e)[:200]
            if "50331648" in ultimo or "request size" in ultimo.lower():
                raise D.DescargaError("El área es demasiado grande para una sola petición (límite de Earth Engine 50 MB). Usa un MDT/área de estudio más pequeña.")
    raise D.DescargaError(f"Earth Engine no entregó «{nombre}» tras 3 intentos: {ultimo}. Revisa tu conexión a internet y que la conexión del módulo Datos / GEE esté verificada.")


def bbox_proyecto(p, medio_km=10.0):
    """Caja (lon_min, lat_min, lon_max, lat_max) del área del proyecto: el área de estudio del modelo si ya hay MDT registrado (con un margen pequeño) o ±medio_km alrededor del sitio."""
    from . import descargas as D
    from .ui import proyecto as P
    carpeta = Path(p["proyecto"]); datos, _ = P.abrir(str(carpeta)); _, cfg = P.config_climanet(datos, carpeta)
    if cfg.get("aoi") and cfg.get("dem"):                                                                    # área del modelo (con un margen pequeño)
        from pyproj import Transformer
        x0, x1, y0, y1 = [float(v) for v in cfg["aoi"]]; tf = Transformer.from_crs(datos["crs"], "EPSG:4326", always_xy=True)
        pts = [tf.transform(x, y) for x in (x0, x1) for y in (y0, y1)]; lons, lats = [a for a, b in pts], [b for a, b in pts]
        bbox = [min(lons) - 0.003, min(lats) - 0.003, max(lons) + 0.003, max(lats) + 0.003]; origen = "área de estudio del modelo"
    else:
        lon, lat = p.get("lon"), p.get("lat")
        if lon is None:
            m = re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(datos.get("ubicacion", "")))
            if not m:
                raise D.DescargaError("El proyecto no tiene un punto de sitio (lon/lat).")
            lon, lat = m.group(1), m.group(2)
        lon, lat = float(lon), float(lat); medio = medio_km / 111.0
        bbox = [lon - medio, lat - medio, lon + medio, lat + medio]; origen = f"±{medio_km:g} km alrededor del sitio (aún no hay MDT registrado)"
    return bbox, origen


def suelo_gee(destino, p, progreso):
    """Paso 1: baja a la carpeta del proyecto las capas de USO DE SUELO (ESA WorldCover v200, 10 m) y TEXTURA DEL SUELO (OpenLandMap, 250 m) del área del proyecto, en su resolución nativa.
    El paso 2 (CN y Manning) se calcula después LOCALMENTE con estas capas: se pueden ver, revisar y reutilizar sin volver a pedir nada a Earth Engine."""
    import json, math
    import numpy as np, rasterio
    from . import gee_chirps as G, descargas as D
    from .ui import proyecto as P
    carpeta = Path(p["proyecto"]); datos, _ = P.abrir(str(carpeta)); _, cfg = P.config_climanet(datos, carpeta)
    bbox, origen = bbox_proyecto(p, medio_km=float(p.get("medio_km", 10)))
    ancho_px = (bbox[2] - bbox[0]) * 111320 * math.cos(math.radians((bbox[1] + bbox[3]) / 2)) / 10
    if ancho_px > 6000 or (bbox[3] - bbox[1]) * 111320 / 10 > 6000:
        raise D.DescargaError("El área es demasiado grande para bajar el uso de suelo a 10 m en una petición. Usa un área de estudio más pequeña (≤ 30 km de lado).")
    progreso(0.02, "conectando con Earth Engine")
    info, ee = G.iniciar()
    if not info.get("autenticado"):
        raise D.DescargaError("Earth Engine no está conectado: abre el módulo «Datos / GEE» y pulsa «Conectar con Google Earth Engine». " + str(info.get("error"))[:120])
    geom = ee.Geometry.Rectangle(bbox, proj="EPSG:4326", geodesic=False)
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    tx = ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02").select("b0")
    _bajar_capa(wc, geom, 10, destino, "uso_suelo_worldcover.tif", progreso, 0.05, 0.60, D)
    _bajar_capa(tx, geom, 250, destino, "textura_suelo_openlandmap.tif", progreso, 0.60, 0.90, D)
    progreso(0.92, "comprobando las capas y dibujando la vista previa")
    with rasterio.open(destino / "uso_suelo_worldcover.tif") as s:
        w = s.read(1, masked=True).filled(0).astype(int); nd = int((w == 0).sum())
    clases = {int(c): {"clase": CLASES_WC.get(int(c), "?"), "pct": round(float((w == c).mean() * 100), 2)} for c in np.unique(w) if c != 0}
    with rasterio.open(destino / "textura_suelo_openlandmap.tif") as s:
        t = s.read(1, masked=True); tex_validas = round(float(t.count() / t.size * 100), 1)
    vista = []
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap, BoundaryNorm
        cod = sorted(PALETA_WC); cmap = ListedColormap(["#000000"] + [PALETA_WC[c] for c in cod]); norm = BoundaryNorm([0] + [c - 0.5 for c in cod] + [cod[-1] + 0.5], cmap.N)
        fig, ax = plt.subplots(figsize=(6.5, 5.2)); ax.imshow(np.where(np.isin(w, cod), w, 0), cmap=cmap, norm=norm, interpolation="nearest"); ax.set_axis_off()
        ax.set_title("Uso de suelo (ESA WorldCover 2021, 10 m)\n" + " · ".join(f"{v['clase']} {v['pct']:g} %" for k, v in sorted(clases.items(), key=lambda kv: -kv[1]['pct'])[:4]), fontsize=8)
        fig.tight_layout(); fig.savefig(destino / "uso_suelo_vista.png", dpi=130); plt.close(fig); vista = ["uso_suelo_vista.png"]
    except Exception:
        pass
    return {"archivos": ["uso_suelo_worldcover.tif", "textura_suelo_openlandmap.tif"] + vista, "fuente": "ESA WorldCover v200 (2021, 10 m) y OpenLandMap SOL_TEXTURE-CLASS_USDA-TT (250 m), vía Earth Engine",
            "bbox_lonlat": bbox, "origen_area": origen, "clases_cobertura": clases, "sin_dato_pct": round(100 * nd / w.size, 2), "textura_validas_pct": tex_validas, "crs": "EPSG:4326",
            "nota": "Capas cartográficas en resolución nativa. El paso siguiente calcula CN y Manning con tablas de referencia a partir de ellas: estimaciones, no medidas ni calibradas."}


def cn_manning_gee(destino, p, progreso):
    import requests
    from rasterio.warp import reproject, Resampling, transform_bounds
    import rasterio
    from scipy.ndimage import distance_transform_edt
    from . import gee_chirps as G, descargas as D
    from .ui import proyecto as P
    carpeta = Path(p["proyecto"])
    datos, _ = P.abrir(str(carpeta))
    cfgp, cfg = P.config_climanet(datos, carpeta)
    if not cfg.get("dem") or not cfg.get("aoi"):
        raise D.DescargaError("Falta el MDT del proyecto (define la malla del modelo): pulsa «MDT 30 m (Copernicus)» o carga tu MDT en el módulo 5 · Terreno. Si ya lo descargaste, vuelve a pulsar «2 · Calcular CN y Manning»: se registra solo.")
    from climanet import terrain
    dem, meta = terrain.load_dem(cfg["dem"], float(cfg.get("res", 30)), cfg.get("aoi"))
    tr, crs = meta["transform"], meta["crs"]
    activo = np.isfinite(dem)
    capas = _ultimas_capas(carpeta)
    if not capas:
        raise D.DescargaError("Primero baja las capas de uso de suelo y suelo: botón «1 · Uso de suelo y suelo» del módulo Datos / GEE.")
    dl_wc, dl_tx = capas
    progreso(0.2, "leyendo las capas de uso de suelo y suelo descargadas (sin conexión)")
    progreso(0.6, "calculando CN y Manning")
    grids = []
    for archivo in (dl_wc, dl_tx):
        with rasterio.open(archivo) as s:
            src = s.read(1, masked=True).astype("float32").filled(np.nan); dst = np.full(dem.shape, np.nan, dtype=np.float32)
            reproject(src, dst, src_transform=s.transform, src_crs=s.crs, dst_transform=tr, dst_crs=crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.nearest)
            grids.append(dst)
    wcg, texg = grids
    textura_valida = np.isfinite(texg) & (texg >= 1) & (texg <= 12)
    necesita_suelo = activo & np.isin(wcg, [10, 20, 30, 40, 50, 60, 100])
    estimado = necesita_suelo & ~textura_valida
    dist, idx = distance_transform_edt(~textura_valida, sampling=(abs(tr.e), tr.a), return_indices=True)
    if estimado.any() and dist[estimado].max() > 2000:
        raise D.DescargaError("Hay un hueco de suelo a más de 2 km: no se estima; se necesitan datos de suelo del lugar.")
    tex_lleno = texg.copy(); tex_lleno[estimado] = texg[tuple(idx[:, estimado])]
    cn = np.full(dem.shape, np.nan, dtype=np.float32); nm = np.full(dem.shape, np.nan, dtype=np.float32)
    for cover, vals in CN.items():
        for t, g in HSG.items():
            cn[(wcg == cover) & (tex_lleno == t)] = vals[g - 1]
    cn[wcg == 80] = 100; cn[(wcg == 90) | (wcg == 95)] = 98
    for cover, n in NMAP.items():
        nm[wcg == cover] = n
    valido = activo & np.isfinite(cn) & np.isfinite(nm)
    cobertura = float(valido.sum() / max(activo.sum(), 1) * 100)
    if cobertura < 99.99:
        raise D.DescargaError(f"Cobertura de parámetros incompleta ({cobertura:.3f} %): hay clases de cobertura o de suelo sin tabla. No se rellena con valores por defecto.")
    perfil = {k: v for k, v in meta.items() if k not in ("cobertura_dem", "aviso")}; perfil.update(dtype="float32", nodata=-9999, compress="deflate", count=1, driver="GTiff")
    archivos = []
    for nombre, arr in (("cn_gee.tif", cn), ("manning_gee.tif", nm), ("worldcover.tif", wcg), ("textura_suelo.tif", texg), ("mascara_suelo_estimado.tif", estimado.astype(float))):
        with rasterio.open(destino / nombre, "w", **perfil) as s:
            s.write(np.where(activo, arr, -9999).astype("float32"), 1)
        archivos.append(nombre)
    clases = {int(c): {"clase": CLASES_WC.get(int(c), "?"), "pct": round(float((wcg[activo] == c).mean() * 100), 2)} for c in np.unique(wcg[activo & np.isfinite(wcg)])}
    res = {"archivos": archivos, "fuente": "ESA WorldCover v200 (2021) × OpenLandMap SOL_TEXTURE-CLASS_USDA b0 (capas bajadas con Earth Engine y guardadas en el proyecto: " + dl_wc.parent.name + ")", "cobertura_parametros_pct": cobertura, "suelo_estimado_pct": round(float(estimado.sum() / max(activo.sum(), 1) * 100), 3),
           "suelo_estimado_dist_max_m": float(dist[estimado].max()) if estimado.any() else 0.0, "cn_min_max_media": [float(np.nanmin(cn[activo])), float(np.nanmax(cn[activo])), round(float(np.nanmean(cn[activo])), 1)],
           "manning_min_max_media": [float(np.nanmin(nm[activo])), float(np.nanmax(nm[activo])), round(float(np.nanmean(nm[activo])), 4)], "clases_cobertura": clases,
           "tablas": {"manning": NMAP, "HSG": HSG, "CN": {str(k): v for k, v in CN.items()}}, "celdas": int(activo.sum()), "res_m": abs(tr.a),
           "nota": "Estimaciones cartográficas con tablas de referencia (las mismas de Milagro), NO medidas ni calibradas. La resolución de la malla no equivale a detalle observado. En zonas urbanas o con obras, un CN/Manning detallado del lugar es mejor y tiene prioridad."}
    res["registro"] = registrar(carpeta, destino, res)
    return res


def registrar(carpeta, destino, res):
    """Escribe cn_tif/manning_tif en la configuración SOLO si el proyecto no trae los suyos (copia .bak). Devuelve qué pasó."""
    from .ui import proyecto as P
    datos, _ = P.abrir(str(carpeta))
    cp = Path(carpeta) / datos["config_climanet"]
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    propios = [k for k in ("cn_tif", "manning_tif") if cfg.get(k) and cfg.get(k.split("_")[0] + "_origen") != "gee"]
    if propios:
        return {"estado": "conservado_usuario", "texto": f"El proyecto ya trae {', '.join(propios)} propios: se conservan. Los de Earth Engine quedaron guardados para comparar."}
    marca = f"{datetime.now():%Y%m%d_%H%M%S}"
    (cp.parent / f"{cp.name}.{marca}.bak").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    rel = lambda n: str((Path(destino) / n).relative_to(carpeta)).replace("\\", "/")
    cfg["cn_tif"] = rel("cn_gee.tif"); cfg["manning_tif"] = rel("manning_gee.tif"); cfg["cn_origen"] = "gee"; cfg["manning_origen"] = "gee"
    cp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    if isinstance(datos.get("procedencia"), dict):
        d2 = json.loads(json.dumps(datos)); d2["procedencia"].setdefault("notas", []).append(f"CN y Manning estimados desde Earth Engine ({marca}): WorldCover 2021 × suelo OpenLandMap, tablas de referencia de CLIMANET; no calibrados.")
        P.guardar(d2, carpeta, sobrescribir=True)
    return {"estado": "registrado", "texto": "CN y Manning de Earth Engine registrados en el proyecto (por defecto). Si tienes datos detallados, regístralos: tendrán prioridad."}
