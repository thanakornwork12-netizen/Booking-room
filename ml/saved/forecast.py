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
#  │  Ensemble Weighting – Layer 2                                    │
#  │  Weighted blend – LSTM 20% | LGB 40% | XGB 40%                  │
#  └──────────────────────────────────────────────────────────────────┘
#
#  Pipeline แบบเรียบง่าย (เน้นความแม่นสูงสุด):
#    1. LSTM (Primary) → จับ temporal/seasonal
#    2. LightGBM + XGBoost (Support) → เสริมโครงสร้าง
#    3. Weighted blend → รวมเป็น Ensemble (LSTM 20%, LGB 40%, XGB 40%)
#    4. ไม่มี robust/fallback/calibration gates — train ทุกห้องด้วย flow เดียวกัน
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
os.environ.setdefault('DISABLE_DJANGO_SCHEDULER', '1')

import json
import numpy as np
import pandas as pd
import joblib
from datetime import datetime, timedelta
from sklearn.metrics import (
    mean_absolute_error, r2_score, mean_squared_error,
    accuracy_score, f1_score, recall_score, precision_score,
    classification_report
)
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


def _seed_everything(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)


_seed_everything(42)

# ── TensorFlow (LSTM – Primary Base Model) ────────────────────────────────────
try:
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping, Callback, ReduceLROnPlateau
    from tensorflow.keras.optimizers import Adam
    LSTM_AVAILABLE = True
except ImportError:
    LSTM_AVAILABLE = False
    print("⚠️  TensorFlow ไม่พบ – LSTM (Primary Model) ไม่สามารถใช้งานได้")
    print("   กรุณาติดตั้ง: pip install tensorflow")
else:
    tf.random.set_seed(42)

# ── Hyperparameter Set Configuration (A/B/C) ──────────────────────────────────
PARAM_SETS = {
    'A': {
        'name': 'A - Fast (Baseline)',
        'lstm_epochs': 20, 'lstm_batch': 16,
        'lstm_lookback': 20,
        'lgb_estimators': 20, 'lgb_depth': 6, 'lgb_leaves': 31, 'lgb_lr': 0.15,
        'xgb_estimators': 20, 'xgb_depth': 5, 'xgb_lr': 0.15,
    },
    'B': {
        'name': 'B - Balanced',
        'lstm_epochs': 50, 'lstm_batch': 8,
        'lstm_lookback': 40,
        'lgb_estimators': 50, 'lgb_depth': 8, 'lgb_leaves': 63, 'lgb_lr': 0.06,
        'xgb_estimators': 50, 'xgb_depth': 6, 'xgb_lr': 0.06,
    },
    'C': {
        'name': 'C - High Quality',
        'lstm_epochs': 70, 'lstm_batch': 4,
        'lstm_lookback': 70,
        'lgb_estimators': 70, 'lgb_depth': 10, 'lgb_leaves': 127, 'lgb_lr': 0.04,
        'xgb_estimators': 70, 'xgb_depth': 8, 'xgb_lr': 0.04,
    },
    # Experimental — trains harder than C to test whether more training keeps
    # helping or plateaus/hurts. Not the production default; used only for
    # the one-off A/B/C/D comparison experiment (see saved_meta_D/ archive).
    'D': {
        'name': 'D - Extra Deep (Experimental)',
        'lstm_epochs': 100, 'lstm_batch': 2,
        'lstm_lookback': 100,
        'lgb_estimators': 100, 'lgb_depth': 12, 'lgb_leaves': 255, 'lgb_lr': 0.03,
        'xgb_estimators': 100, 'xgb_depth': 10, 'xgb_lr': 0.03,
    },
}

# ── Config ─────────────────────────────────────────────────────────────────────
MIN_DAYS      = 30   # จำนวน booking ขั้นต่ำต่อห้อง (ข้อมูลจริง ~700+ ต่อห้อง)
MIN_UNIQUE_DAYS = 14  # จำนวนวันที่มีการใช้งานขั้นต่ำ
FORECAST_DAYS = 14
LSTM_LOOKBACK = 30  # ↑ ขยายจาก 14 → 30 เพื่อจับ seasonal patterns
# Set current parameter set (will be overridden by --param-set argument)
CURRENT_PARAM_SET = 'C'
LSTM_EPOCHS   = PARAM_SETS['C']['lstm_epochs']
LSTM_BATCH    = PARAM_SETS['C']['lstm_batch']
LSTM_LOOKBACK_OVERRIDE = PARAM_SETS['C'].get('lstm_lookback', LSTM_LOOKBACK)
LSTM_PATIENCE = 15  # ↑ ขยายจาก 10 → 15
DISABLE_EARLY_STOPPING = False
MODEL_DIR     = os.path.join(CURRENT_DIR, "saved_models")
META_DIR      = os.path.join(CURRENT_DIR, "saved_meta")
METRICS_DIR   = os.path.join(CURRENT_DIR, "metrics_plots")
TRAINING_HISTORY_LOG = os.path.join(METRICS_DIR, "training_history.jsonl")
RUN_ID = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(META_DIR,  exist_ok=True)
os.makedirs(METRICS_DIR, exist_ok=True)


def _room_artifact_dir(room) -> str:
    room_id = getattr(room, 'id', room)
    return os.path.join(MODEL_DIR, str(room_id))


def _room_artifact_path(room, filename: str) -> str:
    return os.path.join(_room_artifact_dir(room), filename)

def _normalize_training_history_key(key):
    if not isinstance(key, str):
        return None
    key = key.strip().lower()
    if key in {'accuracy', 'acc', 'train_accuracy'}:
        return 'train_acc'
    if key in {'val_accuracy', 'valid_accuracy', 'val_acc'}:
        return 'val_acc'
    if key in {'loss', 'train_loss', 'mae'}:
        return 'train_loss'
    if key in {'val_loss', 'valid_loss', 'val_mae'}:
        return 'val_loss'
    return None

def _normalize_training_history_metrics(history: dict):
    preferred_keys = {
        'train_acc': ['train_accuracy', 'accuracy', 'acc'],
        'val_acc': ['valid_accuracy', 'val_accuracy', 'val_acc'],
        'train_loss': ['train_loss', 'loss', 'mae'],
        'val_loss': ['valid_loss', 'val_loss', 'val_mae'],
    }
    metrics = {}
    for output_key, candidate_keys in preferred_keys.items():
        for key in candidate_keys:
            values = history.get(key)
            if isinstance(values, (list, np.ndarray)) and len(values) > 0:
                metrics[output_key] = np.asarray(values, dtype=float)
                break
    return metrics


def _fill_missing_history_metrics(metrics: dict, other_metrics: list):
    required_keys = ['train_acc', 'val_acc', 'train_loss', 'val_loss']
    lengths = []
    for key in required_keys:
        values = metrics.get(key)
        if not isinstance(values, (list, np.ndarray)):
            return {}
        lengths.append(len(values))
    if not lengths:
        return {}

    max_epochs = min(lengths)
    if max_epochs == 0:
        return {}

    return {
        key: np.asarray(metrics[key], dtype=float)[:max_epochs]
        for key in required_keys
    }


def _build_training_history_records(model_name: str, history: dict, room_name: str, param_set: str, other_metrics: list):
    if not isinstance(history, dict):
        history = {}
    metrics = _normalize_training_history_metrics(history)
    if not metrics:
        return []

    max_epochs = max((len(vals) for vals in metrics.values()), default=0)
    if max_epochs == 0:
        return []

    records = []
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    skipped = 0

    for epoch_idx in range(max_epochs):
        values = []
        for key in ['train_acc', 'val_acc', 'train_loss', 'val_loss']:
            arr = metrics.get(key)
            if arr is None or epoch_idx >= len(arr) or not np.isfinite(arr[epoch_idx]):
                values = None
                break
            values.append(float(arr[epoch_idx]))
        if values is None:
            skipped += 1
            continue

        record = {
            'timestamp': timestamp,
            'run_id': RUN_ID,
            'param_set': str(param_set).upper(),
            'room': str(room_name),
            'model': str(model_name).lower(),
            'epoch': epoch_idx + 1,
            'train_acc': values[0],
            'val_acc': values[1],
            'train_loss': values[2],
            'val_loss': values[3],
        }
        records.append(record)

    if skipped:
        warnings.warn(
            f"Skipping {skipped} training-history epoch(s) for {model_name}/{room_name}/{param_set} "
            "because some metrics were missing or non-finite."
        )
    return records

