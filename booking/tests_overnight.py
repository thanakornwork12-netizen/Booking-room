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


# ══════════════════════════════════════════════════════════════
# จองพร้อมกันจริงหลายเธรดบน Postgres — ต้องได้รายการเดียว
# ══════════════════════════════════════════════════════════════
import threading  # noqa: E402

from django.db import connections  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402


class ConcurrentBookingTests(TransactionTestCase):
    def setUp(self):
        b = Building.objects.create(name='อาคารทดสอบ', code='TT')
        self.room = Room.objects.create(id=445, building=b, name='2C09', floor=1, capacity=40, room_type='ห้องเรียน')
        self.users = [User.objects.create_user(username=f'qa_race_{i}', password='QaRace1234', role='student',
                                               email=f'qa_race_{i}@example.com') for i in range(10)]

    def _race(self, payload_for, path='/api/bookings/'):
        barrier = threading.Barrier(len(self.users))
        codes = []

        def worker(user):
            try:
                c = APIClient()
                c.force_authenticate(user)
                barrier.wait()
                codes.append(c.post(path, payload_for(user), format='json').status_code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(u,)) for u in self.users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return codes

    def test_ten_users_same_slot_only_one_wins(self):
        day = timezone.localdate() + timedelta(days=5)
        start, end = aware(day, 10), aware(day, 11)
        codes = self._race(lambda u: {'room': self.room.id, 'title': 'แข่ง', 'attendees': 5,
                                      'start_time': start.isoformat(), 'end_time': end.isoformat()})
        self.assertEqual(sorted(codes).count(201), 1, codes)
        self.assertEqual(Booking.objects.filter(room=self.room, status__in=['pending', 'approved']).count(), 1)

    def test_overlapping_but_different_slots_only_one_wins(self):
        day = timezone.localdate() + timedelta(days=5)
        # แต่ละคนเลื่อนเวลาเริ่ม 5 นาที แต่ทุกช่วงทับกันหมด
        codes = self._race(lambda u: {
            'room': self.room.id, 'title': 'ทับ', 'attendees': 5,
            'start_time': (aware(day, 9) + timedelta(minutes=5 * self.users.index(u))).isoformat(),
            'end_time': (aware(day, 11)).isoformat()})
        self.assertEqual(codes.count(201), 1, codes)


class ReminderAfterRescheduleTests(QABase):
    def test_moving_start_time_resets_reminder(self):
        day = timezone.localdate() + timedelta(days=4)
        b = Booking.objects.create(user=self.bot, room=self.room, title='ประชุม', attendees=5,
                                   start_time=aware(day, 10), end_time=aware(day, 11),
                                   status='approved', reminded=True)
        r = self.client.patch(f'/api/bookings/{b.id}/', {'start_time': aware(day, 14).isoformat(),
                                                          'end_time': aware(day, 15).isoformat()}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        b.refresh_from_db()
        self.assertFalse(b.reminded)

    def test_title_only_edit_keeps_reminder_flag(self):
        day = timezone.localdate() + timedelta(days=4)
        b = Booking.objects.create(user=self.bot, room=self.room, title='ประชุม', attendees=5,
                                   start_time=aware(day, 10), end_time=aware(day, 11),
                                   status='approved', reminded=True)
        self.client.patch(f'/api/bookings/{b.id}/', {'title': 'ประชุมใหม่'}, format='json')
        b.refresh_from_db()
        self.assertTrue(b.reminded)


# ══════════════════════════════════════════════════════════════
# อีเมลทุกแบบต้อง escape ข้อความที่ผู้ใช้พิมพ์เอง
# ══════════════════════════════════════════════════════════════
from django.core import mail  # noqa: E402
from django.test import override_settings  # noqa: E402

from booking import signals  # noqa: E402
from booking.models import TermBooking  # noqa: E402

EVIL = '<script>alert(1)</script>'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailEscapingTests(QABase):
    def setUp(self):
        super().setUp()
        self.bot.first_name = EVIL
        self.bot.save()
        day = timezone.localdate() + timedelta(days=3)
        self.booking = Booking.objects.create(
            user=self.bot, room=self.room, title=EVIL, note=EVIL, reject_reason=EVIL, attendees=5,
            start_time=aware(day, 10), end_time=aware(day, 11))
        self.term = TermBooking.objects.create(
            user=self.bot, room=self.room, subject_name=EVIL, subject_code='<i>c</i>', term_name='<i>t</i>', note=EVIL,
            reject_reason=EVIL, attendees=5, day_of_week=day.weekday(), start_time=time_type(13),
            end_time=time_type(14), term_start=day, term_end=day + timedelta(days=30))
        mail.outbox.clear()

    def html_parts(self):
        out = []
        for m in mail.outbox:
            out += [c for c, mime in getattr(m, 'alternatives', []) if mime == 'text/html']
        return out

    def test_no_raw_user_html_in_any_email(self):
        calls = [
            (signals.send_welcome_email, self.bot),
            (signals.send_approval_request_email, self.booking),
            (signals.send_approval_request_email, self.term),
            (signals.send_booking_pending_email, self.booking),
            (signals.send_booking_confirmation_email, self.booking),
            (signals.send_booking_rejected_email, self.booking),
            (signals.send_booking_cancelled_email, self.booking),
            (signals.send_term_booking_pending_email, self.term),
            (signals.send_term_booking_confirmation_email, self.term),
            (signals.send_term_booking_rejected_email, self.term),
            (signals.send_term_booking_cancelled_email, self.term),
        ]
        for fn, obj in calls:
            fn(obj)
        signals.send_password_reset_email(self.bot, uidb64='x', token='y')
        html = self.html_parts()
        self.assertGreaterEqual(len(html), 10, f'ได้อีเมล HTML แค่ {len(html)} ฉบับ')
        for part in html:
            self.assertNotIn(EVIL, part)
            self.assertNotIn('<i>c</i>', part)
            self.assertNotIn('<i>t</i>', part)
