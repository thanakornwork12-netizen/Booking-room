# ══════════════════════════════════════════════════════════════════════════════
#  Ensemble weight scheme comparison — NO retraining.
#
#  Loads the already-trained/saved LSTM+LightGBM+XGBoost models per room
#  (the live saved_models/ — currently Set C), rebuilds each room's
#  calibration set, gets each model's predictions once, then blends those
#  SAME predictions under several weight schemes to compare accuracy.
#  Only the blend formula changes between schemes — nothing is retrained.
#
#  Usage: python ml/saved/analyze_ensemble_weights.py
# ══════════════════════════════════════════════════════════════════════════════
import os, sys, warnings

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
sys.path.append(BASE_DIR)
sys.path.insert(0, CURRENT_DIR)
os.environ.setdefault('DISABLE_DJANGO_SCHEDULER', '1')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

import django
django.setup()

import numpy as np
import pandas as pd
import joblib
import tensorflow as tf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from booking.models import Booking, Room
import forecast as F

METRICS_DIR = F.METRICS_DIR


def load_raw_bookings() -> pd.DataFrame:
    raw_qs = Booking.objects.exclude(status='cancelled').values('start_time', 'end_time', 'room_id')
    raw = pd.DataFrame(list(raw_qs))
    for col in ['start_time', 'end_time']:
        raw[col] = pd.to_datetime(raw[col])
        if raw[col].dt.tz is None:
            raw[col] = raw[col].dt.tz_localize('UTC')
        raw[col] = raw[col].dt.tz_convert('Asia/Bangkok')
    raw['duration'] = (raw['end_time'] - raw['start_time']).dt.total_seconds() / 3600
    raw['duration'] = raw['duration'].clip(lower=0.25, upper=12.0)
    raw['date'] = raw['start_time'].dt.date
    return raw


def build_all_rooms_daily(raw: pd.DataFrame, rooms) -> dict:
    all_rooms_daily = {}
    for r in rooms:
        rdf_r = raw[raw['room_id'] == r.id]
        if len(rdf_r) == 0:
            all_rooms_daily[r] = pd.Series(dtype=float)
            continue
        daily_r = (
            rdf_r.groupby('date')['duration'].sum()
                 .reindex(pd.date_range(rdf_r['date'].min(), rdf_r['date'].max(), freq='D').date, fill_value=0.0)
                 .astype(float)
        )
        daily_r.index = pd.to_datetime(daily_r.index)
        all_rooms_daily[r] = daily_r
    return all_rooms_daily


