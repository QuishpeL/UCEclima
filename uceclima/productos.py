# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Zeta Z4 · Productos ordenados por módulo.

Cada módulo deja sus productos en <proyecto>/productos/NN_modulo/ con la misma estructura:
  shapes/   capas vectoriales (.shp con sus archivos, .gpkg, .geojson)
  figuras/  .png / .jpg / .svg
  csv/      tablas (.csv, .xlsx)
  rasters/  .tif
  registro/ procedencia en .json (manifiestos, decisiones, resúmenes)
  informe.md e informe.html  (qué hay, de dónde sale y las cifras clave)
y productos/index.html enlaza todos los módulos.

Reglas: son COPIAS ordenadas (los originales quedan donde los dejó cada módulo); nada se sobrescribe: si un archivo con el mismo nombre ya existe y
su contenido cambió, la nueva versión se guarda con sello de tiempo. Los resultados siguen siendo no calibrados ni validados salvo que el proyecto diga lo contrario."""
import hashlib, html, json, shutil
from datetime import datetime
from pathlib import Path

MODULOS = [  # (carpeta, título, [(patrón glob relativo al proyecto, prefijo por carpeta padre)])
    ("01_proyecto", "Proyecto y zona de estudio", ["proyecto_uceclima.json", "config_climanet.json", "zona_estudio/*", "registro/estaciones_referencia.json"]),
    ("02_descargas", "Descargas (Earth Engine y servicios públicos)", ["datos_descargados/*/manifiesto.json", "datos_descargados/*/*/manifiesto.json", "datos_descargados/*/suelo/*.png",
                                                                       "datos_descargados/*/*.png"]),
    ("03_lluvia", "Lluvia: estaciones y CHIRPS", ["datos/estaciones/*.csv", "datos_descargados/*/chirps/chirps_diario.csv", "datos_descargados/chirps_*/chirps_diario.csv",
                                                  "datos_descargados/*/chirps/graficos/*", "datos_descargados/chirps_*/graficos/*", "datos/series_premodulo/*.csv"]),
    ("04_idf", "Lluvia de diseño (IDF)", ["registro/idf/*.csv", "registro/idf/*.json", "registro/idf_x/*/*", "registro/idf_x/*"]),
    ("05_terreno", "Terreno", ["registro/terreno_preview.png", "registro/terreno_historial.json", "datos_descargados/*/mdt/manifiesto.json"]),
    ("06_cuenca", "Cuenca", ["cuenca/activa.json", "cuenca/*/*"]),
    ("07_calibracion", "Hidrología y calibración", ["calibracion/barridos/*/*.csv", "calibracion/barridos/*/config.json", "calibracion/aceptadas/*/*", "calibracion/*.csv",
                                                    "calibracion/observaciones/*.json", "calibracion/benchmark/*/*"]),
    ("08_corridas_2D", "Corridas 2D (land)", ["resultados/corrida_*/entrada.json", "resultados/corrida_*/salida/*/*"]),
    ("09_cmip6", "Cambio climático CMIP6 (Y, SSP5-8.5)", ["registro/cmip6_decision.json", "registro/cmip6/analisis_*/*", "registro/cmip6/hallazgos_papers_*/*"]),
    ("10_papers", "Receta de los papers (fuente de lluvia según el uso)", ["papers/*/*"]),
    ("11_entregas", "Entregas", ["entregas/*/manifiesto.json", "entregas/*/informe.html"]),
]
RUTAS = {  # ruta de la API que produce algo → módulos que se regeneran
    "/api/proyecto/crear": ["01_proyecto", "06_cuenca"], "/api/sitio/nuevo": ["01_proyecto"], "/api/proyecto/sitio": ["01_proyecto"],
    "/api/descargas/iniciar": ["02_descargas"], "/api/estaciones/importar": ["03_lluvia"], "/api/prep/a_proyecto": ["03_lluvia"], "/api/prep/registrar_estacion": ["03_lluvia"],
    "/api/idf/x/guardar": ["04_idf"], "/api/idf/propia": ["04_idf"], "/api/idf/desde_chirps": ["04_idf"], "/api/terreno/registrar": ["05_terreno"], "/api/terreno/gee": ["05_terreno"], "/api/terreno/quemar_rios": ["05_terreno"],
    "/api/cuenca/shape": ["06_cuenca"], "/api/cuenca/activar": ["06_cuenca"], "/api/cuenca/malla": ["06_cuenca"],
    "/api/calibracion/registrar": ["07_calibracion"], "/api/calibracion/lluvia_areal": ["07_calibracion"], "/api/calibracion/barrido": ["07_calibracion"],
    "/api/calibracion/aceptar": ["07_calibracion"], "/api/calibracion/benchmark": ["07_calibracion"],
    "/api/cmip6/asumir_baseline": ["09_cmip6"], "/api/cmip6/evaluar": ["09_cmip6"], "/api/cmip6/factores": ["09_cmip6"],
    "/api/papers/receta": ["10_papers"], "/api/cmip6/papers": ["09_cmip6"], "/api/entregas/construir": ["11_entregas"], "corrida": ["08_corridas_2D"], "descarga": ["02_descargas", "03_lluvia", "05_terreno", "09_cmip6"],
}
TIPO = {".shp": "shapes", ".shx": "shapes", ".dbf": "shapes", ".prj": "shapes", ".cpg": "shapes", ".gpkg": "shapes", ".geojson": "shapes", ".kml": "shapes",
        ".png": "figuras", ".jpg": "figuras", ".jpeg": "figuras", ".svg": "figuras", ".csv": "csv", ".xlsx": "csv", ".tif": "rasters", ".tiff": "rasters",
        ".json": "registro", ".md": "registro", ".txt": "registro", ".html": "registro", ".log": "registro"}
MAX_MB = 200                                                   # un ráster enorme no se duplica: se enlaza en el informe


def _sha(f, n=1 << 20):
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for b in iter(lambda: fh.read(n), b""):
            h.update(b)
    return h.hexdigest()


def _nombre(rel):
    """Nombre plano y único a partir de la ruta relativa: carpetas intermedias como prefijo (barrido_X__resultados.csv)."""
    partes = Path(rel).parts
    pref = [p for p in partes[1:-1] if p not in ("salida", "graficos", "chirps", "mdt", "suelo")]
    return "__".join(pref[-2:] + [partes[-1]]) if pref else partes[-1]


def _copiar(src, dst, enlazados):
    if src.stat().st_size > MAX_MB * 1e6:
        enlazados.append(str(src)); return None
    if dst.exists():
        if dst.stat().st_size == src.stat().st_size and _sha(dst) == _sha(src):
            return dst
        dst = dst.with_name(f"{dst.stem}_{datetime.now():%Y%m%d_%H%M%S}{dst.suffix}")          # nada se sobrescribe
    dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    return dst


def _cifras(f):
    """Cifras clave (escalares de primer nivel) de un JSON de resumen, para el informe."""
    try:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    src = d.get("resumen") if isinstance(d.get("resumen"), dict) else d
    return {k: v for k, v in src.items() if isinstance(v, (int, float, str)) and not isinstance(v, bool) and len(str(v)) < 140}


def generar(carpeta, datos=None, modulos=None):
    """Ordena los productos de los módulos pedidos (o de todos). Devuelve {módulo: {tipo: n archivos}}."""
    P = Path(carpeta); raiz = P / "productos"; raiz.mkdir(exist_ok=True)
    nombre = (datos or {}).get("nombre") or P.name
    hechos = {}
    for mod, titulo, pats in MODULOS:
        if modulos and mod not in modulos:
            continue
        dst = raiz / mod; cuenta = {}; filas = []; enlazados = []; cifras = {}
        vistos = set()
        for pat in pats:
            for f in sorted(P.glob(pat)):
                if not f.is_file() or f.suffix.lower() not in TIPO or "productos" in f.relative_to(P).parts or f.suffix.endswith("bak") or f in vistos:
                    continue
                vistos.add(f); tipo = TIPO[f.suffix.lower()]; rel = f.relative_to(P)
                nom = f.name if tipo == "shapes" else _nombre(rel)
                if tipo == "shapes" and f.parent.name not in ("zona_estudio",):
                    nom = f"{f.parent.name}__{f.name}"
                c = _copiar(f, dst / tipo / nom, enlazados)
                if c is None:
                    continue
                cuenta[tipo] = cuenta.get(tipo, 0) + 1
                filas.append((tipo, str(c.relative_to(dst)).replace("\\", "/"), str(rel).replace("\\", "/")))
                if f.suffix.lower() == ".json" and any(k in f.name for k in ("resumen", "aceptacion", "decision", "activa", "idf_propia", "manifiesto")):
                    cifras[str(rel).replace("\\", "/")] = _cifras(f)
        if not filas and not enlazados:
            continue
        _informe(dst, mod, titulo, nombre, filas, enlazados, cifras)
        hechos[mod] = cuenta
    _indice(raiz, nombre)
    return hechos


def _informe(dst, mod, titulo, nombre, filas, enlazados, cifras):
    sello = datetime.now().isoformat(timespec="seconds")
    md = [f"# {mod[3:].replace('_', ' ').capitalize()} · {titulo}", "", f"Proyecto: **{nombre}** · generado {sello} por UCEclima Lambda.", "",
          "Copias ordenadas de los productos del módulo; los originales siguen en la carpeta del proyecto (columna «origen»).",
          "Resultados no calibrados ni validados salvo que el proyecto declare lo contrario.", ""]
    for tipo in ("figuras", "shapes", "csv", "rasters", "registro"):
        l = [f for f in filas if f[0] == tipo]
        if l:
            md += [f"## {tipo.capitalize()} ({len(l)})", "", "| Archivo | Origen |", "|---|---|"] + [f"| `{a}` | `{o}` |" for _, a, o in l] + [""]
    if enlazados:
        md += ["## Archivos grandes enlazados (no copiados)", ""] + [f"- `{e}`" for e in enlazados] + [""]
    if cifras:
        md += ["## Cifras clave", ""]
        for f, c in cifras.items():
            if c:
                md += [f"**{f}**", ""] + [f"- {k}: {v}" for k, v in list(c.items())[:25]] + [""]
    (dst / "informe.md").write_text("\n".join(md), encoding="utf-8")
    figs = "".join(f'<figure><img src="{html.escape(a)}" loading="lazy"><figcaption>{html.escape(Path(a).name)}</figcaption></figure>' for t, a, _ in filas if t == "figuras")
    tabla = "".join(f"<tr><td>{t}</td><td><a href=\"{html.escape(a)}\">{html.escape(a)}</a></td><td><code>{html.escape(o)}</code></td></tr>" for t, a, o in filas if t != "figuras")
    cif = "".join(f"<h3>{html.escape(f)}</h3><table>" + "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in list(c.items())[:25]) + "</table>" for f, c in cifras.items() if c)
    (dst / "informe.html").write_text(_html(f"{titulo} · {nombre}", f"<p class=s>Generado {sello} · UCEclima Lambda · copias ordenadas; originales en el proyecto. "
                                            f"Resultados no calibrados ni validados salvo declaración expresa.</p><div class=g>{figs}</div><h2>Archivos</h2><table><tr><th>Tipo</th><th>Archivo</th><th>Origen</th></tr>{tabla}</table>{cif}"),
                                      encoding="utf-8")


def _indice(raiz, nombre):
    mods = [d for d in sorted(raiz.iterdir()) if d.is_dir() and (d / "informe.html").exists()]
    tit = {m: t for m, t, _ in MODULOS}
    filas = "".join(f'<tr><td><a href="{d.name}/informe.html">{d.name}</a></td><td>{html.escape(tit.get(d.name, ""))}</td>'
                    f'<td>{" · ".join(f"{k}: {sum(1 for _ in (d / k).iterdir())}" for k in ("figuras", "shapes", "csv", "rasters", "registro") if (d / k).exists())}</td></tr>' for d in mods)
    (raiz / "index.html").write_text(_html(f"Productos · {nombre}", f"<p class=s>UCEclima Lambda · {datetime.now():%Y-%m-%d %H:%M} · un informe por módulo, en el orden del flujo de trabajo.</p>"
                                           f"<table><tr><th>Módulo</th><th>Contenido</th><th>Archivos</th></tr>{filas}</table>"), encoding="utf-8")
    (raiz / "LEEME.md").write_text(f"# Productos de {nombre}\n\nAbrir `index.html`. Cada carpeta NN_modulo tiene shapes/, figuras/, csv/, rasters/, registro/ e informe (md y html).\n"
                                   "Son copias ordenadas: los originales siguen en el proyecto. Nada se sobrescribe (las versiones nuevas llevan sello de tiempo).\n", encoding="utf-8")


def _html(titulo, cuerpo):
    return ("<!doctype html><html lang=es><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>" + html.escape(titulo) + "</title>"
            "<style>body{font-family:'Calibri Light',Calibri,Segoe UI,sans-serif;margin:24px auto;max-width:1100px;padding:0 16px;color:#1d2b3a}h1{color:#1F4E79;border-bottom:2px solid #2E75B6}"
            "h2,h3{color:#2E75B6}table{border-collapse:collapse;width:100%;margin:8px 0}td,th{border:1px solid #c9d7e8;padding:4px 8px;text-align:left;font-size:14px}th{background:#eaf1fb}"
            ".s{color:#5b6b7c}.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}figure{margin:0;border:1px solid #c9d7e8;padding:6px;background:#fff}"
            "img{max-width:100%}figcaption{font-size:12px;color:#5b6b7c}code{font-size:12px}</style><h1>" + html.escape(titulo) + "</h1>" + cuerpo + "</html>")


def tras_ruta(carpeta, datos, ruta):
    """Se llama después de una ruta de la API que produjo algo; regenera solo los módulos afectados."""
    mods = RUTAS.get(ruta)
    return generar(carpeta, datos, mods) if mods else None
