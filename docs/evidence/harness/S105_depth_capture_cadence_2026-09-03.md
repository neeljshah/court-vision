# S105 -- depth-capture cadence and window (STEP 0 premise + capture-side fix)

**NOT VERIFIED.** Written by the S105 lane, not by a verifier. Every number below is
reproducible from the modules and the on-disk stores named beside it; nothing here has been
re-derived by a second party. Calibration language only: no arm was run, no prereg was
sealed, no ledger row was charged, no K was read, no bar was moved.

- Modules changed: `scripts/platformkit/ingame/ingame_book_depth_retention.py` (+`live_first`),
  `scripts/platformkit/ingame/ingame_book_depth_poller.py` (1 call site),
  `scripts/platformkit/ingame/ingame_enrichment_runner.py` (module-level poller state),
  `scripts/platformkit/odds_provider/depth_capture.py` (1 listing filter).
- Tests (per file only): `test_ingame_book_depth_retention.py` 7 passed,
  `test_ingame_book_depth_poller.py` 14 passed, `test_ingame_enrichment_runner.py` 11 passed,
  `scripts/platformkit/odds_provider/test_depth_capture.py` 17 passed.
- Nothing was written to the pod. Nothing under `src/`, `kernel/`, `api/`, `intel/`,
  `scripts/team_system/` or `data/registry/` was read or written. The FWER ledger was never
  opened.

## Verdict

**PREMISE PARTLY FALSIFIED (Q8), ROOT CAUSE FOUND AND FIXED ON THE POLLER PATH, BAR NOT
REACHED AND NOT LOWERED (Q3).**

The row names three candidate reasons -- schedule gating, retention trimming, or a poll
interval. The measured reason is **none of the three: it is ticker selection**, and its root
cause is a single missing argument in the poller's only production caller. Separately, the
capture the row asks to build (first pitch to final at <= 60 s, full ladders) **already
exists and is already running on the pod**; what is missing there is a consumer, not a
capture.

---

## STEP 0 -- what the four modules actually do

| module | poll interval | schedule gating | trimming | writer cadence |
|---|---|---|---|---|
| `mlb_book_capture.run_pod_capture` | `TARGET_CADENCE_SEC = 5.0`, doubling to `MAX_CADENCE_SEC = 60.0` on a 429, `IDLE_CHECK_SEC = 30.0` when nothing is live | **live only** -- `live_gumbo_games` -> `gumbo_mlb_poller.list_live_game_pks(date)`, then `game_pk_bridge_live.build_bridge` (held `CV_MLB_BRIDGE_TTL_SEC`, default 600 s) for the market tickers | none | deadline-paced: each tick sleeps only `started + period - now`, so the achieved period is `max(period, pass_duration)`; one `record_type='cadence'` row per tick |
| `ingame_book_depth_poller.poll_kalshi_depth` | the caller's; production caller is m37 at `DEFAULT_INTERVAL_SEC = 30`, CLI `serve_bounded` default 7 s / 120 s | **none** -- discovery is a bare `/markets?series_ticker=...&status=open&limit=200` per wired series, capped `max_markets_per_sport = 100` | sticky `active_by_sport` capped `max_active_per_sport = 60` | append-only JSONL to `book_depth/<venue>/<date>.jsonl` |
| `ingame_book_depth_kalshi.snapshot_market` | n/a | n/a | per-ticker trade watermark threaded through the caller's state | orderbook + trades in one pass, no extra request |
| `ingame_book_depth_retention.evict_over_cap` | n/a | n/a | **this is the trimming L5 named**: on cap overflow it evicts FUTURE-dated tickers (>1 day out) first, oldest-appended within each bucket, and reaches a today/tomorrow ticker only as a last resort | pure, no I/O |

A fifth module carries the only per-level ladders (what `depth_imbalance` needs):
`odds_provider/depth_capture.run_capture_pass`, fired from
`inplay_capture_loop._maybe_capture_depth` every `DEPTH_CAPTURE_EVERY_N_TICKS = 15` ticks of
`LIVE_INTERVAL_SEC = 20 s` -- **one pass per 300 s** -- with `max_tickers_per_sport = 50` and
a `_list_tickers` that also lists every open market with no live gating.

