import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/'
// อ้างอิงจาก API_BASE_URL ตัวเดียวกัน กันพลาดเวลาแก้ host ตอน deploy จริง
// (ต้องแก้แค่จุดเดียว ไม่ต้องไล่หาทุกที่ที่ hardcode url ไว้)
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws').replace(/\/api\/$/, '/ws/')

const api = axios.create({
  baseURL: API_BASE_URL,
  // 60s ไม่ใช่ 15s เดิม — backend อยู่บน Render free tier ที่ sleep เวลาไม่มี
  // คนใช้งาน request แรกหลัง sleep (cold start) อาจใช้เวลา 30-50 วินาทีกว่า
  // จะตื่น ถ้า timeout สั้นกว่านั้น request จะพังก่อนที่ server จะตอบจริงๆ
  timeout: 60000,
})

// ── แจ้งเตือน "เซิร์ฟเวอร์กำลังตื่น" ตอน request ช้าผิดปกติ (cold start) ───
// ยิง CustomEvent ให้ component ไหนก็ได้ subscribe ได้ ไม่ผูกกับ UI ตรงนี้
const SLOW_REQUEST_MS = 4000
let slowRequestCount = 0

function _notifySlow(isSlow) {
  window.dispatchEvent(new CustomEvent('slow-request', { detail: { slow: isSlow } }))
}

api.interceptors.request.use(config => {
  config._slowFired = false
  config._slowTimer = setTimeout(() => {
    config._slowFired = true
    slowRequestCount += 1
    _notifySlow(true)
  }, SLOW_REQUEST_MS)
  return config
})

function _clearSlowTimer(config) {
  clearTimeout(config?._slowTimer)
  if (config?._slowFired) {
    slowRequestCount = Math.max(0, slowRequestCount - 1)
    if (slowRequestCount === 0) _notifySlow(false)
  }
}

api.interceptors.response.use(
  res => { _clearSlowTimer(res.config); return res },
  err => { _clearSlowTimer(err.config); return Promise.reject(err) },
)

// ── Dual-storage helpers: "จดจำการเข้าสู่ระบบ" → localStorage (คงอยู่ข้ามเซสชัน)
// ไม่ติ๊ก → sessionStorage (หายเมื่อปิดแท็บ) ────────────────────────────────
function _activeStorage() {
  return localStorage.getItem('access_token') ? localStorage : sessionStorage
}

function _getItem(key) {
  return localStorage.getItem(key) ?? sessionStorage.getItem(key)
}

function _setTokens({ access, refresh, remember }) {
  const store = remember ? localStorage : sessionStorage
  const other = remember ? sessionStorage : localStorage
  store.setItem('access_token', access)
  store.setItem('refresh_token', refresh)
  other.removeItem('access_token')
  other.removeItem('refresh_token')
}

