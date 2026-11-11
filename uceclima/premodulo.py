# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""PREMÓDULO · lee Excel/CSV de precipitación y caudal, los guarda en MEMORIA y deja listos los datos para graficar series y tendencias en el mismo módulo.

Reglas (no se saltan):
- Los archivos crudos NUNCA se modifican. Lo leído queda en memoria (y en una copia en ~/.uceclima/memoria_premodulo para no perderlo al reiniciar); al crear el proyecto se guarda con su origen y hash.
- No se inventa nada: los valores no numéricos o centinela (-999, -9999) quedan vacíos; los negativos de lluvia/caudal se anulan y se cuentan; si una misma fecha trae valores distintos queda VACÍA (no se promedia).
- Lluvia sub-diaria → total diario; caudal sub-diario → media diaria; un día solo vale si tiene ≥ 80 % de los registros esperados. Se avisa siempre que se agregó.
- Si el programa no puede saber qué es una columna (lluvia, caudal, nivel), no adivina: pide confirmación con una vista previa."""
import csv, hashlib, io, json, math, re, unicodedata
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

from . import preparacion as PR, series_api as SER

MEM_DIR = Path.home() / ".uceclima" / "memoria_premodulo"
CENTINELAS = (-999.0, -9999.0, -99.0, 9999.0, 99999.0)
CENTINELAS_LLUVIA = (888.0, 999.0)                                                  # códigos de «sin dato» de INAMHI en lecturas de lluvia (no en caudal: 888 m³/s puede ser real)
TIPOS = {"lluvia": ("mm/día", "Precipitación"), "caudal": ("m³/s", "Caudal"), "nivel": ("m", "Nivel / cota")}
_MEM = {"series": {}, "cargada": False}


class PremoduloError(ValueError):
    pass


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _slug(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()).strip("_")[:80] or "serie"


# ------------------------------------------------------------------------------------------------ memoria (y copia en disco)
def _cargar_disco():
    if _MEM["cargada"]:
        return
    _MEM["cargada"] = True
    idx = MEM_DIR / "indice.json"
    if not idx.exists():
        return
    try:
        for m in json.loads(idx.read_text(encoding="utf-8")):
            f = MEM_DIR / f"{m['slug']}.csv"
            if f.exists():
                d = pd.read_csv(f, parse_dates=["fecha"])
                _MEM["series"][m["id"]] = {"meta": m, "serie": d.set_index("fecha")["valor"].astype(float)}
    except Exception:
        pass


def _guardar_disco():
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    for sid, e in _MEM["series"].items():
        f = MEM_DIR / f"{e['meta']['slug']}.csv"
        if not f.exists():
            e["serie"].rename("valor").rename_axis("fecha").reset_index().to_csv(f, index=False)
    (MEM_DIR / "indice.json").write_text(json.dumps([e["meta"] for e in _MEM["series"].values()], ensure_ascii=False, indent=1), encoding="utf-8")


def memoria():
    _cargar_disco()
    out = []
    for sid, e in _MEM["series"].items():
        m = e["meta"]
        out.append({"id": sid, "nombre": m["nombre"], "tipo": m["tipo"], "unidad": m["unidad"], "inicio": m["inicio"], "fin": m["fin"], "n": m["n_dias_con_dato"], "origen": m["origen"], "calidad": m["calidad"], "lon": m.get("lon"), "lat": m.get("lat")})
    return {"series": out, "n": len(out), "nota": "Datos en memoria: no se guardan en un proyecto hasta que lo crees (módulo 1)."}


def serie(sid):
    _cargar_disco()
    e = _MEM["series"].get(sid)
    if not e:
        raise PremoduloError("Esa serie no está en la memoria del premódulo.")
    return e["serie"]


def quitar(sid):
    _cargar_disco()
    e = _MEM["series"].pop(sid, None)
    if e:
        try:
            (MEM_DIR / f"{e['meta']['slug']}.csv").unlink(missing_ok=True)
        except Exception:
            pass
        _guardar_disco()
    return memoria()


def limpiar():
    _cargar_disco()
    for sid in list(_MEM["series"]):
        quitar(sid)
    return memoria()


# ------------------------------------------------------------------------------------------------ lectura de tablas
def _tabla_csv(p):
    raw = Path(p).read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    try:
        sep = csv.Sniffer().sniff(txt[:20000], delimiters=",;\t|").delimiter
    except Exception:
        sep = ";" if txt[:2000].count(";") > txt[:2000].count(",") else ","
    d = pd.read_csv(io.StringIO(txt), sep=sep, dtype=str, engine="python")
    d.columns = [str(c).strip() for c in d.columns]
    return d, {"codificacion": enc, "separador": sep}


def _tabla_excel(p, hoja=None):
    xl = pd.ExcelFile(p)
    hojas = list(xl.sheet_names); mejor, mejor_n = None, -1
    for h in ([hoja] if hoja else hojas):
        d0 = xl.parse(h, header=None, dtype=object)
        if d0.shape[0] > mejor_n and d0.shape[1] >= 2:
            mejor, mejor_n = h, d0.shape[0]
    if mejor is None:
        raise PremoduloError("El Excel no tiene hojas con tablas.")
    d0 = xl.parse(mejor, header=None, dtype=object)
    cab = 0
    for i in range(min(25, len(d0))):                                                        # primera fila con ≥ 2 textos y datos debajo
        f = d0.iloc[i]; txt = sum(isinstance(v, str) and v.strip() != "" for v in f)
        if txt >= 2 and i + 1 < len(d0) and d0.iloc[i + 1].notna().sum() >= 2:
            cab = i; break
    d = d0.iloc[cab + 1:].copy(); d.columns = [str(c).strip() if c is not None and str(c) != "nan" else f"col{j}" for j, c in enumerate(d0.iloc[cab])]
    d = d.dropna(how="all").reset_index(drop=True)
    return d.astype(object).where(d.notna(), None), {"hoja": mejor, "hojas": hojas, "fila_encabezado": cab + 1}


def _a_num(s):
    t = s.astype(str).str.strip().str.replace(" ", "", regex=False)
    t = t.where(~t.isin(["", "None", "nan", "NaN", "-", "--", "S/D", "s/d", "ND", "NULL"]), None)
    coma = t.dropna().str.contains(r"^-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d+$").mean() if t.notna().any() else 0
    if coma > 0.5:
        t = t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce")


def _fechas(s):
    """Convierte a fechas probando día-primero y mes-primero (se elige la que deja más fechas válidas y más orden cronológico). Devuelve (Serie datetime sin zona, ambigüedad)."""
    s = s.astype(str).str.strip()
    if s.str.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}").mean() > 0.8:                      # año-mes-día (ISO): sin ambigüedad, nunca día-primero
        f = pd.to_datetime(s, errors="coerce", dayfirst=False, utc=True).dt.tz_localize(None)
        return f, {"dia_primero": False, "validas_pct": round(100 * float(f.notna().mean()), 1), "ambigua": False}
    cand = {}
    for dayfirst in (True, False):
        f = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst, utc=True).dt.tz_localize(None)
        ok = f.notna().mean(); mono = float((f.dropna().diff().dropna() >= pd.Timedelta(0)).mean()) if f.notna().sum() > 2 else 0
        cand[dayfirst] = (ok, mono, f)
    mejor = max(cand, key=lambda k: (round(cand[k][0], 3), cand[k][1]))
    ok, mono, f = cand[mejor]
    amb = abs(cand[True][0] - cand[False][0]) < 0.02 and abs(cand[True][1] - cand[False][1]) < 0.02 and s.str.contains(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}").mean() > 0.5
    return f, {"dia_primero": bool(mejor), "validas_pct": round(100 * ok, 1), "ambigua": bool(amb)}


def _tipo_por_nombre(nombre):
    n = _norm(nombre)
    if re.search(r"precip|lluvia|rain|\bpp\b|prec\b|ppt", n):
        return "lluvia"
    if re.search(r"caudal|discharge|\bflow\b|gasto|\bq\b|m3 ?s|q m3", n):
        return "caudal"
    if re.search(r"nivel|cota|level|stage|altura|msnm", n):
        return "nivel"
    return None


def _a_diaria(fechas, valores, tipo):
    """Serie diaria desde registros (cualquier paso). Devuelve (serie, info)."""
    d = pd.DataFrame({"f": fechas, "v": valores}).dropna(subset=["f"])
    info = {"registros": int(len(d)), "agregado": False, "paso": "diario", "negativos_anulados": 0, "centinelas_anulados": 0, "conflictos_vacios": 0}
    cen = CENTINELAS + (CENTINELAS_LLUVIA if tipo == "lluvia" else ())
    d.loc[d["v"].isin(cen), "v"] = np.nan; info["centinelas_anulados"] = int(valores.isin(cen).sum())
    if tipo in ("lluvia", "caudal"):
        neg = d["v"] < 0; info["negativos_anulados"] = int(neg.sum()); d.loc[neg, "v"] = np.nan
    d = d.sort_values("f")
    dif = d["f"].diff().dropna()
    paso = dif.median() if len(dif) else pd.Timedelta(days=1)
    if paso < pd.Timedelta(hours=23):
        info.update(agregado=True, paso=f"{int(paso.total_seconds() // 60)} min")
        d["dia"] = d["f"].dt.normalize(); esperados = max(1, int(round(pd.Timedelta(days=1) / paso)))
        horas = d["f"].dt.strftime("%H:%M").value_counts()
        if len(horas) <= 8 and horas.iloc[-1] >= 0.2 * horas.iloc[0]:                    # lecturas fijas (p. ej. 07/13/19 h): se esperan tantas como horas de lectura
            esperados = len(horas); info["paso"] = "lecturas a las " + ", ".join(sorted(horas.index)) + " h"
        g = d.groupby("dia")["v"]; cnt = g.count()
        agg = g.sum(min_count=1) if tipo == "lluvia" else g.mean()
        agg[cnt < 0.8 * esperados] = np.nan                                              # día incompleto: vacío (no se rellena)
        return agg.sort_index(), info
    d["dia"] = d["f"].dt.normalize()
    g = d.groupby("dia")["v"]
    nun = g.nunique(dropna=True); primero = g.first()
    conf = nun > 1; info["conflictos_vacios"] = int(conf.sum()); primero[conf] = np.nan  # fechas repetidas con valores distintos: se dejan vacías
    return primero.sort_index(), info


def _calidad(s):
    s = s.sort_index(); idx = pd.date_range(s.index.min(), s.index.max(), freq="D"); r = s.reindex(idx)
    n = int(r.notna().sum()); g = r.groupby(r.index.year); comp = (g.count() >= 0.9 * g.size())
    return {"dias_periodo": int(len(idx)), "dias_con_dato": n, "faltantes_pct": round(100 * (1 - n / len(idx)), 1), "anios_completos": int(comp.sum()), "anios_total": int(len(comp)),
            "min": float(r.min()), "max": float(r.max()), "media": float(r.mean())}


def _registrar(sid, nombre, tipo, x, origen, info, extra=None):
    x = x.dropna().astype(float); x = x[~x.index.duplicated()].sort_index()
    if len(x) < 5:
        raise PremoduloError(f"«{nombre}» tiene menos de 5 datos válidos.")
    unidad = TIPOS[tipo][0]
    meta = {"id": sid, "slug": _slug(sid), "nombre": nombre, "tipo": tipo, "unidad": unidad, "inicio": x.index.min().date().isoformat(), "fin": x.index.max().date().isoformat(), "n_dias_con_dato": int(len(x)),
            "origen": origen, "lectura": info, "calidad": _calidad(x), "cargada": datetime.now().isoformat(timespec="seconds"), **(extra or {})}
    _cargar_disco()
    previa = _MEM["series"].get(sid)
    if previa and previa["meta"]["origen"].get("sha256") != origen.get("sha256"):                       # mismo id desde OTRO archivo: no se pisa en silencio, se conservan las dos
        sid2 = f"{sid}__{_slug(Path(origen.get('archivo', 'otro')).stem)}"
        meta.update(id=sid2, slug=_slug(sid2), nombre=f"{nombre} ({origen.get('archivo', 'otro archivo')})", aviso_colision=f"ya había una serie «{sid}» de otro archivo ({previa['meta']['origen'].get('archivo')}); se conservaron las dos")
        sid = sid2
    _MEM["series"][sid] = {"meta": meta, "serie": x}                                                      # mismo archivo releído: reemplaza (idempotente)
    return meta


# ------------------------------------------------------------------------------------------------ API: leer un archivo
def vista_previa(ruta, hoja=None, n=8):
    p = Path(ruta)
    if not p.is_file():
        raise PremoduloError("No existe el archivo.")
    d, info = (_tabla_excel(p, hoja) if p.suffix.lower() in (".xlsx", ".xlsm", ".xls") else _tabla_csv(p))
    return {"archivo": p.name, "columnas": list(d.columns), "filas": int(len(d)), "vista": d.head(n).astype(str).values.tolist(), **info}


def leer(ruta, hoja=None, config=None, tipo_defecto=None, guardar=True):
    """Lee un archivo y deja sus series en memoria. `config` (opcional, tras una confirmación): {col_fecha, col_valor, tipo, estacion_col, nombre}.
    Devuelve {estado: ok|confirmar|error, series: [...], mensaje, ...}. Nunca modifica el archivo."""
    p = Path(ruta); config = config or {}
    if not p.is_file():
        return {"archivo": str(ruta), "estado": "error", "mensaje": "No existe el archivo."}
    if p.suffix.lower() not in (".csv", ".txt", ".xlsx", ".xlsm", ".xls"):
        return {"archivo": p.name, "estado": "error", "mensaje": f"Formato {p.suffix or '(sin extensión)'} no soportado: usa Excel (.xlsx) o CSV."}
    origen = {"archivo": p.name, "ruta": str(p), "sha256": PR.sha256(p), "hoja": hoja}
    try:
        # 1) formatos conocidos de lluvia (anuario INAMHI ancho / largo con estaciones)
        if not config:
            clase = PR.clasificar_archivo(p)
            if clase["tipo"] == "precipitacion_ancha_inamhi":
                r = PR.leer_precip_ancha(p, hoja or next((h["hoja"] for h in clase["hojas"] if h["tipo"] == "precipitacion_ancha_inamhi"), None))
                return _desde_largo(r, origen, f"anuario INAMHI (año/mes × 31 días) · hoja {r['hoja']}")
        d, info = (_tabla_excel(p, hoja) if p.suffix.lower() in (".xlsx", ".xlsm", ".xls") else _tabla_csv(p))
        origen["hoja"] = info.get("hoja", hoja)
        return _desde_tabla(d, info, origen, p, {**config, "_tipo_defecto": tipo_defecto, "_guardar": guardar})
    except PremoduloError as e:
        return {"archivo": p.name, "estado": "error", "mensaje": str(e)}
    except Exception as e:
        return {"archivo": p.name, "estado": "error", "mensaje": f"No se pudo leer: {str(e)[:200]}"}


def _desde_largo(r, origen, formato):
    largo = r["largo"]; metas = []; avisos = list(r.get("problemas") or [])
    cat = r["catalogo"].set_index("estacion") if "estacion" in r["catalogo"].columns else None
    for est, g in largo.groupby("estacion"):
        x = g.drop_duplicates("fecha").set_index("fecha")["precipitacion_mm"].sort_index()
        x.index = pd.to_datetime(x.index).tz_localize(None) if getattr(x.index, "tz", None) else pd.to_datetime(x.index)
        nombre = f"{est}" + (f" · {cat.loc[est, 'nombre']}" if cat is not None and est in cat.index and isinstance(cat.loc[est, "nombre"], str) else "")
        try:
            metas.append(_registrar(f"lluvia:{_slug(est)}", nombre, "lluvia", x, origen, {"formato": formato}))
        except PremoduloError as e:
            avisos.append(str(e))
    if not metas:
        return {"archivo": origen["archivo"], "estado": "error", "mensaje": "No se obtuvo ninguna serie válida. " + " ".join(avisos[:2])}
    _guardar_disco()
    return {"archivo": origen["archivo"], "estado": "ok", "formato": formato, "series": [m["id"] for m in metas], "avisos": avisos[:5], "mensaje": f"{len(metas)} estación(es) de lluvia cargadas ({formato})."}


def _desde_tabla(d, info, origen, p, config):
    cols = list(d.columns); n = {c: _norm(c) for c in cols}
    col_f = config.get("col_fecha") or next((c for c in cols if re.fullmatch(r"fecha|date|datetime|fecha hora|fecha y hora|time|tiempo|dia|periodo|timestamp", n[c]) or n[c].startswith("fecha")), None)
    fechas, finfo = None, {}
    if col_f:
        fechas, finfo = _fechas(d[col_f])
    else:                                                                                   # año / mes / día en columnas separadas
        ca = next((c for c in cols if n[c] in ("anio", "ano", "year", "a o")), None); cm = next((c for c in cols if n[c] in ("mes", "month")), None); cd = next((c for c in cols if n[c] in ("dia", "day")), None)
        if ca and cm and cd:
            fechas = pd.to_datetime(dict(year=_a_num(d[ca]), month=_a_num(d[cm]), day=_a_num(d[cd])), errors="coerce"); finfo = {"validas_pct": round(100 * float(fechas.notna().mean()), 1), "ambigua": False}; col_f = f"{ca}/{cm}/{cd}"
    if fechas is None or finfo.get("validas_pct", 0) < 60:
        return _pedir(d, info, p, "No pude identificar la columna de fechas (o menos del 60 % son fechas válidas).", cols, None)
    if re.search(r"(^|[_\-\s])(resumen|summary|estadistic|stats|metadata|metadatos|catalogo)([_\-\s.]|$)", _norm(Path(p).stem).replace(" ", "_") + "_") or fechas.dropna().nunique() < 30:
        return {"archivo": Path(p).name, "estado": "error", "mensaje": "Parece una tabla resumen (o tiene menos de 30 fechas distintas), no una serie: no se carga."}
    excluir = {c for c in cols if c == col_f or re.fullmatch(r"fecha.*|date.*|anio|ano|year|mes|month|dia|day|hora|lon.*|lat.*|altitud.*|codigo|id|estacion|station|nombre.*", n[c])}
    est_col = config.get("estacion_col") or next((c for c in cols if re.fullmatch(r"estacion|station|codigo estacion|cod estacion|codigo|id estacion|estacion id", n[c])), None)
    num = {c: _a_num(d[c]) for c in cols if c not in excluir or c == config.get("col_valor")}
    cand = [c for c, v in num.items() if v.notna().mean() >= 0.3]          # G5 (Delta): antes 0.6; ahora se avisa si < 60 %
    if config.get("col_valor"):
        cand = [config["col_valor"]]
    if not cand:
        return _pedir(d, info, p, "No hay columnas numéricas con datos para usar como valores.", cols, fechas)
    metas, avisos, pendientes = [], [], []
    avisos += [f"{c}: solo {100 * num[c].notna().mean():.0f} % de filas con valor (se carga; revisa los vacíos)." for c in cand if c in num and num[c].notna().mean() < 0.6]
    base = Path(p).stem
    for c in cand:
        tipo = config.get("tipo") or _tipo_por_nombre(c) or (_tipo_por_nombre(base) if len(cand) == 1 else None) or config.get("_tipo_defecto")
        if tipo not in TIPOS:
            pendientes.append(c); continue
        v = num[c]
        grupos = [(None, slice(None))]
        if est_col and 1 <= d[est_col].nunique() < 500:
            grupos = [(e, d[est_col] == e) for e in d[est_col].dropna().unique()]
        for est, sel in grupos:
            f = fechas[sel] if est is not None else fechas; vv = v[sel] if est is not None else v
            x, linfo = _a_diaria(f, vv, tipo)
            if est is not None:
                nombre = f"{est}" + (f" · {c}" if len(cand) > 1 else "")
                sid = f"{tipo}:{_slug(est)}" + (f"_{_slug(c)}" if len(cand) > 1 else "")
            else:
                nombre = f"{base} · {c}" if len(cand) > 1 else base
                sid = f"{tipo}:{_slug(base)}" + (f"_{_slug(c)}" if len(cand) > 1 else "")
            nombre = config.get("nombre") or nombre
            try:
                metas.append(_registrar(sid, nombre, tipo, x, {**origen, "columna_fecha": col_f, "columna_valor": c}, {**linfo, **finfo, **{k: v2 for k, v2 in info.items() if k in ("codificacion", "separador", "fila_encabezado")}}))
            except PremoduloError as e:
                avisos.append(str(e))
    if pendientes and not metas:
        return _pedir(d, info, p, f"No sé qué es {', '.join('«' + c + '»' for c in pendientes[:4])}: ¿lluvia, caudal o nivel?", cols, fechas, candidatos=pendientes, col_fecha=col_f)
    if not metas:
        return {"archivo": origen["archivo"], "estado": "error", "mensaje": "No se obtuvo ninguna serie válida. " + " ".join(avisos[:2])}
    if config.get("_guardar", True):
        _guardar_disco()
    if finfo.get("ambigua"):
        avisos.append("Las fechas tipo 01/02/2020 son ambiguas: se interpretaron como " + ("día/mes/año" if finfo.get("dia_primero") else "mes/día/año") + ". Verifícalo en el gráfico.")
    for m in metas:
        L = m["lectura"]
        if L.get("agregado"): avisos.append(f"{m['nombre']}: {L['paso'] if L['paso'].startswith('lecturas') else 'registros cada ' + L['paso']} agregados a diario (día válido con ≥ 80 % de registros)" + (f"; {L['centinelas_anulados']} códigos de «sin dato» anulados." if L.get("centinelas_anulados") else "."))
        if L.get("negativos_anulados"): avisos.append(f"{m['nombre']}: {L['negativos_anulados']} valores negativos anulados.")
        if L.get("conflictos_vacios"): avisos.append(f"{m['nombre']}: {L['conflictos_vacios']} fechas repetidas con valores distintos quedaron vacías.")
    if pendientes:
        avisos.append("Columnas sin identificar (no cargadas): " + ", ".join(pendientes[:5]) + ".")
    return {"archivo": origen["archivo"], "estado": "ok", "series": [m["id"] for m in metas], "avisos": avisos[:8], "mensaje": f"{len(metas)} serie(s) cargada(s)."}


def _pedir(d, info, p, motivo, cols, fechas, candidatos=None, col_fecha=None):
    return {"archivo": Path(p).name, "ruta": str(p), "estado": "confirmar", "mensaje": motivo, "columnas": cols, "candidatos": candidatos or cols, "col_fecha": col_fecha, "vista": d.head(8).astype(str).values.tolist(),
            "info": {k: v for k, v in info.items() if k != "hojas"}, "hojas": info.get("hojas"), "tipos": {k: v[1] for k, v in TIPOS.items()}}


def leer_varios(rutas, hoja=None):
    res = [leer(r, hoja) for r in rutas]
    return {"resultados": res, "memoria": memoria(), "ok": sum(r["estado"] == "ok" for r in res), "por_confirmar": sum(r["estado"] == "confirmar" for r in res), "errores": sum(r["estado"] == "error" for r in res)}


def leer_carpeta(carpeta, maximo=2000):
    c = Path(carpeta)
    if not c.is_dir():
        raise PremoduloError("No existe esa carpeta.")
    arch = [f for f in sorted(c.rglob("*")) if f.is_file() and f.suffix.lower() in (".csv", ".txt", ".xlsx", ".xlsm") and not f.name.startswith(("~$", "."))][:maximo]
    if not arch:
        raise PremoduloError("La carpeta no tiene archivos Excel/CSV.")
    return leer_varios([str(a) for a in arch])


# ------------------------------------------------------------------------------------------------ carga masiva (cientos de estaciones), en segundo plano
LOTE = {"activo": False, "total": 0, "hechos": 0, "actual": "", "ok": 0, "confirmar": 0, "errores": 0, "series": 0, "resultados": [], "catalogo": None, "inicio": None, "fin": None}


def _es_catalogo(p):
    """¿Archivo de catálogo de estaciones (código + lon/lat o x/y)? Devuelve DataFrame[codigo, lon, lat, nombre?] o None."""
    try:
        d, _ = (_tabla_excel(p) if p.suffix.lower() in (".xlsx", ".xlsm", ".xls") else _tabla_csv(p))
    except Exception:
        return None
    n = {c: _norm(c) for c in d.columns}
    cod = next((c for c in d.columns if re.fullmatch(r"codigo|cod|code|id|estacion|station|codigo estacion", n[c])), None)
    lon = next((c for c in d.columns if re.fullmatch(r"lon|long|longitud|longitude|x", n[c])), None)
    lat = next((c for c in d.columns if re.fullmatch(r"lat|latitud|latitude|y", n[c])), None)
    if not (cod and lon and lat) or len(d) < 2:
        return None
    if any(re.fullmatch(r"fecha.*|date.*", n[c]) for c in d.columns):
        return None
    nom = next((c for c in d.columns if re.fullmatch(r"nombre|name|estacion nombre|nombre estacion", n[c]) and c != cod), None)
    out = pd.DataFrame({"codigo": d[cod].astype(str).str.strip(), "lon": _a_num(d[lon]), "lat": _a_num(d[lat])})
    if nom:
        out["nombre"] = d[nom].astype(str)
    out = out.dropna(subset=["lon", "lat"])
    if out.empty or not (out.lon.abs() <= 180).all():                         # x/y en metros: se guardan tal cual con aviso
        return out.assign(crs="desconocido (no geográfico)")
    return out.assign(crs="EPSG:4326")


def _coordenadas(cat):
    """Pone lon/lat a las series de la memoria cuyo código coincide con el catálogo."""
    if cat is None or cat.empty:
        return 0
    idx = {_slug(c).lower(): r for c, r in zip(cat["codigo"], cat.to_dict("records"))}
    n = 0
    for sid, e in _MEM["series"].items():
        cod = sid.split(":", 1)[-1].split("__")[0].lower()
        r = idx.get(cod) or next((v for k, v in idx.items() if k and (cod.startswith(k + "_") or cod == k)), None)
        if r:
            e["meta"].update(lon=float(r["lon"]), lat=float(r["lat"]), crs_coordenadas=r.get("crs")); n += 1
    return n


def iniciar_lote(rutas=None, carpeta=None, tipo_defecto=None, hoja=None):
    import threading
    if LOTE["activo"]:
        raise PremoduloError("Ya hay una carga masiva en curso.")
    if carpeta:
        c = Path(carpeta)
        if not c.is_dir():
            raise PremoduloError("No existe esa carpeta.")
        rutas = [str(f) for f in sorted(c.rglob("*")) if f.is_file() and f.suffix.lower() in (".csv", ".txt", ".xlsx", ".xlsm", ".xls") and not f.name.startswith(("~$", "."))]
    rutas = list(rutas or [])
    if not rutas:
        raise PremoduloError("No hay archivos Excel/CSV para leer.")
    if tipo_defecto not in (None, "", *TIPOS):
        raise PremoduloError("Tipo por defecto no válido (lluvia, caudal o nivel).")
    LOTE.update(activo=True, total=len(rutas), hechos=0, actual="", ok=0, confirmar=0, errores=0, series=0, resultados=[], catalogo=None, inicio=datetime.now().isoformat(timespec="seconds"), fin=None)

    def correr():
        _cargar_disco(); cat = []
        try:
            for r in rutas:
                p = Path(r); LOTE["actual"] = p.name
                c = _es_catalogo(p) if p.suffix.lower() in (".csv", ".txt", ".xlsx", ".xlsm", ".xls") else None
                if c is not None:
                    cat.append(c); res = {"archivo": p.name, "estado": "ok", "mensaje": f"catálogo de {len(c)} estaciones (coordenadas)", "catalogo": True}
                else:
                    res = leer(r, hoja, None, tipo_defecto or None, guardar=False)
                LOTE["hechos"] += 1; LOTE[{"ok": "ok", "confirmar": "confirmar"}.get(res["estado"], "errores")] += 1
                LOTE["series"] += len(res.get("series") or [])
                LOTE["resultados"].append({k: res.get(k) for k in ("archivo", "ruta", "estado", "mensaje", "series", "avisos", "columnas", "candidatos", "col_fecha", "vista", "tipos", "catalogo")})
            if cat:
                todo = pd.concat(cat, ignore_index=True).drop_duplicates("codigo")
                LOTE["catalogo"] = {"estaciones": int(len(todo)), "con_coordenadas": _coordenadas(todo)}
            _guardar_disco()
        finally:
            LOTE.update(activo=False, actual="", fin=datetime.now().isoformat(timespec="seconds"))
    threading.Thread(target=correr, daemon=True).start()
    return {"total": len(rutas)}


def estado_lote(desde=0):
    r = {k: v for k, v in LOTE.items() if k != "resultados"}
    r["resultados"] = LOTE["resultados"][int(desde):]
    return r


# ------------------------------------------------------------------------------------------------ gráficos (mismo cálculo que el resto del programa)
def datos_lluvia(sid):
    return SER.lluvia_serie(serie(sid), sid)


def datos_caudal(sid):
    return SER.caudal_serie(serie(sid), sid)


def catalogo_series():
    """Mismo formato que /api/series/catalogo (para reutilizar el dibujo de series y tendencias)."""
    m = memoria()["series"]
    return {"series": [{"id": s["id"], "nombre": s["nombre"], "tipo": s["tipo"], "unidad": s["unidad"], "inicio": s["inicio"], "fin": s["fin"], "n": s["n"]} for s in m if s["tipo"] in ("lluvia", "caudal")]}


# ------------------------------------------------------------------------------------------------ llevar la memoria a un proyecto
def _dist_km(lon1, lat1, lon2, lat2):
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2); dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, a)))


def guardar_en_proyecto(carpeta, ids=None, cerca=None, radio_km=100.0):
    """Escribe las series de la memoria en <proyecto>/datos/series_premodulo/ (CSV diario + índice con origen y hash). Nada se sobrescribe: si ya existe, se agrega sufijo con marca de tiempo.
    8.0.1: con `cerca=(lon, lat)` y sin `ids`, no copia las series con coordenadas a más de `radio_km` del sitio (en Yaguachi se copiaban las 257 de Pichincha).
    Las series sin coordenadas sí se copian, porque no se puede saber dónde están; se cuentan aparte para avisar."""
    _cargar_disco()
    lejanas, sin_coord = [], []
    if ids is None and cerca is not None:
        ids = []
        for sid, e in _MEM["series"].items():
            lo, la = e["meta"].get("lon"), e["meta"].get("lat")
            if lo is None or la is None:
                sin_coord.append(sid); ids.append(sid)
            elif _dist_km(float(cerca[0]), float(cerca[1]), float(lo), float(la)) <= radio_km:
                ids.append(sid)
            else:
                lejanas.append(sid)
        if not ids:
            return {"guardadas": [], "carpeta": None, "lejanas": len(lejanas), "sin_coordenadas": 0, "radio_km": radio_km}
    ids = ids or list(_MEM["series"])
    dest = Path(carpeta) / "datos" / "series_premodulo"; dest.mkdir(parents=True, exist_ok=True)
    idx_f = dest / "indice.json"; idx = json.loads(idx_f.read_text(encoding="utf-8")) if idx_f.exists() else []
    hechos = []
    for sid in ids:
        e = _MEM["series"].get(sid)
        if not e:
            continue
        m = dict(e["meta"]); f = dest / f"{m['slug']}.csv"
        if f.exists():
            f = dest / f"{m['slug']}_{datetime.now():%Y%m%d_%H%M%S}.csv"
        e["serie"].rename("valor").rename_axis("fecha").reset_index().to_csv(f, index=False)
        m["archivo"] = f.name; idx = [i for i in idx if i.get("id") != sid] + [m]; hechos.append(sid)
    idx_f.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"guardadas": hechos, "carpeta": str(dest), "lejanas": len(lejanas), "sin_coordenadas": len(sin_coord), "radio_km": radio_km}
