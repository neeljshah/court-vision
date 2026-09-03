# S188 Preflight Tree Gate - 2026-09-04

Spec: `docs/evidence/tracking/specs/S188_spec.md`

Verifier contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and
Q1-Q9.

## Result

The local exhaustive CONSTRUCT meets the fixed bar. Before the change, the
step-3 boot gate exited nonzero in 2 of 8 tree-absence cases. After composing
the existing gate with the new tree gate, it exits nonzero in 8 of 8 cases.
The complete-tree control exits zero and prints `TREES: 8/8 OK`.

This metric closes tree ROOT absence only. A successful root import does not
prove that every module within the tree is present or current.

## Premise re-measurement

The premise was measured before production-code edits.

1. `load_profile("paper").specs()` supplies 14 `kind == "py"` ProcSpecs. The
   existing `pod_bootstrap_check.py --profile paper` gate checks only those 14
   module names through `profile_modules()` and `check_imports()`, and returns
   nonzero only when an import or requested functional probe fails.
2. The committed blocker harness produced the before column below: only `src`
   alone and the seven-root union failed closed.
3. With only `ops` blocked, the existing gate printed `14/14 OK`, but importing
   `supervisor.supervisor` exited 1. Its final exception line was verbatim:

       ModuleNotFoundError: No module named 'ops'

   `ModuleNotFoundError` is the `ImportError` subtype raised through
   `supervisor/supervisor.py` -> `heartbeat_reaper.py` -> the module-level
   `from ops.circuit_breaker import CircuitBreaker, OPEN`.

The premise therefore reproduced and the work proceeded.

## Complete-tree limit check

Before adding the gate, the seven roots and `supervisor.supervisor` all imported
successfully in one local interpreter. Total elapsed time was 0.113252 seconds.
The complete tree therefore did not false-alarm and import cost was not a local
bound.

## Exhaustive before/after table

Exit 0 means the composed step-3 gate would continue. Exit 1 means it would
stop before boot. The eight tree-absence cases enumerate each required root
alone plus their union.

| Case blocked by `sys.meta_path` | Existing gate exit | Composed gate exit |
|---|---:|---:|
| `ops` | 0 | 1 |
| `kernel` | 0 | 1 |
| `governance` | 0 | 1 |
| `data_registry` | 0 | 1 |
| `improve` | 0 | 1 |
| `frontend` | 0 | 1 |
| `src` | 1 | 1 |
| all seven roots | 1 | 1 |
| complete-tree control | 0 | 0 |

Before: 2/8 tree-absence cases exited nonzero.

After: 8/8 tree-absence cases exited nonzero. The control emitted exactly:

    TREES: 8/8 OK

Reproduction commands, from the repository root:

    python docs/evidence/harness/preflight_tree_gate_blocker.py --gate existing
    python docs/evidence/harness/preflight_tree_gate_blocker.py --gate existing --case ops --sharp --verbose
    python docs/evidence/harness/preflight_tree_gate_blocker.py --gate composed
    python docs/evidence/harness/preflight_tree_gate_blocker.py --gate composed --case control --verbose

The harness installs its blocker in the import-probe child, not in the outer
checker. This matches the process boundary of `check_imports()` and preserves
the existing gate's own setup.

## Change

`scripts/platformkit/ops/deploy_tree_gate.py` defines the named eight-module
tuple: the seven required tree roots and `supervisor.supervisor`. It passes the
whole tuple to the existing `pod_bootstrap_check.check_imports()` once, so all
imports happen in one child. It prints one summary line, prints one named line
per failure, and exits nonzero on any failure.

`scripts/platformkit/ops/pod_bootstrap.sh` invokes it as a second step-3 boot
gate immediately after the existing import gate, with the same stop-on-failure
shell shape.

The bootstrap echo and runbook step 3 now say to expect 14 children. The old 15
wording was consistent with counting the supervisor parent plus its 14 children
(S30). The echo is documentation, not a gate or acceptance criterion.

Files that would be deployed:

