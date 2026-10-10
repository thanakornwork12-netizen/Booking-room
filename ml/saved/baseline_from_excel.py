"""
Baseline ที่ไม่ใช้ deep learning — ไว้ตอบว่า "ทำไมต้องใช้ LSTM/ensemble"

สคริปต์นี้ไม่เทรนโมเดล deep learning และไม่โหลดโมเดลที่เทรนไว้เลย มันวัดผล
วิธีพยากรณ์แบบคลาสสิกบน "ชุดทดสอบเดียวกันเป๊ะ" กับที่ test_from_excel.py ใช้
(split เดียวกัน, threshold เดียวกัน, metric เดียวกัน) ตัวเลขที่ได้จึงเอาไป
วางเทียบกับ test_only_results.csv ได้ตรง ๆ

baseline ที่วัด (ทั้งหมดเป็นการทำนายล่วงหน้า 1 วัน เหมือนที่โมเดลถูกวัด):
  naive_lag1      — พรุ่งนี้เท่ากับเมื่อวาน (persistence)
  snaive_lag7     — สัปดาห์หน้าวันเดียวกันเท่ากับสัปดาห์นี้ (seasonal naive)

(เดิมมี ridge_linear ด้วย แต่ตัดออกแล้ว — มันฟิตบนฟีเจอร์ diff_1/diff_7/pct_chg_7
ที่คำนวณจาก y ของวันเดียวกัน (lag_1 + diff_1 == y พอดี) ได้ R²≈1.00 ไม่ใช่เพราะ
โมเดลเก่ง แต่เพราะบวกกลับเฉลยได้ตรง ๆ — ดู build_features() ใน forecast.py)

หมายเหตุ: baseline พวกนี้ไม่ขึ้นกับ hyperparameter set A-E จึงรันครั้งเดียวพอ
threshold/peak_ref อ่านจาก meta ของเซ็ตที่ระบุ (ค่าเริ่มต้น A) เพื่อให้ตัดเกรด
low/medium/urgent ด้วยไม้บรรทัดอันเดียวกับที่โมเดลถูกวัด

Usage: python ml/saved/baseline_from_excel.py [--meta-set A]
"""
import os, sys

# รากโปรเจกต์ (ml/saved/ อยู่ลึกลงไปสองชั้น) — เดิม hardcode path ของเครื่องเดียว
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
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
import forecast as F
from booking.models import Room

# dataset_train/test.xlsx (จาก split_dataset_from_excel.py) แทน booking_data_*.xlsx
# เดิม — ตัดที่ "วันตัดร่วม" เดียวกันทุกห้องและที่ขอบวัน ปิดสองรอยรั่ว: (1) ของเดิม
# แบ่ง 80% แยกรายห้อง ทำให้ train ของห้องหนึ่งคาบเกี่ยว test ของอีกห้อง (2) ของเดิม
# ตัดตามจำนวนแถวไม่ใช่ขอบวัน ทำให้บางวันมีทั้งรายการที่อยู่ train และ test ปนกัน
TRAIN_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'dataset_train.xlsx')
TEST_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'dataset_test.xlsx')
OUT_CSV = os.path.join(BASE_DIR, 'ml', 'saved', 'metrics_plots', 'baseline_results.csv')
MODEL_CSV = os.path.join(BASE_DIR, 'ml', 'saved', 'metrics_plots', 'test_only_results.csv')
# --direct compares against the direct-model sets and takes thresholds from
# their metas, so baseline and model are graded with the same cuts.
DIRECT = '--direct' in sys.argv
if DIRECT:
    MODEL_CSV = MODEL_CSV.replace('.csv', '_direct.csv')
    # Thresholds come from the direct metas in this mode, so the baseline rows
    # differ from the pipeline's; keep them in their own file.
    OUT_CSV = OUT_CSV.replace('.csv', '_direct.csv')

ROOM_IDS = {
    '2C05-06': 443, '2C09': 445, '2C10-11': 446, '2C16-17': 447,
    '3C05-06': 448, '1C-MEETING': 487, '3C16-17': 505, '4C05': 506,
}

META_SET = 'A'
if '--meta-set' in sys.argv:
    META_SET = sys.argv[sys.argv.index('--meta-set') + 1].strip().upper()
META_DIR = os.path.join(BASE_DIR, 'ml', 'saved',
                        f"saved_meta_{META_SET}{'_direct' if DIRECT else '_excel_split'}")


