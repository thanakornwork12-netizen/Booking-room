"""QA ทุกส่วนของระบบที่ชุดทดสอบอื่นยังไม่ครอบ: บัญชีผู้ใช้, ค้นหาห้อง,
จองทั้งเทอม/สลับห้อง, แจ้งเตือน, พยากรณ์, อาคาร, พารามิเตอร์ผิดรูปแบบ

รัน:  python manage.py test booking.tests_qa --noinput
"""
from datetime import datetime, time as time_type, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from booking.models import (
    Booking, Building, MaintenanceBlock, Notification, Room, TermBooking,
)

User = get_user_model()


def next_weekday(weekday, min_days=7):
    d = timezone.localdate() + timedelta(days=min_days)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def aware(d, hh, mm=0):
    return timezone.make_aware(datetime.combine(d, time_type(hh, mm)))


def rows_of(data):
    return data['results'] if isinstance(data, dict) and 'results' in data else data


class QABase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        # ใช้ id จริงของห้องที่เปิดให้ค้นหา/จอง (AI_FORECAST_ROOM_IDS)
        cls.room = Room.objects.create(id=445, building=cls.building, name='2C09', floor=1,
                                       capacity=40, room_type='ห้องเรียน')
        cls.room_b = Room.objects.create(id=446, building=cls.building, name='2C10-11', floor=1,
                                         capacity=60, room_type='ห้องเรียน')

    def setUp(self):
        self.client = APIClient()
        # อาจารย์: ผู้ใช้ทั่วไปที่จองทั้งเทอมได้ด้วย (นักศึกษาจองได้แค่รายครั้ง ดู test_student_cannot_book_term)
        self.bot = User.objects.create_user(
            username='qa_test_bot', password='QaTest1234', role='lecturer',
            email='qa_test_bot@example.com', student_id='6611111111')
        self.user_b = User.objects.create_user(
            username='qa_user_b', password='QaUserB1234', role='student',
            email='qa_user_b@example.com', student_id='6622222222')
        self.admin = User.objects.create_user(
            username='qa_admin', password='QaAdmin1234', role='admin',
            email='qa_admin@example.com')
        self.client.force_authenticate(user=self.bot)
        self.tue = next_weekday(1)

    def as_user(self, user):
        self.client.force_authenticate(user=user)


