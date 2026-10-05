"""เคสขอบของการจองห้อง — เสริมจาก tests_blocktest.py (T01–T30)

รัน:  python manage.py test booking.tests_booking_edge -v 2
"""
from datetime import datetime, timedelta, time as time_type, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from booking.models import Booking, Building, MaintenanceBlock, Room, TermBooking

User = get_user_model()


def next_weekday(weekday, min_days=7):
    d = timezone.localdate() + timedelta(days=min_days)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def aware(d, hh, mm=0):
    return timezone.make_aware(datetime.combine(d, time_type(hh, mm)))


class BookingEdgeBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        cls.room = Room.objects.create(
            id=445, building=cls.building, name='2C09', floor=1, capacity=40, room_type='ห้องเรียน')
        cls.room_b = Room.objects.create(
            id=446, building=cls.building, name='2C10', floor=1, capacity=40, room_type='ห้องเรียน')

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
        self.day = next_weekday(1)  # อังคารถัดไป

    def book(self, start, end, attendees=10, room=None, title='ประชุมทดสอบ', **extra):
        payload = {
            'room': (room or self.room).id, 'title': title, 'attendees': attendees,
            'start_time': start.isoformat(), 'end_time': end.isoformat(),
        }
        payload.update(extra)
        return self.client.post('/api/bookings/', payload, format='json')

    def seed(self, start, end, status='approved', user=None, room=None):
        return Booking.objects.create(
            user=user or self.user_b, room=room or self.room, title='รายการเดิม',
            attendees=10, start_time=start, end_time=end, status=status)


