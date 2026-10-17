"""พยากรณ์ความต้องการใช้ห้องล่วงหน้าด้วยแบบจำลองชุด C (วิธี direct ที่รายงานในเล่ม) แล้วบันทึกลง
ตาราง DemandForecast ให้หน้าค้นหาใช้ — ทุกวันที่บันทึกเป็นผลทำนายของแบบจำลอง C

ไม่เทรนใหม่ — โหลด saved_direct_sets/C/model.pkl ที่เทรนไว้แล้ว และทำนายด้วยขั้นตอนเดียวกับ
test_direct_sets.py ทุกอย่าง (engine รายห้อง, quantile ensemble, strategy รายห้อง, block floor)
ตัวเลขในเล่มจึงไม่เปลี่ยน

สถิติปีก่อนช่วยเติมข้อมูลนำเข้า
──────────────────────────
แบบจำลองต้องการการใช้งานย้อนหลัง (lag / ค่าเฉลี่ย 7–56 วัน) เป็นตัวแปรหลัก ถ้าระบบไม่มีการจอง
เข้ามาต่อเนื่อง (หลังข้อมูลส่งออกจบ 29 เม.ย. 2569) ตัวแปรเหล่านี้เป็น 0 และแบบจำลองทายต่ำทุกวัน
จึงเติมช่วงที่ไม่มีข้อมูลด้วยสถิติปีก่อน = ค่าเฉลี่ยชั่วโมงใช้งานของวันในสัปดาห์เดียวกัน ตำแหน่งเดียวกัน
ของปีก่อน ๆ (52 สัปดาห์ก่อน ±1 สัปดาห์ สูงสุด 3 ปี ใช้เฉพาะวันที่มีข้อมูลจริง) แล้วให้แบบจำลอง C
ทำนายจากข้อมูลนั้น การจองจริงที่มีในช่วงนั้นยังนับเหมือนเดิม (ใช้ค่าที่มากกว่า)

แบบจำลองทายได้ 1–14 วันจากจุดเริ่ม ช่วงที่ยาวกว่านั้นทำนายเป็นรอบ ๆ ละ 14 วัน โดยเลื่อนจุดเริ่ม
ไปทีละ 14 วัน (ข้อมูลนำเข้าระหว่างรอบมาจากสถิติปีก่อนเช่นกัน)

การรัน (ใช้ฐานข้อมูลตาม DATABASE_URL ของเครื่องที่รัน):
    python ml/saved/serve_direct.py --dry-run      # แสดงผล ไม่เขียนฐานข้อมูล
    python ml/saved/serve_direct.py                # เขียนผล 190 วันข้างหน้าลง DemandForecast
    python ml/saved/serve_direct.py --days 60      # กำหนดจำนวนวันเอง
"""
import argparse
import os
import sys
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')
os.environ.setdefault('DISABLE_DJANGO_SCHEDULER', '1')

import django  # noqa: E402
django.setup()

sys.path.insert(0, os.path.join(BASE_DIR, 'ml', 'saved'))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

import direct_forecast as D  # noqa: E402
import forecast as F  # noqa: E402
from booking.models import Booking, DemandForecast  # noqa: E402

TRAIN_XLSX = os.path.join(BASE_DIR, 'ml/saved/data_split/dataset_train.xlsx')
TEST_XLSX = os.path.join(BASE_DIR, 'ml/saved/data_split/dataset_test.xlsx')
MODEL_PATH = os.path.join(BASE_DIR, 'ml/saved/saved_direct_sets/C/model.pkl')
META_DIR = os.path.join(BASE_DIR, 'ml/saved/saved_meta_C_direct')

