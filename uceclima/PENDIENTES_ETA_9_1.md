# Pendientes para UCEclima 9.1 (lo que no entró en Eta 9.0.0)

Numeración de `PENDIENTES_ETA.md` (prueba de novato con el río Yaguachi, 31-oct y 1-nov-2026). Todo lo demás de esa lista está en Eta 9.0.0 (ver CHANGELOG).

| Punto | Qué falta | Por qué no entró |
|---|---|---|
| 4 | Unir tramos 2D (unión cartográfica de varios `hmax.tif`) | Idea sin aprobar |
| 9, 9b | Calcular dentro del programa el CN, el Tc/lag (Témez y Kirpich) y la entrada de una cuenca externa, con cuadro de método y fuentes; contraste con el Q100 de GEOGLOWS | Necesita descargas nuevas y pruebas con casos reales |
| 13, 14 | Diagnóstico de la entrada externa: resolver planos con épsilon, exigir que la ruta recorra el dominio y salga por otro borde, caudal por borde, proponer entradas | Cambia la física de la entrada: requiere validación cuidadosa |
| 15 | Mostrar antes de ejecutar las horas que se van a simular y cortar cuando la entrada termina y el almacenamiento baja | Igual que 13–14 |
| 16 | Gráfica del hidrograma de cada entrada y factor de reducción areal declarado | — |
| 17 | Sección de la salida sobre el cauce del 2D y alerta de volumen negativo en el resumen (en 9.0 solo se explica en pantalla) | — |
| 20b | Que la ventana relance el servidor sola | En 9.0 el servidor ya no se cierra con la ventana abierta y la franja roja explica qué hacer |
| 24b–e, 32e | Un solo «río del proyecto» (shape subido o cauce del MDT) para delineación, salida, sección y mapas; botón para `rios_merge` | En 9.0 los mapas usan los ríos OSM y la red HydroSHEDS queda apagada |
| 25c | Activar cada botón de «Validación con observaciones» solo cuando su casilla tenga datos | — |
| 26c | Serie CMIP6 de la cuenca (promedio areal) además del punto | El paquete exportado ya declara que es un punto |
| 27 | Barra global con tarea, %, tiempo transcurrido y estimado, y bloqueo de botones que chocan | — |
| 29f | «Ver modelos uno por uno» (espagueti) en la serie anual | «Analizar extremos» ya muestra el mejor modelo solo |
| 31b | Corrida en lote de varios Tr, uno detrás de otro, con tiempo y disco estimados | Después del punto de control (ya en 9.0) |
| 11 | Mostrar el tamaño de `cn_tif` en KB y el % de celdas válidas | — |
