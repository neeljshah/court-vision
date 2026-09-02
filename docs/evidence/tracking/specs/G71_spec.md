GAP G71 | sport tennis | worktree a9 | log cx_g71_rejected_code_table_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. CENSUS AND MARKING. Delete nothing, re-track nothing.
WHY THIS ROW EXISTS: G59 found the pod running code a verifier had REJECTED --
domains/tennis/tracking/player_select.py (2,820 bytes) plus a 32-line adapter change to use it,
deployed 2026-09-02 02:23 UTC, never on master. That was REMEDIATED the same day: master's adapter
was deployed (md5 identical both sides), the rejected files removed, and the daemon picks up new
code on its next job because it launches each job with subprocess.Popen. ONE item remains open and
it is this row: **every tennis table the pod wrote between 02:23 UTC and the remediation reflects
the rejected selector, and nothing currently marks them.** Until they are marked, someone will
quote a number from one.
WHAT THE REJECTED CODE DID, so you can state the impact rather than hand-wave it: it stipulated a
player prior of x in [-6, 84], y in [-4, 40] ft. Attempt 1 measured that this drove oob to 0.0000
while COLLAPSING two-player coverage from 5/5, 1/5, 4/5 to 1/5, 0/5, 1/5. So affected tables will
look BETTER on oob and WORSE on coverage than master's behaviour, and both movements are artefacts
of rejected code rather than real tracking changes.
TASK:
  (a) Establish the exact remediation timestamp from the register and the evidence (the rejected
      files are preserved at docs/evidence/tracking/g59_rejected_pod_code/ and on the pod at
      /workspace/g59_backup_2026-09-02/). State the window with both ends.
  (b) Enumerate EVERY tennis tracking table and harness report the pod wrote inside that window.
      Use file mtimes on the pod (read-only) and the daemon ledger. State the count and list them.
      The pod holds about 418 tracking tables, so state how many are tennis and how many fall in
      the window -- both denominators.
  (c) MARK them. Add a durable, machine-readable record --
      docs/evidence/tracking/g71_rejected_code_tables.json -- listing each affected table with its
      write time and the reason. Do NOT modify or delete the tables themselves; a marking file
      beside them is the reversible option and deleting evidence is never the answer.
  (d) Cross-check which of them any landed memo or register row QUOTES a number from. That list is
      the actual damage, and it is the reason this row exists. If the answer is none, say so
      plainly -- that would be very good news and it must be stated, not assumed.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = count of tennis tables written inside the rejected-code window, and of those the
                  count that any landed claim quotes
  before        = unknown; nothing distinguishes a rejected-code table from a clean one
  bar           = THERE IS NO PASS BAR. Success is the complete enumeration with both denominators
                  and a durable marking file. "Zero landed claims quote an affected table" is a
                  perfectly good and welcome outcome.
  n             = all tennis tables on the pod; state the total, the in-window count, and the
                  quoted count
  eye check     = n/a (a provenance census). Any claim about what a table CONTAINS needs the table.
  must not move = every harness threshold, every table on the pod (read-only), the daemon, and
                  every verdict. You mark; you do not re-score and you do not re-track.
NON-TAUTOLOGY: do not define the window from the tables' own timestamps and then report that all
tables in the window are in the window (B1). The window comes from the DEPLOY and REMEDIATION
events, independently of what was written.
DURABILITY (A7): the marking file and the enumeration go under docs/evidence/ before you report.
POD: READ-ONLY, absolutely. No scp, no deploy, no daemon restart, never kill anything -- the daemon
and other sessions' jobs are live. Do not touch any process; another session has asked that its
foundry runner and supervisor be left alone.
EVIDENCE: docs/evidence/tracking/g71_rejected_code_table_census_2026-09-0X.md with the window and
how you established it, the enumeration with both denominators, the marking file path, the list of
landed claims that quote an affected table (or an explicit none), and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a9,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
