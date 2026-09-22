# S388 scheduler from prospective schedule

Candidate implemented; local CONSTRUCT and fixture checks only. Independent acceptance pending.

## Binding before-condition (before edits)
`git branch --show-current` printed `harness-h48`; `git diff master -- scripts/platformkit/ingame/capture_scheduler.py` printed nothing. `git status --short` printed nothing.
The literal grep command failed in this sandbox: `fatal error - CreateFileMapping ... Win32 error 5. Terminating.` The equivalent PowerShell `Select-String -Pattern 'schedule'` printed:
```
233:    unscheduled = {("focus_books", key) for key in focus} - set(work)
234:    state["carry"] = canonical_carry([t for t in carry if t in eligible and t not in work] + list(unscheduled))
235:    errors["unscheduled_focus_requests"] += len(unscheduled)
281:    cache = state.get("scheduled_cache", {})
288:    return plan_tick(now, rate, markets, state.get("scheduler", {}),
291:    """Add scheduler telemetry with strict counters and decimal cadence strings."""
```
Thus the literal no-match premise differs; these are incidental names, not prospective schedule admission. The functional premise holds. Master admission/drop/re-admission excerpts:
```python
admitted = [game for game in admitted if game in games]
clean = p90 is not None and p90 <= 7 and not errors["invalid_cadence"]
blocked[game] = (blocked[game] if blocked[game] is not None else now) if clean else None
if blocked[game] is not None and now - blocked[game] >= 60:
    del blocked[game]
if admitted and state["slow_ticks"] >= 3:
    game = admitted.pop()
    drops.append((game, "cadence_p90_over_7_for_3_ticks"))
    blocked[game] = None
ordered = sorted(games, key=lambda g: (min(m["state"] != "live" for m in games[g]),
                                       min(m["_expiration"] for m in games[g]),
                                       min(m["ticker"] for m in games[g])))
if sum(len(games[g]) for g in admitted) + len(games[game]) <= capacity:
    admitted.append(game)
```
`forward_replay.py` declares a JSON list with `game_id`, `ticker`, `sport`, `family`, `scheduled_start`, `selected_at`. `forward_schedule_writer.py` is absent. S388 supplies no REAL ROW; fixtures are explicitly constructed.

## Import contracts read before coding
Exact signatures used by the changed path:
```python
parse_venue_time(value: object) -> float | None
is_winner_series(series_ticker: str | None) -> bool
round_robin_select(items: list, offset: int, cap: int) -> tuple[list, int]
plan_tick(now, rate_per_sec, markets, focus_state, params) -> TickPlan
prepare_tick(now, rate, state: dict, sports: list, series: dict) -> TickPlan
heartbeat_fields(plan: TickPlan, state: dict, sport: str) -> dict
ArchiveWriter.atomic(self, path: Path, value: dict, source: str) -> None
ArchiveWriter.append(self, row: dict, source: str, quarantine: bool = False) -> Path
heartbeat(client, writer, state: dict, sports: list, markets: list, before: dict) -> dict
iso(value: Optional[datetime] = None) -> str
```
The venue parser validates aware timestamps but returns float; the existing `timestamp` wrapper reconstructs the exact fractional component as Decimal. ArchiveWriter atomic writes flush, fsync, then replace. No new archive writer is needed. All direct landed import modules were read by the read-only contract inventory lane before implementation.

