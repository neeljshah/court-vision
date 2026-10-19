# S787 specification - post-focus-hour moneyline coverage (`extended` focus class)
PAPER ONLY. Capture scheduling only: no orders, no venue writes, no pricing change, coverage language only.
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B1-B10 and Q1-Q8 (S-row: eye check n/a,
REPRODUCTION replaces render). Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md (S-row adjustments).
Register row S787 (docs/evidence/HARNESS_GAPS_2026-09-03.md). Spec lead: Opus, 2026-10-07. No code in this lane.
WHERE: every build/test step LOCAL (pure planner + per-file tests on committed fixtures + tmp roots). No pod, no
network, no data/ write. The premise probe below was a local streaming read (resident memory trivial).

## 0. PREMISE (step 0, re-measured 2026-10-07 with fresh streaming reads)
Run 2026-10-07 18:2xZ, AFTER waiting the full 60 min (17:18Z-18:21Z) for nights/2026-10-06.json, which still
did not exist (night attempt 1 running, pid 17412); run at idle CPU / very-low I/O priority, 4 s, peak RSS 21 MiB.
Source: data/cache/ingame_books_local/kalshi/nba/2026-10-07.jsonl (104,184,781 B) streamed line by line, plus the
last 12,000,000 B of .../nba/2026-10-06.jsonl (274,860,549 B; first row read 22:29:34Z, so 23:50Z is complete);
state: data/cache/ingame_state_local_v2/state/nba/2026-10-07.jsonl (15,960,692 B). Count = KXNBAGAME rows with a
book (both tickers, every request_class); scheduled games from docs/evidence/forward/schedules/2026-10-07_maker_
forward.json (game_id = Kalshi event, game_key = state key).
KXNBAGAME-26OCT06NOPOKC rows per 10-min bucket (UTC), 23:50Z-03:30Z:
  23:50 74 | 00:00 360 | 00:10 360 | 00:20 360 | 00:30 360 | 00:40 360 | 00:50 360 | 01:00 0 | 01:10 0 | 01:20 0 |
  01:30 0 | 01:40 2 | 01:50 0 | 02:00 0 | 02:10 0 | 02:20 2 | 02:30..03:20 0   (360 = focus_books 240 + repoll 120;
  the 2-row buckets are snapshot_bulk rows from the global bulk rotation). First final state row 02:34:29Z.
Same shape for the other two: DENUTA (start 01:00Z) 360 per bucket 01:00-01:50, then 0 (2 bulk rows at 02:20)
to its final 03:34:57Z; LALGSW (start 02:00Z) 360 per bucket 02:00-02:50, then 0; no final row (state shard ends
04:23:17Z with status live). CORRECTION to the row text: DEN at UTA was cut at 02:00Z (start+3600), not 03:00Z.
Uncovered after the first hour: NOP at OKC 94.5 min, DEN at UTA 95.0 min (of 154.5 / 155.0 game minutes, so the
moneyline is captured for 39 pct of the game), LAL at GSW >= 83.3 min (still live at the last state row).
KXNBAGAME snapshot-gap probe, per ticker, consecutive snapshots inside start-120 s .. start+3600 s (seconds):
  ticker                              n_gaps   p50    p95    max
  KXNBAGAME-26OCT06NOPOKC-OKC (sel.)    1487   2.45   2.62   2.90
  KXNBAGAME-26OCT06NOPOKC-NOP            743   5.00   5.05   5.31
  KXNBAGAME-26OCT06DENUTA-UTA           1487   2.45   2.63   3.37
  KXNBAGAME-26OCT06DENUTA-DEN            743   5.00   5.06   5.79
  KXNBAGAME-26OCT06LALGSW-GSW           1487   2.46   2.62   3.07
  KXNBAGAME-26OCT06LALGSW-LAL            743   5.00   5.05   5.51
  Adoption bar p95 <= 120 s: PASS for all six inside the first hour (S767 repoll visible on the selected side).
  After start+3600 the next KXNBAGAME row is a stray bulk row ~40 min later or none, so the bar FAILS post-hour.
