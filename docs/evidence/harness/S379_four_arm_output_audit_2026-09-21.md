# S379: PREPARE output auditor
Built an opt-in, read-only saved-output auditor and one independent construct
test fixture. No fit, trial, real corpus, real ledger or external service ran.
Vocabulary follows contract Q6; automated scan required.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h38 only.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, sections B and Q.
The request's docs/evidence/VERIFIER_CONTRACT.md path is absent; the harness-lane
skill identifies the tracking path above. Eye check is not applicable.
## Binding before-condition
Before coding, `ls scripts/platformkit/ingame/four_arm_output_audit.py`
returned exit code 1. Exact diagnostic text, including its console wrapping:
```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h38\scripts\platformkit\ingame\four_arm_output_audit.py' because it
does not exist.
At line:2 char:1
+ ls scripts/platformkit/ingame/four_arm_output_audit.py
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (C:\Users\neelj\...output_audit.py:String) [Get-ChildItem], ItemNotFound
   Exception
    + FullyQualifiedErrorId : PathNotFound,Microsoft.PowerShell.Commands.GetChildItemCommand
```
## Sources and signatures read before implementation
These are text/JSON sources; image resolution is not applicable. Landed source
and prereg paths had an empty `git diff master -- <paths>` in this session.
The reference file was read but never imported or edited and is not a deliverable.
| Source path | Bytes |
| --- | ---: |
| scripts/platformkit/ingame/baseline_four_arm.py | 13482 |
| scripts/platformkit/ingame/baseline_four_arm_eligibility.py | 10537 |
| scripts/platformkit/execution/venue_time.py | 2029 |
| _reference_s359_four_arm_trial.py | 11042 |
| docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md | 14168 |
Exact landed signatures used to understand the saved artifacts:
```python
def predict_rows(rows: list[dict], corpus: str) -> list[dict]:
def _cell(rows: list[dict]) -> dict:
def summarize(predictions: list[dict]) -> dict:
def stable_key(gid: str, ts: object) -> str:
def select_rows(rows: list[dict], corpus: str) -> tuple[list[dict], dict]:
def load_corpus(corpus_dir: Path, manifest: Path) -> tuple[list[dict], dict, dict]:
```
None of those functions is imported or invoked. The only landed application
function imported by the auditor is this signature, read in full before coding:
```python
def parse_venue_time(value: object) -> float | None:
```
Its documented microsecond truncation is handled by validating through that
function, parsing whole seconds through it, then adding the original fraction
with Decimal. All comparisons retain the complete accepted nine-digit fraction.
Naive strings and non-string saved timestamps are refused.
Gate source was inspected for the two loss definitions: Brier is squared error;
log-loss uses the existing EPS = 1e-6 clipping rule. No gate helper is imported.
## Saved schemas relied upon
- Prereg seal: final `SHA256: <64 lowercase hex>` line; hash every preceding
  byte after CRLF-to-LF normalization, including the separator newline.
- Manifest: `{"files": {"relative.jsonl": "sha256hex"}}`. The prereg pin is
  the per-file manifest's SHA-256 after JSON sorted-key compact serialization,
  not the segmenter manifest's digest. Every listed file is hashed and the
  top-level JSONL inventory must match. Symlinks and escaping paths are refused.
- Corpus JSONL: `game_id`, `ts`, `close_ts`, `outcome` supply identities,
  first-tick chronology, training settlement boundaries and outcome truth.
  Corpus outcomes and all paired outcomes must be consistent per game.
- `attempt.json`: `attempt` and `descriptive_soccer`; only integer attempts
  1 and 2 in the MLB mode are accepted.
- `charge.json`: `ledger_row`, `k_at_launch`, `attempt`, `ledger_path`,
  `prior_max_k_cumulative`. The checks rely on all except `ledger_path`. The embedded
  row supplies `hypothesis_hash`, `prereg_sha256`, `k_cumulative`, `at`. The hypothesis
  is SHA-256 of original prereg bytes plus the canonical manifest digest's ASCII
  bytes. The independently supplied ledger must have exactly one matching
  hypothesis/seal row, identical to the embedded row, with count K. K equals
  `prior_max_k_cumulative + 1`. No higher-K row may have an earlier `at` time.
- `paired_rows.json`: a JSON list of row objects, carrying `game_id`, `ts`,
  `_first_ts`, `close_ts`, `outcome`, `key`, `phase`, `transition`, `fold`,
  `warmup`, `train_n_games`, `train_n_ticks`, optional `train_games`, numeric
  `A`, `B`, `C`, `D`, and `paired_losses[arm][brier|logloss]`.
  The key is compact JSON `[game_id, UTC timestamp]`. Equivalent timestamp
  representations cannot evade duplicate detection. Warmup and transition are
  strict booleans; counts are strict integers; outcomes are numeric binary labels.
