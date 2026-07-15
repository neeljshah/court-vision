# Architecture Guide

This document describes the system's structural layout: how data flows in,
how it is transformed into calibrated predictions, and what runs in production.
Every claim is verified against the repo.

**Honest framing up front.** This is a calibrated prediction platform, not a
betting-edge product. Pregame sports markets are efficient: our model MATCHES
the devigged closing line within noise on team-strength markets. The decisive,
measured calibration win is in-game conditioning. No dollar edge, ROI, or
profit is claimed anywhere in this document or the codebase. See
`docs/JOB_EVIDENCE_PACKET.md` for the full truth source.

---

## The Core Thesis

The NBA engine took ~1,470 commits to reach production quality. The key insight
was that the hard, compounding machinery is sport-agnostic:

- Walk-forward validation with assertion-level leak guards
- Multi-corpus calibration acceptance gates
- Monte Carlo simulation parameterized by sport-specific transition matrices
- Self-improving signal discovery loop

None of that belongs to basketball. It belongs to the infrastructure layer.
The sport-specific pieces (data connectors, event taxonomy, stat definitions)
are thin adapters.

**Result: four sports share one kernel, proven by a fail-closed parity matrix.**

---

## System Diagram

```
RAW INPUTS
  Broadcast video (NBA)          ESPN / OddsAPI / BBRef box scores
  Sports-reference / Stathead     Closing-line snapshots
        |                                   |
        v                                   v
+------------------+           +--------------------------+
|  CV PIPELINE     |           |  DATA INGEST LAYER       |
|  (NBA only)      |           |  domains/<sport>/        |
|  YOLOv8n detect  |           |  ingest_manifest.py      |
|  SIFT homography |           |  (leak_class: PRE/IN/    |
|  Kalman+Hungarian|           |  POST/REF per source)    |
|  OSNet re-ID     |           +-----------+--------------+
|  EasyOCR scores  |                       |
+--------+---------+                       |
         |                                 |
         v                                 v
+--------+---------------------------------+
|           KERNEL/  (sport-blind)         |
|                                          |
|  kernel/validation/   walk-forward CV    |
|                        + truncation-inv  |
|                        leak guard        |
|                                          |
|  kernel/sim_framework/ JointDistribution |
|                        MC path runner    |
|                                          |
|  kernel/decision/      devig (Shin+3)    |
|                        shadow log        |
|                        calibration gate  |
|                                          |
|  kernel/loop/          signal discovery  |
|                        proposer + gate   |
|                                          |
|  kernel/brain/         agent orch        |
+------------------+-----------------------+
                   |
                   | consumes via SportContext
    +--------------+-----------+-----------+-----------+
    v              v           v           v           v
+--------+  +----------+  +-------+  +--------+  +-----+
|bball   |  |mlb/      |  |soccer/|  |tennis/ |  |nfl/ |
|_nba/   |  |predictor |  |pred.  |  |pred.   |  |(stub)|
|pred.py |  +----------+  +-------+  +--------+  +-----+
+---+----+
    |
    |  cohesive_read.predict()  ->  one calibrated p(win) per game
    |  live_read.predict_live() ->  in-game repricer on realized state
    |
    v
+---------------------------------------------+
|  predict_service/  (the canonical store)    |
|  scheduler.py  ->  SnapshotEnvelope/sport   |
|  store.py      ->  atomic latest.json write |
|  contracts.py  ->  schema v1.2.0 (frozen)   |
+-------+--------------------+----------------+
        |                    |
        v                    v
+---------------+    +------------------+
|  Auto-API     |    |  Boards API      |
|  :8099        |    |  :8098           |
|  predict_serv |    |  platformkit/    |
|  ice.app      |    |  frontend/serve  |
+-------+-------+    +---------+--------+
        |                      |
        v                      v
+-----------------------------------------+
|  Next.js / React dashboard  :3000       |
|  webapp/   (live predictions, CLV,      |
|  paper trail, ops health)              |
+-----------------------------------------+
```

---

## Layer-by-Layer Walkthrough

### 1. Data Ingest

Every data source is tagged with a `leak_class` in the domain's
`ingest_manifest.py` before it reaches any feature builder:

