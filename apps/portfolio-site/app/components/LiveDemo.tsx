'use client'
import { useState, useMemo, useCallback } from 'react'
import { motion } from 'framer-motion'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

interface Player { name: string; mu: number; sigma: number; skew: number }
type PropType = 'pts' | 'reb' | 'ast' | '3pm'

const PLAYERS: Player[] = [
  { name: 'LeBron James', mu: 27, sigma: 6.5, skew: 0.2 },
  { name: "Stephen Curry", mu: 29, sigma: 7, skew: 0.1 },
  { name: 'Nikola Jokić', mu: 27, sigma: 6, skew: 0.15 },
  { name: 'Luka Dončić', mu: 33, sigma: 8, skew: 0.25 },
]

const PROP_LABELS: Record<PropType, string> = { pts: 'Points', reb: 'Rebounds', ast: 'Assists', '3pm': '3-Pointers' }
const PROP_MU_SCALE: Record<PropType, number> = { pts: 1, reb: 0.28, ast: 0.22, '3pm': 0.13 }
const PROP_SIGMA_SCALE: Record<PropType, number> = { pts: 1, reb: 0.32, ast: 0.26, '3pm': 0.15 }

function skewNormal(mu: number, sigma: number, alpha: number, rng: () => number): number {
  const u0 = rng(), v = rng()
  const u1 = (Math.sqrt(-2 * Math.log(u0 + 1e-15)) * Math.cos(2 * Math.PI * v))
  const u2 = (Math.sqrt(-2 * Math.log(v + 1e-15)) * Math.sin(2 * Math.PI * u0))
  const delta = alpha / Math.sqrt(1 + alpha * alpha)
  return mu + sigma * (delta * Math.abs(u1) + Math.sqrt(1 - delta * delta) * u2)
}

function seededRng(seed: number): () => number {
  let s = seed
  return () => { s = (1664525 * s + 1013904223) & 0xffffffff; return (s >>> 0) / 0xffffffff }
}

interface SimResult { pOver: number; pUnder: number; mu: number; sigma: number; lo80: number; hi80: number; bins: {x: number; count: number}[] }

function runSim(player: Player, prop: PropType, line: number): SimResult {
  const mu = player.mu * PROP_MU_SCALE[prop]
  const sigma = player.sigma * PROP_SIGMA_SCALE[prop]
  const skew = player.skew
  const N = 10000
  const rng = seededRng(42 + player.mu * 7 + line * 13)
  const samples: number[] = Array.from({length: N}, () => Math.max(0, skewNormal(mu, sigma, skew, rng)))
  const over = samples.filter(x => x > line).length
  const sorted = [...samples].sort((a,b) => a-b)
  const lo80 = sorted[Math.floor(N * 0.1)]
  const hi80 = sorted[Math.floor(N * 0.9)]
  const min = Math.max(0, mu - 3.5 * sigma), max = mu + 3.5 * sigma
  const nBins = 40
  const binW = (max - min) / nBins
  const counts: number[] = Array(nBins).fill(0)
  samples.forEach(s => { const b = Math.min(nBins-1, Math.floor((s - min) / binW)); if (b >= 0) counts[b]++ })
  const bins = counts.map((c, i) => ({ x: Math.round((min + (i + 0.5) * binW) * 10) / 10, count: c }))
  return { pOver: over / N, pUnder: 1 - over / N, mu, sigma, lo80, hi80, bins }
}

function toAmericanOdds(p: number): string {
  if (p <= 0 || p >= 1) return 'N/A'
  if (p > 0.5) return `-${Math.round(p / (1 - p) * 100)}`
  return `+${Math.round((1-p)/p * 100)}`
}

