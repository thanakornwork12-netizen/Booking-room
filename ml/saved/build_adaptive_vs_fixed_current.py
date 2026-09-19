"""Train / calibration / test accuracy comparison for the excel-split models
(saved_meta_{SET}_excel_split) — NOT the old saved_meta_*_new archive that
analyze_adaptive_weights_all_sets.py reads (that one is frozen/protected
and predates today's fixes). Pass --direct for the saved_meta_{SET}_direct run.

Reads straight from data that's already on disk — no retraining, no
re-predicting, no model loading. All three accuracies describe the SAME
winner-take-all model (ensemble_weights in meta.pkl records the winner):
  - "Train Accuracy"       = train_accuracy from the winner's history in
    meta.pkl, read at the calibration-best round (not the last round trained).
  - "Calibration Accuracy" = valid_accuracy from that same history and round —
    the 10% holdout split out of the 80% fit pool, which is what chose the round.
  - "Test Accuracy"        = per-room test_accuracy computed by
    test_from_excel.py and cached in metrics_plots/test_only_results.csv.
  - "Test Balanced Accuracy" sits beside it because plain accuracy is inflated
    in rooms that sit empty most days — see the note in process_set.

Train-Test can come out negative. That is not a bug: an underfit model has no
guarantee of scoring higher on its own fit rows than on a test window whose
class mix happens to be easier.

Usage: python ml/saved/build_adaptive_vs_fixed_current.py [--direct]
"""
import os
import sys
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

# --direct reads the direct-model sets (saved_meta_{SET}_direct and
# test_only_results_direct.csv) and writes separate files, so the pipeline
# table is kept for comparison.
DIRECT = '--direct' in sys.argv or '--blocked' in sys.argv
META_SUFFIX = '_direct' if DIRECT else '_excel_split'
if DIRECT:
    TEST_CSV = TEST_CSV.replace('.csv', '_direct.csv')
    OUT_PNG = OUT_PNG.replace('.png', '_direct.png')
    OUT_CSV = OUT_CSV.replace('.csv', '_direct.csv')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocked_variant  # noqa: E402
blocked_variant.apply(globals())

# A/B/C only. saved_meta_D/E_excel_split still exist but hold metas from an
# earlier run (before the daily-occupancy fix), so including them would put
# rows from two different datasets in one table.
# D is a direct-pipeline set only. saved_meta_D_excel_split exists but holds
# metas from a run that predates the daily-occupancy fix, so pulling it into the
# recursive figures would put two different datasets in one chart.
SETS = ['A', 'B', 'C', 'D'] if DIRECT else ['A', 'B', 'C']


def _acc_at_best(hist, key):
    """Accuracy of the model actually served — read at the calibration-best
    round, not the last round trained. `key` is 'train_accuracy' (the rows the
    booster was fit on) or 'valid_accuracy' (the 10% calibration holdout)."""
    vals = hist.get(key)
    if not vals:
        return None
    br, rounds = hist.get('best_round'), hist.get('rounds')
    if br and rounds and br in rounds:
        return vals[rounds.index(br)]
    if br and not rounds and 1 <= br <= len(vals):
        return vals[br - 1]
    return vals[-1]


