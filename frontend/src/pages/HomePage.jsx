import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { CalendarDays, Clock, Users, LogOut, Search, Bell, X, LayoutDashboard, Building2, ChevronRight } from 'lucide-react'
import api from '../api/axios'

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes scaleIn{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:scale(1)}}
@keyframes rot{to{transform:rotate(360deg)}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .06s ease both}
.au2{animation:fadeUp .28s .12s ease both}
.au3{animation:fadeUp .28s .18s ease both}
.af{animation:fadeIn .2s ease both}
.si{animation:scaleIn .22s ease both}
`

function useDevice() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', fn)
    return () => window.removeEventListener('resize', fn)
  }, [])
  return isMobile
}

function NotiDropdown({ notifications, onDismiss, onClose }) {
  const unread = notifications.filter(n => !n.is_read)
  return (
    <div className="absolute right-0 top-11 w-72 bg-white border border-blue-100 rounded-2xl shadow-2xl shadow-blue-100/50 z-50 overflow-hidden si">
      <div className="px-4 py-3 border-b border-blue-50 flex justify-between items-center">
        <span className="text-sm font-bold text-slate-900">การแจ้งเตือน</span>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600 flex"><X size={14} /></button>
      </div>
      {unread.length === 0 ? (
        <p className="text-center text-sm text-slate-400 py-6">ไม่มีการแจ้งเตือน</p>
      ) : (
        <div className="max-h-60 overflow-y-auto">
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
      )}
    </div>
  )
}

function BookingModal({ booking, onClose, onCancel, fmtTime, fmtDateFull }) {
  if (!booking) return null
  const isActive    = booking.status === 'approved'
  const isCancelled = booking.status === 'cancelled'
  return (
    <div className="fixed inset-0 bg-slate-900/40 z-50 flex items-end md:items-center justify-center px-0 md:px-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-white w-full max-w-md rounded-t-3xl md:rounded-3xl shadow-2xl overflow-hidden si">
        <div className="px-5 py-4 flex items-center justify-between border-b border-blue-50">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full" style={{background: isActive ? '#10b981' : '#cbd5e1'}} />
            <span className="font-bold text-slate-900 text-sm">รายละเอียดการจอง</span>
          </div>
          <button onClick={onClose} className="w-7 h-7 rounded-lg border border-blue-100 bg-blue-50 flex items-center justify-center text-slate-400 hover:text-blue-600 hover:bg-blue-100 transition-colors">
            <X size={14} />
          </button>
        </div>
        <div className="px-5 py-4">
          <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 border border-blue-200 rounded-2xl p-4 flex items-center gap-3 mb-4">
            <div className="w-11 h-11 bg-blue-700 rounded-xl flex items-center justify-center flex-shrink-0">
              <Building2 size={20} color="#fff" />
            </div>
            <div>
              <p className="font-bold text-slate-900 text-base">{booking.room_name || `ห้อง #${booking.room}`}</p>
              <p className="text-xs font-semibold mt-0.5" style={{color: isActive ? '#059669' : '#94a3b8'}}>
                {isActive ? '● กำลังจอง' : '● ยกเลิกแล้ว'}
              </p>
            </div>
          </div>
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
          {isActive && (
            <button onClick={() => onCancel(booking.id)}
              className="w-full border-2 border-red-100 text-red-500 hover:bg-red-50 py-3 rounded-2xl font-bold text-sm transition-colors">
              ยกเลิกการจองนี้
            </button>
          )}
          {isCancelled && (
            <div className="bg-blue-50 border border-blue-100 rounded-2xl px-4 py-3 text-center text-xs text-slate-500">
              การจองนี้ถูกยกเลิกแล้ว
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── DESKTOP ────────────────────────────────────────────
function DesktopHome({ user, bookings, notifications, unreadNotis, activeBookings, cancelledBookings,
  showNoti, setShowNoti, handleDismissNoti, handleLogout, navigate,
  selectedBooking, setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull }) {
  return (
    <div className="min-h-screen bg-slate-100" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>

      {/* TOPBAR */}
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
                className="w-8 h-8 rounded-lg border border-white/20 bg-white/10 flex items-center justify-center text-white hover:bg-white/20 transition-colors relative">
                <Bell size={15} />
                {unreadNotis.length > 0 && <span className="absolute top-1 right-1 w-2 h-2 bg-yellow-400 rounded-full" />}
              </button>
              {showNoti && <NotiDropdown notifications={notifications} onDismiss={handleDismissNoti} onClose={() => setShowNoti(false)} />}
            </div>
            <button onClick={handleLogout}
              className="w-8 h-8 rounded-lg border border-red-300/30 bg-white/10 flex items-center justify-center text-white hover:bg-red-500/20 transition-colors">
              <LogOut size={15} />
            </button>
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-3 gap-6">

          {/* LEFT: book btn + stats */}
          <div className="space-y-5 au">
            <button onClick={() => navigate('/search')}
              className="w-full bg-gradient-to-br from-blue-700 to-blue-600 text-white rounded-2xl p-6 flex items-center justify-between shadow-xl shadow-blue-300 hover:shadow-2xl hover:-translate-y-0.5 active:translate-y-0 transition-all duration-150">
              <div>
                <p className="text-lg font-extrabold mb-1">จองห้องประชุม</p>
                <p className="text-blue-200 text-xs">ค้นหาและจองห้องได้ทันที</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-white/15 border border-white/25 flex items-center justify-center">
                <Search size={22} />
              </div>
            </button>

            <div className="grid grid-cols-3 gap-3">
              {[
                {label:'จองทั้งหมด', value: bookings.length,          color:'text-blue-700',  bg:'bg-white'},
                {label:'กำลังจอง',   value: activeBookings.length,    color:'text-emerald-600',bg:'bg-white'},
                {label:'ยกเลิกแล้ว',value: cancelledBookings.length, color:'text-red-500',    bg:'bg-white'},
              ].map((s,i) => (
                <div key={i} className={`${s.bg} border border-blue-100 rounded-2xl p-4 text-center shadow-sm`}>
                  <p className={`text-2xl font-extrabold ${s.color}`}>{s.value}</p>
                  <p className="text-xs text-slate-500 mt-1">{s.label}</p>
                </div>
              ))}
            </div>
          </div>

          {/* RIGHT: booking list (2 cols wide) */}
          <div className="col-span-2 bg-white border border-blue-100 rounded-2xl shadow-sm overflow-hidden au1">
            <div className="px-6 py-4 flex justify-between items-center border-b border-blue-50">
              <span className="font-bold text-slate-900">การจองของฉัน</span>
              <span className="text-xs text-slate-500 bg-blue-50 px-3 py-1 rounded-full">{bookings.length} รายการ</span>
            </div>
            {bookings.length === 0 ? (
              <div className="py-16 text-center">
                <CalendarDays size={40} className="text-blue-200 mx-auto mb-3" />
                <p className="text-sm text-slate-400 mb-4">ยังไม่มีการจอง</p>
                <button onClick={() => navigate('/search')} className="bg-blue-700 text-white px-5 py-2 rounded-xl text-sm font-semibold hover:bg-blue-800 transition-colors">จองห้องเลย</button>
              </div>
            ) : (
              <div className="divide-y divide-blue-50">
                {bookings.slice(0, 20).map(b => {
                  const isActive    = b.status === 'approved'
                  const isCancelled = b.status === 'cancelled'
                  return (
                    <div key={b.id} onClick={() => setSelectedBooking(b)}
                      className={`px-6 py-4 flex items-center gap-4 cursor-pointer hover:bg-blue-50/40 transition-colors ${isCancelled ? 'opacity-40' : ''}`}>
                      <div className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{background: isActive ? '#10b981' : isCancelled ? '#cbd5e1' : '#fde047'}} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-bold text-slate-900 truncate">{b.room_name || `ห้อง #${b.room}`}</p>
                        <p className="text-xs text-slate-500 truncate mb-1">{b.title}</p>
                        <div className="flex gap-4 text-xs text-slate-400">
                          <span className="flex items-center gap-1"><CalendarDays size={10} />{fmtDate(b.start_time)}</span>
                          <span className="flex items-center gap-1"><Clock size={10} />{fmtTime(b.start_time)}–{fmtTime(b.end_time)}</span>
                          <span className="flex items-center gap-1"><Users size={10} />{b.attendees} คน</span>
                        </div>
                      </div>
                      <ChevronRight size={14} className="text-blue-200 flex-shrink-0" />
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      <BookingModal booking={selectedBooking} onClose={() => setSelectedBooking(null)}
        onCancel={handleCancel} fmtTime={fmtTime} fmtDateFull={fmtDateFull} />
    </div>
  )
}

// ── MOBILE ─────────────────────────────────────────────
function MobileHome({ user, bookings, notifications, unreadNotis, activeBookings, cancelledBookings,
  showNoti, setShowNoti, handleDismissNoti, handleLogout, navigate,
  selectedBooking, setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull }) {
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
              <button onClick={() => navigate('/admin')}
                className="w-8 h-8 rounded-lg border border-white/20 bg-white/10 flex items-center justify-center text-white hover:bg-white/20">
                <LayoutDashboard size={16} />
              </button>
            )}
            <div className="relative">
              <button onClick={() => setShowNoti(!showNoti)}
                className="w-8 h-8 rounded-lg border border-white/20 bg-white/10 flex items-center justify-center text-white hover:bg-white/20 relative">
                <Bell size={16} />
                {unreadNotis.length > 0 && <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-yellow-400 rounded-full" />}
              </button>
              {showNoti && <NotiDropdown notifications={notifications} onDismiss={handleDismissNoti} onClose={() => setShowNoti(false)} />}
            </div>
            <button onClick={handleLogout}
              className="w-8 h-8 rounded-lg border border-red-300/30 bg-white/10 flex items-center justify-center text-white hover:bg-red-500/20">
              <LogOut size={16} />
            </button>
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 space-y-3 pb-12">

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

        <div className="grid grid-cols-3 gap-2 au1">
          {[
            {label:'จองทั้งหมด', value: bookings.length,          color:'text-blue-700'},
            {label:'กำลังจอง',   value: activeBookings.length,    color:'text-emerald-600'},
            {label:'ยกเลิกแล้ว',value: cancelledBookings.length, color:'text-red-500'},
          ].map((s,i) => (
            <div key={i} className="bg-white border border-blue-100 rounded-2xl p-3 text-center shadow-sm">
              <p className={`text-2xl font-extrabold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>

        <div className="bg-white border border-blue-100 rounded-2xl overflow-hidden shadow-sm au2">
          <div className="px-5 py-3.5 flex justify-between items-center border-b border-blue-50">
            <span className="font-bold text-slate-900 text-sm">การจองของฉัน</span>
            <span className="text-xs text-slate-500 bg-blue-50 px-2.5 py-0.5 rounded-full">{bookings.length} รายการ</span>
          </div>
          {bookings.length === 0 ? (
            <div className="py-12 text-center">
              <CalendarDays size={36} className="text-blue-200 mx-auto mb-3" />
              <p className="text-sm text-slate-400 mb-4">ยังไม่มีการจอง</p>
              <button onClick={() => navigate('/search')} className="bg-blue-700 text-white px-5 py-2 rounded-xl text-sm font-semibold">จองห้องเลย</button>
            </div>
          ) : bookings.slice(0,20).map(b => {
            const isActive    = b.status === 'approved'
            const isCancelled = b.status === 'cancelled'
            return (
              <div key={b.id} onClick={() => setSelectedBooking(b)}
                className={`px-5 py-4 flex items-center gap-3 border-b border-blue-50 last:border-0 cursor-pointer hover:bg-blue-50/40 transition-colors ${isCancelled ? 'opacity-40' : ''}`}>
                <div className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
                  style={{background: isActive ? '#10b981' : isCancelled ? '#cbd5e1' : '#fde047'}} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-slate-900 truncate">{b.room_name || `ห้อง #${b.room}`}</p>
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
          })}
        </div>
      </div>

      <BookingModal booking={selectedBooking} onClose={() => setSelectedBooking(null)}
        onCancel={handleCancel} fmtTime={fmtTime} fmtDateFull={fmtDateFull} />
    </div>
  )
}

// ── ROOT ───────────────────────────────────────────────
export default function HomePage() {
  const navigate  = useNavigate()
  const isMobile  = useDevice()
  const [bookings, setBookings]         = useState([])
  const [notifications, setNotifications] = useState([])
  const [user, setUser]                 = useState(null)
  const [loading, setLoading]           = useState(true)
  const [showNoti, setShowNoti]         = useState(false)
  const [selectedBooking, setSelectedBooking] = useState(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [p,b,n] = await Promise.all([api.get('/auth/profile/'),api.get('/bookings/'),api.get('/notifications/')])
        setUser(p.data); setBookings(b.data.results||[]); setNotifications(n.data.results||[])
      } catch { navigate('/login') } finally { setLoading(false) }
    }; load()
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); localStorage.removeItem('user')
    navigate('/login')
  }
  const handleDismissNoti = async (id) => {
    try { await api.post(`/notifications/${id}/read/`); setNotifications(prev => prev.map(n => n.id===id?{...n,is_read:true}:n)) } catch {}
  }
  const handleCancel = async (id) => {
    if (!confirm('ยืนยันการยกเลิกการจองนี้?')) return
    try {
      await api.post(`/bookings/${id}/cancel/`)
      setBookings(prev => prev.map(b => b.id===id?{...b,status:'cancelled'}:b))
      if (selectedBooking?.id===id) setSelectedBooking(prev=>({...prev,status:'cancelled'}))
    } catch { alert('เกิดข้อผิดพลาด') }
  }

  const fmtDate     = dt => new Date(dt).toLocaleDateString('th-TH',{day:'numeric',month:'short',year:'2-digit'})
  const fmtTime     = dt => new Date(dt).toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit'})
  const fmtDateFull = dt => new Date(dt).toLocaleDateString('th-TH',{weekday:'long',day:'numeric',month:'long',year:'numeric'})

  const unreadNotis       = notifications.filter(n=>!n.is_read)
  const activeBookings    = bookings.filter(b=>b.status==='approved')
  const cancelledBookings = bookings.filter(b=>b.status==='cancelled')

  if (loading) return (
    <div className="min-h-screen bg-blue-50 flex flex-col items-center justify-center gap-3" style={{fontFamily:"'Sarabun',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="w-9 h-9 border-3 border-blue-200 border-t-blue-700 rounded-full" style={{animation:'rot .7s linear infinite',borderWidth:3}} />
      <p className="text-sm text-slate-500">กำลังโหลด...</p>
    </div>
  )

  const props = { user, bookings, notifications, unreadNotis, activeBookings, cancelledBookings,
    showNoti, setShowNoti, handleDismissNoti, handleLogout, navigate,
    selectedBooking, setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull }

  return isMobile ? <MobileHome {...props} /> : <DesktopHome {...props} />
}