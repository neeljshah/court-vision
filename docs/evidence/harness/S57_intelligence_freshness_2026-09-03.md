# S57 -- the intelligence layer inside freshness governance

Row: `data/intelligence` holds 151 artifacts, all mtime 2026-06-02, and 0 of
them appeared in `gate_manifest.json`, so nothing dated -- or could block -- a
stale intelligence answer.

Verdict: **ACCEPT WITH CORRECTIONS**, with a **PARTLY FALSIFIED PREMISE**.
151/151 are now registered with a labelled measurement time and the producer
map is wired; the row's causal story ("stale *versus gate corpora rebuilt
2026-09-02*") does not hold -- no intelligence producer reads a gate corpus.

Calibration/audit work only. No dollar, ROI, profit or edge claim; no bar moved.

---

## 0. Premise re-measured first (Q8)

| the row says | measured 2026-09-03 | verdict |
|---|---|---|
| 151 files under `data/intelligence` | 151 files (99 parquet, 50 json, 1 pkl, 1 png) | CONFIRMED |
| all mtime 2026-06-02 | 151/151 mtime 2026-06-02 | CONFIRMED |
| 0 registered in `gate_manifest.json` (19 rows) | 0 of 151; the on-disk manifest was a 19-row snapshot from 2026-09-01T23:26Z, a fresh rebuild finds 59 pre-existing rows | CONFIRMED (the 19 was stale, not wrong) |
| stale "versus gate corpora rebuilt 2026-09-02" | **FALSIFIED.** 0 of the 95 producers reads `data/cache/combo/gate_corpus_*.parquet`. The layer's real inputs are `data/nba_ai.db` (mtime 2026-05-28) and the `data/*.parquet` corpora (May 2026) -- OLDER than the artifacts they produced | FALSIFIED |
| "rebuilt by the S24 refresher where a producer exists" | possible for 19 of 95 producers; for the other 76 a re-run reproduces the same bytes from the same inputs | REFRAMED |

The honest restatement: the intelligence layer is stale in **wall-clock** (91.9
to 97.0 days at the 2026-09-02 reference) and was **ungoverned** (absent from
every manifest). It is NOT stale relative to its own inputs, so a blanket
re-run is churn, not a freshness fix. What was missing is the dating, and that
is what this row lands.

## 1. STEP 0 -- inventory of the 151 by producer

Method: for each artifact, the modules under `scripts|intel|src|api|kernel`
whose text contains the artifact's exact basename AND a write call
(`to_parquet` / `json.dump` / `write_text` / `to_pickle` / `savefig` / ...); a
single candidate wins outright, otherwise the closest name match. Reproduce
with `scripts/platformkit/mcp_server/intelligence_producers.py` (the map is the
frozen output of that scan).

| measure | n | denominator |
|---|---|---|
| artifacts with a producer | 143 | 151 |
| artifacts with no writer anywhere | 8 | 151 |
| distinct producer modules | 95 | -- |
| producers in a HUMAN-GATED tree | **0** | 95 |
| producers reading an input NEWER than their artifact | 19 | 95 |
| artifacts those 19 producers write | 30 | 151 |

**No producer is gated.** All 95 live under `scripts/` (not
`scripts/team_system/`). The 20 `intel/*.py` modules that mention
`data/intelligence` only READ these artifacts -- the single write-shaped hit,
`intel/team_three_pt_defense.py:274`, is a docstring line. So nothing in this
row required editing, or even running, a module under `intel/`, `src/`, `api/`
or `kernel/`. The NO_RUN branch for a gated producer is still built and tested,
because the next producer to land there must be named, not skipped.

The 8 artifacts with no producer at all (dated snapshots and one-off diffs):
`_pid_date_teams.pkl`, `daily_picks_2026-05-29_v2.json`,
`daily_slate_2025-02-28.json`, `int99_v1_vs_v2_diff.parquet`,
`parlay_correlation_retro_validation_v2.parquet`,
`parlay_scores_v2_legacy_calibrated.parquet`,
`player_def_archetype_sidecar_null.parquet`,
`pra_arbitrage_opportunities_2026-05-29.parquet`.

The full 151-row table (artifact, producer module, gated?, inputs read, newest
input, mtime) is section 6.

## 2. CHANGE (a) -- every artifact registered in the gate manifest

`scripts/platformkit/eval_gate/gate_manifest.py`: one discovery clause added
(`data/intelligence/**` -> `category="intelligence"`), and `_row_for` now
parses content only for `.json`/`.jsonl`. Reading a parquet as text would have
made 99 artifacts `UNREADABLE` and `exit(1)` the whole audit -- a broken
reader, not broken evidence. Registration is by file, not by parseability:
registering only the readable third would understate the layer's age exactly
where it is least visible.

