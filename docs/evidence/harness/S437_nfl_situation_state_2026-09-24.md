# S437 NFL state completeness

PREPARE / NOT VALIDATED: construct validation only; independent verification pending.
Machine: local C:/Users/neelj/nba-harness-h92, no external archive or network.
The binding orchestrator amendment supersedes the sibling block and capture edits.
Ownership: the new completeness module, its new test file, this memo, and
docs/research/organization-sprint/PROPOSED_S437_yardline_100.md only.

## Corrected premise and binding before-condition

The original missing-situation premise is false. Existing capture preserves the
normalized down, distance, clock, timeouts and period. Only yardline_100 remains
deliberately unresolved. The amendment requests measurement machinery anyway.
Before writing code, a synthetic ESPN payload was passed through the unchanged
normalize_scoreboard, then filtered by the landed _NFL_TOP_LEVEL_KEYS expression.
Exact output (JSON formatting only, no real rows opened):

```text
BEFORE_STATE={"away_timeouts": 3, "clock_seconds_remaining": 500, "distance": 7, "down": 3, "game_seconds_remaining": 2300, "home_timeouts": 2, "period": 2, "possession_text_raw": "KC 25", "yard_line_raw": 25, "yardline_100": null, "yardline_100_status": "semantics_unverified"}
NFL_FEATURES=('score_diff', 'period', 'game_seconds_remaining', 'down', 'distance', 'possession_is_home', 'home_timeouts', 'away_timeouts')
S413_READER={"away_timeouts": ["present", 3], "distance": ["present", 7], "down": ["present", 3], "game_seconds_remaining": ["present", 2300], "home_timeouts": ["present", 2], "period": ["present", 2], "possession_is_home": ["present", 1], "score_diff": ["present", 4]}
22 passed in 0.44s
19 passed in 0.82s
24 passed in 0.87s
```

The test outputs above correspond, respectively, to test_ingest_nfl_states.py,
test_local_state_capture.py and test_nfl_state_ingest.py, each run alone with
`python -m pytest <file> -q -p no:cacheprovider`.

Probe payload, also embedded verbatim as PAYLOAD in the first new test's fixture:

```json
{"events": [{"competitions": [{"competitors": [{"homeAway": "home", "score": "7", "team": {"abbreviation": "KC", "id": "1"}}, {"homeAway": "away", "score": "3", "team": {"abbreviation": "BAL", "id": "2"}}], "situation": {"awayTimeouts": 3, "distance": 7, "down": 3, "homeTimeouts": 2, "possession": "1", "possessionText": "KC 25", "yardLine": 25}, "status": {"clock": 500, "period": 2, "type": {"name": "STATUS_IN_PROGRESS"}}}], "date": "2026-09-24T20:00:00Z", "id": "construct"}]}
```

No REAL ROW is supplied in the spec. This fixture is explicitly CONSTRUCT. Its
first test normalizes it, wraps the v2 envelope, writes three synthetic receipts
across D and D+1, invokes the CLI and verifies the complete persisted report.

## Read-only dependencies inspected before coding

Exact signatures relied on, from the landed files:

```python
# scripts/platformkit/ingame/baseline_four_arm_features.py
def nfl_state(state: object, home_abbr: object, away_abbr: object) -> dict:
# scripts/platformkit/execution/venue_time.py
def parse_venue_time(value: object) -> float | None:
# scripts/platformkit/ingame/nfl_state_field_census.py
def refuse_out(path: Path) -> None:
def refuse_out_under_root(out: Path, root: Path) -> None:
# domains/nfl/ingest_nfl_states.py (construct test only)
def normalize_scoreboard(payload: dict, receipt: dict) -> List[dict]:
```

The reporter imports NFL_BOUNDS and nfl_state unchanged. Count fields require
`type(value) is int`. S413 bounds remain down 1..4, distance 0..99, period 0..10,
timeouts 0..3 and each score 0..200. Added measurement-only bounds are yardline
0..100 and period-clock seconds 0..900. No new predictive field is declared;
yardline_100 is only a census field. Existing FEATURES and CORPORA are unchanged.

## Instrument and denominators

`scripts/platformkit/ingame/nfl_state_completeness.py` reads only
`<root>/state/nfl/<D>.jsonl` and the D+1 shard. Input lines stream from binary
handles; the report retains per-row classifications for reproduction. Each
source names its resolved absolute path, actual bytes read, physical line count,
presence, and resolution `JSONL rows`. Missing shards are explicit zero-input
sources, not claimed complete captures.

