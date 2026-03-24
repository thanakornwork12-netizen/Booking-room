from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# ============================================================
# 1. USER — ผู้ใช้งานระบบ
# ============================================================
class User(AbstractUser):
    """
    ขยายจาก Django User เดิม เพิ่ม role และข้อมูลเฉพาะมหาวิทยาลัย
    """
    ROLE_CHOICES = [
        ('admin',     'ผู้ดูแลระบบ'),
        ('staff',     'เจ้าหน้าที่'),
        ('lecturer',  'อาจารย์'),
        ('student',   'นักศึกษา'),
    ]

    role        = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    faculty     = models.CharField(max_length=100, blank=True, verbose_name='คณะ/หน่วยงาน')
    phone       = models.CharField(max_length=20, blank=True, verbose_name='เบอร์โทร')
    avatar      = models.ImageField(upload_to='avatars/', null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ผู้ใช้งาน'

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"


# ============================================================
# 2. BUILDING — อาคาร
# ============================================================
class Building(models.Model):
    """
    อาคารหรือตึกภายในมหาวิทยาลัย
    """
    name        = models.CharField(max_length=100, verbose_name='ชื่ออาคาร')
    code        = models.CharField(max_length=10, unique=True, verbose_name='รหัสอาคาร')  # เช่น SC, EN, LA
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
    """
    ข้อมูลห้องแต่ละห้อง
    """
    STATUS_CHOICES = [
        ('available',    'ว่าง'),
        ('occupied',     'ถูกใช้งาน'),
        ('maintenance',  'ซ่อมบำรุง'),
        ('disabled',     'ปิดใช้งาน'),
    ]

    building     = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='rooms')
    name         = models.CharField(max_length=50, verbose_name='ชื่อห้อง')         # เช่น A201
    floor        = models.IntegerField(verbose_name='ชั้น')
    capacity     = models.IntegerField(verbose_name='ความจุ (คน)')
    room_type    = models.CharField(max_length=50, verbose_name='ประเภทห้อง')       # เช่น ห้องประชุม, ห้องเรียน
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    image        = models.ImageField(upload_to='rooms/', null=True, blank=True)
    description  = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ห้อง'
        unique_together = ('building', 'name')  # ห้องชื่อซ้ำกันไม่ได้ในอาคารเดียวกัน

    def __str__(self):
        return f"{self.building.code}-{self.name} (จุ {self.capacity} คน)"


# ============================================================
# 4. ROOM FACILITY — อุปกรณ์/สิ่งอำนวยความสะดวกในห้อง
# ============================================================
class RoomFacility(models.Model):
    """
    อุปกรณ์ที่มีในห้อง เช่น โปรเจกเตอร์ ระบบเสียง TV กระดาน
    """
    room     = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='facilities')
    name     = models.CharField(max_length=100, verbose_name='ชื่ออุปกรณ์')
    quantity = models.IntegerField(default=1, verbose_name='จำนวน')

    class Meta:
        verbose_name = 'อุปกรณ์ในห้อง'

    def __str__(self):
        return f"{self.room} — {self.name} x{self.quantity}"


# ============================================================
# 5. BOOKING — การจองห้อง (ตารางหลักสำคัญที่สุด)
# ============================================================
class Booking(models.Model):
    """
    บันทึกการจองห้องทุกครั้ง — ใช้เป็น Training Data ของ LSTM ด้วย
    """
    STATUS_CHOICES = [
        ('pending',   'รอยืนยัน'),
        ('approved',  'อนุมัติแล้ว'),
        ('rejected',  'ปฏิเสธ'),
        ('cancelled', 'ยกเลิก'),
        ('completed', 'เสร็จสิ้น'),
        ('no_show',   'ไม่มาใช้งาน'),  # สำคัญมาก — ใช้วิเคราะห์ No-show Pattern
    ]

    SOURCE_CHOICES = [
        ('chatbot', 'แชตบอท'),
        ('web',     'เว็บแอป'),
        ('admin',   'Admin'),
    ]

    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    room          = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    title         = models.CharField(max_length=200, verbose_name='ชื่อกิจกรรม/วัตถุประสงค์')
    attendees     = models.IntegerField(verbose_name='จำนวนผู้เข้าร่วม')
    start_time    = models.DateTimeField(verbose_name='เวลาเริ่ม')
    end_time      = models.DateTimeField(verbose_name='เวลาสิ้นสุด')
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    source        = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='web')
    note          = models.TextField(blank=True, verbose_name='หมายเหตุ')
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
    approved_by   = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_bookings'
    )

    class Meta:
        verbose_name = 'การจอง'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} | {self.room} | {self.start_time:%d/%m/%Y %H:%M}"

    def duration_hours(self):
        """ระยะเวลาการจองเป็นชั่วโมง — ใช้วิเคราะห์"""
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600


