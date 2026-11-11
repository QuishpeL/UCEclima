# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Ficha de observaciones de campo: esquema, validación de completitud y extracción para la compuerta de línea base.

NO inventa ni imputa datos: solo comprueba que lo aportado sea utilizable y dice qué falta.
Estados: vacia -> incompleta -> lista_para_calibrar -> lista_para_validar (calibración y validación SIEMPRE en eventos separados).
"""
from pathlib import Path
import numpy as np
import pandas as pd

ESQUEMA = {
    "eventos.csv": ["evento_id", "inicio", "fin", "zona_horaria", "rol", "descripcion", "fuente"],
    "hietograma_observado.csv": ["evento_id", "estacion_id", "fecha", "lluvia_mm", "paso_min", "tipo", "fuente"],
    "aforos_caudal.csv": ["evento_id", "estacion_id", "nombre_estacion", "x", "y", "crs", "fecha", "caudal_m3s", "nivel_m",
                          "datum_vertical", "identidad_confirmada", "incertidumbre_pct", "fuente"],
    "marcas_nivel.csv": ["evento_id", "marca_id", "x", "y", "crs", "tipo", "cota_agua_m", "calado_m", "datum_vertical", "metodo",
                         "incertidumbre_m", "fecha_observacion", "fuente"],
    "secciones_estructuras.csv": ["id", "tipo", "cauce", "x_ini", "y_ini", "x_fin", "y_fin", "crs", "cota_fondo_m", "cota_margen_izq_m",
                                  "cota_margen_der_m", "dimensiones", "datum_vertical", "fecha_medicion", "fuente"],
}
ROLES = {"calibracion", "validacion"}
TIPOS_LLUVIA = {"observada", "estimada", "desagregada"}
TIPOS_MARCA = {"marca_agua", "profundidad", "seco"}
DATUM_INVALIDOS = {"", "desconocido", "unknown", "nan", "none"}


def crear_plantillas(carpeta):
    """Escribe los CSV vacíos (solo encabezados). No se incluyen filas de ejemplo para que nadie las confunda con datos."""
    carpeta = Path(carpeta); carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, cols in ESQUEMA.items():
        p = carpeta / nombre
        if not p.exists():
            pd.DataFrame(columns=cols).to_csv(p, index=False)
    return sorted(ESQUEMA)


def _leer(carpeta, nombre, problemas):
    p = Path(carpeta) / nombre
    if not p.exists():
        problemas.append(f"{nombre}: archivo ausente"); return None
    d = pd.read_csv(p)
    falta = [c for c in ESQUEMA[nombre] if c not in d.columns]
    if falta:
        problemas.append(f"{nombre}: faltan columnas {falta}"); return None
    return d


def _fecha_ok(serie):
    f = pd.to_datetime(serie, errors="coerce", utc=False)
    return f.notna() & serie.astype(str).str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)       # exige zona horaria explícita


def validar_ficha(carpeta):
    """Devuelve {'estado', 'problemas', 'resumen'}. 'problemas' lista lo que impide calibrar/validar; nada se completa por defecto."""
    pr = []
    ev = _leer(carpeta, "eventos.csv", pr); hy = _leer(carpeta, "hietograma_observado.csv", pr)
    af = _leer(carpeta, "aforos_caudal.csv", pr); mk = _leer(carpeta, "marcas_nivel.csv", pr)
    _leer(carpeta, "secciones_estructuras.csv", pr)
    res = {"eventos": 0, "eventos_calibracion": 0, "eventos_validacion": 0, "marcas_validas_por_evento": {}, "eventos_con_lluvia": []}
    if ev is None or ev.empty:
        return {"estado": "vacia", "problemas": pr + ["no hay eventos registrados"], "resumen": res}
    # ---- eventos
    if ev.evento_id.duplicated().any():
        pr.append("eventos.csv: evento_id duplicado")
    for col in ("inicio", "fin"):
        mal = ev[~_fecha_ok(ev[col])]
        if len(mal): pr.append(f"eventos.csv: {col} sin fecha válida con zona horaria en {mal.evento_id.tolist()}")
    if (~ev.rol.isin(ROLES)).any():
        pr.append(f"eventos.csv: rol debe ser {sorted(ROLES)}")
    res["eventos"] = len(ev); res["eventos_calibracion"] = int((ev.rol == "calibracion").sum()); res["eventos_validacion"] = int((ev.rol == "validacion").sum())
    ids = set(ev.evento_id)
    # ---- lluvia observada
    ok_lluvia = set()
    if hy is not None and len(hy):
        if hy.evento_id.isin(ids).all() is False or (~hy.evento_id.isin(ids)).any():
            pr.append("hietograma_observado.csv: eventos que no existen en eventos.csv")
        if (~_fecha_ok(hy.fecha)).any(): pr.append("hietograma_observado.csv: fechas sin zona horaria")
        if (hy.lluvia_mm.isna()).any() or (hy.lluvia_mm < 0).any(): pr.append("hietograma_observado.csv: lluvia ausente o negativa (no se imputa)")
        if (~hy.tipo.isin(TIPOS_LLUVIA)).any(): pr.append(f"hietograma_observado.csv: tipo debe ser {sorted(TIPOS_LLUVIA)}")
        if hy.duplicated(["evento_id", "estacion_id", "fecha"]).any(): pr.append("hietograma_observado.csv: registros duplicados")
        ok_lluvia = set(hy.evento_id) & ids
    res["eventos_con_lluvia"] = sorted(ok_lluvia)
    # ---- aforos
    ok_aforo = set()
    if af is not None and len(af):
        if (af.identidad_confirmada.astype(str).str.lower() != "si").any():
            pr.append("aforos_caudal.csv: hay aforos con identidad no confirmada (no se usan)")
        buenos = af[(af.identidad_confirmada.astype(str).str.lower() == "si") & af.caudal_m3s.notna() & (af.caudal_m3s >= 0)]
        if af.datum_vertical.astype(str).str.lower().isin(DATUM_INVALIDOS).any() and af.nivel_m.notna().any():
            pr.append("aforos_caudal.csv: niveles sin datum vertical")
        ok_aforo = set(buenos.evento_id) & ids
    # ---- marcas de nivel
    marcas_ok = {}
    if mk is not None and len(mk):
        if (~mk.tipo.isin(TIPOS_MARCA)).any(): pr.append(f"marcas_nivel.csv: tipo debe ser {sorted(TIPOS_MARCA)}")
        malas = mk[mk.datum_vertical.astype(str).str.lower().isin(DATUM_INVALIDOS) & (mk.tipo == "marca_agua")]
        if len(malas): pr.append(f"marcas_nivel.csv: {len(malas)} marcas de nivel de agua sin datum vertical")
        if mk.incertidumbre_m.isna().any(): pr.append("marcas_nivel.csv: faltan incertidumbres (incertidumbre_m)")
        if (~_fecha_ok(mk.fecha_observacion)).any(): pr.append("marcas_nivel.csv: fecha_observacion sin zona horaria")
        if mk.crs.astype(str).str.upper().ne("EPSG:32717").any(): pr.append("marcas_nivel.csv: crs debe ser EPSG:32717 (UTM 17S)")
        valido = mk[mk.x.notna() & mk.y.notna() & mk.calado_m.notna() & (mk.calado_m >= 0) & mk.evento_id.isin(ids)]
        marcas_ok = valido.groupby("evento_id").size().to_dict()
    res["marcas_validas_por_evento"] = marcas_ok
    # ---- separación calibración / validación
    cal = set(ev[ev.rol == "calibracion"].evento_id); val = set(ev[ev.rol == "validacion"].evento_id)
    puede_cal = [e for e in cal if e in ok_lluvia and (e in ok_aforo or marcas_ok.get(e, 0) >= 3)]
    puede_val = [e for e in val if e in ok_lluvia and marcas_ok.get(e, 0) >= 5]
    if not puede_cal: pr.append("calibración: ningún evento de calibración tiene lluvia observada + (aforo confirmado o ≥3 marcas)")
    if not puede_val: pr.append("validación: ningún evento de validación tiene lluvia observada + ≥5 marcas/puntos válidos")
    if not (cal and val): pr.append("se necesitan eventos separados de calibración y de validación")
    estado = "lista_para_validar" if (puede_cal and puede_val and not [p for p in pr if "calibración:" not in p and "validación:" not in p and "separados" not in p]) else \
             "lista_para_calibrar" if puede_cal else "incompleta"
    return {"estado": estado, "problemas": pr, "resumen": res}


def marcas_para_validacion(carpeta, evento_id, salida_csv):
    """Escribe x,y,calado_obs_m de las marcas válidas de UN evento de validación y devuelve los metadatos que exige baseline."""
    ev = pd.read_csv(Path(carpeta) / "eventos.csv"); mk = pd.read_csv(Path(carpeta) / "marcas_nivel.csv")
    fila = ev[ev.evento_id == evento_id]
    if fila.empty or fila.iloc[0].rol != "validacion":
        raise ValueError(f"{evento_id} no es un evento de validación (la calibración y la validación deben estar separadas).")
    m = mk[(mk.evento_id == evento_id) & mk.x.notna() & mk.y.notna() & mk.calado_m.notna() & (mk.calado_m >= 0)]
    if len(m) == 0:
        raise ValueError("Sin marcas válidas para este evento.")
    m[["x", "y"]].assign(calado_obs_m=m.calado_m).to_csv(salida_csv, index=False)
    return {"evento": evento_id, "fecha": str(fila.iloc[0].inicio)[:10], "crs": "EPSG:32717", "unidades": "m"}
