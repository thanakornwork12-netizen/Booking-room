"""
seed.py — สร้างข้อมูลจำลองสมจริง ~50,000+ records
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
from booking.models import User, Building, Room, Booking

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
bc = Booking.objects.count()
rc = Room.objects.count()
bdc= Building.objects.count()
Booking.objects.all().delete()
Room.objects.all().delete()
Building.objects.all().delete()
row('ลบ Booking', f'{bc:,}', 'records')
row('ลบ Room',    rc, 'ห้อง')
row('ลบ Building', bdc, 'อาคาร')

# ── Buildings + Rooms ──────────────────────────────────
sep('Buildings + Rooms')
building_configs = {
    'Library':     {'code': 'LIB',  'count': 12},
    'Science':     {'code': 'SC',   'count': 10},
    'Engineering': {'code': 'EN',   'count': 10},
    'Main':        {'code': 'MAIN', 'count':  8},
}

all_rooms = []
for bname, cfg in building_configs.items():
    b = Building.objects.create(name=bname, code=cfg['code'])
    rooms_in_b = []
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
        rooms_in_b.append(r)
    caps  = [r.capacity for r in rooms_in_b]
    types = Counter(r.room_type for r in rooms_in_b)
    print(f"  {C}[{cfg['code']}] {bname}{W}  {cfg['count']} ห้อง  "
          f"capacity {min(caps)}–{max(caps)} คน  "
          f"meeting:{types.get('meeting',0)} lecture:{types.get('lecture',0)}")

row('รวมทั้งหมด', len(all_rooms), 'ห้อง')

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
                'last_name': 'Test',
                'email': f'seed{i}@ubu.ac.th',
                'role': role,
            },
        )
users = list(User.objects.all())
row('seed_xxx สร้างใหม่', User.objects.count() - before, 'accounts')
for role in ['student','lecturer','staff','admin']:
    n = User.objects.filter(role=role).count()
    if n: row(f'  role={role}', n, 'คน')
row('users ทั้งหมดในระบบ', len(users), 'คน')

# ── Config ─────────────────────────────────────────────
sep('Config')
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
hours  = list(HOUR_W.keys())
hprobs = np.array([HOUR_W[h] for h in hours], dtype=float)
hprobs /= hprobs.sum()

row('ช่วงชั่วโมง',  f'{min(hours)}:00 – {max(hours)}:00', f'({len(hours)} ชั่วโมง)')
row('Peak ช่วงเช้า', '10:00 น.', f'weight={HOUR_W[10]}')
row('Peak ช่วงบ่าย', '13:00 น.', f'weight={HOUR_W[13]}')
row('วันหยุด',       len(HOLIDAYS), 'วัน/ปี (daily_base=5)')
row('room_pop',      'Beta(5,2)',   f'mean≈0.71')

def semester_factor(d: date) -> float:
    m = d.month
    if m in (6,7,8,9):   return 1.50
    if m in (10,):       return 1.80
    if m in (11,12,1,2): return 1.40
    if m in (3,):        return 1.70
    return 0.50

def daily_base(d: date) -> int:
    if (d.month, d.day) in HOLIDAYS: return 5
    return int(250 * DAY_W[d.weekday()] * semester_factor(d))

# ── Generate ───────────────────────────────────────────
sep('Generate Bookings')
START = date.today() - timedelta(days=730)
END   = date.today()
row('ช่วงเวลา', f'{START} → {END}', f'({(END-START).days} วัน)')

total, bulk = 0, []
title_counter, hour_counter, room_counter = Counter(), Counter(), Counter()
cur = START

while cur <= END:
    base    = daily_base(cur)
    n_today = max(0, int(np.random.normal(base, base * 0.2)))
    dist    = np.random.multinomial(n_today, hprobs)

    for i, hr in enumerate(hours):
        for _ in range(dist[i]):
            room   = random.choices(all_rooms, weights=[room_pop[r.id] for r in all_rooms], k=1)[0]
            minute = random.choice([0, 15, 30])
            start_dt = timezone.make_aware(datetime(cur.year, cur.month, cur.day, hr, minute))
            duration = random.choices([60,90,120,150,180], weights=[0.35,0.25,0.25,0.08,0.07])[0]
            attendees = max(1, int(np.random.beta(2, 4) * room.capacity) + 1)
            attendees = min(attendees, room.capacity)
            title = random.choices(
                ["ประชุมกลุ่ม","ติวหนังสือ","ประชุมโครงการ","อบรม","สอบ","เรียนพิเศษ","สัมมนา"],
                weights=[25,20,20,10,10,10,5],
            )[0]
            bulk.append(Booking(
                user=random.choice(users), room=room, title=title,
                attendees=attendees, start_time=start_dt,
                end_time=start_dt + timedelta(minutes=duration), status='completed',
            ))
            title_counter[title]   += 1
            hour_counter[hr]       += 1
            room_counter[room.name]+= 1
            total += 1

    if len(bulk) >= 5000:
        Booking.objects.bulk_create(bulk, ignore_conflicts=True)
        print(f"  {D}💾 {total:,} records  [{cur}]{W}")
        bulk = []

    cur += timedelta(days=1)

if bulk:
    Booking.objects.bulk_create(bulk, ignore_conflicts=True)

days_covered = (END - START).days

# ── Summary ────────────────────────────────────────────
sep('สรุปผล')
row('Records ทั้งหมด',  f'{total:,}',              'records')
row('ช่วงเวลา',         f'{START} → {END}',         f'({days_covered} วัน)')
row('ห้อง',             len(all_rooms),              'ห้อง')
row('เฉลี่ยต่อวัน',     f'{total//days_covered:,}',  'records/วัน')
row('เฉลี่ยต่อห้อง',    f'{total//len(all_rooms):,}','records/ห้อง')

print(f"\n  {Y}ชั่วโมง top 3:{W}")
for hr, n in hour_counter.most_common(3):
    pct = n/total*100
    print(f"    {hr:02d}:00  {G}{n:,}{W}  {D}({pct:.1f}%){W}")

print(f"\n  {Y}ประเภทกิจกรรม:{W}")
for t, n in title_counter.most_common():
    pct = n/total*100
    print(f"    {t:<14}  {G}{n:,}{W}  {D}({pct:.1f}%){W}")

print(f"\n  {Y}ห้อง top 5:{W}")
for name, n in room_counter.most_common(5):
    print(f"    {name:<12}  {G}{n:,}{W}  records")

print(f"\n{B}{'═'*52}{W}")
print(f"  {G}✅ Seed เสร็จสมบูรณ์{W}")
print(f"{B}{'═'*52}{W}\n")