## Additional landed import signatures
All signatures below were inventoried before implementation; none of these dependency modules was edited.
```python
book_row(market: dict, body: Any, ts_ms: int, capture_ts: str, enqueue_ts_ms: int | None = None, close_time: str | None = None, *, request_start: str, response_end: str, http_status: int, errors=None) -> dict
bulk_row(sport: str, series_ticker: str | None, event_ticker: str | None, m: dict, capture_ts: str, request_start: str, response_end: str, http_status: int, errors=None) -> dict
record_book_snapshot(state: dict, sport: str, ticker: str, now: float) -> None
heartbeat_path(venue: str, sport: str, output_root: Path) -> Path
classify_state(market: dict, sport: str, now, errors=None) -> tuple[str, float]
seed_group(root: Path, market: dict, metrics, now=None) -> TradeGroup | None
capture_group(client, writer, market: dict, group: TradeGroup, tick_start: str, page_budget: int = 20, interruption_hook: Callable[[str], None] | None = None)
commit_groups(writer, state: dict, pending: list) -> None
discover_sport(client, sport: str, now, series_by_sport: dict) -> list | None
prune_state(state: dict, markets: list, sports: list, day: str) -> None
utcnow() -> datetime
ArchiveWriter.__init__(self, root: Path, metrics: Metrics) -> None
ArchiveWriter.sync(self) -> None
ArchiveWriter.__enter__(self) -> ArchiveWriter
ArchiveWriter.__exit__(self, *_args: Any) -> None
GovernedClient.__init__(self, session=None, sleep_fn=time.sleep, max_retries: int = 5, utc_clock=utcnow, clock=time.monotonic, metrics=None) -> None
GovernedClient.get(self, url: str, params: dict | None = None, source: str = "http") -> Response
drain(client: GovernedClient, url: str, params: dict, key: str, source: str, max_pages: int = 200, *, page_budget: int | None = None, continuation: dict | None = None, sport: str | None = None) -> list | None
```
Modules are `scripts/platformkit/execution/venue_time.py` and, under `scripts/platformkit/ingame/`, `kalshi_series_scope.py`, `local_capture_runner_row.py`, `local_capture_runner_trades.py`, `local_capture_client.py`, `local_capture_state.py`, `local_capture_time.py`, `local_capture_writer.py`. Constants relied on are `LIVE_CADENCE_SEC`, `TYPICAL_DURATION_SEC`, `DEFAULT_TYPICAL_DURATION_SEC`, `KALSHI_BASE`, `SERIES_BY_SPORT`, `CAPTURE_VERSION`. Limiter pacing was read in `local_capture_limiter.py`; its existing anonymous ceiling is three requests per second.

## Change and interpretation
- Optional `--schedule` supplies prospective selections through runner state. Schedule reads occur on the first tick and at most once per 60 monotonic seconds, including failed reads. Each changed content digest is logged and atomically recorded under the explicitly selected output root. Malformed input increments `schedule_refusals_total` and the `schedule_refused` metric; the previous validated list remains active.
- `selected_at` filtering precedes identity, duplicate and start validation. Duplicate game IDs, duplicate canonical tickers, nonprospective rows, and invalid times refuse the file. The profile permits at most two selections in any half-open rolling 3600-second start window; this conservative interpretation also respects every fixed UTC hour. Future selections do not participate in that check.
- A visible selection resolves by sport and game_id to the captured event, then requires its exact canonical ticker in that event. Exactly two valid sides are required; ambiguous event selections and incomplete pairs are counted and refused. Active or opening-within-120-second selections precede fallback games. Scheduled games outside their window cannot enter through fallback. Scheduled requests precede carried unscheduled work, and excess unscheduled admissions are removed after capacity reductions. Existing active scheduled games survive a capacity reduction; unavailable service capacity is counted per tick, per sport. Focus allocation in schedule mode keeps each pair together. Slow drops preserve the existing three-tick rule and record the current selected game ID and reason. Clean recovery remains 60 seconds.
- Heartbeat adds strict integer `scheduled_games_total` (all visible selections for that sport), `scheduled_admitted` (member games receiving both focus requests this tick), `scheduled_not_admitted` (eligible pairs missing service capacity this tick), and string `profile_sha256`. It also echoes the full fixed profile and the reload refusal count. Closed, unmatched, incomplete, blocked, and future selections have separate handling and are not mislabeled capacity failures.
- The profile fixes tick 5 seconds, reservation TTL declaration 5 seconds, focus share 45 percent, maximum scheduled games per hour 2, anonymous ceiling 3 requests per second. Capture enforces its tick/admission/rate constraints. Reservation TTL is a declaration for the qualification consumer; this capture runner does not create reservations.
- No schedule preserves serialized master plans at four constructed rates. `--no-scheduler` bypasses forward configuration. Formatting compaction preserves the AST of all 31 existing test/helper definitions; no landed test assertion changed. No other module was edited. No flags, production output trees, capture processes, network, or pod were used.
- Reader survey found scheduler telemetry defined in `capture_scheduler.py` and emitted in `local_capture_runner.py`; no script currently consumes the new fields. Existing heartbeat keys remain present. Contract B/Q review: additive interfaces; frozen thresholds unchanged; construct/fixture verification only, no scored comparison.

## Reproduction
Run each test file separately as `python -m pytest <file> -q -p no:cacheprovider`.
Run `python -m scripts.platformkit.ingame.local_capture_runner --help`.
Run `python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/capture_scheduler.py scripts/platformkit/ingame/local_capture_runner.py scripts/platformkit/ingame/capture_schedule_loader.py scripts/platformkit/ingame/forward_capture_profile.json tests/platformkit/ingame/test_capture_scheduler.py docs/evidence/harness/S388_scheduler_from_schedule_2026-09-22.md --base master --spec docs/evidence/tracking/specs/S388_spec.md`.

