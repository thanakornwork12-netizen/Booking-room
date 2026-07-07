from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create or update superuser Nkadmin with password 123456"

    def handle(self, *args, **options):
        User = get_user_model()
        username = "Nkadmin"
        password = "123456"
        email = "nkadmin@example.com"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        if not created:
            user.is_staff = True
            user.is_superuser = True

        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS("Superuser 'Nkadmin' created."))
        else:
            self.stdout.write(self.style.SUCCESS("Superuser 'Nkadmin' updated with new password."))
