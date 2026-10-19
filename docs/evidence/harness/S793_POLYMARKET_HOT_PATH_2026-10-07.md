# S793 -- polymarket capture hot path: TRACED + FIXED (PAPER ONLY; NOT ADOPTED)

Branch `cxp/S793-2026-10-07` (worktree). Adoption = a polymarket relaunch by the dispatcher
(21:05Z-21:55Z or 00:05Z+; the launcher has no -DryRun). Calibration/infrastructure only.

## Premise (re-verified 19:13Z)
No `polymarket_live_capture` process (psutil, self-excluded). Live shards: polymarket/mlb
2026-10-06.jsonl 381,940,512 B, 2026-10-07.jsonl 88,318,268 B; `_trade_state` 99 MB / 17,854 files.
Saved heartbeat 04:22Z: tick_duration_s 163.252, n_markets_tracked 727, n_requests_10min 1,720.

## Tracer
scratchpad `s793/trace_run.py`: one process; wraps builtins/io.open file objects (read, readline,
readinto, iteration), pathlib read_text/read_bytes, os.read, ssl recv/recv_into, plain recv_into,
plus a requests.Session.send body table (informational, not in the total). Call site = first 3
scripts/platformkit frames. Live read roots (state root, schedule, pointer, --sports mlb), output
root = scratch with COPIES of the two live shards (so own-shard reads are faithful and the live
shard + lock are untouched). Coverage = counted / psutil process read_bytes.

## BEFORE (base 9648e6f09) -- stopped at the 1.5 GB cap after 57.1 s, coverage 1.003
| bytes | calls | target | call site |
|---:|---:|---|---|
| 805,306,368 | 404,724 | own shard 2026-10-06.jsonl | local_capture_tail.py:37 tail_lines < local_capture_backfill.py:58 archive_tail < polymarket_live_trades.py:44 seed_group |
| 752,958,001 | 391,484 | own shard 2026-10-07.jsonl | same |
| 29,208,519 | 4 | state/mlb/2026-10-06.jsonl | state_shard_index.py:100 shard_fold (S788 first fold) |
| 21,673,026 | 3 | state/mlb/2026-10-07.jsonl | same |
| 7,412,030 | 1,011 | gamma-api (TLS) | polymarket_live_sources.py:68 discover_events |

1,558,264,369 of 1,616,760,189 counted bytes (96.4%) = seed_group. 805,306,368 = exactly 12 x 64 MiB.

**Root cause.** `polymarket_live_trades.seed_group` (line 26) called `archive_tail(root, sport,
now, metrics)`, which streams the last TAIL_BYTES = 64 MiB (local_capture_backfill.py:18) of
BOTH yesterday's and today's own shard and json-parses every line, once per newly seeded market,
then discards all rows except that market's. About 134 MB and about 4.8 s per seed. A fresh process
seeds every tracked market (727), so the first ticks read about 97 GB. That is CPU-bound json
parsing at the measured ~25 MB/s, and the first tick never finishes. The S788 state index was not
the cause: it reads 51 MB once.

## Fix (smallest correct change)
New `scripts/platformkit/ingame/polymarket_seed_tail.py` (159 LOC): one index per shard. It reads
only the bytes appended since the previous call and keeps, per event_ticker, the rows seed_group
reads (trade and closure rows as raw bytes, re-parsed on replay; other rows as the 3 fields
seed_group reads). It also keeps every bad-line drop in file order. `ticker_tail` replays exactly
what archive_tail gave seed_group for one ticker: same rows, same drop counters in the same order,
and the same `no readable archive evidence` raise. Segmentation mirrors tail_lines. The window
(start > size - TAIL_BYTES) is enforced by a prune. A shrink or inode change rebuilds the index,
and a rolled-off day is evicted. `polymarket_live_trades.py`: a one-line rewire of seed_group
(+ module import; 300 LOC, at the cap; the now-unused `archive_tail` import was dropped in the tier-B
correction round). No heartbeat key changed (a `seed_tail` bytes counter in the heartbeat is
PROPOSED only, because of the byte-pinned heartbeat test). Request rates are unchanged.

