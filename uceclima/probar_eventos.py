# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
from eventos import Evento,validar_hietograma,elegir_producto
from datetime import datetime,timedelta
e=Evento('prueba','2011-02-02T00:00:00-05:00','2011-02-02T04:00:00-05:00','M0037')
assert validar_hietograma(['2011-02-02T00:00:00-05:00'],['2011-02-02T04:00:00-05:00'],[40.],e)['lluvia_total_mm']==40
p=e.plan();a,b=map(datetime.fromisoformat,p['consulta_total']);days=[]
while a<b:days.append(a.date().isoformat());a+=timedelta(days=1)
assert elegir_producto(p,{'v2_daily':days})['fallback']
assert elegir_producto(p,{'v3_daily_sat':days,'v2_daily':days})['version']=='v3_daily_sat'
assert elegir_producto(p,{})['version'] is None
try:validar_hietograma(['2011-02-02T01:00:00-05:00'],['2011-02-02T04:00:00-05:00'],[40.],e)
except ValueError:pass
else:raise AssertionError('Hueco no detectado')
print('OK: ventanas, hietograma, preferencia v3, fallback v2 y faltantes')
