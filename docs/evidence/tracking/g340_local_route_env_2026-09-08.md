VERDICT: PARTIAL -- with the shim, both conda imports succeed (n=2/2) and the no-op-on-clean-preflight test passes; the system interpreter does not clear the bar (n=0/2 after shim) because the shim's own onnx preflight raises an uncaught ImportError before either downstream import runs, and it actively REGRESSES system YOLO, which imported cleanly (with a non-fatal numpy-ABI warning) before the shim was applied.

# G340 Local Route Environment -- measured

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections A, B and Q. EYE CHECK: NONE.
Prereg `docs/evidence/tracking/g340_prereg_2026-09-08.md`, seal `b024ba52bfda1b38e06038d28b79d8f86c79ee21820fd542c7544e245104dcd7`.
Premise held (not all four before-imports succeeded): conda YOLO fails, conda osnet_reid succeeds, system YOLO succeeds, system osnet_reid fails.

## Diagnosis chains (pip show; pin changes unexecuted)
conda basketball_ai: onnx 1.20.1, ml-dtypes 0.3.2, torch 2.1.2+cu121, torchvision 0.16.2+cu121, ultralytics 8.4.21, torchreid NOT INSTALLED, tensorboard 2.15.2, numpy 1.26.4.
system python: onnx 1.17.0, ml-dtypes 0.3.2, torch 2.2.0+cu121, torchvision 0.17.0+cu121, ultralytics 8.3.64, torchreid 0.2.5, tensorboard 2.10.1, numpy 2.2.6.
conda YOLO before: `ImportError: cannot import name 'YOLO' from 'ultralytics'` (no chained AttributeError surfaced at this call site; full text `tracebacks/conda_yolo_before.txt`). system osnet_reid before: `AttributeError: module 'numpy' has no attribute 'bool8'` via tensorboard->torchreid (`tracebacks/system_osnet_before.txt`), matching the G333 diagnosis. system YOLO before succeeded with a non-fatal `UserWarning: Failed to initialize NumPy: _ARRAY_API not found` (`tracebacks/system_yolo_before.txt`).

## 2x2 table (before -> after; shim action)
| interpreter | import | before_ok | after_ok | shim action |
|---|---|---|---|---|
| conda basketball_ai | YOLO | 000000 | 000001 | onnx_stub_for_mldtypes_attribute_error |
| conda basketball_ai | osnet_reid | 000001 | 000001 | onnx_stub_for_mldtypes_attribute_error |
| system python | YOLO | 000001 | 000000 | shim raised (see below) |
| system python | osnet_reid | 000000 | 000000 | shim raised (see below) |

## System after-shim: named exception (why it still fails)
`env_shim._onnx_preflight` catches only `ModuleNotFoundError` and `AttributeError`; the system interpreter's `onnx` import raises a plain `ImportError: cannot import name 'builder' from 'google.protobuf.internal'` (protobuf/onnx version mismatch, unrelated to ml_dtypes), which is NOT caught. `prepare_route_imports()` therefore raises before either `from ultralytics import YOLO` or `import src.tracking.osnet_reid` runs (`tracebacks/system_yolo_after.txt`, `tracebacks/system_osnet_after.txt`, identical). This is a NEW GAP for a future row, not fixed here: the preflight needs a bare `except ImportError` (superset of `ModuleNotFoundError`) guarded the same way, or a scoped `except Exception` limited to the `onnx` import line.

Pin proposal: `environment_fix_2026-09-08.md` (unexecuted). `ENVIRONMENT_NOTES.md` already states system stays unapproved pending a clean after-shim row; that prediction is now confirmed measured, not just asserted -- no edit needed.

## NOT VERIFIED
- Why conda's before-traceback shows a plain `ImportError` rather than the AttributeError chain G333 recorded; not re-diagnosed here (out of scope for the finisher row).
- Whether upgrading `ml_dtypes`/`onnx` (conda) or `tensorboard` (system) per the PROPOSED pins would also clear the system protobuf `ImportError`; not executed, 0 packages touched.
- The shim's `except ImportError` gap above; named, not patched, in this row.
- No pod, no GPU, no video; installed packages, `src/`, `data/`, flags and `TRACKING_GAPS_2026-09-01.md` untouched.

WALL TIME: about 40 minutes of lane time, entirely local; 0 GPU seconds, 0 pod commands. TEST (each alone, `-q -p no:cacheprovider`, conda interpreter): `test_g340_env_shim.py` 3 passed | `test_g62_environment_sidecar.py` 7 passed | `test_loc_rail_scope.py` 1 passed. Never a full pytest.
ARTIFACT SHA-256 (LF-normalised): `env_shim.py` `b4454c35ee54500f6e42cd91ef6f1e2c4a584a2ffcec3323059af455f53e874a` | `imports.csv` `de471be4e49ec2fd69d9493d1feb5e34695342702b8f1704df741948dd3063af` | conda `environment.json` `6176e9789984e70fb01f82ad291d6a2c266b4087b78d7a79da8ff8b3c05c9210` | system `environment.json` `5854c612535bac10ee3b7a6bef00a0fae8b83c460facdfa93bbfb467e4aa0800`.
Vocabulary follows contract Q6; automated scan required.
