# CHANGELOG · UCEclima beta

## 7.0.0-omega · 27-oct-2026 (instalación «UCEclima Omega»; no reemplaza a Epsilon) · versión consolidada con el caso real Milagro (M0037, evento del 26-oct-2026)
Corregido (encontrado modelando un caso real paso a paso; cada uno con prueba en `tests/test_epsilon.py`)
- G12 · Premódulo: lecturas a horas fijas (07/13/19 h) se agregan a diario esperando tantas lecturas como horas de lectura (antes esperaba 4 por día y anulaba todos los días).
- G13 · Premódulo: 888 y 999 son «sin dato» de INAMHI en lluvia (no en caudal); antes se sumaban como lluvia (años de 10 000–74 000 mm).
- G14 · CN y Manning encuentran las capas de suelo bajadas por la descarga «sitio» (`sitio_*/suelo`); antes fallaba «Primero baja las capas de suelo».
- G15 · Evento observado REAL horario de más de 12 h (hasta 96 h), marcado `real_largo`; la corrida lo acepta solo si se estima ≤ 30 min.
- G16 · La estimación de la corrida cuenta la duración de los hidrogramas de entrada.
- G17 · Hidrogramas de entrada y evento observado desde la interfaz: tarjeta «0 · Forzamiento» en Corrida; `POST /api/corrida/entradas` (valida t = 0, Q final = 0 y punto dentro del área) y `GET /api/corrida/forzamiento`.
- G18 · La ventana del evento se escribe en HORA LOCAL de la estación (antes se tomaba como UTC sin avisarlo: 5 h de desfase en Ecuador); se devuelve en local y UTC.
- G19 · Si la salida de la cuenca activa queda fuera del área de cálculo, no se pide la sección y se avisa (antes la corrida fallaba al arrancar).
- G20 · Humedad antecedente declarada (`cn_amc_2d`: I/III/auto NEH-4) también para el CN ráster de la 2D; agua e impermeable (CN ≥ 98) no cambian. Con «auto» usa la estación del evento.
- G21 · El registro de una corrida de evento observado dice «Evento <id>» (antes «diseno_idf_historica TrNone»).
- G23 · Cuencas externas (hidrograma del núcleo con la misma IDF y Tr de la 2D) declarables desde la API (`/api/corrida/cuencas_externas`) y la tarjeta «0 · Forzamiento»; la estimación de la corrida cuenta su cola.
- G24 · Tope de horas simuladas según el tiempo estimado: hasta 96 h si se estima ≤ 30 min (antes 12 h fijas: una tormenta de diseño de 24 h no se podía correr).
- G22 · Borde de salida libre: se CIERRA a ≤ 10 celdas de cada hidrograma de entrada (`borde_cerrado_entradas_celdas`, 0 = desactivado), como la línea de condición de entrada de HEC-RAS. Antes el borde libre devolvía al exterior gran parte del caudal que entraba cerca del borde (caso Milagro: el río de 156 m³/s casi no cruzaba el dominio). Sin hidrogramas de entrada, nada cambia.
- G25 · Sección de salida pegada a un borde: el río sale por ese borde (sección perpendicular); antes podía quedar paralela al borde y medir casi nada.
Añadido · Omega
- O1 · FABDEM (GLO-30 sin bosques ni edificios; Hawker et al. 2022, Environ. Res. Lett. 17 024016) como terreno de Earth Engine («producto»: glo30 | fabdem), con el método validado del agente CLIMALAB: sin `.resample()` en GEE, verificación contra la media nativa del servidor, respaldo EPSG:4326 + bilinear local y rechazo de un MDT constante. Se registra como MDT (no DSM). Licencia CC BY-NC-SA 4.0.
- O2 · Filtro DECLARADO de picos (`/api/terreno/filtrar_picos`, botón en Terreno): celdas que superan la mediana local en más del umbral → mediana; MDT nuevo + informe; nada se sobrescribe.
- O3 · Visor 3D: ríos HydroSHEDS del proyecto siempre visibles (casilla «Ríos»), grosor por área aportante.
- O4 · Contaminantes con entrada propia en el menú; estilo minimalista carboncillo (vista isométrica y planta).
- O5 · Mapa estilo RAS automático y sobrio (solo hospitales y barrios rotulados, íconos pequeños, fondo blanco; el título dice el terreno real: FABDEM, GLO-30 o propio) al terminar cada corrida (satélite + ríos + calles + edificios expuestos + equipamiento OSM + estación + lugar; Tr o evento y calado p99 en el título). Si no hay red, la corrida sigue completada y se avisa.
- O6 · Informe HTML autocontenido dentro de cada entrega (`informe.html`): resumen, datos, terreno, cuencas y entradas, resultados por corrida con su mapa e hidrograma, CMIP6 si existe, archivos y limitaciones; todas las cifras salen de los resultados.
- El hidrograma de la salida dice «evento observado» o «diseño Tr N» según la corrida.
- O7 · Quemar ríos en el terreno (`/api/terreno/quemar_rios`, botón en Terreno): la red HydroSHEDS del proyecto se graba con profundidad DECLARADA (z = mínimo 3×3 − profundidad, ancho en celdas). Necesario con FABDEM, que suaviza los cauces (caso Milagro: encajonamiento 0,04 m en la entrada del río; con 2 m la cuenca externa pasa el control de cauce).
- O7b · La quema de ríos fuerza el descenso aguas abajo (≥ 1 mm por celda, tramos de menor a mayor área aportante): cauce continuo hasta el borde y sin pozas en confluencias (Milagro: sin esto, la ruta D8 de la entrada no salía del dominio). No se quema dos veces el mismo terreno.
- G26 · CMIP6 en la Costa: el QQM mensual descartaba los 34 modelos porque agosto casi no tiene días húmedos (Milagro). Ahora, si un mes tiene < 20 días húmedos, sus cuantiles húmedos usan una ventana estacional ±1…±3 meses (Themeßl et al. 2011); la frecuencia de días secos sigue siendo la del mes; queda en `avisos`.
- G27 · Área de cálculo alineada a la malla del terreno y múltiplo de la celda: el área sugerida se alinea sola; si la persona da un área desalineada se avisa (no se mueve en silencio). Antes (Milagro) un desfase de 24–29 m y un lado de 10 000 m con celdas de 30 m hacían que el promedio de carga borrara el cauce quemado de una celda (encajonamiento de +1,9 a −0,2 m).
- O8 · Figuras en INGLÉS solo para los papers (`figuras_idioma.py`; `cmip6_figuras.todas(idioma="en")`, `mapa_referencias.mapa(idioma="en")`): copia `_en.png` traducida, punto decimal, aviso de textos sin traducir; el programa, los informes y el manual siguen en español.
- O9 · Ríos «merge» MDT + HydroSHEDS (`terreno_import.rios_merge`, método del agente CLIMALAB): HydroSHEDS da la estructura y el MDT la posición; cada tramo se retraza por la ruta de máxima acumulación D8 del MDT (penalizada lejos de la guía) y se suaviza. La quema, el mapa estilo RAS y el visor 3D usan estas líneas si existen. Antes los ríos HydroSHEDS (~500 m) se veían «en escalera» y no calzaban con la imagen satelital (pedido del usuario, Milagro).
Pruebas: `tests/test_epsilon.py` (27); suite completa sin fallos.

