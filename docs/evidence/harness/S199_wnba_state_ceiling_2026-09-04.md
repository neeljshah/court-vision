# S199 WNBA state ceiling, 2026-09-04

Verdict: FALSIFIED. This is an unscored census result. No calibration comparison
or operational decision was made.

## Premise reproduction

The committed census memo and its summary JSON agree on the stated headline
inputs: 85 intersect games, 186,736 intersect in-play ticks, 18,650 joined
ticks, 19,456 in-span ticks (10.42 percent), 167,280 outside-span ticks,
168 cached PBP games, 84,143 actions with the required fields, and 504
checkpoint states. The JSON also agrees with the stated 250 in-span median,
274 p90, 15-second state-age median, 132-second p90, and zero joined ages
above 300 seconds.

## Direct remeasurement

The premise is falsified when the current source rows are remeasured against
each game's own PBP action span. The existing
`data/cache/inplay_odds/wnba_checkpoints_full.parquet` has 18,650 rows, as
reproduced by the unchanged backward 300-second join. Of those rows, 707 have
`ts` later than their game's final PBP action. Its SHA-256 is
`a97392703bb6c710b0713f8421db860236dcb0c1b9dcc6623ca1d4d5e57a76dc`.

The 186,736 ticks partition under the proposed definitions as follows:

| Measured category | Ticks |
| --- | ---: |
| PRE_FIRST_ACTION | 165,191 |
| JOINED_BACKWARD_300S | 17,943 |
| INTERIOR_GAP_GT_300S_FROM_ANY_ACTION | 723 |
| POST_LAST_ACTION | 2,089 |
| FUTURE_ACTION_WITHIN_300S_ONLY | 790 |
| Total | 186,736 |

The final category is in the PBP span, is more than 300 seconds after the
preceding action, and is at most 300 seconds before a later action. It is not
JOINED under the unchanged backward as-of rail and is not an interior gap under
the spec's "more than 300 s from any action" definition. Thus the requested
four-class partition is not exhaustive.

The 707 post-last-action rows already present in the old checkpoint parquet
also falsify the census statement that no state can be recovered for all
167,280 ticks outside cached PBP wallclock spans. They arise from the unchanged
backward rail carrying the last action for up to 300 seconds, not from a new
boundary state.

## Stop condition

S199 step 0 requires a FALSIFIED result to stop before the requested additive
module, new parquet, or test is created. Therefore this landing makes no code
or data change, does not write under `data/`, and leaves the existing checkpoint
parquet, `wnba_wallclock_join.py`, `asof_join.py`, register, and ledger
untouched.

## Contract self-check

Q8 is satisfied by remeasuring the row's premise before implementation. Q1-Q6
and Q9 do not apply because this is not a scored result. B1 is satisfied: the
complete 186,736-tick denominator and the unmatched 790-row category are
named rather than excluded. B2-B10 do not apply because no schema, reader,
gate, deployment, or production module changed.

## Not verified

- No boundary-clamped final state was created.
- No new parquet exists because the required four-class partition is not
  supported by the source measurement.
- The S199 per-file test was not created or run because the specification's
  stop condition precluded implementation.
