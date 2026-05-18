import { useState } from 'react'
import { todayGames, playerProps, recentResults } from '../mockData'

// TODO: Replace mock data with:
//   GET /api/predictions/today  → game slate
//   GET /api/predictions/props  → player prop edges
//   WebSocket /ws/live          → live injury alerts (Phase 16)

const STAT_COLORS = {
  OVER:  'text-green-400 bg-green-500/10 border-green-500/30',
  UNDER: 'text-red-400 bg-red-500/10 border-red-500/30',
}

const EDGE_COLORS = {
  '+EV':    'bg-green-500/15 text-green-400 border border-green-500/30',
  'NO EDGE': 'bg-gray-500/15 text-gray-400 border border-gray-700',
  'LEAN':   'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30',
}

export default function BettingDashboard() {
  const [propFilter, setPropFilter] = useState('All')
  const [sortBy, setSortBy] = useState('ev')

  const propStats = ['All', 'PTS', 'REB', 'AST']
  const filteredProps = playerProps
    .filter(p => propFilter === 'All' || p.stat === propFilter)
    .sort((a, b) => sortBy === 'ev' ? Math.abs(b.ev) - Math.abs(a.ev) : b.confidence - a.confidence)

  // Summary metrics
  const edges = todayGames.filter(g => g.edge === '+EV').length
  const topProp = playerProps.sort((a, b) => Math.abs(b.ev) - Math.abs(a.ev))[0]

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-8">

      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Betting Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">March 24, 2025 · 5 games · Model: 69.1% win prob accuracy</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="px-2.5 py-1.5 bg-green-500/10 text-green-400 border border-green-500/30 rounded-lg font-medium">
            {edges} +EV games
          </span>
          <span className="px-2.5 py-1.5 bg-orange-500/10 text-orange-400 border border-orange-500/30 rounded-lg font-medium">
            Top: {topProp.player} {topProp.stat} {topProp.recommendation} (+{(topProp.ev * 100).toFixed(1)}% EV)
          </span>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KpiCard label="Model Accuracy" value="69.1%" sub="+14.6% vs baseline" color="green" />
        <KpiCard label="Today's Games" value="5" sub="3 +EV edges found" color="orange" />
        <KpiCard label="Best EV" value="+10.3%" sub="Tatum PTS OVER 27.5" color="blue" />
        <KpiCard label="CLV Proxy" value="+8.1%" sub="vs closing line" color="purple" />
      </div>

      {/* Today's games */}
      <section>
        <h2 className="text-lg font-bold text-white mb-3 flex items-center gap-2">
          Today's Slate
          <span className="text-xs font-normal text-gray-500">— March 24, 2025</span>
        </h2>
        <div className="space-y-3">
          {todayGames.map(game => <GameCard key={game.id} game={game} />)}
        </div>
      </section>

      {/* Player props */}
      <section>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
          <h2 className="text-lg font-bold text-white">
            Player Props
            <span className="text-xs font-normal text-gray-500 ml-2">— {filteredProps.length} projections</span>
          </h2>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Stat filter */}
            <div className="flex bg-[#1a1d24] border border-gray-800 rounded-lg p-0.5 gap-0.5">
              {propStats.map(s => (
                <button
                  key={s}
                  onClick={() => setPropFilter(s)}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all ${
                    propFilter === s ? 'bg-orange-500 text-white' : 'text-gray-400 hover:text-white'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            {/* Sort */}
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value)}
              className="bg-[#1a1d24] border border-gray-700 text-gray-300 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-orange-500"
            >
              <option value="ev">Sort: Best EV</option>
              <option value="conf">Sort: Confidence</option>
            </select>
          </div>
        </div>

        {/* Props table */}
        <div className="bg-[#1a1d24] border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Player</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Matchup</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Stat</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Line</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Proj</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Edge</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">EV</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Pick</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider hidden md:table-cell">L5</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {filteredProps.map((prop, idx) => (
                  <PropRow key={`${prop.playerId}-${prop.stat}-${idx}`} prop={prop} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <p className="text-xs text-gray-600 mt-2">
          Model: PTS MAE 0.310 · REB MAE 0.115 · AST MAE 0.091 · All R² &gt; 0.93
          {/* TODO: Real-time model confidence intervals from GET /api/predictions/props/{player_id} */}
        </p>
      </section>

      {/* Recent results */}
      <section>
        <h2 className="text-lg font-bold text-white mb-3">Recent Results</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {recentResults.map(r => (
            <div key={r.id} className="bg-[#1a1d24] border border-gray-800 rounded-lg px-3 py-2.5 flex items-center justify-between">
              <div className="text-sm font-medium text-gray-300">{r.away} @ {r.home}</div>
              <div className="text-sm font-bold text-white">{r.awayScore}–{r.homeScore}</div>
              <div className="text-xs text-gray-600">{r.date.slice(5)}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

function GameCard({ game }) {
  const homePct = Math.round(game.winProb.home * 100)
  const awayPct = Math.round(game.winProb.away * 100)
  const favored = game.winProb.home > game.winProb.away ? 'home' : 'away'

  return (
    <div className="bg-[#1a1d24] border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors">
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">

        {/* Teams */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Away */}
            <div className="flex items-center gap-2">
              <span className="text-xl">{game.awayLogo}</span>
              <div>
                <span className={`font-bold text-sm ${favored === 'away' ? 'text-white' : 'text-gray-400'}`}>
                  {game.awayTeam}
                </span>
                <span className="text-xs text-gray-600 ml-1 hidden sm:inline">{game.awayName}</span>
              </div>
            </div>
            <span className="text-gray-600 text-xs font-medium">@</span>
            {/* Home */}
            <div className="flex items-center gap-2">
              <span className="text-xl">{game.homeLogo}</span>
              <div>
                <span className={`font-bold text-sm ${favored === 'home' ? 'text-white' : 'text-gray-400'}`}>
                  {game.homeTeam}
                </span>
                <span className="text-xs text-gray-600 ml-1 hidden sm:inline">{game.homeName}</span>
              </div>
            </div>
            <span className="text-xs text-gray-600">{game.gameTime}</span>
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${EDGE_COLORS[game.edge]}`}>
              {game.edge}
            </span>
          </div>

          {/* Win prob bar */}
          <div className="mt-2.5 flex items-center gap-2">
            <span className="text-xs text-gray-500 w-8 text-right">{awayPct}%</span>
            <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-orange-500 rounded-full"
                style={{ width: `${homePct}%` }}
              />
            </div>
            <span className="text-xs text-gray-500 w-8">{homePct}%</span>
          </div>
        </div>

        {/* Prediction + lines */}
        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap text-xs text-gray-400 shrink-0">
          <StatPill label="Spread" value={`${game.spread.favorite} ${game.spread.line > 0 ? '+' : ''}${game.spread.line}`} />
          <StatPill label="O/U" value={game.total.line} />
          <StatPill label="FGA/min" value={game.shotsPerMinute} />
          <div className="flex flex-col items-center bg-orange-500/10 border border-orange-500/30 rounded-lg px-3 py-1.5">
            <span className="text-[10px] text-orange-500/70 font-medium uppercase tracking-wider">Pick</span>
            <span className="text-orange-400 font-bold text-sm">{game.prediction}</span>
            <span className="text-[10px] text-orange-500/70">{Math.round(game.confidence * 100)}%</span>
          </div>
        </div>
      </div>

      {game.modelNote && (
        <p className="text-xs text-gray-600 mt-2.5 pt-2.5 border-t border-gray-800/50">
          💡 {game.modelNote}
        </p>
      )}
    </div>
  )
}

function PropRow({ prop }) {
  const edgeAbs = Math.abs(prop.edge)
  const evPct = (prop.ev * 100).toFixed(1)
  const isPositiveEV = prop.ev > 0.04

  return (
    <tr className={`hover:bg-gray-800/30 transition-colors ${isPositiveEV ? '' : 'opacity-70'}`}>
      <td className="px-4 py-3">
        <div className="font-semibold text-white text-sm">{prop.player}</div>
        <div className="text-xs text-gray-500">{prop.team} · {prop.position}</div>
      </td>
      <td className="px-4 py-3 text-xs text-gray-400">vs {prop.opponent}</td>
      <td className="px-3 py-3 text-center">
        <span className="text-xs font-mono text-gray-300 bg-gray-800 px-1.5 py-0.5 rounded">{prop.stat}</span>
      </td>
      <td className="px-3 py-3 text-center text-sm font-mono text-gray-300">{prop.line}</td>
      <td className="px-3 py-3 text-center text-sm font-bold text-white">{prop.projection.toFixed(1)}</td>
      <td className="px-3 py-3 text-center">
        <span className={`text-xs font-mono ${prop.edge > 0 ? 'text-green-400' : 'text-red-400'}`}>
          {prop.edge > 0 ? '+' : ''}{prop.edge.toFixed(1)}
        </span>
      </td>
      <td className="px-3 py-3 text-center">
        <span className={`text-xs font-semibold ${isPositiveEV ? 'text-green-400' : 'text-gray-500'}`}>
          {prop.ev > 0 ? '+' : ''}{evPct}%
        </span>
      </td>
      <td className="px-3 py-3 text-center">
        <span className={`text-xs font-bold px-2 py-0.5 rounded border ${STAT_COLORS[prop.recommendation]}`}>
          {prop.recommendation}
        </span>
      </td>
      {/* Last 5 games mini sparkline */}
      <td className="px-4 py-3 hidden md:table-cell">
        <div className="flex items-end gap-0.5 h-6">
          {prop.last5.map((val, i) => {
            const max = Math.max(...prop.last5)
            const h = Math.round((val / max) * 100)
            const color = val > prop.line ? 'bg-green-500' : 'bg-red-500'
            return (
              <div key={i} title={`Game ${i + 1}: ${val}`}
                className={`w-3 rounded-sm ${color} opacity-80`}
                style={{ height: `${h}%` }}
              />
            )
          })}
        </div>
      </td>
    </tr>
  )
}

function StatPill({ label, value }) {
  return (
    <div className="flex flex-col items-center bg-[#252932] rounded-lg px-2.5 py-1.5 min-w-[56px]">
      <span className="text-[10px] text-gray-600 font-medium uppercase tracking-wider">{label}</span>
      <span className="text-gray-200 font-semibold text-xs">{value}</span>
    </div>
  )
}

function KpiCard({ label, value, sub, color }) {
  const colors = {
    green:  'text-green-400 bg-green-500/10 border-green-500/20',
    orange: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
    blue:   'text-blue-400 bg-blue-500/10 border-blue-500/20',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  }
  return (
    <div className={`rounded-xl border p-4 ${colors[color]}`}>
      <div className="text-2xl font-black">{value}</div>
      <div className="text-xs font-semibold mt-0.5">{label}</div>
      <div className="text-[11px] opacity-70 mt-0.5">{sub}</div>
    </div>
  )
}
