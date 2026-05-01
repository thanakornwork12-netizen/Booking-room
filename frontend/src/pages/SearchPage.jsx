import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, CheckCircle, Building2, ChevronRight,
  Search, Clock, Users, Calendar, MapPin, Zap,
  AlertTriangle, BookOpen, Coffee, Filter, X,
} from 'lucide-react'
import api from '../api/axios'

// ─── Constants ───────────────────────────────────────────────────────────────

const BUILDINGS = [
  { code: '',     label: 'ทั้งหมด' },
  { code: 'LIB',  label: 'ห้องสมุด' },
  { code: 'SC',   label: 'วิทยาศาสตร์' },
  { code: 'EN',   label: 'วิศวกรรม' },
  { code: 'MAIN', label: 'สำนักงาน' },
]
const TIME_SLOTS = ['08:00','09:00','10:00','11:00','13:00','14:00','15:00','16:00']
const DURATIONS  = [{ label: '1 ชม.', hours: 1 },{ label: '2 ชม.', hours: 2 },{ label: '3 ชม.', hours: 3 }]
const ATTENDEES_PRESETS = [2, 5, 10, 20, 30, 50]
const CAPACITY_BUFFER   = 10

const TERM_ALLOWED_TYPES = ['ห้องเรียน', 'ห้อง lecture', 'ห้อง Lecture', 'classroom', 'lecture', 'Lecture Hall', 'lecture_hall']

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
    badge: 'รีบจองด่วนที่สุด!', sub: 'โอกาสสุดท้ายก่อนเต็ม',
    badgeCls: 'bg-red-50 text-red-700 border border-red-200',
    dotColor: '#dc2626', pillCls: 'bg-red-50 border border-red-200',
    textCls: 'text-red-700', subCls: 'text-red-500',
    cardBg: 'bg-red-50', cardBorder: 'border-red-200', numCls: 'text-red-600',
    scoreLabel: '≥ 0.70',
  },
  high: {
    badge: 'รีบจองด่วน!', sub: 'เริ่มเป็นที่ต้องการสูง',
    badgeCls: 'bg-orange-50 text-orange-700 border border-orange-200',
    dotColor: '#f97316', pillCls: 'bg-orange-50 border border-orange-200',
    textCls: 'text-orange-700', subCls: 'text-orange-500',
    cardBg: 'bg-orange-50', cardBorder: 'border-orange-200', numCls: 'text-orange-600',
    scoreLabel: '0.50–0.69',
  },
  medium: {
    badge: 'ควรจองตอนนี้', sub: 'เริ่มมีคนสนใจห้องนี้',
    badgeCls: 'bg-yellow-50 text-yellow-800 border border-yellow-300',
    dotColor: '#f59e0b', pillCls: 'bg-yellow-50 border border-yellow-300',
    textCls: 'text-yellow-800', subCls: 'text-yellow-600',
    cardBg: 'bg-yellow-50', cardBorder: 'border-yellow-200', numCls: 'text-yellow-600',
    scoreLabel: '0.30–0.49',
  },
  low: {
    badge: 'ยังว่างอยู่', sub: 'ห้องว่าง พร้อมใช้งาน',
    badgeCls: 'bg-blue-50 text-blue-700 border border-blue-200',
    dotColor: '#2563eb', pillCls: 'bg-blue-50 border border-blue-200',
    textCls: 'text-blue-700', subCls: 'text-blue-500',
    cardBg: 'bg-blue-50', cardBorder: 'border-blue-200', numCls: 'text-blue-600',
    scoreLabel: '< 0.30',
  },
  none: {
    badge: '—', sub: '',
    badgeCls: 'bg-gray-100 text-gray-500 border border-gray-200',
    dotColor: '#cbd5e1', pillCls: 'bg-gray-50 border border-gray-200',
    textCls: 'text-gray-500', subCls: 'text-gray-400',
    cardBg: 'bg-gray-50', cardBorder: 'border-gray-200', numCls: 'text-gray-500',
    scoreLabel: '',
  },
}

const SUMMARY_TIERS = [
  { level: 'urgent', label: 'รีบจองด่วนที่สุด!' },
  { level: 'high',   label: 'รีบจองด่วน!'       },
  { level: 'medium', label: 'ควรจองตอนนี้'       },
  { level: 'low',    label: 'ยังว่างอยู่'         },
]

// ─── Equipment Presets ───────────────────────────────────────────────────────
const EQUIPMENT_PRESETS = [
  { key: 'projector',   label: 'โปรเจกเตอร์',  icon: '📽️', keywords: ['โปรเจกเตอร์'] },
  { key: 'whiteboard',  label: 'ไวท์บอร์ด',    icon: '📋', keywords: ['ไวท์บอร์ด', 'กระดานไวท์บอร์ด'] },
  { key: 'sound',       label: 'ระบบเสียง',     icon: '🔊', keywords: ['ระบบเสียง', 'ลำโพง', 'เสียง'] },
  { key: 'mic',         label: 'ไมโครโฟน',      icon: '🎤', keywords: ['ไมโครโฟน', 'ไมค์', 'ไมโคร', 'ไมโครโฟนไร้สาย'] },
  { key: 'ac',          label: 'แอร์',           icon: '❄️', keywords: ['ปรับอากาศ', 'แอร์', 'เครื่องปรับอากาศ'] },
  { key: 'tv',          label: 'TV/จอแสดงผล',   icon: '📺', keywords: ['TV', 'จอแสดงผล', 'จอรับภาพ', 'TV / จอแสดงผล'] },
  { key: 'computer',    label: 'คอมพิวเตอร์',   icon: '💻', keywords: ['คอมพิวเตอร์'] },
  { key: 'camera',      label: 'กล้องวิดีโอ',   icon: '📹', keywords: ['กล้อง', 'กล้องบันทึกการสอน', 'กล้องวิดีโอคอนเฟอเรนซ์'] },
  { key: 'smartboard',  label: 'Smart Board',   icon: '🖊️', keywords: ['Smart Board', 'กระดาน Smart', 'Smart'] },
  { key: 'wifi',        label: 'WiFi',           icon: '📶', keywords: ['WiFi', 'wifi'] },
]

// ─── Facility Icons ──────────────────────────────────────────────────────────

const FAC_ICONS = {
  'โปรเจกเตอร์':                    '📽️',
  'จอรับภาพ':                       '🖥️',
  'ไวท์บอร์ด':                      '📋',
  'กระดานไวท์บอร์ด':                '📋',
  'ระบบเสียง':                      '🔊',
  'ไมโครโฟน':                       '🎤',
  'ไมโครโฟนไร้สาย':                 '🎤',
  'เครื่องปรับอากาศ':               '❄️',
  'WiFi':                           '📶',
  'เต้าเสียบไฟฟ้า':                 '🔌',
  'TV / จอแสดงผล':                  '📺',
  'คอมพิวเตอร์ (สำหรับผู้นำเสนอ)':  '💻',
  'คอมพิวเตอร์ (สำหรับผู้สอน)':     '💻',
  'กล้องวิดีโอคอนเฟอเรนซ์':         '📹',
  'กล้องบันทึกการสอน':              '📹',
  'กระดาน Smart Board':             '🖊️',
  'Smart Board':                    '🖊️',
  'เครื่องพิมพ์เอกสาร':             '🖨️',
  'ตู้เก็บเอกสาร':                  '🗄️',
  'ตู้เก็บอุปกรณ์การสอน':           '🗄️',
  'ม่านบังแสง':                     '🪟',
  'นาฬิกาแขวน':                     '🕐',
  'โพเดียม / แท่นบรรยาย':           '🎙️',
  'จอแสดงผลเสริม (ด้านข้าง)':       '🖥️',
  'ระบบ LMS (จอควบคุม)':            '🖥️',
}

