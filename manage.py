#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

"""
seed.py — สร้างข้อมูลจำลองสำหรับระบบจองห้องอัจฉริยะ
รัน: python manage.py shell < seed.py
หรือ: python seed.py (ถ้าตั้ง DJANGO_SETTINGS_MODULE แล้ว)

ข้อมูลที่สร้าง:
  - 4 อาคาร, 20 ห้อง
  - 50 ผู้ใช้ (อาจารย์ + นักศึกษา + เจ้าหน้าที่)
  - ~1,500 การจอง ย้อนหลัง 6 เดือน (พร้อม Pattern จริง)
  - Preference ของแต่ละ User (ขนาดห้อง, ประเภท, ตึก)
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
# 1. สร้างอาคาร
# ============================================================
print("🏢 สร้างอาคาร...")
buildings_data = [
    {'code': 'SC',  'name': 'อาคารวิทยาศาสตร์'},
    {'code': 'EN',  'name': 'อาคารวิศวกรรมศาสตร์'},
    {'code': 'BA',  'name': 'อาคารบริหารธุรกิจ'},
    {'code': 'LIB', 'name': 'อาคารสำนักวิทยบริการ'},
]
buildings = {d['code']: Building.objects.create(**d) for d in buildings_data}

# ============================================================
# 2. สร้างห้อง
# ============================================================
print("🚪 สร้างห้อง...")
rooms_data = [
    # อาคาร SC
    {'building': 'SC', 'name': 'SC-101', 'floor': 1, 'capacity': 30,  'room_type': 'ห้องประชุม'},
    {'building': 'SC', 'name': 'SC-201', 'floor': 2, 'capacity': 10,  'room_type': 'ห้องประชุมเล็ก'},
    {'building': 'SC', 'name': 'SC-202', 'floor': 2, 'capacity': 50,  'room_type': 'ห้องสัมมนา'},
    {'building': 'SC', 'name': 'SC-301', 'floor': 3, 'capacity': 8,   'room_type': 'ห้องประชุมเล็ก'},
    {'building': 'SC', 'name': 'SC-LAB', 'floor': 1, 'capacity': 40,  'room_type': 'ห้อง Lab'},
    # อาคาร EN
    {'building': 'EN', 'name': 'EN-101', 'floor': 1, 'capacity': 20,  'room_type': 'ห้องประชุม'},
    {'building': 'EN', 'name': 'EN-201', 'floor': 2, 'capacity': 60,  'room_type': 'ห้องสัมมนา'},
    {'building': 'EN', 'name': 'EN-202', 'floor': 2, 'capacity': 12,  'room_type': 'ห้องประชุมเล็ก'},
    {'building': 'EN', 'name': 'EN-LAB', 'floor': 3, 'capacity': 35,  'room_type': 'ห้อง Lab'},
    {'building': 'EN', 'name': 'EN-301', 'floor': 3, 'capacity': 8,   'room_type': 'ห้องประชุมเล็ก'},
    # อาคาร BA
    {'building': 'BA', 'name': 'BA-101', 'floor': 1, 'capacity': 100, 'room_type': 'ห้องบรรยาย'},
    {'building': 'BA', 'name': 'BA-201', 'floor': 2, 'capacity': 25,  'room_type': 'ห้องประชุม'},
    {'building': 'BA', 'name': 'BA-202', 'floor': 2, 'capacity': 15,  'room_type': 'ห้องประชุม'},
    {'building': 'BA', 'name': 'BA-VIP', 'floor': 3, 'capacity': 10,  'room_type': 'ห้องประชุม VIP'},
    # อาคาร LIB
    {'building': 'LIB', 'name': 'LIB-G1',  'floor': 1, 'capacity': 6,  'room_type': 'ห้องกลุ่มย่อย'},
    {'building': 'LIB', 'name': 'LIB-G2',  'floor': 1, 'capacity': 6,  'room_type': 'ห้องกลุ่มย่อย'},
    {'building': 'LIB', 'name': 'LIB-G3',  'floor': 1, 'capacity': 8,  'room_type': 'ห้องกลุ่มย่อย'},
    {'building': 'LIB', 'name': 'LIB-201', 'floor': 2, 'capacity': 20, 'room_type': 'ห้องประชุม'},
    {'building': 'LIB', 'name': 'LIB-301', 'floor': 3, 'capacity': 30, 'room_type': 'ห้องสัมมนา'},
    {'building': 'LIB', 'name': 'LIB-IT',  'floor': 2, 'capacity': 30, 'room_type': 'ห้อง Lab'},
]

rooms = []
for d in rooms_data:
    r = Room.objects.create(
        building=buildings[d['building']],
        name=d['name'], floor=d['floor'],
        capacity=d['capacity'], room_type=d['room_type']
    )
    rooms.append(r)

# อุปกรณ์แต่ละห้อง
facilities_map = {
    'ห้องประชุม':      ['โปรเจกเตอร์', 'ไวท์บอร์ด', 'ระบบเสียง'],
    'ห้องประชุมเล็ก':  ['TV', 'ไวท์บอร์ด'],
    'ห้องสัมมนา':      ['โปรเจกเตอร์', 'ไมโครโฟน', 'ระบบเสียง', 'ไวท์บอร์ด'],
    'ห้อง Lab':        ['คอมพิวเตอร์', 'โปรเจกเตอร์'],
    'ห้องบรรยาย':      ['โปรเจกเตอร์', 'ไมโครโฟน', 'ระบบเสียง'],
    'ห้องประชุม VIP':  ['TV', 'ไวท์บอร์ด', 'ระบบเสียง', 'วิดีโอคอล'],
    'ห้องกลุ่มย่อย':   ['ไวท์บอร์ด'],
}
for r in rooms:
    for fname in facilities_map.get(r.room_type, []):
        RoomFacility.objects.create(room=r, name=fname)

# ============================================================
# 3. สร้างผู้ใช้ (สะท้อน Flow จริง — มี preference ฝังอยู่ใน pattern การจอง)
# ============================================================
print("👤 สร้างผู้ใช้...")

faculties = ['วิทยาศาสตร์', 'วิศวกรรมศาสตร์', 'บริหารธุรกิจ', 'ศิลปศาสตร์', 'สาธารณสุขศาสตร์']

# อาจารย์ 15 คน
lecturers = []
for i in range(1, 16):
    u = User.objects.create_user(
        username=f'lecturer{i:02d}',
        password='pass1234',
        first_name=f'อาจารย์ชื่อ{i}',
        last_name=f'นามสกุล{i}',
        email=f'lecturer{i:02d}@ubu.ac.th',
        role='lecturer',
        faculty=random.choice(faculties),
        phone=f'08{random.randint(10000000,99999999)}'
    )
    lecturers.append(u)

# นักศึกษา 25 คน
students = []
for i in range(1, 26):
    u = User.objects.create_user(
        username=f'student{i:02d}',
        password='pass1234',
        first_name=f'นักศึกษาชื่อ{i}',
        last_name=f'นามสกุล{i}',
        email=f'student{i:02d}@ubu.ac.th',
        role='student',
        faculty=random.choice(faculties),
        phone=f'08{random.randint(10000000,99999999)}'
    )
    students.append(u)

# เจ้าหน้าที่ 5 คน
staff_users = []
for i in range(1, 6):
    u = User.objects.create_user(
        username=f'staff{i:02d}',
        password='pass1234',
        first_name=f'เจ้าหน้าที่ชื่อ{i}',
        last_name=f'นามสกุล{i}',
        email=f'staff{i:02d}@ubu.ac.th',
        role='staff',
        faculty='สำนักงาน',
    )
    staff_users.append(u)

all_users = lecturers + students + staff_users

# ============================================================
# USER PREFERENCE MAP
# สะท้อน Flow: ผู้ใช้บอก preference แล้วระบบแนะนำห้อง
# เก็บเป็น dict ใช้ตอน generate booking
# ============================================================
user_prefs = {}
for u in lecturers:
    # อาจารย์ชอบห้องประชุมขนาดกลาง-ใหญ่ ช่วงเช้า-บ่าย
    user_prefs[u.id] = {
        'preferred_capacity': random.choice([(10,30), (20,50), (30,100)]),
        'preferred_types':    random.sample(['ห้องประชุม','ห้องสัมมนา','ห้องประชุมเล็ก'], 2),
        'preferred_hours':    list(range(8, 17)),   # 08:00-16:00
        'preferred_building': random.choice(list(buildings.keys())),
        'typical_attendees':  random.randint(5, 30),
    }
for u in students:
    # นักศึกษาชอบห้องกลุ่มย่อย/Lab ช่วงบ่าย-เย็น
    user_prefs[u.id] = {
        'preferred_capacity': random.choice([(4,10), (6,15)]),
        'preferred_types':    random.sample(['ห้องกลุ่มย่อย','ห้อง Lab','ห้องประชุมเล็ก'], 2),
        'preferred_hours':    list(range(13, 20)),  # 13:00-19:00
        'preferred_building': random.choice(['LIB', 'SC', 'EN']),
        'typical_attendees':  random.randint(3, 8),
    }
for u in staff_users:
    user_prefs[u.id] = {
        'preferred_capacity': random.choice([(10,30), (20,50)]),
        'preferred_types':    ['ห้องประชุม', 'ห้องประชุม VIP'],
        'preferred_hours':    list(range(9, 16)),
        'preferred_building': 'BA',
        'typical_attendees':  random.randint(5, 15),
    }

# ============================================================
# 4. สร้างข้อมูลการจอง ย้อนหลัง 6 เดือน
# ============================================================
print("📅 สร้างข้อมูลการจอง (ย้อนหลัง 6 เดือน)...")

today = date.today()
start_date = today - timedelta(days=180)

# Pattern การจองจริง (สะท้อนพฤติกรรมในมหาวิทยาลัย)
# วันจันทร์-ศุกร์ แน่นกว่าเสาร์-อาทิตย์
# ช่วง 09:00-12:00 และ 13:00-16:00 แน่นที่สุด
WEEKDAY_WEIGHT = [0.9, 0.95, 0.85, 0.90, 0.80, 0.30, 0.10]  # จ-อา
HOUR_WEIGHT = {
    8: 0.3, 9: 0.9, 10: 1.0, 11: 0.95,
    12: 0.4, 13: 0.85, 14: 1.0, 15: 0.90,
    16: 0.6, 17: 0.3, 18: 0.2, 19: 0.1
}

booking_titles = [
    'ประชุมกลุ่มวิจัย', 'นัดประชุมโปรเจกต์', 'สอบสัมภาษณ์',
    'ประชุมวิชาการ', 'อบรมเชิงปฏิบัติการ', 'ประชุมคณะกรรมการ',
    'ติวหนังสือกลุ่ม', 'นำเสนองาน', 'ประชุมนักศึกษา',
    'ประชุมสโมสร', 'สัมมนาวิชาการ', 'เตรียมสอบกลุ่ม',
]

bookings_created = 0
current_date = start_date

while current_date <= today:
    weekday = current_date.weekday()  # 0=จันทร์, 6=อาทิตย์
    day_weight = WEEKDAY_WEIGHT[weekday]

    # จำนวน booking ต่อวัน (สะท้อน Pattern จริง)
    daily_bookings = int(random.gauss(8 * day_weight, 2))
    daily_bookings = max(0, min(daily_bookings, 15))

    for _ in range(daily_bookings):
        user = random.choice(all_users)
        pref = user_prefs[user.id]

        # เลือกชั่วโมงตาม preference ของ user + hour weight
        available_hours = [h for h in pref['preferred_hours'] if h in HOUR_WEIGHT]
        if not available_hours:
            continue
        hour_weights = [HOUR_WEIGHT.get(h, 0.1) for h in available_hours]
        start_hour = random.choices(available_hours, weights=hour_weights)[0]

        # ระยะเวลา 1-3 ชั่วโมง
        duration = random.choices([1, 2, 3], weights=[0.4, 0.4, 0.2])[0]

        start_dt = timezone.make_aware(
            datetime(current_date.year, current_date.month, current_date.day,
                     start_hour, random.choice([0, 30]))
        )
        end_dt = start_dt + timedelta(hours=duration)

        # เลือกห้องที่ตรง preference ของ user
        cap_min, cap_max = pref['preferred_capacity']
        matching_rooms = [
            r for r in rooms
            if r.room_type in pref['preferred_types']
            and cap_min <= r.capacity <= cap_max
        ]
        if not matching_rooms:
            matching_rooms = rooms  # fallback

        # เรียงห้องตาม preference ตึก (สะท้อน ranking ที่ระบบแสดง)
        preferred_rooms = [r for r in matching_rooms
                           if r.building.code == pref['preferred_building']]
        other_rooms = [r for r in matching_rooms
                       if r.building.code != pref['preferred_building']]
        ranked_rooms = preferred_rooms + other_rooms

        room = ranked_rooms[0] if ranked_rooms else random.choice(rooms)

        # สถานะการจอง (สะท้อน Pattern จริง)
        if current_date < today - timedelta(days=7):
            # ข้อมูลเก่า — มีผลลัพธ์แล้ว
            status = random.choices(
                ['completed', 'no_show', 'cancelled'],
                weights=[0.75, 0.15, 0.10]
            )[0]
        elif current_date < today:
            # สัปดาห์ที่แล้ว
            status = random.choices(
                ['completed', 'approved', 'no_show', 'cancelled'],
                weights=[0.50, 0.30, 0.10, 0.10]
            )[0]
        else:
            # วันนี้
            status = random.choices(
                ['approved', 'pending'],
                weights=[0.7, 0.3]
            )[0]

        attendees = min(
            pref['typical_attendees'] + random.randint(-2, 3),
            room.capacity
        )
        attendees = max(1, attendees)

        try:
            b = Booking.objects.create(
                user=user,
                room=room,
                title=random.choice(booking_titles),
                attendees=attendees,
                start_time=start_dt,
                end_time=end_dt,
                status=status,
                note=''
            )
            bookings_created += 1

            # BookingLog
            BookingLog.objects.create(
                booking=b,
                changed_by=user,
                old_status='pending',
                new_status=status,
            )
        except Exception:
            pass  # ข้าม ถ้า error

    current_date += timedelta(days=1)

print(f"  ✅ สร้าง Booking ทั้งหมด {bookings_created} รายการ")

# ============================================================
# 5. สร้าง RoomUsageStat รายวัน (สำหรับ Dashboard)
# ============================================================
print("📊 สร้างสถิติรายวัน...")
stats_created = 0
for room in rooms:
    check_date = start_date
    while check_date <= today:
        bookings = Booking.objects.filter(room=room, start_time__date=check_date)
        total = bookings.count()
        if total > 0:
            completed  = bookings.filter(status='completed').count()
            no_show    = bookings.filter(status='no_show').count()
            cancelled  = bookings.filter(status='cancelled').count()

            # คำนวณ utilization จากชั่วโมงที่ถูกจอง
            booked_hours = sum(
                b.duration_hours() for b in bookings.filter(
                    status__in=['completed', 'approved']
                )
            )
            available_hours = 12  # 08:00-20:00
            utilization = min((booked_hours / available_hours) * 100, 100)

            RoomUsageStat.objects.update_or_create(
                room=room, date=check_date,
                defaults={
                    'total_bookings':   total,
                    'completed':        completed,
                    'no_show':          no_show,
                    'cancelled':        cancelled,
                    'utilization_rate': round(utilization, 1),
                }
            )
            stats_created += 1
        check_date += timedelta(days=1)

print(f"  ✅ สร้างสถิติ {stats_created} รายการ")

# ============================================================
# สรุป
# ============================================================
print("\n" + "="*50)
print("✅ Seed เสร็จสมบูรณ์!")
print(f"  🏢 อาคาร:        {Building.objects.count()} รายการ")
print(f"  🚪 ห้อง:         {Room.objects.count()} รายการ")
print(f"  👤 ผู้ใช้:        {User.objects.filter(is_superuser=False).count()} รายการ")
print(f"  📅 การจอง:       {Booking.objects.count()} รายการ")
print(f"  📊 สถิติรายวัน:  {RoomUsageStat.objects.count()} รายการ")
print("="*50)
print("\n💡 วิธีใช้ข้อมูลเทรน LSTM:")
print("   python manage.py shell")
print("   >>> from booking.models import Booking")
print("   >>> qs = Booking.objects.filter(status__in=['completed','no_show'])")
print(f"   >>> print(qs.count(), 'records ready for training')")
if __name__ == '__main__':
    main()
