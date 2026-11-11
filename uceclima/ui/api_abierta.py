# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""API abierta de UCEclima para agentes de IA y scripts: clave de acceso local, especificación OpenAPI y guía para modelos de lenguaje.
La API es la misma que usa la interfaz (nada duplicado). Solo escucha en 127.0.0.1. Las lecturas (GET) no piden clave; las acciones (POST) piden
la clave en `Authorization: Bearer <clave>`. La clave vive en %USERPROFILE%\\.uceclima\\api_key.txt; quien tenga ese archivo ya tiene acceso a la cuenta de Windows."""
import hmac, os, secrets
from pathlib import Path

ARCHIVO_CLAVE = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".uceclima" / "api_key.txt"


def cargar_clave():
    try:
        if ARCHIVO_CLAVE.exists():
            k = ARCHIVO_CLAVE.read_text(encoding="utf-8").strip()
            if len(k) >= 24:
                return k
        ARCHIVO_CLAVE.parent.mkdir(parents=True, exist_ok=True)
        k = "cu_" + secrets.token_urlsafe(30)
        ARCHIVO_CLAVE.write_text(k, encoding="utf-8")
        return k
    except OSError:
        return "cu_" + secrets.token_urlsafe(30)           # sin disco: clave solo de esta sesión


def clave_valida(esperada, cabecera):
    if not cabecera or not cabecera.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(cabecera[7:].strip().encode(), esperada.encode())


def _op(resumen, metodo="get", cuerpo=None, params=None, nota=""):
    d = {"summary": resumen, "description": nota or resumen, "responses": {"200": {"description": "OK (JSON)"}, "400": {"description": "Entrada inválida o regla científica no cumplida"}}}
    if params:
        d["parameters"] = [{"name": n, "in": "query", "required": False, "schema": {"type": "string"}, "description": t} for n, t in params]
    if cuerpo:
        d["requestBody"] = {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {k: {"type": "string", "description": v} for k, v in cuerpo.items()}}}}}
    if metodo == "post":
        d["security"] = [{"bearer": []}]
    return {metodo: d}


def openapi(version):
    rutas = {
        "/api/estado": _op("Estado general: proyecto abierto, corridas recientes, módulos y su estado (implementado/parcial/bloqueado/pendiente)."),
        "/api/proyectos_demo": _op("Lista los proyectos de demostración."),
        "/api/proyecto/demo": _op("Abre una demostración", "post", {"id": "sintetico | milagro"}),
        "/api/proyecto/abrir": _op("Abre un proyecto (carpeta o proyecto_uceclima.json)", "post", {"ruta": "ruta absoluta"}),
        "/api/proyecto/guardar_como": _op("Guarda una copia del proyecto en una carpeta nueva (nunca sobrescribe)", "post", {"carpeta": "carpeta nueva", "nombre": "nombre"}),
        "/api/verificar": _op("Verifica entradas del proyecto abierto (hashes, CRS, cobertura, datum) y estima recursos", "post"),
        "/api/corrida/iniciar": _op("Ejecuta UNA corrida pequeña (una por vez; tope de celdas). Con «escenario» usa una IDF de diseño alternativa (todas históricas). Devuelve el id de la corrida.", "post", {"escenario": "opcional: directa | observado | escalada | chirps", "estacion": "estación de referencia de la IDF (M0138)"}),
        "/api/escenarios/idf": _op("Escenarios de lluvia de diseño del proyecto con sus magnitudes (24 h y duración de la tormenta) y su procedencia", params=[("estacion", "estación INAMHI de referencia")]),
        "/api/visor/capa": _op("Una sola capa de una corrida (para superponer «fantasmas» de otros escenarios)", params=[("id", "id de corrida"), ("capa", "hmax|vmax|duracion")]),
        "/api/corrida/hietograma": _op("Hietograma de diseño usado por una corrida (para comparar escenarios)", params=[("id", "id de corrida")]),
        "/api/corrida/estado": _op("Estado y progreso de una corrida", params=[("id", "id de corrida; vacío = la última")]),
        "/api/corrida/resultado": _op("Resumen, evaluación numérica (balance, Courant, pasos) y marcas de calibración", params=[("id", "id de corrida")]),
        "/api/corrida/cancelar": _op("Cancela la corrida en curso", "post"),
        "/api/visor/datos": _op("Terreno y capas reales de una corrida (hmax, vmax, duración) como mallas JSON", params=[("id", "id de corrida; vacío = la última completada")]),
        "/api/campo/estado": _op("Validación de campo: encuestas generadas, marcas importadas y último contraste con el modelo (no corre el modelo)"),
        "/api/estaciones": _op("Lista las estaciones pluviométricas del proyecto con su control de calidad"),
        "/api/estaciones/serie": _op("Serie de una estación", params=[("id", "id de estación"), ("inicio", "ISO UTC"), ("fin", "ISO UTC")]),
        "/api/estaciones/vista_previa": _op("Lee un CSV de lluvia y propone columnas (no escribe nada)", "post", {"archivo": "ruta absoluta del CSV"}),
        "/api/estaciones/importar": _op("Importa una estación (no sobrescribe; id nuevo)", "post",
                                       {"archivo": "ruta CSV", "id": "id", "nombre": "nombre", "tipo": "pluviometro|pluviografo|automatica|otra", "col_fecha": "columna fecha", "col_lluvia": "columna lluvia",
                                        "x": "este en CRS del proyecto", "y": "norte", "lon": "o longitud WGS84", "lat": "o latitud WGS84", "zona_horaria": "p. ej. America/Guayaquil", "dayfirst": "true/false"}),
        "/api/estaciones/hietograma": _op("Exporta el hietograma de un evento a un CSV nuevo (solo datos; no conduce el modelo)", "post", {"id": "estación", "inicio": "ISO", "fin": "ISO"}),
        "/api/terreno/inspeccionar": _op("Inspecciona un GeoTIFF de dron/WebODM: CRS, resolución, NoData, rango, avisos (no modifica nada)", "post", {"archivo": "ruta absoluta del .tif"}),
        "/api/terreno/registrar": _op("Registra el MDT/DSM como terreno del proyecto abierto (por referencia; respalda config y proyecto)", "post",
                                      {"archivo": "ruta del .tif", "tipo_terreno": "MDT|DSM|desconocido", "datum": "texto, p. ej. «no verificado»", "res": "resolución del modelo en m", "aoi": "[x0,x1,y0,y1] opcional"}),
        "/api/proyecto/evento": _op("Declara un EVENTO OBSERVADO de una estación como forzamiento de la corrida (en vez de la tormenta IDF). Valida sin ausentes ni huecos; lluvia diaria exige desagregacion='uniforme'. Sigue siendo un modelo no calibrado.", "post",
                                    {"estacion": "id de estación importada", "inicio": "ISO UTC", "fin": "ISO UTC", "desagregacion": "'uniforme' solo si la lluvia es diaria", "sim_horas": "opcional; por defecto duración del evento + 1 h (tope 12 h)"}),
        "/api/pronostico/lista": _op("7b · Consultas de pronóstico del proyecto, modelos disponibles (gfs, ecmwf, imerg), sitio y avisos"),
        "/api/pronostico/serie": _op("7b · Serie horaria (UTC) de una consulta de pronóstico guardada", params=[("id", "id de la consulta, p. ej. gfs_20261105_153000")]),
        "/api/pronostico/consultar": _op("7b · Pide la lluvia de UN modelo: gfs (NOAA), ecmwf (Europa) o imerg (NASA, lluvia ya caída, Earth Engine). Guarda datos/pronostico/<modelo>_<sello>/ (CSV horario UTC + procedencia). Es un pronóstico a ~25 km, no una observación ni una alerta oficial.", "post",
                                          {"modelo": "gfs|ecmwf|imerg", "dias": "1 a 10 (imerg: 1 a 7)", "lon": "opcional (por defecto el sitio del proyecto)", "lat": "opcional", "muestreo": "area (promedio del área 2D) | punto", "zona": "hora de la tabla diaria (por defecto según el sitio)"}),
        "/api/pronostico/comparar": _op("7b · Consulta varios modelos y devuelve la tabla diaria lado a lado y los hietogramas", "post", {"modelos": "lista de gfs|ecmwf|imerg", "dias": "1 a 10", "lon": "opcional", "lat": "opcional", "muestreo": "area|punto", "zona": "opcional"}),
        "/api/pronostico/usar": _op("7b · Declara una consulta de pronóstico como forzamiento de la corrida 2D (estación «PRON_…» + evento con la marca forzamiento_externo). La corrida y sus mapas saldrán rotulados PRONÓSTICO, nunca «evento observado». Si el pronóstico trae menos de 1 mm no hay nada que modelar.", "post",
                                    {"id": "id de la consulta", "horas": "6 a 95 (por defecto 72)", "permitir_poca_lluvia": "true/false"}),
        "/api/pronostico/geoglows": _op("7b · Caudal pronosticado de un tramo GEOGLOWS v2 (mediana y banda alta cada 3 h) como CSV t_s;Q_m3s para hidrograma de entrada. Modelo global: orden de magnitud, no ubica el cauce.", "post", {"river_id": "número del tramo", "horas": "por defecto 96"}),
        "/api/peligro/generar": _op("Mapas de calado, velocidad y PELIGRO (calado × velocidad, clases ARR 2019) de una corrida: GeoTIFF, shapefile por clases (UTM y WGS84, GeoPackage) y PNG de cada variable, lámina de 3 paneles con OSM y resumen de km² y edificios. Carpeta nueva en productos/13_peligro. El mar se excluye. Sin calibrar ni validar.", "post",
                                    {"id": "id de corrida, «todas» o vacío = la última", "zoom": "opcional [lon_min, lat_min, lon_max, lat_max]"}),
        "/api/proyecto/evento_quitar": _op("Vuelve a la tormenta de diseño IDF (copia .bak de la configuración)", "post"),
        "/api/prep/escanear": _op("PREMÓDULO: escanea una carpeta de datos crudos y clasifica cada archivo (lluvia ancha INAMHI, lluvia larga, inventario de eventos SGR, ráster…)", "post", {"carpeta": "ruta absoluta"}),
        "/api/prep/precipitacion": _op("PREMÓDULO: lee un archivo de lluvia (identifica columnas por contenido, no por encabezado) y devuelve problemas, catálogo y calidad por estación (completitud, años sin datos, huecos). No escribe nada.", "post", {"archivo": "ruta", "hoja": "opcional"}),
        "/api/prep/inventario": _op("PREMÓDULO: lee un inventario de eventos (SGR/SNGR) y devuelve su resumen y problemas (fechas nulas, coordenadas repetidas, duplicados). No escribe nada.", "post", {"archivo": "ruta", "hoja": "opcional"}),
        "/api/prep/contrastar": _op("PREMÓDULO: contrasta la lluvia diaria de UNA estación con los eventos del inventario (percentil y retorno empírico por evento; tasa de eventos por clase de lluvia). Descriptivo, sin causalidad.", "post",
                                    {"precip_archivo": "archivo de lluvia o precipitacion_diaria.csv ya ordenado", "estacion": "id", "inventario_archivo": "ruta", "lat": "latitud de la estación (opcional)", "lon": "longitud (opcional)",
                                     "radio_km": "radio alrededor de la estación (por defecto 30)", "cantones": "lista de cantones (opcional)", "ventana_dias": "acumulado previo (3)", "solo_hidromet": "true/false"}),
        "/api/prep/ordenar": _op("PREMÓDULO: ordena y fusiona los archivos de lluvia en una CARPETA NUEVA (precipitacion_diaria.csv, estaciones.csv, informe_calidad.json, manifest con SHA-256, LEEME). Nunca modifica los crudos; conflictos entre fuentes quedan vacíos.", "post",
                                 {"archivos": "lista de rutas de lluvia", "inventario": "ruta opcional", "salida": "carpeta (por defecto datos_preparados del proyecto)"}),
        "/api/prep/registrar_estacion": _op("PREMÓDULO: lleva una estación ordenada (lluvia diaria) al proyecto abierto", "post", {"preparados": "carpeta preparados_AAAAMMDD_HHMMSS", "estacion": "id"}),
        "/api/sitio/nuevo": _op("Crea un proyecto NUEVO desde un sitio y lanza automáticamente las descargas: MDT Copernicus 30 m, CN y Manning estimados (WorldCover × suelo OpenLandMap, siempre desde Earth Engine salvo que el proyecto traiga los suyos), CHIRPS, GEOGLOWS y opcional CELEC. Requiere cuenta de Earth Engine autorizada. CMIP6 no se descarga.", "post",
                                {"nombre": "nombre del proyecto", "lon": "longitud WGS84", "lat": "latitud", "inicio": "AAAA-MM-DD (CHIRPS)", "fin": "AAAA-MM-DD", "medio_km": "mitad del lado del MDT (km, por defecto 20)", "celec": "true para traer cota y caudal de Mazar"}),
        "/api/descargas": _op("Estado de las descargas del proyecto (progreso, manifiestos, archivos)"),
        "/api/descargas/iniciar": _op("Lanza UNA descarga: sitio | mdt | chirps | geoglows | celec (una a la vez; carpeta nueva)", "post", {"fuente": "sitio|mdt|cn_manning|chirps|geoglows|celec", "parametros": "objeto: lon, lat, inicio, fin, medio_km…"}),
        "/api/gee/autorizar": _op("Abre el navegador para que la persona autorice Earth Engine con su cuenta", "post"),
        "/api/gee/proyecto": _op("Guarda el ID de proyecto de Google Cloud para Earth Engine (no es un secreto)", "post", {"proyecto": "id de proyecto"}),
        "/api/actividad": _op("Bitácora en vivo (lo que hacen la IA, la interfaz, las descargas y las corridas); la pantalla la muestra", params=[("desde", "número del último evento ya visto")]),
        "/api/actividad/narrar": _op("La IA deja un mensaje en la pantalla del usuario (qué está haciendo y por qué). Úsalo para narrar tu avance.", "post", {"mensaje": "texto corto", "detalle": "opcional", "modulo": "preparacion|series|lluvia|terreno|gee|corrida…", "nivel": "info|ok|aviso|error"}),
        "/api/series/catalogo": _op("Series disponibles en el proyecto (CHIRPS, estaciones, CELEC, GEOGLOWS)"),
        "/api/series/lluvia": _op("Totales anuales, máximos, climatología mensual y tendencia (Mann-Kendall + Sen) de una serie de lluvia", params=[("id", "id de serie, p. ej. chirps:media_caja_mm")]),
        "/api/series/caudal": _op("Hidrograma diario, curva de duración y eventos de una serie de caudal", params=[("id", "id de serie, p. ej. celec:caudal_m3s")]),
        "/api/series/evento": _op("Hidrograma + hietograma de un evento seleccionado", params=[("id", "evento, p. ej. P015")]),
        "/api/cmip6/compuerta": _op("Estado de la compuerta de CMIP6 y de la decisión del usuario de asumir la línea base"),
        "/api/cmip6/asumir_baseline": _op("Registra la DECISIÓN DEL USUARIO de asumir la línea base como correcta para habilitar CMIP6 (no la valida). Requiere confirmo=true y solo debe llamarse si el usuario lo decidió.", "post", {"confirmo": "true", "texto": "opcional"}),
        "/api/cmip6/evaluar": _op("Evalúa los modelos CMIP6 históricos descargados contra la referencia observada: sesgo, RMSE de climatología/cuantiles/máximos anuales, QQM con validación cruzada, mejor modelo y ensamble", "post", {"referencia": "est:M0138 | chirps:media_caja_mm", "k": "tamaño del ensamble (5)"}),
        "/api/cmip6/factores": _op("Factores de cambio (QDM) de los modelos seleccionados con el futuro descargado: Tr10/Tr100 de 24 h, total anual, p99; mediana ponderada y rango p10–p90", "post"),
        "/api/hidrologia/casos": _op("Panel Hidrología y calibración: corridas del proyecto y estado de las observaciones"),
        "/api/hidrologia/serie": _op("Series del panel (hietograma, hidrogramas, volúmenes, balance, tránsito, métricas en períodos coincidentes)", params=[("id", "id de corrida del proyecto")]),
        "/api/hidrologia/exportar": _op("Exporta tablas y gráficas del panel a una carpeta nueva", "post", {"fuente": "corrida", "id": "id de corrida"}),
        "/api/cmip6/resultados": _op("Último análisis CMIP6 del proyecto: ranking, gráficas y factores"),
        "/api/cmip6/idf": _op("IDF oficial de X y su ajuste por la tasa de cambio de cada Tr para un escenario Y (curvas Tr × duración)", params=[("id", "cc_ssp585_<horizonte>_<mediana|p10|p90|mejor|cuantiles>")]),
        "/api/bd/esquema": _op("Tablas de la base de datos SQLite del proyecto (series CMIP6 originales y corregidas, métricas, factores, eventos, corridas…)"),
        "/api/bd/sincronizar": _op("Reconstruye la base de datos del proyecto desde sus archivos (idempotente)", "post", {"referencia": "serie de lluvia de referencia (chirps:celda_nex_mm)"}),
        "/api/bd/consulta": _op("Consulta SQL de SOLO LECTURA (una sentencia SELECT/WITH, tope de filas) sobre la base de datos del proyecto", "post", {"sql": "SELECT …", "max_filas": "5000"}),
        "/api/cmip6/anual": _op("Totales y máximos anuales CMIP6 (original vs corregido, rango entre modelos) y la referencia observada, desde la base de datos"),
        "/api/ia/config": _op("Entradas MCP para Claude Desktop, Claude Code (.mcp.json) y VS Code (.vscode/mcp.json) y si ya están instaladas"),
        "/api/ia/instalar": _op("Instala (fusiona, con copia .bak) el servidor MCP de UCEclima en la configuración de una IA; solo por decisión del usuario", "post", {"destino": "claude_desktop | claude_code | vscode", "carpeta": "carpeta del proyecto de VS Code (opcional)"}),
        "/api/lluvia/auditoria": _op("Auditoría del Excel de IDF (M0037)"),
        "/api/lluvia/seleccion": _op("Selección estadística de eventos con límites"),
        "/api/chirps/plan": _op("Plan de ventanas CHIRPS", "post", {"inicio": "AAAA-MM-DD", "fin": "AAAA-MM-DD"}),
        "/api/chirps/cobertura": _op("Cobertura real en Earth Engine (usa las credenciales del sistema; nunca se guardan)", "post", {"inicio": "AAAA-MM-DD", "fin": "AAAA-MM-DD"}),
        "/api/cmip6/compuerta": _op("Estado de la compuerta de línea base: el cambio climático está BLOQUEADO hasta calibrar y validar"),
    }
    return {"openapi": "3.0.3",
            "info": {"title": "UCEclima API local", "version": version,
                     "description": "API local (127.0.0.1) de UCEclima para agentes de IA. Reglas del proyecto que la API hace cumplir: solo condiciones históricas/IDF; CMIP6 bloqueado hasta calibrar y validar la línea base; "
                                    "una corrida por vez y con tope de tamaño; nada se sobrescribe; los resultados no están calibrados ni validados."},
            "servers": [{"url": "http://127.0.0.1:8765"}],
            "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer", "description": "Clave de %USERPROFILE%\\.uceclima\\api_key.txt (pestaña «API / IA» de la interfaz)"}}},
            "paths": rutas}


GUIA_IA = """# UCEclima: guía para agentes de IA

