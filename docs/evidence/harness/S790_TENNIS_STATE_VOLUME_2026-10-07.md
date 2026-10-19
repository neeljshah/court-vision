# S790 -- tennis state volume (2026-10-07) -- MEMO, read-only, no code change -- PAPER ONLY

Verdict: **MEMO WRITTEN**. 99.88 pct of tennis state rows repeat the previous row of the same
match, and 99.66 pct come from matches that are not live. A change-only rule with a live
exemption is projected to cut the tennis shard from about 5.0 GB/day to about 0.05-0.1 GB/day.

## Method

This read ran after `docs/evidence/forward/nights/2026-10-06.json` existed (18:25Z) and after
paper_night pid 17412 had exited. It streamed the LAST 64 MiB (67,108,864 B) of
`data/cache/ingame_state_local_v2/state/tennis/2026-10-07.jsonl` (551,300,473 B at 18:25Z) line
by line after one seek, dropping the partial first line and any unterminated last line. No file
was loaded whole. The script lives in the session scratchpad only (s790_read.py).
The row schema comes from `local_state_capture._build_row`: the payload is `state` (tennis: a
single key, `players`) plus `status`, and the writer's own `state_changed` flag compares
(status, state) to the previous row of the same game.

## Numbers (window 04:13:47Z to 18:25:43Z; 69 minutes with rows because capture was down 04:23Z-17:26Z)

| metric | value |
|---|---|
| rows / parse errors | 84,027 / 0 |
| mean row bytes | 799 |
| distinct matches | 728 |
| rows/min, pre-outage (04:13-04:23, 11 min) | 41,803 rows, about 4,368/min = 728 matches x 6/min (10 s cadence) |
| rows/min, post-boot (17:26-18:25, 58 min) | 42,224 rows, median 728/min = 1 per match per min |
| rows per match per active minute (pooled) | 1.67 |
| same (status, state) as previous row of the same match | 0.9988 (n = 83,299 = rows minus first row per match) |
| writer `state_changed == False` | 0.9988 (n = 84,027) |
| state keys that changed when a row changed | `players`, 97 times |
| status | final 60,802 · pre 22,939 · live 286 |
| share of rows with status != live | 0.9966 |

The first post-boot tennis row is at 17:26Z. Together with the S788 memo, this bounds the
state child's startup recovery to about 17:09Z-17:26Z.

## PROPOSED dedupe / cadence rule (for a later build row; nothing changed here)

1. `status == live`: keep every poll (the latency and freshness receipts need each one).
2. `pre` and `final`: write a row only when (status, state) differs from the last WRITTEN row
   of that match. Write one keep-alive row per match every 30 min so that recovery's
   "latest row per game" and the polymarket `state_index` still see the match on both day shards.
3. `final`: stop polling, and stop the keep-alive, 60 min after the first final row.

Projected volume (728 matches, the 799 B mean row):
- Today, 10 s cadence: 728 x 6 x 1,440 = 6.29 M rows/day, about 5.0 GB/day. The 10-06 shard is
  3.75 GB for a partial day, so the order of magnitude agrees.
- Under the rule: keep-alives 728 x 48 = 34,944 rows, plus live polls (0.34 pct of 6.29 M =
  about 21,400 rows), plus changes (0.12 pct, about 7,500 rows). That is about 64,000 rows/day,
  about 51 MB/day. With rule 3 trimming the final keep-alives it is lower again. Taking the
  live share as uncertain (see below), the planning range is 0.05-0.1 GB/day.
- Knock-on effects: the 2-day recovery window and each polymarket full read shrink by the same
  factor of about 50-100.

## NOT verified

- The window covers 69 active minutes, which is mostly the 04:xxZ and 17:xx-18:xxZ hours. The
  live share during European-daytime tennis is likely higher than 0.34 pct, which would push
  the projection toward the top of the range. A 24 h census is needed before this rule is specced.
- Why the post-boot cadence is 60 s rather than the pre-outage 10 s (lane config versus
  post-recovery state) is not established.
- Whether any consumer needs non-live repeat rows (for example per-poll receipts for `pre`
  matches) is not audited. That audit is a precondition of rule 2.
