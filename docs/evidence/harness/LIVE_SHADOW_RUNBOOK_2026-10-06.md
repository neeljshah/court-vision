# Live shadow quote recorder (S515) -- runbook, 2026-10-06

PAPER ONLY. The recorder reads the captured book and state shards on this laptop and appends
hypothetical maker quote INTENTS to `data/cache/live_shadow/`. It has no network access, no venue
client, no executor and no order path. Wording on tracked files: calibration and execution quality only.

Owner approval: 2026-09-29 ~19:2xZ ("Yes, start it once verified"), with the conditions in the launcher
header (free RAM >= 2,000 MB at start; peak <= 150 MB; record pid/argv/peak/start; stop file). Owner
directive 2026-10-06 ~00:5xZ: the desk quotes LIVE (paper) during games, not only in the nightly replay;
the dispatcher keeps the recorder alive (it was "owner-run only" before).

## 1. Premise check (fresh reads, 2026-10-06 00:5xZ)

- NOT running at 00:51Z: no process matched `live_shadow` (Win32_Process query). The only run ever was a
  BOUNDED direct run on 09-29 (pid 20384, nonce 576a4eb1, `--until 2026-09-30T04:15:00Z`, relative roots),
  NOT under the supervisor: `data/cache/capture_supervisor/` has no `supervisor_live_shadow.*` and no
  `live_shadow.launch.log`, so the 09-29 launcher was never executed. Last heartbeat 2026-09-30T04:14:59Z:
  912 ticks, rows_written 1015, peak_rss_mib 69.55, low_ram_skip 465, write_errors 0.
- On disk: `data/cache/live_shadow/mlb/2026-09-29.jsonl` (185 lines: 1 run + 184 arm rows) and
  `.../2026-09-30.jsonl` (830 arm rows), games 849849 and 849851. Decisions over 1,014 arm rows: quote 96,
  no_quote 918 (tail_window_miss 506, stale_book 302, p0_missing 94, game_final 4, state_stale 2).
- `docs/evidence/forward/live_shadow/` holds only `PREREG_S519.json`: no fills report has ever been written.
- Sports: the CLI accepts `--sports mlb` only (`live_shadow_cli.py` main, `choices=["mlb"]`); the fills
  CLI likewise (`live_shadow_fills_io.py` main). The NBA slice (S518) is BUILT and PARKED on branch
  `harness-h281` (22b05fb04), not on master. NFL / soccer / tennis: nothing (S780 spec).
- S519 code identity: the three pinned files hash (CRLF-normalised) to the sealed values
  (`live_shadow_quoter.py` da2b3afa..., `blend_apply.py` 9f9ec929..., `mlb_live_model.py` 921d2f54...),
  so rows recorded on master today count toward the S519 window.

## 2. Continuous vs per slate (decision)

CONTINUOUS under its own `capture_supervisor --name live_shadow` (the launcher's far-future
`--until 2099-01-01T00:00:00Z`). Why it works:
- Each tick loads the schedules for the days around t (`live_shadow_io.load_schedules` / `days_at`) and
  keeps entries with `start - 900 s <= t <= start + 18000 s` that are not final; with no entry it idles and
  sleeps 300 s (heartbeat `idle: true`). So one process covers every served MLB game, and a game whose
  window opens while it runs gets its p0 frozen before first pitch (p0 = venue pregame mid at the cutoff).
- UTC day boundary: output shards are per UTC day (`<out>/mlb/<D>.jsonl`); S584 (LANDED dd5231387) writes a
  continuation run row on each new day shard and was exercised across midnight (186 kill/restart
  combinations of the real CLI, exactly-once).
- Restarts: the supervisor restarts ANY child exit (backoff <= 300 s). p0 is recovered from the existing
  shard (`recover_p0`), so a restart mid-game keeps the frozen p0.
- Laptop reboot: the S500 tick recreates ONLY books, state2 and polymarket (`status.json` keys
  `capture:books`, `capture:state2`, `capture:polymarket`); it does NOT relaunch live_shadow. After a
  reboot the watchdog rule (section 5) relaunches it; with the watchdog not running nothing does.
- A start AFTER first pitch records `p0_missing` on the blend arm for that game (a counted reason); the mid
  arm still quotes.

## 3. Launch and check

