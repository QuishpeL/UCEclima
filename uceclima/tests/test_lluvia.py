# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Pruebas del módulo 1 (lluvia y eventos). Ejecutar: python -m uceclima.tests.test_lluvia  (desde MILAGRO)"""
import sys, traceback
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np, pandas as pd
import uceclima
from uceclima.eventos import Evento
from uceclima.lluvia import DisenoIDF, EventoObservado, desagregar_uniforme
from climanet import inamhi

IDF = inamhi.idf_estacion("M0037")
TZ = "-05:00"


def _evento(horas=4):
    return Evento("e", "2011-02-02T00:00:00-05:00", f"2011-02-02T{horas:02d}:00:00-05:00", "M0037")


def test_diseno_conserva_volumen_exacto_y_no_tiene_fecha():
    d = DisenoIDF(IDF, 100, 180, fuente="INAMHI libro M0037")
    h = d.hietograma()
    assert h["tipo"] == "diseno_idf" and h["sin_fecha_meteorologica"] and "No es un evento observado" in h["aviso"]
    assert abs(h["volumen_mm"] - h["volumen_esperado_mm"]) < 1e-6 * h["volumen_esperado_mm"]
    hib = DisenoIDF(IDF, 100, 180, fuente="x", fecha_contexto="2011-02-02").hietograma()
    assert hib["tipo"].startswith("experimento_hibrido")
    for malo in (dict(factor=1.13), dict(tr=3)):
        try:
            DisenoIDF(IDF, malo.get("tr", 100), 180, fuente="x", factor=malo.get("factor", 1.0)); raise SystemExit("debió rechazar " + str(malo))
        except ValueError:
            pass


def test_observado_no_se_reemplaza_por_bloques_idf():
    ev = _evento(3)
    ini = ["2011-02-02T00:00:00-05:00", "2011-02-02T00:10:00-05:00", "2011-02-02T01:00:00-05:00"]      # intervalos IRREGULARES de pluviógrafo
    fin = ["2011-02-02T00:10:00-05:00", "2011-02-02T01:00:00-05:00", "2011-02-02T03:00:00-05:00"]
    mm = [12.0, 3.0, 5.0]
    o = EventoObservado(ev, ini, fin, mm)
    f = o.a_forzamiento()
    assert list(f["edges_s"]) == [0, 600, 3600, 10800] and list(f["mm"]) == mm and f["volumen_mm"] == 20.0 and f["tipo"] == "observada"
    for roto in (dict(mm=[12.0, float("nan"), 5.0]), dict(mm=[12.0, -1.0, 5.0])):
        try:
            EventoObservado(ev, ini, fin, roto["mm"]); raise SystemExit("ausente/negativa debió fallar")
        except ValueError:
            pass
    try:
        EventoObservado(ev, [ini[0], ini[2]], [fin[0], fin[2]], [12.0, 5.0]); raise SystemExit("hueco debió fallar")
    except ValueError:
        pass


def test_maxima_por_duracion_y_tr_implicito_sin_extrapolar():
    ev = _evento(4)
    t0 = datetime.fromisoformat("2011-02-02T00:00:00-05:00")
    mm = [0.0] * 8 + [10.0, 20.0, 5.0] + [0.0] * 37                       # 48 intervalos de 5 min
    ini = [(t0 + timedelta(minutes=5 * k)).isoformat() for k in range(48)]; fin = [(t0 + timedelta(minutes=5 * (k + 1))).isoformat() for k in range(48)]
    ev = Evento("e", ini[0], fin[-1], "M0037")
    o = EventoObservado(ev, ini, fin, mm)
    m = o.maxima_por_duracion([5, 15, 30])
    assert abs(m[5]["profundidad_mm"] - 20.0) < 1e-9 and abs(m[15]["profundidad_mm"] - 35.0) < 1e-9 and abs(m[30]["profundidad_mm"] - 35.0) < 1e-9
    assert o.maxima_por_duracion([2])[2].get("advertencia")
    c = o.comparar_con_idf(IDF, (15, 30))
    assert c[15]["Tr_implicito"] is not None
    suave = EventoObservado(ev, ini, fin, [0.01] * 48).comparar_con_idf(IDF, (30,))
    assert str(suave[30]["Tr_implicito"]).startswith("<")                  # menor que el Tr mínimo: no se extrapola
    gigante = EventoObservado(ev, ini, fin, [50.0] * 48).comparar_con_idf(IDF, (30,))
    assert str(gigante[30]["Tr_implicito"]).startswith(">")


def test_diaria_solo_entra_como_desagregada():
    ev = Evento("d", "2011-02-02T00:00:00-05:00", "2011-02-04T00:00:00-05:00", "M0037")
    o = desagregar_uniforme(["2011-02-02", "2011-02-03"], [48.0, 24.0], ev)
    assert o.tipo == "desagregada" and abs(o.a_forzamiento()["volumen_mm"] - 72.0) < 1e-9 and o.procedencia["incertidumbre"].startswith("alta")
    try:
        desagregar_uniforme(["2011-02-02"], [float("nan")], ev); raise SystemExit("nan debió fallar")
    except ValueError:
        pass
    try:
        EventoObservado(ev, o.inicios, o.finales, o.mm, tipo="inventada"); raise SystemExit("tipo inválido")
    except ValueError:
        pass


if __name__ == "__main__":
    fallos = 0
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            try:
                f(); print("OK   ", name)
            except BaseException as e:
                fallos += 1; print("FALLA", name, "->", repr(e)); traceback.print_exc(limit=3)
    sys.exit(1 if fallos else 0)
