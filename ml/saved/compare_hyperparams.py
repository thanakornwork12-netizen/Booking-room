"""
Compare Hyperparameter Sets A, B, C Results
Generates comparison plots and table from saved metadata
"""
import os
import sys
import csv
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
import joblib

CURRENT_DIR = Path(__file__).resolve().parent
META_DIR = CURRENT_DIR / "saved_meta"
# NOTE: previously this also merged in saved_meta_A/B/C (archived snapshots
# from an older, separate comparison run with a different, fixed room count
# per set). Mixing that archive with the live saved_meta/ folder made
# "Ensemble Acc" here disagree with param_set_summary_table.png /
# plot_param_set_ensemble_accuracy, which read saved_meta/ only. Restricting
# to saved_meta/ keeps this report consistent with the rest of the reporting
# pipeline — it always reflects current production state.
ARCHIVE_META_DIRS = [
    META_DIR,
]
PARAM_SET_NAMES = {
    'A': 'A - Fast (Baseline)',
    'B': 'B - Balanced (Aggressive)',
    'C': 'C - High Quality',
    'D': 'D - Extra Deep (Experimental)',
}
METRICS_DIR = CURRENT_DIR / "metrics_plots"

os.makedirs(METRICS_DIR, exist_ok=True)


def load_all_meta_by_set():
    """Load all metadata and group by parameter set."""
    meta_by_set = {'A': [], 'B': [], 'C': [], 'D': [], 'UNKNOWN': []}
    known_dirs = {
        'saved_meta_A': 'A',
        'saved_meta_B': 'B',
        'saved_meta_C': 'C',
        'saved_meta_D': 'D',
    }

    found_dirs = [d for d in ARCHIVE_META_DIRS if d.exists()]
    if not found_dirs:
        print(f"⚠️  No metadata directories found among: {', '.join(str(d) for d in ARCHIVE_META_DIRS)}")
        return meta_by_set

    for meta_dir in found_dirs:
        source_label = known_dirs.get(meta_dir.name, None)
        for meta_file in sorted(meta_dir.glob('*_meta.pkl')):
            try:
                meta = joblib.load(meta_file)
                if not isinstance(meta, dict):
                    continue
                param_set = meta.get('param_set') or source_label
                if param_set in {'A', 'B', 'C'}:
                    meta_by_set[param_set].append(meta)
                else:
                    meta_by_set['UNKNOWN'].append(meta)
            except Exception as e:
                print(f"⚠️  Failed to load {meta_file}: {e}")

    return meta_by_set


def compute_set_statistics(metas, set_name):
    """Compute average metrics for a parameter set."""
    if not metas:
        return None
    
    stats = {
        'set': set_name,
        'room_count': len(metas),
        'accuracy': [],
        'loss': [],
        'r2': [],
        'mae': [],
        'rmse': [],
        'smape': [],
        'lstm_acc': [],
        'lightgbm_acc': [],
        'xgboost_acc': [],
        'ensemble_acc': [],
    }
    
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        
        # Classification metrics
        cls_metrics = meta.get('cls_metrics') or {}
        if isinstance(cls_metrics, dict):
            stats['accuracy'].append(float(cls_metrics.get('accuracy', np.nan)))
            stats['loss'].append(float(cls_metrics.get('loss', np.nan)))
        
        # Regression metrics
        reg_metrics = meta.get('reg_metrics') or {}
        if isinstance(reg_metrics, dict):
            stats['r2'].append(float(reg_metrics.get('r2', np.nan)))
            stats['mae'].append(float(reg_metrics.get('mae', np.nan)))
            stats['rmse'].append(float(reg_metrics.get('rmse', np.nan)))
            stats['smape'].append(float(reg_metrics.get('smape', np.nan)))
        
        # Per-model accuracy
        model_metrics = meta.get('model_metrics') or {}
        if isinstance(model_metrics, dict):
            for model_name in ['lstm', 'lightgbm', 'xgboost', 'ensemble']:
                key_name = f'{model_name}_acc'
                if key_name not in stats:
                    stats[key_name] = []
                metrics = model_metrics.get(model_name, {}) or {}
                cls = metrics.get('classification') or {}
                if not isinstance(cls, dict):
                    cls = {}
                acc = cls.get('accuracy', np.nan)
                if isinstance(acc, (int, float)):
                    stats[key_name].append(float(acc))
    
    # Compute averages
    result = {'set': set_name, 'room_count': len(metas)}
    for key in ['accuracy', 'loss', 'r2', 'mae', 'rmse', 'smape', 
                'lstm_acc', 'lightgbm_acc', 'xgboost_acc', 'ensemble_acc']:
        values = np.asarray(stats[key], dtype=float)
        values = values[np.isfinite(values)]
        if len(values) > 0:
            result[f'{key}_mean'] = float(np.mean(values))
            result[f'{key}_std'] = float(np.std(values))
            result[f'{key}_count'] = len(values)
        else:
            result[f'{key}_mean'] = np.nan
            result[f'{key}_std'] = np.nan
            result[f'{key}_count'] = 0
    
    return result


