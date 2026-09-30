# booking/signals.py
# ส่ง WebSocket Event อัตโนมัติทุกครั้งที่ Booking เปลี่ยนสถานะ

from django.db import connection, transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.utils.html import escape
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import pytz
import logging
import threading
import socket

from .models import Booking, Notification, TermBooking

THAI_TZ      = pytz.timezone('Asia/Bangkok')
SITE_URL     = getattr(settings, 'SITE_URL', 'http://localhost:8000')
FRONTEND_URL = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
logger = logging.getLogger(__name__)


def get_recipient_email(user):
    if user.email:
        return user.email

    username = user.username or ''
    if '@' in username:
        return username
    if username.isdigit():
        return f'{username}@ubu.ac.th'
    return ''


def send_email_after_commit(send_func, instance):
    def run():
        try:
            logger.info('Background email thread starting for instance id=%s', getattr(instance, 'id', None))
            logger.info('EMAIL_HOST=%s EMAIL_PORT=%s EMAIL_BACKEND=%s',
                        getattr(settings, 'EMAIL_HOST', None),
                        getattr(settings, 'EMAIL_PORT', None),
                        getattr(settings, 'EMAIL_BACKEND', None))
            send_func(instance)
        except Exception:
            logger.exception('ส่งอีเมลแบบ background ไม่สำเร็จ')
        finally:
            # thread นี้เปิด connection DB ของตัวเอง (อ่าน instance.user/room)
            # Django ไม่ปิดให้เพราะไม่ใช่ thread ของ request — เดิมค้างไว้ทุกอีเมล
            # จน DB เทสต์ลบไม่ได้ ("being accessed by other users") และบน Neon
            # กิน connection limit
            connection.close()

    def _start_thread():
        logger.info('Starting background email thread (on commit) for instance id=%s', getattr(instance, 'id', None))
        threading.Thread(target=run, daemon=True).start()

    transaction.on_commit(_start_thread)


def log_email_error(context, error):
    if isinstance(error, (TimeoutError, socket.timeout)):
        logger.error(
            '%s: เชื่อมต่อ SMTP ไม่สำเร็จภายใน %s วินาที (%s:%s). '
            'ตรวจสอบ firewall/network หรือเปลี่ยน EMAIL_BACKEND/SMTP provider',
            context,
            getattr(settings, 'EMAIL_TIMEOUT', None),
            getattr(settings, 'EMAIL_HOST', None),
            getattr(settings, 'EMAIL_PORT', None),
        )
        return

    logger.exception('%s: %s', context, error)


@receiver(pre_save, sender=Booking)
def stash_old_booking_status(sender, instance, **kwargs):
    """เก็บสถานะก่อน save ไว้ใน instance เพื่อให้ post_save รู้ว่าเปลี่ยนจากอะไรมาเป็นอะไร"""
    if not instance.pk:
        instance._old_status = None
        return
    instance._old_status = Booking.objects.filter(pk=instance.pk).values_list('status', flat=True).first()


@receiver(post_save, sender=Booking)
def broadcast_booking_update(sender, instance, created, **kwargs):
    """
    ทุกครั้งที่ Booking ถูก save → broadcast ให้ทุก Client รู้ และส่งอีเมลตามการเปลี่ยนสถานะ
    """
    old_status = getattr(instance, '_old_status', None)

    if created:
        send_email_after_commit(send_booking_pending_email, instance)
        send_email_after_commit(send_approval_request_email, instance)
    elif old_status == 'pending' and instance.status == 'approved':
        send_email_after_commit(send_booking_confirmation_email, instance)
    elif old_status == 'pending' and instance.status == 'rejected':
        send_email_after_commit(send_booking_rejected_email, instance)
    elif instance.status == 'cancelled' and old_status != 'cancelled':
        send_email_after_commit(send_booking_cancelled_email, instance)

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    try:
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
    except Exception:
        logger.exception('ส่ง WebSocket booking update ไม่สำเร็จ')


