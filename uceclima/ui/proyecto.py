# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Modelo de proyecto de UCEclima (interfaz): abrir, validar con esquema, guardar sin sobrescribir y verificar entradas.
Separa la interfaz del cálculo: aquí solo se leen/validan archivos; la simulación la hace el núcleo CLIMANET en un proceso aparte."""
import hashlib, json, math, time
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

ESQUEMA = json.loads((Path(__file__).parent / "esquema_proyecto.json").read_text(encoding="utf-8"))
ARCHIVO = "proyecto_uceclima.json"
RECIENTES = Path.home() / ".uceclima" / "recientes.json"          # solo rutas; nunca credenciales
LIMITE_CELDAS = 250_000                                            # tope de casos «pequeños» desde la interfaz
LIMITE_HORAS = 12.0
K_SEG_POR_CELDA_PASO = 8e-8                                        # medido en la corrida de 105 000 celdas / 33 000 pasos / 274 s (malla)


class ProyectoError(ValueError):
    pass


ARCHIVOS_ANTIGUOS = ("proyecto_" + "climauce" + ".json", "proyecto_" + "ucemi" + ".json")      # nombres que usaron los proyectos de versiones anteriores (ClimaUCE, UCEMI)


def _ruta_proyecto(ruta):
    """Carpeta o archivo de proyecto. Los proyectos de versiones anteriores se abren sin perder nada: se crea al lado proyecto_uceclima.json y el original se conserva."""
    p = Path(ruta)
    if p.is_file() and p.name in ARCHIVOS_ANTIGUOS:
        p = p.parent
    if p.is_dir():
        nuevo = p / ARCHIVO
        if not nuevo.exists():
            for viejo in ARCHIVOS_ANTIGUOS:
                if (p / viejo).exists():
                    import shutil
                    shutil.copy2(p / viejo, nuevo); break
        return nuevo
    return p


def abrir(ruta):
    """Lee y valida el proyecto con el esquema. Devuelve (proyecto, carpeta). Lanza ProyectoError con mensajes legibles."""
    arch = _ruta_proyecto(ruta)
    if not arch.is_file():
        raise ProyectoError(f"No existe el archivo de proyecto: {arch}")
    try:
        datos = json.loads(arch.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProyectoError(f"El proyecto no es un JSON válido: {e}")
    errores = sorted(jsonschema.Draft7Validator(ESQUEMA).iter_errors(datos), key=lambda e: list(e.path))
    if errores:
        raise ProyectoError("Proyecto inválido: " + "; ".join(f"{'/'.join(map(str, e.path)) or 'raíz'}: {e.message}" for e in errores[:6]))
    carpeta = arch.parent
    datos["_carpeta"] = str(carpeta)
    _recordar(str(arch))
    return datos, carpeta


def guardar(datos, carpeta, sobrescribir=False):
    """Escribe proyecto_uceclima.json. Si ya existe, se niega salvo `sobrescribir=True` (se guarda copia .bak con marca de tiempo)."""
    carpeta = Path(carpeta); carpeta.mkdir(parents=True, exist_ok=True)
    arch = carpeta / ARCHIVO
    limpio = {k: v for k, v in datos.items() if not k.startswith("_")}
    errores = list(jsonschema.Draft7Validator(ESQUEMA).iter_errors(limpio))
    if errores:
        raise ProyectoError("No se guarda un proyecto inválido: " + "; ".join(e.message for e in errores[:4]))
    if arch.exists():
        if not sobrescribir:
            raise ProyectoError(f"Ya existe {arch}. Elige otra carpeta o confirma explícitamente la sobrescritura.")
        arch.replace(carpeta / f"{ARCHIVO}.{datetime.now():%Y%m%d_%H%M%S}.bak")
    arch.write_text(json.dumps(limpio, indent=2, ensure_ascii=False), encoding="utf-8")
    return arch


def _recordar(ruta):
    try:
        RECIENTES.parent.mkdir(exist_ok=True)
        lista = json.loads(RECIENTES.read_text(encoding="utf-8")) if RECIENTES.exists() else []
        lista = [ruta] + [r for r in lista if r != ruta]
        RECIENTES.write_text(json.dumps(lista[:8], ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def recientes():
    try:
        import tempfile
        tmp = str(Path(tempfile.gettempdir()).resolve()).lower()
        return [r for r in json.loads(RECIENTES.read_text(encoding="utf-8")) if Path(r).exists() and not str(Path(r).resolve()).lower().startswith(tmp)]   # sin carpetas temporales (pruebas)
    except Exception:
        return []


CLAVES_RUTA = ("dem", "cn_tif", "manning_tif", "cobertura_tif", "idf_csv", "scenarios_csv", "validacion_csv")


def resolver_rutas(cfg, carpeta):
    """Convierte a absolutas las rutas relativas de la configuración (relativas a la carpeta del proyecto): proyectos portables, sin depender del directorio de trabajo."""
    cfg = json.loads(json.dumps(cfg))
    ab = lambda r: str(Path(r) if Path(r).is_absolute() else (Path(carpeta) / r).resolve())
    for k in CLAVES_RUTA:
        if cfg.get(k): cfg[k] = ab(cfg[k])
    for c in cfg.get("cuencas_externas", []) or []:
        if c.get("shp"): c["shp"] = ab(c["shp"])
    if isinstance(cfg.get("evento_observado"), dict) and cfg["evento_observado"].get("hietograma_csv"):
        cfg["evento_observado"]["hietograma_csv"] = ab(cfg["evento_observado"]["hietograma_csv"])
    return cfg


def config_climanet(datos, carpeta):
    p = Path(datos["config_climanet"])
    p = p if p.is_absolute() else Path(carpeta) / p
    return p, resolver_rutas(json.loads(p.read_text(encoding="utf-8")), carpeta)


def sha256(path, cache=None):
    """SHA-256; para archivos grandes reutiliza el valor guardado si tamaño y fecha no cambiaron."""
    p = Path(path); st = p.stat(); clave = f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    if cache is not None and clave in cache:
        return cache[clave]
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    if cache is not None:
        cache[clave] = h.hexdigest()
    return h.hexdigest()


def _etiqueta_forzamiento(ev):
    """Lambda: un pronóstico o una estimación satelital nunca se llama «evento observado»."""
    t = (ev.get("forzamiento_externo") or {}).get("tipo")
    return "PRONÓSTICO (no es una observación)" if t == "pronostico" else "ESTIMACIÓN SATELITAL (no es una medición en tierra)" if t == "satelite" else "EVENTO OBSERVADO"


def _chk(id_, estado, mensaje, **dato):
    return {"id": id_, "estado": estado, "mensaje": mensaje, "dato": dato}


def verificar(datos, carpeta):
    """Verifica entradas SIN ejecutar el modelo. Cada chequeo: ok | aviso | error | pendiente. Devuelve {'chequeos', 'puede_ejecutar', 'estimacion', 'hashes'}."""
    import rasterio, numpy as np
    carpeta = Path(carpeta); ch = []
    try:
        cfg_path, cfg = config_climanet(datos, carpeta)
        ch.append(_chk("config", "ok", f"Configuración del núcleo leída: {cfg_path.name}", ruta=str(cfg_path)))
    except Exception as e:
        return {"chequeos": [_chk("config", "error", f"No se pudo leer la configuración del núcleo: {e}")], "puede_ejecutar": False, "estimacion": None, "hashes": {}}
    rel = lambda r: (Path(r) if Path(r).is_absolute() else carpeta / r)
    cache_h = {}
    cache_arch = carpeta / "registro" / "hashes.json"
    if cache_arch.exists():
        try: cache_h = json.loads(cache_arch.read_text(encoding="utf-8"))
        except Exception: cache_h = {}
    hashes = {}
    # --- archivos de entrada
    for clave in ("dem", "cn_tif", "manning_tif", "cobertura_tif", "idf_csv"):
        if cfg.get(clave):
            p = rel(cfg[clave])
            if not p.exists():
                ch.append(_chk(clave, "error", f"Falta el archivo '{clave}': {p}"))
            else:
                hashes[clave] = {"ruta": str(p), "bytes": p.stat().st_size, "sha256": sha256(p, cache_h)}
                ch.append(_chk(clave, "ok", f"{clave}: {p.name} ({p.stat().st_size / 1e6:.1f} MB, SHA-256 {hashes[clave]['sha256'][:12]}…)"))
    if cfg.get("evento_observado"):
        ev = cfg["evento_observado"]; pe = rel(ev["hietograma_csv"])
        if not pe.exists():
            ch.append(_chk("evento", "error", f"Falta el hietograma del evento observado: {pe}"))
        else:
            try:
                from climanet import evento as EV
                _, bl, inf = EV.cargar_evento({**ev, "hietograma_csv": str(pe)}, float(ev.get("bloque_min", 5)))
                hashes["evento_observado"] = {"ruta": str(pe), "bytes": pe.stat().st_size, "sha256": sha256(pe, cache_h)}
                ch.append(_chk("evento", "aviso" if inf["advertencias"] else "ok", f"FORZAMIENTO = {_etiqueta_forzamiento(ev)} «{inf['id']}»: {inf['P_total_mm']:.1f} mm entre {inf['inicio_utc'][:16]} y {inf['fin_utc'][:16]} UTC. "
                                                                                    + " ".join(inf["advertencias"])))
            except Exception as e:
                ch.append(_chk("evento", "error", f"El evento observado no es válido: {str(e)[:260]}"))
        ch.append(_chk("idf", "ok", "No se usa la IDF: el forzamiento es " + ("el pronóstico." if (ev.get("forzamiento_externo") or {}).get("tipo") == "pronostico" else "la estimación satelital." if (ev.get("forzamiento_externo") or {}).get("tipo") == "satelite" else "el evento observado.")))
    elif cfg.get("idf_inamhi"):
        ch.append(_chk("idf", "ok", f"IDF oficial INAMHI (libro): {cfg['idf_inamhi']}"))
    elif cfg.get("idf_csv"):
        ch.append(_chk("idf", "aviso", "IDF desde CSV externo: confirmar su procedencia (la oficial es el libro INAMHI)."))
    else:
        ch.append(_chk("idf", "error", "Falta la fuente de la IDF."))
    # --- terreno
    est = None
    if cfg.get("dem") and rel(cfg["dem"]).exists():
        with rasterio.open(rel(cfg["dem"])) as s:
            crs_ok = s.crs is not None and s.crs.is_projected and abs(s.crs.linear_units_factor[1] - 1.0) < 1e-9
            ch.append(_chk("terreno_crs", "ok" if crs_ok else "error", f"CRS del terreno: {s.crs} ({'proyectado en metros' if crs_ok else 'NO es proyectado en metros'})", crs=str(s.crs)))
            if str(s.crs.to_epsg()) != datos["crs"].split(":")[1]:
                ch.append(_chk("terreno_crs_proyecto", "aviso", f"El CRS del terreno (EPSG:{s.crs.to_epsg()}) difiere del declarado en el proyecto ({datos['crs']})."))
            ch.append(_chk("terreno_resolucion", "ok", f"Resolución nativa {abs(s.res[0]):.2f} m, {s.width}×{s.height} píxeles", res=abs(s.res[0])))
            aoi = cfg.get("aoi") or [s.bounds.left, s.bounds.right, s.bounds.bottom, s.bounds.top]
            dentro = aoi[0] >= s.bounds.left and aoi[1] <= s.bounds.right and aoi[2] >= s.bounds.bottom and aoi[3] <= s.bounds.top
            ch.append(_chk("aoi", "ok" if dentro else "error", "El área de estudio está dentro del terreno." if dentro else "El área de estudio sale de la extensión del terreno."))
            if dentro:
                from rasterio.windows import from_bounds
                paso = max(int((aoi[1] - aoi[0]) / max(abs(s.res[0]) * 40, 1)), 1)
                w = from_bounds(aoi[0], aoi[2], aoi[1], aoi[3], s.transform)
                a = s.read(1, window=w, out_shape=(max(int(w.height) // paso, 2), max(int(w.width) // paso, 2)))
                v = np.isfinite(a) & (a != s.nodata) & (a > -1e3) & (a < 1e4)
                cob = float(v.mean())
                ch.append(_chk("terreno_cobertura", "ok" if cob >= 0.99 else ("aviso" if cob >= 0.95 else "error"), f"Cobertura de datos válidos en el área: {cob * 100:.1f} % (muestreo decimado)", cobertura=cob))
        tt = datos.get("tipo_terreno", "desconocido")
        ch.append(_chk("terreno_tipo", "ok" if tt == "MDT" else "aviso", f"Tipo de terreno declarado: {tt}. " + ("" if tt == "MDT" else "Si es un modelo de superficie (DSM) incluye edificios/vegetación; no es suelo desnudo.")))
        dv = datos["datum_vertical"].lower()
        ch.append(_chk("datum", "aviso" if ("no verificado" in dv or "desconoc" in dv) else "ok", f"Datum vertical: {datos['datum_vertical']}. " + ("Sin control vertical no se pueden comparar cotas con otras fuentes." if ("no verificado" in dv or "desconoc" in dv) else "")))
        # --- estimación de recursos
        res = float(cfg.get("res", 10))
        aoi = cfg.get("aoi")
        if aoi:
            celdas = int((aoi[1] - aoi[0]) / res) * int((aoi[3] - aoi[2]) / res)
            horas = float(cfg.get("sim_horas", 6)); h_prof = 2.0
            for e_ in cfg.get("entradas_hidrograma") or []:                  # G16: la corrida se alarga hasta el final de cada hidrograma de entrada
                try:
                    from climanet.pipeline import leer_hidrograma_entrada
                    e2 = dict(e_); e2["csv"] = str(e2["csv"]) if Path(str(e2.get("csv", ""))).is_absolute() or not e2.get("csv") else str(carpeta / e2["csv"])
                    horas = max(horas, float(leer_hidrograma_entrada(e2)[0][-1]) / 3600 + 300 / 3600)
                except Exception:
                    pass
            if not cfg.get("evento_observado"):                                # G16/G23: cola de las cuencas externas (base del HU triangular SCS: 2,67·tp tras la tormenta)
                for c_ in cfg.get("cuencas_externas") or []:
                    horas = max(horas, float(cfg.get("storm_min", 180)) / 60 + 2.67 * (float(c_.get("lag_h") or 1) + 5 / 120))
            dt = min(float(cfg.get("max_dt", 5)), float(cfg.get("cfl", .35)) * res / math.sqrt(9.81 * h_prof))
            pasos = int(horas * 3600 / dt)
            seg = celdas * pasos * K_SEG_POR_CELDA_PASO
            est = {"celdas": celdas, "pasos_aprox": pasos, "horas_simuladas": horas, "tiempo_estimado_s": round(seg, 1), "memoria_estimada_mb": round(celdas * 8 * 14 / 1e6, 1),
                   "base": "extrapolado de una corrida medida de 105 000 celdas (274 s); orientativo", "limite_celdas": LIMITE_CELDAS, "limite_horas": LIMITE_HORAS}
            lim_h = LIMITE_HORAS
            ev_ = cfg.get("evento_observado") or {}
            if seg <= 1800:                                                    # G24: el recurso real es el tiempo; hasta 96 h simuladas si se estima ≤ 30 min (tormentas de 24 h, eventos reales)
                lim_h = 96.0; est["limite_horas"] = lim_h; est["nota"] = "tope 96 h simuladas porque el tiempo estimado es ≤ 30 min"
            excede = celdas > LIMITE_CELDAS or horas > lim_h
            ch.append(_chk("recursos", "error" if excede else "ok", (f"Caso grande ({celdas:,} celdas, {horas:g} h): la interfaz no lo ejecuta. Reducir el área o la resolución." if excede
                                                                    else f"Caso pequeño: {celdas:,} celdas, ~{pasos:,} pasos, tiempo estimado ≈ {seg:.0f} s."), **est))
        else:
            ch.append(_chk("recursos", "error", "La configuración no define 'aoi'; la interfaz exige un área acotada."))
    # --- núcleo: validación de configuración
    try:
        from climanet import pipeline
        pipeline.verificar_config(cfg)
        ch.append(_chk("nucleo", "ok", "El núcleo CLIMANET acepta la configuración (cambio climático desactivado, entradas declaradas)."))
    except Exception as e:
        ch.append(_chk("nucleo", "error", f"El núcleo rechaza la configuración: {str(e)[:300]}"))
    # --- etiqueta
    if datos["tipo"] == "sintetico":
        ch.append(_chk("etiqueta", "aviso", "PROYECTO SINTÉTICO: sirve para probar el flujo; sus resultados no representan ningún lugar real."))
    ch.append(_chk("calibracion", "pendiente", "Sin calibración ni validación con observaciones: los resultados son de diseño, no un mapa de amenaza."))
    try:                                                                   # C19: CN de la 2D frente al CN calibrado en hidro
        acc = sorted((carpeta / "calibracion" / "aceptadas").glob("aceptada_*")) if (carpeta / "calibracion" / "aceptadas").exists() else []
        if acc:
            cnc = json.loads((acc[-1] / "aceptacion.json").read_text(encoding="utf-8"))["combinacion"].get("CN")
            fuente = cfg.get("cn_fuente", "raster")
            ch.append(_chk("cn_2d", "aviso" if fuente == "raster" else "ok", (f"La 2D usará el CN del ráster ({cfg.get('cn_origen', 'origen no declarado')}); en hidro aceptaste CN {cnc:g} (modelo agregado diario). Elige en ⚙ «CN para la 2D» cuál usar y decláralo."
                                                                             if fuente == "raster" else f"La 2D usará el CN calibrado en hidro ({cnc:g}) uniforme en toda el área."), cn_calibrado=cnc, fuente=fuente))
    except Exception:
        pass
    if str(datos.get("tipo_terreno", "")).upper() == "DSM" and not cfg.get("fill_sinks"):                 # C21
        ch.append(_chk("dsm", "aviso", "El terreno es un DSM (incluye edificios y vegetación): en zona urbana atrapa agua y acelera el flujo. Considera rellenar depresiones (⚙ de la corrida) o un MDT sin edificaciones."))
    try:                                                                   # cuenca activa vs área simulada (C18)
        act = carpeta / "cuenca" / "activa.json"
        if act.exists() and cfg.get("aoi"):
            import geopandas as gpd, shapely.geometry as sg
            a = json.loads(act.read_text(encoding="utf-8"))
            if a.get("origen") != "malla":
                g = gpd.read_file(carpeta / a["carpeta"] / "cuenca.gpkg").to_crs(datos["crs"]).geometry.unary_union
                x0, x1, y0, y1 = cfg["aoi"]; dentro = g.intersection(sg.box(x0, y0, x1, y1)).area / g.area * 100 if g.area > 0 else 0
                if dentro < 99.5:
                    ch.append(_chk("cuenca_aoi", "aviso", f"La cuenca activa ({a['area_km2']:.1f} km²) queda {100 - dentro:.0f} % FUERA del área simulada: la corrida 2D no representa toda la cuenca. Ajusta el área de estudio o el sitio del proyecto.", dentro_pct=round(dentro, 1)))
                else:
                    ch.append(_chk("cuenca_aoi", "ok", "La cuenca activa está completa dentro del área simulada."))
    except Exception as e:
        ch.append(_chk("cuenca_aoi", "aviso", f"No se pudo comparar la cuenca activa con el área simulada: {str(e)[:120]}"))
    try:
        cache_arch.parent.mkdir(exist_ok=True); cache_arch.write_text(json.dumps(cache_h), encoding="utf-8")
    except Exception:
        pass
    puede = not any(c["estado"] == "error" for c in ch)
    return {"chequeos": ch, "puede_ejecutar": puede, "estimacion": est, "hashes": hashes}
