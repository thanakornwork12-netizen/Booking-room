import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Clock, CheckCircle, AlertCircle, XCircle, Building2, Zap, TrendingUp, ChevronRight } from 'lucide-react'
import api from '../api/axios'

const BUILDINGS = [
  { code: '',     label: 'ทุกตึก',        icon: '🏫' },
  { code: 'SC',   label: 'วิทยาศาสตร์',   icon: '🔬' },
  { code: 'EN',   label: 'วิศวกรรม',      icon: '⚙️' },
  { code: 'BA',   label: 'บริหาร',         icon: '💼' },
  { code: 'LIB',  label: 'ห้องสมุด',       icon: '📚' },
  { code: 'MED',  label: 'แพทย์',          icon: '🏥' },
  { code: 'ART',  label: 'ศิลปศาสตร์',     icon: '🎨' },
  { code: 'AGR',  label: 'เกษตร',          icon: '🌾' },
  { code: 'NUR',  label: 'พยาบาล',         icon: '💊' },
  { code: 'MAIN', label: 'สำนักงาน',       icon: '🏛️' },
]

const TIME_SLOTS = [
  '08:00','09:00','10:00','11:00',
  '13:00','14:00','15:00','16:00',
]

const DURATIONS = [
  { label: '1 ชม.', hours: 1 },
  { label: '2 ชม.', hours: 2 },
  { label: '3 ชม.', hours: 3 },
]

const ATTENDEES_PRESETS = [2, 5, 10, 20, 30, 50]

const FACILITIES = [
  { value: 'โปรเจกเตอร์', label: '📽️ Projector' },
  { value: 'ไวท์บอร์ด',   label: '📋 Whiteboard' },
  { value: 'ไมโครโฟน',    label: '🎤 Mic' },
  { value: 'คอมพิวเตอร์', label: '💻 Computer' },
  { value: 'ระบบเสียง',   label: '🔊 Sound' },
  { value: 'TV',           label: '📺 TV' },
]

const FORECAST_CONFIG = {
  low:    { icon: <CheckCircle size={13} />,  badge: 'ว่าง',      badgeCls: 'bg-emerald-50 text-emerald-700', border: 'border-l-emerald-400', bar: 'bg-emerald-400', barW: '20%', sort: 0, label: '✅ แนะนำ',    labelCls: 'text-emerald-600' },
  medium: { icon: <AlertCircle size={13} />,  badge: 'เริ่มแน่น', badgeCls: 'bg-amber-50 text-amber-700',     border: 'border-l-amber-400',   bar: 'bg-amber-400',   barW: '60%', sort: 1, label: '⚡ จองด่วน',  labelCls: 'text-amber-600' },
  high:   { icon: <XCircle size={13} />,      badge: 'แน่น',      badgeCls: 'bg-rose-50 text-rose-700',       border: 'border-l-rose-400',    bar: 'bg-rose-400',    barW: '90%', sort: 2, label: '⚠️ เกือบเต็ม', labelCls: 'text-rose-500' },
  none:   { icon: <Building2 size={13} />,    badge: '-',          badgeCls: 'bg-gray-50 text-gray-400',       border: 'border-l-gray-200',    bar: 'bg-gray-200',    barW: '0%',  sort: 3, label: '',            labelCls: 'text-gray-400' },
}

const inputClass = "w-full border border-gray-200 bg-gray-50 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white transition-all"

