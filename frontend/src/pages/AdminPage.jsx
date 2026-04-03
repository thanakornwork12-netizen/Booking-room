import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Clock, BarChart2, TrendingUp, Calendar, X,
  Building2, AlertTriangle, Zap, UserX,
  Download, ChevronDown, FileSpreadsheet, Check, LayoutGrid
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

// ── ข้อมูลห้องทั้งหมด (static fallback + enrichment) ──────────
const ALL_ROOMS_DATA = [
  // LIB
  { code:'LIB-01', capacity:18, util:0.611, peak:0.278, building:'ห้องสมุด' },
  { code:'LIB-02', capacity:17, util:0.588, peak:0.353, building:'ห้องสมุด' },
  { code:'LIB-03', capacity:16, util:0.625, peak:0.312, building:'ห้องสมุด' },
  { code:'LIB-04', capacity:14, util:0.643, peak:0.357, building:'ห้องสมุด' },
  { code:'LIB-05', capacity:21, util:0.667, peak:0.286, building:'ห้องสมุด' },
  { code:'LIB-06', capacity:13, util:0.615, peak:0.308, building:'ห้องสมุด' },
  { code:'LIB-07', capacity:19.6,util:0.612,peak:0.306, building:'ห้องสมุด' },
  { code:'LIB-08', capacity:15, util:0.600, peak:0.333, building:'ห้องสมุด' },
  { code:'LIB-09', capacity:16, util:0.625, peak:0.375, building:'ห้องสมุด' },
  { code:'LIB-10', capacity:20, util:0.600, peak:0.350, building:'ห้องสมุด' },
  { code:'LIB-11', capacity:22, util:0.591, peak:0.318, building:'ห้องสมุด' },
  { code:'LIB-12', capacity:12, util:0.667, peak:0.333, building:'ห้องสมุด' },
  // SC
  { code:'SC-01',  capacity:17, util:0.588, peak:0.353, building:'วิทยาศาสตร์' },
  { code:'SC-02',  capacity:17, util:0.588, peak:0.294, building:'วิทยาศาสตร์' },
  { code:'SC-03',  capacity:12, util:0.583, peak:0.333, building:'วิทยาศาสตร์' },
  { code:'SC-04',  capacity:19, util:0.632, peak:0.316, building:'วิทยาศาสตร์' },
  { code:'SC-05',  capacity:13, util:0.615, peak:0.385, building:'วิทยาศาสตร์' },
  { code:'SC-06',  capacity:15, util:0.667, peak:0.333, building:'วิทยาศาสตร์' },
  { code:'SC-07',  capacity:16, util:0.625, peak:0.375, building:'วิทยาศาสตร์' },
  { code:'SC-08',  capacity:16, util:0.625, peak:0.375, building:'วิทยาศาสตร์' },
  { code:'SC-09',  capacity:15, util:0.533, peak:0.333, building:'วิทยาศาสตร์' },
  { code:'SC-10',  capacity:19, util:0.632, peak:0.316, building:'วิทยาศาสตร์' },
  // EN
  { code:'EN-01',  capacity:12,   util:0.583, peak:0.333, building:'วิศวกรรม' },
  { code:'EN-02',  capacity:17,   util:0.632, peak:0.353, building:'วิศวกรรม' },
  { code:'EN-03',  capacity:14.55,util:0.619, peak:0.344, building:'วิศวกรรม' },
  { code:'EN-04',  capacity:17,   util:0.588, peak:0.294, building:'วิศวกรรม' },
  { code:'EN-05',  capacity:17,   util:0.647, peak:0.353, building:'วิศวกรรม' },
  { code:'EN-06',  capacity:14,   util:0.571, peak:0.357, building:'วิศวกรรม' },
  { code:'EN-07',  capacity:16,   util:0.625, peak:0.312, building:'วิศวกรรม' },
  { code:'EN-08',  capacity:16,   util:0.625, peak:0.312, building:'วิศวกรรม' },
  { code:'EN-09',  capacity:15,   util:0.600, peak:0.333, building:'วิศวกรรม' },
  { code:'EN-10',  capacity:14,   util:0.643, peak:0.357, building:'วิศวกรรม' },
  // MAIN
  { code:'MAIN-01',capacity:16.5,util:0.606, peak:0.364, building:'อาคารหลัก' },
  { code:'MAIN-02',capacity:11,  util:0.636, peak:0.364, building:'อาคารหลัก' },
  { code:'MAIN-03',capacity:10,  util:0.600, peak:0.300, building:'อาคารหลัก' },
  { code:'MAIN-04',capacity:15,  util:0.667, peak:0.333, building:'อาคารหลัก' },
  { code:'MAIN-05',capacity:16,  util:0.625, peak:0.375, building:'อาคารหลัก' },
  { code:'MAIN-06',capacity:22,  util:0.591, peak:0.318, building:'อาคารหลัก' },
  { code:'MAIN-07',capacity:16,  util:0.625, peak:0.312, building:'อาคารหลัก' },
  { code:'MAIN-08',capacity:13,  util:0.615, peak:0.308, building:'อาคารหลัก' },
]

