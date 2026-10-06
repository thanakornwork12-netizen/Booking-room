"""QA รอบ 2 — บัคที่เจอจากการไล่ทดสอบ แต่ละเทสต์ยืนยันพฤติกรรมที่ถูกต้อง
รัน: python manage.py test booking.tests_qa_round2 --noinput"""
from datetime import time as time_type, timedelta

from django.utils import timezone

from booking.models import Booking, MaintenanceBlock, Room, TermBooking
from booking.tests_qa import QABase, aware


class QARound2Tests(QABase):
    def make_term(self, status, **over):
        f = dict(user=self.bot, room=self.room, subject_name='วิชา', attendees=20,
                 day_of_week=1, start_time=time_type(10), end_time=time_type(12),
                 term_start=self.tue, term_end=self.tue + timedelta(days=60), status=status)
        f.update(over)
        return TermBooking.objects.create(**f)

    def make_booking(self, start, end, status='approved', user=None):
        return Booking.objects.create(user=user or self.bot, room=self.room, title='x', attendees=5,
                                      start_time=start, end_time=end, status=status)

    # ── อนุมัติจองทั้งเทอม ─────────────────────────────────────
    def test_cannot_approve_cancelled_term(self):
        tb = self.make_term('cancelled')
        self.as_user(self.admin)
        r = self.client.post(f'/api/term-bookings/{tb.id}/approve/')
        self.assertEqual(r.status_code, 400)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'cancelled')

    def test_cannot_approve_rejected_term_that_ended(self):
        past = timezone.localdate() - timedelta(days=200)
        tb = self.make_term('rejected', term_start=past, term_end=past + timedelta(days=60),
                            day_of_week=past.weekday())
        self.as_user(self.admin)
        self.assertEqual(self.client.post(f'/api/term-bookings/{tb.id}/approve/').status_code, 400)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'rejected')

    def test_pending_term_still_approvable(self):
        tb = self.make_term('pending')
        self.as_user(self.admin)
        self.assertEqual(self.client.post(f'/api/term-bookings/{tb.id}/approve/').status_code, 200)
        tb.refresh_from_db()
        self.assertEqual(tb.status, 'active')

    # ── ห้องที่ซ่อนจากการค้นหา ──────────────────────────────────
    def hidden_room(self):
        return Room.objects.create(id=9001, building=self.building, name='HIDDEN', floor=1,
                                   capacity=40, room_type='ห้องเรียน')

    def test_cannot_book_hidden_room(self):
        r = self.client.post('/api/bookings/', {
            'room': self.hidden_room().id, 'title': 'x', 'attendees': 5,
            'start_time': aware(self.tue, 10).isoformat(), 'end_time': aware(self.tue, 11).isoformat(),
        }, format='json')
        self.assertEqual(r.status_code, 400, r.data)

    def test_cannot_term_book_hidden_room(self):
        r = self.client.post('/api/term-bookings/', {
            'room': self.hidden_room().id, 'subject_name': 'x', 'attendees': 5, 'day_of_week': 1,
            'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=30)),
        }, format='json')
        self.assertEqual(r.status_code, 400, r.data)

    def test_old_booking_in_hidden_room_can_still_edit_title(self):
        hidden = self.hidden_room()
        b = Booking.objects.create(user=self.bot, room=hidden, title='เดิม', attendees=5,
                                   start_time=aware(self.tue, 10), end_time=aware(self.tue, 11))
        r = self.client.patch(f'/api/bookings/{b.id}/', {'title': 'ใหม่'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)

    # ── แก้เวลาการจองที่จบแล้ว ──────────────────────────────────
    def test_cannot_extend_finished_booking(self):
        now = timezone.now()
        b = self.make_booking(now - timedelta(days=2), now - timedelta(days=2, hours=-1))
        r = self.client.patch(f'/api/bookings/{b.id}/',
                              {'end_time': (now + timedelta(days=5)).isoformat()}, format='json')
        self.assertEqual(r.status_code, 400, r.data)

    def test_can_extend_ongoing_booking(self):
        now = timezone.now()
        b = self.make_booking(now - timedelta(minutes=30), now + timedelta(minutes=30))
        r = self.client.patch(f'/api/bookings/{b.id}/',
                              {'end_time': (now + timedelta(hours=1)).isoformat()}, format='json')
        self.assertEqual(r.status_code, 200, r.data)

    # ── แดชบอร์ดนับรายการที่เช็คอินแล้ว ─────────────────────────
    def test_dashboard_still_counts_after_check_in(self):
        now = timezone.now()
        b = self.make_booking(now - timedelta(minutes=5), now + timedelta(minutes=30))
        self.as_user(self.admin)
        before = self.client.get('/api/dashboard/').data
        self.as_user(self.bot)
        self.client.post(f'/api/bookings/{b.id}/check_in/')
        b.refresh_from_db()
        self.assertEqual(b.status, 'checked_in')
        self.as_user(self.admin)
        after = self.client.get('/api/dashboard/').data
        self.assertEqual(before['today_dynamic'], after['today_dynamic'])
        self.assertEqual(before['popular_rooms'], after['popular_rooms'])

    # ── สถานะห้องหลังปิดงานซ่อม ─────────────────────────────────
    def test_completing_current_block_frees_room_despite_future_block(self):
        now = timezone.now()
        self.as_user(self.admin)
        r1 = self.client.post('/api/maintenance-blocks/', {
            'room': self.room.id, 'start_time': (now - timedelta(hours=1)).isoformat(),
            'end_time': (now + timedelta(hours=2)).isoformat()}, format='json')
        self.assertEqual(r1.status_code, 201, r1.data)
        self.assertIn('id', r1.data)
        self.client.post('/api/maintenance-blocks/', {
            'room': self.room.id, 'start_time': (now + timedelta(days=30)).isoformat(),
            'end_time': (now + timedelta(days=30, hours=3)).isoformat()}, format='json')
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'maintenance')
        self.client.post(f'/api/maintenance-blocks/{r1.data["id"]}/complete/')
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'available')

    def test_cancelling_block_keeps_disabled_room_disabled(self):
        now = timezone.now()
        mb = MaintenanceBlock.objects.create(room=self.room, start_time=now + timedelta(days=3),
                                             end_time=now + timedelta(days=3, hours=2))
        Room.objects.filter(pk=self.room.pk).update(status='disabled')
        self.as_user(self.admin)
        self.client.post(f'/api/maintenance-blocks/{mb.id}/cancel/')
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'disabled')

    # ── ยกเลิกการจองที่จบแล้ว ───────────────────────────────────
    def test_cannot_cancel_finished_booking(self):
        now = timezone.now()
        b = self.make_booking(now - timedelta(hours=3), now - timedelta(hours=1))
        self.assertEqual(self.client.post(f'/api/bookings/{b.id}/cancel/').status_code, 400)
        b.refresh_from_db()
        self.assertEqual(b.status, 'approved')

    def test_cannot_cancel_finished_booking_from_email(self):
        now = timezone.now()
        b = self.make_booking(now - timedelta(hours=3), now - timedelta(hours=1))
        self.client.force_authenticate(user=None)
        r = self.client.post(f'/api/bookings/{b.id}/cancel-email/{b.checkin_token}/')
        self.assertEqual(r.status_code, 400)

    # ── ฟีดสถานะห้อง ────────────────────────────────────────────
    def test_status_feed_sees_booking_that_started_yesterday(self):
        now = timezone.now()
        self.make_booking(now - timedelta(days=1), now + timedelta(hours=1))
        row = next(x for x in self.client.get('/api/rooms/status-feed/').data if x['id'] == self.room.id)
        self.assertEqual(row['state'], 'active', row)

    # ── input แปลกๆ ─────────────────────────────────────────────
    def test_calendar_bad_room_param_is_400(self):
        self.assertEqual(self.client.get('/api/term-bookings/calendar/?room=abc').status_code, 400)

    def test_term_search_rejects_reversed_range(self):
        r = self.client.post('/api/rooms/search/', {
            'booking_type': 'term', 'attendees': 5, 'day_of_week': 1,
            'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(self.tue + timedelta(days=60)), 'term_end': str(self.tue),
        }, format='json')
        self.assertEqual(r.status_code, 400, r.data)

    def test_today_feed_negative_limit_uses_default(self):
        for i, rid in enumerate((443, 447, 448, 487, 505, 506)):
            Room.objects.create(id=rid, building=self.building, name=f'R{i}', floor=1,
                                capacity=40, room_type='ห้องเรียน')
        r = self.client.get('/api/rooms/today-feed/?limit=-1')
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(len(r.data), 5)

    # ── ผู้อนุมัติ/ผู้ปฏิเสธดูจาก log (ไม่มีฟิลด์ approved_by แล้ว) ─────────
    def test_approver_and_rejecter_recorded_in_log(self):
        ok = self.make_booking(aware(self.tue, 10), aware(self.tue, 11), status='pending')
        no = self.make_booking(aware(self.tue, 13), aware(self.tue, 14), status='pending')
        self.as_user(self.admin)
        self.assertEqual(self.client.post(f'/api/bookings/{ok.id}/approve/').status_code, 200)
        self.assertEqual(self.client.post(f'/api/bookings/{no.id}/reject/').status_code, 200)
        self.assertTrue(ok.logs.filter(new_status='approved', changed_by=self.admin).exists())
        self.assertTrue(no.logs.filter(new_status='rejected', changed_by=self.admin).exists())
