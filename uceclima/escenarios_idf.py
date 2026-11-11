# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Escenarios de lluvia de DISEÑO (todos históricos; ninguno es cambio climático) para contrastar qué tan sensible es el resultado a la IDF elegida:
  directa     IDF oficial INAMHI de la estación de referencia, sin escalar (principal).
  observado   la misma IDF reescalada para que su lluvia de 24 h Tr 100 iguale el Gumbel de los MÁXIMOS ANUALES OBSERVADOS en esa estación (del propio proyecto).
  escalada    IDF oficial INAMHI «escalada» al sitio (modo automático del libro) — fantasma.
  chirps      la misma IDF reescalada al Gumbel de los máximos anuales de CHIRPS (media de la caja) — fantasma.
Reescalar es un factor único para todas las duraciones: conserva la FORMA de la IDF de la estación y cambia su magnitud. Cada variante queda escrita como CSV en `registro/idf/`
con su procedencia. Nada se calibra: son magnitudes de diseño distintas para comparar."""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd

TR = 100


class EscenarioError(ValueError):
    pass


def _gumbel(x, tr):
    x = np.asarray(x, float); a = math.sqrt(6) / math.pi * x.std(ddof=1); u = x.mean() - 0.5772 * a
    return float(u - a * math.log(-math.log(1 - 1 / tr)))


def _max_anuales(s, minimo=0.9):
    s = s.dropna() if False else s
    g = s.groupby(s.index.year); ok = g.count() >= minimo * g.size()
    return g.max()[ok]


def _serie_estacion(proyecto, ide):
    f = Path(proyecto) / "datos" / "estaciones" / f"{ide}.csv"
    if not f.exists():
        raise EscenarioError(f"El proyecto no tiene la estación {ide} registrada (usa el premódulo: ordenar y «Registrar estación»).")
    x = pd.read_csv(f, parse_dates=["fecha"]); x["fecha"] = x["fecha"].dt.tz_localize(None).dt.normalize()
    s = x.groupby("fecha")["lluvia_mm"].sum(min_count=1)
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))


def _serie_chirps(proyecto, col="media_caja_mm"):
    b = Path(proyecto) / "datos_descargados"
    c = sorted(b.glob("sitio_*/chirps/chirps_diario.csv")) + sorted(b.glob("chirps_*/chirps_diario.csv"))
    if not c:
        raise EscenarioError("El proyecto no tiene CHIRPS descargado.")
    x = pd.read_csv(c[-1], parse_dates=["fecha"]).set_index("fecha")[col]
    return x


def _profundidad(idf, dur_min, tr=TR):
    """Profundidad (mm) para una duración, interpolando linealmente la intensidad en log-duración (solo informativo; el solver usa su propio bloques alternos)."""
    d = np.log(np.array(idf.columns, float)); i = idf.loc[tr].values.astype(float)
    return float(np.interp(np.log(dur_min), d, i) * dur_min / 60.0)


def definiciones(proyecto, cfg, estacion="M0138", duracion_min=180):
    import uceclima                                                       # fija sys.path hacia el núcleo
    from climanet import inamhi
    propia = idf_propia(proyecto, cfg)
    if propia is not None:                                                # Zeta: IDF propia declarada (p. ej. fuera de Ecuador); los escenarios Y la escalan igual que a la del INAMHI
        base, info_p = propia
        estacion = info_p.get("estacion") or estacion
        out = [{"id": "directa", "nombre": f"IDF propia ({info_p.get('nombre', 'declarada')})", "rol": "principal", "factor": 1.0, "fuente": info_p.get("fuente", "IDF propia declarada"), "idf_propia": True}]
    else:
        base = inamhi.idf_estacion(estacion)
        base = base[0] if isinstance(base, tuple) else base
        out = [{"id": "directa", "nombre": f"IDF directa {estacion} (INAMHI)", "rol": "principal", "factor": 1.0, "fuente": f"INAMHI libro de intensidades, estación {estacion}, sin escalar"}]
    p24 = _profundidad(base, 1440)
    lat_lon = (cfg.get("idf_inamhi") or {}) if propia is None else {}
    try:
        obs = _max_anuales(_serie_estacion(proyecto, estacion)); g = _gumbel(obs, TR)
        out.append({"id": "observado", "nombre": f"IDF {estacion} ajustada a observados (Gumbel {g:.0f} mm/24 h)", "rol": "referencia", "factor": g / p24,
                    "fuente": f"Gumbel de {len(obs)} máximos anuales de la estación {estacion} (años con ≥ 90 % de días), Tr {TR}", "gumbel_24h_mm": g, "n_anios": int(len(obs))})
    except EscenarioError as e:
        out.append({"id": "observado", "nombre": "IDF ajustada a observados", "rol": "referencia", "factor": None, "no_disponible": str(e)})
    if "lat" in lat_lon:
        e, info = inamhi.idf_sitio(float(lat_lon["lat"]), float(lat_lon["lon"]))
        out.append({"id": "escalada", "nombre": f"IDF escalada al sitio (INAMHI, ref. {info.get('estacion_ref')})", "rol": "fantasma", "factor": _profundidad(e, 1440) / p24,
                    "fuente": f"INAMHI idf_sitio modo {info.get('modo')}, estación de referencia {info.get('estacion_ref')} a {info.get('dist_ref_km')} km"})
    try:
        ch = _max_anuales(_serie_chirps(proyecto)); g = _gumbel(ch, TR)
        out.append({"id": "chirps", "nombre": f"IDF {estacion} ajustada a CHIRPS (Gumbel {g:.0f} mm/24 h)", "rol": "fantasma", "factor": g / p24,
                    "fuente": f"Gumbel de {len(ch)} máximos anuales de CHIRPS (media de la caja), Tr {TR}", "gumbel_24h_mm": g, "n_anios": int(len(ch))})
    except EscenarioError as e:
        out.append({"id": "chirps", "nombre": "IDF ajustada a CHIRPS", "rol": "fantasma", "factor": None, "no_disponible": str(e)})
    out += _escenarios_cmip6(proyecto)
    for d in out:
        if d.get("factor"):
            d["p24_mm"] = round(p24 * d["factor"], 1); d["p_duracion_mm"] = round(_profundidad(base, duracion_min) * d["factor"], 1); d["duracion_min"] = duracion_min
    return out, base


def idf_propia(proyecto, cfg):
    """Zeta: IDF propia registrada con /api/idf/propia (registro/idf/idf_propia.json). Devuelve (tabla Tr × min en mm/h, info) o None."""
    meta = Path(proyecto) / "registro" / "idf" / "idf_propia.json"
    if not meta.exists() or cfg.get("idf_inamhi"):
        return None
    info = json.loads(meta.read_text(encoding="utf-8"))
    f = Path(proyecto) / info["archivo"]
    t = pd.read_csv(f, index_col=0); t.columns = t.columns.astype(int); t.index = t.index.astype(int)
    return t, info


def registrar_idf_propia(proyecto, archivo, fuente, nombre="", estacion=None):
    """Zeta: registra una IDF propia (CSV: primera columna Tr en años, encabezados = duración en minutos, valores = intensidad mm/h) con su FUENTE obligatoria.
    Valida forma y monotonía, copia el CSV a registro/idf/ con sello de tiempo, la declara en config_climanet.json (idf_csv) y quita la IDF del INAMHI de X. Nada se sobrescribe."""
    from datetime import datetime
    import shutil
    if not (fuente or "").strip():
        raise EscenarioError("La IDF propia necesita su fuente (norma, estudio, estación y método). No se registra sin ella.")
    src = Path(str(archivo).strip().strip('"'))
    if not src.exists():
        raise EscenarioError(f"No existe el archivo: {src}")
    try:
        t = pd.read_csv(src, index_col=0); t.columns = t.columns.astype(float).astype(int); t.index = t.index.astype(float).astype(int)
    except Exception as e:
        raise EscenarioError(f"El CSV debe tener Tr en la primera columna y duraciones en minutos como encabezados: {str(e)[:150]}")
    t = t.sort_index()[sorted(t.columns)]
    if t.isna().any().any() or (t.values <= 0).any():
        raise EscenarioError("La IDF tiene celdas vacías o no positivas.")
    if (t.diff(axis=1).iloc[:, 1:] > 1e-9).any().any():
        raise EscenarioError("La intensidad debe disminuir con la duración en cada Tr (revisa unidades: mm/h).")
    if (t.diff(axis=0).iloc[1:] < -1e-9).any().any():
        raise EscenarioError("La intensidad debe crecer con el periodo de retorno en cada duración.")
    if 1440 not in t.columns or 100 not in t.index:
        raise EscenarioError("La IDF propia debe incluir la duración de 1440 min y el Tr 100 (los factores CMIP6 y la tormenta de 24 h los usan).")
    d = Path(proyecto) / "registro" / "idf"; d.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S"); dst = d / f"idf_propia_{sello}.csv"
    t.to_csv(dst)
    info = {"archivo": str(dst.relative_to(proyecto)).replace("\\", "/"), "origen": str(src), "fuente": fuente.strip(), "nombre": nombre or src.stem, "estacion": estacion,
            "registrada": datetime.now().isoformat(timespec="seconds"), "tr": [int(x) for x in t.index], "duraciones_min": [int(x) for x in t.columns],
            "p24_tr100_mm": round(float(t.loc[100, 1440]) * 24, 1)}
    meta = d / "idf_propia.json"
    if meta.exists():
        shutil.copy2(meta, d / f"idf_propia_{sello}_anterior.json.bak")
    meta.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    cf = Path(proyecto) / "config_climanet.json"; cfg = json.loads(cf.read_text(encoding="utf-8"))
    shutil.copy2(cf, cf.with_name(f"config_climanet.json.{sello}.bak"))
    cfg.pop("idf_inamhi", None); cfg.pop("idf_x", None); cfg["idf_csv"] = str(dst.resolve())
    cf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def idf_desde_chirps(proyecto, columna=None):
    """Zeta (replicable en todo el mundo): IDF del sitio a partir de CHIRPS cuando no hay IDF oficial ni estaciones.
    Pd(T) = Gumbel por momentos de los máximos diarios anuales de CHIRPS (años con ≥ 90 % de días) × 1,13 (intervalo fijo de lectura → 24 h móviles, Weiss 1964);
    duraciones de 1 a 24 h con los coeficientes de Campos (1978), los mismos de la cadena del libro INAMHI; 5-30 min por la ley potencial ajustada a esos puntos.
    SUPUESTO GENÉRICO declarado. Además, según los papers P1-P2, CHIRPS subestima los máximos anuales (≈ −31 % en los niveles de retorno en Ecuador):
    esta IDF es probablemente BAJA; con estaciones locales, sustitúyela."""
    from .idf_excel import COEF_CAMPOS, FACTOR_INTERVALO_FIJO
    b = Path(proyecto) / "datos_descargados"
    c = sorted(b.glob("sitio_*/chirps/chirps_diario.csv")) + sorted(b.glob("chirps_*/chirps_diario.csv"))
    if not c:
        raise EscenarioError("El proyecto no tiene CHIRPS descargado (módulo 3).")
    d = pd.read_csv(c[-1], parse_dates=["fecha"]).set_index("fecha")
    col = columna or next((k for k in ("media_caja_mm", "celda_nex_mm", "centro_mm") if k in d.columns), None)
    if col is None:
        raise EscenarioError("No encuentro la columna de lluvia de CHIRPS.")
    s = d[col].astype(float).asfreq("D"); ams = _max_anuales(s).dropna()
    if len(ams) < 15:
        raise EscenarioError(f"Solo {len(ams)} años completos de CHIRPS: se necesitan ≥ 15 para un Gumbel.")
    TRS_, DUR = (2, 5, 10, 25, 50, 100), (5, 10, 15, 20, 30, 60, 120, 180, 360, 720, 1440)
    horas = sorted(COEF_CAMPOS); filas = {}
    for tr in TRS_:
        p24 = _gumbel(ams.values, tr) * FACTOR_INTERVALO_FIJO
        ih = {h * 60: p24 * COEF_CAMPOS[h] / h for h in horas}                      # mm/h para 60…1440 min
        k, lna = np.polyfit(np.log(list(ih)), np.log(list(ih.values())), 1)
        filas[tr] = [ih[t] if t in ih else float(np.exp(lna) * t ** k) for t in DUR]
    tab = pd.DataFrame.from_dict(filas, orient="index", columns=DUR); tab.index.name = "Tr"
    for j in range(1, tab.shape[1]):                                                 # monotonía estricta por la interpolación entre 120 y 180 min, por si acaso
        tab.iloc[:, j] = np.minimum(tab.iloc[:, j], tab.iloc[:, j - 1])
    carpeta = Path(proyecto) / "registro" / "idf"; carpeta.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    f = carpeta / f"idf_chirps_borrador_{datetime.now():%Y%m%d_%H%M%S}.csv"; tab.round(3).to_csv(f)
    fuente = (f"CHIRPS ({c[-1].relative_to(proyecto)}, columna {col}): Gumbel por momentos de {len(ams)} máximos diarios anuales ({int(ams.index.min())}–{int(ams.index.max())}) × 1,13 (Weiss 1964); "
              "coeficientes de duración de Campos (1978) para 1–24 h y ley potencial para < 1 h. SUPUESTO GENÉRICO sin estaciones; CHIRPS subestima los máximos (≈ −31 % en Ecuador, papers P1-P2): IDF probablemente baja.")
    info = registrar_idf_propia(proyecto, f, fuente, "IDF desde CHIRPS (por defecto, sin estaciones)")
    info["anios_chirps"] = int(len(ams)); info["advertencia"] = "IDF probablemente baja (CHIRPS subestima máximos anuales). Con estaciones locales, sustitúyela."
    return info


ESTADISTICOS = {"mediana": "mediana_ponderada", "p90": "p90", "p10": "p10"}
ETQ_ESTAD = {"mediana": "ensamble ClimWIP (mediana ponderada)", "p90": "ensamble p90 (extremo alto)", "p10": "ensamble p10 (extremo bajo)", "mejor": "mejor modelo", "cuantiles": "ensamble de cuantiles por quintiles"}
SSP_TXT = {"ssp585": "SSP5-8.5"}
HORIZONTES = ("2040-2069", "2071-2100")


def _escenarios_cmip6(proyecto):
    """Escenarios Y: la IDF oficial de X multiplicada por el factor de cambio CMIP6 DE CADA Tr (como en las entregas de Machala/Gualaquiza: IDF_ajustada(Tr, d) = IDF(Tr, d) × factor(Tr), con el factor de 24 h
    para todas las duraciones; supuesto explícito: la transferencia a duraciones subdiarias no está validada). X (condiciones existentes) no cambia nunca. Solo SSP5-8.5 (decisión del usuario)."""
    from . import cmip6_descarga as CD
    b = Path(proyecto) / "registro" / "cmip6"; c = sorted(b.glob("analisis_*")) if b.exists() else []
    f = c[-1] / "factores_cc.csv" if c else None
    if not f or not f.exists():
        return []
    F = pd.read_csv(f); out = []
    res = json.loads((c[-1] / "resumen_analisis.json").read_text(encoding="utf-8")); mejor = res.get("mejor_modelo")
    fm = c[-1] / "factores_por_modelo.csv"; pm = pd.read_csv(fm) if fm.exists() else None
    TRS_ = (2, 5, 10, 25, 50, 100)
    def vector(hor, ver, col):
        v = {}
        for t in TRS_:
            r = F[(F["horizonte"] == hor) & (F["version"] == ver) & (F["metrica"] == f"Tr{t} de 24 h")]
            if r.empty:
                return None
            v[t] = float(r.iloc[0][col])
        return v
    for hor in HORIZONTES:
        base100 = F[(F["horizonte"] == hor) & (F["version"] == "QQM/QDM") & (F["metrica"] == "Tr100 de 24 h")]
        if base100.empty:
            continue
        rango = [(float(base100.iloc[0]["p10"]) - 1) * 100, (float(base100.iloc[0]["p90"]) - 1) * 100]; nmod = int(base100.iloc[0]["n_modelos"])
        cand = {est: vector(hor, "QQM/QDM", col) for est, col in ESTADISTICOS.items()}
        cand["cuantiles"] = vector(hor, "QQM/QDM · ensamble de cuantiles", "mediana_ponderada")
        if pm is not None and mejor:
            sel = lambda t: pm[(pm["horizonte"] == hor) & (pm["metrica"] == f"Tr{t} de 24 h") & (pm["modelo"] == mejor)]
            vm = {t: float(sel(t)["factor_corregido"].iloc[0]) for t in TRS_ if not sel(t).empty}
            cand["mejor"] = vm if len(vm) == len(TRS_) else None
        for est, vec in cand.items():
            if not vec:
                continue
            fac = vec[100]; nom_est = ETQ_ESTAD[est] + (f" ({mejor})" if est == "mejor" else "")
            out.append({"id": f"cc_ssp585_{hor}_{est}", "tipo": "cmip6", "ssp": "ssp585", "horizonte": hor, "estadistico": est, "factor": fac, "factor_por_tr": {str(k): v for k, v in vec.items()}, "tasa_cambio_pct": (fac - 1) * 100,
                        "rango_pct": rango, "n_modelos": nmod if est != "mejor" else 1, "nombre": f"CMIP6 SSP5-8.5 {hor} · {nom_est} ({(fac - 1) * 100:+.0f} %)", "rol": "cambio climático (CMIP6, bajo supuesto)",
                        "fuente": f"Factor de cambio por Tr de 24 h (QQM/QDM, {'modelo ' + str(mejor) if est == 'mejor' else 'ensamble ClimWIP de ' + str(nmod) + ' modelos NEX-GDDP-CMIP6'}, {ETQ_ESTAD[est]}) aplicado fila por fila a la IDF directa de la estación; mismo factor para todas las duraciones. "
                                  "SUPUESTO EXPLORATORIO de cambio uniforme por duración (el factor diario no demuestra el cambio subdiario; IDF resultante no validada). "
                                  "Línea base asumida por decisión del usuario; no calibrada ni validada. Escenario de sensibilidad, no predicción.", "supuesto": "exploratorio_cambio_uniforme_por_duracion"})
    return out


def preparar(proyecto, cfg, escenario_id, estacion="M0138"):
    """Devuelve (parche de configuración, definición). Escribe el CSV de la IDF reescalada cuando hace falta."""
    defs, base = definiciones(proyecto, cfg, estacion, int(cfg.get("storm_min", 180)))
    d = next((x for x in defs if x["id"] == escenario_id), None)
    if d is None:
        raise EscenarioError("Escenario desconocido (directa | observado | escalada | chirps | cc_<ssp>_<horizonte>_<mediana|p10|p90>).")
    if not d.get("factor"):
        raise EscenarioError(d.get("no_disponible") or "Escenario no disponible.")
    if escenario_id == "directa":
        if d.get("idf_propia"):                                           # Zeta: la IDF propia ya está declarada en idf_csv
            return {"idf_inamhi": None, "idf_csv": str((Path(proyecto) / idf_propia(proyecto, cfg)[1]["archivo"]).resolve())}, d
        return {"idf_inamhi": {"estacion": estacion}, "idf_csv": None}, d
    if d.get("tipo") == "cmip6":
        carpeta = Path(proyecto) / "registro" / "idf"; carpeta.mkdir(parents=True, exist_ok=True)
        fac = pd.Series({int(k): v for k, v in d["factor_por_tr"].items()}).sort_index()
        fac = pd.Series({t: float(fac[fac.index[np.abs(fac.index - t).argmin()]]) for t in base.index})   # Zeta: Tr sin factor propio (p. ej. 500) toma el del Tr más cercano, declarado
        d = {**d, "factor_aplicado_por_tr": {str(k): v for k, v in fac.items()}}
        f = carpeta / f"{escenario_id}_{estacion}.csv"; base.mul(fac, axis=0).round(3).to_csv(f)
        (carpeta / f"{escenario_id}_{estacion}.json").write_text(json.dumps({**d, "archivo": f.name}, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"idf_inamhi": None, "idf_csv": str(f.relative_to(proyecto)).replace("\\", "/")}, d
    if escenario_id == "escalada":
        return {"idf_inamhi": cfg["idf_inamhi"], "idf_csv": None}, d
    carpeta = Path(proyecto) / "registro" / "idf"; carpeta.mkdir(parents=True, exist_ok=True)
    f = carpeta / f"{escenario_id}_{estacion}.csv"
    (base * d["factor"]).round(3).to_csv(f)
    (carpeta / f"{escenario_id}_{estacion}.json").write_text(json.dumps({**d, "archivo": f.name}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"idf_inamhi": None, "idf_csv": str(f.relative_to(proyecto)).replace("\\", "/")}, d
