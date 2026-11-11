# UCEclima · interfaz — estado, pruebas y relevo para Codex (13-oct-2026)

## Cómo usar
Doble clic en `uceclima\UCEclima.cmd` → ventana de la aplicación. Flujo vertical verificado: **1 Proyecto → abrir/demo → 7 Corrida: Comprobar → Ejecutar caso pequeño → 8 Evaluación (métricas + mapa)**.
Proyectos de demostración: SINTÉTICO (600×600 m inventados) y Milagro caso pequeño (600×600 m reales: DEM de dron 0,3 m → 10 m, CN/Manning del proyecto, IDF libro INAMHI M0037, Tr 100 / 3 h).

## Implementado (conectado a funciones reales)
| Etapa | Qué hace hoy |
|---|---|
| 1 Proyecto | abrir carpeta/archivo, esquema JSON, recientes, demos, guardar copia sin sobrescribir, diálogo de archivo nativo |
| 2 GEE | prueba de conexión (credenciales del sistema), lista de caché, explicación de acceso |
| 3 Lluvia | auditoría del Excel M0037 (atribución Caiza 2026, hallazgos, ecuación) y selección estadística de eventos con límites |
| 4 CHIRPS | plan de ventanas ±5/±21 d y cobertura real en GEE (v3 → v2, sin mezclar, fallback visible) |
| 5 Terreno | CRS, resolución, cobertura, tipo MDT/DSM, datum, vista previa sombreada |
| 6 Cuencas | lectura de diagnósticos (correspondencia HMS, áreas, candidatos de entrada, datos faltantes) |
| 7 Corrida | comprobación previa con hashes y estimación de recursos; una tarea; progreso; cancelar; registro; historial con estados completado/fallido/cancelado/interrumpido |
| 8 Evaluación | volumen m³ y %, residual, Courant, pasos, % limitador, áreas, «no evaluada» para capacidad/pérdidas/secciones, mapa real del calado máximo |
| 9 CMIP6 | bloqueado, con las razones leídas de la compuerta y de la ficha de observaciones |
| 2 Datos / GEE · sitio nuevo | **proyecto nuevo desde un punto (lon, lat), descarga automática**: crea el proyecto y trae solo el MDT Copernicus GLO-30 de 30 m (UTM, registrado como DSM), **CN y Manning estimados desde Earth Engine por defecto** (ESA WorldCover 2021 × suelo OpenLandMap, mismas tablas de referencia de CLIMANET/Milagro, no calibrados; si el proyecto ya trae CN/Manning detallados, los suyos tienen prioridad y los de GEE quedan al lado para comparar), CHIRPS (v3 si existe; si no v2, sin mezclar), tramos candidatos de GEOGLOWS (1940–hoy) y, opcional, cota y caudal de Mazar (CELEC). Una descarga a la vez, carpeta nueva con manifiesto y SHA-256, progreso en pantalla. Solo requiere cuenta de Earth Engine (botón «Autorizar»: el programa no ve ni guarda credenciales). **CMIP6 no se descarga** (bloqueado hasta calibrar y validar la línea base) |
| 3 Lluvia · eventos del proyecto | selección estadística de eventos con la lluvia CHIRPS y el caudal descargados: umbrales derivados de los propios datos y escritos en `criterios.json`, falla de sensor anulada (no corregida), bloques de año hidrológico calibración/validación, ventanas CHIRPS −21/+5 d, volumen directo observado, hidrogramas diarios por evento (paquete previo a HEC-RAS/2D) |
| 0 Preparación de datos (premódulo) | **carga de datos crudos ordenada con ayuda de una IA** (vía API abierta; el programa no lleva un modelo de lenguaje): escanea y clasifica archivos (lluvia ancha de anuario INAMHI, lluvia larga, inventario de eventos SGR/SNGR, ráster…), lee la lluvia por CONTENIDO (corrige encabezados corridos, filas de título/grupo), mide calidad por estación (completitud, años sin datos, huecos), revisa el inventario (fechas nulas, coordenadas repetidas, duplicados), **contrasta lluvia vs eventos** (percentil y retorno empírico por evento; tasa de eventos por clase de lluvia; descriptivo, sin causalidad) y **ordena** todo en una carpeta nueva (crudos intactos; conflictos entre fuentes quedan vacíos; manifiesto con SHA-256). Puede registrar una estación en el proyecto |
| 9 CMIP6 · cambio climático (Y) | **decisión del usuario registrada** (línea base asumida; no calibrada ni validada), NEX-GDDP-CMIP6 (NASA, 25 km, Earth Engine) en dos fases (histórico 1981–2014 de los 33 modelos; futuro 2015–2100 solo de los mejores), referencia **CHIRPS** (celda de 0,25°, 1981–2025), evaluación (sesgo, RMSE de climatología/cuantiles/máximos anuales), **QQM mensual con validación cruzada**, **mejor modelo y ensamble ponderado**, **QDM** que preserva la señal, **verificación independiente 2015–2025**, **tasa de cambio de la lluvia de entrada** (mediana, p10, p90 y mejor modelo) como escenarios Y que corren en el mismo modelo; gráficas de datos crudos vs corregidos, abanico anual 1981–2100 y factores. **Todo lo de cambio climático se ve en magenta degradado**; X (condiciones existentes) en tonos fríos |
| Base de datos del proyecto | SQLite `base_datos/uceclima.sqlite` (series CMIP6 originales y corregidas, métricas, factores, referencia, eventos, escenarios, corridas, estaciones); consulta SQL de solo lectura por la interfaz y por la API/MCP |
| ★ API / IA (+ MCP) | **servidor MCP** (`python -m uceclima.mcp_servidor` o `UCEclima.exe --mcp`, ~33 herramientas con las reglas del proyecto) para Claude Desktop, Claude Code y VS Code; instalación con un clic (fusiona y deja .bak); guías `AGENTS.md`/`CLAUDE.md` |
| ★ API / IA | API local abierta (127.0.0.1) para agentes de IA y scripts: `/api/openapi.json`, `/api/docs`, guía para modelos `/api/ia`; los POST piden `Authorization: Bearer <clave>` (clave en `%USERPROFILE%\.uceclima\api_key.txt`, visible en la pestaña). Es la misma API de la interfaz; hace cumplir las reglas (CMIP6 bloqueado, una corrida por vez, nada se sobrescribe) |
| 3 Lluvia · estaciones | **importar CSV de pluviómetro/pluviógrafo** con vista previa, columnas elegidas, zona horaria (se guarda en UTC), control de calidad (huecos, negativos, duplicados, paso), catálogo compatible con CLIMANET `StationRain`, serie y hietograma de evento. **un evento de la estación puede conducir la corrida** (modo `evento_observado` del núcleo: sin ausentes ni huecos, lluvia diaria solo con desagregación uniforme declarada, hasta 12 h simuladas; el modelo sigue sin calibrar y no es una validación) |
| 5 Terreno · MDT de dron | inspeccionar un GeoTIFF (CRS, resolución, NoData, rango, avisos) y **registrarlo** como terreno del proyecto por referencia (ruta + hash, sin copiar), con tipo MDT/DSM y datum declarados, área de estudio y tope de 250 000 celdas; respalda config y proyecto |
| 8 Evaluación · escenarios de IDF | **comparación de escenarios de lluvia de diseño** (todos históricos, ninguno es cambio climático): IDF directa de la estación INAMHI (principal), IDF reescalada al Gumbel de los máximos anuales observados (referencia), y «fantasmas»: IDF escalada al sitio y reescalada a CHIRPS. Tabla, lluvia acumulada superpuesta y área inundada; en el Visor 3D los fantasmas se dibujan de fondo sobre el mismo terreno |
| ★ Visor 3D de resultados | maqueta isométrica nocturna (three.js propio vendorizado en `ui/static/vendor/`, tomado de `Milagro_3D.html`) con el terreno y las capas REALES de la corrida: calado máximo, velocidad máxima y duración con calado ≥ 0,3 m; cambio de capa, umbral de calado, exageración vertical, vista isométrica/perspectiva, brillo, curvas de nivel y rejilla, lectura por celda al pasar el cursor y «barrido por calado» (recorre el umbral; NO es evolución temporal). Sin h(t) porque el solver no exporta estados |
| ★ Maquetas isométricas | galería de figuras estilo «anatomy» (kit isométrico en `ui/static/iso/`, licencia MIT incluida). **Implementada: «Almacenamiento del terreno»**: pila de 16 láminas por clase de cota con el DEM real del proyecto, agua transparente, calibre de gancho y dos diales (área bajo el nivel y volumen V(η)); es geometría del terreno, no simulación de inundación. **Pendientes**: balance de volumen (con `balance_agua.csv`), paso de tiempo/Courant, conectividad de caras, celda con relieve subcelda |
| 10 VOTEX | enlace a mapa estático y a la maqueta sintética rotulada |