// ── helper: ค้นหาข้อมูล static ของห้อง ──
const getRoomData = (name) =>
  ALL_ROOMS_DATA.find(r => name?.includes(r.code)) || null

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
// สถานะ:
//   pending   = รอยืนยัน (กำลังจอง - สีเหลือง)
//   approved  + isNow   = กำลังใช้งาน (สีเขียว)
//   approved  + isSoon  = จะเริ่มเร็วๆ นี้ (สีส้มอำพัน)
//   approved  + future  = ยืนยันแล้ว (สีน้ำเงิน)
//   approved  + isPast  = เสร็จสิ้น
//   cancelled = ยกเลิกแล้ว
//   no_show   = No-Show
const STATUS_CFG = {
  pending:   { label:'กำลังจอง',    bg:'bg-yellow-50',   text:'text-yellow-700', dot:'#f59e0b' },
  approved:  { label:'ยืนยันแล้ว',  bg:'bg-blue-50',     text:'text-blue-700',   dot:'#3b82f6' },
  active:    { label:'กำลังใช้งาน', bg:'bg-emerald-50',  text:'text-emerald-700',dot:'#10b981' },
  soon:      { label:'จะเริ่มเร็วๆ',bg:'bg-amber-50',    text:'text-amber-700',  dot:'#f59e0b' },
  cancelled: { label:'ยกเลิกแล้ว',  bg:'bg-red-50',      text:'text-red-600',    dot:'#f87171' },
  completed: { label:'เสร็จสิ้น',   bg:'bg-slate-100',   text:'text-slate-500',  dot:'#94a3b8' },
  no_show:   { label:'No-Show',     bg:'bg-orange-50',   text:'text-orange-700', dot:'#f97316' },
}
const getS = s => STATUS_CFG[s] || { label:s, bg:'bg-slate-100', text:'text-slate-500', dot:'#94a3b8' }

// ── ดึง status ที่ถูกต้องตาม logic ──────────────────────────
const getEffectiveS = (b) => {
  if (b.status === 'approved') {
    if (isPast(b.end_time))         return STATUS_CFG.completed
    if (isNow(b.start_time, b.end_time)) return STATUS_CFG.active
    if (isSoon(b.start_time))       return STATUS_CFG.soon
    return STATUS_CFG.approved
  }
  if (b.status === 'pending') return STATUS_CFG.pending
  return getS(b.status)
}

// ── คำนวณ room status หลัก + รายการ bookings ทั้งหมด ────────
const getRoomStatus = (roomName, bookings) => {
  const now = new Date()
  const roomBookings = bookings.filter(b => {
    const bn = b.room_name || `ห้อง #${b.room}`
    // เอาเฉพาะที่ยังไม่หมดเวลา (end_time > ตอนนี้) และสถานะ active/pending
    return bn === roomName
      && (b.status === 'approved' || b.status === 'pending')
      && new Date(b.end_time) > now
  })
  const sorted = [...roomBookings].sort((a,b) => new Date(a.start_time)-new Date(b.start_time))

  const active   = sorted.find(b => b.status === 'approved' && isNow(b.start_time, b.end_time))
  const upcoming = sorted.find(b => b.status === 'approved' && isSoon(b.start_time))
  const pending  = sorted.find(b => b.status === 'pending')
  const booked   = sorted.find(b => b.status === 'approved' && !isPast(b.end_time) && !isNow(b.start_time, b.end_time) && !isSoon(b.start_time))

  let state, label, color, bg, border
  if (active)        { state='active';  label='กำลังใช้งาน';  color='#10b981'; bg='#d1fae5'; border='#6ee7b7' }
  else if (upcoming) { state='soon';    label='จะเริ่มเร็วๆ'; color='#f59e0b'; bg='#fef3c7'; border='#fcd34d' }
  else if (pending)  { state='pending'; label='กำลังจอง';    color='#eab308'; bg='#fefce8'; border='#fde047' }
  else if (booked)   { state='booked';  label='ยืนยันแล้ว';  color='#3b82f6'; bg='#eff6ff'; border='#93c5fd' }
  else               { state='free';    label='ว่าง';        color='#94a3b8'; bg='#f1f5f9'; border='#cbd5e1' }

  return { state, label, color, bg, border, allBookings: sorted }
}

