# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Proyecto nuevo desde un sitio (lon, lat): el programa crea el proyecto, lanza las descargas (MDT, CHIRPS, GEOGLOWS, opcional CELEC) y al terminar registra el MDT.
La persona solo necesita una cuenta de Earth Engine autorizada. Nada sobrescribe: cada proyecto y cada descarga van en carpetas nuevas."""
import json, os, re, subprocess, sys
from datetime import datetime
from pathlib import Path

from . import proyecto as P
from .. import descargas as D, terreno_import as TIMP

RAIZ_PROYECTOS = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "UCEclima_proyectos"
CONFIG_USUARIO = Path.home() / ".uceclima" / "config.json"


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"[áàä]", "a", re.sub(r"[éèë]", "e", re.sub(r"[íìï]", "i", re.sub(r"[óòö]", "o", re.sub(r"[úùü]", "u", t.lower().replace("ñ", "n"))))))).strip("_") or "proyecto"


def en_ecuador(lon, lat):
    return -92 <= lon <= -74 and -6 <= lat <= 2


def zona_desde_shape(ruta, crs_si_falta=None):
    """Zeta Z3: lee el shape (o GeoPackage/GeoJSON/KML) de la zona de estudio y devuelve el punto (dentro del polígono), la extensión y el área.
    No adivina el CRS: si el archivo no lo declara, hay que indicarlo."""
    import geopandas as gpd
    ruta = Path(str(ruta or "").strip().strip('"'))
    if not ruta.exists():
        raise D.DescargaError(f"No existe el archivo de la zona de estudio: {ruta}")
    try:
        g = gpd.read_file(ruta)
    except Exception as e:
        raise D.DescargaError(f"No pude leer la zona de estudio: {str(e)[:200]}")
    if g.crs is None:
        if not crs_si_falta:
            raise D.DescargaError("La zona de estudio no declara sistema de coordenadas (falta el .prj). Indica el CRS (p. ej. EPSG:32630 o EPSG:4326); no lo adivino.")
        g = g.set_crs(crs_si_falta)
    g = g[g.geometry.notna() & g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if g.empty:
        raise D.DescargaError("La zona de estudio no tiene polígonos (¿son líneas o puntos?).")
    geo = g.to_crs(4326).geometry.make_valid()
    u = geo.union_all() if hasattr(geo, "union_all") else geo.unary_union
    pt = u.representative_point(); lon, lat = float(pt.x), float(pt.y)
    utm = gpd.GeoSeries([u], crs=4326).to_crs(D.utm_epsg(lon, lat)).iloc[0]
    x0, y0, x1, y1 = utm.bounds
    return {"lon": round(lon, 6), "lat": round(lat, 6), "area_km2": round(utm.area / 1e6, 3), "medio_km": round(max(x1 - x0, y1 - y0) / 2000 + 2, 1),
            "bbox_lonlat": [round(v, 6) for v in u.bounds], "n_poligonos": int(len(g)), "archivo": str(ruta)}


def copiar_zona(carpeta, ruta):
    """Copia el shape (con .prj, .dbf, .shx, …) a <proyecto>/zona_estudio/ y devuelve la ruta de la copia."""
    import shutil
    ruta = Path(str(ruta).strip().strip('"')); dst = Path(carpeta) / "zona_estudio"; dst.mkdir(parents=True, exist_ok=True)
    for f in ruta.parent.glob(ruta.stem + ".*"):
        shutil.copy2(f, dst / f.name)
    return dst / ruta.name


def crear(nombre, lon, lat, base=None, shape=None, crs_shape=None):
    nombre = (nombre or "").strip()
    if len(nombre) < 3:
        raise D.DescargaError("Dale un nombre de al menos 3 letras al proyecto.")
    zona = zona_desde_shape(shape, crs_shape) if shape else None
    if zona and (lon in (None, "") or lat in (None, "")):
        lon, lat = zona["lon"], zona["lat"]
    try:
        num = lambda v: float(str(v).strip().replace(",", ".").replace("\u2212", "-").replace("\u2013", "-").replace(" ", ""))      # 8.0.1: menos tipográfico (− –) copiado de un texto
        lon, lat = num(lon), num(lat)
    except (TypeError, ValueError):
        raise D.DescargaError("Escribe la longitud y la latitud del sitio en grados decimales (por ejemplo -78.645 y -2.585).")
    if not D.punto_admitido(lon, lat):
        raise D.DescargaError(D.MENSAJE_FUERA)
    from ..proyecto_sitio import carpeta_con_sufijo
    carpeta = Path(base or RAIZ_PROYECTOS) / carpeta_con_sufijo(_slug(nombre))                    # R3: carpetas de proyecto terminan en «ucec»
    if carpeta.exists():
        raise D.DescargaError(f"Ya existe un proyecto «{nombre}» en {carpeta}. Ábrelo o usa otro nombre.")
    carpeta.mkdir(parents=True)
    epsg = D.utm_epsg(lon, lat)
    cfg = {"out_dir": "resultados/_no_usado", "res": 30, "boundary": "free_outflow", "escenarios": ["diseno_idf_historica"], "Tr": 100, "storm_min": 180, "sim_horas": 6}
    notas = ["Sin CN ni Manning: no se simula hasta declararlos con su fuente."]
    if en_ecuador(lon, lat):
        cfg.update({"idf_inamhi": {"lat": lat, "lon": lon}, "idf_x": {"lat": lat, "lon": lon, "estacion": None, "modo": "auto", "fuente": "INAMHI libro de intensidades (automático: confírmalo en el módulo IDF)"}})
    else:                                                                         # Zeta: la IDF del INAMHI solo vale en Ecuador
        notas.append("Sitio fuera de Ecuador: la IDF del INAMHI no aplica. En el módulo 4 · IDF: «IDF desde CHIRPS» (por defecto, sin estaciones) o «Registrar IDF propia» (CSV Tr × minutos con su fuente) antes de las tormentas de diseño.")
    (carpeta / "config_climanet.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    proc = {"creado": datetime.now().isoformat(timespec="seconds"), "origen": "uceclima.ui.sitio_api.crear", "punto": [lon, lat], "notas": notas}
    if zona:
        copia = copiar_zona(carpeta, zona["archivo"])
        proc["zona_estudio"] = {**zona, "copia": str(copia.relative_to(carpeta)).replace("\\", "/"), "nota": "El punto es interior al polígono (representative_point); el área 2D y la cuenca activa salen del shape."}
    P.guardar({"version_esquema": 1, "nombre": nombre, "tipo": "real", "ubicacion": f"lon {lon:.4f}, lat {lat:.4f}",
               "descripcion": "Proyecto creado desde " + ("un shape de zona de estudio" if zona else "un sitio") + ": datos descargados automáticamente; faltan CN, Manning y cuenca para modelar.",
               "crs": f"EPSG:{epsg}", "datum_vertical": "no verificado", "tipo_terreno": "desconocido", "unidades": {"longitud": "m", "lluvia": "mm", "caudal": "m3/s"}, "carpeta_resultados": "resultados",
               "config_climanet": "config_climanet.json", "procedencia": proc}, carpeta)
    try:
        from .. import estaciones_ref
        (carpeta / "registro").mkdir(exist_ok=True)
        (carpeta / "registro" / "estaciones_referencia.json").write_text(json.dumps(estaciones_ref.cercanas(lat, lon), ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return carpeta


def registrar_mdt_en(estado, destino, p):
    """Registra el MDT descargado en `destino/mdt` como terreno del proyecto abierto (DSM, datum declarado, área ≤ tope del modelo)."""
    tif = next((Path(destino) / "mdt").glob("*.tif"), None) or next(Path(destino).glob("*.tif"), None)     # descarga «sitio» (subcarpeta mdt/) o botón suelto «MDT»
    if tif is None:
        raise D.DescargaError("No se encontró el MDT descargado.")
    centro = None
    try:
        from pyproj import Transformer
        centro = Transformer.from_crs("EPSG:4326", estado.datos["crs"], always_xy=True).transform(float(p["lon"]), float(p["lat"]))
    except Exception:
        pass
    ins = TIMP.inspeccionar(str(tif)); res = 30.0
    aoi = TIMP.aoi_sugerida(ins, 30.0, centro=centro, lado_m=min(10000.0, ins["ancho_m"], ins["alto_m"]))
    if p.get("ambito") == "cuenca":
        try:
            from ..cuenca import extension_activa
            ext = extension_activa(estado.carpeta, estado.datos["crs"], margen_m=500.0)
            if ext:
                e = ins["extension"]; x0, y0, x1, y1 = ext["xy"]
                aoi = [max(x0, e["x0"]), min(x1, e["x1"]), max(y0, e["y0"]), min(y1, e["y1"])]
                import math
                res = max(30.0, math.ceil(math.sqrt((aoi[1] - aoi[0]) * (aoi[3] - aoi[2]) / TIMP.CELDAS_MAX)))   # dentro del tope de celdas
        except Exception:
            pass
    if "fabdem" in tif.name.lower():                                                 # Omega O1: suelo desnudo estimado
        TIMP.registrar(estado, str(tif), "MDT", "EGM2008 (FABDEM, derivado de Copernicus GLO-30); no verificado localmente", res, aoi)
    else:
        TIMP.registrar(estado, str(tif), "DSM", "EGM2008 (Copernicus GLO-30); no verificado localmente", res, aoi)


def registrar_mdt(estado):
    """Versión para una descarga suelta del MDT (se ejecuta al terminar)."""
    def hacer(destino, man):
        if ((man.get("pasos") or {}).get("mdt") or {}).get("estado") == "ok" or man.get("fuente_id") == "mdt":
            registrar_mdt_en(estado, destino, man["parametros"])
    return hacer


def registrar_mdt_descargado(estado):
    """Si el proyecto abierto aún no tiene MDT registrado, registra el último MDT descargado COMPLETO de su carpeta (botón «MDT» o «sitio»).
    Devuelve la carpeta usada o None si no hay ninguno. No reemplaza un MDT ya registrado."""
    _, cfg = estado.cfg()
    if cfg.get("dem") and cfg.get("aoi"):
        return None
    for d in sorted((Path(estado.carpeta) / "datos_descargados").glob("*"), reverse=True):
        if not (d.name.startswith("mdt_2") or d.name.startswith("sitio_")):
            continue
        est = d / "estado.json"
        if not est.exists() or json.loads(est.read_text(encoding="utf-8")).get("estado") != "completado":
            continue
        tif = next((d / "mdt").glob("*.tif"), None) or next(d.glob("*.tif"), None)
        if tif is None:
            continue
        man = d / "manifiesto.json"
        par = (json.loads(man.read_text(encoding="utf-8")).get("parametros") or {}) if man.exists() else {}
        if "lon" not in par:
            m = re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(estado.datos.get("ubicacion", "")))
            par = {"lon": float(m.group(1)), "lat": float(m.group(2))} if m else {}
        registrar_mdt_en(estado, d, par)
        return d.name
    return None


def autorizar_ee():
    """Abre el flujo de autorización de Earth Engine en el navegador (la persona inicia sesión con SU cuenta; el programa no ve ni guarda credenciales)."""
    cmd = [sys.executable, "--ee-auth"] if getattr(sys, "frozen", False) else [sys.executable, "-c", "import ee; ee.Authenticate()"]
    subprocess.Popen(cmd, creationflags=0x08000000 if os.name == "nt" else 0)
    return {"mensaje": "Se abrió el navegador para autorizar Earth Engine con tu cuenta de Google. Al terminar, vuelve aquí y pulsa «Probar conexión»."}


def guardar_proyecto_gee(pid):
    pid = (pid or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9\-]{4,28}[a-z0-9]", pid):
        raise D.DescargaError("El ID de proyecto de Google Cloud no parece válido (ej.: mi-proyecto-123).")
    CONFIG_USUARIO.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG_USUARIO.read_text(encoding="utf-8")) if CONFIG_USUARIO.exists() else {}
    cfg["gee_project"] = pid
    CONFIG_USUARIO.write_text(json.dumps(cfg), encoding="utf-8")
    return {"gee_project": pid}
