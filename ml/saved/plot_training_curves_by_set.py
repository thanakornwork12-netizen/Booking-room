"""Training-curve chart: accuracy per boosting round, one line per param set
(A-E), averaged across all 8 rooms' winning model (LGB or XGB, whichever
each room's meta.pkl says won). Reads straight from saved_meta_*_excel_split/
— no retraining.

Usage: python ml/saved/plot_training_curves_by_set.py
"""
import os
import glob
import joblib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE_DIR = '/Users/macthanakorn/room_booking'
SAVED_DIR = os.path.join(BASE_DIR, 'ml', 'saved')
OUT_PNG = os.path.join(SAVED_DIR, 'metrics_plots', 'training_curves_by_set.png')

SETS = ['A', 'B', 'C', 'D', 'E']
SET_NAMES = {'A': 'Fast', 'B': 'Balanced', 'C': 'High Quality', 'D': 'Extra Deep', 'E': 'Max Depth'}
COLORS = {'A': '#f59e0b', 'B': '#10b981', 'C': '#3b82f6', 'D': '#8b5cf6', 'E': '#ef4444'}

curves = {}  # set -> {'train': [(round_idx, [acc per room...]), ...], 'valid': ...}
for set_name in SETS:
    d = os.path.join(SAVED_DIR, f'saved_meta_{set_name}_excel_split')
    per_room_train, per_room_valid = [], []
    for f in sorted(glob.glob(os.path.join(d, '*_meta.pkl'))):
        m = joblib.load(f)
        weights = m.get('ensemble_weights', {}) or {}
        winner = max(weights, key=weights.get) if weights else 'lightgbm'
        hist = m.get('lgb_history', {}) if winner == 'lightgbm' else m.get('xgb_history', {})
        ta = hist.get('train_accuracy')
        va = hist.get('valid_accuracy')
        if ta and va:
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
    ax.plot(range(1, len(tr) + 1), tr, color=c, marker='o', markersize=3, linewidth=2,
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