# ============================================================
# 6. BOOKING LOG — ประวัติการเปลี่ยนสถานะการจอง
# ============================================================
class BookingLog(models.Model):
    """
    บันทึกทุกครั้งที่สถานะการจองเปลี่ยน เช่น pending → approved
    ใช้สำหรับ Audit Trail และวิเคราะห์พฤติกรรม
    """
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
# 7. DEMAND FORECAST — ผลการพยากรณ์ความต้องการจาก LSTM
# ============================================================
class DemandForecast(models.Model):
    """
    เก็บผลที่ LSTM Model ทำนายไว้ ระบบอ่านจาก Table นี้ไปแสดงผล
    รัน LSTM ทุกคืน แล้ว Insert ผลลัพธ์มาเก็บที่นี่
    """
    room            = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='forecasts')
    forecast_date   = models.DateField(verbose_name='วันที่พยากรณ์')
    hour            = models.IntegerField(verbose_name='ชั่วโมง (0-23)')
    predicted_demand = models.FloatField(verbose_name='ความต้องการที่คาดการณ์ (0-1)')
    demand_level    = models.CharField(
        max_length=10,
        choices=[('low','ต่ำ'), ('medium','ปานกลาง'), ('high','สูง')],
        default='low'
    )
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'การพยากรณ์ความต้องการ'
        unique_together = ('room', 'forecast_date', 'hour')

    def __str__(self):
        return f"{self.room} | {self.forecast_date} {self.hour}:00 | {self.predicted_demand:.2f}"


# ============================================================
# 8. NOTIFICATION — การแจ้งเตือน
# ============================================================
class Notification(models.Model):
    """
    แจ้งเตือนผู้ใช้ เช่น การจองได้รับอนุมัติ, เตือนก่อนใช้ห้อง 30 นาที
    """
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
# 9. CHAT SESSION — ประวัติการคุยกับ Chatbot
# ============================================================
class ChatSession(models.Model):
    """
    Session การสนทนากับแชตบอท 1 Session = 1 การสนทนาต่อเนื่อง
    """
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions')
    started_at  = models.DateTimeField(auto_now_add=True)
    ended_at    = models.DateTimeField(null=True, blank=True)
    booking     = models.ForeignKey(
        Booking, null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text='การจองที่เกิดขึ้นจาก Session นี้'
    )

    class Meta:
        verbose_name = 'เซสชันแชตบอท'

    def __str__(self):
        return f"Chat #{self.id} — {self.user} — {self.started_at:%d/%m/%Y %H:%M}"


class ChatMessage(models.Model):
    """
    ข้อความแต่ละข้อความใน Chat Session
    """
    SENDER_CHOICES = [
        ('user', 'ผู้ใช้'),
        ('bot',  'แชตบอท'),
    ]

    session    = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender     = models.CharField(max_length=10, choices=SENDER_CHOICES)
    message    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ข้อความแชต'
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.sender}] {self.message[:50]}"


# ============================================================
# 10. ROOM USAGE STATS — สถิติรายวัน (Pre-computed สำหรับ Dashboard)
# ============================================================
class RoomUsageStat(models.Model):
    """
    สถิติการใช้งานห้องรายวัน คำนวณล่วงหน้าไว้สำหรับแสดง Dashboard
    ไม่ต้อง Query Booking ทุกครั้ง ช่วยให้ Dashboard โหลดเร็ว
    """
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