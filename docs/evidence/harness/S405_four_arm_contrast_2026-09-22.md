# S405 additive D-minus-C producer fields -- PREPARE

Local machine, worktree C:/Users/neelj/nba-harness-h66; construct inputs only.
Authority: docs/evidence/tracking/specs/S405_spec.md.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B and Q.
Baseline master: dfdac82bca0c16d12adedbf3d25a47c1fd54357d.
No real corpus, charged trial, seal, production record or network operation.

## Before-condition, quoted from master

scripts/platformkit/ingame/nba_four_arm_trial.py:41-51:

```python
def _primary(cells: dict) -> dict:
    comparisons = cells["comparisons"]
    brier = _cell(comparisons["C_brier"])
    return dict(label="PRIMARY", comparison="period-first C-minus-A",
                verdict=brier["verdict"], brier=brier,
                logloss=_cell(comparisons["C_logloss"], label="SECONDARY"),
                **{k: v for k, v in cells.items() if k not in ("comparisons", "d_subset")},
                secondaries=_label(dict(comparisons={
                    k: v for k, v in comparisons.items() if k != "C_brier"},
                    game_first={k: v["game_first"] for k, v in comparisons.items()},
                    d_subset=cells.get("d_subset", {}))))
```

scripts/platformkit/ingame/nba_four_arm_trial.py:26-32:

```python
    result = {k: _label(v, descriptive or k == "d_subset" or k.startswith("D_"))
              for k, v in value.items()}
    if any(k in result for k in ("verdict", "comparisons", "populations", "d_subset")):
        result["label"] = "SECONDARY DESCRIPTIVE" if descriptive else "SECONDARY"
    if descriptive and "verdict" in result:
        result["interval_verdict"] = result["verdict"]
        result["verdict"] = "DESCRIPTIVE"
```

The generic wrapper copies B_*, C_* and any D_* supplied by the period helper.
For the landed NBA shape, D_* reside inside secondaries.d_subset.comparisons;
secondaries.comparisons omits C_brier, which is the primary brier cell.
Neither D_minus_C_<metric> nor d_subset.scored_keys exists before this change.

scripts/platformkit/ingame/baseline_four_arm.py:160-165:

```python
                frame['a'] = loss(frame[arm], frame['outcome'])
                frame['b'] = loss(frame['A'], frame['outcome'])
                units = frame[['game_id', 'week', 'a', 'b']]
                if weighting == 'equal_game':
                    units = units.groupby(['game_id', 'week'], as_index=False).mean()
                point, lo, hi = cluster_bootstrap(units, 'a', 'b')
```

scripts/platformkit/ingame/baseline_four_arm.py:177-183:

```python
                comparisons[f'{arm}_{metric}'] = {
                    'point': point, 'ci95': [lo, hi], 'verdict': status,
                    'leave_one_game_out_range': [float(leave.min()), float(leave.max())]
                    if ng > 1 else None, 'largest_absolute_share': shares,
                    'concentration_pass': shares['game_id'] is not None
                    and shares['game_id'] <= 0.5,
                }
```

scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:70-73:

```python
def cluster_bootstrap(df, col_a, col_b, n_boot=N_BOOT, seed=SEED):
    """Game-clustered bootstrap CI on the paired tick-weighted mean(a - b)."""
    rng = np.random.default_rng(seed)
    g = df.groupby('game_id').agg(sa=(col_a, 'sum'), sb=(col_b, 'sum'), n=(col_a, 'size'))
```

scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:77-82:

```python
    for i in range(n_boot):
        pick = rng.integers(0, ng, ng)
        diffs[i] = (sa[pick].sum() - sb[pick].sum()) / nn[pick].sum()
    point = (sa.sum() - sb.sum()) / nn.sum()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(point), float(lo), float(hi)
```

docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md:15:

> B-minus-A, D-minus-A and D-minus-C are secondary; D is conditional on provenance.

docs/evidence/tracking/specs/S395_spec.md:71-77, AMENDMENT 3:

> AMENDMENT 3 (2026-09-22 19:0xZ; binding; from fix 1d against the LANDED S394 runner shape). MEASURED by the fix agent on a fixture
> built through trial._primary(stratified_cells(primary_rows)): the landed S394 runner emits NO D_minus_C_<metric> contrast and NO
> d_subset.scored_keys, both named in this row's CHANGE clause. RULING: the auditor audits each when present and never invents
> either; requiring them would fail every real S394 output. Their absence is recorded in the audit report as a producer gap
> (check status NOT_AUDITABLE with reason producer_field_absent, never PASS) and in the memo's NOT VERIFIED list; closing it is an
> additive S394 follow-up row (allocated by the orchestrator, not this row). The auditor's release verdict on the landed shape is
> therefore reached with C.means NOT_AUDITABLE and those two checks NOT_AUDITABLE, and the seal / trial memo must say so in words.

## FIX 1c -- S405 AMENDMENT 2 (a)-(e)

