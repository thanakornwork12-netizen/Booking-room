# booking/serializers.py

from rest_framework import serializers
from django.utils import timezone
from datetime import datetime
from .models import (
    User, Building, Room, Facility, RoomFacility,
    TermBooking, Booking, BookingLog,
    DemandForecast, Notification, RoomUsageStat, MaintenanceBlock,
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

        # Normalize username so users who register with an email
        # (e.g. '6611234567@ubu.ac.th') will have the same username
        # as LDAP logins that use the bare student id '6611234567'.
        username = validated_data.get('username', '')
        if isinstance(username, str) and '@' in username:
            validated_data['username'] = username.split('@')[0]

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)
    new_password2 = serializers.CharField(write_only=True, min_length=6)

    def validate(self, data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError('กรุณาเข้าสู่ระบบก่อน')

        if not user.has_usable_password():
            raise serializers.ValidationError({
                'old_password': 'บัญชีนี้ใช้รหัสผ่านจาก LDAP กรุณาเปลี่ยนรหัสผ่านที่ระบบมหาวิทยาลัย'
            })

        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError({
                'new_password': 'รหัสผ่านใหม่ไม่ตรงกัน'
            })

        if not user.check_password(data['old_password']):
            raise serializers.ValidationError({
                'old_password': 'รหัสผ่านเดิมไม่ถูกต้อง'
            })

        if data['old_password'] == data['new_password']:
            raise serializers.ValidationError({
                'new_password': 'รหัสผ่านใหม่ต้องไม่ซ้ำกับรหัสผ่านเดิม'
            })

        return data


class DeleteAccountSerializer(serializers.Serializer):
    confirm_username = serializers.CharField(write_only=True)
    confirm_text = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')

    def validate(self, data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError('กรุณาเข้าสู่ระบบก่อน')

        if data['confirm_username'].strip() != user.username:
            raise serializers.ValidationError({
                'confirm_username': 'ชื่อผู้ใช้ไม่ตรงกับบัญชีปัจจุบัน'
            })

        if data['confirm_text'].strip().upper() != 'DELETE':
            raise serializers.ValidationError({
                'confirm_text': 'กรุณาพิมพ์ DELETE เพื่อยืนยัน'
            })

        if user.has_usable_password():
            password = data.get('password', '')
            if not password:
                raise serializers.ValidationError({
                    'password': 'กรุณากรอกรหัสผ่านเพื่อยืนยันการลบบัญชี'
                })
            if not user.check_password(password):
                raise serializers.ValidationError({
                    'password': 'รหัสผ่านไม่ถูกต้อง'
                })

        return data


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
        target_date  = start_time.date()
        target_dow   = target_date.weekday()
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


# ============================================================
# LDAP JWT AUTH
# ============================================================
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import serializers

from .ldap_auth import authenticate_ldap
from .models import User


class LDAPTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Login ด้วย LDAP มหาวิทยาลัย

    Frontend ส่ง:
    {
        "username": "6612345678",
        "password": "xxxx"
    }

    ระบบจะ:
    1. ตรวจสอบ credential กับ LDAP
    2. ถ้าถูก -> สร้าง/อัปเดต Django User
    3. สร้าง JWT access + refresh token
    """

    def validate(self, attrs):

        # =====================================================
        # รับค่าจาก frontend
        # =====================================================

        username = attrs.get('username', '').strip()
        password = attrs.get('password', '')

        if not username:
            raise serializers.ValidationError({
                'detail': 'กรุณากรอกรหัสนักศึกษา'
            })

        if not password:
            raise serializers.ValidationError({
                'detail': 'กรุณากรอกรหัสผ่าน'
            })

        # =====================================================
        # รองรับกรอกทั้ง:
        # 6612345678
        # และ
        # 6612345678@ubu.ac.th
        # =====================================================

        pure_username = username

        if '@' in username:
            pure_username = username.split('@')[0]

        # =====================================================
        # LDAP AUTH ก่อน แล้ว fallback ไปบัญชี local ที่สมัครผ่านระบบ
        # =====================================================

        ldap_user = authenticate_ldap(
            pure_username,
            password
        )

        if not ldap_user:
            user = (
                User.objects.filter(username=username).first()
                or User.objects.filter(username=pure_username).first()
            )

            if not user or not user.check_password(password):
                raise serializers.ValidationError({
                    'detail': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
                })

            refresh = RefreshToken.for_user(user)
            return {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'display_name': f'{user.first_name} {user.last_name}'.strip(),
                    'full_name': f'{user.first_name} {user.last_name}'.strip(),
                    'email': user.email,
                    'faculty': user.faculty,
                    'role': user.role,
                    'avatar': (
                        user.avatar.url
                        if getattr(user, 'avatar', None)
                        else None
                    ),
                    'is_new_user': False,
                }
            }


        # =====================================================
        # CREATE / UPDATE DJANGO USER
        # =====================================================

        user, created = User.objects.get_or_create(
            username=pure_username
        )

        # =====================================================
        # UPDATE USER INFO FROM LDAP
        # =====================================================

        full_name = ldap_user.get('full_name', '')

        # แยกชื่อ นามสกุล
        name_parts = full_name.split(' ', 1)

        first_name = ''
        last_name = ''

        if len(name_parts) >= 1:
            first_name = name_parts[0]

        if len(name_parts) >= 2:
            last_name = name_parts[1]

        user.first_name = first_name
        user.last_name = last_name

        user.email = ldap_user.get('email') or f'{pure_username}@ubu.ac.th'

        user.faculty = ldap_user.get(
            'department',
            ''
        )

        # default role
        if not user.role:
            user.role = 'student'

        # IMPORTANT:
        # ไม่เก็บ password ใน database
        user.set_unusable_password()

        user.save()

        # =====================================================
        # GENERATE JWT TOKEN
        # =====================================================

        refresh = RefreshToken.for_user(user)

        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # =====================================================
        # RESPONSE
        # =====================================================

        return {

            # JWT
            'access': access_token,
            'refresh': refresh_token,

            # USER INFO
            'user': {

                'id': user.id,

                'username': user.username,

                'first_name': user.first_name,

                'last_name': user.last_name,

                'display_name': f'{user.first_name} {user.last_name}'.strip(),

                'full_name': f'{user.first_name} {user.last_name}'.strip(),

                'email': user.email,

                'faculty': user.faculty,

                'role': user.role,

                'avatar': (
                    user.avatar.url
                    if getattr(user, 'avatar', None)
                    else None
                ),

                'is_new_user': created,
            }
        }


# ============================================================
# MAINTENANCE BLOCK
# ============================================================
class MaintenanceBlockSerializer(serializers.ModelSerializer):
    room_name     = serializers.CharField(source='room.name', read_only=True)
    building_name = serializers.CharField(source='room.building.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model  = MaintenanceBlock
        fields = [
            'id', 'room', 'room_name', 'building_name',
            'start_time', 'end_time', 'reason', 'note', 'status',
            'predicted_demand_avg', 'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class MaintenanceBlockCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MaintenanceBlock
        fields = ['room', 'start_time', 'end_time', 'reason', 'note', 'predicted_demand_avg']

    def validate(self, data):
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError('เวลาสิ้นสุดต้องหลังเวลาเริ่ม')
        return data


class AdminRoomStatusSerializer(serializers.Serializer):
    id          = serializers.IntegerField()
    name        = serializers.CharField()
    code        = serializers.CharField()
    building    = serializers.CharField()
    capacity    = serializers.IntegerField()
    room_type   = serializers.CharField()
    status      = serializers.CharField()
    util_rate   = serializers.FloatField(required=False)
    booking_count = serializers.IntegerField(required=False)
