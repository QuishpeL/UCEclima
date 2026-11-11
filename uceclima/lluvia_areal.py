# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Lluvia areal de la cuenca activa con estaciones del proyecto (C12): Thiessen dinámico o IDW.

Thiessen dinámico: cada día se usan solo las estaciones con dato ese día; los polígonos de Thiessen de ESE conjunto se recortan a la cuenca y
el peso de cada estación es el área de su polígono dentro de la cuenca / área de la cuenca. Los conjuntos repetidos se calculan una vez.
IDW: media sobre una malla regular de puntos dentro de la cuenca, con peso 1/d² a las estaciones con dato ese día.
Estaciones candidatas: las que caen dentro de la cuenca más un radio (por defecto 10 km). Fuentes: series del premódulo guardadas en el
proyecto (con lon/lat del catálogo) y estaciones registradas en el proyecto. Nada se rellena: un día sin ninguna estación queda vacío.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd


class ArealError(Exception):
    pass


def _cuenca(carpeta, crs):
    import geopandas as gpd
    act = Path(carpeta) / "cuenca" / "activa.json"
    if not act.exists():
        raise ArealError("No hay cuenca activa (hidro · Cuenca).")
    a = json.loads(act.read_text(encoding="utf-8"))
    if a.get("origen") == "malla":
        raise ArealError("La cuenca activa es la malla CHIRPS: carga o acepta una cuenca hidrográfica.")
    return gpd.read_file(Path(carpeta) / a["carpeta"] / "cuenca.gpkg").to_crs(crs).geometry.unary_union, a


def estaciones(carpeta, crs):
    """[{id, nombre, x, y, fuente, serie (diaria mm)}] de lluvia con coordenadas."""
    from pyproj import Transformer
    carpeta = Path(carpeta); out = []
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    idx = carpeta / "datos" / "series_premodulo" / "indice.json"
    if idx.exists():
        for m in json.loads(idx.read_text(encoding="utf-8")):
            if m.get("tipo") != "lluvia" or m.get("lon") is None or m.get("lat") is None:
                continue
            f = idx.parent / m.get("archivo", f"{m['slug']}.csv")
            if not f.exists():
                continue
            d = pd.read_csv(f, parse_dates=["fecha"]); x, y = tf.transform(float(m["lon"]), float(m["lat"]))
            out.append({"id": m["id"].split(":", 1)[-1], "nombre": m.get("nombre", m["id"]), "x": x, "y": y, "fuente": "premódulo",
                        "serie": pd.Series(d["valor"].values, index=pd.to_datetime(d["fecha"])).astype(float)})
    cat = carpeta / "datos" / "estaciones" / "catalogo.csv"
    if cat.exists():
        c = pd.read_csv(cat)
        for r in c.itertuples():
            f = cat.parent / f"{r.id}.csv"
            if not f.exists() or str(r.id).startswith("WRF_"):
                continue
            d = pd.read_csv(f)
            t = pd.to_datetime(d["fecha"], utc=True).dt.tz_convert("America/Guayaquil").dt.tz_localize(None)
            s = pd.Series(pd.to_numeric(d["lluvia_mm"], errors="coerce").values, index=t).resample("D").sum(min_count=1)
            out.append({"id": str(r.id), "nombre": str(getattr(r, "nombre", r.id)), "x": float(r.x), "y": float(r.y), "fuente": "estación registrada", "serie": s})
    return out


def _pesos_thiessen(puntos, cuenca):
    from shapely.geometry import MultiPoint, Point
    from shapely.ops import voronoi_diagram
    if len(puntos) == 1:
        return np.array([1.0])
    env = cuenca.envelope.buffer(max(cuenca.bounds[2] - cuenca.bounds[0], cuenca.bounds[3] - cuenca.bounds[1]) * 3 + 1e4)
    celdas = list(voronoi_diagram(MultiPoint([Point(p) for p in puntos]), envelope=env).geoms)
    w = np.zeros(len(puntos))
    for c in celdas:
        k = next((i for i, p in enumerate(puntos) if c.contains(Point(p)) or c.touches(Point(p))), None)
        if k is not None:
            w[k] = c.intersection(cuenca).area
    return w / cuenca.area


def _pesos_idw(puntos, cuenca, n=400, potencia=2.0):
    from shapely.geometry import Point
    x0, y0, x1, y1 = cuenca.bounds; lado = max(np.sqrt((x1 - x0) * (y1 - y0) / n), 1.0)
    gx, gy = np.meshgrid(np.arange(x0 + lado / 2, x1, lado), np.arange(y0 + lado / 2, y1, lado))
    dentro = np.array([cuenca.contains(Point(a, b)) for a, b in zip(gx.ravel(), gy.ravel())])
    g = np.c_[gx.ravel()[dentro], gy.ravel()[dentro]]
    if len(g) == 0:
        g = np.array([[cuenca.centroid.x, cuenca.centroid.y]])
    P = np.asarray(puntos, float); d = np.hypot(g[:, None, 0] - P[None, :, 0], g[:, None, 1] - P[None, :, 1]); d = np.maximum(d, 1.0)
    w = (1 / d ** potencia); w = w / w.sum(axis=1, keepdims=True)
    return w.mean(axis=0)


