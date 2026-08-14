# ══════════════════════════════════════════════════════════════════════════════
#  Adaptive (per-room, model-decides) vs Fixed (20/40/40) ensemble weight —
#  compared across ALL 5 param sets (A/B/C/D/E). NO retraining.
#
#  "Adaptive" = the REAL production formula already in forecast.py
#  (_derive_ensemble_weights): for each room, weight each base model by its
#  own prior × (R²/MAE) score on that room's calibration data — the model
#  that room's data says to trust gets more say, per room, per set.
#
#  "Fixed" = the same 20% LSTM / 40% LGB / 40% XGB for every room.
#
#  Both are blended from the SAME cached per-room predictions and scored on
#  the SAME held-out test split for every set, so the comparison is
#  apples-to-apples — unlike earlier runs that compared numbers computed
#  with different room counts / methodologies.
#
#  Outputs (separate from every earlier log/plot in this project):
#    metrics_plots/adaptive_weight_analysis.jsonl   (per-room, per-set detail)
#    metrics_plots/adaptive_vs_fixed_summary.csv    (per-set aggregate)
#    metrics_plots/adaptive_vs_fixed_by_set.png     (table, styled like
#                                                     hyperparam_comparison_reconciled.png)
#
#  Usage: python ml/saved/analyze_adaptive_weights_all_sets.py [--sets A,B,C,D,E]
# ══════════════════════════════════════════════════════════════════════════════
import os, sys, json, warnings, datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import forecast as F
from analyze_ensemble_weights import (
    load_raw_bookings, build_all_rooms_daily, collect_room_cal_predictions,
)
from booking.models import Room

METRICS_DIR = F.METRICS_DIR
JSONL_PATH = os.path.join(METRICS_DIR, 'adaptive_weight_analysis.jsonl')
CSV_PATH = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_summary.csv')
PNG_PATH = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_by_set.png')

FIXED_WEIGHTS = {'lstm': 0.20, 'lightgbm': 0.40, 'xgboost': 0.40}
SET_NAMES_DEFAULT = ['A', 'B', 'C', 'D', 'E']


def compute_full_metrics(y_true, y_pred, thr_high, thr_med, peak_ref) -> dict:
    y_pred = np.maximum(0.0, np.asarray(y_pred, dtype=float))
    _, cls = F._evaluate_with_best_threshold(y_true, y_pred, thr_high, thr_med, peak_ref)
    return {
        'accuracy': float(cls['accuracy']),
        'loss': float(cls['loss']),
        'r2': float(F.r2_score(y_true, y_pred)),
        'mae': float(F.mean_absolute_error(y_true, y_pred)),
        'rmse': float(F.rmse(y_true, y_pred)),
        'smape': float(F.smape(y_true, y_pred)),
    }


def round_pcts_to_100(pcts: dict) -> dict:
    """Round each percentage to a whole number while keeping the total at
    exactly 100 — rounding each value independently (e.g. 33.4/33.3/33.3)
    can drift to 99 or 101, which looks wrong in a report. Largest-remainder
    method: floor everything, then hand out the leftover points to whichever
    values had the biggest fractional part."""
    keys = list(pcts.keys())
    floors = {k: int(np.floor(pcts[k])) for k in keys}
    remainder = 100 - sum(floors.values())
    fracs = sorted(keys, key=lambda k: pcts[k] - floors[k], reverse=True)
    result = dict(floors)
    for k in fracs[:remainder]:
        result[k] += 1
    return result


def resolve_dirs(set_name: str):
    if set_name == 'C':
        return F.META_DIR, F.MODEL_DIR
    meta_dir = os.path.join(CURRENT_DIR, f'saved_meta_{set_name}_new')
    model_dir = os.path.join(CURRENT_DIR, f'saved_models_{set_name}_new')
    return meta_dir, model_dir


