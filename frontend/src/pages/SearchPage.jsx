import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  ArrowLeft, Bell, BarChart3, Building2, Calendar, CalendarDays, Check,
  CheckCircle, ChevronDown, ChevronRight, Clock, Coffee, Home,
  LifeBuoy, LayoutDashboard, MapPin, RefreshCw, Search, Settings2,
  Sparkles, ArrowRight, Users, X, BookOpen, AlertTriangle,
} from 'lucide-react'
import api from '../api/axios'

// ─── Constants ───────────────────────────────────────────────────────────────
const DEFAULT_BUILDINGS = [{ code: '', label: 'ทั้งหมด' }]
const TIME_SLOTS = ['08:00','09:00','10:00','11:00','13:00','14:00','15:00','16:00']
const DURATIONS  = [{ label: '1 ชม.', hours: 1 },{ label: '2 ชม.', hours: 2 },{ label: '3 ชม.', hours: 3 }]
// ห้องที่มีข้อมูล AI จริง (ดู AI_FORECAST_ROOM_IDS ฝั่ง backend) ตอนนี้เป็นห้อง
// Lab คอมพิวเตอร์ขนาดใหญ่ล้วน (ความจุ 31-61 คน) ไม่มีห้องเล็ก — ปรับค่าเริ่มต้น/
// ขั้นต่ำผู้เข้าร่วมเป็น 20 คน ให้ตรงกับห้องที่มีจริง กันค้นหากลุ่มเล็กแล้วไม่เจอห้องเลย
const MIN_ATTENDEES     = 20
const ATTENDEES_PRESETS = [20, 30, 40, 50, 60]

const DAYS_OF_WEEK = [
  { value: 1, label: 'จ.',  full: 'วันจันทร์' },
  { value: 2, label: 'อ.',  full: 'วันอังคาร' },
  { value: 3, label: 'พ.',  full: 'วันพุธ' },
  { value: 4, label: 'พฤ.', full: 'วันพฤหัสบดี' },
  { value: 5, label: 'ศ.',  full: 'วันศุกร์' },
  { value: 6, label: 'ส.',  full: 'วันเสาร์' },
  { value: 0, label: 'อา.', full: 'วันอาทิตย์' },
]

const ROOM_STATUS = {
  available:   { label: 'ว่าง',      cls: 'bg-green-50 text-green-700 border-green-200',  dot: '#16a34a' },
  occupied:    { label: 'ถูกใช้งาน', cls: 'bg-red-50 text-red-600 border-red-200',        dot: '#dc2626' },
  maintenance: { label: 'ซ่อมบำรุง', cls: 'bg-amber-50 text-amber-700 border-amber-200',  dot: '#d97706' },
  disabled:    { label: 'ปิดใช้',    cls: 'bg-gray-100 text-gray-500 border-gray-200',    dot: '#9ca3af' },
}

const FORECAST_CONFIG = {
  urgent: {
    badge: 'รีบจองด่วน!', sub: 'โอกาสสุดท้ายก่อนเต็ม',
    badgeCls: 'bg-red-50 text-red-700 border border-red-200',
    dotColor: '#dc2626', pillCls: 'bg-red-50 border border-red-200',
    textCls: 'text-red-700', subCls: 'text-red-500',
    cardBg: 'bg-red-50', cardBorder: 'border-red-200', numCls: 'text-red-600',
  },
  high: {
    badge: 'ความต้องการสูง', sub: 'เริ่มเป็นที่ต้องการ',
    badgeCls: 'bg-orange-50 text-orange-700 border border-orange-200',
    dotColor: '#f97316', pillCls: 'bg-orange-50 border border-orange-200',
    textCls: 'text-orange-700', subCls: 'text-orange-500',
    cardBg: 'bg-orange-50', cardBorder: 'border-orange-200', numCls: 'text-orange-600',
  },
  medium: {
    badge: 'ควรจองตอนนี้', sub: 'เริ่มมีคนสนใจ',
    badgeCls: 'bg-yellow-50 text-yellow-800 border border-yellow-300',
    dotColor: '#f59e0b', pillCls: 'bg-yellow-50 border border-yellow-300',
    textCls: 'text-yellow-800', subCls: 'text-yellow-600',
    cardBg: 'bg-yellow-50', cardBorder: 'border-yellow-200', numCls: 'text-yellow-600',
  },
  low: {
    badge: 'ยังว่างอยู่', sub: 'ห้องว่าง พร้อมใช้งาน',
    badgeCls: 'bg-blue-50 text-blue-700 border border-blue-200',
    dotColor: '#2563eb', pillCls: 'bg-blue-50 border border-blue-200',
    textCls: 'text-blue-700', subCls: 'text-blue-500',
    cardBg: 'bg-blue-50', cardBorder: 'border-blue-200', numCls: 'text-blue-600',
  },
  none: {
    badge: '—', sub: '',
    badgeCls: 'bg-gray-100 text-gray-500 border border-gray-200',
    dotColor: '#cbd5e1', pillCls: 'bg-gray-50 border border-gray-200',
    textCls: 'text-gray-500', subCls: 'text-gray-400',
    cardBg: 'bg-gray-50', cardBorder: 'border-gray-200', numCls: 'text-gray-500',
  },
}

const SUMMARY_TIERS = [
  { level: 'urgent', label: 'รีบจองด่วน!' },
  { level: 'high',   label: 'ความต้องการสูง' },
  { level: 'medium', label: 'ควรจองตอนนี้' },
  { level: 'low',    label: 'ยังว่างอยู่' },
]

const FALLBACK_EQUIPMENT_PRESETS = [
  { key: 'computer',   label: 'คอมพิวเตอร์', shortLabel: 'คอมฯ', icon: '💻', keywords: ['คอมพิวเตอร์', 'computer', 'pc', 'imac'], group_key: 'computer', group_label: 'คอมพิวเตอร์', is_category: true },
  { key: 'projector',  label: 'โปรเจกเตอร์', shortLabel: 'โปรเจค', icon: '📽️', keywords: ['โปรเจกเตอร์', 'โปรเจคเตอร์', 'projector'], group_key: 'projector', group_label: 'โปรเจกเตอร์', is_category: true },
  { key: 'microphone', label: 'ไมโครโฟน', shortLabel: 'ไมค์', icon: '🎤', keywords: ['ไมโครโฟน', 'microphone', 'ไมค์'], group_key: 'microphone', group_label: 'ไมโครโฟน', is_category: true },
  { key: 'sound',      label: 'ระบบเสียง', shortLabel: 'เสียง', icon: '🔊', keywords: ['ระบบเสียง', 'เครื่องเสียง', 'ลำโพง', 'mixer'], group_key: 'sound', group_label: 'ระบบเสียง', is_category: true },
  { key: 'tv',         label: 'TV / จอแสดงผล', shortLabel: 'TV/จอ', icon: '📺', keywords: ['tv', 'จอแสดงผล', 'จอ ', 'จอแขวน', 'จอมอเตอร์', 'จอไฟฟ้า', 'นิ้ว'], group_key: 'tv', group_label: 'TV / จอแสดงผล', is_category: true },
  { key: 'video_conf', label: 'Video Conference', shortLabel: 'VDO Conf', icon: '📹', keywords: ['video conference', 'วีดีโอ', 'vdo', 'webcam', 'zoom', 'teams', 'meet'], group_key: 'video_conf', group_label: 'Video Conference', is_category: true },
  { key: 'flipboard', label: 'Flipboard', shortLabel: 'Flipboard', icon: '📋', keywords: ['flipboard', 'flip2'], group_key: 'flipboard', group_label: 'Flipboard', is_category: true },
  { key: 'interactive', label: 'โปรเจกเตอร์อินเทอร์แอคทีฟ', shortLabel: 'อินเทอร์แอคทีฟ', icon: '🖊️', keywords: ['อินเทอร์แอคทีฟ', 'interactive', 'touch screen'], group_key: 'interactive', group_label: 'โปรเจกเตอร์อินเทอร์แอคทีฟ', is_category: true },
]

// keyword ของแต่ละ preset ต้องครอบคลุมเท่ากับ category ที่ backend ให้มา
// (booking/views.py equipment_filters) ไม่งั้นปุ่ม quick preset จะกรองห้องตกหล่น
// เทียบกับถ้าเลือกผ่าน chip category ตรงๆ ทั้งที่ควรให้ผลเหมือนกัน
const QUICK_EQUIPMENT_PRESETS = [
  { key: 'presentation_ready', label: 'นำเสนอ / บรรยาย', shortLabel: 'นำเสนอ', icon: '📽️', hint: 'โปรเจกเตอร์ + จอ', keywords: ['โปรเจกเตอร์', 'โปรเจคเตอร์', 'projector', 'จอ'] },
  { key: 'computer_lab', label: 'คอมพิวเตอร์แลบ', shortLabel: 'คอมแลบ', icon: '💻', hint: 'PC / iMac', keywords: ['pc', 'คอมพิวเตอร์', 'computer', 'imac'] },
  { key: 'audio_room', label: 'ประชุมพร้อมเสียง', shortLabel: 'ระบบเสียง', icon: '🔊', hint: 'ไมค์ + ลำโพง', keywords: ['ไมค์', 'ไมโครโฟน', 'microphone', 'ระบบเสียง', 'เครื่องเสียง', 'ลำโพง', 'mixer'] },
  { key: 'video_meeting', label: 'Video Conference', shortLabel: 'วิดีโอ', icon: '📹', hint: 'กล้อง / Zoom', keywords: ['video conference', 'zoom', 'กล้อง', 'วีดีโอ', 'vdo', 'webcam', 'teams', 'meet'] },
]

