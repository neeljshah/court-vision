# S394 NBA trial runner

PREPARE candidate; local construct checks pass. Independent acceptance pending.

## Binding before-condition

The exact binding command `ls scripts/platformkit/ingame/nba_four_arm_trial.py`
exited 1 before creating the runner (the equivalent `Get-Item` also exited 1):

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h53\scripts\platformkit\ingame\nba_four_arm_trial.py' because it
does not exist.
```

The S394 spec was the first file read. Required landed sources were read;
`git diff master --` for S359, the scorer, period cells and backtest runner
was empty. S382 was read as documentary input only. No REAL ROW is given by
S394; the first test consumes a wholly synthetic corpus end to end.

## Exact landed signatures read before coding

```python
def validate_inputs(corpus_dir: Path, manifest: Path, prereg: Path | None,
                    *, census_only: bool = False, loaded: tuple | None = None) -> dict:
def git_committed(prereg: Path) -> bool:
def predict_rows(rows: list[dict], corpus: str) -> list[dict]:
def summarize(predictions: list[dict]) -> dict:
def _atomic_json(path: Path, value: object) -> None:
def load_corpus(corpus_dir: Path, manifest: Path) -> tuple[list[dict], dict, dict]:
def select_rows(rows: list[dict], corpus: str) -> tuple[list[dict], dict]:
def stratified_cells(rows: list[dict], periods: tuple = PERIODS) -> dict:
def canonical_ledger_path() -> Path:
def assert_canonical_ledger(ledger_path: Path, allow_noncanonical: bool) -> bool:
def _charge_ledger(path: Path, spec: str, sport: str, start: str, end: str, *,
                   family: str | None = None, hypothesis_hash: str | None = None,
                   tier: str | None = None, prereg_sha256: str | None = None,
                   trial_prereg_sha256: str | None = None) -> dict:
def load_fwer(path) -> List[dict]:
def ledger_lock(path: Optional[Path] = None, *,
                required: bool = True) -> Iterator[None]:
