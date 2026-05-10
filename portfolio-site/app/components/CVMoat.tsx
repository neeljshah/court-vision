'use client'
import { motion } from 'framer-motion'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

function HalfCourt({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 200 106" className="w-full max-w-[260px] mx-auto">
      <rect x="0" y="0" width="200" height="106" rx="2" fill="#0d0d18" stroke="#1f1f2e" strokeWidth="0.8"/>
      <rect x="4" y="4" width="192" height="98" fill="none" stroke="#2a2a3a" strokeWidth="0.8"/>
      <rect x="4" y="36" width="60" height="34" fill="none" stroke="#2a2a3a" strokeWidth="0.8"/>
      <line x1="64" y1="36" x2="64" y2="70" stroke="#2a2a3a" strokeWidth="0.8"/>
      <ellipse cx="64" cy="53" rx="18" ry="18" fill="none" stroke="#2a2a3a" strokeWidth="0.8" strokeDasharray="2 2"/>
      <path d="M4 22 Q70 106 136 53 Q136 0 4 84" fill="none" stroke="#2a2a3a" strokeWidth="0.8"/>
      <ellipse cx="24" cy="53" rx="10" ry="10" fill="none" stroke="#2a2a3a" strokeWidth="0.6" strokeDasharray="1.5 1.5"/>
      <circle cx="24" cy="53" r="2.5" fill="none" stroke="#3b82f6" strokeWidth="1"/>
      <circle cx="24" cy="53" r="0.8" fill="#3b82f6"/>
      {children}
    </svg>
  )
}

const fatigueData = Array.from({length: 48}, (_, i) => ({
  min: i + 1,
  dist: 0.8 + 0.4 * Math.sin(i * 0.3) + 0.2 * Math.sin(i * 0.7) + (i > 36 ? 0.3 * Math.sin((i-36) * 0.5) : 0),
  decay: Math.max(0.2, 0.9 - i * 0.015 + 0.1 * Math.sin(i * 0.4)),
}))

