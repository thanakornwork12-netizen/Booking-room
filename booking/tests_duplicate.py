"""การจองซ้ำแบบเดียวกันทุกอย่าง — ครั้งที่สองต้องไม่ถูกสร้าง

ครอบทั้งกดซ้ำทีละครั้ง, กดสองครั้งพร้อมกันจริง (สอง request แข่งกัน),
จองทั้งเทอมซ้ำ, จองสลับห้องซ้ำ และการจองซ้ำหลังรายการแรกถูกยกเลิก/ปฏิเสธ
"""
import threading
from datetime import datetime, time as time_type, timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from booking.models import Booking, Building, Room, TermBooking

User = get_user_model()


def next_weekday(weekday, min_days=7):
    d = timezone.localdate() + timedelta(days=min_days)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


class DuplicateBase:
    def make_fixtures(self):
        self.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        self.room = Room.objects.create(id=445, building=self.building, name='2C09', floor=1,
                                        capacity=40, room_type='ห้องเรียน')
        self.room_b = Room.objects.create(id=446, building=self.building, name='2C10-11', floor=1,
                                          capacity=60, room_type='ห้องเรียน')
        self.bot = User.objects.create_user(username='qa_test_bot', password='QaTest1234',
                                            role='student', email='qa_test_bot@example.com')
        self.admin = User.objects.create_user(username='qa_admin', password='QaAdmin1234',
                                              role='admin', email='qa_admin@example.com')
        self.tue = next_weekday(1)

    def booking_payload(self):
        # รูปแบบเดียวกับที่หน้าเว็บส่ง (เวลาไม่มี timezone ระบบตีความเป็นเวลาไทย)
        return {
            'room': self.room.id, 'title': 'ประชุมกลุ่ม', 'attendees': 10,
            'start_time': f'{self.tue}T13:00:00', 'end_time': f'{self.tue}T15:00:00',
        }

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c


class SequentialDuplicateTests(DuplicateBase, TestCase):
    def setUp(self):
        self.make_fixtures()
        self.client = self.client_for(self.bot)

    def test_same_booking_twice_is_rejected(self):
        first = self.client.post('/api/bookings/', self.booking_payload(), format='json')
        second = self.client.post('/api/bookings/', self.booking_payload(), format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 400)
        self.assertIn('ห้องนี้ถูกจองในช่วงเวลาดังกล่าวแล้ว', str(second.data))
        self.assertEqual(Booking.objects.count(), 1)

    def test_duplicate_rejected_at_every_active_status(self):
        first = self.client.post('/api/bookings/', self.booking_payload(), format='json')
        b = Booking.objects.get(pk=first.data['id']) if 'id' in first.data else Booking.objects.get()
        for status in ('pending', 'approved', 'checked_in'):
            with self.subTest(status=status):
                Booking.objects.filter(pk=b.pk).update(status=status)
                r = self.client.post('/api/bookings/', self.booking_payload(), format='json')
                self.assertEqual(r.status_code, 400)
        self.assertEqual(Booking.objects.count(), 1)

    def test_rebook_allowed_after_first_is_cancelled_or_rejected(self):
        for status in ('cancelled', 'rejected'):
            with self.subTest(status=status):
                Booking.objects.all().delete()
                self.client.post('/api/bookings/', self.booking_payload(), format='json')
                Booking.objects.update(status=status)
                r = self.client.post('/api/bookings/', self.booking_payload(), format='json')
                self.assertEqual(r.status_code, 201, r.data)

    def test_my_bookings_list_shows_it_once(self):
        self.client.post('/api/bookings/', self.booking_payload(), format='json')
        self.client.post('/api/bookings/', self.booking_payload(), format='json')
        rows = self.client.get('/api/bookings/').data
        rows = rows['results'] if isinstance(rows, dict) else rows
        self.assertEqual(len(rows), 1)

    def test_same_term_booking_twice_is_rejected(self):
        payload = {
            'room': self.room.id, 'subject_name': 'สถิติวิศวกรรม', 'attendees': 20,
            'day_of_week': 1, 'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=60)),
        }
        first = self.client.post('/api/term-bookings/', payload, format='json')
        second = self.client.post('/api/term-bookings/', payload, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(TermBooking.objects.filter(status='active').count(), 1)

    def test_same_split_booking_twice_is_rejected(self):
        payload = {
            'subject_name': 'วิชาสลับห้อง', 'day_of_week': 1, 'start_time': '10:00',
            'end_time': '12:00', 'attendees': 20,
            'first_room_id': self.room.id, 'first_term_start': str(self.tue),
            'first_term_end': str(self.tue + timedelta(days=27)),
            'second_room_id': self.room_b.id,
            'second_term_start': str(self.tue + timedelta(days=28)),
            'second_term_end': str(self.tue + timedelta(days=60)),
        }
        first = self.client.post('/api/term-bookings/split-book/', payload, format='json')
        second = self.client.post('/api/term-bookings/split-book/', payload, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(TermBooking.objects.filter(status='active').count(), 2)

    def test_two_users_same_slot(self):
        other = User.objects.create_user(username='qa_user_b', password='x', role='student')
        self.client.post('/api/bookings/', self.booking_payload(), format='json')
        r = self.client_for(other).post('/api/bookings/', self.booking_payload(), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Booking.objects.count(), 1)

    def test_search_hides_room_after_booking(self):
        self.client.post('/api/bookings/', self.booking_payload(), format='json')
        r = self.client.post('/api/rooms/search/', {
            'attendees': 10, 'date': str(self.tue), 'start_time': '13:00', 'end_time': '15:00',
        }, format='json')
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertNotIn(self.room.id, {row['id'] for row in rows})


class ConcurrentDuplicateTests(DuplicateBase, TransactionTestCase):
    """กดจองสองครั้งพร้อมกันจริง: สอง request ผ่านการตรวจเบื้องต้นใน serializer
    ได้ทั้งคู่ ต้องเหลือรายการเดียวเพราะ perform_create ล็อกแถวห้องแล้วตรวจซ้ำ"""

    ATTEMPTS = 5

    def setUp(self):
        self.make_fixtures()

    def fire_at_once(self, url, payload_factory):
        barrier = threading.Barrier(self.ATTEMPTS)
        results = []
        lock = threading.Lock()

        def worker():
            client = self.client_for(self.bot)
            barrier.wait()
            try:
                r = client.post(url, payload_factory(), format='json')
                with lock:
                    results.append(r.status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(self.ATTEMPTS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return sorted(results)

    def test_simultaneous_identical_bookings_create_one(self):
        codes = self.fire_at_once('/api/bookings/', self.booking_payload)
        self.assertEqual(codes.count(201), 1, codes)
        self.assertEqual(codes.count(400), self.ATTEMPTS - 1, codes)
        self.assertEqual(Booking.objects.count(), 1)

    def test_simultaneous_identical_term_bookings_create_one(self):
        def payload():
            return {
                'room': self.room.id, 'subject_name': 'สถิติวิศวกรรม', 'attendees': 20,
                'day_of_week': 1, 'start_time': time_type(10).strftime('%H:%M'),
                'end_time': time_type(12).strftime('%H:%M'),
                'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=60)),
            }
        codes = self.fire_at_once('/api/term-bookings/', payload)
        self.assertEqual(codes.count(201), 1, codes)
        self.assertEqual(TermBooking.objects.count(), 1)
