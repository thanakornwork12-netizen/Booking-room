import pathlib
import joblib
from ml.saved import plotting

base = pathlib.Path('ml/saved')
archive_dirs = [
    base / 'saved_meta',
    base / 'saved_meta_A',
    base / 'saved_meta_B',
    base / 'saved_meta_C',
]
metas = []
seen = set()
for d in archive_dirs:
    if not d.exists():
        continue
    for f in sorted(d.glob('*_meta.pkl')):
        if str(f) in seen:
            continue
        seen.add(str(f))
        try:
            meta = joblib.load(f)
        except Exception:
            continue
        metas.append((str(meta.get('room_name') or meta.get('room_id') or f.stem), meta))
print('loaded', len(metas), 'metas')
for model, cfg in [('lstm', ['accuracy', 'acc']), ('lightgbm', ['train_accuracy', 'accuracy', 'acc']), ('xgboost', ['train_accuracy', 'accuracy', 'acc'])]:
    histories = plotting._collect_training_history(metas, model)
    print(model, 'histories', len(histories))
    for series_name, keys in [('train_acc', cfg), ('val_acc', ['valid_accuracy', 'val_accuracy', 'val_acc']), ('train_loss', ['train_loss', 'loss']), ('val_loss', ['valid_loss', 'val_loss'])]:
        series = plotting._mean_history_series(histories, keys)
        print(' ', series_name, 'len', None if series is None else len(series), 'first', None if series is None else list(series[:5]), 'last', None if series is None else list(series[-5:]))