def load_or_build_rooms_data(set_name: str):
    cache_path = os.path.join(METRICS_DIR, f'.rooms_data_cache_{set_name}.pkl')
    if os.path.exists(cache_path):
        print(f"   📦 Loading cached predictions: {cache_path}")
        return joblib.load(cache_path)

    meta_dir, model_dir = resolve_dirs(set_name)
    if not os.path.isdir(meta_dir) or not os.path.isdir(model_dir):
        print(f"   ❌ No archive found for Set {set_name}: {meta_dir}")
        return []

    raw = load_raw_bookings()
    rooms = list(Room.objects.all())
    all_rooms_daily = build_all_rooms_daily(raw, rooms)

    rooms_data = []
    n_total = len(rooms)
    for i, room in enumerate(rooms, 1):
        d = collect_room_cal_predictions(room, raw, all_rooms_daily, meta_dir=meta_dir, model_dir=model_dir)
        if d is not None:
            rooms_data.append(d)
        if i % 10 == 0 or i == n_total:
            print(f"      ...{i}/{n_total} rooms ({i/n_total*100:.0f}%), {len(rooms_data)} usable", flush=True)
    if rooms_data:
        joblib.dump(rooms_data, cache_path)
        print(f"   📦 Cached: {cache_path}")
    return rooms_data


def process_set(set_name: str, jsonl_file) -> dict:
    print(f"\n{'=' * 70}\n🔍 Set {set_name}\n{'=' * 70}")
    rooms_data = load_or_build_rooms_data(set_name)
    if not rooms_data:
        return None

    per_room_metrics = {
        'lstm': [], 'lightgbm': [], 'xgboost': [], 'fixed_ensemble': [], 'adaptive_ensemble': [],
    }
    adaptive_weights_seen = []

    for d in rooms_data:
        cal, test = d['cal'], d['test']
        thr_high, thr_med, peak_ref = d['thr_high'], d['thr_med'], d['peak_ref']

        # The REAL production formula: derive per-room weights from this
        # room's OWN calibration performance (never sees the test split).
        adaptive_w = F._derive_ensemble_weights(
            cal['y'],
            {'lstm': cal['lstm'], 'lightgbm': cal['lgb'], 'xgboost': cal['xgb']},
            primary='lstm',
        )
        adaptive_weights_seen.append(adaptive_w)

        adaptive_pred = (
            adaptive_w.get('lstm', 0.0) * test['lstm']
            + adaptive_w.get('lightgbm', 0.0) * test['lgb']
            + adaptive_w.get('xgboost', 0.0) * test['xgb']
        )
        fixed_pred = (
            FIXED_WEIGHTS['lstm'] * test['lstm']
            + FIXED_WEIGHTS['lightgbm'] * test['lgb']
            + FIXED_WEIGHTS['xgboost'] * test['xgb']
        )

        room_metrics = {
            'lstm': compute_full_metrics(test['y'], test['lstm'], thr_high, thr_med, peak_ref),
            'lightgbm': compute_full_metrics(test['y'], test['lgb'], thr_high, thr_med, peak_ref),
            'xgboost': compute_full_metrics(test['y'], test['xgb'], thr_high, thr_med, peak_ref),
            'fixed_ensemble': compute_full_metrics(test['y'], fixed_pred, thr_high, thr_med, peak_ref),
            'adaptive_ensemble': compute_full_metrics(test['y'], adaptive_pred, thr_high, thr_med, peak_ref),
        }
        for key, vals in room_metrics.items():
            per_room_metrics[key].append(vals)

        jsonl_file.write(json.dumps({
            'timestamp': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'param_set': set_name,
            'room': d['room'],
            'adaptive_weights': {k: round(float(v), 4) for k, v in adaptive_w.items()},
            'fixed_weights': FIXED_WEIGHTS,
            'metrics': room_metrics,
        }, ensure_ascii=False) + '\n')
    jsonl_file.flush()

    mean_adaptive_w = {
        k: float(np.mean([w.get(k, 0.0) for w in adaptive_weights_seen]))
        for k in ('lstm', 'lightgbm', 'xgboost')
    }

    def _mean(key, field):
        return float(np.mean([m[field] for m in per_room_metrics[key]]))

    weight_pcts = round_pcts_to_100({
        'lstm': mean_adaptive_w['lstm'] * 100,
        'lightgbm': mean_adaptive_w['lightgbm'] * 100,
        'xgboost': mean_adaptive_w['xgboost'] * 100,
    })

    summary = {
        'Set': set_name,
        'Rooms': len(rooms_data),
        'R2 (adaptive)': round(_mean('adaptive_ensemble', 'r2'), 4),
        'MAE (adaptive)': round(_mean('adaptive_ensemble', 'mae'), 4),
        'RMSE (adaptive)': round(_mean('adaptive_ensemble', 'rmse'), 4),
        'sMAPE (adaptive)': round(_mean('adaptive_ensemble', 'smape'), 2),
        'LSTM Acc': round(_mean('lstm', 'accuracy'), 4),
        'LGB Acc': round(_mean('lightgbm', 'accuracy'), 4),
        'XGB Acc': round(_mean('xgboost', 'accuracy'), 4),
        'Fixed Ensemble Acc (20/40/40)': round(_mean('fixed_ensemble', 'accuracy'), 4),
        'Adaptive Ensemble Acc': round(_mean('adaptive_ensemble', 'accuracy'), 4),
        'Fixed Ensemble Loss (20/40/40)': round(_mean('fixed_ensemble', 'loss'), 4),
        'Adaptive Ensemble Loss': round(_mean('adaptive_ensemble', 'loss'), 4),
        'Mean Adaptive Weight LSTM %': weight_pcts['lstm'],
        'Mean Adaptive Weight LGB %': weight_pcts['lightgbm'],
        'Mean Adaptive Weight XGB %': weight_pcts['xgboost'],
    }
    print(
        f"\n📊 Set {set_name}: Fixed Acc={summary['Fixed Ensemble Acc (20/40/40)']:.4f}  "
        f"Adaptive Acc={summary['Adaptive Ensemble Acc']:.4f}  "
        f"(mean adaptive weight: LSTM {summary['Mean Adaptive Weight LSTM %']}% / "
        f"LGB {summary['Mean Adaptive Weight LGB %']}% / XGB {summary['Mean Adaptive Weight XGB %']}%)"
    )
    return summary


