# S481 WNBA registration - 2026-09-28

Candidate: PASS, 15/15 enumerated CONSTRUCT cases. Independent verification pending.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h133; fixture transports only.
No scoring, production archive, network, pod, relaunch or schedule deployment was performed.

## Binding before-condition
Observed before implementation in this session:
```text
SPORTS_AVAILABLE = ['mlb', 'nba', 'soccer', 'tennis', 'nfl', 'ncaaf'] POLLERS has wnba: False
--sports wnba -> SystemExit(2)
fetch_schedule wnba -> KeyError 'wnba'
build_schedule wnba -> ValueError invalid_sports
ALIASES keys = ['mlb', 'nba', 'soccer', 'tennis', 'nfl', 'ncaaf']
segment(wnba) -> regulation_unavailable
qualification [NFL] -> ['maker_forward_nfl']
qualification [NFL, WNBA] -> undeclared_sport
```

## Cases
| Case | Assertion | Result |
|---|---|---|
| 1 | Surfaces plus exactly WNBA; CLI acceptance | PASS |
| 2 | Every clock contract row direct and through poller | PASS |
| 3 | Four unmodified real finals archived; zero of ten enrichment fields present | PASS |
| 4 | Two real pregame states; unavailable minute-precision starts | PASS |
| 5 | Live statuses, isolated malformed period, duplicate enrichment refusal in both orders | PASS |
| 6 | Cold scheduled discovery; four focus snapshots and two rotating bulk rows per later tick | PASS |
| 7 | Legacy first tick eight books; next three ticks no requests | PASS |
| 8 | Live-first admission and paired capacity at three rates, both orders | PASS |
| 9 | Twelve sticky starvation ticks then admission after closure, both orders | PASS |
| 10 | Real ESPN route and two minute-precision normalizations | PASS |
| 11 | UTC day links, declared-zone refusals, prior US listing, derivative refusal | PASS |
| 12 | Two aliases, thirteen shared codes, all eight real ticker identities | PASS |
| 13 | Real producers to fresh writer and strict reader; minus one microsecond refuses two rows | PASS |
| 14 | Pinned NBA/soccer outputs; NBA state and both books modes archive/heartbeat bytes; mutant killed | PASS |
| 15 | Pinned NBA/NFL schedule bytes, other aliases, WNBA HTTP 403 isolation | PASS |

## Per-file reproduction
Each invocation: python -m pytest PATH -q -p no:cacheprovider.
| File | Passed |
|---|---|
| tests/platformkit/ingame/test_wnba_registration.py | 45 |
| tests/platformkit/ingame/test_wnba_registration_books.py | 4 |
| tests/platformkit/ingame/test_wnba_registration_e2e.py | 12 |
| tests/platformkit/ingame/test_local_state_capture.py | 19 |
| tests/platformkit/ingame/test_state_capture_sources.py | 240 |
| tests/platformkit/ingame/test_state_capture_io.py | 198 |
| tests/platformkit/ingame/test_local_state_capture_schedule.py | 367 |
| tests/platformkit/ingame/test_nba_state_enrichment_archive.py | 10 |
| tests/platformkit/ingame/test_capture_scheduler.py | 151 |
| tests/platformkit/ingame/test_local_capture_runner.py | 8 |
| tests/platformkit/ingame/test_local_capture_runner_wnba.py | 6 |
| tests/platformkit/test_kalshi_book_capture.py | 13 |
| tests/platformkit/execution/test_forward_schedule_sources.py | 63 |
| tests/platformkit/execution/test_forward_schedule_dates.py | 87 |
| tests/platformkit/execution/test_forward_schedule_writer.py | 45 |
| tests/platformkit/execution/test_forward_schedule_local_date.py | fifty-four |
| tests/platformkit/execution/test_forward_schedule_local_date_e2e.py | 15 |
| tests/platformkit/execution/test_forward_schedule_team_set.py | 23 |
| tests/platformkit/execution/test_forward_schedule_utc_day.py | 20 |
| tests/platformkit/ops/test_capture_deploy_preflight.py | 50 |
| tests/platformkit/test_loc_rail_scope.py | 1 |

CLI --help PASS: local_state_capture, local_capture_runner, forward_schedule_writer and s481_memo_facts. Contract preflight: nine checks PASS.
Power check: in-memory NBA clock mutation was detected by archived-byte comparison (case 14).

