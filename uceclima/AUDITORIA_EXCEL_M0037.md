# Auditoría del Excel «Curva-IDF-de-M0037 - INAMHI.xlsx»

Atribución registrada (aportada por el usuario): **Caiza 2026**, fuente declarada «IDF INAMHI M0037». Referencia bibliográfica completa: **pendiente**.
Archivo: SHA-256 `116e87e3…0466`, 389 401 B, modificado por última vez el 7-oct-2026. Auditoría reproducible: `python -m uceclima.idf_excel` → `auditoria/M0037_excel_auditoria.json`.

## Qué contiene realmente (leyendo las fórmulas)
10 hojas: Registros Pluviómetro · Precip. Máx. Probable · Pearson III · LOG Normal · KOLMOGOROV-SMIRNOV · Tabla Pd · Tabla I · Regresiones I-D-T · Cte. Regresión Cuenca · Curvas IDF Cuenca.
Cadena de cálculo: **máximos anuales de 24 h (mm, 31 años, 1985–2015)** → Gumbel por momentos (α = √6/π·s; u = x̄ − 0,5772·α) → factor de intervalo fijo **1,13** →
coeficientes de duración de **Campos (1978)** (1 h = 0,30 … 24 h = 1,00) → intensidades Pd/d → regresión potencial `I = d·t^n` por Tr (2, 5, 10, 25) → `I = K·T^m / t^|n|`:

**I = 435,487 · T^0,18757 / t^0,61639** (I en mm/h, T en años, t en min).

Unidades: precipitaciones en mm; intensidades en mm/h; duraciones en h (Tabla Pd/I) y min (regresión). Distribución elegida en la hoja de Kolmogorov-Smirnov: Gumbel (Δmax 0,028 < Δ0 0,159; Log-Normal 0,032; Pearson III 0,060).

## Verificación
Recomputo independiente en Python desde la serie de máximos: media, desviación, α, u, XT (Tr 2–25), d, n, K, m y la tabla final coinciden con las celdas en caché con diferencia relativa máxima **1,2·10⁻¹³**.

## Hallazgos (a resolver con el usuario)
1. **Identidad de la estación:** la hoja de datos dice «… 24 Hrs. (mm) - **CUMBE**», pero el archivo se llama «M0037». El M0037 del libro INAMHI es *Milagro-Ingenio Valdez*. No se puede afirmar que estos datos sean de Milagro.
2. **No es la IDF del libro INAMHI:** es un método de pluviómetro diario + coeficientes de Campos, no la ecuación `i = K·Idtr·t⁻ⁿ` de pluviógrafos del libro. Frente al cuadro del libro (M0037): Excel/libro = **1,45–1,57 a 5 min**, 0,96–1,07 a 15–20 min, **0,63–0,69 a 60 min**, 0,72–0,79 a 120 min. Curvas incompatibles: no intercambiarlas ni promediarlas.
3. **No hay lluvia subdiaria medida:** las duraciones de 5–60 min salen de extrapolar la regresión (los datos van de 1 a 24 h por coeficientes tabulados).
4. Factor 1,13 de intervalo fijo en todo XT: corrección estadística, **no** factor climático.
5. K y m se ajustan solo con Tr 2–25 años: usar la ecuación para Tr 50/100 es extrapolación (la hoja calcula XT de 50 a 500 años pero no las ajusta).
6. Rótulos de año desordenados en «Precip. Máx. Probable» (C34–C36 apuntan a otras filas que D34–D36); los valores no cambian.
7. Gráficos e imágenes de las hojas no se auditaron visualmente.

## Uso permitido en UCEclima
Solo como **fuente IDF separada y rotulada** («Excel Caiza 2026, hoja CUMBE») dentro de `DisenoIDF`; la IDF por defecto del proyecto sigue siendo la del libro INAMHI. Ninguna se mezcla con un evento observado.
