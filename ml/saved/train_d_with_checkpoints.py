# ══════════════════════════════════════════════════════════════════════════════
#  Set D, retrained WITH checkpoints — the only way to get a genuine
#  "adaptive weight / accuracy vs training round" curve.
#
#  Why retraining is unavoidable here (unlike every other analysis this
#  session): the saved LSTM only has its FINAL epoch's weights — no
#  intermediate checkpoints were ever kept. LightGBM/XGBoost don't have this
#  problem (their SAVED, already-trained boosters can predict using only the
#  first K trees via num_iteration/iteration_range — no retraining needed for
#  those two), so only the LSTM half of this actually needs a real re-run.
#
#  What this does per room:
#    1. Rebuild the exact same train/cal/test split Set D used.
#    2. Retrain LSTM with the SAME hyperparameters (lookback=70, epochs=70,
#       batch=8) — same architecture, same seed — but save a checkpoint
#       every 10 epochs.
#    3. At each checkpoint epoch K, blend LSTM(K) with LGB/XGB's prediction
#       using only their first K trees (Set D's already-trained boosters,
#       no retraining) — the same "as if training stopped at round K" ensemble.
#    4. Adaptive weight is derived from that checkpoint's calibration
#       predictions and scored on the held-out test split, exactly like
#       analyze_adaptive_weights_all_sets.py — just repeated once per checkpoint.
#
#  Outputs:
#    metrics_plots/d_checkpoint_curve.jsonl   (per-room, per-checkpoint detail)
#    metrics_plots/d_checkpoint_curve.csv     (aggregated per-checkpoint)
#    metrics_plots/d_checkpoint_curve.png     (3-panel epoch curve, Set D only)
#
#  Usage: python ml/saved/train_d_with_checkpoints.py
#  Takes hours — same order of magnitude as the original D training run.
# ══════════════════════════════════════════════════════════════════════════════
import os, sys, json, shutil, warnings, datetime, tempfile

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import numpy as np
import pandas as pd
import joblib
import tensorflow as tf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import forecast as F
from analyze_ensemble_weights import load_raw_bookings, build_all_rooms_daily
from booking.models import Room

METRICS_DIR = F.METRICS_DIR
JSONL_PATH = os.path.join(METRICS_DIR, 'd_checkpoint_curve.jsonl')
CSV_PATH = os.path.join(METRICS_DIR, 'd_checkpoint_curve.csv')
PNG_PATH = os.path.join(METRICS_DIR, 'd_checkpoint_curve.png')

D_META_DIR = os.path.join(CURRENT_DIR, 'saved_meta_D_new')
D_MODEL_DIR = os.path.join(CURRENT_DIR, 'saved_models_D_new')

CHECKPOINT_FREQ = 10
FIXED_WEIGHTS = {'lstm': 0.20, 'lightgbm': 0.40, 'xgboost': 0.40}

# Pin globals to Set D's config — train_lstm() and the feature/split helpers
# all read these as module-level defaults.
_D_CFG = F.PARAM_SETS['D']
F.CURRENT_PARAM_SET = 'D'
F.LSTM_EPOCHS = _D_CFG['lstm_epochs']
F.LSTM_BATCH = _D_CFG['lstm_batch']
F.LSTM_LOOKBACK = _D_CFG['lstm_lookback']
CHECKPOINT_EPOCHS = list(range(CHECKPOINT_FREQ, F.LSTM_EPOCHS + 1, CHECKPOINT_FREQ))
if CHECKPOINT_EPOCHS[-1] != F.LSTM_EPOCHS:
    CHECKPOINT_EPOCHS.append(F.LSTM_EPOCHS)


