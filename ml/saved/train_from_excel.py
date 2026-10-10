"""
TRAINING ONLY — prints no accuracy/test numbers at all. Trains from
dataset_train.xlsx and saves model files; that's the whole job. For
results, run the separate test_from_excel.py, which loads these saved
models and evaluates them against dataset_test.xlsx.

(dataset_test.xlsx is still read here — its dates are needed to fix the
train/calibration boundary and to keep the lag/rolling features continuous
right up to that boundary — but its rows are never used to fit anything, and
nothing computed from them gets printed by this script.)

No DB query for the booking rows themselves (only Room/TermBooking metadata
comes from the DB, since forecast.py's feature builder needs the Room object
and term schedule).

Runs all hyperparameter sets (A-F), each saved to its own folder.

The boundary between (train+calib) and test is fixed to exactly match
the Excel files' own split (last row in train.xlsx vs first row in
test.xlsx), not a recomputed fraction.

Usage: python ml/saved/train_from_excel.py [--sets A,B,C]  (default: all 5)
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
import pandas as pd
import forecast as F
from param_sets import PARAM_SETS
from booking.models import Room

TRAIN_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'dataset_train.xlsx')
TEST_XLSX = os.path.join(BASE_DIR, 'ml', 'saved', 'data_split', 'dataset_test.xlsx')

# room_code -> room_id, from the 8 rooms confirmed to have real booking history
ROOM_IDS = {
    '2C05-06': 443, '2C09': 445, '2C10-11': 446, '2C16-17': 447,
    '3C05-06': 448, '1C-MEETING': 487, '3C16-17': 505, '4C05': 506,
}

SETS = ['A', 'B', 'C', 'D', 'E', 'F']
if '--sets' in sys.argv:
    idx = sys.argv.index('--sets')
    SETS = [s.strip().upper() for s in sys.argv[idx + 1].split(',') if s.strip()]

ROOMS_FILTER = None
if '--rooms' in sys.argv:
    idx = sys.argv.index('--rooms')
    ROOMS_FILTER = {s.strip() for s in sys.argv[idx + 1].split(',') if s.strip()}

# LSTM has never won the tree-first serving gate on any room trained so far
# (see forecast.LSTM_EXCLUSION_NOTE) — skip fitting it to cut per-room time.
# LSTM is off by default (forecast.SKIP_LSTM = True). --no-lstm is kept so
# existing commands still work; --with-lstm turns it back on.
if '--no-lstm' in sys.argv:
    F.SKIP_LSTM = True
if '--with-lstm' in sys.argv:
    F.SKIP_LSTM = False


def daily_from_rows(df: pd.DataFrame) -> pd.Series:
    """Uses forecast.expand_bookings_to_daily so a multi-day booking (e.g. an
    exam-week block) contributes a bounded, realistic amount to EVERY day it
    spans, instead of its whole raw duration landing on the start date."""
    if len(df) == 0:
        return pd.Series(dtype=float)
    expanded = F.expand_bookings_to_daily(df)
    if len(expanded) == 0:
        return pd.Series(dtype=float)
    s = (expanded.groupby('date')['duration'].sum()
         .reindex(pd.date_range(expanded['date'].min(), expanded['date'].max(), freq='D').date, fill_value=0.0)
         .astype(float))
    s.index = pd.to_datetime(s.index)
    return s


def to_rdf(df: pd.DataFrame, room_id: int) -> pd.DataFrame:
    out = df.copy()
    out['room_id'] = room_id
    out['duration'] = out['duration_hours']
    out['hour'] = pd.to_datetime(out['start_time']).dt.hour
    out['end_hour'] = pd.to_datetime(out['end_time']).dt.hour
    out['date'] = pd.to_datetime(out['date']).dt.date
    return out


train_all = pd.read_excel(TRAIN_XLSX)
test_all = pd.read_excel(TEST_XLSX)
train_all['date'] = pd.to_datetime(train_all['date']).dt.date
test_all['date'] = pd.to_datetime(test_all['date']).dt.date

# Match the production pipeline's load_raw_bookings(): cap each booking at
# 12h (a room's realistic daily operating window) before aggregating by day.
# Without this, a single multi-day booking (e.g. an 8-day exam block logged
# under its start date) dumps its whole 200+ hour total onto one calendar
# day, which no room can physically deliver — a data-representation artifact,
# not real demand, and it was distorting the daily series badly for rooms
# with these multi-day blocks (e.g. 2C05-06).
train_all['duration_hours'] = train_all['duration_hours'].clip(lower=0.25, upper=12.0)
test_all['duration_hours'] = test_all['duration_hours'].clip(lower=0.25, upper=12.0)

print(f"Loaded {len(train_all)} train rows, {len(test_all)} test rows from Excel", flush=True)
print("(test rows are used only to fix the train/calibration boundary and keep features "
      "continuous — nothing computed from them is fit or printed by this script)\n", flush=True)

# All 8 rooms' full daily series (train+test), keyed by Room object, so a
# room with little history can borrow a same-room_type seasonal pattern via
# forecast.fit_peer_profile — the training call below cuts each peer's
# series off before THIS room's own train_end, so no room's calibration/test
# window ever leaks into another room's features through this.
all_rooms_daily = {}
for code, room_id in ROOM_IDS.items():
    room_obj = Room.objects.get(id=room_id)
    tr_rows = train_all[train_all['room_code'] == code]
    te_rows = test_all[test_all['room_code'] == code]
    all_rooms_daily[room_obj] = pd.concat(
        [daily_from_rows(tr_rows), daily_from_rows(te_rows)]
    ).sort_index()

for set_name in SETS:
    params = PARAM_SETS[set_name]
    print(f"\n{'=' * 80}\n TRAINING SET {set_name} — {params['name']}\n{'=' * 80}", flush=True)

    META_DIR = os.path.join(BASE_DIR, 'ml', 'saved', f'saved_meta_{set_name}_excel_split')
    MODEL_DIR = os.path.join(BASE_DIR, 'ml', 'saved', f'saved_models_{set_name}_excel_split')
    os.makedirs(META_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)
    F.META_DIR = META_DIR
    F.MODEL_DIR = MODEL_DIR

    F.CURRENT_PARAM_SET = set_name
    # Train every configured round, then SELECT the calibration-best round
    # afterwards (_mark_best_booster_round records it; _predict_booster serves
    # that round via num_iteration/iteration_range, and LSTM restores its best
    # epoch). This matches what forecast.py's own __main__ already does.
    #
    # It was previously False here, so this path stopped as soon as the
    # calibration slice plateaued — which both truncated every learning curve
    # the plots draw and risked halting before a later, better optimum. The
    # final Excel test split is untouched either way; only the calibration
    # slice is ever consulted.
    F.DISABLE_EARLY_STOPPING = True
    F.LSTM_EPOCHS = params['lstm_epochs']
    F.LSTM_BATCH = params['lstm_batch']
    F.LSTM_LOOKBACK = params['lstm_lookback']

    for code, room_id in ROOM_IDS.items():
        if ROOMS_FILTER is not None and code not in ROOMS_FILTER:
            continue
        room = Room.objects.get(id=room_id)
        tr_rows = train_all[train_all['room_code'] == code]
        te_rows = test_all[test_all['room_code'] == code]
        if len(te_rows) == 0:
            print(f"⏭️  {code}: no test rows in dataset_test.xlsx, skipping")
            continue

        daily_train = daily_from_rows(tr_rows)
        daily_test = daily_from_rows(te_rows)
        daily_full = pd.concat([daily_train, daily_test]).sort_index()
        n_train_days = len(daily_train)

        rdf_full = pd.concat([to_rdf(tr_rows, room.id), to_rdf(te_rows, room.id)], ignore_index=True)
        # TermBooking is empty for every room, so load_term_schedule() alone
        # leaves all 18 term_* features constant zero. Fall back to mining the
        # recurring timetable from this room's own bookings, cut off at the
        # same train_end custom_split uses below — the calibration slice and
        # the Excel test split are both excluded.
        _calib_len = max(1, int(round(n_train_days * 0.125)))
        _train_end = max(n_train_days - _calib_len, F.MIN_TRAIN_ROWS)
        _term_cutoff = daily_full.index[min(_train_end, len(daily_full) - 1)]
        schedule = F.resolve_term_schedule(room.id, rdf_full, cutoff_date=_term_cutoff)

        orig_split = F._split_time_series

        def custom_split(X, y, train_frac=None, calib_frac=None, _n_train=n_train_days):
            n = len(X)
            calib_len = max(1, int(round(_n_train * 0.125)))  # keeps train:calib:test ~= 70:10:20 overall
            train_end = max(_n_train - calib_len, F.MIN_TRAIN_ROWS)
            calib_end = min(_n_train, n - 1)
            if train_end < F.MIN_TRAIN_ROWS or calib_end <= train_end or calib_end >= n:
                return None
            return (X.iloc[:train_end], X.iloc[train_end:calib_end], X.iloc[calib_end:],
                    y[:train_end], y[train_end:calib_end], y[calib_end:],
                    train_end, calib_end)

        F._split_time_series = custom_split
        try:
            print(f"\n🏠 {code}  (train days={len(daily_train)})")
            result = F._train_room_pipeline(room, daily_full, rdf_full, schedule, verbose=False,
                                             all_rooms_daily=all_rooms_daily)
        finally:
            F._split_time_series = orig_split

        if result is None:
            print(f"   ⚠️  {code}: split failed (not enough rows)")
            continue

        F._save_room_models(room, result)
        print(f"✅ {code:.<18} trained and saved (run test_from_excel.py for results)")

    print(f"\n✅ DONE SET {set_name}", flush=True)

print("\n\n🏁 ALL SETS TRAINED — run test_from_excel.py to see accuracy results", flush=True)