```

Sources: `scripts/platformkit/ingame/baseline_four_arm.py`,
`scripts/platformkit/ingame/baseline_four_arm_eligibility.py`,
`scripts/platformkit/ingame/baseline_four_arm_period.py`,
`scripts/platformkit/eval_gate/backtest_runner.py`,
`scripts/platformkit/eval_gate/ledger.py`, `scripts/platformkit/clv_ledger_io.py`.
S359 supplies the launch sequence and Python-only test hook. S387's
`d_eligible`, `d_subset`, and `d_subset_warmup_keys` remain intact.
S383's CLI exposes values only with `--show-values`; this runner writes values
to artifacts and prints accounting only. Vocabulary follows contract Q6.

## Prepared behavior

Only the four spec-owned new files changed. No existing module was edited.
Nine launch boundaries: committed normalized seal, manifest pin, canonical
ledger, output/attempt checks, census, authority re-read, shared charge with
launch K, durable charge.json, prediction. Every injected failure stops later
steps. The Python test hook is the S359 spelling; the CLI has no opt-out.
Absent, empty, duplicate-field, duplicate-count and unterminated ledgers refuse.
Tier comes from the sealed declaration. Family is `ingame_four_arm_nba_r1`.
Hypothesis hashing uses LF-normalized prereg content and canonical manifest
JSON; paths and checkout line endings cannot change it.

The future sealed document must contain exactly one `NBA_TRIAL_JSON: ` line
followed by a JSON object. Required fields are `family`, `tier` (T2 or T3),
`corpus` (nba_checkpoints_r1), `manifest_sha256` (complete canonical digest),
`primary_game_ids` (explicit unique identities), `census` and `primary_census`.
Both census objects contain every field in the guard's `COUNTS` and
`HISTOGRAMS` constants plus complete `folds` records with `date`, `train_games`,
`train_ticks` and boolean `warmup`. Every count is a nonnegative strict int.
The first-tick date endpoints supply the ledger date range. This is an input
format for a future seal; the lane did not alter or seal the S382 draft.
The orchestrator must reconcile all S382 pre-seal decisions before committing
that authority, including exposure identities and provenance clearance.

Full-corpus paired_rows.json and summary.json preserve the S359 structures.
TEST mode stamps each JSON artifact; paired lists use the same TEST wrapper.
Primary population rows are selected by sealed IDs before recomputing the
scorer's folds and training populations. primary_paired_rows.json archives
these independently reconstructible losses. No full-population training game
is silently inserted into the restricted primary. The period helper receives
the whole primary population after both saved scorer artifacts are written and
makes the warm-up split itself, so its census is complete (see FIX 1c).
primary.json exposes C-minus-A Brier, companion log-loss, four period means
and supports, whole-game counts, retained/discarded draws, interval and verdict.
trial_summary.json starts with primary_verdict. Other comparisons are SECONDARY;
D uses the landed paired subset and is explicitly DESCRIPTIVE. The full
population is separately descriptive. No secondary replaces the primary.

JSON writes use the row's own insertion-order writer (see FIX 1b): flush and
os.fsync into a temporary file, then os.replace, and never sort_keys.
A durable ledger_before.jsonl snapshot precedes the shared charge helper;
the appended ledger is synchronized even when the helper raises. A failed
append leaves an occupied attempt and counted CHARGE_INCOMPLETE artifact.
Recovery is manual: preserve complete later charges and inspect any torn tail
against the snapshot. Never blindly restore the snapshot over concurrent work.

## Construct validation

The first test runs constructed ticks across three games through the actual
loader, scorer and period implementation, with one missing D value (the counts
in this paragraph are PRE-FIX 1c; see FIX 1c for the current construct). Twelve
ticks, four warm-up, eight ABC and seven D. It checks arithmetic against
saved losses and both row permutations. A second end-to-end case excludes one
game and proves folds and training IDs are recomputed for the frozen primary.
No measured corpus statistic or calibration conclusion is reported.
Other cases cover all nine failure boundaries, actual S382 draft refusal,
invalid/uncommitted seals, pins, census/mutation mismatches, attempt ceilings,
strict counts, large exact K, line-ending identity, duplicate authorities,
partial writes and atomic replacement failure. The final launch-K test inserts
an unrelated charge before our append and another after prediction begins.

Commands (local Windows worktree; no full suite):

```text
python -m pytest tests/platformkit/ingame/test_nba_four_arm_trial.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.nba_four_arm_trial --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/nba_four_arm_trial.py scripts/platformkit/ingame/nba_four_arm_trial_guards.py tests/platformkit/ingame/test_nba_four_arm_trial.py docs/evidence/harness/S394_nba_trial_runner_2026-09-22.md --base master --spec docs/evidence/tracking/specs/S394_spec.md
```

Per-file result, PRE-FIX 1c and superseded by the FIX 1c section: 77 passed in
24.75s. Earlier development runs passed 68, 72 and 73 cases. CLI --help exited 0.
Contract preflight: 9 PASS, 0 FAIL. ASCII decoding succeeded for all four files.
Line counts using len(text.splitlines()), PRE-FIX 1b and superseded twice
(see FIX 1b and FIX 1c): runner 156, guards 211, tests 299, memo 140. No helper
CLI is defined. The one test file covers both new modules.
The read-only review identified and the lane corrected changed summary shape,
unterminated ledger append, duplicate ledger fields and uncounted parse failures.
The fixes are covered by the final construct run; independent acceptance is
still pending. Git status listed only the four owned untracked files.

## FIX 1b

Round 1 of independent verification returned REJECT with two BLOCKING findings.
Both were reproduced before any edit and both now pass. The verifier could not
run the per-file test at all (its sandbox had no writable temporary directory,
so all 77 cases failed in setup); this lane ran it, 77 passed before and after.

Finding 1, trial_summary.json must carry primary_verdict first on disk. The
stated mechanism did not reproduce as written: the verifier attributed
sort_keys=True to baseline_four_arm._atomic_json, which this row imported, but
that landed writer does not sort. Writing the summary through it put
primary_verdict first already. The sibling module baseline_four_arm_period
DOES canonicalize with sort_keys=True at its own _atomic_json, so the ordering
the spec requires was inherited by accident from an unowned private helper and
was never asserted on the saved artifact: the test compared the returned dict
with == , which ignores key order. The finding is therefore accepted as a real
defect in its substance. nba_four_arm_trial_guards.write no longer calls
scorer._atomic_json; it serializes with sort_keys=False and routes the ASCII
bytes through the row's own snapshot helper, which already wrote a temporary
file, flushed it, fsynced it and os.replace'd it into position, so no second
atomic writer was added. Emulating the sorting sibling by flipping the new
writer to sort_keys=True makes the saved first key 'attempt' and fails the new
assertion; with sort_keys=False the saved first key is 'primary_verdict'.

Finding 2, secondary game_first results embedded unlabelled in the primary
Brier and log-loss cells. This reproduced exactly as stated: feeding _primary a
cells object whose C_brier.game_first is {"verdict": "UNDERPOWERED"} produced
primary["brier"]["game_first"] with no label, while only the copy under
secondaries carried label SECONDARY. A new _cell helper drops game_first from
both embedded primary cells, so only the explicitly labelled copies under
secondaries survive. Note that the landed stratified_cells already sets
label SECONDARY inside game_first, so on the real path the embedded copy was
labelled; the defect that remains on every path is structural, a secondary
result nested inside the primary cell and duplicating the labelled copy.

Regression tests were added to the end-to-end construct test rather than to a
new test function, so the existing launched fixture is reused and the file
stays within the 300-line rail. They assert the first key of the SAVED
trial_summary.json, walk every dictionary under both secondaries subtrees and
require a SECONDARY label on each result, and walk the primary subtree to
require that no game_first key survives and that exactly two labels remain,
PRIMARY at the root and SECONDARY on the retained log-loss cell. The recursive
walker _dicts is the only new test helper. Nine blank lines and two wrapped
continuations were reclaimed to pay for these lines; no assertion the verifier
confirmed as correct was removed or weakened. The fsync-failure test now
patches the os module through the guards namespace the writer actually uses.
Line counts after the fix: runner 161, guards 217, tests 299, memo 192.

## FIX 1c

Round 2 of independent verification returned ACCEPT WITH CORRECTIONS with five
corrections. Each was reproduced before any change. Nothing the verifier
confirmed was altered: the on-disk primary_verdict-first write, the SECONDARY
labelling and the nine-step launch order are untouched, and no assertion was
removed to pay for the new lines.

Correction 1, the only end-to-end check on the PRIMARY point compared it with
the tick-weighted mean over a construct carrying exactly one tick per period per
game, where period-first weighting and tick weighting are bit-identical, so the
check could not tell the two apart. Reproduced by scoring the old construct
through the landed scorer and period helper: the period-first point and the tick
mean came back equal bit for bit. Game g2 now carries three extra Q4 ticks, so
the construct is fifteen rows, four warm-up, eleven scored, fourteen D-eligible
and ten scored D. The test recomputes the period-first statistic independently
from the SAVED paired rows -- tick to game-period mean, then games within a
period, then periods -- and asserts the artifact equals that recomputation AND
differs from the tick mean. On the unbalanced construct the two disagree in the
first decimal place, for Brier and for log-loss.

Correction 2, the runner pre-filtered warm-up rows before stratified_cells, so
primary.json self-reported a warm-up count of zero over an already-reduced input
count. Reproduced on identical rows: the pre-filtered call reported n_input 11
and n_warmup 0 where the unfiltered call reported 15 and 4, and the D subset
reported 10 and 0 where the unfiltered call reported 14 and 4. The runner now
passes the unfiltered primary predictions and lets the landed helper make the
split. No value changed. The D point is identical to the last digit, and a
recursive comparison of both reports with the four census counters removed is
equal, so n_input and n_warmup are the only fields that differ.
n_warmup_excluded_upstream was therefore unnecessary and was not added.

Correction 3, the counted wrapper rebuilt every refusal as the bare exception
type name, so an unsealed prereg, a mismatched seal and an uncommitted prereg
were all the same indistinguishable "refused=1 authority ValueError". The
wrapper now keeps the cause text. The draft, unsealed, seal and commit refusal
modes, plus the new absent-prereg mode, each assert their own cause through a
CAUSES table.

Correction 4, an absent prereg escaped guards.authority as an uncounted
FileNotFoundError because OSError was not in the counted tuple. Reproduced
directly against the guard. OSError is now counted and a no_prereg refusal mode
covers it. With the four changed source lines reverted, seven cases fail -- the
two census assertions and the five cause assertions -- and all pass with them.

Final per-file result after FIX 1c: 78 passed (the new no_prereg refusal mode is
the added case). CLI --help exited 0. Contract preflight: 9 PASS, 0 FAIL. Git
status listed only the four owned untracked files.

Correction 5, the pre-FIX-1b line-count and per-file-result sentences are now
marked as such, the pre-FIX-1c construct-count sentence likewise, and the
"receives only scored rows" sentence was corrected rather than annotated because
FIX 1c makes it false. Line counts after FIX 1c: runner
162, guards 220, tests 299, memo 257. The test file stayed at its rail by
tightening only -- merged assertions, one dropped comment line and a single
census-mutation branch -- never by dropping a check.

## NOT VERIFIED

- No real corpus, real ledger, network, pod, sealed NBA prereg or trial was used.
- Committed synthetic authorities use the landed git_committed test seam;
  the uncommitted refusal is injected, not an integration test against git.
- Power loss, physical disk recovery, and simultaneous operating-system
  processes were not exercised; write failures are injected constructs.
- No quantities, prices, fees, fills, queues, as-of query, or timestamp recovery
  is implemented by this runner; their numerical rules are outside these tests.
- Dependency internals beyond the synthetic scorer routes were not exhaustively
  retested. No corpus exposure or cross-corpus conclusion is validated here.
- Independent verification and landing remain outstanding.
- FIX 1b changed only the JSON writer, the primary cell assembly and the
  construct test; no launch guard, refusal or charge path was touched, and no
  new run against a real corpus, ledger or sealed prereg was performed.
- FIX 1c changed two source lines in the counted wrapper, one line choosing the
  population handed to the landed period helper, and the construct test. The
  period-first and warm-up-census claims are measured on the synthetic construct
  only; no real corpus, real ledger, sealed prereg or trial was involved, and
  the unbalanced construct is not a statement about any real period mix.
