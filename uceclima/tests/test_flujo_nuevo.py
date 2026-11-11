# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Flujo nuevo de UCEclima: premódulo (leer Excel/CSV de lluvia y caudal → memoria → gráficos), módulo 1 (crear proyecto con las series), módulo 2 (conexión GEE sin red: flujo de autorización y
verificación) y módulo 3 (gráficos CHIRPS dentro de la carpeta). Datos sintéticos de respuesta conocida; sin red. Ejecutar: python -m uceclima.tests.test_flujo_nuevo"""
import json, shutil, sys, tempfile, threading, traceback, urllib.request, urllib.error
from pathlib import Path
import numpy as np
import pandas as pd

import uceclima
from uceclima import premodulo as PRE, gee_conexion as GEEC, chirps_salidas as CHS, series_api as SER
from uceclima.ui import servidor as SV

TMP = Path(tempfile.mkdtemp(prefix="uceclima_flujo_"))
PRE.MEM_DIR = TMP / "memoria"                                                       # nunca tocar la memoria real del usuario
GEEC.CONFIG_USUARIO = TMP / "config_gee.json"
SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SV.ESTADO.puerto}"


def get(ruta):
    with urllib.request.urlopen(BASE + ruta, timeout=60) as r:
        return json.loads(r.read())


def post(ruta, cuerpo=None):
    req = urllib.request.Request(BASE + ruta, data=json.dumps(cuerpo or {}).encode(), method="POST", headers={"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _limpio():
    PRE._MEM["series"].clear(); PRE._MEM["cargada"] = True; shutil.rmtree(PRE.MEM_DIR, ignore_errors=True)


def _lluvia_csv(ruta, n=3 * 365, estacion=True, sep=",", decimal="."):
    f = pd.date_range("2000-01-01", periods=n); v = np.round(np.random.default_rng(3).gamma(.6, 7, n), 1)
    d = pd.DataFrame({"Estacion": "M9999", "Fecha": f.strftime("%Y-%m-%d"), "Precipitacion (mm)": v}) if estacion else pd.DataFrame({"fecha": f.strftime("%d/%m/%Y"), "pp": v})
    d.to_csv(ruta, index=False, sep=sep, decimal=decimal); return v


def test_csv_de_lluvia_con_estacion_queda_en_memoria_y_se_grafica():
    _limpio(); f = TMP / "lluvia.csv"; v = _lluvia_csv(f)
    r = PRE.leer(str(f)); assert r["estado"] == "ok" and r["series"] == ["lluvia:M9999"], r
    s = PRE.serie("lluvia:M9999"); assert len(s) == len(v) and abs(s.sum() - v.sum()) < 1e-6 and s.index[0] == pd.Timestamp("2000-01-01")
    m = PRE.memoria(); assert m["n"] == 1 and m["series"][0]["tipo"] == "lluvia" and m["series"][0]["unidad"] == "mm/día" and m["series"][0]["calidad"]["faltantes_pct"] == 0
    d = PRE.datos_lluvia("lluvia:M9999"); assert d["años_completos"] == 3 and len(d["clima_mensual"]["media"]) == 12


def test_coma_decimal_punto_y_coma_y_fecha_dia_primero():
    _limpio(); f = TMP / "pp_coma.csv"; v = _lluvia_csv(f, estacion=False, sep=";", decimal=",")
    r = PRE.leer(str(f)); assert r["estado"] == "ok", r
    s = PRE.serie(r["series"][0]); assert abs(s.sum() - v.sum()) < 1e-6 and s.index[31] == pd.Timestamp("2000-02-01"), s.index[:3]          # 01/02/2000 = 1 de febrero (día primero)


def test_caudal_subdiario_se_promedia_a_diario_y_no_se_rellena():
    _limpio(); t = pd.date_range("2020-01-01", periods=24 * 4 * 9, freq="15min"); q = np.full(len(t), 10.0); q[(t.day == 2)] = 20.0
    d = pd.DataFrame({"fecha": t.strftime("%Y-%m-%d %H:%M"), "caudal_m3s": q}); d = d[~((d.fecha.str.startswith("2020-01-04")) & (d.fecha.str[11:13].astype(int) > 5))]        # el día 4 queda con pocos registros
    f = TMP / "q15.csv"; d.to_csv(f, index=False)
    r = PRE.leer(str(f)); assert r["estado"] == "ok" and any("agregados a diario" in a for a in r["avisos"]), r
    s = PRE.serie(r["series"][0]); assert s.loc["2020-01-02"] == 20.0 and s.loc["2020-01-01"] == 10.0 and pd.Timestamp("2020-01-04") not in s.index           # día incompleto: vacío
    assert PRE.memoria()["series"][0]["tipo"] == "caudal" and PRE.memoria()["series"][0]["unidad"] == "m³/s"


def test_negativos_centinelas_y_conflictos_quedan_vacios_y_se_cuentan():
    _limpio(); f = pd.date_range("2001-01-01", periods=60); v = np.full(60, 3.0); v[5] = -4.0; v[6] = -999.0
    d = pd.DataFrame({"fecha": f.strftime("%Y-%m-%d"), "lluvia_mm": v}); d = pd.concat([d, pd.DataFrame({"fecha": [f[10].strftime("%Y-%m-%d")], "lluvia_mm": [9.0]})])      # fecha repetida con otro valor
    ruta = TMP / "sucia.csv"; d.to_csv(ruta, index=False); r = PRE.leer(str(ruta)); assert r["estado"] == "ok"
    s = PRE.serie(r["series"][0]); L = PRE.memoria()["series"][0]
    assert f[5] not in s.index and f[6] not in s.index and f[10] not in s.index and len(s) == 57, len(s)
    assert any("negativos" in a for a in r["avisos"]) and any("repetidas" in a for a in r["avisos"])


def test_misma_estacion_en_dos_archivos_no_se_pisa_y_releer_el_mismo_es_idempotente():
    _limpio(); a, b = TMP / "estA.csv", TMP / "estB.csv"; va = _lluvia_csv(a); vb = _lluvia_csv(b, n=2 * 365)                  # ambos traen la estación M9999, con datos distintos
    assert PRE.leer(str(a))["estado"] == "ok" and PRE.leer(str(b))["estado"] == "ok"
    m = PRE.memoria(); assert m["n"] == 2, [s["id"] for s in m["series"]]
    assert PRE.serie("lluvia:M9999").size == 3 * 365 and any(s["id"].endswith("__estB") for s in m["series"])
    PRE.leer(str(a)); assert PRE.memoria()["n"] == 2                                                                   # releer el mismo archivo no duplica


def test_columna_ambigua_pide_confirmacion_y_no_adivina():
    _limpio(); f = TMP / "amb.csv"; pd.DataFrame({"fecha": pd.date_range("2020-01-01", periods=40).strftime("%Y-%m-%d"), "valor": range(40)}).to_csv(f, index=False)
    r = PRE.leer(str(f)); assert r["estado"] == "confirmar" and r["candidatos"] == ["valor"] and PRE.memoria()["n"] == 0
    r = PRE.leer(str(f), config={"col_fecha": "fecha", "col_valor": "valor", "tipo": "caudal"}); assert r["estado"] == "ok" and PRE.memoria()["series"][0]["tipo"] == "caudal"


def test_archivo_inexistente_o_formato_no_soportado_da_error_claro_y_no_rompe():
    _limpio(); r = PRE.leer(str(TMP / "no_existe.csv")); assert r["estado"] == "error" and "No existe" in r["mensaje"]
    p = TMP / "x.pdf"; p.write_bytes(b"%PDF"); r = PRE.leer(str(p)); assert r["estado"] == "error" and "no soportado" in r["mensaje"]
    v = PRE.leer_varios([str(TMP / "no_existe.csv")]); assert v["errores"] == 1 and v["ok"] == 0


def test_excel_con_titulo_encima_del_encabezado():
    _limpio(); f = TMP / "q.xlsx"
    d = pd.DataFrame({"Fecha": pd.date_range("2015-05-01", periods=45), "Caudal (m3/s)": np.linspace(5, 50, 45)})
    with pd.ExcelWriter(f) as w:
        pd.DataFrame([["ESTACIÓN H0001 · CAUDALES DIARIOS", None], [None, None]]).to_excel(w, index=False, header=False, sheet_name="Hoja1")
        d.to_excel(w, index=False, startrow=2, sheet_name="Hoja1")
    r = PRE.leer(str(f)); assert r["estado"] == "ok", r
    s = PRE.serie(r["series"][0]); assert len(s) == 45 and abs(s.iloc[-1] - 50) < 1e-9 and PRE.memoria()["series"][0]["tipo"] == "caudal"


def test_memoria_sobrevive_al_reinicio_y_se_puede_quitar():
    _limpio(); f = TMP / "l2.csv"; _lluvia_csv(f); PRE.leer(str(f))
    PRE._MEM["series"].clear(); PRE._MEM["cargada"] = False                                    # «reinicio»
    assert PRE.memoria()["n"] == 1 and PRE.serie("lluvia:M9999").notna().sum() > 1000
    assert PRE.quitar("lluvia:M9999")["n"] == 0 and PRE.memoria()["n"] == 0


def test_rutas_api_leer_memoria_graficos_y_crear_proyecto_con_las_series():
    _limpio(); f = TMP / "api_lluvia.csv"; _lluvia_csv(f, n=4 * 365)
    c, j = post("/api/prep/leer", {"archivos": [str(f)]}); assert c == 200 and j["ok"] == 1 and j["memoria"]["n"] == 1
    assert get("/api/prep/memoria")["n"] == 1 and get("/api/prep/catalogo")["series"][0]["id"] == "lluvia:M9999"
    assert get("/api/prep/lluvia?id=lluvia:M9999")["años_completos"] == 4
    c, j = post("/api/prep/a_proyecto", {}); assert c == 400                                       # sin proyecto abierto
    c, j = post("/api/proyecto/crear", {"nombre": "Proyecto de prueba", "lon": -78.645, "lat": -2.585, "carpeta_base": str(TMP / "proy"), "incluir_memoria": True})
    assert c == 200 and j["series_guardadas"] == 1 and (Path(j["carpeta"]) / "proyecto_uceclima.json").exists(), j
    d = Path(j["carpeta"]); assert (d / "datos" / "series_premodulo" / "indice.json").exists() and j["proyecto"]["crs"] == "EPSG:32717"
    idx = json.loads((d / "datos" / "series_premodulo" / "indice.json").read_text(encoding="utf-8")); assert idx[0]["origen"]["sha256"] and idx[0]["origen"]["archivo"] == "api_lluvia.csv"
    cat = get("/api/series/catalogo")["series"]; assert any(s["id"] == "pre:lluvia_M9999" for s in cat)
    assert get("/api/series/lluvia?id=pre:lluvia_M9999")["años_completos"] == 4
    c, j2 = post("/api/proyecto/crear", {"nombre": "Fuera de CHIRPS", "lon": 10, "lat": 60, "carpeta_base": str(TMP / "proy")}); assert c == 400 and "fuera de la cobertura" in j2["error"]
    assert (TMP / "orig_intacto.txt").exists() is False and Path(f).read_text(encoding="utf-8").startswith("Estacion")          # el archivo crudo no se tocó


def test_proyecto_creado_con_un_nombre_anterior_se_abre_sin_perder_nada():
    from uceclima.ui import proyecto as PRY
    for k, viejo_nombre in enumerate(PRY.ARCHIVOS_ANTIGUOS):                                                    # ClimaUCE y UCEMI
        c, j = post("/api/proyecto/crear", {"nombre": f"Proyecto antiguo {k}", "lon": -78.645, "lat": -2.585, "carpeta_base": str(TMP / "viejo")}); assert c == 200
        d = Path(j["carpeta"]); nuevo = d / PRY.ARCHIVO; viejo = d / viejo_nombre
        nuevo.rename(viejo); assert viejo.exists() and not nuevo.exists()                                       # como lo dejaba la versión anterior
        c, j2 = post("/api/proyecto/abrir", {"ruta": str(d)}); assert c == 200 and j2["proyecto"]["nombre"] == f"Proyecto antiguo {k}"
        assert nuevo.exists() and viejo.exists()                                                                   # se creó el nuevo y el original se conservó
        nuevo.unlink(); c, j3 = post("/api/proyecto/abrir", {"ruta": str(viejo)}); assert c == 200                 # también abriendo el archivo antiguo directamente


def test_nombre_del_programa_es_uceclima_en_pantalla_y_en_la_api():
    html = urllib.request.urlopen(BASE + "/", timeout=30).read().decode("utf-8")
    assert "<title>UCEclima" in html and "<strong>UCEclima Lambda</strong>" in html and "Doctorado en Gestión Sustentable del Agua y Riego" in html and "logo_uce.png" in html   # Zeta: logo UCE en el pie
    assert "climauce" not in html.lower() and SV.ESTADO.token in html
    e = get("/api/estado"); assert "uceclima" in e["carpeta_proyectos"].lower()


# ------------------------------------------------------------------ módulo 4 · IDF INAMHI como X
def test_proyecto_nuevo_nace_con_la_idf_del_inamhi_y_la_estacion_depende_del_sitio():
    from uceclima import idf_x as X
    c, j = post("/api/proyecto/crear", {"nombre": "Sitio Mazar", "lon": -78.645, "lat": -2.585, "carpeta_base": str(TMP / "idf")}); assert c == 200
    cfg = json.loads((Path(j["carpeta"]) / "config_climanet.json").read_text(encoding="utf-8"))
    assert cfg["idf_inamhi"] == {"lat": -2.585, "lon": -78.645} and cfg["idf_x"]["fuente"].startswith("INAMHI") and cfg["Tr"] == 100 and cfg["storm_min"] == 180
    r = get("/api/idf/x"); assert r["referencia"]["codigo"] == "M0138" and r["referencia"]["nombre"] == "PAUTE" and 20 < r["referencia"]["dist_km"] < 30 and r["modo_auto"] == "escalada"
    assert len(r["ecuaciones"]) >= 2 and all(e["K"] > 0 and 0 < e["n"] < 1.5 for e in r["ecuaciones"]) and r["tablas"]["estacion"]["tr"] == [2, 5, 10, 25, 50, 100]
    assert r["tablas"]["estacion"]["duraciones_min"] == [5, 10, 15, 20, 30, 60, 120, 360, 1440] and "HISTÓRICA" in r["avisos"][0]
    c, j2 = post("/api/proyecto/crear", {"nombre": "Sitio Guayas", "lon": -79.60, "lat": -2.12, "carpeta_base": str(TMP / "idf")}); assert c == 200
    r2 = get("/api/idf/x"); assert r2["referencia"]["codigo"] != "M0138" and r2["referencia"]["dist_km"] < 80                                      # otra zona → otra estación: nada escrito a fuego
    esc = get("/api/escenarios/idf"); assert any(e["id"] == "directa" and r2["referencia"]["codigo"] in e["nombre"] for e in esc["escenarios"]), [e["nombre"] for e in esc["escenarios"]][:2]


def test_la_ecuacion_del_libro_reproduce_el_cuadro_de_la_estacion():
    from uceclima import idf_x as X
    r = X.calcular({"ubicacion": "lon -78.6450, lat -2.5850"}, "M0138")
    ec = r["ecuaciones"]; tr100 = r["tablas"]["estacion"]["intensidad_mmh"][-1]; idtr = r["idtr_sitio"]["TR100"]
    for d, i in zip(r["tablas"]["estacion"]["duraciones_min"], tr100):                                         # i = K · Idtr · t^-n con la Idtr de la propia estación debe acercarse al cuadro (el libro mide ~4 % de error medio)
        e = next(x for x in ec if x["t_desde_min"] - 1e-9 <= d <= x["t_hasta_min"] + 1e-9)
        assert i > 0 and e["K"] > 0
    assert r["tormenta"]["tr"] == 100 and abs(sum(r["tormenta"]["mm_por_bloque"]) - r["tormenta"]["p24_mm"] * 0.74) < 0.35 * r["tormenta"]["p24_mm"]


def test_guardar_idf_x_fija_la_configuracion_deja_archivos_nuevos_y_conserva_copia():
    c, j = post("/api/proyecto/crear", {"nombre": "Fijar IDF", "lon": -78.645, "lat": -2.585, "carpeta_base": str(TMP / "idf2")}); assert c == 200
    carpeta = Path(j["carpeta"])
    c, g = post("/api/idf/x/guardar", {"estacion": "M0138", "modo": "estacion", "tr": 100, "duracion_min": 180}); assert c == 200, g
    cfg = json.loads((carpeta / "config_climanet.json").read_text(encoding="utf-8"))
    assert cfg["idf_inamhi"] == {"estacion": "M0138"} and cfg["idf_x"]["modo"] == "estacion" and cfg["idf_x"]["estacion"] == "M0138"          # «directa»: cuadro exacto sin escalar
    assert any(p.name.startswith("config_climanet.json.") and p.suffix == ".bak" for p in carpeta.iterdir())
    d = carpeta / g["carpeta"]; assert all((d / f).stat().st_size > 0 for f in ("idf_estacion.csv", "idf_estacion.xlsx", "ecuaciones_zona.csv", "idf_curvas.png", "tormenta_diseno.png", "idf_x.json"))
    c, g2 = post("/api/idf/x/guardar", {"estacion": "M0031", "modo": "auto"}); assert c == 200 and g2["carpeta"] != g["carpeta"]               # nada se sobrescribe
    cfg = json.loads((carpeta / "config_climanet.json").read_text(encoding="utf-8")); assert cfg["idf_inamhi"] == {"lat": -2.585, "lon": -78.645, "estacion": "M0031"}
    png = urllib.request.urlopen(BASE + "/api/idf/x/png?nombre=idf_curvas.png", timeout=60).read(); assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_las_tres_graficas_idf_pedidas_a_la_vez_llegan_completas():
    c, j = post("/api/proyecto/crear", {"nombre": "Graficas IDF", "lon": -78.645, "lat": -2.585, "carpeta_base": str(TMP / "idf3")}); assert c == 200
    res, errores = {}, []
    def pedir(n):
        try: res[n] = urllib.request.urlopen(BASE + f"/api/idf/x/png?nombre={n}&duracion=180&tr=100", timeout=120).read()
        except Exception as e: errores.append((n, str(e)))
    hilos = [threading.Thread(target=pedir, args=(n,)) for n in ("idf_curvas.png", "idf_modos_tr100.png", "tormenta_diseno.png")]
    [h.start() for h in hilos]; [h.join() for h in hilos]
    assert not errores, errores
    assert all(v[1:4] == b"PNG" and len(v) > 8000 for v in res.values()) and len(set(len(v) for v in res.values())) == 3


# ------------------------------------------------------------------ módulo 11 · entregas (BCA FEMA y El Niño / La Niña)
def _corrida_con_calados(proyecto, nombre, escenario, factor, calado):
    """Corrida sintética terminada con un hmax de respuesta conocida: la mitad oeste = `calado`, la mitad este seca."""
    import rasterio
    from rasterio.transform import from_origin
    import geopandas as gpd
    from shapely.geometry import box
    r = Path(proyecto) / "resultados" / nombre; s = r / "salida" / "Tr100_prueba"; s.mkdir(parents=True)
    a = np.zeros((20, 20), dtype="float32"); a[:, :10] = calado
    with rasterio.open(s / "hmax.tif", "w", driver="GTiff", width=20, height=20, count=1, dtype="float32", crs="EPSG:32717", transform=from_origin(759000, 9714000, 30, 30), nodata=-9999) as d:
        d.write(a, 1)
    gpd.GeoDataFrame({"umbral_m": [0.3]}, geometry=[box(759000, 9713400, 759300, 9714000)], crs="EPSG:32717").to_file(s / "inundacion_ge_03m.gpkg", driver="GPKG")
    (s / "resumen.json").write_text(json.dumps({"estado": "final_completo", "Tr": 100, "P_total_mm": 70.0, "area_ge_0.3_km2": 0.27 if calado >= 0.3 else 0.0, "calado_max_m": float(calado), "estado_calibracion": "no calibrado", "factor_cc": factor}), encoding="utf-8")
    (r / "entrada.json").write_text(json.dumps({"escenario": {"id": escenario, "nombre": escenario, "factor": factor, "ssp": "ssp585" if escenario.startswith("cc_") else None, "horizonte": "2040-2069" if escenario.startswith("cc_") else None}}), encoding="utf-8")
    return s


def test_entrega_arma_carpetas_por_programa_y_calcula_la_exposicion_con_respuesta_conocida():
    from pyproj import Transformer
    from uceclima import entregas as ENT
    c, j = post("/api/proyecto/crear", {"nombre": "Entrega prueba", "lon": -78.645, "lat": -2.585, "carpeta_base": str(TMP / "ent")}); assert c == 200
    carpeta = Path(j["carpeta"])
    _corrida_con_calados(carpeta, "corrida_20260101_000001_real_directa", "directa", 1.0, 0.8)                        # X: calado 0,8 m en la mitad oeste
    _corrida_con_calados(carpeta, "corrida_20260101_000002_real_cc_ssp585_2040-2069_mediana", "cc_ssp585_2040-2069_mediana", 1.2, 2.4)   # Y: calado 2,4 m
    tf = Transformer.from_crs("EPSG:32717", "EPSG:4326", always_xy=True)
    puntos = [(759100, 9713900), (759200, 9713800), (759400, 9713900), (759500, 9713700), (100, 100)]                  # 2 en la mitad oeste, 2 en la este (seca), 1 fuera del dominio
    lon, lat = zip(*[tf.transform(x, y) for x, y in puntos])
    d = carpeta / "datos_descargados" / "otras_20260101_000000" / "edificaciones"; d.mkdir(parents=True)
    pd.DataFrame({"lon": lon, "lat": lat, "area_m2": [50, 60, 70, 80, 90], "confianza": 0.8}).to_csv(d / "edificaciones_puntos.csv", index=False)
    c, e = post("/api/entregas/construir", {}); assert c == 200, e
    raiz = Path(e["ruta_completa"]); assert {"01_resultados", "02_BCA_FEMA", "03_ENSO_El_Nino_La_Nina"} <= set(e["por_carpeta"]) | {"02_BCA_FEMA", "03_ENSO_El_Nino_La_Nina"} and (raiz / "00_LEEME.md").exists() and (raiz / "manifiesto.json").exists()
    t = pd.read_csv(raiz / "01_resultados" / "tablas" / "resumen_corridas.csv"); assert set(t["escenario"]) == {"directa", "cc_ssp585_2040-2069_mediana"} and set(t["tipo"].str[0]) == {"X", "Y"}
    assert (raiz / "01_resultados" / "tablas" / "resumen_corridas.xlsx").exists() and len(list((raiz / "01_resultados" / "shapes").glob("*_wgs84.shp"))) == 2 and len(list((raiz / "01_resultados" / "shapes").glob("*_utm.shp"))) == 2
    x = pd.read_csv(raiz / "02_BCA_FEMA" / "resumen_exposicion_por_escenario.csv"); ed = x[x["elemento"] == "edificaciones"]
    def n(esc, cl): return int(ed[(ed["escenario"] == esc) & (ed["clase_calado"] == cl)]["n"].sum())
    assert n("directa", "0,5–1 m") == 2 and n("directa", "> 2 m") == 0 and n("directa", "fuera del dominio del modelo") == 1                  # 0,8 m → clase 0,5–1; los 2 puntos del este están secos
    assert n("cc_ssp585_2040-2069_mediana", "> 2 m") == 2 and n("cc_ssp585_2040-2069_mediana", "0,5–1 m") == 0
    assert abs(float(ed[(ed["escenario"] == "directa") & (ed["clase_calado"] == "0,5–1 m")]["area_m2"].sum()) - 110) < 1e-6                         # 50 + 60 m²
    f = pd.read_csv(raiz / "02_BCA_FEMA" / "frecuencia" / "escenarios_frecuencia.csv"); assert set(f["Tr_anios"]) == {100} and abs(f["probabilidad_anual"].iloc[0] - 0.01) < 1e-9 and sorted(f["factor_cc"]) == [1.0, 1.2]
    assert len(list((raiz / "02_BCA_FEMA" / "peligro").glob("*_clases_calado_wgs84.shp"))) == 2 and len(list((raiz / "02_BCA_FEMA" / "peligro").glob("*_calado_max_m.tif"))) == 2
    assert (raiz / "02_BCA_FEMA" / "exposicion" / "edificaciones_calado_utm.shp").exists() and (raiz / "02_BCA_FEMA" / "LEEME_BCA_FEMA.md").exists()
    txt = (raiz / "02_BCA_FEMA" / "LEEME_BCA_FEMA.md").read_text(encoding="utf-8"); assert "Curvas calado–daño" in txt and "no calibrado" in txt.lower()
    assert any("Población" in nota for nota in e["notas"]) and any("CHIRPS" in nota for nota in e["notas"])                                              # lo que falta se dice
    man = json.loads((raiz / "manifiesto.json").read_text(encoding="utf-8")); assert all(len(a["sha256"]) == 64 for a in man["archivos"]) and len(man["archivos"]) == e["archivos"]
    c, e2 = post("/api/entregas/construir", {}); assert c == 200 and e2["ruta_completa"] != e["ruta_completa"]                                          # nada se sobrescribe
    assert len(get("/api/entregas")["entregas"]) == 2


def test_cada_modulo_del_menu_tiene_su_propia_pantalla():
    import re
    js = "\n".join(f.read_text(encoding="utf-8") for f in (Path(SV.__file__).parent / "static").glob("*.js"))
    m = re.search(r"const VISTAS = \{([^}]*)\}", js); base = set(re.findall(r"(\w+)\s*:", m.group(1))) if m else set()
    asignadas = set(re.findall(r"VISTAS\.(\w+)\s*=", js))
    faltan = [x["id"] for x in get("/api/estado")["modulos"] if x["id"] not in base | asignadas]
    assert not faltan, f"módulos del menú sin pantalla (caen en Proyecto): {faltan}"


# ------------------------------------------------------------------ módulo 2 · conexión con Earth Engine (sin red)
def test_gee_estado_por_pasos_y_proyecto_valido():
    assert GEEC.estado()["paso_actual"] in (1, 2)
    for malo in ("Mi Proyecto", "ab", "PROYECTO-X", "1abcdef"):
        try:
            GEEC.guardar_proyecto(malo); raise AssertionError("debía rechazar " + malo)
        except GEEC.GeeError:
            pass
    assert GEEC.guardar_proyecto("clima-prueba-123")["gee_project"] == "clima-prueba-123" and GEEC.estado()["proyecto"] == "clima-prueba-123"
    assert "token" not in (TMP / "config_gee.json").read_text(encoding="utf-8").lower()                  # solo el ID del proyecto


def test_gee_autorizacion_en_modo_codigo_y_cancelacion_sin_abrir_navegador():
    import webbrowser
    webbrowser.open = lambda *a, **k: True
    a = GEEC.iniciar_autorizacion("codigo"); assert a["fase"] == "esperando_codigo" and a["url"].startswith("https://code.earthengine.google.com/client-auth")
    try:
        GEEC.enviar_codigo("   "); raise AssertionError("debía rechazar código vacío")
    except GEEC.GeeError:
        pass
    assert GEEC.cancelar()["auth"]["fase"] == "cancelado"
    b = GEEC.iniciar_autorizacion("localhost"); assert b["fase"] == "esperando_aprobacion" and "accounts.google.com" in b["url"] and "code_challenge=" in b["url"]       # PKCE: no viaja ningún secreto
    GEEC.cancelar()


def test_gee_verificar_traduce_errores_a_ayuda_concreta():
    GEEC.guardar_proyecto("clima-prueba-123")
    assert "registr" in GEEC._ayuda_error("Not signed up for Earth Engine").lower() and "api" in GEEC._ayuda_error("Earth Engine API has not been used in project").lower()
    assert "permiso" in GEEC._ayuda_error("403 Permission denied").lower() and "autorizar" in GEEC._ayuda_error("invalid_grant").lower()
    GEEC.CONFIG_USUARIO.unlink(missing_ok=True)                                                              # sin proyecto guardado
    v = GEEC.verificar(""); assert v["verificacion"]["ok"] is False and "ID del proyecto" in v["verificacion"]["error"]
    antes = GEEC.credenciales_existen; GEEC.credenciales_existen = lambda: False                              # con proyecto pero sin autorización: no se llama a la red
    try:
        v = GEEC.verificar("clima-prueba-123"); assert v["verificacion"]["ok"] is False and "autorización" in v["verificacion"]["error"] and "paso 2" in v["verificacion"]["ayuda"]
    finally:
        GEEC.credenciales_existen = antes
    c, j = post("/api/gee/proyecto", {"proyecto": "Mal Id"}); assert c == 400
    assert get("/api/gee/estado")["paso_actual"] in (1, 2, 3)


def test_gee_conectar_prueba_candidatos_en_orden_y_se_queda_con_el_primero_que_funciona():
    import os
    for k in ("UCECLIMA_GEE_PROJECT", "EARTHENGINE_PROJECT", "GOOGLE_CLOUD_PROJECT"):
        os.environ.pop(k, None)
    GEEC.CONFIG_USUARIO.unlink(missing_ok=True)
    antes = (GEEC.credenciales_existen, GEEC.proyecto_sugerido, GEEC._proyecto_gcloud, GEEC.verificar)
    try:
        GEEC.credenciales_existen = lambda: True; GEEC.proyecto_sugerido = lambda: "proyecto-de-credenciales"; GEEC._proyecto_gcloud = lambda: "proyecto-gcloud-1"
        os.environ["GOOGLE_CLOUD_PROJECT"] = "proyecto-entorno-1"
        assert GEEC.candidatos() == ["proyecto-entorno-1", "proyecto-de-credenciales", "proyecto-gcloud-1"]                      # sin repetir, en orden
        llamados = []
        def falso(pid=None):
            llamados.append(pid); ok = pid == "proyecto-de-credenciales"
            GEEC._VERIF.update(ok=ok, proyecto=pid, detalle="simulado" if ok else None, error=None if ok else "Not signed up for Earth Engine", ayuda=None, fecha_utc="2026-01-01T00:00:00+00:00")
            return GEEC.estado()
        GEEC.verificar = falso
        e = GEEC.conectar()
        assert llamados == ["proyecto-entorno-1", "proyecto-de-credenciales"], llamados                                       # se detuvo en el primero que funcionó
        assert e["conectado"] and e["verificacion"]["proyecto"] == "proyecto-de-credenciales" and [x["ok"] for x in e["verificacion"]["probados"]] == [False, True]
        assert GEEC._cfg()["gee_project"] == "proyecto-de-credenciales"                                                        # quedó guardado el proyecto que funcionó
        GEEC.CONFIG_USUARIO.unlink(missing_ok=True); os.environ.pop("GOOGLE_CLOUD_PROJECT", None); GEEC.proyecto_sugerido = lambda: None; GEEC._proyecto_gcloud = lambda: None
        e = GEEC.conectar(); assert not e["conectado"] and "ID de TU proyecto" in e["verificacion"]["ayuda"]                  # ningún candidato: pide el ID, no inventa
        GEEC.credenciales_existen = lambda: False
        e = GEEC.conectar(); assert not e["conectado"] and "autorización" in e["verificacion"]["error"]
    finally:
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None); GEEC.credenciales_existen, GEEC.proyecto_sugerido, GEEC._proyecto_gcloud, GEEC.verificar = antes


# ------------------------------------------------------------------ módulo 2 · descargas: uso de suelo (paso 1) → CN y Manning calculados localmente (paso 2)
def _capas_sinteticas(proyecto, clase=30, textura=3):
    """Capas de uso de suelo (clase constante) y textura (constante) en EPSG:4326 que cubren el área del proyecto, como las que baja el paso 1."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.warp import transform_bounds
    from uceclima.ui import proyecto as PRY
    datos, _ = PRY.abrir(str(proyecto)); _, cfg = PRY.config_climanet(datos, Path(proyecto)); x0, x1, y0, y1 = cfg["aoi"]
    b = transform_bounds(datos["crs"], "EPSG:4326", x0 - 500, y0 - 500, x1 + 500, y1 + 500)
    d = Path(proyecto) / "datos_descargados" / "suelo_20260101_000000"; d.mkdir(parents=True)
    for nombre, valor, dt, n in (("uso_suelo_worldcover.tif", clase, "uint8", 120), ("textura_suelo_openlandmap.tif", textura, "uint8", 30)):
        with rasterio.open(d / nombre, "w", driver="GTiff", width=n, height=n, count=1, dtype=dt, crs="EPSG:4326", transform=from_bounds(*b, n, n)) as s:
            s.write(np.full((n, n), valor, dtype=dt), 1)
    return d


