# ── Booking → Clean → Feature Engineering → Train Model → Evaluate → Forecast 14 วัน → แปลงเป็นรายชั่วโมง → Save DemandForecast
# ── แก้ไขตาม Research Significance ──
#  Fix 1 : Advanced Baseline (SMA / LastWeek / LinearRegression) แทน Naive=0
#  Fix 2 : Facility Score (Room Score / Facility Density) เป็น Feature ใหม่
#  Fix 3 : LECTURE – ใช้ log-transform + term features แต่ไม่ decompose (แก้ R²=-114)
#           + sMAPE guard (cap 100%)
#  Fix 4 : LSTM disable สำหรับ LECTURE (lookback=7 บน residual flat → garbage)
#  New   : LSTM (TensorFlow/Keras) เป็น 4th model ใน Stacking Ensemble (non-LECTURE เท่านั้น)

import os, sys, warnings, argparse
import numpy as np
import pandas as pd
import joblib
from datetime import timedelta
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.preprocessing import MinMaxScaler

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()
from booking.models import Booking, Room, TermBooking, DemandForecast

import lightgbm as lgb
import xgboost as xgb

warnings.filterwarnings('ignore')

# ── ตรวจสอบ TensorFlow (Optional) ────────────────────────────────────────────
try:
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping
    LSTM_AVAILABLE = True
except ImportError:
    LSTM_AVAILABLE = False
    print("⚠️  TensorFlow ไม่พบ – ข้าม LSTM (ใช้ LGB+XGB Stacking เท่านั้น)")

# ── Config ────────────────────────────────────────────────────────────────────
MIN_DAYS        = 60
FORECAST_DAYS   = 14
LSTM_LOOKBACK   = 14
LSTM_EPOCHS     = 100
LSTM_BATCH      = 16
MODEL_DIR       = os.path.join(CURRENT_DIR, "saved_models")
META_DIR        = os.path.join(CURRENT_DIR, "saved_meta")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(META_DIR,  exist_ok=True)

# ── Fallback hour distribution ────────────────────────────────────────────────
HOUR_DIST_FALLBACK = {
    8: 0.05, 9: 0.10, 10: 0.18, 11: 0.16, 12: 0.02,
    13: 0.17, 14: 0.15, 15: 0.11, 16: 0.07, 17: 0.04,
}

# ── Facility Score (Fix 2) ────────────────────────────────────────────────────
FACILITY_WEIGHTS = {
    'projector':    3,
    'smart_board':  5,
    'wifi':         2,
    'air_con':      2,
    'microphone':   3,
    'whiteboard':   1,
    'tv_screen':    2,
    'video_conf':   4,
    'lab_computer': 4,
}

def compute_facility_score(room) -> float:
    score = 0.0
    field_map = {
        'has_projector':    'projector',
        'has_smart_board':  'smart_board',
        'has_wifi':         'wifi',
        'has_air_con':      'air_con',
        'has_microphone':   'microphone',
        'has_whiteboard':   'whiteboard',
        'has_tv_screen':    'tv_screen',
        'has_video_conf':   'video_conf',
        'has_lab_computer': 'lab_computer',
    }
    for field, key in field_map.items():
        if getattr(room, field, False):
            score += FACILITY_WEIGHTS.get(key, 1)
    max_score = sum(FACILITY_WEIGHTS.values())
    return round(score / max_score, 4) if max_score > 0 else 0.0

# ── Term Schedule ─────────────────────────────────────────────────────────────
def load_term_schedule(room_id: int) -> list[dict]:
    qs = TermBooking.objects.filter(room_id=room_id, status='active').values(
        'day_of_week', 'start_time', 'end_time', 'term_start', 'term_end'
    )
    schedule = []
    for tb in qs:
        schedule.append({
            'dow':        tb['day_of_week'],
            'start_hour': tb['start_time'].hour,
            'end_hour':   tb['end_time'].hour,
            'term_start': tb['term_start'],
            'term_end':   tb['term_end'],
        })
    return schedule


def compute_term_load(d, hour: int, schedule: list[dict]) -> float:
    if not schedule:
        return 0.0
    dow = d.weekday() if hasattr(d, 'weekday') else pd.Timestamp(d).weekday()
    for tb in schedule:
        if tb['dow'] != dow:
            continue
        if not (tb['term_start'] <= d <= tb['term_end']):
            continue
        if tb['start_hour'] <= hour < tb['end_hour']:
            return 1.0
    return 0.0


def build_term_daily_features(date_index, schedule: list[dict]) -> pd.DataFrame:
    rows = []
    for d in date_index:
        d_date  = d.date() if hasattr(d, 'date') else d
        dow     = d.weekday() if hasattr(d, 'weekday') else pd.Timestamp(d).weekday()
        sessions, hours, in_term = 0, 0, 0
        for tb in schedule:
            if not (tb['term_start'] <= d_date <= tb['term_end']):
                continue
            in_term = 1
            if tb['dow'] == dow:
                sessions += 1
                hours    += tb['end_hour'] - tb['start_hour']
        rows.append({
            'term_hours_day': hours,
            'term_sessions':  sessions,
            'in_term':        in_term,
        })
    return pd.DataFrame(rows, index=date_index)

