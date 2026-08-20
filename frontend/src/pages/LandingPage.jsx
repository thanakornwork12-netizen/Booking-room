import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const hasToken = () => !!(localStorage.getItem('access_token') || sessionStorage.getItem('access_token'))

const supportInfo = {
  organization: 'สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
  phone: '045-353102',
  email: 'ocn@ubu.ac.th',
  facebook: 'https://www.facebook.com/odlfanpage',
  copyright: `สงวนลิขสิทธิ์ © ${new Date().getFullYear()} มหาวิทยาลัยอุบลราชธานี`,
}

const FEATURES = [
  {
    emoji: '🤖',
    box: 'bg-blue-50',
    title: 'AI พยากรณ์ความต้องการห้อง',
    desc: 'วิเคราะห์ข้อมูลการใช้งานและแนะนำห้องที่เหมาะสม พร้อมแสดงระดับความต้องการ ต่ำ ปานกลาง ด่วน',
  },
  {
    emoji: '🔍',
    box: 'bg-indigo-50',
    title: 'กรองห้องตามอุปกรณ์',
    desc: 'ค้นหาห้องที่มีโปรเจกเตอร์ ไวท์บอร์ด คอมพิวเตอร์ หรืออุปกรณ์เฉพาะทางได้อย่างละเอียด',
  },
  {
    emoji: '📅',
    box: 'bg-violet-50',
    title: 'จองได้ทั้งรายวันและทั้งเทอม',
    desc: 'รองรับทั้งการจองระยะสั้นรายวัน และการจองประจำตลอดภาคการศึกษา',
  },
  {
    emoji: '✅',
    box: 'bg-emerald-50',
    title: 'เช็คอินง่ายในระบบ',
    desc: 'ยืนยันการใช้ห้องด้วยการกดเช็คอินในระบบก่อนเวลาเริ่ม 15 นาที ไม่ต้องสแกนอะไรเพิ่ม',
  },
]

const STEPS = [
  { emoji: '🔎', title: 'ค้นหาห้อง', desc: 'ระบุวัน เวลา จำนวนคน และอุปกรณ์ที่ต้องการ' },
  { emoji: '🤖', title: 'ดูคำแนะนำจาก AI', desc: 'ระบบแสดงห้องที่เหมาะสมพร้อมระดับความต้องการ' },
  { emoji: '📋', title: 'ยืนยันการจอง', desc: 'กรอกหัวข้อและยืนยันรายละเอียด' },
  { emoji: '✅', title: 'เช็คอินก่อนเริ่มใช้งาน', desc: 'กดเช็คอินภายใน 15 นาทีก่อนเวลาเริ่ม' },
]

const STATS = [
  { value: '69', label: 'ห้องในระบบ' },
  { value: '16', label: 'อาคาร' },
  { value: '>90%', label: 'ความแม่นยำ AI (ห้องที่มีข้อมูลเพียงพอ)' },
  { value: '4', label: 'บทบาทที่รองรับ' },
]

export default function LandingPage() {
  const navigate = useNavigate()

  // คนที่ล็อกอินค้างอยู่แล้วไม่ควรเห็นหน้าโฆษณานี้ซ้ำ — เด้งไป Dashboard ทันที
  useEffect(() => {
    if (hasToken()) navigate('/home', { replace: true })
  }, [navigate])

  return (
    <div className="min-h-screen w-full bg-slate-50 text-slate-900">
      {/* ── Navbar ─────────────────────────────────────── */}
      <header className="border-b border-slate-100 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <p className="text-lg font-extrabold text-blue-700">🏢 UBU Smart Booking</p>
          <button
            type="button"
            onClick={() => navigate('/login')}
            className="rounded-full bg-blue-700 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-blue-800"
          >
            เข้าสู่ระบบ
          </button>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────── */}
      <section className="mx-auto max-w-3xl px-5 py-14 text-center sm:px-8 lg:py-20">
        <h1 className="text-3xl font-extrabold leading-tight text-blue-700 sm:text-4xl">
          ระบบจองห้องอัจฉริยะ
          <span className="mt-1 block text-indigo-600">มหาวิทยาลัยอุบลราชธานี</span>
        </h1>
        <p className="mx-auto mt-4 max-w-lg text-sm leading-7 text-slate-600 sm:text-base">
          ยกระดับการจัดการพื้นที่การศึกษาด้วยเทคโนโลยี AI ที่ช่วยคาดการณ์และแนะนำห้องที่เหมาะสมที่สุดสำหรับคุณ
          พร้อมระบบค้นหาตามอุปกรณ์และจัดการตารางเวลาอย่างมีประสิทธิภาพ
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/login')}
            className="rounded-full bg-blue-700 px-6 py-3 text-sm font-bold text-white transition hover:bg-blue-800"
          >
            เข้าสู่ระบบ
          </button>
          <button
            type="button"
            onClick={() => navigate('/login')}
            className="rounded-full border border-blue-200 px-6 py-3 text-sm font-bold text-blue-700 transition hover:bg-blue-50"
          >
            ดูวิธีใช้งาน
          </button>
        </div>
      </section>

      {/* ── Features ───────────────────────────────────── */}
      <section className="bg-white py-14">
        <div className="mx-auto max-w-6xl px-5 sm:px-8">
          <h2 className="text-center text-2xl font-extrabold text-slate-900">ฟีเจอร์เด่น</h2>
          <p className="mt-2 text-center text-sm text-slate-500">
            เครื่องมือที่ออกแบบมาเพื่อลดความซับซ้อนในการจัดการห้องเรียนและห้องประชุม
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {FEATURES.map(f => (
              <div key={f.title} className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
                <div className={`flex h-12 w-12 items-center justify-center rounded-2xl text-2xl ${f.box}`}>
                  {f.emoji}
                </div>
                <p className="mt-3 text-sm font-bold text-slate-900">{f.title}</p>
                <p className="mt-1.5 text-sm leading-6 text-slate-500">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ───────────────────────────────── */}
      <section className="py-14">
        <div className="mx-auto max-w-6xl px-5 sm:px-8">
          <h2 className="text-center text-2xl font-extrabold text-slate-900">วิธีใช้งานง่ายๆ 4 ขั้นตอน</h2>
          <div className="mt-10 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.title} className="text-center">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-blue-700 text-xl text-white">
                  {s.emoji}
                </div>
                <p className="mt-3 text-xs font-bold text-blue-700">ขั้นที่ {i + 1}</p>
                <p className="mt-1 text-sm font-bold text-slate-900">{s.title}</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Stats ──────────────────────────────────────── */}
      <section className="bg-blue-700 py-14">
        <div className="mx-auto max-w-6xl px-5 sm:px-8">
          <h2 className="text-center text-2xl font-extrabold text-white">ตัวเลขที่น่าเชื่อถือ</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STATS.map(s => (
              <div key={s.label} className="rounded-2xl bg-blue-600/60 p-5 text-center">
                <p className="text-3xl font-extrabold text-white">{s.value}</p>
                <p className="mt-1 text-xs font-semibold text-blue-100">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────── */}
      <footer className="border-t border-slate-100 bg-white py-8">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div>
            <p className="font-extrabold text-blue-700">🏢 UBU Smart Booking</p>
            <p className="mt-1 text-xs text-slate-400">{supportInfo.copyright}</p>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
            <span>โทร. {supportInfo.phone}</span>
            <span>{supportInfo.email}</span>
            <a href={supportInfo.facebook} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
              Facebook: OCNfanpage
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
