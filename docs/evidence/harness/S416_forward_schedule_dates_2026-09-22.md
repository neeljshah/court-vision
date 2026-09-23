# S416 forward schedule dates -- PREPARE construct evidence

Authority: docs/evidence/tracking/specs/S416_spec.md, including AMENDMENTS 1-6.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B, Q.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h69; offline constructs only.
Interpreter actually run: Python 3.10.0. No interpreter replacement or installation.
Starting HEAD and master: e65683a7d1a756a268a0fe3f7e70011045c1fd8f.
Initial git status was empty. No commits, network requests, or real enumeration.

## Binding before-condition quotes at starting master

- scripts/platformkit/execution/forward_schedule_sources.py:17:
  `MLB_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=team"`
- scripts/platformkit/execution/forward_schedule_sources.py:18:
  `ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"`
- scripts/platformkit/execution/forward_schedule_sources.py:19:
  `TENNIS_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/{league}/scoreboard?dates={date}"`
- scripts/platformkit/execution/forward_schedule_sources.py:20-21:
  `ROUTES = {"nfl": "football/nfl", "ncaaf": "football/college-football",`
  `          "nba": "basketball/nba", "soccer": "soccer/eng.1"}`
- scripts/platformkit/execution/forward_schedule_sources.py:112-116, verbatim:

```python
def _fetch_schedule(sport: str, day: str, counts: Counter,
                    opener: Callable | None, tour: str | None = None) -> tuple[list[dict], dict]:
    url = (MLB_URL.format(date=day) if sport == "mlb" else
           TENNIS_URL.format(league=tour, date=day.replace("-", "")) if sport == "tennis" else
           ESPN_URL.format(path=ROUTES[sport]))
```

- scripts/platformkit/execution/forward_schedule_sources.py:100-110:
  `def fetch_schedule(sport: str, day: str, counts: Counter,`
  `for tour in ("atp", "wta"):`; `games.extend(rows)`;
  `return games, {"tour_receipts": receipts}`. Both tour receipts are preserved.
- scripts/platformkit/execution/forward_schedule_sources.py:69:
  `key = comp.get("id") if sport == "tennis" else raw.get("id")`.
  At :91: `pre = status.get("state") == "pre" or status.get("name") == "STATUS_SCHEDULED"`.
  At :96-97: `away_abbr=away, status="pre" if pre else "not_pre",`
  `**schedule(event, metrics, sport))`.
- scripts/platformkit/ingame/local_state_capture_dates.py:99-100:
  `result = {"date": None, "scheduled_start_utc": encoded,`
  `          "date_reason": "missing_scheduled_time"}`.
- scripts/platformkit/execution/forward_schedule_writer.py:25-31:
  `WINNER_SERIES = {` and `"ncaaf": (),  # No landed capture series; never infer one.`
  At :282-290: `parser.add_argument("--date", required=True)`;
  `parser.add_argument("--sports", required=True, help="Comma-separated captured sports")`;
  `parser.add_argument("--schedule-source", choices=("live", "archive"), default="live")`.
- scripts/platformkit/execution/forward_replay_qualification.py:21:
  `WEEK_GAMES, SPORT_GAMES, FILL_GAMES = 4, 30, 30`.
- scripts/platformkit/execution/family_week_ledger.py:18: `TARGET_WEEKS = 8`.
- tests/platformkit/execution/test_forward_schedule_sources.py:86 BEFORE:
  `assert calls == [sources.ESPN_URL.format(path=sources.ROUTES[sport])]`
  AFTER, same line:
  `assert calls == [sources.ESPN_URL.format(path=sources.ROUTES[sport], date=DAY.replace("-", ""))]`
- data/nfl/schedules.parquet is not opened by this lane. Amendment 1 supplies (h):
  docs/evidence/tracking/specs/S416_spec.md:63-69 quotes "7,548 rows", the 40 named
  columns, "gameday is text from 1999-09-12 to 2027-01-10", "season int32 1999..2026",
  "week int32 1..22", and "espn is present". The original (h) at :21-22 states
  "season 2026 game_type REG = 272 rows, gameday 2026-09-09 .. 2027-01-10".
  These are orchestrator facts, not a lane measurement. The test writes only tmp_path parquet.

