# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""IDF INAMHI como X (condiciones existentes): ingesta de las ECUACIONES y CUADROS del libro «Determinación de ecuaciones para el cálculo de intensidades máximas de precipitación» (INAMHI),
ya incluidos en el núcleo (72 zonas pluviográficas, 218 estaciones con Idtr). Para el sitio del proyecto se muestran: la estación de referencia y su zona, las ecuaciones i = K · Idtr · t^-n (por tramos de duración),
el cuadro IDF (9 duraciones × 6 Tr) en los tres modos del libro (estación / escalada / sitio), las curvas y la tormenta de diseño (bloques alternos). Todo es la condición HISTÓRICA (X): sin cambio climático.

Reglas: no se calibra nada; la zona se asigna por la pluviográfica más cercana (confirmar con el mapa del libro cuando el sitio quede entre dos regiones climáticas); la IDF del INAMHI es una intensidad máxima
puntual, no un hietograma observado. Las salidas se guardan en carpetas nuevas con marca de tiempo dentro del proyecto."""
import json, math
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

MODOS = {"estacion": "Estación (cuadro exacto del libro)", "escalada": "Escalada (cuadro de la estación × Idtr del sitio / Idtr de la estación)", "sitio": "Sitio (ecuaciones de la zona con Idtr interpolado)"}


def _nucleo():
    import uceclima                                                                         # fija sys.path hacia el núcleo
    from climanet import inamhi, idf as IDF
    return inamhi, IDF


def punto(datos):
    import re
    m = re.search(r"lon\s*(-?\d+(?:\.\d+)?)\D+lat\s*(-?\d+(?:\.\d+)?)", str(datos.get("ubicacion", "")))
    if not m:
        raise ValueError("El proyecto no declara un punto de sitio (lon/lat).")
    return float(m.group(2)), float(m.group(1))                                          # lat, lon


def pluviograficas_cercanas(lat, lon, n=6):
    inamhi, _ = _nucleo(); _, est, _ = inamhi._cargar()
    pl = est.dropna(subset=["lat", "lon"]).copy(); pl = pl[~pl.coord_revisar & pl.tipo.str.startswith("pluviografica")]
    pl["dist_km"] = [inamhi._hav(lat, lon, a, b) for a, b in zip(pl.lat, pl.lon)]
    return pl.sort_values("dist_km").head(n)[["codigo", "nombre", "lat", "lon", "z_msnm", "dist_km", "n_anios", "zona_ecuaciones"]]


def calcular(datos, estacion=None, duracion_min=180, tr_tormenta=100):
    """Todo lo necesario para mostrar y guardar la IDF X del sitio. `estacion`: pluviográfica de referencia elegida (por defecto, la más cercana)."""
    inamhi, IDF = _nucleo(); lat, lon = punto(datos)
    zon, est, _ = inamhi._cargar()
    cercanas = pluviograficas_cercanas(lat, lon)
    ref = estacion or cercanas.iloc[0]["codigo"]
    tablas, infos = {}, {}
    for modo in MODOS:
        try:
            t, i = inamhi.idf_sitio(lat, lon, modo=modo, estacion=ref); tablas[modo], infos[modo] = t, i
        except Exception as e:                                                          # p. ej. «escalada» sin Idtr de Tabla 3 para esa estación
            tablas[modo], infos[modo] = None, {"error": str(e)[:160]}
    _, info_auto = inamhi.idf_sitio(lat, lon, modo="auto", estacion=ref)
    modo_auto = info_auto["modo"]
    ec = zon[zon.codigo == ref].sort_values("t_desde_min")[["zona", "codigo", "nombre_zona", "tramo", "t_desde_min", "t_hasta_min", "K", "n", "R2"]]
    idtr = inamhi._idtr_sitio(lat, lon)
    fila = est[est.codigo == ref].iloc[0]
    tabla_usada = tablas[modo_auto] if tablas[modo_auto] is not None else tablas["sitio"]
    edges, bloques = IDF.design_storm(tabla_usada, int(tr_tormenta), int(duracion_min), 1.0)
    d24 = float(tabla_usada.loc[int(tr_tormenta), 1440]) * 24
    return {"lat": lat, "lon": lon, "referencia": {"codigo": ref, "nombre": str(fila["nombre"]), "dist_km": round(float(inamhi._hav(lat, lon, fila["lat"], fila["lon"])), 2), "zona": None if pd.isna(fila["zona_ecuaciones"]) else int(fila["zona_ecuaciones"]),
                                                       "anios": None if pd.isna(fila["n_anios"]) else int(fila["n_anios"]), "z_msnm": None if pd.isna(fila["z_msnm"]) else float(fila["z_msnm"])},
            "modo_auto": modo_auto, "info_auto": info_auto, "cercanas": cercanas.round(3).to_dict("records"), "ecuaciones": ec.round(4).to_dict("records"), "idtr_sitio": {k: round(float(v), 3) for k, v in idtr.items()},
            "tablas": {m: (None if t is None else {"tr": [int(x) for x in t.index], "duraciones_min": [int(x) for x in t.columns], "intensidad_mmh": t.round(2).values.tolist()}) for m, t in tablas.items()}, "infos": infos,
            "tormenta": {"tr": int(tr_tormenta), "duracion_min": int(duracion_min), "modo": modo_auto if tablas[modo_auto] is not None else "sitio", "p24_mm": round(d24, 1), "bloque_min": round(float(edges[1] - edges[0]) / 60, 2) if len(edges) > 1 else None,
                         "mm_por_bloque": [round(float(x), 3) for x in np.asarray(bloques).reshape(len(bloques), -1).sum(axis=1)] if np.ndim(bloques) > 1 else [round(float(x), 3) for x in bloques]},
            "metodo": "i(Tr, t) = K · Idtr(Tr) · t^-n  (i en mm/h, t en min, Idtr = intensidad máxima en 24 h); (K, n) de la zona de la pluviográfica de referencia, por tramos de duración.",
            "avisos": ["Condición HISTÓRICA (X): sin cambio climático.", "La zona se asigna por la pluviográfica más cercana: confirma con el mapa del libro si el sitio queda entre dos regiones climáticas (cordillera, costa/sierra).",
                       "La IDF es una intensidad máxima puntual del libro; no es un hietograma observado ni está calibrada con eventos del proyecto."] + list(info_auto.get("avisos", []))}


def _graficas(res, destino):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": "#0f1b2d", "axes.facecolor": "#14233a", "axes.edgecolor": "#3b4a63", "axes.labelcolor": "#c9d6e6", "xtick.color": "#9fb0c6", "ytick.color": "#9fb0c6", "text.color": "#e6edf5",
                         "grid.color": "#25364f", "font.family": ["Calibri", "Arial", "DejaVu Sans"], "font.size": 10})
    pie = f"IDF INAMHI (X) · estación de referencia {res['referencia']['codigo']} {res['referencia']['nombre']} · {res['referencia']['dist_km']} km del sitio · condición histórica, sin cambio climático"
    colores = ["#4cc9f0", "#6cc4ec", "#9fb4ff", "#a98bff", "#ffd166", "#ffffff"]
    out = []
    modo = res["tormenta"]["modo"]; t = res["tablas"][modo]; dur = np.array(t["duraciones_min"]); I = np.array(t["intensidad_mmh"])
    fig, ax = plt.subplots(figsize=(8.4, 5));
    for k, tr in enumerate(t["tr"]):
        ax.loglog(dur, I[k], marker="o", ms=3.5, color=colores[k % len(colores)], label=f"Tr {tr} años")
    ax.set_xlabel("duración (min)"); ax.set_ylabel("intensidad (mm/h)"); ax.set_title(f"Curvas IDF · modo «{modo}»"); ax.grid(alpha=.4, which="both"); ax.legend(fontsize=8); fig.tight_layout(rect=(0, .04, 1, 1)); fig.text(.01, .01, pie, fontsize=7, color="#9fb0c6")
    fig.savefig(destino / "idf_curvas.png", dpi=140); plt.close(fig); out.append("idf_curvas.png")
    fig, ax = plt.subplots(figsize=(8.4, 4.4)); tr100 = t["tr"].index(100) if 100 in t["tr"] else -1
    for m, c, ls in (("estacion", "#6cc4ec", "-"), ("escalada", "#ffd166", "--"), ("sitio", "#a98bff", ":")):
        tm = res["tablas"].get(m)
        if tm:
            ax.loglog(tm["duraciones_min"], np.array(tm["intensidad_mmh"])[tr100], ls, color=c, lw=2, label=MODOS[m].split(" (")[0])
    ax.set_xlabel("duración (min)"); ax.set_ylabel("intensidad Tr 100 (mm/h)"); ax.set_title("Los tres modos del libro · Tr 100"); ax.grid(alpha=.4, which="both"); ax.legend(fontsize=8); fig.tight_layout(rect=(0, .04, 1, 1)); fig.text(.01, .01, pie, fontsize=7, color="#9fb0c6")
    fig.savefig(destino / "idf_modos_tr100.png", dpi=140); plt.close(fig); out.append("idf_modos_tr100.png")
    tor = res["tormenta"]; b = np.array(tor["mm_por_bloque"]); dt = tor["duracion_min"] / max(len(b), 1)
    fig, ax = plt.subplots(figsize=(8.4, 4.2)); ax.bar((np.arange(len(b)) + .5) * dt / 60, b, width=dt / 60 * .9, color="#6cc4ec"); ax.invert_yaxis(); ax.set_xlabel("tiempo (h)"); ax.set_ylabel("lluvia por bloque (mm)")
    ax.set_title(f"Tormenta de diseño (bloques alternos) · Tr {tor['tr']} · {tor['duracion_min']} min · P total {sum(b):.1f} mm"); ax.grid(alpha=.4, axis="y"); fig.tight_layout(rect=(0, .04, 1, 1)); fig.text(.01, .01, pie, fontsize=7, color="#9fb0c6")
    fig.savefig(destino / "tormenta_diseno.png", dpi=140); plt.close(fig); out.append("tormenta_diseno.png")
    return out


def guardar(proyecto, datos, estacion=None, duracion_min=180, tr_tormenta=100):
    """Guarda en <proyecto>/registro/idf_x/idf_x_<marca>/: cuadros CSV+Excel de los 3 modos, ecuaciones, estaciones cercanas, curvas y tormenta (PNG) y un JSON con la decisión. Devuelve (resultado, carpeta, archivos)."""
    res = calcular(datos, estacion, duracion_min, tr_tormenta)
    base = Path(proyecto) / "registro" / "idf_x" / f"idf_x_{datetime.now():%Y%m%d_%H%M%S}"; car, k = base, 1
    while car.exists():                                                                         # dos guardados en el mismo segundo: nunca se pisa una carpeta
        k += 1; car = base.with_name(f"{base.name}_{k}")
    car.mkdir(parents=True)
    files = []
    for m, t in res["tablas"].items():
        if t:
            df = pd.DataFrame(t["intensidad_mmh"], index=t["tr"], columns=t["duraciones_min"]); df.index.name = "tr_anios"
            df.to_csv(car / f"idf_{m}.csv"); files.append(f"idf_{m}.csv")
            try:
                df.to_excel(car / f"idf_{m}.xlsx"); files.append(f"idf_{m}.xlsx")
            except Exception:
                pass
    for nombre, filas in (("ecuaciones_zona", res["ecuaciones"]), ("estaciones_cercanas", res["cercanas"])):
        df = pd.DataFrame(filas); df.to_csv(car / f"{nombre}.csv", index=False); files.append(f"{nombre}.csv")
        try:
            df.to_excel(car / f"{nombre}.xlsx", index=False); files.append(f"{nombre}.xlsx")
        except Exception:
            pass
    files += _graficas(res, car)
    (car / "idf_x.json").write_text(json.dumps({**res, "creado": datetime.now().isoformat(timespec="seconds"), "archivos": files}, ensure_ascii=False, indent=1, default=float), encoding="utf-8"); files.append("idf_x.json")
    return res, car, files


def estacion_proyecto(cfg, datos=None):
    """Pluviográfica de referencia del proyecto: la elegida en la configuración o, si no hay, la más cercana al sitio."""
    e = (cfg.get("idf_x") or {}).get("estacion") or (cfg.get("idf_inamhi") or {}).get("estacion")
    if e:
        return e
    if datos:
        try:
            lat, lon = punto(datos)
            return str(pluviograficas_cercanas(lat, lon, 1).iloc[0]["codigo"])
        except Exception:
            pass
    return "M0138"


_PNG_LOCK = __import__("threading").Lock()
_PNG_CACHE = {}


def png(res, nombre):
    """Bytes de una de las gráficas (idf_curvas.png, idf_modos_tr100.png, tormenta_diseno.png) sin guardarlas en el proyecto. matplotlib no admite hilos en paralelo y el navegador pide las tres a la vez:
    las tres se generan juntas, una sola vez por combinación (estación, Tr, duración, lat/lon) y bajo candado."""
    import tempfile
    clave = (res["lat"], res["lon"], res["referencia"]["codigo"], res["tormenta"]["tr"], res["tormenta"]["duracion_min"])
    with _PNG_LOCK:
        if clave not in _PNG_CACHE:
            if len(_PNG_CACHE) > 12:
                _PNG_CACHE.clear()
            with tempfile.TemporaryDirectory() as d:
                _graficas(res, Path(d)); _PNG_CACHE[clave] = {f.name: f.read_bytes() for f in Path(d).glob("*.png")}
        return _PNG_CACHE[clave][nombre]


def fijar_en_proyecto(estado, estacion=None, modo=None):
    """Declara en la configuración del proyecto la IDF X: sitio (lat/lon) y, si se elige, la pluviográfica de referencia. Deja copia .bak de la configuración."""
    from .ui import proyecto as P
    lat, lon = punto(estado.datos)
    cfg_path = Path(estado.carpeta) / estado.datos["config_climanet"]; cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    (cfg_path.parent / f"{cfg_path.name}.{datetime.now():%Y%m%d_%H%M%S}.bak").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    ref = estacion or estacion_proyecto(cfg, estado.datos)
    cfg["idf_x"] = {"lat": lat, "lon": lon, "estacion": ref, "modo": modo or "auto", "fijada": datetime.now().isoformat(timespec="seconds"), "fuente": "INAMHI libro de intensidades"}
    # «estacion» = cuadro exacto de la pluviográfica (sin escalar); «auto»/«escalada» = el modo automático del libro (estación si está a ≤ 10 km; si no, escalada al Idtr del sitio)
    cfg["idf_inamhi"] = {"estacion": ref} if modo == "estacion" else {"lat": lat, "lon": lon, "estacion": ref}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg["idf_x"]
