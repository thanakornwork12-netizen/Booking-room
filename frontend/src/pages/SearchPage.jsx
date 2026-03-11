import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Clock, MapPin, CheckCircle, AlertCircle, XCircle, Building2, Zap, TrendingUp } from 'lucide-react'
import api from '../api/axios'

const TIME_SLOTS = [
  { label: 'เช้า 08:00', start: '08:00', end: '10:00' },
  { label: 'เช้า 10:00', start: '10:00', end: '12:00' },
  { label: 'เที่ยง 12:00', start: '12:00', end: '14:00' },
  { label: 'บ่าย 13:00', start: '13:00', end: '15:00' },
  { label: 'บ่าย 14:00', start: '14:00', end: '16:00' },
  { label: 'บ่าย 15:00', start: '15:00', end: '17:00' },
  { label: 'เย็น 16:00', start: '16:00', end: '18:00' },
]

const DURATIONS = [
  { label: '1 ชม.', hours: 1 },
  { label: '2 ชม.', hours: 2 },
  { label: '3 ชม.', hours: 3 },
  { label: 'กำหนดเอง', hours: 0 },
]

const ROOM_TYPES = [
  { value: '', label: 'ทั้งหมด' },
  { value: 'ห้องประชุม', label: '🏢 ประชุม' },
  { value: 'ห้องประชุมเล็ก', label: '👥 ประชุมเล็ก' },
  { value: 'ห้องปฏิบัติการ', label: '🔬 Lab' },
  { value: 'ห้องอเนกประสงค์', label: '✨ อเนกประสงค์' },
]

const FACILITIES = [
  { value: 'โปรเจกเตอร์', label: '📽️ โปรเจกเตอร์' },
  { value: 'ไวท์บอร์ด',   label: '📋 ไวท์บอร์ด' },
  { value: 'ไมโครโฟน',    label: '🎤 ไมโครโฟน' },
  { value: 'คอมพิวเตอร์', label: '💻 คอมพิวเตอร์' },
  { value: 'ระบบเสียง',   label: '🔊 ระบบเสียง' },
  { value: 'TV',           label: '📺 TV' },
]

const inputClass = "w-full border border-gray-200 bg-gray-50 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:bg-white transition-colors"

