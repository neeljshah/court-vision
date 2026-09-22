GAP S375 | sport all captured | worktree harness-h41 (master-based) | log cx_s375_capture_scheduler
# Budgeted capture scheduler: a few live winner books at 5 s instead of ~1,200 markets at tens of seconds (design: ASTRA_ROUND13 section 1 row 1)

SINGLE PROBLEM: the anonymous request rate (an adaptive 0.5 to 3 requests per second) is spread over about 1,200 markets, so a live
book is refreshed every tens of seconds. The forward replay (row S362) needs book age <= 5 s and state age <= 15 s at a decision, so
NO game can qualify today. Breadth has to be bought with what is left after a small, stable focus set is served on time.

BINDING BEFORE-CONDITION: read scripts/platformkit/ingame/local_capture_runner.py, local_capture_runner_row.py (AIMDController,
round_robin_select, discover_sport) and local_capture_runner_trades.py (classify_state) on master; quote in the memo the current
per-tick order of work and where the request rate is enforced. `ls scripts/platformkit/ingame/capture_scheduler.py` fails.

CHANGE (owned files: NEW scripts/platformkit/ingame/capture_scheduler.py, local_capture_runner.py, NEW
tests/platformkit/ingame/test_capture_scheduler.py, the memo; edit NO other capture module):
1. capture_scheduler.py (<= 300 LOC, pure, no I/O, injected clock): `plan_tick(now, rate_per_sec, markets, focus_state, params) ->
   TickPlan`. Budget for a 5 s tick = floor(rate_per_sec * 5) requests, split by declared shares 45 / 35 / 10 / 5 / 5 percent:
   focus books, trades for focus + other live tickers, bulk snapshots of everything else (round robin, resumable cursor),
   discovery, reserve for retries. Unused share rolls DOWN that list in order, never up. All budget arithmetic is integer.
   FOCUS SET: winner markets only; candidates ordered by (live before due-pregame, earlier expected_expiration_time, ticker); both
   sides of one game count as ONE focus unit and are admitted or dropped together; capacity = the number of tickers the focus share
   can refresh once per tick; admission is STICKY (an admitted game stays until it ends or is dropped by rule, so a series has no
   churn gaps); when measured focus book cadence p90 exceeds 7 s for 3 consecutive ticks the LATEST-admitted game is dropped and
   the drop is recorded with its reason; re-admission needs 60 s of clean cadence. Selection is deterministic: same inputs, same
   plan, independent of dict or list order. Missing expected_expiration_time -> never focus (counted), never guessed.
2. local_capture_runner.py: the tick loop asks the scheduler for a plan and executes it in plan order; a request that cannot start
   inside the tick is carried, counted as a missed deadline, and never silently skipped. `--no-scheduler` keeps today's behaviour.
   Heartbeat adds (strict ints / decimal strings): focus_games, focus_tickers, focus_cadence_p50_sec, focus_cadence_p90_sec,
   requests_by_class, missed_deadlines_total, focus_drops_total.
3. tests (no network): budget split and roll-down at rates 0.5 / 1 / 2 / 3; both sides admitted together; stickiness across ticks;
   drop on three slow ticks and the 60 s re-admission rule; determinism under shuffled input; missing expiration never focused; zero
   budget (rate below one request per tick) serves focus first and starves nothing forever (bulk cursor still advances within a
   bounded number of ticks -- state the bound); every landed capture test file still passes unchanged.
4. Memo docs/evidence/harness/S375_capture_scheduler_2026-09-21.md incl. the side-by-side smoke command (`--output-root <scratch>
   --max-ticks N --sports mlb,nfl`) that the ORCHESTRATOR will run; the builder runs no network.

CONTROLS: construct tests only, no network, never touch a running capture or its output root. ACCEPTANCE: per-file tests pass one at
a time; --help works; <= 300 LOC per file; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list. The pod is OFF.

AMENDMENT 1 (2026-09-21; binding; the build lane correctly refused to manufacture a pass). The zero-budget clause in CHANGE 3
("rate below one request per tick ... bulk cursor still advances within a bounded number of ticks") is WITHDRAWN as written: a
budget of zero requests cannot serve anything in finite time, and fabricating a request to satisfy a bound would be worse.
Replacement rule: with floor(rate * 5) == 0 the plan is EMPTY, `budget_exhausted_ticks` (strict int) is incremented, the focus set
is left untouched (no drop is triggered by ticks that served nothing), and the AIMD controller's creep is what restores service;
the bound that IS required: once the budget is >= 1 request per tick, the bulk cursor advances by at least one market every tick
in which the focus share leaves a remainder, and by at least one market every 20 ticks unconditionally (a reserved bulk request
every 20 ticks). Tests: zero budget for 100 ticks -> no fabricated request, no drop, counter 100; budget 1 -> focus served, bulk
cursor advanced at least once per 20 ticks. Everything else in the spec stands.