Finished games stay in bulk: 884 bulk rows with venue_status finalized in 00:00-03:30Z across the six sport shards
(NOP at OKC derivatives 152 and DEN at UTA 38 of them after start+3 h).
Reproduction (A2): stream the files above line by line; for KXNBAGAME-<event> rows carrying yes_bid bucket by
floor(capture_ts/600); gaps = sorted consecutive capture_ts differences per ticker inside the window; p95 =
g[int(0.95*n)]; finals = first state row per game_key with status "final".

## 1. LIMIT (step 1) - what the bulk share can fund
Global bulk rotation, all six 2026-10-07 sport shards, 00:00-03:30Z: 2,611 bulk requests (distinct
(tick_start_ts, event_ticker)) over 2,463 focus ticks = 1.06 bulk requests per 5 s tick (~120 per 10 min in every
bucket), 453 distinct events. That is the whole funding pool: replacement only, nothing added.
With bulk floor every F = 4 ticks, extended capacity c = 1.06 x 3/4 = 0.79 requests per tick. Selected ticker only,
target 10 s: per-game cadence = max(10, 5 x E / c) s = E 1: 10 s, E 2: 12.6 s, E 3: 18.9 s. Every value is under
the recorder's book bar for nba/nfl/soccer/tennis (state_age_ceiling_sec = SLOW_STATE_AGE_CEILING_SEC 120 s,
quote_freshness.py:44-45, used at live_shadow_sport.py:137). MLB's book bar is 5 s (STATE_AGE_CEILING_SEC mlb,
live_shadow_quoter:210): a 10 s cadence cannot make MLB books fresh most of the time; MLB gains markout
coverage only (stated, not hidden). Both tickers at 10 s would need 1 request per tick per game (E 3 = 3/tick,
three times the pool): rejected; the recorder quotes only the selected ticker.
Bulk cost while saturated (E >= 2): bulk keeps 1 in 4 ticks, sweep of 453 events ~36 min today -> ~2.4 h during the
extended hours; at E = 1 extended takes 0.5/tick and the sweep is ~67 min. Finished games leaving bulk returns
part of it (884 finalized rows above).

## 2. DESIGN (additive; default OFF in code; owner flips at a books restart)
Code facts the design rests on (read 2026-10-07):
- capture_scheduler._scheduled:122 admits a scheduled game to focus only while start-120 <= now < start+3600.
- A task of kind `focus_books` is added to `focus_tickers` (local_capture_runner.py:179) and from there feeds the
  focus cadence samples (capture_scheduler.prepare_tick:283) and the slow_ticks drop rule (plan_tick:177-182,
  p90 > 7 s for 3 ticks drops a game). A 10 s poll under that kind would drop a first-hour game. Hence a NEW kind.
- The recorder decides final in live_shadow_multi._tick:88-93 + :112-113: a visible state row whose
  `live_shadow_quoter._status(row)` (:77-79, lower-cased `status`) == "final" is TERMINAL for the game even if
  live rows follow (S780 round 4); its window is start-900 .. start+18000 s, kept past 18000 s only while the
  latest state is live and fresh within `_state_bar(sport)` (live_shadow_multi:61-65; live_shadow_sport
  STATE_MAX_AGE_S, mlb = live_shadow_quoter.STATE_MAX_AGE_S) - the `extended_live` counter (:75-76).
- The recorder reads book rows by `record_type in (snapshot, snapshot_bulk)` (live_shadow_io:161, quoter:185),
  never by request_class, so a new request_class value is visible to it.
- observation_support_census.py:117-122 refuses any request_class not in capture_scheduler.CLASSES
  (invalid_request_class). It must learn the new label (A5 reader; see hooks).
- The books child has NO state access today (no ingame_state read in local_capture_runner.py / capture_*).

2.1 Admission (pure, per tick, in NEW scripts/platformkit/ingame/capture_scheduler_extended.py `apply`):
  a game is EXTENDED at tick time `now` iff all hold: EXTENDED_ENABLED; it is a visible forward-schedule row
  (the same rows `schedule_rows` validates, state["forward_schedule"]); now >= start + 3600 (first hour sealed,
  untouched); the row's SELECTED ticker (schedule `ticker`) is in plan.markets (open, not closed/settled/finalized
  per capture_scheduler._rows:63-65); the game is not final (2.3); and now <= start + 18000, or past it the latest
  state row is `live` and fresh within the recorder's own `_state_bar(sport)` (mirror of extended_live).
  Only the selected ticker is polled (the recorder quotes only `entry["ticker"]`, live_shadow_multi:83; same
  precedent as the S767 repoll). One book request per game per cadence.