## Tema
La interfaz es **noche** por defecto (coherente con el visor 3D) y tiene botón «Tema» para volver al claro (preferencia solo en el navegador).

## Pendiente (desactivado en pantalla, con motivo)
Digitalizar bandas · cuencas externas con evento observado (hoy solo con tormenta de diseño) · humedad antecedente (CN) en eventos · rásteres diarios CHIRPS y CHIRPS local · nube de puntos de WebODM y 30 m desde GEE · edición de entradas, perfiles,
breaklines y estructuras (QGIS/GeoPackage) · caudal/nivel por sección y comparación con referencia en la evaluación · corridas con solver subcelda y cuencas externas desde la interfaz ·
descarga y análisis NEX-GDDP-CMIP6 · exportación de estados h(t) y visor 3D+tiempo con datos reales · textura satelital georreferenciada · instalador/empaquetado (.exe) · pruebas de teclado y lector de pantalla exhaustivas.

## Pruebas (reproducibles)
`python uceclima\correr_pruebas_uceclima.py` → idf_excel 2 · lluvia 4 · gee_chirps 4 · seleccion_eventos 3 · hipsometría 5 · preparación 7 · descargas 6 · cmip6 4 · **ui 14** (incluye el visor 3D con datos reales y la maqueta: API, MIME de módulos ES y construcción real de la figura en Chrome/Edge sin cabeza, si está instalado) (servidor real en puerto efímero, proceso de cálculo real con el caso sintético, seguridad de token/host,
esquema, no sobrescribir, entradas faltantes, caso grande rechazado, **una tarea por vez**, **cancelación**, **corrida interrumpida**, CMIP6 bloqueado). CLIMANET sigue en 38 pruebas OK (3 nuevas del evento observado).
Corridas reales por la interfaz: sintético (≈10 s) y Milagro pequeño (10 s; balance 2,8e-13 %, Courant máx. 0,35, 26 688 pasos, 6,9 % de pasos con limitador). Lanzador `UCEclima.cmd` probado en modo sin ventana (HTTP 200).