def list_d_lstm_rooms():
    """Rooms Set D actually trained LSTM for, per its own archived meta —
    same room population as every other Set D analysis this session."""
    rooms_by_id = {r.id: r for r in Room.objects.all()}
    room_ids = []
    for fname in sorted(os.listdir(D_META_DIR)):
        if not fname.endswith('_meta.pkl'):
            continue
        room_id = int(fname.split('_')[0])
        try:
            meta = joblib.load(os.path.join(D_META_DIR, fname))
        except Exception:
            continue
        if isinstance(meta, dict) and meta.get('param_set') == 'D' and meta.get('has_lstm'):
            if room_id in rooms_by_id:
                room_ids.append(room_id)
    return [rooms_by_id[rid] for rid in room_ids]


def process_room(room, raw, all_rooms_daily, jsonl_file):
    meta_path = os.path.join(D_META_DIR, f"{room.id}_meta.pkl")
    meta = joblib.load(meta_path)
    lgb_model = joblib.load(os.path.join(D_MODEL_DIR, str(room.id), 'lgb.pkl'))
    xgb_model = joblib.load(os.path.join(D_MODEL_DIR, str(room.id), 'xgb.pkl'))

    rdf = raw[raw['room_id'] == room.id]
    schedule = F.load_term_schedule(room.id)
    daily = F._prepare_daily_series(rdf, room, all_rooms_daily)
    if daily is None:
        return

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
        return
    X_tr, X_cal, X_te, y_tr, y_cal, y_te, train_end, calib_end = split
    if len(y_cal) == 0 or len(y_te) == 0:
        return

    with tempfile.TemporaryDirectory(prefix=f'd_ckpt_{room.id}_') as ckpt_dir:
        _, scaler, _ = F.train_lstm(
            y_tr, y_cal, lookback=F.LSTM_LOOKBACK, epochs=F.LSTM_EPOCHS, patience=F.LSTM_PATIENCE,
            feat_train_df=feat_df.iloc[:train_end], feat_val_df=feat_df.iloc[train_end:calib_end],
            checkpoint_dir=ckpt_dir, checkpoint_freq=CHECKPOINT_FREQ,
        )
        if scaler is None:
            return

        for k in CHECKPOINT_EPOCHS:
            ckpt_path = os.path.join(ckpt_dir, f'epoch_{k}.keras')
            if not os.path.exists(ckpt_path):
                continue
            ckpt_model = tf.keras.models.load_model(ckpt_path, compile=False)

            lstm_cal, lstm_te = F._collect_lstm_holdout_preds(
                ckpt_model, scaler, feat_df, y_tr, y_cal, y_te, train_end,
            )
            if lstm_cal is None or lstm_te is None or len(lstm_cal) != len(y_cal) or len(lstm_te) != len(y_te):
                continue

            k_lgb = min(k, lgb_model.n_estimators_ if hasattr(lgb_model, 'n_estimators_') else k)
            lgb_cal = np.asarray(lgb_model.predict(X_cal, num_iteration=k), dtype=float)
            lgb_te = np.asarray(lgb_model.predict(X_te, num_iteration=k), dtype=float)
            xgb_cal = np.asarray(xgb_model.predict(X_cal, iteration_range=(0, k)), dtype=float)
            xgb_te = np.asarray(xgb_model.predict(X_te, iteration_range=(0, k)), dtype=float)

            def _finish(y_raw, lstm_p, lgb_p, xgb_p):
                if use_log:
                    y_eval = np.expm1(y_raw)
                    lgb_e, xgb_e = np.expm1(lgb_p), np.expm1(xgb_p)
                    lstm_e = np.expm1(np.asarray(lstm_p, dtype=float))
                else:
                    y_eval, lgb_e, xgb_e = y_raw.copy(), lgb_p, xgb_p
                    lstm_e = np.asarray(lstm_p, dtype=float)
                return (np.nan_to_num(y_eval), np.nan_to_num(lstm_e), np.nan_to_num(lgb_e), np.nan_to_num(xgb_e))

            y_cal_e, lstm_cal_e, lgb_cal_e, xgb_cal_e = _finish(y_cal, lstm_cal, lgb_cal, xgb_cal)
            y_te_e, lstm_te_e, lgb_te_e, xgb_te_e = _finish(y_te, lstm_te, lgb_te, xgb_te)

            adaptive_w = F._derive_ensemble_weights(
                y_cal_e, {'lstm': lstm_cal_e, 'lightgbm': lgb_cal_e, 'xgboost': xgb_cal_e}, primary='lstm',
            )
            adaptive_pred = (
                adaptive_w.get('lstm', 0.0) * lstm_te_e
                + adaptive_w.get('lightgbm', 0.0) * lgb_te_e
                + adaptive_w.get('xgboost', 0.0) * xgb_te_e
            )
            fixed_pred = (
                FIXED_WEIGHTS['lstm'] * lstm_te_e
                + FIXED_WEIGHTS['lightgbm'] * lgb_te_e
                + FIXED_WEIGHTS['xgboost'] * xgb_te_e
            )

            def _metrics(y_true, y_pred):
                y_pred = np.maximum(0.0, y_pred)
                _, cls = F._evaluate_with_best_threshold(y_true, y_pred, meta['thr_high'], meta['thr_med'], meta['peak_ref'])
                return {
                    'accuracy': float(cls['accuracy']), 'loss': float(cls['loss']),
                    'r2': float(F.r2_score(y_true, y_pred)), 'mae': float(F.mean_absolute_error(y_true, y_pred)),
                }

            record = {
                'timestamp': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                'room': room.name, 'checkpoint_epoch': k,
                'adaptive_weights': {kk: round(float(vv), 4) for kk, vv in adaptive_w.items()},
                'metrics': {
                    'lstm': _metrics(y_te_e, lstm_te_e),
                    'fixed_ensemble': _metrics(y_te_e, fixed_pred),
                    'adaptive_ensemble': _metrics(y_te_e, adaptive_pred),
                },
            }
            jsonl_file.write(json.dumps(record, ensure_ascii=False) + '\n')
        jsonl_file.flush()