DEFAULT_DAYS = 190         # ถึงราว 28 เม.ย. 2570 — ทุกวันยังมีข้อมูลจริงของปีก่อนครบ 3 ปี
SEASON_YEARS = 3           # ใช้ปีก่อนหน้าสูงสุดกี่ปี
COVERAGE_DAYS = 28         # หน้าต่างวัดว่าช่วงไหนยังมีการใช้ระบบต่อเนื่อง
MIN_COVERAGE = 0.5         # 28 วันต้องมีวันที่ใช้ห้องอย่างน้อยครึ่งหนึ่ง จึงนับเป็นข้อมูลจริง
FORECAST_HOURS = range(8, 18)   # ชั่วโมงที่บันทึก (เหมือนผลพยากรณ์เดิม 10 แถวต่อห้องต่อวัน)
# เกณฑ์ของหน้าค้นหา (booking/config.py DEMAND_LEVEL_THRESHOLDS) — คะแนน 0–1 ที่บันทึกถูกจัดให้
# เส้นแบ่งรายห้องของแบบจำลองตกที่ 0.50 (ปานกลาง) และ 0.70 (เร่งด่วน) พอดี
SCORE_MED, SCORE_URGENT = 0.50, 0.70


class ServeData(D.Dataset):
    """Dataset เดียวกับตอนเทรน (Excel ชุดเดิม จึงได้ peak / เส้นแบ่ง / room_ix เหมือนกันทุกตัว)
    บวกการจองในฐานข้อมูลหลังข้อมูลส่งออก และขยายปฏิทินถึงวันที่จะพยากรณ์"""

    def __init__(self, train_xlsx, test_xlsx, extra_rows, horizon_end):
        tr = pd.read_excel(train_xlsx)
        te = pd.read_excel(test_xlsx)
        te = pd.concat([te, extra_rows], ignore_index=True)
        for d in (tr, te):
            d['date'] = pd.to_datetime(d['date'])
            d['duration_hours'] = d['duration_hours'].clip(lower=0.25, upper=12.0)
        self.train_rows, self.test_rows = tr, te

        raw = {}
        for code, rid in D.ROOM_IDS.items():
            s_tr = D._daily_series(tr[tr.room_code == code], rid)
            both = pd.concat([tr[tr.room_code == code], te[te.room_code == code]])
            full = D._daily_series(both, rid)
            if full is None or len(full) == 0:
                continue
            n_train = len(s_tr)
            calib_len = max(1, int(round(n_train * D.CALIB_FRACTION)))
            train_end = max(n_train - calib_len, F.MIN_TRAIN_ROWS)
            calib_end = min(n_train, len(full) - 1)
            cap95 = float(full.iloc[:train_end].quantile(0.95)) or 1.0
            s = full.clip(upper=cap95)
            peak = float(s.iloc[:train_end].quantile(0.95)) or 1.0
            thr_high, thr_med = F.compute_adaptive_thresholds(s.iloc[:train_end], peak)
            raw[code] = dict(s=s, rid=rid, peak=peak, thr_high=thr_high, thr_med=thr_med,
                             scale=max(peak, 1e-6), d_train_end=s.index[train_end],
                             d_calib_end=s.index[calib_end], d_last=s.index[-1])

        end = max(max(d['s'].index[-1] for d in raw.values()), pd.Timestamp(horizon_end))
        self.calendar = pd.date_range(min(d['s'].index[0] for d in raw.values()), end, freq='D')
        pos = {d: i for i, d in enumerate(self.calendar)}
        self.pos = pos
        self.codes = list(raw)
        self.code_ix = {c: i for i, c in enumerate(self.codes)}

        self.rooms = {}
        for code, d in raw.items():
            s = d['s'].reindex(self.calendar, fill_value=0.0)
            self.rooms[code] = dict(
                v=s.to_numpy(float), rid=d['rid'], peak=d['peak'], scale=d['scale'],
                thr_high=d['thr_high'], thr_med=d['thr_med'],
                start=pos[d['s'].index[0]], train_end=pos[d['d_train_end']],
                calib_end=pos[d['d_calib_end']],
                last=len(self.calendar) - 1,   # ให้ build_rows สร้างแถวถึงวันที่จะพยากรณ์
            )

        cal = self.calendar
        self.dow = cal.dayofweek.to_numpy()
        self.doy = cal.dayofyear.to_numpy()
        self.woy = cal.isocalendar().week.to_numpy()
        self.month = cal.month.to_numpy()
        self.dom = cal.day.to_numpy()
        self.holiday = np.array([float(F._is_fixed_th_public_holiday(d)) for d in cal])
        self._precompute_rollups()
        self._precompute_blocks(pd.concat([tr, te], ignore_index=True))


