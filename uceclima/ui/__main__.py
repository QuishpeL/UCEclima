# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
import argparse
from .servidor import main
ap = argparse.ArgumentParser(description="Interfaz local de UCEclima")
ap.add_argument("--puerto", type=int, default=8765); ap.add_argument("--sin-ventana", action="store_true")
a = ap.parse_args(); main(a.puerto, abrir=not a.sin_ventana)
