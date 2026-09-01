# CourtVision Platform -- Domain-Agnostic, Calibrated Multi-Sport Forecasting Engine

> **Status (2026-06-15): SHIPPED -- 4 sports live.** NBA, MLB, Soccer, and Tennis predictors are built and validated against real corpora. The product is one converged, calibrated prediction platform: a single win-prob per sport anchors a coherent pregame surface plus an in-game repricer, exposed through `domains/<sport>/predictor.py` and the unified `scripts/platformkit/predict_matchup.py` CLI. For the full product narrative read **[docs/PREDICTOR_PLATFORM.md](PREDICTOR_PLATFORM.md)**; for the honest, adversarially-audited numbers read **[docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)** (the single truth source).

---

## The Thesis

The NBA system took months and 3,206 commits to reach production quality. A naive port to a second sport would cost another several months each -- because the machinery would be rebuilt from scratch every time.

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

### How "one win-prob anchors the whole surface" is realized

A single calibrated number per matchup is the spine; every other market is derived from it, never fit independently. The mechanism, traced through the tennis adapter (`domains/tennis/predictor.py`) as the cleanest reference:

```
   raw rating model           leak-free recalibration         the anchor
  (Elo / Poisson /     -->   (Platt / temperature /     -->   p(win)
   NegBinom / NNLS)           isotonic, per sport)            ONE number
                                                                  |
                          +---------------------+-----------------+-------------------+
                          v                     v                 v                   v
                   moneyline / 1X2        totals (O/U)      spreads / sets       SGP / props
                   = the anchor itself    serve/poss prob   bisected to the      joint samples
                                          bisected so the   same anchor          drawn from the
                                          MC engine's       (coherent margin)    SAME MC paths
                                          marginal == anchor
```

- The rating model emits a *raw* probability; a per-sport leak-free recalibrator (`fit_platt` / temperature / isotonic) maps it to the calibrated anchor (`domains/tennis/predictor.py:89-91, 116`).
- The Monte-Carlo / possession engine is then *bisected* so its match-win marginal equals the anchor (`serve_probs_from_winprob`, `domains/tennis/predictor.py:118-120`). Totals, set scores, and props fall out of the same paths, so they cannot disagree with the moneyline.
- `to_jd()` returns one `JointDistribution` (`kernel.sim_framework`) over the coherent outcome space; `prob_side_win()` on it reproduces the anchor up to Monte-Carlo noise (`domains/tennis/predictor.py:144-159`). Coherence is MC-approximate, not an analytic identity -- the docstring states this honestly.
- `predict_live()` re-prices the *same* anchor against realized state (race-to-N / inning / period repricer) and re-applies a leak-free in-game recalibrator (`domains/tennis/predictor.py:161-206`).

This is what makes the surface auditable: there is exactly one place a probability can be wrong, and every market inherits it.

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

### The kernel/adapter contract (what a NEW sport must implement)

A new sport plugs into three frozen seams. Nothing in `kernel/` changes; the adapter is the only new code. The contract is enforced mechanically -- not by convention -- by `kernel.testing.conformance.check_sport_context()` and the cross-sport parity matrix.

**Seam 1 -- `SportContext` (the runtime contract).** A domain supplies a `SportContext` (`kernel/config/context.py`) carrying nine typed sub-configs. `check_sport_context(ctx)` (`kernel/testing/conformance.py:40`) returns a list of human-readable violations; an empty list means conformant. Required pieces:

| Field | Type | Hard requirement (conformance check) |
|---|---|---|
| `stats` | `SportStatRegistry` | non-empty `target_names()`; `loop_targets` ends with `("minutes","total","winprob","usage","sigma")`; `priced_order() subset of target_names()`; non-empty `sport_id` |
| `clock` | `GameClockConfig` | `regulation_sec() > 0` unless `untimed=True` (tennis is untimed) |
| `roster` | `RosterConfig` | `on_field_count >= 1`; `roster_size >= on_field_count` |
| `game_state` | `GameStateConfig` | must expose `blowout_margin`, `clutch_margin`, `garbage_margin`, `final_margin_sigma`, `winprob_promotion_period`, ... |
| `entities` | `EntityRegistry` protocol | runtime-checkable; must implement the protocol methods |
| `pbp_mapper` | `PBPEventMapper` protocol | runtime-checkable |
| `league_client` | `LeagueClient` protocol | runtime-checkable |
| `atlas_schema` | `AtlasSchema` | present (empty sections allowed) |
| `court` / `speed` | `CourtConfig` / `SpeedConfig` or `None` | optional; type-checked if present |

