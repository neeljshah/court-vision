# S60 -- repo-integrity audit of `scripts/**/_*.py` (2026-09-03)

Verdict: **ACCEPT**. Calibration language only. Nothing here is scored, priced,
promoted or charged; this row measures TRACKEDNESS and IMPORTABILITY.

Follow-up to the S21b new gap: `.gitignore:342` (`scripts/**/_*`) kept three
helper modules the pod imports permanently undeployable, so 10 of S21b's 49 pod
import failures had one cause that no `git archive` method could fix.

## 1. ACCEPTANCE RULE (as applied)

    metric        = untracked scripts/**/_*.py modules that a TRACKED module
                    imports / all such modules
    before        = 6 / 6 untracked (every one ignored by .gitignore:342)
    bar           = 0 untracked; the 10 pod importers go 0/10 -> 10/10 OK; the
                    ~181 scratch helpers stay untracked (the original rule keeps
                    its protection); a regression test fails if the count rises
    n             = 187 (CONSTRUCT, every untracked `_*.py` under scripts/ on
                    disk) x 8,246 (CONSTRUCT, every tracked `.py` in the repo,
                    scanned for an import of each)
    eye check     = n/a (S-row); REPRODUCTION = section 7
    must not move = supervisor 19236 and its 14 children, track daemon 4035,
                    mlb capture 21620 / 21622; no threshold, gate value, flag or
                    ledger row is touched by this row

RESULT: **PASS** -- 6/6 now tracked, pod 0/10 -> 10/10, 181 scratch files still
ignored, test passes.

NON-TAUTOLOGY: the untracked denominator (187) was enumerated from disk BEFORE
any import scan, and the import scan ran over EVERY tracked `.py` in the repo
(8,246), not only the ones already suspected. No file was dropped after seeing
its classification.

## 2. Step 0 -- tracked vs on disk

    git ls-files scripts | grep -E '/_[^/]*\.py$'        -> 129
    ... minus __init__.py (the S46a negation)            ->   9 tracked
    find scripts -name '_*.py' -not -path '*/__pycache__/*' \
        -not -name '__init__.py'                         -> 196 on disk

**196 - 9 = 187 untracked.** (The 9 already tracked are `bot_guards/_plan_*`,
`bot_guards/_state`, `diagnostics/_bench_run`, `analytics_showcase/_clone_safe`
and the four `validate/_*` helpers -- each admitted by an earlier per-path or
per-directory negation.)

## 3. Classification of the 187

