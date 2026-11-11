# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
import sys, traceback
import numpy as np, pandas as pd
import uceclima
from uceclima import seleccion_eventos as S


def _serie(n=800, picos=((50, 120), (200, 90), (230, 100), (500, 70), (640, 130))):
    f = pd.date_range("2010-08-01", periods=n)
    P = np.zeros(n); Q = np.full(n, 5.0)
    for i, mm in picos:
        P[i] = mm; Q[i + 2:i + 6] += mm * 0.8
    return pd.DataFrame({"fecha": f, "P_mm": P, "rellenado": False, "Q_m3s": Q})


G = {"alfa": 24.4, "u": 104.6, "n": 31}


def test_picos_desagrupados_y_tr():
    d = _serie(); c = S.Criterios()
    pk = S.identificar_picos(d, c)
    assert pk == [50, 200, 230, 500, 640] or pk == [50, 200, 500, 640]          # 200 y 230 distan 30 d (>=14): ambos independientes
    e = S.filtrar(S.evaluar(d, pk, G, c), c)
    assert e.cumple.all() and e.Tr_P_max_dia_anios.iloc[0] < e.Tr_P_max_dia_anios.iloc[-1]


def test_datos_incompletos_se_descartan_no_se_rellenan():
    d = _serie(); d.loc[52, "Q_m3s"] = np.nan; d.loc[198, "rellenado"] = True
    c = S.Criterios(); e = S.filtrar(S.evaluar(d, S.identificar_picos(d, c), G, c), c).set_index("evento")
    assert not e.iloc[0].cumple and "caudal ausente" in e.iloc[0].motivo_descarte
    assert not e.iloc[1].cumple and "rellenada" in e.iloc[1].motivo_descarte


def test_bloques_por_anio_hidrologico_sin_antecedentes_compartidos_y_hms_marcado():
    d = _serie(); c = S.Criterios(); e = S.filtrar(S.evaluar(d, S.identificar_picos(d, c), G, c), c)
    sel, bl = S.seleccionar_por_bloques(e, [("HMS X", "2010-09-18", "2010-09-25")])
    f = pd.to_datetime(sel.fecha_pico_lluvia)
    for (_, a), fa in zip(sel.iterrows(), f):
        for (_, b), fb in zip(sel.iterrows(), f):
            if a.rol != b.rol: assert S.anio_hidrologico(fa) != S.anio_hidrologico(fb)             # un bloque entero va a un solo rol
    assert set(bl.rol) <= {"calibracion", "validacion"} and bl.rol.iloc[0] == "calibracion"
    assert S.seleccionar_por_bloques(e, [])[0].equals(S.seleccionar_por_bloques(e, [])[0])           # determinista


if __name__ == "__main__":
    fallos = 0
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            try:
                f(); print("OK   ", name)
            except BaseException as e:
                fallos += 1; print("FALLA", name, "->", repr(e)); traceback.print_exc(limit=3)
    sys.exit(1 if fallos else 0)
