GAP S311 | sport all | worktree aXX | log cx_s311_ops_attempt_ownership
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: allocated 2026-09-07 by the orchestrator's harness finish audit (orchestrator-held; NOT a lane input). The subject sources are the orchestrator's launcher/
  lander tooling (codex_pipeline.sh, codex-land, pod_run, hidden_launch2, lane_alive), which live OUTSIDE this repo and outside every safe build tree. THIS ROW IS
  BUILT IN AN ORCHESTRATOR SCRATCH WORKSPACE AND APPLIED ONLY AFTER OPUS REVIEW: the lane never edits those sources in place and never touches src/, kernel/, api/,
  intel/ or scripts/team_system/. OPS PRECEDES EVERY POD ROW.
WHERE: local scratch workspace, isolated fixture roots, one per-file test; an ISOLATED pod fixture for the transport-write cases only.
POD: ~/bin/pod_run <aN> --ship <code> --fetch <evidence> -- <cmd>; isolated fixture job directory only, never the deployed tree /workspace/nba-ai-system.
PREMISE (step 0, binding, remeasured on the EXACT current sources; print path, line number and text for each): (a) moving-HEAD candidate selection -- build
  EXIT is scoped to the last DISPATCHED row while the SHA comes from master..HEAD, and any old verifier EXIT is accepted; (b) flat dequeue-before-dispatch --
  the lander removes sweep_queue.txt's first row BEFORE the dispatch it guards; (c) unchecked fetch and main-tree fallback -- pod_run falls back to main, reuses
  scratch, accepts unsafe ship/fetch paths and masks remote failure; (d) empty verify/land files suppress dispatch. hidden_launch2 and lane_alive being
  present does NOT falsify these. Stop FALSIFIED only on that remeasurement, never on an absent worktree copy or an incidental date typo.
LIMIT (step 1): a failure mode that cannot be injected in an isolated fixture is labelled NOT_TESTABLE_TODAY with its blocking fact and stays named in the
  denominator, never silently dropped.
CHANGE (step 2): integrate ONLY the ownership, receipt and path checks; exactly ONE authoritative attempt per register row; additive, every old name kept as
  an alias; no wholesale launcher rewrite. c: immutable SID/run logs plus an active pointer; mkdir stage claim; bind the exact final candidate SHA to its
  verifier; require cleanup AND a validated result, not EXIT:0; retain ownership on UNKNOWN, CLEANUP_PENDING or remote jobs; check ancestry and allowed paths
  before landing and before freeing; honor HARNESS_RUN; structured result sidecar only for completed turns; preserve the real rc; propagate unknown cleanup;
  never re-emit final markers after a failed turn and never swallow inspection errors (lane_alive absence is NOT drain). d: the lander ends NEXT none; a
  deterministic dispatcher owns SID directories with an atomic ready->claimed rename, SID/run idempotency and a STARTED receipt before done; one admission
  lock also covers holds, editors and worktree reservation; ambiguous crashes are reconciled, never requeued blindly. e (REQUIRED BEFORE ANY POD WORK):
  remove the main-tree fallback; validate aN; unique remote job directory; safe_path on every input, output and ancestor, rejecting traversal, drives,
  backslashes, reparse points and hardlinks; regular-file archive manifest only; separate the code-root allowlist from inputs/evidence; check tar AND SSH
  status; preserve argv; exact job-id/rc sentinel; timeout nonzero; fetch only on success and a fetch failure is nonzero; enforced READ-ONLY data access under a
  restricted job identity -- a data symlink is writable and lexical validation alone cannot stop link races or absolute deployed-tree writes.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric = the exhaustive injected-failure matrix: duplicate dispatches, duplicate landings, wrong-SHA transitions, writes outside the owned fixture roots, and process exit status per injected transport failure.
  before = the four PREMISE facts hold on today's sources; no ownership, receipt or path check exists.
  bar = 0 duplicate dispatches, 0 duplicate landings, 0 wrong-SHA transitions, 0 writes outside owned fixture roots, and a NONZERO status on EVERY injected
        transport failure; fixture hashes unchanged.
  sign = a detected failure is a nonzero status plus a refused side effect; process exit 0 is never acceptance.
  n = 9 (CONSTRUCT: old ACCEPT, empty log, failed turn, orphan, concurrent claim, crash around STARTED, bad paths, tar/SSH failure, fetch failure -- every case enumerated, none sampled).
  eye check = n/a (S-row); reproduction = verifier reruns the whole matrix in fresh fixture roots and diffs every cell and every fixture hash.
  must not move = the live launcher/lander sources until Opus review applies the diff; src/, kernel/, api/, intel/, scripts/team_system/; data/registry/; every feature flag; all prior dated evidence.
NON-TAUTOLOGY: the denominator names every enumerated case including the ones that still fail; removing a case to clean the matrix is REJECT.
EVIDENCE: docs/evidence/harness/S311_ops_attempt_ownership_2026-09-07.md + summary JSON + the per-case matrix CSV.
TEST: exactly one new per-file test with full package imports driving the fixture failure matrix; run only that file.
BAN: never write data/ or docs/research/; new dated artifacts only; no deploy, flag, registry or shared-ledger write; no gated-tree edit; no forced git operation; calibration language only.
REPORT: matrix table, NOT_TESTABLE_TODAY cases, the diff held for Opus review, test line, SHA, NOT VERIFIED list. No push. NEVER PARK.
