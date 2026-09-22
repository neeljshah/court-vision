# S386 prospective schedule writer

PREPARE candidate, FIX 1f. Local machine:
`C:/Users/neelj/nba-harness-h46`. Specification read directly with
`git show master:docs/evidence/tracking/specs/S386_spec.md`, including all six
amendments. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, B and Q.
The pod is OFF. This memo makes no sampled or scored claim.

## Premise and correction

The original uncommitted candidate was present at FIX 1b start. Its reader used
only archived scheduled_start_utc. AMENDMENT 2 reports the orchestrator's
484 invalid_time refusals; this lane did not repeat that real archive run.
The archive lacks that field today. Earlier candidate prose asserting that
all persisted state rows carried scheduled_start_utc was incorrect.
The landed Qualification constructor compared selected_at > scheduled_start;
inspection confirmed equality could pass. AMENDMENT 1 authorizes its correction.

## Landed interfaces and exact sources

Source files read locally; byte sizes below describe this checkout, not a
provider response. Video resolution is not applicable.

| Input path | Bytes |
| --- | ---: |
| scripts/platformkit/ingame/local_state_capture_sources.py | 12869 |
| scripts/platformkit/ingame/local_state_capture_dates.py | 5517 |
| scripts/platformkit/ingame/game_market_link.py | 9410 |
| scripts/platformkit/ingame/local_capture_runner_trades.py | 5327 |
| scripts/platformkit/execution/forward_replay.py | 15291 |
| scripts/platformkit/execution/forward_replay_io.py | 6486 |
| scripts/platformkit/execution/venue_time.py | 2029 |
| scripts/platformkit/frontend/live_board.py | 20150 |

The spec-named interfaces were also inspected with git show master.
Exact signatures from `scripts/platformkit/ingame/game_market_link.py`:

```python
def alias(sport: str, abbr: Optional[str]) -> Optional[str]:
def team_code_from_ticker(ticker: str) -> Optional[str]:
def index_kalshi_events(rows: List[Dict[str, Any]], metrics: Optional[Metrics] = None,
                        source: str = "linker") -> Dict[str, Dict[str, Any]]:
def link_game(sport: str, date_iso: Optional[str], home_abbr: Optional[str], away_abbr: Optional[str],
              kalshi_index: Dict[str, Dict[str, Any]], scheduled_start_utc: Optional[str] = None,
              metrics: Optional[Metrics] = None, source: str = "linker") -> LinkResult:
def load_kalshi_rows(sport: str, date_iso: str, root: Optional[Path] = None,
                     metrics: Optional[Metrics] = None, source: str = "linker") -> List[Dict[str, Any]]:
```

The loader was inspected but is not called: the writer scans all capture shards,
filters receipt time before schema checks, and preserves decimal JSON tokens.
`venue_time.py`: `def parse_venue_time(value: object) -> float | None:`.
All timestamp parsing passes through that parser. Exact ISO fractional tails
are retained as Decimal after validating and parsing whole seconds through it.
Live conversion uses landed local_state_capture_dates.schedule, which follows
the same parser and emits UTC while retaining a proven local date separately.

`forward_replay.py`: `def main(argv: list[str] | None = None) -> int:` loads
`schedule=json.loads(args.schedule.read_text(encoding="ascii"))`.
The imported reader, Qualification, has
`def __init__(self, schedule: list, as_of: object):`.
It consumes game_id, ticker, sport, family, scheduled_start, selected_at and
refuses duplicate game IDs/tickers. The writer's game_id is event_ticker,
consistent with forward_replay_io.identity.

`local_capture_runner_trades.py`:
`def classify_state(market: dict, sport: str, now, errors=None) -> tuple[str, float]:`
uses expected_expiration_time before close_time, then subtracts typical duration.
That heuristic is not a source of scheduled starts.

Exact templates quoted from `local_state_capture_sources.py`:

```text
MLB_SCHEDULE_URL = https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}
ESPN_SCOREBOARD_URL = https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard
TENNIS_SCOREBOARD_URL = https://site.api.espn.com/apis/site/v2/sports/tennis/{league}/scoreboard?dates={date}
```

