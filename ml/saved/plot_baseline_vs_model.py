"""Chart: test accuracy of the naive baselines vs the trained model (param set C,
the production default), per room plus the mean. Reads existing CSVs only.

Usage: python ml/saved/plot_baseline_vs_model.py [SET]   (default C)
"""
import os
import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SAVED_DIR = os.path.dirname(os.path.abspath(__file__))
MP = os.path.join(SAVED_DIR, 'metrics_plots')
SET = sys.argv[1] if len(sys.argv) > 1 else 'C'
OUT_PNG = os.path.join(MP, f'baseline_vs_model_{SET}.png')
OUT_CSV = os.path.join(MP, f'baseline_vs_model_{SET}.csv')

base = pd.read_csv(os.path.join(MP, 'baseline_results.csv'))
model = pd.read_csv(os.path.join(MP, 'test_only_results.csv'))
model = model[model.param_set == SET].set_index('room')['test_accuracy']
naive = base[base.baseline == 'naive_lag1'].set_index('room')['test_accuracy']
snaive = base[base.baseline == 'snaive_lag7'].set_index('room')['test_accuracy']

df = pd.DataFrame({'naive_lag1': naive, 'snaive_lag7': snaive, 'model': model}).dropna() * 100
df.loc['Mean'] = df.mean()
df.round(2).to_csv(OUT_CSV, index_label='room')
print(df.round(2).to_string())

series = [('naive_lag1', 'Naive (yesterday)', '#b0b0b0'),
          ('snaive_lag7', 'Seasonal naive (same weekday last week)', '#fdae6b'),
          ('model', f'Trained model (set {SET})', '#2b8cbe')]
mean = df.loc['Mean']
fig, ax = plt.subplots(figsize=(8, 6))
labels = ['Naive\n(yesterday)', 'Seasonal naive\n(same weekday last week)', f'Trained model\n(set {SET})']
vals = [mean[c] for c, _, _ in series]
bars = ax.bar(labels, vals, width=0.55, color=[c for _, _, c in series])
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 1, f'{v:.1f}%', ha='center', va='bottom',
            fontsize=15, fontweight='bold')
ax.set_ylim(0, 100)
ax.set_ylabel('Mean test accuracy (%)')
ax.set_title('Baseline vs trained model — mean test accuracy across rooms', loc='left', fontsize=13)
ax.grid(axis='y', alpha=0.25)
ax.set_axisbelow(True)
for sp in ('top', 'right'):
    ax.spines[sp].set_visible(False)
fig.tight_layout()
fig.savefig(OUT_PNG, dpi=150)
print('saved', OUT_PNG)
