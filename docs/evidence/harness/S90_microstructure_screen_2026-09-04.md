# S90 -- order-book microstructure screen (gapfinder L15) + L14 side measurement

Row S90 verbatim (INGAME_GAP_PREMISES L14 L15): as-of depth imbalance / spread /
last-trade direction on the overlap of the two Kalshi depth stores with the scored MLB
ticks (2026-07-09..07-12), bar = next-tick sign accuracy with a clustered CI + outcome
Brier of e4 vs e4+adjustment on the SCREEN side; plus L14 (re-key `event_key` so one
game carries all its in-play markets) as a side measurement. No charge.

## STEP 0 -- premise re-measurement (Q8)

S90 is the SAME L15 gap as row **S100**
(`scripts/platformkit/eval_gate/s100_microstructure.py`), dispatched earlier the same
day and already **CLOSED 2026-09-03 c8acbd78c -- PREMISE FALSIFIED AT TICK GRAIN**
(memo `docs/evidence/harness/S100_microstructure_2026-09-03.md`). Both rows cite the
identical stores (`book_depth/_archive/kalshi` 277,888 rows, `book_depth/_archive/
kalshi_trades` 2,070,472 rows, `depth_history/mlb` 107,356 rows) and the identical bar
(next-tick sign accuracy CI + outcome Brier of e4 vs e4+adjustment). This is a
duplicate-row situation, not a new ask -- surfaced here rather than silently re-run.

This module re-measures the premise FRESH today by calling S100's own pure loaders
under a new stem (`s90_microstructure_2026-09-04*`, independent of S100's artifacts;
`docs/evidence/harness/S100_microstructure_2026-09-03.md` and its CSV/JSON are
untouched). Reproduced exactly:

- **Scored MLB ticks**: 78,986 ticks / 227 games, `2026-06-20T00:51:03Z ..
  2026-07-12T23:02:46Z` (`data/cache/ingame_grade_joined/mlb`).
- **SCREEN partition** (`foundry.tiers.partition_corpus`, seed 0, game blocks; same
  partition S82/S100 use).
- **Max SCREEN-side games with ANY as-of microstructure feature inside a 300 s
  freshness cap: 18** -- identical to S100's reproduced number, confirming the depth
  stores have not been re-captured with denser in-play cadence since S100/S105 closed
  today (S105 landed the ticker-selection fix additively but left the `depth_history`
  300 s cadence CLOSED AT LIMIT; the fix has not yet produced new dense captures on
  disk locally).

## Verdict

**`n_screen_games_any_feature = 18` < this row's own sampling rail `n >= 30`.**
Per `CODEX_SPEC_TEMPLATE.md` PREMISE (step 0): STOP, do not fit an arm. Fitting
next-tick sign accuracy or an outcome-Brier logistic adjustment on 18 clusters would
under-power the CI to the point of being indistinguishable from noise, and reporting it
anyway on a premise already known (from S100) to fail the rail would be exactly the
circular-metric pattern VERIFIER_CONTRACT B1 forbids.

**Result: PREMISE FALSIFIED / INSUFFICIENT.** No arm run. No outcome Brier of e4 vs
e4+adjustment computed. No next-tick sign accuracy scored beyond the descriptive table
S100's `run()` already produces (which itself only reaches 3 games / 305 ticks best
case per S100's memo, all CIs spanning zero). This is a valid row outcome, not a
failure (Q8, CLOSED AT LIMIT precedent).

## L14 side measurement (cheap, independently new -- not covered by S100)

Re-keyed `event_key` by stripping the Kalshi series prefix and grouping on the
remaining game suffix, over the full on-disk price-series stores:

| corpus | required market types | games total | games matched |
|---|---|---:|---:|
| `mlb_price_series.parquet` | moneyline + total | 3,792 | **99** |
| `soccer_intl_price_series.parquet` | moneyline + spread + team_total | 96 | **96** |

Matches the row's own claimed counts ("~99 MLB games", "96 soccer_intl games x 3
markets") to the game. Every soccer_intl event on disk carries all three markets
(96/96); MLB carries moneyline+total for 99 of 3,792 events (2.61 pct) -- the other
3,693 MLB events have only one market type captured. **This is an overlap count only:
no joint distribution fit, no CRPS score, no re-key was applied to a modelling
pipeline** -- that is L14's own row, out of S90's bar, and is reported here purely as
the "cheap if free" side measurement the dispatch asked for.

## Method

`scripts/platformkit/ingame/s90_microstructure_screen.py` (155 LOC):
- `stop_rule_verdict(n_screen_games, bar)` -- pure STEP 0 decision function.
- `rekey_market_overlap(frame, required_types)` -- pure L14 prefix-strip + overlap
  count, works on any `(event_key, market_type)` frame.
- `reproduce_s100_premise(stem, out_dir)` -- calls `S100.run()` (read-only import, S100
  module untouched) under a new stem.
- `l14_side_measurement()` -- reads the two price-series parquet files, calls
  `rekey_market_overlap`.
- `run()` / `main()` -- orchestrates, writes the evidence JSON.

## Reproduction (A2)

```
cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.ingame.s90_microstructure_screen
```
Prints `S90 | PREMISE FALSIFIED / INSUFFICIENT (n_screen_games=18 < bar=30)`, the L14
match counts (99/3792, 96/96), and the evidence path. Deterministic (no randomness;
`partition_corpus(seed=0)` is fixed).

## Evidence

- `docs/evidence/harness/s90_microstructure_2026-09-04.json` -- S100-pipeline
  reproduction (tick-grain + screen-side coverage tables, store block counts).
- `docs/evidence/harness/s90_microstructure_2026-09-04_series.csv` -- per-tick feature
  series behind that reproduction (Q9 archival requirement).
- `docs/evidence/harness/s90_microstructure_2026-09-04_summary.json` -- this row's own
  summary: verdict, L14 counts, NOT VERIFIED list.

## NOT VERIFIED

- No arm was fit; no outcome Brier of e4 vs e4+adjustment; no next-tick sign accuracy
  beyond S100's own descriptive table (3 games / 305 ticks best cell, CI spans zero).
- L14's re-key was not carried into any modelling pipeline (no joint distribution fit,
  no CRPS score) -- overlap counts only.
- The pod-side `data/cache/ingame_books/mlb` store (S105: `mlb_book_capture`, pids
  21620/21622, median 30 s cadence, full ladders first-pitch-to-final) is NOT synced
  locally and was not read here -- per lane rails, no scp before ACCEPT, and joining it
  is a distinct row (S100's memo already names it: "the remaining distance to
  microstructure is a JOIN, not a capture").
- Whether `depth_history`'s 300 s cadence has since been raised is not re-checked here
  beyond the identical 18-game reproduction; that constant is an orchestrator/Neel call
  per S105.

## Test

`python -m pytest tests/platformkit/ingame/test_s90_microstructure_screen.py -q` --
5 passed (CONSTRUCT, `n = 5` cases enumerated: 2 stop-rule cases + 3 rekey cases over a
7-row hand-built frame covering MLB-2-type, MLB-1-type, MLB-spread-only, and the full
soccer_intl 3-type case).
