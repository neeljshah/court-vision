# S499 arm E paper-night declaration

PASS: 490 tests across 24 C5 files; contract preflight 9/9. CONSTRUCT evidence only.
Machine: local Windows worktree `C:/Users/neelj/nba-harness-h142`.
Binding spec: `docs/evidence/tracking/specs/S499_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, B and Q.
Pinned preflight base: `a2b9396e0ed59833e40207fa670bba76f503e020`.

## Scope and declaration

Preserved the supplied budget change: `ceiling_bytes.e = 629145600` and
`deadline_s.e = "1800"`, with no other budget changes. Preserved all three
supplied test conversions. Added a normalized-byte assertion to the capacity
conversion after review found that parsed JSON equality alone weakened its
original byte pin. No production Python module was changed or created: S499's
CHANGE owns the budget, seven existing tests, and this memo only.

The new plan is qualification, fill_realism, week, scoreboard, history, e.
The final command uses the existing committed producer arguments, including
the unformatted served-schedule template and the declared E output root.
No new JSON seal or fixture path was added. New `.gitattributes` patterns: none.
S499 supplies no REAL ROW; the existing construct fixtures remain in use.

## Before-condition reproduced before edits

Commands used `python -m pytest <file> -q -p no:cacheprovider`.
The following are quoted failure summaries from this session:

```text
tests/platformkit/execution/test_paper_night_inputs.py
FAILED ...::test_1_gate[committed]
E       AssertionError: assert 6 == 5
1 failed, 39 passed in 23.09s

tests/platformkit/execution/test_paper_night_inputs_e2e.py
FAILED ...::test_real_children_and_fresh_process_consumer
FAILED ...::test_sunday_fill_excludes_monday_scoreboard_reads_it
assert code == 0
E       assert 3 == 0
2 failed, 9 passed in 13.12s

tests/platformkit/execution/test_scoreboard_history_e2e.py
FAILED ...::test_case15_step_argv_skips_and_case16_actual_plan_handoff
E         Left contains one more item: 'e'
1 failed, 12 passed in 8.11s

