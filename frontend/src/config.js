// ค่าที่ปรับได้ของหน้าเว็บ รวมไว้ที่เดียว — ดูภาพรวมทุกค่าได้ที่ README.md
// หัวข้อ "แก้พารามิเตอร์" (ค่าฝั่ง server อยู่ที่ booking/config.py และ settings.py)

// ── เชื่อมต่อ backend ─────────────────────────────────────────
// URL จริงตั้งผ่าน env VITE_API_URL ตอน build (Vercel/Render) ค่านี้ใช้ตอนรันในเครื่อง
export const DEFAULT_API_URL = 'http://127.0.0.1:8000/api/'
// Render free tier หลับเมื่อไม่มีคนใช้ request แรกหลังตื่นอาจนาน 30–50 วินาที
export const REQUEST_TIMEOUT_MS = 60000
// request ช้ากว่านี้ขึ้นแถบ "เซิร์ฟเวอร์กำลังตื่น"
export const SLOW_REQUEST_MS = 4000

// ── ฟอร์มจอง ─────────────────────────────────────────────────
// ปุ่มเวลาเริ่มในหน้าค้นหา (เว้น 12:00 พักเที่ยง)
export const TIME_SLOTS = ['08:00', '09:00', '10:00', '11:00', '13:00', '14:00', '15:00', '16:00']
// ปุ่มระยะเวลาจอง (ยังกรอกจำนวนชั่วโมงเองได้ผ่านปุ่ม "กำหนดเอง")
export const DURATIONS = [
  { label: '1 ชม.', hours: 1 },
  { label: '2 ชม.', hours: 2 },
  { label: '3 ชม.', hours: 3 },
]

// ── เช็คอิน / สถานะ ───────────────────────────────────────────
// ต้องตรงกับ CHECKIN_OPENS_MINUTES_BEFORE ใน booking/config.py
export const CHECKIN_OPENS_MINUTES_BEFORE = 15
// หน้าแอดมิน: การจองที่จะเริ่มภายในกี่นาทีนับเป็น "จะเริ่มเร็วๆ"
// ต้องตรงกับ STARTING_SOON_MINUTES ใน booking/config.py
export const STARTING_SOON_MINUTES = 30
// หน้าแอดมิน: คำนวณสถานะห้องใหม่ทุกกี่มิลลิวินาที
export const ADMIN_STATUS_REFRESH_MS = 30000

// ── รายการ ──────────────────────────────────────────────────
// หน้าโปรไฟล์/หน้าแรกขอการจองของตัวเองได้ทีละกี่รายการ (backend จำกัดสูงสุด 200)
export const MY_BOOKINGS_PAGE_SIZE = 200

// ── รหัสผ่าน ─────────────────────────────────────────────────
// ตรวจเบื้องต้นก่อนส่ง กฎเต็มอยู่ที่ AUTH_PASSWORD_VALIDATORS ใน settings.py
export const PASSWORD_MIN_LENGTH = 8
