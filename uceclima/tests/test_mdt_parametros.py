# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""MDT descargado con el botón suelto se registra (antes no) y CN/Manning propios desde la PC. Sin red.
Ejecutar: python -m uceclima.tests.test_mdt_parametros"""
import json, shutil, sys, tempfile, threading, traceback, urllib.request, urllib.error
from pathlib import Path
import numpy as np

import uceclima
from uceclima.ui import servidor as SV, sitio_api

TMP = Path(tempfile.mkdtemp(prefix="uceclima_mdt_"))
SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{SV.ESTADO.puerto}"


def post(r, c):
    q = urllib.request.Request(B + r, data=json.dumps(c).encode(), method="POST", headers={"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token})
    try:
        with urllib.request.urlopen(q, timeout=120) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())


def _tif(ruta, valor, crs="EPSG:32717", x0=756000.0, y0=9720000.0, n=400, res=30.0, ruido=True):
    import rasterio
    from rasterio.transform import from_origin
    a = np.full((n, n), valor, dtype="float32")
    if ruido:
        a = a + np.add.outer(np.arange(n), np.arange(n)).astype("float32")
    with rasterio.open(ruta, "w", driver="GTiff", height=n, width=n, count=1, dtype="float32", crs=crs, transform=from_origin(x0, y0, res, res)) as d:
        d.write(a, 1)
    return ruta


def _proyecto_sin_mdt(nombre):
    car = sitio_api.crear(nombre, -78.645, -2.585, base=str(TMP))
    c, r = post("/api/proyecto/abrir", {"ruta": str(car)}); assert c == 200, r
    return Path(car)


def test_mdt_suelto_se_registra_al_terminar():
    car = _proyecto_sin_mdt("mdt suelto")
    d = car / "datos_descargados" / "mdt_20260101_000000"; d.mkdir(parents=True)
    _tif(d / "mdt_glo30_12km_utm32717.tif", 2000.0)
    man = {"fuente_id": "mdt", "parametros": {"lon": -78.645, "lat": -2.585}}
    sitio_api.registrar_mdt(SV.ESTADO)(d, man)                                       # antes no hacía nada (esperaba «pasos» y subcarpeta mdt/)
    _, cfg = SV.ESTADO.cfg(); assert cfg.get("dem") and cfg.get("aoi"), cfg


def test_cn_manning_registra_solo_el_mdt_ya_descargado():
    car = _proyecto_sin_mdt("mdt pendiente")
    d = car / "datos_descargados" / "mdt_20260101_000000"; d.mkdir(parents=True)
    _tif(d / "mdt.tif", 2000.0)
    (d / "estado.json").write_text(json.dumps({"estado": "completado"}), encoding="utf-8")
    (d / "manifiesto.json").write_text(json.dumps({"fuente_id": "mdt", "parametros": {"lon": -78.645, "lat": -2.585}}), encoding="utf-8")
    assert sitio_api.registrar_mdt_descargado(SV.ESTADO) == d.name
    _, cfg = SV.ESTADO.cfg(); assert cfg.get("dem")
    assert sitio_api.registrar_mdt_descargado(SV.ESTADO) is None                       # ya registrado: no lo reemplaza


def test_cn_manning_propios_validan_y_tienen_prioridad():
    car = _proyecto_sin_mdt("propios")
    cn = _tif(TMP / "cn.tif", 70.0, ruido=False); mn = _tif(TMP / "mn.tif", 0.05, ruido=False); malo = _tif(TMP / "cn_malo.tif", 250.0, ruido=False)
    c, r = post("/api/parametros/propios", {"cn": str(cn), "manning": str(mn), "fuente": ""}); assert c == 400            # sin fuente no
    c, r = post("/api/parametros/propios", {"cn": str(malo), "manning": str(mn), "fuente": "Prueba"}); assert c == 400 and "rango" in r["error"]
    c, r = post("/api/parametros/propios", {"cn": str(cn), "manning": str(mn), "fuente": "Estudio X 2024"}); assert c == 200, r
    _, cfg = SV.ESTADO.cfg(); assert cfg["cn_origen"] == "usuario" and (car / cfg["cn_tif"]).exists()
    assert list(car.glob("config_climanet.json.*.bak"))
    from uceclima import parametros_gee as PG
    d = car / "datos_descargados" / "cn_manning_x"; d.mkdir(parents=True)
    assert PG.registrar(car, d, {})["estado"] == "conservado_usuario"                  # los de GEE no pisan los propios


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
