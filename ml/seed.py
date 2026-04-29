"""
seed_heavy_v2.py  –  Heavy Seeder สำหรับ Room Booking ML System
═══════════════════════════════════════════════════════════════════
เป้าหมาย  : ~500,000 Booking records ที่มี variance หนักเบาสูง
            ให้ model เทรนได้ผลดี (R² สูง, sMAPE ต่ำ)

Pattern ที่ simulate:
  • Term-in / Term-out contrast  (เทอมเรียน vs ปิดเทอม)
  • Weekly seasonality           (จันทร์–ศุกร์ หนัก, เสาร์–อาทิตย์ เบา)
  • Hour-of-day peak curve       (09-11, 13-15 = peak; 08, 18-20 = low)
  • Room-type demand multiplier  (classroom > lecture > meeting)
  • Monthly trend + noise        (ต้นเทอม/ปลายเทอมต่างกัน)
  • Random event spikes          (งานพิเศษ ~5% ของวัน)
  • Maintenance gaps             (บางห้องมีช่วง unavailable)

วิธีใช้:
  python seed_heavy_v2.py
"""

import os, sys, random
import numpy as np
from datetime import datetime, timedelta, date
from django.db import connection

# ─────────────────────────────────────────────────────────────────────────────
# 0. DJANGO SETUP
# ─────────────────────────────────────────────────────────────────────────────
sys.path.append('/Users/macthanakorn/room_booking')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()

from django.utils import timezone
from booking.models import User, Building, Room, Booking, TermBooking

random.seed(42)
np.random.seed(42)

B = '\033[1;34m'; Y = '\033[1;33m'; G = '\033[1;32m'; R = '\033[1;31m'; W = '\033[0m'

print(f"\n{B}🚀 SEED HEAVY V2  –  Target: ~500,000 Booking Records{W}")
print("=" * 62)

# ─────────────────────────────────────────────────────────────────────────────
# 1. MASTER DATA  (User / Building / Room)
# ─────────────────────────────────────────────────────────────────────────────
print(f"{G}[1/6] Creating Master Data...{W}")

admin, _ = User.objects.get_or_create(
    username='admin',
    defaults={'role': 'admin', 'is_staff': True, 'is_superuser': True}
)
admin.set_password('admin123')
admin.save()

building_configs = {
    'Library':     {'code': 'LIB', 'meeting': 10, 'lecture': 5,  'classroom': 5},
    'Science':     {'code': 'SC',  'meeting': 5,  'lecture': 5,  'classroom': 10},
    'Engineering': {'code': 'EN',  'meeting': 5,  'lecture': 5,  'classroom': 10},
}

all_rooms      = []
classroom_rooms = []
lecture_rooms  = []
meeting_rooms  = []

for bname, cfg in building_configs.items():
    b, _ = Building.objects.get_or_create(name=bname, code=cfg['code'])
    for r_type in ['meeting', 'lecture', 'classroom']:
        for i in range(1, cfg[r_type] + 1):
            cap = (random.choice([30, 60, 100]) if r_type != 'meeting' else
                   random.choice([10, 15, 20]))
            r, _ = Room.objects.get_or_create(
                name=f"{cfg['code']}-{r_type[0].upper()}{i:02d}",
                building=b,
                defaults={
                    'capacity': cap,
                    'floor': random.randint(1, 5),
                    'room_type': r_type,
                    'status': 'available',
                }
            )
            all_rooms.append(r)
            if r_type == 'classroom': classroom_rooms.append(r)
            elif r_type == 'lecture': lecture_rooms.append(r)
            else:                     meeting_rooms.append(r)

# Users — 20 lecturers + 60 students/staff
lecturers = []
for i in range(20):
    u, _ = User.objects.get_or_create(
        username=f'teacher_{i:02d}', defaults={'role': 'lecturer'})
    lecturers.append(u)

students = []
for i in range(60):
    u, _ = User.objects.get_or_create(
        username=f'student_{i:03d}', defaults={'role': 'student'})
    students.append(u)

all_users = lecturers + students

