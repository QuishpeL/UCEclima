# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Epsilon · E1 MDT de alta resolución (relleno declarado de depresiones, hidrograma de entrada, sección y hidrograma 2D en la salida,
velocidades anómalas, guía de MDT propio) y gráficas principales de CMIP6. Respuesta conocida, sin red.
Ejecutar: python -m uceclima.tests.test_epsilon  (desde UCEclima)"""
import json, shutil, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd

import uceclima  # noqa: F401  (pone climanet en el path)
from climanet import pipeline as PL
from uceclima import matematica_propia as MP, terreno_import as TI, configuracion as CFG, cmip6_figuras as CF
from uceclima.ui import demo
from affine import Affine

TMP = Path(tempfile.mkdtemp(prefix="uceclima_epsilon_"))


def test_e12_relleno_respeta_umbral_y_cuenta_volumen():
    z = np.full((20, 20), 10.0); z[0, :] = z[-1, :] = z[:, 0] = z[:, -1] = 10.0
    z[4:7, 4:7] = 9.5                                                      # depresión somera 0,5 m (artefacto)
    z[12:16, 12:16] = 7.0                                                  # depresión profunda 3 m (laguna)
    n1, i1, d1 = PL.rellenar_depresiones(z, 100.0, None)
    assert i1["depresiones_encontradas"] == 2 and abs(i1["volumen_almacenamiento_quitado_m3"] - (9 * 0.5 + 16 * 3) * 100) < 1e-6
    n2, i2, d2 = PL.rellenar_depresiones(z, 100.0, 1.0)
    assert i2["depresiones_conservadas"] == 1 and abs(i2["volumen_almacenamiento_quitado_m3"] - 9 * 0.5 * 100) < 1e-6
    assert np.allclose(n2[12:16, 12:16], 7.0) and np.allclose(n2[4:7, 4:7], 10.0)


def test_e11_hidrograma_entrada_valida_y_ubica():
    t, q = PL.leer_hidrograma_entrada({"nombre": "a", "t_s": [0, 600, 1200], "q_m3s": [0, 5, 0]})
    assert q.max() == 5
    try:
        PL.leer_hidrograma_entrada({"nombre": "b", "t_s": [0, 600], "q_m3s": [0, 5]}); assert False, "debe exigir que termine en 0"
    except ValueError as e:
        assert "no se inventa" in str(e)
    meta = {"transform": Affine(10, 0, 500000, 0, -10, 9760600)}; act = np.ones((60, 60), bool); act[30, 30] = False
    assert PL._celda_de_xy((500305, 9760295), meta, act) in [(29, 30), (31, 30), (30, 29), (30, 31)]


def test_e14_seccion_salida_sigue_la_pendiente():
    z = np.add.outer(np.zeros(9), -np.arange(9.0))                          # baja hacia columnas crecientes (flujo +x)
    ax, idx, (lo, hi), signo = PL.seccion_salida(z, np.ones_like(z, bool), (4, 4), 2)
    assert ax == "x" and idx == 5 and (lo, hi) == (2, 7) and signo == 1.0
    ax, idx, _, signo = PL.seccion_salida(z.T, np.ones_like(z, bool), (4, 4), 2)
    assert ax == "y" and signo == 1.0
    z2 = np.add.outer(-np.arange(12.0) * 10, np.zeros(12)); z2[6, 7] = z2[6, 6] - 0.5                                # río al sur con un escalón lateral engañoso en la celda vecina
    ax, idx, (lo, hi), signo = PL.seccion_salida(z2, np.ones_like(z2, bool), (6, 6), 2)
    assert ax == "y" and signo == 1.0, (ax, signo)                                                            # sigue el recorrido de varias celdas, no el vecino lateral
    zb = np.tile(np.linspace(0, 10, 40), (30, 1)); zb[:, 3] += 0.0                                                # G25 (Milagro): salida a 3 celdas del borde oeste con semiancho 5 → sección vertical, flujo hacia el oeste
    ax, idx, (lo, hi), signo = PL.seccion_salida(zb, np.ones_like(zb, bool), (15, 3), 5)
    assert ax == "x" and idx == 3 and signo == -1.0, (ax, idx, signo)


def test_e14_hu_scs_igual_que_hidro_y_conserva_volumen():
    edges = np.arange(0, 3 * 3600 + 1, 300.0); blocks = np.r_[np.full(12, 2.0), np.full(12, 4.0), np.full(12, 1.0)]
    t, q = PL.hidrograma_hu_scs(edges, blocks, 55, 0.05, 6.0, 484, 99.074)
    pe = MP.perdidas_scs(np.cumsum(blocks), 55, lam=0.05)["exceso_inc_mm"]; u = MP.uh_scs(99.074, 6.0, 300 / 3600, 484)["u_m3s_mm"]
    assert np.allclose(q, np.convolve(pe, u), rtol=1e-6)                                       # misma formulación que el módulo hidro
    assert abs(q.sum() * 300 - pe.sum() / 1000 * 99.074e6) < 1e-3 * pe.sum() / 1000 * 99.074e6


def test_e13_velocidades_anomalas_se_marcan_no_se_corrigen():
    v = np.full((5, 5), 1.0); h = np.full((5, 5), 0.5); v[2, 3] = 30.0; h[2, 3] = 0.06
    info, m = PL.velocidades_anomalas(v, h, np.ones((5, 5), bool), {"transform": Affine(10, 0, 0, 0, -10, 50)}, 10.0)
    assert info["celdas_anomalas"] == 1 and info["velocidad_max_ms"] == 30.0 and info["velocidad_max_robusta_ms"] == 1.0 and m.sum() == 1
    assert info["celda_max"]["fila"] == 2 and v[2, 3] == 30.0


def test_e1_corrida_completa_con_salida_entrada_y_relleno():
    c = demo.crear_sintetico(TMP / "sint"); cfg = json.loads((c / "config_climanet.json").read_text(encoding="utf-8"))
    cfg["dem"] = str(c / cfg["dem"]); cfg["out_dir"] = str(TMP / "res"); cfg["sim_horas"] = 3
    x0, x1, y0, y1 = cfg["aoi"]; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    import rasterio
    with rasterio.open(cfg["dem"]) as r_:
        z = r_.read(1)
    cfg["salida_xy"] = [cx, cy]; cfg["hidro_comparar"] = {"CN": 80, "lambda": 0.2, "lag_h": 0.5, "PRF": 484, "area_km2": 0.36}
    csv = TMP / "entrada.csv"; pd.DataFrame({"t_s": [0, 1800, 3600], "Q_m3s": [0, 2.0, 0]}).to_csv(csv, index=False)
    cfg["entradas_hidrograma"] = [{"nombre": "aguas_arriba", "csv": str(csv), "xy": [x0 + 105, y1 - 105]}]
    cfg["fill_sinks"] = True; cfg["fill_sinks_max_m"] = 0.5; cfg["exigir_entrada_en_cauce"] = False
    s = PL.run(cfg, progress=lambda *a: None)
    out = Path(cfg["out_dir"]) / "Tr100_diseno_idf_historica"
    hs = s["hidrograma_salida"]; d = pd.read_csv(out / "hidrograma_salida_2d.csv")
    assert {"t_s", "Q_2d_m3s", "Q_hidro_m3s"} <= set(d.columns) and hs["hidro_pico_m3s"] > 0 and (out / "hidrograma_salida.png").exists()
    assert abs(s["entradas"]["aguas_arriba"]["volumen_integrado_m3"] - 3600.0) < 1e-6 and s["entradas_hidrograma"][0]["volumen_m3"] == 3600.0
    assert "relleno_depresiones" in s and (out / "relleno_depresiones_m.tif").exists() and "velocidad_anomala" in s and (out / "v_anomala.tif").exists()
    assert s["error_balance_max_pct"] <= 0.01


def test_e15_sugerencia_mdt_fino_y_resolucion_minima():
    g = TI.sugerencia({"res_m": 1.0}, "DSM")
    o1 = next(o for o in g["opciones"] if o["celda_m"] == 1.0)
    assert abs(o1["area_max_km2"] - 0.25) < 1e-9 and any("subgrid" in r for r in g["recomendaciones"]) and "DSM" in g["avisos"][0]
    assert next(p for p in CFG.ESQUEMA["corrida"] if p["clave"] == "res")["min"] == 0.5
    claves = {p["clave"]: p for p in CFG.ESQUEMA["corrida"]}
    assert claves["cn_amc_2d"]["defecto"] == "ninguna" and claves["cn_2d_declarado"]["defecto"] == 0                     # nunca por defecto


def test_cmip6_toe_solo_modelo():
    a = pd.Series([0.0] * 40 + [5.0] * 60, index=range(2001, 2101))
    assert CF._toe_solo(a, 0.0, 1.0, desde=2015) == 2041
    assert CF._toe_solo(pd.Series([0.0, 5.0, 0.0, 5.0], index=[2020, 2021, 2022, 2023]), 0.0, 1.0) == 2023


def test_cmip6_figuras_en_proyecto_real_si_existe():
    p = Path(r"C:\Users\agdgq\Documents\UCEclima_proyectos\chalpi_h13_delta_validacionucec")
    if not (p / "registro" / "cmip6").exists():
        return                                                                  # en otra PC no hay datos reales: se omite
    r = CF.todas(p)
    assert not any("error" in v for v in r.values()), r
    assert r["bondad_qqm"]["rmse_ciclo_qqm_validado_mm"] < r["bondad_qqm"]["rmse_ciclo_crudo_mm"]


def test_rutas_http_de_las_graficas():
    import threading, urllib.request, urllib.error
    from uceclima.ui import servidor as SV
    srv = SV.crear_servidor(0); threading.Thread(target=srv.serve_forever, daemon=True).start()
    B = f"http://127.0.0.1:{SV.ESTADO.puerto}"; H = {"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token}
    def llamar(u, d=None):
        rq = urllib.request.Request(B + u, data=None if d is None else json.dumps(d).encode(), method="GET" if d is None else "POST", headers=H)
        try:
            with urllib.request.urlopen(rq, timeout=120) as x: return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    try:
        c = demo.crear_sintetico(TMP / "rutas"); assert llamar("/api/proyecto/abrir", {"ruta": str(c)})[0] == 200
        code, j = llamar("/api/cmip6/figuras", {}); assert code == 200 and set(j) == {"toe_cabeza", "bondad_qqm", "toe_indicadores", "toe_sn_grande"}, j
        code, j = llamar("/api/cmip6/figura.png?nombre=bondad_qqm"); assert code == 404 and "desconocida" not in j["error"], j
        code, j = llamar("/api/corrida/hidrograma.png?id=x"); assert code in (400, 404) and "desconocida" not in j["error"], j
    finally:
        srv.shutdown()


def test_validacion_contingencia_exacta():
    from uceclima import validacion_2d as VAL
    o = np.array([1, 1, 0, 0, 1], bool); s_ = np.array([1, 0, 1, 0, 1], bool)
    k = VAL.contingencia(o, s_, np.ones(5, bool))
    assert (k["aciertos"], k["fallos"], k["falsas_alarmas"]) == (2, 1, 1) and k["CSI"] == 0.5 and k["tasa_aciertos"] == round(2 / 3, 3)


def test_validacion_fuentes_3_y_4_contra_una_corrida():
    import rasterio, geopandas as gpd, shapely.geometry as sg
    from uceclima import validacion_2d as VAL
    car = TMP / "val"; sal = car / "resultados" / "corrida_x" / "salida" / "Tr100"; sal.mkdir(parents=True)
    h = np.zeros((10, 10), "float32"); h[2:6, 2:6] = 0.5                                          # 16 celdas mojadas
    T = rasterio.transform.from_origin(500000, 9760100, 10, 10)
    with rasterio.open(sal / "hmax.tif", "w", driver="GTiff", height=10, width=10, count=1, dtype="float32", crs="EPSG:32717", transform=T) as w:
        w.write(h, 1)
    poly = TMP / "mancha.gpkg"; gpd.GeoDataFrame({"a": [1]}, geometry=[sg.box(500020, 9760020, 500060, 9760080)], crs="EPSG:32717").to_file(poly)   # filas 2–7, columnas 2–5
    VAL.registrar_mancha_externa(car, poly, "prueba", "2020-01-01")
    pts = TMP / "marcas.csv"; pd.DataFrame({"x": [500035, 500095], "y": [9760065, 9760005], "calado_obs_m": [0.4, None], "mojado": [1, 0]}).to_csv(pts, index=False)
    VAL.registrar_puntos_campo(car, pts, "prueba campo")
    r = VAL.contrastar(car, "corrida_x")
    k = r["detalle"]["manchas_externas"][0]["contraste"]["h_ge_0.05m"]
    assert (k["aciertos"], k["fallos"], k["falsas_alarmas"]) == (16, 8, 0), k
    pc = r["detalle"]["puntos_campo"][0]
    assert pc["n_dentro"] == 2 and abs(pc["error_medio_m"] - 0.1) < 1e-6 and pc["acierto_mojado_seco_pct"] == 100.0
    assert [f["n"] for f in r["tabla"]] == [1, 2, 3, 4]


def test_contaminantes_masa_y_formulas():
    from uceclima import contaminantes as CT
    r = CT.escenario(100, 20, 1.0, 0.0005, 0.035, 20000, 0.5, nx=2000, ny=40, nt=3)
    f = np.array(r["C_mg_l"][-1]); masa = f.sum() * (20000 / 2000) * (20 / 40) * 1.0 * 1000 / 1e6
    assert abs(masa - 100) < 2, masa                                                          # se conserva la masa (sin decaimiento)
    h = CT.hidraulica(20, 1.0, 0.002, 0.035); U, us = h["U_ms"], h["u_estrella_ms"]
    assert abs(CT.coef_K("elder_1959", U, us, 20, 1.0) - 5.93 * us) < 1e-12 and abs(CT.coef_K("fischer_1975", U, us, 20, 1.0) - 0.011 * U ** 2 * 400 / us) < 1e-9
    r2 = CT.escenario(100, 20, 1.0, 0.0005, 0.035, 20000, 0.5, k_dia=50, nx=2000, ny=40, nt=3)
    assert abs(np.array(r2["C_mg_l"][-1]).sum() / f.sum() - np.exp(-50 * 1800 / 86400)) < 1e-6        # decaimiento de primer orden exacto
    assert all(x["doi"] for x in r["referencias"]) and len(r["referencias"]) == 7


def test_contaminantes_venas_y_cauce():
    from uceclima import contaminantes as CT
    v = CT.particulas(20, 1.0, 0.002, 0.035, 3000, 1.0, nt=10, N=600)
    assert v["N"] == 600 and len(v["x_m"]) == 10 and v["K_particulas_m2s"] > 0
    vr = np.array(v["v_rel"][0]); assert vr.max() > 1.2 and vr.min() < 0.8                                        # hay partículas rápidas y lentas (venas)
    from affine import Affine
    z = np.add.outer(np.arange(30.0)[::-1], np.zeros(30)) + np.abs(np.arange(30) - 15)[None, :] * 0.1                 # valle en la columna 15 que baja hacia filas crecientes
    cam = CT._camino_d8(z, Affine(10, 0, 0, 0, -10, 300), 2, 15, 150)
    assert all(c == 15 for r, c in cam) and cam[-1][0] > cam[0][0]


def test_mapa_muestreo_de_exposicion():
    from uceclima import mapa_referencias as MR
    from affine import Affine
    a = np.zeros((10, 10)); a[3, 4] = 0.8; T = Affine(10, 0, 0, 0, -10, 100)
    d = MR._muestrea(a, T, np.array([45.0, 5.0]), np.array([65.0, 95.0]))
    assert d[0] == 0.8 and d[1] == 0.0


def test_premodulo_lecturas_sinopticas_y_888():
    """G12/G13 (caso real Milagro): lecturas 07/13/19 h se agregan a diario y 888 en lluvia es «sin dato» (en caudal no)."""
    import pandas as pd
    from uceclima import premodulo as P
    f = pd.date_range("2000-01-01", periods=40, freq="D")
    filas = [(d + pd.Timedelta(hours=h), 1.0) for d in f for h in (7, 13, 19)]; filas[5] = (filas[5][0], 888.0)
    ruta = TMP / "M9999_sinoptica.csv"; ruta.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas, columns=["fecha", "PRECIPITACION SUM (mm) - 1 HORAS"]).to_csv(ruta, index=False)
    r = P.leer(str(ruta), guardar=False); assert r["estado"] == "ok", r
    x = P._a_diaria(pd.Series([a for a, _ in filas]), pd.Series([b for _, b in filas]), "lluvia")[0]
    assert x.notna().sum() == 39 and x.max() == 3.0 and pd.isna(x.iloc[1])        # día con un 888: 2 de 3 lecturas < 80 % → vacío
    q = P._a_diaria(pd.Series(f), pd.Series([888.0] * 40), "caudal")[0]; assert q.notna().all()


def test_cn_encuentra_suelo_de_descarga_de_sitio():
    """G14 (caso real Milagro): CN y Manning usan las capas de suelo que trajo la descarga «sitio» (sitio_*/suelo)."""
    from uceclima.parametros_gee import _ultimas_capas
    c = TMP / "proy_g14"; d = c / "datos_descargados" / "sitio_20261027_131542" / "suelo"; d.mkdir(parents=True, exist_ok=True)
    assert _ultimas_capas(c) is None
    for n in ("uso_suelo_worldcover.tif", "textura_suelo_openlandmap.tif"): (d / n).write_bytes(b"x")
    a, b = _ultimas_capas(c); assert a.parent == d and b.name == "textura_suelo_openlandmap.tif"


def test_evento_real_largo_y_entradas_hidrograma():
    """G15/G16/G17 (caso real Milagro): evento real horario > 12 h se declara (real_largo); la verificación suma la cola de los hidrogramas de entrada."""
    import pandas as pd
    from uceclima.ui import evento_api as EA
    assert EA.TOPE_SIM_REAL_H == 96.0 and EA.TOPE_SIM_H == 12.0
    f = TMP / "hid_g17.csv"; f.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"t_s": [0, 3600, 7200, 36000], "Q_m3s": [0, 5.0, 2.0, 0]}).to_csv(f, index=False)
    from climanet.pipeline import leer_hidrograma_entrada
    t, q = leer_hidrograma_entrada({"nombre": "x", "csv": str(f)}); assert t[-1] == 36000 and q.max() == 5.0
    src = (Path(EA.__file__).parent / "servidor.py").read_text(encoding="utf-8"); assert '"/api/corrida/entradas"' in src
    src = (Path(EA.__file__).parent / "proyecto.py").read_text(encoding="utf-8"); assert 'seg <= 1800' in src and 'lim_h = 96.0' in src and "entradas_hidrograma" in src and "cuencas_externas" in src


def test_evento_hora_local_y_amc_raster():
    """G18/G20 (caso real Milagro): la ventana local de Ecuador se pasa a UTC (+5 h) y el CN ráster se lleva a AMC I/III sin tocar agua ni impermeable."""
    import numpy as np
    from uceclima.ui import evento_api as EA
    c = TMP / "proy_g18"; d = c / "datos" / "estaciones"; d.mkdir(parents=True, exist_ok=True)
    (d / "EST1.qc.json").write_text(json.dumps({"estacion": {"zona_horaria_origen": "America/Guayaquil"}, "calidad": {}}), encoding="utf-8")
    u, tz = EA._a_utc(c, "EST1", "2026-10-25 22:00", "local"); assert u == "2026-10-26 03:00:00" and tz == "America/Guayaquil"
    assert EA._a_utc(c, "EST1", "2026-10-26 03:00", "utc") == "2026-10-26 03:00:00"
    src = (Path(EA.__file__).resolve().parents[2] / "climanet" / "climanet" / "pipeline.py").read_text(encoding="utf-8")
    assert 'cfg.get("cn_amc") in ("I", "III")' in src and "Evento " in src
    cn = np.array([76.6, 98.0, 100.0]); m = cn < 98
    i = np.where(m, cn / (2.281 - 0.01281 * cn), cn); assert abs(i[0] - 59.0) < 0.1 and i[1] == 98 and i[2] == 100


def test_borde_cerrado_junto_a_entrada():
    """G22 (caso real Milagro): con salida libre, una entrada a 1 celda del borde se pierde por ese borde; cerrando el borde junto a la entrada el agua entra al dominio.
    numpy y numba dan el mismo resultado; sin máscara el comportamiento anterior no cambia."""
    import numpy as np
    from climanet.hydraulics import simulate, Options
    ny, nx = 20, 30; z = np.tile(np.linspace(1.0, 0.0, nx)[::-1], (ny, 1)) * 0 + np.linspace(0.0, 0.3, nx)[None, :]   # sube hacia el este (la entrada está aguas arriba)
    act = np.ones((ny, nx), bool); n = np.full((ny, nx), 0.04); edges = np.array([0.0, 600.0]); ro = np.zeros((1, ny, nx))
    ent = [{"nombre": "E", "t": np.array([0.0, 1800.0, 3600.0]), "q": np.array([0.0, 20.0, 0.0]), "celdas": [[10, nx - 2]]}]
    lib_cerr = (np.ones(ny, bool), np.r_[np.ones(4, bool), np.zeros(13, bool), np.ones(3, bool)], np.ones(nx, bool), np.ones(nx, bool))
    out = {}
    for b in ("numpy", "numba"):
        for nom, lib in (("libre", None), ("cerrado", lib_cerr)):
            r = simulate(z, act, n, edges, ro, Options(30.0, 30.0, 3600.0, boundary="free_outflow", backend=b, bordes_libres=lib), inlets=[dict(e) for e in ent])
            out[(b, nom)] = r["hmax"][10, :nx // 2].max()
    assert out[("numpy", "cerrado")] > out[("numpy", "libre")] and abs(out[("numpy", "cerrado")] - out[("numba", "cerrado")]) < 1e-6 and abs(out[("numpy", "libre")] - out[("numba", "libre")]) < 1e-6, out


def test_omega_filtro_picos_y_rios_visor():
    """Omega O2/O3: el filtro declarado baja solo los picos (un «edificio» de 10 m) y no toca el resto; el visor recibe los ríos en coordenadas de celda."""
    import numpy as np, rasterio
    from rasterio.transform import from_origin
    from uceclima.terreno_import import filtrar_picos
    z = np.tile(np.linspace(10, 12, 40), (40, 1)).astype("float32"); z[20, 20] += 10.0
    f = TMP / "dsm_picos.tif"; f.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(f, "w", driver="GTiff", height=40, width=40, count=1, dtype="float32", crs="EPSG:32717", transform=from_origin(650000, 9770000, 30, 30), nodata=-9999) as d: d.write(z, 1)
    inf = filtrar_picos(f, 3.0, 5)
    with rasterio.open(inf["salida"]) as s: b = s.read(1)
    assert inf["celdas_corregidas"] == 1 and abs(b[20, 20] - z[20, 21]) < 0.2 and np.allclose(np.delete(b.ravel(), 20 * 40 + 20), np.delete(z.ravel(), 20 * 40 + 20))
    try:
        filtrar_picos(f, 3.0, 5); assert False, "no debe sobrescribir"
    except Exception as e:
        assert "no se sobrescribe" in str(e)
    import geopandas as gpd
    from shapely.geometry import LineString
    from types import SimpleNamespace
    from uceclima.ui.visor_api import _rios
    c = TMP / "proy_rios"; d_ = c / "datos_descargados" / "rios_1"; d_.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame({"UPLAND_SKM": [100.0]}, geometry=[LineString([(650000, 9769400), (651200, 9769400)])], crs=32717).to_file(d_ / "rios_hydrosheds.gpkg", driver="GPKG")
    r = _rios(SimpleNamespace(carpeta=c), from_origin(650000, 9770000, 30, 30), 40, 40, "EPSG:32717")
    assert len(r) == 1 and abs(r[0]["ij"][0][1] - 19.5) < 0.01 and r[0]["ij"][-1][0] > 38


def test_omega_informe_html_autocontenido():
    """Omega O6: el informe se arma aunque falten insumos (lo dice) y no trae dependencias externas."""
    from uceclima import informe_html as IH
    c = TMP / "proy_informe"; (c / "datos" / "estaciones").mkdir(parents=True, exist_ok=True)
    (c / "config_climanet.json").write_text(json.dumps({"res": 30, "aoi": [0, 3000, 0, 3000], "dem": "x/mdt_fabdem_6km.tif"}), encoding="utf-8")
    f = IH.construir(c, {"nombre": "Prueba", "config_climanet": "config_climanet.json", "tipo_terreno": "MDT", "datum_vertical": "EGM2008"}, [], c)
    h = f.read_text(encoding="utf-8")
    assert "Informe de inundación · Prueba" in h and "FABDEM" in h and "9,0 km²" in h and "Sin gráficas CMIP6" in h and "http" not in h.split("<main>")[0]


def test_omega_quemar_rios_profundidad_declarada():
    """Omega O7: el cauce queda `profundidad` bajo el mínimo 3×3 de su entorno; fuera de la línea no cambia; no sobrescribe."""
    import numpy as np, rasterio, geopandas as gpd
    from rasterio.transform import from_origin
    from shapely.geometry import LineString
    from uceclima.terreno_import import quemar_rios
    z = np.tile(np.linspace(10, 11, 30), (30, 1)).astype("float32")
    f = TMP / "mdt_quema.tif"; f.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(f, "w", driver="GTiff", height=30, width=30, count=1, dtype="float32", crs="EPSG:32717", transform=from_origin(650000, 9770000, 30, 30), nodata=-9999) as d: d.write(z, 1)
    g = TMP / "rio_quema.gpkg"; gpd.GeoDataFrame({"UPLAND_SKM": [50.0]}, geometry=[LineString([(650000, 9769535), (650900, 9769535)])], crs=32717).to_file(g, driver="GPKG")
    inf = quemar_rios(f, g, 2.0, 1)
    with rasterio.open(inf["salida"]) as s: b = s.read(1)
    assert inf["celdas_quemadas"] >= 30 and b[15, 10] <= z[14:17, 9:12].min() - 2.0 + 1e-4 and np.allclose(b[3], z[3])
    assert np.all(np.diff(b[15, :]) < 0)                                                       # O7b: el cauce baja siempre en el sentido de la línea
    try:
        quemar_rios(f, g, 2.0, 1); assert False
    except Exception as e:
        assert "no se sobrescribe" in str(e)


def test_qqm_estacion_seca_costa_con_ventana_estacional():
    """G26 (Milagro): con un agosto casi seco, el QQM mensual usa una ventana estacional para los cuantiles húmedos en vez de descartar el modelo."""
    import numpy as np, pandas as pd
    from uceclima.cmip6_sesgo import QQM
    i = pd.date_range("1981-01-01", "2014-12-31", freq="D"); rng = np.random.default_rng(1)
    llueve = np.where(i.month.isin([7, 8, 9]), 0.012, 0.35)
    o = pd.Series(np.where(rng.random(len(i)) < llueve, rng.gamma(0.8, 12, len(i)), 0.0), index=i)
    g = pd.Series(np.where(rng.random(len(i)) < llueve * 1.2, rng.gamma(0.8, 9, len(i)), 0.0), index=i)
    q = QQM().fit(o[o.index.year % 2 == 1], g[g.index.year % 2 == 1])
    assert q.m[8]["ventana"] >= 1 and 8 in q.avisos and q.m[2]["ventana"] == 0
    y = q.transform(g); assert y.notna().all() and (y >= 0).all()


def test_aoi_alineada_a_la_malla():
    """G27 (Milagro): el área se alinea a la malla del ráster (origen 649 770, 30 m) y su lado es múltiplo de la celda."""
    from uceclima.terreno_import import alinear_aoi, _desalineada
    e = {"x0": 649770.0, "x1": 661800.0, "y0": 9760080.0, "y1": 9772110.0}
    a = alinear_aoi([650784.0, 660784.0, 9761091.3, 9771091.3], e, 30.0, 30.0)
    assert a == [650790.0, 660780.0, 9761100.0, 9771090.0], a
    assert _desalineada([650784.0, 660784.0, 9761091.3, 9771091.3], e, 30.0, 30.0) and not _desalineada(a, e, 30.0, 30.0)


def test_omega_figuras_en_ingles_solo_para_papers():
    """Omega O8: el traductor deja la figura en inglés (frases largas antes que palabras sueltas, punto decimal) y avisa de restos en español."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from uceclima.figuras_idioma import traducir, restos
    fig, ax = plt.subplots(); ax.set_title("Lluvia máxima en 24 h · Rx1day (mm)\nla señal no sale de ±1σ de forma permanente"); ax.set_xlabel("año")
    ax.plot([0, 1], [0, 1], label="Intensidad media en días de lluvia (mm/día)"); ax.legend(); ax.text(0, 0, "calado p99 1,47 m")
    traducir(fig); txt = [t.get_text() for t in fig.findobj(matplotlib.text.Text) if t.get_text()]
    assert "Maximum 24-h rainfall · Rx1day (mm)\nthe signal does not leave ±1σ permanently" in txt and "year" in txt and "p99 depth 1.47 m" in txt
    assert "Simple daily intensity index, SDII (mm/day)" in txt and not restos(fig); plt.close(fig)


