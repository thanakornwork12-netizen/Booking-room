"""Chart + table: contiguous (original) vs blocked calibration, sets A-D.

Reads only saved results — no training:
  contiguous: saved_meta_{SET}_direct/          + metrics_plots/test_only_results_direct.csv
  blocked:    blocked_calib/saved_meta_{SET}_direct/ + metrics_plots/test_only_results_direct_blocked.csv
Train / calibration accuracy are read from each room's serving-engine history
at its served round (same definition as build_adaptive_vs_fixed_current.py),
averaged over rooms.

Usage: python ml/saved/plot_blocked_vs_contiguous.py
"""
import glob
import os

import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SAVED = os.path.dirname(os.path.abspath(__file__))
MP = os.path.join(SAVED, 'metrics_plots')
OUT_PNG = os.path.join(MP, 'blocked_vs_contiguous_calibration.png')
OUT_CSV = os.path.join(MP, 'blocked_vs_contiguous_calibration.csv')
SETS = ['A', 'B', 'C', 'D']
VARIANTS = {
    'Contiguous (original)': (SAVED, 'test_only_results_direct.csv'),
    'Blocked': (os.path.join(SAVED, 'blocked_calib'), 'test_only_results_direct_blocked.csv'),
}


def at_best(hist, key):
    vals, br, rounds = hist.get(key), hist.get('best_round'), hist.get('rounds')
    if not vals:
        return None
    if br and rounds and br in rounds:
        return vals[rounds.index(br)]
    return vals[-1]


def read_variant(root, test_csv):
    test = pd.read_csv(os.path.join(MP, test_csv)) if os.path.exists(os.path.join(MP, test_csv)) else None
    rows = []
    for s in SETS:
        tr, ca = [], []
        for f in glob.glob(os.path.join(root, f'saved_meta_{s}_direct', '*_meta.pkl')):
            m = joblib.load(f)
            h = m.get('lgb_history' if m.get('serving_model') == 'lightgbm' else 'xgb_history', {})
            for key, bucket in (('train_accuracy', tr), ('valid_accuracy', ca)):
                v = at_best(h, key)
                if v is not None:
                    bucket.append(v)
        if not tr:
            continue
        t = test[test.param_set == s] if test is not None else None
        rows.append(dict(set=s, rooms=len(tr), train=np.mean(tr), calib=np.mean(ca),
                         test=t.test_accuracy.mean() if t is not None and len(t) else np.nan,
                         test_balanced=t.balanced_accuracy.mean() if t is not None and len(t) else np.nan))
    return pd.DataFrame(rows)


def main():
    frames = []
    for name, (root, csv) in VARIANTS.items():
        df = read_variant(root, csv)
        df.insert(0, 'variant', name)
        frames.append(df)
    df = pd.concat(frames, ignore_index=True).round(4)
    df.to_csv(OUT_CSV, index=False)
    print(df.to_string(index=False))

    metrics = [('train', 'Train'), ('calib', 'Calibration'), ('test', 'Test')]
    colors = {'Contiguous (original)': '#b0b0b0', 'Blocked': '#2b8cbe'}
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    w = 0.38
    for ax, (col, title) in zip(axes, metrics):
        for i, name in enumerate(VARIANTS):
            d = df[df.variant == name].set_index('set').reindex(SETS)
            x = np.arange(len(SETS)) + (i - 0.5) * w
            bars = ax.bar(x, d[col], w * 0.92, color=colors[name], label=name)
            for b, v in zip(bars, d[col]):
                if np.isfinite(v):
                    ax.text(b.get_x() + b.get_width() / 2, v + 0.005, f'{v:.3f}',
                            ha='center', va='bottom', fontsize=8)
        ax.set_title(title, loc='left', fontsize=12)
        ax.set_xticks(np.arange(len(SETS)))
        ax.set_xticklabels(SETS)
        ax.set_ylim(0.5, 1.0)
        ax.grid(axis='y', alpha=0.25)
        ax.set_axisbelow(True)
        for sp in ('top', 'right'):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel('Mean accuracy over 8 rooms')
    fig.suptitle('Contiguous vs blocked calibration — same refit data, only the selection slice differs',
                 x=0.01, ha='left', fontsize=13)
    fig.legend(*axes[0].get_legend_handles_labels(), loc='lower center', ncol=2, frameon=False)
    fig.text(0.01, 0.005, 'Contiguous = one block 2025-05-24..09-09 (break -> new term). '
             'Blocked = 4 x ~12-day blocks spread over the train span, 14-day purge. '
             'Contiguous stays the primary result (pre-registered).', fontsize=8, color='#555')
    fig.tight_layout(rect=(0, 0.07, 1, 0.94))
    fig.savefig(OUT_PNG, dpi=150)
    print(f'saved {OUT_PNG}\nsaved {OUT_CSV}')


if __name__ == '__main__':
    main()
