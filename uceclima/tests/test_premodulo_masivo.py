# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Premódulo · carga masiva: 127 estaciones (carpeta de CSV + catálogo de coordenadas, Excel ancho con códigos) y rechazo de tablas resumen. Sin red.
Ejecutar: python -m uceclima.tests.test_premodulo_masivo"""
import shutil, sys, tempfile, time, traceback
from pathlib import Path
import numpy as np
import pandas as pd

import uceclima
from uceclima import premodulo as PRE

TMP = Path(tempfile.mkdtemp(prefix="uceclima_masivo_"))
PRE.MEM_DIR = TMP / "memoria"                                   # nunca tocar la memoria real
N = 127
FECHAS = pd.date_range("2003-01-01", "2006-12-31")


def _limpio():
    PRE._MEM["series"].clear(); PRE._MEM["cargada"] = True; shutil.rmtree(PRE.MEM_DIR, ignore_errors=True)


def _esperar(maximo=600):
    t = time.time()
    while PRE.LOTE["activo"] and time.time() - t < maximo:
        time.sleep(0.3)
    assert not PRE.LOTE["activo"], "la carga masiva no terminó"
    return PRE.estado_lote()


def test_carpeta_de_127_csv_con_catalogo_de_coordenadas():
    _limpio()
    car = TMP / "quito_csv"; car.mkdir()
    rng = np.random.default_rng(5)
    for k in range(1, N + 1):
        pd.DataFrame({"fecha": FECHAS.strftime("%Y-%m-%d"), "precipitacion_mm": np.round(rng.gamma(0.5, 6, len(FECHAS)), 1)}).to_csv(car / f"P{k:03d}.csv", index=False)
    pd.DataFrame({"codigo": [f"P{k:03d}" for k in range(1, N + 1)], "nombre": [f"Estación {k}" for k in range(1, N + 1)],
                  "lon": -78.6 + np.arange(N) * 0.003, "lat": -0.35 + np.arange(N) * 0.002}).to_csv(car / "estaciones_catalogo_coordenadas.csv", index=False)
    pd.DataFrame({"fecha": ["2003", "2004"], "precipitacion_mm": [1200, 1300]}).to_csv(car / "lluvia_resumen.csv", index=False)
    t0 = time.time(); PRE.iniciar_lote(carpeta=str(car)); e = _esperar()
    m = PRE.memoria()
    assert m["n"] == N, (m["n"], e["errores"], [r["mensaje"] for r in e["resultados"] if r["estado"] != "ok"][:3])
    assert e["ok"] == N + 1 and e["errores"] == 1                                            # 127 series + catálogo; el resumen se rechaza
    assert any("resumen" in r["mensaje"] for r in e["resultados"] if r["estado"] == "error")
    assert e["catalogo"]["con_coordenadas"] == N and all(s["lon"] is not None for s in m["series"])
    assert time.time() - t0 < 300, f"tardó {time.time() - t0:.0f} s"


def test_excel_ancho_127_columnas_con_tipo_por_defecto():
    _limpio()
    f = TMP / "quito_ancho.xlsx"
    rng = np.random.default_rng(9)
    d = pd.DataFrame({"fecha": FECHAS}); d = pd.concat([d, pd.DataFrame(np.round(rng.gamma(0.5, 6, (len(FECHAS), N)), 1), columns=[f"P{k}" for k in range(1, N + 1)])], axis=1)
    d.to_excel(f, index=False)
    PRE.iniciar_lote(rutas=[str(f)]); e = _esperar()
    assert e["confirmar"] == 1 and PRE.memoria()["n"] == 0                                   # sin tipo por defecto: pregunta, no adivina
    PRE.iniciar_lote(rutas=[str(f)], tipo_defecto="lluvia"); e = _esperar()
    m = PRE.memoria(); assert m["n"] == N and all(s["tipo"] == "lluvia" for s in m["series"]), m["n"]


def test_no_dos_lotes_a_la_vez_y_tipo_valido():
    _limpio()
    try:
        PRE.iniciar_lote(rutas=[str(TMP / "x.csv")], tipo_defecto="temperatura"); assert False
    except PRE.PremoduloError:
        pass
    PRE.LOTE["activo"] = True
    try:
        PRE.iniciar_lote(rutas=["a.csv"]); assert False
    except PRE.PremoduloError as ex:
        assert "en curso" in str(ex)
    finally:
        PRE.LOTE["activo"] = False


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                t = time.time(); f(); print("OK   ", n, f"({time.time() - t:.0f} s)")
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=4, file=sys.stdout)
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
