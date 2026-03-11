"""
seed.py — สร้างข้อมูลจำลองสำหรับระบบจองห้องอัจฉริยะ
มหาวิทยาลัยอุบลราชธานี

วิธีรัน:
    python seed.py
"""

import os
import sys
import django
import random
from datetime import datetime, timedelta, date

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')
django.setup()

from django.utils import timezone
from booking.models import (
    User, Building, Room, RoomFacility,
    Booking, BookingLog, RoomUsageStat
)

print("🌱 เริ่มสร้างข้อมูล Seed...")

# ============================================================
# ล้างข้อมูลเก่า
# ============================================================
print("🗑️  ล้างข้อมูลเก่า...")
RoomUsageStat.objects.all().delete()
BookingLog.objects.all().delete()
Booking.objects.all().delete()
RoomFacility.objects.all().delete()
Room.objects.all().delete()
Building.objects.all().delete()
User.objects.filter(is_superuser=False).delete()

# ============================================================
# 1. สร้างอาคาร 9 แห่ง
# ============================================================
print("🏢 สร้างอาคาร 9 แห่ง...")

buildings_data = [
    {'code': 'SC',   'name': 'อาคารวิทยาศาสตร์'},
    {'code': 'EN',   'name': 'อาคารวิศวกรรมศาสตร์'},
    {'code': 'BA',   'name': 'อาคารบริหารธุรกิจ'},
    {'code': 'LIB',  'name': 'อาคารสำนักวิทยบริการ'},
    {'code': 'MED',  'name': 'อาคารแพทยศาสตร์'},
    {'code': 'ART',  'name': 'อาคารศิลปศาสตร์'},
    {'code': 'AGR',  'name': 'อาคารเกษตรศาสตร์'},
    {'code': 'NUR',  'name': 'อาคารพยาบาลศาสตร์'},
    {'code': 'MAIN', 'name': 'อาคารสำนักงานกลาง'},
]

buildings = {}
for d in buildings_data:
    buildings[d['code']] = Building.objects.create(**d)
    print(f"  ✅ {d['code']} — {d['name']}")

# ============================================================
# 2. สร้างห้อง แยกตามหมวดอาคาร
# ============================================================
print("\n🚪 สร้างห้องแยกตามอาคาร...")

# --- โครงสร้าง: (ชื่อห้อง, ชั้น, ความจุ, ประเภทห้อง)
rooms_by_building = {

    'SC': [
        ('SC-101', 1, 30,  'ห้องประชุม'),
        ('SC-102', 1, 50,  'ห้องสัมมนา'),
        ('SC-LAB1',1, 40,  'ห้อง Lab'),
        ('SC-201', 2, 10,  'ห้องประชุมเล็ก'),
        ('SC-202', 2, 8,   'ห้องประชุมเล็ก'),
        ('SC-301', 3, 25,  'ห้องประชุม'),
    ],

    'EN': [
        ('EN-101', 1, 20,  'ห้องประชุม'),
        ('EN-102', 1, 60,  'ห้องสัมมนา'),
        ('EN-LAB1',1, 35,  'ห้อง Lab'),
        ('EN-LAB2',2, 35,  'ห้อง Lab'),
        ('EN-201', 2, 12,  'ห้องประชุมเล็ก'),
        ('EN-301', 3, 8,   'ห้องประชุมเล็ก'),
    ],

    'BA': [
        ('BA-101', 1, 100, 'ห้องบรรยาย'),
        ('BA-201', 2, 25,  'ห้องประชุม'),
        ('BA-202', 2, 15,  'ห้องประชุม'),
        ('BA-VIP', 3, 10,  'ห้องประชุม VIP'),
        ('BA-301', 3, 20,  'ห้องสัมมนา'),
    ],

    'LIB': [
        ('LIB-G1', 1, 6,   'ห้องกลุ่มย่อย'),
        ('LIB-G2', 1, 6,   'ห้องกลุ่มย่อย'),
        ('LIB-G3', 1, 8,   'ห้องกลุ่มย่อย'),
        ('LIB-G4', 1, 8,   'ห้องกลุ่มย่อย'),
        ('LIB-201',2, 20,  'ห้องประชุม'),
        ('LIB-IT', 2, 30,  'ห้อง Lab'),
        ('LIB-301',3, 30,  'ห้องสัมมนา'),
    ],

    'MED': [
        ('MED-101',1, 40,  'ห้องบรรยาย'),
        ('MED-SIM',1, 20,  'ห้อง Lab'),
        ('MED-201',2, 15,  'ห้องประชุม'),
        ('MED-202',2, 10,  'ห้องประชุมเล็ก'),
        ('MED-301',3, 8,   'ห้องประชุมเล็ก'),
    ],

    'ART': [
        ('ART-101',1, 50,  'ห้องบรรยาย'),
        ('ART-201',2, 20,  'ห้องประชุม'),
        ('ART-202',2, 10,  'ห้องประชุมเล็ก'),
        ('ART-STU',3, 15,  'ห้องสัมมนา'),
    ],

    'AGR': [
        ('AGR-101',1, 30,  'ห้องประชุม'),
        ('AGR-LAB',1, 25,  'ห้อง Lab'),
        ('AGR-201',2, 12,  'ห้องประชุมเล็ก'),
        ('AGR-301',3, 20,  'ห้องสัมมนา'),
    ],

    'NUR': [
        ('NUR-101',1, 40,  'ห้องบรรยาย'),
        ('NUR-SIM',1, 20,  'ห้อง Lab'),
        ('NUR-201',2, 15,  'ห้องประชุม'),
        ('NUR-202',2, 8,   'ห้องประชุมเล็ก'),
    ],

    'MAIN': [
        ('MAIN-CON',1, 80,  'ห้องประชุมใหญ่'),
        ('MAIN-101',1, 20,  'ห้องประชุม'),
        ('MAIN-VIP',2, 12,  'ห้องประชุม VIP'),
        ('MAIN-201',2, 15,  'ห้องประชุม'),
        ('MAIN-301',3, 10,  'ห้องประชุมเล็ก'),
    ],
}

