# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Evaluación del modelo: contabilidad numérica separada de capacidad hidráulica."""
import math


def evaluar(resumen, balance, volumen_referencia_m3=None):
    s = resumen
    initial = float(s['volumen_inicial_m3'])
    incoming = float(s['volumen_escorrentia_m3']) + float(s['volumen_entrada_m3'])
    outgoing = float(s['volumen_salida_m3'])
    final = float(s['volumen_final_m3'])
    correction = float(s.get('ajuste_redondeo_m3', 0))
    values = [initial, incoming, outgoing, final, correction]
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Volúmenes no finitos.')
    physical = final + outgoing - initial - incoming
    residual = physical - correction
    scale = initial + incoming
    relative = lambda value: value / scale * 100 if scale > 0 else None
    result = {
        'tipo': 'evaluacion_numerica_del_modelo_no_validacion_fisica',
        'volumen_disponible_m3': scale,
        'diferencia_balance_fisico_m3': physical,
        'diferencia_balance_fisico_pct': relative(physical),
        'ajuste_numerico_m3': correction,
        'residual_tras_ajuste_m3': residual,
        'residual_tras_ajuste_pct': relative(residual),
        'residual_max_registros_m3': max((abs(float(r['residual_m3'])) for r in balance), default=None),
        'error_balance_max_todos_pasos_pct': s.get('error_balance_max_pct'),
        'porcentaje_volumen_almacenado': relative(final),
        'Courant_max': s.get('CFL_max'),
        'Courant_objetivo': s.get('cfl_objetivo'),
        'definicion_Courant': 'criterio de celeridad del solver de inercia local; no CFL advectivo completo',
        'pasos_calculo': s.get('pasos'),
        'pasos_con_limitador': s.get('pasos_limitados'),
        'porcentaje_pasos_con_limitador': (100*s.get('pasos_limitados', 0)/s['pasos'] if s.get('pasos', 0)>0 else None),
        'fraccion_celdas_limitadas_max': s.get('fraccion_celdas_limitadas_max'),
        'iteraciones_no_lineales_por_paso': None,
        'motivo_iteraciones': 'solver explícito; no confundir pasos, iteraciones y activaciones del limitador',
        'perdidas_carga_estructuras_m': None,
        'capacidad_canales': {'estado': 'no_evaluada',
            'requisitos': ['secciones y cotas de fondo/margenes verificadas',
                          'caudales por canal y ubicacion de entradas',
                          'condiciones aguas abajo y estructuras',
                          'niveles, caudal transportado y sobrevertido por tramo'],
            'advertencia': 'Acumulacion pluvial y balance global no demuestran capacidad de canales.'},
    }
    if volumen_referencia_m3 is not None:
        ref = float(volumen_referencia_m3)
        if not math.isfinite(ref) or ref < 0:
            raise ValueError('Volumen de referencia inválido.')
        result['comparacion_referencia'] = {
            'variable': 'volumen_final_m3', 'referencia_m3': ref,
            'diferencia_m3': final-ref,
            'diferencia_pct': 100*(final-ref)/ref if ref>0 else None,
            'condicion': 'solo interpretable para igual dominio, evento e instante; no es error de balance'}
    return result