## 6.0.0-epsilon · 25-oct-2026 (instalación «UCEclima Epsilon»; no reemplaza a Delta)
Añadido · E1 MDT de alta resolución (1–10 m) de punta a punta
- E1.1 Hidrogramas de entrada desde CSV (`entradas_hidrograma`: nombre, csv con t_s y Q_m3s, punto xy): deben empezar en t = 0 y terminar en Q = 0 (la cola no se inventa); el volumen integrado se verifica contra el hidrograma.
- E1.2 Relleno de depresiones como opción declarada (`fill_sinks`, `fill_sinks_max_m`: 0 = todas; si no, solo las de profundidad ≤ umbral). Antes la interfaz lo ofrecía pero el núcleo lo rechazaba (G2). Informa depresiones rellenadas y conservadas, almacenamiento quitado y escribe `relleno_depresiones_m.tif`.
- E1.3 Velocidades anómalas (`v_anomala_ms`, 10 m/s por defecto): se marcan sin corregir, con ubicación, velocidad máxima robusta y p99; ráster `v_anomala.tif` (resto de G17).
- E1.4 Hidrograma 2D en la salida de la cuenca activa: sección transversal según la dirección D8 (`seccion_semiancho_celdas`), `hidrograma_salida_2d.csv` y `hidrograma_salida.png`, comparado con el hidrograma de hidro (SCS-CN + HU con los parámetros aceptados, misma formulación que `matematica_propia.uh_scs`) (G4).
- E1.5 Guía de MDT propio: la inspección sugiere celda, área máxima y solver, y avisa de DSM, puentes, datum y lecho; la celda mínima del modelo baja de 2 m a 0,5 m.
Añadido · CMIP6 (`cmip6_figuras.py`, `/api/cmip6/figuras`, `/api/cmip6/figura.png`)
- Bondad de la corrección QQM con validación cruzada impar/par (ciclo anual y Q-Q de totales mensuales) del mejor modelo.
- Time of Emergence por indicador (total anual, CDD, Rx1day): serie solo-modelo, señal de 11 años, ±1σ/±2σ, franja magenta p10–p90 de todos los modelos y ToE solo-modelo.
- Figura S/N del ensamble en tamaño grande (4 × 3 paneles).
Añadido · Validación de la 2D con observaciones (`validacion_2d.py`, `/api/validacion/*`, tarjeta en 8 · Evaluación)
- Por defecto: (1) caudal observado en la salida frente al hidrograma 2D de una corrida con evento real (KGE, NSE, error de pico y de volumen); (2) mancha de agua Sentinel-1 (Earth Engine, VV antes/después, agua permanente JRC excluida) → CSI, aciertos y falsas alarmas.
- Abiertas: (3) manchas de otras fuentes (Global Flood Database, Copernicus EMS, SNGR, propias) y (4) evidencia de campo (marcas de agua, fotos, testimonios; calado y mojado/seco), contrastadas contra la misma corrida en una tabla única.
- Búsqueda de eventos reales con pasada de Sentinel-1 cerca del pico y preparación de la corrida del evento (lluvia areal diaria, desagregación uniforme declarada); las corridas de validación declaradas admiten hasta 96 h si se estiman ≤ 30 min (las normales siguen con 12 h).
- Caso real (copia de Chalpi, E29 17–19 dic 2015, celda 60 m): caudal KGE −0,41, NSE −0,77, el 2D movió 1 512 m³ frente a 1,82 millones observados; Sentinel-1 del mismo día: CSI 0,00. Resultado negativo y honesto: CN 55 con lluvia diaria y almacenamiento en depresiones no reproducen esa crecida.
Añadido · Maqueta isométrica de dispersión de contaminantes (base, `contaminantes.py`, `/contaminantes`)
- Derrame instantáneo en un tramo rectangular: U y u* por Manning, K longitudinal (Elder 1959, Fischer 1975, Seo y Cheong 1998, Deng et al. 2001, Kashefipour y Falconer 2002), εt = 0,6 h u*, solución 2D con orillas reflejantes y decaimiento; animación, lecturas y referencias verificadas en Crossref. Pedagógica, sin calibrar.
Añadido (25-oct, tarde) · Prueba de estrés para el territorio
- `cn_amc_2d` (ninguna/auto/I/III): humedad antecedente declarada sobre el CN calibrado en la 2D (auto = regla NEH-4 de 5 días).
- `cn_2d_declarado`: CN discrecional declarado por la persona para una prueba de estrés (queda rotulado «no calibrado»).
- Corregido: la sección de la salida toma la dirección del río siguiendo 6 celdas aguas abajo (con celdas gruesas quedaba lateral).
- E29 (Chalpi): CN 55 → KGE −0,43; AMC III (74,1) → −0,55; CN 92 declarado (páramo saturado) + relleno → KGE 0,15, NSE 0,18, 47 % del volumen.
Sin cambio por defecto: sin `salida_xy`, `entradas_hidrograma` ni `fill_sinks`, la corrida es la de Delta (mismas cifras; verificado en Chalpi: 626 557,37 m³).
Pruebas: `tests/test_epsilon.py` (13).

