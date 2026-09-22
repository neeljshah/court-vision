# S381: PREPARE, construct validation passed

No source has been qualified by this build lane. Network access was not used. The orchestrator must run the opt-in probe from the main tree and record its observed verdict in the ledger. The pod
remains OFF.

## Binding before-condition

Read `docs/evidence/tracking/specs/S381_spec.md` before implementation. Command: `ls domains/tennis/live_point_probe.py`. Exit code: 1. Exact output:

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h37\domains\tennis\live_point_probe.py' because it does not exist.
At line:2 char:1
+ ls domains/tennis/live_point_probe.py
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (C:\Users\neelj\..._point_probe.py:String) [Get-ChildItem], ItemNotFound
   Exception
    + FullyQualifiedErrorId : PathNotFound,Microsoft.PowerShell.Commands.GetChildItemCommand
```

## Owned files and interfaces

These five new files are owned by this row (the last test file was added in FIX 1c):

- `domains/tennis/live_point_probe.py`: bounded probe and atomic report writer.
- `domains/tennis/live_point_candidates.json`: ATP/WTA scoreboard and summary
  endpoint templates from the spec, plus the specified ITF page.
- `tests/domains/tennis/test_live_point_probe.py`: construct fixtures and tests.
- `tests/domains/tennis/test_live_point_probe_1c.py`: candidate aggregation regressions.
- `docs/evidence/harness/S381_tennis_point_probe_2026-09-21.md`: this memo.

The existing test layout is `tests/domains/tennis/`, including `test_ingest_setdetail_states.py`; the new tests follow that directory layout. No pre-existing module was edited. No new production
caller or flag was added.

Before coding, read the landed dependency `scripts/platformkit/execution/venue_time.py` in full. Its exact imported API is `def parse_venue_time(value: object) -> float | None:`. The module returns
None for unzoned or invalid input. This probe only asks whether a source timestamp parses; it performs no source-time ordering or cutoff. Its known sub-microsecond truncation therefore cannot change a
boundary here. Observation separation uses the local monotonic clock, requiring a second request start at least 30 seconds after the first response completes. Also read the existing import-package
initializers before coding; they expose no callable API used by this module. All remaining production imports are stdlib.

The spec supplies URL templates, but no REAL ROW payload. The first test consumes the synthetic `point_payload` fixture through injected HTTP responses, the probe, atomic report persistence, and JSON
reload. This is CONSTRUCT evidence only. The only on-disk probe input exercised by the tests is `C:/Users/neelj/nba-harness-h37/domains/tennis/live_point_candidates.json` (688 bytes; resolution not
applicable). Its endpoint templates are verbatim from the spec, with both league substitutions. No archived input, person record, video, or measured source sample was opened. Image resolution is not
applicable.

## Behavior and conservative refusals

Two passes share a strict integer request budget (default 20). Per-host spacing defaults to 2.0 seconds. Summary templates expand only to discovered numeric live match IDs, in sorted order; dates use
the local UTC receipt date. Empty discovery reports NO_LIVE_MATCH. Candidate preparation is sorted independently of input order. Duplicate candidates and duplicate live match identities are refused.

GET requests use urllib's default headers. Redirects and environment proxies are disabled, so hidden requests cannot escape the accounting. No credentials, cookies, authentication, or browser
execution are supplied. HTTP 401/403/429 stops the host immediately, even if body reading fails. Recognized challenge markers also stop the host. Other hosts can continue within the shared budget.

Every attempted response records aware UTC receipts, status, content type, complete-body length and SHA-256 when available, JSON parse status, and a field census. Non-success JSON still receives a
census. Missing metadata stays null. Bodies above 2,000,000 bytes are refused, marked body_truncated, and have null full-body length/hash; no prefix is represented as a complete response. Every
handled exception increments a refusal count; write errors propagate.

Within-game points and current-set games/sets must be valid in one live match; fields from different matches cannot qualify each other. Direct count fields refuse booleans, floats, numeric strings,
missing values, and implausible magnitudes. Provider linescores separately normalize exact integral numeric encodings, including decimal JSON numbers and numeric strings, without a float conversion.
JSON duplicate keys and non-finite constants are refused. Decimal parsing keeps fractional JSON numbers from passing integer checks. No price or fee math exists. Known schema key paths are retained
within 300 total characters per response; unknown key segments are replaced by `*`. No response values or body fragments are persisted. The output identifies candidates by their input-list index.

POINT_LEVEL requires all four state fields on a live match. Overall qualification requires two POINT_LEVEL responses for the same resolved URL, different complete body hashes, and at least 30 seconds
of separation. Otherwise the overall verdict is BLOCKED with a reason. SET_LEVEL and NO_LIVE_MATCH remain explicit outcomes. Atomic replacement follows JSON serialization, flush, and os.fsync. A
failed serialization, fsync, or replacement leaves an existing report intact; an unpublished temporary file may remain for diagnosis.

## Reproduction and checks

Machine: local Windows worktree `C:/Users/neelj/nba-harness-h37` only. No network, archive, pod, benchmark, or scored comparison was used. Contract applied:
`docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q. The shorter contract path in the request does not exist in this checkout.

