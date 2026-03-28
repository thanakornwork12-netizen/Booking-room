import axios from 'axios'

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/',  // ← เพิ่ม / ท้าย
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  const isAuthEndpoint = config.url?.includes('/auth/login') ||
                         config.url?.includes('/auth/register')
  if (token && !isAuthEndpoint) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export default api