print(f"   Rooms: {len(all_rooms)} | Users: {len(all_users)}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. TERM CALENDAR  (กำหนดช่วงเทอม — 2 ปีย้อนหลัง + ปัจจุบัน)
# ─────────────────────────────────────────────────────────────────────────────
print(f"{G}[2/6] Defining Term Calendar...{W}")

today = date.today()

# แต่ละเทอมกินเวลา ~16 สัปดาห์ (112 วัน), พักระหว่างเทอม ~30–60 วัน
terms = [
    {'name': '2/2566', 'start': today - timedelta(days=730),
                        'end':   today - timedelta(days=618)},
    {'name': '1/2567', 'start': today - timedelta(days=580),
                        'end':   today - timedelta(days=468)},
    {'name': '2/2567', 'start': today - timedelta(days=420),
                        'end':   today - timedelta(days=308)},
    {'name': '1/2568', 'start': today - timedelta(days=270),
                        'end':   today - timedelta(days=158)},
    {'name': '2/2568', 'start': today - timedelta(days=120),
                        'end':   today - timedelta(days=8)},
    {'name': '1/2569', 'start': today - timedelta(days=5),
                        'end':   today + timedelta(days=107)},
]

def in_any_term(d: date) -> tuple[bool, dict | None]:
    for t in terms:
        if t['start'] <= d <= t['end']:
            return True, t
    return False, None

def term_week_fraction(d: date, term: dict) -> float:
    """0.0 = ต้นเทอม, 1.0 = ปลายเทอม (ใช้ boost demand ช่วงสอบ)"""
    total = (term['end'] - term['start']).days
    elapsed = (d - term['start']).days
    return elapsed / max(total, 1)

# ─────────────────────────────────────────────────────────────────────────────
# 3. TERM BOOKINGS  (ตารางสอนประจำเทอม)
# ─────────────────────────────────────────────────────────────────────────────
print(f"{G}[3/6] Creating Term Bookings...{W}")

subjects = [
    ("CS101",   "Intro to IT"),
    ("MATH201", "Calculus"),
    ("ENG302",  "Advanced English"),
    ("PHY101",  "Physics I"),
    ("CHEM201", "Organic Chemistry"),
    ("CS302",   "Data Structures"),
    ("STAT201", "Statistics"),
    ("BIO101",  "Biology"),
]
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("DELETE FROM booking_booking;")

term_bookings = []
for term in terms:
    for room in classroom_rooms + lecture_rooms:
        # classroom จอง 3 วัน/สัปดาห์, lecture จอง 2 วัน/สัปดาห์
        days_per_week = 3 if room in classroom_rooms else 2
        dows = random.sample(range(5), days_per_week)  # เฉพาะวันธรรมดา
        for dow in dows:
            subj_code, subj_name = random.choice(subjects)
            start_h = random.choice([8, 9, 10, 13, 14])
            dur_h   = random.choice([2, 3])
            term_bookings.append(TermBooking(
                user         = random.choice(lecturers),
                room         = room,
                subject_name = subj_name,
                subject_code = subj_code,
                day_of_week  = dow,
                start_time   = datetime.strptime(f"{start_h:02d}:00", "%H:%M").time(),
                end_time     = datetime.strptime(f"{start_h+dur_h:02d}:00", "%H:%M").time(),
                term_start   = term['start'],
                term_end     = term['end'],
                term_name    = term['name'],
                attendees    = int(room.capacity * random.uniform(0.65, 0.95)),
                status       = 'active',
            ))

TermBooking.objects.bulk_create(term_bookings)
print(f"   TermBookings: {TermBooking.objects.count():,}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. DEMAND PARAMETERS  (ตัวแปรควบคุม variance)
# ─────────────────────────────────────────────────────────────────────────────

# Hour-of-day demand curve (peak ช่วง 9-11 และ 13-15)
HOUR_CURVE = {
    7:  0.01, 8:  0.04, 9:  0.14, 10: 0.17, 11: 0.13,
    12: 0.02, 13: 0.15, 14: 0.14, 15: 0.10, 16: 0.07,
    17: 0.05, 18: 0.03, 19: 0.02, 20: 0.01,
}
HOURS = sorted(HOUR_CURVE.keys())
HOUR_WEIGHTS = [HOUR_CURVE[h] for h in HOURS]

# Day-of-week multiplier (0=Mon … 6=Sun)
DOW_MULT = {
    0: 1.00, 1: 0.95, 2: 0.90, 3: 0.85, 4: 0.80,
    5: 0.55, 6: 0.45
}

# Room-type base demand per day (จำนวน bookings เฉลี่ย)
ROOM_TYPE_BASE = {
    'classroom': 28,   # เต็มวัน เพราะมีคาบเรียน
    'lecture':   20,
    'meeting':   12,
}

# ─────────────────────────────────────────────────────────────────────────────
# 5. HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def daily_demand_multiplier(d: date) -> float:
    """
    รวม signal หลายชั้น:
      • in-term vs off-term
      • ตำแหน่งในเทอม (ปลายเทอม = สูง เพราะสอบ)
      • วันธรรมดา vs เสาร์อาทิตย์
      • noise แบบ log-normal
    """
    is_term, term = in_any_term(d)
    dow_mult = DOW_MULT[d.weekday()]

    if is_term:
        frac = term_week_fraction(d, term)
        # เริ่มเทอม 0.8x → กลางเทอม 1.0x → ปลายเทอม 1.3x (ช่วงสอบ)
        term_mult = 0.80 + 0.50 * (frac ** 1.5)
        # ช่วงกลางเทอม (mid-term) สอบ: ~week 7-8
        if 0.40 < frac < 0.55:
            term_mult *= 1.25
    else:
        term_mult = 0.55   # จาก 0.25 → 0.55 (ยังมี demand)

    # monthly variation (ต้นปีน้อยกว่า กลางปี)
    month_mult = 1.0 + 0.15 * np.sin(2 * np.pi * (d.month - 3) / 12)

    # log-normal noise (CV ประมาณ 30%)
    noise = np.random.lognormal(mean=0.0, sigma=0.28)

    return float(term_mult * dow_mult * month_mult * noise)


def is_event_day(d: date) -> bool:
    """วันพิเศษ (งานประชุม, สัมมนา) — ประมาณ 4% ของวันธรรมดา in-term"""
    if d.weekday() >= 5:
        return False
    is_term, _ = in_any_term(d)
    return is_term and (random.random() < 0.04)


def sample_booking_hour() -> int:
    return random.choices(HOURS, weights=HOUR_WEIGHTS)[0]


def sample_duration(room_type: str, is_event: bool = False) -> float:
    """duration เป็นชั่วโมง ขึ้นกับประเภทห้องและ event"""
    if is_event:
        return random.choice([3.0, 4.0, 6.0, 8.0])
    if room_type == 'meeting':
        return random.choices([1.0, 1.5, 2.0, 3.0], weights=[30, 25, 30, 15])[0]
    elif room_type == 'lecture':
        return random.choices([1.5, 2.0, 3.0], weights=[20, 50, 30])[0]
    else:  # classroom
        return random.choices([1.5, 2.0, 3.0, 4.0], weights=[15, 40, 35, 10])[0]


def make_booking(d: date, room: Room, user, hour: int,
                 duration: float, status: str) -> Booking:
    start_dt = timezone.make_aware(
        datetime(d.year, d.month, d.day, hour, random.choice([0, 30]))
    )
    end_dt = start_dt + timedelta(hours=duration)
    titles = {
        'meeting':   ["Team Meeting", "Project Review", "One-on-One",
                      "Budget Meeting", "Dept Meeting", "Planning Session"],
        'lecture':   ["Special Lecture", "Guest Speaker", "Workshop",
                      "Seminar", "Training", "Lab Session"],
        'classroom': ["Study Group", "Tutorial", "Exam Prep",
                      "Group Project", "Review Session"],
    }
    title = random.choice(titles.get(room.room_type, ["Booking"]))
    return Booking(
        user       = user,
        room       = room,
        title      = title,
        attendees  = random.randint(3, min(room.capacity, 40)),
        start_time = start_dt,
        end_time   = end_dt,
        status     = status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. GENERATE BOOKINGS  (2 ปีย้อนหลัง → วันนี้)
# ─────────────────────────────────────────────────────────────────────────────
print(f"{G}[4/6] Generating ~500,000 Booking records...{W}")
print(f"       (อาจใช้เวลา 1-3 นาที){W}")

# ⚠️ ใช้ raw SQL ไปแล้วด้านบน ไม่ต้อง delete ซ้ำก็ได้ แต่คงไว้ตามของเดิม
Booking.objects.all().delete()

START_DATE = today - timedelta(days=730)

bulk_buffer   = []
FLUSH_SIZE    = 5000   # 🔥 ลดจาก 15000 → กัน SQLite ระเบิด
total_created = 0

# maintenance
maintenance = {}
for room in all_rooms:
    windows = []
    if random.random() < 0.3:
        gap_start = START_DATE + timedelta(days=random.randint(0, 690))
        gap_end   = gap_start + timedelta(days=random.randint(3, 10))
        windows.append((gap_start, gap_end))
    maintenance[room.id] = windows


def in_maintenance(d: date, room_id: int) -> bool:
    for (s, e) in maintenance.get(room_id, []):
        if s <= d <= e:
            return True
    return False


curr = START_DATE

while curr <= today:
    event_today = is_event_day(curr)

    for room in all_rooms:

        if in_maintenance(curr, room.id):
            continue

        base  = ROOM_TYPE_BASE[room.room_type]
        mult  = daily_demand_multiplier(curr)

        if event_today and room.room_type in ('meeting', 'lecture'):
            mult *= random.uniform(1.8, 3.0)

        # ✅ FIX: ต้องอยู่ใน loop นี้
        MIN_BOOKINGS_PER_DAY = {
            'classroom': 12,
            'lecture': 8,
            'meeting': 5,
        }

        min_floor = MIN_BOOKINGS_PER_DAY.get(room.room_type, 5)

        n_bookings = int(round(base * mult))

        # ✅ FIX: บังคับขั้นต่ำ
        if n_bookings < min_floor:
            n_bookings = random.randint(min_floor, min_floor + 3)

        # hard cap
        n_bookings = min(n_bookings, 40)

        # ✅ FIX: สร้าง booking ต้องอยู่นอก if
        for _ in range(n_bookings):
            hour = sample_booking_hour()
            dur  = sample_duration(room.room_type, is_event=event_today)

            user = random.choice(
                lecturers if room.room_type in ('classroom', 'lecture')
                else all_users
            )

            status = random.choices(
                ['completed', 'cancelled', 'no_show'],
                weights=[85, 10, 5]
            )[0]

            bulk_buffer.append(
                make_booking(curr, room, user, hour, dur, status)
            )

        # ✅ FIX: flush ต้องอยู่ใน room loop
        if len(bulk_buffer) >= FLUSH_SIZE:
            Booking.objects.bulk_create(bulk_buffer, ignore_conflicts=True)
            total_created += len(bulk_buffer)
            bulk_buffer = []

            print(f"   💾 {total_created:>8,} records saved [{curr}] mult={mult:.2f}")

    curr += timedelta(days=1)

# flush สุดท้าย
if bulk_buffer:
    Booking.objects.bulk_create(bulk_buffer, ignore_conflicts=True)
    total_created += len(bulk_buffer)

print(f"\n   ✅ Total Booking records: {total_created:,}")
# ─────────────────────────────────────────────────────────────────────────────
# 7. EXPAND TERM → COMPLETED CLASS BOOKINGS  (history จากตารางสอน)
# ─────────────────────────────────────────────────────────────────────────────
print(f"{G}[5/6] Expanding Term Bookings → Completed Class Records...{W}")

class_bulk = []
for tb in TermBooking.objects.all():
    curr = tb.term_start
    while curr <= tb.term_end and curr < today:
        if curr.weekday() == tb.day_of_week:
            start_dt = timezone.make_aware(
                datetime.combine(curr, tb.start_time))
            end_dt = timezone.make_aware(
                datetime.combine(curr, tb.end_time))
            # attendance variation: บางวันนักศึกษามาน้อย
            att = int(tb.attendees * random.uniform(0.55, 1.0))
            class_bulk.append(Booking(
                user       = tb.user,
                room       = tb.room,
                title      = f"[Class] {tb.subject_code}",
                attendees  = att,
                start_time = start_dt,
                end_time   = end_dt,
                status     = 'completed',
            ))
        curr += timedelta(days=1)

        if len(class_bulk) >= FLUSH_SIZE:
            Booking.objects.bulk_create(class_bulk, ignore_conflicts=True)
            print(f"   💾 class records flushed... total so far: "
                  f"{Booking.objects.count():,}")
            class_bulk = []

if class_bulk:
    Booking.objects.bulk_create(class_bulk, ignore_conflicts=True)
print("\n🛠️ Fixing low-data rooms...")

for room in all_rooms:
    cnt = Booking.objects.filter(room=room).count()

    if cnt < 5000:
        print(f"   ⚠️ Boosting {room.name} ({cnt} → +extra)")

        extra_bulk = []
        for i in range(5000 - cnt):
            d = today - timedelta(days=random.randint(0, 365))
            hour = sample_booking_hour()
            dur = sample_duration(room.room_type)

            extra_bulk.append(
                make_booking(d, room, random.choice(all_users), hour, dur, 'completed')
            )

            if len(extra_bulk) >= 5000:
                Booking.objects.bulk_create(extra_bulk)
                extra_bulk = []

        if extra_bulk:
            Booking.objects.bulk_create(extra_bulk)
# ─────────────────────────────────────────────────────────────────────────────
# 8. SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{G}[6/6] Summary{W}")
print("=" * 62)

total_b = Booking.objects.count()
total_t = TermBooking.objects.count()

print(f"  TermBookings   : {total_t:>10,}")
print(f"  Total Bookings : {total_b:>10,}")
print()

# breakdown by status
from collections import Counter
statuses = Counter(Booking.objects.values_list('status', flat=True))
for k, v in sorted(statuses.items()):
    pct = v / total_b * 100
    bar = '█' * int(pct / 2)
    print(f"  {k:<12} {bar:<30}  {v:>8,}  ({pct:.1f}%)")

print()

# breakdown by room type
from booking.models import Room as _R
for rt in ['classroom', 'lecture', 'meeting']:
    room_ids = list(_R.objects.filter(room_type=rt).values_list('id', flat=True))
    cnt = Booking.objects.filter(room_id__in=room_ids).count()
    print(f"  {rt:<12}: {cnt:>10,} bookings")

print()
print(f"  🔑 Admin: admin / admin123")
print(f"\n{B}✅ Seeding Complete!{W}")
print("  ➜ รัน demand_forecast_all_in_one.py --retrain ได้เลยครับ")