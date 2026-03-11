import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Clock, BarChart2, TrendingUp, Home, Calendar, X } from 'lucide-react'
import api from '../api/axios'

export default function AdminPage() {
  const navigate = useNavigate()
  const [dashboard, setDashboard] = useState(null)
  const [bookings, setBookings] = useState([])
  const [tab, setTab] = useState('overview')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [dashRes, bookingRes] = await Promise.all([
          api.get('/dashboard/'),
          api.get('/bookings/'),
        ])
        setDashboard(dashRes.data)
        setBookings(bookingRes.data.results || [])
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
    } catch {
      alert('เกิดข้อผิดพลาด')
    }
  }

  const statusConfig = {
    approved:  { label: 'จองแล้ว',    bg: 'bg-green-50',  text: 'text-green-700',  dot: 'bg-green-500' },
    cancelled: { label: 'ยกเลิกแล้ว', bg: 'bg-red-50',    text: 'text-red-700',    dot: 'bg-red-500' },
    completed: { label: 'เสร็จสิ้น',  bg: 'bg-gray-50',   text: 'text-gray-600',   dot: 'bg-gray-400' },
  }

  const getStatus = (s) => statusConfig[s] || { label: s, bg: 'bg-gray-50', text: 'text-gray-600', dot: 'bg-gray-400' }

  const demandConfig = {
    low:    { label: 'ว่างสูง',    color: 'text-green-600', bar: 'bg-green-400' },
    medium: { label: 'ปานกลาง',   color: 'text-yellow-600', bar: 'bg-yellow-400' },
    high:   { label: 'เต็มสูง',   color: 'text-red-600',   bar: 'bg-red-400' },
  }

  const formatTime = (dt) => new Date(dt).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
  const formatDate = (dt) => new Date(dt).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' })

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-gray-500 text-sm">กำลังโหลด...</p>
      </div>
    </div>
  )

  const activeBookings = bookings.filter(b => b.status === 'approved')
  const cancelledBookings = bookings.filter(b => b.status === 'cancelled')

  const tabs = [
    { key: 'overview', label: 'ภาพรวม', icon: BarChart2, count: null },
    { key: 'active',   label: 'กำลังจอง', icon: Calendar, count: activeBookings.length },
    { key: 'all',      label: 'ทั้งหมด', icon: Users, count: bookings.length },
  ]

  return (
    <div className="min-h-screen bg-gray-50">

      {/* Header */}
      <div className="bg-white border-b border-gray-100">
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex items-center gap-3 py-4">
            <button onClick={() => navigate('/')}
              className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors">
              <ArrowLeft size={18} />
            </button>
            <div>
              <h1 className="font-bold text-gray-800">Admin Dashboard</h1>
              <p className="text-xs text-gray-400">จัดการการจองห้องประชุม</p>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-1">
            {tabs.map(t => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors
                  ${tab === t.key
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
                <t.icon size={15} />
                {t.label}
                {t.count !== null && (
                  <span className={`px-1.5 py-0.5 rounded-full text-xs font-bold
                    ${tab === t.key ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-500'}`}>
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">

        {/* ===== Tab: ภาพรวม ===== */}
        {tab === 'overview' && dashboard && (
          <>
            {/* KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { icon: Calendar,   label: 'จองวันนี้',     value: dashboard.today_bookings ?? 0,     color: 'blue' },
                { icon: Home,       label: 'ห้องทั้งหมด',   value: dashboard.total_rooms ?? 0,        color: 'purple' },
                { icon: TrendingUp, label: 'อัตราการใช้',   value: `${dashboard.utilization_rate ?? 0}%`, color: 'green' },
                { icon: Users,      label: 'จองทั้งหมด',    value: activeBookings.length,             color: 'orange' },
              ].map((item, i) => {
                const colors = {
                  blue:   'bg-blue-50 text-blue-600',
                  purple: 'bg-purple-50 text-purple-600',
                  green:  'bg-green-50 text-green-600',
                  orange: 'bg-orange-50 text-orange-600',
                }
                return (
                  <div key={i} className="bg-white rounded-2xl p-4 shadow-sm">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-3 ${colors[item.color]}`}>
                      <item.icon size={18} />
                    </div>
                    <p className="text-2xl font-bold text-gray-800">{item.value}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{item.label}</p>
                  </div>
                )
              })}
            </div>

            {/* ห้องยอดนิยม */}
            {dashboard.popular_rooms?.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm p-5">
                <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
                  <TrendingUp size={16} className="text-blue-500" /> ห้องที่ใช้บ่อย
                </h2>
                <div className="space-y-3">
                  {dashboard.popular_rooms.map((room, i) => {
                    const max = dashboard.popular_rooms[0]?.count || 1
                    const pct = Math.round((room.count / max) * 100)
                    return (
                      <div key={i} className="flex items-center gap-3">
                        <span className="text-xs font-bold text-gray-300 w-4">{i + 1}</span>
                        <div className="flex-1">
                          <div className="flex justify-between mb-1">
                            <span className="text-sm text-gray-700">{room.room__name}</span>
                            <span className="text-xs text-gray-400">{room.count} ครั้ง</span>
                          </div>
                          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div className="h-full bg-blue-400 rounded-full transition-all"
                              style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Demand Alerts จาก LSTM */}
            {dashboard.demand_alerts?.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm p-5">
                <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
                  <Clock size={16} className="text-orange-500" /> ช่วงที่คาดว่าจะแน่น (LSTM)
                </h2>
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
          </>
        )}

        {/* ===== Tab: กำลังจอง ===== */}
        {tab === 'active' && (
          <div className="space-y-3">
            {activeBookings.length === 0 ? (
              <div className="bg-white rounded-2xl shadow-sm p-10 text-center">
                <Calendar size={40} className="text-gray-200 mx-auto mb-3" />
                <p className="text-gray-400">ไม่มีการจองที่กำลังดำเนินอยู่</p>
              </div>
            ) : activeBookings.map(b => (
              <div key={b.id} className="bg-white rounded-2xl shadow-sm p-4">
                <div className="flex justify-between items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-gray-800 truncate">{b.title}</p>
                    <p className="text-sm text-blue-600 mt-0.5">{b.room_name || `ห้อง #${b.room}`}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                      <span className="flex items-center gap-1">
                        <Calendar size={11} /> {formatDate(b.start_time)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock size={11} /> {formatTime(b.start_time)} – {formatTime(b.end_time)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Users size={11} /> {b.attendees} คน
                      </span>
                    </div>
                  </div>
                  <button onClick={() => handleCancel(b.id)}
                    className="flex items-center gap-1 text-xs text-red-500 hover:bg-red-50 px-3 py-1.5 rounded-lg transition-colors shrink-0">
                    <X size={13} /> ยกเลิก
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ===== Tab: ทั้งหมด ===== */}
        {tab === 'all' && (
          <div className="space-y-2">
            {bookings.length === 0 ? (
              <div className="bg-white rounded-2xl shadow-sm p-10 text-center">
                <p className="text-gray-400">ยังไม่มีการจอง</p>
              </div>
            ) : bookings.map(b => {
              const s = getStatus(b.status)
              return (
                <div key={b.id} className="bg-white rounded-xl shadow-sm px-4 py-3 flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${s.dot}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{b.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {b.room_name || `ห้อง #${b.room}`} • {formatDate(b.start_time)} • {formatTime(b.start_time)}–{formatTime(b.end_time)}
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
    </div>
  )
}