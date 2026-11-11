# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Gamma · el λ (Ia/S) calibrado en hidro viaja con el CN a la corrida 2D (antes la 2D usaba siempre λ 0,20).
Caso real que lo destapó: Chalpi (EPMAPS), CN 55 + λ 0,05 calibrados, IDF Tr100 3 h = 35,6 mm → con λ 0,20 la 2D daba escorrentía 0.
Ejecutar: python -m uceclima.tests.test_gamma_lambda  (desde UCEclima)"""
import json, shutil, sys, tempfile, threading, time, traceback, urllib.request, urllib.error
from pathlib import Path
from climanet.hydrology import excess_scs
from uceclima.ui import servidor as SV, demo

TMP = Path(tempfile.mkdtemp(prefix="uceclima_gamma_"))
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


def test_nucleo_lambda_cambia_la_escorrentia():
    q20, q05 = float(excess_scs(35.6, 55.0)), float(excess_scs(35.6, 55.0, 0.05))
    assert q20 == 0.0 and 2.5 < q05 < 3.0, (q20, q05)                                    # Ia 41,6 mm > P con λ 0,20; ≈ 2,7 mm con λ 0,05


def test_cn_calibrado_lleva_su_lambda_a_la_2d():
    c = demo.crear_sintetico(TMP / "sint"); assert post("/api/proyecto/abrir", {"ruta": str(c)})[0] == 200
    acc = c / "calibracion" / "aceptadas" / "aceptada_20260101_000000"; acc.mkdir(parents=True)
    (acc / "aceptacion.json").write_text(json.dumps({"persona": "prueba", "combinacion": {"id": 0, "CN": 55.0, "lag_h": 6.0, "PRF": 484.0, "lambda": 0.05}}), encoding="utf-8")
    assert post("/api/config", {"modulo": "corrida", "valores": {"cn_fuente": "calibrado"}})[0] == 200
    code, j = post("/api/corrida/iniciar"); assert code == 200, j
    for _ in range(240):
        e = get("/api/corrida/estado?id=" + j["id"])
        if e["estado"] != "en_curso": break
        time.sleep(1)
    assert e["estado"] == "completado", e
    ent = json.loads((c / "resultados" / j["id"] / "entrada.json").read_text(encoding="utf-8"))["config"]
    rs = get("/api/corrida/resultado?id=" + j["id"])["resumen"]
    assert ent["ia_ratio"] == 0.05 and ent["cn_default"] == 55.0 and "cn_tif" not in ent
    assert rs["ia_ratio"] == 0.05 and "λ 0.05" in rs["cn_origen"], rs.get("cn_origen")


def test_sin_calibracion_sigue_lambda_020():
    c = demo.crear_sintetico(TMP / "sint2"); post("/api/proyecto/abrir", {"ruta": str(c)})
    code, j = post("/api/corrida/iniciar"); assert code == 200, j
    for _ in range(240):
        e = get("/api/corrida/estado?id=" + j["id"])
        if e["estado"] != "en_curso": break
        time.sleep(1)
    assert get("/api/corrida/resultado?id=" + j["id"])["resumen"]["ia_ratio"] == 0.2


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