@receiver(pre_save, sender=TermBooking)
def stash_old_term_status(sender, instance, **kwargs):
    """เหมือน stash_old_booking_status — ให้ post_save รู้ว่าสถานะเปลี่ยนจากอะไร"""
    if not instance.pk:
        instance._old_status = None
        return
    instance._old_status = TermBooking.objects.filter(pk=instance.pk).values_list('status', flat=True).first()


@receiver(post_save, sender=TermBooking)
def send_term_booking_email(sender, instance, created, **kwargs):
    """อีเมลตามการเปลี่ยนสถานะของการจองทั้งเทอม (ลำดับเดียวกับจองรายครั้ง)"""
    old_status = getattr(instance, '_old_status', None)

    if created and instance.status == 'pending':
        send_email_after_commit(send_term_booking_pending_email, instance)
        send_email_after_commit(send_approval_request_email, instance)
    elif created and instance.status == 'active':
        # สร้างเป็น active ตรง ๆ (Django admin/นำเข้าข้อมูล) — ไม่ผ่านขั้นรออนุมัติ
        send_email_after_commit(send_term_booking_confirmation_email, instance)
    elif old_status == 'pending' and instance.status == 'active':
        send_email_after_commit(send_term_booking_confirmation_email, instance)
    elif old_status == 'pending' and instance.status == 'rejected':
        send_email_after_commit(send_term_booking_rejected_email, instance)


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

def send_welcome_email(user):
    """ส่งอีเมลต้อนรับหลังสมัครสมาชิกสำเร็จ"""
    user_email = get_recipient_email(user)
    if not user_email:
        logger.warning('ไม่ส่งอีเมลต้อนรับ เพราะ user %s ไม่มี email', user.id)
        return

    display_name = user.get_full_name() or user.username
    login_url = f'{FRONTEND_URL}/login'

    plain_text = f'''
สวัสดีคุณ {display_name}

สมัครสมาชิกระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี สำเร็จแล้ว 🎉

ชื่อผู้ใช้: {user.username}

เข้าสู่ระบบได้ที่: {login_url}

ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
    '''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#1d4ed8;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">🎉 ยินดีต้อนรับ</h1>
      <p style="color:#bfdbfe;margin:8px 0 0;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
    </div>

    <!-- Yellow accent -->
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{escape(display_name)}</b>
      </p>
      <p style="color:#6b7280;">สมัครสมาชิกสำเร็จแล้ว ตอนนี้สามารถเข้าสู่ระบบเพื่อค้นหาและจองห้องประชุมได้ทันที</p>

      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;border-radius:8px;overflow:hidden;">
        <tr style="background:#eff6ff;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">👤 ชื่อผู้ใช้</td>
          <td style="padding:10px 12px;font-weight:bold;color:#111827;">{escape(user.username)}</td>
        </tr>
      </table>

      <div style="text-align:center;margin:24px 0;">
        <a href="{login_url}"
           style="display:inline-block;background:#1d4ed8;color:white;
                  padding:14px 36px;text-decoration:none;border-radius:8px;
                  font-size:16px;font-weight:bold;">
          เข้าสู่ระบบ
        </a>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>

  </div>
</body>
</html>
    '''

    try:
        logger.info(
            'Attempting send_mail to %s (welcome email, user id=%s) via %s:%s backend=%s',
            user_email,
            user.id,
            getattr(settings, 'EMAIL_HOST', None),
            getattr(settings, 'EMAIL_PORT', None),
            getattr(settings, 'EMAIL_BACKEND', None),
        )
        send_mail(
            subject='🎉 ยินดีต้อนรับสู่ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
            message=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        log_email_error('ส่งอีเมลต้อนรับไม่สำเร็จ', e)


def send_password_reset_email(user, uidb64, token):
    """ส่งลิงก์รีเซ็ตรหัสผ่าน — เฉพาะบัญชีที่สมัครเองในระบบ (มีรหัสผ่านจริงในนี้)
    บัญชี LDAP ของมหาวิทยาลัยไม่ได้ใช้ path นี้ เพราะรหัสผ่านอยู่ที่ LDAP ไม่ใช่ที่นี่"""
    user_email = get_recipient_email(user)
    if not user_email:
        logger.warning('ไม่ส่งอีเมลรีเซ็ตรหัสผ่าน เพราะ user %s ไม่มี email', user.id)
        return

    display_name = user.get_full_name() or user.username
    reset_url = f'{FRONTEND_URL}/reset-password/{uidb64}/{token}'

    plain_text = f'''