def write_comparison_csv(comparison_data, csv_path):
    """Write comparison table to CSV."""
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = [
        'Set', 'Rooms',
        'Accuracy Mean', 'Accuracy Std', 'Accuracy Count',
        'Loss Mean', 'Loss Std', 'Loss Count',
        'R² Mean', 'R² Std', 'R² Count',
        'MAE Mean', 'MAE Std', 'MAE Count',
        'RMSE Mean', 'RMSE Std', 'RMSE Count',
        'sMAPE Mean', 'sMAPE Std', 'sMAPE Count',
        'LSTM Acc Mean', 'LSTM Acc Std', 'LSTM Acc Count',
        'LGB Acc Mean', 'LGB Acc Std', 'LGB Acc Count',
        'XGB Acc Mean', 'XGB Acc Std', 'XGB Acc Count',
        'Ensemble Acc Mean', 'Ensemble Acc Std', 'Ensemble Acc Count',
    ]
    
    def numeric_fmt(value, fmt='.4f'):
        try:
            return format(0.0 if not np.isfinite(value) else value, fmt)
        except Exception:
            return format(0.0, fmt)

    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for set_name, stats in sorted(comparison_data.items()):
            row = {
                'Set': set_name,
                'Rooms': stats['room_count'],
                'Accuracy Mean': numeric_fmt(stats.get('accuracy_mean', np.nan)),
                'Accuracy Std': numeric_fmt(stats.get('accuracy_std', np.nan)),
                'Accuracy Count': stats.get('accuracy_count', 0),
                'Loss Mean': numeric_fmt(stats.get('loss_mean', np.nan)),
                'Loss Std': numeric_fmt(stats.get('loss_std', np.nan)),
                'Loss Count': stats.get('loss_count', 0),
                'R² Mean': numeric_fmt(stats.get('r2_mean', np.nan)),
                'R² Std': numeric_fmt(stats.get('r2_std', np.nan)),
                'R² Count': stats.get('r2_count', 0),
                'MAE Mean': numeric_fmt(stats.get('mae_mean', np.nan)),
                'MAE Std': numeric_fmt(stats.get('mae_std', np.nan)),
                'MAE Count': stats.get('mae_count', 0),
                'RMSE Mean': numeric_fmt(stats.get('rmse_mean', np.nan)),
                'RMSE Std': numeric_fmt(stats.get('rmse_std', np.nan)),
                'RMSE Count': stats.get('rmse_count', 0),
                'sMAPE Mean': numeric_fmt(stats.get('smape_mean', np.nan), fmt='.2f') + '%',
                'sMAPE Std': numeric_fmt(stats.get('smape_std', np.nan), fmt='.2f') + '%',
                'sMAPE Count': stats.get('smape_count', 0),
                'LSTM Acc Mean': numeric_fmt(stats.get('lstm_acc_mean', np.nan)),
                'LSTM Acc Std': numeric_fmt(stats.get('lstm_acc_std', np.nan)),
                'LSTM Acc Count': stats.get('lstm_acc_count', 0),
                'LGB Acc Mean': numeric_fmt(stats.get('lightgbm_acc_mean', np.nan)),
                'LGB Acc Std': numeric_fmt(stats.get('lightgbm_acc_std', np.nan)),
                'LGB Acc Count': stats.get('lightgbm_acc_count', 0),
                'XGB Acc Mean': numeric_fmt(stats.get('xgboost_acc_mean', np.nan)),
                'XGB Acc Std': numeric_fmt(stats.get('xgboost_acc_std', np.nan)),
                'XGB Acc Count': stats.get('xgboost_acc_count', 0),
                'Ensemble Acc Mean': numeric_fmt(stats.get('ensemble_acc_mean', np.nan)),
                'Ensemble Acc Std': numeric_fmt(stats.get('ensemble_acc_std', np.nan)),
                'Ensemble Acc Count': stats.get('ensemble_acc_count', 0),
            }
            writer.writerow(row)


