// ตัวเลือกระยะเวลาจองมาตรฐานของฟอร์มจอง (ต้องตรงกับที่ปุ่มเลือกในฟอร์มมีให้จริง)
export const DURATIONS = [
  { label: '1 ชม.', hours: 1 },
  { label: '2 ชม.', hours: 2 },
  { label: '3 ชม.', hours: 3 },
]

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
