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

// ห้องว่างจากฟีด "ห้องว่างตอนนี้" มี available_until ติดมาด้วย (เวลาที่ห้อง
// ว่างจริงถึง ไม่ใช่ทุกห้องว่างแค่ 1 ชม.เท่ากันหมด) — ถ้าเลือกจองห้องจากฟีดนี้
// ค่า duration เริ่มต้นควรสอดคล้องกับที่การ์ดโฆษณาไว้ ไม่ใช่ค้างที่ 1 ชม.
// (ค่า default ตายตัว) เสมอโดยไม่เกี่ยวอะไรกับเวลาที่ห้องว่างจริง
export const pickFittingDuration = (startTime, availableUntil) => {
  if (!startTime || !availableUntil) return null
  const [sh, sm] = startTime.split(':').map(Number)
  const [uh, um] = availableUntil.split(':').map(Number)
  const hoursFree = (uh * 60 + um - (sh * 60 + sm)) / 60
  const fitting = DURATIONS.map(d => d.hours).filter(h => h <= hoursFree)
  return fitting.length > 0 ? Math.max(...fitting) : Math.min(...DURATIONS.map(d => d.hours))
}