def bookings_after(export_end):
    """การจองในระบบหลังข้อมูลส่งออก ในรูปแบบเดียวกับไฟล์ Excel (เฉพาะที่อนุมัติ/ใช้แล้ว)"""
    code_of = {rid: code for code, rid in D.ROOM_IDS.items()}
    rows = []
    for b in Booking.objects.filter(room_id__in=code_of, status__in=['approved', 'completed'],
                                    start_time__date__gt=export_end):
        s, e = timezone.localtime(b.start_time), timezone.localtime(b.end_time)
        rows.append({'room_code': code_of[b.room_id], 'date': pd.Timestamp(s.date()),
                     'start_time': s.replace(tzinfo=None), 'end_time': e.replace(tzinfo=None),
                     'duration_hours': (e - s).total_seconds() / 3600.0, 'status': b.status})
    return pd.DataFrame(rows, columns=['room_code', 'date', 'start_time', 'end_time',
                                       'duration_hours', 'status'])


def predict_model_c(data, bundle, origin):
    """ทำนาย h = 1..14 จาก origin ด้วยขั้นตอนเดียวกับ test_direct_sets.band_and_hours"""
    qs = bundle['quantiles']
    room_engine = bundle.get('room_engine') or {c: bundle['engine'] for c in data.codes}
    out = {}
    for code in data.codes:
        X, _, meta = data.build_rows(code, [origin])
        if len(X) == 0:
            continue
        spec = bundle['engines'][room_engine[code]]
        q_band = np.column_stack([spec['quantile_models_acc'][q].predict(X) for q in qs])
        q_hours = np.column_stack([spec['quantile_models_mae'][q].predict(X) for q in qs])
        pick = bundle['strategy'].get(code, 'argmax_class')
        cands = D.strategies(data, code, q_band, X, meta)
        band = D.apply_block_floor(cands.get(pick, cands['argmax_class']), X, meta, data)
        hours = np.maximum(0.0, D.apply_block_floor(D.median_forecast(q_hours), X, meta, data))
        out[code] = [(m[3], float(max(0.0, band[i])), float(hours[i])) for i, m in enumerate(meta)]
    return out


def last_real_day(data, upto):
    """วันสุดท้ายที่ระบบยังถูกใช้ต่อเนื่อง (COVERAGE_DAYS วันที่ลงท้ายวันนั้นมีวันที่ใช้ห้องใดห้องหนึ่ง
    ≥ MIN_COVERAGE) — การจองประปรายหลังจากนั้น (เช่นการจองเดโม) ไม่ทำให้นับว่าช่วงที่ว่างคือ
    "ไม่มีคนใช้" ช่วงหลังวันนี้ถือว่า "ไม่มีข้อมูล" และเติมด้วยสถิติปีก่อน"""
    used = np.zeros(upto + 1, dtype=bool)
    for r in data.rooms.values():
        used |= r['v'][:upto + 1] > 0
    cov = pd.Series(used.astype(float)).rolling(COVERAGE_DAYS, min_periods=COVERAGE_DAYS).mean().to_numpy()
    ok = np.flatnonzero(cov >= MIN_COVERAGE)
    return int(ok[-1]) if ok.size else upto


