# CourtVision Platform -- Domain-Agnostic, Calibrated Multi-Sport Forecasting Engine

> **Status (2026-06-15): SHIPPED -- 4 sports live.** NBA, MLB, Soccer, and Tennis predictors are built and validated against real corpora. The product is one converged, calibrated prediction platform: a single win-prob per sport anchors a coherent pregame surface plus an in-game repricer, exposed through `domains/<sport>/predictor.py` and the unified `scripts/platformkit/predict_matchup.py` CLI. For the full product narrative read **[docs/PREDICTOR_PLATFORM.md](PREDICTOR_PLATFORM.md)**; for the honest, adversarially-audited numbers read **[docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)** (the single truth source).

---

## The Thesis

The NBA system took months and 1,470 commits to reach production quality. A naive port to a second sport would cost another several months each -- because the machinery would be rebuilt from scratch every time.

The insight is that the hard, compounding work is sport-agnostic:

- Walk-forward validation with assertion-level leak guards
- Conformal / temperature calibration acceptance gates (must beat raw on >=2 independent corpora)
- A self-improving signal-discovery loop with an honest reject/ship gate
- Monte Carlo simulation of possessions/sequences, parameterized by sport-specific transition matrices
- Devig, calibration tracking, shadow logging, OOS held-out evaluation
- The brain: an autonomous agent loop that proposes, validates, and retires signals

None of that belongs to basketball. It belongs to the infrastructure layer. The sport-specific pieces -- data connectors, event taxonomy, stat definitions, market structures -- are thin adapters that consume the infrastructure.

**Adding a sport requires writing mostly the adapter.** The validated machinery compounds across sports without being rebuilt. This thesis is now PROVEN: four sports share one kernel and one prediction surface.

---

## Architecture: `kernel/` + `domains/<sport>/`

```
+--------------------------------------------------------------------------+
|                          kernel/                                         |
|                   (sport-agnostic, reusable)                            |
|                                                                          |
|  loop/         Self-improving discovery loop                            |
|                  Proposer -> cheap screen -> walk-forward gate -> ship  |
|  sim/          Monte Carlo framework                                    |
|                  Parameterized by transition matrices; sport provides   |
|                  possession/event distributions, kernel runs the paths  |
|  validation/   Walk-forward CV, truncation-invariance tests,           |
|                  conformal/temperature calibration, multi-corpus accept |
|  decision/     Devig (Shin + others), calibration tracker, shadow log  |
|  brain/        Agent orchestration: Opus plans, Sonnet executes;       |
|                  hard ship gates at every layer                         |
|  api/          Shared endpoint scaffolding, auth, health, SSE          |
+--------------------------+-----------------------------------------------+
                           | consumes
       +-------------------+-------------------+-------------------+
       v                   v                   v                   v
+---------------+  +---------------+  +---------------+  +---------------+
| domains/      |  | domains/      |  | domains/      |  | domains/      |
| basketball_nba|  | mlb/          |  | soccer/       |  | tennis/       |
|               |  |               |  |               |  |               |
| predictor.py  |  | predictor.py  |  | predictor.py  |  | predictor.py  |
|  cohesive_read|  |  cohesive_read|  |  cohesive_read|  |  cohesive_read|
|  live_read    |  |  live_read    |  |  live_read    |  |  live_read    |
+---------------+  +---------------+  +---------------+  +---------------+
```

Each domain exposes a `predictor.py` with `cohesive_read` (pregame surface: `predict` / `to_jd`) and `live_read` (in-game repricer: `predict_live`). One win-prob per sport anchors the whole surface so the moneyline, the totals, and the in-game repricer stay mutually coherent.

### Kernel vs. Adapter Responsibility Split

| Concern | kernel/ | domains/<sport>/ |
|---|---|---|
| Walk-forward CV with leak guards | owns | -- |
| Conformal / temperature calibration, multi-corpus gate | owns | -- |
| Monte Carlo path simulation | parameterized framework | transition matrices, possession distributions |
| Signal-discovery loop | owns | feature generators |
| Devig / calibration / shadow log | owns | -- |
| Agent orchestration (planner/executor) | owns | -- |
| Pregame surface + in-game repricer interface | interface (`cohesive_read` / `live_read`) | sport implementation |
| Data ingestion | interface | connector implementation |
| Event taxonomy | interface | event definitions |
| Stat definitions (props) | interface | per-stat schema |
| Market structure (O/U lines, formats) | interface | book-specific adapter |
| CV pipeline (origin/NBA lineage) | -- | NBA-specific (broadcast video) |

---

## Current State: 4 Sports Shipped, ~25 Leak-Free Proof Modules

Four domain adapters are built and validated against real corpora -- `basketball_nba`, `mlb`, `soccer`, `tennis` -- each importing the shared machinery. The platform now ships:

- A pregame surface per sport (`cohesive_read` -> `predict` / `to_jd`)
- An in-game repricer per sport (`live_read` -> `predict_live`)
- The unified CLI `scripts/platformkit/predict_matchup.py` (`cv-matchup`)
- ~25 leak-free / OOS proof modules, including the committed-fixture scoreboards that reproduce the headline numbers in under 60 seconds on a fresh clone

The kernel is being isolated into `kernel/` so a new adapter imports it cleanly; much of the validated machinery already lives sport-blind.