## 5.0.0-delta · 23-oct-2026 (instalación «UCEclima Delta», última versión; no reemplaza a Gamma)
Añadido
- D1 Recesión del caudal base en el barrido: `k_rec="auto"` prueba Q base constante y k estimados de recesiones sin lluvia (p25, mediana, p75); el registro informa el efecto en el NSE (`efecto_recesion`).
- D2 Calibración horaria cuando caudal y lluvia son horarios (paso detectado; si no, diario como Gamma). Lag por defecto 6–120 h; aviso cuando el óptimo cae en el borde del rango.
- D3 Humedad antecedente, siempre opción declarada y nunca por defecto: AMC I/II/III con lluvia de 5 días (35,6 / 53,3 mm) o índice de lluvia antecedente continuo (k 0,9/día).
- D4 Control de la lluvia: «lluvia dudosa» si la escorrentía directa supera a la lluvia del evento; avisos de error de volumen > ±100 %, cobertura < 80 % y una estación con > 80 % del peso.
- D5 Benchmark (`benchmark.py`, `/api/calibracion/benchmark`): referencia sin habilidad (Q base constante) y GR4J diario con ETP constante declarada (o «calibrada», explícito), en las mismas ventanas y métricas. Etiqueta «referencia de comparación, no calibrada por la persona».
Corregido (D6)
- G5 premódulo: columnas con 30–60 % de datos se cargan con aviso (antes se pedía confirmar).
- G8 servidor: puerto exclusivo en Windows; si está ocupado se usa el siguiente libre y se escribe en `puerto.txt`.
- G10 contraste HydroSHEDS: tramo de área más parecida, no el de mayor área.
- G11 cambio de sitio: las descargas de ámbito «cuenca» no se marcan como desactualizadas.
- G17 velocidad máxima diagnosticada solo con h ≥ 5 cm (antes 1 cm).
- G22 aviso de saltos de unidad (mediana anual ×200) al registrar un caudal; no corrige nada.
Sin cambio por defecto: con k constante y humedad «ninguna» el barrido da exactamente los valores de Gamma (Chalpi KGE 0,599/0,686; Tambo 0,441/0,615).
Pruebas: `tests/test_delta.py` (10).

