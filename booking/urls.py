from django.urls import path, include
from rest_framework.routers import DefaultRouter
# เพิ่ม 2 บรรทัดนี้ครับ
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import (
    RegisterView, ProfileView,
    BuildingViewSet, RoomViewSet,
    BookingViewSet, NotificationViewSet,
    DemandForecastViewSet, DashboardView,
    trigger_retrain, export_excel
)

router = DefaultRouter()
# ... ส่วนของ router.register เหมือนเดิม ...
router.register('buildings',    BuildingViewSet,       basename='building')
router.register('rooms',        RoomViewSet,           basename='room')
router.register('bookings',     BookingViewSet,        basename='booking')
router.register('notifications', NotificationViewSet,   basename='notification')
router.register('forecasts',    DemandForecastViewSet, basename='forecast')

urlpatterns = [
    # Auth
    path('auth/register/',  RegisterView.as_view(),        name='register'),
    path('auth/login/',     TokenObtainPairView.as_view(), name='login'), 
    path('auth/refresh/',   TokenRefreshView.as_view(),    name='token_refresh'),
    path('auth/profile/',   ProfileView.as_view(),         name='profile'),

    # Export & Admin Tools
    path('export/excel/',   export_excel,                  name='export_excel'),
    path('retrain/',        trigger_retrain,               name='retrain'),
    path('dashboard/',      DashboardView.as_view(),       name='dashboard'),

    path('', include(router.urls)),
]