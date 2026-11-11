# UCEclima · documentación madre (versión beta 3 · 3.3.0)

UCE · GICARH. Aplicación de escritorio para Windows (`UCEclima.exe`): interfaz web local en `127.0.0.1:8765` (o el puerto libre que anote en `~/.uceclima/puerto.txt`) y servidor MCP `uceclima` (`UCEclima.exe --mcp`).
Modela la **hidrología** (hidro: SCS-CN + hidrograma unitario SCS, tránsito, calibración humana) y la **hidráulica 2D** (land) de cuencas de Ecuador, con descargas de Earth Engine, CHIRPS, GEOGLOWS, IDF INAMHI, CMIP6 y WRF, y entregas para BCA FEMA y ENSO.

Esta especificación reemplaza como referencia a `README.md`, `ESTADO_INTERFAZ.md`, `DECISIONES_INTERFAZ.md` y `ESTADO_ETAPA_1_2.md` (se conservan como antecedentes).

## 1. Filosofía (reglas que no se eliminan)
1. **Nada se sobrescribe**: cada descarga, corrida, barrido o entrega va en una carpeta nueva con sello de tiempo; si se reescribe un archivo de configuración queda un `.bak`.
2. **Nada se calibra solo**: el programa propone y mide; la persona acepta una combinación con su nombre.
3. **La persona confirma la identidad de cada serie observada** (qué mide, dónde, fuente). Sin confirmación no entra a ninguna métrica.
4. **Los resultados sin validar se rotulan como tales** («simulación sin calibrar»; «validación desfavorable»; «óptimo en el borde»).
5. **Una corrida o una descarga a la vez.**
6. X = condiciones existentes (tonos fríos); Y = CMIP6 SSP5-8.5 (magenta). CMIP6 sin compuerta; mejor modelo = RMSE de climatología más bajo.
7. No se inventan parámetros ni datos: lo que falta se pide o queda vacío.

## 2. Módulos
| # | Módulo | Qué hace |
|---|---|---|
| 0 | Preparación de datos | Excel/CSV de lluvia, caudal y nivel; **carga masiva** en segundo plano (cientos de estaciones), tipo por defecto, catálogo de coordenadas (`codigo, lon, lat`), rechazo de tablas resumen. |
| 1 | Proyecto | Crear (carpeta `<nombre>ucec`), abrir, **renombrar**, **editar el sitio** o centrarlo en la cuenca, estaciones INAMHI cercanas, lista de proyectos. |
| 2 | Datos / GEE | Conexión con la cuenta propia de Earth Engine; uso de suelo y suelo; CN y Manning; CN/Manning propios; GEOGLOWS (en el sitio o en la salida de la cuenca); otras capas. |
| 3 | CHIRPS | Lluvia diaria por satélite del sitio. |
| 4 | IDF INAMHI (X) | Ecuaciones del libro del INAMHI; punto = sitio o centroide de la cuenca activa. ⚙ Tr y duración. |
| 5 | Terreno | MDT de Earth Engine (sitio o cuenca activa + margen) o GeoTIFF propio; lámina del MDT; historial de registros. ⚙ resolución. |
| 6 | hidro | Pestañas **Cuenca** (shape, delineación desde MDT con ríos HydroSHEDS o propios, malla CHIRPS), **Hidrología**, **Calibración** (caudal observado, lluvia CHIRPS/estación/areal Thiessen o IDW, eventos, barrido con recesión, comparación R4, aceptación). |
| 7 | land · Corrida 2D | Comprobación previa (cuenca dentro del área simulada, CN de la 2D, DSM urbano) y corrida. ⚙ resolución, tiempo, paso, Courant, solver, frontera, relleno, **CN para la 2D**. |
| 8 | land · Evaluación | Balance, estabilidad, resultado; **alertas** (velocidad > 10 m/s, limitador > 50 %, almacenado > 80 %). |
| 9 | CMIP6 | Evaluación de modelos, futuro SSP5-8.5, factores QDM, **Time of Emergence**. |
| 10 | WRF | Leer salidas WRF (X o Y) con corrección QQM; preparar corridas para Linux/WSL. |
| 11 | Resultados y entregas | 01_resultados (incluye `hidro_calibracion/` y la cuenca activa), 02_BCA_FEMA, 03_ENSO (CHIRPS y lluvia registrada de la cuenca). |
| ★ | Visor 3D y maquetas | Terreno 3D (sin corrida) y resultados con agua. |

