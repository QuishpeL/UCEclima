# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Mapas estáticos REALES a partir de los rásteres que escribe el núcleo (sin satélite, sin agua inventada).
Cada mapa lleva: unidades, CRS, aviso de datum vertical, tipo de resultado (diseño IDF, no calibrado) y, en proyectos sintéticos, una marca visible."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, Normalize
import rasterio

COLORES = {"papel": "#101b29", "carbon": "#e6edf5", "agua": "#6cc4ec", "aviso": "#e8b84d"}      # carboncillo azul (coherente con la interfaz)
plt.rcParams.update({"font.family": ["Calibri", "Arial", "DejaVu Sans"], "text.color": COLORES["carbon"], "axes.labelcolor": COLORES["carbon"], "axes.edgecolor": "#3a5069",
                     "xtick.color": "#93a4b8", "ytick.color": "#93a4b8", "axes.facecolor": COLORES["papel"], "figure.facecolor": COLORES["papel"], "savefig.facecolor": COLORES["papel"]})


def _terreno(cfg, base):
    from climanet import terrain
    p = Path(cfg["dem"]); p = p if p.is_absolute() else Path(base) / p
    return terrain.load_dem(str(p), float(cfg.get("res", 10)), cfg.get("aoi"))


def _decorar(ax, meta, res, sintetico, titulo, subtitulo):
    t = meta["transform"]; ny, nx = meta["height"], meta["width"]
    ext = (t.c, t.c + t.a * nx, t.f + t.e * ny, t.f)
    ax.set_xlabel("Este (m)  ·  " + str(meta["crs"]).replace("EPSG:", "EPSG ")); ax.set_ylabel("Norte (m)")
    ax.ticklabel_format(style="plain", useOffset=False); ax.tick_params(labelsize=8)
    ax.set_title(titulo, fontsize=12, color=COLORES["carbon"], loc="left", pad=22, fontweight="bold")
    ax.text(0, 1.015, subtitulo, transform=ax.transAxes, fontsize=8.5, color=COLORES["aviso"], va="bottom")
    # barra de escala y norte
    L = 10 ** int(np.floor(np.log10((ext[1] - ext[0]) / 3)))
    x0, y0 = ext[0] + (ext[1] - ext[0]) * 0.04, ext[2] + (ext[3] - ext[2]) * 0.05
    ax.plot([x0, x0 + L], [y0, y0], color=COLORES["carbon"], lw=4, solid_capstyle="butt")
    ax.text(x0 + L / 2, y0 + (ext[3] - ext[2]) * 0.015, f"{L:g} m", ha="center", fontsize=8, color=COLORES["carbon"],
            bbox=dict(fc=COLORES["papel"], ec="none", alpha=.75, pad=1))
    ax.annotate("N", xy=(0.95, 0.93), xytext=(0.95, 0.80), xycoords="axes fraction", ha="center", fontsize=12, fontweight="bold",
                color=COLORES["carbon"], arrowprops=dict(arrowstyle="-|>", color=COLORES["carbon"], lw=2))
    if sintetico:
        ax.text(0.5, 0.5, "SINTÉTICO\nno es un lugar real", transform=ax.transAxes, ha="center", va="center", fontsize=34, color="#8a5a00", alpha=.28,
                rotation=25, fontweight="bold")


def render_terreno(cfg, base, png, sintetico=False, nota_tipo="tipo de terreno no declarado"):
    z, meta = _terreno(cfg, base)
    dx = abs(meta["transform"].a)
    ls = LightSource(azdeg=315, altdeg=40)
    zz = np.where(np.isfinite(z), z, np.nanmin(z))
    rgb = ls.shade(zz, cmap=plt.cm.terrain, blend_mode="overlay", vert_exag=2, dx=dx, dy=dx, vmin=np.nanpercentile(z, 1), vmax=np.nanpercentile(z, 99))
    rgb[~np.isfinite(z)] = (0.8, 0.8, 0.8, 1)
    t = meta["transform"]; ny, nx = z.shape; ext = (t.c, t.c + t.a * nx, t.f + t.e * ny, t.f)
    fig, ax = plt.subplots(figsize=(9, 7.2), dpi=110); fig.patch.set_facecolor(COLORES["papel"]); ax.set_facecolor(COLORES["papel"])
    ax.imshow(rgb, extent=ext, origin="upper")
    sm = plt.cm.ScalarMappable(norm=Normalize(np.nanpercentile(z, 1), np.nanpercentile(z, 99)), cmap=plt.cm.terrain)
    cb = fig.colorbar(sm, ax=ax, shrink=.75, pad=.02); cb.set_label("Cota (m) · datum vertical no verificado", fontsize=9)
    _decorar(ax, meta, dx, sintetico, "Terreno del área de estudio", f"Resolución del modelo {dx:g} m · {nota_tipo}")
    fig.tight_layout(); fig.savefig(png, facecolor=fig.get_facecolor()); plt.close(fig)
    return {"min_m": float(np.nanmin(z)), "max_m": float(np.nanmax(z)), "celdas": int(np.isfinite(z).sum()), "res_m": dx}


def render_hmax(cfg, base, hmax_tif, png, sintetico=False, titulo="Calado máximo (diseño IDF)", subtitulo="Diseño IDF histórica · no es un evento observado · no calibrado · no validado", umbral=0.05):
    z, meta = _terreno(cfg, base)
    with rasterio.open(hmax_tif) as s:
        h = s.read(1).astype(float); h[h < 0] = np.nan
    dx = abs(meta["transform"].a)
    if h.shape != z.shape:                                            # el solver subcelda recorta a múltiplos de la celda gruesa
        z = z[:h.shape[0], :h.shape[1]]
    ls = LightSource(azdeg=315, altdeg=40)
    zz = np.where(np.isfinite(z), z, np.nanmin(z))
    base_rgb = ls.shade(zz, cmap=plt.cm.Greys, blend_mode="overlay", vert_exag=2, dx=dx, dy=dx, vmin=np.nanpercentile(z, 1), vmax=np.nanpercentile(z, 99))
    t = meta["transform"]; ny, nx = h.shape; ext = (t.c, t.c + t.a * nx, t.f + t.e * ny, t.f)
    fig, ax = plt.subplots(figsize=(9, 7.2), dpi=110); fig.patch.set_facecolor(COLORES["papel"])
    ax.imshow(base_rgb, extent=ext, origin="upper", alpha=.85)
    vmax = max(float(np.nanpercentile(h[h >= umbral], 98)) if np.any(h >= umbral) else 1.0, 0.5)
    mh = np.ma.masked_where(~(h >= umbral), h)
    im = ax.imshow(mh, extent=ext, origin="upper", cmap="Blues", norm=Normalize(0, vmax), alpha=.9, interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, shrink=.75, pad=.02, extend="max"); cb.set_label(f"Calado máximo (m) · solo celdas ≥ {umbral:g} m", fontsize=9)
    _decorar(ax, meta, dx, sintetico, titulo, subtitulo)
    ax.text(0.02, 0.97, "Cotas: datum vertical no verificado", transform=ax.transAxes, fontsize=8, va="top", color=COLORES["carbon"], bbox=dict(fc=COLORES["papel"], ec="none", alpha=.75, pad=2))
    fig.tight_layout(); fig.savefig(png, facecolor=fig.get_facecolor()); plt.close(fig)
    return {"hmax_max_m": float(np.nanmax(h)), "area_ge_umbral_km2": float(np.nansum(h >= umbral) * dx * dx / 1e6), "escala_color_max_m": vmax}
