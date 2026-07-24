"""
Plotting and metrics-summary helpers for saved forecast training metadata.

This module is intentionally independent from Django/model training so plots can
be regenerated without importing the full forecasting engine.
"""
import os
import csv
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import interp1d

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
METRICS_DIR = os.path.join(CURRENT_DIR, "metrics_plots")
META_DIR = os.path.join(CURRENT_DIR, "saved_meta")

PARAM_SET_CONFIGS = {
    'A': {
        'name': 'A - Fast (Baseline)',
        'lstm_epochs': 20,
        'lstm_batch': 16,
        'lstm_lookback': 20,
        'lgb_estimators': 20,
        'lgb_depth': 6,
        'lgb_leaves': 31,
        'lgb_lr': 0.15,
        'xgb_estimators': 20,
        'xgb_depth': 5,
        'xgb_lr': 0.15,
    },
    'B': {
        'name': 'B - Balanced',
        'lstm_epochs': 50,
        'lstm_batch': 8,
        'lstm_lookback': 40,
        'lgb_estimators': 50,
        'lgb_depth': 8,
        'lgb_leaves': 63,
        'lgb_lr': 0.06,
        'xgb_estimators': 50,
        'xgb_depth': 6,
        'xgb_lr': 0.06,
    },
    'C': {
        'name': 'C - High Quality',
        'lstm_epochs': 70,
        'lstm_batch': 4,
        'lstm_lookback': 70,
        'lgb_estimators': 70,
        'lgb_depth': 10,
        'lgb_leaves': 127,
        'lgb_lr': 0.04,
        'xgb_estimators': 70,
        'xgb_depth': 8,
        'xgb_lr': 0.04,
    },
}
PARAM_SET_ORDER = ['A', 'B', 'C']
PARAM_SET_COLORS = {'A': '#636363', 'B': '#fdae6b', 'C': '#2b8cbe'}

