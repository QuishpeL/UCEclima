# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Ejecuta todas las pruebas de UCEclima (desde la carpeta MILAGRO o desde uceclima): python uceclima\correr_pruebas_uceclima.py"""
import os, subprocess, sys
from pathlib import Path
raiz = Path(__file__).resolve().parents[1]
mods = ["idf_excel", "lluvia", "gee_chirps", "seleccion_eventos", "preparacion", "descargas", "cmip6", "cmip6_matematica", "hidrologia", "terreno_coincidencia", "flujo_nuevo", "cuenca_calibracion", "mdt_parametros", "alfa", "wrf_toe", "premodulo_masivo", "r1_agentes", "fase2_calibracion", "fase2b", "gamma_lambda", "gamma_visor", "delta", "epsilon", "zeta", "eta", "campo", "ui", "lambda"]
fallos = 0
for m in mods:
    r = subprocess.run([sys.executable, "-m", f"uceclima.tests.test_{m}"], cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    ok = sum(1 for l in r.stdout.splitlines() if l.startswith("OK")); mal = [l for l in r.stdout.splitlines() if l.startswith("FALLA")]
    fallos += len(mal) + (r.returncode != 0 and not mal)
    print(f"test_{m}: {ok} OK, {len(mal)} fallos" + ("" if not mal else "\n  " + "\n  ".join(mal)))
print("TOTAL:", "sin fallos" if not fallos else f"{fallos} fallos")
sys.exit(1 if fallos else 0)
