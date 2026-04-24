import { Routes, Route } from 'react-router-dom'
import { LandingPage } from './pages/LandingPage'
import { AppPage } from './pages/AppPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/app" element={<AppPage />} />
    </Routes>
  )
}
