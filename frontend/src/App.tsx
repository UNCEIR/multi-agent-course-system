import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import RecommendPage from './pages/RecommendPage'
import MonitorPage from './pages/MonitorPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<RecommendPage />} />
        <Route path="/monitor" element={<MonitorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
