# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Pruebas de la auditoría del Excel IDF. Se omiten si el archivo del usuario no está en la ruta indicada."""
import sys, traceback
from pathlib import Path
import numpy as np
import uceclima
from uceclima import idf_excel as X
from uceclima.lluvia import DisenoIDF

RUTA = Path(r"C:\Users\agdgq\Desktop\Curva-IDF-de-M0037 - INAMHI.xlsx")


def test_recomputo_independiente_coincide_con_las_celdas():
    if not RUTA.exists():
        print("  (omitida: no existe", RUTA, ")"); return
    rep = X.auditar(RUTA)
    assert rep["atribucion"]["autor_aportado_por_usuario"] == "Caiza 2026" and "pendiente" in rep["atribucion"]["referencia_bibliografica"]
    assert rep["recomputo"]["max_dif_relativa"] < 1e-9, rep["recomputo"]["max_dif_relativa"]
    assert rep["serie"]["n_anios"] == 31 and "CUMBE" in rep["serie"]["titulo_hoja"]
    assert any("Etiqueta de estación inconsistente" in h for h in rep["hallazgos"])           # el archivo dice M0037 pero la hoja dice CUMBE
    assert abs(rep["recomputo"]["parametros"]["K"] - 435.4874) < 1e-3 and abs(rep["recomputo"]["parametros"]["m"] - 0.18757) < 1e-4
    df = X.idf_dataframe(rep)
    h = DisenoIDF(df, 10, 60, fuente="Excel Caiza 2026 (hoja CUMBE)").hietograma()          # entra como fuente separada, con su rótulo
    assert h["fuente_idf"].startswith("Excel") and abs(h["volumen_mm"] - h["volumen_esperado_mm"]) < 1e-6 * h["volumen_esperado_mm"]


def test_gumbel_y_regresion_con_datos_sinteticos():
    rng = np.random.default_rng(2)
    x = 80 + 30 * rng.gumbel(size=40)
    XT, par = X.gumbel_momentos(x, [2, 10, 100], factor=1.0)
    assert XT[0] < XT[1] < XT[2] and abs(par["alfa"] - np.sqrt(6) / np.pi * x.std(ddof=1)) < 1e-12
    prm, f = X.recomputar(x)
    assert prm["n_prom"] < 0 and f(10, 60) > f(10, 120) > f(10, 360)                        # la intensidad decrece con la duración
    assert f(25, 30) > f(2, 30)                                                              # y crece con el periodo de retorno


if __name__ == "__main__":
    fallos = 0
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            try:
                f(); print("OK   ", name)
            except BaseException as e:
                fallos += 1; print("FALLA", name, "->", repr(e)); traceback.print_exc(limit=3)
    sys.exit(1 if fallos else 0)
