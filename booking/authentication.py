"""JWT ที่ผูกกับรหัสผ่านปัจจุบันของผู้ใช้

simplejwt เป็น token แบบ stateless — ออกไปแล้วใช้ได้จนหมดอายุ (access 1 วัน,
refresh 30 วัน) แม้เจ้าของจะเปลี่ยน/รีเซ็ตรหัสผ่านแล้ว token ที่ถูกขโมยไปก็ยัง
ใช้ได้ต่อ และยังเปิดทางให้ยึดบัญชี: สมัคร username = รหัสนักศึกษาของคนอื่นไว้
ก่อน เก็บ token ไว้ พอเจ้าของตัวจริงล็อกอินผ่าน LDAP ระบบรวมเป็นบัญชีเดียวกัน
แต่ token ของคนสมัครยังเข้าได้ (ยืนยันด้วย tests_adversarial ก่อนแก้)

แก้ด้วยการฝัง "ตราประทับ" ที่คำนวณจาก hash รหัสผ่านไว้ใน token ทุกครั้งที่ออก
แล้วตรวจทุก request — รหัสผ่านเปลี่ยนเมื่อไหร่ (เปลี่ยน/รีเซ็ต/ถูก LDAP ยึดคืน
ด้วย set_unusable_password) ตราประทับเปลี่ยนตาม token เก่าทั้งหมดใช้ไม่ได้ทันที
"""
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

STAMP_CLAIM = 'pwd'


def password_stamp(user):
    """ค่าที่เปลี่ยนทุกครั้งที่รหัสผ่านเปลี่ยน — HMAC ของ hash ไม่เปิดเผย hash เอง"""
    return salted_hmac('booking.jwt-password-stamp', user.password).hexdigest()[:20]


def issue_tokens(user):
    """ออก refresh + access พร้อมตราประทับ (access ได้ claim นี้ต่อจาก refresh)"""
    refresh = RefreshToken.for_user(user)
    refresh[STAMP_CLAIM] = password_stamp(user)
    return refresh


def token_matches_user(validated_token, user):
    return constant_time_compare(validated_token.get(STAMP_CLAIM, ''), password_stamp(user))


class StampedJWTAuthentication(JWTAuthentication):
    """JWTAuthentication ที่ปฏิเสธ token ซึ่งออกก่อนรหัสผ่านเปลี่ยนครั้งล่าสุด"""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not token_matches_user(validated_token, user):
            raise AuthenticationFailed('เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่', code='token_stale')
        return user
