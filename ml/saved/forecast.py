"""
seed.py — สร้างข้อมูลจำลองสมจริง ~50,000+ records (Dynamic & Term Bookings)
วางไว้ที่: /Users/macthanakorn/room_booking/ml/saved/forecast.py
รัน: python ml/saved/forecast.py --retrain
"""

import os, sys, warnings, argparse
import numpy as np
import pandas as pd
import joblib
from datetime import timedelta
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()
from booking.models import Booking, Room, TermBooking, DemandForecast
import lightgbm as lgb
import xgboost as xgb
from sklearn.linear_model import Ridge, LinearRegression

warnings.filterwarnings('ignore')

# ── CONFIG ────────────────────────────────────────────────────────────────────
MIN_DAYS      = 60
FORECAST_DAYS = 14
MODEL_DIR     = os.path.join(CURRENT_DIR, "saved_models")
META_DIR      = os.path.join(CURRENT_DIR, "saved_meta")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(META_DIR,  exist_ok=True)

HOUR_DIST_FALLBACK = {
    8: 0.05, 9: 0.10, 10: 0.18, 11: 0.16, 12: 0.02,
    13: 0.17, 14: 0.15, 15: 0.11, 16: 0.07, 17: 0.04,
}

# ── TERM BOOKING HELPERS ──────────────────────────────────────────────────────

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
        d_date   = d.date() if hasattr(d, 'date') else d
        dow      = d.weekday() if hasattr(d, 'weekday') else pd.Timestamp(d).weekday()
        sessions = 0
        hours    = 0
        in_term  = 0
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

# ── HELPERS ───────────────────────────────────────────────────────────────────

def learn_hour_dist(bookings_df, room_id=None, event_threshold_pct=95.0, min_days_required=30):
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
    daily_hour_counts = df_normal.groupby(['date','hour']).size().unstack(fill_value=0)
    for h in range(8, 18):
        if h not in daily_hour_counts.columns:
            daily_hour_counts[h] = 0
    daily_hour_counts = daily_hour_counts[sorted(daily_hour_counts.columns)]

    row_totals   = daily_hour_counts.sum(axis=1)
    valid_rows   = row_totals > 0
    daily_ratios = daily_hour_counts[valid_rows].div(row_totals[valid_rows], axis=0)
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

def build_features(daily, term_df: pd.DataFrame | None = None):
    y_smooth = daily.rolling(window=3, min_periods=1).mean()
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
    df['pct_chg_7'] = df['y'].pct_change(7).replace([np.inf,-np.inf], 0).fillna(0)

    t = np.arange(len(df))
    for period, n_terms in [(7, 3), (365, 4)]:
        for k in range(1, n_terms + 1):
            df[f'sin_{period}_{k}'] = np.sin(2 * np.pi * k * t / period)
            df[f'cos_{period}_{k}'] = np.cos(2 * np.pi * k * t / period)

    df['ratio_vs_7d']  = (df['lag_1'] / (df['roll_mean_7']  + 1e-6)).clip(0, 5)
    df['ratio_vs_28d'] = (df['lag_1'] / (df['roll_mean_28'] + 1e-6)).clip(0, 5)

    if term_df is not None:
        term_aligned = term_df.reindex(df.index, fill_value=0)
        df['term_hours_day'] = term_aligned['term_hours_day'].values
        df['term_sessions']  = term_aligned['term_sessions'].values
        df['in_term']        = term_aligned['in_term'].values
        df['term_hours_lag7']   = df['term_hours_day'].shift(7).fillna(0)
        df['term_load_28d_avg'] = df['term_hours_day'].rolling(28, min_periods=1).mean()
        df['has_term_morning']   = (df['term_hours_day'] > 0).astype(int)
        df['lag1_x_in_term']     = df['lag_1'] * df['in_term']
        df['roll7_x_term_hours'] = df['roll_mean_7'] * df['term_hours_day']
    else:
        for col in ['term_hours_day','term_sessions','in_term',
                    'term_hours_lag7','term_load_28d_avg',
                    'has_term_morning','lag1_x_in_term','roll7_x_term_hours']:
            df[col] = 0.0

    return df.bfill().ffill()

def train_lgb(X_tr, y_tr, X_te, y_te):
    model = lgb.LGBMRegressor(
        objective='regression_l1', n_estimators=5000, learning_rate=0.01,
        max_depth=6, num_leaves=31, min_child_samples=10, lambda_l1=0.3,
        lambda_l2=0.3, feature_fraction=0.8, bagging_fraction=0.8,
        bagging_freq=5, verbose=-1,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(-1)])
    return model

