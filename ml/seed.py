"""
seed.py — สร้างข้อมูลจำลองสมจริง ~50,000+ records (Dynamic & Term Bookings)
วางไว้ที่: /Users/macthanakorn/room_booking/ml/seed.py
รัน: python ml/seed.py
"""

import os, sys, random
import numpy as np
from datetime import datetime, timedelta, date
from collections import Counter

sys.path.append('/Users/macthanakorn/room_booking')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()

from django.utils import timezone
from booking.models import User, Building, Room, Booking, TermBooking

random.seed(42)
np.random.seed(42)

# ── สีสำหรับ terminal ──────────────────────────────────
B = '\033[1;34m'; Y = '\033[1;33m'; G = '\033[1;32m'
C = '\033[1;36m'; D = '\033[2m';    W = '\033[0m'

def sep(t): print(f"\n{B}── {t} {'─'*(46-len(t))}{W}")
def row(k, v, u=''): print(f"  {D}{k:<28}{W} {G}{v}{W} {D}{u}{W}")

print(f"\n{B}{'═'*52}{W}")
print(f"  {Y}🌱 SEED — Room Booking System{W}")
print(f"{B}{'═'*52}{W}")

# ── Reset ──────────────────────────────────────────────
sep('Reset')
bc   = Booking.objects.count()
tbc  = TermBooking.objects.count()
rc   = Room.objects.count()
bdc  = Building.objects.count()

# ฟังก์ชันช่วยลบข้อมูลทีละก้อน ป้องกัน SQLite too many SQL variables
def delete_in_chunks(queryset, batch_size=900):
    while queryset.exists():
        ids = list(queryset.values_list('pk', flat=True)[:batch_size])
        queryset.model.objects.filter(pk__in=ids).delete()

delete_in_chunks(Booking.objects.all())
delete_in_chunks(TermBooking.objects.all())
delete_in_chunks(Room.objects.all())
delete_in_chunks(Building.objects.all())

row('ลบ Booking (รายวัน)',      f'{bc:,}',  'records')
row('ลบ TermBooking (ทั้งเทอม)', f'{tbc:,}', 'records')
row('ลบ Room',                   rc,         'ห้อง')
row('ลบ Building',               bdc,        'อาคาร')

# ── Buildings + Rooms ──────────────────────────────────
sep('Buildings + Rooms')

# room_type weights: meeting / lecture / classroom
# classroom = ห้องเรียนใหญ่ capacity 30-150 คน, จองรายเทอม
building_configs = {
    'Library':     {'code': 'LIB',  'meeting': 10, 'lecture': 2,  'classroom': 2},
    'Science':     {'code': 'SC',   'meeting': 6,  'lecture': 2,  'classroom': 4},
    'Engineering': {'code': 'EN',   'meeting': 6,  'lecture': 2,  'classroom': 4},
    'Main':        {'code': 'MAIN', 'meeting': 4,  'lecture': 2,  'classroom': 6},
}

CLASSROOM_CAPACITIES = [30, 40, 50, 60, 80, 100, 120, 150]
MEETING_CAPACITIES   = [4, 6, 8, 10, 15, 20]
LECTURE_CAPACITIES   = [30, 40, 50, 60]

all_rooms       = []
classroom_rooms = []
lecture_rooms   = []