**File retention is not a trimming.** `sidecar_retention` only MOVES a stale file to
`<dir>/_archive/<name>` and never deletes; S100 read `_archive/` directly. No captured row
was trimmed away.

## STEP 0 -- the pod, read-only

- `21620` is the bash launcher, `21622` the capture itself:
  `python -c "from scripts.platformkit.ingame.mlb_book_capture import run_pod_capture; run_pod_capture(stop=lambda: False)"`,
  cwd `/workspace/nba-ai-system`, started 2026-09-02 14:13:23 UTC, launched with
  `CV_CAPTURE_POD=1 CV_MLB_BOOK_ARCHIVE_LIVE=1` on the `bash -c` line.
- `tail /workspace/mlb_book_capture.log` ends on a `RuntimeError: live MLB archive requires
  CV_CAPTURE_POD=1 and CV_MLB_BOOK_ARCHIVE_LIVE=1` traceback from an EARLIER launch whose env
  did not reach the child. The current process is past that and writing: it is the log that
  is stale, not the capture.
- `data/cache/ingame_books/mlb/2026-09-02.jsonl` 6,168,119 bytes, mtime 21:20 UTC, 3,818 rows
  = 2,185 `snapshot` / 1,628 `cadence` / 3 `fetch_error` / 2 `pressure`, **6 distinct
  `game_pk`**, 00:00:20Z .. 21:20:42Z. (`2026-09-01.jsonl`: 114 rows / 9 games.)
- Per-game in-play coverage on 2026-09-02: spans **79.4 to 238.2 minutes** (whole games), pass
  gaps median 25 to 65 s, p90 36 to 75 s, share of gaps <= 60 s from 0.30 to 0.99. Of 1,639
  cadence rows, 525 saw at least one live game; achieved cadence while live **median 30.0 s,
  p90 64.8 s** against a 5 s target -- the pass itself costs about 30 s, so the deadline
  pacing returns `max(period, pass_duration)`. Max 5 concurrent live games.
- **`data/cache/book_depth/` does not exist on the pod.** `m37_ingame_enrichment` is not among
  the 11 supervisor children (19596-19606 under `python -u -m supervisor --profile paper`,
  pid 19236) and its heartbeat file is absent. `supervisor/stack_specs.py:879` registers it
  with `argv=["--interval","30"]` and its own comment still reads "NOT YET RUNNING -- restart
  pending". The book-depth poller has never run on the pod.
- `data/cache/depth_history/mlb/2026-09-02.jsonl` 1,972,657 bytes, mtime 21:16 -- written by
  pid 19598 `inplay_capture_runner` through the 300 s hook above.

## STEP 0 -- the local stores S100 used, measured against each game's own window

The in-play window is taken from the ticker itself, not from the tick span: Kalshi names an
event `KXMLBGAME-<YY><MON><DD><HHMM><AWAY><HOME>`, so first pitch is that stamp read as ET,
and the window is `[first pitch, +5 h]`. (The tick span is not usable as a window: 144 of 227
scored `game_id`s carry ticks spanning more than 6 hours, one over three calendar dates --
a separate joined-store defect, reported below, not acted on here.)

Of 78,986 scored ticks over 227 games, **44,738 (56.64 pct) fall inside their own game's
window**, over 223 games.

| store | rows before first pitch | inside the window | after | games with a row on their ticker | games with a row INSIDE |
|---|---|---|---|---|---|
| `book_depth/_archive/kalshi` | 67,195 | **444** (0.66 pct) | 0 | 68 | **2** |
| `book_depth/_archive/kalshi_trades` | 283,160 | 7,938 (2.73 pct) | 0 | 9 | 2 |
| `depth_history/mlb` | 15,629 | **318** (1.99 pct) | 0 | 89 | **26** |

In-window row-to-row gap: `book_depth` median 52.5 s (p90 87.2 s) -- the interval is fine on
the rare occasion it fires. `depth_history` p90 1,700 s.

In-window ticks with a `depth_history` ladder row no older than the cap:
**447 / 44,738 (1.00 pct) at 300 s, 34 / 44,738 (0.08 pct) at 60 s.**

## The reason, named

**Not trimming.** File retention archives, never deletes (above), and the sticky eviction is
the fix that was supposed to protect same-day tickers, not the thing removing them.

