# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Conexión con Google Earth Engine DENTRO de la interfaz (sin consola): 1) proyecto de Google Cloud de cada persona, 2) autorización en el navegador con SU cuenta de Google,
3) inicialización y verificación real de la conexión (se consulta un dato de CHIRPS). El programa nunca lee, muestra ni guarda el token: lo escribe la propia librería `ee`
en su carpeta de credenciales habitual. Solo el ID del proyecto se guarda en ~/.uceclima/config.json.

Por qué no `ee.Authenticate()` a secas: en el programa empaquetado no hay consola y el flujo por defecto espera un código por teclado, de modo que se quedaba colgado sin avisar."""
import json, os, re, threading, time, webbrowser
from datetime import datetime, timezone
from pathlib import Path

CONFIG_USUARIO = Path.home() / ".uceclima" / "config.json"
PLAZO_VERIF_S = 15                                       # Zeta: plazo DURO por proyecto (inicializar + consulta de prueba); nada se cuelga
TIEMPO_ESPERA_S = 300                                    # tiempo para aprobar en el navegador
_LOCK = threading.Lock()
_AUTH = {"fase": "reposo", "modo": None, "url": None, "mensaje": "", "error": None, "inicio": None}
_FLOW = {"flow": None}
_HILO = {"t": None, "pid": None}
_VERIF = {"ok": None, "fecha_utc": None, "proyecto": None, "detalle": None, "error": None, "ayuda": None}


class GeeError(ValueError):
    pass


def _cfg():
    try:
        return json.loads(CONFIG_USUARIO.read_text(encoding="utf-8")) if CONFIG_USUARIO.exists() else {}
    except Exception:
        return {}


def proyecto():
    """Zeta: manda el ID que la persona escribió en UCEclima (~/.uceclima/config.json); las variables de entorno solo si no escribió ninguno."""
    if _cfg().get("gee_project"):
        return _cfg()["gee_project"]
    for k in ("UCECLIMA_GEE_PROJECT", "EARTHENGINE_PROJECT", "GOOGLE_CLOUD_PROJECT"):
        if os.environ.get(k):
            return os.environ[k]
    return None


def proyecto_sugerido():
    """ID de proyecto que la propia librería `ee` dejó junto a las credenciales (campo «project», que no es secreto). Solo se SUGIERE: la persona lo confirma al guardarlo."""
    try:
        from ee import oauth
        return json.loads(Path(oauth.get_credentials_path()).read_text(encoding="utf-8")).get("project")
    except Exception:
        return None


_ID = r"[a-z][a-z0-9\-]{4,28}[a-z0-9]"


def _proyecto_gcloud():
    """Proyecto activo de la CLI de Google Cloud (gcloud), si la persona la tiene instalada: solo se lee la propiedad `project`."""
    for d in (Path(os.environ.get("APPDATA", "")) / "gcloud", Path.home() / ".config" / "gcloud"):
        f = d / "configurations" / "config_default"
        try:
            if f.exists():
                m = re.search(r"^\s*project\s*=\s*(\S+)", f.read_text(encoding="utf-8", errors="ignore"), re.M)
                if m:
                    return m.group(1)
        except Exception:
            pass
    return None


def candidatos():
    """Proyectos de Google Cloud que se prueban automáticamente, sin repetir: el guardado, los de variables de entorno, el que dejó `ee` junto a las credenciales y el de gcloud."""
    orden = [_cfg().get("gee_project"), os.environ.get("UCECLIMA_GEE_PROJECT"), os.environ.get("EARTHENGINE_PROJECT"), os.environ.get("GOOGLE_CLOUD_PROJECT"), proyecto_sugerido(), _proyecto_gcloud()]
    out = []
    for c in orden:
        if c and re.fullmatch(_ID, str(c)) and c not in out:
            out.append(c)
    return out


def conectar():
    """Conexión automática: con la autorización ya hecha, prueba cada proyecto candidato (inicializa Earth Engine y consulta CHIRPS) y se queda con el primero que funciona.
    Si ninguno funciona, devuelve el estado con lo probado para que la persona escriba el ID de SU proyecto."""
    probados = []
    if not credenciales_existen():
        with _LOCK:
            _VERIF.update(ok=False, error="Aún no hay autorización de tu cuenta.", ayuda="Pulsa «Conectar con Google Earth Engine» para autorizar.", detalle=None)
        return estado()
    for pid in ([proyecto()] if _cfg().get("gee_project") else candidatos()):      # Zeta: el proyecto escrito por la persona se prueba solo (llave directa)
        e = verificar(pid)
        v = e["verificacion"]
        probados.append({"proyecto": pid, "ok": bool(v["ok"]), "error": (v.get("error") or "")[:160]})
        if v["ok"]:
            guardar_proyecto(pid)
            with _LOCK:
                _VERIF.update(ok=True, proyecto=pid, detalle=v["detalle"], error=None, ayuda=None, fecha_utc=v["fecha_utc"])
            break
    with _LOCK:
        _VERIF["probados"] = probados
    if not probados:
        with _LOCK:
            _VERIF.update(ok=False, error="No encontré ningún proyecto de Google Cloud para probar.", ayuda="Escribe el ID de TU proyecto de Google Cloud registrado en Earth Engine (paso «Proyecto»).")
    return estado()


def guardar_proyecto(pid):
    pid = (pid or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9\-]{4,28}[a-z0-9]", pid):
        raise GeeError("El ID del proyecto de Google Cloud no parece válido. Es en minúsculas, con guiones, p. ej. «mi-proyecto-123» (no es el nombre visible ni el número del proyecto).")
    CONFIG_USUARIO.parent.mkdir(parents=True, exist_ok=True)
    cfg = _cfg(); cfg["gee_project"] = pid; CONFIG_USUARIO.write_text(json.dumps(cfg), encoding="utf-8")
    _VERIF.update(ok=None, error=None, detalle=None, ayuda=None)                       # cambió el proyecto: hay que verificar de nuevo
    try:
        from . import gee_chirps as _G
        if _G._SESION.get("proyecto") != pid:
            _G.olvidar_sesion()
    except Exception:
        pass
    return {"gee_project": pid}


def credenciales_existen():
    """True si la librería `ee` encuentra credenciales autorizadas en este equipo (no se lee ni se muestra su contenido)."""
    try:
        import ee
        ee.data.get_persistent_credentials()
        return True
    except Exception:
        return False


def estado():
    with _LOCK:
        a = dict(_AUTH); v = dict(_VERIF)
    pid = proyecto()
    cred = credenciales_existen()
    paso = 1 if not pid else (2 if not cred else (3 if not v["ok"] else 4))
    return {"proyecto": pid, "proyecto_sugerido": None if pid else (candidatos() or [None])[0], "candidatos": candidatos(), "credenciales": cred, "auth": a, "verificacion": v, "paso_actual": paso, "conectado": bool(v["ok"]),
            "guia_proyecto": "Necesitas un proyecto de Google Cloud registrado para Earth Engine (gratis para investigación/educación): https://code.earthengine.google.com/register — "
                             "al crearlo anota su ID (minúsculas con guiones).",
            "nota": "UCEclima nunca ve ni guarda tu contraseña ni tu token: la autorización la hace Google en tu navegador."}


def _ejecutar_flujo(modo):
    """Hilo: espera la aprobación en el navegador y deja que `ee` escriba las credenciales."""
    from ee import oauth
    try:
        if modo == "localhost":
            try:
                flow = oauth.Flow("localhost")                                                    # puerto habitual 8085
            except OSError:
                flow = oauth.Flow("localhost:0")                                                  # ocupado: Google acepta cualquier puerto local, se elige uno libre
        else:
            flow = oauth.Flow("notebook")
        _FLOW["flow"] = flow
        with _LOCK:
            _AUTH.update(url=flow.auth_url, fase="esperando_aprobacion" if modo == "localhost" else "esperando_codigo",
                         mensaje=("Se abrió el navegador: inicia sesión con tu cuenta de Google y pulsa «Permitir». Cuando termine, esta pantalla se actualiza sola." if modo == "localhost" else
                                  "Se abrió el navegador: inicia sesión, permite el acceso, copia el código que aparece y pégalo aquí."))
        try:
            webbrowser.open(flow.auth_url)
        except Exception:
            pass
        if modo == "localhost":
            flow.save_code()                                                     # bloquea hasta que Google redirige a localhost
            with _LOCK:
                if _AUTH["fase"] == "cancelado":
                    return
                _AUTH.update(fase="completado", mensaje="Autorización recibida. Ahora inicializa y verifica la conexión.", error=None)
    except Exception as e:
        with _LOCK:
            if _AUTH["fase"] != "cancelado":
                _AUTH.update(fase="error", error=str(e)[:300], mensaje="No se pudo completar la autorización automática (el navegador no pudo volver a UCEclima). Usa «Conectar con código»: es igual de válido.")


def iniciar_autorizacion(modo="localhost"):
    if modo not in ("localhost", "codigo"):
        raise GeeError("Modo de autorización desconocido.")
    with _LOCK:
        if _AUTH["fase"] in ("esperando_aprobacion", "esperando_codigo") and time.time() - (_AUTH["inicio"] or 0) < TIEMPO_ESPERA_S:
            return {**_AUTH, "reutilizada": True}
        _AUTH.update(fase="iniciando", modo=modo, url=None, mensaje="Preparando la autorización…", error=None, inicio=time.time())
    _cerrar_servidor()
    threading.Thread(target=_ejecutar_flujo, args=(modo,), daemon=True).start()
    for _ in range(60):                                                            # espera breve a que exista la URL (para mostrarla por si el navegador no se abre)
        with _LOCK:
            if _AUTH["url"] or _AUTH["fase"] == "error":
                break
        time.sleep(0.1)
    with _LOCK:
        return dict(_AUTH)


def enviar_codigo(codigo):
    codigo = (codigo or "").strip()
    fl = _FLOW.get("flow")
    if not codigo or fl is None or _AUTH["modo"] != "codigo":
        raise GeeError("Primero pulsa «Autorizar (modo código)» y copia el código que muestra Google.")
    try:
        fl.save_code(codigo)
    except Exception as e:
        raise GeeError("Google rechazó el código: " + str(e)[:200] + ". Genera uno nuevo con «Autorizar» y pégalo completo.")
    with _LOCK:
        _AUTH.update(fase="completado", mensaje="Código aceptado. Ahora inicializa y verifica la conexión.", error=None)
    return estado()


def _cerrar_servidor():
    fl = _FLOW.get("flow")
    try:
        if fl is not None and getattr(fl, "server", None):
            fl.server.server_close()
    except Exception:
        pass
    _FLOW["flow"] = None


def cancelar():
    with _LOCK:
        _AUTH.update(fase="cancelado", mensaje="Autorización cancelada.")
    _cerrar_servidor()
    return estado()


def _ayuda_error(msg):
    m = msg.lower()
    if "not signed up" in m or "not registered" in m or "register" in m and "earth engine" in m:
        return "Ese proyecto o esa cuenta no está registrado en Earth Engine: regístralo en https://code.earthengine.google.com/register (uso no comercial/investigación) y vuelve a verificar."
    if "earth engine api has not been used" in m or "api has not been used" in m or "service_disabled" in m:
        return "Falta habilitar la API de Earth Engine en tu proyecto de Google Cloud: en la consola de Google Cloud › APIs y servicios › habilita «Google Earth Engine API»."
    if "permission" in m or "403" in m:
        return "Tu cuenta no tiene permiso en ese proyecto: usa un proyecto propio o pide el rol «Earth Engine Resource Viewer / Writer»."
    if "credentials" in m or "authenticate" in m or "invalid_grant" in m or "401" in m:
        return "Las credenciales no son válidas o caducaron: vuelve a pulsar «Autorizar»."
    if "project" in m:
        return "Revisa el ID del proyecto (minúsculas con guiones); debe ser el ID, no el nombre visible."
    return "Revisa tu conexión a internet y vuelve a intentar; si persiste, copia el detalle del error."


def verificar(pid=None, plazo=None):
    """Zeta: igual que antes pero con PLAZO DURO (por defecto 15 s): si Earth Engine no responde, se avisa y la interfaz sigue; si responde más tarde, queda conectado igual."""
    plazo = PLAZO_VERIF_S if plazo is None else plazo
    pid_ = (pid or proyecto() or "").strip()
    previo = _HILO.get("t")
    if previo is not None and previo.is_alive() and _HILO.get("pid") == pid_:     # ya se está verificando ese proyecto (p. ej., el precalentamiento): se espera a ese, no se lanza otro
        previo.join(plazo)
        return estado()
    caja = {}
    hilo = threading.Thread(target=lambda: caja.update(r=_verificar(pid)), daemon=True); _HILO.update(t=hilo, pid=pid_); hilo.start(); hilo.join(plazo)
    if "r" in caja:
        return caja["r"]
    with _LOCK:
        _VERIF.update(ok=False, proyecto=(pid or proyecto()), fecha_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"), detalle=None,
                      error=f"Earth Engine no respondió en {plazo:.0f} s.",
                      ayuda="Revisa tu internet (o el proxy o cortafuegos de la institución) y el ID de tu proyecto. Si responde más tarde, UCEclima queda conectado solo: pulsa «Volver a verificar».")
    return estado()


def precalentar():
    """Al abrir UCEclima: importa `ee` y, si ya hay autorización y proyecto, conecta en segundo plano. Al llegar al módulo 2 la «llave» ya está puesta."""
    def _t():
        try:
            if proyecto() and credenciales_existen():
                verificar(proyecto(), plazo=45)
        except Exception:
            pass
    threading.Thread(target=_t, daemon=True, name="gee_precalentar").start()


def _verificar(pid=None):
    """Inicializa Earth Engine con el proyecto y comprueba que responde (consulta metadatos de CHIRPS: no descarga píxeles). Guarda el resultado para mostrarlo."""
    pid = (pid or proyecto() or "").strip()
    res = {"ok": False, "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "proyecto": pid or None, "detalle": None, "error": None, "ayuda": None}
    if not pid:
        res.update(error="Falta el ID del proyecto de Google Cloud.", ayuda="Completa el paso 1.")
    elif not credenciales_existen():
        res.update(error="Aún no hay autorización de tu cuenta.", ayuda="Completa el paso 2 («Autorizar»).")
    else:
        try:
            import ee
            t0 = time.time()
            ee.Initialize(project=pid)
            try:
                ee.data.setDeadline(20000)                                       # Zeta Z2: un proyecto que no responde se descarta en 20 s (antes podía colgar minutos)
            except Exception:
                pass
            n = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate("2020-01-01", "2020-01-03").size().getInfo()
            if int(n) < 1:
                raise RuntimeError("CHIRPS no devolvió imágenes de prueba")
            try:
                ee.data.setDeadline(180000)
                from . import gee_chirps as _G                                    # la sesión verificada se reutiliza en todas las descargas siguientes
                _G._SESION.update({"proyecto": pid, "t": time.time(), "ee": ee,
                                   "estado": {"autenticado": True, "proyecto": pid, "api": getattr(ee, "__version__", None), "error": None, "fecha_utc": res["fecha_utc"]}})
            except Exception:
                pass
            res.update(ok=True, detalle=f"Earth Engine {getattr(ee, '__version__', '?')} · proyecto {pid} · consulta de prueba a CHIRPS correcta ({int(n)} imágenes de muestra) en {time.time() - t0:.1f} s.")
        except Exception as e:
            msg = str(e)[:400]
            res.update(error=msg, ayuda=_ayuda_error(msg))
    with _LOCK:
        _VERIF.update(res)
    return estado()