2.2 Cadence and funding (the accounting that keeps sealed numbers fixed):
  - Target cadence EXTENDED_CADENCE_S = 10 s per selected ticker. A ticker is DUE when
    now - extended_last[ticker] >= 10 (state kept in plan.state["extended"], persisted via state["scheduler"]).
  - Funding = REPLACEMENT ONLY. After plan_tick returns (focus, repoll, trades, bulk, discovery already planned by
    the unchanged code), `apply` replaces `("bulk", key)` tasks IN PLACE (same list position) with
    `("focus_extended", ticker)` for the due tickers, most-overdue first (never-polled first; ties by start, then
    ticker). Bulk floor: on ticks with service_ticks % BULK_FLOOR_EVERY == 0 (knob, default 4) the FIRST bulk task of the
    tick is never replaced (S767 item 1 requires >= 1 bulk request per 20 ticks; this keeps 1 in 4).
  - Consequences, each a test: len(requests) identical to the pre-S787 plan for the same inputs; every non-bulk
    task (focus_books, focus_repoll, trades, discovery) identical and at the same index; allocations["bulk"]
    decreases by exactly the replaced count and allocations["focus_extended"] (key present only when > 0) carries
    it; reserve unchanged. So the 15-request tick budget (3 req/s x 5 s), the 2.5 s repoll timing
    (capture_repoll.timed_requests positions only repolls; counts per half unchanged) and the S742/S767 focus
    budget cannot move. No request is ever ADDED.
  - The bulk cursor: bulk_cursor is advanced by plan_tick for planned bulk items; `apply` rewinds
    state["bulk_cursor"] by the replaced count (floor 0) so replaced events are served next, not skipped.
    (The repoll path rotates by service_ticks; skipped items there are a stated ceiling, see risks.)
  - extended_last[ticker] = now when PLANNED (pure; a deadline miss shows as a longer gap, counted below).
2.3 Final signal = the STATE ROOT, the recorder's own rule (decision; alternatives rejected below).
  NEW `refresh(state, now, books_root)` (the only I/O; called by the runner before prepare_tick, throttled to once
  per 30 s per sport and only when an extended candidate exists): for each sport with a candidate, read the LAST
  1 MiB (bounded seek, never a whole shard) of `<books_root>/../ingame_state_local_v2/state/<sport>/<D>.jsonl` for
  BOTH candidate dates D = UTC date of now and the previous UTC date (date-keyed rail); skip a partial first line
  and any unparseable line; keep per game_key the latest (capture_ts, status) and a sticky `final` flag set by any
  row with lower-cased status == "final" (terminal, as S780 round 4). Join = schedule row `game_key` <-> state row
  `game_key`: the SAME seam the recorder uses (live_shadow_multi entries carry r["game_key"]), so no new id join
  and no join-rate test is owed; the schedule row is the resolver (game_id = Kalshi event, game_key = state key).
  Rejected: (a) Kalshi market status - finished games' markets stay open for hours (the premise shows bulk still
  polling finished games' derivatives), so it is not a timely final; it stays only as an extra exit. (b) a fixed
  start+N cap - NBA lengths vary with overtime; it would cut live games or keep finished ones, and would not
  match the recorder.
2.4 Exit rules (each counted): final state row -> exit, `extended_exits_final`; the selected ticker absent from
  plan.markets (market closed/settled) -> `extended_exits_market_closed`; past start+18000 without a live and
  fresh state row -> `extended_exits_cap`. A final game also LEAVES BULK: `apply` drops ("bulk", key) tasks whose
  key == (sport, schedule game_id) of a final game before replacement (the winner event only; derivative events
  need a new event-suffix join and are NEW GAP S787b, not this row) and counts `bulk_final_skipped`.
