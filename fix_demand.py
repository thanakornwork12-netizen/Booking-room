import os,sys,django
sys.path.insert(0,'/Users/macthanakorn/room_booking')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','room_booking.settings')
django.setup()
import numpy as np
from booking.models import DemandForecast
vals=np.array(list(DemandForecast.objects.values_list('predicted_demand',flat=True)))
nz=vals[vals>0.5]
th=float(np.percentile(nz,80))
tm=float(np.percentile(nz,40))
print('high>=',th,'med>=',tm)
bulk=[]
for fc in DemandForecast.objects.all():
    if fc.predicted_demand>=th:fc.demand_level='high';fc.availability='likely_full'
    elif fc.predicted_demand>=tm:fc.demand_level='medium';fc.availability='likely_busy'
    else:fc.demand_level='low';fc.availability='likely_available'
    bulk.append(fc)
DemandForecast.objects.bulk_update(bulk,['demand_level','availability'])
[print(l,DemandForecast.objects.filter(demand_level=l).count()) for l in['high','medium','low']]
