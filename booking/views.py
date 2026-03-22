from django.utils import timezone
from django.db.models import Q, Count
from datetime import datetime, date as date_type
import threading

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.management import call_command

from .models import (
    User, Building, Room, Booking,
    BookingLog, DemandForecast, Notification, RoomUsageStat
)
from .serializers import (
    UserSerializer, RegisterSerializer,
    BuildingSerializer,
    RoomSerializer, RoomListSerializer, RoomSearchSerializer,
    BookingSerializer, BookingCreateSerializer,
    BookingLogSerializer, DemandForecastSerializer,
    NotificationSerializer, RoomUsageStatSerializer
)

# ============================================================
# AUTH
# ============================================================
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

# ============================================================
# BUILDING
# ============================================================
class BuildingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Building.objects.filter(is_active=True)
    serializer_class = BuildingSerializer
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
        if self.action == 'list':
            return RoomListSerializer
        return RoomSerializer

    @action(detail=False, methods=['post'])
    def search(self, request):
        ser = RoomSearchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        date     = d['date']
        start_dt = timezone.make_aware(datetime.combine(date, d['start_time']))
        end_dt   = timezone.make_aware(datetime.combine(date, d['end_time']))

        facilities = request.data.get('facilities', [])

        # ห้องที่ถูกจองไว้แล้ว (approved เท่านั้น)
        booked_ids = Booking.objects.filter(
            status__in=['approved'],
            start_time__lt=end_dt,
            end_time__gt=start_dt,
        ).values_list('room_id', flat=True)

        available = Room.objects.filter(
            is_active=True,
            status='available',
            capacity__gte=d['attendees'],
        ).exclude(id__in=booked_ids).select_related('building').prefetch_related('facilities')

        if d.get('room_type'):
            available = available.filter(room_type=d['room_type'])

        if facilities:
            for facility in facilities:
                available = available.filter(facilities__name__icontains=facility)
            available = available.distinct()

        if d.get('building_code'):
            preferred = list(available.filter(building__code=d['building_code']).order_by('capacity'))
            others    = list(available.exclude(building__code=d['building_code']).order_by('capacity'))
            results   = preferred + others
        else:
            results = list(available.order_by('capacity'))

        # ── ดึง Forecast ตรง date + hour ที่ user ค้นหาพอดี ──
        hour = d['start_time'].hour  # int เช่น 10, 13, 14

        response_data = []
        for room in results:
            # แก้ Bug 2: ใช้ .filter().first() แทน .first() แบบเดิม
            # และส่ง predicted_demand กลับด้วย (Frontend ต้องการ)
            forecast = (
                DemandForecast.objects
                .filter(
                    room=room,
                    forecast_date=date,   # date object ตรงกับที่ DRF parse แล้ว
                    hour=hour,            # int ตรงกับที่ ML script บันทึก
                )
                .first()
            )

            room_data = RoomSerializer(room, context={'request': request}).data
            room_data['forecast'] = {
                'demand_level':     forecast.demand_level     if forecast else 'none',
                'availability':     forecast.availability     if forecast else 'likely_available',
                'predicted_demand': float(forecast.predicted_demand) if forecast else 0.0,
                'confidence':       float(forecast.confidence)       if forecast else 0.0,
            }
            response_data.append(room_data)

        # เรียงตาม demand_level: low → medium → high
        # (ห้องที่ว่างขึ้นก่อน เพราะน่าจองมากกว่า)
        level_order = {'low': 0, 'medium': 1, 'high': 2, 'none': 3}
        response_data.sort(
            key=lambda r: level_order.get(r['forecast']['demand_level'], 3)
        )

        return Response(response_data)

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

        bookings = Booking.objects.filter(
            room=room, status='approved',
            start_time__date=target_date,
        ).values('start_time', 'end_time', 'title')

        forecasts = room.forecasts.filter(
            forecast_date=target_date
        ).values('hour', 'demand_level', 'availability', 'predicted_demand')

        return Response({
            'room': room.name,
            'date': target_date,
            'bookings': list(bookings),
            'forecasts': list(forecasts),
        })

# ============================================================
# BOOKING
# ============================================================
class BookingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role in ['admin', 'staff']:
            return Booking.objects.all().select_related('user', 'room__building')
        return Booking.objects.filter(user=user).select_related('room__building')

    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        return BookingSerializer

    def perform_create(self, serializer):
        booking = serializer.save(user=self.request.user, status='approved')
        Notification.objects.create(
            user=self.request.user,
            booking=booking,
            type='booking_approved',
            title='จองห้องสำเร็จ',
            message=f'จองห้อง {booking.room.name} วันที่ {booking.start_time.strftime("%d/%m/%Y %H:%M")} เรียบร้อยแล้ว'
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'error': 'ไม่อนุญาตให้ลบข้อมูล กรุณาใช้ปุ่มยกเลิกการจองแทน'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.user != request.user and request.user.role not in ['admin', 'staff']:
            return Response({'error': 'คุณไม่มีสิทธิ์ยกเลิกการจองนี้'}, status=403)

        if booking.status == 'cancelled':
            return Response({'error': 'รายการนี้ถูกยกเลิกไปแล้ว'}, status=400)

        old_status = booking.status
        booking.status = 'cancelled'
        booking.save()

        BookingLog.objects.create(
            booking=booking,
            changed_by=request.user,
            old_status=old_status,
            new_status='cancelled'
        )
        return Response({'message': 'ยกเลิกการจองเรียบร้อยแล้ว'})

# ============================================================
# DASHBOARD
# ============================================================
class DashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ['admin', 'staff']:
            return Response({'error': 'หน้านี้สำหรับผู้ดูแลระบบเท่านั้น'}, status=403)

        today         = timezone.now().date()
        total_rooms   = Room.objects.filter(is_active=True).count()
        today_bookings = Booking.objects.filter(start_time__date=today, status='approved').count()
        utilization   = round((today_bookings / total_rooms * 100), 1) if total_rooms > 0 else 0

        popular_rooms = (
            Booking.objects.filter(status='approved')
            .values('room__name')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )

        demand_alerts = list(
            DemandForecast.objects.filter(forecast_date=today, demand_level='high')
            .values('room__name', 'hour', 'predicted_demand')
            .order_by('-predicted_demand')[:5]
        )

        return Response({
            'today_bookings':   today_bookings,
            'total_rooms':      total_rooms,
            'utilization_rate': utilization,
            'popular_rooms':    list(popular_rooms),
            'demand_alerts':    demand_alerts,
        })

# ============================================================
# NOTIFICATION & FORECAST
# ============================================================
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.save()
        return Response({'status': 'read'})

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
# RETRAIN
# ============================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_retrain(request):
    if request.user.role not in ['admin', 'staff']:
        return Response({'error': 'จำกัดสิทธิ์เฉพาะผู้ดูแลระบบ'}, status=403)

    def run_training():
        call_command('retrain')

    thread = threading.Thread(target=run_training, daemon=True)
    thread.start()
    return Response({'message': 'ระบบเริ่มการเทรน AI ใหม่ในพื้นหลังแล้ว'})