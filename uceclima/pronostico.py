# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Módulo de PRONÓSTICO de lluvia (7b): GFS (NOAA, EE. UU.), ECMWF IFS (Europa) y NASA GPM IMERG (satélite, lluvia ya caída), más el caudal pronosticado
de GEOGLOWS v2 para el agua de la sierra. Parte de los scripts de la prueba de Yaguachi y de Santa Cruz (pronostico_hoy, tabla_lluvia_6dias, imerg_semana).

- GFS y ECMWF: API pública de Open-Meteo (sin claves; CC BY 4.0), 0,25° (~25 km), horaria. Se promedia sobre el área 2D del proyecto o se toma un punto.
- NASA IMERG V07: media hora, ~10 km, por Earth Engine de la persona (credenciales ya autorizadas; no se leen). Es lluvia ESTIMADA por satélite de los últimos días
  (con ~1 día de retraso), no un pronóstico; en islas y aguaceros convectivos subestima mucho (Galápagos, 30-oct-2026: vio ~11 mm).
- Lo consultado queda en <proyecto>/datos/pronostico/<modelo>_<sello>/ (CSV horario UTC + procedencia.json). Nada se sobrescribe.
- «Usar como forzamiento» importa esa serie como una estación «PRON_…» y declara el evento con la marca `forzamiento_externo`: el núcleo y las pantallas lo rotulan
  PRONÓSTICO (o ESTIMACIÓN SATELITAL), nunca «evento observado».
