"""One-off chart: TrainAcc vs TestAcc per param set (A-E), showing the
overfitting gap. Reads the numbers straight from saved_meta_*_excel_split/
and metrics_plots/test_only_results.csv — no retraining.

Usage: python ml/saved/plot_train_vs_test_gap.py
"""
import os
import sys
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

# --direct reads the direct-model sets (saved_meta_{SET}_direct, written by
# train_direct_sets.py) instead of the recursive pipeline's, and writes a
# separate file so neither run overwrites the other's figure.
DIRECT = '--direct' in sys.argv or '--blocked' in sys.argv
META_SUFFIX = '_direct' if DIRECT else '_excel_split'
if DIRECT:
    OUT_PNG = OUT_PNG.replace('.png', '_direct.png')
    TEST_CSV = TEST_CSV.replace('.csv', '_direct.csv')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocked_variant  # noqa: E402
blocked_variant.apply(globals())
SET_LABELS = (['Fast', 'Balanced', 'Wide', 'Overfit probe'] if DIRECT else
              ['Fast', 'Balanced', 'High Quality', 'Extra Deep', 'Max Depth'])


def _train_acc_at_best(hist):
    """Train accuracy of the model actually served.

    Both pipelines train past the optimum and serve the calibration-best
    round (_predict_booster / the direct refit), so the last history value
    describes trees that are never used. Direct histories store a point
    every 10 rounds with the round numbers in 'rounds'.
    """
    ta = hist.get('train_accuracy')
    if not ta:
        return None
    br, rounds = hist.get('best_round'), hist.get('rounds')
    if br and rounds and br in rounds:
        return ta[rounds.index(br)]
    if br and not rounds and 1 <= br <= len(ta):
        return ta[br - 1]
    return ta[-1]

# Only A/B/C are trained now: those three vary the training schedule
# (300/800/1500 trees at lr .05/.03/.01) with capacity held fixed. D/E belong
# to an older experiment and have no current metas, so leaving them in this
# list drew empty series.
# D is a direct-pipeline set only. saved_meta_D_excel_split exists but holds
# metas from a run that predates the daily-occupancy fix, so pulling it into the
# recursive figures would put two different datasets in one chart.
SETS = ['A', 'B', 'C', 'D'] if DIRECT else ['A', 'B', 'C']

# TrainAcc: mean train_accuracy of the winning model at its served round, per set
train_rows = []
for set_name in SETS:
    d = os.path.join(SAVED_DIR, f'saved_meta_{set_name}{META_SUFFIX}')
    for f in sorted(glob.glob(os.path.join(d, '*_meta.pkl'))):
        m = joblib.load(f)
        weights = m.get('ensemble_weights', {}) or {}
        winner = max(weights, key=weights.get) if weights else 'lightgbm'
        hist = m.get('lgb_history', {}) if winner == 'lightgbm' else m.get('xgb_history', {})
        acc = _train_acc_at_best(hist)
        if acc is not None:
            train_rows.append({'set': set_name, 'train_acc': acc})

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
    SETS, SET_LABELS)])
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
