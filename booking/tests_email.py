"""อีเมลที่ระบบส่ง — Django test runner ใช้ locmem backend เก็บอีเมลไว้ใน
mail.outbox แทนการส่งจริง"""
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from booking.models import Booking, Building, Room
from booking.scheduler import send_checkin_reminders

User = get_user_model()


def _send_on_commit_inline(send_func, instance):
    """แทน send_email_after_commit ในเทสต์ — ยังส่งหลัง commit เหมือนเดิม
    แต่ส่งในเธรดเดียวกัน เทสต์จึงเห็นอีเมลใน mail.outbox ทันที"""
    transaction.on_commit(lambda: send_func(instance))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        cls.room = Room.objects.create(
            id=445, building=cls.building, name='2C09', floor=1, capacity=40, room_type='ห้องเรียน')
        cls.user = User.objects.create_user(
            username='qa_test_bot', password='QaTest1234', role='student',
            email='qa_test_bot@example.com')

    def test_checkin_reminder_sent_once(self):
        start = timezone.now() + timedelta(minutes=15)
        b = Booking.objects.create(user=self.user, room=self.room, title='ประชุม', attendees=5,
                                   start_time=start, end_time=start + timedelta(hours=1),
                                   status='approved')
        send_checkin_reminders()
        send_checkin_reminders()  # รอบที่สองต้องไม่ส่งซ้ำ

        b.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['qa_test_bot@example.com'])
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertIn(str(b.checkin_token), mail.outbox[0].body)
        self.assertTrue(b.reminded)

    def test_no_reminder_outside_window(self):
        start = timezone.now() + timedelta(hours=2)
        Booking.objects.create(user=self.user, room=self.room, title='ประชุม', attendees=5,
                               start_time=start, end_time=start + timedelta(hours=1),
                               status='approved')
        send_checkin_reminders()
        self.assertEqual(len(mail.outbox), 0)

    def test_booking_request_sends_email_from_default_sender(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        start = timezone.now() + timedelta(days=7)
        with mock.patch('booking.signals.send_email_after_commit', _send_on_commit_inline), \
             self.captureOnCommitCallbacks(execute=True):
            r = client.post('/api/bookings/', {
                'room': self.room.id, 'title': 'ประชุมกลุ่ม', 'attendees': 10,
                'start_time': start.isoformat(),
                'end_time': (start + timedelta(hours=2)).isoformat(),
            }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn('qa_test_bot@example.com', [to for m in mail.outbox for to in m.to])
        for m in mail.outbox:
            self.assertEqual(m.from_email, settings.DEFAULT_FROM_EMAIL)


class SchedulerStartTests(TestCase):
    """start() ต้องเริ่มงานเมื่อรันเป็นเซิร์ฟเวอร์ รวมถึง daphne ที่ใช้บน production"""

    def run_start(self, argv):
        from booking import scheduler
        with mock.patch.object(scheduler.sys, 'argv', argv), \
             mock.patch.dict(scheduler.os.environ, {'DISABLE_DJANGO_SCHEDULER': '', 'RUN_MAIN': ''}), \
             mock.patch.object(scheduler, 'BackgroundScheduler') as fake:
            scheduler.start()
        return fake.return_value.add_job.called

    def test_starts_under_daphne(self):
        self.assertTrue(self.run_start(['daphne', '-p', '8000', 'room_booking.asgi:application']))

    def test_starts_under_runserver(self):
        self.assertTrue(self.run_start(['manage.py', 'runserver']))

    def test_skips_management_commands(self):
        self.assertFalse(self.run_start(['manage.py', 'migrate']))
