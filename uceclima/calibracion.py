# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Calibración de hidro con datos (módulo aditivo; no cambia corridas ni resultados existentes).

El programa propone y mide; la persona decide. Pasos:
  1. registrar_observacion   copia la serie de caudal al proyecto y registra QUÉ es (tipo, fuente, estación) y si la persona
                             confirma su identidad. Sin confirmación la serie queda como candidata y no entra a ninguna métrica.
  2. eventos                 identifica eventos en la serie observada y propone una partición AJUSTE / VALIDACIÓN (editable).
  3. barrido                 la persona fija rangos de CN, lag, PRF y λ; se evalúan todas las combinaciones con el modelo agregado
                             de eventos (pérdidas SCS-CN + HU SCS triangular de matematica_propia) y se miden NSE, KGE, PBIAS,
                             error de pico y de volumen POR SEPARADO en ajuste y validación.
  4. aceptar                 la persona elige una combinación; se registra quién, cuándo y con qué métricas. Nada se activa solo.

Modelo de evento (declarado): Q_sim(t) = Q_base + Q_directo(t); Q_base = caudal observado al inicio del evento (constante);
Q_directo = convolución del exceso SCS-CN acumulado desde el inicio del evento con el HU SCS triangular. Paso = el de la serie (diario).
Es un modelo agregado sencillo: los parámetros aceptados son «efectivos» para esta cuenca, datos y paso, no propiedades físicas medidas.

Delta (opciones declaradas, ninguna por defecto salvo que la persona las pida):
  D1 caudal base con recesión exponencial (k_rec="auto" usa k estimado de recesiones sin lluvia: p25, mediana, p75) y efecto en NSE.
  D2 paso horario cuando caudal y lluvia son horarios (paso detectado; si no, diario como Gamma); aviso de óptimo en el borde del rango.
  D3 humedad antecedente: "amc5" (CN por clase AMC I/II/III con lluvia de 5 días previos) o "api" (índice de lluvia antecedente
     continuo, k = 0,9 por día, mismos umbrales, CN interpolado entre I y III). Nunca por defecto.
  D4 control de calidad: coeficiente de escorrentía > 0,85 o ≥ 1, eventos con error de volumen > ±100 %, cobertura y peso de estaciones,
     eventos con «lluvia dudosa» (escorrentía directa del evento mayor que su lluvia).
