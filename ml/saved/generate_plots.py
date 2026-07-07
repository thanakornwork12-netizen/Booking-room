"""
Utility to generate metric CSV and training-curve PNGs from saved meta files.
This script is intentionally small and independent from `forecast.py`.

Usage:
    python ml/saved/generate_plots.py
"""
import os
import sys
from pathlib import Path

import joblib

CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR.parents[1]
sys.path.append(str(BASE_DIR))

from ml.saved import plotting

META_DIR = CURRENT_DIR / "saved_meta"
METRICS_DIR = CURRENT_DIR / "metrics_plots"


def load_all_meta(meta_dir: str):
    p = Path(meta_dir)
    metas = []
    for f in sorted(p.glob('*_meta.pkl')):
        try:
            meta = joblib.load(f)
            metas.append((f.stem.replace('_meta', ''), meta))
        except Exception:
            continue
    return metas


def main():
    meta_dir = META_DIR
    metas = load_all_meta(meta_dir)
    if not metas:
        print('No meta files found in', meta_dir)
        return

    print(f'Loaded {len(metas)} meta files - generating plots in {METRICS_DIR}')

    try:
        n = plotting.generate_model_curve_plots(metas, str(METRICS_DIR))
        print('generate_model_curve_plots returned:', n)
    except Exception as e:
        print('generate_model_curve_plots failed:', e)

    try:
        summary = plotting.aggregate_model_metrics(metas)
        ok = plotting.plot_model_summary(summary, os.path.join(METRICS_DIR, 'model_summary_metrics.png'))
        print('plot_model_summary ok=', ok)
    except Exception as e:
        print('plot_model_summary failed:', e)


if __name__ == '__main__':
    main()
