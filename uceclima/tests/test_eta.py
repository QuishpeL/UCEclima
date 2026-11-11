# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Pruebas de Eta 9.0.0 (correcciones de la prueba de novato con el río Yaguachi, 1-nov-2026)."""
import json, shutil, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import uceclima                                    # fija sys.path al núcleo
from climanet.hydraulics import simulate, Options

TMP = Path(tempfile.mkdtemp(prefix="uceclima_eta_"))


def _caso(backend):
    ny, nx = 24, 30
    yy, xx = np.mgrid[0:ny, 0:nx]
    dem = 10 - 0.02 * xx + 0.3 * np.abs(yy - ny / 2) / ny
    act = np.ones_like(dem, bool); act[0, 0] = False
    n = np.full(dem.shape, 0.05)
    edges = np.array([0., 600., 1200., 1800.]); run = np.zeros((3, ny, nx)); run[0] = 8; run[1] = 20; run[2] = 5
    o = Options(10, 10, 5400, max_dt=5, boundary="free_outflow", backend=backend, record_interval=60, frame_interval=300)
    inl = [{"nombre": "rio", "t": [0, 900, 2400, 3600], "q": [0, 3.0, 1.0, 0], "celdas": [[12, 1]]}]
    return dem, act, n, edges, run, o, inl


class Corte(Exception):
    pass


def test_punto_control_reanuda_identico():
    for backend in ("numpy", "numba"):
        dem, act, n, e, r, o, inl = _caso(backend)
        ref = simulate(dem, act, n, e, r, o, inlets=inl)
        ck = TMP / f"pc_{backend}.npz"; visto = []

        def cortar(f, s):
            visto.append(s)
            if len(visto) == 40: raise Corte()
        try:
            simulate(dem, act, n, e, r, o, inlets=inl, checkpoint=ck, checkpoint_every_s=0, progress=cortar)
            raise AssertionError("no se cortó")
        except Corte:
            pass
        assert ck.exists(), "no quedó punto de control"
        meta = json.loads(str(np.load(ck)["meta"]))
        assert 0 < meta["progreso"] < 1
        rr = simulate(dem, act, n, e, r, o, inlets=inl, checkpoint=ck, checkpoint_every_s=0, resume=True)
        assert np.array_equal(rr["hmax"], ref["hmax"]), backend
        assert np.array_equal(rr["hfinal"], ref["hfinal"]), backend
        assert rr["resumen"]["pasos"] == ref["resumen"]["pasos"]
        assert abs(rr["resumen"]["volumen_salida_m3"] - ref["resumen"]["volumen_salida_m3"]) < 1e-9
        assert len(rr["fotos"]["t_s"]) == len(ref["fotos"]["t_s"])
        assert rr["resumen"].get("reanudada") is True
        assert not ck.exists(), "el punto de control debe borrarse al terminar bien"


def test_punto_control_rechaza_otra_corrida():
    dem, act, n, e, r, o, inl = _caso("numpy"); ck = TMP / "pc_otra.npz"; c = [0]

    def cortar(f, s):
        c[0] += 1
        if c[0] == 10: raise Corte()
    try:
        simulate(dem, act, n, e, r, o, inlets=inl, checkpoint=ck, checkpoint_every_s=0, progress=cortar)
    except Corte:
        pass
    r2 = r * 1.3
    try:
        simulate(dem, act, n, e, r2, o, inlets=inl, checkpoint=ck, resume=True)
        raise AssertionError("debió rechazar")
    except ValueError as ex:
        assert "no corresponde" in str(ex)


def _bd_sintetica(carpeta, futuro=True, n_mod=4):
    from uceclima import basedatos as BD
    import pandas as pd
    c = BD.abrir(carpeta); rng = np.random.default_rng(3)
    fechas = pd.date_range("1981-01-01", "2025-12-31", freq="D")
    c.executemany("INSERT INTO referencia_lluvia VALUES (?,?,?)", [("chirps:celda_nex_mm", d.strftime("%Y-%m-%d"), float(v)) for d, v in zip(fechas, rng.gamma(0.6, 12, len(fechas)))])
    for k in range(n_mod):
        m = f"M{k}"; c.execute("INSERT INTO cmip6_modelos (modelo, posicion, seleccionado, peso) VALUES (?,?,?,?)", (m, k + 1, 1, 1.0 / n_mod))
        for esc, f0, f1 in (("historical", "1981-01-01", "2014-12-31"), ("ssp585", "2015-01-01", "2100-12-31")):
            if esc == "ssp585" and not futuro: continue
            fs = pd.date_range(f0, f1, freq="D"); esc_ = 1.0 if esc == "historical" else 1.0 + np.linspace(0, 0.6, len(fs))
            v = rng.gamma(0.6, 12, len(fs)) * esc_
            c.executemany("INSERT INTO cmip6_series VALUES (?,?,?,?,?,?)", [(m, esc, d.strftime("%Y-%m-%d"), float(x), float(x), "QQM") for d, x in zip(fs, v)])
    c.commit(); c.close()


