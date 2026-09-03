# S168 Third Strip Copy

## Premise and scope

S168 measured the remaining direct `event_key` strip implementation in
`scripts/platformkit/ingame/s90_microstructure_screen.py:69`. The premise was
true before the change: the shared helper and S90 each implemented the rule.

Only `data/cache/inplay_odds/mlb_price_series.parquet` was read for the value
comparison, one store at a time and with `columns=["event_key"]` only.

## Grep census

| Time | File:line | Implementation |
| --- | --- | --- |
| Before | scripts/platformkit/venue_history/game_key.py:9 | helper: `event_key.astype(str).str.split("-", n=1).str[1]` |
| Before | scripts/platformkit/ingame/s90_microstructure_screen.py:69 | `suffix = frame["event_key"].astype(str).str.split("-", n=1).str[1]` |
| After | scripts/platformkit/venue_history/game_key.py:13 | helper only |

The whole `scripts/platformkit` Python tree was searched for the first-hyphen
strip form. The direct-copy metric is 1 before and 0 after, excluding the
helper itself.

## Derived-column reproduction

The before and after values use the MLB store's row order. For each Parquet row
group, the derived series was hashed with `pandas.util.hash_pandas_object`
using `index=False, categorize=False`; SHA-256 was applied to the concatenated
row-ordered value-hash bytes. This avoids loading unrelated columns or stores.

| State | Rows | SHA-256 |
| --- | ---: | --- |
| Before direct S90 expression | 13473591 | 349cb2143d5e4d3c963736a8e4bb68d83085478fe4cddc48f0801fc6b4f07dd1 |
| After `game_key_from_event_key` | 13473591 | 349cb2143d5e4d3c963736a8e4bb68d83085478fe4cddc48f0801fc6b4f07dd1 |

## Home decision

Keep `scripts/platformkit/venue_history/game_key.py` as the helper home. Its
module docstring now names all three importers:

- `venue_history.build_price_series`
- `eval_gate.s99_corpus`
- `ingame.s90_microstructure_screen`

This keeps the existing stable import path and removes the only remaining
direct S90 copy. The construct count is n = 3 call sites.

## Verification

- `python -m scripts.platformkit.venue_history.test_game_key` exited 0.
- `python -m pytest tests/platformkit/ingame/test_s90_microstructure_screen.py -q`:
  5 passed in 24.74s.
- B1-B10 self-check: no rows were excluded; no schema, reader, threshold, or
  ledger changed; no deployment or module move occurred.
- Q self-check: this is a construct refactor, not a scored comparison. Q1-Q5
  are not applicable; Q6 is satisfied by calibration-only language; Q7 applies
  with exhaustive n = 3 call sites.

## NOT VERIFIED

- No real-store S90 overlap result was recomputed; the required check is the
  byte-identical derived key column and the focused construct test.
- No production daemon or unrelated caller was run.