// key พวกนี้ถูกครอบคลุมโดย QUICK_EQUIPMENT_PRESETS อยู่แล้ว (นำเสนอ→projector,
// คอมพิวเตอร์แลบ→computer, ประชุมพร้อมเสียง→microphone/sound, Video Conference→video_conf)
// ไม่งั้นจะโผล่ซ้ำเป็นปุ่มคนละอันที่หน้าตาเหมือนกัน
const QUICK_PRESET_COVERED_KEYS = ['computer', 'projector', 'microphone', 'sound', 'video_conf']

const getEquipmentOptions = (presets = []) => {
  const categoryOptions = (presets?.length ? presets : FALLBACK_EQUIPMENT_PRESETS)
    .filter(eq => eq.is_category)
    .filter(eq => !QUICK_PRESET_COVERED_KEYS.includes(eq.key))
  return [...QUICK_EQUIPMENT_PRESETS, ...categoryOptions]
}

const findPreset = (presets, key) =>
  [...QUICK_EQUIPMENT_PRESETS, ...(presets || []), ...FALLBACK_EQUIPMENT_PRESETS].find(p => p.key === key)

const getFacIcon = (name) => {
  const lower = (name || '').toLowerCase()
  if (lower.includes('คอมพิวเตอร์') || lower.includes('pc')) return '💻'
  if (lower.includes('โปรเจกเตอร์') || lower.includes('projector')) return '📽️'
  if (lower.includes('ไมโครโฟน') || lower.includes('ไมค์')) return '🎤'
  if (lower.includes('เสียง') || lower.includes('ลำโพง')) return '🔊'
  if (lower.includes('tv') || lower.includes('จอ')) return '📺'
  if (lower.includes('video') || lower.includes('zoom')) return '📹'
  return '🔧'
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
const addHours = (time, hours) => {
  const [h, m] = time.split(':').map(Number)
  return `${String(h + hours).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
// จำนวนชั่วโมงกำหนดเอง — ต้องเป็นจำนวนเต็มบวก และเวลาสิ้นสุดต้องไม่เกิน 23:xx
// (addHours ข้างบนไม่รองรับการข้ามเที่ยงคืน)
const validateCustomDuration = (rawValue, startTime) => {
  const hours = Number(rawValue)
  if (rawValue === '' || Number.isNaN(hours)) return 'กรุณาระบุจำนวนชั่วโมง'
  if (!Number.isInteger(hours) || hours < 1) return 'จำนวนชั่วโมงต้องเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป'
  if (startTime) {
    const [h] = startTime.split(':').map(Number)
    if (h + hours > 23) return `เวลาสิ้นสุดเกิน 23:00 น. กรุณาลดจำนวนชั่วโมงหรือเลือกเวลาเริ่มที่เร็วขึ้น`
  }
  return ''
}
const formatDate = d => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
const formatDateShort = d => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', { day: 'numeric', month: 'short' })
const getDemandLevel = room => {
  const raw = room.forecast?.demand_level
  const availMap = { book_now: 'urgent', book_soon: 'high', recommended: 'medium', likely_available: 'low' }
  if (raw && availMap[raw]) return availMap[raw]
  if (raw && FORECAST_CONFIG[raw]) return raw
  return 'none'
}
const getDayLabel = v => DAYS_OF_WEEK.find(d => d.value === v)?.full ?? ''

const ACADEMIC_TERM_META = {
  1: { label: 'ภาคเรียนที่ 1', short: 'เทอม 1', period: 'มิ.ย. – ต.ค.' },
  2: { label: 'ภาคเรียนที่ 2', short: 'เทอม 2', period: 'พ.ย. – มี.ค.' },
  3: { label: 'ภาคฤดูร้อน', short: 'ฤดูร้อน', period: 'เม.ย. – พ.ค.' },
}
const ACADEMIC_TERM_IDS = [1, 2, 3]
const gregorianFromThaiYear = thaiYear => thaiYear - 543
const getTermDateRange = (thaiYear, termNum) => {
  const gy = gregorianFromThaiYear(thaiYear)
  if (termNum === 1) return { start: `${gy}-06-01`, end: `${gy}-10-31` }
  if (termNum === 2) return { start: `${gy}-11-01`, end: `${gy + 1}-03-31` }
  return { start: `${gy + 1}-04-01`, end: `${gy + 1}-05-31` }
}
const buildTermName = (thaiYear, termNum) => `${ACADEMIC_TERM_META[termNum]?.label ?? 'ภาคเรียน'}/${thaiYear}`
const getDefaultAcademicYearBE = () => {
  const m = new Date().getMonth() + 1
  const gy = new Date().getFullYear()
  return m >= 6 ? gy + 543 : gy + 543 - 1
}
const getDefaultTermNumber = () => {
  const m = new Date().getMonth() + 1
  if (m >= 6 && m <= 10) return 1
  if (m >= 11 || m <= 3) return 2
  return 3
}
const getAcademicYearOptions = () => {
  const current = getDefaultAcademicYearBE()
  return [current - 1, current, current + 1]
}
const isClassroomType = room => {
  if (!room.room_type) return false
  const t = room.room_type.toLowerCase().trim()
  return t.includes('ห้องเรียน') || t.includes('lecture') || t.includes('classroom')
}

const roomHasEquipments = (room, selectedEquipments, equipmentPresets) => {
  if (!selectedEquipments || selectedEquipments.length === 0) return true
  if (!room.facilities || room.facilities.length === 0) return false
  const facilityNames = room.facilities.map(f => f.name.toLowerCase())
  const presets = equipmentPresets?.length ? equipmentPresets : FALLBACK_EQUIPMENT_PRESETS
  return selectedEquipments.every(key => {
    const preset = findPreset(presets, key)
    if (!preset) return true
    return preset.keywords.some(kw => facilityNames.some(fn => fn.includes(kw.toLowerCase())))
  })
}

const normalizeText = value => (value ?? '').toString().toLowerCase().trim()

const getMatchedEquipmentCount = (room, selectedEquipments, equipmentPresets) => {
  if (!selectedEquipments?.length || !room.facilities?.length) return 0
  const facilityNames = room.facilities.map(f => normalizeText(f.name))
  const presets = equipmentPresets?.length ? equipmentPresets : FALLBACK_EQUIPMENT_PRESETS
  return selectedEquipments.reduce((count, key) => {
    const preset = findPreset(presets, key)
    if (!preset) return count
    const matched = preset.keywords.some(kw => facilityNames.some(fn => fn.includes(normalizeText(kw))))
    return matched ? count + 1 : count
  }, 0)
}

const scoreFallbackRoom = (room, {
  attendees,
  building,
  bookingType,
  selectedEquipments,
  equipmentPresets,
}) => {
  const capacity = Number(room.capacity) || 0
  const gap = Math.max(0, capacity - attendees)
  let score = 0
  const reasons = []

  if (capacity === attendees) {
    score += 40
    reasons.push('ความจุพอดี')
  } else if (capacity <= attendees + 5) {
    score += 32
    reasons.push(`รองรับ ${capacity} คน`)
  } else {
    score += Math.max(8, 24 - Math.min(gap, 20))
    reasons.push(`รองรับ ${capacity} คน`)
  }

  const roomBuildingCode = room.building?.code || room.building_code || room.building
  const roomBuildingName = room.building_name || room.building?.name
  if (building && roomBuildingCode && normalizeText(roomBuildingCode) === normalizeText(building)) {
    score += 30
    reasons.push('อาคารเดียวกับเงื่อนไข')
  } else if (building && roomBuildingName) {
    score += 10
    reasons.push(`อาคาร ${roomBuildingName}`)
  }

  if (bookingType === 'term' && isClassroomType(room)) {
    score += 18
    reasons.push('เหมาะกับจองทั้งเทอม')
  }

  const level = getDemandLevel(room)
  if (level === 'low') score += 8
  else if (level === 'medium') score += 5
  else if (level === 'high') score += 2

  const matchedEquipmentCount = getMatchedEquipmentCount(room, selectedEquipments, equipmentPresets)
  if (matchedEquipmentCount > 0) {
    score += matchedEquipmentCount * 7
    reasons.push(`ตรงอุปกรณ์ ${matchedEquipmentCount} รายการ`)
  } else if (selectedEquipments?.length > 0) {
    reasons.push('อุปกรณ์ใกล้เคียง')
  }

  if (room.status === 'available') score += 4

  const reason = reasons.slice(0, 3).join(' · ') || 'ห้องใกล้เคียงที่พร้อมจอง'
  return { score, reason }
}

// ─── Animations ──────────────────────────────────────────────────────────────
const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes scaleIn{from{opacity:0;transform:scale(.98)}to{opacity:1;transform:scale(1)}}
.au{animation:fadeUp .2s ease both}
.au1{animation:fadeUp .2s .05s ease both}
.au2{animation:fadeUp .2s .1s ease both}
.si{animation:scaleIn .2s ease both}
.checkin-pulse{animation:pulse 2.5s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.7}}
`

// ─── Shared Compact Components ───────────────────────────────────────────────
function Chip({ active, children, onClick, className = '' }) {
  return (
    <button onClick={onClick}
      className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all duration-150 whitespace-nowrap
        ${active
          ? 'bg-blue-700 border-blue-700 text-white shadow-sm'
          : 'bg-white border-slate-200 text-slate-600 hover:border-blue-300 hover:bg-blue-50'
        } ${className}`}>
      {children}
    </button>
  )
}

function SectionLabel({ icon: Icon, children }) {
  return (
    <div className="flex items-center gap-1.5 text-slate-500 text-[11px] font-bold uppercase tracking-wider mb-1.5">
      {Icon && <Icon size={11} className="flex-shrink-0" />}<span>{children}</span>
    </div>
  )
}

function EquipmentSelector({ selected, onChange, equipmentPresets = FALLBACK_EQUIPMENT_PRESETS }) {
  const toggle = (key) => {
    if (selected.includes(key)) onChange(selected.filter(k => k !== key))
    else onChange([...selected, key])
  }
  const options = getEquipmentOptions(equipmentPresets)
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(eq => {
        const active = selected.includes(eq.key)
        return (
          <button key={eq.key} onClick={() => toggle(eq.key)}
            className={`group inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-all
              ${active
                ? 'bg-gradient-to-br from-blue-600 to-indigo-600 border-blue-600 text-white shadow-sm'
                : 'bg-white border-slate-200 text-slate-700 hover:border-blue-300 hover:bg-blue-50'}`}>
            <span className="text-sm leading-none">{eq.icon}</span>
            {eq.shortLabel || eq.label}
            {active && <Check size={12} className="text-white shrink-0" />}
          </button>
        )
      })}
    </div>
  )
}

function FacilityTags({ facilities = [], maxShow = 3, highlight = [], equipmentPresets = FALLBACK_EQUIPMENT_PRESETS }) {
  if (!facilities?.length) return null
  const isHighlighted = (name) => highlight.some(key => {
    const preset = findPreset(equipmentPresets, key)
    return preset?.keywords.some(kw => name.toLowerCase().includes(kw.toLowerCase()))
  })
  const shown = facilities.slice(0, maxShow)
  const rest = facilities.length - maxShow
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((f, i) => {
        const hl = isHighlighted(f.name)
        return (
          <span key={i} className={`inline-flex items-center gap-1 text-[10px] rounded-md px-1.5 py-0.5 font-medium border max-w-full
            ${hl ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-slate-50 border-slate-200 text-slate-600'}`}>
            <span className="text-xs leading-none">{getFacIcon(f.name)}</span>
            <span className="truncate">{f.name}</span>
          </span>
        )
      })}
      {rest > 0 && <span className="text-[10px] text-slate-400 border border-slate-200 rounded-md px-1.5 py-0.5 bg-white">+{rest}</span>}
    </div>
  )
}

