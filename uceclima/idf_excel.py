# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Auditoría reproducible del Excel IDF (atribución aportada por el usuario: Caiza 2026) y recomputo independiente en Python.

NO sustituye la IDF oficial del libro INAMHI: documenta qué contiene el archivo, recalcula su cadena de métodos y compara con sus celdas.
Cadena del libro de Excel (verificada leyendo fórmulas): máximos anuales de 24 h (mm) -> Gumbel por momentos -> factor de intervalo fijo 1,13
-> coeficientes de duración de D. F. Campos (1978) -> intensidades -> regresión potencial I = d·t^n por Tr -> I = K·T^m / t^|n|.
"""
import hashlib, json, math
from pathlib import Path
import numpy as np
import openpyxl

ATRIBUCION = {"autor_aportado_por_usuario": "Caiza 2026", "referencia_bibliografica": "pendiente (no verificada)",
              "fuente_declarada_por_usuario": "IDF INAMHI M0037",
              "nota": "La atribución es la indicada por el usuario; el contenido del archivo se audita aparte."}
COEF_CAMPOS = {1: .30, 2: .39, 3: .46, 4: .52, 5: .57, 6: .61, 8: .68, 12: .80, 18: .91, 24: 1.0}      # Tabla Pd del libro (Campos 1978)
FACTOR_INTERVALO_FIJO = 1.13                                                                           # factor de intervalo fijo (Weiss) declarado en la hoja
TR_EXCEL = (2, 5, 10, 25)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def gumbel_momentos(x, T, factor=FACTOR_INTERVALO_FIJO):
    """XT = (u + α·YT)·factor, α = sqrt(6)/π·s (s con n-1), u = media − 0,5772·α  (las constantes de la hoja)."""
    x = np.asarray(x, float); s = x.std(ddof=1); alfa = math.sqrt(6) / math.pi * s; u = x.mean() - 0.5772 * alfa
    yt = -np.log(np.log(np.asarray(T, float) / (np.asarray(T, float) - 1)))
    return (u + alfa * yt) * factor, {"media_mm": float(x.mean()), "desv_n-1_mm": float(s), "alfa": float(alfa), "u": float(u)}


def recomputar(x, tr=TR_EXCEL):
    """Cadena completa desde los máximos anuales. Devuelve parámetros y la función I(T, t_min)."""
    XT, par = gumbel_momentos(x, tr)
    horas = sorted(COEF_CAMPOS, reverse=True)
    t_min = np.array([h * 60 for h in horas], float)
    d, n = [], []
    for k, T in enumerate(tr):
        I = np.array([XT[k] * COEF_CAMPOS[h] / h for h in horas])             # mm/h
        b, a = np.polyfit(np.log(t_min), np.log(I), 1)                          # ln I = ln d + n·ln t
        d.append(math.exp(a)); n.append(b)
    m, lnK = np.polyfit(np.log(np.asarray(tr, float)), np.log(np.asarray(d)), 1)
    K = math.exp(lnK); n_prom = float(np.mean(n))
    f = lambda T, t: K * np.asarray(T, float) ** m / np.asarray(t, float) ** (-n_prom)
    return {"gumbel": par, "XT_mm": dict(zip(map(int, tr), map(float, XT))), "d": d, "n": n, "K": K, "m": float(m), "n_prom": n_prom}, f


def auditar(path):
    """Lee fórmulas y valores en caché y recomputa. Devuelve un dict serializable con hallazgos."""
    path = Path(path)
    wf = openpyxl.load_workbook(path, data_only=False); wv = openpyxl.load_workbook(path, data_only=True)
    rep = {"archivo": str(path), "sha256": sha256(path), "bytes": path.stat().st_size, "atribucion": ATRIBUCION,
           "propiedades": {"creador": wf.properties.creator, "modificado_por": wf.properties.lastModifiedBy,
                           "creado": str(wf.properties.created), "modificado": str(wf.properties.modified)}, "hojas": []}
    for ws in wf.worksheets:
        nform = sum(1 for r in ws.iter_rows() for c in r if isinstance(c.value, str) and c.value.startswith("="))
        nval = sum(1 for r in ws.iter_rows() for c in r if c.value is not None)
        rep["hojas"].append({"nombre": ws.title, "dimensiones": ws.dimensions, "celdas_con_valor": nval, "formulas": nform,
                             "graficos": len(getattr(ws, "_charts", [])), "imagenes": len(getattr(ws, "_images", []))})
    H = "Registros Pluviómetro"; ws, wsv = wf[H], wv[H]
    titulo = str(ws["A1"].value)
    anios, maximos = [], []
    for r in range(4, 40):
        a, v = wsv.cell(r, 1).value, wsv.cell(r, 14).value
        if isinstance(a, (int, float)) and isinstance(v, (int, float)):
            anios.append(int(a)); maximos.append(float(v))
    rep["serie"] = {"hoja": H, "rango": f"A4:A{3 + len(anios)} / N (máx. anual)", "titulo_hoja": titulo, "unidades": "mm (máximo de 24 h por mes y por año)",
                    "n_anios": len(anios), "anios": [anios[0], anios[-1]], "maximo_mm": max(maximos), "tipo_registro": "pluviómetro (24 h); NO pluviógrafo subdiario"}
    x = np.array(maximos)
    # ---- celdas en caché de cada paso
    P = wv["Precip. Máx. Probable"]; PF = wf["Precip. Máx. Probable"]
    cache = {"media_mm": P["C41"].value, "desv_mm": P["C47"].value, "alfa": P["C50"].value, "u": P["C53"].value,
             "XT_corregido": {int(P.cell(r, 6).value): P.cell(r, 10).value for r in range(44, 53)}}
    rep["formulas_clave"] = {"media": str(PF["C41"].value), "desviacion": str(PF["C47"].value), "alfa": str(PF["C50"].value), "u": str(PF["C53"].value),
                             "XT_sin_corregir": str(PF["H45"].value), "XT_corregido": str(PF["J45"].value)}
    par, f = recomputar(x)
    cmp_ = {}
    def rel(a, b): return abs(a - b) / max(abs(b), 1e-12)
    cmp_["media"] = rel(par["gumbel"]["media_mm"], cache["media_mm"]); cmp_["desv"] = rel(par["gumbel"]["desv_n-1_mm"], cache["desv_mm"])
    cmp_["alfa"] = rel(par["gumbel"]["alfa"], cache["alfa"]); cmp_["u"] = rel(par["gumbel"]["u"], cache["u"])
    for T in TR_EXCEL: cmp_[f"XT_T{T}"] = rel(par["XT_mm"][T], cache["XT_corregido"][T])
    R = wv["Cte. Regresión Cuenca"]
    for k, T in enumerate(TR_EXCEL):
        cmp_[f"d_T{T}"] = rel(par["d"][k], R.cell(5 + k, 5).value); cmp_[f"n_T{T}"] = rel(par["n"][k], R.cell(5 + k, 7).value)
    cmp_["K"] = rel(par["K"], R["G23"].value); cmp_["m"] = rel(par["m"], R["I23"].value)
    # ---- tabla final de la hoja 'Curvas IDF Cuenca'
    C = wv["Curvas IDF Cuenca"]
    dur = [C.cell(12, c).value for c in range(3, 60) if isinstance(C.cell(12, c).value, (int, float))]
    filas = []
    for r in range(13, 40):
        T = C.cell(r, 2).value
        if not isinstance(T, (int, float)): break
        vals = [C.cell(r, 3 + j).value for j in range(len(dur))]
        if any(not isinstance(v, (int, float)) for v in vals): continue
        filas.append((int(T), vals))
    tabla = {"duraciones_min": dur, "Tr": [t for t, _ in filas], "i_mm_h": [v for _, v in filas]}
    cmp_["tabla_final_max_dif_rel"] = max((rel(float(f(T, dur[j])), vals[j]) for T, vals in filas for j in range(len(dur))), default=None)
    rep["recomputo"] = {"parametros": par, "comparacion_con_celdas_en_cache(dif_relativa)": cmp_, "max_dif_relativa": max(v for v in cmp_.values() if v is not None),
                        "tolerancia": 1e-6}
    rep["ecuacion_final"] = f"I = {par['K']:.4f}·T^{par['m']:.5f} / t^{-par['n_prom']:.5f}   (I mm/h, T años, t min)"
    rep["tabla_final_hoja"] = tabla
    rep["seleccion_distribucion"] = {"hoja": "KOLMOGOROV - SMIRNOV", "texto": str(wv["KOLMOGOROV - SMIRNOV"]["B70"].value),
                                     "delta_max": {"Gumbel": wv["KOLMOGOROV - SMIRNOV"]["B65"].value, "LogNormal": wv["KOLMOGOROV - SMIRNOV"]["C65"].value,
                                                   "PearsonIII": wv["KOLMOGOROV - SMIRNOV"]["D65"].value}, "delta_0": wv["KOLMOGOROV - SMIRNOV"]["B66"].value}
    # ---- hallazgos
    h = []
    h.append(f"Etiqueta de estación inconsistente: la hoja '{H}' dice «{titulo}» (CUMBE) mientras el archivo se llama M0037 (INAMHI). "
             "El usuario indicó el 13-oct-2026 que CUMBE corresponde a Milagro (afirmación del usuario; sin documento que la respalde todavía). "
             "El M0037 del libro INAMHI es Milagro-Ingenio Valdez y su curva difiere de la del Excel: se conservan como fuentes separadas.")
    h.append("Los datos son máximos de 24 h de un pluviómetro (1985–2015): no hay lluvia subdiaria medida. Las intensidades de 1 a 24 h salen de los coeficientes de "
             "Campos (1978) y las de 5–60 min de extrapolar la regresión potencial: son estimaciones, no observaciones de pluviógrafo.")
    h.append(f"Factor de intervalo fijo {FACTOR_INTERVALO_FIJO} aplicado a todo XT (hoja 'Precip. Máx. Probable', columna J): es una corrección estadística, no un factor climático.")
    try:
        lab = [int(P.cell(r, 3).value) for r in range(6, 37)]
        if lab != sorted(lab) or len(set(lab)) != len(lab):
            rep_rows = [(r, P.cell(r, 3).value, PF.cell(r, 3).value) for r in range(6, 37) if (r > 6 and P.cell(r, 3).value != P.cell(r - 1, 3).value + 1)]
            h.append(f"Etiquetas de año desordenadas/duplicadas en 'Precip. Máx. Probable' (celdas C34-C36 referencian filas distintas de las de D): {rep_rows}; "
                     "los valores de precipitación no cambian, solo el rótulo del año.")
    except Exception:
        pass
    h.append("Las constantes K y m se ajustan solo con Tr = 2, 5, 10 y 25 años; usar la ecuación para Tr 50 o 100 es extrapolación.")
    h.append("Seleccionada la distribución de Gumbel por Kolmogorov-Smirnov (Δmax menor); ninguna prueba demuestra por sí sola idoneidad para extremos.")
    h.append("Las hojas contienen gráficos e imágenes que no se auditaron visualmente.")
    rep["hallazgos"] = h
    return rep


def idf_dataframe(rep):
    """IDF de la hoja 'Curvas IDF Cuenca' como DataFrame (filas Tr, columnas min, mm/h) para DisenoIDF. Fuente: Excel (estación rotulada CUMBE), NO el libro INAMHI."""
    import pandas as pd
    t = rep["tabla_final_hoja"]
    return pd.DataFrame(t["i_mm_h"], index=t["Tr"], columns=[int(d) for d in t["duraciones_min"]])


def comparar_con_libro_inamhi(tabla_hoja, estacion="M0037"):
    """Compara la tabla del Excel con el cuadro IDF del libro INAMHI (climanet.inamhi) en Tr y duraciones comunes."""
    from climanet import inamhi
    libro = inamhi.idf_estacion(estacion)
    filas = []
    for T, vals in zip(tabla_hoja["Tr"], tabla_hoja["i_mm_h"]):
        for d, v in zip(tabla_hoja["duraciones_min"], vals):
            if T in libro.index and d in libro.columns:
                filas.append({"Tr": T, "duracion_min": d, "excel_mm_h": v, "libro_mm_h": float(libro.loc[T, d]), "excel/libro": v / float(libro.loc[T, d])})
    return filas


if __name__ == "__main__":
    import sys
    ruta = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\agdgq\Desktop\Curva-IDF-de-M0037 - INAMHI.xlsx"
    out = Path(__file__).parent / "auditoria"; out.mkdir(exist_ok=True)
    rep = auditar(ruta)
    try:
        rep["comparacion_con_libro_inamhi_M0037"] = comparar_con_libro_inamhi(rep["tabla_final_hoja"])
    except Exception as e:
        rep["comparacion_con_libro_inamhi_M0037"] = f"no disponible: {e}"
    (out / "M0037_excel_auditoria.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("sha256", "serie", "ecuacion_final")}, indent=1, ensure_ascii=False, default=str))
    print("máx. dif. relativa recomputo vs celdas:", rep["recomputo"]["max_dif_relativa"])
    for h_ in rep["hallazgos"]: print(" -", h_)
