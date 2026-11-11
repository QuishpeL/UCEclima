# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""ENTREGAS: una carpeta ordenada con TODO lo que produce el proyecto (shapes, CSV/Excel, mapas, figuras) y, dentro, una subcarpeta de INSUMOS para cada programa que viene después:
  02_BCA_FEMA              análisis beneficio–costo (peligro por escenario, exposición de edificaciones, población y vías, frecuencia/Tr, factor de cambio climático);
  03_ENSO_El_Nino_La_Nina  software de El Niño / La Niña (lluvia mensual y anual, series del premódulo, índice ONI, factores CMIP6);
  (un tercer programa se añade como una carpeta más: PROGRAMAS lo declara).
Reglas: solo se empaqueta lo que existe; lo que falta se dice en los LEEME (no se inventa nada: ni valores de edificios ni curvas de daño). Los resultados siguen siendo NO calibrados ni validados.
Convención de las referencias: toda tabla en CSV y Excel; toda capa en shapefile WGS84 y UTM (campos ≤ 10 caracteres) más GeoPackage; nada se sobrescribe (carpeta nueva con marca de tiempo)."""
import hashlib, json, shutil
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

CLASES_CALADO = [(0.05, 0.3, "0,05–0,3 m"), (0.3, 0.5, "0,3–0,5 m"), (0.5, 1.0, "0,5–1 m"), (1.0, 2.0, "1–2 m"), (2.0, 1e9, "> 2 m")]
PROGRAMAS = {"02_BCA_FEMA": "Análisis beneficio–costo (FEMA BCA)", "03_ENSO_El_Nino_La_Nina": "Software de El Niño / La Niña"}
AVISO = "Resultados no calibrados ni validados (los de CMIP6, además, bajo línea base asumida por decisión del usuario). No son predicción ni huella de inundación observada."


def _xlsx(df, ruta):
    try:
        df.to_excel(ruta, index=False); return True
    except Exception:
        return False


def _tabla(df, carpeta, nombre, archivos):
    carpeta.mkdir(parents=True, exist_ok=True); df.to_csv(carpeta / f"{nombre}.csv", index=False, encoding="utf-8-sig"); archivos.append(carpeta / f"{nombre}.csv")
    if _xlsx(df, carpeta / f"{nombre}.xlsx"):
        archivos.append(carpeta / f"{nombre}.xlsx")


def _capa(gdf, carpeta, nombre, archivos, crs_utm=None):
    """shapefile WGS84 y UTM + GeoPackage."""
    carpeta.mkdir(parents=True, exist_ok=True); g = gdf.copy(); g.columns = [c if c == "geometry" else str(c)[:10] for c in g.columns]
    if g.crs is None and crs_utm:
        g = g.set_crs(crs_utm)
    g.to_crs("EPSG:4326").to_file(carpeta / f"{nombre}_wgs84.shp"); archivos.append(carpeta / f"{nombre}_wgs84.shp")
    g.to_crs(crs_utm or g.crs).to_file(carpeta / f"{nombre}_utm.shp"); archivos.append(carpeta / f"{nombre}_utm.shp")
    g.to_file(carpeta / f"{nombre}.gpkg", driver="GPKG"); archivos.append(carpeta / f"{nombre}.gpkg")


# ------------------------------------------------------------------------------------------------ corridas del proyecto
def corridas(proyecto):
    """Corridas completadas con su escenario (X / Y), factor y archivos de salida."""
    out = []
    for r in sorted((Path(proyecto) / "resultados").glob("corrida_*")):
        s = next(iter(r.glob("salida/*/resumen.json")), None)
        if not s:
            continue
        try:
            res = json.loads(s.read_text(encoding="utf-8")); ent = json.loads((r / "entrada.json").read_text(encoding="utf-8")) if (r / "entrada.json").exists() else {}
        except Exception:
            continue
        if res.get("estado") != "final_completo":
            continue
        esc = ent.get("escenario") or {}; sid = esc.get("id") or res.get("escenario") or "base"
        out.append({"id": r.name, "escenario": sid, "nombre": esc.get("nombre") or res.get("escenario"), "tipo": "Y (CMIP6, cambio climático)" if str(sid).startswith("cc_") else "X (condiciones existentes)",
                    "factor_cc": esc.get("factor", res.get("factor_cc", 1.0)), "ssp": esc.get("ssp"), "horizonte": esc.get("horizonte"), "tr": res.get("Tr"), "p_total_mm": res.get("P_total_mm"), "resumen": res,
                    "dir": r, "salida": s.parent, "hmax": s.parent / "hmax.tif", "vmax": s.parent / "vmax.tif", "duracion": s.parent / "duracion_h_ge_03m.tif", "gpkg": s.parent / "inundacion_ge_03m.gpkg", "mapa": r / "mapa_hmax.png"})
    return out


def _marca(rid):
    """Eta (Yaguachi): «cc_…_mediana_ediana» y «_7_real» salían de cortar los 6 últimos caracteres del id. Ahora va la fecha y hora de la corrida."""
    import re as _re
    m = _re.search(r"(\d{8}_\d{6})", str(rid))
    return m.group(1) if m else str(rid)


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------ exposición (BCA)
def _muestrear(hmax_path, x, y):
    import rasterio
    with rasterio.open(hmax_path) as s:
        vals = np.array([np.nan if np.ma.is_masked(v[0]) else float(v[0]) for v in s.sample(list(zip(x, y)), masked=True)], dtype=float) if len(x) else np.array([])
        b = s.bounds
    dentro = (np.asarray(x) >= b.left) & (np.asarray(x) <= b.right) & (np.asarray(y) >= b.bottom) & (np.asarray(y) <= b.top)
    vals = np.where(dentro, vals, np.nan); vals = np.where(vals > 0.0, vals, 0.0) if len(vals) else vals
    return vals, dentro


def _clase(v):
    for lo, hi, nom in CLASES_CALADO:
        if lo <= v < hi:
            return nom
    return None


def _ultima_descarga(proyecto, patron_archivo):
    for d in sorted((Path(proyecto) / "datos_descargados").glob("otras_*"), reverse=True):
        f = next(iter(d.glob(patron_archivo)), None)
        if f:
            return f
    return None


def _osm_corrida(proyecto, nombre):
    """Eta (Yaguachi): capas OSM que ya bajó el mapa con referencias de la corrida (datos_descargados/osm_*/edificios.json o vias.json)."""
    for d in sorted((Path(proyecto) / "datos_descargados").glob("osm_*"), reverse=True):
        f = d / nombre
        if f.exists():
            try:
                el = json.loads(f.read_text(encoding="utf-8")).get("elements") or []
                if el:
                    return el, d
            except Exception:
                continue
    return None, None


def _edificios_osm(proyecto, crs):
    el, d = _osm_corrida(proyecto, "edificios.json")
    if not el:
        return None, None
    from shapely.geometry import Polygon
    from pyproj import Transformer
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True); filas = []
    for e in el:
        g = e.get("geometry") or []
        if len(g) < 3:
            continue
        lon = [p["lon"] for p in g]; lat = [p["lat"] for p in g]; xs, ys = tf.transform(lon, lat)
        try:
            pol = Polygon(list(zip(xs, ys))); c = pol.centroid; a_ = abs(pol.area)
        except Exception:
            continue
        clon, clat = float(np.mean(lon)), float(np.mean(lat))
        filas.append({"lon": clon, "lat": clat, "area_m2": round(a_, 1), "osm_id": e.get("id"), "tipo_osm": (e.get("tags") or {}).get("building", "yes")})
    return (pd.DataFrame(filas) if filas else None), d


def _vias_osm(proyecto):
    el, d = _osm_corrida(proyecto, "vias.json")
    if not el:
        return None, None
    import geopandas as gpd
    from shapely.geometry import LineString
    geoms, tipos = [], []
    for e in el:
        g = e.get("geometry") or []
        if len(g) >= 2:
            geoms.append(LineString([(p["lon"], p["lat"]) for p in g])); tipos.append((e.get("tags") or {}).get("highway", ""))
    return (gpd.GeoDataFrame({"highway": tipos}, geometry=geoms, crs="EPSG:4326") if geoms else None), d


def exposicion(proyecto, cs, crs, carpeta, archivos, notas):
    """Edificaciones, población y vías expuestas por escenario y clase de calado (solo si esas capas ya se descargaron; si no, se dice)."""
    from pyproj import Transformer
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True); filas = []; ed_cols = {}
    ed = _ultima_descarga(proyecto, "edificaciones/edificaciones_puntos.csv"); df_osm, d_osm = (None, None) if ed is not None else _edificios_osm(proyecto, crs)
    if ed is not None or df_osm is not None:
        if ed is None:
            notas.append(f"Edificaciones: se usaron las de OpenStreetMap que bajó el mapa con referencias de la corrida ({d_osm.name}, {len(df_osm)} edificios; OSM puede estar incompleto). Para Google Open Buildings: Datos / GEE › Otras descargas.")
        df = pd.read_csv(ed) if ed is not None else df_osm; X, Y = tf.transform(df["lon"].values, df["lat"].values); df["x_utm"], df["y_utm"] = X, Y
        for k, c in enumerate(cs, start=1):
            h, dentro = _muestrear(c["hmax"], X, Y); df[f"h_{c['escenario']}"] = np.round(h, 3); ed_cols[f"h{k:02d}"] = c["escenario"]
            cl = pd.Series([_clase(v) if np.isfinite(v) else None for v in h])
            for _, _, nom in CLASES_CALADO:
                sel = (cl == nom).values
                filas.append({"escenario": c["escenario"], "tipo": c["tipo"], "elemento": "edificaciones", "clase_calado": nom, "n": int(sel.sum()), "area_m2": float(df.loc[sel, "area_m2"].sum()) if "area_m2" in df else None})
            filas.append({"escenario": c["escenario"], "tipo": c["tipo"], "elemento": "edificaciones", "clase_calado": "fuera del dominio del modelo", "n": int((~dentro).sum()), "area_m2": None})
        _tabla(df.drop(columns=["x_utm", "y_utm"]), carpeta / "exposicion", "edificaciones_calado_por_escenario", archivos)
        try:
            import geopandas as gpd
            from shapely.geometry import Point
            g = gpd.GeoDataFrame(df[["area_m2"] + [f"h_{c['escenario']}" for c in cs]].copy(), geometry=[Point(a, b) for a, b in zip(df["lon"], df["lat"])], crs="EPSG:4326")
            g.columns = ["area_m2"] + list(ed_cols.keys()) + ["geometry"]; _capa(g, carpeta / "exposicion", "edificaciones_calado", archivos, crs)
            _tabla(pd.DataFrame({"campo_shp": list(ed_cols), "escenario": list(ed_cols.values())}), carpeta / "exposicion", "edificaciones_calado_leyenda_campos", archivos)
        except Exception as e:
            notas.append(f"No se pudo escribir el shapefile de edificaciones: {str(e)[:100]}")
    else:
        notas.append("Edificaciones: no hay capa descargada. Bájala en Datos / GEE › Otras descargas › «Edificaciones (Google Open Buildings)» para calcular edificios expuestos.")
    pop = _ultima_descarga(proyecto, "poblacion_worldpop/poblacion_worldpop.tif")
    if pop is not None:
        import rasterio
        with rasterio.open(pop) as s:
            a = s.read(1, masked=True).filled(0).astype(float); rows, cols = np.indices(a.shape); xs, ys = rasterio.transform.xy(s.transform, rows.ravel(), cols.ravel()); P = a.ravel()
        X, Y = tf.transform(np.asarray(xs), np.asarray(ys))
        for c in cs:
            h, dentro = _muestrear(c["hmax"], X, Y)
            for lo, hi, nom in CLASES_CALADO:
                sel = (h >= lo) & (h < hi) & dentro
                filas.append({"escenario": c["escenario"], "tipo": c["tipo"], "elemento": "población (WorldPop 2020, modelada)", "clase_calado": nom, "n": float(np.round(P[sel].sum(), 1)), "area_m2": None})
    else:
        notas.append("Población: no hay capa descargada (Otras descargas › «Población (WorldPop)»).")
    vias = _ultima_descarga(proyecto, "vias_poblados_osm/vias_osm.gpkg"); g_osm, d_osm = (None, None) if vias is not None else _vias_osm(proyecto)
    if vias is not None or g_osm is not None:
        import geopandas as gpd
        if vias is None:
            notas.append(f"Vías: se usaron las de OpenStreetMap que bajó el mapa con referencias de la corrida ({d_osm.name}, {len(g_osm)} tramos).")
        g = (gpd.read_file(vias) if vias is not None else g_osm).to_crs(crs)
        for c in cs:
            largo = {nom: 0.0 for _, _, nom in CLASES_CALADO}
            for geom in g.geometry:
                if geom is None or geom.length == 0:
                    continue
                n = max(2, int(geom.length // 20)); pts = [geom.interpolate(i / (n - 1), normalized=True) for i in range(n)]; h, dentro = _muestrear(c["hmax"], [p.x for p in pts], [p.y for p in pts]); paso = geom.length / (n - 1)
                for v, d in zip(h, dentro):
                    cl = _clase(v) if d and np.isfinite(v) else None
                    if cl:
                        largo[cl] += paso / 1000
            for nom, km in largo.items():
                filas.append({"escenario": c["escenario"], "tipo": c["tipo"], "elemento": "vías (OSM) inundadas, km", "clase_calado": nom, "n": round(km, 3), "area_m2": None})
    else:
        notas.append("Vías: no hay capa descargada (Otras descargas › «Vías y poblados (OpenStreetMap)»).")
    return pd.DataFrame(filas)


# ------------------------------------------------------------------------------------------------ construcción
def construir(proyecto, datos, ids=None):
    import rasterio
    from rasterio.features import shapes
    import geopandas as gpd
    from shapely.geometry import shape
    proyecto = Path(proyecto); crs = datos["crs"]; base = proyecto / "entregas" / f"entrega_{datetime.now():%Y%m%d_%H%M%S}"; k = 1; raiz = base
    while raiz.exists():
        k += 1; raiz = base.with_name(f"{base.name}_{k}")
    raiz.mkdir(parents=True); archivos, notas = [], []
    cs = corridas(proyecto)
    if ids:                                                                     # Eta (punto 33d): la persona elige qué corridas entran (p. ej., sin la X de prueba)
        cs = [c for c in cs if c["id"] in set(ids)]
    if not cs:
        notas.append("No hay corridas completadas: la entrega solo incluye lluvia y cambio climático.")
    # ---------------- 01 resultados generales
    g1 = raiz / "01_resultados"
    if cs:
        filas = [{"corrida": c["id"], "escenario": c["escenario"], "tipo": c["tipo"], "ssp": c["ssp"], "horizonte": c["horizonte"], "factor_cc": c["factor_cc"], "Tr_anios": c["tr"], "P_total_mm": c["p_total_mm"],
                  "calado_max_m": c["resumen"].get("calado_max_m"), "area_ge_0.05_km2": c["resumen"].get("area_ge_0.05_km2"), "area_ge_0.3_km2": c["resumen"].get("area_ge_0.3_km2"), "area_ge_0.5_km2": c["resumen"].get("area_ge_0.5_km2"),
                  "area_ge_1.0_km2": c["resumen"].get("area_ge_1.0_km2"), "volumen_escorrentia_m3": c["resumen"].get("volumen_escorrentia_m3"), "volumen_salida_m3": c["resumen"].get("volumen_salida_m3"),
                  "error_balance_max_pct": c["resumen"].get("error_balance_max_pct"), "estado_calibracion": c["resumen"].get("estado_calibracion"), "res_m": c["resumen"].get("res_m"), "celdas": c["resumen"].get("celdas")} for c in cs]
        _tabla(pd.DataFrame(filas), g1 / "tablas", "resumen_corridas", archivos)
        for c in cs:
            if c["mapa"].exists():
                (g1 / "mapas").mkdir(parents=True, exist_ok=True); shutil.copy2(c["mapa"], g1 / "mapas" / f"{c['escenario']}_{_marca(c['id'])}_hmax.png"); archivos.append(g1 / "mapas" / f"{c['escenario']}_{_marca(c['id'])}_hmax.png")
            for nombre, ruta in (("hmax", c["hmax"]), ("vmax", c["vmax"]), ("duracion_h_ge_0.3m", c["duracion"])):
                if ruta.exists():
                    (g1 / "raster").mkdir(parents=True, exist_ok=True); dst = g1 / "raster" / f"{c['escenario']}_{_marca(c['id'])}_{nombre}.tif"; shutil.copy2(ruta, dst); archivos.append(dst)
            if c["gpkg"].exists():
                try:
                    _capa(gpd.read_file(c["gpkg"]), g1 / "shapes", f"{c['escenario']}_{_marca(c['id'])}_inundacion_ge_0_3m", archivos, crs)
                except Exception as e:
                    notas.append(f"Shapefile de {c['id']}: {str(e)[:80]}")
        try:                                                                                                    # figura X frente a Y
            import matplotlib; matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            d = pd.DataFrame(filas); d = d[d["area_ge_0.3_km2"].notna()].sort_values(["tipo", "escenario"])
            if len(d):
                fig, ax = plt.subplots(figsize=(9, 0.5 * len(d) + 1.6)); col = ["#ff4da6" if t.startswith("Y") else "#6cc4ec" for t in d["tipo"]]
                ax.barh(d["escenario"], d["area_ge_0.3_km2"], color=col); ax.invert_yaxis(); ax.set_xlabel("área con calado ≥ 0,3 m (km²)"); ax.set_title("X (azul) frente a Y (magenta): área inundada ≥ 0,3 m · sin calibrar")
                fig.tight_layout(); (g1 / "figuras").mkdir(parents=True, exist_ok=True); fig.savefig(g1 / "figuras" / "X_vs_Y_area_inundada.png", dpi=130); plt.close(fig); archivos.append(g1 / "figuras" / "X_vs_Y_area_inundada.png")
        except Exception:
            pass
    for d, nombre in (("registro/idf_x", "idf_x"), ):
        for png in sorted((proyecto / d).glob("*/*.png"))[-3:]:
            (g1 / "figuras").mkdir(parents=True, exist_ok=True); dst = g1 / "figuras" / f"{nombre}_{png.name}"; shutil.copy2(png, dst); archivos.append(dst)
    for dsc in sorted((proyecto / "datos_descargados").glob("*chirps*/graficos")) + sorted((proyecto / "datos_descargados").glob("sitio_*/chirps/graficos")):
        for png in dsc.glob("*.png"):
            (g1 / "figuras").mkdir(parents=True, exist_ok=True); dst = g1 / "figuras" / f"chirps_{png.name}"; shutil.copy2(png, dst); archivos.append(dst)
    # ---------------- 02 BCA FEMA
    g2 = raiz / "02_BCA_FEMA"
    if cs:
        freq = pd.DataFrame([{"escenario": c["escenario"], "tipo": c["tipo"], "Tr_anios": c["tr"], "probabilidad_anual": (1 / c["tr"]) if c["tr"] else None, "factor_cc": c["factor_cc"], "ssp": c["ssp"], "horizonte": c["horizonte"], "P_total_mm": c["p_total_mm"]} for c in cs])
        _tabla(freq, g2 / "frecuencia", "escenarios_frecuencia", archivos)
        for c in cs:
            if c["hmax"].exists():
                (g2 / "peligro").mkdir(parents=True, exist_ok=True); dst = g2 / "peligro" / f"{c['escenario']}_{_marca(c['id'])}_calado_max_m.tif"; shutil.copy2(c["hmax"], dst); archivos.append(dst)
                try:                                                                                              # polígonos por clase de calado
                    with rasterio.open(c["hmax"]) as s:
                        a = s.read(1, masked=True).filled(0).astype("float32"); cl = np.zeros(a.shape, dtype="int16")
                        for i, (lo, hi, _) in enumerate(CLASES_CALADO, start=1):
                            cl[(a >= lo) & (a < hi)] = i
                        geoms = [(shape(g_), int(v)) for g_, v in shapes(cl, mask=cl > 0, transform=s.transform)]
                    gdf = gpd.GeoDataFrame({"clase": [CLASES_CALADO[v - 1][2] for _, v in geoms], "calado_min": [CLASES_CALADO[v - 1][0] for _, v in geoms]}, geometry=[g_ for g_, _ in geoms], crs=crs).dissolve(by="clase", as_index=False)
                    gdf["area_km2"] = gdf.geometry.area / 1e6; _capa(gdf, g2 / "peligro", f"{c['escenario']}_{_marca(c['id'])}_clases_calado", archivos, crs)
                except Exception as e:
                    notas.append(f"Polígonos por clase de {c['id']}: {str(e)[:80]}")
        expo = exposicion(proyecto, cs, crs, g2, archivos, notas)
        if len(expo):
            _tabla(expo, g2, "resumen_exposicion_por_escenario", archivos)
    (g2).mkdir(parents=True, exist_ok=True)
    (g2 / "LEEME_BCA_FEMA.md").write_text(_leeme_bca(notas, bool(cs)), encoding="utf-8"); archivos.append(g2 / "LEEME_BCA_FEMA.md")
    # ---------------- 01 · hidro: calibración, observaciones, cuenca activa y lluvia areal (C24)
    gh = g1 / "hidro_calibracion"
    for sub, patron in (("calibracion/aceptadas", "**/*"), ("observaciones", "*")):
        o = proyecto / sub
        if o.exists():
            for f in o.glob(patron):
                if f.is_file() and not f.name.endswith(".bak") and ".bak_" not in f.name:
                    dst = gh / sub.split("/")[-1] / f.relative_to(o); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, dst); archivos.append(dst)
    bar = sorted((proyecto / "calibracion" / "barridos").glob("barrido_*")) if (proyecto / "calibracion" / "barridos").exists() else []
    if bar:
        for f in bar[-1].rglob("*"):
            if f.is_file():
                dst = gh / "ultimo_barrido" / f.relative_to(bar[-1]); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, dst); archivos.append(dst)
    act = proyecto / "cuenca" / "activa.json"
    if act.exists():
        a_ = json.loads(act.read_text(encoding="utf-8"))
        for f in (proyecto / a_["carpeta"]).glob("*"):
            if f.is_file():
                dst = g1 / "shapes" / "cuenca_activa" / f.name; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, dst); archivos.append(dst)
    if not (proyecto / "calibracion" / "aceptadas").exists():
        notas.append("hidro: no hay ninguna calibración aceptada (los resultados siguen «sin calibrar»).")
    # ---------------- 03 ENSO
    g3 = raiz / "03_ENSO_El_Nino_La_Nina"; notas3 = []; _enso(proyecto, g3, archivos, notas3)
    (g3 / "LEEME_ENSO.md").write_text(_leeme_enso(notas3), encoding="utf-8"); archivos.append(g3 / "LEEME_ENSO.md")
    # ---------------- índice
    (raiz / "00_LEEME.md").write_text(_leeme(datos, cs, notas + notas3), encoding="utf-8"); archivos.append(raiz / "00_LEEME.md")
    man = {"creado": datetime.now().isoformat(timespec="seconds"), "proyecto": datos.get("nombre"), "crs": crs, "aviso": AVISO, "programas": PROGRAMAS, "corridas": [c["id"] for c in cs], "notas": notas + notas3,
           "archivos": [{"ruta": str(a.relative_to(raiz)).replace("\\", "/"), "sha256": _sha(a), "bytes": a.stat().st_size} for a in archivos if a.exists()]}
    (raiz / "manifiesto.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    try:                                                                                                   # Omega O6: informe HTML autocontenido
        from .informe_html import construir as _informe
        man["informe_html"] = str(_informe(proyecto, datos, cs, raiz, man).relative_to(raiz))
    except Exception as e:
        man.setdefault("notas", []).append(f"Informe HTML: no se generó ({str(e)[:120]}).")
    return raiz, man


def _enso(proyecto, g3, archivos, notas):
    g3.mkdir(parents=True, exist_ok=True)
    ch = sorted((proyecto / "datos_descargados").glob("chirps_*/chirps_diario.csv")) + sorted((proyecto / "datos_descargados").glob("sitio_*/chirps/chirps_diario.csv"))
    if ch:
        x = pd.read_csv(max(ch, key=lambda p: p.stat().st_mtime), parse_dates=["fecha"]).set_index("fecha")
        for col in [c for c in ("celda_nex_mm", "media_caja_mm", "pixel_mm") if c in x.columns]:
            m = x[col].resample("MS").agg(["sum", "count"]); m.columns = ["lluvia_mm", "dias_con_dato"]; m["dias_mes"] = m.index.days_in_month; m["completo"] = m["dias_con_dato"] >= 0.9 * m["dias_mes"]
            m = m.reset_index().rename(columns={"fecha": "mes"}); _tabla(m, g3 / "lluvia", f"chirps_{col}_mensual", archivos)
        a = x["celda_nex_mm"].resample("YS").agg(["sum", "count"]) if "celda_nex_mm" in x else None
        if a is not None:
            a.columns = ["lluvia_mm", "dias_con_dato"]; a["completo"] = a["dias_con_dato"] >= 0.9 * 365; a = a.reset_index().rename(columns={"fecha": "anio"}); a["anio"] = a["anio"].dt.year; _tabla(a, g3 / "lluvia", "chirps_celda_nex_mm_anual", archivos)
    else:
        notas.append("ENSO: no hay serie CHIRPS en el proyecto (módulo 3 · CHIRPS).")
    try:                                                                                   # C25: lluvia registrada de la cuenca, rotulada (además de CHIRPS de la caja)
        from . import calibracion as K
        p_, msg = K.lluvia_cuenca(proyecto)
        if p_ is not None:
            m = p_.resample("MS").agg(["sum", "count"]); m.columns = ["lluvia_mm", "dias_con_dato"]; m["completo"] = m["dias_con_dato"] >= 0.9 * m.index.days_in_month
            m = m.reset_index().rename(columns={"fecha": "mes", "index": "mes"}); m["fuente"] = msg[:120]; _tabla(m, g3 / "lluvia", "lluvia_cuenca_registrada_mensual", archivos)
    except Exception as e:
        notas.append(f"ENSO: no se pudo exportar la lluvia de la cuenca: {str(e)[:80]}")
    pre = proyecto / "datos" / "series_premodulo"
    if pre.exists():
        for f in pre.glob("*"):
            (g3 / "series_premodulo").mkdir(parents=True, exist_ok=True); shutil.copy2(f, g3 / "series_premodulo" / f.name); archivos.append(g3 / "series_premodulo" / f.name)
    oni = _oni()
    if oni is not None:
        _tabla(oni, g3 / "indices", "oni_mensual_NOAA_CPC", archivos)
    else:
        notas.append("ENSO: no se pudo descargar el índice ONI de NOAA CPC (sin internet). Descárgalo de https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt y colócalo en 03_ENSO_El_Nino_La_Nina/indices/.")
    cm = sorted((proyecto / "registro" / "cmip6").glob("analisis_*")) if (proyecto / "registro" / "cmip6").exists() else []
    if cm:
        d = cm[-1]
        for nombre in ("factores_cc", "factores_por_modelo", "verificacion_2015_2025", "seleccionados", "metricas_modelos"):
            f = d / f"{nombre}.csv"
            if f.exists():
                _tabla(pd.read_csv(f), g3 / "cmip6", nombre, archivos)
    else:
        notas.append("ENSO: no hay análisis CMIP6 en el proyecto (módulo 10 · CMIP6; requiere la decisión de asumir la línea base).")


def _oni():
    """Índice Oceánico de El Niño (ONI, NOAA CPC): temporadas de 3 meses con su anomalía y la fase por umbral ±0,5 °C (clasificación simple: la regla oficial pide 5 temporadas consecutivas)."""
    try:
        import requests
        r = requests.get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt", timeout=(10, 30)); r.raise_for_status()
        filas = [l.split() for l in r.text.splitlines()[1:] if len(l.split()) >= 4]
        d = pd.DataFrame([{"temporada": a, "anio": int(b), "total": float(c), "ONI": float(e)} for a, b, c, e in filas])
        d["fase_umbral_0_5"] = np.where(d["ONI"] >= 0.5, "El Niño", np.where(d["ONI"] <= -0.5, "La Niña", "neutral")); return d
    except Exception:
        return None


def _leeme_bca(notas, hay):
    return f"""# Insumos para el análisis beneficio–costo (FEMA BCA)
{AVISO}