def test_cn_manning_se_calcula_localmente_con_las_capas_bajadas_y_exige_el_paso_1():
    import rasterio
    from uceclima import descargas as DES, parametros_gee as PG, preparacion
    from uceclima.ui import demo
    c = demo.crear_sintetico(TMP / "sint_suelo"); dest = c / "datos_descargados" / "cn_manning_prueba"; dest.mkdir(parents=True)
    try:
        PG.cn_manning_gee(dest, {"proyecto": str(c)}, lambda f, m: None); raise AssertionError("debía exigir las capas del paso 1")
    except DES.DescargaError as e:
        assert "1 · Uso de suelo y suelo" in str(e)
    _capas_sinteticas(c, clase=30, textura=3)
    mensajes = []
    r = PG.cn_manning_gee(dest, {"proyecto": str(c)}, lambda f, m: mensajes.append(m))
    assert any("sin conexión" in m for m in mensajes) and r["cobertura_parametros_pct"] == 100 and "suelo_20260101_000000" in r["fuente"]
    cn_esperado = PG.CN[30][PG.HSG[3] - 1]
    with rasterio.open(dest / "cn_gee.tif") as s:
        v = s.read(1); v = v[v > -9000]
    assert v.size > 100 and np.allclose(v, cn_esperado) and abs(r["cn_min_max_media"][0] - cn_esperado) < 1e-6
    with rasterio.open(dest / "manning_gee.tif") as s:
        m = s.read(1); m = m[m > -9000]
    assert np.allclose(m, PG.NMAP[30], atol=1e-6)