2.5 Concurrency cap EXTENDED_MAX_GAMES = 3 (= S742 G, three concurrent live windows under live_concurrency). At
  the cap the earliest-start games keep their slots; each further eligible game is counted per tick in
  `extended_refused_cap` and is re-evaluated every tick (no sticky refusal).
2.6 Refusals (named, counted per tick per game, never silent; missing evidence never drops a live game - B3):
  `extended_refused_state_unavailable` (no shard for either date, unreadable, or no row for the game_key in the
  tail): the game STAYS extended until the start+18000 cap; `extended_refused_no_game_key` (schedule row lacks
  game_key): same treatment; `extended_refused_cap` (2.5); `extended_refused_disabled` is NOT emitted (OFF = the
  module returns the plan unchanged and writes no field).
2.7 Heartbeat fields (per sport, additive, via capture_scheduler.heartbeat_fields): `extended_games` (games in the
  class this tick), `extended_requests` (focus_extended tasks planned this tick), `extended_requests_total`,
  `extended_exits_final`, `extended_exits_market_closed`, `extended_exits_cap`, `extended_refused_<reason>` (totals),
  `bulk_final_skipped_total`, `extended_age_p90_sec` (p90 over extended tickers of now - extended_last, decimal
  string; "0" when none), `extended_state_read_at`. requests_by_class gains `focus_extended` only when used
  (same pattern as focus_repoll). Book rows written by these requests carry request_class "focus_extended".

## 3. HOOKS AND LOC PLAN (every file <= 300; capture_scheduler.py and local_capture_runner.py stay EXACTLY 300)
All hook edits are same-line edits (zero net lines):
- capture_scheduler.py:7 append `; from scripts.platformkit.ingame import capture_scheduler_extended as extended`
  (the new module must NOT import capture_scheduler at module level: use dataclasses.replace on the plan).
- capture_scheduler.py:284 `return plan_tick(...)` -> `return extended.apply(plan_tick(...), state, epoch)`.
- capture_scheduler.py:290 `return {**fields, **extended.heartbeat(plan, sport), "profile_sha256": digest,`.
- local_capture_runner.py:14 append the same module import.
- local_capture_runner.py:177 pass `extended.refresh(state, now, writer.root)` (returns state) in place of `state`.
- local_capture_runner.py:181 `if kind != "focus_repoll" ...` -> iterate `scheduler.CLASSES + (extended.KIND,)`
  and treat KIND like focus_repoll (present only when allocated).
- local_capture_runner.py:204 `if kind in ("focus_books", "focus_repoll"):` add `extended.KIND`. focus_last /
  focus_intervals entries for that key are written but never sampled (prepare_tick:283 samples only focus_tickers;
  KIND keys are not added at :179) - a test pins that a focus_extended request never enters focus_tickers.
- local_capture_runner.py:221 never carry KIND: `state["carry"] += [(kind, key)] * (kind != extended.KIND)` keeps
  canonical_carry (which would raise on an unknown class) untouched; the miss still counts missed_deadlines_total.
- observation_support_census.py:118 `label not in CLASSES` -> `label not in CLASSES + (KIND,)` (import on :14);
  observation_support_phases: the builder confirms (A5) a focus_extended receipt is credited to neither focus nor
  bulk, and pins it in a test.
- capture_scheduler.CLASSES, SHARES, forward_capture_profile.json: UNCHANGED (sealed listing; census pins it).
- NEW capture_scheduler_extended.py: KIND, EXTENDED_ENABLED = False, EXTENDED_CADENCE_S = 10,
  EXTENDED_MAX_GAMES = 3, BULK_FLOOR_EVERY = 4, STATE_TAIL_BYTES = 1 MiB, STATE_REFRESH_S = 30; apply, refresh, heartbeat; <= 200 LOC.

## 4. CONFIG / ADOPTION
- Lands with EXTENDED_ENABLED = False (invariant: an agent never flips a flag ON). Recommendation to the owner:
  turn it ON - by construction it adds zero requests (replacement of bulk tasks only). The flip is a ONE-LINE
  separate commit (`EXTENDED_ENABLED = True`), no books argv change, no profile change, no config pin.
