# S237 max-loser-WP tick diagnostic: FALSIFIED premise

## Verdict

FALSIFIED. This row's premise states that the S86 archived JSON and memo do
not carry the max-loser-WP result. The JSON carries the full summary; the memo
publishes p90 and above-0.8 summaries, so the asserted absence is false.
Contract Q8 requires this result to close the row without a new scoring run or
fix.

No scored comparison was performed. Therefore no preregistration was written,
no shared-evaluator run was required, and no reliability-table JSON was
created. The S86 per-tick CSV was not opened.

## Local premise check

Machine: local Windows worktree `C:\Users\neelj\nba-track-a16`.

The following non-raster inputs were opened. Resolution is not applicable.

| Input | Bytes | SHA-256 | Finding |
|---|---:|---|---|
| `C:\Users\neelj\nba-track-a16\scripts\platformkit\eval_gate\s86_nba_every_tick.py` | 16024 | `2e197d14cce6d86ed80db6482cf37b08201c61944b930197cbf6317a1140fa68` | Imports `max_loser_wp` at line 31, calls it at line 192, serializes it at line 198, and renders it at lines 282-284. |
| `C:\Users\neelj\nba-track-a16\data\cache\eval_gate\s86_nba_every_tick_2026-09-03.json` | 87184 | `c2848f078da49b47bd09da6a94b961c3ef2d94500b8c07066ef2eaf895a89b11` | Contains `max_loser_wp` in all 5 `market_reliability_by_period` cells and all 15 `market_reliability_by_period_margin` cells. |
| `C:\Users\neelj\nba-track-a16\docs\evidence\harness\S86_nba_every_tick_2026-09-03.md` | 15655 | `9037c26f86f058f5d759608056abadff33f4ea75db816c9234ba2b3dc8edcf94` | At lines 152, 157, 193, and 194, publishes max-loser-WP-style reliability and its p90 and above-0.8 summaries. |

For a direct archive spot-check, the first archived period cell contains 19
loser paths, quantiles 0.615, 0.750, 0.787, and 0.8465 at 50, 75, 90, and 95
percent, respectively, plus counts 2 above 0.8 and 1 above 0.9. This is an
archived diagnostic value, not a new measurement.

## Contract self-check

- Q8: satisfied. The premise was checked before any scoring and is false.
- Q1 and Q4: not applicable because no scored comparison occurred.
- B1: not applicable; no metric was calculated and no rows were excluded.
- Q6: this memo uses calibration-diagnostic language only.
- A7: the only new evidence path is this memo, and it exists before commit.

## Test line

Not run: this is a Q8 premise closure with no implementation change and no
scored calculation. The S237 requested focused test is not created because the
required implementation is not reached after a falsified premise.

## NOT VERIFIED

- Fresh CSV re-derivation and the peak-WP reliability table were not run
  because Q8 closed the row.

## Result

The S86 artifacts falsify the asserted absence; Q8 closes S237 without
adjudicating the separate peak-WP reliability table.
