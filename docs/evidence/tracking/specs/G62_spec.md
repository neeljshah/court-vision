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