```text
python -m pytest tests/domains/tennis/test_live_point_probe.py -q -p no:cacheprovider
98 passed in 0.68s
python -m domains.tennis.live_point_probe --help
exit 0
python -m scripts.platformkit.tracking.contract_preflight --paths domains/tennis/live_point_probe.py domains/tennis/live_point_candidates.json tests/domains/tennis/test_live_point_probe.py docs/evidence/harness/S381_tennis_point_probe_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S381_spec.md
```

The denominator is all 98 collected construct cases in that one test file. They exercise changed/unchanged observation pairs, budgets, per-host timing, host stopping and host independence, malformed
payloads, strict counts, source and receipt timezone refusal, match isolation, duplicate permutations, privacy, summary discovery, default headers, CLI behavior, and interrupted report writes. Initial
testing found a list-traversal defect (37 passed, 11 failed); fixed. Read-only review found four defects in early host stopping, string-ID duplicate handling, blocked JSON metadata, and truncated-body
metadata; all were corrected and covered by regression tests. No whole-suite tests were run. Follow-up review found inconsistent match-identity alias normalization; fixed and tested across all seven
accepted spellings in both input permutations. Contract preflight: 9 PASS, 0 FAIL across the four owned files. All four are new, ASCII, and at most 300 lines; the module and test file have no existing
callers.

## FIX 1b

Binding inputs: the root verifier verdict and `docs/evidence/tracking/specs/S381_spec.md`, also read through `git show master:`. Neither spec copy contains an AMENDMENT block. All three BLOCKING
findings were reproduced locally before editing the module. No CORRECTION finding was listed. All examples below are generated fixtures; no response archive was opened.

1. Cross-match aggregation: the reproduction puts server/games/sets under match
   1 and pointScore under match 2, inside competitions/groupings beneath a live
   event parent. The second body changes match 2's points from 15/30 to 30/30.
   Before (exact output):
   `F1 {"overall": "QUALIFYING_SOURCE_FOUND", "records": ["POINT_LEVEL", "POINT_LEVEL"], "requests": 2}`
   After (exact output):
   `F1 {"overall": "BLOCKED", "records": ["NO_LIVE_MATCH", "NO_LIVE_MATCH"], "requests": 2}`
   `_matches` traverses event/grouping/competition containers and excludes their
   parents from qualification. A match requires exactly one valid stable ID.
   `test_live_groupings_never_combine_match_fields` exercises both match orders,
   both without and with individual live status, through two injected responses.
   `test_match_requires_stable_identity` rejects missing, boolean, and empty IDs.

2. ESPN per-set shape: the provider fixture uses
   events/groupings/competitions/competitors/linescores/value, with scores
   [6.0, 3.0] and [4.0, 2.0] in a live competition.
   Before (exact output):
   `F2 {"verdict": "ERROR", "games": false, "sets": false}`
   After (exact output):
   `F2 {"verdict": "SET_LEVEL", "games": true, "sets": true}`
   `_set_state` validates two aligned score lists, normalizes only finite exact
   integers, and derives completed-set counts within that match. Missing,
   fractional, non-finite, malformed, and unfinished-prior-set data is refused.
   `test_provider_linescores_set_level` covers integer, float, and string
   encodings through JSON transport and reversed competitor ordering. The
   provider invalid-count, nonfinite-number, completed-set, and incomplete-set
   tests cover refusal and set completion, including 6/0, 7/5, 7/6, and 8/6.