`--all-games` selects NFL rows; repeated `--served-game-key` supplies explicit
capture keys. The instrument does not infer game_id mappings or current service
eligibility. Selected games with zero receipts stay in per_game. Invalid game
keys stay in the unassigned row denominator even for served scope.

All selected, nonfuture NFL rows count in `rows`; each of the ten fields has
present + absent + refused = rows. Null is absent for field completeness and
yardline_100 null additionally has its own count. Scores requires both score
fields. Status is top-level. Malformed lines, blank lines, wrong sports, future
rows and outside-scope rows have separate exact counts: their sum plus rows is
the physical input-line denominator. No incomplete row is removed to raise
completeness. Unknown receipts and bad versions refuse all ten fields.

Filtering by response_end_utc precedes scope/schema checks and duplicate handling.
The venue parser validates each timestamp; Decimal reconstruction retains its
fractional digits. Rows are grouped per game in file order: a strictly later
instant opens a new group, an equal instant joins the open group, and a
decreasing instant is refused out_of_order (AMENDMENT 3(c) final rule).
Within a group, identical duplicates keep the first copy and refuse the rest
as duplicate_identical; a group whose copies disagree refuses every copy as
duplicate_conflict. Nothing is silently merged. Processing is in file order;
latest receipt uses the maximum valid parsed timestamp per game.
Duplicate JSON object keys are also refused, including nested ones. Ambiguous
receipt keys use the earliest valid candidate solely for as-of filtering; any
unparseable candidate prevents that filter and the row remains a refusal.
Receipt gaps are consecutive accepted receipt intervals per game, with exact
Decimal strings, interval count and maximum; zero/one receipt has no maximum.
These are observed intervals, not an estimate of missing polls or service uptime.
Raw yard_line_raw / possession_text_raw JSON pairs retain missing/null distinctions
and their frequencies include refused rows. No yardline interpretation is applied.

The output rejects cache, registry and capture-root destinations. Publication
uses a unique temporary file, flush, fsync, then atomic replace; injected partial
write, fsync and replace failures preserve the previous report.

## Acceptance and reproduction

The superseded draft's before = 0 of 14 and bar = 14 of 14 were for a conversion
module. The binding amendment instead says ACCEPTANCE stays CONSTRUCT over the
enumerated cases; bar = all pass. No sampled or scored claim is made.
Reproduction uses only the new construct file:

```text
python -m pytest tests/platformkit/ingame/test_nfl_state_completeness.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.nfl_state_completeness --help
```

The CLI has no production caller. No pre-existing module or test is edited.
LOC-cap note: baseline_four_arm_features.py and local_state_capture_sources.py
remain 300 lines, and local_state_capture.py remains 299; no cosmetic trim needed.
Final construct result: 123 passed in 1.17s (all 123 collected cases passed).
Before-condition regression files: 22 + 19 + 24 passed, run individually.
Total: 188 passing test cases across four per-file invocations; no full suite.
CLI --help exited 0. The proposed diff passed `git apply --check` without being
applied. Contract preflight passed all 9 checks over all four owned files.
Python files are 263 and 247 lines respectively, counted with len(text.splitlines()).
All four owned files passed ASCII decoding and the 300-line ceiling.
The bounded read-only review reproduced the fixes for duplicate JSON keys and
empty team context. It is not the independent model-tier verifier's acceptance.

All eight protected files matched their pre-build SHA-256 byte hashes:

| File | Unchanged SHA-256 |
| --- | --- |
| domains/nfl/ingest_nfl_states.py | a9d5a3b0ada8eed29aab02408e8f4d18e67199750c972d7b38a94840ce1810fb |
| scripts/platformkit/ingame/local_state_capture_sources.py | 70aac0623c242073fed60c48b9894e234c691bde3e20cfda3bd82e36c690062e |
| scripts/platformkit/ingame/baseline_four_arm_features.py | 4cd95bb70b0578318ad04f7144455e083a754924c8b0ee2c6c596e38e9880647 |
| scripts/platformkit/ingame/nfl_state_field_census.py | 9af78772b3d44da556098a367e4d4959dd7eaf64f53fc38b11ddda56675853f2 |
| scripts/platformkit/ingame/local_state_capture.py | 129b12eb42895a5ae02cb8a6fd0c2df4e6860e7259f82a8dee0a969f846957c0 |
| tests/domains/nfl/test_ingest_nfl_states.py | d00af296829e433db1eebbed74f494c77ea7a30af1c537d5139d13c17866adb4 |
| tests/platformkit/ingame/test_local_state_capture.py | cc92f40e7ac8d67946901518e4e8c425d637ac181bee422b2f0653131ee6703d |
| tests/platformkit/ingame/test_nfl_state_ingest.py | 100c3154c44caf65e7b9d7157abd62b881902feb41e8de53777d24b5f661ec06 |

