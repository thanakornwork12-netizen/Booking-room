"""Adaptive vs Fixed ensemble comparison, using TODAY's excel-split models
(saved_meta_{SET}_excel_split / saved_models_{SET}_excel_split) — NOT the
old saved_meta_*_new archive that analyze_adaptive_weights_all_sets.py reads
(that one is frozen/protected and predates today's fixes).

"Adaptive" here = what the current system actually ships: winner-take-all
per room (100% to whichever of LGB/XGB the CV selection in forecast.py
picked — that's what ensemble_weights in meta.pkl already records, and
matches test_from_excel.py's reported TestAcc exactly).
"Fixed" = a naive 20% LSTM / 40% LGB / 40% XGB blend for every room,
computed by loading and predicting with all 3 saved models (LSTM falls
back to 0% with weight redistributed to LGB/XGB 50/50 if no LSTM model
was saved for that room).

No retraining — only loads already-saved model files and predicts.

Usage: python ml/saved/build_adaptive_vs_fixed_current.py
"""
import os, sys, warnings
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

BASE_DIR = '/Users/macthanakorn/room_booking'
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')
import django
django.setup()
from django.conf import settings
settings.DATABASES['default']['OPTIONS'] = {'sslmode': 'disable'}
from django.db import connections
connections['default'].close()

sys.path.insert(0, os.path.join(BASE_DIR, 'ml', 'saved'))
import numpy as np
import pandas as pd
import joblib
import tensorflow as tf
import matplotlib
matplotlib.use('Agg')

import forecast as F
from param_sets import PARAM_SETS
from booking.models import Room
from analyze_adaptive_weights_all_sets import plot_table

METRICS_DIR = F.METRICS_DIR
TRAIN_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'booking_data_train.xlsx')
TEST_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'booking_data_test.xlsx')
OUT_PNG = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_by_set copy.png')
OUT_CSV = os.path.join(METRICS_DIR, 'adaptive_vs_fixed_by_set_current.csv')

ROOM_IDS = {
    '2C05-06': 443, '2C09': 445, '2C10-11': 446, '2C16-17': 447,
    '3C05-06': 448, '1C-MEETING': 487, '3C16-17': 505, '4C05': 506,
}
SETS = ['A', 'B', 'C', 'D', 'E']
FIXED_WEIGHTS = {'lstm': 0.20, 'lightgbm': 0.40, 'xgboost': 0.40}


def to_rdf(df, room_id):
    out = df.copy()
    out['room_id'] = room_id
    out['duration'] = out['duration_hours']
    out['date'] = pd.to_datetime(out['date']).dt.date
    return out


def rebuild(code, room_id, train_all, test_all):
    tr = train_all[train_all['room_code'] == code]
    te = test_all[test_all['room_code'] == code]
    if len(te) == 0:
        return None
    rdf_full = pd.concat([to_rdf(tr, room_id), to_rdf(te, room_id)], ignore_index=True)
    daily_full = F._prepare_daily_series(rdf_full, None, None)
    daily_train_only = F._prepare_daily_series(to_rdf(tr, room_id), None, None)
    n_train_days = len(daily_train_only) if daily_train_only is not None else 0
    room = Room.objects.get(id=room_id)
    schedule = F.load_term_schedule(room.id)
    return daily_full, n_train_days, room, schedule


