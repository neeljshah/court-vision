# DATA -> EDGE PIPELINE -- the end-to-end chain mapped onto the REAL seams
_Part of the edge-intelligence corpus. The conceptual chain (edge-theory.md) made CONCRETE:
which module is each stage, where it is STRONG, where it is BROKEN, and where the edge
leaks out. Grounded in deep-dives 01 (architecture/funnel), 06 (eval/CLV spine), 09
(intelligence/dead-funnel). Honesty rails: markets are efficient; the win is CALIBRATION,
not a $-edge; a NULL is a success. ASCII only._

## The chain (one line)
DATA -> SIGNALS -> MODELS -> ENGINES -> MARKETS -> INEFFICIENCY -> PROOF -> EXECUTION.
Each arrow is a real seam in the repo. The chain is only as strong as its weakest live
link, and TWO links are currently severed (INTELLIGENCE->MODELS and EXECUTION->PROOF/CLV).
The whole point of the corpus is to know exactly which links carry signal and which leak it.

---

## STAGE 1 -- DATA (the substrate)
Seam: `domains/<sport>/ingest_*.py` -> parquet corpora in `data/` (gitignored).
- NBA: as-of ESPN box + linescore corpus replayed by `NBAPredictor._update`
  (domains/basketball_nba/predictor.py:165-176).
- Soccer/MLB/tennis: per-sport ingest_*.py; the WC vertical is only ~24 matches
  (deep-dive 01 sec5; small-N caveat throughout).
STRONG: leak-safe as-of corpora exist for 5 sports; the box/linescore substrate is real.
BROKEN: "next-tier data is on disk but DISCARDED at ingest" (deep-dive 01 sec5, REVAMP ws03).
The reserved CV slots (`CVSlot`, deep-dive 09 sec1a) that would carry genuinely orthogonal
tracking inputs are UNFILLED. Same-day availability/freshness (the one unmodeled NBA lever,
cut-list CUT 2) is not ingested. => the substrate is at the historical-box ceiling; the
beatable depth is the data we throw away, not better modeling of what we keep.

## STAGE 2 -- SIGNALS / PRIORS (the levers)
Seam: `domains/<sport>/signal_catalog*.py` + as-of builders; the NBA atlas layer
(`intel/*.py` -> 44 parquets) + discovery (`src/loop/discovery.py`).
STRONG: the honest gate records its own failures -- `signal_lab_registry.parquet` = 16
REJECT / 5 VALIDATE (deep-dive 09 sec1c); `discovered_signals.jsonl` = 10/10 REJECT. The
5 VALIDATED NBA signals (`pbp_origin_transition`, `rest_x_age`, `shot_clock_leverage`,
`opp_position_defense_reb`, `oreb_matchup`) passed the leak-free null-shuffle+ablation+FDR
gate and are the most credible on-disk levers.
BROKEN (the central lesson, deep-dive 09 sec5): the signals that PASSED the gate were never
grafted into the served model, and the bulk atlas ablation is a measured NULL --
`.planning/loop/atlas_lift.json`: pts +0.174, reb +0.064, ast +0.008 MAE (all WORSE);
only fg3m -0.003 (trivial, all-folds). => most "signals" are SCOUTING taxonomy
(`signal_registry.parquet`: 86 rows, all `status=folded`, consumer `scouting`/`corr-model`),
not predict-time inputs. The lever stage is rich descriptively, thin causally.

## STAGE 3 -- MODELS (calibrated per-market distribution)
Seam: `domains/<sport>/ratings.py` (Elo / per-90 rates / serve-hold) + the calibration layer
(`scripts/platformkit/recalibration.py`, `calibrator_*.py`, `rating_calibrated.py`).
STRONG: NBA uses MOV-aware Elo + a dispersion recal (`np.polyfit(pr,tt,1)`,
predictor.py:85) + a leak-free in-game temperature recalibrator
(`_fit_live_recalibrator`, predictor.py:100-145; ECE 0.059->0.012, T~1.45). The isotonic
recalibrator is strictly expanding-window (event i uses only 0..i-1), so leak-free by
construction (deep-dive 06 sec1).
BROKEN/CEILING: 6 architectures + 4 levers REJECT on NBA PTS/REB (cut-list CUT 2); recency
beats volume; the ONLY durable model edge is AST pregame ~+7% (RAW, never in playoffs).
MLB Elo is pitcher-BLIND (the biggest single un-pulled lever, deep-dive 01 sec6). => the
models MATCH the devigged close on team strength; that is the honest ceiling, not a bug.

## STAGE 4 -- ENGINES (coherent surface from one distribution)
Seam: `domains/<sport>/predictor.py` {`predict`/`to_jd`/`predict_live`} +
`scripts/platformkit/sim_framework.JointDistribution` (sim_framework.py:54) +
`market_surface(jd, spec)` (sim_framework.py:194) + `live_repricer.get_repricer(sport)`.
STRONG (the cleanest part of the system): ONE win-prob anchors everything. `to_jd`
(predictor.py:179-200) samples total ~ N(mean,sigma) and ANCHORS the margin mean so
P(margin>0) == the Elo win-prob -> ML/spread/total all read off ONE sample matrix by
counting. `predict_live` (predictor.py:202-256) feeds the SAME anchored prior into the
sport-blind repricer + realized score, with a deterministic-game guard (lines 239-241).
Coherent by construction, not bolted on. 5 sports implement the identical interface.
This stage is genuinely solid; little edge work to do here beyond breadth.

## STAGE 5 -- MARKETS (the full ladder + which are soft)
Seam: `domains/<sport>/markets.full_surface` (called at predict_matchup.py:148-149) +
the prop pricing stack `prop_engine`/`prop_edge.py`/`prop_tiering.py`.
- `prop_edge.build_prop_board` (prop_edge.py:229) prices each `PropLine` vs a per-player
  distribution, attaches `_confidence` (prop_edge.py:110) and `_ev_flag` (prop_edge.py:124),
  ranks (prop_edge.py:222).
