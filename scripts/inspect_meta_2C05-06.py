import joblib,sys
from pathlib import Path
p=Path('ml/saved/saved_meta')/'2C05-06_meta.pkl'
if not p.exists():
    print('META_MISSING')
    sys.exit(0)
try:
    m=joblib.load(p)
except Exception as e:
    print('LOAD_ERR', e)
    sys.exit(0)
print('META_KEYS:', sorted(list(m.keys())))
print('reg_metrics:', m.get('reg_metrics'))
print('cls_metrics:', m.get('cls_metrics'))

lh = m.get('lstm_history') or {}
if not lh:
    print('NO_LSTM_HISTORY')
    sys.exit(0)

def show(k):
    v=lh.get(k)
    if not v:
        return
    print(f"{k} len={len(v)} last10=", [round(float(x),6) for x in v[-10:]])

for k in ['loss','val_loss','accuracy','val_accuracy','mae','val_mae']:
    show(k)

import numpy as np

def trend(k,n=5):
    v=lh.get(k)
    if not v or len(v)<n+1:
        return None
    a=np.array(v[-n-1:-1],dtype=float)
    b=np.array(v[-n:],dtype=float)
    return float((b-a).mean())

for k in ['loss','val_loss','accuracy','val_accuracy']:
    t=trend(k,5)
    print('trend',k, 'avg_diff_last5=', None if t is None else round(t,8))
