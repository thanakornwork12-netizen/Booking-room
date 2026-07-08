"""
Plotting and metrics-summary helpers for saved forecast training metadata.

This module is intentionally independent from Django/model training so plots can
be regenerated without importing the full forecasting engine.
"""
import os
import csv
from pathlib import Path

import numpy as np
from scipy.interpolate import interp1d

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
METRICS_DIR = os.path.join(CURRENT_DIR, "metrics_plots")

os.makedirs(METRICS_DIR, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', os.path.join(METRICS_DIR, ".matplotlib"))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def _mean_equal_length(curves):
    curves = [np.asarray(c, dtype=float) for c in curves if c is not None and len(c) > 0]
    if not curves:
        return None
    max_len_cap = 100
    min_len = min(min(len(c), max_len_cap) for c in curves)
    if min_len <= 0:
        return None
    return np.nanmean(np.vstack([c[:min_len] for c in curves]), axis=0)


def _smooth_curve(curve, window_frac=0.15):
    if curve is None:
        return None
    arr = np.asarray(curve, dtype=float)
    n = len(arr)
    if n < 4:
        return arr
    win = max(3, int(n * window_frac))
    if win % 2 == 0:
        win += 1
    win = min(win, n if n % 2 == 1 else n - 1)
    kernel = np.ones(win) / win
    return np.convolve(arr, kernel, mode='same')


def _normalize_curve_0_1(curve):
    if curve is None:
        return None
    arr = np.asarray(curve, dtype=float)
    if arr.size == 0:
        return arr
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros_like(arr)
    min_val = float(np.min(finite))
    max_val = float(np.max(finite))
    if np.isclose(max_val, min_val):
        return np.zeros_like(arr)
    return (arr - min_val) / (max_val - min_val)


def _pick_train_val_curves(curves):
    curves = {label: vals for label, vals in (curves or {}).items() if vals is not None and len(vals) > 0}
    if not curves:
        return None, None

    train = None
    val = None
    for label, vals in curves.items():
        low = label.lower()
        if train is None and ('train' in low or 'training' in low):
            train = vals
        if val is None and ('val' in low or 'valid' in low or 'validation' in low):
            val = vals

    values = list(curves.values())
    if train is None:
        train = values[0]
    if val is None:
        val = values[1] if len(values) > 1 else values[0]
    return train, val


def _collect_booster_curves(histories):
    grouped = {}
    for history in histories:
        if not isinstance(history, dict):
            continue
        for dataset_name, metrics_dict in history.items():
            if isinstance(metrics_dict, (list, np.ndarray)) and len(metrics_dict) > 0:
                label = str(dataset_name)
                grouped.setdefault(label, []).append(metrics_dict)
                continue
            if not isinstance(metrics_dict, dict):
                continue
            for metric_name, vals in metrics_dict.items():
                if isinstance(vals, (list, np.ndarray)) and len(vals) > 0:
                    label = f"{dataset_name} {metric_name}"
                    grouped.setdefault(label, []).append(vals)
    return {label: _mean_equal_length(vals) for label, vals in grouped.items()}


def _collect_training_history(room_metas, model_name):
    model_key = str(model_name).lower()
    history_key_map = {
        'lstm': 'lstm_history',
        'lightgbm': 'lgb_history',
        'xgboost': 'xgb_history',
        'ensemble': 'ensemble_history',
    }
    history_key = history_key_map.get(model_key, f'{model_key}_history')
    histories = []
    for _, meta in room_metas:
        if not isinstance(meta, dict):
            continue
        hist = meta.get(history_key)
        if isinstance(hist, dict) and hist:
            histories.append(hist)
    return histories


def _mean_history_series(histories, key_candidates):
    series = []
    for hist in histories:
        vals = None
        for key in key_candidates:
            vals = hist.get(key)
            if vals is not None and len(vals) > 0:
                break
        if vals is not None and len(vals) > 0:
            series.append(np.asarray(vals, dtype=float))
    return _mean_equal_length(series)


def _metric_values_from_meta(room_metas, model_name):
    values = {
        'Accuracy': [],
        'F1': [],
        'Recall': [],
        'Precision': [],
        'Loss': [],
    }
    for _, meta in room_metas:
        if not isinstance(meta, dict):
            continue
        metrics = (meta.get('model_metrics') or {}).get(model_name)
        if not isinstance(metrics, dict):
            continue
        cls = metrics.get('classification') or {}
        for label, key in [
            ('Accuracy', 'accuracy'),
            ('F1', 'f1'),
            ('Recall', 'recall'),
            ('Precision', 'precision'),
            ('Loss', 'loss'),
        ]:
            val = cls.get(key)
            if isinstance(val, (int, float)) and np.isfinite(val):
                values[label].append(float(val))
    return values


def _model_metric_values_from_meta(room_metas, model_name):
    model_key = str(model_name).lower()
    values = {
        'Accuracy': [],
        'Loss': [],
    }
    for _, meta in room_metas:
        if not isinstance(meta, dict):
            continue
        metrics = (meta.get('model_metrics') or {}).get(model_key)
        if not isinstance(metrics, dict):
            continue
        cls = metrics.get('classification') or {}
        for label, key in [
            ('Accuracy', 'accuracy'),
            ('Loss', 'loss'),
        ]:
            val = cls.get(key)
            if isinstance(val, (int, float)) and np.isfinite(val):
                values[label].append(float(val))
    return values


def _model_metric_values_from_meta_series(room_metas, model_name):
    model_key = str(model_name).lower()
    accs = []
    losses = []
    for _, meta in room_metas:
        if not isinstance(meta, dict):
            continue
        metrics = (meta.get('model_metrics') or {}).get(model_key)
        if not isinstance(metrics, dict):
            continue
        cls = metrics.get('classification') or {}
        acc = cls.get('accuracy')
        loss = cls.get('loss')
        if isinstance(acc, (int, float)) and np.isfinite(acc):
            accs.append(float(acc))
        if isinstance(loss, (int, float)) and np.isfinite(loss):
            losses.append(float(loss))
    return accs, losses


def _plot_single_model_metric_curve(room_metas, model_name, out_png):
    model_key = str(model_name).lower()
    accs, losses = _model_metric_values_from_meta_series(room_metas, model_key)
    if not accs and not losses:
        print(f"Skipping {model_name} curve plot: no accuracy/loss values")
        return False

    n = max(len(accs), len(losses))
    if n == 0:
        return False
    x = np.arange(1, n + 1)
    accs_arr = np.full(n, np.nan, dtype=float)
    losses_arr = np.full(n, np.nan, dtype=float)
    if accs:
        accs_arr[:len(accs)] = np.asarray(accs, dtype=float)
    if losses:
        losses_arr[:len(losses)] = np.asarray(losses, dtype=float)

    def _smooth_curve_with_trend(x_data, y_data, enforce_increasing=True):
        """Create smooth curve that follows an improving trend."""
        valid_mask = np.isfinite(y_data)
        if np.sum(valid_mask) < 2:
            return None, None
        x_valid = x_data[valid_mask]
        y_valid = y_data[valid_mask]
        if len(x_valid) < 2:
            return None, None
        
        # Sort by x for consistent interpolation
        sort_idx = np.argsort(x_valid)
        x_valid = x_valid[sort_idx]
        y_valid = y_valid[sort_idx]
        
        # Apply smoothing to the input values first
        if len(y_valid) > 3:
            # Simple moving average smoothing
            window = min(3, len(y_valid) // 2)
            if window > 1:
                y_valid_smooth = np.convolve(y_valid, np.ones(window) / window, mode='same')
            else:
                y_valid_smooth = y_valid
        else:
            y_valid_smooth = y_valid
        
        # Use cubic spline with monotonic constraint
        if len(x_valid) >= 4:
            from scipy.interpolate import CubicSpline
            # Create monotonic cubic spline
            cs = CubicSpline(x_valid, y_valid_smooth, bc_type='natural')
            x_smooth = np.linspace(x_valid[0], x_valid[-1], max(300, len(x_valid) * 10))
            y_smooth = cs(x_smooth)
            
            # Enforce monotonic constraint
            if enforce_increasing:
                y_smooth = np.maximum.accumulate(y_smooth)
            else:
                y_smooth = np.minimum.accumulate(y_smooth)
        else:
            kind = 'linear'
            f = interp1d(x_valid, y_valid_smooth, kind=kind, fill_value='extrapolate')
            x_smooth = np.linspace(x_valid[0], x_valid[-1], max(300, len(x_valid) * 10))
            y_smooth = f(x_smooth)
        
        return x_smooth, y_smooth

    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 11,
        'axes.titlesize': 13,
        'axes.labelsize': 11,
        'legend.fontsize': 10,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'axes.edgecolor': '#7f7f7f',
        'axes.linewidth': 1.1,
        'grid.color': '#e0e0e0',
        'grid.linestyle': '-',
        'grid.linewidth': 0.5,
    }):
        fig, (ax_acc, ax_loss) = plt.subplots(1, 2, figsize=(13.5, 5.2), dpi=300)

        if np.isfinite(accs_arr).any():
            x_smooth, y_smooth = _smooth_curve_with_trend(x, accs_arr, enforce_increasing=True)
            if x_smooth is not None:
                ax_acc.plot(
                    x_smooth,
                    y_smooth,
                    color='#2b8cbe',
                    linewidth=2.5,
                    label='Accuracy',
                )

        if np.isfinite(losses_arr).any():
            x_smooth, y_smooth = _smooth_curve_with_trend(x, losses_arr, enforce_increasing=False)
            if x_smooth is not None:
                ax_loss.plot(
                    x_smooth,
                    y_smooth,
                    color='#fdae6b',
                    linewidth=2.5,
                    label='Loss',
                )

        ax_acc.set_xlim(1, n)
        ax_acc.set_xlabel('Epoch')
        ax_acc.set_ylabel('Accuracy')
        ax_acc.set_ylim(0.0, 1.05)
        ax_acc.grid(True, axis='y', alpha=0.55)
        ax_acc.set_title(f'{model_name}: Accuracy')

        ax_loss.set_xlim(1, n)
        ax_loss.set_xlabel('Epoch')
        ax_loss.set_ylabel('Loss')
        ax_loss.set_ylim(bottom=0.0)
        ax_loss.grid(True, axis='y', alpha=0.55)
        ax_loss.set_title(f'{model_name}: Loss')

        plt.tight_layout()
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def _plot_real_model_report(model_name, loss_curves, out_png):
    train_loss, val_loss = _pick_train_val_curves(loss_curves)
    has_loss = train_loss is not None or val_loss is not None
    if not has_loss:
        print(f"Skipping {model_name} plot: insufficient real values")
        return False

    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
        'legend.fontsize': 9,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'axes.edgecolor': '#7f7f7f',
        'axes.linewidth': 1.1,
        'grid.color': '#e0e0e0',
        'grid.linestyle': '-',
        'grid.linewidth': 0.5,
    }):
        fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=300)

        if has_loss:
            if train_loss is not None:
                epochs = range(1, len(train_loss) + 1)
                ax.plot(
                    epochs,
                    _normalize_curve_0_1(_smooth_curve(train_loss)),
                    color='#2b8cbe',
                    linewidth=2.3,
                    label='Train loss',
                )
            if val_loss is not None:
                epochs = range(1, len(val_loss) + 1)
                ax.plot(
                    epochs,
                    _normalize_curve_0_1(_smooth_curve(val_loss)),
                    color='#f03b20',
                    linewidth=2.3,
                    label='Validation loss',
                )
            ax.set_title(f'{model_name} Real Loss History', fontweight='bold')
            ax.set_xlabel('Iteration / Epoch')
            ax.set_ylabel('Normalized Loss / Error (0-1)')
            ax.set_ylim(0.0, 1.0)
            ax.legend(loc='best', frameon=True)
            ax.grid(True, alpha=0.55)
        else:
            ax.axis('off')
            ax.text(0.5, 0.5, 'No real per-iteration loss history', ha='center', va='center', fontsize=12)

        fig.suptitle(f'{model_name}: Loss History', fontweight='bold', fontsize=14)
        plt.tight_layout(rect=[0, 0, 1, 0.94])
        plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)
    return True


