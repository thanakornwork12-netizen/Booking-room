import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, LogIn } from 'lucide-react'
import { loginWithLDAP } from '../api/axios'

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes rot{to{transform:rotate(360deg)}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .07s ease both}
.au2{animation:fadeUp .28s .14s ease both}
.au3{animation:fadeUp .28s .21s ease both}
`

const inputCls = `w-full border-2 border-blue-100 bg-blue-50/40 rounded-xl px-4 py-3 text-sm
  text-slate-800 outline-none focus:border-blue-700 focus:bg-white focus:ring-4
  focus:ring-blue-100 transition-all placeholder:text-slate-400`

export default function LoginPage() {
  const navigate = useNavigate()
  const [form, setForm]         = useState({ username: '', password: '' })
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [showPass, setShowPass] = useState(false)

  const onSubmit = async () => {
    if (!form.username.trim() || !form.password) {
      setError('กรุณากรอกรหัสนักศึกษาและรหัสผ่าน')
      return
    }

    setLoading(true)
    setError('')

    try {
      // loginWithLDAP จัดการเก็บ token และข้อมูล user ให้อัตโนมัติ
      await loginWithLDAP(form.username.trim(), form.password)
      navigate('/')
    } catch (err) {
      const msg = err?.response?.data?.detail
             || err?.response?.data?.non_field_errors?.[0]
             || 'รหัสนักศึกษาหรือรหัสผ่านไม่ถูกต้อง'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen bg-blue-50 flex items-center justify-center px-4 py-10"
      style={{ fontFamily: "'Sarabun','Noto Sans Thai',sans-serif" }}
    >
      <style>{ANIM}</style>

      <div className="w-full max-w-sm">

        {/* LOGO BLOCK */}
        <div className="text-center mb-7 au">
          <div className="w-14 h-14 bg-blue-700 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-300">
            <LogIn size={24} color="#fff" />
          </div>
          <h1 className="text-xl font-extrabold text-slate-900">ระบบจองห้องประชุม</h1>
          <p className="text-slate-500 text-xs mt-1">มหาวิทยาลัยอุบลราชธานี</p>
        </div>

        {/* CARD */}
        <div className="bg-white border border-blue-100 rounded-3xl p-7 shadow-xl shadow-blue-100/60 au1">

          {/* yellow accent */}
          <div className="h-1 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-6" />

          <p className="text-base font-extrabold text-slate-900 mb-5">เข้าสู่ระบบ</p>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-4 py-3 rounded-xl mb-4">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div className="au2">
              <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">
                รหัสนักศึกษา
              </label>
              <input
                type="text"
                placeholder="เช่น 66114640275"
                value={form.username}
                onChange={e => setForm({ ...form, username: e.target.value })}
                onKeyDown={e => e.key === 'Enter' && onSubmit()}
                className={inputCls}
                style={{ fontFamily: 'inherit' }}
                autoComplete="username"
              />
            </div>

            <div className="au3">
              <label className="block text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">
                รหัสผ่าน
              </label>
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  placeholder="กรอกรหัสผ่าน"
                  value={form.password}
                  onChange={e => setForm({ ...form, password: e.target.value })}
                  onKeyDown={e => e.key === 'Enter' && onSubmit()}
                  className={`${inputCls} pr-11`}
                  style={{ fontFamily: 'inherit' }}
                  autoComplete="current-password"
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
          </div>

          <button
            onClick={onSubmit}
            disabled={loading}
            className="w-full mt-6 bg-blue-700 hover:bg-blue-800 disabled:bg-slate-400 text-white rounded-xl py-3.5 font-bold text-sm flex items-center justify-center gap-2.5 shadow-lg shadow-blue-200 disabled:shadow-none transition-all active:scale-95 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <div
                  className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full"
                  style={{ animation: 'rot .7s linear infinite' }}
                />
                กำลังเข้าสู่ระบบ...
              </>
            ) : (
              <>
                <LogIn size={15} />
                เข้าสู่ระบบ
              </>
            )}
          </button>
        </div>

        <p className="text-center text-sm text-slate-500 mt-5">
          ยังไม่มีบัญชี?{' '}
          <Link to="/register" className="text-blue-700 font-bold hover:underline">
            สมัครสมาชิก
          </Link>
        </p>
      </div>
    </div>
  )
}