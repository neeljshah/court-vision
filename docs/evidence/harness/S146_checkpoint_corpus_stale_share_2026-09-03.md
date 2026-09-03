# S146 NBA checkpoint corpus state-age share under the S141 300 s rail

Status: MEASURED. The existing parquet is unchanged and every landed NBA
in-game result still stands. A REBUILD under the S141 default rail would drop
250,989 of 465,249 rows (53.947 pct) -- far above the 1 pct threshold in the
gap row -- so this memo carries a rebuild note and a PROPOSED (not applied)
labelled keyword. Nothing was rebuilt, nothing was overwritten.

## Step 0 -- premise

The second caller is `scripts/platformkit/venue_history/nba_checkpoints_full.py:228`:

    joined = join_game_states(states, pm_candles(doc, flip=flipped))

It passes no `max_staleness_s`, so since S141 it takes the keyword default
300.0 s. Its inputs are all on disk and were replayed read-only:

- `data/venue_history/polymarket/nba_2024plus/*.jsonl` -- 321 date-files, 330 MB,
  1,688 distinct `event_slug` docs (the PM price series).
- `data/cache/nba_pbp_wallclock_raw/scoreboard/*.json` -- 398 cached ESPN
  scoreboards (event-id resolution).
- `data/cache/nba_pbp_wallclock_raw/summary/*.json` -- 1,610 cached ESPN
  summaries (the wall-clock state series).

The landed corpus `data/cache/inplay_odds/nba_checkpoints_full.parquet` is
2,829,826 bytes, mtime 2026-07-09 02:25:22 -0500, 465,249 rows over 1,593
distinct `game_id`. It was NOT rebuilt or written by this row; it was opened
read-only once for the comparison below.

## Replay method and the reproduction check

`scripts/platformkit/venue_history/nba_checkpoints_full.build_checkpoints()` was
run unchanged except for two read-only shims applied from a scratch module:

1. `nba_wallclock_join._fetch_cached` replaced by a CACHE-ONLY variant that
   never opens a socket and counts every miss. Result: **0 cache misses** over
   the whole build -- the replay is fully offline and every ESPN payload the
   original build used is still on disk.
2. `join_game_states` called with `max_staleness_s=inf`, which reproduces the
   pre-S141 tolerance-free `merge_asof` exactly: with an infinite rail
   `lag > rail` is never true, so the helper nulls only rows with no earlier
   state at all, and those were already removed by the join's own
   `dropna(subset=["margin"])`. The matched state timestamp was recovered per
   retained row by `np.searchsorted` over the same sorted state ts array the
   join used -- the exact recomputation
   `benchmarks/crps_market/state_lag_sensitivity.py` documents, not a proxy.

Exclusion counters from the replay: games_total 1,688, unmatched_team_name 1,
unresolved_outcome 20, ambiguous_orientation 0, no_espn_event_match 64,
empty_pbp 4, no_candle_overlap 2, duplicate_game_doc 4, games_flipped 1,593,
games_joined 1,593.

REPRODUCTION (the non-tautology check): the pre-rail replay produced
**465,249 rows over 1,593 games -- the same count as the on-disk parquet** --
and on all 13 shared columns, sorted by (game_id, ts, market_prob), the two
frames are `DataFrame.equals` True with the identical canonical hash
`4b6fe0ac38cb5cebef41c3915ab457345e78b7bc986bb4dfcd67478eb9f51ffc`. The replay
therefore reproduces the landed corpus, so the loss numbers below are measured
against the real thing rather than a look-alike.

## What the 300 s rail would drop

Over the 465,249 retained rows, matched-state age is p50 646 s, p90 7,684 s,
max 62,977 s, mean 2,958.7 s. 250,989 rows (**53.947 pct**) sit above the
300 s rail; 214,260 would survive. All 1,593 games stay non-empty, so no game
would be excluded, but every one of them loses rows.

Per period (rows / age p50 / age p90 / age max / rows over rail / share):

| period | rows | p50 s | p90 s | max s | over rail | share |
|---|---|---|---|---|---|---|
| 1 | 44,428 | 12 | 97 | 482 | 4 | 0.000090 |
| 2 | 68,825 | 24 | 587 | 2,691 | 13,775 | 0.200145 |
| 3 | 52,645 | 14 | 125 | 8,036 | 1,626 | 0.030886 |
| 4 | 284,586 | 3,545 | 8,888 | 62,977 | 222,799 | 0.782888 |
| 5 (OT) | 13,152 | 4,314 | 10,764 | 28,167 | 11,358 | 0.863595 |
| 6 (OT) | 1,613 | 4,444 | 9,634 | 16,317 | 1,427 | 0.884687 |

Per game (n = 1,593): games losing at least one row 1,593; games losing every
row 0; rows lost p50 142, p90 205.8, max 1,055; share of the game's own rows
lost p50 0.5188, p90 0.6052, max 0.8851. Worst games 401810349 (1,055 of
1,192), 401812680 (988 of 1,119), 401704691 (796 of 913). Evenly spaced samples
over the sorted game_id list (A3): 401703370 140 of 270, 401705109 160 of 283,
401810052 127 of 256, 401810674 150 of 284, 401873344 24 of 156.

