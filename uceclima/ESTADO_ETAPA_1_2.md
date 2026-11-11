# UCEclima — estado de las etapas 1 (lluvia y eventos) y 2 (GEE y CHIRPS)

13-oct-2026. Casos pequeños, una ejecución a la vez, sin sobrescribir resultados previos. Núcleo CLIMANET intacto (35 pruebas OK). Pruebas de UCEclima: `python -m uceclima.tests.<nombre>` desde `MILAGRO`.

## Implementado
| Archivo | Función | Pruebas |
|---|---|---|
| `eventos.py` (Codex, sin cambios) | contrato de evento fechado, ventanas UTC, validación de hietograma, elección de producto | `probar_eventos.py` |
| `idf_excel.py` | auditoría de hojas/fórmulas, recomputo independiente (Gumbel→Campos→regresión), tabla IDF del Excel, comparación con el libro INAMHI | `test_idf_excel` (2) |
| `lluvia.py` | `DisenoIDF` (diseño; volumen exacto; rotulado híbrido si hay fecha) y `EventoObservado` (intervalos reales; máx. por duración; Tr implícito sin extrapolar; forzamiento sin remuestrear); `desagregar_uniforme` solo para lluvia diaria, rotulada `desagregada` | `test_lluvia` (4) |
| `gee_chirps.py` | inicio de Earth Engine con credenciales ya autorizadas (nada en el repositorio), disponibilidad día a día, selección v3→v2 sin mezclar, serie diaria por cuenca con caché y manifiesto, ventanas evento/±5/±21 d (anidadas y complementarias), topes contra descargas masivas | `test_gee_chirps` (4) con `ee` simulado |
| `ejemplos/chirps_evento_pequeno.py` | ejemplo vivo: evento 2–4 feb 2011, 28 subcuencas | ejecutado una vez |

## Resultado vivo (GEE real, 13-oct-2026)
Earth Engine inicializó con las credenciales existentes del usuario (sin proyecto explícito; ID de proyecto no guardado). Colección `UCSB-CHC/CHIRPS/V3/DAILY_SAT`: **cobertura completa** de la ventana (45 de 45 días), sin fallback.
Caché: `cache/chirps/v3_daily_sat/df7fcfae5b6ab91e/` (serie CSV + manifiesto con colección, fecha de consulta, cobertura y reductor).
Acumulados (mm, días UTC) de las 6 cuencas que intersecan el DEM fino: evento 2–4 feb ≈ 9–15 mm; 5 d antes 50–60; 21 d antes 148–182; 5 d después 55–72; 21 d después 264–292.

## Límites y errores conocidos
- El Excel **no** es la IDF del libro (hasta ±57 % de diferencia) y su estación está rotulada CUMBE: pendiente confirmación del usuario. No se usa por defecto.
- No hay aún un pluviógrafo real importado: `EventoObservado` espera CSV de intervalos; la digitalización asistida de bandas/gráficas **no está implementada**.
- CHIRPS: producto diario en UTC derivado de pentadas; no sustituye lluvia subdiaria; no se ajusta la lluvia observada a CHIRPS. Los acumulados son medias ponderadas por fracción de píxel a 0,05° (cuencas pequeñas pueden caer dentro de uno o dos píxeles).
- La inicialización de GEE usó credenciales ya presentes; no se verificó a qué proyecto Cloud están asociadas. Pruebas de red solo simuladas; la única prueba viva fue el ejemplo.
- Rásteres CHIRPS por día (GeoTIFF) y entrada de datos locales **no implementados** (hoy solo series por cuenca y caché propia); la humedad antecedente no se calcula todavía.
- Esperando decisión: ¿qué estación y evento observado se usarán primero? (datos de pluviógrafo con fechas e intervalos).

## Siguiente (módulo 3, terreno y geometría) — no iniciado