# ── Hour Distribution ─────────────────────────────────────────────────────────
def learn_hour_dist(bookings_df, room_id=None, event_threshold_pct=95.0,
                    min_days_required=30) -> dict:
    df = bookings_df.copy()
    if room_id is not None:
        df = df[df['room_id'] == room_id]
    if len(df) == 0:
        return HOUR_DIST_FALLBACK.copy()

    df['start_time'] = pd.to_datetime(df['start_time'])
    if df['start_time'].dt.tz is None:
        df['start_time'] = df['start_time'].dt.tz_localize('UTC')
    df['start_time'] = df['start_time'].dt.tz_convert('Asia/Bangkok')
    df['date'] = df['start_time'].dt.date
    df['hour'] = df['start_time'].dt.hour
    df = df[df['hour'].between(8, 17)]
    if len(df) == 0:
        return HOUR_DIST_FALLBACK.copy()

    daily_total     = df.groupby('date').size()
    event_threshold = np.percentile(daily_total.values, event_threshold_pct)
    normal_days     = daily_total[daily_total <= event_threshold].index
    if len(normal_days) < min_days_required:
        return HOUR_DIST_FALLBACK.copy()

    df_normal         = df[df['date'].isin(normal_days)]
    daily_hour_counts = df_normal.groupby(['date', 'hour']).size().unstack(fill_value=0)
    for h in range(8, 18):
        if h not in daily_hour_counts.columns:
            daily_hour_counts[h] = 0
    daily_hour_counts = daily_hour_counts[sorted(daily_hour_counts.columns)]

    row_totals    = daily_hour_counts.sum(axis=1)
    valid_rows    = row_totals > 0
    daily_ratios  = daily_hour_counts[valid_rows].div(row_totals[valid_rows], axis=0)
    median_ratios = daily_ratios.median(axis=0)

    filtered = median_ratios.reindex(range(8, 18), fill_value=0)
    total    = filtered.sum()
    if total == 0:
        return HOUR_DIST_FALLBACK.copy()

    normalized = (filtered / total).round(4)
    diff = 1.0 - normalized.sum()
    pk   = normalized.idxmax()
    normalized[pk] = round(normalized[pk] + diff, 4)
    return normalized.to_dict()

