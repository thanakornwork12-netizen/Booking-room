"""
นำเข้าข้อมูลจริงจากไฟล์ Excel ในโฟลเดอร์ ml
รองรับทั้งชื่อใหม่และชื่อเก่า:
  - รวมข้อมูลห้องและประวัติการใช้งาน_ฉบับสมบูรณ์.xlsx
  - รวมข้อมูลห้องและประวัติการใช้งาน.xlsx
→ Building, Room, Facility, RoomFacility, Booking

วิธีใช้:
  python ml/import_real_data.py              # import ทั้งหมด
  python ml/import_real_data.py --clear      # ล้างข้อมูล mock ก่อน import
"""

import os
import re
import sys
import argparse

import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()

from django.utils import timezone
from booking.models import (
    User, Building, Room, Facility, RoomFacility,
    Booking, TermBooking, DemandForecast, BookingLog,
)

EXCEL_CANDIDATES = [
    'รวมข้อมูลห้องและประวัติการใช้งาน_ฉบับสมบูรณ์.xlsx',
    'รวมข้อมูลห้องและประวัติการใช้งาน.xlsx',
]
EXCEL_PATH = None
for fname in EXCEL_CANDIDATES:
    candidate = os.path.join(BASE_DIR, 'ml', fname)
    if os.path.exists(candidate):
        EXCEL_PATH = candidate
        break

BUILDING_CODE = 'ODL'
BUILDING_NAME = 'อาคาร ODL (Online Digital Learning)'

ROOMS_SHEET_CANDIDATES = ['ข้อมูลห้องทั้งหมด', 'ข้อมูลห้อง ODL1 (เดิม)', 'ข้อมูลห้อง ODL1', 'Sheet1']
BOOKINGS_SHEET_CANDIDATES = ['ประวัติการใช้งาน', 'History', 'Sheet2']


def normalize_code(raw: str) -> str:
    """2C 05-06 → 2C05-06, ODL1_2C09 → 2C09"""
    if not raw or pd.isna(raw):
        return ''
    s = str(raw).strip()
    m = re.match(r'ODL1_([^:]+)', s)
    if m:
        s = m.group(1).strip()
    if 'Meeting' in s or 'ห้องประชุม' in s:
        return '1C-MEETING'
    s = re.sub(r'\s*\(iMac\)\s*', '', s, flags=re.I)
    s = re.sub(r'\s+', '', s)
    return s.upper()


def _load_sheet_by_name(sheet_names, header=None):
    xls = pd.ExcelFile(EXCEL_PATH)
    for name in sheet_names:
        if name in xls.sheet_names:
            return pd.read_excel(xls, sheet_name=name, header=header)
    return pd.read_excel(xls, sheet_name=0, header=header)


def parse_capacity(cap_str) -> int:
    if pd.isna(cap_str):
        return 30
    m = re.search(r'(\d+)', str(cap_str))
    return int(m.group(1)) if m else 30


