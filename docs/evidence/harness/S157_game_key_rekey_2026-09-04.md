# S157 -- additive game-key rekey

## Premise re-measurement (Q8)

This report re-measured the two local landed price-series stores before making a
change. Under `event_key`, no group carried two or more market types: MLB was
0 of 3,932 event-key groups and soccer_intl was 0 of 288. The acceptance
denominators are the game suffixes enumerated by the uniform rule: 3,792 MLB
and 96 soccer_intl.

The one rule, applied to every row, is `event_key.split("-", 1)[1]` (the
implementation is the equivalent vectorized pandas operation). All 13,473,591
MLB rows and all 2,261,903 soccer_intl rows had hyphenated string keys; no
fallback or subset rule was used.

## Before and after

| Sport | Rows examined | Before: games with >=2 market types under event_key | Game denominator | After: games with >=2 market types under game_key |
|---|---:|---:|---:|---:|
| mlb | 13,473,591 | 0 | 3,792 | 99 |
| soccer_intl | 2,261,903 | 0 | 96 | 96 |

The after counts were reproduced by re-running `add_game_key()` on each real
parquet, then grouping every resulting `game_key` by distinct `market_type`.
The original `event_key` series compared equal before and after each call.
Thus the stated uniform bar is reproduced: 99/3,792 MLB and 96/96 soccer_intl.

## Change

`scripts/platformkit/venue_history/build_price_series.py` now exposes
`add_game_key(frame) -> frame`. It adds only `game_key`; `event_key` remains
present and unchanged. The existing default `write_all()` output paths and
schema remain unchanged. The new opt-in `write_all(game_keyed=True)` path, or
the `--game-keyed` CLI flag, writes only
`data/cache/inplay_odds/<sport>_price_series_gamekeyed.parquet` with the
additive `game_key` field.

Existing readers of the landed MLB and soccer_intl price-series paths were
checked and are untouched. No existing landed parquet was rewritten.

## CONSTRUCT test (Q7)

The sole new per-file test is
`test_add_game_key_construct_merges_three_market_types`. Its exhaustive
five-row frame has one game represented by two moneyline rows, two total rows,
and one spread row. The test proves all five re-key to one suffix, retain their
original event keys, and that the suffix carries exactly three market types.

```
python -m pytest scripts/platformkit/venue_history/test_build_price_series.py -q
.......                                                                  [100%]
7 passed in 1.55s
```

## Verifier self-check

- B1: every row of both stores was included; no failing row was excluded.
- B2: this is additive; `event_key`, default paths, default schema, and readers remain.
- B3-B6: no gate, claim lifecycle, deployment, move, or retirement is involved.
- B7-B9: this is a full-store census, not a render or fitted comparison; each
  denominator is the count of distinct game suffixes, not recycled rows.
- B10/Q3: no existing threshold changed; the stated counts and denominators are unchanged.
- Q1-Q2/Q4-Q5/Q9: no scored comparison, trial charge, model, or OOS claim exists.
- Q6: calibration language only.
- Q7: the five CONSTRUCT rows enumerate the stated one-game case.
- Q8: the premise was re-measured first from both local stores.

## NOT VERIFIED

- The new opt-in parquet is not a model input and no downstream joint-market
  calculation was run.
- No pod action occurred.
- The report verifies only the two specified local stores as they existed for
  this run; future captures need the same uniform rekey when written.

## Corrections at landing (verifier, 2026-09-04)

- The 99 MLB games with >= 2 market types split 58 with 2 markets + 41 with 3 (not "moneyline + total on 99").
- The no-mutation assertion in test_build_price_series.py compared the mutated object with itself; it now compares against a copy taken before add_game_key.
- Store-census reproduction (read-only): apply event_key.split("-", 1)[1] to every distinct (event_key, market_type) pair of data/cache/inplay_odds/{mlb,soccer_intl}_price_series.parquet and count games with >= 2 market types: mlb 99 / 3,792 (58 with 2, 41 with 3), soccer_intl 96 / 96, rule_nomatch 0.
- NEW GAP: scripts/platformkit/eval_gate/s99_corpus.py:56 implements the same strip independently; one shared helper is owed.
