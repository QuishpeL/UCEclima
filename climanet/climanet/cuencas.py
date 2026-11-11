# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Preparación y diagnóstico de cuencas y ríos para CLIMANET (NO ejecuta simulaciones).

Comprueba, sin inventar nada:
  - identificadores (unicidad, formato), CRS horizontal y datum vertical declarado;
  - geometrías inválidas (se informa; la reparación se hace SOLO en una copia, con método explícito y diferencia de área);
  - solapes entre subcuencas y área calculada vs. AREA_KM2;
  - cobertura válida y cotas sospechosas de cada DEM dentro de cada cuenca (muestreo decimado, declarado);
  - correspondencia con el proyecto HEC-HMS (nombre, área; CN, retardo y red tomados del .basin, nunca del nombre);
  - ejes de ríos como CANDIDATOS de entrada (cruce con el dominio hidráulico); no son secciones medidas ni capacidad.
"""
import hashlib, json, re
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio import features
from rasterio.windows import from_bounds
from shapely.geometry import box
from shapely.validation import explain_validity, make_valid

PATRON_ID = re.compile(r"^[A-Z]{2}-\d{3}$")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------ lectura y CRS
def leer_capa(path, crs_horizontal="EPSG:32717"):
    """Lee una capa. Si su CRS es compuesto (horizontal + vertical desconocido) usa el componente horizontal y lo registra."""
    g = gpd.read_file(path)
    info = {"archivo": str(path), "crs_declarado": g.crs.to_string()[:120] if g.crs else None, "datum_vertical": "no aplica"}
    if g.crs is None:
        raise ValueError(f"{path}: sin CRS.")
    sub = getattr(g.crs, "sub_crs_list", [])
    if sub:
        horiz = sub[0]
        info["datum_vertical"] = "DESCONOCIDO (CRS compuesto con VCS sin nombre ni datum)"
        info["crs_horizontal"] = horiz.to_string()
        g = g.set_crs(horiz, allow_override=True)
    else:
        info["crs_horizontal"] = g.crs.to_string()
    if g.crs.to_epsg() != gpd.GeoSeries([], crs=crs_horizontal).crs.to_epsg():
        raise ValueError(f"{path}: CRS horizontal {g.crs.to_string()} distinto de {crs_horizontal}.")
    return g, info


# ------------------------------------------------------------------ identificadores y geometría
def diagnostico_ids(g, campo="nombre"):
    ids = g[campo].astype(str)
    dup = ids[ids.duplicated(keep=False)].unique().tolist()
    mal = [i for i in ids if not PATRON_ID.match(i)]
    return {"n": int(len(g)), "unicos": bool(ids.is_unique), "duplicados": dup, "formato_no_estandar": mal}


def diagnostico_geometria(g, campo="nombre", campo_area="AREA_KM2"):
    """Devuelve (tabla, g_reparada). La reparación (shapely.make_valid) se aplica SOLO a la copia."""
    filas, rep = [], g.copy()
    for i, r in g.iterrows():
        geom = r.geometry
        valida = bool(geom.is_valid)
        fila = {campo: r[campo], "valida": valida, "motivo": None if valida else explain_validity(geom),
                "area_calc_km2": geom.area / 1e6, "area_declarada_km2": float(r[campo_area]) if campo_area in g.columns else np.nan}
        if campo_area in g.columns and fila["area_declarada_km2"] > 0:
            fila["dif_area_calc_vs_declarada_pct"] = 100 * (fila["area_calc_km2"] / fila["area_declarada_km2"] - 1)
        if not valida:
            nueva = make_valid(geom)
            if nueva.geom_type in ("GeometryCollection", "MultiPolygon"):
                polis = [p for p in getattr(nueva, "geoms", [nueva]) if p.geom_type in ("Polygon", "MultiPolygon")]
                from shapely.ops import unary_union
                nueva = unary_union(polis)
            rep.at[i, "geometry"] = nueva
            fila.update(area_original_no_fiable=bool(geom.area <= 0 or not valida),
                        metodo_reparacion="shapely.make_valid (copia; el original no se modifica)",
                        area_reparada_km2=nueva.area / 1e6, dif_area_reparada_m2=nueva.area - geom.area,
                        dif_area_reparada_pct=(100 * (nueva.area / geom.area - 1) if geom.area > 0 else np.nan), tipo_original=geom.geom_type, tipo_reparado=nueva.geom_type)
        filas.append(fila)
    return pd.DataFrame(filas), rep


def solapes(g, campo="nombre", min_m2=1.0):
    """Pares de polígonos con intersección de área > min_m2 (se espera ~0 si son subcuencas incrementales)."""
    sidx = g.sindex
    filas = []
    for i, a in g.iterrows():
        for j in sidx.query(a.geometry, predicate="intersects"):
            if j <= g.index.get_loc(i):
                continue
            b = g.iloc[j]
            inter = a.geometry.intersection(b.geometry)
            if inter.area > min_m2:
                filas.append({"a": a[campo], "b": b[campo], "area_solape_m2": inter.area,
                              "pct_de_a": 100 * inter.area / a.geometry.area, "pct_de_b": 100 * inter.area / b.geometry.area,
                              "geometry": inter})
    return gpd.GeoDataFrame(filas, geometry="geometry", crs=g.crs) if filas else gpd.GeoDataFrame(
        {"a": [], "b": [], "area_solape_m2": []}, geometry=[], crs=g.crs)


# ------------------------------------------------------------------ cobertura de DEM por cuenca
def cobertura_dem(g, dem_path, campo="nombre", paso_m=30.0, cota_min=-20.0, cota_max=6400.0):
    """Cobertura válida y cotas sospechosas dentro de cada cuenca. Muestreo decimado (vecino más próximo) a ~paso_m:
    NO sustituye una revisión a resolución nativa; los conteos son de celdas muestreadas."""
    filas = []
    with rasterio.open(dem_path) as s:
        res = abs(s.res[0]); nd = s.nodata
        for _, r in g.iterrows():
            geom = r.geometry
            fila = {campo: r[campo], "dem": Path(dem_path).name, "paso_muestreo_m": max(paso_m, res), "area_cuenca_km2": geom.area / 1e6}
            inter = geom.intersection(box(*s.bounds))
            fila["pct_cuenca_dentro_rectangulo_dem"] = 100 * inter.area / geom.area if geom.area > 0 else np.nan
            if inter.is_empty or inter.area <= 0:
                fila.update(celdas_muestreadas=0, pct_valido=0.0, pct_nodata=np.nan, n_sospechosas=0, estado="sin_cobertura")
                filas.append(fila); continue
            x0, y0, x1, y1 = inter.bounds
            paso = max(paso_m, res)
            w, h = max(int((x1 - x0) / paso), 1), max(int((y1 - y0) / paso), 1)
            win = from_bounds(x0, y0, x1, y1, s.transform)
            arr = s.read(1, window=win, out_shape=(h, w), resampling=rasterio.enums.Resampling.nearest, boundless=True, fill_value=nd).astype("float64")
            tr = rasterio.transform.from_bounds(x0, y0, x1, y1, w, h)
            dentro = features.geometry_mask([inter], out_shape=(h, w), transform=tr, invert=True)
            v = arr[dentro]
            nodata = (v == nd) | ~np.isfinite(v) if nd is not None else ~np.isfinite(v)
            ok = v[~nodata]
            sosp = int(((ok < cota_min) | (ok > cota_max)).sum())
            fila.update(celdas_muestreadas=int(dentro.sum()), pct_valido=100 * float((~nodata).mean()) if len(v) else 0.0,
                        pct_nodata=100 * float(nodata.mean()) if len(v) else np.nan, n_sospechosas=sosp,
                        cota_min_m=float(ok.min()) if len(ok) else np.nan, cota_p1_m=float(np.percentile(ok, 1)) if len(ok) else np.nan,
                        cota_p99_m=float(np.percentile(ok, 99)) if len(ok) else np.nan, cota_max_m=float(ok.max()) if len(ok) else np.nan,
                        estado=("cobertura_completa" if len(ok) and (~nodata).mean() >= 0.99 and sosp == 0 else "revisar"),
                        criterio_sospechosa=f"< {cota_min} m o > {cota_max} m")
            filas.append(fila)
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ proyecto HEC-HMS
def leer_basin_hms(path):
    """Lee el .basin de HEC-HMS: subcuencas (área, CN, impermeable %, retardo, hidrograma unitario), tramos, uniones y
    destino aguas abajo de cada elemento. Los valores se copian tal cual; no se deduce nada del nombre."""
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    elems = {}
    for b in re.split(r"\nEnd:\s*\n", txt):
        m = re.match(r"\s*(Subbasin|Junction|Reach|Sink|Source|Reservoir|Diversion): (.+)", b)
        if not m:
            continue
        tipo, nombre = m.group(1), m.group(2).strip()
        get = lambda k: (re.search(r"\n\s*" + re.escape(k) + r":\s*([^\n]*)", b) or [None, None])[1]
        e = {"tipo": tipo, "nombre": nombre, "aguas_abajo": (get("Downstream") or "").strip() or None}
        if tipo == "Subbasin":
            e.update(area_km2=float(get("Area")), cn=float(get("Curve Number")), impermeable_pct=float(get("Percent Impervious Area")),
                     retardo_min=float(get("Lag")), hidrograma_unitario=get("Unitgraph Type"), perdidas=get("LossRate"),
                     transformacion=get("Transform"), flujo_base=get("Baseflow"))
        if tipo == "Reach":
            e.update(metodo=get("Route"), longitud_m=float(get("Length")) if get("Length") else None,
                     pendiente=float(get("Energy Slope")) if get("Energy Slope") else None)
        elems[nombre] = e
    return elems


def red_hms(elems):
    """Comprueba la red: destinos existentes, ciclos y ruta de cada subcuenca hasta el sumidero."""
    problemas, rutas = [], {}
    for n, e in elems.items():
        if e["aguas_abajo"] and e["aguas_abajo"] not in elems:
            problemas.append(f"{n}: aguas abajo '{e['aguas_abajo']}' no existe en el proyecto")
    for n, e in elems.items():
        if e["tipo"] != "Subbasin":
            continue
        ruta, cur, vistos = [n], e["aguas_abajo"], {n}
        while cur and cur in elems:
            if cur in vistos:
                problemas.append(f"ciclo en la red desde {n}"); break
            ruta.append(cur); vistos.add(cur); cur = elems[cur]["aguas_abajo"]
        rutas[n] = ruta
        if elems[ruta[-1]]["tipo"] != "Sink":
            problemas.append(f"{n}: la ruta no termina en un sumidero (termina en {ruta[-1]})")
    return rutas, problemas


def correspondencia(g, elems, campo="nombre", tol_area_pct=1.0):
    """Relaciona `nombre` del shapefile con subcuencas HMS. Coincidencia exacta o, si el formato difiere (p. ej. 'MI--070'),
    candidato por normalización SOLO si el área concuerda; queda como 'probable' y requiere confirmación humana."""
    sb = {n: e for n, e in elems.items() if e["tipo"] == "Subbasin"}
    filas, usados = [], set()
    for _, r in g.iterrows():
        n = str(r[campo]); a_shp = r.geometry.area / 1e6
        if n in sb:
            e, estado, cand = sb[n], "exacta", n
        else:
            norm = re.sub(r"-+", "-", n.strip().upper())
            cand = norm if norm in sb else None
            e = sb.get(cand) if cand else None
            estado = "probable_por_normalizacion_requiere_confirmacion" if e else "sin_correspondencia"
        fila = {"nombre_shp": n, "nombre_hms": cand if e else None, "estado": estado, "area_shp_km2": a_shp}
        if e:
            usados.add(cand)
            d = 100 * (a_shp / e["area_km2"] - 1) if e["area_km2"] else np.nan
            fila.update(area_hms_km2=e["area_km2"], dif_area_pct=d, area_concuerda=bool(abs(d) <= tol_area_pct),
                        cn_hms=e["cn"], impermeable_pct_hms=e["impermeable_pct"], retardo_min_hms=e["retardo_min"],
                        hidrograma_unitario_hms=e["hidrograma_unitario"], aguas_abajo_hms=e["aguas_abajo"])
            if estado.startswith("probable") and not fila["area_concuerda"]:
                fila["estado"] = "sin_correspondencia_area_distinta"
        filas.append(fila)
    solo_hms = sorted(set(sb) - usados)
    return pd.DataFrame(filas), solo_hms


# ------------------------------------------------------------------ ríos y dominio
def candidatos_entrada(rios, dominio, g_cuencas, campo="nombre", campo_rio="NOMBRE"):
    """Cruces de cada eje de río con el borde del dominio hidráulico. SOLO candidatos: sin sección, cota de fondo ni sentido
    de flujo confirmados."""
    filas = []
    borde = dominio.boundary
    for _, r in rios.iterrows():
        pts = r.geometry.intersection(borde)
        if pts.is_empty:
            continue
        for p in (pts.geoms if hasattr(pts, "geoms") else [pts]):
            if p.geom_type != "Point":
                continue
            cuencas = g_cuencas[g_cuencas.geometry.buffer(1.0).contains(p)][campo].tolist()
            lado = ("E" if abs(p.x - dominio.bounds[2]) < 1 else "O" if abs(p.x - dominio.bounds[0]) < 1 else
                    "N" if abs(p.y - dominio.bounds[3]) < 1 else "S")
            filas.append({"rio": r[campo_rio], "x": p.x, "y": p.y, "borde": lado, "cuencas_en_el_punto": ",".join(cuencas),
                          "estado": "candidata_no_confirmada", "geometry": p})
    return gpd.GeoDataFrame(filas, geometry="geometry", crs=rios.crs) if filas else gpd.GeoDataFrame(
        {"rio": []}, geometry=[], crs=rios.crs)


def areas_dominio(g, dominio, campo="nombre"):
    """Área total / interna (dentro del dominio 2D, lluvia sobre malla) / externa (fuera) de cada cuenca."""
    filas = []
    for _, r in g.iterrows():
        inter = r.geometry.intersection(dominio)
        filas.append({campo: r[campo], "area_total_km2": r.geometry.area / 1e6, "area_interna_km2": inter.area / 1e6,
                      "area_externa_km2": (r.geometry.area - inter.area) / 1e6,
                      "interseca_dominio": bool(inter.area > 0)})
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ cobertura a resolución nativa
def cobertura_nativa(g, dem_path, campo="nombre", cota_min=-20.0, cota_max=6400.0, franja=1500):
    """Cobertura y cotas sospechosas contando CADA celda nativa dentro de cada cuenca (lectura por franjas)."""
    from shapely.geometry import box as _box
    acc = {r[campo]: {"celdas": 0, "nodata": 0, "sospechosas": 0, "min": np.inf, "max": -np.inf} for _, r in g.iterrows()}
    with rasterio.open(dem_path) as s:
        b = _box(*s.bounds)
        for r0 in range(0, s.height, franja):
            win = rasterio.windows.Window(0, r0, s.width, min(franja, s.height - r0))
            caja = _box(*rasterio.windows.bounds(win, s.transform))
            cand = [(r[campo], r.geometry) for _, r in g.iterrows() if r.geometry.intersects(caja)]
            if not cand:
                continue
            a = s.read(1, window=win); tr = s.window_transform(win)
            for n, geom in cand:
                m = features.geometry_mask([geom], out_shape=a.shape, transform=tr, invert=True)
                if not m.any():
                    continue
                v = a[m].astype("float64")
                nd = ~np.isfinite(v) | ((v == s.nodata) if s.nodata is not None else False)
                ok = v[~nd]
                x = acc[n]; x["celdas"] += len(v); x["nodata"] += int(nd.sum())
                x["sospechosas"] += int(((ok < cota_min) | (ok > cota_max)).sum())
                if len(ok):
                    x["min"] = min(x["min"], float(ok.min())); x["max"] = max(x["max"], float(ok.max()))
    filas = []
    for n, x in acc.items():
        dentro = x["celdas"] > 0
        filas.append({campo: n, "dem": Path(dem_path).name, "resolucion": "nativa", "celdas_en_rectangulo": x["celdas"],
                      "pct_nodata": (100 * x["nodata"] / x["celdas"]) if dentro else np.nan,
                      "n_sospechosas": x["sospechosas"], "cota_min_m": x["min"] if dentro else np.nan, "cota_max_m": x["max"] if dentro else np.nan,
                      "criterio_sospechosa": f"< {cota_min} m o > {cota_max} m",
                      "estado": ("sin_cobertura" if not dentro else "cobertura_completa" if x["nodata"] == 0 and x["sospechosas"] == 0 else "revisar")})
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ áreas HMS: ¿incrementales o acumuladas?
def explicar_area_hms(g, area_hms_km2, nombre_propio, campo="nombre", max_n=4, tol_km2=0.01):
    """Busca combinaciones de polígonos cuya suma de áreas reproduce el área de HMS. Ayuda a detectar que el HMS usa áreas
    ACUMULADAS (o sumas de otras subcuencas). Son HIPÓTESIS aritméticas que hay que confirmar con la red y la cartografía."""
    from itertools import combinations
    a = {r[campo]: r.geometry.area / 1e6 for _, r in g.iterrows()}
    out = []
    for k in range(1, max_n + 1):
        for comb in combinations(a, k):
            if abs(sum(a[c] for c in comb) - area_hms_km2) <= tol_km2:
                out.append({"combinacion": list(comb), "suma_km2": sum(a[c] for c in comb)})
    return sorted(out, key=lambda d: (len(d["combinacion"]), abs(d["suma_km2"] - area_hms_km2)))[:5]
