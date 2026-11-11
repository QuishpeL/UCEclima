# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Gamma · película del calado en el visor 3D: el núcleo guarda fotos del calado en el tiempo (evolucion_calado.npz), la API las entrega
y el visor las reproduce, más lento en la crecida. Las fotos son lo que el solver tuvo en ese instante; no alteran el cálculo.
Ejecutar: python -m uceclima.tests.test_gamma_visor  (desde UCEclima)"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, traceback, urllib.request, urllib.error
from pathlib import Path
import numpy as np
from climanet.hydraulics import simulate, Options
from uceclima.ui import servidor as SV, demo

TMP = Path(tempfile.mkdtemp(prefix="uceclima_gvisor_"))
SRV = SV.crear_servidor(0); threading.Thread(target=SRV.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{SV.ESTADO.puerto}"
H = {"Content-Type": "application/json", "X-UCECLIMA-TOKEN": SV.ESTADO.token}


def post(r, c=None):
    q = urllib.request.Request(B + r, data=json.dumps(c or {}).encode(), method="POST", headers=H)
    try:
        with urllib.request.urlopen(q, timeout=120) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())


def get(r):
    try:
        with urllib.request.urlopen(urllib.request.Request(B + r, headers=H), timeout=120) as x: return json.loads(x.read())
    except urllib.error.HTTPError as e: return {"_code": e.code, **json.loads(e.read())}


def test_fotos_no_alteran_el_calculo():
    z = np.add.outer(np.linspace(5, 0, 20), np.linspace(1, 0, 20)); act = np.ones_like(z, bool); n = np.full_like(z, 0.05)
    ed = np.array([0., 600.]); ro = np.full((1, 20, 20), 20.)
    a = simulate(z, act, n, ed, ro, Options(10, 10, 1800, boundary="free_outflow"))
    b = simulate(z, act, n, ed, ro, Options(10, 10, 1800, boundary="free_outflow", frame_interval=300))
    assert np.array_equal(a["hmax"], b["hmax"]) and a["resumen"]["volumen_salida_m3"] == b["resumen"]["volumen_salida_m3"]
    t = b["fotos"]["t_s"]; assert t[0] == 0 and abs(t[-1] - 1800) < 1e-6 and len(t) == 7 and not a["fotos"]["t_s"]
    assert np.allclose(b["fotos"]["h"][-1], b["hfinal"], atol=1e-2)                   # la última foto es el estado final (float16)


def test_corrida_guarda_pelicula_y_el_visor_la_reproduce():
    c = demo.crear_sintetico(TMP / "sint"); assert post("/api/proyecto/abrir", {"ruta": str(c)})[0] == 200
    code, j = post("/api/corrida/iniciar"); assert code == 200, j
    for _ in range(240):
        e = get("/api/corrida/estado?id=" + j["id"])
        if e["estado"] != "en_curso": break
        time.sleep(1)
    assert e["estado"] == "completado", e
    assert next(iter((c / "resultados" / j["id"]).rglob("evolucion_calado.npz")), None)
    f = get("/api/visor/fotos?id=" + j["id"]); d = get("/api/visor/datos?id=" + j["id"])
    assert f["nx"] == d["nx"] and f["ny"] == d["ny"] and len(f["t_s"]) >= 5 and len(f["h_mm"]) == len(f["t_s"])
    assert all(len(r) == len(f["idx"]) for r in f["h_mm"]) and max(f["volumen_m3"]) > 0 and f["t_s"][0] == 0
    hmax_mm = max(max(r) for r in f["h_mm"]) / 1000; assert abs(hmax_mm - max(v for v in d["capas"]["hmax"] if v)) < 0.05   # fotos ≤ máximo real
    assert get("/api/visor/fotos?id=NO_EXISTE").get("_code") == 400
    chrome = next((q for q in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe") if os.path.exists(q)), None)
    if chrome:
        out = subprocess.run([chrome, "--headless=new", "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist", "--virtual-time-budget=15000", "--dump-dom", B + "/visor?id=" + j["id"]],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180).stdout
        assert 'id="tiempoBox" hidden' not in out and "Evolución en el tiempo" in out and ">4 h 00 min<" in out, out[-1500:]


def test_corrida_anterior_sin_pelicula_avisa():
    c = demo.crear_sintetico(TMP / "sint2"); post("/api/proyecto/abrir", {"ruta": str(c)})
    run = c / "resultados" / "corrida_20000101_000000_vieja"; run.mkdir(parents=True)
    r = get("/api/visor/fotos?id=corrida_20000101_000000_vieja"); assert r.get("_code") == 400 and "anterior a Gamma" in r["error"]


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
