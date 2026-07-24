import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, UserPlus, ChevronRight, Building2, ShieldCheck, Sparkles } from 'lucide-react'
import api from '../api/axios'

const FACULTIES = [
  'วิทยาศาสตร์','วิศวกรรมศาสตร์','บริหารธุรกิจ',
  'นิติศาสตร์','แพทยศาสตร์','พยาบาลศาสตร์',
  'เกษตรศาสตร์','ศิลปศาสตร์','สาธารณสุขศาสตร์','เภสัชศาสตร์',
]

const ROLES = [
  { value: 'student', label: 'นักศึกษา', icon: '🎓' },
  { value: 'lecturer', label: 'อาจารย์', icon: '👨‍🏫' },
  { value: 'staff', label: 'เจ้าหน้าที่', icon: '🏢' },
  { value: 'admin', label: 'ผู้ดูแลระบบ', icon: '🔑' },
]

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes rot{to{transform:rotate(360deg)}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .06s ease both}
.au2{animation:fadeUp .28s .12s ease both}
.au3{animation:fadeUp .28s .18s ease both}
.au4{animation:fadeUp .28s .24s ease both}
.au5{animation:fadeUp .28s .30s ease both}
`

const inputCls = `w-full border-2 border-blue-100 bg-blue-50/40 rounded-xl px-md py-md text-sm
  text-slate-800 outline-none focus:border-blue-700 focus:bg-white focus:ring-4
  focus:ring-blue-100 transition-all placeholder:text-slate-400`

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    username: '',
    first_name: '',
    email: '',
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

      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-20 -right-16 w-72 h-72 rounded-full bg-blue-200/40 blur-3xl" />
        <div className="absolute top-44 -left-24 w-80 h-80 rounded-full bg-indigo-200/30 blur-3xl" />
      </div>

      <div className="relative z-10 max-w-6xl mx-auto min-h-screen px-4 sm:px-6 lg:px-8 py-4 lg:py-6 flex items-center">
        <div className="grid w-full grid-cols-1 lg:grid-cols-[0.95fr_1.05fr] gap-5 lg:gap-6 items-stretch">
          <div className="hidden lg:flex flex-col justify-between rounded-[28px] border border-blue-100/80 bg-white/70 backdrop-blur-xl shadow-[0_24px_80px_rgba(37,99,235,0.10)] p-7 xl:p-8 au">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-bold tracking-[0.18em] text-blue-700 uppercase">
                <Sparkles size={12} />
                Create Account
              </div>
              <h1 className="mt-6 text-4xl font-extrabold text-slate-900 leading-tight">
                สมัครสมาชิก
                <span className="block text-blue-700">หน้าตาเดียวกับแดชบอร์ดที่ใช้งานจริง</span>
              </h1>
              <p className="mt-4 max-w-xl text-sm leading-7 text-slate-600">
                สร้างบัญชีผู้ใช้หรือผู้ดูแลระบบในฟอร์มที่ชัดเจน แยกเป็นขั้นตอน ลดความแน่น และคุมความสวยงามให้เหมือนหน้า Search
              </p>
            </div>

            <div className="grid grid-cols-3 gap-4">
              {[
                { label: 'ขั้นตอน', value: '2 หน้า' },
                { label: 'ฟอร์ม', value: 'อ่านง่าย' },
                { label: 'โทน UI', value: 'Premium' },
              ].map((item) => (
                <div key={item.label} className="rounded-2xl border border-blue-100 bg-white/80 p-4 shadow-sm">
                  <p className="text-xs font-semibold text-slate-500">{item.label}</p>
                  <p className="mt-2 text-xl font-extrabold text-slate-900">{item.value}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 rounded-[24px] border border-blue-100 bg-gradient-to-br from-blue-600 via-blue-600 to-indigo-600 p-6 text-white shadow-lg shadow-blue-200/40">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/15 border border-white/20">
                  <Building2 size={22} />
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-100">Booking System</p>
                  <p className="text-lg font-bold">ฟอร์มสมัครสมาชิกที่ดูเรียบร้อยและปลอดภัย</p>
                </div>
              </div>
              <div className="mt-5 flex items-center gap-3 text-sm text-blue-50">
                <ShieldCheck size={16} />
                รองรับผู้ใช้หลายบทบาทในดีไซน์เดียวกับหน้าหลัก
              </div>
            </div>
          </div>

          <div className="mx-auto w-full max-w-md lg:max-w-none">
            <div className="text-center mb-6 lg:hidden au">
              <div className="w-14 h-14 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-200">
                <UserPlus size={24} color="#fff" />
              </div>
              <h1 className="text-xl font-extrabold text-slate-900">สมัครสมาชิก</h1>
              <p className="text-slate-500 text-xs mt-1">สร้างบัญชีผู้ใช้งานหรือผู้ดูแลระบบ</p>
            </div>

            <div className="hidden lg:flex items-center gap-4 mb-6 au">
              <div className="w-14 h-14 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-200">
                <UserPlus size={24} color="#fff" />
              </div>
              <div>
                <h1 className="text-2xl font-extrabold text-slate-900">สมัครสมาชิก</h1>
                <p className="text-slate-500 text-sm mt-1">สร้างบัญชีผู้ใช้งานหรือผู้ดูแลระบบ</p>
              </div>
            </div>

            <div className="bg-white/90 backdrop-blur-xl border border-white/70 rounded-[28px] p-5 sm:p-6 shadow-[0_20px_80px_rgba(15,23,42,0.10)] au1">
              <div className="h-1 bg-gradient-to-r from-blue-500 via-indigo-500 to-blue-500 rounded-full mb-5" />

              <div className="flex items-center justify-between gap-4 mb-5">
                <div>
                  <p className="text-[11px] font-bold tracking-[0.22em] text-slate-400 uppercase">Register</p>
                  <p className="text-xl font-extrabold text-slate-900 mt-1">{step === 1 ? 'ข้อมูลผู้ใช้งาน' : 'ตั้งรหัสผ่าน'}</p>
                </div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-700 border border-blue-100">
                  <ShieldCheck size={20} />
                </div>
              </div>

              <div className="flex items-center gap-md mb-5">
                {[1, 2].map(s => (
                  <div key={s} className="flex items-center flex-1">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all
                      ${step >= s ? 'bg-blue-700 text-white shadow-md shadow-blue-200' : 'bg-blue-100 text-blue-300'}`}>
                      {s}
                    </div>
                    {s < 2 && <div className={`flex-1 h-0.5 mx-1.5 rounded-full transition-all ${step > s ? 'bg-blue-700' : 'bg-blue-100'}`} />}
                  </div>
                ))}
                <span className="text-xs text-slate-500 ml-2 flex-shrink-0">
                  {step === 1 ? 'ข้อมูลส่วนตัว' : 'ตั้งรหัสผ่าน'}
                </span>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-4 py-3 rounded-2xl mb-4">
                  {error}
                </div>
              )}

              {step === 1 && (
                <div className="space-y-4">
                  <div className="au2">
                    <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">ชื่อ-นามสกุล</label>
                    <input
                      type="text"
                      placeholder="ชื่อจริง - นามสกุล"
                      className={inputCls}
                      value={form.first_name}
                      onChange={e => set('first_name', e.target.value)}
                      style={{ fontFamily: 'inherit' }}
                    />
                  </div>
                  <div className="au2">
                    <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">ชื่อผู้ใช้</label>
                    <input
                      type="text"
                      placeholder="เช่น somchai123"
                      className={inputCls}
                      value={form.username}
                      onChange={e => set('username', e.target.value)}
                      style={{ fontFamily: 'inherit' }}
                    />
                  </div>
                  <div className="au3">
                    <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">อีเมล</label>
                    <input
                      type="email"
                      placeholder="example@ubu.ac.th"
                      className={inputCls}
                      value={form.email}
                      onChange={e => set('email', e.target.value)}
                      style={{ fontFamily: 'inherit' }}
                    />
                  </div>

                  <div className="au3">
                    <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">ประเภทผู้ใช้ (Role)</label>
                    <div className="group-gap">
                      {ROLES.map(r => (
                        <button
                          key={r.value}
                          type="button"
                          onClick={() => set('role', r.value)}
                          className={`py-3 px-2 rounded-2xl text-xs font-semibold border-2 transition-all text-center shadow-sm
                            ${form.role === r.value
                              ? 'border-blue-700 bg-blue-700 text-white shadow-blue-200'
                              : 'border-blue-100 bg-white text-slate-600 hover:border-blue-300 hover:bg-blue-50'
                            }`}
                        >
                          <div className="text-lg mb-0.5">{r.icon}</div>
                          {r.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="au4">
                    <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">คณะ / หน่วยงาน</label>
                    <select
                      className={inputCls}
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
                    className="au5 w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-2xl py-3.5 font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-200 transition-all active:scale-[0.99]"
                  >
                    ถัดไป <ChevronRight size={14} />
                  </button>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-4">
                  <div className="bg-blue-50 border border-blue-200 rounded-2xl px-4 py-3 au2">
                    <p className="font-bold text-slate-800 text-sm">{form.first_name}</p>
                    <p className="text-blue-500 text-xs mt-0.5">{form.role.toUpperCase()} · {form.faculty || '—'}</p>
                  </div>

                  <div className="au2">
                    <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">รหัสผ่าน</label>
                    <div className="relative">
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
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-600 transition-colors"
                      >
                        {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>

                  <div className="au3">
                    <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">ยืนยันรหัสผ่าน</label>
                    <div className="relative">
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
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-600 transition-colors"
                      >
                        {showPass2 ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    {form.password2 && form.password !== form.password2 && (
                      <p className="text-xs text-red-500 mt-1.5">รหัสผ่านไม่ตรงกัน</p>
                    )}
                  </div>

                  <div className="flex gap-2.5 au4">
                    <button
                      type="button"
                      onClick={() => { setStep(1); setError('') }}
                      className="flex-1 border-2 border-blue-100 text-slate-600 py-3 rounded-2xl font-semibold text-sm hover:bg-blue-50 transition-colors"
                    >
                      ← ย้อนกลับ
                    </button>
                    <button
                      type="button"
                      onClick={onSubmit}
                      disabled={loading}
                      className="flex-[2] bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:bg-slate-400 text-white py-3 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-200 disabled:shadow-none transition-all active:scale-[0.99] disabled:cursor-not-allowed"
                    >
                      {loading
                        ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full" style={{ animation: 'rot .7s linear infinite' }} />กำลังสมัคร...</>
                        : <><UserPlus size={14} />สมัครสมาชิก</>}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <p className="text-center text-sm text-slate-500 mt-5">
              มีบัญชีอยู่แล้ว?{' '}
              <Link to="/login" className="text-blue-700 font-bold hover:underline">เข้าสู่ระบบ</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
