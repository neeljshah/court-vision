# S264 final preregistration: game-first-date repartition

## Scope

This superseding preregistration fixes the final S264 table construction to the
exact game-first-date construction used by `s88_phase_recal.py`. It is sealed
before the final calibration reproduction. No threshold is changed.

## Inputs opened

| path | bytes | resolution |
|---|---:|---|
| `data/cache/ingame_grade_joined` | 73485324 | N/A: read-only JSONL store |
| `docs/evidence/harness/s88_phase_recal_2026-09-04.csv` | 4311731 | N/A: CSV calibration table |

## Fixed construction

- Rows are the full 33,920-row S88 evaluation calibration table, not a sampled subset.
- `iso_week_alias` is the existing ISO year/week derived from each `ts` and is retained unchanged.
- `game_id_block` is `_first_dates(ticks)[game_id]`: the earliest raw tick's `timestamp[:10]`, exactly as S88's outer game-first-date walk-forward construction defines it.
- The shared-ID metric is the count of game IDs with more than one distinct block value.
- The sole calibration reproduction uses `scripts/platformkit/eval_gate/cpcv_engine.py:cpcv_evaluate` with `n_groups=2`, `n_test_groups=1`, and symmetric `embargo_days=1`. The evaluator retains its imported 48-hour team purge and symmetric nonzero embargo.
- Every evaluated recalibration probability is produced by the evaluator callback from the test row's as-of `published_recal_prob` feature. The callback does not inspect outcomes, closes, or raw rows.
- Each state has feature availability one microsecond before its state timestamp; strict redaction is enabled.

## Fixed checks and bars

1. The source table's ISO-week shared-ID count is 4; the new `game_id_block` shared-ID count must be 0.
2. The evaluator must emit exactly one probability per source row and no duplicate `(game_id, ts)` keys.
3. When grouped by unchanged `iso_week_alias`, source and new-table recalibration, incumbent, and market Brier values must reproduce with maximum absolute difference at most `1e-9`.
4. The new table will preserve every source row and existing source column unchanged, adding only `iso_week_alias` and `game_id_block`.

## Non-claims

This is a partition-integrity and calibration-reproduction check. It makes no deployment,
threshold, or performance claim.

Seal: af5a5d8c66c45cf2116fa4abf2cb1be3ce77e8bb794129e73f48a4abad4af9da
