'use client'
import { motion } from 'framer-motion'

const PROJECTS = [
  {
    name: 'SunSolor',
    period: '2025',
    role: 'Demand Forecasting + GenAI Ops',
    desc: 'Prophet with exogenous regressors (weather, permits, solar capacity) on daily residential install volume. GPT-4o agent with SQL tools over BigQuery for natural-language ops queries.',
    stats: [{ label: 'Holdout MAPE', value: '<8%' }, { label: 'Platform', value: 'GCP/BigQuery' }, { label: 'Downstream', value: 'Crew scheduling' }],
    tags: ['Prophet', 'GPT-4o', 'BigQuery', 'dbt'],
  },
  {
    name: 'Fortrex Securities',
    period: '2023–2024',
    role: 'BI & Payments Data Engineering',
    desc: 'Windowed z-score anomaly detection with regime-aware thresholds on live transaction streams. SQL optimization against 7-figure row tables for executive P&L dashboards.',
    stats: [{ label: 'SLA', value: '99.9%' }, { label: 'Table scale', value: '7-figure rows' }, { label: 'Type', value: 'Financial DE' }],
    tags: ['SQL', 'Anomaly Detection', 'Payments', 'Python'],
  },
  {
    name: 'Spatial Intelligence Layer',
    period: '2024',
    role: 'Shot Quality Engine',
    desc: 'SIFT homography to court coordinates. KDE over shot locations weighted by defender proximity and shot-clock state yields zone-level xFG. K-Means lineup archetype detection precursor to spacing_score.',
    stats: [{ label: 'Method', value: 'KDE + K-Means' }, { label: 'Output', value: 'xFG per zone' }, { label: 'Now', value: 'In CourtVision' }],
    tags: ['SIFT', 'KDE', 'K-Means', 'Court geometry'],
  },
]

export default function OtherWork() {
  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#3b82f6] tracking-[0.25em] uppercase mb-3">Other Work</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-12">Projects</h2>
        </motion.div>
        <div className="grid md:grid-cols-3 gap-5">
          {PROJECTS.map((p, i) => (
            <motion.div key={p.name} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: i * 0.1 }} viewport={{ once: true, margin: '-100px' }}
              className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-6 flex flex-col gap-4">
              <div>
                <div className="flex justify-between items-start mb-1">
                  <h3 className="font-semibold text-[#e7e7ee]">{p.name}</h3>
                  <span className="font-mono text-xs text-[#9999a8]">{p.period}</span>
                </div>
                <p className="text-xs text-[#3b82f6] font-mono">{p.role}</p>
              </div>
              <p className="text-sm text-[#9999a8] leading-relaxed">{p.desc}</p>
              <div className="grid grid-cols-3 gap-2">
                {p.stats.map(s => (
                  <div key={s.label} className="bg-[#08080c] rounded-lg p-2 text-center border border-[#1f1f2e]/50">
                    <div className="font-mono text-xs font-bold text-[#e7e7ee]">{s.value}</div>
                    <div className="text-[10px] text-[#9999a8] mt-0.5">{s.label}</div>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {p.tags.map(t => (
                  <span key={t} className="text-[11px] font-mono text-[#9999a8] border border-[#1f1f2e] rounded px-2 py-0.5">{t}</span>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
