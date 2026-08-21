import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  CalendarDays,
  ChevronLeft,
  AlertTriangle,
  Bell,
  BookOpen,
  KeyRound,
  Loader2,
  Menu,
  Search,
  LayoutDashboard,
  Home,
  UserCircle2,
  Settings2,
  LogOut,
  Building2,
  Trash2,
  Phone,
  Mail,
  Globe,
  ExternalLink,
  MessageSquareMore,
} from 'lucide-react'
import api, { changePassword, deleteAccount, logout, getAccessToken, WS_BASE_URL } from '../api/axios'

const navItems = [
  { to: '/home', label: 'หน้าหลัก', icon: Home, exact: true },
  { to: '/search', label: 'จองห้องประชุม', icon: Search },
  { to: '/admin/dashboard', label: 'แดชบอร์ด', icon: LayoutDashboard },
]

const getUser = () => {
  try {
    return JSON.parse(localStorage.getItem('user') || sessionStorage.getItem('user') || '{}')
  } catch {
    return {}
  }
}

const roleLabels = {
  admin: 'ผู้ดูแลระบบ',
  staff: 'เจ้าหน้าที่',
  lecturer: 'อาจารย์',
  student: 'นักศึกษา',
}

const normalizeDisplayName = (values) => {
  const candidates = Array.isArray(values) ? values : [values]
  const titlePattern = /^(นาย|นางสาว|นาง|ว่าที่ร้อยตรี|ว่าที่ร\.ต\.|ดร\.|ผศ\.|รศ\.|ศ\.)\s*/i
  const thaiNamePattern = /[\u0E00-\u0E7F]+(?:\s+[\u0E00-\u0E7F]+)*/
  const blockedLabels = new Set(['student', 'user', 'guest', 'member', 'staff'])

  for (const value of candidates) {
    const raw = String(value || '').trim().replace(/\s+/g, ' ')
    if (!raw) continue

    const stripped = raw.replace(titlePattern, '').trim()
    const thaiMatch = stripped.match(thaiNamePattern)?.[0]?.trim()
    if (thaiMatch) {
      return thaiMatch.split(/\s+/)[0]
    }

    const token = stripped.split(/\s+/)[0] || ''
    if (!token) continue

    const lower = token.toLowerCase()
    const looksLikeEnglishLabel = /^[a-z0-9._-]+$/i.test(token)
    if (blockedLabels.has(lower) || looksLikeEnglishLabel) continue

    return token
  }

  return 'ผู้ใช้ระบบ'
}

const supportInfo = {
  organization: 'สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
  address: '85 ถ.สถลมาร์ค ต.เมืองศรีไค อ.วารินชำราบ จ.อุบลราชธานี 34190',
  phone: '045-353102',
  webmaster: '1502',
  email: 'ocn@ubu.ac.th',
  facebook: 'https://www.facebook.com/odlfanpage',
  copyright: 'สงวนลิขสิทธิ์ พ.ศ. 2556 ตามพระราชบัญญัติลิขสิทธิ์ 2537',
}

