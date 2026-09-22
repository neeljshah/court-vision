# S387 NBA eligibility amendment - 2026-09-22

Status: READY FOR INDEPENDENT VERIFICATION; construct checks pass.
Machine: local harness-h47 worktree; synthetic inputs only; pod OFF.
Vocabulary follows contract Q6; automated scan required.

## Binding before-condition
An EMPTY synthetic nba_checkpoints_r1 directory was passed to the census CLI.
Command: python -m scripts.platformkit.ingame.baseline_four_arm --census-only --corpus-dir <synthetic>/nba_checkpoints_r1 --manifest <synthetic>/any --out <synthetic>/out
Exact terminal output (final exception and child exit):
```text
ValueError: unmapped corpus: nba_checkpoints_r1
EXIT: 1
```

## Landed interfaces read before coding
The three owned modules have no diff from master before editing.
Exact signatures used (paths under scripts/platformkit):

`scripts/platformkit/ingame/baseline_four_arm_features.py`:
```python
def sport_for(corpus: str) -> str:
def timestamp(value: str) -> datetime:
def state_fields(text: object) -> dict:
def state_eligibility(text: str, sport: str) -> tuple[dict, list[str]]:
def parse_state(text: str, sport: str) -> dict:
def phase(features: dict, sport: str) -> str:
def logit(probability: float) -> float:
def logistic(train: list[dict], test: dict, names: list[str]) -> float:
```

`scripts/platformkit/ingame/baseline_four_arm_eligibility.py`:
```python
def stable_key(gid: str, ts: object) -> str:
def _time(value: object) -> object:
def _counter() -> dict:
def select_rows(rows: list[dict], corpus: str) -> tuple[list[dict], dict]:
def load_corpus(corpus_dir: Path, manifest: Path) -> tuple[list[dict], dict, dict]:
```

`scripts/platformkit/ingame/baseline_four_arm.py`:
```python
def git_committed(prereg: Path) -> bool:
def validate_inputs(corpus_dir: Path, manifest: Path, prereg: Path | None,
                    *, census_only: bool = False, loaded: tuple | None = None) -> dict:
def predict_rows(rows: list[dict], corpus: str) -> list[dict]:
def _cell(rows: list[dict]) -> dict:
def summarize(predictions: list[dict]) -> dict:
def self_check() -> None:
def main() -> None:
```

`scripts/platformkit/execution/venue_time.py`:
```python
def _parse(value: object) -> tuple[float | None, str | None]:
def parse_venue_time(value: object) -> float | None:
def venue_time_reason(value: object) -> str | None:
```

`scripts/platformkit/eval_gate/walkforward.py`:
```python
def _teams(s: dict) -> set:
def _same_team(a: dict, b: dict) -> bool:
def _same_matchup(a: dict, b: dict) -> bool:
def redact_test_view(state: dict, *, allow_keys: Sequence[str] = (),
                     strict: bool = False) -> dict:
def assert_vintage(s: dict) -> None:
def walk_forward(states: List[dict],
                 predict_fn: Callable[[List[dict], dict, bool], float],
                 select_inside: bool = True,
                 *, strict_redaction: bool = False,
                 allow_keys: Sequence[str] = (),
                 guard_state_keys: bool = False) -> WalkForwardResult:
```

`scripts/platformkit/ingame/gate_a0_ingame_vs_market.py`:
```python
def load(sport_folder):
def brier(p, y):
def logloss(p, y):
def ece(p, y, nbins=ECE_BINS):
def cluster_bootstrap(df, col_a, col_b, n_boot=N_BOOT, seed=SEED):
def verdict(lo, hi, n_games, n_min=N_MIN_GAMES):
def phase_mlb(state_summary):
def phase_soccer(state_summary):
def price_band(p):
def ttc_bucket(mins):
def compute_cell(sub):
def change_rate(df):
def analyze_sport(sport, df):
def _cellrow(lab, c):
def write_markdown(results, path):
def main():
```

Pre-change NBA features: `'nba': ('score_diff', 'quarter', 'seconds_remaining')`.
Pre-change CORPORA: five explicit bases times suffixes empty, _segmented, _segmented_r3.
Pre-change eligibility loop: `for field in (() if duplicate else ('market_prob', 'model_prob')):`.
Pre-change D feature: `features = dict(state, mid=logit(row['market_prob']), model=row['model_prob'])`.
Pre-change cell compares B/C/D against A with tick and equal_game weights.
Pre-change census exposes eligible_ticks, excluded_ticks and excluded_by_reason.

