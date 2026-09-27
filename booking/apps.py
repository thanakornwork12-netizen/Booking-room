from django.apps import AppConfig


class BookingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'booking'

    def ready(self):
        # import เพื่อลงทะเบียน signal handler (มีผลตอน import) — ห้ามลบแม้ไม่ได้เรียกใช้ตรง ๆ
        import booking.signals  # noqa: F401
        from .scheduler import start
        start()