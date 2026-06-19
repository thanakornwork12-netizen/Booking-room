# Generated manually for MaintenanceBlock model

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0002_booking_checked_in_at_booking_checkin_token_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaintenanceBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField(verbose_name='เวลาเริ่มล็อก')),
                ('end_time', models.DateTimeField(verbose_name='เวลาสิ้นสุดล็อก')),
                ('reason', models.CharField(default='ซ่อมบำรุงเชิงป้องกัน', max_length=200)),
                ('note', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('scheduled', 'กำหนดการแล้ว'),
                        ('active', 'กำลังซ่อม'),
                        ('completed', 'เสร็จสิ้น'),
                        ('cancelled', 'ยกเลิก'),
                    ],
                    default='scheduled',
                    max_length=20,
                )),
                ('predicted_demand_avg', models.FloatField(
                    blank=True, help_text='ค่าเฉลี่ย demand จาก LSTM ช่วงที่เลือก', null=True
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='maintenance_blocks', to=settings.AUTH_USER_MODEL,
                )),
                ('room', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='maintenance_blocks', to='booking.room',
                )),
            ],
            options={
                'verbose_name': 'ช่วงล็อกซ่อมบำรุง',
                'ordering': ['start_time'],
            },
        ),
    ]
