import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

// Backend อยู่บน Render free tier ที่ sleep เวลาไม่มีคนใช้งาน — request แรก
// หลัง sleep (login, สมัคร, จอง ฯลฯ) กว่าจะตื่นอาจใช้เวลาหลายสิบวินาที
// banner นี้โผล่มาบอกผู้ใช้ว่ากำลังรอ ไม่ใช่แอปค้าง (ฟัง event จาก axios.js)
export default function SlowRequestBanner() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const onSlow = (event) => setVisible(!!event.detail?.slow)
    window.addEventListener('slow-request', onSlow)
    return () => window.removeEventListener('slow-request', onSlow)
  }, [])

  if (!visible) return null

  return (
    <div className="fixed inset-x-0 top-0 z-[100] flex justify-center px-4 pt-3">
      <div className="flex items-center gap-2.5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm font-semibold text-amber-800 shadow-lg shadow-amber-900/10">
        <Loader2 size={16} className="shrink-0 animate-spin" />
        เซิร์ฟเวอร์กำลังเริ่มทำงาน กรุณารอสักครู่...
      </div>
    </div>
  )
}
