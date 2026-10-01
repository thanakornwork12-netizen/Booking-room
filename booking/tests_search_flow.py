"""ขั้นตอนค้นหา → แนะนำ → จอง ต้องแนะนำเฉพาะสิ่งที่จองได้จริง
รัน: python manage.py test booking.tests_search_flow --noinput"""
from datetime import timedelta

from django.utils import timezone

from booking.models import Booking, MaintenanceBlock
from booking.tests_qa import QABase, aware


class SplitRecommendTests(QABase):
    def payload(self, **over):
        p = {
            'day_of_week': 1, 'start_time': '10:00', 'end_time': '12:00', 'attendees': 20,
            'term_start': str(self.tue), 'term_end': str(self.tue + timedelta(days=56)),
        }
        p.update(over)
        return p

    def book_recommendation(self, rec):
        p = self.payload()
        return self.client.post('/api/term-bookings/split-book/', {
            'subject_name': 'วิชาสลับห้อง', 'day_of_week': p['day_of_week'],
            'start_time': p['start_time'], 'end_time': p['end_time'], 'attendees': p['attendees'],
            'first_room_id': rec['first_half']['room_id'],
            'first_term_start': rec['first_half']['term_start'],
            'first_term_end': rec['first_half']['term_end'],
            'second_room_id': rec['second_half']['room_id'],
            'second_term_start': rec['second_half']['term_start'],
            'second_term_end': rec['second_half']['term_end'],
        }, format='json')

    def test_recommendation_skips_room_with_one_off_booking(self):
        Booking.objects.create(user=self.user_b, room=self.room, title='สอบย่อย', attendees=5,
                               start_time=aware(self.tue, 10), end_time=aware(self.tue, 12),
                               status='approved')
        r = self.client.post('/api/term-bookings/split-recommend/', self.payload(), format='json')
        self.assertEqual(r.status_code, 200, r.data)
        rec = r.data['recommended_split']
        self.assertIsNotNone(rec)
        self.assertNotEqual(rec['first_half']['room_id'], self.room.id,
                            'แนะนำห้องที่มีการจองรายครั้งทับในครึ่งแรก')
        booked = self.book_recommendation(rec)
        self.assertEqual(booked.status_code, 201, f'จองตามแผนที่ระบบแนะนำไม่ได้: {booked.data}')

    def test_recommendation_skips_room_under_maintenance(self):
        MaintenanceBlock.objects.create(room=self.room, start_time=aware(self.tue, 8),
                                        end_time=aware(self.tue, 17), reason='ซ่อมแอร์',
                                        status='scheduled', created_by=self.admin)
        rec = self.client.post('/api/term-bookings/split-recommend/', self.payload(),
                               format='json').data['recommended_split']
        self.assertNotEqual(rec['first_half']['room_id'], self.room.id)
        self.assertEqual(self.book_recommendation(rec).status_code, 201)

    def test_bad_input_is_400_not_500(self):
        self.client.raise_request_exception = False
        for over in ({'attendees': 'abc'}, {'day_of_week': 'x'}, {'day_of_week': 9},
                     {'start_time': '12:00', 'end_time': '10:00'},
                     {'term_end': str(self.tue - timedelta(days=7))}):
            with self.subTest(over=over):
                r = self.client.post('/api/term-bookings/split-recommend/', self.payload(**over),
                                     format='json')
                self.assertEqual(r.status_code, 400)


class SimilarRoomTests(QABase):
    def test_nearby_time_suggestion_carries_the_new_time(self):
        for room in (self.room, self.room_b):
            Booking.objects.create(user=self.user_b, room=room, title='ประชุม', attendees=5,
                                   start_time=aware(self.tue, 10), end_time=aware(self.tue, 12),
                                   status='approved')
        r = self.client.post('/api/rooms/dynamic-recommend/', {
            'attendees': 10, 'date': str(self.tue), 'start_time': '11:00', 'end_time': '12:00',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        shifted = [s for s in r.data['suggestions'] if 'suggested_date' not in s]
        self.assertTrue(shifted, 'ไม่มีห้องแนะนำในเวลาใกล้เคียง')
        for s in shifted:
            self.assertIn('suggested_start_time', s, 'แนะนำเวลาใหม่แต่ไม่บอกเวลา หน้าเว็บจองเวลาเดิมที่ไม่ว่าง')
            start = s['suggested_start_time']
            end = s['suggested_end_time']
            booked = self.client.post('/api/bookings/', {
                'room': s['id'], 'title': 'ตามคำแนะนำ', 'attendees': 10,
                'start_time': f'{self.tue}T{start}:00', 'end_time': f'{self.tue}T{end}:00',
            }, format='json')
            self.assertEqual(booked.status_code, 201, booked.data)
            break


class SearchValidationTests(QABase):
    def test_search_rejects_time_already_passed(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        r = self.client.post('/api/rooms/search/', {
            'attendees': 10, 'date': str(yesterday), 'start_time': '10:00', 'end_time': '12:00',
        }, format='json')
        self.assertEqual(r.status_code, 400, 'ค้นหาเวลาที่ผ่านไปแล้วได้ห้อง แต่กดจองจะไม่ผ่าน')

    def test_term_search_rejects_term_already_ended(self):
        today = timezone.localdate()
        r = self.client.post('/api/rooms/search/', {
            'attendees': 10, 'booking_type': 'term', 'day_of_week': 1,
            'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(today - timedelta(days=60)), 'term_end': str(today - timedelta(days=1)),
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_today_feed_keeps_room_whose_status_flag_is_stale(self):
        """status ของห้องคือสถานะ ณ ตอนนี้ — ช่วงซ่อมที่ไม่มีอยู่จริงแล้วไม่ควรซ่อนห้อง"""
        self.room.status = 'maintenance'
        self.room.save(update_fields=['status'])
        ids = {r['id'] for r in self.client.get('/api/rooms/today-feed/?limit=0').data}
        now = timezone.localtime()
        if now.hour < 20:  # ฟีดจบที่เวลาปิดอาคาร
            self.assertIn(self.room.id, ids)