def plot_table(df: pd.DataFrame, png_path: str):
    headers = [
        'Set', 'Rooms', 'R²', 'MAE', 'RMSE', 'sMAPE',
        'LSTM Acc', 'LGB Acc', 'XGB Acc', 'Fixed Acc\n(20/40/40)', 'Adaptive Acc\n(model decides)',
        'Weight Split Found by System\n(LSTM / LGB / XGB)',
    ]
    table_data = [headers]
    for _, row in df.iterrows():
        found_split = (
            f"{row['Mean Adaptive Weight LSTM %']:.0f}% / "
            f"{row['Mean Adaptive Weight LGB %']:.0f}% / "
            f"{row['Mean Adaptive Weight XGB %']:.0f}%"
        )
        table_data.append([
            str(row['Set']), str(int(row['Rooms'])),
            f"{row['R2 (adaptive)']:.4f}", f"{row['MAE (adaptive)']:.4f}",
            f"{row['RMSE (adaptive)']:.4f}", f"{row['sMAPE (adaptive)']:.2f}%",
            f"{row['LSTM Acc']:.4f}", f"{row['LGB Acc']:.4f}", f"{row['XGB Acc']:.4f}",
            f"{row['Fixed Ensemble Acc (20/40/40)']:.4f}",
            f"{row['Adaptive Ensemble Acc']:.4f}",
            found_split,
        ])

    row_tints = {'A': '#f0f0f0', 'B': '#fff3e3', 'C': '#e7f4ff', 'D': '#f2e9f7', 'E': '#fbe9e7'}

    with plt.rc_context({'figure.facecolor': 'white', 'axes.facecolor': 'white', 'font.size': 9.5}):
        fig = plt.figure(figsize=(18, 1.7 + 0.5 * len(df)), dpi=300)
        ax = fig.add_subplot(111)
        ax.axis('off')

        col_widths = [0.06, 0.05] + [0.07] * 7 + [0.11, 0.12, 0.16]
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
            winner_col = 10 if row['Adaptive Ensemble Acc'] >= row['Fixed Ensemble Acc (20/40/40)'] else 9
            for j in range(len(headers)):
                cell = table[(i, j)]
                cell.set_facecolor(row_tints.get(s, '#ffffff'))
                cell.set_edgecolor('#cccccc')
                cell.set_linewidth(1)
                if j in (9, 10, 11):
                    cell.set_text_props(weight='bold' if j in (winner_col, 11) else 'normal')

        fig.text(
            0.5, 0.94, 'Ensemble Weight: Chosen by the System per Room, not Fixed by Us — by Param Set',
            ha='center', fontsize=14, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.8', facecolor='#2b8cbe', edgecolor='#1f4e79', linewidth=2, alpha=0.9),
            color='white',
        )
        fig.text(
            0.5, 0.03,
            'No retraining — same saved LSTM/LightGBM/XGBoost models per room and set, scored on the held-out test split. '
            '"Adaptive" = production formula (_derive_ensemble_weights): weight each model by its own R²/MAE on that '
            'room\'s calibration data — the last column is the average split the algorithm actually landed on, not a '
            'value we chose. Bold = the higher Ensemble Acc between Fixed/Adaptive per set.',
            ha='center', fontsize=8, style='italic',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#f5f5f5', edgecolor='#cccccc', linewidth=1),
        )

        plt.tight_layout(rect=[0, 0.08, 1, 0.90])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)