House style and recorded shapes: tests/platformkit/execution/test_forward_schedule_sources.py:21-46
uses an autouse network block, injected BytesIO opener, and event/competition ESPN dictionaries.
test_forward_schedule_game_key.py:18-24 distinguishes event identity from competition identity.
The four protected tests have no ESPN query assertion; fix1f checks tour path fragments only.

## Original built files and schema (later amendments below)

- scripts/platformkit/execution/forward_schedule_sources.py:18,116 changes only the ESPN
  date template and interpolation. All other code, receipt fields and signatures are unchanged.
- scripts/platformkit/execution/forward_schedule_supply.py:40 localizes Eastern wall times,
  round-trips ambiguous/nonexistent times, renders explicit UTC offsets, then uses parse_venue_time.
  It reads only REG NFL rows offline and requires --as-of for every sport's status.
  FIX 1b below supersedes the original one-request-per-day ESPN enumeration.
- tests/platformkit/execution/test_forward_schedule_sources.py:86 is the only changed assertion.
- tests/platformkit/execution/test_forward_schedule_dates.py:65-232 covers URLs, every specified
  refusal, three weeks, order independence, imported constant identity, NFL parquet, DST and CLI.
- tests/platformkit/execution/fixtures/s416_espn_scoreboard.json:1 is an 18-line, 423-byte
  constructed recorded-shape ESPN payload; no live event truth is asserted.
- tests/platformkit/execution/fixtures/s416_nfl_rows.json:1 is an 8-line, 1012-byte six-row
  NFL construct. The test expands it to the 40 named columns, with season/week int32,
  named text fields object, and unused fields null. Resolution is not applicable to these inputs.

Output: notice, as_of, weeks[], sports{}, record_counts{}, unassigned_refusals{}, games[].
Each week is keyed by sport/family, iso_year, iso_week and contains scheduled, pre, not_pre,
games_pre, games_not_pre, time_unknown, status_unknown, refusals{}. Family equals sport.
pre/not_pre and games_pre/games_not_pre are aliases with identical strict-int counts.
Timed games use their UTC ISO week; untimed NFL rows use gameday. Refused rows remain in games
with _refusal. Unattributable failures stay in unassigned_refusals, never assigned an invented
game week. Day mismatches are counted in their actual UTC week, even outside the requested span.
Empty requested weeks stay visible. weeks_total counts emitted weeks for each sport;
weeks_at_or_above_week_games compares accepted scheduled counts with imported WEEK_GAMES.
Scheduled includes identifiable NFL rows with unknown time. Unknown time/status counts cover
all selected NFL rows, including missing identities; they are independent diagnostics.
Every timed accepted row's split is strictly after --as-of versus at/before (AMENDMENT 6).
All JSON is ASCII. Enumeration and output ordering are independent of supplied day order.
Notice: counts of scheduled games only; scheduled supply is not qualification.

## FIX 1b

Authority: S416_spec.md AMENDMENTS 1-6; VERIFIER_CONTRACT.md sections A, B, Q.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h69, offline constructs only.
Interpreter: Python 3.10.0, C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe.
All timestamps used for counting pass through parse_venue_time.
No installed interpreter changes, network calls, commits, or data/cache access.

AMENDMENT 6: every timed accepted row of every sport derives status solely from start_utc
versus --as-of. Strictly later means pre; equal or earlier means not_pre. Feed status is
never read for these counts. Returned accepted-row status and both count aliases agree.
Pinned test: test_every_sport_status_uses_clock covers all six sports, three feed statuses,
and instants before, exactly at, and after as-of. The boundary test also inverts feed status.