- `summary.json`: `scope`, `fold_training_sizes[date]` with `train_games` and
  `train_ticks`, `warmup_keys`, `populations`, `provenance`, `eligibility`.
  Census fields live in `eligibility.sports.mlb`. Frozen text parses files,
  games, ticks, eligible ticks/games, excluded ticks, transition ticks, total
  folds, warmup folds and scored folds. The actual seal freezes 176 games,
  31433 ticks, 29887 eligible ticks, 12339 transition ticks, 15 folds and four
  warmup folds. Those values are not hardcoded into the auditor.
- Census `folds` is a date-ordered list of `{date, train_games, train_ticks,
  warmup}`. Saved row order is unrestricted; date-fold order is checked against
  first-tick UTC dates. Nonzero recorded training sizes are required for scored
  folds. Present training IDs must be unique, exclude the held-out game, refer
  to earlier corpus games and settle strictly before the three-day boundary.
  Missing training IDs produce an explicit noncritical NOT_AUDITABLE check.
- `populations` has exactly `all_tick` and `state_transition_tick`; each has
  `overall` and `by_phase[phase]`. A cell has `n_ticks`, `n_games`,
  `comparisons[tick|equal_game][B|C|D + _brier|_logloss]`. Each comparison has
  `point`, two-element `ci95`, `verdict`, `leave_one_game_out_range`,
  `largest_absolute_share[game_id|week]`, and boolean `concentration_pass`.
  An empty cell has empty comparisons and `verdict: UNDERPOWERED`.
  Undefined shares and single-game leave-out ranges are JSON null.
- `trial_summary.json` from the reference repeats identity/accounting fields
  (`spec_id`, `attempt`, `prereg_sha256`, `manifest_digest`, `scorer_commit`,
  `hypothesis_hash`, `descriptive_soccer`, `family`, `tier`, `k_at_launch`,
  `ledger_row`, `verdicts`, `scope`). It is not consumed: S379 names
  `summary.json` as the comparison authority.
- `failure.json` holds `attempt`, `error_type`, `status`; presence alone fails,
  without exposing its contents. Test-ledger wrapper mode from the reference
  is not supported as a trial evidence format.

## Accounting and schema incompatibilities

AMENDMENT 1 (2026-09-21), read with
`git show master:docs/evidence/tracking/specs/S379_spec.md`, supersedes that
original convention. The orchestrator withdrew the K-plus-one requirement.
Check A now requires strict integer equality of embedded cumulative K and
launch K, and launch K equal to prior maximum plus one. Exactly one supplied
ledger row must match the embedded hypothesis/seal and the entire embedded row.
No higher cumulative K may precede its `at` timestamp; subsequent ledger charges
are permitted. Timestamp comparisons and ledger matching ignore record order.
The unchanged reference-shaped construct now passes every A check.
The landed cell schema contains differences but no per-arm mean fields. The
auditor independently computes all arm means, validates archived per-row losses,
and reports C.means NOT_AUDITABLE for absent summary means. If a cell supplies
`arm_means[weighting][arm][metric]`, it is compared; an earlier missing block
cannot hide an incorrect later block. This extension changes no producer.
AMENDMENT 1 explicitly makes absent means noncritical NOT_AUDITABLE. Critical
reconstruction covers every comparison's `point` and sign, cell counts, largest
single-game share and leave-one-game-out range, with tolerance 1e-12. The four
required regression cases cover embedded/launch K mismatch, prior/launch K
mismatch, unchanged reference-shaped A success, and a point changed by 1e-9.

## FIX 1c

Binding sources: `_verdict_s379_1c.md` and the master S379 spec including
AMENDMENT 1, read using `git show master:docs/evidence/tracking/specs/S379_spec.md`.
Only this row's helper, construct tests and memo changed in this fix pass.
The accounting convention, strict integers, finite arm checks, input protection,
atomic output writes and lack of scorer imports remain as previously implemented.
Before editing, the verifier's three minimal reproductions returned:
```text
finding 1: C.signs=PASS, C.reconstruction=PASS, C.intervals=PASS
finding 2: B.populations=PASS, B.keys=PASS, B.outcomes=PASS, B.warmup=PASS, B.chronology=PASS, B.training=PASS, B.self_training=PASS
finding 3: B.populations=PASS, B.keys=PASS, B.outcomes=PASS, B.warmup=PASS, B.chronology=PASS, B.training=PASS, B.self_training=NOT_AUDITABLE
```
After the fixes, the same reproductions correctly reject their defects:
```text
finding 1: C.signs=PASS, C.reconstruction=PASS, C.intervals=FAIL
finding 2: B.populations=PASS, B.keys=FAIL, B.outcomes=PASS, B.warmup=PASS, B.chronology=PASS, B.training=PASS, B.self_training=PASS
finding 3: B.populations=PASS, B.keys=PASS, B.outcomes=PASS, B.warmup=FAIL, B.chronology=PASS, B.training=FAIL, B.self_training=NOT_AUDITABLE
```
These were failures of the intended rejection behavior, reproduced entirely
from the existing synthetic fixture. The first used a positive reconstructed
point with `ci95=[-0.5,-0.1]` and `verdict=SINGLE-WINDOW`. The second substituted
12:30 for a corpus tick at 12:00. The third invented one training game/tick
for the earliest fold, marked it scored, and omitted the saved training IDs.