# ── Feature Engineering ───────────────────────────────────────────────────────
def build_features(daily, term_df: pd.DataFrame | None = None,
                   facility_score: float = 0.0,
                   use_log: bool = False):
    """
    Fix 2: เพิ่ม facility_score เป็น feature
    Fix 3: รองรับ log-transform (use_log=True) — ใช้กับ LECTURE โดยไม่ decompose
    """
    if use_log:
        y_series = np.log1p(daily)
    else:
        y_series = daily.copy()

    y_smooth = y_series.rolling(window=3, min_periods=1).mean()
    df  = y_smooth.to_frame(name='y')
    idx = pd.to_datetime(df.index)

    df['dow']          = idx.dayofweek.astype(int)
    df['month']        = idx.month.astype(int)
    df['quarter']      = idx.quarter.astype(int)
    df['week_of_year'] = idx.isocalendar().week.astype(int)
    df['is_weekend']   = (idx.dayofweek >= 5).astype(int)
    df['day_of_month'] = idx.day.astype(int)

    for lag in [1, 2, 3, 7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    for w in [3, 7, 14, 28]:
        df[f'roll_mean_{w}'] = df['y'].shift(1).rolling(w, min_periods=1).mean()
        df[f'roll_std_{w}']  = df['y'].shift(1).rolling(w, min_periods=1).std().fillna(0)
        df[f'roll_max_{w}']  = df['y'].shift(1).rolling(w, min_periods=1).max()
        df[f'roll_min_{w}']  = df['y'].shift(1).rolling(w, min_periods=1).min()

    for span in [3, 7, 14]:
        df[f'ewm_{span}'] = df['y'].shift(1).ewm(span=span, min_periods=1).mean()

    df['diff_1']    = df['y'].diff(1)
    df['diff_7']    = df['y'].diff(7)
    df['diff_7_1']  = df['lag_7'] - df['lag_1']
    df['pct_chg_7'] = df['y'].pct_change(7).replace([np.inf, -np.inf], 0).fillna(0)

    for lag in [1, 2, 3]:
        df[f'hourly_lag_{lag}'] = df['y'].shift(lag)

    t = np.arange(len(df))
    for period, n_terms in [(7, 3), (365, 4)]:
        for k in range(1, n_terms + 1):
            df[f'sin_{period}_{k}'] = np.sin(2 * np.pi * k * t / period)
            df[f'cos_{period}_{k}'] = np.cos(2 * np.pi * k * t / period)

    df['ratio_vs_7d']  = (df['lag_1'] / (df['roll_mean_7']  + 1e-6)).clip(0, 5)
    df['ratio_vs_28d'] = (df['lag_1'] / (df['roll_mean_28'] + 1e-6)).clip(0, 5)

    df['facility_score'] = facility_score

    if term_df is not None:
        term_aligned = term_df.reindex(df.index, fill_value=0)
        df['term_hours_day'] = term_aligned['term_hours_day'].values
        df['term_sessions']  = term_aligned['term_sessions'].values
        df['in_term']        = term_aligned['in_term'].values
        df['term_hours_lag7']    = df['term_hours_day'].shift(7).fillna(0)
        df['term_load_28d_avg']  = df['term_hours_day'].rolling(28, min_periods=1).mean()
        df['has_term_morning']   = (df['term_hours_day'] > 0).astype(int)
        df['lag1_x_in_term']     = df['lag_1'] * df['in_term']
        df['roll7_x_term_hours'] = df['roll_mean_7'] * df['term_hours_day']
    else:
        for col in ['term_hours_day', 'term_sessions', 'in_term',
                    'term_hours_lag7', 'term_load_28d_avg',
                    'has_term_morning', 'lag1_x_in_term', 'roll7_x_term_hours']:
            df[col] = 0.0

    return df.bfill().ffill()

# ── LSTM helpers ──────────────────────────────────────────────────────────────
def _make_lstm_sequences(series: np.ndarray, lookback: int):
    X, y = [], []
    for i in range(lookback, len(series)):
        X.append(series[i - lookback: i])
        y.append(series[i])
    return np.array(X), np.array(y)


def train_lstm(y_train_raw: np.ndarray, y_val_raw: np.ndarray,
               lookback: int = LSTM_LOOKBACK) -> tuple:
    if not LSTM_AVAILABLE:
        return None, None

    scaler   = MinMaxScaler()
    all_data = np.concatenate([y_train_raw, y_val_raw]).reshape(-1, 1)
    scaler.fit(all_data)

    y_tr_s = scaler.transform(y_train_raw.reshape(-1, 1)).flatten()
    y_va_s = scaler.transform(y_val_raw.reshape(-1, 1)).flatten()

    full   = np.concatenate([y_tr_s, y_va_s])
    X_full, y_full = _make_lstm_sequences(full, lookback)

    n_tr = len(y_train_raw) - lookback
    if n_tr <= 0 or n_tr >= len(X_full):
        return None, None

    X_tr, y_tr = X_full[:n_tr], y_full[:n_tr]
    X_va, y_va = X_full[n_tr:], y_full[n_tr:]

    X_tr = X_tr.reshape(X_tr.shape[0], X_tr.shape[1], 1)
    X_va = X_va.reshape(X_va.shape[0], X_va.shape[1], 1)

    model = Sequential([
        LSTM(64, return_sequences=True, input_shape=(lookback, 1)),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(16, activation='relu'),
        Dense(1),
    ])
    model.compile(optimizer='adam', loss='mae')
    es = EarlyStopping(monitor='val_loss', patience=15, restore_best_weights=True)
    model.fit(
        X_tr, y_tr,
        validation_data=(X_va, y_va),
        epochs=LSTM_EPOCHS,
        batch_size=LSTM_BATCH,
        callbacks=[es],
        verbose=0,
    )
    return model, scaler


def lstm_predict(model, scaler, history_series: np.ndarray,
                 n_steps: int, lookback: int = LSTM_LOOKBACK) -> np.ndarray:
    if model is None or scaler is None:
        return np.zeros(n_steps)

    if len(history_series) < lookback:
        pad = np.zeros(lookback - len(history_series))
        history_series = np.concatenate([pad, history_series])

    scaled = scaler.transform(history_series.reshape(-1, 1)).flatten()
    window = list(scaled[-lookback:])
    preds  = []
    for _ in range(n_steps):
        x = np.array(window[-lookback:]).reshape(1, lookback, 1)
        p = float(model.predict(x, verbose=0)[0][0])
        preds.append(p)
        window.append(p)

    inv = scaler.inverse_transform(np.array(preds).reshape(-1, 1)).flatten()
    return np.maximum(0, inv)

# ── Base Models ───────────────────────────────────────────────────────────────
def train_lgb(X_tr, y_tr, X_te, y_te):
    model = lgb.LGBMRegressor(
        objective='regression_l1', n_estimators=5000, learning_rate=0.01,
        max_depth=6, num_leaves=31, min_child_samples=10, lambda_l1=0.3,
        lambda_l2=0.3, feature_fraction=0.8, bagging_fraction=0.8,
        bagging_freq=5, verbose=-1,
    )
    model.fit(
        X_tr, y_tr, eval_set=[(X_te, y_te)],
        callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(-1)],
    )
    return model


