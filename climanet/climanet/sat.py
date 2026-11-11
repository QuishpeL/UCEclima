# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Evaluación de umbrales para un Sistema de Alerta Temprana (SAT). NO es un SAT operativo completo:
no adquiere datos en continuo, no vigila telemetría ni incluye pronóstico validado ni umbrales locales aprobados.

Catálogo CSV: id,nombre,x,y,variable,umbral_amarillo,umbral_naranja,umbral_rojo,ventana_h,paso_min
  variable: lluvia (acumulado mm en ventana_h) | nivel (m) | caudal (m3/s);  paso_min = cadencia esperada de la estación
Lecturas (tabla larga): id,fecha,valor. Las fechas se interpretan en `zona_horaria` si no traen zona y se llevan a UTC.

Estados: verde/amarillo/naranja/rojo solo con datos válidos y suficientes. Si faltan datos, están viejos, no cubren
la ventana o son inválidos, el estado es 'desconocido' o 'degradado'; NUNCA verde por defecto.
Reloj: modo 'operativo' usa el reloj actual con zona horaria (o un `ahora` con zona); modo 'replay' exige `ahora` explícito.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

NIVELES = ["verde", "amarillo", "naranja", "rojo"]
ESTADOS_SIN_ALERTA = ["degradado", "desconocido"]
ZONA_DEFECTO = "America/Guayaquil"


def leer_telemetria(path, zona_horaria=ZONA_DEFECTO):
    """CSV/Excel largo id,fecha,valor -> fechas UTC con zona. Reemplazable por un lector de API/datalogger/MQTT."""
    df = pd.read_excel(path) if str(path).endswith(("xlsx", "xls")) else pd.read_csv(path)
    f = pd.to_datetime(df["fecha"])
    df["fecha"] = f.dt.tz_localize(zona_horaria).dt.tz_convert("UTC") if f.dt.tz is None else f.dt.tz_convert("UTC")
    return df.sort_values("fecha")


def _ahora(ahora, modo):
    if modo == "operativo":
        if ahora is None:
            return pd.Timestamp.now(tz="UTC")
        a = pd.Timestamp(ahora)
        if a.tzinfo is None:
            raise ValueError("`ahora` debe tener zona horaria en modo operativo.")
        return a.tz_convert("UTC")
    if modo == "replay":
        if ahora is None:
            raise ValueError("El modo replay exige `ahora` explícito (reloj histórico).")
        a = pd.Timestamp(ahora)
        return a.tz_localize(ZONA_DEFECTO).tz_convert("UTC") if a.tzinfo is None else a.tz_convert("UTC")
    raise ValueError("modo debe ser 'operativo' o 'replay'")


def evaluar(catalogo_csv, lecturas, ahora=None, modo="operativo", max_edad_h=3, cobertura_minima=0.8):
    """Tabla con valor, nivel/estado y motivo para cada estación del catálogo."""
    ahora = _ahora(ahora, modo)
    cat = pd.read_csv(catalogo_csv)
    if lecturas["fecha"].dt.tz is None:
        raise ValueError("Las lecturas deben traer fechas con zona horaria (usar leer_telemetria).")
    filas = []
    for _, e in cat.iterrows():
        base = {"id": e["id"], "nombre": e["nombre"], "variable": e["variable"], "x": e["x"], "y": e["y"], "fecha": ahora}
        d = lecturas[(lecturas["id"] == e["id"]) & (lecturas["fecha"] <= ahora)]
        n_total = len(d)
        d = d.drop_duplicates(["id", "fecha"], keep="last")
        d = d[np.isfinite(d["valor"])]
        if e["variable"] in ("lluvia", "caudal"):
            d = d[d["valor"] >= 0]
        n_inval = n_total - len(d)
        if d.empty:
            filas.append({**base, "valor": np.nan, "nivel": "desconocido", "motivo": "sin lecturas válidas"})
            continue
        edad = ahora - d["fecha"].max()
        if edad > pd.Timedelta(hours=max_edad_h):
            filas.append({**base, "valor": np.nan, "nivel": "desconocido",
                          "motivo": f"última lectura válida hace {edad / pd.Timedelta(hours=1):.1f} h"})
            continue
        motivo = ""
        if e["variable"] == "lluvia":
            vent = pd.Timedelta(hours=float(e["ventana_h"]))
            w = d[d["fecha"] > ahora - vent]
            esperado = vent / pd.Timedelta(minutes=float(e["paso_min"]))
            cob = len(w) / esperado if esperado > 0 else 0.0
            if cob < cobertura_minima:
                filas.append({**base, "valor": float(w["valor"].sum()), "nivel": "degradado",
                              "motivo": f"cobertura de ventana {cob:.0%} < {cobertura_minima:.0%}; acumulado es un mínimo"})
                continue
            v = float(w["valor"].sum())
        else:
            v = float(d.sort_values("fecha")["valor"].iloc[-1])
        n = sum(v >= e[c] for c in ("umbral_amarillo", "umbral_naranja", "umbral_rojo"))
        if n_inval:
            motivo = f"{n_inval} lecturas descartadas (NaN/negativas/duplicadas)"
        filas.append({**base, "valor": v, "nivel": NIVELES[n], "motivo": motivo})
    return pd.DataFrame(filas)


def nivel_general(tabla):
    """Máximo nivel válido; si alguna estación está degradada o desconocida el conjunto no puede ser 'verde'."""
    niveles = list(tabla["nivel"])
    validos = [NIVELES.index(n) for n in niveles if n in NIVELES]
    peor = NIVELES[max(validos)] if validos else None
    incompleto = any(n in ESTADOS_SIN_ALERTA for n in niveles)
    if peor in (None, "verde") and incompleto:
        return "degradado" if "degradado" in niveles else "desconocido"
    return peor if peor is not None else "desconocido"


def alerta_por_modelo(q_pico_m3s, umbrales_q):
    """Pico pronosticado -> nivel. SIN validar: solo informativo hasta calibrar y aprobar umbrales locales."""
    return NIVELES[sum(q_pico_m3s >= u for u in umbrales_q)]


def publicar(tabla, salida_json):
    Path(salida_json).write_text(json.dumps(
        {"general": nivel_general(tabla), "estaciones": json.loads(tabla.to_json(orient="records", date_format="iso"))},
        ensure_ascii=False, indent=2), encoding="utf-8")
