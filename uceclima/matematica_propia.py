# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Matemática propia de hidro (módulo aislado y aditivo; no modifica climanet ni el flujo existente).

Contiene cuatro herramientas de matemática pura, con código propio y ecuaciones publicadas:
  perdidas_scs      Pérdidas SCS-CN (NRCS NEH-4 cap. 10) con fracción impermeable f y λ explícito.
  uh_scs            Hidrograma unitario SCS triangular con factor de pico PRF (484 estándar, 284 Delmarva).
  muskingum_cunge   Tránsito Muskingum-Cunge con coeficientes de Ponce y Yevjevich (1978).
  dt_courant        Paso de tiempo por Courant para onda de gravedad y diagnóstico de C, D de un tramo.

Unidades: lluvia y exceso en mm; área en km²; tiempo en h salvo `dt_s` (s); caudal en m³/s; longitudes en m.
Nada aquí calibra ni predice: son diagnósticos numéricos «sin calibrar». Cada función devuelve un dict con
`avisos` (lista de textos) en lugar de corregir en silencio los datos del usuario.
Datos inválidos (NaN, negativos, fuera de dominio) -> ValueError con mensaje; casos secos -> ceros explícitos.
"""
import math
import numpy as np

# Conversión exacta de PRF (ft³/s por mi² por in, ×h) a m³/s por km² por mm, ×h:  484 -> 0,20833 (el documento local usa 0,208).
_K_PRF = (0.028316846592 / (2.589988110336 * 25.4))
_INTEGRAR = np.trapezoid if hasattr(np, "trapezoid") else np.trapz


def _vector(x, nombre, no_negativo=True):
    a = np.atleast_1d(np.asarray(x, dtype=float))
    if a.ndim != 1 or a.size == 0:
        raise ValueError(f"{nombre} debe ser una serie 1-D no vacía.")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{nombre} contiene NaN o valores infinitos.")
    if no_negativo and np.any(a < 0):
        raise ValueError(f"{nombre} no puede ser negativo.")
    return a


def _positivo(x, nombre):
    v = float(x)
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"{nombre} debe ser finito y mayor que 0 (recibido {x}).")
    return v


# ---------------------------------------------------------------- 1. pérdidas
def perdidas_scs(p_acum_mm, cn, lam=0.2, f_imp=0.0):
    """Exceso acumulado e incremental. S = 25400/CN − 254 (mm); Ia = λ·S; Pe = (P−Ia)²/(P−Ia+S) si P>Ia.
    Con fracción impermeable f: Pe_total = f·P + (1−f)·Pe(P)  (convención del documento local; toda la lluvia de la
    fracción impermeable pasa a exceso). La lluvia debe entrar ACUMULADA y no decreciente."""
    p = _vector(p_acum_mm, "p_acum_mm")
    cn = float(cn)
    if not math.isfinite(cn) or not (0 < cn <= 100):
        raise ValueError("CN debe estar en (0, 100].")
    lam = float(lam)
    if not math.isfinite(lam) or not (0 <= lam <= 1):
        raise ValueError("λ debe estar en [0, 1].")
    f = float(f_imp)
    if not math.isfinite(f) or not (0 <= f <= 1):
        raise ValueError("La fracción impermeable debe estar en [0, 1].")
    if np.any(np.diff(p) < -1e-12):
        raise ValueError("La lluvia acumulada no puede decrecer (¿entregó incrementos en vez de acumulados?).")
    avisos = []
    if not (0.05 <= lam <= 0.3):
        avisos.append(f"λ={lam} fuera del rango usual 0,05–0,3 de la literatura: declarar su fuente.")
    if cn < 30:
        avisos.append(f"CN={cn:.1f} < 30: fuera del rango práctico del método.")
    s = 25400.0 / cn - 254.0
    ia = lam * s
    util = np.maximum(p - ia, 0.0)
    den = util + s
    pe = np.divide(util ** 2, den, out=np.zeros_like(den), where=den > 0)
    total = f * p + (1.0 - f) * pe
    inc = np.diff(np.r_[0.0, total])
    if p[-1] == 0:
        avisos.append("Caso seco: lluvia total 0 -> exceso 0.")
    return {"exceso_acum_mm": total, "exceso_inc_mm": np.maximum(inc, 0.0), "S_mm": s, "Ia_mm": ia,
            "coef_escorrentia": float(total[-1] / p[-1]) if p[-1] > 0 else 0.0, "avisos": avisos}


# ---------------------------------------------------------------- 2. hidrograma unitario SCS
def uh_scs(area_km2, lag_h, dt_h, prf=484.0, tp_incluye_dt=True):
    """UH triangular. tp = Δt/2 + Lag (h). qp = k·PRF·A/tp (m³/s por mm) con k = conversión exacta de unidades.
    La base Tb sale de imponer volumen 1 mm sobre A:  Tb = 2000·tp/(3600·k·PRF) = 1290,7·tp/PRF
    (PRF 484 -> Tb = 2,667·tp; PRF 284 -> 4,545·tp). Las ordenadas son promedios exactos por intervalo Δt, de modo que
    Σ u·Δt = 1000·A (m³ por mm) EXACTO y la convolución conserva el volumen."""
    a = _positivo(area_km2, "area_km2"); lag = _positivo(lag_h, "lag_h"); dt = _positivo(dt_h, "dt_h"); prf = _positivo(prf, "prf")
    avisos = []
    if not (100 <= prf <= 600):
        avisos.append(f"PRF={prf} fuera de 100–600 (rango de las tablas NEH cap. 16).")
    tp = (dt / 2.0 if tp_incluye_dt else 0.0) + lag
    qp = _K_PRF * prf * a / tp
    tb = 2000.0 * a / (3600.0 * qp)             # h; área = ½·qp·tb·3600 = 1000·A
    n = int(math.ceil(tb / dt - 1e-12))

    def acumulada(t):                            # integral de la forma triangular (adimensional, pico 1) de 0 a t
        t = np.minimum(t, tb)
        return np.where(t <= tp, 0.5 * t * t / tp, 0.5 * tp + (t - tp) * (1.0 - 0.5 * (t - tp) / (tb - tp)))
    t_ext = np.arange(0, n + 1) * dt
    area_int = np.diff(acumulada(t_ext))         # h por intervalo
    u = area_int / area_int.sum() * (1000.0 * a / 3600.0) / dt     # m³/s por mm, promedio por intervalo
    return {"u_m3s_mm": u, "t_h": np.arange(1, n + 1) * dt, "tp_h": tp, "tb_h": tb, "qp_m3s_mm": qp,
            "tb_sobre_tp": tb / tp, "avisos": avisos}


def convolver(exceso_inc_mm, u_m3s_mm, dt_h):
    """Q(j) = Σ pe(i)·u(j−i). Conserva volumen: Σ Q·Δt = Σ pe · 1000·A."""
    pe = _vector(exceso_inc_mm, "exceso_inc_mm"); u = _vector(u_m3s_mm, "u_m3s_mm"); dt = _positivo(dt_h, "dt_h")
    q = np.convolve(pe, u)
    return {"q_m3s": q, "t_h": np.arange(1, len(q) + 1) * dt, "volumen_m3": float(q.sum() * dt * 3600.0)}


# ---------------------------------------------------------------- 3. Muskingum-Cunge
def coeficientes_mc(c_ms, dt_s, dx_m, q_m3s, ancho_m, s0):
    """C = c·Δt/Δx ; D = Q/(B·S0·c·Δx) ; X = ½(1−D) ; K = Δx/c.  C0=(−1+C+D)/(1+C+D), C1=(1+C−D)/(1+C+D), C2=(1−C+D)/(1+C+D)."""
    c = _positivo(c_ms, "c_ms"); dt = _positivo(dt_s, "dt_s"); dx = _positivo(dx_m, "dx_m")
    b = _positivo(ancho_m, "ancho_m"); s0 = _positivo(s0, "s0")
    q = float(q_m3s)
    if not math.isfinite(q) or q < 0:
        raise ValueError("q_m3s debe ser finito y no negativo.")
    cou = c * dt / dx
    d = q / (b * s0 * c * dx)
    den = 1.0 + cou + d
    c0, c1, c2 = (-1.0 + cou + d) / den, (1.0 + cou - d) / den, (1.0 - cou + d) / den
    return {"C": cou, "D": d, "X": 0.5 * (1.0 - d), "K_s": dx / c, "C0": c0, "C1": c1, "C2": c2}


def muskingum_cunge(q_in, dt_s, dx_m, c_ms, ancho_m, s0, cola=True, max_cola_pasos=100000, recortar_negativos=True):
    """Tránsito de un tramo. `c_ms` y `ancho_m` pueden ser números (parámetros constantes, con el caudal de referencia
    = pico de entrada) o funciones de Q (parámetros variables; el caudal de referencia en cada paso es la media de I(t),
    I(t+Δt) y O(t), esquema de tres puntos). Estado inicial O(0)=I(0). Si D>1 (X<0) se limita D a 1 (X=0) y se cuenta;
    si C0<0 puede aparecer salida negativa: con recortar_negativos=True (defecto) se limita a 0 y se reporta el volumen
    recortado (el recorte añade masa); con False se conserva la masa exacta pero pueden quedar valores negativos. Nunca se corrige en silencio."""
    q_in = _vector(q_in, "q_in"); dt = _positivo(dt_s, "dt_s"); dx = _positivo(dx_m, "dx_m"); s0 = _positivo(s0, "s0")
    variable = callable(c_ms) or callable(ancho_m)
    cf = c_ms if callable(c_ms) else (lambda q, v=_positivo(c_ms, "c_ms"): v)
    bf = ancho_m if callable(ancho_m) else (lambda q, v=_positivo(ancho_m, "ancho_m"): v)
    avisos = []
    q = q_in.copy()
    if cola:
        # prolongar con ceros hasta drenar el almacenamiento; el límite es explícito
        c_ref = cf(float(q_in.max())); extra = int(min(max_cola_pasos, math.ceil(12.0 * dx / c_ref / dt) + 1))
        q = np.r_[q, np.zeros(extra)]
    if q_in.max() == 0:
        return {"q_out_m3s": np.zeros_like(q), "coef": None, "n_D_limitado": 0, "n_C0_negativo": 0, "volumen_negativo_cortado_m3": 0.0,
                "volumen_in_m3": 0.0, "volumen_out_m3": 0.0, "error_balance_rel": 0.0, "variable": variable,
                "avisos": ["Caso seco: caudal de entrada 0 -> salida 0."]}
    out = np.zeros_like(q); out[0] = q[0]
    n_d = n_c0 = 0; cortado = 0.0
    ref_const = float(q_in.max())
    coef_hist = []
    for i in range(1, len(q)):
        qref = (q[i] + q[i - 1] + out[i - 1]) / 3.0 if variable else ref_const
        k = coeficientes_mc(cf(qref), dt, dx, qref, bf(qref), s0)
        if k["D"] > 1.0:
            n_d += 1; d = 1.0; den = 1.0 + k["C"] + d
            k.update(D=d, X=0.0, C0=(-1 + k["C"] + d) / den, C1=(1 + k["C"] - d) / den, C2=(1 - k["C"] + d) / den)
        if k["C0"] < 0:
            n_c0 += 1
        coef_hist.append(k)
        v = k["C0"] * q[i] + k["C1"] * q[i - 1] + k["C2"] * out[i - 1]
        if v < 0 and recortar_negativos:
            cortado += -v * dt; v = 0.0
        out[i] = v
    vin = float(q_in.sum() * dt); vout = float(out.sum() * dt)
    if n_d:
        avisos.append(f"D>1 en {n_d} pasos (X<0): se limitó D=1 (X=0). Elegir Δx ≥ Q/(B·S0·c) o aceptar la difusión extra.")
    if n_c0:
        avisos.append(f"C0<0 en {n_c0} pasos (C+D<1): riesgo de oscilación; reducir Δt o aumentar Δx.")
    if cortado > 0:
        avisos.append(f"Se recortó salida negativa: {cortado:.3g} m³ (el recorte añade masa a la salida).")
    if variable:
        avisos.append("Parámetros variables: el balance de masa no es exacto (limitación conocida del método de tres puntos).")
    return {"q_out_m3s": out, "coef": coef_hist[0] if not variable else coef_hist, "n_D_limitado": n_d, "n_C0_negativo": n_c0,
            "volumen_negativo_cortado_m3": cortado, "volumen_in_m3": vin, "volumen_out_m3": vout,
            "error_balance_rel": (vout - vin) / vin, "variable": variable, "avisos": avisos}


# ---------------------------------------------------------------- 4. diagnóstico de paso temporal
def dt_courant(dx_m, h_m, u_ms, alfa=0.7, g=9.80665, h_min=1e-3):
    """Δt = α·min(Δx/(|u|+√(g·h))) sobre celdas mojadas (h ≥ h_min). Celdas secas excluidas (se cuentan). Si todo está
    seco devuelve dt=inf con aviso (no hay restricción). α en (0, 1]."""
    dx = np.atleast_1d(np.asarray(dx_m, float)); h = np.atleast_1d(np.asarray(h_m, float)); u = np.atleast_1d(np.asarray(u_ms, float))
    if not (dx.shape == h.shape == u.shape or dx.size == 1):
        raise ValueError("dx, h y u deben tener la misma forma (o dx escalar).")
    if not (np.all(np.isfinite(h)) and np.all(np.isfinite(u)) and np.all(np.isfinite(dx))):
        raise ValueError("dx, h o u contienen NaN o infinitos.")
    if np.any(dx <= 0):
        raise ValueError("dx debe ser > 0.")
    if np.any(h < 0):
        raise ValueError("La profundidad no puede ser negativa.")
    alfa = float(alfa)
    if not (0 < alfa <= 1):
        raise ValueError("α debe estar en (0, 1].")
    mojada = h >= h_min
    dxb = np.broadcast_to(dx, h.shape)
    if not mojada.any():
        return {"dt_s": math.inf, "celdas_secas": int(h.size), "celda_critica": None,
                "avisos": ["Todas las celdas están secas: sin restricción de Courant."]}
    vel = np.abs(u) + np.sqrt(g * h)
    cand = np.where(mojada, dxb / np.where(mojada, vel, 1.0), np.inf)
    k = int(np.argmin(cand))
    return {"dt_s": float(alfa * cand[k]), "celdas_secas": int((~mojada).sum()), "celda_critica": k, "avisos": []}


def diagnostico_tramo(c_ms, dt_s, dx_m, q_m3s, ancho_m, s0):
    """Reporta C, D, X, K y los coeficientes del tramo y marca situaciones problemáticas. No cambia nada."""
    k = coeficientes_mc(c_ms, dt_s, dx_m, q_m3s, ancho_m, s0)
    banderas = []
    if k["D"] > 1:
        banderas.append("D>1 (X<0): Δx menor que Q/(B·S0·c)")
    if k["C0"] < 0:
        banderas.append("C0<0 (C+D<1): posible salida negativa")
    if k["C2"] < 0:
        banderas.append("C2<0 (C>1+D)")
    k["dx_min_X_no_negativo_m"] = q_m3s / (ancho_m * s0 * c_ms)
    k["banderas"] = banderas
    return k
