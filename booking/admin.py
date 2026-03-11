from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Building, Room, RoomFacility,
    Booking, BookingLog, DemandForecast,
    Notification, RoomUsageStat
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
    list_display = ['user', 'room', 'start_time', 'end_time', 'status']
    list_filter  = ['status']

@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ['room', 'forecast_date', 'hour', 'predicted_demand', 'demand_level', 'availability', 'confidence']
    list_filter  = ['demand_level', 'availability', 'room']

admin.site.register(RoomFacility)
admin.site.register(BookingLog)
admin.site.register(Notification)
admin.site.register(RoomUsageStat)