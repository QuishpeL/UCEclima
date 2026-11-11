# UCEclima 9.1.0 "Lambda"

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24122769.svg)](https://doi.org/10.5281/zenodo.24122769)

Archived release (installer, source code and manual): https://doi.org/10.5281/zenodo.24122769

Free desktop application for Windows that links, in one traceable project, gauge screening, event-based hydrological
calibration (SCS-CN + unit hydrograph, KGE/NSE), a mass-conservative 2D local-inertial flood model and CMIP6 scenarios
(NEX-GDDP-CMIP6, SSP5-8.5: bias correction, ClimWIP weights, change factors per return period and time of emergence).
Existing conditions (X) are always shown against the CMIP6 scenario (Y).

Software described in: Quishpe Landeta, D., Palacios, T., Ávila-Salem, M.E., Montero, C. *UCEclima: an open desktop
workflow linking gauge screening, event calibration, 2D flood modelling and CMIP6 time of emergence for climate-informed
design floods in data-scarce catchments*. Submitted to Environmental Modelling & Software (ENVSOFT-D-26-03951).

## Download and install (no programming needed)
1. Download `UCEclima_Lambda_Setup.exe` from the **Releases** page of this repository (or from the Zenodo record).
2. Check the SHA-256 against `SHA256SUMS.txt`.
3. Run the installer (Windows 10/11, 64-bit, no administrator rights). The program opens in the browser at http://127.0.0.1:8765.
4. The program is not code-signed. If Windows Smart App Control blocks it: Windows Security › App & browser control ›
   Smart App Control › Off (personal PC), or ask IT to allow the UCEclima folder (institutional PC).
5. Earth Engine (terrain, CHIRPS, CMIP6) is authorised on each computer with the user's own Google account and Cloud
   project; the program stores no credentials in its code.

The user manual (Spanish) is published with the release (`UCEclima_Lambda_9.1.0_user_manual_ES.pdf`).
The interface is in Spanish; module names are listed below in English.

## Run from source
```
python -m pip install -r uceclima/requirements.txt   # rasterio and geopandas install best with conda
python -m uceclima.ui                                # interface at http://127.0.0.1:8765 (--puerto N, --sin-ventana)
python uceclima/correr_pruebas_uceclima.py           # automated test suite
```
Python 3.9 or later. `climanet/` is the hydrological and hydraulic core; `uceclima/` is the application, local server,
web interface (`uceclima/ui/static`) and tests (`uceclima/tests`); `instalador/` holds the Inno Setup script.

## Modules
0 Data preparation · 1 Project · 2 Data / Earth Engine · 3 CHIRPS · 4 IDF (X) · 5 Terrain · 6 Hydrology · 7 Land cover ·
2D run · 7b Rainfall forecast · 8 Evaluation · 8b 2D map X vs Y · 8c 3D viewer · 9 CMIP6 · 10 WRF · 11 Results and reports ·
12 Field validation.

## Version 9.1.0 "Lambda" vs 9.0.0 "Eta"
The results in the paper were computed with 9.0.0. Version 9.1.0 keeps the hydrological, hydraulic and CMIP6
components of 9.0.0 unchanged and adds: a rainfall-forecast module (GFS and ECMWF IFS via Open-Meteo, NASA GPM IMERG,
GEOGLOWS v2 discharge; runs are labelled as forecasts, never as observations); a depth–velocity–hazard product
(Australian Rainfall and Runoff 2019 classes) in GeoTIFF, shapefile and PNG; a fix of the disconnection banner; and a
fix of the CHIRPS monthly-climatology error bars in very dry months. See `CHANGELOG_LAMBDA.md`.

## Limitations
Results are not calibrated or validated unless the project declares it; they are not predictions. Channel capacity
and head losses are not evaluated. CMIP6 uses SSP5-8.5 only.

## Licence and citation
CC BY-NC 4.0 (see `LICENSE`): free use, modification and redistribution for research, teaching and non-commercial
purposes, with attribution. Please cite the Zenodo record (see `CITATION.cff`) and the paper.

## AI assistance
Code correction and HTML generation were assisted by Claude Code (Anthropic) in Visual Studio Code. Design,
technical direction, review and all decisions on the software are the authors'.

Contact: Diego Quishpe Landeta, dgquishpe@uce.edu.ec · Universidad Central del Ecuador