for bname, cfg in building_configs.items():
    b = Building.objects.create(name=bname, code=cfg['code'])
    rooms_in_b = []
    room_idx   = 1

    # Meeting rooms
    for _ in range(cfg['meeting']):
        r = Room.objects.create(
            name=f"{cfg['code']}-M{room_idx:02d}",
            building=b,
            capacity=random.choice(MEETING_CAPACITIES),
            floor=random.randint(1, 5),
            room_type='meeting',
            status='available',
        )
        all_rooms.append(r); rooms_in_b.append(r); room_idx += 1

    # Lecture rooms
    for _ in range(cfg['lecture']):
        r = Room.objects.create(
            name=f"{cfg['code']}-L{room_idx:02d}",
            building=b,
            capacity=random.choice(LECTURE_CAPACITIES),
            floor=random.randint(1, 5),
            room_type='lecture',
            status='available',
        )
        all_rooms.append(r); rooms_in_b.append(r)
        lecture_rooms.append(r); room_idx += 1

    # Classroom rooms (ห้องเรียนใหญ่ จองรายเทอม)
    for _ in range(cfg['classroom']):
        r = Room.objects.create(
            name=f"{cfg['code']}-C{room_idx:02d}",
            building=b,
            capacity=random.choice(CLASSROOM_CAPACITIES),
            floor=random.randint(1, 5),
            room_type='classroom',
            status='available',
        )
        all_rooms.append(r); rooms_in_b.append(r)
        classroom_rooms.append(r); lecture_rooms.append(r)  # classroom ก็นับเป็น lecture ด้วย
        room_idx += 1

    caps  = [r.capacity for r in rooms_in_b]
    types = Counter(r.room_type for r in rooms_in_b)
    print(f"  {C}[{cfg['code']}] {bname}{W}  {len(rooms_in_b)} ห้อง  "
          f"capacity {min(caps)}–{max(caps)} คน  "
          f"meeting:{types.get('meeting',0)} "
          f"lecture:{types.get('lecture',0)} "
          f"classroom:{types.get('classroom',0)}")

row('รวมทั้งหมด',        len(all_rooms),       'ห้อง')
row('  - classroom',     len(classroom_rooms),  'ห้อง')
row('  - lecture',       len([r for r in all_rooms if r.room_type == 'lecture']), 'ห้อง')
row('  - meeting',       len([r for r in all_rooms if r.room_type == 'meeting']), 'ห้อง')

# ── Users ──────────────────────────────────────────────
sep('Users')
before = User.objects.count()
if User.objects.filter(username__startswith='seed_').count() < 100:
    roles = ['student'] * 70 + ['lecturer'] * 20 + ['staff'] * 10
    for i in range(300):
        role = roles[i % len(roles)]
        User.objects.get_or_create(
            username=f'seed_{i:03d}',
            defaults={
                'first_name': f'User{i}',
                'last_name':  'Test',
                'email':      f'seed{i}@ubu.ac.th',
                'role':       role,
            },
        )
users    = list(User.objects.all())
lecturers = [u for u in users if u.role == 'lecturer']
if not lecturers: lecturers = users[:10]

row('seed_xxx สร้างใหม่', User.objects.count() - before, 'accounts')
for role in ['student','lecturer','staff','admin']:
    n = User.objects.filter(role=role).count()
    if n: row(f'  role={role}', n, 'คน')
row('users ทั้งหมดในระบบ', len(users), 'คน')

# ── Term Config ────────────────────────────────────────
sep('Term Config')

today_date = date.today()

# สร้าง 2 เทอม: เทอมที่แล้ว + เทอมปัจจุบัน (เพื่อให้มีประวัติ)
terms = [
    {
        'name':  f"2/{today_date.year + 542}",
        'start': today_date - timedelta(days=210),
        'end':   today_date - timedelta(days=90),
    },
    {
        'name':  f"1/{today_date.year + 543}",
        'start': today_date - timedelta(days=30),
        'end':   today_date + timedelta(days=90),
    },
]

subjects = [
    ("CS101",   "Introduction to Programming",   'lecture',   2),
    ("CS202",   "Data Structures",               'lecture',   2),
    ("CS301",   "Algorithm Design",              'lecture',   2),
    ("CS401",   "Machine Learning",              'lecture',   2),
    ("MATH101", "Calculus I",                    'lecture',   3),
    ("MATH201", "Linear Algebra",                'lecture',   2),
    ("ENG101",  "English for Communication",     'classroom', 3),
    ("ENG201",  "Academic Writing",              'classroom', 2),
    ("PHYS101", "General Physics",               'classroom', 3),
    ("PHYS201", "Physics Laboratory",            'classroom', 2),
    ("BUS101",  "Introduction to Business",      'classroom', 2),
    ("BUS201",  "Marketing Principles",          'classroom', 2),
    ("CHEM101", "General Chemistry",             'classroom', 3),
    ("BIO101",  "Biology Fundamentals",          'classroom', 2),
]

