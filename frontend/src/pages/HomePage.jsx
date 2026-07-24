import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CalendarDays, Clock, Users, Search, X, XCircle,
  Building2, ChevronRight, CheckCircle2,
  ArrowRight, BookOpen, Zap, AlertCircle, History
} from 'lucide-react'
import api from '../api/axios'

const supportInfo = {
  organization: 'สำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี',
  address: '85 ถ.สถลมาร์ค ต.เมืองศรีไค อ.วารินชำราบ จ.อุบลราชธานี 34190',
  phone: '045-353102',
  webmaster: '1502',
  email: 'ocn@ubu.ac.th',
  facebook: 'https://www.facebook.com/ocnfanpage/',
  copyright: 'สงวนลิขสิทธิ์ พ.ศ. 2556 ตามพระราชบัญญัติลิขสิทธิ์ 2537',
}

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes scaleIn{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:scale(1)}}
@keyframes rot{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.au{animation:fadeUp .3s ease both}
.au1{animation:fadeUp .3s .05s ease both}
.au2{animation:fadeUp .3s .1s ease both}
.si{animation:scaleIn .25s ease both}
.pulse{animation:pulse 2s infinite}
`

const canCheckIn = (startTime) => {
  const diff = (new Date() - new Date(startTime)) / 60000
  return diff >= -15 && diff <= 15
}

const isPast = (endTime) => new Date() > new Date(endTime)

const timeUntil = (startTime) => {
  const diff = Math.round((new Date(startTime) - new Date()) / 60000)
  if (diff > 60) return `${Math.floor(diff/60)} ชม. ${diff%60} นาที`
  if (diff > 0)  return `${diff} นาที`
  if (diff > -15) return 'เปิด check-in แล้ว'
  return null
}

const TUTORIAL_STEPS = [
  { icon: <Search size={24} className="shrink-0" color="#1d4ed8" />, title: 'ค้นหาห้องว่าง', desc: 'กดปุ่ม "จองห้องประชุม" เลือกวันที่ เวลา และจำนวนผู้เข้าร่วม ระบบ AI จะแนะนำห้องที่เหมาะสม' },
  { icon: <Zap size={24} className="shrink-0" color="#f59e0b" />, title: 'ดูการคาดการณ์ AI', desc: '"จองได้เลย" = ห้องว่าง | "ควรจองตอนนี้" = เริ่มมีคนสนใจ | "รีบจองด่วน!" = ใกล้เต็ม' },
  { icon: <CheckCircle2 size={24} className="shrink-0" color="#10b981" />, title: 'Check-in ก่อนถึงเวลา', desc: 'กรุณา Check-in ภายใน 15 นาที มิฉะนั้นระบบจะยกเลิกอัตโนมัติ เพื่อให้ผู้อื่นใช้บริการต่อได้' },
  { icon: <AlertCircle size={24} className="shrink-0" color="#ef4444" />, title: 'หลีกเลี่ยง No-Show', desc: 'หากมาไม่ได้กรุณายกเลิกก่อน ไม่เช่นนั้นสิทธิ์จองอาจถูกระงับเมื่อ no-show เกิน 3 ครั้ง' },
]

// --- Components ---

function TutorialModal({ onClose, userId }) {
  const [step, setStep] = useState(0)
  const isLast = step === TUTORIAL_STEPS.length - 1
  const s = TUTORIAL_STEPS[step]
  const finish = () => { localStorage.setItem(`tutorial_done_${userId}`, '1'); onClose() }

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="bg-white w-full sm:max-w-md max-h-[88vh] rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-y-auto si">
        <div className="bg-blue-700 px-6 pt-6 pb-4">
          <div className="h-1 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
          <div className="flex items-center gap-2 mb-1">
            <BookOpen size={16} color="#fff" />
            <span className="text-white text-xs font-bold uppercase tracking-widest">คู่มือใช้งาน</span>
          </div>
          <p className="text-blue-100 text-xs">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</p>
        </div>
        <div className="flex gap-1.5 px-6 pt-4">
          {TUTORIAL_STEPS.map((_,i) => (
            <div key={i} className={`h-1.5 rounded-full flex-1 transition-all duration-300 ${i <= step ? 'bg-blue-600' : 'bg-slate-100'}`} />
          ))}
        </div>
        <div className="px-5 py-5 min-h-[10rem] flex flex-col justify-center">
          <div className="w-12 h-12 bg-blue-50 border border-blue-100 rounded-2xl flex items-center justify-center mb-3.5 shadow-sm">{s.icon}</div>
          <p className="font-bold text-slate-900 text-lg mb-2 break-words">{s.title}</p>
          <p className="text-slate-600 text-sm leading-relaxed break-words">{s.desc}</p>
        </div>
        <div className="px-6 pb-6 flex gap-3">
          <button onClick={finish} className="flex-1 border border-slate-200 text-slate-600 py-3 rounded-xl font-semibold text-sm hover:bg-slate-50 transition-colors whitespace-nowrap">ข้าม</button>
          <button onClick={() => isLast ? finish() : setStep(step + 1)} className="flex-[2] bg-blue-700 hover:bg-blue-800 text-white py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-200 active:scale-95 transition-all whitespace-nowrap">
            {isLast ? <><CheckCircle2 size={15} />เริ่มใช้งาน</> : <>ถัดไป <ArrowRight size={14} /></>}
          </button>
        </div>

        <div className="border-t border-slate-100 px-5 pb-5 pt-4 text-[11px] leading-5 text-slate-500">
          <p className="font-semibold text-slate-700">{supportInfo.organization}</p>
          <p className="mt-1">{supportInfo.address}</p>
          <p>โทร. {supportInfo.phone} | webmaster {supportInfo.webmaster} | {supportInfo.email}</p>
          <p className="mt-1">{supportInfo.copyright}</p>
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, color, bg, icon: Icon }) {
  return (
    <div className="bg-white border border-slate-100 rounded-2xl px-3 py-3.5 sm:px-4 sm:py-4 flex flex-col items-center justify-center gap-1.5 shadow-sm hover:shadow-md hover:border-blue-100 hover:-translate-y-0.5 transition-all cursor-default text-center">
      {Icon && (
        <div className={`w-9 h-9 sm:w-10 sm:h-10 rounded-xl flex items-center justify-center ${bg}`}>
          <Icon size={17} className={color} />
        </div>
      )}
      <p className={`text-xl sm:text-2xl font-extrabold leading-none ${color}`}>{value}</p>
      <p className="text-[11px] sm:text-xs text-slate-500 leading-tight font-medium">{label}</p>
    </div>
  )
}

function BookingRow({ b, onClick, fmtDate, fmtTime }) {
  const isActive = b.status === 'approved'
  const isFinished = isActive && isPast(b.end_time)
  const isCancelled = b.status === 'cancelled'
  const isNoShow = b.status === 'no_show'
  const showCI = isActive && !isFinished && canCheckIn(b.start_time) && !b.checked_in

  const dotColor = isFinished ? '#94a3b8' : (isActive ? '#10b981' : isNoShow ? '#f97316' : '#cbd5e1')
  const opacityClass = isCancelled || isNoShow || isFinished ? 'opacity-60' : ''

  return (
    <div onClick={onClick} className={`group px-4 sm:px-5 py-3.5 flex items-start gap-3 cursor-pointer hover:bg-blue-50/60 transition-colors border-b border-slate-50 last:border-0 ${opacityClass}`}>
      <div className="w-2.5 h-2.5 rounded-full shrink-0 mt-1.5 ring-2 ring-white" style={{background: dotColor}} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <p className="text-sm font-bold text-slate-800 truncate max-w-full">{b.room_name || `ห้อง #${b.room}`}</p>
          {showCI && <span className="text-[10px] bg-emerald-600 text-white px-1.5 py-0.5 rounded font-bold pulse shrink-0 whitespace-nowrap">Check-in</span>}
          {isNoShow && <span className="text-[10px] bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded font-bold border border-orange-200 shrink-0 whitespace-nowrap">No-Show</span>}
          {isFinished && <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded font-bold border border-slate-200 shrink-0 whitespace-nowrap">เสร็จสิ้น</span>}
        </div>
        <p className="text-xs text-slate-500 truncate mb-1.5">{b.title}</p>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400 font-medium">
          <span className="flex items-center gap-1 whitespace-nowrap"><CalendarDays size={11} />{fmtDate(b.start_time)}</span>
          <span className="flex items-center gap-1 whitespace-nowrap"><Clock size={11} />{fmtTime(b.start_time)}–{fmtTime(b.end_time)}</span>
          <span className="flex items-center gap-1 whitespace-nowrap"><Users size={11} />{b.attendees} คน</span>
        </div>
      </div>
      <ChevronRight size={16} className="text-slate-300 group-hover:text-blue-500 shrink-0 mt-2 transition-colors" />
    </div>
  )
}