function BookingTypeSelector({ value, onChange }) {
  const types = [
    { key: 'daily', icon: Coffee, label: 'รายวัน', sub: 'เลือกวันและเวลา' },
    { key: 'term', icon: BookOpen, label: 'ทั้งเทอม', sub: 'จองประจำทุกสัปดาห์' },
  ]
  return (
    <div className="grid grid-cols-2 gap-2">
      {types.map(t => {
        const Icon = t.icon
        const active = value === t.key
        const accent = active ? (t.key === 'term' ? 'from-indigo-600 to-violet-600 border-indigo-600' : 'from-blue-600 to-indigo-600 border-blue-600') : 'bg-white border-slate-200'
        return (
          <button key={t.key} onClick={() => onChange(t.key)}
            className={`group relative flex items-center gap-2.5 overflow-hidden rounded-2xl border px-3 py-2.5 transition-all text-left
              ${active ? `bg-gradient-to-br ${accent} text-white shadow-md shadow-blue-200/70` : 'bg-white text-slate-700 hover:border-blue-300 hover:shadow-sm'}`}>
            <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${active ? 'bg-white/15' : 'bg-blue-50 group-hover:bg-blue-100'}`}>
              <Icon size={15} className={active ? 'text-white' : 'text-blue-600'} />
            </div>
            <div className="min-w-0">
              <p className={`text-sm font-bold leading-tight truncate ${active ? 'text-white' : 'text-slate-900'}`}>{t.label}</p>
              <p className={`text-[11px] leading-snug truncate ${active ? 'text-white/80' : 'text-slate-500'}`}>{t.sub}</p>
            </div>
            {active && <CheckCircle size={13} className="absolute top-2 right-2 text-white/90" />}
          </button>
        )
      })}
    </div>
  )
}

function RoomStatusBadge({ status }) {
  const cfg = ROOM_STATUS[status] ?? ROOM_STATUS.available
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-1 text-[11px] font-bold ${cfg.cls}`}>
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: cfg.dot }} />
      {cfg.label}
    </span>
  )
}

function CheckInReminder({ startTime }) {
  if (!startTime) return null
  return (
    <div className="checkin-pulse relative overflow-hidden border border-amber-300 bg-amber-50 rounded-xl p-3 shadow-sm">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="text-amber-500 flex-shrink-0 mt-0.5" />
        <p className="text-amber-800 text-xs font-medium leading-snug">
          ⚠️ หากไม่สามารถเข้าใช้งานได้ตามเวลาที่จอง กรุณายกเลิกล่วงหน้า เพื่อให้ผู้อื่นใช้บริการต่อได้
        </p>
      </div>
    </div>
  )
}

function SummaryTiles({ rooms }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {SUMMARY_TIERS.map(s => {
        const cfg = FORECAST_CONFIG[s.level]
        const count = rooms.filter(r => getDemandLevel(r) === s.level).length
        return (
          <div key={s.level} className={`rounded-2xl border px-3 py-3 text-center ${cfg.cardBg} ${cfg.cardBorder}`}>
            <p className={`text-2xl font-extrabold leading-none ${cfg.numCls}`}>{count}</p>
            <p className={`mt-1 text-[10px] font-semibold leading-tight px-1 ${cfg.textCls} opacity-90`}>{s.label}</p>
          </div>
        )
      })}
    </div>
  )
}