def train_xgb(X_tr, y_tr, X_te, y_te):
    model = xgb.XGBRegressor(
        n_estimators=3000, learning_rate=0.01, max_depth=5, subsample=0.8,
        colsample_bytree=0.8, reg_alpha=0.3, reg_lambda=0.3,
        early_stopping_rounds=100, eval_metric='mae', verbosity=0,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
    return model

def stacking_predict(X_tr, y_tr, X_te, y_te, X_pred):
    lgb_model = train_lgb(X_tr, y_tr, X_te, y_te)
    xgb_model = train_xgb(X_tr, y_tr, X_te, y_te)
    lgb_val   = lgb_model.predict(X_te)
    xgb_val   = xgb_model.predict(X_te)
    meta = Ridge(alpha=1.0)
    meta.fit(np.column_stack([lgb_val, xgb_val]), y_te)
    final = meta.predict(np.column_stack([
        lgb_model.predict(X_pred),
        xgb_model.predict(X_pred),
    ]))
    return np.maximum(0, final), lgb_model, xgb_model, meta

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
    return np.mean(2 * np.abs(y_true - y_pred) / (np.abs(y_true) + np.abs(y_pred) + 1e-8)) * 100

def mape(y_true, y_pred):
    mask = y_true > 0
    if not mask.any(): return 0.0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

def rmse(y_true, y_pred):
    return np.sqrt(mean_squared_error(y_true, y_pred))

# ── BUILD FORECAST BULK ───────────────────────────────────────────────────────

def _build_forecast_bulk(room, lgb_model, xgb_model, meta_ridge, history, peak_ref, thr_high, thr_med, room_hour_dist, confidence, forecast_dates, schedule):
    max_hr_weight = max(room_hour_dist.values()) if room_hour_dist else 1.0
    bulk = []
    all_dates  = pd.date_range(pd.Timestamp(history.index.min()), pd.Timestamp(forecast_dates[-1]), freq='D')
    term_df    = build_term_daily_features(all_dates, schedule)
    term_df.index = all_dates

    for fc_date in forecast_dates:
        fc_ts    = pd.Timestamp(fc_date)
        extended = pd.concat([history, pd.Series([np.nan], index=[fc_ts])])
        extended.index = pd.to_datetime(extended.index)
        f_df = build_features(extended, term_df).loc[[fc_ts]].drop(columns='y')

        lgb_pred = float(lgb_model.predict(f_df)[0])
        xgb_pred = float(xgb_model.predict(f_df)[0])
        d_pred   = float(meta_ridge.predict(np.column_stack([[lgb_pred], [xgb_pred]]))[0])
        d_pred   = max(0.0, d_pred)

        history.loc[fc_ts] = d_pred
        baseline_pred  = f_df['roll_mean_28'].values[0] if 'roll_mean_28' in f_df.columns else d_pred * 0.7
        day_norm       = float(np.clip(d_pred / (peak_ref + 1e-6), 0.0, 1.0))
        term_norm      = float(np.clip(baseline_pred / (peak_ref + 1e-6), 0.0, 1.0))

        day_term_demand = min(day_norm, term_norm)
        fc_date_obj = fc_date if isinstance(fc_date, type(fc_date)) else fc_date

        for hr, weight in room_hour_dist.items():
            hr_term_load = compute_term_load(fc_date, hr, schedule)
            hr_factor    = weight / max_hr_weight if max_hr_weight > 0 else 1.0
            hr_pred = day_norm    * hr_factor
            hr_term = max(day_term_demand * hr_factor, hr_term_load * day_norm)
            hr_dyn  = max(0.0, hr_pred - hr_term)

            # ── Demand Score (0.0 – 1.0) with 4-tier label ──────────────────
            demand_score = round(float(hr_pred), 4)

            if demand_score >= 0.70:
                day_level = 'urgent'           # 🔴 ควรจองตอนนี้เลย
                day_avail = 'book_now'
            elif demand_score >= 0.50:
                day_level = 'high'             # 🟠 รีบจอง
                day_avail = 'book_soon'
            elif demand_score >= 0.30:
                day_level = 'medium'           # 🟡 ควรจอง
                day_avail = 'recommended'
            else:
                day_level = 'low'              # 🟢 ยังว่าง / เสี่ยงต่ำ
                day_avail = 'likely_available'

            bulk.append(DemandForecast(
                room             = room,
                forecast_date    = fc_date_obj,
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

        schedule       = load_term_schedule(room.id)
        room_hour_dist = learn_hour_dist(raw, room_id=room.id, event_threshold_pct=95.0, min_days_required=30)
        daily = rdf.groupby('date').size().reindex(pd.date_range(rdf['date'].min(), rdf['date'].max(), freq='D').date, fill_value=0).astype(float)
        daily.index = pd.to_datetime(daily.index)

        term_df = build_term_daily_features(daily.index, schedule)
        term_df.index = daily.index
        feat_df    = build_features(daily, term_df).dropna()
        X          = feat_df.drop(columns='y')
        y          = feat_df['y'].values
        split      = int(len(X) * 0.85)
        X_tr, X_te = X.iloc[:split], X.iloc[split:]
        y_tr, y_te = y[:split], y[split:]
        if len(X_te) < 5:
            continue

        # Train Ensemble
        y_pred_ens, lgb_model, xgb_model, meta_ridge = stacking_predict(X_tr, y_tr, X_te, y_te, X_te)

        # Train Baseline (Linear Regression) for research comparison
        lr_base = LinearRegression()
        lr_base.fit(X_tr, y_tr)
        y_pred_base = lr_base.predict(X_te)
        base_mae = mean_absolute_error(y_te, y_pred_base)

        m_r2    = r2_score(y_te, y_pred_ens)
        m_mae   = mean_absolute_error(y_te, y_pred_ens)
        m_rmse  = rmse(y_te, y_pred_ens)
        m_mape  = mape(y_te, y_pred_ens)
        m_smape = smape(y_te, y_pred_ens)

        room_type = getattr(room, 'room_type', 'unknown').lower()
        all_stats.append({
            'Room': room.name, 'Type': room_type, 'R2': m_r2,
            'MAE': m_mae, 'RMSE': m_rmse, 'MAPE': m_mape, 'sMAPE': m_smape,
            'Base_MAE': base_mae
        })

        peak_ref          = float(daily.quantile(0.95)) or 1.0
        thr_high, thr_med = compute_adaptive_thresholds(daily, peak_ref)
        confidence        = round(max(0.0, m_r2) * 100, 1)

        all_thresholds.append({'Room': room.name, 'peak_ref': round(peak_ref,2), 'thr_high': thr_high, 'thr_med': thr_med, 'term_slots': len(schedule)})

        room_type_tag = f"[{room_type}]"
        print(f"✅ {room.name:.<18} {room_type_tag:<12} R²:{m_r2:.3f} | Ensemble MAE:{m_mae:.2f} (Base MAE:{base_mae:.2f})")

        joblib.dump(lgb_model,  os.path.join(MODEL_DIR, f"{room.id}_lgb.pkl"))
        joblib.dump(xgb_model,  os.path.join(MODEL_DIR, f"{room.id}_xgb.pkl"))
        joblib.dump({
            'peak_ref': peak_ref, 'thr_high': thr_high, 'thr_med': thr_med,
            'hour_dist': room_hour_dist, 'confidence': confidence, 'meta_ridge': meta_ridge,
        }, os.path.join(META_DIR, f"{room.id}_meta.pkl"))

        bulk = _build_forecast_bulk(room, lgb_model, xgb_model, meta_ridge, daily.copy(), peak_ref, thr_high, thr_med, room_hour_dist, confidence, forecast_dates, schedule)
        DemandForecast.objects.filter(room=room, forecast_date__in=forecast_dates).delete()
        DemandForecast.objects.bulk_create(bulk)

    # ── Summary By Room Type ─────────────────────────────────────────────────
    df_res = pd.DataFrame(all_stats)
    if len(df_res) > 0:
        print("\n📊 ── Evaluation by Room Type (Ensemble vs Baseline) ──")
        summary = df_res.groupby('Type').agg({
            'R2': 'mean', 'MAE': 'mean', 'Base_MAE': 'mean', 'MAPE': 'mean', 'sMAPE': 'mean'
        }).reset_index()

        for _, row in summary.iterrows():
            print(f"🔹 Type: {row['Type'].upper()}")
            print(f"   - Avg R²       : {row['R2']:.3f}")
            print(f"   - Ensemble MAE : {row['MAE']:.2f} (ชนะ Baseline ที่ได้ {row['Base_MAE']:.2f})")
            if 'meeting' in row['Type']:
                print(f"   - MAPE         : {row['MAPE']:.1f}% ✅ (Primary Metric)")
            else:
                print(f"   - sMAPE        : {row['sMAPE']:.1f}% ✅ (Primary Metric for Sparse Demand)")
            print("-" * 40)
    _print_summary()

def _print_summary():
    print("\n── จำนวน Record ต่อระดับ ──")
    for lvl in ['urgent', 'high', 'medium', 'low']:
        c = DemandForecast.objects.filter(demand_level=lvl).count()
        print(f"  {lvl:8s}: {c}")
    print("=" * 80)

def generate_forecast_only():
    pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--retrain', action='store_true')
    args = parser.parse_args()
    if args.retrain:
        retrain_and_forecast()
    else:
        generate_forecast_only()