def plot_checkpoint_curve(jsonl_path, png_path):
    records = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    by_epoch = {}
    for r in records:
        by_epoch.setdefault(r['checkpoint_epoch'], []).append(r)

    epochs = sorted(by_epoch.keys())
    plot_metric_curve(by_epoch, epochs, png_path, metric='accuracy')

    rows = []
    for e in epochs:
        recs = by_epoch[e]
        row = {'checkpoint_epoch': e, 'n_rooms': len(recs)}
        for key in ('fixed_ensemble', 'adaptive_ensemble', 'lstm'):
            row[f'{key}_accuracy'] = round(float(np.mean([r['metrics'][key]['accuracy'] for r in recs])), 4)
            row[f'{key}_loss'] = round(float(np.mean([r['metrics'][key]['loss'] for r in recs])), 4)
        for wkey in ('lstm', 'lightgbm', 'xgboost'):
            row[f'weight_{wkey}_pct'] = round(float(np.mean([r['adaptive_weights'].get(wkey, 0.0) for r in recs])) * 100, 1)
        rows.append(row)
    pd.DataFrame(rows).to_csv(CSV_PATH, index=False)


def plot_metric_curve(by_epoch: dict, epochs: list, png_path: str, metric: str = 'accuracy'):
    """metric='accuracy' -> d_checkpoint_curve.png; metric='loss' -> d_checkpoint_curve_loss.png.
    Pure plotting, reusable for a quick re-plot without retraining."""
    is_loss = metric == 'loss'
    panels = [
        ('fixed_ensemble', 'Fixed Ensemble (20/40/40)', '#9e9e9e'),
        ('adaptive_ensemble', 'Adaptive Ensemble (model decides)', '#2b8cbe'),
    ]

    with plt.style.context({'axes.grid': True, 'grid.alpha': 0.45, 'font.size': 10}):
        fig, axes = plt.subplots(1, 2, figsize=(11, 5.5), dpi=300, sharey=True)
        all_values = []
        for ax, (key, title, color) in zip(axes, panels):
            vals = [np.mean([r['metrics'][key][metric] for r in by_epoch[e]]) for e in epochs]
            all_values.extend(vals)
            ax.plot(epochs, vals, color=color, linewidth=2.5, marker='o', markersize=5)
            ax.set_title(title, fontweight='bold')
            ax.set_xlabel('Epoch / Round')
            ax.grid(True, alpha=0.45)
        if is_loss:
            lo, hi = min(all_values), max(all_values)
            pad = (hi - lo) * 0.1 or 0.1
            for ax in axes:
                ax.set_ylim(max(0, lo - pad), hi + pad)
        else:
            for ax in axes:
                ax.set_ylim(0.0, 1.05)
        axes[0].set_ylabel('Loss (cross-entropy)' if is_loss else 'Ensemble Accuracy')
        fig.suptitle(
            f'Set D: {"Loss" if is_loss else "Accuracy"} vs Training Round (real checkpoints, no retraining trick)',
            fontweight='bold', fontsize=13,
        )
        fig.text(
            0.5, 0.005,
            f'Source: d_checkpoint_curve.jsonl — LSTM retrained with checkpoints every {CHECKPOINT_FREQ} epochs; '
            'LGB/XGB use partial-round prediction on the already-trained Set D boosters (no retraining for those two).',
            ha='center', fontsize=8, style='italic',
        )
        plt.tight_layout(rect=[0, 0.03, 1, 0.93])
        plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)


