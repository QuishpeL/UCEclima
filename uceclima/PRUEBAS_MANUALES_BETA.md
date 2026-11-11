# Pruebas manuales · UCEclima beta 3

Caso de referencia: `QuitoCCP2` (PC2). Marca cada prueba con ✔ o ✘ y anota lo observado. Las pruebas automáticas (`python uceclima\correr_pruebas_uceclima.py`, 149 al 17-oct-2026) no reemplazan estas.

## R1 · agentes
1. Crear un proyecto nuevo. Verificar en su carpeta: `.mcp.json`, `.vscode\mcp.json`, `AGENTS.md`, `CLAUDE.md`, `.claude\settings.local.json`.
2. Botón **Agente → VS Code + Claude Code**. En VS Code abrir el panel de Claude Code y pedir «lista las herramientas de uceclima». Esperado: más de 30 herramientas; `estado` devuelve el proyecto abierto.
3. Cerrar UCEclima y pedir al agente «estado». Esperado: UCEclima arranca solo y abre ese proyecto.
4. En una PC con GitHub Copilot: **Agente → VS Code + Copilot**, chat en modo Agente → herramientas → `uceclima` visible.

## R2 · sitio
5. En QuitoCCP2: **1 · Proyecto → Sitio** lon −78,0968, lat −0,2998 → Guardar. Esperado: aviso de descargas desactualizadas; procedencia con el sitio anterior.
6. **5 · Terreno → Área: cuenca activa + margen → MDT de Earth Engine**; luego suelo y CN/Manning. **7 · Corrida → Comprobar**: «La cuenca activa está completa dentro del área simulada».
7. **Centrar en la cuenca activa**: el sitio pasa al interior de Chalpi.

## R3 · nombres
8. Crear «quitocc» → carpeta `quitoccucec`. Renombrar a «Quito CC 2» → carpeta `quito_cc_2ucec`, con el historial intacto.

## R4 · comparación de la calibración
9. **hidro → Calibración → Abrir barrido anterior** (el aceptado) → **Ver** en la combinación CN 50, λ 0,05, lag 6 h, PRF 484. Esperado: KGE 0,569 / 0,593; NSE 0,253 / 0,212; PBIAS 5,1 / 9,0 %; 4 figuras; tabla por evento con 37 eventos (25 ajuste, 12 validación, 1 excluido).
10. Aviso de borde: «CN = 50 en el borde del rango [50, 90]» y «lag 6 en el borde».
11. Balance anual: 2020 marcado (lluvia 2160 mm, escorrentía 574 mm, coeficiente bajo).

## C · correcciones
12. C4: cargar en el premódulo un `_resumen.csv` → rechazado.
13. C10: barrido con un evento sin lluvia → se excluye con aviso, no falla.
14. C12: **Lluvia areal → Ver estaciones** (C16, P46, P64, P74, P75) → **Calcular y usar**. Esperado con las 5: P64 ≈ 0,29 · C16 ≈ 0,26 · P46 ≈ 0,21 · P74 ≈ 0,12 · P75 ≈ 0,12.
15. C13: **Estimar k** → k en días; barrer con k y sin k; comparar el evento E37 (oct-2018) en el mosaico.
16. C2: 2 · GEE → GEOGLOWS «en la salida de la cuenca activa» con la capa de ríos GEOGLOWS v2 (VPU 605) → área de drenaje ≈ 101,6 km² frente a 98,7 km² (≈ 3 %).
17. C5: Cuenca → Salida (aforo) → elegir H13 en la lista → coordenadas −78,0851 / −0,3552.
18. C18/C19/C21: Comprobación previa con la cuenca fuera del área, con calibración aceptada y con DSM → los tres avisos.
19. C20: Evaluación de la corrida con 13,8 m/s, 57,7 % y 90,9 % → tres alertas con causas.
20. C23: 4 · IDF → Punto «centroide de la cuenca activa» → cambia la pluviográfica de referencia.
21. C24/C25: 11 · Entregas → `01_resultados\hidro_calibracion\` y `shapes\cuenca_activa\`; `03_ENSO\lluvia\lluvia_cuenca_registrada_mensual`.
22. Premódulo masivo: carpeta con 127 estaciones + catálogo → 127 series con coordenadas en menos de 1 min.
