# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Pruebas del módulo 12 · Validación de campo (Zeta, 31-oct-2026) con un proyecto sintético de resultado conocido. No corre el modelo."""
import csv, json, re, shutil, subprocess, tempfile
from pathlib import Path

import numpy as np, rasterio
from rasterio.transform import from_origin
from pyproj import Transformer

from uceclima import validacion_campo as VC

TMP = Path(tempfile.mkdtemp(prefix="uce_campo_"))
VC.CONEXION = TMP / "conexion_prueba.json"                   # nunca toca la hoja conectada de la persona
X0, Y0, RES = 650000.0, 9760000.0, 30.0                       # UTM 17S (Milagro aprox.)
A_LL = Transformer.from_crs(32717, 4326, always_xy=True).transform


def _proyecto(nombre="Barrio Prueba"):
    p = TMP / nombre.replace(" ", "_"); h = np.zeros((40, 40), dtype="float32")
    h[10:20, 10:20] = 0.8                                    # zona mojada 0,8 m (filas 10–19, columnas 10–19)
    h[25, 25] = 0.03                                         # charco bajo el umbral del modelo
    for run, esc, fac, tr in (("corrida_20261027_205716_real", "Tr100_diseno_idf_historica", 1.0, 100),
                              ("corrida_20261029_012305_real_cc_ssp585_2071-2100_mediana", "Tr100_diseno_idf_historica", 1.3, 100)):
        d = p / "resultados" / run / "salida" / esc; d.mkdir(parents=True)
        with rasterio.open(d / "hmax.tif", "w", driver="GTiff", height=40, width=40, count=1, dtype="float32", crs="EPSG:32717", transform=from_origin(X0, Y0, RES, RES), nodata=-9999) as w:
            w.write(h * fac, 1)
        (d / "resumen.json").write_text(json.dumps({"Tr": tr, "P_total_mm": 224.9 * fac, "factor_cc": fac, "area_ge_0.5_km2": 0.09}), encoding="utf-8")
    return p


def _ll(fila, col):
    return A_LL(X0 + (col + 0.5) * RES, Y0 - (fila + 0.5) * RES)


def test_encuesta_html_autocontenida_capas_x_y_y_registro():
    p = _proyecto()
    cs = VC.corridas(p); assert len(cs) == 2 and [c["Y"] for c in cs] == [False, True] and cs[1]["horizonte"] == "2071-2100"
    try:
        VC.generar_encuesta(p, endpoint="https://ejemplo.com/robar"); raise AssertionError("endpoint ajeno debió rechazarse")
    except VC.CampoError as e:
        assert "Apps Script" in str(e)
    url = "https://script.google.com/macros/s/AKfyc_prueba-123/exec"
    r = VC.generar_encuesta(p, zona="Barrio Prueba", endpoint=url + "?form=hogares")
    assert r["slug"] == "barrio-prueba" and r["form"] == "validacion_barrio_prueba" and r["registro_en_linea"] and len(r["capas"]) == 2
    assert r["capas"][0].startswith("X ·") and r["capas"][1].startswith("Y · cambio climático 2071-2100") and "enlace" not in r   # sin hoja conectada no se publica
    html = Path(r["html"]).read_text(encoding="utf-8")
    assert "Leaflet 1.9.4" in html and "/*DATA*/" not in html and "/*ENCUESTA_JS*/" not in html and "uceclima-validacion-campo-2.0" in html
    assert "perdida_usd" in html and "Sistema de alerta temprana" in html and "Early warning system" in html             # preguntas completas, en español e inglés
    datos = json.loads(re.search(r"window\.DATA = (\{.*?\});</script>", html, re.S).group(1).replace("<\\/", "</"))
    assert datos["endpoint"] == url and len(datos["capas"]) == 2 and datos["capas"][0]["png"][:8] == "iVBORw0K"     # PNG en base64
    (s, o), (n, e) = datos["capas"][0]["b"]; lon, lat = _ll(15, 15); assert o < lon < e and s < lat < n           # la capa cubre la zona mojada
    assert "no está calibrado" in datos["aviso"] and "nombre" not in json.dumps(datos).lower().replace("nombre del grupo", "")
    pub = Path(r["publicar"]) / "validacion" / "barrio-prueba" / "index.html"; assert pub.read_text(encoding="utf-8") == html
    gs = (Path(r["carpeta"]) / "apps_script_registro.gs").read_text(encoding="utf-8")
    assert gs.count("function doPost") == 1 and "{{CLAVE}}" in gs and "COMPLETO" in (Path(r["carpeta"]) / "LEEME.txt").read_text(encoding="utf-8")   # la plantilla no lleva clave de nadie
    sin = VC.generar_encuesta(p, zona="Barrio Prueba"); assert not sin["registro_en_linea"] and sin["carpeta"] != r["carpeta"]   # nada se sobrescribe
    uno = VC.generar_encuesta(p, zona="Barrio Prueba", base="corrida_20261027_205716_real")                       # «un clic» desde la corrida X: X + sus Y del mismo Tr
    assert uno["corridas"] == ["corrida_20261027_205716_real", "corrida_20261029_012305_real_cc_ssp585_2071-2100_mediana"]
    soloy = VC.generar_encuesta(p, base="corrida_20261029_012305_real_cc_ssp585_2071-2100_mediana"); assert len(soloy["capas"]) == 1 and soloy["capas"][0].startswith("Y")
    node = shutil.which("node")
    if node:                                                                                                       # el JS de la encuesta es válido
        assert subprocess.run([node, "--check", str(VC.PLANT / "encuesta.js")], capture_output=True).returncode == 0


