# S10 -- MLB modern (2022+) close: CLOSED AT LIMIT

Verdict: **CLOSED AT LIMIT**. The bar (>= 60 pct join rate on the 11,179
`games_current.parquet` rows) is not reachable from any local source. Measured
overall rate **8.17 pct (913 / 11,179)**. The bar was NOT lowered.

Premise HOLDS in its literal form (`odds.parquet` still stops 2021-11-02) but its
reading is partly FALSIFIED: a modern local price series does exist for 2023,
2025 and 2026, so "no modern close exists" is false -- it is only unusable at
scale, for the reasons measured below.

## Step 0 -- every local MLB close candidate, measured on disk 2026-09-03

| artifact | rows | date range | note |
|---|---|---|---|
| `data/domains/mlb/odds.parquet` | 28,004 | 2010-04-04 .. 2021-11-02 | decimal `dec_close_home/away`; ends 2021 |
| `data/domains/mlb/games_current.parquet` | 11,179 | 2022-04-07 .. 2026-07-12 | THE denominator |
| `data/cache/inplay_odds/mlb_price_series.parquet` | 13,473,591 | game_date 2023-03-30 .. 2026-07-09 | the only modern quote source |
| `data/domains/mlb/*close*` | none | - | only `weather_vs_close_verdict.json` (a verdict, not prices) |
| `data/domains/mlb/probables.parquet` | 11,334 | - | has `day_night`, NO first-pitch clock |
| `data/domains/mlb/espn_boxscores.parquet` | 2 | - | has `start_time` but only 2 rows |

### `ts` unit finding (the spec's open question)

`ts` is **INT64 EPOCH SECONDS**, not nanoseconds. Median 1,760,842,744 reads as
2025-10-19 02:59:04 UTC under `unit="s"`; under `ms`/`us`/`ns` it reads as
1970-01-21 / 1970-01-01, which is why it "did not parse". Full range
1,680,134,416 .. 1,783,574,160 = 2023-03-30 .. 2026-07-09 UTC, matching
`game_date` exactly.

### Price-series structure (moneyline rows only)

| venue | rows | distinct games | seasons | sides | `close_time` |
|---|---|---|---|---|---|
| polymarket | 9,260,915 | 3,508 slugs | 2023: 744, 2025: 1,928, 2026: 836 | `home` ONLY | 100 pct NULL |
| kalshi | 3,556,162 | 972 events | 2026 only | both team tickers (935 events) | present, 1 per event |

- Polymarket's per-game key is `ticker_or_slug` (`mlb-<away>-<home>-<date>`);
  its `event_key` is a DAILY BUNDLE (`mlb-dailies-2023-03-30`) and must not be
  used as a game key.
- Kalshi `ticker_or_slug == event_key + "-" + side` for 100 pct of rows.
- `prob` is already a probability, so a two-sided pair is devigged by feeding
  `1/prob` as a decimal price through the EXISTING `close_join.close_column`
  (which calls `devig2`). No second devig was written.

### Is a PREGAME close derivable?

Only where a first-pitch clock exists locally. The **only** local clock is the
Kalshi event key `KXMLBGAME-<yy><MON><dd><hhmm><away><home>`, whose `hhmm` is
**ET**: median(`close_time` - start) = **2.85 h** under UTC-4 (p05 2.36, p95
3.82 -- a normal MLB game length), versus 6.85 h under a UTC reading. Kalshi's
`close_time` is the market's settlement close (~3 h AFTER first pitch), so it is
not itself a pregame anchor. Polymarket carries no `close_time` and no clock, so
a Polymarket-only game has NO certifiable pre-first-pitch tick.

Result: pregame close derivable = **yes for 2026 Kalshi games, no elsewhere**.
970 of 972 Kalshi tickers parse; all 970 have pre-start ticks; 935 have both
sides pre-start.

## Step 1 -- the limit