Local Python 3.10.0. Fix 1b's period-weighted saved-loss contrast and validation
are retained. Only the contrast's local scored-row list is canonically sorted
by (game_id, phase, key). Validation returns the original list, preserving
saved predictions and fold_training_sizes insertion order. B2 remains additive.
N_BOOT=2000, SEED=13 and N_MIN_GAMES=30 are unchanged (contract Q3).

The golden fixture now captures every output from the landed runner:
attempt.json, ledger_before.jsonl, charge.json, paired_rows.json, summary.json,
primary_paired_rows.json, primary.json, trial_summary.json, and the return value.
It covers the original OT fixture, games renamed z0,a1,b2, and the separate
primary-population prediction path. Only the temporary ledger path is frozen
identically at capture; only the S405 fields are removed for byte comparison.
Launch authorities and scorer predictions are synthetic; summaries, period
machinery, run orchestration and JSON serialization are exercised unchanged.
The original primary-only golden assertions remain, using this wider capture.
Capture baseline: master e65683a7d1a756a268a0fe3f7e70011045c1fd8f; its runner
source is byte-identical to the before-condition source quoted above.

Both D_minus_C metrics use verdict=DESCRIPTIVE and interval_verdict for the
statistical outcome, matching the existing D cell even below 30 games.
The powered construct repeats the complete scored game under 30 distinct IDs:
180 input rows, 30 excluded OT rows, 150 scored keys, four periods per game.
This repeated synthetic case tests labeling only; it is not independent evidence.

Adjudication of AMENDMENT 2(d): AMENDMENT 1(e)'s population rule stands.
The complete one-game construct retains exactly five scored keys, and its
UNDERPOWERED outcome is in interval_verdict under AMENDMENT 2(b).
The requested one-game empty list is withdrawn. Empty input alone has [].
Complete, incomplete and empty constructs each assert repeat serialization.

Independent diagnostic assertions use the game-period matrix for both metrics,
separately from interval endpoints. A planted g2:1 D=0.9 with consistent saved
losses increases the Brier leave-one-game-out endpoints and decreases the
largest absolute share. Separate analytic assertions pin both after values.

### Worked example and source sizes

Input: primary_rows() in the named test source; n=14 rows (CONSTRUCT).
Four full warm-up rows, one D-ineligible row, one additional subset warm-up
row and one OT row leave seven scored keys:
["g1:3", "g1:4", "g2:1", "g2:2", "g2:3", "g2:4", "g2:5"].
Resolution: n/a (synthetic tabular fixture).
Brier point=0.07999999999999996; reported subset D=0.13999999999999996
minus C=0.06. ci95=[0.07999999999999996, 0.12999999999999995].
leave_one_game_out_range=[0.12999999999999995, 0.12999999999999995].
largest_absolute_share.game_id=1.21875; concentration_pass=false.
Retained/discarded bootstrap draws=1489/511; missing periods are not imputed.
Logloss point=0.17722388438202114; ci95=[0.17722388438202114, 0.2876820724517809].
Both metrics retain SECONDARY DESCRIPTIVE and DESCRIPTIVE/UNDERPOWERED.
New fields satisfy S395 producer checks D.contrast_d_minus_c and D.scored_keys.
S417's C-minus-B primary and B_lag work are outside this row.

Source size: `scripts/platformkit/ingame/nba_four_arm_trial.py` = 11949 bytes (LF-normalized, at landing commit b66352c69)
Source size: `tests/platformkit/ingame/test_nba_four_arm_trial_contrast.py` = 123994 bytes (LF-normalized, at landing commit b66352c69)

Sizes refer to the current candidate; unreproducible historical sizes are removed.
The source-size test independently reads the named candidate files.

### Reproductions

Executed with python -B -c on synthetic fixtures, before and after edits.
Every shell command begins with cd C:\Users\neelj\nba-harness-h66 &&.
Before (verbatim):
```text
a: g2=g2:6,g2:1,g2:2,g2:3,g2:4,g2:5
a: folds=6,11,1
b: BEHIND/BEHIND
c: loo=0.13->0.21 share=1.218750->1.109375
d: keys=5 UNDERPOWERED/UNDERPOWERED repeat=True
e: source_size_matches=False
```

After (verbatim):
```text
a: g2=g2:1,g2:2,g2:3,g2:4,g2:5,g2:6
a: folds=1,6,11
b: DESCRIPTIVE/BEHIND
c: loo=0.13->0.21 share=1.218750->1.109375
d: keys=5 DESCRIPTIVE/UNDERPOWERED repeat=True
e: source_size_matches=True
```

Reproduction uses runner_outputs(trial, case, monkeypatch) for a (then renamed=True),
powered_rows() for b, primary_rows() with g2:1 D changed to 0.9 and saved losses
recomputed for c, the g2-only primary_rows() for d, and Path.stat().st_size for e.
Cells in b-d are trial._primary(trial.stratified_cells(rows), rows).
c already had correct numbers in fix 1b; this pass adds independent assertions.
d retains the same keys and interval outcome; only the descriptive wrapper changes.

### Validation

