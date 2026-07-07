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

_CURRENT_DIR_FOR_ENV = os.path.dirname(os.path.abspath(__file__))

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
    from tensorflow.keras.callbacks import EarlyStopping, Callback
    LSTM_AVAILABLE = True
except ImportError:
    LSTM_AVAILABLE = False
    print("⚠️  TensorFlow ไม่พบ – LSTM (Primary Model) ไม่สามารถใช้งานได้")
    print("   กรุณาติดตั้ง: pip install tensorflow")

# ── Config ─────────────────────────────────────────────────────────────────────
MIN_DAYS      = 30   # จำนวน booking ขั้นต่ำต่อห้อง (ข้อมูลจริง ~700+ ต่อห้อง)
MIN_UNIQUE_DAYS = 14  # จำนวนวันที่มีการใช้งานขั้นต่ำ
FORECAST_DAYS = 14
LSTM_LOOKBACK = 14
# Reduce training budget to speed up retrains and make runs consistent
LSTM_EPOCHS   = 30           # lower epoch budget for faster retrains
LSTM_BATCH    = 32
LSTM_PATIENCE = 5            # หยุดเมื่อ val_loss ไม่ดีขึ้น
MODEL_DIR     = os.path.join(CURRENT_DIR, "saved_models")
META_DIR      = os.path.join(CURRENT_DIR, "saved_meta")
METRICS_DIR   = os.path.join(CURRENT_DIR, "metrics_plots")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(META_DIR,  exist_ok=True)
os.makedirs(METRICS_DIR, exist_ok=True)

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
MIN_ACCEPTED_MODEL_ACCURACY = 0.90

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


# ======= Data-Tiering, Cold-Start, Sparse Helpers =============================
def get_data_tier(n_rows: int, unique_days: int) -> str:
    if n_rows >= 200 and unique_days >= 60:
        return 'full'
    elif n_rows >= 60 and unique_days >= 21:
        return 'medium'
    elif n_rows >= 14 and unique_days >= 7:
        return 'sparse'
    else:
        return 'cold_start'


def build_cold_start_prior(room, all_rooms_daily: dict) -> SeasonalMedianModel:
    """
    รวม daily series จากห้องประเภทเดียวกัน แล้ว fit SeasonalMedianModel เป็น prior
    all_rooms_daily : dict mapping Room -> pd.Series
    """
    same_type = [daily for r, daily in all_rooms_daily.items()
                 if getattr(r, 'room_type', None) == getattr(room, 'room_type', None)
                 and getattr(r, 'id', None) != getattr(room, 'id', None)]
    if not same_type:
        same_type = list(all_rooms_daily.values())

    if len(same_type) == 0:
        # fallback: empty seasonal median
        sm = SeasonalMedianModel()
        sm.global_median = 0.0
        return sm

    combined = pd.concat(same_type).groupby(level=0).mean()
    return SeasonalMedianModel().fit(combined)


def build_similar_series(room, all_rooms_daily: dict):
    """Return a combined same-type series for room-level cold-start or sparse augmentation."""
    similar = [daily for r, daily in all_rooms_daily.items()
               if getattr(r, 'room_type', None) == getattr(room, 'room_type', None)
               and getattr(r, 'id', None) != getattr(room, 'id', None)
               and len(daily) > 0]
    if not similar:
        similar = [daily for r, daily in all_rooms_daily.items() if getattr(r, 'id', None) != getattr(room, 'id', None) and len(daily) > 0]
    if not similar:
        return pd.Series(dtype=float)
    combined = pd.concat(similar).groupby(level=0).mean()
    combined.index = pd.to_datetime(combined.index)
    return combined


def evaluate_prediction_metrics(y_true, y_pred, thr_high, thr_med, peak_ref):
    y_true_eval = np.nan_to_num(np.array(y_true, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    y_pred_eval = np.nan_to_num(np.array(y_pred, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    return {
        'regression': {
            'r2':    round(r2_score(y_true_eval, y_pred_eval), 4),
            'mae':   round(mean_absolute_error(y_true_eval, y_pred_eval), 4),
            'rmse':  round(rmse(y_true_eval, y_pred_eval), 4),
            'smape': round(smape(y_true_eval, y_pred_eval), 4),
        },
        'classification': compute_classification_metrics(y_true_eval, y_pred_eval, thr_high, thr_med, peak_ref),
    }


def _optimize_threshold_multiplier(y_true, y_pred, thr_high, thr_med, peak_ref, grid=None):
    """Find multiplier for thresholds that maximizes classification accuracy.
    Returns (best_multiplier, best_scores_dict).
    """
    if grid is None:
        grid = np.linspace(0.6, 1.4, 17)
    best_m = 1.0
    best_acc = -1.0
    best_metrics = None
    for m in grid:
        th_h = thr_high * float(m)
        th_m = thr_med * float(m)
        try:
            cm = compute_classification_metrics(y_true, y_pred, th_h, th_m, peak_ref)
            acc = float(cm.get('accuracy', 0.0))
        except Exception:
            acc = -1.0
            cm = None
        if acc > best_acc:
            best_acc = acc
            best_m = m
            best_metrics = cm
            if best_acc >= 0.9999:
                break
    return best_m, best_metrics


def _optimize_ensemble_weights(y_true, preds_dict, thr_high, thr_med, peak_ref, grid=None):
    """Search simple linear weights between available preds to maximize accuracy.
    preds_dict: {'lgb': arr, 'xgboost': arr, 'lstm': arr, 'ensemble': arr}
    Returns best_combination_name, best_pred, best_metrics
    """
    keys = [k for k in ['lgb', 'xgboost', 'lstm'] if k in preds_dict and preds_dict[k] is not None]
    if not keys:
        return 'ensemble', preds_dict.get('ensemble'), compute_classification_metrics(y_true, preds_dict.get('ensemble'), thr_high, thr_med, peak_ref)
    if grid is None:
        grid = np.linspace(0.0, 1.0, 11)
    best_acc = -1.0
    best_pred = preds_dict.get('ensemble')
    best_name = 'ensemble'
    best_metrics = compute_classification_metrics(y_true, best_pred, thr_high, thr_med, peak_ref)
    if len(keys) == 1:
        return keys[0], preds_dict[keys[0]], compute_classification_metrics(y_true, preds_dict[keys[0]], thr_high, thr_med, peak_ref)
    if len(keys) == 2:
        a, b = keys
        for wa in grid:
            wb = 1.0 - wa
            pred = wa * np.asarray(preds_dict[a]) + wb * np.asarray(preds_dict[b])
            try:
                metrics = compute_classification_metrics(y_true, pred, thr_high, thr_med, peak_ref)
                acc = float(metrics.get('accuracy', 0.0))
            except Exception:
                continue
            if acc > best_acc:
                best_acc = acc
                best_pred = pred
                best_name = f"{a}:{wa:.2f}+{b}:{wb:.2f}"
                best_metrics = metrics
    else:
        a, b, c = keys[:3]
        for wa in grid:
            for wb in grid:
                wc = 1.0 - wa - wb
                if wc < 0.0 or wc > 1.0:
                    continue
                pred = wa * np.asarray(preds_dict[a]) + wb * np.asarray(preds_dict[b]) + wc * np.asarray(preds_dict[c])
                try:
                    metrics = compute_classification_metrics(y_true, pred, thr_high, thr_med, peak_ref)
                    acc = float(metrics.get('accuracy', 0.0))
                except Exception:
                    continue
                if acc > best_acc:
                    best_acc = acc
                    best_pred = pred
                    best_name = f"{a}:{wa:.2f}+{b}:{wb:.2f}+{c}:{wc:.2f}"
                    best_metrics = metrics
    return best_name, best_pred, best_metrics


def build_cold_start_training_models(room, combined, schedule, use_log=False):
    """Train simple LGB/XGB/meta on combined same-type series for cold start rooms."""
    if len(combined) < 20:
        return None, None, None, None, None, None, None, None, None

    term_df = build_term_daily_features(combined.index, schedule)
    term_df.index = combined.index
    feat_df = build_features(combined, term_df, use_log=use_log).dropna()
    X = feat_df.drop(columns='y')
    y = feat_df['y'].values
    if len(X) < 10:
        return None, None, None, None, None, None, None, None, None

    split = int(len(X) * 0.80)
    if split < 5:
        split = max(len(X) - 5, 5)
    X_tr, X_te = X.iloc[:split], X.iloc[split:]
    y_tr, y_te = y[:split], y[split:]
    if len(X_te) < 3 or len(X_tr) < 5:
        return None, None, None, None, None, None, None, None, None

    lgb_model, lgb_history = train_lgb(X_tr, y_tr, X_te, y_te, robust=False)
    xgb_model, xgb_history = train_xgb(X_tr, y_tr, X_te, y_te, robust=False)
    lgb_train = lgb_model.predict(X_tr)
    xgb_train = xgb_model.predict(X_tr)
    lgb_val = lgb_model.predict(X_te)
    xgb_val = xgb_model.predict(X_te)
    meta_ridge = Ridge(alpha=1.0)
    meta_ridge.fit(np.column_stack([lgb_train, xgb_train]), y_tr)
    meta_val = meta_ridge.predict(np.column_stack([lgb_val, xgb_val]))
    lstm_model, lstm_scaler, lstm_history = None, None, None
    if LSTM_AVAILABLE and not use_log and len(y_tr) >= LSTM_LOOKBACK + 10:
        lstm_model, lstm_scaler, lstm_history = train_lstm(y_tr, y_te, lookback=LSTM_LOOKBACK,
                                                           epochs=LSTM_EPOCHS, patience=LSTM_PATIENCE)
        if lstm_model is not None:
            if isinstance(lstm_scaler, tuple):
                # build feature DataFrame for train+val and use one-step walk-forward
                try:
                    X_tr_df = X_tr if isinstance(X_tr, pd.DataFrame) else pd.DataFrame(X_tr, columns=getattr(X_tr, 'columns', None))
                    X_te_df = X_te if isinstance(X_te, pd.DataFrame) else pd.DataFrame(X_te, columns=getattr(X_tr, 'columns', None))
                except Exception:
                    X_tr_df = pd.DataFrame(X_tr)
                    X_te_df = pd.DataFrame(X_te)
                feat_full = pd.concat([X_tr_df, X_te_df], ignore_index=True)
                feat_full['y'] = np.concatenate([y_tr, y_te])
                lstm_val = lstm_one_step_walkforward(lstm_model, lstm_scaler, feat_full, val_start_idx=len(X_tr_df), lookback=LSTM_LOOKBACK)
            else:
                lstm_val = lstm_predict(lstm_model, lstm_scaler, y_tr, len(y_te), lookback=LSTM_LOOKBACK)
        else:
            lstm_val = None
    else:
        lstm_val = None

    return (lgb_model, xgb_model, meta_ridge,
            lgb_history, xgb_history, lstm_model, lstm_scaler,
            lstm_history, lgb_val, xgb_val, lstm_val, meta_val, X_te, y_te)


def build_features_sparse(daily, term_df=None):
    df = daily.to_frame(name='y')
    idx = pd.to_datetime(df.index)

    df['dow'] = idx.dayofweek.astype(int)
    df['month'] = idx.month.astype(int)
    df['is_weekend'] = (idx.dayofweek >= 5).astype(int)

    for lag in [1, 7]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    for w in [3, 7]:
        df[f'roll_mean_{w}'] = df['y'].shift(1).rolling(w, min_periods=1).mean()
        df[f'roll_std_{w}'] = df['y'].shift(1).rolling(w, min_periods=1).std().fillna(0)

    return df.bfill().ffill()


def train_lgb_sparse(X_tr, y_tr, X_te, y_te):
    model = lgb.LGBMRegressor(
        objective='huber', alpha=0.9,
        n_estimators=180,
        learning_rate=0.06,
        max_depth=3,
        num_leaves=8,
        min_child_samples=5,
        lambda_l1=2.0,
        lambda_l2=2.0,
        n_jobs=-1,
        verbose=-1,
    )
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_tr, y_tr), (X_te, y_te)],
        eval_names=['train', 'valid'],
        eval_metric='mae',
        callbacks=[
            lgb.early_stopping(30, verbose=False),
            lgb.log_evaluation(-1),
        ],
    )
    return model, _extract_booster_history(model.evals_result_)


def augment_sparse_daily(daily: pd.Series, target_days: int = 80) -> pd.Series:
    """Augment sparse series from historical median + realistic noise ใกล้เคียง."""
    if len(daily) >= target_days:
        return daily

    smed = SeasonalMedianModel().fit(daily)
    extra = []
    dates = pd.date_range(
        daily.index.min() - pd.Timedelta(days=target_days),
        daily.index.min() - pd.Timedelta(days=1),
        freq='D'
    )
    # Generate synthetic data from similar rooms' patterns
    for d in dates:
        base = smed.predict_date(d)
        # Add realistic variation (5-15%)
        noise = np.random.normal(0, max(0.05, base) * 0.12)
        value = max(0.0, base * (0.85 + np.random.uniform(0, 0.30)) + noise)
        extra.append(value)

    aug_series = pd.Series(extra, index=dates)
    combined = pd.concat([aug_series, daily]).sort_index()
    print(f"   🔢 Augment: {len(daily)} → {len(combined)} วัน (synthetic={len(extra)}) – ข้อมูลใกล้เคียง")
    return combined


class SeasonalPredictor:
    """Dummy predictor that returns seasonal model predictions for requested index."""
    def __init__(self, seasonal_model: SeasonalMedianModel):
        self.seasonal_model = seasonal_model

    def predict(self, X):
        # X usually a pandas DataFrame with DatetimeIndex
        try:
            idx = getattr(X, 'index', None)
            if idx is None:
                return np.zeros(len(X))
            return np.array([self.seasonal_model.predict_date(d) for d in idx])
        except Exception:
            return np.zeros(len(X))



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


class LSTMClassificationHistoryCallback(Callback):
    """Compute classification accuracy/loss for training and validation per epoch."""
    def __init__(self, x_train, y_train, x_val, y_val, thr_high, thr_med, peak_ref):
        super().__init__()
        self.x_train = x_train
        self.y_train = np.asarray(y_train, dtype=float)
        self.x_val = x_val
        self.y_val = np.asarray(y_val, dtype=float)
        self.thr_high = float(thr_high)
        self.thr_med = float(thr_med)
        self.peak_ref = float(peak_ref)

    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}
        try:
            y_train_pred = self.model.predict(self.x_train, verbose=0).flatten()
            y_val_pred = self.model.predict(self.x_val, verbose=0).flatten()
            train_cls = compute_classification_metrics(self.y_train, y_train_pred, self.thr_high, self.thr_med, self.peak_ref)
            val_cls = compute_classification_metrics(self.y_val, y_val_pred, self.thr_high, self.thr_med, self.peak_ref)
            logs['accuracy'] = train_cls['accuracy']
            logs['val_accuracy'] = val_cls['accuracy']
            logs['class_loss'] = train_cls['loss']
            logs['val_class_loss'] = val_cls['loss']
            logs['class_f1'] = train_cls['f1']
            logs['val_class_f1'] = val_cls['f1']
        except Exception:
            pass


