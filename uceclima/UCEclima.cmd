@echo off
rem UCEclima - lanzador de Windows (doble clic). Busca Python con las dependencias del nucleo CLIMANET.
setlocal
cd /d "%~dp0.."
set "PY="
if exist "%USERPROFILE%\miniconda3\envs\geo_env\python.exe" set "PY=%USERPROFILE%\miniconda3\envs\geo_env\python.exe"
if not defined PY if exist "%USERPROFILE%\anaconda3\envs\geo_env\python.exe" set "PY=%USERPROFILE%\anaconda3\envs\geo_env\python.exe"
if not defined PY set "PY=python"
"%PY%" -c "import rasterio, geopandas, numba, matplotlib, jsonschema" 2>nul
if errorlevel 1 (
  echo.
  echo No se encontraron las dependencias de UCEclima en: %PY%
  echo Instale con:  pip install -r uceclima\requirements.txt   ^(ver uceclima\INSTALACION.md^)
  echo.
  pause
  exit /b 1
)
set "ARGS="
if defined UCECLIMA_SIN_VENTANA set "ARGS=--sin-ventana"
if defined UCECLIMA_PUERTO set "ARGS=%ARGS% --puerto %UCECLIMA_PUERTO%"
echo Iniciando UCEclima... ^(cierre esta ventana para detener^)
"%PY%" -m uceclima.ui %ARGS%
if errorlevel 1 pause
