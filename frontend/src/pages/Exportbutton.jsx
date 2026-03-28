// ExportButton.jsx — วางในโฟลเดอร์เดียวกับ AdminPage.jsx
// แล้ว import ใน AdminPage:
//   import ExportButton from './ExportButton'
// วางปุ่มในส่วน Navbar ของทั้ง DesktopAdmin และ MobileAdmin

import { useState } from 'react'
import { Download, ChevronDown, X, FileSpreadsheet, Check } from 'lucide-react'
import api from '../api/axios'

const SHEETS = [
  { key: 'users',         label: 'ผู้ใช้งาน',      icon: '👤' },
  { key: 'buildings',     label: 'อาคาร',          icon: '🏛️' },
  { key: 'rooms',         label: 'ห้อง',           icon: '🚪' },
  { key: 'facilities',    label: 'อุปกรณ์ในห้อง', icon: '🖥️' },
  { key: 'bookings',      label: 'การจอง',         icon: '📅' },
  { key: 'logs',          label: 'ประวัติการจอง',  icon: '📋' },
  { key: 'forecasts',     label: 'ผลพยากรณ์ AI',  icon: '🤖' },
  { key: 'notifications', label: 'การแจ้งเตือน',  icon: '🔔' },
  { key: 'stats',         label: 'สถิติห้อง',      icon: '📊' },
]

export default function ExportButton({ isMobile = false }) {
  const [open,     setOpen]     = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [selected, setSelected] = useState(new Set(['all']))
  const [done,     setDone]     = useState(false)

  const toggleSheet = (key) => {
    if (key === 'all') {
      setSelected(new Set(['all']))
      return
    }
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

      const res = await api.get(`export/excel/?sheets=${sheets}`, {
        responseType: 'blob',
      })

      // เช็คว่า server ส่ง error JSON กลับมาแทน blob
      const contentType = res.headers['content-type'] || ''
      if (contentType.includes('application/json')) {
        const text = await res.data.text()
        alert('Server Error: ' + text)
        return
      }

      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      })
      const url  = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href  = url
      const now  = new Date().toISOString().slice(0, 10).replace(/-/g, '')
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

  const Spinner = () => (
    <div style={{
      width: 14, height: 14,
      border: '2px solid rgba(255,255,255,0.3)',
      borderTopColor: '#fff',
      borderRadius: '50%',
      animation: 'spin 0.7s linear infinite',
    }} />
  )

  return (
    <div className="relative">
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>

      {/* Trigger Button */}
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 font-semibold transition-all active:scale-95
          ${isMobile
            ? 'text-xs bg-emerald-500 hover:bg-emerald-600 text-white px-2.5 py-1.5 rounded-lg'
            : 'text-xs bg-emerald-500 hover:bg-emerald-600 text-white px-3 py-1.5 rounded-lg shadow-sm'
          }`}
      >
        <Download size={isMobile ? 12 : 13} />
        {!isMobile && 'Export Excel'}
        <ChevronDown size={11} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown Panel */}
      {open && (
        <div
          className="absolute right-0 top-10 w-72 bg-white border border-blue-100 rounded-2xl shadow-2xl z-50 overflow-hidden"
          style={{ animation: 'fadeUp .2s ease both' }}
        >
          {/* Header */}
          <div className="px-4 py-3 flex items-center justify-between border-b border-blue-50 bg-emerald-50">
            <div className="flex items-center gap-2">
              <FileSpreadsheet size={15} className="text-emerald-600" />
              <span className="text-sm font-bold text-emerald-800">Export ข้อมูล Excel</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-600">
              <X size={14} />
            </button>
          </div>

          {/* Sheet Selection */}
          <div className="px-4 py-3">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">
              เลือก Sheet ที่ต้องการ
            </p>

            {/* All option */}
            <button
              onClick={() => toggleSheet('all')}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-semibold mb-1 transition-all
                ${isAll
                  ? 'bg-emerald-600 text-white'
                  : 'hover:bg-emerald-50 text-slate-700 border border-slate-100'
                }`}
            >
              <span>📦</span>
              <span className="flex-1 text-left">ทั้งหมด (All Sheets)</span>
              {isAll && <Check size={13} />}
            </button>

            <div className="border-t border-slate-100 my-2" />

            {/* Individual sheets */}
            <div className="space-y-0.5 max-h-52 overflow-y-auto pr-1">
              {SHEETS.map(s => {
                const active = !isAll && selected.has(s.key)
                return (
                  <button
                    key={s.key}
                    onClick={() => toggleSheet(s.key)}
                    className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                      ${active
                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                        : 'hover:bg-slate-50 text-slate-600 border border-transparent'
                      }`}
                  >
                    <span>{s.icon}</span>
                    <span className="flex-1 text-left">{s.label}</span>
                    {active && <Check size={11} className="text-emerald-600" />}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Footer */}
          <div className="px-4 pb-4">
            <p className="text-xs text-slate-400 mb-2.5 text-center">
              {isAll
                ? 'จะ export ทุก Sheet (10 Sheet)'
                : `เลือก ${selected.size} Sheet`
              }
            </p>
            <button
              onClick={handleExport}
              disabled={loading || done}
              className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold transition-all active:scale-95 disabled:cursor-not-allowed
                ${done
                  ? 'bg-emerald-500 text-white'
                  : 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-md shadow-emerald-200 disabled:bg-slate-300'
                }`}
            >
              {loading
                ? <><Spinner />กำลัง Export...</>
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