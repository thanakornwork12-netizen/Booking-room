# ══════════════════════════════════════════════════════════════════════════════
#  ALL-IN-ONE: Demand Forecast Engine + Update Thai Facilities + Boost Thresholds
#  รวม 3 สคริปต์ไว้ในไฟล์เดียว
#
#  สถาปัตยกรรม: Stacking Ensemble (ตามบทความวิจัย)
#
#  ┌──────────────────────────────────────────────────────────────────┐
#  │  Base Models – Layer 1                                           │
#  │                                                                  │
#  │  [PRIMARY]  LSTM       – จดจำรูปแบบ temporal / seasonal ระยะยาว │
#  │  [SUPPORT]  LightGBM   – Gradient Boosting เชิงโครงสร้าง        │
#  │  [SUPPORT]  XGBoost    – Gradient Boosting รับ noise ได้ดี       │
#  └──────────────────────┬───────────────────────────────────────────┘
#                         │  ผลลัพธ์เบื้องต้นทั้ง 3 ตัว
#                         ▼
#  ┌──────────────────────────────────────────────────────────────────┐
#  │  Meta-Model – Layer 2                                            │
#  │  Ridge Regression – ถ่วงน้ำหนัก LSTM > LGB/XGB แล้วผสานผล      │
#  └──────────────────────────────────────────────────────────────────┘
#
#  การแก้ไขเวอร์ชันนี้ (เน้นห้อง R²ต่ำ/ติดลบ ไม่เพิ่มเวลา train):
#    1. auto-detect problematic rooms จาก CV/spike/zero_ratio (ไม่ hardcode)
#    2. Winsorize (clip 1%–99%) สำหรับห้อง spike รุนแรง แทน IQR ธรรมดา
#    3. Huber loss ใน LGB/XGB สำหรับห้อง noisy → robust ต่อ outlier มากขึ้น
#    4. Fallback seasonal-median model เมื่อ R² < 0 หลัง train
#    5. epochs/patience คงเดิม → ไม่เพิ่มเวลา retrain
#
#  วิธีใช้:
#    python demand_forecast_all_in_one.py --retrain        → retrain + forecast
#    python demand_forecast_all_in_one.py                  → forecast only
#    python demand_forecast_all_in_one.py --update-fac     → อัปเดตอุปกรณ์ภาษาไทย
#    python demand_forecast_all_in_one.py --boost          → ปรับ threshold ให้ Urgent ง่ายขึ้น
#    python demand_forecast_all_in_one.py --show-metrics   → แสดง metrics ที่บันทึกไว้
# ══════════════════════════════════════════════════════════════════════════════

import os, sys, warnings, argparse, random
import numpy as np
import pandas as pd
import joblib
from datetime import timedelta
from sklearn.metrics import (
    mean_absolute_error, r2_score, mean_squared_error,
    accuracy_score, f1_score, recall_score, precision_score,
    classification_report
)
from sklearn.linear_model import Ridge
from sklearn.preprocessing import MinMaxScaler
from scipy.stats import mstats

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()
from booking.models import Booking, Room, Facility, RoomFacility, TermBooking, DemandForecast

import lightgbm as lgb
import xgboost as xgb

warnings.filterwarnings('ignore')

# ── TensorFlow (LSTM – Primary Base Model) ────────────────────────────────────
try:
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping
    LSTM_AVAILABLE = True
except ImportError:
    LSTM_AVAILABLE = False
    print("⚠️  TensorFlow ไม่พบ – LSTM (Primary Model) ไม่สามารถใช้งานได้")
    print("   กรุณาติดตั้ง: pip install tensorflow")

# ── Config ─────────────────────────────────────────────────────────────────────
MIN_DAYS      = 200
FORECAST_DAYS = 14
LSTM_LOOKBACK = 14
LSTM_EPOCHS   = 150          # คงเดิม – ไม่เพิ่มเวลา
LSTM_BATCH    = 16
LSTM_PATIENCE = 20           # คงเดิม
MODEL_DIR     = os.path.join(CURRENT_DIR, "saved_models")
META_DIR      = os.path.join(CURRENT_DIR, "saved_meta")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(META_DIR,  exist_ok=True)

# ── น้ำหนัก Prior (LSTM = Primary) ────────────────────────────────────────────
LSTM_WEIGHT_PRIOR = 0.60
LGB_WEIGHT_PRIOR  = 0.22
XGB_WEIGHT_PRIOR  = 0.18

# ── Thresholds สำหรับ auto-detect ห้องที่มีปัญหา ──────────────────────────────
# ลดค่าลงให้ sensitive กว่าเดิม → จับห้องที่มีความผันผวนปานกลางได้ด้วย
AUTO_ROBUST_CV         = 0.80  # CV > 0.80  → ความผันผวนสูงพอที่จะใช้ Huber
AUTO_ROBUST_SPIKE      = 0.02  # spike > 2% → มี spike ผิดปกติบ่อยพอ
AUTO_ROBUST_ZERO       = 0.25  # zero  > 25% → วันว่างเยอะพอ

# ── R² fallback threshold ──────────────────────────────────────────────────────
# ทุกห้องตรวจ R² หลัง train เสมอ (ไม่ผูกกับ robust)
# ถ้า R² < threshold → ลอง Seasonal Median Fallback
R2_FALLBACK_THRESHOLD  = 0.50  # เพิ่มจาก 0.10 → ครอบคลุมห้องที่ R²ต่ำกว่าเกณฑ์

# ── Fallback hour distribution ─────────────────────────────────────────────────
HOUR_DIST_FALLBACK = {
    8: 0.05, 9: 0.10, 10: 0.18, 11: 0.16, 12: 0.02,
    13: 0.17, 14: 0.15, 15: 0.11, 16: 0.07, 17: 0.04,
    18: 0.03, 19: 0.02, 20: 0.01
}



#  ROBUST PREPROCESSING


def winsorize_series(series: pd.Series, limits=(0.01, 0.01)) -> pd.Series:
    """
    Winsorize: clip ค่าที่ต่ำกว่า 1th และสูงกว่า 99th percentile
    รุนแรงกว่า IQR clip — เหมาะกับห้องที่มี extreme spike (LIB-M10, LIB-C02)
    ใช้ scipy.stats.mstats.winsorize เพื่อ preserve index
    """
    arr     = mstats.winsorize(series.values, limits=limits)
    result  = pd.Series(arr, index=series.index, dtype=float)
    n_clip  = ((series < result.min()) | (series > result.max())).sum()
    if n_clip > 0:
        print(f"   🔧 Winsorize: clip {n_clip} จุด "
              f"(p1={result.min():.2f}, p99={result.max():.2f})")
    return result


