import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Clock, BarChart2, TrendingUp, Calendar, X,
  Building2, AlertTriangle, Zap,
  Download, ChevronDown, FileSpreadsheet, Check, LayoutGrid,
  BookOpen, Wrench, Loader2, Sparkles
} from 'lucide-react'
import api from '../api/axios'

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes scaleIn{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:scale(1)}}
@keyframes rot{to{transform:rotate(360deg)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .06s ease both}
.au2{animation:fadeUp .28s .12s ease both}
.si{animation:scaleIn .22s ease both}
.pulse{animation:pulse 2s ease-in-out infinite}
`

// ข้อมูลห้องดึงจาก API จริง (rooms/admin-status/) — ไม่ใช้ mock
// ── DOW map ───────────────────────────────────────────────────
const DOW_TH = ['อาทิตย์','จันทร์','อังคาร','พุธ','พฤหัสบดี','ศุกร์','เสาร์']

// ── helper: ตรวจว่า TermBooking ใช้งานอยู่ ณ เวลาปัจจุบัน ──
const isTermActive = (tb) => {
  const now  = new Date()
  const dow  = now.getDay() // 0=Sun
  const hour = now.getHours()
  const min  = now.getMinutes()

  // ตรวจ day_of_week (backend ใช้ 0=Mon หรือ 0=Sun — ปรับตาม backend จริง)
  // สมมติ backend: 0=Mon..6=Sun  →  แปลง JS dow
  const jsDow2Backend = (d) => (d === 0 ? 6 : d - 1)
  const beDow = jsDow2Backend(dow)
  if (tb.day_of_week !== beDow) return false

  // ตรวจ term_start / term_end
  const today = now.toISOString().split('T')[0]
  if (tb.term_start && today < tb.term_start) return false
  if (tb.term_end   && today > tb.term_end)   return false

  // ตรวจ start_time / end_time  (format "HH:MM:SS")
  const [sh, sm] = (tb.start_time || '00:00').split(':').map(Number)
  const [eh, em] = (tb.end_time   || '23:59').split(':').map(Number)
  const nowMin   = hour * 60 + min
  const startMin = sh * 60 + sm
  const endMin   = eh * 60 + em
  return nowMin >= startMin && nowMin < endMin
}

// ── TermBooking ของห้องนี้ที่ active วันนี้ (ไม่จำเป็นต้องตรงเวลา) ──
const getTermsToday = (roomId, termBookings) => {
  const now  = new Date()
  const today = now.toISOString().split('T')[0]
  const jsDow2Backend = (d) => (d === 0 ? 6 : d - 1)
  const beDow = jsDow2Backend(now.getDay())

  return termBookings.filter(tb =>
    tb.room === roomId &&
    tb.status === 'active' &&
    tb.day_of_week === beDow &&
    (!tb.term_start || today >= tb.term_start) &&
    (!tb.term_end   || today <= tb.term_end)
  )
}

// ── TermBooking ของห้องนี้ทั้งสัปดาห์ (สำหรับ tooltip/expand) ──
const getTermsThisWeek = (roomId, termBookings) => {
  const now   = new Date()
  const today = now.toISOString().split('T')[0]
  return termBookings.filter(tb =>
    tb.room === roomId &&
    tb.status === 'active' &&
    (!tb.term_start || today >= tb.term_start) &&
    (!tb.term_end   || today <= tb.term_end)
  )
}

const getRoomData = (name, adminRooms) =>
  adminRooms?.find(r => name?.includes(r.code) || r.name === name) || null

// ── ตรวจว่าเลยเวลาสิ้นสุดแล้วหรือยัง ──────────────────────
const isPast = (endTime) => new Date() > new Date(endTime)
const isNow  = (start, end) => {
  const now = new Date()
  return now >= new Date(start) && now <= new Date(end)
}
const isSoon = (start) => {
  const now  = new Date()
  const diff = new Date(start) - now
  return diff > 0 && diff <= 30 * 60 * 1000
}

function useDevice() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', fn); return () => window.removeEventListener('resize', fn)
  }, [])
  return isMobile
}

// ── STATUS CONFIG ─────────────────────────────────────────────
const STATUS_CFG = {
  pending:   { label:'กำลังจอง',    bg:'bg-yellow-50',   text:'text-yellow-700', dot:'#f59e0b' },
  approved:  { label:'ยืนยันแล้ว',  bg:'bg-blue-50',     text:'text-blue-700',   dot:'#3b82f6' },
  active:    { label:'กำลังใช้งาน', bg:'bg-emerald-50',  text:'text-emerald-700',dot:'#10b981' },
  soon:      { label:'จะเริ่มเร็วๆ',bg:'bg-amber-50',    text:'text-amber-700',  dot:'#f59e0b' },
  booked:    { label:'จองแล้ว',     bg:'bg-sky-50',      text:'text-sky-700',    dot:'#0ea5e9' },
  maintenance:{ label:'ซ่อมบำรุง',  bg:'bg-rose-50',     text:'text-rose-700',   dot:'#ef4444' },
  disabled:  { label:'ปิดใช้งาน',    bg:'bg-slate-200',   text:'text-slate-700',  dot:'#64748b' },
  cancelled: { label:'ยกเลิกแล้ว',  bg:'bg-red-50',      text:'text-red-600',    dot:'#f87171' },
  completed: { label:'เสร็จสิ้น',   bg:'bg-slate-100',   text:'text-slate-500',  dot:'#94a3b8' },
  // ── สถานะเทอม (ใหม่) ─────────────────────────────────────
  term_active: { label:'ชั่วโมงเรียน', bg:'bg-purple-50', text:'text-purple-700', dot:'#9333ea' },
  term_today:  { label:'มีตารางสอน',   bg:'bg-violet-50', text:'text-violet-700', dot:'#7c3aed' },
}
const getS = s => {
  if (s === 'no_show') return STATUS_CFG.cancelled
  return STATUS_CFG[s] || { label:s, bg:'bg-slate-100', text:'text-slate-500', dot:'#94a3b8' }
}

const getEffectiveS = (b) => {
  if (b.status === 'approved') {
    if (isPast(b.end_time))              return STATUS_CFG.completed
    if (isNow(b.start_time, b.end_time)) return STATUS_CFG.active
    if (isSoon(b.start_time))            return STATUS_CFG.soon
    return STATUS_CFG.approved
  }
  if (b.status === 'pending') return STATUS_CFG.pending
  return getS(b.status)
}

// ── คำนวณ room status หลัก รวม term ─────────────────────────
const getRoomStatus = (room, bookings, termBookings) => {
  const now = new Date()
  if (room?.status === 'maintenance') {
    return { state:'maintenance', label:'ซ่อมบำรุง', color:'#ef4444', bg:'#fff1f2', border:'#fecdd3', allBookings: [], termsToday: [], termNow: null }
  }
  if (room?.status === 'disabled') {
    return { state:'disabled', label:'ปิดใช้งาน', color:'#64748b', bg:'#f8fafc', border:'#cbd5e1', allBookings: [], termsToday: [], termNow: null }
  }

  const roomName = room?.name || ''
  const roomId = room?.roomId
  const roomBookings = bookings.filter(b => {
    const bn = b.room_name || `ห้อง #${b.room}`
    const sameRoomId = roomId !== undefined && roomId !== null
      ? String(b.room) === String(roomId)
      : false
    return (sameRoomId || bn === roomName)
      && (b.status === 'approved' || b.status === 'pending')
      && new Date(b.end_time) > now
  })
  const sorted = [...roomBookings].sort((a,b) => new Date(a.start_time)-new Date(b.start_time))

  const active   = sorted.find(b => b.status === 'approved' && isNow(b.start_time, b.end_time))
  const upcoming = sorted.find(b => b.status === 'approved' && isSoon(b.start_time))
  const pending  = sorted.find(b => b.status === 'pending')
  const booked   = sorted.find(b => b.status === 'approved' && !isPast(b.end_time) && !isNow(b.start_time, b.end_time) && !isSoon(b.start_time))

  // ── term status ──────────────────────────────────────────
  const termsToday = roomId ? getTermsToday(roomId, termBookings) : []
  const termNow    = termsToday.find(tb => isTermActive(tb))
  const hasTermToday = termsToday.length > 0

  let state, label, color, bg, border
  if (active)          { state='active';      label='กำลังใช้งาน';  color='#10b981'; bg='#d1fae5'; border='#6ee7b7' }
  else if (termNow)    { state='term_active'; label='ชั่วโมงเรียน'; color='#9333ea'; bg='#f3e8ff'; border='#c4b5fd' }
  else if (upcoming)   { state='soon';        label='จะเริ่มเร็วๆ'; color='#f59e0b'; bg='#fef3c7'; border='#fcd34d' }
  else if (pending)    { state='pending';     label='กำลังจอง';    color='#eab308'; bg='#fefce8'; border='#fde047' }
  else if (hasTermToday){ state='term_today'; label='มีตารางสอน';   color='#7c3aed'; bg='#ede9fe'; border='#a78bfa' }
  else if (booked)     { state='booked';      label='ยืนยันแล้ว';  color='#3b82f6'; bg='#eff6ff'; border='#93c5fd' }
  else                 { state='free';        label='ว่าง';        color='#94a3b8'; bg='#f1f5f9'; border='#cbd5e1' }

  return { state, label, color, bg, border, allBookings: sorted, termsToday, termNow }
}

