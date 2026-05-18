import { useState } from 'react'

// TODO: Replace form submit with POST /api/auth/login or /api/auth/register (Phase 13)

export default function Login({ onLogin, user }) {
  const [mode, setMode] = useState('login')          // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')

  if (user) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        <div className="text-center space-y-4">
          <div className="text-5xl">✅</div>
          <h2 className="text-xl font-bold text-white">Signed in as <span className="text-orange-400">{user.email}</span></h2>
          <p className="text-gray-400 text-sm">You have full access to all predictions and analytics.</p>
          <div className="flex gap-3 justify-center mt-2">
            <PlanBadge plan="Pro" />
            <PlanBadge plan="Models: 18" color="blue" />
          </div>
        </div>
      </div>
    )
  }

  function validate() {
    if (!email.includes('@')) return 'Enter a valid email address.'
    if (password.length < 6) return 'Password must be at least 6 characters.'
    if (mode === 'signup' && password !== confirmPassword) return 'Passwords do not match.'
    return null
  }

  function handleSubmit(e) {
    e.preventDefault()
    setError('')
    const err = validate()
    if (err) { setError(err); return }

    setLoading(true)
    // Simulate async auth — TODO: replace with real API call
    setTimeout(() => {
      setLoading(false)
      if (mode === 'login') {
        // Mock auth: any valid email/password works
        onLogin({ email, plan: 'Pro', modelsAccess: 18 })
      } else {
        setSuccess('Account created! Signing you in...')
        setTimeout(() => onLogin({ email, plan: 'Pro', modelsAccess: 18 }), 800)
      }
    }, 700)
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">

        {/* Header */}
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-black">
            <span className="text-orange-500">NBA</span>
            <span className="text-white"> AI</span>
          </h1>
          <p className="text-gray-400 text-sm">
            {mode === 'login' ? 'Sign in to your account' : 'Create a free account'}
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex bg-[#1a1d24] rounded-lg p-1 border border-gray-800">
          <TabBtn label="Sign In"  active={mode === 'login'}  onClick={() => { setMode('login');  setError('') }} />
          <TabBtn label="Sign Up"  active={mode === 'signup'} onClick={() => { setMode('signup'); setError('') }} />
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="w-full bg-[#1a1d24] border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500/50 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full bg-[#1a1d24] border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500/50 transition-colors"
            />
          </div>
          {mode === 'signup' && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Confirm Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full bg-[#1a1d24] border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500/50 transition-colors"
              />
            </div>
          )}

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 text-sm text-red-400">
              {error}
            </div>
          )}
          {success && (
            <div className="bg-green-500/10 border border-green-500/30 rounded-lg px-3 py-2 text-sm text-green-400">
              {success}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-orange-500 hover:bg-orange-400 disabled:bg-orange-500/50 text-white font-semibold py-2.5 rounded-lg transition-colors text-sm"
          >
            {loading ? 'Authenticating...' : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        {/* Features list */}
        <div className="border border-gray-800 rounded-lg p-4 space-y-2">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">What you get</p>
          {[
            ['📊', 'Daily game predictions & spread edges'],
            ['🎯', 'Player prop projections — 7 stat types'],
            ['🤖', 'AI Chat — ask about any player or game'],
            ['📈', 'Analytics — 96 metrics, shot charts'],
            ['⚡', 'Kelly sizing + CLV tracking'],
          ].map(([icon, text]) => (
            <div key={text} className="flex items-center gap-2 text-xs text-gray-400">
              <span>{icon}</span><span>{text}</span>
            </div>
          ))}
        </div>

        <p className="text-center text-xs text-gray-600">
          For research and educational use only. Not financial advice.
        </p>
      </div>
    </div>
  )
}

function TabBtn({ label, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${
        active ? 'bg-orange-500 text-white' : 'text-gray-400 hover:text-white'
      }`}
    >
      {label}
    </button>
  )
}

function PlanBadge({ plan, color = 'orange' }) {
  const colors = {
    orange: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    blue:   'bg-blue-500/15 text-blue-400 border-blue-500/30',
  }
  return (
    <span className={`text-xs font-medium px-2 py-1 rounded border ${colors[color]}`}>
      {plan}
    </span>
  )
}