def parse_room_specs(df) -> list[dict]:
    """อ่านส่วนที่ 1: ข้อมูลห้องจาก sheet ODL1 format ใหม่"""
    rooms = []
    header_row = None
    # หา header row โดยตรวจดูทุกคอลัมน์ เพื่อรองรับ sheet ที่มี header ไม่ได้อยู่คอลัมน์แรก
    keywords = ['รหัสห้อง', 'รหัส', 'room', 'code']
    for i in range(len(df)):
        for j in range(df.shape[1]):
            try:
                val = str(df.iloc[i, j]).strip()
            except Exception:
                continue
            low = val.lower()
            if any(kw in low for kw in keywords):
                header_row = i
                break
        if header_row is not None:
            break
    if header_row is None:
        return rooms
    # Determine whether header row contains named columns (e.g., 'อาคาร')
    headers = [str(x).strip() for x in df.iloc[header_row].values]
    header_map = {h: idx for idx, h in enumerate(headers) if h}

    def find_idx(names, fallback=None):
        for n in names:
            for h, idx in header_map.items():
                if n.lower() in h.lower():
                    return idx
        return fallback

    code_idx = find_idx(['รหัสห้อง', 'room code', 'code'], fallback=0)
    building_idx = find_idx(['อาคาร', 'building', 'ตึก'], fallback=None)
    capacity_idx = find_idx(['ความจุ', 'จุ', 'capacity'], fallback=8)
    extra_idx = find_idx(['อุปกรณ์', 'equipment', 'extra'], fallback=7)
    status_idx = find_idx(['สถานะ', 'status'], fallback=9)
    floor_idx = find_idx(['ชั้น', 'floor'], fallback=1)
    type_idx = find_idx(['ประเภท', 'room type', 'room_type'], fallback=2)
    pc_idx = find_idx(['pc', 'คอมพิวเตอร์', 'จำนวนคอมพิวเตอร์'], fallback=3)

    # If code_idx is still the fallback (0) but that column looks like 'building',
    # try to auto-detect the column that contains room codes by sampling rows.
    if code_idx == 0:
        best_j = None
        best_count = 0
        sample_rows = range(header_row + 1, min(len(df), header_row + 50))
        for j in range(df.shape[1]):
            count = 0
            for i in sample_rows:
                try:
                    v = df.iloc[i, j]
                except Exception:
                    continue
                if pd.isna(v):
                    continue
                if normalize_code(str(v)):
                    count += 1
            if count > best_count:
                best_count = count
                best_j = j
        if best_j is not None and best_count > 0:
            code_idx = best_j

    for i in range(header_row + 1, len(df)):
        row = df.iloc[i]
        code_raw = row[code_idx] if code_idx is not None and code_idx < len(row) else row[0]
        if pd.isna(code_raw):
            continue
        if isinstance(code_raw, str) and code_raw.strip().startswith('📌'):
            break
        code = normalize_code(str(code_raw))
        if not code:
            continue

        # building info (if present)
        building_raw = None
        if building_idx is not None and building_idx < len(row):
            building_raw = row[building_idx]
        if pd.isna(building_raw) or not building_raw:
            building_code = BUILDING_CODE
            building_name = BUILDING_NAME
        else:
            bname = str(building_raw).strip()
            building_name = bname
            building_code = re.sub(r"\s+", '', bname).upper()[:10]

        cap = parse_capacity(row[capacity_idx] if capacity_idx is not None and capacity_idx < len(row) else None)
        extra = str(row[extra_idx]) if extra_idx is not None and extra_idx < len(row) and pd.notna(row[extra_idx]) else ''
        status_value = str(row[status_idx]).strip() if status_idx is not None and status_idx < len(row) and pd.notna(row[status_idx]) else ''
        floor_val = int(row[floor_idx]) if floor_idx is not None and floor_idx < len(row) and pd.notna(row[floor_idx]) and str(row[floor_idx]).isdigit() else 1
        room_type = str(row[type_idx]) if type_idx is not None and type_idx < len(row) and pd.notna(row[type_idx]) else 'ห้องปฏิบัติการ'
        pc_count = int(row[pc_idx]) if pc_idx is not None and pc_idx < len(row) and pd.notna(row[pc_idx]) and str(row[pc_idx]).isdigit() else 0

        rooms.append({
            'code': code,
            'name': str(code_raw).strip(),
            'floor': floor_val,
            'room_type': room_type,
            'pc_count': pc_count,
            'cpu': '',
            'ram': '',
            'storage': '',
            'extra_equipment': extra,
            'capacity': cap,
            'status': 'disabled' if 'งดจอง' in status_value or 'ไม่' in status_value else 'available',
            'building_code': building_code,
            'building_name': building_name,
        })
    return rooms


def parse_bookings(df) -> pd.DataFrame:
    """อ่านประวัติการใช้งานจาก sheet ประวัติการใช้งาน"""
    rows = []
    header_row = None
    for i in range(len(df)):
        if str(df.iloc[i, 0]).strip() == 'ลำดับ':
            header_row = i
            break
    if header_row is None:
        return pd.DataFrame(rows)

    for i in range(header_row + 1, len(df)):
        row = df.iloc[i]
        room_cell = row[1]
        if pd.isna(room_cell):
            continue
        start = pd.to_datetime(row[2])
        end = pd.to_datetime(row[3])
        if pd.isna(start) or pd.isna(end):
            continue
        code = normalize_code(str(room_cell))
        if not code:
            continue
        cap_m = re.search(r'\((\d+)\s*ที่นั่ง\)', str(room_cell))
        capacity = int(cap_m.group(1)) if cap_m else None
        rows.append({
            'code': code,
            'start': start,
            'end': end,
            'capacity_hint': capacity,
            'room_label': str(room_cell),
        })
    return pd.DataFrame(rows)