"""
import itertools
import json
import math
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import matematica_propia as MP

TIPOS = {"caudal_rio_aforo": "Caudal de río en una estación de aforo",
         "afluente_embalse": "Caudal afluente a un embalse (medido o publicado por el operador)",
         "afluente_balance": "Afluente inferido por balance del embalse (cota-volumen + salidas)",
         "salida_embalse": "Caudal de salida de un embalse (turbinado/vertido): refleja la operación",
         "desconocido": "No se sabe qué representa"}
APTOS = {"caudal_rio_aforo", "afluente_embalse", "afluente_balance"}
MAX_COMBINACIONES = 5000


class CalibracionError(Exception):
    pass


def _sello():
    return time.strftime("%Y%m%d_%H%M%S")


def _nueva(base, prefijo):
    base.mkdir(parents=True, exist_ok=True)
    for k in range(60):
        d = base / f"{prefijo}{_sello()}{'' if k == 0 else f'_{k}'}"
        try:
            d.mkdir(); return d
        except FileExistsError:
            time.sleep(0.05)
    raise CalibracionError("no se pudo crear la carpeta")


def _tablas(df, ruta_sin_ext):
    df.to_csv(f"{ruta_sin_ext}.csv", index=False, encoding="utf-8-sig")
    try:
        df.to_excel(f"{ruta_sin_ext}.xlsx", index=False)
    except Exception:
        pass


# ------------------------------------------------------------------------------------------------ 1. observaciones
def vista_previa(ruta, hoja=None):
    ruta = Path(ruta)
    d = pd.read_excel(ruta, sheet_name=hoja or 0) if ruta.suffix.lower() in (".xlsx", ".xls", ".xlsm") else pd.read_csv(ruta, sep=None, engine="python", encoding="utf-8-sig")
    return {"columnas": [str(c) for c in d.columns], "filas": d.head(8).astype(str).values.tolist(), "n": int(len(d))}


def registrar_observacion(carpeta, ruta, col_fecha, col_caudal, tipo, fuente, estacion, confirmado=False, persona="", nota="", hoja=None, umbral_sospechoso=None):
    """Copia la serie (sin tocar el original) y escribe observaciones/aforos_caudal.csv (si existía, se guarda .bak con sello).
    identidad_confirmada = «si» solo si la persona lo confirma Y el tipo es apto para calibrar (no la salida de un embalse).
    umbral_sospechoso (m³/s, opcional, lo fija la persona): valores mayores se marcan «sospechoso» y no entran a las métricas."""
    if tipo not in TIPOS:
        raise CalibracionError("Tipo de serie no reconocido: " + ", ".join(TIPOS))
    if not str(fuente).strip() or not str(estacion).strip():
        raise CalibracionError("Declara la fuente y la estación/punto de la serie: son parte del registro.")
    carpeta = Path(carpeta); ruta = Path(ruta)
    if not ruta.exists():
        raise CalibracionError(f"No existe el archivo {ruta}")
    d = pd.read_excel(ruta, sheet_name=hoja or 0) if ruta.suffix.lower() in (".xlsx", ".xls", ".xlsm") else pd.read_csv(ruta, sep=None, engine="python", encoding="utf-8-sig")
    if col_fecha not in d.columns or col_caudal not in d.columns:
        raise CalibracionError(f"Columnas no encontradas. Disponibles: {list(map(str, d.columns))}")
    f = pd.to_datetime(d[col_fecha], errors="coerce", dayfirst=False)
    q = pd.to_numeric(d[col_caudal], errors="coerce")
    s = pd.DataFrame({"fecha": f, "caudal_m3s": q}).dropna(subset=["fecha"]).drop_duplicates("fecha").sort_values("fecha")
    invalidos = int((~np.isfinite(s.caudal_m3s) | (s.caudal_m3s < 0)).sum())
    s = s[np.isfinite(s.caudal_m3s) & (s.caudal_m3s >= 0)]
    if s.empty:
        raise CalibracionError("La serie no tiene caudales válidos.")
    s["calidad"] = "ok"
    if umbral_sospechoso:
        s.loc[s.caudal_m3s > float(umbral_sospechoso), "calidad"] = "sospechoso"
    apto = tipo in APTOS
    ident = "si" if (confirmado and apto) else "no"
    avisos = []
    if confirmado and not apto:
        avisos.append(f"El tipo «{TIPOS[tipo]}» no es apto para calibrar el modelo de lluvia-escorrentía: la serie queda registrada como NO confirmada.")
    if not confirmado:
        avisos.append("Identidad sin confirmar: la serie queda como candidata y no entra en métricas ni barridos.")
    avisos += saltos_de_unidad(s.set_index("fecha").caudal_m3s)
    s["identidad_confirmada"] = ident; s["tipo"] = tipo; s["estacion"] = estacion; s["fuente"] = fuente
    obs = carpeta / "observaciones"; (obs / "originales").mkdir(parents=True, exist_ok=True)
    copia = obs / "originales" / f"{_sello()}_{ruta.name}"; shutil.copy2(ruta, copia)
    dest = obs / "aforos_caudal.csv"
    if dest.exists():
        shutil.copy2(dest, obs / f"aforos_caudal.csv.bak_{_sello()}")
    s.assign(fecha=s.fecha.dt.strftime("%Y-%m-%d %H:%M:%S")).to_csv(dest, index=False)
    reg = {"fecha_registro": time.strftime("%Y-%m-%dT%H:%M:%S"), "archivo_original": str(ruta), "copia": str(copia.relative_to(carpeta)), "columna_fecha": col_fecha, "columna_caudal": col_caudal,
           "tipo": tipo, "tipo_texto": TIPOS[tipo], "fuente": fuente, "estacion": estacion, "identidad_confirmada": ident, "persona": persona, "nota": nota,
           "n_validos": int(len(s)), "n_invalidos_descartados": invalidos, "n_sospechosos": int((s.calidad == "sospechoso").sum()), "umbral_sospechoso_m3s": umbral_sospechoso,
           "periodo": [str(s.fecha.min()), str(s.fecha.max())], "avisos": avisos}
    hist = obs / "registro_observaciones.json"
    h = json.loads(hist.read_text(encoding="utf-8")) if hist.exists() else []
    h.append(reg); hist.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
    return reg


def saltos_de_unidad(q, factor=200.0):
    """G22 (Delta): avisa si la mediana anual cambia por un factor >= 200 entre años seguidos (típico L/s frente a m³/s en EPMAPS).
    No corrige nada: la persona decide qué periodo vale."""
    m = q[q > 0].groupby(q[q > 0].index.year).median()
    out = []
    for (a0, v0), (a1, v1) in zip(m.items(), list(m.items())[1:]):
        r = v1 / v0 if v0 > 0 else np.inf
        if r >= factor or r <= 1 / factor:
            out.append(f"Posible salto de unidad entre {a0} y {a1}: la mediana anual pasa de {v0:.4g} a {v1:.4g} (×{r:.3g}). Revisa si un periodo está en L/s.")
    return out


def observaciones(carpeta):
    """Serie confirmada y apta (sin sospechosos) como Series diaria sin zona horaria, o (None, motivo)."""
    f = Path(carpeta) / "observaciones" / "aforos_caudal.csv"
    if not f.exists():
        return None, "No hay serie de caudal registrada en el proyecto."
    d = pd.read_csv(f)
    if "identidad_confirmada" not in d.columns:
        return None, "aforos_caudal.csv sin columna identidad_confirmada."
    d = d[d.identidad_confirmada.astype(str).str.lower().isin(["si", "sí", "true", "1"])]
    if "calidad" in d.columns:
        d = d[d.calidad != "sospechoso"]
    if d.empty:
        return None, "La serie registrada no tiene identidad confirmada (o todos sus valores son sospechosos)."
    s = pd.Series(pd.to_numeric(d.caudal_m3s, errors="coerce").values, index=pd.to_datetime(d.fecha)).dropna().sort_index()
    return s[~s.index.duplicated()], f"{len(s)} valores confirmados"


def registrar_lluvia(carpeta, ruta, col_fecha, col_mm, estacion, fuente, persona="", nota="", col_estacion=None, hoja=None):
    """Lluvia diaria de UNA estación como forzamiento de la calibración (alternativa a CHIRPS sobre la cuenca).
    Se copia normalizada a observaciones/lluvia_estacion_<sello>.csv y queda como fuente activa. Es lluvia PUNTUAL: no equivale a la media areal."""
    carpeta = Path(carpeta); ruta = Path(ruta)
    if not str(estacion).strip() or not str(fuente).strip():
        raise CalibracionError("Declara la estación y la fuente de la lluvia.")
    if not ruta.exists():
        raise CalibracionError(f"No existe el archivo {ruta}")
    d = pd.read_excel(ruta, sheet_name=hoja or 0) if ruta.suffix.lower() in (".xlsx", ".xls", ".xlsm") else pd.read_csv(ruta, sep=None, engine="python", encoding="utf-8-sig")
    if col_fecha not in d.columns or col_mm not in d.columns:
        raise CalibracionError(f"Columnas no encontradas. Disponibles: {list(map(str, d.columns))}")
    if col_estacion:
        d = d[d[col_estacion].astype(str) == str(estacion)]
    s = pd.DataFrame({"fecha": pd.to_datetime(d[col_fecha], errors="coerce"), "lluvia_mm": pd.to_numeric(d[col_mm], errors="coerce")}).dropna().drop_duplicates("fecha").sort_values("fecha")
    s = s[s.lluvia_mm >= 0]
    if s.empty:
        raise CalibracionError("La serie de lluvia no tiene valores válidos (¿filtro de estación?).")
    obs = carpeta / "observaciones"; obs.mkdir(parents=True, exist_ok=True)
    f = obs / f"lluvia_estacion_{_sello()}.csv"; s.assign(fecha=s.fecha.dt.strftime("%Y-%m-%d")).to_csv(f, index=False)
    act = {"fuente": "estacion", "tipo_registro": "estacion", "archivo": f.name, "estacion": estacion, "origen": fuente, "archivo_original": str(ruta), "persona": persona, "nota": nota,
           "fecha_registro": time.strftime("%Y-%m-%dT%H:%M:%S"), "n_dias": int(len(s)), "periodo": [str(s.fecha.min().date()), str(s.fecha.max().date())],
           "aviso": "Lluvia PUNTUAL de una estación usada como lluvia media de la cuenca: supuesto de representatividad declarado por la persona."}
    (obs / "lluvia_activa.json").write_text(json.dumps(act, ensure_ascii=False, indent=2), encoding="utf-8")
    return act


def usar_lluvia(carpeta, fuente):
    """Elige el forzamiento: «chirps» (media areal CHIRPS sobre la cuenca) o «estacion» (la última registrada)."""
    f = Path(carpeta) / "observaciones" / "lluvia_activa.json"
    if fuente not in ("chirps", "estacion", "areal"):
        raise CalibracionError("fuente debe ser «chirps», «estacion» o «areal».")
    if not f.exists():
        if fuente != "chirps":
            raise CalibracionError("No hay lluvia de estación ni areal registrada.")
        return {"fuente": "chirps"}
    a = json.loads(f.read_text(encoding="utf-8"))
    a["fuente"] = "chirps" if fuente == "chirps" else a.get("tipo_registro", fuente)
    f.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
    return a


def lluvia_cuenca(carpeta):
    """Forzamiento activo: lluvia de estación registrada (si la persona la eligió) o la última CHIRPS promediada sobre la cuenca."""
    act = Path(carpeta) / "observaciones" / "lluvia_activa.json"
    if act.exists():
        a = json.loads(act.read_text(encoding="utf-8"))
        if a.get("fuente") in ("estacion", "areal"):
            d = pd.read_csv(Path(carpeta) / "observaciones" / a["archivo"])
            s_ = pd.Series(d.lluvia_mm.values, index=pd.to_datetime(d.fecha)).sort_index()
            if a["fuente"] == "areal":
                return s_, f"Lluvia areal {a['estacion']} sobre la cuenca activa"
            return s_, f"Estación {a['estacion']} ({a['origen']}) · lluvia PUNTUAL usada como media de la cuenca"
    from .cuenca import ultima_descarga
    f = ultima_descarga(carpeta, "chirps_cuenca", "chirps_cuenca_diario.csv")
    if not f:
        return None, "No hay lluvia areal de la cuenca: descarga «CHIRPS sobre la cuenca» en el módulo Cuenca."
    d = pd.read_csv(f)
    return pd.Series(d.lluvia_cuenca_mm.values, index=pd.to_datetime(d.fecha)).sort_index(), "CHIRPS media areal sobre la cuenca · " + str(f)


# ------------------------------------------------------------------------------------------------ 2. eventos
def eventos(q, p, percentil=90.0, dias_antes=10, dias_despues=20, separacion_dias=30, max_eventos=40, cada_validacion=3, area_km2=None, paso_h=None):
    """Picos de caudal sobre el percentil dado, separados al menos `separacion_dias`. Ventana = [mínimo en los `dias_antes` previos, pico + `dias_despues`].
    Partición propuesta: uno de cada `cada_validacion` eventos (en orden cronológico) va a VALIDACIÓN; el resto a AJUSTE. Todo es editable."""
    paso_h = float(paso_h or detectar_paso(q, p)); fr = "D" if paso_h >= 24 else f"{int(paso_h)}h"; por_dia = 24.0 / paso_h
    q = q.asfreq(fr); p = p.asfreq(fr)
    umbral = float(np.nanpercentile(q.values, percentil))
    cand = q[(q > umbral) & (q == q.rolling(int(2 * separacion_dias * por_dia + 1), center=True, min_periods=1).max())].sort_values(ascending=False)
    elegidos = []
    for t in cand.index:
        if all(abs((t - u).days) >= separacion_dias for u in elegidos):
            elegidos.append(t)
        if len(elegidos) >= max_eventos:
            break
    filas = []
    for t in sorted(elegidos):
        pre = q[t - pd.Timedelta(days=dias_antes):t]
        if pre.isna().all():
            continue
        ini = pre.idxmin(); fin = t + pd.Timedelta(days=dias_despues)
        qq = q[ini:fin]; pp = p.reindex(pd.date_range(ini, fin, freq=fr))
        if qq.isna().mean() > 0.1 or len(qq) < 5:
            continue
        cob = float(pp.notna().mean() * 100); conl = float((pp > 0.1).mean() * 100)
        fmt = (lambda x: str(x.date())) if paso_h >= 24 else (lambda x: x.strftime("%Y-%m-%d %H:%M"))
        f = {"evento": f"E{len(filas) + 1:02d}", "inicio": fmt(ini), "pico": fmt(t), "fin": fmt(fin), "Q_pico_m3s": round(float(q[t]), 2),
             "Q_base_m3s": round(float(q[ini]), 2), "P_total_mm": round(float(pp.sum()), 1), "cobertura_lluvia_pct": round(cob, 0), "dias_con_lluvia_pct": round(conl, 0), "motivo": ""}
        if area_km2 and float(pp.sum()) > 0:                                        # D4: escorrentía directa del evento frente a su lluvia
            qdir = float((qq - qq.iloc[0]).clip(lower=0).sum()) * paso_h * 3600 / (float(area_km2) * 1e3)
            f["escorrentia_directa_mm"] = round(qdir, 1)
            if qdir > float(pp.sum()):
                f["lluvia_dudosa"] = True; f["aviso"] = f"lluvia dudosa: escorrentía directa {qdir:.0f} mm > lluvia {float(pp.sum()):.0f} mm"
        if cob == 0 or float(pp.sum()) <= 0:
            f["motivo"] = "sin lluvia en la ventana"
        elif cob < 80:
            f["motivo"] = f"cobertura de lluvia {cob:.0f} % (< 80 %)"
        filas.append(f)
    k = 0
    for f in filas:
        if f["motivo"] == "sin lluvia en la ventana":
            f["rol"] = "excluido"; continue
        f["rol"] = "validacion" if (k % cada_validacion) == cada_validacion - 1 else "ajuste"; k += 1
    return {"eventos": filas, "umbral_m3s": round(umbral, 2), "criterios": {"percentil": percentil, "dias_antes": dias_antes, "dias_despues": dias_despues, "separacion_dias": separacion_dias,
            "cada_validacion": cada_validacion, "paso_h": paso_h}, "nota": "Partición propuesta (uno de cada %d a validación, en orden cronológico). Revísala: la decides tú. "
            "Los eventos marcados «lluvia dudosa» no se excluyen solos: si los excluyes, quedan registrados con ese motivo." % cada_validacion}


# ------------------------------------------------------------------------------------------------ 3. modelo de evento y barrido
def caudal_base(q0, n, dt_h, k_rec_d=None):
    """Caudal base del evento: constante (k None) o recesión exponencial Q0·exp(−t/k), t en días (C13)."""
    if k_rec_d is None or not np.isfinite(k_rec_d) or k_rec_d <= 0:
        return np.full(n, float(q0))
    t = np.arange(n) * dt_h / 24.0
    return float(q0) * np.exp(-t / float(k_rec_d))


AMC_UMBRALES_MM = (35.6, 53.3)          # lluvia de 5 días previos (temporada de crecimiento, NEH-4): < 35,6 AMC I; > 53,3 AMC III
HUMEDAD = {"ninguna": "CN constante (AMC II), como Gamma", "amc5": "CN por clase AMC I/II/III con la lluvia de los 5 días previos",
           "api": "CN interpolado entre AMC I y III con el índice de lluvia antecedente continuo (k = 0,9 por día)"}


def cn_amc(cn, clase):
    """Conversión de CN (AMC II) a AMC I o III (Chow, Maidment y Mays 1988; NEH-4)."""
    cn = float(cn)
    if clase == "I":
        return cn / (2.281 - 0.01281 * cn)
    if clase == "III":
        return min(cn / (0.427 + 0.00573 * cn), 99.0)
    return cn


def cn_efectivo(cn, e, modo):
    """CN del evento según la humedad antecedente declarada. Sin dato antecedente se usa AMC II y se informa en e['amc_aviso']."""
    if modo in (None, "", "ninguna"):
        return float(cn)
    lo, hi = AMC_UMBRALES_MM
    if modo == "amc5":
        p5 = e.get("p_ant5_mm")
        if p5 is None or not np.isfinite(p5):
            return float(cn)
        return cn_amc(cn, "I" if p5 < lo else ("III" if p5 > hi else "II"))
    if modo == "api":
        a = e.get("api_mm")
        if a is None or not np.isfinite(a):
            return float(cn)
        if a <= lo:
            return cn_amc(cn, "I") + (float(cn) - cn_amc(cn, "I")) * max(a, 0) / lo
        return float(cn) + (cn_amc(cn, "III") - float(cn)) * min((a - lo) / (hi - lo), 1.0)
    raise CalibracionError("Humedad antecedente no reconocida: " + ", ".join(HUMEDAD))


def simular_e(e, area, params, dt_h):
    """Simula un evento preparado con la tupla de parámetros (CN, lag, PRF, λ[, k][, humedad])."""
    k = params[4] if len(params) > 4 else None; hum = params[5] if len(params) > 5 else "ninguna"
    return simular_evento(e["p"], e["q"][0], area, cn_efectivo(params[0], e, hum), params[1], params[2], params[3], dt_h, k)


def simular_evento(p_mm, q_base, area_km2, cn, lag_h, prf, lam, dt_h, k_rec_d=None):
    pe = MP.perdidas_scs(np.cumsum(p_mm), cn, lam=lam)["exceso_inc_mm"]
    u = MP.uh_scs(area_km2, lag_h, dt_h, prf)["u_m3s_mm"]
    qd = np.convolve(pe, u)[:len(p_mm)]
    return caudal_base(q_base, len(p_mm), dt_h, k_rec_d) + qd


def k_recesion(q, p=None, min_dias=3, umbral_lluvia_mm=0.5):
    """Constante de recesión (días) estimada de tramos de ≥ min_dias con caudal decreciente y sin lluvia: k = −1/ln(Q_t+1/Q_t), mediana."""
    q = q.asfreq("D"); seco = (p.reindex(q.index).fillna(0) <= umbral_lluvia_mm) if p is not None else pd.Series(True, index=q.index)
    r = q.shift(-1) / q; ok = (r > 0) & (r < 1) & seco & seco.shift(-1, fill_value=False) & q.notna()
    grupos = (ok != ok.shift()).cumsum()
    ks = []
    for _, g in r[ok].groupby(grupos[ok]):
        if len(g) >= min_dias:
            ks.extend((-1.0 / np.log(g.values)).tolist())
    if len(ks) < 5:
        return {"k_dias": None, "n": len(ks), "nota": "pocos tramos de recesión sin lluvia para estimar k"}
    ks = np.array(ks); ks = ks[np.isfinite(ks) & (ks > 0) & (ks < 1000)]
    return {"k_dias": round(float(np.median(ks)), 2), "p25": round(float(np.percentile(ks, 25)), 2), "p75": round(float(np.percentile(ks, 75)), 2), "n": int(len(ks)),
            "nota": "mediana de −1/ln(Q(t+1)/Q(t)) en tramos de ≥ %d días sin lluvia (≤ %.1f mm)" % (min_dias, umbral_lluvia_mm)}


def _metricas(o, s):
    o = np.asarray(o, float); s = np.asarray(s, float)
    if len(o) < 3 or o.std() == 0:
        return {"NSE": float("nan"), "KGE": float("nan"), "PBIAS_pct": float("nan")}
    e = s - o
    nse = 1 - float(np.sum(e ** 2)) / float(np.sum((o - o.mean()) ** 2))
    r = float(np.corrcoef(o, s)[0, 1]) if s.std() > 0 else float("nan")
    kge = 1 - math.sqrt((r - 1) ** 2 + (s.std() / o.std() - 1) ** 2 + (s.mean() / o.mean() - 1) ** 2) if np.isfinite(r) else float("nan")
    return {"NSE": nse, "KGE": kge, "PBIAS_pct": 100 * float(e.sum()) / float(o.sum())}


def _evaluar(evs, params, area, dt_h):
    res = {}
    for rol in ("ajuste", "validacion"):
        oo, ss, ep, ev = [], [], [], []
        for e in evs:
            if e["rol"] != rol:
                continue
            sim = simular_e(e, area, params, dt_h)
            b = caudal_base(e["q"][0], len(e["q"]), dt_h, params[4] if len(params) > 4 else None)
            oo.append(e["q"]); ss.append(sim)
            ep.append(100 * (sim.max() / e["q"].max() - 1))
            ev.append(100 * ((sim - b).sum() / max((e["q"] - b).clip(min=0).sum(), 1e-9) - 1))
        if not oo:
            res[rol] = None; continue
        m = _metricas(np.concatenate(oo), np.concatenate(ss))
        m.update({"n_eventos": len(oo), "error_pico_medio_abs_pct": float(np.mean(np.abs(ep))), "error_volumen_directo_medio_pct": float(np.mean(ev))})
        res[rol] = m
    return res


def detectar_paso(q, p):
    """Paso común (h): 1 si caudal y lluvia son horarios (o más finos), 24 en otro caso (Gamma)."""
    def med(s):
        d = pd.Series(s.index).diff().dropna()
        return float(d.median() / pd.Timedelta(hours=1)) if len(d) else 24.0
    return 1.0 if (med(q) <= 1.0 and med(p) <= 1.0) else 24.0


def preparar(carpeta, eventos_tabla=None):
    """Datos comunes del barrido y de las gráficas: (evs, excluidos, area, q, p, cuenca, mq, mp). Mismos criterios en ambos."""
    carpeta = Path(carpeta)
    q, mq = observaciones(carpeta)
    if q is None:
        raise CalibracionError(mq)
    p, mp_ = lluvia_cuenca(carpeta)
    if p is None:
        raise CalibracionError(mp_)
    act = carpeta / "cuenca" / "activa.json"
    if not act.exists():
        raise CalibracionError("No hay cuenca activa.")
    a = json.loads(act.read_text(encoding="utf-8"))
    if a["origen"] == "malla":
        raise CalibracionError("La cuenca activa es la malla CHIRPS: no es una cuenca hidrográfica y no se calibra contra un aforo. Carga o acepta una cuenca.")
    if a["origen"] == "mdt" and "ACEPTADA" not in a.get("etiqueta", ""):
        raise CalibracionError("La delineación automática aún no fue aceptada por la persona.")
    dt_h = detectar_paso(q, p); fr = "D" if dt_h >= 24 else "h"
    q = q.copy(); q.index = q.index.normalize() if dt_h >= 24 else q.index.floor("h"); q = q[~q.index.duplicated()]
    if dt_h < 24:
        p = p.copy(); p.index = p.index.floor("h"); p = p.groupby(level=0).sum(min_count=1)
    tabla = eventos_tabla or eventos(q, p, area_km2=a.get("area_km2"), paso_h=dt_h)["eventos"]
    qd = q.asfreq(fr); pd_ = p.asfreq(fr)
    pdia = p.resample("D").sum(min_count=1)
    api = pdia.fillna(0).ewm(alpha=0.1, adjust=False).mean() / 0.1                  # API_t = 0,9·API_{t−1} + P_t
    evs, excluidos = [], []
    for e in tabla:
        if e.get("rol") not in ("ajuste", "validacion"):
            continue
        i, f = pd.Timestamp(e["inicio"]), pd.Timestamp(e["fin"])
        qq, pp = qd[i:f], pd_.reindex(pd.date_range(i, f, freq=fr))
        if len(qq) < 5 or len(pp) == 0 or pp.notna().sum() == 0 or float(pp.fillna(0).sum()) <= 0:
            excluidos.append(f"{e['evento']} ({'sin lluvia' if len(pp) else 'fuera del periodo de lluvia'})"); continue
        if qq.isna().any() or pp.isna().any():
            qq = qq.interpolate(limit=2)
            if qq.isna().any() or pp.isna().any():
                excluidos.append(f"{e['evento']} (huecos en caudal o lluvia)"); continue
        ant = pdia[i.normalize() - pd.Timedelta(days=5):i.normalize() - pd.Timedelta(days=1)]
        p5 = float(ant.sum()) if len(ant) == 5 and ant.notna().all() else float("nan")
        a_ = api.get(i.normalize() - pd.Timedelta(days=1), float("nan"))
        evs.append({**e, "q": qq.values.astype(float), "p": pp.values.astype(float), "fechas": qq.index, "dt_h": dt_h, "p_ant5_mm": p5, "api_mm": float(a_)})
    return evs, excluidos, float(a["area_km2"]), q, p, a, mq, mp_, tabla


def _por_evento(evs, params, area, dt_h):
    out = []
    for e in evs:
        sim = simular_e(e, area, params, dt_h); b = caudal_base(e["q"][0], len(e["q"]), dt_h, params[4] if len(params) > 4 else None)
        vo = max(float((e["q"] - b).clip(min=0).sum()), 1e-9); out.append({"evento": e["evento"], "rol": e["rol"], "error_volumen_pct": 100 * (float((sim - b).sum()) / vo - 1)})
    return out


def _mejor_por(df, mascara):
    d = df[mascara]
    if d.empty:
        return None
    r = d.iloc[0]
    return {k: (None if pd.isna(r.get(k)) else round(float(r.get(k)), 3)) for k in ("CN", "lag_h", "k_rec_d", "KGE_ajuste", "KGE_validacion", "NSE_ajuste", "NSE_validacion", "PBIAS_pct_ajuste", "PBIAS_pct_validacion")}


def barrido(carpeta, cn=(50, 90, 9), lag_h=(6, 72, 12), prf=(484, 284), lam=(0.2, 0.05), eventos_tabla=None, persona="", k_rec=(None,), humedad=("ninguna",)):
    """Evalúa todas las combinaciones (rangos lineales `(min, max, n)` para CN y lag; listas para PRF y λ) sobre los eventos con su rol.
    Guarda calibracion/barridos/<sello>/ (config, eventos, resultados csv/xlsx). No elige nada: ordena por KGE de AJUSTE y muestra la validación al lado."""
    carpeta = Path(carpeta)
    tabla0 = eventos_tabla
    if tabla0 is not None:
        if not any(e["rol"] == "ajuste" for e in tabla0):
            raise CalibracionError("No hay eventos de AJUSTE.")
        if not any(e["rol"] == "validacion" for e in tabla0):
            raise CalibracionError("No hay eventos de VALIDACIÓN: reserva al menos uno (sin validación no hay calibración que reportar).")
    evs, excluidos, area, q, p, a, mq, mp_, tabla = preparar(carpeta, eventos_tabla)
    dt_h = float(evs[0]["dt_h"]) if evs else 24.0
    if not any(e["rol"] == "ajuste" for e in evs) or not any(e["rol"] == "validacion" for e in evs):
        raise CalibracionError("Tras excluir eventos sin lluvia o con huecos no quedan eventos de ajuste y de validación. Excluidos: " + ", ".join(excluidos[:10]))
    cns = np.linspace(*cn[:2], int(cn[2])); lags = np.linspace(*lag_h[:2], int(lag_h[2]))
    k_est = None
    if k_rec == "auto" or (isinstance(k_rec, (list, tuple)) and "auto" in k_rec):              # D1: k estimado de recesiones sin lluvia
        k_est = k_recesion(q.resample("D").mean(), p.resample("D").sum(min_count=1))
        k_rec = [None] + ([k_est["p25"], k_est["k_dias"], k_est["p75"]] if k_est.get("k_dias") else [])
    ks = sorted({None if (k in (None, "", "constante") or (isinstance(k, float) and not np.isfinite(k))) else round(float(k), 2) for k in (k_rec or (None,))}, key=lambda x: -1 if x is None else x)
    hums = [h for h in (humedad or ("ninguna",))]
    for h in hums:
        if h not in HUMEDAD:
            raise CalibracionError("Humedad antecedente no reconocida: " + ", ".join(HUMEDAD))
    combos = list(itertools.product(cns, lags, [float(x) for x in prf], [float(x) for x in lam], ks, hums))
    if len(combos) > MAX_COMBINACIONES:
        raise CalibracionError(f"{len(combos)} combinaciones (máximo {MAX_COMBINACIONES}): reduce los rangos.")
    filas = []
    for c in combos:
        r = _evaluar(evs, c, area, dt_h)
        fa, fv = r["ajuste"] or {}, r["validacion"] or {}
        filas.append({"CN": round(c[0], 2), "lag_h": round(c[1], 2), "PRF": c[2], "lambda": c[3], "k_rec_d": c[4], "humedad": c[5],
                      **{f"{k}_ajuste": v for k, v in fa.items()}, **{f"{k}_validacion": v for k, v in fv.items()}})
    df = pd.DataFrame(filas).sort_values("KGE_ajuste", ascending=False, na_position="last").reset_index(drop=True)
    df.insert(0, "id", range(len(df)))
    d = _nueva(carpeta / "calibracion" / "barridos", "barrido_")
    _tablas(df.round(4), d / "resultados"); _tablas(pd.DataFrame(tabla), d / "eventos")
    avisos = [f"Eventos excluidos automáticamente: {', '.join(excluidos)}."] if excluidos else []
    if dt_h >= 24 and float(min(lags)) < 24:
        avisos.append("Con paso diario (24 h), un lag menor que 24 h no es identificable: los lags < 24 h dan resultados casi iguales. Con lluvia y caudal horarios el programa calibra en paso horario.")
    mejor = df.iloc[0]
    for clave, vals in (("CN", cns), ("lag_h", lags)):                                    # D2: óptimo en el borde del rango
        if len(vals) > 1 and (abs(float(mejor[clave]) - float(min(vals))) < 1e-9 or abs(float(mejor[clave]) - float(max(vals))) < 1e-9):
            avisos.append(f"El mejor por KGE de ajuste tiene {clave} = {float(mejor[clave]):g}, en el borde del rango [{float(min(vals)):g}, {float(max(vals)):g}]: amplía el rango y vuelve a barrer.")
    efecto_k = None
    if any(k is not None for k in ks) and None in ks:                                     # D1: efecto de la recesión en NSE
        efecto_k = {"sin_recesion": _mejor_por(df, df.k_rec_d.isna()), "con_recesion": _mejor_por(df, df.k_rec_d.notna()), "k_estimado": k_est,
                    "nota": "mejor combinación por KGE de ajuste con caudal base constante y con recesión exponencial"}
        a_, b_ = efecto_k["sin_recesion"], efecto_k["con_recesion"]
        if a_ and b_ and a_["NSE_validacion"] is not None and b_["NSE_validacion"] is not None:
            avisos.append(f"Recesión: NSE validación {a_['NSE_validacion']:.2f} (base constante) → {b_['NSE_validacion']:.2f} (k = {b_['k_rec_d']:g} d); NSE ajuste {a_['NSE_ajuste']:.2f} → {b_['NSE_ajuste']:.2f}.")
    efecto_h = {h: _mejor_por(df, df.humedad == h) for h in hums} if len(hums) > 1 else None
    pe = _por_evento(evs, (float(mejor.CN), float(mejor.lag_h), float(mejor.PRF), float(mejor["lambda"]), None if pd.isna(mejor.k_rec_d) else float(mejor.k_rec_d), mejor.humedad), area, dt_h)
    raros = [x for x in pe if abs(x["error_volumen_pct"]) > 100]                        # D4
    if raros:
        avisos.append("Eventos con error de volumen > ±100 % en la mejor combinación (revisa la lluvia; si los excluyes, quedan como «lluvia dudosa»): "
                      + ", ".join(f"{x['evento']} ({x['error_volumen_pct']:+.0f} %)" for x in raros))
    dudosos = [e["evento"] for e in tabla if e.get("lluvia_dudosa")]
    if dudosos:
        avisos.append("Eventos con escorrentía directa mayor que su lluvia (lluvia dudosa): " + ", ".join(dudosos) + ".")
    baja = [e["evento"] for e in tabla if e.get("cobertura_lluvia_pct") is not None and float(e["cobertura_lluvia_pct"]) < 80]
    if baja:
        avisos.append("Eventos con cobertura de lluvia < 80 %: " + ", ".join(baja) + ".")
    act_f = carpeta / "observaciones" / "lluvia_activa.json"
    if act_f.exists():
        la = json.loads(act_f.read_text(encoding="utf-8")); pesos = [x.get("peso_con_todas", 0) for x in (la.get("pesos") or [])]
        if pesos and max(pesos) > 0.8:
            avisos.append(f"Cobertura de estaciones: una sola estación pesa {100 * max(pesos):.0f} % de la lluvia areal; tormentas fuera de su entorno no se ven.")
    comun = q.index.intersection(p.dropna().index)
    bal = None
    if len(comun) >= 365:
        p_mm = float(p.loc[comun].mean() * 365.25 * (24.0 / dt_h)); q_mm = float(q.loc[comun].mean() * 86400 * 365.25 / (area * 1e3))
        bal = {"dias_comunes": int(len(comun)), "lluvia_mm_anio": round(p_mm, 1), "escorrentia_obs_mm_anio": round(q_mm, 1), "coef_escorrentia": round(q_mm / p_mm, 3) if p_mm > 0 else None}
        if p_mm > 0 and q_mm / p_mm >= 1:
            avisos.append(f"BALANCE IMPOSIBLE: el río escurre {q_mm:.0f} mm/año y la lluvia de entrada da {p_mm:.0f} mm/año (coef. {q_mm / p_mm:.2f} ≥ 1). "
                          "La lluvia está subestimada (o el área/caudal es inconsistente): ningún parámetro lo corrige. Revisa la fuente de lluvia antes de calibrar.")
        elif p_mm > 0 and q_mm / p_mm > 0.85:
            avisos.append(f"Coeficiente de escorrentía alto ({q_mm / p_mm:.2f}): posible subestimación de la lluvia de entrada.")
    cfg = {"creado": time.strftime("%Y-%m-%dT%H:%M:%S"), "persona": persona, "cuenca": a, "balance_anual": bal, "avisos": avisos, "observaciones": mq, "lluvia": mp_, "dt_h": dt_h,
           "rangos": {"CN": list(cn), "lag_h": list(lag_h), "PRF": list(prf), "lambda": list(lam), "k_rec_d": [k for k in ks], "humedad": hums}, "n_combinaciones": len(combos), "n_eventos_usados": len(evs),
           "efecto_recesion": efecto_k, "efecto_humedad": efecto_h, "errores_volumen_mejor": pe,
           "modelo": "Q = Q_base(inicio)[·exp(−t/k)] + conv(exceso SCS-CN[CN por humedad antecedente] acumulado del evento, HU SCS triangular); paso " + ("diario" if dt_h >= 24 else f"{dt_h:g} h"),
           "nota": "Ordenado por KGE de AJUSTE. La validación se muestra al lado y NO se usa para ordenar. La persona elige y acepta."}
    (d / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"barrido": d.name, "avisos": avisos, "balance_anual": bal, "n_combinaciones": len(combos), "n_eventos": len(evs), "dt_h": dt_h, "efecto_recesion": efecto_k, "efecto_humedad": efecto_h,
            "mejores": df.head(25).round(4).replace({np.nan: None}).to_dict("records"), "config": cfg}


def figura(carpeta, barrido_id, combo_id):
    """PNG con los eventos observados (gris) y simulados con la combinación elegida (azul = condición existente X)."""
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .cuenca import _BLOQUEO_PNG
    carpeta = Path(carpeta); d = carpeta / "calibracion" / "barridos" / barrido_id
    res = pd.read_csv(d / "resultados.csv"); ev = pd.read_csv(d / "eventos.csv"); cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    c = res[res.id == int(combo_id)].iloc[0]
    q, _ = observaciones(carpeta); p, _ = lluvia_cuenca(carpeta)
    q.index = q.index.normalize(); q = q[~q.index.duplicated()].asfreq("D"); p = p.asfreq("D")
    n = len(ev); cols = min(4, n); filas = math.ceil(n / cols)
    with _BLOQUEO_PNG:
        fig, axs = plt.subplots(filas, cols, figsize=(3.2 * cols, 2.4 * filas), dpi=100, squeeze=False)
        for k, e in ev.iterrows():
            ax = axs[k // cols][k % cols]
            qq = q[e.inicio:e.fin].interpolate(limit=2); pp = p[e.inicio:e.fin]
            if qq.isna().any() or pp.isna().any():
                ax.set_title(f"{e.evento} (sin datos)", fontsize=8); continue
            sim = simular_evento(pp.values, qq.values[0], cfg["cuenca"]["area_km2"], c.CN, c.lag_h, c.PRF, c["lambda"], cfg["dt_h"], None if pd.isna(c.get("k_rec_d", np.nan)) else float(c["k_rec_d"]))   # figura rápida: CN sin ajuste de humedad
            ax.plot(qq.index, qq.values, color="#555", lw=1.4, label="observado")
            ax.plot(qq.index, sim, color="#0b66c3", lw=1.4, label="simulado (X)")
            ax.set_title(f"{e.evento} · {e.rol}", fontsize=8, color="#b5179e" if e.rol == "validacion" else "#222")
            ax.tick_params(labelsize=6); ax.xaxis.set_major_locator(plt.MaxNLocator(3))
        for k in range(n, filas * cols):
            axs[k // cols][k % cols].axis("off")
        axs[0][0].legend(fontsize=6)
        fig.suptitle(f"CN {c.CN:g} · lag {c.lag_h:g} h · PRF {c.PRF:g} · λ {c['lambda']:g}  —  KGE ajuste {c.KGE_ajuste:.2f} · validación {c.KGE_validacion:.2f}", fontsize=9)
        fig.tight_layout(rect=(0, 0, 1, 0.96)); b = io.BytesIO(); fig.savefig(b, format="png"); plt.close(fig)
    return b.getvalue()


# ------------------------------------------------------------------------------------------------ 4. aceptación
def aceptar(carpeta, barrido_id, combo_id, persona, nota=""):
    if not str(persona).strip():
        raise CalibracionError("Escribe tu nombre: la aceptación es una decisión de una persona.")
    carpeta = Path(carpeta); d = carpeta / "calibracion" / "barridos" / barrido_id
    if not (d / "resultados.csv").exists():
        raise CalibracionError("Barrido no encontrado.")
    res = pd.read_csv(d / "resultados.csv"); cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    fila = res[res.id == int(combo_id)]
    if fila.empty:
        raise CalibracionError("Combinación no encontrada.")
    c = fila.iloc[0].replace({np.nan: None}).to_dict()
    kv, nv = c.get("KGE_validacion"), c.get("n_eventos_validacion")
    favorable = kv is not None and kv > 0 and (c.get("NSE_validacion") or -1) > 0
    etiqueta = (f"Calibración aceptada por {persona}: {int(c.get('n_eventos_ajuste') or 0)} eventos de ajuste, {int(nv or 0)} de validación "
                f"(KGE validación {kv:.2f}). Parámetros efectivos del modelo agregado diario; no es una predicción." if kv is not None else "sin validación")
    if not favorable:
        etiqueta += " · VALIDACIÓN DESFAVORABLE (NSE o KGE ≤ 0): no usar como modelo calibrado."
    borde = []
    for k_, clave in (("CN", "CN"), ("lag_h", "lag_h")):
        rg = (cfg.get("rangos") or {}).get(clave)
        if rg and len(rg) >= 3 and int(rg[2]) > 1 and c.get(k_) is not None and (abs(float(c[k_]) - float(rg[0])) < 1e-9 or abs(float(c[k_]) - float(rg[1])) < 1e-9):
            borde.append(f"{k_} = {c[k_]:g} está en el borde del rango [{rg[0]:g}, {rg[1]:g}]")
    if borde:
        etiqueta += " · ÓPTIMO EN EL BORDE DEL RANGO (" + "; ".join(borde) + "): amplía el rango y vuelve a barrer."
    out = _nueva(carpeta / "calibracion" / "aceptadas", "aceptada_")
    reg = {"persona": persona, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "nota": nota, "barrido": barrido_id, "combinacion": c, "favorable": favorable, "etiqueta": etiqueta, "en_borde": borde,
           "cuenca": cfg["cuenca"], "observaciones": cfg["observaciones"], "modelo": cfg["modelo"]}
    (out / "aceptacion.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        (out / "eventos_ajuste_validacion.png").write_bytes(figura(carpeta, barrido_id, combo_id))
    except Exception:
        pass
    try:
        from . import calibracion_graficas as CG
        CG.comparar(carpeta, barrido_id, combo_id, salida=out / "comparacion")
    except Exception as e:
        reg["aviso_comparacion"] = str(e)[:200]
    return reg


def estado(carpeta):
    carpeta = Path(carpeta)
    q, mq = observaciones(carpeta)
    p, mp_ = lluvia_cuenca(carpeta)
    hist = carpeta / "observaciones" / "registro_observaciones.json"
    acc = sorted((carpeta / "calibracion" / "aceptadas").glob("aceptada_*")) if (carpeta / "calibracion" / "aceptadas").exists() else []
    bar = sorted((carpeta / "calibracion" / "barridos").glob("barrido_*")) if (carpeta / "calibracion" / "barridos").exists() else []
    ult = json.loads((acc[-1] / "aceptacion.json").read_text(encoding="utf-8")) if acc else None
    return {"observaciones": {"ok": q is not None, "mensaje": mq, "periodo": [str(q.index.min().date()), str(q.index.max().date())] if q is not None else None},
            "lluvia": {"ok": p is not None, "mensaje": mp_, "estacion_registrada": json.loads((carpeta / "observaciones" / "lluvia_activa.json").read_text(encoding="utf-8")) if (carpeta / "observaciones" / "lluvia_activa.json").exists() else None}, "registro": json.loads(hist.read_text(encoding="utf-8")) if hist.exists() else [],
            "barridos": [b.name for b in bar][::-1], "aceptada": ult, "tipos": TIPOS,
            "etiqueta": ult["etiqueta"] if ult else "SIMULACIÓN SIN CALIBRAR"}
