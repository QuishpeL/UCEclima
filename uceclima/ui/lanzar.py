# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Abre la interfaz en una ventana tipo aplicación (Edge o Chrome en modo --app) o, si no hay, en el navegador predeterminado."""
import os, subprocess, webbrowser
from pathlib import Path

CANDIDATOS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]


def navegador():
    return next((c for c in CANDIDATOS if Path(c).exists()), None)


PERFIL = Path(os.environ.get("TEMP", ".")) / "uceclima_perfil_ventana"


def ventana_abierta():
    """Eta: ¿sigue abierta la ventana de UCEclima? Edge/Chrome mantienen bloqueado el archivo «lockfile» de su perfil mientras la ventana
    vive. Devuelve True (abierta), False (cerrada) o None (no se sabe: se abrió en el navegador predeterminado)."""
    if not navegador():
        return None
    lf = PERFIL / "lockfile"
    if not lf.exists():
        return False
    try:
        with open(lf, "a"):
            return False                     # se pudo abrir: nadie lo tiene bloqueado, la ventana se cerró
    except OSError:
        return True


def abrir_ventana(url, ancho=1360, alto=880):
    exe = navegador()
    if exe:
        perfil = PERFIL
        subprocess.Popen([exe, f"--app={url}", f"--window-size={ancho},{alto}", f"--user-data-dir={perfil}", "--no-first-run", "--disable-extensions"])
    else:
        webbrowser.open(url)