AMENDMENT 5(a): each ESPN sport (including both tennis tours) requests the UTC date and
the previous date. The additive requests[] records sport, requested_day, source_day, and
receipt (URLs, hashes, HTTP status, byte lengths or error); volatile request timestamps
are omitted to preserve deterministic results. NFL remains offline; MLB uses its dated API.
Rows matching the requested UTC day are retained from either payload. Prior-day rows are
ignored; only other UTC dates are day_mismatch. Identified repeats across the two payloads
increment record_counts[sport].event_seen_twice and never add a second scheduled game.
Same-payload duplicate_schedule_game refusals remain intact. Each failed request is counted.
Pinned test: test_espn_previous_date_boundary covers current-only absence, previous-date
recovery, duplicate delivery, prior-day noise, and all four online ESPN sport families.
test_refused_dates pins genuinely stale dates; test_network_exception_counted pins both failures.
Scheduled includes unknown-time games; weekly thresholds describe supply only, not qualification.
The fixture still yields date None / missing_local_timezone under landed writer linkage;
these constructs show inventory, not S403 schedule emission.

AMENDMENT 5(b), AMENDMENT 4 facts, verbatim counts from the orchestrator's run:
ISO weeks 40-52: 16 / 15 / 14 / 14 / 14 / 15 / 14 / 13 / 16 / 14 / 15 / 16 / 16.
week 53: 2 (December 28-31 partial); all pre; zero refusals;
as-of 2026-09-22T23:15:00Z. not_pre 0, time_unknown 0, status_unknown 0,
refusals {} in every week, unassigned_refusals none. Exit 0.
Source: orchestrator's offline enumeration over 2026-09-28 .. 2026-12-31 using the main
tree's data/nfl/schedules.parquet, as recorded in AMENDMENT 4; not re-run by this lane.
Example: gameday 2026-09-27 20:20 ET -> 2026-09-28T00:20:00Z, ISO week 40;
scheduled_start_utc 2026-09-28T00:20:00+00:00, requested_day 2026-09-28,
game_key 401872962. Pinned test: test_memo_preserves_orchestrator_counts.

Offline Python one-liner reproductions, measured before and after FIX 1b:

```text
STATUS before: [1, 0] [0, 1]
BOUNDARY before: scheduled=0; requests=20260928
MEMO before: counts=False
STATUS after: [0, 1] [1, 0]
BOUNDARY after: scheduled=1; requests=20260928,20260927
MEMO after: counts=True
```

The status reproduction injects the recorded-shape fixture through BytesIO: past start
2026-09-21T23:00:00Z with feed pre; future start 2026-09-28T00:20:00Z with feed post;
as-of 2026-09-22T23:15:00Z. Each pair is [pre, not_pre]. The boundary reproduction
requests only Monday 2026-09-28 and serves that future event only for dates=20260927.
Both are python -c one-liners executing the same source before and after the edit;
no requests leave the injected opener. The memo reproduction tests the exact count string.

FIX 1b checks (each pytest invocation names exactly one file, with -q -p no:cacheprovider):

```text
test_forward_schedule_dates.py: 60 passed in 0.80s
test_forward_schedule_sources.py: 63 passed in 0.72s
test_forward_schedule_game_key.py: 5 passed in 0.64s
test_forward_schedule_team_set.py: 23 passed in 0.69s
test_forward_schedule_fix1f.py: 13 passed in 0.55s
test_forward_schedule_writer.py: 45 passed in 1.80s
```

Initial FIX 1b run had two failures in 4.21s. Both failures were tennis constructs
missing groupings. Corrected the construct and added excluded-prior-version coverage;
the final run above passes all 60 cases. A read-only review confirmed prior-day versions
cannot suppress accepted second-payload rows; event_seen_twice counts independently.
CLI --help exits 0 and describes --as-of for every sport.
SHA-256 checks confirm the landed writer, four protected tests, sources module, and its
already-amended URL assertion test are all byte-identical to the FIX 1b starting files.
The only pre-existing tracked diff is the sources URL template/interpolation and its one
test assertion. FIX 1b changes only supply, dates tests, and this memo; fixtures are unchanged.
Contract A5: a scoped recursive reader scan of scripts/platformkit/execution and
tests/platformkit/execution found only the supply module/CLI and its owned test file.
Contract B/Q self-check: additive requests schema, unchanged thresholds, no scored claims,
no deployment, and explicit refusal counts. No external scoped reader requires migration.
An intermediate preflight rejected the memo's bare numeric initial pass count; the prose
now records the two failed tennis cases without that prohibited number.

