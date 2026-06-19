import pandas as pd
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.http import HttpResponse
from import_export.admin import ImportExportModelAdmin
from .models import (
    User, Building, Room, Facility, RoomFacility,
    Booking, BookingLog, DemandForecast,
    Notification, RoomUsageStat, TermBooking, MaintenanceBlock,
)

# --- Custom Action Function ---

@admin.action(description="📦 Export ข้อมูลสำคัญทั้งหมดเป็นไฟล์เดียว (แยก Sheet)")
def export_combined_data(modeladmin, request, queryset):
    """
    ฟังก์ชันสำหรับดึงข้อมูลจากหลาย Model มาเขียนลง Excel ไฟล์เดียวแต่แยก Tab (Sheet)
    """
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="room_booking_comprehensive_report.xlsx"'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        # 1. Sheet: Selected Bookings (ข้อมูลการจองที่เลือกในหน้า Admin)
        # เราดึงข้อมูลจาก queryset ที่ผู้ใช้ติ๊กเลือก
        bookings_data = list(queryset.values(
            'id', 'title', 'user__username', 'room__name', 
            'start_time', 'end_time', 'status', 'checked_in'
        ))
        pd.DataFrame(bookings_data).to_excel(writer, sheet_name='Bookings', index=False)

        # 2. Sheet: All Rooms (รายชื่อห้องและสถานะทั้งหมด)
        rooms_data = list(Room.objects.all().values(
            'name', 'building__name', 'floor', 'capacity', 'room_type', 'status'
        ))
        pd.DataFrame(rooms_data).to_excel(writer, sheet_name='Rooms', index=False)

        # 3. Sheet: All Users (รายชื่อผู้ใช้งานและบทบาท)
        users_data = list(User.objects.all().values(
            'username', 'first_name', 'last_name', 'role', 'faculty', 'email'
        ))
        pd.DataFrame(users_data).to_excel(writer, sheet_name='Users', index=False)

        # 4. Sheet: Usage Stats (สถิติการใช้งาน)
        stats_data = list(RoomUsageStat.objects.all().values())
        pd.DataFrame(stats_data).to_excel(writer, sheet_name='Usage_Statistics', index=False)

    return response

# --- Admin Classes ---

class RoomFacilityInline(admin.TabularInline):
    model = RoomFacility
    extra = 1

@admin.register(User)
class CustomUserAdmin(UserAdmin, ImportExportModelAdmin):
    list_display = ['username', 'get_full_name', 'role', 'faculty', 'email']
    list_filter  = ['role', 'faculty']
    fieldsets    = UserAdmin.fieldsets + (
        ('ข้อมูลเพิ่มเติม', {'fields': ('role', 'faculty', 'phone')}),
    )

@admin.register(Building)
class BuildingAdmin(ImportExportModelAdmin):
    list_display = ['code', 'name', 'is_active']
    list_filter = ['is_active']

@admin.register(Room)
class RoomAdmin(ImportExportModelAdmin):
    list_display = ['name', 'building', 'floor', 'capacity', 'room_type', 'status']
    list_filter  = ['building', 'status', 'room_type']
    inlines = [RoomFacilityInline]

@admin.register(Facility)
class FacilityAdmin(ImportExportModelAdmin):
    list_display = ['name', 'icon']

@admin.register(Booking)
class BookingAdmin(ImportExportModelAdmin):
    list_display  = ['user', 'room', 'title', 'start_time', 'end_time', 'status', 'checked_in']
    list_filter   = ['status', 'checked_in', 'start_time']
    search_fields = ['user__username', 'room__name', 'title']
    # เพิ่ม Action สำหรับ Export แบบรวมไฟล์
    actions = [export_combined_data]

@admin.register(TermBooking)
class TermBookingAdmin(ImportExportModelAdmin):
    list_display  = ['user', 'room', 'subject_name', 'day_of_week', 'start_time', 'end_time', 'status']
    list_filter   = ['status', 'day_of_week', 'term_name']
    search_fields = ['subject_name', 'subject_code']

@admin.register(DemandForecast)
class DemandForecastAdmin(ImportExportModelAdmin):
    list_display = ['room', 'forecast_date', 'hour', 'demand_level', 'availability']
    list_filter = ['forecast_date', 'demand_level']

@admin.register(BookingLog)
class BookingLogAdmin(admin.ModelAdmin):
    list_display = ['booking', 'term_booking', 'changed_by', 'old_status', 'new_status', 'changed_at']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'title', 'is_read', 'created_at']

@admin.register(RoomUsageStat)
class RoomUsageStatAdmin(ImportExportModelAdmin):
    list_display = ['room', 'date', 'total_bookings', 'utilization_rate']
    list_filter = ['date']

@admin.register(MaintenanceBlock)
class MaintenanceBlockAdmin(admin.ModelAdmin):
    list_display = ['room', 'start_time', 'end_time', 'status', 'predicted_demand_avg']
    list_filter  = ['status', 'room__building']


@admin.register(RoomFacility)
class RoomFacilityAdmin(ImportExportModelAdmin):
    list_display = ['room', 'facility', 'quantity']
    list_filter = ['facility', 'room__building']