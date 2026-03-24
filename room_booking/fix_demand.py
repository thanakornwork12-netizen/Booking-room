import os, sys, django

sys.path.insert(0, '/Users/macthanakorn/room_booking')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')
django.setup()

import numpy as np
from booking.models import DemandForecast

vals    = np.array(list(DemandForecast.objects.values_list('predicted_demand', flat=True)))
nonzero = vals[vals > 0.5]

print(f'Non-zero: {len(nonzero)} / {len(vals)}')
print(f'Max: {nonzero.max():.2f}')

thr_high = float(np.percentile(nonzero, 80))
thr_med  = float(np.percentile(nonzero, 40))

print(f'High threshold: {thr_high:.2f}')
print(f'Med  threshold: {thr_med:.2f}')

bulk = []
for fc in DemandForecast.objects.all():
    if fc.predicted_demand >= thr_high:
        fc.demand_level = 'high'
        fc.availability = 'likely_full'
    elif fc.predicted_demand >= thr_med:
        fc.demand_level = 'medium'
        fc.availability = 'likely_busy'
    else:
        fc.demand_level = 'low'
        fc.availability = 'likely_available'
    bulk.append(fc)

DemandForecast.objects.bulk_update(bulk, ['demand_level', 'availability'])

for lvl in ['high', 'medium', 'low']:
    c = DemandForecast.objects.filter(demand_level=lvl).count()
    print(f'{lvl}: {c}')