Every tracked `.py` in the repo was parsed line by line for an import statement
naming one of the 187 module stems, then resolved three ways: absolute
(`from scripts.a.b._h import`), relative (`from ._h import`, only when the
importer sits in the helper's own directory) and implicit same-directory
(`from _h import`, the `sys.path` form).

| class | n | disposition |
|---|---|---|
| IMPORTED-BY-TRACKED | **6** | must be tracked -- fixed here |
| scratch / unreferenced | **181** | left untracked, deliberately |
| gated-tree, imported-by-tracked | **0** | nothing to report |

### The 6 (each with a real tracked importer)

| helper | LOC | tracked importers |
|---|---|---|
| `scripts/_pts_oof_harness.py` | 231 | `exp_lowshrink_pts_reb.py:48`, `exp_regime_pts_reb.py:40` + `:46`, `exp_stack_pts_reb.py:50`, `exp_transform_pts_reb.py:32` |
| `scripts/ingame/_ingame_fast_harness.py` | 115 | `ingame/analyze_routed_residuals.py:12`, `ingame/audit_ensemble_optimality.py:35` + `:430` |
| `scripts/pit/_scratch_ben_ortho.py` | 331 | `pit/validate_vac_stack_feature.py:41` (`from _scratch_ben_ortho import build_signals`, a same-dir `sys.path` import) |
| `scripts/platformkit/autonomy/_monitor_merge_helpers.py` | 161 | `autonomy/autonomy_monitor_runner.py:59` |
| `scripts/platformkit/data_frontier/_politeness.py` | 49 | `an_public_splits.py:46`, `bbref_advanced.py:34`, `frontier_probe_job.py:32`, `milb_statsapi.py:41`, `savant_bat_tracking.py:31`, `statsbomb_open_full.py:28`, `understat_xg.py:37` |
| `scripts/platformkit/improve/_market_metrics.py` | 97 | `improve/per_market_ledger.py:26`, `improve/test__market_metrics.py:12`, `tests/platformkit/improve/test_per_market_ledger.py:33` |

Three of the six are the ones S21b named. The other three
(`_pts_oof_harness`, `_ingame_fast_harness`, `_scratch_ben_ortho`) sit OUTSIDE
the pod deploy set, so the pod sweep could not see them; they break a fresh
clone all the same.

### Gated trees

`scripts/team_system/**` is human-gated and holds 7 untracked helpers
(`_audit_build_joined`, `_audit_phase3_grade`, `_audit_phase4_clv`,
`_audit_phase6_oos`, `_audit_phase6_skeptics`, `_audit_truncation_invariance`,
`_mine_lineup_chemistry`). **None is imported by any tracked module**, so there
is nothing this lane would have had to stage there. REPORTED, not staged.

`scripts/platformkit/ingame/_materialize_soccer_xgloc.py` also has no tracked
importer and stays untracked.

## 4. The change -- one explicit negation block

Added after the S46a line, at `.gitignore:350-361`: a five-line comment plus
**six `!<path>` lines, one per helper**. Deliberately NOT a blanket
`!scripts/**/_*.py`, which would re-admit all 181 scratch files and destroy the
original rule's purpose. Nothing else in `.gitignore` was touched.

`git check-ignore -v`, before and after:

| path | before | after |
|---|---|---|
| `scripts/_pts_oof_harness.py` | `.gitignore:342:scripts/**/_*` | `.gitignore:356:!scripts/_pts_oof_harness.py` |
| `scripts/ingame/_ingame_fast_harness.py` | `.gitignore:342` | `.gitignore:357` (negated) |
| `scripts/pit/_scratch_ben_ortho.py` | `.gitignore:342` | `.gitignore:358` (negated) |
| `scripts/platformkit/autonomy/_monitor_merge_helpers.py` | `.gitignore:342` | `.gitignore:359` (negated) |
| `scripts/platformkit/data_frontier/_politeness.py` | `.gitignore:342` | `.gitignore:360` (negated) |
| `scripts/platformkit/improve/_market_metrics.py` | `.gitignore:342` | `.gitignore:361` (negated) |

Protection intact -- spot-checked after the change, all still ignored by
`.gitignore:342`: `scripts/_scratch_oof_diagnose.py`, `scripts/_tmp_inspect.py`,
`scripts/team_system/_audit_phase6_oos.py`,
`scripts/platformkit/ingame/_materialize_soccer_xgloc.py`.

Secrets scan of the 6 before staging: `api_key|secret|token|password|bearer|
AKIA|sk-...|xox.-` matched twice, both in `_scratch_ben_ortho.py` and both the
loop variable `token` over a position string. No credential. Q6 scan
(`roi|bankroll|pnl|profit|edge`) matched once, in the safety header of
`_monitor_merge_helpers.py` ("Calibration not edge") -- a retraction context.

Commit `7541ceabe`, 8 files, 1,079 insertions, 0 paths under `data/` or
`vault/`, 0 under a gated tree.

## 5. Fresh-worktree proof

`git worktree add --detach <tmp> HEAD` at the new commit, then from inside that
clean checkout with `PYTHONPATH=<tmp>`:

    import scripts.platformkit.data_frontier._politeness        -> OK
    import scripts.platformkit.improve._market_metrics          -> OK
    import scripts.platformkit.autonomy._monitor_merge_helpers  -> OK

Each `__file__` resolved to the worktree's own copy, not the main repo's.
Worktree removed and pruned afterwards (`git worktree remove`, no `--force`).

## 6. Pod -- md5 parity and the 10 imports

Reached with `ssh -o BatchMode=yes -o ConnectTimeout=20 -F ~/.ssh/config.pod pod`
(port resolved from the alias, today 40193 -- it drifts). Every pid below read
from `/proc`, never `pgrep`/`ps`. No git ran on the pod.

Deployed the **3** helpers that fall inside S21b's deploy set
(`scripts/platformkit/**`):

    git archive HEAD <3 paths> | ssh ... pod 'tar -x --no-same-owner -C /workspace/nba-ai-system'

The other 3 (`scripts/_pts_oof_harness.py`, `scripts/ingame/_ingame_fast_harness.py`,
`scripts/pit/_scratch_ben_ortho.py`) are outside that deploy set and were deliberately NOT shipped --
adding files beyond the parity-defined set would be an unmeasured change to pod
state. They are a fresh-clone fix, not a pod fix.

All 3 were **ABSENT** on the pod before (`ls` confirmed). After, CRLF-normalised
md5 local-vs-pod diffs to 0 lines -- **3/3 identical**:

| file | md5 (both sides) |
|---|---|
| `improve/_market_metrics.py` | `7c517f808592c99b8436a6b6a513928a` |
| `data_frontier/_politeness.py` | `ae783d1616b3d5542c0912861b265aae` |
| `autonomy/_monitor_merge_helpers.py` | `f11204f293d78e020a65287b0e8ba930` |

The 10 failing importers, run one per subprocess under `/usr/local/bin/python`
(the interpreter the supervisor uses) with a 60 s timeout, driver list kept at
`/tmp/s60_mods.txt` and never written into the repo tree (B5):

    BEFORE  OK=0  FAIL=10
    AFTER   OK=10 FAIL=0

The 10 (7 + 1 + 2, exactly S21b's split): `data_frontier.an_public_splits`,
`.bbref_advanced`, `.frontier_probe_job`, `.milb_statsapi`,
`.savant_bat_tracking`, `.statsbomb_open_full`, `.understat_xg`;
`autonomy.autonomy_monitor_runner`; `improve.per_market_ledger` and
`improve.segmented_ledger_tick` (the second reaches `_market_metrics` through
`per_market_ledger`, which is why S21b counted 2 for `improve`).

**Nothing was killed, started or restarted.** By the S21b one-hop rule -- each
of the 14 profile children's own module plus every module it imports directly,
intersected with the 3 files this deploy changed -- **0 of 14** children need a
bounce, so none was bounced. Verified alive from `/proc` after the lane:
supervisor **19236** with 14 children (19596-19606, 152399 `pm_trading.auto_loop`,
154885 `predict_service.scheduler`, 24212 `predict_service.app`), track daemon
**4035**, mlb capture **21620 / 21622**. Another session's
`tracking_corpus_worker` (161769) and `foundry.seed_queue` (160505) also
untouched.

## 7. Test

`tests/platformkit/ops/test_private_helpers_tracked.py` (83 lines) enumerates
every untracked `scripts/**/_*.py` from disk, resolves importers with one
`git grep`, and fails listing each offender. It reads `git ls-files`, so a
helper that stops being tracked regresses it.

    before the six were staged  -> 1 failed, naming all 6 with 14 importer lines
    after                       -> 1 passed  (1.37 s)

A5 readers re-run unchanged in master: `tests/platformkit/ops/test_prepush_guard.py`
**5 passed**, `tests/platformkit/improve/test_per_market_ledger.py` **34 passed**.

Reproduction:

```bash
cd /c/Users/neelj/nba-ai-system
git ls-files scripts | grep -E '/_[^/]*\.py$' | grep -v __init__ | wc -l   # 15
find scripts -name '_*.py' -not -path '*/__pycache__/*' -not -name '__init__.py' | wc -l  # 196
python -m pytest tests/platformkit/ops/test_private_helpers_tracked.py -q   # 1 passed
```

## 8. NOT VERIFIED

- Trackedness is not correctness. The 6 helpers were staged as they stand on
  disk; none was read for defects, none has a test of its own, and
  `_scratch_ben_ortho.py` is **331 lines**, over the 300-LOC rail -- it is
  pre-existing code admitted to git, not new code written by this lane.
- The import scan is STATIC and syntactic. A helper reached only by
  `importlib.import_module(<computed string>)`, `exec`, a subprocess call or a
  path manipulation the scanner cannot see would be classified as scratch and
  left untracked. Lines were matched only when they begin `from ` / `import `
  (plus `import_module` / `__import__` in the audit script).
- The 181 "scratch / unreferenced" are unreferenced BY A TRACKED MODULE. Many
  are imported by other untracked scratch files; that graph was not walked.
- Only 3 of the 6 reached the pod. A pod that later needs
  `_pts_oof_harness`, `_ingame_fast_harness` or `_scratch_ben_ortho` still has
  nothing, and no lane has measured whether it does.
- The fresh-worktree check imported 3 of the 6, not all 6, and importability
  there proves resolution, not behaviour.
- The one-hop bounce rule is the rule applied, and it is stated rather than
  assumed complete: a transitive-only dependency on one of the 3 new files
  could in principle exist. It would have been crashing before this deploy,
  since all 3 files were absent -- but that argument was not exhaustively
  checked against every child's full import closure.
- No per-file test was run on the pod. `pod_bootstrap_check --profile paper` was
  NOT re-run this lane (no child changed, so nothing would have been rearmed).
- The pod is pinned to `7541ceabe` for these 3 files only and drifts with the
  next landing. Full-tree parity was not re-measured; only these 3 were.
- No `data/registry/` write, no ledger charge, no K read, no flag flipped on,
  no threshold or bar moved, no gate re-run, no `--force`, nothing under
  `data/` or `vault/` staged, and no file under a human-gated tree edited or
  staged.