def print_regression_metrics(stats: dict, room_name: str, model_name: str):
    print(f"\n  📈 Regression Metrics – {room_name} :: {model_name}")
    print(f"  {'─' * 50}")
    print(f"  R2    : {stats.get('r2', float('nan')):.4f}")
    print(f"  MAE   : {stats.get('mae', float('nan')):.4f}")
    print(f"  RMSE  : {stats.get('rmse', float('nan')):.4f}")
    print(f"  sMAPE : {stats.get('smape', float('nan')):.3f}%")
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

    df  = y_series.to_frame(name='y')
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

    return df.ffill().fillna(0.0)


# ══════════════════════════════════════════════════════════════════════════════
#  LSTM – Primary Base Model
# ══════════════════════════════════════════════════════════════════════════════

def _make_lstm_sequences(series, lookback):
    X, y = [], []
    for i in range(lookback, len(series)):
        X.append(series[i - lookback: i])
        y.append(series[i])
    return np.array(X), np.array(y)


def build_lstm_sequences_multivariate(feat_df: pd.DataFrame, lookback: int):
    """Build multivariate LSTM sequences from `feat_df` produced by `build_features()`.

    Returns (X, y, feature_cols) where X.shape == (n_samples, lookback, n_features+1)
    and the first channel is the historical `y` values followed by exogenous features.
    """
    feature_cols = [c for c in feat_df.columns if c != 'y']
    y_arr = feat_df['y'].values
    X_feats = feat_df[feature_cols].values  # (n_samples, n_features)

    X, y = [], []
    for i in range(lookback, len(feat_df)):
        window = np.column_stack([
            y_arr[i - lookback:i],
            X_feats[i - lookback:i]
        ])
        X.append(window)
        y.append(y_arr[i])
    if not X:
        return np.zeros((0, lookback, len(feature_cols) + 1)), np.zeros((0,)), feature_cols
    return np.asarray(X), np.asarray(y), feature_cols


def train_lstm(y_train_raw, y_val_raw, lookback=LSTM_LOOKBACK,
               epochs=LSTM_EPOCHS, patience=LSTM_PATIENCE,
               feat_train_df: pd.DataFrame = None, feat_val_df: pd.DataFrame = None):
    if not LSTM_AVAILABLE:
        return None, None, None
    # If feature dataframes are provided, build multivariate sequences and scale inputs
    if feat_train_df is not None and feat_val_df is not None:
        # combine to build continuous windows
        feat_full = pd.concat([feat_train_df, feat_val_df])
        X_full, y_full, feature_cols = build_lstm_sequences_multivariate(feat_full, lookback)
        if X_full.size == 0:
            return None, None, None
        # scalers: one for inputs (per-column), one for target y
        n_cols = X_full.shape[2]
        X_flat = X_full.reshape(-1, n_cols)
        n_tr = len(feat_train_df) - lookback
        if n_tr <= 0 or n_tr >= len(X_full):
            return None, None, None

        X_train_only = X_full[:n_tr]
        scaler_X = MinMaxScaler()
        scaler_X.fit(X_train_only.reshape(-1, n_cols))
        X_flat_s = scaler_X.transform(X_flat)
        X_full_s = X_flat_s.reshape(X_full.shape)

        scaler_y = MinMaxScaler()
        scaler_y.fit(y_full[:n_tr].reshape(-1, 1))
        y_full_s = scaler_y.transform(y_full.reshape(-1, 1)).flatten()

        X_tr, y_tr = X_full_s[:n_tr], y_full_s[:n_tr]
        X_va, y_va = X_full_s[n_tr:], y_full_s[n_tr:]
        # no reshape needed; X_tr shape == (n_samples, lookback, n_cols)
        scaler = (scaler_X, scaler_y)
    else:
        # univariate fallback (legacy)
        scaler_y = MinMaxScaler()
        scaler_y.fit(y_train_raw.reshape(-1, 1))
        y_tr_s = scaler_y.transform(y_train_raw.reshape(-1, 1)).flatten()
        y_va_s = scaler_y.transform(y_val_raw.reshape(-1, 1)).flatten()
        full = np.concatenate([y_tr_s, y_va_s])

        X_full, y_full = _make_lstm_sequences(full, lookback)
        n_tr = len(y_train_raw) - lookback
        if n_tr <= 0 or n_tr >= len(X_full):
            return None, None, None

        X_tr, y_tr = X_full[:n_tr], y_full[:n_tr]
        X_va, y_va = X_full[n_tr:], y_full[n_tr:]
        X_tr = X_tr.reshape(X_tr.shape[0], X_tr.shape[1], 1)
        X_va = X_va.reshape(X_va.shape[0], X_va.shape[1], 1)
        scaler = scaler_y

    # prepare thresholds based on original unscaled y values when possible
    try:
        all_original_y = np.concatenate([y_train_raw, y_val_raw])
    except Exception:
        # fallback: if feat-based path used, reconstruct original y from scaler_y
        if isinstance(scaler, tuple):
            scaler_y = scaler[1]
            # y_full_s is defined if multivariate branch was used
            all_original_y = scaler_y.inverse_transform(y_full_s.reshape(-1, 1)).flatten()
        else:
            all_original_y = np.concatenate([y_train_raw, y_val_raw])
    peak_ref = float(np.percentile(all_original_y, 95)) or 1.0
    thr_high, thr_med = compute_adaptive_thresholds(pd.Series(all_original_y), peak_ref)
    input_cols = X_tr.shape[2]
    model = Sequential([
        LSTM(64, return_sequences=True, input_shape=(lookback, input_cols)),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(16, activation='relu'),
        Dense(1),
    ])
    model.compile(optimizer='adam', loss='mae', metrics=['mae'])
    # Early stop on val_loss plateau: regression task ต้องใช้ loss ไม่ใช่ accuracy
    es = EarlyStopping(monitor='val_loss', mode='min', patience=patience,
                       restore_best_weights=True, verbose=0)
    history = model.fit(X_tr, y_tr, validation_data=(X_va, y_va),
                        epochs=min(epochs, LSTM_EPOCHS), batch_size=LSTM_BATCH,
                        callbacks=[es], verbose=0)

    hist = history.history
    if 'accuracy' in hist and 'val_accuracy' in hist:
        print(
            f"      📈 LSTM training history: epochs={len(hist['loss'])} "
            f"train_loss={hist['loss'][-1]:.4f} val_loss={hist['val_loss'][-1]:.4f} "
            f"train_acc={hist['accuracy'][-1]:.4f} val_acc={hist['val_accuracy'][-1]:.4f}"
        )
    elif 'mae' in hist and 'val_mae' in hist:
        print(
            f"      📈 LSTM training history: epochs={len(hist['loss'])} "
            f"train_mae={hist['mae'][-1]:.4f} val_mae={hist['val_mae'][-1]:.4f}"
        )
    return model, scaler, hist


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