def test_importar_geojson_y_csv_y_contrastar_con_resultado_conocido():
    p = _proyecto("Contraste")
    f = lambda fila, col, res, **kw: {"type": "Feature", "properties": {"id_marca": f"m{fila}_{col}", "resultado": res, **kw}, "geometry": {"type": "Point", "coordinates": list(_ll(fila, col))}}
    zona = [_ll(12, 12), _ll(12, 16), _ll(16, 16), _ll(16, 12)]
    g = {"type": "FeatureCollection", "features": [
        f(15, 15, "SE INUNDA", altura_agua="Cintura (50 cm–1 m)"),           # acierto, altura coincide (0,8 m)
        f(15, 15, "SE INUNDA", altura_cm="20") | {"properties": {"id_marca": "cm", "resultado": "SE INUNDA", "altura_cm": "20"}},   # acierto, el modelo sobreestima
        f(35, 35, "SE INUNDA", altura_agua="Más de 1 metro"),                # omisión del modelo
        f(25, 25, "NO SE INUNDA"),                                          # 3 cm < 5 cm: acierto seco
        f(11, 18, "NO SE INUNDA"),                                          # falsa alarma
        {"type": "Feature", "properties": {"id_marca": "z", "resultado": "SE INUNDA", "altura_agua": "Más de 1 metro"}, "geometry": {"type": "Polygon", "coordinates": [[list(c) for c in zona + zona[:1]]]}},
        {"type": "Feature", "properties": {"id_marca": "fuera", "resultado": "SE INUNDA"}, "geometry": {"type": "Point", "coordinates": [-70.0, -10.0]}},
        {"type": "Feature", "properties": {"resultado": "quizás"}, "geometry": {"type": "Point", "coordinates": [0, 0]}}]}
    fg = TMP / "marcas_grupo.geojson"; fg.write_text(json.dumps(g), encoding="utf-8")
    r = VC.importar(p, fg); assert r["marcas"] == 7 and r["se_inunda"] == 5                                       # «quizás» se descarta
    fc = TMP / "respuestas_hoja.csv"
    with open(fc, "w", encoding="utf-8", newline="") as fh:                                                         # CSV exportado de la hoja (Apps Script)
        w = csv.DictWriter(fh, fieldnames=["id_marca", "estado", "resultado", "lat", "lon", "altura_agua", "geometria_geojson"]); w.writeheader()
        lon, lat = _ll(18, 18); w.writerow({"id_marca": "csv1", "estado": "ACTIVA", "resultado": "SE INUNDA", "lat": lat, "lon": lon, "altura_agua": "Tobillo a rodilla (10–50 cm)"})
        w.writerow({"id_marca": "csv2", "estado": "ANULADA", "resultado": "SE INUNDA", "lat": lat, "lon": lon})
        w.writerow({"id_marca": "m35_35", "estado": "ACTIVA", "resultado": "SE INUNDA", "geometria_geojson": json.dumps({"type": "Point", "coordinates": list(_ll(35, 35))}), "altura_agua": "Cintura (50 cm–1 m)"})
    r2 = VC.importar(p, fc); assert r2["marcas"] == 2                                                              # la ANULADA no entra
    assert len(VC.marcas(p)) == 8                                                                                  # m35_35 se importó dos veces: queda la última
    for malo in (TMP / "no_existe.geojson", fc.with_suffix(".txt")):
        try:
            if malo.suffix == ".txt": malo.write_text("x", encoding="utf-8")
            VC.importar(p, malo); raise AssertionError("debió fallar")
        except VC.CampoError:
            pass
    c = VC.contrastar(p)
    assert c["corrida"] == "corrida_20261027_205716_real" and c["marcas"] == 8 and c["fuera_del_dominio"] == 1
    assert (c["aciertos"], c["omisiones"], c["falsas_alarmas"], c["aciertos_secos"]) == (4, 1, 1, 1), c
    assert c["tasa_deteccion"] == 0.8 and c["indice_exito_critico"] == round(4 / 6, 2)
    fil = {x["id_marca"]: x for x in c["filas"]}
    assert fil["m15_15"]["altura"] == "coincide" and fil["cm"]["altura"] == "el modelo sobreestima" and fil["z"]["altura"] == "el modelo subestima"
    assert fil["m35_35"]["altura_declarada"].startswith("Cintura") and fil["m35_35"]["contraste"] == "omisión del modelo"
    assert fil["z"]["calado_modelo_max_m"] == 0.8 and fil["csv1"]["altura"] == "el modelo sobreestima"
    d = Path(c["carpeta"]); assert (d / "contraste_mapa.png").read_bytes()[:4] == b"\x89PNG" and (d / "contraste_marcas.csv").exists() and "no validación física" in c["nota"]
    y = VC.contrastar(p, "corrida_20261029_012305_real_cc_ssp585_2071-2100_mediana"); assert y["escenario"] == "Tr100_diseno_idf_historica" and y["aciertos"] == 4
    e = VC.estado(p); assert e["marcas"] == 8 and e["ultimo_contraste"]["corrida"].endswith("mediana") and "hmax" not in e["corridas"][0]
    L = VC.laminas(p, zona="Contraste", fondo=False)                                                               # láminas tipo Milagro, sin internet
    assert L["corrida_X"] == "corrida_20261027_205716_real" and L["marcas_en_dominio"] == 7 and L["contraste_X"]["aciertos"] == 4
    assert Path(L["lamina1"]).read_bytes()[1:4] == b"PNG" and Path(L["lamina2"]).read_bytes()[1:4] == b"PNG" and len(L["contraste_Y"]) == 1
    with rasterio.open(Path(L["carpeta"]) / "buffer_acumulado.tif") as s: acc = s.read(1); assert acc.max() > 1.0 and s.crs.to_epsg() == 32717   # marcas superpuestas suman
    L2 = VC.laminas(p, zona="Contraste", fondo=False, radio_m=500); assert L2["carpeta"] != L["carpeta"] and VC.estado(p)["ultimas_laminas"]["radio_buffer_m"] == 500
    assert not any(k.startswith("_") for k in c["filas"][0])                                                    # la tabla exportada no lleva campos internos