const addHours = (time, hours) => {
  const [h, m] = time.split(':').map(Number)
  const total = h + hours
  return `${String(total).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

const FORECAST_CONFIG = {
  low: {
    icon: <CheckCircle size={14} />,
    badge: 'ว่างสูง',
    badgeCls: 'bg-green-50 text-green-700 border border-green-100',
    recommend: '✅ แนะนำให้จองตอนนี้',
    recommendCls: 'text-green-600',
    cardBorder: 'border-l-4 border-l-green-400',
    barColor: 'bg-green-400',
    barWidth: '25%',
    sortOrder: 0,
    tip: 'ช่วงเวลานี้คาดว่าไม่แน่น เหมาะจองมาก',
  },
  medium: {
    icon: <AlertCircle size={14} />,
    badge: 'เริ่มแน่น',
    badgeCls: 'bg-yellow-50 text-yellow-700 border border-yellow-100',
    recommend: '⚡ ควรจองเร็ว ๆ นี้',
    recommendCls: 'text-yellow-600',
    cardBorder: 'border-l-4 border-l-yellow-400',
    barColor: 'bg-yellow-400',
    barWidth: '60%',
    sortOrder: 1,
    tip: 'มีโอกาสเต็มสูง ยิ่งจองเร็วยิ่งดี',
  },
  high: {
    icon: <XCircle size={14} />,
    badge: 'แน่นมาก',
    badgeCls: 'bg-red-50 text-red-700 border border-red-100',
    recommend: '⚠️ ช่วงนี้คาดว่าเต็ม',
    recommendCls: 'text-red-500',
    cardBorder: 'border-l-4 border-l-red-400',
    barColor: 'bg-red-400',
    barWidth: '90%',
    sortOrder: 2,
    tip: 'AI คาดว่าความต้องการช่วงนี้สูงมาก',
  },
  none: {
    icon: <Building2 size={14} />,
    badge: 'ไม่มีข้อมูล',
    badgeCls: 'bg-gray-50 text-gray-500 border border-gray-100',
    recommend: 'ไม่มีข้อมูลการพยากรณ์',
    recommendCls: 'text-gray-400',
    cardBorder: 'border-l-4 border-l-gray-200',
    barColor: 'bg-gray-300',
    barWidth: '0%',
    sortOrder: 3,
    tip: '',
  },
}

export default function SearchPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    attendees: '',
    date: new Date().toISOString().split('T')[0],
    start_time: '',
    end_time: '',
    room_type: '',
  })
  const [selectedSlot, setSelectedSlot] = useState(null)
  const [selectedDuration, setSelectedDuration] = useState(1)
  const [customTime, setCustomTime] = useState(false)
  const [selectedFacilities, setSelectedFacilities] = useState([])
  const [rooms, setRooms] = useState([])
  const [selectedRoom, setSelectedRoom] = useState(null)
  const [loading, setLoading] = useState(false)
  const [bookingLoading, setBookingLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [title, setTitle] = useState('')
  const [error, setError] = useState('')

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const toggleFacility = (val) => {
    setSelectedFacilities(prev =>
      prev.includes(val) ? prev.filter(f => f !== val) : [...prev, val]
    )
  }

  const handleSelectSlot = (slot) => {
    setSelectedSlot(slot.label)
    set('start_time', slot.start)
    if (!customTime) {
      set('end_time', addHours(slot.start, selectedDuration || 1))
    }
  }

  const handleSelectDuration = (d) => {
    setSelectedDuration(d.hours)
    if (d.hours === 0) {
      setCustomTime(true)
    } else {
      setCustomTime(false)
      if (form.start_time) {
        set('end_time', addHours(form.start_time, d.hours))
      }
    }
  }

  const handleSearch = async () => {
    if (!form.attendees || !form.date || !form.start_time || !form.end_time) {
      setError('กรุณากรอกข้อมูลให้ครบ')
      return
    }
    setError('')
    setLoading(true)
    try {
      const res = await api.post('/rooms/search/', {
        ...form,
        facilities: selectedFacilities,
      })

      const sorted = [...res.data].sort((a, b) => {
        const aOrder = FORECAST_CONFIG[a.forecast?.demand_level || 'none'].sortOrder
        const bOrder = FORECAST_CONFIG[b.forecast?.demand_level || 'none'].sortOrder
        return aOrder - bOrder
      })

      setRooms(sorted)
      setStep(2)
    } catch {
      setError('เกิดข้อผิดพลาด กรุณาลองใหม่')
    } finally {
      setLoading(false)
    }
  }

  const handleBook = async () => {
    if (!title) { setError('กรุณากรอกหัวข้อการประชุม'); return }
    setBookingLoading(true)
    setError('')
    try {
      await api.post('/bookings/', {
        room: selectedRoom.id,
        title,
        attendees: parseInt(form.attendees),
        start_time: `${form.date}T${form.start_time}:00+07:00`,
        end_time:   `${form.date}T${form.end_time}:00+07:00`,
      })
      setSuccess(true)
    } catch {
      setError('จองไม่สำเร็จ กรุณาลองใหม่')
    } finally {
      setBookingLoading(false)
    }
  }

  const formatThaiDate = (d) => new Date(d).toLocaleDateString('th-TH', { weekday: 'long', day: 'numeric', month: 'long' })
  const countByLevel = (level) => rooms.filter(r => (r.forecast?.demand_level || 'none') === level).length

  if (success) return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 flex items-center justify-center px-4">
      <div className="bg-white rounded-3xl shadow-xl p-8 text-center max-w-sm w-full">
        <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-5">
          <CheckCircle size={40} className="text-green-500" />
        </div>
        <h2 className="text-xl font-bold text-gray-800 mb-1">จองสำเร็จแล้ว!</h2>
        <p className="text-blue-600 font-medium mb-1">{selectedRoom?.name}</p>
        <p className="text-gray-400 text-sm mb-1">{formatThaiDate(form.date)}</p>
        <p className="text-gray-400 text-sm mb-6">{form.start_time} – {form.end_time} น.</p>
        <p className="text-xs text-gray-400 bg-gray-50 rounded-xl px-4 py-2 mb-6">
          สามารถเข้าใช้ห้องตามเวลาที่กำหนดได้เลย
        </p>
        <button onClick={() => navigate('/')}
          className="w-full bg-blue-600 text-white py-2.5 rounded-xl font-medium hover:bg-blue-700">
          กลับหน้าหลัก
        </button>
      </div>
    </div>
  )

  const stepTitles = ['', 'ระบุความต้องการ', 'เลือกห้อง', 'ยืนยันการจอง']

  return (
    <div className="min-h-screen bg-gray-50">

      {/* Header */}
      <div className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={() => step === 1 ? navigate('/') : setStep(step - 1)}
            className="p-2 rounded-xl hover:bg-gray-100 text-gray-500 transition-colors">
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1">
            <p className="font-semibold text-gray-800 text-sm">{stepTitles[step]}</p>
            <div className="flex gap-1 mt-1">
              {[1,2,3].map(s => (
                <div key={s} className={`h-1 flex-1 rounded-full transition-colors
                  ${step >= s ? 'bg-blue-500' : 'bg-gray-200'}`} />
              ))}
            </div>
          </div>
          <span className="text-xs text-gray-400">{step}/3</span>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 py-5 space-y-4">

        {error && (
          <div className="bg-red-50 border border-red-100 text-red-600 text-sm px-4 py-3 rounded-xl">
            {error}
          </div>
        )}

        {/* ===== Step 1 ===== */}
        {step === 1 && (
          <div className="space-y-4">

            {/* จำนวนคน */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <label className="block text-sm font-semibold text-gray-800 mb-3">จำนวนผู้เข้าร่วม</label>
              <div className="flex items-center gap-3">
                <button onClick={() => set('attendees', Math.max(1, (parseInt(form.attendees) || 1) - 1))}
                  className="w-10 h-10 rounded-xl bg-gray-100 text-gray-600 font-bold text-lg hover:bg-gray-200 transition-colors">
                  −
                </button>
                <div className="flex-1 text-center">
                  <span className="text-3xl font-bold text-blue-600">{form.attendees || 0}</span>
                  <p className="text-xs text-gray-400 mt-0.5">คน</p>
                </div>
                <button onClick={() => set('attendees', (parseInt(form.attendees) || 0) + 1)}
                  className="w-10 h-10 rounded-xl bg-blue-600 text-white font-bold text-lg hover:bg-blue-700 transition-colors">
                  +
                </button>
              </div>
              <div className="flex gap-2 mt-3">
                {[5, 10, 20, 30].map(n => (
                  <button key={n} onClick={() => set('attendees', n)}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors
                      ${parseInt(form.attendees) === n ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                    {n} คน
                  </button>
                ))}
              </div>
            </div>

            {/* วันที่ */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <label className="block text-sm font-semibold text-gray-800 mb-3">วันที่</label>
              <input type="date" className={inputClass}
                value={form.date}
                min={new Date().toISOString().split('T')[0]}
                onChange={e => set('date', e.target.value)} />
              {form.date && <p className="text-xs text-blue-500 mt-2">{formatThaiDate(form.date)}</p>}
            </div>

            {/* เวลา */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <label className="block text-sm font-semibold text-gray-800 mb-3">เลือกช่วงเวลา</label>
              <div className="grid grid-cols-2 gap-2 mb-4">
                {TIME_SLOTS.map(slot => (
                  <button key={slot.label} onClick={() => handleSelectSlot(slot)}
                    className={`py-2.5 px-3 rounded-xl text-xs font-medium border-2 text-left transition-all
                      ${selectedSlot === slot.label ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-100 bg-gray-50 text-gray-600 hover:border-gray-200'}`}>
                    <span className="flex items-center gap-1.5">
                      <Clock size={11} /> {slot.label}
                    </span>
                  </button>
                ))}
              </div>

              {selectedSlot && (
                <div>
                  <p className="text-xs text-gray-500 mb-2">ระยะเวลา</p>
                  <div className="flex gap-2">
                    {DURATIONS.map(d => (
                      <button key={d.label} onClick={() => handleSelectDuration(d)}
                        className={`flex-1 py-2 rounded-xl text-xs font-medium border-2 transition-all
                          ${(customTime && d.hours === 0) || (selectedDuration === d.hours && !customTime && d.hours !== 0)
                            ? 'border-blue-500 bg-blue-50 text-blue-700'
                            : 'border-gray-100 bg-gray-50 text-gray-600 hover:border-gray-200'}`}>
                        {d.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {customTime && (
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">เวลาเริ่ม</label>
                    <input type="time" className={inputClass}
                      value={form.start_time} onChange={e => set('start_time', e.target.value)} />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-1 block">เวลาสิ้นสุด</label>
                    <input type="time" className={inputClass}
                      value={form.end_time} onChange={e => set('end_time', e.target.value)} />
                  </div>
                </div>
              )}

              {form.start_time && form.end_time && (
                <div className="mt-3 bg-blue-50 rounded-xl px-4 py-2.5 flex items-center gap-2">
                  <Clock size={14} className="text-blue-500" />
                  <span className="text-sm text-blue-700 font-medium">
                    {form.start_time} – {form.end_time} น.
                  </span>
                </div>
              )}
            </div>

            {/* ประเภทห้อง */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <label className="block text-sm font-semibold text-gray-800 mb-3">ประเภทห้อง</label>
              <div className="grid grid-cols-3 gap-2">
                {ROOM_TYPES.map(t => (
                  <button key={t.value} onClick={() => set('room_type', t.value)}
                    className={`py-2.5 px-2 rounded-xl text-xs font-medium border-2 text-center transition-all
                      ${form.room_type === t.value ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-100 bg-gray-50 text-gray-600 hover:border-gray-200'}`}>
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* อุปกรณ์ที่ต้องการ */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <div className="flex justify-between items-center mb-3">
                <label className="text-sm font-semibold text-gray-800">
                  อุปกรณ์ที่ต้องการ
                </label>
                <div className="flex items-center gap-2">
                  {selectedFacilities.length > 0 && (
                    <>
                      <span className="text-xs text-blue-500">
                        เลือกแล้ว {selectedFacilities.length} รายการ
                      </span>
                      <button onClick={() => setSelectedFacilities([])}
                        className="text-xs text-gray-400 hover:text-red-400 transition-colors">
                        ล้าง
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {FACILITIES.map(f => (
                  <button key={f.value} onClick={() => toggleFacility(f.value)}
                    className={`py-2.5 px-2 rounded-xl text-xs font-medium border-2 text-center transition-all relative
                      ${selectedFacilities.includes(f.value)
                        ? 'border-blue-500 bg-blue-50 text-blue-700'
                        : 'border-gray-100 bg-gray-50 text-gray-600 hover:border-gray-200'}`}>
                    {selectedFacilities.includes(f.value) && (
                      <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-blue-500 rounded-full" />
                    )}
                    {f.label}
                  </button>
                ))}
              </div>
              {selectedFacilities.length > 0 && (
                <p className="text-xs text-gray-400 mt-2">
                  กรองเฉพาะห้องที่มี: {selectedFacilities.join(', ')}
                </p>
              )}
            </div>

            <button onClick={handleSearch} disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-3 rounded-2xl font-medium transition-colors shadow-sm">
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  กำลังค้นหา...
                </span>
              ) : 'ค้นหาห้อง'}
            </button>
          </div>
        )}

        {/* ===== Step 2 — เลือกห้อง ===== */}
        {step === 2 && (
          <div className="space-y-3">

            <div className="flex justify-between items-center px-1">
              <p className="text-sm text-gray-500">
                พบ <span className="font-semibold text-gray-800">{rooms.length} ห้อง</span> • เรียงตามความพร้อม
              </p>
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <TrendingUp size={11} /> AI Forecast
              </span>
            </div>

            {/* แสดงอุปกรณ์ที่กรองไว้ */}
            {selectedFacilities.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-1">
                {selectedFacilities.map(f => {
                  const found = FACILITIES.find(x => x.value === f)
                  return (
                    <span key={f} className="text-xs bg-blue-50 text-blue-600 border border-blue-100 px-2.5 py-1 rounded-full">
                      {found?.label || f}
                    </span>
                  )
                })}
              </div>
            )}

            {rooms.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {[
                  { level: 'low',    label: 'ว่างสูง',   color: 'text-green-600',  bg: 'bg-green-50' },
                  { level: 'medium', label: 'เริ่มแน่น', color: 'text-yellow-600', bg: 'bg-yellow-50' },
                  { level: 'high',   label: 'แน่นมาก',  color: 'text-red-600',    bg: 'bg-red-50' },
                ].map(s => (
                  <div key={s.level} className={`${s.bg} rounded-xl p-3 text-center`}>
                    <p className={`text-xl font-bold ${s.color}`}>{countByLevel(s.level)}</p>
                    <p className={`text-xs ${s.color} opacity-80`}>{s.label}</p>
                  </div>
                ))}
              </div>
            )}

            {rooms.length === 0 ? (
              <div className="bg-white rounded-2xl shadow-sm p-10 text-center">
                <Building2 size={40} className="text-gray-200 mx-auto mb-3" />
                <p className="text-gray-500 font-medium mb-1">ไม่พบห้องว่าง</p>
                <p className="text-gray-400 text-sm mb-4">
                  {selectedFacilities.length > 0 ? 'ลองลดเงื่อนไขอุปกรณ์ดูครับ' : 'ลองเปลี่ยนวันหรือเวลาดูครับ'}
                </p>
                <button onClick={() => setStep(1)} className="text-blue-600 text-sm font-medium hover:underline">
                  ← ค้นหาใหม่
                </button>
              </div>
            ) : rooms.map((room, idx) => {
              const level = room.forecast?.demand_level || 'none'
              const cfg = FORECAST_CONFIG[level]
              const confidence = room.forecast?.confidence
              const isTopPick = idx === 0 && level === 'low'

              return (
                <div key={room.id}
                  className={`bg-white rounded-2xl shadow-sm overflow-hidden cursor-pointer hover:shadow-md transition-all ${cfg.cardBorder}`}
                  onClick={() => { setSelectedRoom(room); setStep(3) }}>

                  {isTopPick && (
                    <div className="bg-green-500 px-4 py-1.5 flex items-center gap-2">
                      <Zap size={13} className="text-white" />
                      <span className="text-white text-xs font-semibold">แนะนำให้จองตอนนี้</span>
                    </div>
                  )}

                  <div className="p-5">
                    <div className="flex justify-between items-start gap-3">
                      <div className="flex-1 min-w-0">

                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <p className="font-bold text-gray-800">{room.name}</p>
                          <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${cfg.badgeCls}`}>
                            {cfg.icon} {cfg.badge}
                          </span>
                        </div>

                        <p className="text-sm text-gray-400 mb-2">{room.building_name} • ชั้น {room.floor}</p>

                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="flex items-center gap-1 text-xs text-gray-500 bg-gray-50 px-2.5 py-1 rounded-lg">
                            <Users size={12} /> {room.capacity} คน
                          </span>
                          <span className="flex items-center gap-1 text-xs text-gray-500 bg-gray-50 px-2.5 py-1 rounded-lg">
                            <MapPin size={12} /> {room.room_type}
                          </span>
                        </div>

                        {/* อุปกรณ์ของห้อง */}
                        {room.facilities?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {room.facilities.map((f, i) => {
                              const isSelected = selectedFacilities.some(
  sel => f.name === sel  // เปลี่ยนเป็น exact match แทน
)
                              return (
                                <span key={i}
                                  className={`text-xs px-2 py-0.5 rounded-full transition-colors
                                    ${isSelected
                                      ? 'bg-blue-100 text-blue-700 font-medium'
                                      : 'bg-gray-100 text-gray-500'}`}>
                                  {f.name}
                                </span>
                              )
                            })}
                          </div>
                        )}

                        {/* AI Forecast */}
                        {room.forecast && (
                          <div className="mt-3 pt-3 border-t border-gray-50">
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className="text-xs text-gray-400 w-16 shrink-0">ความต้องการ</span>
                              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div className={`h-full rounded-full transition-all ${cfg.barColor}`}
                                  style={{ width: cfg.barWidth }} />
                              </div>
                              {confidence && (
                                <span className="text-xs text-gray-400 w-10 text-right shrink-0">
                                  {confidence}%
                                </span>
                              )}
                            </div>
                            <p className={`text-xs font-medium ${cfg.recommendCls}`}>{cfg.recommend}</p>
                            {cfg.tip && <p className="text-xs text-gray-400 mt-0.5">{cfg.tip}</p>}
                          </div>
                        )}
                      </div>

                      <div className="text-blue-400 mt-1 shrink-0">›</div>
                    </div>
                  </div>
                </div>
              )
            })}

            {rooms.length > 0 && (
              <div className="bg-blue-50 rounded-xl px-4 py-3 flex gap-2">
                <TrendingUp size={14} className="text-blue-500 mt-0.5 shrink-0" />
                <p className="text-xs text-blue-600">
                  ผลการพยากรณ์โดย LSTM Model วิเคราะห์จากประวัติการจองย้อนหลัง เรียงห้องจากโอกาสว่างสูงสุดไปต่ำสุด
                </p>
              </div>
            )}
          </div>
        )}

        {/* ===== Step 3 — ยืนยัน ===== */}
        {step === 3 && selectedRoom && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center">
                  <Building2 size={22} className="text-blue-600" />
                </div>
                <div>
                  <p className="font-bold text-gray-800">{selectedRoom.name}</p>
                  <p className="text-sm text-gray-400">{selectedRoom.building_name} • ชั้น {selectedRoom.floor}</p>
                </div>
              </div>

              <div className="space-y-2 text-sm">
                {[
                  { label: '📅 วันที่',  value: formatThaiDate(form.date) },
                  { label: '⏰ เวลา',   value: `${form.start_time} – ${form.end_time} น.` },
                  { label: '👥 จำนวน', value: `${form.attendees} คน` },
                  { label: '🏢 ประเภท', value: selectedRoom.room_type },
                ].map((row, i) => (
                  <div key={i} className="flex justify-between py-2 border-b border-gray-50 last:border-0">
                    <span className="text-gray-400">{row.label}</span>
                    <span className="font-medium text-gray-700">{row.value}</span>
                  </div>
                ))}
              </div>

              {/* อุปกรณ์ในห้องที่เลือก */}
              {selectedRoom.facilities?.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-50">
                  <p className="text-xs text-gray-400 mb-2">🔧 อุปกรณ์ในห้อง</p>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedRoom.facilities.map((f, i) => (
                      <span key={i} className="text-xs bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full">
                        {f.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {selectedRoom.forecast && (() => {
                const level = selectedRoom.forecast.demand_level || 'none'
                const cfg = FORECAST_CONFIG[level]
                return (
                  <div className={`mt-4 rounded-xl px-4 py-3 flex items-center gap-2
                    ${level === 'low' ? 'bg-green-50' : level === 'medium' ? 'bg-yellow-50' : 'bg-red-50'}`}>
                    {cfg.icon}
                    <div>
                      <p className={`text-sm font-semibold ${cfg.recommendCls}`}>{cfg.recommend}</p>
                      {cfg.tip && <p className="text-xs text-gray-400 mt-0.5">{cfg.tip}</p>}
                    </div>
                  </div>
                )
              })()}
            </div>

            <div className="bg-white rounded-2xl shadow-sm p-5">
              <label className="block text-sm font-semibold text-gray-800 mb-2">หัวข้อการประชุม</label>
              <input type="text" placeholder="เช่น ประชุมกลุ่มโปรเจกต์, สัมมนา..."
                className={inputClass}
                value={title} onChange={e => setTitle(e.target.value)} />
            </div>

            <button onClick={handleBook} disabled={bookingLoading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-3 rounded-2xl font-bold transition-colors shadow-sm">
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