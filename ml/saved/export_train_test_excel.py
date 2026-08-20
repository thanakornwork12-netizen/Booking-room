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
    return df[['room_code', 'building_code', 'room_type', 'date', 'start_time', 'end_time',
               'duration_hours', 'attendees', 'title', 'status']]


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
