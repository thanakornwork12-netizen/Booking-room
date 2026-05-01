# booking/serializers.py

from rest_framework import serializers
from django.utils import timezone
from datetime import datetime
from .models import (
    User, Building, Room, Facility, RoomFacility,
    TermBooking, Booking, BookingLog,
    DemandForecast, Notification, RoomUsageStat
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
        fields = ['username', 'first_name', 'last_name', 'email',
                  'password', 'password2', 'role', 'faculty', 'phone']

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
# ROOM
# ============================================================
class RoomFacilitySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='facility.name', read_only=True)
    icon = serializers.CharField(source='facility.icon', read_only=True)

    class Meta:
        model  = RoomFacility
        fields = ['id', 'name', 'icon', 'quantity']


class RoomSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source='building.name', read_only=True)
    building_code = serializers.CharField(source='building.code', read_only=True)
    facilities    = RoomFacilitySerializer(source='room_facilities', many=True, read_only=True)

    class Meta:
        model  = Room
        fields = ['id', 'name', 'building', 'building_name', 'building_code',
                  'floor', 'capacity', 'room_type', 'status',
                  'description', 'image', 'is_active', 'facilities']


class RoomListSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source='building.name', read_only=True)
    building_code = serializers.CharField(source='building.code', read_only=True)
    forecast      = serializers.SerializerMethodField()

    class Meta:
        model  = Room
        fields = ['id', 'name', 'building', 'building_name', 'building_code',
                  'floor', 'capacity', 'room_type', 'status',
                  'description', 'image', 'is_active', 'forecast']

    def get_forecast(self, obj):
        request     = self.context.get('request')
        search_date = None
        search_hour = None

        if request:
            try:
                if 'date' in request.query_params and 'start_time' in request.query_params:
                    search_date = datetime.strptime(
                        request.query_params['date'], '%Y-%m-%d'
                    ).date()
                    search_hour = datetime.strptime(
                        request.query_params['start_time'], '%H:%M'
                    ).hour
            except ValueError:
                pass

        if not search_date or search_hour is None:
            now         = timezone.now()
            search_date = now.date()
            search_hour = now.hour

        f = obj.forecasts.filter(
            forecast_date=search_date, hour=search_hour
        ).first()

        if f:
            return {
                'has_forecast':     True,
                'demand_level':     f.demand_level,
                'availability':     f.availability,
                'predicted_demand': float(f.predicted_demand),
                'term_demand':      float(f.term_demand),
                'dynamic_demand':   float(f.dynamic_demand),
                'confidence':       float(f.confidence),
            }

        return {
            'has_forecast':     False,
            'demand_level':     'none',
            'availability':     None,
            'predicted_demand': 0,
            'term_demand':      0,
            'dynamic_demand':   0,
            'confidence':       0,
        }