def collect_room_cal_predictions(room, raw, all_rooms_daily, meta_dir=None, model_dir=None):
    """Rebuild this room's calibration set and predict with the ALREADY-SAVED
    models. Returns None if any required artifact/model is missing — only
    rooms where LSTM+LGB+XGB all exist are usable for this comparison,
    since the whole point is comparing LSTM's weight against the other two.

    meta_dir/model_dir default to the live saved_meta//saved_models/ (Set C,
    production) but can point at an archive (e.g. saved_meta_D_new/
    saved_models_D_new/) to run this same comparison for another set.
    """
    meta_dir = meta_dir or F.META_DIR
    model_dir = model_dir or F.MODEL_DIR

    meta_path = os.path.join(meta_dir, f"{room.id}_meta.pkl")
    if not os.path.exists(meta_path):
        return None
    try:
        meta = joblib.load(meta_path)
    except Exception:
        return None
    if not meta.get('has_lstm', False):
        return None

    room_artifact_dir = os.path.join(model_dir, str(room.id))
    lgb_path = os.path.join(room_artifact_dir, "lgb.pkl")
    xgb_path = os.path.join(room_artifact_dir, "xgb.pkl")
    keras_lp = os.path.join(room_artifact_dir, "lstm.keras")
    sp = os.path.join(room_artifact_dir, "lstm_scaler.pkl")
    if not (os.path.exists(lgb_path) and os.path.exists(xgb_path)
            and os.path.exists(keras_lp) and os.path.exists(sp)):
        return None

    try:
        lgb_model = joblib.load(lgb_path)
        xgb_model = joblib.load(xgb_path)
        lstm_model = tf.keras.models.load_model(keras_lp, compile=False)
        lstm_scaler = joblib.load(sp)
    except Exception as e:
        print(f"   ⚠️  {room.name}: failed to load saved models ({e})")
        return None

    rdf = raw[raw['room_id'] == room.id]
    schedule = F.load_term_schedule(room.id)
    daily = F._prepare_daily_series(rdf, room, all_rooms_daily)
    if daily is None:
        return None

    use_log = bool(meta.get('use_log', False))
    cap95 = float(daily.quantile(0.95)) or 1.0
    daily = daily.clip(upper=cap95)
    term_df = F.build_term_daily_features(daily.index, schedule)
    term_df.index = daily.index
    feat_df = F.build_features(daily, term_df, use_log=use_log).dropna()
    X = feat_df.drop(columns='y')
    y = feat_df['y'].values
    split = F._split_time_series(X, y)
    if split is None:
        return None
    X_tr, X_cal, X_te, y_tr, y_cal, y_te, train_end, calib_end = split
    if len(y_cal) == 0:
        return None

    try:
        lgb_cal = np.asarray(lgb_model.predict(X_cal), dtype=float)
        xgb_cal = np.asarray(xgb_model.predict(X_cal), dtype=float)
        lgb_te = np.asarray(lgb_model.predict(X_te), dtype=float)
        xgb_te = np.asarray(xgb_model.predict(X_te), dtype=float)
        lstm_cal, lstm_te = F._collect_lstm_holdout_preds(
            lstm_model, lstm_scaler, feat_df, y_tr, y_cal, y_te, train_end,
        )
    except Exception as e:
        print(f"   ⚠️  {room.name}: prediction failed ({e})")
        return None

    if lstm_cal is None or len(lstm_cal) != len(y_cal):
        return None
    if lstm_te is None or len(lstm_te) != len(y_te) or len(y_te) == 0:
        return None

    def _finish(y_raw, lstm_p, lgb_p, xgb_p):
        if use_log:
            y_eval = np.expm1(y_raw)
            lgb_e = np.expm1(lgb_p)
            xgb_e = np.expm1(xgb_p)
            lstm_e = np.expm1(np.asarray(lstm_p, dtype=float))
        else:
            y_eval = y_raw.copy()
            lgb_e = lgb_p
            xgb_e = xgb_p
            lstm_e = np.asarray(lstm_p, dtype=float)
        return (
            np.nan_to_num(y_eval, nan=0.0, posinf=0.0, neginf=0.0),
            np.nan_to_num(lstm_e, nan=0.0, posinf=0.0, neginf=0.0),
            np.nan_to_num(lgb_e, nan=0.0, posinf=0.0, neginf=0.0),
            np.nan_to_num(xgb_e, nan=0.0, posinf=0.0, neginf=0.0),
        )

    y_cal_eval, lstm_cal, lgb_cal, xgb_cal = _finish(y_cal, lstm_cal, lgb_cal, xgb_cal)
    y_te_eval, lstm_te, lgb_te, xgb_te = _finish(y_te, lstm_te, lgb_te, xgb_te)

    return {
        'room': room.name,
        'cal': {'y': y_cal_eval, 'lstm': lstm_cal, 'lgb': lgb_cal, 'xgb': xgb_cal},
        'test': {'y': y_te_eval, 'lstm': lstm_te, 'lgb': lgb_te, 'xgb': xgb_te},
        'thr_high': meta['thr_high'], 'thr_med': meta['thr_med'], 'peak_ref': meta['peak_ref'],
    }


