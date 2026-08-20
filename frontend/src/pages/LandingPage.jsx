import { useNavigate } from 'react-router-dom'
import { Sparkles, Bot, Search, CalendarDays, CheckCircle2, ArrowRight } from 'lucide-react'

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
    icon: Bot,
    gradient: 'from-blue-500 to-indigo-500',
    title: 'AI พยากรณ์ความต้องการห้อง',
    desc: 'วิเคราะห์ข้อมูลการใช้งานและแนะนำห้องที่เหมาะสม พร้อมแสดงระดับความต้องการ ต่ำ ปานกลาง ด่วน',
  },
  {
    icon: Search,
    gradient: 'from-indigo-500 to-purple-500',
    title: 'กรองห้องตามอุปกรณ์',
    desc: 'ค้นหาห้องที่มีโปรเจกเตอร์ ไวท์บอร์ด คอมพิวเตอร์ หรืออุปกรณ์เฉพาะทางได้อย่างละเอียด',
  },
  {
    icon: CalendarDays,
    gradient: 'from-purple-500 to-fuchsia-500',
    title: 'จองได้ทั้งรายวันและทั้งเทอม',
    desc: 'รองรับทั้งการจองระยะสั้นรายวัน และการจองประจำตลอดภาคการศึกษา',
  },
  {
    icon: CheckCircle2,
    gradient: 'from-emerald-500 to-teal-500',
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

// เอฟเฟกต์เบามาก — floating dot 2 จุดในฉากหลัง Hero เท่านั้น ไม่ใช้ที่อื่น
const FLOAT_ANIM = `
@keyframes float-soft { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
.float-soft { animation: float-soft 5s ease-in-out infinite; }
.float-soft-delay { animation: float-soft 5s ease-in-out infinite; animation-delay: 1.2s; }
`

function HeroBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {/* gradient blobs — CSS เท่านั้น ไม่ใช้รูปภาพ */}
      <div className="absolute -left-24 -top-24 h-72 w-72 rounded-full bg-blue-400/20 blur-3xl" />
      <div className="absolute -right-16 top-4 h-80 w-80 rounded-full bg-purple-400/20 blur-3xl" />
      <div className="absolute bottom-0 left-1/3 h-64 w-64 rounded-full bg-indigo-300/20 blur-3xl" />
      {/* dot grid */}
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{ backgroundImage: 'radial-gradient(circle, #94a3b8 1px, transparent 1px)', backgroundSize: '26px 26px' }}
      />
      {/* floating dots เบาๆ */}
      <div className="float-soft absolute left-[12%] top-[22%] h-2.5 w-2.5 rounded-full bg-blue-400/50" />
      <div className="float-soft-delay absolute right-[15%] top-[65%] h-2 w-2 rounded-full bg-purple-400/50" />
      <div className="float-soft absolute right-[28%] top-[18%] h-1.5 w-1.5 rounded-full bg-indigo-400/50" />
    </div>
  )
}

