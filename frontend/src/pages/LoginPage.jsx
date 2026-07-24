import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Eye, EyeOff, LogIn, Building2, ShieldCheck, Sparkles, Phone, Mail, Globe } from 'lucide-react'
import { loginWithLDAP } from '../api/axios'

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes rot{to{transform:rotate(360deg)}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .07s ease both}
.au2{animation:fadeUp .28s .14s ease both}
.au3{animation:fadeUp .28s .21s ease both}
`

const inputCls = `w-full border-2 border-blue-100 bg-blue-50/40 rounded-xl px-md py-md text-sm
  text-slate-800 outline-none focus:border-blue-700 focus:bg-white focus:ring-4
  focus:ring-blue-100 transition-all placeholder:text-slate-400`

const supportInfo = {
  organization: 'สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
  address: '85 ถ.สถลมาร์ค ต.เมืองศรีไค อ.วารินชำราบ จ.อุบลราชธานี 34190',
  phone: '045-353102',
  webmaster: '1502',
  email: 'ocn@ubu.ac.th',
  facebook: 'https://www.facebook.com/ocnfanpage/',
  copyright: 'สงวนลิขสิทธิ์ พ.ศ. 2556 ตามพระราชบัญญัติลิขสิทธิ์ 2537',
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [form, setForm]         = useState({ username: '', password: '' })
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [showPass, setShowPass] = useState(false)

  const onSubmit = async () => {
    if (!form.username.trim() || !form.password) {
      setError('กรุณากรอกชื่อผู้ใช้หรือรหัสนักศึกษาและรหัสผ่าน')
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
      className="w-full min-h-screen bg-[#F8FAFC] relative overflow-x-hidden overflow-y-auto"
      style={{ fontFamily: "'Inter','Prompt','Sarabun','Noto Sans Thai',sans-serif" }}
    >
      <style>{ANIM}</style>

      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-24 -right-20 w-72 h-72 rounded-full bg-blue-200/40 blur-3xl" />
        <div className="absolute top-36 -left-24 w-80 h-80 rounded-full bg-indigo-200/30 blur-3xl" />
      </div>

      <div className="relative z-10 max-w-6xl mx-auto min-h-screen px-4 sm:px-6 lg:px-8 py-4 lg:py-6 flex items-center">
        <div className="grid w-full grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-5 lg:gap-6 items-stretch">
          <div className="hidden lg:flex flex-col justify-between rounded-[28px] border border-blue-100/80 bg-white/70 backdrop-blur-xl shadow-[0_24px_80px_rgba(37,99,235,0.10)] p-7 xl:p-8 au">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-bold tracking-[0.18em] text-blue-700 uppercase">
                <Sparkles size={12} />
                Premium Meeting Room
              </div>
              <h1 className="mt-6 text-4xl font-extrabold text-slate-900 leading-tight">
                ระบบจองห้องประชุม
                <span className="block text-blue-700">ประสบการณ์ใช้งานที่เรียบง่ายและดูพรีเมียม</span>
              </h1>
              <p className="mt-4 max-w-xl text-sm leading-7 text-slate-600">
                เข้าสู่ระบบเพื่อค้นหาห้องว่าง ตรวจสอบเวลา และจัดการการจองในหน้าตาเดียวกับแดชบอร์ดหลัก
                ใช้โทน UI ที่สะอาด โปร่ง และอ่านง่ายเหมือนหน้า Search ที่คุณชอบ
              </p>
            </div>

            <div className="grid grid-cols-3 gap-4">
              {[
                { label: 'ค้นหาเร็ว', value: '1 หน้า' },
                { label: 'ใช้งานลื่น', value: '0 ทับกัน' },
                { label: 'ปลอดภัย', value: 'LDAP' },
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
                  <p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-100">Meeting Room</p>
                  <p className="text-lg font-bold">ค้นหา จอง และยืนยันได้ต่อเนื่อง</p>
                </div>
              </div>
              <div className="mt-5 flex items-center gap-3 text-sm text-blue-50">
                <ShieldCheck size={16} />
                หน้าล็อกอินดีไซน์เดียวกับหน้าใช้งานหลัก
              </div>
            </div>
          </div>

          <div className="mx-auto w-full max-w-md lg:max-w-none">
            <div className="text-center mb-6 lg:hidden au">
              <div className="w-14 h-14 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-200">
                <LogIn size={24} color="#fff" />
              </div>
              <h1 className="text-xl font-extrabold text-slate-900">ระบบจองห้องประชุม</h1>
              <p className="text-slate-500 text-xs mt-1">มหาวิทยาลัยอุบลราชธานี</p>
            </div>

            {/* LOGO BLOCK */}
            <div className="hidden lg:flex items-center gap-4 mb-6 au">
              <div className="w-14 h-14 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-200">
                <LogIn size={24} color="#fff" />
              </div>
              <div>
                <h1 className="text-2xl font-extrabold text-slate-900">ระบบจองห้องประชุม</h1>
                <p className="text-slate-500 text-sm mt-1">มหาวิทยาลัยอุบลราชธานี</p>
              </div>
            </div>

            {/* CARD */}
            <div className="bg-white/90 backdrop-blur-xl border border-white/70 rounded-[28px] p-5 sm:p-6 shadow-[0_20px_80px_rgba(15,23,42,0.10)] au1">
              <div className="h-1 bg-gradient-to-r from-blue-500 via-indigo-500 to-blue-500 rounded-full mb-6" />

              <div className="flex items-start justify-between gap-4 mb-5">
                <div>
                  <p className="text-[11px] font-bold tracking-[0.22em] text-slate-400 uppercase">Sign in</p>
                  <p className="text-xl font-extrabold text-slate-900 mt-1">เข้าสู่ระบบ</p>
                </div>
                <div className="hidden sm:flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-700 border border-blue-100">
                  <ShieldCheck size={20} />
                </div>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-md py-md rounded-2xl mb-4">
                  {error}
                </div>
              )}

              <div className="space-y-4">
                <div className="au2">
                  <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">
                    ชื่อผู้ใช้ / รหัสนักศึกษา
                  </label>
                  <input
                    type="text"
                    placeholder="เช่น somchai123 หรือ 66114640275"
                    value={form.username}
                    onChange={e => setForm({ ...form, username: e.target.value })}
                    onKeyDown={e => e.key === 'Enter' && onSubmit()}
                    className={inputCls}
                    style={{ fontFamily: 'inherit' }}
                    autoComplete="username"
                  />
                </div>

                <div className="au3">
                  <label className="block text-xs font-bold text-blue-700 uppercase tracking-widest mb-2">
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
                className="w-full mt-6 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:bg-slate-400 text-white rounded-2xl py-3.5 font-bold text-sm flex items-center justify-center gap-md shadow-lg shadow-blue-200 disabled:shadow-none transition-all active:scale-[0.99] disabled:cursor-not-allowed"
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

        <div className="mt-5 rounded-[24px] border border-blue-100 bg-white/80 p-4 shadow-sm au2">
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-blue-700">ติดต่อผู้ดูแลระบบ</p>
          <p className="mt-2 text-sm font-semibold text-slate-900">{supportInfo.organization}</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{supportInfo.address}</p>
          <div className="mt-3 grid gap-2 text-sm text-slate-700">
            <p className="flex items-center gap-2"><Phone size={15} className="text-blue-600" /> โทร. {supportInfo.phone}</p>
            <p className="flex items-center gap-2"><Mail size={15} className="text-blue-600" /> webmaster {supportInfo.webmaster}</p>
            <p className="flex items-center gap-2"><Mail size={15} className="text-blue-600" /> {supportInfo.email}</p>
            <a href={supportInfo.facebook} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-blue-700 hover:underline">
              <Globe size={15} className="text-blue-600" />
              OCNfanpage
            </a>
          </div>
        </div>

        <div className="mt-4 text-center text-[11px] leading-5 text-slate-500 au3">
          <p>{supportInfo.copyright}</p>
        </div>
      </div>
    </div>
  )
}