สวัสดีคุณ {display_name}

มีการขอรีเซ็ตรหัสผ่านสำหรับบัญชี {user.username} ในระบบจองห้องประชุม
สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี

ตั้งรหัสผ่านใหม่ได้ที่: {reset_url}
(ลิงก์นี้ใช้ได้ครั้งเดียว และหมดอายุใน 3 วัน หากไม่ได้เป็นคนขอ กรุณาเพิกเฉยอีเมลนี้)

ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
    '''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <div style="background:#1d4ed8;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">🔑 รีเซ็ตรหัสผ่าน</h1>
      <p style="color:#bfdbfe;margin:8px 0 0;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
    </div>
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{escape(display_name)}</b>
      </p>
      <p style="color:#6b7280;">
        มีการขอรีเซ็ตรหัสผ่านสำหรับบัญชี <b>{escape(user.username)}</b> กดปุ่มด้านล่างเพื่อตั้งรหัสผ่านใหม่
      </p>

      <div style="text-align:center;margin:24px 0;">
        <a href="{reset_url}"
           style="display:inline-block;background:#1d4ed8;color:white;
                  padding:14px 36px;text-decoration:none;border-radius:8px;
                  font-size:16px;font-weight:bold;">
          ตั้งรหัสผ่านใหม่
        </a>
      </div>

      <p style="font-size:12px;color:#9ca3af;">
        ลิงก์นี้ใช้ได้ครั้งเดียว และหมดอายุใน 3 วัน หากไม่ได้เป็นคนขอ กรุณาเพิกเฉยอีเมลนี้
      </p>
    </div>

    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>

  </div>
</body>
</html>
    '''

    try:
        send_mail(
            subject='🔑 รีเซ็ตรหัสผ่าน — ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
            message=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        log_email_error('ส่งอีเมลรีเซ็ตรหัสผ่านไม่สำเร็จ', e)


def send_approval_request_email(instance):
    """แจ้งผู้อนุมัติ (settings.APPROVER_EMAIL) ว่ามีคำขอจองใหม่เข้ามา

    ใช้ได้ทั้ง Booking (จองรายวัน) และ TermBooking (จองทั้งเทอม) — สองโมเดลนี้
    เก็บวัน/เวลาคนละแบบ จึงแยกสร้างบรรทัดรายละเอียดตามชนิดของ instance
    """
    approver_email = (getattr(settings, 'APPROVER_EMAIL', '') or '').strip()
    if not approver_email:
        logger.info('ไม่ได้ตั้ง APPROVER_EMAIL — ข้ามการแจ้งผู้อนุมัติ')
        return

    is_term = isinstance(instance, TermBooking)
    requester = instance.user.get_full_name() or instance.user.username
    requester_email = get_recipient_email(instance.user) or '-'
    admin_url = f'{FRONTEND_URL}/admin/dashboard'

    if is_term:
        kind_label = 'จองทั้งเทอม'
        subject_line = instance.subject_name
        when_rows = [
            ('วัน', f'ทุกวัน{instance.get_day_of_week_display()}'),
            ('เวลา', f'{instance.start_time:%H:%M} - {instance.end_time:%H:%M} น.'),
            ('ช่วงเทอม', f'{instance.term_start} ถึง {instance.term_end}'),
        ]
    else:
        start_thai = instance.start_time.astimezone(THAI_TZ)
        end_thai   = instance.end_time.astimezone(THAI_TZ)
        kind_label = 'จองรายวัน'
        subject_line = instance.title
        when_rows = [
            ('วันที่', f'{start_thai:%d/%m/%Y}'),
            ('เวลา', f'{start_thai:%H:%M} - {end_thai:%H:%M} น.'),
        ]

    detail_rows = [
        ('ประเภท', kind_label),
        ('ห้อง', instance.room.name),
        ('อาคาร', instance.room.building.name),
        ('หัวข้อ/วิชา', subject_line),
        *when_rows,
        ('ผู้เข้าร่วม', f'{instance.attendees} คน'),
        ('ผู้ขอจอง', f'{requester} ({requester_email})'),
    ]

    plain_rows = '\n'.join(f'{label:<12}: {value}' for label, value in detail_rows)
    plain_text = f"""
มีคำขอจองห้องใหม่รอการอนุมัติ

{plain_rows}

เข้าไปอนุมัติหรือปฏิเสธได้ที่: {admin_url}

ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
"""

    html_rows = ''.join(
        f'<tr>'
        f'<td style="padding:8px 0;color:#6b7280;font-size:14px;width:120px;">{escape(str(label))}</td>'
        f'<td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{escape(str(value))}</td>'
        f'</tr>'
        for label, value in detail_rows
    )
    html_message = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:24px;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.08);">
    <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:28px 32px;">
      <p style="margin:0;color:#ffffff;font-size:20px;font-weight:700;">มีคำขอจองห้องรอการอนุมัติ</p>
      <p style="margin:6px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">{escape(kind_label)}</p>
    </div>
    <div style="padding:24px 32px;">
      <table style="width:100%;border-collapse:collapse;">{html_rows}</table>
      <a href="{escape(admin_url)}"
         style="display:block;margin-top:24px;padding:14px;background:#4f46e5;color:#ffffff;text-align:center;
                text-decoration:none;border-radius:12px;font-weight:700;font-size:15px;">
        เปิดหน้าอนุมัติการจอง
      </a>
    </div>
    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>
  </div>
