"""ตรวจการชนกันของการจองรายวัน — ใช้ร่วมกันระหว่าง serializer (ตรวจเบื้องต้น
เพื่อ UX) กับ BookingViewSet.perform_create / perform_update (ตรวจซ้ำภายใต้
select_for_update เพื่อกัน race condition)

เดิมตรรกะนี้ถูกคัดลอกไว้สองที่และตรวจจองทั้งเทอมจากวันของ start_time วันเดียว
ทำให้การจองข้ามเที่ยงคืนทับคาบเรียนของวันถัดไปได้ ตอนนี้ไล่ทุกวันในช่วงผ่าน
recurring_slot_conflicts แทน
"""
from datetime import timedelta

from django.utils import timezone

from .models import Booking, MaintenanceBlock, TermBooking

ACTIVE_BOOKING_STATUSES = ['pending', 'approved', 'checked_in']


def recurring_slot_conflicts(local_start, local_end, day_of_week, start_time, end_time, term_start, term_end):
    """
    เช็คว่าเหตุการณ์ครั้งเดียว (Booking/MaintenanceBlock ที่มี start/end เป็น
    datetime จริง) ชนกับ slot รายสัปดาห์ของ TermBooking (day_of_week +
    start_time/end_time ซ้ำทุกสัปดาห์ตลอด [term_start, term_end]) ไหม
    """
    if local_start.date() == local_end.date():
        d = local_start.date()
        if not (term_start <= d <= term_end):
            return False
        if d.weekday() != day_of_week:
            return False
        return local_start.time() < end_time and local_end.time() > start_time
    # เหตุการณ์ข้ามวัน (เช่น ปิดซ่อมบำรุงยาวหลายวัน) — ถือว่าชนถ้ามีวันไหน
    # ในช่วงตรงกับ day_of_week และอยู่ในช่วงเทอม (ระมัดระวังไว้ก่อน ไม่เช็ค
    # เวลาละเอียดในกรณีนี้ เพราะห้องถูกกันทั้งวันอยู่แล้วในทางปฏิบัติ)
    cur = local_start.date()
    while cur <= local_end.date():
        if term_start <= cur <= term_end and cur.weekday() == day_of_week:
            return True
        cur += timedelta(days=1)
    return False


def find_booking_conflict(room, start_time, end_time, exclude_pk=None):
    """คืน (ชนิด, ข้อความ) ของสิ่งแรกที่ชน หรือ None ถ้าว่าง

    ชนิดเป็น 'booking' / 'term' / 'maintenance' ให้ผู้เรียกเลือกข้อความเองได้
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
        status='active',
        term_start__lte=local_end.date(),
        term_end__gte=local_start.date(),
    ):
        if recurring_slot_conflicts(local_start, local_end, tb.day_of_week,
                                    tb.start_time, tb.end_time, tb.term_start, tb.term_end):
            return 'term', (f'ห้องนี้ถูกจองทั้งเทอมโดย "{tb.subject_name}" '
                            f'({tb.start_time:%H:%M}–{tb.end_time:%H:%M})')

    if MaintenanceBlock.objects.filter(
        room=room,
        status__in=['scheduled', 'active'],
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).exists():
        return 'maintenance', 'ห้องนี้ปิดซ่อมบำรุงอยู่ในช่วงเวลาดังกล่าว'

    return None


def find_term_conflict(room, day_of_week, start_time, end_time, term_start, term_end, exclude_pk=None):
    """ข้อความของสิ่งแรกที่ชนกับคาบเรียนรายสัปดาห์ที่จะจอง หรือ None ถ้าว่าง

    ตรวจ 3 แหล่งเหมือนการจองรายครั้ง: คาบทั้งเทอมอื่น, การจองรายครั้ง และ
    ช่วงปิดซ่อม (สองอย่างหลังไล่ทุกสัปดาห์ในช่วงเทอมผ่าน recurring_slot_conflicts)
    exclude_pk ใช้ตอนแก้ไข/เปิดคาบเดิมกลับมา ไม่ให้นับตัวเองว่าชน
    """
    terms = TermBooking.objects.filter(
        room=room,
        day_of_week=day_of_week,
        status='active',
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