Resident memory (tier-B derived bound, NOT measured): trade and closure rows are kept as raw line
bytes, and every kept entry lies inside the 64 MiB window of its shard. That bounds the index at
about 72 MiB per shard (raw bytes plus tuple overhead) and about 145 MiB per sport in the worst
case (two day shards). A finished market's rows age out as the window slides. Live RSS was NOT
measured: the dispatcher reads capture RSS on the first relaunch tick against the 512 MiB cap.

Concurrency note: `_catch_up` reads to EOF, past the size taken from stat. If an append lands
between the stat and the read, the replay is a superset of archive_tail's window (the extra
newest rows are included). No row is lost. In this capture the writer and seed_group run in the
same single-threaded process, so it does not happen between seeds.

## AFTER (same scratch copies, fresh output root)
90 s run: counted 193,455,774, coverage 1.023. 600 s run (4-tick cap, wall-stopped): counted 196,559,574, coverage 1.028.
| bytes (600 s) | calls | target | call site |
|---:|---:|---|---|
| 69,538,558 | 36,117 | own shard 2026-10-07.jsonl | polymarket_seed_tail.py _segments < _catch_up < ticker_tail |
| 67,107,907 | 33,726 | own shard 2026-10-06.jsonl | same (one window build; the shard never grows) |
| 29,208,519 | 4 | state/mlb/2026-10-06.jsonl | state_shard_index.py:100 shard_fold |
| 21,837,218 | 3 | state/mlb/2026-10-07.jsonl | same |
| 7,419,645 | 998 | gamma-api (TLS) | polymarket_live_sources.py:68 discover_events |

Over the 600 s run, own-shard reads after the one-time 2 x 64 MiB window build were about 2.43 MB.
The run appended 2,442,520 B to the 10-07 copy, so steady-state seed reads equal the bytes
appended (KB per seed). That is far under 5 MB per tick. The new floor is a one-time ~134 MB plus
~51 MB (S788 state fold) per process start.

HTTP per endpoint (600 s, decoded body bytes / calls): gamma discovery pages 70.6 MB / 5 (7.4 MB
on the wire); gamma slugs 0.23 MB / 8; clob /book 1,205 calls; clob /markets meta 610 calls;
data-api trades 480 calls. Those 2,295 call-site counts over 600 s are a TRACE-WRAPPER COUNTING
ARTIFACT (retries and double counting in the wrapper), not real throughput and not a breach of
the governor. Every request goes through GovernedClient.get -> aimd.acquire. AIMDController
starts at 2.0 req/s, adds 0.25 every 60 s and has a CEILING of 3.0 (local_capture_limiter.py:46-60),
so 600 s allows at most about 1,650 calls. The governor is unchanged.

## Tests (one process per file)
`tests/platformkit/ingame/test_s793_seed_tail_parity.py` passes 22. It covers randomized
archive_tail-vs-ticker_tail parity across appends, window slides, torn tails, \r splits,
oversize lines and non-str tickers. It also covers the exact window-edge line, the all-invalid
raise, a torn tail longer than the window, read-only-appended-bytes, and seed_group end-to-end
parity (group state + metrics.errors) old vs new. Across 23 related files, 407 tests pass,
including test_local_capture_tail_stream 21, test_polymarket_live_trades 32,
test_polymarket_archived_ids_bound 7, and test_schedule_pointer_startup_union_1d 6 (heartbeat
byte pin).
Tier-B correction (P2): S599 test_j now runs seed_group through the REAL seed source
(seed_tail.ticker_tail, cache cleared), asserts archive_seen, and requires that the group state
and metrics.errors equal those from ticker_tail patched to the current and to the pre-S599
archive_tail.
Mutants 8/8 killed: prune bisect_left, no pos advance, trade rows compacted, raise removed,
rebuild every call, torn tail ignored, volatile unfiltered, no prune.

## NOT verified
- A live trace of the FINAL module. The AFTER traces ran the pre-simplification build, which had
  the same read path. The simplification (skip-first state replaced by the prune) is covered by
  the parity tests and mutants only. The 19:45Z window closed.
- A completed tick time. Even with the fix, the first tick did not finish within 600 s: it is now
  HTTP-bound (meta + 2 books + trades per market at the rate cap).
- RSS of the index on the live process. The bound above is derived, not measured.
- polymarket_live_trades.py is outside the S793 OWNS list. It was edited only because the trace
  points there.
NEW GAP: first tick after a restart is HTTP-bound (one market_meta per tracked market, ~727) -- persist meta_done across restarts.