// ── Request: แนบ token ทุก request ยกเว้น auth endpoints ──────────────────
api.interceptors.request.use(config => {
  const token = _getItem('access_token')
  const isAuthEndpoint =
    config.url?.includes('auth/login') ||
    config.url?.includes('auth/register')

  if (token && !isAuthEndpoint) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Refresh token แบบ dedupe ────────────────────────────────────────────
// หน้าเดียวมักยิงหลาย request พร้อมกัน (Promise.all ใน HomePage เช่น
// profile/bookings/term-bookings/today-feed) ถ้า access token หมดอายุ
// ทุกเส้นจะโดน 401 พร้อมกันหมด — ถ้าไม่ dedupe แต่ละเส้นจะยิง
// POST auth/refresh/ ของตัวเอง (เหมือนปัญหา "Broken pipe" ตอน login ซ้อน
// ที่ _pendingLoginRequest กันไว้แล้วด้านล่าง) ถ้าเส้นใดเส้นหนึ่งพลาด
// (cold start ช้า, เน็ตสะดุดชั่วขณะ) จะเด้ง logout ทั้งที่ session จริงๆ
// ยังกู้คืนได้ปกติจากเส้นอื่นที่ผ่าน ต้อง share promise เดียวกันทุกเส้น
// ให้ผลลัพธ์ตรงกันเสมอ
let _pendingRefresh = null

async function _refreshAccessToken() {
  if (_pendingRefresh) return _pendingRefresh

  _pendingRefresh = (async () => {
    const refresh = _getItem('refresh_token')
    if (!refresh) throw new Error('no refresh token')

    const res = await axios.post(`${API_BASE_URL}auth/refresh/`, { refresh })
    const newAccess = res.data.access
    _activeStorage().setItem('access_token', newAccess)
    // ROTATE_REFRESH_TOKENS=True ฝั่ง backend — refresh token เก่าใช้ครั้ง
    // เดียวแล้วถูกแทนที่ด้วยอันใหม่ ถ้าไม่เก็บอันใหม่ไว้ครั้งถัดไปจะ refresh
    // ด้วย token ที่ไม่ใช่ตัวล่าสุดตลอด (ยังไม่พังเพราะ BLACKLIST_AFTER_ROTATION
    // ปิดอยู่ แต่ผิดเจตนาของการ rotate)
    if (res.data.refresh) _activeStorage().setItem('refresh_token', res.data.refresh)
    return newAccess
  })()

  try {
    return await _pendingRefresh
  } finally {
    _pendingRefresh = null
  }
}

// ── Response: จัดการ token หมดอายุ (401) ─────────────────────────────────
api.interceptors.response.use(
  response => response,

  async error => {
    const original = error.config

    // ถ้า 401 และยังไม่เคย retry
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true

      try {
        const newAccess = await _refreshAccessToken()
        original.headers.Authorization = `Bearer ${newAccess}`
        return api(original)   // retry request เดิม
      } catch {
        // refresh ล้มเหลว (หรือไม่มี refresh token) → logout
        _clearAndRedirect()
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  }
)

function _clearAndRedirect() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
  sessionStorage.removeItem('access_token')
  sessionStorage.removeItem('refresh_token')
  sessionStorage.removeItem('user')
  window.location.href = '/login'
}

// ── กันยิง POST auth/login/ ซ้ำซ้อน ────────────────────────────────────────
// เก็บ promise ของ request ที่กำลังทำอยู่ไว้ระดับ module (ไม่ใช่ระดับ
// component) — ถ้ามีอะไรก็ตามเรียก loginWithLDAP ซ้ำระหว่างที่ request แรก
// ยังไม่จบ (ไม่ว่าจะจาก UI สั่งซ้ำ, StrictMode, extension ของ browser ฯลฯ)
// จะได้ promise เดิมกลับไปแทนที่จะยิง HTTP request ใหม่อีกเส้น กัน
// connection ซ้อนกันที่ทำให้เกิด "Broken pipe" ตอน response แรกมาถึงช้ากว่า
// เส้นที่สอง
let _pendingLoginRequest = null

// ── Helper: login แล้วเก็บ token อัตโนมัติ ────────────────────────────────
export async function loginWithLDAP(username, password, remember = true) {
  if (_pendingLoginRequest) {
    console.log('[DIAG] loginWithLDAP: request already in flight, reusing existing promise')
    return _pendingLoginRequest
  }
  _pendingLoginRequest = _doLoginWithLDAP(username, password, remember)
  try {
    return await _pendingLoginRequest
  } finally {
    _pendingLoginRequest = null
  }
}

async function _doLoginWithLDAP(username, password, remember) {
  console.log('[DIAG] loginWithLDAP: start, posting to auth/login/')
  const res = await api.post('auth/login/', { username, password })
  console.log('[DIAG] loginWithLDAP: got response', res.status, res.data)
  const user = res.data.user || res.data
  const displayName =
    user.display_name ||
    user.full_name ||
    [user.first_name, user.last_name].filter(Boolean).join(' ').trim() ||
    user.name ||
    user.username

  _setTokens({ access: res.data.access, refresh: res.data.refresh, remember })
  console.log('[DIAG] loginWithLDAP: tokens stored, access_token in storage now =', !!(localStorage.getItem('access_token') || sessionStorage.getItem('access_token')))
  const store = remember ? localStorage : sessionStorage
  store.setItem('user', JSON.stringify({
    username: user.username,
    first_name: user.first_name || '',
    last_name: user.last_name || '',
    full_name: user.full_name || displayName,
    display_name: displayName,
    name:     user.full_name || user.name || displayName,
    email:    user.email,
    faculty:  user.faculty,
    role:     user.role,
  }))
  console.log('[DIAG] loginWithLDAP: done, returning')

  return res.data
}

// ── Helper: logout ─────────────────────────────────────────────────────────
export function logout() {
  _clearAndRedirect()
}

export async function changePassword(payload) {
  const res = await api.post('auth/change-password/', payload)
  return res.data
}

export async function deleteAccount(payload) {
  const res = await api.post('auth/delete-account/', payload)
  return res.data
}

// ── Helper: ดึงข้อมูล user ─────────────────────────────────────────────────
export function getUser() {
  try {
    return JSON.parse(_getItem('user')) || null
  } catch {
    return null
  }
}

// ── Helper: อัปเดตข้อมูล user ที่ cache ไว้ (เช่น หลังแก้โปรไฟล์สำเร็จ) —
// merge เข้ากับของเดิม ไม่ต้อง login ใหม่ก็เห็นชื่อ/อีเมลใหม่ที่ header ทันที
export function updateStoredUser(patch) {
  const current = getUser() || {}
  const next = { ...current, ...patch }
  if (patch.first_name !== undefined || patch.last_name !== undefined) {
    const fullName = [next.first_name, next.last_name].filter(Boolean).join(' ').trim()
    next.full_name = fullName || next.username
    next.display_name = fullName || next.username
    next.name = fullName || next.username
  }
  _activeStorage().setItem('user', JSON.stringify(next))
  return next
}

// ── Helper: ดึง access token ปัจจุบัน (เช่นไปใช้ต่อ WebSocket) ──────────────
export function getAccessToken() {
  return _getItem('access_token')
}

export default api
