GAP G347 | sport all | worktree a22 | log cx_g347_env_shim_regression

**ENVIRONMENT FIX ROW (local; codex PREPARES, a finisher EXECUTES the interpreter probes; no src edits).**
`src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/`. NEVER write
`data/registry/`, never flip a flag, never install or uninstall a package (propose the pin instead), never
touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL only, both interpreters: conda `basketball_ai` (py3.10.20 / numpy 1.26.4 /
torch 2.1.2) at `C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe` and the system Python 3.10.0
(numpy 2.2.6 / torch 2.2.0) at `C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe`. No pod.

**WHY THIS ROW EXISTS.** G340 (2026-09-08, ACCEPT WITH CORRECTIONS, PARTIAL) landed `scripts/platformkit/
env_shim.py` whose `_onnx_preflight` catches only `ModuleNotFoundError` and `AttributeError`; in the system
interpreter `import onnx` raises a plain `ImportError` (`cannot import name 'builder' from
'google.protobuf.internal'`, a protobuf / onnx version mismatch), which escapes `prepare_route_imports()` and
turns a CLEAN system YOLO import (before_ok = 1) into a failure (after_ok = 0). A shim that regresses a
working environment is worse than no shim. The 2 x 2 table must be: conda 2/2 after, system no worse than
before, and the shim a strict no-op wherever the route already imports.

**PREMISE (step 0, BINDING before-condition):** in the system interpreter run `python -c "from ultralytics
import YOLO"` (expect success) and `python -c "import scripts.platformkit.env_shim as s; s.prepare_route_imports();
from ultralytics import YOLO"` (expect the ImportError); PRINT both tails. **If the second already succeeds, the
premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **PROBE-FIRST SHIM.** `prepare_route_imports()` first tries the route imports untouched (in a subprocess
     or guarded import); if they succeed it records `import_shim: none` in the sidecar and returns without
     touching `sys.modules`. Only on failure does it apply the ml_dtypes / onnx stub, and `_onnx_preflight`
     catches `ImportError` (the superclass) too, recording the exception class and message in the sidecar.
  2. **NO-REGRESSION TEST.** `tests/platformkit/test_g347_env_shim_no_regression.py`: with a monkeypatched
     clean environment the shim is a no-op (sidecar says none); with a monkeypatched `onnx` that raises a
     plain `ImportError` the shim applies the stub and the route import proceeds; the existing
     `test_g340_env_shim.py` still passes unchanged.
  3. **PIN PROPOSAL.** Extend the landed PROPOSED `environment_fix_2026-09-08.md` (append a dated section,
     never rewrite it) with the protobuf / onnx pin that resolves the system interpreter's mismatch (name the
     exact versions from `pip show protobuf onnx` in that interpreter; state it is unexecuted).
  4. **2 x 2 RERUN (finisher).** Same table as G340 (interpreter x import, before / after, shim action), both
     interpreters, real subprocess probes; tracebacks saved under the artifact directory.
  5. CHANGE NOTHING ELSE. `ENVIRONMENT_NOTES.md` gets a dated 3-line addendum at most.

**HONEST LIMITATIONS to state, not discover:** a shim is a workaround; the pin is proposed, not applied;
the system interpreter's torchreid / numpy 2 failure (G340) is untouched by this row unless the pin resolves it.

ACCEPTANCE RULE:
  metric        = the premise tails; the 2 x 2 table before / after; the shim action per cell; the tests;
                  the pin proposal section
  before        = system YOLO 1 -> 0 after the shim (G340 imports.csv row 3)
  bar           = no cell regresses (after_ok >= before_ok for all 4); conda stays 2/2; the no-op test and
                  the G340 test pass; 0 packages installed or removed
  n             = 2 interpreters x 2 imports
  eye check     = NONE. Say that.
  must not move = every installed package; `src/`; `data/`; every flag; the landed G340 memo and artifacts
  verdict       = **DONE** if the bar holds; **PARTIAL** with the cell that still fails and why.
EVIDENCE: `docs/evidence/tracking/g347_env_shim_regression_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; SHA-256s) + `docs/evidence/tracking/g347_env_shim_regression_2026-09-08/imports.csv`
(integer cells zero-padded to 6 digits) + tracebacks. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT**
(one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g347_env_shim_no_regression.py` and `tests/platformkit/test_g340_env_shim.py`,
each alone. **NEVER a full pytest.** Every new file <= 300 lines; `env_shim.py` stays <= 150 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone), the shim change, the tests and the memo
skeleton, and exits `PREPARED FOR FINISHER` listing the exact probe commands; it must NOT run the interpreter
probes itself (Q1). A missing `data/registry` in the worktree is expected.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
