import joblib
from pathlib import Path
import numpy as np
ROOT = Path('/Users/macthanakorn/room_booking').resolve()
base = ROOT / 'ml' / 'saved'
archive_dirs = [base/'saved_meta', base/'saved_meta_A', base/'saved_meta_B', base/'saved_meta_C']
has_lstm = 0
stats = {'loss': [], 'val_loss': [], 'accuracy': [], 'val_accuracy': [], 'acc': [], 'val_acc': []}
for d in archive_dirs:
    if not d.exists():
        continue
    for f in sorted(d.glob('*_meta.pkl')):
        try:
            meta = joblib.load(f)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        hist = meta.get('lstm_history')
        if isinstance(hist, dict):
            has_lstm += 1
            for k in ['loss', 'val_loss', 'accuracy', 'val_accuracy', 'acc', 'val_acc']:
                v = hist.get(k)
                if isinstance(v, (list, tuple, np.ndarray)):
                    stats[k].append(len(v))
print('total lstm histories', has_lstm)
for k, v in stats.items():
    print(k, len(v), 'min', min(v) if v else None, 'max', max(v) if v else None, 'mean', sum(v)/len(v) if v else None)
