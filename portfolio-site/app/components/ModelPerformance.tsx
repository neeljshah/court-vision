'use client'
import { motion } from 'framer-motion'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ScatterChart, Scatter, ReferenceLine } from 'recharts'

interface ModelRow { model: string; target: string; r2: number; mae: number; ece: number; delta: string }

const MODELS: ModelRow[] = [
  { model: 'props_pts', target: 'points', r2: 0.47, mae: 4.9, ece: 0.021, delta: '+0.08 ΔR²' },
  { model: 'props_reb', target: 'rebounds', r2: 0.40, mae: 2.1, ece: 0.028, delta: '—' },
  { model: 'props_ast', target: 'assists', r2: 0.46, mae: 1.7, ece: 0.024, delta: '—' },
  { model: 'props_fg3m', target: '3-pointers', r2: 0.28, mae: 1.0, ece: 0.035, delta: '—' },
  { model: 'props_tov', target: 'turnovers', r2: 0.25, mae: 1.1, ece: 0.041, delta: '—' },
  { model: 'props_blk', target: 'blocks', r2: 0.18, mae: 0.6, ece: 0.056, delta: '—' },
  { model: 'props_stl', target: 'steals', r2: 0.09, mae: 0.7, ece: 0.071, delta: '—' },
]

const r2Color = (v: number) => v > 0.4 ? '#10b981' : v > 0.2 ? '#f59e0b' : '#ef4444'

const calibData = [
  { predicted: 0.1, actual: 0.09 }, { predicted: 0.2, actual: 0.21 }, { predicted: 0.3, actual: 0.28 },
  { predicted: 0.4, actual: 0.39 }, { predicted: 0.5, actual: 0.51 }, { predicted: 0.6, actual: 0.62 },
  { predicted: 0.7, actual: 0.69 }, { predicted: 0.8, actual: 0.81 }, { predicted: 0.9, actual: 0.88 },
]

export default function ModelPerformance() {
  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#3b82f6] tracking-[0.25em] uppercase mb-3">Model Performance</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-3">Prediction Stack</h2>
          <p className="text-[#9999a8] mb-2 max-w-xl">Walk-forward, season-purged. Train on game_date &lt; t, evaluate on game_date ≥ t, 48h purge window.</p>
          <p className="font-mono text-xs text-[#9999a8] mb-10">R²=0.09 (steals) is not hidden — it defines where the model must not be trusted.</p>
        </motion.div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
          {[
            { label: 'Prop Models', value: '7', sub: 'pts/reb/ast/fg3m/blk/tov/stl' },
            { label: 'Best R²', value: '0.47', sub: 'pts model' },
            { label: 'Mean ECE', value: '0.039', sub: 'across 7 models' },
            { label: 'Test Suite', value: '960+', sub: 'passing tests' },
          ].map(k => (
            <motion.div key={k.label} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} viewport={{ once: true, margin: '-100px' }}
              className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-4">
              <div className="font-mono text-2xl font-bold text-[#e7e7ee]">{k.value}</div>
              <div className="text-xs text-[#9999a8] mt-0.5">{k.label}</div>
              <div className="font-mono text-[10px] text-[#9999a8] mt-1 opacity-60">{k.sub}</div>
            </motion.div>
          ))}
        </div>

        <div className="grid lg:grid-cols-2 gap-8 mb-8">
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}
            className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-5">
            <h3 className="font-mono text-xs text-[#9999a8] uppercase tracking-wider mb-4">R² by Model — Walk-Forward Holdout</h3>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={MODELS} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 60 }}>
                  <XAxis type="number" domain={[0, 0.6]} tick={{ fontSize: 10, fill: '#9999a8' }} tickLine={false} axisLine={false}/>
                  <YAxis type="category" dataKey="target" tick={{ fontSize: 10, fill: '#9999a8' }} tickLine={false} axisLine={false} width={58}/>
                  <Tooltip contentStyle={{ background: '#13131c', border: '1px solid #1f1f2e', borderRadius: 6, fontSize: 11 }} formatter={(v) => [typeof v === 'number' ? v.toFixed(3) : v, 'R²']}/>
                  <ReferenceLine x={0.2} stroke="#1f1f2e" strokeDasharray="3 2"/>
                  <ReferenceLine x={0.4} stroke="#1f1f2e" strokeDasharray="3 2"/>
                  <Bar dataKey="r2" radius={[0, 3, 3, 0]}>
                    {MODELS.map((m) => <Cell key={m.model} fill={r2Color(m.r2)}/>)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }} viewport={{ once: true, margin: '-100px' }}
            className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-5">
            <h3 className="font-mono text-xs text-[#9999a8] uppercase tracking-wider mb-1">Reliability Diagram — pts model</h3>
            <p className="text-[11px] text-[#9999a8] mb-3 font-mono">ECE = 0.021 · closer to diagonal = better calibrated</p>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 4, right: 8, bottom: 16, left: -16 }}>
                  <XAxis type="number" dataKey="predicted" domain={[0,1]} tick={{ fontSize: 10, fill: '#9999a8' }} tickLine={false} axisLine={false} label={{ value: 'Predicted prob', position: 'insideBottom', offset: -10, fontSize: 10, fill: '#9999a8' }}/>
                  <YAxis type="number" dataKey="actual" domain={[0,1]} tick={{ fontSize: 10, fill: '#9999a8' }} tickLine={false} axisLine={false} label={{ value: 'Actual', angle: -90, position: 'insideLeft', offset: 12, fontSize: 10, fill: '#9999a8' }}/>
                  <Tooltip contentStyle={{ background: '#13131c', border: '1px solid #1f1f2e', borderRadius: 6, fontSize: 11 }} formatter={(v) => [typeof v === 'number' ? v.toFixed(2) : v]}/>
                  <ReferenceLine segment={[{x:0,y:0},{x:1,y:1}]} stroke="#3b82f6" strokeDasharray="4 2" strokeWidth={1.5}/>
                  <Scatter data={calibData} fill="#10b981" opacity={0.8}/>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </motion.div>
        </div>

        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}
          className="bg-[#13131c] border border-[#1f1f2e] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1f1f2e]">
                  {['Model', 'Target', 'R²', 'MAE', 'ECE', 'vs Baseline'].map(h => (
                    <th key={h} className="px-4 py-3 text-left font-mono text-xs text-[#9999a8] uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MODELS.map((m, i) => (
                  <tr key={m.model} className={`border-b border-[#1f1f2e]/50 ${i % 2 === 0 ? '' : 'bg-[#08080c]/30'}`}>
                    <td className="px-4 py-3 font-mono text-xs text-[#3b82f6]">{m.model}</td>
                    <td className="px-4 py-3 text-[#9999a8] text-xs">{m.target}</td>
                    <td className="px-4 py-3 font-mono text-sm" style={{ color: r2Color(m.r2) }}>{m.r2.toFixed(3)}</td>
                    <td className="px-4 py-3 font-mono text-sm text-[#e7e7ee]">{m.mae.toFixed(1)}</td>
                    <td className="px-4 py-3 font-mono text-sm text-[#e7e7ee]">{m.ece.toFixed(3)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[#f97316]">{m.delta}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
