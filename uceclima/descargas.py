# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Descargas REPRODUCIBLES de datos externos para un proyecto (como en un equipo recién instalado): CHIRPS (Earth Engine), GEOGLOWS (caudal reanalizado) y series de CELEC.
Reglas: una descarga a la vez; cada descarga va a una carpeta NUEVA con marca de tiempo (nunca sobrescribe); cada una deja un manifiesto (fuente, parámetros, fecha UTC, versión,
SHA-256) y un estado legible; sin credenciales en disco (Earth Engine usa las del sistema); los datos faltantes quedan vacíos (nunca 0); consultas pequeñas y por trozos.
CMIP6 NO se descarga aquí: el cambio climático está bloqueado hasta calibrar y validar la línea base (ver MODULO_CMIP6.md). Un sitio nuevo se crea y se descarga de forma automática con la fuente «sitio»."""
import hashlib, json, math, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd


class DescargaError(ValueError):
    pass


MENSAJE_FUERA = ("El punto está fuera de la cobertura de CHIRPS (latitud −50…50). UCEclima Lambda admite cualquier sitio dentro de esa franja "
                 "(Ecuador, España, resto de América, África, Asia…); NEX-GDDP-CMIP6 y Copernicus GLO-30 son globales.")


def punto_admitido(lon, lat):
    """Zeta Z1: cualquier punto con CHIRPS (latitud −50…50, longitud −180…180). Antes: Omega solo Ecuador; la copia España añadía la península."""
    return -180 <= lon <= 180 and -50 < lat < 50


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------------------------------------ CHIRPS (Earth Engine)
CHIRPS_V2 = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_V3 = "UCSB-CHG/CHIRPS/V3/DAILY_SAT"


def chirps_gee(destino, p, progreso):
    from . import gee_chirps as G
    lon, lat = float(p["lon"]), float(p["lat"]); ini, fin = pd.Timestamp(p["inicio"]), pd.Timestamp(p["fin"])
    caja = float(p.get("caja_deg", 0.45))
    if not punto_admitido(lon, lat):
        raise DescargaError(MENSAJE_FUERA)
    if (fin - ini).days > 366 * 50:
        raise DescargaError("Pide como máximo 50 años por descarga.")
    info, ee = G.iniciar()
    if not info.get("autenticado"):
        raise DescargaError("Earth Engine no está conectado: abre el módulo «Datos / GEE», escribe tu proyecto de Google Cloud, pulsa «Autorizar» y luego «Inicializar y verificar». (" + str(info.get("error"))[:120] + ")")
    asset, nota_version = CHIRPS_V3, "CHIRPS v3 (DAILY_SAT)"
    try:
        ee.ImageCollection(CHIRPS_V3).size().getInfo()
    except Exception:
        asset, nota_version = CHIRPS_V2, "CHIRPS v2 (la v3 no está disponible en esta cuenta; no se mezclan versiones)"
    banda = "precipitation"
    pto = ee.Geometry.Point([lon, lat]); rect = ee.Geometry.Rectangle([lon - caja, lat - caja, lon + caja, lat + caja])
    x0, y0 = math.floor(lon / 0.25) * 0.25, math.floor(lat / 0.25) * 0.25                                   # celda de 0,25° de la malla NEX-GDDP-CMIP6 que contiene el punto (bordes en múltiplos de 0,25°)
    celda = ee.Geometry.Rectangle([x0, y0, x0 + 0.25, y0 + 0.25])
    filas = []
    anios = list(range(ini.year, fin.year + 1))
    for k, y in enumerate(anios):
        a = max(ini, pd.Timestamp(y, 1, 1)); b = min(fin, pd.Timestamp(y, 12, 31))
        col = ee.ImageCollection(asset).filterDate(a.strftime("%Y-%m-%d"), (b + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        f = col.map(lambda im: ee.Feature(None, {"t": im.date().format("YYYY-MM-dd"), "p": im.select(banda).reduceRegion(ee.Reducer.first(), pto, 5566).get(banda),
                                                 "m": im.select(banda).reduceRegion(ee.Reducer.mean(), rect, 5566).get(banda),
                                                 "c": im.select(banda).reduceRegion(ee.Reducer.mean(), celda, 5566).get(banda)}))
        for intento in range(3):
            try:
                feats = f.getInfo()["features"]; break
            except Exception as e:
                if intento == 2:
                    raise DescargaError(f"Earth Engine falló en {y}: {str(e)[:160]}") from e
                time.sleep(3)
        filas += [(x["properties"]["t"], x["properties"].get("p"), x["properties"].get("m"), x["properties"].get("c")) for x in feats]
        progreso((k + 1) / len(anios), f"CHIRPS {y}")
    df = pd.DataFrame(filas, columns=["fecha", "pixel_mm", "media_caja_mm", "celda_nex_mm"]).drop_duplicates("fecha").sort_values("fecha")
    esperados = len(pd.date_range(ini, fin)); falt = esperados - len(df)
    df.to_csv(destino / "chirps_diario.csv", index=False)
    graficos = []
    try:                                                                                                    # gráficos y tendencias dentro de la misma carpeta (la del proyecto)
        from . import chirps_salidas
        graficos = ["graficos/" + n for n in chirps_salidas.generar(destino)]
    except Exception as e:
        graficos = [f"(no se pudieron generar los gráficos: {str(e)[:120]})"]
    return {"archivos": ["chirps_diario.csv"] + graficos, "fuente": asset, "version": nota_version, "n_dias": int(len(df)), "dias_esperados": int(esperados), "dias_faltantes_en_origen": int(falt),
            "periodo": [df["fecha"].min(), df["fecha"].max()], "punto": [lon, lat], "caja_deg": caja, "ee_api": info.get("api"),
            "celda_nex": [x0, y0, x0 + 0.25, y0 + 0.25], "nota": "pixel_mm = píxel de 0,05° que contiene el punto; media_caja_mm = media de la caja ±caja_deg; celda_nex_mm = media de la celda de 0,25° de NEX-GDDP que contiene el punto. Días sin imagen quedan ausentes. Es lluvia estimada por satélite, no una medición."}



# ------------------------------------------------------------------------------------------------ MDT (Copernicus GLO-30 vía Earth Engine)
def utm_epsg(lon, lat):
    zona = int((lon + 180) // 6) + 1
    return (32700 if lat < 0 else 32600) + zona


def mdt_gee(destino, p, progreso):
    """Descarga un MDT de 30 m (Copernicus GLO-30) alrededor de un punto, en UTM y en metros. GLO-30 es un modelo de SUPERFICIE (DSM): incluye vegetación y construcciones."""
    import requests
    from . import gee_chirps as G
    lon, lat = float(p["lon"]), float(p["lat"]); medio = float(p.get("medio_km", 20.0))
    if p.get("ambito") == "cuenca":                                                    # extensión de la cuenca activa + margen (C1)
        from .cuenca import extension_activa
        ext = extension_activa(p["proyecto"], "EPSG:4326")
        if not ext:
            raise DescargaError("No hay cuenca activa (módulo 6 · hidro): usa el ámbito «sitio» o activa una cuenca.")
        x0, y0, x1, y1 = ext["lonlat"]; lon, lat = (x0 + x1) / 2, (y0 + y1) / 2
        medio = max((x1 - x0) * 111.32 * np.cos(np.radians(lat)), (y1 - y0) * 110.57) / 2 + 3.0
        if medio > 30:
            raise DescargaError(f"La cuenca mide {2 * medio:.0f} km de lado: excede el MDT de 30 m (máx. 60 km). Usa el MDT amplio del módulo hidro · Cuenca.")
        p["lon"], p["lat"], p["medio_km"] = lon, lat, round(medio, 2)
    if not punto_admitido(lon, lat):
        raise DescargaError(MENSAJE_FUERA)
    if not (1 <= medio <= 30):
        raise DescargaError("El MDT debe tener entre 2 y 60 km de lado (medio_km entre 1 y 30).")
    info, ee = G.iniciar()
    if not info.get("autenticado"):
        raise DescargaError("Earth Engine no está autorizado en este equipo (usa «Autorizar Earth Engine»). " + str(info.get("error"))[:120])
    epsg = utm_epsg(lon, lat)
    dlat = medio / 110.57; dlon = medio / (111.32 * np.cos(np.radians(lat)))
    region = ee.Geometry.Rectangle([lon - dlon, lat - dlat, lon + dlon, lat + dlat])
    if (p.get("producto") or "glo30") == "fabdem":                               # Omega O1
        return _fabdem(destino, p, progreso, ee, region, epsg, lon, lat, medio)
    col = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("DEM")
    img = col.mosaic().setDefaultProjection(col.first().projection()).clip(region)
    progreso(0.2, "pidiendo el MDT a Earth Engine")
    try:
        url = img.getDownloadURL({"region": region, "scale": 30, "crs": f"EPSG:{epsg}", "format": "GEO_TIFF"})
    except Exception as e:
        raise DescargaError("Earth Engine rechazó la petición del MDT: " + str(e)[:200]) from e
    r = requests.get(url, timeout=300)
    if r.status_code != 200 or len(r.content) < 2000:
        raise DescargaError(f"Falló la descarga del MDT (HTTP {r.status_code}) Earth Engine dijo: " + (r.text or "")[:300].replace("\n", " ") + ". Si el área es muy grande (más de unos 200 km de lado a 90 m), baja la resolución o el tamaño.")
    contenido = r.content
    if contenido[:2] == b"PK":                                                  # a veces llega comprimido
        import io, zipfile
        z = zipfile.ZipFile(io.BytesIO(contenido)); nombre = next(n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))); contenido = z.read(nombre)
    f = destino / f"mdt_glo30_{int(medio * 2)}km_utm{epsg}.tif"; f.write_bytes(contenido)
    progreso(0.8, "verificando el MDT")
    from .terreno_import import inspeccionar
    ins = inspeccionar(str(f))
    return {"archivos": [f.name], "fuente": "Copernicus GLO-30 (COPERNICUS/DEM/GLO30_2024_1, sustituye al activo GLO30 obsoleto) vía Earth Engine", "crs": ins["crs"], "res_m": ins["res_m"], "tipo_terreno_sugerido": "DSM",
            "datum_vertical": "EGM2008 (geoide) según Copernicus GLO-30; no verificado localmente", "validas_pct": ins["validas_pct"], "z_min": ins["z_min"], "z_max": ins["z_max"],
            "extension": ins["extension"], "avisos": ins["avisos"], "punto": [lon, lat], "medio_km": medio,
            "nota": "MDT global de 30 m: es un DSM (incluye vegetación y construcciones) y su exactitud vertical es de varios metros. Sirve para delimitar y explorar; para inundación fina conviene un MDT de dron/LiDAR."}


def _fabdem(destino, p, progreso, ee, region, epsg, lon, lat, medio):
    """FABDEM v1-2 (projects/sat-io/open-datasets/FABDEM): Copernicus GLO-30 con bosques y edificios quitados (Hawker et al. 2022, Environ. Res. Lett. 17 024016).
    Método A: descarga en UTM a 30 m SIN .resample() en Earth Engine (con .resample() GEE devolvió DEM plausibles pero equivocados o constantes: Machala y Milagro, sep-2026).
    Se valida contra la media calculada en el servidor sobre la rejilla nativa. Método B (respaldo): EPSG:4326 nativo + bilinear local a la rejilla UTM.
    Licencia CC BY-NC-SA 4.0 (uso no comercial)."""
    import io, zipfile, requests, rasterio
    from rasterio.warp import reproject, Resampling
    ic = ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").filterBounds(region)
    if ic.size().getInfo() == 0:
        raise DescargaError("FABDEM no tiene teselas en esa zona.")
    progreso(0.1, "media de referencia de FABDEM en el servidor (rejilla nativa)")
    ref = float(list(ic.mosaic().select(0).reduceRegion(ee.Reducer.mean(), region, 30, maxPixels=1e9).getInfo().values())[0])
    def bajar(params):
        r = requests.get(ic.mosaic().select(0).getDownloadURL(params), timeout=600)
        if r.status_code != 200 or len(r.content) < 2000:
            raise DescargaError(f"Falló la descarga de FABDEM (HTTP {r.status_code}) Earth Engine dijo: " + (r.text or "")[:300].replace("\n", " ") + ". Si el área es muy grande (más de unos 200 km de lado a 90 m), baja la resolución o el tamaño.")
        c = r.content
        if c[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(c)); c = z.read(next(n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))))
        return c
    def ok_(a):
        v = np.isfinite(a) & (a > -100)
        return bool(v.mean() > 0.9 and a[v].std() > 0.05 and abs(a[v].mean() - ref) < 5.0), v
    f = destino / f"mdt_fabdem_{int(medio * 2)}km_utm{epsg}.tif"; metodo = "A (UTM sin remuestreo en GEE)"
    progreso(0.3, "pidiendo FABDEM a Earth Engine (método A)")
    f.write_bytes(bajar({"region": region, "scale": 30, "crs": f"EPSG:{epsg}", "format": "GEO_TIFF"}))
    with rasterio.open(f) as s:
        a = s.read(1).astype("float64"); bueno, v = ok_(a); meta = s.profile; T = s.transform; W, H = s.width, s.height
    if not bueno:
        progreso(0.5, "método A no pasó la verificación: método B (EPSG:4326 nativo + bilinear local)")
        tmp = destino / "_fabdem_4326.tif"; tmp.write_bytes(bajar({"region": region.buffer(500), "scale": 30, "crs": "EPSG:4326", "format": "GEO_TIFF"}))
        with rasterio.open(tmp) as s:
            b = s.read(1).astype("float64"); bueno, v = ok_(b)
            if not bueno:
                tmp.unlink(missing_ok=True); f.unlink(missing_ok=True)
                raise DescargaError("FABDEM llegó constante o inválido también con el método B (hueco de tesela): no se usa. Usa GLO-30 con el filtro de picos o un MDT de dron/LiDAR.")
            dst = np.full((H, W), np.nan, "float32")
            reproject(b.astype("float32"), dst, src_transform=s.transform, src_crs=s.crs, dst_transform=T, dst_crs=f"EPSG:{epsg}", resampling=Resampling.bilinear, dst_nodata=np.nan)
        tmp.unlink(missing_ok=True); meta.update(dtype="float32", nodata=-9999.0)
        with rasterio.open(f, "w", **meta) as d:
            d.write(np.where(np.isfinite(dst), dst, -9999.0).astype("float32"), 1)
        metodo = "B (EPSG:4326 nativo + bilinear local)"
    progreso(0.8, "verificando el MDT")
    from .terreno_import import inspeccionar
    ins = inspeccionar(str(f))
    return {"archivos": [f.name], "fuente": "FABDEM v1-2 (projects/sat-io/open-datasets/FABDEM) vía Earth Engine · Hawker et al. 2022 · CC BY-NC-SA 4.0", "producto": "fabdem",
            "metodo_descarga": metodo, "media_servidor_m": round(ref, 2), "crs": ins["crs"], "res_m": ins["res_m"], "tipo_terreno_sugerido": "MDT",
            "datum_vertical": "EGM2008 (geoide), heredado de Copernicus GLO-30; no verificado localmente", "validas_pct": ins["validas_pct"], "z_min": ins["z_min"], "z_max": ins["z_max"],
            "extension": ins["extension"], "avisos": ins["avisos"], "punto": [lon, lat], "medio_km": medio,
            "nota": "FABDEM: GLO-30 con bosques y edificios quitados por aprendizaje automático (Hawker et al. 2022). Es un MDT de suelo desnudo ESTIMADO, no medido; licencia no comercial."}


# ------------------------------------------------------------------------------------------------ GEOGLOWS
GEO = "https://geoglows.ecmwf.int/api/v2/"


def geoglows(destino, p, progreso):
    import requests
    lat, lon = float(p["lat"]), float(p["lon"]); paso = float(p.get("paso_deg", 0.02)); n = int(p.get("n_pasos", 2)); max_tramos = int(p.get("max_tramos", 6))
    nota_salida = "sitio del proyecto"; area_cuenca = None
    if p.get("ambito") == "cuenca":                                                    # C2: el tramo se busca en la SALIDA de la cuenca activa
        act = Path(p["proyecto"]) / "cuenca" / "activa.json"
        if not act.exists():
            raise DescargaError("No hay cuenca activa: elige el ámbito «sitio» o activa una cuenca.")
        a = json.loads(act.read_text(encoding="utf-8")); area_cuenca = a.get("area_km2")
        rj = json.loads((Path(p["proyecto"]) / a["carpeta"] / "resumen.json").read_text(encoding="utf-8"))
        if rj.get("salida_ajustada_lonlat"):
            lon, lat = rj["salida_ajustada_lonlat"]; nota_salida = "salida de la cuenca delineada"
        elif p.get("salida_lon") not in (None, "") and p.get("salida_lat") not in (None, ""):
            lon, lat = float(p["salida_lon"]), float(p["salida_lat"]); nota_salida = "salida (aforo) indicada"
        else:
            import geopandas as gpd
            c_ = gpd.read_file(Path(p["proyecto"]) / a["carpeta"] / "cuenca.gpkg").to_crs(4326).geometry.unary_union.representative_point()
            lon, lat = c_.x, c_.y; nota_salida = "punto interior de la cuenca (no se conoce la salida: indica el aforo)"
        paso, n = 0.005, 3
    offs = [k * paso for k in range(-n, n + 1)]
    puntos = [(round(lat + a, 4), round(lon + b, 4)) for a in offs for b in offs]

    def rid(pt):
        for _ in range(3):
            try:
                r = requests.get(GEO + "getriverid", params={"lat": pt[0], "lon": pt[1]}, timeout=60)
                if r.status_code == 200 and "river_id" in r.json():
                    return pt, int(r.json()["river_id"])
            except Exception:
                time.sleep(2)
        return pt, None
    with ThreadPoolExecutor(5) as ex:
        res = list(ex.map(rid, puntos))
    cand = {}
    for pt, r in res:
        if r is not None:
            d = np.hypot((pt[0] - lat) * 111.0, (pt[1] - lon) * 111.0)
            cand[r] = min(cand.get(r, 1e9), d)
    if not cand:
        raise DescargaError("GEOGLOWS no devolvió ningún tramo de río para ese punto.")
    ids = sorted(cand, key=cand.get)[:max_tramos]
    progreso(0.2, f"{len(cand)} tramos candidatos; descargando {len(ids)}")
    filas, arch = [], []

    def serie(i):
        for _ in range(3):
            try:
                r = requests.get(GEO + f"retrospectivedaily/{i}", params={"format": "csv"}, timeout=180)
                if r.status_code == 200 and len(r.content) > 1000:
                    return i, r.text
            except Exception:
                time.sleep(3)
        return i, None
    with ThreadPoolExecutor(3) as ex:
        for k, (i, txt) in enumerate(ex.map(serie, ids)):
            if txt is None:
                filas.append({"river_id": i, "distancia_km": round(cand[i], 2), "estado": "falló"}); continue
            f = destino / f"geoglows_{i}.csv"; f.write_text(txt, encoding="utf-8"); arch.append(f.name)
            s = pd.read_csv(f, parse_dates=[0]); v = s.iloc[:, 1]
            filas.append({"river_id": i, "distancia_km": round(cand[i], 2), "inicio": str(s.iloc[0, 0])[:10], "fin": str(s.iloc[-1, 0])[:10], "dias": int(len(s)), "caudal_medio_m3s": round(float(v.mean()), 2),
                          "caudal_max_m3s": round(float(v.max()), 1), "estado": "ok"})
            progreso(0.2 + 0.8 * (k + 1) / len(ids), f"tramo {i}")
    if p.get("rios_geoglows"):                                                        # área de drenaje DSContArea desde la capa de ríos GEOGLOWS v2 del usuario
        try:
            import geopandas as gpd
            rg = gpd.read_file(p["rios_geoglows"], ignore_geometry=True)
            col_id = next(c for c in rg.columns if c.lower() in ("linkno", "river_id", "comid"))
            col_a = next(c for c in rg.columns if c.lower() == "dscontarea")
            for f_ in filas:
                fila = rg[rg[col_id].astype("int64") == int(f_["river_id"])]
                if len(fila):
                    v = float(fila[col_a].iloc[0]); km2 = v / 1e6 if v > 1e5 else v
                    f_["area_drenaje_km2"] = round(km2, 2)
                    if area_cuenca:
                        f_["diferencia_area_pct"] = round(100 * (area_cuenca / km2 - 1), 1)
        except Exception as e:
            filas.append({"aviso": f"No se pudo leer DSContArea de la capa GEOGLOWS: {str(e)[:120]}"})
    pd.DataFrame(filas).to_csv(destino / "candidatos.csv", index=False)
    return {"archivos": arch + ["candidatos.csv"], "fuente": "GEOGLOWS v2 (ECMWF) retrospectivo diario", "tramos": filas, "punto": [lon, lat], "referencia_busqueda": nota_salida, "area_cuenca_km2": area_cuenca,
            "nota": "Caudal REANALIZADO (modelo), no medido. " + ("Tramos ordenados por cercanía a la " + nota_salida + "." if p.get("ambito") == "cuenca" else "Tramos por cercanía al sitio.")
                    + (" El área de drenaje (DSContArea) se compara con la del polígono." if p.get("rios_geoglows") else " La API de GEOGLOWS no da el área de drenaje: indica la capa de ríos GEOGLOWS v2 (VPU) para compararla.")}


# ------------------------------------------------------------------------------------------------ CELEC SUR (Mazar)
CELEC = "https://generacioncsr.celec.gob.ec:8443/ords/csr/sardomcsr/"
CELEC_VARS = {"cota_msnm": 30031, "caudal_m3s": 30538}


def celec(destino, p, progreso):
    import requests, urllib3
    urllib3.disable_warnings()
    ini, fin = pd.Timestamp(p["inicio"]), pd.Timestamp(p["fin"])
    meses = pd.date_range(ini.replace(day=1), fin, freq="MS")
    tareas = [(n, m, a) for n, m in CELEC_VARS.items() for a in meses]

    def pedir(t):
        n, m, a = t
        pr = {"mrid": m, "fechaInicio": a.strftime("%Y-%m-%dT00:00:00.000Z"), "fechaFin": (fin + pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z"), "fecha": a.strftime("%d/%m/%Y 00:00:00")}
        for _ in range(4):
            try:
                return n, requests.get(CELEC + "pointValuesMesAvg", params=pr, verify=False, timeout=120).json().get("items", [])
            except Exception:
                time.sleep(2)
        return n, None
    datos, fallos = {n: [] for n in CELEC_VARS}, 0
    with ThreadPoolExecutor(4) as ex:
        for k, (n, items) in enumerate(ex.map(pedir, tareas)):
            if items is None:
                fallos += 1
            else:
                datos[n] += items
            if k % 20 == 0:
                progreso((k + 1) / len(tareas), f"CELEC {k + 1}/{len(tareas)}")
    cols = []
    for n, items in datos.items():
        d = pd.DataFrame(items)
        if d.empty:
            continue
        d["f"] = pd.to_datetime(d["loctimestamp"]).dt.tz_convert("America/Guayaquil").dt.tz_localize(None).dt.floor("D")
        cols.append(d.dropna(subset=["valueedit"]).drop_duplicates("f").set_index("f")["valueedit"].sort_index().rename(n))
    if not cols:
        raise DescargaError("CELEC no devolvió datos para ese periodo.")
    df = pd.concat(cols, axis=1).sort_index(); df = df[(df.index >= ini) & (df.index <= fin)]; df.index.name = "fecha"
    df.to_csv(destino / "celec_mazar_diario.csv")
    return {"archivos": ["celec_mazar_diario.csv"], "fuente": "CELEC SUR · generacioncsr.celec.gob.ec (mrid cota 30031, caudal 30538)", "n_dias": int(len(df)), "con_dato": df.notna().sum().to_dict(),
            "periodo": [str(df.index.min().date()), str(df.index.max().date())], "solicitudes_fallidas": fallos,
            "nota": "Medias diarias de los valores publicados. Fecha en hora local de Ecuador. El significado exacto de la variable «caudal» (afluente, turbinado…) NO está confirmado. "
                    "Puede traer fallas de sensor (picos absurdos): se conservan sin corregir y deben depurarse en el premódulo. El servidor no presenta un certificado verificable (la conexión se hace sin verificar)."}




CONTEXTO = {}                                           # ganchos que pone el servidor (p. ej. registrar el MDT en el proyecto abierto justo después de bajarlo)


def cn_manning(destino, p, progreso):
    from .parametros_gee import cn_manning_gee
    return cn_manning_gee(destino, p, progreso)


def suelo(destino, p, progreso):
    from .parametros_gee import suelo_gee
    return suelo_gee(destino, p, progreso)


def otras(destino, p, progreso):
    from .capas_gee import otras_gee
    return otras_gee(destino, p, progreso)


def sitio(destino, p, progreso):
    """Todo lo que se trae automáticamente para un sitio, siempre desde Earth Engine y servicios públicos: MDT → (se registra) → CN y Manning → CHIRPS → GEOGLOWS → (opcional) CELEC.
    Cada paso va en su subcarpeta; si uno falla, los demás siguen y queda anotado. Si el proyecto ya trae CN/Manning detallados, los suyos tienen prioridad."""
    pasos = [("mdt", mdt_gee, {"lon": p["lon"], "lat": p["lat"], "medio_km": p.get("medio_km", 20)}),
             ("suelo", suelo, {"proyecto": p["proyecto"], "lon": p["lon"], "lat": p["lat"], "medio_km": p.get("medio_km", 20)}),
             ("cn_manning", cn_manning, {"proyecto": p["proyecto"]}),
             ("chirps", chirps_gee, {"lon": p["lon"], "lat": p["lat"], "inicio": p["inicio"], "fin": p["fin"], "caja_deg": p.get("caja_deg", 0.45)}),
             ("geoglows", geoglows, {"lon": p["lon"], "lat": p["lat"]})]
    if p.get("celec"):
        pasos.append(("celec", celec, {"inicio": p.get("celec_inicio") or p["inicio"], "fin": p["fin"]}))
    resultados, archivos = {}, []
    for k, (nombre, fn, pp) in enumerate(pasos):
        sub = destino / nombre; sub.mkdir()
        progreso(k / len(pasos), f"{nombre} ({k + 1}/{len(pasos)})")
        if nombre in ("cn_manning", "suelo") and resultados.get("mdt", {}).get("estado") != "ok":
            resultados[nombre] = {"estado": "fallo", "error": "sin MDT registrado no hay malla: se omite"}; continue
        if nombre == "cn_manning" and resultados.get("suelo", {}).get("estado") != "ok":
            resultados[nombre] = {"estado": "fallo", "error": "sin las capas de uso de suelo y suelo no se calculan CN y Manning: se omite"}; continue
        try:
            r = fn(sub, pp, lambda f, m, k=k: progreso((k + float(f)) / len(pasos), f"{nombre}: {m}"))
            (sub / "manifiesto.json").write_text(json.dumps({"fuente_id": nombre, "creado_utc": _ahora(), "parametros": pp, **r, "sha256": {a: _sha(sub / a) for a in r.get("archivos", []) if (sub / a).exists()}}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            resultados[nombre] = {"estado": "ok", **{kk: r[kk] for kk in ("n_dias", "periodo", "version", "crs", "res_m", "validas_pct", "tramos", "nota", "tipo_terreno_sugerido", "datum_vertical", "extension",
                                                                         "cobertura_parametros_pct", "suelo_estimado_pct", "cn_min_max_media", "manning_min_max_media", "registro") if kk in r}}
            archivos += [f"{nombre}/{a}" for a in r.get("archivos", [])]
            if nombre == "mdt" and CONTEXTO.get("tras_mdt"):
                try:
                    CONTEXTO["tras_mdt"](destino, p)
                except BaseException as e:
                    resultados[nombre]["registro"] = {"estado": "fallo", "texto": "No se pudo registrar el MDT en el proyecto: " + str(e)[:200]}; resultados["mdt"]["estado"] = "fallo"
        except BaseException as e:
            (sub / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            resultados[nombre] = {"estado": "fallo", "error": str(e)[:300]}
    return {"archivos": archivos, "fuente": "descarga automática del sitio", "pasos": resultados, "punto": [p["lon"], p["lat"]],
            "nota": "CMIP6 no se descarga: está bloqueado hasta calibrar y validar la línea base."}


FUENTES = {"sitio": sitio, "suelo": suelo, "otras": otras, "cn_manning": cn_manning, "mdt": mdt_gee, "chirps": chirps_gee, "geoglows": geoglows, "celec": celec}


# ------------------------------------------------------------------------------------------------ gestor (una descarga a la vez)
class GestorDescargas:
    def __init__(self):
        self.hilo = None; self.actual = None; self.lock = threading.Lock(); self.hook = None; self._cancelar = False

    def activa(self):
        return bool(self.hilo and self.hilo.is_alive())

    def iniciar(self, carpeta_proyecto, fuente, params, al_terminar=None):
        if fuente not in FUENTES:
            raise DescargaError("Fuente no disponible. " + ("CMIP6 está bloqueado hasta calibrar y validar la línea base." if "cmip" in str(fuente).lower() else "Opciones: " + ", ".join(FUENTES)))
        with self.lock:
            if self.activa():
                raise DescargaError("Ya hay una descarga en curso: se hace una a la vez.")
            marca = f"{datetime.now():%Y%m%d_%H%M%S}"
            destino = Path(carpeta_proyecto) / "datos_descargados" / f"{fuente}_{marca}"
            if destino.exists():
                raise DescargaError("La carpeta de descarga ya existe; no se sobrescribe.")
            destino.mkdir(parents=True)
            params = {**params, "proyecto": str(carpeta_proyecto)}; self._cancelar = False
            self.actual = {"id": destino.name, "fuente": fuente, "destino": str(destino)}
            (destino / "estado.json").write_text(json.dumps({"estado": "en_curso", "progreso": 0.0, "mensaje": "Iniciando", "inicio": _ahora(), "parametros": params}, ensure_ascii=False), encoding="utf-8")
            self.hilo = threading.Thread(target=self._correr, args=(destino, fuente, params, al_terminar), daemon=True); self.hilo.start()
            return destino.name

    def cancelar(self):
        """Pide cancelar la descarga en curso: se detiene en el próximo aviso de progreso (como máximo ~90 s si está esperando a Earth Engine)."""
        if self.activa():
            self._cancelar = True
            return True
        return False

    def _estado(self, destino, **kw):
        p = destino / "estado.json"; e = dict(kw)
        for k in range(60 if "estado" in kw else 10):                  # en Windows la interfaz puede estar leyéndolo: se reintenta
            try:
                e = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
                e.update(kw); tmp = destino / "estado.json.tmp"; tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(p)
                break
            except (PermissionError, json.JSONDecodeError, OSError):
                time.sleep(0.05 + 0.05 * k)
        if self.hook:
            try:
                self.hook(destino.name, e.get("estado"), e.get("mensaje"), e.get("progreso"))
            except Exception:
                pass

    def _correr(self, destino, fuente, params, al_terminar=None):
        try:
            def _prog(f, m):
                if self._cancelar:
                    raise DescargaError("Descarga cancelada por la persona.")
                self._estado(destino, progreso=round(float(f), 3), mensaje=str(m))
            res = FUENTES[fuente](destino, params, _prog)
            man = {"id": destino.name, "fuente_id": fuente, "creado_utc": _ahora(), "parametros": params, **res}
            man["sha256"] = {a: _sha(destino / a) for a in res.get("archivos", []) if (destino / a).exists()}
            (destino / "manifiesto.json").write_text(json.dumps(man, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            self._estado(destino, estado="completado", progreso=1.0, mensaje="Completado", fin=_ahora())
            if al_terminar:
                try:
                    al_terminar(destino, man)
                except BaseException as e:                                  # un fallo al registrar no invalida lo descargado
                    self._estado(destino, mensaje="Completado; registrar en el proyecto falló: " + str(e)[:200])
        except BaseException as e:
            (destino / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            self._estado(destino, estado="fallido", mensaje=str(e)[:400], fin=_ahora())


INTERRUMPIDA_S = 600


def reanudar(gestor, carpeta_proyecto, did):
    """Relanza una descarga interrumpida con los mismos parámetros; lo ya bajado (por modelo, en CMIP6) se reutiliza."""
    d = Path(carpeta_proyecto) / "datos_descargados" / did
    if not (d / "estado.json").exists():
        raise DescargaError("No existe esa descarga.")
    e = json.loads((d / "estado.json").read_text(encoding="utf-8"))
    if e.get("estado") == "completado":
        raise DescargaError("Esa descarga ya está completa.")
    par = {k: v for k, v in (e.get("parametros") or {}).items() if k != "proyecto"}
    nuevo = gestor.iniciar(carpeta_proyecto, did.rsplit("_", 2)[0], par)
    e.update(estado="reanudada", mensaje=f"Reanudada en {nuevo}"); (d / "estado.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    return nuevo


def listar(carpeta_proyecto):
    base = Path(carpeta_proyecto) / "datos_descargados"
    out = []
    for d in sorted(base.glob("*_*"), reverse=True) if base.exists() else []:
        e = json.loads((d / "estado.json").read_text(encoding="utf-8")) if (d / "estado.json").exists() else {}
        m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8")) if (d / "manifiesto.json").exists() else {}
        est = e.get("estado", "?")
        if est == "en_curso" and (d / "estado.json").exists() and time.time() - (d / "estado.json").stat().st_mtime > INTERRUMPIDA_S:
            est = "interrumpida"                                                    # el proceso que la llevaba se cerró (sesión cerrada, PC apagada…)
        out.append({"id": d.name, "fuente": d.name.rsplit("_", 2)[0], "estado": est, "progreso": e.get("progreso"), "mensaje": e.get("mensaje"),
                    "archivos": m.get("archivos"), "resumen": {k: m[k] for k in ("pasos", "items", "cobertura_parametros_pct", "cn_min_max_media", "manning_min_max_media", "registro", "crs", "res_m", "n_dias", "periodo", "version", "fuente", "dias_faltantes_en_origen", "con_dato", "solicitudes_fallidas", "tramos", "nota") if k in m}})
    return out


# ------------------------------------------------------------------------------------------------ cuenca (aditivo): MDT amplio, ríos HydroSHEDS y delineación en segundo plano
def _registrar_fuentes_cuenca():
    from . import cuenca as _C
    FUENTES.update({"mdt_cuenca": _C.fuente_mdt_cuenca, "rios": _C.fuente_rios, "delinear": _C.fuente_delinear, "chirps_cuenca": _C.fuente_chirps_cuenca})


_registrar_fuentes_cuenca()