def detect_room_profile(room_name: str, daily: pd.Series) -> dict:
    """
    Auto-detect ลักษณะปัญหาของห้องโดยอิงจากสถิติข้อมูลจริง
    ไม่ hardcode ชื่อห้อง → ปรับตัวได้เมื่อเพิ่มห้องใหม่

    Returns dict ประกอบด้วย:
      needs_robust  – ควรใช้ robust preprocessing + Huber loss
      needs_fallback_check – หลัง train ให้ตรวจ R² และ fallback ถ้าต่ำ
      winsorize     – ควร winsorize ก่อน train
      preprocessing – ชื่อ strategy ที่เลือก
    """
    active = daily[daily > 0]
    if len(active) < 10:
        return {
            'cv': 0, 'zero_ratio': 1, 'spike_ratio': 0,
            'needs_robust': True,
            'winsorize': True, 'preprocessing': 'sparse'
        }

    cv          = float(active.std() / (active.mean() + 1e-6))
    zero_ratio  = float((daily == 0).mean())
    p95         = daily.quantile(0.95)
    spike_ratio = float((daily > p95 * 2.0).mean())

    needs_robust = (
        cv > AUTO_ROBUST_CV
        or spike_ratio > AUTO_ROBUST_SPIKE
        or zero_ratio > AUTO_ROBUST_ZERO
    )
    # winsorize เฉพาะห้องที่ spike รุนแรงมาก (spike > 4% หรือ CV > 1.2)
    do_winsorize = cv > 1.2 or spike_ratio > 0.04

    if needs_robust and do_winsorize:
        strategy = 'robust+winsorize'
    elif needs_robust:
        strategy = 'robust'
    else:
        strategy = 'standard'

    return {
        'cv':           round(cv, 3),
        'zero_ratio':   round(zero_ratio, 3),
        'spike_ratio':  round(spike_ratio, 3),
        'needs_robust': needs_robust,
        'winsorize':    do_winsorize,
        'preprocessing': strategy,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SEASONAL MEDIAN FALLBACK MODEL
#  ใช้เมื่อ Stacking Ensemble ให้ R² < R2_FALLBACK_THRESHOLD
#  หลักการ: พยากรณ์ด้วย median ตามวันในสัปดาห์ × เดือน (ไม่ต้อง ML)
# ══════════════════════════════════════════════════════════════════════════════

class SeasonalMedianModel:
    """
    Fallback model สำหรับห้องที่ Stacking ไม่ผ่าน R² threshold
    พยากรณ์จาก median ของ (dow, month) — เสถียรกว่าสำหรับข้อมูล noisy มาก
    """
    def __init__(self):
        self.dow_month_median = {}
        self.dow_median       = {}
        self.global_median    = 0.0

    def fit(self, daily: pd.Series):
        df = pd.DataFrame({'y': daily.values}, index=pd.to_datetime(daily.index))
        df['dow']   = df.index.dayofweek
        df['month'] = df.index.month

        self.global_median    = float(daily.median())
        self.dow_median       = df.groupby('dow')['y'].median().to_dict()
        self.dow_month_median = df.groupby(['dow', 'month'])['y'].median().to_dict()
        return self

    def predict_date(self, d) -> float:
        ts    = pd.Timestamp(d)
        dow   = ts.dayofweek
        month = ts.month
        # ลำดับ: dow+month → dow → global
        return float(
            self.dow_month_median.get((dow, month),
            self.dow_median.get(dow,
            self.global_median))
        )

    def predict_series(self, dates) -> np.ndarray:
        return np.array([self.predict_date(d) for d in dates])


# ══════════════════════════════════════════════════════════════════════════════
#  CLASSIFICATION METRICS HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def demand_score_to_label(score: float, thr_high: float, thr_med: float) -> str:
    if score >= thr_high:
        return 'urgent'
    elif score >= thr_med:
        return 'high'
    elif score >= thr_med * 0.6:
        return 'medium'
    else:
        return 'low'


def compute_classification_metrics(
    y_true_scores: np.ndarray,
    y_pred_scores: np.ndarray,
    thr_high: float,
    thr_med: float,
    peak_ref: float,
) -> dict:
    y_true_norm = np.clip(y_true_scores / (peak_ref + 1e-6), 0, 1)
    y_pred_norm = np.clip(y_pred_scores / (peak_ref + 1e-6), 0, 1)

    y_true_labels = [demand_score_to_label(s, thr_high, thr_med) for s in y_true_norm]
    y_pred_labels = [demand_score_to_label(s, thr_high, thr_med) for s in y_pred_norm]

    labels = ['low', 'medium', 'high', 'urgent']

    acc       = accuracy_score(y_true_labels, y_pred_labels)
    f1        = f1_score(y_true_labels, y_pred_labels,
                         labels=labels, average='weighted', zero_division=0)
    recall    = recall_score(y_true_labels, y_pred_labels,
                             labels=labels, average='weighted', zero_division=0)
    precision = precision_score(y_true_labels, y_pred_labels,
                                labels=labels, average='weighted', zero_division=0)

    label_map = {'low': 0, 'medium': 1, 'high': 2, 'urgent': 3}
    n_classes = len(labels)
    ce_loss   = 0.0
    for true_l, pred_l in zip(y_true_labels, y_pred_labels):
        true_idx        = label_map[true_l]
        pred_idx        = label_map[pred_l]
        probs           = np.full(n_classes, 0.05)
        probs[pred_idx] = 0.85
        probs          /= probs.sum()
        ce_loss        -= np.log(probs[true_idx] + 1e-8)
    ce_loss /= max(len(y_true_labels), 1)

    report = classification_report(
        y_true_labels, y_pred_labels,
        labels=labels, zero_division=0
    )

    return {
        'accuracy':  round(acc,       4),
        'f1':        round(f1,        4),
        'recall':    round(recall,    4),
        'precision': round(precision, 4),
        'loss':      round(ce_loss,   4),
        'report':    report,
    }


def print_classification_metrics(metrics: dict, room_name: str):
    print(f"\n  📊 Classification Metrics – {room_name}")
    print(f"  {'─' * 50}")
    print(f"  Accuracy  : {metrics['accuracy']:.4f}  ({metrics['accuracy']*100:.1f}%)")
    print(f"  F1 Score  : {metrics['f1']:.4f}  (weighted avg)")
    print(f"  Recall    : {metrics['recall']:.4f}  (weighted avg)")
    print(f"  Precision : {metrics['precision']:.4f}  (weighted avg)")
    print(f"  CE Loss   : {metrics['loss']:.4f}")
    print(f"\n  📋 Classification Report:")
    for line in metrics['report'].split('\n'):
        print(f"     {line}")
    print(f"  {'─' * 50}")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 – Demand Forecast Engine
# ══════════════════════════════════════════════════════════════════════════════

def print_data_summary(raw: pd.DataFrame, room=None):
    df = raw.copy()
    if room is not None:
        df = df[df['room_id'] == room.id]

    print("\n" + "=" * 60)
    print(f"📋 DATA SUMMARY {'– ' + room.name if room else '(All Rooms)'}")
    print("=" * 60)

    print(f"\n📌 ภาพรวม")
    print(f"   จำนวน booking ทั้งหมด : {len(df):,} ครั้ง")
    print(f"   ช่วงวันที่            : {df['date'].min()} → {df['date'].max()}")
    total_days  = (df['date'].max() - df['date'].min()).days + 1
    active_days = df['date'].nunique()
    print(f"   จำนวนวันทั้งหมด       : {total_days:,} วัน")
    print(f"   วันที่มี booking       : {active_days:,} วัน")
    print(f"   วันที่ไม่มี booking    : {total_days - active_days:,} วัน")

    print(f"\n⏱️  ระยะเวลาการจอง (ชั่วโมง)")
    print(f"   เฉลี่ย    : {df['duration'].mean():.2f} ชม.")
    print(f"   ต่ำสุด    : {df['duration'].min():.2f} ชม.")
    print(f"   สูงสุด    : {df['duration'].max():.2f} ชม.")
    print(f"   รวมทั้งหมด: {df['duration'].sum():.1f} ชม.")

    daily_hours = df.groupby('date')['duration'].sum()
    print(f"\n🎯 Target: ชั่วโมงรวม/วัน")
    print(f"   เฉลี่ย   : {daily_hours.mean():.2f} ชม./วัน")
    print(f"   ต่ำสุด   : {daily_hours.min():.2f} ชม./วัน")
    print(f"   สูงสุด   : {daily_hours.max():.2f} ชม./วัน")
    print(f"   มัธยฐาน  : {daily_hours.median():.2f} ชม./วัน")

    print(f"\n🕐 การกระจายตามชั่วโมง (start_time)")
    hour_counts = df.groupby('hour')['duration'].sum().sort_index()
    total_hr    = hour_counts.sum()
    for h, v in hour_counts.items():
        bar = '█' * int((v / total_hr) * 30)
        print(f"   {h:02d}:00  {bar:<30}  {v:.1f} ชม. ({v/total_hr*100:.1f}%)")

    print(f"\n📅 การกระจายตามวันในสัปดาห์")
    dow_map = {0: 'จันทร์', 1: 'อังคาร', 2: 'พุธ', 3: 'พฤหัส',
               4: 'ศุกร์', 5: 'เสาร์', 6: 'อาทิตย์'}
    df['dow']  = pd.to_datetime(df['date']).dt.dayofweek
    dow_hours  = df.groupby('dow')['duration'].sum()
    for d, v in dow_hours.items():
        bar = '█' * int((v / dow_hours.max()) * 20)
        print(f"   {dow_map[d]:<6}  {bar:<20}  {v:.1f} ชม.")

    print("=" * 60)


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


def learn_hour_dist(bookings_df, room_id=None) -> dict:
    df = bookings_df.copy()
    if room_id is not None:
        df = df[df['room_id'] == room_id]
    if len(df) == 0:
        return HOUR_DIST_FALLBACK.copy()

    hour_hours = {h: 0.0 for h in range(8, 18)}
    for _, row in df.iterrows():
        s      = int(row['hour'])
        e      = int(row['end_hour']) if 'end_hour' in row else s + 1
        dur    = float(row['duration'])
        span   = max(e - s, 1)
        per_hr = dur / span
        for h in range(s, min(e, 18)):
            if 8 <= h < 18:
                hour_hours[h] = hour_hours.get(h, 0) + per_hr

    total = sum(hour_hours.values())
    if total == 0:
        return HOUR_DIST_FALLBACK.copy()

    normalized = {h: (v / total) for h, v in hour_hours.items()}
    for h in normalized:
        normalized[h] = normalized[h] * 0.85 + (1 / len(normalized)) * 0.15
    s          = sum(normalized.values())
    normalized = {h: round(v / s, 4) for h, v in normalized.items()}
    diff = 1.0 - sum(normalized.values())
    pk   = max(normalized, key=normalized.get)
    normalized[pk] = round(normalized[pk] + diff, 4)
    return normalized


def build_features(daily, term_df=None, use_log: bool = False):
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

    t = np.arange(len(df))
    for period, n_terms in [(7, 3), (365, 4)]:
        for k in range(1, n_terms + 1):
            df[f'sin_{period}_{k}'] = np.sin(2 * np.pi * k * t / period)
            df[f'cos_{period}_{k}'] = np.cos(2 * np.pi * k * t / period)

    df['ratio_vs_7d']  = (df['lag_1'] / (df['roll_mean_7']  + 1e-6)).clip(0, 5)
    df['ratio_vs_28d'] = (df['lag_1'] / (df['roll_mean_28'] + 1e-6)).clip(0, 5)

    if term_df is not None:
        term_aligned             = term_df.reindex(df.index, fill_value=0)
        df['term_hours_day']     = term_aligned['term_hours_day'].values
        df['term_sessions']      = term_aligned['term_sessions'].values
        df['in_term']            = term_aligned['in_term'].values
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


# ══════════════════════════════════════════════════════════════════════════════
#  LSTM – Primary Base Model
# ══════════════════════════════════════════════════════════════════════════════

def _make_lstm_sequences(series, lookback):
    X, y = [], []
    for i in range(lookback, len(series)):
        X.append(series[i - lookback: i])
        y.append(series[i])
    return np.array(X), np.array(y)


def train_lstm(y_train_raw, y_val_raw, lookback=LSTM_LOOKBACK,
               epochs=LSTM_EPOCHS, patience=LSTM_PATIENCE):
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
    es = EarlyStopping(monitor='val_loss', patience=patience, restore_best_weights=True)
    model.fit(X_tr, y_tr, validation_data=(X_va, y_va),
              epochs=epochs, batch_size=LSTM_BATCH,
              callbacks=[es], verbose=0)
    return model, scaler


def lstm_predict(model, scaler, history_series, n_steps, lookback=LSTM_LOOKBACK):
    if model is None or scaler is None:
        return np.zeros(n_steps)
    if len(history_series) < lookback:
        pad            = np.zeros(lookback - len(history_series))
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


# ══════════════════════════════════════════════════════════════════════════════
#  Supporting Base Models – LightGBM & XGBoost
#  robust=True → เปลี่ยน loss เป็น Huber (robust ต่อ outlier มากกว่า MAE ธรรมดา)
# ══════════════════════════════════════════════════════════════════════════════

def train_lgb(X_tr, y_tr, X_te, y_te, robust: bool = False):
    """
    LightGBM – Supporting Model
    robust=True → Huber loss + regularization แรงขึ้น
    Huber loss ดีกว่า MAE สำหรับข้อมูลที่มี extreme outlier เป็นครั้งคราว
    """
    if robust:
        params = dict(
            objective='huber', alpha=0.9,          # Huber: ทนต่อ spike ได้ดีกว่า
            n_estimators=5000, learning_rate=0.01,
            max_depth=5, num_leaves=24,             # ลด complexity
            min_child_samples=20,                   # ต้องการข้อมูลต่อ leaf มากขึ้น
            lambda_l1=1.0, lambda_l2=1.0,           # regularize แรง
            feature_fraction=0.7, bagging_fraction=0.7, bagging_freq=5,
            verbose=-1,
        )
    else:
        params = dict(
            objective='regression_l1',
            n_estimators=5000, learning_rate=0.01,
            max_depth=6, num_leaves=31, min_child_samples=10,
            lambda_l1=0.3, lambda_l2=0.3,
            feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=5,
            verbose=-1,
        )
    model = lgb.LGBMRegressor(**params)
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)],
              callbacks=[lgb.early_stopping(100, verbose=False),
                         lgb.log_evaluation(-1)])
    return model


