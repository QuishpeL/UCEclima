# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Validación de campo (Zeta, 31-oct-2026; reemplaza a la maqueta hipsométrica). Tres pasos, sin correr el modelo:
1) generar_encuesta: HTML autocontenido «¿Se inunda?» de la zona de estudio con los mapas de calado máximo de las corridas (X y Y),
   para encuestar a la comunidad sobre la cota de inundación (como el Taller 3 de Milagro, 23-sep-2026) y registrar las respuestas en línea
   (Apps Script del sitio, p. ej. climalab.net) o por WhatsApp/archivo. Deja además la carpeta lista para publicar en el sitio.
2) importar: marcas en GeoJSON (de la encuesta) o CSV (exportado de la hoja de respuestas); nada se sobrescribe.
3) contrastar: lee el calado del modelo en cada marca y lo compara con lo que dijo la comunidad (tabla de contingencia y altura).
   Es un contraste con conocimiento local: las marcas recuerdan eventos reales, el modelo da eventos de diseño; no es validación física."""
import base64, csv, io, json, re
from datetime import datetime
from pathlib import Path

import numpy as np

PLANT = Path(__file__).parent / "ui" / "static" / "validacion"
APP = "uceclima-validacion-campo-2.0"
CONEXION = Path.home() / ".uceclima" / "encuestas_en_linea.json"   # dirección de la hoja, sitio y clave de la hoja (solo en esta computadora; no va en las encuestas)
SITIO_DEF = "https://climalab.net"
AVISO_EN = ("Map from a model for design events: it is not calibrated or validated and it is not an observed event. "
            "Use it to compare with what you know, not to decide whether your house floods.")
MOJADO_M = 0.05                      # el modelo «moja» una marca si el calado ≥ 5 cm (mismo umbral que los mapas)
ALTURAS = {"Charco (menos de 10 cm)": (0.0, 0.10), "Tobillo a rodilla (10–50 cm)": (0.10, 0.50), "Cintura (50 cm–1 m)": (0.50, 1.0), "Más de 1 metro": (1.0, 99.0)}
CORTES = [0.05, 0.3, 0.5, 1.0, 2.0]
COLORES = [(220, 234, 247), (141, 187, 224), (58, 135, 198), (11, 74, 139), (6, 38, 77)]
ENDPOINT_OK = re.compile(r"^https://script\.google(usercontent)?\.com/macros/s/[A-Za-z0-9_-]+/exec$")
AVISO = ("Mapa de un modelo para eventos de diseño: no está calibrado ni validado y no es un evento observado. "
         "Sirve para comparar con lo que usted conoce, no para decidir si su casa se inunda.")


class CampoError(ValueError):
    pass


def _slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("-")
    return s[:40] or "zona"


def _sello():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _por_fecha(archivos):
    """Productos del módulo del más antiguo al más reciente (por fecha, no por nombre: el nombre empieza con la zona o la corrida)."""
    return sorted(archivos, key=lambda f: (f.stat().st_mtime, f.parent.name))


def _nueva(base):
    """Ruta que aún no existe: base, base_2, base_3… (dos acciones en el mismo segundo no chocan y nada se sobrescribe)."""
    base = Path(base); p = base; k = 2
    while p.exists(): p = base.with_name(f"{base.stem}_{k}{base.suffix}"); k += 1
    return p


def corridas(carpeta):
    """Corridas del proyecto con hmax.tif: id, escenario, Tr, lluvia, si es Y (CMIP6) y áreas."""
    out = []
    for f in sorted(Path(carpeta, "resultados").glob("*/salida/*/hmax.tif")):
        run = f.parents[2].name; r = {}
        if (f.parent / "resumen.json").exists():
            try: r = json.loads((f.parent / "resumen.json").read_text(encoding="utf-8"))
            except ValueError: r = {}
        y = "_cc_" in run or float(r.get("factor_cc") or 1) != 1
        hor = re.search(r"(\d{4}-\d{4})", run)
        out.append({"id": run, "escenario": f.parent.name, "Tr": r.get("Tr"), "P_mm": round(float(r.get("P_total_mm") or 0), 1), "Y": y,
                     "horizonte": hor.group(1) if hor else None, "area_ge_0.5_km2": r.get("area_ge_0.5_km2"), "hmax": str(f)})
    return out


def _titulo_capa(c, idioma="es"):
    if idioma == "en":
        tr = f"{c['Tr']}-year return period" if c.get("Tr") else c["escenario"].replace("_", " ")
        return (f"Y · climate change {c['horizonte'] or ''} · {tr}" if c["Y"] else f"X · current conditions · {tr}").replace("  ", " ")
    tr = f"Tr {c['Tr']} años" if c.get("Tr") else c["escenario"].replace("_", " ")
    return (f"Y · cambio climático {c['horizonte'] or ''} · {tr}" if c["Y"] else f"X · condiciones actuales · {tr}").replace("  ", " ")


def _capa_png(hmax, max_px=1400):
    """Calado máximo reproyectado a WGS84 como PNG RGBA (celdas < 5 cm transparentes) y sus límites [[S, O], [N, E]]."""
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from PIL import Image
    with rasterio.open(hmax) as s:
        if s.crs is None: raise CampoError(f"{Path(hmax).name} no tiene sistema de referencia.")
        tr, w, h = calculate_default_transform(s.crs, "EPSG:4326", s.width, s.height, *s.bounds)
        k = max(1.0, max(w, h) / max_px); w2, h2 = int(w / k), int(h / k)
        tr = tr * tr.scale(w / w2, h / h2)
        dst = np.full((h2, w2), np.nan, dtype="float32")
        src = s.read(1).astype("float32")
        if s.nodata is not None: src[src == s.nodata] = np.nan
        reproject(src, dst, src_transform=s.transform, src_crs=s.crs, dst_transform=tr, dst_crs="EPSG:4326", resampling=Resampling.max, src_nodata=np.nan, dst_nodata=np.nan)
    rgba = np.zeros((h2, w2, 4), dtype="uint8")
    for i, c in enumerate(CORTES):
        sup = CORTES[i + 1] if i + 1 < len(CORTES) else np.inf
        m = (dst >= c) & (dst < sup); rgba[m, :3] = COLORES[i]; rgba[m, 3] = 215
    b = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(b, "PNG", optimize=True)
    oeste, norte = tr.c, tr.f; este, sur = oeste + tr.a * w2, norte + tr.e * h2
    return base64.b64encode(b.getvalue()).decode("ascii"), [[sur, oeste], [norte, este]]


def _area_geojson(carpeta, limites):
    """Zona de estudio del proyecto (shape registrado) o, si no hay, el rectángulo de los mapas."""
    try:
        import geopandas as gpd
        for pat in ("datos/zona_estudio/*.shp", "datos/zona_estudio/*.gpkg", "datos/zona_estudio/*.geojson", "registro/cuenca/*.geojson"):
            for f in sorted(Path(carpeta).glob(pat)):
                g = gpd.read_file(f).to_crs(4326)
                if len(g): return json.loads(g[["geometry"]].to_json())
    except Exception:
        pass
    zg = _zona_utm(carpeta, "EPSG:4326")                    # sin geopandas (EXE): GeoJSON de la cuenca o de la zona
    if zg:
        from shapely.geometry import mapping
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(g)} for g in zg]}
    (s, o), (n, e) = limites
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[o, s], [e, s], [e, n], [o, n], [o, s]]]}}]}


def generar_encuesta(carpeta, ids=None, zona=None, endpoint=None, titulo=None, nombre_proyecto=None, base=None, idioma="es", publicar_en_linea=True):
    """Arma la encuesta HTML. ids: corridas a mostrar (por defecto la X de mayor Tr y las Y del mismo Tr, máximo 3).
    base: «un clic» desde una corrida terminada: esa corrida y, si es X, sus Y (CMIP6) del mismo Tr.
    endpoint: URL /exec del Apps Script (opcional; por defecto, la hoja conectada; sin ninguna se envía por WhatsApp o archivo).
    idioma: «es» o «en» (la persona puede cambiarlo en la encuesta). Si la hoja está conectada, la encuesta se publica sola y
    devuelve el enlace del sitio, el código QR y el mensaje de WhatsApp."""
    carpeta = Path(carpeta); todas = corridas(carpeta)
    if not todas: raise CampoError("El proyecto aún no tiene corridas 2D con calado máximo (hmax). Corre al menos la X en el módulo 7.")
    cx = _leer_conexion()
    if not endpoint and cx.get("endpoint"): endpoint = cx["endpoint"]
    idioma = "en" if str(idioma or "").lower().startswith("en") else "es"
    if endpoint and endpoint != cx.get("endpoint"):
        endpoint = endpoint.strip().split("?")[0]
        if not ENDPOINT_OK.match(endpoint): raise CampoError("La dirección de registro debe ser la de tu Apps Script: https://script.google.com/macros/s/…/exec")
    if base and not ids:
        b0 = next((c for c in todas if c["id"] == base), None)
        if b0 is None: raise CampoError(f"La corrida {base} no tiene calado máximo (hmax).")
        ids = [b0["id"]] + ([] if b0["Y"] else [y["id"] for y in _y_par(todas, b0)[:2]])
    if ids:
        sel = [c for c in todas if c["id"] in ids]
        if len(sel) != len(set(ids)): raise CampoError("Alguna corrida elegida no existe o no tiene hmax.")
    else:
        xs = [c for c in todas if not c["Y"]]
        if not xs: raise CampoError("No hay corrida X (condiciones actuales); la encuesta compara primero con X.")
        trx = max((c["Tr"] or 0) for c in xs); x = [c for c in xs if (c["Tr"] or 0) == trx][-1]
        ys = {}
        for c in todas:
            if c["Y"] and (c["Tr"] or 0) == trx: ys[c["horizonte"]] = c                      # la última de cada horizonte
        sel = [x] + [ys[k] for k in sorted(ys, key=str)][:2]
    capas = []
    for c in sel:
        png, lim = _capa_png(c["hmax"]); capas.append({"titulo": _titulo_capa(c, idioma), "tipo": "Y" if c["Y"] else "X", "png": png, "b": lim, "corrida": c["id"]})
    zona = (zona or nombre_proyecto or carpeta.name).strip(); slug = _slug(zona)
    titulo = (titulo or (f"Does it flood? {zona}" if idioma == "en" else f"¿Se inunda? {zona}")).strip()
    datos = {"titulo": titulo, "zona": zona, "slug": slug, "endpoint": endpoint or "", "form": f"validacion_{slug.replace('-', '_')}"[:60], "idioma": idioma,
             "area": _area_geojson(carpeta, capas[0]["b"]), "capas": [{k: v for k, v in c.items() if k != "corrida"} for c in capas], "aviso": AVISO_EN if idioma == "en" else AVISO,
             "pie": "" if idioma == "en" else "El archivo (.geojson) se abre en QGIS o Google Earth y se importa en UCEclima (módulo Validación de campo)."}
    t = _pagina(datos, titulo)
    sal = _nueva(carpeta / "productos" / "12_validacion_campo" / f"encuesta_{slug}_{_sello()}")
    sitio = sal / "publicar_en_sitio" / "validacion" / slug
    sitio.mkdir(parents=True, exist_ok=False)
    (sal / "encuesta.html").write_text(t, encoding="utf-8"); (sitio / "index.html").write_text(t, encoding="utf-8")
    (sal / "apps_script_registro.gs").write_text((PLANT / "apps_script_uceclima_v2.gs").read_text(encoding="utf-8"), encoding="utf-8")   # sin clave: la de cada persona la pone «Conectar mi hoja»
    meta = {"zona": zona, "slug": slug, "titulo": titulo, "form": datos["form"], "idioma": idioma, "registro_en_linea": bool(endpoint), "corridas": [c["corrida"] for c in capas],
            "capas": [c["titulo"] for c in capas], "creado": datetime.now().isoformat(timespec="seconds"), "app": APP, "tamano_kb": round(len(t.encode("utf-8")) / 1024)}
    if publicar_en_linea and endpoint and endpoint == cx.get("endpoint") and cx.get("clave"):
        try:
            _http(f"{endpoint}?accion=publicar&clave={cx['clave']}", datos)
            meta.update(_enlaces(sal, slug, titulo, cx, idioma))
        except (OSError, ValueError, CampoError) as e:
            meta["publicacion_error"] = f"No se pudo publicar en la hoja ({str(e)[:200]}). La encuesta HTML sí quedó lista para enviar por WhatsApp."
    (sal / "encuesta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (sal / "LEEME.txt").write_text(_leeme(meta), encoding="utf-8")
    return {**meta, "carpeta": str(sal), "html": str(sal / "encuesta.html"), "publicar": str(sal / "publicar_en_sitio")}


def _pagina(datos, titulo, endpoint_def=""):
    """La encuesta como página HTML: con DATA incrustado (archivo autocontenido) o vacía (página genérica del sitio, que lee DATA de la hoja)."""
    t = (PLANT / "encuesta.html").read_text(encoding="utf-8")
    for clave, archivo in (("/*LEAFLET_CSS*/", "leaflet.css"), ("/*ENCUESTA_CSS*/", "encuesta.css"), ("/*LEAFLET_JS*/", "leaflet.js"), ("/*ENCUESTA_JS*/", "encuesta.js")):
        t = t.replace(clave, (PLANT / archivo).read_text(encoding="utf-8").replace("</script", "<\\/script"), 1)
    dat = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/") if datos else "null; window.ENDPOINT_DEF = " + json.dumps(endpoint_def)
    return t.replace("/*DATA*/", dat, 1).replace("{{TITULO}}", _esc(titulo), 1)


def pagina_sitio(endpoint_def=""):
    """Página genérica para el sitio (p. ej. climalab.net/validacion/e/): abre cualquier encuesta publicada con ?z=<zona>&s=<id del Apps Script>.
    Se sube UNA vez; después cada encuesta nueva se publica desde UCEclima sin volver a subir el sitio."""
    return _pagina(None, "¿Se inunda? · Does it flood?", endpoint_def)


# ---------------------------------------------------------------- hoja de Google conectada (una vez) y publicación automática
def _leer_conexion():
    try:
        return json.loads(CONEXION.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def conexion():
    """Lo que la interfaz puede mostrar (nunca la clave)."""
    c = _leer_conexion()
    return {"endpoint": c.get("endpoint", ""), "sitio": c.get("sitio", SITIO_DEF), "conectada": bool(c.get("endpoint") and c.get("clave")), "creada": c.get("creada")}


def conectar(endpoint, sitio=None, _validar=True):
    """Conecta UCEclima con la hoja de validación de la persona (una vez). Crea la clave si no existe y devuelve el código para pegar en el Apps Script."""
    import secrets
    endpoint = str(endpoint or "").strip().split("?")[0]
    if _validar and not ENDPOINT_OK.match(endpoint): raise CampoError("Pega la dirección de tu Apps Script: https://script.google.com/macros/s/…/exec")
    c = _leer_conexion()
    c.update({"endpoint": endpoint, "sitio": (str(sitio or c.get("sitio") or SITIO_DEF).strip().rstrip("/")), "clave": c.get("clave") or secrets.token_urlsafe(18)})
    c.setdefault("creada", datetime.now().isoformat(timespec="seconds"))
    CONEXION.parent.mkdir(parents=True, exist_ok=True); CONEXION.write_text(json.dumps(c, indent=1), encoding="utf-8")
    gs = (PLANT / "apps_script_uceclima_v2.gs").read_text(encoding="utf-8").replace("{{CLAVE}}", c["clave"], 1)
    (CONEXION.parent / "apps_script_uceclima_v2.gs").write_text(gs, encoding="utf-8")
    return {**conexion(), "gs": gs, "archivo_gs": str(CONEXION.parent / "apps_script_uceclima_v2.gs")}


def _http(url, cuerpo=None, timeout=60):
    """GET (sin cuerpo) o POST de texto JSON al Apps Script; Google responde con una redirección que urllib sigue como GET."""
    import urllib.request
    req = urllib.request.Request(url, data=None if cuerpo is None else json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "text/plain;charset=utf-8", "User-Agent": "UCEclima"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        r = json.loads(f.read().decode("utf-8"))
    if not isinstance(r, dict) or not r.get("ok"):
        err = (r or {}).get("error") if isinstance(r, dict) else None
        raise CampoError("La hoja rechazó la clave: vuelve a pegar el código de «Conectar mi hoja» y haz «Nueva versión»." if err == "clave" else f"La hoja respondió con error: {err}")
    return r


def probar_conexion():
    c = _leer_conexion()
    if not c.get("endpoint"): raise CampoError("Primero conecta tu hoja (pega la dirección /exec).")
    r = _http(c["endpoint"])
    if int(r.get("version") or 1) < 2:
        raise CampoError("La hoja responde, pero tiene el código antiguo: pega el código nuevo de «Conectar mi hoja» y haz «Implementar › Administrar implementaciones › Nueva versión».")
    _http(f"{c['endpoint']}?accion=respuestas&form=_prueba_clave&clave={c['clave']}")
    return {"ok": True, "mensaje": "Hoja conectada: UCEclima puede publicar encuestas y leer respuestas."}


def _enlaces(sal, slug, titulo, cx, idioma):
    sid = re.search(r"/macros/s/([A-Za-z0-9_-]+)/exec", cx["endpoint"])
    enlace = f"{cx.get('sitio') or SITIO_DEF}/validacion/e/?z={slug}" + (f"&s={sid.group(1)}" if sid else "") + ("&lang=en" if idioma == "en" else "")
    from urllib.parse import quote
    msg = (f"{titulo}\nHelp us map where it floods (2 minutes, no personal data):\n{enlace}" if idioma == "en"
           else f"{titulo}\nAyúdenos a marcar dónde se inunda (2 minutos, sin datos personales):\n{enlace}")
    out = {"enlace": enlace, "whatsapp": "https://wa.me/?text=" + quote(msg), "publicada": datetime.now().isoformat(timespec="seconds")}
    try:
        import qrcode
        qrcode.make(enlace, box_size=10, border=2).save(sal / "qr_encuesta.png"); out["qr"] = str(sal / "qr_encuesta.png")
    except ImportError:
        pass
    (sal / "ENLACE.txt").write_text(f"{enlace}\n\nWhatsApp:\n{msg}\n", encoding="utf-8")
    return out


def _filas_a_marcas(filas, form):
    """Filas de la hoja → marcas: la última versión de cada id_marca; las borradas en el teléfono quedan como BORRADA (y no cuentan)."""
    ult = {}
    for i, r in enumerate(filas):
        mid = str(r.get("id_marca") or f"{form}_fila{i}")
        try: v = float(r.get("version_marca") or 0)
        except (TypeError, ValueError): v = 0
        if mid not in ult or v >= ult[mid][0]: ult[mid] = (v, r)
    feats = []
    for mid, (v, r) in ult.items():
        g = None
        if r.get("geometria_geojson"):
            try: g = json.loads(r["geometria_geojson"])
            except (TypeError, ValueError): g = None
        if g is None and r.get("lat") not in (None, "") and r.get("lon") not in (None, ""):
            try: g = {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]}
            except (TypeError, ValueError): g = None
        res = str(r.get("resultado") or "").upper().strip()
        if g is None or g.get("type") not in ("Point", "Polygon") or res not in ("SE INUNDA", "NO SE INUNDA"): continue
        p = {k: ("" if v2 is None else str(v2)) for k, v2 in r.items() if k != "geometria_geojson"}
        p.update({"id_marca": mid, "resultado": res, "estado": str(r.get("estado") or "ACTIVA").upper()})
        feats.append({"type": "Feature", "properties": p, "geometry": g})
    return feats


def sincronizar(carpeta, form=None, generar=True, fondo=True):
    """Trae las respuestas de la hoja conectada, las incorpora al proyecto (sin sobrescribir) y, si hay marcas, contrasta y genera las láminas."""
    carpeta = Path(carpeta); c = _leer_conexion()
    if not (c.get("endpoint") and c.get("clave")): raise CampoError("Primero conecta tu hoja (tarjeta «Conectar mi hoja», una sola vez).")
    if not form:
        enc = _por_fecha((carpeta / "productos" / "12_validacion_campo").glob("encuesta_*/encuesta.json"))
        if not enc: raise CampoError("Este proyecto aún no tiene encuesta: genérala primero con «Validar con la comunidad».")
        form = json.loads(enc[-1].read_text(encoding="utf-8"))["form"]
    from urllib.parse import quote
    filas = _http(f"{c['endpoint']}?accion=respuestas&form={quote(form)}&clave={c['clave']}").get("filas") or []
    feats = _filas_a_marcas(filas, form)
    d = carpeta / "datos" / "validacion_campo"; d.mkdir(parents=True, exist_ok=True)
    firma = sorted((x["properties"]["id_marca"], x["properties"].get("version_marca", ""), x["properties"]["estado"]) for x in feats)
    previas = sorted(d.glob(f"marcas_*_en_linea_{_slug(form)}.geojson"))
    nuevo = None
    if feats and (not previas or json.loads(previas[-1].read_text(encoding="utf-8")).get("properties", {}).get("firma") != json.dumps(firma)):
        nuevo = _nueva(d / f"marcas_{_sello()}_en_linea_{_slug(form)}.geojson")
        nuevo.write_text(json.dumps({"type": "FeatureCollection", "properties": {"origen": f"hoja en línea · pestaña {form}", "importado": datetime.now().isoformat(timespec="seconds"), "firma": json.dumps(firma)},
                                     "features": feats}, ensure_ascii=False), encoding="utf-8")
    activas = [x for x in feats if x["properties"]["estado"] != "BORRADA"]
    out = {"pestana": form, "filas": len(filas), "marcas": len(activas), "se_inunda": sum(x["properties"]["resultado"] == "SE INUNDA" for x in activas),
           "borradas": len(feats) - len(activas), "archivo": str(nuevo) if nuevo else None, "sin_cambios": nuevo is None and bool(feats)}
    if generar and marcas(carpeta):
        try:
            r = contrastar(carpeta); out["contraste"] = {k: r.get(k) for k in ("corrida", "aciertos", "omisiones", "falsas_alarmas", "aciertos_secos", "tasa_deteccion", "aviso_muestra", "carpeta")}
            lam = laminas(carpeta, fondo=fondo); out["laminas"] = {k: lam.get(k) for k in ("corrida_X", "lamina1", "lamina2", "carpeta", "marcas_en_dominio")}
        except CampoError as e:
            out["aviso"] = str(e)
    return out


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _leeme(m):
    return f"""Encuesta de campo «{m['titulo']}» · UCEclima (módulo Validación de campo)
