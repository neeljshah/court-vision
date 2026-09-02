# S100 -- order-book microstructure on the scored MLB ticks (STEP 0 premise + descriptive)

**NOT VERIFIED.** Written by the S100 lane, not by a verifier. Every number below is
reproducible from the artifact and the module; nothing here has been re-derived by a second
party. Calibration language only; no arm was run, no prereg was sealed, no ledger row was
charged, no K was read.

- Module: `scripts/platformkit/eval_gate/s100_microstructure.py` (300 LOC)
- Test: `python -m pytest tests/platformkit/ingame/test_s100_microstructure.py -q` -- 11 passed
- Reproduce: `python -m scripts.platformkit.eval_gate.s100_microstructure`
- Artifacts: `data/cache/eval_gate/s100_microstructure_2026-09-03.json` and
  `..._series.csv` (2,835 rows x 19 cols; Q9 differential archive)
- Contract self-check: VERIFIER_CONTRACT sections B and Q -- see the last section.

## Verdict

**PREMISE FALSIFIED AT TICK GRAIN. Part (b) NOT RUN -- the row's own STEP 0 stop rule fired.**
The most-covered feature reaches **18 SCREEN-side games**, below the row's bar of 20, so only
the descriptive next-tick-sign table was produced. No arm, no outcome Brier, no S94-style
recalibration null, no charge, no prereg draft. The bar was **not** lowered (Q3).

The row's premise -- "two depth stores (277,888 rows ... + 2,070,472 trades) and depth_history
(107,356 rows / 765 tickers) overlap the scored MLB ticks on 2026-07-09..07-12" -- is true at
STORE grain and false at TICK grain. Those headline row counts are all-sport totals; the
MLB moneyline-series subsets are 8-20x smaller, and the depth captures for the games that do
share a ticker are almost entirely **pre-game snapshots taken hours before the first scored
tick**, so an as-of feature exists on 0.4 to 1.7 pct of scored ticks, not on the corpus.

## STEP 0 premise -- schemas, rows, tickers, time ranges

Scored side: `data/cache/ingame_grade_joined/mlb`, **78,986 ticks / 227 games**,
2026-06-20T00:51:03Z .. 2026-07-12T23:02:46Z. Fields used: `game_id` (= the Kalshi event
ticker), `ts`, `market_prob` (home side), `outcome`. Next-tick move = the next
`market_prob` within the same game.

| store | rows (mlb, `KXMLBGAME-*` only) | market tickers | event tickers | ts range | events sharing a scored game |
|---|---|---|---|---|---|
| `book_depth/_archive/kalshi` | 119,574 | 231 | 123 | 2026-07-04T03:05:24 .. 2026-07-17T05:16:03 | **68** |
| `book_depth/_archive/kalshi_trades` | 940,765 | 105 | 56 | 2026-07-09T01:05:13 .. 2026-07-17T05:15:48 | **9** |
| `depth_history/mlb` | 19,789 | 390 | 195 | 2026-07-05T03:32:50 .. 2026-09-02T04:50:26 | **89** |

Schemas as read: `book_depth` = `ts, venue, ticker, best_bid, best_ask, spread_bp,
book_thinness, n_levels, last_trade_ts, trades_last_5m, stale_quote_flag, sport`;
`kalshi_trades` = `trade_ts, trade_id, price, count, taker_side, ts, ticker, sport`;
`depth_history` = `ts, sport, ticker, event_ticker, yes_bids, yes_asks, depth_totals, source,
source_url, fetched_at, capture_version`.

Ticker join: the scored store is keyed by EVENT ticker, both depth stores by MARKET ticker
(`<event>-<TEAM>`). Kalshi names an event `<date><time><AWAY><HOME>`, so the home market
ticker is the suffix that ENDS the event's team blob (a doubleheader's trailing `G1`/`G2` is
stripped first). **195 of 195** MLB event tickers seen in the depth stores resolve a unique
home code. Where only the away ticker was captured the feature is used with its sign flipped.