**Not the process being down.** On the 14 dates it wrote, the poller ran essentially around
the clock: **median 1,372 distinct capture-minutes per date out of 1,440** (min 108, max
1,439), and 58.8 pct of its captured minute-cells sit in the MLB in-play UTC hours 17:00-05:00.

**Not the poll interval.** 52.5 s median in-window gap at a 30 s tick.

**It is ticker selection.** Days-ahead of every captured `KXMLBGAME` row (game date minus
capture date):

| days ahead | `book_depth` rows | `depth_history` rows |
|---|---|---|
| -1 (a night game past midnight UTC) | 0 | 90 (0.45 pct) |
| +0 | 11,845 (9.91 pct) | 2,272 (11.48 pct) |
| +1 | 25,693 (21.49 pct) | 6,822 (34.47 pct) |
| +2 | 69,248 (57.91 pct) | 9,359 (47.29 pct) |
| +3 | 12,788 (10.69 pct) | 1,246 (6.30 pct) |

**90.09 pct** of captured `book_depth` rows and **88.06 pct** of `depth_history` rows are for
markets whose game is one to three days away. Per ticker: **227 of 231 (98.27 pct)** MLB
tickers had their LAST `book_depth` capture **before their own first pitch**, a median
**3,664 minutes = 61.1 hours** before it; only 4 (1.73 pct) were still being captured more
than an hour after first pitch.

**The root cause is one missing argument.** `ingame_enrichment_runner._run_book_depth` --
the only production caller of `poll_once` -- called
`poll_once(sports=["mlb","wnba"])` with no `state`, so the poller's entire cross-tick state
(`kalshi_active`, `kalshi_misses`, `kalshi_prev`, `kalshi_trade_watermarks`, `poly_tokens`)
was rebuilt empty every 30 s. The 2026-07-11 sticky-retention fix and the 2026-07-15
date-aware eviction therefore **never ran in production**: every tick polled only the top 100
of an unordered `status=open` page, which Kalshi fills with days-ahead markets, and the
sticky list that was built to carry a ticker through its own game day was thrown away 30
seconds after it was built.

Two independent fingerprints of the same discard, both measurable on disk:

- the trades sidecar re-persisted the whole recent tape every tick --
  **1,060,539 mlb rows for 36,369 distinct `(ticker, trade_id)`, a 29.2x duplication factor**,
  with one trade written **3,340 times**;
- `stale_quote_flag` had no prior snapshot to compare against, which is why S100 measured its
  values null on 25,585 of 25,585 rows carrying the key.

## Change (additive, smallest)

1. `ingame_book_depth_retention.live_first(tickers, now_dt, limit)` -- drop markets whose game
   is more than a day out, **then** cap. Capping after the filter is the whole point: the cap
   used to be reached by future markets alone. Same `is_future_game` predicate
   `evict_over_cap` already uses, so today and tomorrow always survive and an unparseable
   ticker (`is_future_game` -> False) is never dropped.
2. `ingame_book_depth_poller.poll_kalshi_depth` -- discovery routed through `live_first`
   (net 0 lines; the file stays at exactly 300 LOC).
3. `ingame_enrichment_runner._BOOK_DEPTH_STATE` -- a module-level dict threaded into
   `poll_once`, so the sticky list, the miss counts, the prev snapshots and the trade
   watermarks survive the tick.
4. `depth_capture._list_tickers` -- the same `is_future_game` filter on the ladder store's
   listing, so its 50-ticker-per-sport budget reaches the live slate (net 0 lines; the file
   stays at exactly 300 LOC).

**One existing test changed, strengthened not weakened.**
`test_poll_kalshi_depth_protects_live_today_ticker_over_future_dated` asserted
`len(active["mlb"]) == 2` (today plus one surviving future ticker). With `live_first` a
more-than-a-day-out ticker never enters `active` at all, so the assertion is now
`active["mlb"] == [today_ticker]` -- strictly stronger. The eviction ORDER it was covering is
still asserted directly in `test_ingame_book_depth_retention.py`. No threshold, bar or
constant was touched anywhere (`max_markets_per_sport` 100, `max_active_per_sport` 60,
`max_misses` 3, `FUTURE_GRACE_DAYS`, `DEPTH_CAPTURE_EVERY_N_TICKS` 15, `LIVE_INTERVAL_SEC` 20,
`TARGET_CADENCE_SEC` 5 are all byte-identical to master).

