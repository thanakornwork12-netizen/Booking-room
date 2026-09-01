import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mail, Phone, GraduationCap, IdCard, ShieldCheck, Loader2, Save, ArrowLeft } from 'lucide-react'
import api, { getUser, updateStoredUser } from '../api/axios'

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
      const data = err?.response?.data
      const text = data?.detail
        || (data && Object.values(data)[0]?.[0])
        || 'บันทึกข้อมูลไม่สำเร็จ กรุณาลองใหม่'
      setMessage({ type: 'error', text })
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

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-6 sm:px-0">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-4 inline-flex items-center gap-1.5 text-sm font-semibold text-slate-500 transition-colors hover:text-blue-700"
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
                {[form?.first_name, form?.last_name].filter(Boolean).join(' ') || profile?.username}
              </p>
              <p className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold">
                <ShieldCheck size={12} /> {roleLabel}
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-5 p-6">
          {message.text && (
            <div className={`rounded-2xl border px-4 py-3 text-sm ${
              message.type === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-red-200 bg-red-50 text-red-600'
            }`}>
              {message.text}
            </div>
          )}

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
    </div>
  )
}
