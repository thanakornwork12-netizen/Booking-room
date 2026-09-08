"""
Baseline ที่ไม่ใช้ deep learning — ไว้ตอบว่า "ทำไมต้องใช้ LSTM/ensemble"

สคริปต์นี้ไม่เทรนโมเดล deep learning และไม่โหลดโมเดลที่เทรนไว้เลย มันวัดผล
วิธีพยากรณ์แบบคลาสสิกบน "ชุดทดสอบเดียวกันเป๊ะ" กับที่ test_from_excel.py ใช้
(split เดียวกัน, threshold เดียวกัน, metric เดียวกัน) ตัวเลขที่ได้จึงเอาไป
วางเทียบกับ test_only_results.csv ได้ตรง ๆ

baseline ที่วัด (ทั้งหมดเป็นการทำนายล่วงหน้า 1 วัน เหมือนที่โมเดลถูกวัด):
  naive_lag1      — พรุ่งนี้เท่ากับเมื่อวาน (persistence)
  snaive_lag7     — สัปดาห์หน้าวันเดียวกันเท่ากับสัปดาห์นี้ (seasonal naive)
  moving_avg_7    — ค่าเฉลี่ย 7 วันล่าสุด
  moving_avg_28   — ค่าเฉลี่ย 28 วันล่าสุด
  train_mean      — ค่าคงที่ = ค่าเฉลี่ยของชุดเทรน
  dow_mean        — ค่าเฉลี่ยรายวันในสัปดาห์จากชุดเทรน (climatology)
  ridge_linear    — Ridge regression บนฟีเจอร์ชุดเดียวกัน (ML แต่ไม่ deep)

หมายเหตุ: baseline พวกนี้ไม่ขึ้นกับ hyperparameter set A-E จึงรันครั้งเดียวพอ
threshold/peak_ref อ่านจาก meta ของเซ็ตที่ระบุ (ค่าเริ่มต้น A) เพื่อให้ตัดเกรด
low/medium/urgent ด้วยไม้บรรทัดอันเดียวกับที่โมเดลถูกวัด

Usage: python ml/saved/baseline_from_excel.py [--meta-set A]
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
from sklearn.linear_model import Ridge
import forecast as F
from booking.models import Room

TRAIN_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'booking_data_train.xlsx')
TEST_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'booking_data_test.xlsx')
OUT_CSV = os.path.join(BASE_DIR, 'ml', 'saved', 'metrics_plots', 'baseline_results.csv')
MODEL_CSV = os.path.join(BASE_DIR, 'ml', 'saved', 'metrics_plots', 'test_only_results.csv')

ROOM_IDS = {
    '2C05-06': 443, '2C09': 445, '2C10-11': 446, '2C16-17': 447,
    '3C05-06': 448, '1C-MEETING': 487, '3C16-17': 505, '4C05': 506,
}

META_SET = 'A'
if '--meta-set' in sys.argv:
    META_SET = sys.argv[sys.argv.index('--meta-set') + 1].strip().upper()
META_DIR = os.path.join(BASE_DIR, 'ml', 'saved', f'saved_meta_{META_SET}_excel_split')


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
    return {
        'room': room, 'use_log': use_log, 'feat_df': feat_df,
        'train_end': train_end, 'calib_end': calib_end,
        'X_tr': X.iloc[:train_end], 'X_te': X.iloc[calib_end:],
        'y_tr': y[:train_end], 'y_te': y[calib_end:],
    }


def build_baseline_preds(built):
    """คืน dict ของ baseline -> ค่าพยากรณ์บนชุดทดสอบ

    lag_1 / lag_7 / roll_mean_* มีอยู่ใน feat_df อยู่แล้ว และถูกคำนวณจากค่าจริง
    ในอดีต (shift มาแล้ว) จึงใช้เป็น naive/moving-average ได้ตรง ๆ โดยไม่รั่ว
    ข้อมูลอนาคต และอยู่ใน log space เดียวกับ y เมื่อ use_log=True"""
    X_te, X_tr, y_tr = built['X_te'], built['X_tr'], built['y_tr']
    preds = {
        'naive_lag1':    X_te['lag_1'].to_numpy(dtype=float),
        'snaive_lag7':   X_te['lag_7'].to_numpy(dtype=float),
        'moving_avg_7':  X_te['roll_mean_7'].to_numpy(dtype=float),
        'moving_avg_28': X_te['roll_mean_28'].to_numpy(dtype=float),
        'train_mean':    np.full(len(X_te), float(np.mean(y_tr))),
    }

    # climatology รายวันในสัปดาห์ — คิดจากชุดเทรนเท่านั้น วันไหนไม่เคยเจอในเทรน
    # ให้ตกกลับไปใช้ค่าเฉลี่ยรวม
    dow_tr = pd.Series(y_tr, index=X_tr['dow'].to_numpy())
    dow_map = dow_tr.groupby(level=0).mean()
    preds['dow_mean'] = (
        pd.Series(X_te['dow'].to_numpy()).map(dow_map).fillna(float(np.mean(y_tr))).to_numpy(dtype=float)
    )

    # Ridge บนฟีเจอร์ชุดเดียวกับที่ LGBM/XGB เห็น — เส้นแบ่งว่า "ML ธรรมดา"
    # ทำได้แค่ไหน ก่อนจะไปถึง ensemble/LSTM
    ridge = Ridge(alpha=1.0).fit(X_tr.to_numpy(dtype=float), y_tr)
    preds['ridge_linear'] = ridge.predict(X_te.to_numpy(dtype=float))
    return preds


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
        print(f"   {name:14s} Acc={m['test_accuracy']:.3f}  F1={m['f1']:.3f}  "
              f"R²={m['r2']:7.3f}  MAE={m['mae']:.2f}h")

df = pd.DataFrame(rows)
df.to_csv(OUT_CSV, index=False)
print(f"\n📄 บันทึกแล้ว: {OUT_CSV}")

print("\n\n================ สรุป: ค่าเฉลี่ยทุกห้อง ต่อ baseline ================")
summary = df.groupby('baseline')[['test_accuracy', 'f1', 'r2', 'mae']].mean().sort_values('test_accuracy', ascending=False)
print(summary.to_string())

if os.path.exists(MODEL_CSV):
    mdf = pd.read_csv(MODEL_CSV)
    best = mdf.groupby('param_set')[['test_accuracy', 'f1', 'r2', 'mae']].mean()
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