```
powershell -NoProfile -File docs\operations\relaunch_live_shadow_2026-09-29.ps1 -DryRun   # prints argv only
powershell -NoProfile -Command "(Get-Counter '\Memory\Available MBytes').CounterSamples.CookedValue"  # >= 2500
powershell -NoProfile -File docs\operations\relaunch_live_shadow_2026-09-29.ps1          # refuses if running / STOP present / RAM < 2000
```
Rules: not inside a served game's focus hour (start - 5 min to start + 65 min), not 05:20Z-08:45Z, not
while a paper night runs. Check within 10 minutes:
- pid + RSS: the CIM query of section 5 (python processes whose command line matches `live_shadow_quoter`), then
  `Get-Process -Id <pid> | Select PeakWorkingSet64` (bar 150 MB; the heartbeat also has `peak_rss_mib`).
- heartbeat: `data/cache/live_shadow/_heartbeat.json` (`ts`, `ticks`, `idle`, `rows_written`, refusal
  counters) and `data/cache/capture_supervisor/supervisor_live_shadow.heartbeat.json` (mtime fresh).
- intents: `tail -n 3 data/cache/live_shadow/mlb/<D>.jsonl`.
- the three capture heartbeats stay fresh: `sh .planning/codex_push_2026-10-02/desk_check.sh` (local).
Stop: create `data\cache\capture_supervisor\STOP_live_shadow` (the supervisor stops the child and exits).
Remove it only on an owner or dispatcher decision; while it exists the watchdog never relaunches.
Stop at once if RSS > 150 MB or any capture heartbeat goes stale after the launch.

## 4. Evidence path (fills receipt)

The fills receipt (S516) is NOT a paper-night step (`paper_night` steps do not call it) and no tick or
task runs it. The dispatcher runs it once per UTC day D after D+1 ~04:30Z (the receipt reads shards D and
D+1 and marks itself PROVISIONAL until each ticker's trade drain is complete; re-running later upgrades it,
and a FINAL receipt is never overwritten by a non-FINAL one):
```
python -m scripts.platformkit.execution.live_shadow_fills_io --date <D> \
  --shadow-root data/cache/live_shadow --books-root data/cache/ingame_books_local \
  --out docs/evidence/forward/live_shadow/<D>.json
```
Outputs: `docs/evidence/forward/live_shadow/<D>.json` (schema `live_shadow_fills_v1`) and
`<D>.pairs.jsonl` (per-game paired sidecar, digest linked by `sidecar_sha256`). Exit 3 =
shadow_shard_missing (no intents that day), 4 = final_receipt_preserved, 5 = a counted refusal.
Same one-python rule; free RAM >= 2,500 MB; outside focus hours and 05:20Z-08:45Z.
First run: see section 7.

## 5. Keep-alive (watchdog rule)

`.planning/codex_push_2026-10-02/watchdog.sh` (local-only) checks every 5 minutes: when no python /
pythonw process matches `live_shadow_quoter|--name live_shadow`, no `STOP_live_shadow` exists, free RAM
(desk_check) >= 2,500 MB, the time is outside 05:20Z-08:45Z, no paper night is running and no served game is
inside its qualification window, it runs the launcher once, at most once per 30 minutes, and logs
`WATCHDOG <stamp> relaunched live_shadow: <launcher output>` plus `LIVE_SHADOW_RELAUNCH` in
`out/watchdog.log`. A running watchdog keeps its old code: the dispatcher restarts it to pick the rule up.

## 6. Row schemas (for the S775 paper-result ledger and the dashboard)

Intents shard `data/cache/live_shadow/<sport>/<D>.jsonl`, one JSON object per line, `schema`
`live_shadow_v1` on arm rows:
- `kind: "run"` (one per process start and per new day shard): argv, every_s, tail_bytes, freshness_bars
  {book_max_age_s, state_max_age_s}, inventory_policy, ignored_dimensions, sha256 {file: digest},
  run_nonce, row_id, emitted_ts.
- `kind: "p0"` (once per game, frozen): sport, game_key, p0_home, p0_yes_mid_cents, orientation, p0_source
  (`venue_pregame_mid`), p0_book_ts, p0_book_sha256, p0_state_ts, p0_state_sha256, p0_age_s, p0_cutoff
  (`first_live_state` | `scheduled_start`), scheduled_start, t.