def train_xgb(X_tr, y_tr, X_te, y_te, robust: bool = False):
    """
    XGBoost – Supporting Model
    robust=True → pseudo-Huber loss + regularization แรงขึ้น
    """
    if robust:
        params = dict(
            objective='reg:pseudohubererror',       # pseudo-Huber: ทนต่อ noise ดีกว่า
            n_estimators=3000, learning_rate=0.01,
            max_depth=4, subsample=0.7,             # ลด complexity
            colsample_bytree=0.7,
            reg_alpha=1.0, reg_lambda=1.0,
            early_stopping_rounds=100, eval_metric='mae', verbosity=0,
        )
    else:
        params = dict(
            objective='reg:absoluteerror',
            n_estimators=3000, learning_rate=0.01,
            max_depth=5, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.3, reg_lambda=0.3,
            early_stopping_rounds=100, eval_metric='mae', verbosity=0,
        )
    model = xgb.XGBRegressor(**params)
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
    return model


# ══════════════════════════════════════════════════════════════════════════════
#  Meta-Model – Ridge Regression (Layer 2)
# ══════════════════════════════════════════════════════════════════════════════

def _build_meta_input_with_lstm_priority(
    lstm_preds: np.ndarray,
    lgb_preds:  np.ndarray,
    xgb_preds:  np.ndarray,
) -> np.ndarray:
    """
    LSTM ×3 (~60%), LightGBM ×1 (~20%), XGBoost ×1 (~20%)
    """
    return np.column_stack([
        lstm_preds, lstm_preds, lstm_preds,
        lgb_preds,
        xgb_preds,
    ])


