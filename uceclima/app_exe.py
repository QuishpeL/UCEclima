# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Punto de entrada del programa empaquetado (UCEclima.exe). Sin argumentos abre la interfaz; los otros modos son procesos auxiliares que la interfaz relanza
con el mismo ejecutable (no hay Python instalado en el equipo de destino): --worker <carpeta_corrida> y --dialogo carpeta|archivo."""
import os, sys

if sys.stdout is None:                                           # ejecutable sin consola: evita fallos al imprimir
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _dialogo(tipo):
    import tkinter as tk
    from tkinter import filedialog as f
    r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
    if tipo == "datos":
        import json
        print(json.dumps(list(f.askopenfilenames(title="Elegir archivos de datos", filetypes=[("Excel y CSV", "*.xlsx *.xlsm *.xls *.csv *.txt"), ("Todos", "*.*")]))))
    elif tipo == "vector":
        print(f.askopenfilename(title="Elegir capa", filetypes=[("Capas vectoriales", "*.shp *.gpkg *.geojson *.json *.kml"), ("Todos", "*.*")]))
    elif tipo == "raster":
        print(f.askopenfilename(title="Elegir ráster", filetypes=[("GeoTIFF", "*.tif *.tiff"), ("Todos", "*.*")]))
    elif tipo == "tabla":
        print(f.askopenfilename(title="Elegir archivo", filetypes=[("Excel y CSV", "*.xlsx *.xls *.csv *.txt"), ("Todos", "*.*")]))
    else:
        print(f.askdirectory(title="Elegir carpeta") if tipo == "carpeta" else f.askopenfilename(title="Elegir archivo", filetypes=[("Proyecto UCEclima", "*.json"), ("Todos", "*.*")]))


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    a = sys.argv[1:]
    if a[:1] == ["--worker"]:
        from uceclima.ui import worker
        worker.main(a[1], reanudar="--reanudar" in a[2:])
    elif a[:1] == ["--mcp"]:
        from uceclima import mcp_servidor
        mcp_servidor.main()
    elif a[:1] == ["--ee-auth"]:
        import ee
        ee.Authenticate()
    elif a[:1] == ["--dialogo"]:
        _dialogo(a[1])
    else:
        import argparse
        ap = argparse.ArgumentParser(description="UCEclima"); ap.add_argument("--puerto", type=int, default=8765); ap.add_argument("--sin-ventana", action="store_true")
        o = ap.parse_args(a)
        from uceclima.ui.servidor import main
        main(o.puerto, abrir=not o.sin_ventana)
