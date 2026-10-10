"""สถานะห้องตามช่วงปิดซ่อม — ใช้ทั้งตอนแอดมินแก้/ปิดช่วงซ่อม (views) และงาน
เบื้องหลังที่รันทุกนาที (scheduler) ให้สถานะห้องตรงกับเวลาจริงเสมอ"""
from django.utils import timezone

from .models import MaintenanceBlock, Room

OPEN_STATUSES = ('scheduled', 'active')


def sync_room_status(room):
    """ตั้งสถานะห้องตามช่วงซ่อมที่ครอบ "ตอนนี้" — ห้องที่แอดมินปิดใช้งาน
    (disabled) คงไว้ตามเดิม ไม่ถูกเปิดกลับเพราะปิดงานซ่อม"""
    now = timezone.now()
    in_window = MaintenanceBlock.objects.filter(
        room=room, status__in=OPEN_STATUSES, start_time__lte=now, end_time__gt=now,
    ).exists()
    if in_window and room.status not in ('maintenance', 'disabled'):
        room.status = 'maintenance'
        room.save(update_fields=['status'])
    elif not in_window and room.status == 'maintenance':
        room.status = 'available'
        room.save(update_fields=['status'])


def refresh_maintenance():
    """ปิดช่วงซ่อมที่หมดเวลาแล้ว (เป็น completed) และตั้งสถานะห้องให้ตรงกับเวลาจริง

    เดิมไม่มีอะไรปิดช่วงซ่อมที่เลยเวลาเลย ห้องค้าง "ซ่อมบำรุง" ไปตลอดจนกว่าแอดมิน
    จะกดปิดงานเอง และช่วงซ่อมที่ตั้งล่วงหน้าพอถึงเวลาก็ไม่เปลี่ยนสถานะห้อง
    คืนจำนวนช่วงซ่อมที่ปิดให้"""
    now = timezone.now()
    finished = MaintenanceBlock.objects.filter(status__in=OPEN_STATUSES, end_time__lte=now)
    room_ids = set(finished.values_list('room_id', flat=True))
    closed = finished.update(status='completed')
    room_ids |= set(MaintenanceBlock.objects.filter(status__in=OPEN_STATUSES)
                    .values_list('room_id', flat=True))
    room_ids |= set(Room.objects.filter(status='maintenance').values_list('id', flat=True))
    for room in Room.objects.filter(id__in=room_ids):
        sync_room_status(room)
    return closed