def stacking_predict(
    X_tr, y_tr, X_te, y_te, X_pred,
    lstm_model=None, lstm_scaler=None,
    daily_tr_raw=None, n_pred=None,
    lstm_lookback=LSTM_LOOKBACK,
    robust: bool = False,
):
    lgb_model = train_lgb(X_tr, y_tr, X_te, y_te, robust=robust)
    xgb_model = train_xgb(X_tr, y_tr, X_te, y_te, robust=robust)

    lgb_val = lgb_model.predict(X_te)
    xgb_val = xgb_model.predict(X_te)
    lgb_fut = lgb_model.predict(X_pred)
    xgb_fut = xgb_model.predict(X_pred)

    lstm_ready = (
        LSTM_AVAILABLE
        and lstm_model is not None
        and lstm_scaler is not None
        and daily_tr_raw is not None
    )

    # alpha สูงขึ้นสำหรับห้อง robust → Meta-Model ไม่ overfit noise
    alpha = 10.0 if robust else 1.0

    if lstm_ready:
        lstm_val  = lstm_predict(lstm_model, lstm_scaler,
                                 daily_tr_raw, len(y_te), lookback=lstm_lookback)
        hist_full = np.concatenate([daily_tr_raw, y_te])
        lstm_fut  = lstm_predict(lstm_model, lstm_scaler,
                                 hist_full, n_pred or len(X_pred),
                                 lookback=lstm_lookback)

        meta_tr  = _build_meta_input_with_lstm_priority(
            lstm_val[:len(y_te)], lgb_val, xgb_val)
        meta_fut = _build_meta_input_with_lstm_priority(
            lstm_fut[:len(X_pred)], lgb_fut, xgb_fut)

        meta  = Ridge(alpha=alpha)
        meta.fit(meta_tr, y_te)
        final = meta.predict(meta_fut)
    else:
        print("⚠️  LSTM (Primary Model) ไม่พร้อม – ใช้ LGB + XGB เท่านั้น")
        meta  = Ridge(alpha=alpha)
        meta.fit(np.column_stack([lgb_val, xgb_val]), y_te)
        final = meta.predict(np.column_stack([lgb_fut, xgb_fut]))

    return np.maximum(0, final), lgb_model, xgb_model, meta


# ══════════════════════════════════════════════════════════════════════════════
#  Utility Functions
# ══════════════════════════════════════════════════════════════════════════════

def smape(y_true, y_pred):
    raw = (2 * np.abs(y_true - y_pred)
           / (np.abs(y_true) + np.abs(y_pred) + 1e-8)) * 100
    return float(np.mean(np.clip(raw, 0, 100)))


def rmse(y_true, y_pred):
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def compute_adaptive_thresholds(daily, peak_ref, problematic: bool = False):
    historical_norms = np.clip(daily.values / (peak_ref + 1e-6), 0, 1)
    active_norms     = historical_norms[historical_norms > 0.01]

    if len(active_norms) < 10:
        return 0.45, 0.18

    p_high = 55 if problematic else 65
    p_med  = 25 if problematic else 30

    thr_high = float(np.percentile(active_norms, p_high))
    thr_med  = float(np.percentile(active_norms, p_med))
    thr_high = min(max(thr_high, thr_med + 0.10), 0.75)
    thr_med  = max(thr_med, 0.10)

    return round(thr_high, 3), round(thr_med, 3)


def _needs_log_transform(room) -> bool:
    room_type = getattr(room, 'room_type', '') or ''
    return 'lecture' in room_type.lower()


def _build_forecast_bulk(
    room, lgb_model, xgb_model, meta_ridge,
    history, peak_ref, thr_high, thr_med,
    room_hour_dist, confidence, forecast_dates, schedule,
    lstm_model=None, lstm_scaler=None,
    use_log: bool = False,
    lstm_lookback: int = LSTM_LOOKBACK,
    seasonal_model: SeasonalMedianModel = None,
):
    max_hr_weight = max(room_hour_dist.values()) if room_hour_dist else 1.0
    bulk = []

    all_dates = pd.date_range(
        pd.Timestamp(history.index.min()),
        pd.Timestamp(forecast_dates[-1]), freq='D'
    )
    term_df       = build_term_daily_features(all_dates, schedule)
    term_df.index = all_dates

    # ── LSTM Primary พยากรณ์ล่วงหน้าทั้งหมด ──────────────────────────────────
    lstm_daily_preds = {}
    if LSTM_AVAILABLE and lstm_model is not None and lstm_scaler is not None:
        hist_arr = history.values.copy()
        if use_log:
            hist_arr = np.log1p(hist_arr)
        lstm_ahead = lstm_predict(lstm_model, lstm_scaler, hist_arr,
                                  len(forecast_dates), lookback=lstm_lookback)
        if use_log:
            lstm_ahead = np.expm1(lstm_ahead)
        for i, fd in enumerate(forecast_dates):
            lstm_daily_preds[fd] = max(0.0, float(lstm_ahead[i]))

    # ── Seasonal Median Fallback พยากรณ์ล่วงหน้า (ถ้าใช้) ───────────────────
    seasonal_preds = {}
    if seasonal_model is not None:
        for fd in forecast_dates:
            seasonal_preds[fd] = seasonal_model.predict_date(fd)

    for fc_date in forecast_dates:
        # ── เลือก prediction source ────────────────────────────────────────────
        if seasonal_model is not None:
            # Fallback mode: ใช้ seasonal median หลัก + blend กับ LGB/XGB เล็กน้อย
            d_pred_seasonal = seasonal_preds.get(fc_date, peak_ref * 0.5)
            fc_ts    = pd.Timestamp(fc_date)
            extended = pd.concat([history, pd.Series([np.nan], index=[fc_ts])])
            extended.index = pd.to_datetime(extended.index)
            f_df = build_features(extended, term_df, use_log=use_log)\
                .loc[[fc_ts]].drop(columns='y')
            lgb_pred = float(lgb_model.predict(f_df)[0])
            xgb_pred = float(xgb_model.predict(f_df)[0])
            # blend: 70% seasonal median + 15% lgb + 15% xgb
            d_pred = 0.70 * d_pred_seasonal + 0.15 * max(0, lgb_pred) + 0.15 * max(0, xgb_pred)
            history.loc[fc_ts] = d_pred
        else:
            fc_ts    = pd.Timestamp(fc_date)
            extended = pd.concat([history, pd.Series([np.nan], index=[fc_ts])])
            extended.index = pd.to_datetime(extended.index)
            f_df = build_features(extended, term_df, use_log=use_log)\
                .loc[[fc_ts]].drop(columns='y')
            lgb_pred = float(lgb_model.predict(f_df)[0])
            xgb_pred = float(xgb_model.predict(f_df)[0])

            if fc_date in lstm_daily_preds:
                lstm_val_fc = lstm_daily_preds[fc_date]
                if use_log:
                    lstm_val_fc = np.log1p(lstm_val_fc)
                try:
                    meta_in = _build_meta_input_with_lstm_priority(
                        np.array([lstm_val_fc]),
                        np.array([lgb_pred]),
                        np.array([xgb_pred]),
                    )
                    d_pred = float(meta_ridge.predict(meta_in)[0])
                except Exception:
                    d_pred = float(meta_ridge.predict(
                        np.column_stack([[lgb_pred], [xgb_pred]]))[0])
            else:
                try:
                    d_pred = float(meta_ridge.predict(
                        np.column_stack([[lgb_pred], [lgb_pred], [lgb_pred],
                                         [lgb_pred], [xgb_pred]]))[0])
                except Exception:
                    d_pred = float(meta_ridge.predict(
                        np.column_stack([[lgb_pred], [xgb_pred]]))[0])

            d_pred = max(0.0, d_pred)
            if use_log:
                d_pred = np.expm1(d_pred)
            history.loc[fc_ts] = d_pred

        day_norm = float(np.clip(d_pred / (peak_ref + 1e-6), 0.0, 1.0))

        for hr, weight in room_hour_dist.items():
            hr_term_load = compute_term_load(fc_date, hr, schedule)
            hr_factor    = weight / max_hr_weight if max_hr_weight > 0 else 1.0
            hr_pred      = day_norm * (0.6 + 0.4 * hr_factor)
            hr_term      = hr_term_load * day_norm * 0.6
            hr_dyn       = max(0.0, hr_pred - hr_term)
            demand_score = round(float(0.7 * hr_pred + 0.3 * hr_dyn), 4)

            if demand_score >= thr_high:
                day_level = 'urgent';  day_avail = 'book_now'
            elif demand_score >= thr_med:
                day_level = 'high';    day_avail = 'book_soon'
            elif demand_score >= thr_med * 0.6:
                day_level = 'medium';  day_avail = 'recommended'
            else:
                day_level = 'low';     day_avail = 'likely_available'

            bulk.append(DemandForecast(
                room=room, forecast_date=fc_date, hour=hr,
                predicted_demand=demand_score,
                term_demand=round(hr_term, 4),
                dynamic_demand=round(hr_dyn, 4),
                demand_level=day_level,
                availability=day_avail,
                confidence=confidence,
            ))

    return bulk