`def mlb_discover(get: GetFn, date_iso: str) -> List[Dict[str, Any]]:` traverses
`dates[].games[]`: gameDate is the start, gamePk becomes string game_key;
officialDate or dates[].date proves the local date. Directional team fields are
`teams.home.team.abbreviation` and `teams.away.team.abbreviation`.
`def _nfl_league_poll(get: GetFn, date_iso: str, league: str, on_error=None) -> List[Dict[str, Any]]:`
reads the entire `events[]` week. Paths: football/nfl and football/college-football.
NBA: basketball/nba; soccer: soccer/eng.1 (from live_board._ESPN_ROUTES).
ESPN events[].date supplies start; competitions[].id supplies provider game_key;
competitors[].homeAway and team.abbreviation prove direction. Missing local
date or team metadata can be filled from the exact archived game_key, never
from ticker suffixes. Missing or invalid live start is always a counted refusal.
Tennis uses events[].groupings[].competitions[], competition date when present,
and the capture conventions atp:<competition id> and wta:<competition id>.
Amendment 6 authorizes the writer to poll ATP and WTA separately, retaining
both receipts. Live completeness remains unverified.

## FIX 1b

Added --schedule-source live|archive, default live. New helper
`scripts/platformkit/execution/forward_schedule_sources.py` supplies schedule
rows through an injected opener. Production uses urllib's default headers and
one request per sport per run, without retries. Books remain archive-only.
Archive mode retains its original selection behavior for S393.

Each sport's schedule_receipt contains URL, timezone-aware request_start_utc and
response_end_utc, http_status, response_sha256, response_bytes. Hash and length
cover the exact received bytes, before JSON parsing. No response means a null
hash and zero received bytes; schedule_network_failure counts the failure per
sport. Malformed payloads and candidate parse errors have explicit counters.
Receipts and raw-response hashes naturally differ for differently ordered
response bytes; selected entries and all diagnostic counts are order independent.

The census reports strict-int games_seen, linked, written, refused_by_reason,
record_counts and canonical_rules. Every observed candidate is written or
refused once. Duplicate live provider identities refuse all copies. The archived
reader retains its latest-receipt and equal-receipt refusal behavior. An invalid
book side blocks the event; no alternate side conceals its refusal.
Home alias is canonical; lexical minimum is the explicit fallback.

AMENDMENT 1 changes only the selection boundary in qualification: >= refuses.
Its ValueError retains the existing message and carries strict-int reason_counts
with nonprospective_or_duplicate_selection=1. Equality refusal and acceptance
one microsecond before start are explicitly tested. The two landed S362 test
helpers now select before start; their other assertions and frozen bars remain.
An initial replay test exposed decimal-context sensitivity in a new fixture
calculation; a fixed prospective literal corrected the fixture.

New test module: tests/platformkit/execution/test_forward_schedule_sources.py.
All network tests use injected in-memory openers. Constructs cover both payload
shapes, all six sport routes, receipts/hash/bytes, failures, UTC filtering,
missing times, week ordering, duplicate identities, exact archive metadata
fallback, and strict status/count handling. Original writer tests remain.
No real archive was opened and no public request was made by this lane.

## FIX 1c

AMENDMENT 3 supplies the second live run's zero written entries: MLB 16 games,
10 missing_directional_team_evidence and 6 outside_utc_date; NFL 16 invalid_time.
This lane did not repeat that real run. Inspection confirmed the candidate URL
omitted hydration and passed ESPN minute-precision dates to the strict parser.

The MLB request now appends &hydrate=team. The provider's abbreviation follows
the existing landed alias/link path; no team is inferred from an id or name.
Constructs cover hydrated SF/SFG and TB/TAM with NYY, absent abbreviations,
and an unresolved abbreviation. Missing or unresolved evidence stays counted.

Only the selected ESPN date field with exact ASCII YYYY-MM-DDTHH:MMZ shape
receives :00 seconds before the landed schedule reader and shared parser.
The strict-int record_counts.espn_minute_precision_normalized counter records
each normalization, including a shape-correct value that fails calendar validation.
Other shapes, startDate fields, and MLB gameDate values are unchanged.
The source payload is not mutated. Order tests include normalized dates and
duplicate games; receipts retain their byte-order-specific hash and timestamps.

