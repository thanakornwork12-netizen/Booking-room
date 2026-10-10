import {
  CHECKIN_OPENS_MINUTES_BEFORE, DURATIONS, PASSWORD_MIN_LENGTH,
} from '../config'

// วันที่ YYYY-MM-DD ตามเวลาเครื่อง (ไทย) — ห้ามใช้ toISOString() เพราะแปลงเป็น UTC
// ก่อน ช่วง 00:00–06:59 จะได้วันที่ของเมื่อวาน
export const localDateStr = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export { DURATIONS }

// เวลาจบผ่านไปแล้วหรือยัง
export const isPast = (endTime) => new Date() > new Date(endTime)

// เปิดเช็คอินแล้วหรือยัง (ก่อนเวลาเริ่ม CHECKIN_OPENS_MINUTES_BEFORE นาที) — ผู้เรียกเช็ค
// เพิ่มว่าการจองยังไม่จบ จึงเช็คอินได้ถึงเวลาสิ้นสุดตามกฎของ backend (เดิมปุ่มหายไป
// หลังเริ่มได้ 15 นาที ทั้งที่ระบบยังรับเช็คอินอยู่ คนมาสายจึงหาปุ่มไม่เจอ)
export const canCheckIn = (startTime) =>
  (new Date() - new Date(startTime)) / 60000 >= -CHECKIN_OPENS_MINUTES_BEFORE

// ตรวจรหัสผ่านเบื้องต้นก่อนส่ง (กฎเต็มตรวจที่ backend) คืนข้อความผิด หรือ '' ถ้าผ่าน
export const passwordProblem = (password) =>
  (password.length < PASSWORD_MIN_LENGTH || /^\d+$/.test(password))
    ? `รหัสผ่านต้องมีอย่างน้อย ${PASSWORD_MIN_LENGTH} ตัว และไม่เป็นตัวเลขล้วน`
    : ''

export const addHours = (time, hours) => {
  const [h, m] = time.split(':').map(Number)
  return `${String(h + hours).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export const minutesBetween = (startTime, endTime) => {
  if (!startTime || !endTime) return null
  const [sh, sm] = startTime.split(':').map(Number)
  const [eh, em] = endTime.split(':').map(Number)
  return (eh * 60 + em) - (sh * 60 + sm)
}

// ห้องว่างจากฟีด "ห้องว่างตอนนี้" มี available_until ติดมาด้วย (เวลาที่ห้อง
// ว่างจริงถึง ไม่ใช่ทุกห้องว่างแค่ 1 ชม.เท่ากันหมด) — ถ้าเลือกจองห้องจากฟีดนี้
// ค่า duration เริ่มต้นควรสอดคล้องกับที่การ์ดโฆษณาไว้ ไม่ใช่ค้างที่ 1 ชม.
// (ค่า default ตายตัว) เสมอโดยไม่เกี่ยวอะไรกับเวลาที่ห้องว่างจริง
//
// คืนค่า null ถ้าห้องว่างไม่ถึง 1 ชม. (preset สั้นสุดที่ฟอร์มมีให้) — ห้าม
// ปัดขึ้นเป็น 1 ชม.โดยพลการ เพราะจะเกินเวลาที่ห้องว่างจริง ทำให้การ์ดโฆษณา
// เวลาที่จองไม่ได้จริง (กดแล้วจะชนกับการจองถัดไปที่ backend ปฏิเสธ) — ผู้เรียก
// ต้องจัดการกรณี null เอง (เช่น ไม่โชว์ปุ่มจองด่วน หรือโชว์ available_until ตรงๆ
// แทนโดยไม่สัญญาว่าจองได้เต็มช่วงนั้น)
const fittingHours = (startTime, availableUntil) => {
  if (!startTime || !availableUntil) return []
  const [sh, sm] = startTime.split(':').map(Number)
  const [uh, um] = availableUntil.split(':').map(Number)
  const hoursFree = (uh * 60 + um - (sh * 60 + sm)) / 60
  return DURATIONS.map(d => d.hours).filter(h => h <= hoursFree)
}

export const pickFittingDuration = (startTime, availableUntil) => {
  const fitting = fittingHours(startTime, availableUntil)
  return fitting.length > 0 ? Math.max(...fitting) : null
}

// ใช้กับฟีด "ห้องว่างวันนี้" หน้าแรกโดยเฉพาะ — เลือก preset แบบสุ่มจากที่พอดี
// แทนที่จะเอายาวสุดเสมอ (pickFittingDuration) เพราะห้องที่ว่างยาวพอกันหลายห้อง
// จะโชว์ "จองได้ 3 ชม." เหมือนกันหมดทุกใบ ดูซ้ำ ทั้งที่จริงกดจองสั้นกว่านั้นก็ได้
// เหมือนกัน — เรียกครั้งเดียวตอนโหลดข้อมูล (ไม่ใช่ในระหว่าง render) แล้วเก็บผลไว้
// ไม่งั้นตัวเลขจะสุ่มใหม่ทุกครั้งที่ re-render ดูเหมือนกระพริบเปลี่ยนไปมา
export const pickRandomFittingDuration = (startTime, availableUntil) => {
  const fitting = fittingHours(startTime, availableUntil)
  return fitting.length > 0 ? fitting[Math.floor(Math.random() * fitting.length)] : null
}