def evaluate_scheme(rooms_data: list, weights: dict, split: str = 'cal') -> dict:
    """Blend the SAME cached predictions under `weights` and score. No model
    calls happen here — this is pure arithmetic, which is why testing many
    weight schemes (or a full grid search) is fast.

    split='cal': used to SEARCH for weights (calibration set — safe to reuse
    for many trials). split='test': used for the FINAL reported numbers on
    data the search never saw, using the same threshold-optimized accuracy
    (_evaluate_with_best_threshold) as hyperparam_comparison.csv / meta.pkl's
    'Ensemble Acc', so these numbers are directly comparable to those.
    """
    accs, r2s, maes = [], [], []
    for d in rooms_data:
        s = d[split]
        blended = weights['lstm'] * s['lstm'] + weights['lgb'] * s['lgb'] + weights['xgb'] * s['xgb']
        blended = np.maximum(0.0, blended)
        _, cls = F._evaluate_with_best_threshold(s['y'], blended, d['thr_high'], d['thr_med'], d['peak_ref'])
        accs.append(cls['accuracy'])
        r2s.append(F.r2_score(s['y'], blended))
        maes.append(F.mean_absolute_error(s['y'], blended))
    return {
        'accuracy': float(np.mean(accs)),
        'r2': float(np.mean(r2s)),
        'mae': float(np.mean(maes)),
    }


def grid_search_best(rooms_data: list, step: int = 5):
    """Exhaustive search over the weight simplex (step%, all combos summing
    to 100%) directly maximizing blended ensemble accuracy — not each
    model's solo accuracy. Searches on the CALIBRATION split only — the test
    split is held out and only touched once, for the final reported numbers,
    so it stays a genuine out-of-sample check."""
    best_weights, best_result = None, None
    for w_lstm in range(0, 101, step):
        for w_lgb in range(0, 101 - w_lstm, step):
            w_xgb = 100 - w_lstm - w_lgb
            weights = {'lstm': w_lstm / 100, 'lgb': w_lgb / 100, 'xgb': w_xgb / 100}
            result = evaluate_scheme(rooms_data, weights, split='cal')
            if best_result is None or result['accuracy'] > best_result['accuracy']:
                best_weights, best_result = weights, result
    return best_weights, best_result


def _accuracy_fast(rooms_data: list, weights: dict, split: str = 'cal') -> float:
    """Same blend as evaluate_scheme() but WITHOUT the 17-point threshold
    search inside _evaluate_with_best_threshold — plain compute_classification_metrics
    instead. ~17x fewer inner calls. Used only inside the bootstrap loop
    below, where we run the grid search hundreds of times and only care
    about the WEIGHT each run lands on, not a publication-precision accuracy
    number for every single resample."""
    accs = []
    for d in rooms_data:
        s = d[split]
        blended = weights['lstm'] * s['lstm'] + weights['lgb'] * s['lgb'] + weights['xgb'] * s['xgb']
        blended = np.maximum(0.0, blended)
        cls = F.compute_classification_metrics(s['y'], blended, d['thr_high'], d['thr_med'], d['peak_ref'])
        accs.append(cls['accuracy'])
    return float(np.mean(accs))


def grid_search_best_fast(rooms_data: list, step: int = 10):
    best_weights, best_acc = None, -1.0
    for w_lstm in range(0, 101, step):
        for w_lgb in range(0, 101 - w_lstm, step):
            w_xgb = 100 - w_lstm - w_lgb
            weights = {'lstm': w_lstm / 100, 'lgb': w_lgb / 100, 'xgb': w_xgb / 100}
            acc = _accuracy_fast(rooms_data, weights, split='cal')
            if acc > best_acc:
                best_weights, best_acc = weights, acc
    return best_weights, best_acc