# อุปกรณ์ตามประเภทห้อง
facilities_map = {
    'ห้องประชุม':       ['โปรเจกเตอร์', 'ไวท์บอร์ด', 'ระบบเสียง'],
    'ห้องประชุมเล็ก':   ['TV', 'ไวท์บอร์ด'],
    'ห้องประชุมใหญ่':   ['โปรเจกเตอร์', 'ไมโครโฟน', 'ระบบเสียง', 'ไวท์บอร์ด', 'สตรีมมิง'],
    'ห้องสัมมนา':       ['โปรเจกเตอร์', 'ไมโครโฟน', 'ระบบเสียง', 'ไวท์บอร์ด'],
    'ห้องบรรยาย':       ['โปรเจกเตอร์', 'ไมโครโฟน', 'ระบบเสียง'],
    'ห้อง Lab':         ['คอมพิวเตอร์', 'โปรเจกเตอร์'],
    'ห้องประชุม VIP':   ['TV', 'ไวท์บอร์ด', 'ระบบเสียง', 'วิดีโอคอล'],
    'ห้องกลุ่มย่อย':    ['ไวท์บอร์ด'],
}

rooms = []
for bcode, room_list in rooms_by_building.items():
    for (name, floor, capacity, room_type) in room_list:
        r = Room.objects.create(
            building=buildings[bcode],
            name=name,
            floor=floor,
            capacity=capacity,
            room_type=room_type,
        )
        for fname in facilities_map.get(room_type, []):
            RoomFacility.objects.create(room=r, name=fname)
        rooms.append(r)
    print(f"  ✅ {bcode} — {len(room_list)} ห้อง")

print(f"\n  รวมทั้งหมด {len(rooms)} ห้อง")

# ============================================================
# 3. สร้างผู้ใช้ 45 คน
# ============================================================
print("\n👤 สร้างผู้ใช้ 45 คน...")

faculties = [
    'วิทยาศาสตร์', 'วิศวกรรมศาสตร์', 'บริหารธุรกิจ',
    'ศิลปศาสตร์', 'แพทยศาสตร์', 'พยาบาลศาสตร์', 'เกษตรศาสตร์'
]

lecturers, students, staff_users = [], [], []