## Capturas verificadas (`ui\capturas\`, Edge sin cabeza, revisadas una por una)
maquetas · proyecto · gee · lluvia · chirps · terreno · cuencas · corrida · evaluacion (+ `_alta` con mapa completo y `_estrecha` 480 px) · cmip6 · votex · `_sintetico` (marca de agua y rótulo).
Verificado: etiqueta SINTÉTICO en cabecera, título y mapa; «no calibrado/no validado» en evaluación; botones pendientes desactivados; ventana estrecha con menú ☰ y tarjetas apiladas; sin desbordes tras la corrección.
No se capturaron los estados tras pulsar «Probar conexión» ni «Consultar cobertura» (se verificaron por API con GEE real: conexión correcta; CHIRPS v3 DAILY_SAT cobertura completa para feb-2011).

## Errores encontrados y corregidos durante la verificación
1. Rutas relativas del proyecto: el núcleo las resolvía contra el directorio de trabajo → ahora la interfaz las convierte a absolutas.
2. Tabla de «Proyecto actual» desbordaba la tarjeta; métricas ~1e-11 se mostraban como «0» → ahora notación científica.
3. Texto «no calibrado» duplicado; detalle de la compuerta CMIP6 mostraba un diccionario crudo → frases legibles.
4. Estación del Excel: el usuario indicó que CUMBE = Milagro; queda registrado como afirmación del usuario (sin documento que la respalde).

## Límites y riesgos para revisión
- El mapa de Milagro muestra celdas aisladas con agua: es el máximo del modelo en un DSM de 10 m (fosos y construcciones), no una huella de inundación; no está calibrado ni validado.
- La ventana tipo aplicación (`msedge --app`) no se probó con ojo humano; el renderizado sí (Edge sin cabeza). El diálogo «Examinar…» usa Tkinter en un proceso aparte (no probado en pantalla).
- El estimador de tiempo se extrapola de una sola medición (±factor 2); sirve como orden de magnitud.
- `servidor.py` guarda el proyecto abierto en memoria: una sola sesión de usuario por servidor.
- Accesibilidad: foco visible, saltar al contenido, Alt+1…0 para etapas y contraste revisados a ojo; sin auditoría automática (axe/WAVE).

## Actualización 13/14-oct-2026 (noche)
- **Nombre visible: UCEclima.** Paquete Python y rutas siguen `uceclima`. Logos: GICARH (grupo) y UCE (`ui/static/logo_grupo.png`, `logo_uce.png`; los anteriores quedan como `.v1.bak`).
- **hidro / land** (vocabulario propio): hidro = hidrología (cuencas, SCS-CN + UH, Muskingum, panel «Hidrología y calibración»); land = hidráulica 2D (terreno, Manning, fronteras, corrida, evaluación). No son HEC-HMS/HEC-RAS ni equivalen a ellos; el modelo externo usado para comparar se rotula «referencia externa» (no es observación).
- **▶ RUN** en la barra superior: ejecuta la acción principal del módulo abierto (con confirmación; una tarea a la vez; nunca registra la decisión de CMIP6 ni lanza descargas sin pedirlo).
- **Panel «8b · hidro · Hidrología y calibración»** (`hidrologia_api.py`, `ui/static/hidrologia.js`, `/api/hidrologia/{casos,serie,exportar}`, 3 herramientas MCP): series reales del núcleo; métricas solo en períodos coincidentes con dato válido; sin observaciones = «SIMULACIÓN SIN CALIBRAR»; exporta CSV + PNG + manifiesto. Pruebas: `tests/test_hidrologia.py` (10).
- **Terreno**: al inspeccionar un MDT se comprueba si coincide con el sitio/AOI y si se superpone al terreno regional de Earth Engine (veredicto, distancia, pistas de zona UTM, esquema). El AOI por defecto se centra en el sitio. Pruebas: `tests/test_terreno_coincidencia.py` (5).
- **CMIP6 v2 + revisión matemática** (ver `MODULO_CMIP6.md`): cobertura contra el calendario esperado, pesos finitos y normalizados en casos degenerados, QDM probado, Tr100 con años efectivos e intervalo, supuesto IDF exploratorio. Pruebas: `tests/test_cmip6_matematica.py` (19).