function RoomCard({ room, onClick, isTermMode, selectedEquipments, equipmentPresets, isBest }) {
  const level = getDemandLevel(room)
  const cfg = FORECAST_CONFIG[level]
  const facilityCount = room.facilities?.length || 0
  return (
    <div
      onClick={onClick}
      className={`group cursor-pointer overflow-hidden rounded-[20px] border bg-white shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg ${isBest ? 'border-emerald-300 ring-1 ring-emerald-200' : 'border-slate-200 hover:border-blue-200'}`}
    >
      <div className="flex gap-3 p-3">
        <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-2xl bg-slate-100 sm:h-24 sm:w-24">
          {room.image ? (
            <img src={room.image} alt={room.name} className="h-full w-full object-cover" loading="lazy" />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-50 text-blue-300">
              <Building2 size={28} />
            </div>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <span className="truncate text-sm font-bold text-slate-900 transition-colors group-hover:text-blue-700 sm:text-base">{room.name}</span>
            <RoomStatusBadge status={room.status} />
          </div>
          <p className="mt-0.5 truncate text-xs text-slate-400">{room.building_name}</p>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1"><Building2 size={12} className="text-slate-400" /> ชั้น {room.floor}</span>
            <span className="inline-flex items-center gap-1"><Users size={12} className="text-slate-400" /> รองรับ {room.capacity} คน</span>
            {facilityCount > 0 && (
              <span className="inline-flex items-center gap-1"><Sparkles size={12} className="text-slate-400" /> อุปกรณ์ {facilityCount} รายการ</span>
            )}
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {isBest && (
              <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700">
                <Sparkles size={10} /> เหมาะสมที่สุด
              </span>
            )}
            {level !== 'none' && <span className={`whitespace-nowrap rounded-full px-1.5 py-0.5 text-[10px] font-bold ${cfg.badgeCls}`}>{cfg.badge}</span>}
          </div>
        </div>
      </div>

      {facilityCount > 0 && (
        <div className="border-t border-slate-100 px-3 pb-2 pt-2">
          <FacilityTags facilities={room.facilities} maxShow={3} highlight={selectedEquipments} equipmentPresets={equipmentPresets} />
        </div>
      )}

      <button
        type="button"
        className={`flex w-full items-center justify-center gap-1.5 border-t border-slate-100 py-2.5 text-sm font-bold transition-colors ${isBest ? 'bg-emerald-50 text-emerald-700 group-hover:bg-emerald-100' : 'bg-blue-50/70 text-blue-700 group-hover:bg-blue-100'}`}
      >
        {isTermMode ? 'เลือกห้องนี้' : 'เลือกเวลา'} <ChevronRight size={14} />
      </button>
    </div>
  )
}

function SuggestedRoomCard({ room, onSelect, bookingType, attendees, selectedEquipments, equipmentPresets }) {
  const level = getDemandLevel(room)
  const cfg = FORECAST_CONFIG[level]
  const reason = room.recommendation_reason || 'ห้องใกล้เคียงที่พร้อมจอง'

  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm hover:shadow-lg hover:border-blue-200 transition-all group">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-blue-500 via-cyan-400 to-indigo-500" />
      <div className="bg-gradient-to-br from-slate-50 via-white to-blue-50/70 p-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 whitespace-nowrap">
                <Sparkles size={10} /> แผนสอง
              </span>
              {level !== 'none' && <span className={`text-[10px] font-bold px-2 py-1 rounded-full whitespace-nowrap ${cfg.badgeCls}`}>{cfg.badge}</span>}
            </div>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <span className="block font-extrabold text-slate-900 text-base sm:text-lg truncate group-hover:text-blue-700 transition-colors">{room.name}</span>
                <p className="text-xs text-slate-500 mt-1 truncate">
                  {room.building_name} · ชั้น {room.floor} · รองรับ {room.capacity} ที่นั่ง
                </p>
              </div>
              <RoomStatusBadge status={room.status} />
            </div>

            <div className="mt-3 rounded-xl border border-slate-200 bg-white/80 p-3">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">เหตุผลที่แนะนำ</p>
              <p className="text-xs text-slate-700 leading-relaxed">{reason}</p>
            </div>

            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                <Users size={10} /> {attendees} คน
              </span>
              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                <Building2 size={10} /> ชั้น {room.floor}
              </span>
              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100">
                <CheckCircle size={10} /> จุได้ {room.capacity} คน
              </span>
            </div>

            <div className="mt-3">
              <FacilityTags facilities={room.facilities} maxShow={3} highlight={selectedEquipments} equipmentPresets={equipmentPresets} />
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between gap-2 text-[10px] text-slate-500">
          <span className="inline-flex items-center gap-1 font-semibold bg-white border border-slate-200 rounded-full px-2.5 py-1">
            <ArrowRight size={10} /> พร้อมจองต่อทันที
          </span>
          {bookingType === 'term' && (
            <span className="inline-flex items-center gap-1 font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-full px-2.5 py-1">
              ทั้งเทอม
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onSelect}
        className={`w-full ${bookingType === 'term' ? 'bg-indigo-700 hover:bg-indigo-800' : 'bg-blue-700 hover:bg-blue-800'} text-white py-3 font-bold text-sm flex items-center justify-center gap-2 shadow-sm active:scale-95 transition-all`}
      >
        <CheckCircle size={14} /> เลือกห้องนี้เพื่อจองทันที
      </button>
    </div>
  )
}

// ─── Main Layout ─────────────────────────────────────────────────────────────
function AppLayout({ step, setStep, navigate, location, bookingType, setBookingType, formProps, resultProps, confirmProps, onReset, embedded = false }) {
  const {
    attendees, setAttendees, date, setDate, startTime, setStartTime, duration, setDuration,
    building, setBuilding, buildingQuery, setBuildingQuery, endTime, loading, handleSearch, error,
    dayOfWeek, setDayOfWeek, selectedEquipments, setSelectedEquipments, equipmentPresets, buildings,
  } = formProps

  const [customDurationMode, setCustomDurationMode] = useState(!DURATIONS.some(d => d.hours === duration))
  const [customDurationInput, setCustomDurationInput] = useState(String(duration))
  const durationError = customDurationMode ? validateCustomDuration(customDurationInput, startTime) : ''

  const handleCustomDurationChange = (val) => {
    setCustomDurationInput(val)
    const err = validateCustomDuration(val, startTime)
    if (!err) setDuration(Number(val))
  }
  const { rooms, setSelectedRoom, setSplitPlan, similarRooms } = resultProps
  const { selectedRoom, title, setTitle, bookingLoading, handleBook, success, splitPlan, onCancelSplit } = confirmProps

  const isTermMode = bookingType === 'term'
  const accentBg = isTermMode ? 'from-indigo-600 to-violet-600' : 'from-blue-600 to-indigo-600'
  const accentHov = isTermMode ? 'hover:from-indigo-700 hover:to-violet-700' : 'hover:from-blue-700 hover:to-indigo-700'
  const buildingOptions = buildings.filter(b => {
    const q = (buildingQuery || '').trim().toLowerCase()
    if (!q) return true
    return String(b.label || '').toLowerCase().includes(q)
  })
  const visibleRooms = rooms
  const visibleSimilarRooms = similarRooms.slice(0, 2)
  const selectedBuildingLabel = buildings.find(b => b.code === building)?.label || 'ทั้งหมด'
  const navItems = [
    { key: 'home', icon: Home, label: 'Home', active: location === '/home', onClick: () => navigate('/home') },
    { key: 'booking', icon: CalendarDays, label: 'Booking', active: location === '/search', onClick: () => navigate('/search') },
  ]
  const chipsSummary = [
    { label: 'ประเภท', value: isTermMode ? 'ทั้งเทอม' : 'รายวัน', tone: isTermMode ? 'text-indigo-700' : 'text-blue-700' },
    { label: 'ผู้เข้าร่วม', value: `${attendees} คน` },
    { label: isTermMode ? 'วัน' : 'วันที่', value: isTermMode ? (dayOfWeek != null ? `ทุก${getDayLabel(dayOfWeek)}` : 'ยังไม่เลือก') : formatDateShort(date) },
    { label: 'เวลา', value: startTime ? `${startTime} - ${endTime || '...'}` : 'ยังไม่เลือก' },
    { label: 'อาคาร', value: selectedBuildingLabel },
    { label: 'อุปกรณ์', value: `${selectedEquipments.length} รายการ` },
  ]

  if (success) return (
    <div className="min-h-screen w-full bg-[#F8FAFC] flex items-center justify-center px-4" style={{ fontFamily: "'Inter','Prompt','Sarabun',sans-serif" }}>
      <style>{ANIM}</style>
      <div className="w-full max-w-lg rounded-[28px] border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.12)] overflow-hidden">
        <div className={`h-36 bg-gradient-to-br ${accentBg} relative overflow-hidden`}>
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.25),transparent_35%),radial-gradient(circle_at_bottom_left,rgba(255,255,255,0.16),transparent_32%)]" />
          <div className="absolute -right-8 -top-8 w-36 h-36 rounded-full bg-white/10 blur-2xl" />
          <div className="absolute left-6 top-6 w-12 h-12 rounded-2xl bg-white/15 border border-white/20 flex items-center justify-center text-white">
            <CheckCircle size={24} />
          </div>
        </div>
        <div className="p-8 -mt-10">
          <div className="rounded-[24px] bg-white border border-slate-200 shadow-sm p-6">
            <p className="text-xs font-bold uppercase tracking-[0.28em] text-slate-400 mb-2">Booking complete</p>
            <h2 className="text-2xl font-bold text-slate-900">จองสำเร็จแล้ว</h2>
            <p className={`mt-3 text-lg font-semibold ${isTermMode ? 'text-indigo-700' : 'text-blue-700'}`}>{selectedRoom?.name}</p>
            <p className="mt-2 text-sm text-slate-500">
              {isTermMode ? `ทุก${getDayLabel(dayOfWeek)} · ${startTime} - ${endTime} น.` : `${formatDate(date)} · ${startTime} - ${endTime} น.`}
            </p>
            <button
              onClick={() => navigate('/home')}
              className={`mt-6 w-full rounded-2xl py-3.5 text-sm font-bold text-white bg-gradient-to-r ${accentBg} shadow-lg shadow-blue-200/70 hover:shadow-xl transition-all`}
            >
              กลับหน้าหลัก
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  const showChrome = !embedded

  return (
    <div className="min-h-screen w-full bg-[#F8FAFC] text-slate-900 overflow-hidden" style={{ fontFamily: "'Inter','Prompt','Sarabun',sans-serif" }}>
      <style>{ANIM}</style>
      <div className="min-h-screen flex">
        {showChrome && (
        <aside className="hidden xl:flex w-24 flex-col items-center py-5 border-r border-slate-200/80 bg-white/75 backdrop-blur-xl">
          <div className="w-12 h-12 rounded-[20px] bg-gradient-to-br from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-lg shadow-blue-200">
            <LayoutDashboard size={22} />
          </div>
          <div className="mt-6 flex flex-col gap-2.5 w-full px-3">
            {navItems.map(item => {
              const Icon = item.icon
              return (
                <button
                  key={item.label}
                  type="button"
                  onClick={item.onClick}
                  className={`w-full rounded-[20px] px-3 py-3 border transition-all ${item.active ? 'bg-blue-50 border-blue-200 text-blue-700 shadow-sm' : 'bg-white border-transparent text-slate-400 hover:text-slate-700 hover:bg-slate-50'}`}
                >
                  <Icon size={22} className="mx-auto" />
                  <span className="sr-only">{item.label}</span>
                </button>
              )
            })}
          </div>
        </aside>
        )}

        <div className="flex-1 min-w-0 flex flex-col">
          {showChrome && (
          <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white">
            <div className="px-4 sm:px-6 lg:px-8 py-2.5">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-11 h-11 rounded-[18px] bg-gradient-to-br from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-lg shadow-blue-200 shrink-0">
                    <Building2 size={20} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-base font-bold leading-tight truncate">จองห้องเรียน/ประชุม</p>
                    <p className="text-xs text-slate-500 truncate">ระบบจองห้องเรียน/ประชุมออนไลน์</p>
                  </div>
                </div>

                  <div className="hidden lg:flex flex-1 justify-center">
                    <div className="flex items-center gap-2.5 rounded-full border border-slate-200 bg-white px-3.5 py-2.5 shadow-sm">
                    {[
                      { n: 1, label: 'เลือกเงื่อนไข' },
                      { n: 2, label: 'เลือกห้องประชุม' },
                      { n: 3, label: 'ยืนยันการจอง' },
                    ].map((item, index) => (
                      <div key={item.n} className="flex items-center gap-3">
                        <div className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold ${step >= item.n ? 'bg-blue-600 text-white' : 'bg-slate-50 text-slate-500'}`}>
                          <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] ${step >= item.n ? 'bg-white/15' : 'bg-white text-slate-500'}`}>{item.n}</span>
                          {item.label}
                        </div>
                        {index < 2 && <span className="w-10 h-px bg-slate-200" />}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="ml-auto flex items-center gap-2 shrink-0">
                  <button type="button" className="w-10 h-10 rounded-2xl border border-slate-200 bg-white text-slate-500 hover:text-slate-800 hover:border-slate-300 transition-colors flex items-center justify-center relative">
                    <Bell size={17} />
                    <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-rose-500" />
                  </button>
                  <button type="button" className="hidden sm:flex items-center gap-3 rounded-[20px] border border-slate-200 bg-white px-3 py-2 shadow-sm">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-slate-200 to-slate-300" />
                    <div className="text-left">
                      <p className="text-sm font-semibold leading-tight">ผู้ใช้ระบบ</p>
                      <p className="text-xs text-slate-500 leading-tight">Meeting Room</p>
                    </div>
                    <ChevronDown size={16} className="text-slate-400" />
                  </button>
                </div>
              </div>
            </div>
          </header>
          )}

          <main className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 sm:px-6 lg:px-8 py-3">
            <div className="max-w-[1600px] mx-auto w-full min-h-0">
              {error && (
                <div className="mb-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-sm au">
                  {error}
                </div>
              )}

              {step === 1 && (
                <div className="grid gap-2.5 xl:grid-cols-[minmax(0,1fr)_280px] min-h-0">
                  <div className="space-y-2.5 min-h-0">
                    <section className="rounded-2xl border border-slate-200 bg-white/85 shadow-[0_12px_30px_rgba(15,23,42,0.04)] p-2.5 au">
                      <h3 className="text-xs font-bold text-slate-500 mb-2">ประเภทการจอง</h3>
                      <BookingTypeSelector value={bookingType} onChange={v => { setBookingType(v); setDayOfWeek(null) }} />
                    </section>

                    <section className="grid gap-2.5 lg:grid-cols-2 min-h-0">
                      <div className="rounded-2xl border border-slate-200 bg-white/85 shadow-[0_12px_30px_rgba(15,23,42,0.04)] p-2.5 au1">
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <h3 className="text-xs font-bold text-slate-500">ผู้เข้าร่วม</h3>
                          <span className="text-sm font-bold text-blue-700">{attendees} คน</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50/80 px-3 py-1.5 mb-2">
                          <button onClick={() => setAttendees(Math.max(MIN_ATTENDEES, attendees - 1))} className="w-7 h-7 rounded-xl bg-white border border-slate-200 text-slate-600 hover:border-blue-200 hover:text-blue-700 transition-colors flex items-center justify-center text-lg font-light shadow-sm">−</button>
                          <p className="text-lg font-bold text-slate-900 leading-none">{attendees}</p>
                          <button onClick={() => setAttendees(attendees + 1)} className="w-7 h-7 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white hover:shadow-lg hover:shadow-blue-200 transition-all flex items-center justify-center text-lg font-light">+</button>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {ATTENDEES_PRESETS.map(n => (
                            <button key={n} onClick={() => setAttendees(n)} className={`min-w-9 rounded-full px-2 py-1 text-xs font-semibold border transition-all ${attendees === n ? 'bg-blue-600 border-blue-600 text-white shadow-sm' : 'bg-white border-slate-200 text-slate-600 hover:border-blue-300 hover:text-blue-700'}`}>
                              {n}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-slate-200 bg-white/85 shadow-[0_12px_30px_rgba(15,23,42,0.04)] p-2.5 au2">
                        <h3 className="text-xs font-bold text-slate-500 mb-2">{isTermMode ? 'วันในสัปดาห์' : 'วันที่'}</h3>
                        {isTermMode ? (
                          <div className="grid grid-cols-7 gap-1">
                            {DAYS_OF_WEEK.map(d => (
                              <button
                                key={d.value}
                                onClick={() => setDayOfWeek(d.value)}
                                className={`rounded-xl border py-1.5 text-[11px] font-semibold transition-all ${dayOfWeek === d.value ? 'bg-gradient-to-br from-blue-600 to-indigo-600 border-blue-600 text-white shadow-sm' : 'bg-white border-slate-200 text-slate-600 hover:border-blue-300 hover:bg-blue-50'}`}
                              >
                                {d.label}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <input
                            type="date"
                            value={date}
                            min={new Date().toISOString().split('T')[0]}
                            onChange={e => setDate(e.target.value)}
                            className="w-full rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                          />
                        )}
                      </div>
                    </section>

                    <section className="grid gap-2.5 lg:grid-cols-2 min-h-0">
                      <div className="rounded-2xl border border-slate-200 bg-white/85 shadow-[0_12px_30px_rgba(15,23,42,0.04)] p-2.5 au2">
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <h3 className="text-xs font-bold text-slate-500">อาคาร / ห้อง</h3>
                          <MapPin size={14} className="text-blue-600" />
                        </div>
                        <div className="relative mb-2">
                          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                          <input
                            type="text"
                            value={buildingQuery || ''}
                            onChange={e => setBuildingQuery(e.target.value)}
                            placeholder="ค้นหาอาคาร"
                            className="w-full rounded-xl border border-slate-200 bg-slate-50/80 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                          />
                        </div>
                        <div className="max-h-40 overflow-y-auto pr-1">
                          <div className="flex flex-wrap gap-1.5">
                            {buildingOptions.map(b => (
                              <button
                                key={b.code}
                                onClick={() => setBuilding(b.code)}
                                className={`rounded-full border px-2.5 py-1.5 text-xs font-semibold transition-all ${building === b.code ? 'bg-blue-600 border-blue-600 text-white shadow-sm' : 'bg-white border-slate-200 text-slate-600 hover:border-blue-300 hover:bg-blue-50'}`}
                              >
                                {b.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-2xl border border-slate-200 bg-white/85 shadow-[0_12px_30px_rgba(15,23,42,0.04)] p-2.5 au3">
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <h3 className="text-xs font-bold text-slate-500">เวลา และ ระยะเวลา</h3>
                          <Clock size={14} className="text-blue-600" />
                        </div>
                        <div className="grid grid-cols-4 gap-1">
                          {TIME_SLOTS.map(t => (
                            <button
                              key={t}
                              onClick={() => setStartTime(t)}
                              className={`rounded-lg border py-1.5 text-xs font-semibold transition-all ${startTime === t ? 'bg-gradient-to-br from-blue-600 to-indigo-600 border-blue-600 text-white shadow-sm' : 'bg-white border-slate-200 text-slate-700 hover:border-blue-300 hover:bg-blue-50'}`}
                            >
                              {t}
                            </button>
                          ))}
                        </div>
                        <div className="mt-2">
                          <div className="grid grid-cols-4 gap-1">
                            {DURATIONS.map(d => (
                              <button
                                key={d.hours}
                                onClick={() => { setCustomDurationMode(false); setDuration(d.hours) }}
                                className={`rounded-lg border py-1.5 text-xs font-semibold transition-all ${!customDurationMode && duration === d.hours ? 'bg-slate-900 border-slate-900 text-white shadow-sm' : 'bg-white border-slate-200 text-slate-700 hover:border-blue-300 hover:bg-blue-50'}`}
                              >
                                {d.label}
                              </button>
                            ))}
                            <button
                              onClick={() => { setCustomDurationMode(true); setCustomDurationInput(String(duration)) }}
                              className={`rounded-lg border py-1.5 text-xs font-semibold transition-all ${customDurationMode ? 'bg-slate-900 border-slate-900 text-white shadow-sm' : 'bg-white border-slate-200 text-slate-700 hover:border-blue-300 hover:bg-blue-50'}`}
                            >
                              กำหนดเอง
                            </button>
                          </div>
                          {customDurationMode && (
                            <div className="mt-2">
                              <div className="flex items-center gap-2">
                                <input
                                  type="number"
                                  min={1}
                                  step={1}
                                  value={customDurationInput}
                                  onChange={e => handleCustomDurationChange(e.target.value)}
                                  placeholder="จำนวนชั่วโมง"
                                  className={`w-full rounded-lg border px-3 py-1.5 text-xs font-semibold outline-none transition-all ${durationError ? 'border-red-300 bg-red-50 text-red-700' : 'border-slate-200 bg-white text-slate-700 focus:border-blue-400'}`}
                                />
                                <span className="text-xs text-slate-500 whitespace-nowrap">ชั่วโมง</span>
                              </div>
                              {durationError && (
                                <p className="mt-1 text-[11px] text-red-600">{durationError}</p>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </section>

                    <section className="rounded-2xl border border-slate-200 bg-white/85 shadow-[0_12px_30px_rgba(15,23,42,0.04)] p-2.5 au3 min-h-0">
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <h3 className="text-xs font-bold text-slate-500">อุปกรณ์ที่ต้องการ</h3>
                        {selectedEquipments.length > 0 && (
                          <button onClick={() => setSelectedEquipments([])} className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-1 text-xs font-semibold text-rose-600 hover:bg-rose-100 transition-colors">
                            <RefreshCw size={11} /> ล้างทั้งหมด
                          </button>
                        )}
                      </div>
                      <EquipmentSelector selected={selectedEquipments} onChange={setSelectedEquipments} equipmentPresets={equipmentPresets} />
                    </section>
                  </div>

                  <aside className="xl:sticky xl:top-24 h-fit self-start">
                      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_16px_50px_rgba(15,23,42,0.06)]">
                      <div className={`relative overflow-hidden bg-gradient-to-br ${accentBg} px-3 py-2.5 text-white`}>
                        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.20),transparent_34%),radial-gradient(circle_at_bottom_left,rgba(255,255,255,0.14),transparent_32%)]" />
                        <div className="relative flex items-center justify-between gap-2">
                          <h3 className="text-sm font-bold">สรุปการค้นหา</h3>
                          <CalendarDays size={16} className="opacity-80" />
                        </div>
                      </div>

                      <div className="p-2.5">
                        <div className="space-y-1">
                          {chipsSummary.map(item => (
                            <div key={item.label} className="flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50/80 px-2.5 py-1">
                              <span className="text-xs text-slate-500">{item.label}</span>
                              <span className={`text-xs font-semibold text-right ${item.tone || 'text-slate-900'} truncate`}>{item.value}</span>
                            </div>
                          ))}
                        </div>

                        {selectedEquipments.length > 0 && (
                            <div className="mt-2 rounded-xl border border-slate-200 bg-white p-2">
                            <p className="mb-1.5 text-xs font-semibold text-slate-700">อุปกรณ์ที่เลือก</p>
                            <div className="flex flex-wrap gap-1">
                              {selectedEquipments.map(k => {
                                const eq = findPreset(equipmentPresets, k)
                                return (
                                  <span key={k} className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700">
                                    {eq?.icon} {eq?.shortLabel || eq?.label}
                                  </span>
                                )
                              })}
                            </div>
                          </div>
                        )}

                        <div className="mt-2 space-y-1.5">
                          <button
                            onClick={handleSearch}
                            disabled={loading || !!durationError}
                            className={`w-full rounded-xl bg-gradient-to-r ${accentBg} px-3 py-2.5 text-sm font-bold text-white shadow-md shadow-blue-200 transition-all ${accentHov} disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none flex items-center justify-center gap-2`}
                          >
                            {loading ? <><div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" /> กำลังค้นหา...</> : <><Search size={15} /> ค้นหาห้องว่าง</>}
                          </button>
                          <button
                            type="button"
                            onClick={onReset}
                            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300 hover:bg-slate-50 transition-colors flex items-center justify-center gap-2"
                          >
                            <RefreshCw size={14} /> Reset filters
                          </button>
                        </div>
                      </div>
                    </div>
                  </aside>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-3 min-h-0">
                  <div className={`rounded-[26px] bg-gradient-to-r ${accentBg} p-3.5 sm:p-4 text-white shadow-xl shadow-blue-200/60`}>
                    <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      <span className="rounded-full bg-white/15 px-3 py-1.5">{attendees} คน</span>
                      <span className="rounded-full bg-white/15 px-3 py-1.5">{isTermMode ? `ทุก${getDayLabel(dayOfWeek)}` : formatDateShort(date)}</span>
                      <span className="rounded-full bg-white/15 px-3 py-1.5">{startTime} - {endTime}</span>
                      {selectedEquipments.length > 0 && <span className="rounded-full bg-white/15 px-3 py-1.5">{selectedEquipments.length} อุปกรณ์</span>}
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xl font-bold">ผลการค้นหาห้องว่าง</p>
                        <p className="text-sm text-white/75">แตะห้องที่ต้องการเพื่อยืนยันการจอง</p>
                      </div>
                      <button onClick={() => setStep(1)} className="rounded-2xl bg-white/15 px-4 py-2.5 text-sm font-semibold hover:bg-white/25 transition-colors">
                        แก้ไขเงื่อนไข
                      </button>
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px] min-h-0">
                    <div className="space-y-3 min-h-0 xl:order-1">
                      {rooms.length === 0 ? (
                        <div className="rounded-[28px] border border-slate-200 bg-white shadow-sm p-5 text-center">
                          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                            <Sparkles size={28} />
                          </div>
                          <h3 className="text-xl font-bold text-slate-900">ไม่พบห้องตรงเงื่อนไข</h3>
                          <p className="mt-2 text-sm text-slate-500">ลองปรับเวลา อาคาร หรือจำนวนผู้เข้าร่วม แล้วค้นหาใหม่อีกครั้ง</p>
                          {similarRooms.length > 0 && <p className="mt-4 text-xs text-slate-400">ระบบมีแผนสองด้านล่างให้เลือก</p>}
                        </div>
                      ) : (
                        visibleRooms.map((room, index) => (
                          <RoomCard
                            key={room.id}
                            room={room}
                            isTermMode={isTermMode}
                            selectedEquipments={selectedEquipments}
                            equipmentPresets={equipmentPresets}
                            isBest={index === 0}
                            onClick={() => { setSplitPlan(null); setSelectedRoom(room); setStep(3) }}
                          />
                        ))
                      )}
                      {rooms.length > visibleRooms.length && (
                        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center text-xs text-slate-500 shadow-sm">
                          แสดง {visibleRooms.length} จากทั้งหมด {rooms.length} ห้อง
                        </div>
                      )}

                      {rooms.length === 0 && visibleSimilarRooms.length > 0 && (
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="text-lg font-bold text-slate-900">แผนสอง</p>
                              <p className="text-sm text-slate-500">ห้องใกล้เคียงที่พร้อมจอง</p>
                            </div>
                            <span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">{similarRooms.length} ตัวเลือก</span>
                          </div>
                          {visibleSimilarRooms.map(room => (
                            <SuggestedRoomCard
                              key={room.id}
                              room={room}
                              bookingType={bookingType}
                              attendees={attendees}
                              selectedEquipments={selectedEquipments}
                              equipmentPresets={equipmentPresets}
                              onSelect={() => {
                                setSplitPlan(null); setSelectedRoom(room); setTitle('')
                                // แผนสองบางใบแนะนำห้องเดิมแต่คนละวัน (suggested_date) —
                                // ต้องอัปเดตวันที่จองให้ตรงกับวันที่ห้องว่างจริง ไม่งั้น
                                // ฟอร์มยืนยันจะยังพยายามจองวันเดิมที่ห้องไม่ว่างอยู่ดี
                                if (room.suggested_date) setDate(room.suggested_date)
                                setStep(3)
                              }}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="rounded-[22px] border border-slate-200 bg-white/85 shadow-[0_18px_50px_rgba(15,23,42,0.05)] overflow-hidden au3 xl:order-2">
                      <div className="px-4 py-2 border-b border-slate-100 bg-gradient-to-r from-blue-50 via-white to-indigo-50">
                        <p className="text-[10px] font-bold uppercase tracking-[0.28em] text-slate-400 mb-1">Summary</p>
                        <h2 className="text-base font-bold text-slate-900">สรุปการค้นหา</h2>
                        <p className="mt-0.5 text-xs text-slate-500">ตรวจสอบเงื่อนไขก่อนค้นหาห้องว่าง</p>
                      </div>
                      <div className="p-3">
                        <SummaryTiles rooms={rooms} />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {step === 3 && (splitPlan || selectedRoom) && (() => {
                if (splitPlan) {
                  const fh = splitPlan.first_half; const sh = splitPlan.second_half
                  return (
                    <div className="max-w-3xl mx-auto">
                      <button type="button" onClick={onCancelSplit} className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-blue-700">
                        <ArrowLeft size={14} /> กลับเลือกแผนอื่น
                      </button>
                      <div className="rounded-[28px] border border-slate-200 bg-white shadow-sm p-6 sm:p-7">
                        <SectionLabel icon={BookOpen}>ยืนยันจองสลับห้อง (2 ช่วง)</SectionLabel>
                        <div className="grid gap-4 sm:grid-cols-2">
                          <div className="rounded-2xl border border-violet-100 bg-violet-50 p-4">
                            <p className="text-xs font-bold text-violet-700 mb-1">เทอมแรก</p>
                            <p className="text-base font-bold text-slate-900 truncate">{fh.room_name}</p>
                            <p className="text-xs text-slate-500 mt-1">{formatDateShort(fh.term_start)} - {formatDateShort(fh.term_end)}</p>
                          </div>
                          <div className="rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
                            <p className="text-xs font-bold text-indigo-700 mb-1">เทอมหลัง</p>
                            <p className="text-base font-bold text-slate-900 truncate">{sh.room_name}</p>
                            <p className="text-xs text-slate-500 mt-1">{formatDateShort(sh.term_start)} - {formatDateShort(sh.term_end)}</p>
                          </div>
                        </div>
                        <label className="mt-5 block text-sm font-semibold text-slate-700 mb-2">ชื่อวิชา / กิจกรรม *</label>
                        <input
                          type="text"
                          autoFocus
                          value={title}
                          onChange={e => setTitle(e.target.value)}
                          placeholder="เช่น วิชา CS101"
                          className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-base outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                        />
                        <button
                          type="button"
                          onClick={handleBook}
                          disabled={bookingLoading || !title.trim()}
                          className={`mt-5 w-full rounded-2xl bg-gradient-to-r ${accentBg} px-4 py-4 text-base font-bold text-white shadow-lg shadow-blue-200 disabled:bg-slate-300 disabled:shadow-none`}
                        >
                          {bookingLoading ? 'กำลังจอง...' : 'ยืนยันจองทั้ง 2 ช่วง'}
                        </button>
                      </div>
                    </div>
                  )
                }

                const demandLevel = getDemandLevel(selectedRoom)
                const demandCfg = FORECAST_CONFIG[demandLevel]
                return (
                  <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
                    <div className="rounded-[28px] border border-slate-200 bg-white shadow-sm p-5 sm:p-6 space-y-3.5">
                      <div className="flex items-center justify-between gap-3">
                        <SectionLabel icon={Building2}>รายละเอียดห้อง</SectionLabel>
                        <RoomStatusBadge status={selectedRoom.status} />
                      </div>
                      <div>
                        <h2 className="text-2xl font-bold text-slate-900 break-words">{selectedRoom.name}</h2>
                        <p className="mt-1 text-sm text-slate-500">{selectedRoom.building_name} · ชั้น {selectedRoom.floor} · {selectedRoom.room_type}</p>
                      </div>
                      {demandLevel !== 'none' && (
                        <div className={`flex items-center gap-2.5 rounded-2xl px-4 py-3 ${demandCfg.cardBg} border ${demandCfg.cardBorder}`}>
                          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: demandCfg.dotColor }} />
                          <div className="min-w-0">
                            <p className={`text-sm font-bold ${demandCfg.textCls}`}>{demandCfg.badge}</p>
                            {demandCfg.sub && <p className={`text-xs ${demandCfg.subCls}`}>{demandCfg.sub}</p>}
                          </div>
                        </div>
                      )}
                      <div className="grid gap-2.5 rounded-[24px] border border-slate-200 bg-slate-50 p-3.5 text-sm">
                        <div className="flex justify-between gap-4"><span className="text-slate-500">ประเภท</span><span className="font-semibold text-slate-900">{isTermMode ? 'จองทั้งเทอม' : 'จองรายวัน'}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-slate-500">วัน/วันที่</span><span className="font-semibold text-slate-900">{isTermMode ? `ทุก${getDayLabel(dayOfWeek)}` : formatDate(date)}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-slate-500">เวลา</span><span className="font-semibold text-slate-900">{startTime} - {endTime} น.</span></div>
                        <div className="flex justify-between gap-4"><span className="text-slate-500">ผู้เข้าร่วม</span><span className="font-semibold text-slate-900">{attendees} คน (ความจุ {selectedRoom.capacity})</span></div>
                      </div>
                      {selectedRoom.facilities?.length > 0 && (
                        <div>
                          <p className="mb-3 text-xs font-bold uppercase tracking-[0.24em] text-slate-400">อุปกรณ์ในห้อง</p>
                          <FacilityTags facilities={selectedRoom.facilities} maxShow={8} highlight={selectedEquipments} equipmentPresets={equipmentPresets} />
                        </div>
                      )}
                    </div>

                      <div className="space-y-4">
                      <CheckInReminder startTime={startTime} />
                      <div className="rounded-[28px] border border-slate-200 bg-white shadow-sm p-5 sm:p-6">
                        <SectionLabel>{isTermMode ? 'ชื่อวิชา / กิจกรรม' : 'หัวข้อการประชุม'}</SectionLabel>
                        <input
                          type="text"
                          autoFocus
                          placeholder={isTermMode ? 'เช่น วิชา CS101' : 'เช่น ประชุมกลุ่ม'}
                          value={title}
                          onChange={e => setTitle(e.target.value)}
                          className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-base outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                        />
                        <button
                          onClick={handleBook}
                          disabled={bookingLoading}
                          className={`mt-4 flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r ${accentBg} px-4 py-3.5 text-base font-bold text-white shadow-lg shadow-blue-200 transition-all active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none`}
                        >
                          {bookingLoading
                            ? <><div className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-white/30 border-t-white" /> กำลังจอง...</>
                            : <><CheckCircle size={18} className="shrink-0" /> ยืนยันการจอง</>}
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })()}
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}

// ─── Root Component ──────────────────────────────────────────────────────────
export default function SearchPage({ embedded = false }) {
  const navigate = useNavigate()
  const location = useLocation()
  const searchState = location.state || {}
  const [step, setStep] = useState(1)
  const [bookingType, setBookingType] = useState('daily')
  const [attendees, setAttendees] = useState(MIN_ATTENDEES)
  const [date, setDate] = useState(new Date().toISOString().split('T')[0])
  const [dayOfWeek, setDayOfWeek] = useState(null)
  const [startTime, setStartTime] = useState('')
  const [duration, setDuration] = useState(1)
  const [building, setBuilding] = useState('')
  const [buildingQuery, setBuildingQuery] = useState('')
  const [rooms, setRooms] = useState([])
  const [selectedRoom, setSelectedRoom] = useState(null)
  const [title, setTitle] = useState('')
  const [loading, setLoading] = useState(false)
  const [buildings, setBuildings] = useState(DEFAULT_BUILDINGS)
  const [bookingLoading, setBookingLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  const _initYear = getDefaultAcademicYearBE()
  const _initTerm = getDefaultTermNumber()
  const _initDates = getTermDateRange(_initYear, _initTerm)
  const [academicYearBE, setAcademicYearBE] = useState(_initYear)
  const [termNumber, setTermNumber] = useState(_initTerm)
  const [termStart, setTermStart] = useState(_initDates.start)
  const [termEnd, setTermEnd] = useState(_initDates.end)
  const [termName, setTermName] = useState(buildTermName(_initYear, _initTerm))
  const [selectedEquipments, setSelectedEquipments] = useState([])
  const [similarRooms, setSimilarRooms] = useState([])
  const [splitPlan, setSplitPlan] = useState(null)
  const [equipmentPresets, setEquipmentPresets] = useState(FALLBACK_EQUIPMENT_PRESETS)

  const onCancelSplit = () => { setSplitPlan(null); setStep(2) }
  const handleReset = () => {
    setStep(1)
    setBookingType('daily')
    setAttendees(5)
    setDate(new Date().toISOString().split('T')[0])
    setDayOfWeek(null)
    setStartTime('')
    setDuration(1)
    setBuilding('')
    setBuildingQuery('')
    setRooms([])
    setSelectedRoom(null)
    setTitle('')
    setSelectedEquipments([])
    setSimilarRooms([])
    setSplitPlan(null)
    setError('')
  }

  useEffect(() => {
    api.get('rooms/equipment-filters/').then(res => {
      if (res.data?.filters?.length) setEquipmentPresets(res.data.filters)
    }).catch(() => {})
  }, [])

  // wizard นี้เปลี่ยนหน้าจอด้วย step/success state ไม่ใช่เปลี่ยน route — พอ
  // เนื้อหาแต่ละขั้นสูงไม่เท่ากัน ถ้าไม่รีเซ็ต scroll เอง จอจะ "ค้าง"
  // ตำแหน่งเดิมจากขั้นก่อนหน้า ดูเหมือนกระโดดไปอยู่ท้ายหน้าตอนกดยืนยัน
  // (กดยืนยันจอง → success เปลี่ยนเป็น true โดย step ยังเป็น 3 เหมือนเดิม)
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [step, success])

  useEffect(() => {
    // bookable_only: จำกัดตัวเลือกอาคารให้เหลือแค่อาคารที่มีห้องพยากรณ์ AI จริงให้
    // จอง — ไม่งั้น admin ที่เข้ามาจองห้องจริง (ไม่ใช่จัดการ inventory) จะเห็น
    // อาคารที่ไม่มีห้องให้จองเลยสักห้องปนอยู่ด้วย
    api.get('buildings/', { params: { bookable_only: 'true' } }).then(res => {
      const data = res.data?.results ?? res.data ?? []
      setBuildings([{ code: '', label: 'ทั้งหมด' }, ...data.map(b => ({ code: b.code || b.id, label: b.name }))])
    }).catch(() => {})
  }, [])

  useEffect(() => {
    let active = true

    const applyQuickRoom = async () => {
      const quickRoom = searchState.quickRoom
      const quickSearch = (searchState.quickSearch || '').trim()

      if (!quickRoom && !quickSearch) return

      const suggestedRoom = quickRoom || await (async () => {
        try {
          const res = await api.get('/rooms/suggestions/', {
            params: { q: quickSearch, limit: 1 },
          })
          const suggestions = Array.isArray(res.data) ? res.data : []
          return suggestions[0] || null
        } catch {
          return null
        }
      })()

      if (!active || !suggestedRoom) return

      // /rooms/suggestions/ (and quickRoom, which comes from the same
      // lightweight endpoint) only returns id/name/building/floor/capacity —
      // no facilities/image/description. Re-fetch the full room record so
      // step 3 shows real data instead of silently dropping those sections.
      const resolvedRoom = await (async () => {
        if (!suggestedRoom.id) return suggestedRoom
        try {
          const res = await api.get(`/rooms/${suggestedRoom.id}/`)
          return res.data || suggestedRoom
        } catch {
          return suggestedRoom
        }
      })()

      if (!active || !resolvedRoom) return

      setRooms([resolvedRoom])
      setSimilarRooms([])
      setSplitPlan(null)
      setSelectedRoom(resolvedRoom)
      setStep(3)
      if (resolvedRoom.building_code !== undefined) {
        setBuilding(resolvedRoom.building_code || '')
      }
      // มาจากฟีด "ห้องว่างตอนนี้" ในหน้าแรก — ตั้งเวลาเริ่มให้ตรงกับตอนนี้แทนที่
      // จะปล่อยว่าง (ค่าเริ่มต้นของ startTime คือ '' ซึ่งจองต่อไม่ได้จนกว่าจะกรอกเอง)
      if (searchState.quickStartTime) setStartTime(searchState.quickStartTime)
    }

    applyQuickRoom()
    return () => { active = false }
  }, [searchState.quickRoom, searchState.quickSearch, searchState.quickStartTime])

  const endTime = startTime ? addHours(startTime, duration) : ''

  const applyAcademicTerm = (yearBE, termNum) => {
    const { start, end } = getTermDateRange(yearBE, termNum)
    setAcademicYearBE(yearBE); setTermNumber(termNum); setTermStart(start); setTermEnd(end)
    setTermName(buildTermName(yearBE, termNum))
  }

  useEffect(() => { if (bookingType === 'term') applyAcademicTerm(getDefaultAcademicYearBE(), getDefaultTermNumber()) }, [bookingType])

  const fetchSimilarRooms = async (basePayload) => {
    if (bookingType === 'daily') {
      try {
        const recRes = await api.post('/rooms/dynamic-recommend/', basePayload)
        return (Array.isArray(recRes.data?.suggestions) ? recRes.data.suggestions : []).slice(0, 3)
      } catch {
        return []
      }
    }

    try {
      const fallbackPayload = {
        ...basePayload,
        attendees: 1,
        building_code: undefined,
      }
      const recRes = await api.post('/rooms/search/', fallbackPayload)
      const candidates = Array.isArray(recRes.data) ? recRes.data : []
      return candidates
        .filter(room => Number(room.capacity) >= attendees)
        .map(room => {
          const { score, reason } = scoreFallbackRoom(room, {
            attendees,
            building,
            bookingType,
            selectedEquipments,
            equipmentPresets,
          })
          return {
            ...room,
            is_similar_recommendation: true,
            recommendation_score: score,
            recommendation_reason: reason,
          }
        })
        .filter(room => bookingType !== 'term' || isClassroomType(room))
        .sort((a, b) => (b.recommendation_score || 0) - (a.recommendation_score || 0) || (a.capacity - b.capacity))
        .slice(0, 3)
    } catch {
      return []
    }
  }

  const fetchSplitRecommendation = async (basePayload) => {
    if (bookingType !== 'term') return null
    try {
      const res = await api.post('term-bookings/split-recommend/', basePayload)
      return res.data || null
    } catch {
      return null
    }
  }

  const handleSearch = async () => {
    if (!startTime) { setError('กรุณาเลือกเวลาเริ่มต้น'); return }
    if (bookingType === 'term' && dayOfWeek == null) { setError('กรุณาเลือกวันในสัปดาห์'); return }
    if (bookingType === 'daily' && !date) { setError('กรุณาเลือกวันที่'); return }
    setError(''); setLoading(true)
    try {
      const payload = {
        attendees, start_time: startTime, end_time: endTime, building_code: building || undefined,
        booking_type: bookingType === 'term' ? 'term' : 'dynamic',
        ...(bookingType === 'term' ? { day_of_week: dayOfWeek, term_start: termStart, term_end: termEnd, term_name: termName || buildTermName(academicYearBE, termNumber) } : { date })
      }
      const res = await api.post('/rooms/search/', payload)
      const roomsData = Array.isArray(res.data) ? res.data : []
      // ห้องที่มีจริงตอนนี้ล้วนความจุใหญ่ (31-61 คน) ไม่มีห้องเล็ก — เดิมมี upper-bound
      // buffer กันไม่ให้จับคู่ห้องใหญ่เกินไป แต่กับชุดห้องนี้มันตัดออกจนไม่เจอห้องเลย
      // เอาแค่ "ห้องต้องจุพอ" พอ ไม่ต้องกังวลเรื่องห้องใหญ่เกินความจำเป็นอีกต่อไป
      let filtered = roomsData.filter(r => r.capacity >= attendees)
      if (bookingType === 'term') filtered = filtered.filter(r => isClassroomType(r))
      if (selectedEquipments.length > 0) filtered = filtered.filter(r => roomHasEquipments(r, selectedEquipments, equipmentPresets))
      // building_code from the backend is only a soft ordering hint (preferred
      // building first, then every other room) — the chip UI looks/behaves
      // like the equipment filter above, which does hard-exclude, so users
      // pick a building expecting only that building's rooms. Make it match.
      if (building) filtered = filtered.filter(r => r.building_code === building)

      filtered = filtered
        .map(room => ({ ...room, suitability_score: scoreFallbackRoom(room, { attendees, building, bookingType, selectedEquipments, equipmentPresets }).score }))
        .sort((a, b) => b.suitability_score - a.suitability_score || a.capacity - b.capacity)

      if (bookingType === 'term' && filtered.length === 0) {
        const splitRec = await fetchSplitRecommendation(payload)
        if (splitRec?.recommended_split?.first_half && splitRec?.recommended_split?.second_half) {
          setRooms([])
          setSimilarRooms([])
          setSplitPlan(splitRec.recommended_split)
          setStep(3)
          return
        }
      }

      const similar = filtered.length === 0 ? await fetchSimilarRooms(payload) : []

      setRooms(filtered); setSimilarRooms(similar); setSplitPlan(null)
      setStep(2)
    } catch (err) {
      setError('เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง')
    } finally {
      setLoading(false)
    }
  }

  const handleBook = async () => {
    if (!splitPlan && !selectedRoom) { setError('ไม่พบห้องที่เลือก'); return }
    if (!title.trim()) { setError('กรุณากรอกชื่อวิชา / กิจกรรม'); return }
    setBookingLoading(true); setError('')
    try {
      let response
      if (bookingType === 'term' && splitPlan) {
        response = await api.post('term-bookings/split-book/', {
          subject_name: title.trim(), attendees: parseInt(attendees, 10), day_of_week: dayOfWeek,
          start_time: startTime, end_time: endTime, term_name: termName,
          first_room_id: splitPlan.first_half.room_id, first_term_start: splitPlan.first_half.term_start, first_term_end: splitPlan.first_half.term_end,
          second_room_id: splitPlan.second_half.room_id, second_term_start: splitPlan.second_half.term_start, second_term_end: splitPlan.second_half.term_end,
        })
        setSplitPlan(null)
      } else if (bookingType === 'term') {
        response = await api.post('term-bookings/', { room: selectedRoom.id, subject_name: title, attendees: parseInt(attendees), day_of_week: dayOfWeek, start_time: startTime, end_time: endTime, term_start: termStart, term_end: termEnd, term_name: termName })
      } else {
        response = await api.post('bookings/', { room: selectedRoom.id, title: title, attendees: parseInt(attendees), start_time: `${date}T${startTime}:00`, end_time: `${date}T${endTime}:00` })
      }
      if (response.status === 201 || response.status === 200) setSuccess(true)
      else setError('จองไม่สำเร็จ กรุณาลองใหม่')
    } catch (err) {
      setError(err.response?.data ? JSON.stringify(err.response.data) : 'เกิดข้อผิดพลาด กรุณาลองใหม่')
    } finally {
      setBookingLoading(false)
    }
  }

  return (
    <AppLayout
      step={step} setStep={setStep} navigate={navigate} location={location.pathname}
      bookingType={bookingType} setBookingType={setBookingType}
      formProps={{ attendees, setAttendees, date, setDate, startTime, setStartTime, duration, setDuration, building, setBuilding, buildingQuery, setBuildingQuery, endTime, loading, handleSearch, error, dayOfWeek, setDayOfWeek, selectedEquipments, setSelectedEquipments, equipmentPresets, buildings }}
      resultProps={{ rooms, setSelectedRoom, setSplitPlan, similarRooms }}
      confirmProps={{ selectedRoom, title, setTitle, bookingLoading, handleBook, success, splitPlan, onCancelSplit }}
      onReset={handleReset}
      embedded={embedded}
    />
  )
}
