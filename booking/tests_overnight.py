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


class AvatarUploadTests(QABase):
    def test_profile_ignores_avatar_upload(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = io.BytesIO()
        Image.new('RGB', (10, 10)).save(buf, 'PNG')
        img = SimpleUploadedFile('a.png', buf.getvalue(), content_type='image/png')
        r = self.client.patch('/api/auth/profile/', {'avatar': img, 'faculty': 'วิทย์'}, format='multipart')
        self.assertEqual(r.status_code, 200, r.data)
        self.bot.refresh_from_db()
        self.assertFalse(self.bot.avatar)
        self.assertEqual(self.bot.faculty, 'วิทย์')


# ══════════════════════════════════════════════════════════════
# สิทธิ์: นักศึกษาแตะของคนอื่น/ของแอดมินไม่ได้ทุกเส้นทาง
# ══════════════════════════════════════════════════════════════
from booking.models import MaintenanceBlock, Notification  # noqa: E402


class AuthorizationMatrixTests(QABase):
    def setUp(self):
        super().setUp()
        day = timezone.localdate() + timedelta(days=6)
        self.other_booking = Booking.objects.create(
            user=self.bot, room=self.room, title='ของคนอื่น', attendees=5,
            start_time=aware(day, 10), end_time=aware(day, 11))
        self.other_term = TermBooking.objects.create(
            user=self.bot, room=self.room, subject_name='ของคนอื่น', attendees=5, day_of_week=day.weekday(),
            start_time=time_type(13), end_time=time_type(14), term_start=day, term_end=day + timedelta(days=30))
        self.other_notif = Notification.objects.create(user=self.bot, type='system', title='t', message='m')
        self.block = MaintenanceBlock.objects.create(room=self.room_b, start_time=aware(day, 15),
                                                     end_time=aware(day, 16))
        self.pending_lect = User.objects.create_user(username='qa_pending_lect', password='QaLect1234',
                                                     email='qa_pending_lect@example.com', lecturer_status='pending')
        self.as_user(self.user_b)  # นักศึกษา

    def test_student_cannot_touch_others_or_admin_endpoints(self):
        b, t, n, m = self.other_booking.id, self.other_term.id, self.other_notif.id, self.block.id
        day = (timezone.localdate() + timedelta(days=6)).isoformat()
        cases = [
            ('get', f'/api/bookings/{b}/', None), ('patch', f'/api/bookings/{b}/', {'title': 'x'}),
            ('put', f'/api/bookings/{b}/', {'title': 'x'}), ('get', f'/api/bookings/{b}/logs/', None),
            ('post', f'/api/bookings/{b}/cancel/', None), ('post', f'/api/bookings/{b}/approve/', None),
            ('post', f'/api/bookings/{b}/reject/', None), ('delete', f'/api/bookings/{b}/', None),
            ('get', f'/api/term-bookings/{t}/', None), ('patch', f'/api/term-bookings/{t}/', {'note': 'x'}),
            ('delete', f'/api/term-bookings/{t}/', None), ('post', f'/api/term-bookings/{t}/approve/', None),
            ('post', f'/api/term-bookings/{t}/reject/', None),
            ('get', f'/api/notifications/{n}/', None), ('post', f'/api/notifications/{n}/read/', None),
            ('get', '/api/maintenance-blocks/', None), ('get', f'/api/maintenance-blocks/{m}/', None),
            ('post', '/api/maintenance-blocks/', {'room': self.room.id, 'start_time': day + 'T08:00:00+07:00',
                                                  'end_time': day + 'T09:00:00+07:00'}),
            ('post', f'/api/maintenance-blocks/{m}/cancel/', None), ('post', f'/api/maintenance-blocks/{m}/complete/', None),
            ('get', '/api/maintenance/slots/', None), ('get', '/api/dashboard/', None),
            ('get', '/api/export/excel/', None), ('get', '/api/rooms/admin-status/', None),
            ('get', '/api/rooms/usage-stats/', None), ('get', '/api/lecturer-requests/', None),
            ('post', f'/api/lecturer-requests/{self.pending_lect.id}/approve/', None),
            ('post', '/api/rooms/', {'building': self.building.id, 'name': 'Z', 'floor': 1, 'capacity': 5, 'room_type': 'x'}),
            ('patch', f'/api/rooms/{self.room.id}/', {'capacity': 1}), ('delete', f'/api/rooms/{self.room.id}/', None),
            ('post', '/api/buildings/', {'name': 'B', 'code': 'BB'}),
            ('patch', f'/api/buildings/{self.building.id}/', {'is_active': False}),
            ('delete', f'/api/buildings/{self.building.id}/', None),
            ('post', '/api/term-bookings/', {}),
        ]
        leaks = []
        for method, url, data in cases:
            r = getattr(self.client, method)(url, data, format='json')
            if r.status_code not in (403, 404, 405):
                leaks.append((method.upper(), url, r.status_code))
        self.assertEqual(leaks, [])
        # ไม่มีอะไรเปลี่ยนจริง
        self.other_booking.refresh_from_db(); self.other_term.refresh_from_db(); self.block.refresh_from_db()
        self.pending_lect.refresh_from_db(); self.room.refresh_from_db(); self.building.refresh_from_db()
        self.assertEqual((self.other_booking.status, self.other_booking.title), ('pending', 'ของคนอื่น'))
        self.assertEqual(self.other_term.status, 'pending')
        self.assertEqual(self.block.status, 'scheduled')
        self.assertEqual(self.pending_lect.role, 'student')
        self.assertTrue(self.room.is_active and self.building.is_active)

    def test_anonymous_gets_401_everywhere_private(self):
        self.client.force_authenticate(user=None)
        for url in ('/api/bookings/', '/api/term-bookings/', '/api/notifications/', '/api/rooms/',
                    '/api/auth/profile/', '/api/dashboard/', '/api/forecasts/', '/api/rooms/today-feed/',
                    '/api/rooms/status-feed/', f'/api/rooms/{self.room.id}/availability/?date=2030-01-01'):
            self.assertEqual(self.client.get(url).status_code, 401, url)


class TermTodayAlreadyPassedTests(QABase):
    """จองทั้งเทอมวันนี้ คาบของวันนี้ที่เลยเวลาไปแล้วต้องไม่นับเป็นคาบที่เหลือ"""

    def _post(self, start, end, term_end):
        today = timezone.localdate()
        return self.client.post('/api/term-bookings/', {
            'room': self.room.id, 'subject_name': 'วิชาวันนี้', 'attendees': 5, 'day_of_week': today.weekday(),
            'start_time': start, 'end_time': end, 'term_start': (today - timedelta(days=30)).isoformat(),
            'term_end': term_end.isoformat()}, format='json')

    def test_only_class_is_earlier_today_rejected(self):
        now = timezone.localtime()
        if now.hour < 1:
            self.skipTest('ต้องมีช่วงเวลาที่ผ่านไปแล้วของวันนี้')
        r = self._post('00:00', '00:30', timezone.localdate())
        self.assertEqual(r.status_code, 400, r.data)

    def test_mid_term_start_skips_class_already_over_today(self):
        now = timezone.localtime()
        if now.hour < 1:
            self.skipTest('ต้องมีช่วงเวลาที่ผ่านไปแล้วของวันนี้')
        r = self._post('00:00', '00:30', timezone.localdate() + timedelta(days=21))
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['term_start'], (timezone.localdate() + timedelta(days=7)).isoformat())


class SchedulerConnectionTests(QABase):
    def test_job_wrapper_runs_job_and_closes_connection(self):
        from booking.scheduler import _with_fresh_connection
        calls = []
        with mock.patch('django.db.connection.close') as close:
            wrapped = _with_fresh_connection(lambda: calls.append(1) or 'done')
            self.assertEqual(wrapped(), 'done')
        self.assertEqual(calls, [1])
        close.assert_called()
