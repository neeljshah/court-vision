# S488 night output replacement retry

Candidate built: 6/6 construct cases completed; preflight 9/9. Known intermittent
unchanged-test compatibility issue disclosed below. Local Windows constructs only.
Worktree: C:/Users/neelj/nba-harness-h137. No deployment or external inputs.
Pinned baseline: 2ab9640cbc52bfcc0842dc7b020216d93edf6b06.

## Binding before-condition
Fresh AST/source probe, before editing, printed:
```text
SIGNATURE: def atomic(self, path: Path, value: dict, source: str) -> None:
WINERROR_FILTER: False
RETRY_HANDLER: (OSError, ValueError, TypeError), PermissionError, (OSError, ValueError, TypeError)
REPLACE_RETRY_ATTEMPTS = 5
REPLACE_RETRY_DELAY_SEC = 0.1
NIGHT_BARE_REPLACE: True
NIGHT_IMPORTS_WRITER: False
```
The referenced scripts/platformkit/ingame/local_capture_writer.py counts
atomic_replace_retry before each sleep; source-specific write errors, exhausted
atomic_replace_refused, and failed-removal atomic_replace_cleanup_errors.
It retries every PermissionError, including WinError 32 and 5, without filtering.
Its serializer is inseparable from its retry method. The separately landed,
serialization-independent helper was found in scripts/platformkit/ops/atomic_replace.py.
The additional pre-edit probe printed:
```text
BOUNDS: 5 attempts, at most 4 sleeps of 0.1 seconds
FILTER: all PermissionError; caller must restrict winerror
COUNTS: on_retry once before each sleep; on_cleanup_error on failed exhausted-temp removal
NIGHT: final os.replace(temporary, a.out), no helper import
```
The helper has no counters of its own; callbacks supply them. Exhaustion with
its default durable=True removes the stage if possible and re-raises the
PermissionError. Other exceptions propagate without retry.

## Read-before-code signatures
The landed helper and imported scoreboard/amendment modules were read before coding.
Exact relied-on signatures (line wrapping only):
```python
def replace_with_retry(temporary: Path, target: Path, *, durable: bool = True,
                        on_cleanup_error: Callable[[OSError], None] | None = None,
                        on_retry: Callable[[], None] | None = None) -> bool:
def run(books_root: Path, state_root: Path, schedule: Path, day: str, sports: list,
        prereg: Path, history: list = (), as_of: str | None = None, arms: tuple = ('A', 'B', 'C', 'D'), model_optional=frozenset()) -> dict:
def _json(value: object) -> str:
def main(argv: list[str] | None = None, *, root: Path = ROOT,
         git_head: Callable = _git_head, git_commit_time: Callable = _git_commit_time) -> int:
def verify_amendment(path: Path, day: str, *, root: Path = ROOT,
                     git_head: Callable = _git_head, git_commit_time: Callable = _git_commit_time) -> frozenset:
```

## Implementation and evidence
Only the owned night module's publication site and imports change. The existing
helper retains its bounds. Its callback runs inside the PermissionError handler;
sys.exc_info obtains that exception and re-raises it immediately unless winerror
is 32 or 5. This intentionally uses the helper's current uncaught-callback
behavior to narrow its broader exception policy; it adds no retry loop.

The report field is counts.atomic_replace_retry, incremented once per accepted
retry. A fresh staged receipt contains the updated count before the next attempt.
PendingReceipt implements os.PathLike so the helper follows the current stage.
The first stage keeps exactly the old serializer and newline. Zero retries adds
no fields. A prior complete stage survives until its replacement is fsynced. Source-stage
cleanup failures increment in-memory counts.atomic_replace_cleanup_errors; any
subsequent retry serializes that count. A locked leftover remains recoverable. A failure retains the prior destination.
A cleanup failure after the last stage was serialized is not included in that
published receipt; it remains counted in memory. The helper's exhaustion cleanup
also counts failures in the in-memory result;
no new destination receipt is claimed on exhaustion.

