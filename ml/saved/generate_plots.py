"""
Utility to generate metric CSV and training-curve PNGs from saved meta files.
This script is intentionally small and independent from `forecast.py`.

Usage:
    python ml/saved/generate_plots.py
"""
import os
import sys
import csv
from pathlib import Path

import joblib
import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR.parents[1]
sys.path.append(str(BASE_DIR))

from ml.saved import plotting

META_DIR = CURRENT_DIR / "saved_meta"
METRICS_DIR = CURRENT_DIR / "metrics_plots"
METRICS_CSV = METRICS_DIR / "metrics_summary.csv"


def load_all_meta(meta_dir: str):
    p = Path(meta_dir)
    metas = []
    for f in sorted(p.glob('*_meta.pkl')):
        try:
            meta = joblib.load(f)
            room_label = None
            if isinstance(meta, dict):
                room_label = meta.get('room_name') or meta.get('Room') or meta.get('room_id')
            if room_label is None:
                room_label = f.stem.replace('_meta', '')
            metas.append((str(room_label), meta))
        except Exception:
            continue
    return metas


def write_metrics_summary_csv(metas, csv_path: Path):
    rows = []
    for room_name, meta in metas:
        if not isinstance(meta, dict):
            continue
        row = {
            'Room': room_name,
            'Status': 'OK' if meta.get('reg_metrics') and meta.get('cls_metrics') else 'NO_METRICS',
            'Accuracy': np.nan,
            'Loss': np.nan,
            'Acc_ensemble': np.nan,
            'Acc_lgb': np.nan,
            'Acc_xgb': np.nan,
            'Acc_lstm': np.nan,
            'RoomID': meta.get('room_id', ''),
        }

        mmetrics = meta.get('model_metrics') or {}
        if isinstance(mmetrics, dict):
            try:
                row['Accuracy'] = float(mmetrics.get('ensemble', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                row['Accuracy'] = np.nan
            try:
                row['Loss'] = float(mmetrics.get('ensemble', {}).get('classification', {}).get('loss', np.nan))
            except Exception:
                row['Loss'] = np.nan
            try:
                row['Acc_ensemble'] = float(mmetrics.get('ensemble', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                pass
            try:
                row['Acc_lgb'] = float(mmetrics.get('lightgbm', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                pass
            try:
                row['Acc_xgb'] = float(mmetrics.get('xgboost', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                pass
            try:
                row['Acc_lstm'] = float(mmetrics.get('lstm', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                pass
        else:
            cls = meta.get('cls_metrics') or {}
            if isinstance(cls, dict):
                row['Accuracy'] = cls.get('accuracy', np.nan)
                row['Loss'] = cls.get('loss', np.nan)

        rows.append(row)

    if not rows:
        return False

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['RoomID', 'Room', 'Status', 'Accuracy', 'Loss', 'Acc_ensemble', 'Acc_lgb', 'Acc_xgb', 'Acc_lstm']
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return True


def main():
    meta_dir = META_DIR
    metas = load_all_meta(meta_dir)
    if not metas:
        print('No meta files found in', meta_dir)
        return

    print(f'Loaded {len(metas)} meta files - generating plots in {METRICS_DIR}')

    ok = write_metrics_summary_csv(metas, METRICS_CSV)
    if ok:
        print('Created metrics summary CSV:', METRICS_CSV)
    else:
        print('Could not create metrics summary CSV from loaded meta files')

    try:
        n = plotting.generate_model_curve_plots(metas, str(METRICS_DIR))
        print('generate_model_curve_plots returned:', n)
    except Exception as e:
        print('generate_model_curve_plots failed:', e)

    # Generate overview/summary plot as the 5th image
    try:
        ok = plotting.plot_ensemble_model_comparison_from_csv(
            str(METRICS_CSV),
            os.path.join(METRICS_DIR, 'model_overview_summary.png'),
        )
        print('plot_ensemble_model_comparison_from_csv (overview) ok=', ok)
    except Exception as e:
        print('plot_ensemble_model_comparison_from_csv (overview) failed:', e)

    # Generate model configuration documentation as 6th image
    try:
        ok = plotting.plot_model_configuration(
            os.path.join(METRICS_DIR, 'model_configuration.png'),
        )
        print('plot_model_configuration ok=', ok)
    except Exception as e:
        print('plot_model_configuration failed:', e)


if __name__ == '__main__':
    main()
