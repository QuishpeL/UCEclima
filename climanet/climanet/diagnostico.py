# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Diagnóstico de entradas de caudal: ¿la celda de entrada está sobre un cauce y por dónde sale el agua inyectada?

Solo diagnostica la topografía de la malla del modelo (D8 sobre el terreno remuestreado). NO evalúa capacidad
hidráulica de canales ni pérdidas de carga: un cauce no resuelto por el terreno no aparece aquí.
"""
import numpy as np
from . import terrain


def diagnostico_entradas(dem, active, celdas, dx, radio=3, tol_m=0.3, max_pasos=100000):
    z = np.where(active, dem, np.nan)
    zf = terrain.fill_sinks(z)                       # solo para trazar rutas (no se usa en el modelo hidráulico)
    fd, acc = terrain.flow_accumulation(zf, dx)
    ddr = np.array([-1, -1, -1, 0, 0, 1, 1, 1]); ddc = np.array([-1, 0, 1, -1, 1, -1, 0, 1])
    ny, nx = z.shape
    out = []
    for r, c in np.asarray(celdas, int):
        r0, r1, c0, c1 = max(r - radio, 0), min(r + radio + 1, ny), max(c - radio, 0), min(c + radio + 1, nx)
        sobre_min = float(z[r, c] - np.nanmin(z[r0:r1, c0:c1]))
        yy, xx = np.mgrid[r0:r1, c0:c1]
        anillo = (np.maximum(abs(yy - r), abs(xx - c)) == radio)
        encaj = float(np.nanmean(z[r0:r1, c0:c1][anillo]) - z[r, c]) if anillo.any() else 0.0   # >0: la celda está encajonada
        # ruta D8 aguas abajo
        rr, cc, n, drop = r, c, 0, 0.0
        ruta_sale = False
        while n < max_pasos:
            k = fd[rr, cc]
            if k < 0:
                ruta_sale = rr in (0, ny - 1) or cc in (0, nx - 1)
                break
            rr, cc = rr + ddr[k], cc + ddc[k]; n += 1
        drop = float(z[r, c] - zf[rr, cc]) if np.isfinite(zf[rr, cc]) else np.nan
        adv = []
        if encaj < tol_m:
            adv.append(f"encajonamiento {encaj:.2f} m < {tol_m} m: la celda no está en una depresión lineal (probablemente ladera, no cauce)")
        if acc[r, c] < 10:
            adv.append("área aportante D8 propia pequeña (<10 celdas): normal en una cabecera; el cauce depende del aporte externo")
        if not ruta_sale:
            adv.append("la ruta D8 no sale del dominio: el agua queda en una depresión")
        out.append({"celda": [int(r), int(c)], "m_sobre_minimo_local": sobre_min, "encajonamiento_m": encaj, "celdas_aportantes_D8": float(acc[r, c]),
                    "longitud_ruta_m": n * dx, "descenso_ruta_m": drop, "ruta_sale_del_dominio": bool(ruta_sale),
                    "en_cauce": bool(encaj >= tol_m and ruta_sale), "advertencias": adv})
    return out


def candidatos_en_borde(dem, active, dx, k=8, min_acc=200):
    """Celdas de borde con mayor acumulación D8: posibles cruces de cauces por la frontera (a confirmar con geometría real)."""
    z = np.where(active, dem, np.nan)
    zf = terrain.fill_sinks(z); fd, acc = terrain.flow_accumulation(zf, dx)
    ny, nx = z.shape
    borde = np.zeros_like(active); borde[0, :] = borde[-1, :] = borde[:, 0] = borde[:, -1] = True
    idx = np.argwhere(borde & active & (acc >= min_acc))
    idx = idx[np.argsort(-acc[idx[:, 0], idx[:, 1]])][:k]
    return [{"celda": [int(r), int(c)], "borde": ("N" if r == 0 else "S" if r == ny - 1 else "O" if c == 0 else "E"),
             "celdas_aportantes": float(acc[r, c]), "area_aportante_km2": float(acc[r, c] * dx * dx / 1e6)} for r, c in idx]
