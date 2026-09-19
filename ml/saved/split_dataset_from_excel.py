"""แบ่ง train/test จากไฟล์ dataset ต้นฉบับโดยตรง (ไม่ผ่าน database)

  ต้นทาง: ml/saved/data_split/รวมข้อมูลห้องและประวัติการใช้งาน_ฉบับสมบูรณ์_จัดระเบียบแล้ว.xlsx
  ผลลัพธ์: dataset_train.xlsx / dataset_test.xlsx  (คอลัมน์เหมือน booking_data_*.xlsx
           จึงนำไปใช้แทนกันได้)

กฎการแบ่ง — ต่างจาก export_train_test_excel.py สองข้อ เพื่อปิดช่องรั่วที่พบ:

  1. ตัดด้วย "วันตัดร่วม" วันเดียวสำหรับทุกห้อง ไม่ใช่ 80% ของแต่ละห้อง
     ของเดิมแบ่งแยกรายห้อง แต่ละห้องมีช่วงเวลาต่างกัน ผลคือช่วง train ของ
     ห้องหนึ่งไปคาบเกี่ยวกับช่วง test ของอีกห้อง (16.2% ของแถว train เกิด
     หลัง test เริ่มแล้ว) โมเดลที่เทรนรวมหลายห้องจึงเห็นอนาคตของห้องหนึ่ง
     ตอนทำนายอดีตของอีกห้อง

  2. ตัดที่ "ขอบวัน" ไม่ใช่ขอบแถว
     ของเดิมแบ่งตามจำนวนแถว วันที่มีหลายการจองจึงถูกหั่นคาวัน — บางรายการ
     ของวันนั้นอยู่ train บางรายการอยู่ test (เกิดกับ 4 จาก 8 ห้อง) โมเดล
     เห็นบางส่วนของวันที่ต้องทำนายไปแล้ว

สถานะ: นับรวมทุกสถานะ รวม 'ลบแล้ว' ด้วย เพราะงานนี้นิยาม "การใช้งาน" เป็น
การเกิดขึ้นของความต้องการใช้ห้อง (demand) ไม่ใช่การเข้าใช้จริง (occupancy)
คอลัมน์ source_status เก็บสถานะเดิมไว้ เผื่ออยากกรองภายหลัง

Usage: python ml/saved/split_dataset_from_excel.py [--train-frac 0.8]
"""
import os
import re
import sys

import pandas as pd

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(CURRENT_DIR, 'data_split')
SRC = os.path.join(OUT_DIR, 'รวมข้อมูลห้องและประวัติการใช้งาน_ฉบับสมบูรณ์_จัดระเบียบแล้ว.xlsx')

TRAIN_FRAC = 0.80
if '--train-frac' in sys.argv:
    TRAIN_FRAC = float(sys.argv[sys.argv.index('--train-frac') + 1])

HISTORY_HEADER = ['ลำดับ', 'ห้อง', 'วันที่เริ่ม', 'วันที่สิ้นสุด', 'ระยะเวลา', 'ชั่วโมง',
                  'ชื่องาน', 'ผู้ขอใช้', 'อีเมล์', 'หน่วยงาน', 'จำนวนผู้ใช้', 'สถานะ']
DOW_TH = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
OUT_COLS = ['room_code', 'building_code', 'room_type', 'date',
            'เวลาเริ่ม', 'เวลาสิ้นสุด', 'ช่วงเวลา', 'วันในสัปดาห์', 'ข้ามวัน',
            'start_time', 'end_time', 'duration_hours', 'attendees', 'title',
            'status', 'source_status']


def period_of_day(hour: int) -> str:
    if hour < 12:
        return 'เช้า'
    if hour < 16:
        return 'บ่าย'
    return 'เย็น'


def find_history_header(raw: pd.DataFrame) -> int:
    """หาแถวหัวตารางของส่วนที่ 2 แทนการฝังเลขแถวไว้ตรง ๆ เผื่อไฟล์ขยับ"""
    for i in range(len(raw)):
        row = [str(v).strip() for v in raw.iloc[i].tolist()]
        if 'ห้อง' in row and 'วันที่เริ่ม' in row:
            return i
    raise SystemExit('หาหัวตารางประวัติการใช้งานไม่เจอ — ตรวจรูปแบบไฟล์ต้นทาง')


