# S359 four-arm charged-trial runner -- 2026-09-21

PREPARE ONLY. Four new files after FIX 1e; no real trial or real-corpus loss computed.
Vocabulary follows contract Q6; automated scan required.

Machine: local Windows worktree C:/Users/neelj/nba-harness-h17, for source
inspection and synthetic tests only. The pod is OFF.
Authority: docs/evidence/tracking/specs/S359_spec.md and
docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.

Before-condition reproduced before creating the runner:

```text
ls scripts/platformkit/ingame/s359_four_arm_trial.py
Cannot find path ... because it does not exist.
```

The required Python SHA-256 recomputation over the LF-normalized prefix printed
`True`. The authority seal is
`18b45d85983ab60af438acb066ce4940213ece8652538e464004a7cda750361f`.

Implementation: scripts/platformkit/ingame/s359_four_arm_trial.py imports the
landed scorer's validate_inputs, predict_rows and summarize entry points through
its module, and imports baseline_four_arm_eligibility.load_corpus for the census.
Validation runs before loading the census; the scorer owns seal and committed-file
checks. The authority seal and canonical manifest digest must match the sealed
pins. MLB games, raw ticks, eligible ticks, state-transition ticks, fold count,
warm-up count and first-tick date bounds are checked before any charge.

The runner rejects occupied output directories and reserves each attempt before
charging. A separate S359 lock serializes attempt counting around the sanctioned
backtest_runner._charge_ledger call. At most two S359 charges are permitted per
ledger; the second requires --attempt 2. The attempt is recorded in attempt.json,
charge.json and trial_summary.json. Failed scoring is recorded in failure.json;
a failed second attempt is CLOSED AT LIMIT. A partial charged attempt cannot
reuse its directory. Failed charge-artifact persistence never reaches scoring.

charge.json contains the returned ledger row and its launch K before predict_rows
runs. Later unrelated charges cannot change that reported K. The hypothesis hash
uses LF-normalized sealed prereg bytes followed by the ASCII canonical manifest digest.
The loader's raw manifest digest is retained in summary.json provenance; the
canonical digest is recorded in trial_summary.json. The family is reported as
`ingame_four_arm_mlb_r3 (NOT frozen; family of one)`.

paired_rows.json and summary.json preserve the scorer's complete MLB outputs.
The trial summary copies each cell verdict without changing its value, and copies
the sealed scope statement verbatim. Scorer commit 531f0525d is the sealed source
pin. No estimation bar, seed, fitting rule or threshold is reimplemented.
The scorer retains responsibility for walk_forward, purging and embargo.

Soccer requires its sealed revision-3 manifest and census counts. It never reads
or charges the ledger. Its output replaces decision fields with
UNDERPOWERED-DESCRIPTIVE status in every cell, including empty phase cells;
the CLI emits only that descriptive label.

Tests: tests/platformkit/ingame/test_s359_four_arm_trial.py uses tmp_path for
all corpora, output directories and ledgers. Synthetic JSONL files pass through
the landed loader. Boundary tests inject frozen census metadata and synthetic
pins; committed-file status is mocked, while seal verification is real. A separate
test keeps the actual tiny census and proves it refuses before a charge.
Scoring is stubbed to test ordering and exact verdict copying without losses.
The ordering test appends an unrelated temporary-ledger charge inside the scorer
stub and checks that the reported K remains the launch value.

Authorized validation commands:

```text
python -m pytest tests/platformkit/ingame/test_s359_four_arm_trial.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.s359_four_arm_trial --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/s359_four_arm_trial.py tests/platformkit/ingame/test_s359_four_arm_trial.py docs/evidence/harness/S359_four_arm_trial_runner_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S359_spec.md
```

Validation results: 24 passed in 2.65s; --help exited 0. Contract preflight
passed all nine checks over the three new files, including the automated Q6
scan. The per-file test also verified ASCII, the runner's 250-line cap, the
other files' 300-line caps and byte-identical scope text from the authority.
Preflight identified all three files as untracked. No pre-existing module was
edited. No real corpus or real ledger was opened by this lane.

Finisher command for the real run, recorded here and NEVER executed by this lane:

```text
python -m scripts.platformkit.ingame.s359_four_arm_trial --corpus-dir data/cache/ingame_grade_joined/mlb_segmented_r3 --manifest <canonical manifest path> --prereg docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md --out <dir>
```

The finisher supplies the canonical compact per-file manifest and a fresh output
directory in the authorized checkout. The CLI uses the sanctioned canonical
ledger path; it has no alternate-ledger CLI flag. An explicitly authorized second
attempt adds --attempt 2 and uses a fresh output directory.

## FIX 1b