- `scripts/platformkit/ops/deploy_tree_gate.py`
- `scripts/platformkit/ops/pod_bootstrap.sh`

No deploy was performed.

## Closure context - descriptive only

One AST walker seeded the 14 ProcSpec modules. First-party means an import that
resolves to a `.py` file or package `__init__.py` under the repository root.
Module-level traversal includes the AST top-level body and bodies of top-level
`if`, `try`, `with`, `for`, `while`, and `class` statements; full traversal also
includes function bodies. The numerator is module-level closure and the
denominator is full closure. These shares are context, not the acceptance
metric.

| `from X import Y` convention | Module-level/full | Share | Unshipped-tree full modules | Lazy-only within those modules |
|---|---:|---:|---:|---:|
| resolve only `X` | 128/436 | 29.36 pct | 50 | 41 (82.00 pct) |
| also resolve `X.Y` when that submodule exists | 189/553 | 34.18 pct | 58 | 48 (82.76 pct) |

Under the expanded convention, 364 modules in the full closure are lazy-only.
They remain unloaded by design.

## Non-tautology and exclusions

The construct independently removes each of the seven top-level trees named by
the S188 row, then removes their union. The gate does not inspect the blocker or
derive its expected result from gate output.

Excluded and still uncaught:

- partial trees, including one absent or stale module beneath a present root;
- the 364 lazy-only modules in the expanded full closure;
- environment differences or stray namespace packages on the pod.

## Focused test

Only the one new per-file test was run:

    python -m pytest tests/platformkit/ops/test_deploy_tree_gate.py -q
    2 passed in 0.75s

It checks the exact eight-module tuple, the real complete-tree output, and a
simulated named failure with nonzero exit.

## Protected invariants

- `scripts/platformkit/ops/pod_bootstrap_check.py` is byte-identical to the
  checked-in version.
- The 14 ProcSpec names in `config/boot/paper.json` are unchanged.
- The seven functional probe names and `_PROBE_TIMEOUT_S = 60.0` are unchanged.
- The default `IMPORTS (%s): %d/%d OK` format and existing gate exit semantics
  are unchanged.
- The backtest trial-store path is absent in this worktree and remained absent;
  no row was appended and K was not read. Its external 18-row state was not
  opened or copied into this worktree.
- `data/registry/` was untouched and no feature flag was enabled.

## Verifier self-check

Section B:

- B1: clear. The denominator is the named exhaustive eight-case construct; no
  case was excluded.
- B2: clear. No schema, field, status, or reader changed.
- B3: clear. This boot check fails only for absent required deploy roots and
  does not quarantine an item.
- B4: clear. There is no claim/re-claim path.
- B5: clear. Nothing was copied to the pod.
- B6: clear. No module moved or retired; all references remain.
- B7: clear. There is no sampled head slice.
- B8: clear. There is no fitted residual.
- B9: clear. The seven roots plus their union are distinct and exhaustive.
- B10: clear. No existing threshold, probe timeout, or gate value moved.

Section Q:

- Q1: not applicable; this is an unscored construct, not a scored comparison.
- Q2: not applicable; no trial was charged and K remained unread.
- Q3: clear. The 8/8 plus 1/1 control bar is unchanged.
- Q4: not applicable; no OOS estimate or meta-learner is involved.
- Q5: not applicable; no comparative model verdict is made.
- Q6: clear. The memo uses operational and calibration-safe language only.
- Q7: clear. `n = 8 (CONSTRUCT)` is the exhaustive seven roots plus their union.
- Q8: clear. The 2/8 premise and complete-tree limit were re-measured first.
- Q9: not applicable; no scored differential or model state is involved.

## Not verified

- Nothing was measured on the pod.
- No pod files were copied and no process was started or stopped.
- Partial-tree and lazy-only module absence remain outside this gate.
- A pod-specific stray namespace package was not tested.
- The external 18-row backtest trial-store state was not present in this
  worktree; only its continued absence and zero local writes were checked.
