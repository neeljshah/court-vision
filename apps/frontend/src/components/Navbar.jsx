export default function Navbar({ activeTab, setActiveTab, tabs, user, onLogout }) {
  return (
    <header className="sticky top-0 z-50 border-b border-gray-800 bg-[#0f1117]/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between gap-4">

        {/* Logo */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-orange-500 text-xl font-black tracking-tight">NBA</span>
          <span className="text-white text-xl font-black tracking-tight">AI</span>
          <span className="hidden sm:inline ml-2 text-xs text-gray-500 font-mono border border-gray-700 rounded px-1.5 py-0.5">
            BETA
          </span>
        </div>

        {/* Tabs */}
        <nav className="flex items-center gap-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all
                ${activeTab === tab.id
                  ? 'bg-orange-500/15 text-orange-400 border border-orange-500/30'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }
              `}
            >
              <span className="text-base leading-none">{tab.icon}</span>
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          ))}
        </nav>

        {/* User status */}
        <div className="shrink-0 flex items-center gap-2">
          {user ? (
            <>
              <span className="hidden sm:inline text-xs text-gray-400">
                {user.email}
              </span>
              <button
                onClick={onLogout}
                className="text-xs text-gray-500 hover:text-red-400 transition-colors"
              >
                Sign out
              </button>
            </>
          ) : (
            <span className="text-xs text-gray-600 font-mono">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500 mr-1.5 animate-pulse" />
              LIVE
            </span>
          )}
        </div>
      </div>

      {/* Model status bar */}
      <div className="bg-[#1a1d24] border-t border-gray-800/50 px-4 py-1">
        <div className="max-w-7xl mx-auto flex items-center gap-4 text-xs text-gray-500 overflow-x-auto">
          <span className="shrink-0 text-green-500 font-medium">● LIVE</span>
          <span className="shrink-0">Win Prob: <span className="text-gray-300">69.1% acc</span></span>
          <span className="shrink-0 text-gray-700">|</span>
          <span className="shrink-0">Props MAE: <span className="text-gray-300">PTS 0.310 · REB 0.115 · AST 0.091</span></span>
          <span className="shrink-0 text-gray-700">|</span>
          <span className="shrink-0">Models live: <span className="text-gray-300">18/90</span></span>
          <span className="shrink-0 text-gray-700">|</span>
          <span className="shrink-0">Data: <span className="text-gray-300">3,675 games · 221K shots · 569 players</span></span>
        </div>
      </div>
    </header>
  )
}
