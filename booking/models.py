from django.db import models
from django.contrib.auth.models import AbstractUser


# ============================================================
# 1. USER — ผู้ใช้งานระบบ
# ============================================================
class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin',     'ผู้ดูแลระบบ'),
        ('staff',     'เจ้าหน้าที่'),
        ('lecturer',  'อาจารย์'),
        ('student',   'นักศึกษา'),
    ]

    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    faculty    = models.CharField(max_length=100, blank=True, verbose_name='คณะ/หน่วยงาน')
    phone      = models.CharField(max_length=20, blank=True, verbose_name='เบอร์โทร')
    avatar     = models.ImageField(upload_to='avatars/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ผู้ใช้งาน'

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"


# ============================================================
# 2. BUILDING — อาคาร
# ============================================================
class Building(models.Model):
    name        = models.CharField(max_length=100, verbose_name='ชื่ออาคาร')
    code        = models.CharField(max_length=10, unique=True, verbose_name='รหัสอาคาร')
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'อาคาร'

    def __str__(self):
        return f"{self.code} - {self.name}"


# ============================================================
# 3. ROOM — ห้อง
# ============================================================
class Room(models.Model):
    STATUS_CHOICES = [
        ('available',   'ว่าง'),
        ('occupied',    'ถูกใช้งาน'),
        ('maintenance', 'ซ่อมบำรุง'),
        ('disabled',    'ปิดใช้งาน'),
    ]

    building    = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='rooms')
    name        = models.CharField(max_length=50, verbose_name='ชื่อห้อง')
    floor       = models.IntegerField(verbose_name='ชั้น')
    capacity    = models.IntegerField(verbose_name='ความจุ (คน)')
    room_type   = models.CharField(max_length=50, verbose_name='ประเภทห้อง')
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
# 4. ROOM FACILITY — อุปกรณ์ในห้อง
# ============================================================
class RoomFacility(models.Model):
    room     = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='facilities')
    name     = models.CharField(max_length=100, verbose_name='ชื่ออุปกรณ์')
    quantity = models.IntegerField(default=1, verbose_name='จำนวน')

    class Meta:
        verbose_name = 'อุปกรณ์ในห้อง'

    def __str__(self):
        return f"{self.room} — {self.name} x{self.quantity}"


# ============================================================
# 5. BOOKING — การจองห้อง
# ============================================================
class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending',   'รอยืนยัน'),
        ('approved',  'อนุมัติแล้ว'),
        ('rejected',  'ปฏิเสธ'),
        ('cancelled', 'ยกเลิก'),
        ('completed', 'เสร็จสิ้น'),
        ('no_show',   'ไม่มาใช้งาน'),
    ]

    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    room        = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    title       = models.CharField(max_length=200, verbose_name='ชื่อกิจกรรม/วัตถุประสงค์')
    attendees   = models.IntegerField(verbose_name='จำนวนผู้เข้าร่วม')
    start_time  = models.DateTimeField(verbose_name='เวลาเริ่ม')
    end_time    = models.DateTimeField(verbose_name='เวลาสิ้นสุด')
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note        = models.TextField(blank=True, verbose_name='หมายเหตุ')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    
    checked_in = models.BooleanField(default=False, verbose_name='Check-in แล้ว')
    reminded   = models.BooleanField(default=False, verbose_name='แจ้งเตือนแล้ว')
    approved_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_bookings'
    )

    class Meta:
        verbose_name = 'การจอง'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} | {self.room} | {self.start_time:%d/%m/%Y %H:%M}"

    def duration_hours(self):
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600


# ============================================================
# 6. BOOKING LOG — ประวัติการเปลี่ยนสถานะ
# ============================================================
class BookingLog(models.Model):
    booking    = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='logs')
    changed_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    remark     = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ประวัติการจอง'
        ordering = ['-changed_at']


