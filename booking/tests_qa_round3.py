"""QA รอบ 3 (ทั้งระบบ) — แต่ละเทสต์ยืนยันพฤติกรรมที่ถูกต้องหลังแก้
รัน: python manage.py test booking.tests_qa_round3 --noinput"""
from datetime import datetime, time as time_type, timedelta
from unittest import mock

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import TransactionTestCase
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from booking.models import (BookingLog, Booking, Building, MaintenanceBlock, Notification, Room,
                            TermBooking, User)
from booking.overlap import recurring_slot_conflicts
from booking.tests_qa import QABase, aware

NO_LDAP = mock.patch('booking.serializers.authenticate_ldap', return_value=None)


def _bkk(d, hh, mm=0):
    return timezone.make_aware(datetime.combine(d, time_type(hh, mm)))


class QARound3Tests(QABase):
    def setUp(self):
        super().setUp()
        cache.clear()  # ตัวนับ throttle อยู่ใน cache — ไม่ให้ค้างข้ามเทสต์

    def booking(self, start, end, status='pending', user=None, room=None):
        return Booking.objects.create(user=user or self.bot, room=room or self.room, title='x',
                                      attendees=5, start_time=start, end_time=end, status=status)

    def term(self, status='active', user=None, **over):
        f = dict(user=user or self.bot, room=self.room, subject_name='วิชา', attendees=5,
                 day_of_week=1, start_time=time_type(10), end_time=time_type(12),
                 term_start=self.tue, term_end=self.tue + timedelta(days=30), status=status)
        f.update(over)
        return TermBooking.objects.create(**f)

    # ── รหัสผ่าน ───────────────────────────────────────────────
    def test_register_rejects_weak_password(self):
        self.client.force_authenticate(user=None)
        r = self.client.post('/api/auth/register/', {
            'username': 'qa_weakpw', 'first_name': 'a', 'last_name': 'b',
            'email': 'qa_weakpw@example.com', 'password': '123456', 'password2': '123456',
            'role': 'student'}, format='json')
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn('ตัวเลขล้วน', str(r.data))

    def test_register_accepts_strong_password(self):
        self.client.force_authenticate(user=None)
        r = self.client.post('/api/auth/register/', {
            'username': 'qa_strongpw', 'first_name': 'a', 'last_name': 'b',
            'email': 'qa_strongpw@example.com', 'password': 'Booking#2026', 'password2': 'Booking#2026',
            'role': 'student'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)

    def test_reset_rejects_weak_password(self):
        self.client.force_authenticate(user=None)
        r = self.client.post('/api/auth/reset-password-confirm/', {
            'uid': urlsafe_base64_encode(force_bytes(self.bot.pk)),
            'token': default_token_generator.make_token(self.bot),
            'password': '111111', 'password2': '111111'}, format='json')
        self.assertEqual(r.status_code, 400, r.data)

    def test_change_password_rejects_weak_password(self):
        r = self.client.post('/api/auth/change-password/', {
            'old_password': 'QaTest1234', 'new_password': 'password', 'new_password2': 'password'},
            format='json')
        self.assertEqual(r.status_code, 400, r.data)

    # ── จำกัดการยิงซ้ำ ─────────────────────────────────────────
    @NO_LDAP
    def test_login_throttled_per_account(self, _):
        self.client.force_authenticate(user=None)
        codes = [self.client.post('/api/auth/login/', {'username': 'qa_test_bot', 'password': f'x{i}'},
                                  format='json').status_code for i in range(12)]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[-1], 429)
        # บัญชีอื่น (คนในตึกเดียวกัน IP เดียวกัน) ยังล็อกอินได้
        other = self.client.post('/api/auth/login/', {'username': 'qa_user_b', 'password': 'QaUserB1234'},
                                 format='json')
        self.assertEqual(other.status_code, 200, other.data)

    def test_forgot_password_throttled_per_account(self):
        self.client.force_authenticate(user=None)
        codes = [self.client.post('/api/auth/forgot-password/', {'email': 'qa_test_bot@example.com'},
                                  format='json').status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        self.assertIn('รอ', str(self.client.post('/api/auth/forgot-password/',
                                                 {'email': 'QA_TEST_BOT@example.com'}, format='json').data))

    # ── LDAP ───────────────────────────────────────────────────
    def test_ldap_login_does_not_duplicate_email(self):
        cache.clear()
        with mock.patch('booking.serializers.authenticate_ldap', return_value={
                'username': '6655555555', 'full_name': 'Real Person',
                'email': 'qa_test_bot@example.com', 'department': ''}):
            self.client.force_authenticate(user=None)
            r = self.client.post('/api/auth/login/', {'username': '6655555555', 'password': 'pw'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(User.objects.filter(email__iexact='qa_test_bot@example.com').count(), 1)
        self.assertEqual(User.objects.get(username='6655555555').email, '6655555555@ubu.ac.th')

    # ── อาคาร/ห้องที่ปิด ───────────────────────────────────────
    def test_closed_building_rooms_not_searchable_or_bookable(self):
        Building.objects.filter(pk=self.building.pk).update(is_active=False)
        r = self.client.post('/api/rooms/search/', {
            'attendees': 5, 'date': str(self.tue), 'start_time': '10:00', 'end_time': '11:00'}, format='json')
        self.assertEqual(r.data, [])
        b = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'x', 'attendees': 5,
            'start_time': aware(self.tue, 10).isoformat(), 'end_time': aware(self.tue, 11).isoformat()},
            format='json')
        self.assertEqual(b.status_code, 400, b.data)

    def test_closing_room_cancels_future_reservations_and_tells_owner(self):
        b = self.booking(aware(self.tue, 10), aware(self.tue, 11), status='approved')
        tb = self.term(status='active', day_of_week=2, start_time=time_type(13), end_time=time_type(14))
        self.as_user(self.admin)
        self.assertEqual(self.client.delete(f'/api/rooms/{self.room.id}/').status_code, 204)
        b.refresh_from_db(); tb.refresh_from_db()
        self.assertEqual((b.status, tb.status), ('cancelled', 'cancelled'))
        self.assertTrue(Notification.objects.filter(user=self.bot, booking=b, type='booking_cancelled').exists())
        self.assertTrue(Notification.objects.filter(user=self.bot, term_booking=tb, type='term_cancelled').exists())
        self.assertTrue(b.logs.filter(new_status='cancelled', remark='ห้องปิดใช้งาน').exists())

    def test_disabling_room_via_update_cancels_too(self):
        b = self.booking(aware(self.tue, 10), aware(self.tue, 11), status='pending')
        self.as_user(self.admin)
        self.client.patch(f'/api/rooms/{self.room.id}/', {'status': 'disabled'}, format='json')
        b.refresh_from_db()
        self.assertEqual(b.status, 'cancelled')

    def test_closing_building_cancels_its_rooms_reservations(self):
        b = self.booking(aware(self.tue, 10), aware(self.tue, 11), status='approved')
        self.as_user(self.admin)
        self.client.delete(f'/api/buildings/{self.building.id}/')
        b.refresh_from_db()
        self.assertEqual(b.status, 'cancelled')

    def test_cannot_approve_in_disabled_room(self):
        b = self.booking(aware(self.tue, 10), aware(self.tue, 11))
        tb = self.term(status='pending')
        Room.objects.filter(pk=self.room.pk).update(status='disabled')
        self.as_user(self.admin)
        self.assertEqual(self.client.post(f'/api/bookings/{b.id}/approve/').status_code, 400)
        self.assertEqual(self.client.post(f'/api/term-bookings/{tb.id}/approve/').status_code, 400)

    def test_room_capacity_must_be_positive(self):
        self.as_user(self.admin)
        r = self.client.post('/api/rooms/', {'building': self.building.id, 'name': 'NEG', 'floor': 1,
                                             'capacity': 0, 'room_type': 'x'}, format='json')
        self.assertEqual(r.status_code, 400, r.data)

    # ── ความเป็นส่วนตัว ────────────────────────────────────────
    def test_availability_hides_other_peoples_titles(self):
        Booking.objects.create(user=self.user_b, room=self.room, title='ประชุมลับ HR', attendees=5,
                               start_time=aware(self.tue, 10), end_time=aware(self.tue, 11))
        Booking.objects.create(user=self.bot, room=self.room, title='ของฉันเอง', attendees=5,
                               start_time=aware(self.tue, 13), end_time=aware(self.tue, 14))
        data = str(self.client.get(f'/api/rooms/{self.room.id}/availability/?date={self.tue}').data)
        self.assertNotIn('ประชุมลับ HR', data)
        self.assertIn('ของฉันเอง', data)
        self.as_user(self.admin)
        self.assertIn('ประชุมลับ HR', str(self.client.get(
            f'/api/rooms/{self.room.id}/availability/?date={self.tue}').data))

    # ── จองทั้งเทอม ────────────────────────────────────────────
    def test_running_term_not_blocked_by_past_weeks(self):
        today = timezone.localdate()
        start = today - timedelta(days=28)
        dow = (today + timedelta(days=2)).weekday()
        past_day = start + timedelta(days=(dow - start.weekday()) % 7)
        self.booking(aware(past_day, 10), aware(past_day, 11), status='approved', user=self.user_b)
        r = self.client.post('/api/term-bookings/', {
            'room': self.room.id, 'subject_name': 'x', 'attendees': 5, 'day_of_week': dow,
            'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(start), 'term_end': str(today + timedelta(days=60))}, format='json')
        self.assertEqual(r.status_code, 201, r.data)

    def test_future_week_still_blocks_term(self):
        self.booking(aware(self.tue + timedelta(days=7), 10), aware(self.tue + timedelta(days=7), 11),
                     status='approved', user=self.user_b)
        r = self.client.post('/api/term-bookings/', {
            'room': self.room.id, 'subject_name': 'x', 'attendees': 5, 'day_of_week': 1,
            'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=30))}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_admin_cancelling_term_notifies_owner(self):
        tb = self.term(status='active')
        self.as_user(self.admin)
        with mock.patch('booking.signals.send_email_after_commit') as sent:
            self.client.delete(f'/api/term-bookings/{tb.id}/')
        self.assertTrue(Notification.objects.filter(user=self.bot, term_booking=tb, type='term_cancelled').exists())
        self.assertIn('send_term_booking_cancelled_email', [c.args[0].__name__ for c in sent.call_args_list])

    def test_admin_cancelling_booking_notifies_owner(self):
        b = self.booking(aware(self.tue, 10), aware(self.tue, 11), status='approved')
        self.as_user(self.admin)
        self.client.post(f'/api/bookings/{b.id}/cancel/')
        self.assertTrue(Notification.objects.filter(user=self.bot, booking=b, type='booking_cancelled').exists())

    def test_owner_cancelling_own_booking_no_extra_notification(self):
        b = self.booking(aware(self.tue, 10), aware(self.tue, 11), status='approved')
        self.client.post(f'/api/bookings/{b.id}/cancel/')
        self.assertFalse(Notification.objects.filter(user=self.bot, booking=b, type='booking_cancelled').exists())

    # ── ยกเลิกหลังเช็คอิน: เว็บกับอีเมลต้องตรงกัน ────────────────
    def test_checked_in_booking_cannot_be_cancelled_anywhere(self):
        now = timezone.now()
        b = self.booking(now - timedelta(minutes=10), now + timedelta(hours=1), status='checked_in')
        self.assertEqual(self.client.post(f'/api/bookings/{b.id}/cancel/').status_code, 400)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post(f'/api/bookings/{b.id}/cancel-email/{b.checkin_token}/').status_code, 400)
        b.refresh_from_db()
        self.assertEqual(b.status, 'checked_in')

    # ── ช่วงซ่อม ───────────────────────────────────────────────
    def test_cannot_schedule_finished_maintenance(self):
        now = timezone.now()
        self.as_user(self.admin)
        r = self.client.post('/api/maintenance-blocks/', {
            'room': self.room.id, 'start_time': (now - timedelta(days=10)).isoformat(),
            'end_time': (now - timedelta(days=9)).isoformat()}, format='json')
        self.assertEqual(r.status_code, 400, r.data)

    def test_maintenance_slots_huge_days_ok(self):
        self.as_user(self.admin)
        self.assertEqual(self.client.get('/api/maintenance/slots/?days=99999999').status_code, 200)


class OvernightOverlapTests(QABase):
    """การจองข้ามเที่ยงคืนเทียบเวลาจริงของแต่ละวัน"""

    def mon(self):
        today = timezone.localdate()
        return today + timedelta(days=(0 - today.weekday()) % 7 + 7)

    def test_overnight_does_not_clash_next_morning_class(self):
        m = self.mon()
        hit = recurring_slot_conflicts(timezone.localtime(_bkk(m, 22)), timezone.localtime(_bkk(m, 22) + timedelta(hours=4)),
                                       1, time_type(10), time_type(12), m, m + timedelta(days=30))
        self.assertFalse(hit)

    def test_ending_at_midnight_does_not_clash_next_day(self):
        m = self.mon()
        hit = recurring_slot_conflicts(timezone.localtime(_bkk(m, 20)), timezone.localtime(_bkk(m + timedelta(days=1), 0)),
                                       1, time_type(8), time_type(10), m, m + timedelta(days=30))
        self.assertFalse(hit)

    def test_overnight_clashes_early_class_it_really_covers(self):
        m = self.mon()
        hit = recurring_slot_conflicts(timezone.localtime(_bkk(m, 22)), timezone.localtime(_bkk(m, 22) + timedelta(hours=4)),
                                       1, time_type(1), time_type(3), m, m + timedelta(days=30))
        self.assertTrue(hit)

    def test_multi_day_block_covers_middle_days(self):
        m = self.mon()
        hit = recurring_slot_conflicts(timezone.localtime(_bkk(m, 9)), timezone.localtime(_bkk(m + timedelta(days=3), 9)),
                                       2, time_type(15), time_type(16), m, m + timedelta(days=30))
        self.assertTrue(hit)

    def test_overnight_booking_api_allowed_next_to_morning_class(self):
        m = self.mon()
        TermBooking.objects.create(user=self.user_b, room=self.room, subject_name='เช้า', attendees=5,
                                   day_of_week=1, start_time=time_type(10), end_time=time_type(12),
                                   term_start=m, term_end=m + timedelta(days=30), status='active')
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'ค้างคืน', 'attendees': 5,
            'start_time': _bkk(m, 22).isoformat(), 'end_time': (_bkk(m, 22) + timedelta(hours=4)).isoformat()},
            format='json')
        self.assertEqual(r.status_code, 201, r.data)


class RoomSocketTests(TransactionTestCase):
    def setUp(self):
        b = Building.objects.create(name='B', code='B')
        Room.objects.create(id=445, building=b, name='OPEN', floor=1, capacity=10, room_type='x')
        Room.objects.create(id=9001, building=b, name='HIDDEN-ROOM', floor=1, capacity=10, room_type='x')
        self.user = User.objects.create_user(username='qa_test_bot', password='QaTest1234')

    def connect(self, token=None):
        from room_booking.asgi import application

        async def run():
            path = '/ws/rooms/' + (f'?token={token}' if token else '')
            c = WebsocketCommunicator(application, path)
            ok, _ = await c.connect()
            msg = await c.receive_json_from() if ok else None
            await c.disconnect()
            return ok, msg
        return async_to_sync(run)()

    def test_anonymous_rejected(self):
        ok, _ = self.connect()
        self.assertFalse(ok)

    def test_logged_in_user_sees_only_bookable_rooms(self):
        from booking.authentication import issue_tokens
        ok, msg = self.connect(str(issue_tokens(self.user).access_token))
        self.assertTrue(ok)
        self.assertEqual([r['name'] for r in msg['rooms']], ['OPEN'])
