import { useNavigate } from 'react-router-dom'
import { ArrowRight, BookOpen, Building2, CalendarDays, CheckCircle2, Clock, Phone, Mail, Globe, Search, Settings2, ShieldCheck, Users, AlertTriangle } from 'lucide-react'

const supportInfo = {
  organization: 'สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
  address: '85 ถ.สถลมาร์ค ต.เมืองศรีไค อ.วารินชำราบ จ.อุบลราชธานี 34190',
  phone: '045-353102',
  webmaster: '1502',
  email: 'ocn@ubu.ac.th',
  facebook: 'https://www.facebook.com/odlfanpage',
  copyright: 'สงวนลิขสิทธิ์ พ.ศ. 2556 ตามพระราชบัญญัติลิขสิทธิ์ 2537',
}

const sections = [
  {
    icon: Search,
    title: 'ค้นหาห้อง',
    desc: 'ใช้หน้า "จองห้องประชุม" เพื่อค้นหาห้องจากชื่ออาคาร ชื่อห้อง เวลา และจำนวนผู้เข้าร่วม',
  },
  {
    icon: CalendarDays,
    title: 'จองรายวัน',
    desc: 'กรอกหัวข้อ วันที่ เวลา และจำนวนคน เพื่อส่งคำขอจองรายวัน',
  },
  {
    icon: BookOpen,
    title: 'จองทั้งเทอม',
    desc: 'ใช้สำหรับรายวิชาหรือกิจกรรมที่ต้องใช้ห้องประจำในช่วงเวลายาว',
  },
  {
    icon: CheckCircle2,
    title: 'เช็คอิน',
    desc: 'เมื่อถึงเวลาจอง ระบบจะเปิดให้เช็คอินเพื่อยืนยันการมาใช้งาน',
  },
  {
    icon: Settings2,
    title: 'ตรวจสอบสถานะ',
    desc: 'ติดตามการอนุมัติ การปฏิเสธ การยกเลิก และประวัติการใช้งานได้จากหน้าแรก',
  },
  {
    icon: AlertTriangle,
    title: 'ติดต่อผู้ดูแล',
    desc: 'หากพบปัญหา ให้ติดต่อ webmaster หรือสำนักคอมพิวเตอร์และเครือข่ายตามข้อมูลด้านล่าง',
  },
]

const roles = [
  {
    title: 'Student / Lecturer',
    items: ['ดูห้องและค้นหาห้องว่าง', 'สร้างคำขอจองของตัวเอง', 'ดูสถานะการจอง', 'ยกเลิกหรือเช็คอิน'],
  },
  {
    title: 'Staff',
    items: ['อนุมัติหรือปฏิเสธคำขอ', 'จัดการห้องและอาคาร', 'จัดการช่วงซ่อมบำรุง', 'ดูรายงานและสถิติ'],
  },
  {
    title: 'Admin',
    items: ['ทำได้ทุกอย่าง', 'จัดการผู้ใช้งาน', 'ดู dashboard รวม', 'ส่งออกข้อมูลรายงาน'],
  },
]

function InfoCard({ icon: Icon, title, desc }) {
  return (
    <div className="rounded-[24px] border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-700">
        <Icon size={20} />
      </div>
      <p className="text-sm font-bold text-slate-900">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">{desc}</p>
    </div>
  )
}

