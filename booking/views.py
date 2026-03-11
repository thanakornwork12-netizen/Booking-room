from rest_framework.decorators import permission_classes
from django.utils import timezone
from django.db.models import Q
from datetime import datetime
from rest_framework.decorators import api_view
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
import threading
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

        # รับ facilities จาก request (ไม่ผ่าน serializer เพราะเป็น optional list)
        facilities = request.data.get('facilities', [])

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

        # filter อุปกรณ์ — ต้องมีครบทุกอย่างที่เลือก
        if facilities:
            for facility in facilities:
                available = available.filter(
                    facilities__name__icontains=facility
                )
            available = available.distinct()

        if d.get('building_code'):
            preferred = list(available.filter(building__code=d['building_code']).order_by('capacity'))
            others    = list(available.exclude(building__code=d['building_code']).order_by('capacity'))
            results   = preferred + others
        else:
            results = list(available.order_by('capacity'))

        hour = d['start_time'].hour
        response_data = []
        for room in results:
            forecast = room.forecasts.filter(forecast_date=date, hour=hour).first()
            room_data = RoomSerializer(room, context={'request': request}).data
            room_data['forecast'] = {
                'demand_level': forecast.demand_level if forecast else 'low',
                'availability': forecast.availability if forecast else 'low',
                'confidence':   forecast.confidence   if forecast else 0,
            }
            response_data.append(room_data)

        return Response(response_data)

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        room     = self.get_object()
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({'error': 'กรุณาระบุวันที่'}, status=400)

        from datetime import date as date_type
        target_date = date_type.fromisoformat(date_str)

        bookings  = Booking.objects.filter(
            room=room, status='approved',
            start_time__date=target_date,
        ).values('start_time', 'end_time', 'title')

        forecasts = room.forecasts.filter(
            forecast_date=target_date
        ).values('hour', 'demand_level', 'availability', 'predicted_demand')

        return Response({
            'room':      room.name,
            'date':      target_date,
            'bookings':  list(bookings),
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
            message=f'จองห้อง {booking.room.name} วันที่ {booking.start_time:%d/%m/%Y %H:%M} เรียบร้อยแล้ว'
        )

    def destroy(self, request, *args, **kwargs):
        # ปิดการลบจริง — ใช้ POST /bookings/{id}/cancel/ แทน
        return Response(
            {'error': 'ไม่อนุญาตให้ลบข้อมูลการจอง กรุณาใช้การยกเลิกแทน'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.user != request.user and request.user.role not in ['admin', 'staff']:
            return Response({'error': 'ไม่มีสิทธิ์'}, status=403)
        if booking.status != 'approved':
            return Response({'error': 'ไม่สามารถยกเลิกได้'}, status=400)
        old_status     = booking.status
        booking.status = 'cancelled'
        booking.save()
        BookingLog.objects.create(
            booking=booking, changed_by=request.user,
            old_status=old_status, new_status='cancelled'
        )
        return Response({'message': 'ยกเลิกการจองเรียบร้อย'})

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        booking = self.get_object()
        logs    = booking.logs.all()
        return Response(BookingLogSerializer(logs, many=True).data)


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
        notif         = self.get_object()
        notif.is_read = True
        notif.save()
        return Response({'message': 'อ่านแล้ว'})

    @action(detail=False, methods=['post'])
    def read_all(self, request):
        self.get_queryset().update(is_read=True)
        return Response({'message': 'อ่านทั้งหมดแล้ว'})


# ============================================================
# DEMAND FORECAST
# ============================================================
class DemandForecastViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = DemandForecastSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs   = DemandForecast.objects.all()
        room = self.request.query_params.get('room')
        date = self.request.query_params.get('date')
        if room:
            qs = qs.filter(room_id=room)
        if date:
            qs = qs.filter(forecast_date=date)
        return qs


# ============================================================
# DASHBOARD
# ============================================================
class DashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ['admin', 'staff']:
            return Response({'error': 'ไม่มีสิทธิ์'}, status=403)

        today = timezone.now().date()

        total_rooms     = Room.objects.filter(is_active=True).count()
        today_bookings  = Booking.objects.filter(start_time__date=today, status='approved').count()
        total_bookings  = Booking.objects.filter(status='approved').count()
        utilization     = round((today_bookings / total_rooms * 100), 1) if total_rooms > 0 else 0

        from django.db.models import Count
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
            'today_bookings':   today_bookings,
            'pending_bookings': 0,
            'total_rooms':      total_rooms,
            'utilization_rate': utilization,
            'popular_rooms':    list(popular_rooms),
            'demand_alerts':    demand_alerts,
        })


# ============================================================
# RETRAIN
# ============================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_retrain(request):
    if request.user.role not in ['admin', 'staff']:
        return Response({'error': 'Permission denied'}, status=403)

    def run():
        call_command('retrain')

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return Response({'message': 'retrain started'})