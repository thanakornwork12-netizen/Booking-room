# booking/signals.py
# ส่ง WebSocket Event อัตโนมัติทุกครั้งที่ Booking เปลี่ยนสถานะ

from django.db.models.signals import post_save
from django.dispatch import receiver
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