def seasonal_hours(real_v, start, p, last_real):
    """ชั่วโมงใช้งานเฉลี่ยของวันในสัปดาห์เดียวกัน ตำแหน่งเดียวกันของปีก่อน ๆ (52 สัปดาห์ก่อน
    ±1 สัปดาห์ สูงสุด SEASON_YEARS ปี) จากวันที่มีข้อมูลจริงเท่านั้น"""
    vals = []
    for k in range(1, SEASON_YEARS + 1):
        ya = p - 364 * k
        win = [ya + d for d in (-7, 0, 7) if start <= ya + d <= last_real]
        if win:
            vals.append(float(np.mean(real_v[win])))
    return float(np.mean(vals)) if vals else 0.0


def fill_gap_with_history(data, last_real):
    """เติมช่วงหลัง last_real ด้วยสถิติปีก่อน (คงการจองจริงที่มากกว่าไว้) แล้วคำนวณ rolling ใหม่"""
    for r in data.rooms.values():
        real = r['v'].copy()
        r['v'] = real.copy()   # to_numpy() คืนอาร์เรย์อ่านอย่างเดียว
        for p in range(last_real + 1, len(real)):
            r['v'][p] = max(real[p], seasonal_hours(real, r['start'], p, last_real))
    data._precompute_rollups()


def to_score(x, lo, hi):
    """ค่าปกติ (ชั่วโมง / peak) → คะแนน 0–1 ที่เส้นแบ่งรายห้องตก 0.50 / 0.70"""
    if x < lo:
        return SCORE_MED * x / max(lo, 1e-6)
    if x < hi:
        return SCORE_MED + (SCORE_URGENT - SCORE_MED) * (x - lo) / max(hi - lo, 1e-6)
    return min(1.0, SCORE_URGENT + (1.0 - SCORE_URGENT) * (x - hi) / max(hi, 1e-6))


def level_of(score):
    if score >= SCORE_URGENT:
        return 'urgent', 'book_now'
    if score >= SCORE_MED:
        return 'medium', 'recommended'
    return 'low', 'likely_available'


