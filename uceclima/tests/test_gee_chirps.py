# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Pruebas de la lógica de GEE/CHIRPS con un `ee` simulado (sin red). El humo en vivo se hace aparte, explícitamente."""
import sys, tempfile, traceback
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import box
import uceclima
from uceclima import gee_chirps as G
from uceclima.eventos import Evento


class _Col:
    def __init__(self, ids): self.ids = ids
    def filterDate(self, a, b): return _Col([i for i in self.ids if a.replace("-", "") <= i < b.replace("-", "")])
    def aggregate_array(self, campo): return self
    def getInfo(self): return self.ids


class EEFalso:
    """Solo lo necesario para `disponibilidad`: v3 con un hueco; v2 completo."""
    __version__ = "falso"
    def __init__(self, v3, v2): self.v = {"UCSB-CHC/CHIRPS/V3/DAILY_SAT": v3, "UCSB-CHG/CHIRPS/DAILY": v2}
    def ImageCollection(self, nombre):
        if nombre not in self.v: raise RuntimeError("no existe")
        return _Col(self.v[nombre])


def _ids(d0, d1, quitar=()):
    out, a = [], pd.Timestamp(d0)
    while a < pd.Timestamp(d1):
        s = a.strftime("%Y%m%d")
        if s not in quitar: out.append(s)
        a += pd.Timedelta(days=1)
    return out


def _plan():
    return Evento("e", "2011-02-02T00:00:00-05:00", "2011-02-04T00:00:00-05:00", "M0037").plan()


def test_prefiere_v3_usa_v2_solo_si_cubre_y_no_mezcla():
    p = _plan(); a, b = p["consulta_total"][0][:10], p["consulta_total"][1][:10]
    todo = _ids(a, b)
    s = G.seleccionar(p, G.disponibilidad(p, EEFalso(todo, todo))); assert s["version"] == "v3_daily_sat" and not s["fallback"]
    s = G.seleccionar(p, G.disponibilidad(p, EEFalso(_ids(a, b, quitar={"20110210"}), todo)))
    assert s["version"] == "v2_daily" and s["fallback"] and "20110210".replace("", "") is not None
    assert "2011-02-10" in s["diagnostico"]["v3_daily_sat"]["dias_faltantes"]                 # el fallback queda registrado y justificado
    s = G.seleccionar(p, G.disponibilidad(p, EEFalso(_ids(a, b, {"20110210"}), _ids(a, b, {"20110211"}))))
    assert s["version"] is None and not s["cobertura_completa"]                               # ninguna cubre: NO se mezclan versiones
    try:
        G.serie_por_cuenca(s, p, gpd.GeoDataFrame({"nombre": ["a"]}, geometry=[box(0, 0, 1, 1)], crs=4326), EEFalso([], []))
        raise SystemExit("debió negarse a descargar")
    except RuntimeError:
        pass


def test_limite_contra_descargas_masivas():
    p = Evento("e", "2011-01-01T00:00:00-05:00", "2011-12-31T00:00:00-05:00", "M0037").plan()
    sel = {"cobertura_completa": True, "version": "v3_daily_sat", "coleccion": "x"}
    try:
        G.serie_por_cuenca(sel, p, gpd.GeoDataFrame({"nombre": ["a"]}, geometry=[box(0, 0, 1, 1)], crs=4326), EEFalso([], []))
        raise SystemExit("debió rechazar la consulta enorme")
    except ValueError as e:
        assert "demasiado grande" in str(e)


def test_ventanas_sin_solape_accidental_y_ausencias_no_son_cero():
    p = _plan(); dias = pd.date_range(p["consulta_total"][0][:10], p["consulta_total"][1][:10], inclusive="left")
    df = pd.DataFrame([(d, "A", 1.0) for d in dias], columns=["fecha_utc", "nombre", "mm"])
    w = G.ventanas(df, p).set_index(["ventana", "nombre"])
    assert w.loc[("evento", "A"), "acumulado_mm"] == w.loc[("evento", "A"), "dias_esperados"]                  # 1 mm/día
    assert w.loc[("antes_21d", "A"), "acumulado_mm"] == 21 and w.loc[("antes_5d", "A"), "acumulado_mm"] == 5
    assert w.loc[("antes_6a21d", "A"), "acumulado_mm"] == 16 and w.loc[("despues_6a21d", "A"), "acumulado_mm"] == 16   # complementarias sin solape con ±5
    df.loc[df.fecha_utc == dias[3], "mm"] = np.nan                                                              # un día sin dato
    w2 = G.ventanas(df, p).set_index(["ventana", "nombre"])
    assert np.isnan(w2.loc[("antes_21d", "A"), "acumulado_mm"]) and w2.loc[("antes_21d", "A"), "dias_con_dato"] == 20


def test_credenciales_no_se_guardan_en_el_repositorio():
    raiz = Path(G.__file__).resolve().parent
    for f in raiz.rglob("*.py"):
        t = f.read_text(encoding="utf-8", errors="ignore").lower()
        if f.name != "test_gee_chirps.py":
            assert "refresh_token" not in t and "private_key" not in t, f
    assert G.CONFIG_USUARIO.is_relative_to(Path.home()) and not G.CONFIG_USUARIO.is_relative_to(raiz)


if __name__ == "__main__":
    fallos = 0
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            try:
                f(); print("OK   ", name)
            except BaseException as e:
                fallos += 1; print("FALLA", name, "->", repr(e)); traceback.print_exc(limit=3)
    sys.exit(1 if fallos else 0)
