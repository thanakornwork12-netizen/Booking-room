"""QA ทั้งระบบรอบกลางคืน (17 ต.ค. 69) — ไล่ทุกเส้นทางหาบั๊กที่เทสต์เดิมยังไม่ครอบ
รัน: python manage.py test booking.tests_overnight --noinput"""
from datetime import time as time_type, timedelta
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from booking.models import Booking, Building, Room, User
from booking.tests_qa import QABase, aware


# ══════════════════════════════════════════════════════════════
# ล็อกอิน LDAP
# ══════════════════════════════════════════════════════════════
class LDAPEmptyUsernameTests(QABase):
    """AD ของมหาวิทยาลัยรับ bind ที่ DN ว่างเป็น anonymous bind สำเร็จทุกรหัสผ่าน
    (ยืนยันกับ server จริง) เดิมล็อกอินด้วย "@ubu.ac.th" + รหัสอะไรก็ได้ผ่าน"""

    def test_empty_username_never_reaches_ldap(self):
        from booking.ldap_auth import authenticate_ldap
        with mock.patch('booking.ldap_auth.Connection') as conn:
            self.assertIsNone(authenticate_ldap('', 'anything123'))
            self.assertIsNone(authenticate_ldap('   ', 'anything123'))
            self.assertIsNone(authenticate_ldap('6611111111', ''))
            conn.assert_not_called()

    def test_blank_local_part_principal_is_not_tried(self):
        from booking.ldap_auth import authenticate_ldap
        with mock.patch('booking.ldap_auth.Connection') as conn:
            conn.return_value.bound = False
            authenticate_ldap('abc', 'pw123456', extra_principal='@ubu.ac.th')
            tried = [c.kwargs['user'] for c in conn.call_args_list]
            self.assertNotIn('@ubu.ac.th', tried)
            self.assertTrue(all(t.replace('UBU\\', '').partition('@')[0] for t in tried), tried)

    def test_login_with_only_domain_rejected(self):
        self.client.force_authenticate(user=None)
        for name in ('@ubu.ac.th', '@', '  @ubu.ac.th'):
            with mock.patch('booking.serializers.authenticate_ldap') as ldap:
                r = self.client.post('/api/auth/login/', {'username': name, 'password': 'whatever12'},
                                     format='json')
                ldap.assert_not_called()
            self.assertEqual(r.status_code, 400, name)
        self.assertFalse(User.objects.filter(username='').exists())


# ══════════════════════════════════════════════════════════════
# สมัครสมาชิก — ค่าที่ยาว/แปลกต้องได้ 400 ไม่ใช่ 500
# ══════════════════════════════════════════════════════════════
class RegisterEdgeTests(QABase):
    def register(self, **over):
        self.client.force_authenticate(user=None)
        payload = {'email': 'qa_night@example.com', 'password': 'QaNight1234',
                   'password2': 'QaNight1234', 'student_id': '6644444444'}
        payload.update(over)
        return self.client.post('/api/auth/register/', payload, format='json')

    def test_student_id_too_long_is_400(self):
        r = self.register(student_id='6' * 25, password='Zx9!kwPq77', password2='Zx9!kwPq77')
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn('student_id', r.data)

    def test_lecturer_email_longer_than_username_column_is_400(self):
        email = ('a' * 140) + '@example.com'   # 152 ตัว > username 150
        r = self.register(email=email, want_lecturer=True, student_id='')
        self.assertEqual(r.status_code, 400, r.data)

    def test_non_ascii_digits_rejected(self):
        # "６６１１..." (เต็มความกว้าง) และเลขไทย isdigit() เป็น True — เดิมสมัครได้
        # ได้บัญชีหน้าตาเหมือนรหัสนักศึกษาของคนอื่นแต่คนละบัญชีกับที่ LDAP ใช้
        for sid in ('６６４４４４４４４４', '๖๖๔๔๔๔๔๔๔๔'):
            r = self.register(student_id=sid, password='Zx9!kwPq77', password2='Zx9!kwPq77')
            self.assertEqual(r.status_code, 400, (sid, r.data))
            self.assertIn('student_id', r.data)

    def test_profile_student_id_non_ascii_rejected(self):
        r = self.client.patch('/api/auth/profile/', {'student_id': '๖๖๑๑๑๑๑๑๑๒'}, format='json')
        self.assertEqual(r.status_code, 400, r.data)


# ══════════════════════════════════════════════════════════════
# ห้อง
# ══════════════════════════════════════════════════════════════
class RoomEdgeTests(QABase):
    def test_availability_includes_overnight_booking_from_yesterday(self):
        # จองข้ามคืน 22:00 วันจันทร์ – 02:00 วันอังคาร: ดูตารางวันอังคารต้องเห็นช่วงนี้
        mon = self.tue - timedelta(days=1)
        Booking.objects.create(user=self.user_b, room=self.room, title='ข้ามคืน', attendees=5,
                               start_time=aware(mon, 22), end_time=aware(self.tue, 2), status='approved')
        r = self.client.get(f'/api/rooms/{self.room.id}/availability/?date={self.tue.isoformat()}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['dynamic_bookings']), 1, r.data)

    def test_admin_status_query_count_does_not_grow_with_rooms(self):
        self.as_user(self.admin)
        with CaptureQueriesContext(connection) as small:
            self.client.get('/api/rooms/admin-status/')
        for i in range(20):
            Room.objects.create(building=self.building, name=f'X{i}', floor=1, capacity=10, room_type='x')
        with CaptureQueriesContext(connection) as big:
            r = self.client.get('/api/rooms/admin-status/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(big), len(small), 'admin-status ยิง query เพิ่มทีละห้อง (N+1)')

    def test_huge_capacity_is_400_not_500(self):
        self.as_user(self.admin)
        r = self.client.post('/api/rooms/', {'building': self.building.id, 'name': 'BIG', 'floor': 1,
                                             'capacity': 10 ** 12, 'room_type': 'x'}, format='json')
        self.assertEqual(r.status_code, 400, r.data)

    def test_search_huge_attendees_is_not_500(self):
        day = (timezone.localdate() + timedelta(days=3)).isoformat()
        r = self.client.post('/api/rooms/search/', {'attendees': 10 ** 20, 'date': day,
                                                    'start_time': '10:00', 'end_time': '11:00'}, format='json')
        self.assertIn(r.status_code, (200, 400), r.content[:200])
        if r.status_code == 200:
            self.assertEqual(r.data, [])


# ══════════════════════════════════════════════════════════════
# จองทั้งเทอม
# ══════════════════════════════════════════════════════════════
class TermEdgeTests(QABase):
    def payload(self, **over):
        start = timezone.localdate() + timedelta(days=1)
        data = {'room': self.room.id, 'subject_name': 'วิชาทดสอบ', 'attendees': 10, 'day_of_week': self.tue.weekday(),
                'start_time': '08:00', 'end_time': '10:00',
                'term_start': start.isoformat(), 'term_end': (start + timedelta(days=60)).isoformat()}
        data.update(over)
        return data

    def test_term_slot_shorter_than_minimum_rejected(self):
        r = self.client.post('/api/term-bookings/', self.payload(start_time='08:00', end_time='08:01'),
                             format='json')
        self.assertEqual(r.status_code, 400, r.data)

    def test_term_huge_attendees_is_400(self):
        r = self.client.post('/api/term-bookings/', self.payload(attendees=10 ** 12), format='json')
        self.assertEqual(r.status_code, 400, r.data)
