from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


class T01RegisterTests(TestCase):
    """T01 — สมัครสมาชิก: กรอกข้อมูลครบ, password ตรงกัน, student_id เป็นตัวเลข"""

    def setUp(self):
        self.client = APIClient()
        self.payload = {
            'username': 'qa_test_bot',
            'first_name': 'QA',
            'last_name': 'Bot',
            'email': 'qa_test_bot@example.com',
            'password': 'QaTest1234',
            'password2': 'QaTest1234',
            'role': 'student',
            'faculty': 'วิศวกรรมศาสตร์',
            'phone': '0812345678',
            'student_id': '6611234567',
        }

    def test_register_happy_path(self):
        r = self.client.post('/api/auth/register/', self.payload, format='json')
        print('REGISTER status:', r.status_code, r.data)
        self.assertEqual(r.status_code, 201)

        u = User.objects.get(username='qa_test_bot')
        self.assertEqual(u.student_id, '6611234567')
        self.assertEqual(u.role, 'student')
        self.assertTrue(u.check_password('QaTest1234'))
        self.assertNotEqual(u.password, 'QaTest1234')  # hashed

    def test_login_after_register(self):
        self.client.post('/api/auth/register/', self.payload, format='json')
        r = self.client.post('/api/auth/login/',
                             {'username': 'qa_test_bot', 'password': 'QaTest1234'},
                             format='json')
        print('LOGIN status:', r.status_code, list(getattr(r, 'data', {}) or {}))
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.data)

        # token ใช้เรียก endpoint ที่ต้องล็อกอินได้จริง
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + r.data['access'])
        p = self.client.get('/api/auth/profile/')
        print('PROFILE status:', p.status_code, p.data)
        self.assertEqual(p.status_code, 200)
        self.assertEqual(p.data['username'], 'qa_test_bot')

    def test_password_mismatch_rejected(self):
        bad = dict(self.payload, password2='Different999')
        r = self.client.post('/api/auth/register/', bad, format='json')
        print('MISMATCH status:', r.status_code, r.data)
        self.assertEqual(r.status_code, 400)

    def test_non_numeric_student_id_rejected(self):
        bad = dict(self.payload, student_id='66ABC1234')
        r = self.client.post('/api/auth/register/', bad, format='json')
        print('NON-NUMERIC status:', r.status_code, r.data)
        self.assertEqual(r.status_code, 400)
