# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Eta 9.0.0 · «Analizar extremos» (módulo 9) y paquete CMIP6 del territorio.

Pedido del usuario en la prueba de novato con el río Yaguachi (1-nov-2026): la serie anual del ensamble muestra la tendencia pero no los
años extremos tipo El Niño que sí se ven en CHIRPS. El promedio de 28 modelos los cancela, porque cada modelo tiene sus años extremos en
fechas distintas. Esta capa NO cambia Y ni los factores; usa los datos ya descargados (tabla cmip6_series y CHIRPS de la base del proyecto):

1. el mejor modelo, uno solo, con sus propios picos;
2. el umbral de «año extremo» = percentil p90 (o p95) del máximo diario anual de CHIRPS 1981–2014, y los años que lo superan;
3. la frecuencia de años extremos por década: CHIRPS frente a los modelos (porcentaje ponderado con los pesos ClimWIP).

Mensaje: el año exacto no se puede predecir; sí cuántos años extremos llegan por década. SSP5-8.5, no calibrado ni validado, no es predicción.
"""
import json, shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import basedatos as BD

AVISO = "Proyección SSP5-8.5 con CMIP6 NEX-GDDP corregido (QQM/QDM) y pesos ClimWIP. No calibrado ni validado; no es predicción: el año exacto de un extremo no se puede predecir."


class ExtremosError(ValueError):
    pass


def _carpeta_resultados(proyecto):
    base = Path(proyecto) / "resultados" / f"cmip6_{datetime.now():%Y%m%d}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _q_ponderado(v, w, q):
    ok = np.isfinite(v)
    if not ok.any():
        return np.nan
    o = np.argsort(v[ok]); cw = np.cumsum(w[ok][o]); cw = cw / cw[-1]
    return float(np.interp(q, cw, v[ok][o]))


def datos(proyecto, referencia="chirps:celda_nex_mm"):
    """Máximo diario anual de CHIRPS y de cada modelo corregido (histórico + SSP5-8.5), con sus pesos."""
    if not BD.ruta(proyecto).exists():
        raise ExtremosError("El proyecto no tiene base de datos: corre los pasos 1 a 5 del módulo 9 (el paso 5 sincroniza la base).")
    c = BD.abrir(proyecto, solo_lectura=True)
    try:
        ch = pd.read_sql("SELECT fecha, mm FROM referencia_lluvia WHERE serie = ?", c, params=(referencia,), parse_dates=["fecha"])
        s = pd.read_sql("SELECT modelo, escenario, CAST(SUBSTR(fecha,1,4) AS INTEGER) AS anio, MAX(pr_corregida_mm) AS rx1 FROM cmip6_series GROUP BY modelo, escenario, anio", c)
        m = pd.read_sql("SELECT modelo, posicion, peso FROM cmip6_modelos WHERE seleccionado = 1", c).set_index("modelo")
    except Exception as e:
        raise ExtremosError(f"No se pudo leer la base del proyecto ({str(e)[:120]}). Corre el paso 5 «Sincronizar base de datos».")
    finally:
        c.close()
    if ch.empty:
        raise ExtremosError(f"No hay serie de referencia «{referencia}» en la base: corre el paso 2 y luego el 5.")
    fut = set(s.loc[s.escenario == "ssp585", "modelo"])
    if not fut:
        raise ExtremosError("Todavía no hay futuro SSP5-8.5 descargado: corre el paso 3 (y el 5 para sincronizar).")
    mods = [x for x in m.sort_values("posicion").index if x in fut]
    if not mods:
        raise ExtremosError("Ningún modelo seleccionado tiene futuro descargado.")
    ch = ch[ch.fecha.dt.year <= datetime.now().year - 1]
    ams = ch.groupby(ch.fecha.dt.year)["mm"].max()
    P = s[s.modelo.isin(mods)].pivot_table(index="anio", columns="modelo", values="rx1", aggfunc="max")[mods]
    w = m.loc[mods, "peso"].astype(float).fillna(0).values
    w = w / w.sum() if w.sum() > 0 else np.full(len(mods), 1 / len(mods))
    return ams, P, w, mods


def analizar(proyecto, percentil=90, referencia="chirps:celda_nex_mm"):
    if int(percentil) not in (90, 95):
        raise ExtremosError("El umbral solo puede ser p90 (por defecto) o p95 de CHIRPS 1981–2014.")
    ams, P, w, mods = datos(proyecto, referencia)
    base = ams.loc[1981:2014]
    if len(base) < 20:
        raise ExtremosError(f"CHIRPS 1981–2014 tiene solo {len(base)} años en la base: no alcanza para fijar el umbral.")
    umbral = float(np.quantile(base.values, percentil / 100))           # solo con 1981–2014 (la línea base de la corrección)
    mejor = mods[0]
    supera = (P > umbral).astype(float).where(P.notna())
    frac = supera.fillna(0).mul(w, axis=1).sum(axis=1) / P.notna().mul(w, axis=1).sum(axis=1).replace(0, np.nan)
    dec = lambda x: np.minimum((np.asarray(x) // 10) * 10, 2090)            # 2100 (un solo año) entra en la década 2090
    f_mod = (frac.groupby(dec(frac.index)).mean() * 100).rename("modelos_pct")
    f_ch = ((ams > umbral).astype(float).groupby(dec(ams.index)).mean() * 100).rename("chirps_pct")
    n_ch = ams.groupby(dec(ams.index)).size().rename("chirps_anios")
    tabla_dec = pd.concat([f_ch, n_ch, f_mod], axis=1).reset_index().rename(columns={"index": "decada"})
    filas = []
    for a in P.index:
        v = P.loc[a].values.astype(float)
        filas.append({"anio": int(a), "chirps_rx1_mm": float(ams.get(a, np.nan)), "chirps_supera": bool(ams.get(a, -1) > umbral) if a in ams.index else None,
                      "mediana_ponderada_mm": _q_ponderado(v, w, .5), "p10_mm": _q_ponderado(v, w, .1), "p90_mm": _q_ponderado(v, w, .9),
                      f"mejor_modelo_mm": float(P.loc[a, mejor]) if np.isfinite(P.loc[a, mejor]) else None, "mejor_modelo_supera": bool(P.loc[a, mejor] > umbral) if np.isfinite(P.loc[a, mejor]) else None,
                      "fraccion_modelos_sobre_umbral": float(frac.get(a, np.nan))})
    por_anio = pd.DataFrame(filas)
    out = _carpeta_resultados(proyecto) / f"extremos_p{percentil}_{datetime.now():%H%M%S}"
    out.mkdir(parents=True)
    por_anio.to_csv(out / "extremos_por_anio.csv", index=False, encoding="utf-8")
    tabla_dec.to_csv(out / "frecuencia_por_decada.csv", index=False, encoding="utf-8")
    fig = figura(ams, P, w, mejor, umbral, percentil, f_ch, f_mod, out / "extremos.png", len(mods))
    hist = float(frac.loc[1981:2014].mean() * 100)
    fut_ = {int(k): round(float(v), 1) for k, v in f_mod.items() if k >= 2020}
    n_fut_mejor = int((P.loc[2015:, mejor] > umbral).sum())
    resumen = {"creado": datetime.now().isoformat(timespec="seconds"), "percentil": int(percentil), "umbral_mm_dia": round(umbral, 1), "referencia": referencia,
               "mejor_modelo": mejor, "n_modelos": len(mods), "frecuencia_chirps_base_pct": round(float((base > umbral).mean() * 100), 1),
               "frecuencia_modelos_historico_pct": round(hist, 1), "frecuencia_modelos_por_decada_pct": fut_,
               "frecuencia_chirps_por_decada_pct": {int(k): round(float(v), 1) for k, v in f_ch.items()},
               "anios_mejor_modelo_sobre_umbral_2015_2100": n_fut_mejor, "anios_futuros": int(P.loc[2015:].shape[0]),
               "carpeta": str(out.relative_to(proyecto)).replace("\\", "/"), "figura": str(fig.relative_to(proyecto)).replace("\\", "/"), "aviso": AVISO}
    resumen["lectura"] = [
        f"Umbral de año extremo: {resumen['umbral_mm_dia']} mm en un día (p{percentil} del máximo diario anual de CHIRPS 1981–2014). Por construcción, CHIRPS lo supera en cerca del {100 - percentil} % de los años de la línea base ({resumen['frecuencia_chirps_base_pct']} %).",
        f"Los modelos, en el histórico, lo superan en el {resumen['frecuencia_modelos_historico_pct']} % de los años: " + ("subestiman los extremos (coherente con una razón de varianza menor que 1)." if hist < (100 - percentil) * 0.8 else "parecido a CHIRPS."),
        "Frecuencia futura (SSP5-8.5, % de años por década): " + ", ".join(f"{k}s {v} %" for k, v in fut_.items()) + ".",
        f"El mejor modelo ({mejor}), solo, supera el umbral en {n_fut_mejor} de {resumen['anios_futuros']} años futuros: así se ven sus picos, que el promedio esconde.",
        "El año exacto de un extremo no se puede predecir; lo que sí da CMIP6 es cuántos años extremos llegan por década."]
    (out / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "LEEME.md").write_text("# Extremos CMIP6 (UCEclima Lambda)\n\n" + "\n".join("- " + l for l in resumen["lectura"]) +
                                  f"\n\n**Archivos:** `extremos_por_anio.csv` (máximo diario anual por año: CHIRPS, mediana y p10–p90 ponderados, mejor modelo y fracción ponderada de modelos sobre el umbral), "
                                  f"`frecuencia_por_decada.csv` y `extremos.png`.\n\n**Método:** umbral = p{percentil} del máximo diario anual de CHIRPS 1981–2014; pesos ClimWIP; décadas con 2100 dentro de 2090.\n\n{AVISO}\n", encoding="utf-8")
    return resumen


def figura(ams, P, w, mejor, umbral, percentil, f_ch, f_mod, ruta, n):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.style.use("default")
    med = P.apply(lambda r: _q_ponderado(r.values.astype(float), w, .5), axis=1); p10 = P.apply(lambda r: _q_ponderado(r.values.astype(float), w, .1), axis=1)
    p90 = P.apply(lambda r: _q_ponderado(r.values.astype(float), w, .9), axis=1)
    AZ, AZ2, MG = "#1F4E79", "#2E75B6", "#C2185B"
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={"height_ratios": [3, 2]})
    a1.fill_between(P.index, p10, p90, color=MG, alpha=.13, label=f"p10–p90 de {n} modelos")
    a1.plot(med.index, med, color=MG, lw=2.2, label="mediana ponderada (la tendencia)")
    a1.plot(P.index, P[mejor], color=AZ2, lw=1, alpha=.9, label=f"mejor modelo uno solo ({mejor}): sus propios picos")
    ex = P[mejor] > umbral
    a1.scatter(P.index[ex], P[mejor][ex], color=AZ2, s=26, zorder=5)
    a1.plot(ams.index, ams.values, color="black", lw=1.8, label="CHIRPS observado")
    a1.scatter(ams.index[ams > umbral], ams[ams > umbral], color="black", s=28, zorder=6)
    a1.axhline(umbral, color="#E0A100", ls="--", lw=1.4, label=f"umbral de año extremo = p{percentil} de CHIRPS 1981–2014 ({umbral:.0f} mm/día)")
    a1.axvline(2014.5, color="grey", ls=":", lw=1)
    a1.set_ylabel("lluvia máxima de 1 día del año (mm)"); a1.set_xlim(1980, 2101)
    a1.set_title("Máximo diario anual: tendencia (mediana) y extremos (un modelo solo y umbral)", color=AZ, loc="left")
    a1.legend(fontsize=8.5, loc="upper left", ncol=2, frameon=False); a1.grid(alpha=.3)
    x = np.array(f_mod.index); a2.bar(x + 2, f_mod.values, width=4, color=MG, alpha=.75, label="modelos (histórico y SSP5-8.5, ponderado)")
    a2.bar(np.array(f_ch.index) - 2, f_ch.values, width=4, color="black", alpha=.8, label="CHIRPS observado")
    a2.axhline(100 - percentil, color="#E0A100", ls="--", lw=1.2, label=f"{100 - percentil} % = frecuencia de referencia 1981–2014")
    for xi, v in zip(x, f_mod.values): a2.text(xi + 2, v + 1, f"{v:.0f}", ha="center", fontsize=8, color=MG)
    for xi, v in zip(f_ch.index, f_ch.values): a2.text(xi - 2, v + 1, f"{v:.0f}", ha="center", fontsize=8)
    a2.set_ylabel("% de años sobre el umbral"); a2.set_xlabel("década")
    a2.set_title("¿Cada cuánto llega un año extremo? (el año exacto no se puede predecir)", color=AZ, loc="left")
    a2.legend(fontsize=8.5, frameon=False, loc="upper left"); a2.grid(alpha=.3, axis="y"); a2.set_xlim(1975, 2105)
    fig.text(.01, .005, "UCEclima Lambda · " + AVISO, fontsize=7.2, color="grey")
    plt.tight_layout(rect=[0, .02, 1, 1]); fig.savefig(ruta, dpi=150, facecolor="white"); plt.close(fig)
    return ruta


def ultimo(proyecto):
    l = sorted(Path(proyecto).glob("resultados/cmip6_*/extremos_p*/resumen.json"))
    return json.loads(l[-1].read_text(encoding="utf-8")) if l else None


def exportar_paquete(proyecto):
    """Eta (punto 26b): junta en resultados/cmip6_<fecha>/paquete_<hora>/ todo lo de CMIP6 del territorio, con LEEME y Excel resumen.
    Copia (no mueve) lo que ya está en datos_descargados/ y registro/: los datos crudos no se tocan."""
    proyecto = Path(proyecto); out = _carpeta_resultados(proyecto) / f"paquete_{datetime.now():%H%M%S}"; out.mkdir(parents=True)
    hechos = []
    def copiar(origen, destino):
        if origen and Path(origen).exists():
            if Path(origen).is_dir(): shutil.copytree(origen, out / destino)
            else: (out / destino).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(origen, out / destino)
            hechos.append(destino)
    ult = lambda pat: (sorted(proyecto.glob(pat)) or [None])[-1]
    copiar(ult("datos_descargados/cmip6_historico_*"), "01_historico_crudo_1981_2014")
    copiar(ult("datos_descargados/cmip6_futuro_*"), "02_futuro_ssp585_crudo_2015_2100")
    an = ult("registro/cmip6/analisis_*"); copiar(an, "03_evaluacion_pesos_factores")
    copiar(ult("registro/cmip6/hallazgos_papers_*"), "04_cmip6_experimental_papers")
    copiar(ult("registro/cmip6_frontera/analisis_*"), "05_cmip6_frontera")
    ex = ult("resultados/cmip6_*/extremos_p*"); copiar(ex, "06_extremos")
    copiar(ult("registro/cmip6/toe*"), "07_toe")
    xl = out / "resumen_cmip6.xlsx"
    try:
        with pd.ExcelWriter(xl) as wr:
            if an and (an / "metricas_modelos.csv").exists(): pd.read_csv(an / "metricas_modelos.csv").to_excel(wr, sheet_name="modelos_contra_CHIRPS", index=False)
            if an and (an / "factores_cc.csv").exists(): pd.read_csv(an / "factores_cc.csv").to_excel(wr, sheet_name="factores_de_cambio", index=False)
            if an and (an / "verificacion_2015_2025.csv").exists(): pd.read_csv(an / "verificacion_2015_2025.csv").to_excel(wr, sheet_name="verificacion_2015_2025", index=False)
            if ex and (ex / "frecuencia_por_decada.csv").exists(): pd.read_csv(ex / "frecuencia_por_decada.csv").to_excel(wr, sheet_name="extremos_por_decada", index=False)
            pd.DataFrame({"aviso": [AVISO]}).to_excel(wr, sheet_name="LEEME", index=False)
        hechos.append(xl.name)
    except Exception as e:
        (out / "resumen_cmip6_error.txt").write_text(str(e), encoding="utf-8")
    try:
        pj = json.loads((proyecto / "proyecto_uceclima.json").read_text(encoding="utf-8")); sitio = (pj.get("procedencia") or {}).get("punto")
    except Exception:
        sitio = None
    (out / "LEEME.md").write_text(
        "# Paquete CMIP6 del territorio (UCEclima Lambda)\n\n"
        f"- **Fuente:** NASA NEX-GDDP-CMIP6 (Earth Engine `NASA/GDDP-CMIP6`), lluvia diaria, unos 25 km. Solo SSP5-8.5.\n"
        f"- **Dónde:** serie de **un punto** (la celda que contiene el sitio del proyecto{f': lon {sitio[0]}, lat {sitio[1]}' if sitio else ''}), no un promedio de la cuenca.\n"
        "- **Unidades:** mm/día; factores adimensionales (futuro / histórico).\n"
        "- **Método:** evaluación contra CHIRPS (sesgo, RMSE, validación impar/par), pesos ClimWIP (desempeño × independencia), corrección QQM y señal preservada con QDM; "
        "factor de cambio por Tr y horizonte; diagnósticos de los papers 1–3 (experimental); extremos por década.\n"
        f"- **Fecha del paquete:** {datetime.now():%Y-%m-%d %H:%M}.\n\n## Carpetas\n" + "\n".join(f"- `{h}`" for h in hechos) +
        f"\n\n**Aviso:** {AVISO}\n", encoding="utf-8")
    return {"carpeta": str(out.relative_to(proyecto)).replace("\\", "/"), "contenido": hechos}