| season | spine rows | joined (devigged) | rate | one-sided PROXY |
|---|---|---|---|---|
| 2022 | 2,431 | 0 | 0.00 pct | 0 |
| 2023 | 2,437 | 0 | 0.00 pct | 0 |
| 2024 | 2,432 | 0 | 0.00 pct | 0 |
| 2025 | 2,434 | 0 | 0.00 pct | 0 |
| 2026 | 1,445 | 913 | 63.18 pct | 35 |
| **overall** | **11,179** | **913** | **8.17 pct** | 35 |

Fixed, unrecoverable parts of the denominator:

- **2022 (2,431 rows, 21.7 pct of the spine)** -- the price series starts
  2023-03-30. No local row exists at all.
- **2024 (2,432 rows, 21.8 pct)** -- the series has ZERO 2024 rows (seasons
  present: 2023, 2025, 2026 only). This was not in the spec's premise and is a
  second hard hole.
- **2023 + 2025 (4,871 rows, 43.6 pct)** -- Polymarket-only, one-sided, and with
  no first-pitch clock, so no pre-start quote can be certified.

Ceiling even if every Polymarket game could be timed and devigged:
3,508 + 972 games, capped by the spine, is still far under 60 pct. The bar is
unreachable without a source that is not on this box.

Drop counts by reason (from `derive_modern_close().attrs`):

```
unparsed_ticker         2      KXMLBGAME-26JUL071415MILSTLG1 / ...G2 (doubleheader suffix)
unknown_team_token      0
no_pre_start_quote      0
one_sided_proxy        35      kept and labelled PROXY_ONE_SIDED, NOT in the join rate
no_first_pitch_time  3055      Polymarket slugs with no Kalshi twin
ambiguous_spine_key   368      184 same-day doubleheader pairs in games_current
no_spine_match         22      Kalshi events with no matching spine row
bad_price_drop_count    0
null_close_count        0
```

## Calibration on the joined rows (n = 913, all 2026)

| series | Brier |
|---|---|
| devigged pre-first-pitch close | **0.245073** |
| corpus `p_base` | 0.248493 |
| corpus `p_home_elo` | 0.248493 |

`p_base` and `p_home_elo` are the same constant (0.534484) on this unit, so the
0.0034 gap is the close's whole sharpness over a constant. Orientation check:
mean close 0.5268 vs mean outcome 0.5170, and the flipped orientation scores a
worse 0.2684 -- the home/away seats are not transposed.

## Commands

```
python -m pytest scripts/platformkit/eval_gate/test_close_join_mlb.py -q   # 6 passed
python -c "import json; from scripts.platformkit.eval_gate.close_join_mlb import coverage_report_mlb; print(json.dumps(coverage_report_mlb(), indent=2, default=float))"
```

## NOT VERIFIED

- The derived quote is **NOT a settled exchange close**. It is the LAST TICK
  STRICTLY BEFORE the scheduled first pitch. Every row is labelled
  `vintage: PRE_FIRST_PITCH_TICK`.
- The 35 `PROXY_ONE_SIDED` rows carry the venue's vig and are NOT fair
  probabilities. They are excluded from the join rate and from every Brier here.
- The ET offset is a fixed UTC-4 (correct for the Apr-Oct window all 970 tickers
  fall in); a March or November Kalshi game would need a tz table.
- The Kalshi scheduled first pitch is the SCHEDULED time; a rain delay would
  make the true first pitch later, which only makes the "pre-start" claim more
  conservative, never less.
- No mechanism was re-scored in this gap. No ledger row was charged -- this is a
  coverage measurement, not a scored trial.
- 2023/2025 Polymarket coverage was NOT attempted with a heuristic start time;
  inventing one would fabricate a pregame anchor.
- `data/domains/mlb/**`, `close_join.py`, `corpus_cache.py`,
  `backtest_runner.load_states` and every eval_gate threshold are unchanged;
  `gate_corpus_mlb.parquet` was read read-only.