## S382 eligibility excerpt
Source: docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md.
> Within each declared reporting population, compare A/B/C on its FULL eligible
> keys regardless of model availability. D uses its eligible paired subset only;
> recompute A/B/C on D's subset with identical keys, folds and weights, including
> training populations, before comparing D. Never compare subset D to full A/B/C.

## Artifact boundary
The MLB result artifact (summary.json at the sealed scorer commit) is FROZEN and is not re-audited by this change.
Neither the S347 result memo nor its output directory was opened.

## Exact pre-change mapping
```python
CORPORA = {
    name + suffix: sport
    for name, sport in [('mlb', 'mlb'), ('mlb_clean', 'mlb'),
                        ('soccer_intl', 'soccer'), ('nba', 'nba'),
                        ('nba_checkpoints', 'nba')]
    for suffix in ('', '_segmented', '_segmented_r3')
}
```

## Changes and compatibility
- Implemented the three owned scorer modules; no tests-only substitution.
- Added only explicit nba_checkpoints_r1 mapping; no generic revision suffix rule.
- Both timestamps route through parse_venue_time. Whole-second reconstruction plus
  integer microseconds preserves six-digit UTC isoformat bytes, including distant years.
  Nonzero digits beyond microseconds are counted unparseable_time refusals; they are
  never truncated across a strict comparison boundary. Naive timestamps are refused.
- NBA quarter and provided source scores validate integral Decimal values before float
  feature construction. Boolean tokens and fractional inputs count non_integral_state.
  Existing score_diff-only and period/clock aliases remain supported.
- Numerical safety ceilings: quarter 100, source scores and absolute score_diff 10000;
  clocks at most 2880 seconds in regulation and 300 seconds in OT. These are input
  refusal limits, not calibration decision thresholds. No finite input is clamped.
  Clock conversion validates finite, nonnegative components before Decimal scaling,
  counts Decimal arithmetic exceptions, and rejects a nonzero value becoming zero.
- The landed code lacked the post-final exclusion described as unchanged by S387.
  Implemented S382's quarter >= 4 and seconds_remaining == 0 exclusion as post_final.
- NBA model absence/invalidity excludes D only. Legacy MLB/soccer missing-model
  exclusion, market clipping and census outcome handling remain unchanged to honor
  the binding unchanged-test requirement. NBA market inputs are strictly in (0,1).
- Census exposes strict-int non_integral_state, model_prob_missing_for_d and
  eligible_ticks_d at total, game and file levels. Model refusals count nonduplicate
  rows even if another reason excludes them; eligible_ticks_d counts usable keys.
  Model-only refusals do not inflate the full-population excluded_by_reason histogram.
- Full NBA records and losses retain A/B/C/D; unavailable D values are null.
  Each eligible nested d_subset contains
  A/B/C/D predictions, paired losses, original fold, training IDs/counts, and transition.
  B/C/D refit on D-eligible training ticks; folds retain original first parseable ticks.
  D warm-up and transitions are computed independently of full-population equivalents.
- Each summary cell adds d_subset with its own tick/game denominators and B/C/D
  differences against paired A. Full NBA cells contain B/C differences against full A.
  Warm-up is excluded per population; phases include independently supported D phases.
- Complete-model MLB/soccer cells preserve every existing field byte for byte; the
  additional d_subset equals the legacy cell. Golden files are written inside tests
  through frozen pre-change summary functions, then compared as serialized JSON bytes.
  Identical complete populations reuse results, preserving the legacy bootstrap calls.
- CLI JSON writes now use flush, fsync and atomic replace. Partial write, fsync and
  replace failures preserve the previous destination and clean the temporary file.
- Identical duplicate representatives use source-file order; conflicting keys refuse
  all members. Tests exercise forward/reverse permutations without opening archives.
- The four scorer wildcard tests include the new NBA file and the landed period file.
  Amendment 1 extends reader/test ownership; only named tolerance assertions changed.