| Class | Meaning | Example |
|---|---|---|
| `LEAK_PRE_GAME` | Known before tip; safe as pregame feature | Rest days, Elo rating |
| `LEAK_IN_GAME` | Accrues during play | Current score, quarter |
| `LEAK_POST_GAME` | Only known after final whistle | Box-score totals (as targets) |
| `LEAK_REFERENCE` | Static reference | Court dimensions, surfaces |

As-of features built from post-game box scores are `LEAK_PRE_GAME` by
construction because `scripts/platformkit/asof_common` snapshots **before**
updating the current game. This is the primary leak-prevention contract.

### 2. The Sport-Blind Kernel

`kernel/` contains the validated machinery. An AST-level import guard
(`scripts/platformkit/check_import_contract.py`) enforces two rules at
static-analysis time:

1. **Kernel purity:** `kernel/` may not import `src.*`, `domains.*`,
   `api.*`, or `scripts.*`.
2. **Cross-adapter ban:** `domains/<a>/` may not import `domains/<b>/`.

These rules mean the kernel can be unit-tested without any sport adapter
loaded, and adding sport B cannot silently depend on sport A's data.

Key kernel modules:

- `kernel/validation/proof_metrics.py` -- Brier, RMSE, ECE computed
  sport-blind; used by all four sport scoreboards
- `kernel/sim_framework/` -- Monte Carlo path runner; sports provide
  transition matrices; the kernel runs the simulation paths and returns
  a `JointDistribution`
- `kernel/decision/` -- Shin (1992) de-vig (stable bisection solver),
  shadow logging, calibration tracker
- `kernel/loop/` -- signal discovery: LLM-free proposer -> cheap screen
  -> walk-forward gate -> ship/reject verdict
- `kernel/testing/conformance.py` -- `check_sport_context()` validates a
  domain's `SportContext` mechanically; returns human-readable violations

### 3. Domain Adapters

Each adapter lives at `domains/<sport>/` and exposes exactly two surfaces:

- `cohesive_read.predict(home, away, ...)` -- pregame surface; returns a
  calibrated probability envelope
- `live_read.predict_live(...)` -- in-game repricer; fuses the pregame
  prior with realized score state

The five shipped adapters:

| Domain | Path | Model |
|---|---|---|
| NBA | `domains/basketball_nba/predictor.py` | NNLS stack + possession MC sim |
| MLB | `domains/mlb/predictor.py` | pitcher-blind Elo |
| Soccer | `domains/soccer/predictor.py` | Poisson totals |
| Soccer (Intl) | `domains/soccer_intl/predictor.py` | Dixon-Coles bivariate-Poisson (1X2 + O/U-2.5), neutral-site aware |
| Tennis | `domains/tennis/predictor.py` | Elo + Platt calibration |

`domains/nfl/` is a stub (`feature_spec.py` + `ingest_manifest.py` only, no
`predictor.py` -- scaffolded but not validated). The parity matrix marks it
accordingly.

**One win-prob anchors the whole surface.** Each domain's rating model
emits a raw probability. A per-sport leak-free recalibrator (Platt /
temperature / isotonic) maps it to a single calibrated `p(win)`. The
Monte Carlo engine is then bisected so its match-win marginal equals
that anchor. Totals, spreads, and props fall out of the same MC paths
and therefore cannot disagree with the moneyline. This is what makes
the surface auditable: there is exactly one place a probability can be
wrong.

### 4. The Possession Monte Carlo Sim (NBA)

`src/sim/basketball_sim.py` is a data-driven player-level Monte Carlo:

- On-court lineups are sampled from real stint minutes
  (`data/cache/team_system/player_rates.parquet`)
- Each possession is consumed by exactly one of the five on-court players
  (the "shared scoring pie")
- Teammate scoring correlations **emerge** from the mechanics rather than
  being hand-tuned -- measured teammate rho is approximately -0.10 vs
  realized, vs. a prior naive implementation's +0.65
- Defense is parameterized by per-player interior/perimeter ratings;
  make-probability is suppressed against strong defenses via calibrated
  slope constants
- `simulate_game(home, away, n_sims=1000, seed=0)` returns a
  `GameSimResult`; `src/sim/sgp_from_sim.py` prices same-game parlays
  off the joint samples from the same simulation paths

