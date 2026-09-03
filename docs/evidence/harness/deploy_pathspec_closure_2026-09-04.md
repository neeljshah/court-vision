# S187 paper-profile deploy pathspec closure

Remeasurement: 2026-09-03T13:50:22-05:00 (workspace clock)

The artifact filename is the path fixed by the S187 specification.

Verdict: ACCEPT

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Specification: `docs/evidence/tracking/specs/S187_spec.md`.

## Premise remeasurement

The premise was remeasured before implementation. The roots were the 14 Python
process modules returned by `load_profile("paper").specs()`. The static walk
parsed `ast.Import`, absolute `ast.ImportFrom`, and, in the required variant,
each `from X import Y` as the candidate module `X.Y`. A name counted only when
it resolved to a `.py` or `__init__.py` file below the repository root or
`scripts/platformkit`. The repository root was searched first.

The required variant reproduces 524 unique resolved modules across 11
module-bearing top-level trees. The limit variant without the submodule probe
finds 406 unique resolved modules across the same 11-tree set. The tree sets
agree, so the specification permits a derived pathspec.

| top-level tree | with submodule probe | without submodule probe | named by current shell pathspec |
|---|---:|---:|---|
| data_registry | 2 | 2 | no |
| domains | 72 | 67 | yes |
| frontend | 23 | 23 | no |
| governance | 4 | 2 | no |
| improve | 8 | 7 | no |
| kernel | 1 | 1 | no |
| ops | 9 | 4 | no |
| predict_service | 53 | 50 | yes |
| scripts | 330 | 229 | yes |
| src | 9 | 9 | no |
| supervisor | 13 | 12 | yes |
| **total** | **524** | **406** | **4 of 11** |

The current command in `scripts/platformkit/ops/pod_bootstrap.sh:13` names
`scripts/platformkit supervisor predict_service domains config`. Normalized to
module-bearing top-level trees, this is 4 of 11; `config` holds no closure
module. The command in
`docs/evidence/harness/S21b_full_parity_deploy_2026-09-03.md:219` and the delta
scope in `docs/evidence/harness/S21c_delta_deploy_2026-09-03.md:46` cover the
same four module-bearing trees.

The exact omitted set is:

```text
data_registry frontend governance improve kernel ops src
```

Those seven trees contain 56 of 524 closure modules, or 10.69 percent. No tree
was excluded after its result was observed. The denominator is every
module-bearing top-level tree reached by the declared closure walk; external
modules do not resolve in-repository, and data-only `config` is not a closure
tree.

## Additive change

`scripts/platformkit/ops/deploy_pathspec.py` derives the closure from the boot
profile at call time. It contains no literal list of the 11 deployment trees.

- `deploy_trees("paper")` returns all 11 derived trees.
- `--emit` prints a pathspec containing all 11 trees.
- `--check` parses the existing `git archive HEAD` command from
  `pod_bootstrap.sh`, exits 1, and prints exactly the seven omitted trees.

The emitted helper pathspec covers 11 of 11 closure trees. The existing shell
command remains unchanged at 4 of 11; this lane does not wire or run a deploy.

## Reproduction

```powershell
python -c "from scripts.platformkit.ops.deploy_pathspec import closure_counts; print(closure_counts('paper')); print(closure_counts('paper', submodule_probe=False))"
python scripts/platformkit/ops/deploy_pathspec.py --profile paper --emit
python scripts/platformkit/ops/deploy_pathspec.py --profile paper --check
python -m pytest tests/platformkit/ops/test_deploy_pathspec.py -q
```

Observed output:

```text
--emit: data_registry domains frontend governance improve kernel ops predict_service scripts src supervisor
--check: OMITTED: data_registry frontend governance improve kernel ops src
--check exit: 1
test: 1 passed, 5 warnings in 13.06s
```

The warnings are pre-existing `DeprecationWarning` reports from
`scripts/platformkit/improve/improvement_trend.py`; the S187 files do not edit
that module.

## Protected-file check

The following baseline SHA-256 values were captured before implementation.
The S187 commit keeps each path byte-identical to its parent:

| path | baseline SHA-256 |
|---|---|
| `scripts/platformkit/ops/pod_bootstrap.sh` | `3B3E978098EA46EE3A07C8264A83844A3E09C29A5415EB2B193ED927C0CDBD2E` |
| `scripts/platformkit/ops/pod_bootstrap_check.py` | `A4EC2B946CAECB105AE6F677A6C20D9D15FE58C9D567F7B11CA4FDE05D088DE9` |
| `config/boot/paper.json` | `BAE553372D03AC5AA05D89E55CE92C714458B1EC0AA6ABC57381001CF82ED4E4` |
| `supervisor/stack_specs.py` | `B0AAB598E21B34F2557AE7EA70A5792E886D3ED0264821CBD447598ED2CC9316` |
| `.gitignore` | `E659233446B21EDD6A7DF00245A58547956C16DA15D0A10A616C644782982ABF` |

`data/cache/eval_gate/backtest_fwer.jsonl` was absent before implementation. It
remains an absence condition: this work did not create or write any file under
`data/`.

An unrelated concurrent worktree edit changed `pod_bootstrap.sh` after the
baseline capture. It is not staged for S187. Parent-versus-S187 commit-tree
comparison, rather than the shared worktree bytes, is therefore the protected
file check for this lane.

## Contract self-check

| line | result |
|---|---|
| B1 | Pass: the denominator includes every resolved top-level tree; no failed tree was removed. |
| B2 | Pass: the change is additive and changes no schema or reader field. |
| B3 | Not applicable: no quarantine or absent-evidence gate is introduced. |
| B4 | Not applicable: no claiming workflow is introduced. |
| B5 | Pass: no remote access, copy, or deploy occurred. |
| B6 | Pass: no module was moved or retired. |
| B7 | Not applicable: the construct enumerates the full closure, not a sample. |
| B8 | Not applicable: no fitted residual or model comparison is used. |
| B9 | Pass: the 11 units are exhaustive top-level closure trees, not recycled identifiers. |
| B10 | Pass: no threshold, bar, or existing gate changed. |
| Q1 | Not applicable: this is a construct measurement, not a scored comparison. |
| Q2 | Not applicable: no trial was charged and K was not read. |
| Q3 | Pass: every specification bar is unchanged. |
| Q4 | Not applicable: no out-of-sample score or meta-learner is used. |
| Q5 | Not applicable: no AHEAD result is claimed. |
| Q6 | Pass: the new artifacts use system-coverage and calibration-safe wording only. |
| Q7 | Pass: `n = 11 (CONSTRUCT)` and all 11 trees are enumerated. |
| Q8 | Pass: the premise and both resolver variants were remeasured before implementation. |
| Q9 | Not applicable: no scored per-unit loss series exists for this construct. |

## Not verified

- On-pod file presence and behavior are not verified; remote access was
  forbidden and was not attempted.
- No operational deployment was run.
- The emitted pathspec is not yet consumed by `pod_bootstrap.sh`; the existing
  shell command remains unchanged.
- Runtime dynamic imports and relative imports are outside the specification's
  static absolute-import closure.
- Importability and functional behavior of all 524 modules are not established
  by this pathspec-enumeration result.
