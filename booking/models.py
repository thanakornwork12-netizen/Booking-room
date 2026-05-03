# booking/models.py

import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


# ============================================================
# 1. USER
# ============================================================
class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin',    'ผู้ดูแลระบบ'),
        ('staff',    'เจ้าหน้าที่'),
        ('lecturer', 'อาจารย์'),
        ('student',  'นักศึกษา'),
    ]
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    faculty    = models.CharField(max_length=100, blank=True, verbose_name='คณะ/หน่วยงาน')
    phone      = models.CharField(max_length=20, blank=True)
    avatar     = models.ImageField(upload_to='avatars/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ผู้ใช้งาน'

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"


# ============================================================
# 2. BUILDING
# ============================================================
class Building(models.Model):
    name        = models.CharField(max_length=100)
    code        = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'อาคาร'

    def __str__(self):
        return f"{self.code} - {self.name}"


# ============================================================
# 3. ROOM
# ============================================================
class Room(models.Model):
    STATUS_CHOICES = [
        ('available',   'ว่าง'),
        ('occupied',    'ถูกใช้งาน'),
        ('maintenance', 'ซ่อมบำรุง'),
        ('disabled',    'ปิดใช้งาน'),
    ]
    building    = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='rooms')
    name        = models.CharField(max_length=50)
    floor       = models.IntegerField()
    capacity    = models.IntegerField()
    room_type   = models.CharField(max_length=50)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    image       = models.ImageField(upload_to='rooms/', null=True, blank=True)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ห้อง'
        unique_together = ('building', 'name')

    def __str__(self):
        return f"{self.building.code}-{self.name} (จุ {self.capacity} คน)"


# ============================================================
# 4. FACILITIES
# ============================================================
class Facility(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='ชื่ออุปกรณ์')
    icon = models.CharField(max_length=50, blank=True, help_text='เช่น fa-wifi, fa-tv')

    class Meta:
        verbose_name = 'มาสเตอร์อุปกรณ์'
        verbose_name_plural = 'มาสเตอร์อุปกรณ์'

    def __str__(self):
        return self.name


class RoomFacility(models.Model):
    room     = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='room_facilities')
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, verbose_name='อุปกรณ์')
    quantity = models.IntegerField(default=1, verbose_name='จำนวน')

    class Meta:
        verbose_name = 'อุปกรณ์ประจำห้อง'
        unique_together = ('room', 'facility')

    def __str__(self):
        return f"{self.room.name} — {self.facility.name} ({self.quantity})"


# ============================================================
# 5. TERM BOOKING
# ============================================================
class TermBooking(models.Model):
    STATUS_CHOICES = [
        ('active',    'ใช้งานอยู่'),
        ('cancelled', 'ยกเลิกแล้ว'),
        ('ended',     'หมดเทอมแล้ว'),
    ]
    DAY_CHOICES = [
        (0, 'จันทร์'),
        (1, 'อังคาร'),
        (2, 'พุธ'),
        (3, 'พฤหัสบดี'),
        (4, 'ศุกร์'),
        (5, 'เสาร์'),
        (6, 'อาทิตย์'),
    ]

    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='term_bookings')
    room          = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='term_bookings')
    subject_name  = models.CharField(max_length=200, verbose_name='ชื่อรายวิชา/กิจกรรม')
    subject_code  = models.CharField(max_length=20, blank=True, verbose_name='รหัสวิชา')
    attendees     = models.IntegerField(verbose_name='จำนวนนักศึกษา/ผู้เข้าร่วม')
    day_of_week   = models.IntegerField(choices=DAY_CHOICES, verbose_name='วันในสัปดาห์')
    start_time    = models.TimeField(verbose_name='เวลาเริ่ม')
    end_time      = models.TimeField(verbose_name='เวลาสิ้นสุด')
    term_start    = models.DateField(verbose_name='วันเริ่มเทอม')
    term_end      = models.DateField(verbose_name='วันสิ้นสุดเทอม')
    term_name     = models.CharField(max_length=50, blank=True, verbose_name='ชื่อเทอม')
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    note          = models.TextField(blank=True)
    approved_by   = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_term_bookings'
    )
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'การจองทั้งเทอม'
        ordering = ['day_of_week', 'start_time']

    def get_weekly_slots(self):
        from datetime import timedelta
        slots = []
        curr = self.term_start
        while curr <= self.term_end:
            if curr.weekday() == self.day_of_week:
                slots.append(curr)
            curr += timedelta(days=1)
        return slots

    @property
    def total_weeks(self):
        return len(self.get_weekly_slots())

    def __str__(self):
        days = ['จ','อ','พ','พฤ','ศ','ส','อา']
        return f"{self.subject_name} | {self.room} | ทุกวัน{days[self.day_of_week]} {self.start_time:%H:%M}–{self.end_time:%H:%M}"