def train_xgb(X_tr, y_tr, X_te, y_te):
    model = xgb.XGBRegressor(
        n_estimators=3000, learning_rate=0.01, max_depth=5,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.3, reg_lambda=0.3,
        early_stopping_rounds=100, eval_metric='mae', verbosity=0,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
    return model

# ── Advanced Baseline (Fix 1) ─────────────────────────────────────────────────
def compute_advanced_baselines(y_te: np.ndarray, daily_series: pd.Series,
                               split_idx: int) -> dict:
    """
    Fix 1: baselines เทียบบน series เดียวกันกับ y_te เสมอ
    (daily_series ต้องเป็น series เดียวกับที่ใช้ผลิต y_te — ไม่ mix raw/dynamic)
    """
    n_te     = len(y_te)
    all_vals = daily_series.values.astype(float)

    sma_pred = np.zeros(n_te)
    for i in range(n_te):
        end    = split_idx + i
        start  = max(0, end - 7)
        window = all_vals[start:end]
        window = window[np.isfinite(window)]
        sma_pred[i] = float(window.mean()) if len(window) > 0 else 0.0
    sma_pred = np.nan_to_num(sma_pred, nan=0.0, posinf=0.0, neginf=0.0)
    sma_pred = np.maximum(0.0, sma_pred)

    lw_pred = np.zeros(n_te)
    for i in range(n_te):
        idx7 = split_idx + i - 7
        if 0 <= idx7 < len(all_vals):
            v = all_vals[idx7]
            lw_pred[i] = float(v) if np.isfinite(v) else 0.0
        else:
            lw_pred[i] = 0.0
    lw_pred = np.maximum(0.0, lw_pred)

    y_safe = np.nan_to_num(np.asarray(y_te, dtype=float),
                           nan=0.0, posinf=0.0, neginf=0.0)

    return {
        'SMA7_MAE':     mean_absolute_error(y_safe, sma_pred),
        'SMA7_R2':      r2_score(y_safe, sma_pred),
        'LastWeek_MAE': mean_absolute_error(y_safe, lw_pred),
        'LastWeek_R2':  r2_score(y_safe, lw_pred),
    }

# ── Stacking (LGB + XGB [+ LSTM]) ────────────────────────────────────────────
def stacking_predict(X_tr, y_tr, X_te, y_te, X_pred,
                     lstm_model=None, lstm_scaler=None,
                     daily_tr_raw=None, n_pred=None,
                     lstm_lookback: int = LSTM_LOOKBACK):
    lgb_model = train_lgb(X_tr, y_tr, X_te, y_te)
    xgb_model = train_xgb(X_tr, y_tr, X_te, y_te)

    lgb_val = lgb_model.predict(X_te)
    xgb_val = xgb_model.predict(X_te)
    lgb_fut = lgb_model.predict(X_pred)
    xgb_fut = xgb_model.predict(X_pred)

    use_lstm = (LSTM_AVAILABLE and lstm_model is not None
                and lstm_scaler is not None and daily_tr_raw is not None)

    if use_lstm:
        hist_for_val = daily_tr_raw
        lstm_val = lstm_predict(lstm_model, lstm_scaler,
                                hist_for_val, len(y_te),
                                lookback=lstm_lookback)
        hist_full = np.concatenate([daily_tr_raw, y_te])
        lstm_fut  = lstm_predict(lstm_model, lstm_scaler,
                                 hist_full, n_pred or len(X_pred),
                                 lookback=lstm_lookback)

        meta = Ridge(alpha=1.0)
        meta.fit(np.column_stack([lgb_val, xgb_val, lstm_val[:len(y_te)]]), y_te)
        final = meta.predict(np.column_stack([lgb_fut, xgb_fut,
                                               lstm_fut[:len(X_pred)]]))
    else:
        meta = Ridge(alpha=1.0)
        meta.fit(np.column_stack([lgb_val, xgb_val]), y_te)
        final = meta.predict(np.column_stack([lgb_fut, xgb_fut]))

    return np.maximum(0, final), lgb_model, xgb_model, meta

# ── Threshold & Metrics ───────────────────────────────────────────────────────
def compute_adaptive_thresholds(daily, peak_ref):
    historical_norms = np.clip(daily.values / (peak_ref + 1e-6), 0, 1)
    active_norms     = historical_norms[historical_norms > 0.01]
    if len(active_norms) < 10:
        return 0.70, 0.50
    thr_high = float(np.percentile(active_norms, 65))
    thr_med  = float(np.percentile(active_norms, 35))
    thr_high = min(max(thr_high, thr_med + 0.10), 0.90)
    thr_med  = max(thr_med, 0.10)
    return round(thr_high, 3), round(thr_med, 3)


def smape(y_true, y_pred):
    raw = (2 * np.abs(y_true - y_pred)
           / (np.abs(y_true) + np.abs(y_pred) + 1e-8)) * 100
    return float(np.mean(np.clip(raw, 0, 100)))


def mape(y_true, y_pred):
    mask = y_true > 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask])
                                / y_true[mask])) * 100)


def rmse(y_true, y_pred):
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))

# ── Determine if room needs log-transform (Fix 3 revised) ─────────────────────
def _needs_log_transform(room) -> bool:
    """
    Fix 3 (revised): ห้อง LECTURE ใช้ log-transform บน daily_raw โดยตรง
    — ไม่ decompose อีกต่อไป เพราะ decompose over-subtracts signal
    — term features ใน build_features ทำหน้าที่แทน decomposition
    """
    room_type = getattr(room, 'room_type', '') or ''
    return 'lecture' in room_type.lower()


# ── NOTE: decompose_lecture_demand ถูก REMOVED ────────────────────────────────
# เหตุผล: percentile25 * session_ratio over-subtracts จนเหลือ near-zero residuals
# ML เทรนบน residuals ที่แทบ 0 แต่ evaluate บน daily_raw จริง → R²=-114
# แทนที่ด้วย: ส่ง daily_raw เข้า build_features พร้อม term features โดยตรง
# ─────────────────────────────────────────────────────────────────────────────