# ── RETRAIN ────────────────────────────────────────────────────────────────────
def retrain_and_forecast():
    print("\n🚀 RETRAIN + GENERATE FORECAST")
    print("=" * 60)
    print(f"🧠 สถาปัตยกรรม: Stacking Ensemble")
    print(f"   Primary  : LSTM        (weight prior ≈ {LSTM_WEIGHT_PRIOR:.0%})")
    print(f"   Support  : LightGBM    (weight prior ≈ {LGB_WEIGHT_PRIOR:.0%})")
    print(f"   Support  : XGBoost     (weight prior ≈ {XGB_WEIGHT_PRIOR:.0%})")
    print(f"   Meta     : Ridge Regression")
    print(f"   Fallback : Seasonal Median (เมื่อ R² < {R2_FALLBACK_THRESHOLD})")
    print(f"   Robust trigger: CV>{AUTO_ROBUST_CV} | spike>{AUTO_ROBUST_SPIKE:.0%} | zero>{AUTO_ROBUST_ZERO:.0%}")
    if not LSTM_AVAILABLE:
        print(f"\n⚠️  WARNING: LSTM ไม่พร้อม!")
    print("=" * 60)

    raw_qs = Booking.objects.exclude(status='cancelled').values(
        'start_time', 'end_time', 'room_id'
    )
    raw = pd.DataFrame(list(raw_qs))

    if len(raw) == 0:
        print("❌ ไม่มีข้อมูล Booking"); return

    for col in ['start_time', 'end_time']:
        raw[col] = pd.to_datetime(raw[col])
        if raw[col].dt.tz is None:
            raw[col] = raw[col].dt.tz_localize('UTC')
        raw[col] = raw[col].dt.tz_convert('Asia/Bangkok')

    raw['duration'] = (raw['end_time'] - raw['start_time']).dt.total_seconds() / 3600
    raw['duration'] = raw['duration'].clip(lower=0.25, upper=12.0)
    raw['date']     = raw['start_time'].dt.date
    raw['hour']     = raw['start_time'].dt.hour
    raw['end_hour'] = raw['end_time'].dt.hour

    print_data_summary(raw)

    today          = pd.to_datetime('today').date()
    forecast_dates = [today + timedelta(days=d) for d in range(FORECAST_DAYS)]
    all_stats      = []

    for room in Room.objects.all():
        rdf = raw[raw['room_id'] == room.id]
        if len(rdf) < MIN_DAYS:
            print(f"⏭️  {room.name} – ข้อมูลน้อยเกินไป ({len(rdf)} rows < {MIN_DAYS})")
            continue

        schedule = load_term_schedule(room.id)
        use_log  = _needs_log_transform(room)

        daily = (
            rdf.groupby('date')['duration'].sum()
               .reindex(pd.date_range(rdf['date'].min(),
                                      rdf['date'].max(), freq='D').date,
                        fill_value=0.0)
               .astype(float)
        )
        daily.index = pd.to_datetime(daily.index)

        # ── Auto-detect room profile ──────────────────────────────────────────
        profile      = detect_room_profile(room.name, daily)
        needs_robust = profile['needs_robust']

        if needs_robust:
            print(f"\n  ⚠️  {room.name} → {profile['preprocessing'].upper()} "
                  f"(CV={profile['cv']:.2f}, zero={profile['zero_ratio']:.0%}, "
                  f"spike={profile['spike_ratio']:.0%})")
            if profile['winsorize']:
                daily = winsorize_series(daily, limits=(0.01, 0.01))
            else:
                # IQR clip สำหรับห้องที่ robust แต่ไม่ spike รุนแรงมาก
                Q1, Q3 = daily.quantile(0.25), daily.quantile(0.75)
                daily  = daily.clip(upper=Q3 + 2.5 * (Q3 - Q1))
        elif use_log:
            cap95 = float(daily.quantile(0.95))
            daily = daily.clip(upper=cap95)

        room_hour_dist = learn_hour_dist(rdf, room_id=None)

        term_df       = build_term_daily_features(daily.index, schedule)
        term_df.index = daily.index
        feat_df       = build_features(daily, term_df, use_log=use_log).dropna()
        X = feat_df.drop(columns='y')
        y = feat_df['y'].values

        split      = int(len(X) * 0.85)
        X_tr, X_te = X.iloc[:split], X.iloc[split:]
        y_tr, y_te = y[:split], y[split:]
        if len(X_te) < 5:
            continue

        # ── ฝึก LSTM (Primary) ──────────────────────────────────────────────
        lstm_model, lstm_scaler = None, None
        if LSTM_AVAILABLE and not use_log and len(y_tr) >= LSTM_LOOKBACK + 10:
            print(f"   🧠 [1/3] Training LSTM (Primary) for {room.name} ...")
            lstm_model, lstm_scaler = train_lstm(
                y_tr, y_te, lookback=LSTM_LOOKBACK,
                epochs=LSTM_EPOCHS, patience=LSTM_PATIENCE
            )
            status = "✅ success" if lstm_model else "⚠️  failed"
            print(f"         {status}")
        elif use_log:
            print(f"   ⏭️  [1/3] LSTM skipped (LECTURE)")
        else:
            print(f"   ⚠️  [1/3] LSTM skipped (ข้อมูลน้อย)")

        rob_tag = " [ROBUST+Huber]" if needs_robust else ""
        print(f"   🌿 [2/3] LightGBM (Support){rob_tag}")
        print(f"   ⚡ [3/3] XGBoost   (Support){rob_tag}")

        y_pred_ens, lgb_model, xgb_model, meta_ridge = stacking_predict(
            X_tr, y_tr, X_te, y_te, X_te,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            daily_tr_raw=y_tr, n_pred=len(X_te),
            lstm_lookback=LSTM_LOOKBACK,
            robust=needs_robust,
        )

        if use_log:
            y_te_eval   = np.expm1(y_te)
            y_pred_eval = np.expm1(y_pred_ens)
        else:
            y_te_eval   = y_te.copy()
            y_pred_eval = y_pred_ens.copy()

        y_te_eval   = np.nan_to_num(y_te_eval,   nan=0.0, posinf=0.0, neginf=0.0)
        y_pred_eval = np.nan_to_num(y_pred_eval, nan=0.0, posinf=0.0, neginf=0.0)

        m_r2    = r2_score(y_te_eval, y_pred_eval)
        m_mae   = mean_absolute_error(y_te_eval, y_pred_eval)
        m_rmse  = rmse(y_te_eval, y_pred_eval)
        m_smape = smape(y_te_eval, y_pred_eval)

        # ── R² Fallback Check (ทุกห้อง ไม่จำกัดแค่ robust) ──────────────────────
        seasonal_model = None
        used_fallback  = False
        if m_r2 < R2_FALLBACK_THRESHOLD:
            print(f"   🔄 {room.name}: R²={m_r2:.3f} < {R2_FALLBACK_THRESHOLD} "
                  f"→ ลอง Seasonal Median Fallback")
            seasonal_model = SeasonalMedianModel().fit(daily)
            # eval fallback บน test set
            smed_preds  = seasonal_model.predict_series(
                pd.to_datetime(feat_df.index[split:])
            )
            # blend: 70% seasonal + 15% lgb + 15% xgb (เหมือนใน _build_forecast_bulk)
            lgb_te_raw  = np.maximum(0, lgb_model.predict(X_te))
            xgb_te_raw  = np.maximum(0, xgb_model.predict(X_te))
            blend_eval  = 0.70 * smed_preds + 0.15 * lgb_te_raw + 0.15 * xgb_te_raw
            if use_log:
                blend_eval = np.expm1(blend_eval)
            blend_eval  = np.nan_to_num(blend_eval, nan=0.0, posinf=0.0, neginf=0.0)

            fb_r2    = r2_score(y_te_eval, blend_eval)
            fb_smape = smape(y_te_eval, blend_eval)
            if fb_r2 > m_r2:
                print(f"      ✅ Fallback ดีกว่า: R² {m_r2:.3f} → {fb_r2:.3f}, "
                      f"sMAPE {m_smape:.1f}% → {fb_smape:.1f}%")
                m_r2        = fb_r2
                m_smape     = fb_smape
                m_mae       = mean_absolute_error(y_te_eval, blend_eval)
                m_rmse      = rmse(y_te_eval, blend_eval)
                y_pred_eval = blend_eval
                used_fallback = True
            else:
                print(f"      ℹ️  Fallback ไม่ช่วย (R² {fb_r2:.3f} vs {m_r2:.3f}) – คงใช้ Stacking")
                seasonal_model = None

        peak_ref          = float(daily.quantile(0.95)) or 1.0
        thr_high, thr_med = compute_adaptive_thresholds(daily, peak_ref, problematic=needs_robust)
        confidence        = round(max(0.0, 1.0 - m_smape / 100.0) * 100.0, 1)

        cls_metrics = compute_classification_metrics(
            y_te_eval, y_pred_eval, thr_high, thr_med, peak_ref
        )
        print_classification_metrics(cls_metrics, room.name)

        room_type  = getattr(room, 'room_type', 'unknown').lower()
        lstm_tag   = " +LSTM✓"     if lstm_model     else " [no LSTM]"
        log_tag    = " LOG"        if use_log         else ""
        rob_tag2   = " ROBUST"     if needs_robust    else ""
        fb_tag     = " FALLBACK✓"  if used_fallback   else ""

        all_stats.append({
            'Room':      room.name,
            'Type':      room_type,
            'HasLSTM':   lstm_model is not None,
            'Robust':    needs_robust,
            'Fallback':  used_fallback,
            'R2':        m_r2,
            'MAE':       m_mae,
            'RMSE':      m_rmse,
            'sMAPE':     m_smape,
            'Accuracy':  cls_metrics['accuracy'],
            'F1':        cls_metrics['f1'],
            'Recall':    cls_metrics['recall'],
            'Precision': cls_metrics['precision'],
            'Loss':      cls_metrics['loss'],
        })

        print(
            f"✅ {room.name:.<18} [{room_type:<10}]"
            f"{lstm_tag}{log_tag}{rob_tag2}{fb_tag}"
            f"  R²:{m_r2:.3f}  MAE:{m_mae:.2f}ชม  sMAPE:{m_smape:.1f}%"
            f"  Acc:{cls_metrics['accuracy']:.3f}"
            f"  F1:{cls_metrics['f1']:.3f}"
            f"  Loss:{cls_metrics['loss']:.4f}"
            f"  conf:{confidence:.1f}%"
            f"  thr_h:{thr_high:.3f}  thr_m:{thr_med:.3f}"
        )

        # ── บันทึก models ────────────────────────────────────────────────────
        joblib.dump(lgb_model, os.path.join(MODEL_DIR, f"{room.id}_lgb.pkl"))
        joblib.dump(xgb_model, os.path.join(MODEL_DIR, f"{room.id}_xgb.pkl"))
        if seasonal_model is not None:
            joblib.dump(seasonal_model, os.path.join(MODEL_DIR, f"{room.id}_seasonal.pkl"))
        elif os.path.exists(os.path.join(MODEL_DIR, f"{room.id}_seasonal.pkl")):
            os.remove(os.path.join(MODEL_DIR, f"{room.id}_seasonal.pkl"))

        meta_payload = {
            'peak_ref':      peak_ref,
            'thr_high':      thr_high,
            'thr_med':       thr_med,
            'hour_dist':     room_hour_dist,
            'confidence':    confidence,
            'meta_ridge':    meta_ridge,
            'use_log':       use_log,
            'lstm_lookback': LSTM_LOOKBACK,
            'has_lstm':      lstm_model is not None,
            'robust':        needs_robust,
            'used_fallback': used_fallback,
            'cls_metrics':   cls_metrics,
            'reg_metrics': {
                'r2':    round(m_r2,    4),
                'mae':   round(m_mae,   4),
                'rmse':  round(m_rmse,  4),
                'smape': round(m_smape, 4),
            },
        }
        if lstm_model is not None:
            joblib.dump(lstm_model,  os.path.join(MODEL_DIR, f"{room.id}_lstm.pkl"))
            joblib.dump(lstm_scaler, os.path.join(MODEL_DIR, f"{room.id}_lstm_scaler.pkl"))
        joblib.dump(meta_payload, os.path.join(META_DIR, f"{room.id}_meta.pkl"))

        bulk = _build_forecast_bulk(
            room, lgb_model, xgb_model, meta_ridge, daily.copy(),
            peak_ref, thr_high, thr_med, room_hour_dist, confidence,
            forecast_dates, schedule,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            use_log=use_log, lstm_lookback=LSTM_LOOKBACK,
            seasonal_model=seasonal_model,
        )
        DemandForecast.objects.filter(
            room=room, forecast_date__in=forecast_dates
        ).delete()
        DemandForecast.objects.bulk_create(bulk)

    # ── สรุปผลรวม ──────────────────────────────────────────────────────────────
    df_res = pd.DataFrame(all_stats)
    if len(df_res) > 0:
        lstm_count    = df_res['HasLSTM'].sum()
        robust_count  = df_res['Robust'].sum()
        fallback_count = df_res['Fallback'].sum()
        print(f"\n📊 ── สรุปผลการเทรนทั้งหมด ──")
        print(f"   LSTM (Primary)  : {lstm_count}/{len(df_res)} ห้อง")
        print(f"   Robust+Huber    : {robust_count}/{len(df_res)} ห้อง")
        print(f"   Seasonal Fallbk : {fallback_count}/{len(df_res)} ห้อง")
        print(f"{'Room':<20} {'Type':<12} {'LSTM':>5} {'ROB':>4} {'FB':>3} "
              f"{'R²':>6} {'MAE':>7} {'sMAPE':>7} "
              f"{'Acc':>6} {'F1':>6} {'Recall':>7} {'Prec':>7} {'Loss':>7} {'Conf':>6}")
        print("-" * 120)
        for _, r in df_res.iterrows():
            conf = round(max(0.0, 1.0 - r['sMAPE'] / 100.0) * 100.0, 1)
            print(
                f"  {r['Room']:<18} {r['Type']:<12} "
                f"{'✓' if r['HasLSTM'] else '✗':>5} "
                f"{'✓' if r['Robust']  else '-':>4} "
                f"{'✓' if r['Fallback'] else '-':>3} "
                f"{r['R2']:>6.3f} {r['MAE']:>6.2f}ชม {r['sMAPE']:>6.1f}% "
                f"{r['Accuracy']:>6.3f} {r['F1']:>6.3f} "
                f"{r['Recall']:>7.3f} {r['Precision']:>7.3f} "
                f"{r['Loss']:>7.4f} {conf:>5.1f}%"
            )
        print("-" * 120)
        avg_conf = round(max(0.0, 1.0 - df_res['sMAPE'].mean() / 100.0) * 100.0, 1)
        print(
            f"  {'เฉลี่ย':<18} {'':12} {'':>5} {'':>4} {'':>3} "
            f"{df_res['R2'].mean():>6.3f} "
            f"{df_res['MAE'].mean():>6.2f}ชม "
            f"{df_res['sMAPE'].mean():>6.1f}% "
            f"{df_res['Accuracy'].mean():>6.3f} "
            f"{df_res['F1'].mean():>6.3f} "
            f"{df_res['Recall'].mean():>7.3f} "
            f"{df_res['Precision'].mean():>7.3f} "
            f"{df_res['Loss'].mean():>7.4f} "
            f"{avg_conf:>5.1f}%"
        )

    _print_summary()