AMENDMENT 1: the runner reuses backtest_runner.assert_canonical_ledger with
allow_noncanonical=False and resolves canonical_ledger_path(). Relative, absent,
empty, invalid and noncanonical ledgers refuse before reservation. Prior rows
require positive integer K and nonempty base-schema strings. The absolute path
and prior maximum are printed and persisted; returned charge K alone is reported.
The keyword-only test opt-out stamps TEST LEDGER in every artifact; the CLI
exposes no opt-out. Required tests cover all five refusal cases, stamps, launch
K and both forbidden CLI spellings. Original census, validation, attempts,
soccer behavior and verbatim verdicts remain. No real corpus or ledger was opened.
FIX 1b: 32 passed; --help exited 0; all nine preflight checks passed over three
files. ASCII and 250-line runner / 300-line other caps passed. No commit created.

## FIX 1c

Finding 1 (BLOCKING): equality accepted float census counts and non-integer
attempt values. The runner now requires `type(attempt) is int` before census,
and strict integer types for every frozen scalar census count before comparing
the frozen values. First-tick date histogram counts also require strict integers.
Fold cardinality remains derived with len(). No counts are coerced.

Minimal reproduction used an in-memory MLB census with all five frozen scalar
counts converted to float. The attempt probe mocked seal validation and prereg
bytes, then installed a RuntimeError("census sentinel") loader. No input files,
real ledger or corpus were opened by the probe. Before the runner edit:

```text
float census output=accepted
attempt=1.0 output=census sentinel
attempt=2.0 output=census sentinel
attempt=True output=census sentinel
attempt=False output=attempt must be 1 or explicit --attempt 2 for MLB
```

The identical probe after the runner edit:

```text
float census output=refused: sealed census counts must be integers
attempt=1.0 output=attempt must be an integer
attempt=2.0 output=attempt must be an integer
attempt=True output=attempt must be an integer
attempt=False output=attempt must be an integer
```

Regression test: test_strict_integer_counts_before_reservation_or_charge in
tests/platformkit/ingame/test_s359_four_arm_trial.py enumerates n = 28 (CONSTRUCT):
float / True / False for five MLB counts, one date histogram count and two
soccer counts, plus attempts 1.0 / 2.0 / True / False. Reservation and charge
are failure sentinels; invalid attempts also install a census failure sentinel.
Every case checks that neither an output directory nor a ledger was created.
The authorized per-file command before the runner edit reported:

```text
E   Failed: reservation or charge reached
28 failed, 32 passed in 3.30s
```

Some boolean cases already refused by value; the new test additionally requires
an explicit integer-type refusal before equality. After the runner edit:

```text
60 passed in 2.03s
```

Finding 2 (NOTE): the earlier verifier could not create temporary fixtures.
This lane reran the authorized per-file command with TEMP and TMP set to this
writable worktree, and PYTHONDONTWRITEBYTECODE=1. All 60 cases executed.
This does not establish execution in the separate read-only verifier environment.

Findings 3 and 4 (NOTE, no fix requested): canonical-ledger guards, artifact
stamps, launch K, seal ordering, charge ordering, attempt limits, soccer output
sanitization and verbatim MLB verdict extraction retain their existing code.
The original 32 tests pass alongside the 28 new regression cases.

The authorized --help command exited 0. No self-check CLI option exists; the
per-file tests exercise the row's checks. Only the runner, its test and this
memo were edited for FIX 1c. The spec and verifier verdict were not edited.
Contract preflight passed all nine checks over the three row-owned files.
The existing NOT VERIFIED limitations below still apply.

## FIX 1d

Finding 1 (BLOCKING): the manifest pin was checked after corpus loading.
The minimal reproduction is test_manifest_pin_stops_before_charge: install a
wrong manifest pin and a loader that raises if reached. Before the runner fix:

```text
E   RuntimeError: CENSUS_REACHED_BEFORE_MANIFEST_PIN
2 failed, 58 passed in 2.93s
```

The other failure was the test file temporarily exceeding the 300-line limit.
The runner now verifies the canonical JSON manifest digest against the sealed
pin before any corpus load. After census validation it rereads the manifest,
compares the bytes with the initially pinned bytes, and checks the loader's raw
manifest digest. Either mutation refuses before reservation or charge.

Self-audit moved existing canonical-path and output/attempt guards before the
census, retaining the attempt lock through census, reservation and charge.
The single test_launch_order_and_k_snapshot records these stages into a list:
1. Scorer-owned sealed prereg SHA-256 and committed-file validation.
2. Canonical manifest digest against the pin, before any corpus parsing.
3. The sanctioned canonical-ledger path guard.
4. Output-directory and attempt guards, including prior ledger rows.
5. load_corpus and the frozen census denominator checks.
6. Manifest reread and mutation guard.
7. backtest_runner._charge_ledger and its launch K.
8. charge.json persistence.
9. Prediction, followed by the metric stub.

n = 12 (CONSTRUCT): one complete launch, failures injected at all nine stages,
changed manifest bytes at reread, and an inconsistent loader manifest digest.
Each failure asserts the exact reached prefix; all later stages are absent.
The successful list is [1, 2, 3, 4, 5, 6, 7, 8, 9]. The metric stub also checks
that full list. A later unrelated temporary charge leaves the reported launch
K unchanged. Canonical helpers are redirected to a synthetic temporary ledger.
No real corpus, metric or ledger is used.

