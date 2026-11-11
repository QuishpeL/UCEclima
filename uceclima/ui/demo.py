# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Proyectos de demostración. El SINTÉTICO se rotula siempre como tal; el de Milagro usa datos reales con un área mínima.
Ninguno sobrescribe: si la carpeta existe, se abre tal cual."""
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

from . import proyecto as P

RAIZ = Path(__file__).resolve().parents[1] / "proyectos"


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


def crear_sintetico(carpeta=None):
    """Terreno inventado (plano inclinado con un cauce y una depresión), 60×60 celdas de 10 m. Solo prueba el flujo; NO es un lugar."""
    carpeta = Path(carpeta or RAIZ / "demo_sintetico"); arch = carpeta / P.ARCHIVO
    if arch.exists():
        return carpeta
    (carpeta / "datos").mkdir(parents=True, exist_ok=True)
    ny = nx = 60; res = 10.0
    y, x = np.mgrid[0:ny, 0:nx]
    z = 25 - 0.012 * res * y + 0.4 * np.sin(x / 5.0) * np.cos(y / 7.0)
    z[:, 28:31] -= 1.2                                                     # cauce
    z[40:46, 10:16] -= 1.0                                                 # depresión
    tr = from_origin(500000, 9760000 + ny * res, res, res)
    with rasterio.open(carpeta / "datos" / "terreno_sintetico.tif", "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32",
                       crs="EPSG:32717", transform=tr, nodata=-9999) as s:
        s.write(z.astype("float32"), 1)
    cfg = {"dem": "datos/terreno_sintetico.tif", "res": 10, "aoi": [500000, 500600, 9760000, 9760600], "idf_inamhi": {"estacion": "M0037"}, "Tr": 100,
           "storm_min": 120, "sim_horas": 4, "cn_default": 80, "manning_default": 0.05, "boundary": "free_outflow", "out_dir": "resultados/_no_usado",
           "escenarios": ["diseno_idf_historica"]}
    (carpeta / "config_climanet.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    P.guardar({"version_esquema": 1, "nombre": "Demostración SINTÉTICA (no es un lugar real)", "tipo": "sintetico", "ubicacion": "inventada",
               "descripcion": "Terreno artificial de 600×600 m para probar el flujo abrir → verificar → ejecutar → métricas → mapa.",
               "crs": "EPSG:32717", "datum_vertical": "no aplica (terreno sintético)", "tipo_terreno": "desconocido",
               "unidades": {"longitud": "m", "lluvia": "mm", "caudal": "m3/s"}, "carpeta_resultados": "resultados", "config_climanet": "config_climanet.json",
               "procedencia": {"creado": _ahora(), "origen": "uceclima.ui.demo.crear_sintetico", "notas": ["Datos generados por código; sin significado geográfico.", "La IDF es la oficial M0037 solo para dar magnitudes de lluvia plausibles."]}}, carpeta)
    return carpeta


def crear_milagro_pequeno(carpeta=None):
    """Caso REAL pequeño: 600×600 m de Milagro con el DEM fino de dron (0,3 m remuestreado a 10 m), CN/Manning del proyecto y la IDF oficial M0037."""
    carpeta = Path(carpeta or RAIZ / "milagro_caso_pequeno"); arch = carpeta / P.ARCHIVO
    if arch.exists():
        return carpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    ins = "C:/Users/agdgq/Desktop/MILAGROCODEX/insumos/"
    cfg = {"dem": "C:/DRONDJI/DEM_MILAGRO_COMPLETO/DEM_Milagro_8vuelos_armonizado.tif", "res": 10, "aoi": [653800, 654400, 9759800, 9760400],
           "idf_inamhi": {"estacion": "M0037"}, "Tr": 100, "storm_min": 180, "sim_horas": 6, "cn_tif": ins + "cn_dominio_completo.tif",
           "manning_tif": ins + "manning_dominio_completo.tif", "boundary": "free_outflow", "out_dir": "resultados/_no_usado", "escenarios": ["diseno_idf_historica"]}
    (carpeta / "config_climanet.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    P.guardar({"version_esquema": 1, "nombre": "Milagro · caso pequeño (600×600 m)", "tipo": "real", "ubicacion": "Milagro, Guayas, Ecuador (zona del Taller 3)",
               "descripcion": "Prueba del flujo completo con datos reales en un área mínima. No es un estudio de amenaza.",
               "crs": "EPSG:32717", "datum_vertical": "no verificado (sin control vertical local)", "tipo_terreno": "DSM",
               "unidades": {"longitud": "m", "lluvia": "mm", "caudal": "m3/s"}, "carpeta_resultados": "resultados", "config_climanet": "config_climanet.json",
               "procedencia": {"creado": _ahora(), "origen": "uceclima.ui.demo.crear_milagro_pequeno",
                               "notas": ["Terreno: DEM de dron armonizado (8 vuelos); probablemente modelo de superficie (incluye construcciones).", "CN y Manning: WorldCover 2021 × textura OpenLandMap, no calibrados.",
                                         "IDF: libro INAMHI, estación M0037 (Milagro-Ingenio Valdez)."]}}, carpeta)
    return carpeta