**Bar: 151/151 registered with a source label -- MET.**

| category | rows | measured_at_source |
|---|---|---|
| intelligence | **151** | `field:generated_at` 5, `mtime` 146 |
| evidence | 53 | (unchanged) |
| ledger | 4 | (unchanged) |

`TOTAL=208 OK=208 EMPTY=0 UNREADABLE=0 STALE=0`, staleness 91.86 to 96.96 days
at `as_of=2026-09-02T15:12:27Z`. The 5 self-stamped artifacts are
`ai_chat_facts_v2.json`, `breakout_signals.json`, `confidence_curves.json`,
`daily_slate_2025-02-28.json`, `player_development_v2_signals.json`.

ADDITIVE, reproduced: building the manifest with the HEAD module and with the
new module at a fixed `as_of=2026-09-03T00:00:00Z` gives **59/59 pre-existing
rows identical on every key, 0 differing**; the 151 intelligence rows are
purely new. No threshold moved: `_FUTURE_TOLERANCE_DAYS` stays 1.0,
`--max-age-days` stays opt-in and unarmed.

Consequence to record honestly: `harness_health_report`'s `rows_ok` and
`gate_manifest_tool`'s `n_rows` grow from 59 to 208. Neither reader filters on
`category`, so neither breaks; the tool's status filter is the existing way to
narrow it.

## 3. CHANGE (b) -- the producer map, dry-run first

New module `scripts/platformkit/mcp_server/intelligence_producers.py` (290
LOC): the frozen artifact -> producer map, the gated/absent/out-of-scope
classification, and a subprocess runner (these builders are CLI scripts with no
importable `build()`).

`artifact_refresh.py` gains, all defaulted so the existing S24 pass is
untouched:

- `Target.no_run_reason` (optional 4th field) and a `NO_RUN` status, distinct
  from `NO_PRODUCER`. A producer that may not run is named on its row and
  counted in `n_no_run` -- never dropped from the pass.
- `_probe` mtime fallback for non-JSON artifacts (`stamp: "mtime:<iso>"`).
  Without it every parquet target reads `NO_ARTIFACT` forever and a real
  rebuild could never show as `advanced`.
- `--intelligence` (opt-in; the hourly MCP front-door pass must not start 95
  batch builders), `--scope rebuilt|all`, `--dry-run`.

Dry run, `--intelligence --dry-run`:

```
dry run -- 108 target(s), 23 runnable, 160 artifact path(s)
     23 RUN            (4 pre-existing S24 producers + 19 intelligence)
     76 NO_RUN         all one reason: "inputs older than the artifact --
                       re-running reproduces it"
      9 NO_PRODUCER    (8 orphan artifacts + tracking_program_status)
```

Run scope is `rebuilt` by default: only a producer reading an input newer than
the artifact it writes can advance anything. That is the row's own criterion
("a producer that reads a rebuilt corpus is the one that must run"), applied to
the inputs these producers actually read.

## 4. CHANGE (c) -- the measured refresh pass

Command (the 19 in-scope producers only, by name):

```
python -m scripts.platformkit.mcp_server.artifact_refresh --once --intelligence \
  --targets intel:build_clutch_cv,...,intel:test_c1_clean_backtest
started 2026-09-02T15:19:20Z -> finished 2026-09-02T15:52:26Z (33 min 6 s)
artifact refresh -- 19 target(s), 14 advanced, 5 failed, 0 no_producer, 0 no_run
```

**Bar: refreshed count printed against 151 -- 22/151 refreshed.** Per reason for
the other 129, at ARTIFACT level (the counts sum to 151 exactly):

| outcome | artifacts | producers | reason |
|---|---|---|---|
| REFRESHED | **22** | 14 | producer ran, artifact advanced |
| in scope, FAILED | 8 | 5 | named below |
| not in scope: inputs not rebuilt | 61 | 38 | newest input older than the artifact |
| not in scope: every input absent | 44 | 35 | the producer's declared inputs are not on disk |
| not in scope: no input path detected | 8 | 3 | inputs assembled at runtime, unresolvable statically |
| NO PRODUCER | 8 | -- | nothing writes them (section 1) |
| **total** | **151** | | |

GATED PRODUCERS: **0**. Nothing under `intel/`, `src/`, `api/`, `kernel/` or
`scripts/team_system/` was edited or run.

The 5 failures, each named:

