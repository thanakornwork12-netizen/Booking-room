import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CalendarDays, Clock, Users, LogOut, Search, Bell, X,
  LayoutDashboard, Building2, ChevronRight, CheckCircle2,
  ArrowRight, BookOpen, Zap, AlertCircle
} from 'lucide-react'
import api from '../api/axios'

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes scaleIn{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:scale(1)}}
@keyframes rot{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .06s ease both}
.au2{animation:fadeUp .28s .12s ease both}
.af{animation:fadeIn .2s ease both}
.si{animation:scaleIn .25s ease both}
.pulse{animation:pulse 2s infinite}
`

const canCheckIn = (startTime) => {
  const diff = (new Date() - new Date(startTime)) / 60000
  return diff >= -15 && diff <= 15
}

const isPast = (endTime) => {
  return new Date() > new Date(endTime)
}

const timeUntil = (startTime) => {
  const diff = Math.round((new Date(startTime) - new Date()) / 60000)
  if (diff > 60) return `${Math.floor(diff/60)} ชม. ${diff%60} นาที`
  if (diff > 0)  return `${diff} นาที`
  if (diff > -15) return 'เปิด check-in แล้ว'
  return null
}

function useDevice() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', fn); return () => window.removeEventListener('resize', fn)
  }, [])
  return isMobile
}

const TUTORIAL_STEPS = [
  {
    icon: <Search size={28} color="#1d4ed8" />,
    title: 'ค้นหาห้องว่าง',
    desc: 'กดปุ่ม "จองห้องประชุม" เลือกวันที่ เวลา และจำนวนผู้เข้าร่วม ระบบ AI จะแสดงห้องที่แนะนำให้ก่อน',
  },
  {
    icon: <Zap size={28} color="#f59e0b" />,
    title: 'ดูการคาดการณ์ AI',
    desc: '"จองได้เลย" = ห้องว่าง  "ควรจองตอนนี้" = เริ่มมีคนสนใจ  "รีบจองด่วน!" = ใกล้เต็มแล้ว',
  },
  {
    icon: <CheckCircle2 size={28} color="#10b981" />,
    title: 'Check-in ก่อนถึงเวลา',
    desc: 'กดปุ่ม "Check-in" ภายใน 15 นาทีหลังเวลาเริ่ม ไม่เช่นนั้นระบบจะยกเลิกการจองอัตโนมัติ',
  },
  {
    icon: <AlertCircle size={28} color="#ef4444" />,
    title: 'หลีกเลี่ยง No-Show',
    desc: 'หากมาไม่ได้กรุณายกเลิกก่อน ไม่เช่นนั้นสิทธิ์จองอาจถูกระงับเมื่อ no-show เกิน 3 ครั้ง',
  },
]

function TutorialModal({ onClose, userId }) {
  const [step, setStep] = useState(0)
  const isLast = step === TUTORIAL_STEPS.length - 1
  const s = TUTORIAL_STEPS[step]

  const finish = () => {
    localStorage.setItem(`tutorial_done_${userId}`, '1')
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-slate-900/50 z-50 flex items-end md:items-center justify-center px-0 md:px-4">
      <div className="bg-white w-full max-w-md rounded-t-3xl md:rounded-3xl shadow-2xl overflow-hidden si">
        <div className="bg-blue-700 px-6 pt-6 pb-5">
          <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
          <div className="flex items-center gap-2 mb-1">
            <BookOpen size={16} color="#fff" />
            <span className="text-white text-xs font-bold uppercase tracking-widest">คู่มือใช้งาน</span>
          </div>
          <p className="text-white/70 text-xs">ระบบจองห้องประชุม มหาวิทยาลัยอุบลราชธานี</p>
        </div>
        <div className="flex gap-1.5 px-6 pt-5">
          {TUTORIAL_STEPS.map((_,i) => (
            <div key={i} className={`h-1.5 rounded-full flex-1 transition-all ${i <= step ? 'bg-blue-700' : 'bg-blue-100'}`} />
          ))}
        </div>
        <div className="px-6 py-5 min-h-48">
          <div className="w-14 h-14 bg-blue-50 border border-blue-100 rounded-2xl flex items-center justify-center mb-4">
            {s.icon}
          </div>
          <p className="font-extrabold text-slate-900 text-lg mb-2">{s.title}</p>
          <p className="text-slate-600 text-sm leading-relaxed">{s.desc}</p>
        </div>
        <div className="px-6 pb-6 flex gap-3">
          <button onClick={finish}
            className="flex-1 border-2 border-blue-100 text-slate-500 py-3 rounded-xl font-semibold text-sm hover:bg-blue-50">
            ข้าม
          </button>
          <button onClick={() => isLast ? finish() : setStep(step + 1)}
            className="flex-[2] bg-blue-700 hover:bg-blue-800 text-white py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 shadow-md shadow-blue-200 active:scale-95 transition-all">
            {isLast ? <><CheckCircle2 size={15} />เริ่มใช้งาน</> : <>ถัดไป <ArrowRight size={14} /></>}
          </button>
        </div>
      </div>
    </div>
  )
}

function NotiDropdown({ notifications, onDismiss, onClose }) {
  const unread = notifications.filter(n => !n.is_read)
  return (
    <div className="absolute right-0 top-11 w-72 bg-white border border-blue-100 rounded-2xl shadow-2xl z-50 overflow-hidden si">
      <div className="px-4 py-3 border-b border-blue-50 flex justify-between items-center">
        <span className="text-sm font-bold text-slate-900">การแจ้งเตือน</span>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600 flex"><X size={14} /></button>
      </div>
      {unread.length === 0
        ? <p className="text-center text-sm text-slate-400 py-6">ไม่มีการแจ้งเตือน</p>
        : <div className="max-h-60 overflow-y-auto">
            {unread.map(n => (
              <div key={n.id} className="px-4 py-3 flex gap-3 items-start border-b border-blue-50 last:border-0 hover:bg-blue-50/40">
                <div className="w-2 h-2 bg-blue-500 rounded-full mt-1.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-slate-800 mb-0.5">{n.title}</p>
                  <p className="text-xs text-slate-500 line-clamp-2">{n.message}</p>
                </div>
                <button onClick={() => onDismiss(n.id)} className="text-slate-300 hover:text-slate-500 flex-shrink-0 flex"><X size={12} /></button>
              </div>
            ))}
          </div>
      }
    </div>
  )
}

function TermBookingModal({ booking, onClose, onCancel }) {
  if (!booking) return null
  return (
    <div className="fixed inset-0 bg-slate-900/40 z-50 flex items-end md:items-center justify-center px-0 md:px-4" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-white w-full max-w-md rounded-t-3xl md:rounded-3xl shadow-2xl overflow-hidden si">
        <div className="px-5 py-4 flex items-center justify-between border-b border-blue-50">
          <div className="flex items-center gap-2">
            <BookOpen size={18} className="text-blue-700" />
            <span className="font-bold text-slate-900 text-sm">รายละเอียดวิชาเรียน (จองรายเทอม)</span>
          </div>
          <button onClick={onClose} className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center text-slate-400 hover:text-blue-600"><X size={14} /></button>
        </div>
        <div className="px-5 py-5">
          <div className="bg-blue-700 text-white p-4 rounded-2xl mb-4 shadow-lg shadow-blue-200">
            <p className="text-[10px] uppercase tracking-widest opacity-70 mb-1">รายวิชา / กิจกรรม</p>
            <p className="text-lg font-bold leading-tight">{booking.subject_name}</p>
            <p className="text-xs opacity-80 mt-1">{booking.subject_code || 'ไม่ระบุรหัสวิชา'}</p>
          </div>
          <div className="space-y-3 mb-6">
            <div className="flex items-center gap-3 text-slate-600 bg-slate-50 p-3 rounded-xl">
              <Building2 size={16} className="text-blue-600" />
              <div>
                <p className="text-[10px] text-slate-400">ห้องประชุม / อาคาร</p>
                <p className="text-sm font-bold">{booking.room_name} ({booking.building_name})</p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-slate-600 bg-slate-50 p-3 rounded-xl">
              <Clock size={16} className="text-blue-600" />
              <div>
                <p className="text-[10px] text-slate-400">วันและเวลาที่เรียน</p>
                <p className="text-sm font-bold">ทุกวัน{booking.day_name} | {booking.start_time_raw} - {booking.end_time_raw} น.</p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-slate-600 bg-slate-50 p-3 rounded-xl">
              <CalendarDays size={16} className="text-blue-600" />
              <div>
                <p className="text-[10px] text-slate-400">ระยะเวลาของเทอม</p>
                <p className="text-sm font-bold">{booking.term_name} ({booking.term_start} ถึง {booking.term_end})</p>
              </div>
            </div>
          </div>
          <button onClick={() => onCancel(booking.id)} className="w-full py-3 text-red-500 font-bold text-sm border-2 border-red-50 rounded-xl hover:bg-red-50 transition-colors">
            ยกเลิกการจองรายเทอมนี้
          </button>
        </div>
      </div>
    </div>
  )
}

function BookingModal({ booking, onClose, onCancel, onCheckIn, fmtTime, fmtDateFull }) {
  if (!booking) return null
  const isActive    = booking.status === 'approved'
  const isFinished  = isActive && isPast(booking.end_time)
  const isCancelled = booking.status === 'cancelled'
  const isNoShow    = booking.status === 'no_show'
  
  const showCheckIn = isActive && !isFinished && canCheckIn(booking.start_time) && !booking.checked_in
  const until       = isActive && !isFinished && !booking.checked_in ? timeUntil(booking.start_time) : null
  
  const statusColor = isFinished ? '#64748b' : (isActive ? '#10b981' : isNoShow ? '#f97316' : '#cbd5e1')
  const statusLabel = isFinished ? 'ใช้งานเสร็จสิ้น' : (isActive ? 'กำลังจอง' : isNoShow ? 'ไม่มาใช้งาน' : 'ยกเลิกแล้ว')

  return (
    <div className="fixed inset-0 bg-slate-900/40 z-50 flex items-end md:items-center justify-center px-0 md:px-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-white w-full max-w-md rounded-t-3xl md:rounded-3xl shadow-2xl overflow-hidden si">
        <div className="px-5 py-4 flex items-center justify-between border-b border-blue-50">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full" style={{background: statusColor}} />
            <span className="font-bold text-slate-900 text-sm">รายละเอียดการจอง</span>
          </div>
          <button onClick={onClose} className="w-7 h-7 rounded-lg border border-blue-100 bg-blue-50 flex items-center justify-center text-slate-400 hover:text-blue-600 hover:bg-blue-100">
            <X size={14} />
          </button>
        </div>
        <div className="px-5 py-4">
          <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
          <div className={`bg-gradient-to-br border rounded-2xl p-4 flex items-center gap-3 mb-4 ${isFinished ? 'from-slate-50 to-slate-100 border-slate-200' : 'from-blue-50 to-blue-100 border-blue-200'}`}>
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${isFinished ? 'bg-slate-500' : 'bg-blue-700'}`}>
              <Building2 size={20} color="#fff" />
            </div>
            <div>
              <p className="font-bold text-slate-900 text-base">{booking.room_name || `ห้อง #${booking.room}`}</p>
              <span className="text-xs font-semibold" style={{color: statusColor}}>● {statusLabel}</span>
              {booking.checked_in && <span className="ml-2 text-xs bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full font-bold border border-emerald-200">✓ Check-in แล้ว</span>}
            </div>
          </div>
          {isActive && !isFinished && !booking.checked_in && until && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-xl px-4 py-3 mb-4 flex items-start gap-2">
              <AlertCircle size={14} className="text-yellow-600 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-yellow-800">
                {showCheckIn
                  ? 'กรุณา Check-in ภายใน 15 นาที มิฉะนั้นระบบจะยกเลิกอัตโนมัติ'
                  : `อีก ${until} จะสามารถ Check-in ได้`}
              </p>
            </div>
          )}
          <div className="border-2 border-blue-50 rounded-2xl overflow-hidden mb-4">
            {[
              {icon:'📋', label:'หัวข้อ',     value: booking.title},
              {icon:'📅', label:'วันที่',      value: fmtDateFull(booking.start_time)},
              {icon:'⏰', label:'เวลาเริ่ม',   value: fmtTime(booking.start_time) + ' น.'},
              {icon:'⏱️', label:'เวลาสิ้นสุด', value: fmtTime(booking.end_time) + ' น.'},
              {icon:'👥', label:'จำนวนคน',    value: `${booking.attendees} คน`},
            ].map((r,i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5 bg-white border-b border-blue-50 last:border-0">
                <span className="text-sm w-5 flex-shrink-0">{r.icon}</span>
                <span className="text-xs text-slate-500 w-20 flex-shrink-0">{r.label}</span>
                <span className="text-sm font-semibold text-slate-800 flex-1">{r.value}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-300 text-center mb-4">ID: #{booking.id}</p>
          <div className="space-y-2.5">
            {showCheckIn && (
              <button onClick={() => onCheckIn(booking.id)}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3.5 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-emerald-200 active:scale-95 transition-all pulse">
                <CheckCircle2 size={16} />ยืนยันการมาใช้งาน (Check-in)
              </button>
            )}
            {isActive && !isFinished && (
              <button onClick={() => onCancel(booking.id)}
                className="w-full border-2 border-red-100 text-red-500 hover:bg-red-50 py-3 rounded-2xl font-bold text-sm transition-colors">
                ยกเลิกการจองนี้
              </button>
            )}
            {(isCancelled || isNoShow || isFinished) && (
              <div className={`rounded-2xl px-4 py-3 text-center text-xs font-semibold
                ${isNoShow ? 'bg-orange-50 border border-orange-200 text-orange-700' : 
                  isFinished ? 'bg-slate-50 border border-slate-200 text-slate-500' : 
                  'bg-blue-50 border border-blue-100 text-slate-500'}`}>
                {isNoShow ? '⚠️ บันทึกว่า ไม่มาใช้งาน (No-Show)' : 
                 isFinished ? 'การประชุมนี้สิ้นสุดลงแล้ว' : 'การจองนี้ถูกยกเลิกแล้ว'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function BookingRow({ b, onClick, fmtDate, fmtTime, compact=false }) {
  const isActive    = b.status === 'approved'
  const isFinished  = isActive && isPast(b.end_time)
  const isCancelled = b.status === 'cancelled'
  const isNoShow    = b.status === 'no_show'
  
  const showCI      = isActive && !isFinished && canCheckIn(b.start_time) && !b.checked_in
  const dotColor    = isFinished ? '#94a3b8' : (isActive ? '#10b981' : isNoShow ? '#f97316' : '#cbd5e1')
  const opacity     = isCancelled || isNoShow || isFinished ? 'opacity-50' : ''

  return (
    <div onClick={onClick}
      className={`${compact?'px-5 py-4':'px-6 py-4'} flex items-center gap-3 cursor-pointer hover:bg-blue-50/40 transition-colors border-b border-blue-50 last:border-0 ${opacity}`}>
      <div className="w-2 h-2 rounded-full flex-shrink-0 mt-0.5" style={{background: dotColor}} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
          <p className="text-sm font-bold text-slate-900 truncate">{b.room_name || `ห้อง #${b.room}`}</p>
          {showCI && <span className="text-xs bg-emerald-600 text-white px-2 py-0.5 rounded-full font-bold pulse flex-shrink-0">Check-in เปิดแล้ว</span>}
          {isNoShow && <span className="text-xs bg-orange-100 text-orange-700 border border-orange-200 px-2 py-0.5 rounded-full font-bold flex-shrink-0">No-Show</span>}
          {isFinished && <span className="text-xs bg-slate-100 text-slate-500 border border-slate-200 px-2 py-0.5 rounded-full font-bold flex-shrink-0">เสร็จสิ้น</span>}
        </div>
        <p className="text-xs text-slate-500 truncate mb-1">{b.title}</p>
        <div className="flex gap-3 text-xs text-slate-400">
          <span className="flex items-center gap-1"><CalendarDays size={9} />{fmtDate(b.start_time)}</span>
          <span className="flex items-center gap-1"><Clock size={9} />{fmtTime(b.start_time)}–{fmtTime(b.end_time)}</span>
          <span className="flex items-center gap-1"><Users size={9} />{b.attendees} คน</span>
        </div>
      </div>
      <ChevronRight size={13} className="text-blue-200 flex-shrink-0" />
    </div>
  )
}

function DesktopHome(props) {
  const { user, bookings, termBookings, notifications, unreadNotis, activeBookings, cancelledBookings, noShowBookings,
    showNoti, setShowNoti, handleDismissNoti, handleLogout, navigate,
    selectedBooking, setSelectedBooking, setSelectedTermBooking, handleCancel, handleCheckIn, fmtDate, fmtTime, fmtDateFull } = props
  
  return (
    <div className="min-h-screen bg-slate-100" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="bg-blue-700 shadow-lg shadow-blue-900/20">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between gap-6">
          <div>
            <span className="text-white font-bold text-sm">สวัสดี, {user?.first_name || user?.username}</span>
            <span className="text-blue-200 text-xs ml-3">{user?.faculty || 'ระบบจองห้องประชุม'}</span>
          </div>
          <div className="flex items-center gap-2">
            {user?.role && ['admin','staff'].includes(user.role) && (
              <button onClick={() => navigate('/admin')}
                className="flex items-center gap-1.5 text-xs font-semibold text-white/80 hover:text-white border border-white/20 rounded-lg px-3 py-1.5 hover:bg-white/10 transition-colors">
                <LayoutDashboard size={13} />Dashboard
              </button>
            )}
            <div className="relative">
              <button onClick={() => setShowNoti(!showNoti)}
                className="w-8 h-8 rounded-lg border border-white/20 bg-white/10 flex items-center justify-center text-white hover:bg-white/20 relative">
                <Bell size={15} />
                {unreadNotis.length > 0 && <span className="absolute top-1 right-1 w-2 h-2 bg-yellow-400 rounded-full" />}
              </button>
              {showNoti && <NotiDropdown notifications={notifications} onDismiss={handleDismissNoti} onClose={() => setShowNoti(false)} />}
            </div>
            <button onClick={handleLogout}
              className="w-8 h-8 rounded-lg border border-red-300/30 bg-white/10 flex items-center justify-center text-white hover:bg-red-500/20">
              <LogOut size={15} />
            </button>
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
      </div>
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-3 gap-6">
          <div className="space-y-5 au">
            <button onClick={() => navigate('/search')}
              className="w-full bg-gradient-to-br from-blue-700 to-blue-600 text-white rounded-2xl p-6 flex items-center justify-between shadow-xl shadow-blue-300 hover:shadow-2xl hover:-translate-y-0.5 active:translate-y-0 transition-all">
              <div>
                <p className="text-lg font-extrabold mb-1">จองห้องประชุม</p>
                <p className="text-blue-200 text-xs">ค้นหาและจองห้องได้ทันที</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-white/15 border border-white/25 flex items-center justify-center">
                <Search size={22} />
              </div>
            </button>
            
            <div className="grid grid-cols-2 gap-3">
              {[
                {label:'จองทั้งหมด', value: bookings.length,          color:'text-blue-700'},
                {label:'กำลังจอง',   value: activeBookings.length,    color:'text-emerald-600'},
                {label:'ยกเลิกแล้ว',value: cancelledBookings.length, color:'text-red-500'},
                {label:'No-Show',   value: noShowBookings.length,    color:'text-orange-500'},
                {label:'จองรายเทอม', value: termBookings.length,      color:'text-purple-600'},
              ].map((s,i) => (
                <div key={i} className="bg-white border border-blue-100 rounded-2xl p-4 text-center shadow-sm">
                  <p className={`text-2xl font-extrabold ${s.color}`}>{s.value}</p>
                  <p className="text-xs text-slate-500 mt-1">{s.label}</p>
                </div>
              ))}
            </div>

            {/* Term Bookings Quick View */}
            <div className="bg-white border border-purple-100 rounded-2xl shadow-sm overflow-hidden">
                <div className="px-4 py-3 bg-purple-50 flex items-center gap-2 border-b border-purple-100">
                    <BookOpen size={16} className="text-purple-700"/>
                    <span className="font-bold text-sm text-purple-900">วิชาที่จอง (รายเทอม)</span>
                </div>
                <div className="p-2 space-y-2">
                    {termBookings.length === 0 ? (
                        <p className="text-[10px] text-slate-400 p-4 text-center">ไม่มีรายการจองรายเทอม</p>
                    ) : (
                        termBookings.map(tb => (
                            <div key={tb.id} onClick={() => setSelectedTermBooking(tb)} className="p-3 bg-white hover:bg-purple-50 rounded-xl border border-transparent hover:border-purple-100 cursor-pointer transition-all">
                                <p className="text-xs font-bold text-slate-800 truncate">{tb.subject_name}</p>
                                <p className="text-[10px] text-purple-600 font-bold">ทุกวัน{tb.day_name} | {tb.start_time_raw} น.</p>
                            </div>
                        ))
                    )}
                </div>
            </div>
          </div>
          
          <div className="col-span-2 bg-white border border-blue-100 rounded-2xl shadow-sm overflow-hidden au1">
            <div className="px-6 py-4 flex justify-between items-center border-b border-blue-50">
              <span className="font-bold text-slate-900">การจองของฉัน (รายวัน)</span>
              <span className="text-xs text-slate-500 bg-blue-50 px-3 py-1 rounded-full">{bookings.length} รายการ</span>
            </div>
            {bookings.length === 0
              ? <div className="py-16 text-center">
                  <CalendarDays size={40} className="text-blue-200 mx-auto mb-3" />
                  <p className="text-sm text-slate-400 mb-4">ยังไม่มีการจอง</p>
                  <button onClick={() => navigate('/search')} className="bg-blue-700 text-white px-5 py-2 rounded-xl text-sm font-semibold hover:bg-blue-800">จองห้องเลย</button>
                </div>
              : bookings.slice(0,20).map(b => (
                  <BookingRow key={b.id} b={b} fmtDate={fmtDate} fmtTime={fmtTime} onClick={() => setSelectedBooking(b)} />
                ))
            }
          </div>
        </div>
      </div>
    </div>
  )
}

function MobileHome(props) {
  const { 
    user, bookings, termBookings, notifications, unreadNotis,
    activeBookings, cancelledBookings, noShowBookings,
    showNoti, setShowNoti, handleDismissNoti, handleLogout, navigate,
    selectedBooking, setSelectedBooking, setSelectedTermBooking, handleCancel, handleCheckIn, 
    fmtDate, fmtTime, fmtDateFull 
  } = props

  return (
    <div className="min-h-screen bg-blue-50" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="bg-blue-700 sticky top-0 z-40 shadow-lg shadow-blue-900/20">
        <div className="max-w-lg mx-auto px-4 h-14 flex items-center justify-between">
          <div>
            <p className="text-sm font-bold text-white">สวัสดี, {user?.first_name || user?.username}</p>
            <p className="text-xs text-blue-200">{user?.faculty || 'ระบบจองห้องประชุม'}</p>
          </div>
          <div className="flex items-center gap-2">
            {user?.role && ['admin','staff'].includes(user.role) && (
              <button onClick={() => navigate('/admin')} className="w-8 h-8 rounded-lg border border-white/20 bg-white/10 flex items-center justify-center text-white hover:bg-white/20">
                <LayoutDashboard size={16} />
              </button>
            )}
            <div className="relative">
              <button onClick={() => setShowNoti(!showNoti)} className="w-8 h-8 rounded-lg border border-white/20 bg-white/10 flex items-center justify-center text-white hover:bg-white/20 relative">
                <Bell size={16} />
                {unreadNotis.length > 0 && <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-yellow-400 rounded-full" />}
              </button>
              {showNoti && <NotiDropdown notifications={notifications} onDismiss={handleDismissNoti} onClose={() => setShowNoti(false)} />}
            </div>
            <button onClick={handleLogout} className="w-8 h-8 rounded-lg border border-red-300/30 bg-white/10 flex items-center justify-center text-white hover:bg-red-500/20">
              <LogOut size={16} />
            </button>
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
      </div>
      <div className="max-w-lg mx-auto px-4 py-4 space-y-4 pb-20">
        <button onClick={() => navigate('/search')}
          className="au w-full bg-gradient-to-br from-blue-700 to-blue-600 text-white rounded-2xl p-5 flex items-center justify-between shadow-lg shadow-blue-300 hover:opacity-95 active:scale-95 transition-all">
          <div>
            <p className="text-base font-extrabold mb-0.5">จองห้องประชุม</p>
            <p className="text-blue-200 text-xs">ค้นหาและจองห้องได้ทันที</p>
          </div>
          <div className="w-11 h-11 rounded-xl bg-white/15 border border-white/25 flex items-center justify-center">
            <Search size={20} />
          </div>
        </button>

        <div className="grid grid-cols-5 gap-1 au1">
          {[
            { label: 'จองทั้งหมด', value: bookings.length, color: 'text-blue-700' },
            { label: 'กำลังจอง', value: activeBookings.length, color: 'text-emerald-600' },
            { label: 'ยกเลิกแล้ว', value: cancelledBookings.length, color: 'text-red-500' },
            { label: 'No-Show', value: noShowBookings.length, color: 'text-orange-500' },
            { label: 'รายเทอม', value: termBookings.length, color: 'text-purple-600' },
          ].map((s, i) => (
            <div key={i} className="bg-white border border-blue-100 rounded-xl p-2 text-center shadow-sm">
              <p className={`text-lg font-extrabold ${s.color}`}>{s.value}</p>
              <p className="text-[9px] text-slate-500 mt-0.5 leading-tight">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Term Bookings Slider for Mobile */}
        <div className="au1">
            <div className="flex items-center gap-2 mb-2 px-1">
                <BookOpen size={16} className="text-blue-700"/>
                <span className="font-bold text-slate-800 text-sm">จองรายเทอม</span>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide">
                {termBookings.length === 0 ? (
                    <div className="w-full p-6 bg-white rounded-2xl border border-dashed border-slate-200 text-center text-xs text-slate-400">ไม่มีรายการ</div>
                ) : (
                    termBookings.map(tb => (
                        <div key={tb.id} onClick={() => setSelectedTermBooking(tb)} className="min-w-[160px] bg-white p-4 rounded-2xl border border-blue-50 shadow-sm">
                            <p className="text-[10px] font-bold text-blue-600 mb-1">ทุกวัน{tb.day_name}</p>
                            <p className="text-xs font-bold text-slate-800 truncate mb-1">{tb.subject_name}</p>
                            <p className="text-[10px] text-slate-400">{tb.start_time_raw} น.</p>
                        </div>
                    ))
                )}
            </div>
        </div>

        <div className="bg-white border border-blue-100 rounded-2xl overflow-hidden shadow-sm au2">
          <div className="px-5 py-3.5 flex justify-between items-center border-b border-blue-50">
            <span className="font-bold text-slate-900 text-sm">การจองของฉัน (รายวัน)</span>
            <span className="text-xs text-slate-500 bg-blue-50 px-2.5 py-0.5 rounded-full">{bookings.length} รายการ</span>
          </div>
          {bookings.length === 0
            ? <div className="py-12 text-center">
                <CalendarDays size={36} className="text-blue-200 mx-auto mb-3" />
                <p className="text-sm text-slate-400 mb-4">ยังไม่มีการจอง</p>
                <button onClick={() => navigate('/search')} className="bg-blue-700 text-white px-5 py-2 rounded-xl text-sm font-semibold">จองห้องเลย</button>
              </div>
            : bookings.slice(0,20).map(b => (
                <BookingRow key={b.id} b={b} fmtDate={fmtDate} fmtTime={fmtTime}
                  onClick={() => setSelectedBooking(b)} compact />
              ))
          }
        </div>
      </div>
    </div>
  )
}

export default function HomePage() {
  const navigate  = useNavigate()
  const isMobile  = useDevice()
  const [bookings, setBookings]               = useState([])
  const [termBookings, setTermBookings]       = useState([])
  const [notifications, setNotifications]     = useState([])
  const [user, setUser]                       = useState(null)
  const [loading, setLoading]                 = useState(true)
  const [showNoti, setShowNoti]               = useState(false)
  const [selectedBooking, setSelectedBooking] = useState(null)
  const [selectedTermBooking, setSelectedTermBooking] = useState(null)
  const [showTutorial, setShowTutorial]       = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const [p,b,n,t] = await Promise.all([
          api.get('/auth/profile/'),
          api.get('/bookings/'),
          api.get('/notifications/'),
          // จุดสำคัญ: ลบ /api/ ออก เพื่อเลี่ยงปัญหา url ซ้อน
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
      }
      finally { setLoading(false) }
    }; load()
  }, [navigate])

  const handleLogout = () => {
    localStorage.clear()
    navigate('/login')
  }

  const handleDismissNoti = async (id) => {
    try {
      await api.post(`/notifications/${id}/read/`)
      setNotifications(prev => prev.map(n => n.id === id ? {...n, is_read:true} : n))
    } catch {}
  }

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
      setBookings(prev => prev.map(b => b.id === id ? {...b, checked_in: true} : b))
      if (selectedBooking?.id === id) setSelectedBooking(prev => ({...prev, checked_in: true}))
      alert('✅ Check-in สำเร็จ!')
    } catch { alert('ไม่สามารถ Check-in ได้ในขณะนี้') }
  }

  const fmtDate     = dt => new Date(dt).toLocaleDateString('th-TH',{day:'numeric',month:'short',year:'2-digit'})
  const fmtTime     = dt => new Date(dt).toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit'})
  const fmtDateFull = dt => new Date(dt).toLocaleDateString('th-TH',{weekday:'long',day:'numeric',month:'long',year:'numeric'})

  const unreadNotis       = notifications.filter(n => !n.is_read)
  const activeBookings    = bookings.filter(b => b.status === 'approved' && !isPast(b.end_time))
  const cancelledBookings = bookings.filter(b => b.status === 'cancelled')
  const noShowBookings    = bookings.filter(b => b.status === 'no_show')

  if (loading) return (
    <div className="min-h-screen bg-blue-50 flex flex-col items-center justify-center gap-3" style={{fontFamily:"'Sarabun',sans-serif"}}>
      <style>{ANIM}</style>
      <div style={{width:36,height:36,border:'3px solid #bfdbfe',borderTopColor:'#1d4ed8',borderRadius:'50%',animation:'rot .7s linear infinite'}} />
      <p className="text-sm text-slate-500">กำลังโหลด...</p>
    </div>
  )

  const shared = {
    user, bookings, termBookings, notifications, unreadNotis,
    activeBookings, cancelledBookings, noShowBookings,
    showNoti, setShowNoti, handleDismissNoti, handleLogout, navigate,
    selectedBooking, setSelectedBooking, 
    selectedTermBooking, setSelectedTermBooking,
    handleCancel, handleTermCancel, handleCheckIn,
    fmtDate, fmtTime, fmtDateFull
  }

  return (
    <>
      {showTutorial && <TutorialModal onClose={() => setShowTutorial(false)} userId={user?.id} />}
      
      {isMobile ? <MobileHome {...shared} /> : <DesktopHome {...shared} />}
      
      <BookingModal 
        booking={selectedBooking} 
        onClose={() => setSelectedBooking(null)}
        onCancel={handleCancel} 
        onCheckIn={handleCheckIn} 
        fmtTime={fmtTime} 
        fmtDateFull={fmtDateFull} 
      />

      <TermBookingModal 
        booking={selectedTermBooking} 
        onClose={() => setSelectedTermBooking(null)} 
        onCancel={handleTermCancel} 
      />
    </>
  )
}