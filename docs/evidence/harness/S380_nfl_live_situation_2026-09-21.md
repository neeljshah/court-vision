# S380 - PREPARE; archive semantics UNVERIFIED
Local machine, worktree C:/Users/neelj/nba-harness-h36. Construct tests only.
Binding before-condition: `ls domains/nfl/verify_live_situation.py`, exit 1:
```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h36\domains\nfl\verify_live_situation.py' because it does not exist.
At line:2 char:1
+ ls domains/nfl/verify_live_situation.py
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (C:\Users\neelj\...ve_situation.py:String) [Get-ChildItem], ItemNotFound
   Exception
    + FullyQualifiedErrorId : PathNotFound,Microsoft.PowerShell.Commands.GetChildItemCommand
```
Read before coding: domains/nfl/ingest_nfl_states.py (S350).
Exact source signature: `def normalize_scoreboard(payload: dict, receipt: dict) -> List[dict]:`.
The new modules do not import or call that adapter. Its raw mappings are:
`situation = comp.get("situation") or {}`;
`"yard_line_raw": situation.get("yardLine")`;
`"possession_text_raw": situation.get("possessionText")`;
`"down_distance_text_raw": situation.get("downDistanceText")`;
`possession_id = situation.get("possession")`, then
`"possession_team_id_raw": possession_id`.
Possession matches `str(home_team.get("id")) == str(possession_id)` or the
away equivalent, then uses that team's abbreviation; otherwise None.
`"down": _int_or_none(situation.get("down"))` and
`"distance": _int_or_none(situation.get("distance"))`.
Timeouts use `_int_or_none(situation.get("homeTimeouts"))` and the away equivalent.
`is_red_zone = situation.get("isRedZone")`, retained only when bool.
`"last_play_id": (situation.get("lastPlay") or {}).get("id")`.
`"yardline_100": None`, `"yardline_100_status": "semantics_unverified"`.
Period and clock use `_int_or_none(status.get("period"))` and
`_clock_seconds(status)`; scores use `_int_or_none(home.get("score"))`
and the away equivalent. Receipt fields copy the supplied receipt.
No drive or series identifiers are produced by S350.
Only landed runtime import, read in full before coding:
scripts/platformkit/execution/venue_time.py:
`def parse_venue_time(value: object) -> float | None:`.
It rejects unzoned text but truncates fractional seconds to microseconds.
The candidate validates through it and parses whole seconds through it, then
preserves the original fractional digits as integer nanoseconds.
The requested docs/evidence/VERIFIER_CONTRACT.md is absent; the binding
docs/evidence/tracking/VERIFIER_CONTRACT.md was read, including B and Q.
Implemented both pure normalizers and the offline JSONL CLI, with no existing
module edited. The existing tests/domains/nfl layout is used. The spec's entire
REAL ROW is embedded verbatim in test_verify_live_situation.py; its first test
passes that fixture through JSONL input, main(), atomic output and JSON readback.
Only whitespace line wrapping is removed to form the one-line JSONL record.
Interpretations: H_OWN_GOAL returns 100 - raw for either possessing side;
H_HOME_GOAL returns 100 - raw for home and raw for away; H_TEXT uses the named
territory (own: 100 - yard; opponent: yard). Raw and text interpretations are
independent hypotheses; syntactically invalid present fields are counted refusals.
Counts require exact int types. Missing fields remain unknown, except explicit
numeric down/distance text can supply its own observed values. Goal text supplies
only down. No numeric coercion is used for count validation.
Receipt identity is (game_key, parsed response_end_utc, parsed capture_ts).
Sorting uses response then capture at nanosecond precision. Rows later than the
query time are counted and skipped before other schema or receipt grouping.
Every duplicate identity is counted and refused, including identical copies;
conflicting identities are counted separately. Invalid/conflicting rows with a
usable game and time break adjacent play comparisons. Clock and timeout checks
retain last known values in the period or half across missing observations.
Original distance/score/possession rules are historical: FIX 2b superseded them
under AMENDMENT 1; FIX 2e below restores row-identified possession evidence.
Red-zone true is checked at <=20.
Timeout checks cover halves in regulation; overtime timeout resets are untested.
Clock checks are scoped to each period. Pre/final null situations do not supply
orientation evidence. Bounds refuse, rather than truncate, impossible readings:
yard and distance 0..100, down 1..4, timeouts 0..3, score 0..200, period 1..20,
clock 0..900 (0..600 in overtime), regulation game clock 0..3600.
Each accepted row supplies six check opportunities per hypothesis, including
untestable observations. Totals equal the sum of per-check counts. A supporting
transition counts at most once per adjacent pair and requires distance,
touchdown or stationary possession-change evidence. Clock, timeout and repeated
red-zone polling cannot inflate the 30-transition requirement. Contributing
games and home/away sides count only those transitions; touchdown support credits
the previous possessing side. Exactly one hypothesis must have zero contradictions,
at least 30 supporting transitions, at least 2 games and both possessing sides.
The report always names refusal denominators and supplies an UNVERIFIED reason.
Output is a flushed, fsynced temporary sibling followed by atomic replacement.
Partial serialization or replacement failure leaves the preceding report intact
and a recoverable temporary file; both failure paths are construct-tested.
Validation commands (local; one test file at a time):
```text
python -m pytest tests/domains/nfl/test_situation_normalize.py -q -p no:cacheprovider
python -m pytest tests/domains/nfl/test_verify_live_situation.py -q -p no:cacheprovider
python -m domains.nfl.verify_live_situation --help
python -m scripts.platformkit.tracking.contract_preflight --paths domains/nfl/situation_normalize.py domains/nfl/verify_live_situation.py tests/domains/nfl/test_situation_normalize.py tests/domains/nfl/test_verify_live_situation.py docs/evidence/harness/S380_nfl_live_situation_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S380_spec.md
```
Construct cases cover all hypotheses, mirrored coordinates, 29/30/31 transitions,
one-game and one-side refusal, ambiguity, null states, strict types, malformed
JSON, exact timestamp boundaries, receipt ties, duplicate conflicts, permutations,
short/long scores, red-zone bounds, half resets and interrupted output.
Read-only review found three defects, fixed with regressions: touchdown side
credit, monotonic checks across nulls, and contradictory/malformed goal ordinals.
The reviewer then confirmed those three fixes by static inspection.
Initial candidate results: normalization 61 passed; verification 94 passed; total 155
CONSTRUCT tests. CLI --help passed (exit 0). Contract preflight passed all 9
checks. No pre-existing tracked file differs; git status lists only the five
owned new files. Every file is ASCII and <=300 lines, using len(text.splitlines()).
Construct inputs are the two test files named above; no real archive was opened.
## FIX 1b
Both findings in the independent verdict were reproduced before module edits.
The local spec and `git show master:docs/evidence/tracking/specs/S380_spec.md`
were read in full; neither contains an AMENDMENT block.
1. BLOCKING: distance evidence previously admitted penalties. The verifier's
   construct was reproduced with `drives(30)` from the verification test file,
   setting each state's `play_classification` to `penalty`, then calling
   `verify_rows(rows, now=NOW)`. These are 60 rows forming 30 transitions,
   across two games and both possessing sides, each 1st & 10 to 2nd & 8.
   Exact before output:
   `BLOCKING before: VERIFIED supporting_transitions=30 distance={'support': 30, 'contradiction': 0, 'untestable': 30}`
   The new per-file regression run failed before the module fix:
   `AssertionError: assert 'VERIFIED' == 'UNVERIFIED'`; `9 failed, 95 passed`.
   The distance branch now requires the current state's explicit
   `play_classification == "ordinary_scrimmage"`. This field describes the
   completed play leading into that row; an earlier row's classification
   cannot authorize it. Other observation checks are unchanged.
   The same reproduction after the fix prints:
   `BLOCKING after: UNVERIFIED supporting_transitions=0 distance={'support': 0, 'contradiction': 0, 'untestable': 60}`
   `test_distance_requires_explicit_ordinary_scrimmage` enumerates penalty,
   turnover_on_downs, kickoff, punt, end_of_half, unknown, unrecognized,
   explicit None, absent classification, and ordinary_scrimmage. Each checks
   reversed input order, the verdict, transition count and distance counters.
   Existing ordinary-play fixtures now explicitly declare their classification.