def facility_names_from_room(spec: dict) -> list[str]:
    """แปลงข้อมูลอุปกรณ์จริงจาก Excel เป็นชื่อ Facility"""
    names = []
    if spec.get('pc_count', 0) > 0:
        names.append(f'คอมพิวเตอร์ {spec["pc_count"]} เครื่อง')
    if spec.get('cpu'):
        names.append(f'CPU: {spec["cpu"]}')
    if spec.get('ram'):
        names.append(f'RAM: {spec["ram"]}')
    if spec.get('storage'):
        names.append(f'Storage: {spec["storage"]}')
    extra = spec.get('extra_equipment', '')
    if extra:
        for part in re.split(r'[,،]', extra):
            part = part.strip()
            if part:
                names.append(part)
    # แปลงภาษาอังกฤษทั่วไปเป็นภาษาไทย
    mapping = {
        'Projector': 'โปรเจกเตอร์',
        'Interactive Projector': 'โปรเจกเตอร์อินเทอร์แอคทีฟ',
        'Flipboard': 'Flipboard',
        'Video Conference': 'ระบบ Video Conference',
        'ไมโครโฟน': 'ไมโครโฟน',
        'เครื่องเสียง': 'ระบบเสียง',
    }
    result = []
    for n in names:
        for eng, th in mapping.items():
            if eng.lower() in n.lower():
                n = n.replace(eng, th)
        result.append(n)
    return list(dict.fromkeys(result))  # unique, preserve order