## Identity and A9 sources (LF-normalized bytes; resolution n/a for code and JSON)
Pinned base commit: c8208c9a6942de1df8f76385aef99a5696ff93b3. Candidate dispatch parent: b091d9b901b90b5fa910172208c6788211268c1b.
Candidate commit: NOT CREATED (sandbox). Candidate content hashes below identify the uncommitted files.
| Source | Candidate bytes | Base SHA-256 | Candidate SHA-256 | Comparison |
|---|---|---|---|---|
| C:/Users/neelj/nba-harness-h133/scripts/platformkit/ingame/local_state_capture_sources.py | 20773 | c17bbb2e1f27c7f1ce09c97da6e954e7c93cea11e51448cff511b00978b83716 | 42d928f76750d22b9ed6ac4e58f3886fe233b10557fb0a205d69b3ac5ebedbce | NOT EQUAL |
| C:/Users/neelj/nba-harness-h133/scripts/platformkit/execution/forward_schedule_sources.py | 11059 | 67905eb0a17dbc014100811d0caee379f8953d4710c0853597504620b710acb6 | a8ad794a9a09239c7f0b84e77596fd4970d7ca2abdd2794a8a9ffb2452000844 | NOT EQUAL |
| C:/Users/neelj/nba-harness-h133/scripts/platformkit/execution/forward_schedule_writer.py | 15776 | a9bdd7f82c3e61dbde1051e7ccc82ba0a921dfc3653540a1766c5f442ac8dfc5 | 0c2a9318fc6436d5bd605fd34a963ab7a57cb1034f438cd42bedc24d5eb12ee0 | NOT EQUAL |
| C:/Users/neelj/nba-harness-h133/scripts/platformkit/ingame/game_market_link.py | 9248 | ae3a396b681024aa75bdeac46c7704531dba4d0dfc44fc524d8d688d477f8eae | 133fa3c8cdfb912d5103abdf69f9b7492523980ae2a8aadc548a75f0b6944deb | NOT EQUAL |
| C:/Users/neelj/nba-harness-h133/scripts/platformkit/ingame/wnba_state.py | 1729 | ABSENT | 57445a5cf35a249fd72058ade5a01b1224b14e61bf2a76fcf0c8997443ddd90f | NOT EQUAL |
| C:/Users/neelj/nba-harness-h133/scripts/platformkit/ops/probes/s481_memo_facts.py | 11845 | ABSENT | b7c6ad25b8382908b499be94d05634e712518025c714f79fc70646f7eef23fdc | NOT EQUAL |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/test_wnba_registration.py | 13056 | ABSENT | 490adf2f86c69b8b9023e010bb95d19d3119d177c5745433a55b0c737b04f2a2 | NOT EQUAL |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/test_wnba_registration_books.py | 8886 | ABSENT | f3a66864b5cc3d30e1c29d1abdf2034da4fa3db110644418456879a3f5081f59 | NOT EQUAL |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/test_wnba_registration_e2e.py | 12382 | ABSENT | 9165343068b211531d26083e36b1fda9c9231fb8770c0958f54e7a1cd8d061a1 | NOT EQUAL |

| Full fixture path | LF bytes | Resolution | SHA-256 |
|---|---|---|---|
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_kalshi_kxwnbagame_open.json | 18738 | n/a (JSON) | f17019055f9af5b231ef2b2222e1277e09ccf8082e1dd6cc99193e4604458924 |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_espn_wnba_20260927.json | 101269 | n/a (JSON) | 7f7185cd8c8227ecfea15fed96f2a6925e26ea5bbdec4b6236bb54dcf3422c88 |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_espn_wnba_20260928.json | 3630 | n/a (JSON) | 8218053a18e31aa270ab47d1a28f4ebc56c243566696929be0574fcb813b2bfc |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_espn_wnba_20260929.json | 43942 | n/a (JSON) | dca1941f9de5543f909f8ad7f25110fb680b0edea4ff1a57b1ac635419d3c58e |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_espn_wnba_20260930.json | 44326 | n/a (JSON) | 8f6f9a8db4fe52a0ae9ccd80848df2cdff1be564d7eadc73ba41f517e90b0b60 |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_espn_nba_20261019.json | 4389 | n/a (JSON) | 103c4d16597e9fb28b560143ea88aa720f03d0982f7c723bc4370eaf408f4f35 |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_espn_nba_20261020.json | 39884 | n/a (JSON) | 7f6c045bd843413b63d2c36a036b635dc3f718cb648bd301a587e3aa5eb16cf1 |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_espn_nba_20261021.json | 120042 | n/a (JSON) | 91858dca307e6db0149d2f39dd635aea9f1a4b1ba5156626698f39193e09e73e |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/ingame/fixtures/s481_books_nba_2026-09-21_lines1-6.jsonl | 12665 | n/a (JSON) | a4275f17b63c9c1e84ad604b1510f4a039e94ba43aff01c096134e345aa6cdf2 |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/execution/fixtures/s477_books_nfl_2026-09-28_lines1-2.jsonl | 10721 | n/a (JSON) | e41812fe72a32a6c3f90587d189c89c2dd3f5bf83b29843158045e2b3ecb565f |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/execution/fixtures/s477_espn_nfl_20260928.json | 23204 | n/a (JSON) | 98ba725daf5f6e9048d141a0fa0da927dfefb1f8ff84e14abc214489f84f3919 |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/execution/fixtures/s477_espn_nfl_20260929.json | 5193 | n/a (JSON) | d32bdedc9f799a39a5728d8bd0c52d81096c889f596fde3cdd8b5d43bf46a8c5 |
| C:/Users/neelj/nba-harness-h133/tests/platformkit/execution/fixtures/s477_state_nfl_2026-09-28_line16.jsonl | 1036 | n/a (JSON) | 5e30e3e431445a7e4c9c4c9accbd20ad5bb6ea1ed3ad8cee5eb99f212fe80898 |