- `kind: "arm"`: one per (tick, game, arm). Keys: arm (`mid` | `venue_prior_state_blend`), decision
  (`quote` | `no_quote`), reason (`quoted` or the refusal), sport, game_id, game_key, ticker, orientation,
  t_epoch, t_iso, emitted_ts, expires_at_epoch, quote_id, yes_bid_cents, yes_bid_quote_id (`<id>-yb`),
  no_bid_cents, no_bid_quote_id (`<id>-nb`), bid_cents, ask_cents, anchor_cents, model_prob_yes, p0_home,
  p0_source, qty ("1"), fee_cents, room_assumption (`fixed_1_per_side`), inventory_policy
  (`independent_intent_zero`), book_ts, book_age_s, book_row_sha256, book_src {path, observed_size,
  window_start}, state_ts, state_age_s, state_raw_sha256, state_src, refusal_count, clock_conflict,
  row_id (`<D>-<nonce>-<seq>`), run_nonce.
- Heartbeat `_heartbeat.json`: ts, pid, run_nonce, ticks, idle, free_mb, min_free_mb, peak_rss_mib,
  rows_written, write_errors, low_ram_skip, tick_latency_s, plus counters (missing_shards,
  partial_leading, p0_conflict, schedule_*).

Fills receipt `<D>.json` (`live_shadow_fills_v1`): date, status (FINAL | PROVISIONAL), completeness
fields, `arms` {mid, venue_prior_state_blend} each with n_rows, fills {through, touch_queue_bound},
passes {queue_unknown_default, queue_ahead_1}, fill_rate_per_quote_hour, markouts at horizons 60 s and
300 s in probability points clustered by game_id; `replay` (separately labelled replay section);
assumptions (submit 2 s, cancel 1 s latency, margin 1800 s, max_wait 30 s, fee_schedule_version);
refusals; diagnostics; input_sources; receipt_lag; run_meta (peak_rss_mib, rss_bar_mib 300).
Sidecar `<D>.pairs.jsonl`: `kind: "game"` rows with per-arm n_intervals and markouts, `section` live|replay.
Consumers join on (sport, ticker, quote_id); a fill price is in cents per contract, qty 1 per side.

## 7. Measured tonight (2026-10-06)

- Launch 01:25:56Z (free RAM 6,193 MB by the launcher gate; 6,393 MB Available MBytes at 01:25Z), after
  the focus hours of NYY at TB (00:00Z) and ATL at NO (00:15Z). PIDs: hidden_launch 8676, supervisor
  15380, recorder child 13044 (run_nonce c72a4476). Peak working set at +50 s: child 56 MB, supervisor
  20 MB, launcher 18 MB (heartbeat peak_rss_mib 56.0). Argv = the launcher's `-DryRun` output.
- First rows (`data/cache/live_shadow/mlb/2026-10-06.jsonl`, 4 ticks): 1 run row + 16 arm rows, all
  `no_quote`: CWS at CLE (849834, 10-05 schedule, inside start + 5 h) `book_refused:one_sided_book`;
  NYY at TB (849839) `tail_window_miss` (its latest book row is outside the 2 MiB tail; desk_check showed
  its last book row 228 s old at 01:25Z). The blend arm records `p0_missing` for NYY at TB (started before
  the recorder). The first game with p0 frozen at the cutoff is LAD at ATL 22:00Z 10-06.
- Capture heartbeats books / state2 / polymarket 4 s old at 01:25Z (desk_check), re-checked after launch
  (DESK_STATE row).
- First fills receipt, 2026-09-29 (`docs/evidence/forward/live_shadow/2026-09-29.json`, written 01:27Z,
  rc 0, 4 s, peak RSS 27.1 MiB): status PROVISIONAL `ticker_trade_incomplete` (the NYY ticker's trade drain
  stops 14:15Z 09-29); arm mid 12 quote intervals, 168 s quoted, 0 fills under both passes (through and
  queue_ahead_1), no markouts; arm venue_prior_state_blend 0 intervals (p0_missing all run); 1 game,
  unpaired; books_prefiltered 23,378. Not committed (outside this lead's file set).
- Measured weakness to fix (not in S780): on 09-29/30, 506 of 1,014 arm rows were `tail_window_miss` and
  302 `stale_book`, i.e. the 2 MiB tail of a multi-ticker books shard often misses the served ticker.
- S781 LANDED 8717278af 09:57Z 10-06 and adopted by the 09:58:16Z relaunch (recorder 30084, nonce 8a3bbbae). The recorder now reads appended bytes per served key (live_shadow_incr.py) instead of a fixed 2 MiB tail. Check on the first in-window game (LAD at ATL 22:00Z 10-06): quote rows carry read_from and window_start 0 on books/state, bootstrap counters, no tail_window_miss. A late restart can age out a pre-cutoff p0 prior (keep_s 4500): relaunch before the cutoff.
