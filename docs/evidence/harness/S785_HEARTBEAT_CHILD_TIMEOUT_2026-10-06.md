# S785 -- heartbeat child timeout (PAPER ONLY)

Date: 2026-10-06. Lane: S785 reliability lane (dispatcher allocated). Branch: cxp/S785-2026-10-06.

## Before-condition (measured from data/cache/paper_desk/journal/2026-10-06.jsonl, read 16:3xZ)

Three ticks were `tick refused step_refusals` on 2026-10-06:

| tick (UTC) | refusing step | decision / reason | duration_s | refusals | free RAM before |
|---|---|---|---|---|---|
| 02:28:06 | heartbeat:books_root | timed_out / child_timeout | 60.297 | child_timeout 1 | 3,148 MiB |
| 04:56:59 | heartbeat:books_root | timed_out / child_timeout | 60.281 | child_timeout 1 | 3,888 MiB |
| 15:56:31 | heartbeat:state_root | ran / due, exit 0, 0.25 s | 0.25 | child_exited_during_observation 1 | 4,866 MiB |

Only the first two are this row. The 15:56Z refusal is a different class: the child finished
cleanly and `paper_desk_process._owners` (scripts/platformkit/ops/paper_desk_process.py:117) hit
`psutil.NoSuchProcess` for a pid listed by the job between enumeration and inspection. It is NOT
fixed here (follow-up row needed; that file is not in this lane's ownership).

books_root step durations: 10-05 n=24, median 0.656 s, max 19.343 s; 10-06 n=34, median 0.36 s,
two at the 60 s deadline. At 02:28Z the sibling heartbeat:state_root also took 20.766 s. RAM was not
the limit (3.1-3.9 GB free), so the stalls are host I/O (cold directory cache, antivirus, load).

## What the child walks

`capture_watchdog.read_sources` (scripts/platformkit/ingame/capture_watchdog.py:82-110) on the
books root assesses only `kalshi/`. It enumerates `kalshi/*/**/_heartbeat.json` (a recursive glob
that lists every entry: 6,868 entries on 10-06, 9.5 GB; the 6 sport directories hold about 17
daily shards each, and most entries are per-ticker files under `<sport>/_trade_state/`, e.g.
2,742 for mlb, which the `**` descends into although no heartbeat lives there), then per source directory
reads `_heartbeat.json` (<= 64 KiB) and the last 64 KiB of today's UTC shard. It does not read old
shards; the cost that can exceed 60 s is the directory enumeration plus file opens under an I/O
stall, not data volume.

## Fix

Config route (capture_watchdog.py is seal-pinned by test_pinned_must_not_move_seal, so it is not
edited): `docs/operations/paper_desk_config.json` `timeouts_s.watchdog` 60 -> 180. The key is shared
by heartbeat:books_root and heartbeat:state_root (paper_desk_tick.py:224-227 passes "watchdog" to
`execute`, which reads `config["timeouts_s"][timeout]` at paper_desk_tick.py:115). 180 s is 9x the
largest completed run seen (20.8 s); the worst added tick time is 2 x 120 s, against a 30 min cadence
(the tick lock is liveness-based, and night steps already run ~1,800 s inside a tick).

Pin: tests/platformkit/ops/test_s709_desk_root.py CONFIG_SHA re-pinned
0a20c172... -> cd01a3a5... with an S785 authorizing comment.

## Tests (per file, RAM gate >= 2,500 MB, branch worktree)

test_s709_desk_root 36 passed; test_paper_desk_tick 14; test_paper_desk_start 34;
test_paper_desk_amendment 14; test_paper_desk_s522_light_ram 35.

## First live check (after landing)

The first tick after landing journals heartbeat:books_root with the unchanged argv; the check is
that no heartbeat row carries `child_timeout` for 48 slots, and any row with duration_s > 60 shows
decision ran/degraded rather than timed_out. NOT VERIFIED until landed (dispatcher lands).

## Not verified

- That a stalled run finishes inside 180 s (the two timed-out runs were killed at 60 s; their true
  length is unknown). If timeouts recur at 180 s, the next step is bounding the glob (non-recursive
  `kalshi/*/_heartbeat.json`, skipping `_trade_state/`), which needs a seal re-pin of capture_watchdog.py.
- The 15:56Z child_exited_during_observation refusal (separate row).
