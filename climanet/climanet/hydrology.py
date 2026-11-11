# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Hietogramas y SCS-CN con unidades y volumen explícitos, sin factor climático implícito."""
import numpy as np
INTEGRATE = np.trapezoid if hasattr(np, 'trapezoid') else np.trapz


def excess_scs(p_mm, cn, ia_ratio=0.2):
    cn = np.asarray(cn, dtype=float)
    if np.any(~np.isfinite(cn)) or np.any((cn <= 0) | (cn > 100)):
        raise ValueError('CN debe ser finito y estar en (0,100].')
    if np.any(np.asarray(p_mm) < 0):
        raise ValueError('La precipitación acumulada no puede ser negativa.')
    retention = 25400 / cn - 254
    initial = ia_ratio * retention
    positive = np.maximum(np.asarray(p_mm) - initial, 0)
    return np.divide(positive**2, positive + retention,
                     out=np.zeros_like(positive + retention), where=positive + retention > 0)


def alternating_blocks(durations_min, intensities_mmh, duration_min, block_min=5):
    d = np.asarray(durations_min, dtype=float)
    i = np.asarray(intensities_mmh, dtype=float)
    order = np.argsort(d); d, i = d[order], i[order]
    if np.any(~np.isfinite(i)) or np.any(i <= 0) or np.any(np.diff(d) <= 0):
        raise ValueError('IDF inválida o duraciones repetidas.')
    if duration_min < d[0] or duration_min > d[-1]:
        raise ValueError('La duración de tormenta debe estar dentro del soporte IDF.')
    count = int(round(duration_min / block_min))
    if not np.isclose(count * block_min, duration_min):
        raise ValueError('La duración debe ser múltiplo del bloque.')
    cumulative_d = np.arange(1, count + 1) * block_min
    intensity = np.exp(np.interp(np.log(cumulative_d), np.log(d), np.log(i)))
    cumulative_p = intensity * cumulative_d / 60
    increments = np.diff(np.r_[0, cumulative_p])
    if increments.min() < -1e-8:
        raise ValueError('La IDF tiene profundidad acumulada decreciente.')
    increments = np.sort(np.maximum(increments, 0))[::-1]
    arranged = np.empty(count)
    indices = [count//2]
    for k in range(1, count):
        j = count//2 - (k+1)//2 if k % 2 else count//2 + k//2
        indices.append(j)
    arranged[indices] = increments
    assert np.isclose(arranged.sum(), cumulative_p[-1])
    return np.arange(count + 1)*block_min*60., arranged


def gamma_m(prf):
    """Exponente M de la UH gamma de NRCS (q/qp = (t/tp e^(1-t/tp))^M) para un factor de pico PRF (484 -> M~3.7)."""
    from scipy.optimize import brentq
    from scipy.special import gammaln
    f = lambda m: 645.33*np.exp((m+1)*np.log(m) - m - gammaln(m+1)) - prf
    return brentq(f, 0.5, 60.0)


def uh_shape(times, tp, prf, forma='gamma'):
    """Ordenadas (1/s, área unitaria) del hidrograma unitario SCS en `times`."""
    if forma == 'triangular':
        tb = (1290.66/prf)*tp
        shape = np.where(times <= tp, times/tp, np.maximum((tb-times)/(tb-tp), 0))
    else:
        m = gamma_m(prf)
        x = np.maximum(times/tp, 1e-12)
        shape = (x*np.exp(1-x))**m
    return shape


def scs_hydrograph(block_mm, block_seconds, area_km2, cn, tc_h=None, lag_h=None, prf=484., imperv_frac=0., forma='gamma'):
    """Exporta Q(t) convolucionado y normaliza el HU para integral exacta por trapecios."""
    if lag_h is None:
        if tc_h is None:
            raise ValueError('Indicar tc_h o lag_h.')
        lag_h = 0.6*tc_h
    if area_km2 <= 0 or lag_h <= 0 or block_seconds <= 0 or prf <= 0:
        raise ValueError('Área, retardo, PRF y paso deben ser positivos.')
    pc = np.cumsum(block_mm)
    cumulative = (1-imperv_frac)*excess_scs(pc, float(cn)) + imperv_frac*pc   # fracción impermeable: toda la lluvia es exceso
    effective = np.diff(np.r_[0, cumulative])
    tp = block_seconds/2 + lag_h*3600
    tb = (1290.66/prf)*tp if forma == 'triangular' else min(14.0*tp, 4.0*(1290.66/prf)*tp)   # base finita; se renormaliza a área 1
    times = np.arange(0, np.ceil(tb/block_seconds)+1)*block_seconds
    shape = uh_shape(times, tp, prf, forma)
    shape[0] = shape[-1] = 0.0          # extremos nulos: el volumen por trapecios coincide con la suma discreta
    shape /= shape.sum()*block_seconds  # área unitaria exacta
    discharge = np.convolve(effective, shape) * area_km2 * 1000
    times_q = np.arange(len(discharge))*block_seconds
    volume = INTEGRATE(discharge, times_q)
    expected = float(cumulative[-1])*area_km2*1000
    if not np.isclose(volume, expected, rtol=1e-10):
        raise AssertionError('Hidrograma no conserva volumen de exceso.')
    return times_q, discharge, {'volumen_m3': float(volume), 'exceso_mm': float(cumulative[-1]),
             'Qpico_m3s': float(discharge.max()), 'Tpico_h': float(times_q[discharge.argmax()]/3600),
             'duracion_total_h': float(times_q[-1]/3600), 'area_km2': float(area_km2), 'CN': float(cn),
             'Tc_h': (float(tc_h) if tc_h is not None else None), 'lag_h': float(lag_h), 'PRF': float(prf), 'forma_UH': forma, 'factor_climatico': 1.0, 'uso': 'diseño histórico, no calibración'}
