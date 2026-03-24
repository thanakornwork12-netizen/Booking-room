"""
auto_noshow.py — จัดการ booking อัตโนมัติ 3 กรณี
วางที่: booking/management/commands/auto_noshow.py
รัน manual: python manage.py auto_noshow
Cron ทุก 5 นาที: */5 * * * * cd /Users/macthanakorn/room_booking && tf-env/bin/python manage.py auto_noshow >> /tmp/noshow.log 2>&1
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from booking.models import Booking, Notification


class Command(BaseCommand):
    help = 'Auto manage bookings: remind 30min before, no-show 15min after, cancel pending 15min'

    def handle(self, *args, **options):
        now   = timezone.now()
        total = {'remind': 0, 'noshow': 0, 'cancel': 0}

        # ══════════════════════════════════════════════════════
        # CASE 1: แจ้งเตือนล่วงหน้า 30 นาทีก่อนเริ่ม
        # ══════════════════════════════════════════════════════
        upcoming = Booking.objects.filter(
            status='approved',
            start_time__gte=now + timedelta(minutes=25),
            start_time__lte=now + timedelta(minutes=35),
            reminded=False,
        ).select_related('user', 'room')

        for b in upcoming:
            Notification.objects.get_or_create(
                user=b.user,
                booking=b,
                type='booking_reminder',
                defaults=dict(
                    title='⏰ เตือน — ใกล้ถึงเวลาจอง',
                    message=(
                        f'อีก 30 นาที! "{b.title}" ห้อง {b.room.name} '
                        f'เวลา {b.start_time.strftime("%H:%M")} น. '
                        f'กรุณา Check-in ภายใน 15 นาทีหลังเวลาเริ่ม '
                        f'มิฉะนั้นระบบจะยกเลิกอัตโนมัติ'
                    ),
                )
            )
            b.reminded = True
            b.save(update_fields=['reminded'])
            total['remind'] += 1

        # ══════════════════════════════════════════════════════
        # CASE 2: No-Show — ไม่ check-in ภายใน 15 นาทีหลังเริ่ม
        # ══════════════════════════════════════════════════════
        late = Booking.objects.filter(
            status='approved',
            start_time__lte=now - timedelta(minutes=15),
            checked_in=False,
        ).select_related('user', 'room')

        for b in late:
            b.status = 'no_show'
            b.save(update_fields=['status'])
            Notification.objects.create(
                user=b.user,
                booking=b,
                type='system',
                title='❌ การจองถูกยกเลิกอัตโนมัติ',
                message=(
                    f'การจอง "{b.title}" ห้อง {b.room.name} '
                    f'เวลา {b.start_time.strftime("%H:%M")} น. '
                    f'ถูกยกเลิกเนื่องจากไม่มีการ Check-in ภายใน 15 นาที'
                ),
            )
            total['noshow'] += 1

        # ══════════════════════════════════════════════════════
        # CASE 3: ยกเลิก pending ที่ไม่ได้รับ approve ภายใน 15 นาที
        # ══════════════════════════════════════════════════════
        pending_old = Booking.objects.filter(
            status='pending',
            created_at__lte=now - timedelta(minutes=15),
        ).select_related('user', 'room')

        for b in pending_old:
            b.status = 'cancelled'
            b.save(update_fields=['status'])
            Notification.objects.create(
                user=b.user,
                booking=b,
                type='booking_rejected',
                title='🚫 การจองถูกยกเลิกอัตโนมัติ',
                message=(
                    f'การจอง "{b.title}" ห้อง {b.room.name} '
                    f'ถูกยกเลิกเนื่องจากไม่ได้รับการอนุมัติภายใน 15 นาที'
                ),
            )
            total['cancel'] += 1

        self.stdout.write(self.style.SUCCESS(
            f'✅ remind={total["remind"]} | '
            f'noshow={total["noshow"]} | '
            f'cancel_pending={total["cancel"]}'
        ))