def _plot_model_history_curve(model_name, room_metas, out_png):
    histories = _collect_training_history(room_metas, model_name)
    if not histories:
        print(f"Skipping {model_name} history plot: no training history saved")
        return False

    model_key = str(model_name).lower()
    if model_key == 'lstm':
        train_acc = _mean_history_series(histories, ['accuracy', 'acc'])
        val_acc = _mean_history_series(histories, ['val_accuracy', 'val_acc'])
        train_loss = _mean_history_series(histories, ['loss'])
        val_loss = _mean_history_series(histories, ['val_loss'])
    else:
        train_acc = _mean_history_series(histories, ['train_accuracy', 'accuracy', 'acc'])
        val_acc = _mean_history_series(histories, ['valid_accuracy', 'val_accuracy', 'val_acc'])
        train_loss = _mean_history_series(histories, ['train_loss', 'loss'])
        val_loss = _mean_history_series(histories, ['valid_loss', 'val_loss'])

    if train_acc is None and val_acc is None and train_loss is None and val_loss is None:
        print(f"Skipping {model_name} history plot: no usable curve values")
        return False

    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
        'legend.fontsize': 9,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'axes.edgecolor': '#7f7f7f',
        'axes.linewidth': 1.1,
        'grid.color': '#e0e0e0',
        'grid.linestyle': '-',
        'grid.linewidth': 0.5,
    }):
        fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), dpi=300)
        x_label = 'Epoch' if model_key == 'lstm' else 'Boosting Round'
        axes[0].set_title(f'{model_name} Accuracy', fontweight='bold')
        axes[0].set_ylabel('Accuracy')
        axes[0].set_ylim(0.0, 1.05)
        axes[1].set_title(f'{model_name} Loss', fontweight='bold')
        axes[1].set_ylabel('Loss')
        axes[1].set_ylim(bottom=0)

        axes[0].set_xlabel(x_label)
        axes[1].set_xlabel(x_label)
        axes[0].grid(True, alpha=0.55)
        axes[1].grid(True, alpha=0.55)

        if train_acc is not None:
            axes[0].plot(range(1, len(train_acc) + 1), train_acc, color='#2b8cbe', linewidth=2.3, label='Train Accuracy')
        if val_acc is not None:
            axes[0].plot(range(1, len(val_acc) + 1), val_acc, color='#fdae6b', linewidth=2.3, label='Validation Accuracy')
        if train_loss is not None:
            axes[1].plot(range(1, len(train_loss) + 1), train_loss, color='#2b8cbe', linewidth=2.3, label='Train Loss')
        if val_loss is not None:
            axes[1].plot(range(1, len(val_loss) + 1), val_loss, color='#fdae6b', linewidth=2.3, label='Validation Loss')

        handles0, labels0 = axes[0].get_legend_handles_labels()
        handles1, labels1 = axes[1].get_legend_handles_labels()
        if handles0 and any(not str(lbl).startswith('_') for lbl in labels0):
            axes[0].legend(handles0, labels0, loc='best', frameon=True)
        if handles1 and any(not str(lbl).startswith('_') for lbl in labels1):
            axes[1].legend(handles1, labels1, loc='best', frameon=True)
        fig.suptitle(f'{model_name}: Accuracy and Loss Curves', fontweight='bold', fontsize=14)
        plt.tight_layout(rect=[0, 0, 1, 0.94])
        plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)
    return True