def plot_comparison(comparison_data, out_png):
    """Generate comparison plot for parameter sets."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("⚠️  matplotlib not available, skipping plot generation")
        return False
    
    sets = sorted(comparison_data.keys())
    if not sets:
        print("No data to plot")
        return False
    
    accuracy_means = [comparison_data[s].get('accuracy_mean', np.nan) for s in sets]
    loss_means = [comparison_data[s].get('loss_mean', np.nan) for s in sets]
    r2_means = [comparison_data[s].get('r2_mean', np.nan) for s in sets]
    mae_means = [comparison_data[s].get('mae_mean', np.nan) for s in sets]
    
    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 11,
    }):
        fig, axes = plt.subplots(2, 2, figsize=(12, 9), dpi=300)
        
        # Accuracy
        axes[0, 0].bar(sets, accuracy_means, color=['#e7f4ff', '#fff8e7', '#ffe7e7'])
        axes[0, 0].set_title('Average Classification Accuracy', fontweight='bold')
        axes[0, 0].set_ylabel('Accuracy')
        axes[0, 0].set_ylim(0, 1.0)
        axes[0, 0].grid(True, alpha=0.3)
        for i, (s, val) in enumerate(zip(sets, accuracy_means)):
            if np.isfinite(val):
                axes[0, 0].text(i, val + 0.02, f'{val:.3f}', ha='center', va='bottom')
        
        # Loss
        axes[0, 1].bar(sets, loss_means, color=['#e7f4ff', '#fff8e7', '#ffe7e7'])
        axes[0, 1].set_title('Average MAE Loss', fontweight='bold')
        axes[0, 1].set_ylabel('Loss')
        axes[0, 1].grid(True, alpha=0.3)
        for i, (s, val) in enumerate(zip(sets, loss_means)):
            if np.isfinite(val):
                axes[0, 1].text(i, val + 0.01, f'{val:.3f}', ha='center', va='bottom')
        
        # R² Score
        axes[1, 0].bar(sets, r2_means, color=['#e7f4ff', '#fff8e7', '#ffe7e7'])
        axes[1, 0].set_title('Average R² Score', fontweight='bold')
        axes[1, 0].set_ylabel('R² Score')
        axes[1, 0].set_ylim(0, 1.0)
        axes[1, 0].grid(True, alpha=0.3)
        for i, (s, val) in enumerate(zip(sets, r2_means)):
            if np.isfinite(val):
                axes[1, 0].text(i, val + 0.02, f'{val:.3f}', ha='center', va='bottom')
        
        # MAE
        axes[1, 1].bar(sets, mae_means, color=['#e7f4ff', '#fff8e7', '#ffe7e7'])
        axes[1, 1].set_title('Average MAE (Regression)', fontweight='bold')
        axes[1, 1].set_ylabel('MAE')
        axes[1, 1].grid(True, alpha=0.3)
        for i, (s, val) in enumerate(zip(sets, mae_means)):
            if np.isfinite(val):
                axes[1, 1].text(i, val + 0.05, f'{val:.3f}', ha='center', va='bottom')
        
        fig.suptitle('Hyperparameter Set Comparison (A vs B vs C)', fontweight='bold', fontsize=14)
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return True
        except Exception as e:
            print(f"⚠️  Failed to save plot: {e}")
            plt.close(fig)
            return False


def plot_comparison_table(comparison_data, out_png):
    """Generate comparison table plot for hyperparameter sets."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("⚠️  matplotlib not available, skipping table plot generation")
        return False

    rows = []
    columns = [
        'Set', 'Accuracy', 'Loss', 'R²', 'MAE', 'RMSE', 'sMAPE',
        'LSTM', 'LGB', 'XGB', 'Ensemble'
    ]
    def fmt(mean_key, percent=False):
        mean = stats.get(mean_key, np.nan)
        mean = 0.0 if not np.isfinite(mean) else mean
        if percent:
            return f'{mean:.2f}%'
        return f'{mean:.4f}'

    for set_name, stats in sorted(comparison_data.items()):
        rows.append([
            set_name,
            fmt('accuracy_mean'),
            fmt('loss_mean'),
            fmt('r2_mean'),
            fmt('mae_mean'),
            fmt('rmse_mean'),
            fmt('smape_mean', percent=True),
            fmt('lstm_acc_mean'),
            fmt('lightgbm_acc_mean'),
            fmt('xgboost_acc_mean'),
            fmt('ensemble_acc_mean'),
        ])

    fig, ax = plt.subplots(figsize=(14, 1.4 + 0.6 * len(rows)), dpi=150)
    ax.axis('off')
    table = ax.table(
        cellText=rows,
        colLabels=columns,
        cellLoc='center',
        loc='center'
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)
    fig.tight_layout()
    try:
        plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return True
    except Exception as e:
        print(f"⚠️  Failed to save table plot: {e}")
        plt.close(fig)
        return False


