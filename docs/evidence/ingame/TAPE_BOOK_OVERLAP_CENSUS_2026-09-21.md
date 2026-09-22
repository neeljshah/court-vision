# Tape / book-depth overlap census (2026-09-21)

Vocabulary follows contract Q6; automated scan required.

## What was counted

A counts-only pass over the Kalshi per-trade tape (`_archive/kalshi_trades`)
and the dense top-of-book archive (`_archive/kalshi`, the primary
`book_depth/kalshi` path holds no files for this window so the archive path
was used) for venue dates 2026-07-11..2026-07-17, mlb and wnba only. Per
ticker: distinct sized trades, taker-side counts, book-snapshot cadence,
share of snapshots with a valid two-sided quote, trades falling inside the
book span, and staleness (seconds since the latest prior book snapshot) at
the trade level. Separately, a per-day capture-gap census of the tape's own
poll cadence. No price, return, markout, fill, or outcome statistic was
computed anywhere in this pass.

## Headline counts

- mlb: 339 tickers / 91 events, 35,768 distinct sized trades in-window.
- wnba: 267 tickers / 53 events, 32,547 distinct sized trades in-window.
- Every deduplicated trade in the window carried a non-null positive size
  (the null-count defect described for 07-09/07-10 does not reach this
  window).
- Middle eligibility rule (>=30 sized trades, median book cadence <=120s,
  stale-or-no-prior share <=0.5): mlb 22 tickers / 16 events pass; wnba 36
  tickers / 18 events pass. Neither sport reaches the 30-EVENT minimum at
  this cell (16 and 18 events respectively).
- Loosest cell (>=10 sized trades, cadence <=300s, stale share <=1.0): mlb
  41 events / 86 tickers; wnba 31 events / 88 tickers.
- Strictest cell (>=100 sized trades, cadence <=60s, stale share <=0.25):
  mlb 4 events / 6 tickers; wnba 8 events / 12 tickers.

## Capture gaps (tape poll cadence, per day; both sports track together)

- 2026-07-15: largest gap ~647.3 min (mlb) / ~609.3 min (wnba), roughly a
  10-hour outage window around 02:31-12:41 UTC.
- 2026-07-16: largest gap ~384.4 min (~6.4h), 05:21-11:46 UTC, plus four
  more gaps over 10 minutes later the same day.
- 2026-07-13: one gap of ~21-22 minutes; 07-11/07-12/07-14/07-17: no gap
  over 10 minutes (sub-4-minute worst gaps).
- 19 total gaps over 10 minutes across both sports, all on 07-13/07-15/07-16.

## NOT VERIFIED

- No price, spread, fill, or return statistic was checked for accuracy or
  plausibility -- none was computed.
- Whether the 07-15/07-16 capture gaps correspond to a real venue outage or
  a local poller/process gap was not investigated.
- Ticker-to-underlying-game identity (e.g. that all suffixes under one event
  key truly share one physical game) was not cross-checked against a
  schedule source.
- Event-level pass counts fall short of the 30-game minimum under the middle
  rule for both sports; whether a relaxed cell or per-event ticker
  aggregation changes that was not assessed here.

Artifact: `docs/evidence/ingame/tape_book_overlap_census_2026-09-21.json`
Script: `scripts/platformkit/ingame/tape_book_overlap_census.py`