def process_set(set_name, test_df):
    META_DIR = os.path.join(SAVED_DIR, f'saved_meta_{set_name}{META_SUFFIX}')
    if not os.path.isdir(META_DIR):
        print(f"skip {set_name}: no {META_DIR}")
        return None

    train_acc_list, valid_acc_list, valid_loss_list = [], [], []
    weight_sum = {'lightgbm': 0.0, 'xgboost': 0.0}
    n_rooms = 0

    for f in sorted(glob.glob(os.path.join(META_DIR, '*_meta.pkl'))):
        meta = joblib.load(f)
        weights = meta.get('ensemble_weights', {}) or {}
        winner = max(weights, key=weights.get) if weights else 'lightgbm'

        hist = meta.get('lgb_history', {}) if winner == 'lightgbm' else meta.get('xgb_history', {})
        for key, bucket in (('train_accuracy', train_acc_list), ('valid_accuracy', valid_acc_list)):
            acc = _acc_at_best(hist, key)
            if acc is not None:
                bucket.append(acc)
        loss = _acc_at_best(hist, 'valid_loss')
        if loss is not None:
            valid_loss_list.append(loss)

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
        'Calibration Accuracy': round(float(np.mean(valid_acc_list)), 4) if valid_acc_list else 0.0,
        'Test Accuracy (Adaptive)': round(float(set_test['test_accuracy'].mean()), 4) if len(set_test) else 0.0,
        # Plain test accuracy is inflated in rooms that are empty most days
        # (1C-MEETING is ~85% zero): always answering 'low' scores >0.95 there.
        # Balanced accuracy sits next to it so that inflation is visible.
        'Test Balanced Accuracy': round(float(set_test['balanced_accuracy'].mean()), 4) if len(set_test) else 0.0,
        # Calibration Loss is valid_loss (MAE in hours) at the same served
        # round as Calibration Accuracy -- how far off the hours forecast is,
        # not just whether the demand label was right.
        'Calibration Loss': round(float(np.mean(valid_loss_list)), 4) if valid_loss_list else 0.0,
        'Test R2': round(float(set_test['r2'].mean()), 4) if len(set_test) else 0.0,
        'Test MAE': round(float(set_test['mae'].mean()), 4) if len(set_test) else 0.0,
        'Mean Adaptive Weight LGB %': round(weight_pcts['lightgbm'], 1),
        'Mean Adaptive Weight XGB %': round(weight_pcts['xgboost'], 1),
    }


def plot_table(df: pd.DataFrame, png_path: str):
    headers = [
        'Set', 'Train Acc\n(fit rows)', 'Calib Acc\n(10% holdout)', 'Calib Loss\n(MAE, h)',
        'Test Acc\n(20% holdout)', 'Test R2', 'Test MAE\n(h)',
        'Weight Split Found by System\n(LGB / XGB)',
    ]
    table_data = [headers]
    for _, row in df.iterrows():
        found_split = (
            f"{row['Mean Adaptive Weight LGB %']:.0f}% / "
            f"{row['Mean Adaptive Weight XGB %']:.0f}%"
        )
        table_data.append([
            str(row['Set']),
            f"{row['Train Accuracy']:.4f}",
            f"{row['Calibration Accuracy']:.4f}",
            f"{row['Calibration Loss']:.3f}",
            f"{row['Test Accuracy (Adaptive)']:.4f}",
            f"{row['Test R2']:.3f}",
            f"{row['Test MAE']:.3f}",
            found_split,
        ])

    row_tints = {'A': '#f0f0f0', 'B': '#fff3e3', 'C': '#e7f4ff', 'D': '#f2e9f7', 'E': '#fbe9e7'}

    with plt.rc_context({'figure.facecolor': 'white', 'axes.facecolor': 'white', 'font.size': 9.5}):
        fig = plt.figure(figsize=(18, 1.7 + 0.5 * len(df)), dpi=300)
        ax = fig.add_subplot(111)
        ax.axis('off')

        col_widths = [0.06, 0.11, 0.11, 0.10, 0.11, 0.08, 0.09, 0.24]
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
                if j in (1, 4):
                    cell.set_text_props(weight='bold')

        fig.text(
            0.5, 0.94, 'Train / Calibration / Test — Accuracy, Loss, R2 and MAE by Param Set',
            ha='center', fontsize=14, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.8', facecolor='#2b8cbe', edgecolor='#1f4e79', linewidth=2, alpha=0.9),
            color='white',
        )
        fig.text(
            0.5, 0.03,
            'Read straight from disk, no retraining: every column comes from the same winner-take-all model, at '
            'the round it is served at. Calib Acc/Loss are the 10% holdout that chose that round; Test columns are '
            'the held-out 20% (Test R2/MAE from test_only_results, MAE in hours). LSTM is retired, so only LGB/XGB '
            'carry weight.',
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
            print(f"{s}: Train={r['Train Accuracy']:.4f}  Calib={r['Calibration Accuracy']:.4f}  "
                  f"Test={r['Test Accuracy (Adaptive)']:.4f}  BalAcc={r['Test Balanced Accuracy']:.4f}")
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
