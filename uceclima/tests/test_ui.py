# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Pruebas de la interfaz a nivel de API (servidor real en un puerto efímero, proceso de cálculo real, caso sintético pequeño).
Ejecutar: python -m uceclima.tests.test_ui  (desde MILAGRO)"""
import json, shutil, sys, tempfile, threading, time, traceback, urllib.request, urllib.error
from pathlib import Path
import uceclima
from uceclima.ui import servidor as SV, proyecto as P, demo

TMP = Path(tempfile.mkdtemp(prefix="uceclima_ui_"))
SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SV.ESTADO.puerto}"


def get(ruta):
    with urllib.request.urlopen(BASE + ruta, timeout=60) as r:
        ct = r.headers.get("Content-Type", ""); b = r.read()
        return json.loads(b) if "json" in ct else b


def post(ruta, cuerpo=None, token=None):
    req = urllib.request.Request(BASE + ruta, data=json.dumps(cuerpo or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token if token is None else token})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _demo():
    c = demo.crear_sintetico(TMP / "sint")
    return c


def test_seguridad_token_y_host():
    c, j = post("/api/verificar", token="mal"); assert c == 403
    req = urllib.request.Request(BASE + "/api/estado", headers={"Host": "evil.example.com"})
    try:
        urllib.request.urlopen(req); raise SystemExit("debió rechazar host ajeno")
    except urllib.error.HTTPError as e:
        assert e.code == 403
    html = get("/").decode("utf-8"); assert SV.ESTADO.token in html and "__TOKEN__" not in html


def test_proyecto_esquema_y_no_sobrescribir():
    c = _demo()
    code, j = post("/api/proyecto/abrir", {"ruta": str(c)}); assert code == 200 and j["proyecto"]["tipo"] == "sintetico"
    code, j = post("/api/proyecto/abrir", {"ruta": str(TMP / "no_existe")}); assert code == 400 and "No existe" in j["error"]
    malo = TMP / "malo"; malo.mkdir(); (malo / P.ARCHIVO).write_text(json.dumps({"nombre": "x"}), encoding="utf-8")
    code, j = post("/api/proyecto/abrir", {"ruta": str(malo)}); assert code == 400 and "inválido" in j["error"]
    post("/api/proyecto/abrir", {"ruta": str(c)})
    code, j = post("/api/proyecto/guardar_como", {"carpeta": str(c)}); assert code == 409                       # ya existe: no se sobrescribe
    destino = TMP / "copia"
    code, j = post("/api/proyecto/guardar_como", {"carpeta": str(destino), "nombre": "Copia de prueba"}); assert code == 200 and (destino / P.ARCHIVO).exists()
    code, j = post("/api/proyecto/guardar_como", {"carpeta": str(destino)}); assert code == 409


def test_verificacion_detecta_faltantes_y_etiqueta_sintetica():
    c = _demo(); post("/api/proyecto/abrir", {"ruta": str(c)})
    code, v = post("/api/verificar"); assert code == 200 and v["puede_ejecutar"]
    ids = {x["id"]: x for x in v["chequeos"]}
    assert ids["etiqueta"]["estado"] == "aviso" and "SINTÉTICO" in ids["etiqueta"]["mensaje"] and ids["calibracion"]["estado"] == "pendiente"
    assert ids["recursos"]["dato"]["celdas"] == 3600
    # sin terreno: error claro y no se ejecuta
    (c / "datos" / "terreno_sintetico.tif").rename(c / "datos" / "oculto.tif")
    try:
        code, v = post("/api/verificar"); assert not v["puede_ejecutar"] and any(x["id"] == "dem" and x["estado"] == "error" for x in v["chequeos"])
        code, j = post("/api/corrida/iniciar"); assert code == 422 and "no se ejecuta" in j["error"]
    finally:
        (c / "datos" / "oculto.tif").rename(c / "datos" / "terreno_sintetico.tif")


def test_caso_grande_se_rechaza():
    c = _demo(); post("/api/proyecto/abrir", {"ruta": str(c)})
    cfgp = c / "config_climanet.json"; cfg = json.loads(cfgp.read_text(encoding="utf-8")); orig = dict(cfg)
    cfg["aoi"] = [500000, 520000, 9760000, 9780000]; cfg["res"] = 10                                      # fuera del terreno y enorme
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    try:
        code, v = post("/api/verificar"); r = {x["id"]: x for x in v["chequeos"]}
        assert not v["puede_ejecutar"] and r["recursos"]["estado"] == "error"
    finally:
        cfgp.write_text(json.dumps(orig), encoding="utf-8")


def test_flujo_completo_sintetico_y_cancelacion():
    c = _demo(); post("/api/proyecto/abrir", {"ruta": str(c)})
    code, j = post("/api/corrida/iniciar"); assert code == 200, j
    rid = j["id"]
    code2, j2 = post("/api/corrida/iniciar"); assert code2 == 409                                       # una tarea por vez
    for _ in range(240):
        e = get("/api/corrida/estado?id=" + rid)
        if e["estado"] != "en_curso": break
        time.sleep(1)
    assert e["estado"] == "completado", e
    r = get("/api/corrida/resultado?id=" + rid)
    ev, rs = r["evaluacion"], r["resumen"]
    assert abs(ev["diferencia_balance_fisico_pct"]) < 1e-6 and ev["Courant_max"] <= 0.35 + 1e-9 and ev["capacidad_canales"]["estado"] == "no_evaluada"
    assert rs["escenario"] == "diseno_idf_historica" and rs["estado_calibracion"] == "no calibrado" and r["mapa_png"]
    png = get("/api/corrida/mapa.png?id=" + rid); assert png[:4] == b"\x89PNG" and len(png) > 20000
    v = get("/api/visor/datos?id=" + rid)                                                                  # visor 3D: terreno y capas reales de la corrida
    assert v["sintetico"] and v["nx"] * v["ny"] == len(v["z"]) == 3600 and {c["id"] for c in v["capas_info"]} >= {"hmax", "vmax"}
    assert all(len(v["capas"][k]) == 3600 for k in v["capas"]) and v["capas_info"][0]["max"] > 0 and "no calibrado" in v["aviso"]
    try:
        get("/api/visor/datos?id=NO_EXISTE"); raise SystemExit("corrida inexistente debió fallar")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    assert "visor.js" in get("/visor").decode("utf-8")
    import os, subprocess
    chrome = next((q for q in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe") if os.path.exists(q)), None)
    if chrome:                                                                                             # la escena WebGL se construye (software GL) y muestra cifras reales
        out = subprocess.run([chrome, "--headless=new", "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist", "--virtual-time-budget=12000", "--dump-dom", BASE + "/visor?id=" + rid],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180).stdout
        assert "celdas con agua de 3.600" in out and "SINTÉTICO" in out and out.count("<canvas") >= 1
    assert (c / "resultados" / rid / "registro.log").stat().st_size > 0 and (c / "resultados" / rid / "entrada.json").exists()
    # cancelación: se lanza otra y se cancela
    code, j = post("/api/corrida/iniciar"); assert code == 200
    time.sleep(0.3); code, k = post("/api/corrida/cancelar"); assert k["cancelada"]
    e = get("/api/corrida/estado?id=" + j["id"]); assert e["estado"] == "cancelado" and "incompleto" in e["mensaje"]
    assert any(x["id"] == rid and x["estado"] == "completado" for x in get("/api/estado")["corridas"])          # el historial conserva ambas


def test_corrida_interrumpida_se_detecta():
    c = _demo(); post("/api/proyecto/abrir", {"ruta": str(c)})
    run = c / "resultados" / "corrida_20000101_000000_fantasma"; run.mkdir(parents=True)
    (run / "estado.json").write_text(json.dumps({"estado": "en_curso", "pid": 999999, "progreso": 0.4}), encoding="utf-8")
    e = get("/api/corrida/estado?id=corrida_20000101_000000_fantasma"); assert e["estado"] == "interrumpido"


def test_modulos_pendientes_y_cmip6_bloqueado():
    mods = {m["id"]: m for m in get("/api/estado")["modulos"]}
    assert mods["cmip6"]["estado"] == "implementado" and len(mods) == 17 and mods["pronostico"]["estado"] == "implementado" and mods["campo"]["estado"] == "implementado" and mods["visor"]["estado"] == "parcial" and mods["contaminantes"]["estado"] == "parcial"
    c = get("/api/cmip6/compuerta"); assert c["bloqueado"] is False
    code, j = post("/api/chirps/plan", {"inicio": "2011-02-02", "fin": "2011-02-04"}); assert code == 200 and "antes_21d" in j["ventanas"]
    code, j = post("/api/chirps/plan", {"inicio": "2011-02-04", "fin": "2011-02-02"}); assert code == 400


def test_hipsometria_retirada_y_validacion_de_campo_en_su_lugar():
    c = _demo(); post("/api/proyecto/abrir", {"ruta": str(c)})
    for ruta in ("/api/hipsometria?alcance=aoi", "/api/hipsometria/alcances"):                                  # Zeta 31-oct: la maqueta hipsométrica se retiró
        try:
            r = get(ruta); assert not (isinstance(r, dict) and ("n_celdas" in r or "alcances" in r))
        except urllib.error.HTTPError as e:
            assert e.code in (400, 404)
    req = urllib.request.Request(BASE + "/static/iso/iso-kit.mjs")
    with urllib.request.urlopen(req) as r: assert "javascript" in r.headers["Content-Type"]                 # los módulos ES (visor) exigen el tipo MIME correcto
    e = get("/api/campo/estado"); assert isinstance(e["corridas"], list) and e["marcas"] == 0 and e["ultimo_contraste"] is None
    code, j = post("/api/campo/encuesta", {"zona": "Demo", "endpoint": "https://ejemplo.com/x"}); assert code == 400 and "Apps Script" in j["error"] or "corridas" in j["error"]
    code, j = post("/api/campo/contrastar", {}); assert code == 400 and ("marcas" in j["error"] or "corridas" in j["error"])

def test_api_abierta_estaciones_y_mdt_de_dron():
    import numpy as np, rasterio
    from rasterio.transform import from_origin
    c = demo.crear_sintetico(TMP / "sint_api"); post("/api/proyecto/abrir", {"ruta": str(c)})
    # --- clave de API: sin token ni clave no se actúa; con la clave sí; documentación abierta
    req = urllib.request.Request(BASE + "/api/estado", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req); raise SystemExit("POST sin clave debió fallar")
    except urllib.error.HTTPError as e:
        assert e.code == 403
    clave = SV.ESTADO.clave_api
    def con_clave(ruta, cuerpo, k=clave):
        r = urllib.request.Request(BASE + ruta, data=json.dumps(cuerpo).encode(), method="POST", headers={"Content-Type": "application/json", "Authorization": "Bearer " + k})
        try:
            with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    assert con_clave("/api/proyecto/abrir", {"ruta": str(c)}, "cu_clave_falsa_xxxxxxxxxxxxxxxx")[0] == 403
    code, j = con_clave("/api/proyecto/abrir", {"ruta": str(c)}); assert code == 200 and j["proyecto"]["tipo"] == "sintetico"          # un agente maneja la app solo con la clave
    spec = get("/api/openapi.json"); assert spec["openapi"].startswith("3.") and "/api/estaciones/importar" in spec["paths"] and "/api/terreno/registrar" in spec["paths"]
    assert "CMIP6" in get("/api/ia").decode("utf-8")
    assert "bloqueado" in get("/api/ia").decode("utf-8")
    # --- estaciones: CSV con coma decimal, punto y coma, un negativo y un hueco
    import pandas as pd
    ts = pd.date_range("2026-02-01 00:00", periods=288, freq="5min")
    v = np.zeros(len(ts)); v[100:110] = [0.2, 0.8, 1.6, 2.4, 3.0, 2.2, 1.0, 0.6, 0.2, 0.2]; v[50] = -1
    df = pd.DataFrame({"Fecha y hora": ts.strftime("%d/%m/%Y %H:%M"), "Precipitacion (mm)": [str(round(x, 2)).replace(".", ",") for x in v]}).drop(index=range(200, 212))
    csvp = TMP / "pluvio.csv"; df.to_csv(csvp, sep=";", index=False)
    pv = con_clave("/api/estaciones/vista_previa", {"archivo": str(csvp)})[1]
    assert pv["delimitador"] == ";" and pv["propuesta"]["fecha"] == "Fecha y hora" and pv["propuesta"]["lluvia"] == "Precipitacion (mm)"
    meta = {"archivo": str(csvp), "id": "T001", "nombre": "Prueba", "tipo": "pluviografo", "col_fecha": "Fecha y hora", "col_lluvia": "Precipitacion (mm)", "lon": -79.6, "lat": -2.1, "zona_horaria": "America/Guayaquil", "dayfirst": True}
    code, r = con_clave("/api/estaciones/importar", meta); assert code == 200, r
    q = r["calidad"]; assert q["n_registros"] == 276 and q["negativos"] == 1 and q["huecos"] == 1 and abs(q["total_mm"] - 12.2) < 1e-6 and q["paso_min_detectado"] == 5.0, q
    assert q["inicio_utc"].startswith("2026-02-01T05:00")                                            # 00:00 en Guayaquil = 05:00 UTC
    assert con_clave("/api/estaciones/importar", meta)[0] == 400                                       # no sobrescribe
    lista = get("/api/estaciones")["estaciones"]; assert lista[0]["id"] == "T001" and abs(lista[0]["x"] - 622000) < 200000
    ser = get("/api/estaciones/serie?id=T001"); assert len(ser["fecha"]) == 276 and ser["lluvia_mm"][50] is None                          # el negativo quedó ausente, no cero
    dup = pd.concat([df.iloc[:5], df.iloc[:1].assign(**{"Precipitacion (mm)": "9,9"})]); dp = TMP / "dup.csv"; dup.to_csv(dp, sep=";", index=False)
    assert con_clave("/api/estaciones/importar", {**meta, "archivo": str(dp), "id": "T002"})[0] == 400                                   # duplicados contradictorios se rechazan
    code, hz = con_clave("/api/estaciones/hietograma", {"id": "T001", "inicio": "2026-02-01T05:00:00", "fin": "2026-02-01T20:00:00"}); assert code == 200 and hz["n"] > 100
    # --- MDT de dron
    tr = from_origin(500000, 9763000, 0.5, 0.5); z = (30 + 0.01 * np.add.outer(np.arange(2000), np.arange(2000))).astype("float32"); z[:50, :50] = -9999
    dem = TMP / "dron.tif"
    with rasterio.open(dem, "w", driver="GTiff", height=2000, width=2000, count=1, dtype="float32", crs="EPSG:32717", transform=tr, nodata=-9999) as w: w.write(z, 1)
    ins = con_clave("/api/terreno/inspeccionar", {"archivo": str(dem)})[1]
    assert ins["crs"] == "EPSG:32717" and ins["res_m"] == 0.5 and ins["apto"] and 0 < ins["validas_pct"] < 100
    geo = TMP / "geo.tif"
    with rasterio.open(geo, "w", driver="GTiff", height=50, width=50, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(-79.6, -2.1, 0.0001, 0.0001)) as w: w.write(np.ones((50, 50), "float32"), 1)
    assert con_clave("/api/terreno/registrar", {"archivo": str(geo), "tipo_terreno": "DSM", "datum": "no verificado"})[0] == 400          # CRS geográfico: no se registra
    assert con_clave("/api/terreno/registrar", {"archivo": str(dem), "tipo_terreno": "DSM", "datum": "no verificado", "res": 10, "aoi": [400000, 400500, 9762000, 9762500]})[0] == 400  # fuera del ráster
    code, rg = con_clave("/api/terreno/registrar", {"archivo": str(dem), "tipo_terreno": "DSM", "datum": "no verificado", "res": 5, "aoi": [500100, 500500, 9762500, 9762900]}); assert code == 200, rg
    assert rg["celdas_modelo"] == 80 * 80 and list(c.glob("config_climanet.json.*.bak")) and get("/api/estado")["proyecto"]["tipo_terreno"] == "DSM"
    assert json.loads((c / "config_climanet.json").read_text(encoding="utf-8"))["dem"].endswith("dron.tif")


def test_evento_observado_de_estacion_conduce_la_corrida():
    import numpy as np, pandas as pd
    c = demo.crear_sintetico(TMP / "sint_evento"); post("/api/proyecto/abrir", {"ruta": str(c)})
    ts = pd.date_range("2026-02-01 00:00", periods=36, freq="5min"); mm = np.r_[np.zeros(6), np.linspace(1, 8, 12), np.linspace(8, 1, 12), np.zeros(6)]
    csvp = TMP / "ev_est.csv"; pd.DataFrame({"fecha": ts.strftime("%Y-%m-%d %H:%M"), "mm": mm}).to_csv(csvp, index=False)
    meta = {"archivo": str(csvp), "id": "EV01", "col_fecha": "fecha", "col_lluvia": "mm", "x": 500300, "y": 9760300, "dayfirst": False}
    assert post("/api/estaciones/importar", meta)[0] == 200
    code, j = post("/api/proyecto/evento", {"estacion": "EV01", "inicio": "2026-02-01T05:00:00", "fin": "2026-02-01T07:55:00"}); assert code == 200, j
    assert abs(j["P_total_mm"] - mm.sum()) < 1e-6 and j["sim_horas"] >= 3 and not j["desagregada"], j
    assert get("/api/proyecto/evento")["evento"]["id"].startswith("EV01")
    code, v = post("/api/verificar"); chk = {x["id"]: x for x in v["chequeos"]}; assert "EVENTO OBSERVADO" in chk["evento"]["mensaje"] and chk["idf"]["estado"] == "ok", v
    code, j = post("/api/corrida/iniciar"); assert code == 200, j
    rid = j["id"]
    for _ in range(240):
        e = get("/api/corrida/estado?id=" + rid)
        if e["estado"] != "en_curso": break
        time.sleep(1)
    assert e["estado"] == "completado", e
    r = get("/api/corrida/resultado?id=" + rid)["resumen"]
    assert r["tipo_forzamiento"] == "evento_observado" and r["estado_calibracion"] == "no calibrado" and "OBSERVADO" in r["aviso"] and abs(r["P_total_mm"] - mm.sum()) < 1e-6
    for _ in range(100):                                                                                      # el proceso de cálculo tarda un instante en salir tras escribir «completado»
        if not get("/api/estado")["corrida_activa"]: break
        time.sleep(0.2)
    assert post("/api/proyecto/evento", {"estacion": "EV01", "inicio": "2026-02-01T05:00:00", "fin": "2026-02-01T05:05:00", "sim_horas": 0.01})[0] == 400          # la simulación debe cubrir el evento
    assert post("/api/proyecto/evento_quitar")[0] == 200 and get("/api/proyecto/evento")["evento"] is None


def test_premodulo_preparacion_de_datos_por_api():
    from uceclima.tests.test_preparacion import _ancho, _inventario
    import numpy as np, pandas as pd
    c = demo.crear_sintetico(TMP / "sint_prep"); post("/api/proyecto/abrir", {"ruta": str(c)})
    d = TMP / "crudos"; d.mkdir(exist_ok=True)
    xl = _ancho(d); inv = _inventario(d)
    csv = d / "M0001_larga.csv"; pd.DataFrame({"Estacion": "M0001", "Fecha": pd.date_range("2010-01-01", periods=30), "Precipitacion": 2.0}).to_csv(csv, index=False)
    code, e = post("/api/prep/escanear", {"carpeta": str(d)}); assert code == 200 and e["por_tipo"].get("precipitacion_ancha_inamhi") == 1 and e["por_tipo"].get("inventario_eventos") == 1 and e["por_tipo"].get("precipitacion_larga") == 1, e
    code, r = post("/api/prep/precipitacion", {"archivo": str(xl)}); assert code == 200 and {x["codigo"] for x in r["problemas"]} >= {"encabezados_corridos", "filas_de_grupo"} and "M0001" in r["calidad"]
    code, r = post("/api/prep/inventario", {"archivo": str(inv)}); assert code == 200 and r["resumen"]["n_eventos"] == 6
    code, r = post("/api/prep/contrastar", {"precip_archivo": str(xl), "estacion": "M0001", "inventario_archivo": str(inv), "cantones": ["Milagro"], "ventana_dias": 3}); assert code == 200 and r["resumen"]["eventos_dentro_del_periodo_de_lluvia"] == 0 and r["avisos"]   # los eventos son de 2020 y la lluvia de 2010-2011: se dice, no se inventa
    code, r = post("/api/prep/contrastar", {"precip_archivo": str(xl), "estacion": "NOEXISTE", "inventario_archivo": str(inv)}); assert code == 400 and "no está" in r["error"]
    assert post("/api/prep/ordenar", {"archivos": [str(d / "inv.xlsx")]})[0] == 400                                                                                     # un inventario no es lluvia
    code, o = post("/api/prep/ordenar", {"archivos": [str(xl), str(csv)], "inventario": str(inv), "salida": str(TMP / "salida_prep")}); assert code == 200, o
    assert Path(o["carpeta"]).name.startswith("preparados_") and o["fusion"]["conflictos"] >= 1          # el CSV (2,0 mm fijo) contradice al Excel: esos días quedan vacíos, no se promedian
    import pandas as pd2
    sal = pd2.read_csv(Path(o["carpeta"]) / "precipitacion_diaria.csv"); assert (sal[sal["bandera"] == "conflicto"]["precipitacion_mm"].isna()).all() and (sal["bandera"] == "conflicto").any()
    code, g = post("/api/prep/registrar_estacion", {"preparados": o["carpeta"], "estacion": "M0001"}); assert code == 200, g
    assert g["estacion"]["id"] == "M0001" and get("/api/estaciones")["estaciones"][0]["id"] == "M0001"
    assert "/api/prep/ordenar" in get("/api/openapi.json")["paths"] and "Premódulo" in get("/api/ia").decode("utf-8")
    assert post("/api/prep/escanear", {"carpeta": str(TMP / "no_existe")})[0] == 400


def test_actividad_en_vivo_y_series_por_api():
    c = demo.crear_sintetico(TMP / "sint_act"); post("/api/proyecto/abrir", {"ruta": str(c)})
    n0 = get("/api/actividad?desde=0")["ultimo"]
    code, j = post("/api/actividad/narrar", {"mensaje": "Estoy revisando la lluvia", "modulo": "series", "nivel": "ok"}); assert code == 200
    a = get("/api/actividad?desde=" + str(n0)); assert any(e["titulo"] == "Estoy revisando la lluvia" and e["origen"] in ("IA / API", "interfaz") and e["modulo"] == "series" for e in a["eventos"])
    assert any("Abrió" in e["titulo"] for e in get("/api/actividad?desde=0")["eventos"])                           # las acciones POST aparecen solas
    s = get("/api/series/catalogo"); assert s["series"] == []                                                       # un proyecto sin datos descargados: lista vacía, no error
    try:
        get("/api/series/lluvia?id=chirps:media_caja_mm"); raise SystemExit("sin CHIRPS debía fallar")
    except urllib.error.HTTPError as e:
        assert e.code in (400, 404)
    assert "/api/actividad/narrar" in get("/api/openapi.json")["paths"] and "/api/series/caudal" in get("/api/openapi.json")["paths"]
    html = get("/").decode("utf-8"); assert "actividad.js" in html and "series.js" in html


def test_escenarios_de_idf_fantasmas_y_comparacion():
    import numpy as np, pandas as pd
    c = demo.crear_sintetico(TMP / "sint_esc"); post("/api/proyecto/abrir", {"ruta": str(c)})
    e = get("/api/escenarios/idf"); d = {x["id"]: x for x in e["escenarios"]}
    assert d["directa"]["factor"] == 1.0 and d["directa"]["rol"] == "principal" and "M0037" in d["directa"]["nombre"] and 200 < d["directa"]["p24_mm"] < 250          # IDF oficial de la estación del PROYECTO (M0037), Tr 100
    assert d["observado"].get("no_disponible") and "estación" in d["observado"]["no_disponible"]                                            # sin estación observada no se inventa el ajuste
    assert post("/api/corrida/iniciar", {"escenario": "observado"})[0] == 400 and post("/api/corrida/iniciar", {"escenario": "inventado"})[0] == 400
    # con una estación observada registrada, el escenario «observado» sale del Gumbel de SUS máximos anuales (no de un valor puesto a mano)
    ts = pd.date_range("1981-01-01", "2015-12-31"); rng = np.random.default_rng(5)
    mm = np.where(rng.random(len(ts)) < 0.3, rng.gamma(0.9, 9, len(ts)), 0.0)
    csvp = TMP / "m0037.csv"; pd.DataFrame({"fecha": ts.strftime("%Y-%m-%d"), "mm": mm}).to_csv(csvp, index=False)
    assert post("/api/estaciones/importar", {"archivo": str(csvp), "id": "M0037", "col_fecha": "fecha", "col_lluvia": "mm", "x": 500300, "y": 9760300, "zona_horaria": "UTC", "dayfirst": False})[0] == 200
    d = {x["id"]: x for x in get("/api/escenarios/idf")["escenarios"]}
    assert d["observado"]["factor"] > 0 and d["observado"]["n_anios"] >= 30 and abs(d["observado"]["p24_mm"] - d["observado"]["gumbel_24h_mm"]) < 0.2   # la IDF reescalada reproduce el Gumbel observado en 24 h
    code, j = post("/api/corrida/iniciar", {"escenario": "directa"}); assert code == 200 and j["escenario"]["id"] == "directa", j
    rid = j["id"]
    for _ in range(240):
        s = get("/api/corrida/estado?id=" + rid)
        if s["estado"] != "en_curso": break
        time.sleep(1)
    assert s["estado"] == "completado" and s["escenario_id"] == "directa", s
    h = get("/api/corrida/hietograma?id=" + rid); assert h["escenario"]["id"] == "directa" and len(h["lluvia_mm"]) > 10 and h["fin_s"][-1] >= 2 * 3600 - 1
    cap = get("/api/visor/capa?id=" + rid + "&capa=hmax"); assert cap["nx"] * cap["ny"] == len(cap["v"]) == 3600 and cap["escenario"]["id"] == "directa"           # capa ligera para dibujar fantasmas
    assert get("/api/visor/datos?id=" + rid)["escenario"]["id"] == "directa"
    spec = get("/api/openapi.json")["paths"]; assert "/api/escenarios/idf" in spec and "/api/visor/capa" in spec


def test_servidor_mcp_para_ia_de_escritorio_y_vscode():
    import subprocess, os, sys
    from uceclima.ui import ia_config
    env = {**os.environ, "UCEclima_URL": BASE, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    p = subprocess.Popen([sys.executable, "-m", "uceclima.mcp_servidor"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
    def rpc(i, m, params=None):
        msg = {"jsonrpc": "2.0", "id": i, "method": m}
        if params is not None: msg["params"] = params
        p.stdin.write(json.dumps(msg) + "\n"); p.stdin.flush(); return json.loads(p.stdout.readline())
    try:
        r = rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})["result"]
        assert r["serverInfo"]["name"] == "uceclima" and "CMIP6" in r["instructions"] and "calibrados" in r["instructions"]
        nombres = {x["name"] for x in rpc(2, "tools/list")["result"]["tools"]}
        assert len(nombres) >= 30 and {"estado", "narrar", "correr", "cmip6_evaluar", "bd_consulta", "ordenar_datos", "crear_proyecto_desde_sitio", "lanzar_uceclima"} <= nombres
        c = _demo(); post("/api/proyecto/abrir", {"ruta": str(c)})
        e = rpc(3, "tools/call", {"name": "estado", "arguments": {}})["result"]; assert not e["isError"] and json.loads(e["content"][0]["text"])["proyecto"]["tipo"] == "sintetico"
        n0 = get("/api/actividad?desde=0")["ultimo"]
        assert not rpc(4, "tools/call", {"name": "narrar", "arguments": {"mensaje": "Hola desde la IA por MCP", "modulo": "series"}})["result"]["isError"]
        assert any(x["titulo"] == "Hola desde la IA por MCP" and x["origen"] == "IA / API" for x in get("/api/actividad?desde=" + str(n0))["eventos"])
        a = rpc(5, "tools/call", {"name": "cmip6_asumir_baseline", "arguments": {"confirmo_usuario": False}})["result"]; assert a["isError"] and "usuario" in a["content"][0]["text"]       # nunca asume la línea base por su cuenta
        assert rpc(6, "tools/call", {"name": "bd_consulta", "arguments": {"sql": "DROP TABLE x"}})["result"]["isError"]
        assert rpc(7, "tools/call", {"name": "resultado_corrida", "arguments": {}})["result"]["isError"]                                                                              # falta un parámetro obligatorio
        assert "error" in rpc(8, "metodo/inexistente")
    finally:
        p.stdin.close(); p.wait(timeout=10)
    # configuración para Claude Desktop, Claude Code y VS Code: fusiona sin borrar y deja copia .bak
    carpeta = TMP / "ws_ia"; (carpeta / ".vscode").mkdir(parents=True)
    (carpeta / ".vscode" / "mcp.json").write_text(json.dumps({"servers": {"otro": {"command": "x"}}, "inputs": []}), encoding="utf-8")
    os.environ["APPDATA"] = str(TMP / "appdata"); (TMP / "appdata" / "Claude").mkdir(parents=True)
    (TMP / "appdata" / "Claude" / "claude_desktop_config.json").write_text(json.dumps({"mcpServers": {"previo": {"command": "y"}}, "theme": "dark"}), encoding="utf-8")
    for d in ("vscode", "claude_code", "claude_desktop"):
        ia_config.instalar(d, str(carpeta))
    v = json.loads((carpeta / ".vscode" / "mcp.json").read_text(encoding="utf-8")); assert "otro" in v["servers"] and v["servers"]["uceclima"]["type"] == "stdio" and v["inputs"] == [] and list((carpeta / ".vscode").glob("mcp.json.*.bak"))
    cd = json.loads((TMP / "appdata" / "Claude" / "claude_desktop_config.json").read_text(encoding="utf-8")); assert "previo" in cd["mcpServers"] and "uceclima" in cd["mcpServers"] and cd["theme"] == "dark"
    assert json.loads((carpeta / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["uceclima"]["args"][-1] == "uceclima.mcp_servidor"
    st = get("/api/ia/config?carpeta=" + str(carpeta)); assert st["vscode"]["instalado"] and st["claude_code"]["instalado"]
    assert post("/api/ia/instalar", {"destino": "nada"})[0] == 400


def test_rutas_windows_en_js():
    # las rutas que devuelve el servidor en Windows usan «\»: partirlas solo por «/» rompe los enlaces a productos (31-oct-2026)
    for f in (Path(SV.__file__).parent / "static").glob("*.js"):
        assert "carpeta.split(/[\\/]/)" not in f.read_text(encoding="utf-8-sig"), f.name


def test_encuesta_reenvia_si_cambia_la_direccion():
    # cada marca recuerda a qué Apps Script se envió: si la encuesta cambia de dirección, se vuelve a enviar (31-oct-2026)
    js = (Path(SV.__file__).parent / "static" / "validacion" / "encuesta.js").read_text(encoding="utf-8-sig")
    assert "m.enviado = DATA.endpoint" in js and "m.enviado = true" not in js and "!m.enviado)" not in js


if __name__ == "__main__":
    fallos = 0
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            try:
                f(); print("OK   ", name)
            except BaseException as e:
                fallos += 1; print("FALLA", name, "->", repr(e)); traceback.print_exc(limit=4)
    SRV.shutdown(); shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fallos else 0)