def predict_all_models(built, model_dir, room_id, use_log, meta):
    daily_full, n_train_days, room, schedule = built
    cap95 = float(daily_full.quantile(0.95)) or 1.0
    daily_clipped = daily_full.clip(upper=cap95)
    term_df = F.build_term_daily_features(daily_clipped.index, schedule)
    term_df.index = daily_clipped.index
    feat_df = F.build_features(daily_clipped, term_df, use_log=use_log).dropna()

    calib_len = max(1, int(round(n_train_days * 0.125)))
    train_end = max(n_train_days - calib_len, F.MIN_TRAIN_ROWS)
    calib_end = min(n_train_days, len(feat_df) - 1)
    train_end = min(train_end, calib_end)

    X = feat_df.drop(columns='y')
    y = feat_df['y'].values
    X_tr, X_cal, X_te = X.iloc[:train_end], X.iloc[train_end:calib_end], X.iloc[calib_end:]
    y_tr, y_cal, y_te = y[:train_end], y[train_end:calib_end], y[calib_end:]

    room_dir = os.path.join(model_dir, str(room_id))
    preds = {}
    selected_feat_names = None
    for name, fname in [('lightgbm', 'lgb.pkl'), ('xgboost', 'xgb.pkl')]:
        path = os.path.join(room_dir, fname)
        if not os.path.exists(path):
            continue
        model = joblib.load(path)
        feat_names = getattr(model, 'feature_name_', None)
        if feat_names is None:
            feat_names = getattr(model, 'feature_names_in_', None)
        if feat_names is not None:
            selected_feat_names = list(feat_names)
        X_te_sel = X_te[list(feat_names)] if feat_names is not None else X_te
        preds[name] = np.asarray(model.predict(X_te_sel), dtype=float)

    lstm_path = os.path.join(room_dir, 'lstm.keras')
    if os.path.exists(lstm_path):
        try:
            lstm_model = tf.keras.models.load_model(lstm_path, compile=False)
            lstm_scaler = joblib.load(os.path.join(room_dir, 'lstm_scaler.pkl'))
            # LSTM was trained on the same top-30 selected feature subset as
            # LGB/XGB (feature selection happens once, before all 3 models
            # train) — feed it the same subset here, or its scaler rejects
            # the full ~65-column feat_df with a shape mismatch.
            feat_df_for_lstm = feat_df[selected_feat_names + ['y']] if selected_feat_names else feat_df
            _, lstm_test = F._collect_lstm_holdout_preds(
                lstm_model, lstm_scaler, feat_df_for_lstm, y_tr, y_cal, y_te, train_end,
            )
            if lstm_test is not None:
                preds['lstm'] = np.asarray(lstm_test, dtype=float)
        except Exception as e:
            print(f"    LSTM predict failed for room {room_id}: {e}")

    return preds, y_te


def to_eval_scale(arr, use_log):
    if use_log:
        return np.expm1(np.maximum(0, arr))
    return np.maximum(0, arr)


