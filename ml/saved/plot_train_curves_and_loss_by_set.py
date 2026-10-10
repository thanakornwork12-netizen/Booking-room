"""Train accuracy and train loss per boosting round side by side, one line per
param set, averaged across all 8 rooms' winning model. Same layout as
test_curves_and_loss_by_set_direct.png (accuracy left, loss right) — the train
counterpart of that figure.

Reads straight from saved_meta_{SET}{suffix} (lgb_history/xgb_history of the
winning model) — no retraining.

Output: metrics_plots/train_curves_and_loss_by_set[_direct].png

Usage: python ml/saved/plot_train_curves_and_loss_by_set.py [--direct]
"""
import os
import sys
import glob
import joblib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# รากโปรเจกต์ (ml/saved/ อยู่ลึกลงไปสองชั้น) — เดิม hardcode path ของเครื่องเดียว
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SAVED_DIR = os.path.join(BASE_DIR, 'ml', 'saved')
OUT_PNG = os.path.join(SAVED_DIR, 'metrics_plots', 'train_curves_and_loss_by_set.png')

DIRECT = '--direct' in sys.argv or '--blocked' in sys.argv
META_SUFFIX = '_direct' if DIRECT else '_excel_split'
if DIRECT:
    OUT_PNG = OUT_PNG.replace('.png', '_direct.png')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocked_variant  # noqa: E402
blocked_variant.apply(globals())

SETS = ['A', 'B', 'C', 'D'] if DIRECT else ['A', 'B', 'C']
SET_NAMES = ({'A': 'Fast', 'B': 'Balanced', 'C': 'Wide', 'D': 'Overfit probe'} if DIRECT else
             {'A': 'Fast', 'B': 'Balanced', 'C': 'High Quality', 'D': 'Extra Deep', 'E': 'Max Depth'})
COLORS = {'A': '#f59e0b', 'B': '#10b981', 'C': '#3b82f6', 'D': '#8b5cf6', 'E': '#ef4444'}


def _mean_curve(per_room, per_room_rounds):
    """Average rooms point by point, padding shorter rooms with their own last
    value. Keeps the longest room's rounds so the x-axis matches the curve."""
    max_len = max(len(a) for a in per_room)
    padded = np.array([list(a) + [a[-1]] * (max_len - len(a)) for a in per_room], dtype=float)
    rounds = max(per_room_rounds, key=lambda r: len(r) if r else 0)
    if not rounds or len(rounds) != max_len:
        rounds = list(range(1, max_len + 1))
    return list(rounds), padded.mean(axis=0)


def collect_set(set_name):
    d = os.path.join(SAVED_DIR, f'saved_meta_{set_name}{META_SUFFIX}')
    accs, losses, rounds = [], [], []
    for f in sorted(glob.glob(os.path.join(d, '*_meta.pkl'))):
        m = joblib.load(f)
        weights = m.get('ensemble_weights', {}) or {}
        winner = max(weights, key=weights.get) if weights else 'lightgbm'
        hist = m.get('lgb_history', {}) if winner == 'lightgbm' else m.get('xgb_history', {})
        ta, tl = hist.get('train_accuracy'), hist.get('train_loss')
        if ta and tl:
            accs.append(list(ta))
            losses.append(list(tl))
            rounds.append(list(hist['rounds']) if hist.get('rounds') else None)
    if not accs:
        return None
    xs, acc = _mean_curve(accs, rounds)
    xs_loss, loss = _mean_curve(losses, rounds)
    return (xs, acc * 100), (xs_loss, loss)


def _draw(ax, curves, ylabel, title, legend_loc):
    for set_name in SETS:
        if set_name not in curves:
            continue
        xs, ys = curves[set_name]
        ax.plot(xs, ys, color=COLORS[set_name], marker='o', markersize=3, linewidth=2,
                label=f'{set_name} ({SET_NAMES[set_name]})')
    ax.set_title(title, fontweight='bold')
    ax.set_xlabel('Boosting Round')
    ax.set_ylabel(ylabel)
    ax.legend(loc=legend_loc)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(alpha=0.25)


def main():
    acc_curves, loss_curves = {}, {}
    for set_name in SETS:
        print(f'Processing Set {set_name}...')
        result = collect_set(set_name)
        if result is None:
            print(f'   ! Set {set_name}: no train_accuracy/train_loss in meta')
            continue
        acc_curves[set_name], loss_curves[set_name] = result

    plt.rcParams.update({
        'savefig.facecolor': 'white', 'font.family': 'DejaVu Sans',
        'font.size': 11, 'axes.titlesize': 13, 'legend.fontsize': 9.5,
    })
    fig, (ax_acc, ax_loss) = plt.subplots(1, 2, figsize=(17, 6), dpi=300)
    _draw(ax_acc, acc_curves, 'Accuracy (%)', 'TrainAcc per Round (avg. across 8 rooms)', 'lower right')
    _draw(ax_loss, loss_curves, 'Loss (MAE, hours)', 'Train Loss per Round (avg. across 8 rooms)', 'upper right')
    fig.suptitle('Training Curves by Param Set — Winning Model per Room', fontweight='bold', fontsize=14)
    fig.tight_layout()
    plt.savefig(OUT_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f'Saved: {OUT_PNG}')


if __name__ == '__main__':
    main()
