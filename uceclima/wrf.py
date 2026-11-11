# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""WRF en UCEclima: (1) leer salidas existentes y (2) preparar una corrida para otra máquina (Linux/WSL).

(1) leer: archivos wrfout_* (RAINC + RAINNC [+ RAINSH], acumuladas desde el inicio de la corrida; cubos I_RAINC/I_RAINNC si existen)
    o NetCDF posprocesados con una variable de lluvia (pr, precip, PREC, RAIN, tp…) y lat/lon. Se extrae la serie en el sitio
    (celda más cercana) o la media de las celdas dentro de la cuenca activa. Las acumuladas se convierten en incrementos por paso.
    Corrección de sesgo opcional con QQM diario (la misma del módulo CMIP6) contra CHIRPS o una estación, si el periodo común
    alcanza (≥ ~4 años); a escala horaria se aplica la razón diaria corregida/cruda (conserva la forma de la tormenta).
    El resultado se guarda en <proyecto>/datos/wrf_<sello>/ y se puede registrar como «estación» para forzar land o la calibración.
(2) preparar: namelist.wps y namelist.input con 3 dominios anidados centrados en el sitio + script de ejecución. No ejecuta WRF.
"""
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

VARS_LLUVIA = ("pr", "precip", "precipitation", "PREC", "prec", "RAIN", "rain", "tp", "pcp", "PRCP", "prcp")


class WRFError(Exception):
    pass


def _nc():
    try:
        import netCDF4
        return netCDF4
    except ImportError as e:
        raise WRFError("Falta la librería netCDF4 para leer archivos WRF.") from e


def _archivos(ruta):
    p = Path(ruta)
    if p.is_dir():
        fs = sorted([f for f in p.iterdir() if f.is_file() and (f.name.startswith("wrfout") or f.suffix.lower() in (".nc", ".nc4"))])
    else:
        fs = [p]
    fs = [f for f in fs if f.exists()]
    if not fs:
        raise WRFError(f"No hay archivos WRF/NetCDF en {ruta}.")
    return fs


def _tiempos_wrf(ds):
    if "Times" in ds.variables:
        t = ds.variables["Times"][:]
        txt = ["".join(c.decode() if isinstance(c, bytes) else str(c) for c in fila).strip() for fila in np.asarray(t)]
        return pd.to_datetime([x.replace("_", " ") for x in txt])
    if "XTIME" in ds.variables:
        v = ds.variables["XTIME"]; nc = _nc()
        return pd.to_datetime([str(x) for x in nc.num2date(v[:], v.units)])
    raise WRFError("El archivo wrfout no tiene Times ni XTIME.")


def _latlon(ds):
    for la, lo in (("XLAT", "XLONG"), ("lat", "lon"), ("latitude", "longitude"), ("XLAT_M", "XLONG_M"), ("y", "x")):
        if la in ds.variables and lo in ds.variables:
            a, b = np.asarray(ds.variables[la][:], float), np.asarray(ds.variables[lo][:], float)
            if a.ndim == 3:
                a, b = a[0], b[0]
            if a.ndim == 1 and b.ndim == 1:
                b, a = np.meshgrid(b, a)
            return a, b
    raise WRFError("No encuentro latitud/longitud en el archivo.")


def _seleccion(lat2, lon2, lon, lat, poligono=None):
    """Máscara de celdas: dentro del polígono (WGS84) o la celda más cercana al sitio."""
    if poligono is not None:
        from shapely import vectorized
        m = vectorized.contains(poligono, lon2, lat2)
        if m.sum() >= 1:
            return m, f"media de {int(m.sum())} celdas WRF dentro de la cuenca"
    d = (lat2 - lat) ** 2 + ((lon2 - lon) * math.cos(math.radians(lat))) ** 2
    i = np.unravel_index(np.argmin(d), d.shape); m = np.zeros(lat2.shape, bool); m[i] = True
    dist = math.sqrt(float(d[i])) * 111.0
    if dist > 30:
        raise WRFError(f"El sitio queda a {dist:.0f} km de la celda WRF más cercana: el dominio no cubre el proyecto.")
    return m, f"celda WRF más cercana al sitio ({dist:.1f} km)"


def leer(ruta, lon, lat, poligono=None):
    """Serie de lluvia (mm por paso de salida) en el sitio o la cuenca. Devuelve (DataFrame[fecha, lluvia_mm], info)."""
    nc = _nc()
    fs = _archivos(ruta)
    trozos, info = [], {"archivos": [f.name for f in fs], "formato": None, "seleccion": None, "avisos": []}
    previo = None
    for f in fs:
        with nc.Dataset(f) as ds:
            ds.set_auto_mask(True)
            lat2, lon2 = _latlon(ds)
            m, txt = _seleccion(lat2, lon2, lon, lat, poligono); info["seleccion"] = txt
            if "RAINNC" in ds.variables or "RAINC" in ds.variables:
                info["formato"] = "wrfout (acumuladas RAINC+RAINNC)"
                t = _tiempos_wrf(ds); tot = np.zeros(len(t))
                cubo = float(getattr(ds, "BUCKET_MM", 0) or 0)
                for v in ("RAINC", "RAINNC", "RAINSH"):
                    if v in ds.variables:
                        a = np.asarray(ds.variables[v][:], float)
                        iv = "I_" + v
                        if iv in ds.variables and cubo > 0:
                            a = a + np.asarray(ds.variables[iv][:], float) * cubo
                        tot += np.nanmean(np.where(m[None], a, np.nan).reshape(len(t), -1), axis=1)
                inc = np.diff(tot, prepend=np.nan)
                if previo is not None and np.isfinite(tot[0]):
                    inc[0] = tot[0] - previo if tot[0] >= previo else tot[0]          # continuación o nuevo arranque
                    if tot[0] < previo:
                        info["avisos"].append(f"{f.name}: la acumulada reinicia (nueva corrida); el primer paso se toma como acumulado desde su inicio.")
                elif not np.isfinite(inc[0]):
                    inc[0] = tot[0] if len(t) else np.nan
                neg = inc < -1e-6
                if neg.any():
                    info["avisos"].append(f"{f.name}: {int(neg.sum())} incrementos negativos (¿reinicio de cubo?) llevados a 0.")
                inc = np.where(neg, 0.0, inc)
                previo = tot[-1] if len(tot) else previo
                trozos.append(pd.DataFrame({"fecha": t, "lluvia_mm": inc}))
            else:
                v = next((ds.variables[k] for k in VARS_LLUVIA if k in ds.variables), None)
                if v is None:
                    raise WRFError(f"{f.name}: no hay RAINC/RAINNC ni una variable de lluvia ({', '.join(VARS_LLUVIA)}).")
                info["formato"] = f"NetCDF posprocesado (variable «{v.name}», unidades «{getattr(v, 'units', '?')}»)"
                tn = next((k for k in ("time", "Time", "t", "valid_time") if k in ds.variables), None)
                if tn is None:
                    raise WRFError(f"{f.name}: sin variable de tiempo.")
                tv = ds.variables[tn]; t = pd.to_datetime([str(x) for x in nc.num2date(tv[:], tv.units, getattr(tv, "calendar", "standard"))])
                a = np.asarray(v[:], float).reshape(len(t), *lat2.shape)
                s = np.nanmean(np.where(m[None], a, np.nan).reshape(len(t), -1), axis=1)
                u = str(getattr(v, "units", "")).lower().replace(" ", "")
                paso = (t[1] - t[0]).total_seconds() if len(t) > 1 else 86400.0
                if u in ("kgm-2s-1", "kg/m2/s", "kgm**-2s**-1", "mm/s"):
                    s = s * paso
                elif u in ("m",):
                    s = s * 1000.0
                elif u in ("mm/day", "mm/d", "mmday-1", "mm/dia") and paso < 86400:
                    s = s * paso / 86400.0
                elif u not in ("mm", "mm/h", "mm/hr", "mmh-1", ""):
                    info["avisos"].append(f"Unidades «{getattr(v, 'units', '')}» no reconocidas: se leen como mm por paso.")
                trozos.append(pd.DataFrame({"fecha": t, "lluvia_mm": s}))
    df = pd.concat(trozos).dropna(subset=["fecha"]).drop_duplicates("fecha").sort_values("fecha").reset_index(drop=True)
    if df.empty:
        raise WRFError("No se obtuvo ninguna serie.")
    paso = df["fecha"].diff().median()
    info.update(inicio=str(df["fecha"].iloc[0]), fin=str(df["fecha"].iloc[-1]), paso=str(paso), n_pasos=int(len(df)), total_mm=round(float(df["lluvia_mm"].sum()), 2),
                maximo_paso_mm=round(float(df["lluvia_mm"].max()), 2), zona_horaria="UTC (convención de WRF)")
    return df, info


def corregir(df, ref_diaria):
    """QQM diario contra la referencia (Series diaria en mm) y reparto horario por la razón diaria. Devuelve (df_corr, info)."""
    from .cmip6_sesgo import QQM, SesgoError
    d = df.set_index("fecha")["lluvia_mm"]
    dia = d.resample("D").sum(min_count=1)
    if ref_diaria is None:
        return df, {"corregido": False, "motivo": "sin referencia"}
    ref = ref_diaria.copy(); ref.index = pd.to_datetime(ref.index).normalize()
    comun = dia.dropna().index.intersection(ref.dropna().index)
    if len(comun) < 365 * 4:
        return df, {"corregido": False, "motivo": f"periodo común de {len(comun)} días (mínimo ~4 años): WRF se usa sin corregir"}
    try:
        q = QQM().fit(ref.loc[comun], dia.loc[comun])
    except SesgoError as e:
        return df, {"corregido": False, "motivo": str(e)}
    dc = q.transform(dia)
    razon = (dc / dia.replace(0, np.nan)).fillna(0.0)
    out = df.copy(); out["lluvia_mm"] = out["lluvia_mm"].values * razon.reindex(out["fecha"].dt.normalize()).fillna(0.0).values
    return out, {"corregido": True, "metodo": "QQM mensual (igual que CMIP6) sobre totales diarios; reparto horario por la razón diaria", "dias_comunes": int(len(comun)),
                 "total_crudo_mm": round(float(dia.sum()), 1), "total_corregido_mm": round(float(dc.sum()), 1)}


def _referencia(carpeta, fuente):
    if fuente == "chirps":
        dl = sorted((Path(carpeta) / "datos_descargados").glob("chirps_2*"))
        for d in dl[::-1]:
            f = d / "chirps_diario.csv"
            if f.exists():
                r = pd.read_csv(f); return pd.Series(r["pixel_mm"].values, index=pd.to_datetime(r["fecha"])), f"CHIRPS píxel del sitio ({d.name})"
        return None, "no hay CHIRPS descargado"
    return None, "sin corrección"


def procesar(carpeta, datos, ruta, ambito="sitio", correccion="chirps", rol="X", nombre=None):
    """Lee las salidas, corrige (opcional), guarda en datos/wrf_<sello>/ y devuelve el resumen. rol: «X» (histórico/reanálisis) o «Y» (escenario)."""
    carpeta = Path(carpeta)
    if rol not in ("X", "Y"):
        raise WRFError("El rol debe ser X (condición existente) o Y (escenario).")
    m = re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(datos.get("ubicacion", "")))
    if not m:
        raise WRFError("El proyecto no tiene sitio (lon, lat).")
    lon, lat = float(m.group(1)), float(m.group(2))
    pol = None
    if ambito == "cuenca":
        act = carpeta / "cuenca" / "activa.json"
        if not act.exists():
            raise WRFError("No hay cuenca activa (módulo 6 · hidro).")
        import geopandas as gpd
        a = json.loads(act.read_text(encoding="utf-8")); pol = gpd.read_file(carpeta / a["carpeta"] / "cuenca.gpkg").to_crs(4326).geometry.unary_union
    df, info = leer(ruta, lon, lat, pol)
    ref, txt_ref = _referencia(carpeta, correccion)
    dfc, corr = corregir(df, ref)
    corr["referencia"] = txt_ref
    sello = time.strftime("%Y%m%d_%H%M%S")
    out = carpeta / "datos" / f"wrf_{sello}"; out.mkdir(parents=True)
    df.assign(fecha=df["fecha"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(out / "wrf_crudo.csv", index=False)
    dfc.assign(fecha=dfc["fecha"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(out / "wrf_lluvia.csv", index=False)
    dia = dfc.set_index("fecha")["lluvia_mm"].resample("D").sum(min_count=1).rename("lluvia_mm").reset_index()
    dia.assign(fecha=dia["fecha"].dt.strftime("%Y-%m-%d")).to_csv(out / "wrf_diario.csv", index=False)
    res = {"nombre": nombre or f"WRF {sello}", "rol": rol, "ambito": ambito, "lectura": info, "correccion": corr, "carpeta": str(out.relative_to(carpeta)).replace("\\", "/"),
           "nota": "Lluvia simulada por WRF (no observada). Rol " + ("X: condición existente/reanálisis." if rol == "X" else "Y: escenario (se muestra en magenta).")}
    (out / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    try:
        (out / "wrf_lluvia.png").write_bytes(figura(df, dfc, res))
    except Exception:
        pass
    return res


def registrar_como_estacion(carpeta, datos, carpeta_wrf, ide=None):
    """La serie WRF corregida queda como «estación» del proyecto: sirve de forzamiento observado en land y en la calibración."""
    from . import estaciones as EST
    d = Path(carpeta) / carpeta_wrf
    r = json.loads((d / "resumen.json").read_text(encoding="utf-8"))
    m = re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(datos.get("ubicacion", "")))
    ide = ide or f"WRF_{d.name.split('_', 1)[1]}"
    return EST.importar(carpeta, datos["crs"], str(d / "wrf_lluvia.csv"), {"id": ide, "nombre": r["nombre"], "tipo": "otra", "lon": m.group(1), "lat": m.group(2),
                                                                        "col_fecha": "fecha", "col_lluvia": "lluvia_mm", "zona_horaria": "UTC", "dayfirst": False, "fuente": f"WRF · rol {r['rol']} · {r['lectura']['seleccion']}"})


def figura(df, dfc, res):
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .cuenca import _BLOQUEO_PNG
    col = "#d4147f" if res["rol"] == "Y" else "#6cc4ec"
    with _BLOQUEO_PNG:
        fig, ax = plt.subplots(figsize=(11, 3.6), dpi=110, facecolor="#0f1724"); ax.set_facecolor("#131d2b")
        largo = (df["fecha"].iloc[-1] - df["fecha"].iloc[0]).days
        if largo > 60:
            a = df.set_index("fecha")["lluvia_mm"].resample("D").sum(); b = dfc.set_index("fecha")["lluvia_mm"].resample("D").sum(); u = "mm/día"
        else:
            a = df.set_index("fecha")["lluvia_mm"]; b = dfc.set_index("fecha")["lluvia_mm"]; u = "mm/paso"
        ax.plot(a.index, a.values, color="#8b95a3", lw=0.8, label="WRF crudo")
        if res["correccion"].get("corregido"):
            ax.plot(b.index, b.values, color=col, lw=1.1, label="WRF corregido (QQM)")
        ax.set_ylabel(u, color="#8b95a3"); ax.tick_params(colors="#8b95a3", labelsize=7); ax.grid(alpha=0.15); ax.legend(fontsize=7)
        [s_.set_color("#2a3647") for s_ in ax.spines.values()]
        ax.set_title(f"{res['nombre']} · rol {res['rol']} · {res['lectura']['seleccion']} · total {res['lectura']['total_mm']} mm", color="#e6edf3", fontsize=9)
        fig.tight_layout(); bio = io.BytesIO(); fig.savefig(bio, format="png", facecolor=fig.get_facecolor()); plt.close(fig)
    return bio.getvalue()


# ------------------------------------------------------------------------------------------------ (2) preparar una corrida
FISICA = {"mp_physics": 8, "cu_physics": [1, 1, 0], "ra_lw_physics": 4, "ra_sw_physics": 4, "bl_pbl_physics": 1, "sf_sfclay_physics": 1, "sf_surface_physics": 2}
FISICA_TXT = ("Microfísica Thompson (8); cúmulos Kain-Fritsch (1) en d01-d02 y explícita en d03 (≤ 3 km); radiación RRTMG (4); capa límite YSU (1); "
              "capa superficial MM5 revisada (1); suelo Noah (2). Configuración de referencia: ajústala y documéntala para tu estudio.")


def preparar_corrida(carpeta, datos, inicio, fin, dx_d01_km=27.0, razon=3, tam=(100, 100, 100), forzante="ERA5", salida_h=1):
    m = re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(datos.get("ubicacion", "")))
    if not m:
        raise WRFError("El proyecto no tiene sitio (lon, lat).")
    lon, lat = float(m.group(1)), float(m.group(2))
    t0, t1 = pd.Timestamp(inicio), pd.Timestamp(fin)
    if not t1 > t0:
        raise WRFError("La fecha final debe ser posterior a la inicial.")
    if (t1 - t0).days > 31:
        raise WRFError("Para un evento, prepara como máximo 31 días por corrida.")
    if razon not in (3, 5):
        raise WRFError("La razón de anidamiento debe ser 3 o 5.")
    n = [int(x) for x in tam]
    for k, v in enumerate(n):
        if not 40 <= v <= 400:
            raise WRFError("El tamaño de cada dominio debe estar entre 40 y 400 celdas.")
        if k and (v - 1) % razon:
            n[k] = v + (razon - (v - 1) % razon)                                       # e_we − 1 debe ser múltiplo de la razón
    dx = [dx_d01_km * 1000 / razon ** k for k in range(3)]
    ips = [1] + [int((n[k - 1] - n[k] / razon) / 2) for k in (1, 2)]
    fmt = lambda t: t.strftime("%Y-%m-%d_%H:%M:%S")
    wps = f"""&share
 wrf_core = 'ARW',
 max_dom = 3,
 start_date = '{fmt(t0)}', '{fmt(t0)}', '{fmt(t0)}',
 end_date   = '{fmt(t1)}', '{fmt(t1)}', '{fmt(t1)}',
 interval_seconds = {21600 if forzante == "GFS" else 10800},
