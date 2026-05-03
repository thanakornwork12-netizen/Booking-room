# booking/signals.py
# ส่ง WebSocket Event อัตโนมัติทุกครั้งที่ Booking เปลี่ยนสถานะ

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import pytz

from .models import Booking, Notification

THAI_TZ  = pytz.timezone('Asia/Bangkok')
SITE_URL = getattr(settings, 'SITE_URL', 'http://localhost:8000')


@receiver(post_save, sender=Booking)
def broadcast_booking_update(sender, instance, created, **kwargs):
    """
    ทุกครั้งที่ Booking ถูก save → broadcast ให้ทุก Client รู้
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        'room_status',
        {
            'type':       'booking_update',
            'booking_id': instance.id,
            'room_id':    instance.room.id,
            'room_name':  instance.room.name,
            'status':     instance.status,
            'start_time': instance.start_time.isoformat(),
            'end_time':   instance.end_time.isoformat(),
        }
    )

    if created:
        send_booking_confirmation_email(instance)
    elif instance.status == 'cancelled':
        send_booking_cancelled_email(instance)


@receiver(post_save, sender=Notification)
def push_notification(sender, instance, created, **kwargs):
    """
    ทุกครั้งที่มี Notification ใหม่ → ส่งให้ User คนนั้นทันที
    """
    if not created:
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        f'user_{instance.user.id}_notifications',
        {
            'type':       'notification_push',
            'title':      instance.title,
            'message':    instance.message,
            'notif_type': instance.type,
            'booking_id': instance.booking.id if instance.booking else None,
        }
    )


# ─── Email Functions ───────────────────────────────────────────

def send_booking_confirmation_email(instance):
    """ส่งอีเมลยืนยันเมื่อจองสำเร็จ พร้อมปุ่ม Check-in และ ยกเลิก"""
    user_email = instance.user.email
    if not user_email:
        return

    start_thai = instance.start_time.astimezone(THAI_TZ)
    end_thai   = instance.end_time.astimezone(THAI_TZ)

    checkin_url = f'{SITE_URL}/api/bookings/{instance.id}/checkin/{instance.checkin_token}/'
    cancel_url  = f'{SITE_URL}/api/bookings/{instance.id}/cancel-email/{instance.checkin_token}/'

    plain_text = f'''
สวัสดีคุณ {instance.user.get_full_name() or instance.user.username}

การจองห้องของคุณสำเร็จแล้ว 🎉

รายละเอียดการจอง
─────────────────────────
ห้อง      : {instance.room.name}
อาคาร     : {instance.room.building.name}
หัวข้อ    : {instance.title}
วันที่     : {start_thai.strftime("%d/%m/%Y")}
เวลาเริ่ม  : {start_thai.strftime("%H:%M")} น.
เวลาสิ้นสุด: {end_thai.strftime("%H:%M")} น.
ผู้เข้าร่วม: {instance.attendees} คน
─────────────────────────

✅ กด Check-in (ได้ก่อนเวลา 15 นาที): {checkin_url}
❌ ยกเลิกการจอง: {cancel_url}

ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี
    '''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#1d4ed8;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">✅ ยืนยันการจองห้องสำเร็จ</h1>
      <p style="color:#bfdbfe;margin:8px 0 0;">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</p>
    </div>

    <!-- Yellow accent -->
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{instance.user.get_full_name() or instance.user.username}</b>
      </p>
      <p style="color:#6b7280;">การจองห้องของคุณสำเร็จแล้ว รายละเอียดด้านล่างครับ</p>

      <!-- Details Table -->
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;border-radius:8px;overflow:hidden;">
        <tr style="background:#eff6ff;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;color:#111827;">{instance.room.name}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;color:#111827;">{instance.room.building.name}</td>
        </tr>
        <tr style="background:#eff6ff;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;color:#111827;">{instance.title}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">📅 วันที่</td>
          <td style="padding:10px 12px;color:#111827;">{start_thai.strftime("%d/%m/%Y")}</td>
        </tr>
        <tr style="background:#eff6ff;">
          <td style="padding:10px 12px;color:#6b7280;">⏰ เวลา</td>
          <td style="padding:10px 12px;color:#111827;">
            {start_thai.strftime("%H:%M")} – {end_thai.strftime("%H:%M")} น.
          </td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">👥 ผู้เข้าร่วม</td>
          <td style="padding:10px 12px;color:#111827;">{instance.attendees} คน</td>
        </tr>
      </table>

      <!-- Check-in Button -->
      <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:20px;margin:24px 0;text-align:center;">
        <p style="margin:0 0 6px;font-size:15px;color:#15803d;font-weight:bold;">⚠️ กรุณา Check-in ก่อนเข้าใช้ห้อง</p>
        <p style="margin:0 0 16px;font-size:13px;color:#6b7280;">สามารถกด Check-in ได้ก่อนเวลา <b>15 นาที</b> จนถึงเวลาสิ้นสุด</p>
        <a href="{checkin_url}"
           style="display:inline-block;background:#16a34a;color:white;
                  padding:14px 36px;text-decoration:none;border-radius:8px;
                  font-size:16px;font-weight:bold;">
          ✅ กด Check-in ที่นี่
        </a>
      </div>

      <!-- Cancel Button -->
      <div style="background:#fff5f5;border:1px solid #fca5a5;border-radius:10px;padding:16px;margin:0 0 24px;text-align:center;">
        <p style="margin:0 0 12px;font-size:14px;color:#6b7280;">ไม่สามารถมาใช้งานได้?</p>
        <a href="{cancel_url}"
           style="display:inline-block;background:#dc2626;color:white;
                  padding:10px 28px;text-decoration:none;border-radius:8px;
                  font-size:14px;font-weight:bold;">
          ❌ ยกเลิกการจอง
        </a>
      </div>

      <!-- Warning Box -->
      <div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:16px;">
        <p style="margin:0;font-size:14px;color:#92400e;">
          ⚠️ กรุณายกเลิกหากไม่สามารถมาใช้งานได้ เพื่อให้ผู้อื่นสามารถใช้ห้องได้ครับ
        </p>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ลิงก์ใช้ได้ครั้งเดียว • ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>

  </div>
</body>
</html>
    '''

    try:
        send_mail(
            subject=f'✅ ยืนยันการจองห้อง {instance.room.name}',
            message=plain_text,
            from_email='nookkup47@gmail.com',
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=True,
        )
    except Exception as e:
        print(f'❌ ส่งอีเมลยืนยันไม่สำเร็จ: {e}')


def send_booking_cancelled_email(instance):
    """ส่งอีเมลเมื่อการจองถูกยกเลิก"""
    user_email = instance.user.email
    if not user_email:
        return

    start_thai = instance.start_time.astimezone(THAI_TZ)
    end_thai   = instance.end_time.astimezone(THAI_TZ)

    plain_text = f'''
สวัสดีคุณ {instance.user.get_full_name() or instance.user.username}

การจองห้องของคุณถูกยกเลิกแล้ว

รายละเอียดการจองที่ถูกยกเลิก
─────────────────────────
ห้อง      : {instance.room.name}
อาคาร     : {instance.room.building.name}
หัวข้อ    : {instance.title}
วันที่     : {start_thai.strftime("%d/%m/%Y")}
เวลาเริ่ม  : {start_thai.strftime("%H:%M")} น.
เวลาสิ้นสุด: {end_thai.strftime("%H:%M")} น.
─────────────────────────

หากต้องการจองใหม่ สามารถเข้าระบบได้เลย

ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี
    '''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#dc2626;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">❌ การจองถูกยกเลิกแล้ว</h1>
      <p style="color:#fecaca;margin:8px 0 0;">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</p>
    </div>

    <!-- Yellow accent -->
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{instance.user.get_full_name() or instance.user.username}</b>
      </p>
      <p style="color:#6b7280;">การจองห้องของคุณถูกยกเลิกแล้ว รายละเอียดด้านล่างครับ</p>

      <!-- Details Table -->
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;">
        <tr style="background:#fef2f2;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;color:#111827;">{instance.room.name}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;color:#111827;">{instance.room.building.name}</td>
        </tr>
        <tr style="background:#fef2f2;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;color:#111827;">{instance.title}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">📅 วันที่</td>
          <td style="padding:10px 12px;color:#111827;">{start_thai.strftime("%d/%m/%Y")}</td>
        </tr>
        <tr style="background:#fef2f2;">
          <td style="padding:10px 12px;color:#6b7280;">⏰ เวลา</td>
          <td style="padding:10px 12px;color:#111827;">
            {start_thai.strftime("%H:%M")} – {end_thai.strftime("%H:%M")} น.
          </td>
        </tr>
      </table>

      <!-- Info Box -->
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:16px;margin:24px 0;">
        <p style="margin:0;font-size:14px;color:#1e40af;">
          💡 หากต้องการจองใหม่ สามารถเข้าระบบได้เลยครับ
        </p>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>

  </div>
</body>
</html>
    '''

    try:
        send_mail(
            subject=f'❌ การจองห้อง {instance.room.name} ถูกยกเลิกแล้ว',
            message=plain_text,
            from_email='nookkup47@gmail.com',
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=True,
        )
    except Exception as e:
        print(f'❌ ส่งอีเมลยกเลิกไม่สำเร็จ: {e}')