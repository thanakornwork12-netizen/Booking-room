import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Mail, Phone, GraduationCap, IdCard, ShieldCheck, Loader2, Save, ArrowLeft,
  History, CalendarDays, Clock, Users, CheckCircle2, XCircle, KeyRound, UserRound,
} from 'lucide-react'
import api, { getUser, updateStoredUser, changePassword } from '../api/axios'

const roleLabels = {
  admin: 'ผู้ดูแลระบบ',
  staff: 'เจ้าหน้าที่',
  lecturer: 'อาจารย์',
  student: 'นักศึกษา',
}

const inputCls = `w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm
  text-slate-800 outline-none transition-all placeholder:text-slate-400
  focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100
  disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400`

// เงื่อนไขเดียวกับ HomePage — เช็คอินได้ช่วง 15 นาทีก่อน/หลังเวลาเริ่ม
const canCheckIn = (startTime) => {
  const diff = (new Date() - new Date(startTime)) / 60000
  return diff >= -15 && diff <= 15
}
const isPast = (endTime) => new Date() > new Date(endTime)

const fmtDate = dt => new Date(dt).toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' })
const fmtTime = dt => new Date(dt).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })

const HISTORY_PAGE = 5

const firstError = (err, fallback) => {
  const data = err?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return fallback
  if (data.detail) return data.detail
  if (data.error) return data.error
  const first = Object.values(data)[0]
  return (Array.isArray(first) ? first[0] : first) || fallback
}

function Message({ message }) {
  if (!message.text) return null
  return (
    <div className={`rounded-2xl border px-4 py-3 text-sm ${
      message.type === 'success'
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
        : 'border-red-200 bg-red-50 text-red-600'
    }`}>
      {message.text}
    </div>
  )
}

function SectionCard({ icon: Icon, title, right, children }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-slate-100 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-6 py-4">
        <div className="flex items-center gap-2">
          <Icon size={17} className="text-blue-600" />
          <span className="text-sm font-bold text-slate-800">{title}</span>
        </div>
        {right}
      </div>
      <div className="space-y-4 p-6">{children}</div>
    </div>
  )
}

