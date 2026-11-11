# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Servidor MCP (Model Context Protocol, stdio) de UCEclima: permite manejar el programa desde una IA de escritorio (Claude Desktop), Claude Code / VS Code o cualquier cliente MCP.
Es un puente delgado: cada herramienta llama a la API local de UCEclima (127.0.0.1) con la clave de ~/.uceclima/api_key.txt. No guarda credenciales, no abre puertos y aplica las mismas reglas que la API
(CMIP6 bajo decisión del usuario, una corrida por vez, nada se sobrescribe). Sin dependencias externas: JSON-RPC 2.0 por stdin/stdout.
Uso:  python -m uceclima.mcp_servidor     (o  UCEclima.exe --mcp)     Variables: UCEclima_URL (por defecto http://127.0.0.1:8765), UCECLIMA_PUERTO."""
import json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

VERSION = "3.2.0"
PROTOCOLO = "2024-11-05"
ARCHIVO_CLAVE = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".uceclima" / "api_key.txt"
ARCHIVO_PUERTO = ARCHIVO_CLAVE.with_name("puerto.txt")                      # UCEclima anota aquí el puerto en que arrancó
PROYECTO = os.environ.get("UCECLIMA_PROYECTO")                               # carpeta del proyecto de este agente (la del .mcp.json)
_LISTO = {"proyecto": False}


def _url():
    if os.environ.get("UCEclima_URL"):
        return os.environ["UCEclima_URL"]
    if os.environ.get("UCECLIMA_PUERTO"):
        return f"http://127.0.0.1:{os.environ['UCECLIMA_PUERTO']}"
    try:
        return f"http://127.0.0.1:{int(ARCHIVO_PUERTO.read_text(encoding='utf-8').strip())}"
    except (OSError, ValueError):
        return "http://127.0.0.1:8765"


URL = _url()

INSTRUCCIONES = """Eres el operador de UCEclima (hidrología e hidráulica para Ecuador, núcleo CLIMANET). El usuario mira la pantalla de UCEclima mientras trabajas: usa `narrar` para contar qué haces y por qué.
REGLAS (no las saltes): 1) X = condiciones existentes (válidas) siempre se muestra frente a Y = CMIP6 (escenario, en magenta). 2) Nunca inventes parámetros, cotas ni datos; si falta algo, dilo y pregunta.
3) Una corrida por vez y casos pequeños: no lances la cuenca completa, descargas masivas ni corridas nocturnas. 4) Nada se sobrescribe. 5) Los resultados NO están calibrados ni validados: no los presentes como predicción
ni como huella de inundación observada. 6) De CMIP6 solo se usa SSP5-8.5 (el extremo, decisión del usuario). CMIP6 no tiene compuerta: el mejor modelo es el de RMSE más bajo; todo lo de CMIP6 es proyección bajo SSP5-8.5, no predicción.
7) Capacidad de canales y pérdidas de carga son «no evaluadas». 8) No guardes ni muestres credenciales de Earth Engine. 9) Los datos crudos no se tocan; los conflictos quedan vacíos. Si UCEclima no responde, usa `lanzar_uceclima`."""

# nombre, descripción, método, ruta, esquema de entrada (propiedades), requeridos, tipo de paso (qs = query string, cuerpo = JSON)
HERRAMIENTAS = [
    ("estado", "Estado general: proyecto abierto, corridas recientes y módulos con su estado.", "GET", "/api/estado", {}, [], "qs"),
    ("abrir_proyecto", "Abre un proyecto (carpeta o proyecto_uceclima.json).", "POST", "/api/proyecto/abrir", {"ruta": ("string", "ruta absoluta")}, ["ruta"], "cuerpo"),
    ("narrar", "Deja un mensaje en la pantalla del usuario (panel «Actividad en vivo»). Úsalo para contar qué haces.", "POST", "/api/actividad/narrar",
     {"mensaje": ("string", "texto corto"), "modulo": ("string", "preparacion|series|lluvia|terreno|gee|corrida|evaluacion|visor|cmip6"), "nivel": ("string", "info|ok|aviso|error")}, ["mensaje"], "cuerpo"),
    ("prep_leer", "Premódulo: lee Excel/CSV de precipitación y caudal (archivos o una carpeta), los deja en MEMORIA y los grafica en la pantalla del usuario. Si una columna es ambigua devuelve estado «confirmar» (no adivines: pregunta al usuario).", "POST", "/api/prep/leer", {"archivos": ("array", "rutas de archivos Excel/CSV"), "carpeta": ("string", "o una carpeta")}, [], "cuerpo"),
    ("prep_memoria", "Premódulo: series que hay en memoria (tipo, unidad, periodo, calidad, origen).", "GET", "/api/prep/memoria", {}, [], "qs"),
    ("proyecto_crear", "Módulo 1: crea la carpeta de un proyecto nuevo en el punto lon/lat de Ecuador y guarda dentro las series de la memoria del premódulo. No descarga nada.", "POST", "/api/proyecto/crear", {"nombre": ("string", "nombre del proyecto"), "lon": ("number", "longitud"), "lat": ("number", "latitud"), "carpeta_base": ("string", "opcional"), "incluir_memoria": ("boolean", "por defecto true")}, ["nombre", "lon", "lat"], "cuerpo"),
    ("gee_estado", "Módulo 2: estado de la conexión con Earth Engine por pasos (proyecto de Google Cloud, autorización, verificación). La autorización la hace el USUARIO en su navegador; nunca la inicies por él ni pidas su token.", "GET", "/api/gee/estado", {}, [], "qs"),
    ("chirps_graficos", "Módulo 3: gráficos y tendencia de la última descarga CHIRPS del proyecto (se generan si faltan y se guardan dentro de su carpeta).", "GET", "/api/chirps/graficos", {}, [], "qs"),
    ("escanear_datos", "Premódulo: clasifica los archivos de una carpeta de datos crudos.", "POST", "/api/prep/escanear", {"carpeta": ("string", "ruta absoluta")}, ["carpeta"], "cuerpo"),
    ("revisar_lluvia", "Premódulo: lee un archivo de lluvia y devuelve problemas y calidad por estación (no escribe).", "POST", "/api/prep/precipitacion", {"archivo": ("string", "ruta"), "hoja": ("string", "opcional")}, ["archivo"], "cuerpo"),
    ("revisar_inventario", "Premódulo: revisa un inventario de eventos (SGR/SNGR).", "POST", "/api/prep/inventario", {"archivo": ("string", "ruta"), "hoja": ("string", "opcional")}, ["archivo"], "cuerpo"),
    ("contrastar_inventario", "Premódulo: contrasta la lluvia de una estación con los eventos del inventario (descriptivo, sin causalidad).", "POST", "/api/prep/contrastar",
     {"precip_archivo": ("string", "archivo de lluvia o precipitacion_diaria.csv"), "estacion": ("string", "id"), "inventario_archivo": ("string", "ruta"), "lat": ("number", ""), "lon": ("number", ""), "radio_km": ("number", ""), "ventana_dias": ("integer", "")},
     ["precip_archivo", "estacion", "inventario_archivo"], "cuerpo"),
    ("ordenar_datos", "Premódulo: ordena y fusiona archivos de lluvia en una carpeta NUEVA (crudos intactos; conflictos quedan vacíos).", "POST", "/api/prep/ordenar", {"archivos": ("array", "rutas de lluvia"), "inventario": ("string", "opcional"), "salida": ("string", "opcional")}, ["archivos"], "cuerpo"),
    ("registrar_estacion", "Lleva una estación ya ordenada (lluvia diaria) al proyecto abierto.", "POST", "/api/prep/registrar_estacion", {"preparados": ("string", "carpeta preparados_…"), "estacion": ("string", "id")}, ["preparados", "estacion"], "cuerpo"),
    ("crear_proyecto_desde_sitio", "Crea un proyecto nuevo desde lon/lat y descarga solo MDT 30 m, CN y Manning (Earth Engine), CHIRPS, GEOGLOWS y opcionalmente CELEC. Requiere cuenta de Earth Engine autorizada.", "POST", "/api/sitio/nuevo",
     {"nombre": ("string", ""), "lon": ("number", ""), "lat": ("number", ""), "inicio": ("string", "AAAA-MM-DD"), "fin": ("string", "AAAA-MM-DD"), "medio_km": ("number", "mitad del lado del MDT"), "celec": ("boolean", "cota y caudal de Mazar")}, ["nombre", "lon", "lat"], "cuerpo"),
    ("descargas", "Estado y manifiestos de las descargas del proyecto.", "GET", "/api/descargas", {}, [], "qs"),
    ("descargar", "Lanza UNA descarga: mdt | cn_manning | chirps | geoglows | celec | cmip6_historico | cmip6_futuro.", "POST", "/api/descargas/iniciar", {"fuente": ("string", ""), "parametros": ("object", "lon, lat, inicio, fin, modelos, escenarios…")}, ["fuente"], "cuerpo"),
    ("autorizar_earth_engine", "Abre el navegador para que el usuario autorice Earth Engine con su cuenta.", "POST", "/api/gee/autorizar", {}, [], "cuerpo"),
    ("series_catalogo", "Series disponibles del proyecto (CHIRPS, estaciones, CELEC, GEOGLOWS).", "GET", "/api/series/catalogo", {}, [], "qs"),
    ("series_lluvia", "Totales anuales, climatología y tendencia (Mann-Kendall + Sen) de una serie de lluvia.", "GET", "/api/series/lluvia", {"id": ("string", "p. ej. chirps:celda_nex_mm")}, ["id"], "qs"),
    ("series_caudal", "Hidrograma diario, curva de duración y eventos de una serie de caudal.", "GET", "/api/series/caudal", {"id": ("string", "p. ej. celec:caudal_m3s")}, ["id"], "qs"),
    ("seleccionar_eventos", "Selecciona eventos con lluvia CHIRPS + caudal (umbrales derivados de los datos).", "POST", "/api/eventos/seleccionar", {"lluvia": ("string", "media_caja_mm|pixel_mm|celda_nex_mm"), "caudal": ("string", "celec|geoglows:ID"), "por_bloque": ("integer", "")}, [], "cuerpo"),
    ("escenarios_idf", "Escenarios de lluvia de diseño del proyecto: X (condiciones existentes) e Y (CMIP6, con su tasa de cambio).", "GET", "/api/escenarios/idf", {}, [], "qs"),
    ("verificar_entradas", "Verifica las entradas del proyecto abierto y estima recursos.", "POST", "/api/verificar", {}, [], "cuerpo"),
    ("correr", "Ejecuta UNA corrida pequeña. Con `escenario` usa una IDF alternativa: directa | observado | escalada | chirps | cc_ssp585_<2040-2069|2071-2100>_<mediana|p10|p90|mejor|cuantiles>.", "POST", "/api/corrida/iniciar", {"escenario": ("string", "opcional")}, [], "cuerpo"),
    ("estado_corrida", "Estado y progreso de una corrida.", "GET", "/api/corrida/estado", {"id": ("string", "id de corrida; vacío = la última")}, [], "qs"),
    ("resultado_corrida", "Resumen y evaluación numérica (balance, Courant, áreas) de una corrida.", "GET", "/api/corrida/resultado", {"id": ("string", "id de corrida")}, ["id"], "qs"),
    ("cmip6_compuerta", "Estado de la compuerta de CMIP6 y de la decisión del usuario.", "GET", "/api/cmip6/compuerta", {}, [], "qs"),
    ("cmip6_asumir_baseline", "SOLO si el USUARIO decidió asumir la línea base como correcta: registra su decisión (no la valida). Exige confirmo_usuario=true.", "POST", "/api/cmip6/asumir_baseline", {"confirmo_usuario": ("boolean", "true solo si el usuario lo decidió expresamente")}, ["confirmo_usuario"], "cuerpo"),
    ("cmip6_evaluar", "Evalúa modelos CMIP6 contra CHIRPS: sesgo, RMSE, QQM con validación cruzada, mejor modelo y ensamble.", "POST", "/api/cmip6/evaluar", {"referencia": ("string", "chirps:celda_nex_mm"), "k": ("integer", "tamaño del ensamble")}, [], "cuerpo"),
    ("cmip6_factores", "Tasa de cambio de la lluvia (QDM) de los modelos seleccionados: Tr10/Tr100 24 h, total, p99; mediana ponderada y p10–p90.", "POST", "/api/cmip6/factores", {}, [], "cuerpo"),
    ("hidrologia_casos", "Panel Hidrología y calibración: corridas del proyecto abierto disponibles y estado de las observaciones de caudal (solo las del proyecto, con identidad confirmada).", "GET", "/api/hidrologia/casos", {}, [], "qs"),
    ("hidrologia_serie", "Series reales de una corrida del proyecto: hietograma, hidrogramas simulado/observado, volúmenes acumulados, balance y métricas (solo períodos coincidentes). Sin observaciones = SIMULACIÓN SIN CALIBRAR.", "GET", "/api/hidrologia/serie", {"id": ("string", "id de corrida del proyecto")}, ["id"], "qs"),
    ("hidrologia_exportar", "Exporta tablas CSV, gráficas PNG y manifiesto del panel a una carpeta nueva del proyecto.", "POST", "/api/hidrologia/exportar", {"fuente": ("string", "corrida"), "id": ("string", "id de corrida")}, ["id"], "cuerpo"),
    ("cmip6_resultados", "Último análisis CMIP6: ranking, gráficas, factores y verificación 2015–2025.", "GET", "/api/cmip6/resultados", {}, [], "qs"),
    ("pronostico_consultar", "Pide la lluvia pronosticada de un modelo (gfs=NOAA, ecmwf=Europa) o la estimada por satélite NASA IMERG. Pronóstico a ~25 km: no es una observación ni una alerta oficial.", "POST", "/api/pronostico/consultar",
     {"modelo": ("string", "gfs | ecmwf | imerg"), "dias": ("integer", "1 a 10"), "lon": ("number", "opcional"), "lat": ("number", "opcional"), "muestreo": ("string", "area | punto")}, ["modelo"], "cuerpo"),
    ("pronostico_comparar", "Consulta varios modelos de pronóstico y arma la tabla diaria lado a lado.", "POST", "/api/pronostico/comparar", {"modelos": ("array", "gfs, ecmwf, imerg"), "dias": ("integer", "1 a 10")}, [], "cuerpo"),
    ("pronostico_usar", "Declara una consulta de pronóstico como forzamiento de la corrida 2D (rotulado PRONÓSTICO, nunca «evento observado»). Después se corre UNA corrida.", "POST", "/api/pronostico/usar",
     {"id": ("string", "id de la consulta"), "horas": ("integer", "6 a 95"), "permitir_poca_lluvia": ("boolean", "")}, ["id"], "cuerpo"),
    ("pronostico_geoglows", "Caudal pronosticado de un tramo GEOGLOWS v2 como CSV para hidrograma de entrada (modelo global, orden de magnitud).", "POST", "/api/pronostico/geoglows", {"river_id": ("integer", "tramo GEOGLOWS"), "horas": ("integer", "")}, ["river_id"], "cuerpo"),
    ("peligro_generar", "Genera los mapas de calado, velocidad y peligro de una corrida: GeoTIFF, shapefile y PNG en una carpeta nueva (productos/13_peligro).", "POST", "/api/peligro/generar", {"id": ("string", "id de corrida o «todas»; vacío = la última")}, [], "cuerpo"),
    ("bd_esquema", "Tablas de la base de datos SQLite del proyecto.", "GET", "/api/bd/esquema", {}, [], "qs"),
    ("bd_sincronizar", "Reconstruye la base de datos del proyecto desde sus archivos.", "POST", "/api/bd/sincronizar", {"referencia": ("string", "chirps:celda_nex_mm")}, [], "cuerpo"),
    ("bd_consulta", "Consulta SQL de SOLO LECTURA (una sentencia SELECT/WITH) sobre la base de datos del proyecto.", "POST", "/api/bd/consulta", {"sql": ("string", "SELECT …"), "max_filas": ("integer", "")}, ["sql"], "cuerpo"),
]


def _clave():
    try:
        return ARCHIVO_CLAVE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _http(metodo, ruta, datos=None, timeout=900):
    url = _url() + ruta
    if metodo == "GET" and datos:
        url += "?" + urllib.parse.urlencode({k: v for k, v in datos.items() if v not in (None, "")})
        datos = None
    cab = {"Content-Type": "application/json"}
    if metodo == "POST":
        cab["Authorization"] = "Bearer " + _clave()
    req = urllib.request.Request(url, data=(json.dumps(datos or {}).encode() if metodo == "POST" else None), method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _lanzar():
    """Arranca UCEclima sin ventana si no responde. Devuelve texto de estado."""
    try:
        _http("GET", "/api/latido", timeout=3); return "UCEclima ya estaba abierto."
    except Exception:
        pass
    exe = os.environ.get("UCEclima_EXE")
    cmd = [exe, "--sin-ventana"] if exe else [sys.executable, "-m", "uceclima.ui", "--sin-ventana"]
    subprocess.Popen(cmd, creationflags=0x08000000 if os.name == "nt" else 0, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=os.environ.get("UCECLIMA_RAIZ") or None)
    for _ in range(40):
        time.sleep(1)
        try:
            _http("GET", "/api/latido", timeout=3); return "UCEclima arrancó (sin ventana)."
        except Exception:
            continue
    return "UCEclima no respondió tras 40 s."


def _esquema(props, req):
    return {"type": "object", "properties": {k: ({"type": t, "description": d} if t != "array" else {"type": "array", "items": {"type": "string"}, "description": d}) for k, (t, d) in props.items()}, "required": req}


def listar_herramientas():
    out = [{"name": n, "description": d, "inputSchema": _esquema(p, r)} for n, d, _m, _ru, p, r, _t in HERRAMIENTAS]
    out.append({"name": "lanzar_uceclima", "description": "Arranca UCEclima (sin ventana) si no está abierto.", "inputSchema": _esquema({}, [])})
    out.append({"name": "api_get", "description": "Llamada GET libre a la API de UCEclima (ver /api/openapi.json).", "inputSchema": _esquema({"ruta": ("string", "p. ej. /api/openapi.json")}, ["ruta"])})
    out.append({"name": "api_post", "description": "Llamada POST libre a la API de UCEclima (las reglas del proyecto se aplican igual).", "inputSchema": {"type": "object", "properties": {"ruta": {"type": "string"}, "cuerpo": {"type": "object"}}, "required": ["ruta"]}})
    return out


def _asegurar():
    """Antes de la primera herramienta: si UCEclima no responde lo arranca, y abre el proyecto de este agente (UCECLIMA_PROYECTO)."""
    try:
        _http("GET", "/api/latido", timeout=3)
    except Exception:
        _lanzar()
    if PROYECTO and not _LISTO["proyecto"]:
        try:
            c, b = _http("GET", "/api/estado", timeout=10)
            act = (json.loads(b).get("proyecto") or {}).get("_carpeta") if c == 200 else None
            if not act or os.path.normcase(os.path.abspath(act)) != os.path.normcase(os.path.abspath(PROYECTO)):
                _http("POST", "/api/proyecto/abrir", {"ruta": PROYECTO}, timeout=60)
            _LISTO["proyecto"] = True
        except Exception:
            pass


def llamar(nombre, args):
    args = args or {}
    if nombre == "lanzar_uceclima":
        return _lanzar()
    _asegurar()
    if nombre == "api_get":
        c, b = _http("GET", str(args["ruta"]))
    elif nombre == "api_post":
        c, b = _http("POST", str(args["ruta"]), args.get("cuerpo") or {})
    else:
        h = next((x for x in HERRAMIENTAS if x[0] == nombre), None)
        if not h:
            raise KeyError("Herramienta desconocida: " + nombre)
        _n, _d, metodo, ruta, _p, req, _t = h
        faltan = [k for k in req if args.get(k) in (None, "")]
        if faltan:
            raise ValueError("Faltan parámetros: " + ", ".join(faltan))
        if nombre == "cmip6_asumir_baseline":
            if args.get("confirmo_usuario") is not True:
                raise ValueError("Esa decisión es del usuario: pídesela y llama con confirmo_usuario=true solo si la tomó expresamente.")
            args = {"confirmo": True}
        c, b = _http(metodo, ruta, args)
    txt = b.decode("utf-8", errors="replace")
    if len(txt) > 60000:
        txt = txt[:60000] + "\n… (recortado; pide menos datos o usa bd_consulta con LIMIT)"
    if c >= 400:
        raise RuntimeError(f"HTTP {c}: {txt[:1500]}")
    return txt


def _responder(id_, resultado=None, error=None):
    m = {"jsonrpc": "2.0", "id": id_}
    if error is not None:
        m["error"] = error
    else:
        m["result"] = resultado
    sys.stdout.write(json.dumps(m, ensure_ascii=True) + "\n"); sys.stdout.flush()           # JSON en ASCII: legible con cualquier codificación de stdio


def procesar(msg):
    """Devuelve la respuesta (dict) o None si era una notificación."""
    metodo, id_ = msg.get("method"), msg.get("id")
    if metodo == "initialize":
        v = (msg.get("params") or {}).get("protocolVersion") or PROTOCOLO
        return {"protocolVersion": v, "capabilities": {"tools": {"listChanged": False}, "resources": {}}, "serverInfo": {"name": "uceclima", "version": VERSION}, "instructions": INSTRUCCIONES}
    if metodo == "ping":
        return {}
    if metodo == "tools/list":
        return {"tools": listar_herramientas()}
    if metodo == "resources/list":
        return {"resources": [{"uri": "uceclima://guia", "name": "Guía para agentes de IA", "mimeType": "text/plain"}]}
    if metodo == "resources/read":
        try:
            c, b = _http("GET", "/api/ia", timeout=10); txt = b.decode("utf-8", errors="replace")
        except Exception:
            txt = INSTRUCCIONES
        return {"contents": [{"uri": "uceclima://guia", "mimeType": "text/plain", "text": txt}]}
    if metodo == "tools/call":
        p = msg.get("params") or {}
        try:
            return {"content": [{"type": "text", "text": llamar(p.get("name"), p.get("arguments"))}], "isError": False}
        except urllib.error.URLError:
            return {"content": [{"type": "text", "text": "UCEclima no responde en " + _url() + ". Usa la herramienta lanzar_uceclima o abre el programa."}], "isError": True}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
    if id_ is None:
        return None                                              # notificación (p. ej. notifications/initialized)
    raise LookupError("Método no soportado: " + str(metodo))


def main():
    for f in (sys.stdin, sys.stdout):                              # el exe de Windows abre stdio en cp1252; MCP exige UTF-8
        try:
            f.reconfigure(encoding="utf-8")
        except Exception:
            pass
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            msg = json.loads(linea)
        except json.JSONDecodeError:
            _responder(None, error={"code": -32700, "message": "JSON inválido"}); continue
        try:
            r = procesar(msg)
            if msg.get("id") is not None and r is not None:
                _responder(msg["id"], r)
        except LookupError as e:
            if msg.get("id") is not None:
                _responder(msg["id"], error={"code": -32601, "message": str(e)})
        except Exception as e:
            if msg.get("id") is not None:
                _responder(msg["id"], error={"code": -32603, "message": str(e)})


if __name__ == "__main__":
    main()