Un pronóstico a 25 km falla a menudo en la ubicación y la intensidad de los aguaceros: investigación, no alerta oficial (INAMHI / SNGR). Sin calibrar ni validar."""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

MODELOS = {
    "gfs": {"nombre": "NOAA GFS 0,25° (EE. UU.)", "tipo": "pronostico", "url": "https://api.open-meteo.com/v1/gfs", "max_dias": 10},
    "ecmwf": {"nombre": "ECMWF IFS 0,25° (Europa)", "tipo": "pronostico", "url": "https://api.open-meteo.com/v1/ecmwf", "max_dias": 10},
    "imerg": {"nombre": "NASA GPM IMERG V07 (satélite; lluvia ya caída)", "tipo": "satelite", "max_dias": 7},
}
UA = "UCEclima-Lambda"
TOPE_HORAS_EVENTO = 95                                          # el evento real más largo que acepta la corrida es de 96 h (evento_api.TOPE_SIM_REAL_H)
MIN_LLUVIA_UTIL_MM = 1.0                                        # por debajo de esto «no hay nada que modelar» (como el pronóstico de ≈25 mm en Santa Cruz, 2-nov-2026)
AVISO = ("Pronóstico a ~25 km: falla a menudo en la ubicación y la intensidad de los aguaceros (en islas y montañas subestima). Investigación, no alerta oficial (INAMHI / SNGR). "
         "Sin calibrar ni validar.")
ATRIBUCION = ("Pronóstico: Open-Meteo.com (CC BY 4.0) con NOAA GFS y ECMWF IFS (datos abiertos CC BY 4.0). Satélite: NASA GPM IMERG V07 (Huffman et al.), por Google Earth Engine.")


class PronosticoError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ utilidades
def _http_json(url, timeout=120):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = ""
        try:
            cuerpo = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        raise PronosticoError(f"El servicio de pronóstico respondió {e.code}. {cuerpo}".strip()) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PronosticoError("No hay conexión con el servicio de pronóstico (revisa tu internet y vuelve a intentarlo): " + str(getattr(e, "reason", e))[:160]) from e


def _carpeta_nueva(base, nombre):
    """Carpeta nueva `nombre`; si ya existe (dos consultas en el mismo segundo), `nombre_2`, `nombre_3`… Nada se sobrescribe."""
    base = Path(base); base.mkdir(parents=True, exist_ok=True)
    for k in range(1, 100):
        d = base / (nombre if k == 1 else f"{nombre}_{k}")
        try:
            d.mkdir(); return d
        except FileExistsError:
            continue
    raise PronosticoError("No pude crear una carpeta nueva para la consulta.")


def zona_por_defecto(lon, lat):
    """Hora local para las tablas diarias: Galápagos (UTC−6), Ecuador continental (UTC−5) o UTC fuera de ahí."""
    if -92.5 <= lon <= -88.5 and -1.8 <= lat <= 1.8:
        return "Pacific/Galapagos"
    if -81.5 <= lon <= -75.0 and -5.2 <= lat <= 1.6:
        return "America/Guayaquil"
    return "UTC"


def _sitio(datos, lon, lat):
    if lon is not None and lat is not None:
        return float(lon), float(lat)
    p = ((datos or {}).get("procedencia") or {}).get("punto")
    if p and len(p) == 2:
        return float(p[0]), float(p[1])
    m = re.search(r"lon\s*(-?\d+(?:\.\d+)?)\D+lat\s*(-?\d+(?:\.\d+)?)", str((datos or {}).get("ubicacion", "")))
    if m:
        return float(m.group(1)), float(m.group(2))
    raise PronosticoError("Indica la longitud y la latitud del sitio (el proyecto no las trae).")


def _puntos(carpeta, datos, lon, lat, muestreo):
    """Puntos de muestreo: el sitio, o una rejilla de 3×3 sobre el área 2D (AOI) del proyecto (promedio areal)."""
    lon, lat = _sitio(datos, lon, lat)
    if muestreo != "area":
        return [(round(lon, 4), round(lat, 4))], (lon, lat)
    try:
        from pyproj import Transformer
        cfg = json.loads((Path(carpeta) / (datos or {}).get("config_climanet", "config_climanet.json")).read_text(encoding="utf-8")); a = cfg.get("aoi")
        if not a or len(a) != 4:
            raise ValueError
        tf = Transformer.from_crs(str(datos["crs"]), "EPSG:4326", always_xy=True); xs = np.linspace(a[0], a[1], 5)[1:-1]; ys = np.linspace(a[2], a[3], 5)[1:-1]
        pts = [tuple(round(float(c), 4) for c in tf.transform(x, y)) for x in xs for y in ys]
        return pts, (lon, lat)
    except Exception:
        return [(round(lon, 4), round(lat, 4))], (lon, lat)


def _limpiar(s):
    s = s.astype(float).dropna().sort_index(); s = s[~s.index.duplicated()]
    if len(s) < 2:
        raise PronosticoError("El servicio no devolvió lluvia para ese sitio.")
    paso = s.index.to_series().diff().dropna().mode().iloc[0]
    if paso != pd.Timedelta(hours=1):
        raise PronosticoError(f"La serie no es horaria (paso {paso}).")
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="1h"))
    if s.isna().any():
        raise PronosticoError(f"La serie tiene {int(s.isna().sum())} horas sin dato: no se rellenan.")
    return s.clip(lower=0.0)


# ------------------------------------------------------------------------------------------------ fuentes
def _open_meteo(modelo, pts, dias):
    m = MODELOS[modelo]
    url = (f"{m['url']}?latitude=" + ",".join(str(p[1]) for p in pts) + "&longitude=" + ",".join(str(p[0]) for p in pts) + f"&hourly=precipitation&forecast_days={int(dias)}&timezone=UTC")
    j = _http_json(url); j = j if isinstance(j, list) else [j]
    series, celdas = [], set()
    for e in j:
        if "hourly" not in e:
            raise PronosticoError("Respuesta inesperada del servicio de pronóstico: " + str(e.get("reason", e))[:160])
        t = pd.to_datetime(e["hourly"]["time"]).tz_localize("UTC"); series.append(pd.Series(e["hourly"]["precipitation"], index=t, dtype="float64")); celdas.add((round(float(e.get("longitude", 0)), 3), round(float(e.get("latitude", 0)), 3)))
    areal = pd.concat(series, axis=1).mean(axis=1, skipna=True)
    return _limpiar(areal), sorted(celdas)


def _imerg(pts, dias):
    from . import gee_chirps as G
    info, ee = G.iniciar()
    if not (info or {}).get("autenticado"):
        raise PronosticoError("NASA IMERG se baja con Earth Engine y todavía no está autorizado: hazlo en el módulo 2 · Datos / GEE.")
    lons = [p[0] for p in pts]; lats = [p[1] for p in pts]
    region = ee.Geometry.Point([lons[0], lats[0]]) if len(pts) == 1 else ee.Geometry.Rectangle([min(lons) - 0.03, min(lats) - 0.03, max(lons) + 0.03, max(lats) + 0.03])
    fin = datetime.now(timezone.utc); ini = fin - pd.Timedelta(days=int(dias))
    col = ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate(ini.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")).select("precipitation")

    def f(img):
        return ee.Feature(None, {"t": img.get("system:time_start"), "p": img.reduceRegion(ee.Reducer.mean(), region, 1000).get("precipitation")})
    d = ee.FeatureCollection(col.map(f)).getInfo()["features"]
    if not d:
        raise PronosticoError("IMERG todavía no publica esos días (tarda ~1 día). Prueba con menos días o más tarde.")
    s = pd.DataFrame([x["properties"] for x in d]); s["t"] = pd.to_datetime(s["t"], unit="ms", utc=True); s = s.dropna().sort_values("t").set_index("t")["p"].astype(float) * 0.5      # mm/h → mm en la media hora
    h = s.resample("1h").agg(["sum", "count"]); h = h[h["count"] == 2]["sum"]
    return _limpiar(h), [(round(float(np.mean(lons)), 3), round(float(np.mean(lats)), 3))]


# ------------------------------------------------------------------------------------------------ consultar
def _resumen(s, zona):
    loc = s.tz_convert(zona) if zona != "UTC" else s
    diario = loc.resample("D").sum()
    return {"total_mm": round(float(s.sum()), 1), "max_1h_mm": round(float(s.max()), 1), "max_3h_mm": round(float(s.rolling(3).sum().max()), 1) if len(s) >= 3 else None,
            "max_6h_mm": round(float(s.rolling(6).sum().max()), 1) if len(s) >= 6 else None, "max_24h_mm": round(float(s.rolling(24).sum().max()), 1) if len(s) >= 24 else None,
            "diario": [{"dia": d.strftime("%Y-%m-%d"), "mm": round(float(v), 1), "horas": int(((loc.index >= d) & (loc.index < d + pd.Timedelta(days=1))).sum())} for d, v in diario.items()]}


def consultar(carpeta, datos, modelo, lon=None, lat=None, dias=5, muestreo="area", zona=None):
    """Pide la lluvia de UN modelo (gfs | ecmwf | imerg) y la guarda en datos/pronostico/<modelo>_<sello>/. Devuelve el resumen y la serie horaria."""
    modelo = str(modelo).lower()
    if modelo not in MODELOS:
        raise PronosticoError("Modelo desconocido: usa gfs, ecmwf o imerg.")
    dias = int(dias or 5)
    if not 1 <= dias <= MODELOS[modelo]["max_dias"]:
        raise PronosticoError(f"Para {modelo.upper()} pide entre 1 y {MODELOS[modelo]['max_dias']} días.")
    pts, (lon0, lat0) = _puntos(carpeta, datos, lon, lat, muestreo if muestreo in ("area", "punto") else "area")
    zona = zona or zona_por_defecto(lon0, lat0)
    s, celdas = (_imerg(pts, dias) if modelo == "imerg" else _open_meteo(modelo, pts, dias))
    emitido = datetime.now(timezone.utc); sello = emitido.strftime("%Y%m%d_%H%M%S")
    d = _carpeta_nueva(Path(carpeta) / "datos" / "pronostico", f"{modelo}_{sello}"); ide = d.name
    pd.DataFrame({"fecha": s.index, "lluvia_mm": s.values.round(3)}).to_csv(d / "lluvia_horaria_UTC.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    r = _resumen(s, zona)
    prov = {"id": ide, "modelo": modelo, "nombre": MODELOS[modelo]["nombre"], "tipo": MODELOS[modelo]["tipo"], "emitido_utc": emitido.strftime("%Y-%m-%dT%H:%M:%SZ"), "sitio_lonlat": [lon0, lat0], "muestreo": muestreo,
            "puntos_pedidos": len(pts), "celdas_del_modelo": [list(c) for c in celdas], "inicio_utc": s.index[0].strftime("%Y-%m-%dT%H:%M:%SZ"), "fin_utc": s.index[-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "horas": int(len(s)), "zona_local": zona, **r, "aviso": AVISO, "atribucion": ATRIBUCION}
    (d / "procedencia.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1), encoding="utf-8")
    pd.DataFrame(r["diario"]).to_csv(d / "tabla_diaria.csv", index=False, encoding="utf-8-sig")
    return {**prov, "carpeta": str(d), "hietograma": [[t.strftime("%Y-%m-%dT%H:%M:%SZ"), round(float(v), 2)] for t, v in s.items()]}


def comparar(carpeta, datos, modelos=("gfs", "ecmwf"), **kw):
    """Consulta varios modelos y arma la tabla diaria lado a lado (los que fallen se informan, no detienen a los demás)."""
    res, errores = {}, {}
    for m in modelos:
        try:
            res[m] = consultar(carpeta, datos, m, **kw)
        except PronosticoError as e:
            errores[m] = str(e)
    if not res:
        raise PronosticoError("Ningún modelo respondió: " + "; ".join(f"{k}: {v}" for k, v in errores.items()))
    dias = sorted({x["dia"] for r in res.values() for x in r["diario"]})
    tabla = [{"dia": d, **{m: next((x["mm"] for x in r["diario"] if x["dia"] == d), None) for m, r in res.items()}} for d in dias]
    return {"modelos": {m: {k: v for k, v in r.items() if k != "hietograma"} for m, r in res.items()}, "hietogramas": {m: r["hietograma"] for m, r in res.items()}, "tabla": tabla, "errores": errores,
            "zona_local": next(iter(res.values()))["zona_local"], "aviso": AVISO, "atribucion": ATRIBUCION}


def listar(carpeta):
    out = []
    for p in sorted((Path(carpeta) / "datos" / "pronostico").glob("*/procedencia.json"), reverse=True):
        try:
            j = json.loads(p.read_text(encoding="utf-8")); out.append({k: j.get(k) for k in ("id", "modelo", "nombre", "tipo", "emitido_utc", "inicio_utc", "fin_utc", "horas", "total_mm", "max_1h_mm", "zona_local")})
        except Exception:
            continue
    return out


def serie(carpeta, ide):
    ide = re.sub(r"[^A-Za-z0-9_\-]", "", str(ide)); d = Path(carpeta) / "datos" / "pronostico" / ide
    if not (d / "lluvia_horaria_UTC.csv").is_file():
        raise PronosticoError("No existe esa consulta de pronóstico.")
    s = pd.read_csv(d / "lluvia_horaria_UTC.csv"); prov = json.loads((d / "procedencia.json").read_text(encoding="utf-8"))
    return {**prov, "hietograma": [[str(a), round(float(b), 2)] for a, b in zip(s["fecha"], s["lluvia_mm"])]}


# ------------------------------------------------------------------------------------------------ usar como forzamiento
def usar(estado, ide, horas=72, permitir_poca_lluvia=False):
    """Importa la consulta como estación «PRON_…» y declara el evento (marcado como PRONÓSTICO o ESTIMACIÓN SATELITAL). Después se corre UNA corrida en el módulo 7."""
    from . import estaciones as EST
    from .ui import evento_api
    if not estado.datos:
        raise PronosticoError("Abre un proyecto.")
    ide = re.sub(r"[^A-Za-z0-9_\-]", "", str(ide)); d = Path(estado.carpeta) / "datos" / "pronostico" / ide
    if not (d / "lluvia_horaria_UTC.csv").is_file():
        raise PronosticoError("No existe esa consulta de pronóstico.")
    prov = json.loads((d / "procedencia.json").read_text(encoding="utf-8")); horas = int(horas or 72)
    if not 6 <= horas <= TOPE_HORAS_EVENTO:
        raise PronosticoError(f"El tramo a modelar debe durar entre 6 y {TOPE_HORAS_EVENTO} horas (la corrida acepta eventos de hasta 96 h).")
    s = pd.read_csv(d / "lluvia_horaria_UTC.csv", parse_dates=["fecha"]).set_index("fecha")["lluvia_mm"]
    ini = s.index[0]; fin = min(s.index[-1], ini + pd.Timedelta(hours=horas - 1)); tramo = s[ini:fin]
    if float(tramo.sum()) < MIN_LLUVIA_UTIL_MM and not permitir_poca_lluvia:
        raise PronosticoError(f"En las primeras {len(tramo)} horas el modelo pronostica solo {tramo.sum():.1f} mm: no hay nada que modelar. "
                              "Prueba con otro modelo o más horas; si de verdad quieres correrlo, activa «permitir poca lluvia».")
    lon, lat = prov["sitio_lonlat"]; est = ("PRON_" + prov["modelo"].upper() + "_" + ide.split("_", 1)[1]).replace("-", "")                 # p. ej. PRON_GFS_20261105_153000 (o …_2 si hubo dos en el mismo segundo)
    try:
        EST.importar(estado.carpeta, estado.datos["crs"], str(d / "lluvia_horaria_UTC.csv"),
                     {"id": est, "nombre": f"{prov['nombre']} · emitido {prov['emitido_utc'][:16].replace('T', ' ')} UTC (no es una estación)", "tipo": "automatica", "lon": lon, "lat": lat,
                      "col_fecha": "fecha", "col_lluvia": "lluvia_mm", "zona_horaria": "UTC", "dayfirst": False, "fuente": f"{prov['nombre']} · {'pronóstico' if prov['tipo'] == 'pronostico' else 'estimación satelital'}; no es una observación"})
    except EST.EstacionError as e:
        if "ya existe" not in str(e).lower():
            raise PronosticoError(str(e)) from e
    marca = {"tipo": prov["tipo"], "modelo": prov["modelo"], "nombre": prov["nombre"], "consulta": ide, "emitido_utc": prov["emitido_utc"], "muestreo": prov["muestreo"], "aviso": AVISO}
    try:
        out = evento_api.usar(estado, est, ini.strftime("%Y-%m-%dT%H:%M:%S"), fin.strftime("%Y-%m-%dT%H:%M:%S"), zona="utc", forzamiento_externo=marca)
    except evento_api.EventoUIError as e:
        raise PronosticoError(str(e)) from e
    return {**out, "estacion": est, "forzamiento_externo": marca, "siguiente_paso": "Ve al módulo 7 y ejecuta UNA corrida: el resultado saldrá rotulado como "
            + ("PRONÓSTICO" if prov["tipo"] == "pronostico" else "ESTIMACIÓN SATELITAL") + " (no como evento observado)."}


# ------------------------------------------------------------------------------------------------ caudal de la sierra (GEOGLOWS v2 Forecast)
def geoglows_forecast(carpeta, river_id, horas=96):
    """Caudal pronosticado (mediana y banda alta del ensamble, cada 3 h) de un tramo GEOGLOWS v2. Escribe dos CSV t_s;Q_m3s listos para declarar como hidrograma de
    entrada (módulo 7), recortados a `horas`. Es un modelo global: sirve para el orden de magnitud, no para ubicar el cauce."""
    rid = int(re.sub(r"\D", "", str(river_id)) or 0)
    if rid < 1:
        raise PronosticoError("Indica el número del tramo GEOGLOWS (river_id).")
    q = _http_json(f"https://geoglows.ecmwf.int/api/v2/forecast/{rid}?format=json")
    try:
        dq = pd.DataFrame({"fecha": pd.to_datetime(q["datetime"], utc=True), "mediana": q["flow_median"], "alta": q["flow_uncertainty_upper"], "baja": q["flow_uncertainty_lower"]})
    except KeyError as e:
        raise PronosticoError("GEOGLOWS no devolvió el pronóstico de ese tramo.") from e
    dq = dq.dropna().sort_values("fecha"); dq = dq[dq.fecha <= dq.fecha.iloc[0] + pd.Timedelta(hours=int(horas))].reset_index(drop=True)
    if len(dq) < 2:
        raise PronosticoError("El pronóstico de GEOGLOWS es demasiado corto.")
    sello = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"); d = _carpeta_nueva(Path(carpeta) / "datos" / "pronostico", f"geoglows_{rid}_{sello}")
    dq.to_csv(d / "geoglows_pronostico_3h.csv", index=False); t0 = dq.fecha.iloc[0]; filas = {}
    for col, nombre in (("mediana", "geoglows_mediana"), ("alta", "geoglows_banda_alta")):
        t = ((dq.fecha - t0).dt.total_seconds()).tolist(); v = dq[col].tolist(); t.append(t[-1] + 1.0); v.append(0.0)           # al terminar el pronóstico no se simula aporte (se declara, no se inventa la cola)
        pd.DataFrame({"t_s": t, "Q_m3s": v}).to_csv(d / f"{nombre}_t_s_Q_m3s.csv", index=False); filas[nombre] = f"{nombre}; {d / (nombre + '_t_s_Q_m3s.csv')}; <x>; <y>"
    res = {"id": d.name, "carpeta": str(d), "river_id": rid, "inicio_utc": t0.strftime("%Y-%m-%dT%H:%M:%SZ"), "horas": int(horas), "q_mediana_max_m3s": round(float(dq.mediana.max()), 1), "q_alta_max_m3s": round(float(dq.alta.max()), 1),
           "filas_hidrograma_de_entrada": filas, "nota": "Sustituye <x> y <y> por la entrada sobre el cauce del 2D (módulo 7 › hidrogramas de entrada). Modelo global: orden de magnitud, no ubica el cauce.",
           "aviso": "Caudal pronosticado por un modelo global (GEOGLOWS v2, ECMWF): referencia externa, no observación. Sin calibrar ni validar."}
    (d / "procedencia.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