const extractRooms = (bookings, adminRooms = []) => {
  const map = {}
  adminRooms.forEach(r => {
    map[`room-${r.id}`] = {
      roomKey: `room-${r.id}`,
      name: r.name,
      roomId: r.id,
      code: r.code || r.name,
      building: r.building || 'อาคาร ODL',
      capacity: r.capacity,
      util: r.util_rate,
      peak: null,
      status: r.status,
    }
  })
  bookings.forEach(b => {
    const bname = b.room_name || `ห้อง #${b.room}`
    const key = `booking-${b.room}`
    if (!map[key]) {
      map[key] = {
        roomKey: key,
        name: bname,
        roomId: b.room,
        code: bname,
        building: 'อื่นๆ',
        capacity: null,
        util: null,
        peak: null,
        status: 'available',
      }
    } else {
      map[key].roomId = b.room
    }
  })
  return Object.values(map).sort((a, b) => a.name.localeCompare(b.name, 'th'))
}

const BUILDING_ORDER = ['อาคาร ODL (Online Digital Learning)', 'อาคาร ODL', 'อื่นๆ']

// ============================================================
// EXPORT BUTTON
// ============================================================
const SHEETS = [
  { key:'users',         label:'ผู้ใช้งาน',          icon:'👤' },
  { key:'buildings',     label:'อาคาร',             icon:'🏛️' },
  { key:'rooms',         label:'ห้อง',              icon:'🚪' },
  { key:'facilities',    label:'อุปกรณ์ในห้อง',      icon:'🖥️' },
  { key:'bookings',      label:'รายการการจอง',      icon:'📅' },
  { key:'term_bookings', label:'ตารางสอน (เทอม)',    icon:'🗓️' },
  { key:'logs',          label:'บันทึกการแก้ไขสถานะ',  icon:'📋' },
  { key:'forecasts',     label:'ผลพยากรณ์ AI',      icon:'🤖' },
  { key:'notifications', label:'การแจ้งเตือน',       icon:'🔔' },
  { key:'stats',         label:'สถิติห้อง',           icon:'📊' },
]