3. Incomplete challenge detection: the exact fixture is
   `<title>Security verification</title><p>Press and hold to confirm you are a human.</p>`.
   Before (exact output):
   `F3 {"requests": 2, "calls": 2, "candidate": "ERROR"}`
   After (exact output):
   `F3 {"requests": 1, "calls": 1, "candidate": "BLOCKED_BY_HOST"}`
   The pre-JSON challenge classifier now includes security-verification,
   press-and-hold, and human-confirmation signatures.
   `test_security_verification_stops_host` covers the exact page and each marker
   independently, with exactly one request in all six cases.

Validation: the first fix test run passed 90 cases; the final run passed all 98 cases (CONSTRUCT), including all 62 original cases and 36 new cases. Only
`tests/domains/tennis/test_live_point_probe.py` was run, one file at a time, with `-q -p no:cacheprovider`. The CLI `--help` exited 0. No standalone self-check command exists; the CLI zero-budget path
is covered by the existing construct self-check test. The three reproductions above were rerun after the fixes. Only the owned module, tests, and memo were edited; candidate URLs are unchanged. Empty
separator lines were removed to keep the module and tests within 300 lines. NOT VERIFIED remains the final section. Files are left on disk for lane_commit.

## FIX 1c

Binding inputs: `_verdict_s381_1c.md` and the S381 spec, including the copy read with `git show master:docs/evidence/tracking/specs/S381_spec.md`. Neither spec copy contains an AMENDMENT block. One
BLOCKING finding and two NOTE findings were listed; no CORRECTION finding was listed.

1. BLOCKING: the candidate verdict depended on the final event response.
   The minimal reproduction used a scoreboard with two discovered live IDs,
   two changed POINT_LEVEL summaries for one ID, and two NO_LIVE_MATCH
   summaries for the other. Exact failing output before changing the module:

   ```text
   point_id=1 overall=QUALIFYING_SOURCE_FOUND responses=['POINT_LEVEL', 'NO_LIVE_MATCH', 'POINT_LEVEL', 'NO_LIVE_MATCH'] summary_candidate=NO_LIVE_MATCH
   point_id=2 overall=QUALIFYING_SOURCE_FOUND responses=['NO_LIVE_MATCH', 'POINT_LEVEL', 'NO_LIVE_MATCH', 'POINT_LEVEL'] summary_candidate=POINT_LEVEL
   ```

   `probe` now aggregates candidate responses after both passes. Host stopping
   takes precedence, followed by POINT_LEVEL, then SET_LEVEL. Responses that
   are all NO_LIVE_MATCH retain that verdict; mixed ERROR/NO_LIVE_MATCH responses
   conservatively yield ERROR. Candidates without responses keep their existing
   preparation/discovery verdict. Qualification, census, and request behavior
   were unchanged. Import lines were combined to retain the 300-line limit.
   Exact output from rerunning the same reproduction after the fix:

   ```text
   point_id=1 overall=QUALIFYING_SOURCE_FOUND responses=['POINT_LEVEL', 'NO_LIVE_MATCH', 'POINT_LEVEL', 'NO_LIVE_MATCH'] summary_candidate=POINT_LEVEL
   point_id=2 overall=QUALIFYING_SOURCE_FOUND responses=['NO_LIVE_MATCH', 'POINT_LEVEL', 'NO_LIVE_MATCH', 'POINT_LEVEL'] summary_candidate=POINT_LEVEL
   Reproduction: 2 passed
   ```

   The new row-owned regression file preserves the existing 295-line test file.
   Its two-event test covers both ID assignments, both discovery orders, and
   both changed-observation orders (8 cases). Its response-permutation test
   covers 10 outcome pairs in every distinct ordering, including SET_LEVEL,
   ERROR, NO_LIVE_MATCH, and stopped-host precedence (10 collected cases).