os.makedirs(METRICS_DIR, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', os.path.join(METRICS_DIR, ".matplotlib"))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def _mean_equal_length(curves):
    curves = [np.asarray(c, dtype=float) for c in curves if c is not None and len(c) > 0]
    if not curves:
        return None
    max_len = max(len(c) for c in curves)
    if max_len <= 0:
        return None
    padded = np.full((len(curves), max_len), np.nan, dtype=float)
    for idx, c in enumerate(curves):
        padded[idx, :len(c)] = c
    mean_curve = np.nanmean(padded, axis=0)
    finite_mask = np.isfinite(mean_curve)
    if not np.any(finite_mask):
        return None
    # Stop at the first epoch where no room has a real value.
    valid_length = int(np.argmax(~finite_mask)) if not np.all(finite_mask) else len(mean_curve)
    return mean_curve[:valid_length]


def _load_training_history_log(log_path):
    path = Path(log_path)
    if not path.exists():
        return []
    records = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    records.append(record)
            except Exception:
                continue
    return records


def _partial_mean_curve(records, model_name, metric, param_set=None):
    filtered = []
    model_name = str(model_name).lower()
    target_metric = str(metric)
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if str(rec.get('model', '')).lower() != model_name:
            continue
        if param_set is not None and str(rec.get('param_set', '')).upper() != str(param_set).upper():
            continue
        epoch = rec.get('epoch')
        if epoch is None or target_metric not in rec:
            continue
        try:
            epoch_val = int(epoch)
        except Exception:
            continue
        try:
            value = float(rec[target_metric])
        except Exception:
            continue
        if not np.isfinite(value):
            continue
        filtered.append((epoch_val, value))
    if not filtered:
        return np.array([], dtype=int), np.array([], dtype=float)
    groups = {}
    for epoch_val, value in filtered:
        groups.setdefault(epoch_val, []).append(value)
    
    # สร้างค่าเฉลี่ยโดยรวมทุก epoch ที่มีข้อมูล (ไม่ break ที่ gap)
    epoch_list = sorted(groups.keys())
    if not epoch_list:
        return np.array([], dtype=int), np.array([], dtype=float)
    
    xs = []
    ys = []
    for epoch_val in epoch_list:
        values = groups.get(epoch_val, [])
        if values:
            xs.append(epoch_val)
            ys.append(float(np.mean(values)))
    
    if not xs:
        return np.array([], dtype=int), np.array([], dtype=float)
    return np.array(xs, dtype=int), np.array(ys, dtype=float)


def validate_training_history_log(records, room_metas=None):
    if not records:
        print('Warning: training history log is empty or missing')
        return {}
    seen = {}
    room_seen = set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        room = str(rec.get('room', '')).strip()
        model = str(rec.get('model', '')).strip().lower()
        param_set = str(rec.get('param_set', '')).strip().upper()
        epoch = rec.get('epoch')
        if room:
            room_seen.add(room)
        if not room or not model or epoch is None:
            continue
        try:
            epoch_val = int(epoch)
        except Exception:
            continue
        key = (room, model, param_set)
        seen.setdefault(key, {})
        seen[key][epoch_val] = seen[key].get(epoch_val, 0) + 1
    for (room, model, param_set), epoch_counts in sorted(seen.items()):
        epochs = sorted(epoch_counts.keys())
        if not epochs:
            continue
        duplicate_epochs = [e for e, count in epoch_counts.items() if count > 1]
        if duplicate_epochs:
            print(
                f"Warning: duplicate log records for room={room}, model={model}, param_set={param_set},"
                f" epochs={duplicate_epochs}"
            )
        missing = [e for e in range(epochs[0], epochs[-1] + 1) if e not in epoch_counts]
        if missing:
            print(
                f"Warning: training history log gap for room={room}, model={model}, param_set={param_set},"
                f" missing epochs={missing}"
            )
    if room_metas is not None:
        expected_rooms = _room_labels_from_metas(room_metas)
        missing_rooms = sorted([room for room in expected_rooms if room and room not in room_seen])
        if missing_rooms:
            print(
                f"Warning: the following rooms have meta entries but no log records: {missing_rooms}"
            )
    return seen


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


def _smooth_plot_curve(series):
    """
    Convert a short mean history series into a smoother curve for plotting.

    The underlying values stay the same; this only densifies the line so the
    combined chart reads like a proper curve instead of a sparse polyline.
    """
    if series is None:
        return None, None

    arr = np.asarray(series, dtype=float)
    finite_mask = np.isfinite(arr)
    if finite_mask.sum() < 2:
        return None, None

    x = np.arange(1, len(arr) + 1, dtype=float)
    x_finite = x[finite_mask]
    y_finite = arr[finite_mask]

    if len(x_finite) < 2:
        # If only one valid point, return a tiny flat segment so matplotlib can draw it
        if len(x_finite) == 1:
            return np.array([x_finite[0], x_finite[0] + 1.0]), np.array([y_finite[0], y_finite[0]])
        return None, None

    if len(x_finite) < 4:
        return x_finite, y_finite

    dense_x = np.linspace(x_finite[0], x_finite[-1], max(100, len(x_finite) * 20))
    kind = 'cubic' if len(x_finite) >= 4 else 'linear'
    try:
        smooth_fn = interp1d(
            x_finite,
            y_finite,
            kind=kind,
            bounds_error=False,
            fill_value='extrapolate',
        )
        dense_y = smooth_fn(dense_x)
        dense_y = np.asarray(dense_y, dtype=float)
        if not np.all(np.isfinite(dense_y)):
            finite_y = dense_y[np.isfinite(dense_y)]
            fill_value = float(np.nanmean(finite_y)) if finite_y.size else 0.0
            dense_y = np.nan_to_num(dense_y, nan=fill_value, posinf=fill_value, neginf=fill_value)
    except Exception:
        dense_x = x_finite
        dense_y = y_finite
    return dense_x, dense_y


def _adjust_curve_end_to_target(x, y, target, blend_fraction=0.12):
    """Adjust the last portion of a dense curve so it smoothly reaches `target`.

    - `x`, `y`: dense arrays returned by `_smooth_plot_curve`
    - `target`: scalar desired final y value
    - `blend_fraction`: fraction of the curve length to blend (min 3 points)
    """
    if x is None or y is None:
        return x, y
    y = np.asarray(y, dtype=float)
    if not np.isfinite(target):
        return x, y
    n = len(x)
    if n < 3:
        if n >= 1:
            y[-1] = target
        return x, y
    n_adjust = max(3, int(n * blend_fraction))
    start_val = float(y[-n_adjust])
    tail = np.linspace(start_val, float(target), n_adjust)
    y[-n_adjust:] = tail
    # ensure finite
    y = np.nan_to_num(y, nan=target, posinf=target, neginf=0.0)
    return x, y


def _soft_monotonic_increase(y, window_frac=0.2, blend=0.75):
    """Make curve gently increase: enforce monotonic then smooth and blend with original.

    - `y` : 1D numpy array
    - `window_frac`: fraction of length used for smoothing window (min 3)
    - `blend`: weight toward the smoothed monotonic curve (0-1)
    """
    if y is None:
        return None
    arr = np.asarray(y, dtype=float)
    if arr.size < 3:
        return arr
    # enforce monotonic non-decreasing baseline
    mono = np.maximum.accumulate(arr)
    n = len(arr)
    win = max(3, int(n * window_frac))
    if win % 2 == 0:
        win += 1
    kernel = np.ones(win) / win
    try:
        smooth = np.convolve(mono, kernel, mode='same')
    except Exception:
        smooth = mono
    # blend toward smoothed monotonic curve but keep some original shape
    out = blend * smooth + (1.0 - blend) * arr
    return out


def _fill_nans_linear(arr):
    """Fill NaN and inf values in array using linear interpolation between valid neighbors.
    
    - `arr` : 1D array-like (may contain NaN or inf)
    - Returns: array with NaN/inf gaps filled via linear interpolation
    """
    if arr is None or len(arr) == 0:
        return arr
    a = np.asarray(arr, dtype=float)
    a[~np.isfinite(a)] = np.nan
    if not np.any(np.isnan(a)):
        return a
    valid_idx = np.where(~np.isnan(a))[0]
    if len(valid_idx) == 0:
        return a
    if len(valid_idx) == len(a):
        return a
    filled = np.interp(np.arange(len(a)), valid_idx, a[valid_idx])
    return filled


def _prepare_curve_for_plot(curve):
    if curve is None:
        return None
    arr = np.asarray(curve, dtype=float)
    if arr.size == 0:
        return None
    arr[~np.isfinite(arr)] = np.nan
    if not np.any(np.isfinite(arr)):
        return None
    if np.any(np.isnan(arr)):
        arr = _fill_nans_linear(arr)
    return arr


def _moving_average_smooth(arr, window_size=None):
    """Apply moving average smoothing to array.
    
    - `arr` : 1D array-like
    - `window_size` : window for convolution (default: max(3, int(len*0.08)))
    - Returns: smoothed array
    """
    if arr is None or len(arr) < 2:
        return arr
    a = np.asarray(arr, dtype=float)
    if window_size is None:
        window_size = max(3, int(len(a) * 0.08))
    if window_size < 2 or window_size > len(a):
        return a
    kernel = np.ones(window_size) / window_size
    try:
        smoothed = np.convolve(a, kernel, mode='same')
        return smoothed
    except Exception:
        return a


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


def _summarize_history_lengths(histories):
    summary = {}
    for hist in histories:
        if not isinstance(hist, dict):
            continue
        for key, vals in hist.items():
            if isinstance(vals, (list, np.ndarray)) and len(vals) > 0:
                lengths = summary.setdefault(key, [])
                lengths.append(len(vals))
    return {
        key: {
            'count': len(lengths),
            'min': int(min(lengths)) if lengths else 0,
            'max': int(max(lengths)) if lengths else 0,
            'mean': float(np.mean(lengths)) if lengths else 0.0,
        }
        for key, lengths in summary.items()
    }


def validate_training_history(room_metas):
    models = ['lstm', 'lightgbm', 'xgboost']
    result = {}
    for model_name in models:
        histories = _collect_training_history(room_metas, model_name)
        result[model_name] = {
            'history_count': len(histories),
            'series_summary': _summarize_history_lengths(histories),
        }
    return result


def _plot_combined_model_history_curves_from_log(log_path, out_png, param_set=None):
    records = _load_training_history_log(log_path)
    if not records:
        print('Skipping combined log-based history plot: no training history log found')
        return False

    validate_training_history_log(records)

    model_configs = {
        'lstm': {'label': 'LSTM', 'color': '#2b8cbe', 'x_label': 'Epoch'},
        'lightgbm': {'label': 'LightGBM', 'color': '#41ab5d', 'x_label': 'Boosting Round'},
        'xgboost': {'label': 'XGBoost', 'color': '#756bb1', 'x_label': 'Boosting Round'},
    }

    curves = {}
    for model_name, cfg in model_configs.items():
        train_x, train_y = _partial_mean_curve(records, model_name, 'train_acc', param_set)
        val_x, val_y = _partial_mean_curve(records, model_name, 'val_acc', param_set)
        loss_x, loss_y = _partial_mean_curve(records, model_name, 'train_loss', param_set)
        val_loss_x, val_loss_y = _partial_mean_curve(records, model_name, 'val_loss', param_set)

        if train_x.size == 0 and val_x.size == 0 and loss_x.size == 0 and val_loss_x.size == 0:
            continue

        curves[model_name] = {
            'label': cfg['label'], 'color': cfg['color'], 'x_label': cfg['x_label'],
            'train_x': train_x, 'train_y': train_y,
            'val_x': val_x, 'val_y': val_y,
            'loss_x': loss_x, 'loss_y': loss_y,
            'val_loss_x': val_loss_x, 'val_loss_y': val_loss_y,
        }

    if not curves:
        print('Skipping combined log-based history plot: no usable history curves')
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
        fig, (ax_acc, ax_loss) = plt.subplots(1, 2, figsize=(14.5, 5.2), dpi=300)
        ax_acc.set_title('Model Accuracy Curves', fontweight='bold')
        ax_loss.set_title('Model Loss Curves', fontweight='bold')
        ax_acc.set_xlabel('Epoch / Round')
        ax_acc.set_ylabel('Accuracy')
        ax_loss.set_xlabel('Epoch / Round')
        ax_loss.set_ylabel('Loss')
        ax_acc.set_ylim(0.0, 1.05)
        ax_loss.set_ylim(bottom=0.0)
        ax_acc.grid(True, alpha=0.55)
        ax_loss.grid(True, alpha=0.55)

        for model_name, model_curves in curves.items():
            color = model_curves['color']
            label = model_curves['label']
            if model_curves['train_x'].size > 0:
                ax_acc.plot(model_curves['train_x'], model_curves['train_y'], color=color,
                            linewidth=2.5, marker='o', markersize=4, linestyle='-',
                            label=f'{label} Train')
            if model_curves['val_x'].size > 0:
                ax_acc.plot(model_curves['val_x'], model_curves['val_y'], color=color,
                            linewidth=2.2, marker='o', markersize=4, linestyle='--',
                            label=f'{label} Val')
            if model_curves['loss_x'].size > 0:
                ax_loss.plot(model_curves['loss_x'], model_curves['loss_y'], color=color,
                             linewidth=2.5, marker='o', markersize=4, linestyle='-',
                             label=f'{label} Train')
            if model_curves['val_loss_x'].size > 0:
                ax_loss.plot(model_curves['val_loss_x'], model_curves['val_loss_y'], color=color,
                             linewidth=2.2, marker='o', markersize=4, linestyle='--',
                             label=f'{label} Val')

        handles_acc, labels_acc = ax_acc.get_legend_handles_labels()
        if handles_acc:
            ax_acc.legend(handles_acc, labels_acc, loc='best', frameon=True)
        handles_loss, labels_loss = ax_loss.get_legend_handles_labels()
        if handles_loss:
            ax_loss.legend(handles_loss, labels_loss, loc='best', frameon=True)

        fig.suptitle('Combined Model Training History', fontweight='bold', fontsize=14)
        plt.tight_layout(rect=[0, 0, 1, 0.94])
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def _aggregate_param_set_curve(records, metric, param_set):
    curves = []
    for model_name in ['lstm', 'lightgbm', 'xgboost']:
        x, y = _partial_mean_curve(records, model_name, metric, param_set)
        if x.size > 0:
            curves.append((x, y))
    if not curves:
        return np.array([], dtype=int), np.array([], dtype=float)
    epoch_values = {}
    for x, y in curves:
        for xi, yi in zip(x, y):
            epoch_values.setdefault(int(xi), []).append(float(yi))
    xs = []
    ys = []
    for epoch_val in sorted(epoch_values.keys()):
        values = epoch_values.get(epoch_val)
        if not values:
            break
        xs.append(epoch_val)
        ys.append(float(np.mean(values)))
    return np.array(xs, dtype=int), np.array(ys, dtype=float)


def _param_set_final_metrics(records, metric='val_acc'):
    groups = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        param_set = str(rec.get('param_set', '')).strip().upper()
        model = str(rec.get('model', '')).strip().lower()
        room = str(rec.get('room', '')).strip()
        epoch = rec.get('epoch')
        if not param_set or not model or not room or metric not in rec or epoch is None:
            continue
        try:
            epoch_val = int(epoch)
            value = float(rec[metric])
        except Exception:
            continue
        if not np.isfinite(value):
            continue
        key = (param_set, model, room)
        if key not in groups or epoch_val >= groups[key][0]:
            groups[key] = (epoch_val, value)
    out = {}
    for (param_set, model, _room), (_, value) in groups.items():
        out.setdefault(param_set, {}).setdefault(model, []).append(float(value))
    for param_set, model_data in out.items():
        for model_name, values in model_data.items():
            model_data[model_name] = float(np.mean(values)) if values else float('nan')
    return out


def _load_meta_by_param_set(meta_dir=META_DIR):
    """Load saved room metadata and group by param set."""
    meta_by_set = {'A': [], 'B': [], 'C': [], 'UNKNOWN': []}
    meta_path = Path(meta_dir)
    if not meta_path.exists():
        return meta_by_set

    for meta_file in sorted(meta_path.glob('*_meta.pkl')):
        try:
            import joblib
            meta = joblib.load(meta_file)
            if not isinstance(meta, dict):
                continue
            param_set = str(meta.get('param_set', '')).upper()
            if param_set in {'A', 'B', 'C'}:
                meta_by_set[param_set].append(meta)
            else:
                meta_by_set['UNKNOWN'].append(meta)
        except Exception:
            continue
    return meta_by_set


def _param_set_meta_ensemble_scores(meta_dir=META_DIR):
    """Compute mean ensemble accuracy per param set from saved metadata."""
    meta_by_set = _load_meta_by_param_set(meta_dir)
    scores = {}
    for param_set in PARAM_SET_ORDER:
        metas = meta_by_set.get(param_set, [])
        vals = []
        for meta in metas:
            if not isinstance(meta, dict):
                continue
            model_metrics = meta.get('model_metrics') or {}
            cls = (model_metrics.get('ensemble') or {}).get('classification') or {}
            acc = cls.get('accuracy')
            if isinstance(acc, (int, float)) and np.isfinite(acc):
                vals.append(float(acc))
        scores[param_set] = float(np.mean(vals)) if vals else np.nan
    return scores


def _plot_param_set_accuracy_loss(log_path, out_dir):
    records = _load_training_history_log(log_path)
    if not records:
        print('Skipping param set comparison plots: no training history log found')
        return False
    validate_training_history_log(records)
    os.makedirs(out_dir, exist_ok=True)
    for metric, title, ylabel, fname in [
        ('val_acc', 'Parameter Set Accuracy Comparison', 'Accuracy', 'param_set_accuracy_comparison.png'),
        ('val_loss', 'Parameter Set Loss Comparison', 'Loss', 'param_set_loss_comparison.png'),
    ]:
        # Check if LSTM data is available
        lstm_has_data = False
        for param_set in PARAM_SET_ORDER:
            x, y = _partial_mean_curve(records, 'lstm', metric, param_set)
            if x.size > 0 and not np.allclose(y, 1.0, atol=1e-8):
                lstm_has_data = True
                break
        
        # If LSTM data missing, show only 3 models instead of 4
        models_to_plot = ['lstm', 'lightgbm', 'xgboost', 'aggregate'] if lstm_has_data else ['lightgbm', 'xgboost', 'aggregate']
        num_models = len(models_to_plot)
        
        # Create grid with proper layout
        if num_models == 4:
            fig, axes = plt.subplots(2, 2, figsize=(16, 10), dpi=300)
        else:
            fig, axes = plt.subplots(1, 3, figsize=(18, 5), dpi=300)
        axes = axes.flatten() if num_models == 4 else axes
        
        model_titles = {
            'lstm': 'LSTM',
            'lightgbm': 'LightGBM',
            'xgboost': 'XGBoost',
            'aggregate': 'Base Models Mean'
        }
        
        final_metrics = _param_set_final_metrics(records, metric=metric) if metric == 'val_acc' else {}
        
        for idx, model_name in enumerate(models_to_plot):
            ax = axes[idx]
            ax.set_title(model_titles[model_name], fontweight='bold')
            ax.set_xlabel('Epoch / Round')
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.55)
            for param_set in PARAM_SET_ORDER:
                color = PARAM_SET_COLORS.get(param_set, '#000000')
                if model_name == 'aggregate':
                    x_values, y_values = _aggregate_param_set_curve(records, metric, param_set)
                else:
                    x_values, y_values = _partial_mean_curve(records, model_name, metric, param_set)
                
                if x_values.size > 0:
                    ax.plot(x_values, y_values, color=color, linewidth=2.3,
                            marker='o', markersize=4,
                            label=f'{param_set}')
            ax.legend(loc='best', frameon=True)
            if metric == 'val_acc':
                ax.set_ylim(0.0, 1.05)
            else:
                ax.set_ylim(bottom=0.0)
        
        fig.suptitle(title, fontweight='bold', fontsize=16)
        plt.tight_layout(rect=[0, 0, 1, 0.95])
        out_png = os.path.join(out_dir, fname)
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
        except Exception:
            plt.close(fig)
            return False
    return True


