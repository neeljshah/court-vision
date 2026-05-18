'use client'
import { motion } from 'framer-motion'

const STACK = [
  { domain: 'CV / Tracking', pills: ['YOLOv8n', 'OpenCV', 'SIFT', 'EasyOCR', 'OSNet re-ID', 'PyTorch', 'decord (NVDEC)'] },
  { domain: 'ML', pills: ['XGBoost', 'LightGBM', 'CatBoost', 'scikit-learn', 'cvxpy (QP)'] },
  { domain: 'Calibration', pills: ['Isotonic regression', 'Conformal prediction', 'Reliability diagrams'] },
  { domain: 'Time-series', pills: ['Prophet', 'Exogenous regressors', 'Walk-forward harness'] },
  { domain: 'Data', pills: ['nba_api', 'pandas', 'SQLite', 'PostgreSQL', 'dbt', 'BigQuery'] },
  { domain: 'Serving', pills: ['FastAPI', 'Next.js', 'D3.js', 'WebSocket', 'TTL cache'] },
  { domain: 'Infra', pills: ['RunPod GPU', 'Hetzner VPS', 'GitHub Actions', 'Docker', 'B2'] },
  { domain: 'Languages', pills: ['Python 3.9', 'SQL', 'bash', 'TypeScript'] },
]

export default function Stack() {
  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#3b82f6] tracking-[0.25em] uppercase mb-3">Stack</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-12">Technologies</h2>
        </motion.div>
        <div className="space-y-6">
          {STACK.map((group, i) => (
            <motion.div key={group.domain} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: i * 0.04 }} viewport={{ once: true, margin: '-100px' }}
              className="flex flex-col sm:flex-row sm:items-start gap-3">
              <span className="font-mono text-xs text-[#9999a8] uppercase tracking-wider sm:w-36 shrink-0 pt-1">{group.domain}</span>
              <div className="flex flex-wrap gap-2">
                {group.pills.map(p => (
                  <span key={p} className="text-xs font-mono text-[#e7e7ee] bg-[#13131c] border border-[#1f1f2e] px-2.5 py-1 rounded-full hover:border-[#3b82f6]/50 transition-colors">{p}</span>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