# ══════════════════════════════════════════════════════════════
# บัญชีผู้ใช้
# ══════════════════════════════════════════════════════════════
class AccountQATests(QABase):
    def register(self, **over):
        self.client.force_authenticate(user=None)
        payload = {
            'email': 'qa_new_user@example.com', 'password': 'QaTest1234',
            'password2': 'QaTest1234', 'student_id': '6633333333',
        }
        payload.update(over)
        return self.client.post('/api/auth/register/', payload, format='json')

    def test_register_student_uses_student_id_as_login(self):
        r = self.register()
        self.assertEqual(r.status_code, 201, r.data)
        u = User.objects.get(student_id='6633333333')
        self.assertEqual((u.username, u.role, u.lecturer_status), ('6633333333', 'student', ''))

    def test_register_duplicate_student_id(self):
        self.assertEqual(self.register(student_id=self.bot.student_id).status_code, 400)

    def test_register_student_id_taken_as_username(self):
        """มีบัญชีที่ใช้เลขนี้เป็นชื่อเข้าสู่ระบบอยู่แล้ว (เช่นสร้างจากแอดมิน) — 400 ไม่ใช่ 500"""
        User.objects.create_user(username='6644444444', password='x')
        self.assertEqual(self.register(student_id='6644444444').status_code, 400)

    def test_register_ignores_chosen_username(self):
        r = self.register(username='qa_test_bot')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(User.objects.filter(username='qa_test_bot').count(), 1)

    def test_register_staff_role_ignored(self):
        """เลือก role เองไม่ได้แล้ว — ส่ง staff/admin มาก็ได้แค่นักศึกษา"""
        for i, role in enumerate(('staff', 'admin', 'lecturer')):
            with self.subTest(role=role):
                r = self.register(role=role, student_id=f'663333334{i}', email=f'qa_role{i}@example.com')
                self.assertEqual(r.status_code, 201, r.data)
                self.assertEqual(User.objects.get(student_id=f'663333334{i}').role, 'student')

    def test_register_lecturer_request_is_pending(self):
        r = self.register(want_lecturer=True, student_id='', email='qa.lect@example.com')
        self.assertEqual(r.status_code, 201, r.data)
        u = User.objects.get(email='qa.lect@example.com')
        self.assertEqual((u.username, u.role, u.lecturer_status, u.student_id),
                         ('qa.lect@example.com', 'student', 'pending', None))

    def test_register_short_password(self):
        self.assertEqual(self.register(password='abc', password2='abc').status_code, 400)

    def test_register_password_is_hashed(self):
        self.register()
        u = User.objects.get(username='6633333333')
        self.assertTrue(u.check_password('QaTest1234'))
        self.assertNotIn('QaTest1234', u.password)

    def test_profile_requires_login(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/auth/profile/').status_code, 401)

    def test_profile_edit_name(self):
        r = self.client.patch('/api/auth/profile/', {'first_name': 'ชื่อใหม่'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.bot.refresh_from_db()
        self.assertEqual(self.bot.first_name, 'ชื่อใหม่')

    def test_profile_cannot_change_role_or_username(self):
        self.client.patch('/api/auth/profile/', {'role': 'admin', 'username': 'hacker'}, format='json')
        self.bot.refresh_from_db()
        self.assertEqual((self.bot.role, self.bot.username), ('lecturer', 'qa_test_bot'))

    def test_profile_student_id_must_be_numeric(self):
        """กฎเดียวกับตอนสมัคร — แก้ผ่านโปรไฟล์ต้องไม่เลี่ยงได้"""
        r = self.client.patch('/api/auth/profile/', {'student_id': '65abc123'}, format='json')
        self.bot.refresh_from_db()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.bot.student_id, '6611111111')

    def test_profile_student_id_unique(self):
        r = self.client.patch('/api/auth/profile/', {'student_id': '6622222222'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_change_password_wrong_old(self):
        r = self.client.post('/api/auth/change-password/', {
            'old_password': 'nope', 'new_password': 'NewPass123', 'new_password2': 'NewPass123',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_change_password_mismatch(self):
        r = self.client.post('/api/auth/change-password/', {
            'old_password': 'QaTest1234', 'new_password': 'NewPass123', 'new_password2': 'Other123',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_change_password_happy_path(self):
        r = self.client.post('/api/auth/change-password/', {
            'old_password': 'QaTest1234', 'new_password': 'NewPass123', 'new_password2': 'NewPass123',
        }, format='json')
        self.bot.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.bot.check_password('NewPass123'))

    def test_change_password_ldap_account(self):
        self.bot.set_unusable_password()
        self.bot.save()
        r = self.client.post('/api/auth/change-password/', {
            'old_password': 'x', 'new_password': 'NewPass123', 'new_password2': 'NewPass123',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_forgot_password_same_reply_for_unknown(self):
        self.client.force_authenticate(user=None)
        known = self.client.post('/api/auth/forgot-password/', {'email': 'qa_test_bot@example.com'}, format='json')
        unknown = self.client.post('/api/auth/forgot-password/', {'email': 'nobody@example.com'}, format='json')
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data, 'คำตอบต่างกัน = เดาได้ว่าอีเมลไหนมีบัญชี')

    def test_forgot_password_empty(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post('/api/auth/forgot-password/', {}, format='json').status_code, 400)

    def test_reset_password_flow(self):
        self.client.force_authenticate(user=None)
        uid = urlsafe_base64_encode(force_bytes(self.bot.pk))
        token = default_token_generator.make_token(self.bot)
        bad = self.client.post('/api/auth/reset-password-confirm/', {
            'uid': uid, 'token': 'bad-token', 'password': 'Reset1234', 'password2': 'Reset1234',
        }, format='json')
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post('/api/auth/reset-password-confirm/', {
            'uid': uid, 'token': token, 'password': 'Reset1234', 'password2': 'Reset1234',
        }, format='json')
        self.assertEqual(ok.status_code, 200)
        reuse = self.client.post('/api/auth/reset-password-confirm/', {
            'uid': uid, 'token': token, 'password': 'Again1234', 'password2': 'Again1234',
        }, format='json')
        self.assertEqual(reuse.status_code, 400, 'ลิงก์รีเซ็ตต้องใช้ได้ครั้งเดียว')

    def test_reset_password_garbage_uid(self):
        self.client.force_authenticate(user=None)
        r = self.client.post('/api/auth/reset-password-confirm/', {
            'uid': '!!!', 'token': 'x', 'password': 'Reset1234', 'password2': 'Reset1234',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_delete_account_happy_path(self):
        past = Booking.objects.create(
            user=self.bot, room=self.room, title='ใช้ไปแล้ว', attendees=5, status='approved',
            start_time=timezone.now() - timedelta(days=3, hours=2),
            end_time=timezone.now() - timedelta(days=3),
        )
        upcoming = Booking.objects.create(
            user=self.bot, room=self.room, title='ยังไม่ถึง', attendees=5, status='approved',
            start_time=aware(self.tue, 13), end_time=aware(self.tue, 15),
        )
        r = self.client.post('/api/auth/delete-account/', {
            'confirm_username': 'qa_test_bot', 'confirm_text': 'DELETE', 'password': 'QaTest1234',
        }, format='json')
        self.assertEqual(r.status_code, 200)
        # username ถูกปล่อยให้สมัครใหม่ได้ และบัญชีเดิมใช้งานไม่ได้
        self.assertFalse(User.objects.filter(username='qa_test_bot').exists())
        self.bot.refresh_from_db()
        self.assertFalse(self.bot.is_active)
        self.assertFalse(self.bot.has_usable_password())
        self.assertEqual(self.bot.email, '')
        self.assertIsNone(self.bot.student_id)
        # ประวัติที่จบแล้วยังอยู่ (ข้อมูล AI/สถิติ) ส่วนรายการที่ยังไม่ถึงถูกยกเลิก
        past.refresh_from_db()
        upcoming.refresh_from_db()
        self.assertEqual(past.status, 'approved')
        self.assertEqual(upcoming.status, 'cancelled')

    def test_deleted_account_username_can_register_again(self):
        self.client.post('/api/auth/delete-account/', {
            'confirm_username': 'qa_test_bot', 'confirm_text': 'DELETE', 'password': 'QaTest1234',
        }, format='json')
        r = self.register(username='qa_test_bot', email='qa_test_bot@example.com',
                          student_id='6611111111')
        self.assertEqual(r.status_code, 201, r.data)

    def test_delete_account_wrong_password(self):
        r = self.client.post('/api/auth/delete-account/', {
            'confirm_username': 'qa_test_bot', 'confirm_text': 'DELETE', 'password': 'nope',
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(User.objects.filter(username='qa_test_bot').exists())

    def test_jwt_refresh(self):
        self.client.force_authenticate(user=None)
        login = self.client.post('/api/auth/login/', {'username': 'qa_test_bot', 'password': 'QaTest1234'}, format='json')
        r = self.client.post('/api/auth/refresh/', {'refresh': login.data['refresh']}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.data)


# ══════════════════════════════════════════════════════════════
# ค้นหาห้อง
# ══════════════════════════════════════════════════════════════
class SearchQATests(QABase):
    def search(self, **over):
        payload = {'attendees': 10, 'date': str(self.tue), 'start_time': '13:00', 'end_time': '15:00'}
        payload.update(over)
        return self.client.post('/api/rooms/search/', payload, format='json')

    def ids(self, r):
        return {row['id'] for row in rows_of(r.data)}

    def test_search_returns_free_rooms(self):
        r = self.search()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.ids(r), {445, 446})

    def test_search_capacity_filter(self):
        self.assertEqual(self.ids(self.search(attendees=50)), {446})

    def test_search_excludes_booked_room(self):
        for status in ('pending', 'approved'):
            with self.subTest(status=status):
                b = Booking.objects.create(user=self.user_b, room=self.room, title='x', attendees=5,
                                           start_time=aware(self.tue, 14), end_time=aware(self.tue, 16),
                                           status=status)
                self.assertNotIn(445, self.ids(self.search()), f'ห้องที่มีการจอง {status} ยังขึ้นว่า "ว่าง"')
                b.delete()

    def test_search_keeps_room_with_maintenance_on_another_day(self):
        """ตั้งปิดซ่อมไว้เดือนหน้า วันนี้ห้องต้องยังค้นเจอ"""
        self.as_user(self.admin)
        later = self.tue + timedelta(days=30)
        r = self.client.post('/api/maintenance-blocks/', {
            'room': self.room.id, 'start_time': aware(later, 8).isoformat(),
            'end_time': aware(later, 18).isoformat(), 'reason': 'ซ่อมบำรุงเชิงป้องกัน',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.as_user(self.bot)
        self.assertIn(445, self.ids(self.search()), 'ห้องหายจากการค้นหาทั้งที่ปิดซ่อมคนละวัน')

    def test_search_excludes_room_during_maintenance(self):
        MaintenanceBlock.objects.create(room=self.room, start_time=aware(self.tue, 8),
                                        end_time=aware(self.tue, 18), status='scheduled')
        self.assertNotIn(445, self.ids(self.search()))

    def test_search_invalid_input(self):
        self.assertEqual(self.search(start_time='15:00', end_time='13:00').status_code, 400)
        self.assertEqual(self.search(attendees=0).status_code, 400)
        payload = {'attendees': 10, 'start_time': '13:00', 'end_time': '15:00'}
        self.assertEqual(self.client.post('/api/rooms/search/', payload, format='json').status_code, 400)

    def test_term_search(self):
        r = self.client.post('/api/rooms/search/', {
            'booking_type': 'term', 'attendees': 10, 'day_of_week': 1,
            'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=60)),
        }, format='json')
        self.assertEqual(r.status_code, 200, r.data)

    def test_suggestions(self):
        r = self.client.get('/api/rooms/suggestions/?q=50')
        self.assertEqual(r.status_code, 200)
        r = self.client.get('/api/rooms/suggestions/?q=&limit=abc')
        self.assertEqual(r.status_code, 200)

    def test_today_feed_and_status_feed(self):
        self.assertEqual(self.client.get('/api/rooms/today-feed/').status_code, 200)
        self.assertEqual(self.client.get('/api/rooms/today-feed/?limit=abc').status_code, 200)
        self.assertEqual(self.client.get('/api/rooms/status-feed/').status_code, 200)

    def test_availability(self):
        self.assertEqual(self.client.get(f'/api/rooms/{self.room.id}/availability/').status_code, 400)
        self.assertEqual(self.client.get(f'/api/rooms/{self.room.id}/availability/?date=bad').status_code, 400)
        self.assertEqual(self.client.get(f'/api/rooms/{self.room.id}/availability/?date={self.tue}').status_code, 200)

    def test_equipment_filters_and_recommend(self):
        self.assertEqual(self.client.get('/api/rooms/equipment-filters/').status_code, 200)
        r = self.client.post('/api/rooms/dynamic-recommend/', {
            'attendees': 10, 'date': str(self.tue), 'start_time': '13:00', 'end_time': '15:00',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.data)


# ══════════════════════════════════════════════════════════════
# พารามิเตอร์ผิดรูปแบบต้องได้ 400 ไม่ใช่ 500
# ══════════════════════════════════════════════════════════════
class MalformedParamTests(QABase):
    def setUp(self):
        super().setUp()
        self.client.raise_request_exception = False

    def test_rooms_min_capacity_not_a_number(self):
        self.assertEqual(self.client.get('/api/rooms/?min_capacity=abc').status_code, 400)

    def test_forecasts_bad_date(self):
        self.assertEqual(self.client.get('/api/forecasts/?date=not-a-date').status_code, 400)

    def test_maintenance_slots_bad_numbers(self):
        self.as_user(self.admin)
        for q in ('max_demand=abc', 'min_hours=abc', 'days=abc'):
            with self.subTest(q=q):
                self.assertEqual(self.client.get(f'/api/maintenance/slots/?{q}').status_code, 400)

    def test_term_bookings_bad_filter(self):
        self.assertEqual(self.client.get('/api/term-bookings/?room=abc').status_code, 400)


# ══════════════════════════════════════════════════════════════
# จองทั้งเทอม / สลับห้อง
# ══════════════════════════════════════════════════════════════
class TermQATests(QABase):
    def make_term(self, user=None, room=None, dow=1, sh=10, eh=12, status='active'):
        return TermBooking.objects.create(
            user=user or self.bot, room=room or self.room, subject_name='วิชาทดสอบ', attendees=20,
            day_of_week=dow, start_time=time_type(sh), end_time=time_type(eh),
            term_start=self.tue - timedelta(days=7), term_end=self.tue + timedelta(days=60),
            status=status)

    def test_partial_edit_note_only(self):
        tb = self.make_term()
        r = self.client.patch(f'/api/term-bookings/{tb.id}/', {'note': 'ย้ายห้องสอบ'}, format='json')
        self.assertEqual(r.status_code, 200, getattr(r, 'data', r))

    def test_edit_cannot_move_onto_daily_booking(self):
        tb = self.make_term(sh=8, eh=9)
        Booking.objects.create(user=self.user_b, room=self.room, title='ประชุม', attendees=5,
                               start_time=aware(self.tue, 13), end_time=aware(self.tue, 15),
                               status='approved')
        r = self.client.patch(f'/api/term-bookings/{tb.id}/',
                              {'start_time': '13:00', 'end_time': '15:00'}, format='json')
        self.assertEqual(r.status_code, 400, 'แก้คาบเรียนไปทับการจองรายครั้งได้')

    def test_edit_cannot_exceed_capacity(self):
        tb = self.make_term()
        r = self.client.patch(f'/api/term-bookings/{tb.id}/', {'attendees': 500}, format='json')
        self.assertEqual(r.status_code, 400, 'แก้จำนวนคนเกินความจุได้')

    def test_cancel_own_and_twice(self):
        tb = self.make_term()
        self.assertEqual(self.client.delete(f'/api/term-bookings/{tb.id}/').status_code, 200)
        self.assertEqual(self.client.delete(f'/api/term-bookings/{tb.id}/').status_code, 400)

    def test_cannot_cancel_others(self):
        tb = self.make_term(user=self.user_b)
        self.assertIn(self.client.delete(f'/api/term-bookings/{tb.id}/').status_code, (403, 404))
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'active')

    def test_student_cannot_approve(self):
        tb = self.make_term(status='cancelled')
        self.assertIn(self.client.post(f'/api/term-bookings/{tb.id}/approve/').status_code, (403, 404))

    def test_admin_approve_cannot_revive_into_conflict(self):
        """เปิดคาบที่ยกเลิกไปแล้วกลับมา ต้องไม่ทับคาบที่ใช้งานอยู่"""
        old = self.make_term(status='cancelled')
        self.make_term(user=self.user_b)
        self.as_user(self.admin)
        r = self.client.post(f'/api/term-bookings/{old.id}/approve/')
        old.refresh_from_db()
        self.assertEqual(old.status, 'cancelled', f'คาบที่ยกเลิกถูกเปิดกลับมาทับคาบอื่น ({r.status_code})')

    def test_calendar(self):
        self.make_term()
        self.assertEqual(self.client.get('/api/term-bookings/calendar/').status_code, 200)

    def split_payload(self, **over):
        p = {
            'subject_name': 'วิชาสลับห้อง', 'day_of_week': 1, 'start_time': '10:00', 'end_time': '12:00',
            'attendees': 20,
            'first_room_id': self.room.id, 'first_term_start': str(self.tue),
            'first_term_end': str(self.tue + timedelta(days=27)),
            'second_room_id': self.room_b.id, 'second_term_start': str(self.tue + timedelta(days=28)),
            'second_term_end': str(self.tue + timedelta(days=60)),
        }
        p.update(over)
        return p

    def test_split_book_happy_path(self):
        r = self.client.post('/api/term-bookings/split-book/', self.split_payload(), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(TermBooking.objects.filter(status='pending').count(), 2)

    def test_split_book_rejects_daily_booking_conflict(self):
        Booking.objects.create(user=self.user_b, room=self.room, title='ประชุม', attendees=5,
                               start_time=aware(self.tue, 10), end_time=aware(self.tue, 12),
                               status='approved')
        r = self.client.post('/api/term-bookings/split-book/', self.split_payload(), format='json')
        self.assertEqual(r.status_code, 400, 'จองสลับห้องทับการจองรายครั้งได้')

    def test_split_book_rejects_maintenance_conflict(self):
        MaintenanceBlock.objects.create(room=self.room_b, start_time=aware(self.tue + timedelta(days=35), 8),
                                        end_time=aware(self.tue + timedelta(days=35), 18), status='scheduled')
        r = self.client.post('/api/term-bookings/split-book/', self.split_payload(), format='json')
        self.assertEqual(r.status_code, 400, 'จองสลับห้องทับช่วงปิดซ่อมได้')

    def test_split_book_rejects_over_capacity(self):
        r = self.client.post('/api/term-bookings/split-book/', self.split_payload(attendees=500), format='json')
        self.assertEqual(r.status_code, 400, 'จองสลับห้องเกินความจุได้')

    def test_split_book_rejects_invalid_day(self):
        r = self.client.post('/api/term-bookings/split-book/', self.split_payload(day_of_week=9), format='json')
        self.assertEqual(r.status_code, 400, 'day_of_week=9 ถูกบันทึกได้')

    def test_split_book_rejects_bad_attendees(self):
        self.client.raise_request_exception = False
        for bad in ('abc', 0):
            with self.subTest(attendees=bad):
                r = self.client.post('/api/term-bookings/split-book/', self.split_payload(attendees=bad), format='json')
                self.assertEqual(r.status_code, 400)

    def test_split_recommend_missing_fields(self):
        self.assertEqual(self.client.post('/api/term-bookings/split-recommend/', {}, format='json').status_code, 400)


# ══════════════════════════════════════════════════════════════
# แจ้งเตือน / อาคาร / ประวัติ
# ══════════════════════════════════════════════════════════════
class MiscQATests(QABase):
    def test_notifications_are_private(self):
        mine = Notification.objects.create(user=self.bot, type='system', title='ของฉัน', message='-')
        theirs = Notification.objects.create(user=self.user_b, type='system', title='ของคนอื่น', message='-')
        titles = [n['title'] for n in rows_of(self.client.get('/api/notifications/').data)]
        self.assertEqual(titles, ['ของฉัน'])
        self.assertEqual(self.client.post(f'/api/notifications/{theirs.id}/read/').status_code, 404)
        self.client.post('/api/notifications/read_all/')
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertTrue(mine.is_read)
        self.assertFalse(theirs.is_read)

    def test_buildings(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/buildings/').status_code, 200)
        self.as_user(self.bot)
        self.assertEqual(self.client.post('/api/buildings/', {'name': 'x', 'code': 'X1'}, format='json').status_code, 403)
        self.as_user(self.admin)
        self.assertEqual(self.client.post('/api/buildings/', {'name': 'อาคารใหม่', 'code': 'NB'}, format='json').status_code, 201)

    def test_booking_logs_visible_to_owner(self):
        b = Booking.objects.create(user=self.bot, room=self.room, title='x', attendees=5,
                                   start_time=aware(self.tue, 13), end_time=aware(self.tue, 15))
        self.as_user(self.admin)
        self.client.post(f'/api/bookings/{b.id}/approve/')
        self.as_user(self.bot)
        r = self.client.get(f'/api/bookings/{b.id}/logs/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[0]['new_status'], 'approved')

    def test_forecasts_list(self):
        self.assertEqual(self.client.get('/api/forecasts/').status_code, 200)


# ══════════════════════════════════════════════════════════════
# QA รอบ 12 ต.ค.: แดชบอร์ด, ช่วงปิดซ่อมที่ AI แนะนำ, ปิดงานซ่อม, ผลพยากรณ์ในผลค้นหา
# ══════════════════════════════════════════════════════════════
class QARound12OctTests(QABase):
    def test_dashboard_counts_only_bookable_rooms(self):
        # ห้องนอกชุด AI นับเป็นห้องทั้งหมดไม่ได้ — เดิมหารด้วยทุกแถวในตาราง
        Room.objects.create(building=self.building, name='ห้องนอกระบบ', floor=1, capacity=10)
        Booking.objects.create(user=self.bot, room=self.room, title='วันนี้', attendees=5,
                               status='approved', start_time=timezone.now(),
                               end_time=timezone.now() + timedelta(minutes=30))
        self.as_user(self.admin)
        r = self.client.get('/api/dashboard/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total_rooms'], 2)
        self.assertEqual(r.data['utilization_rate'], 50.0)  # 1 ใน 2 ห้องมีคนใช้วันนี้

    def test_maintenance_slots_skip_past_hours_today(self):
        from booking.models import DemandForecast
        today = timezone.localdate()
        DemandForecast.objects.bulk_create([
            DemandForecast(room=self.room, forecast_date=today, hour=h, predicted_demand=0.0)
            for h in range(24)
        ])
        self.as_user(self.admin)
        r = self.client.get('/api/maintenance/slots/', {'min_hours': 1, 'days': 1})
        self.assertEqual(r.status_code, 200)
        now_hour = timezone.localtime().hour
        for s in r.data['slots']:
            if s['date'] == str(today):
                self.assertGreaterEqual(s['start_hour'], now_hour)

    def _block(self, **over):
        data = dict(room=self.room, reason='ซ่อมแอร์', created_by=self.admin, status='scheduled',
                    start_time=timezone.now() - timedelta(hours=1),
                    end_time=timezone.now() + timedelta(hours=1))
        data.update(over)
        return MaintenanceBlock.objects.create(**data)

    def test_closed_maintenance_cannot_be_closed_again(self):
        block = self._block(status='cancelled')
        self.as_user(self.admin)
        r = self.client.post(f'/api/maintenance-blocks/{block.id}/complete/')
        self.assertEqual(r.status_code, 400)
        block.refresh_from_db()
        self.assertEqual(block.status, 'cancelled')
        block.status = 'completed'
        block.save()
        r = self.client.post(f'/api/maintenance-blocks/{block.id}/cancel/')
        self.assertEqual(r.status_code, 400)
        block.refresh_from_db()
        self.assertEqual(block.status, 'completed')

    def test_future_maintenance_cannot_be_completed(self):
        block = self._block(start_time=aware(self.tue, 9), end_time=aware(self.tue, 12))
        self.as_user(self.admin)
        r = self.client.post(f'/api/maintenance-blocks/{block.id}/complete/')
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f'/api/maintenance-blocks/{block.id}/cancel/')
        self.assertEqual(r.status_code, 200)

    def test_search_uses_forecast_of_requested_slot_only(self):
        from booking.models import DemandForecast
        DemandForecast.objects.create(room=self.room, forecast_date=self.tue, hour=13,
                                      predicted_demand=0.9, demand_level='urgent')
        # ผลของวันอื่นต้องไม่ปนเข้ามา
        DemandForecast.objects.create(room=self.room, forecast_date=self.tue - timedelta(days=7),
                                      hour=13, predicted_demand=0.0)
        r = self.client.post('/api/rooms/search/', {
            'attendees': 5, 'date': str(self.tue), 'start_time': '13:00', 'end_time': '14:00',
        }, format='json')
        self.assertEqual(r.status_code, 200)
        room = next(x for x in rows_of(r.data) if x['id'] == self.room.id)
        self.assertTrue(room['forecast']['has_forecast'])
        self.assertEqual(room['forecast']['demand_level'], 'urgent')

    def test_room_list_is_ordered(self):
        r = self.client.get('/api/rooms/')
        ids = [x['id'] for x in rows_of(r.data)]
        self.assertEqual(ids, sorted(ids))


# ══════════════════════════════════════════════════════════════
# QA รอบจุดที่ไม่เคยทดสอบ (12 ต.ค.)
# ══════════════════════════════════════════════════════════════
class QAOverlookedTests(QABase):
    def book(self, **over):
        p = {'room': self.room.id, 'title': 'probe', 'attendees': 5,
             'start_time': aware(self.tue, 13).isoformat(), 'end_time': aware(self.tue, 14).isoformat()}
        p.update(over)
        return self.client.post('/api/bookings/', p, format='json')

    def test_deleted_prefix_username_reserved_and_delete_never_collides(self):
        self.client.force_authenticate(user=None)
        r = self.client.post('/api/auth/register/', {
            'email': f'deleted_{self.user_b.pk}@example.com', 'want_lecturer': True,
            'password': 'QaTest1234', 'password2': 'QaTest1234'}, format='json')
        self.assertEqual(r.status_code, 400)
        # แม้มี username แบบนั้นอยู่แล้ว (เช่นสร้างจากแอดมิน) การลบบัญชีต้องไม่พัง
        User.objects.create_user(username=f'deleted_{self.user_b.pk}', password='x')
        self.as_user(self.user_b)
        r = self.client.post('/api/auth/delete-account/', {
            'confirm_username': 'qa_user_b', 'confirm_text': 'DELETE', 'password': 'QaUserB1234'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_started_booking_time_cannot_be_edited(self):
        now = timezone.now()
        b = Booking.objects.create(user=self.bot, room=self.room_b, title='inprog', attendees=1,
                                   status='approved', start_time=now - timedelta(minutes=10),
                                   end_time=now + timedelta(minutes=50))
        r = self.client.patch(f'/api/bookings/{b.id}/', {'end_time': (now + timedelta(hours=2)).isoformat()},
                              format='json')
        self.assertEqual(r.status_code, 400)
        b.refresh_from_db()
        self.assertEqual(b.status, 'approved')
        # แก้หัวข้ออย่างเดียวยังได้
        r = self.client.patch(f'/api/bookings/{b.id}/', {'title': 'เปลี่ยนชื่อ'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_note_length_limited(self):
        r = self.book(note='x' * 1001)
        self.assertEqual(r.status_code, 400)
        self.assertIn('note', r.data)

    def test_seconds_rounded_and_minimum_duration(self):
        s = aware(self.tue, 10).replace(second=30)
        r = self.book(start_time=s.isoformat(), end_time=(s + timedelta(seconds=15)).isoformat())
        self.assertEqual(r.status_code, 400)
        r = self.book(start_time=aware(self.tue, 10, 0).replace(second=40).isoformat(),
                      end_time=aware(self.tue, 11, 0).replace(second=10).isoformat())
        self.assertEqual(r.status_code, 201, r.data)
        b = Booking.objects.get(title='probe')
        self.assertEqual((b.start_time.second, b.end_time.second), (0, 0))

    def test_end_time_within_advance_limit(self):
        from django.conf import settings
        far = timezone.localdate() + timedelta(days=settings.MAX_ADVANCE_BOOKING_DAYS)
        r = self.book(start_time=aware(far, 10).isoformat(),
                      end_time=(aware(far, 10) + timedelta(days=5)).isoformat())
        self.assertEqual(r.status_code, 400)
        r = self.book(start_time=aware(far, 10).isoformat(), end_time=aware(far, 12).isoformat())
        self.assertEqual(r.status_code, 201, r.data)

    def test_term_must_have_a_future_slot(self):
        today = timezone.localdate()
        past_day = today - timedelta(days=2)
        r = self.client.post('/api/term-bookings/', {
            'room': self.room.id, 'subject_name': 'x', 'attendees': 5,
            'day_of_week': past_day.weekday(), 'start_time': '08:00', 'end_time': '09:00',
            'term_start': str(past_day), 'term_end': str(today + timedelta(days=3)), 'term_name': 'x'},
            format='json')
        self.assertEqual(r.status_code, 400)

    def test_capacity_cannot_drop_below_upcoming_booking(self):
        Booking.objects.create(user=self.bot, room=self.room, title='big', attendees=30, status='approved',
                               start_time=aware(self.tue, 9), end_time=aware(self.tue, 10))
        self.as_user(self.admin)
        r = self.client.patch(f'/api/rooms/{self.room.id}/', {'capacity': 10}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(f'/api/rooms/{self.room.id}/', {'capacity': 30}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_reject_reason_is_capped(self):
        b = Booking.objects.create(user=self.bot, room=self.room, title='p', attendees=1, status='pending',
                                   start_time=aware(self.tue, 9), end_time=aware(self.tue, 10))
        self.as_user(self.admin)
        self.client.post(f'/api/bookings/{b.id}/reject/', {'reason': 'x' * 5000}, format='json')
        b.refresh_from_db()
        self.assertEqual(len(b.reject_reason), 1000)

    def test_late_approved_booking_still_gets_reminder(self):
        from django.core import mail
        from booking.scheduler import send_booking_reminders
        start = timezone.now() + timedelta(minutes=5)
        b = Booking.objects.create(user=self.bot, room=self.room, title='late', attendees=1, status='approved',
                                   start_time=start, end_time=start + timedelta(hours=1))
        send_booking_reminders()
        b.refresh_from_db()
        self.assertTrue(b.reminded)
        self.assertTrue(any('late' in (m.body + str(m.alternatives)) or m.to == [self.bot.email]
                            for m in mail.outbox))
        # เหลือ 5 นาที หัวอีเมลต้องบอก 5 นาที ไม่ใช่ 15 นาทีตายตัว
        subject = next(m.subject for m in mail.outbox if m.to == [self.bot.email])
        self.assertIn('อีก 5 นาที', subject)


# ══════════════════════════════════════════════════════════════
# QA ไล่กดหน้าเว็บจริง (12 ต.ค.)
# ══════════════════════════════════════════════════════════════
class QAEndToEndFindingsTests(QABase):
    def test_mid_term_booking_starts_at_next_class(self):
        today = timezone.localdate()
        term_start = today - timedelta(days=60)
        dow = today.weekday()
        r = self.client.post('/api/term-bookings/', {
            'room': self.room.id, 'subject_name': 'กลางเทอม', 'attendees': 5, 'day_of_week': dow,
            'start_time': '23:00', 'end_time': '23:30',
            'term_start': str(term_start), 'term_end': str(today + timedelta(days=30)), 'term_name': 'x'},
            format='json')
        self.assertEqual(r.status_code, 201, r.data)
        tb = TermBooking.objects.get(subject_name='กลางเทอม')
        self.assertGreaterEqual(tb.term_start, today)
        self.assertEqual(tb.term_start.weekday(), dow)

    def test_split_recommend_halves_start_from_today(self):
        today = timezone.localdate()
        r = self.client.post('/api/term-bookings/split-recommend/', {
            'attendees': 5, 'day_of_week': self.tue.weekday(), 'start_time': '13:00', 'end_time': '14:00',
            'term_start': str(today - timedelta(days=120)), 'term_end': str(today + timedelta(days=60)),
        }, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        text = str(r.data)
        # ไม่มีช่วงไหนในแผนที่เริ่มก่อนวันนี้
        self.assertNotIn(str(today - timedelta(days=120)), text)

    def test_room_status_socket_hides_unbookable_rooms(self):
        import asyncio
        from booking.consumers import RoomStatusConsumer
        sent = []

        async def fake_send(text_data=None, **kw):
            sent.append(text_data)

        def event(room_id):
            return {'booking_id': 1, 'room_id': room_id, 'room_name': 'x', 'status': 'approved',
                    'start_time': '', 'end_time': ''}

        c = RoomStatusConsumer()
        c.send = fake_send
        c.user = self.bot
        asyncio.run(c.booking_update(event(99999)))   # ห้องนอกชุดที่เปิดจอง
        asyncio.run(c.booking_update(event(self.room.id)))
        self.assertEqual(len(sent), 1)
        c.user = self.admin
        asyncio.run(c.booking_update(event(99999)))
        self.assertEqual(len(sent), 2)


# ══════════════════════════════════════════════════════════════
# สิทธิ์ตาม role และการล็อกอิน (12 ต.ค.)
# ══════════════════════════════════════════════════════════════
class RoleMatrixTests(QABase):
    """นักศึกษา/อาจารย์ = ผู้ใช้ทั่วไป, เจ้าหน้าที่/ผู้ดูแล = ฝั่งผู้ดูแล — ตรงกับ
    ตารางสิทธิ์ในหน้าวิธีใช้งาน (GuidePage)"""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        self.lect = User.objects.create_user(username='qa_lect', password='QaLect1234', role='lecturer',
                                             email='lect@example.com')
        self.staff = User.objects.create_user(username='qa_staff', password='QaStaff1234', role='staff',
                                              email='staff@example.com')
        self.other = Booking.objects.create(user=self.user_b, room=self.room, title='ของคนอื่น', attendees=1,
                                            status='pending', start_time=aware(self.tue, 9),
                                            end_time=aware(self.tue, 10))
        self.lect_booking = Booking.objects.create(user=self.lect, room=self.room_b, title='ของอาจารย์',
                                                   attendees=1, status='pending', start_time=aware(self.tue, 9),
                                                   end_time=aware(self.tue, 10))

    ADMIN_GETS = ['/api/dashboard/', '/api/export/excel/?sheets=rooms', '/api/rooms/usage-stats/',
                  '/api/rooms/admin-status/', '/api/maintenance/slots/', '/api/maintenance-blocks/']

    def test_general_users_blocked_from_admin_endpoints(self):
        for user in (self.user_b, self.lect):   # นักศึกษา, อาจารย์
            self.as_user(user)
            for url in self.ADMIN_GETS:
                self.assertEqual(self.client.get(url).status_code, 403, (user.role, url))
            theirs = self.other if user != self.user_b else self.lect_booking
            self.assertEqual(self.client.post(f'/api/bookings/{theirs.id}/approve/').status_code, 403)
            self.assertEqual(self.client.get(f'/api/bookings/{theirs.id}/').status_code, 404)
            # สิทธิ์เช็คก่อนตรวจข้อมูล: ส่งข้อมูลไม่ครบก็ได้ 403 ไม่ใช่ 400
            self.assertEqual(self.client.post('/api/rooms/', {}, format='json').status_code, 403)
            self.assertEqual(self.client.post('/api/buildings/', {}, format='json').status_code, 403)
            rows = rows_of(self.client.get('/api/bookings/').data)
            if user != self.user_b:   # self.other เป็นของ user_b เอง
                self.assertFalse(any(b['id'] == self.other.id for b in rows))

    def test_staff_has_admin_rights(self):
        for user in (self.staff, self.admin):
            self.as_user(user)
            for url in self.ADMIN_GETS:
                self.assertEqual(self.client.get(url).status_code, 200, (user.role, url))
            rows = rows_of(self.client.get('/api/bookings/').data)
            self.assertTrue(any(b['id'] == self.other.id for b in rows))
        self.as_user(self.staff)
        self.assertEqual(self.client.post(f'/api/bookings/{self.other.id}/approve/').status_code, 200)

    def test_login_username_is_case_insensitive(self):
        self.client.force_authenticate(user=None)
        r = self.client.post('/api/auth/login/', {'username': 'QA_LECT', 'password': 'QaLect1234'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['user']['role'], 'lecturer')

    def test_student_cannot_book_term(self):
        """นักศึกษาจองได้เฉพาะรายครั้ง — ทุกช่องทางของการจองทั้งเทอมได้ 403"""
        term = {'room': self.room.id, 'subject_name': 'x', 'attendees': 5, 'day_of_week': self.tue.weekday(),
                'start_time': '08:00', 'end_time': '09:00', 'term_start': str(self.tue),
                'term_end': str(self.tue + timedelta(days=30)), 'term_name': 'x'}
        split = {'subject_name': 'x', 'attendees': 5, 'day_of_week': self.tue.weekday(),
                 'start_time': '08:00', 'end_time': '09:00',
                 'first_room_id': self.room.id, 'first_term_start': str(self.tue),
                 'first_term_end': str(self.tue + timedelta(days=14)),
                 'second_room_id': self.room_b.id, 'second_term_start': str(self.tue + timedelta(days=15)),
                 'second_term_end': str(self.tue + timedelta(days=30))}
        legacy = TermBooking.objects.create(
            user=self.user_b, room=self.room_b, subject_name='เดิม', attendees=1, day_of_week=self.tue.weekday(),
            start_time=aware(self.tue, 10).time(), end_time=aware(self.tue, 11).time(),
            term_start=self.tue, term_end=self.tue + timedelta(days=30), status='pending')
        self.as_user(self.user_b)
        self.assertEqual(self.client.post('/api/term-bookings/', term, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/term-bookings/split-book/', split, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/term-bookings/split-recommend/', {
            'attendees': 5, 'day_of_week': 1, 'start_time': '08:00', 'end_time': '09:00',
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=30))}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/rooms/search/', {
            'attendees': 5, 'booking_type': 'term', 'day_of_week': 1, 'start_time': '08:00', 'end_time': '09:00',
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=30))}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/term-bookings/{legacy.id}/', {'subject_name': 'y'},
                                           format='json').status_code, 403)
        self.assertFalse(TermBooking.objects.filter(subject_name='x').exists())
        # รายการเดิมของตัวเองยังดูและยกเลิกได้
        self.assertEqual(self.client.get(f'/api/term-bookings/{legacy.id}/').status_code, 200)
        self.assertEqual(self.client.delete(f'/api/term-bookings/{legacy.id}/').status_code, 200)
        # รายวันยังจองได้ตามปกติ
        r = self.client.post('/api/bookings/', {'room': self.room.id, 'title': 'ok', 'attendees': 5,
                             'start_time': aware(self.tue, 13).isoformat(),
                             'end_time': aware(self.tue, 14).isoformat()}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        # อาจารย์จองทั้งเทอมได้
        self.as_user(self.lect)
        self.assertEqual(self.client.post('/api/term-bookings/', term, format='json').status_code, 201)
