import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Clock, BarChart2, TrendingUp, Calendar, X, Building2, AlertTriangle, Zap, UserX } from 'lucide-react'
import api from '../api/axios'

const ANIM = `
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes scaleIn{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:scale(1)}}
@keyframes rot{to{transform:rotate(360deg)}}
.au{animation:fadeUp .28s ease both}
.au1{animation:fadeUp .28s .06s ease both}
.au2{animation:fadeUp .28s .12s ease both}
.si{animation:scaleIn .22s ease both}
`

function useDevice() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', fn); return () => window.removeEventListener('resize', fn)
  }, [])
  return isMobile
}

const STATUS_CFG = {
  approved:  { label:'กำลังจอง',   bg:'bg-emerald-50',  text:'text-emerald-700', dot:'#10b981' },
  cancelled: { label:'ยกเลิกแล้ว', bg:'bg-red-50',      text:'text-red-600',     dot:'#f87171' },
  completed: { label:'เสร็จสิ้น',  bg:'bg-slate-100',   text:'text-slate-500',   dot:'#94a3b8' },
  no_show:   { label:'No-Show',    bg:'bg-orange-50',   text:'text-orange-700',  dot:'#f97316' },
}
const getS = s => STATUS_CFG[s] || { label:s, bg:'bg-slate-100', text:'text-slate-500', dot:'#94a3b8' }

