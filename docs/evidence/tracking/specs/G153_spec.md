GAP G153 | sport all | worktree a7 | log cx_g153_decoded_frames_producer
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7 and Q8; self-check
section B before reporting. This row RE-OPENS G149. Move nothing.

WHAT G149 LEFT UNFINISHED, and why it is now unblocked. G149 reported NOT VALIDATED: the remote
producer source was byte-identical to the local additive `decoded_frames` writer, the focused test
passed, but all 12 latest ledger rows predated a new-import cycle and omitted the key, and no real
after-row could be observed because the daemon was dead and restarting it was forbidden. So the row
ended with a passing test and zero evidence from a real row.

G147-CORR is what makes this matter: the coverage-bar adjudication is blocked on a PRODUCER GAP, not
on time. The decode manifest IS computed on every run, but on SUCCESS the denominator is never
persisted to the ledger row. Until a real row carries it, no corrected-coverage comparison exists for
any table, and the 0.90 bar cannot be honestly adjudicated in either direction.

DO THIS, all of it locally -- do not wait on the pod and do not poll it:
  (a) Re-measure the premise (Q8). Read the current producer code and state, quoted with file:line,
      whether `decoded_frames` is written on the SUCCESS path today. G149 said the source was
      byte-identical to a working local writer; check that this is still true at HEAD and say so.
  (b) Build a minimal end-to-end LOCAL reproduction: a real (small) tracking run that goes through
      the actual success path and produces an actual ledger row, then read that row back off disk and
      show whether `decoded_frames` is present and what its value is. A test that mocks the writer
      proves nothing here -- G149 already had one of those and it is exactly why the row could not
      close. The value of this row is a REAL row with a REAL number in it.
  (c) If the key is absent from the real row, find where it is dropped and say so with file:line.
      You MAY land the additive fix that persists it, provided it is additive: a new key, no rename,
      no removal, no schema change, and every reader of the ledger grepped and reported (B2, A5).
  (d) If the key IS present in your real local row, then the producer is fine and the gap is
      deployment: say that plainly, name the sha the pod would need, and stop. That is a full success.
  (e) State the ELIGIBLE denominator for anything you count. Never the raw sample size.

DO NOT change the coverage bar, any threshold, the coordinate contract, the eligibility definition,
or any verdict. Do not remove or rename any existing ledger field.

ACCEPTANCE RULE:
  metric        = presence and value of `decoded_frames` in at least one REAL locally produced ledger
                  row, plus the quoted producer path at HEAD
  before        = 0 of 427 rows on the dead pod carried it; the test passed against a writer nothing
                  real had exercised
  bar           = NO pass bar. Success is one real row read back off disk with a definite answer
                  either way. "Present locally, so the gap is deployment" and "absent, dropped at
                  file:line" are both full successes.
  n             = >= 1 real ledger row produced by a real run (CONSTRUCT); state the run's decoded
                  frame count independently
  eye check     = replaced by REPRODUCTION (Q7): show the row as it sits on disk, verbatim
  must not move = every ledger field name, the 0.90 coverage bar, every threshold, the coordinate
                  contract, and every verdict
EVIDENCE: docs/evidence/tracking/g153_decoded_frames_producer_2026-09-03.md with the quoted producer
path, the verbatim real row, the reader grep from A5, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test. Run ONLY that file. NEVER a full pytest -- it freezes the box.
POD: DO NOT TOUCH. Never kill or restart anything. The daemon is being brought up by the orchestrator
and must not be raced.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
SHARED MODULE: track_daemon.py is live. Land in git only; the orchestrator deploys.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