# Class time slots: (start_hour, duration_hours)  — ตามตารางมหาวิทยาลัยจริง
CLASS_SLOTS = [
    (8,  2), (8,  3),
    (10, 2), (10, 3),
    (13, 2), (13, 3),
    (15, 2),
]

row('จำนวนเทอม', len(terms), 'เทอม')
row('วิชาทั้งหมด', len(subjects), 'วิชา')

# ── Generate Term Bookings ──────────────────────────────
sep('Generate Term Bookings')

term_bookings_all = []

for term in terms:
    t_name  = term['name']
    t_start = term['start']
    t_end   = term['end']

    # แบ่งห้อง classroom สำหรับเทอมนี้
    target_rooms = classroom_rooms + lecture_rooms
    target_rooms = list(set(target_rooms))  # dedup

    for room in target_rooms:
        # classroom รับได้มากกว่า 1 วิชาต่อสัปดาห์ (คนละ slot)
        max_subjects = 3 if room.room_type == 'classroom' else 2
        used_slots   = set()

        num_subj = random.randint(1, max_subjects)
        random.shuffle(subjects)

        for subj_code, subj_name, preferred_type, days_per_week in subjects[:num_subj * 2]:
            if len(used_slots) >= max_subjects:
                break

            # เลือก day_of_week ตาม days_per_week
            available_days = [d for d in range(5)]
            random.shuffle(available_days)
            slot_days = []

            for dow in available_days:
                slot, start_h, end_h = random.choice(
                    [(s, s[0], s[0] + s[1]) for s in CLASS_SLOTS]
                )
                slot_key = (dow, start_h)
                if slot_key in used_slots:
                    continue
                used_slots.add(slot_key)
                slot_days.append((dow, start_h, end_h))
                if len(slot_days) >= min(days_per_week, 2):
                    break

            if not slot_days:
                continue

            for dow, start_h, end_h in slot_days:
                start_time = datetime(2000, 1, 1, start_h, 0).time()
                end_time   = datetime(2000, 1, 1, end_h,   0).time()

                term_bookings_all.append(TermBooking(
                    user         = random.choice(lecturers),
                    room         = room,
                    subject_name = subj_name,
                    subject_code = subj_code,
                    day_of_week  = dow,
                    start_time   = start_time,
                    end_time     = end_time,
                    term_start   = t_start,
                    term_end     = t_end,
                    term_name    = t_name,
                    attendees    = int(room.capacity * random.uniform(0.65, 0.95)),
                    status       = 'active',
                ))

if term_bookings_all:
    TermBooking.objects.bulk_create(term_bookings_all)
    row('สร้างข้อมูล TermBooking', len(term_bookings_all), 'รายการ (2 เทอม)')
    for term in terms:
        n = TermBooking.objects.filter(term_name=term['name']).count()
        row(f"  เทอม {term['name']}", n, 'รายการ')


# ── Expand TermBookings → Booking records (ให้ model เห็น pattern) ───────────
sep('Expand TermBookings → Booking History')

"""
TermBooking = ตารางสอน รายเทอม
แต่ model เรียนรู้จาก Booking (รายวัน) ดังนั้นต้องสร้าง Booking จริงๆ
จากทุก TermBooking โดย loop ทุกสัปดาห์ตลอดเทอม
"""