| producer | artifacts | failure |
|---|---|---|
| `build_cv_fatigue_trajectories.py` | 1 | timeout at 300 s |
| `build_ingame_momentum.py` | 1 | timeout at 300 s |
| `build_lineup_chemistry.py` | 2 | timeout at 300 s |
| `build_quarter_momentum.py` | 2 | `KeyError: 'player_id'` |
| `build_tipoff_predictability.py` | 2 | `KeyError: 'player_id'` |

The two `KeyError: 'player_id'` failures are the row's real finding stated
precisely: those two builders can no longer read their own inputs, so their
four artifacts are frozen at 2026-06-02 by a schema drift nobody was told
about. That is exactly what registering the layer now surfaces. Both are named
here and left for their own row -- no producer was edited.

One defect was found and root-fixed inside this lane: the first pass returned
`UnicodeEncodeError: 'charmap' codec` from `build_clutch_cv`. The builders
print non-ASCII progress lines and the child inherited the cp1252 console
codec, so the builder died AFTER writing part of its output -- a half-refreshed
artifact reported as a clean failure. `_runner` now passes
`PYTHONIOENCODING=utf-8` to the child; the encoding belongs to the pipe, not to
the data. With the fix, 14 of 19 producers ran to completion.

Manifest AFTER the pass: `TOTAL=214 OK=214 EMPTY=0 UNREADABLE=0`, intelligence
151/151, staleness now **0.04 to 97.03 days** -- the 22 refreshed rows read
under a day, the other 129 still read 91.9 to 97.0 days, which is the honest
picture and the point of registering them.

## 5. Tests

`tests/platformkit/mcp_server/test_intelligence_producers.py` -- 7 tests:

1. all three fake intelligence files discovered with `category="intelligence"`;
2. `measured_at_source` is `field:generated_at` for the stamped one and `mtime`
   for the rest, and `measured_at` is never null;
3. a binary (parquet) artifact registers `OK` with `error=None`, not
   `UNREADABLE`;
4. a gated producer (`intel/team_paint_defense.py`) classifies NO_RUN with its
   path in the reason;
5. a NO_RUN row survives a real `refresh_once` pass: status `NO_RUN` (not
   `NO_PRODUCER`), reason on the row, `n_no_run == 1`, target not dropped;
6. absent and out-of-scope producers each get their own named reason;
7. the map covers 143 + 8 = 151 artifacts with no artifact claimed twice.

Regression, run per file in master:

| file | result |
|---|---|
| `tests/platformkit/mcp_server/test_intelligence_producers.py` | 7 passed |
| `tests/platformkit/mcp_server/test_artifact_refresh.py` | 7 passed |
| `scripts/platformkit/eval_gate/test_gate_manifest.py` + `test_gate_manifest_measured_at.py` | 20 passed |
| `scripts/platformkit/mcp/test_gate_manifest_tool.py` + `test_harness_health_report.py` + `test_ledger_backup.py` | 16 passed |

## 6. Inventory table -- all 151