// ── No-Show Rate Card ──────────────────────────────────
function NoShowCard({ bookings }) {
  const total   = bookings.filter(b => ['approved','completed','cancelled','no_show'].includes(b.status)).length
  const noShow  = bookings.filter(b => b.status === 'no_show').length
  const rate    = total > 0 ? (noShow / total * 100).toFixed(1) : 0
  const isHigh  = rate >= 20
  const isMed   = rate >= 10

  // top 3 users ที่ no-show บ่อย
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
        <span className={`text-sm font-bold ${isHigh?'text-red-700':isMed?'text-orange-700':'text-slate-700'}`}>
          อัตรา No-Show
        </span>
        {isHigh && <span className="text-xs bg-red-100 text-red-700 border border-red-200 px-2 py-0.5 rounded-full font-bold ml-auto">⚠️ สูงมาก</span>}
        {isMed && !isHigh && <span className="text-xs bg-orange-100 text-orange-700 border border-orange-200 px-2 py-0.5 rounded-full font-bold ml-auto">ควรดูแล</span>}
      </div>

      <div className="flex items-end gap-3 mb-3">
        <span className={`text-4xl font-extrabold ${isHigh?'text-red-600':isMed?'text-orange-600':'text-slate-700'}`}>
          {rate}%
        </span>
        <span className="text-sm text-slate-500 mb-1.5">{noShow} / {total} การจอง</span>
      </div>

      {/* progress bar */}
      <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden mb-4">
        <div className="h-full rounded-full transition-all"
          style={{
            width: `${Math.min(rate, 100)}%`,
            background: isHigh ? '#ef4444' : isMed ? '#f97316' : '#10b981',
          }} />
      </div>

      {topUsers.length > 0 && (
        <>
          <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">No-Show บ่อยที่สุด</p>
          {topUsers.map(([name, cnt], i) => (
            <div key={i} className="flex justify-between text-xs py-1.5 border-b border-slate-100 last:border-0">
              <span className="text-slate-700 font-medium">{name}</span>
              <span className={`font-bold ${cnt >= 3 ? 'text-red-600' : 'text-orange-500'}`}>{cnt} ครั้ง {cnt >= 3 ? '⚠️' : ''}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

function BookingDetailModal({ booking, onClose, onCancel, fmtTime, fmtDateFull }) {
  if (!booking) return null
  const s = getS(booking.status)
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
              {icon:'📋',label:'หัวข้อ',     value:booking.title},
              {icon:'📅',label:'วันที่',      value:fmtDateFull(booking.start_time)},
              {icon:'⏰',label:'เวลาเริ่ม',   value:fmtTime(booking.start_time)+' น.'},
              {icon:'⏱️',label:'เวลาสิ้นสุด', value:fmtTime(booking.end_time)+' น.'},
              {icon:'👥',label:'จำนวนคน',    value:`${booking.attendees} คน`},
            ].map((r,i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5 bg-white border-b border-blue-50 last:border-0">
                <span className="text-sm w-5 flex-shrink-0">{r.icon}</span>
                <span className="text-xs text-slate-500 w-20 flex-shrink-0">{r.label}</span>
                <span className="text-sm font-semibold text-slate-800 flex-1">{r.value}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-300 text-center mb-4">ID: #{booking.id}</p>
          {booking.status === 'approved' && (
            <button onClick={() => onCancel(booking.id)} className="w-full border-2 border-red-100 text-red-500 hover:bg-red-50 py-3 rounded-2xl font-bold text-sm transition-colors">
              ยกเลิกการจองนี้
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

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

// ── DESKTOP ────────────────────────────────────────────
function DesktopAdmin({ dashboard, bookings, weekStats, tab, setTab, selectedBooking,
  setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull, navigate }) {
  const activeB    = bookings.filter(b=>b.status==='approved')
  const cancelledB = bookings.filter(b=>b.status==='cancelled')
  const noShowB    = bookings.filter(b=>b.status==='no_show')
  const tabs = [
    {key:'active',   label:'กำลังจอง', count:activeB.length},
    {key:'overview', label:'ภาพรวม',   count:null},
    {key:'noshow',   label:'No-Show',  count:noShowB.length},
    {key:'all',      label:'ทั้งหมด',  count:bookings.length},
  ]
  return (
    <div className="min-h-screen bg-slate-100" style={{fontFamily:"'Sarabun','Noto Sans Thai',sans-serif"}}>
      <style>{ANIM}</style>
      <div className="bg-blue-700 shadow-lg shadow-blue-900/20">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => navigate('/')} className="flex items-center gap-2 text-white/80 hover:text-white text-sm font-medium"><ArrowLeft size={15} />หน้าหลัก</button>
          <div className="h-5 w-px bg-white/20" />
          <span className="text-white font-bold text-sm">Admin Dashboard</span>
          <div className="ml-auto flex items-center gap-1.5 bg-yellow-300 text-yellow-900 text-xs font-bold rounded-full px-3 py-1.5">
            <Zap size={10} />AI Forecast Active
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
                {label:'จองวันนี้',      value:dashboard?.today_bookings??0,  color:'text-blue-700'},
                {label:'กำลังจองทั้งหมด',value:activeB.length,                 color:'text-emerald-600'},
                {label:'ยกเลิกแล้ว',    value:cancelledB.length,              color:'text-red-500'},
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
              {activeB.length === 0
                ? <div className="bg-white border border-blue-100 rounded-2xl py-16 text-center shadow-sm">
                    <Calendar size={40} className="text-blue-200 mx-auto mb-3" />
                    <p className="text-slate-400 text-sm">ไม่มีการจองที่กำลังดำเนินอยู่</p>
                  </div>
                : activeB.map(b => (
                    <div key={b.id}
                      className="bg-white border border-blue-100 rounded-2xl px-6 py-4 flex items-center gap-4 cursor-pointer hover:shadow-md hover:-translate-y-0.5 transition-all"
                      style={{borderLeftWidth:4,borderLeftColor:'#10b981'}}
                      onClick={() => setSelectedBooking(b)}>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1">
                          <p className="font-bold text-slate-900 truncate">{b.title}</p>
                          <span className="text-xs bg-emerald-50 text-emerald-700 px-2.5 py-0.5 rounded-full font-semibold flex-shrink-0">กำลังจอง</span>
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
                  ))
              }
            </div>
          </div>
        )}

        {tab === 'overview' && dashboard && (
          <div className="grid grid-cols-3 gap-6">
            <div className="space-y-4 au">
              {[
                {label:'จองวันนี้',    value:dashboard.today_bookings??0,        icon:'📅',color:'text-blue-700'},
                {label:'ห้องทั้งหมด', value:dashboard.total_rooms??0,            icon:'🏢',color:'text-slate-700'},
                {label:'อัตราการใช้', value:`${dashboard.utilization_rate??0}%`, icon:'📊',color:'text-emerald-600'},
                {label:'กำลังจอง',   value:activeB.length,                       icon:'✅',color:'text-blue-600'},
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
                      const pct = Math.round((room.count/(dashboard.popular_rooms[0]?.count||1))*100)
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
              const s = getS(b.status)
              return (
                <div key={b.id} onClick={() => setSelectedBooking(b)}
                  className="bg-white border border-blue-100 rounded-xl px-6 py-4 flex items-center gap-4 cursor-pointer hover:bg-blue-50/40 transition-colors">
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

// ── MOBILE ─────────────────────────────────────────────
function MobileAdmin({ dashboard, bookings, weekStats, tab, setTab, selectedBooking,
  setSelectedBooking, handleCancel, fmtDate, fmtTime, fmtDateFull, navigate }) {
  const activeB = bookings.filter(b=>b.status==='approved')
  const cancelledB = bookings.filter(b=>b.status==='cancelled')
  const noShowB = bookings.filter(b=>b.status==='no_show')
  const tabs = [
    {key:'active',   label:'จอง',     count:activeB.length},
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
          <div className="flex items-center gap-1 bg-yellow-300 text-yellow-900 text-xs font-bold rounded-full px-2 py-0.5"><Zap size={9} />AI</div>
        </div>
        <div className="h-0.5 bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-300" />
        <div className="max-w-lg mx-auto px-4 flex border-t border-white/10">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex-1 flex items-center justify-center gap-1 py-2.5 text-xs font-semibold border-b-2 transition-colors
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
            <div className="grid grid-cols-3 gap-2 au">
              {[
                {label:'วันนี้',     value:dashboard?.today_bookings??0, color:'text-blue-700'},
                {label:'กำลังจอง',  value:activeB.length,               color:'text-emerald-600'},
                {label:'ยกเลิก',    value:cancelledB.length,            color:'text-red-500'},
              ].map((s,i) => (
                <div key={i} className="bg-white border border-blue-100 rounded-2xl p-3 text-center shadow-sm">
                  <p className={`text-2xl font-extrabold ${s.color}`}>{s.value}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>
            <div className="au1"><NoShowCard bookings={bookings} /></div>
            {activeB.map(b => (
              <div key={b.id}
                className="bg-white border border-blue-100 rounded-2xl px-4 py-4 flex items-center gap-3 cursor-pointer hover:shadow-md transition-all au2"
                style={{borderLeftWidth:4,borderLeftColor:'#10b981'}}
                onClick={() => setSelectedBooking(b)}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <p className="font-bold text-slate-900 text-sm truncate">{b.title}</p>
                    {b.checked_in && <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-bold flex-shrink-0">✓ Check-in</span>}
                  </div>
                  <p className="text-xs text-blue-600 mb-1">{b.room_name}</p>
                  <div className="flex gap-3 text-xs text-slate-400">
                    <span>📅 {fmtDate(b.start_time)}</span>
                    <span>⏰ {fmtTime(b.start_time)}</span>
                  </div>
                </div>
                <button onClick={e=>{e.stopPropagation();handleCancel(b.id)}} className="text-xs text-red-400 border border-red-100 px-2.5 py-1.5 rounded-xl flex items-center gap-1 flex-shrink-0">
                  <X size={11} />ยกเลิก
                </button>
              </div>
            ))}
          </>
        )}

        {tab === 'overview' && dashboard && (
          <>
            <div className="grid grid-cols-2 gap-2 au">
              {[
                {label:'จองวันนี้',   value:dashboard.today_bookings??0,        icon:'📅',color:'text-blue-700'},
                {label:'ห้องทั้งหมด',value:dashboard.total_rooms??0,            icon:'🏢',color:'text-slate-700'},
                {label:'อัตราการใช้',value:`${dashboard.utilization_rate??0}%`, icon:'📊',color:'text-emerald-600'},
                {label:'กำลังจอง',   value:activeB.length,                      icon:'✅',color:'text-blue-600'},
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
              <p className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2"><BarChart2 size={13} className="text-blue-600" />การจองรายวัน 7 วัน</p>
              <BarChartBlock weekStats={weekStats} />
            </div>
          </>
        )}

        {tab === 'noshow' && (
          <>
            <div className="au"><NoShowCard bookings={bookings} /></div>
            {noShowB.length === 0
              ? <div className="bg-white border border-blue-100 rounded-2xl py-10 text-center au1"><p className="text-slate-400 text-sm">ไม่มีรายการ No-Show 🎉</p></div>
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
              const s = getS(b.status)
              return (
                <div key={b.id} onClick={() => setSelectedBooking(b)}
                  className="bg-white border border-blue-100 rounded-xl px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-blue-50/40">
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

// ── ROOT ───────────────────────────────────────────────
export default function AdminPage() {
  const navigate = useNavigate()
  const isMobile = useDevice()
  const [dashboard,setDashboard]   = useState(null)
  const [bookings,setBookings]     = useState([])
  const [tab,setTab]               = useState('active')
  const [loading,setLoading]       = useState(true)
  const [weekStats,setWeekStats]   = useState([])
  const [selectedBooking,setSelectedBooking] = useState(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [dashRes,bookingRes] = await Promise.all([api.get('/dashboard/'),api.get('/bookings/')])
        setDashboard(dashRes.data)
        const all = bookingRes.data.results || []
        setBookings(all)
        const days = ['อา','จ','อ','พ','พฤ','ศ','ส']
        const stats = []
        for (let i=6;i>=0;i--) {
          const d = new Date(); d.setDate(d.getDate()-i)
          const ds = d.toISOString().split('T')[0]
          stats.push({day:days[d.getDay()],date:ds,count:all.filter(b=>new Date(b.start_time).toISOString().split('T')[0]===ds&&b.status==='approved').length})
        }
        setWeekStats(stats)
      } catch { navigate('/login') } finally { setLoading(false) }
    }; load()
  }, [])

  const handleCancel = async (id) => {
    if (!confirm('ยืนยันการยกเลิกการจองนี้?')) return
    try {
      await api.post(`/bookings/${id}/cancel/`)
      setBookings(prev => prev.map(b=>b.id===id?{...b,status:'cancelled'}:b))
      if (selectedBooking?.id===id) setSelectedBooking(prev=>({...prev,status:'cancelled'}))
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

  const props = { dashboard, bookings, weekStats, tab, setTab, selectedBooking, setSelectedBooking,
    handleCancel, fmtDate, fmtTime, fmtDateFull, navigate }
  return isMobile ? <MobileAdmin {...props} /> : <DesktopAdmin {...props} />
}