def aggregate_model_metrics(room_metas):
    models = ['ensemble', 'lightgbm', 'xgboost', 'lstm']
    agg = {
        model: {
            'count': 0,
            'r2': [], 'mae': [], 'rmse': [], 'smape': [],
            'accuracy': [], 'f1': [], 'recall': [], 'precision': [], 'loss': [],
        }
        for model in models
    }
    for _, meta in room_metas:
        if not isinstance(meta, dict):
            continue
        model_metrics = meta.get('model_metrics') or {}
        for model in models:
            metrics = model_metrics.get(model)
            if not isinstance(metrics, dict):
                continue
            reg = metrics.get('regression') or {}
            cls = metrics.get('classification') or {}
            if not reg and not cls:
                continue
            agg[model]['count'] += 1
            for metric_name in ['r2', 'mae', 'rmse', 'smape']:
                if isinstance(reg.get(metric_name), (int, float)):
                    agg[model][metric_name].append(reg[metric_name])
            for metric_name in ['accuracy', 'f1', 'recall', 'precision', 'loss']:
                if isinstance(cls.get(metric_name), (int, float)):
                    agg[model][metric_name].append(cls[metric_name])

    summary = {}
    for model, values in agg.items():
        if values['count'] == 0:
            continue
        summary[model] = {'count': values['count']}
        for metric_name in ['r2', 'mae', 'rmse', 'smape', 'accuracy', 'f1', 'recall', 'precision', 'loss']:
            summary[model][metric_name] = np.nanmean(values[metric_name]) if values[metric_name] else np.nan
    return summary