**Vocabulario:** *hidro* = módulo de hidrología (cuencas, SCS-CN + hidrograma unitario, Muskingum, panel Hidrología y calibración); *land* = módulo hidráulico 2D (terreno, Manning, fronteras, malla, corrida). Son nombres propios de UCEclima: no son HEC-HMS ni HEC-RAS ni equivalen a ellos. Una serie de un modelo externo es «referencia externa», nunca una observación.


UCEclima es un programa local (hidrología/hidráulica, núcleo CLIMANET). Esta API permite que un agente lo maneje paso a paso.
Base: http://127.0.0.1:{puerto}   Especificación: /api/openapi.json   Interactiva: /api/docs
Lecturas (GET): sin clave. Acciones (POST): cabecera  Authorization: Bearer <clave>  (la clave está en {archivo_clave}).

## Premódulo de preparación de datos (úsalo ANTES de modelar)
El usuario carga datos crudos y tú, con estos endpoints, lo ayudas a ordenarlos. Tú decides los casos ambiguos (hoja, estación, filtros); el programa hace el trabajo seguro y reproducible.
1. POST /api/prep/escanear {{"carpeta": "..."}}   -> clasifica cada archivo.
2. POST /api/prep/precipitacion {{"archivo": "..."}} y /api/prep/inventario  -> problemas y calidad (no escriben nada). Explica al usuario QUÉ está mal y por qué.
3. POST /api/prep/contrastar -> lluvia vs eventos del inventario: percentil y retorno empírico por evento. Es descriptivo; el inventario tiene subregistro; no afirmes causalidad.
4. POST /api/prep/ordenar {{"archivos": [...], "inventario": "..."}} -> carpeta NUEVA con todo ordenado. Los crudos no se tocan; los conflictos quedan vacíos (no los resuelvas inventando valores).
5. POST /api/prep/registrar_estacion -> lleva la estación al proyecto; luego /api/proyecto/evento para usar un evento observado.
No rellenes huecos, no conviertas ausentes en 0, no mezcles estaciones distintas, y cita siempre los años/periodos sin datos.