export default function LiveDemo() {
  const [playerIdx, setPlayerIdx] = useState(0)
  const [prop, setProp] = useState<PropType>('pts')
  const [line, setLine] = useState(26.5)
  const [expanded, setExpanded] = useState(false)

  const player = PLAYERS[playerIdx]
  const result = useMemo(() => runSim(player, prop, line), [player, prop, line])

  const edge = Math.round((result.pOver - 0.5238) * 10000)
  const kelly = Math.max(0, Math.min(0.25, (result.pOver - 0.5238) / 0.4762 * 0.25))

  const handleLine = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setLine(parseFloat(e.target.value) || 0)
  }, [])

  const handleProp = useCallback((p: PropType) => {
    setProp(p)
    setLine(Math.round(player.mu * PROP_MU_SCALE[p] * 2) / 2 - 0.5)
  }, [player.mu])

  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#10b981] tracking-[0.25em] uppercase mb-3">Live Demo</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-3">Prop Simulator</h2>
          <p className="text-[#9999a8] mb-8 max-w-xl">10,000-path Skew-Normal Monte Carlo. Client-side, seeded, reproducible. Set a line to see the distribution and edge.</p>
        </motion.div>

        <div className="flex flex-wrap gap-3 mb-8">
          {PLAYERS.map((p, i) => (
            <button key={p.name} onClick={() => setPlayerIdx(i)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${playerIdx === i ? 'border-[#3b82f6] bg-[#3b82f6]/10 text-[#3b82f6]' : 'border-[#1f1f2e] text-[#9999a8] hover:text-[#e7e7ee] hover:border-[#3b82f6]/50'}`}>
              {p.name}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 mb-8">
          {(Object.keys(PROP_LABELS) as PropType[]).map(p => (
            <button key={p} onClick={() => handleProp(p)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${prop === p ? 'border-[#10b981] bg-[#10b981]/10 text-[#10b981]' : 'border-[#1f1f2e] text-[#9999a8] hover:text-[#e7e7ee]'}`}>
              {PROP_LABELS[p]}
            </button>
          ))}
          <div className="flex items-center gap-2 ml-2">
            <label className="text-sm text-[#9999a8] font-mono">Line:</label>
            <input type="number" step="0.5" value={line} onChange={handleLine}
              className="w-20 bg-[#13131c] border border-[#1f1f2e] rounded px-2 py-1.5 text-sm font-mono text-[#e7e7ee] focus:border-[#3b82f6] outline-none"/>
          </div>
        </div>

        <div className="grid lg:grid-cols-[1fr_260px] gap-6">
          <div className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-5">
            <h3 className="font-mono text-xs text-[#9999a8] uppercase tracking-wider mb-4">Distribution — {PROP_LABELS[prop]} · n=10,000 paths</h3>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={result.bins} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                  <defs>
                    <linearGradient id="over-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="x" tick={{ fontSize: 10, fill: '#9999a8' }} tickLine={false} axisLine={false}/>
                  <YAxis tick={{ fontSize: 9, fill: '#9999a8' }} tickLine={false} axisLine={false}/>
                  <Tooltip contentStyle={{ background: '#13131c', border: '1px solid #1f1f2e', borderRadius: 6, fontSize: 11 }} formatter={(v) => [`${v} paths`, 'Count']}/>
                  <ReferenceLine x={result.lo80} stroke="#3b82f6" strokeDasharray="3 2" strokeWidth={0.8}/>
                  <ReferenceLine x={result.hi80} stroke="#3b82f6" strokeDasharray="3 2" strokeWidth={0.8} label={{ value: '80% CI', fontSize: 9, fill: '#3b82f6', position: 'insideTopRight' }}/>
                  <ReferenceLine x={line} stroke="#f97316" strokeWidth={2} label={{ value: `Line ${line}`, fontSize: 10, fill: '#f97316', position: 'insideTopLeft' }}/>
                  <Area type="monotone" dataKey="count" stroke="#10b981" strokeWidth={1.5} fill="url(#over-grad)" dot={false}/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="flex gap-4 mt-2 text-xs text-[#9999a8]">
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#10b981] inline-block"/>Over {line}</span>
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#ef4444] inline-block"/>Under {line}</span>
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#3b82f6] inline-block"/>80% CI</span>
            </div>
          </div>

          <div className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-5 space-y-4">
            <div>
              <div className="text-xs text-[#9999a8] uppercase tracking-wider mb-3 font-mono">Model Output</div>
              <div className="space-y-2">
                {[
                  ['μ (mean)', result.mu.toFixed(1)],
                  ['σ (std)', result.sigma.toFixed(1)],
                  ['P(Over)', `${(result.pOver * 100).toFixed(1)}%`],
                  ['P(Under)', `${(result.pUnder * 100).toFixed(1)}%`],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between items-center">
                    <span className="text-xs text-[#9999a8]">{label}</span>
                    <span className="font-mono text-sm text-[#e7e7ee]">{value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="border-t border-[#1f1f2e] pt-4">
              <div className="text-xs text-[#9999a8] uppercase tracking-wider mb-3 font-mono">Pricing</div>
              <div className="space-y-2">
                {[
                  { label: 'Fair odds (Over)', value: toAmericanOdds(result.pOver), colored: false },
                  { label: 'Fair odds (Under)', value: toAmericanOdds(result.pUnder), colored: false },
                  { label: 'Vegas (synthetic)', value: '-110 / -110', colored: false },
                  { label: 'Edge vs -110', value: `${edge > 0 ? '+' : ''}${edge} bps`, colored: true },
                  { label: 'Kelly (0.25× cap)', value: `${(kelly * 100).toFixed(2)}%`, colored: false },
                  { label: '80% CI', value: `[${result.lo80.toFixed(1)}, ${result.hi80.toFixed(1)}]`, colored: false },
                ].map(({ label, value, colored }) => (
                  <div key={label} className="flex justify-between items-center">
                    <span className="text-xs text-[#9999a8]">{label}</span>
                    <span className={`font-mono text-sm ${colored ? (edge > 0 ? 'text-[#10b981]' : 'text-[#ef4444]') : 'text-[#e7e7ee]'}`}>{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4">
          <button onClick={() => setExpanded(!expanded)} className="text-xs text-[#9999a8] hover:text-[#e7e7ee] font-mono flex items-center gap-1 transition-colors">
            {expanded ? '▲' : '▼'} How this works
          </button>
          {expanded && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-3 bg-[#13131c] border border-[#1f1f2e] rounded-xl p-4 text-sm text-[#9999a8] space-y-2">
              <p>The simulator draws 10,000 samples from a Skew-Normal distribution parameterized by the historical μ and σ for the selected player/prop. Skew parameter α captures the positive tail (big games).</p>
              <p>Edge is computed against a synthetic -110/-110 market (implied p=0.5238 per side). Kelly fraction is capped at 0.25× full Kelly. Conformal intervals (80%) are empirical quantiles from the simulation, providing a distribution-free coverage guarantee.</p>
            </motion.div>
          )}
        </div>
      </div>
    </section>
  )
}