| # | artifact (data/intelligence/) | producer module | gated? | inputs read (n) | newest input | mtime |
|---|---|---|---|---|---|---|
| 1 | `_pid_date_teams.pkl` | `-- NONE --` | n/a | none detected | - | 2026-06-02 |
| 2 | `absence_cv_impact.parquet` | `scripts/build_absence_impact.py` | no | 6 (4 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 3 | `active_trend_signals.json` | `scripts/build_ai_chat_corpus.py` | no | none detected | - | 2026-06-02 |
| 4 | `ai_chat_facts.json` | `scripts/build_ai_chat_facts_v2.py` | no | none detected | - | 2026-06-02 |
| 5 | `ai_chat_facts_v2.json` | `scripts/build_ai_chat_facts_v2.py` | no | none detected | - | 2026-06-02 |
| 6 | `ai_chat_index.json` | `scripts/build_ai_chat_corpus.py` | no | none detected | - | 2026-06-02 |
| 7 | `anomaly_log.parquet` | `scripts/build_anomaly_intel.py` | no | 4 (3 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 8 | `anti_correlation_parlay_candidates.parquet` | `scripts/build_daily_picks.py` | no | 1 (1 absent) | - | 2026-06-02 |
| 9 | `archetype_drift.parquet` | `scripts/build_archetype_drift.py` | no | 9 (8 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 10 | `archetype_drift_signals.json` | `scripts/build_archetype_drift.py` | no | 9 (8 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 11 | `archetype_label_sidecar.parquet` | `scripts/int95_per_archetype_residual.py` | no | 4 (4 absent) | - | 2026-06-02 |
| 12 | `archetype_outlier_signals.parquet` | `scripts/build_archetype_outlier_signal.py` | no | 11 (10 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 13 | `archetype_scheme_advantages.json` | `scripts/build_archetype_scheme_matrix.py` | no | 4 (4 absent) | - | 2026-06-02 |
| 14 | `archetype_scheme_interactions.parquet` | `scripts/build_archetype_scheme_matrix.py` | no | 4 (4 absent) | - | 2026-06-02 |
| 15 | `atlas_features_sidecar.parquet` | `scripts/prop_pergame_walk_forward_atlas.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 16 | `atlas_redundancy_matrix.parquet` | `scripts/diagnose_atlas_redundancy.py` | no | 1 (1 absent) | - | 2026-06-02 |
| 17 | `bench_starter_signatures.json` | `scripts/build_bench_starter_split.py` | no | 4 (2 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 18 | `bench_starter_split.parquet` | `scripts/build_bench_starter_split.py` | no | 4 (2 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 19 | `blk_residual_head_v1.parquet` | `scripts/int90_blk_residual_head.py` | no | 7 (5 absent) | 2026-06-02T18:30:31 **NEWER** | 2026-06-02 |
| 20 | `bookmaker_consistency.parquet` | `scripts/check_bookmaker_consistency.py` | no | 1 (0 absent) | 2026-05-27T23:47:02 | 2026-06-02 |
| 21 | `breakout_signals.json` | `scripts/build_ai_chat_corpus.py` | no | none detected | - | 2026-06-02 |
| 22 | `built_signals_sidecar.parquet` | `scripts/prop_pergame_walk_forward_built.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 23 | `c1_clean_backtest_results.json` | `scripts/test_c1_clean_backtest.py` | no | 8 (3 absent) | 2026-06-26T18:37:18 **NEWER** | 2026-06-02 |
| 24 | `clutch_cv_split.parquet` | `scripts/build_clutch_cv.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 25 | `clutch_rankings.json` | `scripts/build_clutch_cv.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 26 | `coaching_adjustments.parquet` | `scripts/build_coaching_adjustments.py` | no | 7 (3 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 27 | `compound_candidates.parquet` | `scripts/build_ai_chat_facts_v2.py` | no | none detected | - | 2026-06-02 |
| 28 | `compound_signal_hunt_v3.parquet` | `scripts/hunt_compound_signals_v3.py` | no | 19 (19 absent) | - | 2026-06-02 |
| 29 | `compound_signal_hunt_v4.parquet` | `scripts/hunt_compound_signals_v4.py` | no | 20 (20 absent) | - | 2026-06-02 |
| 30 | `confidence_curves.json` | `scripts/build_confidence_intervals.py` | no | 4 (3 absent) | 2026-05-26T06:52:57 | 2026-06-02 |
| 31 | `confidence_ensemble.parquet` | `scripts/build_confidence_ensemble.py` | no | 6 (6 absent) | - | 2026-06-02 |
| 32 | `current_form_profiles.parquet` | `scripts/build_current_form.py` | no | 6 (3 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 33 | `cv_anomaly_v2_validation.json` | `scripts/build_cv_anomaly_v2.py` | no | 7 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 34 | `cv_consistency_eval.json` | `scripts/eval_kelly_with_cv_consistency.py` | no | 5 (5 absent) | - | 2026-06-02 |
| 35 | `cv_consistency_kelly.parquet` | `scripts/build_cv_consistency_kelly.py` | no | 3 (2 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 36 | `cv_coverage_gates.parquet` | `scripts/build_cv_coverage_gates.py` | no | 7 (4 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 37 | `cv_coverage_interactions.parquet` | `scripts/build_cv_coverage_interactions.py` | no | 2 (1 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 38 | `cv_fatigue_trajectories.parquet` | `scripts/build_cv_fatigue_trajectories.py` | no | 6 (2 absent) | 2026-09-01T14:28:10 **NEWER** | 2026-06-02 |
| 39 | `cv_pace_features_sidecar.parquet` | `scripts/build_cv_pace_features.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 40 | `cv_pace_per_game.parquet` | `scripts/build_cv_pace_features.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 41 | `cv_quality_confidence_curves.json` | `scripts/build_cv_quality_confidence.py` | no | none detected | - | 2026-06-02 |
| 42 | `cv_quality_per_game.parquet` | `scripts/build_cv_quality_confidence.py` | no | none detected | - | 2026-06-02 |
| 43 | `cv_shot_clock_features_sidecar.parquet` | `scripts/build_cv_shot_clock_features_sidecar.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 44 | `cv_shot_clock_per_game.parquet` | `scripts/build_cv_shot_clock_features.py` | no | 5 (2 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 45 | `cv_shot_range_features_sidecar.parquet` | `scripts/build_cv_shot_range_features.py` | no | 3 (3 absent) | - | 2026-06-02 |
| 46 | `cv_shot_range_per_game.parquet` | `scripts/build_cv_shot_range_features.py` | no | 3 (3 absent) | - | 2026-06-02 |
| 47 | `cv_shot_type_features_sidecar.parquet` | `scripts/build_cv_shot_type_features.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 48 | `cv_shot_types_per_game.parquet` | `scripts/build_cv_shot_types.py` | no | 6 (1 absent) | 2026-09-01T14:28:10 **NEWER** | 2026-06-02 |
| 49 | `daily_picks_2026-05-29.json` | `scripts/build_player_betting_profile.py` | no | 5 (5 absent) | - | 2026-06-02 |
| 50 | `daily_picks_2026-05-29_v2.json` | `-- NONE --` | n/a | none detected | - | 2026-06-02 |
| 51 | `daily_picks_retro_2026-04-25_to_2026-05-24.parquet` | `scripts/run_daily_picks_retro.py` | no | 3 (0 absent) | 2026-09-02T14:45:50 **NEWER** | 2026-06-02 |
| 52 | `daily_picks_retro_v1_vs_v2_comparison.parquet` | `scripts/run_daily_picks_retro_v2.py` | no | 3 (0 absent) | 2026-09-02T14:45:50 **NEWER** | 2026-06-02 |
| 53 | `daily_slate_2025-02-28.json` | `-- NONE --` | n/a | none detected | - | 2026-06-02 |
| 54 | `defensive_schemes.parquet` | `scripts/build_defensive_schemes.py` | no | 1 (0 absent) | 2026-05-24T23:59:00 | 2026-06-02 |
| 55 | `dow_cv_profiles.parquet` | `scripts/build_time_of_day_cv.py` | no | 12 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 56 | `dow_signals.json` | `scripts/build_time_of_day_cv.py` | no | 12 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 57 | `form_vs_baseline_deltas.json` | `scripts/build_current_form.py` | no | 6 (3 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 58 | `ft_rate_predictions.parquet` | `scripts/build_ft_rate_model.py` | no | 12 (9 absent) | 2026-05-24T23:14:53 | 2026-06-02 |
| 59 | `game_neighbors.json` | `scripts/build_game_similarity.py` | no | 5 (2 absent) | 2026-08-31T23:00:54 **NEWER** | 2026-06-02 |
| 60 | `game_similarity_index.parquet` | `scripts/build_game_similarity.py` | no | 5 (2 absent) | 2026-08-31T23:00:54 **NEWER** | 2026-06-02 |
| 61 | `garbage_time_player_aggregates.parquet` | `scripts/build_garbage_time_gates.py` | no | 4 (2 absent) | 2026-05-24T23:14:53 | 2026-06-02 |
| 62 | `garbage_time_segments.parquet` | `scripts/build_garbage_time_gates.py` | no | 4 (2 absent) | 2026-05-24T23:14:53 | 2026-06-02 |
| 63 | `gt_weighted_forms.parquet` | `scripts/build_gt_weighted_forms.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 64 | `h1_h2_projections.parquet` | `scripts/build_h1_to_h2_projection.py` | no | 8 (4 absent) | 2026-05-26T06:52:57 | 2026-06-02 |
| 65 | `h2_projection_signals.json` | `scripts/build_h1_to_h2_projection.py` | no | 8 (4 absent) | 2026-05-26T06:52:57 | 2026-06-02 |
| 66 | `ingame_momentum.parquet` | `scripts/build_ingame_momentum.py` | no | 6 (1 absent) | 2026-09-01T14:28:10 **NEWER** | 2026-06-02 |
| 67 | `int60_validation_results.json` | `scripts/validate_cv_coverage_interactions.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 68 | `int99_v1_vs_v2_diff.parquet` | `-- NONE --` | n/a | none detected | - | 2026-06-02 |
| 69 | `int_v8_results.json` | `scripts/test_int41_int23_compound_v8.py` | no | 5 (0 absent) | 2026-05-27T23:40:21 | 2026-06-02 |
| 70 | `lineup_chemistry.parquet` | `scripts/build_lineup_chemistry.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 71 | `lineup_signatures.json` | `scripts/build_lineup_chemistry.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 72 | `matchup_deviations.parquet` | `scripts/build_matchup_intel.py` | no | 6 (5 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 73 | `matchup_grid.parquet` | `scripts/build_matchup_grid.py` | no | 4 (4 absent) | - | 2026-06-02 |
| 74 | `momentum_signals.parquet` | `scripts/build_momentum_signals.py` | no | 1 (1 absent) | - | 2026-06-02 |
| 75 | `multitask_residual_head_predictions.parquet` | `scripts/int116_wrapper.py` | no | 3 (3 absent) | - | 2026-06-02 |
| 76 | `non_gt_forms_sidecar.parquet` | `scripts/build_non_gt_rolling_features.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 77 | `officials_cv_impact.parquet` | `scripts/build_officials_cv_impact.py` | no | 6 (3 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 78 | `officials_player_sensitivity.parquet` | `scripts/build_officials_cv_impact.py` | no | 6 (3 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 79 | `officials_signals.json` | `scripts/build_officials_cv_impact.py` | no | 6 (3 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 80 | `opp_defensive_intensity.parquet` | `scripts/build_opp_defensive_intensity.py` | no | 6 (4 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 81 | `opp_minutes_predictions.parquet` | `scripts/build_opp_minutes_v2.py` | no | 8 (6 absent) | 2026-05-26T06:52:57 | 2026-06-02 |
| 82 | `opp_normalized_cv.parquet` | `scripts/build_opp_normalized_cv.py` | no | 7 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 83 | `opp_paint_allowance.parquet` | `scripts/build_opp_paint_allowance.py` | no | 6 (5 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 84 | `opponent_imposed_profiles.json` | `scripts/build_matchup_intel.py` | no | 6 (5 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 85 | `pace_adjusted_cv.parquet` | `scripts/build_pace_adjusted_cv.py` | no | 5 (2 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 86 | `pace_adjusted_rankings.json` | `scripts/build_pace_adjusted_cv.py` | no | 5 (2 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 87 | `pair_chemistry.parquet` | `scripts/build_pair_chemistry.py` | no | 3 (3 absent) | - | 2026-06-02 |
| 88 | `pair_signatures.json` | `scripts/build_pair_chemistry.py` | no | 3 (3 absent) | - | 2026-06-02 |
| 89 | `parlay_correlation_retro_buckets.parquet` | `scripts/validate_parlay_correlation_retro.py` | no | 9 (9 absent) | - | 2026-06-02 |
| 90 | `parlay_correlation_retro_validation.parquet` | `scripts/validate_parlay_correlation_retro.py` | no | 9 (9 absent) | - | 2026-06-02 |
| 91 | `parlay_correlation_retro_validation_v2.parquet` | `-- NONE --` | n/a | none detected | - | 2026-06-02 |
| 92 | `parlay_scores_v2_demo.parquet` | `scripts/build_daily_picks.py` | no | 1 (1 absent) | - | 2026-06-02 |
| 93 | `parlay_scores_v2_demo_with_calibration.parquet` | `scripts/score_multi_leg_v2.py` | no | 7 (7 absent) | - | 2026-06-02 |
| 94 | `parlay_scores_v2_legacy_calibrated.parquet` | `-- NONE --` | n/a | none detected | - | 2026-06-02 |
| 95 | `per_archetype_residual_v1.parquet` | `scripts/int95_per_archetype_residual.py` | no | 4 (4 absent) | - | 2026-06-02 |
| 96 | `per_book_edge_audit_2026-05-29.parquet` | `scripts/build_player_betting_profile.py` | no | 5 (5 absent) | - | 2026-06-02 |
| 97 | `per_player_calibration.parquet` | `scripts/build_per_player_calibration.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 98 | `per_player_confidence.parquet` | `scripts/build_daily_slate.py` | no | 5 (5 absent) | - | 2026-06-02 |
| 99 | `player_archetype_definitions.json` | `scripts/build_player_atlas.py` | no | 7 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 100 | `player_atlas_feature_list.json` | `scripts/build_player_atlas.py` | no | 7 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 101 | `player_atlas_viz.png` | `scripts/build_player_atlas.py` | no | 7 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 102 | `player_betting_profile.parquet` | `scripts/build_player_betting_profile.py` | no | 5 (5 absent) | - | 2026-06-02 |
| 103 | `player_def_archetype_sidecar.parquet` | `scripts/build_player_def_archetype.py` | no | 3 (3 absent) | - | 2026-06-02 |
| 104 | `player_def_archetype_sidecar_null.parquet` | `-- NONE --` | n/a | none detected | - | 2026-06-02 |
| 105 | `player_development.parquet` | `scripts/build_player_development.py` | no | 7 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 106 | `player_development_v2.parquet` | `scripts/build_player_development_v2.py` | no | 6 (5 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 107 | `player_development_v2_signals.json` | `scripts/build_player_development_v2.py` | no | 6 (5 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 108 | `player_fingerprints.parquet` | `scripts/build_player_atlas.py` | no | 7 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 109 | `player_fingerprints_kbest.parquet` | `scripts/refit_atlas_k_sweep.py` | no | 5 (5 absent) | - | 2026-06-02 |
| 110 | `player_opp_splits_sidecar.parquet` | `scripts/build_player_opp_splits.py` | no | 1 (1 absent) | - | 2026-06-02 |
| 111 | `player_similarity.parquet` | `scripts/build_player_similarity.py` | no | 4 (4 absent) | - | 2026-06-02 |
| 112 | `pos_vs_pos_matchups.parquet` | `scripts/build_position_vs_position.py` | no | 3 (2 absent) | 2026-05-24T23:14:53 | 2026-06-02 |
| 113 | `pos_vs_pos_signals.json` | `scripts/build_position_vs_position.py` | no | 3 (2 absent) | 2026-05-24T23:14:53 | 2026-06-02 |
| 114 | `position_scheme_interactions.parquet` | `scripts/build_position_scheme_matrix.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 115 | `position_scheme_signals.json` | `scripts/build_position_scheme_matrix.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 116 | `possession_type_profiles.parquet` | `scripts/build_possession_type_intel.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 117 | `possession_type_signatures.json` | `scripts/build_possession_type_intel.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 118 | `pra_arbitrage_opportunities_2026-05-29.parquet` | `-- NONE --` | n/a | none detected | - | 2026-06-02 |
| 119 | `pts_decomposition_predictions.parquet` | `scripts/train_pts_decomposition.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 120 | `q1_extrapolation_signals.parquet` | `scripts/build_q1_extrapolation_signals.py` | no | 5 (1 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 121 | `quarter_profiles.parquet` | `scripts/build_quarter_momentum.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 122 | `quarter_signatures.json` | `scripts/build_quarter_momentum.py` | no | 4 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 123 | `rest_cv_impact.parquet` | `scripts/build_rest_cv_intel.py` | no | 5 (2 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 124 | `rest_cv_signatures.json` | `scripts/build_rest_cv_intel.py` | no | 5 (2 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 125 | `retro_bet_audit.parquet` | `scripts/audit_retro_bets.py` | no | 10 (10 absent) | - | 2026-06-02 |
| 126 | `rolling_trends.parquet` | `scripts/build_rolling_trends.py` | no | 4 (2 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 127 | `schedule_strength_7d.parquet` | `scripts/build_schedule_strength.py` | no | 2 (1 absent) | 2026-05-24T23:59:00 | 2026-06-02 |
| 128 | `scheme_indicators.json` | `scripts/build_defensive_schemes.py` | no | 1 (0 absent) | 2026-05-24T23:59:00 | 2026-06-02 |
| 129 | `sequential_patterns.parquet` | `scripts/build_sequential_possession.py` | no | 6 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 130 | `sequential_signatures.json` | `scripts/build_sequential_possession.py` | no | 6 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 131 | `shot_clock_buckets.parquet` | `scripts/build_shot_clock_buckets.py` | no | 5 (2 absent) | 2026-09-01T14:28:10 **NEWER** | 2026-06-02 |
| 132 | `shot_clock_player_profiles.json` | `scripts/build_shot_clock_buckets.py` | no | 5 (2 absent) | 2026-09-01T14:28:10 **NEWER** | 2026-06-02 |
| 133 | `shot_quality_live_validation.json` | `scripts/eval_live_shot_quality.py` | no | 2 (2 absent) | - | 2026-06-02 |
| 134 | `similar_neighbors.json` | `scripts/build_similarity_engine.py` | no | 3 (2 absent) | 2026-04-24T00:55:45 | 2026-06-02 |
| 135 | `similarity_matrix.parquet` | `scripts/build_similarity_engine.py` | no | 3 (2 absent) | 2026-04-24T00:55:45 | 2026-06-02 |
| 136 | `star_absence_effects.json` | `scripts/build_absence_impact.py` | no | 6 (4 absent) | 2026-05-27T07:22:01 | 2026-06-02 |
| 137 | `stat_correlation_matrix.parquet` | `scripts/build_stat_correlations.py` | no | 3 (3 absent) | - | 2026-06-02 |
| 138 | `streak_excluded_players.json` | `scripts/build_streak_signatures.py` | no | 5 (4 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 139 | `streak_signatures.parquet` | `scripts/build_streak_signatures.py` | no | 5 (4 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 140 | `streak_signatures_summary.json` | `scripts/build_streak_signatures.py` | no | 5 (4 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 141 | `team_adjustment_tendencies.json` | `scripts/build_coaching_adjustments.py` | no | 7 (3 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 142 | `team_change_log.json` | `scripts/build_trade_intel.py` | no | 6 (2 absent) | 2026-09-01T14:28:10 **NEWER** | 2026-06-02 |
| 143 | `team_tempo_spacing.parquet` | `scripts/build_team_tempo_spacing.py` | no | 8 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 144 | `teammate_correlation.parquet` | `scripts/build_teammate_correlation.py` | no | 4 (4 absent) | - | 2026-06-02 |
| 145 | `time_of_day_cv.parquet` | `scripts/build_time_of_day_cv.py` | no | 12 (6 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 146 | `tipoff_predictability.parquet` | `scripts/build_tipoff_predictability.py` | no | 3 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 147 | `tipoff_predictability_signals.json` | `scripts/build_tipoff_predictability.py` | no | 3 (2 absent) | 2026-09-01T14:28:09 **NEWER** | 2026-06-02 |
| 148 | `trade_profile_shifts.parquet` | `scripts/build_trade_intel.py` | no | 6 (2 absent) | 2026-09-01T14:28:10 **NEWER** | 2026-06-02 |
| 149 | `v6_simulation_results.json` | `scripts/simulate_v6_deployment.py` | no | 5 (1 absent) | 2026-05-27T23:40:21 | 2026-06-02 |
| 150 | `v8_clean_subset_results.json` | `scripts/test_v8_clean_subset.py` | no | 1 (0 absent) | 2026-05-29T04:54:12 | 2026-06-02 |
| 151 | `v9_unified_results.json` | `scripts/test_v8_clean_subset.py` | no | 1 (0 absent) | 2026-05-29T04:54:12 | 2026-06-02 |

## 7. NOT VERIFIED

- **The producer map is a text scan, not a traced write.** A producer was
  attributed by "exact basename + a write call in the same module"; a module
  that builds its output path from fragments would be missed, and where several
  modules mention one artifact the closest name match wins. 63 of 143
  attributions had exactly one candidate; the rest were disambiguated by name.
  No attribution was confirmed by running the producer and watching the file.
- **Input lists are a regex over path literals**, so a builder reading a path
  assembled at runtime is undercounted. The `input_newer_than_artifact` split
  (19 / 76) rests on those lists.
- **The 8 no-producer artifacts** were not proven producerless -- only that no
  module under `scripts|intel|src|api|kernel` names them beside a write.
- **Artifact CONTENT was never opened**: no intelligence artifact was scored,
  joined to a corpus, or checked against a close. This row dates them; it makes
  no claim about whether any of them carries signal.
- **`assert_fresh` is NOT armed** on the intelligence category. 146/151 rows are
  mtime-sourced, so arming it unscoped would block the layer wholesale (the
  S45(c) situation, one category wider). Producer `generated_at` stamps come
  first.
- **The 3 timeouts were not retried at a longer limit.** 300 s is a knob, not
  a bar; whether those builders finish in 20 minutes or hang forever is
  unmeasured, so they are recorded as timeouts, not as broken.
- **The two `KeyError: 'player_id'` builders were not diagnosed.** The
  failure is reproduced and named; which input lost the column, and whether
  their four artifacts are recoverable at all, is a separate row.
- **129 of 151 artifacts remain at their 2026-06-02 content.** This row makes
  that visible and dated; it does not fix it, and 61 of them are provably not
  fixable by re-running (their inputs never moved).
- **No OS scheduler task was armed** (S24's rule stands), and the pod was not
  touched.

## 8. Contract self-check

B1 no metric excludes its own failures -- the denominator is all 151.
B2 additive: 59/59 pre-existing manifest rows identical; `no_run_reason`
defaults to None so every existing `Target` is unchanged.
B3 an unregistrable artifact is registered mtime-labelled, never dropped; a
producer that may not run is NO_RUN by name, never skipped.
B4 no claimable queue introduced. B5 nothing copied to the pod.
B6 no module moved or retired. B7 the table is the full 151, not a head slice.
B8 no fit, no residual. B9 the denominator is 151 distinct files.
B10 no bar or threshold changed.
Q1-Q2 no scored comparison, no prereg needed, no ledger charge (K untouched).
Q3 no bar moved. Q4 nothing scored OOS. Q5 no AHEAD claimed.
Q6 calibration language only; no retracted figure appears. The single `edge`
token in the memo (`per_book_edge_audit.parquet`, section 6) is a pre-existing
filename on disk being inventoried, not a claim.
Q7 `n = 151 (CONSTRUCT)` -- every file under `data/intelligence` is enumerated,
so the enumeration is the whole set. Q8 premise re-measured in section 0 and
partly FALSIFIED, reported as the result.
