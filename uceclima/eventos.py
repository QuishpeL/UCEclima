# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Contrato de evento fechado y planificación CHIRPS, independiente del solver."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math

PRODUCTOS = [('v3_daily_sat', 'UCSB-CHC/CHIRPS/V3/DAILY_SAT'),
             ('v2_daily', 'UCSB-CHG/CHIRPS/DAILY')]


@dataclass
class Evento:
    nombre: str
    inicio: str
    fin: str
    estacion: str
    fuente: str = 'pluviografo'
    zona: str = 'America/Guayaquil'

    def fechas(self):
        def parse(value):
            date = datetime.fromisoformat(value)
            return date.replace(tzinfo=ZoneInfo(self.zona)) if date.tzinfo is None else date
        start, end = parse(self.inicio), parse(self.fin)
        if end <= start:
            raise ValueError('Fin debe ser posterior al inicio.')
        if not self.nombre.strip() or not self.estacion.strip():
            raise ValueError('Identificar evento y estacion.')
        return start, end

    def plan(self):
        start, end = self.fechas()
        # CHIRPS es diario UTC: incluir todos los dias que intersectan el evento.
        utcstart, utcend = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        first = utcstart.replace(hour=0, minute=0, second=0, microsecond=0)
        last = utcend.replace(hour=0, minute=0, second=0, microsecond=0)
        if utcend != last:
            last += timedelta(days=1)
        fmt = lambda d: d.isoformat()
        windows = {'evento_dias_utc': [fmt(first), fmt(last)]}
        for days in (5,21):
            windows[f'antes_{days}d'] = [fmt(first-timedelta(days=days)),fmt(first)]
            windows[f'despues_{days}d'] = [fmt(last),fmt(last+timedelta(days=days))]
        return {'evento':self.__dict__, 'intervalos':'inicio inclusivo, fin exclusivo',
                'ventanas':windows,
                'consulta_total':[fmt(first-timedelta(days=21)),fmt(last+timedelta(days=21))],
                'productos_preferidos':PRODUCTOS,
                'advertencia':'CHIRPS diario aporta contexto; no reemplaza el pluviografo subdiario.'}


def validar_hietograma(inicios, finales, mm, evento):
    start,end = evento.fechas()
    if not (len(inicios)==len(finales)==len(mm)) or not len(mm):
        raise ValueError('Intervalos y lluvia incompatibles.')
    previous=start
    total=0.
    for a,b,rain in zip(inicios,finales,mm):
        a,b=datetime.fromisoformat(a),datetime.fromisoformat(b)
        if a.tzinfo is None or b.tzinfo is None:
            raise ValueError('Cada intervalo requiere zona/offset horario.')
        if a!=previous or b<=a:
            raise ValueError('Intervalos con huecos, solapes o duracion invalida.')
        if not math.isfinite(rain) or rain<0:
            raise ValueError('Lluvia debe ser finita y no negativa; ausencias no son cero.')
        total+=rain;previous=b
    if previous!=end:
        raise ValueError('El hietograma no cubre exactamente el evento.')
    return {'lluvia_total_mm':total,'intervalos':len(mm),'fuente':evento.fuente}


def elegir_producto(plan, disponibilidad):
    """disponibilidad: version -> fechas UTC diarias presentes. No mezcla versiones."""
    start,end=map(datetime.fromisoformat,plan['consulta_total'])
    expected=set()
    while start<end:
        expected.add(start.date().isoformat());start+=timedelta(days=1)
    diagnostic={}
    for version,collection in PRODUCTOS:
        missing=sorted(expected-set(disponibilidad.get(version,[])))
        diagnostic[version]={'dias_faltantes':missing}
        if not missing:
            return {'version':version,'coleccion':collection,'cobertura_completa':True,
                    'diagnostico':diagnostic,'fallback':version!='v3_daily_sat'}
    return {'version':None,'cobertura_completa':False,'diagnostico':diagnostic,
            'estado':'sin_producto_completo; no rellenar ni mezclar silenciosamente'}