def main():
    if '--plot' in sys.argv:
        if not os.path.exists(JSONL_PATH):
            print(f"❌ {JSONL_PATH} not found yet — the training run hasn't written any checkpoints.")
            return
        records = []
        with open(JSONL_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        by_epoch = {}
        for r in records:
            by_epoch.setdefault(r['checkpoint_epoch'], []).append(r)
        epochs = sorted(by_epoch.keys())
        print(f"📋 {len(records)} records across {len(epochs)} checkpoint epoch(s): {epochs}")
        plot_metric_curve(by_epoch, epochs, PNG_PATH, metric='accuracy')
        print(f"📄 Saved: {PNG_PATH}")
        loss_png = os.path.join(METRICS_DIR, 'd_checkpoint_curve_loss.png')
        plot_metric_curve(by_epoch, epochs, loss_png, metric='loss')
        print(f"📄 Saved: {loss_png}")
        return

    print("=" * 70)
    print(f"🔍 Set D — retrain with checkpoints every {CHECKPOINT_FREQ} epochs (up to {F.LSTM_EPOCHS})")
    print("=" * 70)

    rooms = list_d_lstm_rooms()
    print(f"📋 {len(rooms)} rooms with LSTM in Set D's archive")
    if not rooms:
        print("❌ No rooms found — is saved_meta_D_new/ present?")
        return

    raw = load_raw_bookings()
    all_rooms = list(Room.objects.all())
    all_rooms_daily = build_all_rooms_daily(raw, all_rooms)

    with open(JSONL_PATH, 'a', encoding='utf-8') as jsonl_file:
        for i, room in enumerate(rooms, 1):
            print(f"[{i}/{len(rooms)}] {room.name}", flush=True)
            try:
                process_room(room, raw, all_rooms_daily, jsonl_file)
            except Exception as e:
                print(f"   ⚠️  failed: {e}")

    print(f"\n📄 Per-checkpoint detail: {JSONL_PATH}")
    plot_checkpoint_curve(JSONL_PATH, PNG_PATH)
    print(f"📄 Saved: {CSV_PATH}")
    print(f"📄 Saved: {PNG_PATH}")

    records = []
    with open(JSONL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    by_epoch = {}
    for r in records:
        by_epoch.setdefault(r['checkpoint_epoch'], []).append(r)
    loss_png = os.path.join(METRICS_DIR, 'd_checkpoint_curve_loss.png')
    plot_metric_curve(by_epoch, sorted(by_epoch.keys()), loss_png, metric='loss')
    print(f"📄 Saved: {loss_png}")
    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
