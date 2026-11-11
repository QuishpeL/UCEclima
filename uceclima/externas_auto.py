# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Lambda 9.2 · cuencas externas AUTOMÁTICAS e hidrograma de entrada de GEOGLOWS para ríos grandes.

Es el método con que se modeló Quito por secciones (5-nov-2026, script externas_seccion.py), ahora dentro del programa:
  1. D8 (priority-flood) sobre el MDT AMPLIO del proyecto (GLO-30 agregado, descarga «mdt_cuenca»).
  2. Entradas = celdas de fuera del área 2D que descargan a una celda de dentro con ≥ area_min_km2 de aporte. Cada celda de fuera pertenece a
     UNA sola entrada (áreas incrementales, sin solape: el núcleo lo exige).
  3. Cuencas chicas (≤ area_max_km2): CN de las MISMAS tablas WorldCover × OpenLandMap (AMC II) del proyecto y lag NEH-630 (longitud de flujo y
     pendiente del MDT amplio). El núcleo calcula su hidrograma con la misma IDF y Tr de la corrida.
  4. Cuencas grandes (> area_max_km2): no se modelan con SCS; se proponen como entrada GEOGLOWS (hidrograma de un modelo global, ver
     climanet.entradas_geoglows).
  5. La entrada se ajusta a la celda de cauce del MDT del proyecto (encajonamiento ≥ 0,3 m) a ≤ 5 celdas del cruce del borde.