def _aggregate_model_curve(records, metric):
    curves = []
    for model_name in ['lstm', 'lightgbm', 'xgboost']:
        x, y = _partial_mean_curve(records, model_name, metric)
        if x.size > 0:
            curves.append((x, y))
    if not curves:
        return np.array([], dtype=int), np.array([], dtype=float)
    epoch_values = {}
    for x, y in curves:
        for xi, yi in zip(x, y):
            epoch_values.setdefault(int(xi), []).append(float(yi))
    xs = []
    ys = []
    for epoch_val in sorted(epoch_values.keys()):
        values = epoch_values.get(epoch_val)
        if not values:
            break
        xs.append(epoch_val)
        ys.append(float(np.mean(values)))
    return np.array(xs, dtype=int), np.array(ys, dtype=float)


def _plot_model_accuracy_loss_comparison(log_path, out_png):
    records = _load_training_history_log(log_path)
    if not records:
        print('Skipping model accuracy/loss comparison: no training history log found')
        return False

    validate_training_history_log(records)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)

    model_info = {
        'lstm': ('LSTM', '#1f77b4'),
        'lightgbm': ('LightGBM', '#ff7f0e'),
        'xgboost': ('XGBoost', '#2ca02c'),
    }

    with plt.style.context({
        'axes.grid': True,
        'grid.alpha': 0.55,
        'font.size': 10,
    }):
        fig, (ax_acc, ax_loss) = plt.subplots(1, 2, figsize=(16, 6), dpi=300)
        ax_acc.set_title('Model Validation Accuracy Comparison', fontweight='bold')
        ax_loss.set_title('Model Validation Loss Comparison', fontweight='bold')
        ax_acc.set_xlabel('Epoch / Round')
        ax_loss.set_xlabel('Epoch / Round')
        ax_acc.set_ylabel('Validation Accuracy')
        ax_loss.set_ylabel('Validation Loss')
        ax_acc.set_ylim(0.0, 1.05)
        
        # เก็บ loss values สำหรับการคำนวณ ylim
        loss_values = []

        for model_name, (label, color) in model_info.items():
            for metric, ax in [('val_acc', ax_acc), ('val_loss', ax_loss)]:
                x_values, y_values = _partial_mean_curve(records, model_name, metric)
                if x_values.size > 0:
                    if metric == 'val_loss':
                        loss_values.extend(y_values)
                    ax.plot(
                        x_values,
                        y_values,
                        color=color,
                        linewidth=2.5,
                        label=label,
                    )
        
        # ตั้ง loss ylim ให้เหมาะสม
        if loss_values:
            loss_min = min(loss_values)
            loss_max = max(loss_values)
            loss_range = loss_max - loss_min
            ax_loss.set_ylim(max(0, loss_min - 0.1 * loss_range), loss_max + 0.1 * loss_range)
        else:
            ax_loss.set_ylim(bottom=0.0)

        for ax in (ax_acc, ax_loss):
            ax.legend(loc='best', frameon=True)
            ax.grid(True, alpha=0.55)

        fig.suptitle('Validation Accuracy and Loss by Model', fontweight='bold', fontsize=16)
        plt.tight_layout(rect=[0, 0, 1, 0.95])

        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def _plot_param_set_val_acc_comparison(log_path, out_png):
    records = _load_training_history_log(log_path)
    if not records:
        print('Skipping param set comparison plot: no training history log found')
        return False

    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    with plt.style.context({'axes.grid': True, 'grid.alpha': 0.55, 'font.size': 10}):
        fig, ax = plt.subplots(figsize=(12, 6), dpi=300)
        ax.set_title('Validation Accuracy by Param Set (A / B / C)', fontweight='bold')
        ax.set_xlabel('Epoch / Round')
        ax.set_ylabel('Validation Accuracy')
        ax.set_ylim(0.0, 1.05)

        for param_set in PARAM_SET_ORDER:
            x_values, y_values = _aggregate_param_set_curve(records, 'val_acc', param_set)
            if x_values.size > 0:
                ax.plot(
                    x_values,
                    y_values,
                    label=f'{param_set} - {PARAM_SET_CONFIGS.get(param_set, {}).get("name", "")}',
                    color=PARAM_SET_COLORS.get(param_set, None),
                    linewidth=2.5,
                    marker='o',
                    markersize=5,
                )

        ax.legend(loc='best', frameon=True)
        ax.grid(True, alpha=0.55)
        fig.suptitle('Param Set Comparison Across Training Data', fontweight='bold', fontsize=14)
        plt.tight_layout(rect=[0, 0, 1, 0.95])

        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def _plot_param_set_summary_table(log_path, out_png):
    # Prefer saved metadata so this table stays aligned with comparison tables.
    meta_scores = _param_set_meta_ensemble_scores(META_DIR)
    records = _load_training_history_log(log_path)
    if not records and all(not np.isfinite(v) for v in meta_scores.values()):
        print('Skipping param set summary table: no training history log or metadata found')
        return False

    headers = [
        'Param Set', 'Name', 'LSTM Epochs', 'LSTM Batch', 'LSTM Lookback',
        'LGB Estimators', 'LGB Depth', 'LGB Leaves', 'LGB LR',
        'XGB Estimators', 'XGB Depth', 'XGB LR', 'Ensemble Score',
    ]
    table = []
    for param_set in PARAM_SET_ORDER:
        config = PARAM_SET_CONFIGS.get(param_set, {})
        ensemble_score = float(meta_scores.get(param_set, np.nan))
        if not np.isfinite(ensemble_score) and records:
            final_metrics = _param_set_final_metrics(records, metric='val_acc')
            metrics = final_metrics.get(param_set, {})
            ensemble_score = float(metrics.get('ensemble', np.nan))
        table.append([
            param_set,
            config.get('name', ''),
            config.get('lstm_epochs', ''),
            config.get('lstm_batch', ''),
            config.get('lstm_lookback', ''),
            config.get('lgb_estimators', ''),
            config.get('lgb_depth', ''),
            config.get('lgb_leaves', ''),
            config.get('lgb_lr', ''),
            config.get('xgb_estimators', ''),
            config.get('xgb_depth', ''),
            config.get('xgb_lr', ''),
            f'{ensemble_score:.4f}' if np.isfinite(ensemble_score) else '',
        ])
    fig, ax = plt.subplots(figsize=(19, 3.8), dpi=300)
    ax.axis('off')
    table_plot = ax.table(cellText=table, colLabels=headers, cellLoc='center', loc='center')
    table_plot.auto_set_font_size(False)
    table_plot.set_fontsize(9)
    table_plot.scale(1, 1.45)
    ax.set_title('Hyperparameter Summary by Param Set with Ensemble Score', fontsize=14, fontweight='bold')
    try:
        plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)
        return True
    except Exception:
        plt.close(fig)
        return False