# ══════════════════════════════════════════════════════════════
# 1. ข้อมูลนำเข้าไม่ถูกต้อง
# ══════════════════════════════════════════════════════════════
class InputValidationTests(BookingEdgeBase):
    def test_end_before_start(self):
        r = self.book(aware(self.day, 15), aware(self.day, 13))
        self.assertEqual(r.status_code, 400)

    def test_negative_attendees(self):
        r = self.book(aware(self.day, 13), aware(self.day, 15), attendees=-5)
        self.assertEqual(r.status_code, 400)

    def test_attendees_not_a_number(self):
        r = self.book(aware(self.day, 13), aware(self.day, 15), attendees='abc')
        self.assertEqual(r.status_code, 400)

    def test_missing_title(self):
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'attendees': 10,
            'start_time': aware(self.day, 13).isoformat(),
            'end_time': aware(self.day, 15).isoformat(),
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_title_too_long(self):
        r = self.book(aware(self.day, 13), aware(self.day, 15), title='ก' * 201)
        self.assertEqual(r.status_code, 400)

    def test_room_does_not_exist(self):
        r = self.client.post('/api/bookings/', {
            'room': 999999, 'title': 'x', 'attendees': 10,
            'start_time': aware(self.day, 13).isoformat(),
            'end_time': aware(self.day, 15).isoformat(),
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_garbage_datetime(self):
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'x', 'attendees': 10,
            'start_time': 'พรุ่งนี้บ่ายโมง', 'end_time': aware(self.day, 15).isoformat(),
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_start_one_minute_ago(self):
        start = timezone.now() - timedelta(minutes=1)
        r = self.book(start, start + timedelta(hours=1))
        self.assertEqual(r.status_code, 400)

    def test_client_cannot_set_status_approved(self):
        r = self.book(aware(self.day, 13), aware(self.day, 15), status='approved')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Booking.objects.get().status, 'pending')

    def test_client_cannot_book_as_other_user(self):
        r = self.book(aware(self.day, 13), aware(self.day, 15), user=self.user_b.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Booking.objects.get().user, self.bot)

    def test_utc_input_is_interpreted_in_bangkok_time(self):
        """ส่งเวลาเป็น UTC (Z) มา ระบบต้องตีความถูก ไม่เลื่อนวัน"""
        start_utc = aware(self.day, 13).astimezone(dt_timezone.utc)  # 06:00Z
        r = self.book(start_utc, start_utc + timedelta(hours=2))
        self.assertEqual(r.status_code, 201)
        b = Booking.objects.get()
        self.assertEqual(timezone.localtime(b.start_time).hour, 13)


# ══════════════════════════════════════════════════════════════
# 2. ห้องที่ไม่ควรจองได้
# ══════════════════════════════════════════════════════════════
class RoomAvailabilityTests(BookingEdgeBase):
    def test_cannot_book_deactivated_room(self):
        self.room_b.is_active = False
        self.room_b.status = 'disabled'
        self.room_b.save()
        r = self.book(aware(self.day, 13), aware(self.day, 15), room=self.room_b)
        self.assertEqual(r.status_code, 400, 'จองห้องที่ปิดใช้งานแล้วได้')
        self.assertFalse(Booking.objects.exists())


# ══════════════════════════════════════════════════════════════
# 3. การซ้อนทับ — ทุกรูปแบบ
# ══════════════════════════════════════════════════════════════
class OverlapTests(BookingEdgeBase):
    def setUp(self):
        super().setUp()
        self.seed(aware(self.day, 10), aware(self.day, 12))  # รายการเดิม 10–12

    def assert_rejected(self, sh, eh, sm=0, em=0):
        r = self.book(aware(self.day, sh, sm), aware(self.day, eh, em))
        self.assertEqual(r.status_code, 400,
                         f'{sh:02d}:{sm:02d}-{eh:02d}:{em:02d} ควรชน 10-12 แต่ได้ {r.status_code}')

    def assert_accepted(self, sh, eh, sm=0, em=0):
        r = self.book(aware(self.day, sh, sm), aware(self.day, eh, em))
        self.assertEqual(r.status_code, 201,
                         f'{sh:02d}:{sm:02d}-{eh:02d}:{em:02d} ไม่ควรชน แต่ได้ {r.status_code} {r.data}')

    def test_new_inside_existing(self):          self.assert_rejected(10, 11, 30, 30)
    def test_new_covers_existing(self):          self.assert_rejected(9, 13)
    def test_identical_slot(self):               self.assert_rejected(10, 12)
    def test_overlap_start(self):                self.assert_rejected(9, 11)
    def test_overlap_end(self):                  self.assert_rejected(11, 13)
    def test_one_minute_overlap(self):           self.assert_rejected(11, 12, 59, 30)
    def test_ends_exactly_at_start(self):        self.assert_accepted(8, 10)
    def test_starts_exactly_at_end(self):        self.assert_accepted(12, 13)

    def test_other_room_same_time_is_fine(self):
        r = self.book(aware(self.day, 10), aware(self.day, 12), room=self.room_b)
        self.assertEqual(r.status_code, 201)

    def test_pending_blocks_slot(self):
        self.seed(aware(self.day, 14), aware(self.day, 16), status='pending')
        r = self.book(aware(self.day, 15), aware(self.day, 17))
        self.assertEqual(r.status_code, 400)

    def test_checked_in_blocks_slot(self):
        self.seed(aware(self.day, 14), aware(self.day, 16), status='checked_in')
        r = self.book(aware(self.day, 15), aware(self.day, 17))
        self.assertEqual(r.status_code, 400)

    def test_cancelled_does_not_block(self):
        self.seed(aware(self.day, 14), aware(self.day, 16), status='cancelled')
        r = self.book(aware(self.day, 14), aware(self.day, 16))
        self.assertEqual(r.status_code, 201)

    def test_rejected_does_not_block(self):
        self.seed(aware(self.day, 14), aware(self.day, 16), status='rejected')
        r = self.book(aware(self.day, 14), aware(self.day, 16))
        self.assertEqual(r.status_code, 201)


class TermAndMaintenanceOverlapTests(BookingEdgeBase):
    def make_term(self, dow, sh, eh, status='active', start_offset=-7, end_offset=60):
        return TermBooking.objects.create(
            user=self.admin, room=self.room, subject_name='วิชาทดสอบ', attendees=30,
            day_of_week=dow, start_time=time_type(sh, 0), end_time=time_type(eh, 0),
            term_start=self.day + timedelta(days=start_offset),
            term_end=self.day + timedelta(days=end_offset), status=status)

    def test_term_other_weekday_does_not_block(self):
        self.make_term(dow=3, sh=13, eh=15)   # พฤหัส
        r = self.book(aware(self.day, 13), aware(self.day, 15))  # อังคาร
        self.assertEqual(r.status_code, 201)

    def test_term_cancelled_does_not_block(self):
        self.make_term(dow=1, sh=13, eh=15, status='cancelled')
        r = self.book(aware(self.day, 13), aware(self.day, 15))
        self.assertEqual(r.status_code, 201)

    def test_term_ended_before_date_does_not_block(self):
        self.make_term(dow=1, sh=13, eh=15, start_offset=-60, end_offset=-1)
        r = self.book(aware(self.day, 13), aware(self.day, 15))
        self.assertEqual(r.status_code, 201)

    def test_term_touching_boundary_does_not_block(self):
        self.make_term(dow=1, sh=13, eh=15)
        r = self.book(aware(self.day, 15), aware(self.day, 16))
        self.assertEqual(r.status_code, 201)

    def test_booking_across_midnight_into_term_slot(self):
        """จองข้ามเที่ยงคืน จันทร์ 22:00 → อังคาร 09:00 ทับคาบเรียนอังคาร 08:00–10:00"""
        self.make_term(dow=1, sh=8, eh=10)
        mon = self.day - timedelta(days=1)
        r = self.book(aware(mon, 22), aware(self.day, 9))
        self.assertEqual(r.status_code, 400, f'จองข้ามคืนทับคาบเรียนได้: {r.data}')

    def test_maintenance_cancelled_does_not_block(self):
        MaintenanceBlock.objects.create(
            room=self.room, start_time=aware(self.day, 8), end_time=aware(self.day, 18),
            status='cancelled', created_by=self.admin)
        r = self.book(aware(self.day, 13), aware(self.day, 15))
        self.assertEqual(r.status_code, 201)

    def test_maintenance_touching_boundary_does_not_block(self):
        MaintenanceBlock.objects.create(
            room=self.room, start_time=aware(self.day, 8), end_time=aware(self.day, 13),
            status='scheduled', created_by=self.admin)
        r = self.book(aware(self.day, 13), aware(self.day, 15))
        self.assertEqual(r.status_code, 201)


# ══════════════════════════════════════════════════════════════
# 4. แก้ไขการจองที่มีอยู่แล้ว (PATCH / PUT)
# ══════════════════════════════════════════════════════════════
class EditBookingTests(BookingEdgeBase):
    def setUp(self):
        super().setUp()
        self.mine = Booking.objects.create(
            user=self.bot, room=self.room, title='ของฉัน', attendees=10,
            start_time=aware(self.day, 8), end_time=aware(self.day, 9), status='pending')
        self.theirs = self.seed(aware(self.day, 10), aware(self.day, 12))

    def patch(self, **data):
        for k, v in list(data.items()):
            if isinstance(v, datetime):
                data[k] = v.isoformat()
        return self.client.patch(f'/api/bookings/{self.mine.id}/', data, format='json')

    def test_edit_cannot_move_into_someone_elses_slot(self):
        r = self.patch(start_time=aware(self.day, 10), end_time=aware(self.day, 12))
        self.mine.refresh_from_db()
        self.assertEqual(r.status_code, 400, 'แก้เวลาไปทับการจองของคนอื่นได้')
        self.assertEqual(timezone.localtime(self.mine.start_time).hour, 8)

    def test_edit_cannot_exceed_capacity(self):
        r = self.patch(attendees=500)
        self.assertEqual(r.status_code, 400, 'แก้จำนวนผู้เข้าร่วมเกินความจุได้')

    def test_edit_cannot_set_zero_attendees(self):
        r = self.patch(attendees=0)
        self.assertEqual(r.status_code, 400)

    def test_edit_cannot_make_end_before_start(self):
        r = self.patch(end_time=aware(self.day, 7))
        self.assertEqual(r.status_code, 400, 'แก้ให้เวลาสิ้นสุดก่อนเวลาเริ่มได้')

    def test_edit_cannot_move_into_the_past(self):
        past = timezone.localdate() - timedelta(days=2)
        r = self.patch(start_time=aware(past, 8), end_time=aware(past, 9))
        self.assertEqual(r.status_code, 400, 'แก้ไปวันที่ผ่านมาแล้วได้')

    def test_edit_cannot_move_into_maintenance(self):
        MaintenanceBlock.objects.create(
            room=self.room, start_time=aware(self.day, 14), end_time=aware(self.day, 18),
            status='scheduled', created_by=self.admin)
        r = self.patch(start_time=aware(self.day, 15), end_time=aware(self.day, 16))
        self.assertEqual(r.status_code, 400)

    def test_edit_cannot_self_approve(self):
        self.patch(status='approved')
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, 'pending')

    def test_edit_cannot_reassign_owner(self):
        self.patch(user=self.user_b.id)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.user, self.bot)

    def test_edit_title_only_is_allowed(self):
        r = self.patch(title='ชื่อใหม่')
        self.assertEqual(r.status_code, 200, r.data)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.title, 'ชื่อใหม่')

    def test_edit_to_non_overlapping_slot_is_allowed(self):
        r = self.patch(start_time=aware(self.day, 13), end_time=aware(self.day, 14))
        self.assertEqual(r.status_code, 200, r.data)

    def test_edit_own_slot_does_not_collide_with_itself(self):
        r = self.patch(start_time=aware(self.day, 8), end_time=aware(self.day, 9, 30))
        self.assertEqual(r.status_code, 200, r.data)

    def test_cannot_edit_cancelled_booking(self):
        self.mine.status = 'cancelled'
        self.mine.save(update_fields=['status'])
        r = self.patch(title='ปลุกกลับมา')
        self.assertEqual(r.status_code, 400)

    def test_edit_cannot_move_into_deactivated_room(self):
        self.room_b.is_active = False
        self.room_b.save(update_fields=['is_active'])
        r = self.patch(room=self.room_b.id)
        self.assertEqual(r.status_code, 400)

    def test_cannot_edit_someone_elses_booking(self):
        r = self.client.patch(f'/api/bookings/{self.theirs.id}/', {'title': 'แฮก'}, format='json')
        self.assertIn(r.status_code, (403, 404))
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.title, 'รายการเดิม')

    def test_delete_is_blocked(self):
        r = self.client.delete(f'/api/bookings/{self.mine.id}/')
        self.assertEqual(r.status_code, 405)
        self.assertTrue(Booking.objects.filter(pk=self.mine.pk).exists())


