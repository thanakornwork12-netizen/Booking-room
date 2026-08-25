import pandas as pd
import re
from difflib import SequenceMatcher
from django.utils import timezone
from django.db.models import Count, Q
from datetime import datetime, date as date_type, timedelta
from django.http import HttpResponse, JsonResponse
import io, threading, pytz
from rest_framework.views import APIView
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from functools import partial
from django.shortcuts import redirect, render
from .ldap_auth import authenticate_ldap
from .models import (
    User, Building, Room, Facility, RoomFacility,
    TermBooking, Booking, BookingLog,
    DemandForecast, Notification, RoomUsageStat, MaintenanceBlock,
)
from .serializers import (
    UserSerializer, RegisterSerializer,
    ChangePasswordSerializer, DeleteAccountSerializer,
    BuildingSerializer,
    RoomSerializer, RoomListSerializer, RoomSearchSerializer,
    TermBookingSerializer, TermBookingCreateSerializer,
    BookingSerializer, BookingCreateSerializer,
    BookingLogSerializer, DemandForecastSerializer,
    NotificationSerializer, RoomUsageStatSerializer,
    MaintenanceBlockSerializer, MaintenanceBlockCreateSerializer,
)

THAI_TZ = pytz.timezone('Asia/Bangkok')


# ============================================================
# AUTH
# ============================================================
class RegisterView(generics.CreateAPIView):
    queryset           = User.objects.all()
    serializer_class   = RegisterSerializer
    permission_classes = [AllowAny]


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])

        return Response({'detail': 'เปลี่ยนรหัสผ่านสำเร็จ'})


class ForgotPasswordView(APIView):
    """ขอลิงก์รีเซ็ตรหัสผ่าน — ใช้ได้เฉพาะบัญชีที่สมัครเองในระบบ (มีรหัสผ่านจริง
    เก็บไว้ในนี้) บัญชี LDAP ของมหาวิทยาลัยไม่มีรหัสผ่านเก็บในระบบนี้เลย
    (user.password ว่างเปล่าเสมอ — ล็อกอินผ่าน LDAP โดยตรง) จึงรีเซ็ตจากที่นี่
    ไม่ได้ ต้องแจ้งให้ติดต่อ IT แทน"""
    permission_classes = [AllowAny]

    def post(self, request):
        identifier = (request.data.get('email') or request.data.get('username') or '').strip()
        if not identifier:
            return Response({'error': 'กรุณากรอกอีเมลหรือชื่อผู้ใช้'}, status=400)

        user = (
            User.objects.filter(email__iexact=identifier).first()
            or User.objects.filter(username=identifier).first()
        )

        if user and not user.password:
            return Response({
                'detail': (
                    'บัญชีนี้เข้าสู่ระบบด้วยรหัสนักศึกษา/รหัสผ่านของมหาวิทยาลัย (LDAP) '
                    'ไม่สามารถรีเซ็ตรหัสผ่านผ่านหน้านี้ได้ กรุณาติดต่อสำนักคอมพิวเตอร์และเครือข่าย '
                    'โทร. 045-353102 เพื่อรีเซ็ตรหัสผ่าน'
                ),
                'ldap_account': True,
            })

        if user and user.email:
            from .signals import send_email_after_commit, send_password_reset_email
            token = default_token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            send_email_after_commit(partial(send_password_reset_email, uidb64=uidb64, token=token), user)

        # ข้อความเดียวกันไม่ว่าจะเจอบัญชีหรือไม่ กันคนสุ่มเช็คว่าอีเมล/ชื่อผู้ใช้นี้
        # มีอยู่ในระบบไหม
        return Response({
            'detail': 'หากอีเมลหรือชื่อผู้ใช้นี้มีอยู่ในระบบ เราได้ส่งลิงก์รีเซ็ตรหัสผ่านไปทางอีเมลแล้ว กรุณาตรวจสอบกล่องอีเมลของคุณ',
        })


class ResetPasswordConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uidb64 = request.data.get('uid', '')
        token = request.data.get('token', '')
        password = request.data.get('password', '')
        password2 = request.data.get('password2', '')

        if not password or password != password2:
            return Response({'error': 'รหัสผ่านไม่ตรงกัน'}, status=400)
        if len(password) < 6:
            return Response({'error': 'รหัสผ่านต้องมีอย่างน้อย 6 ตัว'}, status=400)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'error': 'ลิงก์รีเซ็ตรหัสผ่านไม่ถูกต้องหรือหมดอายุแล้ว'}, status=400)

        if not user.password:
            return Response({'error': 'บัญชีนี้ไม่รองรับการรีเซ็ตรหัสผ่านในระบบนี้'}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({'error': 'ลิงก์รีเซ็ตรหัสผ่านไม่ถูกต้องหรือหมดอายุแล้ว'}, status=400)

        user.set_password(password)
        user.save(update_fields=['password'])
        return Response({'detail': 'ตั้งรหัสผ่านใหม่สำเร็จ กรุณาเข้าสู่ระบบอีกครั้ง'})


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.delete()

        return Response({'detail': 'ลบบัญชีผู้ใช้สำเร็จ'})


def _require_admin_or_staff(request):
    if getattr(request.user, 'role', None) not in ['admin', 'staff']:
        raise PermissionDenied('สำหรับผู้ดูแลระบบเท่านั้น')


# ============================================================
# BUILDING
# ============================================================
class BuildingViewSet(viewsets.ModelViewSet):
    serializer_class   = BuildingSerializer

    def get_queryset(self):
        qs = Building.objects.filter(is_active=True).order_by('name')
        # การจอง (SearchPage) กับการจัดการ inventory (AdminPage) เรียก endpoint
        # นี้ร่วมกัน แยกด้วย query param แทน role ของผู้ใช้ — ไม่งั้น admin ที่เข้า
        # หน้าค้นหาห้องเพื่อจองจริงจะเห็นอาคารที่ไม่มีห้องให้จองเลยสักห้องไปด้วย
        # (แต่ยังต้องเห็นครบ 16 อาคารตอนจัดการ inventory ในหน้าแอดมิน)
        if self.request.query_params.get('bookable_only') == 'true':
            qs = qs.filter(rooms__id__in=AI_FORECAST_ROOM_IDS, rooms__is_active=True).distinct()
        return qs

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        _require_admin_or_staff(self.request)
        serializer.save()

    def perform_update(self, serializer):
        _require_admin_or_staff(self.request)
        serializer.save()

    def perform_destroy(self, instance):
        _require_admin_or_staff(self.request)
        instance.is_active = False
        instance.save(update_fields=['is_active'])


# ============================================================
# ROOM
# ============================================================
# ห้องที่มีข้อมูลการใช้งานสะสมมากพอให้โมเดล AI (ml/saved/forecast.py) เรียนรู้
# และพยากรณ์ความต้องการได้แม่นยำจริง (~90%+ ตรวจสอบแล้ว) — อีก 61 ห้องที่เหลือ
# ยังไม่มีข้อมูลพอ เลยซ่อนจากการค้นหา/จองของผู้ใช้ทั่วไป จนกว่าจะมีข้อมูลสะสมพอ
# staff/admin ยังเห็นห้องทั้งหมดตามปกติ เพื่อจัดการ inventory จริงของมหาวิทยาลัยได้ครบ
AI_FORECAST_ROOM_IDS = {443, 445, 446, 447, 448, 487, 505, 506}


class RoomViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        is_staff = getattr(self.request.user, 'role', None) in ['admin', 'staff']
        qs = Room.objects.select_related('building')
        qs = qs if is_staff else qs.filter(is_active=True, id__in=AI_FORECAST_ROOM_IDS)
        building  = self.request.query_params.get('building')
        room_type = self.request.query_params.get('room_type')
        capacity  = self.request.query_params.get('min_capacity')
        if building:
            qs = qs.filter(building__code=building)
        if room_type:
            qs = qs.filter(room_type=room_type)
        if capacity:
            qs = qs.filter(capacity__gte=int(capacity))
        return qs

    def get_serializer_class(self):
        return RoomListSerializer if self.action == 'list' else RoomSerializer

    def perform_create(self, serializer):
        _require_admin_or_staff(self.request)
        serializer.save()

    def perform_update(self, serializer):
        _require_admin_or_staff(self.request)
        serializer.save()

    def perform_destroy(self, instance):
        _require_admin_or_staff(self.request)
        instance.is_active = False
        instance.status = 'disabled'
        instance.save(update_fields=['is_active', 'status'])

    @action(detail=False, methods=['post'])
    def search(self, request):
        ser = RoomSearchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        booking_type = d.get('booking_type', 'dynamic')
        if booking_type == 'dynamic':
            return self._search_dynamic(d, request)
        else:
            return self._search_term(d, request)

    @action(detail=False, methods=['get'], url_path='suggestions')
    def suggestions(self, request):
        q = (request.query_params.get('q') or '').strip()
        limit = request.query_params.get('limit', 8)
        try:
            limit = max(1, min(int(limit), 20))
        except (TypeError, ValueError):
            limit = 8

        # การค้นหา/จองห้องจำกัดแค่ห้องที่มีข้อมูล AI จริงเสมอ ไม่ว่าใครจะเป็นคนจอง
        # (ต่างจาก RoomViewSet.get_queryset ทั่วไปที่ยังให้ staff/admin เห็นครบ
        # สำหรับจัดการ inventory)
        rooms_qs = Room.objects.filter(is_active=True, id__in=AI_FORECAST_ROOM_IDS)
        rooms = list(rooms_qs.select_related('building').order_by('building__name', 'name'))

        if not q:
            picked = rooms[:limit]
        else:
            scored = []
            for room in rooms:
                score = self._score_suggestion(room, q)
                if score > 0:
                    scored.append((score, room))
            scored.sort(key=lambda item: (-item[0], item[1].building.name if item[1].building else '', item[1].name))
            picked = [room for _, room in scored[:limit]]

        return Response([
            {
                'id': room.id,
                'name': room.name,
                'building_name': room.building.name if room.building else 'ไม่ระบุอาคาร',
                'building_code': room.building.code if room.building else '',
                'floor': room.floor,
                'capacity': room.capacity,
                'room_type': room.room_type,
                'status': room.status,
            }
            for room in picked
        ])

    def _search_dynamic(self, d, request):
        target_date = d['date']
        start_dt    = timezone.make_aware(datetime.combine(target_date, d['start_time']))
        end_dt      = timezone.make_aware(datetime.combine(target_date, d['end_time']))
        target_dow  = target_date.weekday()

        booked_dynamic = Booking.objects.filter(
            status__in=['pending', 'approved'],
            start_time__lt=end_dt, end_time__gt=start_dt,
        ).values_list('room_id', flat=True)

        maint_blocked = MaintenanceBlock.objects.filter(
            status__in=['scheduled', 'active'],
            start_time__lt=end_dt, end_time__gt=start_dt,
        ).values_list('room_id', flat=True)

        booked_term = TermBooking.objects.filter(
            day_of_week=target_dow, status='active',
            term_start__lte=target_date, term_end__gte=target_date,
        ).exclude(start_time__gte=d['end_time']).exclude(end_time__lte=d['start_time'])\
         .values_list('room_id', flat=True)

        blocked   = set(list(booked_dynamic) + list(booked_term) + list(maint_blocked))
        # การจองจำกัดแค่ห้องที่มีข้อมูล AI จริงเสมอ ไม่ว่าใครจะเป็นคนจอง
        available = Room.objects.filter(
            is_active=True, status='available', capacity__gte=d['attendees'], id__in=AI_FORECAST_ROOM_IDS,
        ).exclude(id__in=blocked).select_related('building')\
         .prefetch_related('room_facilities__facility', 'forecasts')

        if d.get('room_type'):
            available = available.filter(room_type=d['room_type'])
        if d.get('building_code'):
            preferred = list(available.filter(building__code=d['building_code']).order_by('capacity'))
            others    = list(available.exclude(building__code=d['building_code']).order_by('capacity'))
            results   = preferred + others
        else:
            results = list(available.order_by('capacity'))

        return Response(self._enrich_rooms(results, target_date, d['start_time'], d['end_time'], 'dynamic', request))

    def _search_term(self, d, request):
        fallback_date = d.get('date') or date_type.today()
        dow     = d.get('day_of_week', fallback_date.weekday())
        t_start = d.get('term_start', fallback_date)
        t_end   = d.get('term_end',   fallback_date)

        booked_term = TermBooking.objects.filter(
            day_of_week=dow, status='active',
            term_start__lte=t_end, term_end__gte=t_start,
        ).exclude(start_time__gte=d['end_time']).exclude(end_time__lte=d['start_time'])\
         .values_list('room_id', flat=True)

        # ช่วงซ่อมบำรุงที่ทับกับเทอม
        maint_blocked = MaintenanceBlock.objects.filter(
            status__in=['scheduled', 'active'],
            start_time__date__lte=t_end, end_time__date__gte=t_start,
        ).values_list('room_id', flat=True)

        # การจองจำกัดแค่ห้องที่มีข้อมูล AI จริงเสมอ ไม่ว่าใครจะเป็นคนจอง
        available = Room.objects.filter(
            is_active=True, status='available', capacity__gte=d['attendees'], id__in=AI_FORECAST_ROOM_IDS,
        ).exclude(id__in=set(list(booked_term) + list(maint_blocked))).select_related('building')\
         .prefetch_related('room_facilities__facility', 'forecasts')

        if d.get('room_type'):
            available = available.filter(room_type=d['room_type'])
        if d.get('building_code'):
            preferred = list(available.filter(building__code=d['building_code']).order_by('capacity'))
            others    = list(available.exclude(building__code=d['building_code']).order_by('capacity'))
            results   = preferred + others
        else:
            results = list(available.order_by('capacity'))

        today = date_type.today()
        forecast_target_date = today
        for i in range(14):
            test_date = today + timedelta(days=i)
            if test_date.weekday() == dow:
                forecast_target_date = test_date
                break

        enriched = self._enrich_rooms(results, forecast_target_date, d['start_time'], d['end_time'], 'term', request)
        for room_data in enriched:
            conflict_count = Booking.objects.filter(
                room_id=room_data['id'],
                start_time__week_day=(dow + 2) % 7 or 7,
                status__in=['completed', 'approved'],
            ).exclude(start_time__time__gte=d['end_time'])\
             .exclude(end_time__time__lte=d['start_time']).count()
            room_data['term_conflict_count'] = conflict_count

        return Response(enriched)

    def _enrich_rooms(self, rooms, target_date, start_time, end_time, booking_type, request):
        result = []
        start_hour = start_time.hour
        end_hour   = end_time.hour
        if end_time.minute > 0:
            end_hour += 1
        check_end_hour = end_hour if end_hour > start_hour else start_hour + 1
        level_order = {'low': 0, 'medium': 1, 'high': 2, 'urgent': 3}

        for room in rooms:
            all_forecasts = list(room.forecasts.all())
            forecasts = [
                f for f in all_forecasts
                if f.forecast_date == target_date and start_hour <= f.hour < check_end_hour
            ]
            room_data = RoomSerializer(room, context={'request': request}).data
            room_data['building_name'] = room.building.name if room.building else "ไม่ระบุอาคาร"
            room_data['historical_demand_count'] = getattr(room, 'historical_demand_count', 0)
            room_data['booking_type'] = booking_type

            if forecasts:
                count    = len(forecasts)
                avg_pred = sum(f.predicted_demand for f in forecasts) / count
                avg_term = sum(f.term_demand for f in forecasts) / count
                avg_dyn  = sum(f.dynamic_demand for f in forecasts) / count
                avg_conf = sum(f.confidence for f in forecasts) / count
                if avg_pred >= 0.70:   final_level, final_avail = 'urgent', 'book_now'
                elif avg_pred >= 0.50: final_level, final_avail = 'high',   'book_soon'
                elif avg_pred >= 0.30: final_level, final_avail = 'medium', 'recommended'
                else:                  final_level, final_avail = 'low',    'likely_available'
                room_data['forecast'] = {
                    'demand_level': final_level, 'availability': final_avail,
                    'predicted_demand': round(avg_pred, 4), 'term_demand': round(avg_term, 4),
                    'dynamic_demand': round(avg_dyn, 4), 'confidence': round(avg_conf, 1),
                    'has_forecast': True,
                }
            else:
                room_data['forecast'] = {
                    'demand_level': 'low', 'availability': 'likely_available',
                    'predicted_demand': 0.0, 'term_demand': 0.0,
                    'dynamic_demand': 0.0, 'confidence': 0.0, 'has_forecast': False,
                }
            result.append(room_data)

        result.sort(key=lambda r: level_order.get(r['forecast']['demand_level'], 0))
        return result

    def _score_suggestion(self, room, query):
        haystacks = [
            room.name or '',
            room.building.name if room.building else '',
            room.building.code if room.building else '',
            room.room_type or '',
            f"{room.name or ''} {room.building.name if room.building else ''} {room.building.code if room.building else ''}",
        ]
        q = self._normalize_query(query)
        if not q:
            return 0.0

        best = 0.0
        for text in haystacks:
            candidate = self._normalize_query(text)
            if not candidate:
                continue
            ratio = SequenceMatcher(None, q, candidate).ratio()
            best = max(best, ratio)
            if q in candidate:
                best = max(best, min(1.0, ratio + 0.35))
            q_tokens = set(q.split())
            if q_tokens:
                candidate_tokens = set(candidate.split())
                overlap = len(q_tokens & candidate_tokens) / len(q_tokens)
                best = max(best, ratio * 0.7 + overlap * 0.3)
        return round(best, 4)

    def _normalize_query(self, value):
        return re.sub(r'\s+', ' ', (value or '').strip().lower())

    def _blocked_room_ids(self, target_date, start_time, end_time):
        """ห้องที่ถูกจอง/ซ่อมบำรุง/จองเทอม ในช่วงเวลาที่ระบุ"""
        start_dt   = timezone.make_aware(datetime.combine(target_date, start_time))
        end_dt     = timezone.make_aware(datetime.combine(target_date, end_time))
        target_dow = target_date.weekday()

        booked_dynamic = set(Booking.objects.filter(
            status__in=['pending', 'approved', 'checked_in'],
            start_time__lt=end_dt, end_time__gt=start_dt,
        ).values_list('room_id', flat=True))

        maint_blocked = set(MaintenanceBlock.objects.filter(
            status__in=['scheduled', 'active'],
            start_time__lt=end_dt, end_time__gt=start_dt,
        ).values_list('room_id', flat=True))

        booked_term = set(TermBooking.objects.filter(
            day_of_week=target_dow, status='active',
            term_start__lte=target_date, term_end__gte=target_date,
        ).exclude(start_time__gte=end_time).exclude(end_time__lte=start_time)
         .values_list('room_id', flat=True))

        return booked_dynamic | maint_blocked | booked_term

    def _score_similar_room(self, room, attendees, building_code=None, room_type=None):
        if room.capacity < attendees:
            return None, []
        score   = max(0, 50 - (room.capacity - attendees) * 2)
        reasons = [f'รองรับ {room.capacity} คน']
        if building_code and room.building.code == building_code:
            score += 40
            reasons.append(f'อาคาร {room.building.name}')
        elif building_code:
            score += 12
            reasons.append(f'อาคารใกล้เคียง ({room.building.name})')
        else:
            reasons.append(room.building.name)
        if room_type and room_type.lower() in (room.room_type or '').lower():
            score += 25
            reasons.append('ประเภทห้องตรงที่ต้องการ')
        elif room_type:
            score += 8
            reasons.append(f'ประเภท {room.room_type}')
        return score, reasons

    def _find_similar_dynamic_rooms(self, d, request, max_results=8):
        """
        หาห้องว่างใกล้เคียงเมื่อค้นหาปกติไม่เจอหรือไม่มี AI forecast
        ลำดับ: ช่วงเวลาเดิม → ขยายความจุ → ช่วงเวลาใกล้เคียง ±30/60 นาที
        """
        from datetime import time as time_type, timedelta as td

        target_date   = d['date']
        start_time    = d['start_time']
        end_time      = d['end_time']
        attendees     = d['attendees']
        building_code = (d.get('building_code') or '').strip()
        room_type     = (d.get('room_type') or '').strip()

        # การจองจำกัดแค่ห้องที่มีข้อมูล AI จริงเสมอ — เหมือน _search_dynamic/_search_term
        base_qs = Room.objects.filter(
            is_active=True, status='available', id__in=AI_FORECAST_ROOM_IDS,
        ).select_related('building').prefetch_related(
            'room_facilities__facility', 'forecasts',
        )

        def collect_for_slot(st, et, time_label=None):
            blocked = self._blocked_room_ids(target_date, st, et)
            candidates = base_qs.filter(capacity__gte=attendees).exclude(id__in=blocked)
            scored = []
            for room in candidates:
                sc, reasons = self._score_similar_room(
                    room, attendees, building_code or None, room_type or None,
                )
                if sc is None:
                    continue
                if not time_label:
                    reasons.insert(0, 'ว่างตามเวลาที่เลือก')
                else:
                    reasons.insert(0, time_label)
                scored.append((sc, room, ' · '.join(reasons[:4])))
            scored.sort(key=lambda x: (-x[0], x[1].capacity))
            return scored

        # Tier 1: exact time
        all_scored = collect_for_slot(start_time, end_time)

        # Tier 2: relaxed capacity (ยังว่างช่วงเดิม แต่ห้องใหญ่ขึ้น)
        if len(all_scored) < max_results:
            blocked = self._blocked_room_ids(target_date, start_time, end_time)
            relaxed = base_qs.exclude(id__in=blocked).filter(
                capacity__gte=max(1, attendees - 2),
            )
            seen = {r.id for _, r, _ in all_scored}
            for room in relaxed:
                if room.id in seen or room.capacity < attendees:
                    continue
                sc, reasons = self._score_similar_room(
                    room, attendees, building_code or None, room_type or None,
                )
                if sc is None:
                    sc = 5
                    reasons = [f'รองรับ {room.capacity} คน (ขยายจากเงื่อนไขเดิม)']
                reasons.insert(0, 'ว่างตามเวลาที่เลือก')
                all_scored.append((sc - 5, room, ' · '.join(reasons[:4])))
                seen.add(room.id)

        # Tier 3: ช่วงเวลาใกล้เคียง ±30 / ±60 นาที
        if len(all_scored) < max_results:
            st_dt = datetime.combine(target_date, start_time)
            et_dt = datetime.combine(target_date, end_time)
            duration = et_dt - st_dt
            offsets = [30, -30, 60, -60]
            seen = {r.id for _, r, _ in all_scored}
            for mins in offsets:
                new_st = (st_dt + td(minutes=mins)).time()
                new_et = (st_dt + td(minutes=mins) + duration).time()
                if new_st >= new_et:
                    continue
                label = f'เวลาใกล้เคียง {new_st.strftime("%H:%M")}–{new_et.strftime("%H:%M")}'
                for sc, room, reason in collect_for_slot(new_st, new_et, label):
                    if room.id in seen:
                        continue
                    all_scored.append((sc - 15, room, reason))
                    seen.add(room.id)
                    if len(all_scored) >= max_results * 2:
                        break

        all_scored.sort(key=lambda x: (-x[0], x[1].capacity))
        top_rooms = [r for _, r, _ in all_scored[:max_results]]

        enriched = []
        if top_rooms:
            enriched = self._enrich_rooms(
                top_rooms, target_date, start_time, end_time, 'dynamic', request,
            )
            reason_map = {r.id: reason for _, r, reason in all_scored[:max_results]}
            for item in enriched:
                item['is_similar_recommendation'] = True
                item['recommendation_reason'] = reason_map.get(item['id'], 'ห้องใกล้เคียงที่ว่าง')

        # Tier 4: วันเดียวกันหาห้องไม่ได้เลย (หรือได้ไม่ครบ) — ลองห้องเดิม/ห้องใกล้
        # เคียงแบบเดียวกันแต่ขยับไปวันอื่นแทน (พรุ่งนี้ / มะรืนนี้ / 3 วันถัดไป) คนละ
        # เรื่องกับ Tier 3 ที่ขยับแค่ "เวลา" ในวันเดิม — นี่ขยับ "วัน" ทั้งวัน แต่ละ
        # วันมีวันที่ไม่เหมือนกัน เลย enrich แยกทีละวันแทนที่จะโยนรวมกับ top_rooms
        # ข้างบน (ซึ่ง _enrich_rooms รับวันที่เดียวสำหรับทุกห้องในก้อนเดียวกัน)
        day_suggestions = []
        if len(enriched) < max_results:
            seen_ids = {item['id'] for item in enriched}
            for days_ahead in (1, 2, 3):
                if len(enriched) + len(day_suggestions) >= max_results:
                    break
                other_date = target_date + td(days=days_ahead)
                blocked_other_day = self._blocked_room_ids(other_date, start_time, end_time)
                candidates = base_qs.filter(capacity__gte=attendees).exclude(id__in=blocked_other_day)
                day_scored = []
                for room in candidates:
                    if room.id in seen_ids:
                        continue
                    sc, _ = self._score_similar_room(room, attendees, building_code or None, room_type or None)
                    if sc is None:
                        continue
                    day_scored.append((sc, room))
                day_scored.sort(key=lambda x: (-x[0], x[1].capacity))
                day_label = other_date.strftime('%d/%m')
                for sc, room in day_scored:
                    if len(enriched) + len(day_suggestions) >= max_results:
                        break
                    day_enriched = self._enrich_rooms([room], other_date, start_time, end_time, 'dynamic', request)
                    for item in day_enriched:
                        item['is_similar_recommendation'] = True
                        item['recommendation_reason'] = f'ห้องเดิมว่าง แต่คนละวัน — {day_label}'
                        item['suggested_date'] = other_date.isoformat()
                        day_suggestions.append(item)
                    seen_ids.add(room.id)

        return enriched + day_suggestions

    def _rooms_free_until(self, room_ids, target_date, now_time):
        """เวลาที่แต่ละห้อง 'ว่างไปจนถึง' จริงๆ นับจากตอนนี้ — เวลาเริ่มของงานถัดไป
        (จอง/ซ่อมบำรุง/ล็อกทั้งเทอม) ที่ใกล้ที่สุดวันนี้ หรือ 23:59 ถ้าไม่มีอะไรเหลือแล้ว
        แต่ละห้องว่างไม่เท่ากัน ไม่ควรเหมาว่าทุกห้องว่างแค่ 1 ชม.เท่ากันหมด

        คำนวณทีเดียวหลายห้อง (3 query รวม แทนที่จะเป็น 3 query ต่อห้อง — กัน N+1
        ตอนฟีดมีหลายห้อง) คืนค่าเป็น dict {room_id: time}"""
        from datetime import time as time_type

        day_end = time_type(23, 59)
        result = {rid: day_end for rid in room_ids}

        def apply_earliest(rows, extract_time):
            for room_id, start_time in rows:
                t = extract_time(start_time)
                if t < result[room_id]:
                    result[room_id] = t

        booking_rows = Booking.objects.filter(
            room_id__in=room_ids, status__in=['pending', 'approved', 'checked_in'],
            start_time__date=target_date, start_time__time__gt=now_time,
        ).values_list('room_id', 'start_time')
        apply_earliest(booking_rows, lambda dt: timezone.localtime(dt).time())

        maint_rows = MaintenanceBlock.objects.filter(
            room_id__in=room_ids, status__in=['scheduled', 'active'],
            start_time__date=target_date, start_time__time__gt=now_time,
        ).values_list('room_id', 'start_time')
        apply_earliest(maint_rows, lambda dt: timezone.localtime(dt).time())

        target_dow = target_date.weekday()
        term_rows = TermBooking.objects.filter(
            room_id__in=room_ids, day_of_week=target_dow, status='active',
            term_start__lte=target_date, term_end__gte=target_date,
            start_time__gt=now_time,
        ).values_list('room_id', 'start_time')
        apply_earliest(term_rows, lambda dt: dt)

        return result

    @action(detail=False, methods=['get'], url_path='today-feed')
    def today_feed(self, request):
        """ห้องว่าง ณ ตอนนี้ สำหรับฟีดแนะนำในหน้าแรก — จำกัดแค่ห้องที่มีข้อมูล AI
        จริงเหมือนเส้นทางจองอื่นๆ (ดู AI_FORECAST_ROOM_IDS)

        แต่ละห้องโชว์เวลาที่ว่างจริงของตัวเอง (ไม่ใช่ล็อกไว้ 1 ชม.เท่ากันหมด) — บาง
        ห้องว่างแค่ 20 นาที บางห้องว่างยาว 3 ชม. ก็ควรเห็นต่างกัน กันคนเข้าใจผิดว่า
        ห้องที่จริงว่างนานกว่านั้นมาก ดันโชว์แค่ 1 ชม.

        ?limit=N (default 5) — หน้าแรกใช้ค่า default โชว์ตัวอย่างสั้นๆ ส่วน "ดูทั้งหมด"
        ส่ง limit สูงๆ มาแทน (หรือ 0 = ไม่จำกัด) เพื่อเห็นห้องว่างตอนนี้ทั้งหมดจริง
        """
        now = timezone.localtime()
        today = now.date()
        now_time = now.time()

        try:
            limit = int(request.query_params.get('limit', 5))
        except (TypeError, ValueError):
            limit = 5

        # เช็คว่างเฉพาะ ณ ตอนนี้ (หน้าต่างแคบๆ 1 นาที) ไม่บังคับว่าต้องว่างยาวเป็น
        # ชม. — ระยะที่ว่างจริงของแต่ละห้องคำนวณแยกด้านล่างด้วย _room_free_until
        instant_end = (datetime.combine(today, now_time) + timedelta(minutes=1)).time()
        blocked = self._blocked_room_ids(today, now_time, instant_end)
        qs = (
            Room.objects.filter(
                is_active=True, status='available', id__in=AI_FORECAST_ROOM_IDS,
            ).exclude(id__in=blocked).select_related('building')
            .prefetch_related('room_facilities__facility', 'forecasts')
            .order_by('capacity')
        )
        rooms = list(qs) if limit <= 0 else list(qs[:limit])

        enriched = self._enrich_rooms(rooms, today, now_time, instant_end, 'dynamic', request)
        # _enrich_rooms ใช้ start_time/end_time แค่กรอง forecast ข้างในเฉยๆ ไม่ได้
        # แนบกลับมาในผลลัพธ์ — ฟีดนี้ต้องโชว์ช่วงเวลาที่ว่างจริงในการ์ดด้วย
        # (จับคู่ด้วย room id เพราะ _enrich_rooms เรียง result ใหม่ตาม demand
        # level ไม่ใช่ลำดับเดิมของ rooms อีกแล้ว)
        free_until_map = self._rooms_free_until([item['id'] for item in enriched], today, now_time)
        for item in enriched:
            item['available_from'] = now_time.strftime('%H:%M')
            item['available_until'] = free_until_map[item['id']].strftime('%H:%M')
        return Response(enriched)

    @action(detail=False, methods=['post'], url_path='dynamic-recommend')
    def dynamic_recommend(self, request):
        """
        แนะนำห้องจองรายวันใกล้เคียง — ใช้เมื่อค้นหาปกติไม่พบห้องหรือไม่มี AI forecast
        """
        ser = RoomSearchSerializer(data={**request.data, 'booking_type': 'dynamic'})
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        suggestions = self._find_similar_dynamic_rooms(d, request)
        return Response({
            'count':       len(suggestions),
            'suggestions': suggestions,
            'message':     (
                'พบห้องใกล้เคียงที่ว่าง — เลือกจองได้ทันที'
                if suggestions else
                'ไม่พบห้องใกล้เคียงในช่วงเวลานี้ ลองเปลี่ยนวันหรือเวลา'
            ),
        })

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        room = self.get_object()
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({'error': 'กรุณาระบุวันที่ (YYYY-MM-DD)'}, status=400)
        try:
            target_date = date_type.fromisoformat(date_str)
        except ValueError:
            return Response({'error': 'รูปแบบวันที่ไม่ถูกต้อง'}, status=400)

        return Response({
            'room': room.name, 'date': target_date,
            'dynamic_bookings': list(Booking.objects.filter(
                room=room, status='approved', start_time__date=target_date,
            ).values('start_time', 'end_time', 'title', 'attendees')),
            'term_bookings': list(TermBooking.objects.filter(
                room=room, status='active', day_of_week=target_date.weekday(),
                term_start__lte=target_date, term_end__gte=target_date,
            ).values('subject_name', 'start_time', 'end_time', 'attendees', 'term_name')),
            'forecasts': list(room.forecasts.filter(forecast_date=target_date).values(
                'hour', 'demand_level', 'availability', 'predicted_demand', 'term_demand', 'dynamic_demand'
            )),
        })

    @action(detail=False, methods=['get'], url_path='equipment-filters')
    def equipment_filters(self, request):
        """
        ตัวกรองอุปกรณ์สำหรับหน้าค้นหา — อิง Facility master จริงใน DB
        คืนหมวดหลักก่อน แล้วเติมรายการ master ทั้งหมดเพื่อไม่ให้ตัวเลือกตกหล่น
        """
        facility_rows = list(Facility.objects.order_by('name').values('id', 'name'))
        active_names = set(
            Facility.objects.filter(roomfacility__room__is_active=True)
            .values_list('name', flat=True)
            .distinct()
        )
        names = [row['name'] for row in facility_rows]
        names_lower = [n.lower() for n in names]

        categories = [
            {'key': 'computer',  'label': 'คอมพิวเตอร์',              'icon': '💻',
             'keywords': ['คอมพิวเตอร์', 'computer', 'pc ', 'pc |', 'pc', 'imac']},
            {'key': 'projector', 'label': 'โปรเจกเตอร์',              'icon': '📽️',
             'keywords': ['โปรเจกเตอร์', 'โปรเจคเตอร์', 'projector']},
            {'key': 'microphone','label': 'ไมโครโฟน',                 'icon': '🎤',
             'keywords': ['ไมโครโฟน', 'microphone', 'ไมค์']},
            {'key': 'sound',     'label': 'ระบบเสียง',                'icon': '🔊',
             'keywords': ['ระบบเสียง', 'เครื่องเสียง', 'ลำโพง', 'mixer']},
            {'key': 'tv',        'label': 'TV / จอแสดงผล',            'icon': '📺',
             'keywords': ['tv', 'จอแสดงผล', 'จอ ', 'จอแขวน', 'จอมอเตอร์', 'จอไฟฟ้า', 'นิ้ว']},
            {'key': 'flipboard', 'label': 'Flipboard',                'icon': '📋',
             'keywords': ['flipboard', 'flip2']},
            {'key': 'video_conf','label': 'Video Conference',         'icon': '📹',
             'keywords': ['video conference', 'วีดีโอ', 'vdo', 'webcam', 'zoom', 'teams', 'meet']},
            {'key': 'interactive','label': 'โปรเจกเตอร์อินเทอร์แอคทีฟ', 'icon': '🖊️',
             'keywords': ['อินเทอร์แอคทีฟ', 'interactive', 'touch screen']},
        ]

        for cat in categories:
            cat['group_key'] = cat['key']
            cat['group_label'] = cat['label']
            cat['is_category'] = True

        available = [
            cat for cat in categories
            if any(
                kw in name
                for name in names_lower
                for kw in cat['keywords']
            )
        ]

        def get_group(name):
            name_lower = name.lower()
            for cat in categories:
                if any(kw in name_lower for kw in cat['keywords']):
                    return cat
            return {'key': 'other', 'label': 'อุปกรณ์อื่นๆ', 'icon': '🔧'}

        master_filters = [
            {
                'key': f'facility_{row["id"]}',
                'label': row['name'],
                'icon': get_group(row['name'])['icon'],
                'keywords': [row['name']],
                'is_master': True,
                'group_key': get_group(row['name'])['key'],
                'group_label': get_group(row['name'])['label'],
                'has_active_room': row['name'] in active_names,
            }
            for row in facility_rows
        ]

        return Response({
            'filters': available + master_filters,
            'facility_names': names,
            'active_facility_names': sorted(active_names),
        })

    @action(detail=False, methods=['get'], url_path='admin-status')
    def admin_status(self, request):
        """รายการห้องจริงจาก DB สำหรับ Admin (แทน ALL_ROOMS_DATA mock)"""
        if getattr(request.user, 'role', None) not in ['admin', 'staff']:
            return Response({'error': 'สำหรับผู้ดูแลระบบเท่านั้น'}, status=403)

        rooms = Room.objects.select_related('building')
        total_bookings = Booking.objects.filter(status__in=['approved', 'completed']).count() or 1
        result = []
        for room in rooms:
            cnt = Booking.objects.filter(room=room, status__in=['approved', 'completed']).count()
            result.append({
                'id':           room.id,
                'name':         room.name,
                'code':         room.name,
                'building':     room.building.name if room.building else 'ไม่ระบุ',
                'building_id':  room.building_id,
                'building_code': room.building.code if room.building else '',
                'floor':        room.floor,
                'capacity':     room.capacity,
                'room_type':    room.room_type,
                'status':       room.status,
                'util_rate':    round(cnt / total_bookings, 4),
                'booking_count': cnt,
            })
        return Response(result)


# ============================================================
# TERM BOOKING ViewSet
# ============================================================
def _recurring_slot_conflicts(local_start, local_end, day_of_week, start_time, end_time, term_start, term_end):
    """
    เช็คว่าเหตุการณ์ครั้งเดียว (Booking/MaintenanceBlock ที่มี start/end เป็น
    datetime จริง) ชนกับ slot รายสัปดาห์ของ TermBooking (day_of_week +
    start_time/end_time ซ้ำทุกสัปดาห์ตลอด [term_start, term_end]) ไหม
    """
    if local_start.date() == local_end.date():
        d = local_start.date()
        if not (term_start <= d <= term_end):
            return False
        if d.weekday() != day_of_week:
            return False
        return local_start.time() < end_time and local_end.time() > start_time
    # เหตุการณ์ข้ามวัน (เช่น ปิดซ่อมบำรุงยาวหลายวัน) — ถือว่าชนถ้ามีวันไหน
    # ในช่วงตรงกับ day_of_week และอยู่ในช่วงเทอม (ระมัดระวังไว้ก่อน ไม่เช็ค
    # เวลาละเอียดในกรณีนี้ เพราะห้องถูกกันทั้งวันอยู่แล้วในทางปฏิบัติ)
    cur = local_start.date()
    while cur <= local_end.date():
        if term_start <= cur <= term_end and cur.weekday() == day_of_week:
            return True
        cur += timedelta(days=1)
    return False


class TermBookingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = TermBooking.objects.select_related('user', 'room__building')
        if user.is_authenticated:
            user_role = getattr(user, 'role', None)
            if user_role not in ['admin', 'staff']:
                qs = qs.filter(user=user)
        else:
            qs = qs.filter(status='active')

        room   = self.request.query_params.get('room')
        dow    = self.request.query_params.get('day_of_week')
        term   = self.request.query_params.get('term_name')
        active = self.request.query_params.get('active_only')
        if room:         qs = qs.filter(room_id=room)
        if dow is not None: qs = qs.filter(day_of_week=dow)
        if term:         qs = qs.filter(term_name__icontains=term)
        if active:
            today = date_type.today()
            qs = qs.filter(status='active', term_start__lte=today, term_end__gte=today)
        return qs

    def get_serializer_class(self):
        return TermBookingCreateSerializer if self.action == 'create' else TermBookingSerializer

    def perform_create(self, serializer):
        room        = serializer.validated_data['room']
        day_of_week = serializer.validated_data['day_of_week']
        start_time  = serializer.validated_data['start_time']
        end_time    = serializer.validated_data['end_time']
        term_start  = serializer.validated_data['term_start']
        term_end    = serializer.validated_data['term_end']

        with transaction.atomic():
            Room.objects.select_for_update().get(pk=room.pk)

            if TermBooking.objects.filter(
                room=room,
                day_of_week=day_of_week,
                status='active',
                term_start__lte=term_end,
                term_end__gte=term_start,
            ).exclude(
                start_time__gte=end_time
            ).exclude(
                end_time__lte=start_time
            ).exists():
                raise ValidationError({'detail': 'ห้องนี้มีการจองทั้งเทอมซ้อนในช่วงเวลาเดียวกันแล้ว'})

            # เช็คซ้อนกับ Booking รายวัน — Booking.start_time เป็น datetime จริง
            # ครั้งเดียว ต่างจาก TermBooking ที่ซ้ำทุกสัปดาห์ เลยต้องไล่เช็คทีละ
            # รายการว่าตรงกับ day_of_week/ช่วงเวลาที่จะจองทั้งเทอมไหม
            candidate_bookings = Booking.objects.filter(
                room=room,
                status__in=['pending', 'approved', 'checked_in'],
                start_time__date__lte=term_end,
                end_time__date__gte=term_start,
            )
            for b in candidate_bookings:
                local_start = timezone.localtime(b.start_time)
                local_end   = timezone.localtime(b.end_time)
                if _recurring_slot_conflicts(local_start, local_end, day_of_week, start_time, end_time, term_start, term_end):
                    raise ValidationError({'detail': f'ห้องนี้มีการจองรายวัน "{b.title}" ซ้อนกับวันและเวลาที่เลือกในบางสัปดาห์'})

            candidate_blocks = MaintenanceBlock.objects.filter(
                room=room,
                status__in=['scheduled', 'active'],
                start_time__date__lte=term_end,
                end_time__date__gte=term_start,
            )
            for mb in candidate_blocks:
                local_start = timezone.localtime(mb.start_time)
                local_end   = timezone.localtime(mb.end_time)
                if _recurring_slot_conflicts(local_start, local_end, day_of_week, start_time, end_time, term_start, term_end):
                    raise ValidationError({'detail': 'ห้องนี้ปิดซ่อมบำรุงซ้อนกับวันและเวลาที่เลือกในบางสัปดาห์'})

            term_booking = serializer.save(user=self.request.user, status='active')
            Notification.objects.create(
                user=self.request.user, term_booking=term_booking,
                type='term_approved', title='จองห้องทั้งเทอมสำเร็จ',
                message=(f'จองห้อง {term_booking.room.name} สำหรับ "{term_booking.subject_name}" '
                         f'ทุกวัน{term_booking.get_day_of_week_display()} '
                         f'{term_booking.start_time:%H:%M}–{term_booking.end_time:%H:%M} '
                         f'ตั้งแต่ {term_booking.term_start} ถึง {term_booking.term_end}')
            )

    def destroy(self, request, *args, **kwargs):
        tb = self.get_object()
        if tb.user != request.user and getattr(request.user, 'role', None) not in ['admin', 'staff']:
            return Response({'error': 'ไม่มีสิทธิ์'}, status=403)
        if tb.status == 'cancelled':
            return Response({'error': 'ยกเลิกไปแล้ว'}, status=400)
        tb.status = 'cancelled'
        tb.save()
        BookingLog.objects.create(
            term_booking=tb, changed_by=request.user,
            old_status='active', new_status='cancelled'
        )
        return Response({'message': 'ยกเลิกการจองทั้งเทอมเรียบร้อยแล้ว'})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if getattr(request.user, 'role', None) not in ['admin', 'staff']:
            return Response({'error': 'ไม่มีสิทธิ์'}, status=403)
        tb = self.get_object()
        tb.status = 'active'
        tb.approved_by = request.user
        tb.save()
        return Response({'message': 'อนุมัติการจองทั้งเทอมแล้ว'})

    @action(detail=False, methods=['get'])
    def calendar(self, request):
        today = date_type.today()
        qs = TermBooking.objects.filter(
            status='active', term_start__lte=today, term_end__gte=today,
        ).select_related('room__building', 'user')
        room = request.query_params.get('room')
        if room:
            qs = qs.filter(room_id=room)
        days = {i: [] for i in range(7)}
        for tb in qs:
            days[tb.day_of_week].append({
                'id': tb.id, 'room': tb.room.name, 'building': tb.room.building.name,
                'subject_name': tb.subject_name, 'subject_code': tb.subject_code,
                'start_time': tb.start_time.strftime('%H:%M'),
                'end_time':   tb.end_time.strftime('%H:%M'),
                'attendees':  tb.attendees, 'user': tb.user.get_full_name(),
            })
        day_names = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
        return Response({
            day_names[i]: sorted(slots, key=lambda x: x['start_time'])
            for i, slots in days.items()
        })

    @action(detail=False, methods=['post'], url_path='split-recommend')
    def split_recommend(self, request):
        """
        แนะนำจองทั้งเทอมแบบสลับห้อง: ครึ่งเทอมแรกห้อง A ครึ่งเทอมหลังห้อง B
        เมื่อห้องเดียวไม่ว่างตลอดเทอม
        """
        room_id    = request.data.get('room')
        building_code = request.data.get('building_code')
        dow        = request.data.get('day_of_week')
        start_time = request.data.get('start_time')
        end_time   = request.data.get('end_time')
        term_start = request.data.get('term_start')
        term_end   = request.data.get('term_end')
        attendees  = request.data.get('attendees', 30)

        if not all([dow is not None, start_time, end_time, term_start, term_end]):
            return Response({'error': 'กรุณาระบุ day_of_week, start_time, end_time, term_start, term_end'},
                            status=400)

        try:
            t_start = date_type.fromisoformat(str(term_start))
            t_end   = date_type.fromisoformat(str(term_end))
            start_t = datetime.strptime(str(start_time), '%H:%M').time() if len(str(start_time)) <= 5 \
                 else datetime.strptime(str(start_time), '%H:%M:%S').time()
            end_t = datetime.strptime(str(end_time), '%H:%M').time() if len(str(end_time)) <= 5 \
                 else datetime.strptime(str(end_time), '%H:%M:%S').time()
            preferred_room_id = int(room_id) if room_id not in (None, '') else None
        except ValueError as e:
            return Response({'error': f'รูปแบบวันที่/เวลาไม่ถูกต้อง: {e}'}, status=400)
        except TypeError:
            preferred_room_id = None

        mid = t_start + (t_end - t_start) // 2
        first_end = mid
        second_start = mid + timedelta(days=1)

        preferred_room = None
        if preferred_room_id is not None:
            preferred_room = Room.objects.filter(
                id=preferred_room_id, is_active=True, status='available', id__in=AI_FORECAST_ROOM_IDS,
            ).select_related('building').first()

        def is_room_blocked(room_obj, period_start, period_end):
            return TermBooking.objects.filter(
                room=room_obj,
                day_of_week=dow, status='active',
                term_start__lte=period_end, term_end__gte=period_start,
            ).exclude(start_time__gte=end_t).exclude(end_time__lte=start_t).exists()

        def room_score(room_obj, period_start, period_end):
            if is_room_blocked(room_obj, period_start, period_end):
                return None
            gap = max(0, int(room_obj.capacity or 0) - int(attendees))
            score = 0

            # ความจุใกล้เคียงคือดีที่สุด
            if gap == 0:
                score += 45
            elif gap <= 3:
                score += 38
            elif gap <= 8:
                score += 30
            elif gap <= 15:
                score += 22
            else:
                score += max(8, 18 - min(gap, 25) // 2)

            # ห้องที่อยู่ในอาคารเดียวกับห้องเดิม/อาคารที่เลือก ให้คะแนนเพิ่ม
            if preferred_room and preferred_room.building_id == room_obj.building_id:
                score += 14
            if building_code and room_obj.building and room_obj.building.code == building_code:
                score += 18
            elif building_code and room_obj.building and room_obj.building.code != building_code:
                score += 2

            # ถ้าจองทั้งเทอม ควรเลือกห้องเรียนมากกว่าห้องพิเศษ
            room_type = (room_obj.room_type or '').lower()
            if any(k in room_type for k in ['classroom', 'lecture', 'ห้องเรียน']):
                score += 10

            # ให้ห้องที่ผู้ใช้ระบุไว้เป็นตัวเลือกนำ ถ้ามันยังใช้ได้ในครึ่งช่วงนั้น
            if preferred_room and room_obj.id == preferred_room.id:
                score += 30
            elif preferred_room and room_obj.building_id == preferred_room.building_id:
                score += 6

            return score

        # การจองจำกัดแค่ห้องที่มีข้อมูล AI จริงเสมอ — เหมือน _search_dynamic/_search_term
        base_qs = Room.objects.filter(
            is_active=True,
            status='available',
            capacity__gte=attendees,
            id__in=AI_FORECAST_ROOM_IDS,
        ).select_related('building')
        if building_code:
            preferred_rooms = list(base_qs.filter(building__code=building_code).order_by('capacity', 'name'))
            other_rooms = list(base_qs.exclude(building__code=building_code).order_by('capacity', 'name'))
            candidates = preferred_rooms + other_rooms
        else:
            candidates = list(base_qs.order_by('capacity', 'name'))

        def rank_candidates(period_start, period_end):
            ranked = []
            for room_obj in candidates:
                score = room_score(room_obj, period_start, period_end)
                if score is None:
                    continue
                ranked.append((score, room_obj))
            ranked.sort(key=lambda item: (-item[0], item[1].capacity or 0, item[1].name))
            return ranked[:8]

        first_rooms = rank_candidates(t_start, first_end)
        second_rooms = rank_candidates(second_start, t_end)

        suggestions = []
        for first_score, r1 in first_rooms:
            for second_score, r2 in second_rooms:
                if r1.id == r2.id:
                    continue
                pair_score = first_score + second_score
                if r1.building_id == r2.building_id:
                    pair_score += 8
                if preferred_room and r1.id == preferred_room.id:
                    pair_score += 10
                if preferred_room and r2.id == preferred_room.id:
                    pair_score += 10
                suggestions.append({
                    'score': pair_score,
                    'first_half': {
                        'room_id': r1.id, 'room_name': r1.name,
                        'building': r1.building.name if r1.building else 'ไม่ระบุ',
                        'term_start': str(t_start), 'term_end': str(first_end),
                    },
                    'second_half': {
                        'room_id': r2.id, 'room_name': r2.name,
                        'building': r2.building.name if r2.building else 'ไม่ระบุ',
                        'term_start': str(second_start), 'term_end': str(t_end),
                    },
                    'message': (
                        f'เทอมแรก ({t_start}–{first_end}): ห้อง {r1.name} | '
                        f'เทอมหลัง ({second_start}–{t_end}): ห้อง {r2.name}'
                    ),
                })
                if len(suggestions) >= 8:
                    break
            if len(suggestions) >= 8:
                break

        suggestions.sort(key=lambda item: item['score'], reverse=True)
        best_split = suggestions[0] if suggestions else None

        return Response({
            'needs_split':    True,
            'term_midpoint':  str(mid),
            'recommended_split': best_split,
            'suggestions':    suggestions,
            'first_half_rooms':  [{'id': r.id, 'name': r.name, 'score': score} for score, r in first_rooms],
            'second_half_rooms': [{'id': r.id, 'name': r.name, 'score': score} for score, r in second_rooms],
            'split_reason': 'ห้องเป้าหมายไม่ว่างตลอดเทอม จึงแนะนำแผนจองสลับห้อง',
        })

    @action(detail=False, methods=['post'], url_path='split-book')
    def split_book(self, request):
        """
        จองทั้งเทอมแบบสลับห้อง — สร้าง TermBooking 2 รายการ (ครึ่งเทอมแรก + ครึ่งเทอมหลัง)
        """
        from django.db import transaction

        data = request.data
        required = [
            'subject_name', 'day_of_week', 'start_time', 'end_time',
            'first_room_id', 'first_term_start', 'first_term_end',
            'second_room_id', 'second_term_start', 'second_term_end',
        ]
        missing = [k for k in required if data.get(k) in (None, '')]
        if missing:
            return Response({'error': f'ข้อมูลไม่ครบ: {", ".join(missing)}'}, status=400)

        try:
            dow = int(data['day_of_week'])
            start_t = datetime.strptime(str(data['start_time']), '%H:%M').time() \
                if len(str(data['start_time'])) <= 5 \
                else datetime.strptime(str(data['start_time']), '%H:%M:%S').time()
            end_t = datetime.strptime(str(data['end_time']), '%H:%M').time() \
                if len(str(data['end_time'])) <= 5 \
                else datetime.strptime(str(data['end_time']), '%H:%M:%S').time()
            f_start = date_type.fromisoformat(str(data['first_term_start']))
            f_end   = date_type.fromisoformat(str(data['first_term_end']))
            s_start = date_type.fromisoformat(str(data['second_term_start']))
            s_end   = date_type.fromisoformat(str(data['second_term_end']))
        except (ValueError, TypeError) as e:
            return Response({'error': f'รูปแบบวันที่/เวลาไม่ถูกต้อง: {e}'}, status=400)

        if start_t >= end_t or f_start >= f_end or s_start >= s_end:
            return Response({'error': 'ช่วงวันที่หรือเวลาไม่ถูกต้อง'}, status=400)
        if f_end >= s_start:
            return Response({'error': 'ช่วงเทอมแรกและเทอมหลังต้องไม่ซ้อนกัน'}, status=400)

        attendees  = int(data.get('attendees', 30))
        term_name  = data.get('term_name', '')
        note_base  = data.get('note', '')
        subject    = data['subject_name']
        subject_code = data.get('subject_code', '')

        common = {
            'user': request.user,
            'subject_name': subject,
            'subject_code': subject_code,
            'attendees': attendees,
            'day_of_week': dow,
            'start_time': start_t,
            'end_time': end_t,
            'term_name': term_name,
            'status': 'active',
        }

        def check_overlap(room_id, t_start, t_end):
            return TermBooking.objects.filter(
                room_id=room_id,
                day_of_week=dow,
                status='active',
                term_start__lte=t_end,
                term_end__gte=t_start,
            ).exclude(start_time__gte=end_t).exclude(end_time__lte=start_t).exists()

        if check_overlap(data['first_room_id'], f_start, f_end):
            return Response({'error': 'ห้องเทอมแรกมีการจองซ้อนในช่วงเวลานี้แล้ว'}, status=400)
        if check_overlap(data['second_room_id'], s_start, s_end):
            return Response({'error': 'ห้องเทอมหลังมีการจองซ้อนในช่วงเวลานี้แล้ว'}, status=400)

        try:
            with transaction.atomic():
                tb1 = TermBooking.objects.create(
                    room_id=data['first_room_id'],
                    term_start=f_start,
                    term_end=f_end,
                    note=(note_base + ' [เทอมแรก — จองสลับห้อง]').strip(),
                    **common,
                )
                tb2 = TermBooking.objects.create(
                    room_id=data['second_room_id'],
                    term_start=s_start,
                    term_end=s_end,
                    note=(note_base + ' [เทอมหลัง — จองสลับห้อง]').strip(),
                    **common,
                )
        except Exception as e:
            return Response({'error': str(e)}, status=400)

        for tb in (tb1, tb2):
            Notification.objects.create(
                user=request.user,
                term_booking=tb,
                type='term_approved',
                title='จองห้องทั้งเทอม (สลับห้อง) สำเร็จ',
                message=(
                    f'จองห้อง {tb.room.name} สำหรับ "{tb.subject_name}" '
                    f'ทุกวัน{tb.get_day_of_week_display()} '
                    f'{tb.start_time:%H:%M}–{tb.end_time:%H:%M} '
                    f'ตั้งแต่ {tb.term_start} ถึง {tb.term_end}'
                ),
            )

        ser = TermBookingSerializer
        return Response({
            'message': 'จองสลับห้องทั้ง 2 ช่วงเรียบร้อยแล้ว',
            'first_booking':  ser(tb1, context={'request': request}).data,
            'second_booking': ser(tb2, context={'request': request}).data,
        }, status=201)


# ============================================================
# DYNAMIC BOOKING ViewSet
# ============================================================
class BookingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # AnonymousUser — กด checkin/cancel จาก email
        if not user.is_authenticated:
            return Booking.objects.all().select_related('user', 'room__building')
        user_role = getattr(user, 'role', None)
        if user_role in ['admin', 'staff']:
            return Booking.objects.all().select_related('user', 'room__building')
        return Booking.objects.filter(user=user).select_related('user', 'room__building')

    def get_serializer_class(self):
        return BookingCreateSerializer if self.action == 'create' else BookingSerializer

    def perform_create(self, serializer):
        room       = serializer.validated_data['room']
        start_time = serializer.validated_data['start_time']
        end_time   = serializer.validated_data['end_time']

        with transaction.atomic():
            # Lock the room row first. Any other request creating a Booking or
            # MaintenanceBlock for this same room also takes this lock before
            # its own overlap check, so concurrent requests serialize instead
            # of both passing the check before either commits (the race the
            # serializer's own validate() — a plain read with no locking —
            # can't close on its own).
            Room.objects.select_for_update().get(pk=room.pk)

            if Booking.objects.filter(
                room=room,
                status__in=['pending', 'approved', 'checked_in'],
                start_time__lt=end_time,
                end_time__gt=start_time,
            ).exists():
                raise ValidationError({'detail': 'ห้องนี้ถูกจองในช่วงเวลาดังกล่าวแล้ว (มีคนจองพร้อมกัน)'})

            target_date = start_time.date()
            target_dow  = target_date.weekday()
            if TermBooking.objects.filter(
                room=room,
                day_of_week=target_dow,
                status='active',
                term_start__lte=target_date,
                term_end__gte=target_date,
            ).exclude(
                start_time__gte=end_time.time()
            ).exclude(
                end_time__lte=start_time.time()
            ).exists():
                raise ValidationError({'detail': 'ห้องนี้ถูกจองทั้งเทอมในช่วงเวลาดังกล่าวแล้ว'})

            if MaintenanceBlock.objects.filter(
                room=room,
                status__in=['scheduled', 'active'],
                start_time__lt=end_time,
                end_time__gt=start_time,
            ).exists():
                raise ValidationError({'detail': 'ห้องนี้ปิดซ่อมบำรุงอยู่ในช่วงเวลาดังกล่าว'})

            booking = serializer.save(user=self.request.user, status='approved')
            Notification.objects.create(
                user=self.request.user, booking=booking,
                type='booking_approved', title='จองห้องสำเร็จ',
                message=(f'จองห้อง {booking.room.name} '
                         f'วันที่ {booking.start_time.astimezone(THAI_TZ).strftime("%d/%m/%Y %H:%M")} '
                         f'เรียบร้อยแล้ว')
            )

    def destroy(self, request, *args, **kwargs):
        return Response({'error': 'ใช้ปุ่ม cancel แทน'}, status=405)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        user_role = getattr(request.user, 'role', None)
        if booking.user != request.user and user_role not in ['admin', 'staff']:
            return Response({'error': 'ไม่มีสิทธิ์'}, status=403)
        if booking.status == 'cancelled':
            return Response({'error': 'ยกเลิกไปแล้ว'}, status=400)
        old = booking.status
        booking.status = 'cancelled'
        booking.save()
        BookingLog.objects.create(
            booking=booking, changed_by=request.user,
            old_status=old, new_status='cancelled'
        )
        return Response({'message': 'ยกเลิกการจองเรียบร้อยแล้ว'})

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        return Response(BookingLogSerializer(self.get_object().logs.all(), many=True).data)

    @action(detail=True, methods=['post'], url_path='check_in')
    def check_in(self, request, pk=None):
        booking = self.get_object()
        user_role = getattr(request.user, 'role', None)

        if booking.user != request.user and user_role not in ['admin', 'staff']:
            return Response({'error': 'ไม่มีสิทธิ์ Check-in การจองนี้'}, status=403)
        if booking.checked_in:
            return Response({'message': 'Check-in ไปแล้ว', 'checked_in': True})
        if booking.status != 'approved':
            return Response({
                'error': 'ไม่สามารถ Check-in ได้',
                'status': booking.status,
            }, status=400)

        now = timezone.now()
        window_start = booking.start_time - timedelta(minutes=15)

        if now < window_start:
            return Response({
                'error': 'ยังไม่ถึงเวลา Check-in',
                'check_in_available_at': window_start,
            }, status=400)

        if now > booking.end_time:
            return Response({'error': 'เลยเวลาการจองแล้ว'}, status=400)

        old = booking.status
        booking.checked_in = True
        booking.checked_in_at = now
        booking.status = 'checked_in'
        booking.save()
        BookingLog.objects.create(
            booking=booking,
            changed_by=request.user,
            old_status=old,
            new_status='checked_in',
        )

        return Response({
            'message': 'Check-in สำเร็จ',
            'checked_in': True,
            'status': booking.status,
        })

    # ─── CHECK-IN via Email Link ───────────────────────────────
    @action(
        detail=True, methods=['get'],
        permission_classes=[AllowAny],
        url_path='checkin/(?P<token>[^/.]+)',
    )
    def checkin(self, request, pk=None, token=None):
        booking = self.get_object()

        if str(booking.checkin_token) != token:
            return HttpResponse(self._html('❌', '#dc2626', 'Link ไม่ถูกต้อง',
                                           'ลิงก์นี้ไม่ถูกต้องหรือหมดอายุแล้วครับ'), status=400)
        if booking.checked_in:
            return HttpResponse(self._html('✅', '#16a34a', 'Check-in ไปแล้ว',
                                           f'คุณ Check-in ห้อง {booking.room.name} ไปแล้วครับ'))
        if booking.status != 'approved':
            return HttpResponse(self._html('❌', '#dc2626', 'ไม่สามารถ Check-in ได้',
                                           f'สถานะการจองปัจจุบัน: {booking.get_status_display()}'), status=400)

        now          = timezone.now()
        window_start = booking.start_time - timedelta(minutes=15)

        if now < window_start:
            window_start_thai = window_start.astimezone(THAI_TZ)
            start_thai        = booking.start_time.astimezone(THAI_TZ)
            return HttpResponse(self._html(
                '⏰', '#d97706', 'ยังไม่ถึงเวลา Check-in',
                f'สามารถ Check-in ได้ตั้งแต่ <b>{window_start_thai.strftime("%H:%M")} น.</b> ครับ<br>'
                f'(ก่อนเวลาเริ่ม {start_thai.strftime("%H:%M")} น. 15 นาที)'
            ), status=400)

        if now > booking.end_time:
            end_thai = booking.end_time.astimezone(THAI_TZ)
            return HttpResponse(self._html('❌', '#dc2626', 'เลยเวลาการจองแล้ว',
                                           f'ไม่สามารถ Check-in ได้หลังเวลาสิ้นสุด ({end_thai.strftime("%H:%M")} น.) ครับ'), status=400)

        booking.checked_in    = True
        booking.checked_in_at = now
        booking.status        = 'checked_in'
        booking.save()
        BookingLog.objects.create(
            booking=booking, changed_by=booking.user,
            old_status='approved', new_status='checked_in'
        )
        start_thai = booking.start_time.astimezone(THAI_TZ)
        end_thai   = booking.end_time.astimezone(THAI_TZ)
        return HttpResponse(self._html(
            '✅', '#16a34a', 'Check-in สำเร็จ!',
            f'ห้อง <b>{booking.room.name}</b><br>'
            f'เวลา <b>{start_thai.strftime("%H:%M")} – {end_thai.strftime("%H:%M")} น.</b><br>'
            f'หัวข้อ: {booking.title}<br><br>ขอให้ประชุมได้ดีนะครับ 🎉'
        ))

    # ─── CANCEL via Email Link (GET = หน้ายืนยัน, POST = ยกเลิกจริง) ──
    @action(
        detail=True, methods=['get', 'post'],
        permission_classes=[AllowAny],
        url_path='cancel-email/(?P<token>[^/.]+)',
    )
    def cancel_email(self, request, pk=None, token=None):
        booking = self.get_object()

        if str(booking.checkin_token) != token:
            return HttpResponse(self._html('❌', '#dc2626', 'Link ไม่ถูกต้อง',
                                           'ลิงก์นี้ไม่ถูกต้องหรือหมดอายุแล้วครับ'), status=400)
        if booking.status == 'cancelled':
            return HttpResponse(self._html('❌', '#6b7280', 'ยกเลิกไปแล้ว',
                                           f'การจองห้อง {booking.room.name} ถูกยกเลิกไปแล้วครับ'))
        if booking.status in ['checked_in', 'completed']:
            return HttpResponse(self._html('❌', '#dc2626', 'ไม่สามารถยกเลิกได้',
                                           f'สถานะปัจจุบัน: {booking.get_status_display()}'), status=400)

        # GET → แสดงหน้ายืนยัน
        if request.method == 'GET':
            start_thai   = booking.start_time.astimezone(THAI_TZ)
            end_thai     = booking.end_time.astimezone(THAI_TZ)
            confirm_url  = request.build_absolute_uri()
            return HttpResponse(f'''
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;">
  <div style="background:white;border-radius:16px;padding:48px 40px;text-align:center;max-width:420px;box-shadow:0 4px 16px rgba(0,0,0,0.1);">
    <div style="font-size:64px;margin-bottom:16px;">🗑️</div>
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);border-radius:4px;margin-bottom:20px;"></div>
    <h1 style="color:#dc2626;margin:0 0 12px;font-size:22px;">ยืนยันการยกเลิกการจอง?</h1>
    <div style="background:#f9fafb;border-radius:10px;padding:16px;margin:16px 0;text-align:left;font-size:15px;line-height:2;">
      <p style="margin:0;">🏢 ห้อง: <b>{booking.room.name}</b></p>
      <p style="margin:0;">📌 หัวข้อ: {booking.title}</p>
      <p style="margin:0;">📅 วันที่: {start_thai.strftime("%d/%m/%Y")}</p>
      <p style="margin:0;">⏰ เวลา: {start_thai.strftime("%H:%M")} – {end_thai.strftime("%H:%M")} น.</p>
    </div>
    <form method="post" action="{confirm_url}">
      <input type="hidden" name="csrfmiddlewaretoken" value="">
      <button type="submit"
        style="background:#dc2626;color:white;border:none;padding:14px 32px;
               border-radius:8px;font-size:16px;font-weight:bold;cursor:pointer;width:100%;margin-bottom:12px;">
        ✅ ยืนยัน ยกเลิกการจอง
      </button>
    </form>
    <p style="color:#9ca3af;font-size:13px;margin-top:8px;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
  </div>
</body>
</html>''')

        # POST → ยกเลิกจริง
        old = booking.status
        booking.status = 'cancelled'
        booking.save()
        BookingLog.objects.create(
            booking=booking, changed_by=booking.user,
            old_status=old, new_status='cancelled'
        )
        return HttpResponse(self._html(
            '✅', '#16a34a', 'ยกเลิกการจองสำเร็จ',
            f'ห้อง <b>{booking.room.name}</b><br>'
            f'หัวข้อ: {booking.title}<br><br>'
            f'หากต้องการจองใหม่ สามารถเข้าระบบได้เลยครับ'
        ))

    @staticmethod
    def _html(icon, color, title, detail):
        return f'''<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;">
  <div style="background:white;border-radius:16px;padding:48px 40px;text-align:center;max-width:400px;box-shadow:0 4px 16px rgba(0,0,0,0.1);">
    <div style="font-size:72px;margin-bottom:16px;">{icon}</div>
    <div style="height:4px;background:linear-gradient(to right,#fde047,#f59e0b);border-radius:4px;margin-bottom:20px;"></div>
    <h1 style="color:{color};margin:0 0 12px;font-size:24px;">{title}</h1>
    <p style="color:#6b7280;font-size:16px;line-height:1.6;">{detail}</p>
    <p style="color:#9ca3af;font-size:13px;margin-top:32px;">ระบบจองห้องประชุม สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
  </div>
</body>
</html>'''


# ============================================================
# NOTIFICATION
# ============================================================
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        n = self.get_object()
        n.is_read = True
        n.save()
        return Response({'status': 'read'})

    @action(detail=False, methods=['post'])
    def read_all(self, request):
        self.get_queryset().update(is_read=True)
        return Response({'status': 'ok'})


# ============================================================
# DEMAND FORECAST
# ============================================================
class DemandForecastViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = DemandForecastSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs   = DemandForecast.objects.all().order_by('forecast_date', 'hour')
        room = self.request.query_params.get('room')
        date = self.request.query_params.get('date')
        if room: qs = qs.filter(room_id=room)
        if date: qs = qs.filter(forecast_date=date)
        return qs


# ============================================================
# MAINTENANCE — Predictive Maintenance Scheduler
# ============================================================
class MaintenanceSlotsView(APIView):
    """คัดกรองช่วง demand ต่ำจาก DemandForecast (LSTM)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if getattr(request.user, 'role', None) not in ['admin', 'staff']:
            return Response({'error': 'สำหรับผู้ดูแลระบบเท่านั้น'}, status=403)

        room_id  = request.query_params.get('room')
        max_dem  = float(request.query_params.get('max_demand', 0.10))
        min_hrs  = int(request.query_params.get('min_hours', 3))
        days     = int(request.query_params.get('days', 14))

        slots = _find_maintenance_slots(
            room_id=int(room_id) if room_id else None,
            max_demand=max_dem,
            min_consecutive_hours=min_hrs,
            days_ahead=days,
        )
        return Response({'slots': slots, 'count': len(slots)})


def _find_maintenance_slots(
    room_id: int | None = None,
    max_demand: float = 0.10,
    min_consecutive_hours: int = 3,
    days_ahead: int = 14,
) -> list[dict]:
    """
    คัดกรองช่วงเวลาที่ demand ต่ำติดกันจาก DemandForecast โดยตรง
    ไม่ต้อง import โมดูล ML หนัก ๆ ใน request path
    """
    today = timezone.localdate()
    end = today + timedelta(days=days_ahead)

    qs = DemandForecast.objects.filter(
        forecast_date__gte=today,
        forecast_date__lte=end,
        predicted_demand__lt=max_demand,
    ).select_related('room').order_by('room_id', 'forecast_date', 'hour')

    if room_id:
        qs = qs.filter(room_id=room_id)

    slots = []
    current = None

    for fc in qs:
        key = (fc.room_id, fc.forecast_date)
        if current and current['key'] == key and fc.hour == current['last_hour'] + 1:
            current['hours'].append(fc.hour)
            current['demands'].append(float(fc.predicted_demand))
            current['last_hour'] = fc.hour
        else:
            if current and len(current['hours']) >= min_consecutive_hours:
                slots.append(_finalize_maintenance_slot(current))
            current = {
                'key': key,
                'room_id': fc.room_id,
                'room_name': fc.room.name,
                'date': fc.forecast_date,
                'hours': [fc.hour],
                'demands': [float(fc.predicted_demand)],
                'last_hour': fc.hour,
            }

    if current and len(current['hours']) >= min_consecutive_hours:
        slots.append(_finalize_maintenance_slot(current))

    return sorted(slots, key=lambda s: (s['date'], s['start_hour']))


def _finalize_maintenance_slot(current: dict) -> dict:
    hrs = current['hours']
    return {
        'room_id': current['room_id'],
        'room_name': current['room_name'],
        'date': str(current['date']),
        'start_hour': min(hrs),
        'end_hour': max(hrs) + 1,
        'hours': hrs,
        'avg_demand': round(sum(current['demands']) / len(current['demands']), 4),
        'label': (
            f"{current['room_name']} | {current['date']} "
            f"{min(hrs):02d}:00–{max(hrs) + 1:02d}:00"
        ),
    }


class MaintenanceBlockViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = MaintenanceBlock.objects.select_related('room__building', 'created_by')

    def get_serializer_class(self):
        if self.action == 'create':
            return MaintenanceBlockCreateSerializer
        return MaintenanceBlockSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self.request.user, 'role', None) not in ['admin', 'staff']:
            return qs.none()
        room = self.request.query_params.get('room')
        if room:
            qs = qs.filter(room_id=room)
        return qs.order_by('-start_time')

    def perform_create(self, serializer):
        room       = serializer.validated_data['room']
        start_time = serializer.validated_data['start_time']
        end_time   = serializer.validated_data['end_time']

        with transaction.atomic():
            Room.objects.select_for_update().get(pk=room.pk)

            if Booking.objects.filter(
                room=room,
                status__in=['pending', 'approved', 'checked_in'],
                start_time__lt=end_time,
                end_time__gt=start_time,
            ).exists():
                raise ValidationError({'detail': 'ห้องนี้มีการจองอยู่ในช่วงเวลาดังกล่าว ไม่สามารถปิดซ่อมบำรุงได้'})

            target_date = start_time.date()
            target_dow  = target_date.weekday()
            if TermBooking.objects.filter(
                room=room,
                day_of_week=target_dow,
                status='active',
                term_start__lte=target_date,
                term_end__gte=target_date,
            ).exclude(
                start_time__gte=end_time.time()
            ).exclude(
                end_time__lte=start_time.time()
            ).exists():
                raise ValidationError({'detail': 'ห้องนี้มีการจองทั้งเทอมอยู่ในช่วงเวลาดังกล่าว ไม่สามารถปิดซ่อมบำรุงได้'})

            if MaintenanceBlock.objects.filter(
                room=room,
                status__in=['scheduled', 'active'],
                start_time__lt=end_time,
                end_time__gt=start_time,
            ).exists():
                raise ValidationError({'detail': 'ห้องนี้มีการปิดซ่อมบำรุงในช่วงเวลาดังกล่าวอยู่แล้ว'})

            block = serializer.save(
                created_by=self.request.user,
                status='scheduled',
            )
            block.room.status = 'maintenance'
            block.room.save(update_fields=['status'])

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        block = self.get_object()
        block.status = 'completed'
        block.save(update_fields=['status'])
        if not MaintenanceBlock.objects.filter(
            room=block.room, status__in=['scheduled', 'active']
        ).exists():
            block.room.status = 'available'
            block.room.save(update_fields=['status'])
        return Response({'message': 'บำรุงรักษาเสร็จสิ้น'})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        block = self.get_object()
        block.status = 'cancelled'
        block.save(update_fields=['status'])
        if not MaintenanceBlock.objects.filter(
            room=block.room, status__in=['scheduled', 'active']
        ).exists():
            block.room.status = 'available'
            block.room.save(update_fields=['status'])
        return Response({'message': 'ยกเลิกช่วงซ่อมบำรุงแล้ว'})


# ============================================================
# DASHBOARD
# ============================================================
class DashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ['admin', 'staff']:
            return Response({'error': 'สำหรับผู้ดูแลระบบเท่านั้น'}, status=403)

        today       = timezone.now().date()
        total_rooms = Room.objects.count()
        today_dynamic = Booking.objects.filter(start_time__date=today, status='approved').count()
        today_term    = TermBooking.objects.filter(
            day_of_week=today.weekday(), status='active',
            term_start__lte=today, term_end__gte=today,
        ).count()
        pending = Booking.objects.filter(status='pending').count()
        popular = (
            Booking.objects.filter(status__in=['approved', 'completed'])
            .values('room__name').annotate(count=Count('id')).order_by('-count')[:5]
        )
        demand_alerts = list(
            DemandForecast.objects.filter(forecast_date=today, demand_level__in=['urgent', 'high'])
            .values('room__name', 'hour', 'predicted_demand', 'term_demand', 'dynamic_demand', 'demand_level')
            .order_by('-predicted_demand')[:5]
        )
        return Response({
            'today_bookings':   today_dynamic + today_term,
            'today_dynamic':    today_dynamic,
            'today_term':       today_term,
            'pending':          pending,
            'total_rooms':      total_rooms,
            'utilization_rate': round((today_dynamic + today_term) / max(total_rooms, 1) * 100, 1),
            'popular_rooms':    list(popular),
            'demand_alerts':    demand_alerts,
        })


# ============================================================
# EXPORT EXCEL
# ============================================================
class ExportExcelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sheets_param  = request.query_params.get('sheets', 'all')
        mapping = {
            'users': User, 'buildings': Building, 'rooms': Room,
            'facilities': Facility, 'bookings': Booking,
            'term_bookings': TermBooking, 'logs': BookingLog,
            'forecasts': DemandForecast, 'notifications': Notification, 'stats': RoomUsageStat,
        }
        selected_keys = mapping.keys() if sheets_param == 'all' else sheets_param.split(',')

        try:
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = 'attachment; filename="export.xlsx"'

            with pd.ExcelWriter(response, engine='openpyxl') as writer:
                for key in selected_keys:
                    if key not in mapping: continue
                    queryset = mapping[key].objects.all()
                    try:
                        queryset = queryset.order_by('-id')
                    except Exception:
                        pass

                    data = list(queryset.values())
                    df   = pd.DataFrame(data)
                    if df.empty:
                        df = pd.DataFrame([{"System Message": "No data found"}])
                    else:
                        for col in df.columns:
                            if pd.api.types.is_datetime64_any_dtype(df[col]):
                                df[col] = df[col].dt.tz_localize(None)
                            else:
                                df[col] = df[col].apply(lambda x: "" if x is None else str(x))

                    sheet_name = key.replace('_', ' ').title()[:31]
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    worksheet = writer.sheets[sheet_name]
                    for i, col in enumerate(df.columns):
                        lengths    = [len(str(val)) for val in df[col].values]
                        max_len    = max(lengths) if lengths else 0
                        column_len = max(max_len, len(str(col))) + 2
                        col_letter = chr(65 + (i % 26)) if i < 26 else f"A{chr(65 + (i - 26))}"
                        worksheet.column_dimensions[col_letter].width = min(column_len, 50)

            return response
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=400)
        
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        # ส่ง credential ที่ user กรอกไป verify กับ LDAP
        ldap_user = authenticate_ldap(username, password)

        if ldap_user:
            # สร้าง/อัปเดต Django user
            user, _ = User.objects.get_or_create(username=username)
            user.first_name = ldap_user['full_name']
            user.email      = ldap_user['email']
            user.save()

            login(request, user,
                  backend='django.contrib.auth.backends.ModelBackend')
            return redirect('home')

        return render(request, 'login.html',
                      {'error': 'รหัสนักศึกษาหรือรหัสผ่านไม่ถูกต้อง'})

    return render(request, 'login.html')