def plot_line_style_summary(df: pd.DataFrame, png_path: str):
    """3-panel line chart styled like param_set_val_acc_by_model.png (line +
    marker, shared grid style) — but there's no epoch axis for a per-set
    aggregate, so Set (A-E) is the x-axis instead, with one line each for
    Fixed vs Adaptive. Reads only the summary CSV — no models, no Django/TF
    work beyond what's already imported, seconds to regenerate."""
    sets = list(df['Set'])
    panels = [
        ('Fixed Ensemble Acc (20/40/40)', 'Adaptive Ensemble Acc', 'Ensemble Accuracy', 'Accuracy'),
        ('R2 (adaptive)', None, 'R² (adaptive)', 'R²'),
        ('MAE (adaptive)', None, 'MAE (adaptive)', 'MAE (ชม.)'),
    ]
    with plt.style.context({'axes.grid': True, 'grid.alpha': 0.45, 'font.size': 10}):
        fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), dpi=300)

        # Panel 1: Fixed vs Adaptive accuracy, one line each, across sets
        ax = axes[0]
        ax.plot(sets, df['Fixed Ensemble Acc (20/40/40)'], color='#9e9e9e', linewidth=2.2,
                marker='o', markersize=5, linestyle='--', label='Fixed (20/40/40)')
        ax.plot(sets, df['Adaptive Ensemble Acc'], color='#2b8cbe', linewidth=2.5,
                marker='o', markersize=5, label='Adaptive (model decides)')
        ax.set_title('Ensemble Accuracy', fontweight='bold')
        ax.set_ylabel('Accuracy')
        ax.set_ylim(0.85, 1.0)
        ax.legend(loc='lower right', frameon=True, fontsize=8.5)

        # Panel 2: R2 of the adaptive ensemble across sets
        ax = axes[1]
        ax.plot(sets, df['R2 (adaptive)'], color='#ff7f0e', linewidth=2.2, marker='o', markersize=5)
        ax.set_title('R² (Adaptive Ensemble)', fontweight='bold')
        ax.set_ylabel('R²')

        # Panel 3: weight split found by the system, stacked lines
        ax = axes[2]
        ax.plot(sets, df['Mean Adaptive Weight LSTM %'], color='#1f77b4', linewidth=2.2,
                marker='o', markersize=5, label='LSTM')
        ax.plot(sets, df['Mean Adaptive Weight LGB %'], color='#ff7f0e', linewidth=2.2,
                marker='o', markersize=5, label='LGB')
        ax.plot(sets, df['Mean Adaptive Weight XGB %'], color='#2ca02c', linewidth=2.2,
                marker='o', markersize=5, label='XGB')
        ax.set_title('Weight Split Found by System', fontweight='bold')
        ax.set_ylabel('Weight (%)')
        ax.set_ylim(0, 65)
        ax.legend(loc='center right', frameon=True, fontsize=8.5)

        for ax in axes:
            ax.set_xlabel('Param Set')
            ax.grid(True, alpha=0.45)

        fig.suptitle('Adaptive vs Fixed Ensemble Weight, by Param Set (A-E)', fontweight='bold', fontsize=14)
        fig.text(
            0.5, 0.005,
            'Source: adaptive_vs_fixed_summary.csv — no retraining, same saved models per set, scored on held-out test split.',
            ha='center', fontsize=8, style='italic',
        )
        plt.tight_layout(rect=[0, 0.03, 1, 0.93])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)