def calcular(carpeta, datos, metodo="thiessen", radio_km=10.0, ids=None, inicio=None, fin=None):
    if metodo not in ("thiessen", "idw"):
        raise ArealError("Método: thiessen o idw.")
    crs = datos.get("crs") or "EPSG:32717"
    cuenca, a = _cuenca(carpeta, crs)
    from shapely.geometry import Point
    todas = estaciones(carpeta, crs)
    if not todas:
        raise ArealError("No hay estaciones de lluvia con coordenadas en el proyecto (premódulo con catálogo de coordenadas o estaciones registradas).")
    zona = cuenca.buffer(float(radio_km) * 1000)
    cand = [e for e in todas if zona.contains(Point(e["x"], e["y"])) and (not ids or e["id"] in ids)]
    if not cand:
        raise ArealError(f"Ninguna estación de lluvia dentro de la cuenca ni a menos de {radio_km:g} km.")
    M = pd.concat({e["id"]: e["serie"] for e in cand}, axis=1).sort_index()
    M = M[~M.index.duplicated()]
    if inicio:
        M = M[M.index >= pd.Timestamp(inicio)]
    if fin:
        M = M[M.index <= pd.Timestamp(fin)]
    puntos = {e["id"]: (e["x"], e["y"]) for e in cand}
    disp = M.notna()
    patrones = {}
    serie = pd.Series(np.nan, index=M.index); n_est = disp.sum(axis=1)
    for patron, filas in disp.groupby(list(disp.columns)).groups.items():
        patron = patron if isinstance(patron, tuple) else (patron,)
        cols = [c for c, v in zip(disp.columns, patron) if v]
        if not cols:
            continue
        clave = tuple(cols)
        if clave not in patrones:
            pts = [puntos[c] for c in cols]
            patrones[clave] = _pesos_thiessen(pts, cuenca) if metodo == "thiessen" else _pesos_idw(pts, cuenca)
        w = patrones[clave]; s = w.sum()
        if s <= 0:
            continue
        serie.loc[filas] = (M.loc[filas, cols].values * (w / s)).sum(axis=1)
    pts_all = [puntos[c] for c in M.columns]
    w_all = _pesos_thiessen(pts_all, cuenca) if metodo == "thiessen" else _pesos_idw(pts_all, cuenca)
    pesos = pd.DataFrame({"estacion": list(M.columns), "peso_con_todas": np.round(w_all / max(w_all.sum(), 1e-12), 4),
                          "dentro_de_la_cuenca": [cuenca.contains(Point(puntos[c])) for c in M.columns],
                          "dias_con_dato": [int(disp[c].sum()) for c in M.columns]}).sort_values("peso_con_todas", ascending=False)
    return serie, pesos, {"metodo": metodo, "estaciones": list(M.columns), "n_estaciones": int(len(M.columns)), "conjuntos_distintos": len(patrones),
                          "dias": int(len(serie)), "dias_sin_estacion": int(serie.isna().sum()), "radio_km": float(radio_km), "cuenca": a.get("carpeta"), "area_km2": a.get("area_km2"),
                          "media_anual_mm": round(float(serie.mean() * 365.25), 1) if serie.notna().any() else None, "n_estaciones_por_dia": n_est}


def registrar(carpeta, datos, metodo="thiessen", radio_km=10.0, ids=None, persona=""):
    """Calcula y deja la lluvia areal como forzamiento activo de la calibración (observaciones/lluvia_activa.json · fuente «areal»)."""
    serie, pesos, info = calcular(carpeta, datos, metodo, radio_km, ids)
    obs = Path(carpeta) / "observaciones"; obs.mkdir(parents=True, exist_ok=True)
    sello = time.strftime("%Y%m%d_%H%M%S")
    f = obs / f"lluvia_areal_{metodo}_{sello}.csv"
    pd.DataFrame({"fecha": serie.index.strftime("%Y-%m-%d"), "lluvia_mm": serie.round(3).values, "n_estaciones": info.pop("n_estaciones_por_dia").values}).to_csv(f, index=False)
    fp = obs / f"lluvia_areal_{metodo}_{sello}_pesos.csv"; pesos.to_csv(fp, index=False, encoding="utf-8-sig")
    act = {"fuente": "areal", "tipo_registro": "areal", "archivo": f.name, "estacion": f"{metodo} ({info['n_estaciones']} estaciones)", "origen": "lluvia areal de la cuenca activa",
           "pesos_archivo": fp.name, "pesos": pesos.to_dict("records"), "persona": persona, "fecha_registro": time.strftime("%Y-%m-%dT%H:%M:%S"), **info,
           "aviso": ("Thiessen dinámico: pesos por día según las estaciones con dato." if metodo == "thiessen" else "IDW (1/d²) sobre una malla dentro de la cuenca.")}
    (obs / "lluvia_activa.json").write_text(json.dumps(act, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return act