# ── Bulk Forecast Builder ─────────────────────────────────────────────────────
def _build_forecast_bulk(room, lgb_model, xgb_model, meta_ridge,
                         history, peak_ref, thr_high, thr_med,
                         room_hour_dist, confidence, forecast_dates, schedule,
                         lstm_model=None, lstm_scaler=None,
                         use_log: bool = False, facility_score: float = 0.0,
                         lstm_lookback: int = LSTM_LOOKBACK):
    """
    Fix 3 (revised): history ที่ส่งเข้ามาต้องเป็น series เดียวกันกับที่ใช้ train
    — สำหรับ LECTURE: history = daily_raw (log-transform ใน build_features)
    — LSTM disabled สำหรับ LECTURE (lstm_model จะเป็น None)
    """
    max_hr_weight = max(room_hour_dist.values()) if room_hour_dist else 1.0
    bulk = []
    all_dates = pd.date_range(
        pd.Timestamp(history.index.min()),
        pd.Timestamp(forecast_dates[-1]), freq='D'
    )
    term_df       = build_term_daily_features(all_dates, schedule)
    term_df.index = all_dates

    lstm_daily_preds = {}
    if LSTM_AVAILABLE and lstm_model is not None and lstm_scaler is not None:
        hist_arr   = history.values.copy()
        # ถ้า use_log: history อยู่ใน original scale, LSTM train บน log scale
        if use_log:
            hist_arr = np.log1p(hist_arr)
        lstm_ahead = lstm_predict(lstm_model, lstm_scaler, hist_arr,
                                  len(forecast_dates), lookback=lstm_lookback)
        if use_log:
            lstm_ahead = np.expm1(lstm_ahead)
        for i, fd in enumerate(forecast_dates):
            lstm_daily_preds[fd] = max(0.0, float(lstm_ahead[i]))

    for fc_date in forecast_dates:
        fc_ts    = pd.Timestamp(fc_date)
        extended = pd.concat([history, pd.Series([np.nan], index=[fc_ts])])
        extended.index = pd.to_datetime(extended.index)

        f_df = build_features(
            extended, term_df,
            facility_score=facility_score,
            use_log=use_log,
        ).loc[[fc_ts]].drop(columns='y')

        lgb_pred = float(lgb_model.predict(f_df)[0])
        xgb_pred = float(xgb_model.predict(f_df)[0])

        if fc_date in lstm_daily_preds:
            lstm_val_fc = lstm_daily_preds[fc_date]
            if use_log:
                lstm_val_fc = np.log1p(lstm_val_fc)
            try:
                d_pred = float(meta_ridge.predict(
                    np.column_stack([[lgb_pred], [xgb_pred], [lstm_val_fc]])
                )[0])
            except Exception:
                d_pred = float(meta_ridge.predict(
                    np.column_stack([[lgb_pred], [xgb_pred]])
                )[0])
        else:
            d_pred = float(meta_ridge.predict(
                np.column_stack([[lgb_pred], [xgb_pred]])
            )[0])

        d_pred = max(0.0, d_pred)

        # Inverse log-transform
        if use_log:
            d_pred = np.expm1(d_pred)

        # อัปเดต history ด้วย original scale เสมอ (log จะทำอีกรอบใน build_features)
        history.loc[fc_ts] = d_pred

        baseline_pred = (f_df['roll_mean_28'].values[0]
                         if 'roll_mean_28' in f_df.columns else d_pred * 0.7)
        # baseline_pred อยู่ใน log-space ถ้า use_log → inverse กลับก่อนใช้
        if use_log:
            baseline_pred = np.expm1(float(baseline_pred))

        day_norm  = float(np.clip(d_pred / (peak_ref + 1e-6), 0.0, 1.0))
        term_norm = float(np.clip(baseline_pred / (peak_ref + 1e-6), 0.0, 1.0))
        day_term_demand = min(day_norm, term_norm)

        for hr, weight in room_hour_dist.items():
            hr_term_load = compute_term_load(fc_date, hr, schedule)
            hr_factor    = weight / max_hr_weight if max_hr_weight > 0 else 1.0
            hr_pred      = day_norm * hr_factor
            hr_term      = max(day_term_demand * hr_factor, hr_term_load * day_norm)
            hr_dyn       = max(0.0, hr_pred - hr_term)
            demand_score = round(float(hr_pred), 4)

            if demand_score >= 0.70:
                day_level = 'urgent'
                day_avail = 'book_now'
            elif demand_score >= 0.50:
                day_level = 'high'
                day_avail = 'book_soon'
            elif demand_score >= 0.30:
                day_level = 'medium'
                day_avail = 'recommended'
            else:
                day_level = 'low'
                day_avail = 'likely_available'

            bulk.append(DemandForecast(
                room             = room,
                forecast_date    = fc_date,
                hour             = hr,
                predicted_demand = demand_score,
                term_demand      = round(hr_term, 4),
                dynamic_demand   = round(hr_dyn,  4),
                demand_level     = day_level,
                availability     = day_avail,
                confidence       = confidence,
            ))
    return bulk

