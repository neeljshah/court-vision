# S686 cloud result 2026-09-30 -- landed Hansen SPA vs arch 8.0.0 SPA cross-check

Row: S686 (QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2; one-off override section 3a). Branch
`cloud/S686-2026-09-30`. Spec: `S686_spec_2026-09-30.md` (AMENDMENT 1 + builder note). This compares
p-value methods only. It makes no scored claim, and no model is compared to any venue.

## Licence (read first)
arch 8.0.0 wheel, `dist-info/licenses/LICENSE.md`: NCSA (University of Illinois/NCSA style; the
metadata says `License-Expression: NCSA`), copyright Kevin Sheppard. It is permissive: use, copy
and modify are allowed as long as the notice is kept. Dev use is permitted, so the row is NOT
LICENCE_BLOCKED. arch is pinned only in `requirements-oracles-dev.txt` and is imported only in
`scripts/platformkit/oracles/`.

## Reviewers (codex not available)
All three were independent Opus sub-agents spawned by this run. None of them wrote the code.
- Pre-build critic: REVISE with 12 items, all folded into AMENDMENT 1.
- CONTRACT tier: ACCEPT WITH CORRECTIONS. The one correction was that this memo was missing; it is written now.
- ADVERSARIAL tier: ACCEPT WITH CORRECTIONS. It ran 16 mutants and 15 were killed. M5 (a change to
  the kernel restart probability) survived. The builder then added
  `test_kernel_variance_equals_arch_internal_variance`, which asserts equality with arch's own
  `_loss_diff_var` to 1e-12, and re-ran M5 in a scratch copy: KILLED (1 failed, 22 passed). The
  builder also added `test_verdict_rule_is_literal_two_decimals`. Before that test, M7b and M10
  were caught only by the byte comparison with the tracked artifact.
- These fixes were test-only, so there was no re-verify round. Neither tier returned REJECT.

## Result (seed 2718, B = 2000, mean block 5 = the landed defaults; n = 7 fixtures (CONSTRUCT))
| fx | K | games | P0 landed | P_arch | delta | R1 | R2 | verdict | largest component |
|---|---|---|---|---|---|---|---|---|---|
| F1 | 1 | 200 | 0.066967 | 0.063500 | +0.003467 | 0 | 0 | EXPLAINED | c_rng -0.003 |
| F2 | 5 | 200 | 0.001000 | 0.000500 | +0.000500 | 0 | 0 | EQUAL_2DP | - |
| F3 | 8 | 200 | 0.000500 | 0.273000 | -0.272500 | 0 | 0 | EXPLAINED | c_P5 (studentization) +0.273 |
| F4 | 3 | 200 | 1.000000 | 0.845500 | +0.154500 | 0 | 0 | EXPLAINED | c_P3 -0.993, c_P4 +0.843 (truncation ties) |
| F5 | 4 | 150 | 0.579210 | 0.599000 | -0.019790 | 0 | 0 | EXPLAINED | c_rng +0.029 |
| F6 | 4 | 60 | 0.000500 | 0.001500 | -0.001000 | 0 | 0 | EQUAL_2DP | - |
| F7 | 3 | 200 | 0.163918 | 0.389000 | -0.225082 | 0 | 0 | EXPLAINED | c_P6b (kernel-variance recentring) +0.225 |

The row verdict is PASS: R1 = R2 = 0 on all 7 fixtures, and every fixture is EQUAL_2DP or EXPLAINED.

What the numbers mean:
- arch 8.0.0 `SPA.compute()` does not studentize its statistic. The `studentize` flag only feeds
  the recentring variance. So arch's "consistent" p is not Hansen's studentized T^SPA.
- The two p-values differ materially when candidate variances differ (F3), when every
  candidate's mean is below zero (F4: the landed max(0, .) truncation gives p = 1), and when
  losses are serially dependent (F7).
- At alpha 0.05 the two decisions disagree on F3 only. This is for information; it is not a bar.

## Artifacts
- `tests/platformkit/oracles/fixtures/S686_crosscheck_2026-09-30.json`. It holds every rung and
  component, the versions, `spa_test_sha256` b9c86896...56c6 and `fixture_sha256` bb6eacb4...ae89.
- The fixtures are in `tests/platformkit/oracles/fixtures/s686_loss_matrices.json`.
- Both files live under tests/ because .gitignore:588 ignores harness JSON and force flags are banned.

## Commands and counts (one file per process)
- `python3 tools/desk_bin/run_files.py . tests/platformkit/oracles/test_spa_arch_crosscheck.py` -> 23 passed
- `python3 tools/desk_bin/run_files.py . scripts/platformkit/eval_gate/test_spa_test.py` -> 4 passed (landed code, unchanged)
- `python3 tools/desk_bin/run_files.py . tests/platformkit/test_loc_rail_scope.py` -> 1 passed
- `PYTHONPATH=. python3 -m scripts.platformkit.oracles.spa_arch_crosscheck --check` -> ARTIFACT_MATCH

## NOT VERIFIED
- Windows or laptop re-run (Python 3.10). The artifact must be byte-identical under the pins in
  requirements-oracles-dev.txt; a different numpy may change the generator stream.
- No real archived loss differentials were used (they do not exist; see S675). The fixture loss
  matrix is tracked, so the construct acceptance itself is fully verified here.
- MCS and StepM are not compared: the desk has no MCS or StepM code to cross-check.

PORTABLE: yes.

NEW GAP lines (from the reviewers; none is rowed, ids come from the orchestrator):
- arch 8.0.0 SPA is unstudentized and returns NaN for n < 16. A studentized external oracle, or
  a hand-computed Hansen reference, is still missing.
- hansen_spa silently drops zero-variance columns from the family maximum.
- Rung P6a (ddof) is 0 on every fixture. c_P3 and c_P4 are each exercised by one fixture only (F4).
- The landed helpers (stationary_indices, studentized_stats, game_cluster_matrix) are checked
  only by the sha pin, not against an independent implementation.