Over ALL 4,786,851 input price ticks of the 1,593 joined games, 4,321,602 have
no prior state at all (the PM series starts long before tip-off), so the
helper's own `stale_share` -- which counts absent and over-rail together --
would read 0.955240.

## Composition of the loss (why the number is so large)

Of the 250,989 rows the rail removes, **235,513 (93.83 pct) are matched to the
last play state of their game**, with median `game_clock_s` 0.0 -- these are
post-final-buzzer price ticks that the tolerance-free join carried the final
score forward onto. That is exactly the S99 defect `eval_gate/asof_join` was
written for, and removing them is a correctness improvement, not a data loss.

The remaining 15,476 rows (6.17 pct of the loss, **3.33 pct of the corpus**)
are genuine mid-game play-by-play gaps: age p50 589 s, p90 835 s, max 8,629 s,
and 13,775 of them sit in period 2 -- the halftime break, when ESPN posts no
plays but the market keeps ticking.

## Effect on the landed checkpoint-bucket results

`ingame_nba_winprob.CHECKPOINTS` selects, per game, the last row at or before
each elapsed-minute anchor. Re-selecting on the railed frame:

| bucket | games pre-rail | games railed | games lost | row changed | margin changed | p90 abs market_prob shift |
|---|---|---|---|---|---|---|
| end_q1 (12.0) | 1,592 | 1,592 | 0 | 2 | 0 | 0.000 |
| halftime (24.0) | 1,593 | 1,593 | 0 | 351 | 0 | 0.005 |
| end_q3 (36.0) | 1,593 | 1,593 | 0 | 1 | 0 | 0.000 |
| q4_under5 (43.0) | 1,593 | 1,593 | 0 | 0 | 0 | 0.000 |

No checkpoint game is lost in any bucket, and the state (`margin`) attached to
the selected row never changes; only halftime re-selects a different tick in
351 of 1,593 games, at a median absolute market_prob shift of 0.000 and a p90
of 0.005. So the bucket-scored rows (S86, S98 and the ingame_nba_winprob line)
are near-insensitive to the rail. The every-tick consumers are not: 18 modules
read this parquet, including `eval_gate/s86_nba_every_tick.py`,
`ssac/halflife.py`, `execution/entry_timing/{assemble,study}.py`,
`analytics_showcase/comeback_atlas.py` and `ingame/nba_mechanism_ladder.py`,
and each would see 53.947 pct fewer rows, concentrated in period 4 and OT.

## REBUILD NOTE (binding until the keyword lands)

Do NOT rebuild `data/cache/inplay_odds/nba_checkpoints_full.parquet` with the
current code. `python -m scripts.platformkit.venue_history.nba_checkpoints_full`
today would silently write 214,260 rows in place of 465,249, and every
every-tick result above would move with no recorded reason. If a rebuild is
needed before the change below lands, write to a NEW path and diff row counts
per game against the existing parquet first.

## PROPOSED (not applied) -- labelled keyword plus a state-age column

Proposal for `scripts/platformkit/venue_history/nba_checkpoints_full.py`
(platformkit, a safe tree; deliberately NOT applied by this measurement row):

    def build_checkpoints(directory: Path = PM_DIR, *,
                          max_staleness_s: float = 300.0
                          ) -> Tuple[pd.DataFrame, Dict[str, int]]:
        ...
            joined = join_game_states(states, pm_candles(doc, flip=flipped),
                                      max_staleness_s=max_staleness_s)

with `write()` taking and forwarding the same keyword, and `_main()` printing
the retained-row count beside the existing corpus size so a rebuild can never
shrink the corpus silently.

The lazier variant worth considering instead: keep `max_staleness_s=inf` at
BUILD time and add one additive `state_age_s` column, so no row is dropped at
build time and each of the 18 consumers applies whatever rail it wants as a
filter. That keeps the post-buzzer tail visible as data instead of deleting it,
and is additive under B2. Either way the choice is a real decision about what
the corpus means, so it is proposed here and left for the human.

## Scope and honesty

Read-only: no parquet rebuilt or overwritten, no `data/registry/` write, no
flag flipped, no pod contact, no network (0 cache misses; the fetch path was
replaced by a cache-only shim), no file under src/ kernel/ api/ intel/
scripts/team_system/ read or written, no edit to `nba_wallclock_join.py` (S145
owns it), no ledger charged (`backtest_fwer.jsonl` untouched at 18 rows), no
seal, no bar moved. Calibration substrate only; this row scores nothing and
claims nothing about accuracy or profit. Durable artifact:
`docs/evidence/harness/S146_checkpoint_corpus_stale_share_2026-09-03_measurement.json`.

NOT VERIFIED: the pre-rail semantics were reproduced by calling the CURRENT
`join_game_states` with an infinite rail rather than by importing the module
from base commit 4b7169973; the argument that these are identical is the
`lag > inf` reasoning above plus the exact hash match against the landed
parquet, which was itself built by the pre-S141 code. No independent verifier
has re-run this replay.