2. CORRECTION: `checked_state` was called with state
   `{"period": None, "clock_seconds_remaining": 601}` and the valid KC/IND
   live envelope. Exact before output:
   `CORRECTION before: {'period': None, 'clock_seconds_remaining': 601}`.
   The defect was the two `or 0` expressions, not acceptance of unknown period.
   Both values are now bound and tested explicitly against None before applying
   the overtime bound. Exact after output intentionally preserves the result:
   `CORRECTION after: {'period': None, 'clock_seconds_remaining': 601}`.
   Eight new construct cases preserve missing/None fields, allow regulation
   900 and overtime 0/600, and refuse known overtime 601. No missing field
   is synthesized. No unrelated normalization behavior changed.
Final FIX 1b per-file results: verification 104 passed; normalization 69 passed;
total 173 CONSTRUCT tests. The commands above were run one file at a time with
`-q -p no:cacheprovider`. CLI --help exited 0; there is no separate row self-check
CLI. Both owned modules were edited. All code/test files are ASCII and <=300
lines. No real archive, network, pod, or FWER ledger was used.
FIX 1b contract preflight: 9 PASS, 0 FAIL over the five owned files; the verdict
file was excluded. Files remain on disk for lane_commit; no SHA was created.
## FIX 2a
Local worktree only; the user authorized edits to the landed S380 files for this
fix. The original NEW-files before-condition is historical, not this fix's premise.
Orchestrator finding (2026-09-22 00:58Z, not independently rerun here): 7,725
archive rows, 244 live, each hypothesis with zero support and contradiction and
46,350 untestable observations. The landed validator additionally refused live
status outright. The supplied fixture confirms live status on all 60 rows.
Verbatim input, resolution not applicable (JSONL):
`C:/Users/neelj/nba-harness-h36/tests/domains/nfl/fixtures/s380_real_live_rows_2026-09-22.jsonl`
is 51,968 bytes, 60 rows, one game (401872947), 49 NYG and 11 LAR possessions.
SHA-256: `05cfc118963c76872b51f350e82335dff0a7f31213724d697457131b34c1a321`.
The supplied bytes are unchanged and belong in the lane_commit path list.
Status vocabulary sources:
- The fixture quotes `"capture_version":"local_state_capture_v1"` and
  `"status":"live"` on every row. The user reports pre/live/final in production.
