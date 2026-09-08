VERDICT: DONE -- no cell regresses (after_ok >= before_ok in all 4), conda stays 2/2 after, both
focused tests pass in conda, 0 packages installed or removed.

# G347 Env Shim Regression -- measured
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections A and B. EYE CHECK: NONE.
Prereg `docs/evidence/tracking/g347_prereg_2026-09-08.md`, seal `97f525f09511027f6d4592bdb68f40e2a2a4790183d4ce6731b42bdfecd5fcbf`.

## Premise (system interpreter; PYTHONPATH=worktree root, fresh subprocess each)
Plain `from ultralytics import YOLO`: succeeds (non-fatal numpy-ABI warning), `tracebacks/premise_system_plain.txt`.
OLD (pre-G347, `git show ea33d9625:scripts/platformkit/env_shim.py`) shim then the same import: FAILS,
uncaught `ImportError: cannot import name 'builder' from 'google.protobuf.internal'` inside
`_onnx_preflight` before the route import runs (`tracebacks/premise_system_old_shim.txt`) -- reproduces
G340's regression, premise TRUE for the pre-fix shim. NEW probe-first shim then the same import:
SUCCEEDS, `shim_action=none` (child YOLO probe is clean, `_onnx_preflight` never runs),
`tracebacks/premise_system_new_shim.txt`.

## 2 x 2 table (before -> after; shim action)
| interpreter | import | before_ok | after_ok | shim action |
|---|---|---|---|---|
| conda basketball_ai | YOLO | 000000 | 000001 | onnx_stub_for_mldtypes_attribute_error |
| conda basketball_ai | osnet_reid | 000001 | 000001 | onnx_stub_for_mldtypes_attribute_error |
| system python | YOLO | 000001 | 000001 | none |
| system python | osnet_reid | 000000 | 000000 | none |

System YOLO no longer regresses (was 1->0 in G340; now 1->1, the fix). System osnet_reid is unchanged
(0->0): its `AttributeError: module 'numpy' has no attribute 'bool8'` comes from torchreid/tensorboard,
unrelated to onnx; probe-first shim never touches it (`shim_action=none` both cells). Full table:
`imports.csv`; tracebacks under `tracebacks/`.

## Pin proposal and notes addenda
`environment_fix_2026-09-08.md`: original 21 lines byte-identical to landed G340 (diffed against
38e9cc3c4); lane appended one dated section, never rewrote it. Confirmed via system `pip show protobuf
onnx`: protobuf 3.19.6, onnx 1.17.0, matching the appended proposal (`protobuf==3.20.3`, unexecuted).
`ENVIRONMENT_NOTES.md`: 3-line dated addendum appended, prefix byte-identical to 38e9cc3c4.

## Tests (conda, each alone, `-q -p no:cacheprovider --basetemp=verify_tmp_g347/...`)
`test_g347_env_shim_no_regression.py` 2 passed | `test_g340_env_shim.py` 3 passed (unchanged) |
`test_loc_rail_scope.py` 1 passed. `env_shim.py` 58 lines (<= 150).
Report-only, system interpreter (pytest 9.0.2 present, not installed here): `test_g340_env_shim.py`
1 passed, 2 failed -- `test_known_mldtypes_attribute_error...` fails because probe-first short-circuits
`_onnx_preflight` (system YOLO's own subprocess probe is clean) before the monkeypatched
`import_module` runs, an old single-path test not a regression; `test_current_route_imports_after_
preparation` fails on the pre-existing system `numpy.bool8` osnet_reid gap above. Neither is in the
acceptance bar (prereg binds conda only).
## NOT VERIFIED
- A shim is a workaround, not a repair; production route files are unchanged.
- The protobuf/onnx pin is proposed only, unexecuted; whether it also fixes system osnet_reid's
  unrelated numpy.bool8/torchreid path is untested.
- The system interpreter's torchreid / numpy 2 failure (G340/G333) stands untouched.
- The system-interpreter run of `test_g340_env_shim.py` was never in the acceptance bar; report only.
WALL TIME: 2026-09-08, UTC 18:11-18:16 for the interpreter probes (per-file tests ~1 min more); local
only, 0 GPU seconds, 0 pod commands, 0 packages installed or removed.
SHA-256 (LF-normalised): `env_shim.py` d8d3fbd7aafe0923e6dfaf4291a4f2a201cb4bb5b5dbc7d1c794cd692ca31e7b |
`test_g347_env_shim_no_regression.py` 8e97258f5478263b08de28df7f4e1b6ef5257ceaf97cdb5a0de501166773b5cc |
`imports.csv` 41aeb7009827c858efaa6f44070266fe7ba02f83bf0457cdf8cdde7897c39334 | conda `environment.json`
2e189b11ddba0c5eb3ca7c73b03d0fd1a5a1a0a66ea841044676c9ea0de03cfb | system `environment.json`
b5b2da982601a3c47378418e9679940a1a8df73eb52971248ebf0c2b2379a46a | `environment_fix_2026-09-08.md`
febe8b9dec2e514a15e82300817ac270746a89d47a36ce624bba1279bf8a67ba | `ENVIRONMENT_NOTES.md`
ddbbd0e16f6f91af998b901ea01c2afdc9a50b6ca19bb6318491677194381c81
Vocabulary follows contract Q6; automated scan required.
