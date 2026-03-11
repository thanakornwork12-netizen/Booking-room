# booking/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone


class RoomStatusConsumer(AsyncWebsocketConsumer):
    """
    WebSocket สำหรับสถานะห้องแบบ Real-time
    URL: ws://localhost:8000/ws/rooms/
    ทุก Client ที่เชื่อมต่อจะได้รับการอัปเดตพร้อมกัน
    """

    async def connect(self):
        self.group_name = 'room_status'

        # เข้าร่วม Group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        # ส่งสถานะห้องทั้งหมดให้ Client ทันทีที่เชื่อมต่อ
        rooms = await self.get_all_rooms()
        await self.send(text_data=json.dumps({
            'type':  'initial_rooms',
            'rooms': rooms,
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """รับข้อความจาก Client (ถ้าต้องการ ping หรือ request ข้อมูล)"""
        try:
            data = json.loads(text_data)
            msg_type = data.get('type')

            if msg_type == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))

            elif msg_type == 'get_rooms':
                rooms = await self.get_all_rooms()
                await self.send(text_data=json.dumps({
                    'type':  'initial_rooms',
                    'rooms': rooms,
                }))

        except Exception as e:
            await self.send(text_data=json.dumps({
                'type':  'error',
                'message': str(e)
            }))

    # ---- Event handlers (รับจาก group_send) ----

    async def room_status_update(self, event):
        """รับ event เมื่อสถานะห้องเปลี่ยน แล้วส่งต่อให้ Client"""
        await self.send(text_data=json.dumps({
            'type':        'room_status_update',
            'room_id':     event['room_id'],
            'room_name':   event['room_name'],
            'status':      event['status'],
            'updated_at':  event['updated_at'],
        }))

    async def booking_update(self, event):
        """รับ event เมื่อมีการจองใหม่ หรือสถานะการจองเปลี่ยน"""
        await self.send(text_data=json.dumps({
            'type':       'booking_update',
            'booking_id': event['booking_id'],
            'room_id':    event['room_id'],
            'room_name':  event['room_name'],
            'status':     event['status'],
            'start_time': event['start_time'],
            'end_time':   event['end_time'],
        }))

    async def notification_push(self, event):
        """ส่ง Notification ให้ Client เฉพาะคน"""
        await self.send(text_data=json.dumps({
            'type':    'notification',
            'title':   event['title'],
            'message': event['message'],
            'notif_type': event.get('notif_type', 'system'),
        }))

    # ---- DB Queries (ต้องใช้ database_sync_to_async) ----

    @database_sync_to_async
    def get_all_rooms(self):
        from .models import Room
        rooms = Room.objects.filter(is_active=True).select_related('building')
        return [
            {
                'id':            r.id,
                'name':          r.name,
                'building_code': r.building.code,
                'building_name': r.building.name,
                'floor':         r.floor,
                'capacity':      r.capacity,
                'room_type':     r.room_type,
                'status':        r.status,
            }
            for r in rooms
        ]


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket สำหรับ Notification เฉพาะ User
    URL: ws://localhost:8000/ws/notifications/
    แต่ละ User จะอยู่ใน Group ของตัวเอง
    """

    async def connect(self):
        user = self.scope.get('user')

        if not user or not user.is_authenticated:
            await self.close()
            return

        # Group เฉพาะ user นี้
        self.group_name = f'user_{user.id}_notifications'

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        # ส่งจำนวน unread notifications
        count = await self.get_unread_count(user.id)
        await self.send(text_data=json.dumps({
            'type':  'unread_count',
            'count': count,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        pass

    async def notification_push(self, event):
        """รับ notification แล้วส่งให้ Client"""
        await self.send(text_data=json.dumps({
            'type':       'new_notification',
            'title':      event['title'],
            'message':    event['message'],
            'notif_type': event.get('notif_type', 'system'),
            'booking_id': event.get('booking_id'),
        }))

    @database_sync_to_async
    def get_unread_count(self, user_id):
        from .models import Notification
        return Notification.objects.filter(user_id=user_id, is_read=False).count()
class RetrainConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return
        if user.role not in ['admin', 'staff']:
            await self.close()
            return
        await self.channel_layer.group_add('retrain_progress', self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard('retrain_progress', self.channel_name)

    async def retrain_update(self, event):
        await self.send(text_data=json.dumps(event))