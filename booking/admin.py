from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Building, Room, RoomFacility,
    Booking, BookingLog, DemandForecast,
    Notification, RoomUsageStat,
    TermBooking,  # ← เพิ่ม
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'get_full_name', 'role', 'faculty', 'email']
    list_filter  = ['role', 'faculty']
    fieldsets    = UserAdmin.fieldsets + (
        ('ข้อมูลเพิ่มเติม', {'fields': ('role', 'faculty', 'phone')}),
    )

@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active']

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'building', 'floor', 'capacity', 'room_type', 'status']
    list_filter  = ['building', 'status', 'room_type']

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display  = ['user', 'room', 'title', 'start_time', 'end_time', 'status', 'checked_in']
    list_filter   = ['status', 'checked_in']
    search_fields = ['user__username', 'room__name', 'title']
    ordering      = ['-created_at']

@admin.register(TermBooking)
class TermBookingAdmin(admin.ModelAdmin):
    list_display  = ['user', 'room', 'subject_name', 'subject_code', 'day_of_week', 'start_time', 'end_time', 'term_name', 'status']
    list_filter   = ['status', 'day_of_week', 'term_name']
    search_fields = ['user__username', 'room__name', 'subject_name', 'subject_code']
    ordering      = ['day_of_week', 'start_time']

@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ['room', 'forecast_date', 'hour', 'predicted_demand', 'demand_level', 'availability', 'confidence']
    list_filter  = ['demand_level', 'availability', 'room']

@admin.register(BookingLog)
class BookingLogAdmin(admin.ModelAdmin):
    list_display = ['booking', 'term_booking', 'changed_by', 'old_status', 'new_status', 'changed_at']
    list_filter  = ['old_status', 'new_status']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ['user', 'type', 'title', 'is_read', 'created_at']
    list_filter   = ['type', 'is_read']
    search_fields = ['user__username', 'title']

@admin.register(RoomUsageStat)
class RoomUsageStatAdmin(admin.ModelAdmin):
    list_display = ['room', 'date', 'total_bookings', 'term_bookings', 'dynamic_bookings', 'utilization_rate']
    list_filter  = ['room']

admin.site.register(RoomFacility)