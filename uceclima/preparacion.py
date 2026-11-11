# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""PREMÓDULO · Preparación de datos de ingreso.

Recibe datos crudos (lluvia en formato ancho de anuario INAMHI o largo, inventario de eventos de la SGR/SNGR, rásteres, etc.), los clasifica, los ordena a un formato
único, mide su calidad y los contrasta entre sí (lluvia diaria vs eventos del inventario). REGLAS: los archivos crudos NUNCA se modifican; todo lo ordenado se escribe en
una carpeta nueva con marca de tiempo; lo ausente queda ausente (nunca 0); no se promedian ni suman valores contradictorios (se marcan «conflicto» y quedan vacíos);
el contraste es descriptivo (no demuestra causalidad ni calibra nada) y el inventario de eventos está sujeto a subregistro.
"""
import calendar, hashlib, json, math, re, unicodedata
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

MAX_ARCHIVOS = 400
TIPOS_HIDROMET = ("inundacion", "lluvias intensas", "deslizamiento", "movimiento en masa", "aluvion", "avenida torrencial", "desbordamiento", "socavamiento", "hundimiento", "erosion")
CODIGOS_FALTANTE = {-99.0, -999.0, -9999.0, 999.0, 9999.0}


class PrepError(ValueError):
    pass


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def _num(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    t = str(x).strip().replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return np.nan


# ------------------------------------------------------------------------------------------------ escaneo y clasificación
def _filas_excel(path, hoja, n):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[hoja]
    out = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i >= n:
            break
        out.append(list(r))
    wb.close()
    return out


def _clasificar_tabla(filas):
    """Clasifica una tabla (lista de filas) por su contenido. Devuelve (tipo, detalle)."""
    for i, r in enumerate(filas[:15]):
        celdas = [_norm(c) for c in r if c is not None]
        if not celdas:
            continue
        if "fecha del evento" in celdas and "evento" in celdas:
            return "inventario_eventos", f"encabezado en la fila {i + 1}"
        if "anio" in celdas and "mes" in celdas and sum(1 for c in celdas if re.fullmatch(r"v?\d{1,2}( \d)?", c)) >= 28:
            return "precipitacion_ancha_inamhi", f"encabezado en la fila {i + 1} (año/mes + 31 días)"
        if any(c in ("fecha", "date", "fecha hora", "datetime") for c in celdas) and any(re.search(r"precip|lluvia|rain|pp\b", c) for c in celdas):
            return "precipitacion_larga", f"encabezado en la fila {i + 1}"
        if any(c in ("fecha", "date", "fecha hora", "datetime") for c in celdas) and any(re.search(r"caudal|^q$|nivel|altura|discharge", c) for c in celdas):
            return "caudal_largo", f"encabezado en la fila {i + 1}"
    return "tabla_otra", "no reconocida"


def clasificar_archivo(p):
    p = Path(p); ext = p.suffix.lower(); info = {"archivo": p.name, "ruta": str(p), "extension": ext, "mb": round(p.stat().st_size / 1e6, 3), "tipo": "otro", "detalle": "", "hojas": []}
    try:
        if ext in (".csv", ".txt"):
            filas = pd.read_csv(p, sep=None, engine="python", nrows=15, header=None, dtype=object, encoding="utf-8", encoding_errors="replace").values.tolist()
            t, d = _clasificar_tabla(filas); info.update(tipo=t, detalle=d)
        elif ext in (".xlsx", ".xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True); hojas = list(wb.sheetnames); wb.close()
            for h in hojas:
                t, d = _clasificar_tabla(_filas_excel(p, h, 15)); info["hojas"].append({"hoja": h, "tipo": t, "detalle": d})
            utiles = [h for h in info["hojas"] if h["tipo"] != "tabla_otra"]
            if utiles:
                info.update(tipo=utiles[0]["tipo"], detalle=f"hoja «{utiles[0]['hoja']}»: {utiles[0]['detalle']}")
            else:
                info.update(tipo="excel_otro", detalle=f"{len(hojas)} hoja(s) no reconocidas")
        elif ext in (".tif", ".tiff"):
            import rasterio
            with rasterio.open(p) as s:
                info.update(tipo="raster", detalle=f"{s.width}×{s.height} px · {abs(s.res[0]):g} · {s.crs.to_string() if s.crs else 'SIN CRS'}")
        elif ext in (".shp", ".gpkg", ".geojson"):
            info.update(tipo="vector", detalle="capa vectorial")
        elif ext in (".pdf", ".doc", ".docx"):
            info.update(tipo="documento")
        elif ext in (".zip", ".rar", ".7z"):
            info.update(tipo="comprimido", detalle="descomprime antes de preparar")
    except Exception as e:
        info.update(tipo="ilegible", detalle=str(e)[:120])
    return info


def escanear(carpeta):
    c = Path(carpeta)
    if not c.is_dir():
        raise PrepError("No existe esa carpeta.")
    archivos = [f for f in sorted(c.rglob("*")) if f.is_file() and not f.name.startswith(("~$", ".")) and len(f.relative_to(c).parts) <= 4][:MAX_ARCHIVOS]
    res = [clasificar_archivo(f) for f in archivos]
    por_tipo = {}
    for r in res:
        por_tipo[r["tipo"]] = por_tipo.get(r["tipo"], 0) + 1
    return {"carpeta": str(c), "n_archivos": len(res), "por_tipo": por_tipo, "archivos": res}


# ------------------------------------------------------------------------------------------------ lluvia ancha (anuario INAMHI)
def leer_precip_ancha(path, hoja=None):
    """Convierte un anuario ancho (estación, año, mes, 31 días) a formato largo. Las columnas se identifican por su CONTENIDO, no por el encabezado."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    hoja = hoja or next((h for h in wb.sheetnames if _clasificar_tabla(_filas_excel(path, h, 15))[0] == "precipitacion_ancha_inamhi"), wb.sheetnames[0])
    filas = [list(r) for r in wb[hoja].iter_rows(values_only=True)]
    wb.close()
    problemas = []
    # fila de encabezado = la que tiene 'anio' y 'mes'
    h = next((i for i, r in enumerate(filas[:20]) if "anio" in [_norm(c) for c in r if c is not None] and "mes" in [_norm(c) for c in r if c is not None]), None)
    if h is None:
        raise PrepError("No se encontró el encabezado con año y mes.")
    if h > 0:
        problemas.append({"codigo": "filas_titulo", "n": h, "texto": f"{h} fila(s) de título antes del encabezado (se ignoran)."})
    datos = [r for r in filas[h + 1:]]
    util, grupos = [], []
    for r in datos:
        n = sum(1 for c in r if c is not None and str(c).strip() != "")
        (util if n >= 5 else grupos).append(r)
    grupos = [str(next((c for c in r if c is not None), "")) for r in grupos if any(c is not None for c in r)]
    if grupos:
        problemas.append({"codigo": "filas_de_grupo", "n": len(grupos), "texto": f"{len(grupos)} fila(s) de grupo/región sin datos ({', '.join(sorted(set(grupos))[:6])}); se ignoran."})
    # posición del año por contenido
    pos = []
    for r in util[:400]:
        for j in range(len(r) - 1):
            a, m = _num(r[j]), _num(r[j + 1])
            if 1900 <= a <= 2100 and 1 <= m <= 12 and float(a).is_integer() and float(m).is_integer():
                pos.append(j); break
    if not pos:
        raise PrepError("No se pudo ubicar la columna de año y mes por su contenido.")
    py = max(set(pos), key=pos.count); pm = py + 1; pd0 = py + 2
    ncols = max(len(r) for r in util)
    if ncols - pd0 < 31:
        raise PrepError(f"Solo hay {ncols - pd0} columnas de días tras el mes; se esperaban 31.")
    enc = [_norm(c) for c in filas[h]]
    esperadas = {"estacion": 0, "anio": 6, "mes": 7}
    if enc and enc.index("anio") != py:
        problemas.append({"codigo": "encabezados_corridos", "n": py - enc.index("anio"),
                          "texto": f"Los encabezados están corridos {py - enc.index('anio')} columna(s): «anio» está rotulada en la columna {enc.index('anio') + 1} pero el año está en la columna {py + 1} (se corrigió leyendo el contenido)."})
    # nombre/coordenadas por contenido
    reg, filas_largo, cat = [], [], {}
    dup_claves = {}
    for r in util:
        r = list(r) + [None] * (ncols - len(r))
        est = str(r[0]).strip() if r[0] is not None else ""
        a, m = _num(r[py]), _num(r[pm])
        if not est or not (1900 <= a <= 2100) or not (1 <= m <= 12):
            problemas.append({"codigo": "fila_ilegible", "n": 1, "texto": f"Fila sin estación/año/mes válidos: {[str(c)[:12] for c in r[:9]]}"}); continue
        a, m = int(a), int(m)
        textos = [str(c).strip() for c in r[1:py] if isinstance(c, str) and c.strip() and not re.fullmatch(r"[-+]?\d+([.,]\d+)?", c.strip())]
        nums = [(_num(c)) for c in r[1:py] if not (isinstance(c, str) and not re.fullmatch(r"[-+]?\d+([.,]\d+)?", c.strip()))]
        nums = [x for x in nums if not math.isnan(x)]
        lon = next((x for x in nums if -82 <= x <= -74 and abs(x) > 5), np.nan); lat = next((x for x in nums if -6 <= x <= 2 and abs(x) <= 6 and x != lon), np.nan)
        alt = next((x for x in nums if x not in (lon, lat) and -10 <= x <= 6000), np.nan)
        if est not in cat:
            cat[est] = {"estacion": est, "nombre": next((t for t in textos if t != est), ""), "lon": lon, "lat": lat, "altitud_m": alt}
        clave = (est, a, m)
        dup_claves.setdefault(clave, []).append(r)
        if len(dup_claves[clave]) > 1:
            continue
        nd = calendar.monthrange(a, m)[1]
        for d in range(1, 32):
            v = r[pd0 + d - 1]
            if d > nd:
                if v is not None and str(v).strip() != "":
                    reg.append(("dia_inexistente", est, a, m, d))
                continue
            bandera, x = "ok", np.nan
            if v is None or str(v).strip() == "":
                bandera = "ausente"
            else:
                x = _num(v)
                if math.isnan(x):
                    bandera = "texto_no_numerico"
                elif x in CODIGOS_FALTANTE:
                    x, bandera = np.nan, "codigo_faltante"
                elif x < 0:
                    x, bandera = np.nan, "negativo"
                elif x > 400:
                    bandera = "sospechoso_>400"
            filas_largo.append((est, pd.Timestamp(a, m, d), x, bandera))
    conf = 0
    for k, lst in dup_claves.items():
        if len(lst) > 1:
            conf += 1
    if conf:
        problemas.append({"codigo": "meses_repetidos", "n": conf, "texto": f"{conf} combinaciones estación-año-mes repetidas: solo se usó la primera (revisa si difieren)."})
    inex = [x for x in reg if x[0] == "dia_inexistente"]
    if inex:
        problemas.append({"codigo": "dias_inexistentes", "n": len(inex), "texto": f"{len(inex)} celdas con valor en días que no existen (p. ej. 30 de febrero); se descartan."})
    largo = pd.DataFrame(filas_largo, columns=["estacion", "fecha", "precipitacion_mm", "bandera"])
    cont = largo["bandera"].value_counts().to_dict()
    for k, txt in (("texto_no_numerico", "celdas con texto no numérico"), ("codigo_faltante", "celdas con código de faltante (-99, 999, 9999…)"), ("negativo", "valores negativos"), ("sospechoso_>400", "valores > 400 mm/día (se conservan, marcados)")):
        if cont.get(k):
            problemas.append({"codigo": k, "n": int(cont[k]), "texto": f"{cont[k]} {txt}."})
    catalogo = pd.DataFrame(list(cat.values()))
    return {"largo": largo, "catalogo": catalogo, "problemas": problemas, "hoja": hoja, "formato": "ancho (año, mes, 31 días)"}


