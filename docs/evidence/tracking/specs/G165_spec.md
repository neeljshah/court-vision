GAP G165 | sport all | worktree TBD | log cx_g165_full_volume_reap
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A5, A7 and Q8; self-check
section B before reporting. **B3 is the rule this row lives or dies by. Read it twice before writing
any code.**

THE DEFECT, and it is PRE-EXISTING -- it predates the 2026-09-03 session and was NOT introduced by
G151. On a full `/workspace` volume, `_finish` can raise from at least two points that sit ABOVE the
retention step, and neither `tick` nor `main` has an exception handler
(`scripts/platformkit/track_daemon.py`, `while True: tick(...)`):

  1. `write_ball_telemetry_declaration` -> `scripts/platformkit/tracking_schema.py:175-178`,
     `destination.write_text(...)` with no `try`. This is on the CLIP_SPORTS path
     (`nba`, `wnba`, `ncaa_basketball`, `basketball`) -- the bulk of the workload. The adjacent
     `_BALL[job["sport"]]` is also an unguarded dict lookup.
  2. `adjudicate` -> `scripts/platformkit/track_daemon_done.py:155`, `_atomic_json(...)` writing the
     verdict sidecar, likewise unguarded.

When either raises: the daemon dies mid-reap, `active.pop` has already happened so every OTHER
in-flight job's bookkeeping is lost, and the source stays in STAGE because `retain` sits below. The
keeper restarts on a flat 60-second poll with no backoff and no cap, re-claims the same video, and
re-tracks it -- roughly 1,000 seconds of GPU per cycle, adding disk pressure to the very volume that
was already full. G151-CORR fixed exactly this shape for the LEDGER append via `_record_loudly`.
These two sites are the same shape, still open.

**THE TRAP, and it is why this needs a designed row rather than a patch.** The obvious fix -- move
retention into a `finally` so the source always leaves STAGE -- is WRONG and would be an automatic
reject. `read_adjudicated` plus a CORPUS hit is what makes a game skippable; retaining a video whose
verdict was never written moves it out of STAGE while leaving it unadjudicated, so it is never
re-tracked and never scored. **That converts an unbounded retry into permanent silent loss, which is
B3 FALL-THROUGH LOSS: missing is not bad.** Do not do it. If you find yourself writing `finally:
retain(...)`, stop and re-read B3.

WHAT TO ESTABLISH FIRST (Q8 -- re-measure, do not assume):
  (a) Confirm both raise sites from the code at HEAD and quote them with file:line. Confirm that
      `tick` and `main` still have no handler. If any of that is already fixed, say so and the row
      narrows or closes -- a falsified premise is a valid result.
  (b) Enumerate EVERY write inside `_finish` and inside `adjudicate` that can raise on a full volume.
      Exhaustive, stated as a CONSTRUCT with the enumeration declared complete. That list is the
      deliverable even if no code changes.
  (c) A5 IS MANDATORY: grep every reader of the verdict sidecar, the capability file and the ledger
      row, and report them, before proposing anything that changes when any of the three is written.

THEN, and only with (a)-(c) in hand, propose the SMALLEST change that stops the unbounded loop
WITHOUT creating silent loss. The orchestrator's view, offered to be argued with rather than
followed: the honest fix is probably not to make the reap survive harder but to make the daemon STOP
CLAIMING NEW WORK while the volume is unwritable -- a full disk is a reason to idle loudly, not to
retry forever. If you take that route, the claim-side gate must be loud in the log on every cycle so
an idle daemon is never mistaken for a healthy one. If you take a different route, say why it does
not reintroduce B3.

DO NOT change any threshold, the coverage definition, the decoded-frame denominator, the eligibility
definition, `MAX_POD_BACKLOG`, the worker count, or any verdict. Do not restart or kill the pod
daemon; the orchestrator owns it and deploys after ACCEPT (B5).

ACCEPTANCE RULE:
  metric        = the exhaustive list of full-volume raise sites in the reap path with file:line; the
                  A5 reader survey; and, if code changes, a test that FAILS without the change
  before       = the ledger append is guarded by `_record_loudly`; at least two sibling sites are not,
                  and both sit above retention on the CLIP_SPORTS path
  bar           = NO pass bar. Success is the enumeration plus a defended proposal. "The only safe
                  fix is larger than this row" is a FULL SUCCESS -- report it and stop rather than
                  landing something that trades a loop for silent loss.
  n             = every raising write in `_finish` and `adjudicate` (CONSTRUCT, exhaustive)
  eye check     = replaced by REPRODUCTION (Q7): demonstrate the failure with a simulated unwritable
                  target in a temp directory, never by filling a real volume and never on the pod
  must not move = every threshold and bar, the coverage definition, the decoded-frame denominator,
                  the eligibility definition, MAX_POD_BACKLOG, the worker count, and every verdict
EVIDENCE: docs/evidence/tracking/g165_full_volume_reap_2026-09-03.md with the quoted sites, the
exhaustive enumeration, the A5 survey, the reproduction, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
Re-read `track_daemon.py` at HEAD before quoting a line number -- this file changed three times on
2026-09-03 and a reviewer already reported stale line numbers from a snapshot read.
TEST: exactly one new per-file test if you change code. Run ONLY that file. NEVER a full pytest.
POD: READ-ONLY. The daemon is RUNNING. Never kill, restart or deploy to it.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