def load_history() -> pd.DataFrame:
    raw = pd.read_excel(SRC, sheet_name='ข้อมูลห้อง ODL1 (เดิม)', header=None)
    hdr = find_history_header(raw)
    df = raw.iloc[hdr + 1:].copy()
    df.columns = HISTORY_HEADER
    df = df[df['ห้อง'].notna()].copy()

    start = pd.to_datetime(df['วันที่เริ่ม'], errors='coerce')
    end = pd.to_datetime(df['วันที่สิ้นสุด'], errors='coerce')
    bad = start.isna() | end.isna() | (end <= start)
    if bad.any():
        print(f'⚠️  ข้ามแถวที่เวลาไม่สมบูรณ์ {int(bad.sum())} แถว')
    df, start, end = df[~bad], start[~bad], end[~bad]

    # "ODL1_2C09: ห้องปฏิบัติการคอมพิวเตอร์ (30 ที่นั่ง)" -> "2C09"
    code = df['ห้อง'].astype(str).str.extract(r'ODL1_([^:]+)')[0].str.strip()
    code = code.replace({'1C_Meeting_Room': '1C-MEETING'})

    out = pd.DataFrame({
        'room_code': code.values,
        'room_type': df['ห้อง'].astype(str).str.extract(r':\s*([^(]+)')[0].str.strip().values,
        'date': start.dt.normalize().values,
        'เวลาเริ่ม': start.dt.strftime('%H:%M').values,
        'เวลาสิ้นสุด': end.dt.strftime('%H:%M').values,
        'ช่วงเวลา': start.dt.hour.map(period_of_day).values,
        'วันในสัปดาห์': start.dt.dayofweek.map(lambda d: DOW_TH[d]).values,
        'ข้ามวัน': (end.dt.normalize() > start.dt.normalize()).map({True: 'ใช่', False: ''}).values,
        'start_time': start.values,
        'end_time': end.values,
        'duration_hours': ((end - start).dt.total_seconds() / 3600.0).round(2).values,
        'attendees': pd.to_numeric(df['จำนวนผู้ใช้'], errors='coerce').fillna(0).astype(int).values,
        'title': df['ชื่องาน'].astype(str).values,
        'source_status': df['สถานะ'].astype(str).values,
    })
    out['building_code'] = 'ODL'
    out['status'] = 'completed'
    return out[out['room_code'].notna()].sort_values(['start_time', 'room_code']).reset_index(drop=True)


def main():
    df = load_history()
    # เลือกวันตัดที่ทำให้สัดส่วน "จำนวนรายการ" ใกล้ TRAIN_FRAC ที่สุด แทนการตัดที่
    # TRAIN_FRAC ของจำนวนวัน — แต่ละวันมีจำนวนการจองไม่เท่ากัน (ช่วงสอบจองทีละ
    # 5-8 ห้อง ปิดเทอมแทบไม่มีเลย) การตัดตามวันจึงเพี้ยนจากสัดส่วนที่ต้องการ
    # ยังคงตัดที่ขอบวันเสมอ ไม่มีวันไหนถูกแบ่งไปอยู่ทั้งสองฝั่ง
    per_day = df.groupby('date').size().sort_index()
    cum = per_day.cumsum() / len(df)
    cutoff_idx = int((cum - TRAIN_FRAC).abs().argmin())
    cutoff = per_day.index[cutoff_idx] + pd.Timedelta(days=1)
    days = pd.DatetimeIndex(per_day.index)

    train = df[df['date'] < cutoff]
    test = df[df['date'] >= cutoff]

    os.makedirs(OUT_DIR, exist_ok=True)
    train_path = os.path.join(OUT_DIR, 'dataset_train.xlsx')
    test_path = os.path.join(OUT_DIR, 'dataset_test.xlsx')
    train[OUT_COLS].to_excel(train_path, index=False)
    test[OUT_COLS].to_excel(test_path, index=False)

    print(f'ต้นทาง : {len(df)} รายการ | {days[0].date()} → {days[-1].date()} ({len(days)} วัน)')
    print(f'วันตัด : {cutoff.date()}  (train < วันนี้ , test >= วันนี้)')
    print(f'train  : {len(train):5d} รายการ ({len(train)/len(df)*100:.1f}%)  {train["date"].min().date()} → {train["date"].max().date()}')
    print(f'test   : {len(test):5d} รายการ ({len(test)/len(df)*100:.1f}%)  {test["date"].min().date()} → {test["date"].max().date()}')
    assert train['date'].max() < test['date'].min(), 'ช่วงเวลา train/test ทับกัน'
    print('✅ ไม่มีวันไหนอยู่ทั้งสองฝั่ง')

    print('\nรายห้อง:')
    print(f'  {"ห้อง":12s} {"train":>6s} {"test":>6s}')
    for c in sorted(df['room_code'].unique()):
        print(f'  {c:12s} {len(train[train.room_code==c]):6d} {len(test[test.room_code==c]):6d}')

    print('\nสถานะเดิมในต้นทาง:')
    for k, v in df['source_status'].value_counts().items():
        print(f'  {k:14s} {v}')

    print(f'\n📄 {train_path}\n📄 {test_path}')


if __name__ == '__main__':
    main()