function statusBadge(b) {
  const finished = (b.status === 'approved' || b.status === 'checked_in') && isPast(b.end_time)
  if (finished) return { label: 'เสร็จสิ้น', cls: 'bg-slate-100 text-slate-500 border-slate-200' }
  if (b.checked_in || b.status === 'checked_in') return { label: 'Check-in แล้ว', cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' }
  switch (b.status) {
    case 'approved':  return { label: 'ยืนยันแล้ว', cls: 'bg-blue-50 text-blue-700 border-blue-200' }
    case 'pending':   return { label: 'รออนุมัติ', cls: 'bg-amber-100 text-amber-700 border-amber-200' }
    case 'rejected':  return { label: 'ถูกปฏิเสธ', cls: 'bg-rose-100 text-rose-700 border-rose-200' }
    case 'cancelled': return { label: 'ยกเลิกแล้ว', cls: 'bg-slate-100 text-slate-500 border-slate-200' }
    default:          return { label: b.status, cls: 'bg-slate-100 text-slate-500 border-slate-200' }
  }
}

function BookingHistory() {
  const [bookings, setBookings] = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [shown, setShown]       = useState(HISTORY_PAGE)
  const [busyId, setBusyId]     = useState(null)

  useEffect(() => {
    let active = true
    api.get('bookings/')
      .then(res => { if (active) setBookings(res.data.results || res.data || []) })
      .catch(() => { if (active) setError('โหลดประวัติการจองไม่สำเร็จ') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const handleCancel = async (id) => {
    if (busyId || !confirm('ยืนยันการยกเลิกการจองนี้?')) return
    setBusyId(id)
    try {
      await api.post(`bookings/${id}/cancel/`)
      setBookings(prev => prev.map(b => b.id === id ? { ...b, status: 'cancelled' } : b))
    } catch (err) {
      alert(firstError(err, 'ยกเลิกการจองไม่สำเร็จ'))
    } finally { setBusyId(null) }
  }

  const handleCheckIn = async (id) => {
    if (busyId) return
    setBusyId(id)
    try {
      await api.post(`bookings/${id}/check_in/`)
      setBookings(prev => prev.map(b => b.id === id ? { ...b, checked_in: true, status: 'checked_in' } : b))
      alert('✅ Check-in สำเร็จ!')
    } catch (err) {
      alert(firstError(err, 'ไม่สามารถ Check-in ได้ในขณะนี้'))
    } finally { setBusyId(null) }
  }

  return (
    <SectionCard
      icon={History}
      title="ประวัติการจอง"
      right={!loading && !error && (
        <span className="rounded-md bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-500">{bookings.length} รายการ</span>
      )}
    >
      {loading ? (
        <div className="flex justify-center py-6"><Loader2 size={22} className="animate-spin text-blue-600" /></div>
      ) : error ? (
        <Message message={{ type: 'error', text: error }} />
      ) : bookings.length === 0 ? (
        <p className="py-4 text-center text-sm text-slate-400">ยังไม่มีประวัติการจอง</p>
      ) : (
        <>
          <div className="divide-y divide-slate-100 rounded-2xl border border-slate-100">
            {bookings.slice(0, shown).map(b => {
              const badge = statusBadge(b)
              const approved = b.status === 'approved'
              const finished = approved && isPast(b.end_time)
              const showCheckIn = approved && !finished && !b.checked_in && canCheckIn(b.start_time)
              const showCancel = (approved && !finished && !b.checked_in) || b.status === 'pending'
              const busy = busyId === b.id
              return (
                <div key={b.id} className="px-4 py-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-bold text-slate-800">{b.room_name || `ห้อง #${b.room}`}</p>
                    <span className={`shrink-0 whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] font-bold ${badge.cls}`}>{badge.label}</span>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-slate-500">{b.title}</p>
                  <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] font-medium text-slate-400">
                    <span className="flex items-center gap-1 whitespace-nowrap"><CalendarDays size={11} />{fmtDate(b.start_time)}</span>
                    <span className="flex items-center gap-1 whitespace-nowrap"><Clock size={11} />{fmtTime(b.start_time)}–{fmtTime(b.end_time)}</span>
                    <span className="flex items-center gap-1 whitespace-nowrap"><Users size={11} />{b.attendees} คน</span>
                  </div>
                  {(showCheckIn || showCancel) && (
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      {showCheckIn && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => handleCheckIn(b.id)}
                          className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white transition-colors hover:bg-emerald-700 disabled:bg-slate-300"
                        >
                          <CheckCircle2 size={13} /> Check-in
                        </button>
                      )}
                      {showCancel && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => handleCancel(b.id)}
                          className="inline-flex items-center gap-1.5 rounded-full border border-red-200 px-3.5 py-1.5 text-xs font-bold text-red-600 transition-colors hover:bg-red-50 disabled:text-slate-300"
                        >
                          <XCircle size={13} /> {b.status === 'pending' ? 'ยกเลิกคำขอ' : 'ยกเลิกการจอง'}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {bookings.length > shown && (
            <button
              type="button"
              onClick={() => setShown(n => n + HISTORY_PAGE)}
              className="w-full rounded-full border border-slate-200 py-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50"
            >
              แสดงเพิ่ม ({bookings.length - shown} รายการ)
            </button>
          )}
        </>
      )}
    </SectionCard>
  )
}

function ChangePasswordForm({ canChange }) {
  const [form, setForm]       = useState({ old_password: '', new_password: '', new_password2: '' })
  const [saving, setSaving]   = useState(false)
  const [message, setMessage] = useState({ type: '', text: '' })
  const isSubmittingRef = useRef(false)

  const set = (key, value) => setForm(f => ({ ...f, [key]: value }))

  const onSubmit = async () => {
    if (isSubmittingRef.current) return
    if (!form.old_password || !form.new_password || !form.new_password2) {
      setMessage({ type: 'error', text: 'กรุณากรอกข้อมูลให้ครบทุกช่อง' })
      return
    }
    if (form.new_password !== form.new_password2) {
      setMessage({ type: 'error', text: 'รหัสผ่านใหม่ไม่ตรงกัน' })
      return
    }
    isSubmittingRef.current = true
    setSaving(true)
    setMessage({ type: '', text: '' })
    try {
      const data = await changePassword(form)
      setForm({ old_password: '', new_password: '', new_password2: '' })
      setMessage({ type: 'success', text: data.detail || 'เปลี่ยนรหัสผ่านสำเร็จ' })
    } catch (err) {
      setMessage({ type: 'error', text: firstError(err, 'เปลี่ยนรหัสผ่านไม่สำเร็จ กรุณาลองใหม่') })
    } finally {
      isSubmittingRef.current = false
      setSaving(false)
    }
  }

  return (
    <SectionCard icon={KeyRound} title="เปลี่ยนรหัสผ่าน">
      {!canChange ? (
        <p className="text-sm text-slate-500">
          บัญชีนี้เข้าสู่ระบบด้วยรหัสผ่านของมหาวิทยาลัย (LDAP) กรุณาเปลี่ยนรหัสผ่านที่ระบบของมหาวิทยาลัย
        </p>
      ) : (
        <>
          <Message message={message} />
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">รหัสผ่านเดิม</label>
            <input className={inputCls} type="password" autoComplete="current-password"
              value={form.old_password} onChange={e => set('old_password', e.target.value)} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-slate-500">รหัสผ่านใหม่ (อย่างน้อย 6 ตัว)</label>
              <input className={inputCls} type="password" autoComplete="new-password"
                value={form.new_password} onChange={e => set('new_password', e.target.value)} />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-slate-500">ยืนยันรหัสผ่านใหม่</label>
              <input className={inputCls} type="password" autoComplete="new-password"
                value={form.new_password2} onChange={e => set('new_password2', e.target.value)} />
            </div>
          </div>
          <button
            type="button"
            onClick={onSubmit}
            disabled={saving}
            className="flex w-full items-center justify-center gap-2 rounded-full border-2 border-blue-100 py-3 text-sm font-bold text-blue-700 transition-all hover:bg-blue-50 active:scale-[0.99] disabled:cursor-not-allowed disabled:text-slate-300"
          >
            {saving
              ? <><Loader2 size={16} className="animate-spin" /> กำลังเปลี่ยนรหัสผ่าน...</>
              : <><KeyRound size={16} /> เปลี่ยนรหัสผ่าน</>}
          </button>
        </>
      )}
    </SectionCard>
  )
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const [profile, setProfile]   = useState(null)
  const [form, setForm]         = useState(null)
  const [loading, setLoading]   = useState(true)
  const [saving, setSaving]     = useState(false)
  const [message, setMessage]   = useState({ type: '', text: '' })
  const isSubmittingRef = useRef(false)

  useEffect(() => {
    let active = true
    api.get('auth/profile/')
      .then(res => {
        if (!active) return
        setProfile(res.data)
        setForm({
          first_name: res.data.first_name || '',
          last_name:  res.data.last_name || '',
          email:      res.data.email || '',
          phone:      res.data.phone || '',
          faculty:    res.data.faculty || '',
          student_id: res.data.student_id || '',
        })
      })
      .catch(() => { if (active) setMessage({ type: 'error', text: 'โหลดข้อมูลโปรไฟล์ไม่สำเร็จ' }) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const set = (key, value) => setForm(f => ({ ...f, [key]: value }))

  const onSave = async () => {
    if (isSubmittingRef.current) return
    isSubmittingRef.current = true
    setSaving(true)
    setMessage({ type: '', text: '' })
    try {
      const res = await api.patch('auth/profile/', form)
      setProfile(res.data)
      updateStoredUser(res.data)
      setMessage({ type: 'success', text: 'บันทึกข้อมูลสำเร็จ' })
    } catch (err) {
      setMessage({ type: 'error', text: firstError(err, 'บันทึกข้อมูลไม่สำเร็จ กรุณาลองใหม่') })
    } finally {
      isSubmittingRef.current = false
      setSaving(false)
    }
  }

  const localUser = getUser()
  const roleLabel = roleLabels[profile?.role] || roleLabels[localUser?.role] || 'ผู้ใช้ระบบ'
  const initials = (form?.first_name?.[0] || form?.last_name?.[0] || profile?.username?.[0] || '?').toUpperCase()

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 size={28} className="animate-spin text-blue-600" />
      </div>
    )
  }

  if (!form) {
    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-6 sm:px-0">
        <Message message={message} />
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5 px-4 py-6 sm:px-0">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-500 transition-colors hover:text-blue-700"
      >
        <ArrowLeft size={15} /> กลับ
      </button>

      <div className="overflow-hidden rounded-3xl border border-slate-100 bg-white shadow-sm">
        <div className="bg-gradient-to-br from-blue-700 via-blue-600 to-indigo-600 px-6 py-8 text-white">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-white/15 text-2xl font-bold ring-4 ring-white/20">
              {initials}
            </div>
            <div className="min-w-0">
              <p className="truncate text-lg font-extrabold">
                {[form.first_name, form.last_name].filter(Boolean).join(' ') || profile?.username}
              </p>
              <p className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold">
                <ShieldCheck size={12} /> {roleLabel}
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-5 p-6">
          <div className="flex items-center gap-2">
            <UserRound size={17} className="text-blue-600" />
            <span className="text-sm font-bold text-slate-800">ข้อมูลส่วนตัว</span>
          </div>

          <Message message={message} />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-slate-500">ชื่อ</label>
              <input className={inputCls} value={form.first_name} onChange={e => set('first_name', e.target.value)} placeholder="ชื่อ" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-slate-500">นามสกุล</label>
              <input className={inputCls} value={form.last_name} onChange={e => set('last_name', e.target.value)} placeholder="นามสกุล" />
            </div>
          </div>

          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-500">
              <Mail size={13} /> อีเมล
            </label>
            <input className={inputCls} type="email" value={form.email} onChange={e => set('email', e.target.value)} placeholder="อีเมล" />
          </div>

          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-500">
              <Phone size={13} /> เบอร์โทรศัพท์
            </label>
            <input className={inputCls} value={form.phone} onChange={e => set('phone', e.target.value)} placeholder="เบอร์โทรศัพท์" />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-500">
                <GraduationCap size={13} /> คณะ/หน่วยงาน
              </label>
              <input className={inputCls} value={form.faculty} onChange={e => set('faculty', e.target.value)} placeholder="คณะ/หน่วยงาน" />
            </div>
            <div>
              <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-500">
                <IdCard size={13} /> รหัสนักศึกษา
              </label>
              <input className={inputCls} value={form.student_id} onChange={e => set('student_id', e.target.value)} placeholder="รหัสนักศึกษา" />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 border-t border-slate-100 pt-5 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-slate-400">ชื่อผู้ใช้ (แก้ไขไม่ได้)</label>
              <input className={inputCls} value={profile?.username || ''} disabled />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-slate-400">สถานะ (แก้ไขไม่ได้)</label>
              <input className={inputCls} value={roleLabel} disabled />
            </div>
          </div>

          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 py-3 text-sm font-bold text-white shadow-sm transition-all hover:bg-blue-800 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {saving
              ? <><Loader2 size={16} className="animate-spin" /> กำลังบันทึก...</>
              : <><Save size={16} /> บันทึกการเปลี่ยนแปลง</>}
          </button>
        </div>
      </div>

      <BookingHistory />

      <ChangePasswordForm canChange={profile?.can_change_password !== false} />
    </div>
  )
}