- `scripts/platformkit/ingame/live_loop.py:65` quotes
  `_STATE_MAP = {"pre": "pre", "in": "live", "post": "final"}`;
  `scripts/platformkit/ingame/state_bus.py:28` quotes
  `_STATUS = ("pre", "live", "final")`. Capture-writer linkage is not established.
- `domains/nfl/ingest_nfl_states.py:53` defines `_STATUS_MAP`, including
  `"STATUS_IN_PROGRESS": "in"`, `"STATUS_HALFTIME": "in"` and
  `"STATUS_END_PERIOD": "in"`. Retain in for S350 compatibility.
Validation and all three live checks now share live/in membership. Statuses
outside pre/live/in/final are counted status refusals, including delayed and
postponed as expressly required by FIX 2a. No threshold or observation check
semantics changed; S350 remains unchanged.
The real-fixture test exposed a second input-format mismatch after the status
fix: `1 failed, 115 passed`, with accepted_rows=0 rather than 60. Every fixture
down-distance string has a location suffix, such as `2nd & 6 at NYG 34`.
The parser now accepts this bounded suffix; malformed suffixes and conflicting
down/distance counts still refuse. No missing number becomes zero.
The fixture runs through main(), JSON output and verify_rows(). A seeded shuffle
must reproduce the complete report. All 60 rows are accepted with zero refusals.
Each hypothesis has clock support=59 and timeouts support=59, each with zero
contradictions and one untestable observation. Distance is untestable on all 60.
H_TEXT is checked for every real possession; separate LAR 22 constructs return
78 for LAR possession and 22 for NYG possession. Counts are strict integers.
The requested nonzero real distance assertion is BLOCKED by missing evidence:
all 60 rows lack drive_id, series_id and play_classification. Inferring these
would change the FIX 1b check semantics and admit unclassified plays. The test
therefore asserts the honest zero distance result, plus the absence of those
fields. Synthetic ordinary-play tests exercise 30 distance transitions for both
live and in. Real-fixture verdict remains UNVERIFIED. No fixture fields were added.
All three existing except clauses still count refusals or malformed JSON;
uncaught failures propagate. No new exception handler was introduced.
FIX 2a results: verification 116 passed; normalization 79 passed (195 total).
CLI --help exited 0. Run the two commands above individually with no cacheprovider.
The preflight command above must also include the fixture path given here.
Contract preflight: 9 PASS, 0 FAIL across all six lane files including the fixture.

