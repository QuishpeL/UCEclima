# Instalación de UCEclima (Windows 10/11)

## Requisitos
- Python 3.9 o superior (probado con 3.9.24, entorno `geo_env` de Miniconda) y un navegador Edge o Chrome (para la ventana de la aplicación).
- Dependencias: `pip install -r uceclima\requirements.txt` (numpy, scipy, pandas, rasterio, geopandas, shapely, matplotlib, numba, scikit-image, jsonschema, openpyxl; `earthengine-api` solo para GEE/CHIRPS).
  En Windows, rasterio y geopandas se instalan mejor con conda: `conda create -n geo_env python=3.9 rasterio geopandas numba matplotlib scikit-image jsonschema openpyxl scipy pandas` y luego `pip install earthengine-api`.
- Sin Internet la aplicación funciona; solo GEE/CHIRPS necesitan conexión.

## Instalación limpia
1. Copiar la carpeta `MILAGRO` (con `climanet\` y `uceclima\`) a una ruta sin tildes ni espacios si es posible.
2. Crear/activar el entorno e instalar dependencias (arriba).
3. Doble clic en `uceclima\UCEclima.cmd`. Si faltan dependencias, el lanzador lo dice y no arranca a medias.
4. (Opcional) GEE: abrir una terminal y ejecutar `earthengine authenticate`; la interfaz reutiliza esas credenciales, nunca las guarda.

## Variables opcionales del lanzador
`UCECLIMA_SIN_VENTANA=1` (no abre ventana; usar un navegador en la URL mostrada) · `UCECLIMA_PUERTO=8765` · `UCECLIMA_GEE_PROJECT=<id proyecto Cloud>`.

## Desinstalar
Borrar la carpeta. La interfaz solo escribe en la carpeta de cada proyecto, en `uceclima\cache` y `uceclima\salidas`, y la lista de proyectos recientes en `%USERPROFILE%\.uceclima\recientes.json` (rutas, sin secretos).
