"""
Export the REAL booking history (no synthetic/augmented rows) as three
Excel files, split per room in chronological order — for manual review
before retraining, so it's clear exactly what the model trains/tests on.

  booking_data_original.xlsx  — all real, non-cancelled bookings (ground truth)
  booking_data_train.xlsx     — first 80% of each room's history (by time)
  booking_data_test.xlsx      — last 20% of each room's history (by time, held out)

Split rule per room (by record count, chronological, not random):
  n <= 1   -> everything goes to train, test is empty (flagged in summary)
  n >= 2   -> n_train = round(n * 0.8), clamped so test always keeps >= 1 row

Usage: python ml/saved/export_train_test_excel.py
"""
import os
import sys
import math

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()

import pandas as pd
from booking.models import Booking

OUT_DIR = os.path.join(CURRENT_DIR, 'data_split')
TRAIN_FRAC = 0.80

DOW_TH = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']

# คอลัมน์ที่โค้ดอ่านไปใช้จริง (test_from_excel.py, plot_test_curves_by_set.py
# อ่านตามชื่อคอลัมน์ การเพิ่มคอลัมน์ใหม่จึงไม่กระทบ)
BASE_COLS = ['room_code', 'building_code', 'room_type', 'date', 'start_time', 'end_time',
             'duration_hours', 'attendees', 'title', 'status']
# คอลัมน์อ่านง่ายสำหรับเปิดดูใน Excel — start_time/end_time เป็น datetime เต็ม
# ซึ่งอ่านยากเวลาเปิดไฟล์ตรวจข้อมูลด้วยตา
READABLE_COLS = ['เวลาเริ่ม', 'เวลาสิ้นสุด', 'ช่วงเวลา', 'วันในสัปดาห์', 'ข้ามวัน']


def period_of_day(hour: int) -> str:
    """แบ่งช่วงเวลาตามคาบการใช้ห้องจริง (ข้อมูลเริ่ม 08:00 สิ้นสุด 19:00)"""
    if hour < 12:
        return 'เช้า'
    if hour < 16:
        return 'บ่าย'
    return 'เย็น'


def add_readable_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    """เติมคอลัมน์เวลาแบบอ่านออกต่อจาก date โดยไม่แตะคอลัมน์เดิม

    start_time/end_time ตัวเดิมยังอยู่ครบ (โค้ดเทรน/ทดสอบใช้ตัวนั้น) คอลัมน์ที่
    เพิ่มเป็นค่าที่ derive มาทั้งหมด ไม่ใช่ข้อมูลใหม่ — มีไว้ให้เปิดไฟล์แล้วเห็น
    ทันทีว่าแต่ละรายการจองช่วงไหนของวัน
    """
    out = df.copy()
    start = pd.to_datetime(out['start_time'])
    end = pd.to_datetime(out['end_time'])
    out['เวลาเริ่ม'] = start.dt.strftime('%H:%M')
    out['เวลาสิ้นสุด'] = end.dt.strftime('%H:%M')
    out['ช่วงเวลา'] = start.dt.hour.map(period_of_day)
    out['วันในสัปดาห์'] = start.dt.dayofweek.map(lambda d: DOW_TH[d])
    # การจองที่กินข้ามวัน — expand_bookings_to_daily() ใน forecast.py กระจาย
    # ชั่วโมงของรายการพวกนี้ไปทุกวันที่มันครอบ แถวที่ติดธงนี้จึงไม่ได้ใช้ชั่วโมง
    # ทั้งหมดในวันเดียวตามที่ duration_hours แสดง
    out['ข้ามวัน'] = (end.dt.normalize() > start.dt.normalize()).map({True: 'ใช่', False: ''})
    cols = list(BASE_COLS)
    at = cols.index('date') + 1
    return out[cols[:at] + READABLE_COLS + cols[at:]]


def load_real_bookings() -> pd.DataFrame:
    qs = Booking.objects.exclude(status='cancelled').select_related('room', 'room__building').values(
        'room__name', 'room__room_type', 'room__building__code',
        'start_time', 'end_time', 'status', 'title', 'attendees',
    )
    df = pd.DataFrame(list(qs))
    df = df.rename(columns={
        'room__name': 'room_code',
        'room__room_type': 'room_type',
        'room__building__code': 'building_code',
    })
    for col in ['start_time', 'end_time']:
        df[col] = pd.to_datetime(df[col])
        if df[col].dt.tz is None:
            df[col] = df[col].dt.tz_localize('UTC')
        df[col] = df[col].dt.tz_convert('Asia/Bangkok').dt.tz_localize(None)
    df['duration_hours'] = ((df['end_time'] - df['start_time']).dt.total_seconds() / 3600).round(2)
    df['date'] = df['start_time'].dt.date
    df = df.sort_values(['room_code', 'start_time']).reset_index(drop=True)
    return add_readable_time_columns(df[BASE_COLS])


def split_per_room(df: pd.DataFrame):
    train_parts, test_parts, summary_rows = [], [], []
    for room_code, g in df.groupby('room_code', sort=True):
        g = g.sort_values('start_time')
        n = len(g)
        if n <= 1:
            n_tr = n
        else:
            n_tr = max(1, round(n * TRAIN_FRAC))
            n_tr = min(n_tr, n - 1)
        train_parts.append(g.iloc[:n_tr])
        test_parts.append(g.iloc[n_tr:])
        summary_rows.append({
            'room_code': room_code,
            'total_records': n,
            'train_records': n_tr,
            'test_records': n - n_tr,
            'test_empty': (n - n_tr) == 0,
        })
    train_df = pd.concat(train_parts).reset_index(drop=True) if train_parts else df.iloc[0:0]
    test_df = pd.concat(test_parts).reset_index(drop=True) if test_parts else df.iloc[0:0]
    summary_df = pd.DataFrame(summary_rows)
    return train_df, test_df, summary_df


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_real_bookings()
    print(f"📥 Real (non-cancelled) booking records: {len(df):,} across {df['room_code'].nunique()} rooms")

    train_df, test_df, summary_df = split_per_room(df)

    n_test_empty = int(summary_df['test_empty'].sum())
    print(f"   train: {len(train_df):,} rows   test: {len(test_df):,} rows")
    print(f"   ⚠️  rooms with 0 test rows (only 1 real record total): {n_test_empty}")

    original_path = os.path.join(OUT_DIR, 'booking_data_original.xlsx')
    train_path = os.path.join(OUT_DIR, 'booking_data_train.xlsx')
    test_path = os.path.join(OUT_DIR, 'booking_data_test.xlsx')

    with pd.ExcelWriter(original_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='ประวัติการใช้งาน', index=False)
        summary_df.to_excel(writer, sheet_name='สรุป', index=False)
    train_df.to_excel(train_path, sheet_name='train', index=False)
    test_df.to_excel(test_path, sheet_name='test', index=False)

    print(f"📄 Saved: {original_path}")
    print(f"📄 Saved: {train_path}")
    print(f"📄 Saved: {test_path}")


if __name__ == '__main__':
    main()
