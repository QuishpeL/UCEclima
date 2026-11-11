# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""CMIP6 (NASA NEX-GDDP-CMIP6 en Earth Engine, variable pr) para un punto: decisión de la compuerta y descarga por fases.

COMPUERTA: la regla del proyecto es «primero condiciones existentes bien modeladas». El 13-oct-2026 el usuario decidió ASUMIR la línea base como correcta para avanzar con CMIP6. Esa decisión se
registra tal cual en `registro/cmip6_decision.json` (con fecha y texto) y TODO resultado de CMIP6 queda rotulado «línea base asumida por decisión del usuario; no calibrada ni validada». Sin ese archivo
la descarga sigue bloqueada.

FASES (para no hacer descargas masivas): 1) «historico» 1981–2014 de los modelos pedidos (por defecto todos los que tienen histórico y SSP5-8.5) para EVALUARLOS contra lo observado;
2) «futuro» 2015–2100 solo de los modelos y escenarios pedidos (normalmente los mejores). Consultas por tramos con getRegion (rápido); el calendario es el del producto (365 días en la mayoría).
Unidades: pr en kg m-2 s-1 → mm/día (×86400). Los días sin dato quedan ausentes."""
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

from . import descargas as D

COLECCION = "NASA/GDDP-CMIP6"
ESCENARIOS = ("ssp585",)                      # decisión del usuario (13-oct-2026): solo el escenario extremo SSP5-8.5
HIST_INI, HIST_FIN = "1981-01-01", "2014-12-31"
FUT_INI, FUT_FIN = "2015-01-01", "2100-12-31"
TEXTO_DECISION = ("El usuario decidió (13-oct-2026) asumir la línea base como correcta para avanzar con CMIP6: «asumimos que está correcto, igual el programa permite mejorar». "
                  "La línea base NO está calibrada ni validada en eventos independientes.")


def _decision_path(proyecto):
    return Path(proyecto) / "registro" / "cmip6_decision.json"


def decision(proyecto):
    p = _decision_path(proyecto)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def asumir_baseline(proyecto, texto=None):
    p = _decision_path(proyecto)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    p.parent.mkdir(parents=True, exist_ok=True)
    d = {"decision": "linea_base_asumida_por_el_usuario", "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "texto": texto or TEXTO_DECISION, "estado_real_de_la_linea_base": "no calibrada ni validada",
         "condiciones": ["Todo resultado CMIP6 se rotula «línea base asumida por decisión del usuario».", "Se compara siempre contra la línea base equivalente y se reportan rangos entre modelos.",
                         "El producto NEX-GDDP ya viene con corrección de sesgo (BCSD): la corrección local se compara contra el original y para el futuro se usa un método que preserva la señal de cambio."]}
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def exigir_decision(proyecto):
    """Sin compuerta desde el 14-oct-2026 (decisión del usuario): CMIP6 se usa directamente. Se conserva la función por compatibilidad."""
    return None


def modelos_disponibles(ee, escenarios=("historical",) + ESCENARIOS):
    col = ee.ImageCollection(COLECCION)
    por = {e: set(col.filter(ee.Filter.eq("scenario", e)).distinct("model").aggregate_array("model").getInfo()) for e in escenarios}
    comunes = set.intersection(*por.values())
    return sorted(comunes)


def _tramo(ee, modelo, escenario, a, b, pto):
    col = (ee.ImageCollection(COLECCION).filter(ee.Filter.eq("model", modelo)).filter(ee.Filter.eq("scenario", escenario)).filterDate(a, b).select("pr"))
    for intento in range(3):
        try:
            filas = col.getRegion(pto, 27830).getInfo()
            break
        except Exception as e:
            if intento == 2:
                raise D.DescargaError(f"Earth Engine falló con {modelo}/{escenario} {a[:4]}–{b[:4]}: {str(e)[:150]}") from e
    if len(filas) < 2:
        return pd.DataFrame(columns=["fecha", "pr_mm"])
    d = pd.DataFrame(filas[1:], columns=filas[0])
    d["fecha"] = pd.to_datetime(d["time"], unit="ms").dt.normalize()
    d["pr_mm"] = pd.to_numeric(d["pr"], errors="coerce") * 86400.0
    return d[["fecha", "pr_mm"]]


HILOS = 6                                      # Zeta Z2: modelos en paralelo (cada uno es una consulta getRegion independiente a Earth Engine)


def _paralelo(tareas, progreso, etiqueta):
    """Ejecuta [(clave, función)] con HILOS hilos; devuelve {clave: resultado o excepción}. El progreso se informa al terminar cada tarea."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out, lock, hechos = {}, threading.Lock(), [0]
    with ThreadPoolExecutor(max_workers=HILOS) as ex:
        fut = {ex.submit(f): k for k, f in tareas}
        for fu in as_completed(fut):
            k = fut[fu]
            try:
                out[k] = fu.result()
            except Exception as e:
                out[k] = e
            with lock:
                hechos[0] += 1
                progreso(hechos[0] / len(tareas), f"{k} {etiqueta} ({hechos[0]}/{len(tareas)}, {HILOS} en paralelo)")
    return out


