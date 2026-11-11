# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Selección ESTADÍSTICA y reproducible de eventos para calibrar y validar (sin mirar el ajuste del modelo).

Criterios (fijados antes de evaluar cualquier modelo):
  1. Eventos independientes: grupos de días lluviosos (>= umbral) separados por >= `secos` días secos; entre eventos >= `separacion` días.
  2. Datos completos en la ventana [inicio-antes, fin+despues]: sin lluvia ni caudal ausentes y sin valores rellenados («CORRECTED»).
  3. Magnitud: periodo de retorno de la lluvia máxima diaria (Gumbel de los máximos anuales de 24 h SIN factor de intervalo fijo, comparable con valores diarios).
  4. Respuesta medible: pico de caudal >= `ratio_pico` veces el caudal base previo.
  5. Partición calibración/validación por rango de magnitud (alternada, deterministica) con al menos `min_dias_entre_grupos` días de separación entre ambos
     grupos, para que ningún evento de validación comparta antecedentes con uno de calibración.
Alcance: la lluvia diaria es de un pluviómetro (estación rotulada CUMBE, identificada por el usuario como Milagro); la serie «horaria» del proyecto es una
desagregación UNIFORME diaria (no observada). El aforo (AJ_CHIMBO / H390) tiene identidad por confirmar. Nada de esto prueba calibración local.
"""
import math
from dataclasses import dataclass
import numpy as np
import pandas as pd


def cargar_series(ruta_p, ruta_q):
    """Lluvia diaria (de la serie horaria desagregada) y caudal medio diario, con sus banderas de calidad."""
    p = pd.read_csv(ruta_p, encoding="utf-8-sig"); q = pd.read_csv(ruta_q, encoding="utf-8-sig")
    horas_uniformes = bool((p.groupby("Daily_Source_Date").Precipitation_mm.nunique() == 1).all())
    dia = p.groupby("Daily_Source_Date").agg(P_mm=("Precipitation_mm", "sum"), P_crudo_mm=("P_Daily_Raw_mm", "first"),
                                              rellenado=("QC_Flag", lambda s: bool((s != "OBSERVED").any()))).reset_index()
    dia["fecha"] = pd.to_datetime(dia.Daily_Source_Date)
    q["fecha"] = pd.to_datetime(q.Timestamp_HMS.str.replace(", 24:00", "", regex=False), format="%d %b %Y")
    d = dia.merge(q[["fecha", "Q_mean_m3s", "QC_Flag"]].rename(columns={"Q_mean_m3s": "Q_m3s", "QC_Flag": "Q_qc"}), on="fecha", how="outer").sort_values("fecha").reset_index(drop=True)
    d.loc[d.Q_qc == "MISSING", "Q_m3s"] = np.nan                                           # ausente = NaN, no 0
    d.loc[d.P_crudo_mm.isna(), "P_mm"] = np.nan
    d.attrs["horas_uniformes_dentro_del_dia"] = horas_uniformes
    return d


def gumbel_sin_correccion(maximos):
    x = np.asarray(maximos, float); s = x.std(ddof=1); alfa = math.sqrt(6) / math.pi * s; u = x.mean() - 0.5772 * alfa
    return {"alfa": alfa, "u": u, "n": len(x)}


def tr_gumbel(x_mm, g):
    F = math.exp(-math.exp(-(x_mm - g["u"]) / g["alfa"]))
    return float("inf") if F >= 1 else 1.0 / (1.0 - F)


@dataclass
class Criterios:
    umbral_pico_mm: float = 60.0    # lluvia diaria mínima de un pico candidato (peaks-over-threshold)
    separacion_picos: int = 14      # días mínimos entre picos independientes (se conserva el mayor)
    antes: int = 7                  # días de antecedente en la ventana
    despues: int = 14               # días de recesión en la ventana
    min_dq_m3s: float = 10.0        # respuesta mínima: Qpico(ventana, 0..10 d tras el pico) - Q base previo
    max_retardo_dias: int = 10
    min_dias_entre_grupos: int = 30


def identificar_picos(d, c=Criterios()):
    """Picos de lluvia diaria >= umbral, desagrupados: dentro de `separacion_picos` días solo se conserva el mayor."""
    p = d.P_mm.fillna(0).values
    cand = [i for i in np.argsort(-p) if p[i] >= c.umbral_pico_mm]
    elegidos = []
    for i in cand:
        if all(abs(i - j) >= c.separacion_picos for j in elegidos):
            elegidos.append(i)
    return sorted(elegidos)


def evaluar(d, picos, g, c=Criterios()):
    filas = []
    for k, i in enumerate(picos):
        w0, w1 = max(i - c.antes, 0), min(i + c.despues, len(d) - 1)
        v = d.iloc[w0:w1 + 1]
        base = d.Q_m3s.iloc[max(i - c.antes - 3, 0):max(i - c.antes, 1)].min()          # caudal base antes de la ventana
        resp = d.Q_m3s.iloc[i:i + c.max_retardo_dias + 1]
        pico = resp.max() if resp.notna().any() else np.nan
        i_pico = resp.idxmax() if resp.notna().any() else None
        pmax = float(d.P_mm.iloc[i])
        filas.append({"evento": f"P{k + 1:03d}", "fecha_pico_lluvia": d.fecha.iloc[i].date().isoformat(), "ventana_inicio": d.fecha.iloc[w0].date().isoformat(),
                      "ventana_fin": d.fecha.iloc[w1].date().isoformat(), "P_max_dia_mm": pmax, "Tr_P_max_dia_anios": tr_gumbel(pmax, g),
                      "P_3d_mm": float(d.P_mm.iloc[max(i - 1, 0):i + 2].sum()), "P_7d_antes_mm": float(d.P_mm.iloc[max(i - 7, 0):i].sum()),
                      "P_21d_antes_mm": float(d.P_mm.iloc[max(i - 21, 0):i].sum()),
                      "Q_base_previo_m3s": float(base) if np.isfinite(base) else np.nan, "Q_pico_m3s": float(pico) if np.isfinite(pico) else np.nan,
                      "fecha_Q_pico": d.fecha.loc[i_pico].date().isoformat() if i_pico is not None else None,
                      "retardo_pico_dias": int(i_pico - i) if i_pico is not None else np.nan,
                      "dQ_m3s": float(pico - base) if np.isfinite(pico) and np.isfinite(base) else np.nan,
                      "dias_P_faltantes": int(v.P_mm.isna().sum()), "dias_Q_faltantes": int(v.Q_m3s.isna().sum()),
                      "dias_P_rellenados": int(v.rellenado.sum()), "dias_ventana": len(v)})
    return pd.DataFrame(filas)


def filtrar(e, c=Criterios()):
    e = e.copy()
    e["motivo_descarte"] = ""
    e.loc[e.dias_P_faltantes > 0, "motivo_descarte"] += "lluvia ausente; "
    e.loc[e.dias_Q_faltantes > 0, "motivo_descarte"] += "caudal ausente en la ventana; "
    e.loc[e.dias_P_rellenados > 0, "motivo_descarte"] += "lluvia rellenada; "
    e.loc[~(e.dQ_m3s >= c.min_dq_m3s), "motivo_descarte"] += f"sin respuesta (dQ < {c.min_dq_m3s} m3/s); "
    e["cumple"] = e.motivo_descarte == ""
    return e


def particion(e, c=Criterios()):
    """Alterna por rango de periodo de retorno (el más extremo, a validación) y excluye los eventos a menos de `min_dias_entre_grupos` días de un evento
    del otro grupo. Determinista y sin usar ningún resultado de modelo."""
    s = e[e.cumple].sort_values("Tr_P_max_dia_anios", ascending=False).copy()
    s["rol"] = ["validacion" if i % 2 == 0 else "calibracion" for i in range(len(s))]
    s["_f"] = pd.to_datetime(s.fecha_pico_lluvia)
    for i, r in s.iterrows():
        otros = s[(s.rol != r.rol) & (s.index != i) & (s.rol != "excluido_por_cercania_temporal")]
        if len(otros) and abs((otros._f - r._f).dt.days).min() < c.min_dias_entre_grupos:
            s.loc[i, "rol"] = "excluido_por_cercania_temporal"
    return s.drop(columns="_f").sort_values("fecha_pico_lluvia")


def anio_hidrologico(fecha, mes_inicio=8):
    """Año hidrológico que empieza en `mes_inicio` (agosto: separa las estaciones lluviosas de la costa ecuatoriana)."""
    f = pd.Timestamp(fecha)
    return f.year + 1 if f.month >= mes_inicio else f.year


def seleccionar_por_bloques(e, ventanas_ya_usadas=None, por_bloque=2, dias_entre_eventos=30):
    """Selección final. Cada año hidrológico es un BLOQUE que se asigna entero a calibración o a validación (ningún antecedente compartido entre roles).
    Por bloque se toman hasta `por_bloque` eventos, el de mayor Tr y otro a >= `dias_entre_eventos` días. Los bloques se ordenan por el Tr de su mejor
    evento y se alternan empezando por calibración (así ambos grupos cubren magnitudes altas y bajas). `ventanas_ya_usadas` = [(nombre, inicio, fin)] de
    eventos ya empleados para ajustar otro modelo (p. ej. HMS): se marcan y, si caen en validación, se advierte que no es independiente.
    Devuelve (tabla de eventos elegidos, tabla de bloques)."""
    c = e[e.cumple].copy()
    c["bloque"] = [anio_hidrologico(f) for f in c.fecha_pico_lluvia]
    c["f"] = pd.to_datetime(c.fecha_pico_lluvia)
    elegidos, bloques = [], []
    for b, g in c.groupby("bloque"):
        g = g.sort_values(["Tr_P_max_dia_anios", "P_3d_mm"], ascending=False)
        sel = []
        for _, r in g.iterrows():
            if len(sel) < por_bloque and all(abs((r.f - s.f).days) >= dias_entre_eventos for s in sel):
                sel.append(r)
        bloques.append({"bloque": int(b), "n_candidatos": int(len(g)), "mejor_Tr": float(g.Tr_P_max_dia_anios.iloc[0]), "eventos": [s.evento for s in sel]})
        elegidos += [(b, s) for s in sel]
    bl = pd.DataFrame(bloques).sort_values("mejor_Tr", ascending=False).reset_index(drop=True)
    bl["rol"] = ["calibracion" if i % 2 == 0 else "validacion" for i in range(len(bl))]
    rol = dict(zip(bl.bloque, bl.rol))
    filas = []
    for b, s in elegidos:
        d = s.to_dict(); d.pop("f", None); d["rol"] = rol[b]; d["bloque_anio_hidrologico"] = int(b)
        d["ya_usado_en"] = ""
        for nombre, a, z in (ventanas_ya_usadas or []):
            if pd.Timestamp(a) <= pd.Timestamp(d["ventana_fin"]) and pd.Timestamp(z) >= pd.Timestamp(d["ventana_inicio"]):
                d["ya_usado_en"] += nombre + "; "
        if d["ya_usado_en"] and d["rol"] == "validacion":
            d["advertencia"] = "validación NO independiente: el evento ya se empleó para ajustar otro modelo"
        elif d["retardo_pico_dias"] >= 10:
            d["advertencia"] = "pico de caudal en el borde de la ventana de respuesta (≥10 d): revisar si responde a esta lluvia"
        else:
            d["advertencia"] = ""
        filas.append(d)
    return pd.DataFrame(filas).sort_values(["rol", "fecha_pico_lluvia"]), bl
