"""Train vs Test accuracy comparison, using TODAY's excel-split models
(saved_meta_{SET}_excel_split) — NOT the old saved_meta_*_new archive that
analyze_adaptive_weights_all_sets.py reads (that one is frozen/protected
and predates today's fixes).

Reads straight from data that's already on disk — no retraining, no
re-predicting, no model loading:
  - "Train Accuracy" = the winning model's own final train_accuracy from
    its training history in meta.pkl (lgb_history/xgb_history).
  - "Test Accuracy (Adaptive)" = per-room test_accuracy already computed by
    test_from_excel.py and cached in metrics_plots/test_only_results.csv,
    averaged per set (this is the same winner-take-all model the system
    actually serves — ensemble_weights in meta.pkl records the winner).

Usage: python ml/saved/build_adaptive_vs_fixed_current.py
"""
import os
import glob
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE_DIR = '/Users/macthanakorn/room_booking'
SAVED_DIR = os.path.join(BASE_DIR, 'ml', 'saved')
METRICS_DIR = os.path.join(SAVED_DIR, 'metrics_plots')
TEST_CSV = os.path.join(METRICS_DIR, 'test_only_results.csv')
OUT_PNG = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_by_set copy.png')
OUT_CSV = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_by_set_current.csv')

SETS = ['A', 'B', 'C', 'D', 'E']


def process_set(set_name, test_df):
    META_DIR = os.path.join(SAVED_DIR, f'saved_meta_{set_name}_excel_split')
    if not os.path.isdir(META_DIR):
        print(f"skip {set_name}: no {META_DIR}")
        return None

    train_acc_list = []
    weight_sum = {'lstm': 0.0, 'lightgbm': 0.0, 'xgboost': 0.0}
    n_rooms = 0

    for f in sorted(glob.glob(os.path.join(META_DIR, '*_meta.pkl'))):
        meta = joblib.load(f)
        weights = meta.get('ensemble_weights', {}) or {}
        winner = max(weights, key=weights.get) if weights else 'lightgbm'

        hist = meta.get('lgb_history', {}) if winner == 'lightgbm' else meta.get('xgb_history', {})
        ta = hist.get('train_accuracy')
        if ta:
            train_acc_list.append(ta[-1])

        for k in weight_sum:
            weight_sum[k] += weights.get(k, 0.0)
        n_rooms += 1

    if n_rooms == 0:
        return None

    set_test = test_df[test_df['param_set'] == set_name]
    weight_pcts = {k: weight_sum[k] / n_rooms * 100 for k in weight_sum}

    return {
        'Set': set_name,
        'Rooms': n_rooms,
        'Train Accuracy': round(float(np.mean(train_acc_list)), 4) if train_acc_list else 0.0,
        'Test Accuracy (Adaptive)': round(float(set_test['test_accuracy'].mean()), 4) if len(set_test) else 0.0,
        'Mean Adaptive Weight LSTM %': round(weight_pcts['lstm'], 1),
        'Mean Adaptive Weight LGB %': round(weight_pcts['lightgbm'], 1),
        'Mean Adaptive Weight XGB %': round(weight_pcts['xgboost'], 1),
    }


def plot_table(df: pd.DataFrame, png_path: str):
    headers = [
        'Set', 'Rooms', 'Train Acc\n(winner model)', 'Test Acc\n(Adaptive)',
        'Gap\n(pp)', 'Weight Split Found by System\n(LSTM / LGB / XGB)',
    ]
    table_data = [headers]
    for _, row in df.iterrows():
        found_split = (
            f"{row['Mean Adaptive Weight LSTM %']:.0f}% / "
            f"{row['Mean Adaptive Weight LGB %']:.0f}% / "
            f"{row['Mean Adaptive Weight XGB %']:.0f}%"
        )
        gap_pp = (row['Train Accuracy'] - row['Test Accuracy (Adaptive)']) * 100
        table_data.append([
            str(row['Set']), str(int(row['Rooms'])),
            f"{row['Train Accuracy']:.4f}",
            f"{row['Test Accuracy (Adaptive)']:.4f}",
            f"{gap_pp:.1f}",
            found_split,
        ])

    row_tints = {'A': '#f0f0f0', 'B': '#fff3e3', 'C': '#e7f4ff', 'D': '#f2e9f7', 'E': '#fbe9e7'}

    with plt.rc_context({'figure.facecolor': 'white', 'axes.facecolor': 'white', 'font.size': 9.5}):
        fig = plt.figure(figsize=(14, 1.7 + 0.5 * len(df)), dpi=300)
        ax = fig.add_subplot(111)
        ax.axis('off')

        col_widths = [0.08, 0.07, 0.15, 0.15, 0.1, 0.25]
        table = ax.table(cellText=table_data, cellLoc='center', loc='center', colWidths=col_widths)
        table.auto_set_font_size(False)
        table.set_fontsize(9.5)
        table.scale(1, 2.2)

        for j in range(len(headers)):
            cell = table[(0, j)]
            cell.set_facecolor('#2b8cbe')
            cell.set_text_props(weight='bold', color='white', fontsize=9.5)
            cell.set_edgecolor('#1f4e79')
            cell.set_linewidth(2)

        for i, (_, row) in enumerate(df.iterrows(), start=1):
            s = str(row['Set'])
            for j in range(len(headers)):
                cell = table[(i, j)]
                cell.set_facecolor(row_tints.get(s, '#ffffff'))
                cell.set_edgecolor('#cccccc')
                cell.set_linewidth(1)
                if j in (2, 3):
                    cell.set_text_props(weight='bold')

        fig.text(
            0.5, 0.94, 'Train vs Test Accuracy — the Overfitting Gap, by Param Set',
            ha='center', fontsize=14, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.8', facecolor='#2b8cbe', edgecolor='#1f4e79', linewidth=2, alpha=0.9),
            color='white',
        )
        fig.text(
            0.5, 0.03,
            'Read straight from disk, no retraining/predicting: Train Acc is the winning model\'s own final '
            'train_accuracy from its training history; Test Acc (Adaptive) is the same winner-take-all model '
            '(per room, chosen by _derive_ensemble_weights) averaged from test_from_excel.py\'s cached results. '
            'The last column is the average weight split the algorithm actually landed on, not a value we chose.',
            ha='center', fontsize=8, style='italic',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#f5f5f5', edgecolor='#cccccc', linewidth=1),
        )

        plt.tight_layout(rect=[0, 0.08, 1, 0.90])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)


def main():
    test_df = pd.read_csv(TEST_CSV)
    rows = []
    for s in SETS:
        r = process_set(s, test_df)
        if r:
            rows.append(r)
            print(f"{s}: Train={r['Train Accuracy']:.4f}  Test(Adaptive)={r['Test Accuracy (Adaptive)']:.4f}")
    if not rows:
        print("No results.")
        return
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"Saved CSV: {OUT_CSV}")
    plot_table(df, OUT_PNG)
    print(f"Saved PNG: {OUT_PNG}")


if __name__ == '__main__':
    main()
