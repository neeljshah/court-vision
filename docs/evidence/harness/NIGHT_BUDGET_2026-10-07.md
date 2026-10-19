PAPER ONLY; calibration evidence only

# NIGHT BUDGET 2026-10-07 -- do tonight's paper-night steps fit their deadlines? (read-only; no code changed, no test run)
Lead: night-budget investigation lead, 2026-10-07 19:01Z-19:2xZ. Every byte count is os.stat or a
recorded artifact field; every wall is a night record field. Estimates are labelled ESTIMATE.
## 1. Where the deadlines live

- Per-step deadlines: scripts/platformkit/execution/paper_night_budget.json:30
  `deadline_s` = qualification 900, fill_realism 1200, week 300, scoreboard 900, history 900, e 1800
  (sum 6,000 s). Read by paper_night_deadline.py:38 (deadline_ns) and enforced in poll_step
  (paper_night_deadline.py:268 sets KILLED / step_deadline_exceeded).
- Night total: the tick child timeout docs/operations/paper_desk_config.json:28 `timeouts_s.night` 7200,
  floor-checked at scripts/platformkit/ops/paper_desk_tick.py:116-117 (night_timeout_below_7200).
  S779 memo section 7: worst case = 6,000 s of deadlines + 600 s S755 RAM wait = 6,600 s < 7,200 s.
- Seal status: NO PREREG names paper_night_budget.json (PREREG_2026-10-07 hashes seven files:
  ingame_scoreboard*.py, baseline_four_arm*.py, walkforward.py). The budget is TEST-pinned
  (test_s526_admission_need LF hash, test_paper_night_deferral, test_registry_scorer_e_night_capacity,
  test_s485_baseline_contract, test_s558_round4) and its sha256 is stamped on every night record
  (night_ram_census.py:22 HISTORICAL_MARGINS). paper_desk_config.json is tick-pinned (s709 pin).
  fill_realism*.py, tape_fill_sim.py, registry_scorer_e_night*.py are not seal-hashed either.
- S779 raised fill_realism 600 -> 1200 in 9363066a7 (2026-10-06 05:09 -0500), config only.
## 2. fill_realism: what drives its wall

- Inputs = every DISPATCHED sport's books (also passed as trades; deduped by path, read once) and
  state shards for days D and D+1 (paper_night_inputs.py:101-129; population = served schedule sports).
  Tennis is not dispatched tonight (no served tennis row), so the tennis state shard is NOT an input.
- fill_realism_io.py:127 `_index` json-decodes EVERY row (Decimal parse) and inserts every in-window
  row into a temp sqlite (cache_size 2 MB, :255). :199 `_global_conflicts` then re-opens the file
  once PER TRADE ROW (seek + readline); :183 `_load` re-opens the file once PER SELECTED ROW per ticker.
- :259 replays EVERY ticker present in the books shards, not only served tickers. Measured on the one
  shard read (nba books 2026-10-06, 274.9 MB, 172,096 rows, 1,597 B/row): 600 tickers with
  snapshots (game, spreads, totals, 1H markets), 365 with trades; live game tickers carry 5,457-7,022
  snapshots and up to 7,966 prints each; sum over tickers of snapshots^2 = 1.62e8.
- Per ticker, run() executes 8 scenarios (quote lives {5, 30} x GRID (1, 2, 4, 8); fill_realism.py:259-261).
  Each scenario is super-linear in that ticker's live book rows:
  - tape_fill_sim.py:55 `_queue` scans ALL books per quote (Q x B);
  - tape_fill_sim.py:214 loops all quotes per print (P x Q);
  - fill_realism.py:213 `ahead = next(...)` scans books per quote (Q x B);
  - fill_realism.py:214-219 loops prints per quote and, inside, sums over ALL fills (Q x P x F);
  - fill_realism.py:198 rebuilds the full prepared-row list per fill (F x B).
  With Q about 2 x B (one quote per side per snapshot), cost grows with the SQUARE of each live
  ticker's snapshot count. Work therefore scales with live in-game book activity (more live games,
  longer windows) faster than with bytes.
- No progress output: only the final summary line (fill_realism.py:289), so a killed run leaves stdout_last_line empty.
## 3. registry_scorer_e_night and forward_qualification_daily