export default function GuidePage() {
  const navigate = useNavigate()

  return (
    <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-5">
      <section className="overflow-hidden rounded-[28px] bg-gradient-to-br from-blue-700 via-blue-700 to-indigo-700 p-6 text-white shadow-[0_18px_50px_rgba(37,99,235,0.22)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-bold uppercase tracking-[0.22em] text-blue-100">
              <BookOpen size={12} />
              User Guide
            </div>
            <h1 className="mt-4 text-3xl font-extrabold leading-tight sm:text-4xl">คู่มือการใช้งานระบบจองห้อง</h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-blue-50/90">
              ใช้สำหรับดูภาพรวมการใช้งานระบบจองห้องของมหาวิทยาลัยอุบลราชธานี ตั้งแต่การค้นหาห้อง
              การจอง การเช็คอิน ไปจนถึงการติดต่อผู้ดูแลระบบ
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={() => navigate('/search')}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-white px-5 py-3 text-sm font-bold text-blue-700 shadow-lg shadow-blue-900/15 transition hover:bg-blue-50"
            >
              <Search size={16} />
              ไปหน้าจองห้อง
            </button>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/20 bg-white/10 px-5 py-3 text-sm font-bold text-white transition hover:bg-white/15"
            >
              <ArrowRight size={16} />
              กลับหน้าหลัก
            </button>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {sections.map(section => (
          <InfoCard key={section.title} icon={section.icon} title={section.title} desc={section.desc} />
        ))}
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        {roles.map(role => (
          <div key={role.title} className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                <ShieldCheck size={19} />
              </div>
              <div>
                <p className="text-sm font-bold text-slate-900">{role.title}</p>
                <p className="text-xs text-slate-500">สิทธิ์ตามบทบาท</p>
              </div>
            </div>
            <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-600">
              {role.items.map(item => (
                <li key={item} className="flex gap-2">
                  <span className="mt-1 h-2 w-2 rounded-full bg-blue-600" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-purple-50 text-purple-700">
              <Clock size={19} />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-900">ขั้นตอนใช้งานแบบย่อ</p>
              <p className="text-xs text-slate-500">เริ่มจากค้นหาแล้วค่อยยืนยัน</p>
            </div>
          </div>
          <ol className="mt-4 space-y-3 text-sm leading-6 text-slate-600">
            <li className="rounded-2xl bg-slate-50 p-3">1. เลือกเมนูจองห้องประชุมแล้วค้นหาห้องที่เหมาะสม</li>
            <li className="rounded-2xl bg-slate-50 p-3">2. ตรวจสอบรายละเอียดห้อง ความจุ และอุปกรณ์ที่มี</li>
            <li className="rounded-2xl bg-slate-50 p-3">3. ส่งคำขอจองและรอการอนุมัติ</li>
            <li className="rounded-2xl bg-slate-50 p-3">4. เมื่อถึงเวลา ให้เช็คอินเพื่อยืนยันการใช้งาน</li>
          </ol>
        </div>

        <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700">
              <Phone size={19} />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-900">ติดต่อผู้ดูแล</p>
              <p className="text-xs text-slate-500">สำนักคอมพิวเตอร์และเครือข่าย ม.อุบลฯ</p>
            </div>
          </div>

          <div className="mt-4 space-y-3 text-sm leading-6 text-slate-700">
            <p>{supportInfo.organization}</p>
            <p>{supportInfo.address}</p>
            <p>โทร. {supportInfo.phone}</p>
            <p>webmaster ภายใน {supportInfo.webmaster}</p>
            <p>{supportInfo.email}</p>
            <a href={supportInfo.facebook} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-blue-700 hover:underline">
              <Globe size={15} />
              OCNfanpage
            </a>
          </div>

          <div className="mt-5 rounded-2xl border border-amber-100 bg-amber-50 p-4 text-xs leading-6 text-amber-800">
            พบปัญหา คำแนะนำ โปรดแจ้ง webmaster เพื่อช่วยตรวจสอบระบบ
          </div>
        </div>
      </section>

      <footer className="rounded-[24px] border border-slate-200 bg-white p-5 text-xs leading-6 text-slate-500 shadow-sm">
        <p className="font-semibold text-slate-700">{supportInfo.organization}</p>
        <p className="mt-1">{supportInfo.address}</p>
        <p className="mt-1">โทร. {supportInfo.phone} | webmaster {supportInfo.webmaster} | {supportInfo.email}</p>
        <p className="mt-1">{supportInfo.copyright}</p>
      </footer>
    </div>
  )
}