The proposal resides under the repository's ignored docs/research tree; it is on
disk and must be included explicitly by lane_commit. No index writes were made.

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/nfl_state_completeness.py tests/platformkit/ingame/test_nfl_state_completeness.py docs/evidence/harness/S437_nfl_situation_state_2026-09-24.md docs/research/organization-sprint/PROPOSED_S437_yardline_100.md --base master --spec docs/evidence/tracking/specs/S437_spec.md
```

## FIX 1b (AMENDMENTS 1-2)

Base sha for this row: `d0c6f114e` (`git rev-parse --short HEAD` in this worktree,
C:/Users/neelj/nba-harness-h92; HEAD unmoved throughout). Round 1 was Opus tier 2
ACCEPT WITH CORRECTIONS (items a-g below) and codex sol REJECT on four blockers
(items a-d below); both are applied together in this fix.

Item -> code hunk -> test:

- A2(a) microseconds-only instant: `nfl_state_completeness.py` `instant()` (now
  `int(round(parse_venue_time(v) * 1_000_000))`, no own regex/Decimal fractional
  arithmetic) -> `test_nanosecond_digits_collapse_to_one_instant` (both files;
  `.0000001Z`/`.0000009Z` collapse to the same int at this epoch magnitude because
  float64 cannot resolve sub-microsecond digits here, verified interactively before
  writing the test) and `test_microsecond_gap_precision_replaces_nanosecond`
  (replaces the old nanosecond-precision gap assertion with a 2-microsecond one).
- A1(a)+A2(b) first-copy-kept duplicates / conflicts / out-of-order: the per-game
  grouping loop in `census_rows` (groups by file order; a strictly later instant
  opens a group, an equal instant joins it, an earlier one refuses out_of_order)
  -> `test_duplicate_identical_keeps_first_copy`, `test_duplicate_conflict_refuses_every_copy`,
  `test_out_of_order_receipt_refused_and_counted`. Replaces the old
  `test_duplicate_refused_both_permutations` and `test_order_and_latest_per_game`
  (both asserted file-order independence, which A2(b) explicitly ends).
  Regression fallout from making order matter: `test_probe_fixture_end_to_end`'s
  D+1 fixture wrote its two rows in receipt-decreasing order, which is now a
  genuine out_of_order case unrelated to what that test measures, so the write
  order was corrected to receipt-increasing; `test_microsecond_gap_precision_...`
  needed the same correction for its own two rows.
- A1(c)+A2(c) NO_SHARD: `run()` checks both shard paths' presence before reading
  either; if either is absent it calls `census_rows([], ...)` (zero rows
  summarised, including from a genuinely present sibling shard) and sets
  `summary_reason='NO_SHARD'` plus `missing_shards` (absolute paths); each absent
  source also carries `status: 'NO_SHARD'` -> updated `test_output_guards_and_missing_shards`
  (both-missing case) and new `test_one_day_missing_shard_zeroes_rows` in the _1b
  file (one real row on the present shard, still zeroed because the sibling is gone).
- A2(d) sorted ASCII JSON: added `allow_nan=False` to the persisted `json.dump`,
  the stdout `json.dumps`, and the raw-pair `json.dumps`; `sort_keys`/`ensure_ascii`
  were already present -> new `test_persisted_json_is_sorted_ascii_and_typed` (_1b
  file: exact ASCII decode, top-level key order, `int` types on count fields).
- A1(d) bounds pinned + identity: `census.NFL_BOUNDS` was already the same object
  as `baseline_four_arm_features.NFL_BOUNDS` (direct `from ... import NFL_BOUNDS`),
  so no code change; added `test_bounds_pinned_literal_and_nfl_bounds_identity`
  (_1b file) asserting the `is` identity and literal bound tuples, never reading
  them back off `census.BOUNDS` itself.
- A1(e) dead overlay: deleted the unreachable `refused:s413` overlay loop in
  `classify()`. It compared `parsed[name][0] == 'refused'` (from `nfl_state()`,
  same NFL_BOUNDS numeric predicate) against `fields[name] == 'present'` (from
  this module's own `_numeric()`, the identical predicate on the identical value)
  -- the two conditions are mutually exclusive by construction, so the branch
  could never fire. `nfl_state()` still drives `fields['scores']` (via
  `parsed['score_diff']`) and `fields['possession_team']` (via
  `parsed['possession_is_home']`); no other field reads `parsed`.
- A1(f) two constructs: `test_postponed_status_and_missing_state_still_carries_status`
  (_1b file) covers both a `status='postponed'` row classified present, and a row
  with `state=None` still carrying `status='present'` while every other field
  is absent.
- A1(g) unassigned_rows: added `unassigned_rows` (count of rows whose `game_key`
  never resolved to a string, i.e. excluded from every `per_game` bucket) to the
  top-level result -> `test_unassigned_rows_plus_per_game_equals_rows` (_1b file)
  asserts `sum(per_game[g]['rows']) + unassigned_rows == rows`.

Test counts, run individually this session: `test_nfl_state_completeness.py`
125 passed; `test_nfl_state_completeness_1b.py` 6 passed. Neighbouring landed
files re-run unchanged: `test_nfl_state_ingest.py` 24 passed, `test_baseline_four_arm.py`
53 passed, `test_baseline_four_arm_eligibility.py` 45 passed,
`test_baseline_four_arm_nba.py` 134 passed, `test_baseline_four_arm_period.py`
72 passed, `tests/domains/nfl/test_ingest_nfl_states.py` 22 passed,
`tests/platformkit/ingame/test_local_state_capture.py` 19 passed (the three
before-condition counts named above are reproduced unchanged). LOC: 299 / 275 / 70.
`python -m scripts.platformkit.tracking.contract_preflight` over the four
candidate files (module, both test files, this memo): PASS on all 9 checks.

Recomputed A9 row (exact source, this tree, base `d0c6f114e`) -- the eight
protected files' SHA-256 still match the original table above byte-for-byte;
recomputed directly against this worktree rather than carried over from the
`ca49495be` measurement:

| File | SHA-256 (this tree, unchanged) |
| --- | --- |
| domains/nfl/ingest_nfl_states.py | a9d5a3b0ada8eed29aab02408e8f4d18e67199750c972d7b38a94840ce1810fb |
| scripts/platformkit/ingame/local_state_capture_sources.py | 70aac0623c242073fed60c48b9894e234c691bde3e20cfda3bd82e36c690062e |
| scripts/platformkit/ingame/baseline_four_arm_features.py | 4cd95bb70b0578318ad04f7144455e083a754924c8b0ee2c6c596e38e9880647 |
| scripts/platformkit/ingame/nfl_state_field_census.py | 9af78772b3d44da556098a367e4d4959dd7eaf64f53fc38b11ddda56675853f2 |
| scripts/platformkit/ingame/local_state_capture.py | 129b12eb42895a5ae02cb8a6fd0c2df4e6860e7259f82a8dee0a969f846957c0 |
| tests/domains/nfl/test_ingest_nfl_states.py | d00af296829e433db1eebbed74f494c77ea7a30af1c537d5139d13c17866adb4 |
| tests/platformkit/ingame/test_local_state_capture.py | cc92f40e7ac8d67946901518e4e8c425d637ac181bee422b2f0653131ee6703d |
| tests/platformkit/ingame/test_nfl_state_ingest.py | 100c3154c44caf65e7b9d7157abd62b881902feb41e8de53777d24b5f661ec06 |

NEW GAPS carried forward from AMENDMENT 1, neither closed by this fix:

1. Served scope still takes game keys from the caller (`--served-game-key`); the
   census does not derive eligible keys from any served/schedule list itself.
   A later row would need to thread that derivation in explicitly.
2. The yardline proposal would push `domains/nfl/ingest_nfl_states.py` to
   roughly 315 lines (over the 300-LOC cap) if applied as drafted.
   `docs/research/organization-sprint/PROPOSED_S437_yardline_100.md` now carries
   a "NEW GAP" section naming the required split (move `_candidate_yardline`,
   and optionally the unwired `yardline_100_from`, into a new sibling module).

Yardline_100 semantics remain UNVERIFIED (no real-shard fixture exists yet);
this fix only measures completeness of the fields capture already carries.

## FIX 1c (AMENDMENT 3)

Base sha for this row: `aac8a5b86` (`git rev-parse --short HEAD` in this worktree,
C:/Users/neelj/nba-harness-h92; HEAD unmoved throughout). Round 2 was codex sol
REJECT on two blockers (a, b below) and one correction (c below).

Item -> code hunk -> test:

- A3(a) non-finite values never crash: `nfl_state_completeness.py` gained
  `ensure_ascii=True, allow_nan=False` on the `_Object` dedup-key `json.dumps(v,
  sort_keys=True)` call and the row-details tiebreak `json.dumps(r, sort_keys=True)`
  call (one keyword addition each, no new lines; LOC stays 299). `min()` calls its
  key function on every group member, including single-member groups (verified
  interactively before writing the fix), so a NaN or Infinity anywhere in a row --
  nested arbitrarily deep in `state` -- now raises inside the `object_pairs_hook`
  construction that runs as part of `json.loads`; the existing per-line
  `except ValueError: counts['malformed'] += 1; continue` already catches it, so
  the census completes with no new except clause. This is a genuine behavior
  change from pre-A3: NaN/Infinity used to reach per-field `refused:non_int`
  classification; now the whole row is malformed before it is ever classified.
  `test_numeric_refusals` and `test_bad_receipt_stays_in_denominator` in the main
  construct file had their NaN/Infinity parametrize cases removed (with a comment
  explaining why) since those values no longer produce the old per-field outcome.
  New regressions in the _1b file: `test_non_finite_raw_value_counted_malformed_not_crashed`
  (state-nested yard_line_raw/down/clock_seconds_remaining, x NaN/+Infinity/-Infinity)
  and `test_non_finite_receipt_counted_malformed_not_crashed` (top-level
  response_end_utc, same three values).
- A3(b) exact-byte and strict-int assertions: `test_persisted_json_is_sorted_ascii_and_typed`
  (_1b file) now compares the persisted file's bytes to
  `json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False, indent=2)
  .encode('ascii') + b'\n'` exactly, drives the CLI and compares captured stdout
  bytes to `json.dumps({'rows': ..., 'distinct_game_keys': ...}, sort_keys=True,
  ensure_ascii=True, allow_nan=False) + '\n'` exactly, and walks the whole parsed
  report with a new recursive `_assert_int_counts` helper requiring `type(value)
  is int` at every integer found, with the one legitimate boolean
  (`sources[i]['present']`) named as the sole excluded path. Writing the exact
  persisted-byte assertion surfaced a real platform bug on this machine: the
  writer opened its temp file in Windows default text mode, so every persisted
  `\n` was silently translated to `\r\n`, failing the byte comparison. Fixed in
  `run()` by adding `newline=''` to the `tempfile.NamedTemporaryFile(...)` call
  (one keyword, no new line) so the persisted bytes are LF-exact on any platform.
- A3(c) memo restated: the paragraph at the old :85-89 location (above, under
  "Instrument and denominators") is rewritten to the final rules -- identical
  duplicates keep the first copy (duplicate_identical), conflicting copies refuse
  every copy (duplicate_conflict), decreasing instants are out_of_order,
  processing is in file order -- and the file-order-independence sentence is
  removed.

Test counts, run individually this session: `test_nfl_state_completeness.py`
105 passed (125 at fix 1b, minus 20 NaN/Infinity parametrize cases now superseded
by the malformed-row regressions); `test_nfl_state_completeness_1b.py` 18 passed
(6 at fix 1b, plus 12 new non-finite cases: 9 state-nested + 3 receipt-level).
Neighbouring landed files re-run unchanged, each singly: `test_baseline_four_arm.py`
53 passed, `test_baseline_four_arm_eligibility.py` 45 passed,
`test_baseline_four_arm_nba.py` 134 passed, `test_baseline_four_arm_period.py`
72 passed, `test_nfl_state_ingest.py` 24 passed (all match their fix-1b counts).
LOC: 299 / 275 / 111 (module / main test file / _1b test file), all <= 300.
No move to a new `nfl_state_completeness_io.py` was needed: both A3(a) hunks
added keywords to existing lines rather than new lines, so the module stayed at
its pre-existing 299-line count.

Recomputed A9 row (this tree, base `aac8a5b86`) -- the eight protected files'
SHA-256 still match the original table byte-for-byte, recomputed directly:

| File | SHA-256 (this tree, unchanged) |
| --- | --- |
| domains/nfl/ingest_nfl_states.py | a9d5a3b0ada8eed29aab02408e8f4d18e67199750c972d7b38a94840ce1810fb |
| scripts/platformkit/ingame/local_state_capture_sources.py | 70aac0623c242073fed60c48b9894e234c691bde3e20cfda3bd82e36c690062e |
| scripts/platformkit/ingame/baseline_four_arm_features.py | 4cd95bb70b0578318ad04f7144455e083a754924c8b0ee2c6c596e38e9880647 |
| scripts/platformkit/ingame/nfl_state_field_census.py | 9af78772b3d44da556098a367e4d4959dd7eaf64f53fc38b11ddda56675853f2 |
| scripts/platformkit/ingame/local_state_capture.py | 129b12eb42895a5ae02cb8a6fd0c2df4e6860e7259f82a8dee0a969f846957c0 |
| tests/domains/nfl/test_ingest_nfl_states.py | d00af296829e433db1eebbed74f494c77ea7a30af1c537d5139d13c17866adb4 |
| tests/platformkit/ingame/test_local_state_capture.py | cc92f40e7ac8d67946901518e4e8c425d637ac181bee422b2f0653131ee6703d |
| tests/platformkit/ingame/test_nfl_state_ingest.py | 100c3154c44caf65e7b9d7157abd62b881902feb41e8de53777d24b5f661ec06 |

Yardline_100 semantics remain UNVERIFIED (no real-shard fixture exists yet); this
fix, like fix 1b, only measures completeness of the fields capture already carries.

## FIX 1d (AMENDMENT 4)

Base sha for this row: `bb393cbc3` (`git rev-parse --short HEAD` in this worktree,
C:/Users/neelj/nba-harness-h92; HEAD unmoved throughout). Round 3 was codex sol
REJECT on three items (a-c below).

Item -> code hunk -> test:

- A4(a) stdout bytes are LF only: `nfl_state_completeness.py` `main()` no longer
  calls `print(...)` (text-mode stdout, which silently translates `\n` to `\r\n`
  on Windows -- the same class of bug A3(b) already fixed for the persisted
  file). It now builds the summary JSON string, appends a single `'\n'`, encodes
  it ASCII, and writes it in one call via `sys.stdout.buffer.write(...)`, bypassing
  text-mode translation entirely. `import sys` was added (alphabetical, between
  `re` and `tempfile`); one pre-existing blank import-separator line was removed
  as the matching cosmetic trim, so the module stays at its pre-existing 299-line
  count -> `test_persisted_json_is_sorted_ascii_and_typed` (_1b file) switched its
  fixture from `capsys` to `capsysbinary` and now compares `capsysbinary.readouterr().out`
  (bytes) against `json.dumps(...).encode('ascii') + b'\n'` exactly; `capsys`
  could not have caught the original bug because pytest's text-capture fixture
  does its own newline normalization, masking the very translation being fixed.
- A4(b) strict-int assertion that bites: the `_1b` file's `_assert_int_counts`
  helper walked every dict/list in the report (top-level counts, per-game counts,
  nested `refused_by_reason` and `raw_yardline_field_side_pairs` maps, `sources[].bytes`
  and `.lines`) but silently skipped any leaf that was neither `dict`, `list`,
  `bool`, nor `int` -- a float in a count slot (e.g. a mutated `rows = 1.5`) fell
  through every branch unchecked and the assertion never fired. Fixed by widening
  the leaf check from `isinstance(node, int)` to `isinstance(node, (int, float))`
  while keeping the assertion itself at `type(node) is int`, so a genuine int
  still passes and a float now fails -> two new regressions,
  `test_int_count_assertion_bites_on_float_rows` (mutates top-level `rows` to
  `1.5`, wrapped in `pytest.raises(AssertionError)`) and
  `test_int_count_assertion_bites_on_boolean_count` (mutates `diagnostics.lines`
  to `True`, a bool outside the sole legitimate `sources[].present` path, also
  wrapped in `pytest.raises(AssertionError)`). The existing bool-path exclusion
  and the real (unmutated) report's call to `_assert_int_counts` were re-verified
  unchanged.
- A4(c) memo LOC corrected: the FIX 1c LOC line claimed `102` lines for the `_1b`
  test file; the measured value at that point (and today, before this fix's two
  new tests) is `111`. Corrected above to `299 / 275 / 111`. All A9 identities in
  this section are regenerated directly from this tree rather than carried over.

Test counts, run individually this session: `test_nfl_state_completeness.py`
105 passed (unchanged -- this fix touches only the module's CLI writer and the
`_1b` test file, not the main construct file); `test_nfl_state_completeness_1b.py`
20 passed (18 at fix 1c, plus the 2 new A4(b) mutation regressions).
Neighbouring landed/tracked files re-run unchanged, each singly:
`test_baseline_four_arm.py` 53 passed, `test_baseline_four_arm_eligibility.py`
45 passed, `test_baseline_four_arm_nba.py` 134 passed,
`test_baseline_four_arm_period.py` 72 passed, `test_nfl_state_ingest.py`
24 passed, `test_local_state_capture.py` 19 passed,
`tests/domains/nfl/test_ingest_nfl_states.py` 22 passed (all match prior counts).
`python -m scripts.platformkit.ingame.nfl_state_completeness --help` exited 0.
LOC (measured with `wc -l` this session): 299 / 275 / 129 (module / main test
file / `_1b` test file, which grew by the two new mutation tests), all <= 300;
no move to a new `nfl_state_completeness_io.py` was needed -- the stdout-writer
hunk stayed LOC-neutral (one import line added, one blank import-separator line
removed). `python -m scripts.platformkit.tracking.contract_preflight --base
master --spec docs/evidence/tracking/specs/S437_spec.md` over the four candidate
files (module, both test files, this memo): PASS on all 9 checks, 0 FAIL.

Recomputed A9 row (this tree, base `bb393cbc3`) -- the eight protected files'
SHA-256 still match the original table byte-for-byte, recomputed directly with
`git diff --quiet master -- <path>` (all unchanged) and a fresh SHA-256 pass:

| File | SHA-256 (this tree, unchanged) |
| --- | --- |
| domains/nfl/ingest_nfl_states.py | a9d5a3b0ada8eed29aab02408e8f4d18e67199750c972d7b38a94840ce1810fb |
| scripts/platformkit/ingame/local_state_capture_sources.py | 70aac0623c242073fed60c48b9894e234c691bde3e20cfda3bd82e36c690062e |
| scripts/platformkit/ingame/baseline_four_arm_features.py | 4cd95bb70b0578318ad04f7144455e083a754924c8b0ee2c6c596e38e9880647 |
| scripts/platformkit/ingame/nfl_state_field_census.py | 9af78772b3d44da556098a367e4d4959dd7eaf64f53fc38b11ddda56675853f2 |
| scripts/platformkit/ingame/local_state_capture.py | 129b12eb42895a5ae02cb8a6fd0c2df4e6860e7259f82a8dee0a969f846957c0 |
| tests/domains/nfl/test_ingest_nfl_states.py | d00af296829e433db1eebbed74f494c77ea7a30af1c537d5139d13c17866adb4 |
| tests/platformkit/ingame/test_local_state_capture.py | cc92f40e7ac8d67946901518e4e8c425d637ac181bee422b2f0653131ee6703d |
| tests/platformkit/ingame/test_nfl_state_ingest.py | 100c3154c44caf65e7b9d7157abd62b881902feb41e8de53777d24b5f661ec06 |

Yardline_100 semantics remain UNVERIFIED (no real-shard fixture exists yet); this
fix, like fix 1b and 1c, only measures completeness of the fields capture already
carries.

## NOT VERIFIED

- Independent verifier acceptance and reproduction in master.
- Real Thursday or Sunday shards, real field-side semantics, and a real-row fixture.
- Any proposed conversion applied to normalization or used by capture.
- Actual served-game membership; keys are supplied explicitly by the caller.
- Live receipt cadence, missing polls, concurrent capture appends, and long-run memory use.
- OS power loss during publication, directory fsync durability, or permission failures.
- Calibration or model performance; this instrument reports completeness only.
- Yardline_100 semantics: UNVERIFIED, no real-shard fixture exists yet.