The spec supplies no REAL ROW. Tests construct an empty schedule and missing
shards under pytest's temporary directory. Case 1 runs the full night entry point
and real scorer twice, first using the module loaded from the pinned git blob,
then the candidate, asserting identical bytes. Only the policy-seal reader is
substituted with pinned committed content. No moving ref is queried by new tests.
The identity test compares six S475 implementation files and all three SEALS
artifacts against the pinned commit; it checks the table and calls the real
verify_amendment for 2026-09-30 using pinned bytes and commit-time lookup.
The existing paper_night_steps reader accepts additive strict-integer counts.

Construct case mapping: 1 byte parity; 2 two locks then success (32 and 5);
3 exhausted bound with original exception and previous receipt; 4 other or absent
winerror immediately propagates; 5 other OSError immediately propagates;
6 thirty consecutive per-file paper-night suite invocations (results below).
Additional tests cover a still-locked source stage, cleanup failure, and failed
stage fsync with and without a prior destination receipt. No new JSON seal or fixture paths: .gitattributes patterns = none.

## Verification results
All pytest invocations use python -m pytest <one file> -q -p no:cacheprovider.
- New test_ingame_scoreboard_night_replace.py: 13 passed.
- Unchanged test_ingame_scoreboard_night.py: 31 passed.
- Unchanged test_ingame_scoreboard_night_table.py: 104 passed.
- Unchanged test_ingame_scoreboard_night_e2e.py: initially 8 passed; final
  rerun 7 passed / 1 failed, then immediate unchanged rerun 8 passed (see below).
- Initial paper-night repetition: runs 1-7 each passed 14 tests; run 8 had
  13 passed, 1 failed in test_injected_five_step_list_is_count_agnostic:
  expected code == 0, observed code == 3. This test uses fake children; the
  failure cause was not established. No unrelated files were changed.
- Paper-night second block: runs 1-30 each passed 14 tests, exit 0.
- Additional final-candidate block: runs 1-12 each passed 14 tests, exit 0.
  Conservatively discard second-block runs 1-12 because the last durability
  edit happened during that block. Runs 13-30 plus the additional 12 establish
  30 consecutive invocations on final code, each 14/14: 420 passed, 0 failed.
- Night and table suites were rerun after those invocations: 31 and 104 passed.
- The end-to-end rerun failure was test_01_real_row_amendment_fresh_process.
  Its construct receipt contained counts.atomic_replace_retry = 1. The real
  child returned 0 and published the receipt; the test compares its counts
  against a scorer-only report that cannot include the required new retry
  counter. An immediate unchanged per-file rerun passed all 8 tests. This is
  an intermittent compatibility gap in an unowned test, not a hidden pass.
  The failed construct's complete counts were:
  {"atomic_replace_retry": 1, "model_not_reconstructible:B_lag": 2,
   "model_not_reconstructible:D": 2, "served_games": 2,
   "training_duplicate": 0, "unsettled_games": 2}.
- python -m scripts.platformkit.execution.ingame_scoreboard_night --help: exit 0.
- Contract preflight: 9/9 passed over all three owned files.
- Owned Python line counts: night module 196; new tests 230. ASCII, LF only.

## Follow-up bare replacement sites
Unmodified, outside this row: scripts/platformkit/execution/paper_night.py:67,
scripts/platformkit/execution/fill_realism_io.py:80,
scripts/platformkit/ops/forward_week_report.py (atomic writer), and
scripts/platformkit/execution/ingame_scoreboard.py (final publication).

- ORCHESTRATOR LANDING EDIT (AMENDMENT 1): test_ingame_scoreboard_night_e2e.py compares through _env_free (retry counters removed after an int 0..4 assert); 3 of 3 runs pass.

## NOT VERIFIED
The source of the spontaneous eligible PermissionError in the end-to-end run
was not determined; antivirus attribution and controlled native handle
contention were not tested. Deterministic lock cases use injected failures. No real archive, network, pod, production night,
or deployment was exercised. The initial fake-child repetition failure was
not diagnosed. The unchanged end-to-end equality assertion can fail when the
required retry counter appears; this unowned test was not changed. Independent verifier acceptance and lane_commit remain pending.
