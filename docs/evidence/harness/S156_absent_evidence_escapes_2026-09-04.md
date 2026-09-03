# S156 -- route all three remaining absent-evidence escapes

Date: 2026-09-04. Lane: `track-a16`. Contract: `VERIFIER_CONTRACT.md` sections B and Q.

## Premise and scope

The three S156 branches were re-measured and confirmed: one private early return in
`test_ledger_schema_s13.py`, plus one existence-only skip in each of
`test_calibration_report.py` and `test_tick_informative.py`. All three could allow
missing required evidence to avoid a failure outside a structural worktree absence.

The metric is exactly these three named branches: before 0/3 routed through
`worktree_marker`; after 3/3. `n = 3 (CONSTRUCT)`. No branch is omitted.

## Change

- Ledger: `test_next_k_family_counts_aliased_rows_s89` now calls its existing
  `_require_real_ledger(path)` instead of returning when the file is absent.
- Calibration: added the existing `worktree_marker` import and local
  `_require_default_report_evidence(landed_path, cache_path)`.
- Tick: added the existing `worktree_marker` import and local
  `_require_requote_artifacts(spec)`.

The two local guards return only when all required paths exist. Otherwise they skip
only when `is_worktree_checkout()` is true; they call `pytest.fail` and name every
missing path in main-repository mode. There is no new shared helper.

## Before and after

| File / enumerated branch | Before | After | Main-evidence reproduction |
|---|---:|---:|---|
| `test_ledger_schema_s13.py` / aliased-family count | silent return | `_require_real_ledger(path)` | 8 original cases preserved; 1 S156 construct case added |
| `test_calibration_report.py` / default report reproduction | unconditional skip | marker-controlled local guard | 9 original cases preserved; 1 S156 construct case added |
| `test_tick_informative.py` / published-CI requote | unconditional skip | marker-controlled local guard | 17 original cases preserved; 1 S156 construct case added |

The pre-change main-repository commands were 8, 9, and 17 passed, respectively.
After the one mandated construct test per file, the modified-source runs against
the main repository's read-only evidence are 9, 10, and 18 passed. Thus every
pre-existing case still passes and no pre-existing case was added or removed.

## Main-evidence pytest outputs

The commands ran with working directory `C:\Users\neelj\nba-ai-system`, main-repository
evidence paths, and the modified worktree test module imported explicitly. The
temporary process patches only test-module evidence constants so the worktree source
uses the main repository's read-only evidence; it does not modify the main checkout.

```text
.........                                                                [100%]
9 passed in 0.72s
```

```text
..........                                                               [100%]
10 passed in 4.35s
```

```text
..................                                                       [100%]
18 passed in 2.18s
```

The corresponding commands are the three required per-file invocations with
`-q -p no:cacheprovider`.

## Two-mode construct outcomes

Each new test uses one deliberately absent path. With `FOUNDRY_WORKTREE=1`, it
observes `pytest.skip.Exception`; after removing that environment setting and
forcing main-repository marker mode, it observes `pytest.fail.Exception` naming
the absent path.

| File | Worktree outcome | Main-repository outcome |
|---|---|---|
| ledger | skip for absent `backtest_fwer.jsonl` | fail: `charge ledger absent` |
| calibration | skip for absent `artifact.json` and `combo` | fail naming `artifact.json` |
| tick | skip for absent `absent.csv` and `absent.json` | fail naming `absent.csv` |

Direct selection of the three new tests produced one pass in each file:

```text
1 passed, 8 deselected
1 passed, 9 deselected
1 passed, 17 deselected
```

## Read-only checks and scope

`backtest_fwer.jsonl` remains byte-identical: 18 nonblank rows, MD5
`a4ae7c13995672e478d59770591b83ba`. It was only read. No production module, flag,
registry, pod, or remote was changed. The three test files remain 111, 162, and 179
lines, all below the 300-line rail.

## Contract self-check

- B1: the metric enumerates all three named branches; none is excluded.
- B2: no schema, status, field, reader, or public interface changed.
- B3: this is the repaired condition; missing required evidence fails outside a
  structural worktree checkout.
- B4: no claim or retry lifecycle exists here.
- B5: no deployment occurred.
- B6: no module moved or retired; imports use the existing marker module.
- B7: no rendering or set sampling occurred.
- B8: no fitted or scored comparison occurred.
- B9: the denominator is the exhaustive named three-branch construct, not recycled.
- B10: no assertion, count, threshold, or bar in pre-existing tests moved.
- Q1, Q2, Q4, Q5, and Q9: no scoring, charged trial, held-out comparison, corpus
  comparison, or archived differential is involved.
- Q3: no bar or threshold changed.
- Q6: calibration-only wording is used; prohibited financial-performance language
  and retracted figures are absent.
- Q7: `n = 3 (CONSTRUCT)` is exhaustive; the S-row eye check is not applicable.
- Q8: the premise was re-measured and confirmed before the change.

## Not verified

- A verifier should rerun the three commands after the commit is applied in the
  physical main checkout. This lane kept that shared checkout unmodified while
  using its real evidence in a temporary test process.
- No visual review applies to this S-row.
