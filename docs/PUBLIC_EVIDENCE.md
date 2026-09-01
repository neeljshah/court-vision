# Public Evidence — 60-Second Funnel Scan

> **See it first, then read this.** The flagship product is **CourtVision Analytics — the Reading
> Room**, live at
> **[neeljshah.github.io/court-vision/analytics](https://neeljshah.github.io/court-vision/analytics)**:
> 74 analytics modules and 1,549 entity atlas cards, 6 prior-art-gated novel stats (one published
> as an honest null), Scout AI in three honest tiers, and a self-grading claim ledger — every
> number on the page carrying the artifact path it was read from. The dense quant terminal is
> product 2, at **[neeljshah.github.io/court-vision](https://neeljshah.github.io/court-vision)**.
>
> This document is the fast scan of what the engine underneath actually does and how well,
> organized by the funnel. Every number here is the **leak-free, audited** version. For the full
> adversarial audit — every claim's proof artifact plus the complete do-not-claim list — read
> **[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**. For the ceiling analysis:
> **[CEILING.md](CEILING.md)**. For open gaps: **[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)**.

**The funnel:** `DATA → SIGNALS → MODELS → ENGINES → PREDICTIONS → INTELLIGENCE`, with an
agentic loop that re-validates every stage. Each stage refines the one above it.

---

## September 1 evidence update

- The multi-sport tracking audit is fail-closed: the frozen sweep accepted no
  retained game as coordinate-quality evidence, while declared image-pixel rows
  remain training-only. The audit also records its denominator limitation, a
  falsified soccer camera-ceiling hypothesis, a scoped baseball retraction, and
  the football graphics confounder. See the
  [session evidence index](evidence/SESSION_2026-09-01_INDEX.md) and
  [tracking status](TRACKING.md).
- Evaluation receipts now include redacted predictor inputs, an identity floor,
  fail-closed comparison, a versioned baseline, null calibration, multiplicity
  correction, and a frozen-odds ledger. These are safeguards, not performance
  claims.
- Paper execution records maker-only wiring, venue-clock latency, market-data
  capture, and insufficient or rejected mechanism arms. No live-money or
  betting-edge claim follows from these receipts.

---

## The one-paragraph version

End-to-end NBA intelligence system, intensive solo build (3,206 commits, Mar–Jul 2026),
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

- 7 prop heads (q10/q50/q90), leak-free MAE on a **20,354-row production-model
  chronological holdout** (last 20% by date, production inference path; re-measured
  2026-07-20 by `scripts/verify_production_mae.py`, which fail-closes on >0.02 drift):
  **PTS ~4.83 / REB ~1.92 / AST ~1.39 / FG3M ~0.89**.
  Competitive with published benchmarks. **Lead with this.**
- Win-prob 5-way NNLS stack: **0.709 acc / 0.193 Brier** (3-fold WF).
- In-play endQ3 residual heads cut MAE ~46% vs pregame (mostly mechanical; **~26% over a naive
  carry-forward baseline**, WF-validated, leak-clean).
- **The one measured calibration win: in-game conditioning** -- conditioning on realized
  mid-game state sharpens win-prob calibration **Brier 0.209 -> 0.159 (NBA), 0.241 -> 0.126
  (MLB)**, real-corpus OOS, `edge_claimed=False` (a live book sees the score too). Decomposed
  honestly: a rating-blind score-only baseline already reaches 0.172 (NBA) / 0.128 (MLB);
  the model's own pregame prior adds the last ~0.014 (NBA) / ~0.001 (MLB).
  Full three-arm receipts: [INGAME_PROOF.md](INGAME_PROOF.md) section 2a.
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
- Prop backtests match the market within noise; **no durable positive edge survives cross-corpus.**
  Every candidate signal was rejected on ≥2 independent corpora, and positive full-sample lifts
  sign-flip out-of-sample — the overfit signature, caught by the gate. Calibration/sharpness, not a
  $ edge.
- The old in-play backtest headline was an **L5-proxy model-quality ceiling, retracted as a
  tradeable figure** (see the retraction table below and
  [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)). Real closing-line CLV can't be measured yet
  (first reading **Oct 2026**); the methodology to measure it is built. **Zero real money placed, by design.**
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

### Beyond the funnel · AUTONOMY + ORACLE — *the loop now runs itself, and answers questions honestly*

- **Two previously-missing autonomy stages are now live**: forward **self-shadowing**
  settles the loop's own provisional verdicts against real outcomes as they land, and
  zero-LLM **self-proposal** generates + gates new hypotheses on a schedule — no human
  trigger, no model call. A **sentinel layer** (disk pressure, exception bursts, stalled
  heartbeats, tamper-evidence hashes) and a **one-command system-liveness harness**
  compose every gate/ledger into one readout that refuses to report green over a down
  section — verified this week to correctly return `OVERALL: RED` with the specific
  failing subsystem named.
- **A 4-sport answer-engine oracle**, built from claims already on the books: a "what
  affects what" **effect graph** (555 nodes / 296 edges, NBA+MLB+soccer+tennis) computed
  entirely by labeling and linking existing ledger rows — zero new statistics — plus a
  resolver registry that REFUSES any unregistered question type instead of improvising.
  The knowledge engine feeding it is now fully drained: **197 mechanism hypotheses closed
  across all 4 sports** (89 CONFIRMED_LOCAL, 74 honest NULLs, 34 not-testable/other) —
  the large NULL share is the expected shape of a real audit, and every mechanism answer
  carries its own verdict, sample size, p-value, and source file. No folklore, no
  plausible-sounding guesses.
- *Proof:* `scripts/platformkit/autoloop/{shadow_settle_job,propose_gate_job}.py`,
  `scripts/platformkit/ops_sentinel/`, `scripts/platformkit/proof_harness/system_proof.py`,
  `scripts/platformkit/answers/{effect_graph,resolver_registry,contract_client}.py`.
  Walkthrough: [PRODUCT_DEMO.md](PRODUCT_DEMO.md).

---

## What was retracted (the discipline headline)

The validation harnesses were built to refute the headlines. When a famous number didn't survive,
the honest version was written down and the inflated one retired:

| Retracted | Root cause | Honest version |
|---|---|---|
| +18.38% ROI on 1,535 bets | Market-follow grading artifact (model never read; flat -110 fiction; in-sample filters) | Break-even-minus-vig vs real closes; market efficient, no durable $ edge claimed |
| endQ3 Brier 0.119 "Pinnacle-class" | Q4 feature leak (`halftime_pace_shift`, `trailing_team_q4_usg_hhi`); source file reads 0.1354, not 0.1191 | Leak-free ~0.141 (caught own pipeline Q4 leak) |
| +54% in-play ROI | L5-proxy model-quality ceiling, not a tradeable/realized result | No $ figure quoted; first real CLV Oct 2026 |
| "Season edge proven" | Full-season WF: CLV ≈ 0; model explains 0.13%/0.29% of line move | Market is efficient; well-calibrated but does not beat the close |
| "13-month build" / "hand-typed 3,206 commits" | Git history spans ~3 months; ~91% commits agent-authored under direction | ~3-month build; solo human architect/director of an agentic pipeline |

Full do-not-claim list with source-code root causes: **[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**.

---

## Where to go next

| If you want... | Read |
|--------------|------|
| The honest, audited account (start here) | [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) |
| The full README with the funnel narrative | [../README.md](../README.md) |
| The 15-minute demo path (system health, live prediction, oracle receipt, board, ledgers) | [PRODUCT_DEMO.md](PRODUCT_DEMO.md) |
| The 80-artifact intelligence layer | [INTELLIGENCE.md](INTELLIGENCE.md) |
| System architecture (funnel, component by component) | [../ARCHITECTURE.md](../ARCHITECTURE.md) |
| Known limitations + validation gaps | [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) |
| The data/feature ceiling analysis | [CEILING.md](CEILING.md) |
| CV pipeline deep-dive | [CV_TRACKING.md](CV_TRACKING.md) |

*Last verified: 2026-06-11. Numbers reconciled to the leak-free audited figures in JOB_EVIDENCE_PACKET.md.*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
