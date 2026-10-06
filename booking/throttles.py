"""จำกัดจำนวนครั้งของ endpoint ที่ถูกยิงซ้ำเพื่อโจมตีได้ (ล็อกอิน / ลืมรหัสผ่าน)

นับต่อ "บัญชีที่ถูกกรอก" ไม่ใช่ต่อ IP — ในมหาวิทยาลัยนักศึกษาทั้งตึกออกเน็ต
ผ่าน IP เดียวกัน (NAT) ถ้านับต่อ IP คนหนึ่งพิมพ์ผิดรัวๆ จะล็อกทั้งตึก
เดิมไม่มีการจำกัดเลย: เดารหัสผ่านบัญชีที่สมัครเองได้ไม่จำกัด และยิงอีเมล
รีเซ็ตรหัสผ่านใส่กล่องอีเมลคนอื่นได้รัวๆ

อัตราอยู่ใน settings.BOOKING_THROTTLE_RATES เป็น (จำนวนครั้ง, วินาที) อ่านตอน
ใช้งานทุกครั้ง (ไม่ใช่ตอน import แบบ DRF ปกติ) จึงปรับใน test ได้
"""
from django.conf import settings
from rest_framework.exceptions import Throttled
from rest_framework.throttling import SimpleRateThrottle


class ThaiThrottled(Throttled):
    default_detail = 'ลองหลายครั้งเกินไป'
    extra_detail_singular = 'กรุณารออีก {wait} วินาทีแล้วลองใหม่'
    extra_detail_plural = 'กรุณารออีก {wait} วินาทีแล้วลองใหม่'


class ThaiThrottleMixin:
    """ให้ view ตอบข้อความภาษาไทยเมื่อโดนจำกัด (ค่าเริ่มต้นของ DRF เป็นอังกฤษ)"""

    def throttled(self, request, wait):
        raise ThaiThrottled(wait)


class _PerIdentifierThrottle(SimpleRateThrottle):
    fields = ()

    def get_rate(self):
        return settings.BOOKING_THROTTLE_RATES.get(self.scope)

    def parse_rate(self, rate):
        return rate if rate else (None, None)

    def get_cache_key(self, request, view):
        data = getattr(request, 'data', None) or {}
        ident = next((str(data.get(f)).strip().lower() for f in self.fields if data.get(f)), '')
        if not ident:
            return None  # ไม่ได้กรอกอะไรมา — serializer ตอบ 400 เองอยู่แล้ว
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class LoginThrottle(_PerIdentifierThrottle):
    scope = 'login'
    fields = ('username',)


class PasswordResetThrottle(_PerIdentifierThrottle):
    scope = 'password_reset'
    fields = ('email', 'username')