## FIX 2b

AMENDMENT 1 was read with `git show master:docs/evidence/tracking/specs/S380_spec.md`.
It supersedes the historical explicit-classification rules in FIX 1b/2a above.
The local machine and supplied 51,968-byte / 60-row fixture above are the only
real input; its bytes and SHA-256 remain unchanged. No full archive was opened.
The new domains/nfl/situation_infer.py supplies deterministic receipt-ordered
inference. Same possession and known unchanged scores define drive continuity;
each observed down=1 starts a series, even on repeated polling. Any change of
(down, distance, yard_line_raw, last_play_id) defines a play. Optional drive and
series IDs and ordinary-play classification no longer authorize distance checks.
Distance uses consecutive plays within an observed series, down increasing by
one, and signed movement with <=1-yard disagreement. Zero gains and losses are
included. The fixture begins on down=2: its first 2->3 pair precedes an observed
series start and is untestable. New first downs and new drives end the old series.
FIX 2e restores the row-identified possession-change evidence removed by FIX 2d.
Missing scores never establish unchanged scores. Missing situation fields block
situation checks while the FIX 2a clock/timeout comparisons still run.
Raw null/absent fields remain untestable even if numeric text could fill them.
Touchdowns accept +6/+7/+8 for the previous possessing side, supporting at <=40
yards and counting larger values as long_score, never as contradictions.
Games/sides now include testable distance, touchdown and possession transitions,
including contradictions. Clock/timeout support and red-zone polling do not
supply transition diversity; long_score remains an untestable touchdown outcome.
Supporting transitions still count at most once per
pair. VERIFIED still requires zero contradictions, >=30 supporting transitions,
>=2 games, both possessing sides, and exactly one qualifying hypothesis.
Real-fixture counts corrected by FIX 2e are support / contradiction / untestable:
| Hypothesis | distance | possession_change | touchdown | total | transitions |
| --- | --- | --- | --- | --- | --- |
| H_OWN_GOAL | 4 / 1 / 55 | 0 / 1 / 59 | 0 / 0 / 60 | 122 / 2 / 236 | 4 |
| H_HOME_GOAL | 5 / 0 / 55 | 0 / 1 / 59 | 0 / 0 / 60 | 123 / 1 / 236 | 5 |
| H_TEXT | 5 / 0 / 55 | 1 / 0 / 59 | 0 / 0 / 60 | 124 / 0 / 236 | 6 |
All have games=1, sides=2, long_score=0; clock and timeouts each 59 / 0 / 1;
red_zone is 0 / 0 / 60. Input=accepted=60; refusals=0; malformed_json=0.
The report remains UNVERIFIED. AMENDMENT 1(g) exception: rule (e) is defeated
by both scores being exactly zero on every supplied row, so no +6/+7/+8 exists.
No inference can supply a touchdown without inventing an observation. The tests
assert this zero-score census and all exact counts, plus seeded shuffle equality.
Synthetic drives cover (b)-(f), including both scoring sides, conversions, 40/41,
1-yard and 3-yard boundaries, null/absent fields, zero/negative gains and diversity
from contradictions. All counts are strict integers. Every except clause still
counts refusals or malformed JSON; unhandled failures re-raise to the caller.
FIX 2b results: normalization/inference 145 PASS; verification 116 PASS; total
261 tests. Both per-file commands above used -q -p no:cacheprovider.
CLI --help: PASS (exit 0). Contract preflight: 9 PASS, 0 FAIL over seven files.
The preflight path list adds domains/nfl/situation_infer.py and the fixture.
Independent read-only review found no blocking defect; no extra tests were run.