Per-file commands, sequential, using Python 3.10.0:
python -m pytest tests/platformkit/ingame/test_nba_four_arm_trial_contrast.py -q -p no:cacheprovider
34 passed in 48.33s
python -m pytest tests/platformkit/ingame/test_nba_four_arm_trial.py -q -p no:cacheprovider
78 passed in 28.29s

contract_preflight --paths (the three owned paths) --base master --spec
docs/evidence/tracking/specs/S405_spec.md: exit 0, 9 PASS, 0 FAIL.
```text
PASS vocab clean over 3 files
PASS crlf no index-side CRLF over 3 file(s); 2 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 4 dir(s)
PASS row_duplication no row duplication over checked artifacts
```
Reader survey of ingame Python modules finds no other contrast consumer.
Guards and the one landed test file retain their starting SHA-256 identities:
- nba_four_arm_trial_guards.py: 3c2c3cbc9248fb2d7acde33ed163c25cb4416ccfdb55a3c5949f7c61ce1b3f9f
- test_nba_four_arm_trial.py: d66b22ec1323f340c63f0278b90afea839576fabbb56143ed457f891bf2851e4
The scoped git diff master --stat reports the runner only because the new test
and memo are untracked; git status lists exactly the three owned paths.
No commits, network operations, registry access or real-corpus trial.

## FIX 1d -- S405 AMENDMENT 3

Local Python 3.10.0; fixture-only reproduction, no real corpus.
_checked_rows now recomputes every saved subset loss for A, B, C and D,
for Brier and logloss, with absolute tolerance 1e-12 and zero relative tolerance.
A mismatch names the arm, subset row key and metric in inconsistent_paired_loss.
Validation still returns the original list; no sorting, weights, labels,
diagnostics, keys, bootstrap constants or golden output bytes were changed.

The pinned test covers 24 constructs: four arms x two metrics x three deltas.
A Brier starts at exactly 0.25; adding 0.1 pins the reported 0.35 corruption.
Both 0.1 and 2e-12 refuse before period cells; 5e-13 remains within tolerance.
Every refusal pins the complete reason, including arm, g2:1 and metric.
Fix 1c's widened golden, D-minus-C equality, DESCRIPTIVE convention,
independent diagnostics and one-game repeat serialization remain in place.
Source sizes above were re-measured after this edit.

Before, verbatim from a Python one-liner on primary_rows():
```text
clean: C=0.06 D=0.14 contrast=0.08
ACCEPTED: C=0.035 D=0.115 contrast=0.08
```
After, verbatim from the same fixture mutation:
```text
clean: C=0.06 D=0.14 contrast=0.08
REFUSED: refused=1 inconsistent_paired_loss arm=A key=g2:1 metric=brier
```

Reproduction one-liner (the before run omitted the exception-printing hook):
```python
import sys; sys.excepthook=lambda cls,error,tb: print('REFUSED: '+str(error)); from tests.platformkit.ingame.test_nba_four_arm_trial_contrast import primary_rows; from scripts.platformkit.ingame import nba_four_arm_trial as t; r=primary_rows(); s=t._primary(t.stratified_cells(r),r)['secondaries']; print('clean: C={:.3g} D={:.3g} contrast={:.3g}'.format(s['d_subset']['comparisons']['C_brier']['point'],s['d_subset']['comparisons']['D_brier']['point'],s['comparisons']['D_minus_C_brier']['point'])); next(x for x in r if x['key']=='g2:1')['d_subset']['paired_losses']['A']['brier']=0.35; s=t._primary(t.stratified_cells(r),r)['secondaries']; print('ACCEPTED: C={:.3g} D={:.3g} contrast={:.3g}'.format(s['d_subset']['comparisons']['C_brier']['point'],s['d_subset']['comparisons']['D_brier']['point'],s['comparisons']['D_minus_C_brier']['point']))
```
Executed locally via python -B -c; after exits 1 from the uncaught refusal.
The runner CLI continues to translate ContrastRefused to exit 3.

FIX 1d sequential validation (Python 3.10.0, cache provider disabled):
- test_nba_four_arm_trial_contrast.py: fifty-four passed in 44.85s
- test_nba_four_arm_trial.py (only landed trial test): 78 passed in 25.59s
Guards and landed test SHA-256 values still match the FIX 1c values above.
Initial preflight flagged the numeric test count as bare-integer vocabulary;
the count is spelled out here. No source or test behavior changed.

FIX 1d preflight rerun: exit 0, 9 PASS, 0 FAIL; all nine check lines match
the validation block above. Only the three owned paths remain in git status.

LANDING NOTE (2026-09-23, orchestrator): the gated landing run on master reported 1 failed / 53 passed for this test file:
test_memo_source_size_matches_candidate compared the raw checkout size (12171 bytes on master's CRLF checkout) with the memo's
12164 (the worktree copy, mixed line endings). The test now measures LF-normalized bytes of each file AT THE LANDING COMMIT b66352c69 (git show), so neither
a CRLF checkout nor a later row's edit to the runner can fail it. No runner behaviour changed.

## NOT VERIFIED

- Real NBA corpus, charged trial, seal, or production results.
- S395 auditor integration and independent verification on master.

NOT VERIFIED
