"""การจองทั้งเทอมต้องผ่านการอนุมัติ (pending → active / rejected) เหมือนจองรายครั้ง
รัน: python manage.py test booking.tests_term_approval --noinput"""
from datetime import time as time_type, timedelta
from unittest import mock

from django.core import mail
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from booking.models import BookingLog, Notification, TermBooking
from booking.tests_qa import QABase, aware


def _send_on_commit_inline(send_func, instance):
    transaction.on_commit(lambda: send_func(instance))


class TermApprovalTests(QABase):
    def payload(self, **over):
        p = {
            'room': self.room.id, 'subject_name': 'สถิติวิศวกรรม', 'attendees': 20,
            'day_of_week': 1, 'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=60)),
        }
        p.update(over)
        return p

    def request_term(self, **over):
        r = self.client.post('/api/term-bookings/', self.payload(**over), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return TermBooking.objects.latest('id')

    def make_term(self, status, user=None, **over):
        fields = dict(
            user=user or self.bot, room=self.room, subject_name='วิชาทดสอบ', attendees=20,
            day_of_week=1, start_time=time_type(10), end_time=time_type(12),
            term_start=self.tue, term_end=self.tue + timedelta(days=60), status=status)
        fields.update(over)
        return TermBooking.objects.create(**fields)

    # ── สร้าง ────────────────────────────────────────────────
    def test_new_term_booking_waits_for_approval(self):
        tb = self.request_term()
        self.assertEqual(tb.status, 'pending')
        self.assertIsNone(tb.approved_by)
        self.assertTrue(Notification.objects.filter(
            user=self.bot, term_booking=tb, type='term_pending').exists())

    def test_client_cannot_set_status_active(self):
        tb = self.request_term(status='active')
        self.assertEqual(tb.status, 'pending')

    def test_split_book_waits_for_approval(self):
        r = self.client.post('/api/term-bookings/split-book/', {
            'subject_name': 'วิชาสลับห้อง', 'day_of_week': 1, 'start_time': '10:00',
            'end_time': '12:00', 'attendees': 20,
            'first_room_id': self.room.id, 'first_term_start': str(self.tue),
            'first_term_end': str(self.tue + timedelta(days=27)),
            'second_room_id': self.room_b.id,
            'second_term_start': str(self.tue + timedelta(days=28)),
            'second_term_end': str(self.tue + timedelta(days=60)),
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(TermBooking.objects.filter(status='pending').count(), 2)
        self.assertEqual(r.data['first_booking']['status'], 'pending')

    # ── คำขอที่รออนุมัติกันช่วงเวลาไว้ ────────────────────────
    def test_pending_blocks_other_requests(self):
        self.request_term()
        self.as_user(self.user_b)
        term = self.client.post('/api/term-bookings/', self.payload(), format='json')
        self.assertEqual(term.status_code, 400, 'จองทั้งเทอมทับคำขอที่รออนุมัติได้')
        daily = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'ประชุม', 'attendees': 5,
            'start_time': aware(self.tue, 10).isoformat(),
            'end_time': aware(self.tue, 11).isoformat(),
        }, format='json')
        self.assertEqual(daily.status_code, 400, 'จองรายครั้งทับคำขอทั้งเทอมที่รออนุมัติได้')

    def test_pending_shows_in_availability_not_in_calendar(self):
        tb = self.make_term('pending', term_start=timezone.localdate() - timedelta(days=7))
        r = self.client.get(f'/api/rooms/{self.room.id}/availability/?date={self.tue}')
        self.assertEqual([t['status'] for t in r.data['term_bookings']], ['pending'])
        cal = self.client.get('/api/term-bookings/calendar/').data
        self.assertEqual(sum(len(v) for v in cal.values()), 0, 'คาบที่ยังไม่อนุมัติขึ้นปฏิทิน')
        tb.status = 'active'
        tb.save()
        cal = self.client.get('/api/term-bookings/calendar/').data
        self.assertEqual(sum(len(v) for v in cal.values()), 1)

    # ── อนุมัติ / ปฏิเสธ ─────────────────────────────────────
    def test_student_cannot_approve_or_reject(self):
        tb = self.request_term()
        for action in ('approve', 'reject'):
            with self.subTest(action=action):
                r = self.client.post(f'/api/term-bookings/{tb.id}/{action}/')
                self.assertEqual(r.status_code, 403)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'pending')

    def test_admin_approve(self):
        tb = self.request_term()
        self.as_user(self.admin)
        r = self.client.post(f'/api/term-bookings/{tb.id}/approve/')
        self.assertEqual(r.status_code, 200, r.data)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'active')
        self.assertEqual(tb.approved_by, self.admin)
        self.assertTrue(BookingLog.objects.filter(
            term_booking=tb, old_status='pending', new_status='active', changed_by=self.admin).exists())
        self.assertTrue(Notification.objects.filter(
            user=self.bot, term_booking=tb, type='term_approved').exists())

    def test_admin_reject_frees_the_slot(self):
        tb = self.request_term()
        self.as_user(self.admin)
        r = self.client.post(f'/api/term-bookings/{tb.id}/reject/', {'reason': 'ห้องปิดปรับปรุง'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        tb.refresh_from_db()
        self.assertEqual((tb.status, tb.reject_reason), ('rejected', 'ห้องปิดปรับปรุง'))
        self.assertTrue(BookingLog.objects.filter(
            term_booking=tb, new_status='rejected', remark='ห้องปิดปรับปรุง').exists())
        self.assertTrue(Notification.objects.filter(
            user=self.bot, term_booking=tb, type='term_rejected').exists())

        self.as_user(self.user_b)
        again = self.client.post('/api/term-bookings/', self.payload(), format='json')
        self.assertEqual(again.status_code, 201, 'ปฏิเสธแล้วช่วงเวลายังไม่ว่าง')

    def test_reject_only_pending(self):
        tb = self.make_term('active')
        self.as_user(self.admin)
        self.assertEqual(self.client.post(f'/api/term-bookings/{tb.id}/reject/').status_code, 400)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'active')

    def test_cannot_approve_request_whose_term_already_ended(self):
        today = timezone.localdate()
        tb = self.make_term('pending', term_start=today - timedelta(days=60),
                            term_end=today - timedelta(days=1))
        self.as_user(self.admin)
        self.assertEqual(self.client.post(f'/api/term-bookings/{tb.id}/approve/').status_code, 400)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'pending')

    # ── แก้ไข / ยกเลิก ───────────────────────────────────────
    def test_owner_moving_approved_class_needs_reapproval(self):
        tb = self.make_term('active', approved_by=self.admin)
        r = self.client.patch(f'/api/term-bookings/{tb.id}/',
                              {'start_time': '13:00', 'end_time': '15:00'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'pending', 'ย้ายเวลาหลังอนุมัติแล้วไม่ต้องอนุมัติใหม่')
        self.assertIsNone(tb.approved_by)

    def test_note_only_edit_keeps_approval(self):
        tb = self.make_term('active')
        self.client.patch(f'/api/term-bookings/{tb.id}/', {'note': 'เปลี่ยนผู้สอน'}, format='json')
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'active')

    def test_admin_edit_keeps_approval(self):
        tb = self.make_term('active')
        self.as_user(self.admin)
        r = self.client.patch(f'/api/term-bookings/{tb.id}/',
                              {'start_time': '13:00', 'end_time': '15:00'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'active')

    def test_cancel_pending_and_not_rejected(self):
        tb = self.request_term()
        self.assertEqual(self.client.delete(f'/api/term-bookings/{tb.id}/').status_code, 200)
        self.assertTrue(BookingLog.objects.filter(
            term_booking=tb, old_status='pending', new_status='cancelled').exists())
        rejected = self.make_term('rejected')
        self.assertEqual(self.client.delete(f'/api/term-bookings/{rejected.id}/').status_code, 400)

    def test_dashboard_counts_pending_term_requests(self):
        self.request_term()
        self.as_user(self.admin)
        self.assertEqual(self.client.get('/api/dashboard/').data['pending'], 1)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   APPROVER_EMAIL='qa_approver@example.com')
