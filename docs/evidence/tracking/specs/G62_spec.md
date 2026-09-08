GAP G62 | sport all | worktree a4 | log cx_g62_run_environment_stamp
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including the NEW A7 clause;
self-check every line of section B before you report. Small, additive, and it closes a hole that
cost this program a whole day of confusion.
PREMISE (step 0, reproduce it): G52 recorded "the tennis pipeline is NOT REPRODUCIBLE run to run"
from a pair of local runs whose coverage differed on 7 of 15 ranges. On the pod the same pipeline
is EXACTLY reproducible -- 30 of 30 repeats bit-identical across gpu_baseline, gpu_pinned and
cpu_pinned, with byte-identical frame decode. The two local runs could never be reconciled with
the pod result for one concrete reason: the artifact that reported them,
docs/evidence/tracking/tennis_player_select_limit_2026-09-04/report.json, records NO environment
at all. Open it and confirm: its only top-level keys are `bounds` and `matches`. No host, no
timestamp, no library versions, no device, no seed, no code revision.
LIMIT (step 1): a reproducibility claim is uninterpretable without the environment it was measured
in. With no stamp, a difference between two runs cannot be attributed to the code, the machine, the
library build or the ordering, and nobody can re-run the losing arm later because nobody knows what
it was. No amount of care in the analysis recovers a fact that was never recorded.
CHANGE (step 2): ADDITIVE ONLY. Add a run-environment stamp to the artifacts tracking lanes write.
  (a) Write one small helper that returns the stamp, and use it -- do not copy the dict into
      several call sites. At minimum: UTC timestamp, hostname, platform, python version, cv2
      version, numpy version, torch version and CUDA availability if torch is importable, the seed
      in force, and the git revision plus whether the tree was dirty.
  (b) Include a content hash of the modules that actually determine the result. Do NOT hash the
      whole repo -- name the specific modules per artifact type and say why in the memo. The G52
      driver already did exactly this for three tennis modules; follow that precedent.
  (c) Apply it to the tracking-evidence artifacts a lane writes. Enumerate which writers you
      changed and which you deliberately did not.
  (d) Purely additive: no existing key renamed or removed, and any reader must still parse an
      artifact that lacks the stamp. Old artifacts have no stamp and must not become unreadable.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = fraction of newly written tracking-evidence artifacts carrying a complete stamp
  before        = 0.0 -- report.json carries no environment key at all
  bar           = 1.0 on newly written artifacts from the writers you changed, every pre-existing
                  key byte-identical, and a stampless artifact still parsed by every reader
  n             = >= 3 constructed artifacts (with torch present, without it, and a dirty tree),
                  plus every writer you touched enumerated
  eye check     = n/a (a schema change). Reproduction = a printed stamp in the memo.
  must not move = every harness threshold, every existing artifact key, and every verdict. This
                  row records facts; it decides nothing.
NON-TAUTOLOGY: do not derive the git revision by shelling out in a way that silently returns empty
on failure and then reporting the field as present. If the revision cannot be read, record an
explicit null with a reason, the same way G48 handled an unreadable frame rate.
SCOPE DISCIPLINE: do NOT retrofit stamps onto historical artifacts. They cannot be reconstructed
and inventing one would be worse than the gap. Say so in the memo.
EVIDENCE: docs/evidence/tracking/g62_run_environment_stamp_2026-09-0X.md with the reproduced
report.json key list, the stamp helper, the writers changed and skipped, a printed example stamp,
the backward-compatibility test output, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy, no scp, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a4,
no push. Report the sha.
SHARED MODULE: if you touch tracking_harness.py you must take the token in
docs/evidence/SHARED_MODULE_TOKEN.md and PUSH the release when done. Prefer not to touch it --
another lane (G50B) is working there right now, so coordinate or stay out.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.

---
**VERSION 2026-09-08b (orchestrator amendment; the 2026-09-04 text above is frozen and stays binding where it does not conflict; worktree now a6; log cx_g62_environment_sidecar). Since the original allocation, S287 (2026-09-08) proved the possession simulator byte-repeatable inside one environment but different across the pod and the local box on 171/180 ticks, and G327 found the detector deterministic 120/120 only within one environment. The row below adds a uniform sidecar and the two captures; it supersedes the original METHOD where the two differ, keeps its premise artifact (tennis_player_select_limit_2026-09-04/report.json) as the first census entry, and keeps every bar additive.**

GAP G62 | sport all | worktree a6 | log cx_g62_environment_sidecar

