# S643 (R1) step 0 -- book-only live-match census, 2026-09-30

Counts only; no scored quantity. Probe `r1_step0_census.py` (this directory), run 2026-09-30
~15:24-15:30Z on the Kalshi books archive `data/cache/ingame_books_local/kalshi/<sport>/`
(daily shards 09-21..09-30, no 09-27 shard; the 09-30 shard was still being appended).
Outputs: `r1_step0_census_{tennis,mlb,nfl}.json`. Peak RSS: tennis 152.5 MiB, MLB 82.3 MiB,
NFL 59.9 MiB (cap 400 MiB, psutil check every ten thousand lines).

## Method

Line-streamed; `snapshot_bulk` rows skipped by a byte check before decode; focus `snapshot`
rows with `market_state == "live"` and `trade` rows parsed with the LANDED S550 parsers
(`exec_quality_audit_pool.parse_snapshot` / `parse_trade`, read-only import; trade dedupe by
trade_id over the day plus the previous day). A focus snapshot counts as depth only when both
top-five ladders are non-empty. Status per ticker mirrors S550 `game_record` WITHOUT live state
(tennis has no linked state; this is the book-only arm R1 uses for tennis):
NO_DEPTH (fewer than twenty live ladder snapshots) > TAPE_MISSING (no deduped print between
the first and last live ladder snapshot) > OK. A match (event_ticker) is OK when any of its
tickers is OK; its day is the UTC day of its first live ladder snapshot. A stricter
"dense" count requires one ticker with at least ten minutes of ladder coverage at gaps of at
most ten seconds (the R1 floor of twenty join instants on the thirty-second grid needs ten
minutes).

## Counts

| sport | events with any live ladder snapshot or print | OK | TAPE_MISSING | NO_DEPTH | OK and dense (>= 10 min) |
|---|---|---|---|---|---|
| tennis | 423 | 48 | 1 | 374 | 27 |
| MLB (book-only, all KXMLB series) | 358 | 19 | 3 | 336 | 14 |
| NFL | 4 | 0 | 0 | 4 | 0 |

- Tennis OK matches per first-live UTC day: 09-21 17, 09-22 8, 09-24 2, 09-25 8, 09-28 6,
  09-29 7 (six of nine shard days carry any). By series: ATP Challenger 19, ATP 14, WTA 15;
  KXATPSETWINNER tickers are all NO_DEPTH (260).
- Tennis OK tickers: ladder coverage p10 / p50 / p90 = 0.0 / 19.4 / 413.6 minutes (total
  9,380.4 minutes); in-window prints p10 / p50 / p90 = 17 / 198 / 7,360.
- Most tennis focus snapshots carry an EMPTY book: on 09-24, 6,279 of 7,389 focus snapshots had
  every price, size and ladder field null (counter `snapshot_unparsed` = 78,130 over the archive).
- MLB book-only OK tickers are all KXMLBGAME (36 OK tickers); every derivative series ticker is
  NO_DEPTH (bulk only). MLB OK matches per day: 09-21 2, 09-22 5, 09-24 8, 09-25 3, 09-29 1
  (the top-five ladder is present only in the first focus hour, S598).
- NFL: zero live focus snapshots in the archive (5,420 focus snapshots, all pregame); S502 blocks
  linking.

## Decision this census feeds (R1 corpus plan)

The slate rule: tennis qualifies if it gives 30 or more OK matches by the seal date plus 14 days.
It already holds 48 OK matches (27 dense) in six live days, about 3 dense matches per live day,
so the rule is met on the S550 ladder now and on the dense count within days. R1 therefore runs
TWO corpora, MLB (with state) and tennis (book-only), never pooled. NFL is out of scope for R1.

## NOT VERIFIED

- Whether the empty-book tennis focus snapshots are illiquid live markets or settled ones.
- Per-match fill counts under the S550 touch simulator (the 300-fills-per-arm floor); prints in
  window are a proxy only.
- Whether tennis focus coverage persists after the S598 books adoption.
- The MLB book-only count is not the S550 served-game count (no state gate here).
