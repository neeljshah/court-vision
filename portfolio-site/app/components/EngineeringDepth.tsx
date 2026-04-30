'use client'
import { motion } from 'framer-motion'
import { Database, Cpu, GitCommit, ShieldCheck } from 'lucide-react'

const CARDS = [
  {
    icon: Database,
    title: 'Ingest Queue',
    desc: 'SQLite-backed parallel job queue with claim-race retry, per-game quality scoring (ball_valid_pct, homography_coverage), and reset_stale_jobs.py for pods that OOM mid-game.',
    code: `python -m src.ingest.manifest migrate\npython scripts/ingest_process.py --max-games 80 --parallel 4`,
    stat: '17 → 80 games targeted',
    file: 'src/ingest/processing_worker.py',
  },
  {
    icon: Cpu,
    title: 'GPU Optimization',
    desc: 'CFS quota detection (17.85 cores on RunPod 3090). OMP thread cap eliminates 45% throttle rate. decord NVDEC moves decode to GPU. _VRAM_FLUSH_INTERVAL=3000 prevents sync stalls.',
    code: `OMP_NUM_THREADS=6 MKL_NUM_THREADS=6 \\\npython scripts/ingest_process.py --parallel 4`,
    stat: '45 → 80 fps aggregate',
    file: 'scripts/launch_single_3090_pod.sh',
  },
  {
    icon: GitCommit,
    title: 'Reproducibility',
    desc: 'SHA256 manifests at data/release/v0.14/output_hashes.txt. Seeded Monte Carlo (--seed 42). Pinned data snapshots. A reviewer with source videos reproduces the headline table bit-exactly.',
    code: `python scripts/reproduce.py --seed 42\n# verifies output_hashes.txt bit-exactly`,
    stat: 'Bit-exact reproduction',
    file: 'data/release/v0.14/output_hashes.txt',
  },
  {
    icon: ShieldCheck,
    title: 'Test Coverage',
    desc: '960+ passing tests across 13 complete phases. FastAPI serving 9 endpoints with in-process TTL cache. Phase suites isolated — no cross-phase test bleed.',
    code: `python -m pytest tests/ -q\n# 960+ passed, 93 skipped (GPU/PG)`,
    stat: '960+ tests · 13 phases',
    file: 'tests/',
  },
]

export default function EngineeringDepth() {
  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#3b82f6] tracking-[0.25em] uppercase mb-3">Engineering</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-12">System Depth</h2>
        </motion.div>
        <div className="grid md:grid-cols-2 gap-5">
          {CARDS.map((card, i) => {
            const Icon = card.icon
            return (
              <motion.div key={card.title} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: i * 0.08 }} viewport={{ once: true, margin: '-100px' }}
                className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-6 flex flex-col gap-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-[#3b82f6]/10 border border-[#3b82f6]/20">
                      <Icon size={18} className="text-[#3b82f6]"/>
                    </div>
                    <h3 className="font-semibold text-[#e7e7ee]">{card.title}</h3>
                  </div>
                  <span className="font-mono text-xs text-[#10b981] bg-[#10b981]/10 border border-[#10b981]/20 px-2 py-0.5 rounded text-right leading-tight max-w-[120px]">{card.stat}</span>
                </div>
                <p className="text-sm text-[#9999a8] leading-relaxed">{card.desc}</p>
                <pre className="bg-[#08080c] rounded-lg p-3 font-mono text-xs text-[#9999a8] overflow-x-auto border border-[#1f1f2e]/50"><code>{card.code}</code></pre>
                <p className="font-mono text-[11px] text-[#9999a8] opacity-60">→ {card.file}</p>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
