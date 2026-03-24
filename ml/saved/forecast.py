import os, sys, warnings
import numpy as np
import pandas as pd
from datetime import timedelta
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()
from booking.models import Booking, Room, DemandForecast
import lightgbm as lgb
import xgboost as xgb
from sklearn.linear_model import Ridge

warnings.filterwarnings('ignore')

MIN_DAYS      = 60
FORECAST_DAYS = 7

HOUR_DIST_FALLBACK = {
    8: 0.05, 9: 0.10, 10: 0.18, 11: 0.16, 12: 0.02,
    13: 0.17, 14: 0.15, 15: 0.11, 16: 0.07, 17: 0.04,
}

def learn_hour_dist(bookings_df, room_id=None,
                    event_threshold_pct=95.0, min_days_required=30):
    df = bookings_df.copy()
    if room_id is not None:
        df = df[df['room_id'] == room_id]
    if len(df) == 0:
        return HOUR_DIST_FALLBACK.copy()
    df['date'] = pd.to_datetime(df['start_time']).dt.date
    df['hour'] = pd.to_datetime(df['start_time']).dt.hour
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

def build_features(daily):
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
    df['pct_chg_7'] = df['y'].pct_change(7).replace([np.inf, -np.inf], 0).fillna(0)
    t = np.arange(len(df))
    for period, n_terms in [(7, 3), (365, 4)]:
        for k in range(1, n_terms + 1):
            df[f'sin_{period}_{k}'] = np.sin(2 * np.pi * k * t / period)
            df[f'cos_{period}_{k}'] = np.cos(2 * np.pi * k * t / period)
    df['ratio_vs_7d']  = (df['lag_1'] / (df['roll_mean_7']  + 1e-6)).clip(0, 5)
    df['ratio_vs_28d'] = (df['lag_1'] / (df['roll_mean_28'] + 1e-6)).clip(0, 5)
    return df.bfill().ffill()

def train_lgb(X_tr, y_tr, X_te, y_te):
    model = lgb.LGBMRegressor(
        objective='regression_l1', n_estimators=5000, learning_rate=0.01,
        max_depth=6, num_leaves=31, min_child_samples=10,
        lambda_l1=0.3, lambda_l2=0.3, feature_fraction=0.8,
        bagging_fraction=0.8, bagging_freq=5, verbose=-1,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)],
              callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(-1)])
    return model

