import { useState } from 'react'
import Navbar from './components/Navbar'
import Login from './components/Login'
import ChatWindow from './components/ChatWindow'
import BettingDashboard from './components/BettingDashboard'
import AnalyticsDashboard from './components/AnalyticsDashboard'
import Dashboard from './components/Dashboard'

// Tab definitions — maps to Phase 13–15 backend routes
const TABS = [
  { id: 'dashboard', label: 'AI Core',   icon: '⚡' },
  { id: 'betting',   label: 'Legacy Bets', icon: '📊' },
  { id: 'analytics', label: 'Analytics', icon: '📈' },
  { id: 'chat',      label: 'AI Chat',   icon: '🤖' },
  { id: 'login',     label: 'Account',   icon: '👤' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')
  // Minimal auth state — TODO: Replace with JWT from FastAPI /auth endpoint (Phase 13)
  const [user, setUser] = useState(null)

  function handleLogin(userData) {
    setUser(userData)
    setActiveTab('dashboard')
  }

  function handleLogout() {
    setUser(null)
    setActiveTab('login')
  }

  return (
    <div className="min-h-screen bg-[#0f1117] text-white flex flex-col h-screen">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        tabs={TABS}
        user={user}
        onLogout={handleLogout}
      />

      <main className="flex-1 overflow-hidden h-full">
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'betting'   && <BettingDashboard />}
        {activeTab === 'analytics' && <AnalyticsDashboard />}
        {activeTab === 'chat'      && <ChatWindow user={user} />}
        {activeTab === 'login'     && <Login onLogin={handleLogin} user={user} />}
      </main>
    </div>
  )
}
