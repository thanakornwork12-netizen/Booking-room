"""Block Test T01–T30 — รันจริงผ่าน API ด้วย test database แยก

รัน:  python manage.py test booking.tests_blocktest -v 2
ผลลัพธ์ดิบจะถูกเขียนลง /tmp/blocktest_results.json (ใช้สร้างไฟล์ xlsx)
"""
import json
import os
from datetime import datetime, timedelta, time as time_type

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from booking.models import Booking, Building, MaintenanceBlock, Room, TermBooking

User = get_user_model()

RESULTS = {}
OUT = os.environ.get('BLOCKTEST_OUT', '/tmp/blocktest_results.json')


def record(code, response, note=''):
    """เก็บ status code + body ของผลจริงไว้กรอกลงตาราง"""
    if response is None:
        body = ''
        status = ''
    else:
        status = response.status_code
        try:
            body = json.dumps(response.data, ensure_ascii=False, default=str)
        except Exception:
            body = str(getattr(response, 'content', ''))[:300]
    RESULTS[code] = {'status': status, 'body': body, 'note': note}
    print(f'[{code}] {status} {body} {note}')


def next_weekday(weekday, min_days=7):
    """วันที่ในอนาคตถัดไปที่ตรงกับ weekday (0=จันทร์)"""
    d = timezone.localdate() + timedelta(days=min_days)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def aware(d, hh, mm=0):
    return timezone.make_aware(datetime.combine(d, time_type(hh, mm)))


