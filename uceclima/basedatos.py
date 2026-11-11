# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Base de datos del proyecto (SQLite) — parte del modelo. Un único archivo `base_datos/uceclima.sqlite` dentro del proyecto con lo que se descargó, se calculó y se corrigió, para consultarlo
con SQL (también desde una IA por la API/MCP) sin reabrir decenas de CSV. Es una COPIA ordenada y trazable de los archivos del proyecto (los archivos siguen siendo la fuente): `sincronizar` la
reconstruye de forma idempotente. La consulta es de SOLO LECTURA (una sola sentencia SELECT/WITH, con tope de filas y de tiempo).

Tablas: procedencia · referencia_lluvia · cmip6_modelos · cmip6_series (original y corregida por QQM/QDM, con modelo/escenario/método) · cmip6_factores · cmip6_factores_por_modelo ·
cmip6_verificacion · eventos · escenarios_idf · corridas · estaciones."""
import json, re, sqlite3, time
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

ESQUEMA = """
CREATE TABLE IF NOT EXISTS procedencia (clave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS referencia_lluvia (serie TEXT, fecha TEXT, mm REAL, PRIMARY KEY (serie, fecha));
CREATE TABLE IF NOT EXISTS cmip6_modelos (modelo TEXT PRIMARY KEY, posicion INTEGER, seleccionado INTEGER, peso REAL, w_desempeno REAL, w_independencia REAL, distancia_desempeno REAL, peso_q1 REAL, peso_q2 REAL, peso_q3 REAL,
  peso_q4 REAL, peso_q5 REAL, bias_total_pct REAL, rmse_clim_mm_mes REAL, rmse_cuantiles_mm REAL, rmse_max_anuales_mm REAL, rmse_clim_mm_mes_val_original REAL, rmse_clim_mm_mes_val_qqm REAL, rmse_clim_mm_mes_val_eqm_agente REAL,
  rmse_cuantiles_mm_val_original REAL, rmse_cuantiles_mm_val_qqm REAL, rmse_cuantiles_mm_val_eqm_agente REAL, mejora_qqm_cuantiles_pct REAL, tr100_24h_mod_mm REAL, estado TEXT);
CREATE TABLE IF NOT EXISTS cmip6_series (modelo TEXT, escenario TEXT, fecha TEXT, pr_original_mm REAL, pr_corregida_mm REAL, metodo TEXT, PRIMARY KEY (modelo, escenario, fecha));
CREATE TABLE IF NOT EXISTS cmip6_factores (escenario TEXT, horizonte TEXT, metrica TEXT, version TEXT, mediana_ponderada REAL, p10 REAL, p90 REAL, minimo REAL, maximo REAL, n_modelos INTEGER, cobertura_peso REAL);
CREATE TABLE IF NOT EXISTS cmip6_factores_por_modelo (escenario TEXT, horizonte TEXT, metrica TEXT, modelo TEXT, peso REAL, peso_q5 REAL, factor_corregido REAL, factor_original REAL, factor_agente REAL);
CREATE TABLE IF NOT EXISTS cmip6_verificacion (modelo TEXT, version TEXT, bias_total_pct REAL, rmse_clim_mm_mes REAL, rmse_cuantiles_mm REAL, rmse_max_anuales_mm REAL);
CREATE TABLE IF NOT EXISTS eventos (evento TEXT, rol TEXT, fecha_pico_lluvia TEXT, ventana_inicio TEXT, ventana_fin TEXT, P_max_dia_mm REAL, Tr_P_max_dia_anios REAL, Q_base_previo_m3s REAL, Q_pico_m3s REAL, dQ_m3s REAL, V_directo_hm3 REAL);
CREATE TABLE IF NOT EXISTS escenarios_idf (id TEXT, nombre TEXT, rol TEXT, factor REAL, p24_mm REAL, fuente TEXT);
CREATE TABLE IF NOT EXISTS corridas (id TEXT PRIMARY KEY, estado TEXT, escenario_id TEXT, escenario TEXT, p_total_mm REAL, area_ge_03m_km2 REAL, area_ge_005m_km2 REAL, balance_pct REAL, courant_max REAL, segundos REAL);
CREATE TABLE IF NOT EXISTS estaciones (id TEXT PRIMARY KEY, nombre TEXT, x REAL, y REAL, tipo TEXT, registros INTEGER, inicio TEXT, fin TEXT);
CREATE INDEX IF NOT EXISTS ix_series_modelo ON cmip6_series (modelo, escenario);
"""


class BDError(ValueError):
    pass


def ruta(proyecto):
    return Path(proyecto) / "base_datos" / "uceclima.sqlite"


def abrir(proyecto, solo_lectura=False):
    p = ruta(proyecto)
    if solo_lectura:
        if not p.exists():
            raise BDError("Este proyecto aún no tiene base de datos (usa «Sincronizar»).")
        return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p); c.executescript(ESQUEMA); return c


def _vaciar_e_insertar(c, tabla, df):
    c.execute(f"DELETE FROM {tabla}")
    if df is not None and len(df):
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({tabla})")]
        d = df.reindex(columns=cols)
        d = d.astype(object).where(pd.notna(d), None)
        c.executemany(f"INSERT OR REPLACE INTO {tabla} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", d.values.tolist())


def _ultima(proyecto, patron):
    c = sorted((Path(proyecto) / "datos_descargados").glob(patron))
    return c[-1] if c else None


def _leer(f):
    d = pd.read_csv(f, parse_dates=["fecha"]); return d.drop_duplicates("fecha").set_index("fecha")["pr_mm"].astype(float).sort_index()


def sincronizar(proyecto, referencia="chirps:celda_nex_mm"):
    """Reconstruye la base desde los archivos del proyecto. Devuelve el conteo de filas por tabla."""
    from . import cmip6_descarga as CD, cmip6_sesgo as SB, series_api as SER, escenarios_idf as ESC
    proyecto = Path(proyecto); c = abrir(proyecto); n = {}
    c.execute("DELETE FROM procedencia")
    prov = {"sincronizado_utc": datetime.utcnow().isoformat(timespec="seconds"), "proyecto": proyecto.name, "referencia_lluvia": referencia,
            "aviso": "Copia ordenada de los archivos del proyecto; los archivos son la fuente. Resultados no calibrados ni validados."}
    dec = CD.decision(proyecto)
    if dec:
        prov["cmip6_decision"] = json.dumps(dec, ensure_ascii=False)
    # referencia observada
    try:
        s = SER._serie(proyecto, referencia); s = s[(s.index >= "1981-01-01")]
        _vaciar_e_insertar(c, "referencia_lluvia", pd.DataFrame({"serie": referencia, "fecha": s.index.strftime("%Y-%m-%d"), "mm": s.values}))
    except Exception as e:
        c.execute("DELETE FROM referencia_lluvia"); prov["referencia_error"] = str(e)[:150]
    # CMIP6
    base = proyecto / "registro" / "cmip6"; an = sorted(base.glob("analisis_*")) if base.exists() else []
    dh, dfu = _ultima(proyecto, "cmip6_historico_*"), _ultima(proyecto, "cmip6_futuro_*")
    c.execute("DELETE FROM cmip6_series")
    if an:
        car = an[-1]; prov["cmip6_analisis"] = car.name
        met = pd.read_csv(car / "metricas_modelos.csv"); sel = pd.read_csv(car / "seleccionados.csv")
        met["seleccionado"] = met["modelo"].isin(sel["modelo"]).astype(int)
        _vaciar_e_insertar(c, "cmip6_modelos", met)
        if dh:
            cal = SB._cargar_cal(car)
            for f in sorted(dh.glob("*_historical.csv")):
                m = f.name.replace("_historical.csv", ""); h = _leer(f)
                corr = None
                if m in cal:
                    q = SB.QQM(); q.m = cal[m]; corr = q.transform(h)
                df = pd.DataFrame({"modelo": m, "escenario": "historical", "fecha": h.index.strftime("%Y-%m-%d"), "pr_original_mm": h.values, "pr_corregida_mm": corr.values if corr is not None else np.nan,
                                   "metodo": "QQM mensual (calibrado 1981–2014)" if corr is not None else "sin corregir"})
                cols = list(df.columns); c.executemany("INSERT OR REPLACE INTO cmip6_series VALUES (?,?,?,?,?,?)", df.astype(object).where(pd.notna(df), None)[cols].values.tolist())
                fut = SB.leer_futuro(proyecto, m) if m in cal else None
                if fut is not None:
                    q = SB.QQM(); q.m = cal[m]; cor = SB.qdm_por_bloques(q, fut, h)
                    d2 = pd.DataFrame({"modelo": m, "escenario": "ssp585", "fecha": fut.index.strftime("%Y-%m-%d"), "pr_original_mm": fut.values, "pr_corregida_mm": cor.reindex(fut.index).values, "metodo": "QDM por bloques (preserva la señal de cambio)"})
                    c.executemany("INSERT OR REPLACE INTO cmip6_series VALUES (?,?,?,?,?,?)", d2.astype(object).where(pd.notna(d2), None)[cols].values.tolist())
        fj = car / "factores_cc.csv"
        if fj.exists():
            F = pd.read_csv(fj).rename(columns={"min": "minimo", "max": "maximo"}); _vaciar_e_insertar(c, "cmip6_factores", F)
            _vaciar_e_insertar(c, "cmip6_factores_por_modelo", pd.read_csv(car / "factores_por_modelo.csv"))
        else:
            c.execute("DELETE FROM cmip6_factores"); c.execute("DELETE FROM cmip6_factores_por_modelo")
        fv = car / "verificacion_2015_2025.csv"
        _vaciar_e_insertar(c, "cmip6_verificacion", pd.read_csv(fv) if fv.exists() else None)
    # eventos, escenarios, corridas, estaciones
    sel_dir = SER._sel_dir(proyecto)
    _vaciar_e_insertar(c, "eventos", pd.read_csv(sel_dir / "eventos_seleccionados.csv") if sel_dir and (sel_dir / "eventos_seleccionados.csv").exists() else None)
    try:
        from .ui import proyecto as P
        datos, _ = P.abrir(str(proyecto)); _, cfg = P.config_climanet(datos, proyecto)
        defs, _b = ESC.definiciones(proyecto, cfg, __import__("uceclima.idf_x", fromlist=["x"]).estacion_proyecto(cfg, __import__("uceclima.ui.proyecto", fromlist=["x"]).abrir(str(proyecto))[0]), int(cfg.get("storm_min", 180)))
        _vaciar_e_insertar(c, "escenarios_idf", pd.DataFrame([{k: d.get(k) for k in ("id", "nombre", "rol", "factor", "p24_mm", "fuente")} for d in defs]))
        filas = []
        for r in sorted((proyecto / datos["carpeta_resultados"]).glob("corrida_*")):
            st = json.loads((r / "estado.json").read_text(encoding="utf-8")) if (r / "estado.json").exists() else {}
            rs = next(iter(r.rglob("resumen.json")), None); ev = next(iter(r.rglob("evaluacion_numerica.json")), None)
            rr = json.loads(rs.read_text(encoding="utf-8")) if rs else {}; ee = json.loads(ev.read_text(encoding="utf-8")) if ev else {}
            filas.append({"id": r.name, "estado": st.get("estado"), "escenario_id": st.get("escenario_id"), "escenario": st.get("escenario"), "p_total_mm": rr.get("P_total_mm"), "area_ge_03m_km2": rr.get("area_ge_0.3_km2"),
                          "area_ge_005m_km2": rr.get("area_ge_0.05_km2"), "balance_pct": ee.get("diferencia_balance_fisico_pct"), "courant_max": ee.get("Courant_max"), "segundos": rr.get("segundos")})
        _vaciar_e_insertar(c, "corridas", pd.DataFrame(filas))
    except Exception as e:
        prov["escenarios_corridas_error"] = str(e)[:150]
    try:
        from . import estaciones as EST
        _vaciar_e_insertar(c, "estaciones", pd.DataFrame([{"id": e["id"], "nombre": e.get("nombre"), "x": e.get("x"), "y": e.get("y"), "tipo": e.get("tipo"), "registros": (e.get("calidad") or {}).get("n_registros"),
                                                           "inicio": ((e.get("calidad") or {}).get("inicio_utc") or "")[:10], "fin": ((e.get("calidad") or {}).get("fin_utc") or "")[:10]} for e in EST.listar(proyecto)]))
    except Exception:
        pass
    c.executemany("INSERT OR REPLACE INTO procedencia VALUES (?,?)", [(k, str(v)) for k, v in prov.items()])
    c.commit()
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        n[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    c.execute("VACUUM"); c.close()
    return {"archivo": str(ruta(proyecto)), "tablas": n, "mb": round(ruta(proyecto).stat().st_size / 1e6, 1)}


def esquema(proyecto):
    c = abrir(proyecto, solo_lectura=True); out = []
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        out.append({"tabla": t, "filas": c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], "columnas": [r[1] + " " + (r[2] or "") for r in c.execute(f"PRAGMA table_info({t})")]})
    c.close(); return out


_PROHIBIDO = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|trigger|load_extension)\b", re.I)


def consultar(proyecto, sql, max_filas=5000, max_s=15):
    """SOLO lectura: una sola sentencia que empiece por SELECT o WITH. Devuelve columnas y filas (con tope)."""
    s = (sql or "").strip().rstrip(";").strip()
    if not s or ";" in s:
        raise BDError("Escribe una sola sentencia SQL.")
    if not re.match(r"^(select|with)\b", s, re.I) or _PROHIBIDO.search(s):
        raise BDError("Solo se permiten consultas de lectura (SELECT / WITH).")
    c = abrir(proyecto, solo_lectura=True); t0 = time.time()
    c.set_progress_handler(lambda: 1 if time.time() - t0 > max_s else 0, 100000)
    try:
        cur = c.execute(s); cols = [d[0] for d in cur.description]; filas = cur.fetchmany(max_filas + 1)
    except sqlite3.Error as e:
        raise BDError("Consulta inválida o demasiado lenta: " + str(e)[:200]) from e
    finally:
        c.close()
    cortado = len(filas) > max_filas
    return {"columnas": cols, "filas": [list(r) for r in filas[:max_filas]], "cortado": cortado, "max_filas": max_filas}