2. NOTE: all fix-1b corrections were confirmed correct. No census, provider
   linescore, or challenge logic was changed. All existing cases still pass.
3. NOTE: the verifier lacked writable temporary storage. The permitted original
   test file now passes all 98 cases locally, including all five cases that
   write temporary files. No candidate change was needed for that note.

Validation (CONSTRUCT, this worktree only):

```text
python -m pytest tests/domains/tennis/test_live_point_probe_1c.py -q -p no:cacheprovider
18 passed in 0.41s
python -m pytest tests/domains/tennis/test_live_point_probe.py -q -p no:cacheprovider
98 passed in 0.65s
python -m domains.tennis.live_point_probe --help
exit 0
```

The denominator is all 116 collected cases across those two individually run files. The original CLI test runs the zero-budget self-check; no standalone self-check command exists. No real requests or
archived data were used. Preflight command for this fix:

```text
python -m scripts.platformkit.tracking.contract_preflight --paths domains/tennis/live_point_probe.py domains/tennis/live_point_candidates.json tests/domains/tennis/test_live_point_probe.py tests/domains/tennis/test_live_point_probe_1c.py docs/evidence/harness/S381_tennis_point_probe_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S381_spec.md
9 PASS, 0 FAIL
```

## FIX 1d

Binding inputs: `_verdict_s381_1d.md` and both local and `git show master:` copies of the S381 spec; neither has amendments. One BLOCKING finding, no CORRECTION. All checks used constructed fixtures
in this worktree, with writable local temp.

1. BLOCKING: mixed NO_LIVE_MATCH/ERROR must preserve the valid observation.
   `probe` now uses the exact precedence BLOCKED_BY_HOST, POINT_LEVEL, SET_LEVEL,
   NO_LIVE_MATCH, ERROR. This supersedes the mixed-response rule in FIX 1c.
   Updated `test_candidate_response_permutations` to require NO_LIVE_MATCH in
   both permutations. Before the module fix: `1 failed, 17 passed in 0.84s`,
   with `AssertionError: assert 'ERROR' == 'NO_LIVE_MATCH'`.
   Exact minimal reproduction output before and after the module fix:

   ```text
   Input [NO_LIVE_MATCH, ERROR] -> candidate=ERROR; expected=NO_LIVE_MATCH; FAIL
   Input [ERROR, NO_LIVE_MATCH] -> candidate=ERROR; expected=NO_LIVE_MATCH; FAIL
   Input [NO_LIVE_MATCH, ERROR] -> candidate=NO_LIVE_MATCH; expected=NO_LIVE_MATCH; PASS
   Input [ERROR, NO_LIVE_MATCH] -> candidate=NO_LIVE_MATCH; expected=NO_LIVE_MATCH; PASS
   ```

2. NOTE: event ordering and changed-observation qualification were confirmed;
   their logic is unchanged and the existing regression cases pass.
3. NOTE: budget, spacing, host stops, privacy, and default opener were confirmed;
   their logic is unchanged and the original construct tests pass.
4. NOTE: the verifier had no writable temp directory. Both per-file commands
   listed in FIX 1c now pass locally, including filesystem-writing cases.

Validation: regression file 18 passed in 0.38s; original file 98 passed in 0.66s (116 collected CONSTRUCT cases, run separately with `-q -p no:cacheprovider`). Minimal reproduction: 2/2 passed. CLI
`--help`: exit 0. The original CLI test passes the zero-budget self-check; no standalone self-check command exists. Contract preflight: 9 PASS, 0 FAIL with the five-path command in FIX 1c, excluding
verdicts.

## FIX 1e

Binding inputs: `_verdict_s381_1e.md` and both local and `git show master:` S381 spec copies; neither contains amendments. Construct fixtures only.