term_derived_bookings = []
for tb in TermBooking.objects.select_related('room', 'user').all():
    cur = tb.term_start
    # หาวันแรกของเทอมที่ตรง day_of_week
    while cur.weekday() != tb.day_of_week:
        cur += timedelta(days=1)

    while cur <= tb.term_end:
        start_dt = timezone.make_aware(
            datetime(cur.year, cur.month, cur.day,
                     tb.start_time.hour, tb.start_time.minute)
        )
        end_dt = timezone.make_aware(
            datetime(cur.year, cur.month, cur.day,
                     tb.end_time.hour, tb.end_time.minute)
        )
        # สุ่ม absent rate 5-15% (บางครั้งไม่มีคลาส)
        if random.random() > 0.10:
            term_derived_bookings.append(Booking(
                user       = tb.user,
                room       = tb.room,
                title      = f"[เรียน] {tb.subject_code} {tb.subject_name}",
                attendees  = tb.attendees,
                start_time = start_dt,
                end_time   = end_dt,
                status     = 'completed' if end_dt.date() < date.today() else 'confirmed',
            ))
        cur += timedelta(weeks=1)

    if len(term_derived_bookings) >= 5000:
        Booking.objects.bulk_create(term_derived_bookings, batch_size=500, ignore_conflicts=True)
        term_derived_bookings = []

if term_derived_bookings:
    Booking.objects.bulk_create(term_derived_bookings, batch_size=500, ignore_conflicts=True)

term_derived_count = Booking.objects.filter(title__startswith='[เรียน]').count()
row('Booking จาก TermBookings', f'{term_derived_count:,}', 'records')


# ── Config สำหรับ Dynamic Bookings ─────────────────────
sep('Config (Dynamic Bookings)')
HOUR_W = {
    8:  0.50, 9:  1.10, 10: 1.80, 11: 1.60, 12: 0.20,
    13: 1.70, 14: 1.50, 15: 1.10, 16: 0.70, 17: 0.35,
}
DAY_W  = {0:1.30, 1:1.20, 2:1.10, 3:1.00, 4:0.80, 5:0.12, 6:0.04}
HOLIDAYS = {
    (1,1),(4,6),(4,13),(4,14),(4,15),(5,1),(5,4),
    (6,3),(7,28),(8,12),(10,13),(10,23),(12,5),(12,10),(12,31),
}
room_pop = {r.id: np.random.beta(5, 2) for r in all_rooms}

# classroom มี base popularity ต่ำกว่า (จองเป็นรายเทอม ไม่ walk-in)
for r in classroom_rooms:
    room_pop[r.id] *= 0.25

hours  = list(HOUR_W.keys())
hprobs = np.array([HOUR_W[h] for h in hours], dtype=float)
hprobs /= hprobs.sum()

row('ช่วงชั่วโมง',   f'{min(hours)}:00 – {max(hours)}:00', f'({len(hours)} ชั่วโมง)')
row('Peak ช่วงเช้า', '10:00 น.',   f'weight={HOUR_W[10]}')
row('Peak ช่วงบ่าย', '13:00 น.',   f'weight={HOUR_W[13]}')
row('วันหยุด',        len(HOLIDAYS),'วัน/ปี (daily_base=5)')
row('room_pop',       'Beta(5,2)',  f'mean≈0.71 | classroom ×0.25')


def semester_factor(d: date) -> float:
    m = d.month
    if m in (4, 5, 10): return 2.50
    if m in (6, 7, 8, 9): return 1.50
    if m in (11, 12, 1, 2): return 1.40
    if m in (3,): return 1.70
    return 0.50


def daily_base(d: date) -> int:
    if (d.month, d.day) in HOLIDAYS: return 5
    return int(800 * DAY_W[d.weekday()] * semester_factor(d))


# ── Generate Dynamic Bookings ──────────────────────────
sep('Generate Dynamic Bookings')
START = date.today() - timedelta(days=730)
END   = date.today()
row('ช่วงเวลา', f'{START} → {END}', f'({(END-START).days} วัน)')

total, bulk = 0, []
title_counter, hour_counter, room_counter = Counter(), Counter(), Counter()
cur = START