class _HojaFalsa:
    """Imita el Apps Script v2 (apps_script_uceclima_v2.gs) en un servidor local: publicar, leer la encuesta, guardar filas y devolver respuestas con clave."""
    def __init__(self, clave, version=2):
        import http.server, threading, urllib.parse
        hoja = self; self.clave, self.version, self.encuestas, self.pestanas = clave, version, {}, {}

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _r(self, o):
                b = json.dumps(o).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            def do_GET(self):
                q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
                if q.get("accion") == "encuesta":
                    return self._r({"ok": True, "datos": hoja.encuestas[q["z"]]} if q.get("z") in hoja.encuestas else {"ok": False, "error": "no existe"})
                if q.get("accion") == "respuestas":
                    return self._r({"ok": False, "error": "clave"} if q.get("clave") != hoja.clave else {"ok": True, "filas": hoja.pestanas.get(q.get("form"), [])})
                self._r({"ok": True, "msg": "Servidor activo", "version": hoja.version})
            def do_POST(self):
                q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query)); d = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                if q.get("accion") == "publicar":
                    if q.get("clave") != hoja.clave: return self._r({"ok": False, "error": "clave"})
                    hoja.encuestas[d["slug"]] = d; return self._r({"ok": True, "z": d["slug"]})
                hoja.pestanas.setdefault(q.get("form"), []).append(d); self._r({"ok": True})
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/exec"


