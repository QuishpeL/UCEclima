# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Pipeline integrado: DEM + IDF oficial + lluvia sobre malla (área interna) + cuencas externas (BasinModel)
como hidrogramas de entrada al solver 2D + procedencia.

Resultado: escenario de DISEÑO basado en IDF histórica. No es un evento observado, no está calibrado y no es HEC-RAS.

Partición de áreas (evita contar dos veces la escorrentía): la lluvia sobre malla actúa SOLO sobre el dominio 2D;
cada cuenca externa aporta únicamente el área de su polígono que queda FUERA del dominio 2D.
"""
import hashlib, json, subprocess, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from rasterio.features import rasterize
from shapely.geometry import shape, box
from shapely.ops import unary_union
import geopandas as gpd
from . import terrain, idf as idfm, inamhi
from .basin import BasinModel, Subbasin
from .forcing import DesignStorm
from . import evento as evm
from .hydrology import excess_scs
from .hydraulics import simulate, Options
from .evaluacion_numerica import evaluar as evaluar_numerica
from .diagnostico import diagnostico_entradas
from . import subgrid as SG
from rasterio.transform import Affine

NMAP = {10: .12, 20: .05, 30: .035, 40: .04, 50: .08, 60: .03, 80: .03, 90: .05, 95: .05, 100: .035}
ETIQUETA = "diseno_idf_historica"
AVISO_EVENTO = ("Evento de lluvia OBSERVADO (histórico) simulado con un modelo NO calibrado ni validado: no es una validación, no es una huella de inundación observada y no es una simulación HEC-RAS.")
AVISOS_FORZAMIENTO = {"evento_observado": AVISO_EVENTO,
                      "pronostico": ("PRONÓSTICO de lluvia simulado con un modelo NO calibrado ni validado: no es una observación, no es una huella de inundación y no es una alerta oficial (INAMHI / SNGR). "
                                     "Un pronóstico a ~25 km falla a menudo en la ubicación y la intensidad de los aguaceros."),
                      "estimacion_satelital": ("Lluvia ESTIMADA POR SATÉLITE (no medida en tierra) simulada con un modelo NO calibrado ni validado: en islas y aguaceros convectivos el satélite subestima mucho; "
                                               "no es una huella de inundación observada.")}
AVISO = ("Escenario de DISEÑO con IDF histórica; no es un evento observado, no está calibrado ni validado y "
         "no es una simulación HEC-RAS.")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def verificar_config(cfg):
    """Comprueba que existan las entradas, que el escenario sea histórico y devuelve su procedencia (hashes)."""
    errores, prov = [], {}
    for k in ("dem", "cn_tif", "cobertura_tif", "manning_tif"):
        if cfg.get(k):
            if not Path(cfg[k]).exists():
                errores.append(f"No existe {k}: {cfg[k]}")
            else:
                prov[k] = {"ruta": cfg[k], "sha256": _sha(cfg[k])}
    for c in cfg.get("cuencas_externas", []):
        if not Path(c["shp"]).exists():
            errores.append(f"No existe la geometría de la cuenca externa {c.get('nombre')}: {c['shp']}")
        else:
            prov["cuenca_" + c["nombre"]] = {"ruta": c["shp"], "sha256": _sha(c["shp"])}
        for k in ("nombre", "cn"):
            if c.get(k) is None:
                errores.append(f"Cuenca externa {c.get('nombre')}: falta '{k}' (debe declararse con su fuente)")
        if c.get("tc_h") is None and c.get("lag_h") is None:
            errores.append(f"Cuenca externa {c.get('nombre')}: falta tc_h o lag_h (con su fuente)")
        if c.get("entrada_xy") is None:
            errores.append(f"Cuenca externa {c.get('nombre')}: entrada_xy pendiente; la entrada debe definirse sobre un canal confirmado")
    for e in cfg.get("entradas_geoglows", []) or []:                                # Lambda 9.2: río grande sin datos → hidrograma de GEOGLOWS
        for k in ("nombre", "xy", "gumbel", "forma"):
            if not e.get(k):
                errores.append(f"Entrada GEOGLOWS {e.get('nombre')}: falta '{k}' (vuelve a analizar el tramo en la pantalla)")
    if cfg.get("evento_observado") and cfg.get("entradas_geoglows"):
        errores.append("Las entradas GEOGLOWS solo se usan con tormentas de diseño (un evento observado no tiene período de retorno): quítalas o usa el diseño IDF")
    if cfg.get("evento_observado"):
        if cfg.get("cuencas_externas"):
            errores.append("evento_observado con cuencas_externas aún no está soportado (los hidrogramas externos se generan con la tormenta de diseño); se omiten o se usa el diseño IDF")
        if not Path(cfg["evento_observado"].get("hietograma_csv", "")).exists():
            errores.append("No existe evento_observado.hietograma_csv")
        else:
            prov["evento_observado"] = {"ruta": cfg["evento_observado"]["hietograma_csv"], "sha256": _sha(cfg["evento_observado"]["hietograma_csv"])}
    elif not (cfg.get("idf_inamhi") or cfg.get("idf_csv")):
        errores.append("Falta la fuente de IDF (idf_inamhi o idf_csv)")
    if cfg.get("escenarios") and set(cfg["escenarios"]) - {ETIQUETA}:
        errores.append("Los escenarios de cambio climático están desactivados; solo se admite " + ETIQUETA)
    if errores:
        raise ValueError("Configuración inválida:\n - " + "\n - ".join(errores))
    try:
        git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip()
    except Exception:
        git = ""
    prov["codigo_sha256"] = {p.name: _sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    prov["git"] = git or "sin repositorio"
    prov["python"] = sys.version.split()[0]
    return prov


def _celda(meta, x, y):
    c = ~meta["transform"] * (x, y)
    return int(c[1]), int(c[0])


def _hidrograma_externo(cfg_c, idf, tr, storm_min, meta, active, dem_shape):
    """Hidrograma de una cuenca externa (solo su área fuera del dominio 2D) y celda de entrada."""
    g = gpd.read_file(cfg_c["shp"])
    if g.crs is not None and getattr(g.crs, "sub_crs_list", None):      # CRS compuesto: componente horizontal (vertical desconocido)
        g = g.set_crs(g.crs.sub_crs_list[0], allow_override=True)
    g = g.to_crs(meta["crs"])
    if cfg_c.get("campo"):
        g = g[g[cfg_c["campo"]].astype(str) == str(cfg_c["valor"])]
        if len(g) != 1:
            raise ValueError(f"{cfg_c['nombre']}: el filtro {cfg_c['campo']}={cfg_c['valor']} devolvió {len(g)} elementos (se espera 1).")
    elif cfg_c.get("fila") is not None:
        g = g.iloc[[cfg_c["fila"]]]
    poly = unary_union(g.geometry)
    t = meta["transform"]
    dominio = box(*rasterio.transform.array_bounds(meta["height"], meta["width"], t)[:4])
    dominio = box(t.c, t.f + t.e * meta["height"], t.c + t.a * meta["width"], t.f)
    externa = poly.difference(dominio)
    area_km2 = externa.area / 1e6
    if area_km2 <= 0:
        return None
    r, c = _celda(meta, *cfg_c["entrada_xy"])
    if not (0 <= r < dem_shape[0] and 0 <= c < dem_shape[1]) or not active[r, c]:
        raise ValueError(f"La entrada de {cfg_c['nombre']} no cae en una celda activa del dominio 2D.")
    edges, blocks = idfm.design_storm(idf, tr, storm_min, 1.0)
    cen = externa.centroid
    storm = DesignStorm(idf, tr, storm_min, 1.0)
    bm = BasinModel([Subbasin(cfg_c["nombre"], area_km2, cfg_c["cn"], cfg_c.get("tc_h"), cen.x, cen.y, lag_h=cfg_c.get("lag_h"),
                              prf=cfg_c.get("prf", 484.0), imperv_frac=cfg_c.get("imperv_frac", 0.0))])
    q = bm.run(storm, step_s=300)[cfg_c["nombre"]]
    t_q, v_q = q.index.values.astype(float), q.values.copy()
    v_q[-1] = 0.0   # la cola debe terminar en cero (exigido por el solver)
    return {"nombre": cfg_c["nombre"], "area_externa_km2": area_km2, "area_poligono_km2": poly.area / 1e6,
            "celda": (r, c), "geometria_externa": externa, "t": t_q, "q": v_q, "volumen_m3": float(np.trapezoid(v_q, t_q) if hasattr(np, "trapezoid") else np.trapz(v_q, t_q)),
            "informe": bm.informe[cfg_c["nombre"]]}


def _write(path, arr, active, meta):
    p = {k: v for k, v in meta.items() if k not in ("cobertura_dem", "aviso")}
    p.update(dtype="float32", nodata=-9999, compress="deflate")
    with rasterio.open(path, "w", **p) as s:
        s.write(np.where(active, arr, -9999).astype("float32"), 1)


def _guardar_fotos(path, fotos, hmax, active, area_celda, umbral=0.01):
    """Evolución del calado para el visor: solo celdas que alguna vez superan `umbral` m, calado en mm (uint16), más el volumen y
    el área mojada de cada foto. Es lo que el solver tuvo en ese instante; no se interpola ni se recalcula nada."""
    if not fotos or not fotos.get("t_s"):
        return
    idx = np.flatnonzero((active & (hmax >= umbral)).ravel())
    H = np.stack([np.asarray(f, dtype=np.float32).ravel()[idx] for f in fotos["h"]]) if len(idx) else np.zeros((len(fotos["t_s"]), 0), np.float32)
    vol = np.array([float(np.asarray(f, dtype=np.float64)[active].sum()) * area_celda for f in fotos["h"]])
    np.savez_compressed(path, t_s=np.asarray(fotos["t_s"], float), idx=idx.astype(np.uint32), shape=np.asarray(hmax.shape),
                        h_mm=np.clip(np.round(H * 1000), 0, 65535).astype(np.uint16), volumen_m3=vol,
                        area_mojada_m2=(H >= 0.05).sum(axis=1) * area_celda, umbral_m=umbral)


# ------------------------------------------------------------------ Epsilon · E1 (MDT de alta resolución de punta a punta)
def rellenar_depresiones(dem, area_celda, max_m=None):
    """Relleno DECLARADO de depresiones (opción, nunca por defecto). Con max_m solo se rellenan las depresiones cuya
    profundidad máxima es ≤ max_m (artefactos del MDT); las más profundas (lagunas reales) se conservan intactas."""
    from scipy import ndimage
    filled = terrain.fill_sinks(dem)
    d = np.where(np.isfinite(dem), filled - dem, 0.0); d[d < 1e-6] = 0.0
    lab, n = ndimage.label(d > 0, structure=np.ones((3, 3)))
    conservadas = 0
    if max_m is not None and n:
        pmax = ndimage.maximum(d, lab, index=np.arange(1, n + 1))
        quitar = np.flatnonzero(pmax > float(max_m)) + 1; conservadas = len(quitar)
        d[np.isin(lab, quitar)] = 0.0
    nuevo = np.where(np.isfinite(dem), dem + d, np.nan)
    info = {"modo": "todas" if max_m is None else f"solo depresiones de profundidad ≤ {float(max_m):g} m", "umbral_m": None if max_m is None else float(max_m),
            "depresiones_encontradas": int(n), "depresiones_conservadas": int(conservadas), "celdas_rellenadas": int((d > 0).sum()),
            "volumen_almacenamiento_quitado_m3": float(d.sum() * area_celda), "profundidad_max_rellenada_m": float(d.max()) if d.size else 0.0,
            "aviso": "Opción declarada: el relleno quita almacenamiento del terreno (lagunas, depresiones). Úsalo para artefactos del MDT, no para lagunas reales."}
    return nuevo, info, d


def _celda_de_xy(xy, meta, active):
    """Celda activa más cercana a (x, y) en el CRS del proyecto."""
    inv = ~meta["transform"]; c, r = inv * (float(xy[0]), float(xy[1])); r, c = int(np.floor(r)), int(np.floor(c))
    ny, nx = active.shape
    if not (0 <= r < ny and 0 <= c < nx):
        raise ValueError(f"El punto {xy} queda fuera del dominio 2D.")
    if active[r, c]:
        return r, c
    rr, cc = np.nonzero(active); k = int(np.argmin((rr - r) ** 2 + (cc - c) ** 2)); return int(rr[k]), int(cc[k])


def leer_hidrograma_entrada(e):
    """{'nombre','csv' (columnas t_s y Q_m3s) | 't_s','q_m3s', 'xy':[x,y]} → (t, q). Debe empezar en t=0 y terminar en Q=0 (no se inventa la cola)."""
    if e.get("csv"):
        d = pd.read_csv(e["csv"]); ct = next((c for c in d.columns if c.lower() in ("t_s", "tiempo_s", "t")), None); cq = next((c for c in d.columns if c.lower() in ("q_m3s", "caudal_m3s", "q")), None)
        if ct is None or cq is None:
            raise ValueError(f"Hidrograma {e.get('nombre')}: el CSV necesita columnas t_s y Q_m3s.")
        t, q = d[ct].astype(float).values, d[cq].astype(float).values
    else:
        t, q = np.asarray(e["t_s"], float), np.asarray(e["q_m3s"], float)
    if len(t) < 2 or t[0] != 0 or np.any(np.diff(t) <= 0) or np.any(q < 0) or q[-1] != 0:
        raise ValueError(f"Hidrograma {e.get('nombre')}: debe empezar en t = 0 s, crecer en el tiempo, no tener caudales negativos y TERMINAR en Q = 0 (la cola no se inventa).")
    return t, q


def seccion_salida(dem, active, rc, semiancho=5, pasos=6):
    """Sección transversal en la celda de salida. La dirección del río se toma del recorrido aguas abajo de `pasos` celdas
    (máxima pendiente sobre el terreno sin depresiones), no de una sola celda: con celdas gruesas la dirección local puede ser lateral.
    Devuelve (eje, índice_cara, (lo, hi), signo)."""
    r0, c0 = rc; ny, nx = dem.shape
    bordes = {"o": c0, "e": nx - 1 - c0, "n": r0, "s": ny - 1 - r0}                # G25: salida pegada a un borde → el río sale por ese borde
    lado = min(bordes, key=bordes.get)
    if bordes[lado] < max(int(semiancho), 3):                                   # la sección misma tocaría el borde: el río sale por él
        if lado in ("o", "e"):
            return "x", (c0 if lado == "o" else c0 + 1), (max(r0 - semiancho, 0), min(r0 + semiancho + 1, ny)), (-1.0 if lado == "o" else 1.0)
        return "y", (r0 if lado == "n" else r0 + 1), (max(c0 - semiancho, 0), min(c0 + semiancho + 1, nx)), (-1.0 if lado == "n" else 1.0)
    z = np.where(active, dem, np.nan)
    try:
        z = terrain.fill_sinks(z)
    except Exception:
        pass
    r, c, vistos = r0, c0, {(r0, c0)}
    for _ in range(pasos):
        best, sig = -np.inf, None
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                rr, cc = r + a, c + b
                if (a or b) and 0 <= rr < ny and 0 <= cc < nx and active[rr, cc] and (rr, cc) not in vistos and np.isfinite(z[rr, cc]):
                    pend = (z[r, c] - z[rr, cc]) / np.hypot(a, b)
                    if pend > best:
                        best, sig = pend, (rr, cc)
        if sig is None:
            break
        r, c = sig; vistos.add(sig)
    dr, dc = r - r0, c - c0
    if dr == 0 and dc == 0:
        dc = 1
    if abs(dc) >= abs(dr):
        return "x", (c0 + 1 if dc >= 0 else c0), (max(r0 - semiancho, 0), min(r0 + semiancho + 1, ny)), (1.0 if dc >= 0 else -1.0)
    return "y", (r0 + 1 if dr >= 0 else r0), (max(c0 - semiancho, 0), min(c0 + semiancho + 1, nx)), (1.0 if dr >= 0 else -1.0)

def hidrograma_hu_scs(edges, blocks, cn, lam, lag_h, prf, area_km2):
    """Hidrograma del modelo de eventos de hidro (SCS-CN agregado + HU triangular SCS) para la MISMA tormenta, paso = bloques de lluvia.
    Misma formulación que uceclima.matematica_propia.uh_scs (tp = Δt/2 + lag; qp = k·PRF·A/tp con k = conversión exacta de unidades; Tb por volumen de 1 mm)."""
    dt = float(edges[1] - edges[0]); dt_h = dt / 3600
    pe = np.diff(np.r_[0, excess_scs(np.cumsum(blocks), float(cn), float(lam))])
    tp = dt_h / 2 + float(lag_h); qp = (0.028316846592 / (2.589988110336 * 25.4)) * float(prf) * float(area_km2) / tp; tb = 2000.0 * float(area_km2) / (3600.0 * qp)
    n = int(np.ceil(tb / dt_h)); tt = np.arange(n + 1) * dt_h
    acum = lambda t: np.where(np.minimum(t, tb) <= tp, 0.5 * np.minimum(t, tb) ** 2 / tp, 0.5 * tp + (np.minimum(t, tb) - tp) * (1 - 0.5 * (np.minimum(t, tb) - tp) / (tb - tp)))
    ai = np.diff(acum(tt)); u = ai / ai.sum() * (1000.0 * float(area_km2) / 3600.0) / dt_h
    q = np.convolve(pe, u); return np.arange(1, len(q) + 1) * dt, q


def velocidades_anomalas(vmax, hmax, active, meta, umbral_ms=10.0):
    """Marca (no corrige) celdas con velocidad máxima irreal: somera y empinada (q/h con h pequeño). Devuelve info y máscara."""
    mojada = active & (hmax >= 0.05); m = mojada & (vmax > float(umbral_ms))
    info = {"umbral_ms": float(umbral_ms), "celdas_anomalas": int(m.sum()), "pct_de_celdas_mojadas": float(100 * m.sum() / max(mojada.sum(), 1)),
            "velocidad_max_ms": float(vmax[active].max()) if active.any() else 0.0,
            "velocidad_max_robusta_ms": float(vmax[mojada & ~m].max()) if (mojada & ~m).any() else 0.0,
            "p99_mojadas_ms": float(np.percentile(vmax[mojada], 99)) if mojada.any() else 0.0,
            "nota": "Diagnóstico: se marcan, no se corrigen. Suelen ser celdas muy someras y empinadas; la velocidad robusta excluye esas celdas."}
    if m.any():
        r, c = np.unravel_index(np.argmax(np.where(m, vmax, -1)), vmax.shape); x, y = meta["transform"] * (c + 0.5, r + 0.5)
        info["celda_max"] = {"fila": int(r), "columna": int(c), "x": float(x), "y": float(y), "calado_max_m": float(hmax[r, c])}
    return info, m


def run(cfg, scenario=ETIQUETA, tr=None, progress=print):
    if scenario != ETIQUETA:
        raise ValueError("Cambio climático desactivado: solo " + ETIQUETA)
    prov = verificar_config(cfg)
    ev = cfg.get("evento_observado")
    tr = int(tr or cfg.get("Tr", 100))
    if ev:
        tr = None                                                         # un evento observado no tiene período de retorno de diseño
        out = Path(cfg["out_dir"]) / f"Evento_{str(ev.get('id') or Path(ev['hietograma_csv']).stem)}_historico"
    else:
        out = Path(cfg["out_dir"]) / f"Tr{tr}_{ETIQUETA}"
    out.mkdir(parents=True, exist_ok=True)
    res = float(cfg.get("res", 10))
    solver = cfg.get("solver", "malla")
    if solver not in ("malla", "subgrid"):
        raise ValueError("solver debe ser 'malla' o 'subgrid'.")
    modelo_sg = None
    if solver == "subgrid":
        # Celda gruesa = m×m píxeles finos del MDT; la hidráulica usa volumen-elevación y secciones de cara subcelda.
        rf = float(cfg.get("rf_m", 2.0)); m = int(round(res / rf))
        if m < 1 or abs(m * rf - res) > 1e-9:
            raise ValueError("res debe ser múltiplo de rf_m en el solver subgrid.")
        zf, mf = terrain.load_dem(cfg["dem"], rf, cfg.get("aoi"), cobertura_minima=0.999)
        if not np.isfinite(zf).all():
            raise ValueError("El solver subgrid exige MDT fino sin huecos en el dominio.")
        nyc, nxc = zf.shape[0] // m, zf.shape[1] // m
        zf = zf[:nyc * m, :nxc * m]
        modelo_sg = SG.construir(zf, m, rf, cfg.get("cresta", "mean"))
        dem = modelo_sg["zs"].mean(axis=-1)                       # cota media de celda (solo para diagnóstico y mapas)
        t0_ = mf["transform"]
        meta = dict(mf, height=nyc, width=nxc, transform=Affine(res, 0, t0_.c, 0, -res, t0_.f))
    else:
        dem, meta = terrain.load_dem(cfg["dem"], res, cfg.get("aoi"))
    relleno_dep = prof_relleno = None
    if cfg.get("fill_sinks", False):                              # Epsilon E1.2: opción DECLARADA, nunca por defecto
        if modelo_sg is not None:
            raise ValueError("El relleno de depresiones solo está disponible con el solver de malla.")
        dem, relleno_dep, prof_relleno = rellenar_depresiones(dem, meta["transform"].a * abs(meta["transform"].e), cfg.get("fill_sinks_max_m") or None)
    active = np.isfinite(dem)
    # Celdas sin dato temático: solo se rellenan si la configuración lo declara (valor y motivo quedan en el resumen).
    rel = cfg.get("relleno_declarado")          # {"cn": 85, "manning": 0.06, "motivo": "..."}
    cmin = 0.0 if rel else 0.95
    relleno = {}
    if cfg.get("cn_tif"):
        cn = terrain.match_raster(cfg["cn_tif"], meta, dem.shape, cobertura_minima=cmin)
        sin = ~np.isfinite(cn) | (cn <= 0) | (cn > 100)
        relleno["cn_pct_celdas_rellenadas"] = float(sin[active].mean() * 100)
        cn = np.where(sin, (rel or {}).get("cn", cfg.get("cn_default", 85.)), cn)
        if cfg.get("cn_amc") in ("I", "III"):                                 # G20: CN ráster (AMC II) llevado a AMC I/III (NEH-4; Chow et al. 1988); agua e impermeable (≥ 98) no cambian
            m_ = cn < 98
            cn = np.where(m_, cn / (2.281 - 0.01281 * cn) if cfg["cn_amc"] == "I" else np.minimum(cn / (0.427 + 0.00573 * cn), 99.0), cn)
            relleno["cn_amc"] = cfg["cn_amc"]
    else:
        cn = np.full(dem.shape, cfg.get("cn_default", 85.))
    nm = np.full(dem.shape, float((rel or {}).get("manning", cfg.get("manning_default", .06))))
    if cfg.get("manning_tif"):     # Manning ya calculado por celda (mismas fuentes declaradas en su manifiesto)
        nm = terrain.match_raster(cfg["manning_tif"], meta, dem.shape, cobertura_minima=cmin)
        relleno["manning_pct_celdas_rellenadas"] = float((~np.isfinite(nm))[active].mean() * 100)
        nm = np.where(np.isfinite(nm) & (nm > 0), nm, float((rel or {}).get("manning", cfg.get("manning_default", .06))))
    elif cfg.get("cobertura_tif"):
        cob = terrain.match_raster(cfg["cobertura_tif"], meta, dem.shape, cobertura_minima=cmin)
        relleno["manning_pct_celdas_rellenadas"] = float((~np.isfinite(cob))[active].mean() * 100)
        for k, v in NMAP.items():
            nm[cob == k] = v
    if rel:
        relleno["declaracion"] = rel
    if ev:
        idf, idf_info = None, {"fuente": "evento observado"}
    elif cfg.get("idf_inamhi"):
        q = cfg["idf_inamhi"]
        if "estacion" in q and "lat" not in q:
            idf, idf_info = inamhi.idf_estacion(q["estacion"]), {"fuente": "INAMHI libro de intensidades", "estacion_ref": q["estacion"]}
        else:
            idf, idf_info = inamhi.idf_sitio(q["lat"], q["lon"], estacion=q.get("estacion"))
    else:
        idf, idf_info = idfm.load_idf(cfg["idf_csv"]), {"fuente": "CSV externo " + cfg["idf_csv"]}
    dur = int(cfg.get("storm_min", 180))
    if ev:
        edges, blocks, info_ev = evm.cargar_evento(ev, float(ev.get("bloque_min", 5)))
        idf_info = dict(info_ev)
        fx_ = ev.get("forzamiento_externo")                              # Lambda: un pronóstico o una estimación satelital no se rotula «evento observado»
        if fx_:
            idf_info["fuente"] = ("PRONÓSTICO " if fx_.get("tipo") == "pronostico" else "ESTIMACIÓN SATELITAL ") + str(fx_.get("nombre", "")) + ": " + str(idf_info["fuente"]).replace("evento observado: ", "")
        dur = int(round(edges[-1] / 60.0))
    else:
        edges, blocks = idfm.design_storm(idf, tr, dur, 1.0)
    ia_ratio = float(cfg.get("ia_ratio", 0.2))          # λ = Ia/S: va junto con el CN (un CN calibrado con λ 0,05 no vale con λ 0,20)
    if not 0.0 < ia_ratio <= 0.6:                       # Zeta Z6: hasta 0,6 para usar calibraciones externas tal cual (p. ej., HEC-HMS con Ia explícita: Ia/S = 0,55)
        raise ValueError("ia_ratio (λ) debe estar en (0, 0.6].")
    cum = np.array([excess_scs(p, np.where(active, cn, 80), ia_ratio) for p in np.r_[0, np.cumsum(blocks)]])
    runoff = np.diff(cum, axis=0); runoff[:, ~active] = 0
    dx, dy = meta["transform"].a, abs(meta["transform"].e)

    ext = [h for h in (_hidrograma_externo(c, idf, tr, dur, meta, active, dem.shape) for c in cfg.get("cuencas_externas", [])) if h]
    kw = {}
    sim_s = float(cfg.get("sim_horas", 6)) * 3600
    if ev and sim_s < float(edges[-1]):
        raise ValueError(f"sim_horas ({sim_s/3600:g} h) es menor que la duración del evento ({edges[-1]/3600:.1f} h): la simulación debe cubrir todo el evento.")
    for i in range(len(ext)):
        for j in range(i + 1, len(ext)):
            ov = ext[i]["geometria_externa"].intersection(ext[j]["geometria_externa"]).area
            if ov > 1.0:
                raise ValueError(f"Las áreas externas de {ext[i]['nombre']} y {ext[j]['nombre']} se solapan {ov:.0f} m2: "
                                 "se duplicaría el aporte. Usar áreas incrementales (sin solape).")
    if len({tuple(h["celda"]) for h in ext}) != len(ext):
        raise ValueError("Dos cuencas externas comparten la misma celda de entrada; definir entradas distintas.")
    # Cada cuenca externa entra por SU celda con SU hidrograma (nunca se suman ni se reparten entre entradas).
    inlets = [{"nombre": h["nombre"], "t": h["t"], "q": h["q"], "celdas": [list(h["celda"])]} for h in ext]
    entradas_csv = []                                                 # Epsilon E1.1: hidrogramas de entrada (p. ej. caudal de aguas arriba de un área de detalle)
    for k_, e_ in enumerate(cfg.get("entradas_hidrograma", [])):
        t_, q_ = leer_hidrograma_entrada(e_); rc_ = _celda_de_xy(e_["xy"], meta, active); nom_ = str(e_.get("nombre") or f"hidrograma_{k_ + 1}")
        inlets.append({"nombre": nom_, "t": t_, "q": q_, "celdas": [list(rc_)]})
        entradas_csv.append({"nombre": nom_, "celda": list(rc_), "xy": [float(v) for v in e_["xy"]], "pico_m3s": float(q_.max()),
                             "volumen_m3": float((np.trapezoid if hasattr(np, "trapezoid") else np.trapz)(q_, t_)), "fuente": e_.get("csv") or "lista"})
    entradas_geo = []                                                 # Lambda 9.2: ríos grandes sin datos de caudal → GEOGLOWS v2 (pico Gumbel del Tr de esta corrida)
    if cfg.get("entradas_geoglows"):
        from . import entradas_geoglows as EG
        t_pico_tormenta = float(edges[int(np.argmax(blocks))] + edges[int(np.argmax(blocks)) + 1]) / 2.0
        sim_geo = float(cfg.get("sim_horas", 6)) * 3600
        for k_, e_ in enumerate(cfg["entradas_geoglows"]):
            t_, q_, inf_ = EG.hidrograma(e_, None if ev else tr, t_pico_tormenta, sim_geo)
            rc_ = _celda_de_xy(e_["xy"], meta, active); nom_ = str(e_.get("nombre") or f"geoglows_{k_ + 1}")
            inlets.append({"nombre": nom_, "t": t_, "q": q_, "celdas": [list(rc_)]})
            entradas_geo.append({**inf_, "nombre": nom_, "celda": list(rc_), "xy": [float(v) for v in e_["xy"]]})
            progress(f"Entrada GEOGLOWS {nom_}: pico {inf_['pico_m3s']} m3/s (Tr {tr}, Gumbel de {inf_['n_anios_gumbel']} años" + (", EXTRAPOLADO" if inf_["extrapolado"] else "") + f") a las {inf_['t_pico_h']} h")
    sim_s = float(cfg.get("sim_horas", 6)) * 3600
    if inlets:
        sim_s = max(sim_s, max(float(h["t"][-1]) for h in inlets) + 300.0)   # cubrir la cola completa de cada hidrograma
    kw = dict(inlets=inlets) if inlets else {}
    sal = None                                                        # Epsilon E1.4: sección en la salida → hidrograma 2D
    if cfg.get("salida_xy") and modelo_sg is None:
        rc_s = _celda_de_xy(cfg["salida_xy"], meta, active); ax_, idx_, rango_, signo_ = seccion_salida(dem, active, rc_s, int(cfg.get("seccion_semiancho_celdas", 5)))
        sal = {"celda": list(rc_s), "eje": ax_, "indice_cara": int(idx_), "rango": [int(rango_[0]), int(rango_[1])], "signo": signo_}
        kw["sections"] = {"salida": (ax_, int(idx_), (int(rango_[0]), int(rango_[1])))}
    diag_entradas = diagnostico_entradas(dem, active, [h["celda"] for h in ext], dx) if ext else []
    for h, d in zip(ext, diag_entradas):
        if not d["en_cauce"]:
            msg = f"Entrada '{h['nombre']}' {d['celda']}: " + "; ".join(d["advertencias"])
            if cfg.get("exigir_entrada_en_cauce", True):
                raise ValueError(msg + " (desactivar con exigir_entrada_en_cauce=false bajo responsabilidad del usuario)")
            progress("AVISO " + msg)
    bordes = None; bordes_info = None                                  # G22: el borde junto a cada entrada se cierra (no devuelve al exterior el agua que entra)
    R_ = int(cfg.get("borde_cerrado_entradas_celdas", 10))
    if inlets and R_ > 0 and cfg.get("boundary", "free_outflow") == "free_outflow":
        ny_, nx_ = dem.shape; lo_, le_, ln_, ls_ = (np.ones(ny_, bool), np.ones(ny_, bool), np.ones(nx_, bool), np.ones(nx_, bool))
        for h_ in inlets:
            for rr_, cc_ in h_["celdas"]:
                if cc_ <= R_: lo_[max(rr_ - R_, 0):rr_ + R_ + 1] = False
                if nx_ - 1 - cc_ <= R_: le_[max(rr_ - R_, 0):rr_ + R_ + 1] = False
                if rr_ <= R_: ln_[max(cc_ - R_, 0):cc_ + R_ + 1] = False
                if ny_ - 1 - rr_ <= R_: ls_[max(cc_ - R_, 0):cc_ + R_ + 1] = False
        bordes = (lo_, le_, ln_, ls_)
        bordes_info = {"radio_celdas": R_, "celdas_de_borde_cerradas": {"oeste": int((~lo_).sum()), "este": int((~le_).sum()), "norte": int((~ln_).sum()), "sur": int((~ls_).sum())},
                       "nota": "Borde cerrado a ≤ R celdas de cada hidrograma de entrada (como una línea de condición de entrada); el resto del borde es salida libre."}
    t0 = time.time()
    esc_info = cfg.get("escenario_info") or {}                          # Eta: la etiqueta dice el escenario real (Y CMIP6), no «diseno_idf_historica»
    etq = (ETIQUETA + " Tr" + str(tr)) if not esc_info.get("id") else (str(esc_info["id"]) + " Tr" + str(tr))
    if modelo_sg is None:                                               # Eta (Mejora 1): punto de control para reanudar tras un corte
        kw["checkpoint"] = str(out / "punto_control.npz"); kw["checkpoint_every_s"] = float(cfg.get("punto_control_min", 10)) * 60
        kw["resume"] = bool(cfg.get("_reanudar")); kw["on_checkpoint"] = lambda m_: progress(f"PUNTO DE CONTROL guardado al {int(m_['progreso']*100)} % ({m_['step']} pasos): si se corta, la corrida se puede reanudar desde aquí.")
        r = simulate(dem, active, nm, edges, runoff,
                     Options(dx, dy, sim_s, max_dt=float(cfg.get("max_dt", 5)), cfl=float(cfg.get("cfl", 0.35)),
                             boundary=cfg.get("boundary", "free_outflow"), backend="numba",
                             frame_interval=float(cfg.get("fotos_min", 5)) * 60, bordes_libres=bordes),
                     progress=lambda f, s: progress(f"  {('Evento ' + str(ev.get('id'))) if ev else etq}: {int(f*100)}% ({s} pasos)"), **kw)
    else:
        rs = SG.simular(modelo_sg, nm, edges, runoff,
                        SG.SubgridOptions(sim_s, max_dt=float(cfg.get("max_dt", 5)), cfl=float(cfg.get("cfl", 0.35)),
                                          boundary=cfg.get("boundary", "free_outflow")),
                        entradas=inlets or None, progress=lambda f, s: progress(f"  {('Evento ' + str(ev.get('id'))) if ev else (ETIQUETA + ' Tr' + str(tr))} (subgrid): {int(f*100)}% ({s} pasos)"))
        r = {"hmax": rs["h_medio_max"], "vmax": rs["vmax"], "duracion_h_ge_03m": rs["duracion_h_ge_03m"],
             "hfinal": rs["V_final"] / modelo_sg["area"], "balance": rs["balance"], "resumen": rs["resumen"], "eta_max": rs["eta_max"]}
        r["resumen"]["definicion_calado"] = "calado MEDIO de celda (volumen/área); el nivel máximo por celda está en eta_max.tif"
        r["resumen"]["solver_subgrid"] = {"m": modelo_sg["m"], "rf_m": modelo_sg["rf"], "cresta": cfg.get("cresta", "mean")}
    s = r["resumen"]
    s["entradas_diagnostico"] = diag_entradas
    if entradas_geo:
        s["entradas_geoglows"] = entradas_geo
    fx = (ev or {}).get("forzamiento_externo") or {}
    tipo_ev = "pronostico" if fx.get("tipo") == "pronostico" else ("estimacion_satelital" if fx.get("tipo") == "satelite" else "evento_observado")
    if fx:
        s["forzamiento_externo"] = fx
    s.update(segundos=time.time() - t0, Tr=tr, escenario=(("evento_observado_historico" if tipo_ev == "evento_observado" else tipo_ev + "_" + str(fx.get("modelo", ""))) if ev else ETIQUETA), tipo_forzamiento=(tipo_ev if ev else ("diseno_idf_cmip6" if esc_info.get("tipo") == "cmip6" else "diseno_idf")), factor_cc=float(esc_info.get("factor") or 1.0), escenario_id=esc_info.get("id"), escenario_nombre=esc_info.get("nombre"), P_total_mm=float(blocks.sum()),
             solver=solver, res_m=res, cfl_objetivo=float(cfg.get("cfl", 0.35)), max_dt_s=float(cfg.get("max_dt", 5)), celdas=int(active.sum()), estado_calibracion="no calibrado", aviso=(AVISOS_FORZAMIENTO[tipo_ev] if ev else AVISO), relleno_tematico=relleno,
             ia_ratio=ia_ratio, cn_origen=cfg.get("cn_origen", "ráster" if cfg.get("cn_tif") else "cn_default"), idf_fuente=idf_info["fuente"], idf_info=idf_info,
             cuencas_externas=[{k: h[k] for k in ("nombre", "area_externa_km2", "area_poligono_km2", "volumen_m3", "informe")} for h in ext],
             aporte_por_entrada={h["nombre"]: {"volumen_hidrograma_m3": h["volumen_m3"], "volumen_integrado_m3": r["resumen"]["entradas"][h["nombre"]]["volumen_integrado_m3"]} for h in ext},
             aporte_externo_m3=float(sum(h["volumen_m3"] for h in ext)))
    for d in (.05, .3, .5, 1.):
        s[f"area_ge_{d}_km2"] = float((active & (r["hmax"] >= d)).sum() * dx * dy / 1e6)
    if relleno_dep is not None:
        s["relleno_depresiones"] = relleno_dep; _write(out / "relleno_depresiones_m.tif", prof_relleno, active, meta)
    if entradas_csv:
        s["entradas_hidrograma"] = entradas_csv
        if bordes_info: s["bordes_cerrados_entradas"] = bordes_info
    va, mva = velocidades_anomalas(r["vmax"], r["hmax"], active, meta, float(cfg.get("v_anomala_ms", 10.0)))     # Epsilon E1.3
    s["velocidad_anomala"] = va; _write(out / "v_anomala.tif", mva.astype("float32"), active, meta)
    if sal is not None and "secciones" in r and "salida" in r["secciones"]:
        sec = r["secciones"]["salida"]; tq = pd.DataFrame({"t_s": sec["t_s"], "Q_2d_m3s": np.asarray(sec["Q_m3s"], float) * sal["signo"]})
        hc = cfg.get("hidro_comparar")
        if hc and not ev:
            th, qh = hidrograma_hu_scs(edges, blocks, hc["CN"], hc["lambda"], hc["lag_h"], hc["PRF"], hc["area_km2"])
            tq["Q_hidro_m3s"] = np.interp(tq["t_s"], np.r_[0, th], np.r_[0, qh], right=0.0)
            sal["hidro"] = {k: hc[k] for k in ("CN", "lambda", "lag_h", "PRF", "area_km2")}
            sal["hidro_pico_m3s"] = float(qh.max()); sal["hidro_t_pico_h"] = float(th[int(np.argmax(qh))] / 3600)
            sal["hidro_volumen_m3"] = float(qh.sum() * (edges[1] - edges[0]))
        tq.to_csv(out / "hidrograma_salida_2d.csv", index=False)
        sal["pico_2d_m3s"] = float(tq["Q_2d_m3s"].max()); sal["t_pico_2d_h"] = float(tq["t_s"].iloc[int(tq["Q_2d_m3s"].values.argmax())] / 3600)
        sal["volumen_2d_m3"] = float(sec["volumen_m3"] * sal["signo"])
        sal["nota"] = ("Caudal 2D a través de una sección de " + str(sal["rango"][1] - sal["rango"][0]) + " celdas en la salida (muestreo cada 5 min). "
                       "Hidro = modelo de eventos con los parámetros aceptados para la MISMA tormenta; diferencias esperables: la 2D incluye almacenamiento en depresiones y tránsito sobre el terreno.")
        s["hidrograma_salida"] = sal
        try:
            import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(9, 4.2), dpi=130)
            ax.plot(tq["t_s"] / 3600, tq["Q_2d_m3s"], color="#1f63c6", lw=2.2, label="2D (sección en la salida)")
            if "Q_hidro_m3s" in tq:
                ax.plot(tq["t_s"] / 3600, tq["Q_hidro_m3s"], color="#c0182a", lw=1.8, ls="--", label="hidro (SCS-CN + HU, parámetros aceptados)")
            ax.set_xlabel("tiempo (h)"); ax.set_ylabel("caudal (m³/s)"); ax.grid(alpha=0.3); ax.legend()
            ax.set_title("Hidrograma en la salida · " + ("evento observado" if ev else f"diseño Tr {tr}") + ", no calibrado ni validado"); fig.tight_layout(); fig.savefig(out / "hidrograma_salida.png"); plt.close(fig)
        except Exception:
            pass
    for k in ("hmax", "vmax", "duracion_h_ge_03m") + (("eta_max",) if "eta_max" in r else ()):
        _write(out / f"{k}.tif", r[k], active, meta)
    _guardar_fotos(out / "evolucion_calado.npz", r.get("fotos"), r["hmax"], active, dx * dy)
    pd.DataFrame(r["balance"]).to_csv(out / "balance_agua.csv", index=False)
    pd.DataFrame({"inicio_s": edges[:-1], "fin_s": edges[1:], "lluvia_mm": blocks}).to_csv(out / "hietograma.csv", index=False)
    mask = (active & (r["hmax"] >= .3)).astype("uint8")
    polys = [shape(g) for g, v in features.shapes(mask, mask=mask == 1, transform=meta["transform"]) if v == 1]
    if polys:
        gpd.GeoDataFrame({"umbral_m": [.3]}, geometry=[unary_union(polys)], crs=meta["crs"]).to_file(out / "inundacion_ge_03m.gpkg", driver="GPKG")
    evaluacion = evaluar_numerica(s, r["balance"])
    (out / "evaluacion_numerica.json").write_text(json.dumps(evaluacion, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    s["evaluacion_numerica_archivo"] = "evaluacion_numerica.json"
    s["capacidad_canales_estado"] = "no_evaluada"
    (out / "resumen.json").write_text(json.dumps(s, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    (out / "procedencia.json").write_text(json.dumps({"config": cfg, "entradas": prov, "idf": idf_info,
                                                      "dem": {"cobertura": meta.get("cobertura_dem"), "aviso": meta.get("aviso")}},
                                                     indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return s
