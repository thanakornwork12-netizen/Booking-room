import { useState, useRef, Fragment } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  Eye, EyeOff, LogIn, Building2, ShieldCheck, ArrowRight,
  Check, ChevronDown, CalendarRange, UserRound, Lock,
  ShieldCheck as ShieldIcon, Bell,
} from 'lucide-react'
import { loginWithLDAP } from '../api/axios'

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes rot{to{transform:rotate(360deg)}}
@keyframes roomGlow{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.35)}50%{box-shadow:0 0 0 6px rgba(37,99,235,0)}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .07s ease both}
.au2{animation:fadeUp .28s .14s ease both}
.room-glow{animation:roomGlow 2.6s ease-in-out infinite}
@media (prefers-reduced-motion: reduce){
  .room-glow{animation:none}
}
`

const inputCls = `w-full rounded-2xl border border-slate-200 bg-slate-50 pl-11 pr-4 py-2.5 sm:py-3 text-sm
  text-slate-800 outline-none transition-all placeholder:text-slate-400
  focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100`

const supportInfo = {
  organization: 'สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
  phone: '045-353102',
  email: 'ocn@ubu.ac.th',
  copyright: 'สงวนลิขสิทธิ์ พ.ศ. 2556 ตามพระราชบัญญัติลิขสิทธิ์ 2537',
}

const SCHEDULE_TIMES = ['08:00', '09:00', '10:00', '11:00', '12:00']
const SCHEDULE_ROOMS = [
  { name: 'ห้อง 301', busy: [1] },
  { name: 'ห้อง 302', busy: [0, 4] },
  { name: 'ห้อง 303', free: 2 },
  { name: 'ห้อง 304', busy: [3] },
  { name: 'ห้อง 305', busy: [] },
]

const FEATURE_CHIPS = [
  { icon: CalendarRange, label: 'จองง่าย',   sub: 'เลือกวัน เวลา ได้ทันที' },
  { icon: ShieldIcon,    label: 'ปลอดภัย',   sub: 'ข้อมูลถูกเข้ารหัส' },
  { icon: Bell,          label: 'แจ้งเตือน', sub: 'ไม่พลาดทุกการจอง' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const [form, setForm]         = useState({ username: '', password: '' })
  const [remember, setRemember] = useState(true)
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [showPass, setShowPass] = useState(false)
  // ล็อกแบบ sync ด้วย ref กันยิงซ้ำ — ต่างจาก loading (state) ที่ต้องรอ
  // re-render ก่อนถึงจะมีผล ถ้ากด Enter สองครั้งหรือ Enter+คลิกไล่ๆ กัน
  // ในช่วงที่ยังไม่ re-render ก็ยังหลุดผ่าน guard เดิมได้
  const isSubmittingRef = useRef(false)

  const onSubmit = async () => {
    if (isSubmittingRef.current) return
    if (!form.username.trim() || !form.password) {
      setError('กรุณากรอกชื่อผู้ใช้หรือรหัสนักศึกษาและรหัสผ่าน')
      return
    }

    isSubmittingRef.current = true
    setLoading(true)
    setError('')

    try {
      console.log('[DIAG] onSubmit: calling loginWithLDAP')
      // loginWithLDAP จัดการเก็บ token และข้อมูล user ให้อัตโนมัติ
      await loginWithLDAP(form.username.trim(), form.password, remember)
      console.log('[DIAG] onSubmit: loginWithLDAP resolved, calling navigate("/")')
      navigate('/')
      console.log('[DIAG] onSubmit: navigate("/") called')
    } catch (err) {
      console.error('[DIAG] onSubmit: caught error', err, 'err.response=', err?.response, 'err.message=', err?.message, 'err.code=', err?.code)
      const msg = err?.response?.data?.detail
             || err?.response?.data?.non_field_errors?.[0]
             || (err?.response ? 'รหัสนักศึกษาหรือรหัสผ่านไม่ถูกต้อง' : 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาลองใหม่')
      setError(msg)
    } finally {
      isSubmittingRef.current = false
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
            ระบบจองห้องประชุม
            <span className="mt-1 block text-blue-700">มหาวิทยาลัยอุบลราชธานี</span>
          </h1>
          <div className="mt-3 h-1 w-14 rounded-full bg-blue-600" />
          <p className="mt-3 text-sm leading-6 text-slate-500">
            ค้นหาห้องว่าง จองรายวันหรือรายเทอมได้ทันที
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
                <Fragment key={room.name}>
                  <p className="flex items-center text-[10px] font-semibold text-slate-500">{room.name}</p>
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
                </Fragment>
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

        {/* ── Login card ─────────────────────────────────────── */}
        <div className="w-full max-w-md">
          <div className="mb-5 text-center sm:mb-6 lg:hidden au">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-blue-600 shadow-lg shadow-blue-200 sm:mb-4 sm:h-14 sm:w-14">
              <Building2 size={22} color="#fff" />
            </div>
            <h1 className="text-lg font-extrabold text-slate-900 sm:text-xl">ระบบจองห้องประชุม</h1>
            <p className="mt-1 text-xs text-slate-500">มหาวิทยาลัยอุบลราชธานี</p>
          </div>

          <div className="overflow-hidden rounded-[22px] border border-slate-200 bg-white shadow-[0_20px_80px_rgba(15,23,42,0.10)] au1 sm:rounded-[28px]">
            <div className="flex items-center justify-between gap-4 p-5 pb-0 sm:p-6 sm:pb-0">
              <div>
                <p className="text-[11px] font-bold tracking-[0.22em] text-slate-400 uppercase">Sign in</p>
                <p className="mt-1 text-xl font-extrabold text-slate-900">เข้าสู่ระบบ</p>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-blue-100 bg-blue-50 text-blue-700 sm:h-11 sm:w-11">
                <ShieldCheck size={20} />
              </div>
            </div>

            <div className="p-5 pt-4 sm:p-6 sm:pt-4">
              {error && (
                <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {error}
                </div>
              )}

              <div className="space-y-3.5 sm:space-y-4">
                <div>
                  <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">
                    ชื่อผู้ใช้ / รหัสนักศึกษา / อีเมล
                  </label>
                  <div className="relative">
                    <UserRound size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      type="text"
                      placeholder="เช่น somchai123, 66114640275 หรืออีเมล"
                      value={form.username}
                      onChange={e => setForm({ ...form, username: e.target.value })}
                      onKeyDown={e => e.key === 'Enter' && onSubmit()}
                      className={inputCls}
                      style={{ fontFamily: 'inherit' }}
                      autoComplete="username"
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">
                    รหัสผ่าน
                  </label>
                  <div className="relative">
                    <Lock size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      type={showPass ? 'text' : 'password'}
                      placeholder="กรอกรหัสผ่าน"
                      value={form.password}
                      onChange={e => setForm({ ...form, password: e.target.value })}
                      onKeyDown={e => e.key === 'Enter' && onSubmit()}
                      className={`${inputCls} pr-12`}
                      style={{ fontFamily: 'inherit' }}
                      autoComplete="current-password"
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
              </div>

              <label className="mt-4 flex select-none items-center gap-2.5 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={e => setRemember(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-200"
                />
                จดจำการเข้าสู่ระบบ
              </label>

              <button
                onClick={onSubmit}
                disabled={loading}
                className="mt-5 flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 py-3 text-sm font-bold text-white shadow-lg shadow-blue-200 transition-all hover:from-blue-700 hover:to-indigo-700 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-400 disabled:shadow-none sm:py-3.5"
              >
                {loading ? (
                  <>
                    <div
                      className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white"
                      style={{ animation: 'rot .7s linear infinite' }}
                    />
                    กำลังเข้าสู่ระบบ...
                  </>
                ) : (
                  <>
                    <LogIn size={15} />
                    เข้าสู่ระบบ
                    <ArrowRight size={15} />
                  </>
                )}
              </button>
            </div>
          </div>

          <p className="mt-5 text-center text-sm text-slate-500">
            ยังไม่มีบัญชี?{' '}
            <Link to="/register" className="text-blue-700 font-bold hover:underline">
              สมัครสมาชิก
            </Link>
          </p>

          <p className="mt-8 text-center text-xs leading-5 text-slate-400 au2">
            {supportInfo.organization} · โทร. {supportInfo.phone} · {supportInfo.email}
            <br />
            {supportInfo.copyright}
          </p>
        </div>
      </div>
    </div>
  )
}