**A second premise from gap map L15 is falsified.** L15 records "a reduced form is already on
the ticks: `spread_bp`, `book_thinness`, `stale_quote` on 25,585 of 79,566 `ingame_grade/mlb`
rows (32.16 pct)". The KEYS are present on 25,585 rows; the VALUES are **null on 25,585 of
25,585 (100 pct)**. There is no reduced microstructure form on the ticks, so the standalone
depth stores are the only substrate.

## Tick-grain overlap -- the number the row asked for first

Coverage = a scored tick for which a feature row exists **strictly before** it and no older
than the freshness cap. `flow_60` / `flow_300` do not depend on the cap (their own window
defines them); `last_trade_dir` does.

| feature | cap 300 s: ticks / games | cap 60 s: ticks / games | **SCREEN side, cap 300 s** | SCREEN, cap 60 s |
|---|---|---|---|---|
| `depth_imbalance` | 1,346 / **35** | 65 / 26 | 649 / **18** | 30 / 13 |
| `spread_bp` | 793 / 3 | 734 / 3 | 394 / 2 | 364 / 2 |
| `last_trade_dir` | 455 / 3 | 293 / 3 | 194 / 2 | 124 / 2 |
| `flow_60` | 293 / 3 | 293 / 3 | 124 / 2 | 124 / 2 |
| `flow_300` | 455 / 3 | 455 / 3 | 194 / 2 | 194 / 2 |

Of 78,986 scored ticks that is **1.70 pct** (imbalance, 300 s cap) down to **0.37 pct**
(60 s trade flow). Median feature age: 194 s at the 300 s cap, 37 s at the 60 s cap -- the
imbalance is a several-minute-stale snapshot, not a touch read at the tick. The covered dates
are 2026-07-05, 07-07, 07-08, 07-10, 07-11, 07-12 (six days, one window).

Partition (S82 rule, `foundry.tiers.partition_corpus`, basis `corpus_unit`, seed 0):
114 SCREEN games / 113 VERDICT games,
`screen_sha256 = aa8f24af259299d1173b4b40c6070b932f019fe9fd8a985e5560c2f568c54c84`,
`verdict_sha256 = 8429a7b3d12cafd34595850e9e8e9e2064459937c58732f11f25cc3b5278f1c7`.
The VERDICT side was never read.

**18 < 20 -> stop.** Part (b) is not run and nothing is charged.

## Feature definitions (all read strictly before the tick, home-oriented)

- `depth_imbalance` = (size at the best YES bid - size at the best YES ask) / their sum, from
  the `depth_history` ladders. `yes_asks` is the RAW Kalshi `no_dollars` ladder
  (`depth_capture.py:130`), so both sides take their own max price and the imbalance is the
  size ratio at the touch. **Derivable only here** -- `book_depth` keeps a top-3 aggregate
  (`book_thinness`) and no per-level sizes.
- `spread_bp`, `book_thinness`, `stale_quote` = the last `book_depth` snapshot before the tick.
- `last_trade_dir` = +1 if `taker_side == "yes"`, -1 otherwise, at the last trade before the
  tick.
- `flow_60` / `flow_300` = the signed trade COUNT in the open interval (t-w, t). `count` is
  null on 2.8 pct of trade rows, so this is a count, never a signed size. Stated as a limit,
  not worked around.

**The guard** (`as_of`, tested): the returned row must be STRICTLY before the tick; a row
stamped at the tick is a future read and is refused. `test_as_of_is_strictly_before_the_tick`,
`test_as_of_respects_the_freshness_cap` and
`test_as_of_never_returns_a_row_at_or_after_the_tick` cover it, including mis-ordered input.
Purging on settlement does not apply: no model was fit, so there is no train fold to purge.

## (a) Next-tick sign -- descriptive only

Does `sign(feature)` call the sign of the market's next move? Accuracy with a game-clustered
DM CI on `1{correct} - 0.5` (so the CI is quoted against 0.50). Held quotes (zero next-tick
move) are dropped and counted. Both partition sides are pooled here because this table is
descriptive and feeds no arm.