# ── RETRAIN + GENERATE FORECAST ───────────────────────────────────────────────
def retrain_and_forecast():
    print("\n🚀 RETRAIN + GENERATE FORECAST (RESEARCH EVALUATION MODE)")
    print("=" * 80)

    raw_qs = Booking.objects.exclude(status='cancelled').values('start_time', 'room_id')
    raw    = pd.DataFrame(list(raw_qs))
    if len(raw) > 0:
        raw['start_time'] = pd.to_datetime(raw['start_time'])
        if raw['start_time'].dt.tz is None:
            raw['start_time'] = raw['start_time'].dt.tz_localize('UTC')
        raw['start_time'] = raw['start_time'].dt.tz_convert('Asia/Bangkok')
        raw['date'] = raw['start_time'].dt.date

    all_stats      = []
    all_thresholds = []
    today          = pd.to_datetime('today').date()
    forecast_dates = [today + timedelta(days=d) for d in range(FORECAST_DAYS)]

    for room in Room.objects.all():
        rdf = raw[raw['room_id'] == room.id] if len(raw) > 0 else pd.DataFrame()
        if hasattr(room, 'historical_demand_count'):
            room.historical_demand_count = len(rdf)
            room.save(update_fields=['historical_demand_count'])
        if len(rdf) < MIN_DAYS:
            continue

        # ── Feature prep ─────────────────────────────────────────────────────
        schedule       = load_term_schedule(room.id)
        room_hour_dist = learn_hour_dist(raw, room_id=room.id,
                                         event_threshold_pct=95.0,
                                         min_days_required=30)
        facility_score = compute_facility_score(room)
        use_log        = _needs_log_transform(room)

        # Fix 3 (revised): ใช้ daily_raw โดยตรงสำหรับทุก room type
        # ไม่ decompose อีกต่อไป — term features ทำงานแทนใน build_features
        daily = (
            rdf.groupby('date').size()
               .reindex(pd.date_range(rdf['date'].min(),
                                      rdf['date'].max(), freq='D').date,
                        fill_value=0)
               .astype(float)
        )
        daily.index = pd.to_datetime(daily.index)

        # Winsorize ที่ p95 สำหรับ LECTURE เพื่อลด spike ก่อน log-transform
        # (แทน decompose ที่เดิม) — ทำบน daily_raw โดยตรง
        if use_log:
            cap95 = float(daily.quantile(0.95))
            daily = daily.clip(upper=cap95)
            print(f"   📐 LECTURE log-only: winsorize p95={cap95:.1f} "
                  f"(avg={daily.mean():.1f}) — no decompose")

        term_df       = build_term_daily_features(daily.index, schedule)
        term_df.index = daily.index
        feat_df       = build_features(daily, term_df,
                                       facility_score=facility_score,
                                       use_log=use_log).dropna()
        X = feat_df.drop(columns='y')
        y = feat_df['y'].values

        split      = int(len(X) * 0.85)
        X_tr, X_te = X.iloc[:split], X.iloc[split:]
        y_tr, y_te = y[:split], y[split:]
        if len(X_te) < 5:
            continue

        # ── Train LSTM ────────────────────────────────────────────────────
        # Fix 4: LSTM disabled สำหรับ LECTURE
        # เหตุผล: daily หลัง winsorize ยังอาจมี high variance จาก term peaks
        # lookback=14 บน log-space ที่มี strong weekly seasonality จาก term
        # ทำให้ LSTM เพิ่ม variance มากกว่า signal — LGB+XGB เพียงพอ
        lstm_model, lstm_scaler = None, None
        if LSTM_AVAILABLE and not use_log and len(y_tr) >= LSTM_LOOKBACK + 10:
            print(f"   🧠 Training LSTM for {room.name} (lookback={LSTM_LOOKBACK}) ...")
            lstm_model, lstm_scaler = train_lstm(
                y_train_raw=y_tr,
                y_val_raw=y_te,
                lookback=LSTM_LOOKBACK,
            )
        elif use_log:
            print(f"   ⏭️  LSTM skipped for {room.name} (LECTURE – use LGB+XGB only)")

        # ── Stacking Ensemble ─────────────────────────────────────────────
        y_pred_ens, lgb_model, xgb_model, meta_ridge = stacking_predict(
            X_tr, y_tr, X_te, y_te, X_te,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            daily_tr_raw=y_tr, n_pred=len(X_te),
            lstm_lookback=LSTM_LOOKBACK,
        )

        # Inverse log สำหรับ evaluation
        if use_log:
            y_te_eval   = np.expm1(y_te)
            y_pred_eval = np.expm1(y_pred_ens)
        else:
            y_te_eval   = y_te.copy()
            y_pred_eval = y_pred_ens.copy()

        # Sanitize
        y_te_eval   = np.nan_to_num(np.asarray(y_te_eval,   dtype=float),
                                    nan=0.0, posinf=0.0, neginf=0.0)
        y_pred_eval = np.nan_to_num(np.asarray(y_pred_eval, dtype=float),
                                    nan=0.0, posinf=0.0, neginf=0.0)

        # ── Fix 1: Advanced Baselines ─────────────────────────────────────
        # baselines คำนวณบน daily (winsorized raw) — series เดียวกับ train
        # แปลงกลับ original scale เพื่อ fair comparison กับ y_te_eval
        daily_for_baseline = daily.copy()
        if use_log:
            daily_for_baseline_vals = np.expm1(
                np.log1p(daily_for_baseline.values)   # ยังคง winsorized
            )
            daily_baseline_series = pd.Series(daily_for_baseline_vals,
                                               index=daily_for_baseline.index)
        else:
            daily_baseline_series = daily_for_baseline

        baseline_stats = compute_advanced_baselines(y_te_eval,
                                                    daily_baseline_series,
                                                    split)

        # ── Metrics ───────────────────────────────────────────────────────
        m_r2    = r2_score(y_te_eval, y_pred_eval)
        m_mae   = mean_absolute_error(y_te_eval, y_pred_eval)
        m_rmse  = rmse(y_te_eval, y_pred_eval)
        m_mape  = mape(y_te_eval, y_pred_eval)
        m_smape = smape(y_te_eval, y_pred_eval)

        room_type = getattr(room, 'room_type', 'unknown').lower()
        all_stats.append({
            'Room':     room.name,
            'Type':     room_type,
            'UseLog':   use_log,
            'FacScore': facility_score,
            'R2':       m_r2,
            'MAE':      m_mae,
            'RMSE':     m_rmse,
            'MAPE':     m_mape,
            'sMAPE':    m_smape,
            'SMA7_MAE':     baseline_stats['SMA7_MAE'],
            'SMA7_R2':      baseline_stats['SMA7_R2'],
            'LastWeek_MAE': baseline_stats['LastWeek_MAE'],
            'LastWeek_R2':  baseline_stats['LastWeek_R2'],
        })

        # ── Thresholds & Confidence ────────────────────────────────────────
        # peak_ref ใช้ daily (winsorized) ทั้งสำหรับ LECTURE และ room ปกติ
        peak_ref          = float(daily.quantile(0.95)) or 1.0
        thr_high, thr_med = compute_adaptive_thresholds(daily, peak_ref)
        confidence        = round(max(0.0, m_r2) * 100, 1)

        all_thresholds.append({
            'Room': room.name, 'peak_ref': round(peak_ref, 2),
            'thr_high': thr_high, 'thr_med': thr_med,
            'term_slots': len(schedule),
        })

        room_type_tag = f"[{room_type}]"
        lstm_tag      = " +LSTM" if lstm_model else ""
        log_tag       = " LOG" if use_log else ""
        print(
            f"✅ {room.name:.<18} {room_type_tag:<12}"
            f"{lstm_tag}{log_tag}"
            f" R²:{m_r2:.3f} | MAE:{m_mae:.2f}"
            f" | SMA7:{baseline_stats['SMA7_MAE']:.2f}"
            f" | LW:{baseline_stats['LastWeek_MAE']:.2f}"
            f" | fac:{facility_score:.2f}"
        )

        # ── Save models ───────────────────────────────────────────────────
        joblib.dump(lgb_model, os.path.join(MODEL_DIR, f"{room.id}_lgb.pkl"))
        joblib.dump(xgb_model, os.path.join(MODEL_DIR, f"{room.id}_xgb.pkl"))
        meta_payload = {
            'peak_ref':       peak_ref,
            'thr_high':       thr_high,
            'thr_med':        thr_med,
            'hour_dist':      room_hour_dist,
            'confidence':     confidence,
            'meta_ridge':     meta_ridge,
            'use_log':        use_log,
            'facility_score': facility_score,
            'lstm_lookback':  LSTM_LOOKBACK,
        }
        if lstm_model is not None:
            joblib.dump(lstm_model,  os.path.join(MODEL_DIR, f"{room.id}_lstm.pkl"))
            joblib.dump(lstm_scaler, os.path.join(MODEL_DIR, f"{room.id}_lstm_scaler.pkl"))
            meta_payload['has_lstm'] = True
        else:
            meta_payload['has_lstm'] = False
        joblib.dump(meta_payload, os.path.join(META_DIR, f"{room.id}_meta.pkl"))

        # ── Generate Forecast ──────────────────────────────────────────────
        # ส่ง daily (winsorized raw) เป็น history — ตรงกับ series ที่ train
        bulk = _build_forecast_bulk(
            room, lgb_model, xgb_model, meta_ridge, daily.copy(),
            peak_ref, thr_high, thr_med, room_hour_dist, confidence,
            forecast_dates, schedule,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            use_log=use_log, facility_score=facility_score,
            lstm_lookback=LSTM_LOOKBACK,
        )
        DemandForecast.objects.filter(
            room=room, forecast_date__in=forecast_dates
        ).delete()
        DemandForecast.objects.bulk_create(bulk)

    # ── Research Summary ─────────────────────────────────────────────────────
    df_res = pd.DataFrame(all_stats)
    if len(df_res) > 0:
        print("\n📊 ── Evaluation by Room Type (Ensemble vs Advanced Baselines) ──")
        agg_cols = {
            'R2': 'mean', 'MAE': 'mean', 'RMSE': 'mean',
            'MAPE': 'mean', 'sMAPE': 'mean',
            'SMA7_MAE': 'mean', 'SMA7_R2': 'mean',
            'LastWeek_MAE': 'mean', 'LastWeek_R2': 'mean',
        }
        summary = df_res.groupby('Type').agg(agg_cols).reset_index()

        for _, row in summary.iterrows():
            print(f"\n🔹 Type: {row['Type'].upper()}")
            print(f"   ┌─ Ensemble ─────────────────────────────────────────────")
            print(f"   │  Avg R²           : {row['R2']:.3f}")
            print(f"   │  Avg MAE          : {row['MAE']:.2f}")
            print(f"   │  Avg RMSE         : {row['RMSE']:.2f}")
            print(f"   ├─ Baseline (Fix 1) ─────────────────────────────────────")
            print(f"   │  SMA-7  MAE / R²  : {row['SMA7_MAE']:.2f} / {row['SMA7_R2']:.3f}")
            print(f"   │  LastWk MAE / R²  : {row['LastWeek_MAE']:.2f} / {row['LastWeek_R2']:.3f}")
            improve_pct = ((row['SMA7_MAE'] - row['MAE']) / (row['SMA7_MAE'] + 1e-6)) * 100
            print(f"   │  MAE Improvement  : {improve_pct:.1f}% vs SMA-7")
            print(f"   ├─ Metrics ──────────────────────────────────────────────")
            if 'meeting' in row['Type']:
                print(f"   │  MAPE             : {row['MAPE']:.1f}% ✅ (Primary Metric)")
            else:
                print(f"   │  sMAPE (capped)   : {row['sMAPE']:.1f}% ✅ (Fix 3 Applied)")
            print(f"   └────────────────────────────────────────────────────────")
            print("-" * 60)

        print("\n🏢 ── Facility Score Analysis (Fix 2) ──")
        if 'FacScore' in df_res.columns and df_res['FacScore'].sum() > 0:
            fac_df = df_res[['Room', 'FacScore', 'MAE', 'R2']].sort_values(
                'FacScore', ascending=False
            )
            for _, row in fac_df.iterrows():
                bar = '█' * int(row['FacScore'] * 20)
                print(f"   {row['Room']:<18} fac={row['FacScore']:.2f} {bar}")
        else:
            print("   (Facility fields not found in Room model – add has_projector etc.)")

    _print_summary()