def process_set(set_name):
    train_all = pd.read_excel(TRAIN_XLSX)
    test_all = pd.read_excel(TEST_XLSX)
    train_all['date'] = pd.to_datetime(train_all['date']).dt.date
    test_all['date'] = pd.to_datetime(test_all['date']).dt.date

    META_DIR = os.path.join(BASE_DIR, 'ml', 'saved', f'saved_meta_{set_name}_excel_split')
    MODEL_DIR = os.path.join(BASE_DIR, 'ml', 'saved', f'saved_models_{set_name}_excel_split')
    if not os.path.isdir(META_DIR):
        print(f"skip {set_name}: no {META_DIR}")
        return None

    # LSTM sequence shape depends on lookback, which differs per param set
    # (20/40/60/70/90 for A-E) — must match what that set's models were
    # actually trained with, or _collect_lstm_holdout_preds silently builds
    # wrong-shaped input and prediction fails.
    F.LSTM_LOOKBACK = PARAM_SETS[set_name]['lstm_lookback']

    per_room = {'lstm': [], 'lightgbm': [], 'xgboost': [], 'fixed_ensemble': [], 'adaptive_ensemble': []}
    n_rooms = 0
    adaptive_weight_sum = {'lstm': 0.0, 'lightgbm': 0.0, 'xgboost': 0.0}

    for code, room_id in ROOM_IDS.items():
        meta_path = os.path.join(META_DIR, f'{room_id}_meta.pkl')
        if not os.path.exists(meta_path):
            continue
        meta = joblib.load(meta_path)
        use_log = meta.get('use_log', False)
        built = rebuild(code, room_id, train_all, test_all)
        if built is None:
            continue
        try:
            preds, y_te = predict_all_models(built, MODEL_DIR, room_id, use_log, meta)
        except Exception as e:
            print(f"  {set_name}/{code}: skip ({e})")
            continue
        if 'lightgbm' not in preds and 'xgboost' not in preds:
            continue

        y_te_eval = to_eval_scale(y_te, use_log)
        thr_high, thr_med, peak_ref = meta['thr_high'], meta['thr_med'], meta['peak_ref']

        def score(pred_raw):
            pred_eval = to_eval_scale(pred_raw, use_log)
            n = min(len(y_te_eval), len(pred_eval))
            cls = F.compute_classification_metrics(y_te_eval[:n], pred_eval[:n], thr_high, thr_med, peak_ref)
            r2 = F.r2_score(y_te_eval[:n], pred_eval[:n])
            mae = F.mean_absolute_error(y_te_eval[:n], pred_eval[:n])
            rmse = F.rmse(y_te_eval[:n], pred_eval[:n])
            smape = F.smape(y_te_eval[:n], pred_eval[:n])
            return {'accuracy': cls['accuracy'], 'loss': cls['loss'], 'r2': r2, 'mae': mae, 'rmse': rmse, 'smape': smape}

        NEUTRAL = {'accuracy': 0.0, 'loss': 0.0, 'r2': 0.0, 'mae': 0.0, 'rmse': 0.0, 'smape': 0.0}
        for name in ('lstm', 'lightgbm', 'xgboost'):
            per_room[name].append(score(preds[name]) if name in preds else NEUTRAL)

        # Fixed 20/40/40 (redistribute LSTM's share to LGB/XGB if no LSTM saved)
        active = {k: v for k, v in FIXED_WEIGHTS.items() if k in preds}
        wsum = sum(active.values())
        active = {k: v / wsum for k, v in active.items()} if wsum > 0 else active
        n = min(len(preds[k]) for k in active) if active else 0
        fixed_pred = sum(active[k] * preds[k][:n] for k in active) if active else np.zeros_like(y_te)
        per_room['fixed_ensemble'].append(score(fixed_pred))

        # Adaptive: winner-take-all, exactly matching what the saved
        # ensemble_weights says the current system actually serves.
        weights = meta.get('ensemble_weights', {}) or {}
        winner = max(weights, key=weights.get) if weights else ('lightgbm' if 'lightgbm' in preds else 'xgboost')
        adaptive_pred = preds.get(winner, preds.get('lightgbm', preds.get('xgboost')))
        per_room['adaptive_ensemble'].append(score(adaptive_pred))
        for k in adaptive_weight_sum:
            adaptive_weight_sum[k] += weights.get(k, 0.0)
        n_rooms += 1

    if n_rooms == 0:
        return None

    def mean_of(key, field):
        vals = [m[field] for m in per_room[key]]
        return float(np.mean(vals)) if vals else 0.0

    weight_pcts_raw = {k: adaptive_weight_sum[k] / n_rooms * 100 for k in adaptive_weight_sum}

    return {
        'Set': set_name,
        'Rooms': n_rooms,
        'R2 (adaptive)': round(mean_of('adaptive_ensemble', 'r2'), 4),
        'MAE (adaptive)': round(mean_of('adaptive_ensemble', 'mae'), 4),
        'RMSE (adaptive)': round(mean_of('adaptive_ensemble', 'rmse'), 4),
        'sMAPE (adaptive)': round(mean_of('adaptive_ensemble', 'smape'), 2),
        'LSTM Acc': round(mean_of('lstm', 'accuracy'), 4),
        'LGB Acc': round(mean_of('lightgbm', 'accuracy'), 4),
        'XGB Acc': round(mean_of('xgboost', 'accuracy'), 4),
        'Fixed Ensemble Acc (20/40/40)': round(mean_of('fixed_ensemble', 'accuracy'), 4),
        'Adaptive Ensemble Acc': round(mean_of('adaptive_ensemble', 'accuracy'), 4),
        'Fixed Ensemble Loss (20/40/40)': round(mean_of('fixed_ensemble', 'loss'), 4),
        'Adaptive Ensemble Loss': round(mean_of('adaptive_ensemble', 'loss'), 4),
        'Mean Adaptive Weight LSTM %': round(weight_pcts_raw['lstm'], 1),
        'Mean Adaptive Weight LGB %': round(weight_pcts_raw['lightgbm'], 1),
        'Mean Adaptive Weight XGB %': round(weight_pcts_raw['xgboost'], 1),
    }


def main():
    rows = []
    for s in SETS:
        print(f"Processing Set {s}...")
        r = process_set(s)
        if r:
            rows.append(r)
            print(f"  -> Fixed={r['Fixed Ensemble Acc (20/40/40)']:.4f}  Adaptive={r['Adaptive Ensemble Acc']:.4f}")
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