# ชื่อกิจกรรมแยกตาม room_type
TITLES_MEETING   = ["ประชุมกลุ่ม","ประชุมโครงการ","สัมมนา","อบรม","ประชุมคณะ"]
TITLES_LECTURE   = ["ติวหนังสือ","เรียนพิเศษ","ทบทวนบทเรียน","สอบ","Workshop"]
TITLES_CLASSROOM = ["สอบกลางภาค","สอบปลายภาค","อบรมพิเศษ","สอบแก้ตัว","กิจกรรมนักศึกษา"]

while cur <= END:
    base    = daily_base(cur)
    n_today = max(0, int(np.random.normal(base, base * 0.2)))
    dist    = np.random.multinomial(n_today, hprobs)

    for i, hr in enumerate(hours):
        for _ in range(dist[i]):
            room   = random.choices(
                all_rooms,
                weights=[room_pop[r.id] for r in all_rooms],
                k=1,
            )[0]
            minute   = random.choice([0, 15, 30])
            start_dt = timezone.make_aware(
                datetime(cur.year, cur.month, cur.day, hr, minute)
            )
            duration = random.choices(
                [60, 90, 120, 150, 180],
                weights=[0.35, 0.25, 0.25, 0.08, 0.07],
            )[0]
            attendees = max(1, int(np.random.beta(2, 4) * room.capacity) + 1)
            attendees = min(attendees, room.capacity)

            if room.room_type == 'classroom':
                title_pool = TITLES_CLASSROOM
                title_w    = [30, 30, 15, 15, 10]
            elif room.room_type == 'lecture':
                title_pool = TITLES_LECTURE
                title_w    = [30, 25, 20, 15, 10]
            else:
                title_pool = TITLES_MEETING
                title_w    = [30, 25, 20, 15, 10]

            title = random.choices(title_pool, weights=title_w)[0]

            bulk.append(Booking(
                user       = random.choice(users),
                room       = room,
                title      = title,
                attendees  = attendees,
                start_time = start_dt,
                end_time   = start_dt + timedelta(minutes=duration),
                status     = 'completed',
            ))
            title_counter[title]    += 1
            hour_counter[hr]        += 1
            room_counter[room.name] += 1
            total += 1

    if len(bulk) >= 5000:
        Booking.objects.bulk_create(bulk, batch_size=500, ignore_conflicts=True)
        print(f"  {D}💾 {total:,} records  [{cur}]{W}")
        bulk = []

    cur += timedelta(days=1)

if bulk:
    Booking.objects.bulk_create(bulk, batch_size=500, ignore_conflicts=True)

days_covered = (END - START).days

# ── Summary ────────────────────────────────────────────
sep('สรุปผล')
row('Records (รายวัน/dynamic)', f'{total:,}',                    'records')
row('Records (จาก TermBooking)', f'{term_derived_count:,}',       'records')
row('Records (TermBooking)',      f'{len(term_bookings_all):,}',  'วิชา')
row('ช่วงเวลา',                   f'{START} → {END}',             f'({days_covered} วัน)')
row('ห้อง',                        len(all_rooms),                 'ห้อง')
row('เฉลี่ยต่อวัน',                f'{total//days_covered:,}',    'records/วัน')
row('เฉลี่ยต่อห้อง',               f'{total//len(all_rooms):,}',  'records/ห้อง')

print(f"\n  {Y}ชั่วโมง top 3 (จองรายวัน):{W}")
for hr, n in hour_counter.most_common(3):
    pct = n / total * 100
    print(f"    {hr:02d}:00  {G}{n:,}{W}  {D}({pct:.1f}%){W}")

print(f"\n  {Y}ประเภทกิจกรรม (จองรายวัน):{W}")
for t, n in title_counter.most_common():
    pct = n / total * 100
    print(f"    {t:<18}  {G}{n:,}{W}  {D}({pct:.1f}%){W}")

print(f"\n  {Y}ห้อง top 5 (จองรายวัน):{W}")
for name, n in room_counter.most_common(5):
    print(f"    {name:<12}  {G}{n:,}{W}  records")

print(f"\n{B}{'═'*52}{W}")
print(f"  {G}✅ Seed เสร็จสมบูรณ์{W}")
print(f"{B}{'═'*52}{W}\n")