# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Estaciones pluviométricas/pluviográficas del proyecto: importar CSV con vista previa y control de calidad, catálogo, series y hietograma de evento.
Todo se guarda dentro del proyecto (datos/estaciones/). No se interpola, no se corrige y no se rellenan huecos: lo ausente queda ausente.
Formato normalizado: <id>.csv con columnas fecha (ISO-8601 en UTC) y lluvia_mm (mm por registro) y catalogo.csv (id,nombre,x,y,tipo,...) compatible con CLIMANET StationRain.
Un evento de una estación puede conducir la corrida vía ui/evento_api.py (CLIMANET evento_observado); el modelo sigue sin calibrar."""
import csv, json, re
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

TIPOS = ("pluviometro", "pluviografo", "automatica", "otra")
COLS_FECHA = ("fecha", "datetime", "date", "fechahora", "fecha_hora", "timestamp", "time", "dia")
COLS_LLUVIA = ("lluvia_mm", "lluvia", "precipitacion", "precip", "pp", "mm", "rain", "rainfall", "prec", "valor")
ZONA_DEFECTO = "America/Guayaquil"


class EstacionError(ValueError):
    pass


def _carpeta(proyecto):
    return Path(proyecto) / "datos" / "estaciones"


def _leer(path, max_filas=None):
    p = Path(path)
    if not p.is_file():
        raise EstacionError("No existe el archivo indicado.")
    muestra = p.read_bytes()[:20000].decode("utf-8", errors="replace")
    try:
        delim = csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    df = pd.read_csv(p, sep=delim, nrows=max_filas, encoding="utf-8", encoding_errors="replace", dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    if df.shape[1] < 2:
        raise EstacionError("El archivo necesita al menos dos columnas (fecha y lluvia).")
    return df, delim


def _adivinar(cols, candidatos):
    bajo = {c.lower().replace(" ", "_"): c for c in cols}
    for k in candidatos:
        if k in bajo:
            return bajo[k]
    for k in candidatos:
        for b, c in bajo.items():
            if k in b:
                return c
    return None


def _numero(s):
    return pd.to_numeric(s.astype(str).str.strip().str.replace(",", ".", regex=False), errors="coerce")


def vista_previa(path):
    """Primeras filas, delimitador y columnas propuestas. No escribe nada."""
    df, delim = _leer(path, max_filas=400000)
    cf = _adivinar(df.columns, COLS_FECHA)
    return {"delimitador": delim, "n_filas": int(len(df)), "columnas": list(df.columns), "muestra": df.head(8).fillna("").values.tolist(),
            "propuesta": {"fecha": cf, "lluvia": _adivinar([c for c in df.columns if c != cf], COLS_LLUVIA)}}


def _normalizar(path, col_fecha, col_lluvia, zona, dayfirst):
    df, _ = _leer(path)
    if col_fecha not in df.columns or col_lluvia not in df.columns:
        raise EstacionError("Las columnas elegidas no existen en el archivo.")
    f = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=bool(dayfirst))
    v = _numero(df[col_lluvia])
    malas = int(f.isna().sum())
    d = pd.DataFrame({"fecha": f, "lluvia_mm": v})[f.notna()]
    if d.empty:
        raise EstacionError("Ninguna fecha pudo interpretarse; revisa la columna de fecha y el orden día/mes.")
    if d["fecha"].dt.tz is None:
        try:
            d["fecha"] = d["fecha"].dt.tz_localize(zona, ambiguous="NaT", nonexistent="NaT")
        except Exception as e:
            raise EstacionError(f"Zona horaria no válida: {zona}") from e
    d["fecha"] = d["fecha"].dt.tz_convert("UTC")
    return d.dropna(subset=["fecha"]).sort_values("fecha"), malas


def control_calidad(d, fechas_malas=0, max_mm_paso=None):
    """Resumen de calidad sobre la serie normalizada (sin corregir nada)."""
    n = int(len(d))
    dif = d["fecha"].diff().dropna()
    paso = dif.mode().iloc[0] if len(dif) else pd.Timedelta(0)
    paso_min = round(paso.total_seconds() / 60, 3)
    dup = int(d.duplicated("fecha", keep=False).sum())
    conflicto = int((d[d.duplicated("fecha", keep=False)].groupby("fecha")["lluvia_mm"].nunique(dropna=False) > 1).sum()) if dup else 0
    huecos = int((dif > paso * 1.5).sum()) if paso_min > 0 else 0
    mayor_hueco_h = round(float(dif.max().total_seconds() / 3600), 2) if len(dif) else 0.0
    neg = int((d["lluvia_mm"] < 0).sum()); ausentes = int(d["lluvia_mm"].isna().sum())
    vals = d["lluvia_mm"].where(d["lluvia_mm"] >= 0)
    avisos = []
    if conflicto: avisos.append(f"{conflicto} marcas de tiempo repetidas con valores distintos: el modelo las rechazaría.")
    if neg: avisos.append(f"{neg} valores negativos (se guardan como ausentes).")
    if fechas_malas: avisos.append(f"{fechas_malas} filas con fecha ilegible fueron omitidas.")
    if huecos: avisos.append(f"{huecos} huecos mayores a 1,5 pasos (el mayor: {mayor_hueco_h} h); no se rellenan.")
    if paso_min == 0.0: avisos.append("No se pudo detectar el paso de tiempo.")
    if max_mm_paso and (vals > max_mm_paso).any(): avisos.append(f"{int((vals > max_mm_paso).sum())} valores superan {max_mm_paso} mm por registro.")
    return {"n_registros": n, "inicio_utc": d["fecha"].min().isoformat(), "fin_utc": d["fecha"].max().isoformat(), "paso_min_detectado": paso_min,
            "duplicados": dup, "duplicados_conflictivos": conflicto, "huecos": huecos, "mayor_hueco_h": mayor_hueco_h, "negativos": neg, "ausentes": ausentes,
            "max_mm_registro": None if vals.dropna().empty else round(float(vals.max()), 3), "total_mm": round(float(vals.sum()), 2), "avisos": avisos}


def importar(proyecto, crs_proyecto, archivo, meta):
    """Importa una estación. meta: id, nombre, tipo, x/y en el CRS del proyecto o lon/lat, col_fecha, col_lluvia, zona_horaria, dayfirst, fuente.
    No sobrescribe: un id existente es un error."""
    ide = re.sub(r"[^A-Za-z0-9_\-]", "", str(meta.get("id", "")).strip())
    if len(ide) < 2:
        raise EstacionError("El identificador de la estación debe tener al menos 2 caracteres (letras, números, _ o -).")
    tipo = meta.get("tipo", "pluviometro")
    if tipo not in TIPOS:
        raise EstacionError("Tipo de estación no válido.")
    d = _carpeta(proyecto)
    if (d / f"{ide}.csv").exists():
        raise EstacionError(f"La estación {ide} ya existe en este proyecto; no se sobrescribe. Usa otro identificador.")
    try:
        if meta.get("x") not in (None, "") and meta.get("y") not in (None, ""):
            x, y = float(meta["x"]), float(meta["y"])
        elif meta.get("lon") not in (None, "") and meta.get("lat") not in (None, ""):
            from pyproj import Transformer
            x, y = Transformer.from_crs("EPSG:4326", crs_proyecto, always_xy=True).transform(float(meta["lon"]), float(meta["lat"]))
        else:
            raise EstacionError("Indica la ubicación: x e y en el CRS del proyecto, o lon y lat (WGS84).")
    except (TypeError, ValueError) as e:
        raise EstacionError("Coordenadas no numéricas.") from e
    serie, malas = _normalizar(archivo, meta.get("col_fecha"), meta.get("col_lluvia"), meta.get("zona_horaria") or ZONA_DEFECTO, meta.get("dayfirst", True))
    qc = control_calidad(serie, malas, meta.get("max_mm_registro"))
    if qc["duplicados_conflictivos"]:
        raise EstacionError("Hay marcas de tiempo repetidas con valores contradictorios; corrige el archivo (no se suman ni se promedian).")
    serie = serie.drop_duplicates("fecha")
    serie.loc[serie["lluvia_mm"] < 0, "lluvia_mm"] = np.nan
    d.mkdir(parents=True, exist_ok=True)
    out = serie.copy(); out["fecha"] = out["fecha"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out.to_csv(d / f"{ide}.csv", index=False)
    fila = {"id": ide, "nombre": meta.get("nombre") or ide, "x": round(x, 3), "y": round(y, 3), "tipo": tipo, "crs": crs_proyecto, "fuente": meta.get("fuente", ""),
            "zona_horaria_origen": meta.get("zona_horaria") or ZONA_DEFECTO, "archivo_origen": Path(archivo).name, "importada": datetime.now().isoformat(timespec="seconds")}
    cat = d / "catalogo.csv"
    prev = pd.read_csv(cat) if cat.exists() else pd.DataFrame()
    pd.concat([prev, pd.DataFrame([fila])], ignore_index=True).to_csv(cat, index=False)
    (d / f"{ide}.qc.json").write_text(json.dumps({"estacion": fila, "calidad": qc}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"estacion": fila, "calidad": qc}


def listar(proyecto):
    d = _carpeta(proyecto); cat = d / "catalogo.csv"
    if not cat.exists():
        return []
    out = []
    for r in pd.read_csv(cat).to_dict("records"):
        q = d / f"{r['id']}.qc.json"
        r["calidad"] = json.loads(q.read_text(encoding="utf-8"))["calidad"] if q.exists() else None
        out.append(r)
    return out


def serie(proyecto, ide, inicio=None, fin=None, paso="auto"):
    ide = re.sub(r"[^A-Za-z0-9_\-]", "", ide or "")
    f = _carpeta(proyecto) / f"{ide}.csv"
    if not f.exists():
        raise EstacionError("No existe esa estación en el proyecto.")
    d = pd.read_csv(f, parse_dates=["fecha"])
    if inicio: d = d[d["fecha"] >= pd.Timestamp(inicio, tz="UTC")]
    if fin: d = d[d["fecha"] <= pd.Timestamp(fin, tz="UTC")]
    if paso != "auto" and len(d):
        d = d.set_index("fecha")["lluvia_mm"].resample(paso).sum(min_count=1).reset_index()
    if len(d) > 5000:                                                       # para dibujar: se agrega a diario, sin cambiar el total
        d = d.set_index("fecha")["lluvia_mm"].resample("D").sum(min_count=1).reset_index()
    return d


def hietograma(proyecto, ide, inicio, fin, ruta_salida=None):
    """Hietograma de un evento (mm por registro, tal cual) en un CSV nuevo. Es solo un archivo de datos: no pone a la estación a conducir el modelo."""
    d = serie(proyecto, ide, inicio, fin)
    if d.empty:
        raise EstacionError("No hay registros en esa ventana.")
    ruta = Path(ruta_salida or (_carpeta(proyecto) / f"hietograma_{ide}_{pd.Timestamp(inicio):%Y%m%d}_{pd.Timestamp(fin):%Y%m%d}.csv"))
    if ruta.exists():
        raise EstacionError("Ese hietograma ya existe; no se sobrescribe.")
    d.to_csv(ruta, index=False)
    return {"archivo": str(ruta), "n": int(len(d)), "total_mm": round(float(d["lluvia_mm"].sum()), 2)}