def _print_summary():
    print("\n── จำนวน Record ต่อระดับ ──")
    for lvl in ['urgent', 'high', 'medium', 'low']:
        c = DemandForecast.objects.filter(demand_level=lvl).count()
        print(f"  {lvl:8s}: {c:,}")
    print("=" * 60)


def generate_forecast_only():
    print("\n🔄 GENERATE FORECAST ONLY (no retrain)")
    today          = pd.to_datetime('today').date()
    forecast_dates = [today + timedelta(days=d) for d in range(FORECAST_DAYS)]

    raw_qs = Booking.objects.exclude(status='cancelled').values(
        'start_time', 'end_time', 'room_id'
    )
    raw = pd.DataFrame(list(raw_qs))

    if len(raw) > 0:
        for col in ['start_time', 'end_time']:
            raw[col] = pd.to_datetime(raw[col])
            if raw[col].dt.tz is None:
                raw[col] = raw[col].dt.tz_localize('UTC')
            raw[col] = raw[col].dt.tz_convert('Asia/Bangkok')
        raw['duration'] = (raw['end_time'] - raw['start_time']).dt.total_seconds() / 3600
        raw['duration'] = raw['duration'].clip(lower=0.25, upper=12.0)
        raw['date']     = raw['start_time'].dt.date
        raw['hour']     = raw['start_time'].dt.hour
        raw['end_hour'] = raw['end_time'].dt.hour

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

        if 'cls_metrics' in meta:
            print_classification_metrics(meta['cls_metrics'], room.name)

        # โหลด LSTM
        lstm_model, lstm_scaler = None, None
        if meta.get('has_lstm', False) and LSTM_AVAILABLE:
            lp = os.path.join(MODEL_DIR, f"{room.id}_lstm.pkl")
            sp = os.path.join(MODEL_DIR, f"{room.id}_lstm_scaler.pkl")
            if os.path.exists(lp) and os.path.exists(sp):
                lstm_model  = joblib.load(lp)
                lstm_scaler = joblib.load(sp)

        # โหลด Seasonal Fallback (ถ้ามี)
        seasonal_model = None
        sp_path = os.path.join(MODEL_DIR, f"{room.id}_seasonal.pkl")
        if meta.get('used_fallback', False) and os.path.exists(sp_path):
            seasonal_model = joblib.load(sp_path)
            print(f"  📅 {room.name}: ใช้ Seasonal Median Fallback")

        rdf = raw[raw['room_id'] == room.id] if len(raw) > 0 else pd.DataFrame()
        if len(rdf) < MIN_DAYS:
            rdf = raw.copy()

        use_log = meta.get('use_log', False)
        daily = (
            rdf.groupby('date')['duration'].sum()
               .reindex(pd.date_range(rdf['date'].min(),
                                      rdf['date'].max(), freq='D').date,
                        fill_value=0.0)
               .astype(float)
        )
        daily.index = pd.to_datetime(daily.index)
        if use_log:
            daily = daily.clip(upper=meta['peak_ref'])

        schedule = load_term_schedule(room.id)
        bulk = _build_forecast_bulk(
            room, lgb_model, xgb_model, meta_ridge, daily.copy(),
            meta['peak_ref'], meta['thr_high'], meta['thr_med'],
            meta['hour_dist'], meta['confidence'], forecast_dates, schedule,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            use_log=use_log,
            lstm_lookback=meta.get('lstm_lookback', LSTM_LOOKBACK),
            seasonal_model=seasonal_model,
        )
        DemandForecast.objects.filter(
            room=room, forecast_date__in=forecast_dates
        ).delete()
        DemandForecast.objects.bulk_create(bulk)

        mode = "📅 Seasonal+LGB+XGB" if seasonal_model else \
               ("✓ LSTM+LGB+XGB" if lstm_model else "○ LGB+XGB only")
        print(f"  ✅ {room.name} – forecast updated [{mode}]")

    _print_summary()


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 – Update Thai Facilities
# ══════════════════════════════════════════════════════════════════════════════

