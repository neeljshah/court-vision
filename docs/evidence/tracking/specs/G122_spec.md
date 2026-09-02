GAP G122 | sport all | worktree a2 | log cx_g122_source_retention_fix
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This IMPLEMENTS a recommendation whose cost objection has been measured away.
Read docs/evidence/tracking/g116_source_retention_census_2026-09-02.md first -- it contains the
code-quoted policy history you need and you must not re-derive it.
WHAT G116 MEASURED, on a frozen census of 199 pod tracking tables:
  - **Source retention 73/199 = 36.68 pct.** Nearly two thirds of tracking tables have no source
    video, so the number in them can never be re-checked.
  - **Memo-cited tables: 61/94 = 64.89 pct retained.** A third of the evidence this programme cites
    in committed memos has no source behind it.
  - **Gate-eligible tables: 8/8 retained.** The subset that matters most is currently intact, which
    is the reassuring half and must not be broken by anything this row does.
  - Corpus 9.64 GiB today; one-source-per-table extrapolates to **26.27 GiB**.
THE COST OBJECTION IS DEAD, and the orchestrator measured it: `df -h /workspace` on the pod reports
**334 TB free**. Full retention at 26.27 GiB is 0.008 pct of available space. There is no storage
argument for discarding sources, so the only remaining question is mechanical.
WHY IT MATTERS, and it is not hypothetical -- FOUR measurements died of this in a single day:
  - G96 could not complete the eye check that would have decided whether to reinstate a retracted
    harness change, because tennis_10's source is pruned and three retrieval paths failed.
  - G110 found 3 of 33 basketball frames are different CONTENT because WFl3V7ZY4ss was re-acquired.
  - G114 found no source at all for five legacy tennis tables, so they can be neither validated nor
    re-tracked.
  - G38B found zero retained selected-player tennis tables.
DO THIS:
  (a) FIND the deletion. G116 quotes the policy history; use it. footage_bridge.py documents
      "download -> scp -> track on pod -> delete local AND remote copies immediately", while
      track_daemon.py moves a tracked video into data/footage_corpus/ instead of deleting it. Those
      two differ. Establish exactly which path deletes a source today and under what condition.
  (b) STOP the deletion, minimally. Prefer changing the smallest thing that keeps a source. Do NOT
      rewrite the staging protocol: the .part-then-rename atomic upload contract and the rule that
      only a plain .mp4 is a complete upload are load-bearing, and track_daemon.py warns explicitly
      against adding size-stability polling. Leave all of that alone.
  (c) DO NOT let the fix fill the stage directory. The daemon watches data/footage_bridge/ and will
      re-track anything that lands there as a plain .mp4. A retention fix that writes into the stage
      would create an infinite re-tracking loop. Say in the memo how you avoided that.
  (d) VERIFY on a real cycle: after the change, confirm that a newly tracked game leaves its source
      present, by name, and that an already-retained source is not disturbed. Measure, do not
      assert -- 8/8 gate-eligible retention must still be 8/8 afterwards.
  (e) BACKFILL IS OUT OF SCOPE and must be said so plainly. The 126 tables whose sources are already
      gone cannot be recovered by this row; G96 and G114 both established that re-acquisition
      returns different content or nothing. Name the count that stays permanently unverifiable.
DO NOT change any harness threshold, the coordinate contract, the rung ladder, or any verdict. Do
not delete or move any existing clip. NEVER KILL ANYTHING ON THE POD -- the track daemon, its
keeper, seven bridge lanes and other sessions' processes are live.
ACCEPTANCE RULE:
  metric        = whether a newly tracked game retains its source, demonstrated on a real cycle; and
                  gate-eligible retention re-measured
  before        = 73/199 = 36.68 pct overall, 61/94 memo-cited, 8/8 gate-eligible
  bar           = a new game's source demonstrably survives tracking, AND gate-eligible retention is
                  still 8/8, AND nothing lands in the stage directory that the daemon would re-track.
                  If you find the deletion is NOT in a path you may safely change, report that and
                  stop -- a proposal under docs/research/organization-sprint/ is a full success.
  n             = at least one real tracked game observed end to end; state its game_id
  eye check     = n/a. Reproduction = the source file present by name after a tracking cycle that
                  would previously have removed it.
  must not move = the .part / .mp4 completion contract, the atomic rename, every harness threshold,
                  the coordinate contract, every verdict, every existing clip, and every pod process
EVIDENCE: docs/evidence/tracking/g122_source_retention_fix_2026-09-0X.md with the deletion path
quoted, the change made, the verified cycle with its game_id, the re-measured gate-eligible count,
the loop-avoidance argument, the permanently-unverifiable count, and a NOT VERIFIED list.
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: a deploy IS permitted for this row if the fix is pod-side, but never kill anything and never
touch a running process.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2, no
push unless the token requires it. Report the sha.
SHARED MODULE: track_daemon.py IS under the token in docs/evidence/SHARED_MODULE_TOKEN.md. If your
fix reaches it, take the token and push the release. Prefer footage_bridge.py, which is not.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