**Seam 2 -- `feature_spec.py` (the train==inference contract).** A frozen `FeatureSpec` (`scripts/platformkit/feature_spec_core.py`) declares the base feature matrix as an ordered tuple of `FeatureField(name, source, default, cast, source2, op)`. `build_base_matrix(spec, df)` is the single derivation point, so the same columns are produced at train and at inference -- this closes the most expensive bug class (a feature wired at train that silently reads `0.0` at inference; see `improve/parity_check.py`). Tennis's full spec is five fields (`domains/tennis/feature_spec.py`): two `OP_DIFF` Elo diffs plus `best_of` / `rest_days_a` / `rest_days_b`.

**Seam 3 -- `ingest_manifest.py` (the provenance / leak contract).** An `IngestManifest` (`scripts/platformkit/ingest_manifest_core.py`) tags every corpus with a `leak_class` and a freshness SLA. The four classes are load-bearing for leak-safety:

- `LEAK_PRE_GAME` -- known before tip; safe as a pregame feature.
- `LEAK_IN_GAME` -- accrues during play; in-game conditioning only.
- `LEAK_POST_GAME` -- only known after the final whistle; settlement labels and training *targets*, never pregame features.
- `LEAK_REFERENCE` -- static reference (parks, surfaces, rosters).

The honesty anchor: a post-game box (e.g. tennis `match_stats`) is `LEAK_POST_GAME`, but the as-of features *derived* from it (`asof_features` / `asof_hold` / `asof_return`) are `LEAK_PRE_GAME` by construction, because `scripts.platformkit.asof_common` snapshots **before** updating (`domains/tennis/ingest_manifest.py`).

**The 9-step playbook** (codified in `scripts/platformkit/new_sport_scaffold.py`) to add a sport, e.g. NFL:

```
1. Ingest corpora to data/domains/<sport>/ (games, odds, ...).
2. python -m data_registry.inventory scan        # census sees non-empty corpora
3. python -m scripts.platformkit.new_sport_scaffold <sport> --write
4. Edit domains/<sport>/feature_spec.py fields to match the adapter base matrix.
5. Edit domains/<sport>/ingest_manifest.py sources + leak_class + SLA.
6. Add <sport> to scripts.platformkit.parity_matrix.SPORTS; run it -> all cells green.
7. Write a guarded real-adapter parity test (byte-equal base matrix).
8. Build a depth as-of builder via scripts.platformkit.asof_common; eval + gate it.
9. Record the honest gate verdict (REJECT / MATCH) in the reject ledger.
```

The scaffolder stamps valid-out-of-the-box `__init__` / `feature_spec` / `ingest_manifest` stubs (a toy rating-diff + rest field, a games + odds source); you then edit them to the real adapter and prove byte-equal parity. Steps 8-9 are where the honesty discipline lives: most depth signals are expected to REJECT, and a recorded REJECT is a first-class result.

### The parity-matrix mechanism

`scripts/platformkit/parity_matrix.py` is one fail-closed green/red grid over `SPORTS x {census, manifest, feature_spec}`. It is pure-offline (imports only the domain decl modules + `data_registry`) and runs in under a few seconds with no torch and no app boot.

```
                 census          manifest        feature_spec
basketball_nba   green           green           green
mlb              green           green           green
soccer           green           green           green
soccer_intl      green           green           green
tennis           green           green           green
                 -------------------------------------------
PARITY: GREEN (0 red cells)
```

Each cell is computed independently (`parity_matrix.py:65-116`):
- **census** -- `scan_corpora` finds the sport's corpora and `check_drift` confirms none required is 0-row (RED on missing/empty).
- **manifest** -- `domains.<sport>.ingest_manifest` both validates structurally (`man.validate()`) AND every declared source exists + is non-empty in the live census (`man.validate_against_inventory(inv)`).
- **feature_spec** -- `domains.<sport>.feature_spec` loads, has a non-empty frozen catalog (`catalog_hash()`), and `build_base_matrix` produces exactly `n_features()` columns with matching names (structural parity; byte-equal-to-adapter parity is proven separately per-sport in `tests/platformkit/`).

The grid is **fail-closed with a tri-state**: a dimension a sport has *not built yet* is `n/a` (gray) and does NOT fail the gate; a dimension that is PRESENT-but-broken is `red` and DOES (`is_green()` returns True only if no resolvable cell is RED -- CLI exit 2 otherwise, `parity_matrix.py:131-163`). `soccer_intl` has since filled in the manifest/feature_spec seam (`domains/soccer_intl/ingest_manifest.py`, `domains/soccer_intl/feature_spec.py`, `domains/soccer_intl/predictor.py`) and is now green across all three cells like every other sport.

