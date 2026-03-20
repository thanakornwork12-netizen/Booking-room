import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, CheckCircle, AlertCircle, XCircle, Building2, ChevronRight, TrendingUp } from 'lucide-react'
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
  { label: '1 ชั่วโมง', hours: 1 },
  { label: '2 ชั่วโมง', hours: 2 },
  { label: '3 ชั่วโมง', hours: 3 },
]

const ATTENDEES_PRESETS = [2, 5, 10, 20, 30, 50]

const FORECAST_CONFIG = {
  low:    { badge: 'ว่าง',      color: '#059669', bg: '#f0fdf4', border: '#6ee7b7', dot: '#10b981', sort: 0 },
  medium: { badge: 'เริ่มแน่น', color: '#d97706', bg: '#fffbeb', border: '#fcd34d', dot: '#f59e0b', sort: 1 },
  high:   { badge: 'แน่น',      color: '#dc2626', bg: '#fef2f2', border: '#fca5a5', dot: '#ef4444', sort: 2 },
  none:   { badge: '—',          color: '#9ca3af', bg: '#f9fafb', border: '#e5e7eb', dot: '#d1d5db', sort: 3 },
}

const addHours = (time, hours) => {
  const [h, m] = time.split(':').map(Number)
  return `${String(h + hours).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

const formatDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
})

const formatDateShort = (d) => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', {
  day: 'numeric', month: 'short'
})

export default function SearchPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)

  const [attendees, setAttendees]   = useState(5)
  const [date, setDate]             = useState(new Date().toISOString().split('T')[0])
  const [startTime, setStartTime]   = useState('')
  const [duration, setDuration]     = useState(1)
  const [building, setBuilding]     = useState('')

  const [rooms, setRooms]               = useState([])
  const [selectedRoom, setSelectedRoom] = useState(null)
  const [title, setTitle]               = useState('')
  const [loading, setLoading]           = useState(false)
  const [bookingLoading, setBookingLoading] = useState(false)
  const [success, setSuccess]           = useState(false)
  const [error, setError]               = useState('')

  const endTime = startTime ? addHours(startTime, duration) : ''

  const handleSearch = async () => {
    if (!startTime) { setError('กรุณาเลือกเวลาเริ่มต้น'); return }
    setError('')
    setLoading(true)
    try {
      const res = await api.post('/rooms/search/', {
        attendees, date,
        start_time: startTime,
        end_time: endTime,
        building_code: building || undefined,
      })
      const sorted = [...res.data].sort((a, b) =>
        FORECAST_CONFIG[a.forecast?.demand_level || 'none'].sort -
        FORECAST_CONFIG[b.forecast?.demand_level || 'none'].sort
      )
      setRooms(sorted)
      setStep(2)
    } catch {
      setError('เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง')
    } finally {
      setLoading(false)
    }
  }

  const handleBook = async () => {
    if (!title.trim()) { setError('กรุณากรอกหัวข้อการประชุม'); return }
    setBookingLoading(true)
    setError('')
    try {
      await api.post('/bookings/', {
        room: selectedRoom.id, title, attendees,
        start_time: `${date}T${startTime}:00+07:00`,
        end_time:   `${date}T${endTime}:00+07:00`,
      })
      setSuccess(true)
    } catch {
      setError('ไม่สามารถจองได้ กรุณาลองใหม่อีกครั้ง')
    } finally {
      setBookingLoading(false)
    }
  }

  // ── SUCCESS ─────────────────────────────────────────
  if (success) return (
    <div style={{ minHeight: '100vh', background: '#f8fafc', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div style={{ background: '#fff', borderRadius: 20, border: '1px solid #e2e8f0', padding: '2.5rem 2rem', textAlign: 'center', maxWidth: 360, width: '100%' }}>
        <div style={{ width: 56, height: 56, borderRadius: '50%', background: '#f0fdf4', border: '1px solid #bbf7d0', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1.5rem' }}>
          <CheckCircle size={26} color="#16a34a" />
        </div>
        <p style={{ fontSize: 18, fontWeight: 700, color: '#0f172a', marginBottom: 4 }}>จองสำเร็จแล้ว</p>
        <p style={{ fontSize: 15, fontWeight: 600, color: '#2563eb', marginBottom: 4 }}>{selectedRoom?.name}</p>
        <p style={{ fontSize: 13, color: '#64748b', marginBottom: 2 }}>{formatDateShort(date)}</p>
        <p style={{ fontSize: 13, color: '#64748b', marginBottom: 2 }}>{startTime} – {endTime} น.</p>
        <p style={{ fontSize: 13, color: '#64748b', marginBottom: 28 }}>{attendees} ผู้เข้าร่วม</p>
        <button onClick={() => navigate('/')} style={{ width: '100%', background: '#0f172a', color: '#fff', border: 'none', borderRadius: 10, padding: '12px 0', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
          กลับหน้าหลัก
        </button>
      </div>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc', fontFamily: "'Sarabun', sans-serif" }}>

      {/* ── HEADER ── */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 10 }}>
        <div style={{ maxWidth: 560, margin: '0 auto', padding: '0 1rem', height: 56, display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => step === 1 ? navigate('/') : setStep(step - 1)}
            style={{ width: 36, height: 36, borderRadius: 8, border: '1px solid #e2e8f0', background: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#475569' }}>
            <ArrowLeft size={16} />
          </button>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', margin: 0 }}>
              {step === 1 ? 'ค้นหาห้องประชุม' : step === 2 ? `ผลการค้นหา · ${rooms.length} ห้อง` : 'ยืนยันการจอง'}
            </p>
            <p style={{ fontSize: 11, color: '#94a3b8', margin: 0 }}>ขั้นตอนที่ {step} จาก 3</p>
          </div>
          {/* step dots */}
          <div style={{ display: 'flex', gap: 4 }}>
            {[1,2,3].map(s => (
              <div key={s} style={{ width: s === step ? 16 : 6, height: 6, borderRadius: 3, background: step >= s ? '#2563eb' : '#e2e8f0', transition: 'all 0.2s' }} />
            ))}
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 560, margin: '0 auto', padding: '1.25rem 1rem' }}>

        {/* ERROR */}
        {error && (
          <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', fontSize: 13, padding: '10px 14px', borderRadius: 10, marginBottom: 12 }}>
            {error}
          </div>
        )}

        {/* ═══════════════════════════════════════════
            STEP 1 — ฟอร์มค้นหา
        ═══════════════════════════════════════════ */}
        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

            {/* จำนวนคน */}
            <Section label="จำนวนผู้เข้าร่วม">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <StepBtn onClick={() => setAttendees(Math.max(1, attendees - 1))}>−</StepBtn>
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <span style={{ fontSize: 36, fontWeight: 800, color: '#0f172a', lineHeight: 1 }}>{attendees}</span>
                  <span style={{ fontSize: 13, color: '#94a3b8', marginLeft: 6 }}>คน</span>
                </div>
                <StepBtn primary onClick={() => setAttendees(attendees + 1)}>+</StepBtn>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {ATTENDEES_PRESETS.map(n => (
                  <button key={n} onClick={() => setAttendees(n)}
                    style={{ flex: 1, padding: '6px 0', borderRadius: 7, border: `1px solid ${attendees === n ? '#2563eb' : '#e2e8f0'}`, background: attendees === n ? '#eff6ff' : '#fff', color: attendees === n ? '#1d4ed8' : '#64748b', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                    {n}
                  </button>
                ))}
              </div>
            </Section>

            {/* วันที่ */}
            <Section label="วันที่">
              <input type="date"
                value={date}
                min={new Date().toISOString().split('T')[0]}
                onChange={e => setDate(e.target.value)}
                style={{ width: '100%', border: '1px solid #e2e8f0', borderRadius: 8, padding: '9px 12px', fontSize: 13, color: '#0f172a', background: '#f8fafc', outline: 'none', boxSizing: 'border-box' }} />
            </Section>

            {/* เวลา */}
            <Section label="เวลาเริ่มต้น">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, marginBottom: 14 }}>
                {TIME_SLOTS.map(t => (
                  <button key={t} onClick={() => setStartTime(t)}
                    style={{ padding: '8px 0', borderRadius: 8, border: `1px solid ${startTime === t ? '#2563eb' : '#e2e8f0'}`, background: startTime === t ? '#eff6ff' : '#fff', color: startTime === t ? '#1d4ed8' : '#475569', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                    {t}
                  </button>
                ))}
              </div>
              <p style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>ระยะเวลา</p>
              <div style={{ display: 'flex', gap: 6 }}>
                {DURATIONS.map(d => (
                  <button key={d.hours} onClick={() => setDuration(d.hours)}
                    style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: `1px solid ${duration === d.hours ? '#2563eb' : '#e2e8f0'}`, background: duration === d.hours ? '#eff6ff' : '#fff', color: duration === d.hours ? '#1d4ed8' : '#475569', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                    {d.label}
                  </button>
                ))}
              </div>
              {startTime && (
                <div style={{ marginTop: 10, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>{startTime} – {endTime}</span>
                  <span style={{ fontSize: 12, color: '#64748b' }}>{formatDateShort(date)}</span>
                </div>
              )}
            </Section>

            {/* อาคาร */}
            <Section label="อาคาร">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {BUILDINGS.map(b => (
                  <button key={b.code} onClick={() => setBuilding(b.code)}
                    style={{ padding: '7px 14px', borderRadius: 8, border: `1px solid ${building === b.code ? '#2563eb' : '#e2e8f0'}`, background: building === b.code ? '#eff6ff' : '#fff', color: building === b.code ? '#1d4ed8' : '#475569', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                    {b.label}
                  </button>
                ))}
              </div>
            </Section>

            <button onClick={handleSearch} disabled={loading}
              style={{ width: '100%', background: loading ? '#94a3b8' : '#0f172a', color: '#fff', border: 'none', borderRadius: 10, padding: '13px 0', fontSize: 14, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              {loading ? (
                <>
                  <div style={{ width: 16, height: 16, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                  กำลังค้นหา...
                </>
              ) : 'ค้นหาห้องว่าง'}
            </button>
          </div>
        )}

        {/* ═══════════════════════════════════════════
            STEP 2 — ผลการค้นหา
        ═══════════════════════════════════════════ */}
        {step === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

            {/* summary bar */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4 }}>
              <div style={{ display: 'flex', gap: 12, fontSize: 12, color: '#475569', flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 700, color: '#0f172a' }}>{attendees} คน</span>
                <span>{formatDateShort(date)}</span>
                <span>{startTime}–{endTime}</span>
                {building && <span>{BUILDINGS.find(b => b.code === building)?.label}</span>}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#2563eb', fontWeight: 600 }}>
                <TrendingUp size={11} />
                AI Forecast
              </div>
            </div>

            {/* demand summary */}
            {rooms.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {[
                  { level: 'low',    label: 'ว่าง' },
                  { level: 'medium', label: 'เริ่มแน่น' },
                  { level: 'high',   label: 'แน่น' },
                ].map(s => {
                  const cfg = FORECAST_CONFIG[s.level]
                  const count = rooms.filter(r => (r.forecast?.demand_level || 'none') === s.level).length
                  return (
                    <div key={s.level} style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 10, padding: '10px 0', textAlign: 'center' }}>
                      <p style={{ fontSize: 22, fontWeight: 800, color: cfg.color, margin: 0 }}>{count}</p>
                      <p style={{ fontSize: 11, color: cfg.color, margin: 0, opacity: 0.8 }}>{s.label}</p>
                    </div>
                  )
                })}
              </div>
            )}

            {rooms.length === 0 ? (
              <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '3rem 1rem', textAlign: 'center' }}>
                <Building2 size={32} color="#cbd5e1" style={{ marginBottom: 12 }} />
                <p style={{ fontSize: 14, fontWeight: 600, color: '#475569', marginBottom: 4 }}>ไม่พบห้องว่าง</p>
                <p style={{ fontSize: 12, color: '#94a3b8', marginBottom: 16 }}>ลองเปลี่ยนวันที่หรือเวลา</p>
                <button onClick={() => setStep(1)} style={{ fontSize: 13, color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 }}>← ค้นหาใหม่</button>
              </div>
            ) : rooms.map((room, idx) => {
              const level = room.forecast?.demand_level || 'none'
              const cfg = FORECAST_CONFIG[level]
              const isTop = idx === 0 && level === 'low'

              return (
                <div key={room.id}
                  onClick={() => { setSelectedRoom(room); setStep(3) }}
                  style={{ background: '#fff', border: `1px solid ${isTop ? '#bfdbfe' : '#e2e8f0'}`, borderLeft: `3px solid ${cfg.dot}`, borderRadius: 10, padding: '14px', cursor: 'pointer', transition: 'box-shadow 0.15s' }}
                  onMouseEnter={e => e.currentTarget.style.boxShadow = '0 2px 12px rgba(0,0,0,0.07)'}
                  onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}>

                  {isTop && (
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 5, padding: '2px 8px', marginBottom: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: '#1d4ed8' }}>แนะนำ</span>
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3, flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{room.name}</span>
                        <span style={{ fontSize: 11, fontWeight: 600, color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 5, padding: '1px 7px' }}>
                          {cfg.badge}
                        </span>
                      </div>
                      <p style={{ fontSize: 12, color: '#64748b', margin: 0 }}>
                        {room.building_name} · ชั้น {room.floor} · {room.capacity} ที่นั่ง · {room.room_type}
                      </p>
                    </div>
                    <ChevronRight size={15} color="#cbd5e1" style={{ flexShrink: 0, marginLeft: 8 }} />
                  </div>
                </div>
              )
            })}

            {rooms.length > 0 && (
              <p style={{ textAlign: 'center', fontSize: 11, color: '#94a3b8', marginTop: 4 }}>เรียงตามการคาดการณ์ AI</p>
            )}
          </div>
        )}

        {/* ═══════════════════════════════════════════
            STEP 3 — ยืนยัน
        ═══════════════════════════════════════════ */}
        {step === 3 && selectedRoom && (() => {
          const level = selectedRoom.forecast?.demand_level || 'none'
          const cfg = FORECAST_CONFIG[level]
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

              <Section label="ห้องที่เลือก">
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 8, background: '#f1f5f9', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Building2 size={18} color="#475569" />
                  </div>
                  <div>
                    <p style={{ fontSize: 15, fontWeight: 700, color: '#0f172a', margin: '0 0 2px' }}>{selectedRoom.name}</p>
                    <p style={{ fontSize: 12, color: '#64748b', margin: 0 }}>{selectedRoom.building_name} · ชั้น {selectedRoom.floor} · {selectedRoom.room_type}</p>
                  </div>
                </div>

                {[
                  { label: 'วันที่',         value: formatDate(date) },
                  { label: 'เวลา',           value: `${startTime} – ${endTime} น.` },
                  { label: 'ผู้เข้าร่วม',   value: `${attendees} คน` },
                ].map((r, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '9px 0', borderTop: i === 0 ? '1px solid #f1f5f9' : '1px solid #f1f5f9' }}>
                    <span style={{ fontSize: 13, color: '#64748b' }}>{r.label}</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>{r.value}</span>
                  </div>
                ))}

                {cfg.badge !== '—' && (
                  <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 6, background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 8, padding: '8px 12px' }}>
                    <div style={{ width: 7, height: 7, borderRadius: '50%', background: cfg.dot }} />
                    <span style={{ fontSize: 12, fontWeight: 600, color: cfg.color }}>คาดการณ์: {cfg.badge}</span>
                  </div>
                )}
              </Section>

              <Section label="หัวข้อการประชุม">
                <input
                  type="text"
                  placeholder="เช่น ประชุมกลุ่ม, นำเสนองาน, อบรม..."
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  autoFocus
                  style={{ width: '100%', border: '1px solid #e2e8f0', borderRadius: 8, padding: '9px 12px', fontSize: 13, color: '#0f172a', background: '#f8fafc', outline: 'none', boxSizing: 'border-box' }} />
              </Section>

              <button onClick={handleBook} disabled={bookingLoading}
                style={{ width: '100%', background: bookingLoading ? '#94a3b8' : '#0f172a', color: '#fff', border: 'none', borderRadius: 10, padding: '13px 0', fontSize: 14, fontWeight: 700, cursor: bookingLoading ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                {bookingLoading ? (
                  <>
                    <div style={{ width: 16, height: 16, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                    กำลังจอง...
                  </>
                ) : 'ยืนยันการจอง'}
              </button>
            </div>
          )
        })()}

      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input[type="date"]:focus { border-color: #93c5fd !important; background: #fff !important; }
        input[type="text"]:focus { border-color: #93c5fd !important; background: #fff !important; }
      `}</style>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────
function Section({ label, children }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '14px' }}>
      <p style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.07em', margin: '0 0 12px' }}>{label}</p>
      {children}
    </div>
  )
}

function StepBtn({ children, onClick, primary }) {
  return (
    <button onClick={onClick} style={{ width: 38, height: 38, borderRadius: 8, border: `1px solid ${primary ? '#2563eb' : '#e2e8f0'}`, background: primary ? '#2563eb' : '#fff', color: primary ? '#fff' : '#475569', fontSize: 20, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
      {children}
    </button>
  )
}