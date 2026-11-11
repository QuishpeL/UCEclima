# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Capturas de pantalla reproducibles con Edge/Chrome sin cabeza: python -m uceclima.ui.capturas [puerto] [sufijo]. Requiere el servidor en marcha y un proyecto abierto."""
import subprocess, sys
from pathlib import Path
from .lanzar import navegador

RUTAS = ["preparacion", "proyecto", "gee", "chirps", "idf", "terreno", "cuencas", "corrida", "evaluacion", "hidrologia", "cmip6", "entregas"]
SALIDA = Path(__file__).parent / "capturas"


def capturar(puerto=8765, sufijo="", tam=(1360, 900), rutas=RUTAS, espera_ms=9000):
    exe = navegador(); SALIDA.mkdir(exist_ok=True); hechas = []
    perfil = Path(__import__("os").environ.get("TEMP", ".")) / "uceclima_perfil_captura"
    for r in rutas:
        out = SALIDA / f"{r}{sufijo}.png"
        subprocess.run([exe, "--headless=new", f"--screenshot={out}", f"--window-size={tam[0]},{tam[1]}", f"--user-data-dir={perfil}", "--hide-scrollbars",
                        f"--virtual-time-budget={espera_ms}", "--no-first-run", f"http://127.0.0.1:{puerto}/#/{r}"], capture_output=True, timeout=120)
        hechas.append(out)
    return hechas


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    suf = sys.argv[2] if len(sys.argv) > 2 else ""
    tam = (480, 900) if suf == "_estrecha" else (1360, 900)
    for f in capturar(p, suf, tam): print(f, f.exists() and f.stat().st_size)
