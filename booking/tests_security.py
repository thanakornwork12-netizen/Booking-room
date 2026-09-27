"""ทดสอบช่องโหว่ของหน้า HTML ที่ส่งให้ผู้ใช้ผ่านลิงก์ในอีเมล

หน้า check-in / cancel ทางอีเมลถูกประกอบด้วย f-string แล้วส่งเป็น HttpResponse
ดิบๆ ถ้าค่าที่ผู้ใช้กรอกเอง (ชื่อกิจกรรม, ชื่อห้อง) ไม่ถูก escape ก่อน ผู้จองจะ
ฝังสคริปต์ลงหน้าที่คนอื่นเปิดได้ (stored XSS)
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from booking.models import Booking, Building, Room, TermBooking

User = get_user_model()

PAYLOAD = '<script>alert("xss")</script>'


class EmailPageEscapingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        cls.room = Room.objects.create(
            building=cls.building, name='2C09', floor=1, capacity=40,
            room_type='ห้องเรียน',
        )

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='qa_test_bot', password='QaTest1234',
            email='qa_test_bot@example.com', role='student',
        )

    def make_booking(self, title=PAYLOAD, status='approved', minutes_ahead=5):
        start = timezone.now() + timedelta(minutes=minutes_ahead)
        return Booking.objects.create(
            user=self.user, room=self.room, title=title, attendees=10,
            start_time=start, end_time=start + timedelta(hours=1), status=status,
        )

    def assert_not_executable(self, response):
        html = response.content.decode()
        self.assertNotIn(PAYLOAD, html, 'สคริปต์ดิบหลุดลงหน้า HTML')
        self.assertIn('&lt;script&gt;', html, 'ข้อความควรถูก escape แล้วยังแสดงอยู่')

    def test_checkin_page_escapes_booking_title(self):
        b = self.make_booking()
        r = self.client.get(f'/api/bookings/{b.id}/checkin/{b.checkin_token}/')
        self.assertEqual(r.status_code, 200)
        self.assert_not_executable(r)

    def test_cancel_confirm_page_escapes_booking_title(self):
        b = self.make_booking()
        r = self.client.get(f'/api/bookings/{b.id}/cancel-email/{b.checkin_token}/')
        self.assertEqual(r.status_code, 200)
        self.assert_not_executable(r)

    def test_cancel_success_page_escapes_booking_title(self):
        b = self.make_booking()
        r = self.client.post(f'/api/bookings/{b.id}/cancel-email/{b.checkin_token}/')
        self.assertEqual(r.status_code, 200)
        self.assert_not_executable(r)

    def test_checkin_page_escapes_room_name(self):
        self.room.name = PAYLOAD
        self.room.save(update_fields=['name'])
        b = self.make_booking(title='ประชุมปกติ')
        r = self.client.get(f'/api/bookings/{b.id}/checkin/{b.checkin_token}/')
        self.assertEqual(r.status_code, 200)
        self.assert_not_executable(r)

    def test_already_checked_in_page_escapes_room_name(self):
        self.room.name = PAYLOAD
        self.room.save(update_fields=['name'])
        b = self.make_booking(title='ประชุมปกติ')
        b.checked_in = True
        b.save(update_fields=['checked_in'])
        r = self.client.get(f'/api/bookings/{b.id}/checkin/{b.checkin_token}/')
        self.assertEqual(r.status_code, 200)
        self.assert_not_executable(r)


class MaintenanceOverlapTests(TestCase):
    """ช่วงปิดซ่อมบำรุงเป็น DateTimeField ที่กินเวลาข้ามวันได้ (ดู docstring ของ
    MaintenanceBlock) แต่ perform_create ตรวจซ้อนกับ TermBooking โดยดู weekday
    ของ start_time วันเดียว — ช่วงที่กินหลายวันจึงทับคาบเรียนกลางสัปดาห์ได้
    """

    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        cls.room = Room.objects.create(
            building=cls.building, name='2C09', floor=1, capacity=40,
            room_type='ห้องเรียน',
        )

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='qa_admin', password='QaAdmin1234',
            email='qa_admin@example.com', role='admin',
        )
        self.client.force_authenticate(user=self.admin)

    def next_weekday(self, weekday, min_days=7):
        d = timezone.localdate() + timedelta(days=min_days)
        while d.weekday() != weekday:
            d += timedelta(days=1)
        return d

    def test_multi_day_block_cannot_cover_term_booking_midweek(self):
        from datetime import time as time_type

        mon = self.next_weekday(0)
        wed = mon + timedelta(days=2)
        TermBooking.objects.create(
            user=self.admin, room=self.room, subject_name='วิศวกรรมซอฟต์แวร์',
            attendees=30, day_of_week=2,  # วันพุธ
            start_time=time_type(10, 0), end_time=time_type(12, 0),
            term_start=mon - timedelta(days=7), term_end=wed + timedelta(days=60),
            status='active',
        )

        # ปิดซ่อม จันทร์ 08:00 → ศุกร์ 18:00 ครอบคาบเรียนวันพุธไว้เต็มๆ
        start = timezone.make_aware(timezone.datetime.combine(mon, time_type(8, 0)))
        end = timezone.make_aware(
            timezone.datetime.combine(mon + timedelta(days=4), time_type(18, 0)))
        r = self.client.post('/api/maintenance-blocks/', {
            'room': self.room.id,
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'reason': 'ซ่อมบำรุงเชิงป้องกัน',
        }, format='json')

        self.assertEqual(
            r.status_code, 400,
            f'ควรถูกปฏิเสธเพราะทับคาบเรียนวันพุธ แต่ได้ {r.status_code}')
        self.assertIn('จองทั้งเทอม', str(r.data))

    def test_same_day_block_over_term_booking_still_rejected(self):
        """กรณีวันเดียว (สาขาเดิมของ _recurring_slot_conflicts) ต้องยังปฏิเสธ"""
        from datetime import time as time_type

        wed = self.next_weekday(2)
        TermBooking.objects.create(
            user=self.admin, room=self.room, subject_name='วิศวกรรมซอฟต์แวร์',
            attendees=30, day_of_week=2,
            start_time=time_type(10, 0), end_time=time_type(12, 0),
            term_start=wed - timedelta(days=7), term_end=wed + timedelta(days=60),
            status='active',
        )
        start = timezone.make_aware(timezone.datetime.combine(wed, time_type(11, 0)))
        end = timezone.make_aware(timezone.datetime.combine(wed, time_type(13, 0)))
        r = self.client.post('/api/maintenance-blocks/', {
            'room': self.room.id,
            'start_time': start.isoformat(), 'end_time': end.isoformat(),
            'reason': 'ซ่อมบำรุงเชิงป้องกัน',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_block_not_touching_term_booking_is_allowed(self):
        """ช่วงที่ไม่ชนคาบเรียนเลยต้องสร้างได้ตามปกติ (กันแก้แล้วเข้มเกินไป)"""
        from datetime import time as time_type

        wed = self.next_weekday(2)
        TermBooking.objects.create(
            user=self.admin, room=self.room, subject_name='วิศวกรรมซอฟต์แวร์',
            attendees=30, day_of_week=2,
            start_time=time_type(10, 0), end_time=time_type(12, 0),
            term_start=wed - timedelta(days=7), term_end=wed + timedelta(days=60),
            status='active',
        )
        start = timezone.make_aware(timezone.datetime.combine(wed, time_type(13, 0)))
        end = timezone.make_aware(timezone.datetime.combine(wed, time_type(15, 0)))
        r = self.client.post('/api/maintenance-blocks/', {
            'room': self.room.id,
            'start_time': start.isoformat(), 'end_time': end.isoformat(),
            'reason': 'ซ่อมบำรุงเชิงป้องกัน',
        }, format='json')
        self.assertEqual(r.status_code, 201, str(r.data))