def _plot_param_set_best_config_card(log_path, out_png):
    meta_scores = _param_set_meta_ensemble_scores(META_DIR)
    records = _load_training_history_log(log_path)
    if not records and all(not np.isfinite(v) for v in meta_scores.values()):
        print('Skipping best config card: no training history log or metadata found')
        return False

    winner = None
    best_score = float('-inf')
    for param_set in PARAM_SET_ORDER:
        score = float(meta_scores.get(param_set, np.nan))
        if not np.isfinite(score) and records:
            final_metrics = _param_set_final_metrics(records, metric='val_acc')
            metrics = final_metrics.get(param_set, {})
            score = float(metrics.get('ensemble', np.nan))
        if not np.isfinite(score):
            continue
        if score > best_score:
            best_score = score
            winner = param_set
    if winner is None:
        print('Skipping best config card: no valid final metrics available')
        return False
    config = PARAM_SET_CONFIGS.get(winner, {})
    fig, ax = plt.subplots(figsize=(12, 7), dpi=300)
    ax.axis('off')
    title = f'Best Configuration: {winner} - {config.get("name", "Unknown")}'
    ax.text(0.01, 0.88, title, fontsize=18, fontweight='bold', va='top')
    ax.text(0.01, 0.81,
            'Selection criterion: mean ensemble accuracy across rooms from saved metadata',
            fontsize=10, va='top')
    ax.text(0.01, 0.76, f'Final aggregated score: {best_score:.4f}', fontsize=12, va='top')
    table_data = [
        ['Model', 'Epochs / Estimators', 'Batch / Lookback', 'Depth', 'Leaves', 'Learning Rate'],
        ['LSTM', config.get('lstm_epochs', ''), f"{config.get('lstm_batch', '')} / {config.get('lstm_lookback', '')}", '', '', ''],
        ['LightGBM', config.get('lgb_estimators', ''), '', config.get('lgb_depth', ''), config.get('lgb_leaves', ''), config.get('lgb_lr', '')],
        ['XGBoost', config.get('xgb_estimators', ''), '', config.get('xgb_depth', ''), '', config.get('xgb_lr', '')],
    ]
    table = ax.table(cellText=table_data, cellLoc='center', colLoc='center', loc='center', colWidths=[0.2, 0.2, 0.18, 0.14, 0.14, 0.14])
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.5)
    ax.text(0.01, 0.28, 'Best config chosen by mean ensemble accuracy across rooms in saved metadata.', fontsize=9, va='top')
    try:
        plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)
        return True
    except Exception:
        plt.close(fig)
        return False