const getFacIcon = (name) => {
  if (FAC_ICONS[name]) return FAC_ICONS[name]
  if (name.includes('คอมพิวเตอร์')) return '💻'
  if (name.includes('จอ') || name.includes('TV')) return '🖥️'
  if (name.includes('กล้อง')) return '📹'
  if (name.includes('ไมค์') || name.includes('ไมโคร')) return '🎤'
  if (name.includes('เสียง') || name.includes('ลำโพง')) return '🔊'
  if (name.includes('ปรับอากาศ')) return '❄️'
  return '🔧'
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const addHours = (time, hours) => {
  const [h, m] = time.split(':').map(Number)
  return `${String(h + hours).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
const formatDate = d => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
})
const formatDateShort = d => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', {
  day: 'numeric', month: 'short',
})

const getDemandLevel = room => {
  const raw = room.forecast?.demand_level
  const availMap = {
    book_now: 'urgent',
    book_soon: 'high',
    recommended: 'medium',
    likely_available: 'low',
  }
  if (raw && availMap[raw]) return availMap[raw]
  if (raw && FORECAST_CONFIG[raw]) return raw
  return 'none'
}

const getDayLabel = v => DAYS_OF_WEEK.find(d => d.value === v)?.full ?? ''

const isClassroomType = room => {
  if (!room.room_type) return false
  const t = room.room_type.toLowerCase().trim()
  return (
    t.includes('ห้องเรียน') ||
    t.includes('lecture') ||
    t.includes('classroom') ||
    t.includes('เรียน')
  )
}

// ─── Equipment filter helper ──────────────────────────────────────────────────
// คืน true ถ้าห้องมีอุปกรณ์ที่ผู้ใช้เลือก *อย่างน้อยหนึ่งชื่อ* ต่อหนึ่ง preset key
// (ห้องสามารถมีอุปกรณ์อื่นๆ ปนมาได้)
const roomHasEquipments = (room, selectedEquipments) => {
  if (!selectedEquipments || selectedEquipments.length === 0) return true
  if (!room.facilities || room.facilities.length === 0) return false

  const facilityNames = room.facilities.map(f => f.name.toLowerCase())

  return selectedEquipments.every(key => {
    const preset = EQUIPMENT_PRESETS.find(p => p.key === key)
    if (!preset) return true
    return preset.keywords.some(kw =>
      facilityNames.some(fn => fn.includes(kw.toLowerCase()))
    )
  })
}

// ─── Animations ──────────────────────────────────────────────────────────────

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes scaleIn{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:scale(1)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .06s ease both}
.au2{animation:fadeUp .28s .12s ease both}
.au3{animation:fadeUp .28s .18s ease both}
.au4{animation:fadeUp .28s .24s ease both}
.si{animation:scaleIn .22s ease both}
.af{animation:fadeIn .2s ease both}
.checkin-pulse{animation:pulse 2.5s ease-in-out infinite}
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

// ─── Shared small components ──────────────────────────────────────────────────

function Chip({ active, children, onClick, className = '' }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-xs font-semibold border-2 transition-all duration-150
        ${active
          ? 'bg-blue-700 border-blue-700 text-white shadow-sm'
          : 'bg-white border-blue-100 text-slate-600 hover:border-blue-300 hover:text-blue-700 hover:bg-blue-50'
        } ${className}`}>
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

// ─── EquipmentSelector ────────────────────────────────────────────────────────

function EquipmentSelector({ selected, onChange, compact = false }) {
  const toggle = (key) => {
    if (selected.includes(key)) {
      onChange(selected.filter(k => k !== key))
    } else {
      onChange([...selected, key])
    }
  }

  return (
    <div className={`flex flex-wrap ${compact ? 'gap-1.5' : 'gap-2'}`}>
      {EQUIPMENT_PRESETS.map(eq => {
        const active = selected.includes(eq.key)
        return (
          <button
            key={eq.key}
            onClick={() => toggle(eq.key)}
            className={`inline-flex items-center gap-1.5 rounded-full border-2 font-semibold transition-all duration-150
              ${compact ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-xs'}
              ${active
                ? 'bg-blue-700 border-blue-700 text-white shadow-sm'
                : 'bg-white border-blue-100 text-slate-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700'
              }`}
          >
            <span className="text-sm leading-none">{eq.icon}</span>
            {eq.label}
            {active && (
              <span className="w-3.5 h-3.5 rounded-full bg-white/25 flex items-center justify-center ml-0.5">
                <X size={8} className="text-white" />
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ─── FacilityTags ─────────────────────────────────────────────────────────────

function FacilityTags({ facilities = [], compact = true, maxShow = 5, highlight = [] }) {
  if (!facilities || facilities.length === 0) return null

  // ตรวจว่า facility นี้ตรงกับ highlighted keywords ไหม
  const isHighlighted = (facilityName) => {
    if (!highlight || highlight.length === 0) return false
    const nameLower = facilityName.toLowerCase()
    return highlight.some(key => {
      const preset = EQUIPMENT_PRESETS.find(p => p.key === key)
      if (!preset) return false
      return preset.keywords.some(kw => nameLower.includes(kw.toLowerCase()))
    })
  }

  if (compact) {
    const shown = facilities.slice(0, maxShow)
    const rest  = facilities.length - maxShow
    return (
      <div className="flex flex-wrap gap-1 mt-2">
        {shown.map((f, i) => {
          const hl = isHighlighted(f.name)
          return (
            <span
              key={i}
              className={`inline-flex items-center gap-1 text-xs rounded-full px-2 py-0.5 font-medium border transition-all
                ${hl
                  ? 'bg-blue-50 border-blue-300 text-blue-700 ring-1 ring-blue-200'
                  : 'bg-slate-50 border-slate-200 text-slate-600'
                }`}
              title={`${f.name} ×${f.quantity}`}
            >
              <span className="text-sm leading-none">{getFacIcon(f.name)}</span>
              {f.name}
              {f.quantity > 1 && (
                <span className={`rounded-full px-1 text-xs font-bold ${hl ? 'bg-blue-200 text-blue-600' : 'bg-slate-200 text-slate-500'}`}>×{f.quantity}</span>
              )}
            </span>
          )
        })}
        {rest > 0 && (
          <span className="text-xs text-slate-400 border border-slate-200 rounded-full px-2 py-0.5 bg-white">
            +{rest} อื่นๆ
          </span>
        )}
      </div>
    )
  }

  // Full grid สำหรับ Step 3
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {facilities.map((f, i) => {
        const hl = isHighlighted(f.name)
        return (
          <div
            key={i}
            className={`flex items-center gap-2 rounded-xl px-3 py-2 border transition-all
              ${hl
                ? 'bg-blue-50 border-blue-200 ring-1 ring-blue-100'
                : 'bg-slate-50 border-slate-100'
              }`}
          >
            <span className="text-base flex-shrink-0">{getFacIcon(f.name)}</span>
            <div className="min-w-0">
              <p className={`text-xs font-semibold truncate leading-tight ${hl ? 'text-blue-700' : 'text-slate-700'}`}>{f.name}</p>
              <p className="text-xs text-slate-400">จำนวน {f.quantity} ชิ้น</p>
            </div>
            {hl && <span className="ml-auto text-blue-400 flex-shrink-0"><CheckCircle size={12} /></span>}
          </div>
        )
      })}
    </div>
  )
}

// ─── BookingTypeSelector ──────────────────────────────────────────────────────

function BookingTypeSelector({ value, onChange, compact = false }) {
  const types = [
    {
      key: 'daily', icon: Coffee,
      label: 'ห้องประชุม / รายวัน',
      sub: 'จองใช้งานเป็นครั้ง เลือกวันและเวลาที่ต้องการ',
      activeBg: 'bg-blue-700', activeBorder: 'border-blue-700',
    },
    {
      key: 'term', icon: BookOpen,
      label: 'จองทั้งเทอม',
      sub: 'จองห้องเรียน/ห้อง Lecture ประจำทุกสัปดาห์',
      activeBg: 'bg-indigo-700', activeBorder: 'border-indigo-700',
    },
  ]
  return (
    <div className="grid grid-cols-2 gap-3">
      {types.map(t => {
        const Icon = t.icon
        const active = value === t.key
        return (
          <button key={t.key} onClick={() => onChange(t.key)}
            className={`relative flex flex-col items-start gap-1.5 rounded-2xl border-2 transition-all duration-150 text-left
              ${compact ? 'px-4 py-3' : 'px-5 py-4'}
              ${active
                ? `${t.activeBorder} ${t.activeBg} text-white shadow-lg`
                : 'border-blue-100 bg-white text-slate-700 hover:border-blue-300 hover:bg-blue-50'
              }`}>
            <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0
              ${active ? 'bg-white/20' : 'bg-blue-50'}`}>
              <Icon size={16} className={active ? 'text-white' : 'text-blue-600'} />
            </div>
            <div>
              <p className={`font-bold text-sm leading-tight ${active ? 'text-white' : 'text-slate-800'}`}>{t.label}</p>
              {!compact && (
                <p className={`text-xs mt-0.5 leading-snug ${active ? 'text-white/75' : 'text-slate-400'}`}>{t.sub}</p>
              )}
            </div>
            {active && (
              <div className="absolute top-3 right-3 w-5 h-5 rounded-full bg-white/25 flex items-center justify-center">
                <CheckCircle size={12} className="text-white" />
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ─── RoomStatusBadge ─────────────────────────────────────────────────────────

function RoomStatusBadge({ status }) {
  const cfg = ROOM_STATUS[status] ?? ROOM_STATUS.available
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full border ${cfg.cls}`}>
      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: cfg.dot }} />
      {cfg.label}
    </span>
  )
}

// ─── CheckInReminder ─────────────────────────────────────────────────────────

function CheckInReminder({ startTime, compact = false }) {
  if (!startTime) return null
  return (
    <div className={`checkin-pulse relative overflow-hidden border-2 border-amber-400
      bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl shadow-md shadow-amber-100
      ${compact ? 'px-4 py-3.5' : 'px-5 py-4'}`}>
      <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-amber-400 to-orange-400 rounded-l-2xl" />
      <div className="flex items-start gap-3 ml-1">
        <div className="w-9 h-9 rounded-xl bg-amber-400 flex items-center justify-center flex-shrink-0 shadow-sm shadow-amber-200">
          <AlertTriangle size={18} color="#fff" strokeWidth={2.5} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-amber-900 font-extrabold text-sm leading-snug mb-1">⚠️ ในกรณีที่ไม่สามารถเข้าใช้งานห้องตามเวลาที่จองไว้ ขอความกรุณาดำเนินการยกเลิกการจองล่วงหน้า เพื่อให้ผู้อื่นสามารถใช้บริการต่อได้ ขอบคุณค่ะ/ครับ!</p>
          <p className="text-amber-800 text-xs leading-relaxed">
            
          </p>
          
          </div>
        </div>
      </div>
   
  )
}

// ─── TermFilterBanner ────────────────────────────────────────────────────────

function TermFilterBanner({ compact = false }) {
  return (
    <div className={`flex items-center gap-2.5 bg-indigo-50 border border-indigo-200 rounded-xl ${compact ? 'px-3 py-2' : 'px-4 py-3'}`}>
      <Filter size={13} className="text-indigo-600 flex-shrink-0" />
      <p className={`text-indigo-700 font-semibold ${compact ? 'text-xs' : 'text-xs'}`}>
        แสดงเฉพาะ <span className="font-extrabold">ห้องเรียน / ห้อง Lecture</span> สำหรับการจองทั้งเทอม
      </p>
    </div>
  )
}

// ─── SummaryTiles ─────────────────────────────────────────────────────────────

function SummaryTiles({ rooms, layout = 'vertical' }) {
  if (layout === 'grid') {
    return (
      <div className="grid grid-cols-2 gap-2 au1">
        {SUMMARY_TIERS.map(s => {
          const cfg   = FORECAST_CONFIG[s.level]
          const count = rooms.filter(r => getDemandLevel(r) === s.level).length
          return (
            <div key={s.level} className={`border rounded-2xl py-3 text-center ${cfg.cardBg} ${cfg.cardBorder}`}>
              <p className={`text-2xl font-extrabold ${cfg.numCls}`}>{count}</p>
              <p className={`text-xs font-semibold mt-0.5 leading-tight px-1 ${cfg.textCls} opacity-90`}>{s.label}</p>
            </div>
          )
        })}
      </div>
    )
  }
  return (
    <div className="space-y-3 au1">
      {SUMMARY_TIERS.map(s => {
        const cfg   = FORECAST_CONFIG[s.level]
        const count = rooms.filter(r => getDemandLevel(r) === s.level).length
        return (
          <div key={s.level} className={`border rounded-2xl py-4 text-center ${cfg.cardBg} ${cfg.cardBorder}`}>
            <p className={`text-3xl font-extrabold ${cfg.numCls}`}>{count}</p>
            <p className={`text-xs font-semibold mt-1 ${cfg.textCls} opacity-80`}>{s.label}</p>
          </div>
        )
      })}
      <p className="text-xs text-slate-400 text-center">เรียงตาม AI Forecast</p>
    </div>
  )
}

// ─── RoomCard ─────────────────────────────────────────────────────────────────

function RoomCard({ room, idx, onClick, compact = false, isTermMode = false, selectedEquipments = [] }) {
  const level = getDemandLevel(room)
  const cfg   = FORECAST_CONFIG[level]
  const isTop = idx === 0 && (level === 'low' || level === 'none')

  return (
    <div
      className={`bg-white border border-blue-100 rounded-2xl cursor-pointer
        hover:shadow-lg hover:shadow-blue-100 hover:-translate-y-0.5 transition-all duration-150
        ${compact ? 'px-4 py-4' : 'px-6 py-5'}`}
      style={{ borderLeftWidth: 4, borderLeftColor: cfg.dotColor }}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          {isTop && (
            <span className="inline-block bg-yellow-100 text-yellow-800 border border-yellow-300 text-xs font-bold rounded-full px-2.5 py-0.5 mb-2">แนะนำ</span>
          )}
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            <span className={`font-bold text-slate-900 ${compact ? 'text-sm' : 'text-base'}`}>{room.name}</span>
            <RoomStatusBadge status={room.status} />
            <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${cfg.badgeCls}`}>{cfg.badge}</span>
            {isTermMode && (
              <span className="text-xs bg-indigo-50 text-indigo-600 border border-indigo-200 rounded-full px-2 py-0.5 font-semibold">
                {room.room_type}
              </span>
            )}
            {room.forecast?.has_forecast === false && (
              <span className="text-xs text-slate-400 border border-slate-200 rounded-full px-2 py-0.5">ไม่มีข้อมูล AI</span>
            )}
          </div>
          <p className="text-xs text-slate-500 mb-1">
            {room.building_name} · ชั้น {room.floor} · {room.capacity} ที่นั่ง
            {!compact && ` · ${room.room_type}`}
          </p>
          {room.description && (
            <p className="text-xs text-slate-400 mb-1.5 line-clamp-1">{room.description}</p>
          )}
          {level !== 'none' && (
            <p className={`text-xs font-semibold ${cfg.subCls} mb-1`}>{cfg.sub}</p>
          )}
          {/* อุปกรณ์ — highlight ตัวที่ผู้ใช้เลือก */}
          <FacilityTags
            facilities={room.facilities}
            compact={true}
            maxShow={compact ? 4 : 6}
            highlight={selectedEquipments}
          />
        </div>
        <ChevronRight size={14} className="text-blue-200 flex-shrink-0 mt-1" />
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// DESKTOP LAYOUT
// ═══════════════════════════════════════════════════════════════════════════════

function DesktopLayout({ step, setStep, navigate, bookingType, setBookingType, formProps, resultProps, confirmProps }) {
  const {
    attendees, setAttendees, date, setDate,
    startTime, setStartTime, duration, setDuration,
    building, setBuilding, endTime, loading, handleSearch, error,
    dayOfWeek, setDayOfWeek,
    termStart, setTermStart,
    termEnd, setTermEnd,
    termName, setTermName,
    selectedEquipments, setSelectedEquipments,
  } = formProps
  const { rooms, setSelectedRoom } = resultProps
  const { selectedRoom, title, setTitle, bookingLoading, handleBook, success } = confirmProps

  const isTermMode = bookingType === 'term'
  const accentBg   = isTermMode ? 'bg-indigo-700' : 'bg-blue-700'
  const accentHov  = isTermMode ? 'hover:bg-indigo-800' : 'hover:bg-blue-800'
  const accentShadow = isTermMode ? 'shadow-indigo-200' : 'shadow-blue-200'

  if (success) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <style>{ANIM}</style>
      <div className="bg-white border border-blue-100 rounded-3xl p-12 text-center max-w-md w-full shadow-2xl si">
        <div className={`w-20 h-20 rounded-full ${accentBg} flex items-center justify-center mx-auto mb-6 shadow-xl ${accentShadow}`}>
          <CheckCircle size={38} color="#fff" />
        </div>
        <div className="h-1 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-6" />
        <p className="text-2xl font-extrabold text-slate-900 mb-2">จองสำเร็จแล้ว</p>
        <p className={`text-lg font-bold mb-4 ${isTermMode ? 'text-indigo-700' : 'text-blue-700'}`}>{selectedRoom?.name}</p>
        {isTermMode
          ? (
            <>
              <p className="text-sm text-slate-500">ทุก{getDayLabel(dayOfWeek)} · {startTime} – {endTime} น.</p>
              {termStart && termEnd && (
                <p className="text-xs text-slate-400 mt-1">{formatDateShort(termStart)} – {formatDateShort(termEnd)}</p>
              )}
              {termName && <p className="text-xs text-indigo-600 font-semibold mt-1">{termName}</p>}
            </>
          )
          : <p className="text-sm text-slate-500">{formatDate(date)} · {startTime} – {endTime} น.</p>
        }
        <p className="text-sm text-slate-500 mt-1">{attendees} ผู้เข้าร่วม</p>
        <div className="mt-6 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-left">
          <p className="text-amber-800 text-xs font-bold mb-0.5">⚠️ อย่าลืม! กด Check-in ภายใน 15 นาที</p>
          <p className="text-amber-700 text-xs">หลังเวลา {startTime} น. มิฉะนั้นการจองจะถูกยกเลิกอัตโนมัติ</p>
        </div>
        <button onClick={() => navigate('/')}
          className={`mt-5 w-full ${accentBg} ${accentHov} text-white rounded-2xl py-4 font-bold text-sm transition-all shadow-lg ${accentShadow} active:scale-95`}>
          กลับหน้าหลัก
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-slate-100" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>

      {/* Top bar */}
      <div className={`${accentBg} shadow-lg shadow-blue-900/20`}>
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => step === 1 ? navigate('/') : setStep(step - 1)}
            className="flex items-center gap-2 text-white/80 hover:text-white text-sm font-medium transition-colors">
            <ArrowLeft size={15} />
            {step === 1 ? 'หน้าหลัก' : 'ย้อนกลับ'}
          </button>
          <div className="h-5 w-px bg-white/20" />
          <div className="flex items-center gap-2">
            <span className="bg-white/15 text-white text-xs font-bold px-2.5 py-1 rounded-full flex items-center gap-1">
              {isTermMode ? <><BookOpen size={10} />ทั้งเทอม</> : <><Coffee size={10} />รายวัน</>}
            </span>
            <span className="text-white font-bold text-sm">
              {step === 1 ? 'เลือกเงื่อนไข' : step === 2 ? `ผลการค้นหา · ${rooms.length} ห้อง` : 'ยืนยันการจอง'}
            </span>
          </div>
          <div className="ml-auto flex items-center gap-3">
            {[1,2,3].map(s => (
              <div key={s} className="flex items-center gap-1.5">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-all
                  ${step >= s ? 'bg-white text-blue-700' : 'bg-white/20 text-white/60'}`}>{s}</div>
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

      {/* ── STEP 1 ── */}
      {step === 1 && (
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="grid grid-cols-3 gap-6">
            <div className="col-span-2 space-y-5">

              <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au">
                <SectionLabel>ประเภทการจอง</SectionLabel>
                <BookingTypeSelector value={bookingType} onChange={v => { setBookingType(v); setDayOfWeek(null) }} />
                {isTermMode && (
                  <div className="mt-3"><TermFilterBanner /></div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-5">
                <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au1">
                  <SectionLabel icon={Users}>จำนวนผู้เข้าร่วม</SectionLabel>
                  <div className="flex items-center gap-4 mb-4">
                    <button onClick={() => setAttendees(Math.max(1, attendees - 1))}
                      className="w-10 h-10 rounded-xl border-2 border-blue-100 bg-blue-50 text-blue-600 text-xl font-bold flex items-center justify-center hover:bg-blue-100 transition-all active:scale-90">−</button>
                    <div className="flex-1 text-center">
                      <span className="text-5xl font-extrabold text-slate-900">{attendees}</span>
                      <span className="text-sm text-slate-400 ml-2">คน</span>
                    </div>
                    <button onClick={() => setAttendees(attendees + 1)}
                      className={`w-10 h-10 rounded-xl ${accentBg} text-white text-xl font-bold flex items-center justify-center ${accentHov} shadow-sm ${accentShadow} active:scale-90`}>+</button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {ATTENDEES_PRESETS.map(n => <Chip key={n} active={attendees === n} onClick={() => setAttendees(n)}>{n} คน</Chip>)}
                  </div>
                </div>

                <div className="space-y-5">
                  {isTermMode ? (
                    <div className="bg-white border border-indigo-100 rounded-2xl p-6 shadow-sm au2">
                      <SectionLabel icon={Calendar}>วันในสัปดาห์</SectionLabel>
                      <div className="grid grid-cols-4 gap-1.5">
                        {DAYS_OF_WEEK.map(d => (
                          <button key={d.value} onClick={() => setDayOfWeek(d.value)}
                            className={`py-2.5 rounded-xl text-xs font-bold border-2 transition-all duration-150
                              ${dayOfWeek === d.value
                                ? 'bg-indigo-700 border-indigo-700 text-white shadow-sm'
                                : 'bg-white border-indigo-100 text-slate-600 hover:border-indigo-300 hover:bg-indigo-50'}`}>
                            {d.label}
                          </button>
                        ))}
                      </div>
                      {dayOfWeek != null && (
                        <p className="mt-2 text-xs text-indigo-600 font-semibold">ทุก{getDayLabel(dayOfWeek)}</p>
                      )}
                    </div>
                  ) : (
                    <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au2">
                      <SectionLabel icon={Calendar}>วันที่</SectionLabel>
                      <input type="date" value={date} min={new Date().toISOString().split('T')[0]}
                        onChange={e => setDate(e.target.value)}
                        className="w-full border-2 border-blue-100 rounded-xl px-4 py-2.5 text-sm text-slate-800 bg-blue-50/40 outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 transition-all"
                        style={{fontFamily:"inherit"}} />
                    </div>
                  )}

                  <div className={`bg-white rounded-2xl p-6 shadow-sm au3 border ${isTermMode ? 'border-indigo-100' : 'border-blue-100'}`}>
                    <SectionLabel icon={MapPin}>อาคาร</SectionLabel>
                    <div className="flex flex-wrap gap-1.5">
                      {BUILDINGS.map(b => <Chip key={b.code} active={building === b.code} onClick={() => setBuilding(b.code)}>{b.label}</Chip>)}
                    </div>
                  </div>
                </div>
              </div>

              {isTermMode && (
                <div className="bg-white border border-indigo-100 rounded-2xl p-5 shadow-sm au2">
                  <SectionLabel>ข้อมูลเทอม</SectionLabel>
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-slate-500 mb-1 block">ชื่อเทอม</label>
                      <input type="text" value={termName} onChange={e => setTermName(e.target.value)}
                        placeholder="เช่น ภาคเรียนที่ 1/2568"
                        className="w-full border-2 border-indigo-100 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100 transition-all"
                        style={{fontFamily:"inherit"}} />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-slate-500 mb-1 block">วันเริ่มเทอม <span className="text-red-400">*</span></label>
                        <input type="date" value={termStart} onChange={e => setTermStart(e.target.value)}
                          className="w-full border-2 border-indigo-100 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100 transition-all"
                          style={{fontFamily:"inherit"}} />
                      </div>
                      <div>
                        <label className="text-xs text-slate-500 mb-1 block">วันสิ้นสุดเทอม <span className="text-red-400">*</span></label>
                        <input type="date" value={termEnd} onChange={e => setTermEnd(e.target.value)}
                          className="w-full border-2 border-indigo-100 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100 transition-all"
                          style={{fontFamily:"inherit"}} />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className={`bg-white rounded-2xl p-6 shadow-sm au3 border ${isTermMode ? 'border-indigo-100' : 'border-blue-100'}`}>
                <SectionLabel icon={Clock}>เวลา</SectionLabel>
                <div className="grid grid-cols-8 gap-2 mb-4">
                  {TIME_SLOTS.map(t => (
                    <button key={t} onClick={() => setStartTime(t)}
                      className={`py-2.5 rounded-xl text-xs font-semibold border-2 transition-all duration-150
                        ${startTime === t
                          ? `${accentBg} border-transparent text-white shadow-sm`
                          : 'bg-white border-blue-100 text-slate-600 hover:border-blue-300 hover:bg-blue-50'}`}>
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
                    <div className={`ml-auto ${accentBg} rounded-xl px-5 py-2 si`}>
                      <span className="text-sm font-bold text-white">{startTime} – {endTime} น.</span>
                      <span className="text-white/60 text-xs ml-3">
                        {isTermMode && dayOfWeek != null ? `ทุก${getDayLabel(dayOfWeek)}` : formatDateShort(date)}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* ── อุปกรณ์ที่ต้องการ ── */}
              <div className={`bg-white rounded-2xl p-6 shadow-sm au4 border ${isTermMode ? 'border-indigo-100' : 'border-blue-100'}`}>
                <div className="flex items-center justify-between mb-3">
                  <SectionLabel>อุปกรณ์ที่ต้องการ</SectionLabel>
                  {selectedEquipments.length > 0 && (
                    <button
                      onClick={() => setSelectedEquipments([])}
                      className="text-xs text-slate-400 hover:text-red-500 flex items-center gap-1 transition-colors"
                    >
                      <X size={11} />ล้างทั้งหมด
                    </button>
                  )}
                </div>
                <EquipmentSelector selected={selectedEquipments} onChange={setSelectedEquipments} />
                {selectedEquipments.length > 0 && (
                  <div className="mt-3 flex items-center gap-2 bg-blue-50 border border-blue-100 rounded-xl px-3 py-2">
                    <Filter size={11} className="text-blue-500 flex-shrink-0" />
                    <p className="text-xs text-blue-600 font-semibold">
                      กรองเฉพาะห้องที่มี: {selectedEquipments.map(k => EQUIPMENT_PRESETS.find(p => p.key === k)?.label).join(', ')}
                    </p>
                  </div>
                )}
              </div>

            </div>

            {/* Summary sidebar */}
            <div className="au4">
              <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm sticky top-20">
                <p className="text-base font-bold text-slate-900 mb-1">สรุปการค้นหา</p>
                <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
                <div className="space-y-3 mb-6 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-500">ประเภท</span>
                    <span className={`font-bold ${isTermMode ? 'text-indigo-700' : 'text-blue-700'}`}>{isTermMode ? 'ทั้งเทอม' : 'รายวัน'}</span>
                  </div>
                  {isTermMode && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-slate-500">ห้อง</span>
                        <span className="font-bold text-indigo-600 text-xs">เฉพาะห้องเรียน/Lecture</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">ชื่อเทอม</span>
                        <span className="font-bold text-slate-800 text-xs truncate max-w-[120px]">{termName || '—'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">ช่วงเทอม</span>
                        <span className="font-bold text-slate-800 text-xs">
                          {termStart && termEnd ? `${formatDateShort(termStart)}–${formatDateShort(termEnd)}` : '—'}
                        </span>
                      </div>
                    </>
                  )}
                  <div className="flex justify-between"><span className="text-slate-500">ผู้เข้าร่วม</span><span className="font-bold text-slate-800">{attendees} คน</span></div>
                  {isTermMode
                    ? <div className="flex justify-between"><span className="text-slate-500">วัน</span><span className="font-bold text-slate-800">{dayOfWeek != null ? `ทุก${getDayLabel(dayOfWeek)}` : '—'}</span></div>
                    : <div className="flex justify-between"><span className="text-slate-500">วันที่</span><span className="font-bold text-slate-800">{formatDateShort(date)}</span></div>
                  }
                  <div className="flex justify-between"><span className="text-slate-500">เวลา</span><span className="font-bold text-slate-800">{startTime ? `${startTime}–${endTime}` : '—'}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">อาคาร</span><span className="font-bold text-slate-800">{BUILDINGS.find(b => b.code === building)?.label || 'ทั้งหมด'}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">ขนาดห้อง</span><span className="font-bold text-slate-800">{attendees}–{attendees + CAPACITY_BUFFER} คน</span></div>
                  {selectedEquipments.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <span className="text-slate-500">อุปกรณ์ที่ต้องการ</span>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {selectedEquipments.map(k => {
                          const eq = EQUIPMENT_PRESETS.find(p => p.key === k)
                          return (
                            <span key={k} className="inline-flex items-center gap-1 bg-blue-50 border border-blue-200 text-blue-700 rounded-full px-2 py-0.5 text-xs font-semibold">
                              {eq?.icon} {eq?.label}
                            </span>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
                <button onClick={handleSearch} disabled={loading}
                  className={`w-full ${accentBg} ${accentHov} disabled:bg-slate-400 text-white rounded-2xl py-4 font-bold text-sm flex items-center justify-center gap-2.5 shadow-lg ${accentShadow} transition-all active:scale-95 disabled:cursor-not-allowed`}>
                  {loading
                    ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />ค้นหา...</>
                    : <><Search size={15} />ค้นหาห้องว่าง</>}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── STEP 2 ── */}
      {step === 2 && (
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className={`${accentBg} rounded-2xl px-6 py-4 flex items-center justify-between mb-6 shadow-md ${accentShadow} au`}>
            <div className="flex gap-6 items-center flex-wrap">
              <span className="text-white font-bold">{attendees} คน</span>
              {isTermMode
                ? <span className="text-white/80 text-sm">ทุก{getDayLabel(dayOfWeek)}</span>
                : <span className="text-white/80 text-sm">{formatDateShort(date)}</span>
              }
              <span className="text-white/80 text-sm">{startTime}–{endTime}</span>
              {building && <span className="text-white/80 text-sm">{BUILDINGS.find(b=>b.code===building)?.label}</span>}
              <span className="text-white/80 text-sm">จุ {attendees}–{attendees + CAPACITY_BUFFER} คน</span>
              {isTermMode && termName && (
                <span className="bg-white/15 text-white text-xs font-semibold rounded-full px-2.5 py-1">{termName}</span>
              )}
              {isTermMode && (
                <span className="bg-white/15 text-white text-xs font-bold rounded-full px-2.5 py-1 flex items-center gap-1">
                  <Filter size={10} />ห้องเรียน / Lecture เท่านั้น
                </span>
              )}
              {selectedEquipments.length > 0 && (
                <span className="bg-white/15 text-white text-xs font-bold rounded-full px-2.5 py-1 flex items-center gap-1">
                  <Filter size={10} />
                  {selectedEquipments.map(k => EQUIPMENT_PRESETS.find(p => p.key === k)?.icon).join(' ')}
                  {selectedEquipments.length} อุปกรณ์
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 bg-yellow-300 text-yellow-900 text-xs font-bold rounded-full px-3 py-1.5">
              <Zap size={11} />AI Forecast
            </div>
          </div>

          <div className="grid grid-cols-4 gap-6">
            <SummaryTiles rooms={rooms} layout="vertical" />
            <div className="col-span-3 space-y-3 au2">
              {rooms.length === 0 ? (
                <div className="bg-white border border-blue-100 rounded-2xl py-16 text-center">
                  <Building2 size={40} className="text-blue-200 mx-auto mb-4" />
                  <p className="font-semibold text-blue-700 mb-2">
                    {isTermMode ? 'ไม่พบห้องเรียน/Lecture ที่ว่าง' : 'ไม่พบห้องว่างที่เหมาะสม'}
                  </p>
                  <p className="text-xs text-slate-400 mb-4">สำหรับ {attendees}–{attendees + CAPACITY_BUFFER} คน</p>
                  <button onClick={() => setStep(1)} className="text-sm text-blue-600 hover:underline">← ค้นหาใหม่</button>
                </div>
              ) : rooms.map((room, idx) => (
                <RoomCard key={room.id} room={room} idx={idx} isTermMode={isTermMode}
                  selectedEquipments={selectedEquipments}
                  onClick={() => { setSelectedRoom(room); setStep(3) }} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── STEP 3 ── */}
      {step === 3 && selectedRoom && (() => {
        const level = getDemandLevel(selectedRoom)
        const cfg   = FORECAST_CONFIG[level]
        return (
          <div className="max-w-3xl mx-auto px-6 py-8">
            <div className="mb-6 au"><CheckInReminder startTime={startTime} /></div>
            <div className="grid grid-cols-2 gap-6">

              {/* left */}
              <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm au1">
                <SectionLabel icon={Building2}>ห้องที่เลือก</SectionLabel>
                <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
                <div className="mb-4">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <p className="text-lg font-bold text-slate-900">{selectedRoom.name}</p>
                    <RoomStatusBadge status={selectedRoom.status} />
                  </div>
                  <p className="text-xs text-slate-500">{selectedRoom.building_name} · ชั้น {selectedRoom.floor} · {selectedRoom.room_type}</p>
                  {selectedRoom.description && <p className="text-xs text-slate-400 mt-1">{selectedRoom.description}</p>}
                </div>

                {/* booking detail table */}
                <div className="border-2 border-blue-50 rounded-xl overflow-hidden mb-4">
                  {[
                    { label: 'ประเภท',      value: isTermMode ? 'จองทั้งเทอม' : 'จองรายวัน' },
                    isTermMode
                      ? { label: 'วัน',       value: `ทุก${getDayLabel(dayOfWeek)}` }
                      : { label: 'วันที่',    value: formatDate(date) },
                    { label: 'เวลา',         value: `${startTime} – ${endTime} น.` },
                    { label: 'ผู้เข้าร่วม', value: `${attendees} คน` },
                    { label: 'ความจุห้อง',  value: `${selectedRoom.capacity} คน` },
                    ...(isTermMode && termName ? [{ label: 'เทอม', value: termName }] : []),
                    ...(isTermMode && termStart && termEnd
                      ? [{ label: 'ช่วงเทอม', value: `${formatDateShort(termStart)} – ${formatDateShort(termEnd)}` }]
                      : []),
                  ].map((r, i) => (
                    <div key={i} className="flex justify-between px-4 py-3 bg-white border-b border-blue-50 last:border-0">
                      <span className="text-xs text-slate-500">{r.label}</span>
                      <span className="text-sm font-semibold text-slate-800">{r.value}</span>
                    </div>
                  ))}
                </div>

                {/* อุปกรณ์ในห้อง — highlight ตามที่เลือก */}
                {selectedRoom.facilities?.length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                      <span>🔧</span>อุปกรณ์ในห้อง
                      <span className="text-slate-300 font-normal">({selectedRoom.facilities.length} รายการ)</span>
                      {selectedEquipments.length > 0 && (
                        <span className="text-blue-500 font-semibold normal-case tracking-normal">· ไฮไลต์อุปกรณ์ที่เลือก</span>
                      )}
                    </p>
                    <FacilityTags
                      facilities={selectedRoom.facilities}
                      compact={false}
                      highlight={selectedEquipments}
                    />
                  </div>
                )}

                {cfg.badge !== '—' && (
                  <div className={`flex items-center gap-2.5 rounded-xl px-4 py-3 ${cfg.pillCls}`}>
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: cfg.dotColor }} />
                    <span className={`text-xs font-bold ${cfg.textCls}`}>{cfg.badge}</span>
                    <span className={`text-xs ${cfg.subCls} opacity-80`}>— {cfg.sub}</span>
                  </div>
                )}
              </div>

              {/* right */}
              <div className="space-y-5 au2">
                <div className="bg-white border border-blue-100 rounded-2xl p-6 shadow-sm">
                  <SectionLabel>{isTermMode ? 'ชื่อวิชา / กิจกรรม' : 'หัวข้อการประชุม'}</SectionLabel>
                  <input type="text" autoFocus
                    placeholder={isTermMode ? 'เช่น วิชา CS101, กิจกรรมชมรม...' : 'เช่น ประชุมกลุ่ม, นำเสนองาน...'}
                    value={title} onChange={e => setTitle(e.target.value)}
                    className="w-full border-2 border-blue-100 rounded-xl px-4 py-3 text-sm text-slate-800 bg-blue-50/40 outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 transition-all placeholder:text-slate-400"
                    style={{fontFamily:"inherit"}} />
                </div>
                <button onClick={handleBook} disabled={bookingLoading}
                  className={`w-full ${accentBg} ${accentHov} disabled:bg-slate-400 text-white rounded-2xl py-5 font-bold text-base flex items-center justify-center gap-3 shadow-xl ${accentShadow} transition-all active:scale-95 disabled:cursor-not-allowed`}>
                  {bookingLoading
                    ? <><div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />กำลังจอง...</>
                    : <><CheckCircle size={18} />{isTermMode ? 'ยืนยันจองทั้งเทอม' : 'ยืนยันการจอง'}</>}
                </button>
              </div>
            </div>
          </div>
        )
      })()}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// MOBILE LAYOUT
// ═══════════════════════════════════════════════════════════════════════════════

function MobileLayout({ step, setStep, navigate, bookingType, setBookingType, formProps, resultProps, confirmProps }) {
  const {
    attendees, setAttendees, date, setDate,
    startTime, setStartTime, duration, setDuration,
    building, setBuilding, endTime, loading, handleSearch, error,
    dayOfWeek, setDayOfWeek,
    termStart, setTermStart,
    termEnd, setTermEnd,
    termName, setTermName,
    selectedEquipments, setSelectedEquipments,
  } = formProps
  const { rooms, setSelectedRoom } = resultProps
  const { selectedRoom, title, setTitle, bookingLoading, handleBook, success } = confirmProps

  const isTermMode   = bookingType === 'term'
  const accentBg     = isTermMode ? 'bg-indigo-700' : 'bg-blue-700'
  const accentHov    = isTermMode ? 'hover:bg-indigo-800' : 'hover:bg-blue-800'
  const accentShadow = isTermMode ? 'shadow-indigo-200' : 'shadow-blue-200'

  if (success) return (
    <div className="min-h-screen bg-blue-50 flex items-center justify-center p-4"
      style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="bg-white border border-blue-100 rounded-3xl p-8 text-center max-w-sm w-full shadow-xl si">
        <div className={`w-16 h-16 rounded-full ${accentBg} flex items-center justify-center mx-auto mb-5 shadow-lg ${accentShadow}`}>
          <CheckCircle size={30} color="#fff" />
        </div>
        <div className="h-1 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-5" />
        <p className="text-xl font-extrabold text-slate-900 mb-1.5">จองสำเร็จแล้ว</p>
        <p className={`text-base font-bold mb-3 ${isTermMode ? 'text-indigo-700' : 'text-blue-700'}`}>{selectedRoom?.name}</p>
        {isTermMode
          ? (
            <>
              <p className="text-sm text-slate-500">ทุก{getDayLabel(dayOfWeek)} · {startTime} – {endTime} น.</p>
              {termStart && termEnd && (
                <p className="text-xs text-slate-400 mt-1">{formatDateShort(termStart)} – {formatDateShort(termEnd)}</p>
              )}
              {termName && <p className="text-xs text-indigo-600 font-semibold mt-1">{termName}</p>}
            </>
          )
          : <p className="text-sm text-slate-500">{formatDateShort(date)} · {startTime} – {endTime} น.</p>
        }
        <p className="text-sm text-slate-500 mt-0.5">{attendees} คน</p>
        <div className="mt-5 bg-amber-50 border border-amber-300 rounded-xl px-4 py-3 text-left">
          <p className="text-amber-800 text-xs font-bold mb-0.5">⚠️ อย่าลืม! กด Check-in ภายใน 15 นาที</p>
          <p className="text-amber-700 text-xs">หลังเวลา {startTime} น. มิฉะนั้นการจองจะถูกยกเลิกอัตโนมัติ</p>
        </div>
        <button onClick={() => navigate('/')}
          className={`mt-5 w-full ${accentBg} text-white rounded-xl py-3.5 text-sm font-bold shadow-md ${accentShadow} active:scale-95`}>
          กลับหน้าหลัก
        </button>
      </div>
    </div>
  )

  const stepTitle = step === 1 ? 'ค้นหาห้อง'
                  : step === 2 ? `ผลการค้นหา · ${rooms.length} ห้อง`
                  : 'ยืนยันการจอง'

  return (
    <div className="min-h-screen bg-blue-50" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>

      <div className={`${accentBg} sticky top-0 z-50 shadow-lg shadow-blue-900/20`}>
        <div className="max-w-lg mx-auto px-4 h-14 flex items-center gap-3">
          <button onClick={() => step === 1 ? navigate('/') : setStep(step - 1)}
            className="w-8 h-8 rounded-lg border border-white/20 bg-white/10 flex items-center justify-center text-white hover:bg-white/20 transition-colors flex-shrink-0">
            <ArrowLeft size={15} />
          </button>
          <div className="flex-1">
            <p className="text-sm font-bold text-white leading-tight">{stepTitle}</p>
            <p className="text-xs text-white/60">{isTermMode ? 'จองทั้งเทอม' : 'จองรายวัน'} · ขั้นตอนที่ {step}/3</p>
          </div>
          <div className="flex gap-1.5">
            {[1,2,3].map(s => (
              <div key={s} className="h-1.5 rounded-full transition-all duration-300"
                style={{ width: s === step ? 20 : 6, background: step >= s ? '#fff' : 'rgba(255,255,255,.25)' }} />
            ))}
          </div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 pb-12 space-y-3">
        {error && <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-4 py-3 rounded-xl af">{error}</div>}

        {/* ── STEP 1 ── */}
        {step === 1 && (
          <>
            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au">
              <SectionLabel>ประเภทการจอง</SectionLabel>
              <BookingTypeSelector value={bookingType} onChange={v => { setBookingType(v); setDayOfWeek(null) }} compact />
              {isTermMode && (
                <div className="mt-3"><TermFilterBanner compact /></div>
              )}
            </div>

            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au1">
              <SectionLabel icon={Users}>จำนวนผู้เข้าร่วม</SectionLabel>
              <div className="flex items-center gap-4 mb-4">
                <button onClick={() => setAttendees(Math.max(1, attendees - 1))}
                  className="w-10 h-10 rounded-xl border-2 border-blue-100 bg-blue-50 text-blue-600 text-xl font-bold flex items-center justify-center hover:bg-blue-100 transition-all active:scale-90">−</button>
                <div className="flex-1 text-center">
                  <span className="text-5xl font-extrabold text-slate-900">{attendees}</span>
                  <span className="text-sm text-slate-400 ml-2">คน</span>
                </div>
                <button onClick={() => setAttendees(attendees + 1)}
                  className={`w-10 h-10 rounded-xl ${accentBg} text-white text-xl font-bold flex items-center justify-center ${accentHov} shadow-sm ${accentShadow} active:scale-90`}>+</button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {ATTENDEES_PRESETS.map(n => <Chip key={n} active={attendees === n} onClick={() => setAttendees(n)}>{n} คน</Chip>)}
              </div>
            </div>

            {isTermMode ? (
              <div className="bg-white border border-indigo-100 rounded-2xl p-5 shadow-sm au2">
                <SectionLabel icon={Calendar}>วันในสัปดาห์</SectionLabel>
                <div className="grid grid-cols-4 gap-1.5">
                  {DAYS_OF_WEEK.map(d => (
                    <button key={d.value} onClick={() => setDayOfWeek(d.value)}
                      className={`py-2.5 rounded-xl text-xs font-bold border-2 transition-all duration-150
                        ${dayOfWeek === d.value
                          ? 'bg-indigo-700 border-indigo-700 text-white shadow-sm'
                          : 'bg-white border-indigo-100 text-slate-600 hover:border-indigo-300 hover:bg-indigo-50'}`}>
                      {d.label}
                    </button>
                  ))}
                </div>
                {dayOfWeek != null && (
                  <p className="mt-2 text-xs text-indigo-600 font-semibold">ทุก{getDayLabel(dayOfWeek)}</p>
                )}
              </div>
            ) : (
              <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au2">
                <SectionLabel icon={Calendar}>วันที่</SectionLabel>
                <input type="date" value={date} min={new Date().toISOString().split('T')[0]}
                  onChange={e => setDate(e.target.value)}
                  className="w-full border-2 border-blue-100 rounded-xl px-4 py-2.5 text-sm text-slate-800 bg-blue-50/40 outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 transition-all"
                  style={{fontFamily:"inherit"}} />
              </div>
            )}

            {isTermMode && (
              <div className="bg-white border border-indigo-100 rounded-2xl p-5 shadow-sm au2">
                <SectionLabel>ข้อมูลเทอม</SectionLabel>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">ชื่อเทอม</label>
                    <input type="text" value={termName} onChange={e => setTermName(e.target.value)}
                      placeholder="เช่น ภาคเรียนที่ 1/2568"
                      className="w-full border-2 border-indigo-100 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100 transition-all"
                      style={{fontFamily:"inherit"}} />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-slate-500 mb-1 block">วันเริ่มเทอม <span className="text-red-400">*</span></label>
                      <input type="date" value={termStart} onChange={e => setTermStart(e.target.value)}
                        className="w-full border-2 border-indigo-100 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-indigo-500 transition-all"
                        style={{fontFamily:"inherit"}} />
                    </div>
                    <div>
                      <label className="text-xs text-slate-500 mb-1 block">วันสิ้นสุดเทอม <span className="text-red-400">*</span></label>
                      <input type="date" value={termEnd} onChange={e => setTermEnd(e.target.value)}
                        className="w-full border-2 border-indigo-100 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-indigo-500 transition-all"
                        style={{fontFamily:"inherit"}} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au3">
              <SectionLabel icon={Clock}>เวลาเริ่มต้น</SectionLabel>
              <div className="grid grid-cols-4 gap-1.5 mb-4">
                {TIME_SLOTS.map(t => (
                  <button key={t} onClick={() => setStartTime(t)}
                    className={`py-2.5 rounded-xl text-xs font-semibold border-2 transition-all duration-150
                      ${startTime === t
                        ? `${accentBg} border-transparent text-white shadow-sm`
                        : 'bg-white border-blue-100 text-slate-600 hover:border-blue-300 hover:bg-blue-50'}`}>
                    {t}
                  </button>
                ))}
              </div>
              <p className="text-xs font-bold text-blue-600 uppercase tracking-widest mb-2.5 flex items-center gap-1.5"><Clock size={10} />ระยะเวลา</p>
              <div className="flex gap-1.5">
                {DURATIONS.map(d => <Chip key={d.hours} active={duration === d.hours} onClick={() => setDuration(d.hours)} className="flex-1 justify-center">{d.label}</Chip>)}
              </div>
              {startTime && (
                <div className={`mt-3 ${accentBg} rounded-xl px-4 py-3 flex justify-between items-center si`}>
                  <span className="text-sm font-bold text-white">{startTime} – {endTime} น.</span>
                  <span className="text-xs text-white/60">
                    {isTermMode && dayOfWeek != null ? `ทุก${getDayLabel(dayOfWeek)}` : formatDateShort(date)}
                  </span>
                </div>
              )}
            </div>

            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au3">
              <SectionLabel icon={MapPin}>อาคาร</SectionLabel>
              <div className="flex flex-wrap gap-1.5">
                {BUILDINGS.map(b => <Chip key={b.code} active={building === b.code} onClick={() => setBuilding(b.code)}>{b.label}</Chip>)}
              </div>
            </div>

            {/* ── อุปกรณ์ที่ต้องการ (mobile) ── */}
            <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au3">
              <div className="flex items-center justify-between mb-3">
                <SectionLabel>อุปกรณ์ที่ต้องการ</SectionLabel>
                {selectedEquipments.length > 0 && (
                  <button
                    onClick={() => setSelectedEquipments([])}
                    className="text-xs text-slate-400 hover:text-red-500 flex items-center gap-1 transition-colors"
                  >
                    <X size={11} />ล้าง
                  </button>
                )}
              </div>
              <EquipmentSelector selected={selectedEquipments} onChange={setSelectedEquipments} compact />
              {selectedEquipments.length > 0 && (
                <div className="mt-2.5 flex items-center gap-2 bg-blue-50 border border-blue-100 rounded-xl px-3 py-2">
                  <Filter size={10} className="text-blue-500 flex-shrink-0" />
                  <p className="text-xs text-blue-600 font-semibold">
                    มี: {selectedEquipments.map(k => EQUIPMENT_PRESETS.find(p => p.key === k)?.label).join(', ')}
                  </p>
                </div>
              )}
            </div>

            <button onClick={handleSearch} disabled={loading}
              className={`au4 w-full ${accentBg} ${accentHov} disabled:bg-slate-400 text-white rounded-2xl py-4 text-sm font-bold flex items-center justify-center gap-2.5 shadow-lg ${accentShadow} transition-all active:scale-95 disabled:cursor-not-allowed`}>
              {loading
                ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />ค้นหา...</>
                : <><Search size={15} />ค้นหาห้องว่าง</>}
            </button>
          </>
        )}

        {/* ── STEP 2 ── */}
        {step === 2 && (
          <>
            <div className={`${accentBg} rounded-2xl px-4 py-3 flex items-center justify-between flex-wrap gap-2 shadow-md ${accentShadow} au`}>
              <div className="flex gap-3 flex-wrap items-center text-sm">
                <span className="font-bold text-white">{attendees} คน</span>
                {isTermMode
                  ? <span className="text-white/80 text-xs">ทุก{getDayLabel(dayOfWeek)}</span>
                  : <span className="text-white/80 text-xs">{formatDateShort(date)}</span>
                }
                <span className="text-white/80 text-xs">{startTime}–{endTime}</span>
                <span className="text-white/80 text-xs">จุ {attendees}–{attendees + CAPACITY_BUFFER} คน</span>
                {isTermMode && (
                  <span className="bg-white/15 text-white text-xs font-semibold rounded-full px-2 py-0.5 flex items-center gap-1">
                    <Filter size={9} />ห้องเรียน/Lecture
                  </span>
                )}
                {selectedEquipments.length > 0 && (
                  <span className="bg-white/15 text-white text-xs font-semibold rounded-full px-2 py-0.5 flex items-center gap-1">
                    <Filter size={9} />
                    {selectedEquipments.map(k => EQUIPMENT_PRESETS.find(p => p.key === k)?.icon).join('')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 bg-yellow-300 text-yellow-900 text-xs font-bold rounded-full px-3 py-1">
                <Zap size={10} />AI
              </div>
            </div>

            {rooms.length > 0 && <SummaryTiles rooms={rooms} layout="grid" />}

            {rooms.length === 0 ? (
              <div className="bg-white border border-blue-100 rounded-2xl py-12 text-center au">
                <Building2 size={32} className="text-blue-200 mx-auto mb-3" />
                <p className="text-sm font-semibold text-blue-700 mb-1">
                  {isTermMode ? 'ไม่พบห้องเรียน/Lecture ที่ว่าง' : 'ไม่พบห้องว่างที่เหมาะสม'}
                </p>
                <p className="text-xs text-slate-400 mb-3">สำหรับ {attendees}–{attendees + CAPACITY_BUFFER} คน</p>
                <button onClick={() => setStep(1)} className="text-xs text-blue-600 hover:underline">← ค้นหาใหม่</button>
              </div>
            ) : rooms.map((room, idx) => (
              <RoomCard key={room.id} room={room} idx={idx} compact isTermMode={isTermMode}
                selectedEquipments={selectedEquipments}
                onClick={() => { setSelectedRoom(room); setStep(3) }} />
            ))}
          </>
        )}

        {/* ── STEP 3 ── */}
        {step === 3 && selectedRoom && (() => {
          const level = getDemandLevel(selectedRoom)
          const cfg   = FORECAST_CONFIG[level]
          return (
            <>
              <div className="au"><CheckInReminder startTime={startTime} compact /></div>

              <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au1">
                <SectionLabel icon={Building2}>ห้องที่เลือก</SectionLabel>
                <div className="h-0.5 bg-gradient-to-r from-yellow-300 to-yellow-500 rounded-full mb-4" />
                <div className="mb-4">
                  <div className="flex items-center gap-2 flex-wrap mb-0.5">
                    <p className="text-base font-bold text-slate-900">{selectedRoom.name}</p>
                    <RoomStatusBadge status={selectedRoom.status} />
                  </div>
                  <p className="text-xs text-slate-500">{selectedRoom.building_name} · ชั้น {selectedRoom.floor} · {selectedRoom.room_type}</p>
                  {selectedRoom.description && <p className="text-xs text-slate-400 mt-1">{selectedRoom.description}</p>}
                </div>

                {/* booking detail table */}
                <div className="border-2 border-blue-50 rounded-xl overflow-hidden mb-4">
                  {[
                    { label: 'ประเภท',      value: isTermMode ? 'จองทั้งเทอม' : 'จองรายวัน' },
                    isTermMode
                      ? { label: 'วัน',       value: `ทุก${getDayLabel(dayOfWeek)}` }
                      : { label: 'วันที่',    value: formatDate(date) },
                    { label: 'เวลา',         value: `${startTime}–${endTime} น.` },
                    { label: 'ผู้เข้าร่วม', value: `${attendees} คน` },
                    { label: 'ความจุห้อง',  value: `${selectedRoom.capacity} คน` },
                    ...(isTermMode && termName ? [{ label: 'เทอม', value: termName }] : []),
                    ...(isTermMode && termStart && termEnd
                      ? [{ label: 'ช่วงเทอม', value: `${formatDateShort(termStart)} – ${formatDateShort(termEnd)}` }]
                      : []),
                  ].map((r, i) => (
                    <div key={i} className="flex justify-between px-4 py-2.5 bg-white border-b border-blue-50 last:border-0">
                      <span className="text-xs text-slate-500">{r.label}</span>
                      <span className="text-sm font-semibold text-slate-800">{r.value}</span>
                    </div>
                  ))}
                </div>

                {/* อุปกรณ์ในห้อง */}
                {selectedRoom.facilities?.length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                      <span>🔧</span>อุปกรณ์ในห้อง
                      <span className="text-slate-300 font-normal">({selectedRoom.facilities.length} รายการ)</span>
                    </p>
                    <FacilityTags
                      facilities={selectedRoom.facilities}
                      compact={false}
                      highlight={selectedEquipments}
                    />
                  </div>
                )}

                {cfg.badge !== '—' && (
                  <div className={`flex items-center gap-2 rounded-xl px-4 py-3 ${cfg.pillCls}`}>
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: cfg.dotColor }} />
                    <span className={`text-xs font-bold ${cfg.textCls}`}>{cfg.badge} — {cfg.sub}</span>
                  </div>
                )}
              </div>

              <div className="bg-white border border-blue-100 rounded-2xl p-5 shadow-sm au2">
                <SectionLabel>{isTermMode ? 'ชื่อวิชา / กิจกรรม' : 'หัวข้อการประชุม'}</SectionLabel>
                <input type="text" autoFocus
                  placeholder={isTermMode ? 'เช่น วิชา CS101, กิจกรรมชมรม...' : 'เช่น ประชุมกลุ่ม, นำเสนองาน...'}
                  value={title} onChange={e => setTitle(e.target.value)}
                  className="w-full border-2 border-blue-100 rounded-xl px-4 py-2.5 text-sm text-slate-800 bg-blue-50/40 outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 transition-all placeholder:text-slate-400"
                  style={{fontFamily:"inherit"}} />
              </div>

              <button onClick={handleBook} disabled={bookingLoading}
                className={`au3 w-full ${accentBg} ${accentHov} disabled:bg-slate-400 text-white rounded-2xl py-4 font-bold text-sm flex items-center justify-center gap-2.5 shadow-lg ${accentShadow} transition-all active:scale-95 disabled:cursor-not-allowed`}>
                {bookingLoading
                  ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />กำลังจอง...</>
                  : <><CheckCircle size={15} />{isTermMode ? 'ยืนยันจองทั้งเทอม' : 'ยืนยันการจอง'}</>}
              </button>
            </>
          )
        })()}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROOT
// ═══════════════════════════════════════════════════════════════════════════════

export default function SearchPage() {
  const navigate  = useNavigate()
  const isMobile  = useDevice()
  const [step, setStep]                           = useState(1)
  const [bookingType, setBookingType]             = useState('daily')
  const [attendees, setAttendees]                 = useState(5)
  const [date, setDate]                           = useState(new Date().toISOString().split('T')[0])
  const [dayOfWeek, setDayOfWeek]                 = useState(null)
  const [startTime, setStartTime]                 = useState('')
  const [duration, setDuration]                   = useState(1)
  const [building, setBuilding]                   = useState('')
  const [rooms, setRooms]                         = useState([])
  const [selectedRoom, setSelectedRoom]           = useState(null)
  const [title, setTitle]                         = useState('')
  const [loading, setLoading]                     = useState(false)
  const [bookingLoading, setBookingLoading]       = useState(false)
  const [success, setSuccess]                     = useState(false)
  const [error, setError]                         = useState('')
  const [termStart, setTermStart]                 = useState('')
  const [termEnd, setTermEnd]                     = useState('')
  const [termName, setTermName]                   = useState('ภาคเรียนที่ 1/2568')
  const [selectedEquipments, setSelectedEquipments] = useState([])   // ← NEW

  const endTime = startTime ? addHours(startTime, duration) : ''

 const handleSearch = async () => {
  if (!startTime) { setError('กรุณาเลือกเวลาเริ่มต้น'); return }
  if (bookingType === 'term' && dayOfWeek == null) { setError('กรุณาเลือกวันในสัปดาห์'); return }
  if (bookingType === 'term' && !termStart) { setError('กรุณาเลือกวันเริ่มเทอม'); return }
  if (bookingType === 'term' && !termEnd) { setError('กรุณาเลือกวันสิ้นสุดเทอม'); return }
  if (bookingType === 'daily' && !date) { setError('กรุณาเลือกวันที่'); return }

  setError(''); setLoading(true)
  try {
    const payload = {
      attendees,
      start_time: startTime,
      end_time: endTime,
      building_code: building || undefined,
      booking_type: bookingType === 'term' ? 'term' : 'dynamic',
      ...(bookingType === 'term'
        ? {
            day_of_week: dayOfWeek,
            term_start: termStart,
            term_end: termEnd,
            term_name: termName || 'ภาคเรียนที่ 1/2568',
          }
        : { date }
      ),
    }

    const res = await api.post('/rooms/search/', payload)
    console.log('ห้องแรกเต็มๆ:', JSON.stringify(res.data[0], null, 2))
    console.log('ผลลัพธ์:', res.data)
    console.log('facilities ห้องแรก:', res.data[0]?.facilities)
    console.log('จำนวนห้องก่อนกรอง:', res.data.length)

    let filtered = res.data.filter(r =>
      r.capacity >= attendees && r.capacity <= attendees + CAPACITY_BUFFER
    )

    if (bookingType === 'term') {
      filtered = filtered.filter(r => isClassroomType(r))
    }

    if (selectedEquipments.length > 0) {
      filtered = filtered.filter(r => roomHasEquipments(r, selectedEquipments))
    }

    setRooms(filtered)
    setStep(2)
  } catch (err) {
    console.log('error full:', err)
    console.log('error message:', err.message)
    setError('เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง')
  } finally {
    setLoading(false)
  }
}

const handleBook = async () => {
  if (!selectedRoom) {
    setError('ไม่พบห้องที่เลือก กรุณาเลือกห้องใหม่')
    return
  }

  setBookingLoading(true)
  setError('')

  try {
    let response

    if (bookingType === 'term') {
      const termPayload = {
        room: selectedRoom.id,
        subject_name: title,
        subject_code: 'N/A',
        attendees: parseInt(attendees),
        day_of_week: dayOfWeek,
        start_time: startTime,
        end_time: endTime,
        term_start: termStart,
        term_end: termEnd,
        term_name: termName,
        note: '',
      }
      response = await api.post('term-bookings/', termPayload)
    } else {
      const dynamicPayload = {
        room: selectedRoom.id,
        title: title,
        attendees: parseInt(attendees),
        start_time: `${date}T${startTime}:00`,
        end_time: `${date}T${endTime}:00`,
        note: '',
      }
      response = await api.post('bookings/', dynamicPayload)
    }

    if (response.status === 201 || response.status === 200) {
      setSuccess(true)
    } else {
      setError('จองไม่สำเร็จ กรุณาลองใหม่')
    }
  } catch (err) {
    const errorData = err.response?.data
    const msg = errorData ? JSON.stringify(errorData) : 'เกิดข้อผิดพลาด กรุณาลองใหม่'
    setError(msg)
  } finally {
    setBookingLoading(false)
  }
}

  const shared = {
    bookingType, setBookingType,
    formProps: {
      attendees, setAttendees, date, setDate,
      startTime, setStartTime, duration, setDuration,
      building, setBuilding, endTime, loading, handleSearch, error,
      dayOfWeek, setDayOfWeek,
      termStart, setTermStart,
      termEnd, setTermEnd,
      termName, setTermName,
      selectedEquipments, setSelectedEquipments,   // ← NEW
    },
    resultProps:  { rooms, setSelectedRoom },
    confirmProps: { selectedRoom, title, setTitle, bookingLoading, handleBook, success },
  }

  return isMobile
    ? <MobileLayout step={step} setStep={setStep} navigate={navigate} {...shared} />
    : <DesktopLayout step={step} setStep={setStep} navigate={navigate} {...shared} />
}