The UTC filter is unchanged. A construct verifies next-UTC-day MLB starts are
refused as outside_utc_date, and the runbook explains this daily boundary.
All constructs use synthetic payloads and injected openers; no network is used.
An initial test used TBR for the book code; the landed table maps TB to TAM.
The fixture was corrected to that existing table; production aliases are unchanged.

## FIX 1d

AMENDMENT 4 reports the third real run still refused 10 of 16 MLB games as
missing_directional_team_evidence. Local inspection confirmed that the landed
index retains unordered team_codes for capture rows without home_abbr/away_abbr.
The writer formerly passed that index only to the directional linker. The
orchestrator's real run was not repeated here; game_market_link.py is unchanged.

The writer still tries the landed linker first. A missing-direction refusal can
now use the venue schedule's home/away abbreviations through the landed alias
table. The fallback requires exactly those two codes and the ticker's local
date equal to the game's local date. A UTC date or capture date cannot substitute.
Multiple exact sets on that date refuse as ambiguous_doubleheader, even if one
has directional metadata. Embedded ticker times never resolve an ambiguity.
Conflicting or reversed book metadata cannot be bypassed by this fallback.
Canonical home_alias and lexical_fallback behavior remains; no start is inferred.

The additive census link_paths maps each successfully linked provider game_key
to linker or team_set, before duplicate output refusal. Count fields remain
strict integers; the schedule's six-field shape is unchanged. Every implementation
except clause increments a named counter; uncaught exceptions propagate.

The new test file tests/platformkit/execution/test_forward_schedule_team_set.py
contains the four requested test families, n = 17 (CONSTRUCT): venue direction
and aliases (2), doubleheaders with zero/one/two directional events (3), exact-set
and local-date mismatches or missing teams (8), and linker preference plus
partial/reversed/conflicting direction (4). All cases reverse capture order;
the success cases also reverse schedule order. Network calls are blocked and
provider payloads are injected in memory. Two initial assertions expected UTC
text without fractional seconds; corrected expectations match the landed parser.

## FIX 1e

AMENDMENT 5 reports one written game, five ambiguous_doubleheader refusals,
and four missing_directional_team_evidence refusals in the fourth real run.
Inspection confirmed the candidate indexed all series before either link path.
The orchestrator's real archive run was not repeated by this lane.

Landed winner entries quoted from master kalshi_series_scope.SERIES_BY_SPORT:
mlb: KXMLBGAME; nba: KXNBAGAME;
soccer: KXEPLGAME, KXBUNDESLIGAGAME, KXLALIGAGAME, KXSERIEAGAME,
KXLIGUE1GAME, KXUCLGAME;
tennis: KXATPMATCH, KXATPCHALLENGERMATCH, KXWTAMATCH.
That scope also lists wnba: KXWNBAGAME; ncaab: KXNCAAMBGAME, KXNCAABBGAME,
outside the writer's supported sports. local_capture_runner.SERIES_BY_SPORT
adds nfl: KXNFLGAME alongside its spread series. There is no NCAAF entry.
Contrary to the spec's shorthand, classify_state has no winner predicate;
it selects capture cadence using timestamps. The list above comes from scope
and the runner, read with git show master, never inferred from event team codes.
Additional local input paths: scripts/platformkit/ingame/kalshi_series_scope.py
(9326 bytes), scripts/platformkit/ingame/local_capture_runner.py (17286 bytes).

Exact winner-series prefixes now filter latest market tickers before indexing,
so both linkage paths and the doubleheader check share the restricted index.
record_counts.derivative_series_ignored counts excluded latest tickers, not
events or historical snapshots: both sides of one derivative count as two.
Unknown and wrong-sport prefixes also stay excluded and counted; no NCAAF
series is guessed. Two actual winner events still refuse as doubleheaders.
refused_team_evidence maps each missing_directional_team_evidence game_key
to its venue home_abbr/away_abbr, sorted venue_team_codes through existing
aliases, and compared_team_code_sets by same-local-date winner event.
Only supplied abbreviations and observed codes are listed, without alias edits.
Six added CONSTRUCT cases cover derivative-plus-winner on both link paths,
two refused games' exact census listings, and three non-winner-only refusals.
The census construct reverses both archive and schedule order and checks JSON
serialization. A bounded independent code review found no blocking findings.

## FIX 1f