## FIX 1c
Authority: master S416_spec.md AMENDMENTS 7-8; all prior amendments retained.
Base: orphaned HEAD 5a42c84ed; ownership uses git diff HEAD, never master.
Interpreter: Python 3.10.0, C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe.
Counting timestamps pass through parse_venue_time; date-only text proves no instant.
AMENDMENT 7: collect both payloads by id before date/status decisions; conflicting
starts emit one event_start_conflict with sorted conflicting_start_utc text, no chosen
instant and no status. Identical cross-payload copies schedule once. Same-payload
duplicate refusals remain as in FIX 1b. Tests reverse fetch order and parsed row order.
AMENDMENT 8(a): only the ESPN status extraction changes beyond the existing URL fix.
Malformed status counts feed_status_malformed and returns not_pre; real-parser tests
assert that a future event still counts scheduled=1/pre=1 through the supply clock.
AMENDMENT 8(b): every refused row has null status; a present source status is separate
feed_status text. Unparseable source starts are start_text with no fallback UTC instant.
The landed parser already collapses invalid raw date text to null; supply retains the
text it receives, tested both through the real parser and directly at the supply boundary.
Pinned tests: test_collected_before_decisions_all_orders, test_malformed_status_real_parser,
test_refused_dates, test_memo_preserves_orchestrator_counts.

Offline Python one-liner reproductions (same program before/after, injected BytesIO):
CLOCK tuples are (scheduled, pre, not_pre); WEEK tuples are (day_mismatch, weeks_total).
Both lists enumerate normal/reversed actual fetch iteration. UNTIMED tuples contain
(input, day_unverifiable, scheduled, status, feed_status, scheduled_start_utc).
The preliminary malformed probe served both dates and counted two parse failures;
the final paired probe below serves only the requested date (one event).
~~~text
CLOCK before: [(1, 0, 1), (1, 1, 0)]
CLOCK after: [(0, 0, 0), (0, 0, 0)]
WEEK before: [(1, 2), (0, 1)]
WEEK after: [(0, 1), (0, 1)]
MALFORMED before: scheduled=0 pre=0 schedule_game_parse_failure=1 feed_status_malformed=0
MALFORMED after: scheduled=1 pre=1 schedule_game_parse_failure=0 feed_status_malformed=1
UNTIMED before: [('2026-09-28', 1, 0, 'pre', None, None), (None, 1, 0, 'pre', None, None), ('bad', 1, 0, 'pre', None, None)]
UNTIMED after: [('2026-09-28', 1, 0, None, 'pre', None), (None, 1, 0, None, 'pre', None), ('bad', 1, 0, None, 'pre', None)]
~~~
Order tests enumerate all four fetch/parsed-row order combinations for two conflicting
start pairs and one identical pair. They compare full serialized ASCII JSON bytes,
including fixed receipts; raw response body hashes retain their original provenance.
Reproduction uses python -c exec(bytes.fromhex(...)) to avoid cmd.exe quoting failures,
runpy of the owned test file for fixtures/openers, and an in-memory copy of supply's
source with only fetch iteration reversed. It never writes source or opens a URL.
For each conflict, event_start_conflict=1; both start strings are retained, scheduled=0.
Final single-file runs (-q -p no:cacheprovider):
~~~text
test_forward_schedule_dates.py: 79 passed in 0.82s
test_forward_schedule_sources.py: 63 passed in 0.67s
test_forward_schedule_game_key.py: 5 passed in 0.57s
test_forward_schedule_team_set.py: 23 passed in 0.59s
test_forward_schedule_fix1f.py: 13 passed in 0.52s
test_forward_schedule_writer.py: 45 passed in 1.63s
~~~
CLI --help exits 0. SHA-256 matches the start of this turn for the writer and all five
landed test files, including the sources test with its existing URL assertion change.
No commit, live request, data/cache access or change outside the owned files.

