"""ตรวจค่าที่ต้องตั้งก่อนขึ้น production — แสดงใน `python manage.py check --deploy`"""
from django.conf import settings
from django.core.checks import Tags, Warning, register

_LOCAL_HOSTS = ('localhost', '127.0.0.1')


@register(Tags.security, deploy=True)
def production_settings_check(app_configs, **kwargs):
    problems = []
    for name in ('SITE_URL', 'FRONTEND_URL'):
        value = getattr(settings, name, '')
        if any(host in value for host in _LOCAL_HOSTS):
            problems.append(Warning(
                f'{name} ยังชี้ไป {value}',
                hint=f'ตั้ง env {name} เป็น URL จริง ไม่งั้นลิงก์ในอีเมลจะเปิดไม่ได้',
                id='booking.W001',
            ))
    if not getattr(settings, 'BREVO_API_KEY', ''):
        problems.append(Warning(
            'ยังไม่ได้ตั้ง BREVO_API_KEY',
            hint='ระบบจะส่งอีเมลไม่ได้ (Render บล็อก SMTP)',
            id='booking.W002',
        ))
    if settings.SECRET_KEY.startswith('django-insecure-'):
        problems.append(Warning(
            'ใช้ SECRET_KEY สำรองที่อยู่ใน git',
            hint='ตั้ง env SECRET_KEY หรือ DJANGO_SECRET_KEY — key นี้ใช้เซ็น JWT ด้วย',
            id='booking.W003',
        ))
    return problems
