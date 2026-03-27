from django.utils import timezone
from django.db.models import Q, Count, Prefetch
from django.db import transaction
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
        qs = (
            Room.objects.filter(is_active=True)
            .select_related('building')
            .prefetch_related(
                Prefetch('forecasts', to_attr='prefetched_forecasts')  # ✅ FIX N+1
            )
        )

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


    # ========================================================
    # SEARCH ROOM
    # ========================================================
    @action(detail=False, methods=['post'])
    def search(self, request):
        ser = RoomSearchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        date     = d['date']
        start_dt = timezone.make_aware(datetime.combine(date, d['start_time']))
        end_dt   = timezone.make_aware(datetime.combine(date, d['end_time']))
        now      = timezone.now()

        facilities = request.data.get('facilities', [])

        # ✅ FIX overlap + real-time availability
        booked_ids = Booking.objects.filter(
            status='approved',
            start_time__lt=end_dt,
            end_time__gt=max(start_dt, now),
        ).values_list('room_id', flat=True)

        available = (
            Room.objects.filter(
                is_active=True,
                capacity__gte=d['attendees'],
            )
            .exclude(id__in=booked_ids)
            .exclude(status__in=['maintenance', 'disabled'])
            .select_related('building')
            .prefetch_related('facilities')
        )

        if d.get('room_type'):
            available = available.filter(room_type=d['room_type'])

        if facilities:
            for f in facilities:
                available = available.filter(facilities__name__icontains=f)
            available = available.distinct()

        if d.get('building_code'):
            preferred = list(available.filter(building__code=d['building_code']).order_by('capacity'))
            others    = list(available.exclude(building__code=d['building_code']).order_by('capacity'))
            results   = preferred + others
        else:
            results = list(available.order_by('capacity'))

        # ✅ FIX: preload forecast ทีเดียว (กัน N+1)
        forecasts = DemandForecast.objects.filter(
            forecast_date=date,
            hour=d['start_time'].hour,
            room__in=results
        )

        forecast_map = {(f.room_id): f for f in forecasts}

        response_data = []
        for room in results:
            forecast = forecast_map.get(room.id)

            room_data = RoomSerializer(room, context={'request': request}).data
            room_data['forecast'] = {
                'demand_level':     forecast.demand_level if forecast else 'none',
                'availability':     forecast.availability if forecast else 'likely_available',
                'predicted_demand': float(forecast.predicted_demand) if forecast else 0.0,
                'confidence':       float(forecast.confidence) if forecast else 0.0,
            }
            response_data.append(room_data)

        level_order = {'low': 0, 'medium': 1, 'high': 2, 'none': 3}
        response_data.sort(key=lambda r: level_order.get(r['forecast']['demand_level'], 3))

        return Response(response_data)


    # ========================================================
    # AVAILABILITY
    # ========================================================
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
            room=room,
            status='approved',
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

        qs = Booking.objects.select_related('user', 'room__building')

        return qs if user.role in ['admin', 'staff'] else qs.filter(user=user)

    def get_serializer_class(self):
        return BookingCreateSerializer if self.action == 'create' else BookingSerializer


    def perform_create(self, serializer):
        with transaction.atomic():
            room       = serializer.validated_data['room']
            start_time = serializer.validated_data['start_time']
            end_time   = serializer.validated_data['end_time']

            conflict = (
                Booking.objects
                .select_for_update()
                .filter(
                    room=room,
                    status='approved',
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                )
                .exists()
            )

            if conflict:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({
                    'non_field_errors': ['ห้องนี้ถูกจองในช่วงเวลาดังกล่าวแล้ว']
                })

            booking = serializer.save(user=self.request.user, status='approved')

            Notification.objects.create(
                user=self.request.user,
                booking=booking,
                type='booking_approved',
                title='จองห้องสำเร็จ',
                message=f'จองห้อง {booking.room.name} เรียบร้อยแล้ว'
            )


    def destroy(self, request, *args, **kwargs):
        return Response(
            {'error': 'ไม่อนุญาตให้ลบข้อมูล กรุณาใช้ยกเลิกแทน'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )


    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()

        if booking.user != request.user and request.user.role not in ['admin', 'staff']:
            return Response({'error': 'ไม่มีสิทธิ์'}, status=403)

        if booking.status == 'cancelled':
            return Response({'error': 'ถูกยกเลิกแล้ว'}, status=400)

        old_status = booking.status
        booking.status = 'cancelled'
        booking.save()

        BookingLog.objects.create(
            booking=booking,
            changed_by=request.user,
            old_status=old_status,
            new_status='cancelled'
        )

        return Response({'message': 'ยกเลิกสำเร็จ'})


# ============================================================
# DASHBOARD
# ============================================================
class DashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ['admin', 'staff']:
            return Response({'error': 'สำหรับ admin เท่านั้น'}, status=403)

        today = timezone.now().date()

        total_rooms = Room.objects.filter(is_active=True).count()
        today_bookings = Booking.objects.filter(
            start_time__date=today,
            status='approved'
        ).count()

        utilization = round((today_bookings / total_rooms * 100), 1) if total_rooms else 0

        popular_rooms = (
            Booking.objects.filter(status='approved')
            .values('room__name')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )

        demand_alerts = list(
            DemandForecast.objects.filter(
                forecast_date=today,
                demand_level='high'
            ).values('room__name', 'hour', 'predicted_demand')
            .order_by('-predicted_demand')[:5]
        )

        return Response({
            'today_bookings': today_bookings,
            'total_rooms': total_rooms,
            'utilization_rate': utilization,
            'popular_rooms': list(popular_rooms),
            'demand_alerts': demand_alerts,
        })


# ============================================================
# NOTIFICATION
# ============================================================
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.save()
        return Response({'status': 'read'})


# ============================================================
# FORECAST
# ============================================================
class DemandForecastViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DemandForecastSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = DemandForecast.objects.all().order_by('forecast_date', 'hour')

        room = self.request.query_params.get('room')
        date = self.request.query_params.get('date')

        if room:
            qs = qs.filter(room_id=room)
        if date:
            qs = qs.filter(forecast_date=date)

        return qs


# ============================================================
# RETRAIN
# ============================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_retrain(request):
    if request.user.role not in ['admin', 'staff']:
        return Response({'error': 'admin only'}, status=403)

    def run_training():
        call_command('retrain')

    threading.Thread(target=run_training, daemon=True).start()

    return Response({'message': 'เริ่ม retrain แล้ว'})