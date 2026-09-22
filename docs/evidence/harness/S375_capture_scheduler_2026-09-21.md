# S375 capture scheduler

FIX 1c local CONSTRUCT checks pass under S375 AMENDMENT 1.
Independent verifier acceptance remains pending.
The binding amendment was read with
`git show master:docs/evidence/tracking/specs/S375_spec.md`; the worktree spec
predates it and was left unchanged. Independent acceptance is the orchestrator's.

## Fix lane 1b changes

- Zero-budget ticks return no requests and zero allocations, increment the strict
  integer `budget_exhausted_ticks`, preserve admission, cooldown, slow-tick state,
  carried tasks and cursors, and never emit a focus drop.
- Heartbeats expose the new strict integer counter. The runner preserves focus
  tracking on empty ticks. Under the controller lock, the empty-budget route uses
  the controller's existing timed STEP/CEILING increase; no acquire or HTTP call
  is fabricated. Normal positive-budget AIMD behavior remains unchanged.
- A one-request budget gives its sole slot to an eligible single-ticker focus game,
  except every twentieth positive-budget tick reserves it for bulk. Multi-ticker
  games still require whole-game capacity and are never partially admitted.
- Bulk gets at least one request whenever focus leaves room, and a reserved
  request every 20 positive-budget ticks. Integer slots are transferred from
  unused focus, reserve, trades, discovery, then focus when required by the bound.
  Other unused shares still roll down. No request credit carries between ticks.
- The two amendment tests cover 100 empty ticks with existing focus and two prior
  slow ticks, counter/heartbeat and AIMD recovery, and 100 budget-one ticks with
  focus service on the other 95 ticks and bulk at 20/40/60/80/100. Existing tests
  also assert bulk cursor progress on every positive-budget tick with room, and
  reject non-integer exhaustion/service counters.

## BINDING BEFORE-CONDITION

Original candidate before-condition evidence (before its edits): the three
named capture modules matched master: `git diff master -- scripts/platformkit/ingame/local_capture_runner.py scripts/platformkit/ingame/local_capture_runner_row.py scripts/platformkit/ingame/local_capture_runner_trades.py`
returned exit 0 with empty output. The absence probe returned exit 1:

```text
Get-Item : Cannot find path 'scripts/platformkit/ingame/capture_scheduler.py' because it does not exist.
```

Master tick order (rechecked in lane 1b): `_markets` discovers each expired sport cache, then live
winner books alternate with fresh trade groups; deferred historical trade groups
follow; derivative event bulk requests follow; cursor commits and heartbeat finish
the tick. `GovernedClient.get` calls `self.aimd.acquire(self.sleep_fn)` inside its
attempt loop. `AIMDController.acquire` serializes starts with `next_send`, interval
`1.0 / self.rate + self.RELEASE_GUARD_SEC`, and shared retry cooldowns. This does
not impose a five-second tick deadline or request-class allocation.

## Landed interfaces read before coding

Exact signatures relied on (the controller is re-exported by the row module;
discovery actually lives in local_capture_state.py):

```python
def parse_venue_time(value: object) -> float | None:
def is_winner_series(series_ticker: str | None) -> bool:
def round_robin_select(items: list, offset: int, cap: int) -> tuple[list, int]:
def classify_state(market: dict, sport: str, now, errors=None) -> tuple[str, float]:
def discover_sport(client, sport: str, now, series_by_sport: dict) -> list | None:
def commit_groups(writer, state: dict, pending: list) -> None:
def prune_state(state: dict, markets: list, sports: list, day: str) -> None:
def heartbeat(client, writer, state: dict, sports: list, markets: list, before: dict) -> dict:
def seed_group(root: Path, market: dict, metrics, now=None) -> TradeGroup | None:
def capture_group(client, writer, market: dict, group: TradeGroup, tick_start: str,
                  page_budget: int = 20):
def book_row(market: dict, body: Any, ts_ms: int, capture_ts: str,
             enqueue_ts_ms: int | None = None, close_time: str | None = None,
             *, request_start: str, response_end: str, http_status: int, errors=None) -> dict:
def bulk_row(sport: str, series_ticker: str | None, event_ticker: str | None, m: dict,
             capture_ts: str, request_start: str, response_end: str, http_status: int,
             errors=None) -> dict:
def record_book_snapshot(state: dict, sport: str, ticker: str, now: float) -> None:
def iso(value: Optional[datetime] = None) -> str:
def utcnow() -> datetime:
def drain(client: GovernedClient, url: str, params: dict, key: str,
          source: str, max_pages: int = 200, *, page_budget: int | None = None,
          continuation: dict | None = None, sport: str | None = None) -> list | None:
# GovernedClient
def get(self, url: str, params: dict | None = None, source: str = "http") -> Response:
# AIMDController
def acquire(self, sleep_fn: Callable = time.sleep) -> None:
def stats_10min(self) -> tuple[int, int, float]:
# ArchiveWriter
def append(self, row: dict, source: str, quarantine: bool = False) -> Path:
def sync(self) -> None:
def atomic(self, path: Path, value: dict, source: str) -> None:
```

The spec supplies no REAL ROW. Tests use explicit constructed markets.