function ExportButton({ isMobile = false }) {
  const [open,     setOpen]     = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [selected, setSelected] = useState(new Set(['all']))
  const [done,     setDone]     = useState(false)

  const toggleSheet = (key) => {
    if (key === 'all') { setSelected(new Set(['all'])); return }
    const next = new Set(selected)
    next.delete('all')
    if (next.has(key)) next.delete(key)
    else next.add(key)
    if (next.size === 0) next.add('all')
    setSelected(next)
  }

  const isAll = selected.has('all')

  const handleExport = async () => {
    setLoading(true)
    try {
      const sheets = isAll ? 'all' : [...selected].join(',')
      const res = await api.get(`export/excel/?sheets=${sheets}`, { responseType:'blob' })
      const contentType = res.headers['content-type'] || ''
      if (contentType.includes('application/json')) {
        const text = await res.data.text()
        alert('Server Error: ' + text)
        return
      }
      const blob = new Blob([res.data], { type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const url  = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href  = url
      const now  = new Date().toISOString().slice(0,10).replace(/-/g,'')
      link.setAttribute('download', `room_booking_export_${now}.xlsx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      setDone(true)
      setTimeout(() => { setDone(false); setOpen(false) }, 2000)
    } catch (err) {
      alert('เกิดข้อผิดพลาดในการส่งออกข้อมูล')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 font-semibold transition-all active:scale-95
          ${isMobile
            ? 'text-xs bg-emerald-500 hover:bg-emerald-600 text-white px-2.5 py-1.5 rounded-lg'
            : 'text-xs bg-emerald-500 hover:bg-emerald-600 text-white px-3 py-1.5 rounded-lg shadow-sm'
          }`}>
        <Download size={isMobile ? 12 : 13} />
        {!isMobile && 'Export Excel'}
        <ChevronDown size={11} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-72 bg-white border border-blue-100 rounded-2xl shadow-2xl z-50 overflow-hidden"
          style={{ animation:'fadeUp .2s ease both' }}>
          <div className="px-4 py-3 flex items-center justify-between border-b border-blue-50 bg-emerald-50">
            <div className="flex items-center gap-2">
              <FileSpreadsheet size={15} className="text-emerald-600" />
              <span className="text-sm font-bold text-emerald-800">Export ข้อมูล Excel</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-600">
              <X size={14} />
            </button>
          </div>
          <div className="px-4 py-3">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">เลือก Sheet ที่ต้องการ</p>
            <button onClick={() => toggleSheet('all')}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-semibold mb-1 transition-all
                ${isAll ? 'bg-emerald-600 text-white' : 'hover:bg-emerald-50 text-slate-700 border border-slate-100'}`}>
              <span>📦</span>
              <span className="flex-1 text-left">ทั้งหมด (All Sheets)</span>
              {isAll && <Check size={13} />}
            </button>
            <div className="border-t border-slate-100 my-2" />
            <div className="space-y-0.5 max-h-52 overflow-y-auto pr-1">
              {SHEETS.map(s => {
                const active = !isAll && selected.has(s.key)
                return (
                  <button key={s.key} onClick={() => toggleSheet(s.key)}
                    className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                      ${active
                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                        : 'hover:bg-slate-50 text-slate-600 border border-transparent'
                      }`}>
                    <span>{s.icon}</span>
                    <span className="flex-1 text-left">{s.label}</span>
                    {active && <Check size={11} className="text-emerald-600" />}
                  </button>
                )
              })}
            </div>
          </div>
          <div className="px-4 pb-4">
            <p className="text-xs text-slate-400 mb-2.5 text-center">
              {isAll ? 'จะ export ทุก Sheet (10 Sheet)' : `เลือก ${selected.size} Sheet`}
            </p>
            <button onClick={handleExport} disabled={loading || done}
              className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold transition-all active:scale-95 disabled:cursor-not-allowed
                ${done
                  ? 'bg-emerald-500 text-white'
                  : 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-md shadow-emerald-200 disabled:bg-slate-300'
                }`}>
              {loading
                ? <><div style={{width:14,height:14,border:'2px solid rgba(255,255,255,0.3)',borderTopColor:'#fff',borderRadius:'50%',animation:'spin 0.7s linear infinite'}} />กำลัง Export...</>
                : done
                  ? <><Check size={15} />ดาวน์โหลดสำเร็จ!</>
                  : <><Download size={15} />ดาวน์โหลด Excel</>
              }
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================
// BOOKING DETAIL MODAL
// ============================================================
function BookingDetailModal({ booking, onClose, onCancel, fmtTime, fmtDateFull }) {
  if (!booking) return null
  const s = getEffectiveS(booking)
  return (
    <div className="fixed inset-0 bg-slate-900/40 z-50 flex items-end md:items-center justify-center px-0 md:px-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-white w-full max-w-md rounded-t-3xl md:rounded-3xl shadow-2xl overflow-hidden si">
        <div className="px-5 py-4 flex items-center justify-between border-b border-blue-50">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full" style={{background:s.dot}} />
            <span className="font-bold text-slate-900 text-sm">รายละเอียดการจอง</span>
          </div>
          <button onClick={onClose} className="w-7 h-7 rounded-lg border border-blue-100 bg-blue-50 flex items-center justify-center text-slate-400 hover:text-blue-600"><X size={14} /></button>
        </div>
        <div className="px-5 py-4">
          <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 border border-blue-200 rounded-2xl p-4 flex items-center gap-3 mb-4">
            <div className="w-11 h-11 bg-blue-700 rounded-xl flex items-center justify-center flex-shrink-0"><Building2 size={20} color="#fff" /></div>
            <div>
              <p className="font-bold text-slate-900 text-base">{booking.room_name || `ห้อง #${booking.room}`}</p>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${s.bg} ${s.text}`}>{s.label}</span>
            </div>
          </div>
          <div className="border-2 border-blue-50 rounded-2xl overflow-hidden mb-4">
            {[
              {icon:'📋',label:'หัวข้อ',      value:booking.title},
              {icon:'📅',label:'วันที่',       value:fmtDateFull(booking.start_time)},
              {icon:'⏰',label:'เวลาเริ่ม',    value:fmtTime(booking.start_time)+' น.'},
              {icon:'⏱️',label:'เวลาสิ้นสุด', value:fmtTime(booking.end_time)+' น.'},
              {icon:'👥',label:'จำนวนคน',     value:`${booking.attendees} คน`},
            ].map((r,i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5 bg-white border-b border-blue-50 last:border-0">
                <span className="text-sm w-5 flex-shrink-0">{r.icon}</span>
                <span className="text-xs text-slate-500 w-20 flex-shrink-0">{r.label}</span>
                <span className="text-sm font-semibold text-slate-800 flex-1">{r.value}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-300 text-center mb-4">ID: #{booking.id}</p>
          {(booking.status === 'approved' || booking.status === 'pending') && !isPast(booking.end_time) && (
            <button onClick={() => onCancel(booking.id)}
              className="w-full border-2 border-red-100 text-red-500 hover:bg-red-50 py-3 rounded-2xl font-bold text-sm transition-colors">
              ยกเลิกการจองนี้
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ============================================================
// BAR CHART
// ============================================================
function BarChartBlock({ weekStats }) {
  const maxCount = Math.max(...weekStats.map(s=>s.count), 1)
  return (
    <div className="flex items-end gap-2 h-24">
      {weekStats.map((s,i) => {
        const h = Math.max((s.count/maxCount)*100, 4)
        const isToday = i === 6
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1">
            <span className="text-xs text-slate-400">{s.count||''}</span>
            <div className="w-full rounded-t-lg" style={{height:`${h}%`,background:isToday?'#1d4ed8':'#bfdbfe'}} />
            <span className={`text-xs font-medium ${isToday?'text-blue-700':'text-slate-400'}`}>{s.day}</span>
          </div>
        )
      })}
    </div>
  )
}

// ============================================================
// TERM SCHEDULE POPUP  (แสดงตารางสอนของห้องนี้วันนี้)
// ============================================================
function TermSchedulePopup({ termsToday, termNow, roomName }) {
  if (termsToday.length === 0) return null
  return (
    <div className="mt-2 rounded-xl border border-purple-200 bg-purple-50 px-3 py-2 space-y-1">
      <p className="text-xs font-bold text-purple-700 flex items-center gap-1 mb-1.5">
        <BookOpen size={10} />ตารางสอนวันนี้
      </p>
      {termsToday.map((tb, i) => {
        const nowActive = isTermActive(tb)
        return (
          <div key={i}
            className={`flex items-center gap-2 text-xs rounded-lg px-2 py-1 ${nowActive ? 'bg-purple-200/60' : ''}`}>
            <div
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{
                background: nowActive ? '#9333ea' : '#c4b5fd',
                animation: nowActive ? 'pulse 2s ease-in-out infinite' : undefined,
              }}
            />
            <span className={`tabular-nums font-semibold ${nowActive ? 'text-purple-800' : 'text-purple-600'}`}>
              {(tb.start_time||'').slice(0,5)}–{(tb.end_time||'').slice(0,5)}
            </span>
            {tb.subject_name && (
              <span className="text-purple-500 truncate flex-1">{tb.subject_name}</span>
            )}
            {nowActive && (
              <span className="text-xs bg-purple-600 text-white px-1.5 py-0.5 rounded-full font-bold flex-shrink-0">กำลังสอน</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ============================================================
// ROOM STATUS GRID
// ============================================================
function RoomStatusGrid({ bookings, termBookings, adminRooms, fmtTime, isMobile = false }) {
  const [tick, setTick] = useState(0)
  const [filterBuilding, setFilterBuilding] = useState('ทั้งหมด')
  const [filterState, setFilterState] = useState('all')
  const [selectedRoom, setSelectedRoom] = useState(null)

  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 30000)
    return () => clearInterval(t)
  }, [])

  const rooms = extractRooms(bookings, adminRooms)
  const roomStatuses = rooms.map(room => ({
    room,
    status: getRoomStatus(room, bookings, termBookings),
  }))

  const preferredBuildings = BUILDING_ORDER.filter(b => roomStatuses.some(({room}) => room.building === b))
  const extraBuildings = Array.from(new Set(roomStatuses.map(({room}) => room.building || 'อื่นๆ')))
    .filter(b => !BUILDING_ORDER.includes(b))
    .sort((a, b) => a.localeCompare(b, 'th'))
  const buildings = ['ทั้งหมด', ...preferredBuildings, ...extraBuildings]
  const filteredByBuilding = filterBuilding === 'ทั้งหมด'
    ? roomStatuses
    : roomStatuses.filter(({room}) => room.building === filterBuilding)

  const visibleRooms = filterState === 'all'
    ? filteredByBuilding
    : filteredByBuilding.filter(({status}) => status.state === filterState)

  const grouped = buildings
    .filter(b => b !== 'ทั้งหมด')
    .map(b => ({ building:b, rooms: visibleRooms.filter(({room}) => (room.building || 'อื่นๆ') === b) }))
    .filter(g => g.rooms.length > 0)

  const stateCounts = roomStatuses.reduce((acc, {status}) => {
    acc[status.state] = (acc[status.state] || 0) + 1
    return acc
  }, {})
  const activeCount      = stateCounts.active || 0
  const termActiveCount  = stateCounts.term_active || 0
  const termTodayCount   = stateCounts.term_today || 0
  const soonCount        = stateCounts.soon || 0
  const pendingCount     = stateCounts.pending || 0
  const bookedCount      = stateCounts.booked || 0
  const freeCount        = stateCounts.free || 0
  const maintenanceCount = stateCounts.maintenance || 0
  const disabledCount    = stateCounts.disabled || 0

  const BUILDING_ICONS = {
    'อาคาร ODL (Online Digital Learning)': '🏢',
    'อาคาร ODL': '🏢',
    'อื่นๆ': '🚪',
  }

  const stateFilters = [
    { key:'all', label:'ทั้งหมด', count: rooms.length },
    { key:'active', label:'กำลังใช้งาน', count: activeCount },
    { key:'term_active', label:'ชั่วโมงเรียน', count: termActiveCount },
    { key:'term_today', label:'มีตารางสอน', count: termTodayCount },
    { key:'pending', label:'กำลังจอง', count: pendingCount },
    { key:'soon', label:'จะเริ่มเร็วๆ', count: soonCount },
    { key:'booked', label:'จองแล้ว', count: bookedCount },
    { key:'free', label:'ว่าง', count: freeCount },
    { key:'maintenance', label:'ซ่อมบำรุง', count: maintenanceCount },
    { key:'disabled', label:'ปิดใช้งาน', count: disabledCount },
  ]

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-emerald-400" />
            <span className="text-xs text-slate-600 font-medium">กำลังใช้งาน <span className="font-extrabold text-emerald-600">{activeCount}</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-purple-500" />
            <span className="text-xs text-slate-600 font-medium">ชั่วโมงเรียน <span className="font-extrabold text-purple-600">{termActiveCount}</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-violet-300" />
            <span className="text-xs text-slate-600 font-medium">มีตารางสอน <span className="font-extrabold text-violet-600">{termTodayCount}</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-yellow-300" />
            <span className="text-xs text-slate-600 font-medium">กำลังจอง <span className="font-extrabold text-yellow-600">{pendingCount}</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-amber-300" />
            <span className="text-xs text-slate-600 font-medium">จะเริ่มเร็วๆ <span className="font-extrabold text-amber-600">{soonCount}</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-sky-400" />
            <span className="text-xs text-slate-600 font-medium">จองแล้ว <span className="font-extrabold text-sky-700">{bookedCount}</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-slate-200" />
            <span className="text-xs text-slate-600 font-medium">ว่าง <span className="font-extrabold text-slate-500">{freeCount}</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-rose-400" />
            <span className="text-xs text-slate-600 font-medium">ซ่อมบำรุง <span className="font-extrabold text-rose-600">{maintenanceCount}</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-slate-500" />
            <span className="text-xs text-slate-600 font-medium">ปิดใช้งาน <span className="font-extrabold text-slate-600">{disabledCount}</span></span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-1.5 text-xs text-slate-400">
          <Clock size={11} className="pulse" />
          <span>อัปเดตทุก 30 วิ</span>
        </div>
      </div>

      <div className="flex gap-1.5 flex-wrap">
        {stateFilters.map(s => (
          <button key={s.key} onClick={() => setFilterState(s.key)}
            className={`text-xs px-3 py-1.5 rounded-full font-semibold transition-all whitespace-nowrap
              ${filterState === s.key
                ? 'bg-slate-900 text-white shadow-sm'
                : 'bg-white border border-slate-100 text-slate-600 hover:border-slate-300'
              }`}>
            {s.label}
            <span className={`ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full ${filterState === s.key ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-500'}`}>
              {s.count}
            </span>
          </button>
        ))}
      </div>

      <div className="flex gap-1.5 flex-wrap">
        {buildings.map(b => (
          <button key={b} onClick={() => setFilterBuilding(b)}
            className={`text-xs px-3 py-1.5 rounded-full font-semibold transition-all
              ${filterBuilding === b
                ? 'bg-blue-700 text-white shadow-sm'
                : 'bg-white border border-blue-100 text-slate-600 hover:border-blue-300'
              }`}>
            {b !== 'ทั้งหมด' && <span className="mr-1">{BUILDING_ICONS[b]||'🚪'}</span>}
            {b}
          </button>
        ))}
      </div>

      {grouped.length === 0 ? (
        <div className="bg-white border border-blue-100 rounded-2xl py-12 text-center shadow-sm">
          <LayoutGrid size={30} className="text-blue-200 mx-auto mb-3" />
          <p className="text-slate-400 text-sm">ไม่พบข้อมูลห้อง</p>
        </div>
      ) : (
        <div className="space-y-3">
          {grouped.map(({ building, rooms: brooms }) => (
            <div key={building}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">{BUILDING_ICONS[building]||'🚪'}</span>
                <h3 className="text-sm font-bold text-slate-700">{building}</h3>
                <span className="text-xs text-slate-400">({brooms.length} ห้อง)</span>
                <div className="flex-1 h-px bg-slate-100 ml-2" />
              </div>
              <div className={`grid gap-2.5 ${isMobile ? 'grid-cols-2' : 'grid-cols-3 lg:grid-cols-4 xl:grid-cols-5'}`}>
                {brooms.map(({room, status: rs}) => {
                  const roomKey = room.roomKey || String(room.roomId || room.name)
                  const isOpen = selectedRoom === roomKey
                  return (
                    <div
                      key={roomKey}
                      className={`relative cursor-pointer select-none ${isOpen && rs.termsToday.length > 0 ? 'col-span-2' : ''}`}
                      onClick={() => setSelectedRoom(isOpen ? null : roomKey)}
                    >
                      <div
                        className="rounded-2xl border-2 p-3 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
                        style={{
                          background: rs.bg,
                          borderColor: isOpen ? rs.color : rs.border,
                          boxShadow: isOpen ? `0 0 0 3px ${rs.color}30` : undefined,
                        }}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div
                            className="w-2.5 h-2.5 rounded-full flex-shrink-0 mt-0.5"
                            style={{
                              background: rs.color,
                              boxShadow: ['active', 'pending', 'term_active', 'maintenance'].includes(rs.state)
                                ? `0 0 0 4px ${rs.color}30`
                                : undefined,
                              animation: ['active', 'pending', 'term_active', 'maintenance'].includes(rs.state)
                                ? 'pulse 2s ease-in-out infinite'
                                : undefined,
                            }}
                          />
                          <div className="flex items-center gap-1 flex-wrap justify-end">
                            {rs.termsToday.length > 0 && rs.state !== 'term_active' && (
                              <span className="text-xs font-bold px-1.5 py-0.5 rounded-full leading-tight"
                                style={{ background:'#ede9fe', color:'#7c3aed', fontSize:'9px' }}>
                                📚เทอม
                              </span>
                            )}
                            <span
                              className="text-xs font-bold px-1.5 py-0.5 rounded-full leading-tight"
                              style={{ background: rs.color + '20', color: rs.color, fontSize:'10px' }}>
                              {rs.label}
                            </span>
                          </div>
                        </div>

                        <p className="text-sm font-extrabold text-slate-800 leading-tight mb-1 truncate">{room.name}</p>

                        {rs.state === 'maintenance' || rs.state === 'disabled' ? (
                          <p className="text-xs text-slate-500 mt-1">
                            {rs.state === 'maintenance' ? 'กำลังปิดห้องเพื่อซ่อมบำรุง' : 'ห้องถูกปิดใช้งาน'}
                          </p>
                        ) : rs.allBookings.length === 0 && rs.termsToday.length === 0 ? (
                          <p className="text-xs text-slate-400 mt-1">ไม่มีการจอง</p>
                        ) : (
                          <div className="mt-1.5 space-y-1">
                            {rs.allBookings.map((bk, bi) => {
                              const bNow  = isNow(bk.start_time, bk.end_time)
                              const bSoon = isSoon(bk.start_time)
                              const bPend = bk.status === 'pending'
                              const dotC  = bNow ? '#10b981' : bSoon ? '#f59e0b' : bPend ? '#eab308' : '#3b82f6'
                              const timeC = bNow ? 'text-emerald-600 font-bold' : bSoon ? 'text-amber-600 font-semibold' : bPend ? 'text-yellow-600' : 'text-blue-500'
                              return (
                                <div key={bi} className="flex items-center gap-1.5">
                                  <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: dotC }} />
                                  <span className={`text-[11px] ${timeC} tabular-nums`}>
                                    {fmtTime(bk.start_time)}–{fmtTime(bk.end_time)}
                                  </span>
                                  {bNow && <span className="text-[10px] text-emerald-600 font-bold">●</span>}
                                  {bPend && <span className="text-[10px] text-yellow-500">?</span>}
                                </div>
                              )
                            })}
                          </div>
                        )}

                        {isOpen && rs.termsToday.length > 0 && (
                          <TermSchedulePopup
                            termsToday={rs.termsToday}
                            termNow={rs.termNow}
                            roomName={room.name}
                          />
                        )}

                        {!isOpen && rs.termsToday.length > 0 && (
                          <p className="text-xs text-purple-400 mt-1.5 font-medium">
                            📚 {rs.termsToday.length} คาบ วันนี้ · แตะเพื่อดู
                          </p>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-white border border-blue-100 rounded-2xl p-3 shadow-sm">
        <div className={`flex ${isMobile ? 'flex-col gap-2' : 'items-center gap-5'}`}>
          <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">สรุปสถานะห้องทั้งหมด {rooms.length} ห้อง</p>
          <div className="flex gap-4 flex-wrap">
            <div className="text-center">
              <p className="text-xl font-extrabold text-emerald-600">{activeCount}</p>
              <p className="text-xs text-slate-400">กำลังใช้งาน</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-purple-600">{termActiveCount}</p>
              <p className="text-xs text-slate-400">ชั่วโมงเรียน</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-violet-500">{termTodayCount}</p>
              <p className="text-xs text-slate-400">มีตารางสอน</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-yellow-500">{pendingCount}</p>
              <p className="text-xs text-slate-400">กำลังจอง</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-amber-500">{soonCount}</p>
              <p className="text-xs text-slate-400">จะเริ่มเร็วๆ</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-sky-700">{bookedCount}</p>
              <p className="text-xs text-slate-400">จองแล้ว</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-slate-400">{freeCount}</p>
              <p className="text-xs text-slate-400">ว่างอยู่</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-rose-600">{maintenanceCount}</p>
              <p className="text-xs text-slate-400">ซ่อมบำรุง</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-slate-600">{disabledCount}</p>
              <p className="text-xs text-slate-400">ปิดใช้งาน</p>
            </div>
            <div className="text-center">
              <p className="text-xl font-extrabold text-blue-700">{rooms.length}</p>
              <p className="text-xs text-slate-400">ทั้งหมด</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================
// MAINTENANCE INSIGHTS
// ============================================================
const normalizeText = (value) =>
  String(value ?? '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ')

const jsDowToBackend = (dow) => (dow === 0 ? 6 : dow - 1)
const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

const isTermBookingActiveNow = (tb) => {
  const now = new Date()
  const today = now.toISOString().split('T')[0]
  if (tb.term_start && today < tb.term_start) return false
  if (tb.term_end && today > tb.term_end) return false
  if (tb.day_of_week !== jsDowToBackend(now.getDay())) return false

  const [sh, sm] = String(tb.start_time || '00:00').split(':').map(Number)
  const [eh, em] = String(tb.end_time || '23:59').split(':').map(Number)
  const current = now.getHours() * 60 + now.getMinutes()
  return current >= (sh * 60 + sm) && current < (eh * 60 + em)
}

const resolveRoomFromRecord = (record, adminRooms = []) => {
  if (!record) return null
  const roomId = record.room ?? record.room_id ?? record.id ?? null
  const roomName = normalizeText(record.room_name || record.name || '')
  const roomCode = normalizeText(record.room_code || record.code || '')

  return adminRooms.find(room => {
    const sameId = roomId !== null && String(room.id) === String(roomId)
    const sameName = roomName && (
      normalizeText(room.name) === roomName ||
      normalizeText(room.code) === roomName
    )
    const sameCode = roomCode && (
      normalizeText(room.name) === roomCode ||
      normalizeText(room.code) === roomCode
    )
    return sameId || sameName || sameCode
  }) || null
}

const buildMaintenanceInsights = ({
  adminRooms = [],
  bookings = [],
  termBookings = [],
  dashboard = {},
  slots = [],
}) => {
  const roomMap = new Map()

  adminRooms.forEach(room => {
    const base = {
      id: room.id,
      name: room.name,
      code: room.code || room.name,
      building: room.building || 'ไม่ระบุ',
      capacity: room.capacity || 0,
      bookingCount: 0,
      approvedCount: 0,
      completedCount: 0,
      pendingCount: 0,
      checkedInCount: 0,
      termCount: 0,
      termTodayCount: 0,
      termActiveCount: 0,
      demandAlerts: [],
      reasons: [],
      usageIndex: 0,
      riskIndex: 0,
      idleIndex: 0,
      termPressureIndex: 0,
      utilizationShare: Number(room.util_rate || 0),
    }
    ;[String(room.id), normalizeText(room.name), normalizeText(room.code)]
      .filter(Boolean)
      .forEach(key => roomMap.set(key, base))
  })

  const getRoomBucket = (record) => {
    const resolved = resolveRoomFromRecord(record, adminRooms)
    if (resolved) {
      const keys = [String(resolved.id), normalizeText(resolved.name), normalizeText(resolved.code)]
      const existing = keys.map(k => roomMap.get(k)).find(Boolean)
      if (existing) return existing

      const created = {
        id: resolved.id,
        name: resolved.name,
        code: resolved.code || resolved.name,
        building: resolved.building || 'ไม่ระบุ',
        capacity: resolved.capacity || 0,
        bookingCount: 0,
        approvedCount: 0,
        completedCount: 0,
        pendingCount: 0,
        checkedInCount: 0,
        termCount: 0,
        termTodayCount: 0,
        termActiveCount: 0,
        demandAlerts: [],
        reasons: [],
        usageIndex: 0,
        riskIndex: 0,
        idleIndex: 0,
        termPressureIndex: 0,
        utilizationShare: 0,
      }
      keys.forEach(key => roomMap.set(key, created))
      return created
    }
    return null
  }

  bookings.forEach(booking => {
    const bucket = getRoomBucket(booking)
    if (!bucket) return
    if (['approved', 'completed', 'checked_in', 'pending'].includes(booking.status)) {
      bucket.bookingCount += 1
    }
    if (booking.status === 'approved') bucket.approvedCount += 1
    if (booking.status === 'completed') bucket.completedCount += 1
    if (booking.status === 'pending') bucket.pendingCount += 1
    if (booking.status === 'checked_in') bucket.checkedInCount += 1
  })

  const todayDow = jsDowToBackend(new Date().getDay())
  termBookings.forEach(tb => {
    const bucket = getRoomBucket(tb)
    if (!bucket) return
    if (tb.status === 'active') bucket.termCount += 1
    if (tb.status === 'active' && tb.day_of_week === todayDow) bucket.termTodayCount += 1
    if (tb.status === 'active' && isTermBookingActiveNow(tb)) bucket.termActiveCount += 1
  })

  const alerts = Array.isArray(dashboard?.demand_alerts) ? dashboard.demand_alerts : []
  const alertMap = new Map()
  alerts.forEach(alert => {
    const key = normalizeText(alert.room__name || '')
    if (key) alertMap.set(key, alert)
  })

  const rooms = Array.from(new Set(roomMap.values()))
  const maxBookings = Math.max(...rooms.map(room => room.bookingCount), 1)
  const maxCapacity = Math.max(...rooms.map(room => room.capacity || 0), 1)

  rooms.forEach(room => {
    const demandAlert = alertMap.get(normalizeText(room.name)) || alertMap.get(normalizeText(room.code))
    const usageIndex = Math.round((room.bookingCount / maxBookings) * 100)
    const idleIndex = room.bookingCount === 0 && room.termCount === 0 ? 100 : Math.max(0, 100 - usageIndex)
    const termPressureIndex = Math.round(clamp((room.termTodayCount * 28) + (room.termCount * 8), 0, 100))
    const riskIndex = Math.round(clamp(
      (usageIndex * 0.35) +
      (room.pendingCount * 9) +
      (room.termActiveCount * 14) +
      (room.capacity >= 40 ? 4 : 0) +
      (demandAlert ? 18 : 0),
      0,
      100,
    ))

    const reasons = []
    if (room.bookingCount === 0 && room.termCount === 0) reasons.push('ไม่มีการใช้งาน')
    if (room.bookingCount >= Math.ceil(maxBookings * 0.7) && room.bookingCount > 0) reasons.push('ใช้งานถี่')
    if (room.pendingCount > 0) reasons.push(`รออนุมัติ ${room.pendingCount} รายการ`)
    if (room.termTodayCount > 0) reasons.push(`มีคาบเทอมวันนี้ ${room.termTodayCount} คาบ`)
    if (room.termCount > 0) reasons.push(`มีตารางสอนรวม ${room.termCount} คาบ`)
    if (demandAlert) reasons.push(`AI เตือน ${demandAlert.hour}:00`)
    if ((room.capacity || 0) / maxCapacity >= 0.85 && room.bookingCount === 0) reasons.push('ห้องใหญ่แต่เงียบ')

    room.demandAlerts = demandAlert ? [demandAlert] : []
    room.usageIndex = usageIndex
    room.idleIndex = idleIndex
    room.termPressureIndex = termPressureIndex
    room.riskIndex = riskIndex
    room.reasons = reasons.slice(0, 4)
    room.utilizationShare = Number(room.utilizationShare || 0)
  })

  const rankedRooms = [...rooms]
    .filter(room => room.bookingCount > 0 || room.termCount > 0)
    .sort((a, b) => {
      if (b.riskIndex !== a.riskIndex) return b.riskIndex - a.riskIndex
      return b.bookingCount - a.bookingCount
    })
    .slice(0, 6)

  const busyRooms = [...rooms]
    .sort((a, b) => {
      if (b.bookingCount !== a.bookingCount) return b.bookingCount - a.bookingCount
      return b.usageIndex - a.usageIndex
    })
    .slice(0, 5)

  const idleRooms = [...rooms]
    .filter(room => room.bookingCount === 0 && room.termCount === 0)
    .sort((a, b) => {
      if ((b.capacity || 0) !== (a.capacity || 0)) return (b.capacity || 0) - (a.capacity || 0)
      return a.name.localeCompare(b.name, 'th')
    })
    .slice(0, 6)

  const watchRooms = [...rooms]
    .filter(room => room.riskIndex >= 35 || room.demandAlerts.length > 0 || room.pendingCount > 0)
    .sort((a, b) => b.riskIndex - a.riskIndex)
    .slice(0, 6)

  const termRooms = [...rooms]
    .filter(room => room.termCount > 0 || room.termTodayCount > 0)
    .sort((a, b) => {
      if (b.termTodayCount !== a.termTodayCount) return b.termTodayCount - a.termTodayCount
      return b.termPressureIndex - a.termPressureIndex
    })
    .slice(0, 6)

  const biggestEmpty = [...idleRooms].sort((a, b) => (b.capacity || 0) - (a.capacity || 0))[0] || null

  return {
    summary: {
      totalRooms: rooms.length,
      busyRooms: busyRooms.length,
      idleRooms: idleRooms.length,
      watchRooms: watchRooms.length,
      termRooms: termRooms.length,
      maintenanceSlots: slots.length,
      demandAlerts: alerts.length,
      biggestEmpty,
    },
    rankedRooms,
    busyRooms,
    idleRooms,
    watchRooms,
    termRooms,
    slots,
  }
}

// ============================================================
// MAINTENANCE SCHEDULER PANEL
// ============================================================
function MaintenancePanel({ dashboard, bookings, termBookings, adminRooms }) {
  const [slots, setSlots]       = useState([])
  const [report, setReport]     = useState(null)
  const [loading, setLoading]   = useState(false)
  const [blocking, setBlocking] = useState(null)
  const [ranAt, setRanAt]       = useState(null)

  const runMaintenanceAI = async () => {
    setLoading(true)
    try {
      const [slotResult] = await Promise.allSettled([
        api.get('maintenance/slots/', { params: { min_hours: 3, max_demand: 0.10, days: 21 } }),
      ])
      const nextSlots = slotResult.status === 'fulfilled'
        ? (slotResult.value.data.slots || [])
        : []
      setSlots(nextSlots)
      setReport(buildMaintenanceInsights({
        adminRooms,
        bookings,
        termBookings,
        dashboard,
        slots: nextSlots,
      }))
      setRanAt(new Date())
      if (slotResult.status !== 'fulfilled') {
        alert('วิเคราะห์รีพอร์ตได้ แต่ดึงสล็อตซ่อมบำรุงจาก AI ไม่สำเร็จ')
      }
    } catch {
      setReport(buildMaintenanceInsights({
        adminRooms,
        bookings,
        termBookings,
        dashboard,
        slots: [],
      }))
      setRanAt(new Date())
      alert('สร้างรีพอร์ตไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }

  const blockSlot = async (slot) => {
    if (!confirm(`ล็อกห้อง ${slot.room_name}\n${slot.date} ${String(slot.start_hour).padStart(2,'0')}:00–${String(slot.end_hour).padStart(2,'0')}:00\nเพื่อซ่อมบำรุง?`)) return
    setBlocking(slot.label)
    try {
      const start = `${slot.date}T${String(slot.start_hour).padStart(2,'0')}:00:00`
      const end   = `${slot.date}T${String(slot.end_hour).padStart(2,'0')}:00:00`
      await api.post('maintenance-blocks/', {
        room: slot.room_id,
        start_time: start,
        end_time: end,
        reason: 'ซ่อมบำรุงเชิงป้องกัน (AI แนะนำ)',
        predicted_demand_avg: slot.avg_demand,
        note: `ช่วง demand ต่ำ ${(slot.avg_demand * 100).toFixed(1)}% — ${slot.hours?.length || 0} ชม.`,
      })
      alert('ล็อกห้องเรียบร้อย — ส่งช่างเข้าบำรุงได้')
      setSlots(prev => prev.filter(s => s.label !== slot.label))
    } catch (e) {
      alert(e.response?.data?.error || 'ล็อกห้องไม่สำเร็จ')
    } finally {
      setBlocking(null)
    }
  }

  return (
    <div className="au flex flex-col gap-4 max-h-[calc(100vh-11rem)] overflow-y-auto pr-1 pb-4">
      <div className="bg-gradient-to-br from-slate-900 via-blue-900 to-blue-700 text-white rounded-3xl p-6 shadow-xl shadow-blue-900/20 overflow-hidden relative">
        <div
          className="absolute inset-0 opacity-15 pointer-events-none"
          style={{
            background:
              'radial-gradient(circle at top right, #fde047 0%, transparent 28%), radial-gradient(circle at bottom left, #38bdf8 0%, transparent 35%)',
          }}
        />
        <div className="relative flex flex-col gap-4">
          <div>
            <h2 className="text-lg font-black flex items-center gap-2">
              <Wrench size={18} className="text-yellow-300" />
              AI Maintenance Copilot
            </h2>
            <p className="text-xs text-white/75 mt-1 leading-relaxed">
              กดครั้งเดียวเพื่อสรุปห้องที่ใช้งานหนัก, ห้องที่ว่างจริง, ห้องที่ควรตรวจสอบ, และสล็อตซ่อมบำรุงที่ล็อกได้ทันที
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={runMaintenanceAI} disabled={loading}
              className="inline-flex items-center gap-2 bg-white text-blue-800 hover:bg-blue-50 text-sm font-bold px-4 py-2.5 rounded-2xl shadow-lg shadow-black/10 disabled:opacity-60">
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
              สร้างรีพอร์ต AI
            </button>
            {report && ranAt && (
              <span className="inline-flex items-center gap-2 text-xs bg-white/10 border border-white/15 px-3 py-2 rounded-2xl text-white/80">
                อัปเดตล่าสุด {ranAt.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
        </div>
      </div>

      {report ? (
        <>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'ห้องทั้งหมด', value: report.summary.totalRooms, tone: 'text-slate-900', bg: 'from-slate-50 to-white' },
              { label: 'ห้องที่ใช้งานหนัก', value: report.summary.busyRooms, tone: 'text-blue-700', bg: 'from-blue-50 to-white' },
              { label: 'ห้องว่าง', value: report.summary.idleRooms, tone: 'text-emerald-700', bg: 'from-emerald-50 to-white' },
              { label: 'ห้องที่ต้องดู', value: report.summary.watchRooms, tone: 'text-rose-700', bg: 'from-rose-50 to-white' },
            ].map((card, i) => (
              <div key={i} className={`bg-gradient-to-br ${card.bg} border border-white rounded-2xl p-4 shadow-sm`}>
                <p className={`text-2xl font-black ${card.tone}`}>{card.value}</p>
                <p className="text-xs text-slate-500 mt-1">{card.label}</p>
              </div>
            ))}
          </div>

          <div className="bg-white border border-blue-100 rounded-3xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-black text-slate-900">ห้องที่ใช้งานเยอะที่สุด</h3>
                <p className="text-xs text-slate-500">อันดับจากจำนวนการใช้งานจริงและเทอมที่ผูกอยู่</p>
              </div>
              <span className="text-xs bg-blue-50 text-blue-700 border border-blue-100 px-3 py-1.5 rounded-full font-semibold">
                ดัชนีใช้งาน
              </span>
            </div>
            <div className="space-y-3">
              {report.busyRooms.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-4">ยังไม่มีข้อมูลห้องที่ใช้งานหนัก</p>
              ) : report.busyRooms.map((room, index) => (
                <div key={room.id || room.name} className="rounded-2xl border border-blue-100 p-4 bg-gradient-to-r from-blue-50 to-white">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-xl bg-blue-700 text-white flex items-center justify-center text-xs font-black flex-shrink-0">
                      {index + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <p className="font-bold text-slate-900 truncate">{room.name}</p>
                        <span className="text-xs font-bold text-blue-700 bg-blue-100 px-2.5 py-1 rounded-full">
                          {room.usageIndex}%
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        ใช้งาน {room.bookingCount} ครั้ง · ความจุ {room.capacity || '-'} คน
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-3">
            <div className="bg-white border border-emerald-100 rounded-3xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-black text-slate-900">ห้องว่างที่ควรเปิดใช้</h3>
                  <p className="text-xs text-slate-500">ห้องที่ยังแทบไม่ถูกใช้งานและพร้อมเอาไปโปรโมต</p>
                </div>
                <span className="text-xs bg-emerald-50 text-emerald-700 border border-emerald-100 px-3 py-1.5 rounded-full font-semibold">
                  ว่างจริง
                </span>
              </div>
              <div className="space-y-2">
                {report.idleRooms.length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-3">ไม่พบห้องว่างแบบเด่นๆ</p>
                ) : report.idleRooms.map(room => (
                  <div key={room.id || room.name} className="rounded-2xl border border-emerald-100 bg-emerald-50/50 px-4 py-3">
                    <p className="text-sm font-bold text-slate-900">{room.name}</p>
                    <p className="text-xs text-slate-500 mt-1">
                      ความจุ {room.capacity || '-'} คน · เหมาะเปิดจองได้ทันที
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white border border-rose-100 rounded-3xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-black text-slate-900">ห้องที่ควรตรวจสอบ</h3>
                  <p className="text-xs text-slate-500">รวมสัญญาณ no-show, คิวรอ, เทอม, และ AI forecast</p>
                </div>
                <span className="text-xs bg-rose-50 text-rose-700 border border-rose-100 px-3 py-1.5 rounded-full font-semibold">
                  เฝ้าระวัง
                </span>
              </div>
              <div className="space-y-2">
                {report.watchRooms.length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-3">ยังไม่พบห้องที่ต้องดูเป็นพิเศษ</p>
                ) : report.watchRooms.map(room => (
                  <div key={room.id || room.name} className="rounded-2xl border border-rose-100 bg-rose-50/50 px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-slate-900 truncate">{room.name}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          {room.reasons.length > 0 ? room.reasons.join(' · ') : 'ควรตรวจสอบสถานะการใช้งาน'}
                        </p>
                      </div>
                      <span className="text-xs font-black text-rose-700 bg-rose-100 px-2.5 py-1 rounded-full flex-shrink-0">
                        {room.riskIndex}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-white border border-violet-100 rounded-3xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-black text-slate-900">ตารางเทอมที่ต้องจับตา</h3>
                <p className="text-xs text-slate-500">ห้องที่มีตารางสอนวันนี้หรือแน่นจากเทอม</p>
              </div>
              <span className="text-xs bg-violet-50 text-violet-700 border border-violet-100 px-3 py-1.5 rounded-full font-semibold">
                เทอม
              </span>
            </div>
            <div className="space-y-2">
              {report.termRooms.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-3">ไม่มีห้องเทอมที่ต้องเตือนเป็นพิเศษ</p>
              ) : report.termRooms.map(room => (
                <div key={room.id || room.name} className="rounded-2xl border border-violet-100 bg-violet-50/50 px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-slate-900 truncate">{room.name}</p>
                      <p className="text-xs text-slate-500 mt-1">
                        วันนี้ {room.termTodayCount} คาบ · ทั้งหมด {room.termCount} คาบ
                      </p>
                    </div>
                    <span className="text-xs font-black text-violet-700 bg-violet-100 px-2.5 py-1 rounded-full flex-shrink-0">
                      {room.termPressureIndex}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white border border-emerald-100 rounded-3xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-black text-slate-900">สล็อตซ่อมบำรุงที่ AI แนะนำ</h3>
                <p className="text-xs text-slate-500">กดล็อกห้องได้ทันทีเมื่อเห็นช่วงเวลาที่เหมาะ</p>
              </div>
              <button onClick={runMaintenanceAI} disabled={loading}
                className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-2 rounded-xl disabled:opacity-50">
                {loading ? 'กำลังอัปเดต...' : 'รีเฟรชสล็อต'}
              </button>
            </div>
            {slots.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-6">
                {loading ? 'กำลังค้นหาช่วงเวลาที่เหมาะสม...' : 'ยังไม่มีสล็อตซ่อมบำรุงที่แนะนำ'}
              </p>
            ) : (
              <div className="space-y-2">
                {slots.map((slot, i) => (
                  <div key={i} className="flex items-center gap-3 border border-emerald-100 bg-emerald-50/60 rounded-2xl px-4 py-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-slate-800 truncate">{slot.room_name}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {slot.date} · {String(slot.start_hour).padStart(2, '0')}:00–{String(slot.end_hour).padStart(2, '0')}:00
                      </p>
                      <p className="text-xs text-emerald-700 mt-1">
                        demand เฉลี่ย {(slot.avg_demand * 100).toFixed(1)}%
                      </p>
                    </div>
                    <button onClick={() => blockSlot(slot)} disabled={blocking === slot.label}
                      className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-2 rounded-xl disabled:opacity-50 flex-shrink-0">
                      {blocking === slot.label ? 'กำลังล็อก...' : 'ล็อกทันที'}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="bg-white border border-blue-100 rounded-3xl p-8 shadow-sm text-center">
          <div className="w-14 h-14 rounded-2xl bg-blue-50 text-blue-700 flex items-center justify-center mx-auto mb-3">
            <Sparkles size={20} />
          </div>
          <p className="text-sm font-bold text-slate-800">ยังไม่มีรีพอร์ต AI</p>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            กดปุ่ม “สร้างรีพอร์ต AI” เพื่อดึงภาพรวมทั้งหมดครั้งเดียว แล้วค่อยกดล็อกสล็อตที่เหมาะ
          </p>
        </div>
      )}
    </div>
  )
}

// ============================================================
// DESKTOP
// ============================================================
function DesktopAdmin({ dashboard, bookings, termBookings, adminRooms, weekStats, tab, setTab, selectedBooking,
  setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull, navigate }) {

  const pendingB   = bookings.filter(b => b.status === 'pending')
  const activeB    = bookings.filter(b => b.status === 'approved' && !isPast(b.end_time))
  const cancelledB = bookings.filter(b => b.status === 'cancelled')
  const currentB   = bookings.filter(b =>
    (b.status === 'pending') ||
    (b.status === 'approved' && !isPast(b.end_time))
  )

  const tabs = [
    {key:'active',   label:'การจองปัจจุบัน', count:currentB.length},
    {key:'rooms',    label:'สถานะห้อง',      count:adminRooms?.length ?? null},
    {key:'maintenance', label:'ซ่อมบำรุง AI', count:null},
    {key:'overview', label:'ภาพรวม',         count:null},
    {key:'all',      label:'ทั้งหมด',        count:bookings.length},
  ]

  return (
    <div className="w-full bg-[#F8FAFC] flex flex-col overflow-x-hidden overflow-y-auto min-h-0" style={{fontFamily:"'Inter','Prompt','Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="sticky top-0 z-30 bg-white/90 backdrop-blur-xl border-b border-white/70 shadow-[0_12px_40px_rgba(37,99,235,0.06)] flex-shrink-0">
        <div className="max-w-7xl mx-auto px-4 lg:px-5 h-14 flex items-center gap-3">
          <button onClick={() => navigate('/')} className="flex items-center gap-2 text-slate-600 hover:text-blue-700 text-sm font-medium">
            <ArrowLeft size={15} />หน้าหลัก
          </button>
          <div className="h-5 w-px bg-slate-200" />
          <span className="text-slate-900 font-bold text-sm">Admin Dashboard</span>
          <div className="ml-auto flex items-center gap-3">
            <div className="flex items-center gap-1.5 bg-blue-50 text-blue-700 border border-blue-100 text-xs font-bold rounded-full px-3 py-1.5">
              <Zap size={10} />AI Forecast Active
            </div>
            <ExportButton isMobile={false} />
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-blue-500 via-indigo-500 to-blue-500" />
        <div className="max-w-7xl mx-auto px-4 lg:px-5 flex gap-1.5 overflow-x-auto">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-3.5 py-2.5 text-sm font-semibold border-b-2 transition-colors whitespace-nowrap
                ${tab===t.key?'border-blue-600 text-blue-700':'border-transparent text-slate-500 hover:text-slate-800'}`}>
              {t.label}
              {t.count!==null && (
                <span className={`text-xs px-2 py-0.5 rounded-full font-bold
                  ${tab===t.key?'bg-blue-50 text-blue-700':'bg-slate-100 text-slate-500'}`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden">
        <div className="min-h-0 max-w-7xl mx-auto px-4 lg:px-5 py-3 flex flex-col gap-3">

        {tab === 'active' && (
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-3 au">
              {[
                {label:'จองวันนี้',        value:dashboard?.today_bookings??0, color:'text-blue-700'},
                {label:'รอยืนยัน (pending)',value:pendingB.length,              color:'text-yellow-600'},
                {label:'ยืนยันแล้ว',       value:activeB.length,               color:'text-emerald-600'},
                {label:'ยกเลิกแล้ว',       value:cancelledB.length,            color:'text-red-500'},
            ].map((s,i) => (
                <div key={i} className="bg-white border border-blue-100 rounded-2xl p-4 shadow-sm">
                  <p className={`text-2xl font-extrabold ${s.color}`}>{s.value}</p>
                  <p className="text-sm text-slate-500 mt-1">{s.label}</p>
                </div>
              ))}
              {dashboard?.demand_alerts?.length > 0 && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-2xl p-3.5">
                  <p className="text-xs font-bold text-yellow-800 flex items-center gap-1.5 mb-3">
                    <AlertTriangle size={12} />AI คาดว่าช่วงนี้จะแน่น
                  </p>
                  {dashboard.demand_alerts.slice(0,3).map((a,i) => (
                    <div key={i} className="flex justify-between text-xs py-1.5 border-b border-yellow-100 last:border-0">
                      <span className="font-medium text-yellow-900">{a.room__name}</span>
                      <span className="text-yellow-700">{a.hour}:00 น.</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="col-span-2 space-y-3 au1">
              {currentB.length === 0
                ? <div className="bg-white border border-blue-100 rounded-2xl py-12 text-center shadow-sm">
                    <Calendar size={40} className="text-blue-200 mx-auto mb-3" />
                    <p className="text-slate-400 text-sm">ไม่มีการจองที่กำลังดำเนินอยู่</p>
                  </div>
                : currentB.map(b => {
                    const eff = getEffectiveS(b)
                    return (
                      <div key={b.id}
                        className="bg-white border border-blue-100 rounded-2xl px-4 py-3.5 flex items-center gap-4 cursor-pointer hover:shadow-md hover:-translate-y-0.5 transition-all"
                        style={{borderLeftWidth:4, borderLeftColor: eff.dot}}
                        onClick={() => setSelectedBooking(b)}>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2.5 mb-1 flex-wrap">
                            <p className="font-bold text-slate-900 truncate">{b.title}</p>
                            <span className={`text-xs px-2.5 py-0.5 rounded-full font-semibold flex-shrink-0 ${eff.bg} ${eff.text}`}>
                              {eff.label}
                            </span>
                            {b.checked_in && <span className="text-xs bg-blue-50 text-blue-700 px-2.5 py-0.5 rounded-full font-semibold flex-shrink-0">✓ Check-in</span>}
                          </div>
                          <p className="text-sm text-blue-600 font-medium mb-1 truncate">{b.room_name||`ห้อง #${b.room}`}</p>
                          <div className="flex gap-3 text-xs text-slate-400 flex-wrap">
                            <span>📅 {fmtDate(b.start_time)}</span>
                            <span>⏰ {fmtTime(b.start_time)}–{fmtTime(b.end_time)}</span>
                            <span>👥 {b.attendees} คน</span>
                          </div>
                        </div>
                        <button onClick={e=>{e.stopPropagation();handleCancel(b.id)}}
                          className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-600 border border-red-100 hover:bg-red-50 px-3 py-1.5 rounded-xl flex-shrink-0">
                          <X size={11} />ยกเลิก
                        </button>
                      </div>
                    )
                  })
              }
            </div>
          </div>
        )}

        {tab === 'rooms' && (
          <div className="au flex flex-col min-h-0">
            <div className="flex items-center gap-2 mb-4">
              <LayoutGrid size={16} className="text-blue-600" />
              <h2 className="text-base font-bold text-slate-800">สถานะห้องแบบ Real-time</h2>
              <span className="text-xs text-slate-400 ml-1">— ห้องทั้งหมด {adminRooms?.length ?? 0} ห้อง (ข้อมูลจริงจาก DB)</span>
            </div>
            <div className="min-h-0 max-h-[calc(100dvh-15rem)] overflow-y-auto overflow-x-hidden pr-1">
              <RoomStatusGrid bookings={bookings} termBookings={termBookings} adminRooms={adminRooms} fmtTime={fmtTime} isMobile={false} />
            </div>
          </div>
        )}

        {tab === 'maintenance' && (
          <MaintenancePanel
            dashboard={dashboard}
            bookings={bookings}
            termBookings={termBookings}
            adminRooms={adminRooms}
          />
        )}

        {tab === 'overview' && dashboard && (
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-3 au">
              {[
                {label:'จองวันนี้',    value:dashboard.today_bookings??0,        icon:'📅',color:'text-blue-700'},
                {label:'ห้องทั้งหมด', value:adminRooms?.length ?? dashboard.total_rooms ?? 0, icon:'🏢',color:'text-slate-700'},
                {label:'อัตราการใช้', value:`${dashboard.utilization_rate??0}%`, icon:'📊',color:'text-emerald-600'},
                {label:'ยืนยันแล้ว',  value:activeB.length,                      icon:'✅',color:'text-blue-600'},
              ].map((s,i) => (
                <div key={i} className="bg-white border border-blue-100 rounded-2xl p-4 shadow-sm flex items-center gap-3">
                  <span className="text-xl">{s.icon}</span>
                  <div>
                    <p className={`text-xl font-extrabold ${s.color}`}>{s.value}</p>
                    <p className="text-xs text-slate-500">{s.label}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="col-span-2 space-y-3 au1">
              <div className="bg-white border border-blue-100 rounded-2xl p-4 shadow-sm">
                <p className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
                  <BarChart2 size={14} className="text-blue-600" />การจองรายวัน 7 วันล่าสุด
                </p>
                <BarChartBlock weekStats={weekStats} />
                <div className="mt-3 pt-3 border-t border-blue-50 flex justify-between text-xs text-slate-400">
                  <span>รวม: {weekStats.reduce((s,d)=>s+d.count,0)} การจอง</span>
                  <span>เฉลี่ย: {(weekStats.reduce((s,d)=>s+d.count,0)/7).toFixed(1)}/วัน</span>
                </div>
              </div>
              {dashboard.popular_rooms?.length > 0 && (
                <div className="bg-white border border-blue-100 rounded-2xl p-4 shadow-sm">
                  <p className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <TrendingUp size={14} className="text-blue-600" />ห้องที่ใช้บ่อย
                  </p>
                  <div className="space-y-3">
                    {dashboard.popular_rooms.map((room,i) => {
                      const pct  = Math.round((room.count/(dashboard.popular_rooms[0]?.count||1))*100)
                      const cols = ['bg-blue-500','bg-blue-400','bg-blue-300','bg-blue-200','bg-blue-100']
                      return (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-xs font-black text-slate-300 w-4">{i+1}</span>
                          <div className="flex-1">
                            <div className="flex justify-between mb-1">
                              <span className="text-sm font-semibold text-slate-800">{room.room__name}</span>
                              <span className="text-xs text-slate-400">{room.count} ครั้ง</span>
                            </div>
                            <div className="h-2 bg-blue-50 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${cols[i]}`} style={{width:`${pct}%`}} />
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 'all' && (
          <div className="space-y-2 au">
            {bookings.map(b => {
              const s = getEffectiveS(b)
              return (
                <div key={b.id} onClick={() => setSelectedBooking(b)}
                  className={`bg-white border border-blue-100 rounded-xl px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-blue-50/40 transition-colors
                    ${isPast(b.end_time) && b.status === 'approved' ? 'opacity-60' : ''}`}>
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{background:s.dot}} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{b.title}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{b.room_name||`ห้อง #${b.room}`} · {fmtDate(b.start_time)} · {fmtTime(b.start_time)}</p>
                  </div>
                  <span className={`text-xs px-3 py-1 rounded-full font-semibold flex-shrink-0 ${s.bg} ${s.text}`}>{s.label}</span>
                </div>
              )
            })}
          </div>
        )}
        </div>
      </div>
      <BookingDetailModal booking={selectedBooking} onClose={()=>setSelectedBooking(null)}
        onCancel={handleCancel} fmtTime={fmtTime} fmtDateFull={fmtDateFull} />
    </div>
  )
}

// ============================================================
// MOBILE
// ============================================================
function MobileAdmin({ dashboard, bookings, termBookings, adminRooms, weekStats, tab, setTab, selectedBooking,
  setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull, navigate }) {

  const pendingB   = bookings.filter(b => b.status === 'pending')
  const activeB    = bookings.filter(b => b.status === 'approved' && !isPast(b.end_time))
  const cancelledB = bookings.filter(b => b.status === 'cancelled')
  const currentB   = bookings.filter(b =>
    (b.status === 'pending') ||
    (b.status === 'approved' && !isPast(b.end_time))
  )

  const tabs = [
    {key:'active',   label:'จอง',     count:currentB.length},
    {key:'rooms',    label:'ห้อง',    count:adminRooms?.length ?? null},
    {key:'maintenance', label:'ซ่อม', count:null},
    {key:'overview', label:'ภาพรวม',  count:null},
    {key:'all',      label:'ทั้งหมด', count:bookings.length},
  ]

  return (
    <div className="w-full bg-[#F8FAFC] flex flex-col overflow-x-hidden overflow-y-auto min-h-0" style={{fontFamily:"'Inter','Prompt','Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="sticky top-0 z-40 bg-white/90 backdrop-blur-xl border-b border-white/70 shadow-[0_12px_40px_rgba(37,99,235,0.06)] flex-shrink-0">
        <div className="max-w-lg mx-auto px-4 h-12 flex items-center gap-3">
          <button onClick={() => navigate('/')} className="text-slate-600 hover:text-blue-700 flex items-center"><ArrowLeft size={14} /></button>
          <span className="text-slate-900 font-bold text-sm flex-1">Admin Dashboard</span>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 bg-blue-50 text-blue-700 border border-blue-100 text-xs font-bold rounded-full px-2 py-0.5"><Zap size={9} />AI</div>
            <ExportButton isMobile={true} />
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-blue-500 via-indigo-500 to-blue-500" />
        <div className="max-w-lg mx-auto px-2 flex border-t border-slate-100 overflow-x-auto bg-white/80">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex-shrink-0 flex items-center justify-center gap-1 px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap
                ${tab===t.key?'border-blue-600 text-blue-700':'border-transparent text-slate-500 hover:text-slate-800'}`}>
              {t.label}
              {t.count!==null && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold
                  ${tab===t.key?'bg-blue-50 text-blue-700':'bg-slate-100 text-slate-500'}`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden">
        <div className="min-h-0 max-w-lg mx-auto px-4 py-3 space-y-3">
        {tab === 'active' && (
          <>
            <div className="grid grid-cols-2 gap-2 au">
              {[
                {label:'วันนี้',     value:dashboard?.today_bookings??0, color:'text-blue-700'},
                {label:'รอยืนยัน',  value:pendingB.length,              color:'text-yellow-600'},
                {label:'ยืนยันแล้ว',value:activeB.length,               color:'text-emerald-600'},
                {label:'ยกเลิก',    value:cancelledB.length,            color:'text-red-500'},
              ].map((s,i) => (
                <div key={i} className="bg-white border border-blue-100 rounded-2xl p-3 text-center shadow-sm">
                  <p className={`text-2xl font-extrabold ${s.color}`}>{s.value}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>
            {currentB.length === 0
              ? <div className="bg-white border border-blue-100 rounded-2xl py-12 text-center au1">
                  <Calendar size={32} className="text-blue-200 mx-auto mb-3" />
                  <p className="text-slate-400 text-sm">ไม่มีการจองที่กำลังดำเนินอยู่</p>
                </div>
              : currentB.map(b => {
                  const eff = getEffectiveS(b)
                  return (
                    <div key={b.id}
                      className="bg-white border border-blue-100 rounded-2xl px-4 py-4 flex items-center gap-3 cursor-pointer hover:shadow-md transition-all au2"
                      style={{borderLeftWidth:4, borderLeftColor: eff.dot}}
                      onClick={() => setSelectedBooking(b)}>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <p className="font-bold text-slate-900 text-sm truncate">{b.title}</p>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-bold flex-shrink-0 ${eff.bg} ${eff.text}`}>{eff.label}</span>
                          {b.checked_in && <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-bold flex-shrink-0">✓ Check-in</span>}
                        </div>
                        <p className="text-xs text-blue-600 mb-1">{b.room_name}</p>
                        <div className="flex gap-3 text-xs text-slate-400">
                          <span>📅 {fmtDate(b.start_time)}</span>
                          <span>⏰ {fmtTime(b.start_time)}</span>
                        </div>
                      </div>
                      <button onClick={e=>{e.stopPropagation();handleCancel(b.id)}}
                        className="text-xs text-red-400 border border-red-100 px-2.5 py-1.5 rounded-xl flex items-center gap-1 flex-shrink-0">
                        <X size={11} />ยกเลิก
                      </button>
                    </div>
                  )
                })
            }
          </>
        )}

        {tab === 'rooms' && (
          <div className="au flex flex-col min-h-0">
            <div className="flex items-center gap-2 mb-4">
              <LayoutGrid size={14} className="text-blue-600" />
              <h2 className="text-sm font-bold text-slate-800">สถานะห้อง {adminRooms?.length ?? 0} ห้อง</h2>
            </div>
            <div className="min-h-0 max-h-[calc(100dvh-12rem)] overflow-y-auto overflow-x-hidden pr-1">
              <RoomStatusGrid bookings={bookings} termBookings={termBookings} adminRooms={adminRooms} fmtTime={fmtTime} isMobile={true} />
            </div>
          </div>
        )}

        {tab === 'maintenance' && (
          <MaintenancePanel
            dashboard={dashboard}
            bookings={bookings}
            termBookings={termBookings}
            adminRooms={adminRooms}
          />
        )}

        {tab === 'overview' && dashboard && (
          <>
            <div className="grid grid-cols-2 gap-2 au">
              {[
                {label:'จองวันนี้',    value:dashboard.today_bookings??0,        icon:'📅',color:'text-blue-700'},
                {label:'ห้องทั้งหมด', value:adminRooms?.length ?? dashboard.total_rooms ?? 0, icon:'🏢',color:'text-slate-700'},
                {label:'อัตราการใช้', value:`${dashboard.utilization_rate??0}%`, icon:'📊',color:'text-emerald-600'},
                {label:'ยืนยันแล้ว',  value:activeB.length,                      icon:'✅',color:'text-blue-600'},
              ].map((s,i) => (
                <div key={i} className="bg-white border border-blue-100 rounded-2xl p-4 shadow-sm">
                  <span className="text-xl">{s.icon}</span>
                  <p className={`text-2xl font-extrabold mt-1 ${s.color}`}>{s.value}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>
            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au2">
              <p className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
                <BarChart2 size={13} className="text-blue-600" />การจองรายวัน 7 วัน
              </p>
              <BarChartBlock weekStats={weekStats} />
            </div>
          </>
        )}

        {tab === 'all' && (
          <div className="space-y-2 au">
            {bookings.map(b => {
              const s = getEffectiveS(b)
              return (
                <div key={b.id} onClick={() => setSelectedBooking(b)}
                  className={`bg-white border border-blue-100 rounded-xl px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-blue-50/40
                    ${isPast(b.end_time) && b.status === 'approved' ? 'opacity-60' : ''}`}>
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{background:s.dot}} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{b.title}</p>
                    <p className="text-xs text-slate-400">{b.room_name||`ห้อง #${b.room}`} · {fmtDate(b.start_time)}</p>
                  </div>
                  <span className={`text-xs px-2.5 py-1 rounded-full font-semibold flex-shrink-0 ${s.bg} ${s.text}`}>{s.label}</span>
                </div>
              )
            })}
          </div>
        )}
        </div>
      </div>
      <BookingDetailModal booking={selectedBooking} onClose={()=>setSelectedBooking(null)}
        onCancel={handleCancel} fmtTime={fmtTime} fmtDateFull={fmtDateFull} />
    </div>
  )
}

// ============================================================
// ROOT
// ============================================================
export default function AdminPage() {
  const navigate = useNavigate()
  const isMobile = useDevice()
  const [dashboard,       setDashboard]      = useState(null)
  const [adminRooms,      setAdminRooms]      = useState([])
  const [bookings,        setBookings]        = useState([])
  const [termBookings,    setTermBookings]    = useState([])
  const [tab,             setTab]             = useState('active')
  const [loading,         setLoading]         = useState(true)
  const [weekStats,       setWeekStats]       = useState([])
  const [selectedBooking, setSelectedBooking] = useState(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [dashRes, bookingRes, termRes, roomsRes] = await Promise.all([
          api.get('dashboard/'),
          api.get('bookings/'),
          api.get('term-bookings/'),
          api.get('rooms/admin-status/').catch(() => ({ data: [] })),
        ])
        setDashboard(dashRes.data)
        setAdminRooms(Array.isArray(roomsRes.data) ? roomsRes.data : [])
        const all = bookingRes.data.results || []
        setBookings(all)

        // term bookings — รองรับ paginated หรือ array โดยตรง
        const termAll = termRes.data.results ?? termRes.data ?? []
        setTermBookings(Array.isArray(termAll) ? termAll : [])

        const days = ['อา','จ','อ','พ','พฤ','ศ','ส']
        const stats = []
        for (let i=6;i>=0;i--) {
          const d = new Date(); d.setDate(d.getDate()-i)
          const ds = d.toISOString().split('T')[0]
          stats.push({
            day: days[d.getDay()], date: ds,
            count: all.filter(b =>
              new Date(b.start_time).toISOString().split('T')[0] === ds &&
              (b.status === 'approved' || b.status === 'pending')
            ).length
          })
        }
        setWeekStats(stats)
      } catch { navigate('/login') }
      finally  { setLoading(false) }
    }
    load()
  }, [])

  const handleCancel = async (id) => {
    if (!confirm('ยืนยันการยกเลิกการจองนี้?')) return
    try {
      await api.post(`bookings/${id}/cancel/`)
      setBookings(prev => prev.map(b => b.id===id ? {...b,status:'cancelled'} : b))
      if (selectedBooking?.id===id) setSelectedBooking(prev => ({...prev,status:'cancelled'}))
    } catch { alert('เกิดข้อผิดพลาด') }
  }

  const fmtDate     = dt => new Date(dt).toLocaleDateString('th-TH',{day:'numeric',month:'short'})
  const fmtTime     = dt => new Date(dt).toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit'})
  const fmtDateFull = dt => new Date(dt).toLocaleDateString('th-TH',{weekday:'long',day:'numeric',month:'long'})

  if (loading) return (
    <div className="w-full bg-[#F8FAFC] flex flex-col items-center justify-center gap-3 overflow-x-hidden overflow-y-auto min-h-0" style={{fontFamily:"'Inter','Prompt','Sarabun',sans-serif"}}>
      <style>{ANIM}</style>
      <div style={{width:36,height:36,border:'3px solid #dbeafe',borderTopColor:'#2563eb',borderRadius:'50%',animation:'rot .7s linear infinite'}} />
      <p className="text-sm text-slate-500">กำลังโหลด...</p>
    </div>
  )

  const props = {
    dashboard, adminRooms, bookings, termBookings, weekStats, tab, setTab,
    selectedBooking, setSelectedBooking,
    handleCancel, fmtDate, fmtTime, fmtDateFull, navigate
  }
  return isMobile ? <MobileAdmin {...props} /> : <DesktopAdmin {...props} />
}
