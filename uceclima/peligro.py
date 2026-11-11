# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Mapas de CALADO, VELOCIDAD y PELIGRO de una corrida (botón del módulo 8 y de «Resultados y entregas»).

Parte de la herramienta externa `mapas_peligro.py` de Eta y la integra al programa. Lee lo que el núcleo ya deja en cada corrida (hmax.tif, vmax.tif),
el terreno QUE USÓ ESA CORRIDA (su entrada.json; no el actual del proyecto, que puede ser otro MDT) y las vías y edificios de OSM, y escribe en
<proyecto>/productos/13_peligro/<corrida>_<sello>/ (carpeta nueva; nada se sobrescribe):
  · lamina_calado_velocidad_peligro.png (3 paneles con OSM, norte y escala; mar o agua permanente en turquesa)
  · calado/, velocidad/, peligro/: cada variable con su GeoTIFF, su PNG y su shapefile por clases (UTM y WGS84, más GeoPackage)
  · resumen_peligro.csv (km² y edificios OSM por clase) y LEEME.md
Peligro = calado × velocidad (m²/s) con los máximos de cada celda (no ocurren a la vez: cota superior). Clases de Australian Rainfall and Runoff 2019
(Smith et al. 2014): h·v < 0,3 bajo · 0,3–0,6 niños y autos · 0,6–1,2 adultos · > 1,2 extremo. Resultados sin calibrar ni validar."""
import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

CL_PELIGRO = [0.0, 0.3, 0.6, 1.2, 1e9]
NOM_PELIGRO = ["bajo (< 0,3)", "niños y autos (0,3–0,6)", "adultos (0,6–1,2)", "extremo (> 1,2)"]
CL_VEL = [(0.0, 0.5, "< 0,5 m/s"), (0.5, 1.0, "0,5–1 m/s"), (1.0, 2.0, "1–2 m/s"), (2.0, 1e9, "> 2 m/s")]
CL_CALADO = [(0.05, 0.3, "0,05–0,3 m"), (0.3, 0.5, "0,3–0,5 m"), (0.5, 1.0, "0,5–1 m"), (1.0, 2.0, "1–2 m"), (2.0, 1e9, "> 2 m")]
UMBRAL_MOJADO = 0.05                                            # m: una celda con menos de 5 cm no se considera mojada
AVISO = "Resultados sin calibrar ni validar: no son predicción ni huella de inundación observada."
TURQ = "#3fd0c9"


class PeligroError(ValueError):
    pass


def corridas_con_resultados(proyecto):
    """Corridas del proyecto que tienen hmax.tif (las únicas de las que se pueden sacar mapas)."""
    return [d.name for d in sorted((Path(proyecto) / "resultados").glob("corrida_*")) if list(d.glob("salida/*/hmax.tif"))]


# ------------------------------------------------------------------------------------------------ lectura
def _terreno_de_la_corrida(proy, run_dir):
    """El MDT que USÓ la corrida (entrada.json); si no está, el del proyecto. Una corrida con DSM no se rotula con FABDEM."""
    try:
        dem = json.loads((run_dir / "entrada.json").read_text(encoding="utf-8")).get("config", {}).get("dem")
    except Exception:
        dem = None
    if not dem:
        cfg = json.loads((proy / "config_climanet.json").read_text(encoding="utf-8")); dem = cfg.get("dem")
    if not dem:
        raise PeligroError("No encuentro el terreno de la corrida.")
    p = Path(dem)
    return p if p.is_absolute() else proy / p


def _osm(proy, tf, T):
    """Vías y edificios de OpenStreetMap que ya bajó el programa (datos_descargados/osm_*), en coordenadas de celda."""
    ds = [d for d in sorted((proy / "datos_descargados").glob("osm_*"), reverse=True) if (d / "vias.json").exists()]
    if not ds:
        return [], []
    pix = lambda xs, ys: ((np.array(xs) - T.c) / T.a, (np.array(ys) - T.f) / T.e)

    def lee(n):
        f = ds[0] / n
        return json.loads(f.read_text(encoding="utf-8")).get("elements", []) if f.exists() else []
    vias = [(pix(*tf.transform([p["lon"] for p in e["geometry"]], [p["lat"] for p in e["geometry"]])), (e.get("tags") or {}).get("highway", "")) for e in lee("vias.json") if len(e.get("geometry") or []) > 1]
    edif = [pix(*tf.transform([p["lon"] for p in e["geometry"]], [p["lat"] for p in e["geometry"]])) for e in lee("edificios.json") if len(e.get("geometry") or []) > 3]
    return vias, edif


def _mascara_mar(dem):
    """Mar o agua permanente al nivel del mar (cota ≤ 1 m), solo si de verdad hay mar en el dominio (> 1 % de celdas): el modelo les pone lluvia y calado,
    pero no son inundación terrestre. En el continente (sin celdas a nivel del mar) no se enmascara nada."""
    if np.isfinite(dem).any() and np.nanmin(dem) < 1.0 and np.mean(dem <= 1.0) > 0.01:
        return ~(dem > 1.0)
    return np.zeros(dem.shape, bool)


# ------------------------------------------------------------------------------------------------ dibujo
def _dibujar(ax, fig, capa, h, v, hv, moj, mar, hs, vias, edif, T, lim):
    from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap
    agua = LinearSegmentedColormap.from_list("a", ["#cfeefa", "#5fc0ec", "#1a78c8", "#0a2f7a"]); peli = ListedColormap(["#ffe08a", "#ff9f40", "#e8433a", "#6b0f1a"])
    ax.imshow(hs, cmap="gray", alpha=.6)
    if mar.any():
        ax.imshow(np.where(mar, 1, np.nan), cmap=ListedColormap([TURQ]), alpha=.85)
    if capa == "h":
        im = ax.imshow(np.where(moj, h, np.nan), cmap=agua, vmin=UMBRAL_MOJADO, vmax=max(1.0, float(np.nanpercentile(h[moj], 98)) if moj.any() else 1), alpha=.92)
        fig.colorbar(im, ax=ax, shrink=.62, orientation="horizontal", pad=.03)
    elif capa == "v":
        im = ax.imshow(np.where(moj, v, np.nan), cmap="plasma", vmin=0, vmax=3, alpha=.92); fig.colorbar(im, ax=ax, shrink=.62, orientation="horizontal", pad=.03)
    else:
        im = ax.imshow(np.where(moj, hv, np.nan), cmap=peli, norm=BoundaryNorm(CL_PELIGRO[:4] + [100], 4), alpha=.95)
        cb = fig.colorbar(im, ax=ax, shrink=.62, orientation="horizontal", pad=.03, ticks=[0.15, 0.45, 0.9, 1.5]); cb.ax.set_xticklabels(["bajo", "niños/autos", "adultos", "extremo"], fontsize=8)
    for cc, rr in edif:
        ax.fill(cc, rr, facecolor="none", edgecolor="#333333", lw=0.25)
    for (cc, rr), hw in vias:
        pr = hw in ("primary", "secondary", "tertiary", "trunk", "motorway"); ax.plot(cc, rr, color="#e0a100" if pr else "#444444", lw=1.3 if pr else 0.45, alpha=.9)
    ax.set_xlim(lim[0], lim[1]); ax.set_ylim(lim[3], lim[2]); ax.set_xticks([]); ax.set_yticks([])
    km = 1000 / abs(T.a); x0 = lim[0] + (lim[1] - lim[0]) * 0.06; y0 = lim[3] - (lim[3] - lim[2]) * 0.05
    ax.plot([x0, x0 + km], [y0, y0], color="k", lw=4); ax.text(x0 + km / 2, y0 - (lim[3] - lim[2]) * 0.02, "1 km", ha="center", fontsize=9)
    ax.annotate("N", xy=(0.93, 0.95), xytext=(0.93, 0.86), xycoords="axes fraction", ha="center", fontsize=12, fontweight="bold", arrowprops=dict(arrowstyle="-|>", color="k"))


def _leyenda(ax, mar, hay_osm):
    from matplotlib.patches import Patch
    leg = ([Patch(facecolor="none", edgecolor="#333", label="edificios OSM"), Patch(color="#e0a100", label="vías principales OSM")] if hay_osm else []) + ([Patch(color=TURQ, label="mar / agua permanente (no es inundación)")] if mar.any() else [])
    if leg:
        ax.legend(handles=leg, loc="upper left", fontsize=8, framealpha=.9)


# ------------------------------------------------------------------------------------------------ shapes y rásteres
def _escribir_tif(ruta, arr, prof, nodata=-9999.0):
    import rasterio
    p2 = dict(prof); p2.update(dtype="float32", count=1, nodata=nodata, compress="deflate")
    with rasterio.open(ruta, "w", **p2) as w:
        w.write(np.where(np.isfinite(arr), arr, nodata).astype("float32"), 1)


def _shape_clases(valores, mascara, clases, T, crs, carpeta, nombre, campo, archivos):
    """Polígonos disueltos por clase (shapefile UTM y WGS84 + GeoPackage)."""
    import geopandas as gpd
    from rasterio.features import shapes
    from shapely.geometry import shape
    from .entregas import _capa
    cl = np.zeros(valores.shape, dtype="int16")
    for i, (lo, hi, _) in enumerate(clases, start=1):
        cl[mascara & (valores >= lo) & (valores < hi)] = i
    geoms = [(shape(g), int(k)) for g, k in shapes(cl, mask=cl > 0, transform=T)]
    if not geoms:
        return 0.0
    gdf = gpd.GeoDataFrame({"clase": [clases[k - 1][2] for _, k in geoms], campo: [clases[k - 1][0] for _, k in geoms]}, geometry=[g for g, _ in geoms], crs=crs).dissolve(by="clase", as_index=False)
    gdf["area_km2"] = gdf.geometry.area / 1e6
    _capa(gdf, carpeta, nombre, archivos, crs)
    return float(gdf["area_km2"].sum())


# ------------------------------------------------------------------------------------------------ una corrida
def _una(proy, run, zoom=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rasterio
    from matplotlib.colors import LightSource
    from pyproj import Transformer
    from rasterio.warp import Resampling, reproject
    run_dir = proy / "resultados" / run
    sal = sorted((run_dir / "salida").glob("*/hmax.tif"))
    if not sal:
        raise PeligroError(f"La corrida {run} no tiene hmax.tif (¿terminó bien?).")
    d = sal[0].parent
    with rasterio.open(d / "hmax.tif") as s:
        h = s.read(1).astype(float); T = s.transform; crs = s.crs; prof = s.profile
    v = rasterio.open(d / "vmax.tif").read(1).astype(float) if (d / "vmax.tif").exists() else np.zeros_like(h)
    h[~np.isfinite(h)] = 0; v[~np.isfinite(v)] = 0
    dem_f = _terreno_de_la_corrida(proy, run_dir); dem = np.full(h.shape, np.nan)
    with rasterio.open(dem_f) as s:
        reproject(rasterio.band(s, 1), dem, dst_transform=T, dst_crs=crs, resampling=Resampling.bilinear, dst_nodata=np.nan)
    mar = _mascara_mar(dem); moj = (~mar) & (h >= UMBRAL_MOJADO); hv = np.where(moj, h * v, 0.0)
    out = proy / "productos" / "13_peligro" / f"{run}_{datetime.now():%Y%m%d_%H%M%S}"; out.mkdir(parents=True)
    archivos = []; tf = Transformer.from_crs("EPSG:4326", str(crs), always_xy=True); vias, edif = _osm(proy, tf, T)
    cel = abs(T.a * T.e) / 1e6
    # --- rásteres y shapefiles por variable
    for carpeta, nombre, arr, clases, campo in (("calado", "calado_max_m", h, CL_CALADO, "calado_min"), ("velocidad", "velocidad_max_ms", v, CL_VEL, "vel_min"),
                                                  ("peligro", "peligro_hv_m2s", hv, [(CL_PELIGRO[k], CL_PELIGRO[k + 1], NOM_PELIGRO[k]) for k in range(4)], "hv_min")):
        (out / carpeta).mkdir(exist_ok=True)
        _escribir_tif(out / carpeta / f"{nombre}.tif", np.where(moj, arr, np.nan), prof); archivos.append(out / carpeta / f"{nombre}.tif")
        _shape_clases(arr, moj, clases, T, crs, out / carpeta, nombre.split("_")[0] + "_clases", campo, archivos)
    # --- resumen por clase de peligro (km² y edificios)
    filas = [{"clase": NOM_PELIGRO[k], "area_tierra_km2": round(float((moj & (hv >= CL_PELIGRO[k]) & (hv < CL_PELIGRO[k + 1])).sum() * cel), 3)} for k in range(4)]
    if edif:
        cls = np.zeros(4, int)
        for cc, rr in edif:
            i, j = int(round(float(np.mean(rr)))), int(round(float(np.mean(cc))))
            if 0 <= i < h.shape[0] and 0 <= j < h.shape[1] and moj[i, j]:
                cls[int(np.searchsorted(CL_PELIGRO, hv[i, j], side="right") - 1)] += 1
        for k in range(4):
            filas[k]["edificios_osm"] = int(cls[k])
    with open(out / "resumen_peligro.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys())); w.writeheader(); w.writerows(filas)
    archivos.append(out / "resumen_peligro.csv")
    # --- láminas
    hs = LightSource(315, 40).hillshade(np.nan_to_num(dem, nan=np.nanmin(dem) if np.isfinite(dem).any() else 0), vert_exag=3)
    lim = (0, h.shape[1], 0, h.shape[0])
    if zoom:
        xs, ys = tf.transform([zoom[0], zoom[2]], [zoom[1], zoom[3]]); cx = (np.array(xs) - T.c) / T.a; cy = (np.array(ys) - T.f) / T.e
        lim = (max(0, min(cx)), min(h.shape[1], max(cx)), max(0, min(cy)), min(h.shape[0], max(cy)))
    nombre_proy = json.loads((proy / "proyecto_uceclima.json").read_text(encoding="utf-8")).get("nombre", proy.name)
    titulos = {"h": "Calado máximo (m)", "v": "Velocidad máxima (m/s)", "hv": "Peligro calado × velocidad (m²/s)"}
    fig, ax = plt.subplots(1, 3, figsize=(20, 7.6))
    for a, capa in zip(ax, ("h", "v", "hv")):
        _dibujar(a, fig, capa, h, v, hv, moj, mar, hs, vias, edif, T, lim); a.set_title(titulos[capa], color="#1F4E79", fontsize=12)
    _leyenda(ax[0], mar, bool(vias or edif))
    fig.suptitle(f"{nombre_proy} · {run} · calado, velocidad y peligro · UCEclima Lambda", color="#1F4E79", fontsize=14)
    fig.text(0.01, 0.01, "Peligro: Australian Rainfall and Runoff 2019 · h·v con los máximos de cada celda (no simultáneos): cota superior · resultados sin calibrar ni validar", fontsize=8.5, color="grey")
    plt.tight_layout(rect=[0, .03, 1, .95]); fig.savefig(out / "lamina_calado_velocidad_peligro.png", dpi=125, facecolor="white"); plt.close(fig); archivos.append(out / "lamina_calado_velocidad_peligro.png")
    for capa, carpeta, nombre in (("h", "calado", "calado_max_m"), ("v", "velocidad", "velocidad_max_ms"), ("hv", "peligro", "peligro_hv_m2s")):
        fig, a = plt.subplots(figsize=(9.5, 8)); _dibujar(a, fig, capa, h, v, hv, moj, mar, hs, vias, edif, T, lim); _leyenda(a, mar, bool(vias or edif))
        a.set_title(f"{titulos[capa]} · {nombre_proy}", color="#1F4E79", fontsize=12); fig.text(0.01, 0.01, AVISO, fontsize=8, color="#b00020")
        plt.tight_layout(rect=[0, .03, 1, 1]); fig.savefig(out / carpeta / f"{nombre}.png", dpi=130, facecolor="white"); plt.close(fig); archivos.append(out / carpeta / f"{nombre}.png")
    (out / "LEEME.md").write_text(
        f"# Calado, velocidad y peligro · {run}\n\nGenerado {datetime.now():%Y-%m-%d %H:%M} por UCEclima Lambda desde hmax.tif y vmax.tif de la corrida y el terreno que ella usó ({dem_f.name}).\n\n"
        + "\n".join(f"- {f['clase']}: {f['area_tierra_km2']} km²" + (f", {f['edificios_osm']} edificios OSM" if "edificios_osm" in f else "") for f in filas)
        + f"\n\n- calado/, velocidad/, peligro/: GeoTIFF, PNG y shapefile por clases (UTM y WGS84, más GeoPackage).\n- Celda mojada: calado ≥ {UMBRAL_MOJADO} m."
        + (" Mar o agua permanente (cota ≤ 1 m) excluida." if mar.any() else "") + "\n\nPeligro = calado × velocidad con los máximos de cada celda (no ocurren a la vez: cota superior). Clases de Australian Rainfall and Runoff 2019 "
        "(Smith et al. 2014). " + AVISO + "\n", encoding="utf-8")
    archivos.append(out / "LEEME.md")
    return {"id": run, "carpeta": str(out), "lamina": str(out / "lamina_calado_velocidad_peligro.png"), "archivos": len(archivos), "resumen": filas, "terreno": dem_f.name,
            "mar_excluido": bool(mar.any()), "area_mar_km2": round(float(mar.sum() * cel), 2), "aviso": AVISO}


def generar(proyecto, run=None, zoom=None):
    """`run`: id de corrida, «todas» o None (= la última con resultados). `zoom`: [lon_min, lat_min, lon_max, lat_max] para acercar la lámina."""
    proy = Path(proyecto); todas = corridas_con_resultados(proy)
    if not todas:
        raise PeligroError("El proyecto no tiene corridas con resultados (hmax.tif). Ejecuta primero una corrida en el módulo 7.")
    if run in (None, ""):
        elegidas = [todas[-1]]
    elif run == "todas":
        elegidas = todas
    elif run in todas:
        elegidas = [run]
    else:
        raise PeligroError("Esa corrida no existe o no tiene resultados.")
    if zoom is not None and (len(zoom) != 4 or not (zoom[0] < zoom[2] and zoom[1] < zoom[3])):
        raise PeligroError("El acercamiento necesita lon_min, lat_min, lon_max, lat_max (con el mínimo menor que el máximo).")
    return {"corridas": [_una(proy, r, zoom) for r in elegidas], "carpeta_base": str(proy / "productos" / "13_peligro")}