## 4.0.2-gamma · 22-oct-2026 (actualiza «UCEclima Gamma»; versión publicada en Zenodo)
Corregido
- G21: el servidor ya no se cierra solo mientras un agente o un script trabaja por la API. Toda petición a /api/ cuenta como señal de vida; antes se cerraba a los 2 minutos sin la ventana abierta.
- G23: `/api/estado` y `/api/corrida/estado` respondían 500 cuando `tasklist` devolvía caracteres de consola (cp850). Ahora se lee en bytes.
Documentado
- G22: cambios de unidad no documentados en 18 de 49 series de caudal de EPMAPS. Hay que revisarlas año por año antes de calibrar; el control automático en el premódulo queda pendiente.
- Segundo caso de aplicación: cuenca Tambo (H18, Cotopaxi).

## 4.0.1-gamma · 21-oct-2026 (actualiza «UCEclima Gamma»)
Cambiado
- ToE (G18), método del ensamble de Machala/Gualaquiza:
  - Señal: media ponderada de las anomalías de los modelos.
  - Ruido: √(variabilidad interna sin tendencia² + dispersión entre modelos²), con base 1981–2014.
  - Índices nuevos: CDD, CWD, SPI-12 mínimo, meses con SPI-3 ≤ −1, R95pTOT y SDII.
  - Acuerdo de signo entre modelos. Ya no se mezclan modelos que emergen en sentidos opuestos.
- Visor 3D (G20, parcial):
  - «Fantasmas» pasa a «Escenarios plausibles».
  - La capa Y CMIP6 va encima, en magenta intenso, solo donde Y supera a X.
  - Al abrir una corrida X, las Y vienen marcadas.

## 4.0.0-gamma · 21-oct-2026 (instalación «UCEclima Gamma»)
Esta versión sale de recorrer el ciclo completo con datos EPMAPS de Quito (cuenca H13 Chalpi Grande). Se instala aparte: no reemplaza a la Beta 3.

