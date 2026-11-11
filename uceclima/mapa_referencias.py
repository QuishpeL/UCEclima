# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Epsilon · mapa de la corrida 2D con referencias (método de los mapas de Machala/Gualaquiza/Portoviejo, CLIMALAB):
imagen satelital (Esri World Imagery), calado suavizado SOLO para visualización, calles, huellas de edificios (expuestos en rojo:
≥ 0,5 m y ≥ 1 m), salud, educación, seguridad, gobierno y lugares de OpenStreetMap, salida de la cuenca, norte, escala y leyenda.
Calcula además la EXPOSICIÓN (edificios e instalaciones por calado) → exposicion.xlsx y edificios_expuestos.gpkg.
OSM se descarga una vez por proyecto y zona (Overpass, datos públicos ODbL) y queda en datos_descargados/osm_<sello>/. Nada se inventa:
si OSM no tiene edificios o equipamiento en la zona, el mapa lo dice."""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

OVERPASS = "https://overpass-api.de/api/interpreter"
ICON = {"salud": ("P", "#c0392b", 34, "Salud (hospital/clínica)"), "educacion": ("s", "#3d6fb6", 12, "Educación"),          # Omega: íconos pequeños y tonos sobrios
        "seguridad": ("D", "#d68910", 14, "Policía / bomberos"), "gobierno": ("*", "#7d5ba6", 30, "Gobierno / municipio")}


class MapaError(ValueError):
    pass


def _bbox_lonlat(T, shape, crs):
    from pyproj import Transformer
    ny, nx = shape; tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    xs = [T.c, T.c + T.a * nx]; ys = [T.f, T.f + T.e * ny]; lo, la = tr.transform([xs[0], xs[1], xs[0], xs[1]], [ys[0], ys[0], ys[1], ys[1]])
    return min(la), min(lo), max(la), max(lo)


def descargar_osm(carpeta, bbox, timeout=90, presupuesto_s=300):
    """Edificios, equipamiento, lugares y vías de OSM para el bbox (sur, oeste, norte, este). Reutiliza la descarga si ya existe para ese bbox."""
    base = Path(carpeta) / "datos_descargados"; clave = "_".join(f"{v:.3f}" for v in bbox)
    previa = next((d for d in sorted(base.glob("osm_*"), reverse=True) if (d / "bbox.txt").exists() and (d / "bbox.txt").read_text().strip() == clave), None)
    if previa is not None and not list(previa.glob("*.error.txt")) and (previa / "rios.json").exists():
        return previa
    s, w, n, e = bbox; bb = f"({s},{w},{n},{e})"
    consultas = {
        "edificios": f'[out:json][timeout:{timeout}];way["building"]{bb};out geom;',
        "pois": f'[out:json][timeout:{timeout}];(nwr["amenity"~"hospital|clinic|doctors|school|college|university|kindergarten|police|fire_station|townhall|community_centre"]{bb};'
                f'nwr["healthcare"]{bb};nwr["office"="government"]{bb};node["place"~"city|town|village|suburb|neighbourhood|hamlet"]{bb};);out center;',
        "vias": f'[out:json][timeout:{timeout}];way["highway"~"motorway|trunk|primary|secondary|tertiary|residential|unclassified"]{bb};out geom;',
        "rios": f'[out:json][timeout:{timeout}];way["waterway"~"river|stream|canal|drain"]{bb};out geom;'}       # Eta (Mejora 2): ríos trazados sobre imagen
    d = previa or (base / f"osm_{time.strftime('%Y%m%d_%H%M%S')}"); d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()                                                          # Eta: tiempo máximo total; lo que no baje se reintenta la próxima vez
    for k, q in consultas.items():
        if (d / f"{k}.json").exists():
            continue                                                          # ya descargado: solo se reintenta lo que falló
        for intento in range(3):
            if time.time() - t0 > presupuesto_s:
                (d / f"{k}.error.txt").write_text("Sin tiempo: OpenStreetMap (Overpass) no respondió a tiempo; se reintenta al generar el mapa otra vez.", encoding="utf-8"); break
            req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": "UCEclima/6 (GICCRH-UCE)"})
            try:
                (d / f"{k}.json").write_bytes(urllib.request.urlopen(req, timeout=timeout + 30).read()); (d / f"{k}.error.txt").unlink(missing_ok=True); break
            except Exception as ex:
                (d / f"{k}.error.txt").write_text(str(ex)[:500], encoding="utf-8"); time.sleep(5 * (intento + 1))
    (d / "bbox.txt").write_text(clave); (d / "LEEME.txt").write_text("OpenStreetMap © colaboradores de OSM (ODbL), descargado con Overpass para el mapa de referencias de UCEclima.", encoding="utf-8")
    return d


def _leer_osm(d, crs):
    import geopandas as gpd
    from shapely.geometry import Point, Polygon, LineString
    bld = pois = vias = None
    try:
        j = json.loads((d / "edificios.json").read_text(encoding="utf-8")); polys = []
        for el in j.get("elements", []):
            g = el.get("geometry")
            if g and len(g) >= 4:
                polys.append((el["id"], Polygon([(p["lon"], p["lat"]) for p in g])))
        if polys:
            bld = gpd.GeoDataFrame({"osm_id": [p[0] for p in polys]}, geometry=[p[1] for p in polys], crs=4326)
            bld = bld[bld.is_valid & ~bld.is_empty].to_crs(crs); bld["xc"] = bld.geometry.centroid.x; bld["yc"] = bld.geometry.centroid.y
    except Exception:
        pass
    try:
        j = json.loads((d / "pois.json").read_text(encoding="utf-8")); rows = []
        for el in j.get("elements", []):
            t = el.get("tags", {}); c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
            if c.get("lat") is None:
                continue
            am, hc, pl = t.get("amenity", ""), t.get("healthcare", ""), t.get("place", "")
            if am in ("hospital", "clinic", "doctors") or hc: tipo = "salud"
            elif am in ("school", "college", "university", "kindergarten"): tipo = "educacion"
            elif am in ("police", "fire_station"): tipo = "seguridad"
            elif am in ("townhall", "community_centre") or t.get("office") == "government": tipo = "gobierno"
            elif pl: tipo = "lugar"
            else: continue
            rows.append({"nombre": t.get("name", ""), "tipo": tipo, "detalle": am or hc or pl, "lon": c["lon"], "lat": c["lat"]})
        if rows:
            pois = gpd.GeoDataFrame(rows, geometry=[Point(r["lon"], r["lat"]) for r in rows], crs=4326).to_crs(crs)
    except Exception:
        pass
    try:
        j = json.loads((d / "vias.json").read_text(encoding="utf-8")); ls = []
        for el in j.get("elements", []):
            g = el.get("geometry")
            if g and len(g) >= 2:
                hw = el.get("tags", {}).get("highway", ""); ls.append({"nombre": el.get("tags", {}).get("name", ""), "clase": "principal" if hw in ("motorway", "trunk", "primary", "secondary", "tertiary") else "local",
                                                                      "geometry": LineString([(p["lon"], p["lat"]) for p in g])})
        if ls:
            vias = gpd.GeoDataFrame(ls, crs=4326).to_crs(crs)
    except Exception:
        pass
    return bld, pois, vias


def leer_rios_osm(d, crs):
    """Eta (Mejora 2): ríos, esteros y canales de OSM (trazados sobre imagen satelital). Ubican el cauce real mejor que HydroSHEDS/GEOGLOWS."""
    import geopandas as gpd
    from shapely.geometry import LineString
    try:
        j = json.loads((Path(d) / "rios.json").read_text(encoding="utf-8")); ls = []
        for el in j.get("elements", []):
            g = el.get("geometry")
            if g and len(g) >= 2:
                t = el.get("tags", {}); ls.append({"nombre": t.get("name", ""), "clase": t.get("waterway", ""), "geometry": LineString([(p["lon"], p["lat"]) for p in g])})
        return gpd.GeoDataFrame(ls, crs=4326).to_crs(crs) if ls else None
    except Exception:
        return None


def _muestrea(a, T, xs, ys, win=0):
    r = np.floor((ys - T.f) / T.e).astype(int); c = np.floor((xs - T.c) / T.a).astype(int); out = np.zeros(len(xs))
    for i, (rr, cc) in enumerate(zip(r, c)):
        if 0 <= rr < a.shape[0] and 0 <= cc < a.shape[1]:
            out[i] = np.nanmax(a[max(0, rr - win):rr + win + 1, max(0, cc - win):cc + win + 1])
    return np.nan_to_num(out)


def mapa(carpeta, run, descargar=True, umbral_m=0.05, titulo=None, idioma="es", rios_hydrosheds=False):
    """Mapa con referencias y exposición de una corrida. Devuelve rutas y cifras de exposición."""
    import rasterio, geopandas as gpd
    import contextily as cx
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe, cm
    from matplotlib.colors import Normalize, LinearSegmentedColormap
    from matplotlib.lines import Line2D
    from scipy.ndimage import gaussian_filter, zoom
    from pyproj import Transformer
    carpeta = Path(carpeta); d = carpeta / "resultados" / str(run)
    if not run or ".." in str(run) or not d.is_dir():
        raise MapaError("Corrida no encontrada.")
    f = next(d.rglob("hmax.tif"), None)
    if f is None:
        raise MapaError("La corrida no tiene hmax.tif.")
    with rasterio.open(f) as s:
        a = s.read(1, masked=True).filled(np.nan).astype("float64"); T = s.transform; crs = s.crs; bnd = s.bounds
    resumen = json.loads(next(d.rglob("resumen.json")).read_text(encoding="utf-8"))
    osm = descargar_osm(carpeta, _bbox_lonlat(T, a.shape, crs)) if descargar else None
    bld, pois, vias = _leer_osm(osm, crs) if osm else (None, None, None)
    out = f.parent; expo = {"edificios_osm": 0 if bld is None else int(len(bld))}
    prof = None
    if bld is not None and len(bld):
        prof = _muestrea(a, T, bld.xc.values, bld.yc.values); expo.update({"edificios_calado_ge_0.5m": int((prof >= 0.5).sum()), "edificios_calado_ge_1m": int((prof >= 1.0).sum())})
        ex_ = bld[prof >= 0.5].copy(); ex_["calado_m"] = np.round(prof[prof >= 0.5], 2)
        if len(ex_): ex_[["osm_id", "calado_m", "geometry"]].to_file(out / "edificios_expuestos.gpkg", driver="GPKG")
    crit = None
    if pois is not None and len(pois):
        crit = pois[pois.tipo.isin(list(ICON))].copy(); crit["calado_m"] = np.round(_muestrea(a, T, crit.geometry.x.values, crit.geometry.y.values, win=1), 2)
        expo["instalaciones_osm"] = int(len(crit)); expo["instalaciones_calado_ge_0.3m"] = int((crit.calado_m >= 0.3).sum())
    with pd.ExcelWriter(out / "exposicion.xlsx") as w:
        pd.DataFrame([expo]).to_excel(w, sheet_name="resumen", index=False)
        if crit is not None: crit.drop(columns="geometry").sort_values(["tipo", "nombre"]).to_excel(w, sheet_name="instalaciones", index=False)
    # ---------------------------------------------------------------- figura
    tf = Transformer.from_crs(crs, 3857, always_xy=True)
    l, bt = tf.transform(bnd.left, bnd.bottom); r, tp = tf.transform(bnd.right, bnd.top)
    plt.style.use("default")                                                              # el proceso de corrida puede traer un estilo oscuro
    fig, ax = plt.subplots(figsize=(10, 10), dpi=170, facecolor="white"); ax.set_xlim(l, r); ax.set_ylim(bt, tp)
    fuente_base = "Esri World Imagery"
    try:
        cx.add_basemap(ax, source=cx.providers.Esri.WorldImagery, attribution=False, zorder=1)
    except Exception as ex:
        fuente_base = "sin imagen satelital (" + str(ex)[:60] + ")"
    wet = np.isfinite(a) & (a >= umbral_m); fct = 3
    wet_hi = np.clip(zoom(wet.astype(np.float32), fct, order=1), 0, 1); dep_hi = zoom(np.where(wet, a, 0).astype(np.float32), fct, order=3)
    wgt = gaussian_filter(wet_hi, 0.75); num = gaussian_filter(np.maximum(dep_hi, 0) * wet_hi, 0.75)
    up = np.divide(num, wgt, out=np.zeros_like(num), where=wgt > 1e-4); alpha = np.clip((wgt - 0.04) / 0.48, 0, 1)
    vmax = float(min(np.percentile(a[wet], 98), 3.0)) if wet.any() else 1.0
    cmap = LinearSegmentedColormap.from_list("agua", ["#b9f3f0", "#43d3df", "#168eb8", "#164f91"], N=256)
    rgba = cmap(Normalize(umbral_m, vmax)(up)); rgba[..., 3] = alpha * 0.8
    ax.imshow(rgba, extent=(l, r, bt, tp), interpolation="bilinear", zorder=4)
    glow = [pe.withStroke(linewidth=2.4, foreground="black")]; box = dict(boxstyle="round,pad=0.16", facecolor="white", alpha=0.8, edgecolor="none")
    if vias is not None and len(vias):
        v3 = vias.to_crs(3857); v3[v3.clase == "local"].plot(ax=ax, color="#3b4149", lw=0.3, alpha=.5, zorder=5)
        v3[v3.clase == "principal"].plot(ax=ax, color="#1c222b", lw=1.0, zorder=6, path_effects=[pe.withStroke(linewidth=1.9, foreground="#cfd6df")])
    if bld is not None and len(bld):
        g3 = bld.to_crs(3857); g3.plot(ax=ax, facecolor="none", edgecolor="#ffffff", linewidth=0.15, alpha=0.5, zorder=5)
        m5, m1 = prof >= 0.5, prof >= 1.0
        if (m5 & ~m1).any(): g3[m5 & ~m1].plot(ax=ax, facecolor="#ff3b30", edgecolor="none", zorder=6)
        if m1.any(): g3[m1].plot(ax=ax, facecolor="#7a0010", edgecolor="#ffd0d0", linewidth=0.15, zorder=6)
    hay_rios = False; hay_rios_osm = False; fr = []
    ro = leer_rios_osm(osm, crs) if osm else None                                         # Eta (Mejora 2): el río que se dibuja es el de OSM, trazado sobre imagen
    if ro is not None and len(ro):
        r3 = ro.to_crs(3857); grande = r3.clase.isin(["river", "canal"])
        r3[~grande].plot(ax=ax, color="#5ec8ff", linewidth=0.7, alpha=0.9, zorder=7)
        r3[grande].plot(ax=ax, color="#1fa2ff", linewidth=1.8, zorder=7, path_effects=[pe.withStroke(linewidth=2.8, foreground="#0b2a44")]); hay_rios_osm = True
    try:                                                                               # HydroSHEDS/GEOGLOWS: red aproximada (±1 km), solo si se pide
        fr = (sorted((carpeta / "datos_descargados").glob("rios_merge_*/rios_merge.gpkg")) or sorted((carpeta / "datos_descargados").glob("rios_*/rios_hydrosheds.gpkg"))) if rios_hydrosheds else []
        if fr:
            from shapely.geometry import box as _box
            gr = gpd.read_file(fr[-1]).to_crs(crs); gr = gr[gr.intersects(_box(bnd.left, bnd.bottom, bnd.right, bnd.top))]
            if len(gr):
                gr.to_crs(3857).plot(ax=ax, color="#00d9ff", linewidth=np.clip(gr.UPLAND_SKM.values / 150, 0.6, 2.4), linestyle="--", alpha=0.8, zorder=7); hay_rios = True
    except Exception:
        pass
    try:                                                                               # estaciones del proyecto
        cat = carpeta / "datos" / "estaciones" / "catalogo.csv"
        if cat.exists():
            ce = pd.read_csv(cat); te = Transformer.from_crs(ce["crs"].iloc[0], 3857, always_xy=True)
            for _, e_ in ce.iterrows():
                xe, ye = te.transform(float(e_["x"]), float(e_["y"]))
                if l <= xe <= r and bt <= ye <= tp:
                    ax.scatter([xe], [ye], marker="^", s=120, c="#ffef5c", edgecolors="black", zorder=12)
                    ax.text(xe, ye, "  " + str(e_["id"]).split("_")[0], fontsize=7.5, color="#0f1620", ha="left", va="center", bbox=dict(boxstyle="round,pad=0.16", facecolor="white", alpha=0.8, edgecolor="none"), zorder=12)
    except Exception:
        pass
    try:
        lugar = json.loads((carpeta / "proyecto_uceclima.json").read_text(encoding="utf-8")).get("nombre", "")
        lugar = lugar.split(" ")[0] if lugar else ""
        if lugar:
            ax.text(0.5, 0.965, lugar.upper(), transform=ax.transAxes, ha="center", fontsize=14, fontweight="bold", family="serif", color="#0d1b2a",
                    bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.85, edgecolor="none"), zorder=12)
    except Exception:
        pass
    puestos = []
    def libre(x, y, dmin):
        return not any(abs(x - px) < dmin and abs(y - py) < dmin for px, py in puestos)
    dmin = (r - l) / 12                                                               # Omega: rótulos espaciados (solo los importantes)
    if pois is not None and len(pois):
        p3 = pois.to_crs(3857)
        for tipo, (mk, col, sz, _) in ICON.items():
            q = p3[p3.tipo == tipo]
            if len(q): ax.scatter(q.geometry.x, q.geometry.y, marker=mk, s=sz, c=col, edgecolors="white", linewidths=0.4, alpha=0.9, zorder=10)
        imp = p3[(p3.tipo == "salud") & p3.detalle.astype(str).isin(["hospital"])] if "detalle" in p3 else p3.head(0)          # solo hospitales y barrios llevan nombre
        for tipo, lim in (("salud", 4), ("lugar", 6)):
            cand = imp if (tipo == "salud" and len(imp)) else p3[p3.tipo == tipo]
            for _, rr in cand[cand.nombre.astype(str).str.len() > 2].head(lim).iterrows():
                if libre(rr.geometry.x, rr.geometry.y, dmin):
                    puestos.append((rr.geometry.x, rr.geometry.y))
                    ax.text(rr.geometry.x, rr.geometry.y, " " + str(rr["nombre"])[:28], fontsize=5.6 if tipo != "lugar" else 6.4, family="serif", style="italic" if tipo == "lugar" else "normal",
                            color="#4a1010" if tipo == "salud" else "#1b2533", ha="left", va="bottom", bbox=dict(boxstyle="round,pad=0.12", facecolor="white", alpha=0.6, edgecolor="none"), zorder=11)
    sal = (resumen.get("hidrograma_salida") or {}).get("celda")
    if sal:
        x, y = T * (sal[1] + 0.5, sal[0] + 0.5); x3, y3 = tf.transform(x, y)
        ax.scatter([x3], [y3], marker="^", s=110, c="#ffd400", edgecolors="black", zorder=12)
        ax.text(x3, y3, "  sección de salida", fontsize=7.5, color="#0f1620", ha="left", va="center", bbox=box, zorder=12)
    ax.annotate("N", xy=(0.05, 0.93), xytext=(0.05, 0.85), xycoords="axes fraction", ha="center", fontsize=14, fontweight="bold", color="w", path_effects=glow,
                arrowprops=dict(arrowstyle="-|>", color="w", lw=2), zorder=13)
    ancho_m = bnd.right - bnd.left; esc = 10 ** int(np.floor(np.log10(ancho_m / 4))); esc = esc * (2 if ancho_m / esc > 10 else 1)
    x0 = l + (r - l) * 0.62; y0 = bt + (tp - bt) * 0.05; sb = esc * (r - l) / ancho_m
    ax.plot([x0, x0 + sb], [y0, y0], color="w", lw=4, solid_capstyle="butt", path_effects=glow, zorder=13)
    ax.text(x0 + sb / 2, y0 + (tp - bt) * 0.012, f"{esc / 1000:g} km" if esc >= 1000 else f"{esc:g} m", color="w", fontsize=8, ha="center", path_effects=glow, zorder=13)
    hs = [Line2D([], [], marker="s", ls="", mfc="#ff3b30", mec="none", ms=7, label="Edificio con calado ≥ 0,5 m"), Line2D([], [], marker="s", ls="", mfc="#7a0010", mec="none", ms=7, label="Edificio con calado ≥ 1 m")]
    if hay_rios_osm: hs.append(Line2D([], [], color="#1fa2ff", lw=2, label="Ríos y esteros (OpenStreetMap)"))
    if hay_rios: hs.append(Line2D([], [], color="#00d9ff", lw=2, ls="--", label="Red HydroSHEDS (aproximada, ±1 km)"))
    for tipo, (mk, col, _, lab) in ICON.items():
        if pois is not None and (pois.tipo == tipo).any(): hs.append(Line2D([], [], marker=mk, ls="", mfc=col, mec="white", ms=8, label=lab))
    ax.legend(handles=hs, loc="upper center", bbox_to_anchor=(0.5, -0.005), ncol=3, fontsize=7.2, framealpha=0.95)
    sm_ = cm.ScalarMappable(norm=Normalize(umbral_m, vmax), cmap=cmap); sm_.set_array([])
    cb = fig.colorbar(sm_, ax=ax, shrink=.55, pad=.02); cb.set_label("Calado máximo (m)", fontsize=9)
    esc_txt = (resumen.get("escenario") or "")
    tipo_f = str(resumen.get("tipo_forzamiento") or ""); tr_ = resumen.get("Tr")
    caso = (f"Tr {tr_}" if tr_ else {"pronostico": "PRONÓSTICO", "estimacion_satelital": "ESTIMACIÓN SATELITAL"}.get(tipo_f, "evento observado")) + (f" · {esc_txt}" if esc_txt and not str(esc_txt).startswith(("diseno", "evento", "pronostico", "estimacion")) else "")
    p99 = float(np.nanpercentile(a[np.isfinite(a) & (a >= umbral_m)], 99)) if (np.isfinite(a) & (a >= umbral_m)).any() else 0.0
    try:
        dem_ = str(json.loads((carpeta / "config_climanet.json").read_text(encoding="utf-8")).get("dem") or "").lower()
    except Exception:
        dem_ = ""
    terreno_ = "FABDEM" if "fabdem" in dem_ else ("GLO-30, DSM" if "glo30" in dem_ else "MDT del proyecto")
    tit = titulo or (f"Inundación 2D ({terreno_}) — {caso} · calado p99 {p99:.2f} m · {resumen.get('area_ge_0.05_km2', 0):.1f} km² (≥ 5 cm)"
                     + (f" · {expo.get('edificios_calado_ge_0.5m', 0)} edificios con ≥ 0,5 m" if bld is not None else " · OSM sin edificios en la zona"))
    ax.set_title(tit + f"\ncalado suavizado solo para visualización · base: {fuente_base} · calles, edificios y equipamiento OSM · " + ("evento real, modelo no calibrado" if not tr_ else "escenario de diseño, no calibrado"),
                 color="#1F4E79", fontweight="bold", fontsize=9.5, pad=8)
    ax.set_xticks([]); ax.set_yticks([]); fig.savefig(out / "mapa_referencias.png", bbox_inches="tight", facecolor="white")
    if idioma == "en":                                                                   # copia en inglés solo para los papers
        from .figuras_idioma import traducir
        traducir(fig); fig.savefig(out / "mapa_referencias_en.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    res = {"figura": str((out / "mapa_referencias.png").relative_to(carpeta)).replace("\\", "/"), "exposicion": expo, "base": fuente_base,
           "osm": None if osm is None else str(osm.relative_to(carpeta)).replace("\\", "/"), "aviso": "Exposición calculada sobre un escenario no calibrado; OSM puede estar incompleto."}
    (out / "mapa_referencias.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