class TermApprovalEmailTests(QABase):
    def run_with_mail(self, fn):
        mail.outbox.clear()
        with mock.patch('booking.signals.send_email_after_commit', _send_on_commit_inline), \
             self.captureOnCommitCallbacks(execute=True):
            r = fn()
        return r, {to: m for m in mail.outbox for to in m.to}

    def test_emails_follow_the_approval_steps(self):
        payload = {
            'room': self.room.id, 'subject_name': '<b>สถิติ</b>', 'attendees': 20,
            'day_of_week': 1, 'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=60)),
        }
        r, sent = self.run_with_mail(lambda: self.client.post('/api/term-bookings/', payload, format='json'))
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn('รออนุมัติ', sent['qa_test_bot@example.com'].subject)
        self.assertIn('qa_approver@example.com', sent, 'ไม่ได้แจ้งผู้อนุมัติ')
        html = sent['qa_test_bot@example.com'].alternatives[0][0]
        self.assertNotIn('<b>สถิติ</b>', html, 'ชื่อวิชาไม่ถูก escape ในอีเมล')

        tb = TermBooking.objects.get()
        self.as_user(self.admin)
        _, sent = self.run_with_mail(lambda: self.client.post(f'/api/term-bookings/{tb.id}/approve/'))
        self.assertIn('ยืนยัน', sent['qa_test_bot@example.com'].subject)

    def test_reject_email_carries_reason(self):
        tb = TermBooking.objects.create(
            user=self.bot, room=self.room, subject_name='วิชาทดสอบ', attendees=20,
            day_of_week=1, start_time=time_type(10), end_time=time_type(12),
            term_start=self.tue, term_end=self.tue + timedelta(days=60), status='pending')
        self.as_user(self.admin)
        _, sent = self.run_with_mail(lambda: self.client.post(
            f'/api/term-bookings/{tb.id}/reject/', {'reason': 'ห้องปิดปรับปรุง'}, format='json'))
        m = sent['qa_test_bot@example.com']
        self.assertIn('ถูกปฏิเสธ', m.subject)
        self.assertIn('ห้องปิดปรับปรุง', m.body)


