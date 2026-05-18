'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'

interface Node {
  id: string
  label: string
  sublabel: string
  tier: 'standard' | 'moat'
  tooltip: string
  detail: string
  file?: string
}

const NODES: Node[] = [
  { id: 'video', label: 'Broadcast Video', sublabel: '60fps H.264', tier: 'standard',
    tooltip: 'Full-game broadcast feeds at 60fps. H.264 only; AV1 quarantined due to decoder constraints.',
    detail: 'Input is a full-game broadcast video file (1080p60, H.264). Decoded via decord NVDEC for GPU-accelerated frame extraction, falling back to PyAV on CPU. Each game is ~7GB; 29 usable games (9 CLEAN + 20 PARTIAL of 75 attempted) currently in the CV registry, targeting 80 CLEAN.',
    file: 'scripts/ingest_fetch.py' },
  { id: 'yolo', label: 'YOLOv8n', sublabel: 'Player + Ball', tier: 'standard',
    tooltip: 'Custom-trained YOLOv8n detecting 10 players + ball per frame at ~20fps/worker.',
    detail: 'YOLOv8n fine-tuned on NBA broadcast frames. Detects bounding boxes for all 10 on-court players and the ball. Runs on RTX GPU; ~20 fps per worker with 4 parallel workers on a single 3090.',
    file: 'src/tracking/player_detection.py' },
  { id: 'sift', label: 'SIFT Homography', sublabel: 'Pixel → Court ft', tier: 'standard',
    tooltip: 'SIFT feature matching maps broadcast pixel coordinates to court feet (0-94 × 0-50).',
    detail: 'SIFT keypoints on court markings (3pt arc, paint, center circle) matched to a template court. Homography estimated via RANSAC. Broadcast panorama ratio fix prevents degenerate homographies; 5-second window fallback for occlusion.',
    file: 'src/pipeline/unified_pipeline.py' },
  { id: 'kalman', label: 'Kalman + Hungarian', sublabel: 'Multi-Object Track', tier: 'standard',
    tooltip: 'Kalman filter state prediction + Hungarian algorithm for optimal detection-track assignment.',
    detail: 'Each player track maintains a Kalman state (x, y, vx, vy). New detections assigned to existing tracks via Hungarian algorithm minimizing IoU cost. Handles occlusion with a 30-frame track memory before ID is retired.',
    file: 'src/tracking/advanced_tracker.py' },
  { id: 'osnet', label: 'OSNet Re-ID', sublabel: '512-dim embeddings', tier: 'standard',
    tooltip: 'OSNet extracts 512-dim appearance embeddings for persistent player identity across frames.',
    detail: 'OSNet re-ID network generates a 512-dimensional embedding per player crop. Cosine similarity to a gallery of known player embeddings resolves ID collisions after occlusion. EasyOCR jersey number provides disambiguation fallback.',
    file: 'src/tracking/osnet_reid.py' },
  { id: 'ocr', label: 'EasyOCR', sublabel: 'Jersey Numbers', tier: 'standard',
    tooltip: 'EasyOCR reads jersey numbers from player crops for re-ID disambiguation.',
    detail: 'EasyOCR runs on player bounding box crops when OSNet cosine similarity is below the confidence threshold. Jersey number resolves the assignment. Handles motion blur via multi-scale processing.',
    file: 'src/tracking/player_detection.py' },
  { id: 'event', label: 'EventDetector', sublabel: 'Shots · Passes · Screens', tier: 'standard',
    tooltip: 'Rule-based + learned detector for game events from tracking trajectories.',
    detail: 'Consumes per-frame tracking data to detect shots (ball trajectory parabola), passes (velocity spike between players), screens (stationary player proximity), and drives (speed threshold crossing into paint). Feeds event_id keyed feature store.',
    file: 'src/pipeline/unified_pipeline.py' },
  { id: 'cvfeatures', label: 'CV Feature Store', sublabel: 'THE MOAT', tier: 'moat',
    tooltip: 'defender_distance, spacing_score, legs_fatigue — spatial signals not in any public dataset.',
    detail: 'Three features produced by the CV pipeline that have no public equivalent: defender_distance (meters to nearest defender at shot release, post-homography), spacing_score (convex hull area of 4 off-ball offensive players), legs_fatigue (cumulative running distance, 6-min exponential decay). Combined SHAP: 31% of pts model mass. ΔR²: +0.08 over API baseline.',
    file: 'src/features/feature_engineering.py' },
  { id: 'nbaapi', label: 'NBA API Merger', sublabel: 'Game logs · PBP · Lineups', tier: 'moat',
    tooltip: 'NBA API data (game logs, shot dashboard, PBP, lineup on/off) merged with CV features on event_id × player_id.',
    detail: 'nba_api pulls game logs, shot charts, play-by-play, and lineup on/off data. Joined to CV tracking on game_id × event_id × player_id. Ingestion timestamps preserved — feature store keyed to tip-off time for no-leakage walk-forward replay.',
    file: 'src/data/nba_stats.py' },
  { id: 'models', label: '75-Model Stack', sublabel: 'XGB · Ridge · LGB', tier: 'moat',
    tooltip: '75 .pkl/.json models across 5 tiers. 7 prop models (pts/reb/ast/fg3m/blk/tov/stl), win prob, game total, DNP predictor.',
    detail: 'Tier 1 (API): XGBoost + Ridge stacker for 7 player props + win_prob + game_total. Tier 2 (shot data): xFG v1, zone tendency. Tier 3 (CV ≥20g): xFG v2 w/ defender_distance. Tier 4 (CV ≥50g): fatigue curve, rebound positioning. Tier 5 (NLP): DNP predictor AUC=0.979. Walk-forward, 48h purge.',
    file: 'src/prediction/player_props.py' },
  { id: 'mc', label: 'Monte Carlo', sublabel: '10K paths', tier: 'moat',
    tooltip: '10,000 correlated simulation paths with tempo, foul trouble, garbage time, and Q4 usage wired.',
    detail: '10,000 possession-level simulation paths per game. Correlates pts/reb/ast residuals via Ledoit-Wolf shrunk covariance. FoulTrouble, GarbageTime, and Q4Usage modules adjust minute projections. Output: full joint distribution over player stat lines.',
    file: 'src/prediction/win_probability.py' },
  { id: 'kelly', label: 'Kelly + CLV', sublabel: 'Fractional 0.25×', tier: 'moat',
    tooltip: 'Fractional Kelly sizing (0.25–0.5×) with Ledoit-Wolf 7×7 correlation shrinkage and Shin devig vs Pinnacle close.',
    detail: 'Full Kelly optimizes E[log W] but ruins on edge misestimation. System uses k∈[0.25,0.5]×f* calibrated to market maturity. 7×7 prop correlation matrix estimated with Ledoit-Wolf shrinkage, reducing correlated-leg overstaking by 20–40%. CLV measured vs Pinnacle Shin-devigged close: +14 bps/bet, t=2.3, n=312.',
    file: 'src/prediction/betting_portfolio.py' },
]