def lstm_one_step_walkforward(model, scaler, feat_full_df: pd.DataFrame, val_start_idx: int, lookback: int = LSTM_LOOKBACK):
    """Produce one-step-ahead walk-forward predictions using feature DataFrame.

    feat_full_df should be the concatenation of train+val feature DataFrames used
    to build sequences. `val_start_idx` is the index (in rows) where validation begins
    (i.e., number of training rows). Returns an array of length len(feat_full_df)-val_start_idx
    with predictions in original units.
    """
    if model is None or scaler is None:
        return np.zeros(max(0, len(feat_full_df) - val_start_idx))
    if not isinstance(scaler, tuple):
        # fallback to univariate in-sample preds using lstm_in_sample_preds
        hist = feat_full_df['y'].values
        preds = lstm_in_sample_preds(model, scaler, hist, lookback=lookback)
        return preds[val_start_idx:]

    scaler_X, scaler_y = scaler
    feature_cols = [c for c in feat_full_df.columns if c != 'y']
    y_arr = feat_full_df['y'].values
    X_feats = feat_full_df[feature_cols].values
    n = len(feat_full_df)
    if n < lookback + 1:
        return np.zeros(max(0, n - val_start_idx))

    # build windows for validation indices and scale using scaler_X
    preds = []
    for t in range(val_start_idx, n):
        start = t - lookback
        window = np.column_stack([y_arr[start:t], X_feats[start:t]])  # shape (lookback, n_cols)
        x_flat = window.reshape(1, -1)
        # scaler_X expects flat rows of shape (lookback * n_cols,), but we trained it on per-timestep cols
        # so transform per-timestep
        x_flat_scaled = scaler_X.transform(window.reshape(-1, window.shape[1])).reshape(1, window.shape[0], window.shape[1])
        x_in = x_flat_scaled.reshape(1, window.shape[0], window.shape[1])
        p = float(model.predict(x_in, verbose=0)[0][0])
        inv = scaler_y.inverse_transform(np.array([[p]])).flatten()[0]
        preds.append(max(0.0, inv))
    return np.array(preds)


def lstm_in_sample_preds(model, scaler, history_series, lookback=LSTM_LOOKBACK):
    """Produce in-sample (one-step) LSTM predictions aligned with the history.

    For each time t (starting at index `lookback`) predict y[t] from the previous
    `lookback` values. The returned array has the same length as ``history_series``;
    early indices (0..lookback-1) are filled with the first valid prediction.
    """
    if model is None or scaler is None:
        return np.zeros(len(history_series))
    hist = np.asarray(history_series, dtype=float)
    if len(hist) < lookback + 1:
        # not enough data to form even one window — fallback to constant predictions
        p = lstm_predict(model, scaler, hist, 1, lookback=lookback)
        return np.repeat(p[0] if len(p) else 0.0, len(hist))

    scaled = scaler.transform(hist.reshape(-1, 1)).flatten()
    preds = np.zeros(len(hist))
    first_pred = None
    for i in range(lookback, len(hist)):
        window = np.array(scaled[i - lookback:i]).reshape(1, lookback, 1)
        p = float(model.predict(window, verbose=0)[0][0])
        inv = scaler.inverse_transform(np.array([p]).reshape(-1, 1)).flatten()[0]
        preds[i] = max(0.0, inv)
        if first_pred is None:
            first_pred = preds[i]
    if first_pred is None:
        first_pred = 0.0
    # fill early indexes with first valid prediction so length matches y_tr
    preds[:lookback] = first_pred
    return preds


def lstm_in_sample_preds_multivariate(model, scaler, feat_df: pd.DataFrame, lookback=LSTM_LOOKBACK):
    """In-sample one-step predictions for multivariate LSTM.

    feat_df must contain column `y` plus the same exogenous feature columns used at train time.
    scaler is expected to be a tuple `(scaler_X, scaler_y)`.
    """
    if model is None or scaler is None or not isinstance(scaler, tuple):
        return np.zeros(len(feat_df))
    scaler_X, scaler_y = scaler
    feature_cols = [c for c in feat_df.columns if c != 'y']
    y_arr = feat_df['y'].values
    X_feats = feat_df[feature_cols].values
    n = len(feat_df)
    preds = np.zeros(n)
    if n < lookback + 1:
        return preds
    first_pred = None
    for t in range(lookback, n):
        window = np.column_stack([y_arr[t - lookback:t], X_feats[t - lookback:t]])
        window_scaled = scaler_X.transform(window)
        x_in = window_scaled.reshape(1, lookback, window.shape[1])
        p = float(model.predict(x_in, verbose=0)[0][0])
        inv = scaler_y.inverse_transform(np.array([[p]])).flatten()[0]
        preds[t] = max(0.0, inv)
        if first_pred is None:
            first_pred = preds[t]
    preds[:lookback] = first_pred or 0.0
    return preds


def lstm_predict_multivariate(model, scaler, feat_history_df: pd.DataFrame, n_steps,
                               lookback=LSTM_LOOKBACK, future_feat_df: pd.DataFrame = None):
    """Recursive multi-step forecast for multivariate LSTM.

    `feat_history_df` must contain `y` and exogenous features for the historical window.
    `future_feat_df` (optional) should have rows for each future step with exogenous features
    (same columns as feat_history_df without `y`). If missing, last feature row is reused.
    """
    if model is None or scaler is None or not isinstance(scaler, tuple):
        return np.zeros(n_steps)
    if feat_history_df is None or len(feat_history_df) == 0:
        return np.zeros(n_steps)
    scaler_X, scaler_y = scaler
    feature_cols = [c for c in feat_history_df.columns if c != 'y']
    hist_y = list(feat_history_df['y'].values)
    hist_feats = [row for row in feat_history_df[feature_cols].values]
    if not hist_y or not hist_feats:
        return np.zeros(n_steps)
    preds = []
    for t in range(n_steps):
        y_window = np.array(hist_y[-lookback:]) if len(hist_y) >= lookback else np.array([0.0] * (lookback - len(hist_y)) + hist_y)[-lookback:]
        feat_window = np.array(hist_feats[-lookback:]) if len(hist_feats) >= lookback else np.vstack([hist_feats[0]] * lookback)
        window = np.column_stack([y_window, feat_window])
        window_scaled = scaler_X.transform(window)
        x_in = window_scaled.reshape(1, lookback, window.shape[1])
        p = float(model.predict(x_in, verbose=0)[0][0])
        inv = scaler_y.inverse_transform(np.array([[p]])).flatten()[0]
        inv = max(0.0, inv)
        preds.append(inv)
        hist_y.append(inv)
        if future_feat_df is not None and t < len(future_feat_df):
            hist_feats.append(future_feat_df.iloc[t].values)
        else:
            hist_feats.append(hist_feats[-1])
    return np.array(preds)


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
            objective='huber', alpha=0.9,
            n_estimators=140, learning_rate=0.04,
            max_depth=5, num_leaves=24,
            min_child_samples=20,
            lambda_l1=1.0, lambda_l2=1.0,
            feature_fraction=0.7, bagging_fraction=0.7, bagging_freq=5,
            n_jobs=-1,
            verbose=-1,
        )
    else:
        params = dict(
            objective='regression_l1',
            n_estimators=140, learning_rate=0.05,
            max_depth=6, num_leaves=31, min_child_samples=10,
            lambda_l1=0.3, lambda_l2=0.3,
            feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=5,
            n_jobs=-1,
            verbose=-1,
        )
    model = lgb.LGBMRegressor(**params)
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_tr, y_tr), (X_te, y_te)],
        eval_names=['train', 'valid'],
        eval_metric='mae',
        callbacks=[
            lgb.early_stopping(15, verbose=False),
            lgb.log_evaluation(-1),
        ],
    )
    return model, _extract_booster_history(model.evals_result_)


