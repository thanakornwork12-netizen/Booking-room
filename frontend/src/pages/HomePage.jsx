import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { CalendarDays, Clock, Users, LogOut, Search, Bell, X, LayoutDashboard, MapPin, Building2, ChevronRight, Info } from 'lucide-react'
import api from '../api/axios'

export default function HomePage() {
  const navigate = useNavigate()
  const [bookings, setBookings] = useState([])
  const [notifications, setNotifications] = useState([])
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showNoti, setShowNoti] = useState(false)
  const [selectedBooking, setSelectedBooking] = useState(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [profileRes, bookingRes, notiRes] = await Promise.all([
          api.get('/auth/profile/'),
          api.get('/bookings/'),
          api.get('/notifications/'),
        ])
        setUser(profileRes.data)
        setBookings(bookingRes.data.results || [])
        setNotifications(notiRes.data.results || [])
      } catch {
        navigate('/login')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    navigate('/login')
  }

  const handleDismissNoti = async (id) => {
    try {
      await api.post(`/notifications/${id}/read/`)
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
    } catch {}
  }

  const handleCancel = async (id) => {
    if (!confirm('ยืนยันการยกเลิกการจองนี้?')) return
    try {
      await api.post(`/bookings/${id}/cancel/`)
      setBookings(prev => prev.map(b => b.id === id ? { ...b, status: 'cancelled' } : b))
      if (selectedBooking?.id === id) {
        setSelectedBooking(prev => ({ ...prev, status: 'cancelled' }))
      }
    } catch {
      alert('เกิดข้อผิดพลาด')
    }
  }

  const formatDate = (dt) => new Date(dt).toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' })
  const formatTime = (dt) => new Date(dt).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
  const formatDateFull = (dt) => new Date(dt).toLocaleDateString('th-TH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

  const unreadNotis = notifications.filter(n => !n.is_read)
  const activeBookings = bookings.filter(b => b.status === 'approved')
  const cancelledBookings = bookings.filter(b => b.status === 'cancelled')

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-gray-500 text-sm">กำลังโหลด...</p>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-50">

      {/* Navbar */}
      <div className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-3 flex justify-between items-center">
          <div>
            <h1 className="font-bold text-gray-800">สวัสดี, {user?.first_name || user?.username} 👋</h1>
            <p className="text-xs text-gray-400">{user?.faculty || 'ระบบจองห้องประชุม'}</p>
          </div>
          <div className="flex items-center gap-2">
            {user?.role && ['admin', 'staff'].includes(user.role) && (
              <button onClick={() => navigate('/admin')}
                className="p-2 rounded-xl hover:bg-gray-100 text-gray-500 transition-colors">
                <LayoutDashboard size={20} />
              </button>
            )}
            <div className="relative">
              <button onClick={() => setShowNoti(!showNoti)}
                className="p-2 rounded-xl hover:bg-gray-100 text-gray-500 transition-colors relative">
                <Bell size={20} />
                {unreadNotis.length > 0 && (
                  <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
                )}
              </button>
              {showNoti && (
                <div className="absolute right-0 top-12 w-80 bg-white rounded-2xl shadow-xl border border-gray-100 z-20 overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-50 flex justify-between items-center">
                    <p className="font-semibold text-gray-800 text-sm">การแจ้งเตือน</p>
                    <button onClick={() => setShowNoti(false)} className="text-gray-400 hover:text-gray-600">
                      <X size={16} />
                    </button>
                  </div>
                  {unreadNotis.length === 0 ? (
                    <p className="text-center text-gray-400 text-sm py-6">ไม่มีการแจ้งเตือน</p>
                  ) : (
                    <div className="max-h-64 overflow-y-auto">
                      {unreadNotis.map(n => (
                        <div key={n.id} className="px-4 py-3 hover:bg-gray-50 flex gap-3 items-start border-b border-gray-50 last:border-0">
                          <div className="w-2 h-2 bg-blue-500 rounded-full mt-1.5 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-700">{n.title}</p>
                            <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{n.message}</p>
                          </div>
                          <button onClick={() => handleDismissNoti(n.id)} className="text-gray-300 hover:text-gray-500 shrink-0">
                            <X size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            <button onClick={handleLogout}
              className="p-2 rounded-xl hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors">
              <LogOut size={20} />
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 py-5 space-y-4">

        {/* ปุ่มจองห้องใหญ่ */}
        <button onClick={() => navigate('/search')}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-2xl p-5 flex items-center justify-between transition-colors shadow-sm">
          <div className="text-left">
            <p className="font-bold text-lg">จองห้องประชุม</p>
            <p className="text-blue-200 text-sm mt-0.5">ค้นหาและจองห้องได้เลย</p>
          </div>
          <div className="bg-white/20 p-3 rounded-xl">
            <Search size={24} />
          </div>
        </button>

        {/* สถิติ */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: 'จองทั้งหมด', value: bookings.length,           color: 'text-gray-800' },
            { label: 'กำลังจอง',   value: activeBookings.length,     color: 'text-green-600' },
            { label: 'ยกเลิกแล้ว', value: cancelledBookings.length,  color: 'text-red-500' },
          ].map((s, i) => (
            <div key={i} className="bg-white rounded-2xl p-4 shadow-sm text-center">
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-gray-400 mt-1">{s.label}</p>
            </div>
          ))}
        </div>

        {/* รายการจอง */}
        <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 flex justify-between items-center border-b border-gray-50">
            <h2 className="font-semibold text-gray-800">การจองของฉัน</h2>
            <span className="text-xs text-gray-400">{bookings.length} รายการ</span>
          </div>

          {bookings.length === 0 ? (
            <div className="text-center py-12">
              <CalendarDays size={40} className="text-gray-200 mx-auto mb-3" />
              <p className="text-gray-400 text-sm mb-4">ยังไม่มีการจอง</p>
              <button onClick={() => navigate('/search')}
                className="bg-blue-600 text-white px-5 py-2 rounded-xl text-sm hover:bg-blue-700">
                จองห้องเลย
              </button>
            </div>
          ) : (
            <div>
              {bookings.slice(0, 20).map((b) => {
                const isActive = b.status === 'approved'
                const isCancelled = b.status === 'cancelled'
                return (
                  <div key={b.id}
                    className={`px-5 py-4 flex items-center gap-3 border-b border-gray-50 last:border-0 cursor-pointer hover:bg-gray-50 transition-colors
                      ${isCancelled ? 'opacity-50' : ''}`}
                    onClick={() => setSelectedBooking(b)}>

                    <div className={`w-2 h-2 rounded-full shrink-0
                      ${isActive ? 'bg-green-500' : isCancelled ? 'bg-gray-300' : 'bg-yellow-400'}`} />

                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-800 text-sm truncate">
                        {b.room_name || `ห้อง #${b.room}`}
                      </p>
                      <p className="text-xs text-gray-400 truncate">{b.title}</p>
                      <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                        <span className="flex items-center gap-1">
                          <CalendarDays size={10} /> {formatDate(b.start_time)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock size={10} /> {formatTime(b.start_time)}–{formatTime(b.end_time)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Users size={10} /> {b.attendees}
                        </span>
                      </div>
                    </div>

                    <ChevronRight size={14} className="text-gray-300 shrink-0" />
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* ===== Modal รายละเอียดการจอง ===== */}
      {selectedBooking && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end justify-center sm:items-center px-4"
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedBooking(null) }}>
          <div className="bg-white w-full max-w-md rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden">

            {/* Header */}
            <div className="px-5 py-4 flex items-center justify-between border-b border-gray-50">
              <div className="flex items-center gap-2">
                <div className={`w-2.5 h-2.5 rounded-full
                  ${selectedBooking.status === 'approved' ? 'bg-green-500' : 'bg-gray-300'}`} />
                <p className="font-bold text-gray-800">รายละเอียดการจอง</p>
              </div>
              <button onClick={() => setSelectedBooking(null)}
                className="p-1.5 rounded-xl hover:bg-gray-100 text-gray-400 transition-colors">
                <X size={18} />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4">

              {/* ห้อง */}
              <div className="flex items-center gap-3 bg-blue-50 rounded-2xl p-4">
                <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center shrink-0">
                  <Building2 size={22} className="text-blue-600" />
                </div>
                <div>
                  <p className="font-bold text-gray-800 text-lg">{selectedBooking.room_name || `ห้อง #${selectedBooking.room}`}</p>
                  <p className="text-xs text-blue-500 mt-0.5">
                    {selectedBooking.status === 'approved' ? '✅ กำลังจอง' : '❌ ยกเลิกแล้ว'}
                  </p>
                </div>
              </div>

              {/* รายละเอียด */}
              <div className="space-y-0 border border-gray-100 rounded-2xl overflow-hidden">
                {[
                  { icon: '📋', label: 'หัวข้อ',     value: selectedBooking.title },
                  { icon: '📅', label: 'วันที่',      value: formatDateFull(selectedBooking.start_time) },
                  { icon: '⏰', label: 'เวลาเริ่ม',   value: formatTime(selectedBooking.start_time) + ' น.' },
                  { icon: '⏱️', label: 'เวลาสิ้นสุด', value: formatTime(selectedBooking.end_time) + ' น.' },
                  { icon: '👥', label: 'จำนวนคน',    value: `${selectedBooking.attendees} คน` },
                ].map((row, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-gray-50 last:border-0 bg-white">
                    <span className="text-base w-6 shrink-0">{row.icon}</span>
                    <span className="text-xs text-gray-400 w-20 shrink-0">{row.label}</span>
                    <span className="text-sm font-medium text-gray-700 flex-1">{row.value}</span>
                  </div>
                ))}
              </div>

              {/* booking id */}
              <p className="text-xs text-gray-300 text-center">ID: #{selectedBooking.id}</p>

              {/* ปุ่มยกเลิก */}
              {selectedBooking.status === 'approved' && (
                <button
                  onClick={() => handleCancel(selectedBooking.id)}
                  className="w-full border-2 border-red-100 text-red-500 hover:bg-red-50 py-3 rounded-2xl font-semibold text-sm transition-colors">
                  ยกเลิกการจองนี้
                </button>
              )}

              {selectedBooking.status === 'cancelled' && (
                <div className="bg-gray-50 rounded-2xl px-4 py-3 text-center">
                  <p className="text-sm text-gray-400">การจองนี้ถูกยกเลิกแล้ว</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  )
}