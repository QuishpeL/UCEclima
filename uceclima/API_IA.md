# UCEclima · API abierta para IA

Base `http://127.0.0.1:8765` (solo el propio equipo). Especificación `/api/openapi.json`, página `/api/docs`, guía para pegar en un agente `/api/ia`.
Lecturas (GET): sin clave. Acciones (POST): `Authorization: Bearer <clave>`; la clave se genera sola en `%USERPROFILE%\.uceclima\api_key.txt` y se ve en la pestaña «API / IA».

Flujo: `GET /api/estado` → `POST /api/proyecto/abrir` → `POST /api/terreno/inspeccionar|registrar` (MDT de dron) → `POST /api/estaciones/vista_previa|importar` →
`POST /api/proyecto/evento` (opcional: lluvia observada de una estación) → `POST /api/verificar` → `POST /api/corrida/iniciar` → `GET /api/corrida/estado|resultado` → `GET /api/visor/datos`.

Reglas que se hacen cumplir: solo condiciones históricas/IDF (CMIP6 bloqueado hasta calibrar y validar); una corrida por vez y con tope de celdas; nada se sobrescribe (ids/carpetas nuevos, copias .bak);
resultados no calibrados ni validados; capacidad de canales/pérdidas «no evaluada»; un evento de estación (POST /api/proyecto/evento) puede conducir el modelo, que sigue sin calibrar (no es una validación). Credenciales de Earth Engine: nunca se leen ni se guardan.

Premódulo de preparación de datos (antes de modelar): `POST /api/prep/escanear | precipitacion | inventario | contrastar | ordenar | registrar_estacion`. Los crudos no se tocan; los conflictos quedan vacíos; el contraste con el inventario SGR es descriptivo (subregistro, sin causalidad).

MCP: `python -m uceclima.mcp_servidor` (o `UCEclima.exe --mcp`) — registrado en `.mcp.json` (Claude Code) y `.vscode/mcp.json` (VS Code); Claude Desktop: pestaña «API / IA» → Instalar. Ver `AGENTS.md`.
CMIP6 (solo si el usuario asumió la línea base): `POST /api/cmip6/evaluar | factores`, `GET /api/cmip6/resultados | anual`, descargas `cmip6_historico | cmip6_futuro`; escenarios Y `cc_<ssp>_<horizonte>_<mediana|p10|p90|mejor>` en `POST /api/corrida/iniciar`. Base de datos: `/api/bd/esquema | sincronizar | consulta`.
