"""ระดับความต้องการเหลือ 3 ระดับ (ต่ำ / ปานกลาง / เร่งด่วน) ให้ตรงกับการวัดผลแบบจำลอง

ข้อมูลพยากรณ์ที่มีอยู่แปลงตามเส้นแบ่งของการวัดผล: 'medium' เดิม (0.6–1.0 × thr_med)
เป็น 'low' และ 'high' เดิม (thr_med – thr_high) เป็น 'medium' — ต้องแปลงตามลำดับนี้
"""
from django.db import migrations, models


def to_three_levels(apps, schema_editor):
    DemandForecast = apps.get_model('booking', 'DemandForecast')
    DemandForecast.objects.filter(demand_level='medium').update(demand_level='low', availability='likely_available')
    DemandForecast.objects.filter(demand_level='high').update(demand_level='medium', availability='recommended')


def back_to_four_levels(apps, schema_editor):
    # แยก 'low' ที่มาจาก 'medium' เดิมคืนไม่ได้ — คืนแค่ 'high'
    DemandForecast = apps.get_model('booking', 'DemandForecast')
    DemandForecast.objects.filter(demand_level='medium').update(demand_level='high', availability='book_soon')


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0012_lecturer_request'),
    ]

    operations = [
        migrations.RunPython(to_three_levels, back_to_four_levels),
        migrations.AlterField(
            model_name='demandforecast',
            name='demand_level',
            field=models.CharField(choices=[('low', 'ต่ำ'), ('medium', 'ปานกลาง'), ('urgent', 'เร่งด่วน')],
                                   default='low', max_length=10),
        ),
        migrations.AlterField(
            model_name='demandforecast',
            name='availability',
            field=models.CharField(choices=[('likely_available', '🟢 ยังว่าง'), ('recommended', '🟡 ควรจอง'),
                                            ('book_now', '🔴 ควรจองตอนนี้เลย')],
                                   default='likely_available', max_length=20),
        ),
    ]