// ── รวม bookings + ALL_ROOMS_DATA เป็น rooms ─────────────────
// ถ้า booking มีห้องใหม่ที่ไม่ใน ALL_ROOMS_DATA ก็เพิ่มเข้าไปด้วย
const extractRooms = (bookings) => {
  const map = {}

  // เพิ่มจาก static list ก่อน
  ALL_ROOMS_DATA.forEach(r => {
    map[r.code] = { name:r.code, roomId:null, ...r }
  })

  // เพิ่ม/อัปเดตจาก bookings (กรณีชื่อ match กับ code)
  bookings.forEach(b => {
    const bname = b.room_name || `ห้อง #${b.room}`
    if (!map[bname]) {
      // ห้องใหม่ที่ไม่อยู่ใน static list
      map[bname] = { name:bname, roomId:b.room, code:bname, building:'อื่นๆ', capacity:null, util:null, peak:null }
    } else {
      // อัปเดต roomId
      map[bname].roomId = b.room
    }
    // ถ้า room_name จาก booking ตรงกับ code ใน static
    const rd = getRoomData(bname)
    if (rd && map[rd.code]) map[rd.code].roomId = b.room
  })

  return Object.values(map).sort((a,b) => a.name.localeCompare(b.name, 'th'))
}

// ── Building groups ──────────────────────────────────────────
const BUILDING_ORDER = ['ห้องสมุด','วิทยาศาสตร์','วิศวกรรม','อาคารหลัก','อื่นๆ']