def sweep_lstm_weight_curve(rooms_data: list, step: int = 5, split: str = 'cal'):
    """For each LSTM weight level (0%, step%, ..., 100%), find the best
    LGB/XGB split for the REMAINING budget and record accuracy/R²/MAE at
    that best split. Produces one point per LSTM level for a line curve —
    same cached predictions, no retraining, uses the fast (non-threshold-
    search) accuracy so a full sweep stays quick."""
    lstm_pct, accs, r2s, maes = [], [], [], []
    for w_lstm in range(0, 101, step):
        best = None  # (acc, r2, mae)
        for w_lgb in range(0, 101 - w_lstm, step):
            w_xgb = 100 - w_lstm - w_lgb
            weights = {'lstm': w_lstm / 100, 'lgb': w_lgb / 100, 'xgb': w_xgb / 100}
            acc_r2_mae = []
            for d in rooms_data:
                s = d[split]
                blended = weights['lstm'] * s['lstm'] + weights['lgb'] * s['lgb'] + weights['xgb'] * s['xgb']
                blended = np.maximum(0.0, blended)
                cls = F.compute_classification_metrics(s['y'], blended, d['thr_high'], d['thr_med'], d['peak_ref'])
                acc_r2_mae.append((cls['accuracy'], F.r2_score(s['y'], blended), F.mean_absolute_error(s['y'], blended)))
            acc_r2_mae = np.array(acc_r2_mae)
            mean_acc, mean_r2, mean_mae = acc_r2_mae.mean(axis=0)
            if best is None or mean_acc > best[0]:
                best = (mean_acc, mean_r2, mean_mae)
        lstm_pct.append(w_lstm)
        accs.append(best[0])
        r2s.append(best[1])
        maes.append(best[2])
    return {'lstm_pct': lstm_pct, 'accuracy': accs, 'r2': r2s, 'mae': maes}


def plot_weight_sweep_curve(curve: dict, set_name: str, n_rooms: int, png_path: str):
    """3-panel line chart (Accuracy / R² / MAE vs LSTM weight %), styled
    like param_set_val_acc_by_model.png — line + marker, shared grid style."""
    x = curve['lstm_pct']
    panels = [
        ('accuracy', 'Accuracy', '#1f77b4'),
        ('r2', 'R²', '#ff7f0e'),
        ('mae', 'MAE (ชม.)', '#2ca02c'),
    ]
    with plt.style.context({'axes.grid': True, 'grid.alpha': 0.45, 'font.size': 10}):
        fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), dpi=300)
        for ax, (key, label, color) in zip(axes, panels):
            y = curve[key]
            ax.plot(x, y, color=color, linewidth=2.2, marker='o', markersize=4)
            best_i = int(np.argmax(y)) if key != 'mae' else int(np.argmin(y))
            ax.scatter([x[best_i]], [y[best_i]], color='red', s=60, zorder=5, label=f'best: {x[best_i]}% LSTM')
            ax.axvline(20, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='current (20%)')
            ax.set_title(label, fontweight='bold')
            ax.set_xlabel('LSTM Weight (%)')
            ax.set_ylabel(label)
            ax.grid(True, alpha=0.45)
            ax.legend(loc='best', fontsize=8, frameon=True)

        fig.suptitle(
            f'Ensemble Accuracy/R²/MAE vs LSTM Weight — Set {set_name} ({n_rooms} rooms, best LGB/XGB split at each level)',
            fontweight='bold', fontsize=13,
        )
        fig.text(
            0.5, 0.005,
            'No retraining — same saved models, cached predictions. At each LSTM weight level, the LGB/XGB split '
            'shown is whichever performed best (calibration split).',
            ha='center', fontsize=8, style='italic',
        )
        plt.tight_layout(rect=[0, 0.05, 1, 0.93])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)