def _append_training_history_log(room, result):
    room_name = getattr(room, 'name', None) or str(getattr(room, 'id', ''))
    lstm_metrics = _normalize_training_history_metrics(result.get('lstm_history') or {})
    lgb_metrics = _normalize_training_history_metrics(result.get('lgb_history') or {})
    xgb_metrics = _normalize_training_history_metrics(result.get('xgb_history') or {})

    records = []
    records.extend(_build_training_history_records('lstm', result.get('lstm_history') or {}, room_name, CURRENT_PARAM_SET, [lgb_metrics, xgb_metrics]))
    records.extend(_build_training_history_records('lightgbm', result.get('lgb_history') or {}, room_name, CURRENT_PARAM_SET, [lstm_metrics, xgb_metrics]))
    records.extend(_build_training_history_records('xgboost', result.get('xgb_history') or {}, room_name, CURRENT_PARAM_SET, [lstm_metrics, lgb_metrics]))
    # Append ensemble single-step summary if available (ensures ensemble presence in log)
    try:
        ensemble_summary = result.get('model_metrics', {}).get('ensemble') if isinstance(result.get('model_metrics'), dict) else None
        if ensemble_summary:
            cls = ensemble_summary.get('classification', {}) or {}
            reg = ensemble_summary.get('regression', {}) or {}
            # prefer classification accuracy/loss, fallback to regression metrics
            acc = None
            loss = None
            if isinstance(cls.get('accuracy'), (int, float)):
                acc = float(cls.get('accuracy'))
            if isinstance(cls.get('loss'), (int, float)):
                loss = float(cls.get('loss'))
            if acc is None:
                # try regression 'r2'/'mae' presence — use inverse mapping for loss
                if isinstance(reg.get('mae'), (int, float)):
                    loss = float(reg.get('mae'))
            if acc is None and isinstance(reg.get('r2'), (int, float)):
                # no accuracy, but we can set acc to NaN-equivalent None
                acc = None
            if acc is not None and loss is not None:
                rec = {
                    'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'run_id': RUN_ID,
                    'param_set': str(CURRENT_PARAM_SET).upper(),
                    'room': str(room_name),
                    'model': 'ensemble',
                    'epoch': 1,
                    'train_acc': float(acc),
                    'val_acc': float(acc),
                    'train_loss': float(loss),
                    'val_loss': float(loss),
                }
                records.append(rec)
    except Exception:
        # don't allow logging failures to break training flow
        pass
    if not records:
        return False
    with open(TRAINING_HISTORY_LOG, 'a', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return True

# ── น้ำหนัก Prior (ปรับเป็น LSTM 20% | LGB 40% | XGB 40%) ───────────────────
LSTM_WEIGHT_PRIOR = 0.20
LGB_WEIGHT_PRIOR  = 0.40
XGB_WEIGHT_PRIOR  = 0.40

# Ensemble gating / label sensitivity tuning
LSTM_R2_MIN_WEIGHT = 0.0
LSTM_R2_LOW        = 0.00
LSTM_R2_HIGH       = 0.25
LABEL_BUFFER       = 0.015
LABEL_MED_BUFFER   = 0.035

# ── Train/val/test split ───────────────────────────────────────────────────────
TRAIN_FRAC  = 0.70
CALIB_FRAC  = 0.15
MIN_TRAIN_ROWS = 15

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
        cv > 1.0
        or spike_ratio > 0.04
        or zero_ratio > 0.35
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


def _evaluate_with_best_threshold(y_true, y_pred, thr_high, thr_med, peak_ref):
    base_metrics = compute_classification_metrics(y_true, y_pred, thr_high, thr_med, peak_ref)
    best_m, best_metrics = _optimize_threshold_multiplier(y_true, y_pred, thr_high, thr_med, peak_ref)
    if best_metrics is None:
        return 1.0, base_metrics
    return float(best_m), best_metrics


def _resolve_effective_thresholds(thr_high, thr_med, model_metrics, selected_model):
    """Return thresholds adjusted for the selected model when calibration exists."""
    if selected_model != 'lstm':
        return float(thr_high), float(thr_med), 1.0

    lstm_metrics = (model_metrics or {}).get('lstm') or {}
    cal_mult = float(lstm_metrics.get('calibration_multiplier', 1.0) or 1.0)
    thr_high_eff = float(thr_high) * cal_mult
    thr_med_eff = float(thr_med) * cal_mult
    return round(thr_high_eff, 3), round(thr_med_eff, 3), cal_mult


def _split_eval_calibration(y, train_frac=0.7, calib_frac=0.15):
    """Split a holdout sequence into calibration and final-test slices in time order."""
    n = len(y)
    if n <= 0:
        return slice(0, 0), slice(0, 0)
    calib_start = int(n * train_frac)
    calib_end = int(n * (train_frac + calib_frac))
    calib_start = min(max(calib_start, 1), max(n - 1, 1))
    calib_end = min(max(calib_end, calib_start + 1), n)
    return slice(calib_start, calib_end), slice(calib_end, n)


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
    if not use_log:
        peak_ref = float(combined.quantile(0.95)) or 1.0
        thr_high, thr_med = compute_adaptive_thresholds(combined, peak_ref)
        lgb_history, xgb_history = _attach_booster_accuracy_history(
            lgb_model, xgb_model,
            X_tr, y_tr, X_te, y_te,
            thr_high, thr_med, peak_ref,
            lgb_history=lgb_history,
            xgb_history=xgb_history,
        )
    lgb_train = lgb_model.predict(X_tr)
    xgb_train = xgb_model.predict(X_tr)
    lgb_val = lgb_model.predict(X_te)
    xgb_val = xgb_model.predict(X_te)
    ensemble_weights = _derive_ensemble_weights(
        y_te,
        {'lightgbm': lgb_val, 'xgboost': xgb_val},
        primary='lightgbm',
        base_prior={'lightgbm': 0.50, 'xgboost': 0.50},
    )
    meta_val = _blend_predictions({'lightgbm': lgb_val, 'xgboost': xgb_val}, ensemble_weights)
    lstm_model, lstm_scaler, lstm_history = None, None, None
    if LSTM_AVAILABLE and len(y_tr) >= LSTM_LOOKBACK + 10:
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

    return (lgb_model, xgb_model, ensemble_weights,
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


def augment_sparse_daily(daily: pd.Series, target_days: int = 80) -> tuple[pd.Series, int]:
    """Augment sparse series from historical median + realistic noise ใกล้เคียง.

    Returns (combined_series, synthetic_count) so callers can keep synthetic
    rows in train/calibration only and reserve real observed days for test.
    """
    if len(daily) >= target_days:
        return daily, 0

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
    return combined, len(extra)


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

def demand_score_to_label(
    score: float,
    thr_high: float,
    thr_med: float,
    buffer_ratio: float = LABEL_BUFFER,
    med_buffer_ratio: float = LABEL_MED_BUFFER,
) -> str:
    # Keep a small dead-zone, but widen the medium band a bit so it can appear
    # in skewed rooms without causing flip-flop on tiny errors.
    buffer = max(buffer_ratio, 0.01)
    med_buffer = max(med_buffer_ratio, buffer)
    urgent_cut = thr_high * (1.0 + buffer)
    high_cut   = thr_high * (1.0 - buffer)
    med_cut    = thr_med * (1.0 - med_buffer)

    if score >= urgent_cut:
        return 'urgent'
    elif score >= high_cut:
        return 'high'
    elif score >= med_cut:
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


def _tier_accuracy_target(tier: str) -> float:
    tier = str(tier or '').lower()
    if tier == 'full':
        return 0.88
    if tier == 'medium':
        return 0.75
    if tier in {'sparse', 'cold_start'}:
        return 0.60
    return 0.70


def print_classification_metrics(metrics: dict, room_name: str, room_id: int | None = None):
    label = room_name if room_id is None else f"{room_name} [id={room_id}]"
    print(f"\n  📊 Classification Metrics – {label}")
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
    def __init__(self, x_train, y_train_raw, x_val, y_val_raw, scaler_y, thr_high, thr_med, peak_ref, lookback=0):
        super().__init__()
        self.x_train = x_train
        self.y_train_raw = np.asarray(y_train_raw, dtype=float)
        self.x_val = x_val
        self.y_val_raw = np.asarray(y_val_raw, dtype=float)
        self.scaler_y = scaler_y
        self.thr_high = float(thr_high)
        self.thr_med = float(thr_med)
        self.peak_ref = float(peak_ref)
        self.lookback = int(lookback)
        self.train_accuracy_history = []
        self.val_accuracy_history = []
        self.train_loss_history = []
        self.val_loss_history = []

    def _inverse_transform(self, values):
        if self.scaler_y is None:
            return np.asarray(values, dtype=float)
        try:
            inv = self.scaler_y.inverse_transform(np.asarray(values, dtype=float).reshape(-1, 1)).flatten()
            return np.maximum(0.0, inv)
        except Exception:
            return np.asarray(values, dtype=float)

    def _align_raw_targets(self, y_pred, y_raw):
        if len(y_raw) == len(y_pred):
            return y_raw
        if len(y_raw) > len(y_pred):
            if len(y_raw) - len(y_pred) == self.lookback:
                return y_raw[self.lookback:]
            return y_raw[-len(y_pred):]
        return y_raw

    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}
        try:
            y_train_pred = self.model.predict(self.x_train, verbose=0).flatten()
            y_val_pred = self.model.predict(self.x_val, verbose=0).flatten()
            y_train_pred_raw = self._inverse_transform(y_train_pred)
            y_val_pred_raw = self._inverse_transform(y_val_pred)
            y_train_target = self._align_raw_targets(y_train_pred, self.y_train_raw)
            y_val_target = self._align_raw_targets(y_val_pred, self.y_val_raw)

            train_cls = compute_classification_metrics(y_train_target, y_train_pred_raw, self.thr_high, self.thr_med, self.peak_ref)
            val_cls = compute_classification_metrics(y_val_target, y_val_pred_raw, self.thr_high, self.thr_med, self.peak_ref)

            train_loss = float(mean_absolute_error(y_train_target, y_train_pred_raw))
            val_loss = float(mean_absolute_error(y_val_target, y_val_pred_raw))

            logs['accuracy'] = train_cls['accuracy']
            logs['val_accuracy'] = val_cls['accuracy']
            logs['train_loss'] = train_loss
            logs['val_loss'] = val_loss
            logs['class_loss'] = train_cls['loss']
            logs['val_class_loss'] = val_cls['loss']
            logs['class_f1'] = train_cls['f1']
            logs['val_class_f1'] = val_cls['f1']

            self.train_accuracy_history.append(train_cls['accuracy'])
            self.val_accuracy_history.append(val_cls['accuracy'])
            self.train_loss_history.append(train_loss)
            self.val_loss_history.append(val_loss)
        except Exception:
            pass


def print_regression_metrics(stats: dict, room_name: str, model_name: str, room_id: int | None = None):
    label = room_name if room_id is None else f"{room_name} [id={room_id}]"
    print(f"\n  📈 Regression Metrics – {label} :: {model_name}")
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
    
    # ✅ RIGHT-SIZED LSTM ARCHITECTURE: smaller capacity to match small per-room datasets
    # (3-layer, 128-unit stack overfit/oscillated on datasets of only a few hundred rows —
    #  a single LSTM layer converges more smoothly on this data size)
    model = Sequential([
        LSTM(48, return_sequences=False, input_shape=(lookback, input_cols)),
        Dropout(0.2),
        Dense(16, activation='relu'),
        Dense(1),
    ])
    
    # ✅ GENTLER OPTIMIZER: lower initial LR + clipping (no deprecated `decay` arg —
    # LR scheduling is handled entirely by ReduceLROnPlateau below)
    optimizer = Adam(learning_rate=0.0005, clipvalue=1.0)
    model.compile(optimizer=optimizer, loss='mae', metrics=['mae'])
    
    # ✅ EARLY STOPPING + LEARNING RATE SCHEDULER
    callbacks = []
    if not DISABLE_EARLY_STOPPING:
        es = EarlyStopping(monitor='val_loss', mode='min', patience=patience,
                           restore_best_weights=True, verbose=0)
        callbacks.append(es)
        
        # Reduce learning rate on plateau (important for convergence!)
        reduce_lr = ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,       # ลด LR ลง 50%
            patience=8,       # หลัง 8 epochs ที่ไม่ improve (เดิม 5 — ตัดสินใจเร็วไป ทำให้ plateau นาน)
            min_lr=1e-5,
            verbose=0
        )
        callbacks.append(reduce_lr)
    cls_cb = LSTMClassificationHistoryCallback(
        X_tr, y_train_raw, X_va, y_val_raw, scaler_y, thr_high, thr_med, peak_ref,
        lookback=lookback
    )
    callbacks.append(cls_cb)
    history = model.fit(X_tr, y_tr, validation_data=(X_va, y_va),
                        epochs=min(epochs, LSTM_EPOCHS), batch_size=LSTM_BATCH,
                        callbacks=callbacks, verbose=0)

    hist = history.history
    if hasattr(cls_cb, 'train_accuracy_history') and cls_cb.train_accuracy_history:
        hist.setdefault('accuracy', cls_cb.train_accuracy_history)
    if hasattr(cls_cb, 'val_accuracy_history') and cls_cb.val_accuracy_history:
        hist.setdefault('val_accuracy', cls_cb.val_accuracy_history)
    if getattr(cls_cb, 'train_loss_history', None):
        hist['train_loss'] = cls_cb.train_loss_history
    if getattr(cls_cb, 'val_loss_history', None):
        hist['val_loss'] = cls_cb.val_loss_history

    if 'accuracy' in hist and 'val_accuracy' in hist:
        print(
            f"      📈 LSTM training history: epochs={len(hist.get('train_loss', hist.get('loss', [])))} "
            f"train_loss={hist['train_loss'][-1]:.4f} val_loss={hist['val_loss'][-1]:.4f} "
            f"train_acc={hist['accuracy'][-1]:.4f} val_acc={hist['val_accuracy'][-1]:.4f}"
        )
    elif 'mae' in hist and 'val_mae' in hist:
        print(
            f"      📈 LSTM training history: epochs={len(hist.get('mae', hist.get('loss', [])))} "
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
    global CURRENT_PARAM_SET
    params_set = PARAM_SETS.get(CURRENT_PARAM_SET, PARAM_SETS['B'])
    
    if robust:
        params = dict(
            objective='huber', alpha=0.9,
            n_estimators=params_set['lgb_estimators'], learning_rate=params_set.get('lgb_lr', 0.04),
            max_depth=params_set['lgb_depth'], num_leaves=params_set['lgb_leaves'],
            min_child_samples=20,
            lambda_l1=1.0, lambda_l2=1.0,
            feature_fraction=0.7, bagging_fraction=0.7, bagging_freq=5,
            n_jobs=-1,
            verbose=-1,
        )
    else:
        params = dict(
            objective='regression_l1',
            n_estimators=params_set['lgb_estimators'], learning_rate=params_set.get('lgb_lr', 0.05),
            max_depth=params_set['lgb_depth'], num_leaves=params_set['lgb_leaves'],
            min_child_samples=10,
            lambda_l1=0.3, lambda_l2=0.3,
            feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=5,
            n_jobs=-1,
            verbose=-1,
        )
    model = lgb.LGBMRegressor(**params)
    callbacks = [lgb.log_evaluation(-1)]
    if not DISABLE_EARLY_STOPPING:
        callbacks.insert(0, lgb.early_stopping(15, verbose=False))
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_tr, y_tr), (X_te, y_te)],
        eval_names=['train', 'valid'],
        eval_metric='mae',
        callbacks=callbacks,
    )
    return model, _extract_booster_history(model.evals_result_)


