# S313 fix 3b -- the 14 pod-routed answer-package reader tests (2026-09-08)

The attempt-3 verifier's AST census over `tests/**/*.py` plus `scripts/platformkit/**/test_*.py`
finds 21 files that import a named module of the answers package directly (`receipt_guard`,
`resolver_registry`, `effect_graph`, `contract_client`). The census was reproduced here and returns
the same 21. The S313 spec WHERE clause routes "the answers files one at a time on the pod", so the
14 census members that live under `scripts/platformkit/answers/` are the pod set; the other 7 live
under `tests/` or at the `scripts/platformkit/` root and already carry local results in the memo.

The 7 local census members, for completeness: `scripts/platformkit/test_guard_invariants.py`,
`tests/platformkit/analytics_verify/test_answers.py`, `tests/platformkit/analytics_verify/test_system_map.py`,
`tests/platformkit/answers/test_atlas_resolver.py`, `tests/platformkit/answers/test_prediction_quality_resolver.py`,
`tests/platformkit/mcp_server/test_edge_refusal.py`, `tests/platformkit/test_s313_answers_label_survival.py`.

## How these were run (fix 3c, 2026-09-08) -- ROUTE A, `pod_run` with its linked data tree

Route A. `/c/Users/neelj/bin/pod_run a22 ... -- bash -c '<the 14 commands in sequence>'`, one
invocation per tree. The launcher ran to completion from this lane: its two `du` pre-flights took
about two minutes, it created a fresh job root under `/workspace/wt/a22/jobs/`, and -- the point of
this rerun -- it linked the real data tree into that job root:

```
PWD=/workspace/wt/a22/jobs/s313fix3c_cand2
lrwxrwxrwx 1 root root 29 Sep  8 09:31 data -> /workspace/nba-ai-system/data
Python 3.12.3
```

The same line, dated 09:37 with job id `s313fix3c_base`, opens the master log. `data/` was read
only; the tests that write fixtures write them to pytest's `tmp_path`, never below `data/`, so no
file under `/workspace/nba-ai-system` was created, changed or removed. No daemon was signalled;
`track_daemon` and `vol_guard.py` were not touched.

The pod's system interpreter still carries no `pytest`, and `pod_run` invokes `python` from the
system, so each command names the venv built for fix 3b instead:
`/workspace/wt/a22/s313_fix3b/venv/bin/python -m pytest scripts/platformkit/answers/<file>.py -q -p no:cacheprovider`.
`python -V` inside it: **Python 3.12.3**; pytest 9.1.1, pandas 2.3.3, numpy 2.1.2. That venv lives
in the fix-3b job root and was neither rebuilt nor modified here.

Two trees, both shipped by `pod_run`'s own manifest rule, differing only in the commit:

- candidate `bc78a7ab6`, shipped from the `a22` worktree
- master `0ed7bd4e3` (current `origin/master`), shipped from a `git archive 0ed7bd4e3` export
  placed in a scratch directory and handed to the launcher through `POD_WORKTREE`

`pod_run` walks `scripts/`, `tests/`, `domains/`, `kernel/`, `src/` for `.py` only, so the ship
list adds, identically for both trees: `--ship conftest.py pyproject.toml pytest.ini signals
domains scripts/platformkit/reference_baseline.json scripts/platformkit/eval_gate
scripts/platformkit/ingame scripts/platformkit/benchmarks`. A first pass without `signals` and
`domains` collected zero tests in all 14 files (`ModuleNotFoundError: No module named 'signals'`);
that pass is discarded and the list above is the one both trees ran.

## Result with the linked data tree, verbatim tail per file

