import { useState, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, ArrowRight, UserRound, Lock, Brain, CalendarClock, CheckCircle2 } from 'lucide-react'
import { loginWithLDAP } from '../api/axios'

const inputCls = `w-full rounded-2xl border border-slate-200 bg-slate-50 pl-11 pr-4 py-3 text-sm
  text-slate-800 outline-none transition-all placeholder:text-slate-400
  focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100`

// การ์ดตัวอย่างฝั่งขวา — ข้อมูลตกแต่งเฉยๆ ไม่ใช่ข้อมูลจริงจาก API
// หมายเหตุ: เช็คอินจริงในระบบเป็นการกดปุ่มยืนยันในเว็บ ไม่มีการสแกน QR
const FEATURES = [
  { icon: Brain, title: 'แนะนำห้องด้วย AI', desc: 'ระบบแนะนำห้องอัจฉริยะตามความต้องการของคุณ' },
  { icon: CalendarClock, title: 'เช็คสถานะห้องว่างแบบเรียลไทม์', desc: 'ตรวจสอบสถานะห้องว่างแบบเรียลไทม์' },
  { icon: CheckCircle2, title: 'เช็คอินง่ายในระบบ', desc: 'กดยืนยันเช็คอินในระบบ ไม่ต้องสแกนอะไรเพิ่ม' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const [form, setForm]         = useState({ username: '', password: '' })
  const [remember, setRemember] = useState(true)
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [forgotNote, setForgotNote] = useState(false)
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
      // loginWithLDAP จัดการเก็บ token และข้อมูล user ให้อัตโนมัติ
      await loginWithLDAP(form.username.trim(), form.password, remember)
      navigate('/')
    } catch (err) {
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
    <div className="flex min-h-screen w-full flex-col bg-white lg:flex-row">
      {/* ── ฝั่งซ้าย: ฟอร์มล็อกอิน ─────────────────────── */}
      <div className="flex w-full flex-1 items-center justify-center px-6 py-10 sm:px-10 lg:px-16">
        <div className="w-full max-w-md">
          <p className="text-2xl font-extrabold text-blue-700">🏢 UBU Smart Booking</p>
          <p className="mt-2 text-sm text-slate-500">เข้าสู่ระบบเพื่อจัดการการจองห้องอัจฉริยะ</p>

          {error && (
            <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
              {error}
            </div>
          )}

          <div className="mt-6 space-y-4">
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">
                รหัสผู้ใช้ / รหัสนักศึกษา / อีเมล
              </label>
              <div className="relative">
                <UserRound size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="กรอกข้อมูล"
                  value={form.username}
                  onChange={e => setForm({ ...form, username: e.target.value })}
                  onKeyDown={e => e.key === 'Enter' && onSubmit()}
                  className={inputCls}
                  autoComplete="username"
                />
              </div>
            </div>

            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">รหัสผ่าน</label>
              <div className="relative">
                <Lock size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type={showPass ? 'text' : 'password'}
                  placeholder="กรอกรหัสผ่าน"
                  value={form.password}
                  onChange={e => setForm({ ...form, password: e.target.value })}
                  onKeyDown={e => e.key === 'Enter' && onSubmit()}
                  className={`${inputCls} pr-12`}
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

          <div className="mt-4 flex items-center justify-between">
            <label className="flex select-none items-center gap-2.5 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={remember}
                onChange={e => setRemember(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-200"
              />
              จำฉันไว้
            </label>
            <button
              type="button"
              onClick={() => setForgotNote(true)}
              className="text-sm font-semibold text-blue-700 hover:underline"
            >
              ลืมรหัสผ่าน?
            </button>
          </div>
          {forgotNote && (
            <p className="mt-2 text-xs text-slate-500">
              กรุณาติดต่อสำนักคอมพิวเตอร์และเครือข่าย โทร. 045-353102 เพื่อรีเซ็ตรหัสผ่าน
            </p>
          )}

          <button
            onClick={onSubmit}
            disabled={loading}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 py-3.5 text-sm font-bold text-white shadow-sm transition-all hover:bg-blue-800 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {loading ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                กำลังเข้าสู่ระบบ...
              </>
            ) : (
              <>
                เข้าสู่ระบบ
                <ArrowRight size={15} />
              </>
            )}
          </button>

          <p className="mt-5 text-center text-sm text-slate-500">
            ยังไม่มีบัญชี?{' '}
            <Link to="/register" className="font-bold text-blue-700 hover:underline">
              สมัครสมาชิก
            </Link>
          </p>
        </div>
      </div>

      {/* ── ฝั่งขวา: ตกแต่ง (desktop only) ─────────────────── */}
      <div className="hidden w-full flex-1 flex-col items-center justify-center gap-8 bg-indigo-50 px-10 py-10 text-center lg:flex xl:px-16">
        <div>
          <h2 className="text-2xl font-extrabold text-slate-900">ฟีเจอร์เด่นของระบบ</h2>
          <p className="mt-2 text-sm text-slate-500">ระบบจองห้องอัจฉริยะที่ช่วยให้ชีวิตวิชาการของคุณง่ายขึ้น</p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {FEATURES.map(f => (
            <div key={f.title} className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
                <f.icon size={22} />
              </div>
              <p className="mt-4 text-sm font-bold text-slate-900">{f.title}</p>
              <p className="mt-1.5 text-xs leading-5 text-slate-500">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
