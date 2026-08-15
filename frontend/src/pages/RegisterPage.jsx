import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  Eye, EyeOff, UserPlus, ChevronRight, Building2, ShieldCheck,
  Check, ChevronDown, CalendarRange, UserRound, AtSign, Mail, Lock,
  ShieldCheck as ShieldIcon, Bell, Hash,
} from 'lucide-react'
import api from '../api/axios'

const FACULTIES = [
  'วิทยาศาสตร์','วิศวกรรมศาสตร์','บริหารธุรกิจ',
  'นิติศาสตร์','แพทยศาสตร์','พยาบาลศาสตร์',
  'เกษตรศาสตร์','ศิลปศาสตร์','สาธารณสุขศาสตร์','เภสัชศาสตร์',
]

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes rot{to{transform:rotate(360deg)}}
@keyframes roomGlow{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.35)}50%{box-shadow:0 0 0 6px rgba(37,99,235,0)}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .06s ease both}
.au2{animation:fadeUp .28s .12s ease both}
.au3{animation:fadeUp .28s .18s ease both}
.au4{animation:fadeUp .28s .24s ease both}
.au5{animation:fadeUp .28s .30s ease both}
.room-glow{animation:roomGlow 2.6s ease-in-out infinite}
@media (prefers-reduced-motion: reduce){
  .room-glow{animation:none}
}
`

const inputCls = `w-full rounded-2xl border border-slate-200 bg-slate-50 pl-11 pr-4 py-2.5 sm:py-3 text-sm
  text-slate-800 outline-none transition-all placeholder:text-slate-400
  focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100`

const plainInputCls = `w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 sm:py-3 text-sm
  text-slate-800 outline-none transition-all placeholder:text-slate-400
  focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100`

const SCHEDULE_TIMES = ['08:00', '09:00', '10:00', '11:00', '12:00']
const SCHEDULE_ROOMS = [
  { name: 'ห้อง 301', busy: [1] },
  { name: 'ห้อง 302', busy: [0, 4] },
  { name: 'ห้อง 303', free: 2 },
  { name: 'ห้อง 304', busy: [3] },
  { name: 'ห้อง 305', busy: [] },
]

const FEATURE_CHIPS = [
  { icon: CalendarRange, label: 'กรอกง่าย',   sub: 'ทีละขั้นตอน ไม่งง' },
  { icon: ShieldIcon,    label: 'ปลอดภัย',    sub: 'ข้อมูลถูกเข้ารหัส' },
  { icon: Bell,          label: 'ยืนยันไว',   sub: 'ใช้งานได้ทันที' },
]

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    username: '',
    first_name: '',
    email: '',
    student_id: '',
    password: '',
    password2: '',
    role: 'student',
    faculty: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [showPass2, setShowPass2] = useState(false)
  const [step, setStep] = useState(1)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const goNext = () => {
    if (!form.first_name) return setError('กรุณากรอกชื่อ-นามสกุล')
    if (!form.username) return setError('กรุณากรอกชื่อผู้ใช้')
    if (!form.email) return setError('กรุณากรอกอีเมล')
    if (form.student_id && !/^\d+$/.test(form.student_id)) return setError('รหัสนักศึกษาต้องเป็นตัวเลขเท่านั้น')
    setError('')
    setStep(2)
  }

  const onSubmit = async () => {
    if (!form.faculty) return setError('กรุณาเลือกคณะ/หน่วยงาน')
    if (!form.password) return setError('กรุณากรอกรหัสผ่าน')
    if (form.password !== form.password2) return setError('รหัสผ่านไม่ตรงกัน')
    if (form.password.length < 6) return setError('รหัสผ่านต้องมีอย่างน้อย 6 ตัว')

    setLoading(true)
    setError('')
    try {
      await api.post('/auth/register/', form)
      navigate('/login')
    } catch (err) {
      setError('สมัครสมาชิกไม่สำเร็จ อาจมีชื่อผู้ใช้หรืออีเมลนี้ในระบบแล้ว')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="w-full min-h-screen bg-[#F8FAFC] relative overflow-x-hidden overflow-y-auto"
      style={{ fontFamily: "'Inter','Prompt','Sarabun','Noto Sans Thai',sans-serif" }}
    >
      <style>{ANIM}</style>

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center gap-6 px-4 py-6 sm:gap-8 sm:px-6 sm:py-8 lg:h-screen lg:flex-row lg:items-center lg:justify-center lg:gap-16 lg:py-0">

        {/* ── Brand (desktop only) ───────────────────────────── */}
        <div className="hidden max-w-md flex-col lg:flex au">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-blue-600 shadow-lg shadow-blue-200">
            <Building2 size={22} color="#fff" />
          </div>
          <h1 className="mt-5 text-3xl font-extrabold leading-tight text-slate-900">
            สมัครสมาชิก
            <span className="mt-1 block text-blue-700">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</span>
          </h1>
          <div className="mt-3 h-1 w-14 rounded-full bg-blue-600" />
          <p className="mt-3 text-sm leading-6 text-slate-500">
            สร้างบัญชีเพื่อค้นหาห้องว่าง จองรายวันหรือรายเทอมได้ทันที
          </p>

          {/* ── Schedule grid mock ──────────────────────────── */}
          <div className="mt-5 rounded-[22px] border border-slate-200 bg-white p-3.5 shadow-[0_20px_60px_rgba(37,99,235,0.08)]">
            <div className="flex items-center gap-1.5 text-sm font-bold text-slate-700">
              <CalendarRange size={15} className="text-blue-600" />
              อาคาร ODL · ชั้น 3
              <ChevronDown size={14} className="text-slate-400" />
            </div>

            <div className="mt-3 grid grid-cols-[3rem_repeat(5,1fr)] gap-1 text-center">
              <div />
              {SCHEDULE_TIMES.map(t => (
                <p key={t} className="text-[9px] font-semibold text-slate-400">{t}</p>
              ))}

              {SCHEDULE_ROOMS.map((room) => (
                <>
                  <p key={room.name} className="flex items-center text-[10px] font-semibold text-slate-500">{room.name}</p>
                  {SCHEDULE_TIMES.map((_, ci) => {
                    const isFree = room.free === ci
                    const isBusy = room.busy?.includes(ci)
                    return (
                      <div
                        key={ci}
                        className={
                          isFree
                            ? 'room-glow flex h-5 items-center justify-center rounded-md bg-blue-600'
                            : isBusy
                              ? 'h-5 rounded-md bg-slate-200'
                              : 'h-5 rounded-md bg-slate-50 border border-slate-100'
                        }
                      >
                        {isFree && <Check size={10} className="text-white" strokeWidth={3} />}
                      </div>
                    )
                  })}
                </>
              ))}
            </div>

            <div className="mt-2.5 flex items-center justify-center gap-4 border-t border-slate-100 pt-2.5 text-[9px] font-semibold text-slate-400">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full border border-slate-300" /> ว่าง</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-slate-300" /> ไม่ว่าง</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-blue-600" /> กำลังจอง</span>
            </div>
          </div>

          {/* ── Feature chips ───────────────────────────────── */}
          <div className="mt-4 grid grid-cols-3 gap-2.5">
            {FEATURE_CHIPS.map(({ icon: Icon, label, sub }) => (
              <div key={label} className="rounded-2xl border border-slate-200 bg-white/70 p-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
                  <Icon size={14} />
                </div>
                <p className="mt-1.5 text-xs font-bold text-slate-800">{label}</p>
                <p className="text-[9px] leading-3.5 text-slate-400">{sub}</p>
              </div>
            ))}
          </div>
        </div>

        {/* ── Register card ─────────────────────────────────── */}
        <div className="w-full max-w-md">
          <div className="mb-5 text-center sm:mb-6 lg:hidden au">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-blue-600 shadow-lg shadow-blue-200 sm:mb-4 sm:h-14 sm:w-14">
              <UserPlus size={22} color="#fff" />
            </div>
            <h1 className="text-lg font-extrabold text-slate-900 sm:text-xl">สมัครสมาชิก</h1>
            <p className="mt-1 text-xs text-slate-500">สร้างบัญชีผู้ใช้งานหรือผู้ดูแลระบบ</p>
          </div>

          <div className="overflow-hidden rounded-[22px] border border-slate-200 bg-white shadow-[0_20px_80px_rgba(15,23,42,0.10)] au1 sm:rounded-[28px]">
            <div className="flex items-center justify-between gap-4 p-5 pb-0 sm:p-6 sm:pb-0">
              <div>
                <p className="text-[11px] font-bold tracking-[0.22em] text-slate-400 uppercase">Register</p>
                <p className="mt-1 text-xl font-extrabold text-slate-900">{step === 1 ? 'ข้อมูลผู้ใช้งาน' : 'ตั้งรหัสผ่าน'}</p>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-blue-100 bg-blue-50 text-blue-700 sm:h-11 sm:w-11">
                <ShieldCheck size={20} />
              </div>
            </div>

            <div className="p-5 pt-4 sm:p-6 sm:pt-4">
              <div className="mb-5 flex items-center gap-2">
                {[1, 2].map(s => (
                  <div key={s} className="flex flex-1 items-center">
                    <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-all
                      ${step >= s ? 'bg-blue-700 text-white shadow-md shadow-blue-200' : 'bg-blue-100 text-blue-300'}`}>
                      {s}
                    </div>
                    {s < 2 && <div className={`mx-1.5 h-0.5 flex-1 rounded-full transition-all ${step > s ? 'bg-blue-700' : 'bg-blue-100'}`} />}
                  </div>
                ))}
                <span className="ml-2 flex-shrink-0 text-xs text-slate-500">
                  {step === 1 ? 'ข้อมูลส่วนตัว' : 'ตั้งรหัสผ่าน'}
                </span>
              </div>

              {error && (
                <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {error}
                </div>
              )}

              {step === 1 && (
                <div className="space-y-3.5 sm:space-y-4">
                  <div className="au2">
                    <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">ชื่อ-นามสกุล</label>
                    <div className="relative">
                      <UserRound size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type="text"
                        placeholder="ชื่อจริง - นามสกุล"
                        className={inputCls}
                        value={form.first_name}
                        onChange={e => set('first_name', e.target.value)}
                        style={{ fontFamily: 'inherit' }}
                      />
                    </div>
                  </div>
                  <div className="au2">
                    <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">ชื่อผู้ใช้</label>
                    <div className="relative">
                      <AtSign size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type="text"
                        placeholder="เช่น somchai123"
                        className={inputCls}
                        value={form.username}
                        onChange={e => set('username', e.target.value)}
                        style={{ fontFamily: 'inherit' }}
                      />
                    </div>
                  </div>
                  <div className="au2">
                    <label className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-blue-700">
                      รหัสนักศึกษา
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold normal-case tracking-normal text-blue-500">#ไม่บังคับ</span>
                    </label>
                    <div className="relative">
                      <Hash size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type="text"
                        inputMode="numeric"
                        placeholder="เช่น 66114640275 (อาจารย์ไม่ต้องกรอก)"
                        className={inputCls}
                        value={form.student_id}
                        onChange={e => set('student_id', e.target.value.replace(/\D/g, ''))}
                        style={{ fontFamily: 'inherit' }}
                      />
                    </div>
                  </div>
                  <div className="au3">
                    <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">อีเมล</label>
                    <div className="relative">
                      <Mail size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type="email"
                        placeholder="example@ubu.ac.th"
                        className={inputCls}
                        value={form.email}
                        onChange={e => set('email', e.target.value)}
                        style={{ fontFamily: 'inherit' }}
                      />
                    </div>
                  </div>

                  <div className="au4">
                    <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">คณะ / หน่วยงาน</label>
                    <select
                      className={plainInputCls}
                      value={form.faculty}
                      onChange={e => set('faculty', e.target.value)}
                      style={{ fontFamily: 'inherit' }}
                    >
                      <option value="">-- เลือกคณะ --</option>
                      {FACULTIES.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>

                  <button
                    type="button"
                    onClick={goNext}
                    className="au5 flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 py-3 text-sm font-bold text-white shadow-lg shadow-blue-200 transition-all hover:from-blue-700 hover:to-indigo-700 active:scale-[0.99] sm:py-3.5"
                  >
                    ถัดไป <ChevronRight size={14} />
                  </button>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-3.5 sm:space-y-4">
                  <div className="au2 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3">
                    <p className="text-sm font-bold text-slate-800">{form.first_name}</p>
                    <p className="mt-0.5 text-xs text-blue-500">{form.faculty || '—'}</p>
                  </div>

                  <div className="au2">
                    <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">รหัสผ่าน</label>
                    <div className="relative">
                      <Lock size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type={showPass ? 'text' : 'password'}
                        placeholder="อย่างน้อย 6 ตัวอักษร"
                        className={`${inputCls} pr-11`}
                        value={form.password}
                        onChange={e => set('password', e.target.value)}
                        style={{ fontFamily: 'inherit' }}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPass(!showPass)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 transition-colors hover:text-blue-600"
                      >
                        {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>

                  <div className="au3">
                    <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">ยืนยันรหัสผ่าน</label>
                    <div className="relative">
                      <Lock size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type={showPass2 ? 'text' : 'password'}
                        placeholder="กรอกรหัสผ่านอีกครั้ง"
                        className={`${inputCls} pr-11 ${form.password2 && form.password !== form.password2 ? 'border-red-300 ring-2 ring-red-100' : ''}`}
                        value={form.password2}
                        onChange={e => set('password2', e.target.value)}
                        style={{ fontFamily: 'inherit' }}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPass2(!showPass2)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 transition-colors hover:text-blue-600"
                      >
                        {showPass2 ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    {form.password2 && form.password !== form.password2 && (
                      <p className="mt-1.5 text-xs text-red-500">รหัสผ่านไม่ตรงกัน</p>
                    )}
                  </div>

                  <div className="au4 flex gap-2.5">
                    <button
                      type="button"
                      onClick={() => { setStep(1); setError('') }}
                      className="flex-1 rounded-2xl border-2 border-slate-200 py-3 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50"
                    >
                      ← ย้อนกลับ
                    </button>
                    <button
                      type="button"
                      onClick={onSubmit}
                      disabled={loading}
                      className="flex-[2] flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 py-3 text-sm font-bold text-white shadow-lg shadow-blue-200 transition-all hover:from-blue-700 hover:to-indigo-700 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-400 disabled:shadow-none"
                    >
                      {loading
                        ? <><div className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white" style={{ animation: 'rot .7s linear infinite' }} />กำลังสมัคร...</>
                        : <><UserPlus size={14} />สมัครสมาชิก</>}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <p className="mt-5 text-center text-sm text-slate-500">
            มีบัญชีอยู่แล้ว?{' '}
            <Link to="/login" className="text-blue-700 font-bold hover:underline">เข้าสู่ระบบ</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