def update_to_thai_facilities():
    print("🧹 ล้างข้อมูลอุปกรณ์เก่า (เฉพาะตารางเชื่อมโยง)...")
    RoomFacility.objects.all().delete()

    fac_list = [
        'โปรเจกเตอร์', 'ไวท์บอร์ด', 'ระบบเสียง', 'ไมโครโฟนไร้สาย',
        'เครื่องปรับอากาศ', 'WiFi', 'เต้าเสียบไฟฟ้า', 'TV / จอแสดงผล',
        'คอมพิวเตอร์ (สำหรับผู้นำเสนอ)', 'Smart Board', 'กล้องบันทึกการสอน'
    ]
    facility_objs = [Facility.objects.get_or_create(name=name)[0] for name in fac_list]
    count = 0
    for room in Room.objects.all():
        chosen = random.sample(facility_objs, random.randint(4, 7))
        for f in chosen:
            RoomFacility.objects.create(room=room, facility=f)
        count += 1
    print(f"✅ เรียบร้อย! อัปเดตอุปกรณ์ภาษาไทยให้ทั้ง {count} ห้องแล้ว")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 – Boost Thresholds
# ══════════════════════════════════════════════════════════════════════════════

def boost_thresholds():
    print("🚀 กำลังเพิ่มโอกาสเกิดสถานะ 'รีบจองด่วน!'...")
    for room in Room.objects.all():
        meta_path = os.path.join(META_DIR, f"{room.id}_meta.pkl")
        if os.path.exists(meta_path):
            meta = joblib.load(meta_path)
            meta['thr_high'] = 0.55
            meta['thr_med']  = 0.28
            joblib.dump(meta, meta_path)
    print("✅ ปรับเกณฑ์เสร็จแล้ว!")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 – Show Saved Metrics