def _serie(ee, modelo, escenario, ini, fin, pto, paso_anios=30):              # Zeta: tramos de 30 años (antes 15): la mitad de consultas, muy lejos del límite de getRegion
    partes = []
    a = pd.Timestamp(ini)
    while a <= pd.Timestamp(fin):
        b = min(a + pd.DateOffset(years=paso_anios), pd.Timestamp(fin) + pd.Timedelta(days=1))
        partes.append(_tramo(ee, modelo, escenario, a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d"), pto)); a = b
    s = pd.concat(partes).drop_duplicates("fecha").sort_values("fecha")
    return s


def _contexto(p):
    from . import gee_chirps as G
    lon, lat = float(p["lon"]), float(p["lat"])
    if not D.punto_admitido(lon, lat):                                               # variante España (30-oct-2026): mismo filtro que descargas.punto_admitido
        raise D.DescargaError(D.MENSAJE_FUERA)
    exigir_decision(p["proyecto"])
    info, ee = G.iniciar()
    if not info.get("autenticado"):
        raise D.DescargaError("Earth Engine no está autorizado en este equipo (usa «Autorizar Earth Engine»). " + str(info.get("error"))[:120])
    return ee, ee.Geometry.Point([lon, lat]), lon, lat


def _previo(destino, nombre, lon, lat):
    """Archivo ya descargado (mismo nombre, mismo punto) en otra carpeta de la misma fuente: se copia en vez de volver a pedirlo."""
    import shutil
    fuente = destino.name.rsplit("_", 2)[0]
    for d in sorted(destino.parent.glob(f"{fuente}_*"), reverse=True):
        f = d / nombre
        if d == destino or not f.exists() or f.stat().st_size < 1000:
            continue
        try:
            par = json.loads((d / "estado.json").read_text(encoding="utf-8")).get("parametros") or {}
            if abs(float(par.get("lon")) - lon) > 1e-6 or abs(float(par.get("lat")) - lat) > 1e-6:
                continue
        except Exception:
            continue
        shutil.copy2(f, destino / nombre)
        return True
    return False


def cmip6_historico(destino, p, progreso):
    ee, pto, lon, lat = _contexto(p)
    modelos = p.get("modelos") or modelos_disponibles(ee)
    maxm = int(p.get("max_modelos") or 0)
    if maxm:
        modelos = list(modelos)[:maxm]
    arch, estado = [], {}

    def uno(m):
        f = destino / f"{m}_historical.csv"
        if _previo(destino, f.name, lon, lat):
            s = pd.read_csv(f, parse_dates=["fecha"])
        else:
            s = _serie(ee, m, "historical", HIST_INI, HIST_FIN, pto); s.to_csv(f, index=False)
        return f.name, s

    progreso(0.0, f"{len(modelos)} modelos históricos, {HILOS} en paralelo")
    res = _paralelo([(m, (lambda m=m: uno(m))) for m in modelos], progreso, "histórico")
    for m in modelos:
        r = res[m]
        if isinstance(r, Exception):
            estado[m] = {"estado": "fallo", "error": str(r)[:200]}; continue
        nombre, s = r; arch.append(nombre)
        estado[m] = {"estado": "ok", "dias": int(len(s)), "primera": str(s["fecha"].min().date()), "ultima": str(s["fecha"].max().date()), "pr_max_mm": round(float(s["pr_mm"].max()), 1)}
    return {"archivos": arch, "fuente": f"{COLECCION} (NEX-GDDP-CMIP6, NASA) vía Earth Engine · variable pr", "fase": "historico", "periodo": [HIST_INI, HIST_FIN], "punto": [lon, lat], "modelos": estado,
            "celda_nominal": "0,25° (~25 km); getRegion toma la celda que contiene el punto", "decision": decision(p["proyecto"]),
            "nota": "pr en mm/día (kg m-2 s-1 × 86400). Producto ya corregido por sesgo (BCSD) por NASA: no se aplica otra corrección a ciegas. Línea base asumida por decisión del usuario; no calibrada ni validada."}


def cmip6_futuro(destino, p, progreso):
    ee, pto, lon, lat = _contexto(p)
    modelos = p.get("modelos")
    if not modelos:
        raise D.DescargaError("Indica los modelos del futuro (normalmente los mejores de la evaluación histórica).")
    esc = p.get("escenarios") or list(ESCENARIOS)
    if not set(esc) <= set(ESCENARIOS):
        raise D.DescargaError("Escenario válido: ssp585 (decisión del usuario: solo el extremo).")
    ini_f, fin_f = p.get("inicio") or FUT_INI, p.get("fin") or FUT_FIN                       # se puede pedir solo 2040–2100 (ventanas de análisis) para ahorrar descargas
    arch, estado = [], {}

    def uno(m, e):
        f = destino / f"{m}_{e}.csv"
        if _previo(destino, f.name, lon, lat):
            s = pd.read_csv(f, parse_dates=["fecha"])
        else:
            s = _serie(ee, m, e, ini_f, fin_f, pto); s.to_csv(f, index=False)
        return f.name, s

    pares = [(m, e) for m in modelos for e in esc]
    res = _paralelo([(f"{m}/{e}", (lambda m=m, e=e: uno(m, e))) for m, e in pares], progreso, "futuro")
    for m, e in pares:
        r = res[f"{m}/{e}"]
        if isinstance(r, Exception):
            estado[f"{m}/{e}"] = {"estado": "fallo", "error": str(r)[:200]}; continue
        nombre, s = r; arch.append(nombre)
        estado[f"{m}/{e}"] = {"estado": "ok", "dias": int(len(s)), "primera": str(s["fecha"].min().date()), "ultima": str(s["fecha"].max().date())}
    return {"archivos": arch, "fuente": f"{COLECCION} (NEX-GDDP-CMIP6, NASA) vía Earth Engine · variable pr", "fase": "futuro", "periodo": [ini_f, fin_f], "punto": [lon, lat], "series": estado,
            "decision": decision(p["proyecto"]), "nota": "Proyecciones, no predicciones. Línea base asumida por decisión del usuario; no calibrada ni validada."}


D.FUENTES["cmip6_historico"] = cmip6_historico
D.FUENTES["cmip6_futuro"] = cmip6_futuro
