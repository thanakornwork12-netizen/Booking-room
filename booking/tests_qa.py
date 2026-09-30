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
        self.bot = User.objects.create_user(
            username='qa_test_bot', password='QaTest1234', role='student',
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
            'username': 'qa_new_user', 'first_name': 'QA', 'last_name': 'New',
            'email': 'qa_new_user@example.com', 'password': 'QaTest1234',
            'password2': 'QaTest1234', 'role': 'student', 'student_id': '6633333333',
        }
        payload.update(over)
        return self.client.post('/api/auth/register/', payload, format='json')

    def test_register_duplicate_username(self):
        self.assertEqual(self.register(username='qa_test_bot').status_code, 400)

    def test_register_email_username_colliding_after_normalisation(self):
        """qa_test_bot@ubu.ac.th ถูกตัดเหลือ qa_test_bot ซึ่งมีอยู่แล้ว — ต้องได้ 400 ไม่ใช่ 500"""
        r = self.register(username='qa_test_bot@ubu.ac.th')
        self.assertEqual(r.status_code, 400)

    def test_register_email_username_is_normalised(self):
        r = self.register(username='qa.person@ubu.ac.th')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(User.objects.filter(username='qa.person').exists())

    def test_register_student_id_username_rejected(self):
        """รหัสนักศึกษาเป็นของบัญชี LDAP — สมัครจองไว้ก่อนไม่ได้ ทั้งแบบตรงและแบบอีเมล"""
        for name in ('6699999999', '6699999999@ubu.ac.th', '６６９９９９９９９９'):
            with self.subTest(name=name):
                r = self.register(username=name)
                self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(username__contains='99999999').exists())

    def test_register_staff_role_rejected(self):
        r = self.register(role='staff')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(username='qa_new_user').exists())

    def test_register_admin_role_rejected(self):
        self.assertEqual(self.register(role='admin').status_code, 400)

    def test_register_short_password(self):
        self.assertEqual(self.register(password='abc', password2='abc').status_code, 400)

    def test_register_password_is_hashed(self):
        self.register()
        u = User.objects.get(username='qa_new_user')
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
        self.assertEqual((self.bot.role, self.bot.username), ('student', 'qa_test_bot'))

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
        r = self.client.post('/api/auth/delete-account/', {
            'confirm_username': 'qa_test_bot', 'confirm_text': 'DELETE', 'password': 'QaTest1234',
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username='qa_test_bot').exists())

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
        for status in ('pending', 'approved', 'checked_in'):
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