def bootstrap_weight_stability(rooms_data: list, n_iterations: int = 50, step: int = 10, seed: int = 42):
    """Resample rooms WITH replacement (same size as rooms_data) and re-run
    the grid search each time — entirely on cached predictions, no model
    calls. If the resulting best weight barely moves across resamples, the
    weight the full-data search found is a stable property of these models,
    not a fluke of exactly which 58 rooms happened to be available.
    """
    rng = np.random.default_rng(seed)
    n = len(rooms_data)
    results = []
    for i in range(n_iterations):
        idx = rng.integers(0, n, size=n)
        resampled = [rooms_data[j] for j in idx]
        weights, acc = grid_search_best_fast(resampled, step=step)
        results.append(weights)
        if (i + 1) % 10 == 0 or (i + 1) == n_iterations:
            print(f"   ...bootstrap {i+1}/{n_iterations}", flush=True)
    return results


def plot_comparison(rows, n_rooms, png_path):
    """rows: list of (name, weights_dict, result_dict). Pure plotting — no
    model loading — so the chart can be re-tweaked in seconds from the CSV
    instead of re-running the ~minutes-long model-loading pass."""
    short_labels = ['Equal\nWeight', 'Current\n(Production)', 'Proportional-\nto-Accuracy', 'Grid-Search\nOptimal']
    accs = [res['accuracy'] for _, _, res in rows]
    r2s = [res['r2'] for _, _, res in rows]
    maes = [res['mae'] for _, _, res in rows]
    colors = ['#9e9e9e', '#2b8cbe', '#fdae6b', '#2ca02c']

    with plt.rc_context({'figure.facecolor': 'white', 'axes.facecolor': 'white', 'font.size': 10}):
        fig, axes = plt.subplots(1, 3, figsize=(18, 7.5), dpi=300)

        for ax, values, title, ylabel, higher_better in [
            (axes[0], accs, 'Ensemble Accuracy', 'Accuracy', True),
            (axes[1], r2s, 'Ensemble R²', 'R²', True),
            (axes[2], maes, 'Ensemble MAE', 'MAE (ชม.)', False),
        ]:
            bars = ax.bar(range(len(values)), values, color=colors)
            ax.set_title(title, fontweight='bold', fontsize=12)
            ax.set_ylabel(ylabel)
            ax.set_xticks(range(len(short_labels)))
            ax.set_xticklabels(short_labels, fontsize=9.5)
            top = max(values)
            ax.set_ylim(0, top * 1.18)
            ax.grid(True, alpha=0.3, axis='y')
            best_idx = int(np.argmax(values)) if higher_better else int(np.argmin(values))
            for i, (bar, v) in enumerate(zip(bars, values)):
                weight = 'bold' if i == best_idx else 'normal'
                ax.text(bar.get_x() + bar.get_width() / 2, v + top * 0.02, f'{v:.4f}',
                        ha='center', va='bottom', fontweight=weight, fontsize=9.5)

        fig.suptitle(
            f'Ensemble Weight Scheme Comparison ({n_rooms} rooms, held-out test split)',
            fontweight='bold', fontsize=14, y=0.99,
        )

        # Legend mapping each bar color to its exact weight split — keeps the
        # per-bar x-labels short so they never overlap.
        legend_lines = [
            f"{name}: LSTM {w['lstm']*100:.0f}% / LGB {w['lgb']*100:.0f}% / XGB {w['xgb']*100:.0f}%"
            for name, w, _ in rows
        ]
        handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors]
        fig.legend(
            handles, legend_lines, loc='lower center', ncol=4,
            bbox_to_anchor=(0.5, 0.075), frameon=False, fontsize=9.5,
        )

        caption = (
            'No retraining — same saved LSTM/LightGBM/XGBoost models per room, only the blend weights differ. '
            'Weights were searched/derived on the calibration split; accuracy shown here is scored on the '
            'held-out TEST split (never used for the search) with the same threshold-optimized accuracy used '
            'for "Ensemble Acc" elsewhere in this project, so "Current (production)" should match that number. '
            'Bold value = best in that metric.'
        )
        fig.text(0.5, 0.01, caption, ha='center', va='bottom', fontsize=8.5,
                  style='italic', wrap=True, color='#444444')

        plt.tight_layout(rect=[0, 0.14, 1, 0.95])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)


