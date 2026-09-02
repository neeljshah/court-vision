# S53 -- soccer gate-spine as-of enrichment + S22 soccer re-run (ACCEPT)

Gap (register): the soccer gate corpus carries only 11 pregame shots/SOT as-of
columns, so all 15 soccer mechanisms are NOT_TESTABLE against the close (S22);
the ingredients exist on disk but are not joined into the gate spine. Enrich the
spine additively, same 25,834 rows, `event_date` order, then re-run S22's soccer
engine.

Calibration language only. DESCRIPTIVE_ONLY. Nothing scored, promoted or charged
-- `data/cache/eval_gate/backtest_fwer.jsonl` was never opened and no
`_charge_ledger` path exists in anything this lane touched.

## STEP 0 -- what each of the 15 soccer mechanisms needs, and who carries it

Denominator for every join rate below: **25,834** corpus rows.

| # | mechanism (slug prefix) | ingredient column it needs | on-disk carrier | join key | joinable AS-OF? |
|---|---|---|---|---|---|
| 1 | `team_time_score_state_conditioned_shot_model` | `score_state`, `time_bucket` per shot | StatsBomb event cache -- no match-grain parquet | -- | NO (event grain) |
| 2 | `first_goal_timing_predicts_final_result` | first-goal minute (+ `ftr`) | StatsBomb event grain; `ftr` on `matches.parquet` | event_id | NO -- minute is in-match; `ftr` is same-match (LEAKY) |
| 3 | `leading_team_defensive_shell` | `score_state` + shots/min | StatsBomb event grain | -- | NO (event grain) |
| 4 | `set_piece_vs_open_play_shot_conversion` | `shot.type.name` share | StatsBomb shot grain | -- | NO (shot grain) |
| 5 | `pressing_intensity_ppda_proxy` | `ppda` | recomputed in memory by `validate_pressing_defense.py`, never persisted | -- | NO (not on disk) |
| 6 | `goalkeeper_distribution_style` | goal-kick pass height | StatsBomb event grain | -- | NO (event grain) |
| 7 | `formation_change_mid_match_impact` | Tactical Shift event | StatsBomb event grain | -- | NO (event grain) |
| 8 | `home_advantage_..._neutral_venues` | `neutral` | `data/domains/soccer_intl/results.parquet` | date+teams | NO -- **0 of 49,477** intl rows share a (date, home_team, away_team) with the 25,834 corpus matches |
| 9 | `neutral_venue_split_replicates_across_era` | `neutral` + era | same | date+teams | NO -- same 0 overlap |
| 10 | `tournament_competitive_context_..._friendlies` | `tournament` | same | date+teams | NO -- same 0 overlap |
| 11 | `trailing_xg_supremacy_is_a_stable_team_trait` | `diff_xg_supremacy_asof` | **`data/domains/soccer/asof_xg_proxy.parquet`** | **event_id** | **YES -- 25,708 / 25,834 = 0.995123** |
| 12 | `first_substitution_timing` | substitution minute | StatsBomb event grain | -- | NO (event grain) |
| 13 | `trailing_team_shot_rate_vs_tied` | `score_state` | StatsBomb event grain | -- | NO (event grain) |
| 14 | `xg_additivity_..._shot_rebound_clusters` | `possession_id` + per-shot `statsbomb_xg` | StatsBomb shot grain | -- | NO (shot grain) |
| 15 | `defensive_block_depth_..._counterattack_share` | event-grain compactness + `play_pattern` | StatsBomb event grain | -- | NO (event grain) |

