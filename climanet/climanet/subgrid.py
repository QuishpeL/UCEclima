# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Solver 2D de inercia local con representación SUBCELDA del terreno (volumen-elevación y secciones de cara).

Idea (equivalente conceptual a las tablas hidráulicas de HEC-RAS 2D): cada celda gruesa agrupa m×m píxeles finos del MDT.
 - Almacenamiento: V(η) = a_p·Σ max(η − z_p, 0), exacto y monótono; el estado es el volumen V y el nivel η se obtiene invirtiendo V(η).
 - Caras: la sección mojada A(η) se integra sobre el perfil de cresta fino de la cara, e_k = max(z_izq,k , z_der,k); R = A/W.
 - Flujo de cara: Q = (Q0 − g·A·Δt·S)/(1 + g·Δt·n²·|Q0|/(A·R^(4/3))), S = (η_der − η_izq)/dx  (misma formulación que el solver de malla
   regular; para terreno plano y sección rectangular se reduce exactamente a él).
 - Conservación: limitador de volumen saliente por celda, contabilidad de lluvia, entradas, salida y almacenamiento (residual ~ redondeo).
Alcance: prototipo explícito sin términos advectivos ni estructuras; no es HEC-RAS ni está calibrado.
"""
from dataclasses import dataclass
import numpy as np
from numba import njit, prange


@dataclass
class SubgridOptions:
    end_seconds: float
    max_dt: float = 5.0
    cfl: float = 0.35
    boundary: str = "closed"          # 'closed' | 'free_outflow'
    gravity: float = 9.81
    record_interval: float = 300.0
    max_steps: int = 2_000_000


# --------------------------------------------------------------------------- preprocesamiento
def construir(zf, m, rf, cresta="max"):
    """zf: MDT fino (ny*m, nx*m) en metros, finito. m: píxeles finos por lado de celda gruesa. rf: tamaño del píxel fino (m).
    cresta: cota de la cresta de cara a partir de los dos píxeles que la flanquean: 'max' (barrera conservadora, como el solver de malla),
    'mean' (terreno interpolado sobre la línea de la cara) o 'min'."""
    if cresta not in ("max", "mean", "min"):
        raise ValueError("cresta debe ser max, mean o min.")
    comb = {"max": np.maximum, "mean": lambda a, b: 0.5 * (a + b), "min": np.minimum}[cresta]
    zf = np.asarray(zf, dtype=np.float64)
    if zf.ndim != 2 or zf.shape[0] % m or zf.shape[1] % m:
        raise ValueError("El MDT fino debe tener dimensiones múltiplo de m.")
    if not np.isfinite(zf).all():
        raise ValueError("El MDT fino debe ser finito en todo el dominio.")
    ny, nx = zf.shape[0] // m, zf.shape[1] // m
    blocks = zf.reshape(ny, m, nx, m).transpose(0, 2, 1, 3).reshape(ny, nx, m * m)
    zs = np.sort(blocks, axis=-1)
    Sp = np.concatenate([np.zeros((ny, nx, 1)), np.cumsum(zs, axis=-1)], axis=-1)                 # Sp[...,j] = suma de los j menores
    ap = rf * rf
    j = np.arange(zs.shape[-1])
    Vlev = ap * (j * zs - Sp[..., :-1])                                                           # V al nivel η = zs[j] (con j píxeles bajo el nivel)
    # caras verticales (entre columnas c-1 y c): c = 0..nx
    izq = np.arange(1, nx) * m - 1
    E = comb(zf[:, izq], zf[:, izq + 1]).reshape(ny, m, nx - 1).transpose(0, 2, 1)
    ex = np.concatenate([zf[:, 0].reshape(ny, m)[:, None, :], E, zf[:, -1].reshape(ny, m)[:, None, :]], axis=1)
    # caras horizontales (entre filas r-1 y r): r = 0..ny
    arr = np.arange(1, ny) * m - 1
    F = comb(zf[arr, :], zf[arr + 1, :]).reshape(ny - 1, nx, m)
    ey = np.concatenate([zf[0, :].reshape(nx, m)[None, :, :], F, zf[-1, :].reshape(nx, m)[None, :, :]], axis=0)
    ex = np.sort(ex, axis=-1); ey = np.sort(ey, axis=-1)
    exS = np.concatenate([np.zeros(ex.shape[:2] + (1,)), np.cumsum(ex, axis=-1)], axis=-1)
    eyS = np.concatenate([np.zeros(ey.shape[:2] + (1,)), np.cumsum(ey, axis=-1)], axis=-1)
    return dict(ny=ny, nx=nx, m=m, rf=rf, dx=m * rf, zs=np.ascontiguousarray(zs), Sp=np.ascontiguousarray(Sp), Vlev=np.ascontiguousarray(Vlev),
                ex=np.ascontiguousarray(ex), exS=np.ascontiguousarray(exS), ey=np.ascontiguousarray(ey), eyS=np.ascontiguousarray(eyS),
                area=(m * rf) ** 2, ap=ap)


# --------------------------------------------------------------------------- núcleos numba
@njit(cache=True, inline="always")
def _eta(V, zs, Sp, Vlev, ap, r, c):
    M = zs.shape[2]
    if V <= 0.0:
        return zs[r, c, 0]
    lo, hi = 0, M - 1                                   # mayor j con Vlev[j] <= V
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if Vlev[r, c, mid] <= V:
            lo = mid
        else:
            hi = mid - 1
    return (V / ap + Sp[r, c, lo + 1]) / (lo + 1)


@njit(parallel=True, cache=True)
def _niveles(V, zs, Sp, Vlev, ap, eta):
    ny, nx = V.shape
    for r in prange(ny):
        for c in range(nx):
            eta[r, c] = _eta(V[r, c], zs, Sp, Vlev, ap, r, c)


@njit(cache=True, inline="always")
def _seccion(e, eS, r, c, eup, m, rf):
    j = 0
    while j < m and e[r, c, j] < eup:
        j += 1
    if j == 0:
        return 0.0, 0.0
    return rf * (j * eup - eS[r, c, j]), j * rf


@njit(parallel=True, cache=True)
def _flujos(Qx, Qy, eta, ex, exS, ey, eyS, nman, ny, nx, m, rf, dx, g, dt, free, vface_x, vface_y):
    for r in prange(ny):
        for c in range(1, nx):
            eL, eR = eta[r, c - 1], eta[r, c]
            A, W = _seccion(ex, exS, r, c, max(eL, eR), m, rf)
            if A <= 1e-12:
                Qx[r, c] = 0.0; vface_x[r, c] = 0.0
                continue
            R = A / W; q = Qx[r, c]; n = 0.5 * (nman[r, c - 1] + nman[r, c])
            Qx[r, c] = (q - g * A * dt * (eR - eL) / dx) / (1.0 + g * dt * n * n * abs(q) / (A * R ** (4.0 / 3.0)))
            vface_x[r, c] = abs(Qx[r, c]) / A
        Qx[r, 0] = 0.0; Qx[r, nx] = 0.0
        if free:
            A, W = _seccion(ex, exS, r, 0, eta[r, 0], m, rf)
            if A > 1e-12:
                Qx[r, 0] = -A * np.sqrt(g * A / W)
            A, W = _seccion(ex, exS, r, nx, eta[r, nx - 1], m, rf)
            if A > 1e-12:
                Qx[r, nx] = A * np.sqrt(g * A / W)
    for r in prange(1, ny):
        for c in range(nx):
            eU, eD = eta[r - 1, c], eta[r, c]
            A, W = _seccion(ey, eyS, r, c, max(eU, eD), m, rf)
            if A <= 1e-12:
                Qy[r, c] = 0.0; vface_y[r, c] = 0.0
                continue
            R = A / W; q = Qy[r, c]; n = 0.5 * (nman[r - 1, c] + nman[r, c])
            Qy[r, c] = (q - g * A * dt * (eD - eU) / dx) / (1.0 + g * dt * n * n * abs(q) / (A * R ** (4.0 / 3.0)))
            vface_y[r, c] = abs(Qy[r, c]) / A
    for c in prange(nx):
        Qy[0, c] = 0.0; Qy[ny, c] = 0.0
        if free:
            A, W = _seccion(ey, eyS, 0, c, eta[0, c], m, rf)
            if A > 1e-12:
                Qy[0, c] = -A * np.sqrt(g * A / W)
            A, W = _seccion(ey, eyS, ny, c, eta[ny - 1, c], m, rf)
            if A > 1e-12:
                Qy[ny, c] = A * np.sqrt(g * A / W)


@njit(parallel=True, cache=True)
def _limitar_y_actualizar(V, src, Qx, Qy, dt, ny, nx, area, hmean_max, vmax, dur, vfx, vfy, umbral):
    """Limita el volumen saliente por celda, actualiza V y acumula máximos. Devuelve (salida_frontera, ajuste, nlimitadas, vmin)."""
    f = np.ones((ny, nx))
    nlim = 0
    for r in range(ny):
        for c in range(nx):
            out = (max(Qx[r, c + 1], 0.0) + max(-Qx[r, c], 0.0) + max(Qy[r + 1, c], 0.0) + max(-Qy[r, c], 0.0)) * dt
            disp = V[r, c] + src[r, c]
            if out > disp:
                f[r, c] = disp / out if out > 0 else 1.0
                nlim += 1
    for r in prange(ny):
        for c in range(1, nx):
            Qx[r, c] *= f[r, c - 1] if Qx[r, c] >= 0 else f[r, c]
    for r in prange(1, ny):
        for c in range(nx):
            Qy[r, c] *= f[r - 1, c] if Qy[r, c] >= 0 else f[r, c]
    for r in prange(ny):
        Qx[r, 0] *= f[r, 0]; Qx[r, nx] *= f[r, nx - 1]
    for c in prange(nx):
        Qy[0, c] *= f[0, c]; Qy[ny, c] *= f[ny - 1, c]
    ajuste = 0.0; vmin = 1e30
    for r in range(ny):
        for c in range(nx):
            nuevo = V[r, c] + src[r, c] + dt * (Qx[r, c] - Qx[r, c + 1] + Qy[r, c] - Qy[r + 1, c])
            vmin = min(vmin, nuevo)
            if nuevo < 0.0:
                ajuste += -nuevo; nuevo = 0.0
            V[r, c] = nuevo
            h = nuevo / area
            if h > hmean_max[r, c]:
                hmean_max[r, c] = h
            if h >= umbral:
                dur[r, c] += dt
            v = max(vfx[r, c], vfx[r, c + 1], vfy[r, c], vfy[r + 1, c])
            if v > vmax[r, c]:
                vmax[r, c] = v
    salida = dt * ((Qx[:, nx].sum() - Qx[:, 0].sum()) + (Qy[ny, :].sum() - Qy[0, :].sum()))
    return salida, ajuste, nlim, vmin


# --------------------------------------------------------------------------- simulación
def simular(modelo, manning, edges_s, runoff_mm, opts, entradas=None, V0=None, progress=None):
    """modelo: salida de construir(). manning: (ny,nx). runoff_mm: (n_bloques, ny, nx) exceso en mm por bloque (bordes edges_s).
    entradas: [{'nombre','t','q','celdas':[[r,c],...]}] (cada una con su hidrograma). Devuelve dict con máximos, balance y resumen."""
    P = modelo; ny, nx, m, rf, dx, area, ap = P["ny"], P["nx"], P["m"], P["rf"], P["dx"], P["area"], P["ap"]
    g = opts.gravity
    nman = np.asarray(manning, dtype=np.float64)
    edges = np.asarray(edges_s, float); runoff = np.asarray(runoff_mm, float)
    if runoff.shape != (len(edges) - 1, ny, nx) or edges[0] != 0 or np.any(np.diff(edges) <= 0):
        raise ValueError("Forzamiento inválido.")
    if edges[-1] > opts.end_seconds:
        raise ValueError("La simulación terminaría antes de completar la lluvia.")
    ent = []
    for e in (entradas or []):
        t_, q_ = np.asarray(e["t"], float), np.asarray(e["q"], float)
        if len(t_) < 2 or t_[0] != 0 or np.any(np.diff(t_) <= 0) or np.any(q_ < 0) or q_[-1] != 0 or t_[-1] > opts.end_seconds:
            raise ValueError(f"Hidrograma inválido en {e.get('nombre')}.")
        ent.append(dict(nombre=e["nombre"], t=t_, q=q_, celdas=np.asarray(e["celdas"], int), vol=0.0,
                        esperado=float((np.trapezoid if hasattr(np, 'trapezoid') else np.trapz)(q_, t_))))
    V = np.zeros((ny, nx)) if V0 is None else np.array(V0, float)
    eta = np.empty((ny, nx)); _niveles(V, P["zs"], P["Sp"], P["Vlev"], ap, eta)
    Qx = np.zeros((ny, nx + 1)); Qy = np.zeros((ny + 1, nx))
    vfx = np.zeros((ny, nx + 1)); vfy = np.zeros((ny + 1, nx))
    hmean_max = V / area; eta_max = eta.copy(); vmax = np.zeros((ny, nx)); dur = np.zeros((ny, nx))
    zmin = P["zs"][..., 0]
    vol0 = float(V.sum()); v_rain = v_in = v_out = v_adj = 0.0
    t = 0.0; step = 0; max_res = 0.0; max_cfl = 0.0; nlim_steps = 0; max_lim_frac = 0.0
    nxt = 0.0; reg = []
    free = opts.boundary == "free_outflow"
    if opts.boundary not in ("closed", "free_outflow"):
        raise ValueError("Frontera desconocida.")
    while t < opts.end_seconds - 1e-8:
        if step >= opts.max_steps:
            raise RuntimeError("Límite de pasos alcanzado.")
        H = float(np.max(eta - zmin)) + 0.01
        dt = min(opts.max_dt, opts.cfl * dx / np.sqrt(g * H), opts.end_seconds - t)
        blk = int(np.searchsorted(edges, t + 1e-9, side="right") - 1)
        if blk < len(runoff):
            dt = min(dt, edges[blk + 1] - t)
        for e in ent:
            if t < e["t"][-1]:
                dt = min(dt, e["t"][int(np.searchsorted(e["t"], t + 1e-9, side="right"))] - t)

        def fuentes(d):
            s = np.zeros((ny, nx)); rv = 0.0
            if blk < len(runoff):
                s += runoff[blk] / 1000.0 * area * d / (edges[blk + 1] - edges[blk]); rv = float(s.sum())
            iv = []
            for e in ent:
                v_ = 0.5 * (np.interp(t, e["t"], e["q"], left=0, right=0) + np.interp(t + d, e["t"], e["q"], left=0, right=0)) * d
                np.add.at(s, (e["celdas"][:, 0], e["celdas"][:, 1]), v_ / len(e["celdas"]))
                iv.append(v_)
            return s, rv, iv
        src, rv, iv = fuentes(dt)
        cfl_paso = dt * np.sqrt(g * (H + float(src.max()) / area)) / dx
        if cfl_paso > opts.cfl * (1 + 1e-12):                      # el CFL se cumple con la profundidad tras el aporte
            dt = dt * opts.cfl / cfl_paso; src, rv, iv = fuentes(dt)
            cfl_paso = dt * np.sqrt(g * (H + float(src.max()) / area)) / dx
        _flujos(Qx, Qy, eta, P["ex"], P["exS"], P["ey"], P["eyS"], nman, ny, nx, m, rf, dx, g, dt, free, vfx, vfy)
        salida, ajuste, nlim, vmin = _limitar_y_actualizar(V, src, Qx, Qy, dt, ny, nx, area, hmean_max, vmax, dur, vfx, vfy, 0.3)
        _niveles(V, P["zs"], P["Sp"], P["Vlev"], ap, eta)
        np.maximum(eta_max, eta, out=eta_max)
        v_rain += rv; v_in += sum(iv); v_out += salida; v_adj += ajuste
        for e, v_ in zip(ent, iv): e["vol"] += v_
        t += dt; step += 1; max_cfl = max(max_cfl, cfl_paso)
        if nlim:
            nlim_steps += 1; max_lim_frac = max(max_lim_frac, nlim / (ny * nx))
        res = float(V.sum()) - (vol0 + v_rain + v_in - v_out + v_adj)
        max_res = max(max_res, abs(res))
        if t >= nxt - 1e-7:
            reg.append({"tiempo_s": t, "volumen_almacenado_m3": float(V.sum()), "volumen_escorrentia_m3": v_rain, "volumen_entrada_m3": v_in,
                        "volumen_salida_m3": v_out, "ajuste_redondeo_m3": v_adj, "residual_m3": res})
            nxt = t + opts.record_interval
            if progress: progress(t / opts.end_seconds, step)
        if not np.isfinite(V).all() or not np.isfinite(Qx).all():
            raise FloatingPointError("Estado no finito.")
    escala = max(vol0 + v_rain + v_in, 1.0)
    resumen = {"tiempo_final_h": t / 3600, "pasos": step, "frontera": opts.boundary, "volumen_inicial_m3": vol0, "volumen_escorrentia_m3": v_rain,
               "volumen_entrada_m3": v_in, "volumen_salida_m3": v_out, "volumen_final_m3": float(V.sum()), "ajuste_redondeo_m3": v_adj,
               "residual_final_m3": reg[-1]["residual_m3"] if reg else 0.0, "error_balance_max_pct": max_res / escala * 100,
               "CFL_max": max_cfl, "pasos_limitados": nlim_steps, "fraccion_celdas_limitadas_max": max_lim_frac,
               "calado_medio_max_m": float(hmean_max.max()), "velocidad_max_ms": float(vmax.max()), "estado": "final_completo",
               "entradas": {e["nombre"]: {"volumen_integrado_m3": e["vol"], "volumen_hidrograma_m3": e["esperado"], "diferencia_m3": e["vol"] - e["esperado"]} for e in ent}}
    return {"h_medio_max": hmean_max, "eta_max": eta_max, "vmax": vmax, "duracion_h_ge_03m": dur / 3600, "V_final": V, "eta_final": eta,
            "balance": reg, "resumen": resumen}