function Arrow({ isMobile }: { isMobile: boolean }) {
  return isMobile ? (
    <div className="flex justify-center my-1">
      <svg width="16" height="20" viewBox="0 0 16 20">
        <defs>
          <linearGradient id="ag-v" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4"/>
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.8"/>
          </linearGradient>
        </defs>
        <path d="M8 0 L8 14 M4 10 L8 16 L12 10" stroke="url(#ag-v)" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  ) : (
    <div className="flex items-center">
      <svg width="32" height="16" viewBox="0 0 32 16">
        <defs>
          <linearGradient id="ag-h" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4"/>
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.9"/>
          </linearGradient>
        </defs>
        <path d="M0 8 L22 8 M18 4 L24 8 L18 12" stroke="url(#ag-h)" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  )
}

export default function Architecture() {
  const [activeNode, setActiveNode] = useState<Node | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)

  return (
    <section id="architecture" className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}>
          <p className="font-mono text-xs text-[#3b82f6] tracking-[0.25em] uppercase mb-3">System Architecture</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-3">Pipeline Overview</h2>
          <p className="text-[#9999a8] mb-12 max-w-xl">Click any node for implementation details. Orange nodes are the spatial moat — not replicable from public data.</p>
        </motion.div>

        {/* Desktop: horizontal flow */}
        <div className="hidden lg:flex items-center flex-wrap gap-y-3">
          {NODES.map((node, i) => (
            <div key={node.id} className="flex items-center">
              <motion.div
                initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: i * 0.05 }} viewport={{ once: true, margin: '-100px' }}
                className="relative"
                onMouseEnter={() => setHovered(node.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => setActiveNode(node)}
              >
                <div className={`cursor-pointer rounded-lg border px-3 py-2 transition-all duration-200 min-w-[100px] text-center ${
                  node.tier === 'moat'
                    ? 'border-[#f97316] bg-[#13131c] hover:border-orange-400 hover:shadow-[0_0_16px_rgba(249,115,22,0.2)] hover:scale-105'
                    : 'border-[#1f1f2e] bg-[#13131c] hover:border-[#3b82f6] hover:shadow-[0_0_16px_rgba(59,130,246,0.15)] hover:scale-105'
                }`}>
                  <div className={`text-xs font-semibold leading-tight ${node.tier === 'moat' ? 'text-[#f97316]' : 'text-[#e7e7ee]'}`}>{node.label}</div>
                  <div className="text-[10px] text-[#9999a8] mt-0.5">{node.sublabel}</div>
                </div>
                {/* Tooltip */}
                {hovered === node.id && (
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 bg-[#13131c] border border-[#1f1f2e] rounded-lg p-3 text-xs text-[#9999a8] z-20 shadow-xl pointer-events-none">
                    {node.tooltip}
                  </div>
                )}
              </motion.div>
              {i < NODES.length - 1 && <Arrow isMobile={false} />}
            </div>
          ))}
        </div>

        {/* Mobile: vertical flow */}
        <div className="lg:hidden flex flex-col items-center">
          {NODES.map((node, i) => (
            <div key={node.id} className="flex flex-col items-center w-full max-w-xs">
              <motion.div
                initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: i * 0.04 }} viewport={{ once: true, margin: '-100px' }}
                onClick={() => setActiveNode(node)}
                className={`cursor-pointer w-full rounded-lg border px-4 py-3 text-center transition-all duration-200 ${
                  node.tier === 'moat'
                    ? 'border-[#f97316] bg-[#13131c]'
                    : 'border-[#1f1f2e] bg-[#13131c]'
                }`}
              >
                <div className={`text-sm font-semibold ${node.tier === 'moat' ? 'text-[#f97316]' : 'text-[#e7e7ee]'}`}>{node.label}</div>
                <div className="text-xs text-[#9999a8] mt-0.5">{node.sublabel}</div>
              </motion.div>
              {i < NODES.length - 1 && <Arrow isMobile={true} />}
            </div>
          ))}
        </div>

        <div className="flex gap-6 mt-8">
          <div className="flex items-center gap-2 text-xs text-[#9999a8]"><span className="w-3 h-3 rounded border border-[#1f1f2e] bg-[#13131c] inline-block" />Standard pipeline</div>
          <div className="flex items-center gap-2 text-xs text-[#9999a8]"><span className="w-3 h-3 rounded border border-[#f97316] bg-[#13131c] inline-block" />Spatial moat (CV-derived)</div>
        </div>
      </div>

      {/* Modal */}
      <AnimatePresence>
        {activeNode && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-6"
            onClick={() => setActiveNode(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className="bg-[#13131c] border border-[#1f1f2e] rounded-xl p-6 max-w-lg w-full shadow-2xl"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex justify-between items-start mb-4">
                <div>
                  <p className={`font-mono text-xs tracking-widest uppercase mb-1 ${activeNode.tier === 'moat' ? 'text-[#f97316]' : 'text-[#3b82f6]'}`}>
                    {activeNode.tier === 'moat' ? 'Spatial Moat' : 'Pipeline Stage'}
                  </p>
                  <h3 className="text-xl font-bold text-[#e7e7ee]">{activeNode.label}</h3>
                  <p className="text-sm text-[#9999a8]">{activeNode.sublabel}</p>
                </div>
                <button onClick={() => setActiveNode(null)} className="text-[#9999a8] hover:text-[#e7e7ee] transition-colors p-1">
                  <X size={20} />
                </button>
              </div>
              <p className="text-sm text-[#9999a8] leading-relaxed mb-4">{activeNode.detail}</p>
              {activeNode.file && (
                <div className="bg-[#08080c] rounded p-2 border border-[#1f1f2e]">
                  <span className="font-mono text-xs text-[#3b82f6]">{activeNode.file}</span>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