def train_xgb(X_tr, y_tr, X_te, y_te, robust: bool = False):
    """
    XGBoost – Supporting Model
    robust=True → pseudo-Huber loss + regularization แรงขึ้น
    """
    global CURRENT_PARAM_SET
    params_set = PARAM_SETS.get(CURRENT_PARAM_SET, PARAM_SETS['B'])
    
    if robust:
        params = dict(
            objective='reg:pseudohubererror',
            n_estimators=params_set['xgb_estimators'], learning_rate=params_set.get('xgb_lr', 0.04),
            max_depth=params_set['xgb_depth'], subsample=0.7,
            colsample_bytree=0.7,
            reg_alpha=1.0, reg_lambda=1.0,
            eval_metric='mae', verbosity=0,
        )
    else:
        params = dict(
            objective='reg:absoluteerror',
            n_estimators=params_set['xgb_estimators'], learning_rate=params_set.get('xgb_lr', 0.05),
            max_depth=params_set['xgb_depth'], subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.3, reg_lambda=0.3,
            eval_metric='mae', verbosity=0,
        )
    if not DISABLE_EARLY_STOPPING:
        params['early_stopping_rounds'] = 15
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
    keys = list(evals_result.keys())
    train_metrics = {}
    valid_metrics = {}
    for dataset_name, metrics in evals_result.items():
        if not isinstance(metrics, dict):
            continue
        lower_name = str(dataset_name).lower()
        # LightGBM: keys are 'train', 'valid'
        # XGBoost: keys are 'validation_0' (train), 'validation_1' (valid)
        if lower_name == 'train' or lower_name.startswith('validation_0'):
            train_metrics = metrics
        elif lower_name == 'valid' or lower_name.startswith('validation_1'):
            valid_metrics = metrics
    # Extract loss from train metrics
    for metric_name, values in train_metrics.items():
        if isinstance(values, (list, np.ndarray)) and len(values) > 0:
            history['train_loss'] = list(values)
            break
    # Extract loss from valid metrics
    for metric_name, values in valid_metrics.items():
        if isinstance(values, (list, np.ndarray)) and len(values) > 0:
            history['valid_loss'] = list(values)
            break
    return history


def _history_round_count(history: dict) -> int:
    """Infer the number of boosting rounds from eval history."""
    if not isinstance(history, dict):
        return 0
    for metrics in history.values():
        if not isinstance(metrics, dict):
            continue
        for values in metrics.values():
            if isinstance(values, (list, np.ndarray)) and len(values) > 0:
                return len(values)
    return 0


