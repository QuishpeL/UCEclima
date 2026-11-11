# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Panel «Hidrología y calibración»: hietograma, hidrogramas observado/simulado, volúmenes acumulados, balance y tránsito, con las series REALES de las corridas del proyecto (punto de partida: Mazar).

Reglas (no se saltan):
- Se usan solo series que existen: salidas de corridas (hietograma.csv, balance_agua.csv, resumen.json) y observaciones del PROYECTO (observaciones/aforos_caudal.csv con identidad confirmada).
  Milagro NO se usa: no tiene caudales observados, así que no puede servir de base para calibrar. Unidades y fechas se conservan; si una serie no tiene fecha se dice (tiempo desde el inicio).
- Las métricas con observaciones se calculan SOLO en los instantes coincidentes con dato válido en ambas series (sin interpolar, sin rellenar). Sin observaciones válidas el resultado se rotula
  «SIMULACIÓN SIN CALIBRAR». Con observaciones sigue sin declararse calibrado: la calibración y la validación exigen eventos distintos.
- Balance por subcuenca y tránsito por tramo solo existen si el proyecto define cuencas y tramos; Mazar aún no tiene polígono de cuenca: el panel lo dice en lugar de mostrar datos de otro sitio.
- Nada de lo que se exporta sobrescribe: carpeta nueva con marca de tiempo."""
import csv, json, math, re, sys
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

ETQ_SIN_CALIBRAR = "SIMULACIÓN SIN CALIBRAR"
AVISO = ("Resultado de simulación bajo línea base asumida por decisión del usuario; no calibrado ni validado. No es predicción ni una simulación de otros programas (HEC-HMS/HEC-RAS) ni equivale a ellos. "
         "Capacidad de canales y pérdidas de carga: no evaluadas.")
MIN_PARES = 5                                       # pares coincidentes mínimos para reportar cualquier métrica


class HidroError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ métricas SOLO en períodos coincidentes con dato válido
def _serie(x, nombre):
    s = x if isinstance(x, pd.Series) else pd.Series(x)
    if not isinstance(s.index, pd.DatetimeIndex):
        raise HidroError(f"{nombre}: el índice debe ser de fechas (no se emparejan series sin fecha).")
    return s.astype(float)


def metricas_coincidentes(obs, sim, unidad_obs="m3/s", unidad_sim="m3/s", minimo=MIN_PARES):
    """Compara obs y sim SOLO en los instantes presentes en ambas con valor finito (sin interpolar ni rellenar). Exige la misma unidad y que ambos índices tengan (o no) zona horaria.
    Devuelve n_pares, periodo coincidente, cobertura de la observación sobre la ventana simulada y NSE, KGE, PBIAS, RMSE, errores de pico, de tiempo al pico y de volumen. Si hay menos de `minimo`
    pares no calcula nada y explica por qué (`calculado: False`)."""
    if unidad_obs != unidad_sim:
        raise HidroError(f"unidades distintas (obs {unidad_obs} · sim {unidad_sim}): convertir explícitamente antes de comparar.")
    o, s = _serie(obs, "observada"), _serie(sim, "simulada")
    if (o.index.tz is None) != (s.index.tz is None):
        raise HidroError("una serie tiene zona horaria y la otra no: localizar explícitamente (no se asume).")
    o = o[~o.index.duplicated()].sort_index(); s = s[~s.index.duplicated()].sort_index()
    ok_o, ok_s = np.isfinite(o.values), np.isfinite(s.values)
    idx = o.index[ok_o].intersection(s.index[ok_s])
    ventana = s.index[ok_s]
    cob = float(o.index[ok_o].isin(ventana).sum() / max(len(ventana), 1)) if len(ventana) else 0.0
    base = {"n_pares": int(len(idx)), "n_obs_validas": int(ok_o.sum()), "n_sim_validas": int(ok_s.sum()), "cobertura_obs_sobre_sim": cob, "unidad": unidad_sim,
            "periodo_coincidente": [str(idx.min()), str(idx.max())] if len(idx) else None, "criterio": "solo instantes con dato válido en ambas series; sin interpolar ni rellenar"}
    if len(idx) < minimo:
        return {**base, "calculado": False, "motivo": f"{len(idx)} pares coincidentes válidos (mínimo {minimo}): no se calculan métricas."}
    a, b = o.loc[idx].values, s.loc[idx].values; e = b - a; sa = float(np.sum((a - a.mean()) ** 2))
    dt = float(np.median(np.diff(idx.values).astype("timedelta64[s]").astype(float))) if len(idx) > 1 else float("nan")
    nse = 1 - float(np.sum(e ** 2)) / sa if sa > 0 else float("nan")
    r = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
    kge = 1 - math.sqrt((r - 1) ** 2 + (b.std() / a.std() - 1) ** 2 + (b.mean() / a.mean() - 1) ** 2) if np.isfinite(r) and a.std() > 0 and a.mean() != 0 else float("nan")
    ia, ib = int(np.argmax(a)), int(np.argmax(b))
    return {**base, "calculado": True, "NSE": nse, "KGE": kge, "PBIAS_pct": 100 * float(e.sum()) / float(a.sum()) if a.sum() != 0 else float("nan"), "RMSE": float(np.sqrt(np.mean(e ** 2))),
            "pico_obs": float(a.max()), "pico_sim": float(b.max()), "error_pico_pct": 100 * (float(b.max()) / float(a.max()) - 1) if a.max() > 0 else float("nan"),
            "error_tiempo_pico_min": float((idx[ib] - idx[ia]).total_seconds() / 60),
            "volumen_obs_m3": float(a.sum() * dt), "volumen_sim_m3": float(b.sum() * dt), "error_volumen_pct": 100 * (float(b.sum()) / float(a.sum()) - 1) if a.sum() > 0 else float("nan"),
            "nota": "Métricas sobre los pares coincidentes; no implican calibración ni validación (se necesitan eventos de calibración y de validación distintos)."}


def estado_calibracion(observaciones, metricas):
    """Rótulo del resultado. Sin observaciones válidas: «SIMULACIÓN SIN CALIBRAR». Con ellas: comparación (jamás «calibrado» automático)."""
    if observaciones is None or not metricas or not metricas.get("calculado"):
        return {"etiqueta": ETQ_SIN_CALIBRAR, "calibracion": "sin_calibrar", "motivo": (metricas or {}).get("motivo") or "no hay observaciones válidas coincidentes con la simulación"}
    return {"etiqueta": f"Comparación con observaciones ({metricas['n_pares']} pares coincidentes) · calibración y validación pendientes", "calibracion": "comparacion_con_observaciones",
            "motivo": "hay pares válidos, pero la calibración exige separar eventos de calibración y de validación"}


# ------------------------------------------------------------------------------------------------ observaciones (formato de observaciones/FICHA_OBSERVACIONES.md)
def leer_observaciones(proyecto=None, ruta=None):
    """aforos_caudal.csv del PROYECTO (o la ruta dada): SOLO aforos con identidad_confirmada = si y caudal válido. Devuelve (Series con fecha y zona | None, nota).
    La serie CELEC de Mazar es candidata, pero su variable «caudal» no tiene el significado confirmado: no entra hasta que la persona lo confirme y la registre en ese archivo."""
    cand = [Path(ruta)] if ruta else ([Path(proyecto) / "observaciones" / "aforos_caudal.csv"] if proyecto else [])
    for f in cand:
        if not f.exists():
            continue
        d = pd.read_csv(f)
        if d.empty:
            continue
        if not {"fecha", "caudal_m3s", "identidad_confirmada"} <= set(d.columns):
            return None, f"{f.name}: faltan columnas fecha, caudal_m3s, identidad_confirmada."
        d = d[d["identidad_confirmada"].astype(str).str.lower().isin(["si", "sí", "true", "1"])].copy()
        d["caudal_m3s"] = pd.to_numeric(d["caudal_m3s"], errors="coerce"); d = d[np.isfinite(d["caudal_m3s"]) & (d["caudal_m3s"] >= 0)]
        d["fecha"] = pd.to_datetime(d["fecha"], utc=True, errors="coerce"); d = d.dropna(subset=["fecha"])
        if d.empty:
            return None, f"{f.name} no tiene aforos con identidad confirmada y caudal válido."
        return d.drop_duplicates("fecha").set_index("fecha")["caudal_m3s"].sort_index(), f"{len(d)} aforos con identidad confirmada ({f})"
    return None, "no hay observaciones de caudal confirmadas en el proyecto (observaciones/aforos_caudal.csv). La serie CELEC de Mazar es candidata, pero el significado de su «caudal» está sin confirmar."


# ------------------------------------------------------------------------------------------------ fuente 1: corridas del proyecto (2D)
def corridas(proyecto):
    out = []
    for r in sorted((Path(proyecto) / "resultados").glob("corrida_*"), reverse=True):
        s = next(iter(r.glob("salida/*/resumen.json")), None)
        if not s or not (s.parent / "hietograma.csv").exists():
            continue
        try:
            d = json.loads(s.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({"id": r.name, "escenario": d.get("escenario"), "forzamiento": d.get("tipo_forzamiento"), "P_total_mm": d.get("P_total_mm"), "estado": d.get("estado"), "area_km2": (d.get("area_m2") or 0) / 1e6})
    return out


def _fecha_inicio_corrida(r):
    try:
        e = json.loads((r / "entrada.json").read_text(encoding="utf-8")); ev = (e.get("config") or {}).get("evento_observado") or {}
        h = ev.get("hietograma_csv")
        if h and Path(h).exists():
            d = pd.read_csv(h, nrows=3)
            col = next((c for c in d.columns if c.lower() in ("fecha", "inicio", "datetime", "time", "tiempo")), None)
            if col:
                t = pd.to_datetime(d[col].iloc[0], errors="coerce", utc=True)
                if pd.notna(t):
                    return t
    except Exception:
        pass
    return None


def serie_corrida(proyecto, run_id, observaciones=None):
    r = Path(proyecto) / "resultados" / run_id
    sal = next(iter(r.glob("salida/*/resumen.json")), None)
    if not sal:
        raise HidroError("La corrida no tiene resumen.json.")
    carp = sal.parent; res = json.loads(sal.read_text(encoding="utf-8"))
    hi = pd.read_csv(carp / "hietograma.csv"); ba = pd.read_csv(carp / "balance_agua.csv"); area = float(res["area_m2"])
    t0 = _fecha_inicio_corrida(r)
    mm = hi["lluvia_mm"].values; cum_mm = np.cumsum(mm)
    t = ba["tiempo_s"].values; vs = ba["volumen_salida_m3"].values; dt = np.diff(t)
    q = np.where(dt > 0, np.diff(vs) / np.where(dt > 0, dt, 1), np.nan); tq = (t[1:] + t[:-1]) / 2
    cum_rain = np.interp(t, np.r_[0, hi["fin_s"].values], np.r_[0, cum_mm]) / 1000 * area
    perd = cum_rain - ba["volumen_escorrentia_m3"].values
    fecha = (lambda s: [str(t0 + pd.to_timedelta(x, unit="s")) for x in s]) if t0 is not None else (lambda s: None)
    sim = {"nombre": "Simulado en la frontera de salida del dominio 2D", "tipo": "simulado", "unidad": "m3/s", "t_s": tq.tolist(), "fecha": fecha(tq), "q": q.tolist(),
           "metodo": "Q = Δ(volumen_salida_m3)/Δt del balance de agua del solver (no es un caudal en una sección)."}
    metr = None; obs_info = "no aplicable: la corrida es de diseño y no tiene fechas, no puede emparejarse con observaciones"
    series = [sim]
    if t0 is not None and observaciones is not None:
        qs = pd.Series(q, index=pd.DatetimeIndex([t0 + pd.to_timedelta(x, unit="s") for x in tq]))
        metr = metricas_coincidentes(observaciones, qs); obs_info = "emparejado por fecha"
        o = observaciones[(observaciones.index >= qs.index.min()) & (observaciones.index <= qs.index.max())]
        series.append({"nombre": "Observado (aforos con identidad confirmada)", "tipo": "observado", "unidad": "m3/s", "fecha": [str(i) for i in o.index], "q": o.values.tolist()})
    elif t0 is not None:
        obs_info = "la corrida tiene fechas, pero no hay observaciones válidas de caudal"
    est = estado_calibracion(observaciones if (t0 is not None) else None, metr)
    dt_h = np.diff(np.r_[0, hi["fin_s"].values]) / 3600
    balance = [{"unidad_espacial": "Dominio 2D completo", "area_km2": area / 1e6, "lluvia_mm": float(mm.sum()), "lluvia_m3": float(cum_rain[-1]), "escorrentia_generada_m3": float(ba["volumen_escorrentia_m3"].iloc[-1]),
                "perdidas_inferidas_m3": float(perd[-1]), "salida_m3": float(vs[-1]), "almacenado_final_m3": float(ba["volumen_almacenado_m3"].iloc[-1]), "entrada_m3": float(ba["volumen_entrada_m3"].iloc[-1]),
                "residual_m3": float(res.get("residual_final_m3", float("nan"))), "error_balance_max_pct": float(res.get("error_balance_max_pct", float("nan"))),
                "nota": "pérdidas = lluvia − escorrentía generada (inferidas; el solver no las separa en infiltración/otras). No hay subcuencas en el modelo 2D (Mazar aún sin polígono de cuenca)."}]
    ap = res.get("aporte_por_entrada")
    if isinstance(ap, dict):
        for k, v in ap.items():
            balance.append({"unidad_espacial": f"Aporte externo «{k}»", "salida_m3": None, "entrada_m3": float(v) if isinstance(v, (int, float)) else None})
    return {"fuente": "corrida", "id": run_id, "escenario": res.get("escenario"), "forzamiento": res.get("tipo_forzamiento"), "estado": est, "aviso": AVISO + " " + str(res.get("aviso", "")).replace("�", ""),
            "observaciones": obs_info, "tiempo": {"referencia": str(t0) if t0 is not None else None, "nota": "tiempo en segundos desde el inicio de la corrida" + ("" if t0 is not None else " (sin fecha: tormenta de diseño)")},
            "hietograma": {"inicio_s": hi["inicio_s"].tolist(), "fin_s": hi["fin_s"].tolist(), "mm": mm.tolist(), "acumulado_mm": cum_mm.tolist(), "unidad": "mm por intervalo", "fecha_inicio": fecha(hi["inicio_s"].values)},
            "hidrogramas": series, "volumenes": {"t_s": t.tolist(), "lluvia_m3": cum_rain.tolist(), "escorrentia_m3": ba["volumen_escorrentia_m3"].tolist(), "salida_m3": vs.tolist(),
                                                 "almacenado_m3": ba["volumen_almacenado_m3"].tolist(), "perdidas_inferidas_m3": perd.tolist(), "unidad": "m3 acumulados"},
            "balance": balance, "transito": [], "transito_nota": "No aplica: el proyecto no define tramos con tránsito (el modelo 2D no los usa). Mazar aún no tiene polígono de cuenca.", "metricas": metr,
            "resumen": {"Qpico_salida_m3s": float(np.nanmax(q)), "t_pico_h": float(tq[int(np.nanargmax(q))] / 3600), "P_total_mm": float(mm.sum())}}


# ------------------------------------------------------------------------------------------------ catálogo y exportación
def casos(proyecto):
    return {"corridas": corridas(proyecto) if proyecto else [], "observaciones": leer_observaciones(proyecto)[1], "etiqueta_por_defecto": ETQ_SIN_CALIBRAR,
            "subcuencas": "Este proyecto no define subcuencas ni tramos: el balance es del dominio 2D completo y el tránsito por tramo no aplica (Mazar aún no tiene polígono de cuenca)."}


def _guardar_csv(path, filas, cols):
    pd.DataFrame(filas, columns=cols).to_csv(path, index=False, encoding="utf-8")


def exportar(proyecto, fuente, id_, salida=None, observaciones_ruta=None):
    if fuente != "corrida":
        raise HidroError("Solo se exportan corridas del proyecto (fuente = corrida).")
    """CSV (hietograma, hidrogramas, volúmenes, balance, tránsito, métricas) + PNG de cada gráfica + manifiesto, en carpeta nueva con marca de tiempo. Nunca sobrescribe."""
    obs, _ = leer_observaciones(proyecto, observaciones_ruta)
    d = serie_corrida(proyecto, id_, obs)
    base = Path(salida) if salida else Path(proyecto) / "registro" / "hidrologia"
    car = base / f"hidrologia_{datetime.now():%Y%m%d_%H%M%S}_{d['fuente']}_{re.sub(r'[^A-Za-z0-9_.-]', '_', id_)}"; car.mkdir(parents=True)
    h = d["hietograma"]; arch = []
    def w(nombre, df):
        df.to_csv(car / nombre, index=False, encoding="utf-8"); arch.append(nombre)
    hh = pd.DataFrame({"inicio_s": h["inicio_s"], "fin_s": h["fin_s"], "lluvia_mm": h["mm"], "acumulado_mm": h["acumulado_mm"]})
    if h.get("fecha_inicio"):
        hh.insert(0, "fecha_inicio", h["fecha_inicio"])
    w("hietograma.csv", hh)
    filas = []
    for s in d["hidrogramas"]:
        n = len(s["q"])
        for i in range(n):
            filas.append({"serie": s["nombre"], "tipo": s["tipo"], "t_s": s["t_s"][i] if s.get("t_s") else None, "fecha": s["fecha"][i] if s.get("fecha") else None, "caudal_" + s["unidad"].replace("/", "_"): s["q"][i]})
    w("hidrogramas.csv", pd.DataFrame(filas))
    v = d["volumenes"]; w("volumenes_acumulados.csv", pd.DataFrame({k: val for k, val in v.items() if isinstance(val, list) and len(val) == len(v["t_s"])}))
    w("balance.csv", pd.DataFrame(d["balance"]))
    if d["transito"]:
        w("transito_por_tramo.csv", pd.concat([pd.DataFrame({"caso": t["caso"], "K_h": t["K_h"], "X": t["X"], "subtramos": t["subtramos"], "t_min": t["t_min"], "entrada_m3s": t["entrada"], "HMS_m3s": t["HMS"], "CLIMANET_m3s": t["CLIMANET"]}) for t in d["transito"]]))
    if d.get("metricas"):
        w("metricas_periodo_coincidente.csv", pd.DataFrame([d["metricas"]]))
    pngs = _png(car, d)
    man = {"creado": datetime.now().isoformat(timespec="seconds"), "fuente": d["fuente"], "id": id_, "estado": d["estado"], "aviso": d["aviso"], "observaciones": d["observaciones"], "tiempo": d["tiempo"],
           "tablas": arch, "graficas": pngs, "unidades": {"caudal": "m3/s", "volumen": "m3", "lluvia": "mm"}, "metricas": d.get("metricas"), "transito_nota": d["transito_nota"]}
    (car / "manifiesto.json").write_text(json.dumps(man, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return {"carpeta": str(car), "tablas": arch, "graficas": pngs, "estado": d["estado"]}


def _png(car, d):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": "#0f1b2d", "axes.facecolor": "#14233a", "axes.edgecolor": "#3b4a63", "axes.labelcolor": "#c9d6e6", "xtick.color": "#9fb0c6", "ytick.color": "#9fb0c6",
                         "text.color": "#e6edf5", "grid.color": "#25364f", "font.family": ["Calibri", "Arial", "DejaVu Sans"], "font.size": 10})
    CIAN, REF, OBS = "#6cc4ec", "#93a4b8", "#ffffff"; etiqueta = d["estado"]["etiqueta"]; pie = f"{etiqueta} · {d['id']} · línea base asumida; no calibrada ni validada"; out = []
    def cierre(fig, nombre):
        fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.text(0.01, 0.01, pie, fontsize=8, color="#ffd166" if d["estado"]["calibracion"] == "sin_calibrar" else "#9fb0c6"); fig.savefig(car / nombre, dpi=140); plt.close(fig); out.append(nombre)
    h = d["hietograma"]; x = (np.array(h["fin_s"]) + np.array(h["inicio_s"])) / 7200
    fig, ax = plt.subplots(figsize=(8, 4)); ax.bar(x, h["mm"], width=(np.array(h["fin_s"][:1]) - np.array(h["inicio_s"][:1]))[0] / 3600 * .9, color=CIAN)
    ax.invert_yaxis(); ax.set_xlabel("tiempo (h desde el inicio)"); ax.set_ylabel("lluvia (" + h["unidad"] + ")"); ax2 = ax.twinx(); ax2.plot(x, h["acumulado_mm"], color="#ffd166"); ax2.set_ylabel("acumulado (mm)")
    ax.set_title("Hietograma"); ax.grid(alpha=.4); cierre(fig, "hietograma.png")
    fig, ax = plt.subplots(figsize=(8, 4))
    for s in d["hidrogramas"]:
        tx = np.array(s["t_s"]) / 3600 if s.get("t_s") else np.arange(len(s["q"]))
        ax.plot(tx, s["q"], color={"simulado": CIAN, "referencia_modelo": REF, "observado": OBS}[s["tipo"]], ls="--" if s["tipo"] == "referencia_modelo" else "-", lw=2, label=s["nombre"][:60])
    ax.set_xlabel("tiempo (h desde el inicio)"); ax.set_ylabel("caudal (m³/s)"); ax.set_title("Hidrogramas"); ax.legend(fontsize=7); ax.grid(alpha=.4); cierre(fig, "hidrogramas.png")
    v = d["volumenes"]; fig, ax = plt.subplots(figsize=(8, 4)); tv = np.array(v["t_s"]) / 3600
    for k, c in (("lluvia_m3", "#ffd166"), ("escorrentia_m3", CIAN), ("salida_m3", "#a98bff"), ("almacenado_m3", REF)):
        if k in v:
            ax.plot(tv, v[k], color=c, lw=2, label=k.replace("_m3", "").replace("_", " "), ls="-")
    ax.set_xlabel("tiempo (h)"); ax.set_ylabel("volumen acumulado (m³)"); ax.set_title("Volúmenes acumulados"); ax.legend(fontsize=7); ax.grid(alpha=.4); cierre(fig, "volumenes_acumulados.png")
    r = d["balance"][0]; fig, ax = plt.subplots(figsize=(8, 4)); nom = ["lluvia", "escorrentía", "pérdidas\ninferidas", "salida", "almacenado\nfinal"]
    val = [r["lluvia_m3"], r["escorrentia_generada_m3"], r["perdidas_inferidas_m3"], r["salida_m3"], r["almacenado_final_m3"]]; ax.bar(nom, [x_ / 1e6 for x_ in val], color=["#ffd166", CIAN, REF, "#a98bff", "#6cc4ec"])
    ax.set_ylabel("hm³"); ax.set_title("Balance del dominio 2D"); cierre(fig, "balance.png")
    return out
