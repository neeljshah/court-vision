GAP G160 | sport all | worktree a8 | log cx_g160_pod_code_identity
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7 and Q8; self-check
section B before reporting. This is a READ-ONLY MEASUREMENT. Move nothing, deploy nothing, restart
nothing, kill nothing.

WHY THIS ROW EXISTS. On 2026-09-02 the pod was found running REJECTED code, silently, and every pod
number quoted that day had to be re-examined. Today the replacement pod was deployed from HEAD and
then a further two files were deployed after their row was accepted. Two distinct things can drift
and they are NOT the same question:

  1. **The FILES on the pod** versus the sha they are supposed to match.
  2. **The CODE THE RUNNING PROCESS ACTUALLY LOADED**, which is whatever was on disk when the daemon
     started and is NOT updated by a later deploy. The daemon is a long-lived Python process. Files
     were deployed to `/workspace/nba-ai-system` at roughly 2026-09-03T14:3xZ while a daemon started
     at roughly 14:13Z was still running. So the daemon is executing pre-deploy code RIGHT NOW, and
     any claim of the form "the pod is running commit X" is false for that process until it restarts.

Establish both, separately, and do not let one stand in for the other.

DO THIS, entirely read-only:
  (a) For every file under `scripts/platformkit/` and `domains/` on the pod, compare against the
      repository at HEAD. **CRLF is expected and is not drift**: the pod copy was produced by
      `git archive`, which applied line-ending conversion, so compare on LF-NORMALISED content. A
      comparison that reports every file as different has found the newline, not a defect. Report the
      count identical, the count differing, and NAME every differing file.
  (b) Determine what the RUNNING daemon actually loaded. `/proc/<pid>/` is available. Its start time,
      its cwd, its open files, and the mtimes of the modules it imported are all readable. State
      plainly whether the running process predates the most recent deploy, and name the specific
      landed changes it is therefore NOT executing. The orchestrator believes G151's write probes are
      among them -- verify or falsify that rather than repeating it (Q8).
  (c) Say what the practical consequence is, in one paragraph, for any number read out of the pod
      ledger between the daemon's start and its next restart. Be precise about which rows are affected
      and which are not.
  (d) Check for a FOREIGN deploy. Another session was bootstrapping the same pod concurrently and left
      `/workspace/bootstrap.log`, `/workspace/pod_md5.txt` and `/workspace/pod_md5n.txt`. Read those
      read-only and report whether anything outside this session's deploy has written to
      `/workspace/nba-ai-system`. If it has, that is the headline.
  (e) State the ELIGIBLE DENOMINATOR for every count (the number of files compared). Never a bare
      sample size.

DO NOT deploy, copy, restart, kill or delete anything on the pod. DO NOT restart the daemon to "fix"
the staleness -- that is the orchestrator's call and doing it would destroy the very measurement this
row exists to take, and could kill in-flight tracking jobs.

ACCEPTANCE RULE:
  metric        = LF-normalised identical/differing file counts with every differing file named; a
                  definite statement of whether the running daemon predates the last deploy and which
                  landed changes it is not executing; the foreign-write finding
  before        = the pod's file state and its running-process state have never been distinguished;
                  "the pod runs commit X" has been asserted without separating the two
  bar           = NO pass bar. Success is both questions answered separately with evidence. "Files
                  match and the process is stale" is the expected answer and is a full success;
                  finding otherwise is a better one.
  n             = every file under scripts/platformkit/ and domains/ (CONSTRUCT, exhaustive -- state
                  that the enumeration is complete)
  eye check     = replaced by REPRODUCTION (Q7): every command quoted with its raw output
  must not move = every pod file, every pod process, every threshold, the coordinate contract, and
                  every verdict
EVIDENCE: docs/evidence/tracking/g160_pod_code_identity_2026-09-03.md with the comparison table, the
process-staleness finding, the consequence paragraph, the foreign-write check, and a NOT VERIFIED
list. Commit the raw comparison under docs/evidence/tracking/g160_identity/ BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: STRICTLY READ-ONLY. The daemon, the keeper and the bridge are all LIVE. Never kill or restart
anything, and never deploy.
COMMIT: explicit pathspec only, in a8, no push. Report the sha.
NEVER PARK: do not poll the pod in a blocking loop; never end waiting.