def to_rdf(df: pd.DataFrame, room_id: int) -> pd.DataFrame:
    out = df.copy()
    out['room_id'] = room_id
    out['duration'] = out['duration_hours']
    out['date'] = pd.to_datetime(out['date']).dt.date
    return out


def rebuild_room_features(code, room_id, train_all, test_all):
    """สร้าง daily series / feat_df / จุดแบ่ง train-test ให้เหมือน
    test_from_excel.py:rebuild_room_features() ทุกประการ — ถ้าแก้ฝั่งโน้น
    ต้องแก้ตรงนี้ด้วย ไม่งั้นตัวเลข baseline กับโมเดลจะเทียบกันไม่ได้"""
    tr_rows = train_all[train_all['room_code'] == code]
    te_rows = test_all[test_all['room_code'] == code]
    if len(te_rows) == 0:
        return None

    rdf_full = pd.concat([to_rdf(tr_rows, room_id), to_rdf(te_rows, room_id)], ignore_index=True)
    daily_full = F._prepare_daily_series(rdf_full, None, None)
    daily_train_only = F._prepare_daily_series(to_rdf(tr_rows, room_id), None, None)
    n_train_days = len(daily_train_only) if daily_train_only is not None else 0

    calib_len = max(1, int(round(n_train_days * 0.125)))
    train_end = max(n_train_days - calib_len, F.MIN_TRAIN_ROWS)
    calib_end = min(n_train_days, len(daily_full) - 1)
    train_end = min(train_end, calib_end)

    room = Room.objects.get(id=room_id)
    # TermBooking is empty for every room here, so load_term_schedule() alone
    # leaves all 18 term_* features constant zero. resolve_term_schedule falls
    # back to mining the recurring timetable out of this room's own bookings,
    # cut off at train_end so nothing from calibration or test is used.
    _term_cutoff = daily_full.index[min(train_end, len(daily_full) - 1)]
    schedule = F.resolve_term_schedule(room.id, rdf_full, cutoff_date=_term_cutoff)
    use_log = F._needs_log_transform(room)
    cap95 = float(daily_full.iloc[:train_end].quantile(0.95)) or 1.0
    daily_clipped = daily_full.clip(upper=cap95)
    term_df = F.build_term_daily_features(daily_clipped.index, schedule)
    term_df.index = daily_clipped.index
    feat_df = F.build_features(daily_clipped, term_df, use_log=use_log, booking_ahead_df=rdf_full).dropna()
    calib_end = min(n_train_days, len(feat_df) - 1)
    train_end = min(train_end, calib_end)

    X = feat_df.drop(columns='y')
    y = feat_df['y'].values
    return {
        'room': room, 'use_log': use_log, 'feat_df': feat_df,
        # Raw-scale daily series aligned to feat_df's index (build_features
        # drops the first rows that have no lag history). build_baseline_preds
        # walks this in actual hours and log1p's on the way out, so it must
        # NOT be the log-space feat_df['y'].
        'daily': daily_clipped.loc[feat_df.index],
        'train_end': train_end, 'calib_end': calib_end,
        'X_tr': X.iloc[:train_end], 'X_te': X.iloc[calib_end:],
        'y_tr': y[:train_end], 'y_te': y[calib_end:],
    }


def build_baseline_preds(built):
    """Baselines on the same repeated 14-day recursive horizon as ML test.

    At each new forecast origin the observed history is available again; within
    the horizon, only the baseline's own prior predictions may be used.
    """
    horizon = max(1, int(F.FORECAST_DAYS))
    out = {'naive_lag1': [], 'snaive_lag7': []}
    start, end = built['calib_end'], len(built['daily'])
    for origin in range(start, end, horizon):
        histories = {
            name: built['daily'].iloc[:origin].copy()
            for name in out
        }
        for forecast_date in built['daily'].index[origin:min(origin + horizon, end)]:
            for name, lag in [('naive_lag1', 1), ('snaive_lag7', 7)]:
                history = histories[name]
                raw = float(history.iloc[-lag]) if len(history) >= lag else float(history.iloc[-1])
                raw = max(0.0, raw)
                out[name].append(float(np.log1p(raw)) if built['use_log'] else raw)
                history.loc[forecast_date] = raw
    return {name: np.asarray(pred, dtype=float) for name, pred in out.items()}


