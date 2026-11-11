# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Series y gráficas del premódulo: catálogo de series del proyecto (CHIRPS, estaciones importadas, CELEC, GEOGLOWS), agregados anuales/mensuales, tendencia (Mann-Kendall + pendiente de Sen)
e hidrogramas de eventos. Solo lee lo que hay en el proyecto; no rellena, no corrige y marca los años incompletos. La tendencia es descriptiva: con pocos años o series cortas es frágil."""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd


class SerieError(ValueError):
    pass


def _d(proyecto):
    return Path(proyecto) / "datos_descargados"


def _ultima(proyecto, nombre):
    b = _d(proyecto)
    c = sorted(b.glob(f"sitio_*/{nombre}")) + sorted(b.glob(f"{nombre}_*"))
    return c[-1] if c else None


def catalogo(proyecto):
    out = []
    d = _ultima(proyecto, "chirps")
    if d and (d / "chirps_diario.csv").exists():
        x = pd.read_csv(d / "chirps_diario.csv", parse_dates=["fecha"])
        for col, nom in (("celda_nex_mm", "CHIRPS · media de la celda de 0,25° (la de NEX-GDDP)"), ("media_caja_mm", "CHIRPS · media de la caja"), ("pixel_mm", "CHIRPS · píxel del punto")):
            if col not in x.columns:
                continue
            out.append({"id": f"chirps:{col}", "nombre": nom, "tipo": "lluvia", "unidad": "mm/día", "inicio": x["fecha"].min().date().isoformat(), "fin": x["fecha"].max().date().isoformat(), "n": int(x[col].notna().sum())})
    pre = Path(proyecto) / "datos" / "series_premodulo" / "indice.json"                                   # series cargadas en el premódulo y guardadas con el proyecto
    if pre.exists():
        for m in json.loads(pre.read_text(encoding="utf-8")):
            if m.get("tipo") in ("lluvia", "caudal"):
                out.append({"id": f"pre:{m['slug']}", "nombre": f"{m['nombre']} (premódulo)", "tipo": m["tipo"], "unidad": m["unidad"], "inicio": m["inicio"], "fin": m["fin"], "n": m["n_dias_con_dato"]})
    est = Path(proyecto) / "datos" / "estaciones"
    for f in sorted(est.glob("*.csv")) if est.exists() else []:
        if f.name.startswith(("catalogo", "hietograma", "evento_", "_origen")):
            continue
        x = pd.read_csv(f, parse_dates=["fecha"])
        out.append({"id": f"est:{f.stem}", "nombre": f"Estación {f.stem}", "tipo": "lluvia", "unidad": "mm/registro", "inicio": x["fecha"].min().date().isoformat(), "fin": x["fecha"].max().date().isoformat(), "n": int(x["lluvia_mm"].notna().sum())})
    c = _ultima(proyecto, "celec")
    if c and (c / "celec_mazar_diario.csv").exists():
        x = pd.read_csv(c / "celec_mazar_diario.csv", parse_dates=["fecha"])
        for col, nom, t, u in (("caudal_m3s", "CELEC · caudal (significado sin confirmar)", "caudal", "m³/s"), ("cota_msnm", "CELEC · cota del embalse", "nivel", "msnm")):
            if col in x.columns:
                out.append({"id": f"celec:{col}", "nombre": nom, "tipo": t, "unidad": u, "inicio": x["fecha"].min().date().isoformat(), "fin": x["fecha"].max().date().isoformat(), "n": int(x[col].notna().sum())})
    g = _ultima(proyecto, "geoglows")
    for f in sorted(g.glob("geoglows_*.csv")) if g else []:
        rid = f.stem.split("_")[1]
        out.append({"id": f"geoglows:{rid}", "nombre": f"GEOGLOWS · tramo {rid} (reanalizado)", "tipo": "caudal", "unidad": "m³/s", "inicio": "1940-01-01", "fin": None, "n": None})
    return out


def _serie(proyecto, sid):
    tipo, _, k = sid.partition(":")
    req = {"chirps": ("chirps", "chirps_diario.csv"), "celec": ("celec", "celec_mazar_diario.csv"), "geoglows": ("geoglows", f"geoglows_{k}.csv")}.get(tipo)
    if req:
        dd = _ultima(proyecto, req[0])
        if dd is None or not (dd / req[1]).exists():
            raise SerieError(f"Este proyecto no tiene la serie «{sid}» descargada (usa «Datos / GEE»).")
    if tipo == "chirps":
        d = _ultima(proyecto, "chirps")
        x = pd.read_csv(d / "chirps_diario.csv", parse_dates=["fecha"]).set_index("fecha")[k]
    elif tipo == "pre":
        d = Path(proyecto) / "datos" / "series_premodulo"; idx = json.loads((d / "indice.json").read_text(encoding="utf-8")) if (d / "indice.json").exists() else []
        m = next((i for i in idx if i["slug"] == k), None)
        if not m:
            raise SerieError("Esa serie del premódulo no está en el proyecto.")
        x = pd.read_csv(d / m["archivo"], parse_dates=["fecha"]).set_index("fecha")["valor"]
    elif tipo == "papers":                                                               # Zeta: series derivadas con los métodos de los papers (p. ej., CHIRPS reescalado mes-año, P2)
        f = Path(proyecto) / "datos" / "papers" / f"{k}.csv"
        if not f.exists():
            raise SerieError("Esa serie derivada de los papers no está en el proyecto.")
        x = pd.read_csv(f, parse_dates=["fecha"]).set_index("fecha")["valor"]
    elif tipo == "est":
        f = Path(proyecto) / "datos" / "estaciones" / f"{k}.csv"
        if not f.exists():
            raise SerieError("No existe esa estación.")
        x = pd.read_csv(f, parse_dates=["fecha"]); x["fecha"] = x["fecha"].dt.tz_localize(None).dt.normalize()
        x = x.groupby("fecha")["lluvia_mm"].sum(min_count=1)
    elif tipo == "celec":
        c = _ultima(proyecto, "celec"); x = pd.read_csv(c / "celec_mazar_diario.csv", parse_dates=["fecha"]).set_index("fecha")[k]
    elif tipo == "geoglows":
        g = _ultima(proyecto, "geoglows"); s = pd.read_csv(g / f"geoglows_{k}.csv", parse_dates=[0])
        x = pd.Series(s.iloc[:, 1].values, index=pd.to_datetime(s.iloc[:, 0], utc=True).dt.tz_localize(None).dt.normalize())
    else:
        raise SerieError("Serie no reconocida.")
    return x.astype(float).sort_index()


def mann_kendall(y):
    """Mann-Kendall (con corrección de empates) y pendiente de Sen. y: valores por año. Devuelve tau, p (bilateral, aprox. normal) y pendiente por año."""
    y = np.asarray(y, float); n = len(y)
    if n < 8:
        return {"n": n, "tau": None, "p": None, "sen_por_anio": None, "aviso": "menos de 8 años completos: no se estima tendencia"}
    s = sum(np.sign(y[j] - y[i]) for i in range(n - 1) for j in range(i + 1, n))
    _, cnt = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(c * (c - 1) * (2 * c + 5) for c in cnt)) / 18.0
    z = 0.0 if s == 0 else (s - np.sign(s)) / math.sqrt(var)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    pend = np.median([(y[j] - y[i]) / (j - i) for i in range(n - 1) for j in range(i + 1, n)])
    return {"n": n, "tau": float(s / (n * (n - 1) / 2)), "p": float(p), "sen_por_anio": float(pend), "aviso": ""}


def lluvia(proyecto, sid, minimo_completo=0.9):
    return lluvia_serie(_serie(proyecto, sid), sid, minimo_completo)


def lluvia_serie(x, sid, minimo_completo=0.9):
    """Agregados anuales, climatología y tendencia de una serie diaria de lluvia (Series con índice de fechas). Sirve para series del proyecto y para las de la memoria del premódulo."""
    cal = pd.date_range(x.index.min(), x.index.max(), freq="D"); x = x.reindex(cal)
    g = x.groupby(x.index.year)
    anual = pd.DataFrame({"total": g.sum(min_count=1), "max_dia": g.max(), "con_dato": g.count(), "dias": g.size()})
    anual["completo"] = anual["con_dato"] >= minimo_completo * anual["dias"]
    comp = anual[anual["completo"]]
    # el total anual solo es comparable con años completos; en los incompletos se muestra lo medido y se marca
    mes = x.groupby([x.index.year, x.index.month]).sum(min_count=20).unstack()
    clima = {"mes": list(range(1, 13)), "media": [None if pd.isna(v) else round(float(v), 1) for v in mes.mean()], "p25": [None if pd.isna(v) else round(float(v), 1) for v in mes.quantile(.25)],
             "p75": [None if pd.isna(v) else round(float(v), 1) for v in mes.quantile(.75)]}
    tt = mann_kendall(comp["total"].values); tm = mann_kendall(comp["max_dia"].values)
    j = lambda s: [None if pd.isna(v) else round(float(v), 1) for v in s]
    media_total = float(comp["total"].mean()) if len(comp) else None
    return {"id": sid, "anios": [int(a) for a in anual.index], "total_mm": j(anual["total"]), "max_dia_mm": j(anual["max_dia"]), "completo": [bool(v) for v in anual["completo"]], "con_dato": [int(v) for v in anual["con_dato"]],
            "clima_mensual": clima, "tendencia_total": tt, "tendencia_max_dia": tm, "media_total_mm": media_total, "años_completos": int(len(comp)),
            "nota": "Los años con menos de 90 % de días con dato se dibujan aparte y no entran en la tendencia. Mann-Kendall + pendiente de Sen: descriptivo; con pocos años o autocorrelación es frágil."}


def caudal(proyecto, sid):
    return caudal_serie(_serie(proyecto, sid), sid, _eventos(proyecto))


def caudal_serie(x, sid, ev=None):
    """Hidrograma diario, curva de duración y resumen de una serie diaria de caudal (`ev`: eventos seleccionados, si los hay)."""
    v = x.dropna()
    q995 = float(np.nanpercentile(v, 99.5)); med = x.rolling(15, center=True, min_periods=5).median()
    sosp = (x > 5 * med) & (x > 3 * q995)
    xx = x.copy(); xx[sosp] = np.nan
    orden = np.sort(xx.dropna().values)[::-1]; n = len(orden)
    pe = np.linspace(0, 100, 101); fdc = [float(np.percentile(orden, 100 - p)) for p in pe] if n else []
    g = xx.groupby(xx.index.year)
    ev = ev or []
    return {"id": sid, "fecha_inicio": x.index.min().date().isoformat(), "q": [None if pd.isna(a) else round(float(a), 2) for a in xx.values], "sospechosos": [d.date().isoformat() for d in x.index[sosp]],
            "media": float(v.mean()), "mediana": float(v.median()), "p95": float(np.percentile(v, 95)), "max": float(xx.max()), "fdc_pct": pe.tolist(), "fdc": fdc,
            "anual": {"anios": [int(a) for a in g.mean().index], "media": [None if pd.isna(a) else round(float(a), 1) for a in g.mean()], "max": [None if pd.isna(a) else round(float(a), 1) for a in g.max()]},
            "eventos": ev, "nota": "Medias diarias. Los días marcados como sospechosos (pico aislado absurdo) no se dibujan ni se corrigen."}


def _sel_dir(proyecto):
    b = Path(proyecto) / "registro" / "eventos"
    c = sorted(b.glob("seleccion_*")) if b.exists() else []
    return c[-1] if c else None


def _eventos(proyecto):
    d = _sel_dir(proyecto)
    if not d or not (d / "eventos_seleccionados.csv").exists():
        return []
    s = pd.read_csv(d / "eventos_seleccionados.csv")
    cols = [c for c in ("evento", "rol", "fecha_pico_lluvia", "ventana_inicio", "ventana_fin", "P_max_dia_mm", "Tr_P_max_dia_anios", "Q_base_previo_m3s", "Q_pico_m3s", "dQ_m3s", "V_directo_hm3") if c in s.columns]
    return s[cols].replace({np.nan: None}).to_dict("records")


def evento(proyecto, ide):
    d = _sel_dir(proyecto)
    if not d:
        raise SerieError("Este proyecto no tiene selección de eventos.")
    f = next((d / "hidrogramas").glob(f"{ide}_*.csv"), None)
    if not f:
        raise SerieError("No existe ese evento.")
    h = pd.read_csv(f)
    meta = next((e for e in _eventos(proyecto) if e["evento"] == ide), {})
    return {"evento": ide, "meta": meta, "fecha": h["fecha"].tolist(), "lluvia_mm": [None if pd.isna(a) else round(float(a), 2) for a in h["lluvia_serie_mm"]],
            "caudal_m3s": [None if pd.isna(a) else round(float(a), 2) for a in h["Q_m3s"]], "otras": {c: [None if pd.isna(a) else round(float(a), 2) for a in h[c]] for c in h.columns if c.startswith("CHIRPS_")}}
