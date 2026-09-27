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
