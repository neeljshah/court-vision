GAP G340 | sport all | worktree a22 | log cx_g340_local_route_env

**ENVIRONMENT ROW (local; codex PREPARES, a finisher EXECUTES the environment probes; no src edits).**
`src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/`. NEVER
write `data/registry/`, never flip a flag, never install or uninstall packages in this row (propose the
exact pin change instead), never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL only (this box has more than one interpreter: conda `basketball_ai`
py3.10.20 / numpy 1.26.4 / torch 2.1.2+cu121 / cv2 4.13.0, and a system Python 3.10.0 / numpy 2.2.6 /
torch 2.2.0+cu121 / cv2 4.11.0 -- G62 and G333 recorded both). No pod, no GPU beyond an import.

**WHY THIS ROW EXISTS.** G333 (2026-09-08) found that NEITHER local interpreter can start the production
route unaided: in conda, `import onnx` raises `AttributeError` (ml_dtypes 0.3.2 lacks the 4-bit float
type) and `torch/onnx/_internal/onnxruntime.py` guards it with `except ImportError` only, so the error
escapes through torchvision and kills `from ultralytics import YOLO`; in the system Python, torchreid
imports tensorboard, which touches `np.bool8`, removed in numpy 2. Every local smoke this program runs
has been using an ad-hoc `sys.modules['onnx']` stub or the pod. S316 also needs the alternate
interpreter to run the sim. An environment that cannot import the route is a landmine for every local
measurement and for anyone cloning the repo.

**PREMISE (step 0, BINDING before-condition):** in each interpreter run
`python -c "from ultralytics import YOLO"` and `python -c "import src.tracking.osnet_reid"` (or the
route's re-ID import) and PRINT the full tracebacks (last 15 lines each). **If both interpreters import
both cleanly, the premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **DIAGNOSE.** For each failure name the exact package/version chain (`pip show` / `conda list` for
     onnx, ml_dtypes, torch, torchvision, ultralytics, torchreid, tensorboard, numpy) and the minimal
     repair: a pin change (e.g. `ml_dtypes>=0.4` or `onnx` upgrade for the conda env; a torchreid
     shim or `tensorboard` pin for the system env), or a guard in a harness-side import shim under
     `scripts/platformkit/env_shim.py` that pre-imports safely WITHOUT stubbing away real functionality
     (a stub that hides `onnx` is acceptable only when the route never exports ONNX -- state that from
     the code). Prefer the pin change; write it as a PROPOSED `environment_fix_2026-09-08.md` with the
     exact commands, NOT executed in this row.
  2. **SHIM + TEST (harness).** `scripts/platformkit/env_shim.py` (<= 120 lines): `prepare_route_imports()`
     that applies the minimal safe workaround for the detected environment and records what it did in
     the environment sidecar (`env_sidecar.py` from G62, additive key `import_shim`); a per-file test
     that, in the current interpreter, the route imports after the shim and that the shim is a no-op on
     an environment that imports cleanly (monkeypatched).
  3. **VERIFY ON BOTH INTERPRETERS (finisher).** Run the premise commands with and without the shim in
     both interpreters; table: interpreter, import, before, after, shim action taken (n = 2 x 2).
  4. **DOCUMENT.** Add the interpreter table and the pin proposal to the memo; record in
     `docs/evidence/tracking/ENVIRONMENT_NOTES.md` (<= 40 lines, new file) which interpreter every local
     measurement must use and how to check.

**HONEST LIMITATIONS to state, not discover:** a shim is a workaround, not a repair; the pin change is
proposed, not applied; the pod environment is separate (py3.12 / torch 2.8) and untouched.

ACCEPTANCE RULE:
  metric        = the two tracebacks; the diagnosis chain per interpreter; the shim + test; the 2 x 2
                  before/after table; the PROPOSED pin change; ENVIRONMENT_NOTES.md
  before        = neither interpreter starts the route unaided; smokes use ad-hoc stubs
  bar           = with the shim, `from ultralytics import YOLO` and the route's re-ID import succeed in
                  at least the conda interpreter (both if possible); the shim is a no-op on a clean
                  environment (test); 0 packages installed or removed
  n             = 2 interpreters x 2 imports
  eye check     = NONE. Say that.
  must not move = every installed package; `src/`; `data/`; the pod; every flag
  verdict       = **DONE** if the bar holds; **PARTIAL** with the interpreter that still fails and why.
EVIDENCE: `docs/evidence/tracking/g340_local_route_env_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `docs/evidence/tracking/g340_local_route_env_2026-09-08/
imports.csv` (integer cells zero-padded to 6 digits) + `ENVIRONMENT_NOTES.md`. **ADD ONE RESULTS_LEDGER.md
ROW IN THE SAME COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g340_env_shim.py`, alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone), the shim, the test and the memo
skeleton, and exits with `PREPARED FOR FINISHER` listing the exact commands; it must NOT run the
interpreter probes itself (Q1: measurements come after the sealed commit). A missing `data/registry` in
the worktree is expected.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