## Implementation and interpretation

- `plan_tick` is pure, copies input state, accepts injected time, and returns its
  next state. Admission sorts live before due pregame, expiration, then ticker.
  A game's supplied sides enter and leave together. Duplicated ticker rows are
  counted and refused, including the other side's focus eligibility. Missing or
  invalid expiration is counted. Future receipts are skipped before row validation.
- Five-second budgets use the exact integer ratio of the supplied rate. The
  declared shares are 45 / 35 / 10 / 5 / 5 percent. Focus capacity is the integer
  floor of its share, except the amended budget-one service rule. Lower classes
  retain fractional percentage entitlements above a one-request budget
  between ticks, including clipped whole entitlements; no HTTP credit crosses a
  tick. Rounding residue goes to reserve. Unused class allocations roll downward.
- At rates 0.5 / 1 / 2 / 3, budgets are 2 / 5 / 10 / 15 and focus ticker capacities
  are 0 / 2 / 4 / 6. Under constructed continuous demand, five bulk event units
  receive service within 50 ticks at each rate; five discovery units receive
  service within 60 ticks at rate 0.5. These are enumerated fixture bounds, not a
  universal bound under arbitrary HTTP latency or a changing eligible set.
- With rate below 0.2, `floor(rate * 5)` is zero. The amended empty-plan rule
  applies; no service bound is claimed until budget is positive. Exhausted ticks
  do not consume the 20-tick reservation counter or change focus admission.
- Three consecutive ticks with cadence p90 above 7 seconds drop the latest
  admitted game. A dropped game needs 60 seconds of continuously observed clean
  cadence before admission. Paired recovery probes use spare focus capacity,
  after admitted games, so losing the final game does not prevent recovery.
  Probes are excluded from admitted focus counts. Cadence uses per-ticker latest
  completed interval, conservatively extended by current outstanding age; nearest
  rank p50/p90 are decimal strings, with "0" and strict-integer
  `focus_cadence_samples=0` when this tick has no samples.
- The CLI uses scheduling by default; `--no-scheduler` selects legacy behavior.
  Existing Python API defaults remain compatible; callers can pass
  `scheduler_enabled=True`. A scoped ContextVar carries CLI mode while preserving
  the existing forwarded CLI arguments. The legacy selection helper is pure;
  only the owned runner applies the returned rotation updates.
- Each scheduled trade, bulk or discovery task drains at most one page. Actual
  attempts pass a deadline guard before and after AIMD admission. Retries consume
  reserve. Tasks unable to start remain carried and increment missed deadlines;
  carried tasks with no current allocation remain queued. Obsolete carried tasks
  are explicitly counted. Request counters include actual starts only.
- Incomplete discovery pages remain staged until completion; invalid nested rows
  retain the prior cache. A counted hard page-limit refusal resets the continuation
  rather than leaving a permanently exhausted cursor. Bulk continuation is also
  resumed, and reset on a counted hard limit. No other capture module was edited.
- Archive writes and trade commits use the existing append/sync/checkpoint path.
  Heartbeat additions use atomic replacement. Drop records use atomic files named
  `_focus_drops_<cumulative_count>.json`. Request-class and missed/drop totals in
  each sport heartbeat are capture-wide; admitted game/ticker counts are per sport.
  Scheduler rotation, admission and bulk/discovery continuation state is in memory.

## Reproduction and evidence

Machine: this Windows worktree, CPU only. No network, archive, capture process or
production output directory was used. All test input was constructed in code.
Image/video resolution is not applicable. The test source is
`C:/Users/neelj/nba-harness-h41/tests/platformkit/ingame/test_capture_scheduler.py`
(19830 bytes, 300 lines); the first test consumes its constructed pair through
the real client, runner, archive writer and heartbeat using fake HTTP.

Run each command separately with the stated suffix:
`python -m pytest <file> -q -p no:cacheprovider`.

| File under tests/platformkit/ingame/ | Passed |
| --- | ---: |
| test_capture_scheduler.py | 98 |
| test_local_capture_runner.py | 8 |
| test_local_capture_backfill.py | 12 |
| test_local_capture_failures.py | 17 |
| test_local_capture_fix1c.py | 24 |
| test_local_capture_fix1e.py | 41 |
| test_local_capture_io.py | 35 |

Total: 235 passing cases, including 98 scheduler CONSTRUCT cases. The six landed
capture test files are unchanged. No full-suite command was run.

Owned Python sizes from `len(text.splitlines())`: capture_scheduler.py 300 lines
(16776 bytes), local_capture_runner.py 300 lines (16986 bytes), test file 300
lines (19830 bytes). All three decode as ASCII. The memo is ASCII as well.