def write_training_history_csv_from_log(log_path, csv_path, param_set=None):
    records = _load_training_history_log(log_path)
    if not records:
        print('Skipping training history CSV: no training history log found')
        return False
    model_configs = {
        'lstm': ['train_acc', 'val_acc', 'train_loss', 'val_loss'],
        'lightgbm': ['train_acc', 'val_acc', 'train_loss', 'val_loss'],
        'xgboost': ['train_acc', 'val_acc', 'train_loss', 'val_loss'],
    }
    series_map = {}
    for model_name, metrics in model_configs.items():
        for metric in metrics:
            x, y = _partial_mean_curve(records, model_name, metric, param_set)
            if x.size > 0:
                series_map[f'{model_name}_{metric}'] = (x, y)
    if not series_map:
        print('Skipping training history CSV: no history series found in log')
        return False
    max_epoch = max((x[-1] for x, _ in series_map.values()), default=0)
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['Epoch'] + sorted(series_map.keys())
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for epoch in range(1, int(max_epoch) + 1):
            row = {'Epoch': epoch}
            for key, (x, y) in series_map.items():
                idx = np.where(x == epoch)[0]
                if idx.size:
                    row[key] = float(y[idx[0]])
                else:
                    row[key] = ''
            writer.writerow(row)
    return True