for i in range(1, 16):
    u = User.objects.create_user(
        username=f'lecturer{i:02d}', password='pass1234',
        first_name=f'อาจารย์ชื่อ{i}', last_name=f'นามสกุล{i}',
        email=f'lecturer{i:02d}@ubu.ac.th',
        role='lecturer', faculty=random.choice(faculties),
        phone=f'08{random.randint(10000000,99999999)}'
    )
    lecturers.append(u)

for i in range(1, 26):
    u = User.objects.create_user(
        username=f'student{i:02d}', password='pass1234',
        first_name=f'นักศึกษาชื่อ{i}', last_name=f'นามสกุล{i}',
        email=f'student{i:02d}@ubu.ac.th',
        role='student', faculty=random.choice(faculties),
        phone=f'08{random.randint(10000000,99999999)}'
    )
    students.append(u)

for i in range(1, 6):
    u = User.objects.create_user(
        username=f'staff{i:02d}', password='pass1234',
        first_name=f'เจ้าหน้าที่ชื่อ{i}', last_name=f'นามสกุล{i}',
        email=f'staff{i:02d}@ubu.ac.th',
        role='staff', faculty='สำนักงานกลาง',
    )
    staff_users.append(u)

all_users = lecturers + students + staff_users
print(f"  ✅ อาจารย์ {len(lecturers)} | นักศึกษา {len(students)} | เจ้าหน้าที่ {len(staff_users)}")

# ============================================================
# User Preference (ใช้ตอน generate booking)
# ============================================================
all_bcodes = list(buildings.keys())

user_prefs = {}
for u in lecturers:
    user_prefs[u.id] = {
        'capacity_range':  random.choice([(10,30),(20,50),(30,100)]),
        'preferred_types': random.sample(['ห้องประชุม','ห้องสัมมนา','ห้องประชุมเล็ก'], 2),
        'preferred_hours': list(range(8, 17)),
        'preferred_bcode': random.choice(all_bcodes),
        'avg_attendees':   random.randint(5, 30),
    }
for u in students:
    user_prefs[u.id] = {
        'capacity_range':  random.choice([(4,10),(6,15)]),
        'preferred_types': random.sample(['ห้องกลุ่มย่อย','ห้อง Lab','ห้องประชุมเล็ก'], 2),
        'preferred_hours': list(range(13, 20)),
        'preferred_bcode': random.choice(['LIB','SC','EN']),
        'avg_attendees':   random.randint(3, 8),
    }
for u in staff_users:
    user_prefs[u.id] = {
        'capacity_range':  random.choice([(10,30),(20,50)]),
        'preferred_types': ['ห้องประชุม','ห้องประชุม VIP','ห้องประชุมใหญ่'],
        'preferred_hours': list(range(9, 16)),
        'preferred_bcode': 'MAIN',
        'avg_attendees':   random.randint(5, 15),
    }

# ============================================================
# 4. สร้างข้อมูล Booking ย้อนหลัง 6 เดือน
# ============================================================
print("\n📅 สร้างข้อมูลการจอง (ย้อนหลัง 6 เดือน)...")

today       = date.today()
start_date  = today - timedelta(days=180)

WEEKDAY_WEIGHT = [0.9, 0.95, 0.85, 0.90, 0.80, 0.30, 0.10]
HOUR_WEIGHT = {
    8:0.3, 9:0.9, 10:1.0, 11:0.95,
    12:0.4, 13:0.85, 14:1.0, 15:0.90,
    16:0.6, 17:0.3, 18:0.2, 19:0.1
}

titles = [
    'ประชุมกลุ่มวิจัย','นัดประชุมโปรเจกต์','สอบสัมภาษณ์',
    'ประชุมวิชาการ','อบรมเชิงปฏิบัติการ','ประชุมคณะกรรมการ',
    'ติวหนังสือกลุ่ม','นำเสนองาน','ประชุมนักศึกษา',
    'ประชุมสโมสร','สัมมนาวิชาการ','เตรียมสอบกลุ่ม',
    'ประชุมหลักสูตร','ประชุมบุคลากร','อบรมพัฒนาทักษะ',
]

bookings_created = 0
current_date = start_date

