"""ตรวจ (และแก้) วันในสัปดาห์ของการจองทั้งเทอมที่ถูกบันทึกผิด convention

ที่มา: หน้าค้นหา (SearchPage.jsx) เคยส่ง day_of_week เป็นเลขแบบ JavaScript
(0=อาทิตย์, 1=จันทร์ ... 6=เสาร์) แต่ backend เก็บ/ตีความแบบ Python weekday()
(0=จันทร์ ... 6=อาทิตย์ — ดู TermBooking.DAY_CHOICES และ
_recurring_slot_conflicts) ทำให้การจองทั้งเทอมที่สร้างผ่านหน้าเว็บถูกบันทึก
เป็น "วันถัดไป" จากที่ผู้ใช้เลือก (เลือกพุธได้พฤหัสบดี ฯลฯ ส่วนอาทิตย์เพี้ยน
ไปเป็นจันทร์) แก้ที่ต้นทางแล้วใน commit d7ec1a5 — คำสั่งนี้ไว้จัดการ "ข้อมูลเก่า"
ที่ค้างอยู่ก่อนหน้านั้น

ค่าที่ถูกต้อง = (ค่าที่เก็บไว้ + 6) % 7   (แปลง JS -> Python)

ใช้งาน:
    python manage.py audit_term_dow                 # ดูอย่างเดียว (dry-run)
    python manage.py audit_term_dow --apply --ids 3,7   # แก้จริง (ต้องระบุ --ids)
    python manage.py audit_term_dow --apply --ids 3,7,9   # แก้เฉพาะ id ที่ระบุ

**อ่านผล dry-run ก่อนเสมอ** — รายการที่ถูกสร้างผ่าน Django admin หรือยิง API
ตรงๆ ด้วย convention ที่ถูกอยู่แล้ว ไม่ควรถูกเลื่อน คำสั่งนี้เลยไม่เดาให้เอง
แต่จะโชว์สัญญาณประกอบ (term_name ตรงแพตเทิร์นของหน้าเว็บไหม, role ของผู้จอง)
ให้ตัดสินใจ แล้วค่อยเลือกแก้ด้วย --ids
"""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from booking.models import TermBooking

DAYS = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
# term_name ที่หน้าเว็บสร้างให้อัตโนมัติ เช่น "ภาคเรียนที่ 1/2569", "ภาคฤดูร้อน/2569"
WEB_TERM_NAME = re.compile(r'^(ภาคเรียนที่ \d|ภาคฤดูร้อน)/\d{4}$')


def day_label(v):
    return DAYS[v] if isinstance(v, int) and 0 <= v < 7 else f'?({v})'


class Command(BaseCommand):
    help = 'ตรวจ/แก้ day_of_week ของ TermBooking ที่บันทึกด้วย convention ของ JS แทน Python'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='แก้ข้อมูลจริง — ต้องใช้คู่กับ --ids เสมอ (ค่าเริ่มต้นคือดูอย่างเดียว)')
        parser.add_argument('--ids', type=str, default='',
                            help='จำกัดเฉพาะ id ที่ระบุ คั่นด้วย comma เช่น 3,7,9')
        parser.add_argument('--include-inactive', action='store_true',
                            help='รวมรายการที่ไม่ใช่ status=active ด้วย')

    def handle(self, *args, **opts):
        qs = TermBooking.objects.select_related('user', 'room').order_by('id')
        if not opts['include_inactive']:
            qs = qs.filter(status='active')
        if opts['ids']:
            wanted = {int(x) for x in opts['ids'].split(',') if x.strip()}
            qs = qs.filter(id__in=wanted)

        rows = list(qs)
        if not rows:
            self.stdout.write(self.style.WARNING('ไม่พบการจองทั้งเทอมตามเงื่อนไข'))
            return

        self.stdout.write(f'พบ {len(rows)} รายการ\n')
        self.stdout.write('id   | ตอนนี้เก็บเป็น | ถ้าแก้จะเป็น  | ผู้จอง (role)          | term_name            | สร้างผ่านเว็บ?')
        self.stdout.write('-' * 110)

        for tb in rows:
            fixed = (tb.day_of_week + 6) % 7
            role = getattr(tb.user, 'role', '?') if tb.user else '-'
            uname = tb.user.username if tb.user else '-'
            looks_web = 'ใช่' if WEB_TERM_NAME.match(tb.term_name or '') else 'ไม่แน่ใจ'
            self.stdout.write(
                f'{tb.id:<4} | {day_label(tb.day_of_week):<12} | {day_label(fixed):<12} | '
                f'{uname[:14]:<14} ({role:<7}) | {(tb.term_name or "-")[:20]:<20} | {looks_web}'
            )

        self.stdout.write('')
        self.stdout.write('หมายเหตุ: "สร้างผ่านเว็บ? = ใช่" คือ term_name ตรงแพตเทิร์นที่หน้าค้นหาสร้างให้')
        self.stdout.write('อัตโนมัติ ซึ่งเป็นทางเดียวที่ผู้ใช้ทั่วไปสร้างการจองทั้งเทอมได้ → มีโอกาสสูงที่วันเพี้ยน')
        self.stdout.write('ส่วน "ไม่แน่ใจ" อาจถูกสร้างจาก Django admin/ยิง API เอง ซึ่งอาจถูกอยู่แล้ว')

        if not opts['apply']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('นี่คือ dry-run — ยังไม่ได้แก้อะไร'))
            self.stdout.write('ถ้าตรวจแล้วโอเค สั่งแก้ด้วย: python manage.py audit_term_dow --apply --ids <id ที่จะแก้>')
            return

        # บังคับให้ระบุ --ids เสมอตอนแก้จริง: การเลื่อนวันไม่ idempotent (รันซ้ำ
        # = เลื่อนซ้ำ) และรายการที่สร้างจาก Django admin อาจถูกอยู่แล้ว การเปิดให้
        # --apply เปล่าๆ กวาดทั้งตารางจึงเสี่ยงทำข้อมูลที่ถูกอยู่แล้วพังโดยไม่มีทาง
        # ย้อนกลับอัตโนมัติ
        if not opts['ids']:
            raise CommandError(
                'ต้องระบุ --ids ด้วยตอนใช้ --apply (เช่น --apply --ids 3,7)\n'
                'ดูผล dry-run ก่อนแล้วเลือกเฉพาะ id ที่ยืนยันแล้วว่าวันเพี้ยนจริง — '
                'คำสั่งนี้ไม่แก้ทั้งตารางให้ เพราะการเลื่อนวันรันซ้ำแล้วเพี้ยนเพิ่ม '
                'และรายการที่สร้างนอกหน้าเว็บอาจถูกอยู่แล้ว'
            )

        with transaction.atomic():
            for tb in rows:
                tb.day_of_week = (tb.day_of_week + 6) % 7
                tb.save(update_fields=['day_of_week'])

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'แก้แล้ว {len(rows)} รายการ'))
        self.stdout.write(self.style.WARNING('อย่ารันคำสั่งนี้ซ้ำกับ id เดิม — วันจะเลื่อนไปอีกรอบ'))