| # | file (`scripts/platformkit/answers/`) | candidate `bc78a7ab6` | master `0ed7bd4e3` | same |
|---|---|---|---|---|
| 1 | `test_answer_consistency_intel.py` | 12 passed in 12.64s | 12 passed in 13.29s | yes |
| 2 | `test_answer_consistency_mlb.py` | 15 skipped in 2.32s | 15 skipped in 2.44s | yes |
| 3 | `test_answer_consistency_nba.py` | 15 skipped in 2.26s | 15 skipped in 2.21s | yes |
| 4 | `test_answer_consistency_soccer.py` | 9 skipped in 2.16s | 9 skipped in 2.35s | yes |
| 5 | `test_answer_consistency_tennis.py` | 10 skipped in 2.18s | 10 skipped in 2.44s | yes |
| 6 | `test_calibration_scoreboard_regex.py` | 1 failed, 3 passed in 2.28s | 1 failed, 3 passed in 2.41s | yes |
| 7 | `test_claims_resolver.py` | 3 failed, 15 passed in 2.47s | 3 failed, 15 passed in 2.57s | yes |
| 8 | `test_edge_calibration_guards.py` | 20 passed in 1.98s | 20 passed in 2.24s | yes |
| 9 | `test_effect_graph.py` | 10 passed in 2.48s | 10 passed in 3.66s | yes |
| 10 | `test_leaderboard_resolver.py` | 33 skipped in 2.19s | 33 skipped in 1.95s | yes |
| 11 | `test_leaderboard_team_scope.py` | 18 passed in 2.22s | 18 passed in 2.25s | yes |
| 12 | `test_mechanism_effect.py` | 20 passed in 1.96s | 20 passed in 2.28s | yes |
| 13 | `test_player_compare.py` | 13 passed in 3.31s | 13 passed in 2.27s | yes |
| 14 | `test_resolver_registry_routing.py` | 37 passed in 2.22s | 37 passed in 2.35s | yes |

Every one of the 14 exists on master, so no file is reported "not on master".
Totals with the linked data tree: candidate 148 passed, 4 failed, 82 skipped; master 148 passed,
4 failed, 82 skipped. Summed pytest time: 42.7 s on the candidate, 44.7 s on master.
NO file is red on the candidate and green on master; there is no candidate-only red.

## The 4 reds and the 82 skips, named honestly, and WHY the linked tree did not clear them

Both trees fail the SAME four tests, by name, so no red is candidate-only and nothing in this lane
is attributable to the attempt-3 extraction:

```
FAILED scripts/platformkit/answers/test_calibration_scoreboard_regex.py::test_calibration_number_nba_returns_real_data_not_no_data
FAILED scripts/platformkit/answers/test_claims_resolver.py::test_list_claim_families_real_repo_ok
FAILED scripts/platformkit/answers/test_claims_resolver.py::test_list_claim_families_sport_filter
FAILED scripts/platformkit/answers/test_claims_resolver.py::test_resolve_routes_list_vs_wrap
```

The counts equal the fix-3b subset run exactly, and the reason is now measured rather than
assumed. The skips gate on `contracts._load_df(sport)`, which globs
`data/cache/profiles/<sport>_*_profiles.parquet` (`scripts/platformkit/profiles/ask.py:35,70`); the
claims reds read `data/cache/intel_claims/`. With the tree linked, both paths were probed directly
on the pod:

```
$ ls -d /workspace/nba-ai-system/data/cache/profiles
ls: cannot access '/workspace/nba-ai-system/data/cache/profiles': No such file or directory
$ ls /workspace/nba-ai-system/data/cache/intel_claims
ls: cannot access '/workspace/nba-ai-system/data/cache/intel_claims': No such file or directory
```

So the corpora these files need are absent from the pod's OWN data tree, not merely from a shipped
subset. That is the honest scope of this evidence: the data-backed readers were exercised against
the linked tree, and the tree does not carry the built profile parquets or the claims store, so 82
assertions remain gated and 4 stay red for corpus absence on BOTH commits. NOT FIXED IN THIS LANE
and NOT diagnosed further: this lane supplies results, and a source change to a red that neither
the candidate introduced nor the correction named would be out of scope.

## SUPERSEDED -- the fix-3b direct-ssh subset run (no linked data tree)

Kept for the record. The attempt-3 verifier rejected this table on B2 because the tree carried no
`data/`, so the data-backed reader behaviour was unchecked. The table above replaces it. Its claim
that the launcher is blocked is left as written: it was true for the run it describes, and gap
S313-POD-LAUNCHER-BLOCKED is still carried on the codex side, but route A worked from this lane.

## How these were run

Pod, reached over ssh directly (the `pod_run` launcher is still blocked -- gap
S313-POD-LAUNCHER-BLOCKED stands). Job root `/workspace/wt/a22/s313_fix3b/`; nothing under
`/workspace/nba-ai-system` was written or read for these runs, and no daemon was signalled.
The pod's system interpreter carries no `pytest`, so an isolated
`python -m venv --system-site-packages /workspace/wt/a22/s313_fix3b/venv` was created inside the job
root and `pytest` installed into it alone; the system interpreter and the deployed tree were left
untouched. `python -V` inside that venv: **Python 3.12.3**; pytest 9.1.1, pandas 2.3.3, numpy 2.1.2.