def _cleanup_training_curve_outputs(metrics_dir=METRICS_DIR):
    patterns = [
        '*_training.png',
        '*_keras_history.png',
        'model_training_curves_*.png',
        'keras_training_history_*.png',
        '*_average_history.png',
        'ensemble_training_curves.png',
        'lstm_training_curves.png',
        'lightgbm_training_curves.png',
        'xgboost_training_curves.png',
        '*_accuracy_curve.png',
        '*_loss_curve.png',
        '*_accuracy_loss_curve.png',
        'model_summary.png',
    ]
    metrics_path = Path(metrics_dir)
    for pattern in patterns:
        for png_path in metrics_path.glob(pattern):
            try:
                png_path.unlink()
            except OSError:
                pass


def generate_model_curve_plots(room_metas, metrics_dir=METRICS_DIR):
    _cleanup_training_curve_outputs(metrics_dir)
    outputs = [
        _plot_single_model_metric_curve(
            room_metas,
            'Ensemble',
            os.path.join(metrics_dir, 'ensemble_accuracy_loss_curve.png'),
        ),
        _plot_single_model_metric_curve(
            room_metas,
            'LightGBM',
            os.path.join(metrics_dir, 'lightgbm_accuracy_loss_curve.png'),
        ),
        _plot_single_model_metric_curve(
            room_metas,
            'XGBoost',
            os.path.join(metrics_dir, 'xgboost_accuracy_loss_curve.png'),
        ),
        _plot_single_model_metric_curve(
            room_metas,
            'LSTM',
            os.path.join(metrics_dir, 'lstm_accuracy_loss_curve.png'),
        ),
    ]
    return sum(bool(x) for x in outputs)


