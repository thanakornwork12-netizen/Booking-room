import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, LogIn } from 'lucide-react'
import api from '../api/axios'

export default function LoginPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass, setShowPass] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await api.post('/auth/login/', form)
      localStorage.setItem('access_token', res.data.access)
localStorage.setItem('refresh_token', res.data.refresh)
const profile = await api.get('/auth/profile/')
localStorage.setItem('user', JSON.stringify(profile.data))
      navigate('/')
    } catch {
      setError('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo / Title */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
            <LogIn size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-800">ระบบจองห้องประชุม</h1>
          <p className="text-gray-500 text-sm mt-1">เข้าสู่ระบบเพื่อดำเนินการต่อ</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-3xl shadow-xl p-7 space-y-4">

          {error && (
            <div className="bg-red-50 border border-red-100 text-red-600 text-sm px-4 py-3 rounded-xl">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">ชื่อผู้ใช้</label>
            <input
              type="text"
              placeholder="กรอกชื่อผู้ใช้"
              className="w-full border border-gray-200 bg-gray-50 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white transition-colors"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">รหัสผ่าน</label>
            <div className="relative">
              <input
                type={showPass ? 'text' : 'password'}
                placeholder="กรอกรหัสผ่าน"
                className="w-full border border-gray-200 bg-gray-50 rounded-xl px-4 py-2.5 pr-11 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white transition-colors"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
              />
              <button type="button" onClick={() => setShowPass(!showPass)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showPass ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
          </div>

          <button
            type="button"
            disabled={loading}
            onClick={handleSubmit}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2.5 rounded-xl font-medium text-sm transition-colors shadow-sm mt-2">
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                กำลังเข้าสู่ระบบ...
              </span>
            ) : 'เข้าสู่ระบบ'}
          </button>
        </div>

        <p className="text-center text-sm text-gray-500 mt-5">
          ยังไม่มีบัญชี?{' '}
          <Link to="/register" className="text-blue-600 font-medium hover:underline">สมัครสมาชิก</Link>
        </p>

      </div>
    </div>
  )
}