The kernel's `kernel/sim_framework/` provides the sport-blind path runner
and `JointDistribution` type; the basketball sim implements the NBA-specific
transition mechanics on top of it.

### 5. The predict_service Store

`predict_service/` is the canonical data layer between the prediction
models and everything that reads them. It never recomputes; it only serves.

- `predict_service/scheduler.py` runs the producer loop: calls each
  sport's `cohesive_read.predict()`, assembles a `SnapshotEnvelope`, and
  writes `latest.json` atomically (tmp + replace)
- `predict_service/contracts.py` defines the frozen schema (currently
  v1.2.0): `SnapshotEnvelope` -> `PredictionRecord`s -> `EdgeRow`s
- An `EdgeRow` carries one model probability and one market probability
  and **no dollar field** -- `ev` is a probability-space quantity, never
  a stake
- A missing or torn read degrades to an `unavailable` sentinel; the API
  never fabricates a value

### 6. The API Layer (:8099 and :8098)

**Auto-API (:8099)** -- `predict_service/app.py`, a FastAPI app that
serves the canonical store read-only:

- `GET /health` -- liveness
- `GET /api/sports` -- active sports + capabilities
- `GET /api/predict/{sport}` -- full SnapshotEnvelope
- `GET /api/predict/{sport}/{game_id}` -- single game record

Additional guarded routers are mounted via `core_mounts`, `extra_mounts`,
and `ingame_mounts`; an import failure degrades that path to a 503 rather
than crashing the app.

**Legacy boards API (:8098)** -- `scripts/platformkit/frontend/serve.py`
serves the UI board data.

**The legacy FastAPI app** at `api/main.py` provides ~100 routes across
16 tag groups (analytics, backtest, betting, clv, courtvision, dashboard,
devig, health, lines, lineup, live, predictions, props, risk, simulation,
stitch) plus 4 WebSocket/SSE endpoints. This is the full research surface
and CV-era legacy; the canonical serving path is predict_service above.

### 7. The 45-Service Supervised Stack

`supervisor/manifest.py` defines a topologically-sorted process inventory.
`base_specs()` (`supervisor/stack_specs.py`) returns 45 `ProcSpec` entries,
numbered `m1_producer` through `m41_public_splits` with gaps at `m3` and
`m28` (verified: `from supervisor.stack_specs import base_specs;
len(base_specs())` == 45). The table below is a representative slice, not
the full roster:

| Process | Port | Role |
|---|---|---|
| `m1_producer` | -- | Produces calibrated envelopes per sport |
| `m1_api_paper` | 8099 | Auto-API (read-only predict store) |
| `m1_api_boards` | 8098 | Boards API for the UI |
| `m1_ui` | 3000 | Next.js dashboard |
| `m1_paper` | -- | Paper-trading loop |
| `m1_line_daemon` | -- | Closing-line snapshot capture for CLV |
| `m6_ingame_loop` | -- | In-game repricer loop |
| `m2_inplay` | -- | In-play odds capture |
| `m4_selfimprove` | -- | Self-improve ratchet |
| `m7_ingame_refresh` | -- | In-game state refresh |
| `m5_autonomy_monitor` | -- | Autonomy health monitor |
| `m8_ci_cadence` | -- | CI cadence runner |
| `m2_inplay_capture` | -- | In-play state capture |
| `m10_best_bets_compute` | -- | Best-bets computation |
| `m11_ingame_pred_tick` | -- | In-game prediction tick |
| `m12_pm_paper_tick` | -- | Paper-trading tick |
| `m13_props_pred_tick` | -- | Props prediction tick |

Readiness probes decide when a process is READY (not merely alive):
`tcp-port-open`, `http-200`, `heartbeat-file-fresh`, or `none`. Restart
policy is capped exponential backoff. The capture / in-game / self-improve
daemons are independent branches with no `depends_on` edges: a dead feed
is one red status entry, and the rest of the stack keeps running.

`boot.ps1` brings up the full local stack. Before launching the supervisor
it runs a fail-closed governance preflight (honesty linter, provenance,
concurrency, pkl integrity, leak audit, parity). The preflight is
decision-only: it never authorizes a bet and never moves money. Real-money
placement is **default-DENY** and requires a separate explicit human flip.

### 8. The Parity Matrix

