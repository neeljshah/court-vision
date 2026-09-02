# S93 -- price every MLB in-play tick: PREMISE FALSIFIED, CLOSED AT LIMIT

**Date** 2026-09-03 | **Lane** signals-ingame | **Tier** premise census (a NON-FINDING) |
**Verdict** CLOSED AT LIMIT | **edge_claimed** false | **Charge** none (no prereg seal, no K
read, no ledger row, no `_charge_ledger`) | **Label** SINGLE-WINDOW (one corpus)

Reproduce: `python -m scripts.platformkit.eval_gate.s93_mlb_every_tick`
Artifact: `data/cache/eval_gate/s93_mlb_every_tick_premise_2026-09-03.json`
Test: `python -m pytest tests/platformkit/ingame/test_s93_mlb_every_tick.py -q` (4 passed)

---

## Step 0 -- the premise table

The S93 row asserts a 12,772,159-row / 3,780-event MLB moneyline corpus "with no model
series", implying the model series is the only missing half. **It is not.** The market half
carries no state at all, and the state half does not exist on disk for 95 pct of those
events.

| Fact | Measured |
|---|---|
| Corpus path | `data/cache/inplay_odds/mlb_price_series.parquet` |
| Schema | `sport, venue, game_date, ticker_or_slug, event_key, market_type, side, ts, prob, traded, close_time, result_where_known` |
| Rows (all markets) | 13,473,591 (moneyline 12,817,077 / total 526,057 / spread 130,457) |
| **Moneyline rows with a known outcome** | **12,772,159** |
| **Events** | **3,780** (polymarket 2,808 / kalshi 972) |
| Date range | 2023-03-30 .. 2026-07-09 (2023: 56 events, 2025: 1,924, 2026: 1,800) |
| Tick cadence | median inter-tick gap **60 s** (p10 0 s, p90 62 s) |
| Ticks per event | median 2,783, mean 3,379 |
| Quoted span per event | **median 46.72 h** -- the store quotes a game market ~2 days before first pitch |
| **Game STATE on a tick** | **NONE.** No score, inning, half, outs, count or base column exists in the schema. A tick is a price and a timestamp. |

### Where state could come from (all on-disk, no fetch)

| Source | Key | Extent | State depth |
|---|---|---|---|
| `data/cache/ingame_grade_joined/mlb` | Kalshi ticker | **227 games**, 2026-06-20..2026-07-12 | rich (`score, inning, half, outs, base, bos, re, count, pitch_count, tto`) -- this is S82's own corpus |
| `data/domains/mlb/espn_wp/_archive/*_series.json` | ESPN event id **+ `capture_name` = the ticker** | 117 games, 2026-06-19 on | wallclock + score only |
| `data/cache/ingame_grade/mlb` | ESPN event id, **no on-disk bridge to a ticker** | 405 games, 2026-06-19..2026-09-01 | `score, inning, half` only |
| `data/domains/mlb/gumbo_live/_archive` | statsapi `game_pk`, no on-disk bridge | 123 games / 44,015 rows, 2026-07-04..07-15 | rich, `captured_at` wall clock |
| `data/cache/statcast/savant_full__*.parquet` | `game_pk` | 2023-2026, ~700k pitches/season | full state for every pitch but **no wall-clock column in any of its 42** -- a 60 s market tick cannot be placed in it |
| `data/domains/mlb/_raw/statsapi` | -- | schedules only (`sched_2022..2026.json`, 15 MB) | none |

`scripts/platformkit/ingame/game_pk_bridge_live.py` is a **live-feed** module (it GETs
statsapi, ESPN and Kalshi for one date); it is not an on-disk bridge and this lane does not
fetch. The only on-disk ESPN-id -> ticker bridge is the `capture_name` field in the 117
`espn_wp` series files.

### Reconstruction share

| Quantity | n | share of 3,780 |
|---|---|---|
| Distinct tickers with per-tick state anywhere on disk | 240 (227 joined + 13 further from `espn_wp`) | -- |
| **Events of the 3,780 for which state at tick time is reconstructable** | **177** | **4.68 pct** |
| Events inside the state-capture window (2026-06-20..2026-07-09) | 354 | 9.37 pct |
| Events outside any capture window -- state impossible from disk | **3,426** | 90.63 pct |
| ESPN-keyed state captures with no on-disk ticker bridge | 392 | -- |

