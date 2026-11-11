# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""WRF (lectura de salidas sintéticas con respuesta conocida, registro como estación, namelist) y Time of Emergence (serie sintética).
Ejecutar: python -m uceclima.tests.test_wrf_toe"""
import json, shutil, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd

import uceclima
from uceclima import wrf as W, toe as T, estaciones as EST
from uceclima.ui import sitio_api

TMP = Path(tempfile.mkdtemp(prefix="uceclima_wrf_"))
LON, LAT = -78.645, -2.585


def _wrfout(ruta, t0, horas, incrementos, acum0=0.0, nx=12, ny=10):
    """wrfout mínimo: Times, XLAT/XLONG (Time, sn, we), RAINC/RAINNC acumuladas. incrementos: mm por hora en TODA la malla."""
    import netCDF4
    with netCDF4.Dataset(ruta, "w") as d:
        d.createDimension("Time", None); d.createDimension("DateStrLen", 19); d.createDimension("south_north", ny); d.createDimension("west_east", nx)
        ts = d.createVariable("Times", "S1", ("Time", "DateStrLen"))
        t = pd.date_range(t0, periods=horas, freq="h")
        ts[:] = netCDF4.stringtochar(np.array([x.strftime("%Y-%m-%d_%H:%M:%S") for x in t], dtype="S19"))
        la, lo = np.meshgrid(np.linspace(LAT - 0.3, LAT + 0.3, ny), np.linspace(LON - 0.3, LON + 0.3, nx), indexing="ij")
        for nom, v in (("XLAT", la), ("XLONG", lo)):
            x = d.createVariable(nom, "f4", ("Time", "south_north", "west_east")); x[:] = np.repeat(v[None], horas, 0)
        acum = acum0 + np.cumsum(incrementos)
        for nom, frac in (("RAINC", 0.3), ("RAINNC", 0.7)):
            x = d.createVariable(nom, "f4", ("Time", "south_north", "west_east")); x[:] = np.repeat((acum * frac)[:, None, None], ny, 1).repeat(nx, 2)
    return acum[-1]


def test_wrfout_continuacion_y_reinicio():
    inc1 = np.array([0, 1, 2, 5, 3, 0, 0, 1.5]); inc2 = np.array([2, 2, 0, 0, 4, 1, 0, 0.5])
    car = TMP / "wrf1"; car.mkdir()
    fin1 = _wrfout(car / "wrfout_d03_2026-01-01_00", "2026-01-01 00:00", 8, inc1)
    _wrfout(car / "wrfout_d03_2026-01-01_08", "2026-01-01 08:00", 8, inc2, acum0=fin1)                   # continúa la acumulada
    df, info = W.leer(car, LON, LAT)
    assert len(df) == 16 and abs(df["lluvia_mm"].sum() - (inc1.sum() + inc2.sum())) < 1e-3, (df["lluvia_mm"].sum(), info)
    assert np.allclose(df["lluvia_mm"].values[1:8], inc1[1:], atol=1e-4) and "RAINC" in info["formato"]
    car2 = TMP / "wrf2"; car2.mkdir()
    _wrfout(car2 / "wrfout_a", "2026-02-01 00:00", 6, np.array([1, 1, 1, 1, 1, 1.0]))
    _wrfout(car2 / "wrfout_b", "2026-02-01 06:00", 6, np.array([2, 0, 0, 0, 0, 0.0]))                     # corrida nueva: reinicia
    df2, info2 = W.leer(car2, LON, LAT)
    assert abs(df2["lluvia_mm"].sum() - 8.0) < 1e-3 and any("reinicia" in a for a in info2["avisos"])


def test_netcdf_posprocesado_en_kg_m2_s():
    import netCDF4
    f = TMP / "pr_diario.nc"
    with netCDF4.Dataset(f, "w") as d:
        d.createDimension("time", 5); d.createDimension("lat", 6); d.createDimension("lon", 7)
        t = d.createVariable("time", "f8", ("time",)); t.units = "days since 2026-03-01 00:00:00"; t[:] = np.arange(5)
        d.createVariable("lat", "f4", ("lat",))[:] = np.linspace(LAT - 0.2, LAT + 0.2, 6); d.createVariable("lon", "f4", ("lon",))[:] = np.linspace(LON - 0.2, LON + 0.2, 7)
        p = d.createVariable("pr", "f4", ("time", "lat", "lon")); p.units = "kg m-2 s-1"; p[:] = (np.array([0, 10, 20, 5, 0.0]) / 86400.0)[:, None, None] * np.ones((5, 6, 7))
    df, info = W.leer(f, LON, LAT)
    assert np.allclose(df["lluvia_mm"].values, [0, 10, 20, 5, 0], atol=1e-3) and "pr" in info["formato"]


def test_fuera_del_dominio_falla_claro():
    car = TMP / "wrf3"; car.mkdir(); _wrfout(car / "wrfout_x", "2026-01-01", 3, np.ones(3))
    try:
        W.leer(car, -80.5, -0.5); assert False
    except W.WRFError as e:
        assert "no cubre" in str(e)


def test_procesar_registra_estacion_y_namelist():
    c = sitio_api.crear("wrf proyecto", LON, LAT, base=str(TMP))
    datos = json.loads((Path(c) / "proyecto_uceclima.json").read_text(encoding="utf-8"))
    car = TMP / "wrf4"; car.mkdir(); _wrfout(car / "wrfout_d03", "2026-01-05 00:00", 24, np.r_[np.zeros(6), np.full(6, 4.0), np.zeros(12)])
    r = W.procesar(c, datos, car, ambito="sitio", correccion="chirps", rol="X")
    assert r["correccion"]["corregido"] is False and abs(r["lectura"]["total_mm"] - 24.0) < 1e-3
    est = W.registrar_como_estacion(c, datos, r["carpeta"])
    assert est["estacion"]["id"].startswith("WRF_") and any(e["id"] == est["estacion"]["id"] for e in EST.listar(c))
    n = W.preparar_corrida(c, datos, "2026-01-05 00:00", "2026-01-07 00:00", tam=(100, 100, 100))
    d = Path(c) / n["carpeta"]
    wps = (d / "namelist.wps").read_text(encoding="utf-8"); inp = (d / "namelist.input").read_text(encoding="utf-8")
    assert "ref_lat   = -2.5850" in wps and "max_dom = 3" in inp and (d / "ejecutar_wrf.sh").exists()
    assert [x["dx_km"] for x in n["dominios"]] == [27.0, 9.0, 3.0] and all((int(x["celdas"].split("×")[0]) - 1) % 3 == 0 for x in n["dominios"][1:])
    for malo in (("2026-01-07", "2026-01-05"), ("2026-01-01", "2026-03-01")):
        try:
            W.preparar_corrida(c, datos, *malo); assert False
        except W.WRFError:
            pass


def test_toe_serie_sintetica_respuesta_conocida():
    anios = np.arange(1981, 2101)
    rng = np.random.default_rng(1)
    base = rng.normal(100, 10, len(anios))
    tend = np.where(anios > 2030, (anios - 2030) * 1.0, 0.0)                    # +1 mm/año desde 2031; ruido σ≈10
    r = T.toe_serie(pd.Series(base + tend, index=anios), ventana=20, umbral=1.0)
    assert r["signo"] == 1 and 2035 <= r["toe"] <= 2055, r["toe"]
    r0 = T.toe_serie(pd.Series(base, index=anios), ventana=20, umbral=1.0)
    assert r0["toe"] is None                                                    # sin señal no emerge
    s = pd.Series(np.r_[np.zeros(360), np.full(5, 10.0)], index=pd.date_range("2001-01-01", periods=365))
    ia = T.indices_anuales(s); assert ia.loc[2001, "Rx5day"] == 50 and ia.loc[2001, "PRCPTOT"] == 50 and ia.loc[2001, "R20mm"] == 0
    assert ia.loc[2001, "CDD"] == 360 and ia.loc[2001, "CWD"] == 5 and ia.loc[2001, "SDII"] == 10                      # Gamma: rachas e intensidad


def test_gamma_ensamble_no_mezcla_signos_opuestos():
    anios = np.arange(1981, 2101); rng = np.random.default_rng(3)
    sube = pd.Series(rng.normal(100, 10, len(anios)) + np.where(anios > 2030, (anios - 2030) * 1.0, 0), index=anios)
    baja = pd.Series(rng.normal(100, 10, len(anios)) - np.where(anios > 2030, (anios - 2030) * 1.0, 0), index=anios)
    e = T.toe_ensamble({"A": sube, "B": baja}, {"A": 0.5, "B": 0.5})
    assert e["toe"] is None and abs(e["acuerdo_signo"] - 0.5) < 1e-9                       # discrepan → la dispersión infla el ruido: no emerge
    sube2 = pd.Series(rng.normal(100, 10, len(anios)) + np.where(anios > 2030, (anios - 2030) * 1.0, 0), index=anios)
    e2 = T.toe_ensamble({"A": sube, "C": sube2}, {"A": 0.5, "C": 0.5})
    assert e2["signo"] == 1 and 2035 <= e2["toe"] <= 2070 and e2["acuerdo_signo"] == 1.0    # coinciden → emerge con aumento


def test_gamma_spi_y_ruido_sin_tendencia():
    rng = np.random.default_rng(5); d = pd.date_range("1981-01-01", "2020-12-31")
    s = pd.Series(rng.gamma(0.6, 8, len(d)) * (rng.random(len(d)) < 0.5), index=d)
    ia = T.indices_anuales(s)
    assert ia["SPI12_min"].loc[1982:2014].between(-4, 1.5).all() and ia["SPI3_secos"].loc[1982:2014].mean() > 0
    m = T._spi(s.resample("MS").sum(), 3); b = m[(m.index.year >= 1981) & (m.index.year <= 2014)].dropna()
    assert abs(b.mean()) < 0.15 and 0.8 < b.std() < 1.2                                      # SPI ~ N(0,1) en la base
    t = pd.Series(np.arange(34) * 3.0 + rng.normal(0, 1, 34), index=range(1981, 2015))
    assert T._ruido_base(t) < 2 < t.std()                                                     # la tendencia no se cuenta como ruido


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=4, file=sys.stdout)
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
