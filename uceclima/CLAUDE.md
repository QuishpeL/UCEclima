# UCEclima · guía para agentes de IA (Codex, Claude Code, GitHub Copilot en VS Code)

UCEclima (hidrología e hidráulica para Ecuador, núcleo CLIMANET; grupo GICARH · Universidad Central del Ecuador) está **abierto para que un agente lo maneje desde VS Code**. La interfaz gráfica no muestra esto (es interno): se usa con el servidor MCP o con la API local.

## Cómo conectarse
1. **MCP (recomendado)**: servidor `python -m uceclima.mcp_servidor` (o `UCEclima.exe --mcp`). Ya está declarado en `.vscode/mcp.json` (VS Code · Copilot/Codex) y `.mcp.json` (Claude Code). Ajusta las rutas si moviste la carpeta.
2. **API HTTP** local: `http://127.0.0.1:8765` · especificación `/api/openapi.json` · guía `/api/ia` · los POST llevan `Authorization: Bearer <clave de ~/.uceclima/api_key.txt>`.
3. Si UCEclima no responde, la herramienta `lanzar_uceclima` lo arranca.

## Orden de trabajo (igual que los módulos de la pantalla)
0. **Preparación de datos**: `prep_leer` (Excel/CSV de precipitación y caudal → memoria; el usuario los ve graficados), `prep_memoria`.
1. **Proyecto**: `proyecto_crear` (carpeta nueva con las series de la memoria) o `abrir_proyecto`.
2. **Datos / GEE**: el usuario pone SU proyecto de Google Cloud, autoriza en el navegador e inicializa/verifica la conexión (`gee_estado` para ver en qué paso está). **Tú no autorizas por él ni ves su token.**
3. **CHIRPS**: `descargar` (fuente `chirps`) → serie, gráficos y tendencias quedan dentro del proyecto (`chirps_graficos`).
4. Terreno → hidro (cuencas) → land (corrida 2D, una por vez) → evaluación → hidro (hidrología y calibración) → CMIP6 → `bd_consulta`.
- Cuenta lo que haces con `narrar` (panel «Actividad en vivo»); el usuario puede activar «Seguir al agente».

## Vocabulario propio
- **hidro** = módulo de hidrología (cuencas, SCS-CN + hidrograma unitario, Muskingum, panel «Hidrología y calibración»). **land** = módulo hidráulico 2D (terreno, Manning, fronteras, malla, corrida, evaluación).
- Son nombres de módulos de UCEclima: **no** son HEC-HMS ni HEC-RAS ni equivalen a ellos. Una serie de un modelo externo es «referencia externa», nunca una observación.

## Reglas que no se saltan
- **X = condiciones existentes** (válidas, tonos fríos) frente a **Y = CMIP6 cambio climático** (escenario, siempre magenta degradado).
- Nunca inventes parámetros, cotas ni datos: si falta algo, dilo y pregunta. Datos crudos intactos; los conflictos entre fuentes quedan vacíos (no se promedian).
- Una corrida o descarga por vez, casos pequeños; sin cuenca completa, sin descargas masivas, sin corridas nocturnas. Nada se sobrescribe (carpetas nuevas con marca de tiempo; copias .bak).
- Resultados **no calibrados ni validados**; no son predicción ni huella de inundación observada. Capacidad de canales y pérdidas de carga: «no evaluadas». Sin observaciones de caudal confirmadas: «simulación sin calibrar».
- CMIP6 solo existe si el **usuario** decidió asumir la línea base (`cmip6_asumir_baseline` exige su confirmación explícita; nunca la llames por iniciativa propia). **Solo SSP5-8.5.**
- No leas, guardes ni muestres credenciales de Earth Engine. Referencia observada para corregir CMIP6: **CHIRPS**; lluvia de diseño de X: IDF oficial del INAMHI.
- Punto de partida y caso de referencia: **Mazar** (`proyectos/mazar`). Milagro no tiene caudales observados: no sirve para calibrar.
