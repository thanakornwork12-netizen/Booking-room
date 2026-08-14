import requests

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class BrevoAPIBackend(BaseEmailBackend):
    """
    ส่งอีเมลผ่าน Brevo REST API (HTTPS) แทน SMTP ตรงๆ

    Render บล็อก outbound port 587 (ยืนยันแล้วจาก OSError: Network is
    unreachable ตอนแรก แล้วพอบังคับ IPv4 กลับกลายเป็น timeout พอดี 30
    วินาทีทุกครั้ง — รูปแบบ packet ถูกทิ้งเงียบๆ แบบนี้คือ egress firewall
    บล็อก port ไม่ใช่ปัญหา credential/network route) เปลี่ยนมาใช้ HTTPS
    (port 443) ผ่าน API แทนเลยหลีกเลี่ยงปัญหานี้ได้ทั้งหมด
    """

    API_URL = 'https://api.brevo.com/v3/smtp/email'

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, 'BREVO_API_KEY', '')
        if not api_key:
            if not self.fail_silently:
                raise ValueError('BREVO_API_KEY ยังไม่ได้ตั้งค่า')
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send_one(message, api_key)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent

    def _send_one(self, message, api_key):
        html_body = None
        for content, mimetype in getattr(message, 'alternatives', []):
            if mimetype == 'text/html':
                html_body = content
                break

        payload = {
            'sender': {'email': message.from_email},
            'to': [{'email': addr} for addr in message.to],
            'subject': message.subject,
            'textContent': message.body,
        }
        if html_body:
            payload['htmlContent'] = html_body

        response = requests.post(
            self.API_URL,
            json=payload,
            headers={
                'api-key': api_key,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            timeout=15,
        )
        response.raise_for_status()