# ══════════════════════════════════════════════════════════════
# 5. ความเป็นส่วนตัว / สิทธิ์
# ══════════════════════════════════════════════════════════════
class PrivacyTests(BookingEdgeBase):
    def test_student_list_shows_only_own(self):
        Booking.objects.create(user=self.bot, room=self.room, title='ของฉัน', attendees=5,
                               start_time=aware(self.day, 8), end_time=aware(self.day, 9))
        self.seed(aware(self.day, 10), aware(self.day, 12))
        r = self.client.get('/api/bookings/')
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual([b['title'] for b in rows], ['ของฉัน'])

    def test_student_cannot_read_others_booking(self):
        b = self.seed(aware(self.day, 10), aware(self.day, 12))
        r = self.client.get(f'/api/bookings/{b.id}/')
        self.assertEqual(r.status_code, 404)

    def test_admin_can_cancel_others_booking(self):
        b = self.seed(aware(self.day, 10), aware(self.day, 12))
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f'/api/bookings/{b.id}/cancel/')
        self.assertEqual(r.status_code, 200)

    def test_email_link_wrong_token_rejected(self):
        b = self.seed(aware(self.day, 10), aware(self.day, 12))
        self.client.force_authenticate(user=None)
        r = self.client.post(f'/api/bookings/{b.id}/cancel-email/not-the-token/')
        b.refresh_from_db()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(b.status, 'approved')


