# S645 (R3) step 0 -- series census + the landed S339 / S368 scanners on the September archive, 2026-09-30

Counts only. The anchored latent pricer is NOT built and is not authorised by this memo.
Probe lane: a Sonnet sub-agent of the RESEARCH lead, ~15:28-15:36Z, scripts and outputs in this
directory (`r3_series_census.py/.json`, `r3_s339_sum_to_one.py/.json`, `r3_s368_structural.py/.json`).
Archive: `data/cache/ingame_books_local/kalshi/<sport>/` daily shards 09-21..09-30 (09-30 still being
appended; complete lines only). Peak RSS: census 26 MiB, S339 109 MiB, S368 20 MiB (cap 400 MiB).

## A. Series census (`r3_series_census.json`)

- Distinct events per series across the archive: MLB KXMLBGAME 99, EXTRAS 99, F5 / F5TOTAL / F5SPREAD /
  F3 78 each, F7 79; NFL GAME 48, SPREAD 33; NBA GAME 3; WNBA GAME 4; tennis ATP match 107, WTA match 89,
  ATP Challenger match 265, ATP set winner 226; soccer 9-18 per league.
- BULK CADENCE IS ABOUT TWENTY MINUTES PER TICKER, not 11-30 s: the census median per-ticker gap between
  consecutive `snapshot_bulk` rows is about 1,045-1,215 s in every series. Re-measured by the lead on
  MLB 2026-09-29 KXMLBGAME (16 tickers, 556 gaps): p10 / p50 / p90 = 1,127.3 / 1,182.8 / 1,910.3 s.
  The slate's "bulk cadence about 11-30 s" (section 2, flagged UNVERIFIED there) is FALSIFIED.
- Focus `snapshot` cadence is about 5.2 s on focus days; focus rows exist only for MLB GAME, NFL GAME,
  NBA GAME and the tennis match series. Every MLB derivative family (F3, F5, F7, F5TOTAL, F5SPREAD,
  EXTRAS) has bulk and trade rows but NO focus snapshot.
- Player props: one series, KXMLBPITCH (1 event, 129 bulk rows, 09-21..09-26, no trades). No NBA
  points / rebounds / assists / threes series in the archive.

## B. S339 sum-to-one audit (`r3_s339_sum_to_one.json`; module 74b1e26aa, pure functions, unedited)

Run on winner families only (two-outcome GAME / match series; MLB F3 / F5 / F7 and soccer GAME as
three-ticker sets with a tie ticker, checked from ticker suffixes); never on strike ladders.
- Bulk feed: 44,672 aligned snapshots, 0 dropped by alignment, every family COHERENT; fee-netted
  complete-set violations 6 of 44,672.
- Focus feed: 92,162 aligned snapshots, 510 dropped by alignment, every family with data COHERENT;
  fee-netted violations 46 of 92,162 (MLB GAME 9 of 27,536; NFL GAME 2 of 2,244; ATP Challenger 35
  of 30,225).

## C. S368 structural scanner (`r3_s368_structural.json`; module 518a4f4b5): BLOCKED

The capture carries the structural fields (team id in custom_strike, floor_strike with strike_type
"greater" on totals and spreads) for all six MLB / NFL families checked, but the scanner requires a
REVIEWED definitions manifest with attestations no captured row carries (settlement_verified,
fee_schedule_verified, fee_mode, quantity, payout_unit, complete-set exclusivity, a settlement rule
id; S368 spec line 76: the manifest is reviewed, not inferred from ticker spelling). Events scanned 0.

## What this decides for R3 (per the slate's step-0 rule)

- Corpus 2 (live archive) can only carry derivative mids at the ~20-minute bulk cadence: the R3
  primary (15-minute reversion slope) and its 5-minute secondary are not measurable on it, and the
  derivative book-age exclusion (> 60 s) would drop nearly every tick. Unless derivative tickers
  are focused (a capture change, not research), corpus 2 is INSUFFICIENT for R3 as sketched.
- Structural coherence on winner sets is already COHERENT net of fees (0.01-0.05 pct of aligned
  snapshots). The pricer stays unbuilt; the lead does not proceed past step 0.

## Consequence for R2 (S644)

R2 planned "bulk mids for all listed games" on a 30 s grid with book age <= 30 s. At ~20-minute bulk
cadence that feed is unusable; R2 must run on FOCUS snapshots of served games (S644 AMENDMENT 1).

## NOT VERIFIED

- Whether the two-outcome families partition exactly (a void could leave the yes sum below 1).
- Event counts are per event-day in B (a game spanning midnight may count twice).
- The 2 s alignment window on bulk sweep rows was not validated; bulk timestamps are response_end_ts.
- Some census gap medians come from a 50,000-entry reservoir (estimates).