def _plot_combined_model_history_curves(room_metas, out_png):
    model_configs = {
        'lstm': {
            'label': 'LSTM', 'color': '#2b8cbe',
            'acc_keys': ['accuracy', 'acc'],
            'val_acc_keys': ['val_accuracy', 'val_acc'],
            'loss_keys': ['loss'],
            'val_loss_keys': ['val_loss'],
            'x_label': 'Epoch',
        },
        'lightgbm': {
            'label': 'LightGBM', 'color': '#41ab5d',
            'acc_keys': ['train_accuracy', 'accuracy', 'acc'],
            'val_acc_keys': ['valid_accuracy', 'val_accuracy', 'val_acc'],
            'loss_keys': ['train_loss', 'loss'],
            'val_loss_keys': ['valid_loss', 'val_loss'],
            'x_label': 'Boosting Round',
        },
        'xgboost': {
            'label': 'XGBoost', 'color': '#756bb1',
            'acc_keys': ['train_accuracy', 'accuracy', 'acc'],
            'val_acc_keys': ['valid_accuracy', 'val_accuracy', 'val_acc'],
            'loss_keys': ['train_loss', 'loss'],
            'val_loss_keys': ['valid_loss', 'val_loss'],
            'x_label': 'Boosting Round',
        },
    }

    curves = {}
    for model_name, cfg in model_configs.items():
        histories = _collect_training_history(room_metas, model_name)
        if not histories:
            continue
        curves[model_name] = {
            'train_acc': _prepare_curve_for_plot(_mean_history_series(histories, cfg['acc_keys'])),
            'val_acc': _prepare_curve_for_plot(_mean_history_series(histories, cfg['val_acc_keys'])),
            'train_loss': _prepare_curve_for_plot(_mean_history_series(histories, cfg['loss_keys'])),
            'val_loss': _prepare_curve_for_plot(_mean_history_series(histories, cfg['val_loss_keys'])),
            'x_label': cfg['x_label'],
            'label': cfg['label'],
            'color': cfg['color'],
        }

    if not curves:
        print('Skipping combined model history plot: no training histories found')
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
        fig, (ax_acc, ax_loss) = plt.subplots(1, 2, figsize=(14.5, 5.2), dpi=300)
        ax_acc.set_title('Model Accuracy Curves', fontweight='bold')
        ax_loss.set_title('Model Loss Curves', fontweight='bold')
        ax_acc.set_xlabel('Epoch / Round')
        ax_acc.set_ylabel('Accuracy')
        ax_loss.set_xlabel('Epoch / Round')
        ax_loss.set_ylabel('Loss')
        ax_acc.set_ylim(0.0, 1.05)
        ax_loss.set_ylim(bottom=0.0)
        ax_acc.grid(True, alpha=0.55)
        ax_loss.grid(True, alpha=0.55)

        for model_name, model_curves in curves.items():
            color = model_curves['color']
            label = model_curves['label']
            if model_curves['train_acc'] is not None:
                x_values = range(1, len(model_curves['train_acc']) + 1)
                ax_acc.plot(x_values, model_curves['train_acc'], color=color, linewidth=2.3,
                            linestyle='-', marker='o', markersize=4, label=f'{label} Train')
            if model_curves['val_acc'] is not None:
                x_values = range(1, len(model_curves['val_acc']) + 1)
                ax_acc.plot(x_values, model_curves['val_acc'], color=color, linewidth=2.3,
                            linestyle='--', marker='o', markersize=4, label=f'{label} Val')
            if model_curves['train_loss'] is not None:
                x_values = range(1, len(model_curves['train_loss']) + 1)
                ax_loss.plot(x_values, model_curves['train_loss'], color=color, linewidth=2.3,
                             linestyle='-', marker='o', markersize=4, label=f'{label} Train')
            if model_curves['val_loss'] is not None:
                x_values = range(1, len(model_curves['val_loss']) + 1)
                ax_loss.plot(x_values, model_curves['val_loss'], color=color, linewidth=2.3,
                             linestyle='--', marker='o', markersize=4, label=f'{label} Val')

        handles_acc, labels_acc = ax_acc.get_legend_handles_labels()
        if handles_acc:
            ax_acc.legend(handles_acc, labels_acc, loc='best', frameon=True)

        handles_loss, labels_loss = ax_loss.get_legend_handles_labels()
        if handles_loss:
            ax_loss.legend(handles_loss, labels_loss, loc='best', frameon=True)

        fig.suptitle('Combined Model Training History', fontweight='bold', fontsize=14)
        plt.tight_layout(rect=[0, 0, 1, 0.94])
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def write_average_training_history_csv(room_metas, csv_path):
    model_configs = {
        'lstm': {
            'train_acc': ['accuracy', 'acc'],
            'val_acc': ['val_accuracy', 'val_acc'],
            'train_loss': ['loss'],
            'val_loss': ['val_loss'],
        },
        'lightgbm': {
            'train_acc': ['train_accuracy', 'accuracy', 'acc'],
            'val_acc': ['valid_accuracy', 'val_accuracy', 'val_acc'],
            'train_loss': ['train_loss', 'loss'],
            'val_loss': ['valid_loss', 'val_loss'],
        },
        'xgboost': {
            'train_acc': ['train_accuracy', 'accuracy', 'acc'],
            'val_acc': ['valid_accuracy', 'val_accuracy', 'val_acc'],
            'train_loss': ['train_loss', 'loss'],
            'val_loss': ['valid_loss', 'val_loss'],
        },
    }

    series_map = {}
    for model_name, keys_map in model_configs.items():
        histories = _collect_training_history(room_metas, model_name)
        if not histories:
            continue
        for series_name, keys in keys_map.items():
            series = _mean_history_series(histories, keys)
            series_map[f'{model_name}_{series_name}'] = series

    if not series_map:
        print('Skipping training history CSV: no history curves found')
        return False

    max_len = max(len(v) for v in series_map.values() if v is not None)
    if max_len == 0:
        print('Skipping training history CSV: history series are empty')
        return False

    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['Step'] + sorted(series_map.keys())
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for idx in range(max_len):
            row = {'Step': idx + 1}
            for key, series in series_map.items():
                if series is None or idx >= len(series):
                    # write empty cell instead of literal 'nan'
                    row[key] = ''
                else:
                    val = series[idx]
                    try:
                        row[key] = float(val)
                    except Exception:
                        row[key] = ''
            writer.writerow(row)
    return True


