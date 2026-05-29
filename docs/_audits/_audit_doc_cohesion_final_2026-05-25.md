# Doc Cohesion Audit — Final Pass (2026-05-25)

Pre-Swish-Analytics audit. Scope: cold-reader experience for github.com/neeljshah/court-vision tomorrow morning.

Working tree: `master` @ `ae0cbb76` (execute_loop R10 just landed). Prior agents (5 commits this session: `623462d5`, `304b4e4f`, `7b43dff1`, `82f96367`, `9c93af8a`) had already aligned README, CLAUDE.md, CLAUDE-state.md, PROJECT_INDEX.md, ARCHITECTURE.md, ROADMAP.md, START_HERE.md, CHANGELOG.md, CONTRIBUTING.md, MASTER_PLAN.md, PREDICTIONS_QUICKSTART.md, ML_MODELS.md, CEILING.md, PRODUCTION_RUNBOOK.md.

---

## Section 1: Cold-Reader Walkthrough Findings

### Reachable from README and resolves on GitHub

Verified by `git ls-files` (not by reading): every link below is committed and will render on github.com.

| README link | Verified |
|---|---|
| `VISION.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `MASTER_PLAN.md`, `CHANGELOG.md`, `CONTRIBUTING.md` | tracked |
| `CLAUDE.md`, `PREDICTIONS_QUICKSTART.md` | tracked |
| `docs/CLAUDE-state.md`, `docs/SWISH_DEMO.md` | tracked (added before `.gitignore` rule on line 163) |
| `docs/PROJECT_INDEX.md`, `docs/START_HERE.md` | tracked |
| `docs/architecture/{system-overview,cv-pipeline,possession-simulator,execution-engine,dashboard-spec}.md` | tracked |
| `docs/research/{edge-taxonomy,competitive-landscape,market-microstructure,precedent-analysis,data-sources,validation-methodology}.md` | tracked |
| `docs/strategy/{timing-layer,account-longevity,learning-loop}.md` | tracked |
| `docs/models/{MODEL_UNIVERSE,model-registry}.md` | tracked |
| `data/models/{win_prob_metrics,quantile_pergame_metrics,prop_pergame_walk_forward,betting_backtest,betting_backtest_smart_line,quantile_calibration}.json` | tracked (explicit whitelists in `.gitignore`) |
| `src/prediction/{prop_backtester,devig,betting_portfolio,risk_guards,live_engine,live_quantile_bands}.py` | tracked |
| `tests/test_{devig,risk_guards}.py` | tracked |
| `results/README.md` | tracked |
| 25 scripts referenced (predict_player, predict_slate, daily_run, swish_demo, etc.) | all tracked |

### Broken on GitHub (gitignored — cold reader hits 404)

These were referenced from canonical docs but won't resolve for a cold visitor. Fixed in this pass:

| Reference site | What it linked to | Fix applied |
|---|---|---|
| `VISION.md:158` | `vault/Research/Renaissance Methodology.md` (gitignored) | Replaced with text note that the file lives only in the maintainer's local working copy |
| `ROADMAP.md:131-133` | `.planning/ROADMAP.md`, `vault/Plans/Gate 1 Validation.md`, `vault/Plans/Agentic Research System.md` (all gitignored) | Replaced with explanatory text notes |
| `docs/PROJECT_INDEX.md:78` | `[.planning/ROADMAP.md](../.planning/ROADMAP.md)` clickable link (gitignored) | Replaced with backticked path + explanatory note |

Verified gitignored set: `.planning/`, `vault/`, `data/models/*.pkl`, `*.pt`/`*.pth`/`*.onnx`, `data/tracking/`, `data/videos/`, `data/nba/`, `data/ingest/queue.db`. None of these are linked from README directly; canonical docs are now cold-reader-safe.

---

## Section 2: Cross-Doc Consistency Check

Reviewed the canonical hierarchy in order: README → CLAUDE → CLAUDE-state → PROJECT_INDEX → VISION → ARCHITECTURE → ROADMAP → MASTER_PLAN → CHANGELOG.

### Numbers that disagreed before this pass

#### 1. Endpoint count

| File:line | Claim | Action |
|---|---|---|
| `CLAUDE.md:43` | "FastAPI (9 endpoints, 5 routers)" | **fixed** → "~49 endpoints across 7 routers" |
| `ARCHITECTURE.md:93` | "6 endpoints + 5 routers" | **fixed** → "~49 endpoints across 7 routers" |
| `ARCHITECTURE.md:152` | "~49 endpoints across 7 routers" | canonical — kept |
| `docs/PROJECT_INDEX.md:93` | "~49 endpoints across 7 routers" | canonical — kept |
| `docs/CLAUDE-state.md:22` | "~49 endpoints across 7 routers" | canonical — kept |
| `docs/START_HERE.md:86` | "(10 endpoints)" | **fixed** → "(~49 endpoints across 7 routers)" |
| `docs/API.md:3` | "5 routers, 21+ endpoints live" | left as-is (historical doc, marked legacy in PROJECT_INDEX) |
| `docs/ROADMAP.md:53` | "24 endpoints across 5 routers" | left as-is (historical phase log) |

Canonical value: **~49 endpoints across 7 routers** (main, predictions, models, analytics, dashboard, execution, stitch).

#### 2. Test count

| File:line | Claim | Action |
|---|---|---|
| `VISION.md:81` | "regression test suite (1040 passing)" | **fixed** → "2,661 pass on RunPod / 1040+ on core suite locally; ~26 transient failures, none prediction-critical" |
| `ARCHITECTURE.md:96` | "1040 passing" | **fixed** → "2,661 pass on RunPod (1040+ on the core suite locally)" |
| `docs/START_HERE.md:88` | "1040+ tests" | **fixed** → "2,661 pass on RunPod / 1040+ on core suite locally" |
| `CHANGELOG.md:47`, `docs/CLAUDE-state.md:9`, `docs/PROJECT_INDEX.md:95`, `docs/ROADMAP.md:28`, `docs/PRODUCTION_RUNBOOK.md:21` | "2,661 pass on RunPod" | canonical — kept |

Canonical value: **2,661 pass on RunPod / 1040+ on core suite locally**, ~26 transient failures (tracking suite + pyarrow-missing on Windows). None prediction-critical.

#### 3. Model count

All canonical docs agree on **85 trained ML artifacts / 119 `.pkl` files**. Verified consistent across README, CLAUDE, VISION, ARCHITECTURE, MASTER_PLAN, ML_MODELS, CEILING, CLAUDE-state, PROJECT_INDEX, START_HERE, ROADMAP, CHANGELOG.

#### 4. Module count

`~120 prediction modules` consistent across CLAUDE-state.md, START_HERE.md, docs/ROADMAP.md. Not load-bearing in README, VISION, ARCHITECTURE, MASTER_PLAN — left as-is.

#### 5. CV games

All canonical docs agree on **17 quality / 29 usable / 75 attempted, target 80 CLEAN**. Verified consistent across README, VISION, ARCHITECTURE, ROADMAP, MASTER_PLAN, CHANGELOG, CLAUDE-state, START_HERE, CEILING, signal-inventory, data-pipeline, SWISH_DEMO.

#### 6. MAE table

All canonical docs agree on PTS 4.62, REB 1.90, AST 1.36, FG3M 0.89, STL 0.72, BLK 0.44, TOV 0.89. Verified in README (lines 81-87 and 287-293), VISION (lines 65-71), MASTER_PLAN canonical-facts table (lines 31-43), PREDICTIONS_QUICKSTART (lines 34-42), ML_MODELS, CEILING, ARCHITECTURE component row.

#### 7. Win prob

All canonical docs agree on **0.7094 acc / 0.193 Brier (walk-forward, 3-fold)** and **0.717 acc / 0.188 Brier (single-split)**. No disagreement.

#### 8. Latest cycle

| File | Claim |
|---|---|
| `CHANGELOG.md` | 0.15.0 — improve_loop R7, execute_loop V1 39/40, cycle 110 |
| `PREDICTIONS_QUICKSTART.md:3` | "master `7b43dff1` (improve_loop R7 / execute_loop R8, post-cycle-110)" |
| `docs/CLAUDE-state.md:12` | improve_loop R7, cycle 110, execute_loop V1 39/40 layers (`cae147b9`) |
| `ROADMAP.md:8` | "Current State (2026-05-24 · loop 5 / cycle 96e)" |
| Working tree | `ae0cbb76` (execute_loop R10) |

PREDICTIONS_QUICKSTART references R8 but R10 just landed in another session (`4c766ed2` then `ae0cbb76`). Not load-bearing for the cold reader — improve_loop R7 + the cycle-110 in-play ship is the story they care about. Left intentionally untouched (PREDICTIONS_QUICKSTART is a thin layer over current production state and was deliberately pinned).

---

## Section 3: README Polish for Cold Visitors

### What the README already does well

The first 12 lines establish:
- **What:** "AI-native sports intelligence platform where Claude agents autonomously discover, validate, ship, and retire prediction signals" (line 3)
- **What this is / isn't:** lines 5-7 — research machine, not prediction model; not a betting tool
- **Why now:** "1-3 years before Genius Sports or Sportradar ships a tracking-integrated prop pricing API" (line 9)
- **Honest performance numbers:** The dedicated section "The 71% Result — Backtested, Not Claimed" lines 46-68 walks through walk-forward acc, Brier, the ROI table, and the honest caveats
- **Architecture overview:** "The Four-Layer Stack" lines 159-194 + the mermaid diagram lines 252-275
- **Roadmap pointer:** §Roadmap at line 430

### Polish applied in this pass

Added a "Current state (2026-05-25)" one-liner immediately under the "navigation" sentence (line 11) so a cold visitor in the first 30 seconds sees:

> 85 trained ML artifacts (119 `.pkl`) across ~120 prediction modules. FastAPI serving layer with ~49 endpoints across 7 routers. 2,661 tests pass on RunPod. Walk-forward holdout: 71% game-win accuracy, +20-28% backtested prop ROI at the +0.5 edge threshold across 7 stats (N=19,964 player-games). Gate 1 (CLV vs Pinnacle close) not yet run — top priority.

Also added pointers to **PREDICTIONS_QUICKSTART.md** and **docs/SWISH_DEMO.md** in the same nav sentence — these were already linked deeper in the README but not visible above the fold. The Swish reviewer can now go from landing → demo flow in one click.

### What was NOT changed (and why)

- **The 71% Result section** (lines 46-68): the dual-gate ROI table is the strongest single piece of evidence in the repo. Kept verbatim.
- **The Four-Layer Stack** (lines 159-194): perception/memory/simulation/action narrative is tight. Kept verbatim.
- **The 164 Gaps** (lines 197-247): the systematic enumeration is the conceptual moat. Kept verbatim.
- **Build phases / roadmap table** (lines 368-385): consistent with ROADMAP.md. Kept verbatim.
- **Architectural mermaid diagram** (lines 252-275): renders correctly on github. Kept verbatim.

---

## Section 4: Verdict

**The github story is coherent for tomorrow's Swish Analytics meeting.**

A cold visitor landing on github.com/neeljshah/court-vision now sees, in this order:

1. **Title + tagline** — "The Renaissance of Sports" + the agentic framing
2. **What/what-not** — research machine, not a betting tool
3. **The window** — 1-3 years before Genius Sports / Sportradar ships
4. **Navigation** — VISION / ARCHITECTURE / ROADMAP / PREDICTIONS_QUICKSTART / SWISH_DEMO all one click away
5. **Current state one-liner** — 85 models, 49 endpoints, 2661 tests, 71% / +20-28% ROI, Gate 1 pending
6. **The 71% Result** — the dual-gate dollar story (the highest-evidence section)
7. **What's Built Today** — the daily ops chain (predict / inject / lineup / line / settle / CLV)
8. **The Six Revenue Surfaces** — multi-surface monetization
9. **Why Possible Now** — the 5000× cost compression argument
10. **The Four-Layer Stack** — perception → memory → simulation → action
11. **The 164 Gaps** — the conceptual moat
12. **Roadmap + Risk Framework**
13. **Beyond Betting + Dashboard + About**

This is the "this person built something real and serious" first impression the brief asked for.

### Top 3 residual risks (none blockers)

1. **PREDICTIONS_QUICKSTART.md pins master at `7b43dff1` / execute_loop R8** while the working tree is now at `ae0cbb76` / execute_loop R10. A reviewer who looks closely at that one doc may see a stale-looking commit reference — not catastrophic (the production MAE story is unchanged), and the task explicitly contested `scripts/execute_loop/*` and `scripts/improve_loop/state.json`, so a downstream pass should update QUICKSTART only after verifying production state hasn't shifted.
2. **`docs/API.md:3` and `docs/ROADMAP.md:53`** still show older endpoint counts (21+ / 24). They are explicitly flagged as legacy/historical in `docs/PROJECT_INDEX.md` ("Historical Documentation — Still Accurate") and won't be on the cold-reader path unless they go through the index. Low priority; kept to preserve the historical-phase-log narrative.
3. **ARCHITECTURE.md component table line 95** says "85 models registered" and Data Flow line 136 says "85 models" — both true today, but a future-careful reviewer might wonder whether the 119 `.pkl` file count and the 85 trained-artifact count are the same number. MASTER_PLAN's canonical-facts table reconciles them explicitly ("85+ trained ML artifacts (119 .pkl files incl. residual heads, period heads, calibration)"). README + ARCHITECTURE could borrow that one-liner if the question comes up in the interview.

None of these block tomorrow's meeting. The canonical hierarchy (README → CLAUDE → CLAUDE-state → PROJECT_INDEX → VISION → ARCHITECTURE → ROADMAP → MASTER_PLAN → CHANGELOG) tells one consistent story end-to-end.

---

## Files modified in this pass

- `README.md` — added current-state one-liner + Quickstart/Swish-demo nav pointers
- `CLAUDE.md` — endpoint count corrected (9 → ~49 across 7 routers)
- `ARCHITECTURE.md` — endpoint count (6+5 → ~49/7) + test count (1040 → 2,661 RunPod)
- `VISION.md` — test count (1040 → 2,661 RunPod) + Renaissance methodology link → text note
- `ROADMAP.md` — `.planning/` and `vault/Plans/` footer links → text notes (cold reader 404 fix)
- `docs/PROJECT_INDEX.md` — `.planning/ROADMAP.md` clickable link → backticked path + cold-reader note
- `docs/START_HERE.md` — endpoint count (10 → ~49/7) + test count (1040+ → 2,661 RunPod / 1040+ locally)

No source code, scripts, or contested files touched. Surgical edits only.

---

*Audit produced by Opus 4.7 1M-ctx agent · 2026-05-25*
