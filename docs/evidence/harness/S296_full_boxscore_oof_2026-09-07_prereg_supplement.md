# S296 preregistration supplement: 2026-09-07 finish-audit clauses

This sealed supplement is committed before any 2026-09-07 S296 scorer
execution. It supplements, without rewriting,
`docs/evidence/harness/S296_full_boxscore_oof_2026-09-04_prereg.md` and
`docs/evidence/harness/S296_full_boxscore_oof_2026-09-04_prereg_attempt2.md`.
Their premise, inputs, field set, CPCV design, existing metrics, `+0.004`
comparison bar, and SINGLE-WINDOW calibration status all remain unchanged and
are not restated as new commitments here.

`docs/evidence/tracking/specs/S296_spec.md` gained a `VERSION 2026-09-07
(finish audit)` section after the two seals above were written. That section
retains every earlier acceptance clause and ADDS the clauses this supplement
fixes in advance. The added measurements are recorded here before any of them
is computed on the scored corpus.

## Added measurements, fixed before scoring

1. ABSORBED S292 PREFLIGHT. Before any fit, the four archived prop-evaluation
   inputs are recounted and each is labelled `TESTABLE` or `NOT_TESTABLE_TODAY`
   with its exact blocking fact: `data/cache/prop_calibration_history.parquet`,
   `data/cache/props_eval_nba_calibration.json`,
   `data/cache/prop_sigma_scale.json`, and
   `data/frontend/prop_history_corpus.jsonl`. n = 4 (CONSTRUCT, exhaustive).
   The aggregate-versus-per-bet granularity distinction and the absence of any
   market comparison are reported as blocking facts and are never omitted. A
   count that fails to reproduce is reported FALSIFIED and closes the preflight.

2. RECOUNT BEFORE FITTING. The two exact boxscore parquets are recounted in the
   same process that fits: union 78,767 unique `game_id+player_id` rows in
   3,645 game clusters, zero key overlap, and zero source algebra violations
   across `oreb+dreb == reb`, `fgm <= fga`, `fg3m <= fg3a`, `fg3m <= fgm`,
   `ftm <= fta`, `2*(fgm-fg3m) + 3*fg3m + ftm == pts`, and non-negativity.

3. ZERO-MINUTE PRESERVATION AND THE ROSTER DISTINCTION. Rows with `min == 0`
   are preserved in every denominator and counted as OBSERVED DNPs. A player
   with no row at all is a MISSING ROSTER RECORD; neither source carries an
   as-of roster, so missing records are reported as unobservable from these two
   inputs, quantified only by the per-game-team row-count distribution. That
   limit is stated, never inferred away.

4. JOINT TRAIN-SCALED ENERGY. In addition to the already-sealed raw joint
   energy score, each arm reports an energy score computed after dividing every
   field by that split's evaluator-supplied training standard deviation
   (floored at 1e-9). Both energies carry paired game-cluster CIs. Neither is
   compared against `+0.004`: CRPS, pinball, energy and log score have their own
   units and that bar is not their threshold.

5. ENDPOINT EXCEEDANCES AND DISCRETE ATOMS. Nominal `q10-q90` coverage stays
   0.80. Each field additionally reports the share of held-out states below its
   q10 and above its q90, and the share whose q10 equals its q90 (a degenerate
   discrete atom). Coverage, exceedance and atom shares are reported with their
   denominators.

6. PER-FOLD HELD-OUT GAME COUNTS. Each CPCV split reports its held-out game
   cluster count; any scored fold below 30 held-out games is labelled
   NOT SCORABLE rather than scored.

## Declared non-claims

The 25 candidate and baseline samples are drawn from observed source vectors,
so their internal box-score algebra holds by construction. The sample algebra
violation count is therefore reported as a construction property of the
resampling, never as evidence that a model learned coherence.

All comparative NULL, BEHIND or NOT SCORABLE outcomes are valid results. The
verdict remains SINGLE-WINDOW; no promotion follows from it. New dated
artifacts are written under the `2026-09-07` stem; no existing artifact is
rewritten and nothing under `data/` is written.

SEAL_SHA256: 53862fc7a0692592501ef45c3796119ef22133638886a4e52638a362eed34da7
