# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Epsilon · validación de la corrida 2D con observaciones. Cuatro fuentes, contrastadas contra la MISMA corrida:
  1) caudal observado en la estación de salida (por defecto, de observaciones/aforos_caudal.csv)        → KGE, NSE, error de pico y de volumen
  2) mancha de agua Sentinel-1 (por defecto, Earth Engine con la cuenta de la persona)                → CSI, aciertos, falsas alarmas
  3) manchas externas cargadas por la persona (Global Flood Database, Copernicus EMS, SNGR, propias…) → CSI, aciertos, falsas alarmas
  4) evidencia de campo cargada por la persona (marcas de agua, fotos, testimonios, niveles)          → error de calado, acierto mojado/seco
Nada se inventa ni se rellena: si una fuente no existe para el evento, se informa. La validación NO convierte la corrida en predicción.
Todo queda en el proyecto: validacion/ (observaciones cargadas y su registro) y resultados/<corrida>/validacion/ (contrastes)."""
import json
import math
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import calibracion as K

S1_UMBRAL_DB = -16.0          # VV post-evento por debajo: superficie lisa (agua)
S1_CAMBIO_DB = -3.0           # caída respecto de la referencia seca
JRC_PERMANENTE = 50           # % de ocurrencia JRC GSW: agua permanente (lagunas), se excluye del contraste
TOPE_SIM_VALIDACION_H = 96.0  # evento observado de validación (la corrida normal sigue con su tope de 12 h)


class ValidacionError(ValueError):
    pass


def _sello():
    return time.strftime("%Y%m%d_%H%M%S")


def _corrida(carpeta, run):
    d = Path(carpeta) / "resultados" / str(run)
    if not run or ".." in str(run) or not d.is_dir():
        raise ValidacionError("Corrida no encontrada.")
    sal = next(d.rglob("hmax.tif"), None)
    if sal is None:
        raise ValidacionError("La corrida no tiene hmax.tif (¿terminó?).")
    return d, sal.parent


def _registro(carpeta):
    f = Path(carpeta) / "validacion" / "registro.json"
    return f, (json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"manchas_externas": [], "puntos_campo": []})


# ------------------------------------------------------------------ eventos candidatos
def candidatos(carpeta, con_s1=True, max_eventos=20, dias_post=2):
    """Eventos reales (de la calibración aceptada o del último barrido) con su pico; si con_s1, las pasadas de Sentinel-1 entre el pico y pico + dias_post."""
    carpeta = Path(carpeta); base = carpeta / "calibracion"
    acc = sorted((base / "aceptadas").glob("aceptada_*"))
    bar = json.loads((acc[-1] / "aceptacion.json").read_text(encoding="utf-8"))["barrido"] if acc else (sorted((base / "barridos").glob("barrido_*"))[-1].name if (base / "barridos").exists() else None)
    if not bar:
        raise ValidacionError("No hay eventos: selecciona eventos en hidro · Calibración.")
    ev = pd.read_csv(base / "barridos" / bar / "eventos.csv").fillna("")
    q, _ = K.observaciones(carpeta)
    filas = []
    for _, e in ev.iterrows():
        if str(e.get("excluir", "")).lower() in ("si", "sí", "true", "1"):
            continue
        pico = pd.Timestamp(e["pico"]); qp = float(q.get(pico, np.nan)) if q is not None else np.nan
        filas.append({"evento": e["evento"], "inicio": str(e["inicio"])[:10], "pico": str(pico.date()), "fin": str(e["fin"])[:10], "q_pico_m3s": None if not np.isfinite(qp) else round(qp, 2)})
    filas = sorted(filas, key=lambda f: -(f["q_pico_m3s"] or 0))[:max_eventos]
    if con_s1:
        ee = _ee(); aoi = _aoi_proyecto(carpeta)
        for f in filas:
            p0 = pd.Timestamp(f["pico"])
            if p0 < pd.Timestamp("2014-10-03"):
                f["s1"] = []; continue
            col = ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(aoi).filter(ee.Filter.eq("instrumentMode", "IW")).filterDate(str(p0.date()), str((p0 + pd.Timedelta(days=dias_post + 1)).date()))
            f["s1"] = sorted({time.strftime("%Y-%m-%d", time.gmtime(t / 1000)) for t in col.aggregate_array("system:time_start").getInfo()})
        filas.sort(key=lambda f: (not f["s1"], -(f["q_pico_m3s"] or 0)))
    return {"barrido": bar, "eventos": filas, "nota": f"Sentinel-1 buscado entre el pico y {dias_post} días después (el agua baja rápido en cuencas de montaña)." if con_s1 else ""}


# ------------------------------------------------------------------ preparar la corrida del evento observado
def preparar_evento(carpeta, cfg_path, inicio, fin, res_m=None, extra_h=12.0):
    """Hietograma areal diario del evento (lluvia de la cuenca activa, sin rellenar) → config de la corrida como evento observado.
    Deja respaldo .bak de la configuración y guarda los valores previos para restaurarlos con restaurar_config()."""
    carpeta = Path(carpeta); p, msg = K.lluvia_cuenca(carpeta)
    if p is None:
        raise ValidacionError(msg)
    d = p[pd.Timestamp(inicio):pd.Timestamp(fin)]
    if d.empty or d.isna().any():
        raise ValidacionError("La lluvia areal tiene vacíos en esa ventana: no se rellenan. Elige otra ventana.")
    dest = carpeta / "validacion" / "eventos"; dest.mkdir(parents=True, exist_ok=True)
    ide = f"areal_{pd.Timestamp(inicio):%Y%m%d}_{pd.Timestamp(fin):%Y%m%d}"; f = dest / f"hietograma_{ide}_{_sello()}.csv"
    pd.DataFrame({"fecha": d.index.strftime("%Y-%m-%d"), "lluvia_mm": d.values}).to_csv(f, index=False)
    dur_h = 24.0 * len(d); sim = dur_h + float(extra_h)
    if sim > TOPE_SIM_VALIDACION_H:
        raise ValidacionError(f"El evento necesita {sim:g} h simuladas; el tope de validación es {TOPE_SIM_VALIDACION_H:g} h. Recorta la ventana.")
    cfg_path = Path(cfg_path); cfg = json.loads(cfg_path.read_text(encoding="utf-8")); m = _sello()
    (cfg_path.parent / f"{cfg_path.name}.{m}.bak").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    previos = {k: cfg.get(k) for k in ("evento_observado", "sim_horas", "res")}
    cfg["evento_observado"] = {"id": ide, "hietograma_csv": str(f), "bloque_min": 15.0, "desagregacion": "uniforme",
                               "fuente": "lluvia areal de la cuenca (" + msg + ")", "validacion": True, "previos": previos}
    cfg["sim_horas"] = sim
    if res_m:
        cfg["res"] = float(res_m)
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"hietograma": str(f.relative_to(carpeta)).replace("\\", "/"), "dias": len(d), "lluvia_total_mm": round(float(d.sum()), 1), "sim_horas": sim, "res_m": cfg.get("res"),
            "nota": "Lluvia diaria repartida uniformemente en el día (rotulada «desagregada»): el pico 2D horario no es comparable; se compara caudal medio diario."}


def restaurar_config(cfg_path):
    cfg_path = Path(cfg_path); cfg = json.loads(cfg_path.read_text(encoding="utf-8")); ev = cfg.get("evento_observado") or {}
    if not ev.get("validacion"):
        return {"restaurado": False}
    (cfg_path.parent / f"{cfg_path.name}.{_sello()}.bak").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    for k, v in (ev.get("previos") or {}).items():
        if v is None: cfg.pop(k, None)
        else: cfg[k] = v
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"); return {"restaurado": True}


# ------------------------------------------------------------------ 1) caudal observado
def comparar_caudal(carpeta, run):
    carpeta = Path(carpeta); d, sal = _corrida(carpeta, run)
    ent = json.loads((d / "entrada.json").read_text(encoding="utf-8")); ev = (ent.get("config") or {}).get("evento_observado")
    if not ev:
        raise ValidacionError("La corrida no es de un evento observado: el caudal medido solo se compara con lluvia real.")
    f2 = sal / "hidrograma_salida_2d.csv"
    if not f2.exists():
        raise ValidacionError("La corrida no tiene hidrograma en la salida (cuenca activa necesaria).")
    h = pd.read_csv(ev["hietograma_csv"]); t0 = pd.Timestamp(h["fecha"].iloc[0])
    q2 = pd.read_csv(f2); q2.index = t0 + pd.to_timedelta(q2["t_s"], unit="s")
    sim = q2["Q_2d_m3s"].resample("D").mean()
    qo, msg = K.observaciones(carpeta)
    if qo is None:
        raise ValidacionError(msg)
    obs = qo.reindex(sim.index); base = float(obs.iloc[0]); dobs = (obs - base).clip(lower=0)
    ok = dobs.notna() & sim.notna(); o, s = dobs[ok].values, sim[ok].values
    if len(o) < 3:
        raise ValidacionError("Muy pocos días con caudal observado en la ventana del evento.")
    m = K._metricas(o, s)
    res = {"fuente": "caudal observado en la salida", "corrida": run, "dias": int(len(o)), "caudal_base_inicial_m3s": round(base, 3),
           "KGE": m["KGE"], "NSE": m["NSE"], "PBIAS_pct": m["PBIAS_pct"],
           "pico_obs_m3s": round(float(o.max()), 3), "pico_2d_m3s": round(float(s.max()), 3), "error_pico_pct": round(100 * (s.max() - o.max()) / max(o.max(), 1e-9), 1),
           "volumen_obs_m3": round(float(o.sum() * 86400)), "volumen_2d_m3": round(float(s.sum() * 86400)),
           "nota": "Escorrentía directa diaria: caudal observado menos el caudal del primer día (la 2D arranca seca y no simula el caudal base). Lluvia diaria desagregada."}
    out = d / "validacion"; out.mkdir(exist_ok=True)
    pd.DataFrame({"fecha": sim.index.strftime("%Y-%m-%d"), "Q_obs_directo_m3s": dobs.values, "Q_2d_m3s": sim.values}).to_csv(out / "caudal_obs_vs_2d.csv", index=False)
    (out / "caudal.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 4), dpi=130); ax.plot(sim.index, dobs.values, "-o", color="black", label="observado (directo)")
        ax.plot(sim.index, sim.values, "-s", color="#1f63c6", label="2D en la salida"); ax.set_ylabel("caudal medio diario (m³/s)"); ax.grid(alpha=.3); ax.legend()
        ax.set_title(f"Validación 1 · caudal · KGE {m['KGE']:.2f} · NSE {m['NSE']:.2f}"); fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(out / "caudal_obs_vs_2d.png"); plt.close(fig)
    except Exception:
        pass
    return res


# ------------------------------------------------------------------ contraste de manchas (2, 3) y puntos (4)
def contingencia(obs, sim, valido):
    """Tabla de contingencia de mojado/seco: aciertos, fallos (observado y no simulado), falsas alarmas y CSI."""
    o, s, v = np.asarray(obs, bool), np.asarray(sim, bool), np.asarray(valido, bool)
    H = int((o & s & v).sum()); M = int((o & ~s & v).sum()); F = int((~o & s & v).sum())
    return {"aciertos": H, "fallos": M, "falsas_alarmas": F, "CSI": round(H / (H + M + F), 3) if (H + M + F) else None,
            "tasa_aciertos": round(H / (H + M), 3) if (H + M) else None, "tasa_falsas_alarmas": round(F / (H + F), 3) if (H + F) else None,
            "sesgo_area": round((H + F) / (H + M), 3) if (H + M) else None}


def _grilla(sal):
    import rasterio
    with rasterio.open(sal / "hmax.tif") as r:
        return r.read(1, masked=True).filled(np.nan), r.profile, r.transform, r.crs


def _guardar_mascara(destino, arr, perfil):
    import rasterio
    p = dict(perfil); p.update(dtype="uint8", count=1, nodata=255)
    with rasterio.open(destino, "w", **p) as w:
        w.write(arr.astype("uint8"), 1)


def _contrastar_mascara(sal, obs_mask, nombre, permanente=None, umbrales=(0.05, 0.3)):
    hmax, perfil, T, crs = _grilla(sal); valido = np.isfinite(hmax)
    if permanente is not None:
        valido &= ~permanente
    return {f"h_ge_{u:g}m": contingencia(obs_mask, np.nan_to_num(hmax) >= u, valido) for u in umbrales}


def _ee():
    from . import gee_conexion as G
    e = G.estado()
    if not e.get("conectado"):
        e = G.conectar()
    if not e.get("conectado"):
        raise ValidacionError("Earth Engine no está conectado: conéctalo en 2 · Datos / GEE con tu cuenta.")
    import ee
    return ee


def _aoi_proyecto(carpeta):
    ee = _ee(); act = Path(carpeta) / "cuenca" / "activa.json"
    a = json.loads(act.read_text(encoding="utf-8")) if act.exists() else None
    import geopandas as gpd
    g = gpd.read_file(Path(carpeta) / a["carpeta"] / "cuenca.gpkg").to_crs(4326) if a else None
    if g is None:
        raise ValidacionError("Activa una cuenca para buscar Sentinel-1.")
    x0, y0, x1, y1 = g.total_bounds; return ee.Geometry.Rectangle([float(x0), float(y0), float(x1), float(y1)])


def mancha_sentinel1(carpeta, run, fecha_pico, dias_post=2, dias_ref=(60, 5)):
    """2) Mancha Sentinel-1 VV: referencia seca (mediana de dias_ref antes del evento) y la primera pasada entre el pico y pico + dias_post.
    Agua = VV_post < S1_UMBRAL_DB y VV_post − VV_ref < S1_CAMBIO_DB; se excluye el agua permanente (JRC GSW ≥ 50 %). Se descarga en la grilla de la 2D."""
    import io, urllib.request, rasterio
    carpeta = Path(carpeta); d, sal = _corrida(carpeta, run); ee = _ee()
    hmax, perfil, T, crs = _grilla(sal); ny, nx = hmax.shape
    from pyproj import Transformer
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    xs = [T.c, T.c + T.a * nx]; ys = [T.f, T.f + T.e * ny]; lo, la = tr.transform([xs[0], xs[1], xs[0], xs[1]], [ys[0], ys[0], ys[1], ys[1]])
    aoi = ee.Geometry.Rectangle([min(lo), min(la), max(lo), max(la)])
    p0 = pd.Timestamp(fecha_pico)
    col = ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(aoi).filter(ee.Filter.eq("instrumentMode", "IW")).filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")).select("VV")
    post_c = col.filterDate(str(p0.date()), str((p0 + pd.Timedelta(days=dias_post + 1)).date())).sort("system:time_start")
    n_post = post_c.size().getInfo()
    if n_post == 0:
        raise ValidacionError(f"No hay pasadas de Sentinel-1 entre {p0.date()} y {(p0 + pd.Timedelta(days=dias_post)).date()}: elige otro evento.")
    t_post = time.strftime("%Y-%m-%d", time.gmtime(post_c.first().get("system:time_start").getInfo() / 1000))
    post = post_c.filterDate(t_post, str((pd.Timestamp(t_post) + pd.Timedelta(days=1)).date())).mosaic()
    ref = col.filterDate(str((p0 - pd.Timedelta(days=dias_ref[0])).date()), str((p0 - pd.Timedelta(days=dias_ref[1])).date())).median()
    agua = post.lt(S1_UMBRAL_DB).And(post.subtract(ref).lt(S1_CAMBIO_DB)).unmask(0)
    perm = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).gte(JRC_PERMANENTE)
    img = agua.rename("agua").addBands(perm.rename("permanente")).toByte()
    url = img.getDownloadURL({"crs": str(crs), "crs_transform": [T.a, T.b, T.c, T.d, T.e, T.f], "dimensions": f"{nx}x{ny}", "format": "GEO_TIFF"})
    b = urllib.request.urlopen(url, timeout=300).read()
    with rasterio.open(io.BytesIO(b)) as r:
        A = r.read(1).astype(bool); P = r.read(2).astype(bool)
    out = d / "validacion"; out.mkdir(exist_ok=True)
    _guardar_mascara(out / f"sentinel1_agua_{t_post}.tif", A, perfil); _guardar_mascara(out / "jrc_agua_permanente.tif", P, perfil)
    res = {"fuente": "Sentinel-1 (VV, Earth Engine)", "corrida": run, "fecha_pico": str(p0.date()), "fecha_imagen": t_post, "dias_despues_del_pico": int((pd.Timestamp(t_post) - p0).days),
           "celdas_agua_s1": int(A.sum()), "celdas_permanentes_excluidas": int(P.sum()),
           "metodo": f"VV post < {S1_UMBRAL_DB} dB y caída > {-S1_CAMBIO_DB} dB respecto de la mediana {dias_ref[0]}–{dias_ref[1]} días antes; agua permanente JRC GSW ≥ {JRC_PERMANENTE} % excluida.",
           "contraste": _contrastar_mascara(sal, A, "s1", permanente=P),
           "limites": "Sentinel-1 (≈ 10 m remuestreado a la celda 2D) no ve cauces más estrechos que la celda ni agua bajo vegetación densa; la pasada puede llegar después del pico."}
    (out / "sentinel1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def registrar_mancha_externa(carpeta, ruta, fuente, fecha, nombre=None):
    """3) Mancha observada de otra fuente (polígono .gpkg/.shp/.geojson o ráster 0/1). Se copia al proyecto con su fuente y fecha; no se modifica."""
    carpeta = Path(carpeta); ruta = Path(ruta)
    if not ruta.exists():
        raise ValidacionError(f"No existe {ruta}.")
    if not str(fuente).strip() or not str(fecha).strip():
        raise ValidacionError("Declara la fuente y la fecha de la mancha.")
    dest = carpeta / "validacion" / "manchas_externas" / f"{_sello()}_{ruta.stem}"; dest.mkdir(parents=True)
    for f in ruta.parent.glob(ruta.stem + ".*"):
        shutil.copy2(f, dest / f.name)
    f, reg = _registro(carpeta); f.parent.mkdir(parents=True, exist_ok=True)
    item = {"nombre": nombre or ruta.stem, "archivo": str((dest / ruta.name).relative_to(carpeta)).replace("\\", "/"), "fuente": fuente, "fecha": str(fecha), "registrado": time.strftime("%Y-%m-%dT%H:%M:%S")}
    reg["manchas_externas"].append(item); f.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8"); return item


def registrar_puntos_campo(carpeta, ruta_csv, fuente):
    """4) Evidencia de campo: CSV con x,y (CRS del proyecto) o lon,lat; y calado_obs_m (marca de agua) y/o mojado (1/0); fecha y descripcion opcionales."""
    carpeta = Path(carpeta); d = pd.read_csv(ruta_csv)
    if not ({"x", "y"} <= set(d.columns) or {"lon", "lat"} <= set(d.columns)):
        raise ValidacionError("El CSV necesita columnas x,y (CRS del proyecto) o lon,lat.")
    if not ({"calado_obs_m"} & set(d.columns) or {"mojado"} & set(d.columns)):
        raise ValidacionError("El CSV necesita calado_obs_m (marca de agua, m) y/o mojado (1 = hubo agua, 0 = seco).")
    if not str(fuente).strip():
        raise ValidacionError("Declara la fuente de la evidencia de campo.")
    dest = carpeta / "validacion" / "puntos_campo"; dest.mkdir(parents=True, exist_ok=True); f2 = dest / f"{_sello()}_{Path(ruta_csv).name}"; shutil.copy2(ruta_csv, f2)
    f, reg = _registro(carpeta); f.parent.mkdir(parents=True, exist_ok=True)
    item = {"archivo": str(f2.relative_to(carpeta)).replace("\\", "/"), "fuente": fuente, "n_puntos": int(len(d)), "registrado": time.strftime("%Y-%m-%dT%H:%M:%S")}
    reg["puntos_campo"].append(item); f.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8"); return item


def _mascara_externa(carpeta, item, sal):
    hmax, perfil, T, crs = _grilla(sal); arch = Path(carpeta) / item["archivo"]
    if arch.suffix.lower() in (".tif", ".tiff"):
        import rasterio
        from rasterio.warp import reproject, Resampling
        out = np.zeros(hmax.shape, "float32")
        with rasterio.open(arch) as r:
            reproject(rasterio.band(r, 1), out, dst_transform=T, dst_crs=crs, resampling=Resampling.nearest)
        return out > 0.5
    import geopandas as gpd
    from rasterio import features
    g = gpd.read_file(arch).to_crs(crs)
    return features.rasterize(((geom, 1) for geom in g.geometry if geom is not None), out_shape=hmax.shape, transform=T, fill=0).astype(bool)


def _puntos(carpeta, item, sal):
    hmax, perfil, T, crs = _grilla(sal); d = pd.read_csv(Path(carpeta) / item["archivo"])
    if {"x", "y"} <= set(d.columns):
        x, y = d["x"].astype(float).values, d["y"].astype(float).values
    else:
        from pyproj import Transformer
        x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(d["lon"].astype(float).values, d["lat"].astype(float).values)
    inv = ~T; filas = []
    for i, (xi, yi) in enumerate(zip(x, y)):
        c, r = inv * (xi, yi); r, c = int(math.floor(r)), int(math.floor(c))
        dentro = 0 <= r < hmax.shape[0] and 0 <= c < hmax.shape[1] and np.isfinite(hmax[r, c])
        hs = float(hmax[r, c]) if dentro else None
        fila = {"punto": i + 1, "dentro_del_dominio": dentro, "calado_2d_m": hs}
        if "calado_obs_m" in d.columns and pd.notna(d["calado_obs_m"].iloc[i]) and dentro:
            fila["calado_obs_m"] = float(d["calado_obs_m"].iloc[i]); fila["error_m"] = round(hs - fila["calado_obs_m"], 3)
        if "mojado" in d.columns and pd.notna(d["mojado"].iloc[i]) and dentro:
            fila["mojado_obs"] = bool(int(d["mojado"].iloc[i])); fila["mojado_2d"] = bool(hs >= 0.05); fila["acierto"] = fila["mojado_obs"] == fila["mojado_2d"]
        filas.append(fila)
    T_ = pd.DataFrame(filas); res = {"fuente": item["fuente"], "archivo": item["archivo"], "n_puntos": len(filas), "n_dentro": int(T_["dentro_del_dominio"].sum())}
    if "error_m" in T_:
        e = T_["error_m"].dropna(); res.update(error_medio_m=round(float(e.mean()), 3), error_abs_medio_m=round(float(e.abs().mean()), 3), rmse_m=round(float(np.sqrt((e ** 2).mean())), 3))
    if "acierto" in T_:
        a = T_["acierto"].dropna(); res["acierto_mojado_seco_pct"] = round(100 * float(a.mean()), 1)
    res["puntos"] = filas; return res


def contrastar(carpeta, run):
    """Tabla única de las cuatro fuentes para una corrida (usa lo ya calculado para 1 y 2; calcula 3 y 4 con lo registrado)."""
    carpeta = Path(carpeta); d, sal = _corrida(carpeta, run); out = d / "validacion"; out.mkdir(exist_ok=True)
    filas = []
    c = out / "caudal.json"
    if c.exists():
        j = json.loads(c.read_text(encoding="utf-8")); filas.append({"n": 1, "fuente": j["fuente"], "tipo": "por defecto", "metrica": f"KGE {j['KGE']:.2f} · NSE {j['NSE']:.2f} · error de pico {j['error_pico_pct']:+.0f} %"})
    else:
        filas.append({"n": 1, "fuente": "caudal observado en la salida", "tipo": "por defecto", "metrica": "pendiente: «Comparar con caudal observado» (requiere corrida con evento observado)"})
    s = out / "sentinel1.json"
    if s.exists():
        j = json.loads(s.read_text(encoding="utf-8")); k = j["contraste"]["h_ge_0.05m"]
        filas.append({"n": 2, "fuente": f"{j['fuente']} · {j['fecha_imagen']} (+{j['dias_despues_del_pico']} d)", "tipo": "por defecto", "metrica": f"CSI {k['CSI']} · aciertos {k['tasa_aciertos']} · falsas alarmas {k['tasa_falsas_alarmas']}"})
    else:
        filas.append({"n": 2, "fuente": "Sentinel-1 (Earth Engine)", "tipo": "por defecto", "metrica": "pendiente: «Mancha Sentinel-1»"})
    _, reg = _registro(carpeta); det = {"manchas_externas": [], "puntos_campo": []}
    for it in reg["manchas_externas"]:
        try:
            ct = _contrastar_mascara(sal, _mascara_externa(carpeta, it, sal), it["nombre"]); k = ct["h_ge_0.05m"]
            det["manchas_externas"].append({**it, "contraste": ct}); filas.append({"n": 3, "fuente": f"{it['fuente']} · {it['fecha']}", "tipo": "cargada por la persona", "metrica": f"CSI {k['CSI']} · aciertos {k['tasa_aciertos']} · falsas alarmas {k['tasa_falsas_alarmas']}"})
        except Exception as e:
            filas.append({"n": 3, "fuente": it["fuente"], "tipo": "cargada por la persona", "metrica": "error: " + str(e)[:120]})
    if not reg["manchas_externas"]:
        filas.append({"n": 3, "fuente": "mancha externa (Global Flood Database, Copernicus EMS, SNGR, propia)", "tipo": "abierta", "metrica": "sin cargar"})
    for it in reg["puntos_campo"]:
        try:
            r = _puntos(carpeta, it, sal); det["puntos_campo"].append(r)
            m = " · ".join(x for x in (f"RMSE calado {r['rmse_m']} m" if "rmse_m" in r else "", f"acierto mojado/seco {r['acierto_mojado_seco_pct']} %" if "acierto_mojado_seco_pct" in r else "") if x)
            filas.append({"n": 4, "fuente": it["fuente"], "tipo": "cargada por la persona", "metrica": f"{r['n_dentro']}/{r['n_puntos']} puntos dentro · " + m})
        except Exception as e:
            filas.append({"n": 4, "fuente": it["fuente"], "tipo": "cargada por la persona", "metrica": "error: " + str(e)[:120]})
    if not reg["puntos_campo"]:
        filas.append({"n": 4, "fuente": "evidencia de campo (marcas de agua, fotos, testimonios, niveles)", "tipo": "abierta", "metrica": "sin cargar"})
    res = {"corrida": run, "tabla": filas, "detalle": det, "nota": "Contraste de UNA corrida con las observaciones disponibles. No convierte la corrida en predicción ni en mapa de amenaza."}
    (out / "contraste.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return res