PARAM_SET_COLORS = {'A': '#636363', 'B': '#fdae6b', 'C': '#2b8cbe', 'D': '#8e44ad', 'E': '#c0392b'}


def plot_per_room_metric_curve(jsonl_path: str, png_path: str, metric: str = 'accuracy'):
    """Real multi-point curve version of param_set_val_acc_by_model.png /
    param_set_val_loss_by_model.png — those charts' x-axis is Epoch/Round
    (training has a natural sequence); adaptive weighting doesn't, so each
    line here is that set's per-room values SORTED ascending — x-axis is
    just "room rank", not a real epoch, but it produces the same dense,
    smooth curve shape. 3 panels: Fixed Ensemble / Adaptive Ensemble / LSTM
    (solo, for reference).
    """
    is_loss = metric == 'loss'
    records = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue

    by_set = {}
    for rec in records:
        by_set.setdefault(rec['param_set'], []).append(rec)

    panels = [
        ('fixed_ensemble', 'Fixed Ensemble (20/40/40)'),
        ('adaptive_ensemble', 'Adaptive Ensemble (model decides)'),
        ('lstm', 'LSTM (solo, for reference)'),
    ]

    with plt.style.context({'axes.grid': True, 'grid.alpha': 0.45, 'font.size': 10}):
        fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), dpi=300, sharey=True)

        all_values = []
        for ax, (metric_key, title) in zip(axes, panels):
            for set_name in sorted(by_set.keys()):
                vals = sorted(r['metrics'][metric_key][metric] for r in by_set[set_name])
                all_values.extend(vals)
                ax.plot(
                    range(1, len(vals) + 1), vals,
                    label=set_name, color=PARAM_SET_COLORS.get(set_name),
                    linewidth=2.2, marker='o', markersize=3,
                )
            ax.set_title(title, fontweight='bold')
            ax.set_xlabel(f'Room rank (sorted by {metric}, low → high)')
            ax.grid(True, alpha=0.45)

        if is_loss:
            lo, hi = min(all_values), max(all_values)
            pad = (hi - lo) * 0.1 or 0.1
            for ax in axes:
                ax.set_ylim(max(0, lo - pad), hi + pad)
        else:
            for ax in axes:
                ax.set_ylim(0.0, 1.05)

        axes[0].set_ylabel('Loss (cross-entropy)' if is_loss else 'Accuracy')
        axes[0].legend(loc=('upper right' if is_loss else 'lower right'), frameon=True, fontsize=8.5, title='Param Set')
        fig.suptitle(
            f'Ensemble {"Loss" if is_loss else "Accuracy"} Across Rooms, by Param Set (A-E)',
            fontweight='bold', fontsize=14,
        )
        fig.text(
            0.5, 0.005,
            f'Source: adaptive_weight_analysis.jsonl — each line is that set\'s per-room {metric} values sorted '
            'ascending (rooms aren\'t naturally ordered, so this shows the shape/spread instead of a real epoch axis).',
            ha='center', fontsize=8, style='italic',
        )
        plt.tight_layout(rect=[0, 0.03, 1, 0.93])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)