def test_omega_rios_merge_sigue_el_talweg():
    """Omega O9: con una guía desplazada 4 celdas del talweg real de un valle, el río merge vuelve al talweg (máxima acumulación del MDT)."""
    import numpy as np, rasterio, geopandas as gpd
    from rasterio.transform import from_origin
    from shapely.geometry import LineString
    from uceclima.terreno_import import rios_merge
    ny, nx = 40, 60; yy, xx = np.mgrid[0:ny, 0:nx]
    z = (10 + 0.05 * (nx - xx) + 0.3 * np.abs(yy - 20)).astype("float32")           # valle con talweg en la fila 20, baja hacia el este
    f = TMP / "mdt_merge.tif"; f.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(f, "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32", crs="EPSG:32717", transform=from_origin(650000, 9770000, 30, 30), nodata=-9999) as d: d.write(z, 1)
    g = TMP / "guia_merge.gpkg"; yg = 9770000 - 24.5 * 30                                  # guía en la fila 24 (120 m al sur del talweg)
    gpd.GeoDataFrame({"UPLAND_SKM": [50.0], "REACH_ID": [1]}, geometry=[LineString([(650000 + 5 * 30, yg), (650000 + 55 * 30, yg)])], crs=32717).to_file(g, driver="GPKG")
    out = TMP / "rios_merge_prueba.gpkg"; out.unlink(missing_ok=True)
    inf = rios_merge(f, g, out, tol_m=300.0, sigma=0.5)
    l = gpd.read_file(out).geometry.iloc[0]; filas = [(9770000 - y) / 30 - 0.5 for _, y in list(l.coords)[5:-5]]
    assert inf["tramos"] == 1 and abs(np.median(filas) - 20) < 1.0, (inf, np.median(filas))


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=6, file=sys.stdout)
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