def train_xgb(X_tr, y_tr, X_te, y_te):
    model = xgb.XGBRegressor(
        n_estimators=3000, learning_rate=0.01, max_depth=5,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.3, reg_lambda=0.3,
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
    final = meta.predict(np.column_stack([lgb_model.predict(X_pred),
                                          xgb_model.predict(X_pred)]))
    return np.maximum(0, final), lgb_model

def compute_adaptive_thresholds(daily, peak_ref):
    historical_norms = np.clip(daily.values / (peak_ref + 1e-6), 0, 1)
    active_norms     = historical_norms[historical_norms > 0.01]
    if len(active_norms) < 10:
        return 0.60, 0.30
    thr_high = float(np.percentile(active_norms, 65))
    thr_med  = float(np.percentile(active_norms, 35))
    thr_high = min(max(thr_high, thr_med + 0.05), 0.90)
    thr_med  = max(thr_med, 0.05)
    return round(thr_high, 3), round(thr_med, 3)

def smape(y_true, y_pred):
    return np.mean(2 * np.abs(y_true - y_pred) /
                   (np.abs(y_true) + np.abs(y_pred) + 1e-8)) * 100

def mape(y_true, y_pred):
    mask = y_true > 0
    if not mask.any(): return 0.0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

def rmse(y_true, y_pred):
    return np.sqrt(mean_squared_error(y_true, y_pred))

print("\n🚀 STACKING ENSEMBLE v2: Learned HOUR_DIST + Adaptive Threshold")
print("=" * 80)

raw_qs = Booking.objects.exclude(status='cancelled').values('start_time', 'room_id')
raw    = pd.DataFrame(list(raw_qs))
raw['date'] = pd.to_datetime(raw['start_time']).dt.date

all_stats      = []
all_thresholds = []
today          = pd.to_datetime('today').date()
forecast_dates = [today + timedelta(days=d) for d in range(FORECAST_DAYS)]

for room in Room.objects.all():
    rdf = raw[raw['room_id'] == room.id]
    if len(rdf) < MIN_DAYS:
        continue

    room_hour_dist = learn_hour_dist(raw, room_id=room.id,
                                     event_threshold_pct=95.0,
                                     min_days_required=30)

    daily = rdf.groupby('date').size().reindex(
        pd.date_range(rdf['date'].min(), rdf['date'].max(), freq='D').date,
        fill_value=0,
    ).astype(float)

    feat_df    = build_features(daily).dropna()
    X          = feat_df.drop(columns='y')
    y          = feat_df['y'].values
    split      = int(len(X) * 0.85)
    X_tr, X_te = X.iloc[:split], X.iloc[split:]
    y_tr, y_te = y[:split], y[split:]
    if len(X_te) < 5:
        continue

    y_pred_ens, lgb_model = stacking_predict(X_tr, y_tr, X_te, y_te, X_te)

    m_r2    = r2_score(y_te, y_pred_ens)
    m_mae   = mean_absolute_error(y_te, y_pred_ens)
    m_rmse  = rmse(y_te, y_pred_ens)
    m_mape  = mape(y_te, y_pred_ens)
    m_smape = smape(y_te, y_pred_ens)
    all_stats.append({'Room': room.name, 'R2': m_r2, 'MAE': m_mae,
                      'RMSE': m_rmse, 'MAPE': m_mape, 'sMAPE': m_smape})

    peak_ref          = float(daily.quantile(0.95)) or 1.0
    thr_high, thr_med = compute_adaptive_thresholds(daily, peak_ref)

    all_thresholds.append({'Room': room.name, 'peak_ref': round(peak_ref, 2),
                           'thr_high': thr_high, 'thr_med': thr_med})

    print(f"✅ {room.name:.<20} | R²:{m_r2:.3f} | MAPE:{m_mape:.1f}% "
          f"| high>={thr_high:.3f} med>={thr_med:.3f} peak_ref={peak_ref:.1f}")

    history = daily.copy()
    bulk    = []

    for d in range(FORECAST_DAYS):
        fc_date  = forecast_dates[d]
        extended = pd.concat([history, pd.Series([np.nan], index=[fc_date])])
        f_df     = build_features(extended).loc[[fc_date]].drop(columns='y')
        d_pred   = max(0.0, float(lgb_model.predict(f_df)[0]))
        history.loc[fc_date] = d_pred

        # ✅ day_norm = 0.0-1.0 → ใช้เป็น predicted_demand และ classify ระดับวัน
        day_norm = float(np.clip(d_pred / (peak_ref + 1e-6), 0.0, 1.0))

        if day_norm >= thr_high:
            day_level, day_avail = 'high',   'likely_full'
        elif day_norm >= thr_med:
            day_level, day_avail = 'medium', 'likely_busy'
        else:
            day_level, day_avail = 'low',    'likely_available'

        for hr in room_hour_dist.keys():
            # ✅ FIX: predicted_demand = day_norm ทุก hour
            # → สอดคล้องกับ demand_level เสมอ ไม่มี 0.0 + medium อีกแล้ว
            # hour_dist ใช้แค่กำหนดว่า hour ไหนบ้างที่มีข้อมูล (8-17)
            bulk.append(DemandForecast(
                room             = room,
                forecast_date    = fc_date,
                hour             = hr,
                predicted_demand = round(day_norm, 4),  # ✅ 0.0-1.0 สอดคล้อง demand_level
                demand_level     = day_level,
                availability     = day_avail,
                confidence       = round(max(0.0, m_r2) * 100, 1),
            ))

    # ✅ delete เฉพาะห้องนี้ก่อน → ไม่มี unique_together conflict
    # ถ้า script crash กลางคัน ห้องที่ save แล้วยังอยู่ครบ
    DemandForecast.objects.filter(
        room=room,
        forecast_date__in=forecast_dates,
    ).delete()

    DemandForecast.objects.bulk_create(bulk)
    print(f"   💾 Saved {len(bulk)} records")

# ── Summary ──────────────────────────────────────────────────────────────────
df_res = pd.DataFrame(all_stats)
df_thr = pd.DataFrame(all_thresholds)

print("\n" + "=" * 80)
if len(df_res):
    print(f"📈 Avg R²:    {df_res['R2'].mean():.3f}")
    print(f"📉 Avg MAE:   {df_res['MAE'].mean():.2f}")
    print(f"📉 Avg RMSE:  {df_res['RMSE'].mean():.2f}")
    print(f"📉 Avg MAPE:  {df_res['MAPE'].mean():.1f}%")
    print(f"📉 Avg sMAPE: {df_res['sMAPE'].mean():.1f}%")
    print("\n── Adaptive Thresholds ที่ใช้ (0-1) ──")
    print(df_thr.to_string(index=False))

print("\n── จำนวน Record ต่อระดับ ──")
for lvl in ['high', 'medium', 'low']:
    c = DemandForecast.objects.filter(demand_level=lvl).count()
    print(f"  {lvl:8s}: {c}")
print("=" * 80)