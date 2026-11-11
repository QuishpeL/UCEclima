# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Módulo 2 — Google Earth Engine y CHIRPS. Sin credenciales en el repositorio; con caché local; sin descargas masivas.

Flujo: iniciar() -> disponibilidad() -> eventos.elegir_producto() (una sola versión, con fallback explícito) -> serie_por_cuenca() -> ventanas().
Convenciones: CHIRPS es diario en UTC (system:index = AAAAMMDD); el día local de Guayaquil (UTC-5) no coincide exactamente. Las ausencias son NaN, nunca 0.
Producto preferido: UCSB-CHC/CHIRPS/V3/DAILY_SAT (diario derivado de pentadas con IMERG; NO es pluviómetro subdiario). Fallback: UCSB-CHG/CHIRPS/DAILY (v2) solo si cubre toda la ventana.
"""
import hashlib, json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd

from .eventos import PRODUCTOS, elegir_producto

CACHE = Path(__file__).resolve().parent / "cache" / "chirps"
CONFIG_USUARIO = Path.home() / ".uceclima" / "config.json"      # FUERA del repositorio: aquí se guarda solo el ID del proyecto, nunca tokens
MAX_DIAS = 120
MAX_FEATURES = 4000                                              # días × cuencas por consulta: evita descargas masivas por accidente


def _proyecto(proyecto=None):
    if proyecto: return proyecto
    if CONFIG_USUARIO.exists():                                  # Zeta: manda el ID escrito por la persona en UCEclima
        try:
            p = json.loads(CONFIG_USUARIO.read_text(encoding="utf-8")).get("gee_project")
            if p: return p
        except Exception:
            pass
    for k in ("UCECLIMA_GEE_PROJECT", "EARTHENGINE_PROJECT", "GOOGLE_CLOUD_PROJECT"):
        if os.environ.get(k): return os.environ[k]
    return None


_SESION = {"proyecto": None, "t": 0.0, "estado": None, "ee": None}           # Zeta Z2: una sola inicialización por sesión (antes, cada descarga repetía ee.Initialize)
SESION_SEG = 45 * 60                                                          # se renueva a los 45 min (los tokens de Google duran ~60 min)


def olvidar_sesion():
    """Fuerza a reinicializar Earth Engine en la siguiente llamada (p. ej., tras cambiar de proyecto de Google Cloud o re-autorizar)."""
    _SESION.update({"proyecto": None, "t": 0.0, "estado": None, "ee": None})


def iniciar(proyecto=None, ee_module=None, forzar=False):
    """Inicializa Earth Engine con las credenciales YA autorizadas del usuario (no las lee ni las copia). Devuelve el estado.
    Para autorizar por primera vez: `earthengine authenticate` (navegador) y, si procede, guardar el ID de proyecto en ~/.uceclima/config.json.
    Zeta: reutiliza la sesión ya inicializada (mismo proyecto, < 45 min) en vez de repetir ee.Initialize en cada descarga."""
    import time as _t
    pid = _proyecto(proyecto)
    if (ee_module is None and not forzar and _SESION["ee"] is not None and _SESION["proyecto"] == pid and _t.time() - _SESION["t"] < SESION_SEG):
        return dict(_SESION["estado"], reutilizada=True), _SESION["ee"]
    estado = {"autenticado": False, "proyecto": pid, "api": None, "error": None, "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    estado, ee = _iniciar(estado, ee_module)
    if ee is not None and ee_module is None:
        _SESION.update({"proyecto": pid, "t": _t.time(), "estado": estado, "ee": ee})
    return estado, ee


def _iniciar(estado, ee_module):
    try:
        ee = ee_module
        if ee is None:
            import ee
        estado["api"] = getattr(ee, "__version__", None)
        (ee.Initialize(project=estado["proyecto"]) if estado["proyecto"] else ee.Initialize())
        try:                                                     # sin plazo, una llamada a Earth Engine puede esperar para siempre con una red lenta
            ee.data.setDeadline(180000)
        except Exception:
            pass
        estado["autenticado"] = True
    except Exception as e:                                       # pragma: no cover - depende del entorno del usuario
        estado["error"] = str(e)[:300]
    return estado, (ee if estado["autenticado"] else None)


def _dias(a, b):
    a, b = datetime.fromisoformat(a), datetime.fromisoformat(b); out = []
    while a < b:
        out.append(a.date().isoformat()); a += timedelta(days=1)
    return out


def disponibilidad(plan, ee):
    """Fechas UTC con imagen en cada producto dentro de la ventana de consulta. Solo metadatos (sin descargar píxeles)."""
    a, b = plan["consulta_total"]
    d0, d1 = a[:10], b[:10]
    disp = {}
    for version, coleccion in PRODUCTOS:
        try:
            ids = ee.ImageCollection(coleccion).filterDate(d0, d1).aggregate_array("system:index").getInfo()
            disp[version] = sorted(f"{i[:4]}-{i[4:6]}-{i[6:8]}" for i in ids)
        except Exception as e:                                   # producto no consultable: queda como sin cobertura, no se inventa
            disp[version] = []; disp.setdefault("_errores", {})[version] = str(e)[:200]
    return disp


def seleccionar(plan, disp):
    """Reutiliza eventos.elegir_producto: una sola versión con cobertura completa o 'sin producto completo'."""
    sel = elegir_producto(plan, {k: v for k, v in disp.items() if not k.startswith("_")})
    sel["errores_consulta"] = disp.get("_errores", {})
    return sel


def _cuencas_wgs84(gdf, campo):
    g = gdf.to_crs(4326)
    return g[[campo, "geometry"]]


def serie_por_cuenca(sel, plan, cuencas, ee, campo="nombre", cache=None):
    """Media diaria por cuenca (mm/día) del producto elegido. `cuencas`: GeoDataFrame con CRS válido y geometrías válidas. Devuelve (DataFrame, ruta de caché)."""
    if not sel.get("cobertura_completa"):
        raise RuntimeError("Sin producto con cobertura completa: no se descarga ni se mezclan versiones.")
    dias = _dias(*plan["consulta_total"])
    if len(dias) > MAX_DIAS or len(dias) * len(cuencas) > MAX_FEATURES:
        raise ValueError(f"Consulta demasiado grande ({len(dias)} días × {len(cuencas)} cuencas); el límite evita descargas masivas.")
    g = _cuencas_wgs84(cuencas, campo)
    clave = hashlib.sha256(json.dumps([sel["coleccion"], plan["consulta_total"], sorted(g[campo].astype(str)),
                                       [x.wkb_hex[:64] for x in g.geometry]], sort_keys=True).encode()).hexdigest()[:16]
    carpeta = Path(cache) if cache else CACHE / sel["version"] / clave
    csv = carpeta / "serie_diaria_por_cuenca.csv"
    if csv.exists():                                             # caché: no se vuelve a consultar ni se sobrescribe
        return pd.read_csv(csv, parse_dates=["fecha_utc"]), carpeta
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(r.geometry.__geo_interface__), {campo: str(r[campo])}) for _, r in g.iterrows()])
    col = ee.ImageCollection(sel["coleccion"]).filterDate(plan["consulta_total"][0][:10], plan["consulta_total"][1][:10]).select("precipitation")
    red = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)

    def por_dia(img):
        f = img.reduceRegions(collection=fc, reducer=red, scale=5566, crs="EPSG:4326")
        return f.map(lambda x: x.set("fecha", img.get("system:index")))
    info = col.map(por_dia).flatten().getInfo()
    filas = []
    for f in info["features"]:
        p = f["properties"]; i = p["fecha"]
        filas.append({"fecha_utc": f"{i[:4]}-{i[4:6]}-{i[6:8]}", campo: p[campo], "mm": p.get("mean"), "n_pixeles": p.get("count")})
    df = pd.DataFrame(filas)
    df["fecha_utc"] = pd.to_datetime(df["fecha_utc"])
    esperado = pd.MultiIndex.from_product([pd.to_datetime(dias), g[campo].astype(str)], names=["fecha_utc", campo])
    df = df.set_index(["fecha_utc", campo]).reindex(esperado).reset_index()                  # los días sin dato quedan NaN
    carpeta.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv, index=False)
    manifiesto = {"producto": sel["version"], "coleccion": sel["coleccion"], "fallback": sel.get("fallback"), "consulta_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "ventana_consulta": plan["consulta_total"], "dias": len(dias), "cuencas": int(len(g)), "campo": campo, "dias_con_dato": int(df.mm.notna().groupby(df.fecha_utc).any().sum()),
                  "dias_sin_dato": int((~df.mm.notna().groupby(df.fecha_utc).any()).sum()), "unidades": "mm/día (UTC)", "reductor": "media ponderada por fracción de píxel, escala 5566 m, EPSG:4326",
                  "api_ee": getattr(ee, "__version__", None), "diagnostico_cobertura": sel.get("diagnostico"), "advertencia": plan.get("advertencia"),
                  "no_es": "pluviómetro ni lluvia subdiaria; los días UTC no coinciden exactamente con el día local (UTC-5)"}
    (carpeta / "manifiesto.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return df, carpeta


def ventanas(df, plan, campo="nombre"):
    """Acumulados por cuenca para evento, ±5 y ±21 días. Ventanas anidadas (antes_21d incluye antes_5d) y complementarias (antes_6a21d) sin solape accidental.
    Un acumulado con algún día sin dato es NaN (no se subestima en silencio)."""
    w = plan["ventanas"]; d = df.copy(); d["fecha_utc"] = pd.to_datetime(d["fecha_utc"])
    def rango(a, b): return (d.fecha_utc >= pd.Timestamp(a[:10])) & (d.fecha_utc < pd.Timestamp(b[:10]))
    ev0, ev1 = w["evento_dias_utc"]
    defin = {"evento": (ev0, ev1)}
    for n in (5, 21):
        defin[f"antes_{n}d"] = tuple(w[f"antes_{n}d"]); defin[f"despues_{n}d"] = tuple(w[f"despues_{n}d"])
    defin["antes_6a21d"] = (w["antes_21d"][0], w["antes_5d"][0]); defin["despues_6a21d"] = (w["despues_5d"][1], w["despues_21d"][1])
    filas = []
    for nombre, (a, b) in defin.items():
        sub = d[rango(a, b)]
        for c, s in sub.groupby(campo):
            nd = (pd.Timestamp(b[:10]) - pd.Timestamp(a[:10])).days
            filas.append({"ventana": nombre, campo: c, "inicio_utc": a[:10], "fin_utc_exclusivo": b[:10], "dias_esperados": nd, "dias_con_dato": int(s.mm.notna().sum()),
                          "acumulado_mm": float(s.mm.sum()) if s.mm.notna().all() and len(s) == nd else np.nan})
    return pd.DataFrame(filas)
