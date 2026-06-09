# AGENTS.md — orientation for AI coding agents

This file is the convention-name landing pad for Cursor, Aider, Codex CLI, OpenCode, and other AI dev tools that don't read `CLAUDE.md`. Everything below is the same orientation a Claude reader would get from [CLAUDE.md](CLAUDE.md); the deeper task→file routing tables live there.

---

## What this repo is

**CourtVision** — end-to-end NBA prediction + betting platform built solo by [Neel Shah](https://neelshahportfolio.netlify.app) over 13 months.

Stack: YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID 512-dim → EasyOCR → EventDetector → FastAPI (~49 endpoints across 7 routers) → 9 production daemons. Computer vision on broadcast video produces court-coordinate behavioral features (defender_distance, spacing, fatigue, paint dwell) that feed an 80-artifact intelligence layer, which feeds 7 prop models + a 3-snapshot in-play win-prob stack, which feeds Shin-devigged EV calculation + segment-filtered fractional Kelly sizing + multi-book scanning + arbitrage detection.

---

## Read these three first, nothing else

1. **[docs/PUBLIC_EVIDENCE.md](docs/PUBLIC_EVIDENCE.md)** — 60-second scan with headline numbers + verification commands. Canonical truth source.
2. **[README.md](README.md)** — dense long-form: architecture, methodology, walk-forward tables, reproducibility.
3. **[docs/INTELLIGENCE.md](docs/INTELLIGENCE.md)** — manifest of the 80 derived artifacts between CV tracking and the prediction models.

**Skip on first pass:** `ROADMAP.md`, `MASTER_PLAN.md`, `docs/architecture/*`, `src/prediction/*.py` walks. 120 modules under `src/prediction/` are research surface; only ~12 are runtime — the load-bearing list is in [README.md § Load-bearing modules](README.md).

---

## TL;DR numbers (HONEST / leak-free — inflated headlines retracted, see [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md))

The funnel: **DATA → SIGNALS → MODELS → ENGINES → PREDICTIONS → INTELLIGENCE**, with an agentic loop that re-validates every stage.

- **Defensible core:** leak-free prop MAE **PTS ~4.58 / REB ~1.90 / AST ~1.34 / FG3M ~0.88** (~51K held-out/stat); win-prob **0.709 acc / 0.193 Brier**; CV pipeline broadcast→court at **~$0.10–0.13/game**.
- **Betting vs real closes:** the **market is efficient** — break-even-minus-vig overall; **AST ~+4–5%** is the one durable edge (breaks in playoffs). *Re-grade:* `python scripts/run_gate1_full_analysis.py` → −2.00%.
- **In-play:** endQ3 MAE lift ~46% pooled (~26% over naive carry-forward, WF, leak-clean); endQ3 Brier **~0.141** leak-free.
- **In-play backtest 78% / +54%** is an **L5-proxy ceiling**, not realized edge; real est. +15–25%; first real CLV Oct 2026; zero real money placed.

**Never re-print as current wins:** +18.38% ROI (market-follow grading artifact), endQ3 0.119 (Q4 leak), +54%-as-edge, CLV +8.94pp. They appear only as artifacts the harness caught.

```bash
python scripts/run_gate1_full_analysis.py   # honest re-grade: ~ -2.00% (market efficient)
# committed source-of-truth JSON: data/models/quantile_pergame_metrics.json, win_prob_metrics.json
```

---

## Repo conventions (if you're going to edit code)

- **Python 3.9 · conda env `basketball_ai` · CUDA 11.8 · RTX 4060 8GB local**
- Max 300 LOC/file · type hints · docstrings on public API only
- Models → `data/models/` (most are gitignored; whitelist is in `.gitignore`)
- Logs / vault → `vault/` (gitignored)
- Headless video only (`--no-show`); never `cv2.imshow`
- Tests: `python -m pytest tests/ -q` (4,100+ collected)
- **Critical invariant:** `_VRAM_FLUSH_INTERVAL` in `src/pipeline/unified_pipeline.py` MUST be 3000, not 100. (Past regressions have set it to 100 and OOM'd the GPU.)
- Never run: `run.py`, `loop_processor.py` (legacy entry points)

Task → primary file routing lives in [CLAUDE.md § Task → Files](CLAUDE.md). If you're a tool that reads this file but not CLAUDE.md, also load that table when picking files to edit.

---

## Honest gaps (don't hide these)

- The +54% in-play backtest is paper (L5 line proxy). Real-money expectation is **+15–25%**.
- CV scale-up is **7/80** full-feature games. Blocked behind `defender_distance=200.0` sentinel → NULL fix (ISSUE-022).
- DraftKings / Caesars / MGM scrapers are IP-blocked. Pinnacle / Bovada / FanDuel / PrizePicks cover the rest.
- `sim_win_prob` polarity bug is documented openly in `vault/Models/Polarity Bug Audit 2026-05-27.md` (unpatched; gated behind v1-LGB retrain cascade; estimated CLV impact +1.5pp to +3.5pp when patched).

Full gap inventory at [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).