| cap | feature | n | games | accuracy | CI95 (accuracy - 0.50) | p | excludes 0.50 | zero-move dropped |
|---|---|---|---|---|---|---|---|---|
| 300 s | `depth_imbalance` | 305 | 25 | 0.5508 | [+0.0000304, +0.10161] | 0.0499 | yes | 1,037 |
| 300 s | `last_trade_dir` | 162 | 3 | 0.5370 | [-0.51200, +0.58607] | -- | no | -- |
| 300 s | `flow_300` | 162 | 3 | 0.5309 | [-0.91034, +0.97206] | -- | no | -- |
| 300 s | `flow_60` | 142 | 3 | 0.5000 | [-0.44740, +0.44740] | -- | no | -- |
| 60 s | `depth_imbalance` | 20 | 15 | 0.5500 | [-0.23246, +0.33246] | 0.7099 | no | 45 |
| 60 s | `last_trade_dir` | 144 | 3 | 0.5139 | [-0.78760, +0.81538] | -- | no | -- |
| 60 s | `flow_300` | 162 | 3 | 0.5309 | [-0.91034, +0.97206] | -- | no | -- |
| 60 s | `flow_60` | 142 | 3 | 0.5000 | [-0.44740, +0.44740] | -- | no | -- |

**Read this as a null.** One cell of eight clears 0.50 at p = 0.0499 -- exactly the count a
family of eight uncorrected tests produces by chance, and no multiplicity control was applied
because nothing here is a claim. The same feature at the tighter 60 s cap (n = 20) does not
clear. The signal, if any, sits on a feature a median 194 s stale, on six days, on one venue,
with both partition sides pooled. Next-tick sign is not calibration and not outcome skill: an
accuracy is not an improvement in Brier and never a dollar quantity.

## (b) Outcome -- NOT RUN

Not run, by the row's own STEP 0 rule (18 SCREEN games < 20). Nothing was fit, nothing was
scored against `e4`, no S94-style global recalibration null was built, no tick-weighted Brier
or clustered DM interval exists for an arm, and `attach_informative_summary` was therefore not
called -- there is no paired-loss series to summarise. `prereg_draft_warranted = false`,
`arm_run = false` in the artifact. The +0.004 bar is recorded in the artifact unchanged as the
bar an arm would have faced.

## What would move this

The blocker is capture, not code. `depth_history` writes one orderbook row per active ticker
per poll and its dense body ends 2026-07-27; `book_depth` and `kalshi_trades` end 2026-07-17,
after the scored corpus. To reach 20+ SCREEN games the depth poll has to run DURING games that
the grader also scores, on the same days. The module is ready for that: point it at a longer
overlap and the same command produces the same tables with a real n. `depth_history` remains
in no retention policy (`sidecar_retention.DEFAULT_POLICY` covers `book_depth` only).

## Contract self-check (B and Q)

- B1 no circular metric: coverage is counted on the whole scored corpus; the excluded set
  (ticks with no as-of row, and held quotes) is named and counted in the artifact.
- B2 additive: one new module, one new test, no column renamed or removed anywhere.
- B3 no fall-through loss: a missing depth row yields `None`, never a dropped or quarantined
  tick; the tick stays in every denominator.
- B7 no head slices: every scored tick in all 227 games is walked; nothing is sampled.
- B9 no degenerate denominator: the cluster is the game (25 clusters on the one cell with a
  CI), and both the tick and the game counts are printed for every cell.
- B10 no bar moved: `MIN_GAMES_TO_ARM = 20` and `IMPROVEMENT_BAR = 0.004` are the row's own
  values, in the artifact byte-for-byte.
- Q1/Q2 no seal, no charge, no K read -- a SCREEN premise is a non-finding.
- Q4 not applicable: nothing was scored out of sample because no model was fit.
- Q5 labelled `SINGLE-WINDOW` in the artifact and here (six days, one venue).
- Q6 calibration language only; none of the retracted figures appears.
- Q7 the n's above are SAMPLED, and the sampling rail is why (b) stopped.
- Q8 premise re-measured first: the row's tick-grain premise is FALSIFIED and L15's
  "reduced form on the ticks" is FALSIFIED. A falsified premise is a valid result.
- Q9 the per-tick series is archived beside the summary
  (`s100_microstructure_2026-09-03_series.csv`: game, ts, date, market, next_market, d_market,
  y, every feature, both feature ages, the freshness cap, `is_screen`, `cluster_id`), so every
  table above is recomputable from the artifact alone.