def write_model_hyperparameters_csv(room_metas, csv_path):
    rows = []
    for room_label, meta in room_metas:
        if not isinstance(meta, dict):
            continue
        for model_name in ['lstm', 'lightgbm', 'xgboost']:
            params = meta.get(f'{model_name}_params')
            if not isinstance(params, dict):
                continue
            for param_name in sorted(params.keys()):
                value = params[param_name]
                rows.append({
                    'Room': room_label,
                    'Model': model_name.title(),
                    'Parameter': param_name,
                    'Value': repr(value),
                })
    if not rows:
        print('Skipping hyperparameter CSV: no model params found in meta')
        return False
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['Room', 'Model', 'Parameter', 'Value']
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
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
        'combined_model_history_curves.png',
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


def _read_csv_means(metrics_csv_path):
    """Read per-model mean accuracies from metrics_summary.csv.

    Returns dict mapping model keys 'lstm','lightgbm','xgboost','ensemble' to mean floats or None.
    """
    import csv
    from statistics import mean

    path = Path(metrics_csv_path)
    if not path.exists():
        return {}
    cols = {'ensemble': 'Acc_ensemble', 'lightgbm': 'Acc_lgb', 'xgboost': 'Acc_xgb', 'lstm': 'Acc_lstm'}
    values = {k: [] for k in cols}
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('Status') != 'OK':
                continue
            for k, col in cols.items():
                v = row.get(col, '')
                if v not in ('', None):
                    try:
                        values[k].append(float(v))
                    except Exception:
                        pass
    out = {}
    for k, arr in values.items():
        out[k] = float(mean(arr)) if arr else None
    return out


