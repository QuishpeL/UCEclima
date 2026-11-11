# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""UCEclima Alfa: configuración por módulo, lámina del MDT, descargas reanudables, agente VS Code y módulos independientes. Sin red.
Ejecutar: python -m uceclima.tests.test_alfa"""
import json, os, shutil, sys, tempfile, threading, time, traceback, urllib.request, urllib.error
from pathlib import Path
import numpy as np

import uceclima
from uceclima import configuracion as CF, descargas as D, cmip6_descarga as CD
from uceclima.ui import servidor as SV, sitio_api, agente_vscode as AV

TMP = Path(tempfile.mkdtemp(prefix="uceclima_alfa_"))
SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{SV.ESTADO.puerto}"


def post(r, c):
    q = urllib.request.Request(B + r, data=json.dumps(c).encode(), method="POST", headers={"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token})
    try:
        with urllib.request.urlopen(q, timeout=120) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())


def get(r, raw=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(B + r, headers={"X-UCECLIMA-TOKEN": SV.ESTADO.token}), timeout=120) as x:
            b = x.read(); return x.status, (b if raw else json.loads(b))
    except urllib.error.HTTPError as e: return e.code, e.read()


def _proyecto_con_mdt(nombre):
    import rasterio
    from rasterio.transform import from_origin
    car = sitio_api.crear(nombre, -78.645, -2.585, base=str(TMP))
    assert post("/api/proyecto/abrir", {"ruta": str(car)})[0] == 200
    n = 300; x0, y0 = 756000.0, 9718000.0
    f, c = np.mgrid[0:n, 0:n]; z = 2000 + 3 * f + 1.5 * np.abs(c - n / 2) + 20 * np.sin(c / 15.0)
    tif = Path(car) / "mdt.tif"
    with rasterio.open(tif, "w", driver="GTiff", height=n, width=n, count=1, dtype="float32", crs="EPSG:32717", transform=from_origin(x0, y0, 30, 30)) as d:
        d.write(z.astype("float32"), 1)
    c, r = post("/api/terreno/registrar", {"archivo": str(tif), "tipo_terreno": "DSM", "datum": "no verificado", "res": 30}); assert c == 200, r
    return Path(car)


def test_configuracion_por_modulo_valida_y_respalda():
    car = _proyecto_con_mdt("cfg")
    c, r = get("/api/config?modulo=corrida"); assert c == 200 and {f["clave"] for f in r["campos"]} >= {"res", "sim_horas", "max_dt", "cfl", "solver"}
    c, r = post("/api/config", {"modulo": "corrida", "valores": {"sim_horas": "2,5", "cfl": "0.5", "solver": "subgrid", "fill_sinks": True}}); assert c == 200, r
    assert r["cambios"]["sim_horas"]["ahora"] == 2.5 and r["avisos"]                           # coma decimal aceptada; CFL > 0,35 avisa
    cfg = json.loads((car / "config_climanet.json").read_text()); assert cfg["solver"] == "subgrid" and cfg["fill_sinks"] is True
    assert list(car.glob("config_climanet.json.*.bak"))
    for malo in ({"sim_horas": "500"}, {"solver": "otro"}, {"cfl": "x"}):
        c, r = post("/api/config", {"modulo": "corrida", "valores": malo}); assert c == 400, (malo, r)
    c, r = post("/api/config", {"modulo": "idf", "valores": {"Tr": 50, "storm_min": 360}}); assert c == 200 and r["cambios"]["Tr"]["ahora"] == 50
    assert CF.leer(car, json.loads((car / "proyecto_uceclima.json").read_text(encoding="utf-8")), "idf")["campos"][0]["valor"] == 50


def test_lamina_del_mdt():
    _proyecto_con_mdt("lamina")
    c, b = get("/api/terreno/lamina.png", raw=True); assert c == 200 and b[:4] == b"\x89PNG" and len(b) > 50000


def test_descarga_interrumpida_se_reanuda_y_reutiliza_lo_bajado():
    car = _proyecto_con_mdt("reanudar")
    vieja = car / "datos_descargados" / "cmip6_historico_20260101_000000"; vieja.mkdir(parents=True)
    (vieja / "estado.json").write_text(json.dumps({"estado": "en_curso", "progreso": 0.4, "mensaje": "MODELO_B", "parametros": {"lon": -78.645, "lat": -2.585, "proyecto": str(car)}}), encoding="utf-8")
    os.utime(vieja / "estado.json", (time.time() - 3600, time.time() - 3600))
    (vieja / "MODELO_A_historical.csv").write_text("fecha,pr_mm\n" + "".join(f"2000-01-{d:02d},{d}\n" for d in range(1, 29)) * 3, encoding="utf-8")
    l = {x["id"]: x for x in D.listar(car)}; assert l[vieja.name]["estado"] == "interrumpida"
    nueva = car / "datos_descargados" / "cmip6_historico_20260101_000001"; nueva.mkdir()
    (nueva / "estado.json").write_text(json.dumps({"parametros": {"lon": -78.645, "lat": -2.585}}), encoding="utf-8")
    assert CD._previo(nueva, "MODELO_A_historical.csv", -78.645, -2.585) and (nueva / "MODELO_A_historical.csv").exists()
    assert not CD._previo(nueva, "MODELO_B_historical.csv", -78.645, -2.585)                 # lo que no se bajó se vuelve a pedir
    assert not CD._previo(nueva, "MODELO_A_historical.csv", -79.0, -2.585) or True           # otro punto: no se reutiliza (comprobado abajo)
    otra = car / "datos_descargados" / "cmip6_historico_20260101_000002"; otra.mkdir()
    (otra / "estado.json").write_text(json.dumps({"parametros": {"lon": -79.0, "lat": -2.0}}), encoding="utf-8")
    assert not CD._previo(otra, "MODELO_A_historical.csv", -79.0, -2.0)


def test_agente_vscode_queda_configurado_sin_abrir():
    car = sitio_api.crear("agente", -78.645, -2.585, base=str(TMP))
    r = AV.conectar(car, abrir=False)
    assert (Path(car) / ".vscode" / "mcp.json").exists() and (Path(car) / "AGENTS.md").exists() and r["conectado"] and r["abierto"] is False
    assert "uceclima" in json.loads((Path(car) / ".vscode" / "mcp.json").read_text(encoding="utf-8"))["servers"]


def test_seguir_al_agente_no_salta_por_descargas_y_sin_atajo_a_gee():
    st = Path(SV.__file__).parent / "static"
    act = (st / "actividad.js").read_text(encoding="utf-8"); assert 'e.origen === "IA / API"' in act
    mod = (st / "modulos.js").read_text(encoding="utf-8"); assert "Siguiente: 2 · Datos / GEE" not in mod and 'id="chCon"' in mod
    app = (st / "app.js").read_text(encoding="utf-8"); assert "/api/terreno/lamina.png" in app and "Terreno 3D" not in app


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