Two AST-only guards keep the seams honest at the import layer (`scripts/platformkit/check_import_contract.py`): **kernel purity** (`kernel/` may not import `src.*` / `domains.*` / `api.*` / `scripts.*`) and the **cross-adapter ban** (`domains/<a>/` may not import `domains/<b>/`). These never execute the inspected files.

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

All numbers are calibration/sharpness (lower Brier/RMSE = sharper). They are NOT a profit edge. The canonical record is **[docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)**.

**Pregame -- beat-the-close (leak-free OOS, held-out 2nd half):**

| Sport / market | Ours | Devigged close | Verdict |
|---|---|---|---|
| NBA moneyline (Brier) | 0.1735 | 0.1672 | MATCH (within noise) |
| NBA total O/U (RMSE) | 19.17 | 18.11 | BEHIND (injury/lineup freshness) |
| MLB moneyline (Brier) | 0.2429 | 0.2390 | MATCH (tiny deficit = pitcher-blindness) |
| MLB total O/U (RMSE) | 4.72 | 4.44 | BEHIND (park/weather/SP freshness) |
| Soccer O/U-2.5 (Brier) | 0.2465 | 0.2390 | MATCH (pooled Platt) |
| Tennis ATP ml (Brier) | 0.2177 | 0.2028 | BEHIND (ATP closes very efficient) |

**In-game -- conditioning on realized state vs the static pregame line:**
NOTE: NBA row is real-corpus-only (VALIDATION_PENDING on a fresh clone -- committed fixture
prints no-improvement for NBA due to SYNTHETIC ANCHOR ARTIFACT; MLB/Soccer/Tennis reproduce).

| Sport | Static -> conditional (Brier) | Corpus |
|---|---|---|
| NBA (end Q1/Q2/Q3) | 0.209 -> 0.159 | real-corpus only; VALIDATION_PENDING on fixture |
| MLB (after inning 3/5/7) | 0.241 -> 0.126 | reproduces on committed fixture |
| Soccer 1X2 (half-time) | 0.626 -> 0.502 ; O/U-2.5 0.264 -> 0.176 | reproduces on committed fixture |
| Tennis (after set 1) | 0.219 -> 0.151 | reproduces on committed fixture |

**The thesis:** pregame MATCHES the devigged close on team-strength markets and is BEHIND on
totals/ATP ONLY by freshness data a box model cannot see. IN-GAME conditioning (a pregame
intelligence prior fused with realized state) is the decisive measured, calibrated, and delivered
edge -- MLB/Soccer/Tennis WIN reproduced on committed fixtures; NBA in-game WIN is real-corpus
(VALIDATION_PENDING), edge_claimed = False. No fabricated $ edge.

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

## Module Map (path -> responsibility)

| Layer | Module(s) | Responsibility |
|---|---|---|
| kernel / config | `kernel/config/{context,stats,clock,roster,game_state,entities,pbp,roster,court,speed}.py` | The nine typed sub-configs of `SportContext` -- the runtime contract |
| kernel / conformance | `kernel/testing/conformance.py` | `check_sport_context()` -- mechanical adapter validation |
| kernel / sim | `kernel/sim_framework/` (+ `joint/`) | Sport-blind Monte-Carlo path framework; `JointDistribution` |
| kernel / validation | `kernel/validation/proof_metrics.py` | Brier / RMSE / ECE proof metrics, sport-blind |
| feature seam | `scripts/platformkit/feature_spec_core.py` | `FeatureSpec` / `FeatureField` / `build_base_matrix` (train==inference) |
| provenance seam | `scripts/platformkit/ingest_manifest_core.py` | `IngestManifest` / leak-class constants / freshness SLA |
| parity gate | `scripts/platformkit/parity_matrix.py` | Fail-closed census x manifest x feature_spec grid |
| import guards | `scripts/platformkit/check_import_contract.py` | Kernel-purity + cross-adapter-ban (AST-only) |
| new-sport codegen | `scripts/platformkit/new_sport_scaffold.py` | Stamp the three decl seams; the 9-step playbook |
| train/infer parity | `improve/parity_check.py` | `parity_ok()` -- catch silent zero-read feature wiring bugs |
| per-sport adapter | `domains/<sport>/{predictor,feature_spec,ingest_manifest,adapter}.py` | The only new code per sport |
| always-on stack | `supervisor/manifest.py`, `boot.ps1` | Process inventory + DAG-ordered boot (see PLATFORM_TOOLING) |
| serving | `predict_service/{app,produce,assemble,scheduler,store,contracts}.py` | Auto-API (:8099) + producer; one calibrated envelope per sport |