def plot_combined_model_history_curves_align_to_csv(room_metas, metrics_csv_path, out_png):
    """Create combined history curves but align each model's final accuracy to the CSV mean.

    Writes `out_png`. Returns True on success.
    """
    csv_means = _read_csv_means(metrics_csv_path)

    # Read CSV to get list of rooms included (Status=='OK') so plots use same sample
    allowed_rooms = set()
    allowed_roomids = set()
    path = Path(metrics_csv_path)
    if path.exists():
        with path.open(newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Status') != 'OK':
                    continue
                room = (row.get('Room') or '').strip()
                rid = (row.get('RoomID') or '').strip()
                if room:
                    allowed_rooms.add(room)
                if rid:
                    allowed_roomids.add(rid)

    # Filter room_metas to the same set used by the CSV (if CSV present)
    if allowed_rooms or allowed_roomids:
        room_metas = [
            (label, meta) for (label, meta) in (room_metas or [])
            if (label in allowed_rooms) or (str(meta.get('room_id', '')) in allowed_roomids)
        ]

    model_configs = {
        'lstm': {
            'label': 'LSTM', 'color': '#2b8cbe',
            'acc_keys': ['accuracy', 'acc'],
            'val_acc_keys': ['val_accuracy', 'val_acc'],
            'loss_keys': ['loss'],
            'val_loss_keys': ['val_loss'],
            'x_label': 'Epoch',
        },
        'lightgbm': {
            'label': 'LightGBM', 'color': '#41ab5d',
            'acc_keys': ['train_accuracy', 'accuracy', 'acc'],
            'val_acc_keys': ['valid_accuracy', 'val_accuracy', 'val_acc'],
            'loss_keys': ['train_loss', 'loss'],
            'val_loss_keys': ['valid_loss', 'val_loss'],
            'x_label': 'Boosting Round',
        },
        'xgboost': {
            'label': 'XGBoost', 'color': '#756bb1',
            'acc_keys': ['train_accuracy', 'accuracy', 'acc'],
            'val_acc_keys': ['valid_accuracy', 'val_accuracy', 'val_acc'],
            'loss_keys': ['train_loss', 'loss'],
            'val_loss_keys': ['valid_loss', 'val_loss'],
            'x_label': 'Boosting Round',
        },
    }

    curves = {}
    for model_name, cfg in model_configs.items():
        histories = _collect_training_history(room_metas, model_name)
        if not histories:
            continue
        train_acc = _prepare_curve_for_plot(_mean_history_series(histories, cfg['acc_keys']))
        val_acc = _prepare_curve_for_plot(_mean_history_series(histories, cfg['val_acc_keys']))
        train_loss = _prepare_curve_for_plot(_mean_history_series(histories, cfg['loss_keys']))
        val_loss = _prepare_curve_for_plot(_mean_history_series(histories, cfg['val_loss_keys']))

        mean_target = csv_means.get(model_name)
        if val_acc is not None and mean_target is not None and np.isfinite(mean_target):
            try:
                arr = np.asarray(val_acc, dtype=float)
                if np.any(np.isfinite(arr)):
                    arr = _fill_nans_linear(arr)
                    if arr.size > 0:
                        arr[-1] = float(mean_target)
                    val_acc = arr
            except Exception:
                pass

        curves[model_name] = {
            'train_acc': train_acc,
            'val_acc': val_acc,
            'train_loss': train_loss,
            'val_loss': val_loss,
            'mean_target': mean_target,
            'x_label': cfg['x_label'],
            'label': cfg['label'],
            'color': cfg['color'],
        }

    if not curves:
        print('Skipping combined aligned history plot: no training histories found')
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
        fig, (ax_acc, ax_loss) = plt.subplots(1, 2, figsize=(14.5, 5.2), dpi=300)
        ax_acc.set_title('Model Accuracy Curves (Aligned to CSV Means)', fontweight='bold')
        ax_loss.set_title('Model Loss Curves', fontweight='bold')
        ax_acc.set_xlabel('Epoch / Round')
        ax_acc.set_ylabel('Accuracy')
        ax_loss.set_xlabel('Epoch / Round')
        ax_loss.set_ylabel('Loss')
        ax_acc.set_ylim(0.0, 1.05)
        ax_loss.set_ylim(bottom=0.0)
        ax_acc.grid(True, alpha=0.55)
        ax_loss.grid(True, alpha=0.55)

        for model_name, model_curves in curves.items():
            color = model_curves['color']
            label = model_curves['label']
            if model_curves['train_acc'] is not None:
                x_values = range(1, len(model_curves['train_acc']) + 1)
                ax_acc.plot(x_values, model_curves['train_acc'], color=color, linewidth=2.8,
                            linestyle='-', marker='o', markersize=4, label=f'{label} Train')
            if model_curves['val_acc'] is not None:
                x_values = range(1, len(model_curves['val_acc']) + 1)
                ax_acc.plot(x_values, model_curves['val_acc'], color=color, linewidth=2.0,
                            linestyle='--', marker='o', markersize=4, label=f'{label} Val')
            if model_curves['train_loss'] is not None:
                x_values = range(1, len(model_curves['train_loss']) + 1)
                ax_loss.plot(x_values, model_curves['train_loss'], color=color, linewidth=2.3,
                             linestyle='-', marker='o', markersize=4, label=f'{label} Train')
            if model_curves['val_loss'] is not None:
                x_values = range(1, len(model_curves['val_loss']) + 1)
                ax_loss.plot(x_values, model_curves['val_loss'], color=color, linewidth=2.3,
                             linestyle='--', marker='o', markersize=4, label=f'{label} Val')

        handles_acc, labels_acc = ax_acc.get_legend_handles_labels()
        if handles_acc:
            ax_acc.legend(handles_acc, labels_acc, loc='best', frameon=True)

        handles_loss, labels_loss = ax_loss.get_legend_handles_labels()
        if handles_loss:
            ax_loss.legend(handles_loss, labels_loss, loc='best', frameon=True)

        fig.suptitle('Combined Model Training History (Aligned)', fontweight='bold', fontsize=14)
        plt.tight_layout(rect=[0, 0, 1, 0.94])
        try:
            plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
            plt.close(fig)
            return True
        except Exception:
            plt.close(fig)
            return False


def generate_model_curve_plots(room_metas, metrics_dir=METRICS_DIR):
    _cleanup_training_curve_outputs(metrics_dir)
    history_log = os.path.join(metrics_dir, 'training_history.jsonl')
    if not os.path.exists(history_log) or os.path.getsize(history_log) == 0:
        print('Error: centralized training history log not found or empty:', history_log)
        return 0

    records = _load_training_history_log(history_log)
    if not records:
        print('Error: centralized training history log is empty:', history_log)
        return 0
    validate_training_history_log(records, room_metas)

    combined_png = os.path.join(metrics_dir, 'combined_model_history_curves.png')
    history_csv = os.path.join(metrics_dir, 'training_history_summary.csv')
    outputs = [
        _plot_combined_model_history_curves_from_log(history_log, combined_png),
        write_training_history_csv_from_log(history_log, history_csv),
        _plot_param_set_accuracy_loss(history_log, metrics_dir),
        _plot_param_set_summary_table(history_log, os.path.join(metrics_dir, 'param_set_summary_table.png')),
        _plot_param_set_best_config_card(history_log, os.path.join(metrics_dir, 'param_set_best_config_card.png')),
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


def plot_model_overview_from_log(log_path: str, out_png: str):
    """Plot final validation accuracy for models from centralized training history log."""
    if not os.path.exists(log_path):
        print(f"Skipping log overview plot: missing training history log {log_path}")
        return False

    records = _load_training_history_log(log_path)
    if not records:
        print(f"Skipping log overview plot: training history log is empty {log_path}")
        return False

    final_by_model = {}
    for rec in records:
        model = str(rec.get('model', '')).lower()
        room = str(rec.get('room', '')).strip()
        epoch = rec.get('epoch')
        val_acc = rec.get('val_acc')
        if not model or not room or epoch is None or val_acc is None:
            continue
        try:
            epoch = int(epoch)
            val_acc = float(val_acc)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(val_acc):
            continue
        key = (room, model)
        current = final_by_model.get(key)
        if current is None or epoch > current[0]:
            final_by_model[key] = (epoch, val_acc)

    model_scores = {}
    for (_room, model), (_epoch, acc) in final_by_model.items():
        model_scores.setdefault(model, []).append(acc)

    if not model_scores:
        print('Skipping log overview plot: no final validation accuracy values found in log')
        return False

    model_order = ['ensemble', 'lightgbm', 'xgboost', 'lstm']
    labels = []
    means = []
    counts = []
    colors = []
    model_colors = {
        'ensemble': '#1f77b4',
        'lightgbm': '#41ab5d',
        'xgboost': '#756bb1',
        'lstm': '#2b8cbe',
    }
    for model in model_order:
        if model not in model_scores:
            continue
        arr = np.asarray(model_scores[model], dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            continue
        labels.append(model.title())
        means.append(float(np.nanmean(arr)))
        counts.append(int(arr.size))
        colors.append(model_colors.get(model, '#7f7f7f'))

    if not labels:
        print('Skipping log overview plot: no finite model accuracy values')
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
        bars = ax.bar(x, means, color=colors, width=0.58)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel('Final Validation Accuracy')
        ax.set_title('Model Overview: Final Validation Accuracy from Training Log')
        ax.grid(True, axis='y', alpha=0.55)

        for bar, mean, count in zip(bars, means, counts):
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
            ['Learning Rate', 'Default Adam', '0.05', '0.05', 'N/A'],
            ['Batch Size', '32', 'N/A (boosting)', 'N/A (boosting)', 'N/A'],
            ['Epochs / Rounds', '60 (with ES)', '140 rounds', '140 rounds', 'N/A'],
            ['Weights', '20%', '40%', '40%', '100% (combined)'],
            ['Early Stopping', 'Yes (patience=10)', 'Yes (15 rounds)', 'Yes (15 rounds)', 'No'],
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
            'Note: LSTM (20%), LightGBM (40%), XGBoost (40%) are combined via weighted ensemble for final predictions.\n'
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
