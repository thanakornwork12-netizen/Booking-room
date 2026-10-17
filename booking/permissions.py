"""สิทธิ์ของผู้ดูแลระบบ — ใช้จากที่นี่ที่เดียว แทนการเขียน
``getattr(user, 'role', None) in ['admin', 'staff']`` ซ้ำในแต่ละ view"""
from rest_framework.permissions import BasePermission

ADMIN_ROLES = ('admin', 'staff')


def is_admin_or_staff(user):
    """True ถ้าผู้ใช้เป็น admin หรือ staff — AnonymousUser ไม่มี role จึงได้ False"""
    return getattr(user, 'role', None) in ADMIN_ROLES


class IsAdminOrStaff(BasePermission):
    """ใช้กับ endpoint ที่ต้องจำกัดแค่ admin/staff เท่านั้น (เช่น export ข้อมูล
    ทั้งระบบ, จัดการช่วงปิดซ่อมบำรุง) — เขียนเป็น permission class กลาง
    แทนการเช็ค role อินไลน์กระจายไปแต่ละ view เพราะเคยพลาดมาแล้วจริง:
    MaintenanceBlockViewSet เช็ค role แค่ใน get_queryset() (ใช้กับ list/
    retrieve) แต่ create() ของ DRF ModelViewSet ไม่เรียก get_queryset()
    เลย ทำให้ action สร้างช่วงปิดซ่อมหลุดผ่านไม่ต้องเช็คสิทธิ์อะไรเลย —
    ยืนยันด้วยการทดสอบจริงว่า student สร้างช่วงปิดซ่อมได้สำเร็จก่อนแก้"""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and is_admin_or_staff(request.user))


# จองทั้งเทอม (ซ้ำทุกสัปดาห์ตลอดภาคการศึกษา) — กันห้องไว้นานทั้งเทอม จึงให้เฉพาะ
# อาจารย์และฝั่งผู้ดูแล นักศึกษาจองได้เฉพาะรายครั้ง
TERM_BOOKING_ROLES = ('lecturer', 'staff', 'admin')
TERM_BOOKING_DENIED = 'นักศึกษาจองทั้งเทอมไม่ได้ จองได้เฉพาะรายครั้ง (การจองทั้งเทอมสำหรับอาจารย์และเจ้าหน้าที่)'
TERM_BOOKING_PENDING_LECTURER = 'สิทธิ์อาจารย์ของคุณรอแอดมินยืนยัน ระหว่างนี้จองได้เฉพาะรายครั้ง'


def term_booking_denied_message(user):
    """ข้อความเมื่อจองทั้งเทอมไม่ได้ — แยกกรณีที่ขอสิทธิ์อาจารย์ไว้แล้วแต่ยังรออนุมัติ"""
    if getattr(user, 'lecturer_status', '') == 'pending':
        return TERM_BOOKING_PENDING_LECTURER
    return TERM_BOOKING_DENIED


def can_book_term(user):
    """True ถ้าผู้ใช้จองทั้งเทอมได้ (อาจารย์/เจ้าหน้าที่/ผู้ดูแล)"""
    return getattr(user, 'role', None) in TERM_BOOKING_ROLES


class CanBookTerm(BasePermission):
    """ใช้กับ action ที่สร้าง/แก้/ค้นหาการจองทั้งเทอม — เช็คก่อนตรวจข้อมูล ได้ 403 ทันที"""
    message = TERM_BOOKING_DENIED

    def has_permission(self, request, view):
        allowed = bool(request.user and request.user.is_authenticated and can_book_term(request.user))
        # สมัครเป็นอาจารย์แล้วแต่แอดมินยังไม่ยืนยัน — บอกให้ชัดว่ารออยู่ ไม่ใช่ "นักศึกษา"
        if not allowed:
            self.message = term_booking_denied_message(request.user)
        return allowed
