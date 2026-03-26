import { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine,
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  Legend, Cell,
} from 'recharts'
import {
  winProbMetrics,
  propsModelMetrics,
  lebroGameLog,
  teamComparison,
  datasetStats,
} from '../mockData'

// TODO: Replace with GET /api/analytics/{metric} (Phase 13)

const ORANGE = '#f97316'
const BLUE   = '#3b82f6'
const GREEN  = '#22c55e'
const RED    = '#ef4444'
const GRAY   = '#374151'

// Custom dark tooltip for all charts
function DarkTooltip({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#1a1d24] border border-gray-700 rounded-lg px-3 py-2 shadow-xl text-xs">
      {label && <p className="text-gray-400 mb-1 font-medium">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || '#fff' }} className="font-semibold">
          {p.name}: {formatter ? formatter(p.value) : p.value}
        </p>
      ))}
    </div>
  )
}

// Normalise a team's stats to 0-100 scale for radar
function normalise(val, min, max, invert = false) {
  const n = Math.round(((val - min) / (max - min)) * 100)
  return invert ? 100 - n : n
}

export default function AnalyticsDashboard() {
  const [activeSection, setActiveSection] = useState('model')

  const sections = [
    { id: 'model',   label: 'Model Performance' },
    { id: 'player',  label: 'Player Trends' },
    { id: 'teams',   label: 'Team Comparison' },
    { id: 'dataset', label: 'Dataset' },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Analytics Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">
            18 live models · 3,675 games · 221K shots · 569 players
          </p>
        </div>
        <button className="text-xs bg-[#1a1d24] border border-gray-700 hover:border-orange-500/50 text-gray-400 hover:text-orange-400 rounded-lg px-3 py-2 transition-colors">
          Export Report ↓
          {/* TODO: POST /api/analytics/export → PDF/CSV (Phase 13) */}
        </button>
      </div>

      {/* Section tabs */}
      <div className="flex gap-1 bg-[#1a1d24] border border-gray-800 rounded-xl p-1 flex-wrap">
        {sections.map(s => (
          <button
            key={s.id}
            onClick={() => setActiveSection(s.id)}
            className={`flex-1 min-w-[100px] py-2 text-xs font-semibold rounded-lg transition-all ${
              activeSection === s.id
                ? 'bg-orange-500 text-white shadow'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {activeSection === 'model'   && <ModelSection />}
      {activeSection === 'player'  && <PlayerSection />}
      {activeSection === 'teams'   && <TeamSection />}
      {activeSection === 'dataset' && <DatasetSection />}
    </div>
  )
}

// ─── MODEL PERFORMANCE ──────────────────────────────────────────────────────
function ModelSection() {
  // Win prob fold data for bar chart
  const foldData = winProbMetrics.folds.map(f => ({
    name: `Fold ${f.fold}`,
    accuracy: Math.round(f.acc * 1000) / 10,
    brier: Math.round(f.brier * 1000) / 10,
  }))

  // Props model MAE for bar chart
  const propsData = Object.entries(propsModelMetrics).map(([key, v]) => ({
    name: v.label,
    mae: v.mae,
    r2: Math.round(v.r2 * 1000) / 10,
  }))

  // Feature importance
  const featureData = winProbMetrics.featureImportance.map(f => ({
    name: f.feature.replace(/_/g, ' '),
    importance: Math.round(f.importance * 1000) / 10,
  }))

  return (
    <div className="space-y-6">
      {/* Top stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Win Prob Accuracy" value="69.1%" badge="vs 54.5% baseline" positive />
        <MetricCard label="Brier Score"        value="0.2675"  badge="Lower = better" />
        <MetricCard label="CLV Proxy"          value="+8.1%"  badge="vs closing line" positive />
        <MetricCard label="DNP Model AUC"      value="0.979"  badge="99% recall" positive />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Win prob CV accuracy */}
        <ChartCard title="Win Prob — 4-Fold Cross Validation" subtitle="Walk-forward, 737 games/fold">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={foldData} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252932" />
              <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} />
              <YAxis domain={[55, 70]} tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip content={<DarkTooltip formatter={v => `${v}%`} />} />
              <ReferenceLine y={60} stroke={GRAY} strokeDasharray="4 2" label={{ value: 'Baseline 54.5%', fill: '#6b7280', fontSize: 10 }} />
              <Bar dataKey="accuracy" name="Accuracy %" radius={[4, 4, 0, 0]}>
                {foldData.map((_, i) => (
                  <Cell key={i} fill={i === 2 ? GREEN : ORANGE} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Props MAE */}
        <ChartCard title="Prop Models — MAE by Stat" subtitle="Lower is better · All R² > 0.93">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={propsData} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252932" />
              <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis domain={[0, 0.4]} tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip content={<DarkTooltip />} />
              <Bar dataKey="mae" name="MAE" radius={[4, 4, 0, 0]}>
                {propsData.map((d, i) => (
                  <Cell key={i} fill={d.mae < 0.1 ? GREEN : d.mae < 0.2 ? ORANGE : BLUE} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Feature importance */}
      <ChartCard title="Win Probability — Feature Importance" subtitle="XGBoost, top 8 features">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={featureData} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 100 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#252932" horizontal={false} />
            <XAxis type="number" domain={[0, 14]} tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={v => `${v}%`} />
            <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} width={100} />
            <Tooltip content={<DarkTooltip formatter={v => `${v}%`} />} />
            <Bar dataKey="importance" name="Importance" fill={ORANGE} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  )
}

// ─── PLAYER TRENDS ───────────────────────────────────────────────────────────
function PlayerSection() {
  const [stat, setStat] = useState('pts')

  const statMap = { pts: 'PTS', reb: 'REB', ast: 'AST', min: 'MIN' }
  const chartData = lebroGameLog.map(g => ({
    game: `G${g.game}`,
    value: g[stat],
  }))
  const avg = (lebroGameLog.reduce((s, g) => s + g[stat], 0) / lebroGameLog.length).toFixed(1)
  const last5avg = (lebroGameLog.slice(-5).reduce((s, g) => s + g[stat], 0) / 5).toFixed(1)
  const max = Math.max(...lebroGameLog.map(g => g[stat]))

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-white">LeBron James — 2024-25 Game Log</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Player ID 203999 · source: data/nba/gamelog_203999_2024-25.json
          </p>
        </div>
        <div className="flex bg-[#1a1d24] border border-gray-800 rounded-lg p-0.5 gap-0.5">
          {Object.keys(statMap).map(s => (
            <button
              key={s}
              onClick={() => setStat(s)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                stat === s ? 'bg-orange-500 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              {statMap[s]}
            </button>
          ))}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-3">
        <MetricCard label={`Season Avg ${statMap[stat]}`} value={avg} badge="20 games" />
        <MetricCard label="L5 Average" value={last5avg} badge="Last 5 games" positive={parseFloat(last5avg) >= parseFloat(avg)} />
        <MetricCard label="Season High" value={max} badge={`Game ${lebroGameLog.findIndex(g => g[stat] === max) + 1}`} positive />
      </div>

      <ChartCard
        title={`LeBron James — ${statMap[stat]} per Game (2024-25)`}
        subtitle="Source: gamelog_203999_2024-25.json · click bars to filter (TODO: Phase 15)"
      >
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#252932" />
            <XAxis dataKey="game" tick={{ fill: '#6b7280', fontSize: 10 }} interval={2} />
            <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} />
            <Tooltip content={<DarkTooltip />} />
            <ReferenceLine y={parseFloat(avg)} stroke={BLUE} strokeDasharray="4 2"
              label={{ value: `Avg ${avg}`, fill: BLUE, fontSize: 10, position: 'right' }} />
            <Bar dataKey="value" name={statMap[stat]} radius={[3, 3, 0, 0]}>
              {chartData.map((d, i) => (
                <Cell key={i} fill={d.value >= parseFloat(avg) ? ORANGE : GRAY} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Game-by-game table */}
      <ChartCard title="Full Game Log" subtitle="20 most recent games">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-800">
                {['Game', 'PTS', 'REB', 'AST', 'MIN'].map(h => (
                  <th key={h} className="text-left pb-2 pr-4 text-gray-500 font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lebroGameLog.map(g => (
                <tr key={g.game} className="border-b border-gray-800/30 hover:bg-gray-800/20">
                  <td className="py-1.5 pr-4 text-gray-500">G{g.game}</td>
                  <td className={`py-1.5 pr-4 font-semibold ${g.pts >= 30 ? 'text-orange-400' : g.pts >= 20 ? 'text-white' : 'text-gray-400'}`}>{g.pts}</td>
                  <td className={`py-1.5 pr-4 ${g.reb >= 15 ? 'text-blue-400' : 'text-gray-300'}`}>{g.reb}</td>
                  <td className={`py-1.5 pr-4 ${g.ast >= 10 ? 'text-green-400' : 'text-gray-300'}`}>{g.ast}</td>
                  <td className="py-1.5 pr-4 text-gray-400">{g.min}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </div>
  )
}

// ─── TEAM COMPARISON ─────────────────────────────────────────────────────────
function TeamSection() {
  const { teamA, teamB } = teamComparison

  const radarData = [
    { stat: 'Off Rtg',  gsw: normalise(teamA.offRtg, 105, 120), lal: normalise(teamB.offRtg, 105, 120) },
    { stat: 'Def Rtg',  gsw: normalise(teamA.defRtg, 105, 120, true), lal: normalise(teamB.defRtg, 105, 120, true) },
    { stat: 'Pace',     gsw: normalise(teamA.pace, 95, 105), lal: normalise(teamB.pace, 95, 105) },
    { stat: 'eFG%',     gsw: normalise(teamA.eFGpct, 0.50, 0.58), lal: normalise(teamB.eFGpct, 0.50, 0.58) },
    { stat: 'Win%',     gsw: normalise(teamA.winPct, 0.25, 0.75), lal: normalise(teamB.winPct, 0.25, 0.75) },
  ]

  const headToHead = [
    { stat: 'Off Rtg',  gsw: teamA.offRtg, lal: teamB.offRtg, higher: 'lal' },
    { stat: 'Def Rtg',  gsw: teamA.defRtg, lal: teamB.defRtg, higher: 'gsw' },
    { stat: 'Net Rtg',  gsw: teamA.netRtg, lal: teamB.netRtg, higher: 'lal' },
    { stat: 'Pace',     gsw: teamA.pace,   lal: teamB.pace,   higher: 'gsw' },
    { stat: 'eFG%',     gsw: teamA.eFGpct, lal: teamB.eFGpct, higher: 'gsw' },
    { stat: 'TOV%',     gsw: teamA.tovPct, lal: teamB.tovPct, higher: 'lal' },
    { stat: 'Win%',     gsw: teamA.winPct, lal: teamB.winPct, higher: 'lal' },
  ]

  return (
    <div className="space-y-6">
      {/* Team header */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[#1a1d24] border border-gray-800 rounded-xl p-4 text-center">
          <div className="text-3xl mb-1">🟡</div>
          <div className="text-xl font-black text-white">{teamA.abbr}</div>
          <div className="text-xs text-gray-500">{teamA.name}</div>
          <div className="mt-2 text-sm font-bold text-orange-400">{Math.round(teamA.winPct * 100)}% Win Rate</div>
          <div className="text-xs text-gray-500">{teamA.last10} L10</div>
        </div>
        <div className="bg-[#1a1d24] border border-gray-800 rounded-xl p-4 text-center">
          <div className="text-3xl mb-1">💛</div>
          <div className="text-xl font-black text-white">{teamB.abbr}</div>
          <div className="text-xs text-gray-500">{teamB.name}</div>
          <div className="mt-2 text-sm font-bold text-blue-400">{Math.round(teamB.winPct * 100)}% Win Rate</div>
          <div className="text-xs text-gray-500">{teamB.last10} L10</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Radar chart */}
        <ChartCard title="GSW vs LAL — Radar Comparison" subtitle="Normalised to league range">
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radarData} margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
              <PolarGrid stroke="#252932" />
              <PolarAngleAxis dataKey="stat" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <Radar name="GSW" dataKey="gsw" stroke={ORANGE} fill={ORANGE} fillOpacity={0.15} />
              <Radar name="LAL" dataKey="lal" stroke={BLUE}   fill={BLUE}   fillOpacity={0.15} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
              <Tooltip content={<DarkTooltip />} />
            </RadarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Head-to-head table */}
        <ChartCard title="Head-to-Head Stats" subtitle="2024-25 Regular Season">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left pb-2 text-xs text-gray-500 font-semibold">Stat</th>
                <th className="text-center pb-2 text-xs text-orange-400 font-semibold">GSW</th>
                <th className="text-center pb-2 text-xs text-blue-400 font-semibold">LAL</th>
              </tr>
            </thead>
            <tbody>
              {headToHead.map(row => (
                <tr key={row.stat} className="border-b border-gray-800/30">
                  <td className="py-2 text-gray-400 text-xs">{row.stat}</td>
                  <td className={`py-2 text-center font-semibold text-sm ${row.higher === 'gsw' ? 'text-orange-400' : 'text-gray-400'}`}>
                    {row.gsw}
                  </td>
                  <td className={`py-2 text-center font-semibold text-sm ${row.higher === 'lal' ? 'text-blue-400' : 'text-gray-400'}`}>
                    {row.lal}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-gray-600 mt-3">
            {/* TODO: Replace with live team stats from GET /api/teams/{team_id}/stats (Phase 13) */}
            Source: data/nba/matchup_GSW_LAL_2024-25_Reg.json + nba_api team stats
          </p>
        </ChartCard>
      </div>
    </div>
  )
}

// ─── DATASET STATUS ──────────────────────────────────────────────────────────
function DatasetSection() {
  const items = [
    { label: 'Season Games (3 seasons)',  value: '3,675', status: 'live', note: 'Win prob training set' },
    { label: 'Player Game Logs',          value: '622',   status: 'live', note: '569 players, 3 seasons' },
    { label: 'Shot Charts',               value: '221,866', status: 'live', note: 'xFG v1 trained (Brier 0.226)' },
    { label: 'Play-by-Play Games',        value: '3,627', status: 'live', note: '98.4% coverage' },
    { label: 'Injury Reports',            value: '126',   status: 'live', note: 'Refreshed daily' },
    { label: 'Game Clips Tracked (CV)',   value: '17',    status: 'partial', note: 'Short clips — Phase G needs full games' },
    { label: 'Tracking Rows',             value: '29,220', status: 'partial', note: 'Team separation fixed ✅' },
    { label: 'Shots Enriched (CV)',       value: '0',     status: 'pending', note: 'Needs --game-id runs (Phase G)' },
    { label: 'PostgreSQL Records',        value: 'Active', status: 'live', note: '.env wired, CSV partitioned' },
    { label: 'Models Trained',            value: '18/90', status: 'partial', note: 'Tiers 1-2 complete' },
  ]

  const modelMilestones = [
    { phase: 'Phase 4 (now)',  games: 0,    models: 18, note: 'Tier 1: win prob, props, game models' },
    { phase: 'Phase 7',       games: 20,   models: 28, note: 'xFG v2, play type, defensive pressure' },
    { phase: 'Phase 10',      games: 100,  models: 50, note: 'Fatigue, lineup chemistry, matchup matrix' },
    { phase: 'Phase 12',      games: 200,  models: 82, note: 'Full simulator, live win prob LSTM' },
    { phase: 'Phase 16',      games: 500,  models: 90, note: 'All 90 models, cloud GPU, full product' },
  ]

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Games in DB"      value="3,675"  badge="3 seasons" positive />
        <MetricCard label="Shot Charts"      value="221K"   badge="569 players" positive />
        <MetricCard label="Models Live"      value="18/90"  badge="Tiers 1-2" />
        <MetricCard label="CV Clips"         value="17"     badge="Phase G: full games needed" />
      </div>

      <ChartCard title="Dataset Coverage" subtitle="Source: data/nba/ — audited 2026-03-17">
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.label} className="flex items-center gap-3 py-1.5 border-b border-gray-800/30">
              <StatusDot status={item.status} />
              <div className="flex-1 min-w-0">
                <span className="text-sm text-gray-300">{item.label}</span>
                <span className="text-xs text-gray-600 ml-2 hidden sm:inline">{item.note}</span>
              </div>
              <span className={`text-sm font-bold shrink-0 ${
                item.status === 'live' ? 'text-white' :
                item.status === 'partial' ? 'text-yellow-400' : 'text-gray-600'
              }`}>
                {item.value}
              </span>
            </div>
          ))}
        </div>
      </ChartCard>

      <ChartCard title="ML Model Roadmap" subtitle="90 models across 6 tiers — data volume gates each tier">
        <div className="space-y-3 mt-1">
          {modelMilestones.map((m, i) => (
            <div key={i} className={`flex items-start gap-3 ${i === 0 ? 'opacity-100' : 'opacity-50'}`}>
              <div className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold mt-0.5 ${
                i === 0 ? 'bg-orange-500 text-white' : 'bg-gray-800 text-gray-500 border border-gray-700'
              }`}>
                {i === 0 ? '●' : '○'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-sm font-semibold text-white">{m.phase}</span>
                  <span className="text-xs text-gray-500">{m.games}+ CV games needed</span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                    i === 0 ? 'bg-orange-500/15 text-orange-400' : 'bg-gray-800 text-gray-500'
                  }`}>
                    {m.models} models
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{m.note}</p>
              </div>
            </div>
          ))}
        </div>
      </ChartCard>
    </div>
  )
}

// ─── SHARED SUB-COMPONENTS ───────────────────────────────────────────────────
function ChartCard({ title, subtitle, children }) {
  return (
    <div className="bg-[#1a1d24] border border-gray-800 rounded-xl p-5">
      <div className="mb-4">
        <h3 className="text-sm font-bold text-white">{title}</h3>
        {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

function MetricCard({ label, value, badge, positive }) {
  return (
    <div className="bg-[#1a1d24] border border-gray-800 rounded-xl p-4">
      <div className={`text-2xl font-black ${positive ? 'text-orange-400' : 'text-white'}`}>{value}</div>
      <div className="text-xs font-semibold text-gray-400 mt-0.5">{label}</div>
      {badge && <div className="text-[11px] text-gray-600 mt-0.5">{badge}</div>}
    </div>
  )
}

function StatusDot({ status }) {
  const colors = {
    live:    'bg-green-500',
    partial: 'bg-yellow-500',
    pending: 'bg-gray-600',
  }
  return <span className={`shrink-0 w-2 h-2 rounded-full ${colors[status]}`} />
}
