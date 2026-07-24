import axios from 'axios'

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/',
  timeout: 15000,
})

// ── Request: แนบ token ทุก request ยกเว้น auth endpoints ──────────────────
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  const isAuthEndpoint =
    config.url?.includes('auth/login') ||
    config.url?.includes('auth/register')

  if (token && !isAuthEndpoint) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response: จัดการ token หมดอายุ (401) ─────────────────────────────────
api.interceptors.response.use(
  response => response,

  async error => {
    const original = error.config

    // ถ้า 401 และยังไม่เคย retry
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true

      const refresh = localStorage.getItem('refresh_token')
      if (!refresh) {
        // ไม่มี refresh token → logout
        _clearAndRedirect()
        return Promise.reject(error)
      }

      try {
        const res = await axios.post(
          'http://127.0.0.1:8000/api/auth/refresh/',
          { refresh }
        )
        const newAccess = res.data.access
        localStorage.setItem('access_token', newAccess)
        original.headers.Authorization = `Bearer ${newAccess}`
        return api(original)   // retry request เดิม
      } catch {
        // refresh ล้มเหลว → logout
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
  window.location.href = '/login'
}

// ── Helper: login แล้วเก็บ token อัตโนมัติ ────────────────────────────────
export async function loginWithLDAP(username, password) {
  const res = await api.post('auth/login/', { username, password })
  const user = res.data.user || res.data

  localStorage.setItem('access_token',  res.data.access)
  localStorage.setItem('refresh_token', res.data.refresh)
  localStorage.setItem('user', JSON.stringify({
    username: user.username,
    name:     user.full_name || user.name,
    email:    user.email,
    faculty:  user.faculty,
    role:     user.role,
  }))

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

// ── Helper: ดึงข้อมูล user จาก localStorage ───────────────────────────────
export function getUser() {
  try {
    return JSON.parse(localStorage.getItem('user')) || null
  } catch {
    return null
  }
}

export default api
