# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Benchmark Gamma (SCS-CN evento) vs GR4J continuo vs referencia sin habilidad, mismos eventos/forzamiento/metrica.
Solo lectura sobre los proyectos; resultados a la carpeta scratchpad."""
import sys, json, math
sys.path.insert(0, r"C:\Users\agdgq\UCEclima"); sys.path.insert(0, r"C:\Users\agdgq\climanet")
import numpy as np, pandas as pd
from scipy.optimize import differential_evolution
from uceclima import calibracion as C

P = r"C:\Users\agdgq\Documents\UCEclima_proyectos"
CASOS = {"Chalpi H13": P + r"\practica1_epmaps_quitoucec", "Tambo H18": P + r"\tambo_h18_epmapsucec"}
OUT = r"C:\Users\agdgq\AppData\Local\Temp\claude\c--Users-agdgq-MILAGRO\d5e3fcb5-058a-41e2-821c-80ebaea99953\scratchpad"


def gr4j(P_mm, E_mm, x1, x2, x3, x4):
    """GR4J diario (Perrin et al. 2003). Devuelve escorrentia mm/dia."""
    n = len(P_mm); S = 0.5 * x1; R = 0.5 * x3
    nh = int(math.ceil(x4)); nh2 = int(math.ceil(2 * x4))
    def sh1(i): return 0.0 if i <= 0 else (1.0 if i >= x4 else (i / x4) ** 2.5)
    def sh2(i):
        if i <= 0: return 0.0
        if i < x4: return 0.5 * (i / x4) ** 2.5
        if i < 2 * x4: return 1 - 0.5 * (2 - i / x4) ** 2.5
        return 1.0
    uh1 = np.array([sh1(i) - sh1(i - 1) for i in range(1, nh + 1)])
    uh2 = np.array([sh2(i) - sh2(i - 1) for i in range(1, nh2 + 1)])
    s1 = np.zeros(nh); s2 = np.zeros(nh2); Q = np.zeros(n)
    for t in range(n):
        p, e = P_mm[t], E_mm[t]
        if p >= e:
            pn = p - e; en = 0.0
            ps = x1 * (1 - (S / x1) ** 2) * math.tanh(pn / x1) / (1 + (S / x1) * math.tanh(pn / x1))
            es = 0.0
        else:
            pn = 0.0; en = e - p
            es = S * (2 - S / x1) * math.tanh(en / x1) / (1 + (1 - S / x1) * math.tanh(en / x1)); ps = 0.0
        S = max(S + ps - es, 0.0)
        perc = S * (1 - (1 + (S / (4.0 / 9.0 * x1)) ** 4) ** -0.25)
        S = max(S - perc, 0.0)
        pr = perc + (pn - ps)
        s1 = np.roll(s1, -1); s1[-1] = 0.0; s1 += 0.9 * pr * uh1
        s2 = np.roll(s2, -1); s2[-1] = 0.0; s2 += 0.1 * pr * uh2
        F = x2 * (R / x3) ** 3.5
        R = max(R + s1[0] + F, 0.0)
        qr = R * (1 - (1 + (R / x3) ** 4) ** -0.25); R -= qr
        qd = max(s2[0] + F, 0.0)
        Q[t] = qr + qd
    return Q


def kge(o, s):
    return C._metricas(o, s)["KGE"]


def correr(nombre, carpeta):
    from pathlib import Path
    acc = json.loads(next(Path(carpeta, "calibracion", "aceptadas").glob("*/aceptacion.json")).read_text(encoding="utf-8"))
    cb = acc["combinacion"]
    # misma tabla de eventos que uso la persona al aceptar (barrido citado en la aceptacion)
    fb = Path(carpeta, "calibracion", "barridos", acc["barrido"], "eventos.csv")
    tab = pd.read_csv(fb).fillna("").to_dict("records") if fb.exists() else None
    print(nombre, "tabla del barrido aceptado:", fb.name if tab else "NO encontrada (se usa la propuesta por defecto)", acc["barrido"])
    evs, excl, area, q, p, a, mq, mp_, tabla = C.preparar(carpeta, tab)
    prm = (cb["CN"], cb["lag_h"], cb["PRF"], cb["lambda"])
    res = {"caso": nombre, "area_km2": area, "n_ajuste": sum(e["rol"] == "ajuste" for e in evs), "n_val": sum(e["rol"] == "validacion" for e in evs),
           "aceptado_gamma": {"KGE_a": cb["KGE_ajuste"], "KGE_v": cb["KGE_validacion"], "NSE_a": cb["NSE_ajuste"], "NSE_v": cb["NSE_validacion"]}}
    # 1) Gamma reproducido
    r = C._evaluar(evs, prm, area, 24.0)
    res["Gamma"] = {k: r[k] for k in ("ajuste", "validacion")}
    # 2) referencia sin habilidad: caudal base inicial constante
    base = {}
    for rol in ("ajuste", "validacion"):
        oo = np.concatenate([e["q"] for e in evs if e["rol"] == rol]); ss = np.concatenate([np.full(len(e["q"]), e["q"][0]) for e in evs if e["rol"] == rol])
        base[rol] = C._metricas(oo, ss)
    res["Base constante (sin habilidad)"] = base
    # 3) GR4J continuo: lluvia areal y caudal diarios, PET constante calibrada
    qd = q.asfreq("D"); pd_ = p.asfreq("D")
    idx = qd.index.intersection(pd_.dropna().index)
    ini, fin = idx.min(), idx.max()
    ii = pd.date_range(ini, fin, freq="D")
    Pm = pd_.reindex(ii).fillna(0).values
    Qm = qd.reindex(ii)
    conv = 86.4 / area  # m3/s -> mm/dia
    Qobs_mm = Qm.values * conv
    # mascaras de eventos
    def mask(rol):
        m = np.zeros(len(ii), bool)
        for e in evs:
            if e["rol"] == rol:
                m[ii.get_indexer(e["fechas"])] = True
        return m
    ma, mv = mask("ajuste"), mask("validacion")
    ma &= np.isfinite(Qobs_mm); mv &= np.isfinite(Qobs_mm)
    warm = 365

    def sim(th):
        x1, x2, x3, x4, pet = th
        # arranque: un anio previo repetido como calentamiento
        Pw = np.concatenate([Pm[:warm], Pm]); Ew = np.full(len(Pw), pet)
        return gr4j(Pw, Ew, x1, x2, x3, x4)[warm:]

    def fobj(th):
        s = sim(th)
        k = kge(Qobs_mm[ma], s[ma])
        return 1e3 if not np.isfinite(k) else -k
    lim = [(10, 2000), (-5, 5), (10, 500), (0.5, 5), (0.5, 5)]
    de = differential_evolution(fobj, lim, seed=1, maxiter=25, popsize=8, tol=1e-3, polish=False)
    s = sim(de.x)
    gr = {}
    for rol, m in (("ajuste", ma), ("validacion", mv)):
        gr[rol] = C._metricas(Qobs_mm[m], s[m])
    gr["params"] = dict(zip(["x1", "x2", "x3", "x4", "PET_mm_d"], [round(float(v), 3) for v in de.x]))
    res["GR4J continuo (5 parametros)"] = gr
    # 4) GR4J con volumen total (dia completo) en validacion continua
    res["_nota"] = "metrica agrupada sobre ventanas de evento, igual que Gamma (calibracion._evaluar)"
    return res


if __name__ == "__main__":
    todo = [correr(n, c) for n, c in CASOS.items()]
    pd.to_pickle(todo, OUT + r"\bench.pkl")
    def f(m): return {k: round(v, 3) for k, v in m.items() if k in ("NSE", "KGE", "PBIAS_pct")}
    for r in todo:
        print("====", r["caso"], f"area {r['area_km2']:.1f} km2 | eventos ajuste {r['n_ajuste']} / validacion {r['n_val']}")
        print("  Gamma aceptado (guardado):", r["aceptado_gamma"])
        for k, v in r.items():
            if isinstance(v, dict) and "ajuste" in v:
                print(f"  {k:34s} ajuste {f(v['ajuste'])}  validacion {f(v['validacion'])}")
        print("  GR4J params:", r["GR4J continuo (5 parametros)"]["params"])
