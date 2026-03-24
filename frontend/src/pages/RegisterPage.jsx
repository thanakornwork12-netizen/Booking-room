import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, UserPlus, ChevronRight } from 'lucide-react'
import api from '../api/axios'

const FACULTIES = [
  'วิทยาศาสตร์','วิศวกรรมศาสตร์','บริหารธุรกิจ',
  'นิติศาสตร์','แพทยศาสตร์','พยาบาลศาสตร์',
  'เกษตรศาสตร์','ศิลปศาสตร์','สาธารณสุขศาสตร์','เภสัชศาสตร์',
]
const ROLES = [
  {value:'student',  label:'นักศึกษา',    icon:'🎓'},
  {value:'lecturer', label:'อาจารย์',     icon:'👨‍🏫'},
  
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

const inputCls = `w-full border-2 border-blue-100 bg-blue-50/40 rounded-xl px-4 py-2.5 text-sm
  text-slate-800 outline-none focus:border-blue-700 focus:bg-white focus:ring-4
  focus:ring-blue-100 transition-all placeholder:text-slate-400`

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    username:'', first_name:'', email:'',
    password:'', password2:'', role:'student', faculty:''
  })
  const [error, setError]     = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass,  setShowPass]  = useState(false)
  const [showPass2, setShowPass2] = useState(false)
  const [step, setStep] = useState(1)

  const set = (k, v) => setForm(f => ({...f, [k]: v}))

  const goNext = () => {
    if (!form.first_name) return setError('กรุณากรอกชื่อ-นามสกุล')
    if (!form.username)   return setError('กรุณากรอกชื่อผู้ใช้')
    if (!form.email)      return setError('กรุณากรอกอีเมล')
    setError(''); setStep(2)
  }

  const onSubmit = async () => {
    if (!form.faculty)                    return setError('กรุณาเลือกคณะ/หน่วยงาน')
    if (!form.password)                   return setError('กรุณากรอกรหัสผ่าน')
    if (form.password !== form.password2) return setError('รหัสผ่านไม่ตรงกัน')
    if (form.password.length < 6)         return setError('รหัสผ่านต้องมีอย่างน้อย 6 ตัว')
    setLoading(true); setError('')
    try { await api.post('/auth/register/', form); navigate('/login') }
    catch { setError('สมัครสมาชิกไม่สำเร็จ กรุณาตรวจสอบข้อมูล') }
    finally { setLoading(false) }
  }

  return (
    <div className="min-h-screen bg-blue-50 flex items-center justify-center px-4 py-10"
      style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>

      <div className="w-full max-w-sm">

        {/* LOGO BLOCK */}
        <div className="text-center mb-7 au">
          <div className="w-14 h-14 bg-blue-700 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-300">
            <UserPlus size={24} color="#fff" />
          </div>
          <h1 className="text-xl font-extrabold text-slate-900">สมัครสมาชิก</h1>
          <p className="text-slate-500 text-xs mt-1">สร้างบัญชีเพื่อเริ่มจองห้องประชุม</p>
        </div>

        {/* CARD */}
        <div className="bg-white border border-blue-100 rounded-3xl p-7 shadow-xl shadow-blue-100/60 au1">

          {/* yellow accent */}
          <div className="h-1 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-5" />

          {/* STEP INDICATOR */}
          <div className="flex items-center gap-2 mb-5">
            {[1,2].map(s => (
              <div key={s} className="flex items-center flex-1">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all
                  ${step >= s ? 'bg-blue-700 text-white shadow-md shadow-blue-200' : 'bg-blue-100 text-blue-300'}`}>
                  {s}
                </div>
                {s < 2 && <div className={`flex-1 h-0.5 mx-1.5 rounded-full transition-all ${step > s ? 'bg-blue-700' : 'bg-blue-100'}`}/>}
              </div>
            ))}
            <span className="text-xs text-slate-500 ml-2 flex-shrink-0">
              {step === 1 ? 'ข้อมูลส่วนตัว' : 'ตั้งรหัสผ่าน'}
            </span>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-4 py-3 rounded-xl mb-4">
              {error}
            </div>
          )}

          {/* ── STEP 1 ── */}
          {step === 1 && (
            <div className="space-y-4">
              <div className="au2">
                <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">ชื่อ-นามสกุล</label>
                <input type="text" placeholder="ขื่อจริง - นามสกุล" className={inputCls}
                  value={form.first_name} onChange={e => set('first_name', e.target.value)}
                  style={{fontFamily:"inherit"}} />
              </div>
              <div className="au2">
                <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">ชื่อผู้ใช้</label>
                <input type="text" placeholder="เช่น somchai123" className={inputCls}
                  value={form.username} onChange={e => set('username', e.target.value)}
                  style={{fontFamily:"inherit"}} />
              </div>
              <div className="au3">
                <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">อีเมล</label>
                <input type="email" placeholder="example@ubu.ac.th" className={inputCls}
                  value={form.email} onChange={e => set('email', e.target.value)}
                  style={{fontFamily:"inherit"}} />
              </div>
              <div className="au3">
                <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">ประเภทผู้ใช้</label>
                <div className="grid grid-cols-3 gap-2">
                  {ROLES.map(r => (
                    <button key={r.value} type="button" onClick={() => set('role', r.value)}
                      className={`py-3 px-2 rounded-xl text-xs font-semibold border-2 transition-all text-center
                        ${form.role === r.value
                          ? 'border-blue-700 bg-blue-700 text-white shadow-sm'
                          : 'border-blue-100 bg-white text-slate-600 hover:border-blue-300 hover:bg-blue-50'
                        }`}>
                      <div className="text-base mb-1">{r.icon}</div>
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="au4">
                <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">คณะ / หน่วยงาน</label>
                <select className={inputCls} value={form.faculty}
                  onChange={e => set('faculty', e.target.value)}
                  style={{fontFamily:"inherit"}}>
                  <option value="">-- เลือกคณะ --</option>
                  {FACULTIES.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
              <button type="button" onClick={goNext}
                className="au5 w-full bg-blue-700 hover:bg-blue-800 text-white rounded-xl py-3.5 font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-200 transition-all active:scale-95">
                ถัดไป <ChevronRight size={14}/>
              </button>
            </div>
          )}

          {/* ── STEP 2 ── */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 au2">
                <p className="font-bold text-slate-800 text-sm">{form.first_name}</p>
                <p className="text-blue-500 text-xs mt-0.5">{form.email} · {form.faculty || '—'}</p>
              </div>
              <div className="au2">
                <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">รหัสผ่าน</label>
                <div className="relative">
                  <input type={showPass ? 'text' : 'password'} placeholder="อย่างน้อย 6 ตัวอักษร"
                    className={`${inputCls} pr-11`}
                    value={form.password} onChange={e => set('password', e.target.value)}
                    style={{fontFamily:"inherit"}} />
                  <button type="button" onClick={() => setShowPass(!showPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-600 transition-colors">
                    {showPass ? <EyeOff size={16}/> : <Eye size={16}/>}
                  </button>
                </div>
              </div>
              <div className="au3">
                <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">ยืนยันรหัสผ่าน</label>
                <div className="relative">
                  <input type={showPass2 ? 'text' : 'password'} placeholder="กรอกรหัสผ่านอีกครั้ง"
                    className={`${inputCls} pr-11 ${form.password2 && form.password !== form.password2 ? 'border-red-300 ring-2 ring-red-100' : ''}`}
                    value={form.password2} onChange={e => set('password2', e.target.value)}
                    style={{fontFamily:"inherit"}} />
                  <button type="button" onClick={() => setShowPass2(!showPass2)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-600 transition-colors">
                    {showPass2 ? <EyeOff size={16}/> : <Eye size={16}/>}
                  </button>
                </div>
                {form.password2 && form.password !== form.password2 && (
                  <p className="text-xs text-red-500 mt-1.5">รหัสผ่านไม่ตรงกัน</p>
                )}
              </div>
              <div className="flex gap-2.5 au4">
                <button type="button" onClick={() => { setStep(1); setError('') }}
                  className="flex-1 border-2 border-blue-100 text-slate-600 py-3 rounded-xl font-semibold text-sm hover:bg-blue-50 transition-colors">
                  ← ย้อนกลับ
                </button>
                <button type="button" onClick={onSubmit} disabled={loading}
                  className="flex-[2] bg-blue-700 hover:bg-blue-800 disabled:bg-slate-400 text-white py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-200 disabled:shadow-none transition-all active:scale-95 disabled:cursor-not-allowed">
                  {loading
                    ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full" style={{animation:'rot .7s linear infinite'}}/>กำลังสมัคร...</>
                    : <><UserPlus size={14}/>สมัครสมาชิก</>}
                </button>
              </div>
            </div>
          )}
        </div>

        <p className="text-center text-sm text-slate-500 mt-5">
          {step === 1
            ? <> มีบัญชีแล้ว?{' '}<Link to="/login" className="text-blue-700 font-bold hover:underline">เข้าสู่ระบบ</Link></>
            : <> มีบัญชีแล้ว?{' '}<Link to="/login" className="text-blue-700 font-bold hover:underline">เข้าสู่ระบบ</Link></>}
        </p>
      </div>
    </div>
  )
}