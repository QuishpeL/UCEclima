# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Evento de lluvia OBSERVADO como forzamiento (alternativa a la tormenta de diseño IDF).

Entrada: un CSV de hietograma con columnas `fecha` (ISO; sin zona = UTC) y `lluvia_mm` (mm por registro, el registro cubre hasta la marca siguiente),
por ejemplo el que exporta climaUCE desde una estación. Reglas, para no inventar lluvia:
  - lluvia ausente (NaN) en la ventana => error (no se reemplaza por cero);
  - valores negativos => error;
  - paso diario o mayor => se exige declarar `desagregacion: "uniforme"`; el resultado queda rotulado «desagregada» (no es lluvia sub-diaria medida);
  - dentro de un registro la lluvia se reparte de forma UNIFORME en bloques de `bloque_min` (se conserva el volumen; es un supuesto declarado en el resumen).
Devuelve (límites_s, mm por bloque, info) con el mismo formato que `idf.design_storm`. No calibra nada: un evento observado sobre un modelo sin calibrar sigue siendo «no calibrado».
"""
from pathlib import Path
import numpy as np
import pandas as pd


class EventoError(ValueError):
    pass


def cargar_evento(cfg_ev, bloque_min=5):
    ruta = Path(cfg_ev.get("hietograma_csv", ""))
    if not ruta.is_file():
        raise EventoError(f"No existe el hietograma del evento: {ruta}")
    d = pd.read_csv(ruta)
    if not {"fecha", "lluvia_mm"} <= set(d.columns):
        raise EventoError("El hietograma debe tener las columnas fecha y lluvia_mm.")
    d["fecha"] = pd.to_datetime(d["fecha"], utc=True, errors="coerce")
    if d["fecha"].isna().any():
        raise EventoError("Hay fechas ilegibles en el hietograma.")
    d = d.sort_values("fecha").reset_index(drop=True)
    if len(d) < 2:
        raise EventoError("El hietograma necesita al menos dos registros.")
    if d["fecha"].duplicated().any():
        raise EventoError("Hay marcas de tiempo repetidas en el hietograma.")
    if d["lluvia_mm"].isna().any():
        raise EventoError(f"El evento tiene {int(d['lluvia_mm'].isna().sum())} registros de lluvia ausente: no se reemplazan por cero. Recorta la ventana o completa el dato con su fuente.")
    if (d["lluvia_mm"] < 0).any():
        raise EventoError("Hay lluvia negativa en el hietograma.")
    dif = d["fecha"].diff().dropna()
    paso = dif.mode().iloc[0]
    if (dif > paso * 1.5).any():
        raise EventoError(f"Hay huecos en el registro (mayor: {dif.max()}); un evento observado debe ser continuo. Recorta la ventana.")
    paso_min = paso.total_seconds() / 60.0
    desag = cfg_ev.get("desagregacion")
    if paso_min >= 1440 - 1e-6 and desag != "uniforme":
        raise EventoError("La lluvia es diaria: indica desagregacion='uniforme' para repartirla en el día. Quedará rotulada como desagregada (no es lluvia sub-diaria medida).")
    if desag not in (None, "uniforme"):
        raise EventoError("Desagregación no reconocida (solo 'uniforme').")
    fin = d["fecha"].iloc[-1] + paso
    t = np.r_[((d["fecha"] - d["fecha"].iloc[0]).dt.total_seconds().values), (fin - d["fecha"].iloc[0]).total_seconds()]       # límites de registro (s)
    mm = d["lluvia_mm"].values.astype(float)
    bl = float(bloque_min) * 60.0
    n = int(np.ceil(t[-1] / bl - 1e-9))
    edges = np.minimum(np.arange(n + 1) * bl, t[-1]); edges[-1] = t[-1]
    cum = np.r_[0.0, np.cumsum(mm)]
    acum = np.interp(edges, t, cum)                                    # acumulado lineal dentro de cada registro = reparto uniforme
    blocks = np.diff(acum)
    info = {"fuente": f"evento observado: {ruta.name}", "id": str(cfg_ev.get("id") or ruta.stem), "inicio_utc": d["fecha"].iloc[0].isoformat(), "fin_utc": fin.isoformat(),
            "paso_registro_min": paso_min, "bloque_min": float(bloque_min), "n_registros": int(len(d)), "P_total_mm": float(mm.sum()),
            "reparto_dentro_del_registro": "uniforme (supuesto; conserva el volumen)",
            "desagregada": bool(paso_min >= 1440 - 1e-6),
            "advertencias": ["Sin humedad antecedente: el CN se aplica con la condición declarada del proyecto.",
                             "Evento observado sobre un modelo NO calibrado: no es una validación."] + (["Lluvia diaria desagregada de forma uniforme: la forma del hietograma es un supuesto."] if paso_min >= 1440 - 1e-6 else [])}
    if abs(float(blocks.sum()) - float(mm.sum())) > 1e-6 * max(1.0, float(mm.sum())):
        raise EventoError("No se conservó el volumen de lluvia al convertir el evento.")
    return edges, blocks, info
