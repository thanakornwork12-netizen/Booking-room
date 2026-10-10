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
#    python ml/saved/forecast.py --retrain        → retrain + forecast
#    python ml/saved/forecast.py                  → forecast only (14 วัน)
#    python ml/saved/forecast.py --days 120       → forecast only ล่วงหน้า 120 วัน
#    python ml/saved/forecast.py --update-fac     → อัปเดตอุปกรณ์ภาษาไทย
#    python ml/saved/forecast.py --boost          → ปรับ threshold ให้ Urgent ง่ายขึ้น
#    python ml/saved/forecast.py --show-metrics   → แสดง metrics ที่บันทึกไว้
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
    balanced_accuracy_score, classification_report
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

# LSTM is kept in the pipeline as an optional challenger, gated behind
# recursive-calibration accuracy (see the "Tree-first" print in
# _train_room_pipeline) — it is only ever served if it beats BOTH the best
# tree model and seasonal-naive(7) on calibration. In every room trained so
# far it has not cleared that gate: e.g. 2C05-06 — LSTM CalAcc=0.578 vs
# LightGBM=0.661/XGBoost=0.660 and SNaive-7=0.578 (tied with LSTM, both below
# the trees). SKIP_LSTM lets a training run skip fitting it altogether
# (~1-2 min/room saved) without changing which model ends up serving, since
# the gate would reject it anyway — this constant is the citable reference
# for "why not LSTM" in a report.
#
# Default True since 2026-09-10: LSTM is retired from the pipeline. It never
# cleared the gate on any room, and the A/B/C runs recorded 0% LSTM weight in
# every set. Pass --with-lstm to train_from_excel.py to fit it again.
SKIP_LSTM = True
LSTM_EXCLUSION_NOTE = (
    "LSTM is trained as an optional challenger but never selected to serve: "
    "the tree-first gate in _train_room_pipeline only accepts it when its "
    "recursive-calibration accuracy beats both the best tree model and "
    "seasonal-naive(7) on the same calibration window. Across every room "
    "trained, its CalAcc has stayed below the tree winner's (e.g. 2C05-06: "
    "LSTM=0.578 vs LightGBM=0.661/XGBoost=0.660), so it has not cleared that "
    "gate. SKIP_LSTM=True skips training it to save time without changing "
    "which model serves."
)

# Peer-room training augmentation (see build_pooled_peer_rows): rooms with
# fewer than this many training rows get peer rows from same-room_type
# rooms appended to the fit at PEER_AUGMENT_WEIGHT. Rooms at/above this
# threshold already have enough of their own history — added peer rows
# would only dilute, not help. Set PEER_AUGMENT_MAX_TRAIN_ROWS = 0 to
# disable augmentation entirely.
#
# 500, not a rounder 900: tested at 900 on 2C05-06 (761 train rows, so it
# qualified) and it made things WORSE (TestAcc 0.638 vs 0.655 without
# augmentation) — that room already has enough of its own history, so
# borrowed rows only diluted its real signal. 500 excludes it and similar
# rooms, leaving augmentation for genuinely data-starved rooms (e.g. 4C05,
# ~250 train rows) where the tree has little else to learn from.
PEER_AUGMENT_MAX_TRAIN_ROWS = 500
PEER_AUGMENT_WEIGHT = 0.3

# ── Hyperparameter Set Configuration (A/B/C/D/E) ───────────────────────────────
# PARAM_SETS lives in param_sets.py (single source of truth shared with
# plotting.py) so the two files can never drift out of sync again.
sys.path.insert(0, CURRENT_DIR)
from param_sets import PARAM_SETS

# ── Config ─────────────────────────────────────────────────────────────────────
MIN_DAYS      = 30   # จำนวน booking ขั้นต่ำต่อห้อง (ข้อมูลจริง ~700+ ต่อห้อง)
MIN_UNIQUE_DAYS = 14  # จำนวนวันที่มีการใช้งานขั้นต่ำ
FORECAST_DAYS = 14
LSTM_LOOKBACK = 30  # ↑ ขยายจาก 14 → 30 เพื่อจับ seasonal patterns
# Set current parameter set (will be overridden by --param-set argument).
# D is production default: across all 5 sets tested (A-E), D scored highest
# Ensemble Acc and showed the clearest, most stable adaptive-weight advantage
# over a fixed weight (see adaptive_vs_fixed_summary.csv) — C was the prior
# default before that comparison existed.
CURRENT_PARAM_SET = 'D'
LSTM_EPOCHS   = PARAM_SETS[CURRENT_PARAM_SET]['lstm_epochs']
LSTM_BATCH    = PARAM_SETS[CURRENT_PARAM_SET]['lstm_batch']
LSTM_LOOKBACK = PARAM_SETS[CURRENT_PARAM_SET].get('lstm_lookback', LSTM_LOOKBACK)
LSTM_PATIENCE = 15  # ↑ ขยายจาก 10 → 15
# Stop when chronological calibration no longer improves.  Continuing through
# every configured round was the source of the large train/calibration gap in
# the D experiment (especially for XGBoost); the best checkpoint is restored
# below, so this improves generalisation without using the held-out test set.
# Train every configured round and pick the calibration-best one afterwards
# rather than halting mid-curve. _mark_best_booster_round finds the argmin of
# the full calibration-loss curve and _predict_booster serves exactly that
# round, so nothing later than the optimum is ever used — the only cost is
# training time, and the benefit is a complete learning curve for the plots
# plus no risk of stopping before a later, better optimum. Callers that want
# the old behaviour can set this back to False.
DISABLE_EARLY_STOPPING = True

# Budget for the walk-forward SELECTION passes only (never for a served
# model). Selection ranks feature count and LGB-vs-XGB; it does not need a
# converged fit, and running it at set E's 10000 trees / lr 0.002 made the
# selection step cost more than the training it was choosing for.
SELECTION_MAX_TREES = 400
SELECTION_MIN_LR = 0.05
# Set only by the F experiment after its train+calibration walk-forward search.
# None means use CURRENT_PARAM_SET exactly as before.
TREE_PARAMS_OVERRIDE = None
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

# ── Model policy: tree-first, LSTM only as a proven challenger ───────────────
# LightGBM/XGBoost are the serving core. LSTM may be considered only after it
# beats both seasonal-naive lag-7 and the best tree model on calibration.
LSTM_WEIGHT_PRIOR = 0.0
LGB_WEIGHT_PRIOR  = 0.50
XGB_WEIGHT_PRIOR  = 0.50

# Ensemble gating / label sensitivity tuning
LSTM_R2_MIN_WEIGHT = 0.0
LSTM_R2_LOW        = 0.00
LSTM_R2_HIGH       = 0.25
LABEL_BUFFER       = 0.03
LABEL_MED_BUFFER   = 0.06

# ── Train/val/test split ───────────────────────────────────────────────────────
# train 70% + calib 10% = 80% fit/calibration, remaining 20% held out as test
TRAIN_FRAC  = 0.70
CALIB_FRAC  = 0.10
MIN_TRAIN_ROWS = 15

# ── Room operating window ─────────────────────────────────────────────────────
# Bookings in the source data start between 08:00 and 19:00 and end by 20:00,
# so a room can be occupied at most 12h in a day. expand_bookings_to_daily
# clips every booking to this window before measuring occupancy.
ROOM_OPEN_HOUR = 8
ROOM_CLOSE_HOUR = 20

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


class PeerTermProfile:
    """(dow, in_term) seasonal-median profile pooled from peer rooms, using
    EACH peer's own class schedule to know when it was in-term.

    A university's booking pattern tracks the term/exam calendar much more
    tightly than calendar month — the same month can be mid-term one year
    and a semester break the next. Grouping peers by (dow, in_term) instead
    of (dow, month) gives a cleaner "how busy do rooms like this usually
    run right now" signal than SeasonalMedianModel's month-based grouping,
    at the cost of only knowing two term states instead of twelve months.
    """
    def __init__(self):
        self.dow_term_median = {}
        self.dow_median = {}
        self.global_median = 0.0

    def fit(self, dow_arr, in_term_arr, y_arr):
        dfp = pd.DataFrame({
            'dow': np.asarray(dow_arr, dtype=int),
            'in_term': np.asarray(in_term_arr, dtype=int),
            'y': np.asarray(y_arr, dtype=float),
        })
        if len(dfp) == 0:
            return self
        self.global_median = float(dfp['y'].median())
        self.dow_median = dfp.groupby('dow')['y'].median().to_dict()
        self.dow_term_median = dfp.groupby(['dow', 'in_term'])['y'].median().to_dict()
        return self

    def predict(self, dow_arr, in_term_arr) -> np.ndarray:
        dow_arr = np.asarray(dow_arr, dtype=int)
        in_term_arr = np.asarray(in_term_arr, dtype=int)
        out = np.empty(len(dow_arr), dtype=float)
        for i in range(len(dow_arr)):
            out[i] = self.dow_term_median.get(
                (int(dow_arr[i]), int(in_term_arr[i])),
                self.dow_median.get(int(dow_arr[i]), self.global_median),
            )
        return out


def fit_peer_profile(room, all_rooms_daily: dict, cutoff_date=None):
    """Fit two seasonal-median profiles from OTHER rooms of the same
    room_type, so a room's own model can see "how busy do rooms like this
    one usually run" as extra features — real cross-room signal, not an
    exact-value leak, since neither profile ever touches this room's own y:
      - 'seasonal': (dow, month) via SeasonalMedianModel
      - 'term':     (dow, in_term) via PeerTermProfile, using each peer's
        own class schedule — see PeerTermProfile's docstring for why this
        is often the cleaner of the two signals

    cutoff_date, when given, restricts every peer series to dates strictly
    before it (this room's own train_end). Booking activity across rooms is
    contemporaneous — without this cutoff, a peer's calibration/test-period
    demand would implicitly leak into this room's features via the profile,
    the same class of bug the diff_1/pct_chg_7 leak was. Returns None when
    there's no usable peer history at all (features become a constant 0,
    handled by build_features); the two profiles inside the returned dict
    can individually be None if only one of them had enough data.
    """
    if not all_rooms_daily:
        return None
    peers = [
        (r, s) for r, s in all_rooms_daily.items()
        if getattr(r, 'room_type', None) == getattr(room, 'room_type', None)
        and getattr(r, 'id', None) != getattr(room, 'id', None)
        and s is not None and len(s) > 0
    ]
    if cutoff_date is not None:
        cutoff_ts = pd.Timestamp(cutoff_date)
        peers = [(r, s[s.index < cutoff_ts]) for r, s in peers]
    peers = [(r, s) for r, s in peers if len(s) >= 14]
    if not peers:
        return None

    combined = pd.concat([s for _, s in peers]).groupby(level=0).mean()
    seasonal = SeasonalMedianModel().fit(combined) if len(combined) >= 14 else None

    dow_rows, in_term_rows, y_rows = [], [], []
    for r, s in peers:
        try:
            peer_schedule = load_term_schedule(r.id)
            peer_term_df = build_term_daily_features(s.index, peer_schedule)
            peer_term_df.index = s.index
            in_term_vals = peer_term_df['in_term'].to_numpy()
        except Exception:
            in_term_vals = np.zeros(len(s), dtype=int)
        dow_rows.extend(pd.to_datetime(s.index).dayofweek.tolist())
        in_term_rows.extend(list(in_term_vals))
        y_rows.extend(s.to_numpy().tolist())
    term_profile = PeerTermProfile().fit(dow_rows, in_term_rows, y_rows) if len(y_rows) >= 14 else None

    if seasonal is None and term_profile is None:
        return None
    return {'seasonal': seasonal, 'term': term_profile}


def build_pooled_peer_rows(room, all_rooms_daily: dict, cutoff_date, use_log: bool,
                            feature_columns, max_rows: int = 400):
    """Real transfer-learning rows for training: each peer room's OWN
    feature-engineered history (its own lags/rolling/term columns — not the
    target room's), restricted to dates strictly before cutoff_date (this
    room's own train_end, same leak-safety rule as fit_peer_profile).

    Meant to be added to the target room's training rows with a reduced
    sample_weight (see USE_PEER_AUGMENTATION in _train_room_pipeline) — this
    is "borrow data from other rooms" in the literal sense, stronger than
    fit_peer_profile's single summary feature, for rooms whose own history
    is too short for the tree to learn a stable pattern from alone.

    booking_ahead_df is intentionally omitted for peer rows (defaults to
    zero-filled ahead_* columns, see build_booking_ahead_features) — these
    rows exist to teach general demand/seasonal/term structure, not this
    room's own booking-lead-time behavior.

    Returns (X_peer, y_peer), both None if no usable peer history exists.
    """
    if not all_rooms_daily:
        return None, None
    cutoff_ts = pd.Timestamp(cutoff_date)
    rows_X, rows_y = [], []
    for r, daily_r in all_rooms_daily.items():
        if getattr(r, 'room_type', None) != getattr(room, 'room_type', None):
            continue
        if getattr(r, 'id', None) == getattr(room, 'id', None):
            continue
        if daily_r is None or len(daily_r) == 0:
            continue
        daily_r = daily_r[daily_r.index < cutoff_ts]
        if len(daily_r) < 60:
            continue
        try:
            peer_schedule = load_term_schedule(r.id)
            peer_term_df = build_term_daily_features(daily_r.index, peer_schedule)
            peer_term_df.index = daily_r.index
            # No peer_profile here — a peer training against its OWN
            # peer-of-peers profile adds another cross-room hop of
            # complexity for little benefit; 0 is a safe, simple default.
            peer_feat = build_features(daily_r, peer_term_df, use_log=use_log).dropna()
        except Exception:
            continue
        if len(peer_feat) < 30:
            continue
        peer_feat = peer_feat.reindex(columns=list(feature_columns) + ['y'], fill_value=0.0)
        rows_X.append(peer_feat.drop(columns='y'))
        rows_y.append(peer_feat['y'].to_numpy())
    if not rows_X:
        return None, None
    X_peer = pd.concat(rows_X, ignore_index=True)
    y_peer = np.concatenate(rows_y)
    if max_rows and len(X_peer) > max_rows:
        rng = np.random.RandomState(42)
        keep = rng.choice(len(X_peer), size=max_rows, replace=False)
        X_peer = X_peer.iloc[keep].reset_index(drop=True)
        y_peer = y_peer[keep]
    return X_peer, y_peer


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


# _optimize_threshold_multiplier / _evaluate_with_best_threshold were removed
# here. They searched a multiplier on thr_high/thr_med that maximized
# accuracy, but compute_classification_metrics labels y_true with the same
# cuts — so raising them relabels the ground truth rather than improving any
# prediction. On 3C05-06 the search picked 1.4x, which turned 81% of test
# days into 'low' and moved accuracy 0.659 -> 0.843 while balanced accuracy
# fell 0.560 -> 0.473. Shrinkage is corrected on the prediction side instead;
# see fit_prediction_calibration below. Do not reintroduce a threshold search.