def replot_from_csv(csv_path, png_path, n_rooms):
    df = pd.read_csv(csv_path)
    rows = []
    for _, r in df.iterrows():
        w = {'lstm': r['LSTM Weight %'] / 100, 'lgb': r['LGB Weight %'] / 100, 'xgb': r['XGB Weight %'] / 100}
        res = {'accuracy': r['Accuracy'], 'r2': r['R2'], 'mae': r['MAE']}
        rows.append((r['Scheme'], w, res))
    plot_comparison(rows, n_rooms, png_path)
    print(f"📄 Re-plotted from CSV: {png_path}")


def run_bootstrap(rooms_data, set_name, n_iterations):
    print(f"\n🎲 Bootstrap stability check — {n_iterations} resamples of {len(rooms_data)} rooms, Set {set_name}")
    results = bootstrap_weight_stability(rooms_data, n_iterations=n_iterations, step=10)

    lstm_pcts = np.array([w['lstm'] * 100 for w in results])
    lgb_pcts = np.array([w['lgb'] * 100 for w in results])
    xgb_pcts = np.array([w['xgb'] * 100 for w in results])

    print("\n📊 Best weight found per resample — spread across all iterations:")
    for name, vals in [('LSTM', lstm_pcts), ('LGB', lgb_pcts), ('XGB', xgb_pcts)]:
        print(f"   {name:5s} mean={vals.mean():5.1f}%  std={vals.std():5.1f}%  "
              f"median={np.median(vals):5.1f}%  range=[{vals.min():.0f}, {vals.max():.0f}]")

    suffix = '' if set_name == 'C' else f'_{set_name}'
    csv_path = os.path.join(METRICS_DIR, f'ensemble_weight_bootstrap{suffix}.csv')
    df = pd.DataFrame({'LSTM %': lstm_pcts, 'LGB %': lgb_pcts, 'XGB %': xgb_pcts})
    df.to_csv(csv_path, index=False)
    print(f"\n📄 Saved: {csv_path}")

    png_path = os.path.join(METRICS_DIR, f'ensemble_weight_bootstrap{suffix}.png')
    with plt.rc_context({'figure.facecolor': 'white', 'axes.facecolor': 'white', 'font.size': 10}):
        fig, ax = plt.subplots(figsize=(9, 6.5), dpi=300)
        box = ax.boxplot(
            [lstm_pcts, lgb_pcts, xgb_pcts],
            tick_labels=['LSTM', 'LGB', 'XGB'],
            patch_artist=True, widths=0.5,
        )
        for patch, color in zip(box['boxes'], ['#1f77b4', '#ff7f0e', '#2ca02c']):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax.set_ylabel('Weight found by grid search (%)')
        ax.set_title(
            f'Weight Stability Across {n_iterations} Bootstrap Resamples — Set {set_name}',
            fontweight='bold', fontsize=13,
        )
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_ylim(-5, 105)
        caption = (
            f'Each box summarizes the accuracy-maximizing weight found by re-running the grid search on '
            f'{n_iterations} bootstrap resamples (rooms sampled with replacement) of the {len(rooms_data)} '
            f'available rooms — no retraining, same cached predictions each time. A narrow box = stable '
            f'weight; a wide box/whiskers = the earlier single-split "optimal" number is sensitive to which '
            f'rooms happen to be in the sample and should not be read as a precise final answer.'
        )
        fig.text(0.5, 0.01, caption, ha='center', va='bottom', fontsize=8, style='italic',
                  wrap=True, color='#444444')
        plt.tight_layout(rect=[0, 0.1, 1, 1])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
    print(f"📄 Saved: {png_path}")


