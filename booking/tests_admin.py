"""สิทธิ์ของ endpoint ฝั่งผู้ดูแลระบบ — ครอบเส้นทางที่ชุดทดสอบอื่นยังไม่แตะ
(export Excel, dashboard, สถิติ, ช่วงแนะนำปิดซ่อม, จัดการห้อง)
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from booking.models import Building, Room

User = get_user_model()


class AdminEndpointPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        cls.room = Room.objects.create(
            building=cls.building, name='2C09', floor=1, capacity=40, room_type='ห้องเรียน')
        cls.student = User.objects.create_user(
            username='qa_test_bot', password='QaTest1234', role='student')
        cls.admin = User.objects.create_user(
            username='qa_admin', password='QaAdmin1234', role='admin')
        cls.staff = User.objects.create_user(
            username='qa_staff', password='QaStaff1234', role='staff')

    def setUp(self):
        self.client = APIClient()

    def get_as(self, user, url):
        self.client.force_authenticate(user=user)
        return self.client.get(url)

    def test_export_excel_admin_gets_xlsx(self):
        r = self.get_as(self.admin, '/api/export/excel/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('spreadsheetml', r['Content-Type'])

    def test_export_excel_every_sheet_builds(self):
        """ขอทุกชีตที่ export รองรับ — ถ้า model ตัวไหนหาย import ไปจะพังตรงนี้"""
        r = self.get_as(self.admin, '/api/export/excel/?sheets=all')
        self.assertEqual(r.status_code, 200)

    def test_export_excel_student_forbidden(self):
        r = self.get_as(self.student, '/api/export/excel/')
        self.assertEqual(r.status_code, 403)

    def test_dashboard(self):
        self.assertEqual(self.get_as(self.admin, '/api/dashboard/').status_code, 200)
        self.assertEqual(self.get_as(self.staff, '/api/dashboard/').status_code, 200)
        self.assertEqual(self.get_as(self.student, '/api/dashboard/').status_code, 403)

    def test_usage_stats(self):
        self.assertEqual(self.get_as(self.admin, '/api/rooms/usage-stats/').status_code, 200)
        self.assertEqual(self.get_as(self.student, '/api/rooms/usage-stats/').status_code, 403)

    def test_maintenance_slots(self):
        self.assertEqual(self.get_as(self.admin, '/api/maintenance/slots/').status_code, 200)
        self.assertEqual(self.get_as(self.student, '/api/maintenance/slots/').status_code, 403)

    def test_maintenance_blocks_list(self):
        self.assertEqual(self.get_as(self.admin, '/api/maintenance-blocks/').status_code, 200)
        self.assertEqual(self.get_as(self.student, '/api/maintenance-blocks/').status_code, 403)

    def test_room_queryset_scoped_by_role(self):
        """นักศึกษาเห็นเฉพาะห้อง AI (ห้องทดสอบนี้ไม่อยู่ในรายการ) แอดมินเห็นทุกห้อง"""
        def names(user):
            r = self.get_as(user, '/api/rooms/')
            rows = r.data['results'] if isinstance(r.data, dict) else r.data
            return [row['name'] for row in rows]
        self.assertIn('2C09', names(self.admin))
        self.assertNotIn('2C09', names(self.student))

    def test_student_cannot_edit_room(self):
        self.client.force_authenticate(user=self.student)
        r = self.client.patch(f'/api/rooms/{self.room.id}/', {'capacity': 999}, format='json')
        self.room.refresh_from_db()
        self.assertIn(r.status_code, (403, 404))
        self.assertEqual(self.room.capacity, 40)

    def test_admin_can_edit_room(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.patch(f'/api/rooms/{self.room.id}/', {'capacity': 45}, format='json')
        self.room.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.room.capacity, 45)


class MaintenanceLifecycleTests(TestCase):
    """สร้าง / ปฏิเสธเมื่อทับ / ปิดงาน ของช่วงซ่อมบำรุง และสถานะห้องที่ตามมา"""

    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        cls.admin = User.objects.create_user(
            username='qa_admin', password='QaAdmin1234', role='admin')

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        self.room = Room.objects.create(
            building=self.building, name='2C09', floor=1, capacity=40, room_type='ห้องเรียน')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.start = timezone.now() + timedelta(days=10)
        self.end = self.start + timedelta(hours=4)

    def create_block(self, start, end):
        return self.client.post('/api/maintenance-blocks/', {
            'room': self.room.id, 'start_time': start.isoformat(),
            'end_time': end.isoformat(), 'reason': 'ซ่อมบำรุงเชิงป้องกัน',
        }, format='json')

    def test_future_block_keeps_room_available(self):
        """ช่วงซ่อมล่วงหน้าไม่ทำให้ห้องขึ้น "ซ่อมบำรุง" ตั้งแต่วันนี้ (ไม่งั้นห้องหายจากการค้นหา)"""
        r = self.create_block(self.start, self.end)
        self.room.refresh_from_db()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.room.status, 'available')

    def test_current_block_sets_room_status(self):
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        r = self.create_block(now + timedelta(minutes=1), now + timedelta(hours=3))
        self.assertEqual(r.status_code, 201, r.data)
        from booking.models import MaintenanceBlock
        MaintenanceBlock.objects.filter(room=self.room).update(start_time=now - timedelta(minutes=5))
        # สร้างอีกช่วงที่ครอบตอนนี้ผ่าน API ไม่ได้ (ชนกัน) จึงตรวจที่ status-feed แทน
        rows = self.client.get('/api/rooms/status-feed/').data
        state = next(r['state'] for r in rows if r.get('id') == self.room.id or r.get('room_id') == self.room.id)
        self.assertEqual(state, 'maintenance')

    def test_rejects_overlapping_booking(self):
        from booking.models import Booking
        Booking.objects.create(user=self.admin, room=self.room, title='ประชุม', attendees=5,
                               start_time=self.start, end_time=self.end, status='approved')
        r = self.create_block(self.start, self.end)
        self.assertEqual(r.status_code, 400)
        self.assertIn('ไม่สามารถปิดซ่อมบำรุงได้', str(r.data))

    def test_rejects_overlapping_block(self):
        self.create_block(self.start, self.end)
        r = self.create_block(self.start, self.end)
        self.assertEqual(r.status_code, 400)
        self.assertIn('ปิดซ่อมบำรุงในช่วงเวลาดังกล่าวอยู่แล้ว', str(r.data))

    def test_complete_and_cancel_restore_room(self):
        from datetime import timedelta
        first = self.create_block(self.start, self.end).data
        second_start = self.end + timedelta(days=1)
        second = self.create_block(second_start, second_start + timedelta(hours=2)).data
        blocks = self.client.get('/api/maintenance-blocks/').data
        rows = blocks['results'] if isinstance(blocks, dict) else blocks
        ids = sorted(row['id'] for row in rows)
        self.assertEqual(len(ids), 2, (first, second))

        self.room.status = 'maintenance'   # จำลองว่าช่วงแรกเริ่มซ่อมไปแล้ว
        self.room.save(update_fields=['status'])
        r = self.client.post(f'/api/maintenance-blocks/{ids[0]}/complete/')
        self.room.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.room.status, 'maintenance', 'ยังเหลืออีกช่วงค้างอยู่')

        r = self.client.post(f'/api/maintenance-blocks/{ids[1]}/cancel/')
        self.room.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.room.status, 'available')


class DemandLevelTests(TestCase):
    def test_thresholds_at_each_boundary(self):
        from booking.views import _demand_level_for
        cases = [
            (0.95, ('urgent', 'book_now')), (0.70, ('urgent', 'book_now')),
            (0.69, ('high', 'book_soon')),  (0.50, ('high', 'book_soon')),
            (0.49, ('medium', 'recommended')), (0.30, ('medium', 'recommended')),
            (0.29, ('low', 'likely_available')), (0.0, ('low', 'likely_available')),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(_demand_level_for(value), expected)


class StatusFeedTests(TestCase):
    """ลำดับความสำคัญของสถานะห้องใน status-feed"""

    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        cls.user = User.objects.create_user(username='qa_test_bot', password='x', role='student')

    def state_of(self, room):
        client = APIClient()
        client.force_authenticate(user=self.user)
        rows = client.get('/api/rooms/status-feed/').data
        rows = rows.get('rooms', rows) if isinstance(rows, dict) else rows
        return next(r for r in rows if r.get('id') == room.id or r.get('room_id') == room.id)

    def make_room(self, name):
        return Room.objects.create(building=self.building, name=name, floor=1,
                                   capacity=40, room_type='ห้องเรียน')

    def test_free_active_and_active_beats_pending(self):
        from datetime import timedelta
        from django.utils import timezone
        from booking.models import Booking
        free_room, busy_room = self.make_room('R-FREE'), self.make_room('R-BUSY')
        now = timezone.now()
        Booking.objects.create(user=self.user, room=busy_room, title='x', attendees=5,
                               start_time=now - timedelta(minutes=30),
                               end_time=now + timedelta(minutes=30), status='approved')
        Booking.objects.create(user=self.user, room=busy_room, title='y', attendees=5,
                               start_time=now + timedelta(hours=2),
                               end_time=now + timedelta(hours=3), status='pending')
        self.assertEqual(self.state_of(free_room)['state'], 'free')
        self.assertEqual(self.state_of(busy_room)['state'], 'active')


class StatusFeedCheckedInTests(StatusFeedTests):
    def test_checked_in_room_shows_active(self):
        from datetime import timedelta
        from django.utils import timezone
        from booking.models import Booking
        room = self.make_room('R-CHECKIN')
        now = timezone.now()
        Booking.objects.create(user=self.user, room=room, title='x', attendees=5,
                               start_time=now - timedelta(minutes=10),
                               end_time=now + timedelta(minutes=50), status='checked_in',
                               checked_in=True)
        self.assertEqual(self.state_of(room)['state'], 'active',
                         'ห้องที่เช็คอินแล้วขึ้นว่า "ว่าง"')