def fit_prediction_calibration(y_cal, cal_pred, n_knots: int = 21):
    """Fit a monotone quantile map that restores the SPREAD of predictions.

    A regressor trained on MSE/Huber shrinks toward the mean, so its output
    under-disperses: on 3C05-06 the model predicted 'urgent' on 11 of 229
    test days when 43 were truly urgent. Cutting that compressed series with
    thresholds derived from the observed distribution puts days on the wrong
    side of the boundary — which is why these models beat seasonal-naive on
    MAE/R2 yet lost to it on accuracy.

    This maps predicted quantiles onto the calibration target's quantiles,
    so a day the model ranks in its top 5% lands where the top 5% of real
    demand lands. Being monotone it never reorders predictions, so R2/MAE
    change only through the rescale and the ranking the model learned is
    preserved.

    NOT the same thing as scaling the thresholds. compute_classification_
    metrics labels y_true and y_pred with the SAME cuts, so moving the cuts
    relabels the ground truth: on 3C05-06 a 1.4x multiplier turned 81% of
    test days into 'low' and lifted accuracy 0.659 -> 0.843 while balanced
    accuracy FELL 0.560 -> 0.473. That is moving the goalposts, not
    calibration. The thresholds are a fixed ruler; only predictions are
    adjusted here.

    Returns (pred_knots, true_knots) as plain lists for the meta pickle, or
    None when there is not enough calibration data to fit anything.
    """
    if y_cal is None or cal_pred is None:
        return None
    y_cal = np.asarray(y_cal, dtype=float)
    cal_pred = np.asarray(cal_pred, dtype=float)
    n = min(len(y_cal), len(cal_pred))
    if n < 30:
        # A quantile map fit on a handful of points chases noise; leaving
        # predictions alone is the safer default.
        return None
    y_cal, cal_pred = y_cal[:n], cal_pred[:n]
    qs = np.linspace(0.0, 1.0, n_knots)
    pred_knots = np.quantile(cal_pred, qs)
    true_knots = np.quantile(y_cal, qs)
    # np.interp needs strictly increasing x; ties collapse the map to a step.
    if not np.all(np.diff(pred_knots) > 0):
        pred_knots = np.maximum.accumulate(pred_knots + np.arange(n_knots) * 1e-9)
    return [float(v) for v in pred_knots], [float(v) for v in true_knots]


def apply_prediction_calibration(pred, calibration):
    """Apply a fit_prediction_calibration map. Values beyond the calibration
    range are extrapolated linearly from the end segments rather than
    clamped, so a test day busier than anything in calibration still ranks
    above one that is merely busy."""
    pred = np.asarray(pred, dtype=float)
    if not calibration:
        return pred
    try:
        pred_knots, true_knots = calibration
        pred_knots = np.asarray(pred_knots, dtype=float)
        true_knots = np.asarray(true_knots, dtype=float)
    except Exception:
        return pred
    if len(pred_knots) < 2 or len(pred_knots) != len(true_knots):
        return pred
    out = np.interp(pred, pred_knots, true_knots)
    lo, hi = pred < pred_knots[0], pred > pred_knots[-1]
    if lo.any():
        slope = ((true_knots[1] - true_knots[0])
                 / max(pred_knots[1] - pred_knots[0], 1e-9))
        out[lo] = true_knots[0] + slope * (pred[lo] - pred_knots[0])
    if hi.any():
        slope = ((true_knots[-1] - true_knots[-2])
                 / max(pred_knots[-1] - pred_knots[-2], 1e-9))
        out[hi] = true_knots[-1] + slope * (pred[hi] - pred_knots[-1])
    return np.maximum(out, 0.0)


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
    lgb_train = _predict_booster(lgb_model, X_tr, 'lightgbm')
    xgb_train = _predict_booster(xgb_model, X_tr, 'xgboost')
    lgb_val = _predict_booster(lgb_model, X_te, 'lightgbm')
    xgb_val = _predict_booster(xgb_model, X_te, 'xgboost')
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
    history = _extract_booster_history(model.evals_result_)
    _mark_best_booster_round(model, history)
    return model, history




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
    #
    # 'high' merged into 'urgent' (3 classes: low/medium/urgent) — it was a
    # razor-thin transitional band (~4-9% of peak_ref) that real demand
    # rarely landed in cleanly (e.g. 3.3% of 3C05-06's test days), so even a
    # highly accurate regression (R²=0.91, MAE=0.89h) almost always missed
    # it by a hair, tanking reported accuracy without reflecting worse
    # predictions. Widening its buffer didn't help (confirmed empirically —
    # errors are noise on both the medium/high and high/urgent boundaries at
    # once, so moving one boundary just redistributes them). This only
    # changes the ML training/eval labeling; the live booking search UI
    # (booking/views.py _enrich_rooms) has its own separate fixed-threshold
    # scheme and is unaffected.
    buffer = max(buffer_ratio, 0.01)
    med_buffer = max(med_buffer_ratio, buffer)
    urgent_cut = thr_high * (1.0 - buffer)
    med_cut    = thr_med * (1.0 - med_buffer)

    if score >= urgent_cut:
        return 'urgent'
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

    labels = ['low', 'medium', 'urgent']

    acc       = accuracy_score(y_true_labels, y_pred_labels)
    # Plain accuracy is close to meaningless in rooms that are empty most
    # days (1C-MEETING is 85% zero, 4C05 70%): always predicting 'low'
    # scores ~0.98 there while the regression head is no better than the
    # series mean. Balanced accuracy averages recall per class, so those
    # rooms stop inflating any mean taken across rooms, and a room that
    # genuinely never gets the top class stops looking solved.
    bal_acc   = balanced_accuracy_score(y_true_labels, y_pred_labels)
    f1        = f1_score(y_true_labels, y_pred_labels,
                         labels=labels, average='weighted', zero_division=0)
    recall    = recall_score(y_true_labels, y_pred_labels,
                             labels=labels, average='weighted', zero_division=0)
    precision = precision_score(y_true_labels, y_pred_labels,
                                labels=labels, average='weighted', zero_division=0)

    label_map = {'low': 0, 'medium': 1, 'urgent': 2}
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
        'balanced_accuracy': round(bal_acc, 4),
        'n_true_classes': int(len(set(y_true_labels))),
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


class _EpochCheckpointCallback(Callback):
    """Save the model every `freq` epochs to checkpoint_dir/epoch_<N>.keras.
    Used only by the standalone checkpoint-curve analysis (train_d_with_checkpoints.py)
    to reconstruct 'what would the ensemble look like if training stopped at
    round K' without needing separate full training runs per K — normal
    training never passes checkpoint_dir, so this is a no-op by default.
    """
    def __init__(self, checkpoint_dir: str, freq: int = 10):
        super().__init__()
        self.checkpoint_dir = checkpoint_dir
        self.freq = max(1, int(freq))
        os.makedirs(checkpoint_dir, exist_ok=True)

    def on_epoch_end(self, epoch, logs=None):
        epoch_num = epoch + 1
        if epoch_num % self.freq == 0:
            self.model.save(os.path.join(self.checkpoint_dir, f'epoch_{epoch_num}.keras'))


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

    # Same expansion the model target uses, so this summary describes the
    # series actually being learned rather than raw start-date sums.
    _expanded = expand_bookings_to_daily(df)
    daily_hours = (_expanded.groupby('date')['duration'].sum()
                   if len(_expanded) else df.groupby('date')['duration'].sum())
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


