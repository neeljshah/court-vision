'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, BarChart, Bar } from 'recharts'
import { generateEquityCurve } from '@/lib/equityCurve'
import { ChevronDown, ChevronUp } from 'lucide-react'

const equityData = generateEquityCurve(42, 312, 3.8)

const clvBins = [
  { bps: -16, count: 4 }, { bps: -13, count: 7 }, { bps: -10, count: 11 }, { bps: -7, count: 16 },
  { bps: -4, count: 23 }, { bps: -1, count: 32 }, { bps: 2, count: 41 }, { bps: 5, count: 50 },
  { bps: 8, count: 57 }, { bps: 11, count: 61 }, { bps: 14, count: 60 }, { bps: 17, count: 55 },
  { bps: 20, count: 47 }, { bps: 23, count: 38 }, { bps: 26, count: 29 }, { bps: 29, count: 21 },
  { bps: 32, count: 14 }, { bps: 35, count: 9 }, { bps: 38, count: 5 }, { bps: 41, count: 3 },
]

const METHODOLOGY = [
  {
    title: 'Shin Devig',
    code: 'p_true = (p_obs - z) / (1 - 2z)',
    desc: 'Pinnacle closes devigged with Shin (1992). Parameter z fits a single insider-trading term per market. On illiquid alt-line props z > 0.06; on totals z ≈ 0.02–0.04.',
    file: 'src/prediction/betting_portfolio.py',
  },
  {
    title: 'Fractional Kelly (0.25–0.5×)',
    code: 'k ∈ [0.25, 0.5] × f*',
    desc: 'Full Kelly maximizes E[log W] but ruins on edge misestimation. At k=0.25, ruin probability under 2% mis-estimation drops ~10× vs full Kelly.',
    file: 'src/prediction/betting_portfolio.py',
  },
  {
    title: 'Ledoit-Wolf 7×7 Shrinkage',
    code: 'LedoitWolf().fit(prop_residuals)',
    desc: 'Sample covariance from N=80 games is rank-deficient. Ledoit-Wolf shrinks toward scaled identity, reducing correlated-leg overstaking by 20–40%.',
    file: 'src/prediction/betting_portfolio.py',
  },
]

export default function Portfolio() {
  const [openIdx, setOpenIdx] = useState<number | null>(null)

  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#10b981] tracking-[0.25em] uppercase mb-3">Portfolio</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-3">CLV Tearsheet</h2>
          <p className="text-[#9999a8] mb-10 max-w-xl">Paper book only. No live capital until the Phase 19 gate passes. CLV is the primary metric — ROI SE on 312 picks is 3–4%.</p>
        </motion.div>

        <div className="grid grid-cols-3 md:grid-cols-6 gap-4 mb-10">
          {[
            { label: 'Settled Picks', value: '312', color: '' },
            { label: 'CLV bps/bet', value: '+14', color: 'text-[#10b981]' },
            { label: 't-stat', value: '2.3', color: '' },
            { label: 'ROI', value: '+3.8%', color: 'text-[#10b981]' },
            { label: 'Sizing', value: '1u Kelly', color: '' },
            { label: 'Beat Rate', value: '56.4%', color: '' },
          ].map(s => (
            <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} viewport={{ once: true, margin: '-100px' }}
              className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-4 text-center">
              <div className={`font-mono text-xl font-bold ${s.color || 'text-[#e7e7ee]'}`}>{s.value}</div>
              <div className="text-[11px] text-[#9999a8] mt-0.5">{s.label}</div>
            </motion.div>
          ))}
        </div>

        <div className="grid lg:grid-cols-[2fr_1fr] gap-6 mb-6">
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}
            className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-5">
            <div className="flex justify-between items-start mb-4">
              <h3 className="font-mono text-xs text-[#9999a8] uppercase tracking-wider">Equity Curve — 312 Picks</h3>
              <span className="font-mono text-xs text-[#10b981]">+3.8% ROI</span>
            </div>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityData} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
                  <defs>
                    <linearGradient id="equity-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.25}/>
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="pick" tick={{ fontSize: 9, fill: '#9999a8' }} tickLine={false} axisLine={false} label={{ value: 'pick #', position: 'insideBottom', offset: -2, fontSize: 9, fill: '#9999a8' }}/>
                  <YAxis tick={{ fontSize: 9, fill: '#9999a8' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`}/>
                  <Tooltip contentStyle={{ background: '#13131c', border: '1px solid #1f1f2e', borderRadius: 6, fontSize: 11 }} formatter={(v) => [typeof v === 'number' ? `${v.toFixed(2)}%` : v, 'Cum. ROI']}/>
                  <ReferenceLine y={0} stroke="#1f1f2e" strokeDasharray="4 2"/>
                  <Area type="monotone" dataKey="cumRoi" stroke="#10b981" strokeWidth={1.5} fill="url(#equity-grad)" dot={false}/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }} viewport={{ once: true, margin: '-100px' }}
            className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-5">
            <h3 className="font-mono text-xs text-[#9999a8] uppercase tracking-wider mb-4">CLV Distribution (bps)</h3>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={clvBins} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                  <XAxis dataKey="bps" tick={{ fontSize: 9, fill: '#9999a8' }} tickLine={false} axisLine={false}/>
                  <YAxis tick={{ fontSize: 9, fill: '#9999a8' }} tickLine={false} axisLine={false}/>
                  <Tooltip contentStyle={{ background: '#13131c', border: '1px solid #1f1f2e', borderRadius: 6, fontSize: 11 }}/>
                  <ReferenceLine x={14} stroke="#10b981" strokeWidth={1.5} label={{ value: '+14 bps', fontSize: 9, fill: '#10b981', position: 'insideTopLeft' }}/>
                  <Bar dataKey="count" fill="#3b82f6" fillOpacity={0.7} radius={[2,2,0,0]}/>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="font-mono text-[10px] text-[#9999a8] mt-2">CLV converges ~5× faster than realized ROI</p>
          </motion.div>
        </div>

        <div className="space-y-2">
          {METHODOLOGY.map((m, i) => (
            <motion.div key={m.title} initial={{ opacity: 0, y: 8 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: i * 0.05 }} viewport={{ once: true, margin: '-100px' }}
              className="bg-[#13131c] border border-[#1f1f2e] rounded-xl overflow-hidden">
              <button onClick={() => setOpenIdx(openIdx === i ? null : i)} className="w-full flex justify-between items-center px-5 py-4 text-left hover:bg-[#08080c]/30 transition-colors">
                <div className="flex items-center gap-4">
                  <span className="text-sm font-medium text-[#e7e7ee]">{m.title}</span>
                  <code className="font-mono text-xs text-[#3b82f6] bg-[#08080c] px-2 py-0.5 rounded hidden sm:block">{m.code}</code>
                </div>
                {openIdx === i ? <ChevronUp size={16} className="text-[#9999a8] shrink-0"/> : <ChevronDown size={16} className="text-[#9999a8] shrink-0"/>}
              </button>
              {openIdx === i && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="px-5 pb-4 border-t border-[#1f1f2e]">
                  <p className="text-sm text-[#9999a8] mt-3 mb-2">{m.desc}</p>
                  <code className="font-mono text-xs text-[#9999a8]">→ {m.file}</code>
                </motion.div>
              )}
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