- E reads ONLY mlb: registry_scorer_e_night_fields.py:99 hard-codes `folder/'mlb'/shard`; non-mlb served
  rows are counted unsupported_sport (registry_scorer_e_night.py:109). The capture root
  data/cache/ingame_capture_view_v2 is two junctions (kalshi -> ingame_books_local/kalshi,
  state -> ingame_state_local_v2/state); E does NOT walk tennis or any other sport.
  It reads every row of each (day, folder) shard for every night in the 7-day lookback that had a
  served mlb game, plus D+1 (:95-131, json Decimal decode per row), then scores the population.
  Work scales with mlb shard bytes in the window and with the number of mlb games in it.
- Qualification hashes and COPIES every input shard into a snapshot tree before replay
  (forward_qualification_daily.py:73-96), then replays all rows; per row it loops over the games
  (forward_replay_qualification.py:117-122). Work scales with input bytes, times a small per-game
  factor. It is the most disk-sensitive step (read twice, write once).
## 4. Rates from nights 10-02..10-06 and tonight's estimate

Input MB = qualification inputs.snapshots.bytes (the same D / D+1 books + state set fill_realism reads).
E MB = mlb kalshi + state shards in the E window (current sizes; D+1 was partial at run time).

| night | served | input MB (books) | qual s (s/MB) | fill s (s/books-MB) | E games / MB | E s (s/MB) |
|---|---|---|---|---|---|---|
| 10-02 | mlb1 nfl1 | 117 (96) | 164 (1.40) | 28 (0.29) | 6 / 568 | 454 (0.80) |
| 10-03 | mlb3 | 153 (118) | 158 (1.03) | 265 (2.25) | -- | REFUSED (RAM) |
| 10-04 | mlb2 nfl3 | 121 (113) | 29 (0.24) | 85 (0.75) | 11 / 672 | 978 (1.46) |
| 10-05 | mlb1 | 184 (149) | 89 (0.48) | 397 (2.66) | 12 / 914 | 1120 (1.22) |
| 10-06 | mlb2 nfl1 | 565 (489) | 559 (0.99) | KILLED 1200 (>2.45) | 14 / 1064 | KILLED 1800 (>1.69) |

(10-02 and 10-04 fill rates are low because their books were nfl-heavy with little live mlb depth;
10-04 data spans only 18:14Z-19:00Z. Scoreboard: 111 s at 184 MB, 208 s at 565 MB. History 50-68 s.)

Tonight (night 10-07, about 06:05Z 10-08; dispatched mlb + nba; 7 served rows).
At 19:05Z the D shards are mlb books 128 MB, nba books 106 MB, mlb state 21 MB, nba state 17 MB,
with CLE at CWS (20:00Z), LAD at ATL (22:00Z) and MIN at IND (23:00Z) still to be captured live.
ESTIMATE of the input at 06:05Z: D books 410-580 MB, D+1 books (to 06:05Z) 90-260 MB, state 60-100 MB:
total 560-930 MB, books 500-840 MB (reference: night 10-06 read 565 MB; nba 10-06 shard 275 MB for
about 2.5 live preseason games). E window 10-01..10-07 + 10-08: 14 mlb games, 950-1,050 MB.

| step | deadline s | ESTIMATE s (uncontended) | fits? |
|---|---|---|---|
| qualification | 900 | 280-930 (0.5-1.0 s/MB) | likely; upper tail at the deadline |
| fill_realism | 1200 | 1,100-2,270 (2.2-2.7 s/books-MB; quadratic, may be worse) | NO, most likely KILLED |
| week | 300 | about 1 | yes |
| scoreboard | 900 | 210-560 | yes |
| history | 900 | 50-80 | yes |
| e | 1800 | 1,150-1,470 (1.2-1.4 s/MB; or 93 s/game x 14 = 1,300) | yes uncontended, 20-35 pct headroom; a 1.25x slowdown kills it |
| night total | 7200 (tick) | 2,900-4,250 (fill capped at 1,200) | yes; ends by about 07:20Z, before the 08:45Z books restart |
## 5. Contention vs scale for the 10-06 kills

- fill_realism: SCALE. Input was 3.1x night 10-05 (565 vs 184 MB; books 489 vs 149 MB). At night 10-05's
  own uncontended rate (2.66 s/books-MB) the run needs about 1,300 s, over 1,200 s with zero contention;
  the quadratic per-ticker loops make the true need larger. Contention may have added time but is not
  needed to explain the kill, and the share cannot be separated from the record.
- e: SCALE PLUS CONTENTION. Expected uncontended 1,300-1,450 s (14 games, about 1,040 MB at run time);
  the 1,800 s kill needs at least a 1.25x slowdown, consistent with the second pytest wave
  (18:37Z-18:4xZ) and the post-reboot I/O storm (S788 / S789; .planning/NOW.md DELTA 17:4xZ).
