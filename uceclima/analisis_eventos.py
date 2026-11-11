# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Selección de eventos (lluvia diaria + caudal) para un proyecto con datos DESCARGADOS (CHIRPS, CELEC/GEOGLOWS, estación). Reutiliza los criterios estadísticos de
`seleccion_eventos` pero DERIVA los umbrales de los propios datos (no de una cuenca distinta) y los deja escritos:
  - inicio del año hidrológico = mes con menor lluvia media (climatología de la serie);
  - umbral de pico de lluvia = percentil 99 de los días;
  - respuesta mínima de caudal = 25 % del caudal mediano;
  - caudal sospechoso (sensor): valores > 8× el percentil 99,5 se tratan como AUSENTES (la ventana que los contiene se descarta); no se corrigen ni se rellenan.
Salida (carpeta nueva dentro del proyecto): eventos_candidatos.csv, eventos_seleccionados.csv, bloques.csv, criterios.json y resumen_seleccion.json (formato que lee la interfaz).
Descriptivo y reproducible; no calibra nada. El periodo con eventos es el de TRASLAPE entre lluvia y caudal."""
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

from . import seleccion_eventos as SE


class AnalisisError(ValueError):
    pass


def _ultima(proyecto, fuente):
    base = Path(proyecto) / "datos_descargados"
    c = sorted(base.glob(f"sitio_*/{fuente}")) + sorted(base.glob(f"{fuente}_*"))
    return c[-1] if c else None


def cargar_lluvia(proyecto, columna="media_caja_mm"):
    d = _ultima(proyecto, "chirps")
    f = (d / "chirps_diario.csv") if d else None
    if not f or not f.exists():
        raise AnalisisError("El proyecto no tiene CHIRPS descargado (usa la descarga automática del sitio).")
    x = pd.read_csv(f, parse_dates=["fecha"]).set_index("fecha")
    if columna not in x.columns:
        raise AnalisisError(f"CHIRPS no tiene la columna {columna}.")
    return x[columna].astype(float).sort_index(), f.name


def cargar_caudal(proyecto, fuente="celec"):
    if fuente == "celec":
        d = _ultima(proyecto, "celec")
        f = (d / "celec_mazar_diario.csv") if d else None
        if not f or not f.exists():
            raise AnalisisError("El proyecto no tiene la serie de CELEC.")
        return pd.read_csv(f, parse_dates=["fecha"]).set_index("fecha")["caudal_m3s"].astype(float).sort_index(), "CELEC SUR (caudal, significado sin confirmar)"
    if fuente.startswith("geoglows:"):
        rid = fuente.split(":", 1)[1]
        d = _ultima(proyecto, "geoglows"); f = (d / f"geoglows_{rid}.csv") if d else None
        if not f or not f.exists():
            raise AnalisisError(f"No hay descarga GEOGLOWS del tramo {rid}.")
        s = pd.read_csv(f, parse_dates=[0]); idx = pd.to_datetime(s.iloc[:, 0], utc=True).dt.tz_localize(None).dt.normalize()
        return pd.Series(s.iloc[:, 1].values, index=idx).astype(float), f"GEOGLOWS reanalizado tramo {rid}"
    raise AnalisisError("Fuente de caudal no reconocida (celec | geoglows:<id>).")


def seleccionar(proyecto, lluvia, caudal, nombre_lluvia="CHIRPS", nombre_caudal="caudal", por_bloque=2, salida=None, extra=None):
    P = lluvia.copy(); Q = caudal.copy()
    idx = pd.date_range(min(P.index.min(), Q.index.min()), max(P.index.max(), Q.index.max()), freq="D")
    d = pd.DataFrame({"fecha": idx}); d["P_mm"] = P.reindex(idx).values; d["Q_m3s"] = Q.reindex(idx).values
    # --- criterios derivados de los datos
    q995 = float(np.nanpercentile(d["Q_m3s"], 99.5)); med15 = d["Q_m3s"].rolling(15, center=True, min_periods=5).median()
    sospechoso = (d["Q_m3s"] > 5 * med15) & (d["Q_m3s"] > 3 * q995)               # pico aislado Y absurdamente alto; las crecidas de un día plausibles se conservan
    n_sosp = int(sospechoso.sum()); fechas_sosp = [f.date().isoformat() for f in d.loc[sospechoso, "fecha"]]; d.loc[sospechoso, "Q_m3s"] = np.nan
    mensual = P.groupby(P.index.month).mean(); mes_inicio = int(mensual.idxmin())
    umbral = float(np.nanpercentile(d["P_mm"].dropna(), 99)); qmed = float(np.nanmedian(d["Q_m3s"]))
    c = SE.Criterios(umbral_pico_mm=umbral, separacion_picos=14, antes=7, despues=14, min_dq_m3s=max(0.25 * qmed, 1.0), max_retardo_dias=10, min_dias_entre_grupos=30)
    d["P_crudo_mm"] = d["P_mm"]; d["rellenado"] = False; d["Q_qc"] = "OBSERVED"
    solapa = d.dropna(subset=["P_mm", "Q_m3s"])
    if len(solapa) < 365:
        raise AnalisisError("Lluvia y caudal se traslapan menos de un año: no hay base para seleccionar eventos.")
    ini_sol, fin_sol = solapa["fecha"].min(), solapa["fecha"].max()
    maximos = d.dropna(subset=["P_mm"]).groupby(d["fecha"].dt.year)["P_mm"].max()
    maximos = maximos[d.dropna(subset=["P_mm"]).groupby(d["fecha"].dt.year).size() > 300]
    g = SE.gumbel_sin_correccion(maximos.values)
    picos = SE.identificar_picos(d, c)
    # solo picos dentro del periodo con caudal
    picos = [i for i in picos if ini_sol <= d["fecha"].iloc[i] <= fin_sol]
    e = SE.evaluar(d, picos, g, c)
    if e.empty:
        raise AnalisisError("Ningún pico de lluvia supera el umbral dentro del periodo con caudal.")
    e = SE.filtrar(e, c)
    # año hidrológico con el mes de inicio derivado
    antes_defecto = SE.anio_hidrologico.__defaults__
    SE.anio_hidrologico.__defaults__ = (mes_inicio,)                          # la selección por bloques usa el inicio de año hidrológico de ESTA serie; se restaura al terminar
    try:
        sel, bl = SE.seleccionar_por_bloques(e, None, por_bloque=por_bloque)
    finally:
        SE.anio_hidrologico.__defaults__ = antes_defecto
    # volumen directo sobre el caudal base y ventanas CHIRPS (-21/+5 d)
    vol = []
    for r in sel.itertuples():
        w = d[(d["fecha"] >= r.fecha_pico_lluvia) & (d["fecha"] <= pd.Timestamp(r.ventana_fin))]
        base = r.Q_base_previo_m3s
        vol.append(float(np.nansum(np.maximum(w["Q_m3s"].values - base, 0)) * 86400 / 1e6) if np.isfinite(base) else np.nan)
    sel = sel.assign(V_directo_hm3=np.round(vol, 3), ventana_chirps_inicio=[(pd.Timestamp(f) - pd.Timedelta(days=21)).date().isoformat() for f in sel.fecha_pico_lluvia],
                     ventana_chirps_fin=[(pd.Timestamp(f) + pd.Timedelta(days=5)).date().isoformat() for f in sel.fecha_pico_lluvia])
    e["bloque"] = [SE.anio_hidrologico(f, mes_inicio) for f in e.fecha_pico_lluvia]
    criterios = {"derivados_de_los_datos": True, "umbral_pico_lluvia_mm": umbral, "percentil_lluvia": 99, "respuesta_minima_caudal_m3s": c.min_dq_m3s, "caudal_mediano_m3s": qmed, "mes_inicio_anio_hidrologico": mes_inicio,
                 "regla_caudal_sospechoso": "Q > 5× la mediana de ±7 días Y Q > 3× el percentil 99,5", "caudal_sospechoso_umbral_m3s": 3 * q995, "dias_caudal_sospechoso_anulados": n_sosp, "fechas_caudal_sospechoso": fechas_sosp, "separacion_picos_dias": c.separacion_picos, "ventana": f"-{c.antes} d / +{c.despues} d", "por_bloque": por_bloque,
                 "gumbel": g, "traslape": [ini_sol.date().isoformat(), fin_sol.date().isoformat()], "lluvia": nombre_lluvia, "caudal": nombre_caudal}
    resumen = {"titulo": f"Selección estadística de eventos · {nombre_lluvia} + {nombre_caudal} ({ini_sol.year}–{fin_sol.year})", "estacion_lluvia": f"{nombre_lluvia} (descargada automáticamente)", "aforo": f"{nombre_caudal}",
               "picos_candidatos": int(len(e)), "cumplen": int(e["cumple"].sum()), "seleccionados": int(len(sel)),
               "limites": ["Los umbrales se derivaron de los propios datos (percentil 99 de la lluvia; 25 % del caudal mediano) y se listan en criterios.json.",
                           f"{n_sosp} día(s) de caudal con picos absurdos aislados ({', '.join(fechas_sosp[:6])}) se trataron como ausentes; no se corrigieron. Las crecidas de un día plausibles se conservaron.",
                           "La lluvia es CHIRPS (satélite, 5 km) y la media de una caja alrededor del sitio, no la lluvia exacta de la cuenca.",
                           "La partición calibración/validación es por bloques de año hidrológico y no usa ningún resultado de modelo. Nada de esto prueba calibración.",
                           "Si el caudal está regulado por una presa o su significado no está confirmado, la relación lluvia-caudal puede no ser natural.",
                           "Los hidrogramas guardados son medias DIARIAS (no horarias): sirven de contorno aproximado, no resuelven la forma del pico."]}
    salida = Path(salida or Path(proyecto) / "registro" / "eventos")
    out = salida / f"seleccion_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True)
    # hidrogramas observados por evento (paquete previo a HEC-RAS/2D): fecha, lluvia(s), caudal diario medio. Sin rellenar nada.
    hid = out / "hidrogramas"; hid.mkdir()
    for r in sel.itertuples():
        w = d[(d["fecha"] >= r.ventana_inicio) & (d["fecha"] <= r.ventana_fin)][["fecha", "P_mm", "Q_m3s"]].rename(columns={"P_mm": "lluvia_serie_mm"})
        for nom, ser in (extra or {}).items():
            w[nom] = ser.reindex(w["fecha"]).values
        w["Q_m3s"] = w["Q_m3s"].round(3); w.insert(1, "evento", r.evento); w.to_csv(hid / f"{r.evento}_{r.fecha_pico_lluvia}.csv", index=False)
    e.to_csv(out / "eventos_candidatos.csv", index=False); sel.to_csv(out / "eventos_seleccionados.csv", index=False); bl.to_csv(out / "bloques.csv", index=False)
    (out / "criterios.json").write_text(json.dumps(criterios, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    (out / "resumen_seleccion.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"carpeta": str(out), "hidrogramas": len(list(hid.glob("*.csv"))), "criterios": criterios, "resumen": resumen, "seleccionados": sel}
