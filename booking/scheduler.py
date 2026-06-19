from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from datetime import timedelta
import subprocess
import sys


def retrain_model():
    print("🔁 Retraining AI model...")
    subprocess.run([sys.executable, "ml/saved/forecast.py", "--retrain"])


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
        if not user_email:
            continue

        checkin_url = f'{SITE_URL}/api/bookings/{booking.id}/checkin/{booking.checkin_token}/'
        cancel_url  = f'{SITE_URL}/api/bookings/{booking.id}/cancel-email/{booking.checkin_token}/'

        try:
            send_mail(
                subject=f'⏰ อีก 15 นาที! กรุณา Check-in ห้อง {booking.room.name}',
                message=f'กรุณากด Check-in ที่: {checkin_url}',
                from_email='nookkup47@gmail.com',
                recipient_list=[user_email],
                html_message=f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <div style="background:#d97706;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">⏰ อีก 15 นาที ก็ถึงเวลาแล้ว!</h1>
      <p style="color:#fef3c7;margin:8px 0 0;">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</p>
    </div>
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{booking.user.get_full_name() or booking.user.username}</b>
      </p>
      <p style="color:#6b7280;">ใกล้ถึงเวลาการจองของคุณแล้ว อย่าลืม Check-in นะครับ!</p>

      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;">
        <tr style="background:#fffbeb;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;">{booking.room.name}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;">{booking.room.building.name}</td>
        </tr>
        <tr style="background:#fffbeb;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;">{booking.title}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">⏰ เวลา</td>
          <td style="padding:10px 12px;">
            {booking.start_time.strftime("%H:%M")} – {booking.end_time.strftime("%H:%M")} น.
          </td>
        </tr>
      </table>

      <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:20px;margin:24px 0;text-align:center;">
        <p style="margin:0 0 16px;font-size:15px;color:#15803d;font-weight:bold;">
          กด Check-in ได้เลยตอนนี้!
        </p>
        <a href="{checkin_url}"
           style="display:inline-block;background:#16a34a;color:white;
                  padding:14px 36px;text-decoration:none;border-radius:8px;
                  font-size:16px;font-weight:bold;">
          ✅ กด Check-in ที่นี่
        </a>
      </div>

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
        ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี
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


def mark_no_show():
    """เลยเวลาสิ้นสุดแล้วยังไม่ได้ check-in → เปลี่ยนเป็น no_show และส่ง email แจ้ง"""
    from booking.models import Booking, BookingLog
    from django.core.mail import send_mail
    from django.conf import settings
    import pytz

    now      = timezone.now()
    THAI_TZ  = pytz.timezone('Asia/Bangkok')
    SITE_URL = getattr(settings, 'SITE_URL', 'http://localhost:8000')

    bookings = Booking.objects.filter(
        status='approved',
        checked_in=False,
        end_time__lt=now,  # เลยเวลาสิ้นสุดแล้ว
    ).select_related('user', 'room__building')

    for booking in bookings:
        old_status     = booking.status
        booking.status = 'no_show'
        booking.save()

        BookingLog.objects.create(
            booking=booking,
            changed_by=booking.user,
            old_status=old_status,
            new_status='no_show',
        )
        print(f'⚠️ No-show: {booking.user.username} → {booking.room.name}')

        # ส่ง email แจ้งเตือน no-show
        user_email = booking.user.email
        if not user_email:
            continue

        start_thai = booking.start_time.astimezone(THAI_TZ)
        end_thai   = booking.end_time.astimezone(THAI_TZ)
        new_url    = f'{SITE_URL}'

        try:
            send_mail(
                subject=f'⚠️ บันทึกการไม่มาใช้งานห้อง {booking.room.name}',
                message=f'การจองห้อง {booking.room.name} ของคุณถูกบันทึกว่าไม่มาใช้งาน',
                from_email='nookkup47@gmail.com',
                recipient_list=[user_email],
                html_message=f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <div style="background:#7c3aed;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">⚠️ บันทึกการไม่มาใช้งาน</h1>
      <p style="color:#ede9fe;margin:8px 0 0;">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</p>
    </div>
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{booking.user.get_full_name() or booking.user.username}</b>
      </p>
      <p style="color:#6b7280;">
        ระบบได้บันทึกว่าการจองของคุณ <b>ไม่มีการ Check-in</b> ภายในเวลาที่กำหนด
      </p>

      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;">
        <tr style="background:#f5f3ff;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;">{booking.room.name}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;">{booking.room.building.name}</td>
        </tr>
        <tr style="background:#f5f3ff;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;">{booking.title}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">📅 วันที่</td>
          <td style="padding:10px 12px;">{start_thai.strftime("%d/%m/%Y")}</td>
        </tr>
        <tr style="background:#f5f3ff;">
          <td style="padding:10px 12px;color:#6b7280;">⏰ เวลา</td>
          <td style="padding:10px 12px;">
            {start_thai.strftime("%H:%M")} – {end_thai.strftime("%H:%M")} น.
          </td>
        </tr>
      </table>

      <div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:16px;margin:24px 0;">
        <p style="margin:0;font-size:14px;color:#92400e;">
          💡 หากต้องการจองใหม่ สามารถเข้าระบบได้เลยครับ
          กรุณา Check-in ทุกครั้งที่มาใช้งานเพื่อให้ระบบบันทึกการใช้งานได้อย่างถูกต้อง
        </p>
      </div>

      <div style="text-align:center;margin:16px 0;">
        <a href="{new_url}"
           style="display:inline-block;background:#1d4ed8;color:white;
                  padding:12px 28px;text-decoration:none;border-radius:8px;
                  font-size:15px;font-weight:bold;">
          🔗 จองห้องใหม่
        </a>
      </div>
    </div>

    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>
  </div>
</body>
</html>
                ''',
                fail_silently=True,
            )
            print(f'📧 ส่ง email no-show: {booking.user.username}')

        except Exception as e:
            print(f'❌ ส่ง email no-show ไม่สำเร็จ: {e}')


def start():
    scheduler = BackgroundScheduler()

    # เทรน AI ทุกวันตี 3
    scheduler.add_job(retrain_model, 'cron', hour=3)

    # แจ้งเตือน Check-in ก่อน 15 นาที (เช็คทุก 1 นาที)
    scheduler.add_job(send_checkin_reminders, 'interval', minutes=1)

    # เช็ค no-show ทุก 5 นาที
    scheduler.add_job(mark_no_show, 'interval', minutes=5)

    scheduler.start()