"""
Scans every saved_meta_{SET}_excel_split/ folder that currently exists on
disk (regardless of when each set was trained, or whether they were trained
in separate runs on separate days) and consolidates all rooms' results into
one persistent CSV — safe to re-run any time, always reflects whatever sets
are actually saved right now. This is the source to build charts/figures
from, since train_from_excel.py's own summary CSV gets overwritten each run
and only covers that one run's sets.

Usage: python ml/saved/consolidate_results.py
"""
import os
import glob
import joblib
import pandas as pd

BASE_DIR = '/Users/macthanakorn/room_booking'
SAVED_DIR = os.path.join(BASE_DIR, 'ml', 'saved')
OUT_CSV = os.path.join(SAVED_DIR, 'metrics_plots', 'consolidated_results.csv')

ROOM_ORDER = ['2C05-06', '2C09', '2C10-11', '2C16-17', '3C05-06', '1C-MEETING', '3C16-17', '4C05']


def find_sets():
    pattern = os.path.join(SAVED_DIR, 'saved_meta_*_excel_split')
    sets = []
    for path in sorted(glob.glob(pattern)):
        name = os.path.basename(path).replace('saved_meta_', '').replace('_excel_split', '')
        sets.append(name)
    return sets


rows = []
for set_name in find_sets():
    meta_dir = os.path.join(SAVED_DIR, f'saved_meta_{set_name}_excel_split')
    for meta_path in sorted(glob.glob(os.path.join(meta_dir, '*_meta.pkl'))):
        meta = joblib.load(meta_path)
        cls = meta.get('cls_metrics', {}) or {}
        reg = meta.get('reg_metrics', {}) or {}
        w = meta.get('ensemble_weights', {}) or {}
        lstm_w = round(w.get('lstm', 0.0) * 100, 1)
        lgb_w = round(w.get('lightgbm', 0.0) * 100, 1)
        xgb_w = round(w.get('xgboost', 0.0) * 100, 1)
        winner = max(w, key=w.get) if w else None
        rows.append({
            'param_set': set_name,
            'room': meta.get('room_name'),
            'room_id': meta.get('room_id'),
            'test_accuracy': cls.get('accuracy'),
            'f1': cls.get('f1'),
            'recall': cls.get('recall'),
            'precision': cls.get('precision'),
            'r2': reg.get('r2'),
            'mae': reg.get('mae'),
            'rmse': reg.get('rmse'),
            'smape': reg.get('smape'),
            'confidence': meta.get('confidence'),
            'winner_model': winner,
            'lstm_weight_pct': lstm_w,
            'lgb_weight_pct': lgb_w,
            'xgb_weight_pct': xgb_w,
            'train_size': meta.get('train_size'),
            'test_size': meta.get('test_size'),
        })

if not rows:
    print("❌ No saved_meta_*_excel_split folders with results found — run train_from_excel.py first.")
    raise SystemExit(1)

df = pd.DataFrame(rows)
room_rank = {r: i for i, r in enumerate(ROOM_ORDER)}
df['_room_rank'] = df['room'].map(room_rank).fillna(999)
df = df.sort_values(['param_set', '_room_rank']).drop(columns='_room_rank').reset_index(drop=True)

os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
df.to_csv(OUT_CSV, index=False)

print(f"📄 Consolidated {len(df)} room results across {df['param_set'].nunique()} set(s): "
      f"{sorted(df['param_set'].unique())}")
print(f"📄 Saved: {OUT_CSV}\n")

print("=== Per-room TestAcc, by set ===")
pivot = df.pivot_table(index='room', columns='param_set', values='test_accuracy', aggfunc='first')
pivot = pivot.reindex(ROOM_ORDER)
print((pivot * 100).round(1).to_string())

print("\n=== Mean Adaptive Acc per set ===")
means = df.groupby('param_set')['test_accuracy'].mean() * 100
print(means.round(1).to_string())

print("\n=== Mean ensemble weight split per set ===")
wmeans = df.groupby('param_set')[['lstm_weight_pct', 'lgb_weight_pct', 'xgb_weight_pct']].mean()
print(wmeans.round(1).to_string())
