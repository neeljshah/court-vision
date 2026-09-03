GAP G149 | sport all | worktree a3 | log cx_g149_persist_decoded_denominator
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A small PRODUCER fix that unblocks a stuck adjudication.
THE GAP, measured by the orchestrator tonight. G147 set out to adjudicate the tennis coverage bar
and stopped because none of the eight gate-eligible tables carries an auditable decoded-frame
denominator. The orchestrator then recorded that this was merely TIME-BLOCKED and would clear as new
games landed -- and immediately falsified that by checking the last 12 pod ledger rows, including
games tracked tonight after the G139 ffprobe repair. **Not one carries a decoded-frame denominator
field.** The manifest IS computed (track_daemon_done builds it, and its failure is the
decoded_frame_denominator head G139 fixed), but on SUCCESS the denominator is never persisted.
So this is a producer gap, and waiting produces nothing.
WHY IT MATTERS. The harness computes coverage against a denominator that is NOT the decoded frame
count, which G34 measured as inflating coverage 2.5x-4.9x on four tennis clips. Tennis rally share
is 41.7 pct (125/300, Wilson [0.362, 0.473]), so whole-clip coverage cannot exceed roughly 0.42
against a 0.90 bar -- and the pod shows 39 tennis rows with 0 passes. None of that can be
adjudicated without the denominator on the record.
DO THIS, MINIMALLY:
  (a) FIND where the manifest is built and what it already knows. Start at track_daemon_done.py
      around the build_decode_manifest call and read what the manifest summary carries. Quote it.
  (b) PERSIST the decoded-frame denominator onto the ledger row on SUCCESS, alongside the existing
      fields. Additive only: do not rename, remove or repurpose any existing field, and do not
      change any verdict or threshold. Readers of this ledger exist -- grep them (contract A5/B2)
      and confirm an added key breaks none of them.
  (c) DO NOT recompute coverage, do not change the harness, and do not touch the 0.90 bar. This row
      records a number; what to do about it is G147's adjudication and the orchestrator's call.
  (d) VERIFY on a real cycle: after the change, show a newly written ledger row carrying the field,
      by game_id, with the value. A test alone is not enough here -- the whole defect is that
      something computed did not reach the record.
  (e) STATE what the field means precisely: decoded frames of WHAT -- the whole clip, the sampled
      stride, the retained rows? An ambiguous denominator is worse than none, because it would be
      divided by with confidence.
DO NOT change the harness, any threshold, the coordinate contract, or any verdict. NEVER KILL
ANYTHING ON THE POD -- the daemon is live and seven bridge lane workers run under bridge_keeper.
Note the daemon holds old imports, so a deployed change takes effect at its next natural restart;
say so rather than restarting it.
ACCEPTANCE RULE:
  metric        = whether a newly written ledger row carries the decoded-frame denominator, shown by
                  game_id and value
  before        = 0 of the last 12 ledger rows carry it, including post-G139 games
  bar           = a real new row carries the field, AND no existing field changed, AND every ledger
                  reader enumerated and confirmed unaffected. If the field cannot be persisted
                  without touching a token-locked module, say so and stop with a proposal.
  n             = at least one real tracked game observed end to end; state its game_id
  eye check     = n/a. Reproduction = the before rows without the field and the after row with it.
  must not move = every threshold, the 0.90 coverage bar, the harness, every verdict, the
                  coordinate contract, and every existing ledger field
EVIDENCE: docs/evidence/tracking/g149_persist_decoded_denominator_2026-09-0X.md with the quoted
manifest, the reader survey, the verified new row, the field definition, and a NOT VERIFIED list.
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test; run only that file. Never a full pytest.
POD: deploy permitted for this row if the change is pod-side, but never kill or restart anything.
COMMIT: explicit pathspec only, in a3, no push unless the token requires it. Report the sha.
SHARED MODULE: track_daemon.py IS under the token. Prefer track_daemon_done.py or the ledger writer;
if you must touch track_daemon.py, take the token in docs/evidence/SHARED_MODULE_TOKEN.md and push.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
