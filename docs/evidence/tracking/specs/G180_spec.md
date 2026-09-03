GAP G180 | sport all | worktree a2 | log cx_g180_corpus_retention
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A5, A7, B3, B4, Q8); self-check B.
**B3 is the rule this row lives or dies by: missing is not bad, and deleting a source whose result is
NOT durable is exactly the fall-through loss B3 forbids.** Read it before writing a line.

THE PROBLEM, measured 2026-09-03. `/workspace` is quota-limited to about 50 GB and **the pipeline has
no steady state**. When the daemon finishes a staged game it MOVES the source from
`data/footage_bridge` to `data/footage_corpus` (`track_daemon_done.retain`). Bytes move sideways and
nothing is ever freed, so the volume fills monotonically for as long as the bridge uploads. It reached
**40 GB of 50** today, with `footage_bridge` at 19 GB and `footage_corpus` at 18 GB, and there were
NO stale `.part` files to reclaim. The orchestrator had to stop all seven lane workers by hand.

**Why a silent failure here is the worst case:** when the volume fills, pod writes fail SILENTLY. That
is what froze the old pod's ledger at exactly 427 rows across a 200-second watch with no error
anywhere in any log, and cost real diagnostic time.

**THE USER HAS AUTHORIZED DELETING FOOTAGE FROM THE POD once it is used** (2026-09-03). The
orchestrator applied that by hand: 18 corpus sources whose tracking table AND verdict sidecar both
existed were deleted, freeing 13.39 GB and taking the pod from 40 GB to 28 GB. Two sources were KEPT
because they had neither -- `wnba__wnba_01` and `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds`, which
are the thin/unadjudicated rows. **Your job is to make that repeatable and automatic instead of
manual.**

THE RULE, and do not widen it:
  A corpus source may be deleted ONLY when its tracking result is DURABLE -- a nonempty
  `data/tracking/<game_id>/tracking_data.csv` AND a `harness_verdict.json` sidecar both exist.
  **A missing verdict means the game must remain re-trackable. Never delete on rows alone, never on a
  timeout, never on age, and never on "it failed so we do not need it".** A FAIL with a durable
  verdict is a finished result; a thin or unadjudicated game is unfinished work.

DO THIS:
  (a) Q8 first: confirm from code where the source is retained (`retain` in `track_daemon_done.py`)
      and what `read_adjudicated` requires, so your durability test matches the one the daemon already
      trusts for its dedupe branch. Quote both with file:line.
  (b) Implement the retention pass in `scripts/platformkit/` -- NOT in `src/`, which is human-gated.
      It must be idempotent, dry-run by default, and require an explicit flag to delete.
  (c) A5 IS MANDATORY: grep every reader of `data/footage_corpus` before deleting from it. If any lane,
      memo or script re-reads a source for re-measurement, name it and say what breaks.
  (d) Report the eligible denominator: over all corpus sources, how many are durable-and-deletable and
      how many must be kept, with the bytes each way.
  (e) Do NOT wire it into the daemon's hot path in this row. A standalone pass the orchestrator can run
      (and later schedule) is the whole deliverable. No new subsystem, no config file.
  (f) The dry-run output must NAME every file it would delete and why, so a human can audit before the
      flag is ever passed.

DO NOT delete anything that fails the durability test. DO NOT touch `data/footage_bridge` -- staged
files are in flight and a `.part` is handled elsewhere. Do not change any threshold, bar, the
coordinate contract, the eligibility definition, or a verdict. Do not restart or kill the pod daemon.

ACCEPTANCE RULE:
  metric        = durable-vs-keep counts and bytes over all corpus sources; the quoted durability test
                  matching the daemon's own; the A5 reader list; dry-run output naming each candidate
  before        = retention is manual, was done by hand once today, and the volume refills
  bar           = NO pass bar. Success is an idempotent dry-run-by-default pass whose rule matches the
                  daemon's durability test exactly. "Some reader re-reads corpus sources, so automatic
                  deletion is unsafe" is a FULL SUCCESS -- report it and land nothing.
  n             = every corpus source (CONSTRUCT, exhaustive); state the count
  eye check     = replaced by REPRODUCTION (Q7): paste the dry-run output
  must not move = `src/`, the daemon hot path, every threshold and bar, the coordinate contract, the
                  eligibility definition, every verdict, and every non-durable source
EVIDENCE: docs/evidence/tracking/g180_corpus_retention_2026-09-03.md with the quoted durability test,
the counts and bytes, the A5 survey, the dry-run output, and a NOT VERIFIED list. **COMMIT THE MEMO
BEFORE YOU REPORT (A7)** -- two lanes today exited 0 having committed nothing.
TEST: one new per-file test proving a source with a table but NO verdict is NOT deleted. Run only that
file. NEVER a full pytest.
POD: READ-ONLY for inspection and batched. Never kill, restart or deploy over the daemon or keeper.
The orchestrator runs the delete pass after ACCEPT.
COMMIT: explicit pathspec only, in a2, no push. Report the sha and the two counts.
NEVER PARK. Never paste a credential-shaped string into a memo, even a fake fixture.
