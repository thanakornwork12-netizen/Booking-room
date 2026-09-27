// ดึงข้อความ error ที่อ่านรู้เรื่องจาก response ของ DRF — ใช้ร่วมกันทุกหน้า
export const extractErrorMessage = (err, fallback) => {
  const data = err?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.detail) return data.detail
  if (data.error) return data.error
  if (Array.isArray(data.non_field_errors) && data.non_field_errors[0]) return data.non_field_errors[0]
  const firstKey = Object.keys(data)[0]
  const firstVal = firstKey && data[firstKey]
  if (Array.isArray(firstVal) && firstVal[0]) return firstVal[0]
  return fallback
}