tests/platformkit/ops/test_s485_baseline_contract.py
FAILED ...::test_frozen_module_bytes_and_inputs_tests
E           AssertionError: scripts/platformkit/execution/paper_night_budget.json
1 failed, 3 passed in 2.00s
```

Exactly five expected failures across four files. The first two baseline
processes briefly overlapped; all final C5 runs were sequential, one file per
pytest invocation. No whole-suite invocation was used.

## Both e2e root causes and resolution

Read both generated night records before editing:
`test_real_children_and_fresh_p0/docs/evidence/forward/nights/2026-09-24.json`
and `test_sunday_fill_excludes_mond0/docs/evidence/forward/nights/2026-09-27.json`
under the temporary pytest-10969 construct directory. Durable diagnostic
excerpts from both records are identical:

```json
{"name":"e","step_status":"RAN","reason":"child_nonzero_exit","exit_code":2}
{"state":"REFUSED","reason":"caller_policy_uncommitted","counts":{"refused":1}}
```

Both parent records have `status = PARTIAL` and
`reasons = ["child_nonzero_exit"]`. All five earlier steps have
`step_status = RAN`, `reason = null`, and `exit_code = 0`.
The construct root lacks the committed
`docs/evidence/forward/scoreboard/CALLER_POLICY_E_2026-09-30.json`.
The other E seals are likewise not installed there. The first failing check is
`registry_scorer_e_night.py:153`, reached through `_caller` at line 238;
it happens before the effective-date check or population read.

Resolution: retain these historical construct dates and assert the exact
named refusal, its count, E's absent output, and parent exit 3. Do not substitute
an E success. Snapshot the five earlier receipts immediately when `_run`
returns; assert the final record retains every field unchanged after E runs.
Check each earlier exit, reason, error count, artifact presence, size and hash.
Retain the fresh-process consumer's input-window and sport-dispatch checks,
and the Sunday fill exclusion / Monday scoreboard inclusion assertions.

MANDATORY DISCLOSURE: a sole E nonzero refusal makes the production parent
exit 3 with PARTIAL. `paper_night.py:179-180` assigns `child_nonzero_exit`;
line 286 requires every row to be RAN with no reason; line 296 returns 3
otherwise. The construct tests exercise this exact parent behavior.
An E `config_not_effective` receipt is a distinct case: with valid seals,
`registry_scorer_e_night.py:248-251` writes that receipt and returns 0.
It does not alone trigger the parent's nonzero-exit path.
Per the spec, the orchestrator is to land after the 2026-09-29 night so the
first intended effective night is 2026-09-30. This lane did not deploy or arm
an unattended run.

## Landed interfaces read before coding

Exact signatures relied on, quoted from their implementations:

```python
# scripts/platformkit/execution/paper_night.py
def _steps(root: Path, day: str, as_of: str, nonce: str, budget: dict, context: dict | None = None) -> list[dict]:
def _run(step: dict, root: Path, budget: dict) -> dict:
def main(argv: list[str] | None = None, *, steps: list[dict] | None = None) -> int:
# scripts/platformkit/execution/registry_scorer_e_night.py
def e_step(root: Path, day: str, as_of: str, p: dict, raw: dict) -> dict:
# scripts/platformkit/execution/scoreboard_history.py
def history_step(root: Path, day: str, as_of: str, p: dict, raw: dict) -> dict:
# scripts/platformkit/execution/paper_night_inputs.py
def record_inputs(plan: dict, rows: list[dict]) -> dict:
# scripts/platformkit/execution/paper_night_steps.py
def scoreboard_step(root: Path, day: str, as_of: str, sports: list, p: dict, raw: dict) -> dict:
def scoreboard_row_updates(out: Path, before: int | None, reason: str | None) -> dict:
# tests/platformkit/execution/test_paper_night.py
def write(path, value):
def fake(name="qualification", code=0, size=0, status="COMPLETE", out=None):
```

The existing CHILD and LEGACY_NIGHT_CHILD constructs were read at their
definitions. They continue to replace qualification/week/history and select
the legacy scoreboard policy; fill and E execute their landed CLIs.
No new landed-module import was introduced.

## Converted assertions

Paths below are relative to `tests/platformkit/`.

| File:line | Before | After |
| --- | --- | --- |
| execution/test_paper_night.py:163 | Declared names exclude E. | Same names plus E. |
| execution/test_paper_night.py:164 | All ceilings equal the prior value; E deadline absent. | Existing ceilings unchanged; E tuple exactly (629145600, "1800"). |
| execution/test_registry_scorer_e_night_1a.py:168 | E absent from both maps. | E ceiling and deadline exact; input-root assertion retained. |
| execution/test_registry_scorer_e_night_capacity.py:212 | SHA equality with pinned budget bytes. | Remove exactly E's two declarations; parsed equality and LF-normalized byte equality to fixed base. |
| execution/test_paper_night_inputs.py:252 | Five calls for committed, zero otherwise. | Exact six ordered names with E last, empty list otherwise. |
| execution/test_scoreboard_history_e2e.py:232 | Five planned names. | Same names plus E last. |
| execution/test_scoreboard_history_e2e.py:233 | Last step equals history builder result. | Penultimate step equals the same result. |
| execution/test_scoreboard_history_e2e.py:234 | No E argv assertion. | Full E command, output and skip equality. |
| execution/test_scoreboard_history_e2e.py:240 | Scoreboard history checked through index -2. | Same assertion through index -3, preserving scoreboard identity. |
| execution/test_paper_night_inputs_e2e.py:155 | Fresh consumer requires COMPLETE. | Requires PARTIAL with exactly child_nonzero_exit; existing consumer checks retained. |
| execution/test_paper_night_inputs_e2e.py:206 | First historical construct requires exit 0. | Exact E refusal and exit 3; every earlier step successful and artifact intact. |
| execution/test_paper_night_inputs_e2e.py:227 | Sunday construct requires exit 0. | Same exact refusal checks; existing cross-day assertions retained. |
| ops/test_s485_baseline_contract.py:100 | Every frozen source equals pinned text. | All still equal; budget removes only the two exact E tokens before byte-equivalent text comparison, with strict int and semantic checks. |

The additional receipt equality is at
`execution/test_paper_night_inputs_e2e.py:146`; the shared refusal assertions
start at line 189. Budget byte pins use
`70e299544f0b6817aa6595714d73ea363c8e8b27` and
`2132fcf64c7039c4ea51097b7de96b85aa790bbe`, never a moving branch reference.
No working-copy module length or digest was pinned.

## Validation

All C5 invocations used `python -m pytest <one file> -q -p no:cacheprovider`,
sequentially. Every invocation exited 0, with zero failed or skipped cases.
Execution test paths below have prefix `tests/platformkit/execution/` unless
the full ops path is shown.

| Test file | Passed |
| --- | ---: |
| test_ingame_scoreboard_night.py | 31 |
| test_paper_night.py | 39 |
| test_paper_night_deadline.py | 20 |
| test_paper_night_deadline_1b.py | 9 |
| test_paper_night_deadline_1c.py | 3 |
| test_paper_night_e_step_e2e.py | 41 |
| test_paper_night_inputs.py | 40 |
| test_paper_night_inputs_e2e.py | 11 |
| test_paper_night_qualification_isolation.py | 2 |
| test_paper_night_scoreboard_step.py | 14 |
| test_paper_night_scoreboard_step_1c.py | 4 |
| test_paper_night_scoreboard_step_1d.py | 2 |
| test_paper_night_scoreboard_step_1e.py | 1 |
| test_paper_night_scratch.py | 19 |
| test_paper_night_steps.py | 56 |
| test_registry_scorer_e_night.py | 33 |
| test_registry_scorer_e_night_1a.py | 13 |
| test_registry_scorer_e_night_1b.py | 15 |
| test_registry_scorer_e_night_capacity.py | 33 |
| test_registry_scorer_e_night_fields.py | 52 |
| test_registry_scorer_e_night_fixture.py | 16 |
| test_registry_scorer_e_night_replay.py | 19 |
| test_scoreboard_history_e2e.py | 13 |
| tests/platformkit/ops/test_s485_baseline_contract.py | 4 |
| Total | 490 |

S476 C14 remains covered by `test_paper_night_e_step_e2e.py`: the capacity
mapping does not reach `build_population`. No threshold was altered.
All owned files are ASCII and at most 300 lines using `len(text.splitlines())`.
`git diff --check` passed. The final worktree change inventory contains only
the nine paths owned by the spec. No new CLI was created; `--help` succeeded
for `scripts.platformkit.execution.paper_night`,
`scripts.platformkit.execution.registry_scorer_e_night`, and
`scripts.platformkit.tracking.contract_preflight`.

Preflight command, using the pinned base required by S499 RULES(3,5):

```text
python -m scripts.platformkit.tracking.contract_preflight --paths
  scripts/platformkit/execution/paper_night_budget.json
  tests/platformkit/execution/test_paper_night.py
  tests/platformkit/execution/test_registry_scorer_e_night_1a.py
  tests/platformkit/execution/test_registry_scorer_e_night_capacity.py
  tests/platformkit/execution/test_paper_night_inputs.py
  tests/platformkit/execution/test_paper_night_inputs_e2e.py
  tests/platformkit/execution/test_scoreboard_history_e2e.py
  tests/platformkit/ops/test_s485_baseline_contract.py
  docs/evidence/harness/S499_arm_e_activation_2026-09-28.md
  --base a2b9396e0ed59833e40207fa670bba76f503e020
  --spec docs/evidence/tracking/specs/S499_spec.md
PASS vocab clean over 9 files
PASS crlf no index-side CRLF over 9 file(s); 1 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 5 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

Preflight's threshold check is mechanical and vacuous for this spec format;
C1 tests provide the exact budget assertions. No new scoring claim is made.
The fixed source pins and explicit constructed refusals satisfy the applicable
B/Q checks without changing runtime validation or population handling.

## NOT VERIFIED

- The first unattended E night on 2026-09-30.
- Real archive performance, runtime resource bounds or any scored comparison.
- Deployed inputs, scheduling, or service state; no network or pod access.
- Successful E scoring in these two historical e2e constructs: they assert a
  named refusal. Successful construct E paths belong to the existing C5 tests.
- Independent verifier acceptance and lane_commit; no commit was created.