</body>
</html>
"""

    try:
        logger.info(
            'Attempting send_mail to %s (approval request, %s id=%s)',
            approver_email, 'term' if is_term else 'booking', getattr(instance, 'id', None),
        )
        send_mail(
            subject=f'📋 คำขอ{kind_label}ห้อง {instance.room.name} รอการอนุมัติ',
            message=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[approver_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        log_email_error('ส่งอีเมลแจ้งผู้อนุมัติไม่สำเร็จ', e)


def send_booking_pending_email(instance):
    """ส่งอีเมลแจ้งว่าได้รับคำขอจองแล้ว กำลังรอแอดมินอนุมัติ"""
    user_email = get_recipient_email(instance.user)
    if not user_email:
        logger.warning('ไม่ส่งอีเมลรออนุมัติ เพราะ user %s ไม่มี email', instance.user_id)
        return

    start_thai = instance.start_time.astimezone(THAI_TZ)
    end_thai   = instance.end_time.astimezone(THAI_TZ)
    cancel_url = f'{SITE_URL}/api/bookings/{instance.id}/cancel-email/{instance.checkin_token}/'

    plain_text = f'''
สวัสดีคุณ {instance.user.get_full_name() or instance.user.username}

ระบบได้รับคำขอจองห้องของคุณแล้ว กำลังรอแอดมินตรวจสอบและอนุมัติ
เมื่อผลการพิจารณาออกแล้ว ระบบจะส่งอีเมลแจ้งให้ทราบอีกครั้ง

รายละเอียดคำขอจอง
─────────────────────────
ห้อง      : {instance.room.name}
อาคาร     : {instance.room.building.name}
หัวข้อ    : {instance.title}
วันที่     : {start_thai.strftime("%d/%m/%Y")}
เวลาเริ่ม  : {start_thai.strftime("%H:%M")} น.
เวลาสิ้นสุด: {end_thai.strftime("%H:%M")} น.
ผู้เข้าร่วม: {instance.attendees} คน
─────────────────────────

❌ ยกเลิกคำขอจอง: {cancel_url}

ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
    '''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#d97706;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">⏳ ได้รับคำขอจองแล้ว</h1>
      <p style="color:#fef3c7;margin:8px 0 0;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
    </div>

    <!-- Yellow accent -->
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{escape(instance.user.get_full_name() or instance.user.username)}</b>
      </p>
      <p style="color:#6b7280;">ระบบได้รับคำขอจองห้องของคุณแล้ว กำลังรอแอดมินตรวจสอบและอนุมัติ เมื่อผลออกแล้วจะส่งอีเมลแจ้งอีกครั้งครับ</p>

      <!-- Details Table -->
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;border-radius:8px;overflow:hidden;">
        <tr style="background:#fffbeb;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;color:#111827;">{escape(instance.room.name)}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;color:#111827;">{escape(instance.room.building.name)}</td>
        </tr>
        <tr style="background:#fffbeb;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;color:#111827;">{escape(instance.title)}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">📅 วันที่</td>
          <td style="padding:10px 12px;color:#111827;">{start_thai.strftime("%d/%m/%Y")}</td>
        </tr>
        <tr style="background:#fffbeb;">
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

      <!-- Status Box -->
      <div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:16px;margin:24px 0;text-align:center;">
        <p style="margin:0;font-size:14px;color:#92400e;font-weight:bold;">⏳ รอแอดมินอนุมัติ</p>
      </div>

      <!-- Cancel Button -->
      <div style="background:#fff5f5;border:1px solid #fca5a5;border-radius:10px;padding:16px;text-align:center;">
        <p style="margin:0 0 12px;font-size:14px;color:#6b7280;">เปลี่ยนใจ ไม่ต้องการห้องนี้แล้ว?</p>
        <a href="{cancel_url}"
           style="display:inline-block;background:#dc2626;color:white;
                  padding:10px 28px;text-decoration:none;border-radius:8px;
                  font-size:14px;font-weight:bold;">
          ❌ ยกเลิกคำขอจอง
        </a>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ลิงก์ใช้ได้ครั้งเดียว • ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>

  </div>
</body>
</html>
    '''

    try:
      logger.info(
        'Attempting send_mail to %s (pending instance id=%s) via %s:%s backend=%s',
        user_email,
        getattr(instance, 'id', None),
        getattr(settings, 'EMAIL_HOST', None),
        getattr(settings, 'EMAIL_PORT', None),
        getattr(settings, 'EMAIL_BACKEND', None),
      )
      send_mail(
        subject=f'⏳ ได้รับคำขอจองห้อง {instance.room.name} แล้ว รอการอนุมัติ',
        message=plain_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user_email],
        html_message=html_message,
        fail_silently=False,
      )
    except Exception as e:
      log_email_error('ส่งอีเมลรอการอนุมัติไม่สำเร็จ', e)


def send_booking_confirmation_email(instance):
    """ส่งอีเมลยืนยันเมื่อแอดมินอนุมัติการจอง พร้อมปุ่ม Check-in และ ยกเลิก"""
    user_email = get_recipient_email(instance.user)
    if not user_email:
        logger.warning('ไม่ส่งอีเมลยืนยัน เพราะ user %s ไม่มี email', instance.user_id)
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

ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
    '''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#1d4ed8;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">✅ ยืนยันการจองห้องสำเร็จ</h1>
      <p style="color:#bfdbfe;margin:8px 0 0;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
    </div>

    <!-- Yellow accent -->
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{escape(instance.user.get_full_name() or instance.user.username)}</b>
      </p>
      <p style="color:#6b7280;">การจองห้องของคุณสำเร็จแล้ว รายละเอียดด้านล่างครับ</p>

      <!-- Details Table -->
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;border-radius:8px;overflow:hidden;">
        <tr style="background:#eff6ff;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;color:#111827;">{escape(instance.room.name)}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;color:#111827;">{escape(instance.room.building.name)}</td>
        </tr>
        <tr style="background:#eff6ff;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;color:#111827;">{escape(instance.title)}</td>
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
        ลิงก์ใช้ได้ครั้งเดียว • ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>

  </div>
</body>
</html>
    '''

    try:
      logger.info(
        'Attempting send_mail to %s (instance id=%s) via %s:%s backend=%s',
        user_email,
        getattr(instance, 'id', None),
        getattr(settings, 'EMAIL_HOST', None),
        getattr(settings, 'EMAIL_PORT', None),
        getattr(settings, 'EMAIL_BACKEND', None),
      )
      send_mail(
        subject=f'✅ ยืนยันการจองห้อง {instance.room.name}',
        message=plain_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user_email],
        html_message=html_message,
        fail_silently=False,
      )
    except Exception as e:
      log_email_error('ส่งอีเมลยืนยันไม่สำเร็จ', e)


def _send_term_booking_email(instance, *, subject, heading, intro, header_bg, log_label, reason=''):
    """อีเมลถึงผู้จองทั้งเทอม — ใช้ร่วมกันทั้งรับคำขอ / อนุมัติ / ปฏิเสธ"""
    user_email = get_recipient_email(instance.user)
    if not user_email:
        logger.warning('ไม่ส่งอีเมล%s เพราะ user %s ไม่มี email', log_label, instance.user_id)
        return

    day_name = instance.get_day_of_week_display()
    name = instance.user.get_full_name() or instance.user.username
    plain_text = f'''
สวัสดีคุณ {name}

{intro}

รายละเอียดการจอง
─────────────────────────
ห้อง      : {instance.room.name}
อาคาร     : {instance.room.building.name}
วิชา/กิจกรรม: {instance.subject_name}
วัน       : ทุกวัน{day_name}
เวลา      : {instance.start_time:%H:%M} - {instance.end_time:%H:%M} น.
ช่วงเทอม  : {instance.term_start} ถึง {instance.term_end}
ผู้เข้าร่วม: {instance.attendees} คน
─────────────────────────
{f"เหตุผล: {reason}" if reason else ""}

ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
    '''

    # reason เป็นข้อความที่แอดมินพิมพ์เอง ต้อง escape ก่อนฝังใน HTML
    reason_html = f'''
      <div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:10px;padding:16px;margin:0 0 8px;">
        <p style="margin:0 0 4px;font-size:13px;color:#991b1b;font-weight:bold;">เหตุผลที่ปฏิเสธ</p>
        <p style="margin:0;font-size:14px;color:#7f1d1d;">{escape(reason)}</p>
      </div>
    ''' if reason else ''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:{header_bg};padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">{escape(heading)}</h1>
      <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
    </div>
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>
    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">สวัสดีคุณ <b>{escape(name)}</b></p>
      <p style="color:#6b7280;">{escape(intro)}</p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;">
        <tr style="background:#eef2ff;"><td style="padding:10px 12px;color:#6b7280;width:40%;">ห้อง</td><td style="padding:10px 12px;font-weight:bold;color:#111827;">{escape(instance.room.name)}</td></tr>
        <tr><td style="padding:10px 12px;color:#6b7280;">อาคาร</td><td style="padding:10px 12px;color:#111827;">{escape(instance.room.building.name)}</td></tr>
        <tr style="background:#eef2ff;"><td style="padding:10px 12px;color:#6b7280;">วิชา/กิจกรรม</td><td style="padding:10px 12px;color:#111827;">{escape(instance.subject_name)}</td></tr>
        <tr><td style="padding:10px 12px;color:#6b7280;">วัน/เวลา</td><td style="padding:10px 12px;color:#111827;">ทุกวัน{day_name} {instance.start_time:%H:%M} - {instance.end_time:%H:%M} น.</td></tr>
        <tr style="background:#eef2ff;"><td style="padding:10px 12px;color:#6b7280;">ช่วงเทอม</td><td style="padding:10px 12px;color:#111827;">{instance.term_start} ถึง {instance.term_end}</td></tr>
        <tr><td style="padding:10px 12px;color:#6b7280;">ผู้เข้าร่วม</td><td style="padding:10px 12px;color:#111827;">{instance.attendees} คน</td></tr>
      </table>
      {reason_html}
    </div>
  </div>
</body>
</html>
    '''

    try:
        logger.info(
            'Attempting send_mail to %s (term instance id=%s) via %s:%s backend=%s',
            user_email,
            getattr(instance, 'id', None),
            getattr(settings, 'EMAIL_HOST', None),
            getattr(settings, 'EMAIL_PORT', None),
            getattr(settings, 'EMAIL_BACKEND', None),
        )
        send_mail(
            subject=subject,
            message=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        log_email_error(f'ส่งอีเมล{log_label}ไม่สำเร็จ', e)


def send_term_booking_pending_email(instance):
    """ส่งอีเมลเมื่อรับคำขอจองทั้งเทอมแล้ว (รออนุมัติ)"""
    _send_term_booking_email(
        instance,
        subject=f'รับคำขอจองห้องทั้งเทอม {instance.room.name} แล้ว (รออนุมัติ)',
        heading='รับคำขอจองห้องทั้งเทอมแล้ว',
        intro='ระบบได้รับคำขอจองห้องทั้งเทอมของคุณแล้ว กำลังรอแอดมินอนุมัติ จะแจ้งผลให้ทราบทางอีเมลอีกครั้ง',
        header_bg='#b45309', log_label='รับคำขอจองทั้งเทอม',
    )


def send_term_booking_confirmation_email(instance):
    """ส่งอีเมลยืนยันเมื่อการจองทั้งเทอมได้รับอนุมัติ"""
    _send_term_booking_email(
        instance,
        subject=f'ยืนยันการจองห้องทั้งเทอม {instance.room.name}',
        heading='การจองห้องทั้งเทอมได้รับการอนุมัติ',
        intro='การจองห้องทั้งเทอมของคุณได้รับการอนุมัติแล้ว รายละเอียดด้านล่างครับ',
        header_bg='#4338ca', log_label='ยืนยันจองทั้งเทอม',
    )


def send_term_booking_rejected_email(instance):
    """ส่งอีเมลเมื่อแอดมินปฏิเสธคำขอจองทั้งเทอม"""
    _send_term_booking_email(
        instance,
        subject=f'คำขอจองห้องทั้งเทอม {instance.room.name} ถูกปฏิเสธ',
        heading='คำขอจองห้องทั้งเทอมถูกปฏิเสธ',
        intro='คำขอจองห้องทั้งเทอมของคุณถูกปฏิเสธ หากต้องการจองห้องอื่นหรือช่วงเวลาอื่น เข้าระบบเพื่อจองใหม่ได้เลย',
        header_bg='#be123c', log_label='ปฏิเสธจองทั้งเทอม',
        reason=(instance.reject_reason or '').strip(),
    )


def send_booking_cancelled_email(instance):
    """ส่งอีเมลเมื่อการจองถูกยกเลิก"""
    user_email = get_recipient_email(instance.user)
    if not user_email:
        logger.warning('ไม่ส่งอีเมลยกเลิก เพราะ user %s ไม่มี email', instance.user_id)
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

ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
    '''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#dc2626;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">❌ การจองถูกยกเลิกแล้ว</h1>
      <p style="color:#fecaca;margin:8px 0 0;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
    </div>

    <!-- Yellow accent -->
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{escape(instance.user.get_full_name() or instance.user.username)}</b>
      </p>
      <p style="color:#6b7280;">การจองห้องของคุณถูกยกเลิกแล้ว รายละเอียดด้านล่างครับ</p>

      <!-- Details Table -->
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;">
        <tr style="background:#fef2f2;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;color:#111827;">{escape(instance.room.name)}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;color:#111827;">{escape(instance.room.building.name)}</td>
        </tr>
        <tr style="background:#fef2f2;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;color:#111827;">{escape(instance.title)}</td>
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
        ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>

  </div>
</body>
</html>
    '''

    try:
      logger.info(
        'Attempting send_mail to %s (cancel instance id=%s) via %s:%s backend=%s',
        user_email,
        getattr(instance, 'id', None),
        getattr(settings, 'EMAIL_HOST', None),
        getattr(settings, 'EMAIL_PORT', None),
        getattr(settings, 'EMAIL_BACKEND', None),
      )
      send_mail(
            subject=f'❌ การจองห้อง {instance.room.name} ถูกยกเลิกแล้ว',
            message=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        log_email_error('ส่งอีเมลยกเลิกไม่สำเร็จ', e)


def send_booking_rejected_email(instance):
    """ส่งอีเมลเมื่อแอดมินปฏิเสธคำขอจอง"""
    user_email = get_recipient_email(instance.user)
    if not user_email:
        logger.warning('ไม่ส่งอีเมลปฏิเสธ เพราะ user %s ไม่มี email', instance.user_id)
        return

    start_thai = instance.start_time.astimezone(THAI_TZ)
    end_thai   = instance.end_time.astimezone(THAI_TZ)
    reason     = (instance.reject_reason or '').strip()

    plain_text = f'''
สวัสดีคุณ {instance.user.get_full_name() or instance.user.username}

คำขอจองห้องของคุณถูกปฏิเสธ

รายละเอียดคำขอที่ถูกปฏิเสธ
─────────────────────────
ห้อง      : {instance.room.name}
อาคาร     : {instance.room.building.name}
หัวข้อ    : {instance.title}
วันที่     : {start_thai.strftime("%d/%m/%Y")}
เวลาเริ่ม  : {start_thai.strftime("%H:%M")} น.
เวลาสิ้นสุด: {end_thai.strftime("%H:%M")} น.
─────────────────────────
{f"เหตุผล: {reason}" if reason else ""}

หากต้องการจองห้องอื่นหรือช่วงเวลาอื่น สามารถเข้าระบบเพื่อจองใหม่ได้เลย

ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
    '''

    # escape ก่อนฝังใน HTML — reason เป็นข้อความที่แอดมินพิมพ์เอง (เชื่อไม่ได้)
    # ถูกส่งเป็นอีเมล HTML ไปหาอีกคน (ผู้จอง) ไม่ escape จะโดน HTML/script
    # injection ผ่านอีเมลได้ (plain_text ด้านบนไม่ต้อง escape เพราะไม่ใช่ HTML)
    reason_html = f'''
      <div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:10px;padding:16px;margin:0 0 24px;">
        <p style="margin:0 0 4px;font-size:13px;color:#991b1b;font-weight:bold;">เหตุผลที่ปฏิเสธ</p>
        <p style="margin:0;font-size:14px;color:#7f1d1d;">{escape(reason)}</p>
      </div>
    ''' if reason else ''

    html_message = f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;">
  <div style="max-width:520px;margin:32px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#dc2626;padding:28px 32px;">
      <h1 style="color:white;margin:0;font-size:22px;">❌ คำขอจองถูกปฏิเสธ</h1>
      <p style="color:#fecaca;margin:8px 0 0;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
    </div>

    <!-- Yellow accent -->
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);"></div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="font-size:16px;color:#374151;">
        สวัสดีคุณ <b>{escape(instance.user.get_full_name() or instance.user.username)}</b>
      </p>
      <p style="color:#6b7280;">คำขอจองห้องของคุณถูกปฏิเสธ รายละเอียดด้านล่างครับ</p>

      <!-- Details Table -->
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;">
        <tr style="background:#fef2f2;">
          <td style="padding:10px 12px;color:#6b7280;width:40%;">🏢 ห้อง</td>
          <td style="padding:10px 12px;font-weight:bold;color:#111827;">{escape(instance.room.name)}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">🏛️ อาคาร</td>
          <td style="padding:10px 12px;color:#111827;">{escape(instance.room.building.name)}</td>
        </tr>
        <tr style="background:#fef2f2;">
          <td style="padding:10px 12px;color:#6b7280;">📌 หัวข้อ</td>
          <td style="padding:10px 12px;color:#111827;">{escape(instance.title)}</td>
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

      {reason_html}

      <!-- Info Box -->
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:16px;">
        <p style="margin:0;font-size:14px;color:#1e40af;">
          💡 หากต้องการจองห้องอื่นหรือช่วงเวลาอื่น สามารถเข้าระบบเพื่อจองใหม่ได้เลยครับ
        </p>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี
      </p>
    </div>

  </div>
</body>
</html>
    '''

    try:
      logger.info(
        'Attempting send_mail to %s (rejected instance id=%s) via %s:%s backend=%s',
        user_email,
        getattr(instance, 'id', None),
        getattr(settings, 'EMAIL_HOST', None),
        getattr(settings, 'EMAIL_PORT', None),
        getattr(settings, 'EMAIL_BACKEND', None),
      )
      send_mail(
        subject=f'❌ คำขอจองห้อง {instance.room.name} ถูกปฏิเสธ',
        message=plain_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user_email],
        html_message=html_message,
        fail_silently=False,
      )
    except Exception as e:
      log_email_error('ส่งอีเมลปฏิเสธไม่สำเร็จ', e)