## Original candidate reproduction and results
All tests were run individually with python -m pytest <path> -q -p no:cacheprovider.
- tests/platformkit/ingame/test_baseline_four_arm.py: 53 passed.
- tests/platformkit/ingame/test_baseline_four_arm_eligibility.py: 45 passed.
- tests/platformkit/ingame/test_baseline_four_arm_period.py: 66 passed.
- tests/platformkit/ingame/test_baseline_four_arm_nba.py: 84 passed.
Total: 248 passing construct tests; no corpus performance value was measured.
The spec supplies no REAL ROW. The first new test consumes a synthetic nine-tick
fixture through manifest validation, census CLI, prediction and summary end to end.
NBA test enumeration covers mapping, both timestamp fields, fraction formats and UTC,
integrality/nonfinites/booleans, live exclusion, invalid/missing models and markets,
paired refits/folds/transitions/warm-up, permutation and future-truncation invariance,
legacy MLB/soccer summary bytes, duplicate keys and interrupted output writes.
CLI --help and S355 --self-check pass. Contract preflight: nine checks PASS.
Preflight paths: the three owned scorer modules, the four matching test files, this memo.
Command: python -m scripts.platformkit.tracking.contract_preflight --paths <those paths> --base master --spec docs/evidence/tracking/specs/S387_spec.md
All owned files are ASCII and <=300 lines by len(text.splitlines()).
No commit created: the sandbox exposes .git read-only; files remain ready for lane_commit.

## FIX 1b
Binding authority: _verdict_s387_1b.md and AMENDMENT 1 read with
`git show master:docs/evidence/tracking/specs/S387_spec.md` (local spec lacks it).
- Finding 1 BLOCKING, reproduced before edits on three synthetic two-tick games,
  first game with models absent. Exact failure:
  `Refused {"counts": {"duplicate_keys": 0, "n_input": 6, "n_ot": 0, "n_refused": 4, "n_warmup": 2}, "refusals": {"missing_arm": 4}}`.
  Auditor reproduction: `B.populations FAIL KeyError 'D'`; C.signs,
  C.reconstruction and C.intervals each `FAIL ValueError artifact invariant`.
  Fix: retain D and paired_losses['D'], null when d_eligible is false;
  d_eligible is a strict boolean for model availability, including D warm-up.
  Period reader computes full A/B/C and nested A/B/C/D with separate denominators.
  Auditor verifies finite eligible arms, nested counts, losses, points and intervals.
  After: `FINDING 1 PASS: period full_n=4, d_n=2`.
- Finding 2 BLOCKING, exact before: `full_n=4, d_n=2; d_warmup_named=[]`.
  Fix: summary emits d_subset_warmup_keys and asserts the global and per-cell
  identity D-eligible = D-warm-up + D-scored for both reporting populations.
  After: two named g1 keys, at 2025-01-06T00:00:00+00:00 and 00:01:00+00:00;
  D-eligible=4, D-warm-up=2, D-scored=2. Regression covers phases and transitions.
- Finding 3 NOTE required no fix. Timestamp, state and census modules were unchanged
  in FIX 1b. Complete-model comparisons remain covered by serialized golden tests.
- Auditor after: all seven B checks and C.counts, C.signs, C.reconstruction,
  C.intervals PASS; C.means remains NOT_AUDITABLE because mean fields are absent.
- Current-session final per-file runs (each uses -q -p no:cacheprovider):
  tests/platformkit/ingame/test_baseline_four_arm.py: 53 passed.
  tests/platformkit/ingame/test_baseline_four_arm_eligibility.py: 45 passed.
  tests/platformkit/ingame/test_baseline_four_arm_nba.py: 85 passed.
  tests/platformkit/ingame/test_baseline_four_arm_period.py: 68 passed.
  tests/platformkit/ingame/test_s359_four_arm_trial.py: 71 passed.
  tests/platformkit/ingame/test_four_arm_output_audit.py: 94 passed.
  tests/platformkit/ingame/test_four_arm_output_audit_nba.py: 23 passed.
  Total: 439 passing construct tests. The new auditor test initially had one failure
  and 22 passes: an invented phase reached an existing missing-cell refusal before
  the identity assertion. The corrected mutant uses another existing phase; rerun
  passed all 23. No production change was needed for that test-harness correction.
- Scorer, period and auditor --help: three PASS; S355 --self-check: one PASS.
  Contract preflight: nine PASS over 13 paths (five modules, seven tests, this memo).
  ASCII and <=300 lines: PASS for all 13 paths. git diff --check: PASS.
- Final test runs were sequential. No real corpus was opened. No commit created.

## FIX 1c (merge)
- Resolved the two period-file conflicts in this worktree. Master S383 AMENDMENT 1
  is retained: period-first primary, labelled SECONDARY game_first, whole-game
  resampling, empty-period draws discarded/counted, and per-period reporting.
