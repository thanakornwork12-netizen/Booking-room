import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import HomePage from './pages/HomePage'
import SearchPage from './pages/SearchPage'
import AdminPage from './pages/AdminPage'

// เช็คแค่ว่า Login หรือยัง
const PrivateRoute = ({ children }) => {
  return localStorage.getItem('access_token') ? children : <Navigate to="/login" />
}

// เช็คว่าเป็น Admin หรือ Staff จริงไหม (ป้องกัน User แอบเข้า)
const AdminRoute = ({ children }) => {
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin = user.role === 'admin' || user.role === 'staff';
  
  if (!localStorage.getItem('access_token')) return <Navigate to="/login" />;
  return isAdmin ? children : <Navigate to="/" />; // ถ้าไม่ใช่แอดมิน ให้ดีดกลับหน้าแรก
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* User Routes */}
        <Route path="/" element={<PrivateRoute><HomePage /></PrivateRoute>} />
        <Route path="/search" element={<PrivateRoute><SearchPage /></PrivateRoute>} />

        {/* Admin Routes */}
        {/* ปรับ path ให้ตรงกับ navigate('/admin/dashboard') ใน LoginPage */}
        <Route path="/admin/dashboard" element={<AdminRoute><AdminPage /></AdminRoute>} />
        
        {/* แถม: ถ้าใครพิมพ์ /admin เฉยๆ ให้เด้งไป /admin/dashboard */}
        <Route path="/admin" element={<Navigate to="/admin/dashboard" />} />
      </Routes>
    </BrowserRouter>
  )
}