class BlockTest(TestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.building = Building.objects.create(name='อาคารเรียนรวม 2C', code='2C')
        cls.room = Room.objects.create(
            building=cls.building, name='2C09', floor=1,
            capacity=40, room_type='ห้องเรียน',
        )
        cls.room_b = Room.objects.create(
            building=cls.building, name='2C10', floor=1,
            capacity=40, room_type='ห้องเรียน',
        )

    def setUp(self):
        self.client = APIClient()
        # ผู้ใช้ทั่วไปที่ใช้ทดสอบการจอง
        self.bot = User.objects.create_user(
            username='qa_test_bot', password='QaTest1234',
            email='qa_test_bot@example.com', role='student',
            student_id='6611111111', first_name='QA', last_name='Bot',
        )
        self.admin = User.objects.create_user(
            username='qa_admin', password='QaAdmin1234',
            email='qa_admin@example.com', role='admin',
            first_name='QA', last_name='Admin',
        )
        self.user_b = User.objects.create_user(
            username='qa_user_b', password='QaUserB1234',
            email='qa_user_b@example.com', role='student',
            student_id='6622222222', first_name='QA', last_name='UserB',
        )

    # ── helpers ────────────────────────────────────────────────
    def login(self, username, password):
        r = self.client.post('/api/auth/login/',
                             {'username': username, 'password': password}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + r.data['access'])
        return r

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def reg_payload(self, **over):
        p = {
            'username': 'qa_new_user', 'first_name': 'QA', 'last_name': 'New',
            'email': 'qa_new_user@example.com',
            'password': 'QaTest1234', 'password2': 'QaTest1234',
            'role': 'student', 'faculty': 'วิศวกรรมศาสตร์',
            'phone': '0812345678', 'student_id': '6633333333',
        }
        p.update(over)
        return p

    def make_booking(self, start, end, attendees=10, status='pending',
                     user=None, room=None, title='ประชุมทดสอบ'):
        return Booking.objects.create(
            user=user or self.bot, room=room or self.room, title=title,
            attendees=attendees, start_time=start, end_time=end, status=status,
        )

    # ══════════════════════════════════════════════════════════
    # สมัครสมาชิก T01–T04
    # ══════════════════════════════════════════════════════════
    def test_T01_register_valid(self):
        r = self.client.post('/api/auth/register/', self.reg_payload(), format='json')
        # ต้องเข้าสู่ระบบได้จริงหลังสมัคร
        lr = self.client.post('/api/auth/login/',
                              {'username': 'qa_new_user', 'password': 'QaTest1234'},
                              format='json')
        record('T01', r, f'login after register -> {lr.status_code}')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(lr.status_code, 200)
        self.assertIn('access', lr.data)

    def test_T02_register_password_mismatch(self):
        r = self.client.post('/api/auth/register/',
                             self.reg_payload(password2='Different999'), format='json')
        record('T02', r)
        self.assertEqual(r.status_code, 400)
        self.assertIn('รหัสผ่านไม่ตรงกัน', json.dumps(r.data, ensure_ascii=False, default=str))
        self.assertFalse(User.objects.filter(username='qa_new_user').exists())

    def test_T03_register_non_numeric_student_id(self):
        r = self.client.post('/api/auth/register/',
                             self.reg_payload(student_id='65abc123'), format='json')
        record('T03', r)
        self.assertEqual(r.status_code, 400)
        self.assertIn('รหัสนักศึกษาต้องเป็นตัวเลขเท่านั้น', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T04_register_duplicate_student_id(self):
        r = self.client.post('/api/auth/register/',
                             self.reg_payload(student_id='6611111111'), format='json')
        record('T04', r, 'รหัส 6611111111 เป็นของ qa_test_bot อยู่แล้ว')
        self.assertEqual(r.status_code, 400)
        self.assertIn('รหัสนักศึกษานี้ถูกใช้สมัครไปแล้ว', json.dumps(r.data, ensure_ascii=False, default=str))

    # ══════════════════════════════════════════════════════════
    # เข้าสู่ระบบ / บัญชี T05–T07
    # ══════════════════════════════════════════════════════════
    def test_T05_login_wrong_password(self):
        r = self.client.post('/api/auth/login/',
                             {'username': 'qa_test_bot', 'password': 'WrongPass999'},
                             format='json')
        body = json.dumps(r.data, ensure_ascii=False, default=str)
        record('T05', r, 'ระบบตอบ 400 (ไม่ใช่ 401) แต่ไม่คืน token และไม่เปิดเผยข้อมูลบัญชี')
        self.assertIn(r.status_code, (400, 401))
        self.assertNotIn('access', r.data)
        self.assertNotIn('qa_test_bot@example.com', body)
        self.assertNotIn('6611111111', body)

    def test_T06_change_password_same_as_old(self):
        self.auth(self.bot)
        r = self.client.post('/api/auth/change-password/', {
            'old_password': 'QaTest1234',
            'new_password': 'QaTest1234',
            'new_password2': 'QaTest1234',
        }, format='json')
        record('T06', r)
        self.assertEqual(r.status_code, 400)
        self.assertIn('รหัสผ่านใหม่ต้องไม่ซ้ำกับรหัสผ่านเดิม', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T07_delete_account_wrong_confirm_text(self):
        self.auth(self.bot)
        r = self.client.post('/api/auth/delete-account/', {
            'confirm_username': 'qa_test_bot',
            'confirm_text': 'delete me',
            'password': 'QaTest1234',
        }, format='json')
        exists = User.objects.filter(username='qa_test_bot').exists()
        record('T07', r, f'บัญชียังอยู่ = {exists}')
        self.assertEqual(r.status_code, 400)
        self.assertIn('กรุณาพิมพ์ DELETE เพื่อยืนยัน', json.dumps(r.data, ensure_ascii=False, default=str))
        self.assertTrue(exists)

    # ══════════════════════════════════════════════════════════
    # จองห้อง T08–T18
    # ══════════════════════════════════════════════════════════
    def test_T08_booking_requires_login(self):
        d = next_weekday(1)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'ทดสอบไม่ล็อกอิน', 'attendees': 10,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        record('T08', r, f'จำนวน Booking ในระบบ = {Booking.objects.count()}')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(Booking.objects.count(), 0)

    def test_T09_booking_happy_path(self):
        self.auth(self.bot)
        d = next_weekday(1)  # วันอังคาร
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'ประชุมกลุ่ม', 'attendees': 20,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        b = Booking.objects.first()
        record('T09', r, f'สถานะ = {b.status if b else None} ({d} 13:00-15:00)')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(b.status, 'pending')

    def test_T10_booking_same_start_end(self):
        self.auth(self.bot)
        d = next_weekday(1)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'เวลาเท่ากัน', 'attendees': 10,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 13).isoformat(),
        }, format='json')
        record('T10', r)
        self.assertEqual(r.status_code, 400)
        self.assertIn('เวลาสิ้นสุดต้องหลังเวลาเริ่ม', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T11_booking_in_the_past(self):
        self.auth(self.bot)
        d = timezone.localdate() - timedelta(days=3)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'จองย้อนหลัง', 'attendees': 10,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        record('T11', r, f'วันที่ใช้ทดสอบ = {d}')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ไม่สามารถจองเวลาที่ผ่านไปแล้วได้', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T12_booking_zero_attendees(self):
        self.auth(self.bot)
        d = next_weekday(1)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'ผู้เข้าร่วม 0', 'attendees': 0,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        record('T12', r)
        self.assertEqual(r.status_code, 400)
        self.assertIn('จำนวนผู้เข้าร่วมต้องมากกว่า 0', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T13_booking_attendees_equal_capacity(self):
        self.auth(self.bot)
        d = next_weekday(1)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'เต็มความจุพอดี', 'attendees': 40,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        record('T13', r, f'ความจุห้อง = {self.room.capacity}')
        self.assertEqual(r.status_code, 201)

    def test_T14_booking_attendees_over_capacity(self):
        self.auth(self.bot)
        d = next_weekday(1)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'เกินความจุ', 'attendees': 41,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        record('T14', r)
        self.assertEqual(r.status_code, 400)
        self.assertIn('จำนวนผู้เข้าร่วมเกินความจุห้อง (ห้องนี้จุได้ 40 คน)',
                      json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T15_booking_overlap(self):
        d = next_weekday(1)
        self.make_booking(aware(d, 10), aware(d, 12), status='approved')
        self.auth(self.bot)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'ซ้อนเวลา', 'attendees': 10,
            'start_time': aware(d, 11).isoformat(), 'end_time': aware(d, 13).isoformat(),
        }, format='json')
        record('T15', r, 'มีรายการเดิม 10:00-12:00 อยู่แล้ว')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ห้องนี้ถูกจองในช่วงเวลาดังกล่าวแล้ว', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T16_booking_touching_boundary(self):
        d = next_weekday(1)
        self.make_booking(aware(d, 10), aware(d, 12), status='approved')
        self.auth(self.bot)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'ต่อท้ายพอดี', 'attendees': 10,
            'start_time': aware(d, 12).isoformat(), 'end_time': aware(d, 13).isoformat(),
        }, format='json')
        record('T16', r, 'รายการเดิมจบ 12:00 รายการใหม่เริ่ม 12:00')
        self.assertEqual(r.status_code, 201)

    def test_T17_booking_overlap_term_booking(self):
        mon = next_weekday(0)
        TermBooking.objects.create(
            user=self.admin, room=self.room, subject_name='วิศวกรรมซอฟต์แวร์',
            attendees=30, day_of_week=0,
            start_time=time_type(14, 0), end_time=time_type(16, 0),
            term_start=mon - timedelta(days=7), term_end=mon + timedelta(days=30),
            status='active',
        )
        self.auth(self.bot)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'ชนกับจองทั้งเทอม', 'attendees': 10,
            'start_time': aware(mon, 14).isoformat(), 'end_time': aware(mon, 15).isoformat(),
        }, format='json')
        record('T17', r, 'มีจองทั้งเทอม จันทร์ 14:00-16:00')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ถูกจองทั้งเทอมโดย', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T18_booking_during_maintenance(self):
        d = next_weekday(1)
        MaintenanceBlock.objects.create(
            room=self.room, start_time=aware(d, 8), end_time=aware(d, 18),
            reason='ซ่อมบำรุงเชิงป้องกัน', status='scheduled', created_by=self.admin,
        )
        self.auth(self.bot)
        r = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'จองช่วงปิดซ่อม', 'attendees': 10,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        record('T18', r, 'ห้องปิดซ่อม 08:00-18:00')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ห้องนี้ปิดซ่อมบำรุงอยู่ในช่วงเวลาดังกล่าว', json.dumps(r.data, ensure_ascii=False, default=str))

    # ══════════════════════════════════════════════════════════
    # อนุมัติ / ปฏิเสธ T19–T22
    # ══════════════════════════════════════════════════════════
    def test_T19_admin_approve_pending(self):
        d = next_weekday(1)
        b = self.make_booking(aware(d, 13), aware(d, 15))
        self.auth(self.admin)
        r = self.client.post(f'/api/bookings/{b.id}/approve/', {}, format='json')
        b.refresh_from_db()
        notified = b.user.notifications.filter(type='booking_approved').exists()
        record('T19', r, f'สถานะหลังอนุมัติ = {b.status}, แจ้งเตือนผู้จอง = {notified}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b.status, 'approved')
        self.assertTrue(notified)

    def test_T20_normal_user_cannot_approve(self):
        d = next_weekday(1)
        b = self.make_booking(aware(d, 13), aware(d, 15))
        self.auth(self.bot)
        r = self.client.post(f'/api/bookings/{b.id}/approve/', {}, format='json')
        b.refresh_from_db()
        record('T20', r, f'สถานะยังเป็น {b.status}')
        self.assertEqual(r.status_code, 403)
        self.assertIn('ไม่มีสิทธิ์', json.dumps(r.data, ensure_ascii=False, default=str))
        self.assertEqual(b.status, 'pending')

    def test_T21_approve_already_approved(self):
        d = next_weekday(1)
        b = self.make_booking(aware(d, 13), aware(d, 15), status='approved')
        self.auth(self.admin)
        r = self.client.post(f'/api/bookings/{b.id}/approve/', {}, format='json')
        record('T21', r)
        self.assertEqual(r.status_code, 400)
        self.assertIn('อนุมัติได้เฉพาะรายการที่รออนุมัติเท่านั้น', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T22_admin_reject_pending(self):
        d = next_weekday(1)
        b = self.make_booking(aware(d, 13), aware(d, 15))
        self.auth(self.admin)
        r = self.client.post(f'/api/bookings/{b.id}/reject/',
                             {'reason': 'ห้องถูกใช้จัดสอบ'}, format='json')
        b.refresh_from_db()
        # ช่วงเวลานั้นต้องกลับมาว่างให้คนอื่นจองได้
        self.auth(self.user_b)
        r2 = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'จองต่อหลังถูกปฏิเสธ', 'attendees': 5,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        record('T22', r, f'สถานะ = {b.status}, คนอื่นจองช่วงเดิมได้ -> {r2.status_code}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b.status, 'rejected')
        self.assertEqual(r2.status_code, 201)

    # ══════════════════════════════════════════════════════════
    # เช็คอิน T23–T25
    # ══════════════════════════════════════════════════════════
    def test_T23_checkin_15_min_before(self):
        start = timezone.now() + timedelta(minutes=15)
        b = self.make_booking(start, start + timedelta(hours=1), status='approved')
        self.auth(self.bot)
        r = self.client.post(f'/api/bookings/{b.id}/check_in/', {}, format='json')
        b.refresh_from_db()
        record('T23', r, f'สถานะ = {b.status}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b.status, 'checked_in')

    def test_T24_checkin_16_min_before(self):
        start = timezone.now() + timedelta(minutes=16)
        b = self.make_booking(start, start + timedelta(hours=1), status='approved')
        self.auth(self.bot)
        r = self.client.post(f'/api/bookings/{b.id}/check_in/', {}, format='json')
        b.refresh_from_db()
        record('T24', r, f'สถานะยังเป็น {b.status}')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ยังไม่ถึงเวลา Check-in', json.dumps(r.data, ensure_ascii=False, default=str))
        self.assertEqual(b.status, 'approved')

    def test_T25_checkin_pending_booking(self):
        start = timezone.now() + timedelta(minutes=10)
        b = self.make_booking(start, start + timedelta(hours=1), status='pending')
        self.auth(self.bot)
        r = self.client.post(f'/api/bookings/{b.id}/check_in/', {}, format='json')
        record('T25', r)
        self.assertEqual(r.status_code, 400)
        body = json.dumps(r.data, ensure_ascii=False, default=str)
        self.assertIn('ไม่สามารถ Check-in ได้', body)
        self.assertIn('pending', body)  # แจ้งสถานะปัจจุบันกลับมาด้วย

    # ══════════════════════════════════════════════════════════
    # ยกเลิกการจอง T26–T27
    # ══════════════════════════════════════════════════════════
    def test_T26_other_user_cannot_cancel(self):
        d = next_weekday(1)
        b = self.make_booking(aware(d, 13), aware(d, 15), status='approved')
        self.auth(self.user_b)
        r = self.client.post(f'/api/bookings/{b.id}/cancel/', {}, format='json')
        b.refresh_from_db()
        record('T26', r, f'สถานะยังเป็น {b.status}')
        self.assertEqual(r.status_code, 403)
        self.assertIn('ไม่มีสิทธิ์', json.dumps(r.data, ensure_ascii=False, default=str))
        self.assertEqual(b.status, 'approved')

    def test_T27_owner_cancel_twice(self):
        d = next_weekday(1)
        b = self.make_booking(aware(d, 13), aware(d, 15), status='approved')
        self.auth(self.bot)
        r1 = self.client.post(f'/api/bookings/{b.id}/cancel/', {}, format='json')
        b.refresh_from_db()
        # ห้องต้องกลับมาว่าง
        self.auth(self.user_b)
        free = self.client.post('/api/bookings/', {
            'room': self.room.id, 'title': 'จองต่อหลังยกเลิก', 'attendees': 5,
            'start_time': aware(d, 13).isoformat(), 'end_time': aware(d, 15).isoformat(),
        }, format='json')
        self.auth(self.bot)
        r2 = self.client.post(f'/api/bookings/{b.id}/cancel/', {}, format='json')
        record('T27', r2,
               f'ครั้งแรก {r1.status_code} สถานะ={b.status}, ห้องกลับมาว่าง -> {free.status_code}')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(b.status, 'cancelled')
        self.assertEqual(free.status_code, 201)
        self.assertEqual(r2.status_code, 400)
        self.assertIn('ยกเลิกไปแล้ว', json.dumps(r2.data, ensure_ascii=False, default=str))

    # ══════════════════════════════════════════════════════════
    # จองทั้งเทอม T28–T30
    # ══════════════════════════════════════════════════════════
    def test_T28_term_end_before_start(self):
        self.auth(self.bot)
        start = next_weekday(1)
        r = self.client.post('/api/term-bookings/', {
            'room': self.room.id, 'subject_name': 'เทอมย้อนกลับ', 'attendees': 20,
            'day_of_week': 1, 'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(start), 'term_end': str(start - timedelta(days=30)),
        }, format='json')
        record('T28', r)
        self.assertEqual(r.status_code, 400)
        self.assertIn('วันสิ้นสุดเทอมต้องหลังวันเริ่มเทอม', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T29_term_day_never_occurs(self):
        self.auth(self.bot)
        mon = next_weekday(0)
        r = self.client.post('/api/term-bookings/', {
            'room': self.room.id, 'subject_name': 'ทุกวันเสาร์', 'attendees': 20,
            'day_of_week': 5, 'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(mon), 'term_end': str(mon + timedelta(days=2)),
        }, format='json')
        record('T29', r, f'ช่วงเทอม {mon} ถึง {mon + timedelta(days=2)} (จ.-พ.)')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ช่วงวันที่ที่เลือกไม่มีวันดังกล่าวเลย', json.dumps(r.data, ensure_ascii=False, default=str))

    def test_T30_term_overlaps_existing_daily_booking(self):
        tue = next_weekday(1)
        self.make_booking(aware(tue, 10), aware(tue, 12),
                          status='approved', title='ติวรายวิชา')
        self.auth(self.bot)
        r = self.client.post('/api/term-bookings/', {
            'room': self.room.id, 'subject_name': 'สถิติวิศวกรรม', 'attendees': 20,
            'day_of_week': 1, 'start_time': '10:00', 'end_time': '12:00',
            'term_start': str(tue - timedelta(days=1)),
            'term_end': str(tue + timedelta(days=60)),
        }, format='json')
        record('T30', r, f'มีจองรายวัน อังคาร {tue} 10:00-12:00 อยู่แล้ว')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ซ้อนกับวันและเวลาที่เลือกในบางสัปดาห์', json.dumps(r.data, ensure_ascii=False, default=str))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(RESULTS, f, ensure_ascii=False, indent=2)
        print(f'\n>>> wrote {len(RESULTS)} results to {OUT}')
