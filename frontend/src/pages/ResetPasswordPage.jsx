import { useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { Eye, EyeOff, Lock, ArrowRight, KeyRound } from 'lucide-react'
import api from '../api/axios'

const inputCls = `w-full rounded-2xl border border-slate-200 bg-slate-50 pl-11 pr-11 py-3 text-sm
  text-slate-800 outline-none transition-all placeholder:text-slate-400
  focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100`

export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const { uid, token } = useParams()
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const onSubmit = async () => {
    if (!password || !password2) return setError('กรุณากรอกรหัสผ่านใหม่ให้ครบ')
    if (password !== password2) return setError('รหัสผ่านไม่ตรงกัน')
    if (password.length < 6) return setError('รหัสผ่านต้องมีอย่างน้อย 6 ตัว')

    setLoading(true)
    setError('')
    try {
      await api.post('/auth/reset-password-confirm/', { uid, token, password, password2 })
      setSuccess(true)
      setTimeout(() => navigate('/login'), 2500)
    } catch (err) {
      setError(err?.response?.data?.error || 'ลิงก์รีเซ็ตรหัสผ่านไม่ถูกต้องหรือหมดอายุแล้ว')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-slate-50 px-6 py-10">
      <div className="w-full max-w-sm rounded-3xl border border-slate-100 bg-white p-7 shadow-lg shadow-blue-100/40">
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
          <KeyRound size={22} />
        </div>
        <h1 className="text-xl font-extrabold text-slate-900">ตั้งรหัสผ่านใหม่</h1>
        <p className="mt-1 text-sm text-slate-500">กรอกรหัสผ่านใหม่สำหรับบัญชีของคุณ</p>

        {success ? (
          <div className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            ตั้งรหัสผ่านใหม่สำเร็จ กำลังพาไปหน้าเข้าสู่ระบบ...
          </div>
        ) : (
          <>
            {error && (
              <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                {error}
              </div>
            )}
            <div className="mt-4">
              <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">รหัสผ่านใหม่</label>
              <div className="relative">
                <Lock size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type={showPass ? 'text' : 'password'}
                  placeholder="อย่างน้อย 6 ตัวอักษร"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className={inputCls}
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
            <div className="mt-3.5">
              <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-blue-700">ยืนยันรหัสผ่านใหม่</label>
              <div className="relative">
                <Lock size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type={showPass ? 'text' : 'password'}
                  placeholder="กรอกรหัสผ่านใหม่อีกครั้ง"
                  value={password2}
                  onChange={e => setPassword2(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && onSubmit()}
                  className={inputCls}
                />
              </div>
            </div>

            <button
              onClick={onSubmit}
              disabled={loading}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 py-3.5 text-sm font-bold text-white shadow-sm transition-all hover:bg-blue-800 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {loading ? 'กำลังบันทึก...' : <>ตั้งรหัสผ่านใหม่ <ArrowRight size={15} /></>}
            </button>
          </>
        )}

        <p className="mt-5 text-center text-sm text-slate-500">
          <Link to="/login" className="font-bold text-blue-700 hover:underline">กลับไปหน้าเข้าสู่ระบบ</Link>
        </p>
      </div>
    </div>
  )
}