**Joinable as-of: 1 of 15.** Eleven need a grain (event / shot / possession) that
exists nowhere on disk at match grain. Three (#8, #9, #10) name a real on-disk
column, `neutral` / `tournament` on `soccer_intl/results.parquet`, that cannot be
joined at all: the international frame and the six domestic-league corpus_units
are DISJOINT universes -- measured this session, `0` shared (date, home_team,
away_team) keys out of 49,477 x 25,834. #2 could take `ftr` from
`matches.parquet` but that is the match's own result: excluded as leaky.

### Excluded as LEAKY, named (same-match or match-containing aggregates)

| parquet | rows / key | the columns refused | why |
|---|---|---|---|
| `soccer/match_stats.parquet` | 25,834 / event_id | `home_shots` `away_shots` `home_sot` `away_sot` `home_corners` `away_corners` `home_fouls` `away_fouls` `home_yellow` `away_yellow` `home_red` `away_red` `total_shots` `total_sot` `home_sot_ratio` `away_sot_ratio` `hthg` `htag` `htr` | FINAL / half-time counts of the match being scored |
| `soccer/referee_card_foul_profiles.parquet` | 10,251 / event_id | `total_fouls` `total_yellow` `total_red` `total_cards` | that MATCH's own card+foul totals, not a prior-referee aggregate (also only 10,251/25,834 = 0.3968 coverage, and its source has a blank-referee placeholder on 15,583 rows) |
| `soccer/style_fingerprints.parquet` | 1,336 / team+season | `shot_share` `sot_ratio` `fouls_committed_pm` `fouls_drawn_pm` `corners_pm` `cards_pm` `ppg` | WHOLE-SEASON team aggregates that CONTAIN the match being scored |
| `soccer/postmortem.parquet` | 25,834 / event_id | `finishing_residual_home` `finishing_residual_away` `sot_diff` | post-match by construction |
| `soccer/matches.parquet` | 25,834 / event_id | `fthg` `ftag` `total_goals` `target_over25` `ftr` | the label itself |

All of these names are now in `corpus_cache.SOCCER_LEAKY_COLUMNS`; `_asof_only`
raises `ValueError` naming any one of them before it can reach the spine.

Not built and not claimed: a DATE-LAGGED referee card profile or a PRIOR-SEASON
style fingerprint would each be a legal as-of ingredient, but each is a new
derivation rather than a join of something already on disk, and no mechanism in
the ledger names one. Filed as a NEW GAP below, not silently attempted.

## CHANGE -- additive, soccer branch only

`scripts/platformkit/combo/corpus_cache.py`, `_build_soccer` only (LANE W's
tennis branch untouched; mlb and nba builders untouched):

- `asof_xg_proxy.parquet` added as a third source; its nine as-of xG-PROXY
  columns joined on `event_id`. `home_n_prior` / `away_n_prior` already arrive
  from `asof_features` and are deliberately NOT re-joined, so nothing is
  overwritten.
- the eight `asof_features` as-of columns the builder already read and then
  selected out are now kept.
- `SOCCER_LEAKY_COLUMNS` + `_asof_only()` refuse a same-match column by name.
- `build_gate_corpus` writes a `provenance` dict into the sidecar and
  `freshness_report` surfaces it (both additive; a builder returning the old
  2-tuple gets `{}`).

| fact | before | after |
|---|---|---|
| rows | 25,834 | 25,834 |
| columns | 16 | 33 (+17, **0 removed, 0 renamed**) |
| pre-existing columns `DataFrame.equals` | -- | **True** (0 of 16 changed) |
| `event_date` | monotonic, 0 null, 2015-08-07..2026-05-24 | identical |
| `freshness_report` | `stale False`, `order_basis event_date` | `stale False`, `order_basis event_date`, 3 sources |

Rebuild wall time 0.9 s.

### Provenance (sidecar), every rate against the 25,834 denominator

| new column | source parquet | join key | joined / 25,834 | rate |
|---|---|---|---|---|
| `home_sot_for_asof` `home_sot_against_asof` `home_shots_for_asof` `home_shots_against_asof` | `data/domains/soccer/asof_features.parquet` | event_id | 25,752 | 0.996826 |
| `away_sot_for_asof` `away_sot_against_asof` `away_shots_for_asof` `away_shots_against_asof` | `data/domains/soccer/asof_features.parquet` | event_id | 25,729 | 0.995936 |
| `home_xg_for_asof` `home_xg_against_asof` `home_xg_supremacy_asof` | `data/domains/soccer/asof_xg_proxy.parquet` | event_id | 25,752 | 0.996826 |
| `away_xg_for_asof` `away_xg_against_asof` `away_xg_supremacy_asof` | `data/domains/soccer/asof_xg_proxy.parquet` | event_id | 25,729 | 0.995936 |
| `diff_xg_for_asof` `diff_xg_against_asof` `diff_xg_supremacy_asof` | `data/domains/soccer/asof_xg_proxy.parquet` | event_id | 25,708 | 0.995123 |

The missing rows are debuts (prior-only as-of columns are NaN on a team's first
match in the corpus), not join failures: 25,834 / 25,834 event_ids match.

## S22 soccer re-run -- tally 15 NOT_TESTABLE -> 14 NOT_TESTABLE + 1 NULL_LOCAL

`mechanism_wiring_soccer.py` gains a `TRIGGERS` dict carrying the one row whose
ingredient is now a spine column; the other fourteen keep their declared absence
verbatim. Bars unmoved (`|effect| >= 0.02 AND p < 0.01`, coverage >= 0.25,
>= 30 rows a side -- byte-identical to S22).

| sport | wired/defined | with trigger | CONFIRMED_LOCAL | NULL_LOCAL | NOT_TESTABLE |
|---|---|---|---|---|---|
| soccer BEFORE (S22) | 15/15 | 0 | 0 | 0 | 15 |
| soccer AFTER (S53) | 15/15 | **1** | 0 | **1** | **14** |

`out/mechanism_exposure.json` unchanged: soccer wired 15 / not_wired 0 (nba 27,
mlb 22, tennis 23 untouched).

The one scored row, `trailing_xg_supremacy_is_a_stable_team_trait`, trigger
`diff_xg_supremacy_asof`, coverage 0.9977, n = 16,284 across all six league
corpus_units:

| corpus_unit | n | effect | p |
|---|---|---|---|
| D1 | 2,134 | +0.017806 | 0.387422 |
| E0 | 2,660 | +0.010903 | 0.566369 |
| E1 | 3,855 | -0.035260 | 0.026981 |
| F1 | 2,329 | +0.028088 | 0.165919 |
| I1 | 2,651 | -0.016884 | 0.377917 |
| SP1 | 2,655 | +0.024770 | 0.190761 |

**NULL_LOCAL.** No unit clears both bars and the signs are mixed (three up,
three down) -- the expected and honest outcome for a single as-of column against
the strongest available forecast. Nothing here is or claims to be a beat of the
close.

A2 reproduction, recomputed independently of the module from
`gate_corpus_states` + `load_gate_corpus` directly: all six unit rows above are
byte-identical to the artifact, and the scored total 16,284 matches.

## Test

New `scripts/platformkit/combo/test_corpus_cache_soccer_enrich.py` --
**5 passed in 5.18 s**. Real sources, tmp cache dir, no mocks:

1. rebuild is additive -- the 16 pre-S53 columns are present in their exact
   original order at the front of the frame and `DataFrame.equals` the cached
   corpus on all of them, 25,834 rows both sides;
2. exactly the 17 new columns appear, each at its printed non-null count;
3. the sidecar `provenance` names each new column's source parquet, `event_id`
   join key, `n_rows == 25834` and a `join_rate` equal to `n_joined / 25834`;
4. `_asof_only` raises `ValueError` NAMING a same-match column
   (`home_shots`, `fthg`, `total_cards`, `shot_share` each checked) and passes an
   as-of one through;
5. no member of `SOCCER_LEAKY_COLUMNS` reached the built spine.

Regression, all per-file, all in MASTER:

```
test_corpus_cache_freshness.py    -> 10 passed   (S41/S44, unchanged)
test_mechanism_close_effect.py    -> 15 passed
test_mechanism_wiring.py          -> 16 passed
test_close_join_soccer.py + test_mechanism_exposure.py + test_calibration_report.py -> 14 passed
```

## ACCEPTANCE

metric = soccer mechanisms whose declared ingredient is a column of the scored
corpus; denominator = 15. before = **0/15**. after = **1/15**, which is every
one the on-disk ingredients honestly allow (11 need a grain absent from disk, 3
name a column on a corpus with 0 shared keys, 1 is leaky-only).
n = 25,834 corpus rows; 16,284 scored rows on the one trigger.
must not move: every pre-existing column and value (`DataFrame.equals` True on
all 16), the row count (25,834), `event_date` order, the S22 bars,
`data/registry/**` (untouched), `data/cache/eval_gate/backtest_fwer.jsonl`
(never opened). No rename, no removal, no bar moved, no flag flipped.

## NEW GAP

`NEW GAP: two soccer as-of ingredients are derivable but not derived -- a
DATE-LAGGED referee card/foul profile (referee_card_foul_profiles.parquet holds
each match's OWN totals, so a prior-matches-only expanding mean per referee is
needed, and its source has a blank-referee placeholder on 15,583 of 25,834 rows)
and a PRIOR-SEASON style fingerprint (style_fingerprints.parquet is a whole-
season aggregate containing the match, so only the team's previous season is
legal). Neither is named by any of the 15 soccer mechanisms, so neither was
built here; both would widen the legal candidate surface for the foundry.`

## NOT VERIFIED

- The xG family is a SHOTS-BASED PROXY (`K_SOT=0.33`, `K_OFF=0.03`), not true
  xG. Its leak-free / prior-only property is taken from
  `domains.soccer.asof_xg_proxy`'s own construction (`asof_common` snapshot-
  before-update); it was NOT independently re-audited row by row here.