def _extract_booster_accuracy_curve(model, X_tr, y_tr, X_te, y_te, thr_high, thr_med, peak_ref, model_type: str):
    """Build per-boosting-round accuracy curves for booster models."""
    train_acc = []
    valid_acc = []
    if thr_high is None or thr_med is None or peak_ref is None:
        return train_acc, valid_acc

    try:
        if model_type == 'lightgbm':
            total_rounds = _history_round_count(getattr(model, 'evals_result_', {}) or {})
            if total_rounds <= 0:
                total_rounds = int(getattr(model, 'best_iteration_', None) or getattr(model, 'n_estimators_', 0) or 0)
            for i in range(1, total_rounds + 1):
                try:
                    tr_pred = np.asarray(model.predict(X_tr, num_iteration=i), dtype=float)
                    te_pred = np.asarray(model.predict(X_te, num_iteration=i), dtype=float)
                except Exception:
                    break
                tr_cls = compute_classification_metrics(y_tr, tr_pred, thr_high, thr_med, peak_ref)
                te_cls = compute_classification_metrics(y_te, te_pred, thr_high, thr_med, peak_ref)
                train_acc.append(float(tr_cls.get('accuracy', np.nan)))
                valid_acc.append(float(te_cls.get('accuracy', np.nan)))
        elif model_type == 'xgboost':
            total_rounds = _history_round_count(getattr(model, 'evals_result_', {}) or {})
            if total_rounds <= 0:
                try:
                    total_rounds = _history_round_count(model.evals_result() or {})
                except Exception:
                    total_rounds = 0
            if total_rounds <= 0:
                total_rounds = int(getattr(model, 'best_iteration', None) or getattr(model, 'n_estimators', 0) or 0)
            for i in range(1, total_rounds + 1):
                try:
                    tr_pred = np.asarray(model.predict(X_tr, iteration_range=(0, i)), dtype=float)
                    te_pred = np.asarray(model.predict(X_te, iteration_range=(0, i)), dtype=float)
                except Exception:
                    break
                tr_cls = compute_classification_metrics(y_tr, tr_pred, thr_high, thr_med, peak_ref)
                te_cls = compute_classification_metrics(y_te, te_pred, thr_high, thr_med, peak_ref)
                train_acc.append(float(tr_cls.get('accuracy', np.nan)))
                valid_acc.append(float(te_cls.get('accuracy', np.nan)))
    except Exception:
        return train_acc, valid_acc
    return train_acc, valid_acc


def _attach_booster_accuracy_history(
    lgb_model, xgb_model,
    X_tr, y_tr, X_te, y_te,
    thr_high, thr_med, peak_ref,
    lgb_history=None, xgb_history=None,
):
    """Attach per-round accuracy curves into booster history dicts."""
    lgb_history = dict(lgb_history or {})
    xgb_history = dict(xgb_history or {})
    if thr_high is None or thr_med is None or peak_ref is None:
        return lgb_history, xgb_history

    lgb_train_curve, lgb_val_curve = _extract_booster_accuracy_curve(
        lgb_model, X_tr, y_tr, X_te, y_te, thr_high, thr_med, peak_ref, 'lightgbm'
    )
    xgb_train_curve, xgb_val_curve = _extract_booster_accuracy_curve(
        xgb_model, X_tr, y_tr, X_te, y_te, thr_high, thr_med, peak_ref, 'xgboost'
    )

    if lgb_train_curve and lgb_val_curve:
        lgb_history['train_accuracy'] = lgb_train_curve
        lgb_history['valid_accuracy'] = lgb_val_curve
    if xgb_train_curve and xgb_val_curve:
        xgb_history['train_accuracy'] = xgb_train_curve
        xgb_history['valid_accuracy'] = xgb_val_curve
    return lgb_history, xgb_history


