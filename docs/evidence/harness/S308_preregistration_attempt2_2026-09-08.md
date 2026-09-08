# S308 attempt 2 preregistration: nested functional validity of S294 conformal bands

## Scope

This is an uncharged NBA in-game calibration diagnostic. It makes no
comparative promotion and writes neither a shared ledger nor a register. The
S294/S307 artifacts and modules remain byte-identical. Calibration language
only.

The clause above is carried verbatim from attempt 1 for the artifacts. Two
modules are NOT byte-identical in this attempt, and that is stated openly in
the defect-fix and vectorization sections below: the landed S294 and S307
EVIDENCE FILES are untouched, but the S294 route module and the S308 evaluator
both carry corrections. Every hash is recorded under Code identity.

## What attempt 1 produced

Attempt 1 sealed `S308_preregistration_band_functional_validity_2026-09-07.md`
(seal d9941cb05866717d700778c3af99a8e572b30615638fed1402a203c8c00ddeb9) and ran
a pod scorer for 8 h 56 m at about 0.14 of one core. IT PRODUCED NO S308
NUMBER. It finished the S294 baseline replay and then raised FileNotFoundError
on `data/cache/eval_gate/s101_aci_coverage_2026-09-03.json`, an input the pod
tree did not carry. Zero S308 artifacts were written, so nothing from attempt 1
is retracted here; there is nothing to retract. The orchestrator has since
shipped that 30,939-byte input (sha256 prefix 2cbb44bb4a6b2aec) into the pod
data store at `/workspace/nba-ai-system/data/cache/eval_gate/`, which
`/workspace/wt/a18/data` links to. That ship is the only write outside this
lane's own scratch tree that the run depends on.

## Baseline artifact

The S294 baseline is REGENERATED, not reused. The attempt-1 job did leave
`S294_incumbent_conformal_full_s86_blocks_paired_loss_2026-09-04.csv.gz`
(10,916,465 bytes) in the pod scratch tree, but the module that produced it has
changed, so that copy is not reusable evidence. This attempt replays
`s276_incumbent_conformal_band_full_attempt2.run` from scratch inside the same
S308 process and reads only the archive that replay writes. The regenerated
copy stays in the pod scratch tree; the landed S294 evidence files in this
repository are neither overwritten nor re-committed.

## Binding before-condition

Before any S308 metric, replay the unchanged S294 route on the pod. Its
binding output must show ALL grouped coverage 1.000000000 at nominal 0.90 and
0.80 using the ladder_base arm, not recal_null. The retained source is
`data/cache/inplay_odds/nba_checkpoints_full.parquet`: 2,829,826 bytes,
465,249 rows, with columns
`game_id,game_date,ts,period,game_clock_s,score_home,score_away,margin,market_prob,traded,market_ticker,outcome_home_win,venue`;
the first three IDs are 401704627, 401704627, 401704627. It is a tabular
input, so pixel resolution is not applicable.

## Fixed nested design

- Retain the six S86 blocks and one stable evaluator state per tick with key
  `game_id|source_row|ts`.
- For each outer held block, form calibration predictions by holding each of
  the other five blocks in turn. Each inner model is fitted only on the
  remaining four blocks after the shared game-disjoint purge and symmetric
  one-day embargo. Thus no outer-test outcome can affect an inner calibration
  residual, width, or fitted prediction.
- Fit test predictions from the five non-outer blocks after the same purge and
  embargo. Fit grouped split-conformal half-widths from the inner OOF
  calibration predictions only, then apply them once to the outer test block.
- Use the unchanged S101 equal-count grouping by probability for both
  calibration and test. Score every phase and ALL at nominal 0.90 and 0.80;
  retain cells below two groups of 400 ticks as `ABSENT_BECAUSE`.
- Archive every outer membership, every inner training dependency, every
  interval tick, and every grouped interval-score unit. A group frequency
  interval score is `width + (2 / alpha) * distance_to_interval`, where
  `distance_to_interval` is zero when observed group frequency lies inside its
  interval; no row is excluded after scoring.

## Fixed bars and reporting

The S294 before values are ALL half-width 0.031114796 at 0.90 and 0.019952038
at 0.80. The S307 frozen coverage bar remains `[nominal - 0.02, nominal +
0.05]` for ALL and every cell with at least 400 ticks; the S86 400-tick rail
and the 0.004 global Brier bar are unchanged. The S308 validity bar is zero
outer-label dependencies. This is diagnostic-only when comparable nested
groups are absent. Report the S307 bars unchanged, including every failure.

The sign convention is: improvement = baseline loss minus candidate loss;
positive = candidate better. Group-frequency interval-score loss is the
fixed width-plus-outside-distance loss above, so a positive delta means the
candidate has lower loss.

Every bar in this section is carried byte-identical from attempt 1. No bar
moves in this attempt for any reason (Q3).

## Three defect fixes carried into this attempt