1. BLOCKING interval trust: independently reconstruct both endpoints and the
   bootstrap point to tolerance 1e-12. The implementation uses numpy's same
   generator, seed 13, 2000 draws, sorted game IDs, and percentile rule. Equal-game
   units first average losses per (game_id, ISO week). No scorer helper is imported.
   Regressions include the contradictory point/interval and comparisons against
   a separate pandas aggregation plus the literal reference draw loop, for both
   weightings, both losses, all candidates, unequal counts and multiple weeks.
2. BLOCKING fabricated identities: normalize every paired (game_id, ts), require
   its presence in the hash-verified corpus, and reconcile outcome and close_ts
   with every matching corpus record. Regression cases cover a substituted tick,
   a changed close, equivalent timezone representations, and a one-nanosecond
   identity difference. Existing duplicate and outcome checks remain active.
3. BLOCKING invented training: count paired eligible rows per corpus game and
   independently derive eligible training games from corpus first ticks and
   consistent corpus closes. Compare every census, summary and row training count;
   derive warm-up from zero training rows and compare all saved flags/key lists.
   Missing counts fail. Absent training IDs retain the explicit noncritical
   self-training NOT_AUDITABLE, but cannot bypass reconstructed counts/warm-up.
   Regressions cover invented and missing counts, the earliest scored fold, and
   close instants just before, exactly at, and just after the three-day cutoff.
4. NOTE: the verifier's 68 setup errors are recorded as its environment result,
   not passes. This pass runs construct tests in a writable temporary directory.

Exact master reference functions read for finding 1 follow. The independent
implementation compares separate candidate and A sums in the same draw stream.
From `scripts/platformkit/ingame/gate_a0_ingame_vs_market.py`:
```python
def cluster_bootstrap(df, col_a, col_b, n_boot=N_BOOT, seed=SEED):
    """Game-clustered bootstrap CI on the paired tick-weighted mean(a - b)."""
    rng = np.random.default_rng(seed)
    g = df.groupby('game_id').agg(sa=(col_a, 'sum'), sb=(col_b, 'sum'), n=(col_a, 'size'))
    sa, sb, nn = g['sa'].to_numpy(), g['sb'].to_numpy(), g['n'].to_numpy()
    ng = len(g)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, ng, ng)
        diffs[i] = (sa[pick].sum() - sb[pick].sum()) / nn[pick].sum()
    point = (sa.sum() - sb.sum()) / nn.sum()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(point), float(lo), float(hi)
```
The baseline_four_arm.py `_cell` schema is quoted in the saved-artifact list above.
The finding-3 source is `baseline_four_arm.predict_rows`; exact excerpts:
```python
        boundary = first[gid].replace(hour=0, minute=0, second=0, microsecond=0)
        # Purge full game intervals crossing the symmetric [boundary-3d,boundary+3d].
        train = [s for s in train if first[s['game_id']].date() < first[gid].date()
                 and settled[s['game_id']] < boundary - EMBARGO]
        record['train_games'] = sorted({s['game_id'] for s in train})
        record['train_n_games'] = len(record['train_games'])
        record['train_n_ticks'] = len(train)
        record['A'] = test['features']['raw_mid']
        record['warmup'] = not train
```
`EMBARGO = timedelta(days=3)` is defined in baseline_four_arm_eligibility.py.
Its select_rows establishes first ticks from all parseable raw corpus ticks,
including excluded ticks, and rejects inconsistent per-game closes. The audit
preserves nanosecond fractions through the existing venue-parser/Decimal route.
The spec's favourable-interval SINGLE-WINDOW label remains binding; master gate
itself labels small cells UNDERPOWERED, so endpoint/point parity and label policy
are tested separately. This fix changes no producer or threshold.
Verification commands (one test file covers both row modules):
```text
python -m pytest tests/platformkit/ingame/test_four_arm_output_audit.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.four_arm_output_audit --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/four_arm_output_audit.py scripts/platformkit/ingame/four_arm_output_audit_checks.py tests/platformkit/ingame/test_four_arm_output_audit.py docs/evidence/harness/S379_four_arm_output_audit_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S379_spec.md
```
The CLI has no self-check option; contract_preflight supplies the static checks.
Intermediate test run: `3 failed, 75 passed`; the three small-cell fixtures
held numpy scalars instead of JSON-native floats. Corrected the test oracle's
return types; strict production number checks were preserved.
FIX 1c final verification: 83 passed (CONSTRUCT); CLI help exit 0; contract
preflight 9 PASS, zero FAIL. All three minimal reproductions now reject.
Final files: CLI 252 lines, helper 294 lines, tests 300 lines; all ASCII.
SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX 1d

