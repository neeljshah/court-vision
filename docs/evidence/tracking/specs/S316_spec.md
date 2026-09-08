GAP S316 | sport nba | worktree a2 | log cx_s316_mc_cross_env

**HARNESS ROW (S register).** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/ingame/`. NEVER write `data/registry/`, never flip a flag, never claim an edge
(calibration language only), never edit a landed memo, `docs/evidence/HARNESS_GAPS_2026-09-03.md` or
`docs/evidence/RESULTS_LEDGER_SYSTEM.md` (the lander appends; put the proposed ledger line in the memo).

**WHERE THIS ROW RUNS:** LOCAL for the local arms (conda `basketball_ai` = py3.10.20 / numpy 1.26.4 /
torch 2.1.2+cu121 -- confirm and print; this box has more than one interpreter) and the pod for the pod
arm (`/workspace/wt/a2/` scratch; never touch `track_daemon` or the guards; CPU only, nice -n 19; each ssh
call < 9 min; nohup detached). The S287 repeatability harness (`scripts/platformkit/ingame/`,
`test_s287_sim_full_pod.py`, artifacts under `docs/evidence/harness/S287_repeatability_2026-09-08/`)
already runs the 30-cluster restriction in ~1 min locally and ~20 min on the pod; reuse it.

**WHY THIS ROW EXISTS.** S287 fix 1b proved the possession simulator byte-repeatable inside one
environment but different across the pod (py 3.12.3, torch 2.8.0+cu128, numpy 2.1.2, 128 threads) and
the local box on 171/180 ticks (max 0.0418 on simulator ECE), acting on `p_simulator` only. G62 recorded
both environments (`docs/evidence/tracking/g62_environment_sidecar_2026-09-08/environment*.json`) and
named the candidate keys: numpy, torch, torch threads, cpu_count, python, scipy. Until the source is
localised, the S266 1e-9 replay bar cannot be met or honestly re-specified.

**PREMISE (step 0, BINDING before-condition):** re-run the 30-cluster restriction LOCALLY once and
confirm it reproduces the S266 archive to 1e-9 (S287's LOCAL-1 result); PRINT the max diff. **If it
does not reproduce, the premise is FALSE (the local environment moved): STOP, write the memo with the
environment sidecar, commit, report PREMISE FALSE.**

METHOD (one variable per arm; every arm on the SAME machine as its control; n = 180 ticks each):
  1. **THREADS (local).** Re-run locally with `OMP_NUM_THREADS=MKL_NUM_THREADS=1`, and with
     `torch.set_num_threads(1)` and `(128)` if the CPU allows; compare to LOCAL-1 tick by tick. If any
     thread setting moves `p_simulator`, the sim is order-dependent under multithreaded reductions:
     name the reduction (which torch/numpy call) by bisecting with a deterministic-algorithms flag
     (`torch.use_deterministic_algorithms(True)`) and report.
  2. **NUMPY / TORCH VERSION (local, isolated env).** If a second local interpreter exists (G62 found
     py 3.10.0 / numpy 2.2.6 / torch 2.2.0+cu121 on this box), run the restriction there and compare:
     this isolates library versions from hardware. Print both environment sidecars.
  3. **POD THREADS (pod).** Re-run on the pod with `OMP_NUM_THREADS=1` and `torch.set_num_threads(1)`;
     compare to POD-1 (byte-identical expected if threads are not the cause) and to LOCAL-1.
  4. **RNG CONSUMPTION AUDIT (code, read-only).** Cite `file:line` for every random draw in the sim path
     (`src/sim/basketball_sim.py`, `fast_sim.py`, the S256 module): generator type, seeding, and whether
     the number of draws per tick can depend on a floating-point comparison (a threshold crossing that
     differs at the 1e-16 level flips a branch and shifts the stream). Name the first branch that could.
  5. **DECISION TABLE (prereg it).** threads move it -> cause = reduction order; version arm moves it
     with threads fixed -> cause = kernel/library version; neither -> cause = fp comparison branch on
     hardware-specific rounding (step 4 names it). For the named cause, state the additive fix (e.g.
     compute `p_simulator` in float64 with a fixed reduction order, or round the compared quantity to
     1e-9 before the branch) and implement it under `scripts/platformkit/ingame/` behind a flag default
     OFF, then show the flag-ON arm reproduces across environments to 1e-9 on the 180 ticks. If no fix is
     found, propose the re-specified bar (within-environment 1e-9 + reported cross-environment delta).

**HONEST LIMITATIONS to state, not discover:** 180 ticks are the restriction, not the 2,130-tick
construct; a fix that changes `p_simulator` at the 1e-4 level changes S287's BEHIND numbers slightly and
must be reported as such (never re-scored here); the pod's 128 threads cannot be reproduced locally.

ACCEPTANCE RULE:
  metric        = per arm: max |delta p_simulator| vs its control, ticks differing > 1e-9 (n=180),
                  simulator Brier/ECE deltas; the RNG audit table; the decision reached; the flag-ON
                  cross-environment result if a fix exists
  before        = cross-environment delta 0.0418 max on sim ECE, 171/180 ticks; cause unattributed
  bar           = the cause is named by measurement (an arm that moves it, or the audited branch) and
                  the decision table row is stated; if a fix is implemented it reproduces to 1e-9 across
                  environments with the flag ON and is byte-neutral with the flag OFF
  n             = 180 ticks per arm; every random draw site in the audit
  eye check     = NONE. Say that.
  must not move = every S287 number and bar; every flag default; `src/`; `data/`; the pod daemon and
                  guards; `docs/evidence/HARNESS_GAPS_2026-09-03.md`; `docs/evidence/RESULTS_LEDGER_SYSTEM.md`
  verdict       = **DONE** if the cause is named and the decision row stated; **PARTIAL** with the arms
                  that could not run (say why).
EVIDENCE: `docs/evidence/harness/S316_mc_cross_env_2026-09-08.md` (<= 60 lines; VERDICT line 1; arm table;
audit table; decision; NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S316 | <finding with n> | <VERDICT>`) + the per-arm tick CSVs under
`docs/evidence/harness/S316_mc_cross_env_2026-09-08/` (each <= 5 MB) + both environment sidecars.
TEST: `tests/platformkit/test_s316_mc_cross_env.py` (the tick comparer on a hand-pinned construct; the
flag-OFF byte-neutrality if a fix exists) plus `scripts/platformkit/ingame/test_s287_sim_full_pod.py`,
each alone. **NEVER a full pytest.** Every new file <= 300 lines.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