def plot_per_set_cards(df: pd.DataFrame, png_path: str):
    """One summary card per param set, Fixed vs Adaptive side by side —
    reads only adaptive_vs_fixed_summary.csv, no retraining, no model loading."""
    sets = list(df['Set'])
    n = len(sets)
    with plt.rc_context({'figure.facecolor': 'white', 'axes.facecolor': 'white', 'font.size': 10}):
        fig, axes = plt.subplots(1, n, figsize=(3.6 * n, 5.5), dpi=300)
        if n == 1:
            axes = [axes]
        for ax, (_, row) in zip(axes, df.iterrows()):
            fixed_acc = row['Fixed Ensemble Acc (20/40/40)']
            adaptive_acc = row['Adaptive Ensemble Acc']
            winner_is_adaptive = adaptive_acc >= fixed_acc
            bars = ax.bar(
                ['Fixed\n20/40/40', 'Adaptive\n(model decides)'],
                [fixed_acc, adaptive_acc],
                color=['#9e9e9e', '#2b8cbe'],
                width=0.6,
            )
            top = max(fixed_acc, adaptive_acc)
            ax.set_ylim(0, top * 1.22)
            for bar, val in zip(bars, [fixed_acc, adaptive_acc]):
                ax.text(bar.get_x() + bar.get_width() / 2, val + top * 0.02, f'{val:.4f}',
                        ha='center', va='bottom', fontsize=9)
            delta = adaptive_acc - fixed_acc
            arrow = '▲' if delta >= 0 else '▼'
            color = '#1a7f37' if delta >= 0 else '#c0392b'
            ax.text(0.5, top * 1.14, f'{arrow} {delta:+.4f}', ha='center', fontsize=10,
                    fontweight='bold', color=color, transform=ax.transData)
            weight_line = (
                f"{row['Mean Adaptive Weight LSTM %']:.0f}/"
                f"{row['Mean Adaptive Weight LGB %']:.0f}/"
                f"{row['Mean Adaptive Weight XGB %']:.0f}"
            )
            ax.set_title(f"Set {row['Set']}", fontweight='bold', fontsize=13)
            ax.set_xlabel(f'weight found: {weight_line}', fontsize=8)
            ax.grid(True, alpha=0.3, axis='y')
            for spine in ('top', 'right'):
                ax.spines[spine].set_visible(False)

        fig.suptitle('Fixed vs Adaptive Ensemble — Card per Param Set', fontweight='bold', fontsize=14)
        fig.text(
            0.5, 0.01,
            'Source: adaptive_vs_fixed_summary.csv — no retraining. ▲/▼ shows Adaptive minus Fixed accuracy; '
            '"weight found" is the average LSTM/LGB/XGB split the adaptive formula landed on for that set.',
            ha='center', fontsize=8, style='italic', color='#444444',
        )
        plt.tight_layout(rect=[0, 0.05, 1, 0.93])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)