**177 < 300, so this lane stops at the premise per its own STOP rule. No screen was run, no
enlarged tick store was written, no prereg drafted.**

## Why the enlargement cannot resolve the bar even at its ceiling

The S82 interval is clustered on **games**, so it shrinks as `1/sqrt(n_game_clusters)`;
adding ticks inside a game does not narrow it (S82/S43 already measured ICC 0.32-0.37,
design effect 97-112, n_eff 420-483 of 47,104 ticks).

| Step | Value |
|---|---|
| S82 SCREEN side | 41 game clusters, best-feature half-width **0.0053035** (`tick_index_in_game` CI [-0.001971, +0.008636]) |
| SCREEN share of scored games | 41 / 227 = 0.1806 |
| Clusters needed for the 0.002 target | **289** (= 41 x (0.0053035 / 0.002)^2) |
| Scored games needed | **1,601** |
| Reachable from the 177 reconstructable events | **32 clusters** |
| Reachable from all 240 state-bearing tickers | **43 clusters** (half-width ~0.00518) |

So the whole on-disk enlargement moves S82's screen side from 41 clusters to at most 43
(+5 pct) and its half-width from 0.005304 to about 0.00518. The bar stays unresolvable.
The bar itself was **not moved** (BAR 0.004, target half-width 0.002, both byte-identical to
the register row; Q3).

## Secondary correction to the row's own arithmetic

The "24x" in the S93 row is a **tick** ratio, and most of those ticks are not in-play. On an
evenly spaced sample of 30 of the 173 reconstructable events (A3 -- never a head slice), the
13 whose state capture spans a plausible single game (<= 5 h) have a median of **8.6 pct**
(min 0.3, max 11.9) of their price-series ticks falling inside that window. Scaled to the
corpus that is roughly 1.3M in-play ticks, not 12.8M -- and, as above, tick count is not the
binding quantity anyway.

## The acquisition decision this leaves for Neel

The market half is complete and free. **The state half is the constraint**, and exactly one
acquisition unlocks it retroactively:

1. **Backfill statsapi historical game feeds.** `scripts/platformkit/ingame/mlb_event_reactive.py`
   already parses per-play and per-pitch wall clocks out of that payload
   (`about.startTime` :108, `playEvents[].endTime or .startTime` :116) from
   `https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live` (`gumbo_mlb_poller.py:53`).
   One keyless public GET per game, ~3,780 games, keyed by `domains/mlb/game_pk_bridge`
   (date + team pair). This is the only route that puts state on the 2023-2026-06 tail, i.e.
   on the 3,426 events no live capture can ever reach. It is a **network acquisition**, which
   this lane is forbidden to make -- Neel's call.
2. **Or keep capturing forward.** The joined store gains ~15 games/day when the pollers run;
   1,601 scored games is roughly 90 further capture-days beyond the 227 already held, and it
   requires the retention policy to stop trimming the tick stores (L5 measured
   `data/cache/inplay_history/` down to a single date and `ingame_shadow_history/` to 34 files).

Option 1 is the decision; option 2 is a policy change that resolves the bar next season at
the earliest.

## NOT VERIFIED

- The 289-cluster / 1,601-game requirement is a **planning extrapolation** from S82's single
  measured half-width under a `1/sqrt(n)` assumption, not a measured interval at that n.
- The 8.6 pct in-play tick share is a **30-event evenly spaced sample**, not a corpus census,
  and it uses the joined store's own tick span as the game window (that store itself quotes
  pre-game, so the window is an upper bound on the game and the share is an upper bound too).
- The 240-ticker state universe counts a ticker as state-bearing if a file exists for it; no
  per-tick completeness or freshness check was run on the 13 `espn_wp`-only tickers, and
  those carry score-only state (4 of S82's 14 features), so their effective contribution is
  below their count.
- No claim is made about what a model series WOULD score on the enlarged corpus. Nothing was
  scored. SINGLE-WINDOW (one corpus, MLB).