// --- Modals ---

function TermBookingModal({ booking, onClose, onCancel }) {
  if (!booking) return null
  return (
    <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-0 sm:p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-white w-full sm:max-w-md max-h-[86vh] rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-y-auto si flex flex-col">
        <div className="px-5 py-3.5 flex items-center justify-between gap-3 border-b border-slate-100 sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2 min-w-0">
            <BookOpen size={18} className="text-purple-600 shrink-0" />
            <span className="font-bold text-slate-900 text-sm truncate">รายละเอียดรายเทอม</span>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200 shrink-0"><X size={16} /></button>
        </div>
        <div className="p-5 flex-1 overflow-y-auto">
          <div className="bg-purple-600 text-white p-4 rounded-2xl mb-4 shadow-lg shadow-purple-200">
            <p className="text-[10px] uppercase tracking-widest opacity-70 mb-1">รายวิชา / กิจกรรม</p>
            <p className="text-lg font-bold leading-tight break-words">{booking.subject_name}</p>
            <p className="text-xs opacity-80 mt-1">{booking.subject_code || 'ไม่ระบุรหัสวิชา'}</p>
          </div>
          <div className="space-y-3 mb-6">
            <div className="flex items-center gap-3 text-slate-600 bg-slate-50 p-3 rounded-xl border border-slate-100">
              <Building2 size={16} className="text-purple-600 shrink-0" />
              <div className="min-w-0"><p className="text-[10px] text-slate-400">ห้องประชุม / อาคาร</p><p className="text-sm font-bold truncate">{booking.room_name} ({booking.building_name})</p></div>
            </div>
            <div className="flex items-center gap-3 text-slate-600 bg-slate-50 p-3 rounded-xl border border-slate-100">
              <Clock size={16} className="text-purple-600 shrink-0" />
              <div className="min-w-0"><p className="text-[10px] text-slate-400">วันและเวลาที่เรียน</p><p className="text-sm font-bold truncate">ทุกวัน{booking.day_name} | {booking.start_time_raw} - {booking.end_time_raw} น.</p></div>
            </div>
            <div className="flex items-center gap-3 text-slate-600 bg-slate-50 p-3 rounded-xl border border-slate-100">
              <CalendarDays size={16} className="text-purple-600 shrink-0" />
              <div className="min-w-0"><p className="text-[10px] text-slate-400">ระยะเวลาของเทอม</p><p className="text-sm font-bold truncate">{booking.term_name}</p></div>
            </div>
          </div>
          <button onClick={() => onCancel(booking.id)} className="w-full py-3 text-red-600 font-bold text-sm border-2 border-red-100 rounded-xl hover:bg-red-50 transition-colors flex items-center justify-center gap-2">
            <XCircle size={16} /> ยกเลิกการจองรายเทอมนี้
          </button>
        </div>
      </div>
    </div>
  )
}

