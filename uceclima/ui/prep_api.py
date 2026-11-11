# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""API del PREMÓDULO de preparación de datos. Todo es determinista y reproducible: una IA (vía la API abierta) o una persona eligen hoja, columnas, estación y filtros;
el programa ordena, mide la calidad y escribe en carpetas NUEVAS (nunca toca los archivos crudos). No hay modelo de lenguaje dentro del programa."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd

from .. import preparacion as PR, estaciones as EST

MAX_FILAS_TABLA = 400


def _dir_defecto(estado):
    if estado.datos:
        return Path(estado.carpeta) / "datos_preparados"
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "UCEclima_preparados"


def _lluvia(ruta, hoja=None):
    t = PR.clasificar_archivo(ruta)["tipo"]
    if t == "precipitacion_ancha_inamhi":
        return PR.leer_precip_ancha(ruta, hoja)
    if t == "precipitacion_larga":
        return PR.leer_precip_larga(ruta, estacion_defecto=Path(ruta).stem)
    raise PR.PrepError(f"{Path(ruta).name}: no es un archivo de lluvia reconocible ({t}).")


def escanear(cuerpo):
    return PR.escanear(cuerpo.get("carpeta", ""))


def precipitacion(cuerpo):
    r = _lluvia(cuerpo.get("archivo", ""), cuerpo.get("hoja"))
    cal = PR.calidad_serie(r["largo"])
    cat = r["catalogo"].replace({np.nan: None}).to_dict("records")
    return {"formato": r["formato"], "hoja": r["hoja"], "problemas": r["problemas"], "estaciones": cat, "calidad": cal, "filas": int(len(r["largo"]))}


def inventario(cuerpo):
    r = PR.leer_inventario(cuerpo.get("archivo", ""), cuerpo.get("hoja"))
    return {"resumen": r["resumen"], "problemas": r["problemas"]}


def _serie_estacion(cuerpo):
    ruta = cuerpo.get("precip_archivo", "")
    p = Path(ruta)
    if p.name == "precipitacion_diaria.csv":                                  # ya ordenado por el premódulo
        d = pd.read_csv(p, parse_dates=["fecha"])
    else:
        d = _lluvia(ruta, cuerpo.get("hoja"))["largo"]
    est = cuerpo.get("estacion")
    if not est:
        raise PR.PrepError("Indica la estación.")
    g = d[d["estacion"] == est]
    if g.empty:
        raise PR.PrepError(f"La estación {est} no está en ese archivo (hay: {', '.join(sorted(d['estacion'].astype(str).unique())[:15])}).")
    return g.drop_duplicates("fecha").set_index("fecha")["precipitacion_mm"].sort_index()


def contrastar(cuerpo):
    serie = _serie_estacion(cuerpo)
    inv = PR.leer_inventario(cuerpo["inventario_archivo"], cuerpo.get("inventario_hoja"))
    lat, lon = cuerpo.get("lat"), cuerpo.get("lon")
    lat = float(lat) if lat not in (None, "") else None; lon = float(lon) if lon not in (None, "") else None
    c = PR.contrastar(serie, inv["eventos"], lat, lon, float(cuerpo.get("radio_km") or 30), cuerpo.get("cantones") or None, bool(cuerpo.get("solo_hidromet", True)), int(cuerpo.get("ventana_dias") or 3))
    t = c["tabla"]
    tabla = t.head(MAX_FILAS_TABLA).replace({np.nan: None}).to_dict("records")
    s = serie.dropna()
    return {"resumen": c["resumen"], "tasa_por_clase": c["tasa_por_clase"], "avisos": c["avisos"], "problemas_inventario": inv["problemas"], "tabla": tabla, "n_tabla": int(len(t)),
            "serie": {"fecha": [d.strftime("%Y-%m-%d") for d in s.index], "mm": [round(float(v), 1) for v in s.values]},
            "eventos_fechas": sorted(set(t["fecha"])) if len(t) else []}


def ordenar(estado, cuerpo):
    salida = cuerpo.get("salida") or str(_dir_defecto(estado))
    return PR.ordenar_y_guardar(cuerpo.get("archivos") or [], salida, cuerpo.get("inventario") or None)


def registrar_estacion(estado, cuerpo):
    """Lleva una estación ya ordenada (lluvia DIARIA) al proyecto abierto, como estación importada con su calidad."""
    if not estado.datos:
        raise PR.PrepError("Abre un proyecto para registrar la estación.")
    carpeta = Path(cuerpo.get("preparados", ""))
    csv = carpeta / "precipitacion_diaria.csv"; cat = carpeta / "estaciones.csv"
    if not csv.exists() or not cat.exists():
        raise PR.PrepError("Esa carpeta no es una salida del premódulo (falta precipitacion_diaria.csv / estaciones.csv).")
    est = cuerpo.get("estacion"); d = pd.read_csv(csv)
    g = d[d["estacion"] == est]
    if g.empty:
        raise PR.PrepError(f"La estación {est} no está en esos datos.")
    c = pd.read_csv(cat); c = c[c["estacion"] == est]
    if c.empty or pd.isna(c.iloc[0].get("lon")) or pd.isna(c.iloc[0].get("lat")):
        raise PR.PrepError(f"La estación {est} no tiene coordenadas en el catálogo; indícalas con lon y lat.")
    tmp = Path(estado.carpeta) / "datos" / "estaciones" / f"_origen_{est}.csv"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    g[["fecha", "precipitacion_mm"]].to_csv(tmp, index=False)
    meta = {"id": est, "nombre": str(c.iloc[0].get("nombre") or est), "tipo": "pluviometro", "col_fecha": "fecha", "col_lluvia": "precipitacion_mm", "lon": float(c.iloc[0]["lon"]), "lat": float(c.iloc[0]["lat"]),
            "zona_horaria": "UTC", "dayfirst": False, "fuente": f"premódulo: {carpeta.name}"}
    try:
        r = EST.importar(estado.carpeta, estado.datos["crs"], str(tmp), meta)
    finally:
        tmp.unlink(missing_ok=True)
    return r
