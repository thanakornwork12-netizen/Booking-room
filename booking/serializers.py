# booking/serializers.py

from rest_framework import serializers
from .models import (
    User, Building, Room, RoomFacility,
    Booking, BookingLog, DemandForecast,
    Notification, RoomUsageStat
)


# ============================================================
# USER
# ============================================================
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'username', 'first_name', 'last_name',
                  'email', 'role', 'faculty', 'phone', 'avatar']
        read_only_fields = ['id']


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, min_length=6)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model  = User
        fields = ['username', 'first_name', 'last_name',
                  'email', 'password', 'password2',
                  'role', 'faculty', 'phone']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'รหัสผ่านไม่ตรงกัน'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


# ============================================================
# BUILDING
# ============================================================
class BuildingSerializer(serializers.ModelSerializer):
    room_count = serializers.SerializerMethodField()

    class Meta:
        model  = Building
        fields = ['id', 'code', 'name', 'description', 'is_active', 'room_count']

    def get_room_count(self, obj):
        return obj.rooms.filter(is_active=True).count()


# ============================================================
# ROOM FACILITY
# ============================================================
class RoomFacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model  = RoomFacility
        fields = ['id', 'name', 'quantity']


# ============================================================
# ROOM
# ============================================================
class RoomSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source='building.name', read_only=True)
    building_code = serializers.CharField(source='building.code', read_only=True)
    facilities    = RoomFacilitySerializer(many=True, read_only=True)

    class Meta:
        model  = Room
        fields = [
            'id', 'name', 'building', 'building_name', 'building_code',
            'floor', 'capacity', 'room_type', 'status',
            'description', 'image', 'is_active', 'facilities'
        ]


class RoomListSerializer(serializers.ModelSerializer):
    """ใช้ตอนแสดงรายการ ไม่ต้องการรายละเอียด facilities"""
    building_name    = serializers.CharField(source='building.name', read_only=True)
    building_code    = serializers.CharField(source='building.code', read_only=True)
    demand_level     = serializers.SerializerMethodField()
    availability     = serializers.SerializerMethodField()

    class Meta:
        model  = Room
        fields = [
            'id', 'name', 'building', 'building_name', 'building_code',
            'floor', 'capacity', 'room_type', 'status',
            'demand_level', 'availability'
        ]

    def get_demand_level(self, obj):
        """ดึงค่าพยากรณ์ล่าสุดจาก LSTM"""
        from django.utils import timezone
        forecast = obj.forecasts.filter(
            forecast_date=timezone.now().date(),
            hour=timezone.now().hour
        ).first()
        return forecast.demand_level if forecast else 'low'

    def get_availability(self, obj):
        forecast = None
        from django.utils import timezone
        forecast = obj.forecasts.filter(
            forecast_date=timezone.now().date(),
            hour=timezone.now().hour
        ).first()
        return forecast.availability if forecast else 'likely_available'


# ============================================================
# BOOKING
# ============================================================
class BookingSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    room_name = serializers.CharField(source='room.name', read_only=True)
    building  = serializers.CharField(source='room.building.name', read_only=True)

    class Meta:
        model  = Booking
        fields = [
            'id', 'user', 'user_name', 'room', 'room_name', 'building',
            'title', 'attendees', 'start_time', 'end_time',
            'status', 'note', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'status', 'created_at', 'updated_at']

    def validate(self, data):
        """ตรวจสอบว่าห้องไม่ถูกจองซ้อนเวลา"""
        room       = data.get('room')
        start_time = data.get('start_time')
        end_time   = data.get('end_time')

        if start_time >= end_time:
            raise serializers.ValidationError('เวลาสิ้นสุดต้องหลังเวลาเริ่ม')

        # เช็คการซ้อนเวลา
        overlap = Booking.objects.filter(
            room=room,
            status__in=['pending', 'approved'],
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if self.instance:
            overlap = overlap.exclude(pk=self.instance.pk)
        if overlap.exists():
            raise serializers.ValidationError('ห้องนี้ถูกจองในช่วงเวลาดังกล่าวแล้ว')

        return data

    def create(self, validated_data):
        # ดึง user จาก request context
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class BookingCreateSerializer(serializers.ModelSerializer):
    """ใช้ตอนสร้างการจองใหม่ — รับแค่ข้อมูลที่จำเป็น"""
    class Meta:
        model  = Booking
        fields = ['room', 'title', 'attendees', 'start_time', 'end_time', 'note']

    def validate(self, data):
        room       = data.get('room')
        start_time = data.get('start_time')
        end_time   = data.get('end_time')

        if start_time >= end_time:
            raise serializers.ValidationError('เวลาสิ้นสุดต้องหลังเวลาเริ่ม')

        overlap = Booking.objects.filter(
            room=room,
            status__in=['pending', 'approved'],
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if overlap.exists():
            raise serializers.ValidationError('ห้องนี้ถูกจองในช่วงเวลาดังกล่าวแล้ว')

        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# ============================================================
# BOOKING LOG
# ============================================================
class BookingLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source='changed_by.get_full_name', read_only=True
    )

    class Meta:
        model  = BookingLog
        fields = ['id', 'old_status', 'new_status',
                  'remark', 'changed_by_name', 'changed_at']


# ============================================================
# DEMAND FORECAST
# ============================================================
class DemandForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DemandForecast
        fields = [
            'id', 'room', 'forecast_date', 'hour',
            'predicted_demand', 'demand_level',
            'availability', 'confidence'
        ]


# ============================================================
# NOTIFICATION
# ============================================================
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notification
        fields = [
            'id', 'type', 'title', 'message',
            'is_read', 'booking', 'created_at'
        ]


# ============================================================
# ROOM SEARCH (สำหรับ Pop-up ค้นหาห้อง)
# รับ: attendees, room_type, building_code, date, start_hour, end_hour
# คืน: ห้องที่ว่าง เรียงตามความเหมาะสม
# ============================================================
class RoomSearchSerializer(serializers.Serializer):
    attendees    = serializers.IntegerField(min_value=1, help_text='จำนวนคน')
    room_type    = serializers.CharField(required=False, allow_blank=True,
                                         help_text='ประเภทห้อง (ไม่บังคับ)')
    building_code = serializers.CharField(required=False, allow_blank=True,
                                          help_text='รหัสอาคาร (ไม่บังคับ)')
    date         = serializers.DateField(help_text='วันที่ต้องการจอง')
    start_time   = serializers.TimeField(help_text='เวลาเริ่ม')
    end_time     = serializers.TimeField(help_text='เวลาสิ้นสุด')

    def validate(self, data):
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError('เวลาสิ้นสุดต้องหลังเวลาเริ่ม')
        return data


# ============================================================
# ROOM USAGE STAT
# ============================================================
class RoomUsageStatSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model  = RoomUsageStat
        fields = [
            'id', 'room', 'room_name', 'date',
            'total_bookings', 'completed', 'no_show',
            'cancelled', 'utilization_rate'
        ]
