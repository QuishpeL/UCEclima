# Módulo CMIP6 · cambio climático (Y) — protocolo v2 (13-oct-2026)

**Estado:** implementado y probado con datos sintéticos de respuesta conocida y con el caso real Mazar. **Todo lo de Y es proyección bajo supuesto**, no predicción.
La línea base (X, condiciones existentes) fue **asumida por decisión del usuario el 13-oct-2026** («asumimos que está correcto, igual el programa permite mejorar»): **no está calibrada ni validada**. Solo se usa **SSP5-8.5** (decisión del usuario).

## Qué hace (un paso a la vez)
1. **Compuerta**: sin decisión registrada del usuario, nada se descarga ni se calcula (`/api/cmip6/compuerta`, `asumir_baseline`).
2. **Histórico** NEX-GDDP-CMIP6 (33 modelos, 1981–2014) en la celda de 0,25° del sitio, vía Earth Engine (`getRegion`).
3. **Referencia**: CHIRPS (media de la celda NEX, 1981–2025). CHIRPS es satélite, **no es medición de campo**.
4. **Evaluación** (`cmip6_sesgo.evaluar`): ranking y pesos **ClimWIP** (desempeño × independencia), QQM mensual con ajuste de frecuencia de días húmedos, validación cruzada **impar/par** y mitades 1981–97 ↔ 1998–2014, EQM de las entregas Machala/Gualaquiza como comparador, ensamble por **quintiles** (EMME/WMME/QMME-lite).
5. **Futuro** 2015–2100 de los modelos que reúnen ≥ 90 % del peso.
6. **Factores** (`cmip6_sesgo.factores`): QDM por bloques; factor = futuro/histórico del propio modelo, ambos corregidos; ventanas **2040–2069** y **2071–2100**; verificación independiente 2015–2025.
7. **Escenarios Y**: `cc_ssp585_<2040-2069|2071-2100>_<mediana|p10|p90|mejor|cuantiles>` = IDF oficial × factor(Tr). Una corrida por vez.
8. **Base de datos** SQLite del proyecto (`/api/bd/*`, solo lectura SQL).

## Reglas matemáticas (revisión Codex, 13-oct-2026)
- **Completitud**: un año/mes cuenta solo con ≥ 90 % de los días **esperados** del calendario del producto (fechas ausentes = faltantes; 29-feb no esperado en productos de 365 días; calendarios de 360 días no soportados → modelo descartado con motivo). Meses aceptados con huecos se normalizan y se cuentan. Se reportan años excluidos y cobertura efectiva (`metricas_modelos.csv`, `resumen_analisis.json → cobertura`).
- **Pesos**: finitos, ≥ 0, suma 1. Reglas explícitas (devueltas en `reglas_pesos`): modelo único → peso 1; desempeño perfecto (σ_D = 0) → mediana de los D positivos, y si todos son 0 el desempeño no discrimina; modelos idénticos → independencia 1/n; desbordamiento → escala logarítmica; valores no finitos → error (el modelo se excluye y se reporta, **nunca** se sustituye). Los σ son heurísticos de las entregas previas, **no** la calibración de σ del ClimWIP original.
- **QDM**: preserva la señal relativa (probado con +25 % conocido); mes sin días húmedos históricos → sin señal de cambio: se aplica solo el QQM del mes y queda registrado (`avisos`); cola fuera del soporte con razón constante (finita, monótona); el EQM del agente acota la cola al máximo observado (documentado).
- **Tr100**: se informan **años efectivos**, intervalo (bootstrap p5–p95, Gumbel por momentos) y estado. Con < 8 máximos no se estima; con < 30 años o Tr > n es **extrapolación no certificable**.
- **IDF**: **supuesto exploratorio de cambio uniforme por duración** (el factor de 24 h se aplica a todas las duraciones). No demuestra el cambio subdiario; la IDF resultante **no está validada** y el mapa/hidrograma **no es predicción**. Texto en `SUPUESTO_IDF` y en cada escenario.

## Resultados reales Mazar (código corregido)
33 modelos válidos, cobertura 100 %, ninguna regla degenerada activada; 26 modelos reúnen el 90 % del peso; 32 con futuro. Factor Tr100 de 24 h (QQM/QDM, mediana ponderada, p10–p90): 2040–2069 **×1,20** (1,03–1,44); 2071–2100 **×1,37** (1,06–1,75). Tr100 observado CHIRPS 89,9 mm (IC 77–98); ensamble corregido 92,5 mm (IC 76–106): extrapolación no certificada. Verificación 2015–2025: el original NEX sobreestima (+14 %); QQM/QDM subestima (−12 %) y reduce el RMSE de cuantiles de 10,7 a 1,7 mm.

## Límites pendientes
Línea base no calibrada ni validada · CHIRPS ≠ verdad de campo · sin respaldo independiente para intensidades subdiarias · Tr100 no certificable (30–34 años) · σ de ClimWIP heurísticos · NEX-GDDP ya corregido por BCSD y subestima extremos (Thrasher et al. 2022) · calibración con 34 años puede empeorar a un modelo ya bueno · sin pruebas de estacionariedad.

## Referencias
Brunner et al. 2020, *Earth Syst. Dyn.* 11:995 (ClimWIP) · Cannon, Sobie & Murdock 2015, *J. Climate* 28:6938 (QDM) · Thrasher et al. 2022, *Sci. Data* 9:262 (NEX-GDDP-CMIP6) · Song, Shiru & Chung 2025, *Mach. Learn.: Sci. Technol.* (ensamble por quintiles) · entregas Machala/Gualaquiza (EQM, IDF × factor por Tr).

## Pruebas
`python uceclima/correr_pruebas_uceclima.py` · `tests/test_cmip6_matematica.py` (19 casos: año de un solo día, fechas ausentes, mes parcial, calendario 365, modelo único, desempeño cero, modelos idénticos, no finitos, QDM con señal conocida, mes seco, ceros, extremo fuera del soporte, Tr100) y `tests/test_cmip6.py`.
