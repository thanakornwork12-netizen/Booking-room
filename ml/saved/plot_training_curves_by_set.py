"""Training-curve chart: accuracy per boosting round, one line per param set
(A-E), averaged across all 8 rooms' winning model (LGB or XGB, whichever
each room's meta.pkl says won). Reads straight from saved_meta_*_excel_split/
— no retraining.

Usage: python ml/saved/plot_training_curves_by_set.py
"""
import os
import sys
import glob
import joblib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE_DIR = '/Users/macthanakorn/room_booking'
SAVED_DIR = os.path.join(BASE_DIR, 'ml', 'saved')
OUT_PNG = os.path.join(SAVED_DIR, 'metrics_plots', 'training_curves_by_set.png')

# --direct reads the direct-model sets (saved_meta_{SET}_direct, written by
# train_direct_sets.py) instead of the recursive pipeline's, and writes a
# separate file so neither run overwrites the other's figure.
DIRECT = '--direct' in sys.argv or '--blocked' in sys.argv
META_SUFFIX = '_direct' if DIRECT else '_excel_split'
if DIRECT:
    OUT_PNG = OUT_PNG.replace('.png', '_direct.png')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocked_variant  # noqa: E402
blocked_variant.apply(globals())

# Only A/B/C are trained now: those three vary the training schedule
# (300/800/1500 trees at lr .05/.03/.01) with capacity held fixed. D/E belong
# to an older experiment and have no current metas, so leaving them in this
# list drew empty series.
# D is a direct-pipeline set only. saved_meta_D_excel_split exists but holds
# metas from a run that predates the daily-occupancy fix, so pulling it into the
# recursive figures would put two different datasets in one chart.
SETS = ['A', 'B', 'C', 'D'] if DIRECT else ['A', 'B', 'C']
SET_NAMES = ({'A': 'Fast', 'B': 'Balanced', 'C': 'Wide', 'D': 'Overfit probe'} if DIRECT else
             {'A': 'Fast', 'B': 'Balanced', 'C': 'High Quality', 'D': 'Extra Deep', 'E': 'Max Depth'})

def _x_axis(rounds, values):
    """Boosting round for each point. Direct-model histories store one point
    every 10 rounds in 'rounds'; pipeline histories have one per round."""
    if rounds and len(rounds) == len(values):
        return rounds
    return range(1, len(values) + 1)

COLORS = {'A': '#f59e0b', 'B': '#10b981', 'C': '#3b82f6', 'D': '#8b5cf6', 'E': '#ef4444'}

curves = {}  # set -> {'train': [(round_idx, [acc per room...]), ...], 'valid': ...}
for set_name in SETS:
    d = os.path.join(SAVED_DIR, f'saved_meta_{set_name}{META_SUFFIX}')
    per_room_train, per_room_valid = [], []
    set_rounds = None
    for f in sorted(glob.glob(os.path.join(d, '*_meta.pkl'))):
        m = joblib.load(f)
        weights = m.get('ensemble_weights', {}) or {}
        winner = max(weights, key=weights.get) if weights else 'lightgbm'
        hist = m.get('lgb_history', {}) if winner == 'lightgbm' else m.get('xgb_history', {})
        ta = hist.get('train_accuracy')
        va = hist.get('valid_accuracy')
        if ta and va:
            set_rounds = set_rounds or hist.get('rounds')
            per_room_train.append(ta)
            per_room_valid.append(va)
    if per_room_train:
        max_len = max(len(a) for a in per_room_train)
        # pad shorter per-room histories with their own last value so the
        # mean stays defined out to the longest room's round count
        padded_train = np.array([a + [a[-1]] * (max_len - len(a)) for a in per_room_train])
        padded_valid = np.array([a + [a[-1]] * (max_len - len(a)) for a in per_room_valid])
        curves[set_name] = {
            'train_mean': padded_train.mean(axis=0) * 100,
            'rounds': set_rounds,
            'valid_mean': padded_valid.mean(axis=0) * 100,
        }

plt.rcParams.update({
    'savefig.facecolor': 'white',
    'font.family': 'DejaVu Sans',
    'font.size': 11,
    'axes.titlesize': 13,
    'legend.fontsize': 9.5,
})

fig, ax = plt.subplots(figsize=(9, 6), dpi=300)

for set_name in SETS:
    if set_name not in curves:
        continue
    c = COLORS[set_name]
    tr = curves[set_name]['train_mean']
    ax.plot(_x_axis(curves[set_name]['rounds'], tr), tr, color=c, marker='o', markersize=3, linewidth=2,
             label=f'{set_name} ({SET_NAMES[set_name]})')

ax.set_title('TrainAcc per Round (avg. across 8 rooms)', fontweight='bold')
ax.set_xlabel('Boosting Round')
ax.set_ylabel('Accuracy (%)')
ax.legend(loc='lower right')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(alpha=0.25)

fig.suptitle('Training Curves by Param Set — Winning Model per Room', fontweight='bold', fontsize=14)
fig.tight_layout()
plt.savefig(OUT_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
print(f'Saved: {OUT_PNG}')