## Qué trae
- `peligro/`: calado máximo (m) por escenario (GeoTIFF) y polígonos por clase de calado (shapefile WGS84 y UTM + GeoPackage).
- `frecuencia/escenarios_frecuencia.csv|xlsx`: período de retorno, probabilidad anual, factor de cambio climático (escenarios X y Y).
- `exposicion/` y `resumen_exposicion_por_escenario`: edificaciones, población y vías por clase de calado, **solo si esas capas se descargaron** (Datos / GEE › Otras descargas).

## Qué NO trae (lo exige el análisis y debe aportarlo quien lo hace)
- Curvas calado–daño, valor de reposición y contenido de las edificaciones, costos de mitigación, vida útil y tasa de descuento.
- Calado = máximo simulado en celdas de 30 m a partir de un DSM; no es una huella observada ni está calibrado.
- La población de WorldPop es modelada (no censo); las edificaciones de Google Open Buildings son detecciones por satélite.

## Avisos de esta entrega
{chr(10).join('- ' + n for n in notas) if notas else '- (ninguno)'}
"""


def _leeme_enso(notas):
    return f"""# Insumos para el software de El Niño / La Niña
{AVISO}

- `lluvia/`: lluvia CHIRPS mensual y anual del sitio (con cobertura de días y bandera de mes/año completo). CHIRPS es un producto de satélite, no una medición de campo.
- `series_premodulo/`: series de lluvia y caudal que cargó el usuario en el premódulo (con su origen y huella en `indice.json`).
- `indices/`: índice ONI de NOAA CPC (si hubo internet), con fase por umbral ±0,5 °C.
- `cmip6/`: factores de cambio, verificación 2015–2025 y modelos seleccionados (solo si el usuario registró la decisión de asumir la línea base; solo SSP5-8.5).

