# UCEclima Epsilon · plan (abierto el 25-oct-2026)

Después de Alfa → Beta → Gamma → **Delta 5.0.0** (publicada en Zenodo y en el artículo de *Water*) viene **Epsilon**. Se instala aparte y no borra Delta.
Estado (25-oct-2026): **E1 hecho** (E1.1–E1.5 con pruebas; E1.6 caso real a 1 m pendiente: falta un MDT de 1 m real). Hechos también: gráficas principales de CMIP6, validación 1–4 y la maqueta de contaminantes (base).
Reglas, las mismas de Delta:
- respaldo de la versión estable antes de tocar nada;
- al renombrar, solo cambian versión, AppId, instalador y textos (sin refactors);
- una prueba por mejora;
- probar como usuario nuevo;
- una corrida a la vez;
- no inventar datos.

## E1 · MDT de alta resolución (1–10 m) de punta a punta
Objetivo: que un MDT de dron, LiDAR o IGM (1–10 m) sirva para estudios de detalle (un poblado, un puente, un tramo de río) conectados con la hidrología de toda la cuenca.

| # | Mejora | Por qué | Dónde (hoy) |
|---|---|---|---|
| E1.1 | **Hidrograma de entrada en la frontera** (caudal de hidro o de una corrida 2D gruesa → borde aguas arriba del área fina) | Con un área pequeña hoy solo entra la lluvia que cae dentro; falta el agua que llega de arriba | `climanet/hydraulics.py` (fronteras `free_outflow`/`closed`), `pipeline.py` |
| E1.2 | **Rellenar depresiones** en el dominio hidráulico, como opción declarada (G2) | La interfaz lo ofrece pero el núcleo lo rechaza; en Chalpi queda almacenado ~90 % del volumen en depresiones del GLO-30 | `configuracion.py` (`fill_sinks`), `pipeline.py` |
| E1.3 | **Picos anómalos de velocidad**: marcar celdas con v irreal (somera y empinada), indicar dónde ocurren y excluirlas de los resúmenes (resto de G17) | En Tambo (Gamma, h ≥ 1 cm) salieron 36–57 m/s; Delta ya diagnostica solo con h ≥ 5 cm, pero falta marcarlas | `accel.py`, `hydraulics.py`, resumen y visor |
| E1.4 | **Hidrograma 2D en la salida** y comparación con el de hidro (G4) | Permite ver si la 2D y el modelo de eventos mueven el mismo volumen y pico | `worker.py`, mapa y visor |
| E1.5 | **Flujo guiado para MDT propio**: recorte del GeoTIFF al área, sugerencia de celda y de solver *subgrid* (celda 5–10 m con resolución fina de 1 m), y avisos de DSM (árboles, casas), puentes que tapan el cauce, datum elipsoidal frente a EGM2008 y lecho no visible | Hoy se puede, pero exige saber qué elegir | `terreno_import.py`, módulo Terreno |
| E1.6 | **Caso real de prueba a 1 m** | Validar todo lo anterior con datos reales | Falta un MDT de 1 m real (lo aporta el usuario) |

Pruebas previstas: conservación de masa con hidrograma de entrada conocido; relleno de depresiones en un MDT sintético con pozos; detección de celdas con v anómala; hidrograma de salida igual al balance de masa; un caso real pequeño (≤ 0,25 km² a 1 m o subgrid).

## Siguientes mejoras de Epsilon
Por definir con el usuario, después de terminar el artículo. Candidatas de PENDIENTES_DELTA.md:
- G3 tiempo simulado adaptativo;
- G6/G7 premódulo;
- G9 lo que hace un agente se ve en la ventana;
- G14 WRF real;
- G16 informe PDF;
- G19 pesos;
- G20 capa Y − X en el visor.

Otras ideas que salieron:
- corregir la escala de color del mapa 2D (empieza en blanco y el agua se pierde);
- cámara inicial del visor acercada a donde hay agua.

## Hallazgos del 25-oct que guían lo siguiente
- Chalpi, 2D con CN calibrado: el hidrograma en la salida es pequeño (pico 0,8 m³/s frente a 8,9 de hidro) porque una depresión de 3 m del GLO-30, 7 celdas aguas arriba de la salida, retiene el agua. Rellenar solo las de hasta 1 m no la toca.
- Validación E29 (17–19 dic 2015): KGE −0,41, CSI 0,00. La lluvia areal diaria (32 mm) con CN 55 genera unos 2 mm de escorrentía, frente a los ~18 mm observados.
- Sentinel-1 marcó 3 632 celdas de 60 m como agua: probablemente muchas son falsas (páramo húmedo, sombras de ladera). Falta una máscara de pendiente o HAND.

## Siguientes (doctorado)
- MDT de 1 m real + subgrid; humedad antecedente activa en la 2D; lluvia horaria (WRF o estaciones); máscara HAND para Sentinel-1.
- Contaminantes: acoplar U y h de la corrida 2D, derrames continuos, sustancias reales, ecuación de Disley et al. (2015) y calibración de K con trazadores.