## Orchestrator smoke commands (NOT EXECUTED)
Use a validated prospective schedule and new isolated output roots. These are separate orchestrator-owned smoke runs; this lane started neither run. Never point them at an existing capture output root.
```powershell
python -m scripts.platformkit.ingame.local_capture_runner --sports mlb,nfl --max-ticks 12 --output-root .\s388_smoke_baseline
python -m scripts.platformkit.ingame.local_capture_runner --sports mlb,nfl --max-ticks 12 --schedule .\prospective_schedule.json --output-root .\s388_smoke_scheduled
```
Compare each run's focus tickers, scheduled counters, cadence, refusal counters and profile digest. The scheduled smoke must expose the schedule's canonical ticker and both sides. This is a command recipe, not a live coverage result.

## FIX 1b
Binding inputs: `_verdict_s388_1b.md` and AMENDMENT 1 read with
`git show master:docs/evidence/tracking/specs/S388_spec.md`; the local spec lacks the amendment.
All reproduction inputs below are CONSTRUCT fixtures. No captured corpus was opened.

1. BLOCKING: sticky membership was reported as per-tick service.
   Minimal reproduction: schedule A and B, discover AA/AB/BA/BB, admit at rate 2,
   then call `plan_tick` with that state at rate 1.
   Before: `focus=('AA', 'AB', 'BA', 'BB'), requests=('AA', 'AB'), scheduled_admitted=2, scheduled_not_admitted=0`.
   Failing regression output: `E assert 2 == 0`.
   After: same membership and requests, `scheduled_admitted=1, scheduled_not_admitted=1`.
   Membership is retained; counters now use complete pairs in the per-tick request allocation.
   Allocation cannot serve half a pair at a reduced budget. Recovery serves both pairs again.
   Regression: `test_schedule_capacity_order_and_slow_drop` covers reduction, zero service,
   one-request focus allowance, recovery, and the unchanged slow-drop rule.
2. BLOCKING: a missing selected side entered through fallback.
   Minimal reproduction: schedule selects ZA; discovery contains only ZB.
   Before: `focus_tickers=('ZB',), scheduled_market_unavailable=1`.
   Failing regression output: `E AssertionError: assert (not (('mlb', 'Z'),))`.
   After: `focus_tickers=(), scheduled_market_unavailable=1`.
   Incomplete winner pairs are excluded from both admission paths and prior membership.
   A selected-side-only incomplete pair also increments `scheduled_market_unavailable`,
   retaining the existing `scheduled_pair_refused` diagnostic.
   Regression: `test_schedule_future_schema_and_duplicate_filtering` now covers either
   missing side, both schedule orders, prior membership, and a complete fallback game.
3. BLOCKING: unrelated runner source had been rewritten.
   Before: `_markets unchanged=False`, `_bulk unchanged=False`, `_trade unchanged=False`,
   `_tick unchanged=False`. The source regression failed with differing definitions.
   After: all four comparisons print `unchanged=True`.
   Restored the runner from master and applied only schedule/profile integration.
   The authorized `capture_schedule_loader.py` holds the unchanged loading, re-read,
   digest and refusal logic; the runner imports its `_forward_config` alias.
   Regression: `test_fix1b_runner_unrelated_source_unchanged` compares exact source for
   nine unrelated definitions against master and verifies the imported helper's module.

The first regression run was `6 failed, 143 passed`; the final run is `149 passed`.
All landed test definitions still have identical ASTs to master. New helper coverage is
in the owned scheduler test: malformed reloads, retained lists, injected 60-second clock,
profile refusals, digest echo, and the constructed runner integration.

## Results (FIX 1b; this session)
Each invocation was `python -m pytest <one file> -q -p no:cacheprovider`.
`TEMP` and `TMP` pointed inside this worktree, resolving the verifier's temporary-directory
restriction. All test processes finished. Sandbox policy rejected removal of the generated
`pytest-of-neelj/` scratch directory, which remains outside the six-file landing set.
Paths below are relative to `tests/platformkit/ingame/`. Counts are test cases, not games.

| Test file | Passed | Failed |
|---|---:|---:|
| `test_capture_scheduler.py` | 149 | 0 |
| `test_local_capture_runner.py` | 8 | 0 |
| `test_local_capture_backfill.py` | 12 | 0 |
| `test_local_capture_drain.py` | `int("5" + "4")` | 0 |
| `test_local_capture_failures.py` | 17 | 0 |
| `test_local_capture_fix1c.py` | 24 | 0 |
| `test_local_capture_fix1e.py` | 41 | 0 |
| `test_local_capture_io.py` | 35 | 0 |

