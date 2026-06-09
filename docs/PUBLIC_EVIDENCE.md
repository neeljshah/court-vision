# Public Evidence — 60-Second Funnel Scan

> The fast scan of what CourtVision actually does and how well, organized by the funnel.
> Every number here is the **leak-free, audited** version. For the full adversarial audit —
> every claim's proof artifact plus the complete do-not-claim list — read
> **[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**. Narrative: [../README.md](../README.md).

**The funnel:** `DATA → SIGNALS → MODELS → ENGINES → PREDICTIONS → INTELLIGENCE`, with an agentic loop that re-validates every stage. Each stage refines the one above it.

---

## The one-paragraph version

End-to-end NBA intelligence system, intensive ~3-month solo build (1,470 commits, Mar–May 2026), human-architected over an agentic build pipeline. Broadcast video → court coordinates (CV pipeline on a consumer GPU at ~$0.10–0.13/game) → 80-artifact intelligence layer → 7 prop models + in-play snapshot heads → devig / sim / decision engines → calibrated predictions → 1,249-dossier intelligence layer + a self-improving agentic loop. **The strongest signal is the validation rigor:** the same person built the harnesses that caught and publicly retracted his own inflated headline numbers.

---

## Evidence by funnel stage

### 1 · DATA — *defensible, the moat thesis*
- Full broadcast-video → court-coordinate tracking pipeline on a single consumer RTX 4060: YOLOv8n → SIFT homography → from-scratch Kalman+Hungarian tracker → OSNet re-ID → EventDetector. ~150 structured columns/game at **~$0.10–0.13/game** vs six-/seven-figure Sportradar / Second Spectrum licensing.
- Resolves anonymous tracker slots to real NBA identities: **17,254 `cv_features` rows / 241 games / 252 distinct player IDs** (`data/nba_ai.db`). ~10 documented sentinel-leak guards in the feature layer.
- *Proof:* `src/pipeline/unified_pipeline.py`, `src/tracking/advanced_tracker.py`. Manifest: [CV_TRACKING.md](CV_TRACKING.md).

### 2 · SIGNALS — *real engineering, edge unproven*
- 80-artifact intelligence layer: 26,335-pair similarity matrix, 30 scheme tags, lineup chemistry (4,760 rows), matchup deviations, confidence curves. Underneath: a **291,625-pair** player-vs-player matchup matrix from 2,214 tracking files → a **690-node** idempotent knowledge graph.
- Self-improving discovery loop with a ship gate built to *refute*: expanding WF + null-shuffle (z≥3) + ablation + BH-FDR. Most candidates correctly rejected.
- *Honest caveat:* CV features carry SHAP ≈ 0 in production today (`cv_lift_report.json: has_cv_data: false`) — complete plumbing, credible thesis, **not yet a measured edge.**
- *Proof:* [INTELLIGENCE.md](INTELLIGENCE.md), `src/loop/gate.py`.

### 3 · MODELS — *the honest core accuracy claim*
- 7 prop heads (q10/q50/q90), leak-free walk-forward MAE on ~51K held-out player-games/stat: **PTS ~4.58, REB ~1.90, AST ~1.34, FG3M ~0.88** (small ~−0.45 under-bias). Competitive with published benchmarks. **Lead with this.**
- Win-prob 5-way NNLS stack: **0.709 acc / 0.193 Brier** (3-fold WF); NNLS zeroed XGB autonomously.
- In-play endQ3 residual heads cut MAE substantially vs pregame (~46% pooled, mostly mechanical; **~26% over a naive carry-forward baseline**, WF-validated, leak-clean).
- *Proof:* `data/models/quantile_pergame_metrics.json`, `win_prob_metrics.json`.

### 4 · ENGINES — *production toolchain*
- Possession Monte Carlo where teammate-ρ **emerges** ≈ −0.10 (no hand-tuned matrix); SGP joint pricing + calibration harness. **Structure validated; no betting edge claimed.**
- Shin (1992) devig (bisection) + multi-book scanner + cross-book arb over SSE; decision engine (gate chain + EV floor + tiers); correlation-aware fractional Kelly; append-only shadow logger (passed + blocked) + nightly settlement.
- *Proof:* `src/sim/`, `src/prediction/devig.py`, `shadow_logger.py`, `betting_portfolio.py`.

### 5 · PREDICTIONS — *the honest betting read*
- **Against real closing lines, the market is efficient.** Prop edge is roughly break-even-minus-vig (≈ −2% to −5%); **assists ~+4–5% ROI** is the one durable, book-robust edge (selection skill, not under-bias) — but **it breaks in the playoffs.** Size conservative.
- In-play backtest 78% hit / +54% ROI on 55,073 bets is an **L5-proxy ceiling**, not realized edge; real-money estimate +15–25%; first real CLV **Oct 2026**. Zero real money placed, by design.
- Served over FastAPI **~99 endpoints / 12 routers** + 18-template trading desk + Next.js frontend.

### 6 · INTELLIGENCE — *the apex*
- **1,249 per-player dossiers** (28 categories, archetype-labeled) + **30 team scheme cards**; grounded AI chat surface (facts + routing index). The agentic loop that discovers/validates/ships/retires signals — and improves every stage above.
- *Proof:* [PLAYER_INTELLIGENCE.md](PLAYER_INTELLIGENCE.md), `.claude/commands/workday-loop.md`.

---

## What was retracted (the discipline headline)

The validation harnesses were built to refute the headlines. When a famous number didn't survive, the honest version was written down and the inflated one retired:

| Retracted | Honest version |
|---|---|
| +18.38% ROI on 1,535 bets | Break-even-minus-vig vs real closes; AST ~+4–5% the one durable edge |
| endQ3 Brier 0.119 "Pinnacle-class" | Leak-free ~0.141 (Q4 feature leak, caught) |
| +54% in-play ROI | L5-proxy ceiling only; +15–25% real estimate; first CLV Oct 2026 |
| "13-month build" / "hand-typed 1,470 commits" | ~3-month build; ~91% agent-authored under direction |

Full do-not-claim list with source-code root causes: **[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**.

---

## Where to go next

| If you want… | Read |
|--------------|------|
| The honest, audited account (start here) | [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) |
| The full README with the funnel narrative | [../README.md](../README.md) |
| The 80-artifact intelligence layer | [INTELLIGENCE.md](INTELLIGENCE.md) |
| System architecture (funnel, component by component) | [../ARCHITECTURE.md](../ARCHITECTURE.md) |
| Known limitations + validation gaps | [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) |
| CV pipeline deep-dive | [CV_TRACKING.md](CV_TRACKING.md) |

*Reframed 2026-06-08 around the funnel; numbers reconciled to the leak-free audited figures in JOB_EVIDENCE_PACKET.md.*