def score(y_te, raw_pred, use_log, thr_high, thr_med, peak_ref):
    """แปลงกลับจาก log space แล้ววัดด้วย metric ชุดเดียวกับ test_from_excel.py"""
    if use_log:
        y_true = np.expm1(y_te)
        y_pred = np.expm1(np.maximum(0, raw_pred))
    else:
        y_true = y_te.copy()
        y_pred = np.maximum(0, raw_pred)
    y_true = np.nan_to_num(y_true, nan=0.0, posinf=0.0, neginf=0.0)
    y_pred = np.nan_to_num(y_pred, nan=0.0, posinf=0.0, neginf=0.0)
    n = min(len(y_true), len(y_pred))
    y_true, y_pred = y_true[:n], y_pred[:n]
    cls = F.compute_classification_metrics(y_true, y_pred, thr_high, thr_med, peak_ref)
    return {
        'test_accuracy': round(cls['accuracy'], 4),
        'balanced_accuracy': round(cls['balanced_accuracy'], 4),
        'f1': round(cls['f1'], 4),
        'r2': F.r2_score(y_true, y_pred),
        'mae': F.mean_absolute_error(y_true, y_pred),
        'n_test': n,
    }


train_all = pd.read_excel(TRAIN_XLSX)
test_all = pd.read_excel(TEST_XLSX)
train_all['date'] = pd.to_datetime(train_all['date']).dt.date
test_all['date'] = pd.to_datetime(test_all['date']).dt.date

print(f"{'=' * 80}\n BASELINE (ไม่มี deep learning) — threshold จาก meta เซ็ต {META_SET}\n{'=' * 80}", flush=True)

rows = []
for code, room_id in ROOM_IDS.items():
    meta_path = os.path.join(META_DIR, f'{room_id}_meta.pkl')
    if not os.path.exists(meta_path):
        print(f"⏭️  {code}: ไม่มี meta ในเซ็ต {META_SET} ข้าม")
        continue
    meta = joblib.load(meta_path)
    built = rebuild_room_features(code, room_id, train_all, test_all)
    if built is None:
        continue

    thr_high, thr_med, peak_ref = meta['thr_high'], meta['thr_med'], meta['peak_ref']
    use_log = meta.get('use_log', False)

    print(f"\n🏠 {code} (n_test={len(built['y_te'])})")
    for name, pred in build_baseline_preds(built).items():
        m = score(built['y_te'], pred, use_log, thr_high, thr_med, peak_ref)
        rows.append({'room': code, 'baseline': name, **m})
        print(f"   {name:14s} Acc={m['test_accuracy']:.3f}  BalAcc={m['balanced_accuracy']:.3f}  F1={m['f1']:.3f}  "
              f"R²={m['r2']:7.3f}  MAE={m['mae']:.2f}h")

df = pd.DataFrame(rows)
df.to_csv(OUT_CSV, index=False)
print(f"\n📄 บันทึกแล้ว: {OUT_CSV}")

print("\n\n================ สรุป: ค่าเฉลี่ยทุกห้อง ต่อ baseline ================")
summary = df.groupby('baseline')[['test_accuracy', 'balanced_accuracy', 'f1', 'r2', 'mae']].mean().sort_values('test_accuracy', ascending=False)
print(summary.to_string())

if os.path.exists(MODEL_CSV):
    mdf = pd.read_csv(MODEL_CSV)
    _cols = [c for c in ['test_accuracy', 'balanced_accuracy', 'f1', 'r2', 'mae'] if c in mdf.columns]
    best = mdf.groupby('param_set')[_cols].mean()
    print("\n================ เทียบกับโมเดลที่เทรนแล้ว (test_only_results.csv) ================")
    print(best.to_string())
    print(f"\n🏆 baseline ที่ดีที่สุด : {summary.index[0]} Acc={summary['test_accuracy'].iloc[0]:.3f} "
          f"F1={summary['f1'].iloc[0]:.3f} MAE={summary['mae'].iloc[0]:.2f}h")
    top_set = best['test_accuracy'].idxmax()
    print(f"🏆 โมเดลที่ดีที่สุด (เซ็ต {top_set}) : Acc={best.loc[top_set, 'test_accuracy']:.3f} "
          f"F1={best.loc[top_set, 'f1']:.3f} MAE={best.loc[top_set, 'mae']:.2f}h")
    print(f"📈 ส่วนต่าง : Acc +{best.loc[top_set, 'test_accuracy'] - summary['test_accuracy'].iloc[0]:.3f}  "
          f"MAE ลดลง {summary['mae'].iloc[0] - best.loc[top_set, 'mae']:.2f}h")

print("\n🏁 เสร็จสิ้น", flush=True)
