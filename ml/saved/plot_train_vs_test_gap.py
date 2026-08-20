"""One-off chart: TrainAcc vs TestAcc per param set (A-E), showing the
overfitting gap. Reads the numbers straight from saved_meta_*_excel_split/
and metrics_plots/test_only_results.csv — no retraining.

Usage: python ml/saved/plot_train_vs_test_gap.py
"""
import os
import glob
import joblib
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE_DIR = '/Users/macthanakorn/room_booking'
SAVED_DIR = os.path.join(BASE_DIR, 'ml', 'saved')
OUT_PNG = os.path.join(SAVED_DIR, 'metrics_plots', 'train_vs_test_acc_by_set.png')
TEST_CSV = os.path.join(SAVED_DIR, 'metrics_plots', 'test_only_results.csv')

SETS = ['A', 'B', 'C', 'D', 'E']

# TrainAcc: mean final train_accuracy of the winning model, per set
train_rows = []
for set_name in SETS:
    d = os.path.join(SAVED_DIR, f'saved_meta_{set_name}_excel_split')
    for f in sorted(glob.glob(os.path.join(d, '*_meta.pkl'))):
        m = joblib.load(f)
        weights = m.get('ensemble_weights', {}) or {}
        winner = max(weights, key=weights.get) if weights else 'lightgbm'
        hist = m.get('lgb_history', {}) if winner == 'lightgbm' else m.get('xgb_history', {})
        ta = hist.get('train_accuracy')
        if ta:
            train_rows.append({'set': set_name, 'train_acc': ta[-1]})

train_df = pd.DataFrame(train_rows)
train_mean = train_df.groupby('set')['train_acc'].mean().reindex(SETS) * 100

# TestAcc: from the dedicated test-only script's saved results
test_df = pd.read_csv(TEST_CSV)
test_mean = test_df.groupby('param_set')['test_accuracy'].mean().reindex(SETS) * 100

gap = train_mean - test_mean

plt.rcParams.update({
    'savefig.facecolor': 'white',
    'font.family': 'DejaVu Sans',
    'font.size': 11,
    'axes.titlesize': 13,
    'legend.fontsize': 10,
})

fig, ax = plt.subplots(figsize=(9, 5.5), dpi=300)

x = range(len(SETS))
width = 0.35
bars_train = ax.bar([i - width / 2 for i in x], train_mean.values, width,
                     label='TrainAcc', color='#60a5fa', edgecolor='#1e3a8a')
bars_test = ax.bar([i + width / 2 for i in x], test_mean.values, width,
                    label='TestAcc', color='#34d399', edgecolor='#065f46')

for i, (tr, te, g) in enumerate(zip(train_mean.values, test_mean.values, gap.values)):
    ax.text(i - width / 2, tr + 0.4, f'{tr:.1f}%', ha='center', fontsize=9, color='#1e3a8a')
    ax.text(i + width / 2, te + 0.4, f'{te:.1f}%', ha='center', fontsize=9, color='#065f46')
    ax.text(i, min(tr, te) - 3.5, f'gap {g:.1f}pp', ha='center', fontsize=8.5,
            color='#b91c1c' if g == gap.max() else '#6b7280', fontweight='bold' if g == gap.max() else 'normal')

ax.set_xticks(list(x))
ax.set_xticklabels([f'{s}\n({name})' for s, name in zip(
    SETS, ['Fast', 'Balanced', 'High Quality', 'Extra Deep', 'Max Depth'])])
ax.set_ylabel('Accuracy (%)')
ax.set_ylim(60, 105)
ax.set_title('TrainAcc vs TestAcc by Param Set — Overfitting Gap', fontweight='bold')
ax.legend(loc='lower right')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(axis='y', alpha=0.25)

fig.tight_layout()
plt.savefig(OUT_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
print(f'Saved: {OUT_PNG}')