Corridas mostradas: {', '.join(m['corridas'])}
Idioma inicial: {'inglés' if m.get('idioma') == 'en' else 'español'} (la persona puede cambiarlo en la encuesta con el botón EN/ES)
Registro en línea: {'sí, pestaña «' + m['form'] + '» de tu hoja conectada' if m['registro_en_linea'] else 'no (WhatsApp o archivo .geojson)'}
{('Enlace para compartir: ' + m['enlace'] + chr(10) + 'Código QR: qr_encuesta.png · mensaje de WhatsApp: ENLACE.txt' + chr(10)) if m.get('enlace') else ''}{(m['publicacion_error'] + chr(10)) if m.get('publicacion_error') else ''}
Cómo se usa:
1. Comparte el enlace (o el QR) por WhatsApp, o manda encuesta.html directamente: funciona en el teléfono sin servidor.
   Cada marca se envía sola a tu hoja cuando hay internet; sin señal queda guardada en el teléfono y se envía después.
2. En UCEclima, módulo 12, «Traer respuestas de la comunidad»: lee la hoja, incorpora las marcas (respeta las que la gente
   corrigió o borró), contrasta con el modelo y genera las láminas. Puedes repetirlo cuantas veces quieras.
Sin hoja conectada: módulo 12 › «Conectar mi hoja» (una sola vez; usa una hoja de Google NUEVA, no la de otras encuestas).
También puedes copiar publicar_en_sitio/validacion/ en tu sitio y desplegarlo COMPLETO, o importar a mano el CSV o los .geojson.
Es un contraste con conocimiento local, no una validación física del modelo.
No se guardan nombres ni datos personales; solo el nombre del grupo o barrio que la persona escriba.
"""


# ---------------------------------------------------------------- importar marcas
def _feat_csv(f):
    feats = []
    with open(f, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if (r.get("estado") or "ACTIVA").upper() != "ACTIVA": continue
            g = None
            if r.get("geometria_geojson"):
                try: g = json.loads(r["geometria_geojson"])
                except ValueError: g = None
            if g is None and r.get("lat") and r.get("lon"):
                g = {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]}
            if g is None: continue
            feats.append({"type": "Feature", "properties": {k: v for k, v in r.items() if k != "geometria_geojson"}, "geometry": g})
    return feats


def importar(carpeta, archivo):
    """Copia las marcas (GeoJSON de la encuesta o CSV de la hoja de respuestas) a datos/validacion_campo, sin sobrescribir."""
    f = Path(archivo)
    if not f.is_file(): raise CampoError(f"No existe el archivo {f}")
    if f.suffix.lower() in (".geojson", ".json"):
        g = json.loads(f.read_text(encoding="utf-8-sig")); feats = g.get("features", []) if g.get("type") == "FeatureCollection" else []
    elif f.suffix.lower() == ".csv":
        feats = _feat_csv(f)
    else:
        raise CampoError("Formato no admitido: usa el .geojson de la encuesta o el .csv de la hoja de respuestas.")
    feats = [x for x in feats if x.get("geometry") and x["geometry"].get("type") in ("Point", "Polygon")]
    for x in feats:
        p = x["properties"] = x.get("properties") or {}
        p["resultado"] = str(p.get("resultado") or "").upper().strip()
        if p["resultado"] not in ("SE INUNDA", "NO SE INUNDA"): p["resultado"] = ""
    feats = [x for x in feats if x["properties"]["resultado"]]
    if not feats: raise CampoError("El archivo no tiene marcas «SE INUNDA» o «NO SE INUNDA» con ubicación.")
    d = Path(carpeta) / "datos" / "validacion_campo"; d.mkdir(parents=True, exist_ok=True)
    dest = _nueva(d / f"marcas_{_sello()}_{_slug(f.stem)}.geojson")
    dest.write_text(json.dumps({"type": "FeatureCollection", "properties": {"origen": f.name, "importado": datetime.now().isoformat(timespec="seconds")}, "features": feats}, ensure_ascii=False), encoding="utf-8")
    return {"archivo": str(dest), "marcas": len(feats), "se_inunda": sum(x["properties"]["resultado"] == "SE INUNDA" for x in feats)}


def marcas(carpeta):
    """Todas las marcas importadas; si una marca (id_marca) se importó varias veces, queda la última."""
    vistas = {}
    for f in sorted((Path(carpeta) / "datos" / "validacion_campo").glob("marcas_*.geojson")):
        for i, x in enumerate(json.loads(f.read_text(encoding="utf-8"))["features"]):
            vistas[str(x["properties"].get("id_marca") or f"{f.stem}_{i}")] = x
    return [x for x in vistas.values() if str(x["properties"].get("estado") or "ACTIVA").upper() != "BORRADA"]   # borrada en el teléfono: no cuenta


# ---------------------------------------------------------------- contraste con el modelo
def _clase_altura(p):
    cm = str(p.get("altura_cm") or "").replace(",", ".").strip()
    try:
        v = float(cm) / 100
        if v >= 0: return (max(0.0, v - 0.1), v + 0.1), f"{cm} cm"
    except ValueError:
        pass
    a = str(p.get("altura_agua") or "").strip()
    return ALTURAS.get(a), a


def _elegir(carpeta, corrida=None):
    cs = corridas(carpeta)
    if not cs: raise CampoError("El proyecto no tiene corridas con hmax.")
    c = next((x for x in cs if x["id"] == corrida), None) if corrida else next((x for x in reversed(cs) if not x["Y"]), cs[-1])
    if c is None: raise CampoError(f"No existe la corrida {corrida} con hmax.")
    ms = marcas(carpeta)
    if not ms: raise CampoError("Aún no hay marcas importadas (botón «Importar marcas»).")
    return c, ms


def _resumen(c, filas):
    val = [f for f in filas if f["contraste"] != "fuera del dominio"]
    n = lambda k: sum(f["contraste"] == k for f in val)
    a, o, fa, s0 = n("acierto"), n("omisión del modelo"), n("falsa alarma"), n("acierto (seco)")
    si = a + o
    return {"corrida": c["id"], "escenario": c["escenario"], "Tr": c["Tr"], "Y": c["Y"], "horizonte": c["horizonte"], "marcas": len(filas), "fuera_del_dominio": len(filas) - len(val),
            "aciertos": a, "omisiones": o, "falsas_alarmas": fa, "aciertos_secos": s0,
            "tasa_deteccion": round(a / si, 2) if si else None, "indice_exito_critico": round(a / (a + o + fa), 2) if (a + o + fa) else None,
            "altura": {k: sum(f["altura"] == k for f in val if f["resultado"] == "SE INUNDA") for k in ("coincide", "el modelo subestima", "el modelo sobreestima", "sin dato")},
            "umbral_mojado_m": MOJADO_M,
            "aviso_muestra": ("No hay marcas «NO SE INUNDA»: no se pueden evaluar falsas alarmas y la tasa de detección sola es optimista (un modelo que moja todo acertaría siempre). Pide a la comunidad marcar también dónde NO llega el agua."
                              if not (fa + s0) else None),
            "nota": "Contraste con conocimiento local, no validación física: las marcas recuerdan eventos reales (a menudo con drenaje urbano, taponamientos o desbordes que el modelo no representa) y el modelo da un evento de diseño sin calibrar."}


def contrastar(carpeta, corrida=None):
    """Calado del modelo en cada marca (punto: máximo en 3×3 celdas; zona: máximo y media dentro) frente a lo declarado."""
    carpeta = Path(carpeta); c, ms = _elegir(carpeta, corrida)
    filas = _muestrear(c, ms); res = _resumen(c, filas)
    sal = _nueva(carpeta / "productos" / "12_validacion_campo" / f"contraste_{c['id']}_{_sello()}"); sal.mkdir(parents=True, exist_ok=False)
    cols = [k for k in filas[0] if not k.startswith("_")]
    with open(sal / "contraste_marcas.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); [w.writerow({k: f[k] for k in cols}) for f in filas]
    (sal / "contraste_marcas.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {k: f[k] for k in cols}, "geometry": f["_geom"]} for f in filas]}, ensure_ascii=False), encoding="utf-8")
    (sal / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    _figura(c["hmax"], filas, res, sal / "contraste_mapa.png")
    return {**res, "carpeta": str(sal), "filas": [{k: f[k] for k in cols} for f in filas]}


def _muestrear(c, ms):
    import rasterio
    from rasterio.features import geometry_mask
    from shapely.geometry import shape, mapping
    from shapely.ops import transform as stransform
    from pyproj import Transformer
    filas = []
    with rasterio.open(c["hmax"]) as s:
        h = s.read(1).astype(float)
        if s.nodata is not None: h[h == s.nodata] = np.nan
        h = np.where(np.isfinite(h), h, 0.0)
        a_utm = Transformer.from_crs(4326, s.crs, always_xy=True).transform
        for x in ms:
            p = x["properties"]; g = stransform(a_utm, shape(x["geometry"]))
            if g.geom_type == "Point":
                f, k = s.index(g.x, g.y)
                if not (0 <= f < s.height and 0 <= k < s.width): hm = hmed = None
                else: v = h[max(0, f - 1):f + 2, max(0, k - 1):k + 2]; hm = float(v.max()); hmed = float(h[f, k])
            else:
                m = ~geometry_mask([mapping(g)], h.shape, s.transform, all_touched=True); v = h[m]
                hm, hmed = (float(v.max()), float(v.mean())) if v.size else (None, None)
            dicen = p["resultado"] == "SE INUNDA"
            if hm is None: cat = "fuera del dominio"
            else: moja = hm >= MOJADO_M; cat = {(True, True): "acierto", (True, False): "omisión del modelo", (False, True): "falsa alarma", (False, False): "acierto (seco)"}[(dicen, moja)]
            rango, decl = _clase_altura(p) if dicen else (None, "")
            alt = ("sin dato" if not rango or hm is None else "coincide" if rango[0] <= hm <= rango[1] or (rango[1] >= 99 and hm >= 1) else "el modelo subestima" if hm < rango[0] else "el modelo sobreestima")
            c4 = shape(x["geometry"]).centroid
            filas.append({"id_marca": p.get("id_marca", ""), "grupo": p.get("grupo", ""), "resultado": p["resultado"], "forma": x["geometry"]["type"], "lon": round(c4.x, 6), "lat": round(c4.y, 6),
                          "altura_declarada": decl, "frecuencia": p.get("frecuencia", ""), "evento_mas_fuerte": p.get("evento_mas_fuerte", ""),
                          "calado_modelo_max_m": None if hm is None else round(hm, 2), "calado_modelo_celda_o_media_m": None if hmed is None else round(hmed, 2),
                          "contraste": cat, "altura": alt, "_geom": x["geometry"], "_p": p})
    return filas


def _figura(hmax, filas, res, png):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rasterio
    from pyproj import Transformer
    with rasterio.open(hmax) as s:
        h = s.read(1).astype(float); h[(h < MOJADO_M) | ~np.isfinite(h)] = np.nan; b = s.bounds; crs = s.crs
    t = Transformer.from_crs(4326, crs, always_xy=True).transform
    fig, ax = plt.subplots(figsize=(9, 7), dpi=150)
    ax.imshow(h, extent=[b.left, b.right, b.bottom, b.top], cmap="Blues", vmin=0, vmax=2, interpolation="nearest")
    col = {"acierto": "#1E8E6E", "acierto (seco)": "#7FB8A4", "omisión del modelo": "#C0392B", "falsa alarma": "#E67E22", "fuera del dominio": "#95A5A6"}
    for k, cc in col.items():
        pts = [t(f["lon"], f["lat"]) for f in filas if f["contraste"] == k]
        if not pts: continue
        if k == "fuera del dominio": ax.scatter([], [], s=46, c=cc, label=f"{k} ({len(pts)}, no se dibuja)")
        else: ax.scatter(*zip(*pts), s=46, c=cc, edgecolors="white", linewidths=1, label=f"{k} ({len(pts)})", zorder=3)
    ax.set_xlim(b.left, b.right); ax.set_ylim(b.bottom, b.top)
    ax.set_title(f"Marcas de la comunidad frente al calado máximo del modelo · {res['escenario']}", fontsize=10, loc="left")
    ax.text(0.01, 0.01, "Contraste con conocimiento local; no es validación física. Modelo sin calibrar.", transform=ax.transAxes, fontsize=7, color="#555")
    ax.legend(fontsize=8, loc="upper right"); ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(png, bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------- láminas (estilo Taller 3 de Milagro, 23-sep-2026)
RADIO_BUFFER_M = 250                  # alcance del área de influencia difuminada de cada marca «se inunda»
NAVY, ROJO, AZUL, GRIS, PALIDO, MAGENTA = "#0B2545", "#C0392B", "#2E6DA4", "#5B6B7A", "#EEF3F9", "#A3195B"
ALT_COL = [("Charco", "#F6B3A5", "Charco (< 10 cm)"), ("Tobillo", "#E8735F", "Tobillo a rodilla (10–50 cm)"),
           ("Cintura", "#C0392B", "Cintura (50 cm–1 m)"), ("Más de 1", "#7A1010", "Más de 1 metro")]
PERD_SZ = [("Nada", 9), ("Menos de USD 100", 10), ("USD 100 a 500", 12), ("USD 500 a 2", 15), ("USD 2.000 o m", 19)]
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _color_altura(p):
    a = str(p.get("altura_agua") or "")
    for k, c, _ in ALT_COL:
        if a.startswith(k): return c
    try:
        v = float(str(p.get("altura_cm") or "").replace(",", "."))
        return ALT_COL[0 if v < 10 else 1 if v < 50 else 2 if v < 100 else 3][1]
    except ValueError:
        return None


def _tam_perdida(p):
    s = str(p.get("perdida_usd") or "")
    return next((z for k, z in PERD_SZ if s.startswith(k)), 12)


def _top(vals, k=2):
    from collections import Counter
    c = Counter(v.strip() for v in vals if str(v or "").strip())
    return "; ".join(f"{a} ({b})" for a, b in c.most_common(k)) or "—"


def _leer_h(hmax):
    import rasterio
    with rasterio.open(hmax) as s:
        h = s.read(1).astype(float)
        if s.nodata is not None: h[h == s.nodata] = np.nan
        h[(h < MOJADO_M) | ~np.isfinite(h)] = np.nan
        return h, s.bounds, s.crs


def _y_par(cs, x):
    """Corridas Y (CMIP6) del mismo Tr que la X: la última de cada horizonte."""
    ys = {}
    for c in cs:
        if c["Y"] and (c["Tr"] or 0) == (x["Tr"] or 0): ys[c["horizonte"]] = c
    return [ys[k] for k in sorted(ys, key=str)]


def _marcas_utm(filas, crs):
    from shapely.geometry import shape
    from shapely.ops import transform as stransform
    from pyproj import Transformer
    t = Transformer.from_crs(4326, crs, always_xy=True).transform
    return [(stransform(t, shape(f["_geom"])), f) for f in filas]


def _extension(geoms, b, ratio):
    """Recuadro que contiene las marcas dentro del dominio (+ margen), con la proporción del mapa y una cuadrícula de 0,5–10 km."""
    xs = [v for g, _ in geoms for v in (g.bounds[0], g.bounds[2])]; ys = [v for g, _ in geoms for v in (g.bounds[1], g.bounds[3])]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    pad = max(600.0, 0.15 * max(x1 - x0, y1 - y0)); x0 -= pad; x1 += pad; y0 -= pad; y1 += pad
    w, h = max(x1 - x0, 2000.0), max(y1 - y0, 2000.0)
    if w / h < ratio: w = h * ratio
    else: h = w / ratio
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    celda = next((c for c in (500, 1000, 2000, 5000, 10000, 20000) if w / c <= 10), 50000)
    nc, nf = int(np.ceil(w / celda)), int(np.ceil(h / celda))
    return [cx - nc * celda / 2, cy - nf * celda / 2, cx + nc * celda / 2, cy + nf * celda / 2], celda, nc, nf


def _acumulacion(geoms, e, radio, res):
    """Buffer acumulativo: suma de áreas de influencia gaussianas de las marcas «se inunda» (las zonas se rasterizan y difuminan)."""
    from scipy.ndimage import gaussian_filter
    from rasterio import features
    from rasterio.transform import from_origin
    nx, ny = int((e[2] - e[0]) / res), int((e[3] - e[1]) / res)
    tr = from_origin(e[0], e[3], res, res); sig = radio / 2.2
    xs = e[0] + (np.arange(nx) + .5) * res; ys = e[3] - (np.arange(ny) + .5) * res; XX, YY = np.meshgrid(xs, ys)
    acc = np.zeros((ny, nx))
    for g, f in geoms:
        if f["resultado"] != "SE INUNDA": continue
        if g.geom_type in ("Polygon", "MultiPolygon"):
            m = features.rasterize([(g, 1)], out_shape=(ny, nx), transform=tr, fill=0, dtype="uint8").astype(float)
            acc += np.clip(gaussian_filter(m, sig / res), 0, 1)
        else:
            acc += np.exp(-((XX - g.x) ** 2 + (YY - g.y) ** 2) / (2 * sig ** 2))
    return acc, tr


def _fondo(ax, crs, fondo):
    if not fondo: ax.set_facecolor("#EEF1F4"); return "sin mapa de fondo"
    try:
        import contextily as ctx
        ctx.add_basemap(ax, source=ctx.providers.Esri.WorldGrayCanvas, crs=crs, attribution=False, zoom="auto")
        return "Base: Esri Light Gray Canvas"
    except Exception:
        ax.set_facecolor("#EEF1F4"); return "sin mapa de fondo (sin conexión)"


def _cabecera(fig, sobre, titulo, sub, derecha1, derecha2, H=7.5):
    """Banda azul con filete rojo (alturas en pulgadas, para que no cambie con el alto de la lámina)."""
    from matplotlib.patches import Rectangle
    y = lambda d: 1 - d / H
    fig.patches.append(Rectangle((0, y(.7125)), 1, .7125 / H, transform=fig.transFigure, fc=NAVY, ec="none", zorder=0))
    fig.patches.append(Rectangle((0, y(.7575)), 1, .045 / H, transform=fig.transFigure, fc=ROJO, ec="none", zorder=0))
    fig.text(.02, y(.09), sobre.upper(), color="#9DB7D5", fontsize=8, weight="bold", va="top")
    fig.text(.02, y(.285), titulo, color="white", fontsize=17, weight="bold", va="top")
    fig.text(.02, y(.5625), sub, color="#DCE6F2", fontsize=8.5, va="top")
    fig.text(.98, y(.3375), derecha1, color="white", fontsize=10, weight="bold", ha="right", va="top")
    fig.text(.98, y(.5625), derecha2, color="#9DB7D5", fontsize=7.5, ha="right", va="top")


def _norte_escala(ax, e, celda):
    ax.annotate("N", xy=(.965, .93), xycoords="axes fraction", fontsize=13, weight="bold", ha="center", color="white", bbox=dict(boxstyle="circle,pad=.3", fc=NAVY, ec="none"), zorder=13)
    x0, y0 = e[2] - celda * 1.15, e[1] + celda * .18
    ax.plot([x0, x0 + celda], [y0, y0], color=NAVY, lw=4, solid_capstyle="butt", zorder=13)
    ax.text(x0 + celda / 2, y0 + celda * .05, f"{celda / 1000:g} km", ha="center", va="bottom", fontsize=7, weight="bold", color=NAVY, zorder=13)


def _contorno(ax, g, **kw):
    """Borde de un polígono con matplotlib (el EXE no incluye geopandas)."""
    for pol in getattr(g, "geoms", [g]):
        x, y = pol.exterior.xy; ax.plot(x, y, **kw)


def _dibujar_marcas(ax, geoms, n_total, numerar=True):
    fac = 1.0 if n_total <= 8 else max(.3, (8 / n_total) ** .5)
    for i, (g, f) in enumerate(geoms, 1):
        p = f["_p"]; si = f["resultado"] == "SE INUNDA"; c = g.centroid
        if si:
            fc = _color_altura(p); hueco = fc is None; fc = fc or "white"
            rec = str(p.get("frecuencia") or "").startswith("Todos")
            ec, lw = (ROJO, 1.8) if hueco else ((NAVY, 2.4) if rec else ("white", 1.3)); mk = "o"; z = _tam_perdida(p) ** 2 * 1.2
        else:
            fc, ec, lw, mk, z, hueco = AZUL, "white", 1.4, "s", 120, False
        if g.geom_type in ("Polygon", "MultiPolygon"): _contorno(ax, g, color=ROJO if si else AZUL, lw=1.6, zorder=8)
        ax.scatter(c.x, c.y, s=z * fac, c=fc, marker=mk, edgecolors=ec, linewidths=max(.7, lw * fac ** .5), alpha=.95 if n_total <= 8 else .85, zorder=11)
        if numerar and n_total <= 25:
            oscuro = (not si) or (not hueco and fc in ("#C0392B", "#7A1010", "#E8735F"))
            ax.annotate(str(i), (c.x, c.y), ha="center", va="center", fontsize=6, weight="bold", color="white" if oscuro else NAVY, zorder=12)


def _zona_utm(carpeta, crs):
    """Contorno de la zona de estudio en el sistema del ráster (lista de geometrías shapely), o None."""
    try:
        from shapely.geometry import shape
        from shapely.ops import transform as stransform
        from pyproj import Transformer
        for f in sorted(Path(carpeta).glob("registro/cuenca/*.geojson")) + sorted(Path(carpeta).glob("datos/zona_estudio/*.geojson")):
            g = json.loads(f.read_text(encoding="utf-8"))
            src = (g.get("crs") or {}).get("properties", {}).get("name", "EPSG:4326")
            t = Transformer.from_crs(src if "CRS84" not in src else "EPSG:4326", crs, always_xy=True).transform
            gs = [stransform(t, shape(x["geometry"])) for x in g.get("features", []) if x.get("geometry")]
            gs = [x for x in gs if x.geom_type in ("Polygon", "MultiPolygon")]
            if gs: return gs
        import geopandas as gpd                                                     # shp/gpkg, si geopandas está disponible (no en el EXE)
        for pat in ("datos/zona_estudio/*.shp", "datos/zona_estudio/*.gpkg"):
            for f in sorted(Path(carpeta).glob(pat)):
                g = gpd.read_file(f).to_crs(crs)
                if len(g): return list(g.geometry)
    except Exception:
        pass
    return None


def laminas(carpeta, corrida=None, zona=None, radio_m=RADIO_BUFFER_M, fondo=True):
    """Láminas para el informe (como el Taller 3 de Milagro): 1) mapa consolidado de las marcas con buffer acumulativo, cuadrícula
    y lo que dijo la comunidad, sobre la mancha del modelo X; 2) la comunidad frente al modelo X y frente a Y (cambio climático), si hay Y del mismo Tr."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import textwrap as tw
    import rasterio
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Rectangle
    carpeta = Path(carpeta)
    if not corrida:                       # la X que se mostró en la última encuesta; si no, la X de mayor Tr
        cs = corridas(carpeta); xs = [x for x in cs if not x["Y"]]
        encs = _por_fecha((carpeta / "productos" / "12_validacion_campo").glob("encuesta_*/encuesta.json"))
        ult = json.loads(encs[-1].read_text(encoding="utf-8")).get("corridas", []) if encs else []
        corrida = next((i for i in ult if any(x["id"] == i for x in xs)), None)
        if not corrida and xs: corrida = [x for x in xs if (x["Tr"] or 0) == max((x["Tr"] or 0) for x in xs)][-1]["id"]
    nota_x = None
    if corrida:                           # Eta (punto 34): si piden una Y (p. ej., la última contrastada), la lámina 1 usa la X del mismo Tr; la Y va a la lámina 2
        cs_ = corridas(carpeta); pedida = next((x for x in cs_ if x["id"] == corrida), None)
        if pedida and pedida["Y"]:
            xs_ = [x for x in cs_ if not x["Y"] and x.get("Tr") == pedida.get("Tr")] or [x for x in cs_ if not x["Y"]]
            if xs_:
                nota_x = f"Se pidió la corrida Y {corrida}; la lámina 1 usa la X {xs_[-1]['id']} (condiciones actuales) y la Y va en la lámina 2."; corrida = xs_[-1]["id"]
    c, ms = _elegir(carpeta, corrida)
    zona = (zona or carpeta.name).strip()
    filas = _muestrear(c, ms); res = _resumen(c, filas)
    h, b, crs = _leer_h(c["hmax"])
    todas = _marcas_utm(filas, crs)
    geoms = [(g, f) for g, f in todas if f["contraste"] != "fuera del dominio"]
    if not geoms: raise CampoError("Ninguna marca cae dentro del dominio del modelo; revisa que el proyecto y las marcas sean de la misma zona.")
    N = len(geoms); si = [f for _, f in geoms if f["resultado"] == "SE INUNDA"]; no = [f for _, f in geoms if f["resultado"] != "SE INUNDA"]
    e, celda, nc, nf = _extension(geoms, b, 1.34)
    acc, tr = _acumulacion(geoms, e, radio_m, float(np.clip(celda / 50, 10, 50)))
    vmax = max(3.0, float(acc.max())) if acc.size else 3.0
    zon = _zona_utm(carpeta, crs)
    sal = _nueva(carpeta / "productos" / "12_validacion_campo" / f"laminas_{_slug(zona)}_{_sello()}"); sal.mkdir(parents=True, exist_ok=False)
    with rasterio.open(sal / "buffer_acumulado.tif", "w", driver="GTiff", height=acc.shape[0], width=acc.shape[1], count=1, dtype="float32", crs=crs, transform=tr) as d:
        d.write(acc.astype("float32"), 1)
    grupos = len({str(f["_p"].get("grupo") or "").strip() for f in si + no} - {""})
    pie = "UCEclima Lambda · módulo 12 Validación de campo"
    der2 = "Doctorado en Gestión Sustentable del Agua y Riego · UCE"
    tr_txt = f"Tr {c['Tr']} años" if c.get("Tr") else c["escenario"]

    # ---------------- lámina 1 · consolidado
    cm_acc = LinearSegmentedColormap.from_list("acc", ["#FBD5C8", "#F08A6E", "#C0392B", "#7A1010", "#3D0808"])
    fig = plt.figure(figsize=(13.33, 7.5), dpi=200, facecolor="white")
    _cabecera(fig, f"Validación social del riesgo · {zona}", "Resultados consolidados del mapeo comunitario",
              f"Todas las respuestas · cuadrícula de {celda / 1000:g} km (A–{LETRAS[nc - 1]} × 1–{nf}) · buffer acumulativo de {radio_m:g} m · mancha del modelo X ({tr_txt})",
              "UCEclima Lambda", der2)
    ax = fig.add_axes([.015, .07, .61, .81]); ax.set_xlim(e[0], e[2]); ax.set_ylim(e[1], e[3]); ax.set_aspect("equal")
    base = _fondo(ax, crs, fondo); ax.set_xticks([]); ax.set_yticks([])
    for s_ in ax.spines.values(): s_.set_edgecolor(NAVY); s_.set_linewidth(1.6)
    ax.imshow(np.where(np.isfinite(h), 1.0, np.nan), extent=(b.left, b.right, b.bottom, b.top), cmap=LinearSegmentedColormap.from_list("m", ["#8DBBE0", "#8DBBE0"]), alpha=.38, zorder=3, interpolation="nearest")
    for zg in zon or []: _contorno(ax, zg, color=NAVY, lw=1.0, ls="--", zorder=4)
    norm = np.clip(acc / vmax, 0, 1) ** 0.8; rgba = cm_acc(norm); rgba[..., 3] = np.clip(acc / 0.10, 0, 1) * (0.50 + 0.42 * norm)
    ax.imshow(rgba, extent=(e[0], e[2], e[1], e[3]), origin="upper", zorder=5, interpolation="bilinear")
    for i in range(nc + 1): ax.plot([e[0] + i * celda] * 2, [e[1], e[3]], color=NAVY, lw=.7, ls=(0, (4, 3)), alpha=.55, zorder=7)
    for j in range(nf + 1): ax.plot([e[0], e[2]], [e[3] - j * celda] * 2, color=NAVY, lw=.7, ls=(0, (4, 3)), alpha=.55, zorder=7)
    for i in range(nc):
        ax.text(e[0] + (i + .5) * celda, e[3] - celda * .12, LETRAS[i], fontsize=7.5, weight="bold", color="white", ha="center", va="center", zorder=10, bbox=dict(boxstyle="circle,pad=.25", fc=NAVY, ec="white"))
    for j in range(nf):
        ax.text(e[0] + celda * .12, e[3] - (j + .5) * celda, str(j + 1), fontsize=7.5, weight="bold", color="white", ha="center", va="center", zorder=10, bbox=dict(boxstyle="circle,pad=.25", fc=NAVY, ec="white"))
    _dibujar_marcas(ax, geoms, N); _norte_escala(ax, e, celda)
    ax.text(.995, .006, f"{base} · {crs.to_string()} · {N} de {len(todas)} marcas dentro del dominio del modelo", transform=ax.transAxes, fontsize=5.5, color=GRIS, ha="right", va="bottom", zorder=13, bbox=dict(fc="white", alpha=.8, pad=1.5, ec="none"))
    celdas = {}
    for g, f in geoms:
        k = int((g.centroid.x - e[0]) // celda), int((e[3] - g.centroid.y) // celda)
        if 0 <= k[0] < nc and 0 <= k[1] < nf: celdas[f"{LETRAS[k[0]]}{k[1] + 1}"] = celdas.get(f"{LETRAS[k[0]]}{k[1] + 1}", 0) + 1
    pa = fig.add_axes([.64, .07, .345, .81]); pa.axis("off"); pa.set_xlim(0, 1); pa.set_ylim(0, 1)
    pa.add_patch(Rectangle((0, 0), 1, 1, fc=PALIDO, ec="#C9D7E6", lw=1, zorder=0, transform=pa.transAxes))
    pa.text(.04, .975, f"{N}", fontsize=34, weight="bold", color=ROJO, va="top"); nx_ = .04 + .075 * len(str(N)) + .03
    pa.text(nx_, .96, "marcas de la comunidad", fontsize=10.5, weight="bold", color=NAVY, va="top")
    pa.text(nx_, .93, f"{len(si)} «se inunda» · {len(no)} «no se inunda» · {grupos} grupo(s)", fontsize=7.5, color=GRIS, va="top")

    def titulo(y, s):
        pa.text(.04, y, s, fontsize=7.8, weight="bold", color=NAVY, va="top"); pa.plot([.04, .96], [y - .024, y - .024], color="#9DB7D5", lw=.8)
    titulo(.885, "BUFFER ACUMULATIVO · marcas «se inunda» superpuestas")
    pa.imshow(np.linspace(0, 1, 200)[None, :], extent=(.06, .94, .823, .845), aspect="auto", cmap=cm_acc, zorder=2); pa.set_xlim(0, 1); pa.set_ylim(0, 1)
    pa.text(.06, .815, "1 marca", fontsize=6.8, color=NAVY, va="top"); pa.text(.5, .815, "varias", fontsize=6.8, color=NAVY, va="top", ha="center")
    pa.text(.94, .815, f"{vmax:.0f}+ superpuestas", fontsize=6.8, color=NAVY, va="top", ha="right")
    titulo(.775, "COLOR · altura del agua declarada")
    for k, (_, cc, lab) in enumerate(ALT_COL):
        xx = .06 + (k % 2) * .47; yy = .728 - (k // 2) * .037
        pa.scatter(xx, yy, s=80, c=cc, edgecolors="white", linewidths=1, zorder=3); pa.text(xx + .035, yy, lab, fontsize=6.8, va="center", color=NAVY)
    pa.scatter(.06, .654, s=80, c="white", edgecolors=ROJO, linewidths=1.6, zorder=3); pa.text(.095, .654, "Sin dato de altura", fontsize=6.8, va="center", color=NAVY)
    pa.scatter(.53, .654, s=70, c=AZUL, marker="s", edgecolors="white", zorder=3); pa.text(.565, .654, "NO se inunda", fontsize=6.8, va="center", color=NAVY)
    pa.add_patch(Rectangle((.045, .603), .03, .022, fc="#8DBBE0", alpha=.6, ec="none")); pa.text(.095, .614, f"Mancha del modelo X (calado ≥ {MOJADO_M * 100:.0f} cm)", fontsize=6.8, va="center", color=NAVY)
    pa.scatter(.565, .614, s=90, c="#E8735F", edgecolors=NAVY, linewidths=2.2, zorder=3); pa.text(.6, .614, "Anillo = todos los años", fontsize=6.8, va="center", color=NAVY)
    titulo(.575, f"CONTRASTE CON EL MODELO X · {tr_txt}")
    lin = [f"Aciertos {res['aciertos']} · omisiones {res['omisiones']} · falsas alarmas {res['falsas_alarmas']} · aciertos secos {res['aciertos_secos']}",
           f"Tasa de detección {res['tasa_deteccion'] if res['tasa_deteccion'] is not None else '—'} · índice de éxito crítico {res['indice_exito_critico'] if res['indice_exito_critico'] is not None else '—'}",
           "Altura: coincide {coincide} · el modelo subestima {el modelo subestima} · sobreestima {el modelo sobreestima} · sin dato {sin dato}".format(**res["altura"])]
    if res["aviso_muestra"]: lin.append("Sin marcas «NO se inunda»: las falsas alarmas no se pueden evaluar.")
    y = .528
    for t in lin: pa.text(.04, y, t, fontsize=6.8, color="#1B2A3A", va="top"); y -= .03
    titulo(y - .01, "LO QUE DIJO LA COMUNIDAD"); y -= .058
    filas_txt = [("Frecuencia", _top([f["_p"].get("frecuencia") for f in si])), ("Altura del agua", _top([f["_p"].get("altura_agua") for f in si])),
                 ("Se afecta", _top([f["_p"].get("afectado") for f in si])), ("Evento más fuerte", _top([f["_p"].get("evento_mas_fuerte") for f in si])),
                 ("Celdas con marcas", ", ".join(f"{k} ({v})" for k, v in sorted(celdas.items(), key=lambda kv: -kv[1])[:5]) or "—")]
    for lab, val in filas_txt:
        ls = tw.wrap(val, 40) or ["—"]
        pa.text(.04, y, lab, fontsize=6.8, weight="bold", color=ROJO, va="top"); pa.text(.34, y, "\n".join(ls[:2]), fontsize=6.9, color="#1B2A3A", va="top")
        y -= .0235 * len(ls[:2]) + .012
    pa.text(.5, .012, "Contraste con conocimiento local, no validación física · modelo sin calibrar", fontsize=6.3, color=GRIS, ha="center", va="bottom", style="italic")
    fig.text(.02, .035, f"Fuente: marcas de la comunidad importadas en el proyecto (última versión de cada marca) · modelo 2D UCEclima, corrida {c['id']} · {pie}", fontsize=6.5, color=GRIS, va="center")
    l1 = sal / "lamina1_consolidado.png"; fig.savefig(l1, facecolor="white"); plt.close(fig)

    # ---------------- lámina 2 · la comunidad frente a X y frente a Y (cambio climático)
    salida = {"zona": zona, "corrida_X": c["id"], "radio_buffer_m": radio_m, "celda_m": celda, "marcas_en_dominio": N, "contraste_X": {k: v for k, v in res.items() if k not in ("nota",)},
              "lamina1": str(l1), "lamina2": None, "contraste_Y": [], "fondo": base, "nota_corrida_x": nota_x}
    ys = [] if c["Y"] else _y_par(corridas(carpeta), c)
    if ys:
        paneles = [(c, res, h, "Blues", NAVY, f"X · condiciones actuales · {tr_txt}")]
        for yc in ys[:2]:
            fy = _muestrear(yc, ms); ry = _resumen(yc, fy); hy, by, _ = _leer_h(yc["hmax"])
            paneles.append((yc, ry, hy, LinearSegmentedColormap.from_list("mag", ["#F7D7E8", "#E07AB0", "#A3195B", "#5E0B34"]), MAGENTA, f"Y · cambio climático {yc['horizonte'] or ''} · SSP5-8.5"))
            salida["contraste_Y"].append({k: v for k, v in ry.items() if k != "nota"})
        n = len(paneles); anc = .96 / n; ratio = (e[2] - e[0]) / (e[3] - e[1])
        mh = (anc - .012) * 13.33 / ratio; H = 1.2 + mh + 1.8                      # alto justo: sin franjas en blanco
        fy_ = lambda d: 1 - d / H
        fig = plt.figure(figsize=(13.33, H), dpi=200, facecolor="white")
        _cabecera(fig, f"Validación social con cambio climático · {zona}", "La comunidad frente al modelo: hoy (X) y con cambio climático (Y)",
                  f"Mismas {N} marcas sobre el calado máximo de cada corrida · {tr_txt} · Y = CMIP6 SSP5-8.5 bajo supuesto, sin calibrar", "UCEclima Lambda", der2, H=H)
        maps = {}
        for k, (cc, rr, hh, cmap, col, tit) in enumerate(paneles):
            ax = fig.add_axes([.02 + k * anc, fy_(1.2 + mh), anc - .012, mh / H]); ax.set_xlim(e[0], e[2]); ax.set_ylim(e[1], e[3]); ax.set_aspect("equal")
            _fondo(ax, crs, fondo); ax.set_xticks([]); ax.set_yticks([])
            for s_ in ax.spines.values(): s_.set_edgecolor(col); s_.set_linewidth(2)
            bb = b if cc is c else _leer_h(cc["hmax"])[1]
            maps[col] = cmap
            ax.imshow(hh, extent=(bb.left, bb.right, bb.bottom, bb.top), cmap=cmap, vmin=0, vmax=2, alpha=.85, zorder=3, interpolation="nearest")
            for zg in zon or []: _contorno(ax, zg, color=NAVY, lw=.8, ls="--", zorder=4)
            _dibujar_marcas(ax, geoms, max(N, 9), numerar=False); _norte_escala(ax, e, celda)
            ax.set_title(tit, fontsize=9.5, weight="bold", color=col, loc="left")
            area = cc.get("area_ge_0.5_km2")
            t1 = f"Detección {rr['aciertos']}/{rr['aciertos'] + rr['omisiones']}" + (f" · falsas alarmas {rr['falsas_alarmas']}" if (rr["falsas_alarmas"] + rr["aciertos_secos"]) else " · sin marcas «no se inunda»")
            t2 = f"Lluvia {cc['P_mm']:g} mm" + (f" · área ≥ 0,5 m: {float(area):.2f} km²" if area is not None else "")
            x0 = .02 + k * anc; d0 = 1.2 + mh + .12
            fig.text(x0, fy_(d0), t1, fontsize=8.5, weight="bold", color=col, va="top"); fig.text(x0, fy_(d0 + .24), t2, fontsize=7.5, color=GRIS, va="top")
            fig.text(x0, fy_(d0 + .44), "Altura declarada frente al modelo: coincide {coincide} · subestima {el modelo subestima} · sobreestima {el modelo sobreestima}".format(**rr["altura"]), fontsize=7.2, color=GRIS, va="top")
        for k, (col, cmap) in enumerate(maps.items()):
            cax = fig.add_axes([.2 + k * .33, fy_(H - .5), .26, .1 / H])
            cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=matplotlib.colors.Normalize(0, 2)), cax=cax, orientation="horizontal")
            cb.set_label("Calado máximo (m) · " + ("X, condiciones actuales" if col == NAVY else "Y, cambio climático"), fontsize=7, color=col); cb.ax.xaxis.set_label_position("top"); cb.ax.tick_params(labelsize=6.5)
        fig.text(.02, fy_(H - .05), "Marcas: círculo = «se inunda» (color = altura declarada, anillo oscuro = todos los años), cuadrado azul = «no se inunda». Contraste con conocimiento local, no validación física; Y es una proyección bajo supuesto.", fontsize=6.5, color=GRIS, va="bottom")
        l2 = sal / "lamina2_X_vs_Y_cambio_climatico.png"; fig.savefig(l2, facecolor="white"); plt.close(fig); salida["lamina2"] = str(l2)
    (sal / "resumen.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {**salida, "carpeta": str(sal)}


def estado(carpeta):
    carpeta = Path(carpeta); prod = carpeta / "productos" / "12_validacion_campo"
    enc = _por_fecha(prod.glob("encuesta_*/encuesta.json")) if prod.exists() else []
    con = _por_fecha(prod.glob("contraste_*/resumen.json")) if prod.exists() else []
    lam = _por_fecha(prod.glob("laminas_*/resumen.json")) if prod.exists() else []
    ms = marcas(carpeta)
    return {"corridas": [{k: v for k, v in c.items() if k != "hmax"} for c in corridas(carpeta)],
            "encuestas": [{**json.loads(f.read_text(encoding="utf-8")), "carpeta": str(f.parent)} for f in enc][-5:],
            "marcas": len(ms), "se_inunda": sum(m["properties"]["resultado"] == "SE INUNDA" for m in ms),
            "ultimo_contraste": {**json.loads(con[-1].read_text(encoding="utf-8")), "carpeta": str(con[-1].parent)} if con else None,
            "ultimas_laminas": {**json.loads(lam[-1].read_text(encoding="utf-8")), "carpeta": str(lam[-1].parent)} if lam else None}
