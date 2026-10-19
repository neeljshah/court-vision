# S450 preregistration -- DRAFT, UNSEALED

Spec: `docs/evidence/tracking/specs/S450_spec.md` (AMENDMENTS 1-16, cumulative and
binding, override the earlier CHANGE/ACCEPTANCE text wherever they differ --
never AMENDMENT 1 alone). This file is a DRAFT only: no seal hash, no
launch-ledger K charge, no scored comparison. Per AMENDMENT 1(g) the real-run
calibration verdict
requires a SEALED version of this file (grids/scorers/nulls/cluster
unit/abstention policy/decision rule, committed BEFORE scoring) plus one K
charged in the launch ledger and the archived paired-loss series (Q9) -- none of
that has happened. Nothing in this file is a scored claim.

## Corpus

`data/domains/mlb/player_gamelogs.parquet` (321,012 rows, 2022-04-07..2026-07-02,
OBS per S450_spec.md fact (f); NOT opened by this build lane -- construct/fixture
only). Fold labels reused unedited from
`domains.mlb.props_eval_gate_mlb_constants.CORPORA`:
`fit_2022_2023`, `holdout_2024`, `holdout_2025_2026`. Fold BOUNDARIES for the real
run are day-level CLI flags (`--fit-start --fit-end --holdout-a --holdout-b`),
because `holdout_2025_2026` ends mid-2026 (2026-07-02), which the year-only
`CORPORA` tuple cannot express.

## Eligibility manifest

One row per (game_pk, team): the pitcher whose pitching line carries the
SMALLEST finite preserved source ordinal (`ORDINAL_COL =
"pitching_appearance_ordinal"`, 0 = first pitcher used), built from
`player_gamelogs` alone (`build_start_manifest`,
`mlb_pitcher_k_distribution_manifest.py`) -- never from `probables.parquet`,
which is July-2026 metadata and cannot establish historical pregame
availability (AMENDMENT 1(c)). Realised inningsPitched / battersFaced are
NEVER used to rank (AMENDMENT 2(a): an opener at 1.0 IP followed by a bulk arm
at 7.0 IP -> the opener is the start). A `(game_pk, team)` group with no row
carrying a finite ordinal (`math.isfinite` -- NaN, +inf and -inf all refuse,
AMENDMENT 3(a)) is refused WHOLESALE, counted `no_pitching_order`, never a
max-innings fallback -- but that per-row abstention is reached only AFTER a
charge. THE PRE-CHARGE ORDER (AMENDMENT 14(c)/15(d), binding): (1) the
non-charging observed-corpus-bound comparison runs FIRST, immediately after
the corpus is read -- a date-free corpus, or one whose observed max date
differs from the sealed `holdout_b_end`, refuses `holdout_b_end_mismatch`
before anything else is checked; (2) ONLY once the bound matches does the
column guard run (AMENDMENT 12(f)/13(b)/15(b)): refuses
`ordinal_column_absent` when `ORDINAL_COL` is absent from the corpus OR any
`MANIFEST_REQUIRED_COLS` column other than `date` is absent (e.g.
`pitch_strikeOuts`), or `manifest_key_invalid` when a pitcher row's
`game_pk` or `team` is NaN; (3) only after BOTH pass does the launch charge.
`ordinal_column_absent` is therefore expected ONLY when the bound already
matches -- a corpus missing `ORDINAL_COL` AND carrying a mismatched bound
refuses `holdout_b_end_mismatch` first, never "charged, no_pitching_order
for every game" and never `ordinal_column_absent` ahead of the bound check.
Rows with missing/nonpositive
`battersFaced` are KEPT and
scored with projected exposure (`exposure=None` on every arm call, always --
realized exposure is never used by any arm, so a missing `battersFaced` never
blocks a forecast). `pitch_strikeOuts` missing or not a valid strict-int COUNT
is a separate, named abstention (`y_missing` / `y_non_integer_float` / ...).

## Arms

- Arm A: `prop_distribution(df, pid, "Pitcher Strikeouts", as_of, exposure=None)`,
  unedited, byte-identical call shape to `prop_edge_mlb.py:52`.
- Arm B: Arm A + `dispersion=r`. `r` grid-fit on `fit_2022_2023` ONLY by minimum
  mean discrete CRPS, from the predeclared grid `R_GRID = (4, 6, 8, 10, 12, 16,
  24)` (includes the served, never-fit prior 8.0 from
  `props_eval_gate_mlb_constants.dispersion_for("sp_strikeouts")` as one grid
  point, not as a shortcut). Frozen before either holdout is touched.
- Arm C: Arm B's lam scaled by `1 + beta*(opp_k_rate_as_of - league_k_rate_as_of)`,
  fed into `domains.soccer.prop_engine._make_p_over(lam, "negbin", r)` directly.
  `beta` grid-fit on `fit_2022_2023` ONLY, grid `BETA_GRID = (0, 0.25, 0.5, 0.75,
  1.0, 1.5)`. `beta=0.0` always reproduces Arm B exactly (implementation identity
  test, not a null -- AMENDMENT 1(f)) regardless of opponent-rate availability.
  `opp_k_rate_as_of` / `league_k_rate_as_of` pool the opposing team's / the whole
  league's own batter strikeOuts/atBats over rows strictly before the start date.

## PMF adapter

`pmf_from_exceedance` turns each arm's exceedance callable into a PMF over
k=0..60. Abstains (counted, never clamped) on: a non-callable, a non-finite or
out-of-[0,1] p_over, a non-monotone p_over, or residual tail mass at k=60 >=
1e-9. CRPS, pinball@{q10,q50,q90} and log score (floor 1e-9) are computed
directly from this PMF -- `crps_discrete` / `median_and_pm1`
(`props_eval_gate_mlb_dist.py`) are NOT used for scoring (AMENDMENT 1(d)).