D1. `scripts/platformkit/eval_gate/s308_band_functional_validity.py:132` wrote
`"outer_label_dependency": 0` as a literal, so the assertion at the old line
160 restated a constant and the zero-dependency bar was DECLARED, not
measured. It is now MEASURED per outer block: the count of held-block ticks
that reached the inner training pool, plus the count that reached the inner OOF
calibration predictions, both counted from the state list and the calibration
frame. The two counts are archived per dependency row as
`n_outer_ticks_in_inner_train_pool` and `n_outer_ticks_in_calibration`, and the
run asserts their sum is zero. The structural check
`set(calibration.s86_block) == set(range(6)) - {held}` is retained alongside.

D2. `scripts/platformkit/eval_gate/s308_band_functional_validity.py:171` wrote
the S294 BASELINE interval score as
`np.maximum(lo - obs, 0.0, obs - hi)`. numpy's third positional argument is
`out=`, not a third operand, so the upper-side distance was computed into a
throwaway buffer and silently discarded, leaving `max(lo - obs, 0)`. The
corrected line is the preregistered formula,
`width + (2 / alpha) * (max(lo - obs, 0) + max(obs - hi, 0))`. The archive now
carries both `interval_score` (corrected) and
`interval_score_lower_side_only` (the defective value it replaces), and the
report records the group count, the number of groups whose score moves, and the
sum before and after. The candidate rows always used the builtin three-argument
`max(...)` and were never affected; coverage and half-width are unaffected on
both sides. This correction is raised as a NEW GAP against the S294 row rather
than by amending any landed memo, and no landed memo is edited.

D3. `tests/platformkit/test_s308_band_functional_validity.py` took its
calibration `before` and `after` from two identical `s101.calibrate` calls and
never passed the perturbed frame to either, so it asserted determinism, not
label isolation. The test now compares one `run_fold` on the original outer
labels against one on flipped outer labels, and adds a POSITIVE CONTROL: the
same comparison must move when the CALIBRATION labels are moved instead. An
assertion that cannot fail is not evidence.

## Vectorization and its equivalence rule

The per-tick predictor built a fresh one-row DataFrame and called
`predict_proba` once per callback: 2,791,497 callbacks for the nested design at
about 1.301 ms of pod CPU each. `scripts/platformkit/eval_gate/ladder_block_predict.py`
now fits once per frozen block, as before, and then serves that block's ticks
from ONE batched `predict_proba` over the same standardised
`LADDER_BASE_COLS`. The CPCV engine, the purge, the symmetric embargo, the
strict redaction, the vintage assertion and the per-tick record path are all
unchanged; only the arithmetic is batched. Every served tick is checked against
its own source features before it is returned, so a redacted view that had
diverged from the state it was built from would raise rather than be served.

EQUIVALENCE RULE: the reference per-tick path `predict_one` is retained and
callable, and `tests/platformkit/test_ladder_block_predict.py` asserts that the
batched path agrees with it to a maximum absolute difference of 1e-12 over a
2,500-tick sample of the real S86 ticks (falling back to a seeded synthetic
frame only when the corpus file is absent). The same test asserts the block
predictor served through its engine-shaped callback matches the per-tick path
to 1e-12 on the same sample. The identical change is applied to the S294
baseline path, which shared the loop.

## Code identity

Recorded after the fixes above, over the LF bytes committed for this attempt:

- s308_band_functional_validity.py de659650388e7313d9aea0e43ee7af1721d2fbbb7ee5df49ba0ca1ff5000185e
- ladder_block_predict.py 0e85949f148357bb127dce618b1b126092e9f80546c65b11597d181fcf68f0e9
- s276_incumbent_conformal_band_full_attempt2.py 2358512d6f7e8fc84bc32350430b864add39ba0f9b8dd73e433bfda643a78fb0
- cpcv_engine.py 5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5
- s101_aci_coverage.py 4dbadc319b76a0e9c6e4ea53e3c683f242176774290917bebee894344c2cf93f
- s265_incumbent_conformal_band_sample.py 697d7ae649686ec580e9059e62744ce288bd27b6383e311c3c94d881fff817ff
- s86_nba_every_tick.py 2e197d14cce6d86ed80db6482cf37b08201c61944b930197cbf6317a1140fa68

cpcv_engine, s101, s265 and s86 are unchanged from attempt 1 and their hashes
are identical to the attempt-1 record. s276 and s308 changed for D1, D2 and the
vectorization; ladder_block_predict is new.

## Execution

The full nested refit and the S294 baseline replay run only in
`/workspace/wt/a18` on the pod, which carries this worktree's Python tree and
links the data tree. The pod is used because the scorer is expected to exceed
500 MB RSS. No deployed tree, data store, registry, ledger, hypotheses
database, or feature flag is written by this lane. Outputs are written under
`docs/evidence/harness/` with the attempt-2 stem
`S308_band_functional_validity_attempt2_2026-09-08`, so no existing artifact is
rewritten.

## Seal rule

The seal on the last line is the SHA-256 of every byte of this file above the
seal line, after CRLF is normalized to LF. The focused test reads the file,
normalizes it the same way, and recomputes the same value.

SEAL_SHA256: 92e7463acabc9a58dbad4c7b83dfec37a13e7a63295f009629b634dbc7698f4f
