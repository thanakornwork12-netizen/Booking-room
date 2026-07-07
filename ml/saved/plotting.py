"""
Plotting and metrics-summary helpers for saved forecast training metadata.

This module is intentionally independent from Django/model training so plots can
be regenerated without importing the full forecasting engine.
"""
import os
from pathlib import Path

import numpy as np

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


def _plot_real_model_report(model_name, loss_curves, validation_values, out_png):
    train_loss, val_loss = _pick_train_val_curves(loss_curves)

    metric_labels = ['Accuracy', 'F1', 'Recall', 'Precision']
    metric_means = []
    metric_stds = []
    for label in metric_labels:
        vals = np.asarray(validation_values.get(label, []), dtype=float)
        vals = vals[np.isfinite(vals)]
        metric_means.append(float(np.nanmean(vals)) if len(vals) else np.nan)
        metric_stds.append(float(np.nanstd(vals)) if len(vals) else 0.0)

    has_loss = train_loss is not None or val_loss is not None
    has_metrics = any(np.isfinite(v) for v in metric_means)
    if not has_loss and not has_metrics:
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
        fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), dpi=300)

        if has_loss:
            if train_loss is not None:
                epochs = range(1, len(train_loss) + 1)
                axes[0].plot(epochs, _smooth_curve(train_loss), color='#2b8cbe', linewidth=2.3, label='Train loss')
            if val_loss is not None:
                epochs = range(1, len(val_loss) + 1)
                axes[0].plot(epochs, _smooth_curve(val_loss), color='#f03b20', linewidth=2.3, label='Validation loss')
            axes[0].set_title(f'{model_name} Real Loss History', fontweight='bold')
            axes[0].set_xlabel('Iteration / Epoch')
            axes[0].set_ylabel('Loss / Error')
            axes[0].legend(loc='best', frameon=True)
            axes[0].grid(True, alpha=0.55)
        else:
            axes[0].axis('off')
            axes[0].text(0.5, 0.5, 'No real per-iteration loss history', ha='center', va='center', fontsize=12)

        if has_metrics:
            x = np.arange(len(metric_labels))
            colors = ['#2b8cbe', '#41ab5d', '#756bb1', '#fdae6b']
            axes[1].bar(x, metric_means, yerr=metric_stds, color=colors, width=0.58, capsize=4)
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(metric_labels)
            axes[1].set_ylim(0.0, 1.05)
            axes[1].set_ylabel('Score (0-1)')
            axes[1].set_title(f'{model_name} Real Validation Metrics', fontweight='bold')
            axes[1].grid(True, axis='y', alpha=0.55)
            for i, val in enumerate(metric_means):
                if np.isfinite(val):
                    axes[1].text(i, min(val + 0.035, 1.02), f'{val:.3f}', ha='center', va='bottom', fontsize=9)
        else:
            axes[1].axis('off')
            axes[1].text(0.5, 0.5, 'No real validation metrics', ha='center', va='center', fontsize=12)

        fig.suptitle(f'{model_name}: Real Recorded Values Only', fontweight='bold', fontsize=14)
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
        'lstm_training_curves.png',
        'lightgbm_training_curves.png',
        'xgboost_training_curves.png',
        '*_accuracy_curve.png',
        '*_loss_curve.png',
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

    lstm_histories = [
        meta.get('lstm_history') for _, meta in room_metas
        if isinstance(meta.get('lstm_history'), dict)
    ]
    lgb_histories = [
        meta.get('lgb_history') for _, meta in room_metas
        if isinstance(meta.get('lgb_history'), dict)
    ]
    xgb_histories = [
        meta.get('xgb_history') for _, meta in room_metas
        if isinstance(meta.get('xgb_history'), dict)
    ]

    lstm_loss_curves = {
        'Train Loss': _mean_equal_length([h.get('loss') for h in lstm_histories]),
        'Val Loss': _mean_equal_length([h.get('val_loss') for h in lstm_histories]),
    }
    lstm_accuracy_curves = {
        'Train Accuracy': _mean_equal_length([h.get('accuracy') for h in lstm_histories]),
        'Val Accuracy': _mean_equal_length([h.get('val_accuracy') for h in lstm_histories]),
    }

    lgb_loss_curves = _collect_booster_curves(lgb_histories)
    lgb_loss_curves = {
        label.replace('valid_0', 'Val').replace('validation_0', 'Val').replace('valid_loss', 'Val Loss').replace('train_loss', 'Train Loss'): vals
        for label, vals in lgb_loss_curves.items()
    }

    xgb_loss_curves = _collect_booster_curves(xgb_histories)
    xgb_loss_curves = {
        label.replace('valid_0', 'Val').replace('validation_0', 'Val').replace('valid_loss', 'Val Loss').replace('train_loss', 'Train Loss'): vals
        for label, vals in xgb_loss_curves.items()
    }

    outputs = [
        _plot_real_model_report(
            'Ensemble',
            {},
            _metric_values_from_meta(room_metas, 'ensemble'),
            os.path.join(metrics_dir, 'ensemble_training_curves.png'),
        ),
        _plot_real_model_report(
            'LSTM',
            lstm_loss_curves,
            _metric_values_from_meta(room_metas, 'lstm'),
            os.path.join(metrics_dir, 'lstm_training_curves.png'),
        ),
        _plot_real_model_report(
            'LightGBM',
            lgb_loss_curves,
            _metric_values_from_meta(room_metas, 'lightgbm'),
            os.path.join(metrics_dir, 'lightgbm_training_curves.png'),
        ),
        _plot_real_model_report(
            'XGBoost',
            xgb_loss_curves,
            _metric_values_from_meta(room_metas, 'xgboost'),
            os.path.join(metrics_dir, 'xgboost_training_curves.png'),
        ),
    ]
    return sum(bool(x) for x in outputs)


def plot_model_summary(model_summary: dict, out_png: str):
    if not model_summary:
        return False
    labels = []
    r2s = []
    accs = []
    f1s = []
    for name in ['ensemble', 'lightgbm', 'xgboost', 'lstm']:
        summary = model_summary.get(name)
        if not summary:
            continue
        labels.append(name.title())
        r2s.append(float(summary.get('r2', np.nan)))
        accs.append(float(summary.get('accuracy', np.nan)))
        f1s.append(float(summary.get('f1', np.nan)))

    if not labels:
        return False

    x = np.arange(len(labels))
    width = 0.25

    with plt.rc_context({'figure.facecolor': 'white', 'font.size': 12}):
        fig, ax = plt.subplots(figsize=(8, 4), dpi=300)
        ax.bar(x - width, r2s, width, label='R2', color='#2b8cbe')
        ax.bar(x, accs, width, label='Accuracy', color='#7bccc4')
        ax.bar(x + width, f1s, width, label='F1', color='#bae4bc')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel('Score')
        ax.set_title('Model Summary (avg across rooms)')
        ax.legend(frameon=False)
        plt.tight_layout()
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False