Binding verdict: `_verdict_s379_1d.md`; master S379 spec AMENDMENT 1 applies.
Finding 1 (BLOCKING), reproduced before edits using the existing synthetic fixture:
```text
interval reproduction: contains_zero=False
manifest reproduction: A.seal=PASS, A.manifest=FAIL
manifest reproduction without pin comparison: A.manifest=FAIL
```
The old interval case never spanned zero; the empty manifest still failed when
its pin comparison was removed. These were test-isolation failures.
The interval fixture now gives B opposing contributions in two distinct games,
reconstructs its summary naturally, asserts strict zero spanning and a passing
baseline, then changes only its label to MATCH. Signs, counts and reconstruction
must still pass while interval validation rejects the label.
The manifest case changes only the prereg pin and reseals that text. It asserts
an initially passing audit, unchanged manifest bytes, A.seal PASS and A.manifest
FAIL. The row module now expresses the same pin rejection with an explicit
ValueError branch; the audit still redacts its exception text. No threshold,
reconstruction, chronology, accounting or output policy was changed.
After edits, both regression assertions passed (CONSTRUCT):
```text
fixed interval: contains_zero=True, verdict=MATCH, C.intervals=FAIL
fixed manifest: A.seal=PASS, A.manifest=FAIL
fixed manifest without pin comparison: A.manifest=PASS
```
The pin-removal probe executed a source copy in memory, never a file mutation.
Its PASS demonstrates the corrected construct detects removal of that guard.
Findings 2 and 3 (NOTE, fix none): the confirmed implementations stay intact.
The verifier's 83 setup errors are not test passes; this lane uses writable
local scratch. Durable lesson: assert the intended fixture precondition and
isolate a pin mismatch with a valid seal and unchanged manifest content.
FIX 1d verification: per-file pytest 83 passed (CONSTRUCT), zero failures;
CLI --help exit 0; no self-check option exists. Contract preflight: 9 PASS,
zero FAIL. Both corrected reproduction assertions passed. All four deliverables
are ASCII and <=300 lines: CLI 253, helper 294, tests 300, memo 298.
SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX 2a

Binding source: S379 spec AMENDMENT 2. Worktree: nba-harness-h45.
Outcome labels accept finite int or float values exactly equal to 0 or 1;
booleans, fractional values, NaN and strings are refused. All counts retain
strict-int validation. Only the helper reads outcomes; the CLI is unchanged.
CONSTRUCT coverage includes corpus and paired float labels 1.0 / 0.0, plus
boolean, fractional, NaN and string refusal in all five affected checks.
Verification: per-file pytest 88 passed (CONSTRUCT, 203.27s); CLI help exit 0; preflight 9 PASS, zero FAIL.
The sealed trial output and every file under data/cache/ remain unread.

## FIX 2b

Binding source: master S379 spec AMENDMENT 3, read with git show; nba-harness-h45.
RECONSTRUCTION_ABS_TOL = 1e-9 is the single absolute reconstruction tolerance
for point estimates and interval endpoints. Counts remain exact; FIX 2a stays intact.
CONSTRUCT cases seed 5e-10 (PASS) and 2e-9 (FAIL) into a point and each endpoint.
The earlier point-defect case now uses 2e-9. No prereg decision threshold changed.
Verification: per-file pytest 94 passed (CONSTRUCT, 175.20s); CLI help exit 0; preflight 9 PASS, zero FAIL.

## NOT VERIFIED

- No real trial, archive, ledger, network, pod, fit or measured calibration result
  was exercised; all executable evidence is CONSTRUCT.
- Reference runner execution and real-artifact compatibility remain unverified.
- Per-arm mean fields are absent from the current landed summary schema.
- Actual fit membership without IDs, capture-time feature freshness, historical
  prereg commit time and caller-supplied canonical ledger authority are unproven.
- Full eligibility/state-transition feature reconstruction and redundant
  trial_summary.json assertions are outside these saved-output checks.
- No deployment, commit, whole-suite test or independent external acceptance
  was performed. No test simulates operating-system power loss after replacement.