# ------------------------------------------------------------------------------------------------ lluvia larga
def leer_precip_larga(path, estacion_defecto=None):
    p = Path(path)
    df = pd.read_csv(p, sep=None, engine="python", dtype=str, encoding="utf-8", encoding_errors="replace") if p.suffix.lower() != ".xlsx" else pd.read_excel(p, dtype=str)
    cols = {_norm(c): c for c in df.columns}
    cf = next((cols[k] for k in cols if k in ("fecha", "date", "fecha hora", "datetime")), None)
    cp = next((cols[k] for k in cols if re.search(r"precip|lluvia|rain|^pp$", k)), None)
    ce = next((cols[k] for k in cols if re.search(r"estacion|codigo|station|^id$", k)), None)
    if not cf or not cp:
        raise PrepError("El archivo largo necesita columnas de fecha y precipitación.")
    problemas = []
    f = pd.to_datetime(df[cf], errors="coerce")
    malas = int(f.isna().sum())
    if malas:
        problemas.append({"codigo": "fechas_ilegibles", "n": malas, "texto": f"{malas} filas con fecha ilegible (se descartan)."})
    v = pd.to_numeric(df[cp].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    if ce:
        est = df[ce].astype("string").str.strip()
        vacia = est.isna() | (est == "") | (est.str.lower() == "nan")
        unicas = est[~vacia].unique()
        sin_val = vacia & v.isna()
        con_val = vacia & v.notna()
        if con_val.any():
            problemas.append({"codigo": "valores_sin_estacion", "n": int(con_val.sum()), "texto": f"{int(con_val.sum())} filas con lluvia pero SIN código de estación: no se asignan a ninguna (revísalas)."})
        if sin_val.any():
            if len(unicas) == 1:
                est = est.mask(sin_val, unicas[0])
                problemas.append({"codigo": "filas_sin_estacion", "n": int(sin_val.sum()), "texto": f"{int(sin_val.sum())} filas vacías (sin estación y sin valor) entre los datos de {unicas[0]}: se asumieron días faltantes de esa única estación del archivo (inferencia; verifica en el original)."})
            else:
                problemas.append({"codigo": "filas_sin_estacion", "n": int(sin_val.sum()), "texto": f"{int(sin_val.sum())} filas vacías sin estación y el archivo tiene {len(unicas)} estaciones: no se asignan."})
        est = est.where(~(vacia & ~sin_val) & ~(vacia & (len(unicas) != 1)), None)
        est = est.astype(object).where(est.notna(), "SIN_ESTACION")
    else:
        est = pd.Series(estacion_defecto or "SIN_ID", index=df.index)
    largo = pd.DataFrame({"estacion": est, "fecha": f, "precipitacion_mm": v})[f.notna()]
    largo = largo[largo["estacion"] != "SIN_ESTACION"]
    largo["bandera"] = np.where(largo["precipitacion_mm"].isna(), "ausente", "ok")
    ne = int((largo["precipitacion_mm"] < 0).sum())
    if ne:
        problemas.append({"codigo": "negativo", "n": ne, "texto": f"{ne} valores negativos (se invalidan)."}); largo.loc[largo["precipitacion_mm"] < 0, ["precipitacion_mm", "bandera"]] = [np.nan, "negativo"]
    dup = largo.duplicated(["estacion", "fecha"], keep=False)
    if dup.any():
        problemas.append({"codigo": "fechas_repetidas", "n": int(dup.sum()), "texto": f"{int(dup.sum())} filas con estación y fecha repetidas; se conserva la primera."})
        largo = largo.drop_duplicates(["estacion", "fecha"])
    largo["fecha"] = largo["fecha"].dt.normalize()
    return {"largo": largo.sort_values(["estacion", "fecha"]).reset_index(drop=True), "catalogo": pd.DataFrame({"estacion": largo["estacion"].unique()}), "problemas": problemas, "hoja": None, "formato": "largo"}


# ------------------------------------------------------------------------------------------------ calidad
def calidad_serie(largo):
    """Calidad por estación sobre el calendario completo (los días que faltan en el archivo cuentan como ausentes)."""
    out = {}
    for est, g in largo.groupby("estacion"):
        s = g.drop_duplicates("fecha").set_index("fecha")["precipitacion_mm"].sort_index()
        if s.empty:
            continue
        cal = pd.date_range(s.index.min(), s.index.max(), freq="D")
        s = s.reindex(cal)
        n = len(cal); con = int(s.notna().sum())
        por_anio = s.groupby(s.index.year).agg(["count", "size"])
        sin = [int(a) for a, r in por_anio.iterrows() if r["count"] == 0]
        incompletos = [{"anio": int(a), "dias_con_dato": int(r["count"]), "dias": int(r["size"])} for a, r in por_anio.iterrows() if 0 < r["count"] < 0.9 * r["size"]]
        falta = s.isna().values; huecos = []; i = 0
        while i < n:
            if falta[i]:
                j = i
                while j + 1 < n and falta[j + 1]:
                    j += 1
                huecos.append((int(j - i + 1), cal[i].date().isoformat(), cal[j].date().isoformat())); i = j + 1
            else:
                i += 1
        huecos.sort(reverse=True)
        v = s.dropna()
        cero = (v == 0).values; rmax = cur = 0
        for z in cero:
            cur = cur + 1 if z else 0; rmax = max(rmax, cur)
        out[est] = {"inicio": cal[0].date().isoformat(), "fin": cal[-1].date().isoformat(), "dias_calendario": n, "dias_con_dato": con, "completitud_pct": round(100 * con / n, 1),
                    "anios_sin_ningun_dato": sin, "anios_incompletos_<90%": incompletos, "mayores_huecos": [{"dias": a, "desde": b, "hasta": c} for a, b, c in huecos[:5]], "n_huecos": len(huecos),
                    "max_mm_dia": float(v.max()) if len(v) else None, "fecha_max": v.idxmax().date().isoformat() if len(v) else None, "p99_dias_lluviosos_mm": float(v[v >= 1].quantile(.99)) if (v >= 1).any() else None,
                    "dias_lluviosos_pct": round(100 * float((v >= 1).mean()), 1) if len(v) else None, "racha_maxima_dias_en_cero": int(rmax), "valores_>200_mm": int((v > 200).sum()),
                    "total_anual_medio_mm": round(float(v.groupby(v.index.year).sum()[[a for a, r in por_anio.iterrows() if r["count"] >= 0.9 * r["size"]]].mean()), 0) if any(r["count"] >= 0.9 * r["size"] for _, r in por_anio.iterrows()) else None}
    return out


def fusionar(fuentes):
    """Une varias fuentes de lluvia por estación y fecha. Dato en una sola fuente => se toma (origen anotado). En ambas e iguales => ok. En ambas y distintos => CONFLICTO (queda vacío)."""
    partes = []
    for nombre, largo in fuentes:
        d = largo.copy(); d["fuente"] = nombre; partes.append(d)
    todo = pd.concat(partes, ignore_index=True)
    res, informe = [], {"conflictos": 0, "rellenados_desde_otra_fuente": 0, "coinciden": 0, "ejemplos_conflicto": [], "dias_solo_en_una_fuente": {}}
    for (est, f), g in todo.groupby(["estacion", "fecha"], sort=True):
        con = g[g["precipitacion_mm"].notna()]
        if len(con) == 0:
            res.append((est, f, np.nan, g["bandera"].iloc[0], g["fuente"].iloc[0])); continue
        if con["precipitacion_mm"].round(3).nunique() > 1:
            informe["conflictos"] += 1
            if len(informe["ejemplos_conflicto"]) < 8:
                informe["ejemplos_conflicto"].append({"estacion": est, "fecha": f.date().isoformat(), "valores": {r.fuente: float(r.precipitacion_mm) for r in con.itertuples()}})
            res.append((est, f, np.nan, "conflicto", "+".join(con["fuente"]))); continue
        if len(g) == 1:
            informe["dias_solo_en_una_fuente"][g["fuente"].iloc[0]] = informe["dias_solo_en_una_fuente"].get(g["fuente"].iloc[0], 0) + 1
        if len(g) > len(con):
            informe["rellenados_desde_otra_fuente"] += 1; res.append((est, f, float(con["precipitacion_mm"].iloc[0]), "ok_solo_" + con["fuente"].iloc[0], con["fuente"].iloc[0]))
        else:
            if len(con) > 1:
                informe["coinciden"] += 1
            res.append((est, f, float(con["precipitacion_mm"].iloc[0]), con["bandera"].iloc[0], "+".join(con["fuente"])))
    return pd.DataFrame(res, columns=["estacion", "fecha", "precipitacion_mm", "bandera", "fuente"]), informe


# ------------------------------------------------------------------------------------------------ inventario de eventos (SGR/SNGR)
def leer_inventario(path, hoja=None):
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True); hojas = wb.sheetnames; wb.close()
        hoja = hoja or next((h for h in hojas if _clasificar_tabla(_filas_excel(p, h, 15))[0] == "inventario_eventos"), None)
        if hoja is None:
            raise PrepError("No se encontró una hoja con el inventario (columnas EVENTO y FECHA DEL EVENTO).")
        df = pd.read_excel(p, sheet_name=hoja)
    else:
        df = pd.read_csv(p, sep=None, engine="python", encoding="utf-8", encoding_errors="replace")
    ren = {}
    for c in df.columns:
        n = _norm(c)
        for clave, pat in (("provincia", r"^provincia$"), ("canton", r"^canton$"), ("parroquia", r"^parroquias?$"), ("sector", r"comunidad|barrio|sector"), ("lat", r"^latitud$"), ("lon", r"^longitud$"),
                           ("evento", r"^evento$"), ("causa", r"^causa$"), ("categoria", r"categoria"), ("fecha", r"fecha del evento|^fecha$"), ("fallecidas", r"^fallecid"), ("heridas", r"^heridas"),
                           ("desaparecidas", r"desaparecid"), ("familias_afectadas", r"^familias afectadas"), ("personas_afectadas", r"personas afectadas"), ("viviendas_afectadas", r"viviendas afectadas"),
                           ("viviendas_destruidas", r"viviendas destruidas"), ("ha_cultivo_afectadas", r"cultivo afectadas"), ("descripcion", r"descripcion")):
            if re.search(pat, n) and clave not in ren.values():
                ren[c] = clave; break
    d = df.rename(columns=ren)
    for obl in ("evento", "fecha"):
        if obl not in d.columns:
            raise PrepError(f"Al inventario le falta la columna {obl.upper()}.")
    problemas = []
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    nf = int(d["fecha"].isna().sum())
    if nf:
        problemas.append({"codigo": "fechas_nulas", "n": nf, "texto": f"{nf} eventos sin fecha legible (no se pueden contrastar)."})
    for c in ("lat", "lon", "fallecidas", "heridas", "desaparecidas", "familias_afectadas", "personas_afectadas", "viviendas_afectadas", "viviendas_destruidas", "ha_cultivo_afectadas"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["tipo_norm"] = d["evento"].map(_norm)
    d["es_hidromet"] = d["tipo_norm"].map(lambda t: any(k in t for k in TIPOS_HIDROMET))
    if "lat" in d.columns and "lon" in d.columns:
        u = d[["lat", "lon"]].drop_duplicates().shape[0]; con = int(d[["lat", "lon"]].notna().all(axis=1).sum())
        fuera = int(((d["lat"] < -5.5) | (d["lat"] > 2) | (d["lon"] < -92) | (d["lon"] > -74.5)).sum())
        if fuera:
            problemas.append({"codigo": "coordenadas_fuera_de_ecuador", "n": fuera, "texto": f"{fuera} eventos con coordenadas fuera de Ecuador."})
        if con and u < 0.7 * con:
            problemas.append({"codigo": "coordenadas_repetidas", "n": con - u, "texto": f"Solo {u} coordenadas distintas en {con} eventos: muchas son centroides de parroquia/cantón, no el sitio real."})
        sin = len(d) - con
        if sin:
            problemas.append({"codigo": "sin_coordenadas", "n": sin, "texto": f"{sin} eventos sin coordenadas: solo se pueden filtrar por cantón/parroquia."})
    dup = int(d.duplicated(["fecha", "evento"] + [c for c in ("canton", "parroquia", "sector") if c in d.columns]).sum())
    if dup:
        problemas.append({"codigo": "posibles_duplicados", "n": dup, "texto": f"{dup} filas con igual fecha, tipo y lugar (posibles duplicados; no se eliminan)."})
    por_anio = d[d["es_hidromet"] & d["fecha"].notna()].groupby(d["fecha"].dt.year).size()
    if len(por_anio) >= 6:
        ult, prev = por_anio.iloc[-3:].mean(), por_anio.iloc[:-3].mean()
        if prev > 0 and ult / prev > 3:
            problemas.append({"codigo": "registro_no_homogeneo", "n": int(por_anio.iloc[-3:].sum()), "texto": f"Los registros hidrometeorológicos pasan de ~{prev:.0f} por año a ~{ult:.0f} por año en los últimos 3 años: suele reflejar un cambio en la práctica de reporte, no solo más eventos. No lo uses como tendencia sin comprobarlo."})
    resumen = {"n_eventos": int(len(d)), "n_hidromet": int(d["es_hidromet"].sum()), "periodo": [None if d["fecha"].isna().all() else d["fecha"].min().date().isoformat(), None if d["fecha"].isna().all() else d["fecha"].max().date().isoformat()],
               "por_tipo": d["evento"].value_counts().head(12).to_dict(), "hoja": hoja,
               "advertencia": "El inventario de eventos tiene subregistro y sesgo hacia donde hay población y reporte; la ausencia de un evento no prueba que no ocurrió."}
    return {"eventos": d, "problemas": problemas, "resumen": resumen}


# ------------------------------------------------------------------------------------------------ contraste lluvia vs eventos
def _haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2); dl = np.radians(lon2 - lon1); dp = p2 - p1
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def contrastar(serie, eventos, estacion_lat=None, estacion_lon=None, radio_km=30.0, cantones=None, solo_hidromet=True, ventana_dias=3):
    """serie: Series diaria (índice fecha, mm, NaN = ausente). eventos: DataFrame de leer_inventario()['eventos']. Contraste descriptivo, sin causalidad."""
    s = serie.sort_index().astype(float)
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
    ev = eventos[eventos["fecha"].notna()].copy()
    if solo_hidromet:
        ev = ev[ev["es_hidromet"]]
    filtro = []
    if cantones:
        nc = {_norm(c) for c in cantones}
        mc = ev["canton"].map(_norm).isin(nc) if "canton" in ev.columns else pd.Series(False, index=ev.index)
        filtro.append("cantón en " + ", ".join(cantones))
    else:
        mc = pd.Series(False, index=ev.index)
    if estacion_lat is not None and estacion_lon is not None and {"lat", "lon"} <= set(ev.columns) and radio_km:
        dist = _haversine(estacion_lat, estacion_lon, ev["lat"].values, ev["lon"].values)
        mr = pd.Series(dist <= radio_km, index=ev.index).fillna(False); ev["dist_km"] = dist; filtro.append(f"a ≤ {radio_km:g} km de la estación")
    else:
        mr = pd.Series(False, index=ev.index)
    if cantones or (estacion_lat is not None and radio_km):
        ev = ev[mc | mr]
    if ev.empty:
        raise PrepError("Ningún evento cumple el filtro de lugar (cantón o distancia a la estación).")
    w = int(ventana_dias)
    acum = s.rolling(w, min_periods=w).sum()
    ini, fin = s.index.min(), s.index.max()
    enperiodo = ev[(ev["fecha"] >= ini) & (ev["fecha"] <= fin)].copy()
    fuera = len(ev) - len(enperiodo)
    n_anios = max((fin - ini).days / 365.25, 1e-9)
    valores = acum.dropna()
    filas = []
    for r in enperiodo.itertuples():
        d = pd.Timestamp(r.fecha).normalize()
        a1 = s.get(d, np.nan); aw = acum.get(d, np.nan)
        ventana = s.loc[d - pd.Timedelta(days=w - 1):d]; cobertura = int(ventana.notna().sum())
        pct = float((valores <= aw).mean() * 100) if not math.isnan(aw) else np.nan
        exc = int((valores >= aw).sum()) if not math.isnan(aw) else 0
        filas.append({"fecha": d.date().isoformat(), "evento": r.evento, "canton": getattr(r, "canton", ""), "parroquia": getattr(r, "parroquia", ""), "dist_km": None if "dist_km" not in enperiodo.columns else round(float(getattr(r, "dist_km")), 1),
                      "mm_dia": None if math.isnan(a1) else round(float(a1), 1), f"mm_{w}d": None if math.isnan(aw) else round(float(aw), 1), "dias_con_dato_ventana": cobertura,
                      f"percentil_{w}d": None if math.isnan(pct) else round(pct, 1), f"retorno_empirico_{w}d_anios": None if exc == 0 else round(n_anios / exc, 2),
                      "familias_afectadas": getattr(r, "familias_afectadas", np.nan), "viviendas_afectadas": getattr(r, "viviendas_afectadas", np.nan), "fallecidas": getattr(r, "fallecidas", np.nan)})
    tabla = pd.DataFrame(filas)
    pcol = f"percentil_{w}d"
    resumen = {"estacion_periodo": [ini.date().isoformat(), fin.date().isoformat()], "ventana_dias": w, "filtro_lugar": " o ".join(filtro) or "sin filtro", "eventos_en_filtro": int(len(ev)), "eventos_dentro_del_periodo_de_lluvia": int(len(enperiodo)),
               "eventos_fuera_del_periodo": int(fuera)}
    if len(tabla):
        ok = tabla[pcol].dropna()
        resumen.update(eventos_con_dato_de_lluvia=int(len(ok)), percentil_mediano=None if ok.empty else round(float(ok.median()), 1),
                       clases_percentil={"<50": int((ok < 50).sum()), "50-90": int(((ok >= 50) & (ok < 90)).sum()), "90-99": int(((ok >= 90) & (ok < 99)).sum()), ">=99": int((ok >= 99).sum())})
    # inverso: ¿qué fracción de los días de cada clase de lluvia tuvo un evento del inventario (±1 día)?
    fechas_ev = pd.DatetimeIndex(pd.to_datetime(enperiodo["fecha"]).dt.normalize().unique())
    marca = pd.Series(0, index=s.index)
    for d in fechas_ev:
        marca.loc[d - pd.Timedelta(days=1):d + pd.Timedelta(days=1)] = 1
    base = pd.DataFrame({"acum": acum, "evento": marca}).dropna()
    # solo desde que el inventario existe
    if len(enperiodo):
        base = base[base.index >= pd.Timestamp(enperiodo["fecha"].min()) - pd.Timedelta(days=30)]
    clases = []
    if len(base) > 50:
        lim = [-1e9, 0.5, 5, 20, 50, 100, 1e9]
        etq = ["≈0", "0,5–5", "5–20", "20–50", "50–100", ">100"]
        base["clase"] = pd.cut(base["acum"], lim, labels=etq)
        for c, g in base.groupby("clase", observed=True):
            clases.append({"mm_" + str(w) + "d": str(c), "dias": int(len(g)), "dias_con_evento_±1d": int(g["evento"].sum()), "tasa_pct": round(100 * float(g["evento"].mean()), 1)})
    avisos = ["Descriptivo: coincidencia en fecha no es causalidad. El inventario tiene subregistro y puede ubicar el evento en un centroide, no en el sitio.",
              "La lluvia es de UNA estación; una tormenta localizada puede no verse en ella.",
              "Los percentiles se calculan sobre toda la historia disponible de la estación; el retorno empírico no ajusta ninguna distribución."]
    if resumen.get("eventos_dentro_del_periodo_de_lluvia", 0) < 10:
        avisos.append("Muy pocos eventos dentro del periodo de lluvia: cualquier conclusión sería frágil.")
    return {"tabla": tabla, "resumen": resumen, "tasa_por_clase": clases, "avisos": avisos}


