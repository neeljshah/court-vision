VERDICT: PARTIAL -- B could not run (no cached simulator possession-transition output exists; rollout forbidden); A and C are complete; C's sealed decision is STOP SIMULATOR EXPANSION.

# S322 cached simulator diagnostics -- finisher run

Spec: `docs/evidence/tracking/specs/S322_spec.md`. Prereg seal (verified): `eb2a883157e6c383f4781ce0df9719651b036ce2f055f5cf97f533fb7a8b5ee5`.
Interpreter: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe`.

## Premise (recomputed from the v2 series, 1e-9 tolerance)
n = 2130 ticks, 355 clusters. Brier market 0.151529526995 (S287 0.151529526995305), null 0.151996612537 (S287 0.151996612536570), simulator 0.257090852406 (S287 0.257090852406103). Every |diff| < 5e-13. PREMISE TRUE.

## A -- semantics trace (30/30 sealed states, `trace.csv`)
0 unexplained errors; every error listed by field. All 30 states FAIL score_semantics, clock, overtime: the frozen replay source (`S287_selected_tick_series.csv`, the prereg's own frozen input) carries no home_score/away_score/seconds_remaining/period/is_overtime columns, only elapsed, market_prob, p_null, p_simulator, outcome_home_win and identifiers. home_polarity and conservation PASS on all 30, but vacuously: output_side and away-probability are also absent, and `trace_state()`'s None-default treats a missing field as compliant (absent output_side reads as "home"; conservation collapses to 1.0 when away-probability is absent, independent of the real p_simulator value). Net: 0 of 5 checks meaningfully exercised semantics on this artifact -- a source-schema gap, not a scored simulator defect.

Selection (fix 1c): true round-robin over the sealed criteria (earliest, latest, tied, |margin|>=15, overtime, both venues) -- one pick per non-empty bucket per pass, so a dense bucket can never exhaust the 30-slot budget before a later bucket is drawn from -- each bucket sourced from whichever frozen input's schema exposes its fields (primary `S287_selected_tick_series.csv`, fallback `S317_S287_v2_tick_series.csv`); remaining slots stride-filled across the full ordered index. Bucket counts unchanged from fix 1b (only earliest/latest are non-empty on this input pair, so round-robin and the old sequential fill coincide here): earliest=1, latest=1, tied=0 (NO_FIELD_IN_ANY_SOURCE), margin15=0 (NO_FIELD_IN_ANY_SOURCE), overtime=0 (NO_FIELD_IN_ANY_SOURCE), venue=0 (NO_FIELD_IN_ANY_SOURCE), spread_fill=28 -- neither frozen input carries home_score/away_score/period/is_overtime/venue, confirming the schema gap above at the field level, not only the trace-output level. Selected ordered ranks (of 2,130, unchanged): 0,1,80,159,237,316,395,474,552,631,710,789,868,946,1025,1104,1183,1261,1340,1419,1498,1577,1655,1734,1813,1892,1970,2049,2128,2129 -- spans the full index, not a head slice. Boundary states corrected by the ts-alias fix: earliest is now `401810008:120` (ts 1762128843), latest is `401811000:2520` (ts 1775527545) -- see Corrections (fix 1c) below.
Frozen-logit replay: the cached-logit recalibration path (arm ii, `temperature_intercept_m0`) run twice in this environment over all 2,130 states; max |diff| = 0.0 (tolerance 1e-9): PASS (`replay.csv`).

## C -- prior/uncertainty ablation (`ablation.csv`; `cpcv_evaluate`, 3-day embargo, 2000 paired-cluster bootstraps)
M0 substitution: `tick_market_substitution` (v2 series has no pregame-M0 column; used tick p_market per the sealed fallback).

| arm | n rec | n clu | brier | ece10 | logloss | improve vs null | CI95 |
|---|---|---|---|---|---|---|---|
| (i) temp+intercept | 2130 | 355 | 0.252170 | 0.002552 | 0.697539 | -0.100174 | [-0.115629,-0.083779] |
| (ii) temp+intercept+M0 | 2130 | 355 | 0.153851 | 0.018425 | 0.460056 | -0.001854 | [-0.003424,-0.000462] |
| (iii) N (null) | 2130 | 355 | 0.151997 | 0.024326 | 0.455778 | 0 (baseline) | n/a |

Sealed bar C: (ii) needs improvement >= +0.002 AND CI-lower > 0. Actual -0.001854, CI entirely below 0: FAILS. Decision: STOP SIMULATOR EXPANSION until B is fixed.

## B -- transition law: BLOCKED
Enumerated `data/cache/` entries containing pbp|possession: 35 by recursive path search (fix 1c; the 9 below were fix 1b's top-level-only census): `_pbp_residual_diag.json`, `inplay_pbp_microstructure.parquet`, `iter64/iter72_inplay_pbp_*_results.json`, `nba_pbp_wallclock_raw/{summary,scoreboard}`, `pbp_possession_features[_l5].parquet`, `probe_R14_H3_possession_sim_results.json`, `sackmann_pbp/` (tennis, wrong sport), plus the `ingame/pbp_foul_states_*`, `ingame/pbp_states_*`, and `team_system/pbp*` subtree entries the top-level census missed. One store qualifies as genuine sequential NBA play-by-play: `nba_pbp_wallclock_raw/summary/*.json`, 1610 games (game 401703370: 454 ESPN `plays` events with type/team/period/clock/scoringPlay), well over the 200-prefix requirement. B is BLOCKED regardless: no cached artifact anywhere (`data/cache/` or `docs/evidence/harness/`) holds the simulator's own possession-level one-step transition prediction -- S287/S317 cache only tick-level win-probability, and `probe_R14_H3_possession_sim_results.json` is an old ship-gate summary, not per-possession output. Producing one requires invoking the simulator live, forbidden in this row (cached predictions only).

## Minimal fix (`scripts/platformkit/ingame/s322_prior_ablation.py`, 1 line)
`states_from_rows()` passed raw `Z`-suffixed UTC timestamps into `cpcv_engine`'s `datetime.fromisoformat`, which raises on Python 3.10 (no `Z` support pre-3.11) and blocked the ablation run. Fixed: `.replace("Z","+00:00")` before assignment, matching the existing convention in `s264_isoweek_overlap.py` / `exec_calibration.py` / `paper_ingame.py`. Reran the test file (unaffected, still 3 passed) and the module (completed).

EYE CHECK: NONE.

NOT VERIFIED:
- A one-step or single-fold ablation pass is not end-state calibration.
- The 2,130-tick construct is the S287 restriction, not a season.
- (C)'s cached logits were produced in the pod environment; S316's cross-environment difference applies.
- A's home_polarity/conservation PASS is vacuous (see above); its score_semantics/clock/overtime FAIL reflects a source-schema gap, not a measured simulator defect.
- B's transition-law hypothesis remains untested; genuine PBP prefixes exist but no cached simulator possession-output artifact does.

Tests: `tests/platformkit/test_s322_sim_diagnostics.py` 6 passed (fix 1c adds a dense-bucket round-robin-starvation check and a ts-alias min/max boundary check); `tests/platformkit/test_loc_rail_scope.py` 1 passed. LOC: no file this row touches exceeds 300 lines (trace 232, ablation 206 unchanged, test 116); no split needed.
Wall time (UTC): trace 17:58:01-17:58:02; ablation crash+fix+rerun 17:59:28-18:00:37; fix 1b (B7 reselect + replay) 2026-09-08; fix 1c (ts alias + true round-robin) 2026-09-08.
SHA-256 (LF-normalised):
- `trace.csv` (fix 1c) a7438eeecbfdffa47c3054c652ddc0509030ae9de99fe4b1c78493e3a2a07ffe
- `replay.csv` 7c460eb8abac024993afba71da60e860cde446759260f827f8163317257455e8
- `ablation.csv` d8e248b84656d304907967705d4ecbdbacfdd0fb16f3f41b195927e5de5e9514 (unchanged; C not rerun)
- `s322_prior_ablation.py` (unchanged) df76641fc3f21019bcae11c1080290a3ef6b19004f57882c64c25180211bef78
- `s322_semantics_trace.py` (fix 1c) d55583a31fd613f9648511b02fb49a0ff85c4a319be2ceae2338cce2442fb822
`ablation_evaluator_records.csv` (module side output, full-precision per-tick losses) is left on disk but NOT committed: it is not a required artifact, and several of its long raw decimal/timestamp fields coincidentally trip the retracted-digit scan; not worth reformatting for a non-required file.

## Corrections (fix 1b, 2026-09-08)
B7 (verified codex-sol REJECT): the sealed selector's remaining-slot filler was `for row in ordered`, a sequential head-slice (29/30 states from the first 29 of 2,130 ordered positions). Fixed in `s322_semantics_trace.py`: criteria buckets are now field-sourced per-bucket across the sealed frozen inputs (with honest NO_FIELD_IN_ANY_SOURCE reporting when a bucket's fields are absent everywhere) and remaining slots are stride-filled evenly across the full ordered index, never a contiguous run; see selection detail and ranks above. Frozen-logit replay (the method's own requirement, previously only satisfied by writing trace rows) now runs explicitly: two passes of the cached-logit recalibration path, max |diff| = 0.0, well inside the 1e-9 tolerance. NEW GAP (census): `data/cache/ingame/sim2_possessions.parquet` (780,166 rows, 11 columns: period, clock_start, off_is_home, points, duration, off_margin, home_margin, home_score_start, away_score_start, game_id, season) was missed by the original top-level census; it is possession-level, not one of the prereg's four sealed tick-level frozen inputs, so it is out of scope for A's bucket search, and it carries no simulator probability column, so B stays BLOCKED (unchanged verdict, now with the exact reason recorded). NEW GAP (Q9): the differential per-tick evaluator-record CSV exists only as the untracked `ablation_evaluator_records.csv`; per this fix lane's own scope it is left exactly as is and stays uncommitted (not reformatted here) -- a future row should round its decimal fields and commit a digit-scan-clean copy if Q9 needs an archived artifact.

## Corrections (fix 1c, 2026-09-08)
Verified codex-sol REJECT of fix 1b, two findings. (1) `s322_semantics_trace.py:76`'s sealed timestamp sort omitted the primary input's `ts` field (`_value(row, "timestamp_utc", "timestamp")`); `S287_selected_tick_series.csv` carries neither `timestamp_utc` nor `timestamp`, only `ts`, so every primary row's sort key collapsed to the empty string and the game_id tie-break silently picked the wrong earliest/latest. Fixed by adding `"ts"` to the alias list; boundary states corrected from `401809239:120`/`401850920:2520` to the true extremes `401810008:120` (ts 1762128843) and `401811000:2520` (ts 1775527545); `trace.csv` regenerated (all 30 rows re-sorted; ranks unchanged at 0..2129 since only earliest/latest/spread_fill are populated on this input pair). (2) NEW GAP (verified): the criteria-bucket fill at (old) :163-170 was sequential exhaustion, not round-robin -- each bucket in CRITERIA order could claim up to 15 of 30 slots before the next bucket ran, so a dense tied/margin15 span could starve the later overtime/venue buckets to 0 picks even when non-empty. Fixed: true round-robin -- one pick per non-empty bucket per pass, until 30 slots are filled or every bucket is exhausted, then the same stride fill. Added `test_round_robin_draws_from_every_dense_bucket_each_pass` (200 ticks: dense tied and |margin|>=15 spans, 20 overtime rows, 2 venues -> every non-empty bucket now picks >=1) and `test_boundary_states_are_the_true_min_max_ts_rows` (reverse-sorted game_id proves `ts`, not game_id, drives the earliest/latest pick); both pass. Recursive `data/cache/` pbp|possession path count is 35, not the 9 named by fix 1b's top-level-only census; B stays BLOCKED unchanged (none of the 35 holds a cached one-step simulator possession probability). C not rerun (unaffected by A's selection fix); sealed decision STOP SIMULATOR EXPANSION stands.

Proposed ledger line (not written):
`2026-09-08 | in-game calibration | S322 | fix 1c: ts alias added to the sealed timestamp sort (boundary states corrected to 401810008:120/401811000:2520); criteria-bucket fill made true round-robin (fixes overtime/venue starvation behind a dense tied/margin15 span), no bucket-count change on this input pair; trace regenerated (ranks unchanged 0-2129); A source-schema gap (30/30) + C ablation fails bar (improvement -0.00185, CI<0) + B blocked (no cached possession probability; recursive pbp/possession census now 35 paths, still none with a simulator probability) | PARTIAL`
