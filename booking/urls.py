# booking/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import LDAPTokenObtainPairSerializer
from .views import (
    RegisterView, ProfileView,
    ChangePasswordView, DeleteAccountView,
    BuildingViewSet, RoomViewSet,
    TermBookingViewSet, BookingViewSet,
    NotificationViewSet, DemandForecastViewSet,
    DashboardView, ExportExcelView,
    MaintenanceSlotsView, MaintenanceBlockViewSet,
)


# ── Override TokenObtainPairView ให้ใช้ LDAP serializer ──────────────────────
class LDAPTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Body: { "username": "66114640275", "password": "..." }
    ตรวจสอบกับ LDAP มหาวิทยาลัย แทน database
    """
    serializer_class = LDAPTokenObtainPairSerializer


# ── Router ────────────────────────────────────────────────────────────────────
router = DefaultRouter()
router.register('buildings',     BuildingViewSet,       basename='building')
router.register('rooms',         RoomViewSet,           basename='room')
router.register('term-bookings', TermBookingViewSet,    basename='term-booking')
router.register('bookings',      BookingViewSet,        basename='booking')
router.register('notifications', NotificationViewSet,   basename='notification')
router.register('forecasts',     DemandForecastViewSet, basename='forecast')
router.register('maintenance-blocks', MaintenanceBlockViewSet, basename='maintenance-block')

urlpatterns = [
    # Auth
    path('auth/register/', RegisterView.as_view(),           name='register'),
    path('auth/login/',    LDAPTokenObtainPairView.as_view(), name='login'),    # ← เปลี่ยนตรงนี้
    path('auth/refresh/',  TokenRefreshView.as_view(),        name='token_refresh'),
    path('auth/profile/',  ProfileView.as_view(),             name='profile'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('auth/delete-account/',   DeleteAccountView.as_view(),  name='delete_account'),

    # Dashboard + Export
    path('dashboard/',     DashboardView.as_view(),           name='dashboard'),
    path('export/excel/',  ExportExcelView.as_view(),         name='export_excel'),
    path('maintenance/slots/', MaintenanceSlotsView.as_view(), name='maintenance_slots'),

    # ViewSets
    path('', include(router.urls)),
]