def hour_profile(data):
    """สัดส่วนชั่วโมงที่แต่ละห้องถูกใช้ (จากประวัติทั้งหมด) — ชั่วโมงที่ใช้บ่อยสุดได้ 1.0"""
    rows = pd.concat([data.train_rows, data.test_rows], ignore_index=True)
    prof = {}
    for code in data.codes:
        cnt = np.zeros(24)
        for s, e in zip(pd.to_datetime(rows.loc[rows.room_code == code, 'start_time']),
                        pd.to_datetime(rows.loc[rows.room_code == code, 'end_time'])):
            if e <= s or (e - s) > pd.Timedelta(hours=14):
                continue   # บล็อกหลายวันไม่บอกชั่วโมงที่ใช้จริงของแต่ละวัน
            h = s.hour
            while h < 24 and pd.Timestamp(s.date()) + pd.Timedelta(hours=h) < e:
                cnt[h] += 1
                h += 1
        peak = cnt[list(FORECAST_HOURS)].max() or 1.0
        prof[code] = {h: cnt[h] / peak for h in FORECAST_HOURS}
    return prof


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dry-run', action='store_true', help='แสดงผล ไม่เขียนฐานข้อมูล')
    ap.add_argument('--days', type=int, default=DEFAULT_DAYS,
                    help=f'พยากรณ์ล่วงหน้ากี่วัน (ค่าเริ่มต้น {DEFAULT_DAYS})')
    args = ap.parse_args()
    days = max(1, min(args.days, 365))

    today = timezone.localdate()
    export_end = pd.read_excel(TEST_XLSX)['date'].max().date()
    extra = bookings_after(export_end)
    print(f'วันนี้ {today} | ข้อมูลส่งออกถึง {export_end} | การจองในระบบหลังจากนั้น {len(extra)} รายการ')

    data = ServeData(TRAIN_XLSX, TEST_XLSX, extra, today + timedelta(days=days + D.HORIZON))
    bundle = joblib.load(MODEL_PATH)
    # กันโหลดผิดชุด/ข้อมูลไม่ตรงกับตอนเทรน: ลำดับห้อง (room_ix) และ peak ต้องเท่าเดิม
    trained = bundle['rooms']
    assert list(trained) == data.codes, (list(trained), data.codes)
    for code in data.codes:
        assert abs(trained[code]['peak'] - data.rooms[code]['peak']) < 1e-9, code
    print(f"แบบจำลองชุด {bundle['param_set']} ({bundle['param_set_name']}) engine รายห้อง: "
          f"{bundle.get('room_engine')}")

    today_pos = data.pos[pd.Timestamp(today)]
    last_real = last_real_day(data, today_pos)
    fill_gap_with_history(data, last_real)
    print(f'ข้อมูลการใช้ระบบต่อเนื่องจริงถึง {data.calendar[last_real].date()} — '
          f'ช่วงหลังจากนั้น {today_pos - last_real} วันเติมด้วยสถิติปีก่อนเป็นข้อมูลนำเข้า')

    # แบบจำลอง C ทายได้ 1–14 วันจากจุดเริ่ม: ทำนายเป็นรอบ ๆ เลื่อนจุดเริ่มทีละ 14 วัน
    preds = {code: [] for code in data.codes}
    for origin in range(today_pos, today_pos + days, D.HORIZON):
        for code, rows in predict_model_c(data, bundle, origin).items():
            preds[code] += [x for x in rows if today_pos < x[0] <= today_pos + days]
    profiles = hour_profile(data)
    accuracy = {}
    for code in data.codes:
        p = os.path.join(META_DIR, f"{data.rooms[code]['rid']}_meta.pkl")
        accuracy[code] = float((joblib.load(p).get('cls_metrics') or {}).get('accuracy', 0.0)) if os.path.exists(p) else 0.0

    bulk, summary = [], []
    for code, rows in preds.items():
        r = data.rooms[code]
        lo, hi = data.cuts(code)
        for j, band, hours in rows:
            fc_date = data.calendar[j].date()
            day_score = to_score(band, lo, hi)
            summary.append((code, fc_date, level_of(day_score)[0], band, hours))
            for h in FORECAST_HOURS:
                score = round(day_score * (0.6 + 0.4 * profiles[code][h]), 4)
                lvl, avail = level_of(score)
                bulk.append(DemandForecast(
                    room_id=r['rid'], forecast_date=fc_date, hour=h, predicted_demand=score,
                    demand_level=lvl, availability=avail, confidence=round(accuracy[code] * 100, 1),
                    term_demand=0.0, dynamic_demand=score, source='model'))

    df = pd.DataFrame(summary, columns=['room', 'date', 'level', 'model_norm', 'hours'])
    print('\nระดับรายวัน 14 วันแรก:')
    first = df[pd.to_datetime(df['date']) <= pd.Timestamp(today + timedelta(days=D.HORIZON))]
    print(first.pivot(index='date', columns='room', values='level').to_string())
    df['month'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m')
    print('\nจำนวนวันที่เป็นแต่ละระดับ รายเดือน (ทุกห้องรวม, ผลของแบบจำลอง C):')
    print(df.pivot_table(index='month', columns='level', values='room', aggfunc='count', fill_value=0).to_string())

    if args.dry_run:
        print('\n--dry-run: ไม่ได้เขียนฐานข้อมูล')
        return
    dates = sorted({b.forecast_date for b in bulk})
    with transaction.atomic():
        deleted, _ = DemandForecast.objects.filter(room_id__in=[r['rid'] for r in data.rooms.values()],
                                                   forecast_date__in=dates).delete()
        DemandForecast.objects.bulk_create(bulk)
    print(f'\nบันทึก {len(bulk)} แถว ({dates[0]} – {dates[-1]}) แทนที่ของเดิม {deleted} แถว')


if __name__ == '__main__':
    main()
