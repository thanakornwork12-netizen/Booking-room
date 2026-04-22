from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Building, Room, Facility, RoomFacility,
    Booking, BookingLog, DemandForecast,
    Notification, RoomUsageStat, TermBooking
)

# ทำให้สามารถแก้ไขอุปกรณ์ได้โดยตรงในหน้า Room
class RoomFacilityInline(admin.TabularInline):
    model = RoomFacility
    extra = 1

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
    inlines = [RoomFacilityInline] # เพิ่ม Inline อุปกรณ์

@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon']

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display  = ['user', 'room', 'title', 'start_time', 'end_time', 'status', 'checked_in']
    list_filter   = ['status', 'checked_in']
    search_fields = ['user__username', 'room__name', 'title']

@admin.register(TermBooking)
class TermBookingAdmin(admin.ModelAdmin):
    list_display  = ['user', 'room', 'subject_name', 'day_of_week', 'start_time', 'end_time', 'status']
    list_filter   = ['status', 'day_of_week']

@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ['room', 'forecast_date', 'hour', 'demand_level', 'availability']

@admin.register(BookingLog)
class BookingLogAdmin(admin.ModelAdmin):
    list_display = ['booking', 'term_booking', 'changed_by', 'old_status', 'new_status', 'changed_at']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'title', 'is_read', 'created_at']

@admin.register(RoomUsageStat)
class RoomUsageStatAdmin(admin.ModelAdmin):
    list_display = ['room', 'date', 'total_bookings', 'utilization_rate']

# ลงทะเบียนคลาสลูกเผื่อแยกจัดการ
admin.site.register(RoomFacility)