function SettingsModal({ open, onClose, user }) {
  const [activeTab, setActiveTab] = useState('password')
  const [passwordForm, setPasswordForm] = useState({
    old_password: '',
    new_password: '',
    new_password2: '',
  })
  const [deleteForm, setDeleteForm] = useState({
    confirm_username: '',
    confirm_text: '',
    password: '',
  })
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ type: '', text: '' })

  useEffect(() => {
    if (!open) return
    setActiveTab('password')
    setPasswordForm({
      old_password: '',
      new_password: '',
      new_password2: '',
    })
    setDeleteForm({
      confirm_username: user?.username || '',
      confirm_text: '',
      password: '',
    })
    setLoading(false)
    setMessage({ type: '', text: '' })
  }, [open, user?.username])

  if (!open) return null

  const getErrorText = (error, fallback) => {
    const data = error?.response?.data
    if (!data) return fallback
    if (typeof data === 'string') return data
    if (data.detail) return data.detail
    const firstKey = Object.keys(data)[0]
    const firstValue = data[firstKey]
    if (Array.isArray(firstValue)) return firstValue[0]
    if (typeof firstValue === 'string') return firstValue
    return fallback
  }

  const submitChangePassword = async (event) => {
    event.preventDefault()
    setLoading(true)
    setMessage({ type: '', text: '' })

    try {
      const res = await changePassword(passwordForm)
      setMessage({ type: 'success', text: res?.detail || 'เปลี่ยนรหัสผ่านสำเร็จ' })
      setPasswordForm({
        old_password: '',
        new_password: '',
        new_password2: '',
      })
    } catch (error) {
      setMessage({
        type: 'error',
        text: getErrorText(error, 'เปลี่ยนรหัสผ่านไม่สำเร็จ'),
      })
    } finally {
      setLoading(false)
    }
  }

  const submitDeleteAccount = async (event) => {
    event.preventDefault()
    setLoading(true)
    setMessage({ type: '', text: '' })

    try {
      const res = await deleteAccount(deleteForm)
      setMessage({ type: 'success', text: res?.detail || 'ลบบัญชีสำเร็จ' })
      logout()
    } catch (error) {
      setMessage({
        type: 'error',
        text: getErrorText(error, 'ลบบัญชีไม่สำเร็จ'),
      })
      setLoading(false)
    }
  }

  const note = 'แนะนำให้ใช้รหัสผ่านที่เดายากและไม่ซ้ำกับบัญชีอื่น'

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-950/55 p-0 backdrop-blur-sm sm:items-center sm:p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full overflow-hidden rounded-t-[28px] border border-white/20 bg-white shadow-[0_30px_120px_rgba(15,23,42,0.28)] sm:max-w-2xl sm:rounded-[28px]">
        <div className="bg-gradient-to-r from-blue-700 via-blue-700 to-indigo-700 px-5 py-5 text-white sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-blue-100/80">Settings mode</p>
              <h2 className="mt-1 text-2xl font-extrabold leading-tight">โหมดตั้งค่า</h2>
              <p className="mt-1 text-sm text-blue-50/90">จัดการรหัสผ่านและลบบัญชีของคุณในที่เดียว</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-white/10 text-white transition-colors hover:bg-white/20"
              aria-label="Close settings"
            >
              <ChevronLeft size={18} />
            </button>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold text-white/90">
              {user?.username || 'unknown'}
            </span>
            <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold text-white/90">
              {roleLabels[user?.role] || user?.role || 'ผู้ใช้ระบบ'}
            </span>
          </div>
        </div>

        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 sm:px-6">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setActiveTab('password')}
              className={`flex-1 rounded-2xl px-4 py-3 text-sm font-bold transition-all ${
                activeTab === 'password'
                  ? 'bg-white text-blue-700 shadow-sm'
                  : 'bg-transparent text-slate-500 hover:bg-white/70 hover:text-slate-800'
              }`}
            >
              เปลี่ยนรหัสผ่าน
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('delete')}
              className={`flex-1 rounded-2xl px-4 py-3 text-sm font-bold transition-all ${
                activeTab === 'delete'
                  ? 'bg-white text-red-600 shadow-sm'
                  : 'bg-transparent text-slate-500 hover:bg-white/70 hover:text-slate-800'
              }`}
            >
              ลบบัญชี
            </button>
          </div>
        </div>

        <div className="max-h-[78vh] overflow-y-auto p-4 sm:p-6">
          {message.text && (
            <div
              className={`mb-4 rounded-2xl border px-4 py-3 text-sm ${
                message.type === 'success'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-red-200 bg-red-50 text-red-700'
              }`}
            >
              {message.text}
            </div>
          )}

          {activeTab === 'password' && (
            <form onSubmit={submitChangePassword} className="grid gap-4">
              <div className="rounded-[24px] border border-blue-100 bg-blue-50/60 p-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-blue-700 text-white">
                    <KeyRound size={18} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-slate-900">เปลี่ยนรหัสผ่าน</p>
                    <p className="mt-1 text-xs leading-6 text-slate-600">{note}</p>
                  </div>
                </div>
              </div>

              <label className="grid gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.22em] text-slate-500">รหัสผ่านเดิม</span>
                <input
                  type="password"
                  value={passwordForm.old_password}
                  onChange={e => setPasswordForm(prev => ({ ...prev, old_password: e.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                  placeholder="กรอกรหัสผ่านเดิม"
                />
              </label>

              <label className="grid gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.22em] text-slate-500">รหัสผ่านใหม่</span>
                <input
                  type="password"
                  value={passwordForm.new_password}
                  onChange={e => setPasswordForm(prev => ({ ...prev, new_password: e.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                  placeholder="อย่างน้อย 6 ตัวอักษร"
                />
              </label>

              <label className="grid gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.22em] text-slate-500">ยืนยันรหัสผ่านใหม่</span>
                <input
                  type="password"
                  value={passwordForm.new_password2}
                  onChange={e => setPasswordForm(prev => ({ ...prev, new_password2: e.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                  placeholder="พิมพ์รหัสผ่านใหม่อีกครั้ง"
                />
              </label>

              <div className="flex items-center justify-between gap-3 pt-1">
                <p className="text-xs leading-6 text-slate-500">
                  แนะนำให้ใช้รหัสผ่านที่เดายากและไม่ซ้ำกับบัญชีอื่น
                </p>
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-700 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-blue-200 transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />}
                  บันทึกรหัสผ่าน
                </button>
              </div>
            </form>
          )}

          {activeTab === 'delete' && (
            <form onSubmit={submitDeleteAccount} className="grid gap-4">
              <div className="rounded-[24px] border border-red-100 bg-red-50/70 p-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-red-600 text-white">
                    <Trash2 size={18} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-slate-900">ลบบัญชีผู้ใช้</p>
                    <p className="mt-1 text-xs leading-6 text-slate-600">
                      การลบบัญชีจะลบข้อมูลผู้ใช้และข้อมูลที่เกี่ยวข้องตามสิทธิ์ของระบบทันที และไม่สามารถกู้คืนได้
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-[24px] border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-800">
                <div className="flex items-start gap-2">
                  <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                  <p>
                    เพื่อยืนยันการลบ ให้พิมพ์ชื่อผู้ใช้ของคุณให้ตรง และพิมพ์ <span className="font-bold">DELETE</span> ในช่องยืนยัน
                  </p>
                </div>
              </div>

              <label className="grid gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.22em] text-slate-500">ชื่อผู้ใช้</span>
                <input
                  type="text"
                  value={deleteForm.confirm_username}
                  onChange={e => setDeleteForm(prev => ({ ...prev, confirm_username: e.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-red-500 focus:ring-4 focus:ring-red-100"
                  placeholder="กรอกชื่อผู้ใช้ของคุณ"
                />
              </label>

              <label className="grid gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.22em] text-slate-500">พิมพ์ DELETE เพื่อยืนยัน</span>
                <input
                  type="text"
                  value={deleteForm.confirm_text}
                  onChange={e => setDeleteForm(prev => ({ ...prev, confirm_text: e.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-red-500 focus:ring-4 focus:ring-red-100"
                  placeholder="DELETE"
                />
              </label>

              <label className="grid gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.22em] text-slate-500">รหัสผ่านยืนยัน</span>
                <input
                  type="password"
                  value={deleteForm.password}
                  onChange={e => setDeleteForm(prev => ({ ...prev, password: e.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-red-500 focus:ring-4 focus:ring-red-100"
                  placeholder="กรอกรหัสผ่านเดิม"
                />
              </label>

              <div className="flex items-center justify-between gap-3 pt-1">
                <p className="text-xs leading-6 text-slate-500">
                  ต้องยืนยันด้วยชื่อผู้ใช้และพิมพ์ DELETE ให้ถูกต้องก่อนลบบัญชี
                </p>
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl bg-red-600 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-red-200 transition hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  ลบบัญชี
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

function SupportModal({ open, onClose }) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/55 p-0 backdrop-blur-sm sm:items-center sm:p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full overflow-hidden rounded-t-[28px] border border-white/20 bg-white shadow-[0_30px_120px_rgba(15,23,42,0.28)] sm:max-w-2xl sm:rounded-[28px]">
        <div className="bg-gradient-to-r from-blue-700 via-blue-700 to-indigo-700 px-5 py-5 text-white sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-blue-100/80">Support</p>
              <h2 className="mt-1 text-2xl font-extrabold leading-tight">ติดต่อผู้ดูแลระบบ</h2>
              <p className="mt-1 text-sm text-blue-50/90">สำหรับปัญหา คำแนะนำ และการใช้งานระบบจองห้อง</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-white/10 text-white transition-colors hover:bg-white/20"
              aria-label="Close support"
            >
              <ChevronLeft size={18} />
            </button>
          </div>
        </div>

        <div className="max-h-[78vh] overflow-y-auto p-4 sm:p-6">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-500">หน่วยงาน</p>
              <p className="mt-2 text-sm font-bold text-slate-900">{supportInfo.organization}</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{supportInfo.address}</p>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-500">ช่องทางติดต่อ</p>
              <div className="mt-3 space-y-2 text-sm text-slate-700">
                <p className="flex items-center gap-2"><Phone size={16} className="text-blue-600" /> โทร. {supportInfo.phone}</p>
                <p className="flex items-center gap-2"><MessageSquareMore size={16} className="text-blue-600" /> webmaster ภายใน {supportInfo.webmaster}</p>
                <p className="flex items-center gap-2"><Mail size={16} className="text-blue-600" /> {supportInfo.email}</p>
              </div>
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <a
              href={supportInfo.facebook}
              target="_blank"
              rel="noreferrer"
              className="rounded-[24px] border border-blue-100 bg-blue-50/70 p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-500">Facebook</p>
              <p className="mt-2 text-sm font-semibold text-slate-900">OCNfanpage</p>
              <p className="mt-2 text-xs text-slate-500">เปิดเพจเพื่อดูข่าวสารและติดต่อเพิ่มเติม</p>
            </a>
            <div className="rounded-[24px] border border-emerald-100 bg-emerald-50/70 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-500">แจ้งปัญหา</p>
              <p className="mt-2 text-sm font-semibold text-slate-900">ติดต่อ webmaster เพื่อแจ้งปัญหา คำแนะนำ หรือข้อผิดพลาดของระบบ</p>
            </div>
            <div className="rounded-[24px] border border-amber-100 bg-amber-50/70 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-amber-500">หมายเหตุ</p>
              <p className="mt-2 text-sm font-semibold text-slate-900">{supportInfo.copyright}</p>
            </div>
          </div>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl bg-blue-700 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-blue-200 transition hover:bg-blue-800"
            >
              <ExternalLink size={16} />
              ปิดหน้าติดต่อ
            </button>
            <button
              type="button"
              onClick={() => window.open(`mailto:${supportInfo.email}`, '_blank')}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
            >
              <Mail size={16} />
              ส่งอีเมลหา OCN
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function GuideModal({ open, onClose, onGoBooking }) {
  if (!open) return null

  const steps = [
    {
      title: 'เริ่มจากแถบค้นหาด้านบน',
      desc: 'พิมพ์ชื่อห้อง อาคาร หรือรหัสห้อง ระบบจะเดาคำที่พิมพ์ผิดและแสดงห้องที่ใกล้เคียงให้เลือก',
    },
    {
      title: 'เลือกวัน เวลา และจำนวนผู้เข้าร่วม',
      desc: 'จากหน้า จองห้องประชุม ให้กำหนดเงื่อนไขหลักก่อนกดค้นหา ระบบจะคัดห้องที่เหมาะสมให้ทันที',
    },
    {
      title: 'ดูคำแนะนำจาก AI',
      desc: 'ถ้าไม่พบห้องตรงเงื่อนไข ระบบจะเสนอห้องใกล้เคียงหรือห้องสำรองที่น่าจะใช้ได้แทน',
    },
    {
      title: 'ยืนยันและติดตามผล',
      desc: 'เมื่อเลือกห้องได้แล้ว กดยืนยันการจอง และกลับมาดูสถานะได้จากหน้าแรกหรือแดชบอร์ด',
    },
  ]

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/55 p-0 backdrop-blur-sm sm:items-center sm:p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="w-full overflow-hidden rounded-t-[28px] border border-white/20 bg-white shadow-[0_30px_120px_rgba(15,23,42,0.28)] sm:max-w-3xl sm:rounded-[28px]">
        <div className="bg-gradient-to-r from-blue-700 via-blue-700 to-indigo-700 px-5 py-5 text-white sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-blue-100/80">User guide</p>
              <h2 className="mt-1 text-2xl font-extrabold leading-tight">คู่มือการใช้งาน</h2>
              <p className="mt-1 text-sm text-blue-50/90">อ่านจบแล้วเริ่มใช้งานได้ทันที</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-white/10 text-white transition-colors hover:bg-white/20"
              aria-label="Close guide"
            >
              <ChevronLeft size={18} />
            </button>
          </div>
        </div>

        <div className="max-h-[78vh] overflow-y-auto p-4 sm:p-6">
          <div className="grid gap-3 md:grid-cols-2">
            {steps.map((step, index) => (
              <div key={step.title} className="rounded-[24px] border border-slate-200 bg-slate-50 p-4">
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-2xl bg-blue-600 text-white text-sm font-bold">
                  {index + 1}
                </div>
                <p className="text-sm font-bold text-slate-900">{step.title}</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">{step.desc}</p>
              </div>
            ))}
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-[24px] border border-blue-100 bg-blue-50/70 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-500">Tip</p>
              <p className="mt-2 text-sm font-semibold text-slate-900">ถ้าพิมพ์ชื่อห้องผิด ระบบยังพยายามเดาห้องที่ใกล้เคียงให้</p>
            </div>
            <div className="rounded-[24px] border border-emerald-100 bg-emerald-50/70 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-500">Shortcut</p>
              <p className="mt-2 text-sm font-semibold text-slate-900">กด <span className="font-bold text-emerald-700">Enter</span> เพื่อค้นหาทันที</p>
            </div>
            <div className="rounded-[24px] border border-amber-100 bg-amber-50/70 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-amber-500">Help</p>
              <p className="mt-2 text-sm font-semibold text-slate-900">ถ้าไม่พบห้อง ให้ลองเปลี่ยนเวลา หรือดูห้องแนะนำแทน</p>
            </div>
          </div>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onGoBooking}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl bg-blue-700 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-blue-200 transition hover:bg-blue-800"
            >
              <BookOpen size={16} />
              ไปหน้าจองห้องประชุม
            </button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex flex-1 items-center justify-center rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
            >
              ปิดคู่มือ
            </button>
          </div>

          <div className="mt-5 rounded-[24px] border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-500">ติดต่อผู้ดูแล</p>
            <p className="mt-2 text-sm font-semibold text-slate-900">{supportInfo.organization}</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">{supportInfo.address}</p>
            <div className="mt-3 grid gap-2 text-sm text-slate-700 sm:grid-cols-2">
              <p className="flex items-center gap-2"><Phone size={15} className="text-blue-600" /> โทร. {supportInfo.phone}</p>
              <p className="flex items-center gap-2"><MessageSquareMore size={15} className="text-blue-600" /> webmaster {supportInfo.webmaster}</p>
              <p className="flex items-center gap-2"><Mail size={15} className="text-blue-600" /> {supportInfo.email}</p>
              <a href={supportInfo.facebook} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-blue-700 hover:underline">
                <Globe size={15} className="text-blue-600" />
                OCNfanpage
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

const NOTIF_TYPE_ICON = {
  booking_approved:  '✅',
  booking_rejected:  '❌',
  booking_reminder:  '⏰',
  booking_cancelled: '🚫',
  term_approved:     '📚',
  demand_alert:      '📈',
  system:            '🔔',
}

const timeAgo = (iso) => {
  const diffMin = Math.round((Date.now() - new Date(iso)) / 60000)
  if (diffMin < 1) return 'เมื่อสักครู่'
  if (diffMin < 60) return `${diffMin} นาทีที่แล้ว`
  const diffHr = Math.round(diffMin / 60)
  if (diffHr < 24) return `${diffHr} ชม.ที่แล้ว`
  return `${Math.round(diffHr / 24)} วันที่แล้ว`
}

function NotificationBell() {
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [panelPos, setPanelPos] = useState(null)
  const wsRef = useRef(null)
  const buttonRef = useRef(null)

  const refetch = () => {
    api.get('/notifications/').then(res => {
      const list = res.data.results || res.data || []
      setNotifications(list)
      setUnreadCount(list.filter(n => !n.is_read).length)
    }).catch(() => {})
  }

  useEffect(() => {
    refetch()

    const token = getAccessToken()
    if (!token) return

    const ws = new WebSocket(`${WS_BASE_URL}notifications/?token=${token}`)
    wsRef.current = ws
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'unread_count') {
          setUnreadCount(data.count)
        } else if (data.type === 'new_notification') {
          // WS push ไม่ส่ง id ของ Notification มาด้วย — ดึงรายการจริงจาก REST
          // ใหม่อีกที เพื่อให้ได้ id ที่ใช้กดอ่านทีหลังได้ถูกต้อง
          refetch()
        }
      } catch { /* ข้อความไม่ตรงรูปแบบที่คาด ข้ามไป */ }
    }

    return () => ws.close()
  }, [])

  const markRead = async (n) => {
    if (!n.is_read) {
      try {
        await api.post(`/notifications/${n.id}/read/`)
        setNotifications(prev => prev.map(x => x.id === n.id ? { ...x, is_read: true } : x))
        setUnreadCount(prev => Math.max(0, prev - 1))
      } catch { /* เดี๋ยวรอบหน้าค่อยลองใหม่ */ }
    }
  }

  const markAllRead = async () => {
    try {
      await api.post('/notifications/read_all/')
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
      setUnreadCount(0)
    } catch { /* เดี๋ยวรอบหน้าค่อยลองใหม่ */ }
  }

  const toggleOpen = () => {
    setOpen(o => {
      const next = !o
      if (next && buttonRef.current) {
        const rect = buttonRef.current.getBoundingClientRect()
        const panelWidth = Math.min(384, window.innerWidth - 32) // sm:w-96 = 384px, w-[calc(100vw-2rem)] มือถือ
        const margin = 16
        let left = rect.right - panelWidth
        left = Math.max(margin, Math.min(left, window.innerWidth - panelWidth - margin))
        setPanelPos({ top: rect.bottom + 8, left })
        // เปิดดูแล้วถือว่าอ่านเลย ไม่ต้องรอกดทีละอันหรือกด "อ่านทั้งหมด" เอง
        if (unreadCount > 0) markAllRead()
      }
      return next
    })
  }

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={toggleOpen}
        className="relative inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-blue-700"
        aria-label="การแจ้งเตือน"
      >
        <Bell size={19} />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white ring-2 ring-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && panelPos && createPortal(
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="fixed z-50 max-h-[70vh] w-[calc(100vw-2rem)] max-w-sm overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl sm:w-96"
            style={{ top: panelPos.top, left: panelPos.left }}
          >
            <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
              <p className="text-sm font-bold text-slate-900">การแจ้งเตือน</p>
              {unreadCount > 0 && (
                <button onClick={markAllRead} className="text-xs font-semibold text-blue-700 hover:underline">
                  อ่านทั้งหมด
                </button>
              )}
            </div>
            <div className="max-h-[55vh] overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
                  <Bell size={26} className="text-slate-300" />
                  <p className="text-sm text-slate-400">ยังไม่มีการแจ้งเตือน</p>
                </div>
              ) : (
                notifications.map(n => (
                  <button
                    key={n.id}
                    onClick={() => markRead(n)}
                    className={`flex w-full items-start gap-2.5 border-b border-slate-50 px-4 py-3 text-left transition-colors hover:bg-slate-50 ${!n.is_read ? 'bg-blue-50/50' : ''}`}
                  >
                    <span className="mt-0.5 text-base leading-none shrink-0">{NOTIF_TYPE_ICON[n.type] || '🔔'}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-semibold text-slate-800">{n.title}</span>
                        {!n.is_read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-600" />}
                      </span>
                      <span className="mt-0.5 block text-xs text-slate-500 break-words">{n.message}</span>
                      <span className="mt-1 block text-[11px] text-slate-400">{timeAgo(n.created_at)}</span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        </>,
        document.body
      )}
    </div>
  )
}

function AppShell({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [isSupportOpen, setIsSupportOpen] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [searchSuggestions, setSearchSuggestions] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(false)

  const user = useMemo(() => getUser(), [location.pathname])
  const displayName = normalizeDisplayName(
    [
      user?.display_name,
      user?.full_name,
      [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim(),
      user?.first_name,
      user?.name,
      user?.username,
    ],
  )
  const roleLabel = roleLabels[user?.role] || 'ผู้ใช้ระบบ'
  const isAdminOrStaff = ['admin', 'staff'].includes(user?.role)
  // แดชบอร์ดเป็นหน้าสำหรับแอดมิน/เจ้าหน้าที่เท่านั้น (AdminRoute เด้งกลับ
  // หน้าแรกเงียบๆ ถ้า role ไม่ถึง) — ไม่โชว์เมนูนี้ให้ role อื่นเห็น กันกด
  // แล้วรู้สึกว่า "ไม่ไปไหน" ทั้งที่จริงๆ คือถูกเด้งกลับแบบไม่มี feedback
  const visibleNavItems = navItems.filter(item => item.to !== '/admin/dashboard' || isAdminOrStaff)
  const sectionLabel = useMemo(() => {
    if (location.pathname === '/home') return 'หน้าหลัก'
    if (location.pathname.startsWith('/search')) return 'จองห้องประชุม'
    if (location.pathname.startsWith('/admin/dashboard')) return 'รายงาน'
    return 'ระบบจองห้องประชุม'
  }, [location.pathname])

  const quickLinks = [
    {
      key: 'guide',
      label: 'คู่มือ',
      icon: BookOpen,
      onClick: () => navigate('/guide'),
    },
    {
      key: 'settings',
      label: 'ตั้งค่า',
      icon: Settings2,
      onClick: () => setIsSettingsOpen(true),
    },
    {
      key: 'support',
      label: 'ติดต่อผู้ดูแล',
      icon: AlertTriangle,
      onClick: () => setIsSupportOpen(true),
    },
  ]

  useEffect(() => {
    setIsMobileNavOpen(false)
    // React Router ไม่รีเซ็ต scroll position ให้เองตอนเปลี่ยนหน้า — ถ้าหน้า
    // ก่อนหน้า scroll ลงไปอยู่ล่างๆ แล้วหน้าใหม่สั้นกว่า จะเห็นเหมือนจอ
    // "กระโดด" ไปอยู่ท้ายหน้าแทนที่จะเริ่มจากบนสุด
    window.scrollTo(0, 0)
  }, [location.pathname])

  useEffect(() => {
    if (!searchText.trim()) {
      setSearchSuggestions([])
      setSearchLoading(false)
      return
    }

    const timer = setTimeout(async () => {
      setSearchLoading(true)
      try {
        const res = await api.get('/rooms/suggestions/', {
          params: { q: searchText.trim(), limit: 6 },
        })
        const data = Array.isArray(res.data) ? res.data : []
        setSearchSuggestions(data)
      } catch {
        setSearchSuggestions([])
      } finally {
        setSearchLoading(false)
      }
    }, 220)

    return () => clearTimeout(timer)
  }, [searchText])

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setIsMobileNavOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const isActive = (to, exact = false) => {
    if (exact) return location.pathname === to
    return location.pathname === to || location.pathname.startsWith(`${to}/`)
  }

  const sidebarWidthClass = 'lg:w-[300px]'

  const runGlobalSearch = (payload) => {
    const query = (payload || searchText || '').trim()
    if (!query) return
    const top = searchSuggestions[0]
    navigate('/search', {
      state: top
        ? { quickRoom: top, quickSearch: query }
        : { quickSearch: query },
    })
    setShowSuggestions(false)
  }

  return (
    <div className="min-h-screen w-full bg-[linear-gradient(180deg,#f8fbff_0%,#f5f8fc_100%)] text-slate-900">
      <header className="sticky top-0 z-50 border-b border-blue-200/80 bg-[linear-gradient(180deg,#f8fbff_0%,#eef4ff_100%)] shadow-[0_10px_34px_rgba(37,99,235,0.10)]">
        <div className="mx-auto w-full max-w-[1600px] px-4 py-3 sm:px-6 lg:px-8">
          <div className="overflow-hidden rounded-[26px] border border-blue-100 bg-white shadow-[0_18px_50px_rgba(37,99,235,0.08)]">
            <div className="h-1.5 bg-gradient-to-r from-blue-600 via-cyan-400 to-indigo-600" />
            <div className="flex h-20 w-full items-center gap-4 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => setIsMobileNavOpen(true)}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-blue-700 lg:hidden"
              aria-label="Open navigation"
            >
              <Menu size={19} />
            </button>
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white text-blue-700 shadow-[0_12px_28px_rgba(37,99,235,0.18)]">
              <Building2 size={24} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-lg font-extrabold leading-tight text-slate-900">ระบบจองห้องประชุม</p>
              <p className="truncate text-sm font-semibold text-slate-500">สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี</p>
            </div>
          </div>

          <div className="hidden flex-1 justify-center md:flex">
            <div className="relative w-full max-w-[420px]">
              <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') runGlobalSearch()
                }}
                placeholder="ค้นหาห้องประชุม, รายการจอง..."
                className="h-12 w-full rounded-full border border-slate-200 bg-slate-50/90 px-12 pr-4 text-sm text-slate-700 placeholder:text-slate-400 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              />
              <button
                type="button"
                onClick={() => runGlobalSearch()}
                className="absolute right-1 top-1/2 -translate-y-1/2 rounded-full bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-blue-700"
              >
                ค้นหา
              </button>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <NotificationBell />

            <button
              type="button"
              onClick={() => setIsSettingsOpen(true)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-blue-700"
              aria-label="Settings"
            >
              <Settings2 size={19} />
            </button>

            <div className="hidden lg:flex h-11 items-center gap-3 rounded-full border border-white/20 bg-white/10 px-3 pr-4 shadow-sm">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-white">
                <UserCircle2 size={18} />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold leading-tight text-slate-900">{displayName}</p>
                <p className="truncate text-[11px] text-slate-500">{roleLabel}</p>
              </div>
            </div>

            <button
              type="button"
              onClick={logout}
              className="hidden h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-blue-700 lg:inline-flex"
              aria-label="Logout"
            >
              <LogOut size={18} />
            </button>
          </div>
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-[1600px] gap-6 px-4 py-5 sm:px-6 lg:px-8 lg:py-6">
        <aside className={`hidden shrink-0 lg:sticky lg:top-24 lg:flex lg:max-h-[calc(100dvh-7rem)] ${sidebarWidthClass}`}>
          <div className="flex h-full w-full flex-col overflow-y-auto rounded-[28px] border border-slate-200/80 bg-white p-3 shadow-[0_14px_40px_rgba(15,23,42,0.06)]">
            <div className="mb-3 flex items-center justify-between gap-2 px-1 pt-1">
              <div className="min-w-0">
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-500">เมนู</p>
                <p className="text-sm font-semibold text-slate-900">Sidebar</p>
              </div>
              <div className="rounded-full bg-blue-50 px-3 py-1 text-[11px] font-bold text-blue-700">
                {sectionLabel}
              </div>
            </div>

            <nav className="flex flex-col gap-2">
              {visibleNavItems.map(item => {
                const Icon = item.icon
                const active = isActive(item.to, item.exact)
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={`flex items-center gap-3 rounded-[22px] px-4 py-3.5 text-sm font-semibold transition-all ${
                      active
                        ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-[0_14px_28px_rgba(37,99,235,0.22)]'
                        : 'bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    }`}
                  >
                    <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl transition-all ${
                      active ? 'bg-white/15' : 'bg-slate-100 text-slate-500'
                    }`}>
                      <Icon size={18} />
                    </span>
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                )
              })}
            </nav>

            <div className="my-4 border-t border-slate-200/80" />

            <div className="px-1">
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-500">ทางลัด</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">Quick access</p>
            </div>

            <div className="mt-3 flex flex-col gap-2">
              {quickLinks.map(item => {
                const Icon = item.icon
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={item.onClick}
                    className="flex items-center gap-3 rounded-[20px] border border-slate-200 bg-white px-4 py-3 text-left text-sm font-semibold text-slate-600 transition-all hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                      <Icon size={17} />
                    </span>
                    <span className="truncate">{item.label}</span>
                  </button>
                )
              })}
            </div>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <main className="min-h-[calc(100dvh-7.5rem)] px-0 py-0">
            {children}
          </main>
        </div>
      </div>

      <SettingsModal open={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} user={user} />
      <SupportModal open={isSupportOpen} onClose={() => setIsSupportOpen(false)} />

      {isMobileNavOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/45 backdrop-blur-[2px]"
            aria-label="Close navigation overlay"
            onClick={() => setIsMobileNavOpen(false)}
          />
          <div className="absolute left-0 top-0 flex h-full w-[86vw] max-w-xs flex-col bg-white shadow-2xl">
            <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
              <div className="min-w-0">
                <p className="truncate text-sm font-bold text-slate-900">Sidebar</p>
                <p className="truncate text-[11px] text-slate-500">UBU</p>
              </div>
              <button
                type="button"
                className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-600"
                onClick={() => setIsMobileNavOpen(false)}
                aria-label="Close navigation"
              >
                <ChevronLeft size={18} />
              </button>
            </div>
            <nav className="flex flex-1 flex-col gap-2 p-4">
              {visibleNavItems.map(item => {
                const Icon = item.icon
                const active = isActive(item.to, item.exact)
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold ${
                      active ? 'bg-blue-600 text-white' : 'bg-slate-50 text-slate-700'
                    }`}
                  >
                    <Icon size={17} />
                    {item.label}
                  </NavLink>
                )
              })}
            </nav>
            <div className="border-t border-slate-200 px-4 py-4">
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-500">Quick access</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {quickLinks.map(item => {
                  const Icon = item.icon
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={item.onClick}
                      className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-center text-xs font-semibold text-slate-700"
                    >
                      <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                        <Icon size={17} />
                      </span>
                      <span className="truncate">{item.label}</span>
                    </button>
                  )
                })}
              </div>
            </div>
            <div className="border-t border-slate-200 p-4">
              <button
                type="button"
                onClick={logout}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white"
              >
                <LogOut size={16} />
                ออกจากระบบ
              </button>
            </div>
          </div>
        </div>
      )}

      <footer className="border-t border-blue-200/80 bg-[linear-gradient(180deg,#f8fbff_0%,#eef4ff_100%)] text-slate-700 shadow-[0_-10px_34px_rgba(37,99,235,0.10)]">
        {/* มือถือ: การ์ดย่อ 2 บรรทัด + ปุ่มเปิด modal ติดต่อ (ใช้ SupportModal เดิม) แทน
            การ stack 3 คอลัมน์เต็มที่กินพื้นที่จอสูงมากบนจอแคบ */}
        <div className="mx-auto w-full max-w-[1600px] px-4 py-3 sm:hidden">
          <div className="flex items-center justify-between gap-3 rounded-2xl border border-blue-100 bg-white/90 px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-xs font-bold text-slate-900">{supportInfo.organization}</p>
              <p className="mt-0.5 truncate text-[11px] text-slate-400">{supportInfo.copyright}</p>
            </div>
            <button
              type="button"
              onClick={() => setIsSupportOpen(true)}
              className="shrink-0 rounded-full bg-blue-50 px-3 py-1.5 text-[11px] font-bold text-blue-700"
            >
              ติดต่อ
            </button>
          </div>
        </div>

        <div className="mx-auto hidden w-full max-w-[1600px] px-4 py-5 sm:block sm:px-6 lg:px-8">
          <div className="overflow-hidden rounded-[28px] border border-blue-100 bg-white/90 shadow-[0_18px_50px_rgba(37,99,235,0.08)] backdrop-blur-xl">
            <div className="h-1.5 bg-gradient-to-r from-blue-600 via-cyan-400 to-indigo-600" />
            <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[1.2fr_0.9fr_0.9fr]">
              <div className="space-y-3">
                <div className="inline-flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.22em] text-blue-700">
                  ระบบจองห้องประชุม
                </div>
                <div>
                  <p className="text-sm font-extrabold text-slate-900">{supportInfo.organization}</p>
                  <p className="mt-1 text-sm leading-6 text-slate-600">{supportInfo.address}</p>
                </div>
                <p className="text-xs leading-6 text-slate-500">{supportInfo.copyright}</p>
              </div>

              <div className="space-y-3">
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-500">ช่องทางติดต่อ</p>
                <div className="space-y-2 text-sm">
                  <p className="flex items-start gap-2">
                    <span className="mt-0.5 h-2 w-2 rounded-full bg-blue-500" />
                    <span>โทร. {supportInfo.phone}</span>
                  </p>
                  <p className="flex items-start gap-2">
                    <span className="mt-0.5 h-2 w-2 rounded-full bg-indigo-500" />
                    <span>webmaster ภายใน {supportInfo.webmaster}</span>
                  </p>
                  <p className="flex items-start gap-2">
                    <span className="mt-0.5 h-2 w-2 rounded-full bg-cyan-500" />
                    <span>{supportInfo.email}</span>
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-500">ลิงก์เพิ่มเติม</p>
                <a
                  href={supportInfo.facebook}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                >
                  <span className="truncate">Facebook: OCNfanpage</span>
                  <span className="ml-3 rounded-full bg-white px-2 py-1 text-[11px] font-bold text-blue-700 shadow-sm transition group-hover:bg-blue-600 group-hover:text-white">
                    เปิด
                  </span>
                </a>
                <div className="rounded-2xl border border-blue-100 bg-blue-50/70 px-4 py-3 text-sm text-slate-700">
                  พบปัญหา คำแนะนำ โปรดแจ้ง webmaster
                </div>
              </div>
            </div>
          </div>
        </div>
      </footer>

    </div>
  )
}

export default AppShell