/
&geogrid
 parent_id         = 1, 1, 2,
 parent_grid_ratio = 1, {razon}, {razon},
 i_parent_start    = {ips[0]}, {ips[1]}, {ips[2]},
 j_parent_start    = {ips[0]}, {ips[1]}, {ips[2]},
 e_we              = {n[0]}, {n[1]}, {n[2]},
 e_sn              = {n[0]}, {n[1]}, {n[2]},
 geog_data_res     = 'default', 'default', 'default',
 dx = {dx[0]:.0f},
 dy = {dx[0]:.0f},
 map_proj  = 'mercator',
 ref_lat   = {lat:.4f},
 ref_lon   = {lon:.4f},
 truelat1  = {lat:.4f},
 stand_lon = {lon:.4f},
 geog_data_path = '/ruta/a/WPS_GEOG/'
/
&ungrib
 out_format = 'WPS',
 prefix = '{forzante}',
/
&metgrid
 fg_name = '{forzante}'
/
"""
    dt = int(min(6 * dx[0] / 1000, 180))
    lista = lambda v: ", ".join(str(x) for x in v)
    inp = f"""&time_control
 run_days = 0, run_hours = {int((t1 - t0).total_seconds() // 3600)}, run_minutes = 0, run_seconds = 0,
 start_year = {t0.year}, {t0.year}, {t0.year}, start_month = {t0.month:02d}, {t0.month:02d}, {t0.month:02d}, start_day = {t0.day:02d}, {t0.day:02d}, {t0.day:02d},
 start_hour = {t0.hour:02d}, {t0.hour:02d}, {t0.hour:02d},
 end_year = {t1.year}, {t1.year}, {t1.year}, end_month = {t1.month:02d}, {t1.month:02d}, {t1.month:02d}, end_day = {t1.day:02d}, {t1.day:02d}, {t1.day:02d},
 end_hour = {t1.hour:02d}, {t1.hour:02d}, {t1.hour:02d},
 interval_seconds = {21600 if forzante == "GFS" else 10800},
 input_from_file = .true., .true., .true.,
 history_interval = {salida_h * 60}, {salida_h * 60}, {salida_h * 60},
 frames_per_outfile = 24, 24, 24,
 restart = .false., restart_interval = 1440,
 io_form_history = 2, io_form_restart = 2, io_form_input = 2, io_form_boundary = 2,
/
&domains
 time_step = {dt},
 max_dom = 3,
 e_we = {lista(n)}, e_sn = {lista(n)}, e_vert = 45, 45, 45,
 p_top_requested = 5000,
 num_metgrid_levels = {38 if forzante == "ERA5" else 34},
 num_metgrid_soil_levels = 4,
 dx = {lista(int(x) for x in dx)}, dy = {lista(int(x) for x in dx)},
 grid_id = 1, 2, 3, parent_id = 0, 1, 2,
 i_parent_start = {lista(ips)}, j_parent_start = {lista(ips)},
 parent_grid_ratio = 1, {razon}, {razon}, parent_time_step_ratio = 1, {razon}, {razon},
 feedback = 1, smooth_option = 0,
/
&physics
 mp_physics = {FISICA['mp_physics']}, {FISICA['mp_physics']}, {FISICA['mp_physics']},
 cu_physics = {lista(FISICA['cu_physics'])},
 ra_lw_physics = 4, 4, 4, ra_sw_physics = 4, 4, 4, radt = {int(dx[0] / 1000)}, {int(dx[0] / 1000)}, {int(dx[0] / 1000)},
 bl_pbl_physics = 1, 1, 1, sf_sfclay_physics = 1, 1, 1, sf_surface_physics = 2, 2, 2,
 num_land_cat = 21, num_soil_layers = 4, cudt = 0, 0, 0,
/
&dynamics
 w_damping = 1, diff_opt = 1, 1, 1, km_opt = 4, 4, 4, damp_opt = 3, zdamp = 5000., 5000., 5000., dampcoef = 0.2, 0.2, 0.2,
 khdif = 0, 0, 0, kvdif = 0, 0, 0, non_hydrostatic = .true., .true., .true., moist_adv_opt = 1, 1, 1, scalar_adv_opt = 1, 1, 1,
/
&bdy_control
 spec_bdy_width = 5, specified = .true.,
/
&namelist_quilt
 nio_tasks_per_group = 0, nio_groups = 1,
/
"""
    sh = f"""#!/bin/bash
# Corrida WRF preparada por UCEclima para «{datos.get('nombre', '')}» ({fmt(t0)} → {fmt(t1)}, forzante {forzante}).
# Requisitos: WPS y WRF compilados (Linux o WSL), datos geográficos WPS_GEOG y los GRIB de {forzante} en ./grib/.
set -e
WPS=${{WPS_DIR:-$HOME/WPS}}; WRF=${{WRF_DIR:-$HOME/WRF/test/em_real}}; NP=${{NP:-4}}
cp namelist.wps "$WPS"/ && cd "$WPS"
./geogrid.exe
ln -sf ungrib/Variable_Tables/Vtable.{"ECMWF" if forzante == "ERA5" else "GFS"} Vtable
./link_grib.csh "$OLDPWD"/grib/*
./ungrib.exe && ./metgrid.exe
cd "$WRF" && ln -sf "$WPS"/met_em.d0* . && cp "$OLDPWD"/namelist.input .
mpirun -np "$NP" ./real.exe && mpirun -np "$NP" ./wrf.exe
echo "Listo: copia wrfout_d03_* a Windows y cárgalos en UCEclima (módulo WRF · Leer salidas)."
"""
    sello = time.strftime("%Y%m%d_%H%M%S")
    out = Path(carpeta) / "wrf_corridas" / f"corrida_{sello}"; out.mkdir(parents=True)
    (out / "namelist.wps").write_text(wps, encoding="utf-8"); (out / "namelist.input").write_text(inp, encoding="utf-8")
    (out / "ejecutar_wrf.sh").write_bytes(sh.replace("\r\n", "\n").encode("utf-8")); (out / "grib").mkdir()   # fin de línea Linux
    res = {"carpeta": str(out.relative_to(carpeta)).replace("\\", "/"), "dominios": [{"dominio": f"d0{k + 1}", "dx_km": round(dx[k] / 1000, 2), "celdas": f"{n[k]}×{n[k]}",
                                                                                       "lado_km": round(dx[k] * (n[k] - 1) / 1000, 1)} for k in range(3)],
           "time_step_s": dt, "fisica": FISICA_TXT, "forzante": forzante, "inicio": str(t0), "fin": str(t1),
           "pasos": ["Copia la carpeta a Linux/WSL con WPS y WRF compilados.", f"Descarga los GRIB de {forzante} del periodo en ./grib/.", "Ejecuta: bash ejecutar_wrf.sh",
                     "Trae los wrfout_d03_* y cárgalos en UCEclima · WRF · Leer salidas."]}
    (out / "LEEME.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