# ══════════════════════════════════════════════════════════════════════════════

def show_saved_metrics():
    print("\n📊 METRICS ภาพรวมทั้งหมด – ผลการเทรนครั้งล่าสุด")
    print("=" * 75)
    all_stats = []

    for room in Room.objects.all():
        meta_path = os.path.join(META_DIR, f"{room.id}_meta.pkl")
        if not os.path.exists(meta_path):
            continue
        meta = joblib.load(meta_path)
        reg  = meta.get('reg_metrics')
        cls  = meta.get('cls_metrics')
        if reg and cls:
            all_stats.append({
                'Room':      room.name,
                'HasLSTM':   meta.get('has_lstm',      False),
                'Robust':    meta.get('robust',         False),
                'Fallback':  meta.get('used_fallback',  False),
                'R2':        reg['r2'],
                'MAE':       reg['mae'],
                'RMSE':      reg['rmse'],
                'sMAPE':     reg['smape'],
                'Accuracy':  cls['accuracy'],
                'F1':        cls['f1'],
                'Recall':    cls['recall'],
                'Precision': cls['precision'],
                'Loss':      cls['loss'],
                'Conf':      meta.get('confidence', 0),
            })

    if not all_stats:
        print("❌ ไม่พบข้อมูล กรุณารัน --retrain ก่อนครับ"); return

    df = pd.DataFrame(all_stats)
    print(f"\n{'Room':<20} {'LSTM':>5} {'ROB':>4} {'FB':>3} "
          f"{'R²':>6} {'MAE':>7} {'RMSE':>7} {'sMAPE':>7} "
          f"{'Acc':>6} {'F1':>6} {'Recall':>7} {'Prec':>7} {'Loss':>7} {'Conf':>6}")
    print("-" * 118)
    for _, r in df.iterrows():
        print(
            f"  {r['Room']:<18} "
            f"{'✓' if r['HasLSTM'] else '✗':>5} "
            f"{'✓' if r['Robust']  else '-':>4} "
            f"{'✓' if r['Fallback'] else '-':>3} "
            f"{r['R2']:>6.3f} "
            f"{r['MAE']:>6.3f}ชม "
            f"{r['RMSE']:>6.3f}ชม "
            f"{r['sMAPE']:>6.1f}% "
            f"{r['Accuracy']:>6.3f} "
            f"{r['F1']:>6.3f} "
            f"{r['Recall']:>7.3f} "
            f"{r['Precision']:>7.3f} "
            f"{r['Loss']:>7.4f} "
            f"{r['Conf']:>5.1f}%"
        )
    print("-" * 118)
    print(
        f"  {'📊 เฉลี่ย':<18} {'':>5} {'':>4} {'':>3} "
        f"{df['R2'].mean():>6.3f} "
        f"{df['MAE'].mean():>6.3f}ชม "
        f"{df['RMSE'].mean():>6.3f}ชม "
        f"{df['sMAPE'].mean():>6.1f}% "
        f"{df['Accuracy'].mean():>6.3f} "
        f"{df['F1'].mean():>6.3f} "
        f"{df['Recall'].mean():>7.3f} "
        f"{df['Precision'].mean():>7.3f} "
        f"{df['Loss'].mean():>7.4f} "
        f"{df['Conf'].mean():>5.1f}%"
    )
    print("=" * 118)

    print(f"\n🧠 LSTM (Primary)  : {df['HasLSTM'].sum()}/{len(df)} ห้อง")
    print(f"🔧 Robust+Huber    : {df['Robust'].sum()}/{len(df)} ห้อง")
    print(f"📅 Seasonal Fallbk : {df['Fallback'].sum()}/{len(df)} ห้อง")
    print(f"🏆 R² ดีที่สุด    : {df.loc[df['R2'].idxmax(), 'Room']}  ({df['R2'].max():.4f})")
    print(f"⚠️  R² ต่ำที่สุด   : {df.loc[df['R2'].idxmin(), 'Room']}  ({df['R2'].min():.4f})")
    print(f"🏆 Accuracy สูงสุด : {df.loc[df['Accuracy'].idxmax(), 'Room']}  ({df['Accuracy'].max():.4f})")
    print(f"🏆 Loss ต่ำสุด     : {df.loc[df['Loss'].idxmin(), 'Room']}  ({df['Loss'].min():.4f})")

    avg_r2  = df['R2'].mean()
    avg_acc = df['Accuracy'].mean()
    avg_f1  = df['F1'].mean()
    print(f"\n📋 ประเมินภาพรวมโมเดล")
    print(f"   R²       : {'✅ ดีมาก' if avg_r2  >= 0.8 else '⚠️  พอใช้' if avg_r2  >= 0.5 else '❌ ต่ำ'} ({avg_r2:.3f})")
    print(f"   Accuracy : {'✅ ดีมาก' if avg_acc >= 0.8 else '⚠️  พอใช้' if avg_acc >= 0.6 else '❌ ต่ำ'} ({avg_acc:.3f})")
    print(f"   F1 Score : {'✅ ดีมาก' if avg_f1  >= 0.8 else '⚠️  พอใช้' if avg_f1  >= 0.6 else '❌ ต่ำ'} ({avg_f1:.3f})")
    print("=" * 75)


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='All-in-One: Demand Forecast (Stacking Ensemble) + Facilities + Threshold Boost'
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--retrain',      action='store_true')
    group.add_argument('--update-fac',   action='store_true')
    group.add_argument('--boost',        action='store_true')
    group.add_argument('--show-metrics', action='store_true')
    args = parser.parse_args()

    if args.retrain:
        retrain_and_forecast()
    elif args.update_fac:
        update_to_thai_facilities()
    elif args.boost:
        boost_thresholds()
        generate_forecast_only()
    elif args.show_metrics:
        show_saved_metrics()
    else:
        generate_forecast_only()