Nada se registra en el proyecto hasta que la persona lo decide (botones de la pantalla). Resultados no calibrados."""
import io
import json
import math
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

GEO = "https://geoglows.ecmwf.int/api/v2/"


def _proyecto(p):
    from .ui import proyecto as P
    carpeta = Path(p["proyecto"]); datos, _ = P.abrir(str(carpeta)); _, cfg = P.config_climanet(datos, carpeta)
    return carpeta, datos, cfg


def _ruta(carpeta, r):
    r = Path(str(r)); return r if r.is_absolute() else Path(carpeta) / r


# ------------------------------------------------------------------------------------------------ 1-5. detección de cuencas externas
def fuente_externas(destino, p, progreso):
    import geopandas as gpd
    import rasterio
    import shapely.geometry as sg
    from rasterio import features
    from shapely.ops import unary_union
    from . import cuenca as C
    from .descargas import DescargaError
    carpeta, datos, cfg = _proyecto(p)
    aoi = cfg.get("aoi") or []
    if len(aoi) != 4 or not cfg.get("dem"):
        raise DescargaError("Primero registra el MDT del proyecto (módulo 5 · Terreno): el área 2D define qué queda «fuera».")
    amin, amax = float(p.get("area_min_km2", 1.0)), float(p.get("area_max_km2", 100.0))
    if not (0.1 <= amin < amax <= 5000):
        raise DescargaError("Áreas no válidas: 0,1 ≤ mínima < máxima ≤ 5000 km².")
    mdt = C.ultima_descarga(carpeta, "mdt_cuenca", ".tif")
    if not mdt:
        raise DescargaError("Falta el MDT amplio: en el módulo «hidro» pulsa «Descargar MDT amplio» (GLO-30, 90 m, lado de 60 a 120 km) y vuelve aquí.")
    progreso(0.05, "leyendo el MDT amplio")
    with rasterio.open(mdt) as src:
        z = src.read(1, masked=True).astype("float64"); T = src.transform; crs_mdt = src.crs; bnds = src.bounds
    if str(crs_mdt).upper() != str(datos.get("crs", crs_mdt)).upper():
        from pyproj import Transformer
        tf = Transformer.from_crs(datos["crs"], crs_mdt, always_xy=True)
        xs, ys = zip(*[tf.transform(x, y) for x in aoi[:2] for y in aoi[2:]]); aoi_m = [min(xs), max(xs), min(ys), max(ys)]
    else:
        aoi_m = [float(v) for v in aoi]
    if not (bnds.left < aoi_m[0] and bnds.right > aoi_m[1] and bnds.bottom < aoi_m[2] and bnds.top > aoi_m[3]):
        raise DescargaError("El MDT amplio no rodea el área 2D: descárgalo de nuevo centrado en el proyecto y más grande.")
    res = abs(T.a); A = res * res / 1e6
    valido = ~np.ma.getmaskarray(z) & np.isfinite(z.filled(np.nan)); zd = z.filled(np.nan)
    h, w = zd.shape
    progreso(0.1, f"rellenando depresiones y direcciones de flujo D8 ({h} × {w} celdas de {res:.0f} m; puede tardar 1-3 min)")
    orden, recv, W, _, _ = C._inundacion_prioridad(zd, valido)
    recv = np.asarray(recv, dtype=np.int64); n = len(recv)
    progreso(0.35, "acumulando el flujo")
    acc = np.zeros(n, dtype=np.int64); acc[np.asarray(orden, dtype=np.int64)] = 1
    for i in reversed(orden):
        r = recv[i]
        if r >= 0: acc[r] += acc[i]
    # centros de celda en el ráster con anillo → dentro / fuera del área 2D
    filas, cols = np.divmod(np.arange(n), W); filas -= 1; cols -= 1
    xc = T.c + (cols + 0.5) * T.a; yc = T.f + (filas + 0.5) * T.e
    dentro = (xc >= aoi_m[0]) & (xc <= aoi_m[1]) & (yc >= aoi_m[2]) & (yc <= aoi_m[3])
    tiene = recv >= 0; dentro_rec = np.zeros(n, bool); dentro_rec[tiene] = dentro[recv[tiene]]
    donantes = np.flatnonzero(tiene & ~dentro & dentro_rec & (acc * A >= amin))
    if not len(donantes):
        raise DescargaError(f"Ningún cauce de fuera con ≥ {amin:g} km² entra al área 2D: no hacen falta cuencas externas (o el área mínima es muy alta).")
    donantes = donantes[np.argsort(-acc[donantes])]
    progreso(0.45, f"{len(donantes)} entradas con ≥ {amin:g} km²: separando sus cuencas (sin solape)")
    etiqueta = np.zeros(n, dtype=np.int32)
    for k, d in enumerate(donantes, 1): etiqueta[d] = k
    for i in orden:                                                             # de aguas abajo a aguas arriba: cada celda de fuera hereda la entrada de su receptora
        if etiqueta[i] == 0 and not dentro[i]:
            r = recv[i]
            if r >= 0 and not dentro[r]: etiqueta[i] = etiqueta[r]
    lab = etiqueta.reshape(-1, W)[1:-1, 1:-1]
    borde_mdt = np.zeros((h, w), bool); borde_mdt[[0, -1], :] = True; borde_mdt[:, [0, -1]] = True
    geoms = {}
    for gg, v in features.shapes(lab, mask=lab > 0, transform=T):
        geoms.setdefault(int(v), []).append(sg.shape(gg))
    filas_out = []
    for k, d in enumerate(donantes, 1):
        m = lab == k; area = float(m.sum()) * A
        if area < amin:                                                         # su aporte propio (sin lo que ya cuenta otra entrada aguas arriba) es menor que el mínimo
            continue
        rr, cc = divmod(int(recv[d]), W); rr -= 1; cc -= 1
        filas_out.append({"id": k, "area_km2": round(area, 2), "tipo": "chica" if area <= amax else "grande",
                          "cortada_borde_mdt": bool((m & borde_mdt).any()), "x_cruce": float(T.c + (cc + .5) * T.a), "y_cruce": float(T.f + (rr + .5) * T.e),
                          "geometry": unary_union(geoms.get(k, [])), "_mask_id": k})
    g = gpd.GeoDataFrame(filas_out, crs=crs_mdt)
    # ---- 3. longitud de flujo, pendiente (MDT amplio) y CN (WorldCover × OpenLandMap) → lag NEH-630
    progreso(0.55, "longitud de flujo y pendiente de cada cuenca")
    gy, gx = np.gradient(np.where(valido, zd, np.nan), res); pend = np.hypot(gy, gx) * 100
    long_flujo = np.zeros(n)                                                    # distancia a lo largo del flujo hasta la entrada (desde cada celda)
    for i in orden:
        r = recv[i]
        if r >= 0 and etiqueta[i] and etiqueta[r] == etiqueta[i]:
            ra, ca = divmod(i, W); rb, cb = divmod(r, W); long_flujo[i] = long_flujo[r] + res * math.hypot(ra - rb, ca - cb)
    nz = np.flatnonzero(etiqueta); lmax = np.zeros(len(donantes) + 1)
    np.maximum.at(lmax, etiqueta[nz], long_flujo[nz])
    Lmax = {k: float(lmax[k]) + res for k in range(1, len(donantes) + 1)}
    lab_pend = {k: float(np.nanmean(pend[lab == k])) for k in range(1, len(donantes) + 1)}
    chicas = g[g.tipo == "chica"]
    cn_k, cob_k = {}, {}
    if len(chicas):
        progreso(0.6, f"uso de suelo y textura de Earth Engine para {len(chicas)} cuencas chicas")
        cn_k, cob_k = _cn_cuencas(destino, chicas, crs_mdt, progreso)
    progreso(0.85, "ajustando cada entrada a la celda de cauce del MDT del proyecto")
    from climanet import terrain
    from climanet.diagnostico import diagnostico_entradas
    from climanet.pipeline import _celda_de_xy
    dem, meta = terrain.load_dem(str(_ruta(carpeta, cfg["dem"])), float(cfg["res"]), aoi); active = np.isfinite(dem); dx = float(cfg["res"]); ny, nx = dem.shape; T2 = meta["transform"]
    to_proj = None
    if str(crs_mdt).upper() != str(datos.get("crs", crs_mdt)).upper():
        from pyproj import Transformer
        to_proj = Transformer.from_crs(crs_mdt, datos["crs"], always_xy=True)
    usados, salida = set(), []
    for _, r in g.iterrows():
        k = int(r.id); xe, ye = (r.x_cruce, r.y_cruce) if to_proj is None else to_proj.transform(r.x_cruce, r.y_cruce)
        r0, c0 = _celda_de_xy([xe, ye], meta, active)
        cand = [(a, b) for a in range(max(0, r0 - 5), min(ny, r0 + 6)) for b in range(max(0, c0 - 5), min(nx, c0 + 6))
                if min(a, b, ny - 1 - a, nx - 1 - b) <= 4 and np.hypot(a - r0, b - c0) <= 5.01 and active[a, b] and (a, b) not in usados]
        if not cand:
            cand = [(r0, c0)]
        diag = diagnostico_entradas(dem, active, cand, dx)
        ok = [x for x in diag if x["encajonamiento_m"] >= 0.3]
        pool = sorted(ok or diag, key=lambda x: (-x["encajonamiento_m"], -x["celdas_aportantes_D8"])); x = pool[0]; cel = tuple(x["celda"]); usados.add(cel)
        xy = [float(T2.c + (cel[1] + .5) * T2.a), float(T2.f + (cel[0] + .5) * T2.e)]
        fila = {"id": k, "nombre": f"E{k}", "tipo": r.tipo, "area_km2": float(r.area_km2), "cortada_borde_mdt": bool(r.cortada_borde_mdt),
                "entrada_xy": xy, "desplazamiento_m": round(float(np.hypot(cel[0] - r0, cel[1] - c0) * dx)), "encajonamiento_m": round(float(x["encajonamiento_m"]), 2),
                "en_cauce": bool(x["en_cauce"]), "advertencias_entrada": x["advertencias"], "L_m": round(Lmax[k]), "pendiente_pct": round(lab_pend[k], 1)}
        if r.tipo == "chica":
            cn = cn_k.get(k)
            fila.update(cn=None if cn is None else round(cn, 1), cobertura_cn_pct=round(cob_k.get(k, 0.0), 1))
            if cn is not None:
                S = 1000 / cn - 10
                fila["lag_h"] = round(((Lmax[k] * 3.28084) ** 0.8 * (S + 1) ** 0.7) / (1900 * math.sqrt(max(lab_pend[k], 0.5))), 2)
        salida.append(fila)
    gpkg = destino / "cuencas_externas_detectadas.gpkg"
    import pandas as pd
    atr = pd.DataFrame([{k: v for k, v in s.items() if k not in ("entrada_xy", "advertencias_entrada", "tipo", "area_km2", "cortada_borde_mdt")} for s in salida])
    g2 = g.drop(columns=["_mask_id"]).merge(atr, on="id")
    g2.to_file(gpkg, driver="GPKG")
    avisos = []
    if any(s["cortada_borde_mdt"] for s in salida):
        avisos.append("Alguna cuenca toca el borde del MDT amplio: su área está SUBESTIMADA. Descarga un MDT amplio más grande y repite la detección.")
    if any(not s["en_cauce"] for s in salida):
        avisos.append("Alguna entrada no pasa la comprobación de cauce (ruta D8 o encajonamiento). Para usarla tendrás que permitirlo bajo tu responsabilidad.")
    if any(s["tipo"] == "chica" and s.get("cn") is None for s in salida):
        avisos.append("Alguna cuenca chica quedó sin CN (sin cobertura de suelo): no se puede usar hasta tener el CN.")
    prop = {"creado": datetime.now().isoformat(timespec="seconds"), "mdt_amplio": str(mdt), "aoi": aoi, "area_min_km2": amin, "area_max_km2": amax,
            "cuencas": salida, "avisos": avisos,
            "metodo": "D8 priority-flood (Barnes et al., 2014) sobre GLO-30 agregado; áreas incrementales sin solape; CN de tablas WorldCover 2021 × OpenLandMap AMC II (iguales a CN/Manning del proyecto); lag NEH-630; entrada ajustada al cauce del MDT del proyecto. No calibrado.",
            "aportes_laterales": f"Aportes de fuera con menos de {amin:g} km² por entrada no se modelan (escorrentía de ladera menor)."}
    (destino / "propuesta.json").write_text(json.dumps(prop, ensure_ascii=False, indent=1), encoding="utf-8")
    pd.DataFrame([{k: v for k, v in s.items() if k != "advertencias_entrada"} for s in salida]).to_csv(destino / "cuencas_externas_detectadas.csv", index=False, encoding="utf-8-sig")
    progreso(0.98, "listo")
    return {"archivos": ["cuencas_externas_detectadas.gpkg", "cuencas_externas_detectadas.csv", "propuesta.json"],
            "n_chicas": int(sum(s["tipo"] == "chica" for s in salida)), "n_grandes": int(sum(s["tipo"] == "grande" for s in salida)),
            "area_total_km2": round(sum(s["area_km2"] for s in salida), 1), "avisos": avisos, "fuente": prop["metodo"]}


def _cn_cuencas(destino, chicas, crs, progreso):
    """CN medio (AMC II) por cuenca con las tablas del proyecto (parametros_gee): WorldCover 30 m × textura OpenLandMap; huecos de textura por el vecino más próximo."""
    import rasterio
    from rasterio import features
    from rasterio.transform import from_origin
    from rasterio.warp import reproject, Resampling
    from scipy.ndimage import distance_transform_edt
    from . import parametros_gee as PG, gee_chirps as G, descargas as D
    b = chicas.to_crs(4326).total_bounds; bbox = [b[0] - .005, b[1] - .005, b[2] + .005, b[3] + .005]
    if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) > 1.2:
        raise D.DescargaError("Las cuencas chicas ocupan un área demasiado grande para pedir el uso de suelo de una vez: baja el área máxima.")
    info, ee = G.iniciar()
    if not info.get("autenticado"):
        raise D.DescargaError("Earth Engine no está conectado (módulo 2 · Datos / GEE): hace falta para el uso de suelo de las cuencas externas.")
    geom = ee.Geometry.Rectangle(bbox, proj="EPSG:4326", geodesic=False)
    PG._bajar_capa(ee.ImageCollection("ESA/WorldCover/v200").first().select("Map"), geom, 30, destino, "uso_suelo_worldcover_30m.tif", progreso, 0.6, 0.7, D)
    PG._bajar_capa(ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02").select("b0"), geom, 250, destino, "textura_suelo_openlandmap.tif", progreso, 0.7, 0.8, D)
    x0, y0, x1, y1 = chicas.total_bounds; x0 = math.floor(x0 / 30) * 30 - 60; y1 = math.ceil(y1 / 30) * 30 + 60; x1 += 60; y0 -= 60
    H, Wd = int((y1 - y0) / 30), int((x1 - x0) / 30); T30 = from_origin(x0, y1, 30, 30)

    def a30(ruta):
        with rasterio.open(ruta) as s:
            a = s.read(1, masked=True).astype("float32").filled(np.nan); d = np.full((H, Wd), np.nan, dtype=np.float32)
            reproject(a, d, src_transform=s.transform, src_crs=s.crs, dst_transform=T30, dst_crs=crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.nearest)
        return d
    wc = a30(destino / "uso_suelo_worldcover_30m.tif"); tx = a30(destino / "textura_suelo_openlandmap.tif")
    ok = np.isfinite(tx) & (tx >= 1) & (tx <= 12)
    if ok.any():
        _, idx = distance_transform_edt(~ok, return_indices=True, sampling=30); txl = tx.copy(); falta = ~ok & np.isfinite(wc); txl[falta] = tx[tuple(idx[:, falta])]
    else:
        txl = tx
    cn = np.full((H, Wd), np.nan, dtype=np.float32)
    for cover, vals in PG.CN.items():
        for t, gg in PG.HSG.items(): cn[(wc == cover) & (txl == t)] = vals[gg - 1]
    cn_k, cob_k = {}, {}
    for _, r in chicas.iterrows():
        m = features.rasterize([(r.geometry, 1)], out_shape=(H, Wd), transform=T30, fill=0, dtype="uint8").astype(bool)
        cob_k[int(r.id)] = float((m & np.isfinite(cn)).sum() / max(m.sum(), 1) * 100)
        if (m & np.isfinite(cn)).any():
            cn_k[int(r.id)] = float(np.nanmean(cn[m]))
    return cn_k, cob_k


def registrar_externas(carpeta, datos, deteccion, ids, permitir_fuera_de_cauce=False):
    """Copia al proyecto (cuenca/<marca>_ext_E<id>/cuenca.gpkg) las cuencas CHICAS elegidas y devuelve la lista para /api/corrida/cuencas_externas."""
    import geopandas as gpd
    d = Path(carpeta) / "datos_descargados" / str(deteccion)
    if not (d / "propuesta.json").exists():
        raise ValueError("No existe esa detección de cuencas externas en el proyecto.")
    prop = json.loads((d / "propuesta.json").read_text(encoding="utf-8")); g = gpd.read_file(d / "cuencas_externas_detectadas.gpkg")
    pedidas = {int(i) for i in ids}; por_id = {int(c["id"]): c for c in prop["cuencas"]}
    if not pedidas or not pedidas <= set(por_id):
        raise ValueError("Elige al menos una cuenca de la lista detectada.")
    marca = datetime.now().strftime("%Y%m%d_%H%M%S"); lista = []
    for i in sorted(pedidas):
        c = por_id[i]
        if c["tipo"] != "chica":
            raise ValueError(f"E{i} es una cuenca grande ({c['area_km2']} km²): úsala como entrada GEOGLOWS, no con SCS-CN.")
        if c.get("cn") is None or c.get("lag_h") is None:
            raise ValueError(f"E{i} no tiene CN o lag: no se puede usar.")
        if not c["en_cauce"] and not permitir_fuera_de_cauce:
            raise ValueError(f"La entrada de E{i} no pasa la comprobación de cauce ({'; '.join(c['advertencias_entrada'])}). Si decides usarla, marca «permitir bajo mi responsabilidad».")
        nom = f"{marca}_ext_E{i}"; dc = Path(carpeta) / "cuenca" / nom; dc.mkdir(parents=True, exist_ok=False)
        g[g.id == i][["id", "geometry"]].assign(origen="externa_auto_D8_lambda92").to_file(dc / "cuenca.gpkg", driver="GPKG")
        lista.append({"nombre": c["nombre"], "cuenca": nom, "cn": c["cn"], "lag_h": c["lag_h"], "prf": 484, "entrada_xy": c["entrada_xy"],
                      "fuente": f"detección automática {deteccion}: D8 sobre MDT amplio, {c['area_km2']} km², CN tablas WorldCover × OpenLandMap AMC II ({c['cobertura_cn_pct']} % con cobertura), "
                                f"lag NEH-630 (L {c['L_m']} m, pendiente {c['pendiente_pct']} %), entrada ajustada {c['desplazamiento_m']} m al cauce; no calibrado"})
    return lista


# ------------------------------------------------------------------------------------------------ GEOGLOWS · río grande sin datos
def _http(url, params=None, timeout=120, intentos=3):
    import requests
    ultimo = ""
    for k in range(intentos):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            ultimo = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            ultimo = str(e)[:200]
        time.sleep(2 + 2 * k)
    from .descargas import DescargaError
    raise DescargaError("GEOGLOWS no respondió (" + ultimo + "). Revisa tu internet y vuelve a intentarlo.")


def tramos_cercanos(lon, lat, paso=0.01):
    """Tramos GEOGLOWS alrededor de un punto (rejilla 3×3) con su caudal medio anual: el de mayor caudal suele ser el río principal."""
    pts = [(round(lat + a * paso, 4), round(lon + b * paso, 4)) for a in (-1, 0, 1) for b in (-1, 0, 1)]

    def rid(pt):
        try:
            return int(_http(GEO + "getriverid", {"lat": pt[0], "lon": pt[1]}, 60, 2).json()["river_id"])
        except Exception:
            return None
    with ThreadPoolExecutor(5) as ex:
        ids = {i for i in ex.map(rid, pts) if i}
    out = []
    for i in ids:
        try:
            js = _http(GEO + f"annualaverages/{i}", {"format": "json"}, 120, 2).json()
            v = [float(x) for x in (js.get(str(i)) or []) if x is not None] if isinstance(js, dict) else []
            out.append({"river_id": i, "caudal_medio_anual_m3s": round(float(np.mean(v)), 2) if v else None})
        except Exception:
            out.append({"river_id": i, "caudal_medio_anual_m3s": None})
    return sorted(out, key=lambda c: -(c["caudal_medio_anual_m3s"] or -1))


def fuente_geoglows_entrada(destino, p, progreso):
    """Analiza el tramo GEOGLOWS de cada entrada pedida (serie horaria 1940-hoy → Gumbel y forma media de crecida). No registra nada."""
    import pandas as pd
    from pyproj import Transformer
    from climanet import entradas_geoglows as EG
    from .descargas import DescargaError
    carpeta, datos, cfg = _proyecto(p)
    pedidas = p.get("entradas") or []
    if not pedidas or len(pedidas) > 6:
        raise DescargaError("Indica entre 1 y 6 entradas (nombre y coordenadas x, y del área 2D).")
    aoi = cfg.get("aoi") or []
    tf = Transformer.from_crs(datos["crs"], "EPSG:4326", always_xy=True); res = []
    for k, e in enumerate(pedidas):
        x, y = [float(v) for v in e["xy"]]
        if len(aoi) == 4 and not (aoi[0] <= x <= aoi[1] and aoi[2] <= y <= aoi[3]):
            raise DescargaError(f"La entrada {e.get('nombre')} ({x:.0f}, {y:.0f}) queda fuera del área del modelo.")
        lon, lat = tf.transform(x, y); f0 = k / len(pedidas); f1 = (k + 1) / len(pedidas)
        cand = []
        if e.get("river_id"):
            rid = int(e["river_id"]); origen = "tramo indicado por la persona"
        else:
            progreso(f0 + 0.05 * (f1 - f0), f"{e.get('nombre')}: buscando el tramo GEOGLOWS")
            cand = tramos_cercanos(lon, lat)
            if not cand:
                raise DescargaError(f"GEOGLOWS no tiene tramos cerca de {e.get('nombre')}.")
            rid = cand[0]["river_id"]; origen = "tramo de MAYOR caudal medio a ≤ ~1 km de la entrada (revísalo: puede no ser el río que entra)"
        progreso(f0 + 0.2 * (f1 - f0), f"{e.get('nombre')}: bajando la serie horaria del tramo {rid} (~25 MB, 1 min)")
        r = _http(GEO + f"retrospectivehourly/{rid}", {"format": "csv"}, 600)
        f = destino / f"geoglows_horario_{rid}.csv"; f.write_bytes(r.content)
        s = pd.read_csv(f, parse_dates=[0])
        progreso(f0 + 0.8 * (f1 - f0), f"{e.get('nombre')}: máximos anuales, Gumbel y forma de crecida")
        a = EG.analizar_serie(s.iloc[:, 0].dt.tz_localize(None) if s.iloc[:, 0].dt.tz is not None else s.iloc[:, 0], s.iloc[:, 1].values)
        res.append({"nombre": str(e.get("nombre") or f"rio_{k + 1}"), "xy": [x, y], "lonlat": [round(lon, 5), round(lat, 5)], "river_id": rid, "origen_tramo": origen,
                    "candidatos": cand, "archivo": f.name, **a})
    (destino / "analisis_geoglows.json").write_text(json.dumps({"entradas": res, "aviso": "GEOGLOWS v2 (ECMWF): simulación de un modelo global, no observación. No calibrado."},
                                                               ensure_ascii=False, indent=1), encoding="utf-8")
    return {"archivos": ["analisis_geoglows.json"] + [x["archivo"] for x in res],
            "entradas": [{k: x[k] for k in ("nombre", "river_id", "origen_tramo", "tabla_tr_m3s", "caudal_medio_m3s", "inicio", "fin")} | {"n_anios": x["gumbel"]["n_anios"]} for x in res],
            "fuente": "GEOGLOWS v2 retrospectivo horario (ECMWF ERA5 + modelo hidrológico global)",
            "nota": "Pico de diseño = Gumbel por momentos de los máximos horarios anuales; forma = media de las crecidas anuales. Referencia externa, no observación."}


def registrar_geoglows(carpeta, analisis, nombres):
    """Entradas GEOGLOWS elegidas → lista para cfg['entradas_geoglows'] (sin la serie: solo Gumbel, forma y procedencia)."""
    d = Path(carpeta) / "datos_descargados" / str(analisis)
    if not (d / "analisis_geoglows.json").exists():
        raise ValueError("No existe ese análisis GEOGLOWS en el proyecto.")
    a = json.loads((d / "analisis_geoglows.json").read_text(encoding="utf-8"))["entradas"]
    pedidas = set(nombres or [x["nombre"] for x in a]); lista = []
    for x in a:
        if x["nombre"] in pedidas:
            lista.append({"nombre": x["nombre"], "xy": x["xy"], "river_id": x["river_id"], "gumbel": x["gumbel"], "forma": x["forma"], "tabla_tr_m3s": x["tabla_tr_m3s"],
                          "fuente": f"GEOGLOWS v2 retrospectivo horario {x['inicio'][:10]} a {x['fin'][:10]}, tramo {x['river_id']} ({x['origen_tramo']}); análisis {analisis}; no calibrado"})
    if not lista:
        raise ValueError("Ninguna de las entradas pedidas está en ese análisis.")
    return lista