**TOOLING ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/`. NEVER edit a committed evidence hash, a committed evidence artifact, a landed memo,
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL for code and tests; the pod is READ-ONLY for one environment capture
(`ssh -F ~/.ssh/config.pod pod 'python3 -c ...'` printing versions; never a write, never a daemon or guard
interaction; pids 1168432 / 1039858 / 1201700 untouched). No GPU, no video.

**WHY THIS ROW EXISTS.** Tracking-evidence artifacts record NO environment (register row G62, allocated
2026-09-04: `tennis_player_select_limit_2026-09-04/report...` carries none). Since then S287 (2026-09-08)
proved that the possession simulator is byte-repeatable inside one environment yet differs between the
pod (py 3.12.3, torch 2.8.0+cu128, numpy 2.1.2, 128 threads) and the local box (py 3.10.20, torch
2.1.2+cu121, numpy 1.26.4, 6 threads) on 171/180 ticks, and G327 found the production detector
deterministic 120/120 only within one environment. Without an environment record, no landed number can
be replayed with confidence and no cross-environment difference can be attributed. A uniform, additive
environment sidecar is the missing artifact.

**PREMISE (step 0, BINDING before-condition):** census every committed artifact directory under
`docs/evidence/tracking/` and `docs/evidence/harness/` (exhaustive; list dirs) for any file or JSON key
recording python/torch/numpy/cv2/ultralytics versions, thread counts, or host identity. PRINT the table:
directories total, directories with any environment record, keys found. **If more than half of the
directories already carry an environment record with at least python + numpy versions, the premise is
FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **THE SIDECAR.** `scripts/platformkit/env_sidecar.py` (<= 150 lines): `capture() -> dict` and
     `write(path)` producing `environment.json` with: python version, platform, hostname (or a stable
     role tag `pod` / `local` derived from a path check, say which), CPU count and the cgroup quota
     if readable, `OMP_NUM_THREADS`/`MKL_NUM_THREADS`/torch threads, versions of numpy, pandas, torch
     (+ CUDA/cuDNN), cv2, ultralytics, scipy, sklearn where importable (absent -> null, never an import
     error), git head sha and dirty flag, and a capture timestamp (UTC). Deterministic key order; ASCII.
     Never include secrets, tokens, or environment variables beyond the named thread settings.
  2. **HOOK POINTS (additive).** Call it from the harness entry points that write evidence: the pod job
     launcher (`~/bin/pod_run` is outside the repo -- document the one-line call the orchestrator should
     add, do not edit it), `scripts/platformkit/tracking/` runners that write a memo artifact dir (list
     the ones you found; add the call to at most three high-traffic ones with a `--no-env-sidecar` opt-out
     so behaviour stays identical when opted out; default ON is acceptable here because the sidecar is a
     new file and changes no existing output -- say so explicitly under B2), and `lane_commit.py` if it
     lives in the repo (it does not; say so).
  3. **CAPTURES.** Write `environment.json` for the local box and for the pod (read-only capture, output
     captured over ssh into the worktree) into `docs/evidence/tracking/g62_environment_sidecar_2026-09-08/`
     and diff them: table of every key that differs. Cross-reference S287's cross-environment finding:
     list which differing keys are candidates for the p_simulator divergence (numpy/torch/thread count),
     labelled as candidates only.
  4. **TEST.** One per-file test: capture() returns every key with the right type on this box; write()
     round-trips; an unimportable library yields null not an exception (monkeypatch the import).
  5. **CHANGE NOTHING ELSE.** No landed artifact gains a sidecar retroactively (say so); no threshold; no
     register edit; no `src/` edit.

**HONEST LIMITATIONS to state, not discover:** a sidecar records the environment, it does not make results
environment-invariant; retroactive attribution for landed rows is impossible; cgroup and GPU details are
best-effort where readable.

ACCEPTANCE RULE:
  metric        = the premise census table with n; the sidecar module + test; the hook list with the
                  opt-out; the two captures and their diff table; the S287 candidate-key list
  before        = no committed artifact records its environment; S287's cross-environment difference
                  has no recorded environment on either side beyond the memo's prose
  bar           = capture() never raises on a missing library; every hook is additive with an opt-out;
                  both captures committed; every census cell carries n
  n             = every committed artifact directory (exhaustive; Q7); every key of the sidecar
  eye check     = NONE. Say that.
  must not move = every committed artifact and hash; every landed memo; `src/`, `domains/`, `api/`,
                  `kernel/`, `intel/`; `data/`; the pod (read-only capture); the daemon and guards;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g62_environment_sidecar_2026-09-08.md` (<= 60 lines) with VERDICT on
line 1, the census table, the hook list, the diff table, the candidate keys, a **NOT VERIFIED** list, wall
time and the SHA-256s; plus the two `environment*.json` captures and `census.csv` (integer cells
zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append, LF).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g62_environment_sidecar.py`. Run that ONE file and the existing test file of
every runner you hooked, each individually. **NEVER a full pytest.** Every touched file <= 300 lines.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