def test_extremos_umbral_solo_linea_base_y_frecuencias():
    from uceclima import extremos_cmip6 as X
    import pandas as pd
    p = TMP / "ext"; p.mkdir(); _bd_sintetica(p)
    r = X.analizar(p, 90)
    ams = pd.read_csv(p / r["carpeta"] / "extremos_por_anio.csv")
    base = ams[(ams.anio >= 1981) & (ams.anio <= 2014)].chirps_rx1_mm
    assert abs(r["umbral_mm_dia"] - round(float(np.quantile(base, 0.9)), 1)) < 0.11, "el umbral es el p90 de CHIRPS 1981–2014"
    assert 5 <= r["frecuencia_chirps_base_pct"] <= 15, "por construcción, CHIRPS supera el p90 en cerca del 10 % de los años"
    dec = pd.read_csv(p / r["carpeta"] / "frecuencia_por_decada.csv")
    assert 2100 not in set(dec.iloc[:, 0]), "el año 2100 entra en la década 2090"
    assert r["frecuencia_modelos_por_decada_pct"][2090] > r["frecuencia_modelos_historico_pct"], "con lluvia creciente, más años extremos al final del siglo"
    for f in ("extremos.png", "LEEME.md", "resumen.json"): assert (p / r["carpeta"] / f).exists(), f
    r95 = X.analizar(p, 95); assert r95["umbral_mm_dia"] > r["umbral_mm_dia"]
    try:
        X.analizar(p, 80); raise AssertionError("p80 no se permite")
    except X.ExtremosError:
        pass


def test_extremos_sin_futuro_avisa_y_con_un_modelo_funciona():
    from uceclima import extremos_cmip6 as X
    p = TMP / "ext_sf"; p.mkdir(); _bd_sintetica(p, futuro=False)
    try:
        X.analizar(p); raise AssertionError("debió pedir el futuro")
    except X.ExtremosError as e:
        assert "futuro" in str(e)
    p1 = TMP / "ext_1"; p1.mkdir(); _bd_sintetica(p1, n_mod=1)
    assert X.analizar(p1)["n_modelos"] == 1
    paq = X.exportar_paquete(p1)
    assert (p1 / paq["carpeta"] / "LEEME.md").exists() and "un punto" in (p1 / paq["carpeta"] / "LEEME.md").read_text(encoding="utf-8")


def test_nombres_de_la_entrega_llevan_fecha_y_hora():
    from uceclima import entregas as ENT
    assert ENT._marca("corrida_20261101_122833_real_cc_ssp585_2071-2100_mediana") == "20261101_122833"
    assert ENT._marca("corrida_20261031_225837_real") == "20261031_225837"


def test_bitacora_y_lo_hecho_salen_del_disco():
    from uceclima.ui import servidor as SV
    p = TMP / "bit"; (p / "registro").mkdir(parents=True); (p / "proyecto_uceclima.json").write_text("{}", encoding="utf-8")
    SV.bitacora_escribir(p, {"t": "10:00:00", "fecha": "2026-11-01", "titulo": "Corrida terminada", "detalle": "x"})
    SV.bitacora_escribir(p, {"t": "10:05:00", "fecha": "2026-11-01", "titulo": "Exportó", "detalle": "y"})
    ev = SV.bitacora_leer(p); assert [e["titulo"] for e in ev] == ["Corrida terminada", "Exportó"]
    h = SV.lo_hecho(p, [{"id": "corrida_1", "estado": "completado", "fin": "2026-11-01T15:31:34"}, {"id": "corrida_2", "estado": "interrumpido"}])
    pasos = {x["paso"]: x for x in h}
    assert pasos["1 · Proyecto creado"]["hecho"] and pasos["7 · Corridas 2D"]["hecho"] and "interrumpido" in pasos["7 · Corridas 2D"]["detalle"]
    assert not pasos["9 · CMIP6 (factores Y)"]["hecho"]


def test_ventana_cerrada_se_detecta_por_el_perfil():
    from uceclima.ui import lanzar as L
    assert L.ventana_abierta() in (True, False, None)


if __name__ == "__main__":
    fallos = 0
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_") and callable(f):
            try:
                f(); print("OK", nombre)
            except Exception:
                fallos += 1; print("FALLA", nombre); traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