## What this change does NOT reach (Q3 -- the bar is not lowered)

The row's bar is at least 80 pct of scored ticks carrying a fresh (<= 60 s) depth row. The
only store carrying per-level ladders -- the substrate `depth_imbalance` needs, per S100 --
is `depth_history`, and its cadence is a construct, not a coverage accident:
`DEPTH_CAPTURE_EVERY_N_TICKS (15) x LIVE_INTERVAL_SEC (20 s) = 300 s`. **300 s is longer than
60 s, so no ticker-selection fix can reach a 60 s bar from that store; the constant is the
wall.** It was NOT changed here: it is a single knob on the live paper node that multiplies
its Kalshi orderbook request rate fivefold, and moving live request load is an orchestrator
decision, not a lane's. **CLOSED AT LIMIT for this lane, named for the orchestrator.**

## The half of the row that is already done (Q8)

"Capture runs from first pitch to final at <= 60 s cadence, with full ladders" **already
exists and is already running**: `mlb_book_capture.run_pod_capture` on pids 21620/21622 is
gated on live GUMBO games only, writes complete `yes_ladder`/`no_ladder`, and on 2026-09-02
covered each game's whole span (79.4 to 238.2 min) at a median 25-65 s pass gap and an
achieved cadence of median 30.0 s / p90 64.8 s. **It needs no `--window` flag and no
restart.** What it does not have is (a) reach -- 6 distinct `game_pk` on 2026-09-02, bounded
by GUMBO-live plus bridge resolution, not by the window -- and (b) a consumer: S100 joins
`book_depth`, `kalshi_trades` and `depth_history` and reads `data/cache/ingame_books/mlb/`
nowhere. **The remaining distance to S100 is a join of an existing store, not a new capture.**

## For the orchestrator

**Nothing to restart for 21620 / 21622.** No flag is added to them, `mlb_book_capture.py` is
untouched by this diff, and their cadence already clears the window.

**The restart this diff needs is the one pending since m37 was registered.** Deploy only
after ACCEPT (B5 -- nothing was copied to the pod by this lane):

```
git -C /c/Users/neelj/nba-ai-system archive <ACCEPTED_SHA> -- \
  scripts/platformkit/ingame/ingame_book_depth_retention.py \
  scripts/platformkit/ingame/ingame_book_depth_poller.py \
  scripts/platformkit/ingame/ingame_enrichment_runner.py \
  scripts/platformkit/odds_provider/depth_capture.py \
  | ssh -F ~/.ssh/config.pod pod 'tar -x -C /workspace/nba-ai-system'
```

Then adopt the registered ProcSpec. There is no new flag: `stack_specs.py:879` already
carries `argv=["--interval","30"]`, so the supervisor cmdline is unchanged.

```
current: /usr/local/bin/python -u -m supervisor --profile paper        (pid 19236)
after:   /usr/local/bin/python -u -m supervisor --profile paper        (identical)
```

Kill **only** pid 19236 and let the watchdog relaunch it. Do not touch 4035, 21620, 21622,
254284 or 19596-19606. Confirm adoption:

```
ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && \
  cat data/cache/daemon_heartbeats/m37_ingame_enrichment.txt && \
  ls -l data/cache/book_depth/kalshi/ | tail -3'
```

