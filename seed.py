"""
seed.py — สร้างข้อมูลจำลองสมจริง ~50,000+ records
วางไว้ที่: /Users/macthanakorn/room_booking/ml/seed.py
รัน: python ml/seed.py
"""

import os, sys, random
import numpy as np
from datetime import datetime, timedelta, date

sys.path.append('/Users/macthanakorn/room_booking')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()

from django.utils import timezone
from booking.models import User, Building, Room, Booking

random.seed(42)
np.random.seed(42)

print("🌱 เริ่ม seed ข้อมูล...")

# ── Reset ──────────────────────────────────────────────
Booking.objects.all().delete()
Room.objects.all().delete()
Building.objects.all().delete()
print("  🗑  ล้างข้อมูลเก่าแล้ว")

# ── Buildings + Rooms ──────────────────────────────────
building_configs = {
    'Library':     {'code': 'LIB',  'count': 12},
    'Science':     {'code': 'SC',   'count': 10},
    'Engineering': {'code': 'EN',   'count': 10},
    'Main':        {'code': 'MAIN', 'count':  8},
}

all_rooms = []
for bname, cfg in building_configs.items():
    b = Building.objects.create(name=bname, code=cfg['code'])
    for i in range(cfg['count']):
        r = Room.objects.create(
            name=f"{cfg['code']}-{i+1:02d}",
            building=b,
            capacity=random.choice([4, 6, 8, 10, 15, 20, 30, 50, 60]),
            floor=random.randint(1, 5),
            room_type=random.choice(['meeting', 'lecture', 'meeting', 'meeting']),
            status='available',
        )
        all_rooms.append(r)
print(f"  🏢 สร้าง {len(all_rooms)} ห้อง")

# ── Users ──────────────────────────────────────────────
if User.objects.filter(username__startswith='seed_').count() < 100:
    roles = ['student'] * 70 + ['lecturer'] * 20 + ['staff'] * 10
    for i in range(300):
        role = roles[i % len(roles)]
        User.objects.get_or_create(
            username=f'seed_{i:03d}',
            defaults={
                'first_name': f'User{i}',
                'last_name': 'Test',
                'email': f'seed{i}@ubu.ac.th',
                'role': role,
            },
        )
users = list(User.objects.all())
print(f"  👤 users {len(users)} คน")

# ── Hour weights (เฉพาะ 08-17 เท่านั้น) ──────────────
HOUR_W = {
    8:  0.50,   # เริ่มเช้า
    9:  1.10,
    10: 1.80,   # peak เช้า
    11: 1.60,
    12: 0.20,   # พักเที่ยง
    13: 1.70,   # peak บ่าย
    14: 1.50,
    15: 1.10,
    16: 0.70,
    17: 0.35,   # ใกล้เลิก
}

# วันในสัปดาห์
DAY_W = {
    0: 1.30,  # จันทร์ — เยอะที่สุด
    1: 1.20,
    2: 1.10,
    3: 1.00,
    4: 0.80,  # ศุกร์
    5: 0.12,  # เสาร์
    6: 0.04,  # อาทิตย์
}

# popularity รายห้อง (บางห้องดังกว่าห้องอื่น)
room_pop = {r.id: np.random.beta(5, 2) for r in all_rooms}

hours  = list(HOUR_W.keys())
hprobs = np.array([HOUR_W[h] for h in hours], dtype=float)
hprobs /= hprobs.sum()

# ── Semester pattern ───────────────────────────────────
def semester_factor(d: date) -> float:
    m = d.month
    # เทอม 1: มิ.ย.–ต.ค., เทอม 2: พ.ย.–มี.ค.
    if m in (6, 7, 8, 9):    return 1.50   # ต้นเทอม 1
    if m in (10,):            return 1.80   # ปลายเทอม 1 / exam
    if m in (11, 12, 1, 2):   return 1.40   # เทอม 2
    if m in (3,):             return 1.70   # exam เทอม 2
    return 0.50                             # ปิดเทอม เม.ย.–พ.ค.

# holiday (วันหยุดนักขัตฤกษ์ไทย คร่าวๆ)
HOLIDAYS = {
    (1, 1), (4, 6), (4, 13), (4, 14), (4, 15),
    (5, 1), (5, 4), (6, 3), (7, 28), (8, 12),
    (10, 13), (10, 23), (12, 5), (12, 10), (12, 31),
}

def daily_base(d: date) -> int:
    if (d.month, d.day) in HOLIDAYS:
        return 5
    return int(250 * DAY_W[d.weekday()] * semester_factor(d))

# ── Generate ───────────────────────────────────────────
START = date.today() - timedelta(days=730)  # 2 ปีย้อนหลัง
END   = date.today()

total, bulk = 0, []
cur = START

while cur <= END:
    base = daily_base(cur)
    # เพิ่ม noise รายวัน ±20%
    n_today = max(0, int(np.random.normal(base, base * 0.2)))
    dist    = np.random.multinomial(n_today, hprobs)

    for i, hr in enumerate(hours):
        for _ in range(dist[i]):
            room = random.choices(
                all_rooms,
                weights=[room_pop[r.id] for r in all_rooms],
                k=1
            )[0]

            # เพิ่ม noise ในนาที 0/15/30/45
            minute = random.choice([0, 15, 30])
            start_dt = timezone.make_aware(
                datetime(cur.year, cur.month, cur.day, hr, minute)
            )

            duration = random.choices(
                [60, 90, 120, 150, 180],
                weights=[0.35, 0.25, 0.25, 0.08, 0.07],
            )[0]

            attendees = max(1, int(np.random.beta(2, 4) * room.capacity) + 1)
            attendees = min(attendees, room.capacity)

            title = random.choices(
                ["ประชุมกลุ่ม", "ติวหนังสือ", "ประชุมโครงการ",
                 "อบรม", "สอบ", "เรียนพิเศษ", "สัมมนา"],
                weights=[25, 20, 20, 10, 10, 10, 5],
            )[0]

            bulk.append(Booking(
                user=random.choice(users),
                room=room,
                title=title,
                attendees=attendees,
                start_time=start_dt,
                end_time=start_dt + timedelta(minutes=duration),
                status='completed',
            ))
            total += 1

    if len(bulk) >= 5000:
        Booking.objects.bulk_create(bulk, ignore_conflicts=True)
        print(f"  💾 {total:,} records  [{cur}]")
        bulk = []

    cur += timedelta(days=1)

if bulk:
    Booking.objects.bulk_create(bulk, ignore_conflicts=True)

days_covered = (END - START).days
print(f"\n✅ Seed เสร็จ")
print(f"   Records   : {total:,}")
print(f"   ช่วงเวลา  : {START} → {END}  ({days_covered} วัน)")
print(f"   ห้อง      : {len(all_rooms)} ห้อง")
print(f"   เฉลี่ย    : {total // days_covered:,} records/วัน")