### Run it

```
# Pregame + in-game for one matchup
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL --elapsed 0 --home-score 0 --away-score 0

# Reproduce the scoreboards on committed fixtures (proof in <60s, fresh clone)
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
python -m scripts.platformkit.ingame_scoreboard       --corpus tests/fixtures/proof

# Slim install
pip install -r requirements-predictor.txt    # or: pip install -e .  -> cv-matchup / cv-predict / cv-live
```

---

## What The Numbers Say (calibration / sharpness -- NEVER a $ edge)

All numbers are calibration/sharpness (lower Brier/RMSE = sharper). They are NOT a profit edge. The canonical record is **[docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**; the per-sport detail is in `vault/_Edge_Maps/`.

**Pregame -- beat-the-close (leak-free OOS, held-out 2nd half):**

| Sport / market | Ours | Devigged close | Verdict |
|---|---|---|---|
| NBA moneyline (Brier) | 0.1735 | 0.1672 | MATCH (within noise) |
| NBA total O/U (RMSE) | 19.17 | 18.11 | BEHIND (injury/lineup freshness) |
| MLB moneyline (Brier) | 0.2429 | 0.2390 | MATCH (tiny deficit = pitcher-blindness) |
| MLB total O/U (RMSE) | 4.72 | 4.44 | BEHIND (park/weather/SP freshness) |
| Soccer O/U-2.5 (Brier) | 0.2465 | 0.2390 | MATCH (pooled Platt) |
| Tennis ATP ml (Brier) | 0.2177 | 0.2028 | BEHIND (ATP closes very efficient) |

**In-game -- conditioning on realized state beats the static pregame line (all 4 WIN):**

| Sport | Static -> conditional (Brier) |
|---|---|
| NBA (end Q1/Q2/Q3) | 0.209 -> 0.159 |
| MLB (after inning 3/5/7) | 0.241 -> 0.126 |
| Soccer 1X2 (half-time) | 0.626 -> 0.502 ; O/U-2.5 0.264 -> 0.176 |
| Tennis (after set 1) | 0.219 -> 0.151 |

**The thesis:** pregame MATCHES the devigged close on team-strength markets and is BEHIND on totals/ATP ONLY by freshness data a box model cannot see. IN-GAME conditioning (a pregame intelligence prior fused with realized state) is the decisive measured, calibrated, and delivered edge -- 4/4 sports. No fabricated $ edge.

---

## Why The Machinery Compounds Across Sports

The same validation discipline that caught a leaky +18.38% ROI over-claim in NBA (retracted -- see [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)) applies identically to every sport. The walk-forward harness, the truncation-invariance tests, the calibration gates, the shadow logger -- these are sport-blind, and they are exactly what let us reproduce the four-sport scoreboards on committed fixtures.

The hard-won lessons compound too:

- **Calibration is the goal, not a fabricated edge:** "match the devigged close within noise" is the honest, achievable win
- **Single-fold lifts are artifacts:** the gate requires >=2 independent corpora
- **Accuracy != edge:** minimizing MAE pulls toward the line in any sport
- **Freshness beats retraining:** the pregame totals gap is data we cannot see, not a modeling miss
- **In-game conditioning is the real, delivered edge:** proven and calibrated on all four sports
- **Honest nulls and self-caught retractions are successes:** the rigor IS the product

Each lesson is encoded in the kernel as a hard gate or a documented invariant. A new adapter inherits all of them on day one.

---

## Roadmap

### Done -- Extract the kernel + ship four adapters
The sport-agnostic machinery is shared, and NBA/MLB/Soccer/Tennis each run as adapters on top of it with leak-free proofs.

### Now -- Deepen the per-sport data funnel
For each sport, ingest more reachable, fresher data to sharpen calibration and widen the in-game conditioning lead. Pregame markets are efficient; the gains are freshness, joint-market shape, and in-game state.

### Next -- Broaden
Additional sports each add an adapter without touching the kernel. Kernel improvements (calibration, walk-forward gating, the agent loop) benefit every sport simultaneously.

---

## Origin / NBA Computer-Vision Lineage

CourtVision began as an NBA broadcast-video computer-vision pipeline (YOLOv8 detection -> SIFT homography -> Kalman+Hungarian tracking -> OSNet re-ID -> EasyOCR -> event detection) that turns broadcast footage into court coordinates at roughly $0.10/game. That pipeline is real engineering history and remains the NBA adapter's data substrate, but it is **not** the product, and **no CV edge is claimed** -- the spatial-feature SHAP contribution to today's prediction surface is ~0. The product is the four-sport calibrated predictor described above.

---

## What This Is Not

No betting edge / ROI / profitable edge is claimed for any sport. The platform's own validation shows pregame markets are efficient: it MATCHES the devigged close on team-strength markets and is BEHIND on totals/ATP only by freshness data it cannot see. The retracted +18.38% ROI / endQ3-0.119 / +54% in-play numbers are documented measurement artifacts -- they appear ONLY in retraction context in [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) and [docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), never as current.

The value of the platform is two things: engineering compounding (shared infrastructure, shared discipline, shared agent loop across four sports) and the measured, calibrated, delivered in-game conditioning edge -- not a promised betting edge in any market.

---

*CourtVision is built by [Neel Shah](https://neelshahportfolio.netlify.app). Contact: [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)*
