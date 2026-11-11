# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Prototipo de inercia local con caras conservativas y limitador de volumen saliente.

No certifica hidráulica urbana ni representa mareas. Los bordes cerrados o de
salida libre son hipótesis de sensibilidad; las celdas nodata son paredes.
"""
from dataclasses import dataclass
from pathlib import Path
import json, os, time
import numpy as np


@dataclass
class Options:
    dx: float
    dy: float
    end_seconds: float
    max_dt: float = 5.0
    cfl: float = 0.35
    boundary: str = 'closed'
    gravity: float = 9.81
    wet_epsilon: float = 1e-6
    max_steps: int = 500000
    record_interval: float = 300.0
    backend: str = 'numpy'
    frame_interval: float = 0.0        # >0: guarda una «foto» del calado cada tantos segundos (solo para ver la evolución; no altera el cálculo)
    bordes_libres: object = None       # G22: (oeste[ny], este[ny], norte[nx], sur[nx]) booleanos; None = todo el borde libre (si boundary='free_outflow')


def simulate(dem, active, manning, edges_s, runoff_mm, options,
             initial_depth=None, discharge_times=None, discharge_values=None, inlet=None,
             progress=None, sections=None, probes=None, inlets=None,
             checkpoint=None, checkpoint_every_s=600.0, resume=False, on_checkpoint=None):
    z = np.asarray(dem, dtype=float)
    active = np.asarray(active, dtype=bool)
    n = np.asarray(manning, dtype=float)
    o = options
    if o.backend not in ['numpy','numba']:
        raise ValueError('Backend desconocido.')
    if o.backend=='numba':
        from .accel import hydraulic_step
    if z.shape != active.shape or n.shape != z.shape or not active.any():
        raise ValueError('Grillas incompatibles o sin celdas activas.')
    if not np.isfinite(z[active]).all() or not np.isfinite(n[active]).all() or np.any(n[active] <= 0):
        raise ValueError('Terreno y Manning deben ser válidos en todo el dominio.')
    if o.boundary not in ['closed', 'free_outflow']:
        raise ValueError('Frontera desconocida.')
    if o.bordes_libres is None:
        lib_o = np.ones(z.shape[0], dtype=np.bool_); lib_e = lib_o.copy(); lib_n = np.ones(z.shape[1], dtype=np.bool_); lib_s = lib_n.copy()
    else:
        lib_o, lib_e, lib_n, lib_s = [np.asarray(m_, dtype=np.bool_) for m_ in o.bordes_libres]
        if lib_o.shape != (z.shape[0],) or lib_e.shape != (z.shape[0],) or lib_n.shape != (z.shape[1],) or lib_s.shape != (z.shape[1],):
            raise ValueError('bordes_libres: tamaños incompatibles con la malla.')
    if min(o.dx, o.dy, o.end_seconds, o.max_dt, o.record_interval) <= 0:
        raise ValueError('Opciones deben ser positivas.')
    if not 0 < o.cfl <= 0.5:
        raise ValueError('CFL del prototipo debe estar en (0,0.5].')
    edges = np.asarray(edges_s, dtype=float)
    runoff = np.asarray(runoff_mm, dtype=float)
    if runoff.shape != (len(edges)-1, *z.shape) or edges[0] != 0 or np.any(np.diff(edges) <= 0):
        raise ValueError('Forzamiento requiere límites de intervalos y mm por celda/intervalo.')
    if not np.isfinite(runoff[:, active]).all() or np.any(runoff[:, active] < 0):
        raise ValueError('Escorrentía debe ser no negativa y finita.')
    if edges[-1] > o.end_seconds:
        raise ValueError('Simulación terminaría antes de completar la lluvia.')
    # Entradas de caudal: cada una con SU hidrograma y SUS celdas (el volumen de una entrada nunca se reparte a otra).
    # inlets: [{'nombre': str, 't': [s], 'q': [m3/s], 'celdas': [[fila, col], ...]}]. Los argumentos discharge_*/inlet
    # (una sola entrada) se mantienen por compatibilidad.
    if inlets is None:
        inlets = []
        if discharge_times is not None:
            inlets = [{'nombre': 'entrada_unica', 't': discharge_times, 'q': discharge_values, 'celdas': inlet}]
    elif discharge_times is not None:
        raise ValueError('Usar inlets o discharge_*, no ambos.')
    entradas = []
    for k, e_ in enumerate(inlets):
        nombre = str(e_.get('nombre', f'entrada_{k}'))
        if any(x['nombre'] == nombre for x in entradas):
            raise ValueError(f'Nombre de entrada repetido: {nombre}')
        qt_ = np.asarray(e_['t'], dtype=float); qv_ = np.asarray(e_['q'], dtype=float)
        if qt_.shape != qv_.shape or len(qt_) < 2 or qt_[0] != 0 or np.any(np.diff(qt_) <= 0) or np.any(qv_ < 0):
            raise ValueError(f'Hidrograma inválido en {nombre}.')
        if not np.isfinite(qv_).all() or qt_[-1] > o.end_seconds or qv_[-1] != 0:
            raise ValueError(f'Hidrograma de {nombre} debe ser finito, completo y terminar en cero.')
        cells_ = np.asarray(e_['celdas'], dtype=int)
        if cells_.ndim != 2 or cells_.shape[1] != 2 or not len(cells_):
            raise ValueError(f'Entrada {nombre} requiere lista de celdas.')
        if not active[cells_[:,0], cells_[:,1]].all() or len(set(map(tuple,cells_))) != len(cells_):
            raise ValueError(f'Celdas de la entrada {nombre} deben ser activas y únicas.')
        entradas.append({'nombre': nombre, 't': qt_, 'q': qv_, 'celdas': cells_, 'volumen_m3': 0.0,
                         'volumen_esperado_m3': float((np.trapezoid if hasattr(np, 'trapezoid') else np.trapz)(qv_, qt_))})
    z = np.where(active, z, 0)
    n = np.where(active, n, 0.04)
    h = np.zeros(z.shape) if initial_depth is None else np.array(initial_depth, dtype=float, copy=True)
    if h.shape != z.shape or np.any(h[active] < 0) or not np.isfinite(h[active]).all():
        raise ValueError('Profundidad inicial inválida.')
    h[~active] = 0
    ny, nx = z.shape
    area = o.dx*o.dy
    qx = np.zeros((ny,nx+1)); qy = np.zeros((ny+1,nx))
    valid_x = active[:,:-1] & active[:,1:]
    valid_y = active[:-1,:] & active[1:,:]
    zx = np.maximum(z[:,:-1],z[:,1:]); zy = np.maximum(z[:-1,:],z[1:,:])
    nxface = (n[:,:-1]+n[:,1:])/2; nyface = (n[:-1,:]+n[1:,:])/2
    hmax = h.copy(); vmax = np.zeros_like(h); duration = np.zeros_like(h)
    initial_volume = h.sum()*area
    runoff_volume = inflow_volume = outflow_volume = correction_volume = 0.
    maximum_residual = 0.; maximum_cfl = 0.; limited_steps = 0
    maximum_limited_fraction = 0.
    t = 0.; step = 0; next_record = 0.; records = []
    # Seguimiento de transporte (solo diagnóstico, no altera el cálculo):
    #  sections: {nombre: (eje, índice_cara, (lo, hi))}  eje 'x' = cara vertical entre columnas (+ hacia columnas crecientes),
    #            'y' = cara horizontal entre filas (+ hacia filas crecientes). Q en m3/s.
    #  probes:   {nombre: (fila, columna)} serie de calado.
    sections = sections or {}; probes = probes or {}
    sec_vol = {k: 0. for k in sections}; sec_q = {k: [] for k in sections}; probe_h = {k: [] for k in probes}; tr_t = []

    def seguimiento(dt_step):
        for k, (axis, idx, (lo, hi)) in sections.items():
            q = float(qx[lo:hi, idx].sum()*o.dy) if axis == 'x' else float(qy[idx, lo:hi].sum()*o.dx)
            sec_vol[k] += q*dt_step

    def record():
        stored = float(h.sum()*area)
        residual = stored - (initial_volume+runoff_volume+inflow_volume-outflow_volume+correction_volume)
        return {'tiempo_s': t, 'volumen_almacenado_m3': stored,
          'volumen_escorrentia_m3': runoff_volume, 'volumen_entrada_m3': inflow_volume,
          'volumen_salida_m3': outflow_volume, 'ajuste_redondeo_m3': correction_volume,
          'residual_m3': residual, 'profundidad_max_m': float(h.max())}

    def registrar_series():
        tr_t.append(t)
        for k, (axis, idx, (lo, hi)) in sections.items():
            sec_q[k].append(float(qx[lo:hi, idx].sum()*o.dy) if axis == 'x' else float(qy[idx, lo:hi].sum()*o.dx))
        for k, (r_, c_) in probes.items():
            probe_h[k].append(float(h[r_, c_]))

    fotos_t, fotos_h = [], []; next_frame = [0.]

    def foto(forzar=False):
        if o.frame_interval > 0 and (forzar or t >= next_frame[0]-1e-7):
            fotos_t.append(t); fotos_h.append(h.astype(np.float16)); next_frame[0] = t+o.frame_interval

    records.append(record()); registrar_series(); foto(True)
    # Eta (Mejora 1): punto de control para reanudar tras un corte de luz o un cierre. Se escribe cada `checkpoint_every_s` segundos
    # de reloj, en un archivo temporal que luego se renombra (nunca queda a medias). Las fotos van en partes aparte para no
    # reescribir todo cada vez. Al reanudar se carga el estado completo y el cálculo sigue idéntico al de una corrida sin cortes.
    ckpt = Path(checkpoint) if checkpoint else None
    firma = {'forma': list(z.shape), 'activas': int(active.sum()), 'fin_s': float(o.end_seconds), 'dx': float(o.dx), 'dy': float(o.dy),
             'suma_z': float(np.round(z[active].sum(), 3)), 'suma_escorrentia': float(np.round(runoff.sum(), 3)), 'entradas': [e_['nombre'] for e_ in entradas]}
    reloj_ckpt = [time.time()]; fotos_guardadas = [0]
    if ckpt is not None and resume and ckpt.exists():
        with np.load(ckpt, allow_pickle=False) as F:
            meta_ = json.loads(str(F['meta']))
            if meta_['firma'] != firma:
                raise ValueError('El punto de control no corresponde a esta corrida (cambiaron el terreno, la lluvia o las entradas): no se puede reanudar.')
            h = np.ascontiguousarray(F['h'], dtype=float); qx = np.ascontiguousarray(F['qx'], dtype=float); qy = np.ascontiguousarray(F['qy'], dtype=float)
            hmax = np.ascontiguousarray(F['hmax'], dtype=float); vmax = np.ascontiguousarray(F['vmax'], dtype=float); duration = np.ascontiguousarray(F['duration'], dtype=float)
        t = meta_['t']; step = meta_['step']; next_record = meta_['next_record']; next_frame[0] = meta_['next_frame']
        initial_volume = meta_['initial_volume']; runoff_volume = meta_['runoff_volume']; inflow_volume = meta_['inflow_volume']
        outflow_volume = meta_['outflow_volume']; correction_volume = meta_['correction_volume']
        maximum_residual = meta_['maximum_residual']; maximum_cfl = meta_['maximum_cfl']; limited_steps = meta_['limited_steps']
        maximum_limited_fraction = meta_['maximum_limited_fraction']; records = meta_['records']
        sec_vol.update(meta_['sec_vol']); sec_q.update(meta_['sec_q']); probe_h.update(meta_['probe_h']); tr_t[:] = meta_['tr_t']
        for e_ in entradas: e_['volumen_m3'] = meta_['entradas_vol'][e_['nombre']]
        fotos_t[:] = []; fotos_h[:] = []
        for k_ in range(meta_['partes_fotos']):
            with np.load(ckpt.with_name(f'{ckpt.stem}_fotos_{k_:04d}.npz'), allow_pickle=False) as P_:
                fotos_t.extend(P_['t'].tolist()); fotos_h.extend(list(P_['h']))
        fotos_t[:] = fotos_t[:meta_['n_fotos']]; fotos_h[:] = fotos_h[:meta_['n_fotos']]
        fotos_guardadas[0] = meta_['n_fotos']; partes_ = meta_['partes_fotos']
        if progress is not None: progress(t/o.end_seconds, step)
    else:
        partes_ = 0
    partes_fotos = [partes_]

    def punto_control(forzar=False):
        if ckpt is None or (not forzar and time.time()-reloj_ckpt[0] < checkpoint_every_s):
            return
        nuevas = len(fotos_t) - fotos_guardadas[0]
        if nuevas > 0:
            pf = ckpt.with_name(f'{ckpt.stem}_fotos_{partes_fotos[0]:04d}.npz'); tmpf = pf.with_name(pf.stem + '.tmp.npz')
            np.savez(tmpf, t=np.asarray(fotos_t[fotos_guardadas[0]:]), h=np.stack(fotos_h[fotos_guardadas[0]:])); os.replace(tmpf, pf)
            partes_fotos[0] += 1; fotos_guardadas[0] = len(fotos_t)
        meta_ = {'firma': firma, 't': t, 'step': step, 'next_record': next_record, 'next_frame': next_frame[0],
                 'initial_volume': initial_volume, 'runoff_volume': runoff_volume, 'inflow_volume': inflow_volume, 'outflow_volume': outflow_volume,
                 'correction_volume': correction_volume, 'maximum_residual': maximum_residual, 'maximum_cfl': maximum_cfl, 'limited_steps': limited_steps,
                 'maximum_limited_fraction': maximum_limited_fraction, 'records': records, 'sec_vol': sec_vol, 'sec_q': sec_q, 'probe_h': probe_h,
                 'tr_t': tr_t, 'entradas_vol': {e_['nombre']: e_['volumen_m3'] for e_ in entradas}, 'partes_fotos': partes_fotos[0], 'n_fotos': len(fotos_t),
                 'guardado': time.strftime('%Y-%m-%dT%H:%M:%S'), 'progreso': t/o.end_seconds}
        tmp = ckpt.with_name(ckpt.stem + '.tmp.npz')
        np.savez(tmp, h=h, qx=qx, qy=qy, hmax=hmax, vmax=vmax, duration=duration, meta=np.array(json.dumps(meta_)))
        os.replace(tmp, ckpt); reloj_ckpt[0] = time.time()
        if on_checkpoint is not None: on_checkpoint(meta_)

    while t < o.end_seconds-1e-8:
        if step >= o.max_steps:
            raise RuntimeError('Límite de pasos alcanzado antes del final del evento.')
        # CFL explícito del esquema inercial; la velocidad advectiva no está resuelta.
        dt = min(o.max_dt, o.cfl*min(o.dx,o.dy)/np.sqrt(o.gravity*max(float(h.max()),0.01)),o.end_seconds-t)
        block = np.searchsorted(edges, t+1e-9, side='right')-1
        if block < len(runoff):
            dt = min(dt, edges[block+1]-t)
        for e_ in entradas:
            if t < e_['t'][-1]:
                iq = np.searchsorted(e_['t'],t+1e-9,side='right')
                dt = min(dt,e_['t'][iq]-t)
        if dt <= 1e-8:
            raise RuntimeError('Paso temporal degenerado.')
        def forcing(dt):
            src = np.zeros_like(h); rv = iv = 0.
            if block < len(runoff):
                src = np.where(active,runoff[block],0)/1000*dt/(edges[block+1]-edges[block])
                rv = float(src.sum()*area)
            iv_k = []
            for e_ in entradas:
                qstart = np.interp(t,e_['t'],e_['q'],left=0,right=0)
                qend = np.interp(t+dt,e_['t'],e_['q'],left=0,right=0)
                ivk = 0.5*(qstart+qend)*dt
                np.add.at(src, (e_['celdas'][:,0], e_['celdas'][:,1]), ivk/len(e_['celdas'])/area)   # reparto SOLO entre las celdas de esta entrada
                iv_k.append(ivk); iv += ivk
            return src, rv, iv, iv_k
        source, rv, iv, iv_k = forcing(dt)
        # El CFL debe cumplirse con la profundidad DESPUÉS de añadir el aporte de este paso.
        dt_cfl = o.cfl*min(o.dx,o.dy)/np.sqrt(o.gravity*max(float((h+source).max()),0.01))
        if dt_cfl < dt*(1-1e-12):
            dt = dt_cfl
            source, rv, iv, iv_k = forcing(dt)
        runoff_volume += rv; inflow_volume += iv
        for e_, v_ in zip(entradas, iv_k): e_['volumen_m3'] += v_
        available = h+source
        cfl_step = dt*np.sqrt(o.gravity*max(float(available.max()),0.01))/min(o.dx,o.dy)
        if o.backend=='numba':
            ov,cv,nlimited,minimum = hydraulic_step(z,active,n,h,available,qx,qy,hmax,vmax,duration,
                        dt,o.dx,o.dy,o.gravity,o.wet_epsilon,o.boundary=='free_outflow',lib_o,lib_e,lib_n,lib_s)
            if minimum < -1e-10:
                raise FloatingPointError('El limitador no preservó positividad.')
            outflow_volume+=ov;correction_volume+=cv
            if sections: seguimiento(dt)
            if nlimited:
                limited_steps+=1
                maximum_limited_fraction=max(maximum_limited_fraction,nlimited/active.sum())
            maximum_cfl=max(maximum_cfl,cfl_step)
            t+=dt;step+=1
            residual=float(h.sum()*area)-(initial_volume+runoff_volume+inflow_volume-outflow_volume+correction_volume)
            maximum_residual=max(maximum_residual,abs(residual))
            if not np.isfinite(h).all() or not np.isfinite(qx).all() or not np.isfinite(qy).all():
                raise FloatingPointError('Estado hidráulico no finito.')
            foto()
            if t>=next_record-1e-7:
                records.append(record());next_record=t+o.record_interval;registrar_series()
                punto_control()
                if progress is not None:progress(t/o.end_seconds,step)
            continue
        eta = z+h
        hf_x = np.maximum(np.maximum(eta[:,:-1],eta[:,1:])-zx,0)
        hf_y = np.maximum(np.maximum(eta[:-1,:],eta[1:,:])-zy,0)
        old_x = qx[:,1:-1]; old_y = qy[1:-1,:]
        safe_x = np.maximum(hf_x,o.wet_epsilon); safe_y = np.maximum(hf_y,o.wet_epsilon)
        qx[:,1:-1] = np.where(valid_x & (hf_x>o.wet_epsilon),
          (old_x-o.gravity*hf_x*dt*(eta[:,1:]-eta[:,:-1])/o.dx)/
          (1+o.gravity*dt*nxface**2*np.abs(old_x)/safe_x**(7/3)),0)
        qy[1:-1,:] = np.where(valid_y & (hf_y>o.wet_epsilon),
          (old_y-o.gravity*hf_y*dt*(eta[1:,:]-eta[:-1,:])/o.dy)/
          (1+o.gravity*dt*nyface**2*np.abs(old_y)/safe_y**(7/3)),0)
        qx[:,0]=qx[:,-1]=0; qy[0,:]=qy[-1,:]=0
        if o.boundary == 'free_outflow':
            # Sensibilidad con vertido libre al borde. No sustituye una BC de marea.
            qx[:,0] = -np.where(active[:,0] & lib_o, h[:,0]*np.sqrt(o.gravity*h[:,0]),0)
            qx[:,-1] = np.where(active[:,-1] & lib_e, h[:,-1]*np.sqrt(o.gravity*h[:,-1]),0)
            qy[0,:] = -np.where(active[0,:] & lib_n, h[0,:]*np.sqrt(o.gravity*h[0,:]),0)
            qy[-1,:] = np.where(active[-1,:] & lib_s, h[-1,:]*np.sqrt(o.gravity*h[-1,:]),0)
        outgoing = (np.maximum(qx[:,1:],0)+np.maximum(-qx[:,:-1],0))*o.dy + \
                   (np.maximum(qy[1:,:],0)+np.maximum(-qy[:-1,:],0))*o.dx
        fraction = np.ones_like(h)
        np.divide(available*area,dt*outgoing,out=fraction,where=outgoing>0)
        fraction = np.minimum(fraction,1)
        limited = active & (fraction<1-1e-12)
        if limited.any():
            limited_steps += 1
            maximum_limited_fraction = max(maximum_limited_fraction,float(limited.sum()/active.sum()))
        qx[:,1:-1] *= np.where(qx[:,1:-1]>=0,fraction[:,:-1],fraction[:,1:])
        qy[1:-1,:] *= np.where(qy[1:-1,:]>=0,fraction[:-1,:],fraction[1:,:])
        qx[:,0] *= fraction[:,0]; qx[:,-1] *= fraction[:,-1]
        qy[0,:] *= fraction[0,:]; qy[-1,:] *= fraction[-1,:]
        ov = dt*(o.dy*(qx[:,-1].sum()-qx[:,0].sum())+o.dx*(qy[-1,:].sum()-qy[0,:].sum()))
        outflow_volume += float(ov)
        if sections: seguimiento(dt)
        new_h = available + dt*((qx[:,:-1]-qx[:,1:])/o.dx+(qy[:-1,:]-qy[1:,:])/o.dy)
        if new_h[active].min() < -1e-10:
            raise FloatingPointError('El limitador no preservó positividad.')
        correction_volume += float(-new_h[new_h<0].sum()*area)
        h = np.maximum(new_h,0); h[~active]=0
        if not np.isfinite(h).all() or not np.isfinite(qx).all() or not np.isfinite(qy).all():
            raise FloatingPointError('Estado hidráulico no finito.')
        hmax = np.maximum(hmax,h)
        # Velocidad de celda diagnosticada solo cuando h>=5cm (G17, Delta: con 1 cm salían 22 m/s irreales); sin cap de 5m/s.
        wet = h >= 0.05
        vx = np.divide((qx[:,:-1]+qx[:,1:])/2,h,out=np.zeros_like(h),where=wet)
        vy = np.divide((qy[:-1,:]+qy[1:,:])/2,h,out=np.zeros_like(h),where=wet)
        vmax = np.maximum(vmax,np.hypot(vx,vy))
        duration += dt*(h>=0.3)
        maximum_cfl=max(maximum_cfl,float(cfl_step))
        t += dt; step += 1
        residual = float(h.sum()*area)-(initial_volume+runoff_volume+inflow_volume-outflow_volume+correction_volume)
        maximum_residual=max(maximum_residual,abs(residual))
        foto()
        if t >= next_record-1e-7:
            records.append(record()); next_record=t+o.record_interval; registrar_series()
            punto_control()
            if progress is not None: progress(t/o.end_seconds,step)
    records.append(record())
    if fotos_t and fotos_t[-1] < t-1e-7: foto(True)
    mass_scale = max(initial_volume+runoff_volume+inflow_volume,1)
    summary = {'tiempo_final_h':t/3600,'pasos':step,'frontera':o.boundary,'backend':o.backend,
      'volumen_inicial_m3':initial_volume,'volumen_escorrentia_m3':runoff_volume,
      'volumen_entrada_m3':inflow_volume,'volumen_salida_m3':outflow_volume,
      'volumen_final_m3':float(h.sum()*area),'ajuste_redondeo_m3':correction_volume,
      'residual_final_m3':records[-1]['residual_m3'],'error_balance_max_pct':maximum_residual/mass_scale*100,
      'CFL_max':maximum_cfl,'pasos_limitados':limited_steps,'fraccion_celdas_limitadas_max':maximum_limited_fraction,
      'velocidad_max_ms':float(vmax.max()),'calado_max_m':float(hmax.max()),
      'area_m2':float(active.sum()*area),'estado':'final_completo'}
    summary['entradas'] = {e_['nombre']: {'volumen_integrado_m3': e_['volumen_m3'], 'volumen_hidrograma_m3': e_['volumen_esperado_m3'],
                           'diferencia_m3': e_['volumen_m3'] - e_['volumen_esperado_m3'], 'n_celdas': int(len(e_['celdas']))} for e_ in entradas}
    for nombre_, d_ in summary['entradas'].items():
        if abs(d_['diferencia_m3']) > 1e-6 * max(d_['volumen_hidrograma_m3'], 1.0):
            raise AssertionError(f'El volumen integrado de la entrada {nombre_} no coincide con su hidrograma.')
    if summary['error_balance_max_pct'] > 0.01:
        raise AssertionError('Error de balance >0.01% en prototipo.')
    if ckpt is not None:                                   # terminó bien: el punto de control ya no hace falta
        for f_ in [ckpt, *ckpt.parent.glob(f'{ckpt.stem}_fotos_*.npz')]:
            try: f_.unlink()
            except OSError: pass
    if resume: summary['reanudada'] = True
    return {'hmax':hmax,'vmax':vmax,'hfinal':h,'duracion_h_ge_03m':duration/3600,
            'balance':records,'resumen':summary,'fotos':{'t_s':fotos_t,'h':fotos_h},
            'entradas':{e_['nombre']:{'volumen_integrado_m3':e_['volumen_m3'],'volumen_hidrograma_m3':e_['volumen_esperado_m3'],'n_celdas':int(len(e_['celdas']))} for e_ in entradas},
            'secciones':{k:{'volumen_m3':sec_vol[k],'t_s':tr_t,'Q_m3s':sec_q[k]} for k in sections},
            'sondas':{k:{'t_s':tr_t,'h_m':probe_h[k]} for k in probes}}