def plot_acc_loss_line_chart(df: pd.DataFrame, png_path: str):
    """2-panel line chart: Accuracy and Loss, Fixed vs Adaptive, across sets.
    Reads only the summary CSV — no retraining, no model loading."""
    sets = list(df['Set'])
    with plt.style.context({'axes.grid': True, 'grid.alpha': 0.45, 'font.size': 10}):
        fig, axes = plt.subplots(1, 2, figsize=(11, 5.5), dpi=300)

        ax = axes[0]
        ax.plot(sets, df['Fixed Ensemble Acc (20/40/40)'], color='#9e9e9e', linewidth=2.2,
                marker='o', markersize=6, linestyle='--', label='Fixed (20/40/40)')
        ax.plot(sets, df['Adaptive Ensemble Acc'], color='#2b8cbe', linewidth=2.5,
                marker='o', markersize=6, label='Adaptive (model decides)')
        ax.set_title('Ensemble Accuracy', fontweight='bold')
        ax.set_xlabel('Param Set')
        ax.set_ylabel('Accuracy')
        ax.legend(loc='lower right', frameon=True, fontsize=8.5)
        ax.grid(True, alpha=0.45)

        ax = axes[1]
        ax.plot(sets, df['Fixed Ensemble Loss (20/40/40)'], color='#9e9e9e', linewidth=2.2,
                marker='o', markersize=6, linestyle='--', label='Fixed (20/40/40)')
        ax.plot(sets, df['Adaptive Ensemble Loss'], color='#e07b39', linewidth=2.5,
                marker='o', markersize=6, label='Adaptive (model decides)')
        ax.set_title('Ensemble Loss (cross-entropy)', fontweight='bold')
        ax.set_xlabel('Param Set')
        ax.set_ylabel('Loss')
        ax.legend(loc='upper right', frameon=True, fontsize=8.5)
        ax.grid(True, alpha=0.45)

        fig.suptitle('Fixed vs Adaptive — Accuracy & Loss, by Param Set (A-E)', fontweight='bold', fontsize=14)
        fig.text(
            0.5, 0.005,
            'Source: adaptive_vs_fixed_summary.csv — no retraining, same saved models per set, scored on held-out test split.',
            ha='center', fontsize=8, style='italic',
        )
        plt.tight_layout(rect=[0, 0.03, 1, 0.92])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)


def _plot_single_metric_line(df: pd.DataFrame, png_path: str, column: str, title: str, ylabel: str, color: str):
    """One metric, one weighting scheme, all 5 sets — a single line chart."""
    sets = list(df['Set'])
    with plt.style.context({'axes.grid': True, 'grid.alpha': 0.45, 'font.size': 11}):
        fig, ax = plt.subplots(figsize=(7, 5.5), dpi=300)
        ax.plot(sets, df[column], color=color, linewidth=2.5, marker='o', markersize=7)
        for x, y in zip(sets, df[column]):
            ax.annotate(f'{y:.4f}', (x, y), textcoords='offset points', xytext=(0, 8), ha='center', fontsize=9)
        ax.set_title(title, fontweight='bold', fontsize=13)
        ax.set_xlabel('Param Set')
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.45)
        fig.text(
            0.5, 0.01,
            'Source: adaptive_vs_fixed_summary.csv — no retraining, same saved models per set, scored on held-out test split.',
            ha='center', fontsize=8, style='italic',
        )
        plt.tight_layout(rect=[0, 0.04, 1, 1])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)


def plot_four_separate_charts(df: pd.DataFrame):
    specs = [
        ('adaptive_vs_fixed_accuracy_fixed.png', 'Fixed Ensemble Acc (20/40/40)',
         'Ensemble Accuracy — Fixed (20/40/40)', 'Accuracy', '#9e9e9e'),
        ('adaptive_vs_fixed_accuracy_adaptive.png', 'Adaptive Ensemble Acc',
         'Ensemble Accuracy — Adaptive (model decides)', 'Accuracy', '#2b8cbe'),
        ('adaptive_vs_fixed_loss_fixed.png', 'Fixed Ensemble Loss (20/40/40)',
         'Ensemble Loss — Fixed (20/40/40)', 'Loss (cross-entropy)', '#9e9e9e'),
        ('adaptive_vs_fixed_loss_adaptive.png', 'Adaptive Ensemble Loss',
         'Ensemble Loss — Adaptive (model decides)', 'Loss (cross-entropy)', '#e07b39'),
    ]
    for fname, column, title, ylabel, color in specs:
        out_png = os.path.join(METRICS_DIR, fname)
        _plot_single_metric_line(df, out_png, column, title, ylabel, color)
        print(f"📄 Saved: {out_png}")


