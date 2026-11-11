# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Lámina del MDT del proyecto: relieve sombreado con tintes hipsométricos, curvas de nivel, área de estudio, sitio, escala y norte;
curva hipsométrica, histograma de cotas y estadísticas. Solo representa el ráster registrado; no lo modifica."""
import io
import json
import math
import re
import threading
from pathlib import Path

import numpy as np

_BLOQUEO = threading.Lock()


def _paso_curvas(rango):
    for p in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if rango / p <= 25:
            return p
    return 2000


def png(carpeta, datos, ancho_px=1500):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    import rasterio
    from rasterio.enums import Resampling
    carpeta = Path(carpeta)
    cfg = json.loads((carpeta / datos.get("config_climanet", "config_climanet.json")).read_text(encoding="utf-8"))
    if not cfg.get("dem"):
        raise ValueError("El proyecto aún no tiene MDT registrado.")
    ruta = Path(cfg["dem"]); ruta = ruta if ruta.is_absolute() else carpeta / ruta
    with rasterio.open(ruta) as s:
        f = max(1, int(math.ceil(max(s.width, s.height) / ancho_px)))
        z = s.read(1, masked=True, out_shape=(s.height // f, s.width // f), resampling=Resampling.average if f > 1 else Resampling.nearest).astype("float64")
        b = s.bounds; crs = s.crs
    z = z.filled(np.nan)
    dx = (b.right - b.left) / z.shape[1]
    zv = z[np.isfinite(z)]
    if zv.size == 0:
        raise ValueError("El MDT no tiene celdas válidas.")
    zmin, zmax = float(np.nanmin(zv)), float(np.nanpercentile(zv, 99.8))
    zf = np.where(np.isfinite(z), z, zmin)
    ext = (b.left, b.right, b.bottom, b.top)
    with _BLOQUEO:
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
        fig = plt.figure(figsize=(13.5, 7.6), dpi=110, facecolor="#0f1724")
        gs = fig.add_gridspec(3, 3, width_ratios=[2.4, 1, 0.04], height_ratios=[1, 1, 0.55], wspace=0.28, hspace=0.42, left=0.04, right=0.94, top=0.92, bottom=0.07)
        ax = fig.add_subplot(gs[:, 0]); ax.set_facecolor("#0f1724")
        from matplotlib.colors import LinearSegmentedColormap
        cmap = LinearSegmentedColormap.from_list("hipso", plt.get_cmap("gist_earth")(np.linspace(0.18, 1.0, 256)))
        ls = LightSource(azdeg=315, altdeg=40)
        rgb = ls.shade(zf, cmap=cmap, blend_mode="soft", vert_exag=1.5, dx=dx, dy=dx, vmin=zmin, vmax=zmax)
        rgb[~np.isfinite(z)] = (0.06, 0.09, 0.14, 1)
        ax.imshow(rgb, extent=ext, origin="upper", interpolation="bilinear")
        paso = _paso_curvas(zmax - zmin)
        niveles = np.arange(math.ceil(zmin / paso) * paso, zmax, paso)
        xs = np.linspace(b.left + dx / 2, b.right - dx / 2, z.shape[1]); ys = np.linspace(b.top - dx / 2, b.bottom + dx / 2, z.shape[0])
        if len(niveles):
            ax.contour(xs, ys, zf, levels=niveles, colors="#ffffff", linewidths=0.25, alpha=0.35)
            maestras = niveles[niveles % (paso * 5) == 0]
            if len(maestras):
                cs = ax.contour(xs, ys, zf, levels=maestras, colors="#ffffff", linewidths=0.7, alpha=0.7)
                ax.clabel(cs, fmt="%d", fontsize=6, colors="#ffffff")
        if cfg.get("aoi"):
            x0, x1, y0, y1 = cfg["aoi"]
            ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="#ffd166", lw=1.6, ls="--"))
            ax.text(x0, y1, " área de estudio", color="#ffd166", fontsize=7, va="bottom")
        m = re.search(r"lon\s*(-?[\d.]+)\D+lat\s*(-?[\d.]+)", str(datos.get("ubicacion", "")))
        if m:
            from pyproj import Transformer
            sx, sy = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(float(m.group(1)), float(m.group(2)))
            ax.plot(sx, sy, marker="o", ms=6, mfc="#e63946", mec="white", mew=1)
        largo = 10 ** math.floor(math.log10((b.right - b.left) / 4)); largo = largo * (5 if (b.right - b.left) / 4 / largo >= 5 else 2 if (b.right - b.left) / 4 / largo >= 2 else 1)
        bx, by = b.left + (b.right - b.left) * 0.05, b.bottom + (b.top - b.bottom) * 0.05
        ax.plot([bx, bx + largo], [by, by], color="white", lw=3, solid_capstyle="butt"); ax.plot([bx, bx + largo / 2], [by, by], color="#0f1724", lw=1.4, solid_capstyle="butt")
        ax.text(bx + largo / 2, by + (b.top - b.bottom) * 0.012, f"{largo / 1000:g} km" if largo >= 1000 else f"{largo:g} m", color="white", ha="center", fontsize=7)
        nx_, ny_ = b.right - (b.right - b.left) * 0.06, b.top - (b.top - b.bottom) * 0.12
        ax.annotate("N", xy=(nx_, ny_ + (b.top - b.bottom) * 0.06), xytext=(nx_, ny_), color="white", ha="center", fontsize=10, fontweight="bold",
                    arrowprops=dict(arrowstyle="-|>", color="white", lw=1.4))
        ax.set_xlim(b.left, b.right); ax.set_ylim(b.bottom, b.top); ax.set_aspect("equal")
        ax.tick_params(colors="#8b95a3", labelsize=6); [s_.set_color("#2a3647") for s_ in ax.spines.values()]
        ax.ticklabel_format(style="plain", useOffset=False)
        cax = fig.add_subplot(gs[:2, 2])
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(zmin, zmax)); cb = fig.colorbar(sm, cax=cax)
        cb.set_label("cota (m)", color="#c9d1db"); cb.ax.tick_params(colors="#c9d1db", labelsize=6)
        orden = np.sort(zv)[::-1]; area = np.arange(1, orden.size + 1) / orden.size * 100
        a1 = fig.add_subplot(gs[0, 1]); a1.plot(area, orden, color="#6cc4ec", lw=1.8); a1.fill_between(area, orden, orden.min(), color="#6cc4ec", alpha=0.12)
        a1.set_title("Curva hipsométrica", color="#e6edf3", fontsize=9); a1.set_xlabel("área por encima (%)", color="#8b95a3"); a1.set_ylabel("cota (m)", color="#8b95a3")
        a2 = fig.add_subplot(gs[1, 1]); cnt, ed, pat = a2.hist(zv, bins=40, color="#9fb4ff", alpha=0.85)
        for c_, p_ in zip((ed[:-1] + ed[1:]) / 2, pat):
            p_.set_facecolor(cmap((c_ - zmin) / max(zmax - zmin, 1)))
        a2.set_title("Distribución de cotas", color="#e6edf3", fontsize=9); a2.set_xlabel("cota (m)", color="#8b95a3"); a2.set_ylabel("celdas", color="#8b95a3")
        for a in (a1, a2):
            a.set_facecolor("#131d2b"); a.tick_params(colors="#8b95a3", labelsize=6); a.grid(alpha=0.15)
            [s_.set_color("#2a3647") for s_ in a.spines.values()]
        a3 = fig.add_subplot(gs[2, 1:]); a3.axis("off")
        pend = np.degrees(np.arctan(np.hypot(*np.gradient(zf, dx))))[np.isfinite(z)]
        mil = lambda v: f"{v:,.0f}".replace(",", " ")
        filas = [("Cota mínima / máxima", f"{mil(np.nanmin(zv))} / {mil(np.nanmax(zv))} m"), ("Cota media", f"{mil(zv.mean())} m"),
                 ("Pendiente media", f"{pend.mean():.1f}°".replace(".", ",")), ("Extensión", f"{(b.right - b.left) / 1000:.1f} × {(b.top - b.bottom) / 1000:.1f} km".replace(".", ",")),
                 ("Resolución mostrada", f"{dx:.0f} m"), ("CRS", str(crs))]
        for i, (k, v) in enumerate(filas):
            a3.text(0.0 + (i // 3) * 0.52, 0.85 - (i % 3) * 0.33, k, color="#8b95a3", fontsize=7.5, transform=a3.transAxes)
            a3.text(0.0 + (i // 3) * 0.52, 0.85 - (i % 3) * 0.33 - 0.15, v, color="#e6edf3", fontsize=9, transform=a3.transAxes)
        fig.suptitle(f"{datos.get('nombre', '')} · modelo digital de elevación", color="#e6edf3", fontsize=12, x=0.04, ha="left")
        bio = io.BytesIO(); fig.savefig(bio, format="png", facecolor=fig.get_facecolor()); plt.close(fig)
    return bio.getvalue()