export default function CVMoat() {
  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#f97316] tracking-[0.25em] uppercase mb-3">The Moat</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-3">Spatial CV Features</h2>
          <p className="text-[#9999a8] mb-12 max-w-xl">Three features extracted from broadcast video that do not exist in any public NBA dataset.</p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6 mb-8">
          {/* Card 1: defender_distance */}
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}
            className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="font-mono text-xs text-[#f97316] uppercase tracking-wider">defender_distance</p>
                <p className="text-sm text-[#9999a8] mt-1">Meters to nearest defender at shot release</p>
              </div>
              <div className="text-right">
                <div className="font-mono text-lg font-bold text-[#f97316]">14%</div>
                <div className="text-[10px] text-[#9999a8]">SHAP mass</div>
              </div>
            </div>
            <HalfCourt>
              <circle cx="90" cy="53" r="4" fill="#3b82f6" opacity="0.9"/>
              <circle cx="70" cy="30" r="3.5" fill="#3b82f6" opacity="0.7"/>
              <circle cx="70" cy="76" r="3.5" fill="#3b82f6" opacity="0.7"/>
              <circle cx="110" cy="30" r="3.5" fill="#3b82f6" opacity="0.7"/>
              <circle cx="110" cy="76" r="3.5" fill="#3b82f6" opacity="0.7"/>
              <circle cx="85" cy="42" r="3.5" fill="#ef4444" opacity="0.8"/>
              <circle cx="65" cy="25" r="3.5" fill="#ef4444" opacity="0.7"/>
              <circle cx="65" cy="81" r="3.5" fill="#ef4444" opacity="0.7"/>
              <circle cx="105" cy="25" r="3.5" fill="#ef4444" opacity="0.7"/>
              <circle cx="105" cy="81" r="3.5" fill="#ef4444" opacity="0.7"/>
              <circle cx="90" cy="53" r="5" fill="none" stroke="#f97316" strokeWidth="1.5"/>
              <line x1="90" y1="53" x2="85" y2="42" stroke="#f97316" strokeWidth="1" strokeDasharray="3 2"/>
              <text x="87" y="47" fill="#f97316" fontSize="5" fontFamily="monospace">1.8m</text>
            </HalfCourt>
          </motion.div>

          {/* Card 2: spacing_score */}
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }} viewport={{ once: true, margin: '-100px' }}
            className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="font-mono text-xs text-[#f97316] uppercase tracking-wider">spacing_score</p>
                <p className="text-sm text-[#9999a8] mt-1">Convex hull area of 4 off-ball offense</p>
              </div>
              <div className="text-right">
                <div className="font-mono text-lg font-bold text-[#f97316]">11%</div>
                <div className="text-[10px] text-[#9999a8]">SHAP mass</div>
              </div>
            </div>
            <HalfCourt>
              <circle cx="70" cy="30" r="3.5" fill="#3b82f6" opacity="0.9"/>
              <circle cx="70" cy="76" r="3.5" fill="#3b82f6" opacity="0.9"/>
              <circle cx="110" cy="30" r="3.5" fill="#3b82f6" opacity="0.9"/>
              <circle cx="110" cy="76" r="3.5" fill="#3b82f6" opacity="0.9"/>
              <polygon points="70,30 110,30 110,76 70,76" fill="#3b82f6" fillOpacity="0.12" stroke="#3b82f6" strokeWidth="1" strokeDasharray="3 2"/>
              <circle cx="90" cy="53" r="4" fill="#f97316" opacity="0.9"/>
              <circle cx="85" cy="42" r="3.5" fill="#ef4444" opacity="0.7"/>
              <circle cx="65" cy="25" r="3.5" fill="#ef4444" opacity="0.6"/>
              <circle cx="65" cy="81" r="3.5" fill="#ef4444" opacity="0.6"/>
              <circle cx="105" cy="25" r="3.5" fill="#ef4444" opacity="0.6"/>
              <circle cx="105" cy="81" r="3.5" fill="#ef4444" opacity="0.6"/>
              <text x="86" y="58" fill="#3b82f6" fontSize="4.5" fontFamily="monospace">hull=1840ft²</text>
            </HalfCourt>
          </motion.div>

          {/* Card 3: legs_fatigue chart */}
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2 }} viewport={{ once: true, margin: '-100px' }}
            className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="font-mono text-xs text-[#f97316] uppercase tracking-wider">legs_fatigue</p>
                <p className="text-sm text-[#9999a8] mt-1">Cumulative run distance, 6-min decay</p>
              </div>
              <div className="text-right">
                <div className="font-mono text-lg font-bold text-[#f97316]">6%</div>
                <div className="text-[10px] text-[#9999a8]">SHAP mass</div>
              </div>
            </div>
            <div className="h-36">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={fatigueData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <defs>
                    <linearGradient id="fatigue-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f97316" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#f97316" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="min" tick={{ fontSize: 9, fill: '#9999a8' }} tickLine={false} axisLine={false} label={{ value: 'minute', position: 'insideBottom', offset: -2, fontSize: 9, fill: '#9999a8' }}/>
                  <YAxis tick={{ fontSize: 9, fill: '#9999a8' }} tickLine={false} axisLine={false}/>
                  <Tooltip contentStyle={{ background: '#13131c', border: '1px solid #1f1f2e', borderRadius: 6, fontSize: 11 }} labelStyle={{ color: '#9999a8' }}/>
                  <ReferenceLine x={36} stroke="#3b82f6" strokeDasharray="4 2" strokeWidth={1} label={{ value: '6-min window', fontSize: 8, fill: '#3b82f6', position: 'insideTopLeft' }}/>
                  <Area type="monotone" dataKey="dist" stroke="#f97316" strokeWidth={1.5} fill="url(#fatigue-grad)" dot={false}/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </motion.div>
        </div>

        <motion.div initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} viewport={{ once: true, margin: '-100px' }}
          className="bg-[#13131c] border border-[#f97316]/20 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1">
            <span className="font-mono text-sm text-[#f97316]">Combined: 31% SHAP mass · ΔR² = +0.08 vs API-only baseline</span>
            <p className="text-xs text-[#9999a8] mt-1">Measured on pts model. Walk-forward, season-purged. Train on game_date &lt; t, evaluate on game_date ≥ t, 48h purge window.</p>
          </div>
          <div className="font-mono text-xs text-[#9999a8] shrink-0">src/features/feature_engineering.py</div>
        </motion.div>
      </div>
    </section>
  )
}