- The NULL_LOCAL row is a WHOLE-CORPUS median split. No walk-forward, no
  purging, no embargo, no CPCV -- Q4's leak contract does not apply to it and it
  cannot be read as an out-of-sample result. The close carries a SYNTHETIC
  vintage (S34), so any leak check over these states passes by construction.
- The mechanism's own ledger claim is a SPLIT-HALF PERSISTENCE property of the
  trait. The corpus-grain rendering measured here is the trait LEVEL against the
  close residual -- a declared rendering, not the ledger's persistence
  statistic. A NULL here does not refute the persistence claim.
- The other 16 new columns were joined and provenanced but NOT measured against
  anything; no mechanism names them.
- The rebuild adds `asof_xg_proxy.parquet` to the soccer sidecar's source
  manifest, so `autoloop/standing_prereg._gate_corpus_sha('soccer')` moves. That
  is the watermark working as designed (the corpus really did change), same as
  the S41 mlb rebuild.
- The S05 soccer calibration artifact was NOT regenerated: `y`, `p_base` and
  `order_basis` are all unchanged (`DataFrame.equals` True), so its inputs are
  identical. Any OTHER prior number computed from this corpus is untouched and
  unre-verified.
- `corpus_cache.py` is now 404 lines, 104 over the 300-line rail (it was already
  35 over after S41). Kept as one module deliberately, same reason S41 gave:
  the soccer as-of constants and `_asof_only` are read by the builder registry
  and the two private path helpers, and splitting would export those privates.
- No edits to `src/`, `kernel/`, `api/`, `intel/`, the register, or
  `data/registry/`. No feature flag flipped. Nothing copied to the pod. The
  tennis builder branch was not touched (LANE W owns it).
