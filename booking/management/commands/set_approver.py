"""ตั้งบัญชีผู้อนุมัติการจอง — ให้ user ที่มีอีเมลตาม settings.APPROVER_EMAIL
มี role = 'admin' เพื่อเข้าหน้าอนุมัติและกดอนุมัติ/ปฏิเสธการจองได้

    python manage.py set_approver                      # ใช้ settings.APPROVER_EMAIL
    python manage.py set_approver --email a@b.ac.th    # ระบุเอง
    python manage.py set_approver --create             # ถ้ายังไม่มี user ให้สร้างให้

หา user ด้วยอีเมลก่อน ถ้าไม่เจอค่อยลอง username เพราะบัญชีที่ล็อกอินผ่าน LDAP
บางคน username เป็น local-part ของอีเมล ไม่ได้เก็บ email ไว้ในฐานข้อมูล
(ดู get_recipient_email ใน booking/signals.py)
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Grant the admin role to the booking approver account"

    def add_arguments(self, parser):
        parser.add_argument('--email', default=None, help='อีเมลผู้อนุมัติ (ค่าเริ่มต้น: settings.APPROVER_EMAIL)')
        parser.add_argument('--create', action='store_true', help='สร้าง user ให้ถ้ายังไม่มี')
        parser.add_argument('--password', default=None, help='ตั้งรหัสผ่านให้ด้วย (ใช้คู่กับ --create)')

    def handle(self, *args, **options):
        email = (options['email'] or getattr(settings, 'APPROVER_EMAIL', '') or '').strip()
        if not email:
            raise CommandError('ไม่ได้ระบุอีเมล และ settings.APPROVER_EMAIL ว่างอยู่')

        User = get_user_model()
        local_part = email.split('@')[0]
        user = (
            User.objects.filter(email__iexact=email).first()
            or User.objects.filter(username__iexact=email).first()
            or User.objects.filter(username__iexact=local_part).first()
        )

        if user is None:
            if not options['create']:
                raise CommandError(
                    f'ไม่พบบัญชีของ {email} — ให้ผู้ใช้ล็อกอินเข้าระบบหนึ่งครั้งก่อน '
                    f'หรือรันใหม่พร้อม --create เพื่อสร้างบัญชีให้เลย'
                )
            user = User.objects.create(username=email, email=email)
            if options['password']:
                user.set_password(options['password'])
            else:
                user.set_unusable_password()
            self.stdout.write(self.style.WARNING(f'สร้างบัญชีใหม่: {email}'))

        old_role = user.role
        user.role = 'admin'
        if not user.email:
            user.email = email
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f"ตั้ง {user.username} ({user.email}) เป็นผู้อนุมัติแล้ว — role: {old_role} → admin"
        ))
