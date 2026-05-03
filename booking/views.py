import pandas as pd
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

from .models import (
    User, Building, Room, Facility, RoomFacility,
    TermBooking, Booking, BookingLog,
    DemandForecast, Notification, RoomUsageStat
)
from .serializers import (
    UserSerializer, RegisterSerializer,
    BuildingSerializer,
    RoomSerializer, RoomListSerializer, RoomSearchSerializer,
    TermBookingSerializer, TermBookingCreateSerializer,
    BookingSerializer, BookingCreateSerializer,
    BookingLogSerializer, DemandForecastSerializer,
    NotificationSerializer, RoomUsageStatSerializer
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


# ============================================================
# BUILDING
# ============================================================
class BuildingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Building.objects.filter(is_active=True)
    serializer_class   = BuildingSerializer
    permission_classes = [IsAuthenticated]


# ============================================================
# ROOM
# ============================================================
class RoomViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Room.objects.filter(is_active=True).select_related('building')
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

    def _search_dynamic(self, d, request):
        target_date = d['date']
        start_dt    = timezone.make_aware(datetime.combine(target_date, d['start_time']))
        end_dt      = timezone.make_aware(datetime.combine(target_date, d['end_time']))
        target_dow  = target_date.weekday()

        booked_dynamic = Booking.objects.filter(
            status__in=['pending', 'approved'],
            start_time__lt=end_dt, end_time__gt=start_dt,
        ).values_list('room_id', flat=True)

        booked_term = TermBooking.objects.filter(
            day_of_week=target_dow, status='active',
            term_start__lte=target_date, term_end__gte=target_date,
        ).exclude(start_time__gte=d['end_time']).exclude(end_time__lte=d['start_time'])\
         .values_list('room_id', flat=True)

        blocked   = set(list(booked_dynamic) + list(booked_term))
        available = Room.objects.filter(
            is_active=True, status='available', capacity__gte=d['attendees'],
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

        available = Room.objects.filter(
            is_active=True, status='available', capacity__gte=d['attendees'],
        ).exclude(id__in=booked_term).select_related('building')\
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


# ============================================================
# TERM BOOKING ViewSet
# ============================================================
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
        term_booking = serializer.save(user=self.request.user, status='approved')
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
    <p style="color:#9ca3af;font-size:13px;margin-top:8px;">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</p>
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
    <p style="color:#9ca3af;font-size:13px;margin-top:32px;">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</p>
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
# DASHBOARD
# ============================================================
class DashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ['admin', 'staff']:
            return Response({'error': 'สำหรับผู้ดูแลระบบเท่านั้น'}, status=403)

        today       = timezone.now().date()
        total_rooms = Room.objects.filter(is_active=True).count()
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