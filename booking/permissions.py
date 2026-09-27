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