class ExpiredPendingTests(QABase):
    """คำขอที่เลยเวลาไปแล้วโดยไม่ได้อนุมัติ หายจากทุกรายการเอง"""

    def test_expired_pending_booking_disappears(self):
        from booking.models import Booking
        from booking.tests_qa import rows_of
        now = timezone.now()
        expired = Booking.objects.create(
            user=self.bot, room=self.room, title='หมดเวลา', attendees=5,
            start_time=now - timedelta(hours=3), end_time=now - timedelta(hours=1), status='pending')
        waiting = Booking.objects.create(
            user=self.bot, room=self.room, title='ยังรอ', attendees=5,
            start_time=now + timedelta(days=1), end_time=now + timedelta(days=1, hours=1), status='pending')
        past_approved = Booking.objects.create(
            user=self.bot, room=self.room, title='ใช้ไปแล้ว', attendees=5,
            start_time=now - timedelta(days=1, hours=3), end_time=now - timedelta(days=1, hours=1),
            status='approved')
        for user in (self.bot, self.admin):
            with self.subTest(user=user.username):
                self.as_user(user)
                ids = {b['id'] for b in rows_of(self.client.get('/api/bookings/').data)}
                self.assertEqual(ids, {waiting.id, past_approved.id})
        self.assertEqual(self.client.get('/api/dashboard/').data['pending'], 1)
        self.assertTrue(Booking.objects.filter(pk=expired.pk).exists(), 'แถวต้องยังอยู่ในฐานข้อมูล')

    def test_expired_pending_term_request_disappears(self):
        from booking.tests_qa import rows_of
        today = timezone.localdate()
        TermBooking.objects.create(
            user=self.bot, room=self.room, subject_name='เทอมที่จบแล้ว', attendees=20,
            day_of_week=1, start_time=time_type(10), end_time=time_type(12),
            term_start=today - timedelta(days=60), term_end=today - timedelta(days=1), status='pending')
        self.as_user(self.admin)
        self.assertEqual(rows_of(self.client.get('/api/term-bookings/').data), [])
        self.assertEqual(self.client.get('/api/dashboard/').data['pending'], 0)