Finding 2 (CORRECTION): git status reproduced `?? pytest-of-neelj/` alongside
the three candidate files. The explicit FIX 1d orchestrator instruction overrides
the verdict's deletion request: leave this uncommitted sandbox scratch alone.
The candidate is exactly these three paths, for explicit lane_commit pathspecs:
- scripts/platformkit/ingame/s359_four_arm_trial.py
- tests/platformkit/ingame/test_s359_four_arm_trial.py
- docs/evidence/harness/S359_four_arm_trial_runner_2026-09-21.md
The pre-existing spec modification and scratch directory are outside the candidate.

Findings 3 and 4 (NOTE): strict typing and all confirmed validation, charging,
launch-K, output and attempt behavior are retained. Only their launch placement
changed as required above. Test formatting was compacted to retain all boundary
cases within the file limit. The wrong-pin regression now passes.

FIX 1d per-file validation: 71 passed, including all failure prefixes.
The row's --help exited 0; there is no self-check CLI option.
Contract preflight passed all nine checks over exactly the three candidate paths.
TEMP and TMP point into this worktree; PYTHONDONTWRITEBYTECODE=1.
The existing NOT VERIFIED limitations below remain binding.

## FIX 1e

Finding 1 (BLOCKING), reproduced from the committed prereg without a corpus:
```text
CRLF_count=204
current_hash=aa245584a655f33b63baa020c4d5485afbeed5222bdedf22a9b7d7ed9d7ed395
committed_hash=fbc3c37b9d76cc3355ad7cecf4de0b80ea1bc5305f97eb46f4a7de807933f19f
LF_normalized_hash=fbc3c37b9d76cc3355ad7cecf4de0b80ea1bc5305f97eb46f4a7de807933f19f
worktree_equals_committed=False
LF_normalized_equals_committed=True
```
The runner snapshots prereg bytes before scorer validation and compares an exact
reread afterward. Content or newline mutation refuses before manifest reads,
census, reservation or charge. The snapshot then uses the scorer's exact
CRLF-to-LF normalization for the hypothesis hash. Scorer validation is reused.

New tests: tests/platformkit/ingame/test_s359_checkout_identity.py. The identity
case runs the same constructed prereg and multiline manifest as LF and CRLF,
using separate temporary ledgers. It expects the LF hypothesis hash in both the
charge row and summary, and byte-identical hypothesis_hash, prereg_sha256,
manifest_digest and scorer_commit. Two mutation cases install failure sentinels
for loading, reservation and charging. The fourth case checks ASCII and LOC.
Before the module fix the exact per-file command produced:
```text
E   AssertionError: assert 'e9798b8c2a6c...c427e6a721210' == '409f58db5f23...eff785acd69db'
E   Failed: launch reached
3 failed, 1 passed in 2.29s
```
After the module fix: `4 passed in 1.53s`.

Identity self-audit: validate_inputs already hashes the LF-normalized prereg
prefix and checks its seal; the runner checks it against PREREG_SEAL. The manifest
digest already hashes sorted compact JSON, independent of checkout newlines.
scorer_commit is the sealed Git object ID 531f0525d, never a checkout file hash.
charge.json's nested row contains only hypothesis_hash and prereg_sha256
identities; trial_summary.json adds the canonical manifest digest and scorer ID.
None uses raw checkout bytes after this fix. The loader's raw manifest/source
fingerprints in summary.json are transport checks, retained unchanged.

Finding 2 (NOTE): no fix requested. The original test file, including all nine
launch stages and failure prefixes, is unchanged: `71 passed in 2.46s`.
Finding 3 (CORRECTION): the verifier reported "no writable temporary directory
exists". This environment did not reproduce that setup failure: before edits,
the exact original per-file command returned `71 passed in 2.26s`. Both test files
used TEMP and TMP set to this worktree and PYTHONDONTWRITEBYTECODE=1. This verifies
execution here, not in the separate restricted verifier process.

Commands (one file per pytest invocation):
```text
python -m pytest tests/platformkit/ingame/test_s359_checkout_identity.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_s359_four_arm_trial.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.s359_four_arm_trial --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/s359_four_arm_trial.py tests/platformkit/ingame/test_s359_four_arm_trial.py tests/platformkit/ingame/test_s359_checkout_identity.py docs/evidence/harness/S359_four_arm_trial_runner_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S359_spec.md
```
--help exited 0; no self-check CLI option exists. Preflight passed all nine checks.
The candidate adds the new regression file to the original three explicit paths.
Only the row-owned runner and memo were edited; the fourth file is new.
The spec, verdict, existing test file and other modules remain unchanged.

## NOT VERIFIED

- Real corpus availability, hashes, census, losses, verdicts and replication.
- Real ledger contents, launch K, charge persistence or available attempt count.
- Actual committed-file validation in the finisher checkout; tests mock git status.
- Installed scorer bytes against the sealed scorer commit; the recorded commit is
  the preregistration's source pin, not a fresh git measurement.
- Live model input freshness at capture time, as excluded by the sealed authority.
- Cross-process concurrency on the target machine; the shared lock is reused.
- Finisher execution, production behavior, deployment and a lane commit.