def mine_term_schedule(rdf, cutoff_date=None, min_recurrence: int = 12,
                       break_gap_days: int = 45, horizon_years: int = 3) -> list[dict]:
    """Recover the recurring class timetable from the bookings themselves.

    `TermBooking` is empty for every room in this dataset, so
    load_term_schedule() returns [] and all 18 term_* features are constant
    zeros — the single largest block of dead signal in the feature set. The
    academic calendar is nonetheless plainly present in the bookings:
    76 (room, weekday, hour) slots recur 30+ times, semester breaks show up
    as weeks near zero campus-wide, and exam weeks as totals 8x the median.

    This reconstructs the same list-of-dicts shape load_term_schedule()
    returns, so every downstream consumer (compute_term_load,
    build_term_daily_features) works unchanged.

    Method: expand bookings to the (date, weekday, hour) cells they occupy,
    keep each (weekday, hour) cell seen at least `min_recurrence` times, then
    split its dates wherever they are more than `break_gap_days` apart — that
    gap is the semester break — and emit one record per resulting term run.

    LEAKAGE: pass `cutoff_date` (the room's train_end) and only bookings
    strictly before it are used. Without a cutoff the caller is asserting
    that every row given is already in-sample.
    """
    if rdf is None or len(rdf) == 0:
        return []
    need = {'start_time', 'end_time'}
    if not need.issubset(set(getattr(rdf, 'columns', []))):
        return []
    df = rdf[['start_time', 'end_time']].copy()
    df['start_time'] = pd.to_datetime(df['start_time'], errors='coerce')
    df['end_time'] = pd.to_datetime(df['end_time'], errors='coerce')
    df = df.dropna(subset=['start_time', 'end_time'])
    if cutoff_date is not None:
        cutoff = pd.Timestamp(cutoff_date)
        df = df[df['start_time'] < cutoff]
    if len(df) == 0:
        return []

    # (weekday, hour) -> set of dates that cell was occupied
    cells: dict = {}
    for start, end in zip(df['start_time'], df['end_time']):
        if end <= start:
            continue
        cur = start.normalize()
        last = end.normalize()
        while cur <= last:
            win_s = max(start, cur + pd.Timedelta(hours=ROOM_OPEN_HOUR))
            win_e = min(end, cur + pd.Timedelta(hours=ROOM_CLOSE_HOUR))
            if win_e > win_s:
                # Hours the booking actually covers on this day, as offsets
                # from midnight: [floor(start), ceil(end)) clipped to the
                # operating window.
                h0 = int((win_s - cur).total_seconds() // 3600)
                h1 = int(np.ceil((win_e - cur).total_seconds() / 3600.0))
                for hour in range(max(h0, ROOM_OPEN_HOUR), min(h1, ROOM_CLOSE_HOUR)):
                    cells.setdefault((cur.dayofweek, hour), set()).add(cur.date())
            cur = cur + pd.Timedelta(days=1)

    schedule = []
    for (dow, hour), dates in cells.items():
        if len(dates) < min_recurrence:
            continue
        ordered = sorted(dates)
        run_start = prev = ordered[0]
        for d in ordered[1:]:
            if (d - prev).days > break_gap_days:
                schedule.append({'dow': dow, 'start_hour': hour, 'end_hour': hour + 1,
                                 'term_start': run_start, 'term_end': prev})
                run_start = d
            prev = d
        schedule.append({'dow': dow, 'start_hour': hour, 'end_hour': hour + 1,
                         'term_start': run_start, 'term_end': prev})

    # Project the observed terms forward by whole years.
    #
    # Without this the schedule stops at `cutoff_date`, so every date after it
    # falls outside every term run and build_term_daily_features emits its
    # sentinels (days_until_term_end=999, in_term=0, ...) for the entire
    # calibration and test period. The model then trains on real term values
    # and is scored on constants — measured on 3C05-06 that inverted the
    # learning curve outright: calibration loss rose from the first tree
    # (2.77 -> 5.29) and best_round collapsed to 1, versus 2.63 -> 1.82 with
    # no term features at all.
    #
    # An academic calendar repeats annually, so shifting each observed run by
    # 364 days (52 weeks, which preserves the weekday) extends it without
    # looking at a single out-of-sample booking. Copies are only added where
    # they do not overlap a run that was actually observed.
    if schedule and horizon_years > 0:
        observed = list(schedule)
        for rec in observed:
            for k in range(1, horizon_years + 1):
                shift = pd.Timedelta(days=364 * k)
                ts = (pd.Timestamp(rec['term_start']) + shift).date()
                te_ = (pd.Timestamp(rec['term_end']) + shift).date()
                clash = any(r['dow'] == rec['dow'] and r['start_hour'] == rec['start_hour']
                            and not (te_ < r['term_start'] or ts > r['term_end'])
                            for r in observed)
                if not clash:
                    schedule.append({'dow': rec['dow'], 'start_hour': rec['start_hour'],
                                     'end_hour': rec['end_hour'],
                                     'term_start': ts, 'term_end': te_,
                                     'projected': True})
    return schedule


# Mining is DISABLED by default: measured, it made the models strictly worse.
#
# On 3C05-06 (LightGBM, set A) the calibration loss curve inverted — without
# term features it fell 2.63 -> 1.82 and best_round landed at 80; with mined
# term features it ROSE from the first tree (2.77 -> 5.29) and best_round
# collapsed to 1, i.e. the served model was a single tree.
#
# Cause: a schedule mined under a cutoff cannot describe any date after it, so
# build_term_daily_features emits its sentinels (days_until_term_end=999,
# in_term=0) across the whole calibration and test period. The model trains on
# real values and is scored on constants. Projecting the observed terms forward
# by 364-day steps cut the sentinel rows from 100% to 69% of calibration but
# did not fix the curve — best_round stayed at 1.
#
# The 18 term_* features therefore stay constant zero, as they were before, and
# mine_term_schedule() is kept only so a future attempt starts from working,
# tested mining code rather than from scratch. Set use_mined=True to opt in.
def resolve_term_schedule(room_id: int, rdf=None, cutoff_date=None,
                          horizon_years: int = 3, use_mined: bool = False) -> list[dict]:
    """TermBooking rows, or a mined fallback when explicitly requested."""
    schedule = load_term_schedule(room_id)
    if schedule or not use_mined:
        return schedule
    return mine_term_schedule(rdf, cutoff_date=cutoff_date,
                              horizon_years=horizon_years)


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


def _is_fixed_th_public_holiday(d) -> int:
    """Return 1 for Thai public holidays with a fixed Gregorian date.

    We intentionally do not guess substitute days or lunar-calendar holidays:
    an incorrect "holiday" flag is worse than an explicit missing signal.
    Add an authoritative academic/public-holiday calendar later for those.
    """
    ts = pd.Timestamp(d)
    return int((ts.month, ts.day) in {
        (1, 1), (4, 6), (4, 13), (4, 14), (4, 15), (5, 1),
        (7, 28), (8, 12), (10, 13), (10, 23), (12, 5), (12, 10), (12, 31),
    })


def build_term_daily_features(date_index, schedule: list[dict]) -> pd.DataFrame:
    rows = []
    for d in date_index:
        d_date   = d.date() if hasattr(d, 'date') else d
        dow      = d.weekday() if hasattr(d, 'weekday') else pd.Timestamp(d).weekday()
        sessions, hours, in_term = 0, 0, 0
        active_starts, active_ends = [], []
        active_weekly_sessions, active_weekly_hours = 0, 0
        for tb in schedule:
            if not (tb['term_start'] <= d_date <= tb['term_end']):
                continue
            in_term = 1
            active_starts.append(tb['term_start'])
            active_ends.append(tb['term_end'])
            active_weekly_sessions += 1
            active_weekly_hours += max(0, tb['end_hour'] - tb['start_hour'])
            if tb['dow'] == dow:
                sessions += 1
                hours    += tb['end_hour'] - tb['start_hour']
        # Known in advance from the term calendar (not a statistical guess),
        # so it's safe to use for forecasting: exam/urgent-demand days
        # cluster near the end of a term, and this tells the model exactly
        # how close "now" is to that — something in_term alone can't convey.
        if active_ends:
            days_until_term_end = min((te - d_date).days for te in active_ends)
            days_since_term_start = min((d_date - ts).days for ts in active_starts)
            span = days_until_term_end + days_since_term_start
            term_progress_pct = days_since_term_start / span if span > 0 else 0.5
        else:
            days_until_term_end = 999
            days_since_term_start = 999
            term_progress_pct = 0.0
        future_starts = [tb['term_start'] for tb in schedule if tb['term_start'] >= d_date]
        past_ends = [tb['term_end'] for tb in schedule if tb['term_end'] < d_date]
        days_until_term_start = min((start - d_date).days for start in future_starts) if future_starts else 999
        days_since_term_end = min((d_date - end).days for end in past_ends) if past_ends else 999
        rows.append({
            'term_hours_day':      hours,
            'term_sessions':       sessions,
            'in_term':             in_term,
            'days_until_term_end': days_until_term_end,
            'term_progress_pct':   term_progress_pct,
            # Known schedule features: useful around term boundaries/exam weeks.
            'days_until_term_start': days_until_term_start,
            'days_since_term_start': days_since_term_start,
            'days_since_term_end':   days_since_term_end,
            'is_term_start_week':    int(in_term and days_since_term_start <= 7),
            'is_term_end_week':      int(in_term and days_until_term_end <= 7),
            'term_weekly_hours':     active_weekly_hours,
            'term_weekly_sessions':  active_weekly_sessions,
            'term_day_load_ratio':   hours / active_weekly_hours if active_weekly_hours else 0.0,
        })
    return pd.DataFrame(rows, index=date_index)


def build_booking_ahead_features(date_index, bookings_df=None) -> pd.DataFrame:
    """Known-ahead bookings as of the start of each forecast date.

    A row for date d may use only bookings created strictly before d. This
    makes the feature valid for historical backtests and live forecasting.
    """
    index = pd.DatetimeIndex(date_index)
    cols = ['ahead_bookings_1d', 'ahead_hours_1d', 'ahead_attendees_1d',
            'ahead_bookings_7d', 'ahead_hours_7d', 'ahead_bookings_14d', 'ahead_hours_14d']
    out = pd.DataFrame(0.0, index=index, columns=cols)
    if bookings_df is None or len(bookings_df) == 0 or 'created_at' not in bookings_df.columns:
        return out
    b = bookings_df.copy()
    b['booking_date'] = pd.to_datetime(b['date']).dt.normalize()
    b['created_at'] = pd.to_datetime(b['created_at'], errors='coerce')
    if getattr(b['created_at'].dt, 'tz', None) is not None:
        b['created_at'] = b['created_at'].dt.tz_localize(None)
    b['duration'] = pd.to_numeric(b.get('duration', 0), errors='coerce').fillna(0.0).clip(0, 12)
    b['attendees'] = pd.to_numeric(b.get('attendees', 0), errors='coerce').fillna(0.0)
    b = b.dropna(subset=['booking_date', 'created_at'])
    for d in index:
        known = b[b['created_at'] < d]
        for horizon in (1, 7, 14):
            window = known[(known['booking_date'] >= d) & (known['booking_date'] < d + pd.Timedelta(days=horizon))]
            suffix = f'{horizon}d'
            out.loc[d, f'ahead_bookings_{suffix}'] = len(window)
            out.loc[d, f'ahead_hours_{suffix}'] = window['duration'].sum()
            if horizon == 1:
                out.loc[d, 'ahead_attendees_1d'] = window['attendees'].sum()
    return out


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


def build_features(daily, term_df=None, use_log: bool = False, booking_ahead_df=None,
                    peer_profile=None):
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
    df['is_monday']    = (idx.dayofweek == 0).astype(int)
    df['is_friday']    = (idx.dayofweek == 4).astype(int)
    df['is_fixed_th_public_holiday'] = np.array([_is_fixed_th_public_holiday(d) for d in idx], dtype=int)

    for lag in [1, 2, 3, 7, 14, 21, 28]:
        df[f'lag_{lag}'] = df['y'].shift(lag)

    # Year-over-year signal — catches recurring annual events (e.g. exam-week
    # multi-day blocks) that repeat around the same time each year but aren't
    # visible to short lags/rolling windows (max 28 days) or the smooth
    # sin/cos(365) terms below, which can't represent a sharp one-off spike.
    # A ~15-day window (not just the exact day) absorbs the few days of
    # year-to-year date drift these recurring events actually show.
    df['lag_365']          = df['y'].shift(365)
    yoy_window              = df['y'].shift(358).rolling(15, min_periods=1)
    df['yoy_window_mean']  = yoy_window.mean()
    df['yoy_window_max']   = yoy_window.max()

    for w in [3, 7, 14, 28, 90]:
        df[f'roll_mean_{w}'] = df['y'].shift(1).rolling(w, min_periods=1).mean()
        df[f'roll_std_{w}']  = df['y'].shift(1).rolling(w, min_periods=1).std().fillna(0)
        df[f'roll_max_{w}']  = df['y'].shift(1).rolling(w, min_periods=1).max()
        df[f'roll_min_{w}']  = df['y'].shift(1).rolling(w, min_periods=1).min()

    # Dormancy signal — a room whose booking pattern has genuinely collapsed
    # (closed, repurposed, renovation) looks, on lags/season alone, like a
    # normal room having a quiet stretch, so the model keeps predicting the
    # old busy pattern. roll_mean_14 vs roll_mean_90 catches a *sustained*
    # drop (short blips average out); zero_streak catches the same thing
    # from the run-length side. Both are causal (shift(1)-based), so they
    # carry no leakage and degrade gracefully to "business as usual" (ratio
    # ~1, streak resets) once activity resumes.
    df['activity_ratio_recent_vs_long'] = (
        (df['roll_mean_14'] + 1e-6) / (df['roll_mean_90'] + 1e-6)
    ).clip(0, 5)
    prior_zero = (df['y'].shift(1) <= 1e-9).astype(int)
    df['zero_streak'] = prior_zero.groupby((prior_zero == 0).cumsum()).cumsum()

    for span in [3, 7, 14]:
        df[f'ewm_{span}'] = df['y'].shift(1).ewm(span=span, min_periods=1).mean()

    # Momentum features must be calculated from observations strictly before
    # the forecast date t.  For example, diff_1_prev at t is y[t-1]-y[t-2],
    # never y[t]-y[t-1].  This keeps the feature valid in both chronological
    # backtests and the 14-day recursive forecast, where later values are the
    # model's earlier predictions rather than leaked actual demand.
    prior_y = df['y'].shift(1)
    df['diff_1_prev'] = prior_y - df['y'].shift(2)
    df['diff_7_prev'] = prior_y - df['y'].shift(8)
    df['diff_14_prev'] = prior_y - df['y'].shift(15)
    df['diff_accel_prev'] = df['diff_1_prev'] - (df['y'].shift(2) - df['y'].shift(3))
    df['diff_7_1'] = df['lag_7'] - df['lag_1']

    # เข้ารหัสฤดูกาลจาก "ตำแหน่งบนปฏิทิน" ไม่ใช่ "ตำแหน่งแถว" — np.arange(len(df))
    # ถูกต่อเมื่อ index เป็นวันติดกันครบไม่ขาด ซึ่งจริงเฉพาะตอนเทรน (daily series
    # ถูก reindex ด้วย freq='D') แต่ตอนพยากรณ์ forecast_dates เริ่มที่ "วันนี้"
    # ขณะที่ history จบที่วันจองสุดท้าย และ build_features() ถูกเรียกบน
    # history + แถวอนาคตแถวเดียวโดยไม่มีวันว่างคั่น t จึงขยับแค่ +1 ทั้งที่ปฏิทิน
    # กระโดดไปหลายเดือน ทำให้เฟสทั้งรอบสัปดาห์และรอบปีเพี้ยนไปทั้งหมด
    # การผูกกับ dayofweek/dayofyear ทำให้เฟสนิ่งเสมอ ไม่ว่า index จะขาดช่วง
    # หรือเริ่มที่วันไหน และ sin_7_* กลายเป็นการเข้ารหัส "วันในสัปดาห์" แบบวน
    # รอบจริง (dow=6 กับ dow=0 อยู่ติดกัน) ซึ่ง df['dow'] แบบ int ดิบให้ไม่ได้
    for period, n_terms, cycle, pos in [
        (7, 3, 7.0, idx.dayofweek.to_numpy(dtype=float)),
        (365, 4, 365.25, idx.dayofyear.to_numpy(dtype=float)),
    ]:
        for k in range(1, n_terms + 1):
            df[f'sin_{period}_{k}'] = np.sin(2 * np.pi * k * pos / cycle)
            df[f'cos_{period}_{k}'] = np.cos(2 * np.pi * k * pos / cycle)

    df['ratio_vs_7d']  = (df['lag_1'] / (df['roll_mean_7']  + 1e-6)).clip(0, 5)
    df['ratio_vs_28d'] = (df['lag_1'] / (df['roll_mean_28'] + 1e-6)).clip(0, 5)
    df['trend_3_14'] = df['roll_mean_3'] - df['roll_mean_14']
    df['trend_7_28'] = df['roll_mean_7'] - df['roll_mean_28']
    ahead = build_booking_ahead_features(df.index, booking_ahead_df)
    for col in ahead.columns:
        df[col] = ahead[col].values

    if term_df is not None:
        term_aligned             = term_df.reindex(df.index, fill_value=0)
        df['term_hours_day']     = term_aligned['term_hours_day'].values
        df['term_sessions']      = term_aligned['term_sessions'].values
        df['in_term']            = term_aligned['in_term'].values
        df['days_until_term_end'] = term_aligned.get('days_until_term_end', pd.Series(999, index=term_aligned.index)).values
        df['term_progress_pct']  = term_aligned.get('term_progress_pct', pd.Series(0.0, index=term_aligned.index)).values
        df['days_until_term_start'] = term_aligned.get('days_until_term_start', pd.Series(999, index=term_aligned.index)).values
        df['days_since_term_start'] = term_aligned.get('days_since_term_start', pd.Series(999, index=term_aligned.index)).values
        df['days_since_term_end'] = term_aligned.get('days_since_term_end', pd.Series(999, index=term_aligned.index)).values
        df['is_term_start_week'] = term_aligned.get('is_term_start_week', pd.Series(0, index=term_aligned.index)).values
        df['is_term_end_week'] = term_aligned.get('is_term_end_week', pd.Series(0, index=term_aligned.index)).values
        df['term_weekly_hours'] = term_aligned.get('term_weekly_hours', pd.Series(0.0, index=term_aligned.index)).values
        df['term_weekly_sessions'] = term_aligned.get('term_weekly_sessions', pd.Series(0, index=term_aligned.index)).values
        df['term_day_load_ratio'] = term_aligned.get('term_day_load_ratio', pd.Series(0.0, index=term_aligned.index)).values
        df['term_hours_lag7']    = df['term_hours_day'].shift(7).fillna(0)
        df['term_load_28d_avg']  = df['term_hours_day'].rolling(28, min_periods=1).mean()
        df['has_term_morning']   = (df['term_hours_day'] > 0).astype(int)
        df['lag1_x_in_term']     = df['lag_1'] * df['in_term']
        df['roll7_x_term_hours'] = df['roll_mean_7'] * df['term_hours_day']
    else:
        for col in ['term_hours_day', 'term_sessions', 'in_term',
                    'days_until_term_end', 'term_progress_pct',
                    'days_until_term_start', 'days_since_term_start', 'days_since_term_end',
                    'is_term_start_week', 'is_term_end_week',
                    'term_weekly_hours', 'term_weekly_sessions', 'term_day_load_ratio',
                    'term_hours_lag7', 'term_load_28d_avg',
                    'has_term_morning', 'lag1_x_in_term', 'roll7_x_term_hours']:
            df[col] = 999.0 if col in {'days_until_term_end', 'days_until_term_start', 'days_since_term_start', 'days_since_term_end'} else 0.0

    # Cross-room signal: "how busy do peer rooms of the same type usually
    # run on a day like this" — a fixed calendar lookup fit only on peer
    # history from before this room's own train cutoff (see fit_peer_profile),
    # so it carries real pattern from data this room's own history is too
    # short to show, without leaking any room's calibration/test values.
    #
    # A (dow, in_term) variant of this (PeerTermProfile, still defined above)
    # was tried and measured on 2C05-06's held-out test: WORSE (TestAcc 0.616
    # vs 0.655 for (dow, month) alone) — extra features on top of a small,
    # noisy series pushed feature selection to keep fewer, less useful
    # columns overall (top_k dropped 30→20) rather than adding real signal.
    # Reverted to just the (dow, month) profile; PeerTermProfile/fit_peer_profile
    # still compute and store 'term' in case a future room/config benefits.
    seasonal_profile = peer_profile.get('seasonal') if peer_profile else None
    if seasonal_profile is not None:
        peer_seasonal = seasonal_profile.predict_series(idx)
        if use_log:
            peer_seasonal = np.log1p(np.clip(peer_seasonal, 0, None))
        df['peer_seasonal'] = peer_seasonal
    else:
        df['peer_seasonal'] = 0.0
    df['own_vs_peer_gap'] = df['roll_mean_7'] - df['peer_seasonal']

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
               feat_train_df: pd.DataFrame = None, feat_val_df: pd.DataFrame = None,
               checkpoint_dir: str = None, checkpoint_freq: int = 10):
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
    
    # Stop based only on the chronological calibration slice and restore the
    # best validation weights.  The old implementation set patience equal to
    # the total epoch budget, so it could never stop early and kept fitting
    # training noise after validation had plateaued.
    total_epochs = min(epochs, LSTM_EPOCHS)
    callbacks = []
    early_stop_patience = (
        total_epochs if DISABLE_EARLY_STOPPING
        else max(3, min(int(patience), max(3, total_epochs // 3)))
    )
    es = EarlyStopping(monitor='val_loss', mode='min', patience=early_stop_patience,
                        restore_best_weights=True, verbose=0)
    callbacks.append(es)
    if not DISABLE_EARLY_STOPPING:
        # Reduce learning rate on plateau (independent of the above — only
        # adjusts LR mid-training, never shortens the run).
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
    if checkpoint_dir:
        callbacks.append(_EpochCheckpointCallback(checkpoint_dir, freq=checkpoint_freq))
    history = model.fit(X_tr, y_tr, validation_data=(X_va, y_va),
                        epochs=total_epochs, batch_size=LSTM_BATCH,
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

    # Record which epoch's weights actually ended up in the model (1-indexed
    # to match how epoch counts are normally reported/printed).
    val_loss_hist = hist.get('val_loss') or []
    if val_loss_hist:
        best_epoch = int(np.argmin(val_loss_hist)) + 1
        hist['best_epoch'] = best_epoch
        print(
            f"      🏆 LSTM best epoch: {best_epoch}/{len(val_loss_hist)} "
            f"(val_loss={val_loss_hist[best_epoch - 1]:.4f}) — weights restored from here, "
            f"trained all {len(val_loss_hist)} epochs regardless"
        )

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

def _robust_reg_scale(n_estimators: int) -> float:
    """0.0 (few boosting rounds) .. 1.0 (90+ rounds) — how much of the extra
    robust-mode regularization to actually apply.

    Why: the robust-mode regularization strengths below were tuned back when
    every param set used 20-90 rounds. Once round counts got halved (10-50),
    applying that same fixed regularization made rooms that trigger robust
    mode (CV(y_tr) > 1.0) underfit badly with few rounds — confirmed on 2C09
    (Set A, 10 rounds): CalAcc dropped to ~0.62 vs its normal ~0.85+. Scaling
    the extra regularization by how many rounds are actually available keeps
    robust mode's outlier-robustness benefit without starving low-round sets
    of the capacity needed to fit at all."""
    return float(np.clip(n_estimators / 90.0, 0.0, 1.0))


def train_lgb(X_tr, y_tr, X_te, y_te, robust: bool = False, sample_weight=None):
    """
    LightGBM – Supporting Model
    robust=True → Huber loss + regularization แรงขึ้น
    Huber loss ดีกว่า MAE สำหรับข้อมูลที่มี extreme outlier เป็นครั้งคราว
    """
    global CURRENT_PARAM_SET
    params_set = TREE_PARAMS_OVERRIDE or PARAM_SETS.get(CURRENT_PARAM_SET, PARAM_SETS['B'])

    if robust:
        scale = _robust_reg_scale(params_set['lgb_estimators'])
        params = dict(
            objective='huber', alpha=0.9,
            n_estimators=params_set['lgb_estimators'], learning_rate=params_set.get('lgb_lr', 0.04),
            max_depth=params_set['lgb_depth'], num_leaves=params_set['lgb_leaves'],
            min_child_samples=int(round(20 + 10 * scale)),
            lambda_l1=0.8 + 0.7 * scale, lambda_l2=0.8 + 0.7 * scale,
            feature_fraction=0.75, bagging_fraction=0.75, bagging_freq=5,
            n_jobs=-1,
            verbose=-1,
        )
    else:
        params = dict(
            objective='regression_l1',
            n_estimators=params_set['lgb_estimators'], learning_rate=params_set.get('lgb_lr', 0.05),
            max_depth=params_set['lgb_depth'], num_leaves=params_set['lgb_leaves'],
            min_child_samples=params_set.get('lgb_min_child_samples', 20),
            lambda_l1=params_set.get('lgb_lambda_l1', 0.8), lambda_l2=params_set.get('lgb_lambda_l2', 0.8),
            feature_fraction=params_set.get('lgb_feature_fraction', 0.75), bagging_fraction=params_set.get('lgb_bagging_fraction', 0.75), bagging_freq=5,
            n_jobs=-1,
            verbose=-1,
        )
    model = lgb.LGBMRegressor(**params)
    callbacks = [lgb.log_evaluation(-1)]
    if not DISABLE_EARLY_STOPPING:
        callbacks.insert(0, lgb.early_stopping(_early_stopping_rounds(params), verbose=False))
    model.fit(
        X_tr, y_tr,
        sample_weight=sample_weight,
        eval_set=[(X_tr, y_tr), (X_te, y_te)],
        eval_names=['train', 'valid'],
        eval_metric='mae',
        callbacks=callbacks,
    )
    history = _extract_booster_history(model.evals_result_)
    _mark_best_booster_round(model, history)
    return model, history


class HurdleRegressor:
    """Two-stage (hurdle) model for zero-inflated room demand.

    These rooms are empty on 32-85% of days and otherwise booked for 3-12
    hours; there is very little mass in between. A single regressor trained
    on MAE/Huber cannot represent both modes, so it lands between them —
    measured on 3C05-06, the model never predicted below 0.59h although 25%
    of real days are exactly 0. That single failure drives most of the MAE.

    Stage 1 (`gate`) predicts whether the room is used at all; stage 2
    (`positive`) predicts hours GIVEN it is used, trained only on non-empty
    days so its target is unimodal. `mode` combines them:
      'hard' — 0 when P(used) < 0.5, else the stage-2 value.
      'soft' — P(used) * stage-2, a smoother estimate that keeps some
               signal when the gate is unsure.

    Neither is universally better: on the room survey 'hard'/'soft' cut MAE
    in 6 of 8 rooms but made 2C09 and 1C-MEETING clearly worse, so the
    choice is made per room on calibration, never assumed.

    Exposes .predict() and no _calibration_best_round, so _predict_booster
    falls through to it and the recursive rollout needs no special case.
    """

    def __init__(self, gate, positive, mode: str = 'hard', threshold: float = 0.5):
        self.gate = gate
        self.positive = positive
        self.mode = mode
        self.threshold = float(threshold)

    def predict(self, X, num_iteration=None, iteration_range=None):
        """Combine the two stages.

        `num_iteration` / `iteration_range` are forwarded to the stage-2
        model with the gate held fixed, so _extract_booster_accuracy_curve
        can still walk the boosting rounds and the per-round training curves
        keep rendering for hurdle rooms. Without this passthrough those
        rooms would drop out of training_curves_by_set.png entirely.
        """
        prob = np.asarray(self.gate.predict_proba(X), dtype=float)[:, 1]
        kw = {}
        if num_iteration is not None:
            kw['num_iteration'] = num_iteration
        if iteration_range is not None:
            kw['iteration_range'] = iteration_range
        try:
            raw = self.positive.predict(X, **kw) if kw else self.positive.predict(X)
        except TypeError:
            raw = self.positive.predict(X)
        hours = np.maximum(0.0, np.asarray(raw, dtype=float))
        if self.mode == 'soft':
            return prob * hours
        return np.where(prob >= self.threshold, hours, 0.0)

    # Curve/'introspection attributes proxied to the stage-2 booster so the
    # plotting helpers treat a hurdle room like any other room.
    @property
    def evals_result_(self):
        return getattr(self.positive, 'evals_result_', {}) or {}

    @property
    def best_iteration_(self):
        return getattr(self.positive, 'best_iteration_', None)

    @property
    def n_estimators_(self):
        return getattr(self.positive, 'n_estimators_', 0)

    @property
    def feature_importances_(self):
        return getattr(self.positive, 'feature_importances_', None)

    # Callers resolve the column order with
    #   getattr(model, 'feature_name_', None) or getattr(model, 'feature_names_in_', None)
    # and fall back to "every column in the frame" when both are missing.
    # Without these proxies a hurdle room was handed all 94 engineered columns
    # while its stage-2 booster had been fitted on the selected subset, which
    # aborted scoring for exactly the rooms that chose a hurdle (2C09, 2C10-11)
    # and silently spared the one whose selection happened to keep all 94.
    @property
    def feature_name_(self):
        return getattr(self.positive, 'feature_name_', None)

    @property
    def feature_names_in_(self):
        return getattr(self.positive, 'feature_names_in_', None)

    def evals_result(self):
        fn = getattr(self.positive, 'evals_result', None)
        return fn() if callable(fn) else {}

    def get_params(self, deep=True):
        fn = getattr(self.positive, 'get_params', None)
        base = fn(deep) if callable(fn) else {}
        return {**base, 'hurdle_mode': self.mode}

    def with_mode(self, mode: str):
        """Same fitted stages, different combination rule — free to create."""
        return HurdleRegressor(self.gate, self.positive, mode=mode,
                               threshold=self.threshold)


def train_hurdle(model_type, fit_X, fit_y, X_cal, y_cal, mode='hard',
                 robust: bool = False, sample_weight=None):
    """Fit a HurdleRegressor using the current param set's tree size.

    'hard' and 'soft' differ only in how the two stages are combined, so
    callers comparing both should fit once and call `.with_mode()` rather
    than calling this twice — at set E's 10k trees a redundant fit costs as
    much as the model itself.

    Returns None when the split is too lopsided for a gate to be learnable —
    a classifier needs both classes present in usable numbers, and the
    stage-2 regressor needs enough non-empty days to fit at all.
    """
    params_set = TREE_PARAMS_OVERRIDE or PARAM_SETS.get(CURRENT_PARAM_SET, PARAM_SETS['B'])
    nz = np.asarray(fit_y, dtype=float) > 1e-9
    if nz.sum() < 30 or (~nz).sum() < 15:
        return None
    if model_type == 'lightgbm':
        gate = lgb.LGBMClassifier(
            n_estimators=params_set['lgb_estimators'],
            learning_rate=params_set.get('lgb_lr', 0.05),
            max_depth=params_set['lgb_depth'], num_leaves=params_set['lgb_leaves'],
            min_child_samples=params_set.get('lgb_min_child_samples', 20),
            n_jobs=-1, verbose=-1,
        )
    else:
        gate = xgb.XGBClassifier(
            n_estimators=params_set['xgb_estimators'],
            learning_rate=params_set.get('xgb_lr', 0.05),
            max_depth=params_set['xgb_depth'],
            min_child_weight=params_set.get('xgb_min_child_weight', 1),
            eval_metric='logloss', verbosity=0, n_jobs=-1,
        )
    gate.fit(fit_X, nz.astype(int), sample_weight=sample_weight)

    sub_X = fit_X[nz] if isinstance(fit_X, pd.DataFrame) else fit_X[nz]
    sub_y = np.asarray(fit_y, dtype=float)[nz]
    sub_w = np.asarray(sample_weight)[nz] if sample_weight is not None else None
    trainer = train_lgb if model_type == 'lightgbm' else train_xgb
    # Stage 2 early-stops on the non-empty calibration days only, matching
    # the subset it is fit on; an all-days eval set would push it back
    # toward predicting the zeros stage 1 already handles.
    cal_nz = np.asarray(y_cal, dtype=float) > 1e-9
    if cal_nz.sum() >= 5:
        cal_X = X_cal[cal_nz] if isinstance(X_cal, pd.DataFrame) else X_cal[cal_nz]
        cal_y = np.asarray(y_cal, dtype=float)[cal_nz]
    else:
        cal_X, cal_y = X_cal, np.asarray(y_cal, dtype=float)
    positive, _ = trainer(sub_X, sub_y, cal_X, cal_y, robust=robust, sample_weight=sub_w)
    return HurdleRegressor(gate, positive, mode=mode)


def _early_stopping_rounds(params: dict) -> int:
    """Early-stopping patience for the current param set.

    A fixed patience of 10 was the real cap on model capacity: at lr 0.04 a
    room's calibration loss plateaus for more than 10 rounds early on, so
    training stopped almost immediately (observed best_round=80/80 for
    LightGBM and 76/80 for XGBoost — i.e. it never even reached the limit
    it was given). Low learning rates need proportionally more patience or
    they can never be trained to convergence, which is what made these
    models underfit rather than overfit.

    Each param set now states its own 'patience'; the n//20 rule is only a
    fallback for sets that predate the key.
    """
    params_set = TREE_PARAMS_OVERRIDE or PARAM_SETS.get(CURRENT_PARAM_SET, {})
    explicit = (params_set or {}).get('patience')
    if isinstance(explicit, (int, np.integer)) and explicit > 0:
        return int(explicit)
    n = int(params.get('n_estimators', 100) or 100)
    return max(50, n // 20)


def train_xgb(X_tr, y_tr, X_te, y_te, robust: bool = False, sample_weight=None):
    """
    XGBoost – Supporting Model
    robust=True → pseudo-Huber loss + regularization แรงขึ้น
    """
    global CURRENT_PARAM_SET
    params_set = TREE_PARAMS_OVERRIDE or PARAM_SETS.get(CURRENT_PARAM_SET, PARAM_SETS['B'])
    
    if robust:
        scale = _robust_reg_scale(params_set['xgb_estimators'])
        params = dict(
            objective='reg:pseudohubererror',
            n_estimators=params_set['xgb_estimators'], learning_rate=params_set.get('xgb_lr', 0.04),
            max_depth=params_set['xgb_depth'], subsample=0.85 - 0.15 * scale,
            colsample_bytree=0.85 - 0.15 * scale,
            reg_alpha=0.8 + 0.7 * scale, reg_lambda=0.8 + 0.7 * scale,
            eval_metric='mae', verbosity=0,
        )
    else:
        params = dict(
            objective='reg:absoluteerror',
            n_estimators=params_set['xgb_estimators'], learning_rate=params_set.get('xgb_lr', 0.05),
            max_depth=params_set['xgb_depth'], min_child_weight=params_set.get('xgb_min_child_weight', 1),
            subsample=params_set.get('xgb_subsample', 0.8), colsample_bytree=params_set.get('xgb_colsample_bytree', 0.8),
            reg_alpha=params_set.get('xgb_reg_alpha', 0.8), reg_lambda=params_set.get('xgb_reg_lambda', 0.8),
            eval_metric='mae', verbosity=0,
        )
    if not DISABLE_EARLY_STOPPING:
        params['early_stopping_rounds'] = _early_stopping_rounds(params)
    model = xgb.XGBRegressor(**params, n_jobs=-1)
    model.fit(
        X_tr, y_tr,
        sample_weight=sample_weight,
        eval_set=[(X_tr, y_tr), (X_te, y_te)],
        verbose=False,
    )
    history = _extract_booster_history(model.evals_result())
    _mark_best_booster_round(model, history)
    return model, history


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


def _mark_best_booster_round(model, history: dict):
    """Save the calibration-best round after training every configured round."""
    losses = (history or {}).get('valid_loss') or []
    valid = [(i, float(value)) for i, value in enumerate(losses, start=1)
             if np.isfinite(value)]
    if valid:
        best_round, best_loss = min(valid, key=lambda item: item[1])
        setattr(model, '_calibration_best_round', int(best_round))
        history['best_round'] = int(best_round)
        history['best_valid_loss'] = best_loss


def _model_feature_names(model):
    """คอลัมน์ที่โมเดลถูกเทรนมา (หลัง feature selection) หรือ None ถ้าไม่รู้"""
    names = getattr(model, 'feature_name_', None)
    if names is None:
        names = getattr(model, 'feature_names_in_', None)
    return list(names) if names is not None else None


def _predict_booster(model, X, model_type: str):
    """Predict with the persisted calibration-best round, not early stopping.

    จัดคอลัมน์ให้ตรงกับที่โมเดลเทรนมาก่อนทาย — การเทรนเลือกเหลือบางฟีเจอร์ต่อห้อง
    (เช่น 94 → 10) แต่ตอนพยากรณ์จริง (_build_forecast_bulk) สร้างครบทุกคอลัมน์
    เดิมจึงพังด้วย "number of features ... not the same" และไม่มีผลพยากรณ์ใหม่เลย"""
    names = _model_feature_names(model)
    if names and isinstance(X, pd.DataFrame) and list(X.columns) != names:
        X = X.reindex(columns=names, fill_value=0.0)
    best_round = getattr(model, '_calibration_best_round', None)
    if not isinstance(best_round, (int, np.integer)) or best_round < 1:
        return np.asarray(model.predict(X), dtype=float)
    if model_type == 'lightgbm':
        return np.asarray(model.predict(X, num_iteration=int(best_round)), dtype=float)
    if model_type == 'xgboost':
        return np.asarray(model.predict(X, iteration_range=(0, int(best_round))), dtype=float)
    raise ValueError(f'Unknown booster type: {model_type}')


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


def _peak_sample_weights(y_tr: np.ndarray, high_quantile: float = 0.80, peak_weight: float = 1.25) -> np.ndarray:
    """Upweight the highest-demand rows in TRAIN so the model isn't penalized
    equally for under- vs over-predicting them.

    A modest upweight protects rare peak days without making a model fitted on
    an earlier busy term systematically over-predict a quieter later period.

    Derived from y_tr's own quantile only — no calibration, no test, no
    peak_ref/thr_high dependency — so it can't leak anything."""
    if len(y_tr) == 0:
        return np.ones(0)
    cutoff = np.quantile(y_tr, high_quantile)
    return np.where(y_tr >= cutoff, peak_weight, 1.0)


def _select_important_features(X_tr: pd.DataFrame, y_tr: np.ndarray, top_k: int = 30) -> list:
    """Quick LightGBM fit purely to rank features by importance, then keep
    only the top_k most useful ones.

    Why: each room has ~60 engineered features but only ~500-700 effective
    training rows — a high feature:row ratio that invites the final models
    to fit noise in the least-useful columns instead of real signal. This
    probe fit and the importance ranking use TRAIN data only (X_tr/y_tr),
    never calibration or test, so trimming features this way can't leak
    anything — it's the same kind of decision a person would make by eyeballing
    feature importances before modeling, just automated and scoped to train."""
    if X_tr.shape[1] <= top_k:
        return list(X_tr.columns)
    try:
        probe = lgb.LGBMRegressor(
            objective='regression_l1', n_estimators=80, learning_rate=0.08,
            max_depth=6, num_leaves=31, min_child_samples=10,
            n_jobs=-1, verbose=-1,
        )
        probe.fit(X_tr, y_tr)
        importances = pd.Series(probe.feature_importances_, index=X_tr.columns)
        return importances.sort_values(ascending=False).head(top_k).index.tolist()
    except Exception:
        return list(X_tr.columns)


def _cv_select_lgb_xgb_winner(X, y, thr_high, thr_med, peak_ref, n_folds: int = 3) -> dict:
    """Cross-validated comparison of LightGBM vs XGBoost for the ensemble
    SELECTION decision only (the models actually used for serving are still
    trained once on the full train split, as before).

    A single calibration slice (~90-110 days) is one noisy point estimate of
    which model generalizes better. This instead trains copies of each model
    on several different walk-forward cuts WITHIN the train+calibration
    region (X/y here — never test) and averages each model's accuracy across
    folds — the same principle as k-fold cross-validation, which exists
    specifically to stop a single small sample from deciding a
    model-selection call. A model that's genuinely better should win
    consistently across folds; one that only "won" by luck on one slice gets
    averaged back down.

    The fold probes use the ACTIVE param set's real hyperparameters
    (PARAM_SETS[CURRENT_PARAM_SET]) — this used to be a fixed lightweight
    config (60 estimators/depth 5) regardless of which set was training,
    which meant the selection never actually depended on the set being
    evaluated: it compared the same two fixed probes to the same room data
    every time, so the winner was a pure property of the room, never of the
    hyperparameters under test. Now a genuinely different config can
    genuinely produce a different winner, like the rest of the A-E
    comparison is supposed to measure.

    Returns {'lightgbm': avg_accuracy, 'xgboost': avg_accuracy}, or {} if
    there wasn't enough data to run any fold.
    """
    global CURRENT_PARAM_SET
    params_set = PARAM_SETS.get(CURRENT_PARAM_SET, PARAM_SETS['B'])

    n = len(X)
    cut_fracs = np.linspace(0.5, 0.8, n_folds)
    lgb_scores, xgb_scores = [], []
    for frac in cut_fracs:
        cut = int(n * frac)
        val_end = min(cut + max(10, int(n * 0.1)), n)
        if cut < MIN_TRAIN_ROWS or val_end - cut < 3:
            continue
        X_fold_tr, y_fold_tr = X.iloc[:cut], y[:cut]
        X_fold_val, y_fold_val = X.iloc[cut:val_end], y[cut:val_end]

        try:
            fold_weights = _peak_sample_weights(y_fold_tr)
            lgb_fold = lgb.LGBMRegressor(
                objective='regression_l1',
                n_estimators=params_set['lgb_estimators'], learning_rate=params_set.get('lgb_lr', 0.08),
                max_depth=params_set['lgb_depth'], num_leaves=params_set['lgb_leaves'], min_child_samples=20,
                lambda_l1=0.8, lambda_l2=0.8, feature_fraction=0.75,
                bagging_fraction=0.75, bagging_freq=5,
                n_jobs=-1, verbose=-1,
            )
            xgb_fold = xgb.XGBRegressor(
                objective='reg:absoluteerror',
                n_estimators=params_set['xgb_estimators'], learning_rate=params_set.get('xgb_lr', 0.08),
                max_depth=params_set['xgb_depth'], subsample=0.75, colsample_bytree=0.75,
                reg_alpha=0.8, reg_lambda=0.8,
                verbosity=0, n_jobs=-1,
            )
            lgb_fold.fit(X_fold_tr, y_fold_tr, sample_weight=fold_weights)
            xgb_fold.fit(X_fold_tr, y_fold_tr, sample_weight=fold_weights)
        except Exception:
            continue

        lgb_pred = np.asarray(lgb_fold.predict(X_fold_val), dtype=float)
        xgb_pred = np.asarray(xgb_fold.predict(X_fold_val), dtype=float)
        lgb_scores.append(compute_classification_metrics(y_fold_val, lgb_pred, thr_high, thr_med, peak_ref)['accuracy'])
        xgb_scores.append(compute_classification_metrics(y_fold_val, xgb_pred, thr_high, thr_med, peak_ref)['accuracy'])

    if not lgb_scores or not xgb_scores:
        return {}
    return {'lightgbm': float(np.mean(lgb_scores)), 'xgboost': float(np.mean(xgb_scores))}


def _cv_select_tree_config(X, y, thr_high, thr_med, peak_ref, candidates, n_folds: int = 3):
    """Choose top_k and LGB/XGB winner within supplied parameter sets.

    Feature importance is re-fit inside every fold from that fold's training
    rows only.  Thus neither validation nor held-out test targets influence
    the feature count or hyperparameter choice.
    """
    # 50 and "everything" are in the grid because the old (10, 20, 30) never
    # offered the option of keeping most of the columns, and 26 of the 94
    # engineered features are constant zeros in this dataset (18 term_* with
    # an empty TermBooking table, 7 ahead_* with no usable created_at, and
    # peer_seasonal). Selecting 10 of 94 therefore meant 10 of ~68 real ones.
    # Walk-forward CV picks per room, so a wider grid can only help: if the
    # tight counts really are better, they still win.
    n_features = X.shape[1] if hasattr(X, 'shape') else 30
    top_ks = tuple(sorted({k for k in (10, 20, 30, 50, n_features) if k <= n_features}))
    records = []
    n = len(X)
    # This loop only RANKS (top_k, family) — it never produces a served
    # model — yet it fits n_folds x len(top_ks) x len(candidates) x 2
    # boosters with no eval_set, so every fit runs the full n_estimators.
    # At set E's 10000 trees that is 18 full fits per room before real
    # training even starts, which dominated the whole run. A short, fast
    # budget ranks these choices just as well, so cap trees and floor the
    # learning rate here while keeping each candidate's own depth/leaves/
    # regularization — those are what actually differ between candidates.
    def _selection_budget(p: dict) -> tuple:
        lgb_n = min(int(p['lgb_estimators']), SELECTION_MAX_TREES)
        xgb_n = min(int(p['xgb_estimators']), SELECTION_MAX_TREES)
        lgb_lr = max(float(p['lgb_lr']), SELECTION_MIN_LR)
        xgb_lr = max(float(p['xgb_lr']), SELECTION_MIN_LR)
        return lgb_n, lgb_lr, xgb_n, xgb_lr
    for frac in np.linspace(0.5, 0.8, n_folds):
        cut = int(n * frac)
        val_end = min(cut + max(10, int(n * 0.1)), n)
        if cut < MIN_TRAIN_ROWS or val_end - cut < 3:
            continue
        X_fold_tr, y_fold_tr = X.iloc[:cut], np.asarray(y[:cut])
        X_fold_val, y_fold_val = X.iloc[cut:val_end], np.asarray(y[cut:val_end])
        for top_k in top_ks:
            cols = _select_important_features(X_fold_tr, y_fold_tr, top_k=top_k)
            xtr, xval = X_fold_tr[cols], X_fold_val[cols]
            weights = _peak_sample_weights(y_fold_tr)
            for name in candidates:
                p = PARAM_SETS[name]
                try:
                    _ln, _llr, _xn, _xlr = _selection_budget(p)
                    lm = lgb.LGBMRegressor(
                        objective='regression_l1', n_estimators=_ln,
                        learning_rate=_llr, max_depth=p['lgb_depth'],
                        num_leaves=p['lgb_leaves'], min_child_samples=p.get('lgb_min_child_samples', 20),
                        lambda_l1=p.get('lgb_lambda_l1', 0.8), lambda_l2=p.get('lgb_lambda_l2', 0.8),
                        feature_fraction=p.get('lgb_feature_fraction', 0.75),
                        bagging_fraction=p.get('lgb_bagging_fraction', 0.75), bagging_freq=5, n_jobs=-1, verbose=-1,
                    ).fit(xtr, y_fold_tr, sample_weight=weights)
                    xm = xgb.XGBRegressor(
                        objective='reg:absoluteerror', n_estimators=_xn,
                        learning_rate=_xlr, max_depth=p['xgb_depth'],
                        min_child_weight=p.get('xgb_min_child_weight', 1),
                        subsample=p.get('xgb_subsample', 0.75), colsample_bytree=p.get('xgb_colsample_bytree', 0.75),
                        reg_alpha=p.get('xgb_reg_alpha', 0.8), reg_lambda=p.get('xgb_reg_lambda', 0.8),
                        eval_metric='mae', verbosity=0, n_jobs=-1,
                    ).fit(xtr, y_fold_tr, sample_weight=weights)
                    records.append((name, top_k, 'lightgbm', _score_pred(y_fold_val, lm.predict(xval), thr_high, thr_med, peak_ref)))
                    records.append((name, top_k, 'xgboost', _score_pred(y_fold_val, xm.predict(xval), thr_high, thr_med, peak_ref)))
                except Exception:
                    continue
    if not records:
        return None
    scores = pd.DataFrame(records, columns=['param_set', 'top_k', 'model', 'score'])
    means = scores.groupby(['param_set', 'top_k', 'model'], as_index=False)['score'].mean()
    best = means.loc[means['score'].idxmax()]
    pair = means[(means.param_set == best.param_set) & (means.top_k == best.top_k)]
    return {
        'param_set': str(best.param_set), 'top_k': int(best.top_k),
        'winner': str(best.model), 'score': float(best.score),
        'cv_scores': dict(zip(pair.model, pair.score)),
    }


def _score_pred(y_true, y_pred, thr_high=None, thr_med=None, peak_ref=None) -> float:
    """Goodness score for picking the ensemble winner. When thr_high/thr_med/
    peak_ref are given, scores by classification ACCURACY using a FIXED
    threshold (the same one used for CalAcc during training and for the
    official TestAcc) — deliberately NOT a threshold tuned per model.

    Why fixed beats per-model-tuned here: searching ~17 threshold candidates
    on a calibration set this small (~90-110 days) and keeping whichever
    scores best is a classic multiple-comparisons trap — the "best" value
    found is biased upward by luck on that specific small sample, not a
    genuine skill signal. Selecting the winner by that inflated number picks
    whichever model got luckiest with the search, not whichever model is
    actually most accurate. A shared fixed threshold measures every model on
    the same honest yardstick, so the winner reflects real accuracy —
    confirmed in practice: this consistently outperformed the tuned-
    threshold variant on held-out test.

    Falls back to the R²/MAE-based score when thresholds aren't available
    (e.g. older callers)."""
    yt = np.asarray(y_true, dtype=float)
    pp = np.asarray(y_pred, dtype=float)
    n = min(len(yt), len(pp))
    if n <= 0:
        return float('-inf')
    yt, pp = yt[:n], pp[:n]
    if thr_high is not None and thr_med is not None and peak_ref is not None:
        try:
            cls = compute_classification_metrics(yt, pp, thr_high, thr_med, peak_ref)
            return float(cls.get('accuracy', 0.0))
        except Exception:
            pass
    r2 = r2_score(yt, pp)
    if not np.isfinite(r2) or r2 < 0.0:
        return 0.0
    mae = mean_absolute_error(yt, pp)
    return (max(r2, 0.0) + 1e-6) / (mae + 1e-6)


def _prefer_best_single_if_beats_blend(y_true, preds: dict[str, np.ndarray], weights: dict[str, float],
                                        thr_high=None, thr_med=None, peak_ref=None,
                                        cv_scores: dict | None = None) -> dict[str, float]:
    """Always trust whichever single model is most accurate — no blending,
    ever, regardless of whether a blend might score higher. 100% to the
    winner, 0% to everyone else.

    For any model named in cv_scores (LightGBM/XGBoost, when the caller ran
    _cv_select_lgb_xgb_winner), that cross-validated average accuracy is
    used instead of the single-calibration-slice score — a more reliable
    signal, since it isn't just one small sample's read. Models not in
    cv_scores (e.g. LSTM, which isn't cross-validated here) still use the
    single-calibration _score_pred as before. Either way this only ever
    looks at calibration/CV-fold data, never test."""
    available = {k: np.asarray(v, dtype=float) for k, v in preds.items() if v is not None and len(v) > 0}
    if len(available) < 2:
        return weights
    best_name, best_score = None, float('-inf')
    for name, arr in available.items():
        if cv_scores and name in cv_scores:
            s = cv_scores[name]
        else:
            s = _score_pred(y_true, arr, thr_high, thr_med, peak_ref)
        if s > best_score:
            best_name, best_score = name, s
    if best_name is None:
        return weights
    return _normalize_weights({k: (1.0 if k == best_name else 0.0) for k in weights.keys()})


def _derive_ensemble_weights(
    y_true: np.ndarray,
    preds: dict[str, np.ndarray],
    primary: str = 'lstm',
    base_prior: dict[str, float] | None = None,
    thr_high=None, thr_med=None, peak_ref=None,
    cv_scores: dict | None = None,
) -> dict[str, float]:
    weights = _derive_ensemble_weights_blend(y_true, preds, primary, base_prior)
    return _prefer_best_single_if_beats_blend(y_true, preds, weights, thr_high, thr_med, peak_ref, cv_scores)


def _derive_ensemble_weights_blend(
    y_true: np.ndarray,
    preds: dict[str, np.ndarray],
    primary: str = 'lstm',
    base_prior: dict[str, float] | None = None,
) -> dict[str, float]:
    base_prior = base_prior or {
        'lstm': LSTM_WEIGHT_PRIOR, 'lightgbm': LGB_WEIGHT_PRIOR, 'xgboost': XGB_WEIGHT_PRIOR,
    }
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
    cv_scores: dict | None = None,
    extra_train_X=None, extra_train_y=None, extra_train_weight: float = 0.3,
):
    # Make room-local copies so no branch can accidentally reuse a previous room's
    # dataframe/array object via shared reference.
    X_tr = X_tr.copy(deep=True) if isinstance(X_tr, pd.DataFrame) else np.asarray(X_tr).copy()
    X_cal = X_cal.copy(deep=True) if isinstance(X_cal, pd.DataFrame) else np.asarray(X_cal).copy()
    X_te = X_te.copy(deep=True) if isinstance(X_te, pd.DataFrame) else np.asarray(X_te).copy()
    y_tr = np.asarray(y_tr, dtype=float).copy()
    y_cal = np.asarray(y_cal, dtype=float).copy()

    peak_weights = _peak_sample_weights(y_tr)

    # Peer-room rows (see build_pooled_peer_rows) get appended to the FIT
    # data only — never to X_cal/y_cal (early stopping and calibration stay
    # pure target-room, so the recursive-calibration serving check further
    # down still measures this room alone). A reduced weight keeps this
    # room's own pattern dominant; peer rows just add generalizable
    # signal for a target with too little history of its own.
    fit_X, fit_y, fit_w = X_tr, y_tr, peak_weights
    if extra_train_X is not None and extra_train_y is not None and len(extra_train_y) > 0:
        extra_w = np.full(len(extra_train_y), extra_train_weight, dtype=float)
        if isinstance(X_tr, pd.DataFrame):
            extra_X_aligned = extra_train_X.reindex(columns=X_tr.columns, fill_value=0.0)
            fit_X = pd.concat([X_tr, extra_X_aligned], ignore_index=True)
        else:
            fit_X = np.concatenate([X_tr, np.asarray(extra_train_X)])
        fit_y = np.concatenate([y_tr, np.asarray(extra_train_y, dtype=float)])
        fit_w = np.concatenate([peak_weights, extra_w])
    # Huber loss (robust=True) routing switched from CV(y_tr) to zero-day
    # fraction of y_tr, after A/B testing both ways it applied:
    #   2C09   (46% of days nonzero — frequent real usage): Huber HURT it
    #           badly (R² 0.526→0.953, MAE 2.11h→0.52h when forced off).
    #   4C05   (30% nonzero): same story, Huber hurt (R² 0.805→0.960).
    #   1C-MEETING (only 15% of days nonzero — booked almost never): Huber
    #           HELPED (R² 0.776→-2.329, TestAcc 100%→88.7% when forced off).
    # Huber dampens the gradient from large-residual points — correct when
    # those points are genuinely rare noise (1C-MEETING), wrong when they're
    # a frequent recurring pattern the peak-weighting fix is trying to teach
    # the model to hit (2C09/4C05). >80% zero-days is the dividing line
    # between those two cases in the data surveyed. Decided from y_tr only.
    zero_frac = float(np.mean(y_tr <= 1e-9)) if len(y_tr) else 0.0
    use_robust = zero_frac > 0.80
    lgb_model, lgb_history = train_lgb(fit_X, fit_y, X_cal, y_cal, robust=use_robust, sample_weight=fit_w)
    xgb_model, xgb_history = train_xgb(fit_X, fit_y, X_cal, y_cal, robust=use_robust, sample_weight=fit_w)

    # Per-room hurdle selection. Zero-inflated rooms are better served by a
    # gate + positive-part pair than by one regressor straddling both modes,
    # but not every room: a survey of the eight rooms showed hurdle cutting
    # MAE in six while clearly hurting 2C09 and 1C-MEETING. So fit the
    # variants and keep one only if it beats the plain regressor on
    # CALIBRATION accuracy — X_te is never consulted here.
    hurdle_choice = {'lightgbm': 'single', 'xgboost': 'single'}
    if thr_high is not None and thr_med is not None and peak_ref is not None:
        for _mt, _base in (('lightgbm', lgb_model), ('xgboost', xgb_model)):
            _base_acc = compute_classification_metrics(
                y_cal, _predict_booster(_base, X_cal, _mt), thr_high, thr_med, peak_ref)['accuracy']
            _best, _best_acc, _best_mode = None, _base_acc, 'single'
            # One fit, both combination rules — with_mode() reuses the same
            # trained gate and positive-part model.
            _fitted = train_hurdle(_mt, fit_X, fit_y, X_cal, y_cal, mode='hard',
                                   robust=use_robust, sample_weight=fit_w)
            for _mode in (('hard', 'soft') if _fitted is not None else ()):
                _cand = _fitted.with_mode(_mode)
                _acc = compute_classification_metrics(
                    np.asarray(y_cal, dtype=float),
                    np.asarray(_cand.predict(X_cal), dtype=float),
                    thr_high, thr_med, peak_ref)['accuracy']
                if _acc > _best_acc:
                    _best, _best_acc, _best_mode = _cand, _acc, _mode
            if _best is not None:
                hurdle_choice[_mt] = _best_mode
                print(f"    🚪 {_mt}: hurdle '{_best_mode}' beats single on calibration "
                      f"({_base_acc:.4f} -> {_best_acc:.4f}) — using it")
                if _mt == 'lightgbm':
                    lgb_model = _best
                else:
                    xgb_model = _best

    if thr_high is not None and thr_med is not None and peak_ref is not None:
        lgb_history, xgb_history = _attach_booster_accuracy_history(
            lgb_model, xgb_model,
            X_tr, y_tr, X_cal, y_cal,
            thr_high, thr_med, peak_ref,
            lgb_history=lgb_history,
            xgb_history=xgb_history,
        )
        lgb_train_preds = _predict_booster(lgb_model, X_tr, 'lightgbm')
        lgb_val_preds = _predict_booster(lgb_model, X_cal, 'lightgbm')
        xgb_train_preds = _predict_booster(xgb_model, X_tr, 'xgboost')
        xgb_val_preds = _predict_booster(xgb_model, X_cal, 'xgboost')
        lgb_train_cls = compute_classification_metrics(y_tr, lgb_train_preds, thr_high, thr_med, peak_ref)
        lgb_val_cls = compute_classification_metrics(y_cal, lgb_val_preds, thr_high, thr_med, peak_ref)
        xgb_train_cls = compute_classification_metrics(y_tr, xgb_train_preds, thr_high, thr_med, peak_ref)
        xgb_val_cls = compute_classification_metrics(y_cal, xgb_val_preds, thr_high, thr_med, peak_ref)
        print(
            f"    🟢 LightGBM training: best round={lgb_history.get('best_round', 'all')} "
            f"CalLoss={lgb_history.get('best_valid_loss', lgb_history.get('valid_loss', [np.nan])[-1]):.4f} "
            f"TrainAcc={lgb_train_cls['accuracy']:.4f} CalAcc={lgb_val_cls['accuracy']:.4f}"
        )
        print(
            f"    ⚡ XGBoost training: best round={xgb_history.get('best_round', 'all')} "
            f"CalLoss={xgb_history.get('best_valid_loss', xgb_history.get('valid_loss', [np.nan])[-1]):.4f} "
            f"TrainAcc={xgb_train_cls['accuracy']:.4f} CalAcc={xgb_val_cls['accuracy']:.4f}"
        )
    else:
        print("    🟢 LightGBM/XGBoost training: train/valid thresholds unavailable, showing loss history only")

    lgb_val = _predict_booster(lgb_model, X_cal, 'lightgbm')
    xgb_val = _predict_booster(xgb_model, X_cal, 'xgboost')
    lgb_train_preds = _predict_booster(lgb_model, X_tr, 'lightgbm')
    xgb_train_preds = _predict_booster(xgb_model, X_tr, 'xgboost')
    lgb_fut = _predict_booster(lgb_model, X_te, 'lightgbm')
    xgb_fut = _predict_booster(xgb_model, X_te, 'xgboost')

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
        # Tree models are the default serving path. LSTM is eligible only if
        # its chronological validation forecast beats both the best tree and
        # seasonal-naive(7) on the same calibration dates.
        tree_preds = {'lightgbm': lgb_val, 'xgboost': xgb_val}
        tree_scores = {
            name: _score_pred(y_cal, pred, thr_high, thr_med, peak_ref)
            for name, pred in tree_preds.items()
        }
        tree_winner = max(tree_scores, key=tree_scores.get)
        tree_score = tree_scores[tree_winner]
        seasonal_pred = (
            X_cal['lag_7'].to_numpy(dtype=float)
            if isinstance(X_cal, pd.DataFrame) and 'lag_7' in X_cal.columns else None
        )
        seasonal_score = (
            _score_pred(y_cal, seasonal_pred, thr_high, thr_med, peak_ref)
            if seasonal_pred is not None else float('inf')
        )
        lstm_score = _score_pred(y_cal, lstm_val_preds, thr_high, thr_med, peak_ref)
        lstm_selected = lstm_score > tree_score and lstm_score > seasonal_score

        if lstm_selected:
            print(f"    🧠 LSTM accepted: CalAcc={lstm_score:.3f} > "
                  f"{tree_winner.upper()}={tree_score:.3f}, SNaive-7={seasonal_score:.3f}")
            ensemble_weights = {'lstm': 1.0, 'lightgbm': 0.0, 'xgboost': 0.0}
            final, meta_val = lstm_fut_preds, lstm_val_preds
        else:
            print(f"    🌳 Tree-first: LSTM CalAcc={lstm_score:.3f}; "
                  f"{tree_winner.upper()}={tree_score:.3f}; SNaive-7={seasonal_score:.3f}")
            ensemble_weights = _derive_ensemble_weights(
                y_cal, tree_preds, primary=tree_winner,
                base_prior={'lightgbm': 0.50, 'xgboost': 0.50},
                thr_high=thr_high, thr_med=thr_med, peak_ref=peak_ref,
                cv_scores=cv_scores,
            )
            final = _blend_predictions({'lightgbm': lgb_fut, 'xgboost': xgb_fut}, ensemble_weights)
            meta_val = _blend_predictions(tree_preds, ensemble_weights)
    else:
        print("⚠️  LSTM ไม่พร้อม – ensemble ใช้ LGB + XGB")
        ensemble_weights = _derive_ensemble_weights(
            y_cal,
            {'lightgbm': lgb_val, 'xgboost': xgb_val},
            primary='lightgbm',
            base_prior={'lightgbm': 0.50, 'xgboost': 0.50},
            thr_high=thr_high, thr_med=thr_med, peak_ref=peak_ref,
            cv_scores=cv_scores,
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
    serving_model: str = 'ensemble',
    peer_profile=None,
    serving_weights=None,
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
            feat_hist = build_features(history, term_df=term_df, use_log=use_log,
                                        peer_profile=peer_profile).dropna()
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
        f_df = build_features(extended, term_df, use_log=use_log, peer_profile=peer_profile)\
            .loc[[fc_ts]].drop(columns='y')
        lgb_pred = float(_predict_booster(lgb_model, f_df, 'lightgbm')[0])
        xgb_pred = float(_predict_booster(xgb_model, f_df, 'xgboost')[0])

        if serving_model == 'lightgbm':
            d_pred = lgb_pred
        elif serving_model == 'xgboost':
            d_pred = xgb_pred
        elif serving_model == 'blend':
            w = serving_weights or {'lightgbm': 0.5, 'xgboost': 0.5}
            d_pred = w.get('lightgbm', 0.5) * lgb_pred + w.get('xgboost', 0.5) * xgb_pred
        elif fc_date in lstm_daily_preds:
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


def _evaluate_model_preds(y_true, preds_dict, thr_high, thr_med, peak_ref, room_name,
                           cal_preds_dict=None, y_cal=None, verbose: bool = True):
    """Score each model's TEST predictions against y_true, using the SAME
    fixed threshold as CalAcc (the ensemble-selection criterion) and TestAcc
    (the official reported number) — no per-model threshold search here.
    Previously this searched a threshold multiplier per model from
    calibration data; that number wasn't comparable to CalAcc/TestAcc (which
    both use the plain fixed threshold) and repeatedly caused confusion about
    why the "winner" didn't have the highest number in this block. Now all
    three (CalAcc, this block, TestAcc) use one consistent yardstick.
    cal_preds_dict/y_cal are accepted for call-site compatibility but no
    longer used. verbose=False suppresses the per-model TEST print lines
    (still computes and returns the metrics — only the console output changes)
    for callers that want a training-only console (see train_from_excel.py).
    """
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

        cls = compute_classification_metrics(y_true, mp, thr_high, thr_med, peak_ref)
        reg = {
            'r2': round(r2, 4), 'mae': round(mae, 4),
            'rmse': round(rmse(y_true, mp), 4), 'smape': round(smape(y_true, mp), 4),
        }
        model_metrics[mname] = {'regression': reg, 'classification': cls}
        if verbose:
            print(
                f"  📊 {mname.upper():10s}: Accuracy={cls['accuracy']*100:5.1f}% "
                f"| Loss={cls['loss']:.4f} | R²={r2:.4f} | MAE={mae:.4f}"
            )
    return model_metrics


def expand_bookings_to_daily(rdf: pd.DataFrame, daily_cap: float = 12.0) -> pd.DataFrame:
    """Expand bookings into one row per calendar day, measuring each day's
    OCCUPIED time as the union of the bookings covering it, clipped to the
    room's operating window.

    Two bugs used to inflate busy days to physically impossible totals:

    1. Overlap was measured against the calendar day (00:00-24:00), so the
       middle day of a multi-day block (e.g. exam week, Mon 08:00 ->
       next-Tue 20:00) scored a full 24h. The room is not occupied
       overnight — only ROOM_OPEN_HOUR..ROOM_CLOSE_HOUR counts.
    2. Concurrent bookings were summed, not unioned. Two exam-week records
       covering the same days each contributed `daily_cap` hours, so the
       day totalled 24h in a room that is open 12h.

    Combined, that produced daily values up to 24.0h on 16-60 days per
    room. Those days sat at the top of the distribution, so they set
    peak_ref (the 0.95 quantile) and therefore both label thresholds —
    corrupting the labels, not just a few outlier rows. The rooms hit
    hardest were the busiest ones, which is why they scored worst.

    `daily_cap` is kept as a final clamp for rooms whose real window is
    wider than the constants below.

    Requires 'start_time' and 'end_time' columns. Returns a DataFrame with
    columns ['date', 'duration'] — one row per day touched.
    """
    per_day: dict = {}
    for start, end in zip(rdf['start_time'], rdf['end_time']):
        start = pd.Timestamp(start)
        end = pd.Timestamp(end)
        if end <= start:
            continue
        cur = start.normalize()
        last = end.normalize()
        while cur <= last:
            win_start = cur + pd.Timedelta(hours=ROOM_OPEN_HOUR)
            win_end = cur + pd.Timedelta(hours=ROOM_CLOSE_HOUR)
            ov_start = max(start, win_start)
            ov_end = min(end, win_end)
            if ov_end > ov_start:
                per_day.setdefault(cur.date(), []).append((ov_start, ov_end))
            cur = cur + pd.Timedelta(days=1)

    rows_date, rows_hours = [], []
    for day, intervals in per_day.items():
        intervals.sort()
        merged = [list(intervals[0])]
        for iv_start, iv_end in intervals[1:]:
            if iv_start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], iv_end)
            else:
                merged.append([iv_start, iv_end])
        hours = sum((b - a).total_seconds() / 3600.0 for a, b in merged)
        rows_date.append(day)
        rows_hours.append(min(hours, daily_cap))
    return pd.DataFrame({'date': rows_date, 'duration': rows_hours})


def _prepare_daily_series(rdf, room, all_rooms_daily):
    """Build the room's REAL daily series only. Returns None when the room has
    no booking history at all — callers must skip training for that room
    rather than fabricate one (no synthetic augmentation, no borrowing
    another room's series). ``all_rooms_daily`` is accepted for call-site
    compatibility but no longer used."""
    if len(rdf) == 0:
        return None
    expanded = expand_bookings_to_daily(rdf)
    if len(expanded) == 0:
        return None
    daily = (
        expanded.groupby('date')['duration'].sum()
           .reindex(pd.date_range(expanded['date'].min(), expanded['date'].max(), freq='D').date,
                    fill_value=0.0)
           .astype(float)
    )
    daily.index = pd.to_datetime(daily.index)
    return daily


def recursive_snaive_predictions(daily, start_idx, end_idx, use_log=False,
                                  refresh_every=FORECAST_DAYS):
    """Seasonal-naive(7) forecast under the identical recursive,
    refresh-every-N-days protocol as recursive_tree_predictions, so the two
    are directly comparable on calibration and can gate which one serves.

    Returns predictions in the same space recursive_tree_predictions returns
    (log1p space when use_log, actual scale otherwise) so both can be scored
    against y_cal with the same _score_pred call.
    """
    preds = []
    step = max(1, int(refresh_every))
    for origin in range(start_idx, end_idx, step):
        history = daily.iloc[:origin].copy()
        for forecast_date in daily.index[origin:min(origin + step, end_idx)]:
            lag_date = forecast_date - pd.Timedelta(days=7)
            if lag_date in history.index:
                actual_scale_pred = float(history.loc[lag_date])
            elif len(history):
                actual_scale_pred = float(history.iloc[-1])
            else:
                actual_scale_pred = 0.0
            actual_scale_pred = max(0.0, actual_scale_pred)
            history.loc[forecast_date] = actual_scale_pred
            preds.append(np.log1p(actual_scale_pred) if use_log else actual_scale_pred)
    return np.asarray(preds, dtype=float)


def build_committed_block_index(bookings_df):
    """Map each calendar day to the multi-day blocks covering it.

    Returns {date -> [(start_date, hours_that_day), ...]} so a forecast can
    ask what was already committed and running at its origin.

    Ported from direct_forecast, where it measurably helps: 1.9% of bookings
    span more than one day yet carry 26-75% of every room's hours, and on the
    test split every day covered by an already-running block was 'urgent'.
    Trees never split on it because it is too rare, so it is applied as a
    floor on the prediction rather than fed in as a feature.
    """
    index: dict = {}
    if bookings_df is None or len(bookings_df) == 0:
        return index
    cols = set(getattr(bookings_df, 'columns', []))
    if not {'start_time', 'end_time'}.issubset(cols):
        return index
    starts = pd.to_datetime(bookings_df['start_time'], errors='coerce')
    ends = pd.to_datetime(bookings_df['end_time'], errors='coerce')
    for start, end in zip(starts, ends):
        if pd.isna(start) or pd.isna(end) or end <= start:
            continue
        if start.normalize() == end.normalize():
            continue          # single-day booking: nothing is "already running"
        cur = start.normalize()
        last = end.normalize()
        while cur <= last:
            win_s = max(start, cur + pd.Timedelta(hours=ROOM_OPEN_HOUR))
            win_e = min(end, cur + pd.Timedelta(hours=ROOM_CLOSE_HOUR))
            hours = (win_e - win_s).total_seconds() / 3600.0
            if hours > 0:
                index.setdefault(cur.normalize(), []).append(
                    (start.normalize(), min(hours, 12.0)))
            cur = cur + pd.Timedelta(days=1)
    return index


def committed_block_floor(block_index, known_as_of, target_date) -> float:
    """Hours on `target_date` committed by blocks that had already STARTED by
    `known_as_of`. Blocks beginning later are invisible to a forecast made at
    that origin, so they are excluded — this is what keeps the floor honest
    inside a 14-day horizon."""
    if not block_index:
        return 0.0
    entries = block_index.get(pd.Timestamp(target_date).normalize())
    if not entries:
        return 0.0
    cutoff = pd.Timestamp(known_as_of).normalize()
    hours = sum(h for start, h in entries if start <= cutoff)
    return float(min(hours, 12.0))


def recursive_tree_predictions(model, daily, term_df, booking_ahead_df, start_idx,
                               end_idx, feature_names, model_type, use_log=False,
                               refresh_every=FORECAST_DAYS, peer_profile=None):
    """Backtest the same fixed forecast horizon used by the application.

    Within each horizon, lag/rolling features contain only earlier forecasts.
    At the next origin, the observed history is available again, as it is when
    the scheduled forecast job runs.  A single 229-day recursive rollout does
    not represent this application's 14-day serving behaviour.
    """
    preds = []
    step = max(1, int(refresh_every))
    block_index = build_committed_block_index(booking_ahead_df)
    for origin in range(start_idx, end_idx, step):
        history = daily.iloc[:origin].copy()
        known_as_of = daily.index[origin - 1] if origin > 0 else daily.index[0]
        for forecast_date in daily.index[origin:min(origin + step, end_idx)]:
            extended = pd.concat([history, pd.Series([np.nan], index=[forecast_date])])
            row = build_features(
                extended, term_df=term_df, use_log=use_log,
                booking_ahead_df=booking_ahead_df, peer_profile=peer_profile,
            ).loc[[forecast_date]].drop(columns='y')
            row = row.reindex(columns=list(feature_names), fill_value=0.0)
            raw_pred = max(0.0, float(_predict_booster(model, row, model_type)[0]))
            actual_scale_pred = float(np.expm1(raw_pred)) if use_log else raw_pred
            # Hours already committed by a block running at this origin are a
            # fact, not something to predict, so they act as a lower bound.
            floor_hours = committed_block_floor(block_index, known_as_of, forecast_date)
            if floor_hours > actual_scale_pred:
                actual_scale_pred = floor_hours
                raw_pred = float(np.log1p(floor_hours)) if use_log else floor_hours
            history.loc[forecast_date] = max(0.0, actual_scale_pred)
            preds.append(raw_pred)
    return np.asarray(preds, dtype=float)


def recursive_blend_predictions(lgb_model, xgb_model, weights, daily, term_df,
                                 booking_ahead_df, start_idx, end_idx, feature_names,
                                 use_log=False, refresh_every=FORECAST_DAYS, peer_profile=None):
    """Same recursive, refresh-every-N-days protocol as recursive_tree_predictions,
    but each step blends LightGBM + XGBoost (weights = {'lightgbm': w, 'xgboost': w})
    into the single value that then feeds next-step lag/rolling features — matching
    how a 'blend' serving_model actually generates history at run time, rather than
    two single-model rollouts averaged after the fact.
    """
    preds = []
    step = max(1, int(refresh_every))
    w_lgb = weights.get('lightgbm', 0.5)
    w_xgb = weights.get('xgboost', 0.5)
    block_index = build_committed_block_index(booking_ahead_df)
    for origin in range(start_idx, end_idx, step):
        history = daily.iloc[:origin].copy()
        known_as_of = daily.index[origin - 1] if origin > 0 else daily.index[0]
        for forecast_date in daily.index[origin:min(origin + step, end_idx)]:
            extended = pd.concat([history, pd.Series([np.nan], index=[forecast_date])])
            row = build_features(
                extended, term_df=term_df, use_log=use_log,
                booking_ahead_df=booking_ahead_df, peer_profile=peer_profile,
            ).loc[[forecast_date]].drop(columns='y')
            row = row.reindex(columns=list(feature_names), fill_value=0.0)
            lgb_pred = float(_predict_booster(lgb_model, row, 'lightgbm')[0])
            xgb_pred = float(_predict_booster(xgb_model, row, 'xgboost')[0])
            raw_pred = max(0.0, w_lgb * lgb_pred + w_xgb * xgb_pred)
            actual_scale_pred = float(np.expm1(raw_pred)) if use_log else raw_pred
            floor_hours = committed_block_floor(block_index, known_as_of, forecast_date)
            if floor_hours > actual_scale_pred:
                actual_scale_pred = floor_hours
                raw_pred = float(np.log1p(floor_hours)) if use_log else floor_hours
            history.loc[forecast_date] = max(0.0, actual_scale_pred)
            preds.append(raw_pred)
    return np.asarray(preds, dtype=float)


def _cv_select_serving_model(X, y, daily, term_df, rdf, feature_names, use_log,
                              thr_high, thr_med, peak_ref, peer_profile,
                              train_end, calib_end, recursive_cal_scores, n_folds: int = 2):
    """Multi-fold walk-forward version of the recursive-calibration serving
    check. A single calibration slice (recursive_cal_scores, computed on the
    real train_end..calib_end window with the FINAL trained models) has
    repeatedly disagreed with held-out test in practice — e.g. 2C05-06 once
    picked xgboost on that slice (0.596 vs 0.578) but lightgbm was the one
    that actually generalized. Averaging that real fold with extra synthetic
    folds carved out of the training window (fresh LGB/XGB refit on data
    before each fold's cut, backtested recursively on the held-out tail
    after it — the exact 14-day-refresh rollout the app runs in production)
    is a less noisy estimate of which tree generalizes better.

    Returns (serving_model, avg_scores, fold_scores) — fold_scores[0] is
    always the real calibration fold; the rest are synthetic, in order.
    """
    fold_scores = [dict(recursive_cal_scores)]
    fold_len = max(5, calib_end - train_end)
    for frac in np.linspace(0.5, 0.8, n_folds):
        cut = int(train_end * frac)
        hold_end = min(cut + fold_len, train_end)
        if cut < MIN_TRAIN_ROWS or hold_end - cut < 5:
            continue
        X_fold_tr, y_fold_tr = X.iloc[:cut], y[:cut]
        X_fold_hold, y_fold_hold = X.iloc[cut:hold_end], y[cut:hold_end]
        try:
            fold_lgb, _ = train_lgb(X_fold_tr, y_fold_tr, X_fold_hold, y_fold_hold)
            fold_xgb, _ = train_xgb(X_fold_tr, y_fold_tr, X_fold_hold, y_fold_hold)
        except Exception:
            continue
        lgb_roll = recursive_tree_predictions(
            fold_lgb, daily, term_df, rdf, cut, hold_end, feature_names, 'lightgbm',
            use_log, peer_profile=peer_profile)
        xgb_roll = recursive_tree_predictions(
            fold_xgb, daily, term_df, rdf, cut, hold_end, feature_names, 'xgboost',
            use_log, peer_profile=peer_profile)
        fold_scores.append({
            'lightgbm': _score_pred(y_fold_hold, lgb_roll, thr_high, thr_med, peak_ref),
            'xgboost':  _score_pred(y_fold_hold, xgb_roll, thr_high, thr_med, peak_ref),
        })
    avg_scores = {
        name: float(np.mean([f[name] for f in fold_scores]))
        for name in ('lightgbm', 'xgboost')
    }
    serving_model = max(avg_scores, key=avg_scores.get)
    return serving_model, avg_scores, fold_scores


def _train_room_pipeline(room, daily, rdf, schedule, verbose: bool = True, all_rooms_daily=None):
    """
    Tree-first path:
      LightGBM/XGBoost → optional LSTM only when it clears both validation gates

    verbose=False suppresses only the TEST-evaluation console output (the
    "ENSEMBLE –" header, the Classification Metrics block, and the per-model
    ENSEMBLE/LIGHTGBM/XGBOOST/LSTM lines) — everything computed and returned
    is unchanged, and training-time console output (LSTM/CV/feature-selection
    progress, CalAcc) still prints either way, since that reflects DECISIONS
    made during training, not a peek at test results.
    """
    global TREE_PARAMS_OVERRIDE
    # Establish the chronological split BEFORE fitting any distribution-derived
    # preprocessing.  cap95/thresholds must never inspect calibration or test.
    split_probe = _split_time_series(pd.DataFrame(index=daily.index), daily.to_numpy(dtype=float))
    if split_probe is None:
        print(f"   ⚠️  {room.name}: ข้อมูลไม่พอสำหรับ train (rows={len(daily)})")
        return None
    train_end_probe = split_probe[-2]

    use_log = _needs_log_transform(room)
    cap95 = float(daily.iloc[:train_end_probe].quantile(0.95)) or 1.0
    daily = daily.clip(upper=cap95)

    term_df = build_term_daily_features(daily.index, schedule)
    term_df.index = daily.index
    # cutoff = this room's own train_end date — peer_profile is fit only on
    # peer history strictly before it (see fit_peer_profile's docstring).
    peer_profile = fit_peer_profile(room, all_rooms_daily, cutoff_date=daily.index[train_end_probe])
    feat_df = build_features(daily, term_df, use_log=use_log, booking_ahead_df=rdf,
                              peer_profile=peer_profile).dropna()
    X = feat_df.drop(columns='y')
    y = feat_df['y'].values

    split = _split_time_series(X, y)
    if split is None:
        print(f"   ⚠️  {room.name}: ข้อมูลไม่พอสำหรับ train (rows={len(X)})")
        return None

    X_tr, X_cal, X_te, y_tr, y_cal, y_te, train_end, calib_end = split

    # Fixed classification thresholds come from training data only and are
    # shared by all CV candidates.
    fit_daily = daily.iloc[:train_end]
    peak_ref = float(fit_daily.quantile(0.95)) or 1.0
    thr_high, thr_med = compute_adaptive_thresholds(fit_daily, peak_ref)

    # Each parameter set keeps its own tree hyperparameters. It uses the same
    # chronological folds only to select feature count and LGB/XGB within that
    # set, so an A run can never select E's parameters.
    tree_selection = None
    feature_top_k = 30
    if CURRENT_PARAM_SET in PARAM_SETS:
        X_cv_raw = pd.concat([X_tr, X_cal])
        y_cv_raw = np.concatenate([y_tr, y_cal])
        tree_selection = _cv_select_tree_config(
            X_cv_raw, y_cv_raw, thr_high, thr_med, peak_ref,
            candidates=((CURRENT_PARAM_SET, 'A_REG') if CURRENT_PARAM_SET == 'A'
                        else (CURRENT_PARAM_SET,)),
        )
        if tree_selection is not None:
            TREE_PARAMS_OVERRIDE = PARAM_SETS[tree_selection['param_set']]
            feature_top_k = tree_selection['top_k']
            print(f"   🎛️  Walk-forward selection: set={tree_selection['param_set']} "
                  f"top_k={feature_top_k} winner={tree_selection['winner'].upper()} "
                  f"CV Acc={tree_selection['score']:.3f}")
        else:
            TREE_PARAMS_OVERRIDE = None
    else:
        TREE_PARAMS_OVERRIDE = None

    # Trim to the most useful features (ranked on TRAIN only) before doing
    # anything else — reduces the feature:row ratio so LSTM/LGB/XGB spend
    # their limited data on real signal instead of noisy columns. See
    # _select_important_features docstring.
    selected_features = _select_important_features(X_tr, y_tr, top_k=feature_top_k)
    if len(selected_features) < X.shape[1]:
        print(f"   ✂️  Feature selection: {X.shape[1]} → {len(selected_features)} features kept")
        feat_df = feat_df[selected_features + ['y']]
        X = feat_df.drop(columns='y')
        y = feat_df['y'].values
        X_tr, X_cal, X_te = X.iloc[:train_end], X.iloc[train_end:calib_end], X.iloc[calib_end:]

    room_hour_dist = learn_hour_dist(rdf, room_id=room.id) if len(rdf) > 0 else HOUR_DIST_FALLBACK

    lstm_model, lstm_scaler, lstm_history = None, None, None
    if SKIP_LSTM:
        print(f"   ⏭️  [1/3] LSTM skipped (SKIP_LSTM=True — see LSTM_EXCLUSION_NOTE: it has "
              f"never cleared the tree-first serving gate, so training it here would not "
              f"change what serves)")
    elif LSTM_AVAILABLE and len(y_tr) >= LSTM_LOOKBACK + 10:
        print(f"   🧠 [1/3] LSTM (optional challenger) – {room.name}{' (log-transformed)' if use_log else ''}")
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

    print(f"   🌿 [2/3] LightGBM (primary tree)")
    print(f"   ⚡ [3/3] XGBoost (primary tree)")

    # Cross-validated LGB-vs-XGB comparison for the SELECTION decision only —
    # walk-forward folds within X_tr+X_cal (never X_te). See
    # _cv_select_lgb_xgb_winner's docstring: a single ~90-110 day calibration
    # slice is a noisy point estimate of which model generalizes better;
    # averaging several folds is far less likely to be fooled by one
    # unrepresentative sample.
    X_cv = pd.concat([X_tr, X_cal]) if isinstance(X_tr, pd.DataFrame) else np.concatenate([X_tr, X_cal])
    y_cv = np.concatenate([y_tr, y_cal])
    cv_scores = (tree_selection['cv_scores'] if tree_selection is not None
                 else _cv_select_lgb_xgb_winner(X_cv, y_cv, thr_high, thr_med, peak_ref))
    if cv_scores:
        cv_winner = max(cv_scores, key=cv_scores.get)
        print(
            f"   👑 SELECTION (decided here, on train+calibration only — test is never looked at): "
            f"LGB={cv_scores.get('lightgbm', 0):.3f}  XGB={cv_scores.get('xgboost', 0):.3f}  "
            f"→ picking {cv_winner.upper()}"
        )
        print(
            "      (the ENSEMBLE/LIGHTGBM/XGBOOST/LSTM block further below just REPORTS how that "
            "already-made choice did on test — it does not influence the pick above)"
        )

    # Real transfer learning for data-poor rooms: append peer rooms' OWN
    # feature rows (build_pooled_peer_rows) to the training fit, at a
    # reduced weight, when this room's own training history is short enough
    # that the tree is likely starved of pattern to learn from alone. Rooms
    # with enough of their own history skip this — diluting an
    # already-sufficient signal with lower-weighted peer rows has no
    # upside and some risk. X_cal/y_cal (used for early stopping AND every
    # later serving decision) never include peer rows.
    peer_train_X, peer_train_y = None, None
    if all_rooms_daily and len(y_tr) < PEER_AUGMENT_MAX_TRAIN_ROWS:
        peer_train_X, peer_train_y = build_pooled_peer_rows(
            room, all_rooms_daily, cutoff_date=daily.index[train_end],
            use_log=use_log, feature_columns=list(X_tr.columns),
        )
        if peer_train_X is not None:
            print(f"   🧬 Peer training rows: +{len(peer_train_y)} rows borrowed from "
                  f"same-type rooms (weight={PEER_AUGMENT_WEIGHT}, own train rows={len(y_tr)})")

    (y_pred_ens, lgb_model, xgb_model, ensemble_weights,
     lgb_history, xgb_history, lgb_val, xgb_val, lstm_val, meta_val) = stacking_predict(
        X_tr, y_tr, X_cal, y_cal, X_te,
        lstm_model=lstm_model, lstm_scaler=lstm_scaler,
        daily_hist_raw=np.concatenate([y_tr, y_cal]), n_pred=len(X_te),
        lstm_lookback=LSTM_LOOKBACK,
        thr_high=thr_high, thr_med=thr_med, peak_ref=peak_ref,
        cv_scores=cv_scores,
        extra_train_X=peer_train_X, extra_train_y=peer_train_y,
        extra_train_weight=PEER_AUGMENT_WEIGHT,
    )

    # Choose only between the trained tree models with a recursive calibration
    # forecast. Baselines remain separate benchmark scripts.
    feature_names = list(X_tr.columns)
    recursive_cal_preds = {
        'lightgbm': recursive_tree_predictions(
            lgb_model, daily, term_df, rdf, train_end, calib_end, feature_names, 'lightgbm', use_log,
            peer_profile=peer_profile),
        'xgboost': recursive_tree_predictions(
            xgb_model, daily, term_df, rdf, train_end, calib_end, feature_names, 'xgboost', use_log,
            peer_profile=peer_profile),
    }
    recursive_cal_scores = {
        name: _score_pred(y_cal, pred, thr_high, thr_med, peak_ref)
        for name, pred in recursive_cal_preds.items()
    }

    # Blend (LGB+XGB weighted by recursive-calibration score) was tried as a
    # third serving_model candidate here and measured WORSE on held-out test
    # for 2C05-06 (TestAcc 0.633 vs 0.655 for the plain single-model winner)
    # despite winning on the calibration slice — the same calibration/test
    # mismatch that motivated fit_peer_profile's leak-safety cutoff and,
    # below, _cv_select_serving_model. Blend stays reverted to a straight
    # two-way competition; recursive_blend_predictions() is left defined but
    # unused in case a later room/config wants to retry it.
    serving_weights = {'lightgbm': 0.5, 'xgboost': 0.5}

    # _cv_select_serving_model (multi-fold recursive CV, still defined above)
    # was also tried here in place of the plain single-slice pick below, and
    # also measured WORSE on 2C05-06's held-out test (0.629 vs 0.655) — its
    # own fold-averaged scores (lightgbm=0.618 xgboost=0.621) were within
    # 0.003 of each other, i.e. a coin flip, not a confident read. Chasing a
    # selection method that happens to match one room's test score through
    # repeated retries would itself become a form of test-set leakage, so
    # this was reverted to the plain single-slice pick rather than kept on
    # the strength of one lucky/unlucky room. _cv_select_serving_model is
    # left defined in case a future room has enough data for its extra
    # in-train folds to actually add signal instead of just noise.
    serving_model = max(recursive_cal_scores, key=recursive_cal_scores.get)
    # Seasonal-naive(7) under the same recursive protocol — diagnostic
    # comparison only (printed for visibility), never a serving candidate.
    # Baselines stay in their own benchmark scripts; production serving
    # picks only between the trained tree models (and their blend) above.
    recursive_snaive_score = _score_pred(
        y_cal, recursive_snaive_predictions(daily, train_end, calib_end, use_log),
        thr_high, thr_med, peak_ref,
    )
    print(
        "   🧪 Recursive calibration: "
        + "  ".join(f"{name}={score:.3f}" for name, score in recursive_cal_scores.items())
        + f"  snaive7={recursive_snaive_score:.3f} (diagnostic only)"
        + f"  → serving {serving_model}"
    )

    lgb_test = _predict_booster(lgb_model, X_te, 'lightgbm')
    xgb_test = _predict_booster(xgb_model, X_te, 'xgboost')
    lstm_cal, lstm_test = _collect_lstm_holdout_preds(
        lstm_model, lstm_scaler, feat_df, y_tr, y_cal, y_te, train_end,
    )

    # y_cal_eval (real-units calibration target) is needed regardless of whether
    # LSTM passes its gate below — used later to pick classification thresholds
    # from calibration data only, never from test.
    if use_log:
        y_cal_eval = np.expm1(y_cal)
    else:
        y_cal_eval = np.asarray(y_cal, dtype=float)
    y_cal_eval = np.nan_to_num(y_cal_eval, nan=0.0, posinf=0.0, neginf=0.0)

    lstm_gate_pass = False
    lstm_cal_r2 = float('-inf')
    lstm_cal_mae = float('inf')
    lstm_cal_eval = None
    lstm_history_saved = lstm_history  # Save history before potentially clearing it
    if lstm_model is not None and lstm_cal is not None:
        lstm_cal_eval = np.asarray(lstm_cal, dtype=float)
        if use_log:
            lstm_cal_eval = np.expm1(lstm_cal_eval)
        lstm_cal_eval = np.nan_to_num(lstm_cal_eval, nan=0.0, posinf=0.0, neginf=0.0)
        if len(y_cal_eval) > 0 and len(lstm_cal_eval) == len(y_cal_eval):
            try:
                lstm_cal_r2 = float(r2_score(y_cal_eval, lstm_cal_eval))
                lstm_cal_mae = float(mean_absolute_error(y_cal_eval, lstm_cal_eval))
                lstm_gate_pass = np.isfinite(lstm_cal_r2) and lstm_cal_r2 >= LSTM_R2_MIN_WEIGHT
            except Exception:
                lstm_gate_pass = False

    if ensemble_weights.get('lstm', 0.0) <= 0.0:
        # Tree-first policy rejected LSTM on the calibration comparison.
        # Do not keep an unused LSTM in the serving artifact; retain history
        # for diagnostic plots only.
        lstm_model = None
        lstm_scaler = None
        lstm_eval = None
        lstm_cal_eval = None

    if use_log:
        y_te_eval = np.expm1(y_te)
        y_pred_eval = np.expm1(np.maximum(0, y_pred_ens))
        lgb_eval = np.expm1(lgb_test)
        xgb_eval = np.expm1(xgb_test)
        lstm_eval = np.expm1(lstm_test) if lstm_test is not None else None
        lgb_cal_eval = np.expm1(np.asarray(lgb_val, dtype=float)) if lgb_val is not None else None
        xgb_cal_eval = np.expm1(np.asarray(xgb_val, dtype=float)) if xgb_val is not None else None
        ens_cal_eval = np.expm1(np.maximum(0, np.asarray(meta_val, dtype=float))) if meta_val is not None else None
    else:
        y_te_eval = y_te.copy()
        y_pred_eval = np.maximum(0, y_pred_ens)
        lgb_eval, xgb_eval = lgb_test, xgb_test
        lstm_eval = lstm_test
        lgb_cal_eval = np.asarray(lgb_val, dtype=float) if lgb_val is not None else None
        xgb_cal_eval = np.asarray(xgb_val, dtype=float) if xgb_val is not None else None
        ens_cal_eval = np.maximum(0, np.asarray(meta_val, dtype=float)) if meta_val is not None else None

    y_te_eval = np.nan_to_num(y_te_eval, nan=0.0, posinf=0.0, neginf=0.0)
    y_pred_eval = np.nan_to_num(y_pred_eval, nan=0.0, posinf=0.0, neginf=0.0)
    lgb_cal_eval = np.nan_to_num(lgb_cal_eval, nan=0.0, posinf=0.0, neginf=0.0) if lgb_cal_eval is not None else None
    xgb_cal_eval = np.nan_to_num(xgb_cal_eval, nan=0.0, posinf=0.0, neginf=0.0) if xgb_cal_eval is not None else None
    ens_cal_eval = np.nan_to_num(ens_cal_eval, nan=0.0, posinf=0.0, neginf=0.0) if ens_cal_eval is not None else None

    m_r2 = r2_score(y_te_eval, y_pred_eval)
    m_mae = mean_absolute_error(y_te_eval, y_pred_eval)
    m_rmse = rmse(y_te_eval, y_pred_eval)
    m_smape = smape(y_te_eval, y_pred_eval)
    confidence = round(max(0.0, 1.0 - m_smape / 100.0) * 100.0, 1)
    cls_metrics = compute_classification_metrics(y_te_eval, y_pred_eval, thr_high, thr_med, peak_ref)

    if verbose:
        print(f"\n  🎯 ENSEMBLE – {room.name} [id={room.id}]")
        print_classification_metrics(cls_metrics, room.name, room.id)
    model_metrics = _evaluate_model_preds(
        y_te_eval,
        {'ensemble': y_pred_eval, 'lightgbm': lgb_eval, 'xgboost': xgb_eval, 'lstm': lstm_eval},
        thr_high, thr_med, peak_ref, room.name,
        cal_preds_dict={'ensemble': ens_cal_eval, 'lightgbm': lgb_cal_eval, 'xgboost': xgb_cal_eval, 'lstm': lstm_cal_eval},
        y_cal=y_cal_eval,
        verbose=verbose,
    )

    # Prediction calibration, fit on the calibration split of whichever
    # model actually serves this room (test_from_excel.py reads
    # 'serving_model'), so the map matches the series it will be applied to.
    _cal_pred_by_model = {
        'ensemble': ens_cal_eval, 'lightgbm': lgb_cal_eval,
        'xgboost': xgb_cal_eval, 'lstm': lstm_cal_eval,
    }
    # 'blend' serves a lightgbm/xgboost mix; score it on the same mix.
    if serving_model == 'blend' and lgb_cal_eval is not None and xgb_cal_eval is not None:
        _bw = serving_weights or {'lightgbm': 0.5, 'xgboost': 0.5}
        _n = min(len(lgb_cal_eval), len(xgb_cal_eval))
        _cal_pred_by_model['blend'] = (
            float(_bw.get('lightgbm', 0.5)) * np.asarray(lgb_cal_eval[:_n], dtype=float)
            + float(_bw.get('xgboost', 0.5)) * np.asarray(xgb_cal_eval[:_n], dtype=float)
        )
    pred_calibration = fit_prediction_calibration(
        y_cal_eval, _cal_pred_by_model.get(serving_model))
    if verbose:
        if pred_calibration is None:
            print(f"   🎚️  prediction calibration ({serving_model}): none "
                  f"(insufficient calibration data)")
        else:
            _pk, _tk = pred_calibration
            print(f"   🎚️  prediction calibration ({serving_model}): "
                  f"p95 {_pk[-2]:.2f}h -> {_tk[-2]:.2f}h")

    return {
        'daily': daily, 'use_log': use_log, 'cap95': cap95, 'peak_ref': peak_ref,
        'peer_profile': peer_profile,
        'thr_high': thr_high, 'thr_med': thr_med,
        'pred_calibration': pred_calibration,
        'room_hour_dist': room_hour_dist, 'confidence': confidence,
        'lgb_model': lgb_model, 'xgb_model': xgb_model, 'ensemble_weights': ensemble_weights,
        'serving_model': serving_model, 'recursive_cal_scores': recursive_cal_scores,
        'serving_weights': serving_weights,
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
        'cap95': result['cap95'], 'peak_ref': result['peak_ref'],
        'thr_high': result['thr_high'], 'thr_med': result['thr_med'],
        'pred_calibration': result.get('pred_calibration'),
        # Which per-room strategy each family ended up with: 'single', or a
        # HurdleRegressor mode ('hard'/'soft') that beat it on calibration.
        'hurdle_modes': {
            'lightgbm': getattr(result.get('lgb_model'), 'mode', 'single'),
            'xgboost': getattr(result.get('xgb_model'), 'mode', 'single'),
        },
        'hour_dist': result['room_hour_dist'], 'confidence': result['confidence'],
        'ensemble_weights': result['ensemble_weights'], 'use_log': result['use_log'],
        'serving_model': result.get('serving_model', 'ensemble'),
        'recursive_cal_scores': result.get('recursive_cal_scores', {}),
        'peer_profile': result.get('peer_profile'),
        'serving_weights': result.get('serving_weights'),
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
    print("🌳 Pipeline: LightGBM/XGBoost (primary) → LSTM only if it clears both validation gates")
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
        # Must go through _prepare_daily_series like every other daily
        # series: summing raw 'duration' by start date dumps a multi-day
        # booking's whole span (up to 416h) onto day one and leaves the
        # days it actually covered at zero. Peer-profile features were
        # built on that shape while the models were trained on the
        # expanded one.
        daily_r = _prepare_daily_series(rdf_r, None, None)
        all_rooms_daily[r] = daily_r if daily_r is not None else pd.Series(dtype=float)

    for room in Room.objects.all():
        rdf = raw[raw['room_id'] == room.id]
        schedule = load_term_schedule(room.id)
        daily = _prepare_daily_series(rdf, room, all_rooms_daily)
        if daily is None or len(daily) < MIN_TRAIN_ROWS:
            print(f"⏭️  {room.name} – ข้าม (ไม่มีข้อมูลพอ)")
            continue

        print(f"\n🏠 {room.name}")
        result = _train_room_pipeline(room, daily, rdf, schedule, all_rooms_daily=all_rooms_daily)
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
            serving_model=result.get('serving_model', 'ensemble'),
            peer_profile=result.get('peer_profile'),
            serving_weights=result.get('serving_weights'),
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

        # โหลด LSTM — เฉพาะเมื่อไม่ได้ปิดไว้ (SKIP_LSTM) ไฟล์ LSTM เก่าที่ค้างจากการทดลอง
        # ก่อนหน้าใช้ฟีเจอร์คนละชุด โหลดมาแล้วพังทั้งการพยากรณ์ ทั้งที่ระบบจริงไม่ใช้ LSTM
        lstm_model, lstm_scaler = None, None
        if meta.get('has_lstm', False) and LSTM_AVAILABLE and not SKIP_LSTM:
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
        # Same expansion the models were trained on — a raw groupby here
        # made the serving series a different shape from the training
        # series (train/serve skew), on top of the multi-day spike.
        daily = _prepare_daily_series(rdf, None, None)
        if daily is None or len(daily) == 0:
            print(f"   ⏭️  {room.name}: ไม่มีข้อมูลการจองที่ใช้ได้ ข้าม")
            continue
        if use_log:
            daily = daily.clip(upper=meta.get('cap95', meta['peak_ref']))

        schedule = load_term_schedule(room.id)
        bulk = _build_forecast_bulk(
            room, lgb_model, xgb_model, ensemble_weights, daily.copy(),
            meta['peak_ref'], meta['thr_high'], meta['thr_med'],
            meta['hour_dist'], meta['confidence'], forecast_dates, schedule,
            lstm_model=lstm_model, lstm_scaler=lstm_scaler,
            ensemble_model=ensemble_model,
            use_log=use_log,
            lstm_lookback=meta.get('lstm_lookback', LSTM_LOOKBACK),
            serving_model=meta.get('serving_model', 'ensemble'),
            peer_profile=meta.get('peer_profile'),
            serving_weights=meta.get('serving_weights'),
        )
        DemandForecast.objects.filter(
            room=room, forecast_date__in=forecast_dates
        ).delete()
        DemandForecast.objects.bulk_create(bulk)

        mode = meta.get('serving_model', 'ensemble')
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
    parser.add_argument('--param-set', type=str, choices=['A', 'B', 'C', 'D', 'E'], default=CURRENT_PARAM_SET,
                        help='Select hyperparameter set: A (Fast), B (Balanced), C (High Quality), D (Extra Deep, default — best measured Ensemble Acc), E (Maximum Depth, diminishing returns past D).')
    parser.add_argument('--days', type=int, default=FORECAST_DAYS,
                        help='พยากรณ์ล่วงหน้ากี่วัน (ค่าเริ่มต้น FORECAST_DAYS) — ตั้งยาว เช่น 120 '
                             'เพื่อไม่ต้องรันใหม่บ่อย; ยิ่งไกลยิ่งแม่นน้อยลงเพราะพยากรณ์ต่อจากค่าที่ทายเอง')
    parser.add_argument('--enable-early-stop', action='store_true',
                        help='Deprecated and ignored: models always train every configured epoch/round.')
    args = parser.parse_args()

    # Set global parameter set before training
    CURRENT_PARAM_SET = args.param_set
    FORECAST_DAYS = max(1, args.days)
    # Keep all learning curves complete; LSTM restores its best epoch and the
    # tree helpers select their calibration-best boosting round afterwards.
    DISABLE_EARLY_STOPPING = True
    params_set = PARAM_SETS.get(CURRENT_PARAM_SET, PARAM_SETS['B'])
    LSTM_EPOCHS = params_set['lstm_epochs']
    LSTM_BATCH = params_set['lstm_batch']
    LSTM_LOOKBACK = params_set.get('lstm_lookback', LSTM_LOOKBACK)
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