## Avisos
{chr(10).join('- ' + n for n in notas) if notas else '- (ninguno)'}
"""


def _leeme(datos, cs, notas):
    return f"""# Entrega de UCEclima · {datos.get('nombre')}
{AVISO}

| Carpeta | Contenido |
|---|---|
| `01_resultados/` | tablas (CSV y Excel), mapas, figuras, rásteres y shapes (WGS84 y UTM + GPKG) de {len(cs)} corrida(s) |
| `02_BCA_FEMA/` | insumos para el análisis beneficio–costo (peligro, frecuencia, exposición) |
| `03_ENSO_El_Nino_La_Nina/` | insumos para el software de El Niño / La Niña (lluvia, series, ONI, CMIP6) |

Hay un programa más previsto: se añade como otra carpeta con la misma convención. `manifiesto.json` lista cada archivo con su huella (sha256).

## Avisos
{chr(10).join('- ' + n for n in notas) if notas else '- (ninguno)'}
"""


def listar(proyecto):
    out = []
    for d in sorted((Path(proyecto) / "entregas").glob("entrega_*"), reverse=True) if (Path(proyecto) / "entregas").exists() else []:
        m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8")) if (d / "manifiesto.json").exists() else {}
        out.append({"id": d.name, "creado": m.get("creado"), "archivos": len(m.get("archivos", [])), "corridas": len(m.get("corridas", [])), "notas": m.get("notas", [])})
    return out