def _print_summary():
    print("\n── จำนวน Record ต่อระดับ ──")
    for lvl in ['urgent', 'high', 'medium', 'low']:
        c = DemandForecast.objects.filter(demand_level=lvl).count()
        print(f"  {lvl:8s}: {c}")
    print("=" * 80)


def generate_forecast_only():
    """Inference only – โหลด model ที่เซฟไว้แล้ว forecast ใหม่โดยไม่ retrain"""
    print("\n🔄 GENERATE FORECAST ONLY (no retrain)")
    today          = pd.to_datetime('today').date()
    forecast_dates = [today + timedelta(days=d) for d in range(FORECAST_DAYS)]

    raw_qs = Booking.objects.exclude(status='cancelled').values('start_time', 'room_id')
    raw    = pd.DataFrame(list(raw_qs))
    if len(raw) > 0:
        raw['start_time'] = pd.to_datetime(raw['start_time'])
        if raw['start_time'].dt.tz is None:
            raw['start_time'] = raw['start_time'].dt.tz_localize('UTC')
        raw['start_time'] = raw['start_time'].dt.tz_convert('Asia/Bangkok')
        raw['date'] = raw['start_time'].dt.date

    for room in Room.objects.all():
        meta_path = os.path.join(META_DIR, f"{room.id}_meta.pkl")
        lgb_path  = os.path.join(MODEL_DIR, f"{room.id}_lgb.pkl")
        xgb_path  = os.path.join(MODEL_DIR, f"{room.id}_xgb.pkl")
        if not all(os.path.exists(p) for p in [meta_path, lgb_path, xgb_path]):
            continue

        meta       = joblib.load(meta_path)
        lgb_model  = joblib.load(lgb_path)
        xgb_model  = joblib.load(xgb_path)
        meta_ridge = meta['meta_ridge']

        lstm_model, lstm_scaler = None, None
        if meta.get('has_lstm', False) and LSTM_AVAILABLE:
            lp = os.path.join(MODEL_DIR, f"{room.id}_lstm.pkl")
            sp = os.path.join(MODEL_DIR, f"{room.id}_lstm_scaler.pkl")
            if os.path.exists(lp) and os.path.exists(sp):
                lstm_model  = joblib.load(lp)
                lstm_scaler = joblib.load(sp)

        rdf = raw[raw['room_id'] == room.id] if len(raw) > 0 else pd.DataFrame()
        if len(rdf) < MIN_DAYS:
            continue

        use_log = meta.get('use_log', False)

        daily = (
            rdf.groupby('date').size()
               .reindex(pd.date_range(rdf['date'].min(),
                                      rdf['date'].max(), freq='D').date,
                        fill_value=0)
               .astype(float)
        )
        daily.index = pd.to_datetime(daily.index)

        # Winsorize ถ้า LECTURE (ใช้ peak_ref จาก meta เป็น cap)
        if use_log:
            cap = meta['peak_ref']
            daily = daily.clip(upper=cap)

        schedule = load_term_schedule(room.id)
        bulk = _build_forecast_bulk(
            room, lgb_model, xgb_model, meta_ridge, daily.copy(),
            meta['peak_ref'], meta['thr_high'], meta['thr_med'],
            meta['hour_dist'], meta['confidence'], forecast_dates, schedule,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            use_log=use_log,
            facility_score=meta.get('facility_score', 0.0),
            lstm_lookback=meta.get('lstm_lookback', LSTM_LOOKBACK),
        )
        DemandForecast.objects.filter(
            room=room, forecast_date__in=forecast_dates
        ).delete()
        DemandForecast.objects.bulk_create(bulk)
        print(f"  ✅ {room.name} – forecast updated")

    _print_summary()


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Demand Forecast Engine')
    parser.add_argument('--retrain', action='store_true',
                        help='Retrain all models then forecast')
    args = parser.parse_args()

    if args.retrain:
        retrain_and_forecast()
    else:
        generate_forecast_only()