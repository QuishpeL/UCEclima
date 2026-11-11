# UCEclima — módulo de inicio y lluvia

Desarrollo separado de CLIMANET mientras Claude completa sus corridas. No está conectado al lanzador ni descarga datos todavía.

Flujo de usuario:
1. Elegir proyecto y vincular cuenta Google Earth Engine con proyecto Cloud habilitado. La cuenta sola no acredita acceso; verificar autenticación, registro y permisos. No guardar contraseñas/tokens en proyecto ni GitHub. Permitir trabajo offline con datos ya descargados.
2. Elegir evento observado o diseño IDF. En observado, identificar estación, fecha/hora, zona horaria y procedencia del registro. Importar lluvia por intervalos del pluviógrafo; si es imagen de banda o gráfica, digitalización asistida y confirmación humana de escalas, reloj, acumulado/incremental, reinicios y calidad.
3. Analizar con Excel IDF M0037 (atribución Caiza 2026 del usuario), comparando duraciones y acumulados. No transformar por defecto el evento observado en bloques IDF: conservar ambas series por separado.
4. Consultar CHIRPS v3 disponible y, si no cubre la ventana, v2. Probar cobertura día por día para evento y ±21 días, derivar ±5 días. No mezclar versiones dentro de corrida; registrar fallback, ID exacto y fecha de consulta. La variante v3 DAILY_SAT es explícita, no sinónimo de cualquier CHIRPS v3.
5. Mostrar vista de control: hietograma observado, acumulados diarios CHIRPS y comparación por cuenca; fechas diarias UTC no equivalen exactamente al día de observación local. No ajustar automáticamente la lluvia observada para igualarla con CHIRPS.
6. Usar antecedentes para estimación documentada de humedad/pérdidas; posteriores para recesión/evaluación, nunca para inicializar mediante información futura. El flujo base requiere datos/metodología propios.

Si no hay evento observado: generar diseño IDF sin fingir fecha histórica. Se puede elegir fecha de contexto CHIRPS, etiquetando experimento híbrido explícito. Para modelar con lluvia diaria sin pluviografía, paso compatible o desagregación conservativa declarada e incertidumbre.

eventos.py implementa contrato temporal, ventanas UTC, validación de continuidad/volumen del hietograma y selección de versión con cobertura completa. El adaptador GEE y digitalizador de pluviógrafos están pendientes. No se contactó a Claude ni se reiniciaron cálculos.

## Avance 13-oct-2026
Etapas 1 y 2 implementadas con casos pequeños (ver `ESTADO_ETAPA_1_2.md`, `AUDITORIA_EXCEL_M0037.md`). Módulo CMIP6 sigue solo especificado y bloqueado. No se descargó nada masivo.

## Interfaz gráfica (13-oct-2026)
Doble clic en `UCEclima.cmd`. Ver `ESTADO_INTERFAZ.md` (implementado/pendiente, pruebas, capturas), `INSTALACION.md` y `DECISIONES_INTERFAZ.md`. Código en `ui/` (servidor, proyecto, worker, mapas, trabajos, demo, estáticos); el cálculo sigue en CLIMANET.
