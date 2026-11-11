# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Usar un evento OBSERVADO de una estación del proyecto como forzamiento de la corrida (en lugar de la tormenta de diseño IDF).
Exporta el hietograma de la ventana, lo valida con el núcleo (sin ausentes, sin huecos, sin negativos; diaria solo con desagregación declarada) y lo declara en la
configuración (con copia .bak). Sigue siendo un modelo NO calibrado: el resultado no es una validación."""
import json, math
from datetime import datetime
from pathlib import Path

from .. import estaciones as EST

TOPE_SIM_H = 12.0                                    # mismo tope de horas simuladas que la corrida
TOPE_SIM_REAL_H = 96.0                               # G15: evento REAL largo (p. ej. tormenta de 26 h); la corrida lo acepta solo si se estima ≤ 30 min


class EventoUIError(ValueError):
    pass


def _cfg_path(estado):
    p = Path(estado.datos["config_climanet"])
    return p if p.is_absolute() else Path(estado.carpeta) / p


def actual(estado):
    cfg = json.loads(_cfg_path(estado).read_text(encoding="utf-8"))
    return cfg.get("evento_observado")


def _a_utc(carpeta, estacion, t, zona):
    """G18: la ventana se escribe en hora LOCAL de la estación (zona_horaria_origen) o en UTC. Devuelve el texto en UTC sin zona."""
    import pandas as pd
    if (zona or "utc") == "utc":
        return str(pd.Timestamp(t))
    tz = "America/Guayaquil"
    try:
        q = Path(carpeta) / "datos" / "estaciones" / f"{estacion}.qc.json"
        tz = json.loads(q.read_text(encoding="utf-8"))["estacion"].get("zona_horaria_origen") or tz
    except Exception:
        pass
    return str(pd.Timestamp(t).tz_localize(tz).tz_convert("UTC").tz_localize(None)), tz


def usar(estado, estacion, inicio, fin, desagregacion=None, sim_horas=None, bloque_min=5, zona="utc", forzamiento_externo=None):
    from climanet import evento as EV
    ventana_local = None
    if zona == "local":
        (inicio, tz), (fin, _) = _a_utc(estado.carpeta, estacion, inicio, "local"), _a_utc(estado.carpeta, estacion, fin, "local")
        ventana_local = {"zona": tz}
    if not estado.datos:
        raise EventoUIError("Abre un proyecto.")
    marca = f"{datetime.now():%Y%m%d_%H%M%S}"
    carpeta = Path(estado.carpeta)
    ide = f"{estacion}_{str(inicio)[:10].replace('-', '')}"
    destino = carpeta / "datos" / "estaciones" / f"evento_{ide}_{marca}.csv"
    try:
        h = EST.hietograma(carpeta, estacion, inicio, fin, ruta_salida=destino)
    except EST.EstacionError as e:
        raise EventoUIError(str(e)) from e
    cfg_ev = {"id": ide, "hietograma_csv": str(destino), "bloque_min": float(bloque_min)}
    if desagregacion:
        cfg_ev["desagregacion"] = desagregacion
    try:
        edges, blocks, info = EV.cargar_evento(cfg_ev, bloque_min)
    except EV.EventoError as e:
        destino.unlink(missing_ok=True)                  # no deja un archivo de evento inválido
        raise EventoUIError(str(e)) from e
    dur_h = edges[-1] / 3600.0
    sim = float(sim_horas) if sim_horas else math.ceil(dur_h + 1.0)
    if sim < dur_h:
        destino.unlink(missing_ok=True)
        raise EventoUIError(f"sim_horas ({sim:g}) es menor que la duración del evento ({dur_h:.1f} h).")
    if sim > TOPE_SIM_REAL_H:
        destino.unlink(missing_ok=True)
        raise EventoUIError(f"El evento necesita {sim:g} h simuladas; el tope para eventos reales es {TOPE_SIM_REAL_H:g} h. Elige una ventana más corta.")
    cp = _cfg_path(estado)
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    (cp.parent / f"{cp.name}.{marca}.bak").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    if cfg.get("cuencas_externas"):
        raise EventoUIError("Este proyecto tiene cuencas externas, que aún solo se generan con la tormenta de diseño; no se puede usar un evento observado con ellas.")
    cfg["evento_observado"] = {"id": ide, "estacion": estacion, "hietograma_csv": str(destino.relative_to(carpeta)).replace("\\", "/"), "bloque_min": float(bloque_min), **({"desagregacion": desagregacion} if desagregacion else {}),
                               **({"real_largo": True} if sim > TOPE_SIM_H else {}), **({"forzamiento_externo": forzamiento_externo} if forzamiento_externo else {})}   # Lambda: pronóstico o estimación satelital, no observación
    cfg["sim_horas"] = sim
    cp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    out = {"evento": cfg["evento_observado"], "sim_horas": sim, "duracion_h": round(dur_h, 2), "P_total_mm": info["P_total_mm"], "inicio_utc": info["inicio_utc"],
           "fin_utc": info["fin_utc"], "advertencias": info["advertencias"], "desagregada": info["desagregada"]}
    try:                                                                       # G18: la ventana también en hora local de la estación
        import pandas as pd
        tz = (ventana_local or {}).get("zona") or "America/Guayaquil"
        out["inicio_local"] = str(pd.Timestamp(info["inicio_utc"]).tz_convert(tz).tz_localize(None)); out["fin_local"] = str(pd.Timestamp(info["fin_utc"]).tz_convert(tz).tz_localize(None)); out["zona_local"] = tz
    except Exception:
        pass
    return out


def quitar(estado):
    cp = _cfg_path(estado)
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    if "evento_observado" not in cfg:
        return {"evento": None}
    marca = f"{datetime.now():%Y%m%d_%H%M%S}"
    (cp.parent / f"{cp.name}.{marca}.bak").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    cfg.pop("evento_observado")
    cp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return {"evento": None}