def main():
    print("=" * 70)
    print("🔍 Hyperparameter Set Comparison Report")
    print("=" * 70)
    
    meta_by_set = load_all_meta_by_set()
    if meta_by_set.get('UNKNOWN'):
        print(f"\n⚠️  Unknown param_set metadata found: {len(meta_by_set['UNKNOWN'])} files")
        print("   These files have no param_set tag and are not counted in A/B/C.")
    
    comparison_data = {}
    for set_name in ['A', 'B', 'C']:
        metas = meta_by_set.get(set_name, [])
        if not metas:
            print(f"\n⚠️  Set {set_name}: No trained models found")
            continue
        
        stats = compute_set_statistics(metas, set_name)
        comparison_data[set_name] = stats
        param_set_name = metas[0].get('param_set_name') or PARAM_SET_NAMES.get(set_name, 'Unknown')
        print(f"\n📊 Set {set_name} - {param_set_name} ({len(metas)} rooms)")
        print(f"   Accuracy:     {stats.get('accuracy_mean', np.nan):.4f} ± {stats.get('accuracy_std', np.nan):.4f}")
        print(f"   Loss:         {stats.get('loss_mean', np.nan):.4f} ± {stats.get('loss_std', np.nan):.4f}")
        print(f"   R² Score:     {stats.get('r2_mean', np.nan):.4f} ± {stats.get('r2_std', np.nan):.4f}")
        print(f"   MAE:          {stats.get('mae_mean', np.nan):.4f} ± {stats.get('mae_std', np.nan):.4f}")
        print(f"   Ensemble Acc: {stats.get('ensemble_acc_mean', np.nan):.4f}")
    
    if not comparison_data:
        print("\n❌ No parameter sets found. Run training with --param-set A|B|C first.")
        return
    
    # Show full comparison table
    df = pd.DataFrame.from_dict(comparison_data, orient='index')
    df = df.rename(columns={
        'room_count': 'Rooms',
        'accuracy_mean': 'Accuracy Mean', 'accuracy_std': 'Accuracy Std',
        'loss_mean': 'Loss Mean', 'loss_std': 'Loss Std',
        'r2_mean': 'R² Mean', 'r2_std': 'R² Std',
        'mae_mean': 'MAE Mean', 'mae_std': 'MAE Std',
        'rmse_mean': 'RMSE Mean', 'rmse_std': 'RMSE Std',
        'smape_mean': 'sMAPE Mean', 'smape_std': 'sMAPE Std',
        'lstm_acc_mean': 'LSTM Acc Mean', 'lstm_acc_std': 'LSTM Acc Std',
        'lightgbm_acc_mean': 'LGB Acc Mean', 'lightgbm_acc_std': 'LGB Acc Std',
        'xgboost_acc_mean': 'XGB Acc Mean', 'xgboost_acc_std': 'XGB Acc Std',
        'ensemble_acc_mean': 'Ensemble Acc Mean', 'ensemble_acc_std': 'Ensemble Acc Std',
    })
    df = df[[
        'Rooms', 'Accuracy Mean', 'Accuracy Std', 'Loss Mean', 'Loss Std',
        'R² Mean', 'R² Std', 'MAE Mean', 'MAE Std', 'RMSE Mean', 'RMSE Std',
        'sMAPE Mean', 'sMAPE Std', 'LSTM Acc Mean', 'LSTM Acc Std',
        'LGB Acc Mean', 'LGB Acc Std', 'XGB Acc Mean', 'XGB Acc Std',
        'Ensemble Acc Mean', 'Ensemble Acc Std'
    ]].fillna(np.nan)
    print('\n📊 Full comparison table:')
    print(df.to_string(float_format='%.4f'))
    
    # Find best set
    best_set = max(comparison_data.items(), key=lambda x: x[1].get('accuracy_mean', -1))[0]
    print(f"\n🏆 Best Set (by Accuracy): Set {best_set}")
    
    # Write CSV
    csv_path = METRICS_DIR / 'hyperparam_comparison.csv'
    write_comparison_csv(comparison_data, csv_path)
    print(f"\n📄 Saved comparison CSV: {csv_path}")
    
    # NOTE: hyperparam_comparison.png and hyperparam_comparison_table.png are
    # intentionally no longer generated here (superseded by
    # hyperparam_comparison_reconciled.png, which reads the CSV written above
    # and reconciles Ensemble Acc against the saved_meta/ live source).

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
