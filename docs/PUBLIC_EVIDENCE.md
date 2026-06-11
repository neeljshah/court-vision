# Public Evidence — 60-Second Funnel Scan

> The fast scan of what CourtVision actually does and how well, organized by the funnel.
> Every number here is the **leak-free, audited** version. For the full adversarial audit —
> every claim's proof artifact plus the complete do-not-claim list — read
> **[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**. For the ceiling analysis:
> **[CEILING.md](CEILING.md)**. For open gaps: **[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)**.

**The funnel:** `DATA → SIGNALS → MODELS → ENGINES → PREDICTIONS → INTELLIGENCE`, with an
agentic loop that re-validates every stage. Each stage refines the one above it.

---

## The one-paragraph version

End-to-end NBA intelligence system, intensive ~3-month solo build (1,470 commits, Mar–May 2026),
human-architected over an agentic build pipeline. Broadcast video → court coordinates (CV pipeline
on a consumer GPU at **~$0.10–0.13/game**) → 80-artifact intelligence layer → 7 prop models +
in-play snapshot heads → devig / sim / decision engines → calibrated predictions → 1,249-dossier
intelligence layer + a self-improving agentic loop. **430 Python modules** across the full stack.

**The strongest signal is the validation rigor:** the same person built the harnesses that caught
and publicly retracted his own inflated headline numbers. The market-efficiency finding — the model
does not beat efficient closing lines — is the cleanest output a rigorous validation framework can
produce.

---

## Evidence by funnel stage

### 1 · DATA — *defensible, the moat thesis*

- Full broadcast-video → court-coordinate tracking pipeline on a single consumer RTX 4060:
  YOLOv8n → SIFT homography → from-scratch Kalman+Hungarian tracker → OSNet re-ID → EventDetector.
  ~150 structured columns/game at **~$0.10–0.13/game** vs six-/seven-figure Sportradar/Second
  Spectrum licensing.
- Resolves anonymous tracker slots to real NBA identities: **17,254 `cv_features` rows / 241 games /
  252 distinct player IDs** (`data/nba_ai.db`). ~10 documented sentinel-leak guards in the feature layer.
- *Proof:* `src/pipeline/unified_pipeline.py`, `src/tracking/advanced_tracker.py`. Manifest:
  [CV_TRACKING.md](CV_TRACKING.md).
- *Honest caveat:* CV features carry **SHAP ≈ 0 in production today** (`cv_lift_report.json:
  has_cv_data: false`) — complete plumbing, credible thesis, **not yet a measured edge.**

### 2 · SIGNALS — *real engineering, edge at open frontiers*

- **80-artifact intelligence layer**: 291,625-pair player-vs-player matchup matrix from 2,214 raw
  tracking files → **690-node** idempotent knowledge graph (660 player + 30 team nodes) →
  1,249 per-player dossiers (28 statistical categories, archetype-labeled, scheme-tagged).
- Self-improving discovery loop with a ship gate built to *refute*: expanding WF + null-shuffle
  (z ≥ 3) + ablation + BH-FDR. LLM-free signal proposer (`src/loop/discovery.py`) makes discovery
  inexhaustible. Most candidates correctly rejected on point features; real frontier =
  joint/in-game/freshness.
- *Proof:* [INTELLIGENCE.md](INTELLIGENCE.md), `src/loop/gate.py`, `src/loop/discovery.py`.

### 3 · MODELS — *the honest core accuracy claim*

- 7 prop heads (q10/q50/q90), leak-free walk-forward MAE on **~51K held-out player-games/stat**:
  **PTS ~4.58 / REB ~1.90 / AST ~1.34 / FG3M ~0.88** (small ~−0.45 PTS under-bias).
  Competitive with published benchmarks. **Lead with this.**
- Win-prob 5-way NNLS stack: **0.709 acc / 0.193 Brier** (3-fold WF).
- In-play endQ3 residual heads cut MAE ~46% vs pregame (mostly mechanical; **~26% over a naive
  carry-forward baseline**, WF-validated, leak-clean).
- *Proof:* `data/models/quantile_pergame_metrics.json`, `win_prob_metrics.json`.

### 4 · ENGINES — *production toolchain*

- Possession Monte Carlo where teammate-ρ **emerges** ≈ −0.10 (no hand-tuned matrix); SGP joint
  pricing + calibration harness. **Structure validated; no betting edge claimed.**
- Shin (1992) devig (bisection) + multi-book scanner + cross-book arb over SSE; correlation-aware
  fractional Kelly; append-only shadow logger (passed + blocked) + nightly settlement.
- 372-market intelligence stack (every stat/combo/DD/TD/longshot) with in-game re-pricing via
  `--state`; CV_MIN_VAR validated (rank-remap fixes median-shift; seed-stable; cross-season).
- *Proof:* `src/sim/`, `src/prediction/devig.py`, `shadow_logger.py`, `betting_portfolio.py`,
  `scripts/team_system/market_intelligence.py`.

### 5 · PREDICTIONS — *the honest betting read*

- **Against real closing lines, the market is efficient.** Full-season WF backtest (truncation-
  invariance proven): model Brier 0.208 vs close 0.198; spread/total CLV ≈ 0; corr-with-outcome
  = 0.001. PBP Finals replay: win-prob Brier 0.34–0.40 in-series (worse than coin flip).
- Prop edge is roughly break-even-minus-vig (~-2% to -5%). **Assists ~+4–5% ROI** is the one
  durable, book-robust edge (selection skill, not under-bias; positive in both over/under
  directions) — but **it breaks in the playoffs.**
- In-play backtest 78% hit / +54% ROI on 55,073 bets is an **L5-proxy ceiling**, not realized
  edge. Real-money estimate +15–25%. First real CLV **Oct 2026**. **Zero real money placed, by design.**
- Served over FastAPI **~99 endpoints / 12 routers** + 18-template trading desk + Next.js frontend.

### 6 · INTELLIGENCE — *the apex*

- **1,249 per-player dossiers** (28 categories, archetype-labeled) + **30 team scheme cards**;
  grounded AI chat surface (facts + routing index). The agentic loop that discovers/validates/
  ships/retires signals — and improves every stage above.
- LLM scheme-prior layer (`CV_LLM_SCHEME`, default-OFF): LLM emits bounded leak-flagged
  multipliers on existing sim knobs; sim computes every number. Ships **scouting-only** (signal
  redundant with the sim: corr-with-residual +0.005 p=0.87).
- *Proof:* [PLAYER_INTELLIGENCE.md](PLAYER_INTELLIGENCE.md), `src/sim/scheme_prior.py`,
  `.claude/commands/workday-loop.md`.

---

## What was retracted (the discipline headline)

The validation harnesses were built to refute the headlines. When a famous number didn't survive,
the honest version was written down and the inflated one retired:

| Retracted | Root cause | Honest version |
|---|---|---|
| +18.38% ROI on 1,535 bets | Market-follow grading artifact (model never read; flat -110 fiction; in-sample filters) | Break-even-minus-vig vs real closes; AST ~+4–5% the one durable edge |
| endQ3 Brier 0.119 "Pinnacle-class" | Q4 feature leak (`halftime_pace_shift`, `trailing_team_q4_usg_hhi`); source file reads 0.1354, not 0.1191 | Leak-free ~0.141 (caught own pipeline Q4 leak) |
| +54% in-play ROI | L5-proxy ceiling only; real estimate +15–25% | First CLV Oct 2026 |
| "Season edge proven" | Full-season WF: CLV ≈ 0; model explains 0.13%/0.29% of line move | Market is efficient; AST is only measured edge |
| "13-month build" / "hand-typed 1,470 commits" | Git history spans ~3 months; ~91% commits agent-authored under direction | ~3-month build; solo human architect/director of an agentic pipeline |

Full do-not-claim list with source-code root causes: **[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**.

---

## Where to go next

| If you want... | Read |
|--------------|------|
| The honest, audited account (start here) | [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) |
| The full README with the funnel narrative | [../README.md](../README.md) |
| The 80-artifact intelligence layer | [INTELLIGENCE.md](INTELLIGENCE.md) |
| System architecture (funnel, component by component) | [../ARCHITECTURE.md](../ARCHITECTURE.md) |
| Known limitations + validation gaps | [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) |
| The data/feature ceiling analysis | [CEILING.md](CEILING.md) |
| CV pipeline deep-dive | [CV_TRACKING.md](CV_TRACKING.md) |

*Last verified: 2026-06-11. Numbers reconciled to the leak-free audited figures in JOB_EVIDENCE_PACKET.md.*