def test_cancelar_descarga_en_curso_libera_el_gestor():
    import time
    from uceclima import descargas as DES
    def lenta(destino, p, progreso):
        for k in range(200):
            progreso(k / 200, f"paso {k}"); time.sleep(0.05)
        return {"archivos": []}
    DES.FUENTES["_lenta_prueba"] = lenta
    try:
        g = DES.GestorDescargas(); did = g.iniciar(TMP / "proy_cancel", "_lenta_prueba", {}); time.sleep(0.3)
        assert g.activa() and g.cancelar() is True
        for _ in range(100):
            if not g.activa(): break
            time.sleep(0.1)
        assert not g.activa()
        e = json.loads((TMP / "proy_cancel" / "datos_descargados" / did / "estado.json").read_text(encoding="utf-8"))
        assert e["estado"] == "fallido" and "cancelada" in e["mensaje"].lower()
        assert g.cancelar() is False                                                                   # sin descarga activa no hace nada
        time.sleep(1.1); g.iniciar(TMP / "proy_cancel", "_lenta_prueba", {}); assert g.activa(); g.cancelar()           # y se puede lanzar otra después
    finally:
        DES.FUENTES.pop("_lenta_prueba", None)


# ------------------------------------------------------------------ módulo 3 · CHIRPS: gráficos dentro de la carpeta
def test_chirps_genera_graficos_y_resumen_dentro_de_la_carpeta_de_la_descarga():
    d = TMP / "chirps_x"; d.mkdir(); f = pd.date_range("1981-01-01", "2010-12-31")
    v = np.round(np.random.default_rng(1).gamma(.5, 9, len(f)) * (1 + 0.005 * (f.year - 1981)), 2)
    pd.DataFrame({"fecha": f.strftime("%Y-%m-%d"), "pixel_mm": v, "media_caja_mm": v, "celda_nex_mm": v}).to_csv(d / "chirps_diario.csv", index=False)
    arch = CHS.generar(d); assert {"chirps_anual.png", "chirps_climatologia.png", "chirps_excedencia.png", "chirps_resumen_anual.csv", "chirps_resumen.json"} <= set(arch)
    assert all((d / "graficos" / a).stat().st_size > 500 for a in arch)
    res = json.loads((d / "graficos" / "chirps_resumen.json").read_text(encoding="utf-8")); assert res["anios_completos"] == 30 and res["tendencia_total"]["sen_por_anio"] > 0 and "satélite" in res["nota"]
    tab = pd.read_csv(d / "graficos" / "chirps_resumen_anual.csv"); assert len(tab) == 30


if __name__ == "__main__":
    fallos = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("OK   ", n)
            except BaseException:
                fallos += 1; print("FALLA", n); traceback.print_exc(limit=4, file=sys.stdout)
    SRV.shutdown(); shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