## Scorers

Per K-line in `{3.5, 4.5, 5.5, 6.5, 7.5, 8.5}`: exceedance probability and
Brier recomputed from the PMF, plus `cpcv_tail_metrics.reliability_table`
(line 69, imported unedited) over a single `[0,1]` bin with `min_n=30` (Q7).
CRPS / pinball / log score as above, meaned per fold per arm.

## One history policy

For a start on date D, every pool (pitcher history via `prop_distribution`'s own
leak guard, `opp_k_rate_as_of`, `league_k_rate_as_of`, and the FIT-corpus rows
used to fit r and beta) admits only rows with date strictly before D. Each arm
predictor filters its own history from the as-of date; the row does not rely on
`cpcv_engine`'s generic timestamp/matchup purge for this (AMENDMENT 1(b) states
that engine does not enforce chronology on its own). `assert_vintage`
(`cpcv_engine.py`, imported unedited) is called on every scored row as an
additional, generic leak-guard sanity check against a minimal per-row state
(`game_id`, `state_ts` = game day noon, `feature_avail` = the day before at
23:59:59) -- a LeakError here is a hard failure, never caught.

## Abstention policy

A row any one of the three arms cannot forecast (unknown rate/exposure, or a
PMF abstention) is abstained for ALL THREE arms together, with the reason
counted (AMENDMENT 1(c)): the paired denominator never drifts arm-to-arm. No
eligible row is ever silently dropped -- `n_eligible` and `n_scored` are both
reported per fold, and abstention reasons are tallied by name.

## Cluster unit and CI

Cluster unit = **game date** (the calendar day of the start), not game_pk and
not player -- multiple starts share a date and must not be treated as
independent draws. `cluster_boot_ci` (`entry_timing/study.py`, imported
unedited) computes a 95% CI for the mean paired CRPS difference (challenger
minus incumbent), `n_boot=2000`, `seed=13`, requiring >=5 distinct date
clusters or returning `(None, None)`.

## Predictive null (Arm C)

Arm C's null permutes `opp_k_rate_as_of` across same-date starts with shared,
seeded draws (`permute_opp_k_rate_null`, seed=13) -- run FOR REAL in the
real-run route (AMENDMENT 6(c)/FIX 1e-1f `compute_null_losses`/`compute_c_vs_b`),
archiving each identity's OWN null CRPS and null paired delta. THE NULL
DECISION RULE (AMENDMENT 6(b), sealed below as `null_decision_rule`): a
holdout's favour is confirmed only if its REAL mean paired delta
(C-vs-B CRPS) beats the SAME holdout's null mean paired delta; if the null
set does not cover the exact same paired denominator as the real scored set
(same rows, hence the same clusters), the C_vs_B verdict is INSUFFICIENT --
never ACCEPT on a partial null.

## Two-holdout decision rule

`B_vs_A` and `C_vs_B` are each judged independently on `holdout_2024` and
`holdout_2025_2026`:
- Both holdout CIs strictly favour the challenger (CI entirely negative), AND
  (`C_vs_B` only) each holdout's null decision rule above confirms it -> ACCEPT.
- Exactly one favours -> SINGLE-WINDOW (never ACCEPT -- AMENDMENT 1(g), case 11).
- Neither favours -> NULL.
- Either holdout has fewer than 30 scored rows, or (`C_vs_B`) the null coverage
  is incomplete -> INSUFFICIENT (overrides the above).

`fit_2022_2023` scores are descriptive only and never enter the verdict
(AMENDMENT 1(e)). Every scored HOLDOUT row is scored through its own
`cpcv_splits` path's train side after symmetric blocking (AMENDMENT 6(a),
`mlb_pitcher_k_distribution_cpcv.py`), never the unrestricted full corpus.

## Sealed scoring parameters (AMENDMENT 6(d), extended by AMENDMENT 9(a))

The real-run CLI refuses any `--seed`/`--draws`/`--fit-start`/`--fit-end`/
`--holdout-a`/`--holdout-b`/`--holdout-b-end` value that differs from the
block below once this file is sealed and committed; grids/cluster-unit/
abstention/null-rule carry no CLI flag and so cannot drift by construction.
`holdout_b_end` (AMENDMENT 9(a)) is the sealed end of `holdout_2025_2026`;
before this amendment it was silently derived from the input corpus's own
latest date, so a refreshed corpus could widen the scored window without
resealing. AMENDMENT 11(b) (tightening 10(b)) additionally validates the
CORPUS'S OWN observed maximum date against this same sealed bound BEFORE
any charge: the real-run CLI refuses `holdout_b_end_mismatch` unless that
observed date EXACTLY EQUALS `holdout_b_end` -- a row past the bound, a
corpus that has not yet reached it, or a missing observed date are all
refused with no charge and no report, never silently accepted.

<!-- SEALED_PARAMS
seed: 13
draws: 2000
fit_start: 2022-01-01
fit_end: 2023-12-31
holdout_a_start: 2024-01-01
holdout_b_start: 2025-01-01
holdout_b_end: 2026-07-02
r_grid: 4,6,8,10,12,16,24
beta_grid: 0,0.25,0.5,0.75,1,1.5
cluster_unit: game_date
abstention_policy: common_all_or_nothing
null_decision_rule: real_paired_delta_must_beat_same_holdout_null_paired_delta
SEALED_PARAMS -->

## What this draft does NOT do

No seal hash on THIS file yet (the block above is the content to be sealed).
No launch-ledger K charge (Q2). No real corpus was opened. No archived
paired-loss series (Q9) exists yet. Sealing this file (adding the trailing
`SHA:` line and committing it) and running the real corpus is the
orchestrator's next step, not this build lane's.