1. BLOCKING: changed only the production reducer's tuple to POINT_LEVEL, SET_LEVEL, NO_LIVE_MATCH, BLOCKED_BY_HOST, ERROR. This supersedes FIX 1c/1d precedence.
   Direct production-reducer reproduction before the module fix (exact output):

   ```text
   [POINT_LEVEL, BLOCKED_BY_HOST] -> BLOCKED_BY_HOST; expected POINT_LEVEL; FAIL
   [SET_LEVEL, BLOCKED_BY_HOST] -> BLOCKED_BY_HOST; expected SET_LEVEL; FAIL
   [NO_LIVE_MATCH, BLOCKED_BY_HOST] -> BLOCKED_BY_HOST; expected NO_LIVE_MATCH; FAIL
   Reducer ordered pairs: 14 passed, 6 failed
   ```

   Reversed pairs also failed. After the fix (exact output; reversed pairs also pass):

   ```text
   [POINT_LEVEL, BLOCKED_BY_HOST] -> POINT_LEVEL; expected POINT_LEVEL; PASS
   [SET_LEVEL, BLOCKED_BY_HOST] -> SET_LEVEL; expected SET_LEVEL; PASS
   [NO_LIVE_MATCH, BLOCKED_BY_HOST] -> NO_LIVE_MATCH; expected NO_LIVE_MATCH; PASS
   Reducer ordered pairs: 20 passed, 0 failed
   ```

   `test_candidate_response_permutations` executes the production reducer AST directly so host stops cannot discard observations. All 20 distinct ordered pairs and five identical pairs run with initial ERROR and BLOCKED_BY_HOST: 50 reductions. The eight event permutation cases remain unchanged.
   Before the module fix: `12 failed, 11 passed in 0.94s`; example: `AssertionError: assert 'BLOCKED_BY_HOST' == 'POINT_LEVEL'`. After: `23 passed in 0.46s`.
2. CORRECTION: `git status --porcelain -uall -- pytest-of-neelj/` reproduced the eight reported files: `Incidental pytest files: 8; expected 0; FAIL`. Removed only those files; the same check then gave `Incidental pytest files: 0; expected 0; PASS`.
   TEMP/TMP used worktree-local `.pytest-s381-1e`; generated files there were also removed after validation. Final status contains exactly the five owned files. No regression test was requested for this cleanup.
3. NOTE: confirmed request, timing, host-stop, privacy, header, census and qualification behavior is unchanged. The original test file is unchanged.

Validation: the two per-file commands in FIX 1c ran separately with `-q -p no:cacheprovider`: regression file 23 passed; original file 98 passed in 0.64s; total 121 collected CONSTRUCT cases. Direct
reproduction: 20/20 passed. CLI `--help`: exit 0. Explicit CLI self-check: `python -m domains.tennis.live_point_probe --candidates domains/tennis/live_point_candidates.json --out
.pytest-s381-1e/self-check.json --max-requests 0`. Exact output: `Zero-budget self-check: 1 passed; requests=0; verdict=BLOCKED`. No standalone self-check option exists. Reuse the five-path preflight
command in FIX 1c, excluding verifier files. Older prose is reflowed only to retain the 300-line limit.

Final contract preflight: 9 PASS, 0 FAIL over all five owned paths; status lists exactly those five new files. All five are ASCII and at most 300 lines. Files remain on disk for lane_commit.

## NOT VERIFIED

- Real provider availability, rate limits, access policies, response schemas,
  and actual point-state coverage; no source verdict was measured here.
- Challenge detection beyond the explicit marker list, including unfamiliar
  HTML or script-only challenges. No scripts or challenges are executed.
- Schema variants beyond the supported recursive keys and live status shape;
  alternate provider representations can yield conservative ERROR or BLOCKED.
- Full-body metadata for oversized or interrupted responses; these are explicit
  refusals with unknown full length/hash.
- Source-time freshness, historical as-of recovery, timestamp ordering, and
  sub-microsecond cutoff comparisons; this probe implements none of these.
- Real wall-clock drift, filesystem power loss, or external concurrent writers;
  timing and write-failure tests use virtual clocks and injected failures.
- Actual network redirect behavior; the redirect handler is construct-tested.
- Integration with the recursion model, deployment, and the orchestrator's
  main-tree run or ledger entry. No commit was created in this sandbox.
