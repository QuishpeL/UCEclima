# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""D5 · Benchmark de la calibración (Delta). Compara, en LAS MISMAS ventanas de eventos, con la misma lluvia y la misma métrica
(calibracion._evaluar agrupa las ventanas de ajuste y de validación):
  (a) referencia sin habilidad: caudal base del inicio del evento, constante (Knoben et al. 2019 discuten benchmarks así);
  (b) GR4J diario continuo (Perrin et al. 2003) con evapotranspiración potencial CONSTANTE: declarada por la persona (mm/día) o, si lo
      pide explícitamente, calibrada como quinto parámetro; parámetros ajustados por evolución diferencial maximizando el KGE de AJUSTE;
  (c) la combinación del modelo de eventos (Gamma/Delta) que se indique (barrido + id) o la aceptada.
Etiqueta obligatoria: «referencia de comparación, no calibrada por la persona». GR4J y la base constante NO reemplazan la calibración
aceptada: sirven para saber si el modelo de eventos aporta habilidad. Script original: benchmark_referencia.py."""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import calibracion as K

ETIQUETA = "referencia de comparación, no calibrada por la persona"

try:
    from numba import njit
except Exception:                                                     # sin numba funciona igual, más lento
    def njit(*a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]


@njit(cache=not getattr(sys, "frozen", False))                  # en el exe no hay fuente .py: sin caché de numba
def _gr4j(P, E, x1, x2, x3, x4):
    n = len(P); S = 0.5 * x1; R = 0.5 * x3
    nh = int(math.ceil(x4)); nh2 = int(math.ceil(2 * x4))
    uh1 = np.zeros(nh); uh2 = np.zeros(nh2)
    for i in range(1, nh + 1):
        a = 1.0 if i >= x4 else (i / x4) ** 2.5; b = 0.0 if i - 1 <= 0 else (1.0 if i - 1 >= x4 else ((i - 1) / x4) ** 2.5); uh1[i - 1] = a - b
    for i in range(1, nh2 + 1):
        def_ = 0.0
        for j, ii in enumerate((i, i - 1)):
            if ii <= 0:
                v = 0.0
            elif ii < x4:
                v = 0.5 * (ii / x4) ** 2.5
            elif ii < 2 * x4:
                v = 1 - 0.5 * (2 - ii / x4) ** 2.5
            else:
                v = 1.0
            def_ = def_ + (v if j == 0 else -v)
        uh2[i - 1] = def_
    s1 = np.zeros(nh); s2 = np.zeros(nh2); Q = np.zeros(n)
    for t in range(n):
        p = P[t]; e = E[t]
        if p >= e:
            pn = p - e; ps = x1 * (1 - (S / x1) ** 2) * math.tanh(pn / x1) / (1 + (S / x1) * math.tanh(pn / x1)); es = 0.0
        else:
            pn = 0.0; en = e - p; es = S * (2 - S / x1) * math.tanh(en / x1) / (1 + (1 - S / x1) * math.tanh(en / x1)); ps = 0.0
        S = max(S + ps - es, 0.0)
        perc = S * (1 - (1 + (S / (4.0 / 9.0 * x1)) ** 4) ** -0.25); S = max(S - perc, 0.0)
        pr = perc + (pn - ps)
        for k in range(nh - 1):
            s1[k] = s1[k + 1]
        s1[nh - 1] = 0.0
        for k in range(nh2 - 1):
            s2[k] = s2[k + 1]
        s2[nh2 - 1] = 0.0
        for k in range(nh):
            s1[k] += 0.9 * pr * uh1[k]
        for k in range(nh2):
            s2[k] += 0.1 * pr * uh2[k]
        F = x2 * (R / x3) ** 3.5
        R = max(R + s1[0] + F, 0.0)
        qr = R * (1 - (1 + (R / x3) ** 4) ** -0.25); R -= qr
        Q[t] = qr + max(s2[0] + F, 0.0)
    return Q


def gr4j(P_mm, E_mm, x1, x2, x3, x4):
    """GR4J diario (Perrin, Michel y Andréassian 2003). P y E en mm/día; devuelve escorrentía en mm/día."""
    return _gr4j(np.asarray(P_mm, float), np.asarray(E_mm, float), float(x1), float(x2), float(x3), float(x4))


def _combinacion(carpeta, barrido_id=None, combo_id=None):
    carpeta = Path(carpeta)
    if barrido_id is None:
        acc = sorted((carpeta / "calibracion" / "aceptadas").glob("aceptada_*"))
        if not acc:
            raise K.CalibracionError("No hay calibración aceptada: indica un barrido y una combinación.")
        a = json.loads((acc[-1] / "aceptacion.json").read_text(encoding="utf-8")); return a["barrido"], a["combinacion"], "aceptada " + acc[-1].name
    res = pd.read_csv(carpeta / "calibracion" / "barridos" / barrido_id / "resultados.csv")
    f = res[res.id == int(combo_id or 0)]
    if f.empty:
        raise K.CalibracionError("Combinación no encontrada.")
    return barrido_id, f.iloc[0].replace({np.nan: None}).to_dict(), f"{barrido_id} id {int(combo_id or 0)}"


def correr(carpeta, pet_mm_d, barrido_id=None, combo_id=None, persona="", semilla=1, maxiter=25):
    """pet_mm_d: número (ETP constante declarada, mm/día) o «calibrada» (quinto parámetro, declarado como tal). Sin valor no se corre."""
    if pet_mm_d in (None, ""):
        raise K.CalibracionError("Declara la evapotranspiración potencial constante para GR4J (mm/día) o pide «calibrada»: el programa no la inventa.")
    pet_cal = str(pet_mm_d).strip().lower() == "calibrada"
    if not pet_cal:
        pet_mm_d = float(pet_mm_d)
        if not (0 <= pet_mm_d <= 10):
            raise K.CalibracionError("La ETP constante debe estar entre 0 y 10 mm/día.")
    carpeta = Path(carpeta)
    bar, comb, origen = _combinacion(carpeta, barrido_id, combo_id)
    fb = carpeta / "calibracion" / "barridos" / bar / "eventos.csv"
    tab = pd.read_csv(fb).fillna("").to_dict("records") if fb.exists() else None
    evs, excl, area, q, p, a, mq, mp_, tabla = K.preparar(carpeta, tab)
    dt_h = float(evs[0]["dt_h"])
    if dt_h < 24:
        raise K.CalibracionError("El benchmark GR4J es diario; esta calibración es horaria.")
    hum = comb.get("humedad") or "ninguna"
    prm = (float(comb["CN"]), float(comb["lag_h"]), float(comb["PRF"]), float(comb["lambda"]), None if comb.get("k_rec_d") in (None, "") else float(comb["k_rec_d"]), hum)
    filas = []
    r = K._evaluar(evs, prm, area, dt_h)
    filas.append({"modelo": "Modelo de eventos UCEclima (" + origen + ")", "tipo": "calibrado por la persona" if "aceptada" in origen else "combinación del barrido", **_plano(r)})
    base = {}
    for rol in ("ajuste", "validacion"):
        oo = [e["q"] for e in evs if e["rol"] == rol]
        base[rol] = K._metricas(np.concatenate(oo), np.concatenate([np.full(len(e["q"]), e["q"][0]) for e in evs if e["rol"] == rol])) if oo else None
    filas.append({"modelo": "Sin habilidad: caudal base constante del inicio del evento", "tipo": ETIQUETA, **_plano(base)})
    # GR4J continuo
    from scipy.optimize import differential_evolution
    qd = q.asfreq("D"); pd_ = p.asfreq("D"); idx = qd.index.intersection(pd_.dropna().index)
    ii = pd.date_range(idx.min(), idx.max(), freq="D"); Pm = pd_.reindex(ii).fillna(0).values; Qobs = qd.reindex(ii).values * 86.4 / area
    def mask(rol):
        m = np.zeros(len(ii), bool)
        for e in evs:
            if e["rol"] == rol:
                j = ii.get_indexer(e["fechas"]); m[j[j >= 0]] = True
        return m & np.isfinite(Qobs)
    ma, mv = mask("ajuste"), mask("validacion"); warm = min(365, len(Pm))
    def sim(th):
        Pw = np.concatenate([Pm[:warm], Pm]); pet = th[4] if pet_cal else pet_mm_d
        return gr4j(Pw, np.full(len(Pw), pet), *th[:4])[warm:]
    def fobj(th):
        k = K._metricas(Qobs[ma], sim(th)[ma])["KGE"]; return 1e3 if not np.isfinite(k) else -k
    lim = [(10, 2000), (-5, 5), (10, 500), (0.5, 5)] + ([(0.5, 5)] if pet_cal else [])
    t0 = time.time(); de = differential_evolution(fobj, lim, seed=semilla, maxiter=maxiter, popsize=8, tol=1e-3, polish=False); s = sim(de.x)
    gr = {rol: K._metricas(Qobs[m], s[m]) for rol, m in (("ajuste", ma), ("validacion", mv))}
    nombres = ["x1_mm", "x2_mm", "x3_mm", "x4_dias"] + (["ETP_mm_dia (calibrada)"] if pet_cal else [])
    params = dict(zip(nombres, [round(float(v), 3) for v in de.x]))
    if not pet_cal:
        params["ETP_mm_dia (declarada)"] = pet_mm_d
    filas.append({"modelo": "GR4J continuo diario" + (" (ETP calibrada)" if pet_cal else f" (ETP constante declarada {pet_mm_d:g} mm/día)"), "tipo": ETIQUETA, **_plano(gr), "parametros": json.dumps(params, ensure_ascii=False)})
    T = pd.DataFrame(filas)
    out = K._nueva(carpeta / "calibracion" / "benchmarks", "benchmark_")
    K._tablas(T.round(4), out / "benchmark")
    reg = {"creado": time.strftime("%Y-%m-%dT%H:%M:%S"), "persona": persona, "etiqueta": ETIQUETA, "barrido": bar, "origen_combinacion": origen, "pet": "calibrada" if pet_cal else pet_mm_d,
           "n_eventos": {"ajuste": sum(e["rol"] == "ajuste" for e in evs), "validacion": sum(e["rol"] == "validacion" for e in evs)}, "excluidos": excl,
           "metodo": "mismas ventanas de evento, misma lluvia areal y misma métrica (KGE, NSE, PBIAS agrupados por ventanas); GR4J con 1 año de calentamiento repetido; evolución diferencial "
                     f"(semilla {semilla}, maxiter {maxiter}, KGE de ajuste) en {time.time() - t0:.0f} s",
           "tabla": T.replace({np.nan: None}).to_dict("records"),
           "nota": "No se afirma que un modelo supera a otro salvo lo que muestre la tabla. GR4J y la base constante son referencias, no la calibración aceptada."}
    (out / "benchmark.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    reg["carpeta"] = str(out.relative_to(carpeta)).replace("\\", "/")
    return reg


def _plano(r):
    d = {}
    for rol in ("ajuste", "validacion"):
        m = r.get(rol) or {}
        for k in ("KGE", "NSE", "PBIAS_pct"):
            v = m.get(k); d[f"{k}_{rol}"] = None if v is None or not np.isfinite(v) else round(float(v), 4)
    return d