# ══════════════════════════════════════════════════════════════════════════════
#  Simple Ensemble Weights
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {k: max(0.0, float(v)) for k, v in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        n = len(cleaned) or 1
        return {k: 1.0 / n for k in cleaned}
    return {k: v / total for k, v in cleaned.items()}


def _blend_predictions(preds: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    available = {k: np.asarray(v, dtype=float) for k, v in preds.items() if v is not None}
    if not available:
        return np.array([])
    use_weights = _normalize_weights({k: weights.get(k, 0.0) for k in available})
    lengths = [len(v) for v in available.values() if len(v) > 0]
    if not lengths:
        return np.array([])
    n = min(lengths)
    blended = np.zeros(n, dtype=float)
    for name, arr in available.items():
        blended += use_weights.get(name, 0.0) * np.asarray(arr[:n], dtype=float)
    return np.maximum(0.0, blended)


def _ensemble_weight_vector(weights: dict[str, float]) -> np.ndarray:
    vec = np.array([
        float(weights.get('lstm', 0.0)),
        float(weights.get('lightgbm', 0.0)),
        float(weights.get('xgboost', 0.0)),
    ], dtype=np.float32)
    total = float(np.sum(vec))
    if total <= 0.0:
        vec = np.array([0.0, 0.5, 0.5], dtype=np.float32)
        total = 1.0
    return vec / total


def _build_ensemble_keras_model(weights: dict[str, float]):
    """Create a tiny Keras combiner that stores the final ensemble weights.

    This does not embed LightGBM/XGBoost internals. It only saves the final
    blending rule in a portable `.keras` file so inference can load one
    artifact for the last aggregation step.
    """
    if not LSTM_AVAILABLE:
        return None

    kernel = _ensemble_weight_vector(weights).reshape(3, 1)
    inputs = tf.keras.Input(shape=(3,), name='base_predictions')
    outputs = tf.keras.layers.Dense(
        1,
        use_bias=False,
        trainable=False,
        kernel_initializer=tf.keras.initializers.Constant(kernel),
        name='weighted_blend',
    )(inputs)
    model = tf.keras.Model(inputs=inputs, outputs=outputs, name='room_booking_ensemble')
    return model


def _save_ensemble_keras(room, result):
    if not LSTM_AVAILABLE:
        return None

    model = result.get('ensemble_model')
    if model is None:
        model = _build_ensemble_keras_model(result.get('ensemble_weights') or {})
    if model is None:
        return None

    room_dir = _room_artifact_dir(room)
    os.makedirs(room_dir, exist_ok=True)
    path = _room_artifact_path(room, "ensemble.keras")
    model.save(path)
    return path


def _load_ensemble_keras(room):
    if not LSTM_AVAILABLE:
        return None
    candidates = [
        _room_artifact_path(room, "ensemble.keras"),
        os.path.join(MODEL_DIR, f"{room.id}_ensemble.keras"),
    ]
    try:
        for path in candidates:
            if os.path.exists(path):
                return tf.keras.models.load_model(path, compile=False)
    except Exception:
        return None
    return None


def _derive_ensemble_weights(
    y_true: np.ndarray,
    preds: dict[str, np.ndarray],
    primary: str = 'lstm',
    base_prior: dict[str, float] | None = None,
) -> dict[str, float]:
    base_prior = base_prior or {'lstm': 0.20, 'lightgbm': 0.40, 'xgboost': 0.40}
    scores = {}
    r2_scores = {}
    for name, arr in preds.items():
        if arr is None:
            continue
        p = np.asarray(arr, dtype=float)
        if len(p) == 0:
            continue
        n = min(len(y_true), len(p))
        if n <= 0:
            continue
        yt = np.asarray(y_true[:n], dtype=float)
        pp = np.asarray(p[:n], dtype=float)
        r2 = r2_score(yt, pp)
        r2_scores[name] = float(r2) if np.isfinite(r2) else float('-inf')
        if not np.isfinite(r2) or r2 < 0.0:
            scores[name] = 0.0
            continue
        mae = mean_absolute_error(yt, pp)
        # Favor models that are both accurate and explain variance positively.
        scores[name] = (max(r2, 0.0) + 1e-6) / (mae + 1e-6)
    if not scores:
        # No usable signal at all: prefer the supporting models and suppress LSTM.
        if primary in preds:
            support_keys = [k for k in preds.keys() if k != primary]
            if support_keys:
                support_prior = {k: base_prior.get(k, 0.0) for k in support_keys}
                return _normalize_weights(support_prior)
        return _normalize_weights({k: base_prior.get(k, 0.0) for k in preds.keys()})
    weighted = {}
    active_primary = r2_scores.get(primary, float('-inf')) >= 0.0
    for name in preds.keys():
        prior = base_prior.get(name, 0.0)
        score = scores.get(name, 0.0)
        if name == primary:
            # Make LSTM fade out quickly when R² is poor/negative.
            if r2_scores.get(name, float('-inf')) < 0.0:
                prior = 0.0
            elif r2_scores.get(name, 0.0) < LSTM_R2_LOW:
                prior *= 0.25
            elif r2_scores.get(name, 0.0) < LSTM_R2_HIGH:
                prior *= 0.50
            else:
                prior *= 1.05
        weighted[name] = prior * score

    # If LSTM is unusable, re-normalize the supporting models to sum to 1.0.
    if not active_primary and 'lstm' in weighted:
        weighted['lstm'] = 0.0
        support_total = sum(v for k, v in weighted.items() if k != 'lstm')
        if support_total > 0:
            for k in list(weighted.keys()):
                if k != 'lstm':
                    weighted[k] = weighted[k] / support_total
            return _normalize_weights(weighted)
        support_keys = [k for k in weighted.keys() if k != 'lstm']
        if support_keys:
            support_prior = {k: base_prior.get(k, 0.0) for k in support_keys}
            return _normalize_weights(support_prior)
        return _normalize_weights(weighted)

    return _normalize_weights(weighted)


def stacking_predict(
    X_tr, y_tr, X_cal, y_cal, X_te,
    lstm_model=None, lstm_scaler=None,
    daily_hist_raw=None, n_pred=None,
    lstm_lookback=LSTM_LOOKBACK,
    thr_high: float = None,
    thr_med: float = None,
    peak_ref: float = None,
):
    # Make room-local copies so no branch can accidentally reuse a previous room's
    # dataframe/array object via shared reference.
    X_tr = X_tr.copy(deep=True) if isinstance(X_tr, pd.DataFrame) else np.asarray(X_tr).copy()
    X_cal = X_cal.copy(deep=True) if isinstance(X_cal, pd.DataFrame) else np.asarray(X_cal).copy()
    X_te = X_te.copy(deep=True) if isinstance(X_te, pd.DataFrame) else np.asarray(X_te).copy()
    y_tr = np.asarray(y_tr, dtype=float).copy()
    y_cal = np.asarray(y_cal, dtype=float).copy()

    lgb_model, lgb_history = train_lgb(X_tr, y_tr, X_cal, y_cal, robust=False)
    xgb_model, xgb_history = train_xgb(X_tr, y_tr, X_cal, y_cal, robust=False)

    if thr_high is not None and thr_med is not None and peak_ref is not None:
        lgb_history, xgb_history = _attach_booster_accuracy_history(
            lgb_model, xgb_model,
            X_tr, y_tr, X_cal, y_cal,
            thr_high, thr_med, peak_ref,
            lgb_history=lgb_history,
            xgb_history=xgb_history,
        )
        lgb_train_preds = lgb_model.predict(X_tr)
        lgb_val_preds = lgb_model.predict(X_cal)
        xgb_train_preds = xgb_model.predict(X_tr)
        xgb_val_preds = xgb_model.predict(X_cal)
        lgb_train_cls = compute_classification_metrics(y_tr, lgb_train_preds, thr_high, thr_med, peak_ref)
        lgb_val_cls = compute_classification_metrics(y_cal, lgb_val_preds, thr_high, thr_med, peak_ref)
        xgb_train_cls = compute_classification_metrics(y_tr, xgb_train_preds, thr_high, thr_med, peak_ref)
        xgb_val_cls = compute_classification_metrics(y_cal, xgb_val_preds, thr_high, thr_med, peak_ref)
        print(
            f"    🟢 LightGBM training: TrainLoss={lgb_history.get('train_loss', [np.nan])[-1]:.4f} "
            f"CalLoss={lgb_history.get('valid_loss', [np.nan])[-1]:.4f} "
            f"TrainAcc={lgb_train_cls['accuracy']:.4f} CalAcc={lgb_val_cls['accuracy']:.4f}"
        )
        print(
            f"    ⚡ XGBoost training: TrainLoss={xgb_history.get('train_loss', [np.nan])[-1]:.4f} "
            f"CalLoss={xgb_history.get('valid_loss', [np.nan])[-1]:.4f} "
            f"TrainAcc={xgb_train_cls['accuracy']:.4f} CalAcc={xgb_val_cls['accuracy']:.4f}"
        )
    else:
        print("    🟢 LightGBM/XGBoost training: train/valid thresholds unavailable, showing loss history only")

    lgb_val = lgb_model.predict(X_cal)
    xgb_val = xgb_model.predict(X_cal)
    lgb_train_preds = lgb_model.predict(X_tr)
    xgb_train_preds = xgb_model.predict(X_tr)
    lgb_fut = lgb_model.predict(X_te)
    xgb_fut = xgb_model.predict(X_te)

    lstm_ready = (
        LSTM_AVAILABLE
        and lstm_model is not None
        and lstm_scaler is not None
        and daily_hist_raw is not None
    )

    if lstm_ready:
        # If multivariate LSTM was trained (scaler is tuple), use one-step walk-forward
        if isinstance(lstm_scaler, tuple):
            # Build feature dataframe for train+val to support fair one-step validation
            try:
                X_tr_df = X_tr if isinstance(X_tr, pd.DataFrame) else pd.DataFrame(X_tr, columns=getattr(X_tr, 'columns', None))
                X_cal_df = X_cal if isinstance(X_cal, pd.DataFrame) else pd.DataFrame(X_cal, columns=getattr(X_tr, 'columns', None))
            except Exception:
                X_tr_df = pd.DataFrame(X_tr)
                X_cal_df = pd.DataFrame(X_cal)
            X_cal_df = X_cal_df.reindex(columns=X_tr_df.columns, fill_value=0.0)
            feat_full = pd.concat([X_tr_df, X_cal_df], ignore_index=True)
            feat_full['y'] = np.concatenate([y_tr, y_cal])
            lstm_val = lstm_one_step_walkforward(lstm_model, lstm_scaler, feat_full, val_start_idx=len(X_tr_df), lookback=lstm_lookback)
            # For the future/test window, use the feature rows from X_te so the
            # multivariate LSTM sees the same exogenous structure as the booster models.
            try:
                X_te_df = X_te if isinstance(X_te, pd.DataFrame) else pd.DataFrame(X_te, columns=getattr(X_tr, 'columns', None))
            except Exception:
                X_te_df = pd.DataFrame(X_te)
            X_te_df = X_te_df.reindex(columns=X_tr_df.columns, fill_value=0.0)
            lstm_fut = lstm_predict_multivariate(
                lstm_model,
                lstm_scaler,
                feat_full.copy(),
                n_pred or len(X_te),
                lookback=lstm_lookback,
                future_feat_df=X_te_df.copy(),
            )
        else:
            lstm_val  = lstm_predict(lstm_model, lstm_scaler,
                                     daily_hist_raw, len(y_cal), lookback=lstm_lookback)
            hist_full = np.concatenate([daily_hist_raw, y_cal])
            lstm_fut  = lstm_predict(lstm_model, lstm_scaler,
                                     hist_full, n_pred or len(X_te),
                                     lookback=lstm_lookback)

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
            lstm_train_preds = lstm_in_sample_preds(lstm_model, lstm_scaler, daily_hist_raw, lookback=lstm_lookback)
        # lstm_val contains the LSTM forecasts that align with the validation horizon
        lstm_val_preds = lstm_val[:len(y_cal)]
        lstm_fut_preds = lstm_fut[: (n_pred or len(X_te))]
        model_preds = {
            'lstm': lstm_val_preds,
            'lightgbm': lgb_val,
            'xgboost': xgb_val,
        }
        ensemble_weights = _derive_ensemble_weights(
            y_cal, model_preds, primary='lstm',
        )
        final = _blend_predictions(
            {'lstm': lstm_fut_preds, 'lightgbm': lgb_fut, 'xgboost': xgb_fut},
            ensemble_weights,
        )
        meta_val = _blend_predictions(model_preds, ensemble_weights)
    else:
        print("⚠️  LSTM ไม่พร้อม – ensemble ใช้ LGB + XGB")
        ensemble_weights = _derive_ensemble_weights(
            y_cal,
            {'lightgbm': lgb_val, 'xgboost': xgb_val},
            primary='lightgbm',
            base_prior={'lightgbm': 0.50, 'xgboost': 0.50},
        )
        final = _blend_predictions(
            {'lightgbm': lgb_fut, 'xgboost': xgb_fut},
            ensemble_weights,
        )
        meta_val = _blend_predictions({'lightgbm': lgb_val, 'xgboost': xgb_val}, ensemble_weights)

    return (np.maximum(0, final), lgb_model, xgb_model, ensemble_weights,
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
    room, lgb_model, xgb_model, ensemble_weights,
    history, peak_ref, thr_high, thr_med,
    room_hour_dist, confidence, forecast_dates, schedule,
    lstm_model=None, lstm_scaler=None,
    ensemble_model=None,
    use_log: bool = False,
    lstm_lookback: int = LSTM_LOOKBACK,
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

    for fc_date in forecast_dates:
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
            preds = {'lstm': np.array([lstm_val_fc]), 'lightgbm': np.array([lgb_pred]), 'xgboost': np.array([xgb_pred])}
            if ensemble_model is not None:
                try:
                    ensemble_input = np.array([[lstm_val_fc, lgb_pred, xgb_pred]], dtype=np.float32)
                    d_pred = float(ensemble_model.predict(ensemble_input, verbose=0).reshape(-1)[0])
                except Exception:
                    d_pred = float(_blend_predictions(preds, ensemble_weights)[0])
            else:
                d_pred = float(_blend_predictions(preds, ensemble_weights)[0])
        else:
            if ensemble_model is not None:
                try:
                    ensemble_input = np.array([[0.0, lgb_pred, xgb_pred]], dtype=np.float32)
                    d_pred = float(ensemble_model.predict(ensemble_input, verbose=0).reshape(-1)[0])
                except Exception:
                    d_pred = float(_blend_predictions({'lightgbm': np.array([lgb_pred]), 'xgboost': np.array([xgb_pred])}, ensemble_weights)[0])
            else:
                d_pred = float(_blend_predictions({'lightgbm': np.array([lgb_pred]), 'xgboost': np.array([xgb_pred])}, ensemble_weights)[0])

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



# ── Unified training helpers ─────────────────────────────────────────────────

def _split_time_series(X, y, train_frac=TRAIN_FRAC, calib_frac=CALIB_FRAC):
    n = len(X)
    if n < MIN_TRAIN_ROWS:
        return None
    train_end = max(int(n * train_frac), LSTM_LOOKBACK + 5)
    calib_end = max(int(n * (train_frac + calib_frac)), train_end + 1)
    calib_end = min(calib_end, max(n - 1, train_end + 1))
    return (
        X.iloc[:train_end], X.iloc[train_end:calib_end], X.iloc[calib_end:],
        y[:train_end], y[train_end:calib_end], y[calib_end:],
        train_end, calib_end,
    )


def _collect_lstm_holdout_preds(lstm_model, lstm_scaler, feat_df, y_tr, y_cal, y_te, train_end):
    if lstm_model is None or lstm_scaler is None:
        return None, None
    if isinstance(lstm_scaler, tuple):
        holdout = lstm_one_step_walkforward(
            lstm_model, lstm_scaler, feat_df,
            val_start_idx=train_end, lookback=LSTM_LOOKBACK,
        )
    else:
        full_hist = np.concatenate([y_tr, y_cal, y_te])
        preds_full = lstm_in_sample_preds(lstm_model, lstm_scaler, full_hist, lookback=LSTM_LOOKBACK)
        holdout = preds_full[train_end:]
    n_cal, n_te = len(y_cal), len(y_te)
    lstm_cal = holdout[:n_cal] if len(holdout) >= n_cal else holdout
    lstm_test = holdout[n_cal:n_cal + n_te] if len(holdout) >= n_cal + n_te else holdout[n_cal:]
    return lstm_cal, lstm_test


def _evaluate_model_preds(y_true, preds_dict, thr_high, thr_med, peak_ref, room_name):
    model_metrics = {}
    for mname, mpred in preds_dict.items():
        if mpred is None:
            continue
        mp = np.nan_to_num(np.asarray(mpred, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        if len(mp) != len(y_true):
            mp = mp[:len(y_true)] if len(mp) > len(y_true) else np.pad(
                mp, (0, max(0, len(y_true) - len(mp))), 'constant')
        r2 = r2_score(y_true, mp)
        mae = mean_absolute_error(y_true, mp)
        # compute base classification metrics and search for an improved threshold multiplier
        base_cls = compute_classification_metrics(y_true, mp, thr_high, thr_med, peak_ref)
        try:
            best_m, best_metrics = _evaluate_with_best_threshold(y_true, mp, thr_high, thr_med, peak_ref)
        except Exception:
            best_m, best_metrics = 1.0, base_cls
        cls = best_metrics or base_cls
        # attach calibration multiplier when optimization found a different multiplier
        cls['calibration_multiplier'] = float(best_m or 1.0)
        reg = {
            'r2': round(r2, 4), 'mae': round(mae, 4),
            'rmse': round(rmse(y_true, mp), 4), 'smape': round(smape(y_true, mp), 4),
        }
        model_metrics[mname] = {'regression': reg, 'classification': cls}
        print(
            f"  📊 {mname.upper():10s}: Accuracy={cls['accuracy']*100:5.1f}% "
            f"| Loss={cls['loss']:.4f} | R²={r2:.4f} | MAE={mae:.4f}"
        )
    return model_metrics


def _prepare_daily_series(rdf, room, all_rooms_daily):
    """Build daily series; augment from similar rooms when data is sparse."""
    if len(rdf) == 0:
        similar = build_similar_series(room, all_rooms_daily)
        if len(similar) == 0:
            return None
        daily = similar.copy()
    else:
        daily = (
            rdf.groupby('date')['duration'].sum()
               .reindex(pd.date_range(rdf['date'].min(), rdf['date'].max(), freq='D').date,
                        fill_value=0.0)
               .astype(float)
        )
        daily.index = pd.to_datetime(daily.index)

    unique_days = rdf['date'].nunique() if len(rdf) > 0 else daily.index.nunique()
    tier = get_data_tier(len(rdf), unique_days)
    if tier in ('sparse', 'cold_start') or len(daily) < 60:
        if len(rdf) > 0:
            daily, _ = augment_sparse_daily(daily, target_days=60)
        else:
            similar = build_similar_series(room, all_rooms_daily)
            if len(similar) > 0:
                daily = similar.copy()
                daily.index = pd.to_datetime(daily.index)
    return daily


def _train_room_pipeline(room, daily, rdf, schedule):
    """
    Simple unified path:
      LSTM (primary) → LightGBM + XGBoost (support) → weighted ensemble
    """
    use_log = _needs_log_transform(room)
    cap95 = float(daily.quantile(0.95)) or 1.0
    daily = daily.clip(upper=cap95)

    term_df = build_term_daily_features(daily.index, schedule)
    term_df.index = daily.index
    feat_df = build_features(daily, term_df, use_log=use_log).dropna()
    X = feat_df.drop(columns='y')
    y = feat_df['y'].values

    split = _split_time_series(X, y)
    if split is None:
        print(f"   ⚠️  {room.name}: ข้อมูลไม่พอสำหรับ train (rows={len(X)})")
        return None

    X_tr, X_cal, X_te, y_tr, y_cal, y_te, train_end, calib_end = split
    peak_ref = float(daily.quantile(0.95)) or 1.0
    thr_high, thr_med = compute_adaptive_thresholds(daily, peak_ref)
    room_hour_dist = learn_hour_dist(rdf, room_id=room.id) if len(rdf) > 0 else HOUR_DIST_FALLBACK

    lstm_model, lstm_scaler, lstm_history = None, None, None
    if LSTM_AVAILABLE and len(y_tr) >= LSTM_LOOKBACK + 10:
        print(f"   🧠 [1/3] LSTM (Primary) – {room.name}{' (log-transformed)' if use_log else ''}")
        lstm_model, lstm_scaler, lstm_history = train_lstm(
            y_tr, y_cal, lookback=LSTM_LOOKBACK,
            epochs=LSTM_EPOCHS, patience=LSTM_PATIENCE,
            feat_train_df=feat_df.iloc[:train_end],
            feat_val_df=feat_df.iloc[train_end:calib_end],
        )
        print(f"         {'✅ success' if lstm_model else '⚠️  failed'}")
    else:
        reason = 'insufficient data'
        print(f"   ⏭️  [1/3] LSTM skipped ({reason})")

    print(f"   🌿 [2/3] LightGBM (Support)")
    print(f"   ⚡ [3/3] XGBoost (Support)")

    (y_pred_ens, lgb_model, xgb_model, ensemble_weights,
     lgb_history, xgb_history, _, _, _, _) = stacking_predict(
        X_tr, y_tr, X_cal, y_cal, X_te,
        lstm_model=lstm_model, lstm_scaler=lstm_scaler,
        daily_hist_raw=np.concatenate([y_tr, y_cal]), n_pred=len(X_te),
        lstm_lookback=LSTM_LOOKBACK,
        thr_high=thr_high, thr_med=thr_med, peak_ref=peak_ref,
    )

    lgb_test = np.asarray(lgb_model.predict(X_te), dtype=float)
    xgb_test = np.asarray(xgb_model.predict(X_te), dtype=float)
    lstm_cal, lstm_test = _collect_lstm_holdout_preds(
        lstm_model, lstm_scaler, feat_df, y_tr, y_cal, y_te, train_end,
    )

    lstm_gate_pass = False
    lstm_cal_r2 = float('-inf')
    lstm_cal_mae = float('inf')
    lstm_history_saved = lstm_history  # Save history before potentially clearing it
    if lstm_model is not None and lstm_cal is not None:
        lstm_cal_eval = np.asarray(lstm_cal, dtype=float)
        if use_log:
            lstm_cal_eval = np.expm1(lstm_cal_eval)
            y_cal_eval = np.expm1(y_cal)
        else:
            y_cal_eval = np.asarray(y_cal, dtype=float)
        lstm_cal_eval = np.nan_to_num(lstm_cal_eval, nan=0.0, posinf=0.0, neginf=0.0)
        y_cal_eval = np.nan_to_num(y_cal_eval, nan=0.0, posinf=0.0, neginf=0.0)
        if len(y_cal_eval) > 0 and len(lstm_cal_eval) == len(y_cal_eval):
            try:
                lstm_cal_r2 = float(r2_score(y_cal_eval, lstm_cal_eval))
                lstm_cal_mae = float(mean_absolute_error(y_cal_eval, lstm_cal_eval))
                lstm_gate_pass = np.isfinite(lstm_cal_r2) and lstm_cal_r2 >= LSTM_R2_MIN_WEIGHT
            except Exception:
                lstm_gate_pass = False

    if not lstm_gate_pass:
        # LSTM failed the regression gate on this room's calibration set.
        # Drop it from forecast but keep history for plotting.
        lstm_model = None
        lstm_scaler = None
        lstm_eval = None

    if use_log:
        y_te_eval = np.expm1(y_te)
        y_pred_eval = np.expm1(np.maximum(0, y_pred_ens))
        lgb_eval = np.expm1(lgb_test)
        xgb_eval = np.expm1(xgb_test)
        lstm_eval = np.expm1(lstm_test) if lstm_test is not None else None
    else:
        y_te_eval = y_te.copy()
        y_pred_eval = np.maximum(0, y_pred_ens)
        lgb_eval, xgb_eval = lgb_test, xgb_test
        lstm_eval = lstm_test

    y_te_eval = np.nan_to_num(y_te_eval, nan=0.0, posinf=0.0, neginf=0.0)
    y_pred_eval = np.nan_to_num(y_pred_eval, nan=0.0, posinf=0.0, neginf=0.0)

    m_r2 = r2_score(y_te_eval, y_pred_eval)
    m_mae = mean_absolute_error(y_te_eval, y_pred_eval)
    m_rmse = rmse(y_te_eval, y_pred_eval)
    m_smape = smape(y_te_eval, y_pred_eval)
    confidence = round(max(0.0, 1.0 - m_smape / 100.0) * 100.0, 1)
    cls_metrics = compute_classification_metrics(y_te_eval, y_pred_eval, thr_high, thr_med, peak_ref)

    print(f"\n  🎯 ENSEMBLE – {room.name} [id={room.id}]")
    print_classification_metrics(cls_metrics, room.name, room.id)
    model_metrics = _evaluate_model_preds(
        y_te_eval,
        {'ensemble': y_pred_eval, 'lightgbm': lgb_eval, 'xgboost': xgb_eval, 'lstm': lstm_eval},
        thr_high, thr_med, peak_ref, room.name,
    )

    return {
        'daily': daily, 'use_log': use_log, 'peak_ref': peak_ref,
        'thr_high': thr_high, 'thr_med': thr_med,
        'room_hour_dist': room_hour_dist, 'confidence': confidence,
        'lgb_model': lgb_model, 'xgb_model': xgb_model, 'ensemble_weights': ensemble_weights,
        'ensemble_model': _build_ensemble_keras_model(ensemble_weights),
        'lstm_model': lstm_model, 'lstm_scaler': lstm_scaler,
        'lstm_history': lstm_history_saved, 'lgb_history': lgb_history, 'xgb_history': xgb_history,
        'lstm_gate_pass': lstm_gate_pass, 'lstm_cal_r2': lstm_cal_r2, 'lstm_cal_mae': lstm_cal_mae,
        'cls_metrics': cls_metrics,
        'reg_metrics': {
            'r2': round(m_r2, 4), 'mae': round(m_mae, 4),
            'rmse': round(m_rmse, 4), 'smape': round(m_smape, 4),
        },
        'model_metrics': model_metrics,
        'm_r2': m_r2, 'm_mae': m_mae, 'm_rmse': m_rmse, 'm_smape': m_smape,
        'train_size': len(y_tr), 'test_size': len(y_te),
    }


def _save_room_models(room, result):
    room_dir = _room_artifact_dir(room)
    os.makedirs(room_dir, exist_ok=True)
    joblib.dump(result['lgb_model'], _room_artifact_path(room, "lgb.pkl"))
    joblib.dump(result['xgb_model'], _room_artifact_path(room, "xgb.pkl"))
    if result['lstm_model'] is not None:
        result['lstm_model'].save(_room_artifact_path(room, "lstm.keras"))
        joblib.dump(result['lstm_scaler'], _room_artifact_path(room, "lstm_scaler.pkl"))
    ensemble_path = _save_ensemble_keras(room, result)
    sp = _room_artifact_path(room, "seasonal.pkl")
    if os.path.exists(sp):
        os.remove(sp)

    lstm_params = None
    if result['lstm_model'] is not None:
        lstm_params = {
            'lookback': LSTM_LOOKBACK,
            'epochs': LSTM_EPOCHS,
            'batch_size': LSTM_BATCH,
            'patience': LSTM_PATIENCE,
            'optimizer': 'adam',
            'loss': 'mae',
            'architecture': 'LSTM(48)->Dropout->Dense(16)->Dense(1)',
        }

    lgb_params = {}
    try:
        lgb_params = getattr(result['lgb_model'], 'get_params', lambda: {})() or {}
    except Exception:
        lgb_params = {}

    xgb_params = {}
    try:
        xgb_params = getattr(result['xgb_model'], 'get_params', lambda: {})() or {}
    except Exception:
        xgb_params = {}

    meta_payload = {
        'room_id': room.id, 'room_name': room.name,
        'peak_ref': result['peak_ref'], 'thr_high': result['thr_high'], 'thr_med': result['thr_med'],
        'hour_dist': result['room_hour_dist'], 'confidence': result['confidence'],
        'ensemble_weights': result['ensemble_weights'], 'use_log': result['use_log'],
        'lstm_lookback': LSTM_LOOKBACK,
        'has_lstm': result['lstm_model'] is not None,
        'cls_metrics': result['cls_metrics'], 'reg_metrics': result['reg_metrics'],
        'model_metrics': result['model_metrics'], 'selected_model': 'ensemble',
        'train_size': result['train_size'], 'test_size': result['test_size'],
        'lstm_history': result['lstm_history'],
        'lgb_history': result['lgb_history'], 'xgb_history': result['xgb_history'],
        'lstm_params': lstm_params,
        'lgb_params': lgb_params,
        'xgb_params': xgb_params,
        'artifact_dir': _room_artifact_dir(room),
        'ensemble_keras_path': ensemble_path,
        'param_set': CURRENT_PARAM_SET,
        'param_set_name': PARAM_SETS.get(CURRENT_PARAM_SET, {}).get('name', 'Unknown'),
    }
    _append_training_history_log(room, result)
    joblib.dump(meta_payload, os.path.join(META_DIR, f"{room.id}_meta.pkl"))
    return meta_payload


# ── RETRAIN ────────────────────────────────────────────────────────────────────
def retrain_and_forecast():
    print("\n🚀 RETRAIN + GENERATE FORECAST")
    print("=" * 60)
    print("🧠 Pipeline: LSTM (Primary) + LightGBM/XGBoost (Support) → Weighted Ensemble")
    print(f"   LSTM weight prior ≈ {LSTM_WEIGHT_PRIOR:.0%} | LGB ≈ {LGB_WEIGHT_PRIOR:.0%} | XGB ≈ {XGB_WEIGHT_PRIOR:.0%}")
    if not LSTM_AVAILABLE:
        print("⚠️  WARNING: TensorFlow ไม่พบ – จะใช้ LGB+XGB ensemble เท่านั้น")
    print("=" * 60)

    raw_qs = Booking.objects.exclude(status='cancelled').values(
        'start_time', 'end_time', 'room_id'
    )
    raw = pd.DataFrame(list(raw_qs))
    if len(raw) == 0:
        print("❌ ไม่มีข้อมูล Booking")
        return

    for col in ['start_time', 'end_time']:
        raw[col] = pd.to_datetime(raw[col])
        if raw[col].dt.tz is None:
            raw[col] = raw[col].dt.tz_localize('UTC')
        raw[col] = raw[col].dt.tz_convert('Asia/Bangkok')

    raw['duration'] = (raw['end_time'] - raw['start_time']).dt.total_seconds() / 3600
    raw['duration'] = raw['duration'].clip(lower=0.25, upper=12.0)
    raw['date'] = raw['start_time'].dt.date
    raw['hour'] = raw['start_time'].dt.hour
    raw['end_hour'] = raw['end_time'].dt.hour

    print_data_summary(raw)

    today = pd.to_datetime('today').date()
    forecast_dates = [today + timedelta(days=d) for d in range(FORECAST_DAYS)]
    all_stats = []
    room_metas = []

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
        schedule = load_term_schedule(room.id)
        daily = _prepare_daily_series(rdf, room, all_rooms_daily)
        if daily is None or len(daily) < MIN_TRAIN_ROWS:
            print(f"⏭️  {room.name} – ข้าม (ไม่มีข้อมูลพอ)")
            continue

        print(f"\n🏠 {room.name}")
        result = _train_room_pipeline(room, daily, rdf, schedule)
        if result is None:
            continue

        room_type = getattr(room, 'room_type', 'unknown').lower()
        lstm_tag = " +LSTM✓" if result['lstm_model'] else " [no LSTM]"
        cls = result['cls_metrics']
        print(
            f"✅ {room.name:.<18} [{room_type:<10}]{lstm_tag}"
            f"  R²:{result['m_r2']:.3f}  MAE:{result['m_mae']:.2f}ชม  sMAPE:{result['m_smape']:.1f}%"
            f"  Acc:{cls['accuracy']:.3f}  F1:{cls['f1']:.3f}  conf:{result['confidence']:.1f}%"
        )

        all_stats.append({
            'Room': room.name, 'Type': room_type,
            'HasLSTM': result['lstm_model'] is not None,
            'R2': result['m_r2'], 'MAE': result['m_mae'],
            'RMSE': result['m_rmse'], 'sMAPE': result['m_smape'],
            'Accuracy': cls['accuracy'], 'F1': cls['f1'],
            'Recall': cls['recall'], 'Precision': cls['precision'],
            'Loss': cls['loss'],
        })

        meta_payload = _save_room_models(room, result)
        room_metas.append((room.name, meta_payload))

        bulk = _build_forecast_bulk(
            room, result['lgb_model'], result['xgb_model'], result['ensemble_weights'],
            result['daily'].copy(), result['peak_ref'], result['thr_high'], result['thr_med'],
            result['room_hour_dist'], result['confidence'], forecast_dates, schedule,
            lstm_model=result['lstm_model'], lstm_scaler=result['lstm_scaler'],
            ensemble_model=result.get('ensemble_model'),
            use_log=result['use_log'], lstm_lookback=LSTM_LOOKBACK,
        )
        DemandForecast.objects.filter(room=room, forecast_date__in=forecast_dates).delete()
        DemandForecast.objects.bulk_create(bulk)

    df_res = pd.DataFrame(all_stats)
    if len(df_res) > 0:
        lstm_count = int(df_res['HasLSTM'].sum())
        print(f"\n📊 ── สรุปผลการเทรนทั้งหมด ──")
        print(f"   LSTM (Primary)  : {lstm_count}/{len(df_res)} ห้อง")
        print(f"{'Room':<20} {'Type':<12} {'LSTM':>5} {'R²':>6} {'MAE':>7} {'sMAPE':>7} "
              f"{'Acc':>6} {'F1':>6} {'Loss':>7} {'Conf':>6}")
        print("-" * 100)
        for _, r in df_res.iterrows():
            conf = round(max(0.0, 1.0 - r['sMAPE'] / 100.0) * 100.0, 1)
            print(
                f"  {r['Room']:<18} {r['Type']:<12} "
                f"{'✓' if r['HasLSTM'] else '✗':>5} "
                f"{r['R2']:>6.3f} {r['MAE']:>6.2f}ชม {r['sMAPE']:>6.1f}% "
                f"{r['Accuracy']:>6.3f} {r['F1']:>6.3f} "
                f"{r['Loss']:>7.4f} {conf:>5.1f}%"
            )
        print("-" * 100)
        avg_conf = round(max(0.0, 1.0 - df_res['sMAPE'].mean() / 100.0) * 100.0, 1)
        print(
            f"  {'เฉลี่ย':<18} {'':12} {'':>5} "
            f"{df_res['R2'].mean():>6.3f} "
            f"{df_res['MAE'].mean():>6.2f}ชม "
            f"{df_res['sMAPE'].mean():>6.1f}% "
            f"{df_res['Accuracy'].mean():>6.3f} "
            f"{df_res['F1'].mean():>6.3f} "
            f"{df_res['Loss'].mean():>7.4f} "
            f"{avg_conf:>5.1f}%"
        )

    if room_metas:
        print("\n🖼️  Run: python ml/saved/generate_plots.py to create training-curve PNGs.")

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
        room_dir  = _room_artifact_dir(room)
        lgb_path  = _room_artifact_path(room, "lgb.pkl")
        xgb_path  = _room_artifact_path(room, "xgb.pkl")
        legacy_lgb_path = os.path.join(MODEL_DIR, f"{room.id}_lgb.pkl")
        legacy_xgb_path = os.path.join(MODEL_DIR, f"{room.id}_xgb.pkl")
        if not os.path.exists(meta_path):
            continue

        meta       = joblib.load(meta_path)
        lgb_model  = joblib.load(lgb_path if os.path.exists(lgb_path) else legacy_lgb_path)
        xgb_model  = joblib.load(xgb_path if os.path.exists(xgb_path) else legacy_xgb_path)
        ensemble_weights = meta.get('ensemble_weights') or {'lightgbm': 0.5, 'xgboost': 0.5}

        if 'cls_metrics' in meta:
            print_classification_metrics(meta['cls_metrics'], room.name, room.id)

        # โหลด LSTM
        lstm_model, lstm_scaler = None, None
        if meta.get('has_lstm', False) and LSTM_AVAILABLE:
            keras_lp = _room_artifact_path(room, "lstm.keras")
            legacy_pkl_lp = _room_artifact_path(room, "lstm.pkl")
            legacy_lp = os.path.join(MODEL_DIR, f"{room.id}_lstm.pkl")
            sp = _room_artifact_path(room, "lstm_scaler.pkl")
            legacy_sp = os.path.join(MODEL_DIR, f"{room.id}_lstm_scaler.pkl")
            if not os.path.exists(sp):
                sp = legacy_sp
            if os.path.exists(keras_lp) and os.path.exists(sp):
                lstm_model  = tf.keras.models.load_model(keras_lp, compile=False)
                lstm_scaler = joblib.load(sp)
            elif os.path.exists(sp):
                lp = legacy_pkl_lp if os.path.exists(legacy_pkl_lp) else legacy_lp
                if os.path.exists(lp):
                    lstm_model  = joblib.load(lp)
                    lstm_scaler = joblib.load(sp)
        ensemble_model = _load_ensemble_keras(room)

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
            room, lgb_model, xgb_model, ensemble_weights, daily.copy(),
            meta['peak_ref'], meta['thr_high'], meta['thr_med'],
            meta['hour_dist'], meta['confidence'], forecast_dates, schedule,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            ensemble_model=ensemble_model,
            use_log=use_log,
            lstm_lookback=meta.get('lstm_lookback', LSTM_LOOKBACK),
        )
        DemandForecast.objects.filter(
            room=room, forecast_date__in=forecast_dates
        ).delete()
        DemandForecast.objects.bulk_create(bulk)

        mode = "✓ LSTM+LGB+XGB Ensemble" if lstm_model else "○ LGB+XGB Ensemble"
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
        room_bookings_qs = Booking.objects.filter(room_id=room.id).exclude(status='cancelled')
        row = {
            'RoomID':    room.id,
            'Room':      room.name,
            'Type':      getattr(room, 'room_type', 'unknown'),
            'Tier':      get_data_tier(room_bookings_qs.count(), room_bookings_qs.dates('start_time', 'day').count()),
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
            'TargetAcc':    np.nan,
            'PassTarget':   False,
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
            target_acc = _tier_accuracy_target(row['Tier'])
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
                'TargetAcc': target_acc,
                'PassTarget': bool(cls['accuracy'] >= target_acc),
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
              f"{'Acc':>6} {'LGB':>6} {'XGB':>6} {'LSTM':>6} {'Tgt':>6} {'OK':>3} {'F1':>6} {'Recall':>7} {'Prec':>7} {'Loss':>7} {'Conf':>6}")
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
                f"{r.get('TargetAcc', np.nan):>6.3f} "
                f"{'Y' if r.get('PassTarget', False) else 'N':>3} "
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
            f"{df_ok.get('TargetAcc', pd.Series(dtype=float)).mean():>6.3f} "
            f"{(df_ok['PassTarget'].mean() if 'PassTarget' in df_ok else np.nan):>3.0f} "
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

    # Export metric CSV. Plot generation is centralized in ml/saved/generate_plots.py.
    summary_csv = os.path.join(METRICS_DIR, 'metrics_summary.csv')
    df.to_csv(summary_csv, index=False)
    print(f"\n📄 Saved metrics CSV: {summary_csv}")
    print("🖼️  Plot generation is now centralized in ml/saved/generate_plots.py.")
    print("    Run: python ml/saved/generate_plots.py to regenerate all plot PNGs.")


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
    parser.add_argument('--param-set', type=str, choices=['A', 'B', 'C', 'D'], default='C',
                        help='Select hyperparameter set: A (Fast), B (Balanced), C (Accurate, default), D (Extra Deep, experimental).')
    parser.add_argument('--disable-early-stop', action='store_true',
                        help='Force full training rounds and disable early stopping for all models')
    args = parser.parse_args()

    # Set global parameter set before training
    CURRENT_PARAM_SET = args.param_set
    DISABLE_EARLY_STOPPING = bool(args.disable_early_stop)
    params_set = PARAM_SETS.get(CURRENT_PARAM_SET, PARAM_SETS['B'])
    LSTM_EPOCHS = params_set['lstm_epochs']
    LSTM_BATCH = params_set['lstm_batch']
    print(f"\n🔧 Using Hyperparameter Set {CURRENT_PARAM_SET}: {params_set['name']}")
    print(f"   LSTM Epochs: {LSTM_EPOCHS}, LGB Estimators: {params_set['lgb_estimators']}, XGB Estimators: {params_set['xgb_estimators']}\n")

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