## Muestra tu avance al usuario
El usuario mira la pantalla de UCEclima mientras trabajas. Cada acción POST aparece sola en el panel «Actividad en vivo»; además narra con POST /api/actividad/narrar {{"mensaje": "...", "modulo": "series"}} y la pantalla puede seguirte (opción «Seguir al agente»).

## Flujo recomendado
1. GET  /api/estado                              -> qué hay abierto, estado de cada módulo.
2. POST /api/proyecto/abrir {{"ruta": "..."}}       (o /api/proyecto/demo {{"id":"milagro"}})
3. POST /api/terreno/inspeccionar {{"archivo": "...tif"}}  y luego /api/terreno/registrar  (MDT de dron)
4. POST /api/estaciones/vista_previa -> /api/estaciones/importar   (CSV de estación pluviométrica)
5. POST /api/verificar                           -> revisa hashes, CRS, cobertura, datum, recursos.
6. POST /api/corrida/iniciar                     -> UNA corrida pequeña; consulta GET /api/corrida/estado hasta 'completado'.
7. GET  /api/corrida/resultado, /api/visor/datos -> métricas y capas reales.

## Reglas que debes respetar (la API las hace cumplir y tú no debes saltarlas)
- Solo condiciones históricas/IDF. El cambio climático (CMIP6) está bloqueado hasta calibrar y validar la línea base; no lo simules.
- Nunca inventes parámetros, cotas ni datos. Si falta un dato, dilo y pregunta.
- Una corrida por vez, casos pequeños; no lances la cuenca completa ni corridas nocturnas.
- Nada se sobrescribe: usa ids/carpetas nuevos.
- Los resultados NO están calibrados ni validados: no los presentes como predicción ni como huella de inundación observada.
- Capacidad de canales, pérdidas de carga y secciones aparecen como «no evaluada»: no las afirmes.
- Un evento observado (POST /api/proyecto/evento) conduce el modelo con lluvia real de una estación, pero el modelo sigue SIN calibrar: no lo presentes como validación ni como huella observada.
- No guardes ni muestres credenciales (Earth Engine, tokens).
"""


def docs_html(version):
    return """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>UCEclima API</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;font:15px/1.5 "Calibri Light",Calibri,Arial,sans-serif;background:linear-gradient(160deg,#0b121c,#12202f 50%,#1a3148);color:#e6edf5;min-height:100vh}
main{max-width:980px;margin:0 auto;padding:28px 18px}h1{font-weight:300;font-size:28px}code,pre{font-family:Consolas,monospace;font-size:13px}
.op{border:1px solid #26384f;border-radius:12px;background:rgba(14,24,37,.7);padding:12px 16px;margin:10px 0}.m{display:inline-block;min-width:54px;text-align:center;border-radius:6px;padding:1px 8px;font-weight:700;margin-right:8px}
.get{background:#1d6b4d}.post{background:#8a5a00}pre{background:#070d15;border:1px solid #26384f;padding:12px;border-radius:10px;overflow:auto}a{color:#7fd6ee}.dim{color:#93a4b8}</style></head>
<body><main><h1>UCEclima · API local</h1><p class="dim">Versión """ + version + """ · solo 127.0.0.1 · <a href="/api/openapi.json">openapi.json</a> · <a href="/api/ia">guía para agentes de IA</a></p><div id="ops">cargando…</div>
<script>fetch("/api/openapi.json").then(r=>r.json()).then(o=>{document.getElementById("ops").innerHTML=Object.entries(o.paths).map(([p,v])=>Object.entries(v).map(([m,d])=>
`<div class="op"><span class="m ${m}">${m.toUpperCase()}</span><code>${p}</code><br><span class="dim">${d.summary}</span>${d.requestBody?"<pre>"+JSON.stringify(Object.fromEntries(Object.entries(d.requestBody.content["application/json"].schema.properties).map(([k,s])=>[k,s.description])),null,1)+"</pre>":""}</div>`).join("")).join("")})</script></main></body></html>"""
