"""ตัวรันเทสต์ของโปรเจกต์ — เหมือน DiscoverRunner ของ Django แต่ห้ามเทสต์ยิง LDAP จริง

เดิมเทสต์ที่ล็อกอินด้วยบัญชีที่ไม่มีใน LDAP (เช่น qa_test_bot) ส่ง bind จริงไปที่
server ของมหาวิทยาลัยทุกครั้ง: เทสต์ช้าและพังเมื่อไม่มีเน็ต/อยู่นอกเครือข่ายไทย
ค่าเริ่มต้นคือ LDAP ตอบ "ไม่พบ" (None) เทสต์ที่ต้องการผลอื่น patch ทับได้ตามเดิม
"""
from unittest import mock

from django.test.runner import DiscoverRunner


class NoLiveLDAPRunner(DiscoverRunner):
    def run_tests(self, *args, **kwargs):
        with mock.patch('booking.serializers.authenticate_ldap', return_value=None):
            return super().run_tests(*args, **kwargs)