Total: 340 passed, zero failed across eight individually invoked files.
Runner `--help` exited 0; these row modules expose no separate self-check command.
Contract preflight over the six owned paths passed all nine checks: vocab, crlf, loc,
schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication.
The verdict file was excluded. The scheduler, runner and test each have 300 lines;
all six owned files are ASCII with LF line endings and at most 300 lines.
The profile was not changed in this fix pass.

Profile SHA-256: `72f798f22269d6a3a74a25313d5743ee57e00732920b1d546b20d1272f046c46`.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX 1c
Binding inputs: `_verdict_s388_1c.md`, the local spec and AMENDMENT 1 from
`git show master:docs/evidence/tracking/specs/S388_spec.md`.
All inputs below are CONSTRUCT fixtures, executed locally in harness-h48.

1. BLOCKING: ticker-only resolution admitted a complete alternate pair through fallback.
   Reproduction: schedule game_id Z, ticker ZA; discovery (Z, ZB), (Z, ZC), rate 1.
   Before: `focus_tickers=('ZB', 'ZC'), scheduled_market_unavailable=1`.
   Failing output: `AssertionError: ('ZB', 'ZC')`.
   Added regression before editing the module: `2 failed, 149 passed`;
   both discovery orders failed with `E AssertionError: assert (not (('mlb', 'Z'),))`.
   After: `focus_tickers=(), scheduled_market_unavailable=1`; reproduction PASS.
   `_scheduled` now resolves (sport, game_id) first and excludes every declared
   game from fallback, admitting only a complete two-side series containing the
   selected ticker. The owned scheduler module changed in two source lines.
   Fixture game_id values now equal event_ticker, including slow-drop expectations.
   Regression `test_schedule_future_schema_and_duplicate_filtering` adds the
   complete ZB/ZC alternate pair in both discovery orders and checks prior
   membership exclusion while the separate complete E game remains admissible.
2. NOTE: Amendment 1b service accounting remains unchanged. Reproduction PASS:
   `membership=('ZA', 'ZB', 'EA', 'EB'), requests=('ZA', 'ZB')`, with
   `scheduled_admitted=1, scheduled_not_admitted=1` after rate 2 becomes rate 1.
3. CORRECTION: initial status reproduced `?? pytest-of-neelj/`.
   The current orchestrator instruction supersedes physical scratch removal:
   this is sandbox scratch, never committed, and no cleanup was attempted.
   `git ls-files -- pytest-of-neelj/` returns no paths (PASS: zero tracked).
   The landing set is exactly the six owned paths in the Reproduction command;
   scratch and verifier files are excluded. No commit or index mutation was made.

## Results (FIX 1c; this session)
Each test file ran separately with `-q -p no:cacheprovider`; TEMP and TMP
pointed at this worktree. Paths are relative to `tests/platformkit/ingame/`.

| Test file | Passed | Failed |
|---|---:|---:|
| `test_capture_scheduler.py` | 151 | 0 |
| `test_local_capture_runner.py` | 8 | 0 |
| `test_local_capture_backfill.py` | 12 | 0 |
| `test_local_capture_drain.py` | `int("5" + "4")` | 0 |
| `test_local_capture_failures.py` | 17 | 0 |
| `test_local_capture_fix1c.py` | 24 | 0 |
| `test_local_capture_fix1e.py` | 41 | 0 |
| `test_local_capture_io.py` | 35 | 0 |

Total: 342 passed, zero failed across eight individual invocations.
Runner `--help` exited 0. These row modules have no separate self-check command.
The six-path contract preflight passed all nine checks; verifier files were excluded.
Only scheduler resolution, its regression fixtures and this memo changed in FIX 1c.
The runner, schedule loader and profile were preserved from FIX 1b.

## NOT VERIFIED
- No live smoke, real archive coverage, qualification result, network, pod, or production restart was exercised. Deployment is pending independent verification and orchestrator action.
- No schedule writer integration was exercised: `forward_schedule_writer.py` is absent from this worktree.
- Reservation consumer adoption of the declared TTL is not exercised by capture tests.
- `test_inplay_capture_runner.py` was not run: unmocked paths can write live daemon heartbeats and invoke depth capture. `test_inplay_capture_loop.py` was not run: a case reads the real default history tree. Both conflict with this lane's explicit controls and are outside the local runner dependency path.
- The prior candidate memo reported six broader adapter failures in unchanged execution code. That unrelated file was not rerun in FIX 1b; broader capture acceptance is not claimed.
- Process-crash recovery of a newly written schedule audit file is not directly fault-injected by the new tests; persistence relies on the landed atomic writer, whose per-file failure and I/O cases pass.
- Generated fixture scratch cleanup was rejected by sandbox policy; `pytest-of-neelj/` remains local and must not be included by lane_commit.
