# booking/signals.py
# ส่ง WebSocket Event อัตโนมัติทุกครั้งที่ Booking เปลี่ยนสถานะ

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Booking, Notification


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

    # ส่งอีเมลเฉพาะตอนสร้างการจองใหม่
    if created:
        send_booking_confirmation_email(instance)

    # ส่งอีเมลเมื่อสถานะเปลี่ยน (ยกเลิก)
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
    """ส่งอีเมลยืนยันเมื่อจองสำเร็จ"""
    user_email = instance.user.email
    if not user_email:
        return

    try:
        send_mail(
            subject=f'✅ ยืนยันการจองห้อง {instance.room.name}',
            message=f'''
สวัสดีคุณ {instance.user.get_full_name() or instance.user.username}

การจองห้องของคุณสำเร็จแล้ว 🎉

รายละเอียดการจอง
─────────────────────────
ห้อง      : {instance.room.name}
อาคาร     : {instance.room.building.name}
หัวข้อ    : {instance.title}
วันที่     : {instance.start_time.strftime("%d/%m/%Y")}
เวลาเริ่ม  : {instance.start_time.strftime("%H:%M")} น.
เวลาสิ้นสุด: {instance.end_time.strftime("%H:%M")} น.
ผู้เข้าร่วม: {instance.attendees} คน
─────────────────────────

หากไม่สามารถมาใช้งานได้ กรุณายกเลิกการจองในระบบ
เพื่อให้ผู้อื่นสามารถใช้ห้องได้

ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี
            ''',
            from_email='nookkup47@gmail.com',
            recipient_list=[user_email],
            fail_silently=True,  # ถ้าส่งไม่ได้ไม่ให้ระบบพัง
        )
    except Exception as e:
        print(f'❌ ส่งอีเมลยืนยันไม่สำเร็จ: {e}')


def send_booking_cancelled_email(instance):
    """ส่งอีเมลเมื่อการจองถูกยกเลิก"""
    user_email = instance.user.email
    if not user_email:
        return

    try:
        send_mail(
            subject=f'❌ การจองห้อง {instance.room.name} ถูกยกเลิกแล้ว',
            message=f'''
สวัสดีคุณ {instance.user.get_full_name() or instance.user.username}

การจองห้องของคุณถูกยกเลิกแล้ว

รายละเอียดการจองที่ถูกยกเลิก
─────────────────────────
ห้อง      : {instance.room.name}
อาคาร     : {instance.room.building.name}
หัวข้อ    : {instance.title}
วันที่     : {instance.start_time.strftime("%d/%m/%Y")}
เวลาเริ่ม  : {instance.start_time.strftime("%H:%M")} น.
เวลาสิ้นสุด: {instance.end_time.strftime("%H:%M")} น.
─────────────────────────

หากต้องการจองใหม่ สามารถเข้าระบบได้เลย

ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี
            ''',
            from_email='nookkup47@gmail.com',
            recipient_list=[user_email],
            fail_silently=True,
        )
    except Exception as e:
        print(f'❌ ส่งอีเมลยกเลิกไม่สำเร็จ: {e}')