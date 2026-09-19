"""Evaluate the saved direct multi-horizon forecaster on dataset_test.xlsx.

No training happens here.  Forecast origins step 14 days at a time from the
train/test boundary and each one predicts the whole horizon ahead, which is how
the scheduled job actually runs, and matches the protocol test_from_excel.py
uses so the two numbers are directly comparable.

Usage: python ml/saved/test_direct.py
"""
import os
import sys

BASE_DIR = '/Users/macthanakorn/room_booking'
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()
from django.conf import settings
settings.DATABASES['default']['OPTIONS'] = {'sslmode': 'disable'}
from django.db import connections
connections['default'].close()

sys.path.insert(0, os.path.join(BASE_DIR, 'ml', 'saved'))

import joblib
import numpy as np
import pandas as pd

import direct_forecast as D

TRAIN_XLSX = os.path.join(BASE_DIR, 'ml/saved/data_split/dataset_train.xlsx')
TEST_XLSX = os.path.join(BASE_DIR, 'ml/saved/data_split/dataset_test.xlsx')
MODEL_PKL = os.path.join(BASE_DIR, 'ml/saved/saved_direct/model.pkl')
OUT_CSV = os.path.join(BASE_DIR, 'ml/saved/metrics_plots/direct_test_results.csv')

if not os.path.exists(MODEL_PKL):
    raise SystemExit(f'No model at {MODEL_PKL} — run python ml/saved/train_direct.py first')

bundle = joblib.load(MODEL_PKL)
models_acc = bundle['quantile_models_acc']
models_mae = bundle['quantile_models_mae']
strategy = bundle['strategy']
print(f"engine={bundle['engine']}  config={bundle['config_name']}  "
      f"(acc round chosen on calibration: {bundle['calib_scan']['best_acc_round']}, "
      f"mae round: {bundle['calib_scan']['best_mae_round']})")

data = D.Dataset(TRAIN_XLSX, TEST_XLSX)
Xte, Yte, Mte = data.matrix('test')
# Two ensembles, same features: one refit to the round-count that maximised
# calibration accuracy (serves the demand band), one to the round-count that
# minimised calibration MAE (serves the hours forecast).
Q_acc = np.column_stack([models_acc[q].predict(Xte) for q in bundle['quantiles']])
Q_mae = np.column_stack([models_mae[q].predict(Xte) for q in bundle['quantiles']])
te_codes = np.array([m[0] for m in Mte])

print(f"\n{'=' * 86}")
print(' DIRECT MULTI-HORIZON — rolling 14-day forecasts on dataset_test.xlsx')
print('=' * 86)

rows = []
for code in data.codes:
    k = te_codes == code
    if not k.any():
        continue
    r = data.rooms[code]
    sub_meta = [m for m in Mte if m[0] == code]
    cands = D.strategies(data, code, Q_acc[k], Xte[k], sub_meta)
    pick = strategy.get(code, 'argmax_class')

    # Two questions, two losses, two answers: the demand band is scored on the
    # class decision, the hours forecast on the conditional median.  Collapsing
    # them into one number makes both worse.
    band = D.apply_block_floor(cands[pick], Xte[k], sub_meta, data)
    hours = D.apply_block_floor(D.median_forecast(Q_mae[k]), Xte[k], sub_meta, data)

    y_hours = Yte[k] * r['scale']
    cls = D.F.compute_classification_metrics(
        y_hours, np.maximum(0.0, band) * r['scale'],
        r['thr_high'], r['thr_med'], r['peak'])
    p_hours = np.maximum(0.0, hours) * r['scale']
    r2 = D.F.r2_score(y_hours, p_hours)
    mae = D.F.mean_absolute_error(y_hours, p_hours)
    print(f"{code:.<16} strategy={pick:14s} Acc={cls['accuracy']:.3f}  F1={cls['f1']:.3f}  "
          f"R²={r2:6.3f}  MAE={mae:5.2f}h  (n={k.sum()})")
    rows.append({'room': code, 'strategy': pick, 'test_accuracy': cls['accuracy'],
                 'f1': cls['f1'], 'r2': r2, 'mae': mae, 'n_test': int(k.sum()),
                 'evaluation_mode': f'direct_{D.HORIZON}d_multihorizon'})

df = pd.DataFrame(rows)
print('-' * 86)
print(f"MEAN accuracy: {df.test_accuracy.mean():.4f}    MEAN F1: {df.f1.mean():.4f}")
os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
df.to_csv(OUT_CSV, index=False)
print(f'\nSaved: {OUT_CSV}')
