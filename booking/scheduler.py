import os
import sys
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from django.utils.html import escape


def send_checkin_reminders():
    """แจ้งเตือนให้ Check-in ก่อนเวลาเริ่ม 15 นาที"""
    from booking.models import Booking
    from django.core.mail import send_mail
    from django.conf import settings

    now          = timezone.now()
    window_start = now + timedelta(minutes=14)
    window_end   = now + timedelta(minutes=16)

    bookings = Booking.objects.filter(
        status='approved',
        checked_in=False,
        reminded=False,
        start_time__gte=window_start,
        start_time__lte=window_end,
    ).select_related('user', 'room__building')

    SITE_URL = getattr(settings, 'SITE_URL', 'http://localhost:8000')

    for booking in bookings:
        user_email = booking.user.email
        # start_time จาก DB เป็น UTC — เดิม strftime ตรง ๆ อีเมลเตือนจึงบอกเวลา
        # ช้าไป 7 ชั่วโมง (จอง 10:00 อีเมลบอก 03:00)
        start_local = timezone.localtime(booking.start_time)
        end_local   = timezone.localtime(booking.end_time)
        # ข้อความที่ผู้ใช้พิมพ์เองต้อง escape ก่อนใส่ HTML
        name_html     = escape(booking.user.get_full_name() or booking.user.username)
        room_html     = escape(booking.room.name)
        building_html = escape(booking.room.building.name)
        title_html    = escape(booking.title)
        if not user_email:
            continue

        cancel_url = f'{SITE_URL}/api/bookings/{booking.id}/cancel-email/{booking.checkin_token}/'

        try:
            send_mail(
                subject=f'⏰ อีก 15 นาที! ถึงเวลาใช้ห้อง {booking.room.name}',
                message=f'ไม่สามารถมาใช้งานได้? กดยกเลิกที่: {cancel_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user_email],
                html_message=f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <div style="background:#d97706;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">⏰ อีก 15 นาที ก็ถึงเวลาแล้ว!</h1>
      <p style="color:#fef3c7;margin:8px 0 0;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
    </div>
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{name_html}</b>
      </p>
      <p style="color:#6b7280;">ใกล้ถึงเวลาการจองของคุณแล้ว</p>

      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;">
        <tr style="background:#fffbeb;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;">{room_html}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;">{building_html}</td>
        </tr>
        <tr style="background:#fffbeb;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;">{title_html}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">⏰ เวลา</td>
          <td style="padding:10px 12px;">
            {start_local.strftime("%H:%M")} – {end_local.strftime("%H:%M")} น.
          </td>
        </tr>
      </table>

      <div style="background:#fff5f5;border:1px solid #fca5a5;border-radius:10px;padding:16px;text-align:center;">
        <p style="margin:0 0 12px;font-size:14px;color:#6b7280;">ไม่สามารถมาใช้งานได้?</p>
        <a href="{cancel_url}"
           style="display:inline-block;background:#dc2626;color:white;
                  padding:10px 28px;text-decoration:none;border-radius:8px;
                  font-size:14px;font-weight:bold;">
          ❌ ยกเลิกการจอง
        </a>
      </div>
    </div>

    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>
  </div>
</body>
</html>
                ''',
                fail_silently=True,
            )

            booking.reminded = True
            booking.save(update_fields=['reminded'])
            print(f'✅ ส่งแจ้งเตือน Check-in: {booking.user.username} → {booking.room.name}')

        except Exception as e:
            print(f'❌ ส่งแจ้งเตือนไม่สำเร็จ: {e}')


def start():
    # Avoid starting background jobs in ad-hoc management commands / scripts.
    # This prevents executor shutdown noise when forecast.py or shell imports Django.
    if os.environ.get('DISABLE_DJANGO_SCHEDULER') == '1':
        return

    argv = ' '.join(sys.argv).lower()
    # daphne คือเซิร์ฟเวอร์ที่ใช้จริงบน Render (render.yaml) — เดิมไม่อยู่ในรายการนี้
    # งานเตือนเช็คอินจึงไม่เคยเริ่มทำงานบน production
    server_mode = (
        any(name in argv for name in ('runserver', 'gunicorn', 'uvicorn', 'daphne'))
        or os.environ.get('RUN_MAIN') == 'true'
    )
    if not server_mode:
        return

    scheduler = BackgroundScheduler()

    # แจ้งเตือน Check-in ก่อน 15 นาที (เช็คทุก 1 นาที)
    scheduler.add_job(send_checkin_reminders, 'interval', minutes=1)

    scheduler.start()
