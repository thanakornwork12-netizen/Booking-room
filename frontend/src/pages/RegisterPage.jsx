import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, UserPlus } from 'lucide-react'
import api from '../api/axios'

const FACULTIES = [
  'วิทยาศาสตร์', 'วิศวกรรมศาสตร์', 'บริหารธุรกิจ',
  'นิติศาสตร์', 'แพทยศาสตร์', 'พยาบาลศาสตร์',
  'เกษตรศาสตร์', 'ศิลปศาสตร์', 'สาธารณสุขศาสตร์', 'เภสัชศาสตร์',
]

const ROLES = [
  { value: 'student',  label: '🎓 นักศึกษา' },
  { value: 'lecturer', label: '👨‍🏫 อาจารย์' },
  { value: 'staff',    label: '🏢 เจ้าหน้าที่' },
]

const inputClass = "w-full border border-gray-200 bg-gray-50 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white transition-colors"

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    username: '', first_name: '', email: '',
    password: '', password2: '', role: 'student', faculty: ''
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [showPass2, setShowPass2] = useState(false)
  const [step, setStep] = useState(1)

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const nextStep = () => {
    if (!form.first_name) return setError('กรุณากรอกชื่อ-นามสกุล')
    if (!form.username)   return setError('กรุณากรอกชื่อผู้ใช้')
    if (!form.email)      return setError('กรุณากรอกอีเมล')
    setError('')
    setStep(2)
  }

  const handleSubmit = async () => {
    if (!form.faculty)                        return setError('กรุณาเลือกคณะ/หน่วยงาน')
    if (!form.password)                       return setError('กรุณากรอกรหัสผ่าน')
    if (form.password !== form.password2)     return setError('รหัสผ่านไม่ตรงกัน')
    if (form.password.length < 6)             return setError('รหัสผ่านต้องมีอย่างน้อย 6 ตัว')
    setLoading(true)
    setError('')
    try {
      await api.post('/auth/register/', form)
      navigate('/login')
    } catch {
      setError('สมัครสมาชิกไม่สำเร็จ กรุณาตรวจสอบข้อมูล')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">

        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
            <UserPlus size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-800">สมัครสมาชิก</h1>
          <p className="text-gray-500 text-sm mt-1">สร้างบัญชีเพื่อเริ่มจองห้อง</p>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center gap-2 mb-6">
          {[1, 2].map(s => (
            <div key={s} className="flex items-center flex-1">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors
                ${step >= s ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-400'}`}>
                {s}
              </div>
              {s < 2 && <div className={`flex-1 h-0.5 mx-1 ${step > s ? 'bg-blue-400' : 'bg-gray-200'}`} />}
            </div>
          ))}
          <span className="text-xs text-gray-400 ml-1">
            {step === 1 ? 'ข้อมูลส่วนตัว' : 'ความปลอดภัย'}
          </span>
        </div>

        {/* Card */}
        <div className="bg-white rounded-3xl shadow-xl p-7 space-y-4">

          {error && (
            <div className="bg-red-50 border border-red-100 text-red-600 text-sm px-4 py-3 rounded-xl">
              {error}
            </div>
          )}

          {/* Step 1 — ข้อมูลส่วนตัว */}
          {step === 1 && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">ชื่อ-นามสกุล</label>
                <input type="text" placeholder="เช่น สมชาย ใจดี" className={inputClass}
                  value={form.first_name} onChange={e => set('first_name', e.target.value)} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">ชื่อผู้ใช้</label>
                <input type="text" placeholder="เช่น somchai123" className={inputClass}
                  value={form.username} onChange={e => set('username', e.target.value)} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">อีเมล</label>
                <input type="email" placeholder="example@ubu.ac.th" className={inputClass}
                  value={form.email} onChange={e => set('email', e.target.value)} />
              </div>

              {/* Role Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">ประเภทผู้ใช้</label>
                <div className="grid grid-cols-3 gap-2">
                  {ROLES.map(r => (
                    <button key={r.value} type="button" onClick={() => set('role', r.value)}
                      className={`py-2.5 px-2 rounded-xl text-xs font-medium border-2 transition-all text-center
                        ${form.role === r.value
                          ? 'border-blue-500 bg-blue-50 text-blue-700'
                          : 'border-gray-100 bg-gray-50 text-gray-600 hover:border-gray-200'}`}>
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Faculty */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">คณะ/หน่วยงาน</label>
                <select className={inputClass} value={form.faculty} onChange={e => set('faculty', e.target.value)}>
                  <option value="">-- เลือกคณะ --</option>
                  {FACULTIES.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>

              <button type="button" onClick={nextStep}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2.5 rounded-xl font-medium text-sm transition-colors mt-1">
                ถัดไป →
              </button>
            </>
          )}

          {/* Step 2 — รหัสผ่าน */}
          {step === 2 && (
            <>
              {/* สรุปข้อมูล */}
              <div className="bg-blue-50 rounded-xl px-4 py-3 text-sm">
                <p className="font-medium text-blue-800">{form.first_name}</p>
                <p className="text-blue-500 text-xs mt-0.5">{form.email} • {form.faculty}</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">รหัสผ่าน</label>
                <div className="relative">
                  <input type={showPass ? 'text' : 'password'} placeholder="อย่างน้อย 6 ตัวอักษร"
                    className={`${inputClass} pr-11`}
                    value={form.password} onChange={e => set('password', e.target.value)} />
                  <button type="button" onClick={() => setShowPass(!showPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                    {showPass ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">ยืนยันรหัสผ่าน</label>
                <div className="relative">
                  <input type={showPass2 ? 'text' : 'password'} placeholder="กรอกรหัสผ่านอีกครั้ง"
                    className={`${inputClass} pr-11 ${form.password2 && form.password !== form.password2 ? 'ring-2 ring-red-300' : ''}`}
                    value={form.password2} onChange={e => set('password2', e.target.value)} />
                  <button type="button" onClick={() => setShowPass2(!showPass2)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                    {showPass2 ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
                {form.password2 && form.password !== form.password2 && (
                  <p className="text-xs text-red-500 mt-1">รหัสผ่านไม่ตรงกัน</p>
                )}
              </div>

              <div className="flex gap-2 mt-1">
                <button type="button" onClick={() => { setStep(1); setError('') }}
                  className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-xl font-medium text-sm hover:bg-gray-50 transition-colors">
                  ← ย้อนกลับ
                </button>
                <button type="button" onClick={handleSubmit} disabled={loading}
                  className="flex-2 flex-grow bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2.5 rounded-xl font-medium text-sm transition-colors">
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      กำลังสมัคร...
                    </span>
                  ) : 'สมัครสมาชิก'}
                </button>
              </div>
            </>
          )}
        </div>

        <p className="text-center text-sm text-gray-500 mt-5">
          มีบัญชีแล้ว?{' '}
          <Link to="/login" className="text-blue-600 font-medium hover:underline">เข้าสู่ระบบ</Link>
        </p>

      </div>
    </div>
  )
}