def main():
    # --set {C,D,E}: which param set's saved models to analyze. C (default)
    # is the live production saved_models//saved_meta/; D/E only ever exist
    # in their own archive from the ABCDE experiment run.
    set_name = 'C'
    if '--set' in sys.argv:
        idx = sys.argv.index('--set')
        if len(sys.argv) > idx + 1:
            set_name = sys.argv[idx + 1].strip().upper()
    suffix = '' if set_name == 'C' else f'_{set_name}'
    csv_path = os.path.join(METRICS_DIR, f'ensemble_weight_scheme_comparison{suffix}.csv')
    png_path = os.path.join(METRICS_DIR, f'ensemble_weight_scheme_comparison{suffix}.png')

    if set_name == 'C':
        meta_dir, model_dir = F.META_DIR, F.MODEL_DIR
    else:
        meta_dir = os.path.join(CURRENT_DIR, f'saved_meta_{set_name}_new')
        model_dir = os.path.join(CURRENT_DIR, f'saved_models_{set_name}_new')
        if not os.path.isdir(meta_dir) or not os.path.isdir(model_dir):
            print(f"❌ No archive found for Set {set_name}: expected {meta_dir} and {model_dir}")
            return

    if '--replot' in sys.argv:
        n_rooms = int(sys.argv[sys.argv.index('--replot') + 1]) if len(sys.argv) > sys.argv.index('--replot') + 1 and sys.argv[sys.argv.index('--replot') + 1].isdigit() else 58
        replot_from_csv(csv_path, png_path, n_rooms)
        return

    print("=" * 70)
    print(f"🔍 Ensemble Weight Scheme Comparison (no retraining) — Set {set_name}")
    print("=" * 70)

    # Cache rooms_data (predictions) to disk — the slow part is loading ~60
    # Keras models one at a time, not the arithmetic that follows. Once
    # cached, --bootstrap (or any re-analysis) skips straight to the fast part.
    cache_path = os.path.join(METRICS_DIR, f'.rooms_data_cache_{set_name}.pkl')
    if '--fresh' not in sys.argv and os.path.exists(cache_path):
        print(f"📦 Loading cached predictions: {cache_path}")
        rooms_data = joblib.load(cache_path)
        print(f"   {len(rooms_data)} rooms loaded from cache (use --fresh to rebuild)")
    else:
        raw = load_raw_bookings()
        rooms = list(Room.objects.all())
        all_rooms_daily = build_all_rooms_daily(raw, rooms)

        rooms_data = []
        n_total = len(rooms)
        for i, room in enumerate(rooms, 1):
            d = collect_room_cal_predictions(room, raw, all_rooms_daily, meta_dir=meta_dir, model_dir=model_dir)
            if d is not None:
                rooms_data.append(d)
            if i % 5 == 0 or i == n_total:
                print(f"   ...processed {i}/{n_total} rooms ({i/n_total*100:.0f}%), {len(rooms_data)} usable so far", flush=True)
        print(f"\n📋 Usable rooms (LSTM+LGB+XGB all present): {len(rooms_data)}/{len(rooms)}")
        if rooms_data:
            joblib.dump(rooms_data, cache_path)
            print(f"📦 Cached predictions for reuse: {cache_path}")
    if not rooms_data:
        print("❌ No rooms with all 3 saved models found — nothing to compare.")
        return

    if '--bootstrap' in sys.argv:
        idx = sys.argv.index('--bootstrap')
        n_iter = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 and sys.argv[idx + 1].isdigit() else 50
        run_bootstrap(rooms_data, set_name, n_iter)
        return

    if '--curve' in sys.argv:
        print(f"\n📈 Sweeping LSTM weight 0-100% (best LGB/XGB split at each level)...")
        curve = sweep_lstm_weight_curve(rooms_data, step=5, split='cal')
        suffix = '' if set_name == 'C' else f'_{set_name}'
        curve_png = os.path.join(METRICS_DIR, f'ensemble_weight_curve{suffix}.png')
        plot_weight_sweep_curve(curve, set_name, len(rooms_data), curve_png)
        pd.DataFrame(curve).to_csv(os.path.join(METRICS_DIR, f'ensemble_weight_curve{suffix}.csv'), index=False)
        print(f"📄 Saved: {curve_png}")
        print(f"📄 Saved: {os.path.join(METRICS_DIR, f'ensemble_weight_curve{suffix}.csv')}")
        return

    # Scheme 3: proportional to each model's own SOLO accuracy — derived on
    # the calibration split (search phase; test split stays untouched here)
    solo_lstm = evaluate_scheme(rooms_data, {'lstm': 1, 'lgb': 0, 'xgb': 0}, split='cal')
    solo_lgb = evaluate_scheme(rooms_data, {'lstm': 0, 'lgb': 1, 'xgb': 0}, split='cal')
    solo_xgb = evaluate_scheme(rooms_data, {'lstm': 0, 'lgb': 0, 'xgb': 1}, split='cal')
    total_acc = solo_lstm['accuracy'] + solo_lgb['accuracy'] + solo_xgb['accuracy']
    prop_weights = {
        'lstm': solo_lstm['accuracy'] / total_acc,
        'lgb': solo_lgb['accuracy'] / total_acc,
        'xgb': solo_xgb['accuracy'] / total_acc,
    }
    print(f"\n📊 Solo accuracy (calibration split) — LSTM: {solo_lstm['accuracy']:.4f}  LGB: {solo_lgb['accuracy']:.4f}  XGB: {solo_xgb['accuracy']:.4f}")

    # Scheme 4: exhaustive grid search maximizing blended accuracy — also on
    # the calibration split only, so the test split below is a genuine
    # out-of-sample check, not something the search already saw/tuned to.
    best_weights, _ = grid_search_best(rooms_data, step=5)

    schemes = [
        ('Equal', {'lstm': 1/3, 'lgb': 1/3, 'xgb': 1/3}),
        ('Current (production)', {'lstm': 0.20, 'lgb': 0.40, 'xgb': 0.40}),
        ('Proportional-to-Accuracy', prop_weights),
        ('Grid-Search Optimal', best_weights),
    ]

    # Final reported numbers: evaluated on the TEST split (never used for
    # weight search above) with the same threshold-optimized accuracy used
    # for "Ensemble Acc" elsewhere in the pipeline (hyperparam_comparison.csv,
    # meta.pkl) — so "Current (production)" here should land close to the
    # Ensemble Acc already reported for Set C there, not a different number.
    print("\n📊 Scheme comparison (scored on held-out TEST split):")
    rows = []
    for name, w in schemes:
        res = evaluate_scheme(rooms_data, w, split='test')
        rows.append((name, w, res))
        print(
            f"  {name:28s} LSTM={w['lstm']*100:5.1f}% LGB={w['lgb']*100:5.1f}% XGB={w['xgb']*100:5.1f}%"
            f"  ->  Acc={res['accuracy']:.4f}  R²={res['r2']:.4f}  MAE={res['mae']:.4f}"
        )

    # ── CSV ──────────────────────────────────────────────────────────────
    df = pd.DataFrame([
        {
            'Scheme': name,
            'LSTM Weight %': round(w['lstm'] * 100, 1),
            'LGB Weight %': round(w['lgb'] * 100, 1),
            'XGB Weight %': round(w['xgb'] * 100, 1),
            'Accuracy': round(res['accuracy'], 4),
            'R2': round(res['r2'], 4),
            'MAE': round(res['mae'], 4),
        }
        for name, w, res in rows
    ])
    df.to_csv(csv_path, index=False)
    print(f"\n📄 Saved: {csv_path}")

    # ── PNG ──────────────────────────────────────────────────────────────
    plot_comparison(rows, len(rooms_data), png_path)
    print(f"📄 Saved: {png_path}")
    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