def import_all(clear_mock: bool = False):
    if not os.path.exists(EXCEL_PATH):
        print(f'❌ ไม่พบไฟล์: {EXCEL_PATH}')
        return False

    print(f'📂 อ่านไฟล์: {EXCEL_PATH}')
    room_df = _load_sheet_by_name(ROOMS_SHEET_CANDIDATES, header=None)
    booking_df = _load_sheet_by_name(BOOKINGS_SHEET_CANDIDATES, header=None)
    room_specs = parse_room_specs(room_df)
    bookings_df = parse_bookings(booking_df)
    print(f'   ห้องจาก Excel: {len(room_specs)} ห้อง')
    print(f'   ประวัติการจอง: {len(bookings_df):,} รายการ')

    if clear_mock:
        print('🧹 ล้างข้อมูล mock เก่า...')
        from django.db import connection
        # ใช้ raw SQL เพื่อหลีกเลี่ยง SQLite "too many SQL variables" เมื่อมี ~500k rows
        tables = [
            'booking_notification',
            'booking_roomusagestat',
            'booking_demandforecast',
            'booking_bookinglog',
            'booking_booking',
            'booking_termbooking',
            'booking_roomfacility',
            'booking_maintenanceblock',
            'booking_room',
        ]
        with connection.cursor() as cur:
            cur.execute('PRAGMA foreign_keys=OFF')
            for tbl in tables:
                try:
                    cur.execute(f'DELETE FROM {tbl}')
                except Exception:
                    pass
            cur.execute('PRAGMA foreign_keys=ON')
        # ล้างอาคารเดิมทั้งหมดก่อน นำเข้าจาก Excel ใหม่ทั้งหมด
        Building.objects.all().delete()
        # ลบมาสเตอร์อุปกรณ์ mock ที่ไม่ได้ผูกกับห้องแล้ว
        Facility.objects.filter(roomfacility__isnull=True).delete()
        print('   ล้างข้อมูลเสร็จ')

    # สร้าง admin user สำหรับ booking ประวัติ
    system_user, _ = User.objects.get_or_create(
        username='system_import',
        defaults={
            'role': 'admin',
            'first_name': 'ระบบ',
            'last_name': 'นำเข้าข้อมูล',
            'is_staff': True,
        },
    )

    # Prepare buildings map (create building records per building_code)
    buildings_map = {}
    default_building, _ = Building.objects.get_or_create(
        code=BUILDING_CODE,
        defaults={'name': BUILDING_NAME, 'description': 'ข้อมูลจริงจากมหาวิทยาลัย'},
    )
    buildings_map[BUILDING_CODE] = default_building

    # create buildings from specs
    for spec in room_specs:
        bcode = spec.get('building_code', BUILDING_CODE)
        bname = spec.get('building_name', BUILDING_NAME)
        if bcode not in buildings_map:
            b, _ = Building.objects.get_or_create(
                code=bcode,
                defaults={'name': bname, 'description': 'ข้อมูลจริงจากมหาวิทยาลัย'},
            )
            buildings_map[bcode] = b

    code_to_room = {}
    spec_by_code = {r['code']: r for r in room_specs}

    # สร้างห้องจาก spec
    for spec in room_specs:
        building_for_room = buildings_map.get(spec.get('building_code'), default_building)
        room, created = Room.objects.update_or_create(
            building=building_for_room,
            name=spec['code'],
            defaults={
                'floor': spec['floor'],
                'capacity': spec['capacity'],
                'room_type': spec['room_type'],
                'status': spec['status'],
                'description': (
                    f"{spec['name']} | {spec['room_type']} | "
                    f"PC {spec['pc_count']} เครื่อง"
                ),
                'is_active': spec['status'] != 'disabled',
            },
        )
        code_to_room[spec['code']] = room
        action = 'สร้าง' if created else 'อัปเดต'
        print(f'   🚪 {action}: {spec["code"]} (จุ {spec["capacity"]})')

        # อุปกรณ์จริงจาก Excel
        RoomFacility.objects.filter(room=room).delete()
        for fac_name in facility_names_from_room(spec):
            fac, _ = Facility.objects.get_or_create(name=fac_name)
            RoomFacility.objects.create(room=room, facility=fac, quantity=1)

    # สร้างห้องที่มีใน booking แต่ไม่มีใน spec (เช่น 3C16-17)
    booking_codes = bookings_df['code'].unique()
    for code in booking_codes:
        if code in code_to_room:
            continue
        sub = bookings_df[bookings_df['code'] == code]
        cap = sub['capacity_hint'].dropna().iloc[0] if sub['capacity_hint'].notna().any() else 50
        label = sub['room_label'].iloc[0]
        room, created = Room.objects.update_or_create(
            building=default_building,
            name=code,
            defaults={
                'floor': int(code[0]) if code and code[0].isdigit() else 2,
                'capacity': int(cap),
                'room_type': 'ห้องปฏิบัติการคอมพิวเตอร์',
                'status': 'available',
                'description': str(label),
                'is_active': True,
            },
        )
        code_to_room[code] = room
        if created:
            print(f'   🚪 สร้างจากประวัติ: {code} (จุ {cap})')

    # นำเข้า bookings
    print('📅 นำเข้าประวัติการจอง...')
    batch = []
    skipped = 0
    for _, row in bookings_df.iterrows():
        room = code_to_room.get(row['code'])
        if not room:
            skipped += 1
            continue
        start = timezone.make_aware(row['start'].to_pydatetime()) if row['start'].tzinfo is None else row['start']
        end = timezone.make_aware(row['end'].to_pydatetime()) if row['end'].tzinfo is None else row['end']
        batch.append(Booking(
            user=system_user,
            room=room,
            title=f'การใช้งานจริง ({row["code"]})',
            attendees=min(
                room.capacity,
                int(row['capacity_hint']) if pd.notna(row['capacity_hint']) else room.capacity,
            ),
            start_time=start,
            end_time=end,
            status='completed',
        ))
        if len(batch) >= 2000:
            Booking.objects.bulk_create(batch, ignore_conflicts=True)
            batch = []

    if batch:
        Booking.objects.bulk_create(batch, ignore_conflicts=True)

    total_buildings = Building.objects.count()
    total_rooms = Room.objects.count()
    total_bookings = Booking.objects.count()
    total_fac = RoomFacility.objects.count()

    print('\n✅ นำเข้าเสร็จสิ้น')
    print(f'   อาคาร: {total_buildings} อาคาร')
    print(f'   ห้อง: {total_rooms} ห้อง')
    print(f'   การจอง: {total_bookings:,} รายการ')
    print(f'   อุปกรณ์ในห้อง: {total_fac} รายการ')
    if skipped:
        print(f'   ⚠️ ข้ามการจอง (ไม่มีห้อง): {skipped}')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--clear', action='store_true', help='ล้างข้อมูล mock ก่อน import')
    args = parser.parse_args()
    ok = import_all(clear_mock=args.clear)
    sys.exit(0 if ok else 1)
