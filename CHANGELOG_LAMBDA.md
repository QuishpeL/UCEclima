# CHANGELOG · UCEclima Lambda 9.1.0

Lambda es Eta 9.0.0 más cuatro cambios; es la versión de uso. CMIP6 y el resto del programa no cambian respecto de Eta.

## Nuevo
- **Módulo 7b · Pronóstico de lluvia** (`uceclima/pronostico.py`, `ui/static/pronostico.js`, API `/api/pronostico/*`, herramientas MCP `pronostico_*`):
  GFS y ECMWF IFS (Open-Meteo, sin claves), NASA GPM IMERG V07 (Earth Engine) y caudal GEOGLOWS v2 Forecast. Cada consulta queda en
  `datos/pronostico/<modelo>_<sello>/` con su procedencia. «Usar como forzamiento» declara el evento con la marca `forzamiento_externo`; el núcleo
  (`climanet/pipeline.py`) etiqueta la corrida `pronostico_<modelo>` / `estimacion_satelital_<modelo>` y los avisos dicen que no es una observación.
- **Botón «Calado, velocidad y peligro»** (`uceclima/peligro.py`, `ui/static/peligro.js`, API `/api/peligro/generar`, herramienta MCP `peligro_generar`) en los
  módulos 8 y 11: GeoTIFF, shapefile y PNG de cada variable, lámina de 3 paneles con OSM, resumen en km² y edificios (clases ARR 2019). Integra la
  herramienta externa `mapas_peligro.py` de Eta; usa el terreno que usó cada corrida.

## Cambiado
- La franja roja «UCEclima se desconectó» solo aparece ante un corte real (6 latidos fallidos, > 60 s sin respuesta, segunda sonda; no cuenta con la pestaña oculta) y se puede cerrar.
- Marca y versión: UCEclima Lambda 9.1.0; sesión propia `~/.uceclima/sesion_lambda.json` (la primera vez lee la de Eta o Zeta); instalador con AppId propio.

## Corregido
- `chirps_salidas.py`: las barras de error de la climatología mensual nunca son negativas (en Galápagos la media de un mes seco quedaba por encima del percentil 75).

## No incluido (decisión del usuario, 5-nov-2026)
- El cambio «solo meses húmedos» de la calibración CMIP6 (QQM) no se toma: Lambda mantiene el comportamiento de Eta (un mes sin días húmedos suficientes descarta el modelo).
- Siguen pendientes los puntos de `PENDIENTES_ETA_9_1.md` (cuencas externas calculadas, diagnóstico de entradas, barra global, etc.).