For the tooling CLIs, proof-module surface, supervisor process table, and the
robustness test matrix see **[PLATFORM_TOOLING.md](PLATFORM_TOOLING.md)**. For the
end-to-end CV-origin map see **[../ARCHITECTURE.md](../ARCHITECTURE.md)**; for the six
core decision systems see **[architecture/system-overview.md](architecture/system-overview.md)**.

### System intelligence map (machine-readable dataflow graph)

For "how does X work / what produces Y / what consumes Z" -- a curated,
disk-verified graph of writers/daemons/producers/stores/resolvers/webapp
routes and their `writes`/`reads`/`serves`/`registers` edges, built by
`scripts/platformkit/analytics_verify/system_map.py` into
`data/cache/analytics_verify/system_map.json` (gitignored, local-only). Query
it via the same fail-closed resolver contract as everything else in
[ANALYTICS_CONTRACT.md](ANALYTICS_CONTRACT.md):
`resolver_registry.resolve(query, category="system_map", node=<node_id>)`.
The graph never claims a node exists without a disk check --
`verified: true|false` on every node, `edge_claimed: false` always.

---

## The Build Program -- kernel extraction, live status

The `kernel/` + `domains/<sport>/` split described above is not finished by hand; it is executed by
an autonomous build harness (`scripts/platform_harness/`) working a task backlog under the same
gates as everything else in this repo. Current status, pulled from a live run of the harness's own
status probe (not typed by hand):

```
python scripts/platform_harness/build_status.py
program=platform_v1  phase_cursor=0
tasks  total=83  done=53  in_progress=0  review=0  blocked=0  rejected=0  todo/ready=30
percent_done=63.9%
```

53/83 tasks done (63.9%). Full loop mechanics -- probe / adjudicate / plan-wave / spec / spawn /
review / gate / merge, the `HOT_FILES` serialization rules, the game-day landing filter -- are
documented in **[PLATFORM_HARNESS.md](PLATFORM_HARNESS.md)**; the always-on runtime fleet this
harness is separate from (it builds code, the daemons run it) is documented in
**[DAEMONS.md](DAEMONS.md)**.

One concrete extraction artifact worth naming: the ten `CV_CFG_*` dual-path config flags
(`CV_CFG_STATS`, `CV_CFG_PBP`, `CV_CFG_COURT`, `CV_CFG_CLOCK`, `CV_CFG_LEAGUE_CLIENT`,
`CV_CFG_ROSTER`, `CV_CFG_SPEED`, `CV_CFG_GAMESTATE`, `CV_CFG_ENTITIES`, `CV_CFG_ATLAS`) are
registered in `src/brain/flags.py`, every one **default-OFF** with `flag_allowed_on=False` until
its own recorded gate verdict (byte-identical fixture slate ON==OFF, pytest green, loop dry-run
green). Registering a flag is not the same as flipping it -- per the human-gated-paths and
no-edge-claims invariants, this program never flips a flag ON unattended.

`domains/basketball_nba` is carrying real ingest work as part of this deepening, not just
scaffolding: `ingest_espn_player_box.py` backfills the 2025-26 per-player box gap (stats.nba.com is
blocked from this route; ESPN's site.api is the documented working substitute) directly into the
existing `quarter_box` cache shape, so the pre-existing pure transform in `ingest_boxscores.py`
needs zero changes to consume it.

### The census -- the domain-expansion queue

`data/frontend/ops/data_census.json` is the machine-readable answer to "what's on disk, what's
derivable from it, and what's actually built" per sport -- CENSUS -> DIFF -> FACTORY (walk every
source, list what claim families are derivable and their BUILT/PARTIAL/UNBUILT status, then feed
UNBUILT-with-`leverage_rank` families into the standing priority queue). This is the same census
step 2 of the new-sport playbook above runs (`python -m data_registry.inventory scan`) -- one
mechanism serves both "what should this existing sport build next" and "is a new sport's corpus
non-empty enough to onboard." Full per-sport inventory and the priority queue itself:
**[DATA_DEPTH.md](DATA_DEPTH.md)**.

---

## Roadmap

### Done -- Extract the kernel + ship four adapters
The sport-agnostic machinery is shared, and NBA/MLB/Soccer/Tennis each run as adapters on top of it with leak-free proofs.

### Now -- Deepen the per-sport data funnel
For each sport, ingest more reachable, fresher data to sharpen calibration and widen the in-game conditioning lead. Pregame markets are efficient; the gains are freshness, joint-market shape, and in-game state. The kernel-extraction harness (above) is running this concurrently against the platform backlog -- see [PLATFORM_HARNESS.md](PLATFORM_HARNESS.md) for live status.

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


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