`python -m scripts.platformkit.ingame.local_capture_runner --help` succeeds and
lists `--no-scheduler`. The planner is a library, not a CLI.

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/capture_scheduler.py scripts/platformkit/ingame/local_capture_runner.py tests/platformkit/ingame/test_capture_scheduler.py docs/evidence/harness/S375_capture_scheduler_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S375_spec.md
```

Mechanical preflight: nine PASS checks, zero FAIL. No deployment or restart
was performed. The amended spec was read from master; the command above uses the
required local spec path, whose mechanical threshold section is unchanged.

## Orchestrator-only smoke commands

Choose distinct empty scratch roots. Run these side by side only under the
orchestrator's authorization; the builder did not execute them:

```text
python -m scripts.platformkit.ingame.local_capture_runner --output-root <scratch>/scheduled --max-ticks N --sports mlb,nfl
python -m scripts.platformkit.ingame.local_capture_runner --output-root <scratch>/legacy --max-ticks N --sports mlb,nfl --no-scheduler
```

Compare actual start times, heartbeat request counts, focus cadence and missed
deadlines. A slow response may finish after a tick; the guard prevents subsequent
requests from starting at or beyond that tick's deadline.

## FIX 1c

The root verdict `_verdict_s375_1c.md` was read before any edits. Findings 1-3
were reproduced against the candidate before fixes. Finding 4 is a NOTE:
its confirmed amendment logic and CLI behavior were preserved.

1. BLOCKING: capacity loss removed the latest admitted game without slow cadence.
   Failing output from the constructed rates 2 then 1, with no cadence samples:
   `F1 before=(('mlb', 'A'), ('mlb', 'B')), after=(('mlb', 'A'),), drops=((('mlb', 'B'), 'capacity'),), carry=()`
   Removed capacity-triggered drops. New admissions still respect capacity;
   existing admissions remain until closure or the specified three slow ticks.
   Unscheduled focus requests are carried and counted each positive-budget tick;
   the runner includes that count in missed deadlines and tracks all admitted
   tickers for cadence. The no-churn regression replaces the capacity-drop test;
   the runner regression checks two successive reduced-rate ticks and counts.
   Passing reproduction: both games retained, `drops=()`,
   `carry=(('focus_books', 'BA'), ('focus_books', 'BB')), unscheduled=2`.
2. BLOCKING: carry ordering selected different requests with one available slot.
   Failing outputs:
   `F2 carry=[('bulk', ('mlb', 'A')), ('bulk', ('mlb', 'B'))] => requests=(('bulk', ('mlb', 'A')),)`
   `F2 carry=[('bulk', ('mlb', 'B')), ('bulk', ('mlb', 'A'))] => requests=(('bulk', ('mlb', 'B')),)`
   Added validation, tuple normalization, deduplication and canonical class/key
   sorting before selection, zero-budget storage and runner serialization.
   Regression enumerates all carry permutations with duplicate requests against
   all market permutations at both positive and zero budget, comparing full plans
   and serialized contents. Malformed carry inputs are rejected.
   Passing reproduction: both orders return `requests=(('bulk', ('mlb', 'A')),)`
   and `carry=(('bulk', ('mlb', 'B')),)`.
3. BLOCKING: startup heartbeat cadence was null. Failing output:
   `F3 focus_cadence_p50_sec=None (NoneType)`
   `F3 focus_cadence_p90_sec=None (NoneType)`
   Planner and heartbeat now emit finite decimal strings on every tick. Per the
   orchestrator ruling, no samples means literal string "0" for both percentiles
   and strict-integer `focus_cadence_samples=0`. This counter distinguishes an
   unsampled tick from sampled fast cadence. Regression asserts exact values and
   types at startup, zero budget, sampled cadence and invalid sample rejection.
   Passing output: `F3 PASS focus_cadence_p50_sec='0' (str)`,
   `F3 PASS focus_cadence_p90_sec='0' (str)`,
   `F3 PASS focus_cadence_samples=0 (int)`.

The first regression run reported `4 failed, 94 passed`: missing outer-container
validation raised TypeError for None and accepted an empty dict. After adding
that validation, the same per-file command reported `98 passed`.
All six unchanged landed capture files passed with the counts in the table above.
Pytest temporary fixtures used `PYTEST_DEBUG_TEMPROOT` inside this worktree at
`.pytest_cache/s375_1c_tmp`; `PYTHONDONTWRITEBYTECODE=1` prevented import caches.
The planner exposes no CLI self-check; its constructed tests cover that role.
The runner help command passed. No live capture command was executed.
The heartbeat reader survey found the owned runner and owned test references;
no tracked reader matched these cadence fields in `git grep` over scripts/tests.

## NOT VERIFIED

- Actual venue behavior, live book cadence, state freshness, or qualification of
  any real game. No network smoke, real archive, pod or measured corpus was used.
- Process-crash recovery of scheduler admission, cooldown, rotation, carried work,
  or bulk/discovery continuation. Those new states are currently memory-only.
- New scheduler behavior across a UTC day rollover, multi-day uptime, changing
  sport scope, or arbitrary changing market universes; fixtures are bounded.
- Power-loss testing and process-level filesystem failures on the scheduled route;
  the unchanged writer's existing fault-injection tests were run.
- New validation of raw prices, quantities, fees or trade-watermark recovery beyond
  the landed parsers. Their modules were outside this row's edit ownership.
- Byte-for-byte legacy output under `--no-scheduler`; the candidate mode test
  checks selection only, while landed capture tests exercise legacy fixtures.
- Independent verifier acceptance, deployment and production restart.
