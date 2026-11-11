# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Comparación numérica (mismas entradas) entre el hidro actual (climanet) y las funciones de matematica_propia.

SOLO LECTURA sobre el flujo: no modifica proyectos ni resultados de corridas; escribe una carpeta nueva con sello de tiempo.
Entradas del caso Mazar (reales del proyecto): tormenta de diseño X (IDF INAMHI, Tr 100, 180 min), CN medio del ráster de GEE,
área del recuadro AOI. Valores de ENSAYO declarados (no estimados, no calibrados): lag, tramo de tránsito (L, c, B, S0), X fijo.
No es un resultado hidrológico de Mazar y no afirma mejora ni calibración: solo cuantifica diferencias entre implementaciones.
"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]


def correr(proyecto=None, lags_h=(1.0, 2.0), prfs=(484.0, 284.0), tramo=None):
    import uceclima                                              # fija sys.path hacia el núcleo
    from climanet import hydrology as H, basin as B
    from uceclima import idf_x, matematica_propia as M
    import rasterio
    proyecto = Path(proyecto or RAIZ / "uceclima" / "proyectos" / "mazar")
    datos = json.loads((proyecto / "proyecto_uceclima.json").read_text(encoding="utf-8"))
    cfg = json.loads((proyecto / "config_climanet.json").read_text(encoding="utf-8"))
    tor = idf_x.calcular(datos, duracion_min=cfg.get("storm_min", 180), tr_tormenta=cfg.get("Tr", 100))["tormenta"]
    bloque_s = tor["bloque_min"] * 60.0
    bloques = np.asarray(tor["mm_por_bloque"], float)
    with rasterio.open(proyecto / cfg["cn_tif"]) as r:
        cn = float(r.read(1, masked=True).mean())
    x0, x1, y0, y1 = cfg["aoi"]; area = (x1 - x0) * (y1 - y0) / 1e6
    entradas = {"proyecto": datos["nombre"], "tormenta": f"Tr{tor['tr']} {tor['duracion_min']} min, modo {tor['modo']}", "P_total_mm": float(bloques.sum()),
                "bloque_min": tor["bloque_min"], "CN_medio_raster": round(cn, 2), "area_km2_recuadro_AOI": area,
                "nota": "CN medio y área del recuadro AOI (no hay cuenca delineada); lag y tramo son valores de ensayo."}
    filas = []
    dt_h = bloque_s / 3600.0
    pc = np.cumsum(bloques)
    pe = M.perdidas_scs(pc, cn)
    for lag in lags_h:
        for prf in prfs:
            res = {}
            for forma in ("gamma", "triangular"):
                t, q, info = H.scs_hydrograph(bloques, bloque_s, area, cn, lag_h=lag, prf=prf, forma=forma)
                res[f"hidro_actual_{forma}"] = (q, info["volumen_m3"])
            u = M.uh_scs(area, lag, dt_h, prf)
            c = M.convolver(pe["exceso_inc_mm"], u["u_m3s_mm"], dt_h)
            res["propia_triangular"] = (c["q_m3s"], c["volumen_m3"])
            for nombre, (q, v) in res.items():
                filas.append({"lag_h": lag, "PRF": prf, "implementacion": nombre, "Qpico_m3s": round(float(q.max()), 3), "Tpico_h": round(float(q.argmax() * dt_h + dt_h), 3),
                              "volumen_m3": round(float(v), 1), "exceso_mm": round(float(v / (area * 1000)), 4)})
    ref = {(f["lag_h"], f["PRF"]): f for f in filas if f["implementacion"] == "hidro_actual_triangular"}
    for f in filas:
        r = ref[(f["lag_h"], f["PRF"])]
        f["dQpico_vs_actual_triangular_%"] = round(100 * (f["Qpico_m3s"] / r["Qpico_m3s"] - 1), 3)
        f["dVolumen_vs_actual_triangular_%"] = round(100 * (f["volumen_m3"] / r["volumen_m3"] - 1), 4)

    # ---- tránsito: mismos c, B, S0, L y Δt; K,X fijos del núcleo vs Muskingum-Cunge
    tramo = tramo or {"L_m": 10000.0, "c_ms": 1.5, "ancho_m": 50.0, "s0": 0.001, "X_fijo": 0.2}
    q_in = np.r_[res["propia_triangular"][0], np.zeros(120)]
    dt_s = bloque_s
    mc = M.muskingum_cunge(q_in, dt_s, tramo["L_m"], tramo["c_ms"], tramo["ancho_m"], tramo["s0"], cola=False)
    diag = M.diagnostico_tramo(tramo["c_ms"], dt_s, tramo["L_m"], float(q_in.max()), tramo["ancho_m"], tramo["s0"])
    k_h = tramo["L_m"] / tramo["c_ms"] / 3600.0
    transito = []

    def anotar(nombre, q, extra):
        transito.append({"metodo": nombre, "Qpico_entrada_m3s": round(float(q_in.max()), 3), "Qpico_salida_m3s": round(float(q.max()), 3),
                         "atenuacion_%": round(100 * (1 - float(q.max()) / float(q_in.max())), 2), "retraso_pico_min": round((int(q.argmax()) - int(q_in.argmax())) * dt_s / 60, 1),
                         "volumen_salida/entrada": round(float(q.sum() / q_in.sum()), 5), **extra})
    for nombre, x in (("K,X fijos (X de ensayo)", tramo["X_fijo"]), ("K,X fijos con X=½(1−D) del pico", max(0.0, min(0.5, diag["X"])))):
        try:
            qo, inf = B.muskingum(q_in, dt_s, k_h, x, cola=False)
            anotar(f"hidro_actual: {nombre}", qo, {"X": round(x, 4), "K_h": round(k_h, 3), "subtramos": inf["n_subtramos"], "avisos": ""})
        except ValueError as e:
            transito.append({"metodo": f"hidro_actual: {nombre}", "avisos": "no admisible: " + str(e)[:120]})
    anotar("propia: Muskingum-Cunge (parámetros constantes)", mc["q_out_m3s"], {"X": round(diag["X"], 4), "K_h": round(diag["K_s"] / 3600, 3), "subtramos": 1,
                                                                              "avisos": "; ".join(mc["avisos"] + diag["banderas"])})
    return {"entradas": entradas, "tramo_ensayo": tramo, "uh": filas, "transito": transito, "diagnostico_tramo": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in diag.items()}}


def escribir(res, destino=None):
    destino = Path(destino or RAIZ / "comparaciones" / f"matematica_propia_{time.strftime('%Y%m%d_%H%M%S')}")
    destino.mkdir(parents=True, exist_ok=False)
    for nombre in ("uh", "transito"):
        cols = list({k: 0 for f in res[nombre] for k in f})
        with open(destino / f"{nombre}.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(res[nombre])
    (destino / "comparacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


if __name__ == "__main__":
    r = correr()
    d = escribir(r)
    print(json.dumps(r["entradas"], ensure_ascii=False, indent=1))
    for f in r["uh"]:
        print(f)
    for f in r["transito"]:
        print(f)
    print("diag:", r["diagnostico_tramo"]); print("carpeta:", d)