Existing attributes pattern: tests/platformkit/ingame/fixtures/s481_* text eol=lf. No new fixture or seal paths.

## Read-before-build signatures
`_espn_scoreboard_states(get: GetFn, sport: str, site_path: str, date_iso: str, on_error=None) -> List[dict]` (local_state_capture_sources.py).
`parse_scoreboard(payload: Optional[Dict[str, Any]]) -> List[GameState]`; `enrich_nba_event(event: dict, response_end_utc: Optional[str]) -> dict`; `refuse_duplicate_enrichments(rows: List[dict]) -> List[dict]` (domains/basketball_nba/live_state_nba.py).
`fetch_schedule(sport: str, day: str, counts: Counter, opener: Callable | None = None) -> tuple[list[dict], dict]` (forward_schedule_sources.py).
`build_schedule(day: str, sports: list[str], books_root: Path, state_root: Path, family: str, now: str | None = None, *, schedule_source: str = 'live', opener: Callable | None = None, utc_day: bool = False, local_date_tz: str | None = None) -> tuple[list[dict], dict]` (forward_schedule_writer.py).
`alias(sport: str, abbr: Optional[str]) -> Optional[str]`; `team_code_from_ticker(ticker: str) -> Optional[str]` (game_market_link.py).
`plan_tick(now, rate_per_sec, markets, focus_state, params) -> TickPlan`; `schedule_rows(rows: list, now, errors: Counter) -> list`; `timestamp(value: object) -> Decimal` (capture_scheduler.py).
`capture_state_once(*, client: StateClient | None = None, sports: list[str] | None = None, now: datetime | None = None, state: dict | None = None, clock: Callable = time.monotonic, output_root: Path | None = None, writer: StateWriter | None = None, mlb_live: bool = False, nba_pbp_player: bool = False) -> dict`; `_main(argv: list[str] | None = None) -> dict` (local_state_capture.py); `make_client(responses, clock=None)` (test_local_state_capture.py).
`capture_once(*, client=None, sports=None, now=None, state=None, clock: Callable = time.monotonic, output_root=None, _writer=None, scheduler_enabled=False, schedule=None, schedule_pointer=None) -> dict` (local_capture_runner.py); `GovernedClient.__init__(self, session=None, sleep_fn=time.sleep, max_retries: int = 5, utc_clock=utcnow, clock=time.monotonic, metrics=None) -> None` (local_capture_client.py).

## Disclosures
Adoption needs owner-visible books (S486) and state2 relaunches, adding wnba to state2's explicit --sports.
D_ingame_wnba.json is evidence-only unless explicitly connected to the books --schedule at startup and unioned with pointer rows. Qualification remains WNBA-free.
Scheduler focus is live-first, earliest expiration, sticky and capacity-limited: four tickers at rate 2.0 and six at 3.0. Five-second coverage depends on contention. Sixty-second pregame cadence until tip plus fifty minutes belongs only to --no-scheduler.
NBA retains colon-less clock None and its landed OT elapsed 55.0 versus 48.0 at OT start. Missing scores remain zero for both leagues; ESPN minute-precision state starts remain None.
The nba_adapter_empty counter name is reused under source wnba. A conflicting declared-zone date can only refuse. Completion covers capture and prospective selection, not model readiness.
WNBA alone preserves the raw period type before clock validation; the shared parser otherwise coerces it. No existing NBA calculation changes. Thirty-nine protected modules and families_maker_forward.json matched the pinned dispatch parent (LF-normalized); local_capture_runner.py was not edited.

## NOT VERIFIED
ESPN WNBA in-progress shape and enrichment; live WNBA books; semifinal/final ticker naming; sixth-sport request load. Production receipt cadence, latency, deployment and scorer readiness were not exercised.
