# CHANGELOG · UCEclima Lambda 9.2.0 (11-nov-2026)

Lambda 9.2 es Lambda 9.1 más cinco cambios. El núcleo hidrológico, hidráulico y CMIP6 de 9.1 no cambia; las entradas nuevas solo actúan si se declaran.

## Nuevo
- **Cuencas externas automáticas** (`uceclima/externas_auto.py`, `ui/static/externas.js`, tarea `externas`, API `/api/corrida/externas`, `/api/corrida/externas_registrar`):
  el método con que se modeló Quito por secciones (5-nov-2026), ahora dentro del programa. D8 priority-flood sobre el MDT amplio (GLO-30), entradas con
  ≥ área mínima, cuencas incrementales SIN solape, CN de las mismas tablas WorldCover × OpenLandMap (AMC II), lag NEH-630 y entrada ajustada al cauce del
  MDT del proyecto. Las chicas (≤ área máxima) van con SCS-CN y la misma IDF y Tr de la corrida; las grandes se proponen como entrada GEOGLOWS.
  Si una entrada no pasa la comprobación de cauce, solo se usa si la persona marca «bajo mi responsabilidad» (queda escrito en el proyecto).
  Prueba con Quito QS1: 14 de 14 cuencas iguales a las hechas a mano (p. ej., E3 27,19 vs 27,25 km², CN 54,0, lag 1,98 vs 1,97 h) y el río grande de ~540 km² separado.
- **Hidrograma de entrada GEOGLOWS para ríos grandes sin datos** (`climanet/entradas_geoglows.py`, tarea `geoglows_entrada`, API `/api/corrida/entradas_geoglows`,
  `cfg["entradas_geoglows"]`): serie horaria retrospectiva de GEOGLOWS v2 (1940-hoy) del tramo; pico = Gumbel por momentos de los máximos horarios anuales para
  el Tr DE CADA CORRIDA (se avisa si Tr > años de serie); forma = media de las crecidas anuales normalizadas; pico sincronizado con el bloque de máxima lluvia
  de la tormenta local (caso desfavorable, declarado). Solo con tormentas de diseño. El endpoint `returnperiods` de GEOGLOWS fallaba (11-nov-2026) y no se usa.
- **Módulo 13 · visor de partículas «lluvia a caudal»** (`uceclima/particulas.py`, `ui/static/particulas.html`, API `/api/particulas/datos`): el prototipo del
  7-nov-2026 dentro del programa, para cualquier corrida terminada (enlace junto a «Ver métricas»). La cortina de lluvia sigue el hietograma real de la corrida.
  Visualización: la dirección sale de la pendiente de la superficie, no de velocidades guardadas.

## Cambiado
- La franja roja de desconexión es ahora un **ícono pequeño** en la barra superior (verde conectado · ámbar lento · rojo cortado); al pulsarlo, una tarjeta
  pequeña con «Reconectar». Misma detección que 9.1 (6 latidos fallidos y > 60 s, segunda sonda).
- **Licencia**: los encabezados de los archivos decían GPL-3.0; ahora dicen CC BY-NC 4.0, igual que `LICENSE`, GitHub y Zenodo.

## Corregido
- Las respuestas JSON con NaN o infinito rompían el panel Hidrología en corridas con cuencas externas o CMIP6: ahora se envían como vacío (`null`).

---

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
