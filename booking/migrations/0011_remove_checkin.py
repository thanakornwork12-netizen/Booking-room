# ระบบไม่มีการเช็คอินแล้ว — ผู้จองยกเลิกได้ทุกเมื่อก่อนเวลาจบ (ถ้ากำลังใช้อยู่คือคืนห้องก่อนเวลา)
from django.db import migrations, models


def checked_in_to_approved(apps, schema_editor):
    Booking = apps.get_model('booking', 'Booking')
    Booking.objects.filter(status='checked_in').update(status='approved')


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0010_notification_term_cancelled'),
    ]

    operations = [
        migrations.RunPython(checked_in_to_approved, migrations.RunPython.noop),
        migrations.RemoveField(model_name='booking', name='checked_in'),
        migrations.RemoveField(model_name='booking', name='checked_in_at'),
        migrations.RenameField(model_name='booking', old_name='checkin_token', new_name='cancel_token'),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(choices=[('pending', 'รอยืนยัน'), ('approved', 'อนุมัติแล้ว'), ('rejected', 'ปฏิเสธ'), ('cancelled', 'ยกเลิก'), ('completed', 'เสร็จสิ้น')], default='pending', max_length=20),
        ),
    ]