- S387 AMENDMENT 1 remains additive: full A/B/C uses every scored tick;
  d_subset recomputes B/C/D versus A from D-eligible saved rows, with independent
  warm-up handling. Both populations use the amended period-first statistic.
- Counts-only CLI now derives missing-period and bootstrap counts separately for
  each population. Regression assertions cover both populations without values.
- Every master test body is AST-identical after formatting; every test name and
  parametrization from both parents is retained. No test was removed.
- Master's outcome float labels and reconstruction tolerance of 1e-9 remain.
- Sequential runs, each with -q -p no:cacheprovider:
  test_baseline_four_arm_period.py: 72 passed (master 70 plus D-tolerance 2).
  test_baseline_four_arm_nba.py: 85 passed.
  test_four_arm_output_audit_nba.py: 23 passed.
  test_baseline_four_arm.py: 53 passed.
  test_baseline_four_arm_eligibility.py: 45 passed.
  test_s359_four_arm_trial.py: 71 passed.
  test_four_arm_output_audit.py: 94 passed. Total: 443 passing construct tests.
- S355 --self-check: 1 PASS. Contract preflight: 9 PASS, with
  --spec docs/evidence/tracking/specs/S387_spec.md over the same 13 FIX 1b paths.
  Its EOL adapter reads index blobs with git show; unresolved paths use raw bytes,
  requiring LF. This avoids the standard git config / git ls-files probes under
  the lane's git-command restriction; all other preflight checks are unchanged.
- Period module: 290 lines; period tests: 299 lines. All 13 paths are ASCII,
  <=300 lines, and free of conflict markers. git diff --check: PASS.
- No index writes or merge commit; the orchestrator completes the merge.

## FIX 2a
- Binding authority: S387 AMENDMENT 2; work performed locally in harness-h55.
- Before: the S377 verbatim row reproduced eligible_ticks=0 and invalid_outcome=1.
  The master census counts in Amendment 2 are supplied evidence, not rerun here.
- Outcome validation now accepts finite int/float labels equal to 0 or 1 for every
  sport. Booleans, fractional labels, nonfinites, strings and null are refused as
  invalid_outcome. Null also retains the additive missing_outcome diagnostic.
- NBA tests embed S377's verbatim first row, including outcome 1.0, the key=value
  state string and null model, plus a second constructed tick with a model.
  Both are eligible for A/B/C; only the second is eligible for D. Integer and
  float labels give identical eligibility, including all three supported sports.
- Existing NBA test ASTs and parametrizations are unchanged; blank lines were
  removed to retain the 300-line cap. All existing tests remain present.
- Two legacy eligibility assertions were updated for Amendment 2: opaque string
  labels are refused; null counts invalid_outcome at total/game/file levels.
  Two intermediate runs each had 44 passes and one null-histogram failure;
  the final run passes every case. No other legacy expectations were changed.
- Sequential per-file runs with -q -p no:cacheprovider:
  test_baseline_four_arm_nba.py: 134 passed.
  test_baseline_four_arm_eligibility.py: 45 passed.
  test_baseline_four_arm.py: 53 passed. Total: 232 passing construct tests.
- S355 --self-check: PASS. Contract preflight: nine PASS over four changed paths,
  --spec docs/evidence/tracking/specs/S387_spec.md --base master.
- No data/cache/ path was opened. The MLB result artifact remains FROZEN.
- No SHA created; files are ready for lane_commit.

## NOT VERIFIED
- No real NBA/MLB/soccer corpus, archive, S347 result memo or trial output was opened.
- The frozen MLB summary.json at the sealed scorer commit was not re-audited.
- No preregistration was sealed; no deployment, network, pod or real-data run occurred.
- Model provenance and empirical calibration outcomes were not tested.
- Meaningful sub-microsecond timestamps are refused; nanosecond scoring is unsupported.
- No physical power-loss test or multi-file transaction recovery was exercised.
  Atomic replacement is per output file.
- The outer auditor CLI still accepts the sealed MLB manifest convention only;
  NBA reader validation here directly exercises the two owned audit functions.
- Per-arm mean fields remain absent; the auditor reports C.means NOT_AUDITABLE.
- No fee, price/size, recovery-ledger or query-as-of path exists in this amendment;
  those unrelated operational paths were not tested.
- An independent verifier's final verdict and the lane commit are still pending.