Binding inputs: `_verdict_s386_1f.md` and all six amendments read with
`git show master:docs/evidence/tracking/specs/S386_spec.md`. The local spec
still lacks amendments; it was not edited. Reproductions ran locally with
constructed bytes, injected clocks/openers, and temporary synthetic archives.

1. BLOCKING: live selection preceded receipt. Before output:
   `INPUT start=12:00:01Z response_end=12:00:02Z`
   `OUTPUT selected_at=2026-09-21T12:00:00+00:00; written=1`.
   The writer now fetches ALL sports/tours before stamping default selected_at.
   Explicit --now rejects each later response with record_counts and each
   affected candidate with refused_by_reason.schedule_response_after_cutoff.
   Archive reads and start comparisons use the resulting cutoff. After:
   `OUTPUT []; refused_by_reason={'not_prospective': 1}`.
2. BLOCKING: directional linker accepted an incomplete event. Before output:
   `INPUT team_codes=('SFG',); venue=('SFG','NYY')`
   `OUTPUT ticker=KXMLBGAME-26SEP21NYYSFG-SFG; link_paths={'123':'linker'}`.
   Missing, extra and wrong sets all reproduced acceptance. Both link paths
   now check the selected winner event's exact alias set before choosing a
   ticker. After: `OUTPUT []; team_code_set_mismatch=1`, with the compared
   set in refused_team_evidence. Reversed capture order gives identical counts.
3. BLOCKING: tennis omitted WTA. Exact before output:
   `OUTPUT URL .../tennis/atp/scoreboard?dates=20260921; keys=['atp:w1']`
   `Counter({'unqueried_wta_schedule': 1})`.
   Amendment 6(c) supersedes the one-request limit: two requests now enumerate
   both tours, with tour-qualified keys and both receipts under tour_receipts.
   After: `keys=['atp:w1', 'wta:w1']; requests=2; counts={}`.

The new test_forward_schedule_fix1f.py initially reported 5 failed: one timing,
three directional sets, one tennis enumeration. It now covers those findings,
receipt equality and nanosecond cutoffs, fetching all sports before stamping,
as-of archive metadata, tour failures, and independent late-tour refusal.
A first post-fix order assertion compared different request-start clocks;
resetting the injected clock made the intended identical-input comparison.
Legacy successful fixtures now supply both team codes and freeze receipt time.
The retained lexical fallback branch uses an injected LinkResult and an exact
index; a real exact two-team index always contains the home code.
The landed linker, replay implementation, and prior qualification fix are intact.
A read-only code review found no blocking issue in the Amendment 6 changes.

## Reproduction

Total: 272 passed. Commands ran locally; TEMP/TMP point inside this worktree;
PYTHONDONTWRITEBYTECODE=1. Each test command runs ONE file:
`python -m pytest tests/platformkit/execution/<file> -q -p no:cacheprovider`.

| Test file | FIX 1f passed |
| --- | ---: |
| test_forward_schedule_fix1f.py | 13 |
| test_forward_schedule_writer.py | 45 |
| test_forward_schedule_sources.py | 63 |
| test_forward_schedule_team_set.py | 23 |
| test_forward_replay.py | 49 |
| test_forward_replay_qualification.py | 79 |

`python -m scripts.platformkit.execution.forward_schedule_writer --help`:
1 passed (exit 0). No separate self-check option exists. Preflight: 9 passed, zero FAIL.
The preflight --paths list includes all eleven candidate files (the two
schedule modules, qualification, six tests, runbook and this memo), excludes
_verdict_s386_1f.md, and uses --base master --spec
`docs/evidence/tracking/specs/S386_spec.md`. All files must remain ASCII and
at most 300 physical lines: 11 of 11 passed. Git diff --check: 1 passed.
SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED

- Live provider availability, completeness, WTA coverage, or real archive yield.
- The orchestrator's 484-game measurement was supplied, not reproduced here.
- The second live run's MLB/NFL counts were supplied, not reproduced here.
- The third live run's MLB counts were supplied, not reproduced here.
- The fourth live run's game counts and unresolved codes were not reproduced here.
- A live qualifying game, a prospective production schedule, or a commit before start.
- Pod execution, deployment, full test tree, concurrent writers, or physical crash recovery.
- Independent verifier acceptance and lane_commit have not occurred.