STRONG: full market surface per sport from one JD; prop board with confidence + EV flagging.
WHERE EDGE IS (per beatable-pocket thesis): the SOFT/DFS prop ladder is P1; mainlines are
EFFICIENT (CUT 1). The engine correctly prices both; the corpus must point prop effort at
the PROVEN stats and quarantine the CUT-4 negative-skill props (WC Cards/Assists/Goals).

## STAGE 6 -- INEFFICIENCY (detect the crack)
Seam: `odds_provider/` + `odds_shop.py` (line-shop/arb/EV, devig via Shin) +
`prop_edge` EV flag + `pm_trading/edge_signal.py` (PM-vs-book divergence) +
`live_repricer` (the in-game lag pocket).
STRONG: keyless multi-book aggregation + devig + EV/arb detection exist and reuse the shared
Shin devig (`shin.shin_devig`, deep-dive 06 sec2c). The six pockets of edge-theory.md each
have a detection home here.
BROKEN/THIN: live odds breadth is a single republished ESPN line -> no real two-venue arb
(deep-dive 01 sec5). Detection without a captured CLOSE (stage 8) cannot be proven.

## STAGE 7 -- PROOF (calibration + CLV; the only arbiter)
Seam: `scripts/platformkit/eval_gate/` (the keystone) + `self_improve.py` (the ratchet) +
`prop_tiering.py` (the evidence ladder).
STRONG (the most rigorous part of the project, deep-dive 06 sec4): leak-free walk-forward
(`assert_vintage` + purge48h + embargo3d), cluster-robust Diebold-Mariano (unit-tested wider
than naive SE), Shin devig, frozen-baseline regression block, FAIL-CLOSED on empty/leak.
`_verdict` (run_gate.py:74): BEATS_CLOSE only if `bss>0 AND dm.p<0.05 AND n>=200`. The
ratchet can only improve-or-hold.
BROKEN (the binding constraints, deep-dive 06 sec5): (a) the gate has NEVER run on real data
offline -- `--golden` is a SYNTHETIC near-oracle fixture, so it proves the HARNESS
non-regresses, not that the real model is good. (b) `improve_ledger.jsonl` = 48/48
INSUFFICIENT_DATA: real settled games per sport are below `MIN_RECAL_GAMES=60`; `dm.n>=200`
is structurally unreachable near-term. (c) CRPS/pinball are built+tested but NOT wired into
`run_gate` (binary BSS only) -> continuous markets/prop intervals are never gated end-to-end.
=> proof DESIGN is near-bulletproof; proof EVIDENCE is correctly null today.

## STAGE 8 -- EXECUTION (paper -> CLV -> real, gated)
Seam: `frontend/` board + `prop_loop.py`/`prop_paper.py`/`grade_paper.py` +
`clv_ledger.py` (`compute_clv`, clv_ledger.py:100) + `prop_line_history.py` +
`pm_trading/auto_loop.py` (the `--forever` cycle).
STRONG: append-only idempotent ledgers; correct CLV sign (positive = better number than fair
close, clv_ledger.py:100 -- explicitly NOT the documented "record_clv backwards" gotcha);
every paper row carries `executed=False`.
BROKEN (the UNCAPTURED CLV -- the single highest-leverage fix, deep-dive 06 sec5):
`clv_ledger.jsonl` = 38 lines, 14 settled, **0 carry a real CLV**; `prop_line_history.jsonl`
= **1 line**. No closing line is stored, so the honest yardstick (CLV) has NO signal and
`frontend/serve.py:252` reports `pct_beat_close=None`. The "CLV-proven" top tier of
`prop_tiering` does not exist in code (it tops out at CALIBRATION_PROVEN). => the chain
terminates one link short of its own bar for real money.

---

## Where the edge LEAKS OUT (the two severed links, in priority order)
1. EXECUTION->PROOF: closing lines are not captured, so nothing can ever become CLV-PROVEN.
   This is a SCHEDULING/OPS fix (the code exists) -- run `prop_loop`/`pm_trading` cadence up
   to kickoff so `prop_line_history.jsonl` and team-bet close fields accrue. Highest leverage,
   lowest effort (deep-dive 06 sec6 quick-win 1). Until this link closes, every edge claim
   below CALIBRATION-PROVEN is stranded.
2. SIGNALS->MODELS (the dead funnel): atlas/intelligence is built, persisted, READ at
   predict time (player_props.py:2156-2170), then SILENTLY DROPPED because the served model
   was never trained on those columns (`prop_stack_meta.json` has no `atlas_`; deep-dive 09
   sec5). Either retrain WITH `atlas_feature_names()` and re-gate per-section (only the
   all-folds winners), or gate `CV_PROP_EXTRA_FEATURES` OFF and label the block scouting-only.
   The measured ablation says only fg3m is even marginally additive -- so honesty likely
   means DEMOTE, not graft, for most sections.

## How this pipeline drives the corpus
- Stages 1-2 are the lever frontier: deepen DATA in beatable pockets (props, live, CV slots),
  gate every SIGNAL on >=2 corpora (intelligence-architecture.md rule).
- Stages 3-5 are at the efficient ceiling on mainlines -> CUT (calibrated decision-support).
- Stage 6 is where the beatable-pocket DETECTION recipes live (per-sport inefficiency-catalog).
- Stages 7-8 are the bottleneck: fix CLV capture FIRST, because no pocket can graduate from
  HYPOTHESIS -> CALIBRATION-PROVEN -> CLV-PROVEN until the proof and execution links carry signal.
