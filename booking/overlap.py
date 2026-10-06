"""ตรวจการชนกันของการจองรายวัน — ใช้ร่วมกันระหว่าง serializer (ตรวจเบื้องต้น
เพื่อ UX) กับ BookingViewSet.perform_create / perform_update (ตรวจซ้ำภายใต้
select_for_update เพื่อกัน race condition)

เดิมตรรกะนี้ถูกคัดลอกไว้สองที่และตรวจจองทั้งเทอมจากวันของ start_time วันเดียว
ทำให้การจองข้ามเที่ยงคืนทับคาบเรียนของวันถัดไปได้ ตอนนี้ไล่ทุกวันในช่วงผ่าน
recurring_slot_conflicts แทน
"""
from datetime import time as time_type, timedelta

from django.utils import timezone

from .models import Booking, MaintenanceBlock, TermBooking

ACTIVE_BOOKING_STATUSES = ['pending', 'approved', 'checked_in']
# คาบทั้งเทอมที่รออนุมัติกันช่วงเวลาไว้ด้วย เหมือน pending ของการจองรายครั้ง —
# ไม่นับ สองคำขอที่ทับกันจะเข้าไปรออนุมัติพร้อมกันได้
TERM_BLOCKING_STATUSES = ['pending', 'active']


def recurring_slot_conflicts(local_start, local_end, day_of_week, start_time, end_time, term_start, term_end):
    """
    เช็คว่าเหตุการณ์ครั้งเดียว (Booking/MaintenanceBlock ที่มี start/end เป็น
    datetime จริง) ชนกับ slot รายสัปดาห์ของ TermBooking (day_of_week +
    start_time/end_time ซ้ำทุกสัปดาห์ตลอด [term_start, term_end]) ไหม

    ตัดเหตุการณ์เป็นท่อนรายวันแล้วเทียบเวลาจริงของแต่ละวัน — เดิมเหตุการณ์ข้ามวัน
    ถือว่าชนทั้งวันถัดไป จอง 22:00–02:00 วันจันทร์ (หรือ 20:00–24:00) จึงโดน
    ปฏิเสธเพราะคาบ 10:00 วันอังคาร ทั้งที่ไม่ได้ทับกันจริง
    """
    cur = local_start.date()
    last = local_end.date()
    while cur <= last:
        # ท่อนของเหตุการณ์ที่ตกอยู่ในวัน cur (None = สุดวัน 24:00)
        seg_start = local_start.time() if cur == local_start.date() else time_type(0, 0)
        seg_end = local_end.time() if cur == last else None
        empty = seg_end == time_type(0, 0)  # จบเที่ยงคืนพอดี ไม่มีท่อนในวันสุดท้าย
        if (not empty and term_start <= cur <= term_end and cur.weekday() == day_of_week
                and seg_start < end_time and (seg_end is None or seg_end > start_time)):
            return True
        cur += timedelta(days=1)
    return False


def find_booking_conflict(room, start_time, end_time, exclude_pk=None, exclude_maintenance_pk=None):
    """คืน (ชนิด, ข้อความ) ของสิ่งแรกที่ชน หรือ None ถ้าว่าง

    ชนิดเป็น 'booking' / 'term' / 'maintenance' ให้ผู้เรียกเลือกข้อความเองได้
    exclude_pk = Booking ที่กำลังแก้, exclude_maintenance_pk = ช่วงปิดซ่อมที่กำลังแก้
    """
    dynamic = Booking.objects.filter(
        room=room,
        status__in=ACTIVE_BOOKING_STATUSES,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude_pk is not None:
        dynamic = dynamic.exclude(pk=exclude_pk)
    if dynamic.exists():
        return 'booking', 'ห้องนี้ถูกจองในช่วงเวลาดังกล่าวแล้ว'

    local_start = timezone.localtime(start_time)
    local_end = timezone.localtime(end_time)
    for tb in TermBooking.objects.filter(
        room=room,
        status__in=TERM_BLOCKING_STATUSES,
        term_start__lte=local_end.date(),
        term_end__gte=local_start.date(),
    ):
        if recurring_slot_conflicts(local_start, local_end, tb.day_of_week,
                                    tb.start_time, tb.end_time, tb.term_start, tb.term_end):
            return 'term', (f'ห้องนี้ถูกจองทั้งเทอมโดย "{tb.subject_name}" '
                            f'({tb.start_time:%H:%M}–{tb.end_time:%H:%M})')

    maintenance = MaintenanceBlock.objects.filter(
        room=room,
        status__in=['scheduled', 'active'],
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude_maintenance_pk is not None:
        maintenance = maintenance.exclude(pk=exclude_maintenance_pk)
    if maintenance.exists():
        return 'maintenance', 'ห้องนี้ปิดซ่อมบำรุงอยู่ในช่วงเวลาดังกล่าว'

    return None


def find_term_conflict(room, day_of_week, start_time, end_time, term_start, term_end, exclude_pk=None):
    """ข้อความของสิ่งแรกที่ชนกับคาบเรียนรายสัปดาห์ที่จะจอง หรือ None ถ้าว่าง

    ตรวจ 3 แหล่งเหมือนการจองรายครั้ง: คาบทั้งเทอมอื่น, การจองรายครั้ง และ
    ช่วงปิดซ่อม (สองอย่างหลังไล่ทุกสัปดาห์ในช่วงเทอมผ่าน recurring_slot_conflicts)
    exclude_pk ใช้ตอนแก้ไข/เปิดคาบเดิมกลับมา ไม่ให้นับตัวเองว่าชน

    ตรวจเฉพาะสัปดาห์ตั้งแต่วันนี้ไป — เทอมที่เริ่มไปแล้ว (จองกลางเทอม) เดิมโดนการ
    จองเก่าในสัปดาห์ที่ผ่านไปแล้วบล็อกทั้งเทอม ทั้งที่ช่วงนั้นไม่มีผลอะไรแล้ว
    """
    term_start = max(term_start, timezone.localdate())
    if term_start > term_end:
        return None
    terms = TermBooking.objects.filter(
        room=room,
        day_of_week=day_of_week,
        status__in=TERM_BLOCKING_STATUSES,
        term_start__lte=term_end,
        term_end__gte=term_start,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude_pk is not None:
        terms = terms.exclude(pk=exclude_pk)
    if terms.exists():
        return 'ห้องนี้มีการจองทั้งเทอมซ้อนในช่วงเวลาเดียวกันแล้ว'

    def recurring_hit(event):
        return recurring_slot_conflicts(
            timezone.localtime(event.start_time), timezone.localtime(event.end_time),
            day_of_week, start_time, end_time, term_start, term_end,
        )

    for b in Booking.objects.filter(
        room=room,
        status__in=ACTIVE_BOOKING_STATUSES,
        start_time__date__lte=term_end,
        end_time__date__gte=term_start,
    ):
        if recurring_hit(b):
            return f'ห้องนี้มีการจองรายวัน "{b.title}" ซ้อนกับวันและเวลาที่เลือกในบางสัปดาห์'

    for mb in MaintenanceBlock.objects.filter(
        room=room,
        status__in=['scheduled', 'active'],
        start_time__date__lte=term_end,
        end_time__date__gte=term_start,
    ):
        if recurring_hit(mb):
            return 'ห้องนี้ปิดซ่อมบำรุงซ้อนกับวันและเวลาที่เลือกในบางสัปดาห์'

    return None