- Takes effect ONLY at a books restart: STOP_books + one tick via the tick recreate path, as adopted for S767
  10:49Z 10-06 (docs/operations/DESK_STATE.md section 3 books S767 line). On its OWN UTC date and BEFORE the 12:00Z
  D1 (pointer landmine: a books restart after the D1 drops the same-day games - memory
  missed_d1_recovery_and_pointer_landmine), and outside every focus hour (DESK_STATE 1b quiet rule).
- First live check after adoption (NOT VERIFIED until it happens): a served game past start+3600 has
  request_class focus_extended snapshot rows of its selected ticker every ~10 s until its first final state row,
  and none after; extended_* fields in the heartbeat; n_429_10min 0; first-hour gap p95 unchanged.

## 5. ACCEPTANCE RULE (the verifier applies exactly this)
  metric        = (A) per-tick request multiset and length vs the pre-S787 planner on the same inputs;
                  (B) selected-ticker snapshot gap after start+3600 in a 600-tick construct;
                  (C) first-hour selected-ticker gap p95/max with the class ON vs OFF (S767 construct).
  before        = post-hour gap: no snapshot at all (premise section 0); first hour per section 0.
  bar           = (A) every tick: len equal, every non-bulk task equal at equal index, total <= pre-S787 total,
                  never > budget; (B) construct with exactly 1 bulk task per tick, F = 4, 600 ticks: E = 1 -> every planned gap
                  10 s or 15 s, p95 <= 15 s; E = 2 and E = 3 -> per-game slot counts differ by <= 1 and every
                  gap <= (ceil(5E/0.75 / 5) + 1) ticks (no starvation); bulk keeps >= 150 of 600 ticks;
                  (C) ON vs OFF byte-identical focus_books / focus_repoll / trades schedule over the S767
                  600-tick construct at 1, 2 and 3 games (p95 <= 3.0 s, max <= 4.0 s unchanged);
                  (D) exit within one refresh (<= 30 s + one tick) of the first final row; a final row followed by
                  live rows stays exited; a missing shard keeps the game extended to start+18000 then exits_cap;
                  both candidate dates read across 00:00Z; (E) OFF = plan and heartbeat byte-identical to master.
  n             = constructs enumerated in section 6 (CONSTRUCT); fixture replay over the real 10-06/10-07 NBA rows.
  eye check     = n/a (S-row); reproduction = rerun the probe script recorded in section 0 and the construct tests.
  must not move = CLASSES, SHARES, forward_capture_profile.json, capture_repoll.py, served_concurrency.py, every
                  freshness bar, live_shadow_* files, seal-pinned local_capture_writer.py / capture_watchdog.py,
                  every PREREG; capture_scheduler.py and local_capture_runner.py line counts (300).
NON-TAUTOLOGY: (A) and (C) compare against the UNCHANGED planner on the SAME inputs, all ticks, none excluded.

## 6. TESTS (one new file per concern, each <= 300 LOC; run ONE FILE PER PROCESS)
NEW tests/platformkit/ingame/test_s787_extended_budget.py - (A) and (E): property sweep over seeded inputs
  (0-3 focus games, 0-4 extended, 0-40 bulk events, budgets 1..15, service_ticks parity) asserting replacement-only.
NEW tests/platformkit/ingame/test_s787_extended_cadence.py - (B) and (C) on the S767 simulator (injected clock,
  3 req/s limiter, seeded 30-200 ms latency); focus_extended never enters focus_tickers or cadence samples.
NEW tests/platformkit/ingame/test_s787_extended_final.py - (D): tmp state roots, partial last line, two dates,
  final-then-live terminal, missing shard, no game_key, cap, refresh throttle, bounded read (asserts bytes read
  <= STATE_TAIL_BYTES per file).
NEW tests/platformkit/ingame/test_s787_extended_replay.py - fixture replay: a committed <= 200 KB slice of the
  10-07 NBA rows (NOP at OKC selected ticker + its state rows) shows the class covering 01:00Z..final with the
  first-hour plan unchanged.
RERUN (existing, one per process): test_capture_scheduler, test_s767_repoll, test_s767_grid_pause,
  test_served_concurrency, test_served_concurrency_s751, test_local_capture_runner, test_request_class_rows,
  test_observation_support_census_1e, test_s561_live_window, test_capture_schedule_pointer, tests/platformkit/
  test_loc_rail_scope.py (A12).