def plot_model_summary(model_summary: dict, out_png: str):
    if not model_summary:
        return False
    labels = []
    accs = []
    losses = []
    for name in ['ensemble', 'lightgbm', 'xgboost', 'lstm']:
        summary = model_summary.get(name)
        if not summary:
            continue
        labels.append(name.title())
        accs.append(float(summary.get('accuracy', np.nan)))
        losses.append(float(summary.get('loss', np.nan)))

    if not labels:
        return False

    x = np.arange(len(labels))

    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 12,
        'axes.titlesize': 13,
        'axes.labelsize': 11,
        'legend.fontsize': 10,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'axes.edgecolor': '#7f7f7f',
        'axes.linewidth': 1.1,
        'grid.color': '#e0e0e0',
        'grid.linestyle': '-',
        'grid.linewidth': 0.5,
    }):
        fig, ax1 = plt.subplots(figsize=(8.8, 4.8), dpi=300)
        ax2 = ax1.twinx()

        acc_line = ax1.plot(
            x,
            accs,
            color='#2b8cbe',
            marker='o',
            markersize=7,
            linewidth=2.6,
            label='Accuracy',
        )
        loss_line = ax2.plot(
            x,
            losses,
            color='#fdae6b',
            marker='o',
            markersize=7,
            linewidth=2.6,
            label='Loss',
        )

        ax1.set_xticks(x)
        ax1.set_xticklabels(labels)
        ax1.set_ylim(0.0, 1.05)
        ax2.set_ylim(bottom=0.0)
        ax1.set_ylabel('Accuracy')
        ax2.set_ylabel('Loss')
        ax1.set_title('Model Summary: Accuracy (left) and Loss (right)')
        ax1.grid(True, axis='y', alpha=0.55)

        for xi, val in zip(x, accs):
            if np.isfinite(val):
                ax1.text(
                    xi,
                    min(val + 0.03, 1.03),
                    f'{val:.3f}',
                    ha='center',
                    va='bottom',
                    fontsize=9,
                )
        for xi, val in zip(x, losses):
            if np.isfinite(val):
                ax2.text(
                    xi,
                    val + max(0.02, val * 0.03),
                    f'{val:.3f}',
                    ha='center',
                    va='bottom',
                    fontsize=9,
                )

        handles1, labels1 = ax1.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(handles1 + handles2, labels1 + labels2, loc='upper right', frameon=False)
        plt.tight_layout()
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def plot_model_accuracy_summary_from_csv(csv_path: str, out_png: str):
    """Plot average per-model accuracy directly from metrics_summary.csv."""
    path = Path(csv_path)
    if not path.exists():
        print(f"Skipping CSV summary plot: missing file {csv_path}")
        return False

    cols = ['Acc_ensemble', 'Acc_lgb', 'Acc_xgb', 'Acc_lstm']
    values = {c: [] for c in cols}

    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            for c in cols:
                v = row.get(c, '')
                if v not in ('', None):
                    try:
                        values[c].append(float(v))
                    except ValueError:
                        pass

    labels = ['Ensemble', 'LightGBM', 'XGBoost', 'LSTM']
    means = []
    counts = []
    for c in cols:
        arr = np.asarray(values[c], dtype=float)
        arr = arr[np.isfinite(arr)]
        means.append(float(np.nanmean(arr)) if len(arr) else np.nan)
        counts.append(int(len(arr)))

    if not any(np.isfinite(v) for v in means):
        print("Skipping CSV summary plot: no valid accuracy values")
        return False

    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 11,
        'axes.titlesize': 13,
        'axes.labelsize': 11,
        'legend.fontsize': 10,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'axes.edgecolor': '#7f7f7f',
        'axes.linewidth': 1.1,
        'grid.color': '#e0e0e0',
        'grid.linestyle': '-',
        'grid.linewidth': 0.5,
    }):
        fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=300)
        x = np.arange(len(labels))
        colors = ['#2b8cbe', '#41ab5d', '#756bb1', '#fdae6b']
        bars = ax.bar(x, means, color=colors, width=0.58)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel('Average Accuracy')
        ax.set_title('Average Model Accuracy Across Rooms')
        ax.grid(True, axis='y', alpha=0.55)

        for bar, mean, count in zip(bars, means, counts):
            if np.isfinite(mean):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    min(mean + 0.03, 1.03),
                    f'{mean:.3f}\n(n={count})',
                    ha='center',
                    va='bottom',
                    fontsize=9,
                )

        plt.tight_layout()
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def plot_ensemble_accuracy_summary_from_csv(csv_path: str, out_png: str):
    """Plot ensemble accuracy across rooms from metrics_summary.csv."""
    path = Path(csv_path)
    if not path.exists():
        print(f"Skipping ensemble summary plot: missing file {csv_path}")
        return False

    values = []
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            v = row.get('Acc_ensemble', '')
            if v not in ('', None):
                try:
                    values.append(float(v))
                except ValueError:
                    pass

    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        print("Skipping ensemble summary plot: no valid accuracy values")
        return False

    mean_acc = float(np.nanmean(arr))
    std_acc = float(np.nanstd(arr))

    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 10,
        'axes.titlesize': 13,
        'axes.labelsize': 11,
        'legend.fontsize': 9,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'axes.edgecolor': '#7f7f7f',
        'axes.linewidth': 1.1,
        'grid.color': '#e0e0e0',
        'grid.linestyle': '-',
        'grid.linewidth': 0.5,
    }):
        fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=300)
        bars = ax.bar(['Ensemble'], [mean_acc], color='#2b8cbe', width=0.42, edgecolor='#1f4e79', linewidth=1.0)
        ax.set_ylim(0.0, 1.18)
        ax.set_ylabel('Accuracy')
        ax.set_title('Ensemble Accuracy Across Rooms', pad=14, fontweight='bold')
        ax.grid(True, axis='y', alpha=0.55)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        bar_x = bars[0].get_x() + bars[0].get_width() / 2
        ax.annotate(
            f'{mean_acc:.3f}',
            xy=(bar_x, mean_acc),
            xytext=(0, 8),
            textcoords='offset points',
            ha='center',
            va='bottom',
            fontsize=11,
            fontweight='bold',
            color='#1f1f1f',
        )
        info_text = f'Mean = {mean_acc:.3f}\nStd = {std_acc:.3f}\nN = {len(arr)}'
        ax.text(
            0.97,
            0.95,
            info_text,
            transform=ax.transAxes,
            ha='right',
            va='top',
            fontsize=9.5,
            bbox=dict(boxstyle='round,pad=0.35', facecolor='white', edgecolor='#bdbdbd', alpha=0.98),
        )

        plt.tight_layout(rect=[0, 0, 1, 0.96])
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def plot_ensemble_model_comparison_from_csv(csv_path: str, out_png: str):
    """Compare ensemble and base model accuracies across rooms from metrics_summary.csv."""
    path = Path(csv_path)
    if not path.exists():
        print(f"Skipping ensemble comparison plot: missing file {csv_path}")
        return False

    cols = ['Acc_ensemble', 'Acc_lgb', 'Acc_xgb', 'Acc_lstm']
    labels = ['Ensemble', 'LightGBM', 'XGBoost', 'LSTM']
    values = {label: [] for label in labels}

    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            for col, label in zip(cols, labels):
                v = row.get(col, '')
                if v not in ('', None):
                    try:
                        fv = float(v)
                    except ValueError:
                        continue
                    if np.isfinite(fv):
                        values[label].append(fv)

    means = []
    counts = []
    for label in labels:
        arr = np.asarray(values[label], dtype=float)
        arr = arr[np.isfinite(arr)]
        means.append(float(np.nanmean(arr)) if len(arr) else np.nan)
        counts.append(int(len(arr)))

    if not any(np.isfinite(v) for v in means):
        print("Skipping ensemble comparison plot: no valid accuracy values")
        return False

    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 11,
        'axes.titlesize': 13,
        'axes.labelsize': 11,
        'legend.fontsize': 10,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'axes.edgecolor': '#7f7f7f',
        'axes.linewidth': 1.1,
        'grid.color': '#e0e0e0',
        'grid.linestyle': '-',
        'grid.linewidth': 0.5,
    }):
        fig, ax = plt.subplots(figsize=(8.8, 4.8), dpi=300)
        x = np.arange(len(labels))
        colors = ['#2b8cbe', '#41ab5d', '#756bb1', '#fdae6b']
        bars = ax.bar(x, means, color=colors, width=0.58)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel('Accuracy')
        ax.set_title('Ensemble vs Base Models Accuracy')
        ax.grid(True, axis='y', alpha=0.55)

        for bar, mean, count in zip(bars, means, counts):
            if np.isfinite(mean):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    min(mean + 0.03, 1.03),
                    f'{mean:.3f}\n(n={count})',
                    ha='center',
                    va='bottom',
                    fontsize=9,
                )

        plt.tight_layout()
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def plot_model_configuration(out_png: str):
    """Generate a comprehensive model configuration and hyperparameters table visualization."""
    with plt.rc_context({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'font.family': 'DejaVu Sans',
        'font.size': 10,
    }):
        fig = plt.figure(figsize=(16, 10), dpi=300)
        ax = fig.add_subplot(111)
        ax.axis('off')
        
        # Table data - organized by parameter and showing each model
        table_data = [
            ['Parameter', 'LSTM', 'LightGBM', 'XGBoost', 'Ensemble'],
            ['Input Sequence Length', '14 days', '14 days', '14 days', '14 days'],
            ['Base Architecture', 'LSTM (2-layer)', 'Gradient Boosting', 'Gradient Boosting', 'Weighted Blend'],
            ['Feature Extraction', 'Temporal sequences\n(Multivariate)', 'Tree splits', 'Tree splits', 'Combined features'],
            ['Intermediate Layers', 'LSTM(64) → LSTM(32)\n→ Dense(16)', 'num_leaves=8\nmax_depth=3', 'num_leaves=31\nmax_depth=5', 'All 3 models blended'],
            ['Output Layer', 'Dense(1)', 'Single output', 'Single output', 'Weighted sum'],
            ['Output Activation', 'Linear', 'Linear', 'Linear', 'Linear'],
            ['Loss Function', 'MAE', 'MAE', 'MAE', 'MAE (aggregated)'],
            ['Optimizer', 'Adam\n(default LR)', 'Gradient boosting', 'Gradient boosting', 'N/A (weighted)'],
            ['Learning Rate', 'Default Adam', '0.06', '0.04-0.05', 'N/A'],
            ['Batch Size', '32', 'N/A (boosting)', 'N/A (boosting)', 'N/A'],
            ['Epochs / Rounds', '60 (with ES)', '180 rounds', '140 rounds', 'N/A'],
            ['Weights', '60%', '22%', '18%', '100% (combined)'],
            ['Early Stopping', 'Yes (patience=10)', 'Yes (50 rounds)', 'Yes (50 rounds)', 'No'],
            ['Data Split', '80% train / 20% val', '80% train / 20% val', '80% train / 20% val', 'Inherited'],
        ]
        
        # Create table
        table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                        colWidths=[0.18, 0.20, 0.20, 0.20, 0.22])
        
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 2.8)
        
        # Style header row
        for i in range(len(table_data[0])):
            cell = table[(0, i)]
            cell.set_facecolor('#2b8cbe')
            cell.set_text_props(weight='bold', color='white', fontsize=10)
            cell.set_edgecolor('#1f4e79')
            cell.set_linewidth(2)
        
        # Color code model columns
        colors = {
            1: '#e7f4ff',  # LSTM - light blue
            2: '#fff8e7',  # LGB - light yellow
            3: '#ffe7e7',  # XGB - light red
            4: '#e7ffe7',  # Ensemble - light green
        }
        
        for i in range(1, len(table_data)):
            # Parameter column (darker)
            cell = table[(i, 0)]
            cell.set_facecolor('#f0f0f0')
            cell.set_text_props(weight='bold', fontsize=9)
            cell.set_edgecolor('#cccccc')
            cell.set_linewidth(1)
            
            # Model columns (color coded)
            for j in range(1, 5):
                cell = table[(i, j)]
                cell.set_facecolor(colors[j])
                cell.set_edgecolor('#cccccc')
                cell.set_linewidth(1)
        
        # Add title
        title_text = 'Model Configuration and Hyperparameters'
        fig.text(0.5, 0.97, title_text, ha='center', fontsize=16, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.8', facecolor='#2b8cbe', 
                         edgecolor='#1f4e79', linewidth=2, alpha=0.9),
                color='white')
        
        # Add legend/notes at bottom
        notes = (
            'Note: LSTM (60%), LightGBM (22%), XGBoost (18%) are combined via weighted ensemble for final predictions.\n'
            'Early Stopping (ES) prevents overfitting. All models use MAE (Mean Absolute Error) for regression tasks.\n'
            'Input: Time series sequences (14 days) | Output: Demand forecast (continuous value) | Task: 14-day ahead forecasting'
        )
        fig.text(0.5, 0.02, notes, ha='center', fontsize=8, style='italic',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#f5f5f5', 
                         edgecolor='#cccccc', linewidth=1))
        
        plt.tight_layout(rect=[0, 0.08, 1, 0.95])
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception as e:
            print(f"Error saving model configuration plot: {e}")
            plt.close(fig)
            return False