// ============================================================
// EXPORT BUTTON
// ============================================================
const SHEETS = [
  { key:'users',         label:'ผู้ใช้งาน',      icon:'👤' },
  { key:'buildings',     label:'อาคาร',           icon:'🏛️' },
  { key:'rooms',         label:'ห้อง',            icon:'🚪' },
  { key:'facilities',    label:'อุปกรณ์ในห้อง',  icon:'🖥️' },
  { key:'bookings',      label:'การจอง',          icon:'📅' },
  { key:'logs',          label:'ประวัติการจอง',   icon:'📋' },
  { key:'forecasts',     label:'ผลพยากรณ์ AI',   icon:'🤖' },
  { key:'notifications', label:'การแจ้งเตือน',   icon:'🔔' },
  { key:'stats',         label:'สถิติห้อง',       icon:'📊' },
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
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text()
        alert(`Error ${err.response.status}: ${text}`)
      } else {
        alert(`Error: ${err.message}`)
      }
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
// NO-SHOW CARD
// ============================================================
function NoShowCard({ bookings }) {
  const total  = bookings.filter(b => ['approved','completed','cancelled','no_show'].includes(b.status)).length
  const noShow = bookings.filter(b => b.status === 'no_show').length
  const rate   = total > 0 ? (noShow / total * 100).toFixed(1) : 0
  const isHigh = rate >= 20
  const isMed  = rate >= 10

  const userCount = {}
  bookings.filter(b => b.status === 'no_show').forEach(b => {
    const name = b.user_name || `User #${b.user}`
    userCount[name] = (userCount[name] || 0) + 1
  })
  const topUsers = Object.entries(userCount).sort((a,b) => b[1]-a[1]).slice(0,3)

  return (
    <div className={`border rounded-2xl p-5 shadow-sm ${isHigh?'bg-red-50 border-red-200':isMed?'bg-orange-50 border-orange-200':'bg-white border-blue-100'}`}>
      <div className="flex items-center gap-2 mb-3">
        <UserX size={16} className={isHigh?'text-red-500':isMed?'text-orange-500':'text-slate-400'} />
        <span className={`text-sm font-bold ${isHigh?'text-red-700':isMed?'text-orange-700':'text-slate-700'}`}>อัตรา No-Show</span>
        {isHigh && <span className="text-xs bg-red-100 text-red-700 border border-red-200 px-2 py-0.5 rounded-full font-bold ml-auto">⚠️ สูงมาก</span>}
        {isMed && !isHigh && <span className="text-xs bg-orange-100 text-orange-700 border border-orange-200 px-2 py-0.5 rounded-full font-bold ml-auto">ควรดูแล</span>}
      </div>
      <div className="flex items-end gap-3 mb-3">
        <span className={`text-4xl font-extrabold ${isHigh?'text-red-600':isMed?'text-orange-600':'text-slate-700'}`}>{rate}%</span>
        <span className="text-sm text-slate-500 mb-1.5">{noShow} / {total} การจอง</span>
      </div>
      <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden mb-4">
        <div className="h-full rounded-full transition-all"
          style={{width:`${Math.min(rate,100)}%`,background:isHigh?'#ef4444':isMed?'#f97316':'#10b981'}} />
      </div>
      {topUsers.length > 0 && (
        <>
          <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">No-Show บ่อยที่สุด</p>
          {topUsers.map(([name,cnt],i) => (
            <div key={i} className="flex justify-between text-xs py-1.5 border-b border-slate-100 last:border-0">
              <span className="text-slate-700 font-medium">{name}</span>
              <span className={`font-bold ${cnt>=3?'text-red-600':'text-orange-500'}`}>{cnt} ครั้ง {cnt>=3?'⚠️':''}</span>
            </div>
          ))}
        </>
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
// ROOM STATUS GRID — แสดงห้องทั้งหมด 38 ห้อง แยกตามอาคาร
// ============================================================
function RoomStatusGrid({ bookings, fmtTime, isMobile = false }) {
  const [tick, setTick] = useState(0)
  const [filterBuilding, setFilterBuilding] = useState('ทั้งหมด')
  const [selectedRoom, setSelectedRoom] = useState(null)

  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 30000)
    return () => clearInterval(t)
  }, [])

  const rooms = extractRooms(bookings)

  // กรองตาม building
  const buildings = ['ทั้งหมด', ...BUILDING_ORDER.filter(b => rooms.some(r => r.building === b))]
  const filtered = filterBuilding === 'ทั้งหมด'
    ? rooms
    : rooms.filter(r => r.building === filterBuilding)

  // แยกตาม building สำหรับ group display
  const grouped = BUILDING_ORDER
    .map(b => ({ building:b, rooms: filtered.filter(r => r.building === b) }))
    .filter(g => g.rooms.length > 0)

  // สรุปรวม
  const activeCount  = rooms.filter(r => getRoomStatus(r.name, bookings).state === 'active').length
  const soonCount    = rooms.filter(r => getRoomStatus(r.name, bookings).state === 'soon').length
  const pendingCount = rooms.filter(r => getRoomStatus(r.name, bookings).state === 'pending').length
  const freeCount    = rooms.filter(r => getRoomStatus(r.name, bookings).state === 'free').length

  const getNextBooking = (roomName) => {
    const now = new Date()
    return bookings
      .filter(b => (b.room_name === roomName || `ห้อง #${b.room}` === roomName)
        && (b.status === 'approved' || b.status === 'pending')
        && new Date(b.start_time) > now)
      .sort((a,b) => new Date(a.start_time) - new Date(b.start_time))[0]
  }

  const BUILDING_ICONS = {
    'ห้องสมุด':    '📚',
    'วิทยาศาสตร์': '🔬',
    'วิศวกรรม':   '⚙️',
    'อาคารหลัก':  '🏛️',
    'อื่นๆ':       '🚪',
  }

  return (
    <div>
      {/* Legend + Filter */}
      <div className={`flex flex-wrap gap-3 mb-4 items-center`}>
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-emerald-400" />
            <span className="text-xs text-slate-600 font-medium">กำลังใช้งาน <span className="font-extrabold text-emerald-600">{activeCount}</span></span>
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
            <div className="w-3 h-3 rounded-sm bg-slate-200" />
            <span className="text-xs text-slate-600 font-medium">ว่าง <span className="font-extrabold text-slate-500">{freeCount}</span></span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-1.5 text-xs text-slate-400">
          <Clock size={11} className="pulse" />
          <span>อัปเดตทุก 30 วิ</span>
        </div>
      </div>

      {/* Building Filter Tabs */}
      <div className="flex gap-1.5 mb-5 flex-wrap">
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

      {/* Grid แยก group */}
      {grouped.length === 0 ? (
        <div className="bg-white border border-blue-100 rounded-2xl py-16 text-center shadow-sm">
          <LayoutGrid size={36} className="text-blue-200 mx-auto mb-3" />
          <p className="text-slate-400 text-sm">ไม่พบข้อมูลห้อง</p>
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.map(({ building, rooms: brooms }) => (
            <div key={building}>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-base">{BUILDING_ICONS[building]||'🚪'}</span>
                <h3 className="text-sm font-bold text-slate-700">{building}</h3>
                <span className="text-xs text-slate-400">({brooms.length} ห้อง)</span>
                <div className="flex-1 h-px bg-slate-100 ml-2" />
              </div>
              <div className={`grid gap-2.5 ${
                isMobile
                  ? 'grid-cols-2'
                  : 'grid-cols-3 lg:grid-cols-4 xl:grid-cols-6'
              }`}>
                {brooms.map((room) => {
                  const rs = getRoomStatus(room.name, bookings)

                  return (
                    <div key={room.name}
                      className="relative cursor-pointer select-none"
                      onClick={() => setSelectedRoom(selectedRoom === room.name ? null : room.name)}>

                      <div
                        className="rounded-2xl border-2 p-3.5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
                        style={{
                          background: rs.bg,
                          borderColor: selectedRoom === room.name ? rs.color : rs.border,
                          boxShadow: selectedRoom === room.name ? `0 0 0 3px ${rs.color}30` : undefined,
                        }}>

                        {/* ไฟสถานะ + badge */}
                        <div className="flex items-start justify-between mb-2">
                          <div
                            className="w-2.5 h-2.5 rounded-full flex-shrink-0 mt-0.5"
                            style={{
                              background: rs.color,
                              boxShadow: (rs.state==='active' || rs.state==='pending') ? `0 0 0 4px ${rs.color}30` : undefined,
                              animation: (rs.state==='active' || rs.state==='pending') ? 'pulse 2s ease-in-out infinite' : undefined,
                            }}
                          />
                          <span
                            className="text-xs font-bold px-1.5 py-0.5 rounded-full leading-tight"
                            style={{ background: rs.color + '20', color: rs.color, fontSize:'10px' }}>
                            {rs.label}
                          </span>
                        </div>

                        {/* ชื่อห้อง */}
                        <p className="text-sm font-extrabold text-slate-800 leading-tight mb-1">{room.name}</p>

                        {/* รายการจองทั้งหมดของห้องนี้ */}
                        {rs.allBookings.length === 0 ? (
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
                                  <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{background: dotC}} />
                                  <span className={`text-xs ${timeC} tabular-nums`}>
                                    {fmtTime(bk.start_time)}–{fmtTime(bk.end_time)}
                                  </span>
                                  {bNow && <span className="text-xs text-emerald-600 font-bold">●</span>}
                                  {bPend && <span className="text-xs text-yellow-500">?</span>}
                                </div>
                              )
                            })}
                          </div>
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

      {/* สรุปท้าย */}
      <div className="mt-6 bg-white border border-blue-100 rounded-2xl p-4 shadow-sm">
        <div className={`flex ${isMobile ? 'flex-col gap-2' : 'items-center gap-6'}`}>
          <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">สรุปสถานะห้องทั้งหมด {rooms.length} ห้อง</p>
          <div className="flex gap-4 flex-wrap">
            <div className="text-center">
              <p className="text-2xl font-extrabold text-emerald-600">{activeCount}</p>
              <p className="text-xs text-slate-400">กำลังใช้งาน</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-extrabold text-yellow-500">{pendingCount}</p>
              <p className="text-xs text-slate-400">กำลังจอง</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-extrabold text-amber-500">{soonCount}</p>
              <p className="text-xs text-slate-400">จะเริ่มเร็วๆ</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-extrabold text-slate-400">{freeCount}</p>
              <p className="text-xs text-slate-400">ว่างอยู่</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-extrabold text-blue-700">{rooms.length}</p>
              <p className="text-xs text-slate-400">ทั้งหมด</p>
            </div>
          </div>
          {rooms.length > 0 && (
            <div className="ml-auto hidden md:block">
              <div className="h-3 rounded-full overflow-hidden bg-slate-100" style={{width:200}}>
                <div className="h-full flex">
                  <div style={{width:`${(activeCount/rooms.length)*100}%`, background:'#10b981'}} />
                  <div style={{width:`${(pendingCount/rooms.length)*100}%`, background:'#f59e0b'}} />
                  <div style={{width:`${(soonCount/rooms.length)*100}%`, background:'#fcd34d'}} />
                </div>
              </div>
              <p className="text-xs text-slate-400 mt-1 text-right">
                อัตราการใช้งาน {(((activeCount+pendingCount)/rooms.length)*100).toFixed(0)}%
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ============================================================
// DESKTOP
// ============================================================
function DesktopAdmin({ dashboard, bookings, weekStats, tab, setTab, selectedBooking,
  setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull, navigate }) {

  // pending = รอยืนยัน (กำลังจอง), approved = ยืนยันแล้ว (รวม active/soon/future)
  const pendingB   = bookings.filter(b => b.status === 'pending')
  const activeB    = bookings.filter(b => b.status === 'approved' && !isPast(b.end_time))
  const cancelledB = bookings.filter(b => b.status === 'cancelled')
  const noShowB    = bookings.filter(b => b.status === 'no_show')

  // Tab แสดง "กำลังจอง" = pending + approved ที่ยังไม่หมดเวลา
  const currentB   = bookings.filter(b =>
    (b.status === 'pending') ||
    (b.status === 'approved' && !isPast(b.end_time))
  )

  const tabs = [
    {key:'active',   label:'การจองปัจจุบัน', count:currentB.length},
    {key:'rooms',    label:'สถานะห้อง',      count:null},
    {key:'overview', label:'ภาพรวม',         count:null},
    {key:'noshow',   label:'No-Show',        count:noShowB.length},
    {key:'all',      label:'ทั้งหมด',        count:bookings.length},
  ]

  return (
    <div className="min-h-screen bg-slate-100" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="bg-blue-700 shadow-lg shadow-blue-900/20">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => navigate('/')} className="flex items-center gap-2 text-white/80 hover:text-white text-sm font-medium">
            <ArrowLeft size={15} />หน้าหลัก
          </button>
          <div className="h-5 w-px bg-white/20" />
          <span className="text-white font-bold text-sm">Admin Dashboard</span>
          <div className="ml-auto flex items-center gap-3">
            <div className="flex items-center gap-1.5 bg-yellow-300 text-yellow-900 text-xs font-bold rounded-full px-3 py-1.5">
              <Zap size={10} />AI Forecast Active
            </div>
            <ExportButton isMobile={false} />
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
        <div className="max-w-7xl mx-auto px-6 flex">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-colors
                ${tab===t.key?'border-yellow-400 text-white':'border-transparent text-white/60 hover:text-white'}`}>
              {t.label}
              {t.count!==null && (
                <span className={`text-xs px-2 py-0.5 rounded-full font-bold
                  ${t.key==='noshow'&&t.count>0?'bg-orange-400 text-white':tab===t.key?'bg-yellow-400 text-yellow-900':'bg-white/15 text-white/70'}`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">

        {tab === 'active' && (
          <div className="grid grid-cols-3 gap-6">
            <div className="space-y-4 au">
              {[
                {label:'จองวันนี้',        value:dashboard?.today_bookings??0, color:'text-blue-700'},
                {label:'รอยืนยัน (pending)',value:pendingB.length,              color:'text-yellow-600'},
                {label:'ยืนยันแล้ว',       value:activeB.length,               color:'text-emerald-600'},
                {label:'ยกเลิกแล้ว',       value:cancelledB.length,            color:'text-red-500'},
              ].map((s,i) => (
                <div key={i} className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm">
                  <p className={`text-3xl font-extrabold ${s.color}`}>{s.value}</p>
                  <p className="text-sm text-slate-500 mt-1">{s.label}</p>
                </div>
              ))}
              <NoShowCard bookings={bookings} />
              {dashboard?.demand_alerts?.length > 0 && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-2xl p-4">
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
                ? <div className="bg-white border border-blue-100 rounded-2xl py-16 text-center shadow-sm">
                    <Calendar size={40} className="text-blue-200 mx-auto mb-3" />
                    <p className="text-slate-400 text-sm">ไม่มีการจองที่กำลังดำเนินอยู่</p>
                  </div>
                : currentB.map(b => {
                    const eff = getEffectiveS(b)
                    const isPend = b.status === 'pending'
                    return (
                      <div key={b.id}
                        className="bg-white border border-blue-100 rounded-2xl px-6 py-4 flex items-center gap-4 cursor-pointer hover:shadow-md hover:-translate-y-0.5 transition-all"
                        style={{borderLeftWidth:4, borderLeftColor: eff.dot}}
                        onClick={() => setSelectedBooking(b)}>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3 mb-1 flex-wrap">
                            <p className="font-bold text-slate-900 truncate">{b.title}</p>
                            <span className={`text-xs px-2.5 py-0.5 rounded-full font-semibold flex-shrink-0 ${eff.bg} ${eff.text}`}>
                              {eff.label}
                            </span>
                            {b.checked_in && <span className="text-xs bg-blue-50 text-blue-700 px-2.5 py-0.5 rounded-full font-semibold flex-shrink-0">✓ Check-in</span>}
                          </div>
                          <p className="text-sm text-blue-600 font-medium mb-1">{b.room_name||`ห้อง #${b.room}`}</p>
                          <div className="flex gap-4 text-xs text-slate-400">
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
          <div className="au">
            <div className="flex items-center gap-2 mb-6">
              <LayoutGrid size={16} className="text-blue-600" />
              <h2 className="text-base font-bold text-slate-800">สถานะห้องแบบ Real-time</h2>
              <span className="text-xs text-slate-400 ml-1">— ห้องทั้งหมด {ALL_ROOMS_DATA.length} ห้อง (อัปเดตทุก 30 วินาที)</span>
            </div>
            <RoomStatusGrid bookings={bookings} fmtTime={fmtTime} isMobile={false} />
          </div>
        )}

        {tab === 'overview' && dashboard && (
          <div className="grid grid-cols-3 gap-6">
            <div className="space-y-4 au">
              {[
                {label:'จองวันนี้',    value:dashboard.today_bookings??0,        icon:'📅',color:'text-blue-700'},
                {label:'ห้องทั้งหมด', value:ALL_ROOMS_DATA.length,               icon:'🏢',color:'text-slate-700'},
                {label:'อัตราการใช้', value:`${dashboard.utilization_rate??0}%`, icon:'📊',color:'text-emerald-600'},
                {label:'ยืนยันแล้ว',  value:activeB.length,                      icon:'✅',color:'text-blue-600'},
              ].map((s,i) => (
                <div key={i} className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm flex items-center gap-4">
                  <span className="text-2xl">{s.icon}</span>
                  <div>
                    <p className={`text-2xl font-extrabold ${s.color}`}>{s.value}</p>
                    <p className="text-xs text-slate-500">{s.label}</p>
                  </div>
                </div>
              ))}
              <NoShowCard bookings={bookings} />
            </div>
            <div className="col-span-2 space-y-4 au1">
              <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm">
                <p className="text-sm font-bold text-slate-900 mb-5 flex items-center gap-2">
                  <BarChart2 size={14} className="text-blue-600" />การจองรายวัน 7 วันล่าสุด
                </p>
                <BarChartBlock weekStats={weekStats} />
                <div className="mt-4 pt-4 border-t border-blue-50 flex justify-between text-xs text-slate-400">
                  <span>รวม: {weekStats.reduce((s,d)=>s+d.count,0)} การจอง</span>
                  <span>เฉลี่ย: {(weekStats.reduce((s,d)=>s+d.count,0)/7).toFixed(1)}/วัน</span>
                </div>
              </div>
              {dashboard.popular_rooms?.length > 0 && (
                <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm">
                  <p className="text-sm font-bold text-slate-900 mb-5 flex items-center gap-2">
                    <TrendingUp size={14} className="text-blue-600" />ห้องที่ใช้บ่อย
                  </p>
                  <div className="space-y-4">
                    {dashboard.popular_rooms.map((room,i) => {
                      const pct  = Math.round((room.count/(dashboard.popular_rooms[0]?.count||1))*100)
                      const cols = ['bg-blue-500','bg-blue-400','bg-blue-300','bg-blue-200','bg-blue-100']
                      return (
                        <div key={i} className="flex items-center gap-4">
                          <span className="text-xs font-black text-slate-300 w-4">{i+1}</span>
                          <div className="flex-1">
                            <div className="flex justify-between mb-1.5">
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

        {tab === 'noshow' && (
          <div className="grid grid-cols-3 gap-6">
            <div className="au"><NoShowCard bookings={bookings} /></div>
            <div className="col-span-2 space-y-2 au1">
              <p className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
                <UserX size={14} className="text-orange-500" />รายการ No-Show ทั้งหมด
              </p>
              {noShowB.length === 0
                ? <div className="bg-white border border-blue-100 rounded-2xl py-12 text-center">
                    <p className="text-slate-400 text-sm">ไม่มีรายการ No-Show 🎉</p>
                  </div>
                : noShowB.map(b => (
                    <div key={b.id} onClick={() => setSelectedBooking(b)}
                      className="bg-white border border-orange-100 rounded-xl px-6 py-4 flex items-center gap-4 cursor-pointer hover:bg-orange-50/40 transition-colors"
                      style={{borderLeftWidth:4,borderLeftColor:'#f97316'}}>
                      <UserX size={14} className="text-orange-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-slate-800 truncate">{b.title}</p>
                        <p className="text-xs text-slate-400 mt-0.5">{b.room_name} · {fmtDate(b.start_time)} · {fmtTime(b.start_time)}</p>
                        {b.user_name && <p className="text-xs text-orange-600 mt-0.5">โดย {b.user_name}</p>}
                      </div>
                      <span className="text-xs bg-orange-50 text-orange-700 border border-orange-200 px-2.5 py-1 rounded-full font-bold flex-shrink-0">No-Show</span>
                    </div>
                  ))
              }
            </div>
          </div>
        )}

        {tab === 'all' && (
          <div className="space-y-2 au">
            {bookings.map(b => {
              const s = getEffectiveS(b)
              return (
                <div key={b.id} onClick={() => setSelectedBooking(b)}
                  className={`bg-white border border-blue-100 rounded-xl px-6 py-4 flex items-center gap-4 cursor-pointer hover:bg-blue-50/40 transition-colors
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
      <BookingDetailModal booking={selectedBooking} onClose={()=>setSelectedBooking(null)}
        onCancel={handleCancel} fmtTime={fmtTime} fmtDateFull={fmtDateFull} />
    </div>
  )
}

// ============================================================
// MOBILE
// ============================================================
function MobileAdmin({ dashboard, bookings, weekStats, tab, setTab, selectedBooking,
  setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull, navigate }) {

  const pendingB   = bookings.filter(b => b.status === 'pending')
  const activeB    = bookings.filter(b => b.status === 'approved' && !isPast(b.end_time))
  const cancelledB = bookings.filter(b => b.status === 'cancelled')
  const noShowB    = bookings.filter(b => b.status === 'no_show')

  const currentB = bookings.filter(b =>
    (b.status === 'pending') ||
    (b.status === 'approved' && !isPast(b.end_time))
  )

  const tabs = [
    {key:'active',   label:'จอง',     count:currentB.length},
    {key:'rooms',    label:'ห้อง',    count:null},
    {key:'overview', label:'ภาพรวม',  count:null},
    {key:'noshow',   label:'No-Show', count:noShowB.length},
    {key:'all',      label:'ทั้งหมด', count:bookings.length},
  ]

  return (
    <div className="min-h-screen bg-blue-50" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="bg-blue-700 sticky top-0 z-40 shadow-lg shadow-blue-900/20">
        <div className="max-w-lg mx-auto px-4 h-12 flex items-center gap-3">
          <button onClick={() => navigate('/')} className="text-white/80 hover:text-white flex items-center"><ArrowLeft size={14} /></button>
          <span className="text-white font-bold text-sm flex-1">Admin Dashboard</span>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 bg-yellow-300 text-yellow-900 text-xs font-bold rounded-full px-2 py-0.5"><Zap size={9} />AI</div>
            <ExportButton isMobile={true} />
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
        <div className="max-w-lg mx-auto px-2 flex border-t border-white/10 overflow-x-auto">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex-shrink-0 flex items-center justify-center gap-1 px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap
                ${tab===t.key?'border-yellow-400 text-white':'border-transparent text-white/55 hover:text-white'}`}>
              {t.label}
              {t.count!==null && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold
                  ${t.key==='noshow'&&t.count>0?'bg-orange-400 text-white':tab===t.key?'bg-yellow-400 text-yellow-900':'bg-white/15 text-white/70'}`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 space-y-3 pb-12">
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
            <div className="au1"><NoShowCard bookings={bookings} /></div>
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
          <div className="au">
            <div className="flex items-center gap-2 mb-4">
              <LayoutGrid size={14} className="text-blue-600" />
              <h2 className="text-sm font-bold text-slate-800">สถานะห้อง {ALL_ROOMS_DATA.length} ห้อง</h2>
            </div>
            <RoomStatusGrid bookings={bookings} fmtTime={fmtTime} isMobile={true} />
          </div>
        )}

        {tab === 'overview' && dashboard && (
          <>
            <div className="grid grid-cols-2 gap-2 au">
              {[
                {label:'จองวันนี้',    value:dashboard.today_bookings??0,        icon:'📅',color:'text-blue-700'},
                {label:'ห้องทั้งหมด', value:ALL_ROOMS_DATA.length,               icon:'🏢',color:'text-slate-700'},
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
            <div className="au1"><NoShowCard bookings={bookings} /></div>
            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au2">
              <p className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
                <BarChart2 size={13} className="text-blue-600" />การจองรายวัน 7 วัน
              </p>
              <BarChartBlock weekStats={weekStats} />
            </div>
          </>
        )}

        {tab === 'noshow' && (
          <>
            <div className="au"><NoShowCard bookings={bookings} /></div>
            {noShowB.length === 0
              ? <div className="bg-white border border-blue-100 rounded-2xl py-10 text-center au1">
                  <p className="text-slate-400 text-sm">ไม่มีรายการ No-Show 🎉</p>
                </div>
              : noShowB.map(b => (
                  <div key={b.id} onClick={() => setSelectedBooking(b)}
                    className="bg-white border border-orange-100 rounded-xl px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-orange-50/40 au1"
                    style={{borderLeftWidth:4,borderLeftColor:'#f97316'}}>
                    <UserX size={13} className="text-orange-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-800 truncate">{b.title}</p>
                      <p className="text-xs text-slate-400">{b.room_name} · {fmtDate(b.start_time)}</p>
                    </div>
                    <span className="text-xs bg-orange-50 text-orange-700 border border-orange-200 px-2 py-0.5 rounded-full font-bold flex-shrink-0">No-Show</span>
                  </div>
                ))
            }
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
  const [bookings,        setBookings]        = useState([])
  const [tab,             setTab]             = useState('active')
  const [loading,         setLoading]         = useState(true)
  const [weekStats,       setWeekStats]       = useState([])
  const [selectedBooking, setSelectedBooking] = useState(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [dashRes, bookingRes] = await Promise.all([
          api.get('dashboard/'),
          api.get('bookings/'),
        ])
        setDashboard(dashRes.data)
        const all = bookingRes.data.results || []
        setBookings(all)
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
    <div className="min-h-screen bg-blue-50 flex flex-col items-center justify-center gap-3" style={{fontFamily:"'Sarabun',sans-serif"}}>
      <style>{ANIM}</style>
      <div style={{width:36,height:36,border:'3px solid #bfdbfe',borderTopColor:'#1d4ed8',borderRadius:'50%',animation:'rot .7s linear infinite'}} />
      <p className="text-sm text-slate-500">กำลังโหลด...</p>
    </div>
  )

  const props = {
    dashboard, bookings, weekStats, tab, setTab,
    selectedBooking, setSelectedBooking,
    handleCancel, fmtDate, fmtTime, fmtDateFull, navigate
  }
  return isMobile ? <MobileAdmin {...props} /> : <DesktopAdmin {...props} />
}