Two trees, shipped with `git archive ... | ssh ... tar -x`, differing only in the commit:

- `cand` = candidate `bbc05837c`
- `base` = `origin/master` `6097645ed`

Ship path list, identical for both trees, grown by running one file and reading the ImportError
until every import resolved: `scripts/platformkit/**/*.py` + `scripts/platformkit/*.py` +
`scripts/platformkit/**/*.json` + `scripts/platformkit/**/*.yaml`, `scripts/__init__.py`,
`conftest.py`, `pyproject.toml`, `pytest.ini`, `signals/`, `domains/`. `data/` is gitignored and is
therefore absent from both trees, which is why the corpus-backed files skip identically on both.

Command, one file per invocation, from the tree root:
`python -m pytest scripts/platformkit/answers/<file>.py -q -p no:cacheprovider`

## Result, verbatim tail per file

| # | file (`scripts/platformkit/answers/`) | candidate `bbc05837c` | master `6097645ed` | same |
|---|---|---|---|---|
| 1 | `test_answer_consistency_intel.py` | 12 passed in 18.04s | 12 passed in 78.89s | yes |
| 2 | `test_answer_consistency_mlb.py` | 15 skipped in 3.46s | 15 skipped in 8.69s | yes |
| 3 | `test_answer_consistency_nba.py` | 15 skipped in 1.91s | 15 skipped in 8.31s | yes |
| 4 | `test_answer_consistency_soccer.py` | 9 skipped in 2.33s | 9 skipped in 9.90s | yes |
| 5 | `test_answer_consistency_tennis.py` | 10 skipped in 2.07s | 10 skipped in 11.00s | yes |
| 6 | `test_calibration_scoreboard_regex.py` | 1 failed, 3 passed in 2.29s | 1 failed, 3 passed in 12.49s | yes |
| 7 | `test_claims_resolver.py` | 3 failed, 15 passed in 2.61s | 3 failed, 15 passed in 8.90s | yes |
| 8 | `test_edge_calibration_guards.py` | 20 passed in 2.16s | 20 passed in 11.99s | yes |
| 9 | `test_effect_graph.py` | 10 passed in 2.55s | 10 passed in 11.01s | yes |
| 10 | `test_leaderboard_resolver.py` | 33 skipped in 1.64s | 33 skipped in 8.80s | yes |
| 11 | `test_leaderboard_team_scope.py` | 18 passed in 1.54s | 18 passed in 8.41s | yes |
| 12 | `test_mechanism_effect.py` | 20 passed in 1.56s | 20 passed in 8.80s | yes |
| 13 | `test_player_compare.py` | 13 passed in 1.24s | 13 passed in 8.98s | yes |
| 14 | `test_resolver_registry_routing.py` | 37 passed in 1.75s | 37 passed in 12.30s | yes |

Every one of the 14 exists on master, so no file is reported "not on master".
Totals: candidate 148 passed, 4 failed, 82 skipped; master 148 passed, 4 failed, 82 skipped.
Wall time, the 14 files end to end including ssh: 72 s on the candidate, 348 s on master.
The two wall-clock columns differ only because the master pass ran on a colder page cache; the
counts, which are the measurement, are identical.

### The 4 reds, named honestly (superseded wording)

Both trees fail the SAME four tests, by name, so no red is candidate-only and nothing in this lane
is attributable to the attempt-3 extraction:

```
FAILED scripts/platformkit/answers/test_calibration_scoreboard_regex.py::test_calibration_number_nba_returns_real_data_not_no_data
FAILED scripts/platformkit/answers/test_claims_resolver.py::test_list_claim_families_real_repo_ok
FAILED scripts/platformkit/answers/test_claims_resolver.py::test_list_claim_families_sport_filter
FAILED scripts/platformkit/answers/test_claims_resolver.py::test_resolve_routes_list_vs_wrap
```

These four, and the 82 skips, are the same corpus-absence surface: `data/` is not in the git tree,
so the shipped subset carries no built parquet and no claims store. They are a property of the
shipped subset, not of the candidate diff. NOT FIXED IN THIS LANE and NOT diagnosed further here:
this lane supplies results, and a source change to a red neither the candidate introduced nor the
correction named would be out of scope.

Vocabulary follows contract Q6; automated scan required.