def test_hoja_conectada_publica_sola_y_trae_respuestas():
    p = _proyecto("En Linea")
    c = VC.conectar("http://127.0.0.1:1/exec", "https://climalab.net/", _validar=False)
    assert c["conectada"] and "clave" not in VC.conexion() and c["sitio"] == "https://climalab.net" and c["gs"].count(json.loads(VC.CONEXION.read_text())["clave"]) == 1
    try:
        VC.conectar("https://ejemplo.com/robar"); raise AssertionError("dirección ajena debió rechazarse")
    except VC.CampoError:
        pass
    clave = json.loads(VC.CONEXION.read_text())["clave"]
    vieja = _HojaFalsa(clave, version=1); VC.conectar(vieja.url, _validar=False)
    assert json.loads(VC.CONEXION.read_text())["clave"] == clave                                                   # la clave no cambia al reconectar
    try:
        VC.probar_conexion(); raise AssertionError("el código antiguo debió detectarse")
    except VC.CampoError as e:
        assert "Nueva versión" in str(e)
    vie = VC.generar_encuesta(p, zona="Zona vieja", publicar_en_linea=False); import time; time.sleep(0.05)       # nombre alfabéticamente posterior, pero más antigua
    hoja = _HojaFalsa(clave); VC.conectar(hoja.url, _validar=False); assert VC.probar_conexion()["ok"]
    r = VC.generar_encuesta(p, zona="En Linea", idioma="en", base="corrida_20261027_205716_real")                   # un clic: se publica solo
    assert r["enlace"] == "https://climalab.net/validacion/e/?z=en-linea&lang=en" and Path(r["qr"]).read_bytes()[1:4] == b"PNG" and "wa.me" in r["whatsapp"]
    assert r["titulo"].startswith("Does it flood?") and r["capas"][0].startswith("X · current conditions") and r["capas"][1].startswith("Y · climate change")
    pub = hoja.encuestas["en-linea"]; assert pub["endpoint"] == hoja.url and pub["form"] == "validacion_en_linea" and pub["idioma"] == "en" and "not calibrated" in pub["aviso"]
    assert len(pub["capas"]) == 2 and clave not in json.dumps(pub) and clave not in Path(r["html"]).read_text(encoding="utf-8")   # la clave nunca va en la encuesta
    assert VC._http(hoja.url + "?accion=encuesta&z=en-linea")["datos"]["slug"] == "en-linea"                          # lo que lee la página del sitio
    sitio = VC.pagina_sitio(hoja.url); assert "window.DATA = null; window.ENDPOINT_DEF = " in sitio and "accion=encuesta" in sitio
    # el teléfono envía filas: una marca corregida (versión 2), una borrada, una «no se inunda» y una sin ubicación
    geo = lambda fila, col: json.dumps({"type": "Point", "coordinates": list(_ll(fila, col))})
    filas = [{"id_marca": "a", "version_marca": 1, "estado": "ACTIVA", "resultado": "SE INUNDA", "geometria_geojson": geo(15, 15), "altura_agua": "Tobillo a rodilla (10–50 cm)"},
             {"id_marca": "a", "version_marca": 2, "estado": "ACTIVA", "resultado": "SE INUNDA", "geometria_geojson": geo(15, 15), "altura_agua": "Cintura (50 cm–1 m)", "perdida_usd": "USD 500 a 2.000", "medidas": "Dragado de ríos o esteros"},
             {"id_marca": "b", "version_marca": 1, "estado": "ACTIVA", "resultado": "SE INUNDA", "geometria_geojson": geo(35, 35)},
             {"id_marca": "b", "version_marca": 2, "estado": "BORRADA", "resultado": "SE INUNDA", "geometria_geojson": geo(35, 35)},
             {"id_marca": "c", "version_marca": 1, "estado": "ACTIVA", "resultado": "NO SE INUNDA", "lat": _ll(25, 25)[1], "lon": _ll(25, 25)[0]},
             {"id_marca": "d", "version_marca": 1, "estado": "ACTIVA", "resultado": "SE INUNDA"}]
    for f in filas:
        VC._http(f"{hoja.url}?form=validacion_en_linea", f)
    s = VC.sincronizar(p, fondo=False)
    assert vie["form"] == "validacion_zona_vieja" and VC.estado(p)["encuestas"][-1]["form"] == "validacion_en_linea"   # la última es la más reciente, no la de nombre mayor
    assert (s["pestana"], s["filas"], s["marcas"], s["se_inunda"], s["borradas"]) == ("validacion_en_linea", 6, 2, 1, 1), s
    assert s["contraste"]["aciertos"] == 1 and s["contraste"]["aciertos_secos"] == 1 and Path(s["laminas"]["lamina1"]).read_bytes()[1:4] == b"PNG"
    ms = {m["properties"]["id_marca"]: m["properties"] for m in VC.marcas(p)}
    assert set(ms) == {"a", "c"} and ms["a"]["altura_agua"].startswith("Cintura") and ms["a"]["perdida_usd"] == "USD 500 a 2.000"   # queda la última versión; la borrada no cuenta
    assert VC.sincronizar(p, fondo=False, generar=False)["sin_cambios"]                                            # sin filas nuevas: no crea otro archivo
    VC._http(f"{hoja.url}?form=validacion_en_linea", {**filas[4], "version_marca": 2, "estado": "BORRADA"})
    assert VC.sincronizar(p, fondo=False, generar=False)["marcas"] == 1 and set(m["properties"]["id_marca"] for m in VC.marcas(p)) == {"a"}
    hoja.clave = "otra"
    try:
        VC.sincronizar(p, fondo=False); raise AssertionError("clave equivocada debió rechazarse")
    except VC.CampoError as e:
        assert "clave" in str(e)
    hoja.srv.shutdown(); vieja.srv.shutdown(); VC.CONEXION.unlink()


def test_sin_corridas_mensaje_claro():
    p = TMP / "vacio"; p.mkdir()
    for fn in (lambda: VC.generar_encuesta(p), lambda: VC.contrastar(p)):
        try:
            fn(); raise AssertionError("debió fallar")
        except VC.CampoError as e:
            assert "corrida" in str(e).lower()


if __name__ == "__main__":
    import sys, traceback
    ok = mal = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            try:
                v(); ok += 1; print("OK", k, flush=True)
            except Exception as e:
                mal += 1; print("FALLA", k, "->", repr(e)[:300], flush=True); traceback.print_exc()
    print(f"{ok} OK, {mal} fallos"); sys.exit(1 if mal else 0)