# ============================================================
# 7. DEMAND FORECAST — ผลพยากรณ์จาก ML (Stacking Ensemble)
#
# โมเดลจะเทรนจากข้อมูล Booking แล้วเขียนผลลงตารางนี้
# ระบบอ่านค่าจากตารางนี้ไปแสดงผลบนหน้าเว็บ
#
# ตัวอย่างที่โมเดลจะทำนาย:
#   ห้อง A201 | จันทร์ 09:00 → predicted_demand = 85.0
#   → demand_level  = 'high'
#   → availability  = 'likely_full'   ← แสดงผลให้ User เห็น
# ============================================================
class DemandForecast(models.Model):

    # ระดับความต้องการ (โมเดลทำนายออกมาเป็นตัวเลข 0-100 แล้ว Map เป็น level นี้)
    DEMAND_LEVEL_CHOICES = [
        ('low',    'ต่ำ'),       # 0 – 34
        ('medium', 'ปานกลาง'),  # 35 – 69
        ('high',   'สูง'),       # 70 – 100
    ]

    # สถานะที่ระบบแสดงให้ผู้ใช้เห็น (แปลจาก demand_level อีกทีเพื่อความชัดเจน)
    AVAILABILITY_CHOICES = [
        ('likely_available', '🟢 มีโอกาสว่างสูง'),    # demand ต่ำ
        ('likely_busy',      '🟡 มีโอกาสแน่นปานกลาง'), # demand ปานกลาง
        ('likely_full',      '🔴 มีโอกาสเต็ม'),        # demand สูง
    ]

    room          = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='forecasts')
    forecast_date = models.DateField(verbose_name='วันที่พยากรณ์')
    hour          = models.IntegerField(verbose_name='ชั่วโมง (0-23)')

    # ค่าตัวเลขดิบที่โมเดลคำนวณออกมา (0 – 100)
    predicted_demand = models.FloatField(
        verbose_name='ค่าความต้องการที่คาดการณ์ (0–100)',
        help_text='0 = ไม่มีความต้องการเลย, 100 = ต้องการสูงสุด'
    )

    # ระดับที่แปลงจากตัวเลขแล้ว (low / medium / high)
    demand_level = models.CharField(
        max_length=10,
        choices=DEMAND_LEVEL_CHOICES,
        default='low',
        verbose_name='ระดับความต้องการ'
    )

    # สถานะที่แสดงให้ผู้ใช้เห็นบนหน้าเว็บ
    availability = models.CharField(
        max_length=20,
        choices=AVAILABILITY_CHOICES,
        default='likely_available',
        verbose_name='สถานะที่คาดการณ์'
    )

    # ความมั่นใจของโมเดล (0-100%) — ไว้แสดงใน Dashboard Admin
    confidence = models.FloatField(
        default=0.0,
        verbose_name='ความมั่นใจของโมเดล (%)',
        help_text='0-100 เปอร์เซ็นต์'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'การพยากรณ์ความต้องการ'
        unique_together = ('room', 'forecast_date', 'hour')
        ordering = ['forecast_date', 'hour']

    def __str__(self):
        return (
            f"{self.room} | "
            f"{self.forecast_date} {self.hour:02d}:00 | "
            f"{self.get_availability_display()} "
            f"({self.predicted_demand:.1f}%)"  # ← แสดง 42.3% ถูกต้อง
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


# ============================================================
# 8. NOTIFICATION — การแจ้งเตือน
# ============================================================
class Notification(models.Model):
    TYPE_CHOICES = [
        ('booking_approved',  'การจองได้รับอนุมัติ'),
        ('booking_rejected',  'การจองถูกปฏิเสธ'),
        ('booking_reminder',  'เตือนก่อนใช้งาน'),
        ('booking_cancelled', 'การจองถูกยกเลิก'),
        ('demand_alert',      'แจ้งเตือนความต้องการสูง'),
        ('system',            'ระบบ'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    booking    = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)
    type       = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title      = models.CharField(max_length=200)
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'การแจ้งเตือน'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} — {self.title}"


# ============================================================
# 9. ROOM USAGE STATS — สถิติรายวันสำหรับ Dashboard
# ============================================================
class RoomUsageStat(models.Model):
    room             = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='stats')
    date             = models.DateField(verbose_name='วันที่')
    total_bookings   = models.IntegerField(default=0, verbose_name='จำนวนการจองทั้งหมด')
    completed        = models.IntegerField(default=0, verbose_name='ใช้งานจริง')
    no_show          = models.IntegerField(default=0, verbose_name='ไม่มาใช้งาน')
    cancelled        = models.IntegerField(default=0, verbose_name='ยกเลิก')
    utilization_rate = models.FloatField(default=0.0, verbose_name='อัตราการใช้งาน (%)')

    class Meta:
        verbose_name = 'สถิติห้อง'
        unique_together = ('room', 'date')

    def __str__(self):
        return f"{self.room} | {self.date} | {self.utilization_rate:.1f}%"