## 3. Pasos de tiempo (aclaración)
- **hidro · calibración**: modelo agregado **diario** (Δt = 24 h). Con Δt diario un lag < 24 h no es identificable (se avisa). La calibración horaria **no existe todavía** (C14).
- **land · Corrida 2D**: tormenta de diseño con hietograma de **5 min** (3 h, IDF), paso de cálculo ≤ 5 s (⚙ «paso de tiempo máximo»), 6 h simuladas (⚙).
- **CMIP6/ToE**: diario 1981–2100; ToE con media móvil de 20 años.

## 4. Agentes de IA (R1)
Al crear o abrir un proyecto se escriben en su carpeta: `.vscode/mcp.json` (clave `servers`, VS Code/Copilot), `.mcp.json` (clave `mcpServers`, Claude Code), ambos con `command` = ruta de `UCEclima.exe`, `args: ["--mcp"]`, `env.UCEclima_EXE` y `env.UCECLIMA_PROYECTO`; `AGENTS.md` = `CLAUDE.md`; y `.claude/settings.local.json` con `enabledMcpjsonServers: ["uceclima"]`. Se reescriben solo si cambiaron (con `.bak`).
El servidor MCP habla JSON-RPC por stdio en UTF-8 (JSON ASCII), lee el puerto real, arranca UCEclima si está cerrado y abre el proyecto de su carpeta. Botón «Agente» (cabecera): VS Code + Claude Code / VS Code + Copilot, con estado de cada uno.

## 5. Requisitos de la versión beta
Prioridad: **P1** bloquea el flujo · **P2** produce resultados engañosos · **P3** comodidad. Estado al 17-oct-2026 en PC1 (matriz). Caso de referencia: proyecto `QuitoCCP2` (PC2), cuenca Chalpi hasta H13 Chalpi Grande.

