# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""⚙ Configuración por módulo: parámetros matemáticos y de paso que la persona puede cambiar en config_climanet.json.
Cada cambio se valida (tipo y rango) y deja una copia .bak de la configuración anterior."""
import json
import time
from pathlib import Path

ESQUEMA = {
    "terreno": [
        {"clave": "res", "nombre": "Resolución del modelo", "unidad": "m", "tipo": "float", "min": 0.5, "max": 200, "defecto": 30},
    ],
    "idf": [
        {"clave": "Tr", "nombre": "Periodo de retorno", "unidad": "años", "tipo": "opcion", "opciones": [2, 5, 10, 25, 50, 100], "defecto": 100},
        {"clave": "storm_min", "nombre": "Duración de la tormenta", "unidad": "min", "tipo": "int", "min": 30, "max": 1440, "defecto": 180},
    ],
    "corrida": [
        {"clave": "res", "nombre": "Resolución del modelo", "unidad": "m", "tipo": "float", "min": 0.5, "max": 200, "defecto": 30},
        {"clave": "sim_horas", "nombre": "Tiempo simulado", "unidad": "h", "tipo": "float", "min": 0.5, "max": 96, "defecto": 6},
        {"clave": "max_dt", "nombre": "Paso de tiempo máximo", "unidad": "s", "tipo": "float", "min": 0.05, "max": 60, "defecto": 5},
        {"clave": "cfl", "nombre": "Número de Courant objetivo", "unidad": "", "tipo": "float", "min": 0.05, "max": 0.9, "defecto": 0.35},
        {"clave": "solver", "nombre": "Solver", "unidad": "", "tipo": "opcion", "opciones": ["malla", "subgrid"], "defecto": "malla"},
        {"clave": "rf_m", "nombre": "Resolución fina (solo subgrid)", "unidad": "m", "tipo": "float", "min": 0.5, "max": 20, "defecto": 2.0},
        {"clave": "boundary", "nombre": "Frontera", "unidad": "", "tipo": "opcion", "opciones": ["free_outflow", "closed"], "defecto": "free_outflow"},
        {"clave": "fill_sinks", "nombre": "Rellenar depresiones del MDT", "unidad": "", "tipo": "bool", "defecto": False},
        {"clave": "fill_sinks_max_m", "nombre": "Rellenar solo depresiones de hasta (0 = todas)", "unidad": "m", "tipo": "float", "min": 0, "max": 50, "defecto": 0},
        {"clave": "v_anomala_ms", "nombre": "Marcar velocidades mayores que", "unidad": "m/s", "tipo": "float", "min": 2, "max": 50, "defecto": 10},
        {"clave": "seccion_semiancho_celdas", "nombre": "Semiancho de la sección en la salida", "unidad": "celdas", "tipo": "float", "min": 1, "max": 50, "defecto": 5},
        {"clave": "cn_fuente", "nombre": "CN para la 2D", "unidad": "", "tipo": "opcion", "opciones": ["raster", "calibrado"], "defecto": "raster"},
        {"clave": "cn_2d_declarado", "nombre": "CN declarado para la 2D (prueba de estrés; 0 = no usar)", "unidad": "", "tipo": "float", "min": 0, "max": 99, "defecto": 0},
        {"clave": "cn_amc_2d", "nombre": "Humedad antecedente del CN de la 2D (calibrado o ráster)", "unidad": "", "tipo": "opcion", "opciones": ["ninguna", "auto", "I", "III"], "defecto": "ninguna"},
        {"clave": "cn_default", "nombre": "CN donde falte el ráster", "unidad": "", "tipo": "float", "min": 30, "max": 100, "defecto": 85},
        {"clave": "manning_default", "nombre": "Manning donde falte el ráster", "unidad": "s/m^(1/3)", "tipo": "float", "min": 0.01, "max": 0.3, "defecto": 0.06},
    ],
}
AVISOS = {"cfl": (0.35, "Por encima de 0,35 la comprobación de estabilidad del núcleo marca la corrida como fuera de criterio.")}


class ConfigError(Exception):
    pass


def _ruta(carpeta, datos):
    return Path(carpeta) / datos.get("config_climanet", "config_climanet.json")


def leer(carpeta, datos, modulo):
    if modulo not in ESQUEMA:
        raise ConfigError("Módulo sin configuración.")
    cfg = json.loads(_ruta(carpeta, datos).read_text(encoding="utf-8"))
    return {"modulo": modulo, "campos": [{**c, "valor": cfg.get(c["clave"], c["defecto"]), "de_fabrica": c["clave"] not in cfg} for c in ESQUEMA[modulo]]}


def _convertir(c, v):
    t = c["tipo"]
    try:
        if t == "bool":
            return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "si", "sí", "on")
        if t == "opcion":
            o = next((x for x in c["opciones"] if str(x) == str(v)), None)
            if o is None:
                raise ConfigError(f"{c['nombre']}: opción no válida ({v}).")
            return o
        x = float(str(v).replace(",", "."))
        x = int(round(x)) if t == "int" else x
    except (TypeError, ValueError):
        raise ConfigError(f"{c['nombre']}: valor no numérico ({v}).")
    if not (c["min"] <= x <= c["max"]):
        raise ConfigError(f"{c['nombre']}: fuera de rango [{c['min']}, {c['max']}] {c['unidad']}.")
    return x


def guardar(carpeta, datos, modulo, valores):
    if modulo not in ESQUEMA:
        raise ConfigError("Módulo sin configuración.")
    p = _ruta(carpeta, datos)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cambios, avisos = {}, []
    for c in ESQUEMA[modulo]:
        if c["clave"] not in valores:
            continue
        v = _convertir(c, valores[c["clave"]])
        if cfg.get(c["clave"], c["defecto"]) != v:
            cambios[c["clave"]] = {"antes": cfg.get(c["clave"], c["defecto"]), "ahora": v}
            cfg[c["clave"]] = v
        if c["clave"] in AVISOS and isinstance(v, (int, float)) and v > AVISOS[c["clave"]][0]:
            avisos.append(AVISOS[c["clave"]][1])
    if cambios:
        (p.parent / f"{p.name}.{time.strftime('%Y%m%d_%H%M%S')}.bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"cambios": cambios, "avisos": avisos}