MUTANTS (each must turn a test red): M1 append extended tasks instead of replacing (len grows); M2 replace a
  trades or discovery task; M3 dispatch as focus_books (enters focus_tickers, cadence p90 > 7, game drop);
  M4 admit at start+3600-1 (first hour touched); M5 non-terminal final (live row after final re-admits);
  M6 read only the UTC-today shard (00:00Z crossing game never exits final); M7 full-shard read (bytes bound);
  M8 drop the bulk floor (bulk 0 while extended saturates); M9 missing shard drops the game (B3); M10 carry focus_extended
  (canonical_carry raises); M11 cap ignores start order; M12 bulk cursor not rewound.

## 7. VERIFIER CONTRACT
B tier (contract): B1 (A)/(C) over all ticks, none excluded; B2 additive only (new kind, new heartbeat keys,
  CLASSES untouched, census accepts the new label; readers grepped: observation_support_census/phases,
  live_shadow_fills_books/_io, system_fault_cases_shadow, local_capture_writer); B3 missing state keeps the game;
  B4 refusals re-evaluated each tick; B5 no deploy, no books restart by the lane; B6 no orphans; B10 no bar moved;
  Q3 every bar here byte-identical in the memo; Q6 coverage language only; A12 LOC rail.
Q tier (adversarial): Q-a can any input make len(requests) exceed the pre-S787 plan? Q-b can a focus_extended
  key reach focus_tickers, focus cadence samples or carry? Q-c does a game finishing after 00:00Z exit (both
  dates)? Q-d does a stale live row past 18000 s keep a game forever? Q-e can a slow/partial state tail raise
  and kill the tick (refresh must swallow OSError/ValueError into state_unavailable)? Q-f does the bulk floor
  hold at budget 1..3 (reduced AIMD rate)? Q-g does the repoll still fire at tick + 2.5 s with replaced bulk
  positions? Q-h is the final rule byte-for-byte the recorder's (_status lower-case, terminal)?

## 8. RISKS
- RAM of the books child: refresh holds <= 2 x 1 MiB bytes per sport at most once per 30 s, released after
  parsing; extended state = a few dict entries per game. No growth with session length (entries pruned on exit).
- Recorder 16 MiB shard tail reads: the nba shard ran 24.3 / 25.7 / 27.8 / 13.5 MiB per hour 00-03Z 10-07, so the
  tail spans ~35 min today. Added rows: 1 snapshot / 10 s x 1 selected ticker x E games = 360 rows/h/game
  x 5,040 B mean KXNBAGAME book row (n = 6,742) = 1.73 MiB/h/game; E = 3 -> +5.2 MiB/h (+19 pct), tail ~30 min,
  still far above the 120 s book bar. Replaced bulk requests write ~8 snapshot_bulk rows each (nba 2,748 rows /
  337 requests in the probe buckets), so total bytes across shards are about flat; the extended game's own shard
  grows. (The row text's "x 2 tickers" would double this; not adopted.)
- State source dead or late (the nba state shard of 10-07 stopped at 04:23:17Z with LAL at GSW still live): the
  game stays extended to start+18000 s then exits_cap; costs at most 18000-3600 s of one slot share per game.
- Repoll-path bulk rotation is by service_ticks, not the cursor: a replaced tick skips that index; with gcd(F, n)
  > 1 some events can be skipped more than others during extended hours. Ceiling stated; upgrade = rotate the
  bulk index by a served-count instead of service_ticks (NEW GAP if measured).
- Derivative events of finished games still rotate in bulk (suffix join 9 of 9 on the 10-06 NBA slice, too small
  for the >= 95 pct join rail): NEW GAP S787b, using the finalized venue_status bulk rows or the suffix join with
  its own join-rate test.
- Adoption timing: a books restart is the only adoption path; after the 12:00Z D1 it drops the same-day games.

NOT VERIFIED (by construction): live adoption; recorder quoting on extended rows; the state2 shard tail being
current during a game on the night of adoption; derivative events of finished games (S787b).