## FIX 2c

Finding 1 (BLOCKING): changed checked_state's refusal to status_refused.
Minimal reproduction before, for both status="bogus" and missing status:
`accepted_rows=0, refusals={'status': 1}`.
After, both reproduce `accepted_rows=0, refusals={'status_refused': 1}` (PASS).
Finding 2 (CORRECTION): the initial single-test coverage probe reported
`FAIL (no single test names {pre, live, in, final})`.
Extended the existing parameterized refusal regression to name that exact set,
assert acceptance and all six checks completely untestable on empty states,
and assert status_refused for unknown, malformed and missing statuses.
All nine previous rejection cases remain; bogus and missing are explicit cases.
Before the module fix: `11 failed, 111 passed`, with the failing assertion
`assert {'status': 1} == {'status_refused': 1}`. After: `122 passed`.
The combined regression now covers 15 cases, including all four accepted values.
Findings 3 and 4 (NOTE): inference, FIX 2a/2b behavior and fixture kept intact.
Finding 5 (NOTE): retain the fixture in the eventual targeted lane_commit.
Validation: verification 122 PASS; normalization/inference 145 PASS; total 267.
Each file ran separately with `-q -p no:cacheprovider`; CLI --help exited 0.
The CLI exposes no separate self-check command. Only construct/fixture tests ran.

## FIX 2d

Historical attempt: required explicit turnover_on_downs for possession evidence.
Its 166 normalization/inference and 122 verification passes enforced an incorrect
unknown-classification rule. FIX 2e supersedes that rule and its zero counts.

## FIX 2e

Finding 1 (BLOCKING): reproduced `(4, KC, 0-0, None)` to `(1, IND, 0-0, None)`
with inferred_row, raw=65 and text="KC 35" for both rows, then inferred_report.
Before, every hypothesis: `{'support': 0, 'contradiction': 0, 'untestable': 2}`.
Failing output: `AssertionError: fourth-down no-score flip incorrectly untestable`.
Regressions before the module edit: `12 failed, 191 passed`; exact mismatch:
`{'contradiction': 0} != {'contradiction': 1}; {'untestable': 2} != {'untestable': 1}`.
situation_infer now uses the observed fourth-to-first, changed-possession,
known-unchanged-score transition even with absent/unknown classification.
Explicit kickoff/punt still veto it. All other unknown flips remain untestable.
After, support / contradiction / untestable: H_OWN_GOAL=0/1/1,
H_HOME_GOAL=0/1/1, H_TEXT=1/0/1; all three exact reproduction assertions PASS.
Regressions cover missing/None/unknown classification, reversed order, incomplete
transition evidence, score-followed flips, explicit kicks and fixture rows 49-50.
Full fixture counts and totals are corrected in the table above.
Findings 2 and 3 (NOTE): score-followed refusal, statuses, distance inference and
transition-only diversity remain unchanged; the existing checks still pass.
Validation: normalization/inference 203 PASS; verification 122 PASS; total 325.
Both files ran separately with `-q -p no:cacheprovider`; CLI --help PASS (exit 0).
No separate self-check CLI exists. TEMP/TMP used this worktree's .tmp_s380_2e.
Construct/fixture inputs only; no archive, network, pod or measured comparison.
Contract preflight: 9 PASS, 0 FAIL over all seven row files; verdict excluded.

## NOT VERIFIED

- Real touchdown transitions: rule (e) has no score increase in this fixture.
- Real NFL orientation: one game and at most six supporting transitions cannot
  meet the unchanged VERIFIED thresholds. Full archive and deployed callers unrun.
- Real possession-change orientation beyond the single supplied fixture transition.
- Overtime timeout policy, long-return reconstruction and provider corrections.
- Operating-system power-loss behavior and concurrent archive writers.
- No commit was created; files are ready for lane_commit.