# ══════════════════════════════════════════════════════════════
# 6. อนุมัติ / เช็คอิน ตามเวลา
# ══════════════════════════════════════════════════════════════
class TimingTests(BookingEdgeBase):
    def test_cannot_approve_finished_booking(self):
        past = timezone.now() - timedelta(hours=3)
        b = self.seed(past, past + timedelta(hours=1), status='pending')
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f'/api/bookings/{b.id}/approve/')
        self.assertEqual(r.status_code, 400)

    def test_cannot_checkin_after_end(self):
        past = timezone.now() - timedelta(hours=3)
        b = Booking.objects.create(user=self.bot, room=self.room, title='x', attendees=5,
                                   start_time=past, end_time=past + timedelta(hours=1),
                                   status='approved')
        r = self.client.post(f'/api/bookings/{b.id}/check_in/')
        self.assertEqual(r.status_code, 400)

    def test_checkin_during_booking_ok(self):
        start = timezone.now() - timedelta(minutes=10)
        b = Booking.objects.create(user=self.bot, room=self.room, title='x', attendees=5,
                                   start_time=start, end_time=start + timedelta(hours=1),
                                   status='approved')
        r = self.client.post(f'/api/bookings/{b.id}/check_in/')
        self.assertEqual(r.status_code, 200)

    def test_cannot_cancel_after_checkin_via_email(self):
        start = timezone.now() - timedelta(minutes=10)
        b = Booking.objects.create(user=self.bot, room=self.room, title='x', attendees=5,
                                   start_time=start, end_time=start + timedelta(hours=1),
                                   status='checked_in', checked_in=True)
        self.client.force_authenticate(user=None)
        r = self.client.post(f'/api/bookings/{b.id}/cancel-email/{b.checkin_token}/')
        b.refresh_from_db()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(b.status, 'checked_in')