const addHours = (time, hours) => {
  const [h, m] = time.split(':').map(Number)
  return `${String(h + hours).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export default function SearchPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)

  const [attendees, setAttendees] = useState(5)
  const [date, setDate]           = useState(new Date().toISOString().split('T')[0])
  const [startTime, setStartTime] = useState('')
  const [duration, setDuration]   = useState(1)
  const [building, setBuilding]   = useState('')
  const [facilities, setFacilities] = useState([])

  const [rooms, setRooms]               = useState([])
  const [selectedRoom, setSelectedRoom] = useState(null)
  const [title, setTitle]               = useState('')
  const [loading, setLoading]           = useState(false)
  const [bookingLoading, setBookingLoading] = useState(false)
  const [success, setSuccess]           = useState(false)
  const [error, setError]               = useState('')

  const endTime = startTime ? addHours(startTime, duration) : ''

  const toggleFacility = (val) =>
    setFacilities(prev => prev.includes(val) ? prev.filter(f => f !== val) : [...prev, val])

  const handleSearch = async () => {
    if (!startTime) { setError('กรุณาเลือกเวลา'); return }
    setError('')
    setLoading(true)
    try {
      const res = await api.post('/rooms/search/', {
        attendees,
        date,
        start_time: startTime,
        end_time: endTime,
        building_code: building || undefined,
        facilities,
      })
      const sorted = [...res.data].sort((a, b) =>
        FORECAST_CONFIG[a.forecast?.demand_level || 'none'].sort -
        FORECAST_CONFIG[b.forecast?.demand_level || 'none'].sort
      )
      setRooms(sorted)
      setStep(2)
    } catch {
      setError('เกิดข้อผิดพลาด กรุณาลองใหม่')
    } finally {
      setLoading(false)
    }
  }

  const handleBook = async () => {
    if (!title.trim()) { setError('กรุณากรอกหัวข้อ'); return }
    setBookingLoading(true)
    setError('')
    try {
      await api.post('/bookings/', {
        room: selectedRoom.id,
        title,
        attendees,
        start_time: `${date}T${startTime}:00+07:00`,
        end_time:   `${date}T${endTime}:00+07:00`,
      })
      setSuccess(true)
    } catch {
      setError('จองไม่สำเร็จ กรุณาลองใหม่')
    } finally {
      setBookingLoading(false)
    }
  }

  const formatDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', {
    weekday: 'short', day: 'numeric', month: 'short'
  })

  if (success) return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 to-teal-100 flex items-center justify-center px-4">
      <div className="bg-white rounded-3xl shadow-xl p-8 text-center max-w-sm w-full">
        <div className="w-20 h-20 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-5">
          <CheckCircle size={42} className="text-emerald-500" />
        </div>
        <h2 className="text-xl font-bold text-gray-800 mb-1">จองสำเร็จ!</h2>
        <p className="text-blue-600 font-bold text-lg mb-1">{selectedRoom?.name}</p>
        <p className="text-gray-400 text-sm">{formatDate(date)}</p>
        <p className="text-gray-400 text-sm mb-6">{startTime} – {endTime} น.</p>
        <button onClick={() => navigate('/')}
          className="w-full bg-blue-600 text-white py-3 rounded-2xl font-bold hover:bg-blue-700 transition-colors">
          กลับหน้าหลัก
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-50">

      {/* Header */}
      <div className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-lg mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={() => step === 1 ? navigate('/') : setStep(step - 1)}
            className="p-2 rounded-xl hover:bg-gray-100 text-gray-500 transition-colors">
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1">
            <p className="font-bold text-gray-800 text-sm">
              {step === 1 ? 'จองห้องประชุม' : step === 2 ? `พบ ${rooms.length} ห้อง` : 'ยืนยันการจอง'}
            </p>
            <div className="flex gap-1 mt-1">
              {[1,2,3].map(s => (
                <div key={s} className={`h-0.5 flex-1 rounded-full transition-all ${step >= s ? 'bg-blue-500' : 'bg-gray-200'}`} />
              ))}
            </div>
          </div>
          <span className="text-xs text-gray-400">{step}/3</span>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 space-y-3">

        {error && (
          <div className="bg-red-50 border border-red-100 text-red-600 text-sm px-4 py-3 rounded-xl">
            {error}
          </div>
        )}

        {/* ===== STEP 1 ===== */}
        {step === 1 && (
          <div className="space-y-3">

            {/* จำนวนคน */}
            <div className="bg-white rounded-2xl shadow-sm p-4">
              <p className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-3">จำนวนผู้เข้าร่วม</p>
              <div className="flex items-center gap-3 mb-3">
                <button onClick={() => setAttendees(Math.max(1, attendees - 1))}
                  className="w-10 h-10 rounded-xl bg-gray-100 text-gray-600 font-bold text-xl flex items-center justify-center hover:bg-gray-200 transition-colors">−</button>
                <div className="flex-1 text-center">
                  <span className="text-4xl font-black text-blue-600">{attendees}</span>
                  <span className="text-sm text-gray-400 ml-1.5">คน</span>
                </div>
                <button onClick={() => setAttendees(attendees + 1)}
                  className="w-10 h-10 rounded-xl bg-blue-600 text-white font-bold text-xl flex items-center justify-center hover:bg-blue-700 transition-colors">+</button>
              </div>
              <div className="flex gap-1.5">
                {ATTENDEES_PRESETS.map(n => (
                  <button key={n} onClick={() => setAttendees(n)}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all
                      ${attendees === n ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
                    {n}
                  </button>
                ))}
              </div>
            </div>

            {/* วันที่ + เวลา */}
            <div className="bg-white rounded-2xl shadow-sm p-4">
              <p className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-3">วันและเวลา</p>
              <input type="date" className={`${inputClass} mb-3`}
                value={date} min={new Date().toISOString().split('T')[0]}
                onChange={e => setDate(e.target.value)} />
              <p className="text-xs text-gray-400 mb-2">เวลาเริ่ม</p>
              <div className="grid grid-cols-4 gap-1.5 mb-3">
                {TIME_SLOTS.map(t => (
                  <button key={t} onClick={() => setStartTime(t)}
                    className={`py-2 rounded-xl text-xs font-bold border-2 transition-all
                      ${startTime === t ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-transparent bg-gray-50 text-gray-500 hover:bg-gray-100'}`}>
                    {t}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-400 mb-2">ระยะเวลา</p>
              <div className="flex gap-2">
                {DURATIONS.map(d => (
                  <button key={d.hours} onClick={() => setDuration(d.hours)}
                    className={`flex-1 py-2 rounded-xl text-xs font-bold border-2 transition-all
                      ${duration === d.hours ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-transparent bg-gray-50 text-gray-500 hover:bg-gray-100'}`}>
                    {d.label}
                  </button>
                ))}
              </div>
              {startTime && (
                <div className="mt-3 bg-blue-50 rounded-xl px-3 py-2 flex items-center gap-2">
                  <Clock size={13} className="text-blue-500" />
                  <span className="text-sm text-blue-700 font-bold">{startTime} – {endTime} น.</span>
                  <span className="text-xs text-blue-400 ml-auto">{formatDate(date)}</span>
                </div>
              )}
            </div>

            {/* อาคาร */}
            <div className="bg-white rounded-2xl shadow-sm p-4">
              <p className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-3">อาคาร</p>
              <div className="grid grid-cols-5 gap-1.5">
                {BUILDINGS.map(b => (
                  <button key={b.code} onClick={() => setBuilding(b.code)}
                    className={`py-2 px-1 rounded-xl text-center transition-all border-2
                      ${building === b.code ? 'border-blue-500 bg-blue-50' : 'border-transparent bg-gray-50 hover:bg-gray-100'}`}>
                    <div className="text-lg mb-0.5">{b.icon}</div>
                    <p className={`text-xs font-medium leading-tight ${building === b.code ? 'text-blue-700' : 'text-gray-500'}`}>
                      {b.code === '' ? 'ทั้งหมด' : b.code}
                    </p>
                  </button>
                ))}
              </div>
            </div>

            {/* อุปกรณ์ */}
            <div className="bg-white rounded-2xl shadow-sm p-4">
              <div className="flex justify-between items-center mb-3">
                <p className="text-xs font-bold text-gray-400 uppercase tracking-wide">อุปกรณ์ที่ต้องการ</p>
                {facilities.length > 0 && (
                  <button onClick={() => setFacilities([])} className="text-xs text-gray-400 hover:text-red-400">ล้าง</button>
                )}
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                {FACILITIES.map(f => (
                  <button key={f.value} onClick={() => toggleFacility(f.value)}
                    className={`py-2 px-2 rounded-xl text-xs font-medium border-2 text-center transition-all
                      ${facilities.includes(f.value) ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-transparent bg-gray-50 text-gray-500 hover:bg-gray-100'}`}>
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <button onClick={handleSearch} disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-3.5 rounded-2xl font-bold text-base transition-colors shadow-sm">
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  กำลังค้นหา...
                </span>
              ) : '🔍 ค้นหาห้องว่าง'}
            </button>
          </div>
        )}

        {/* ===== STEP 2 ===== */}
        {step === 2 && (
          <div className="space-y-2">

            <div className="bg-white rounded-2xl shadow-sm px-4 py-3 flex items-center gap-2 text-xs text-gray-500 flex-wrap">
              <span className="font-bold text-gray-800">{attendees} คน</span>
              <span>·</span>
              <span>{formatDate(date)}</span>
              <span>·</span>
              <span>{startTime}–{endTime}</span>
              {building && <><span>·</span><span>{BUILDINGS.find(b => b.code === building)?.icon} {building}</span></>}
              <span className="ml-auto flex items-center gap-1 text-blue-500">
                <TrendingUp size={11} /> AI Forecast
              </span>
            </div>

            {rooms.length > 0 && (
              <div className="flex gap-2">
                {[
                  { level: 'low',    label: 'ว่าง',      cls: 'bg-emerald-50 text-emerald-700' },
                  { level: 'medium', label: 'เริ่มแน่น',  cls: 'bg-amber-50 text-amber-700' },
                  { level: 'high',   label: 'เกือบเต็ม', cls: 'bg-rose-50 text-rose-700' },
                ].map(s => (
                  <div key={s.level} className={`flex-1 ${s.cls} rounded-xl py-2 text-center`}>
                    <p className="text-xl font-black">{rooms.filter(r => (r.forecast?.demand_level || 'none') === s.level).length}</p>
                    <p className="text-xs opacity-80">{s.label}</p>
                  </div>
                ))}
              </div>
            )}

            {rooms.length === 0 ? (
              <div className="bg-white rounded-2xl p-10 text-center">
                <Building2 size={36} className="text-gray-200 mx-auto mb-3" />
                <p className="text-gray-500 font-medium mb-1">ไม่พบห้องว่าง</p>
                <p className="text-gray-400 text-sm mb-4">ลองเปลี่ยนเวลาหรืออาคาร</p>
                <button onClick={() => setStep(1)} className="text-blue-600 text-sm font-medium">← ค้นหาใหม่</button>
              </div>
            ) : rooms.map((room, idx) => {
              const level = room.forecast?.demand_level || 'none'
              const cfg = FORECAST_CONFIG[level]
              const isTop = idx === 0 && level === 'low'

              return (
                <div key={room.id}
                  className={`bg-white rounded-2xl shadow-sm overflow-hidden cursor-pointer hover:shadow-md transition-all border-l-4 ${cfg.border}`}
                  onClick={() => { setSelectedRoom(room); setStep(3) }}>

                  {isTop && (
                    <div className="bg-emerald-500 px-3 py-1 flex items-center gap-1.5">
                      <Zap size={12} className="text-white" />
                      <span className="text-white text-xs font-bold">แนะนำ</span>
                    </div>
                  )}

                  <div className="p-4 flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                        <p className="font-bold text-gray-800 text-sm">{room.name}</p>
                        <span className={`text-xs px-1.5 py-0.5 rounded-md font-medium ${cfg.badgeCls}`}>
                          {cfg.icon} {cfg.badge}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 mb-2">
                        {room.building_name} · ชั้น {room.floor} · {room.capacity} คน · {room.room_type}
                      </p>

                      {room.facilities?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-2">
                          {room.facilities.map((f, i) => (
                            <span key={i} className={`text-xs px-1.5 py-0.5 rounded-md
                              ${facilities.includes(f.name) ? 'bg-blue-100 text-blue-700 font-medium' : 'bg-gray-100 text-gray-400'}`}>
                              {f.name}
                            </span>
                          ))}
                        </div>
                      )}

                      {room.forecast && (
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1 bg-gray-100 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${cfg.bar}`} style={{ width: cfg.barW }} />
                          </div>
                          <span className="text-xs text-gray-400">{room.forecast.confidence}%</span>
                          <span className={`text-xs font-semibold ${cfg.labelCls}`}>{cfg.label}</span>
                        </div>
                      )}
                    </div>
                    <ChevronRight size={16} className="text-gray-300 shrink-0" />
                  </div>
                </div>
              )
            })}

            {rooms.length > 0 && (
              <p className="text-center text-xs text-gray-400 py-2">🤖 เรียงตาม AI Forecast</p>
            )}
          </div>
        )}

        {/* ===== STEP 3 ===== */}
        {step === 3 && selectedRoom && (
          <div className="space-y-3">
            <div className="bg-white rounded-2xl shadow-sm p-4">
              <div className="flex items-start gap-3 mb-4">
                <div className="w-11 h-11 bg-blue-50 rounded-xl flex items-center justify-center shrink-0">
                  <Building2 size={20} className="text-blue-600" />
                </div>
                <div>
                  <p className="font-bold text-gray-800">{selectedRoom.name}</p>
                  <p className="text-xs text-gray-400">{selectedRoom.building_name} · ชั้น {selectedRoom.floor} · {selectedRoom.room_type}</p>
                </div>
              </div>

              {[
                { icon: '📅', value: formatDate(date) },
                { icon: '⏰', value: `${startTime} – ${endTime} น.` },
                { icon: '👥', value: `${attendees} คน` },
              ].map((r, i) => (
                <div key={i} className="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0">
                  <span className="text-base w-6">{r.icon}</span>
                  <span className="text-sm font-medium text-gray-700">{r.value}</span>
                </div>
              ))}

              {selectedRoom.facilities?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {selectedRoom.facilities.map((f, i) => (
                    <span key={i} className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-md">{f.name}</span>
                  ))}
                </div>
              )}

              {selectedRoom.forecast && (() => {
                const level = selectedRoom.forecast.demand_level || 'none'
                const cfg = FORECAST_CONFIG[level]
                return (
                  <div className={`mt-3 rounded-xl px-3 py-2 flex items-center gap-2
                    ${level === 'low' ? 'bg-emerald-50' : level === 'medium' ? 'bg-amber-50' : 'bg-rose-50'}`}>
                    {cfg.icon}
                    <span className={`text-xs font-semibold ${cfg.labelCls}`}>
                      {cfg.label} · ความมั่นใจ {selectedRoom.forecast.confidence}%
                    </span>
                  </div>
                )
              })()}
            </div>

            <div className="bg-white rounded-2xl shadow-sm p-4">
              <label className="block text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">หัวข้อการประชุม</label>
              <input type="text" placeholder="เช่น ประชุมกลุ่ม, นำเสนองาน..."
                className={inputClass} value={title}
                onChange={e => setTitle(e.target.value)} autoFocus />
            </div>

            <button onClick={handleBook} disabled={bookingLoading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-3.5 rounded-2xl font-bold text-base transition-colors shadow-sm">
              {bookingLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  กำลังจอง...
                </span>
              ) : '✓ ยืนยันการจอง'}
            </button>
          </div>
        )}

      </div>
    </div>
  )
}