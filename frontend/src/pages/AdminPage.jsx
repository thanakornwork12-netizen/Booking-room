import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Clock, BarChart2, TrendingUp, Calendar, X, ChevronDown, ChevronUp, Building2, AlertTriangle } from 'lucide-react'
import api from '../api/axios'

export default function AdminPage() {
  const navigate = useNavigate()
  const [dashboard, setDashboard] = useState(null)
  const [bookings, setBookings] = useState([])
  const [tab, setTab] = useState('active')
  const [loading, setLoading] = useState(true)
  const [weekStats, setWeekStats] = useState([])
  const [selectedBooking, setSelectedBooking] = useState(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [dashRes, bookingRes] = await Promise.all([
          api.get('/dashboard/'),
          api.get('/bookings/'),
        ])
        setDashboard(dashRes.data)
        const allBookings = bookingRes.data.results || []
        setBookings(allBookings)

        // คำนวณสถิติรายวัน 7 วันย้อนหลัง
        const stats = []
        const days = ['อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส']
        for (let i = 6; i >= 0; i--) {
          const d = new Date()
          d.setDate(d.getDate() - i)
          const dateStr = d.toISOString().split('T')[0]
          const count = allBookings.filter(b => {
            const bDate = new Date(b.start_time).toISOString().split('T')[0]
            return bDate === dateStr && b.status === 'approved'
          }).length
          stats.push({ day: days[d.getDay()], date: dateStr, count })
        }
        setWeekStats(stats)
      } catch {
        navigate('/login')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const handleCancel = async (id) => {
    if (!confirm('ยืนยันการยกเลิกการจองนี้?')) return
    try {
      await api.post(`/bookings/${id}/cancel/`)
      setBookings(prev => prev.map(b => b.id === id ? { ...b, status: 'cancelled' } : b))
      if (selectedBooking?.id === id) setSelectedBooking(prev => ({...prev, status: 'cancelled'}))
    } catch {
      alert('เกิดข้อผิดพลาด')
    }
  }

  const statusConfig = {
    approved:  { label: 'กำลังจอง',   bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
    cancelled: { label: 'ยกเลิกแล้ว', bg: 'bg-red-50',     text: 'text-red-600',    dot: 'bg-red-400' },
    completed: { label: 'เสร็จสิ้น',  bg: 'bg-gray-100',   text: 'text-gray-500',   dot: 'bg-gray-400' },
  }
  const getStatus = (s) => statusConfig[s] || { label: s, bg: 'bg-gray-100', text: 'text-gray-500', dot: 'bg-gray-400' }

  const formatTime = (dt) => new Date(dt).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
  const formatDate = (dt) => new Date(dt).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' })
  const formatDateFull = (dt) => new Date(dt).toLocaleDateString('th-TH', { weekday: 'long', day: 'numeric', month: 'long' })

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
    </div>
  )

  const activeBookings = bookings.filter(b => b.status === 'approved')
  const cancelledBookings = bookings.filter(b => b.status === 'cancelled')
  const maxCount = Math.max(...weekStats.map(s => s.count), 1)

  const tabs = [
    { key: 'active',   label: 'กำลังจอง', count: activeBookings.length },
    { key: 'overview', label: 'ภาพรวม',   count: null },
    { key: 'all',      label: 'ทั้งหมด',  count: bookings.length },
  ]

  return (
    <div className="min-h-screen bg-gray-50">

      {/* Header */}
      <div className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4">
          <div className="flex items-center gap-3 py-3">
            <button onClick={() => navigate('/')}
              className="p-2 rounded-xl hover:bg-gray-100 text-gray-500 transition-colors">
              <ArrowLeft size={18} />
            </button>
            <div className="flex-1">
              <h1 className="font-bold text-gray-800 text-sm">Admin Dashboard</h1>
              <p className="text-xs text-gray-400">จัดการการจองห้องประชุม</p>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex">
            {tabs.map(t => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors
                  ${tab === t.key ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-400 hover:text-gray-600'}`}>
                {t.label}
                {t.count !== null && (
                  <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold
                    ${tab === t.key ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-400'}`}>
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-4 space-y-3">

        {/* ===== Tab: กำลังจอง (DEFAULT) ===== */}
        {tab === 'active' && (
          <div className="space-y-2">

            {/* สรุปด่วน */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: 'กำลังจองวันนี้', value: dashboard?.today_bookings ?? 0, color: 'text-blue-600', bg: 'bg-blue-50' },
                { label: 'กำลังจองทั้งหมด', value: activeBookings.length, color: 'text-emerald-600', bg: 'bg-emerald-50' },
                { label: 'ยกเลิกแล้ว', value: cancelledBookings.length, color: 'text-red-500', bg: 'bg-red-50' },
              ].map((s, i) => (
                <div key={i} className={`${s.bg} rounded-2xl p-3 text-center`}>
                  <p className={`text-2xl font-black ${s.color}`}>{s.value}</p>
                  <p className={`text-xs mt-0.5 ${s.color} opacity-70`}>{s.label}</p>
                </div>
              ))}
            </div>

            {/* demand alerts */}
            {dashboard?.demand_alerts?.length > 0 && (
              <div className="bg-amber-50 border border-amber-100 rounded-2xl p-4">
                <p className="text-xs font-bold text-amber-700 flex items-center gap-1.5 mb-2">
                  <AlertTriangle size={13} /> ⚠️ AI คาดว่าช่วงนี้จะแน่น
                </p>
                <div className="space-y-1">
                  {dashboard.demand_alerts.slice(0, 3).map((a, i) => (
                    <div key={i} className="flex justify-between items-center text-xs">
                      <span className="text-amber-800 font-medium">{a.room__name}</span>
                      <span className="text-amber-600">{a.hour}:00 น.</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* รายการจองปัจจุบัน */}
            {activeBookings.length === 0 ? (
              <div className="bg-white rounded-2xl p-10 text-center shadow-sm">
                <Calendar size={40} className="text-gray-200 mx-auto mb-3" />
                <p className="text-gray-400 text-sm">ไม่มีการจองที่กำลังดำเนินอยู่</p>
              </div>
            ) : activeBookings.map(b => (
              <div key={b.id}
                className="bg-white rounded-2xl shadow-sm overflow-hidden cursor-pointer hover:shadow-md transition-all border-l-4 border-l-emerald-400"
                onClick={() => setSelectedBooking(b)}>
                <div className="p-4 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <p className="font-bold text-gray-800 text-sm truncate">{b.title}</p>
                      <span className="text-xs bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full shrink-0">กำลังจอง</span>
                    </div>
                    <p className="text-xs text-blue-500 font-medium mb-1">{b.room_name || `ห้อง #${b.room}`}</p>
                    <div className="flex items-center gap-3 text-xs text-gray-400">
                      <span>📅 {formatDate(b.start_time)}</span>
                      <span>⏰ {formatTime(b.start_time)}–{formatTime(b.end_time)}</span>
                      <span>👥 {b.attendees} คน</span>
                    </div>
                    {b.user_name && <p className="text-xs text-gray-300 mt-1">โดย {b.user_name}</p>}
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); handleCancel(b.id) }}
                    className="flex items-center gap-1 text-xs text-red-400 hover:text-red-600 hover:bg-red-50 px-2.5 py-1.5 rounded-xl transition-colors shrink-0">
                    <X size={12} /> ยกเลิก
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ===== Tab: ภาพรวม ===== */}
        {tab === 'overview' && dashboard && (
          <div className="space-y-3">

            {/* KPI */}
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'จองวันนี้',   value: dashboard.today_bookings ?? 0,        icon: '📅', color: 'bg-blue-50 text-blue-700' },
                { label: 'ห้องทั้งหมด', value: dashboard.total_rooms ?? 0,           icon: '🏢', color: 'bg-purple-50 text-purple-700' },
                { label: 'อัตราการใช้', value: `${dashboard.utilization_rate ?? 0}%`, icon: '📊', color: 'bg-green-50 text-green-700' },
                { label: 'จองทั้งหมด', value: activeBookings.length,                 icon: '✅', color: 'bg-orange-50 text-orange-700' },
              ].map((item, i) => (
                <div key={i} className="bg-white rounded-2xl p-4 shadow-sm">
                  <span className="text-2xl">{item.icon}</span>
                  <p className="text-2xl font-black text-gray-800 mt-1">{item.value}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{item.label}</p>
                </div>
              ))}
            </div>

            {/* สถิติรายวัน 7 วัน */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <p className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
                <BarChart2 size={15} className="text-blue-500" /> การจองรายวัน (7 วันล่าสุด)
              </p>
              <div className="flex items-end gap-2 h-24">
                {weekStats.map((s, i) => {
                  const h = maxCount > 0 ? Math.max((s.count / maxCount) * 100, 4) : 4
                  const isToday = i === 6
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1">
                      <span className="text-xs text-gray-400">{s.count > 0 ? s.count : ''}</span>
                      <div className="w-full rounded-t-lg transition-all"
                        style={{ height: `${h}%`, backgroundColor: isToday ? '#3b82f6' : '#bfdbfe' }} />
                      <span className={`text-xs font-medium ${isToday ? 'text-blue-600' : 'text-gray-400'}`}>
                        {s.day}
                      </span>
                    </div>
                  )
                })}
              </div>
              <div className="mt-3 pt-3 border-t border-gray-50 flex justify-between text-xs text-gray-400">
                <span>รวม 7 วัน: {weekStats.reduce((s, d) => s + d.count, 0)} การจอง</span>
                <span>เฉลี่ย: {(weekStats.reduce((s, d) => s + d.count, 0) / 7).toFixed(1)}/วัน</span>
              </div>
            </div>

            {/* ห้องยอดนิยม */}
            {dashboard.popular_rooms?.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm p-5">
                <p className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
                  <TrendingUp size={15} className="text-blue-500" /> ห้องที่ใช้บ่อย
                </p>
                <div className="space-y-3">
                  {dashboard.popular_rooms.map((room, i) => {
                    const max = dashboard.popular_rooms[0]?.count || 1
                    const pct = Math.round((room.count / max) * 100)
                    const colors = ['bg-blue-400','bg-indigo-400','bg-violet-400','bg-purple-400','bg-fuchsia-400']
                    return (
                      <div key={i} className="flex items-center gap-3">
                        <span className="text-xs font-black text-gray-300 w-4">{i + 1}</span>
                        <div className="flex-1">
                          <div className="flex justify-between mb-1">
                            <span className="text-sm text-gray-700 font-medium">{room.room__name}</span>
                            <span className="text-xs text-gray-400">{room.count} ครั้ง</span>
                          </div>
                          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${colors[i]}`} style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* demand alerts */}
            {dashboard.demand_alerts?.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm p-5">
                <p className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
                  <AlertTriangle size={15} className="text-amber-500" /> ช่วงที่คาดว่าจะแน่น (AI Forecast)
                </p>
                <div className="space-y-2">
                  {dashboard.demand_alerts.map((a, i) => (
                    <div key={i} className="flex justify-between items-center py-2 border-b border-gray-50 last:border-0">
                      <span className="text-sm text-gray-700">{a.room__name}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-400">{a.hour}:00 น.</span>
                        <span className="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded-full font-medium">
                          คาดว่าแน่น
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ===== Tab: ทั้งหมด ===== */}
        {tab === 'all' && (
          <div className="space-y-2">
            {bookings.length === 0 ? (
              <div className="bg-white rounded-2xl shadow-sm p-10 text-center">
                <p className="text-gray-400 text-sm">ยังไม่มีการจอง</p>
              </div>
            ) : bookings.map(b => {
              const s = getStatus(b.status)
              return (
                <div key={b.id}
                  className="bg-white rounded-xl shadow-sm px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => setSelectedBooking(b)}>
                  <div className={`w-2 h-2 rounded-full shrink-0 ${s.dot}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{b.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {b.room_name || `ห้อง #${b.room}`} · {formatDate(b.start_time)} · {formatTime(b.start_time)}–{formatTime(b.end_time)}
                    </p>
                  </div>
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium shrink-0 ${s.bg} ${s.text}`}>
                    {s.label}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ===== Modal รายละเอียด ===== */}
      {selectedBooking && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end justify-center sm:items-center px-4"
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedBooking(null) }}>
          <div className="bg-white w-full max-w-md rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden">
            <div className="px-5 py-4 flex items-center justify-between border-b border-gray-50">
              <div className="flex items-center gap-2">
                <div className={`w-2.5 h-2.5 rounded-full ${getStatus(selectedBooking.status).dot}`} />
                <p className="font-bold text-gray-800">รายละเอียดการจอง</p>
              </div>
              <button onClick={() => setSelectedBooking(null)}
                className="p-1.5 rounded-xl hover:bg-gray-100 text-gray-400">
                <X size={18} />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4">
              <div className="flex items-center gap-3 bg-blue-50 rounded-2xl p-4">
                <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center shrink-0">
                  <Building2 size={22} className="text-blue-600" />
                </div>
                <div>
                  <p className="font-bold text-gray-800 text-lg">{selectedBooking.room_name || `ห้อง #${selectedBooking.room}`}</p>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${getStatus(selectedBooking.status).bg} ${getStatus(selectedBooking.status).text}`}>
                    {getStatus(selectedBooking.status).label}
                  </span>
                </div>
              </div>

              <div className="border border-gray-100 rounded-2xl overflow-hidden">
                {[
                  { icon: '📋', label: 'หัวข้อ',     value: selectedBooking.title },
                  { icon: '📅', label: 'วันที่',      value: formatDateFull(selectedBooking.start_time) },
                  { icon: '⏰', label: 'เวลาเริ่ม',   value: formatTime(selectedBooking.start_time) + ' น.' },
                  { icon: '⏱️', label: 'เวลาสิ้นสุด', value: formatTime(selectedBooking.end_time) + ' น.' },
                  { icon: '👥', label: 'จำนวน',       value: `${selectedBooking.attendees} คน` },
                ].map((row, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-gray-50 last:border-0">
                    <span className="text-base w-6 shrink-0">{row.icon}</span>
                    <span className="text-xs text-gray-400 w-20 shrink-0">{row.label}</span>
                    <span className="text-sm font-medium text-gray-700 flex-1">{row.value}</span>
                  </div>
                ))}
              </div>

              <p className="text-xs text-gray-300 text-center">ID: #{selectedBooking.id}</p>

              {selectedBooking.status === 'approved' && (
                <button onClick={() => handleCancel(selectedBooking.id)}
                  className="w-full border-2 border-red-100 text-red-500 hover:bg-red-50 py-3 rounded-2xl font-semibold text-sm transition-colors">
                  ยกเลิกการจองนี้
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}