while current_date <= today:
    weekday    = current_date.weekday()
    day_weight = WEEKDAY_WEIGHT[weekday]
    n_bookings = max(0, min(int(random.gauss(10 * day_weight, 2)), 20))

    for _ in range(n_bookings):
        user = random.choice(all_users)
        pref = user_prefs[user.id]

        avail_hours   = [h for h in pref['preferred_hours'] if h in HOUR_WEIGHT]
        if not avail_hours:
            continue
        hour_w        = [HOUR_WEIGHT[h] for h in avail_hours]
        start_hour    = random.choices(avail_hours, weights=hour_w)[0]
        duration      = random.choices([1,2,3], weights=[0.4,0.4,0.2])[0]

        start_dt = timezone.make_aware(datetime(
            current_date.year, current_date.month, current_date.day,
            start_hour, random.choice([0,30])
        ))
        end_dt = start_dt + timedelta(hours=duration)

        cap_min, cap_max = pref['capacity_range']
        matched = [
            r for r in rooms
            if r.room_type in pref['preferred_types']
            and cap_min <= r.capacity <= cap_max
        ] or rooms

        preferred = [r for r in matched if r.building.code == pref['preferred_bcode']]
        others    = [r for r in matched if r.building.code != pref['preferred_bcode']]
        ranked    = preferred + others
        room      = ranked[0] if ranked else random.choice(rooms)

        if current_date < today - timedelta(days=7):
            status = random.choices(
                ['completed','no_show','cancelled'],
                weights=[0.75,0.15,0.10]
            )[0]
        elif current_date < today:
            status = random.choices(
                ['completed','approved','no_show','cancelled'],
                weights=[0.50,0.30,0.10,0.10]
            )[0]
        else:
            status = random.choices(['approved','pending'], weights=[0.7,0.3])[0]

        attendees = max(1, min(
            pref['avg_attendees'] + random.randint(-2,3),
            room.capacity
        ))

        try:
            b = Booking.objects.create(
                user=user, room=room,
                title=random.choice(titles),
                attendees=attendees,
                start_time=start_dt, end_time=end_dt,
                status=status, note=''
            )
            BookingLog.objects.create(
                booking=b, changed_by=user,
                old_status='pending', new_status=status,
            )
            bookings_created += 1
        except Exception:
            pass

    current_date += timedelta(days=1)

print(f"  ✅ การจองทั้งหมด {bookings_created} รายการ")

# ============================================================
# 5. สร้างสถิติรายวัน
# ============================================================
print("\n📊 สร้างสถิติรายวัน...")
stats_created = 0

for room in rooms:
    check_date = start_date
    while check_date <= today:
        qs    = Booking.objects.filter(room=room, start_time__date=check_date)
        total = qs.count()
        if total > 0:
            completed  = qs.filter(status='completed').count()
            no_show    = qs.filter(status='no_show').count()
            cancelled  = qs.filter(status='cancelled').count()
            booked_hrs = sum(
                b.duration_hours()
                for b in qs.filter(status__in=['completed','approved'])
            )
            utilization = min((booked_hrs / 12) * 100, 100)
            RoomUsageStat.objects.update_or_create(
                room=room, date=check_date,
                defaults=dict(
                    total_bookings=total,
                    completed=completed,
                    no_show=no_show,
                    cancelled=cancelled,
                    utilization_rate=round(utilization, 1),
                )
            )
            stats_created += 1
        check_date += timedelta(days=1)

print(f"  ✅ สถิติรายวัน {stats_created} รายการ")

# ============================================================
# สรุป
# ============================================================
print("\n" + "="*50)
print("✅ Seed เสร็จสมบูรณ์!")
print(f"  🏢 อาคาร:        {Building.objects.count()} แห่ง")
print(f"  🚪 ห้อง:         {Room.objects.count()} ห้อง")
print(f"  👤 ผู้ใช้:        {User.objects.filter(is_superuser=False).count()} คน")
print(f"  📅 การจอง:       {Booking.objects.count()} รายการ")
print(f"  📊 สถิติรายวัน:  {RoomUsageStat.objects.count()} รายการ")
print("="*50)
print("\n💡 ข้อมูลพร้อมเทรน LSTM:")
ready = Booking.objects.filter(status__in=['completed','no_show']).count()
print(f"   Booking ที่มีผลแล้ว: {ready} รายการ")