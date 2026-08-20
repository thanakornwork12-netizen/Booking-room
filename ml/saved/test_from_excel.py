"""
Test-only companion to train_from_excel.py — loads ALREADY-TRAINED model
files (lgb.pkl / xgb.pkl / lstm.keras) saved by that script and evaluates
them against booking_data_test.xlsx. No training happens here at all; this
only rebuilds the same input features train_from_excel.py used (so the
saved models see the same kind of input), then predicts and scores.

Run train_from_excel.py first to produce the model files this script reads.

Usage: python ml/saved/test_from_excel.py [--sets A,B,C]  (default: all 5)
"""
import os, sys

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
import forecast as F
from booking.models import Room

TRAIN_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'booking_data_train.xlsx')
TEST_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'booking_data_test.xlsx')

ROOM_IDS = {
    '2C05-06': 443, '2C09': 445, '2C10-11': 446, '2C16-17': 447,
    '3C05-06': 448, '1C-MEETING': 487, '3C16-17': 505, '4C05': 506,
}

SETS = ['A', 'B', 'C', 'D', 'E']
if '--sets' in sys.argv:
    idx = sys.argv.index('--sets')
    SETS = [s.strip().upper() for s in sys.argv[idx + 1].split(',') if s.strip()]


def to_rdf(df: pd.DataFrame, room_id: int) -> pd.DataFrame:
    out = df.copy()
    out['room_id'] = room_id
    out['duration'] = out['duration_hours']
    out['date'] = pd.to_datetime(out['date']).dt.date
    return out


def rebuild_room_features(code, room_id, train_all, test_all):
    """Reconstruct the exact same daily series / feat_df / train-test
    boundary that train_from_excel.py used — no training, just re-deriving
    the inputs the saved models expect."""
    tr_rows = train_all[train_all['room_code'] == code]
    te_rows = test_all[test_all['room_code'] == code]
    if len(te_rows) == 0:
        return None

    rdf_full = pd.concat([to_rdf(tr_rows, room_id), to_rdf(te_rows, room_id)], ignore_index=True)
    daily_full = F._prepare_daily_series(rdf_full, None, None)
    # Same boundary train_from_excel.py used: length of the train-only daily
    # series REINDEXED over its full date span (including zero-booking days),
    # not just the count of days that happened to have a booking.
    daily_train_only = F._prepare_daily_series(to_rdf(tr_rows, room_id), None, None)
    n_train_days = len(daily_train_only) if daily_train_only is not None else 0

    room = Room.objects.get(id=room_id)
    schedule = F.load_term_schedule(room.id)
    use_log = F._needs_log_transform(room)
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
    return {
        'room': room, 'use_log': use_log, 'feat_df': feat_df, 'train_end': train_end, 'calib_end': calib_end,
        'X_tr': X_tr, 'X_cal': X_cal, 'X_te': X_te, 'y_tr': y_tr, 'y_cal': y_cal, 'y_te': y_te,
    }


def predict_with_saved_model(built, model_dir, room_id, winner):
    """Predict X_te using ONLY the saved model that won this room (per
    ensemble_weights in meta.pkl) — no other model needs loading."""
    room_dir = os.path.join(model_dir, str(room_id))
    X_te = built['X_te']

    if winner in ('lightgbm', 'xgboost'):
        fname = 'lgb.pkl' if winner == 'lightgbm' else 'xgb.pkl'
        model = joblib.load(os.path.join(room_dir, fname))
        # Models are trained on a top-30 feature subset (_select_important_features),
        # not the full ~63-column feature set rebuilt here — must re-slice to match.
        feat_names = getattr(model, 'feature_name_', None)
        if feat_names is None:
            feat_names = getattr(model, 'feature_names_in_', None)
        if feat_names is not None:
            X_te = X_te[list(feat_names)]
        return np.asarray(model.predict(X_te), dtype=float)

    if winner == 'lstm':
        lstm_model = tf.keras.models.load_model(os.path.join(room_dir, 'lstm.keras'), compile=False)
        lstm_scaler = joblib.load(os.path.join(room_dir, 'lstm_scaler.pkl'))
        _, lstm_test = F._collect_lstm_holdout_preds(
            lstm_model, lstm_scaler, built['feat_df'], built['y_tr'], built['y_cal'], built['y_te'],
            built['train_end'],
        )
        return np.asarray(lstm_test, dtype=float) if lstm_test is not None else np.zeros(len(X_te))

    return np.zeros(len(X_te))