# ------------------------------------------------------------------------------------------------ ordenar y guardar
def ordenar_y_guardar(entradas, salida, inventario=None):
    """entradas: lista de rutas de archivos de lluvia (anchos o largos). Escribe una carpeta NUEVA con todo ordenado. No modifica los crudos."""
    salida = Path(salida)
    marca = f"{datetime.now():%Y%m%d_%H%M%S}"
    dest = salida / f"preparados_{marca}"
    if dest.exists():
        raise PrepError("La carpeta de salida ya existe; no se sobrescribe.")
    fuentes, problemas, catalogos, manifest = [], {}, [], {"entradas": []}
    for ruta in entradas:
        info = clasificar_archivo(ruta)
        if info["tipo"] == "precipitacion_ancha_inamhi":
            r = leer_precip_ancha(ruta)
        elif info["tipo"] == "precipitacion_larga":
            r = leer_precip_larga(ruta, estacion_defecto=Path(ruta).stem)
        else:
            raise PrepError(f"{Path(ruta).name}: no es un archivo de lluvia reconocible ({info['tipo']}).")
        fuentes.append((Path(ruta).name, r["largo"])); problemas[Path(ruta).name] = r["problemas"]; catalogos.append(r["catalogo"].assign(fuente=Path(ruta).name))
        manifest["entradas"].append({"archivo": Path(ruta).name, "ruta": str(Path(ruta).resolve()), "sha256": sha256(ruta), "tipo": info["tipo"], "formato": r["formato"], "filas_largas": int(len(r["largo"]))})
    if not fuentes:
        raise PrepError("No hay archivos de lluvia que preparar.")
    unido, inf_fusion = fusionar(fuentes)
    cat = pd.concat(catalogos, ignore_index=True)
    cat = cat.groupby("estacion", as_index=False).first()
    cal = calidad_serie(unido.rename(columns={}))
    dest.mkdir(parents=True)
    out = unido.copy(); out["fecha"] = out["fecha"].dt.strftime("%Y-%m-%d")
    out.to_csv(dest / "precipitacion_diaria.csv", index=False)
    cat.to_csv(dest / "estaciones.csv", index=False)
    inv_res = None
    if inventario:
        iv = leer_inventario(inventario)
        e = iv["eventos"].copy(); e["fecha"] = e["fecha"].dt.strftime("%Y-%m-%d"); e.drop(columns=["tipo_norm"]).to_csv(dest / "inventario_eventos_normalizado.csv", index=False)
        inv_res = {"resumen": iv["resumen"], "problemas": iv["problemas"]}; manifest["entradas"].append({"archivo": Path(inventario).name, "ruta": str(Path(inventario).resolve()), "sha256": sha256(inventario), "tipo": "inventario_eventos"})
    informe = {"creado": datetime.now().isoformat(timespec="seconds"), "problemas_por_archivo": problemas, "fusion": inf_fusion, "calidad_por_estacion": cal, "inventario": inv_res}
    (dest / "informe_calidad.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    lineas = ["PREPARACIÓN DE DATOS · UCEclima", f"Creado: {informe['creado']}", "", "Los archivos originales NO se modificaron. Esta carpeta se creó nueva.", "",
              "Archivos:", "- precipitacion_diaria.csv : estacion, fecha, precipitacion_mm, bandera, fuente (vacío = ausente, nunca 0)", "- estaciones.csv : catálogo de estaciones", "- informe_calidad.json : problemas hallados, fusión y calidad por estación",
              "- manifest.json : archivos de entrada con su SHA-256", ""]
    for nom, pr in problemas.items():
        lineas.append(f"Problemas en {nom}:"); lineas += [f"  · {p['texto']}" for p in pr] or ["  (ninguno)"]
    lineas += ["", f"Fusión entre fuentes: {inf_fusion['rellenados_desde_otra_fuente']} días completados desde otra fuente, {inf_fusion['coinciden']} coinciden, {inf_fusion['conflictos']} conflictos (quedan vacíos). Días presentes en una sola fuente: {inf_fusion['dias_solo_en_una_fuente']}."]
    (dest / "LEEME_preparacion.txt").write_text("\n".join(lineas), encoding="utf-8")
    return {"carpeta": str(dest), "estaciones": int(len(cat)), "filas": int(len(out)), "fusion": inf_fusion, "problemas": problemas, "calidad": cal, "archivos": sorted(p.name for p in dest.iterdir())}
