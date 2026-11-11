# UCEclima Zeta 8.0.0 · hecho y pendiente (30-oct-2026)

## Hecho en Zeta

| Código | Qué | Dónde |
|---|---|---|
| Z1 | Cualquier sitio con CHIRPS (latitud −50…50). La IDF del INAMHI solo se propone en Ecuador | `descargas.punto_admitido`, `ui/sitio_api.crear` |
| Z2 | Earth Engine: sesión reutilizada (45 min), verificación con plazo de 20 s por proyecto, CMIP6 en paralelo (6 hilos) y por tramos de 30 años | `gee_chirps.iniciar`, `gee_conexion.verificar`, `cmip6_descarga._paralelo` |
| Z3 | Proyecto desde el shape de la zona de estudio: punto interior, copia en `zona_estudio/`, cuenca activa, área 2D. IDF propia con fuente obligatoria (`/api/idf/propia`) | `ui/sitio_api.zona_desde_shape`, `escenarios_idf.registrar_idf_propia` |
| Z4 | Productos ordenados por módulo en `productos/NN_modulo/`, con un informe en md y html por módulo y un índice. Se regeneran tras cada paso, descarga o corrida. Nada se sobrescribe | `productos.py` |
| Z5 | Receta de los papers según el uso y la red; reescalado mes-año; razón de varianza; número efectivo de modelos; tiempo de emergencia con el ruido de la estación | `papers.py`, módulo 11 |
| Z6 | λ hasta 0,6 en el núcleo, para usar calibraciones con abstracción inicial explícita | `climanet/pipeline.py` |
| Pruebas | `tests/test_zeta.py` (14 pruebas) y prueba de punta a punta con Earth Engine real (Kenia) más todo el conjunto heredado | `correr_pruebas_uceclima.py` |

## Añadido el 30-oct-2026 por la tarde (pedido del usuario: «replicable en todo el mundo con CHIRPS, CMIP6…»)

| Qué | Dónde |
|---|---|
| Por defecto, sin estaciones, todo usa CHIRPS: la receta de los papers (`papers.ejecutar` sin estación) y la referencia para corregir CMIP6 | `papers.py`, `cmip6_sesgo.evaluar` (por defecto `chirps:celda_nex_mm`) |
| La receta se calcula sola al terminar los factores CMIP6, con la misma referencia del análisis; la red se detecta sola (≥ 3 estaciones = densa) | `ui/servidor._receta_auto`, `papers.red_auto` |
| IDF desde CHIRPS en cualquier lugar: Gumbel de máximos anuales × 1,13 y coeficientes de Campos (1978), con el supuesto y el sesgo de CHIRPS declarados | `escenarios_idf.idf_desde_chirps`, `POST /api/idf/desde_chirps` |
| Interfaz de la IDF propia y de la IDF desde CHIRPS en el módulo 4 (antes era el pendiente 3) | `ui/static/idf.js` |
| Terreno con Copernicus `GLO30_2024_1` (el activo `GLO30` está obsoleto en Earth Engine; mismas bandas y valores) | `descargas.mdt_gee`, `cuenca.py` |
| «Modo Word»: reabre el último proyecto, vuelve al módulo y repone los campos (autoguardado); botón 💾 Guardar y Ctrl+S | `ui/servidor._sesion_*`, `_estado_ui`, `ui/static/app.js` |
| Mis hallazgos aplicados a CMIP6 (infografía, también en el visor 3D) y ★ Mapa 2D tipo RAS X vs Y en lugar de las maquetas | `papers.cmip6_hallazgos`, `ui/static/cmip6.js`, `visor.html`, `ui/static/mapa2d.js` |
| Interfaz con el logo de la UCE en el pie, la autoría (Diego Quishpe Landeta, autor; Teresa Palacios y María Eugenia Ávila-Salem, coautoras) y «Desarrollado en el marco del Doctorado en Gestión Sustentable del Agua y Riego (UCE)» | `ui/static/index.html` |

## Añadido el 30-oct-2026 por la noche
| Qué | Dónde |
|---|---|
| CMIP6 · versión de frontera (método de los papers), **en evaluación**: carpeta aparte `registro/cmip6_frontera/`, comparada con el método de referencia (Omega). Contar con ambas versiones es parte de la evaluación del software | `papers.frontera`, `/api/cmip6/frontera`, `cmip6.js` |
| Earth Engine «llave rápida»: ID del proyecto propio primero y a la vista, plazo duro de 15 s, conexión automática al abrir, sesión renovada al cambiar de proyecto | `gee_conexion.py`, `gee_chirps._proyecto`, `modulos.js` |

## Añadido el 31-oct-2026
| Qué | Dónde |
|---|---|
| 12 · Validación de campo: encuesta HTML «¿Se inunda?» con los mapas del modelo, registro en el sitio (Apps Script), importación de marcas y contraste con el calado (reemplaza a la maqueta hipsométrica, que se retiró) | `validacion_campo.py`, `ui/static/campo.js`, `ui/static/validacion/` |
| Láminas de validación social (buffer acumulativo; X frente a Y) y botón «Validar con la comunidad» desde la corrida | `validacion_campo.laminas`, `campo.js`, `app.js` |
| Arreglo: rutas de Windows («\») en los enlaces del módulo 12 (lámina en pantalla, «Abrir la encuesta») | `campo.js`, `tests/test_ui.py` |
| Validación de campo automática: hoja conectada, publicación en un clic (enlace, QR, WhatsApp), español/inglés, traer respuestas → contraste → láminas | `validacion_campo.py`, `campo.js`, `validacion/encuesta.*`, `apps_script_uceclima_v2.gs` |

## Pendiente (siguiente iteración de Zeta)

0. **Evaluar la versión de frontera de CMIP6** en los cuatro casos (Chalpi, Tambo, Milagro y Guadalest), una corrida a la vez, y decidir si pasa a ser el método por defecto. No se corrió por decisión del usuario (30-oct-2026).

1. **Humedad del suelo continua**: dosel, almacenamiento de suelo y percolación (Deficit & Constant o SMA) y simulación diaria continua, para reproducir calibraciones de HEC-HMS como la de T. Palacios (Guadalest: CN 72,94, Ia 51,8 mm, suelo 150 mm).
2. **Tránsito por embalse** (level-pool o Puls modificado) con la curva cota–volumen–superficie del proyecto.
3. ~~Interfaz para la IDF propia~~: hecha el 30-oct-2026 (módulo 4).
4. **Descargas de CN, Manning y suelo en paralelo**: hoy siguen una por una.
5. ~~Caso Guadalest~~: hecho el 30-oct-2026. El usuario corrió las 6 corridas 2D (banda CN 59,5/λ 0,30 frente a CN 30/λ 0,05; X, Y 2040–2069 y Y 2071–2100), que ya están en el paper (Tabla 10, Figura 12). Pendiente derivado: el CN declarado mínimo es 30 y el óptimo por eventos fue 25; evaluar si se baja el límite.
6. **Mapa de I1/Id de la norma 5.2-IC dentro del programa**, para que la IDF española se arme sola. Hoy la IDF se arma fuera del programa con la capa del MITECO.
7. **Validación de campo · segunda ronda en Milagro**, con marcas «NO SE INUNDA» para poder evaluar falsas alarmas. El primer contraste (16 marcas del Taller 3) no tuvo ninguna.
