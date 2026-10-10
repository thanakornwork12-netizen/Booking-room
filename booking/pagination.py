"""การแบ่งหน้าของ API — ค่าเริ่มต้น 20 รายการ แต่หน้าเว็บขอได้มากขึ้นด้วย ?page_size=

เดิมใช้ PageNumberPagination ตายตัว 20 รายการ หน้าโปรไฟล์และหน้าแรกโหลดแค่หน้าแรก
คนที่จองเกิน 20 ครั้งจึงเห็นประวัติไม่ครบ"""
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200
