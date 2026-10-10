"""QA รอบ 4 (ก่อนสอบ) — การแสดงรายการให้ครบ และสถานะห้องตามช่วงซ่อม
รัน: python manage.py test booking.tests_qa_round4 --noinput"""
from datetime import time as time_type, timedelta

from django.utils import timezone

from booking.maintenance import refresh_maintenance
from booking.models import Booking, MaintenanceBlock, Notification, Room, TermBooking
from booking.tests_qa import QABase, aware


class NotificationListTests(QABase):
    def test_newest_first(self):
        old = Notification.objects.create(user=self.bot, type='system', title='เก่า', message='m')
        Notification.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))
        for i in range(25):
            Notification.objects.create(user=self.bot, type='system', title=f'n{i}', message='m')
        newest = Notification.objects.create(user=self.bot, type='system', title='ล่าสุด', message='m')
        rows = self.client.get('/api/notifications/').data['results']
        self.assertEqual(rows[0]['id'], newest.id)
        self.assertNotIn(old.id, [r['id'] for r in rows])

    def test_unread_count_counts_everything(self):
        for i in range(30):
            Notification.objects.create(user=self.bot, type='system', title=f'n{i}', message='m', is_read=i < 5)
        Notification.objects.create(user=self.user_b, type='system', title='คนอื่น', message='m')
        self.assertEqual(self.client.get('/api/notifications/unread-count/').data['count'], 25)


class StatusFilterTests(QABase):
    def test_admin_can_list_only_pending(self):
        for i in range(25):
            Booking.objects.create(user=self.user_b, room=self.room, title=f'ok{i}', attendees=5,
                                   start_time=aware(self.tue, 8) + timedelta(days=7 * (i + 1)),
                                   end_time=aware(self.tue, 9) + timedelta(days=7 * (i + 1)), status='approved')
        p = Booking.objects.create(user=self.bot, room=self.room, title='รออนุมัติ', attendees=5,
                                   start_time=aware(self.tue, 10), end_time=aware(self.tue, 11))
        self.as_user(self.admin)
        rows = self.client.get('/api/bookings/?status=pending').data['results']
        self.assertEqual([r['id'] for r in rows], [p.id])

    def test_pending_terms_listed(self):
        for i in range(25):
            TermBooking.objects.create(user=self.user_b, room=self.room, subject_name=f'วิชา{i}', attendees=5,
                                       day_of_week=i % 5, start_time=time_type(8 + i % 10), end_time=time_type(9 + i % 10),
                                       term_start=self.tue, term_end=self.tue + timedelta(days=60), status='active')
        p = TermBooking.objects.create(user=self.bot, room=self.room_b, subject_name='รออนุมัติ', attendees=5,
                                       day_of_week=6, start_time=time_type(20), end_time=time_type(21),
                                       term_start=self.tue, term_end=self.tue + timedelta(days=60))
        self.as_user(self.admin)
        rows = self.client.get('/api/term-bookings/?status=pending').data['results']
        self.assertEqual([r['id'] for r in rows], [p.id])

    def test_bad_status_400(self):
        self.assertEqual(self.client.get('/api/bookings/?status=nope').status_code, 400)
        self.assertEqual(self.client.get('/api/term-bookings/?status=nope').status_code, 400)

    def test_student_filter_still_own_only(self):
        Booking.objects.create(user=self.user_b, room=self.room, title='x', attendees=5,
                               start_time=aware(self.tue, 10), end_time=aware(self.tue, 11))
        self.assertEqual(self.client.get('/api/bookings/?status=pending').data['results'], [])


class DashboardWeekTests(QABase):
    def test_last_7_days_counts_from_database(self):
        today = timezone.localdate()
        for i in range(30):  # มากกว่าหน้าแรก 20 รายการ
            Booking.objects.create(user=self.bot, room=self.room, title=f'b{i}', attendees=5,
                                   start_time=aware(today - timedelta(days=1), 8) + timedelta(minutes=i),
                                   end_time=aware(today - timedelta(days=1), 8) + timedelta(minutes=i + 1),
                                   status='approved')
        Booking.objects.create(user=self.bot, room=self.room, title='ยกเลิก', attendees=5,
                               start_time=aware(today - timedelta(days=1), 12), end_time=aware(today - timedelta(days=1), 13),
                               status='cancelled')
        self.as_user(self.admin)
        week = self.client.get('/api/dashboard/').data['last_7_days']
        self.assertEqual(len(week), 7)
        self.assertEqual(week[-1]['date'], today.isoformat())
        self.assertEqual(week[-2]['count'], 30)


class MaintenanceRefreshTests(QABase):
    def test_finished_block_closed_and_room_freed(self):
        now = timezone.now()
        mb = MaintenanceBlock.objects.create(room=self.room, start_time=now - timedelta(days=3),
                                             end_time=now - timedelta(days=2))
        Room.objects.filter(pk=self.room.pk).update(status='maintenance')
        self.assertEqual(refresh_maintenance(), 1)
        mb.refresh_from_db(); self.room.refresh_from_db()
        self.assertEqual((mb.status, self.room.status), ('completed', 'available'))

    def test_block_that_started_marks_room(self):
        now = timezone.now()
        MaintenanceBlock.objects.create(room=self.room, start_time=now - timedelta(minutes=5),
                                        end_time=now + timedelta(hours=2))
        refresh_maintenance()
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'maintenance')

    def test_disabled_room_untouched(self):
        now = timezone.now()
        MaintenanceBlock.objects.create(room=self.room, start_time=now - timedelta(days=3),
                                        end_time=now - timedelta(days=2))
        Room.objects.filter(pk=self.room.pk).update(status='disabled')
        refresh_maintenance()
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'disabled')

    def test_future_block_left_alone(self):
        now = timezone.now()
        mb = MaintenanceBlock.objects.create(room=self.room, start_time=now + timedelta(days=3),
                                             end_time=now + timedelta(days=4))
        refresh_maintenance()
        mb.refresh_from_db(); self.room.refresh_from_db()
        self.assertEqual((mb.status, self.room.status), ('scheduled', 'available'))


class PageSizeTests(QABase):
    """หน้าโปรไฟล์/หน้าแรกขอการจองของตัวเองได้มากกว่า 20 รายการ (เดิมเห็นแค่หน้าแรก)"""

    def make(self, n):
        for i in range(n):
            Booking.objects.create(user=self.bot, room=self.room, title=f'b{i}', attendees=5,
                                   start_time=aware(self.tue, 8) + timedelta(days=7 * i),
                                   end_time=aware(self.tue, 9) + timedelta(days=7 * i), status='approved')

    def test_default_is_20(self):
        self.make(25)
        self.assertEqual(len(self.client.get('/api/bookings/').data['results']), 20)

    def test_page_size_returns_more(self):
        self.make(25)
        self.assertEqual(len(self.client.get('/api/bookings/?page_size=200').data['results']), 25)

    def test_page_size_capped_at_200(self):
        from booking.pagination import StandardPagination
        self.assertEqual(StandardPagination.max_page_size, 200)
        self.assertEqual(self.client.get('/api/bookings/?page_size=100000').status_code, 200)