function BookingModal({ booking, onClose, onCancel, onCheckIn, fmtTime, fmtDateFull }) {
  if (!booking) return null
  const isActive = booking.status === 'approved'
  const isFinished = isActive && isPast(booking.end_time)
  const isCancelled = booking.status === 'cancelled'
  const isNoShow = booking.status === 'no_show'
  const showCheckIn = isActive && !isFinished && canCheckIn(booking.start_time) && !booking.checked_in
  const until = isActive && !isFinished && !booking.checked_in ? timeUntil(booking.start_time) : null
  const statusColor = isFinished ? '#64748b' : (isActive ? '#10b981' : isNoShow ? '#f97316' : '#cbd5e1')
  const statusLabel = isFinished ? 'ใช้งานเสร็จสิ้น' : (isActive ? 'กำลังจอง' : isNoShow ? 'ไม่มาใช้งาน' : 'ยกเลิกแล้ว')

  return (
    <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-0 sm:p-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-white w-full sm:max-w-md max-h-[86vh] rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-y-auto si flex flex-col">
        <div className="px-5 py-3.5 flex items-center justify-between gap-3 border-b border-slate-100 sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-3 h-3 rounded-full shrink-0" style={{background: statusColor}} />
            <span className="font-bold text-slate-900 text-sm truncate">รายละเอียดการจอง</span>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200 shrink-0"><X size={16} /></button>
        </div>
        <div className="p-5 flex-1 overflow-y-auto">
          <div className={`border rounded-2xl p-4 flex items-center gap-3 mb-4 ${isFinished ? 'bg-slate-50 border-slate-200' : 'bg-blue-50 border-blue-100'}`}>
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 shadow-sm ${isFinished ? 'bg-slate-200 text-slate-500' : 'bg-blue-600 text-white'}`}>
              <Building2 size={22} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-bold text-slate-900 text-base truncate">{booking.room_name || `ห้อง #${booking.room}`}</p>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-white/80 border whitespace-nowrap" style={{color: statusColor, borderColor: statusColor}}>● {statusLabel}</span>
                {booking.checked_in && <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold border border-emerald-200 whitespace-nowrap">✓ Check-in แล้ว</span>}
              </div>
            </div>
          </div>

          {isActive && !isFinished && !booking.checked_in && until && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-4 flex items-start gap-3">
              <AlertCircle size={16} className="text-amber-600 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800 leading-relaxed break-words">
                {showCheckIn ? 'กรุณา Check-in ภายใน 15 นาที มิฉะนั้นระบบจะยกเลิกอัตโนมัติ' : `อีก ${until} จะเริ่มใช้งาน หากไม่สะดวกกรุณายกเลิกล่วงหน้าเพื่อให้ผู้อื่นใช้บริการต่อ`}
              </p>
            </div>
          )}

          <div className="border border-slate-200 rounded-2xl overflow-hidden mb-4 divide-y divide-slate-100">
            {[
              {icon:'📋', label:'หัวข้อ', value: booking.title},
              {icon:'📅', label:'วันที่', value: fmtDateFull(booking.start_time)},
              {icon:'⏰', label:'เวลาเริ่ม', value: fmtTime(booking.start_time) + ' น.'},
              {icon:'⏱️', label:'เวลาสิ้นสุด', value: fmtTime(booking.end_time) + ' น.'},
              {icon:'👥', label:'จำนวนคน', value: `${booking.attendees} คน`},
            ].map((r,i) => (
              <div key={i} className="flex items-start sm:items-center gap-3 px-4 py-3 bg-white">
                <span className="text-sm w-6 text-center shrink-0">{r.icon}</span>
                <span className="text-xs text-slate-500 w-20 shrink-0 font-medium">{r.label}</span>
                <span className="text-sm font-semibold text-slate-800 flex-1 min-w-0 break-words">{r.value}</span>
              </div>
            ))}
          </div>

          <div className="space-y-2.5">
            {showCheckIn && (
              <button onClick={() => onCheckIn(booking.id)} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3.5 rounded-xl font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-emerald-200 active:scale-95 transition-all pulse">
                <CheckCircle2 size={16} /> ยืนยันการมาใช้งาน (Check-in)
              </button>
            )}
            {isActive && !isFinished && (
              <button onClick={() => onCancel(booking.id)} className="w-full border-2 border-red-100 text-red-600 hover:bg-red-50 py-3 rounded-xl font-bold text-sm transition-colors flex items-center justify-center gap-2">
                <XCircle size={16} /> ยกเลิกการจองนี้
              </button>
            )}
            {(isCancelled || isNoShow || isFinished) && (
              <div className={`rounded-xl px-4 py-3 text-center text-xs font-semibold border ${isNoShow ? 'bg-orange-50 border-orange-200 text-orange-700' : isFinished ? 'bg-slate-50 border-slate-200 text-slate-500' : 'bg-blue-50 border-blue-100 text-slate-500'}`}>
                {isNoShow ? '⚠️ บันทึกว่า ไม่มาใช้งาน (No-Show)' : isFinished ? 'การประชุมนี้สิ้นสุดลงแล้ว' : 'การจองนี้ถูกยกเลิกแล้ว'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// --- Main Page ---

export default function HomePage() {
  const navigate = useNavigate()
  const [bookings, setBookings] = useState([])
  const [termBookings, setTermBookings] = useState([])
  const [notifications, setNotifications] = useState([])
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedBooking, setSelectedBooking] = useState(null)
  const [selectedTermBooking, setSelectedTermBooking] = useState(null)
  const [showTutorial, setShowTutorial] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const [p, b, n, t] = await Promise.all([
          api.get('/auth/profile/'),
          api.get('/bookings/'),
          api.get('/notifications/'),
          api.get('/term-bookings/').catch(() => ({ data: [] }))
        ])
        setUser(p.data)
        setBookings(b.data.results || b.data || [])
        setNotifications(n.data.results || n.data || [])
        setTermBookings(Array.isArray(t.data) ? t.data : (t.data.results || []))
        if (!localStorage.getItem(`tutorial_done_${p.data.id}`)) setShowTutorial(true)
      } catch (err) {
        console.error("Load Data Error", err)
        navigate('/login')
      } finally { setLoading(false) }
    }
    load()
  }, [navigate])

  const handleLogout = () => { localStorage.clear(); navigate('/login') }

  const handleCancel = async (id) => {
    if (!confirm('ยืนยันการยกเลิกการจองนี้?')) return
    try {
      await api.post(`/bookings/${id}/cancel/`)
      setBookings(prev => prev.map(b => b.id === id ? {...b, status:'cancelled'} : b))
      if (selectedBooking?.id === id) setSelectedBooking(null)
    } catch { alert('เกิดข้อผิดพลาด') }
  }

  const handleTermCancel = async (id) => {
    if (!confirm('ยืนยันยกเลิกการจองรายเทอม?')) return
    try {
      await api.delete(`/term-bookings/${id}/`)
      setTermBookings(prev => prev.filter(b => b.id !== id))
      setSelectedTermBooking(null)
      alert('ยกเลิกการจองรายเทอมสำเร็จ')
    } catch { alert('เกิดข้อผิดพลาด') }
  }

  const handleCheckIn = async (id) => {
    try {
      await api.post(`/bookings/${id}/check_in/`)
      setBookings(prev => prev.map(b => b.id === id ? {...b, checked_in: true, status: 'checked_in'} : b))
      if (selectedBooking?.id === id) setSelectedBooking(prev => ({...prev, checked_in: true, status: 'checked_in'}))
      alert('✅ Check-in สำเร็จ!')
    } catch (err) { alert(err.response?.data?.error || 'ไม่สามารถ Check-in ได้ในขณะนี้') }
  }

  const fmtDate = dt => new Date(dt).toLocaleDateString('th-TH',{day:'numeric',month:'short',year:'2-digit'})
  const fmtTime = dt => new Date(dt).toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit'})
  const fmtDateFull = dt => new Date(dt).toLocaleDateString('th-TH',{weekday:'long',day:'numeric',month:'long',year:'numeric'})

  const activeBookings = bookings.filter(b => b.status === 'approved' && !isPast(b.end_time))
  const cancelledBookings = bookings.filter(b => b.status === 'cancelled')
  const noShowBookings = bookings.filter(b => b.status === 'no_show')
  const displayName = user?.first_name || user?.username || user?.email || ''

  if (loading) return (
    <div className="w-full h-full bg-[#F8FAFC] flex flex-col items-center justify-center gap-3">
      <style>{ANIM}</style>
      <div style={{width:40,height:40,border:'3px solid #e2e8f0',borderTopColor:'#2563eb',borderRadius:'50%',animation:'rot .7s linear infinite'}} />
      <p className="text-sm text-slate-500 font-medium">กำลังโหลดข้อมูล...</p>
    </div>
  )

  return (
    <div className="w-full" style={{ fontFamily: "'Inter','Prompt','Sarabun','Noto Sans Thai',sans-serif" }}>
      <style>{ANIM}</style>

      {showTutorial && <TutorialModal onClose={() => setShowTutorial(false)} userId={user?.id} />}

      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-4 sm:gap-5">
        <section className="grid grid-cols-1 gap-3.5 lg:grid-cols-12">
          <div className="lg:col-span-4 rounded-[26px] bg-gradient-to-br from-blue-600 to-indigo-600 p-4 text-white shadow-[0_18px_50px_rgba(37,99,235,0.22)]">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-blue-100">Welcome back</p>
                <h1 className="mt-2 text-2xl font-extrabold leading-tight sm:text-3xl">สวัสดี, {displayName}</h1>
                <p className="mt-2 text-sm text-blue-50/90">{user?.faculty || 'ระบบจองห้องประชุม'}</p>
              </div>
              <button
                onClick={() => navigate('/search')}
              className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 border border-white/15 transition-transform hover:scale-105"
              >
                <Search size={22} />
              </button>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                onClick={() => navigate('/search')}
                className="rounded-2xl bg-white px-4 py-2 text-sm font-semibold text-blue-700 shadow-sm transition-transform hover:-translate-y-0.5"
              >
                จองห้องประชุม
              </button>
              {user?.role && ['admin','staff'].includes(user.role) && (
                <button
                  onClick={() => navigate('/admin/dashboard')}
                  className="rounded-2xl border border-white/20 bg-white/10 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-white/15"
                >
                  ไป Dashboard
                </button>
              )}
            </div>
          </div>

          <div className="lg:col-span-8 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard label="จองทั้งหมด" value={bookings.length} color="text-blue-600" bg="bg-blue-50" icon={History} />
            <StatCard label="กำลังจอง" value={activeBookings.length} color="text-emerald-600" bg="bg-emerald-50" icon={CheckCircle2} />
            <StatCard label="ยกเลิกแล้ว" value={cancelledBookings.length} color="text-red-500" bg="bg-red-50" icon={XCircle} />
            <StatCard label="No-Show" value={noShowBookings.length} color="text-orange-500" bg="bg-orange-50" icon={AlertCircle} />
            <StatCard label="รายเทอม" value={termBookings.length} color="text-purple-600" bg="bg-purple-50" icon={BookOpen} />
          </div>
        </section>

        <section className="grid grid-cols-1 gap-3.5 lg:grid-cols-3">
          <div className="flex min-h-[260px] flex-col overflow-hidden rounded-[24px] border border-white/70 bg-white/90 shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
            <div className="flex items-center gap-2 border-b border-blue-100 bg-gradient-to-r from-purple-50 via-white to-blue-50 px-4 py-3">
              <BookOpen size={16} className="text-purple-600" />
              <span className="text-sm font-bold text-slate-800">วิชาที่จอง (รายเทอม)</span>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto p-3">
              {termBookings.length === 0 ? (
                <div className="flex h-full min-h-[220px] flex-col items-center justify-center p-4 text-center">
                  <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-purple-50">
                    <BookOpen size={26} className="text-purple-300" />
                  </div>
                  <p className="text-xs text-slate-400">ไม่มีรายการจองรายเทอม</p>
                </div>
              ) : (
                termBookings.map(tb => (
                  <button
                    key={tb.id}
                    onClick={() => setSelectedTermBooking(tb)}
                    className="w-full rounded-xl border border-slate-100 bg-white p-2.5 text-left transition-all hover:border-purple-200 hover:bg-purple-50"
                  >
                    <p className="mb-1 truncate text-xs font-bold text-slate-800">{tb.subject_name}</p>
                    <p className="flex items-center gap-1 truncate text-[11px] font-semibold text-purple-600">
                      <Clock size={10} className="shrink-0" /> ทุกวัน{tb.day_name} | {tb.start_time_raw} น.
                    </p>
                  </button>
                ))
              )}
            </div>
            {termBookings.length > 4 && (
              <div className="border-t border-slate-100 px-4 py-3 text-[11px] text-slate-500">
                แสดงเฉพาะ 4 รายการล่าสุด
              </div>
            )}
          </div>

          <div className="lg:col-span-2 flex min-h-[260px] flex-col overflow-hidden rounded-[24px] border border-white/70 bg-white/90 shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
            <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/40 px-4 py-3">
              <div className="flex min-w-0 items-center gap-2">
                <CalendarDays size={16} className="shrink-0 text-blue-600" />
                <span className="truncate text-sm font-bold text-slate-800">การจองของฉัน (รายวัน)</span>
              </div>
              <span className="shrink-0 rounded-md bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-500">{bookings.length} รายการ</span>
            </div>

            {bookings.length === 0 ? (
              <div className="flex min-h-[220px] flex-1 flex-col items-center justify-center p-6 text-center">
                <div className="mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-blue-50">
                  <CalendarDays size={32} className="text-blue-300" />
                </div>
                <p className="mb-4 text-sm font-medium text-slate-500">ยังไม่มีการจองห้องประชุม</p>
                <button
                  onClick={() => navigate('/search')}
                  className="rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-200 transition-colors hover:from-blue-700 hover:to-indigo-700"
                >
                  จองห้องเลย
                </button>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto">
                {bookings.slice(0, 4).map(b => (
                  <BookingRow key={b.id} b={b} fmtDate={fmtDate} fmtTime={fmtTime} onClick={() => setSelectedBooking(b)} />
                ))}
              </div>
            )}
            {bookings.length > 4 && (
              <div className="border-t border-slate-100 px-4 py-3 text-[11px] text-slate-500">
                แสดงเฉพาะ 4 รายการล่าสุด
              </div>
            )}
          </div>
        </section>
      </div>

      <BookingModal booking={selectedBooking} onClose={() => setSelectedBooking(null)} onCancel={handleCancel} onCheckIn={handleCheckIn} fmtTime={fmtTime} fmtDateFull={fmtDateFull} />
      <TermBookingModal booking={selectedTermBooking} onClose={() => setSelectedTermBooking(null)} onCancel={handleTermCancel} />
    </div>
  )
}