def main():
    if '--four' in sys.argv:
        if not os.path.exists(CSV_PATH):
            print(f"❌ {CSV_PATH} not found — run the full analysis first.")
            return
        df = pd.read_csv(CSV_PATH)
        plot_four_separate_charts(df)
        return

    if '--accloss' in sys.argv:
        if not os.path.exists(CSV_PATH):
            print(f"❌ {CSV_PATH} not found — run the full analysis first.")
            return
        df = pd.read_csv(CSV_PATH)
        out_png = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_acc_loss.png')
        plot_acc_loss_line_chart(df, out_png)
        print(f"📄 Saved: {out_png}")
        return

    if '--cards' in sys.argv:
        if not os.path.exists(CSV_PATH):
            print(f"❌ {CSV_PATH} not found — run the full analysis first.")
            return
        df = pd.read_csv(CSV_PATH)
        cards_png = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_cards.png')
        plot_per_set_cards(df, cards_png)
        print(f"📄 Saved: {cards_png}")
        return

    if '--roomcurve' in sys.argv:
        if not os.path.exists(JSONL_PATH):
            print(f"❌ {JSONL_PATH} not found — run the full analysis first.")
            return
        curve_png = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_room_curve.png')
        plot_per_room_accuracy_curve(JSONL_PATH, curve_png)
        print(f"📄 Saved: {curve_png}")
        return

    if '--chart' in sys.argv:
        if not os.path.exists(CSV_PATH):
            print(f"❌ {CSV_PATH} not found — run the full analysis first.")
            return
        df = pd.read_csv(CSV_PATH)
        chart_png = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_line_chart.png')
        plot_line_style_summary(df, chart_png)
        print(f"📄 Saved: {chart_png}")
        return

    set_names = SET_NAMES_DEFAULT
    if '--sets' in sys.argv:
        idx = sys.argv.index('--sets')
        if len(sys.argv) > idx + 1:
            set_names = [s.strip().upper() for s in sys.argv[idx + 1].split(',') if s.strip()]

    print("=" * 70)
    print(f"🔍 Adaptive vs Fixed Ensemble Weight — Sets: {', '.join(set_names)}")
    print("=" * 70)

    summaries = []
    with open(JSONL_PATH, 'a', encoding='utf-8') as jsonl_file:
        for set_name in set_names:
            summary = process_set(set_name, jsonl_file)
            if summary is not None:
                summaries.append(summary)

    if not summaries:
        print("❌ No sets produced results — nothing to summarize.")
        return

    df = pd.DataFrame(summaries)
    df.to_csv(CSV_PATH, index=False)
    print(f"\n📄 Saved: {CSV_PATH}")
    print(f"📄 Per-room detail log (appended): {JSONL_PATH}")

    plot_table(df, PNG_PATH)
    print(f"📄 Saved: {PNG_PATH}")

    print("\n📊 Final summary:")
    print(df[['Set', 'Rooms', 'Fixed Ensemble Acc (20/40/40)', 'Adaptive Ensemble Acc']].to_string(index=False))
    n_adaptive_wins = int((df['Adaptive Ensemble Acc'] >= df['Fixed Ensemble Acc (20/40/40)']).sum())
    print(f"\n🏆 Adaptive weighting wins in {n_adaptive_wins}/{len(df)} sets")
    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