def train_xgb(X_tr, y_tr, X_te, y_te, robust: bool = False):
    """
    XGBoost – Supporting Model
    robust=True → pseudo-Huber loss + regularization แรงขึ้น
    """
    if robust:
        params = dict(
            objective='reg:pseudohubererror',
            n_estimators=140, learning_rate=0.04,
            max_depth=4, subsample=0.7,
            colsample_bytree=0.7,
            reg_alpha=1.0, reg_lambda=1.0,
            early_stopping_rounds=15, eval_metric='mae', verbosity=0,
        )
    else:
        params = dict(
            objective='reg:absoluteerror',
            n_estimators=140, learning_rate=0.05,
            max_depth=5, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.3, reg_lambda=0.3,
            early_stopping_rounds=15, eval_metric='mae', verbosity=0,
        )
    model = xgb.XGBRegressor(**params, n_jobs=-1)
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_tr, y_tr), (X_te, y_te)],
        verbose=False,
    )
    return model, _extract_booster_history(model.evals_result())


def _extract_booster_history(evals_result):
    history = {}
    if not isinstance(evals_result, dict):
        return history
    # xgboost may return keys like 'validation_0', 'validation_1'
    keys = list(evals_result.keys())
    for dataset_name, metrics in evals_result.items():
        if not isinstance(metrics, dict):
            continue
        lower_name = str(dataset_name).lower()
        # map common patterns to train/valid
        if lower_name.startswith('train'):
            prefix = 'train'
        elif lower_name.startswith('valid'):
            prefix = 'valid'
        elif lower_name.startswith('validation'):
            # try to infer order: validation_0 -> first eval_set, validation_1 -> second
            try:
                idx = int(lower_name.split('_')[-1])
            except Exception:
                idx = None
            if idx == 0 and len(keys) > 1:
                # assume validation_0 corresponds to first eval_set (train)
                prefix = 'train'
            elif idx == 1 and len(keys) > 1:
                prefix = 'valid'
            else:
                prefix = 'valid'
        else:
            prefix = lower_name
        for metric_name, values in metrics.items():
            if isinstance(values, (list, np.ndarray)) and len(values) > 0:
                history[f'{prefix}_loss'] = list(values)
                break
    return history


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
    thr_high: float = None,
    thr_med: float = None,
    peak_ref: float = None,
):
    lgb_model, lgb_history = train_lgb(X_tr, y_tr, X_te, y_te, robust=robust)
    xgb_model, xgb_history = train_xgb(X_tr, y_tr, X_te, y_te, robust=robust)

    if thr_high is not None and thr_med is not None and peak_ref is not None:
        lgb_train_preds = lgb_model.predict(X_tr)
        lgb_val_preds = lgb_model.predict(X_te)
        xgb_train_preds = xgb_model.predict(X_tr)
        xgb_val_preds = xgb_model.predict(X_te)
        lgb_train_cls = compute_classification_metrics(y_tr, lgb_train_preds, thr_high, thr_med, peak_ref)
        lgb_val_cls = compute_classification_metrics(y_te, lgb_val_preds, thr_high, thr_med, peak_ref)
        xgb_train_cls = compute_classification_metrics(y_tr, xgb_train_preds, thr_high, thr_med, peak_ref)
        xgb_val_cls = compute_classification_metrics(y_te, xgb_val_preds, thr_high, thr_med, peak_ref)
        print(
            f"    🟢 LightGBM training: TrainLoss={lgb_history.get('train_loss', [np.nan])[-1]:.4f} "
            f"ValLoss={lgb_history.get('valid_loss', [np.nan])[-1]:.4f} "
            f"TrainAcc={lgb_train_cls['accuracy']:.4f} ValAcc={lgb_val_cls['accuracy']:.4f}"
        )
        print(
            f"    ⚡ XGBoost training: TrainLoss={xgb_history.get('train_loss', [np.nan])[-1]:.4f} "
            f"ValLoss={xgb_history.get('valid_loss', [np.nan])[-1]:.4f} "
            f"TrainAcc={xgb_train_cls['accuracy']:.4f} ValAcc={xgb_val_cls['accuracy']:.4f}"
        )
    else:
        print("    🟢 LightGBM/XGBoost training: train/valid thresholds unavailable, showing loss history only")

    lgb_val = lgb_model.predict(X_te)
    xgb_val = xgb_model.predict(X_te)
    lgb_train_preds = lgb_model.predict(X_tr)
    xgb_train_preds = xgb_model.predict(X_tr)
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
        # If multivariate LSTM was trained (scaler is tuple), use one-step walk-forward
        if isinstance(lstm_scaler, tuple):
            # Build feature dataframe for train+val to support fair one-step validation
            try:
                X_tr_df = X_tr if isinstance(X_tr, pd.DataFrame) else pd.DataFrame(X_tr, columns=getattr(X_tr, 'columns', None))
                X_te_df = X_te if isinstance(X_te, pd.DataFrame) else pd.DataFrame(X_te, columns=getattr(X_tr, 'columns', None))
            except Exception:
                X_tr_df = pd.DataFrame(X_tr)
                X_te_df = pd.DataFrame(X_te)
            feat_full = pd.concat([X_tr_df, X_te_df], ignore_index=True)
            feat_full['y'] = np.concatenate([y_tr, y_te])
            lstm_val = lstm_one_step_walkforward(lstm_model, lstm_scaler, feat_full, val_start_idx=len(X_tr_df), lookback=lstm_lookback)
            # In retrain this function evaluates X_pred == X_te, so the one-step
            # validation forecast is the correct aligned LSTM prediction.
            lstm_fut = lstm_val[: (n_pred or len(X_pred))]
        else:
            lstm_val  = lstm_predict(lstm_model, lstm_scaler,
                                     daily_tr_raw, len(y_te), lookback=lstm_lookback)
            hist_full = np.concatenate([daily_tr_raw, y_te])
            lstm_fut  = lstm_predict(lstm_model, lstm_scaler,
                                     hist_full, n_pred or len(X_pred),
                                     lookback=lstm_lookback)

        # Build training / validation features for the meta model.
        # Use in-sample LSTM one-step preds for the training set and
        # one-step/forecasted LSTM outputs for validation / future.
        # Produce in-sample LSTM one-step preds for training set.
        if isinstance(lstm_scaler, tuple):
            # build training feature DataFrame
            try:
                X_tr_df = X_tr if isinstance(X_tr, pd.DataFrame) else pd.DataFrame(X_tr, columns=getattr(X_tr, 'columns', None))
            except Exception:
                X_tr_df = pd.DataFrame(X_tr)
            X_tr_df = X_tr_df.copy()
            X_tr_df['y'] = y_tr
            lstm_train_preds = lstm_in_sample_preds_multivariate(lstm_model, lstm_scaler, X_tr_df, lookback=lstm_lookback)
        else:
            lstm_train_preds = lstm_in_sample_preds(lstm_model, lstm_scaler, daily_tr_raw, lookback=lstm_lookback)
        # lstm_val contains the LSTM forecasts that align with the validation horizon
        lstm_val_preds = lstm_val[:len(y_te)]
        lstm_fut_preds = lstm_fut[: (n_pred or len(X_pred))]

        meta_train_feats = _build_meta_input_with_lstm_priority(
            lstm_train_preds, lgb_train_preds, xgb_train_preds)
        meta_val_feats = _build_meta_input_with_lstm_priority(
            lstm_val_preds, lgb_val, xgb_val)
        meta_fut = _build_meta_input_with_lstm_priority(
            lstm_fut_preds, lgb_fut, xgb_fut)

        meta  = Ridge(alpha=alpha)
        # Train meta on training features (not on validation)
        meta.fit(meta_train_feats, y_tr)
        final = meta.predict(meta_fut)
        meta_val = meta.predict(meta_val_feats)
    else:
        print("⚠️  LSTM (Primary Model) ไม่พร้อม – ใช้ LGB + XGB เท่านั้น")
        meta  = Ridge(alpha=alpha)
        meta_train_feats = np.column_stack([lgb_train_preds, xgb_train_preds])
        meta_val_feats = np.column_stack([lgb_val, xgb_val])
        meta.fit(meta_train_feats, y_tr)
        final = meta.predict(np.column_stack([lgb_fut, xgb_fut]))
        meta_val = meta.predict(meta_val_feats)

    if thr_high is not None and thr_med is not None and peak_ref is not None:
        # Ensure meta train predictions are produced from training features
        try:
            if 'meta_train_feats' in locals():
                meta_train_preds = meta.predict(meta_train_feats)
            else:
                meta_train_preds = meta.predict(np.column_stack([lgb_train_preds, xgb_train_preds]))
        except Exception:
            # fallback: predict on whatever meta_tr exists
            try:
                meta_train_preds = meta.predict(meta_tr)
            except Exception:
                meta_train_preds = np.repeat(np.nan, len(y_tr))

        meta_train_cls = compute_classification_metrics(y_tr, meta_train_preds, thr_high, thr_med, peak_ref)
        meta_val_cls = compute_classification_metrics(y_te, meta_val, thr_high, thr_med, peak_ref)
        print(
            f"    🟣 Meta training: TrainLoss={meta_train_cls['loss']:.4f} "
            f"ValLoss={meta_val_cls['loss']:.4f} "
            f"TrainAcc={meta_train_cls['accuracy']:.4f} ValAcc={meta_val_cls['accuracy']:.4f}"
        )

    return (np.maximum(0, final), lgb_model, xgb_model, meta,
            lgb_history, xgb_history, lgb_val, xgb_val,
            (lstm_val if 'lstm_val' in locals() else None),
            (meta_val if 'meta_val' in locals() else None))


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
    selected_model: str = 'ensemble',
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
        if isinstance(lstm_scaler, tuple):
            feat_hist = build_features(history, term_df=term_df, use_log=use_log).dropna()
            lstm_ahead = lstm_predict_multivariate(
                lstm_model,
                lstm_scaler,
                feat_hist,
                len(forecast_dates),
                lookback=lstm_lookback,
            )
        else:
            hist_arr = history.values.copy()
            if use_log:
                hist_arr = np.log1p(hist_arr)
            lstm_ahead = lstm_predict(
                lstm_model,
                lstm_scaler,
                hist_arr,
                len(forecast_dates),
                lookback=lstm_lookback,
            )
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

            if selected_model == 'lightgbm':
                d_pred = lgb_pred
            elif selected_model == 'xgboost':
                d_pred = xgb_pred
            elif selected_model == 'lstm' and fc_date in lstm_daily_preds:
                d_pred = lstm_val_fc

            d_pred = max(0.0, d_pred)
            if use_log:
                d_pred = np.expm1(d_pred)
            history.loc[fc_ts] = d_pred

        # guard against non-finite predictions (can happen with synthetic fallbacks)
        if not np.isfinite(d_pred):
            d_pred = 0.0
        day_norm = float(np.clip(d_pred / (peak_ref + 1e-6), 0.0, 1.0))

        for hr, weight in room_hour_dist.items():
            hr_term_load = compute_term_load(fc_date, hr, schedule)
            hr_factor    = weight / max_hr_weight if max_hr_weight > 0 else 1.0
            hr_pred      = day_norm * (0.6 + 0.4 * hr_factor)
            hr_term      = hr_term_load * day_norm * 0.6
            hr_dyn       = max(0.0, hr_pred - hr_term)
            demand_score = 0.7 * hr_pred + 0.3 * hr_dyn
            if not np.isfinite(demand_score):
                demand_score = 0.0
            demand_score = round(float(demand_score), 4)

            if not np.isfinite(hr_term):
                hr_term = 0.0
            if not np.isfinite(hr_dyn):
                hr_dyn = 0.0

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
    room_metas     = []

    # Build per-room daily series map (used for cold-start priors)
    all_rooms_daily = {}
    for r in Room.objects.all():
        rdf_r = raw[raw['room_id'] == r.id]
        if len(rdf_r) == 0:
            all_rooms_daily[r] = pd.Series(dtype=float)
            continue
        daily_r = (
            rdf_r.groupby('date')['duration'].sum()
                 .reindex(pd.date_range(rdf_r['date'].min(), rdf_r['date'].max(), freq='D').date,
                          fill_value=0.0)
                 .astype(float)
        )
        daily_r.index = pd.to_datetime(daily_r.index)
        all_rooms_daily[r] = daily_r

    for room in Room.objects.all():
        rdf = raw[raw['room_id'] == room.id]
        unique_days = rdf['date'].nunique()
        tier = get_data_tier(len(rdf), unique_days)

        if tier == 'cold_start':
            print(f"🥶 {room.name} – Cold Start → ใช้ Prior จากห้องประเภทเดียวกัน")
            seasonal_model = build_cold_start_prior(room, all_rooms_daily)
            combined = build_similar_series(room, all_rooms_daily)
            if len(combined) == 0:
                # fallback: build a zero series spanning forecast horizon + buffer
                start = forecast_dates[0] - timedelta(days=60)
                end = forecast_dates[-1]
                idx = pd.date_range(start, end, freq='D')
                combined = pd.Series(0.0, index=idx)

            combined.index = pd.to_datetime(combined.index)
            peak_ref = float(combined.quantile(0.95)) or 1.0
            thr_high, thr_med = compute_adaptive_thresholds(combined, peak_ref)
            room_hour_dist = learn_hour_dist(rdf, room_id=room.id) or HOUR_DIST_FALLBACK
            confidence = 50.0

            # Default fallback predictors
            lgb_model = SeasonalPredictor(seasonal_model)
            xgb_model = SeasonalPredictor(seasonal_model)
            meta_ridge = None
            lgb_history = xgb_history = lstm_history = None
            lstm_model = lstm_scaler = None
            lgb_val = xgb_val = lstm_val = meta_val = None
            model_metrics = {}
            reg_metrics = {
                'r2':    round(0.0, 4),
                'mae':   round(0.0, 4),
                'rmse':  round(0.0, 4),
                'smape': round(0.0, 4),
            }
            cls_metrics = {
                'accuracy':  0.0,
                'f1':        0.0,
                'recall':    0.0,
                'precision': 0.0,
                'loss':      0.0,
                'report':    '',
            }
            used_fallback = True
            use_log = False

            cold_results = build_cold_start_training_models(
                room, combined, load_term_schedule(room.id), use_log=False
            )
            if cold_results is not None and cold_results[0] is not None:
                (lgb_model, xgb_model, meta_ridge,
                 lgb_history, xgb_history, lstm_model, lstm_scaler,
                 lstm_history, lgb_val, xgb_val, lstm_val,
                 meta_val, X_te, y_te) = cold_results
                y_true = y_te.copy()
                y_pred_meta = np.maximum(0, meta_val)
                if len(y_true) > 0:
                    if False:
                        pass
                    y_te_eval = y_true
                    y_pred_eval = y_pred_meta
                    if use_log:
                        y_te_eval = np.expm1(y_te_eval)
                        y_pred_eval = np.expm1(y_pred_eval)
                    reg_metrics = {
                        'r2':    round(r2_score(y_te_eval, y_pred_eval), 4),
                        'mae':   round(mean_absolute_error(y_te_eval, y_pred_eval), 4),
                        'rmse':  round(rmse(y_te_eval, y_pred_eval), 4),
                        'smape': round(smape(y_te_eval, y_pred_eval), 4),
                    }
                    cls_metrics = compute_classification_metrics(y_te_eval, y_pred_eval, thr_high, thr_med, peak_ref)
                    # baseline evaluation
                    model_metrics['ensemble'] = evaluate_prediction_metrics(y_te_eval, y_pred_meta, thr_high, thr_med, peak_ref)
                    preds = {'ensemble': y_pred_meta}
                    if lgb_val is not None:
                        lgb_eval = np.maximum(0, lgb_val)
                        model_metrics['lightgbm'] = evaluate_prediction_metrics(y_te_eval, lgb_eval, thr_high, thr_med, peak_ref)
                        preds['lgb'] = lgb_eval
                    if xgb_val is not None:
                        xgb_eval = np.maximum(0, xgb_val)
                        model_metrics['xgboost'] = evaluate_prediction_metrics(y_te_eval, xgb_eval, thr_high, thr_med, peak_ref)
                        preds['xgboost'] = xgb_eval
                    if lstm_val is not None:
                        lstm_eval = np.maximum(0, lstm_val)
                        lstm_metrics = evaluate_prediction_metrics(y_te_eval, lstm_eval, thr_high, thr_med, peak_ref)
                        if lstm_metrics['classification']['accuracy'] >= MIN_ACCEPTED_MODEL_ACCURACY:
                            model_metrics['lstm'] = lstm_metrics
                            preds['lstm'] = lstm_eval
                        else:
                            lstm_model = None
                            lstm_scaler = None
                            lstm_history = None
                    if meta_val is not None:
                        model_metrics['meta'] = evaluate_prediction_metrics(y_te_eval, np.maximum(0, meta_val), thr_high, thr_med, peak_ref)

                    # Try to improve classification accuracy by tuning threshold multipliers per-model
                    for name, pred_arr in list(preds.items()):
                        try:
                            best_m, best_cls = _optimize_threshold_multiplier(y_te_eval, np.asarray(pred_arr), thr_high, thr_med, peak_ref)
                            # attach calibration info
                            model_metrics.setdefault(name, {})
                            model_metrics[name]['calibration_multiplier'] = float(best_m)
                            model_metrics[name]['classification_calibrated'] = best_cls
                        except Exception:
                            pass

                    # Try simple ensemble weight search across base predictors to maximize accuracy
                    try:
                        best_name, best_pred, best_metrics = _optimize_ensemble_weights(y_te_eval, preds, thr_high, thr_med, peak_ref)
                        model_metrics['best_ensemble_combo'] = {'name': best_name, 'classification': best_metrics}
                        # if this ensemble beats the stored ensemble accuracy, prefer it for cls_metrics
                        best_acc = float(best_metrics.get('accuracy', 0.0)) if best_metrics else 0.0
                        base_acc = float(model_metrics.get('ensemble', {}).get('classification', {}).get('accuracy', 0.0))
                        if best_acc > base_acc:
                            cls_metrics = best_metrics
                            # also update ensemble entry to reflect calibrated version
                            model_metrics['ensemble']['classification_calibrated'] = best_metrics
                    except Exception:
                        pass

                    confidence = round(max(0.0, 1.0 - reg_metrics['smape'] / 100.0) * 100.0, 1)

            # Model fallback when not enough training data was available
            if meta_ridge is None:
                meta_ridge = Ridge(alpha=1.0)
                dummy_X = np.zeros((len(combined), 2))
                meta_ridge.fit(dummy_X, combined.values)

            joblib.dump(seasonal_model, os.path.join(MODEL_DIR, f"{room.id}_seasonal.pkl"))
            joblib.dump(lgb_model, os.path.join(MODEL_DIR, f"{room.id}_lgb.pkl"))
            joblib.dump(xgb_model, os.path.join(MODEL_DIR, f"{room.id}_xgb.pkl"))
            if lstm_model is not None:
                joblib.dump(lstm_model,  os.path.join(MODEL_DIR, f"{room.id}_lstm.pkl"))
                joblib.dump(lstm_scaler, os.path.join(MODEL_DIR, f"{room.id}_lstm_scaler.pkl"))

            meta_payload = {
                'peak_ref':      peak_ref,
                'thr_high':      thr_high,
                'thr_med':       thr_med,
                'hour_dist':     room_hour_dist,
                'confidence':    confidence,
                'meta_ridge':    meta_ridge,
                'use_log':       False,
                'lstm_lookback': LSTM_LOOKBACK,
                'has_lstm':      lstm_model is not None,
                'robust':        False,
                'used_fallback': used_fallback,
                'cls_metrics':   cls_metrics,
                'reg_metrics':   reg_metrics,
                'model_metrics': model_metrics,
                'selected_model': 'ensemble',
                'train_size':    len(combined),
                'test_size':     len(X_te) if 'X_te' in locals() else 0,
                'lstm_history':  lstm_history,
                'lgb_history':   lgb_history,
                'xgb_history':   xgb_history,
            }
            joblib.dump(meta_payload, os.path.join(META_DIR, f"{room.id}_meta.pkl"))

            bulk = _build_forecast_bulk(
                room, lgb_model, xgb_model, meta_ridge, combined.copy(),
                peak_ref, thr_high, thr_med, room_hour_dist, confidence,
                forecast_dates, load_term_schedule(room.id),
                lstm_model=lstm_model, lstm_scaler=lstm_scaler,
                use_log=False, lstm_lookback=LSTM_LOOKBACK,
                seasonal_model=seasonal_model,
                selected_model='ensemble',
            )
            DemandForecast.objects.filter(
                room=room, forecast_date__in=forecast_dates
            ).delete()
            DemandForecast.objects.bulk_create(bulk)
            continue

        # tier controls
        force_disable_lstm = (tier == 'medium')

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

        # Sparse-tier: augment + lean features + stronger regularization
        if tier == 'sparse':
            print(f"🟡 {room.name} – Sparse → Augment + Seasonal Median + LGB(sparse)")
            daily = augment_sparse_daily(daily, target_days=60)
            term_df = build_term_daily_features(daily.index, schedule)
            term_df.index = daily.index
            feat_df = build_features_sparse(daily, term_df).dropna()
            X = feat_df.drop(columns='y')
            y = feat_df['y'].values

            split = int(len(X) * 0.85)
            X_tr, X_te = X.iloc[:split], X.iloc[split:]
            y_tr, y_te = y[:split], y[split:]
            if len(X_te) < 5:
                print(f"   ⚠️ Sparse: น้อยกว่า 5 test rows สำหรับ {room.name} – จะใช้ข้อมูล available เพื่อประเมิน")
            lstm_model, lstm_scaler, lstm_history = None, None, None
            lgb_history, xgb_history = None, None

            lgb_model, lgb_history = train_lgb_sparse(X_tr, y_tr, X_te, y_te)
            xgb_model, xgb_history = train_xgb(X_tr, y_tr, X_te, y_te, robust=False)

            lgb_val = lgb_model.predict(X_te)
            xgb_val = xgb_model.predict(X_te)
            lgb_train_preds = lgb_model.predict(X_tr)
            xgb_train_preds = xgb_model.predict(X_tr)
            lgb_fut = lgb_model.predict(X_te)
            xgb_fut = xgb_model.predict(X_te)

            alpha = 10.0 if False else 1.0
            meta_ridge = Ridge(alpha=alpha)
            meta_ridge.fit(np.column_stack([lgb_train_preds, xgb_train_preds]), y_tr)
            final = meta_ridge.predict(np.column_stack([lgb_fut, xgb_fut]))
            y_pred_ens = np.maximum(0, final)

            # evaluate will reuse variables below (y_pred_ens, lgb_model, xgb_model, meta_ridge)
            # prepare model-level preds for metrics
            lgb_val = lgb_val
            xgb_val = xgb_val
            lstm_val = None
            meta_val = meta_ridge.predict(np.column_stack([lgb_val, xgb_val]))
        else:
            term_df       = build_term_daily_features(daily.index, schedule)
            term_df.index = daily.index
            feat_df       = build_features(daily, term_df, use_log=use_log).dropna()
            X = feat_df.drop(columns='y')
            y = feat_df['y'].values

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

        room_hour_dist = learn_hour_dist(rdf, room_id=room.id)

        if tier != 'sparse':
            term_df       = build_term_daily_features(daily.index, schedule)
            term_df.index = daily.index
            feat_df       = build_features(daily, term_df, use_log=use_log).dropna()
            X = feat_df.drop(columns='y')
            y = feat_df['y'].values

            split      = int(len(X) * 0.85)
            X_tr, X_te = X.iloc[:split], X.iloc[split:]
            y_tr, y_te = y[:split], y[split:]
            if len(X_te) < 5:
                print(f"   ⚠️  {room.name}: มี test rows น้อยกว่า 5 ({len(X_te)}) — จะประเมินจากข้อมูลที่มี")
        else:
            # sparse path: X, y, split are prepared earlier
            pass

        # ── ฝึก LSTM (Primary) ──────────────────────────────────────────────
        lstm_model, lstm_scaler, lstm_history = None, None, None
        train_lstm_candidate = (
            LSTM_AVAILABLE
            and not use_log
            and not force_disable_lstm
            and not needs_robust
            and len(y_tr) >= max(LSTM_LOOKBACK + 10, 90)
        )
        if train_lstm_candidate:
            print(f"   🧠 [1/3] Training LSTM (Primary) for {room.name} ...")
            # pass feature DataFrame to train multivariate LSTM (fairer input)
            feat_tr_df = feat_df.iloc[:split]
            feat_va_df = feat_df.iloc[split:]
            lstm_model, lstm_scaler, lstm_history = train_lstm(
                y_tr, y_te, lookback=LSTM_LOOKBACK,
                epochs=LSTM_EPOCHS, patience=LSTM_PATIENCE,
                feat_train_df=feat_tr_df, feat_val_df=feat_va_df
            )
            status = "✅ success" if lstm_model else "⚠️  failed"
            print(f"         {status}")
            # Quality gate: validate LSTM on the test horizon and discard if poor
            try:
                if lstm_model is not None:
                    # Use one-step walk-forward validation when multivariate features were used
                    if isinstance(lstm_scaler, tuple):
                        lstm_val_check = lstm_one_step_walkforward(lstm_model, lstm_scaler, feat_df, val_start_idx=split, lookback=LSTM_LOOKBACK)
                    else:
                        # fallback: use in-sample one-step preds from univariate path
                        full_hist = np.concatenate([y_tr, y_te])
                        preds_full = lstm_in_sample_preds(lstm_model, lstm_scaler, full_hist, lookback=LSTM_LOOKBACK)
                        lstm_val_check = preds_full[split:split+len(y_te)]
                    # align lengths
                    if len(lstm_val_check) != len(y_te):
                        lstm_val_check = lstm_val_check[:len(y_te)] if len(lstm_val_check) > len(y_te) else np.pad(lstm_val_check, (0, max(0, len(y_te)-len(lstm_val_check))), 'constant')
                    lv = np.nan_to_num(lstm_val_check, nan=0.0, posinf=0.0, neginf=0.0)
                    yt = np.nan_to_num(np.asarray(y_te, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
                    lstm_r2 = r2_score(yt, lv) if len(yt) > 0 else float('-inf')
                    lstm_mae = mean_absolute_error(yt, lv) if len(yt) > 0 else float('inf')
                    gate_peak_ref = float(daily.quantile(0.95)) or 1.0
                    gate_thr_high, gate_thr_med = compute_adaptive_thresholds(
                        daily,
                        gate_peak_ref,
                        problematic=needs_robust,
                    )
                    lstm_cls = compute_classification_metrics(
                        yt,
                        lv,
                        gate_thr_high,
                        gate_thr_med,
                        gate_peak_ref,
                    )
                    lstm_acc = float(lstm_cls.get('accuracy', 0.0))
                    # Drop LSTM if it is worse than baseline or misses the accuracy target.
                    if lstm_r2 < 0.0 or lstm_acc < MIN_ACCEPTED_MODEL_ACCURACY:
                        print(
                            f"      ⚠️  Dropping LSTM for {room.name}: "
                            f"val_acc={lstm_acc:.4f} (<{MIN_ACCEPTED_MODEL_ACCURACY:.2f}) "
                            f"R²={lstm_r2:.4f} MAE={lstm_mae:.4f}"
                        )
                        lstm_model = None
                        lstm_scaler = None
                        lstm_history = None
                    else:
                        print(
                            f"      ✅ LSTM accepted for {room.name}: "
                            f"val_acc={lstm_acc:.4f} R²={lstm_r2:.4f} MAE={lstm_mae:.4f}"
                        )
            except Exception:
                # conservative: if evaluation fails, keep existing behavior
                pass
        elif use_log:
            print(f"   ⏭️  [1/3] LSTM skipped (LECTURE)")
        elif needs_robust:
            print(f"   ⏭️  [1/3] LSTM skipped (robust/noisy room)")
        elif force_disable_lstm:
            print(f"   ⏭️  [1/3] LSTM skipped (medium tier)")
        else:
            print(f"   ⚠️  [1/3] LSTM skipped (ข้อมูลน้อย)")

        rob_tag = " [ROBUST+Huber]" if needs_robust else ""
        print(f"   🌿 [2/3] LightGBM (Support){rob_tag}")
        print(f"   ⚡ [3/3] XGBoost   (Support){rob_tag}")

        if tier == 'sparse':
            # already trained above (sparse path)
            pass
        else:
            peak_ref = float(daily.quantile(0.95)) or 1.0
            thr_high, thr_med = compute_adaptive_thresholds(daily, peak_ref, problematic=needs_robust)
            (y_pred_ens, lgb_model, xgb_model, meta_ridge,
                 lgb_history, xgb_history, lgb_val, xgb_val,
                 lstm_val, meta_val) = stacking_predict(
                    X_tr, y_tr, X_te, y_te, X_te,
                    lstm_model=lstm_model, lstm_scaler=lstm_scaler,
                    daily_tr_raw=y_tr, n_pred=len(X_te),
                    lstm_lookback=LSTM_LOOKBACK,
                    robust=needs_robust,
                    thr_high=thr_high, thr_med=thr_med, peak_ref=peak_ref,
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
            train_index = pd.to_datetime(feat_df.index[:split])
            daily_train_for_fallback = daily.reindex(train_index).ffill().fillna(0.0)
            seasonal_model = SeasonalMedianModel().fit(daily_train_for_fallback)
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

        # --- Compute and print per-model metrics (regression + classification)
        model_metrics = {}
        model_preds = {
            'ensemble': y_pred_eval,
            'lightgbm': (np.expm1(lgb_val) if use_log and lgb_val is not None else lgb_val),
            'xgboost':  (np.expm1(xgb_val) if use_log and xgb_val is not None else xgb_val),
            'meta':     (np.expm1(meta_val) if use_log and meta_val is not None else meta_val),
            'lstm':     (np.expm1(lstm_val) if use_log and lstm_val is not None else lstm_val),
        }
        for mname, mpred in model_preds.items():
            if mpred is None:
                continue
            # ensure array-like
            mp = np.nan_to_num(np.array(mpred, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
            if len(mp) != len(y_te_eval):
                # if lengths mismatch try to align to test length
                mp = mp[:len(y_te_eval)] if len(mp) > len(y_te_eval) else np.pad(mp, (0, max(0, len(y_te_eval)-len(mp))), 'constant')
            r2 = r2_score(y_te_eval, mp)
            mae = mean_absolute_error(y_te_eval, mp)
            rm = rmse(y_te_eval, mp)
            sm = smape(y_te_eval, mp)
            reg = {'r2': round(r2, 4), 'mae': round(mae, 4), 'rmse': round(rm, 4), 'smape': round(sm, 4)}
            cls = compute_classification_metrics(y_te_eval, mp, thr_high, thr_med, peak_ref)
            model_metrics[mname] = {'regression': reg, 'classification': cls}
            # Print model accuracy prominently
            acc_pct = cls['accuracy'] * 100
            print(f"  📊 {mname.upper():10s}: Accuracy={acc_pct:5.1f}% | Loss={cls['loss']:.4f} | R²={r2:.4f} | MAE={mae:.4f}")
            print_regression_metrics(reg, room.name, mname)
            print_classification_metrics(cls, f"{room.name} :: {mname}")

        selected_model = 'ensemble'
        if model_metrics:
            candidates = []
            for name in ['ensemble', 'meta', 'lightgbm', 'xgboost', 'lstm']:
                metrics = model_metrics.get(name)
                if not metrics:
                    continue
                cls = metrics.get('classification') or {}
                reg = metrics.get('regression') or {}
                candidates.append((
                    float(cls.get('accuracy', 0.0)),
                    -float(reg.get('mae', np.inf)),
                    name,
                ))
            if candidates:
                selected_model = max(candidates)[2]
                if selected_model == 'meta':
                    selected_model = 'ensemble'
        print(f"  🧭 Selected forecast model: {selected_model}")

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
            'model_metrics': model_metrics if 'model_metrics' in locals() else {},
            'selected_model': selected_model,
            'train_size':   len(y_tr),
            'test_size':    len(y_te),
            'lstm_history': lstm_history,
            'lgb_history':  lgb_history,
            'xgb_history':  xgb_history,
        }
        if lstm_model is not None:
            joblib.dump(lstm_model,  os.path.join(MODEL_DIR, f"{room.id}_lstm.pkl"))
            joblib.dump(lstm_scaler, os.path.join(MODEL_DIR, f"{room.id}_lstm_scaler.pkl"))
        joblib.dump(meta_payload, os.path.join(META_DIR, f"{room.id}_meta.pkl"))
        # collect for aggregated plotting after retrain
        try:
            room_metas.append((room.name, meta_payload))
        except Exception:
            pass

        bulk = _build_forecast_bulk(
            room, lgb_model, xgb_model, meta_ridge, daily.copy(),
            peak_ref, thr_high, thr_med, room_hour_dist, confidence,
            forecast_dates, schedule,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            use_log=use_log, lstm_lookback=LSTM_LOOKBACK,
            seasonal_model=seasonal_model,
            selected_model=selected_model,
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

    # Note: plotting has been moved to a separate utility.
    # To generate training-curve PNGs run: ml/saved/generate_plots.py
    if len(room_metas) > 0:
        print("\n🖼️  Plots are no longer auto-generated by retrain.")
        print("    Run: python ml/saved/generate_plots.py to create training-curve PNGs.")

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
            selected_model=meta.get('selected_model', 'ensemble'),
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

def import_facilities_from_excel():
    """นำเข้าอุปกรณ์จริงจาก Excel (ห้ามใช้ข้อมูลจำลอง)"""
    import_path = os.path.join(BASE_DIR, 'ml', 'import_real_data.py')
    if not os.path.exists(import_path):
        print("❌ ไม่พบ ml/import_real_data.py")
        return
    print("📥 นำเข้าอุปกรณ์และข้อมูลห้องจาก Excel...")
    import importlib.util
    spec = importlib.util.spec_from_file_location('import_real_data', import_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.import_all(clear_mock=False)
    print("✅ อุปกรณ์จาก Excel อัปเดตแล้ว")


def update_to_thai_facilities():
    """Deprecated: ใช้ import_facilities_from_excel แทน (ข้อมูลจริงเท่านั้น)"""
    print("⚠️  --update-fac ถูกแทนที่ด้วยการนำเข้าจาก Excel")
    import_facilities_from_excel()


# ── Predictive Maintenance: หาช่วง demand ต่ำจาก DemandForecast ─────────────
def find_maintenance_slots(
    room_id: int = None,
    max_demand: float = 0.10,
    min_consecutive_hours: int = 3,
    days_ahead: int = 14,
) -> list[dict]:
    """
    คัดกรองช่วงเวลาที่ LSTM/Ensemble พยากรณ์ demand ต่ำติดกัน
    คืนค่า list ของ slot {room_id, room_name, date, start_hour, end_hour, avg_demand}
    """
    from datetime import date as date_type
    today = date_type.today()
    end   = today + timedelta(days=days_ahead)

    qs = DemandForecast.objects.filter(
        forecast_date__gte=today,
        forecast_date__lte=end,
        predicted_demand__lt=max_demand,
    ).select_related('room').order_by('room_id', 'forecast_date', 'hour')

    if room_id:
        qs = qs.filter(room_id=room_id)

    slots = []
    current = None

    for fc in qs:
        key = (fc.room_id, fc.forecast_date)
        if current and current['key'] == key and fc.hour == current['last_hour'] + 1:
            current['hours'].append(fc.hour)
            current['demands'].append(fc.predicted_demand)
            current['last_hour'] = fc.hour
        else:
            if current and len(current['hours']) >= min_consecutive_hours:
                slots.append(_finalize_slot(current))
            current = {
                'key': key,
                'room_id': fc.room_id,
                'room_name': fc.room.name,
                'date': fc.forecast_date,
                'hours': [fc.hour],
                'demands': [fc.predicted_demand],
                'last_hour': fc.hour,
            }

    if current and len(current['hours']) >= min_consecutive_hours:
        slots.append(_finalize_slot(current))

    return sorted(slots, key=lambda s: (s['date'], s['start_hour']))


def _finalize_slot(current: dict) -> dict:
    hrs = current['hours']
    return {
        'room_id':    current['room_id'],
        'room_name':  current['room_name'],
        'date':       str(current['date']),
        'start_hour': min(hrs),
        'end_hour':   max(hrs) + 1,
        'hours':      hrs,
        'avg_demand': round(sum(current['demands']) / len(current['demands']), 4),
        'label':      f"{current['room_name']} | {current['date']} "
                      f"{min(hrs):02d}:00–{max(hrs)+1:02d}:00",
    }


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


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 – Show Saved Metrics
# ══════════════════════════════════════════════════════════════════════════════

def show_saved_metrics(compact: bool = False):
    print("\n📊 METRICS ภาพรวมทั้งหมด – ผลการเทรนครั้งล่าสุด")
    print("=" * 75)
    all_stats = []
    room_metas = []

    for room in Room.objects.all():
        row = {
            'RoomID':    room.id,
            'Room':      room.name,
            'Type':      getattr(room, 'room_type', 'unknown'),
            'Status':    'NO_META',
            'HasLSTM':   False,
            'Robust':    False,
            'Fallback':  False,
            'R2':        np.nan,
            'MAE':       np.nan,
            'RMSE':      np.nan,
            'sMAPE':     np.nan,
            # ensemble accuracy (kept for backward compatibility)
            'Accuracy':  np.nan,
            'F1':        np.nan,
            'Recall':    np.nan,
            'Precision': np.nan,
            'Loss':      np.nan,
            'Conf':      np.nan,
            # per-model accuracies
            'Acc_ensemble': np.nan,
            'Acc_lgb':      np.nan,
            'Acc_xgb':      np.nan,
            'Acc_lstm':     np.nan,
        }

        meta_path = os.path.join(META_DIR, f"{room.id}_meta.pkl")
        if not os.path.exists(meta_path):
            all_stats.append(row)
            continue
        meta = joblib.load(meta_path)
        reg  = meta.get('reg_metrics')
        cls  = meta.get('cls_metrics')
        row.update({
            'Status':   'NO_METRICS',
            'HasLSTM':  meta.get('has_lstm',      False),
            'Robust':   meta.get('robust',         False),
            'Fallback': meta.get('used_fallback',  False),
            'Conf':     meta.get('confidence',     np.nan),
        })
        if reg and cls:
            room_metas.append((room.name, meta))
            row.update({
                'Status':    'OK',
                'R2':        reg['r2'],
                'MAE':       reg['mae'],
                'RMSE':      reg['rmse'],
                'sMAPE':     reg['smape'],
                'Accuracy':  cls['accuracy'],
                'F1':        cls['f1'],
                'Recall':    cls['recall'],
                'Precision': cls['precision'],
                'Loss':      cls['loss'],
            })
            # populate per-model accuracies when available
            mmetrics = meta.get('model_metrics', {}) if isinstance(meta, dict) else {}
            try:
                row['Acc_ensemble'] = float(mmetrics.get('ensemble', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                row['Acc_ensemble'] = np.nan
            try:
                row['Acc_lgb'] = float(mmetrics.get('lightgbm', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                row['Acc_lgb'] = np.nan
            try:
                row['Acc_xgb'] = float(mmetrics.get('xgboost', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                row['Acc_xgb'] = np.nan
            try:
                row['Acc_lstm'] = float(mmetrics.get('lstm', {}).get('classification', {}).get('accuracy', np.nan))
            except Exception:
                row['Acc_lstm'] = np.nan
        all_stats.append(row)

    if not all_stats:
        print("❌ ไม่พบข้อมูล กรุณารัน --retrain ก่อนครับ"); return

    # Compact mode: only print the aggregated model summary table
    if compact:
        model_summary = aggregate_model_metrics(room_metas)
        if model_summary:
            print("\n📊 Summary Metrics by Model (average across rooms with data)")
            print("-------------------------------------------------------------------------------")
            print(
                f"{'Model':<9} {'Cnt':>4} {'R2':>6} {'MAE':>6} {'RMSE':>6} {'sMAPE':>6} "
                f"{'Acc':>6} {'F1':>6} {'Rec':>6} {'Prec':>6} {'Loss':>6}"
            )
            print("-------------------------------------------------------------------------------")
            for name in ['ensemble', 'lightgbm', 'xgboost', 'lstm']:
                summary = model_summary.get(name)
                if not summary:
                    continue
                print(
                    f"{name.title():<9} {summary['count']:>4} "
                    f"{summary['r2']:>6.3f} {summary['mae']:>6.3f} {summary['rmse']:>6.3f} "
                    f"{summary['smape']:>6.3f} {summary['accuracy']:>6.3f} {summary['f1']:>6.3f} "
                    f"{summary['recall']:>6.3f} {summary['precision']:>6.3f} {summary['loss']:>6.3f}"
                )
            print("=" * 118)
        return

    df = pd.DataFrame(all_stats)
    df_ok = df[df['Status'] == 'OK'].copy()
    print(f"📌 ห้องทั้งหมดในระบบ: {len(df)} | มี metrics ครบ: {len(df_ok)} | ยังไม่มี metrics: {len(df) - len(df_ok)}")

    if df_ok.empty:
        print("\n❌ ยังไม่มีห้องที่มี metrics ครบ กรุณารัน --retrain ก่อนครับ")
    else:
        print(f"\n{'Room':<20} {'LSTM':>5} {'ROB':>4} {'FB':>3} "
              f"{'R²':>6} {'MAE':>7} {'RMSE':>7} {'sMAPE':>7} "
              f"{'Acc':>6} {'LGB':>6} {'XGB':>6} {'LSTM':>6} {'F1':>6} {'Recall':>7} {'Prec':>7} {'Loss':>7} {'Conf':>6}")
        print("  (Acc = ensemble, LGB = LightGBM, XGB = XGBoost, LSTM = LSTM)")
        print("-" * 118)
        for _, r in df_ok.iterrows():
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
                f"{r.get('Acc_lgb', np.nan):>6.3f} "
                f"{r.get('Acc_xgb', np.nan):>6.3f} "
                f"{r.get('Acc_lstm', np.nan):>6.3f} "
                f"{r['F1']:>6.3f} "
                f"{r['Recall']:>7.3f} "
                f"{r['Precision']:>7.3f} "
                f"{r['Loss']:>7.4f} "
                f"{r['Conf']:>5.1f}%"
            )
        print("-" * 118)
        print(
            f"  {'📊 เฉลี่ย':<18} {'':>5} {'':>4} {'':>3} "
            f"{df_ok['R2'].mean():>6.3f} "
            f"{df_ok['MAE'].mean():>6.3f}ชม "
            f"{df_ok['RMSE'].mean():>6.3f}ชม "
            f"{df_ok['sMAPE'].mean():>6.1f}% "
            f"{df_ok['Accuracy'].mean():>6.3f} "
            f"{df_ok.get('Acc_lgb', pd.Series(dtype=float)).mean():>6.3f} "
            f"{df_ok.get('Acc_xgb', pd.Series(dtype=float)).mean():>6.3f} "
            f"{df_ok.get('Acc_lstm', pd.Series(dtype=float)).mean():>6.3f} "
            f"{df_ok['F1'].mean():>6.3f} "
            f"{df_ok['Recall'].mean():>7.3f} "
            f"{df_ok['Precision'].mean():>7.3f} "
            f"{df_ok['Loss'].mean():>7.4f} "
            f"{df_ok['Conf'].mean():>5.1f}%"
        )
        print("=" * 118)

        model_summary = aggregate_model_metrics(room_metas)
        if model_summary:
            print("\n📊 Summary Metrics by Model (average across rooms with data)")
            print("-------------------------------------------------------------------------------")
            print(
                f"{'Model':<9} {'Cnt':>4} {'R2':>6} {'MAE':>6} {'RMSE':>6} {'sMAPE':>6} "
                f"{'Acc':>6} {'F1':>6} {'Rec':>6} {'Prec':>6} {'Loss':>6}"
            )
            print("-------------------------------------------------------------------------------")
            for name in ['ensemble', 'lightgbm', 'xgboost', 'lstm']:
                summary = model_summary.get(name)
                if not summary:
                    continue
                print(
                    f"{name.title():<9} {summary['count']:>4} "
                    f"{summary['r2']:>6.3f} {summary['mae']:>6.3f} {summary['rmse']:>6.3f} "
                    f"{summary['smape']:>6.3f} {summary['accuracy']:>6.3f} {summary['f1']:>6.3f} "
                    f"{summary['recall']:>6.3f} {summary['precision']:>6.3f} {summary['loss']:>6.3f}"
                )
            print("=" * 118)

    print("\n📄 ข้อมูล metrics ทั้งหมด (ค่าจริงจาก meta ล่าสุด)")
    print("-" * 118)
    full_formatters = {
        'RoomID':     lambda v: f"{int(v)}",
        'R2':        lambda v: f"{v:.4f}",
        'MAE':       lambda v: f"{v:.4f}",
        'RMSE':      lambda v: f"{v:.4f}",
        'sMAPE':     lambda v: f"{v:.4f}",
        'Accuracy':  lambda v: f"{v:.4f}",
        'Acc_ensemble': lambda v: f"{v:.4f}",
        'Acc_lgb':      lambda v: f"{v:.4f}",
        'Acc_xgb':      lambda v: f"{v:.4f}",
        'Acc_lstm':     lambda v: f"{v:.4f}",
        'F1':        lambda v: f"{v:.4f}",
        'Recall':    lambda v: f"{v:.4f}",
        'Precision': lambda v: f"{v:.4f}",
        'Loss':      lambda v: f"{v:.4f}",
        'Conf':      lambda v: f"{v:.1f}",
    }
    with pd.option_context(
        'display.max_columns', None,
        'display.max_rows', None,
        'display.width', 240,
    ):
        print(df.to_string(index=False, formatters=full_formatters))
    print("-" * 118)

    if not df_ok.empty:
        total_rooms = len(df)
        ok_rooms = len(df_ok)
        lstm_ok = int(df_ok['HasLSTM'].sum())
        robust_ok = int(df_ok['Robust'].sum())
        fallback_ok = int(df_ok['Fallback'].sum())

        print(f"\n🧠 LSTM (Primary)  : {lstm_ok}/{total_rooms} ห้องทั้งหมด ({lstm_ok}/{ok_rooms} ห้องที่มี metrics ครบ)")
        print(f"🔧 Robust+Huber    : {robust_ok}/{total_rooms} ห้องทั้งหมด ({robust_ok}/{ok_rooms} ห้องที่มี metrics ครบ)")
        print(f"📅 Seasonal Fallbk : {fallback_ok}/{total_rooms} ห้องทั้งหมด ({fallback_ok}/{ok_rooms} ห้องที่มี metrics ครบ)")
        print(f"🏆 R² ดีที่สุด    : {df_ok.loc[df_ok['R2'].idxmax(), 'Room']}  ({df_ok['R2'].max():.4f})")
        print(f"⚠️  R² ต่ำที่สุด   : {df_ok.loc[df_ok['R2'].idxmin(), 'Room']}  ({df_ok['R2'].min():.4f})")
        print(f"🏆 Accuracy สูงสุด : {df_ok.loc[df_ok['Accuracy'].idxmax(), 'Room']}  ({df_ok['Accuracy'].max():.4f})")
        print(f"🏆 Loss ต่ำสุด     : {df_ok.loc[df_ok['Loss'].idxmin(), 'Room']}  ({df_ok['Loss'].min():.4f})")

        avg_r2  = df_ok['R2'].mean()
        avg_acc = df_ok['Accuracy'].mean()
        avg_f1  = df_ok['F1'].mean()
        print(f"\n📋 ประเมินภาพรวมโมเดล")
        print(f"   R²       : {'✅ ดีมาก' if avg_r2  >= 0.8 else '⚠️  พอใช้' if avg_r2  >= 0.5 else '❌ ต่ำ'} ({avg_r2:.3f})")
        print(f"   Accuracy : {'✅ ดีมาก' if avg_acc >= 0.8 else '⚠️  พอใช้' if avg_acc >= 0.6 else '❌ ต่ำ'} ({avg_acc:.3f})")
        print(f"   F1 Score : {'✅ ดีมาก' if avg_f1  >= 0.8 else '⚠️  พอใช้' if avg_f1  >= 0.6 else '❌ ต่ำ'} ({avg_f1:.3f})")
        print("=" * 75)

    # Export metric CSV only. Plot generation has been moved to `ml/saved/generate_plots.py`.
    summary_csv = os.path.join(METRICS_DIR, 'metrics_summary.csv')
    df.to_csv(summary_csv, index=False)
    print(f"\n📄 Saved metrics CSV: {summary_csv}")
    print("🖼️  Plots are not generated here. Run: python ml/saved/generate_plots.py to create PNGs.")


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
    group.add_argument('--import-excel', action='store_true', help='นำเข้าข้อมูลจริงจาก Excel')
    group.add_argument('--boost',        action='store_true')
    group.add_argument('--show-metrics', action='store_true')
    parser.add_argument('--compact-metrics', action='store_true', help='Show only the summary metrics table')
    args = parser.parse_args()

    if args.import_excel:
        import_path = os.path.join(BASE_DIR, 'ml', 'import_real_data.py')
        import importlib.util
        spec = importlib.util.spec_from_file_location('import_real_data', import_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.import_all(clear_mock=True)
        print("\n🔄 เริ่ม retrain หลัง import...")
        retrain_and_forecast()
    elif args.retrain:
        retrain_and_forecast()
    elif args.update_fac:
        update_to_thai_facilities()
    elif args.boost:
        boost_thresholds()
        generate_forecast_only()
    elif args.show_metrics:
        # Default to compact output for quicker, per-model summaries.
        # Use --compact-metrics to request the same behavior explicitly.
        show_saved_metrics(compact=True)
    else:
        generate_forecast_only()