`scripts/platformkit/parity_matrix.py` is a fail-closed green/red grid
over `SPORTS x {census, manifest, feature_spec}`. It runs in seconds
with no torch and no app boot.

Current state:

```
                 census     manifest   feature_spec
basketball_nba   green      green      green
mlb              green      green      green
soccer           green      green      green
soccer_intl      green      green      green
tennis           green      green      green
                 ------------------------------
PARITY: GREEN (0 red cells)
```

A dimension a sport has not built yet is `n/a` (gray) and does NOT fail
the gate. A dimension that is present-but-broken is red and DOES fail
(`parity_matrix.py:131-163`).

---

## Key Honest Numbers

The following calibration numbers are from `docs/PLATFORM.md` and
`docs/JOB_EVIDENCE_PACKET.md`. These are calibration/sharpness metrics
(lower Brier = sharper forecast). They are not edge or profit claims.

**Pregame -- beat-the-close (leak-free OOS, held-out 2nd half):**

| Sport / market | Model | Devigged close | Verdict |
|---|---|---|---|
| NBA moneyline (Brier) | 0.1735 | 0.1672 | MATCH within noise |
| MLB moneyline (Brier) | 0.2429 | 0.2390 | MATCH |
| Soccer O/U-2.5 (Brier) | 0.2465 | 0.2390 | MATCH |
| Tennis ATP ml (Brier) | 0.2177 | 0.2028 | BEHIND (market very efficient) |

**In-game conditioning (static -> conditional Brier):**

| Sport | Result | Corpus |
|---|---|---|
| NBA (end Q1/Q2/Q3) | 0.209 -> 0.159 | real-corpus; VALIDATION_PENDING on fixture |
| MLB (inning 3/5/7) | 0.241 -> 0.126 | reproduces on committed fixture |
| Soccer 1X2 (half-time) | 0.626 -> 0.502 | reproduces on committed fixture |
| Tennis (after set 1) | 0.219 -> 0.151 | reproduces on committed fixture |

The thesis: pregame MATCHES the efficient close on team-strength markets.
In-game conditioning is the decisive measured, calibrated win -- fusing
the pregame intelligence prior with the realized score state.

Retracted numbers (+18.38% pregame ROI, endQ3 Brier 0.119, +54% in-play)
are documented measurement artifacts. They appear only inside explicit
retraction context in `docs/JOB_EVIDENCE_PACKET.md` and
`docs/KNOWN_LIMITATIONS.md`. They are never current.

---

## Where to Look in the Repo

| What you want to see | Where |
|---|---|
| Sport-blind kernel | `kernel/` (loop, sim_framework, validation, decision, brain, config) |
| NBA basketball sim | `src/sim/basketball_sim.py` |
| Kernel sim framework | `kernel/sim_framework/` |
| Domain adapters (all 4 sports) | `domains/{basketball_nba,mlb,soccer,tennis}/predictor.py` |
| Adapter conformance contract | `kernel/testing/conformance.py` + `kernel/config/context.py` |
| Feature train==inference seam | `scripts/platformkit/feature_spec_core.py` |
| Leak-class tagging per source | `domains/<sport>/ingest_manifest.py` |
| Parity matrix (fail-closed) | `scripts/platformkit/parity_matrix.py` |
| Import direction guard | `scripts/platformkit/check_import_contract.py` |
| Canonical predict store | `predict_service/{contracts,store,scheduler,app}.py` |
| Auto-API (:8099) | `predict_service/app.py` |
| Boards API (:8098) | `scripts/platformkit/frontend/serve.py` |
| Legacy full FastAPI surface | `api/main.py` (100 routes, 16 tag groups) |
| Supervisor process manifest | `supervisor/manifest.py` |
| Full boot sequence | `boot.ps1` |
| Calibration / honesty numbers | `docs/JOB_EVIDENCE_PACKET.md` (truth source) |
| Beat-the-close scoreboard | `scripts/platformkit/beat_the_close_scoreboard.py` |
| In-game scoreboard | `scripts/platformkit/ingame_scoreboard.py` |
| Walk-forward backtester | `src/prediction/walk_forward_backtester.py` |
| Shin de-vig implementation | `src/prediction/devig.py` |


---
<!-- nav-footer -->
**Navigate:** [Up: guide index](00_OVERVIEW.md) - [Home](../../README.md)