The heartbeat must be fresh within 90 s (the ProcSpec's `readiness.fresh_sec`) and the
`book_depth/kalshi/` directory must be non-empty.

**Verification query** -- one live slate, target at least 80 pct. Note it reads the LIVE store
tree, not the `_archive/` tree S100 read:

```
python - <<'PYEOF'
from pathlib import Path
from scripts.platformkit.eval_gate import s100_microstructure as m
SLATE = "2026-09-05"          # the date to verify
R = Path("data/cache")
ticks = m.load_scored_ticks()
_q, _f, ladders = m.load_stores(R/"book_depth"/"kalshi",
                                R/"book_depth"/"kalshi_trades",
                                R/"depth_history"/"mlb")
sides = m.ticker_map(_q, _f, ladders)
day = ticks[ticks["date"] == SLATE]
ok = 0
for game, grp in day.groupby("game"):
    timeline, _sign = m._oriented(ladders, sides.get(game, {}))
    if not timeline:
        continue
    ok += sum(1 for t in grp["t"] if m.as_of(timeline, t, 60.0) is not None)
print("fresh <= 60 s depth row on %d of %d scored ticks (%.2f pct); bar 80.00"
      % (ok, len(day), 100.0 * ok / max(1, len(day))))
PYEOF
```

Expect this to stay BELOW the bar until `DEPTH_CAPTURE_EVERY_N_TICKS` is moved, for the
reason stated above; the same query at a 300 s cap is the honest read of what this diff
alone buys.

## Filed, not acted on

- **`ingame_grade_joined/mlb` groups ticks from more than one real game under one
  `game_id`.** 144 of 227 scored `game_id`s span more than 6 hours;
  `KXMLBGAME-26JUL061915NYMATL` carries ticks on 2026-07-05, 07-06 and 07-07, including a
  07-05T18:58Z tick at inning 2 / 3-5 and a 07-07T02:56Z tick at inning 10 / 6-7. That
  inflates the 78,986-tick / 227-game denominator S100 and this memo both quote. A separate
  row, not this one.
- `depth_history` is still in no file-retention policy (`sidecar_retention.DEFAULT_POLICY`
  covers `book_depth` only) -- unchanged from S100, and harmless while retention only
  archives.

## Contract self-check (B and Q)

- **B1** no circular metric: every share is over the whole scored corpus or the whole capture
  store; the excluded sets (ticks outside their own game window, tickers with no capture row)
  are named and counted rather than dropped.
- **B2** additive schema: one new function (`live_first`), one new module-level constant, two
  filtered listings. No column, status value or field was renamed or removed. A5 sweep on
  every reader of what the diff touches: `poll_kalshi_depth` / `_live_kalshi_tickers` /
  `evict_over_cap` have no callers outside the poller and its tests; the ops summary
  `data/frontend/ops/ingame_enrichment.json` has no reader anywhere in the repo, and its only
  consumer, `post_restart_enrichment_checks.py`, checks directory existence and mtime only.
- **B3** no fall-through loss: an unparseable ticker is KEPT by `is_future_game` -> False, so a
  parse miss never silently drops a market; missing is never treated as bad.
- **B5** no pre-verification deploy: nothing was copied to the pod. Every pod command in this
  lane was a read (`cat`, `ls`, `/proc/<pid>/cmdline`, a python read of one JSONL); no process
  was killed, started or signalled.
- **B6** no orphans: nothing was moved or retired.
- **B7** no head slices: every scored tick in all 227 games and every row in all three stores
  is walked; the days-ahead and last-capture tables are full sweeps, not samples.
- **B9** no degenerate denominator: both the tick count and the game count are printed for
  every coverage cell, and the per-ticker table (231 tickers) is a second, independent unit.
- **B10** no bar moved: every constant named above is byte-identical to master; the one bar
  this row carries (at least 80 pct at <= 60 s) is reported UNMET, not lowered.
- **Q1/Q2** no seal, no charge, no K read -- this is a capture-side ops row, not a scored
  comparison. `backtest_fwer.jsonl` was never opened.
- **Q3** the 60 s / 80 pct bar is stated unchanged and reported unmet, with the exact constant
  that blocks it named.
- **Q4** not applicable: nothing was scored out of sample, nothing was fit.
- **Q5** not applicable: no AHEAD is claimed. Every measurement is single-window (one venue,
  the July local archive plus one pod day) and labelled so.
- **Q6** calibration language only; none of the retracted figures appears.
- **Q7** the coverage shares are SAMPLED metrics over 78,986 ticks / 227 games; the module
  reading (interval, gating, trimming, cadence) is a CONSTRUCT enumerated over all five
  modules that write or gate a depth row, and the enumeration is the table above.
- **Q8** premise re-measured first, and it is partly FALSIFIED: the row's three candidate
  reasons (schedule gating, retention trimming, poll interval) are each measured and each
  ruled out, and the in-play-window capture the row asks to build already exists and already
  runs. A falsified premise is a valid result.
- **Q9** not applicable: no paired-loss series exists because no comparison was scored. The
  reported shares recompute from the named stores with the query above.