Contract A5 reader scan: only supply/tests read the new fields; no external migration.
## FIX 1d (historical)
Authority: S416_spec.md AMENDMENT 9; AMENDMENTS 1-8 retained.
Python 3.10.0; all counting timestamps pass through parse_venue_time.
Added raw start_text before normalization; supply preserves it on untimed refused rows.
Real-parser date-only, garbage and null reproduction, in that order:
RAW_START before: ['None', 'None', 'None']
RAW_START after: ['2026-09-28', 'bad', 'None']
The prior FIX 1c statement about lost text is superseded.
Historical dates test: 79 passed in 0.86s; all five landed test files passed.
Historical CLI --help and preflight: exit 0; PASS 9, FAIL 0.
Writer and five landed tests matched their starting SHA-256 values.

## FIX 1e
Authority: S416_spec.md AMENDMENT 10; AMENDMENTS 1-9 retained.
Local Windows worktree: C:/Users/neelj/nba-harness-h74; no commit or git metadata write.
Interpreter: Python 3.10.0, C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe.
Counting timestamps still pass through parse_venue_time.
sources.py:103-104 selects the first present non-null raw start for start_text.
Empty text and whitespace survive verbatim; all absent/null yields the text "None".
The normalized-instant selection, date URL and tolerant status extraction are unchanged.
dates.py:59-78 pins empty, whitespace, null, date-only and garbage through the REAL parser.
Supply, both fixtures, the landed writer and all five landed test files are unchanged.
The starting HEAD diff already contained the sources URL/status/raw-text amendments
and the sources test's single URL assertion. That pre-existing unowned test diff remains.

REPRODUCTION: n = 3 (CONSTRUCT), empty text, whitespace, null, in that order.
Before and after used python -B -c one-liners with runpy of the dates test helpers.
payload() loads tests/platformkit/execution/fixtures/s416_espn_scoreboard.json (423 bytes).
Other start fields were asserted absent; build() injects BytesIO into the REAL parser.
Equivalent one-liner body (the measured program was hex-encoded for cmd.exe):
~~~python
import runpy; t=runpy.run_path("tests/platformkit/execution/test_forward_schedule_dates.py"); out=[]; exec("for start in ('', '   ', None):\n data=t['payload'](); data['events'][0]['date']=start; out.append(t['build'](data)['games'][0]['start_text'])"); print(out)
~~~
~~~text
EMPTY_START before: ['None', '   ', 'None']
EMPTY_START after: ['', '   ', 'None']
~~~
All three refused rows retain status null and feed_status "pre".
ROUND4: ['2026-09-28', 'bad', 'None']
MINUTE: ('2026-10-05T23:00Z', '2026-10-05T23:00:00.000000Z')
In-memory prior-parser comparison: 11/11 well-formed status variants identical;
12 raw field/value cases and empty-with-valid-fallback preserve normalized fields/counters.
The dates test retains all four conflict orders, identical copies and malformed admission.
Contract B/Q: unchanged thresholds, additive text field, no scored claims.
Contract A5: scoped start_text reader scan covers execution modules and tests.
Final single-file runs (-q -p no:cacheprovider), in requested order:
~~~text
test_forward_schedule_dates.py: 83 passed in 0.83s
test_forward_schedule_sources.py: 63 passed in 0.65s
test_forward_schedule_game_key.py: 5 passed in 0.66s
test_forward_schedule_team_set.py: 23 passed in 0.67s
test_forward_schedule_fix1f.py: 13 passed in 0.51s
test_forward_schedule_writer.py: 45 passed in 1.72s
~~~
CLI --help: exit 0. Six-path preflight (--base master, S416_spec.md): PASS 9, FAIL 0; no network/data/cache.

NOT VERIFIED
- Live ESPN enumeration and acceptance of dates=; all inputs here are offline constructs.
- Master re-runs and orchestrator landing; this lane measures only the named worktree.
- Superseded timings in the historical build/FIX 1b sections are not current measurements.
- S403's own feed-derived status and single-date boundary exposure need its owner's follow-up.