# ============================================================
# 6. BOOKING — จองรายวัน
# ============================================================
class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending',    'รอยืนยัน'),
        ('approved',   'อนุมัติแล้ว'),
        ('rejected',   'ปฏิเสธ'),
        ('cancelled',  'ยกเลิก'),
        ('completed',  'เสร็จสิ้น'),
        ('no_show',    'ไม่มาใช้งาน'),
        ('checked_in', 'เช็คอินแล้ว'),  # ✅ เพิ่ม
    ]

    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    room           = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    title          = models.CharField(max_length=200, verbose_name='ชื่อกิจกรรม/วัตถุประสงค์')
    attendees      = models.IntegerField()
    start_time     = models.DateTimeField()
    end_time       = models.DateTimeField()
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note           = models.TextField(blank=True)
    checked_in     = models.BooleanField(default=False)
    checked_in_at  = models.DateTimeField(null=True, blank=True)   # ✅ เพิ่ม
    checkin_token  = models.UUIDField(default=uuid.uuid4, editable=False)  # ✅ เพิ่ม
    reminded       = models.BooleanField(default=False)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)
    approved_by    = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_bookings'
    )

    class Meta:
        verbose_name = 'การจองรายวัน'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} | {self.room} | {self.start_time:%d/%m/%Y %H:%M}"


# ============================================================
# 7. BOOKING LOG
# ============================================================
class BookingLog(models.Model):
    booking      = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='logs', null=True, blank=True)
    term_booking = models.ForeignKey(TermBooking, on_delete=models.CASCADE, related_name='logs', null=True, blank=True)
    changed_by   = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    old_status   = models.CharField(max_length=20)
    new_status   = models.CharField(max_length=20)
    remark       = models.TextField(blank=True)
    changed_at   = models.DateTimeField(auto_now_add=True)


# ============================================================
# 8. DEMAND FORECAST
# ============================================================
class DemandForecast(models.Model):
    DEMAND_LEVEL_CHOICES = [
        ('low',    'ต่ำ'),
        ('medium', 'ปานกลาง'),
        ('high',   'สูง'),
        ('urgent', 'เร่งด่วน'),
    ]
    AVAILABILITY_CHOICES = [
        ('likely_available', '🟢 ยังว่าง'),
        ('recommended',      '🟡 ควรจอง'),
        ('book_soon',        '🟠 รีบจอง'),
        ('book_now',         '🔴 ควรจองตอนนี้เลย'),
    ]

    room             = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='forecasts')
    forecast_date    = models.DateField()
    hour             = models.IntegerField()
    predicted_demand = models.FloatField(help_text='0.0 – 1.0')
    demand_level     = models.CharField(max_length=10, choices=DEMAND_LEVEL_CHOICES, default='low')
    availability     = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='likely_available')
    confidence       = models.FloatField(default=0.0)
    term_demand      = models.FloatField(default=0.0)
    dynamic_demand   = models.FloatField(default=0.0)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'การพยากรณ์ความต้องการ'
        unique_together = ('room', 'forecast_date', 'hour')
        ordering = ['forecast_date', 'hour']

    def __str__(self):
        return f"{self.room} | {self.forecast_date} {self.hour:02d}:00 | {self.get_availability_display()}"


# ============================================================
# 9. NOTIFICATION
# ============================================================
class Notification(models.Model):
    TYPE_CHOICES = [
        ('booking_approved',  'การจองได้รับอนุมัติ'),
        ('booking_rejected',  'การจองถูกปฏิเสธ'),
        ('booking_reminder',  'เตือนก่อนใช้งาน'),
        ('booking_cancelled', 'การจองถูกยกเลิก'),
        ('term_approved',     'การจองทั้งเทอมได้รับอนุมัติ'),
        ('demand_alert',      'แจ้งเตือนความต้องการสูง'),
        ('system',            'ระบบ'),
    ]
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    booking      = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)
    term_booking = models.ForeignKey(TermBooking, null=True, blank=True, on_delete=models.SET_NULL)
    type         = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title        = models.CharField(max_length=200)
    message      = models.TextField()
    is_read      = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)


# ============================================================
# 10. ROOM USAGE STATS
# ============================================================
class RoomUsageStat(models.Model):
    room               = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='stats')
    date               = models.DateField()
    total_bookings     = models.IntegerField(default=0)
    term_bookings      = models.IntegerField(default=0)
    dynamic_bookings   = models.IntegerField(default=0)
    utilization_rate   = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('room', 'date')