train_all = pd.read_excel(TRAIN_XLSX)
test_all = pd.read_excel(TEST_XLSX)
train_all['date'] = pd.to_datetime(train_all['date']).dt.date
test_all['date'] = pd.to_datetime(test_all['date']).dt.date

all_results = []

for set_name in SETS:
    META_DIR = os.path.join(BASE_DIR, 'ml', 'saved', f'saved_meta_{set_name}_excel_split')
    MODEL_DIR = os.path.join(BASE_DIR, 'ml', 'saved', f'saved_models_{set_name}_excel_split')
    if not os.path.isdir(META_DIR):
        print(f"⏭️  Set {set_name}: no trained models found at {META_DIR}, run train_from_excel.py first — skipping")
        continue
    print(f"\n{'=' * 80}\n TESTING SET {set_name} (loading saved models — no training happens here)\n{'=' * 80}", flush=True)

    for code, room_id in ROOM_IDS.items():
        meta_path = os.path.join(META_DIR, f'{room_id}_meta.pkl')
        if not os.path.exists(meta_path):
            print(f"⏭️  {code}: no saved model for this set, skip")
            continue
        meta = joblib.load(meta_path)

        built = rebuild_room_features(code, room_id, train_all, test_all)
        if built is None:
            continue

        weights = meta.get('ensemble_weights', {})
        winner = max(weights, key=weights.get) if weights else 'lightgbm'
        try:
            raw_pred = predict_with_saved_model(built, MODEL_DIR, room_id, winner)
        except Exception as e:
            print(f"⚠️  {code}: saved model doesn't match current features (likely trained before a "
                  f"feature/data change) — retrain this set with train_from_excel.py first. ({e})")
            continue

        use_log = meta.get('use_log', False)
        y_te = built['y_te']
        if use_log:
            y_te_eval = np.expm1(y_te)
            y_pred_eval = np.expm1(np.maximum(0, raw_pred))
        else:
            y_te_eval = y_te.copy()
            y_pred_eval = np.maximum(0, raw_pred)
        y_te_eval = np.nan_to_num(y_te_eval, nan=0.0, posinf=0.0, neginf=0.0)
        y_pred_eval = np.nan_to_num(y_pred_eval, nan=0.0, posinf=0.0, neginf=0.0)
        n = min(len(y_te_eval), len(y_pred_eval))
        y_te_eval, y_pred_eval = y_te_eval[:n], y_pred_eval[:n]

        thr_high, thr_med, peak_ref = meta['thr_high'], meta['thr_med'], meta['peak_ref']
        cls = F.compute_classification_metrics(y_te_eval, y_pred_eval, thr_high, thr_med, peak_ref)
        r2 = F.r2_score(y_te_eval, y_pred_eval)
        mae = F.mean_absolute_error(y_te_eval, y_pred_eval)

        print(
            f"✅ {code:.<18} winner={winner:10s} TestAcc={cls['accuracy']:.3f}  "
            f"F1={cls['f1']:.3f}  R²={r2:.3f}  MAE={mae:.2f}h  (n_test={n})"
        )
        all_results.append({
            'param_set': set_name, 'room': code, 'winner': winner,
            'test_accuracy': cls['accuracy'], 'f1': cls['f1'], 'r2': r2, 'mae': mae, 'n_test': n,
        })

    print(f"✅ DONE SET {set_name}", flush=True)

print("\n\n================ SUMMARY (loaded saved models, scored on booking_data_test.xlsx) ================")
df = pd.DataFrame(all_results)
print(df.to_string(index=False))
out_csv = os.path.join(BASE_DIR, 'ml', 'saved', 'metrics_plots', 'test_only_results.csv')
df.to_csv(out_csv, index=False)
print(f"\n📄 Saved: {out_csv}")
if len(df):
    print("\n📊 Mean test accuracy per set:")
    print(df.groupby('param_set')['test_accuracy'].mean().to_string())
print("\n🏁 ALL SETS TESTED", flush=True)