# ============================================================
# TERM BOOKING — จองทั้งเทอม
# ============================================================
class TermBookingSerializer(serializers.ModelSerializer):
    user_name     = serializers.CharField(source='user.get_full_name', read_only=True)
    room_name     = serializers.CharField(source='room.name',          read_only=True)
    building_name = serializers.CharField(source='room.building.name', read_only=True)
    day_name      = serializers.CharField(source='get_day_of_week_display', read_only=True)
    total_weeks   = serializers.SerializerMethodField()

    class Meta:
        model  = TermBooking
        fields = [
            'id', 'user', 'user_name', 'room', 'room_name', 'building_name',
            'subject_name', 'subject_code', 'attendees',
            'day_of_week', 'day_name', 'start_time', 'end_time',
            'term_start', 'term_end', 'term_name',
            'status', 'note', 'total_weeks', 'created_at',
        ]
        read_only_fields = ['id', 'user', 'status', 'created_at']

    def get_total_weeks(self, obj):
        return len(obj.get_weekly_slots())

    def validate(self, data):
        start   = data.get('start_time')
        end     = data.get('end_time')
        room    = data.get('room')
        dow     = data.get('day_of_week')
        t_start = data.get('term_start')
        t_end   = data.get('term_end')

        if start >= end:
            raise serializers.ValidationError('เวลาสิ้นสุดต้องหลังเวลาเริ่ม')
        if t_start >= t_end:
            raise serializers.ValidationError('วันสิ้นสุดเทอมต้องหลังวันเริ่มเทอม')

        # ตรวจซ้อนกับ TermBooking อื่น
        overlap = TermBooking.objects.filter(
            room=room,
            day_of_week=dow,
            status='active',
            term_start__lte=t_end,
            term_end__gte=t_start,
        ).exclude(
            start_time__gte=end
        ).exclude(
            end_time__lte=start
        )
        if self.instance:
            overlap = overlap.exclude(pk=self.instance.pk)
        if overlap.exists():
            raise serializers.ValidationError(
                'ห้องนี้มีการจองทั้งเทอมซ้อนในช่วงเวลาเดียวกันแล้ว'
            )
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class TermBookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TermBooking
        fields = ['room', 'subject_name', 'subject_code', 'attendees',
                  'day_of_week', 'start_time', 'end_time',
                  'term_start', 'term_end', 'term_name', 'note']

    def validate(self, data):
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError('เวลาสิ้นสุดต้องหลังเวลาเริ่ม')
        if data['term_start'] >= data['term_end']:
            raise serializers.ValidationError('วันสิ้นสุดเทอมต้องหลังวันเริ่มเทอม')

        overlap = TermBooking.objects.filter(
            room=data['room'],
            day_of_week=data['day_of_week'],
            status='active',
            term_start__lte=data['term_end'],
            term_end__gte=data['term_start'],
        ).exclude(
            start_time__gte=data['end_time']
        ).exclude(
            end_time__lte=data['start_time']
        )
        if overlap.exists():
            raise serializers.ValidationError(
                'ห้องนี้มีการจองทั้งเทอมซ้อนในช่วงเวลาเดียวกันแล้ว'
            )
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# ============================================================
# DYNAMIC BOOKING — จองรายวัน
# NOTE: การตรวจซ้อนหลักอยู่ใน views.py (perform_create)
#       โดยใช้ select_for_update() เพื่อป้องกัน Race Condition
#       Serializer ตรวจเบื้องต้นก่อน เพื่อ UX ที่ดี
# ============================================================
class BookingSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    room_name = serializers.CharField(source='room.name',          read_only=True)
    building  = serializers.CharField(source='room.building.name', read_only=True)

    class Meta:
        model  = Booking
        fields = ['id', 'user', 'user_name', 'room', 'room_name', 'building',
                  'title', 'attendees', 'start_time', 'end_time',
                  'status', 'note', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'status', 'created_at', 'updated_at']


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Booking
        fields = ['room', 'title', 'attendees', 'start_time', 'end_time', 'note']

    def validate(self, data):
        room       = data['room']
        start_time = data['start_time']
        end_time   = data['end_time']

        if start_time >= end_time:
            raise serializers.ValidationError('เวลาสิ้นสุดต้องหลังเวลาเริ่ม')

        # ── ชั้นที่ 1: ตรวจ Dynamic Booking (เบื้องต้น ยังไม่ Lock) ──
        overlap_dynamic = Booking.objects.filter(
            room=room,
            status__in=['pending', 'approved'],
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if self.instance:
            overlap_dynamic = overlap_dynamic.exclude(pk=self.instance.pk)
        if overlap_dynamic.exists():
            raise serializers.ValidationError(
                'ห้องนี้ถูกจองในช่วงเวลาดังกล่าวแล้ว'
            )

        # ── ชั้นที่ 2: ตรวจ TermBooking (ห้องถูกล็อกตลอดเทอม) ──
        target_date = start_time.date()
        target_dow  = target_date.weekday()
        overlap_term = TermBooking.objects.filter(
            room=room,
            day_of_week=target_dow,
            status='active',
            term_start__lte=target_date,
            term_end__gte=target_date,
        ).exclude(
            start_time__gte=end_time.time()
        ).exclude(
            end_time__lte=start_time.time()
        )
        if overlap_term.exists():
            tb = overlap_term.first()
            raise serializers.ValidationError(
                f'ห้องนี้ถูกจองทั้งเทอมโดย "{tb.subject_name}" '
                f'({tb.start_time:%H:%M}–{tb.end_time:%H:%M})'
            )

        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# ============================================================
# ROOM SEARCH
# ============================================================
class RoomSearchSerializer(serializers.Serializer):
    attendees     = serializers.IntegerField(min_value=1)
    room_type     = serializers.CharField(required=False, allow_blank=True)
    building_code = serializers.CharField(required=False, allow_blank=True)
    date          = serializers.DateField(required=False, allow_null=True)
    start_time    = serializers.TimeField()
    end_time      = serializers.TimeField()
    booking_type  = serializers.ChoiceField(
        choices=['dynamic', 'term'],
        default='dynamic',
        help_text='dynamic=จองรายวัน, term=จองทั้งเทอม'
    )
    term_start  = serializers.DateField(required=False, allow_null=True)
    term_end    = serializers.DateField(required=False, allow_null=True)
    day_of_week = serializers.IntegerField(required=False, min_value=0, max_value=6)

    def validate(self, data):
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError('เวลาสิ้นสุดต้องหลังเวลาเริ่ม')

        if data.get('booking_type') == 'term':
            if data.get('day_of_week') is None:
                raise serializers.ValidationError(
                    'การค้นหาห้องทั้งเทอมต้องระบุวันในสัปดาห์ (day_of_week)'
                )
        else:
            if not data.get('date'):
                raise serializers.ValidationError(
                    'การค้นหารายวันต้องระบุวันที่ (date)'
                )
        return data


# ============================================================
# BOOKING LOG
# ============================================================
class BookingLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source='changed_by.get_full_name', read_only=True
    )

    class Meta:
        model  = BookingLog
        fields = ['id', 'old_status', 'new_status', 'changed_by_name', 'changed_at']


# ============================================================
# DEMAND FORECAST
# ============================================================
class DemandForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DemandForecast
        fields = ['id', 'room', 'forecast_date', 'hour',
                  'predicted_demand', 'demand_level', 'availability',
                  'confidence', 'term_demand', 'dynamic_demand']


# ============================================================
# NOTIFICATION
# ============================================================
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notification
        fields = ['id', 'type', 'title', 'message',
                  'is_read', 'booking', 'term_booking', 'created_at']


# ============================================================
# ROOM USAGE STAT
# ============================================================
class RoomUsageStatSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model  = RoomUsageStat
        fields = ['id', 'room', 'room_name', 'date',
                  'total_bookings', 'term_bookings', 'dynamic_bookings',
                  'utilization_rate']