| ID | Prio. | Módulo | Antes | Ahora | Criterio de aceptación | Estado |
|---|---|---|---|---|---|---|
| R1 | P1 | Proyecto / MCP | Solo `.vscode/mcp.json`; el exe respondía en cp1252 (JSON ilegible); puerto fijo 8765 | Ambos agentes configurados al crear/abrir; MCP UTF-8; puerto real; abre el proyecto | Un proyecto nuevo abre en VS Code con Claude Code y con Copilot y ambos listan las herramientas de `uceclima` | Hecho (protocolo probado con el exe: 41 herramientas, abre el proyecto). Falta ver Copilot en una PC con Copilot |
| R2 | P2 | 1 · Proyecto | El sitio no se podía cambiar | Editar lon/lat o centrar en la cuenca; UTM recalculado; sitio anterior en la procedencia; descargas MDT/suelo/CN/GEOGLOWS e IDF marcadas como desactualizadas | Mover a lon −78,0968, lat −0,2998 y que las nuevas descargas cubran el 100 % de la cuenca | Hecho (con «Área: cuenca activa» el MDT/CN cubren el 100 %) |
| R3 | P3 | 1 · Proyecto | Carpeta = nombre | Carpeta `<nombre>ucec`; `proyecto_uceclima.json` dentro; renombrar sin perder historial; lista de proyectos | «quitocc» → `quitoccucec`; renombrar conserva archivos y procedencia | Hecho |
| R4 | P2 | hidro · Calibración | Una figura de eventos | Mosaico, dispersión pico/volumen, sensibilidad KGE–CN, duración + balance anual, tablas por evento y global (PNG + CSV) | Con QuitoCCP2: KGE 0,569/0,593; NSE 0,253/0,212; PBIAS 5,1/9,0 % | Hecho; métricas = mismas funciones del barrido (prueba automática). Falta verificar las cifras con QuitoCCP2 en PC2 |
| C1 | P1 | 2 · GEE / 5 · Terreno | MDT 40 km y CN 10 km alrededor del sitio | Ámbito «cuenca activa + margen» | El área simulada cubre la cuenca | Hecho |
| C2 | P2 | 2 · GEE | GEOGLOWS por cercanía al sitio | Búsqueda en la salida de la cuenca; DSContArea si se da la capa GEOGLOWS v2 | Tramo en la salida y diferencia de área reportada | Parcial: la API no da DSContArea; se compara con la capa v2 del usuario |
| C3 | P2 | 5 · Terreno | «No hay terreno regional» con MDT de GEE | Reconoce `mdt_*` | Coincidencia con el MDT de GEE | Hecho |
| C4 | P2 | 0 · Preparación | Aceptaba `_resumen.csv` | Rechaza tablas resumen / < 30 fechas | Error explícito | Hecho |
| C5 | P2 | hidro · Cuenca | Delinear prellenaba el sitio | «Salida (aforo)» con lista de estaciones (INAMHI hidrométricas, caudales del proyecto) | La salida es el aforo elegido | Hecho |
| C6 | P3 | hidro · Cuenca | Solo HydroSHEDS | Red de ríos propia (GEOGLOWS v2 u otra) para quemar | Delineación con la red elegida y contraste de área | Hecho (la capa GEOGLOWS v2 la aporta la persona) |
| C7 | P2 | hidro · Cuenca | Solo aviso de distancia | Botón «Mover el sitio a la cuenca» en el mismo aviso | — | Hecho |
| C8 | P2 | Calibración | Columnas fijas | Autodetección desde la vista previa | — | Hecho |
| C9 | P2 | Calibración | Fuente de lluvia «INAMHI» | Vacía y obligatoria | — | Hecho |
| C10 | P1 | Calibración | El barrido fallaba con eventos sin lluvia | % de días con lluvia y cobertura por evento; excluidos con aviso; < 80 % marcado | El barrido corre y lista los excluidos | Hecho |
| C11 | P2 | Calibración | «Proponer eventos» borraba roles | Conserva roles editados | — | Hecho |
| C12 | P2 | Calibración | Una sola estación | Lluvia areal Thiessen dinámico o IDW con pesos | Pesos = definición de Thiessen (prueba con malla independiente) | Hecho |
| C13 | P2 | Calibración | Q base constante | Recesión exponencial; k estimado o barrido | k sintético = 8 d se recupera | Hecho |
| C14 | P3 | Calibración | Sin aviso | Aviso de lag < 24 h con paso diario | — | Parcial: calibración horaria pendiente |
| C15 | P3 | Calibración | — | Balance anual por año; incoherentes marcados | — | Hecho (en R4) |
| C16 | P2 | 5 · Terreno | AOI 600 m centrado en el sitio | AOI = recuadro de la cuenca ≤ 250 000 celdas; cobertura de la cuenca en la coincidencia | — | Hecho |
| C17 | P2 | 5 · Terreno | Errores de registro poco visibles | Resultado siempre visible e historial (éxito/error) | — | Hecho |
| C18 | P1 | 7 · Corrida | Sin aviso de cuenca fuera | Chequeo «la cuenca queda X % fuera del área simulada» | — | Hecho |
| C19 | P2 | 7 · Corrida | CN de GEE sin relación con el calibrado | Chequeo con ambos y ⚙ «CN para la 2D» (ráster/calibrado) | — | Hecho |
| C20 | P2 | 8 · Evaluación | Sin alertas | Alertas con causas | — | Hecho |
| C21 | P3 | 7 · Corrida | — | Aviso DSM + ⚙ relleno de depresiones | — | Hecho (MDT sin edificaciones: pendiente) |
| C22 | P3 | 8 · Evaluación | «Calado medio de celda máximo» | «Calado máximo de celda» | — | Hecho |
| C23 | P2 | 4 · IDF | Punto = sitio | Punto = sitio o centroide de la cuenca (elección explícita) | — | Hecho |
| C24 | P2 | 11 · Entregas | Sin calibración ni cuenca | `01_resultados/hidro_calibracion/` (aceptadas, último barrido, observaciones, lluvia areal) y `shapes/cuenca_activa/` | — | Hecho |
| C25 | P2 | 11 · Entregas | ENSO solo con CHIRPS de la caja | Más la lluvia registrada de la cuenca, rotulada | — | Hecho |
| C26 | P2 | Calibración | Rangos volvían a los de fábrica | Últimos rangos conservados; aviso de óptimo en el borde al aceptar | — | Hecho |

Además (no estaban en la lista): carga masiva del premódulo; corrección de una carrera de escritura de `estado.json` en Windows que podía tumbar corridas y descargas; Time of Emergence y WRF (beta 1).

## 6. Pendientes conocidos
- Calibración horaria (C14) con los datos horarios EPMAPS.
- DSContArea automático de GEOGLOWS v2 (C2) sin capa del usuario.
- MDT sin edificaciones (C21).
- Validar el lector WRF con salidas reales.
- Verificar R4 con las cifras de QuitoCCP2 y R1 con Copilot.
