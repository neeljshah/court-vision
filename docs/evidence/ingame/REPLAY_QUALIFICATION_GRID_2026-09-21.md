# Replay qualification grid (2026-09-21)

Vocabulary follows contract Q6; automated scan required.

## What was counted

Counts-only pass over the Kalshi per-trade tape and the dense top-of-book
archive for venue dates 2026-07-11..2026-07-17, game-winner markets only
(ticker prefix ending GAME), mlb and wnba. Reads timestamps, tickers, sport,
trade_id, taker_side, and the PRESENCE of a trade size / best_bid / best_ask
only -- never a price, size, or outcome VALUE, never where a price went.
Population comes from the book archive (events with zero prints included).
Scheduled start decoded from the ticker (America/New_York); WNBA tickers
carry no HHMM group anywhere in this window, so all 20 wnba events get
`start_unknown` and no window. Window = [start, start+60min]. Three tiers:
primary (bin share 0.80/0.90, gap 45/90/120s), relaxed_1 (0.80/0.80,
60/120/180s), relaxed_2 (0.60/0.60, 90/180/300s). "Passing (b)" requires
every ticker of the event to individually clear the tier.

## Result table

| sport | events (pop) | decodable start | primary a/b/both | relaxed_1 a/b/both | relaxed_2 a/b/both | dates (primary) |
|---|---|---|---|---|---|---|
| mlb  | 50 | 50 | 2/0/0 | 2/0/0 | 2/0/0 | 0 |
| wnba | 20 |  0 | 0/0/0 | 0/0/0 | 0/0/0 | 0 |

Grid (c) share of 60 grid points/window with a later book capture available:
mlb h=30s 0.008, h=120s 0.010, h=300s 0.010 (pooled, 2 mlb events); wnba null.

## Binding constraint

Two independent, verified blockers -- neither is trade scarcity per se:

1. The trade tape's last recorded trade/capture, all 7 shards and both
   sports, is 2026-07-17T05:16 UTC (day 6 of the intended 7): any scheduled
   start after that has zero sized prints by construction -- 45 of 50 mlb
   events. Only the 2 events starting 07-12 clear (a).
2. Those 2 still fail (b): book-poll cadence that early runs ~89s median /
   ~226s p95 per ticker (checked directly against the book archive), missing
   every tier's cadence bar; one ticker side had zero captures in-window.
3. WNBA is blocked upstream of both: no WNBA GAME ticker in this window
   carries a decodable HHMM, so 0 of 20 wnba events ever get a window.

## Does 30 games per sport qualify?

No, for both sports, at every tier tested, including the loosest
(relaxed_2). mlb: 0 of 50 events pass (a)+(b) at any tier (2 pass (a)
alone). wnba: 0 of 20 events can even be evaluated (no decodable start).

## Trade hygiene

- 1,850,541 total trade rows; 68,476 globally-unique trade_ids.
- 1,782,065 identical repeats (same trade_id, byte-identical row minus
  capture `ts`) vs 0 conflicting duplicates -- trades are immutable once
  recorded, so every repeat matches.
- 245,927 rows (13.3%) where the shard filename's date differs from the
  trade's own trade_ts venue date (midnight-boundary re-capture).
- 0 unparseable trade_ts values.

## NOT VERIFIED

- Whether the 2026-07-17T05:16 UTC cutoff is a real venue pause or a local
  poller/process stop was not investigated.
- Whether a WNBA ticker ever carries an HHMM group outside this window: not
  checked. Price, spread, fill, or outcome accuracy: not checked, not computed.
- Whether relaxing "all tickers must pass (b)" to per-ticker (vs per-event)
  changes the count was not assessed.

Artifact: `docs/evidence/ingame/replay_qualification_grid_2026-09-21.json`
Script: `scripts/platformkit/ingame/replay_qualification_grid.py`
