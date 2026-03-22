import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, CheckCircle, Building2, ChevronRight,
  Search, Clock, Users, Calendar, MapPin, Zap, Monitor, Smartphone
} from 'lucide-react'
import api from '../api/axios'

const BUILDINGS = [
  { code: '',     label: 'ทั้งหมด' },
  { code: 'LIB',  label: 'ห้องสมุด' },
  { code: 'SC',   label: 'วิทยาศาสตร์' },
  { code: 'EN',   label: 'วิศวกรรม' },
  { code: 'MAIN', label: 'สำนักงาน' },
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

const FORECAST_CONFIG = {
  low: {
    badge: 'จองได้เลย', sub: 'ห้องว่าง พร้อมใช้งาน',
    badgeCls: 'bg-blue-50 text-blue-700 border border-blue-200',
    dotColor: '#2563eb', leftColor: '#2563eb',
    pillCls: 'bg-blue-50 border border-blue-200',
    textCls: 'text-blue-700', subCls: 'text-blue-500',
    cardBg: 'bg-blue-50', cardBorder: 'border-blue-200',
    numCls: 'text-blue-600', sort: 0,
  },
  medium: {
    badge: 'ควรจองตอนนี้', sub: 'เริ่มมีคนสนใจห้องนี้',
    badgeCls: 'bg-yellow-50 text-yellow-800 border border-yellow-300',
    dotColor: '#f59e0b', leftColor: '#f59e0b',
    pillCls: 'bg-yellow-50 border border-yellow-300',
    textCls: 'text-yellow-800', subCls: 'text-yellow-600',
    cardBg: 'bg-yellow-50', cardBorder: 'border-yellow-200',
    numCls: 'text-yellow-600', sort: 1,
  },
  high: {
    badge: 'รีบจองด่วน!', sub: 'โอกาสสุดท้ายก่อนเต็ม',
    badgeCls: 'bg-orange-50 text-orange-700 border border-orange-200',
    dotColor: '#f97316', leftColor: '#f97316',
    pillCls: 'bg-orange-50 border border-orange-200',
    textCls: 'text-orange-700', subCls: 'text-orange-500',
    cardBg: 'bg-orange-50', cardBorder: 'border-orange-200',
    numCls: 'text-orange-600', sort: 2,
  },
  none: {
    badge: '—', sub: '',
    badgeCls: 'bg-gray-100 text-gray-500 border border-gray-200',
    dotColor: '#cbd5e1', leftColor: '#e2e8f0',
    pillCls: 'bg-gray-50 border border-gray-200',
    textCls: 'text-gray-500', subCls: 'text-gray-400',
    cardBg: 'bg-gray-50', cardBorder: 'border-gray-200',
    numCls: 'text-gray-500', sort: 3,
  },
}

const addHours = (time, hours) => {
  const [h, m] = time.split(':').map(Number)
  return `${String(h + hours).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
const formatDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
})
const formatDateShort = (d) => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', {
  day: 'numeric', month: 'short',
})

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes scaleIn{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:scale(1)}}
@keyframes slideRight{from{opacity:0;transform:translateX(-16px)}to{opacity:1;transform:translateX(0)}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .06s ease both}
.au2{animation:fadeUp .28s .12s ease both}
.au3{animation:fadeUp .28s .18s ease both}
.au4{animation:fadeUp .28s .24s ease both}
.si{animation:scaleIn .22s ease both}
.af{animation:fadeIn .2s ease both}
.sr{animation:slideRight .25s ease both}
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

function Chip({ active, children, onClick, className = '' }) {
  return (
    <button onClick={onClick}
      className={`
        px-3 py-1.5 rounded-full text-xs font-semibold border-2 transition-all duration-150
        ${active
          ? 'bg-blue-700 border-blue-700 text-white shadow-sm'
          : 'bg-white border-blue-100 text-slate-600 hover:border-blue-300 hover:text-blue-700 hover:bg-blue-50'
        } ${className}
      `}>
      {children}
    </button>
  )
}

function SectionLabel({ icon: Icon, children }) {
  return (
    <div className="flex items-center gap-1.5 text-blue-600 text-xs font-bold uppercase tracking-widest mb-3">
      {Icon && <Icon size={11} />}{children}
    </div>
  )
}

// ── DESKTOP LAYOUT ────────────────────────────────────
function DesktopLayout({ step, setStep, navigate, formProps, resultProps, confirmProps }) {
  const {
    attendees, setAttendees, date, setDate,
    startTime, setStartTime, duration, setDuration,
    building, setBuilding, endTime, loading, handleSearch, error
  } = formProps

  const { rooms, setSelectedRoom } = resultProps
  const { selectedRoom, title, setTitle, bookingLoading, handleBook, success } = confirmProps

  if (success) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <style>{ANIM}</style>
      <div className="bg-white border border-blue-100 rounded-3xl p-12 text-center max-w-md w-full shadow-2xl si">
        <div className="w-20 h-20 rounded-full bg-blue-700 flex items-center justify-center mx-auto mb-6 shadow-xl shadow-blue-200">
          <CheckCircle size={38} color="#fff" />
        </div>
        <div className="h-1 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-6" />
        <p className="text-2xl font-extrabold text-slate-900 mb-2">จองสำเร็จแล้ว</p>
        <p className="text-lg font-bold text-blue-700 mb-4">{selectedRoom?.name}</p>
        <p className="text-sm text-slate-500">{formatDate(date)}</p>
        <p className="text-sm text-slate-500 mt-1">{startTime} – {endTime} น. · {attendees} ผู้เข้าร่วม</p>
        <button onClick={() => navigate('/')}
          className="mt-8 w-full bg-blue-700 hover:bg-blue-800 text-white rounded-2xl py-4 font-bold text-sm transition-all shadow-lg shadow-blue-200 active:scale-95">
          กลับหน้าหลัก
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-slate-100" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>

      {/* TOP NAVBAR */}
      <div className="bg-blue-700 shadow-lg shadow-blue-900/20">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => step === 1 ? navigate('/') : setStep(step - 1)}
            className="flex items-center gap-2 text-white/80 hover:text-white text-sm font-medium transition-colors">
            <ArrowLeft size={15} />
            {step === 1 ? 'หน้าหลัก' : 'ย้อนกลับ'}
          </button>
          <div className="h-5 w-px bg-white/20" />
          <span className="text-white font-bold text-sm">
            {step === 1 ? 'ค้นหาห้องประชุม' : step === 2 ? `ผลการค้นหา · ${rooms.length} ห้อง` : 'ยืนยันการจอง'}
          </span>
          <div className="ml-auto flex items-center gap-3">
            {[1,2,3].map(s => (
              <div key={s} className="flex items-center gap-1.5">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-all
                  ${step >= s ? 'bg-white text-blue-700' : 'bg-white/20 text-white/60'}`}>
                  {s}
                </div>
                <span className={`text-xs hidden lg:block transition-colors ${step >= s ? 'text-white' : 'text-white/50'}`}>
                  {s === 1 ? 'เลือกเงื่อนไข' : s === 2 ? 'เลือกห้อง' : 'ยืนยัน'}
                </span>
                {s < 3 && <div className={`w-8 h-px ${step > s ? 'bg-white' : 'bg-white/25'}`} />}
              </div>
            ))}
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
      </div>

      {error && (
        <div className="max-w-7xl mx-auto px-6 pt-4">
          <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-4 py-3 rounded-xl af">{error}</div>
        </div>
      )}

      {/* STEP 1 DESKTOP — 2 column */}
      {step === 1 && (
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="grid grid-cols-3 gap-6">

            {/* LEFT: form fields */}
            <div className="col-span-2 space-y-5">
              <div className="grid grid-cols-2 gap-5">
                {/* จำนวนคน */}
                <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au">
                  <SectionLabel icon={Users}>จำนวนผู้เข้าร่วม</SectionLabel>
                  <div className="flex items-center gap-4 mb-4">
                    <button onClick={() => setAttendees(Math.max(1, attendees - 1))}
                      className="w-10 h-10 rounded-xl border-2 border-blue-100 bg-blue-50 text-blue-600 text-xl font-bold flex items-center justify-center hover:bg-blue-100 transition-all active:scale-90">−</button>
                    <div className="flex-1 text-center">
                      <span className="text-5xl font-extrabold text-slate-900">{attendees}</span>
                      <span className="text-sm text-slate-400 ml-2">คน</span>
                    </div>
                    <button onClick={() => setAttendees(attendees + 1)}
                      className="w-10 h-10 rounded-xl bg-blue-700 text-white text-xl font-bold flex items-center justify-center hover:bg-blue-800 shadow-sm shadow-blue-300 active:scale-90">+</button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {ATTENDEES_PRESETS.map(n => <Chip key={n} active={attendees === n} onClick={() => setAttendees(n)}>{n} คน</Chip>)}
                  </div>
                </div>

                {/* วันที่ + อาคาร */}
                <div className="space-y-5">
                  <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au1">
                    <SectionLabel icon={Calendar}>วันที่</SectionLabel>
                    <input type="date" value={date}
                      min={new Date().toISOString().split('T')[0]}
                      onChange={e => setDate(e.target.value)}
                      className="w-full border-2 border-blue-100 rounded-xl px-4 py-2.5 text-sm text-slate-800 bg-blue-50/40 outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 transition-all"
                      style={{fontFamily:"inherit"}} />
                  </div>
                  <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au2">
                    <SectionLabel icon={MapPin}>อาคาร</SectionLabel>
                    <div className="flex flex-wrap gap-1.5">
                      {BUILDINGS.map(b => <Chip key={b.code} active={building === b.code} onClick={() => setBuilding(b.code)}>{b.label}</Chip>)}
                    </div>
                  </div>
                </div>
              </div>

              {/* เวลา full-width */}
              <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au3">
                <SectionLabel icon={Clock}>เวลา</SectionLabel>
                <div className="grid grid-cols-8 gap-2 mb-4">
                  {TIME_SLOTS.map(t => (
                    <button key={t} onClick={() => setStartTime(t)}
                      className={`py-2.5 rounded-xl text-xs font-semibold border-2 transition-all duration-150
                        ${startTime === t ? 'bg-blue-700 border-blue-700 text-white shadow-sm' : 'bg-white border-blue-100 text-slate-600 hover:border-blue-300 hover:bg-blue-50'}`}>
                      {t}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-xs font-bold text-blue-600 uppercase tracking-widest flex items-center gap-1"><Clock size={10} />ระยะเวลา</span>
                  <div className="flex gap-1.5">
                    {DURATIONS.map(d => <Chip key={d.hours} active={duration === d.hours} onClick={() => setDuration(d.hours)}>{d.label}</Chip>)}
                  </div>
                  {startTime && (
                    <div className="ml-auto bg-blue-700 rounded-xl px-5 py-2 si">
                      <span className="text-sm font-bold text-white">{startTime} – {endTime} น.</span>
                      <span className="text-blue-200 text-xs ml-3">{formatDateShort(date)}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* RIGHT: summary + search */}
            <div className="au4">
              <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm sticky top-20">
                <p className="text-base font-bold text-slate-900 mb-1">สรุปการค้นหา</p>
                <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
                <div className="space-y-3 mb-6 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-500">ผู้เข้าร่วม</span>
                    <span className="font-bold text-slate-800">{attendees} คน</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">วันที่</span>
                    <span className="font-bold text-slate-800">{formatDateShort(date)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">เวลา</span>
                    <span className="font-bold text-slate-800">{startTime ? `${startTime}–${endTime}` : '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">อาคาร</span>
                    <span className="font-bold text-slate-800">{BUILDINGS.find(b => b.code === building)?.label || 'ทั้งหมด'}</span>
                  </div>
                </div>
                <button onClick={handleSearch} disabled={loading}
                  className="w-full bg-blue-700 hover:bg-blue-800 disabled:bg-slate-400 text-white rounded-2xl py-4 font-bold text-sm flex items-center justify-center gap-2.5 shadow-lg shadow-blue-200 transition-all active:scale-95 disabled:cursor-not-allowed">
                  {loading
                    ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />ค้นหา...</>
                    : <><Search size={15} />ค้นหาห้องว่าง</>}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STEP 2 DESKTOP — list */}
      {step === 2 && (
        <div className="max-w-7xl mx-auto px-6 py-8">
          {/* summary */}
          <div className="bg-blue-700 rounded-2xl px-6 py-4 flex items-center justify-between mb-6 shadow-md shadow-blue-300 au">
            <div className="flex gap-6 items-center">
              <span className="text-white font-bold">{attendees} คน</span>
              <span className="text-blue-200 text-sm">{formatDateShort(date)}</span>
              <span className="text-blue-200 text-sm">{startTime}–{endTime}</span>
              {building && <span className="text-blue-200 text-sm">{BUILDINGS.find(b=>b.code===building)?.label}</span>}
            </div>
            <div className="flex items-center gap-2 bg-yellow-300 text-yellow-900 text-xs font-bold rounded-full px-3 py-1.5">
              <Zap size={11} />AI Forecast
            </div>
          </div>

          {/* demand stat + list */}
          <div className="grid grid-cols-4 gap-6">
            <div className="space-y-3 au1">
              {[
                {level:'low',    label:'จองได้เลย'},
                {level:'medium', label:'ควรจองตอนนี้'},
                {level:'high',   label:'รีบจองด่วน!'},
              ].map(s => {
                const cfg   = FORECAST_CONFIG[s.level]
                const count = rooms.filter(r => (r.forecast?.demand_level||'none') === s.level).length
                return (
                  <div key={s.level} className={`border rounded-2xl py-4 text-center ${cfg.cardBg} ${cfg.cardBorder}`}>
                    <p className={`text-3xl font-extrabold ${cfg.numCls}`}>{count}</p>
                    <p className={`text-xs font-semibold mt-1 ${cfg.textCls} opacity-80`}>{s.label}</p>
                  </div>
                )
              })}
              <p className="text-xs text-slate-400 text-center pt-1">เรียงตาม AI Forecast</p>
            </div>
            <div className="col-span-3 space-y-3 au2">
              {rooms.length === 0 ? (
                <div className="bg-white border border-blue-100 rounded-2xl py-16 text-center">
                  <Building2 size={40} className="text-blue-200 mx-auto mb-4" />
                  <p className="font-semibold text-blue-700 mb-2">ไม่พบห้องว่าง</p>
                  <button onClick={() => setStep(1)} className="text-sm text-blue-600 hover:underline">← ค้นหาใหม่</button>
                </div>
              ) : rooms.map((room, idx) => {
                const level = room.forecast?.demand_level || 'none'
                const cfg   = FORECAST_CONFIG[level]
                const isTop = idx === 0 && level === 'low'
                return (
                  <div key={room.id}
                    className="bg-white border border-blue-100 rounded-2xl px-6 py-5 cursor-pointer flex items-center gap-4 hover:shadow-lg hover:shadow-blue-100 hover:-translate-y-0.5 transition-all duration-150"
                    style={{borderLeftWidth:4,borderLeftColor:cfg.dotColor}}
                    onClick={() => { setSelectedRoom(room); setStep(3) }}>
                    <div className="flex-1 min-w-0">
                      {isTop && <span className="inline-block bg-yellow-100 text-yellow-800 border border-yellow-300 text-xs font-bold rounded-full px-3 py-0.5 mb-2">แนะนำ</span>}
                      <div className="flex items-center gap-3 mb-1.5">
                        <span className="text-base font-bold text-slate-900">{room.name}</span>
                        <span className={`text-xs font-bold px-3 py-0.5 rounded-full ${cfg.badgeCls}`}>{cfg.badge}</span>
                      </div>
                      <p className="text-sm text-slate-500">{room.building_name} · ชั้น {room.floor} · {room.capacity} ที่นั่ง · {room.room_type}</p>
                      {level !== 'none' && <p className={`text-xs font-semibold mt-1 ${cfg.subCls}`}>{cfg.sub}</p>}
                    </div>
                    <ChevronRight size={16} className="text-blue-200 flex-shrink-0" />
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* STEP 3 DESKTOP */}
      {step === 3 && selectedRoom && (() => {
        const cfg = FORECAST_CONFIG[selectedRoom.forecast?.demand_level || 'none']
        return (
          <div className="max-w-3xl mx-auto px-6 py-8">
            <div className="grid grid-cols-2 gap-6">
              <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au">
                <SectionLabel icon={Building2}>ห้องที่เลือก</SectionLabel>
                <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-5" />
                <div className="flex gap-3 mb-5">
                  <div className="w-12 h-12 rounded-xl bg-blue-100 border border-blue-200 flex items-center justify-center flex-shrink-0">
                    <Building2 size={22} className="text-blue-600" />
                  </div>
                  <div>
                    <p className="text-lg font-bold text-slate-900">{selectedRoom.name}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{selectedRoom.building_name} · ชั้น {selectedRoom.floor} · {selectedRoom.room_type}</p>
                  </div>
                </div>
                <div className="border-2 border-blue-50 rounded-xl overflow-hidden">
                  {[
                    {label:'วันที่',       value: formatDate(date)},
                    {label:'เวลา',         value: `${startTime} – ${endTime} น.`},
                    {label:'ผู้เข้าร่วม', value: `${attendees} คน`},
                  ].map((r,i) => (
                    <div key={i} className="flex justify-between px-4 py-3 bg-white border-b border-blue-50 last:border-0">
                      <span className="text-xs text-slate-500">{r.label}</span>
                      <span className="text-sm font-semibold text-slate-800">{r.value}</span>
                    </div>
                  ))}
                </div>
                {cfg.badge !== '—' && (
                  <div className={`mt-4 flex items-center gap-2.5 rounded-xl px-4 py-3 ${cfg.pillCls}`}>
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{background:cfg.dotColor}} />
                    <span className={`text-xs font-bold ${cfg.textCls}`}>{cfg.badge}</span>
                    <span className={`text-xs ${cfg.subCls} opacity-80`}>— {cfg.sub}</span>
                  </div>
                )}
              </div>
              <div className="space-y-5 au1">
                <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm">
                  <SectionLabel>หัวข้อการประชุม</SectionLabel>
                  <input type="text" autoFocus
                    placeholder="เช่น ประชุมกลุ่ม, นำเสนองาน..."
                    value={title} onChange={e => setTitle(e.target.value)}
                    className="w-full border-2 border-blue-100 rounded-xl px-4 py-3 text-sm text-slate-800 bg-blue-50/40 outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 transition-all placeholder:text-slate-400"
                    style={{fontFamily:"inherit"}} />
                </div>
                <button onClick={handleBook} disabled={bookingLoading}
                  className="w-full bg-blue-700 hover:bg-blue-800 disabled:bg-slate-400 text-white rounded-2xl py-5 font-bold text-base flex items-center justify-center gap-3 shadow-xl shadow-blue-200 transition-all active:scale-95 disabled:cursor-not-allowed">
                  {bookingLoading
                    ? <><div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />กำลังจอง...</>
                    : <><CheckCircle size={18} />ยืนยันการจอง</>}
                </button>
              </div>
            </div>
          </div>
        )
      })()}
    </div>
  )
}

// ── MOBILE LAYOUT ─────────────────────────────────────
function MobileLayout({ step, setStep, navigate, formProps, resultProps, confirmProps }) {
  const {
    attendees, setAttendees, date, setDate,
    startTime, setStartTime, duration, setDuration,
    building, setBuilding, endTime, loading, handleSearch, error
  } = formProps
  const { rooms, setSelectedRoom } = resultProps
  const { selectedRoom, title, setTitle, bookingLoading, handleBook, success } = confirmProps

  if (success) return (
    <div className="min-h-screen bg-blue-50 flex items-center justify-center p-4"
      style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="bg-white border border-blue-100 rounded-3xl p-8 text-center max-w-sm w-full shadow-xl si">
        <div className="w-16 h-16 rounded-full bg-blue-700 flex items-center justify-center mx-auto mb-5 shadow-lg shadow-blue-200">
          <CheckCircle size={30} color="#fff" />
        </div>
        <div className="h-1 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-5" />
        <p className="text-xl font-extrabold text-slate-900 mb-1.5">จองสำเร็จแล้ว</p>
        <p className="text-base font-bold text-blue-700 mb-3">{selectedRoom?.name}</p>
        <p className="text-sm text-slate-500 mb-1">{formatDateShort(date)}</p>
        <p className="text-sm text-slate-500 mb-1">{startTime} – {endTime} น.</p>
        <p className="text-sm text-slate-500 mb-7">{attendees} ผู้เข้าร่วม</p>
        <button onClick={() => navigate('/')}
          className="w-full bg-blue-700 hover:bg-blue-800 text-white rounded-xl py-3.5 text-sm font-bold transition-all shadow-md shadow-blue-200 active:scale-95">
          กลับหน้าหลัก
        </button>
      </div>
    </div>
  )

  const stepTitle = step === 1 ? 'ค้นหาห้องประชุม' : step === 2 ? `ผลการค้นหา · ${rooms.length} ห้อง` : 'ยืนยันการจอง'

  return (
    <div className="min-h-screen bg-blue-50" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="bg-blue-700 sticky top-0 z-50 shadow-lg shadow-blue-900/20">
        <div className="max-w-lg mx-auto px-4 h-14 flex items-center gap-3">
          <button onClick={() => step === 1 ? navigate('/') : setStep(step - 1)}
            className="w-8 h-8 rounded-lg border border-white/20 bg-white/10 flex items-center justify-center text-white hover:bg-white/20 transition-colors flex-shrink-0">
            <ArrowLeft size={15} />
          </button>
          <div className="flex-1">
            <p className="text-sm font-bold text-white leading-tight">{stepTitle}</p>
            <p className="text-xs text-blue-200">ขั้นตอนที่ {step} จาก 3</p>
          </div>
          <div className="flex gap-1.5">
            {[1,2,3].map(s => (
              <div key={s} className="h-1.5 rounded-full transition-all duration-300"
                style={{width: s === step ? 20 : 6, background: step >= s ? '#fff' : 'rgba(255,255,255,.25)'}} />
            ))}
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 pb-12 space-y-3">
        {error && <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-4 py-3 rounded-xl af">{error}</div>}

        {step === 1 && (
          <>
            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au">
              <SectionLabel icon={Users}>จำนวนผู้เข้าร่วม</SectionLabel>
              <div className="flex items-center gap-4 mb-4">
                <button onClick={() => setAttendees(Math.max(1, attendees - 1))}
                  className="w-10 h-10 rounded-xl border-2 border-blue-100 bg-blue-50 text-blue-600 text-xl font-bold flex items-center justify-center hover:bg-blue-100 transition-all active:scale-90">−</button>
                <div className="flex-1 text-center">
                  <span className="text-5xl font-extrabold text-slate-900">{attendees}</span>
                  <span className="text-sm text-slate-400 ml-2">คน</span>
                </div>
                <button onClick={() => setAttendees(attendees + 1)}
                  className="w-10 h-10 rounded-xl bg-blue-700 text-white text-xl font-bold flex items-center justify-center hover:bg-blue-800 shadow-sm shadow-blue-300 active:scale-90">+</button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {ATTENDEES_PRESETS.map(n => <Chip key={n} active={attendees === n} onClick={() => setAttendees(n)}>{n} คน</Chip>)}
              </div>
            </div>

            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au1">
              <SectionLabel icon={Calendar}>วันที่</SectionLabel>
              <input type="date" value={date} min={new Date().toISOString().split('T')[0]}
                onChange={e => setDate(e.target.value)}
                className="w-full border-2 border-blue-100 rounded-xl px-4 py-2.5 text-sm text-slate-800 bg-blue-50/40 outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 transition-all"
                style={{fontFamily:"inherit"}} />
            </div>

            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au2">
              <SectionLabel icon={Clock}>เวลาเริ่มต้น</SectionLabel>
              <div className="grid grid-cols-4 gap-1.5 mb-4">
                {TIME_SLOTS.map(t => (
                  <button key={t} onClick={() => setStartTime(t)}
                    className={`py-2.5 rounded-xl text-xs font-semibold border-2 transition-all duration-150
                      ${startTime === t ? 'bg-blue-700 border-blue-700 text-white shadow-sm' : 'bg-white border-blue-100 text-slate-600 hover:border-blue-300 hover:bg-blue-50'}`}>
                    {t}
                  </button>
                ))}
              </div>
              <p className="text-xs font-bold text-blue-600 uppercase tracking-widest mb-2.5 flex items-center gap-1.5"><Clock size={10} />ระยะเวลา</p>
              <div className="flex gap-1.5">
                {DURATIONS.map(d => <Chip key={d.hours} active={duration === d.hours} onClick={() => setDuration(d.hours)} className="flex-1 justify-center">{d.label}</Chip>)}
              </div>
              {startTime && (
                <div className="mt-3 bg-blue-700 rounded-xl px-4 py-3 flex justify-between items-center si">
                  <span className="text-sm font-bold text-white">{startTime} – {endTime} น.</span>
                  <span className="text-xs text-blue-200">{formatDateShort(date)}</span>
                </div>
              )}
            </div>

            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au3">
              <SectionLabel icon={MapPin}>อาคาร</SectionLabel>
              <div className="flex flex-wrap gap-1.5">
                {BUILDINGS.map(b => <Chip key={b.code} active={building === b.code} onClick={() => setBuilding(b.code)}>{b.label}</Chip>)}
              </div>
            </div>

            <button onClick={handleSearch} disabled={loading}
              className="au4 w-full bg-blue-700 hover:bg-blue-800 disabled:bg-slate-400 text-white rounded-2xl py-4 text-sm font-bold flex items-center justify-center gap-2.5 shadow-lg shadow-blue-200 transition-all active:scale-95 disabled:cursor-not-allowed">
              {loading ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />ค้นหา...</> : <><Search size={15} />ค้นหาห้องว่าง</>}
            </button>
          </>
        )}

        {step === 2 && (
          <>
            <div className="bg-blue-700 rounded-2xl px-4 py-3 flex items-center justify-between flex-wrap gap-2 shadow-md shadow-blue-300 au">
              <div className="flex gap-3 flex-wrap items-center text-sm">
                <span className="font-bold text-white">{attendees} คน</span>
                <span className="text-blue-200 text-xs">{formatDateShort(date)}</span>
                <span className="text-blue-200 text-xs">{startTime}–{endTime}</span>
              </div>
              <div className="flex items-center gap-1.5 bg-yellow-300 text-yellow-900 text-xs font-bold rounded-full px-3 py-1"><Zap size={10} />AI</div>
            </div>

            {rooms.length > 0 && (
              <div className="grid grid-cols-3 gap-2 au1">
                {[{level:'low',label:'จองได้เลย'},{level:'medium',label:'ควรจองตอนนี้'},{level:'high',label:'รีบจองด่วน!'}].map(s => {
                  const cfg = FORECAST_CONFIG[s.level]
                  const count = rooms.filter(r=>(r.forecast?.demand_level||'none')===s.level).length
                  return (
                    <div key={s.level} className={`border rounded-2xl py-3 text-center ${cfg.cardBg} ${cfg.cardBorder}`}>
                      <p className={`text-2xl font-extrabold ${cfg.numCls}`}>{count}</p>
                      <p className={`text-xs font-semibold mt-0.5 ${cfg.textCls} opacity-80`}>{s.label}</p>
                    </div>
                  )
                })}
              </div>
            )}

            {rooms.length === 0 ? (
              <div className="bg-white border border-blue-100 rounded-2xl py-12 text-center au">
                <Building2 size={32} className="text-blue-200 mx-auto mb-3" />
                <p className="text-sm font-semibold text-blue-700 mb-1">ไม่พบห้องว่าง</p>
                <button onClick={() => setStep(1)} className="text-xs text-blue-600 hover:underline mt-2">← ค้นหาใหม่</button>
              </div>
            ) : rooms.map((room,idx) => {
              const level = room.forecast?.demand_level || 'none'
              const cfg   = FORECAST_CONFIG[level]
              const isTop = idx === 0 && level === 'low'
              return (
                <div key={room.id}
                  className="bg-white border border-blue-100 rounded-2xl px-4 py-4 cursor-pointer flex items-center gap-3 hover:shadow-md hover:shadow-blue-100 hover:-translate-y-0.5 active:translate-y-0 transition-all au"
                  style={{borderLeftWidth:4,borderLeftColor:cfg.dotColor}}
                  onClick={() => { setSelectedRoom(room); setStep(3) }}>
                  <div className="flex-1 min-w-0">
                    {isTop && <span className="inline-block bg-yellow-100 text-yellow-800 border border-yellow-300 text-xs font-bold rounded-full px-2.5 py-0.5 mb-2">แนะนำ</span>}
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="text-sm font-bold text-slate-900">{room.name}</span>
                      <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${cfg.badgeCls}`}>{cfg.badge}</span>
                    </div>
                    <p className="text-xs text-slate-500">{room.building_name} · ชั้น {room.floor} · {room.capacity} ที่นั่ง</p>
                    {level !== 'none' && <p className={`text-xs font-semibold mt-1 ${cfg.subCls}`}>{cfg.sub}</p>}
                  </div>
                  <ChevronRight size={14} className="text-blue-200 flex-shrink-0" />
                </div>
              )
            })}
          </>
        )}

        {step === 3 && selectedRoom && (() => {
          const cfg = FORECAST_CONFIG[selectedRoom.forecast?.demand_level || 'none']
          return (
            <>
              <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au">
                <SectionLabel icon={Building2}>ห้องที่เลือก</SectionLabel>
                <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
                <div className="flex gap-3 mb-4">
                  <div className="w-10 h-10 rounded-xl bg-blue-100 border border-blue-200 flex items-center justify-center flex-shrink-0">
                    <Building2 size={18} className="text-blue-600" />
                  </div>
                  <div>
                    <p className="text-base font-bold text-slate-900">{selectedRoom.name}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{selectedRoom.building_name} · ชั้น {selectedRoom.floor}</p>
                  </div>
                </div>
                <div className="border-2 border-blue-50 rounded-xl overflow-hidden">
                  {[{label:'วันที่',value:formatDate(date)},{label:'เวลา',value:`${startTime}–${endTime} น.`},{label:'ผู้เข้าร่วม',value:`${attendees} คน`}].map((r,i)=>(
                    <div key={i} className="flex justify-between px-4 py-2.5 bg-white border-b border-blue-50 last:border-0">
                      <span className="text-xs text-slate-500">{r.label}</span>
                      <span className="text-sm font-semibold text-slate-800">{r.value}</span>
                    </div>
                  ))}
                </div>
                {cfg.badge !== '—' && (
                  <div className={`mt-3 flex items-center gap-2 rounded-xl px-4 py-3 ${cfg.pillCls}`}>
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{background:cfg.dotColor}} />
                    <span className={`text-xs font-bold ${cfg.textCls}`}>{cfg.badge} — {cfg.sub}</span>
                  </div>
                )}
              </div>
              <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au1">
                <SectionLabel>หัวข้อการประชุม</SectionLabel>
                <input type="text" autoFocus placeholder="เช่น ประชุมกลุ่ม, นำเสนองาน..."
                  value={title} onChange={e=>setTitle(e.target.value)}
                  className="w-full border-2 border-blue-100 rounded-xl px-4 py-2.5 text-sm text-slate-800 bg-blue-50/40 outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 transition-all placeholder:text-slate-400"
                  style={{fontFamily:"inherit"}} />
              </div>
              <button onClick={handleBook} disabled={bookingLoading}
                className="au2 w-full bg-blue-700 hover:bg-blue-800 disabled:bg-slate-400 text-white rounded-2xl py-4 font-bold text-sm flex items-center justify-center gap-2.5 shadow-lg shadow-blue-200 transition-all active:scale-95 disabled:cursor-not-allowed">
                {bookingLoading ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />กำลังจอง...</> : <><CheckCircle size={15} />ยืนยันการจอง</>}
              </button>
            </>
          )
        })()}
      </div>
    </div>
  )
}

// ── ROOT ──────────────────────────────────────────────
export default function SearchPage() {
  const navigate    = useNavigate()
  const isMobile    = useDevice()
  const [step, setStep]         = useState(1)
  const [attendees, setAttendees] = useState(5)
  const [date, setDate]           = useState(new Date().toISOString().split('T')[0])
  const [startTime, setStartTime] = useState('')
  const [duration, setDuration]   = useState(1)
  const [building, setBuilding]   = useState('')
  const [rooms, setRooms]         = useState([])
  const [selectedRoom, setSelectedRoom] = useState(null)
  const [title, setTitle]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [bookingLoading, setBookingLoading] = useState(false)
  const [success, setSuccess]     = useState(false)
  const [error, setError]         = useState('')

  const endTime = startTime ? addHours(startTime, duration) : ''

  const handleSearch = async () => {
    if (!startTime) { setError('กรุณาเลือกเวลาเริ่มต้น'); return }
    setError(''); setLoading(true)
    try {
      const res = await api.post('/rooms/search/', {
        attendees, date, start_time: startTime, end_time: endTime,
        building_code: building || undefined,
      })
      const sorted = [...res.data].sort((a,b) =>
        FORECAST_CONFIG[a.forecast?.demand_level||'none'].sort -
        FORECAST_CONFIG[b.forecast?.demand_level||'none'].sort
      )
      setRooms(sorted); setStep(2)
    } catch { setError('เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง') }
    finally   { setLoading(false) }
  }

  const handleBook = async () => {
    if (!title.trim()) { setError('กรุณากรอกหัวข้อการประชุม'); return }
    setBookingLoading(true); setError('')
    try {
      await api.post('/bookings/', {
        room: selectedRoom.id, title, attendees,
        start_time: `${date}T${startTime}:00+07:00`,
        end_time:   `${date}T${endTime}:00+07:00`,
      })
      setSuccess(true)
    } catch { setError('ไม่สามารถจองได้ กรุณาลองใหม่อีกครั้ง') }
    finally   { setBookingLoading(false) }
  }

  const shared = {
    formProps: { attendees, setAttendees, date, setDate, startTime, setStartTime, duration, setDuration, building, setBuilding, endTime, loading, handleSearch, error },
    resultProps: { rooms, setSelectedRoom },
    confirmProps: { selectedRoom, title, setTitle, bookingLoading, handleBook, success },
  }

  return isMobile
    ? <MobileLayout step={step} setStep={setStep} navigate={navigate} {...shared} />
    : <DesktopLayout step={step} setStep={setStep} navigate={navigate} {...shared} />
}