export default function LandingPage() {
  const navigate = useNavigate()
  // ผู้ใช้ที่ล็อกอินอยู่แล้วเข้าหน้านี้ได้ตามปกติ (เช่นกดกลับมาดูจากหน้า Dashboard)
  // แค่เปลี่ยนปุ่ม CTA ให้พาไปหน้าหลักแทนหน้า login ที่ไม่จำเป็นอีกแล้ว
  const loggedIn = hasToken()
  const goToApp = () => navigate(loggedIn ? '/home' : '/login')

  return (
    <div className="min-h-screen w-full overflow-x-hidden bg-slate-50 text-slate-900">
      <style>{FLOAT_ANIM}</style>

      {/* ── Navbar ─────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-slate-100 bg-white/80 shadow-sm backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <p className="text-lg font-extrabold text-blue-700">🏫 UBU Smart Booking</p>
          <button
            type="button"
            onClick={goToApp}
            className="rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-2.5 text-sm font-bold text-white shadow-sm shadow-blue-500/20 transition-all hover:-translate-y-0.5 hover:shadow-md hover:shadow-blue-500/30"
          >
            {loggedIn ? 'ไปที่หน้าหลัก' : 'เข้าสู่ระบบ'}
          </button>
        </div>
        <div className="h-[2px] bg-gradient-to-r from-blue-500/40 via-purple-500/40 to-transparent" />
      </header>

      {/* ── Hero ───────────────────────────────────────── */}
      <section className="relative">
        <HeroBackdrop />
        <div className="relative mx-auto max-w-3xl px-5 py-16 text-center sm:px-8 lg:py-24">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-100 bg-gradient-to-r from-blue-50 to-purple-50 px-4 py-1.5 text-xs font-bold text-blue-700 shadow-sm">
            <Sparkles size={12} /> ระบบจองห้องอัจฉริยะ
          </span>

          <h1 className="mt-5 text-3xl font-extrabold leading-tight sm:text-4xl lg:text-5xl">
            <span className="block text-slate-900">ระบบจองห้องอัจฉริยะ</span>
            <span className="mt-1 block bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              มหาวิทยาลัยอุบลราชธานี
            </span>
          </h1>

          <p className="mx-auto mt-4 max-w-lg text-sm leading-7 text-slate-600 sm:text-base">
            ยกระดับการจัดการพื้นที่การศึกษาด้วยเทคโนโลยี AI ที่ช่วยคาดการณ์และแนะนำห้องที่เหมาะสมที่สุดสำหรับคุณ
            พร้อมระบบค้นหาตามอุปกรณ์และจัดการตารางเวลาอย่างมีประสิทธิภาพ
          </p>

          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <button
              type="button"
              onClick={goToApp}
              className="rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-blue-500/25 transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-blue-500/30"
            >
              {loggedIn ? 'ไปที่หน้าหลัก' : 'เข้าสู่ระบบ'}
            </button>
            <button
              type="button"
              onClick={() => navigate(loggedIn ? '/guide' : '/login')}
              className="rounded-full border border-blue-200 bg-white px-6 py-3 text-sm font-bold text-blue-700 transition-all hover:-translate-y-0.5 hover:bg-blue-50"
            >
              ดูวิธีใช้งาน
            </button>
          </div>
        </div>
      </section>

      {/* ── Features ───────────────────────────────────── */}
      <section className="relative bg-white py-16">
        <div className="mx-auto max-w-6xl px-5 sm:px-8">
          <div className="text-center">
            <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-blue-600">
              <Sparkles size={12} /> ฟีเจอร์เด่น
            </span>
            <h2 className="mt-2 text-2xl font-extrabold text-slate-900 sm:text-3xl">ฟีเจอร์เด่น</h2>
            <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
              เครื่องมือที่ออกแบบมาเพื่อลดความซับซ้อนในการจัดการห้องเรียนและห้องประชุม
            </p>
          </div>

          <div className="mt-10 grid gap-5 sm:grid-cols-2">
            {FEATURES.map(f => (
              <div
                key={f.title}
                className="group relative overflow-hidden rounded-2xl border border-slate-100 bg-white p-6 shadow-sm transition-all hover:-translate-y-1 hover:shadow-lg"
              >
                <div className={`flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br ${f.gradient} text-white shadow-sm transition-transform duration-300 group-hover:scale-110`}>
                  <f.icon size={22} />
                </div>
                <p className="mt-4 text-base font-bold text-slate-900">{f.title}</p>
                <p className="mt-1.5 text-sm leading-6 text-slate-500">{f.desc}</p>

                <ArrowRight
                  size={16}
                  className="absolute bottom-5 right-6 text-slate-300 transition-all duration-300 group-hover:translate-x-1 group-hover:text-blue-600"
                />
                <div className={`absolute inset-x-0 bottom-0 h-1 bg-gradient-to-r ${f.gradient} opacity-0 transition-opacity duration-300 group-hover:opacity-100`} />
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
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 text-xl text-white shadow-sm shadow-blue-500/20">
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
      <section className="relative overflow-hidden bg-gradient-to-br from-blue-700 to-indigo-800 py-14">
        <div className="mx-auto max-w-6xl px-5 sm:px-8">
          <h2 className="text-center text-2xl font-extrabold text-white">ตัวเลขที่น่าเชื่อถือ</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STATS.map(s => (
              <div key={s.label} className="rounded-2xl border border-white/10 bg-white/10 p-5 text-center backdrop-blur-sm">
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
            <p className="font-extrabold text-blue-700">🏫 UBU Smart Booking</p>
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