- qualification 559 s: 0.99 s/MB, inside the historical 0.24-1.40 band; mostly scale. Scoreboard 208 s
  shows no visible slowdown per MB. So the step-level evidence of contention is weak except for E.
## 6. Recommendation: (c) input-cost fix, with no budget change tonight

A deadline raise alone does not fix fill_realism: the tonight estimate (1,100-2,270 s) straddles any
value that keeps the worst-case step sum under the 7,200 s tick timeout (fill_realism 1800 gives
6,600 + 600 = 7,200 s, zero headroom). Tonight, expect fill_realism KILLED (night PARTIAL, no
fill_realism/2026-10-07.json); record it as a scale outcome, not a defect of the night. E should fit.

PROPOSED register row (no id; dispatcher allocates):

FILL_REALISM PER-TICKER REPLAY IS QUADRATIC IN LIVE BOOK ROWS: EXACT-OUTPUT INDEXING FIX
- Evidence: this memo sections 2, 4, 5; nights/2026-10-06.json fill_realism KILLED 1200.4 s on 565 MB;
  S779 scratch night B KILLED at 600 s after adding 4 nba games; nba 10-06 shard 600 tickers, live
  tickers 5-7k snapshots each.
- Fix (identity-preserving, artifact bytes unchanged):
  1. Profile first: cProfile one scratch-root fill_realism run on hard-linked 10-05 inputs to rank the
     loops (fill_realism.py:198, :213, :214-219; tape_fill_sim.py:55, :214) before editing.
  2. fill_realism.py:213 -> dict lookup keyed (ticker, ts, side, price) built once per scenario;
     :219 -> Counter of fill qty keyed (quote_id, trade_id) built once from result['fills'];
     :214 -> prints grouped by (ticker, side) and sorted by ts, with the outside_quote_life count for
     prints outside (submit_ts, cancel_ts) computed arithmetically (bisect) instead of per print;
     :198 -> build the prepared-row list once per scenario, not per fill.
  3. tape_fill_sim.py:55 -> per-ticker books sorted by ts with bisect for the latest-at-or-before set.
  4. fill_realism_io.py:183/:199 -> keep one open handle per path for the run instead of one open per row.
  5. Emit one progress line per ticker to stderr (ticker index / total, rows) so a kill is diagnosable.
- Alternative (IDENTITY CHANGE, needs its own spec): replay only tickers of served events.
- Acceptance tests: (a) byte-identical fill_realism/<D>.json for scratch reruns of nights 10-03 and
  10-05 (sha256 equal to the committed artifacts); (b) a scratch rerun of night 10-06's argv on
  hard-linked inputs completes under 600 s with the box quiet; (c) the existing per-file tests
  test_fill_realism_1d, test_paper_maker_fill_realism, test_queue_sensitivity,
  test_fill_model_fill_realism, test_paper_night_qualification_isolation pass one per process;
  (d) a unit check that a synthetic ticker with 4,000 snapshots and 4,000 prints runs in under 10 s.
- LOC impact: fill_realism.py is 298 of 300 LOC, so the new indexes must be net-zero there or live in
  fill_realism_markout.py (91 LOC) or a new fill_realism_index.py (about 60 LOC); tape_fill_sim.py
  296 LOC: the bisect helper also goes in the new module. fill_realism.py is copied into
  test_paper_night_qualification_isolation.py:45, so that test must stay green. No seal file touched.

What must be true for night 10-07 to be judged on scale, not contention:
- The night starts on the 06:05Z tick (not a daytime retrospective run) on a box awake since at least
  the previous evening (warm cache, no reboot ingest).
- No agent lanes, codex lanes or pytest processes from 06:00Z to the night's end (focus-hour rule).
- No S789 recovery ingest running and polymarket either still stopped or on the S788 fix (no
  whole-shard re-read per tick); state capture heartbeats fresh.
- The night record shows free_ram_at_start_bytes above every floor (no RAM deferral) and the
  qualification snapshot bytes are recorded (the input size the rates above use).
If those hold and fill_realism is killed again, the kill is scale and the row above is the fix; if E
is killed under those conditions, E needs its own row (mlb-window input cost), not a deadline raise.

Disclosure: at about 19:02Z this lead started a repo-wide recursive grep that also walked data/
(about 2 minutes, before the 19:55Z quiet window) and stopped it once noticed; one shard (nba books
2026-10-06) was stream-read at 19:06Z (2.8 s, RSS 19 MB).
