# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Servidor local de la interfaz de UCEclima (solo 127.0.0.1). Biblioteca estándar: sin framework adicional.
La interfaz solo lee/valida y lanza procesos del núcleo; no contiene ecuaciones. Todas las acciones que cambian algo (POST) exigen el token de sesión."""
import collections, json, mimetypes, os, secrets, subprocess, sys, threading, time, traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import uceclima
TR_PERMITIDOS = (2, 5, 10, 25, 50, 100)                     # Eta: los Tr de las tablas del INAMHI
from . import proyecto as P, demo, mapas, visor_api, api_abierta, evento_api, prep_api, sitio_api, ia_config
from .. import entregas as ENT, idf_x as IDFX, premodulo as PRE, gee_conexion as GEEC, hidrologia_api as HID, basedatos as BD, cmip6_descarga as CMD, cmip6_sesgo as CSB, escenarios_idf as ESC, series_api as SER, analisis_eventos as AEV, estaciones as EST, terreno_import as TIMP, preparacion as PREP, descargas as DESC
from .trabajos import GestorTrabajos
from . import cuenca_api, wrf_api

AQUI = Path(__file__).resolve().parent
STATIC = AQUI / "static"
RAIZ = AQUI.parents[1]                         # carpeta MILAGRO
NUCLEO = RAIZ / "climanet"


SESION = Path.home() / ".uceclima" / "sesion_lambda.json"    # Lambda: archivo propio (no pisa la sesión de Eta ni de Zeta); la primera vez lee la de Eta o la de Zeta
SESION_ETA = Path.home() / ".uceclima" / "sesion_eta.json"
SESION_ZETA = Path.home() / ".uceclima" / "sesion_zeta.json"     # Zeta «modo Word»: solo la ruta del último proyecto (nunca credenciales)


def _es_temporal(carpeta):
    import tempfile
    try:
        return str(Path(carpeta).resolve()).lower().startswith(str(Path(tempfile.gettempdir()).resolve()).lower())
    except OSError:
        return True


def _sesion_guardar(carpeta):
    if _es_temporal(carpeta):                                  # las pruebas automáticas no pisan la sesión de la persona
        return
    try:
        SESION.parent.mkdir(parents=True, exist_ok=True)
        SESION.write_text(json.dumps({"proyecto": str(carpeta), "abierto": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _sesion_restaurar(estado):
    """Al arrancar: reabre el último proyecto (si sigue existiendo). Devuelve la carpeta o None."""
    try:
        s = json.loads(next((f for f in (SESION, SESION_ETA, SESION_ZETA) if f.exists()), SESION).read_text(encoding="utf-8")) if any(f.exists() for f in (SESION, SESION_ETA, SESION_ZETA)) else {}
        c = s.get("proyecto")
        if c and (Path(c) / "proyecto_uceclima.json").exists():
            estado.abrir(c); estado.log("Proyecto reabierto donde lo dejaste", c, "proyecto", "ok", "sistema")
            return c
    except Exception:
        pass
    return None


def bitacora_escribir(carpeta, e):
    try:
        f = Path(carpeta) / "registro" / "bitacora.jsonl"; f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as g: g.write(json.dumps(e, ensure_ascii=False) + "\n")
    except OSError:
        pass


def bitacora_leer(carpeta, n=300):
    f = Path(carpeta) / "registro" / "bitacora.jsonl"
    if not f.exists():
        return []
    try:
        lin = f.read_bytes()[-400_000:].decode("utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for l in lin:
        try: out.append(json.loads(l))
        except ValueError: continue
    return out


def lo_hecho(carpeta, corridas):
    """Eta (Mejora 1 · B): «Lo que llevas hecho», armado con los archivos del proyecto (no con la memoria del navegador)."""
    c = Path(carpeta); pasos = []
    def fecha(p):
        try: return datetime.fromtimestamp(Path(p).stat().st_mtime).strftime("%d-%m %H:%M")
        except OSError: return ""
    def ult(patron):
        l = sorted(c.glob(patron)); return l[-1] if l else None
    pj = c / "proyecto_uceclima.json"
    pasos.append({"modulo": "proyecto", "paso": "1 · Proyecto creado", "hecho": pj.exists(), "cuando": fecha(pj), "detalle": c.name})
    ch = ult("datos_descargados/chirps*") or ult("chirps*")
    pasos.append({"modulo": "chirps", "paso": "3 · Lluvia CHIRPS", "hecho": bool(ch), "cuando": fecha(ch) if ch else "", "detalle": ch.name if ch else ""})
    idf = ult("registro/idf/*.csv")
    pasos.append({"modulo": "idf", "paso": "4 · IDF (X)", "hecho": bool(idf), "cuando": fecha(idf) if idf else "", "detalle": idf.name if idf else ""})
    mdt = ult("datos_descargados/mdt_*")
    pasos.append({"modulo": "terreno", "paso": "5 · Terreno (MDT)", "hecho": bool(mdt), "cuando": fecha(mdt) if mdt else "", "detalle": mdt.name if mdt else ""})
    act = c / "cuenca" / "activa.json"; a = {}
    try: a = json.loads(act.read_text(encoding="utf-8")) if act.exists() else {}
    except (OSError, ValueError): a = {}
    pasos.append({"modulo": "hidro", "paso": "6 · Cuenca aceptada", "hecho": bool(a), "cuando": fecha(act) if a else "", "detalle": (f"{a.get('carpeta', '')} · {a.get('area_km2', 0):,.1f} km²".replace(",", " ") if a else "")})
    comp = [r for r in corridas if r.get("estado") == "completado"]
    pasos.append({"modulo": "corrida", "paso": "7 · Corridas 2D", "hecho": bool(comp), "cuando": (comp[0].get("fin") or comp[0].get("inicio") or "").replace("T", " ")[:16] if comp else "",
                  "detalle": f"{len(comp)} completada(s)" + (f" · última: {comp[0]['id']}" if comp else "") + "".join(f" · {r['id']}: {r['estado']}" for r in corridas if r.get("estado") in ("en_curso", "interrumpido"))})
    cm = ult("registro/cmip6/analisis_*")
    pasos.append({"modulo": "cmip6", "paso": "9 · CMIP6 (factores Y)", "hecho": bool(cm), "cuando": fecha(cm) if cm else "", "detalle": cm.name if cm else ""})
    en = ult("entregas/entrega_*")
    pasos.append({"modulo": "entregas", "paso": "11 · Entrega armada", "hecho": bool(en), "cuando": fecha(en) if en else "", "detalle": en.name if en else ""})
    la = ult("productos/12_validacion_campo/laminas_*")
    pasos.append({"modulo": "campo", "paso": "12 · Láminas de validación", "hecho": bool(la), "cuando": fecha(la) if la else "", "detalle": la.name if la else ""})
    return pasos


def _corridas_a_bitacora(E, corr):
    """Cada corrida que cambia de estado (también las que terminaron con el programa cerrado) queda una vez en la bitácora."""
    if not E.carpeta: return
    f = Path(E.carpeta) / "registro" / "bitacora_corridas.json"
    try: vistos = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError): vistos = {}
    cambio = False
    for r in corr:
        est = r.get("estado")
        if est and vistos.get(r["id"]) != est and est != "pendiente":
            vistos[r["id"]] = est; cambio = True
            txt = {"en_curso": "Corrida en curso", "completado": "Corrida terminada", "fallido": "Corrida fallida", "cancelado": "Corrida cancelada", "interrumpido": "Corrida interrumpida (se puede reanudar si dejó punto de control)"}.get(est, est)
            E.log(txt, f"{r['id']} · {r.get('mensaje', '')}", "corrida", "error" if est in ("fallido", "interrumpido") else "ok", "sistema", est not in ("fallido", "interrumpido"))
    if cambio:
        try: f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(vistos, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError: pass


def _estado_ui(carpeta, cambios=None):
    """registro/estado_ui.json del proyecto: módulo donde se quedó la persona y lo escrito en los campos de cada módulo. Se fusiona; nada de credenciales."""
    f = Path(carpeta) / "registro" / "estado_ui.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        d = {}
    if cambios is not None:
        if cambios.get("ruta"):
            d["ruta"] = str(cambios["ruta"])[:40]
        if isinstance(cambios.get("campos"), dict) and cambios.get("ruta"):
            limpio = {str(k)[:60]: str(v)[:2000] for k, v in list(cambios["campos"].items())[:200] if not any(s in str(k).lower() for s in ("clave", "token", "pass", "secret", "codigo_gee"))}
            d.setdefault("campos", {})[str(cambios["ruta"])[:40]] = limpio
        d["actualizado"] = datetime.now().isoformat(timespec="seconds")
        if cambios.get("guardado"):
            d["ultimo_guardado"] = d["actualizado"]
        f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


class Estado:
    def __init__(self):
        self.token = secrets.token_urlsafe(24)
        self.clave_api = api_abierta.cargar_clave()
        self.descargas = DESC.GestorDescargas()
        self.actividad = collections.deque(maxlen=400); self.seq = 0
        self.descargas.hook = self._hook_descarga; self._ultimo_pct = {}
        self.puerto = None
        self.datos = None; self.carpeta = None; self.gestor = None
        self.lock = threading.Lock()

    def abrir(self, ruta):
        datos, carpeta = P.abrir(ruta)
        self.datos, self.carpeta = datos, carpeta
        try:                                                       # el agente de VS Code queda listo en la carpeta del proyecto
            from . import agente_vscode
            if not str(carpeta).lower().startswith(str(Path(os.environ.get("TEMP", "~"))).lower()):
                agente_vscode.configurar(carpeta)                  # VS Code/Copilot y Claude Code (solo reescribe si algo cambió)
        except Exception:
            pass
        self.gestor = GestorTrabajos(carpeta / datos["carpeta_resultados"])
        _sesion_guardar(carpeta)                                   # Zeta «modo Word»: el último proyecto se reabre solo al volver
        with self.lock:                                            # Eta (Mejora 1): la pantalla vuelve a mostrar lo hecho, leído del disco
            self.actividad.clear()
            for e in bitacora_leer(carpeta, 60):
                self.seq += 1; self.actividad.append({**e, "n": self.seq, "anterior": True})
        return datos

    def bitacora(self, modulo, titulo, detalle=""):
        self.log(titulo, detalle, modulo, "ok", "interfaz")

    def cfg(self):
        return P.config_climanet(self.datos, self.carpeta)

    def log(self, titulo, detalle="", modulo=None, nivel="info", origen="sistema", ok=True):
        """Bitácora en vivo que la pantalla muestra (qué hace la IA/API, las descargas y las corridas). No guarda datos sensibles."""
        e = {"t": datetime.now().strftime("%H:%M:%S"), "fecha": datetime.now().strftime("%Y-%m-%d"), "titulo": str(titulo)[:160], "detalle": str(detalle)[:300], "modulo": modulo, "nivel": nivel, "origen": origen, "ok": ok}
        with self.lock:
            self.seq += 1
            self.actividad.append({"n": self.seq, **e})
        if self.carpeta and not (titulo == "Descargando datos" and nivel == "info"):      # Eta (Mejora 1): bitácora del proyecto en disco, «como un chat con memoria»
            bitacora_escribir(self.carpeta, e)

    def _hook_descarga(self, did, estado, mensaje, progreso):
        pct = int((progreso or 0) * 10) * 10
        if estado == "en_curso" and self._ultimo_pct.get(did) == pct and pct not in (0,):
            return
        self._ultimo_pct[did] = pct
        self.log({"en_curso": "Descargando datos", "completado": "Descarga completada", "fallido": "Descarga fallida"}.get(estado, "Descarga"), f"{mensaje} · {int((progreso or 0) * 100)} %", "gee",
                 "error" if estado == "fallido" else ("ok" if estado == "completado" else "info"), "descargas", estado != "fallido")
        if estado == "completado":                                                   # Zeta Z4: cada descarga terminada deja sus productos ordenados
            threading.Thread(target=_productos_tras, args=("descarga",), daemon=True).start()


ESTADO = Estado()

MODULOS = [
    {"id": "preparacion", "nombre": "0 · Preparación de datos", "estado": "implementado", "resumen": "Carga Excel/CSV de precipitación y caudal, los guarda en memoria y los grafica aquí mismo (series, tendencias, climatología, curva de duración)."},
    {"id": "proyecto", "nombre": "1 · Proyecto", "estado": "implementado", "resumen": "Crear la carpeta del proyecto (con las series cargadas) o abrir uno existente. Nada se sobrescribe."},
    {"id": "gee", "nombre": "2 · Datos / GEE", "estado": "implementado", "resumen": "Tu proyecto de Google Cloud, autorización con tu cuenta e inicialización verificada de Earth Engine; descargas del proyecto (MDT, CN/Manning, GEOGLOWS, CELEC)."},
    {"id": "chirps", "nombre": "3 · CHIRPS", "estado": "implementado", "resumen": "Descarga las series CHIRPS del sitio, genera gráficos y tendencias y lo guarda todo en la carpeta del proyecto."},
    {"id": "idf", "nombre": "4 · IDF (X)", "estado": "implementado", "resumen": "La lluvia de diseño de las condiciones existentes (X): en Ecuador, el libro del INAMHI; en cualquier otro lugar, IDF desde CHIRPS o IDF propia con su fuente (Zeta)."},
    {"id": "terreno", "nombre": "5 · Terreno", "estado": "parcial", "resumen": "Verificación de CRS, resolución y cobertura + vista previa; comprueba si un MDT de dron coincide con la zona de trabajo y con el terreno de Earth Engine."},
    {"id": "hidro", "nombre": "6 · hidro", "estado": "implementado", "resumen": "Todo lo de hidrología en un solo lugar, con pestañas: Cuenca (tu shape, delineación desde el MDT o malla CHIRPS de 5 km), Hidrología (series de las corridas) y Calibración (caudal observado, eventos de ajuste y validación, barrido de parámetros; tú aceptas)."},
    {"id": "corrida", "nombre": "7 · land · Corrida 2D", "estado": "implementado", "resumen": "Comprobación previa, una tarea por vez, progreso, cancelar y registro persistente."},
    {"id": "pronostico", "nombre": "7b · Pronóstico (GFS · ECMWF · NASA)", "estado": "implementado", "resumen": "Lluvia pronosticada por GFS (NOAA) y ECMWF (Europa) y lluvia ya caída estimada por NASA IMERG; tabla a varios días, gráfico y uso como forzamiento de la corrida 2D (rotulado PRONÓSTICO), más el caudal pronosticado de GEOGLOWS. Investigación, no alerta oficial."},
    {"id": "evaluacion", "nombre": "8 · land · Evaluación", "estado": "parcial", "resumen": "Volumen m³/%, Courant, pasos y mapa. Caudal/nivel por sección y comparación con referencia: pendiente."},
    {"id": "mapa2d", "nombre": "8b · Mapa 2D X frente a Y (tipo RAS)", "estado": "implementado", "resumen": "Planta del calado máximo como en RAS Mapper: X condiciones existentes, Y cambio climático CMIP6 y la diferencia Y − X, con terreno sombreado, ríos, lectura de celda, áreas y exportar PNG (Zeta)."},
    {"id": "visor", "nombre": "8c · Visor 3D de resultados", "estado": "parcial", "resumen": "Terreno y capas reales de una corrida (calado máximo, velocidad máxima, duración) en 3D isométrico con control de capas, exageración vertical y capas fantasma de escenarios."},
    {"id": "cmip6", "nombre": "9 · CMIP6", "estado": "implementado", "resumen": "Modelos NEX-GDDP-CMIP6 contra CHIRPS; mejor modelo = RMSE más bajo; tasa de cambio SSP5-8.5 (Y, magenta)."},
    {"id": "wrf", "nombre": "10 · WRF", "estado": "implementado", "resumen": "Leer salidas WRF (wrfout o NetCDF) como lluvia X o Y, con corrección QQM, y preparar corridas WRF para Linux/WSL."},
    {"id": "entregas", "nombre": "11 · Resultados y entregas", "estado": "implementado", "resumen": "Todo en shapes, CSV/Excel, mapas y figuras; el botón de calado, velocidad y peligro (TIFF, shapefile y PNG); y la carpeta de insumos para los siguientes programas: BCA FEMA y El Niño / La Niña. Incluye el visor VOTEX 4D (maqueta)."},
    {"id": "campo", "nombre": "12 · Validación de campo", "estado": "implementado", "resumen": "Encuesta HTML «¿Se inunda?» de la zona de estudio con los mapas del modelo (X y Y), para preguntar a la comunidad hasta dónde llega el agua y registrar las respuestas en tu sitio web; importar las marcas, contrastarlas con el calado del modelo y generar las láminas con buffer acumulativo y X frente a Y (Zeta, como el Taller 3 de Milagro)."},
    {"id": "contaminantes", "nombre": "☁ Contaminantes", "estado": "parcial", "resumen": "Dispersión de un derrame en un tramo de río (vista isométrica y planta sobre satélite). Base pedagógica, sin calibrar."}
]


def _json(handler, obj, code=200):
    cuerpo = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(code); handler.send_header("Content-Type", "application/json; charset=utf-8"); handler.send_header("Content-Length", str(len(cuerpo)))
    handler.send_header("Cache-Control", "no-store"); handler.end_headers(); handler.wfile.write(cuerpo)


def _archivo(handler, path, tipo=None):
    path = Path(path)
    if not path.is_file():
        return _json(handler, {"error": "No existe el archivo solicitado."}, 404)
    b = path.read_bytes()
    fijos = {".mjs": "text/javascript; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg"}
    handler.send_response(200); handler.send_header("Content-Type", tipo or fijos.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
    handler.send_header("Content-Length", str(len(b))); handler.send_header("Cache-Control", "no-store"); handler.end_headers(); handler.wfile.write(b)


def _texto(handler, texto, tipo):
    b = texto.encode("utf-8")
    handler.send_response(200); handler.send_header("Content-Type", tipo); handler.send_header("Content-Length", str(len(b)))
    handler.send_header("Cache-Control", "no-store"); handler.end_headers(); handler.wfile.write(b)


def _dialogo(tipo):
    """Diálogo nativo de Windows en un proceso aparte (Tk exige el hilo principal). Devuelve la ruta o ''."""
    cod = ("import tkinter as tk\nfrom tkinter import filedialog as f\nr=tk.Tk();r.withdraw();r.attributes('-topmost',True)\n"
           + ("print(f.askdirectory(title='Elegir carpeta'))" if tipo == "carpeta" else
              "import json\nprint(json.dumps(list(f.askopenfilenames(title='Elegir archivos de datos',filetypes=[('Excel y CSV','*.xlsx *.xlsm *.xls *.csv *.txt'),('Todos','*.*')]))))" if tipo == "datos" else
              "print(f.askopenfilename(title='Elegir capa',filetypes=[('Capas vectoriales','*.shp *.gpkg *.geojson *.json *.kml'),('Todos','*.*')]))" if tipo == "vector" else
              "print(f.askopenfilename(title='Elegir archivo',filetypes=[('Excel y CSV','*.xlsx *.xls *.csv *.txt'),('Todos','*.*')]))" if tipo == "tabla" else
              "print(f.askopenfilename(title='Elegir ráster',filetypes=[('GeoTIFF','*.tif *.tiff'),('Todos','*.*')]))" if tipo == "raster" else
              "print(f.askopenfilename(title='Elegir archivo',filetypes=[('Proyecto UCEclima','*.json'),('Todos','*.*')]))"))
    cmd = [sys.executable, "--dialogo", tipo] if getattr(sys, "frozen", False) else [sys.executable, "-c", cod]
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000 if os.name == "nt" else 0)
    if tipo == "datos":
        try: return [x.replace("/", os.sep) for x in json.loads(r.stdout.strip() or "[]")]
        except Exception: return []
    return r.stdout.strip().replace("/", os.sep)


# ------------------------------------------------------------------------------------------------ rutas
def api_get(h, ruta, q):
    E = ESTADO
    if ruta.startswith(("/api/cuenca/", "/api/calibracion/")):
        return cuenca_api.get(h, E, ruta, q, _json)
    if ruta.startswith("/api/wrf/") or ruta.startswith("/api/cmip6/toe") or ruta == "/api/cmip6/figura.png":
        return wrf_api.get(h, E, ruta, q, _json)
    if ruta == "/api/openapi.json":
        return _json(h, api_abierta.openapi(uceclima.__version__))
    if ruta == "/api/docs":
        return _texto(h, api_abierta.docs_html(uceclima.__version__), "text/html; charset=utf-8")
    if ruta == "/api/ia":
        return _texto(h, api_abierta.GUIA_IA.format(puerto=ESTADO.puerto, archivo_clave=str(api_abierta.ARCHIVO_CLAVE)), "text/plain; charset=utf-8")
    if ruta == "/api/descargas":
        if not E.datos: return _json(h, {"descargas": [], "activa": False})
        return _json(h, {"descargas": DESC.listar(E.carpeta), "activa": E.descargas.activa(), "fuentes": list(DESC.FUENTES)})
    if ruta == "/api/proyecto/evento":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        return _json(h, {"evento": evento_api.actual(E)})
    if ruta == "/api/estaciones":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        return _json(h, {"estaciones": EST.listar(E.carpeta), "nota": "Un evento de estación puede conducir la corrida (POST /api/proyecto/evento); el modelo sigue sin calibrar."})
    if ruta == "/api/corrida/forzamiento":                                   # G17/G18: lo que conduce la corrida (evento observado + hidrogramas de entrada)
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        _, cfg_f = E.cfg()
        return _json(h, {"evento_observado": cfg_f.get("evento_observado"), "entradas_hidrograma": cfg_f.get("entradas_hidrograma") or [], "sim_horas": cfg_f.get("sim_horas"), "aoi": cfg_f.get("aoi"),
                         "cuencas_externas": cfg_f.get("cuencas_externas") or [], "cuencas": sorted(x.name for x in (Path(E.carpeta) / "cuenca").glob("*") if (x / "cuenca.gpkg").exists()),
                         "estaciones": [{"id": r["id"], "nombre": r.get("nombre"), "zona": (r.get("zona_horaria_origen") or "")} for r in EST.listar(E.carpeta)]})
    if ruta == "/api/estaciones/serie":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            d = EST.serie(E.carpeta, (q.get("id") or [""])[0], (q.get("inicio") or [None])[0], (q.get("fin") or [None])[0])
            return _json(h, {"fecha": d["fecha"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist(), "lluvia_mm": [None if v != v else round(float(v), 3) for v in d["lluvia_mm"]]})
        except EST.EstacionError as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/ia/config":
        return _json(h, ia_config.estado((q.get("carpeta") or [None])[0]))
    if ruta == "/api/ia/info":
        return _json(h, {"url": f"http://127.0.0.1:{ESTADO.puerto}", "docs": "/api/docs", "openapi": "/api/openapi.json", "guia": "/api/ia", "archivo_clave": str(api_abierta.ARCHIVO_CLAVE)})
    if ruta == "/api/cmip6/idf":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            _, cfg = E.cfg(); defs, base = ESC.definiciones(E.carpeta, cfg, IDFX.estacion_proyecto(cfg, E.datos), int(cfg.get("storm_min", 180)))
            idc = (q.get("id") or [""])[0]; d = next((z for z in defs if z["id"] == idc), None)
            if not d or "factor_por_tr" not in d: return _json(h, {"error": "Escenario Y desconocido."}, 400)
            import pandas as pd
            adj = base.mul(pd.Series({int(k): v_ for k, v_ in d["factor_por_tr"].items()}), axis=0)
            return _json(h, {"id": idc, "nombre": d["nombre"], "duraciones_min": [int(c) for c in base.columns], "tr": [int(i) for i in base.index], "idf_oficial": base.round(2).values.tolist(), "idf_ajustada": adj.round(2).values.tolist(),
                             "factor_por_tr": d["factor_por_tr"], "nota": d["fuente"]})
        except (ESC.EscenarioError, OSError, ValueError, KeyError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/bd/esquema":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, {"archivo": str(BD.ruta(E.carpeta)), "existe": BD.ruta(E.carpeta).exists(), "tablas": BD.esquema(E.carpeta) if BD.ruta(E.carpeta).exists() else []})
        except (BD.BDError, OSError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/cmip6/anual":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, CSB.anual(E.carpeta))
        except (CSB.SesgoError, BD.BDError, OSError, KeyError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/cmip6/resultados":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        b = Path(E.carpeta) / "registro" / "cmip6"; c = sorted(b.glob("analisis_*")) if b.exists() else []
        if not c: return _json(h, {"analisis": None, "decision": CMD.decision(E.carpeta)})
        d = c[-1]; out = {"analisis": d.name, "decision": CMD.decision(E.carpeta), "resumen": json.loads((d / "resumen_analisis.json").read_text(encoding="utf-8")), "graficas": json.loads((d / "graficas.json").read_text(encoding="utf-8"))}
        import pandas as pd
        rk = pd.read_csv(d / "metricas_modelos.csv"); sl = pd.read_csv(d / "seleccionados.csv")
        rk["seleccionado"] = rk["modelo"].isin(sl["modelo"]).astype(int)
        out["ranking"] = rk.replace({float("nan"): None}).to_dict("records")
        if (d / "factores_cc.json").exists(): out["factores"] = json.loads((d / "factores_cc.json").read_text(encoding="utf-8"))
        if (d / "verificacion_2015_2025.csv").exists(): out["verificacion"] = pd.read_csv(d / "verificacion_2015_2025.csv").replace({float("nan"): None}).to_dict("records")
        return _json(h, out)
    if ruta == "/api/prep/lote":
        return _json(h, PRE.estado_lote((q.get("desde") or [0])[0]))
    if ruta == "/api/prep/memoria":
        return _json(h, PRE.memoria())
    if ruta == "/api/prep/catalogo":
        return _json(h, PRE.catalogo_series())
    if ruta in ("/api/prep/lluvia", "/api/prep/caudal"):
        try:
            sid = (q.get("id") or [""])[0]
            return _json(h, PRE.datos_lluvia(sid) if ruta.endswith("lluvia") else PRE.datos_caudal(sid))
        except (PRE.PremoduloError, KeyError) as e: return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/proyecto/archivo":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        rel = (q.get("ruta") or [""])[0]; f = (E.carpeta / rel).resolve()
        if E.carpeta.resolve() not in f.parents or f.suffix.lower() not in (".png", ".csv", ".json", ".jpg", ".svg"):
            return _json(h, {"error": "Archivo no permitido."}, 403)
        return _archivo(h, f)
    if ruta == "/api/chirps/graficos":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        ds = sorted((E.carpeta / "datos_descargados").glob("chirps_*")) + sorted((E.carpeta / "datos_descargados").glob("sitio_*/chirps"))
        ds = [d for d in ds if (d / "chirps_diario.csv").exists()]
        if not ds: return _json(h, {"descarga": None, "graficos": [], "nota": "Aún no hay una descarga CHIRPS en este proyecto."})
        d = max(ds, key=lambda x: (x / "chirps_diario.csv").stat().st_mtime); g = d / "graficos"
        if not (g / "chirps_resumen.json").exists():                                                  # descarga anterior sin gráficos: se generan ahora, dentro de la misma carpeta
            try:
                from uceclima import chirps_salidas
                chirps_salidas.generar(d)
            except Exception as e:
                return _json(h, {"error": "No se pudieron generar los gráficos: " + str(e)[:200]}, 400)
        res = json.loads((g / "chirps_resumen.json").read_text(encoding="utf-8")) if (g / "chirps_resumen.json").exists() else {}
        return _json(h, {"descarga": d.name, "carpeta": str(d.relative_to(E.carpeta)).replace("\\", "/"), "graficos": sorted(p.name for p in g.glob("*.png")), "tablas": sorted(p.name for p in g.glob("*.csv")), "resumen": res})
    if ruta in ("/api/idf/x", "/api/idf/x/png"):
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            try:                                                                       # Zeta: fuera de Ecuador el libro del INAMHI no aplica (antes respondía con un error ilegible)
                import re as _re
                _m = _re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(E.datos.get("ubicacion", "")))
                if _m and not sitio_api.en_ecuador(float(_m.group(1)), float(_m.group(2))):
                    return _json(h, {"error": "Sitio fuera de Ecuador: el libro de intensidades del INAMHI no aplica aquí. Usa la tarjeta «IDF fuera de Ecuador o sin IDF oficial (Zeta)» de arriba: IDF desde CHIRPS o IDF propia con su fuente.", "fuera_de_ecuador": True}, 400)
            except (ValueError, TypeError):
                pass
            est = (q.get("estacion") or [None])[0]; dur = int((q.get("duracion") or [180])[0]); tr = int((q.get("tr") or [100])[0])
            if not est:
                _, cfg0 = E.cfg(); est = (cfg0.get("idf_x") or {}).get("estacion") or (cfg0.get("idf_inamhi") or {}).get("estacion")
            datos_idf = E.datos
            if (q.get("punto") or ["sitio"])[0] == "cuenca":                          # C23: punto IDF en el centroide de la cuenca activa
                act = Path(E.carpeta) / "cuenca" / "activa.json"
                if not act.exists(): return _json(h, {"error": "No hay cuenca activa: el punto IDF sigue siendo el sitio del proyecto."}, 400)
                import geopandas as gpd
                a_ = json.loads(act.read_text(encoding="utf-8")); cpt = gpd.read_file(Path(E.carpeta) / a_["carpeta"] / "cuenca.gpkg").to_crs(4326).geometry.unary_union.representative_point()
                datos_idf = {**E.datos, "ubicacion": f"lon {cpt.x:.4f}, lat {cpt.y:.4f}"}
            res = IDFX.calcular(datos_idf, est, dur, tr)
            if ruta.endswith("/png"):
                nombre = (q.get("nombre") or ["idf_curvas.png"])[0]
                if nombre not in ("idf_curvas.png", "idf_modos_tr100.png", "tormenta_diseno.png"): return _json(h, {"error": "Gráfica desconocida."}, 400)
                b = IDFX.png(res, nombre); h.send_response(200); h.send_header("Content-Type", "image/png"); h.send_header("Content-Length", str(len(b))); h.send_header("Cache-Control", "no-store"); h.end_headers(); h.wfile.write(b); return
            _, cfg1 = E.cfg(); res["fijada"] = cfg1.get("idf_x"); return _json(h, res)
        except (ValueError, KeyError, IndexError) as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/entregas":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        return _json(h, {"entregas": ENT.listar(E.carpeta), "corridas": [{"id": c["id"], "escenario": c["escenario"], "tipo": c["tipo"]} for c in ENT.corridas(E.carpeta)], "programas": ENT.PROGRAMAS})
    if ruta == "/api/gee/catalogo":
        from uceclima import capas_gee
        return _json(h, capas_gee.catalogo())
    if ruta == "/api/gee/estado":
        return _json(h, GEEC.estado())
    if ruta == "/api/hidrologia/casos":
        try: return _json(h, HID.casos(E.carpeta if E.datos else None))
        except HID.HidroError as e: return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/hidrologia/serie":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            idr = (q.get("id") or [""])[0]
            return _json(h, HID.serie_corrida(E.carpeta, idr, HID.leer_observaciones(E.carpeta)[0]))
        except (HID.HidroError, KeyError, FileNotFoundError, ValueError) as e: return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/escenarios/idf":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            _, cfg = E.cfg()
            defs, _b = ESC.definiciones(E.carpeta, cfg, (q.get("estacion") or [IDFX.estacion_proyecto(cfg, E.datos)])[0], int(cfg.get("storm_min", 180)))
            return _json(h, {"escenarios": defs, "Tr": ESC.TR, "nota": "Todos son diseños históricos; reescalar es un factor único que conserva la forma de la IDF de la estación. Ninguno es cambio climático."})
        except (ESC.EscenarioError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/visor/capa":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, visor_api.capa(E, (q.get("id") or [""])[0], (q.get("capa") or ["hmax"])[0]))
        except (ValueError, OSError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/visor/fotos":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, visor_api.fotos(E, (q.get("id") or [""])[0]))
        except (ValueError, OSError, KeyError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/corrida/hietograma":
        run = (q.get("id") or [""])[0]
        f = next(iter((E.gestor.base / run).rglob("hietograma.csv")), None) if E.gestor and run else None
        if not f: return _json(h, {"error": "No existe el hietograma de esa corrida."}, 404)
        import pandas as pd
        d = pd.read_csv(f); ent = json.loads((E.gestor.base / run / "entrada.json").read_text(encoding="utf-8")) if (E.gestor.base / run / "entrada.json").exists() else {}
        return _json(h, {"id": run, "escenario": ent.get("escenario"), "inicio_s": d["inicio_s"].tolist(), "fin_s": d["fin_s"].tolist(), "lluvia_mm": d["lluvia_mm"].round(3).tolist()})
    if ruta == "/api/actividad":
        desde = int((q.get("desde") or ["0"])[0] or 0)
        with E.lock:
            ev = [e for e in E.actividad if e["n"] > desde]; ultimo = E.seq
        return _json(h, {"eventos": ev, "ultimo": ultimo, "corrida_activa": bool(E.gestor and E.gestor.activa()), "descarga_activa": E.descargas.activa()})
    if ruta.startswith("/api/series/"):
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if ruta == "/api/series/catalogo": return _json(h, {"series": SER.catalogo(E.carpeta)})
            sid = (q.get("id") or [""])[0]
            if ruta == "/api/series/lluvia": return _json(h, SER.lluvia(E.carpeta, sid))
            if ruta == "/api/series/caudal": return _json(h, SER.caudal(E.carpeta, sid))
            if ruta == "/api/series/evento": return _json(h, SER.evento(E.carpeta, sid))
            return _json(h, {"error": "Ruta de series no encontrada"}, 404)
        except (SER.SerieError, KeyError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/latido":
        import time
        _LATIDO[0] = time.time(); return _json(h, {"ok": True})
    if ruta in ("/api/pronostico/lista", "/api/pronostico/serie"):                    # Lambda 7b: consultas de pronóstico del proyecto
        from .. import pronostico as PRO
        try:
            if ruta == "/api/pronostico/serie":
                if not E.carpeta: return _json(h, {"error": "Abre un proyecto."}, 400)
                return _json(h, PRO.serie(E.carpeta, (q.get("id") or [""])[0]))
            sitio = None
            try: sitio = list(PRO._sitio(E.datos, None, None)) if E.datos else None
            except PRO.PronosticoError: pass
            return _json(h, {"consultas": PRO.listar(E.carpeta) if E.carpeta else [], "modelos": {k: {"nombre": v["nombre"], "tipo": v["tipo"], "max_dias": v["max_dias"]} for k, v in PRO.MODELOS.items()},
                             "sitio_lonlat": sitio, "aviso": PRO.AVISO, "atribucion": PRO.ATRIBUCION})
        except (PRO.PronosticoError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/bitacora":                                                        # Eta (Mejora 1): todo lo hecho en el proyecto, leído del disco
        if not E.carpeta: return _json(h, {"eventos": [], "hecho": []})
        corr = E.gestor.listar() if E.gestor else []
        return _json(h, {"eventos": bitacora_leer(E.carpeta, int((q.get("n") or ["300"])[0])), "hecho": lo_hecho(E.carpeta, corr), "proyecto": str(E.carpeta)})
    if ruta == "/api/estado":
        corr = E.gestor.listar() if E.gestor else []
        _corridas_a_bitacora(E, corr)
        return _json(h, {"version": uceclima.__version__, "python": sys.version.split()[0], "proyecto": ({k: v for k, v in E.datos.items()} if E.datos else None),
                         "recientes": P.recientes(), "carpeta_proyectos": str(sitio_api.RAIZ_PROYECTOS), "corrida_activa": bool(E.gestor and E.gestor.activa()), "corridas": corr[:15], "modulos": MODULOS})
    if ruta == "/api/proyectos_demo":
        return _json(h, [{"id": "mazar", "nombre": "Mazar · punto de partida (datos reales, descargados con UCEclima)", "carpeta": str(demo.RAIZ / "mazar")},
                         {"id": "sintetico", "nombre": "Demostración SINTÉTICA", "carpeta": str(demo.RAIZ / "demo_sintetico")}])
    if ruta == "/api/corrida/estado":
        run = (q.get("id") or [None])[0]
        if not E.gestor: return _json(h, {"error": "Abre un proyecto."}, 400)
        if not run:
            l = E.gestor.listar(); run = l[0]["id"] if l else None
        if not run: return _json(h, {"estado": "sin_corridas"})
        e = E.gestor.estado_de(E.gestor.base / run); e["log"] = E.gestor.cola_log(run); return _json(h, e)
    if ruta == "/api/corrida/resultado":
        run = (q.get("id") or [None])[0]; r = E.gestor.resultado(run)
        if isinstance(r, dict) and r.get("resumen") and run not in _PROD_CORRIDAS:     # Zeta Z4: la primera vez que se consulta una corrida terminada, sus productos se ordenan
            _PROD_CORRIDAS.add(run); threading.Thread(target=_productos_tras, args=("corrida",), daemon=True).start()
        return _json(h, r)
    if ruta == "/api/papers/receta":                                                   # Zeta Z5: solo la recomendación (sin calcular)
        from .. import papers as PAP
        try:
            return _json(h, PAP.receta((q.get("uso") or ["emergencia"])[0], (q.get("red") or ["densa"])[0]))
        except ValueError as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/cmip6/frontera":                                                  # Zeta: versión de frontera (papers) frente al método de referencia (Omega)
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        from .. import papers as PAP
        return _json(h, PAP.comparar_versiones(E.carpeta))
    if ruta in ("/api/cmip6/extremos", "/api/cmip6/extremos.png"):                     # Eta (punto 29i): último análisis de extremos
        if not E.carpeta: return _json(h, {"error": "Abre un proyecto."}, 400)
        from .. import extremos_cmip6 as EXT
        r_ = EXT.ultimo(E.carpeta)
        if ruta.endswith(".png"):
            return _archivo(h, Path(E.carpeta) / r_["figura"]) if r_ else _json(h, {"error": "Sin análisis de extremos."}, 404)
        return _json(h, r_ or {"error": "Todavía no hay análisis de extremos."})
    if ruta in ("/api/cmip6/papers", "/api/cmip6/papers.png"):                         # Zeta: hallazgos de los papers aplicados a CMIP6 (último cálculo)
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        from .. import papers as PAP
        u = PAP.cmip6_hallazgos_ultimo(E.carpeta)
        if not u: return _json(h, {"error": "Aún no se calculan los hallazgos de los papers para CMIP6 (módulo 9 › «CMIP6 experimental» › «Calcular diagnósticos experimentales»)."}, 404)
        if ruta.endswith(".png"): return _archivo(h, Path(E.carpeta) / u["carpeta"] / "infografia_cmip6_papers.png", "image/png")
        return _json(h, u)
    if ruta == "/api/proyecto/estado_ui":                                              # Zeta «modo Word»: dónde se quedó la persona
        if not E.datos: return _json(h, {"proyecto": None})
        return _json(h, {"proyecto": str(E.carpeta), **_estado_ui(E.carpeta)})
    if ruta == "/api/productos/estado":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        raiz = Path(E.carpeta) / "productos"
        return _json(h, {"carpeta": str(raiz), "modulos": sorted(d.name for d in raiz.iterdir() if d.is_dir()) if raiz.exists() else [], "index": str(raiz / "index.html")})
    if ruta == "/api/proyecto/archivo.png":                                       # Epsilon: PNG del proyecto (planta de contaminantes, mapa con referencias)
        rel = (q.get("f") or [""])[0]
        if not E.datos or ".." in rel or not rel.endswith(".png") or not (rel.startswith("registro/contaminantes/") or rel.startswith("resultados/")):
            return _json(h, {"error": "archivo no permitido"}, 400)
        return _archivo(h, Path(E.carpeta) / rel, "image/png")
    if ruta == "/api/validacion/caudal.png":                                      # Epsilon: figura de la validación 1
        run = (q.get("id") or [None])[0]
        if not run or ".." in run or "/" in run or "\\" in run: return _json(h, {"error": "id inválido"}, 400)
        return _archivo(h, E.gestor.base / run / "validacion" / "caudal_obs_vs_2d.png", "image/png")
    if ruta == "/api/corrida/hidrograma.png":                                     # Epsilon E1.4
        run = (q.get("id") or [None])[0]
        if not run or ".." in run or "/" in run or "\\" in run: return _json(h, {"error": "id inválido"}, 400)
        f = next((E.gestor.base / run).rglob("hidrograma_salida.png"), None)
        return _archivo(h, f, "image/png") if f else _json(h, {"error": "Esta corrida no tiene hidrograma en la salida (corrida anterior a Epsilon o sin cuenca activa)."}, 404)
    if ruta == "/api/contaminantes/calcular":                                    # Epsilon: dispersión de contaminantes (no requiere proyecto)
        from .. import contaminantes as CT
        try:
            p = json.loads((q.get("p") or ["{}"])[0]); p = {k_: v for k_, v in p.items() if k_ in ("M_kg", "B", "h", "S", "n", "L_m", "t_h", "metodo", "k_dia", "y0_frac", "x0_m", "umbral_mg_l", "venas", "irregularidad")}
            return _json(h, CT.escenario(**p))
        except (CT.ContaminanteError, TypeError, ValueError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/corrida/mapa.png":
        run = (q.get("id") or [None])[0]; return _archivo(h, E.gestor.base / run / "mapa_hmax.png", "image/png")
    if ruta == "/api/terreno/preview.png":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        png = E.carpeta / "registro" / "terreno_preview.png"; png.parent.mkdir(exist_ok=True)
        _, cfg = E.cfg()
        if not png.exists():
            mapas.render_terreno(cfg, E.carpeta, png, sintetico=E.datos["tipo"] == "sintetico", nota_tipo=f"terreno declarado: {E.datos.get('tipo_terreno', 'desconocido')}")
        return _archivo(h, png, "image/png")
    if ruta == "/api/visor/datos":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            run = (q.get("id") or [None])[0]
            if not run:
                l = [c for c in E.gestor.listar() if c.get("estado") == "completado"]; lx = [c for c in l if "_cc_" not in c["id"]]   # Eta (32b): por defecto la X más reciente (la Y se enciende encima)
                run = (lx or l)[0]["id"] if l else None
            if not run: return _json(h, visor_api.solo_terreno(E))                          # sin corridas: el 3D muestra el terreno registrado
            return _json(h, visor_api.datos(E, run))
        except Exception as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/campo/estado":                                                    # Zeta: validación de campo (reemplaza a la maqueta hipsométrica)
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        from .. import validacion_campo as VC
        return _json(h, VC.estado(E.carpeta))
    if ruta == "/api/campo/conexion":                                                   # hoja de Google conectada (nunca devuelve la clave)
        from .. import validacion_campo as VC
        return _json(h, VC.conexion())
    if ruta in ("/api/campo/encuesta.html", "/api/campo/contraste.png", "/api/campo/lamina.png", "/api/campo/qr.png"):
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        c = (q.get("c") or [""])[0]
        if not c or ".." in c or "/" in c or "\\" in c or not c.startswith(("encuesta_", "contraste_", "laminas_")): return _json(h, {"error": "carpeta inválida"}, 400)
        nombre = {"/api/campo/encuesta.html": "encuesta.html", "/api/campo/contraste.png": "contraste_mapa.png", "/api/campo/qr.png": "qr_encuesta.png"}.get(ruta) or ("lamina2_X_vs_Y_cambio_climatico.png" if (q.get("n") or ["1"])[0] == "2" else "lamina1_consolidado.png")
        f = Path(E.carpeta) / "productos" / "12_validacion_campo" / c / nombre
        return _archivo(h, f, "text/html; charset=utf-8" if ruta.endswith(".html") else "image/png")
    if ruta == "/api/lluvia/auditoria":
        f = RAIZ / "uceclima" / "auditoria" / "M0037_excel_auditoria.json"
        if not f.exists(): return _json(h, {"error": "Aún no hay auditoría. Ejecutar: python -m uceclima.idf_excel"}, 404)
        a = json.loads(f.read_text(encoding="utf-8"))
        return _json(h, {k: a.get(k) for k in ("archivo", "sha256", "atribucion", "serie", "ecuacion_final", "hallazgos", "seleccion_distribucion")} | {"max_dif_recomputo": a["recomputo"]["max_dif_relativa"]})
    if ruta == "/api/lluvia/seleccion":
        d = RAIZ / "uceclima" / "salidas" / "seleccion_eventos_milagro"
        if E.datos and (Path(E.carpeta) / "registro" / "eventos").exists():
            prop = sorted((Path(E.carpeta) / "registro" / "eventos").glob("seleccion_*"))
            if prop: d = prop[-1]
        elif E.datos and not Path(E.carpeta).name.startswith(("milagro", "demo")):
            return _json(h, {"error": "Este proyecto aún no tiene una selección de eventos. Usa «Seleccionar eventos de este proyecto»."}, 404)
        if not (d / "eventos_seleccionados.csv").exists(): return _json(h, {"error": "Sin selección todavía."}, 404)
        import pandas as pd
        s = pd.read_csv(d / "eventos_seleccionados.csv")
        cols = [c for c in ["rol", "evento", "fecha_pico_lluvia", "P_max_dia_mm", "Tr_P_max_dia_anios", "dQ_m3s", "V_directo_hm3", "ventana_chirps_inicio", "ventana_chirps_fin", "ya_usado_en", "advertencia"] if c in s.columns]
        return _json(h, {"eventos": s[cols].fillna("").to_dict("records"), "resumen": json.loads((d / "resumen_seleccion.json").read_text(encoding="utf-8"))})
    if ruta == "/api/cuencas/resumen":
        d = NUCLEO / "preparacion_cuencas"
        if not (E.datos and "milagro" in str(E.datos.get("nombre", "")).lower()):          # estas capas son de Milagro: no se muestran en otro proyecto
            return _json(h, {"error": "Este proyecto no tiene cuencas ni ríos definidos (Mazar aún no tiene polígono de cuenca). Las capas de cuencas del núcleo son de Milagro y solo se muestran en ese proyecto."}, 404)
        if not d.exists(): return _json(h, {"error": "Ejecutar preparar_cuencas.py primero."}, 404)
        import pandas as pd
        corr = pd.read_csv(d / "correspondencias_hms.csv"); cand = pd.read_csv(d / "candidatos_entrada.csv")
        return _json(h, {"correspondencia": corr.estado.value_counts().to_dict(), "areas_no_concuerdan": corr[corr.area_concuerda == False][["nombre_shp", "area_shp_km2", "area_hms_km2", "dif_area_pct"]].round(2).to_dict("records"),
                         "candidatos_entrada": cand[["rio", "x", "y", "borde", "cuencas_en_el_punto", "estado"]].round(1).to_dict("records"),
                         "datos_faltantes": (d / "datos_faltantes.md").read_text(encoding="utf-8")})
    if ruta == "/api/cmip6/compuerta":
        return _json(h, {"bloqueado": False, "razones": [], "anulacion": CMD.decision(E.carpeta) if E.datos else None, "nota": ""})
    if ruta == "/api/config":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        try:
            from .. import configuracion as CFGM
            return _json(h, CFGM.leer(E.carpeta, E.datos, (q.get("modulo") or [""])[0]))
        except Exception as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/terreno/lamina.png":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        try:
            from .. import terreno_lamina as TL
            b = TL.png(E.carpeta, E.datos); h.send_response(200); h.send_header("Content-Type", "image/png"); h.send_header("Content-Length", str(len(b))); h.send_header("Cache-Control", "no-store"); h.end_headers(); h.wfile.write(b); return
        except Exception as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/agente/vscode":
        from . import agente_vscode as AV
        return _json(h, AV.estado(E.carpeta if E.datos else None))
    if ruta == "/api/proyectos/lista":
        from .. import proyecto_sitio as PS
        return _json(h, {"carpeta": str(sitio_api.RAIZ_PROYECTOS), "proyectos": PS.listar(sitio_api.RAIZ_PROYECTOS)})
    if ruta == "/api/proyecto/desactualizadas":
        if not E.datos: return _json(h, {"desactualizadas": None})
        from .. import proyecto_sitio as PS
        return _json(h, {"desactualizadas": PS.desactualizadas(E.carpeta)})
    if ruta == "/api/terreno/historial":
        f = Path(E.carpeta) / "registro" / "terreno_historial.json" if E.datos else None
        return _json(h, {"historial": json.loads(f.read_text(encoding="utf-8"))[::-1] if f and f.exists() else []})
    if ruta == "/api/estaciones/referencia":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        try:
            from .. import estaciones_ref
            lat, lon = IDFX.punto(E.datos)
            return _json(h, estaciones_ref.cercanas(lat, lon))
        except (ValueError, KeyError, OSError) as e: return _json(h, {"error": str(e)[:200]}, 400)
    return _json(h, {"error": "Ruta desconocida"}, 404)


RUTA_ACTIVIDAD = {
    "/api/parametros/propios": ("gee", "Registró CN y Manning propios desde la PC"), "/api/terreno/gee": ("terreno", "Pidió el MDT de Earth Engine como terreno"), "/api/descargas/reanudar": ("gee", "Reanudó una descarga interrumpida"), "/api/config": ("proyecto", "Cambió la configuración de un módulo"), "/api/agente/vscode": ("proyecto", "Conectó el agente de VS Code"), "/api/cmip6/toe": ("cmip6", "Calculó el Time of Emergence"), "/api/proyecto/sitio": ("proyecto", "Cambió el sitio del proyecto"), "/api/proyecto/renombrar": ("proyecto", "Renombró el proyecto"), "/api/wrf/leer": ("wrf", "Leyó salidas WRF"), "/api/wrf/estacion": ("wrf", "Registró la lluvia WRF como estación"), "/api/wrf/preparar": ("wrf", "Preparó una corrida WRF"), "/api/cuenca/shape": ("cuenca", "Cargó el shape de la cuenca"), "/api/cuenca/malla": ("cuenca", "Creó la malla de celdas CHIRPS"), "/api/cuenca/activar": ("cuenca", "Aceptó/activó una cuenca"),
    "/api/calibracion/registrar": ("calibracion", "Registró una serie de caudal observado"), "/api/calibracion/registrar_lluvia": ("calibracion", "Registró lluvia de estación como forzamiento"), "/api/calibracion/usar_lluvia": ("calibracion", "Cambió la lluvia de forzamiento"), "/api/calibracion/eventos": ("calibracion", "Propuso eventos de ajuste y validación"),
    "/api/calibracion/barrido": ("calibracion", "Barrió combinaciones de parámetros"), "/api/calibracion/aceptar": ("calibracion", "Aceptó una combinación de parámetros (decisión de la persona)"),
    "/api/entregas/construir": ("evaluacion", "Armó la carpeta de entrega (resultados, BCA FEMA, El Niño/La Niña)"),
    "/api/idf/x/guardar": ("lluvia", "Fijó la IDF del INAMHI como X del proyecto"), "/api/idf/propia": ("lluvia", "Registró una IDF propia con su fuente como X del proyecto"), "/api/idf/desde_chirps": ("lluvia", "Armó la IDF desde CHIRPS (por defecto, sin estaciones)"),
    "/api/campo/encuesta": ("campo", "Generó la encuesta de validación de campo (HTML)"), "/api/campo/sincronizar": ("campo", "Trajo las respuestas de la comunidad desde la hoja (contraste y láminas)"), "/api/campo/conectar": ("campo", "Conectó la hoja de validación"), "/api/campo/importar": ("campo", "Importó marcas de la comunidad"), "/api/campo/contrastar": ("campo", "Contrastó las marcas con el calado del modelo"), "/api/campo/laminas": ("campo", "Generó las láminas de validación social (consolidado con buffer y X frente a Y)"), "/api/productos/generar": ("entregas", "Ordenó los productos de los módulos (shapes, figuras, CSV, informe)"), "/api/proyecto/guardar_avance": ("proyecto", "Guardó el avance (pantalla y productos)"), "/api/cmip6/papers": ("cmip6", "Aplicó los hallazgos de los papers a CMIP6"), "/api/cmip6/frontera": ("cmip6", "Calculó la versión de frontera de CMIP6 (papers; en evaluación)"), "/api/papers/receta": ("cmip6", "Aplicó la receta de los papers (fuente de lluvia según el uso)"),
    "/api/proyecto/crear": ("proyecto", "Creó la carpeta de un proyecto nuevo"), "/api/descargas/cancelar": ("gee", "Pidió cancelar la descarga en curso"), "/api/gee/autorizar": ("gee", "Inició la autorización de Earth Engine"), "/api/gee/verificar": ("gee", "Verificó la conexión con Earth Engine"), "/api/gee/conectar": ("gee", "Conectó con Earth Engine probando los proyectos disponibles"),
    "/api/prep/leer": ("preparacion", "Leyó archivos de precipitación y caudal"), "/api/prep/a_proyecto": ("preparacion", "Guardó las series del premódulo en el proyecto"),
    "/api/hidrologia/exportar": ("evaluacion", "Exportó tablas y gráficas del panel Hidrología y calibración"),
    "/api/proyecto/abrir": ("proyecto", "Abrió un proyecto"), "/api/proyecto/demo": ("proyecto", "Abrió un proyecto de demostración"), "/api/proyecto/guardar_como": ("proyecto", "Guardó una copia del proyecto"),
    "/api/sitio/nuevo": ("gee", "Creó un proyecto nuevo desde un sitio y lanzó las descargas"), "/api/descargas/iniciar": ("gee", "Lanzó una descarga"), "/api/gee/probar": ("gee", "Probó la conexión con Earth Engine"),
    "/api/eventos/seleccionar": ("lluvia", "Seleccionó eventos con lluvia y caudal"), "/api/estaciones/importar": ("lluvia", "Importó una estación"), "/api/estaciones/vista_previa": ("lluvia", "Revisó un CSV de lluvia"),
    "/api/proyecto/evento": ("lluvia", "Declaró un evento observado como forzamiento"), "/api/terreno/filtrar_picos": ("terreno", "Aplicó el filtro declarado de picos al terreno"), "/api/terreno/quemar_rios": ("terreno", "Grabó los ríos HydroSHEDS en el terreno (profundidad declarada)"), "/api/corrida/cuencas_externas": ("corrida", "Declaró cuencas externas para tormentas de diseño"), "/api/corrida/entradas": ("corrida", "Declaró hidrogramas de entrada en el borde del dominio"), "/api/terreno/inspeccionar": ("terreno", "Inspeccionó un MDT"), "/api/terreno/registrar": ("terreno", "Registró un MDT"),
    "/api/prep/escanear": ("preparacion", "Escaneó una carpeta de datos crudos"), "/api/prep/precipitacion": ("preparacion", "Revisó un archivo de lluvia"), "/api/prep/inventario": ("preparacion", "Revisó un inventario de eventos"),
    "/api/prep/contrastar": ("preparacion", "Contrastó lluvia con el inventario"), "/api/prep/ordenar": ("preparacion", "Ordenó los datos en una carpeta nueva"), "/api/prep/registrar_estacion": ("preparacion", "Registró una estación en el proyecto"),
    "/api/cmip6/asumir_baseline": ("cmip6", "Registró la decisión: línea base asumida"), "/api/bd/sincronizar": ("cmip6", "Sincronizó la base de datos del proyecto"), "/api/bd/consulta": ("cmip6", "Consultó la base de datos"), "/api/cmip6/evaluar": ("cmip6", "Evaluó los modelos CMIP6 (sesgo, RMSE, QQM)"), "/api/cmip6/factores": ("cmip6", "Calculó factores de cambio (QDM)"), "/api/verificar": ("corrida", "Verificó las entradas"), "/api/corrida/iniciar": ("corrida", "Lanzó una corrida"), "/api/corrida/cancelar": ("corrida", "Canceló la corrida"),
    "/api/peligro/generar": ("evaluacion", "Generó los mapas de calado, velocidad y peligro (TIFF, shapefile y PNG)"),
    "/api/pronostico/consultar": ("pronostico", "Consultó un pronóstico de lluvia"), "/api/pronostico/comparar": ("pronostico", "Consultó y comparó pronósticos de lluvia (GFS, ECMWF, NASA IMERG)"),
    "/api/pronostico/usar": ("pronostico", "Declaró un pronóstico como forzamiento (rotulado PRONÓSTICO)"), "/api/pronostico/geoglows": ("pronostico", "Consultó el caudal pronosticado de GEOGLOWS")}


_PROD_CORRIDAS = set()                                                        # corridas cuyos productos ya se ordenaron en esta sesión


def _zona_a_cuenca(carpeta):
    """Zeta Z3: si el proyecto se creó desde un shape de zona de estudio, ese polígono queda como cuenca activa (área 2D, lluvia areal, productos)."""
    E = ESTADO
    z = (E.datos or {}).get("procedencia", {}).get("zona_estudio")
    if not z:
        return None
    try:
        from .. import cuenca as CU
        r = CU.cargar_shape(E.carpeta, E.datos, str(Path(carpeta) / z["copia"]))
        return {**z, "carpeta": r.get("carpeta"), "area_cuenca_km2": r.get("area_km2"), "activa": r.get("activa")}
    except Exception as e:
        return {**z, "error_cuenca": str(e)[:300]}


def _productos_tras(ruta_api, *_):
    """Zeta Z4: tras cada paso que produce algo, se regeneran los productos ordenados del módulo correspondiente (shapes, figuras, CSV, informe)."""
    E = ESTADO
    if not E.datos:
        return None
    try:
        from .. import productos as PROD
        return PROD.tras_ruta(E.carpeta, E.datos, ruta_api)
    except Exception as e:
        try:
            E.log("No se pudieron ordenar los productos del módulo", str(e)[:200], None, "aviso", "interfaz")
        except Exception:
            pass
        return None


def _receta_auto():
    """Zeta: tras los factores CMIP6, receta de los papers con la misma referencia que usó el análisis (estación «est:<id>» o CHIRPS)."""
    E = ESTADO
    if not E.datos:
        return None
    try:
        from .. import papers as PAP
        cars = sorted((Path(E.carpeta) / "registro" / "cmip6").glob("analisis_*"))
        ref = json.loads((cars[-1] / "resumen_analisis.json").read_text(encoding="utf-8")).get("referencia", "") if cars else ""
        est = ref.split(":", 1)[1] if ref.startswith("est:") else None
        r = PAP.ejecutar(E.carpeta, est, "emergencia", "auto")
        E.log("Receta de los papers calculada automáticamente", r.get("carpeta", ""), "cmip6", "ok", "interfaz")
        try:                                                                           # y los hallazgos aplicados a CMIP6 (infografía del módulo 9 y del visor)
            h_ = PAP.cmip6_hallazgos(E.carpeta); E.log("Hallazgos de los papers aplicados a CMIP6", h_.get("carpeta", ""), "cmip6", "ok", "interfaz")
        except Exception as e2:
            E.log("No se pudieron aplicar los hallazgos a CMIP6", str(e2)[:200], "cmip6", "aviso", "interfaz")
        _productos_tras("/api/papers/receta")
        return r
    except Exception as e:
        try:
            E.log("No se pudo calcular la receta de los papers", str(e)[:200], "cmip6", "aviso", "interfaz")
        except Exception:
            pass
        return None


def _hist_terreno(E, fila):
    try:
        f = Path(E.carpeta) / "registro" / "terreno_historial.json"; f.parent.mkdir(exist_ok=True)
        l = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        l.append({"fecha": datetime.now().isoformat(timespec="seconds"), **fila}); f.write_text(json.dumps(l[-200:], ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def api_post(h, ruta, cuerpo):
    E = ESTADO
    if ruta.startswith(("/api/cuenca/", "/api/calibracion/")):
        return cuenca_api.post(h, E, ruta, cuerpo, _json)
    if ruta == "/api/contaminantes/planta":                                      # Epsilon: vista 2 de contaminantes (planta sobre imagen satelital)
        from .. import contaminantes as CT
        if not E.datos: return _json(h, {"error": "Abre un proyecto: la vista en planta usa su MDT."}, 400)
        try:
            p = {k_: v for k_, v in (cuerpo.get("params") or {}).items() if k_ in ("M_kg", "B", "h", "S", "n", "L_m", "t_h", "metodo", "k_dia", "y0_frac", "umbral_mg_l")}
            return _json(h, CT.planta(E.carpeta, float(cuerpo["lon"]), float(cuerpo["lat"]), p, float(cuerpo.get("exagerar_ancho") or 8)))
        except (CT.ContaminanteError, KeyError, TypeError, ValueError, OSError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/mapa/referencias":                                          # Epsilon: mapa con satélite, OSM y exposición
        from .. import mapa_referencias as MR
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        try:
            return _json(h, MR.mapa(E.carpeta, cuerpo.get("id"), bool(cuerpo.get("descargar", True))))
        except (MR.MapaError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/contaminantes/guardar":
        from .. import contaminantes as CT
        if not E.datos: return _json(h, {"error": "Abre un proyecto para guardar el escenario."}, 400)
        try:
            p = {k_: v for k_, v in cuerpo.items() if k_ in ("M_kg", "B", "h", "S", "n", "L_m", "t_h", "metodo", "k_dia", "y0_frac", "x0_m", "umbral_mg_l", "venas", "irregularidad")}
            return _json(h, CT.guardar(E.carpeta, p))
        except (CT.ContaminanteError, TypeError, ValueError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta.startswith("/api/validacion/"):                                          # Epsilon: validación de la 2D con observaciones (1–4)
        from .. import validacion_2d as VAL
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        cp = Path(E.carpeta) / E.datos["config_climanet"]
        try:
            if ruta == "/api/validacion/candidatos": return _json(h, VAL.candidatos(E.carpeta, bool(cuerpo.get("con_s1", True))))
            if ruta == "/api/validacion/preparar":
                if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
                return _json(h, VAL.preparar_evento(E.carpeta, cp, cuerpo["inicio"], cuerpo["fin"], cuerpo.get("res_m") or None, float(cuerpo.get("extra_h") or 12)))
            if ruta == "/api/validacion/restaurar": return _json(h, VAL.restaurar_config(cp))
            if ruta == "/api/validacion/caudal": return _json(h, VAL.comparar_caudal(E.carpeta, cuerpo.get("id")))
            if ruta == "/api/validacion/sentinel1": return _json(h, VAL.mancha_sentinel1(E.carpeta, cuerpo.get("id"), cuerpo["fecha_pico"], int(cuerpo.get("dias_post") or 2)))
            if ruta == "/api/validacion/mancha": return _json(h, VAL.registrar_mancha_externa(E.carpeta, cuerpo["ruta"], cuerpo.get("fuente", ""), cuerpo.get("fecha", ""), cuerpo.get("nombre")))
            if ruta == "/api/validacion/puntos": return _json(h, VAL.registrar_puntos_campo(E.carpeta, cuerpo["ruta"], cuerpo.get("fuente", "")))
            if ruta == "/api/validacion/contrastar": return _json(h, VAL.contrastar(E.carpeta, cuerpo.get("id")))
        except (VAL.ValidacionError, KeyError, ValueError, OSError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
        return _json(h, {"error": "Ruta desconocida."}, 404)
    if ruta.startswith("/api/wrf/") or ruta in ("/api/cmip6/toe", "/api/cmip6/figuras"):
        return wrf_api.post(h, E, ruta, cuerpo, _json)
    if ruta == "/api/proyecto/evento":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            return _json(h, evento_api.usar(E, cuerpo.get("estacion", ""), cuerpo.get("inicio"), cuerpo.get("fin"), cuerpo.get("desagregacion") or None, cuerpo.get("sim_horas") or None, zona=cuerpo.get("zona") or "utc"))
        except (evento_api.EventoUIError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/corrida/cuencas_externas":                                # G23: cuencas externas para tormentas de DISEÑO (el núcleo calcula su hidrograma con la misma IDF y Tr)
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            cp = Path(E.carpeta) / E.datos["config_climanet"]; cfg = json.loads(cp.read_text(encoding="utf-8")); aoi = cfg.get("aoi") or []
            nuevas = []
            for k, c_ in enumerate(cuerpo.get("cuencas") or []):
                d_ = Path(E.carpeta) / "cuenca" / str(c_["cuenca"])
                if not (d_ / "cuenca.gpkg").exists(): raise ValueError(f"No existe la cuenca «{c_['cuenca']}» en el proyecto.")
                cn_, lag_ = float(c_["cn"]), float(c_["lag_h"]); x_, y_ = [float(v) for v in c_["entrada_xy"]]
                if not 30 <= cn_ <= 99 or not 0.05 <= lag_ <= 100: raise ValueError("CN entre 30 y 99 y lag entre 0,05 y 100 h.")
                if len(aoi) == 4 and not (aoi[0] <= x_ <= aoi[1] and aoi[2] <= y_ <= aoi[3]): raise ValueError(f"La entrada de {c_.get('nombre')} queda fuera del área del modelo.")
                nuevas.append({"nombre": str(c_.get("nombre") or f"cuenca_{k + 1}"), "shp": f"cuenca/{c_['cuenca']}/cuenca.gpkg", "cn": cn_, "lag_h": lag_, "prf": float(c_.get("prf", 484)),
                               "entrada_xy": [x_, y_], "fuente": str(c_.get("fuente") or "declarada por la persona")})
            (cp.parent / f"{cp.name}.{datetime.now():%Y%m%d_%H%M%S}.bak").write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            if nuevas: cfg["cuencas_externas"] = nuevas
            else: cfg.pop("cuencas_externas", None)
            cp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            return _json(h, {"cuencas_externas": nuevas, "nota": "Solo para tormentas de diseño: cada cuenca recibe la misma IDF y Tr que la 2D; se usa solo su área fuera del dominio. No calibrado."})
        except (ValueError, KeyError, OSError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/corrida/entradas":                                        # G17: hidrogramas de entrada (Epsilon E1.1) declarados por la persona
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            from climanet.pipeline import leer_hidrograma_entrada
            cp = Path(E.carpeta) / E.datos["config_climanet"]; cfg = json.loads(cp.read_text(encoding="utf-8")); aoi = cfg.get("aoi") or []
            nuevas, resumen = [], []
            for k, e_ in enumerate(cuerpo.get("entradas") or []):
                f_ = Path(str(e_.get("csv") or "")); f_ = f_ if f_.is_absolute() else Path(E.carpeta) / f_
                t_, q_ = leer_hidrograma_entrada({"nombre": e_.get("nombre"), "csv": str(f_)})
                x_, y_ = [float(v) for v in e_["xy"]]
                if len(aoi) == 4 and not (aoi[0] <= x_ <= aoi[1] and aoi[2] <= y_ <= aoi[3]): raise ValueError(f"La entrada {e_.get('nombre')} ({x_:.0f}, {y_:.0f}) queda fuera del área del modelo.")
                nuevas.append({"nombre": str(e_.get("nombre") or f"entrada_{k + 1}"), "csv": str(f_), "xy": [x_, y_], "fuente": str(e_.get("fuente") or "declarada por la persona")})
                resumen.append({"nombre": nuevas[-1]["nombre"], "pico_m3s": round(float(q_.max()), 2), "duracion_h": round(float(t_[-1]) / 3600, 2), "volumen_m3": round(float(sum((t_[1:] - t_[:-1]) * (q_[1:] + q_[:-1]) / 2)), 0)})
            (cp.parent / f"{cp.name}.{datetime.now():%Y%m%d_%H%M%S}.bak").write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            if nuevas: cfg["entradas_hidrograma"] = nuevas
            else: cfg.pop("entradas_hidrograma", None)
            cp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            return _json(h, {"entradas": resumen, "nota": "Hidrogramas declarados (no calibrados). La corrida se alarga hasta el final de cada uno; cada uno entra por su celda."})
        except (ValueError, KeyError, OSError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/proyecto/evento_quitar":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        return _json(h, evento_api.quitar(E))
    if ruta.startswith("/api/prep/"):
        try:
            if ruta == "/api/prep/leer":
                return _json(h, PRE.leer_carpeta(cuerpo["carpeta"]) if cuerpo.get("carpeta") else PRE.leer_varios(cuerpo.get("archivos") or [], cuerpo.get("hoja")))
            if ruta == "/api/prep/lote":
                return _json(h, PRE.iniciar_lote(cuerpo.get("archivos"), cuerpo.get("carpeta"), cuerpo.get("tipo_defecto") or None, cuerpo.get("hoja")))
            if ruta == "/api/prep/confirmar":
                r = PRE.leer(cuerpo.get("ruta", ""), cuerpo.get("hoja"), cuerpo.get("config") or {}); return _json(h, {"resultado": r, "memoria": PRE.memoria()})
            if ruta == "/api/prep/vista_previa": return _json(h, PRE.vista_previa(cuerpo.get("ruta", ""), cuerpo.get("hoja")))
            if ruta == "/api/prep/quitar": return _json(h, PRE.quitar(cuerpo.get("id", "")))
            if ruta == "/api/prep/limpiar": return _json(h, PRE.limpiar())
            if ruta == "/api/prep/a_proyecto":
                if not E.datos: return _json(h, {"error": "Abre o crea un proyecto primero (módulo 1)."}, 400)
                return _json(h, PRE.guardar_en_proyecto(E.carpeta, cuerpo.get("ids") or None))
            if ruta == "/api/prep/escanear": return _json(h, prep_api.escanear(cuerpo))
            if ruta == "/api/prep/precipitacion": return _json(h, prep_api.precipitacion(cuerpo))
            if ruta == "/api/prep/inventario": return _json(h, prep_api.inventario(cuerpo))
            if ruta == "/api/prep/contrastar": return _json(h, prep_api.contrastar(cuerpo))
            if ruta == "/api/prep/ordenar": return _json(h, prep_api.ordenar(E, cuerpo))
            if ruta == "/api/prep/registrar_estacion": return _json(h, prep_api.registrar_estacion(E, cuerpo))
            return _json(h, {"error": "Ruta del premódulo no encontrada"}, 404)
        except (PREP.PrepError, EST.EstacionError, KeyError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:500]}, 400)
    if ruta == "/api/eventos/seleccionar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            P_, nl = AEV.cargar_lluvia(E.carpeta, cuerpo.get("lluvia") or "media_caja_mm")
            Q_, nq = AEV.cargar_caudal(E.carpeta, cuerpo.get("caudal") or "celec")
            otra = "pixel_mm" if (cuerpo.get("lluvia") or "media_caja_mm") == "media_caja_mm" else "media_caja_mm"
            try: extra = {"CHIRPS_" + otra: AEV.cargar_lluvia(E.carpeta, otra)[0]}
            except AEV.AnalisisError: extra = None
            r = AEV.seleccionar(E.carpeta, P_, Q_, f"CHIRPS ({cuerpo.get('lluvia') or 'media_caja_mm'})", nq, int(cuerpo.get("por_bloque") or 2), extra=extra)
            return _json(h, {"carpeta": r["carpeta"], "hidrogramas": r["hidrogramas"], "criterios": r["criterios"], "resumen": r["resumen"], "n": int(len(r["seleccionados"]))})
        except (AEV.AnalisisError, OSError, ValueError, KeyError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/bd/sincronizar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, BD.sincronizar(E.carpeta, cuerpo.get("referencia") or "chirps:celda_nex_mm"))
        except (BD.BDError, OSError, ValueError, KeyError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/bd/consulta":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, BD.consultar(E.carpeta, cuerpo.get("sql", ""), int(cuerpo.get("max_filas") or 5000)))
        except (BD.BDError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/cmip6/asumir_baseline":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        if cuerpo.get("confirmo") is not True: return _json(h, {"error": "Debes confirmar explícitamente (confirmo: true): es una decisión del usuario, no un resultado."}, 400)
        return _json(h, CMD.asumir_baseline(E.carpeta, cuerpo.get("texto")))
    if ruta == "/api/cmip6/evaluar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            r = CSB.evaluar(E.carpeta, cuerpo.get("referencia") or "chirps:celda_nex_mm", int(cuerpo.get("k") or 5))
            return _json(h, {"carpeta": r["carpeta"], "resumen": r["resumen"], "graficas": r["graficas"], "ranking": r["ranking"].replace({float("nan"): None}).to_dict("records")})
        except (CSB.SesgoError, OSError, ValueError, KeyError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/cmip6/factores":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            r = CSB.factores(E.carpeta)
            return _json(h, {"carpeta": r["carpeta"], "nota": r["nota"], "factores": r["factores"].replace({float("nan"): None}).to_dict("records")})
        except (CSB.SesgoError, OSError, ValueError, KeyError, IndexError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/actividad/narrar":
        E.log(str(cuerpo.get("mensaje", ""))[:160] or "(mensaje vacío)", str(cuerpo.get("detalle", "")), cuerpo.get("modulo") or None, cuerpo.get("nivel") if cuerpo.get("nivel") in ("info", "ok", "error", "aviso") else "info", "IA / API")
        return _json(h, {"ok": True, "n": E.seq})
    if ruta in ("/api/gee/autorizar", "/api/gee/codigo", "/api/gee/cancelar", "/api/gee/verificar", "/api/gee/conectar", "/api/gee/proyecto"):
        try:
            if ruta == "/api/gee/autorizar": return _json(h, GEEC.iniciar_autorizacion(cuerpo.get("modo") or "localhost"))
            if ruta == "/api/gee/codigo": return _json(h, GEEC.enviar_codigo(cuerpo.get("codigo")))
            if ruta == "/api/gee/cancelar": return _json(h, GEEC.cancelar())
            if ruta == "/api/gee/conectar": return _json(h, GEEC.conectar())
            if ruta == "/api/gee/verificar": return _json(h, GEEC.verificar(cuerpo.get("proyecto") or None))
            GEEC.guardar_proyecto(cuerpo.get("proyecto")); return _json(h, GEEC.estado())
        except GEEC.GeeError as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/proyecto/crear":
        try:
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            carpeta = sitio_api.crear(cuerpo.get("nombre"), cuerpo.get("lon"), cuerpo.get("lat"), base=cuerpo.get("carpeta_base") or None, shape=cuerpo.get("shape") or None, crs_shape=cuerpo.get("crs_shape") or None)
            punto = json.loads((Path(carpeta) / "proyecto_uceclima.json").read_text(encoding="utf-8"))["procedencia"]["punto"]       # 8.0.1: solo series cercanas al sitio
            guardadas = PRE.guardar_en_proyecto(carpeta, cerca=punto) if cuerpo.get("incluir_memoria", True) and PRE.memoria()["n"] else {"guardadas": [], "carpeta": None}
            pr = E.abrir(str(carpeta)); zona = _zona_a_cuenca(carpeta)
            return _json(h, {"proyecto": pr, "carpeta": str(carpeta), "series_guardadas": len(guardadas["guardadas"]), "series_lejanas": guardadas.get("lejanas", 0),
                             "series_sin_coordenadas": guardadas.get("sin_coordenadas", 0), "radio_km": guardadas.get("radio_km"), "zona_estudio": zona})
        except (DESC.DescargaError, KeyError, ValueError, OSError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/sitio/nuevo":
        try:
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            if E.descargas.activa(): return _json(h, {"error": "Ya hay una descarga en curso."}, 409)
            carpeta = sitio_api.crear(cuerpo.get("nombre"), cuerpo.get("lon"), cuerpo.get("lat"), base=cuerpo.get("carpeta_base") or None, shape=cuerpo.get("shape") or None, crs_shape=cuerpo.get("crs_shape") or None)
            E.abrir(str(carpeta)); zona = _zona_a_cuenca(carpeta)
            lon_, lat_ = E.datos["procedencia"]["punto"]
            params = {"lon": float(lon_), "lat": float(lat_), "inicio": cuerpo.get("inicio") or "1981-01-01", "fin": cuerpo.get("fin") or datetime.now().strftime("%Y-%m-%d"),
                      "medio_km": float(cuerpo.get("medio_km") or (E.datos["procedencia"].get("zona_estudio") or {}).get("medio_km") or 20), "celec": bool(cuerpo.get("celec")), "celec_inicio": cuerpo.get("celec_inicio")}
            if zona and zona.get("carpeta"):
                params["ambito"] = "cuenca"                                           # Zeta Z3: el área 2D sale del shape de la zona de estudio (con 500 m de margen)
            DESC.CONTEXTO["tras_mdt"] = lambda d, p: sitio_api.registrar_mdt_en(E, d, p)
            did = E.descargas.iniciar(carpeta, "sitio", params)
            return _json(h, {"proyecto": str(carpeta), "descarga": did})
        except (DESC.DescargaError, KeyError, ValueError, OSError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/hidrologia/exportar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, HID.exportar(E.carpeta, cuerpo.get("fuente", "corrida"), cuerpo.get("id", "")))
        except (HID.HidroError, KeyError, FileNotFoundError, ValueError, OSError) as e: return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/entregas/construir":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            raiz, man = ENT.construir(E.carpeta, E.datos, ids=cuerpo.get("corridas") or None)
            por = {}
            for a in man["archivos"]: k = a["ruta"].split("/")[0]; por[k] = por.get(k, 0) + 1
            return _json(h, {"carpeta": str(Path(raiz).relative_to(E.carpeta)).replace("\\", "/"), "ruta_completa": str(raiz), "archivos": len(man["archivos"]), "por_carpeta": por, "notas": man["notas"], "corridas": man["corridas"]})
        except (ValueError, KeyError, OSError) as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta in ("/api/campo/conectar", "/api/campo/probar"):                           # conectar la hoja de validación (una vez) y probarla
        try:
            from .. import validacion_campo as VC
            if ruta.endswith("probar"): return _json(h, VC.probar_conexion())
            return _json(h, VC.conectar(cuerpo.get("endpoint"), cuerpo.get("sitio") or None))
        except (ValueError, OSError, KeyError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta in ("/api/campo/encuesta", "/api/campo/importar", "/api/campo/contrastar", "/api/campo/laminas", "/api/campo/sincronizar"):    # Zeta: validación de campo (no corre el modelo)
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            from .. import validacion_campo as VC
            if ruta.endswith("sincronizar"):
                return _json(h, VC.sincronizar(E.carpeta, cuerpo.get("form") or None))
            if ruta.endswith("encuesta"):
                return _json(h, VC.generar_encuesta(E.carpeta, cuerpo.get("ids") or None, cuerpo.get("zona") or None, cuerpo.get("endpoint") or None,
                                                    cuerpo.get("titulo") or None, E.datos.get("nombre"), cuerpo.get("base") or None, cuerpo.get("idioma") or "es"))
            if ruta.endswith("laminas"):
                return _json(h, VC.laminas(E.carpeta, cuerpo.get("corrida") or None, cuerpo.get("zona") or E.datos.get("nombre") or None, float(cuerpo.get("radio_m") or VC.RADIO_BUFFER_M)))
            if ruta.endswith("importar"):
                return _json(h, VC.importar(E.carpeta, str(cuerpo.get("archivo") or "").strip().strip('"')))
            r = VC.contrastar(E.carpeta, cuerpo.get("corrida") or None); r["filas"] = r["filas"][:300]
            return _json(h, r)
        except (ValueError, OSError, KeyError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/cmip6/frontera":                                                  # Zeta: calcula la versión de frontera de CMIP6 (en evaluación; carpeta aparte)
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            from .. import papers as PAP
            PAP.frontera(E.carpeta, cuerpo.get("estacion") or None, cuerpo.get("red") or "auto", int(cuerpo.get("k") or 5))
            return _json(h, PAP.comparar_versiones(E.carpeta))
        except (ValueError, OSError, KeyError, IndexError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/cmip6/extremos":                                                 # Eta (punto 29i): «Analizar extremos» (no cambia Y ni los factores)
        if not E.carpeta: return _json(h, {"error": "Abre un proyecto."}, 400)
        from .. import extremos_cmip6 as EXT
        try:
            r_ = EXT.analizar(E.carpeta, int(cuerpo.get("percentil") or 90))
            E.bitacora("cmip6", "Analizó los extremos CMIP6 (frecuencia de años extremos por década)", r_["carpeta"])
            return _json(h, r_)
        except (EXT.ExtremosError, ValueError, KeyError, OSError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/cmip6/exportar":                                                 # Eta (punto 26b): paquete CMIP6 del territorio en resultados/
        if not E.carpeta: return _json(h, {"error": "Abre un proyecto."}, 400)
        from .. import extremos_cmip6 as EXT
        try:
            r_ = EXT.exportar_paquete(E.carpeta); E.bitacora("cmip6", "Exportó el paquete CMIP6 del territorio", r_["carpeta"]); return _json(h, r_)
        except (OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/cmip6/papers":                                                   # Zeta: calcula los hallazgos de los papers sobre el análisis CMIP6
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            from .. import papers as PAP
            return _json(h, PAP.cmip6_hallazgos(E.carpeta))
        except (ValueError, OSError, KeyError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/papers/receta":                                                  # Zeta Z5: diagnósticos y receta de los papers 1–3 con los datos del proyecto
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            from .. import papers as PAP
            return _json(h, PAP.ejecutar(E.carpeta, cuerpo.get("estacion") or None, cuerpo.get("uso") or "emergencia", cuerpo.get("red") or "auto"))   # sin estación: CHIRPS (por defecto)
        except (ValueError, OSError, KeyError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/proyecto/estado_ui":                                              # Zeta «modo Word»: guarda módulo y campos (autoguardado de la pantalla)
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        return _json(h, _estado_ui(E.carpeta, cuerpo))
    if ruta == "/api/proyecto/guardar_avance":                                         # Zeta «modo Word»: Guardar (Ctrl+S): estado de la pantalla + productos ordenados
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            d = _estado_ui(E.carpeta, {**cuerpo, "guardado": True}); _sesion_guardar(E.carpeta)
            from .. import productos as PROD
            r = PROD.generar(E.carpeta, E.datos)
            return _json(h, {"guardado": d.get("ultimo_guardado"), "ruta": d.get("ruta"), "modulos_productos": len(r), "carpeta": str(E.carpeta)})
        except (OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta in ("/api/pronostico/consultar", "/api/pronostico/comparar", "/api/pronostico/usar", "/api/pronostico/geoglows"):    # Lambda 7b: pronóstico de lluvia (GFS, ECMWF, NASA IMERG) y caudal GEOGLOWS
        from .. import pronostico as PRO
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if ruta == "/api/pronostico/usar":
                if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
                return _json(h, PRO.usar(E, cuerpo.get("id", ""), cuerpo.get("horas") or 72, bool(cuerpo.get("permitir_poca_lluvia"))))
            if ruta == "/api/pronostico/geoglows":
                return _json(h, PRO.geoglows_forecast(E.carpeta, cuerpo.get("river_id"), cuerpo.get("horas") or 96))
            kw = dict(lon=cuerpo.get("lon"), lat=cuerpo.get("lat"), dias=cuerpo.get("dias") or 5, muestreo=cuerpo.get("muestreo") or "area", zona=cuerpo.get("zona") or None)
            if ruta == "/api/pronostico/consultar":
                return _json(h, PRO.consultar(E.carpeta, E.datos, cuerpo.get("modelo", ""), **kw))
            return _json(h, PRO.comparar(E.carpeta, E.datos, tuple(cuerpo.get("modelos") or ("gfs", "ecmwf")), **kw))
        except (PRO.PronosticoError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/peligro/generar":                                                # Lambda: mapas de calado, velocidad y peligro de una corrida (TIFF, shapefile y PNG)
        from .. import peligro as PEL
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            return _json(h, PEL.generar(E.carpeta, cuerpo.get("id") or None, cuerpo.get("zoom") or None))
        except (PEL.PeligroError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/productos/generar":                                              # Zeta Z4: ordenar ahora todos los productos del proyecto
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            from .. import productos as PROD
            r = PROD.generar(E.carpeta, E.datos, cuerpo.get("modulos") or None)
            return _json(h, {"modulos": r, "carpeta": str(Path(E.carpeta) / "productos"), "index": str(Path(E.carpeta) / "productos" / "index.html")})
        except (OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/idf/desde_chirps":                                               # Zeta: IDF por defecto en cualquier lugar del mundo (sin IDF oficial ni estaciones)
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, ESC.idf_desde_chirps(E.carpeta, cuerpo.get("columna") or None))
        except (ESC.EscenarioError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/idf/propia":                                                     # Zeta: IDF propia con fuente (p. ej. Norma 5.2-IC en España)
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            info = ESC.registrar_idf_propia(E.carpeta, cuerpo.get("archivo", ""), cuerpo.get("fuente", ""), cuerpo.get("nombre", ""), cuerpo.get("estacion") or None)
            return _json(h, info)
        except (ESC.EscenarioError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/idf/x/guardar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            est = cuerpo.get("estacion") or None; modo = cuerpo.get("modo") or "auto"
            fijada = IDFX.fijar_en_proyecto(E, est, modo)
            res, car, files = IDFX.guardar(E.carpeta, E.datos, fijada["estacion"], int(cuerpo.get("duracion_min") or 180), int(cuerpo.get("tr") or 100))
            return _json(h, {"fijada": fijada, "carpeta": str(Path(car).relative_to(E.carpeta)).replace("\\", "/"), "archivos": files, "referencia": res["referencia"]})
        except (ValueError, KeyError, IndexError, OSError) as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/proyecto/sitio":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            from .. import proyecto_sitio as PS
            r = PS.cambiar_sitio(E.carpeta, E.datos, cuerpo.get("lon"), cuerpo.get("lat"), bool(cuerpo.get("centrar_cuenca"))); E.abrir(str(E.carpeta)); return _json(h, r)
        except (ValueError, KeyError, OSError) as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/proyecto/renombrar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if (E.gestor and E.gestor.activa()) or E.descargas.activa(): return _json(h, {"error": "Hay una corrida o descarga en curso; espera a que termine."}, 409)
            from .. import proyecto_sitio as PS
            r = PS.renombrar(E.carpeta, E.datos, cuerpo.get("nombre")); E.abrir(r["carpeta"]); return _json(h, r)
        except (ValueError, KeyError, OSError) as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/terreno/gee":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            prod = cuerpo.get("producto") or "glo30"                                 # Omega O1: «glo30» (DSM) o «fabdem» (suelo desnudo)
            if (cuerpo.get("ambito") or "sitio") == "sitio" and prod == "glo30":
                usado = sitio_api.registrar_mdt_descargado(E)
                if usado: return _json(h, {"registrado": usado, "mensaje": f"MDT de Earth Engine ya descargado ({usado}) registrado como terreno del proyecto."})
                _, cfg = E.cfg()
                if cfg.get("dem") and cfg.get("aoi"): return _json(h, {"registrado": None, "mensaje": "El proyecto ya tiene un terreno registrado."})
            import re as _re
            m = _re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(E.datos.get("ubicacion", "")))
            if not m: return _json(h, {"error": "El proyecto no tiene punto de sitio (lon, lat)."}, 400)
            DESC.CONTEXTO["tras_mdt"] = None
            did = E.descargas.iniciar(E.carpeta, "mdt", {"lon": float(m.group(1)), "lat": float(m.group(2)), "medio_km": float(cuerpo.get("medio_km") or 20), "ambito": cuerpo.get("ambito") or "sitio", "producto": prod}, al_terminar=sitio_api.registrar_mdt(E))
            return _json(h, {"descarga": did, "mensaje": "Descargando el MDT de Earth Engine; se registra solo al terminar."})
        except (DESC.DescargaError, ValueError, KeyError, OSError) as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/parametros/propios":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            from .. import parametros_propios as PP
            return _json(h, PP.registrar(E.carpeta, E.datos, cuerpo.get("cn", ""), cuerpo.get("manning", ""), cuerpo.get("fuente", ""), cuerpo.get("persona", "")))
        except (ValueError, KeyError, OSError) as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/descargas/reanudar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, {"descarga": DESC.reanudar(E.descargas, E.carpeta, cuerpo.get("id", ""))})
        except DESC.DescargaError as e: return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/config":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            from .. import configuracion as CFGM
            return _json(h, CFGM.guardar(E.carpeta, E.datos, cuerpo.get("modulo", ""), cuerpo.get("valores") or {}))
        except Exception as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/agente/vscode":
        try:
            from . import agente_vscode as AV
            return _json(h, AV.conectar(E.carpeta if E.datos else None, agente=cuerpo.get("agente") or "ambos"))
        except Exception as e: return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/descargas/cancelar":
        return _json(h, {"cancelada": bool(E.descargas.cancelar())})
    if ruta == "/api/descargas/iniciar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            fuente = cuerpo.get("fuente", "")
            if fuente == "mdt": DESC.CONTEXTO["tras_mdt"] = None
            if fuente in ("suelo", "cn_manning"):                                    # el MDT ya está en la carpeta pero sin registrar: se registra solo
                try:
                    usado = sitio_api.registrar_mdt_descargado(E)
                    if usado: E.log("Registró el MDT ya descargado", usado, "gee", "ok", "interfaz", True)
                except Exception as ex:
                    return _json(h, {"error": "Hay un MDT descargado pero no se pudo registrar: " + str(ex)[:250] + " · Puedes registrarlo a mano en el módulo 5 · Terreno."}, 400)
            return _json(h, {"descarga": E.descargas.iniciar(E.carpeta, fuente, cuerpo.get("parametros") or {}, al_terminar=(sitio_api.registrar_mdt(E) if fuente == "mdt" else None))})
        except DESC.DescargaError as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/ia/instalar":
        try:
            return _json(h, ia_config.instalar(cuerpo.get("destino", ""), cuerpo.get("carpeta") or None))
        except (ia_config.IAConfigError, OSError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/ia/clave":
        return _json(h, {"clave": E.clave_api, "archivo": str(api_abierta.ARCHIVO_CLAVE)})
    if ruta == "/api/estaciones/vista_previa":
        try:
            return _json(h, EST.vista_previa(cuerpo.get("archivo", "")))
        except (EST.EstacionError, OSError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/estaciones/importar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, EST.importar(E.carpeta, E.datos["crs"], cuerpo.get("archivo", ""), cuerpo))
        except (EST.EstacionError, OSError) as e:
            return _json(h, {"error": str(e)[:400]}, 400)
    if ruta == "/api/estaciones/hietograma":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            return _json(h, EST.hietograma(E.carpeta, cuerpo.get("id", ""), cuerpo.get("inicio"), cuerpo.get("fin")))
        except (EST.EstacionError, OSError, ValueError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/terreno/inspeccionar":
        try:
            r = TIMP.inspeccionar(cuerpo.get("archivo", ""))
            try: r["sugerencia"] = TIMP.sugerencia(r)                                   # Epsilon E1.5
            except Exception: pass
            if E.datos:
                try: r["coincidencia"] = TIMP.coincidencia(r, E)
                except Exception as ex: r["coincidencia"] = {"veredicto": "error", "mensaje": "No se pudo comparar con la zona de trabajo: " + str(ex)[:160], "pistas": []}
            return _json(h, r)
        except TIMP.TerrenoError as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/terreno/quemar_rios":                                     # Omega O7: graba la red HydroSHEDS del proyecto en el MDT con profundidad declarada
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            _, cfg = E.cfg(); dem = cfg.get("dem")
            if not dem: return _json(h, {"error": "El proyecto no tiene terreno registrado."}, 400)
            fr = sorted((Path(E.carpeta) / "datos_descargados").glob("rios_merge_*/rios_merge.gpkg")) or sorted((Path(E.carpeta) / "datos_descargados").glob("rios_*/rios_hydrosheds.gpkg"))   # O9: merge si existe
            if not fr: return _json(h, {"error": "Primero descarga la red de ríos HydroSHEDS (hidro › Cuenca)."}, 400)
            dem = cuerpo.get("mdt") or dem                                      # se puede partir de otro MDT del proyecto (p. ej. el FABDEM sin quemar)
            dem = dem if Path(dem).is_absolute() else str(Path(E.carpeta) / dem)
            if "_rios" in Path(dem).stem: return _json(h, {"error": "Ese terreno ya tiene ríos quemados: indica el MDT de origen (campo «mdt»)."}, 400)
            inf = TIMP.quemar_rios(dem, fr[-1], cuerpo.get("profundidad_m", 2.0), cuerpo.get("ancho_celdas", 1), cuerpo.get("area_min_km2", 10.0))
            d = E.datos; r = TIMP.registrar(E, inf["salida"], d.get("tipo_terreno", "MDT"), d.get("datum_vertical", ""), float(cfg.get("res", 30)), cfg.get("aoi"))
            _hist_terreno(E, {"resultado": "rios_quemados", "archivo": inf["salida"], "aoi": r.get("aoi"), "res_m": r.get("res_modelo_m"), "quema": {k: inf[k] for k in ("profundidad_m", "ancho_celdas", "celdas_quemadas")}})
            return _json(h, {"quema": inf, "registro": r})
        except (TIMP.TerrenoError, ValueError, OSError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/terreno/filtrar_picos":                                   # Omega O2: filtro declarado; crea un MDT nuevo y lo registra (copia .bak de la configuración)
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            _, cfg = E.cfg(); dem = cfg.get("dem")
            if not dem: return _json(h, {"error": "El proyecto no tiene terreno registrado."}, 400)
            dem = dem if Path(dem).is_absolute() else str(Path(E.carpeta) / dem)
            inf = TIMP.filtrar_picos(dem, cuerpo.get("umbral_m", 3.0), cuerpo.get("ventana", 5))
            d = E.datos; aoi = cfg.get("aoi"); res = float(cfg.get("res", 30))
            r = TIMP.registrar(E, inf["salida"], d.get("tipo_terreno", "DSM"), d.get("datum_vertical", ""), res, aoi)
            _hist_terreno(E, {"resultado": "filtro_picos", "archivo": inf["salida"], "aoi": r.get("aoi"), "res_m": r.get("res_modelo_m"), "filtro": {k: inf[k] for k in ("umbral_m", "ventana_celdas", "celdas_corregidas")}})
            return _json(h, {"filtro": inf, "registro": r})
        except (TIMP.TerrenoError, ValueError, OSError) as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    if ruta == "/api/terreno/registrar":
        try:
            if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
            if E.gestor and E.gestor.activa(): return _json(h, {"error": "Hay una corrida en curso; espera a que termine."}, 409)
            r = TIMP.registrar(E, cuerpo.get("archivo", ""), cuerpo.get("tipo_terreno", "desconocido"), cuerpo.get("datum", ""), cuerpo.get("res", 10), cuerpo.get("aoi"))
            _hist_terreno(E, {"resultado": "registrado", "archivo": cuerpo.get("archivo", ""), "aoi": r.get("aoi"), "res_m": r.get("res_modelo_m")}); return _json(h, r)
        except TIMP.TerrenoError as e:
            _hist_terreno(E, {"resultado": "error", "archivo": cuerpo.get("archivo", ""), "mensaje": str(e)[:300]})
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/dialogo":
        d = _dialogo(cuerpo.get("tipo", "archivo"))
        return _json(h, {"rutas": d} if isinstance(d, list) else {"ruta": d})
    if ruta == "/api/proyecto/abrir":
        try:
            d = E.abrir(cuerpo["ruta"]); return _json(h, {"proyecto": d})
        except (P.ProyectoError, KeyError) as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/proyecto/demo":
        try:
            if cuerpo.get("id") == "mazar":
                carpeta = demo.RAIZ / "mazar"
                if not (carpeta / P.ARCHIVO).exists(): return _json(h, {"error": "El proyecto Mazar de demostración no está en esta instalación."}, 404)
            else:
                carpeta = demo.crear_sintetico() if cuerpo.get("id") == "sintetico" else demo.crear_milagro_pequeno()
            return _json(h, {"proyecto": E.abrir(carpeta)})
        except Exception as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/proyecto/guardar_como":
        if not E.datos: return _json(h, {"error": "No hay proyecto abierto."}, 400)
        try:
            destino = Path(cuerpo["carpeta"])
            if (destino / P.ARCHIVO).exists() and not cuerpo.get("sobrescribir"):
                return _json(h, {"error": f"Ya existe un proyecto en {destino}. No se sobrescribe sin confirmación explícita."}, 409)
            import shutil
            d = {k: v for k, v in E.datos.items() if not k.startswith("_")}; d["nombre"] = cuerpo.get("nombre") or d["nombre"]
            destino.mkdir(parents=True, exist_ok=True)
            cp, _ = E.cfg(); shutil.copy2(cp, destino / "config_climanet.json"); d["config_climanet"] = "config_climanet.json"
            origen = E.carpeta / "datos"
            if origen.is_dir() and not (destino / "datos").exists(): shutil.copytree(origen, destino / "datos")
            d["procedencia"] = {**d["procedencia"], "notas": d["procedencia"].get("notas", []) + [f"Guardado como copia el {datetime.now():%Y-%m-%d %H:%M} desde {E.carpeta}"]}
            P.guardar(d, destino, sobrescribir=bool(cuerpo.get("sobrescribir")))
            return _json(h, {"guardado": str(destino)})
        except (P.ProyectoError, KeyError) as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/verificar":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        return _json(h, P.verificar(E.datos, E.carpeta))
    if ruta == "/api/corrida/iniciar":
        if not E.datos: return _json(h, {"error": "Abre un proyecto."}, 400)
        v = P.verificar(E.datos, E.carpeta)
        if not v["puede_ejecutar"]:
            return _json(h, {"error": "La comprobación previa tiene errores; no se ejecuta.", "chequeos": [c for c in v["chequeos"] if c["estado"] == "error"]}, 422)
        _, cfg = E.cfg()
        if cfg.get("cn_fuente") == "calibrado":                                       # C19: CN calibrado en hidro, uniforme, declarado
            acc = sorted((Path(E.carpeta) / "calibracion" / "aceptadas").glob("aceptada_*"))
            if not acc: return _json(h, {"error": "Elegiste «CN calibrado» para la 2D pero no hay ninguna calibración aceptada en hidro."}, 400)
            comb = json.loads((acc[-1] / "aceptacion.json").read_text(encoding="utf-8"))["combinacion"]
            lam = float(comb.get("lambda", 0.2))                                       # el λ calibrado viaja con el CN (Gamma)
            cn_c = float(comb["CN"]); amc = cfg.get("cn_amc_2d") or "ninguna"; nota_amc = ""
            if amc in ("I", "III", "auto"):                                          # Epsilon: humedad antecedente DECLARADA (NEH-4; Chow et al. 1988)
                from .. import calibracion as K
                clase = amc
                if amc == "auto":
                    ev_ = cfg.get("evento_observado") or {}
                    try:
                        import pandas as _pd
                        p_, _ = K.lluvia_cuenca(E.carpeta); t0_ = _pd.Timestamp(_pd.read_csv(ev_["hietograma_csv"])["fecha"].iloc[0]).tz_localize(None)
                        p5 = float(p_[t0_ - _pd.Timedelta(days=5):t0_ - _pd.Timedelta(days=1)].sum())
                        clase = "I" if p5 < K.AMC_UMBRALES_MM[0] else ("III" if p5 > K.AMC_UMBRALES_MM[1] else "II"); nota_amc = f", lluvia de 5 días previos {p5:.1f} mm"
                    except Exception:
                        clase = "II"; nota_amc = ", sin lluvia antecedente disponible (AMC II)"
                cn_c = K.cn_amc(cn_c, clase) if clase in ("I", "III") else cn_c; nota_amc = f" → AMC {clase} declarada{nota_amc}: CN {cn_c:.1f}"
            cfg = {**{k: v for k, v in cfg.items() if k != "cn_tif"}, "cn_default": cn_c, "ia_ratio": lam,
                   "cn_origen": f"calibrado en hidro ({acc[-1].name}): CN {float(comb['CN']):g}, λ {lam:g}{nota_amc}"}
        elif cfg.get("cn_tif") and (cfg.get("cn_amc_2d") or "ninguna") in ("I", "III", "auto"):   # G20: humedad antecedente declarada también para el CN ráster (NEH-4)
            from .. import calibracion as K
            clase, nota_amc = cfg["cn_amc_2d"], ""
            if clase == "auto":
                ev_ = cfg.get("evento_observado") or {}
                try:
                    import pandas as _pd
                    t0_ = _pd.Timestamp(_pd.read_csv(Path(E.carpeta) / ev_["hietograma_csv"] if not Path(ev_["hietograma_csv"]).is_absolute() else ev_["hietograma_csv"])["fecha"].iloc[0])
                    t0_ = t0_.tz_convert("UTC") if t0_.tzinfo else t0_.tz_localize("UTC")
                    if ev_.get("estacion"):
                        s_ = EST.serie(E.carpeta, ev_["estacion"], str((t0_ - _pd.Timedelta(days=5)).tz_localize(None)), str((t0_ - _pd.Timedelta(minutes=1)).tz_localize(None)))
                        p5, n_ = float(s_["lluvia_mm"].sum()), int(s_["lluvia_mm"].notna().sum()); fuente_ = f"estación {ev_['estacion']} ({n_} registros)"
                    else:
                        p_, _ = K.lluvia_cuenca(E.carpeta); t1_ = t0_.tz_localize(None); p5 = float(p_[t1_ - _pd.Timedelta(days=5):t1_ - _pd.Timedelta(days=1)].sum()); fuente_ = "lluvia de la cuenca"
                    clase = "I" if p5 < K.AMC_UMBRALES_MM[0] else ("III" if p5 > K.AMC_UMBRALES_MM[1] else "II"); nota_amc = f", lluvia de 5 días previos {p5:.1f} mm ({fuente_})"
                except Exception:
                    clase = "II"; nota_amc = ", sin lluvia antecedente disponible (AMC II)"
            cfg = {**cfg, "cn_amc": clase, "cn_origen": f"{cfg.get('cn_origen', 'ráster')} · humedad antecedente AMC {clase} declarada (NEH-4){nota_amc}"}
        if cfg.get("cn_2d_declarado"):                                              # Epsilon: CN DISCRECIONAL declarado por la persona (prueba de estrés), nunca por defecto
            cnd = float(cfg["cn_2d_declarado"])
            if not 30 <= cnd <= 99: return _json(h, {"error": "El CN declarado debe estar entre 30 y 99."}, 400)
            cfg = {**{k: v for k, v in cfg.items() if k != "cn_tif"}, "cn_default": cnd, "ia_ratio": float(cfg.get("ia_ratio", 0.05) if cfg.get("cn_fuente") == "calibrado" else cfg.get("ia_ratio", 0.2)),
                   "cn_origen": f"CN {cnd:g} DECLARADO por la persona (valor discrecional de prueba de estrés, no calibrado)"}
        try:                                                                        # Epsilon E1.4: sección en la salida de la cuenca activa y comparación con hidro
            act = Path(E.carpeta) / "cuenca" / "activa.json"
            if act.exists() and not cfg.get("salida_xy"):
                a_ = json.loads(act.read_text(encoding="utf-8")); rj = json.loads((Path(E.carpeta) / a_["carpeta"] / "resumen.json").read_text(encoding="utf-8"))
                ll = rj.get("salida_ajustada_lonlat") or rj.get("salida_pedida_lonlat")
                if ll:
                    from pyproj import Transformer
                    x_, y_ = Transformer.from_crs("EPSG:4326", E.datos["crs"], always_xy=True).transform(float(ll[0]), float(ll[1]))
                    ao_ = cfg.get("aoi") or []; m_ = 2 * float(cfg.get("res", 10))               # G19: salida fuera del área de cálculo → no se pide la sección (antes la corrida fallaba al arrancar)
                    if len(ao_) == 4 and not (ao_[0] + m_ <= x_ <= ao_[1] - m_ and ao_[2] + m_ <= y_ <= ao_[3] - m_):
                        E.log("Salida de la cuenca activa fuera del área de cálculo: no se calcula el hidrograma 2D en la salida", f"({x_:.0f}, {y_:.0f})", "corrida", "aviso", "interfaz", True)
                    else:
                        cfg = {**cfg, "salida_xy": [x_, y_]}
                acc_ = sorted((Path(E.carpeta) / "calibracion" / "aceptadas").glob("aceptada_*"))
                if acc_ and a_.get("area_km2"):
                    cb = json.loads((acc_[-1] / "aceptacion.json").read_text(encoding="utf-8"))["combinacion"]
                    cfg = {**cfg, "hidro_comparar": {"CN": float(cb["CN"]), "lambda": float(cb.get("lambda", 0.2)), "lag_h": float(cb["lag_h"]), "PRF": float(cb.get("PRF", 484)), "area_km2": float(a_["area_km2"])}}
        except Exception:
            pass
        esc = None; etiqueta = "sintetica" if E.datos["tipo"] == "sintetico" else "real"
        if cuerpo.get("tr") not in (None, ""):                                      # Eta (punto 31a): selector de Tr, una corrida por Tr (100 por defecto)
            try:
                tr_ = int(cuerpo["tr"])
            except (TypeError, ValueError):
                return _json(h, {"error": "Tr debe ser un número entero de años."}, 400)
            if tr_ not in TR_PERMITIDOS: return _json(h, {"error": f"Tr {tr_} no está en las tablas del INAMHI: elige {', '.join(map(str, TR_PERMITIDOS))}."}, 400)
            cfg = {**cfg, "Tr": tr_}
        tr_corrida = int(cfg.get("Tr", 100))
        if tr_corrida != 100: etiqueta = f"{etiqueta}_tr{tr_corrida}"
        if cuerpo.get("escenario"):
            try:
                parche, esc = ESC.preparar(E.carpeta, cfg, cuerpo["escenario"], cuerpo.get("estacion") or IDFX.estacion_proyecto(cfg, E.datos))
                cfg = {**cfg, **{k: v_ for k, v_ in parche.items() if v_ is not None}}
                for k, v_ in parche.items():
                    if v_ is None: cfg.pop(k, None)
                if parche.get("idf_csv"): cfg["idf_csv"] = str((Path(E.carpeta) / parche["idf_csv"]).resolve())
                etiqueta = f"{etiqueta}_{esc['id']}"
                if esc.get("tipo") == "cmip6":                                          # Eta (punto 30): la decisión general (13/14-oct) queda escrita en cada proyecto
                    try: CMD.asumir_baseline(E.carpeta, CMD.TEXTO_DECISION + " Registrada en este proyecto al correr el primer escenario Y (UCEclima Lambda).")
                    except Exception: pass
            except ESC.EscenarioError as e:
                return _json(h, {"error": str(e)}, 400)
        if esc is None and not cfg.get("evento_observado"):                          # Eta (punto 32a): la X también lleva su nombre de escenario (visor 3D, láminas, entregas)
            esc = {"id": "x_existente", "nombre": "X · condiciones existentes", "tipo": "x"}
        if esc is not None:
            fac_ = (esc.get("factor_aplicado_por_tr") or {}).get(str(tr_corrida), esc.get("factor"))
            cfg = {**cfg, "escenario_info": {"id": esc.get("id"), "nombre": esc.get("nombre"), "tipo": esc.get("tipo"), "factor": fac_}}
        try:
            rid = E.gestor.iniciar(cfg, E.datos["nombre"], E.datos["tipo"], E.carpeta, etiqueta=etiqueta, escenario=esc)
            return _json(h, {"id": rid, "escenario": esc})
        except RuntimeError as e:
            return _json(h, {"error": str(e)}, 409)
    if ruta == "/api/corrida/reanudar":                                          # Eta (Mejora 1): seguir una corrida interrumpida desde su último punto de control
        if not E.gestor: return _json(h, {"error": "Abre un proyecto."}, 400)
        try:
            rid = E.gestor.reanudar(str(cuerpo.get("id") or ""))
            E.bitacora("corrida", "Reanudó la corrida desde el último punto de control", rid)
            return _json(h, {"id": rid, "reanudada": True})
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            return _json(h, {"error": str(e)}, 409)
    if ruta == "/api/corrida/cancelar":
        return _json(h, {"cancelada": bool(E.gestor and E.gestor.cancelar())})
    if ruta == "/api/gee/probar":
        from uceclima import gee_chirps
        est, ee = gee_chirps.iniciar(cuerpo.get("proyecto") or None)
        est["mensaje"] = ("Conexión correcta con Earth Engine (credenciales ya autorizadas en este equipo)." if est["autenticado"] else
                          "Sin acceso a Earth Engine. Autorizar una vez con «earthengine authenticate» en una terminal y, si procede, indicar el proyecto Cloud. La interfaz nunca guarda ni muestra tokens.")
        cache = RAIZ / "uceclima" / "cache" / "chirps"
        est["cache_local"] = [str(p.relative_to(RAIZ)) for p in cache.glob("*/*")] if cache.exists() else []
        return _json(h, est)
    if ruta == "/api/chirps/plan":
        from uceclima.eventos import Evento
        try:
            ev = Evento(cuerpo.get("nombre") or "evento", f"{cuerpo['inicio']}T00:00:00-05:00", f"{cuerpo['fin']}T00:00:00-05:00", cuerpo.get("estacion") or "CUMBE")
            return _json(h, ev.plan())
        except Exception as e:
            return _json(h, {"error": str(e)}, 400)
    if ruta == "/api/chirps/cobertura":
        from uceclima import gee_chirps
        from uceclima.eventos import Evento
        try:
            ev = Evento("evento", f"{cuerpo['inicio']}T00:00:00-05:00", f"{cuerpo['fin']}T00:00:00-05:00", "CUMBE"); plan = ev.plan()
            if (datetime.fromisoformat(cuerpo["fin"]) - datetime.fromisoformat(cuerpo["inicio"])).days > 30:
                return _json(h, {"error": "La interfaz limita el evento a 30 días (consultas pequeñas)."}, 400)
            est, ee = gee_chirps.iniciar()
            if ee is None: return _json(h, {"error": "Sin acceso a Earth Engine: " + str(est['error'])[:200], "plan": plan}, 503)
            sel = gee_chirps.seleccionar(plan, gee_chirps.disponibilidad(plan, ee))
            return _json(h, {"plan": plan, "seleccion": {k: sel.get(k) for k in ("version", "coleccion", "cobertura_completa", "fallback", "estado")},
                             "dias_faltantes": {k: v["dias_faltantes"][:10] for k, v in sel["diagnostico"].items()}})
        except Exception as e:
            return _json(h, {"error": str(e)[:300]}, 400)
    return _json(h, {"error": "Ruta desconocida"}, 404)


class Manejador(BaseHTTPRequestHandler):
    server_version = "UCEclima/0.1"

    def log_message(self, fmt, *a):                       # silencio: el registro de corrida es el persistente
        pass

    def send_response(self, code, message=None):
        self._codigo = code
        super().send_response(code, message)

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._host_ok(): return _json(self, {"error": "Host no permitido"}, 403)
        u = urlparse(self.path); ruta = u.path; q = parse_qs(u.query)
        if ruta.startswith("/api/"):
            _LATIDO[0] = time.time()                       # G21: la actividad por la API (agente o script) también mantiene vivo el servidor
        try:
            if ruta.startswith("/api/"):
                return api_get(self, ruta, q)
            if ruta in ("/", "/index.html"):
                html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", ESTADO.token)
                b = html.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store"); self.end_headers(); return self.wfile.write(b)
            if ruta.startswith("/static/"):
                f = (STATIC / ruta[len("/static/"):]).resolve()
                if STATIC.resolve() not in f.parents: return _json(self, {"error": "No permitido"}, 403)
                return _archivo(self, f)
            if ruta == "/visor":
                return _archivo(self, STATIC / "visor.html", "text/html; charset=utf-8")
            if ruta == "/contaminantes":                          # Epsilon: maqueta de dispersión de contaminantes (base)
                html = (STATIC / "contaminantes.html").read_text(encoding="utf-8").replace("</head>", f'<script>window.TOKEN="{ESTADO.token}";</script></head>')
                b = html.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store"); self.end_headers(); return self.wfile.write(b)
            if ruta == "/visual/index.html":                      # maqueta 4D SINTÉTICA de Codex
                return _archivo(self, NUCLEO / "visual" / "index.html", "text/html; charset=utf-8")
            if ruta == "/visual/base_milagro.jpg":
                return _archivo(self, NUCLEO / "visual" / "base_milagro.jpg")
            return _json(self, {"error": "No encontrado"}, 404)
        except Exception:
            return _json(self, {"error": "Error interno", "detalle": traceback.format_exc()[-600:]}, 500)

    def do_POST(self):
        if not self._host_ok(): return _json(self, {"error": "Host no permitido"}, 403)
        if self.headers.get("X-UCECLIMA-TOKEN") != ESTADO.token and not api_abierta.clave_valida(ESTADO.clave_api, self.headers.get("Authorization")):
            return _json(self, {"error": "Falta la clave de API (Authorization: Bearer <clave>) o el token de sesión"}, 403)
        _LATIDO[0] = time.time()                           # G21: una acción autenticada cuenta como señal de vida
        n = int(self.headers.get("Content-Length") or 0)
        try:
            cuerpo = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except json.JSONDecodeError:
            return _json(self, {"error": "JSON inválido"}, 400)
        ruta_p = urlparse(self.path).path
        origen = "IA / API" if api_abierta.clave_valida(ESTADO.clave_api, self.headers.get("Authorization")) else "interfaz"
        self._codigo = 200
        try:
            return api_post(self, ruta_p, cuerpo)
        except Exception:
            return _json(self, {"error": "Error interno", "detalle": traceback.format_exc()[-600:]}, 500)
        finally:
            info = RUTA_ACTIVIDAD.get(ruta_p)
            ok = getattr(self, "_codigo", 200) < 400
            if info:
                ESTADO.log(info[1] + ("" if ok else " (con error)"), ruta_p, info[0], "info" if ok else "error", origen, ok)
            try:                                                                     # Zeta Z4: productos ordenados del módulo, en segundo plano (no demora la respuesta)
                from .. import productos as _PR
                if ok and ruta_p in _PR.RUTAS:
                    threading.Thread(target=_productos_tras, args=(ruta_p,), daemon=True).start()
                if ok and ruta_p == "/api/cmip6/factores":                            # Zeta: la receta de los papers se calcula sola (CHIRPS por defecto, o la estación de referencia del análisis)
                    threading.Thread(target=_receta_auto, daemon=True).start()
            except Exception:
                pass


class _ServidorExclusivo(ThreadingHTTPServer):
    """G8 (Delta): en Windows allow_reuse_address deja a dos programas en el mismo puerto; aquí el puerto se toma en exclusiva."""
    allow_reuse_address = False

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def crear_servidor(puerto=0):
    srv = _ServidorExclusivo(("127.0.0.1", puerto), Manejador)
    ESTADO.puerto = srv.server_address[1]
    return srv


_LATIDO = [0.0]


def registrar_servidor(msg):
    """Eta (punto 20c): ~/.uceclima/servidor.log dice cuándo y por qué se cerró o se reinició el servidor."""
    try:
        f = Path.home() / ".uceclima" / "servidor.log"; f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists() and f.stat().st_size > 2_000_000: f.replace(f.with_suffix(".log.1"))
        with open(f, "a", encoding="utf-8") as g: g.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass


def _vigilar_ventana(srv, tolerancia_s=120.0, espera_inicial_s=60.0, tolerancia_sin_ventana_s=6 * 3600.0):
    """La página envía un latido cada 5 s. Zeta se cerraba tras 120 s sin latidos aunque la ventana siguiera abierta (Windows congela la
    ventana de noche: Yaguachi, 1-nov-2026). Eta: solo se cierra cuando la ventana de la aplicación de verdad se cerró (su perfil ya no está
    bloqueado), nunca con una corrida o una descarga en curso, y deja escrito el motivo en ~/.uceclima/servidor.log."""
    import time
    from .lanzar import ventana_abierta
    t0 = time.time()
    while True:
        time.sleep(5)
        ult = _LATIDO[0] or t0
        limite = tolerancia_s if _LATIDO[0] else espera_inicial_s
        if time.time() - ult <= limite or (ESTADO.gestor and ESTADO.gestor.activa()) or ESTADO.descargas.activa():
            continue
        abierta = ventana_abierta()
        if abierta is True:
            continue                                       # la ventana existe pero está dormida o congelada: el servidor sigue
        if abierta is None and time.time() - ult <= tolerancia_sin_ventana_s:
            continue                                       # navegador predeterminado: no se puede saber, se espera mucho más
        registrar_servidor(f"Cierre normal: la ventana de UCEclima se cerró (último latido hace {time.time() - ult:.0f} s; sin corrida ni descarga en curso).")
        srv.shutdown(); return


def main(puerto=8765, abrir=True):
    try:
        srv = crear_servidor(puerto)
    except OSError:                                        # puerto ocupado (otra copia abierta): el siguiente libre, si no uno cualquiera
        srv = None
        for _p in range(puerto + 1, puerto + 20):
            try:
                srv = crear_servidor(_p); break
            except OSError:
                continue
        srv = srv or crear_servidor(0)
    url = f"http://127.0.0.1:{ESTADO.puerto}/"
    try:                                                   # el servidor MCP (agentes de VS Code / Claude Code) lee aquí el puerto real
        _pp = Path.home() / ".uceclima" / "puerto.txt"; _pp.parent.mkdir(parents=True, exist_ok=True); _pp.write_text(str(ESTADO.puerto), encoding="utf-8")
    except OSError:
        pass
    print(f"UCEclima en {url}  (Ctrl+C para cerrar)")
    registrar_servidor(f"Inicio de UCEclima {uceclima.__version__} en {url}")
    _sesion_restaurar(ESTADO)                                # Zeta «modo Word»: continúa con el último proyecto
    try:
        GEEC.precalentar()                                   # Zeta: Earth Engine se conecta en segundo plano al abrir (si ya hay autorización y proyecto)
    except Exception:
        pass
    if abrir:
        from .lanzar import abrir_ventana
        abrir_ventana(url)
    if getattr(sys, "frozen", False):                      # sin consola: al cerrar la ventana de la aplicación el programa se detiene solo
        threading.Thread(target=_vigilar_ventana, args=(srv,), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        registrar_servidor("Cierre con Ctrl+C.")
    except BaseException as e:
        registrar_servidor(f"Cierre por error: {type(e).__name__}: {str(e)[:300]}"); raise
    finally:
        if ESTADO.gestor and ESTADO.gestor.activa():
            ESTADO.gestor.cancelar()
        srv.server_close()


if __name__ == "__main__":
    main()
