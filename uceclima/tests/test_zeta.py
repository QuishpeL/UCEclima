# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Zeta 8.0.0 · pruebas de Z1 (cobertura CHIRPS), Z2 (sesión de Earth Engine), Z3 (proyecto desde shape + IDF propia), Z4 (productos ordenados),
Z5 (papers: reescalado mes-año, razón de varianza, N efectivo, ToE con ruido de estación) y Z6 (λ hasta 0,6). Sin red y sin corridas.
Ejecutar: python -m uceclima.tests.test_zeta  (desde UCEclima)"""
import json, shutil, sys, tempfile, threading, traceback, urllib.request, urllib.error
from pathlib import Path
import numpy as np
import pandas as pd
from uceclima import descargas as D, gee_chirps as G, productos as PROD, papers as PAP, escenarios_idf as ESC
from uceclima.ui import servidor as SV, sitio_api

TMP = Path(tempfile.mkdtemp(prefix="uceclima_zeta_"))
SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{SV.ESTADO.puerto}"
H = {"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token}


def post(r, c=None):
    q = urllib.request.Request(B + r, data=json.dumps(c or {}).encode(), method="POST", headers=H)
    try:
        with urllib.request.urlopen(q, timeout=120) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())


def get(r):
    with urllib.request.urlopen(urllib.request.Request(B + r, headers=H), timeout=120) as x: return json.loads(x.read())


def _shape(nombre, x0=743000, y0=4283000, lado=4000, epsg=32630, prj=True):
    import geopandas as gpd
    from shapely.geometry import Polygon
    p = Polygon([(x0, y0), (x0 + lado, y0), (x0 + lado, y0 + lado * 0.6), (x0 + lado * 0.3, y0 + lado), (x0, y0 + lado)])
    f = TMP / "shapes" / nombre; f.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame({"id": [1]}, geometry=[p], crs=f"EPSG:{epsg}").to_file(f)
    if not prj:
        f.with_suffix(".prj").unlink()
    return f


def test_z1_cobertura_chirps_mundial():
    assert D.punto_admitido(-78.6, -2.6) and D.punto_admitido(-0.2, 38.68) and D.punto_admitido(36.8, -1.3) and D.punto_admitido(100.5, 13.7)
    assert not D.punto_admitido(10, 60) and not D.punto_admitido(-68, -55) and not D.punto_admitido(200, 0)
    assert D.utm_epsg(-0.2, 38.68) == 32630 and D.utm_epsg(-78.6, -2.6) == 32717
    try:
        sitio_api.crear("Fuera de CHIRPS", 10, 60, base=TMP); raise AssertionError("debió rechazar")
    except D.DescargaError as e:
        assert "cobertura de CHIRPS" in str(e)


def test_z2_sesion_earth_engine_reutilizada():
    class FakeEE:
        __version__ = "fake"; n = 0
        class data:
            @staticmethod
            def setDeadline(ms): pass
        @classmethod
        def Initialize(cls, project=None): cls.n += 1
    G.olvidar_sesion()
    e1, ee1 = G.iniciar("proyecto-de-prueba-1", ee_module=FakeEE)
    assert e1["autenticado"] and FakeEE.n == 1 and G._SESION["ee"] is None              # con un módulo inyectado (pruebas) no se guarda la sesión
    G._SESION.update({"proyecto": "proyecto-de-prueba-1", "t": __import__("time").time(), "estado": e1, "ee": FakeEE})
    e2, ee2 = G.iniciar("proyecto-de-prueba-1")
    assert e2.get("reutilizada") and ee2 is FakeEE and FakeEE.n == 1                    # reutiliza: no vuelve a inicializar
    G.olvidar_sesion(); assert G._SESION["ee"] is None


def test_z3_proyecto_desde_shape_en_espana():
    shp = _shape("zona_guadalest.shp")
    z = sitio_api.zona_desde_shape(shp)
    assert 35 < z["lat"] < 44.5 and -1 < z["lon"] < 0.5 and abs(z["area_km2"] - 13.6) < 0.2, z
    c = sitio_api.crear("Zona desde shape", "", "", base=TMP / "proy", shape=str(shp))
    pr = json.loads((c / "proyecto_uceclima.json").read_text(encoding="utf-8")); cfg = json.loads((c / "config_climanet.json").read_text(encoding="utf-8"))
    assert pr["crs"] == "EPSG:32630" and "zona_estudio" in pr["procedencia"] and (c / "zona_estudio" / "zona_guadalest.prj").exists()
    assert "idf_inamhi" not in cfg and any("IDF propia" in n for n in pr["procedencia"]["notas"])      # fuera de Ecuador no se propone la IDF del INAMHI
    c2 = sitio_api.crear("Mazar zeta", -78.645, -2.585, base=TMP / "proy")
    assert "idf_inamhi" in json.loads((c2 / "config_climanet.json").read_text(encoding="utf-8"))


def test_z3_shape_sin_prj_no_se_adivina():
    shp = _shape("sin_prj.shp", prj=False)
    try:
        sitio_api.zona_desde_shape(shp); raise AssertionError("debió pedir el CRS")
    except D.DescargaError as e:
        assert "no lo adivino" in str(e)
    assert sitio_api.zona_desde_shape(shp, "EPSG:32630")["area_km2"] > 10


def test_z3_api_crear_desde_shape_registra_cuenca_y_productos():
    shp = _shape("zona_api.shp", x0=744000)
    c, j = post("/api/proyecto/crear", {"nombre": "Zeta API shape", "shape": str(shp), "carpeta_base": str(TMP / "proyapi"), "incluir_memoria": False})
    assert c == 200, j
    z = j["zona_estudio"]; assert z and z.get("carpeta") and abs(z["area_cuenca_km2"] - 13.6) < 0.2, z
    car = Path(j["carpeta"]); PROD.generar(car, None)
    assert (car / "productos" / "index.html").exists() and (car / "productos" / "01_proyecto" / "informe.html").exists()
    assert any((car / "productos" / "06_cuenca" / "shapes").glob("*.shp")) or any((car / "productos" / "06_cuenca" / "shapes").glob("*.gpkg"))


def _idf_csv(f, crece=True):
    TR, DUR = [2, 10, 25, 50, 100], [5, 15, 30, 60, 120, 360, 1440]
    t = pd.DataFrame([[ (100 + 20 * k) * (d / 60) ** -0.6 for d in DUR] for k, _ in enumerate(TR)], index=TR, columns=DUR)
    if not crece:
        t.iloc[0, 0] = 1e4
    t.index.name = "Tr"; t.to_csv(f); return f


def test_z3_idf_propia_valida_y_escala_cmip6():
    c = sitio_api.crear("IDF propia zeta", -0.2, 38.68, base=TMP / "idf")
    try:
        ESC.registrar_idf_propia(c, _idf_csv(TMP / "mala.csv", crece=False), "prueba"); raise AssertionError("debió rechazar la IDF no monótona")
    except ESC.EscenarioError:
        pass
    try:
        ESC.registrar_idf_propia(c, _idf_csv(TMP / "buena.csv"), "   "); raise AssertionError("debió exigir la fuente")
    except ESC.EscenarioError:
        pass
    info = ESC.registrar_idf_propia(c, TMP / "buena.csv", "Norma 5.2-IC (prueba)", "IDF de prueba")
    cfg = json.loads((c / "config_climanet.json").read_text(encoding="utf-8"))
    assert Path(cfg["idf_csv"]).exists() and "idf_inamhi" not in cfg and info["p24_tr100_mm"] > 0
    defs, base = ESC.definiciones(c, cfg)
    assert defs[0]["idf_propia"] and list(base.index) == [2, 10, 25, 50, 100]
    parche, d = ESC.preparar(c, cfg, "directa")
    assert parche["idf_csv"] and Path(parche["idf_csv"]).exists()


def test_z4_productos_no_sobrescriben():
    P = TMP / "prod_proy"; (P / "registro" / "idf").mkdir(parents=True)
    (P / "proyecto_uceclima.json").write_text(json.dumps({"nombre": "prueba"}), encoding="utf-8")
    f = P / "registro" / "idf" / "idf_propia_1.csv"; f.write_text("Tr,60\n100,50\n", encoding="utf-8")
    r = PROD.generar(P, {"nombre": "prueba"}); assert "04_idf" in r and (P / "productos" / "04_idf" / "csv").exists()
    PROD.generar(P, {"nombre": "prueba"}); n1 = len(list((P / "productos" / "04_idf" / "csv").iterdir()))
    f.write_text("Tr,60\n100,55\n", encoding="utf-8"); PROD.generar(P, {"nombre": "prueba"})
    n2 = len(list((P / "productos" / "04_idf" / "csv").iterdir()))
    assert n1 == 1 and n2 == 2, (n1, n2)                                            # mismo contenido: no duplica; contenido nuevo: versión con sello


def test_z5_reescalado_mes_anio_y_varianza():
    rng = np.random.default_rng(1); idx = pd.date_range("1981-01-01", "2014-12-31", freq="D")
    obs = pd.Series(rng.gamma(0.6, 8, len(idx)) * (rng.random(len(idx)) < 0.4), index=idx)
    sat = obs.groupby(obs.index.to_period("M")).transform(lambda x: x.sum() / len(x)) * rng.uniform(0.5, 1.5, len(idx))   # satélite «liso» con otro reparto
    rs, fac = PAP.reescalar_mes_anio(sat, obs)
    m1, m2 = rs.resample("MS").sum(), obs.resample("MS").sum()
    assert np.allclose(m1.values, m2.values, rtol=1e-9, atol=1e-6)                 # conserva los totales mensuales de la referencia
    v = PAP.razon_varianza(rs, obs); assert abs(v["PRCPTOT"]["razon"] - 1) < 1e-6 and v["PRCPTOT"]["lectura"].startswith("conserva")
    infl = PAP.razon_varianza(obs * (1 + 0.6 * (obs.index.year % 2)), obs); assert infl["PRCPTOT"]["razon"] > 1.2


def test_z5_n_efectivo_y_receta():
    rng = np.random.default_rng(2); x = rng.normal(size=60)
    iguales = pd.DataFrame({f"m{i}": x + 1e-3 * rng.normal(size=60) for i in range(10)})
    indep = pd.DataFrame({f"m{i}": rng.normal(size=600) for i in range(10)})
    assert PAP.n_efectivo(iguales)["n_eff"] < 1.1 and PAP.n_efectivo(indep)["n_eff"] > 8
    r = PAP.receta("emergencia", "densa"); assert "ESTACIÓN" in r["ruido_toe"] and len(r["citas_texto"]) == 3
    assert "crudo" in PAP.receta("balance", "dispersa")["correccion_satelite"]
    assert get("/api/papers/receta?uso=diseno&red=dispersa")["uso"] == "diseno"


def test_z5_toe_ruido_estacion_mas_tardio():
    rng = np.random.default_rng(3); anios = np.arange(1981, 2101)
    ser = {f"m{i}": pd.Series(500 + 1.5 * np.clip(anios - 2014, 0, None) + rng.normal(0, 20, len(anios)), index=anios) for i in range(6)}
    from uceclima import toe as T
    e_mod = T.toe_ensamble(ser, {}); e_est = PAP.toe_con_ruido(ser, {}, sigma_int=60.0)
    assert e_mod["toe"] is not None and (e_est["toe"] is None or e_est["toe"] > e_mod["toe"]), (e_mod["toe"], e_est["toe"])   # más ruido → emerge más tarde (P1)


def _proyecto_con_chirps(nombre, lon=36.8, lat=-1.3):
    """Proyecto en cualquier lugar (por defecto, Kenia) con un CHIRPS diario sintético de 1981–2020 en datos_descargados/sitio_*/chirps/."""
    c = sitio_api.crear(nombre, lon, lat, base=TMP / "mundo")
    rng = np.random.default_rng(7); idx = pd.date_range("1981-01-01", "2020-12-31", freq="D")
    p = rng.gamma(0.5, 9, len(idx)) * (rng.random(len(idx)) < 0.35)
    d = c / "datos_descargados" / "sitio_20260101_000000" / "chirps"; d.mkdir(parents=True)
    pd.DataFrame({"fecha": idx.strftime("%Y-%m-%d"), "media_caja_mm": p, "celda_nex_mm": p}).to_csv(d / "chirps_diario.csv", index=False)
    return c


def test_zz_mundo_sin_estaciones_receta_chirps_por_defecto():
    c = _proyecto_con_chirps("Kenia sin estaciones")
    assert PAP.red_auto(c) == ("dispersa", 0)
    r = PAP.ejecutar(c)                                                                  # sin estación: CHIRPS por defecto
    assert r["red"] == "dispersa" and r["referencia"].startswith("CHIRPS") and "crudo" in r["receta"]["referencia_cmip6"]
    assert (c / r["carpeta"] / "informe.md").exists() and any("CHIRPS" in a for a in r["avisos"])
    try:
        PAP.ejecutar(sitio_api.crear("Sin nada", 100.5, 13.7, base=TMP / "mundo")); raise AssertionError("sin CHIRPS ni estación debe avisar")
    except ValueError as e:
        assert "CHIRPS" in str(e)


def test_zz_idf_desde_chirps_en_cualquier_lugar():
    c = _proyecto_con_chirps("Kenia IDF")
    info = ESC.idf_desde_chirps(c)
    cfg = json.loads((c / "config_climanet.json").read_text(encoding="utf-8"))
    t = pd.read_csv(Path(cfg["idf_csv"]), index_col=0); t.columns = t.columns.astype(int)
    assert "idf_inamhi" not in cfg and info["anios_chirps"] == 40 and "CHIRPS" in info["fuente"] and "probablemente baja" in info["advertencia"]
    assert (t.diff(axis=1).iloc[:, 1:] <= 1e-9).all().all() and (t.diff(axis=0).iloc[1:] >= -1e-9).all().all()
    assert abs(t.loc[100, 1440] * 24 - info["p24_tr100_mm"]) < 0.2 and t.loc[100, 60] > t.loc[100, 1440] * 5   # 1 h ≫ intensidad media de 24 h (Campos 0,30)
    c2, j = post("/api/proyecto/abrir", {"ruta": str(c)}); assert c2 == 200
    c3, j3 = post("/api/idf/desde_chirps", {}); assert c3 == 200 and j3["p24_tr100_mm"] > 0, j3


def test_zz_interfaz_logo_uce_abajo_autoria_y_doctorado():
    html = (Path(__file__).resolve().parents[1] / "ui" / "static" / "index.html").read_text(encoding="utf-8")
    assert html.index("pie-logos") > html.index("id=\"nav\"") and "logo_uce.png" in html and "Doctorado en Gestión Sustentable del Agua y Riego" in html and "UCEclima Lambda" in html
    assert "Autor: Diego Quishpe Landeta" in html and "Coautoras: Teresa Palacios y María Eugenia Ávila-Salem" in html
    js = (Path(__file__).resolve().parents[1] / "ui" / "static" / "idf.js").read_text(encoding="utf-8")
    assert "/api/idf/desde_chirps" in js and "/api/idf/propia" in js


def test_zz_modo_word_guardar_y_continuar():
    c = _proyecto_con_chirps("Modo Word")
    assert post("/api/proyecto/abrir", {"ruta": str(c)})[0] == 200
    c1, j1 = post("/api/proyecto/estado_ui", {"ruta": "idf", "campos": {"zIdfFte": "Norma 5.2-IC", "zIdfCsv": "C:\\x.csv", "clave_api": "NO"}})
    assert c1 == 200 and j1["ruta"] == "idf" and j1["campos"]["idf"]["zIdfFte"] == "Norma 5.2-IC" and "clave_api" not in j1["campos"]["idf"]   # nada de claves
    post("/api/proyecto/estado_ui", {"ruta": "cmip6"})
    g = get("/api/proyecto/estado_ui"); assert g["ruta"] == "cmip6" and g["campos"]["idf"]["zIdfCsv"] == "C:\\x.csv"                      # se fusiona, no se pierde
    c2, j2 = post("/api/proyecto/guardar_avance", {"ruta": "terreno", "campos": {"a": "1"}})
    assert c2 == 200 and j2["guardado"] and (c / "productos" / "index.html").exists() and get("/api/proyecto/estado_ui")["ultimo_guardado"] == j2["guardado"]
    viejo = SV.SESION
    try:                                                                                 # la sesión reabre el último proyecto al arrancar
        SV.SESION = TMP / "sesion_prueba.json"; SV.SESION.write_text(json.dumps({"proyecto": str(c)}), encoding="utf-8")
        SV.ESTADO.datos = None; assert SV._sesion_restaurar(SV.ESTADO) == str(c) and SV.ESTADO.datos["nombre"] == "Modo Word"
        SV.SESION.write_text(json.dumps({"proyecto": str(TMP / "no_existe")}), encoding="utf-8"); assert SV._sesion_restaurar(SV.ESTADO) is None
    finally:
        SV.SESION = viejo
    assert SV._es_temporal(c)                                                            # proyectos en carpetas temporales (pruebas) no pisan la sesión real


def test_zz_cmip6_hallazgos_mapa2d_y_visor():
    est = get("/api/estado"); ids = [m["id"] for m in est["modulos"]]
    assert "mapa2d" in ids and "maquetas" not in ids                                     # el mapa 2D tipo RAS reemplaza a las maquetas en el menú
    raiz = Path(__file__).resolve().parents[1] / "ui" / "static"
    html = (raiz / "index.html").read_text(encoding="utf-8"); assert "/static/mapa2d.js" in html
    js = (raiz / "mapa2d.js").read_text(encoding="utf-8"); assert "VISTAS.mapa2d" in js and "/api/visor/capa" in js and "Y − X" in js
    assert "papersCC" in (raiz / "visor.html").read_text(encoding="utf-8") and "/api/cmip6/papers" in (raiz / "cmip6.js").read_text(encoding="utf-8")
    c = _proyecto_con_chirps("Sin CMIP6"); post("/api/proyecto/abrir", {"ruta": str(c)})
    try:
        get("/api/cmip6/papers"); raise AssertionError("sin cálculo debe responder 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404
    c2, j2 = post("/api/cmip6/papers", {}); assert c2 == 400 and "CMIP6" in j2["error"]       # sin análisis CMIP6: aviso claro
    from uceclima.ui import servidor as _S
    assert "campo" in ids and "/static/campo.js" in html and "VISTAS.campo" in (raiz / "campo.js").read_text(encoding="utf-8")   # 31-oct: validación de campo en lugar de la maqueta hipsométrica
    assert not (raiz / "maqueta.js").exists() and not (raiz.parents[1] / "hipsometria.py").exists()


def _lluvia(n_anios, seed, escala=8.0, p_hum=0.32, ini="1981-01-01"):
    idx = pd.date_range(ini, periods=int(n_anios * 365.25), freq="D"); rng = np.random.default_rng(seed)
    f = 1.0 + 0.6 * np.cos((idx.month.values - 3) / 12 * 2 * np.pi)
    return pd.Series(np.where(rng.random(len(idx)) < p_hum * f, rng.gamma(0.8, escala * f, len(idx)), 0.0), index=idx)


def test_zz_cmip6_version_frontera_aparte_del_metodo_de_referencia():
    """La versión de frontera (papers) va en registro/cmip6_frontera: no cambia el análisis de referencia ni los escenarios que usan la IDF y el 2D."""
    from uceclima import cmip6_descarga as CD, cmip6_sesgo as SB
    c = _proyecto_con_chirps("Frontera", lon=-0.2, lat=38.6); CD.asumir_baseline(c)
    ch = _lluvia(40, 3)[:"2020-12-31"]
    pd.DataFrame({"fecha": ch.index.strftime("%Y-%m-%d"), "media_caja_mm": ch.values, "celda_nex_mm": ch.values}).to_csv(c / "datos_descargados" / "sitio_20260101_000000" / "chirps" / "chirps_diario.csv", index=False)
    est = c / "datos" / "estaciones"; est.mkdir(parents=True, exist_ok=True)
    for k in range(3):                                                                   # 3 estaciones → red «densa»
        o = ch * (1.25 + 0.05 * k) * (1 + 0.3 * np.sin(np.arange(len(ch)) / 365.25 * 2 * np.pi / 7))   # más lluvia y más variabilidad interanual que CHIRPS
        pd.DataFrame({"fecha": o.index.strftime("%Y-%m-%dT00:00:00Z"), "lluvia_mm": o.values}).to_csv(est / f"E{k}.csv", index=False)
    dh = c / "datos_descargados" / "cmip6_historico_20260101_000000"; df = c / "datos_descargados" / "cmip6_futuro_20260101_000001"; dh.mkdir(parents=True); df.mkdir(parents=True)
    idx = pd.date_range("1981-01-01", "2014-12-31")
    for k, (m, esc_) in enumerate({"M1": 8.5, "M2": 11.0, "M3": 14.0}.items()):
        s = _lluvia(34, 20 + k, escala=esc_)[: len(idx)]; s.index = idx[: len(s)]
        pd.DataFrame({"fecha": s.index.strftime("%Y-%m-%d"), "pr_mm": s.values}).to_csv(dh / f"{m}_historical.csv", index=False)
        fu = _lluvia(86, 40 + k, escala=esc_, ini="2015-01-01") * 1.3
        pd.DataFrame({"fecha": fu.index.strftime("%Y-%m-%d"), "pr_mm": fu.values}).to_csv(df / f"{m}_ssp585.csv", index=False)
    ref = SB.evaluar(c, "chirps:celda_nex_mm", 3); SB.factores(c, ref["carpeta"])          # método de referencia (Omega)
    antes = sorted((c / "registro" / "cmip6").glob("analisis_*")); fac_antes = (antes[-1] / "factores_cc.csv").read_bytes()
    from uceclima import escenarios_idf as ESC
    esc_antes = {e["id"]: e["factor_por_tr"] for e in ESC._escenarios_cmip6(c)}
    fr = PAP.frontera(c, "E0")                                                            # red densa + estación → CHIRPS reescalado mes-año (P2)
    assert fr["referencia"].startswith("papers:chirps_reescalado_E0") and fr["red"] == "densa" and fr["en_evaluacion"] and "en evaluación" in fr["nota"]
    assert (c / fr["carpeta"] / "frontera.json").exists() and fr["carpeta"].startswith("registro/cmip6_frontera/") and fr["factor_tr100"] and fr["toe_oficial"]
    assert sorted((c / "registro" / "cmip6").glob("analisis_*")) == antes and (antes[-1] / "factores_cc.csv").read_bytes() == fac_antes
    assert {e["id"]: e["factor_por_tr"] for e in ESC._escenarios_cmip6(c)} == esc_antes      # la IDF y el 2D siguen con el método de referencia
    rs = pd.read_csv(next((c / "datos" / "papers").glob("chirps_reescalado_E0_*.csv")), parse_dates=["fecha"]).set_index("fecha")["valor"]
    o0 = PAP._serie_estacion(c, "E0"); a, b_ = rs["1990-03"].sum(), o0["1990-03"].sum()
    assert abs(a - b_) < 1e-6 * max(1, b_)                                               # conserva el total mensual de la estación
    fr2 = PAP.frontera(c)                                                                 # sin estación → CHIRPS crudo
    assert fr2["referencia"] == "chirps:celda_nex_mm" and "crudo" in fr2["referencia_texto"]
    fr3 = PAP.frontera(c, "E1", red="dispersa"); assert fr3["referencia"] == "chirps:celda_nex_mm" and "P3" in fr3["referencia_texto"]   # red dispersa: anclar empeora (P3)
    assert post("/api/proyecto/abrir", {"ruta": str(c)})[0] == 200
    g = get("/api/cmip6/frontera"); f0 = g["filas"][0]
    assert f0["referencia_omega"] and f0["frontera"] and g["frontera"]["carpeta"] == fr3["carpeta"] and "no reemplaza" in g["nota"]
    js = (Path(__file__).resolve().parents[1] / "ui" / "static" / "cmip6.js").read_text(encoding="utf-8"); assert "/api/cmip6/frontera" in js and "en evaluación" in js
    try:
        PAP.frontera(sitio_api.crear("Sin CHIRPS", 10, 10, base=TMP / "mundo")); raise AssertionError("sin CHIRPS debe avisar")
    except ValueError as e:
        assert "CHIRPS" in str(e)


def test_z2_gee_llave_rapida_proyecto_propio_y_plazo_duro():
    """El ID que escribe la persona manda sobre variables de entorno y candidatos; ninguna verificación cuelga la interfaz más que el plazo."""
    import os, time
    from uceclima import gee_conexion as GC
    viejo_cfg, viejo_cfg2, viejo_v, viejo_cred = GC.CONFIG_USUARIO, G.CONFIG_USUARIO, GC._verificar, GC.credenciales_existen
    os.environ["EARTHENGINE_PROJECT"] = "proyecto-del-entorno"
    try:
        GC.CONFIG_USUARIO = G.CONFIG_USUARIO = TMP / "gee_cfg" / "config.json"
        assert GC.proyecto() == "proyecto-del-entorno" and G._proyecto() == "proyecto-del-entorno"      # sin ID escrito: el del entorno
        GC.guardar_proyecto("teresa-gee-123")
        assert GC.proyecto() == "teresa-gee-123" and G._proyecto() == "teresa-gee-123"                  # escrito por la persona: manda
        probados = []
        GC.credenciales_existen = lambda: True
        GC._verificar = lambda pid=None: (probados.append(pid), GC.estado())[1]
        GC.conectar(); assert probados == ["teresa-gee-123"]                                           # solo SU proyecto, sin recorrer candidatos
        GC._verificar = lambda pid=None: time.sleep(30)                                               # Earth Engine colgado
        t0 = time.time(); e = GC.verificar("teresa-gee-123", plazo=1.5); dt = time.time() - t0
        assert dt < 3 and e["verificacion"]["ok"] is False and "no respondió" in e["verificacion"]["error"]
        t0 = time.time(); GC.verificar("teresa-gee-123", plazo=1.0); assert time.time() - t0 < 2     # una segunda espera no lanza otra conexión ni se cuelga
    finally:
        GC.CONFIG_USUARIO, G.CONFIG_USUARIO, GC._verificar, GC.credenciales_existen = viejo_cfg, viejo_cfg2, viejo_v, viejo_cred
        os.environ.pop("EARTHENGINE_PROJECT", None); GC._VERIF.update(ok=None, error=None, ayuda=None, detalle=None)
    js = (Path(__file__).resolve().parents[1] / "ui" / "static" / "modulos.js").read_text(encoding="utf-8")
    assert "1 · ID de TU proyecto" in js and js.index('"gProy"') < js.index('id="gConectar"')                       # el ID va primero, a la vista
    assert "GEEC.precalentar()" in (Path(__file__).resolve().parents[1] / "ui" / "servidor.py").read_text(encoding="utf-8")


def test_z6_lambda_hasta_06():
    src = (Path(__file__).resolve().parents[2] / "climanet" / "climanet" / "pipeline.py").read_text(encoding="utf-8")
    assert "0.0 < ia_ratio <= 0.6" in src
    from climanet.hydrology import excess_scs
    S = 25400 / 72.94 - 254; lam = 51.8 / S
    assert abs(lam - 0.5497) < 1e-3 and float(excess_scs(100.0, 72.94, lam)) > 0           # calibración de T. Palacios (Ia 51,8 mm) usable tal cual


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=5, file=sys.stdout)
    SRV.shutdown(); shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
