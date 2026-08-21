import { useNavigate } from 'react-router-dom'

const supportInfo = {
  organization: 'สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
  address: '85 ถ.สถลมาร์ค ต.เมืองศรีไค อ.วารินชำราบ จ.อุบลราชธานี 34190',
  phone: '045-353102',
  webmaster: '1502',
  email: 'ocn@ubu.ac.th',
  facebook: 'https://www.facebook.com/odlfanpage',
  copyright: 'สงวนลิขสิทธิ์ พ.ศ. 2556 ตามพระราชบัญญัติลิขสิทธิ์ 2537',
}

const STEPS = [
  {
    n: 1, emoji: '🔍', color: 'bg-blue-700',
    title: 'ค้นหาห้อง',
    desc: 'ระบุวัน เวลา และจำนวนคน ระบบ AI จะแนะนำห้องที่เหมาะสมที่สุดให้คุณทันที พร้อมข้อมูลอุปกรณ์ภายในห้อง',
  },
  {
    n: 2, emoji: '📅', color: 'bg-indigo-600',
    title: 'ยืนยันการจอง',
    desc: 'ตรวจสอบรายละเอียด กดยืนยัน และรอรับแจ้งเตือนผ่านระบบหรืออีเมลมหาวิทยาลัย',
  },
  {
    n: 3, emoji: '🔑', color: 'bg-emerald-500',
    title: 'ใช้งานห้อง',
    desc: 'มาใช้งานห้องได้ตามเวลาที่จองไว้ หากมีเหตุไม่สามารถมาได้ กดยกเลิกได้ทันทีผ่านลิงก์ในอีเมลยืนยันการจอง',
  },
]

const PERMISSIONS = [
  {
    feature: 'จองห้องประชุมกลุ่มย่อย (Co-working)',
    student: true, lecturer: true, staff: true, admin: true,
  },
  {
    feature: 'จองห้องเรียน / ห้องบรรยาย',
    student: false, lecturer: true, staff: true, admin: true,
  },
  {
    feature: 'จองล่วงหน้า (มากกว่า 7 วัน)',
    student: false, lecturer: true, staff: true, admin: true,
  },
  {
    feature: 'จัดการระบบและอนุมัติการจองพิเศษ',
    student: false, lecturer: false, staff: false, admin: true,
  },
]

const ROLE_COLUMNS = [
  { key: 'student', label: 'นักศึกษา', emoji: '🧑‍🎓' },
  { key: 'lecturer', label: 'อาจารย์', emoji: '🧑‍🏫' },
  { key: 'staff', label: 'บุคลากร', emoji: '🧑‍💼' },
  { key: 'admin', label: 'แอดมิน', emoji: '🛠️' },
]

function PermissionMark({ ok }) {
  return ok ? (
    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">✓</span>
  ) : (
    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-slate-100 text-slate-300">✕</span>
  )
}

export default function GuidePage() {
  const navigate = useNavigate()

  return (
    <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-6">
      <header>
        <h1 className="text-3xl font-extrabold text-slate-900">วิธีใช้งานระบบ 📖</h1>
        <p className="mt-2 text-sm text-slate-500">คู่มือและขั้นตอนการจองห้องอัจฉริยะสำหรับนักศึกษาและบุคลากร</p>
      </header>

      <section>
        <h2 className="text-xl font-extrabold text-slate-900">ขั้นตอนการจองห้อง 🚀</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          {STEPS.map(step => (
            <div key={step.n} className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
              <div className={`flex h-11 w-11 items-center justify-center rounded-full text-sm font-extrabold text-white ${step.color}`}>
                {step.n}
              </div>
              <p className="mt-4 text-base font-bold text-slate-900">{step.title} {step.emoji}</p>
              <p className="mt-2 text-sm leading-6 text-slate-500">{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-extrabold text-slate-900">สิทธิ์การใช้งาน 🛡️</h2>
        <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-100 bg-white shadow-sm">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="bg-slate-50 text-left text-slate-500">
                <th className="px-5 py-3.5 font-semibold">ฟีเจอร์ / สิทธิ์</th>
                {ROLE_COLUMNS.map(col => (
                  <th key={col.key} className="px-5 py-3.5 text-center font-semibold">{col.label} {col.emoji}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PERMISSIONS.map(row => (
                <tr key={row.feature} className="border-t border-slate-100">
                  <td className="px-5 py-4 text-slate-700">{row.feature}</td>
                  {ROLE_COLUMNS.map(col => (
                    <td key={col.key} className="px-5 py-4 text-center">
                      <PermissionMark ok={row[col.key]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-2xl bg-blue-700 p-6 text-white sm:p-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-lg font-extrabold">ต้องการความช่วยเหลือเพิ่มเติม? 💬</p>
            <p className="mt-1 text-sm text-blue-100">
              {supportInfo.organization} · โทร. {supportInfo.phone} · webmaster ภายใน {supportInfo.webmaster}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => navigate('/search')}
              className="rounded-full bg-white px-5 py-2.5 text-sm font-bold text-blue-700 transition hover:bg-blue-50"
            >
              ไปหน้าจองห้อง
            </button>
            <a
              href={`mailto:${supportInfo.email}`}
              className="rounded-full border border-white/40 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-white/10"
            >
              ติดต่อผู้ดูแลระบบ
            </a>
          </div>
        </div>
      </section>

      <footer className="rounded-2xl border border-slate-100 bg-white p-5 text-xs leading-6 text-slate-500 shadow-sm">
        <p className="font-semibold text-slate-700">{supportInfo.organization}</p>
        <p className="mt-1">{supportInfo.address}</p>
        <p className="mt-1">
          โทร. {supportInfo.phone} | webmaster {supportInfo.webmaster} | {supportInfo.email} |{' '}
          <a href={supportInfo.facebook} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
            Facebook: OCNfanpage
          </a>
        </p>
        <p className="mt-1">{supportInfo.copyright}</p>
      </footer>
    </div>
  )
}