Añadido
- G15 Película del calado en el visor 3D:
  - El núcleo guarda una foto del calado cada 5 min simulados (`fotos_min`) sin alterar el cálculo, en `evolucion_calado.npz`. La API la entrega en `/api/visor/fotos`.
  - En el visor: botón «▶ Evolución en el tiempo», barra de tiempo, curva de volumen y **cámara lenta en la crecida** (hasta ×0,2 cuando el volumen pasa del 40 % de su máximo).
- CMIP6: campo «Modelos». Vacío usa todos, que es lo normal; con una lista se descarga solo esa (ensamble pedagógico, con aviso).
- Documento `PENDIENTES_GAMMA.md` con lo que queda del ciclo (G2–G16).

Corregido
- G1 La corrida 2D con «CN calibrado» ahora usa también el **λ calibrado**; antes usaba λ = 0,20 fijo, y con CN 55 y λ 0,05 la escorrentía salía 0. El resumen de cada corrida declara `ia_ratio` y `cn_origen`.
- El botón de CMIP6 ya no dice «33 modelos» fijo.

Pruebas: `test_gamma_lambda` y `test_gamma_visor`; batería completa de 159 pruebas sin fallos.

## 3.3.0-beta3 · 17-oct-2026 (instalación «UCEclima Beta 3»)
Añadido
- R2 editar el sitio del proyecto o centrarlo en la cuenca activa; descargas dependientes marcadas como desactualizadas (`registro/desactualizadas.json`).
- R3 carpetas de proyecto con sufijo `ucec`; renombrar sin perder historial; lista de proyectos de la carpeta de proyectos.
- R4 comparación de la calibración: mosaico de hidrogramas, dispersión pico/volumen, sensibilidad KGE–CN, curva de duración y balance anual, tablas por evento y global (PNG + CSV); también en cada aceptación.
- C12 lluvia areal de la cuenca: Thiessen dinámico o IDW con pesos (`lluvia_areal.py`).
- C13 caudal base con recesión exponencial; k estimado de los tramos de recesión o barrido.
- C2 GEOGLOWS en la salida de la cuenca; DSContArea con la capa GEOGLOWS v2 del usuario. C6 red de ríos propia para quemar.
- C5 salida (aforo) desde una lista de estaciones; C7 mover el sitio desde el aviso de cuenca lejana.
- C17 historial de registros del terreno; C19 «CN para la 2D» (ráster o calibrado); C20 alertas en Evaluación; C21 aviso DSM; C23 punto IDF en el centroide de la cuenca.
- C24 la entrega incluye calibración, observaciones, lluvia areal y la cuenca activa; C25 ENSO con la lluvia registrada de la cuenca.
- C14 aviso de lag < 24 h con paso diario; C15 años de balance incoherente.
Cambiado
- El barrido y las gráficas usan la misma preparación de eventos (`calibracion.preparar`).
- C3 Terreno reconoce el MDT de Earth Engine; C16 compara con la cuenca activa.
- C22 «Calado máximo de celda».

## 3.2.0-beta2 · 17-oct-2026 (instalación «UCEclima Beta 2»)
Añadido
- R1 agentes VS Code + Claude Code y VS Code + Copilot (`.mcp.json`, `.vscode/mcp.json`, `AGENTS.md` = `CLAUDE.md`, autorización del servidor); el MCP arranca UCEclima y abre el proyecto.
- Carga masiva del premódulo (cientos de estaciones, segundo plano, tipo por defecto, catálogo de coordenadas).
- C1/C16 ámbito «cuenca activa + margen» para MDT, suelo y CN/Manning. C18 aviso de cuenca fuera del área 2D.
- C4 rechazo de tablas resumen; C8 autodetección de columnas; C9 fuente de lluvia obligatoria; C10 exclusión de eventos sin lluvia; C11 roles conservados; C26 rangos conservados y aviso de borde.
Corregido
- El servidor MCP del `.exe` respondía en cp1252: ahora UTF-8 y JSON ASCII.
- Carrera de escritura de `estado.json` en Windows («Acceso denegado») que podía tumbar corridas y descargas.

## 3.1.0-beta · 16-oct-2026 (instalación «UCEclima»)
- Time of Emergence en CMIP6; módulo WRF (leer salidas y preparar corridas).
