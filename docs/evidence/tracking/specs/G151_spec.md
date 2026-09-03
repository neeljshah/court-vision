GAP G151 | sport all | worktree a3 | log cx_g151_quota_fails_loud
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This row MAY change code, and the change is narrow: make an existing SILENT failure
LOUD. It changes no threshold, no bar, no gate, no verdict, and no coordinate contract.

THE FAILURE, observed on 2026-09-02 and not hypothetical. `/workspace` on the pod is quota-limited to
roughly 50 GB. When it fills, every write fails SILENTLY:
  - the track daemon stopped appending to its ledger and sat at exactly 427 rows for a 200-second
    watch with no error anywhere in any log
  - scp uploads failed and left `.part` files that could never complete
  - the archive tool created nine EMPTY files, reporting "Cannot write: Disk quota exceeded" only to
    a stream nobody was reading
  - real operator time was spent blaming stale Python imports in a long-running daemon before another
    session diagnosed the quota
`df -h /workspace` DOES NOT DETECT THIS. It reports the cluster's free space and showed 372,096 GB
free while the volume was completely full. df is not a lever that exists here.

WHAT TO BUILD, and nothing more. A write probe: create a small file, fsync it, read it back, delete
it. That is the only reliable test. Wire it at the two places where the silence actually cost us:
  (a) the ledger append path in scripts/platformkit/track_daemon.py -- a failed append must raise or
      log at error level, never return quietly
  (b) the upload path in scripts/platformkit/footage_bridge.py -- a failed scp must be distinguished
      from a successful one, and a `.part` left behind by a quota failure must be reported
Keep it small. This is a guard, not a subsystem: no new module hierarchy, no config file, no retry
policy, no monitoring daemon. If a few lines in each place do it, that is the whole change.

THE CATCH YOU MUST ESTABLISH FIRST. Read both call sites and say, from the code, what they do TODAY
when a write fails. If one of them already fails loudly, do not touch it -- report that it is already
guarded and guard only the other. A premise that turns out false is a valid result (Q8): three
premises in this program were already false when the row was read.

MEASURE: run your probe read-only against the live pod at the ~/.ssh/config.pod alias `pod` ONCE and
report the current headroom it observes. `du -sh /workspace/*` gives the breakdown. Do NOT delete
anything on the pod, do not restart anything, do not kill anything.

ACCEPTANCE RULE:
  metric        = for each of the two call sites, its behaviour on a failed write BEFORE (quoted from
                  code) and AFTER (demonstrated by the test); plus the one live headroom observation
  before        = both paths fail silently; the failure mode is documented only in prose
  bar           = NO pass bar. Success is: the current behaviour established from the code, the guard
                  added only where it is actually missing, and one test that FAILS if the guard is
                  removed. "Already guarded, no change needed" is a full success.
  n             = 2 call sites (CONSTRUCT, exhaustive)
  eye check     = replaced by REPRODUCTION: the test must fail with the guard reverted, and you must
                  show that it does
  must not move = every threshold, every gate, the coordinate contract, the daemon's worker count,
                  every verdict, and every file on the pod
EVIDENCE: docs/evidence/tracking/g151_quota_fails_loud_2026-09-03.md with the before/after code
quotes, the live headroom observation, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test. Run ONLY that file. NEVER a full pytest -- it freezes the box.
POD: READ-ONLY plus a single probe file you delete. NEVER kill or restart anything on the pod.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: track_daemon.py and footage_bridge.py are both live -- the daemon may be RUNNING while
you work. Do not restart it. Your change lands in git only; the orchestrator deploys.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
