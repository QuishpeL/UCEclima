# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""OTRAS DESCARGAS de Earth Engine (opcionales): capas que enriquecen la base de datos del proyecto, siguiendo las referencias de Machala y Gualaquiza (pendiente, hidrografía, suelo y erosión RUSLE,
cobertura y vegetación, población, clima y emisiones). Cada capa se baja SOLO para el área del proyecto, en su resolución nativa (o la menor que quepa en una petición), y se guarda en la carpeta del proyecto
con su manifiesto (fuente, fecha, escala, estadísticos) y una vista previa. Tres tipos: «imagen» (GeoTIFF), «serie» (CSV mensual promediado en el área) y «tabla» (CSV de objetos).

Reglas: nada se inventa ni se rellena; todo es un dato de teledetección/modelo (no una medición de campo) y se rotula así; RUSLE es una ESTIMACIÓN EXPLORATORIA con factores simplificados (ver `RUSLE_NOTA`)."""
import json, math, re
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

CATEGORIAS = ["Terreno e hidrografía", "Suelo y erosión", "Cobertura, vegetación e incendios", "Población e infraestructura", "Clima", "Emisiones y atmósfera"]
RUSLE_NOTA = ("RUSLE = R·K·LS·C·P con P = 1. R: erosividad de la lluvia desde la precipitación anual media de CHIRPS 1991–2020 (Renard y Freimund, 1994). K: erodabilidad desde arena, arcilla y carbono orgánico de OpenLandMap "
              "(ecuación EPIC de Williams, 1995). LS: simplificado con la pendiente de NASADEM y el área de drenaje de MERIT Hydro (Desmet y Govers, 1996; máximo 50). C: desde el NDVI medio de MODIS 2018–2023 "
              "(van der Knijff et al., 2000). Es una estimación exploratoria a ~90 m, sin calibrar con pérdidas de suelo medidas; úsala para comparar zonas, no como valor absoluto.")


def _i(id_, cat, nombre, desc, fuente, res, periodo, tipo, **extra):
    return {"id": id_, "categoria": cat, "nombre": nombre, "descripcion": desc, "fuente": fuente, "resolucion": res, "periodo": periodo, "tipo": tipo, **extra}


CATALOGO = [
    _i("pendiente", CATEGORIAS[0], "Pendiente del terreno", "Pendiente en grados calculada del modelo de elevación NASADEM. Base para flujo, erosión y estabilidad.", "NASA/NASADEM_HGT/001", "30 m", "2000", "imagen"),
    _i("altitud_nasadem", CATEGORIAS[0], "Altitud NASADEM", "Elevación del terreno (m s. n. m.) NASADEM, para contrastar con el MDT del proyecto.", "NASA/NASADEM_HGT/001", "30 m", "2000", "imagen"),
    _i("merit_hydro", CATEGORIAS[0], "Hidrografía MERIT Hydro", "Área de drenaje aguas arriba (km²), altura sobre el drenaje más cercano HAND (m) y elevación hidrológicamente corregida.", "MERIT/Hydro/v1_0_1", "90 m", "2000", "imagen"),
    _i("agua_superficial", CATEGORIAS[0], "Agua superficial (JRC)", "Frecuencia de agua (ocurrencia %), recurrencia y estacionalidad 1984–2021: cuerpos y cauces permanentes o temporales.", "JRC/GSW1_4/GlobalSurfaceWater", "30 m", "1984–2021", "imagen"),
    _i("rusle", CATEGORIAS[1], "Erosión del suelo (RUSLE)", "Factores R, K, LS, C y pérdida de suelo A (t·ha⁻¹·año⁻¹). Estimación exploratoria.", "CHIRPS · OpenLandMap · NASADEM · MERIT · MODIS", "90 m", "1991–2023", "imagen", aviso=RUSLE_NOTA),
    _i("suelo_propiedades", CATEGORIAS[1], "Arena, arcilla y carbono orgánico del suelo", "Textura y materia orgánica en los primeros 0–10 cm (OpenLandMap).", "OpenLandMap SOL_*", "250 m", "—", "imagen"),
    _i("perdida_forestal", CATEGORIAS[2], "Cobertura arbórea y pérdida forestal (Hansen)", "Cobertura arbórea del año 2000 (%), pérdida (0/1) y año de pérdida 2001–2023.", "UMD/hansen/global_forest_change_2023_v1_11", "30 m", "2000–2023", "imagen"),
    _i("ndvi_modis", CATEGORIAS[2], "NDVI de MODIS (serie mensual)", "Índice de vegetación promedio del área, mes a mes.", "MODIS/061/MOD13Q1", "250 m", "2001–hoy", "serie", inicio="2001-01-01"),
    _i("area_quemada", CATEGORIAS[2], "Área quemada (MODIS, serie mensual)", "Fracción del área quemada cada mes.", "MODIS/061/MCD64A1", "500 m", "2001–hoy", "serie", inicio="2001-01-01"),
    _i("poblacion_worldpop", CATEGORIAS[3], "Población (WorldPop 2020)", "Personas por celda de 100 m (Ecuador, 2020). Estimación modelada, no censo.", "WorldPop/GP/100m/pop", "100 m", "2020", "imagen"),
    _i("edificaciones", CATEGORIAS[3], "Edificaciones (Google Open Buildings)", "Huellas de edificios detectadas por satélite: número, área y puntos (máx. 5 000).", "GOOGLE/Research/open-buildings/v3/polygons", "vector", "2023", "tabla"),
    _i("luces_nocturnas", CATEGORIAS[3], "Luces nocturnas (VIIRS, serie mensual)", "Radiancia nocturna promedio del área: indicador de actividad humana.", "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG", "~500 m", "2014–hoy", "serie", inicio="2014-01-01"),
    _i("terraclimate", CATEGORIAS[4], "TerraClimate (serie mensual)", "Precipitación, evapotranspiración potencial y real, déficit, escorrentía, humedad del suelo y temperaturas máxima y mínima.", "IDAHO_EPSCOR/TERRACLIMATE", "~4 km", "1958–2023", "serie", inicio="1981-01-01"),
    _i("era5_land", CATEGORIAS[4], "ERA5-Land (serie mensual)", "Temperatura del aire a 2 m (°C), precipitación (mm) y humedad del suelo (m³/m³) de la reanálisis.", "ECMWF/ERA5_LAND/MONTHLY_AGGR", "~9 km", "1950–hoy", "serie", inicio="1981-01-01"),
    _i("emisiones_no2", CATEGORIAS[5], "Dióxido de nitrógeno NO₂ (Sentinel-5P)", "Columna troposférica de NO₂ (mol/m²): tráfico, industria y quema. Mapa medio y serie mensual.", "COPERNICUS/S5P/OFFL/L3_NO2", "~1,1 km", "2018–hoy", "serie_imagen", inicio="2018-07-01"),
    _i("emisiones_co", CATEGORIAS[5], "Monóxido de carbono CO (Sentinel-5P)", "Columna de CO (mol/m²): combustión y quemas. Mapa medio y serie mensual.", "COPERNICUS/S5P/OFFL/L3_CO", "~1,1 km", "2018–hoy", "serie_imagen", inicio="2018-07-01"),
    _i("emisiones_ch4", CATEGORIAS[5], "Metano CH₄ (Sentinel-5P)", "Razón de mezcla de CH₄ en aire seco (ppb). Mapa medio y serie mensual.", "COPERNICUS/S5P/OFFL/L3_CH4", "~7 km", "2019–hoy", "serie_imagen", inicio="2019-01-01",
       aviso="Con nubosidad persistente (zonas andinas húmedas) el filtro de calidad de TROPOMI descarta casi todos los datos: la serie puede venir vacía."),
    _i("emisiones_so2", CATEGORIAS[5], "Dióxido de azufre SO₂ (Sentinel-5P)", "Columna de SO₂ (mol/m²): volcanes e industria. Mapa medio y serie mensual.", "COPERNICUS/S5P/OFFL/L3_SO2", "~1,1 km", "2018–hoy", "serie_imagen", inicio="2018-07-01"),
    _i("fabdem", CATEGORIAS[0], "MDT sin vegetación ni edificios (FABDEM)", "Modelo de elevación de «suelo desnudo» a 30 m (Copernicus GLO-30 corregido de bosques y edificios): mejor para modelar inundación que un DSM.", "projects/sat-io/open-datasets/FABDEM", "30 m", "2011–2015", "imagen",
       aviso="Licencia CC BY-NC-SA 4.0: uso NO comercial. Cita: Hawker et al. (2022), Environ. Res. Lett. 17, 024016."),
    _i("indice_aridez", CATEGORIAS[4], "Índice de aridez (P / PET)", "Precipitación anual media (CHIRPS 1991–2020) sobre evapotranspiración potencial anual (TerraClimate). < 0,65 seco; > 1 húmedo.", "CHIRPS · TerraClimate", "~1 km", "1991–2020", "imagen"),
    _i("vias_poblados_osm", CATEGORIAS[3], "Vías y poblados (OpenStreetMap)", "Red vial (por tipo) y poblados dentro del área del proyecto: exposición y accesos. No viene de Earth Engine (servicio Overpass).", "OpenStreetMap · Overpass API", "vector", "actual", "tabla",
       aviso="© colaboradores de OpenStreetMap (ODbL). Cobertura variable según la zona; no es un inventario oficial."),
    _i("emisiones_hcho", CATEGORIAS[5], "Formaldehído HCHO (Sentinel-5P)", "Columna troposférica de HCHO (mol/m²): quemas e isopreno de la vegetación. Mapa medio y serie mensual.", "COPERNICUS/S5P/OFFL/L3_HCHO", "~1,1 km", "2018–hoy", "serie_imagen", inicio="2018-10-01"),
    _i("limites_gaul", CATEGORIAS[3], "Límites administrativos (FAO GAUL nivel 2)", "Cantones/distritos que tocan el área del proyecto, con nombre y provincia.", "FAO/GAUL/2015/level2", "vector", "2015", "tabla"),
]
POR_ID = {c["id"]: c for c in CATALOGO}

# series: banda → (factor, nombre de salida, unidad)
SERIES = {
    "ndvi_modis": ("MODIS/061/MOD13Q1", 250, {"NDVI": (0.0001, "ndvi", "índice")}),
    "area_quemada": ("MODIS/061/MCD64A1", 500, {"BurnDate": (1.0, "fraccion_quemada", "fracción")}),
    "luces_nocturnas": ("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG", 500, {"avg_rad": (1.0, "radiancia_nW_cm2_sr", "nW/(cm²·sr)")}),
    "terraclimate": ("IDAHO_EPSCOR/TERRACLIMATE", 4638, {"pr": (1.0, "precipitacion_mm", "mm/mes"), "pet": (0.1, "pet_mm", "mm/mes"), "aet": (0.1, "aet_mm", "mm/mes"), "def": (0.1, "deficit_mm", "mm/mes"),
                                                       "ro": (1.0, "escorrentia_mm", "mm/mes"), "soil": (0.1, "humedad_suelo_mm", "mm"), "tmmx": (0.1, "tmax_C", "°C"), "tmmn": (0.1, "tmin_C", "°C")}),
    "era5_land": ("ECMWF/ERA5_LAND/MONTHLY_AGGR", 11132, {"temperature_2m": (1.0, "temperatura_2m_C", "°C"), "total_precipitation_sum": (1000.0, "precipitacion_mm", "mm/mes"), "volumetric_soil_water_layer_1": (1.0, "humedad_suelo_m3m3", "m³/m³")}),
    "emisiones_no2": ("COPERNICUS/S5P/OFFL/L3_NO2", 1113, {"tropospheric_NO2_column_number_density": (1.0, "no2_mol_m2", "mol/m²")}),
    "emisiones_co": ("COPERNICUS/S5P/OFFL/L3_CO", 1113, {"CO_column_number_density": (1.0, "co_mol_m2", "mol/m²")}),
    "emisiones_ch4": ("COPERNICUS/S5P/OFFL/L3_CH4", 1113, {"CH4_column_volume_mixing_ratio_dry_air": (1.0, "ch4_ppb", "ppb")}),
    "emisiones_so2": ("COPERNICUS/S5P/OFFL/L3_SO2", 1113, {"SO2_column_number_density": (1.0, "so2_mol_m2", "mol/m²")}),
    "emisiones_hcho": ("COPERNICUS/S5P/OFFL/L3_HCHO", 1113, {"tropospheric_HCHO_column_number_density": (1.0, "hcho_mol_m2", "mol/m²")}),
}
OFFSET_K = {"temperature_2m": -273.15}                                                                     # kelvin → °C


def catalogo():
    return {"categorias": CATEGORIAS, "items": [{k: v for k, v in c.items()} for c in CATALOGO],
            "nota": "Todo es opcional. Son datos de satélite o modelos (no mediciones de campo); se bajan solo para el área de tu proyecto y se guardan en su carpeta."}


# ------------------------------------------------------------------------------------------------ constructores de imágenes (Earth Engine)
def _imagen(ee, id_):
    if id_ == "pendiente":
        return ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation")).rename("pendiente_grados"), 30, ["pendiente_grados"]
    if id_ == "altitud_nasadem":
        return ee.Image("NASA/NASADEM_HGT/001").select("elevation").rename("altitud_m"), 30, ["altitud_m"]
    if id_ == "merit_hydro":
        h = ee.Image("MERIT/Hydro/v1_0_1"); return h.select(["upa", "hnd", "elv"]).rename(["area_drenaje_km2", "hnd_m", "elevacion_m"]), 90, ["area_drenaje_km2", "hnd_m", "elevacion_m"]
    if id_ == "agua_superficial":
        g = ee.Image("JRC/GSW1_4/GlobalSurfaceWater"); return g.select(["occurrence", "recurrence", "seasonality"]).rename(["ocurrencia_pct", "recurrencia_pct", "estacionalidad_meses"]), 30, ["ocurrencia_pct", "recurrencia_pct", "estacionalidad_meses"]
    if id_ == "suelo_propiedades":
        a = ee.Image("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02").select("b0").rename("arena_pct"); c = ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select("b0").rename("arcilla_pct")
        o = ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02").select("b0").multiply(5).rename("carbono_organico_g_kg")
        return a.addBands(c).addBands(o), 250, ["arena_pct", "arcilla_pct", "carbono_organico_g_kg"]
    if id_ == "perdida_forestal":
        h = ee.Image("UMD/hansen/global_forest_change_2023_v1_11"); return h.select(["treecover2000", "loss", "lossyear"]).rename(["cobertura_arborea_2000_pct", "perdida", "anio_perdida_desde_2000"]), 30, ["cobertura_arborea_2000_pct", "perdida", "anio_perdida_desde_2000"]
    if id_ == "poblacion_worldpop":
        c = ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "ECU")).filter(ee.Filter.eq("year", 2020)).mosaic().select("population").rename("poblacion_por_celda"); return c, 100, ["poblacion_por_celda"]
    if id_ == "rusle":
        return _rusle(ee), 90, ["R", "K", "LS", "C", "A_t_ha_anio"]
    if id_ == "fabdem":
        return ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").mosaic().select("b1").rename("altitud_fabdem_m"), 30, ["altitud_fabdem_m"]
    if id_ == "indice_aridez":
        p = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate("1991-01-01", "2021-01-01").select("precipitation").sum().divide(30).rename("precipitacion_anual_mm")
        pet = ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE").filterDate("1991-01-01", "2021-01-01").select("pet").sum().multiply(0.1).divide(30).rename("pet_anual_mm")
        return p.addBands(pet).addBands(p.divide(pet).rename("indice_aridez")), 1000, ["precipitacion_anual_mm", "pet_anual_mm", "indice_aridez"]
    raise KeyError(id_)


def _rusle(ee):
    """Factores RUSLE como bandas (ver RUSLE_NOTA). P = 1."""
    p = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate("1991-01-01", "2021-01-01").select("precipitation").sum().divide(30).rename("P")
    R = p.expression("P <= 850 ? 0.0483 * (P ** 1.610) : 587.8 - 1.219 * P + 0.004105 * P * P", {"P": p}).rename("R")
    san = ee.Image("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02").select("b0"); cla = ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select("b0")
    oc = ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02").select("b0").multiply(5).divide(10)                    # g/kg → %
    sil = ee.Image(100).subtract(san).subtract(cla).max(0.1)
    K = ee.Image().expression("(0.2 + 0.3 * exp(-0.0256 * S * (1 - L / 100))) * ((L / (A + L)) ** 0.3) * (1 - 0.25 * C / (C + exp(3.72 - 2.95 * C))) * (1 - 0.7 * N / (N + exp(-5.51 + 22.9 * N))) * 0.1317",
                              {"S": san, "L": sil, "A": cla.max(0.1), "C": oc, "N": ee.Image(1).subtract(san.divide(100))}).rename("K")
    sl = ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation")).multiply(math.pi / 180)
    upa = ee.Image("MERIT/Hydro/v1_0_1").select("upa").max(0.0001)                                                              # km²
    LS = ee.Image().expression("min(50, ((U * 1000000 / 90) / 22.13) ** 0.4 * (sin(S) / 0.0896) ** 1.3)", {"U": upa, "S": sl.max(0.001)}).rename("LS")
    ndvi = ee.ImageCollection("MODIS/061/MOD13Q1").filterDate("2018-01-01", "2024-01-01").select("NDVI").mean().multiply(0.0001).clamp(0, 0.95)
    C = ndvi.expression("exp(-2 * N / (1 - N))", {"N": ndvi}).rename("C")
    A = R.multiply(K).multiply(LS).multiply(C).rename("A_t_ha_anio")
    return R.addBands(K).addBands(LS).addBands(C).addBands(A).toFloat()


# ------------------------------------------------------------------------------------------------ utilidades de salida
def _xlsx(df, ruta):
    """Copia en Excel de una tabla (regla de las entregas: toda tabla en .xlsx además del CSV)."""
    try:
        df.to_excel(ruta, index=False)
        return True
    except Exception:
        return False


def _vector(df, geometria, destino, nombre, crs_utm=None):
    """Capa vectorial en shapefile WGS84 y UTM (campos ≤ 10 caracteres) y GeoPackage. `geometria`: lista de objetos shapely. Devuelve los archivos creados."""
    import geopandas as gpd
    g = gpd.GeoDataFrame(df.copy(), geometry=geometria, crs="EPSG:4326"); g.columns = [c if c == "geometry" else str(c)[:10] for c in g.columns]
    out = []
    g.to_file(destino / f"{nombre}_wgs84.shp"); out += [f"{nombre}_wgs84.shp"]
    if crs_utm:
        g.to_crs(crs_utm).to_file(destino / f"{nombre}_utm.shp"); out += [f"{nombre}_utm.shp"]
    g.to_file(destino / f"{nombre}.gpkg", driver="GPKG"); out += [f"{nombre}.gpkg"]
    return out


def _estadisticos(archivo, bandas):
    import rasterio
    out = {}
    with rasterio.open(archivo) as s:
        for k, nombre in enumerate(bandas[: s.count], start=1):
            a = s.read(k, masked=True).astype("float64")
            out[nombre] = {"min": float(a.min()) if a.count() else None, "media": float(a.mean()) if a.count() else None, "max": float(a.max()) if a.count() else None, "validas_pct": round(float(a.count() / a.size * 100), 1)}
    return out


def _vista_png(archivo, bandas, titulo, destino):
    import rasterio
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with rasterio.open(archivo) as s:
        n = min(s.count, len(bandas)); datos = [s.read(k, masked=True).astype("float64") for k in range(1, n + 1)]
    cols = min(n, 3); filas = int(math.ceil(n / cols))
    fig, axs = plt.subplots(filas, cols, figsize=(4.2 * cols, 3.9 * filas), squeeze=False)
    for ax in axs.ravel():
        ax.set_axis_off()
    for k, (a, nom) in enumerate(zip(datos, bandas)):
        ax = axs.ravel()[k]; im = ax.imshow(a, cmap="viridis" if "pendiente" not in nom else "magma"); ax.set_title(nom, fontsize=9); fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    fig.suptitle(titulo, fontsize=10); fig.tight_layout(); fig.savefig(destino, dpi=120); plt.close(fig)


def _vista_serie(df, columnas, titulo, destino):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(columnas); fig, axs = plt.subplots(n, 1, figsize=(9, 2.2 * n + 0.8), sharex=True, squeeze=False)
    f = pd.to_datetime(df["fecha"])
    for ax, c in zip(axs.ravel(), columnas):
        ax.plot(f, df[c], color="#2b8fc7", lw=1.4); ax.set_ylabel(c, fontsize=8); ax.grid(alpha=.3)
    fig.suptitle(titulo, fontsize=10); fig.tight_layout(); fig.savefig(destino, dpi=120); plt.close(fig)


def _serie_mensual(ee, id_, geom, inicio, fin, progreso, f0, f1):
    coleccion, escala, bandas = SERIES[id_]
    col = ee.ImageCollection(coleccion).select(list(bandas))
    if id_ == "area_quemada":                                                                                  # BurnDate = día del año de la quema (0/máscara si no se quemó): se convierte en fracción quemada
        col = col.map(lambda im: im.select("BurnDate").gt(0).unmask(0).rename("BurnDate").copyProperties(im, ["system:time_start"]))
    meses = pd.period_range(pd.Timestamp(inicio).to_period("M"), pd.Timestamp(fin).to_period("M"), freq="M"); filas = []
    for k in range(0, len(meses), 24):
        trozo = meses[k:k + 24]
        fechas = ee.List([m.start_time.strftime("%Y-%m-%d") for m in trozo])
        def por_mes(d):                                                                              # un solo argumento: Earth Engine pasa objetos del servidor, no variables de Python
            d = ee.Date(d); sub = col.filterDate(d, d.advance(1, "month")); red = sub.mean().reduceRegion(ee.Reducer.mean(), geom, escala, maxPixels=1e9, bestEffort=True)
            return ee.Feature(None, red).set("fecha", d.format("YYYY-MM-dd")).set("n_imagenes", sub.size())
        for intento in range(3):
            try:
                feats = ee.FeatureCollection(fechas.map(por_mes)).getInfo()["features"]; break
            except Exception as e:
                if intento == 2:
                    raise
                import time; time.sleep(3)
        filas += [x["properties"] for x in feats]
        progreso(f0 + (f1 - f0) * min(1, (k + 24) / len(meses)), f"{id_}: {trozo[-1]}")
    df = pd.DataFrame(filas)
    out = pd.DataFrame({"fecha": df["fecha"], "n_imagenes": df.get("n_imagenes")})
    for b, (factor, nombre, unidad) in bandas.items():
        v = pd.to_numeric(df.get(b), errors="coerce") * factor + OFFSET_K.get(b, 0.0); out[nombre] = v.round(6)
    return out


def _tabla(ee, id_, geom, destino, progreso, bbox=None, crs_utm=None):
    from shapely.geometry import Point, shape
    if id_ == "edificaciones":
        fc = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons").filterBounds(geom)
        n = int(fc.size().getInfo()); resumen = {"n_edificaciones": n}
        feats = fc.limit(5000).map(lambda f: ee.Feature(f.geometry().centroid(1), {"area_m2": f.get("area_in_meters"), "confianza": f.get("confidence")})).getInfo()["features"]
        df = pd.DataFrame([{"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1], **f["properties"]} for f in feats])
        resumen.update({"puntos_guardados": int(len(df)), "area_total_m2": float(df["area_m2"].sum()) if len(df) else 0.0, "completo": bool(n <= 5000)})
        df.to_csv(destino / "edificaciones_puntos.csv", index=False); files = ["edificaciones_puntos.csv"]
        if _xlsx(df, destino / "edificaciones_puntos.xlsx"): files.append("edificaciones_puntos.xlsx")
        if len(df):
            try:
                files += _vector(df, [Point(x, y) for x, y in zip(df["lon"], df["lat"])], destino, "edificaciones_puntos", crs_utm)
            except Exception:
                pass
        return files, resumen
    if id_ == "limites_gaul":
        import warnings; warnings.filterwarnings("ignore")
        fc = ee.FeatureCollection("FAO/GAUL/2015/level2").filterBounds(geom)
        feats = fc.getInfo()["features"]; df = pd.DataFrame([{"pais": f["properties"].get("ADM0_NAME"), "provincia": f["properties"].get("ADM1_NAME"), "canton": f["properties"].get("ADM2_NAME"), "codigo": f["properties"].get("ADM2_CODE")} for f in feats])
        df.to_csv(destino / "limites_gaul.csv", index=False); files = ["limites_gaul.csv"]
        if _xlsx(df, destino / "limites_gaul.xlsx"): files.append("limites_gaul.xlsx")
        (destino / "limites_gaul.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8"); files.append("limites_gaul.geojson")
        try:
            files += _vector(df, [shape(f["geometry"]) for f in feats], destino, "limites_gaul", crs_utm)
        except Exception:
            pass
        return files, {"n_unidades": int(len(df)), "unidades": df.to_dict("records")}
    if id_ == "vias_poblados_osm":
        import requests
        from shapely.geometry import LineString
        w, s, e, n = bbox
        consulta = f"[out:json][timeout:60];(way[\"highway\"]({s},{w},{n},{e});node[\"place\"]({s},{w},{n},{e}););out geom;"
        datos, ultimo = None, ""
        for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
            for intento in range(2):
                try:
                    progreso(0.5, f"consultando Overpass ({url.split('/')[2]})"); r = requests.post(url, data={"data": consulta}, timeout=(15, 90)); r.raise_for_status(); datos = r.json(); break
                except Exception as ex:
                    ultimo = str(ex)[:160]
            if datos:
                break
        if not datos:
            raise RuntimeError("OpenStreetMap (Overpass) está saturado o no respondió (" + ultimo + "). Es un servicio público con límite de uso: intenta de nuevo en unos minutos.")
        vias = [x for x in datos["elements"] if x["type"] == "way" and len(x.get("geometry", [])) > 1]; poblados = [x for x in datos["elements"] if x["type"] == "node"]
        def largo_km(g):
            import math
            return sum(math.hypot((b["lon"] - a["lon"]) * 111.32 * math.cos(math.radians(a["lat"])), (b["lat"] - a["lat"]) * 110.57) for a, b in zip(g[:-1], g[1:]))
        dv = pd.DataFrame([{"osm_id": x["id"], "tipo": x.get("tags", {}).get("highway"), "nombre": x.get("tags", {}).get("name"), "largo_km": round(largo_km(x["geometry"]), 3)} for x in vias])
        dp = pd.DataFrame([{"osm_id": x["id"], "tipo": x.get("tags", {}).get("place"), "nombre": x.get("tags", {}).get("name"), "lon": x["lon"], "lat": x["lat"]} for x in poblados])
        files = []
        for nombre, df in (("vias_osm", dv), ("poblados_osm", dp)):
            df.to_csv(destino / f"{nombre}.csv", index=False); files.append(f"{nombre}.csv")
            if _xlsx(df, destino / f"{nombre}.xlsx"): files.append(f"{nombre}.xlsx")
        try:
            if len(dv): files += _vector(dv, [LineString([(p["lon"], p["lat"]) for p in x["geometry"]]) for x in vias], destino, "vias_osm", crs_utm)
            if len(dp): files += _vector(dp, [Point(x["lon"], x["lat"]) for x in poblados], destino, "poblados_osm", crs_utm)
        except Exception:
            pass
        por_tipo = dv.groupby("tipo")["largo_km"].sum().round(2).to_dict() if len(dv) else {}
        return files, {"n_tramos": int(len(dv)), "largo_total_km": round(float(dv["largo_km"].sum()), 2) if len(dv) else 0.0, "largo_por_tipo_km": por_tipo, "n_poblados": int(len(dp))}
    raise KeyError(id_)


# ------------------------------------------------------------------------------------------------ descarga (fuente «otras» del gestor)
def otras_gee(destino, p, progreso):
    """Baja las capas elegidas (`p['items']`: lista de ids del catálogo) una tras otra; si una falla las demás siguen y queda anotado. Cada capa en su subcarpeta."""
    from . import gee_chirps as G, descargas as D
    from .parametros_gee import bbox_proyecto, _bajar_capa
    ids = [i for i in (p.get("items") or []) if i in POR_ID]
    if not ids:
        raise D.DescargaError("Elige al menos una capa del catálogo.")
    bbox, origen = bbox_proyecto(p, medio_km=float(p.get("medio_km", 10)))
    from .ui import proyecto as PRY
    try:
        crs_utm = PRY.abrir(str(p["proyecto"]))[0].get("crs")
    except Exception:
        crs_utm = None
    progreso(0.01, "conectando con Earth Engine")
    info, ee = G.iniciar()
    if not info.get("autenticado") and ids != ["vias_poblados_osm"]:
        raise D.DescargaError("Earth Engine no está conectado: abre el módulo «Datos / GEE» y pulsa «Conectar con Google Earth Engine». " + str(info.get("error"))[:120])
    geom = ee.Geometry.Rectangle(bbox, proj="EPSG:4326", geodesic=False) if ee is not None else None
    hoy = datetime.now().strftime("%Y-%m-%d"); resultados, archivos = {}, []
    ancho_m = (bbox[2] - bbox[0]) * 111320 * math.cos(math.radians((bbox[1] + bbox[3]) / 2)); alto_m = (bbox[3] - bbox[1]) * 111320
    for k, id_ in enumerate(ids):
        c = POR_ID[id_]; sub = destino / id_; sub.mkdir(); f0, f1 = k / len(ids), (k + 1) / len(ids); mani = {"id": id_, "nombre": c["nombre"], "fuente": c["fuente"], "tipo": c["tipo"], "creado_utc": datetime.utcnow().isoformat(timespec="seconds"), "bbox_lonlat": bbox}
        try:
            progreso(f0, f"{c['nombre']} ({k + 1} de {len(ids)})")
            files = []
            if c["tipo"] in ("imagen", "serie_imagen"):
                if c["tipo"] == "imagen":
                    img, escala, bandas = _imagen(ee, id_)
                else:                                                                                              # mapa medio de los últimos 24 meses
                    coleccion, escala, bd = SERIES[id_]; fin = pd.Timestamp(hoy); ini = fin - pd.DateOffset(months=24)
                    img = ee.ImageCollection(coleccion).select(list(bd)).filterDate(ini.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")).mean().rename([v[1] for v in bd.values()]).toFloat(); bandas = [v[1] for v in bd.values()]
                    mani["periodo_mapa"] = [ini.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")]
                nb = max(1, len(bandas)); esc = float(escala)
                while (ancho_m / esc) * (alto_m / esc) * nb * 4 > 42e6:                                         # que quepa en una petición (≤ 50 MB)
                    esc *= 1.5
                mani["escala_m"] = round(esc, 1); mani["escala_nativa_m"] = escala; mani["bandas"] = bandas
                _bajar_capa(img.toFloat(), geom, esc, sub, f"{id_}.tif", lambda f, m: progreso(f0 + (f1 - f0) * (0.1 + 0.6 * float(f)), m), 0.0, 1.0, D)
                mani["estadisticos"] = _estadisticos(sub / f"{id_}.tif", bandas); files.append(f"{id_}.tif")
                try:
                    _vista_png(sub / f"{id_}.tif", bandas, f"{c['nombre']} · {c['fuente']}", sub / f"{id_}_vista.png"); files.append(f"{id_}_vista.png")
                except Exception:
                    pass
            if c["tipo"] in ("serie", "serie_imagen"):
                ini = p.get("inicio") or c.get("inicio") or "2001-01-01"
                df = _serie_mensual(ee, id_, geom, ini, hoy, progreso, f0 + (f1 - f0) * (0.7 if c["tipo"] == "serie_imagen" else 0.05), f1)
                df.to_csv(sub / f"{id_}_mensual.csv", index=False); files.append(f"{id_}_mensual.csv")
                if _xlsx(df, sub / f"{id_}_mensual.xlsx"): files.append(f"{id_}_mensual.xlsx")
                cols = [x for x in df.columns if x not in ("fecha", "n_imagenes")]
                mani["serie"] = {"inicio": ini, "fin": hoy, "meses": int(len(df)), "meses_con_dato": int(df[cols[0]].notna().sum()) if cols else 0}
                try:
                    _vista_serie(df, cols[:4], f"{c['nombre']} · promedio en el área del proyecto", sub / f"{id_}_serie.png"); files.append(f"{id_}_serie.png")
                except Exception:
                    pass
            if c["tipo"] == "tabla":
                files, resumen = _tabla(ee, id_, geom, sub, progreso, bbox, crs_utm); mani["resumen"] = resumen
            if id_ == "rusle":
                mani["aviso"] = RUSLE_NOTA
            mani["archivos"] = files; (sub / "manifiesto.json").write_text(json.dumps(mani, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            resultados[id_] = {"estado": "ok", "nombre": c["nombre"], "archivos": files, **{k2: mani[k2] for k2 in ("estadisticos", "serie", "resumen", "escala_m") if k2 in mani}}
            archivos += [f"{id_}/{a}" for a in files]
        except BaseException as e:
            if "cancelada" in str(e).lower():
                raise
            import traceback
            (sub / "error.txt").write_text(traceback.format_exc(), encoding="utf-8"); resultados[id_] = {"estado": "fallo", "nombre": c["nombre"], "error": str(e)[:300]}
    return {"archivos": archivos, "fuente": "Earth Engine · catálogo de capas opcionales", "items": resultados, "bbox_lonlat": bbox, "origen_area": origen,
            "nota": "Datos de satélite o modelos (no mediciones de campo), recortados al área del proyecto. Opcionales: enriquecen la base de datos de referencia."}
