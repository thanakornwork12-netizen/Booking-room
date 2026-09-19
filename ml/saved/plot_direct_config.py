"""Hyperparameter table for the DIRECT forecaster — the model whose numbers
the A/B/C results actually come from.

metrics_plots/model_configuration.png is built from param_sets.py, which
belongs to the older recursive per-room pipeline (saved_meta_*_excel_split).
Nothing in the direct pipeline reads param_sets.py: train_direct_sets.py maps
each set to a key in train_direct.LGB_GRID / XGB_GRID instead. Putting that
table next to direct results therefore describes a different model.

Everything here is read out of saved_direct_sets/{SET}/model.pkl — the served
bundle itself — so the table cannot drift from what was actually trained.

Usage: python3 ml/saved/plot_direct_config.py
"""
import os
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_ROOT = os.path.join(CURRENT_DIR, 'saved_direct_sets')
OUT_PNG = os.path.join(CURRENT_DIR, 'metrics_plots', 'model_configuration_direct.png')
import sys  # noqa: E402
sys.path.insert(0, CURRENT_DIR)
import blocked_variant  # noqa: E402
blocked_variant.apply(globals())
SETS = ['A', 'B', 'C', 'D']

# Only the hyperparameters that actually distinguish the sets. subsample and
# colsample_bytree move only between 0.75-0.85 across all four sets and were
# never the variable under test (capacity and regularisation strength were),
# so they are left out of the table to keep it to what a reader needs to see
# the story: budget/rate form the geometric ladder, leaves/min_child/reg_*
# show A-D moving from small+tight to (D) wide+loose, and rounds served is
# the direct evidence for where each set actually stopped.
LGB_KEYS = ['num_leaves', 'min_child_samples', 'reg_alpha', 'reg_lambda']
XGB_KEYS = ['max_depth', 'min_child_weight', 'reg_alpha', 'reg_lambda']
TINTS = {'A': '#f0f0f0', 'B': '#fff3e3', 'C': '#e7f4ff', 'D': '#f2e9f7'}


def _label(key):
    return key.replace('_', ' ').title().replace('Lr', 'LR')


def load_bundles():
    out = {}
    for s in SETS:
        p = os.path.join(MODEL_ROOT, s, 'model.pkl')
        if os.path.exists(p):
            out[s] = joblib.load(p)
    return out


def build_rows(bundles):
    rows = [
        ('Rounds budget', lambda b: b.get('rounds_budget', '—')),
        ('Learning rate', lambda b: b.get('learning_rate', '—')),
    ]
    for eng, keys, tag in (('lightgbm', LGB_KEYS, 'LGB'), ('xgboost', XGB_KEYS, 'XGB')):
        for k in keys:
            rows.append((f'{tag} {_label(k)}',
                         lambda b, e=eng, k=k: b['engines'].get(e, {}).get('params', {}).get(k, '—')))
        rows.append((f'{tag} rounds served',
                     lambda b, e=eng: b['engines'].get(e, {}).get('n_acc', '—')))
        rows.append((f'{tag} rooms served',
                     lambda b, e=eng: sum(1 for v in (b.get('room_engine') or {}).values() if v == e)))
    return rows


def main():
    bundles = load_bundles()
    if not bundles:
        print(f'No bundles under {MODEL_ROOT} — run train_direct_sets.py first.')
        return
    sets = [s for s in SETS if s in bundles]
    rows = build_rows(bundles)

    header = ['Parameter'] + [f"{s}\n{bundles[s].get('param_set_name', s).split(' - ')[-1]}"
                              for s in sets]
    table_data = [header] + [[label] + [str(fn(bundles[s])) for s in sets] for label, fn in rows]

    with plt.rc_context({'figure.facecolor': 'white', 'font.size': 10}):
        fig = plt.figure(figsize=(3.4 + 2.2 * len(sets), 1.6 + 0.42 * len(rows)), dpi=300)
        ax = fig.add_subplot(111)
        ax.axis('off')
        w = (1.0 - 0.30) / max(len(sets), 1)
        table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                         colWidths=[0.30] + [w] * len(sets))
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2.2)

        for j in range(len(header)):
            c = table[(0, j)]
            c.set_facecolor('#2b8cbe')
            c.set_text_props(weight='bold', color='white', fontsize=10.5)
            c.set_edgecolor('#1f4e79')
            c.set_linewidth(2)
        for i in range(1, len(table_data)):
            table[(i, 0)].set_facecolor('#f7f7f7')
            table[(i, 0)].set_text_props(weight='bold', fontsize=9.5)
            for j, s in enumerate(sets, start=1):
                table[(i, j)].set_facecolor(TINTS.get(s, '#ffffff'))
            for j in range(len(header)):
                table[(i, j)].set_edgecolor('#cccccc')
                table[(i, j)].set_linewidth(1)

        fig.text(0.5, 0.95, 'Direct Forecaster — Hyperparameter Configuration, Sets A / B / C / D',
                 ha='center', fontsize=14, fontweight='bold', color='white',
                 bbox=dict(boxstyle='round,pad=0.8', facecolor='#2b8cbe',
                           edgecolor='#1f4e79', linewidth=2, alpha=0.9))
        fig.text(0.5, 0.03,
                 'Read from saved_direct_sets/{SET}/model.pkl — the served bundle. One model is pooled over all '
                 'rooms and both engines are trained for every set; each room is then served by whichever engine '
                 'won on its calibration window, so "rooms served" is a real count. Each set trains its full Rounds '
                 'budget with no early stopping (rounds x rate = 24 for every set); "rounds served" is the round '
                 'chosen afterward from that finished run\'s calibration curve. '
                 'This is NOT param_sets.py — that file belongs to the older recursive pipeline.',
                 ha='center', fontsize=8, style='italic',
                 bbox=dict(boxstyle='round,pad=0.5', facecolor='#f5f5f5',
                           edgecolor='#cccccc', linewidth=1))
        plt.tight_layout(rect=[0, 0.07, 1, 0.91])
        os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
        plt.savefig(OUT_PNG, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
    print(f'Saved: {OUT_PNG}')


if __name__ == '__main__':
    main()
