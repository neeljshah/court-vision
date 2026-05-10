'use client'
import { motion } from 'framer-motion'

const PRINCIPLES = [
  { n: '01', title: 'Walk-forward, purged, always.', body: 'K-fold on time-ordered data is a correctness bug. Train on game_date < t, evaluate on ≥ t, 48h purge window. No exceptions.' },
  { n: '02', title: 'Baselines first.', body: "Every model has a cheap API-only baseline it must beat. Δ reported before the headline number. If alt data doesn't move R² past noise, it doesn't ship." },
  { n: '03', title: 'CLV over ROI.', body: "ROI on 312 picks has SE of 3–4%. CLV against Pinnacle's close is approximately unbiased and converges ~5× faster." },
  { n: '04', title: 'Calibration ≠ accuracy.', body: 'Reliability diagrams and ECE on every probabilistic model. An accurate but miscalibrated model cannot be safely sized with Kelly.' },
  { n: '05', title: 'Ship the bug list.', body: "R²=0.09 for steals is in the table. If I can't name what's wrong, I haven't understood it." },
  { n: '06', title: 'Reproducibility is a feature.', body: 'SHA256 manifests, seeded Monte Carlo, pinned snapshots. A reviewer with source videos reproduces headline numbers bit-exactly.' },
  { n: '07', title: 'Costs modeled, not assumed.', body: "Kelly fractions account for slippage and vig differential. CLV measured net of Pinnacle's margin, not gross." },
]

export default function Principles() {
  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#3b82f6] tracking-[0.25em] uppercase mb-3">Research Principles</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-12">Methodology</h2>
        </motion.div>
        <div className="space-y-px">
          {PRINCIPLES.map((p, i) => (
            <motion.div key={p.n} initial={{ opacity: 0, x: -16 }} whileInView={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: i * 0.05 }} viewport={{ once: true, margin: '-100px' }}
              className="flex gap-6 py-5 border-l-2 border-[#3b82f6] pl-6 bg-[#13131c]/30 hover:bg-[#13131c]/60 transition-colors rounded-r-lg pr-4">
              <span className="font-mono text-sm text-[#3b82f6] shrink-0 mt-0.5 w-6">{p.n}</span>
              <div>
                <p className="text-sm font-medium text-[#e7e7ee] mb-1">{p.title}</p>
                <p className="text-sm text-[#9999a8] leading-relaxed">{p.body}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
