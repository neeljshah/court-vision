# S164 shared event-key strip helper

Date: 2026-09-03

## Premise re-measurement

The two pre-change implementations were present and produced identical values on
the specified read-only first 200 MLB rows:

```python
frame["game_key"] = frame["event_key"].astype(str).str.split("-", n=1).str[1]
frame["game_key"] = frame.pop("event_key").str.split("-", n=1).str[1].astype("category")
```

Construct result: `sample_rows=200`, `outputs_identical=True`, and zero nulls
from either implementation. This confirms the S164 premise rather than assuming it.

## Change and metric

`scripts.platformkit.venue_history.game_key.game_key_from_event_key` is the one
shared implementation. `add_game_key` and `s99_corpus.rekey` both import it.
The named strip-rule implementation count changed from 2 to 1. The helper preserves
the existing `astype(str)` behavior; `rekey` retains its existing categorical cast.

The full-store digest is SHA-256 over the row-order concatenation of
`pd.util.hash_pandas_object(derived, index=False).values.tobytes()` for each
50,000-row PyArrow `event_key` batch. Stores were opened one at a time and only
the `event_key` column was read.

| Store | Rows | Pre add_game_key SHA-256 | Pre s99 rekey SHA-256 | Post helper SHA-256 |
| --- | ---: | --- | --- | --- |
| mlb | 13,473,591 | 349cb2143d5e4d3c963736a8e4bb68d83085478fe4cddc48f0801fc6b4f07dd1 | 349cb2143d5e4d3c963736a8e4bb68d83085478fe4cddc48f0801fc6b4f07dd1 | 349cb2143d5e4d3c963736a8e4bb68d83085478fe4cddc48f0801fc6b4f07dd1 |
| soccer_intl | 2,261,903 | 76d350356b2fc5d3ff5f8d0772b5e4ce132cd5b18319a6c5d2340225fc44e11a | 76d350356b2fc5d3ff5f8d0772b5e4ce132cd5b18319a6c5d2340225fc44e11a | 76d350356b2fc5d3ff5f8d0772b5e4ce132cd5b18319a6c5d2340225fc44e11a |

Both complete derived columns have the same row count and digest before and after.

## Verification

- `python -m pytest scripts/platformkit/venue_history/test_game_key.py -q`: 1 passed.
- `python -m pytest scripts/platformkit/venue_history/test_build_price_series.py -q`: 7 passed.
- `python -m pytest tests/platformkit/ingame/test_s99_cross_market.py -q`: 8 passed, 1 skipped.
- B1-B10: no rows excluded, schema or thresholds changed, writes performed, modules moved, or gates altered.
- Q1-Q6 and Q9: not scored-comparison work. Q7: the construct exhaustively names 2 call sites and 2 stores. Q8: premise re-measured above.

## NOT VERIFIED

- A production `rekey()` end-to-end materialization was not run; it would load its broad filtered view. Its exact derived-column operation was re-derived over every row and its dedicated per-file test passed.
- No unrelated event-key parsing rules were changed; S164 is limited to the two named series-prefix call sites.
