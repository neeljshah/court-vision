GAP G183 | sport all | worktree a2 | log cx_g183_corpus_keeplist
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A2, A5, A7, B3, Q8); self-check B.
RAILS: pod READ-ONLY and BATCHED; one store at a time, never a whole store over 300 MB; never kill,
restart or deploy over the pod daemon or keeper; never launch powershell; never write under `data/`;
**DELETE NOTHING, on the pod or locally**; ASCII only; never paste a credential-shaped string.

WHY. G180 (landed) refused to automate corpus retention because its mandatory A5 survey found SEVEN
readers that re-measure from corpus sources and would break if a source is deleted:

  `scripts/platformkit/tracking_corpus_ab.py`, `scripts/platformkit/tracking/footage_census.py`,
  `scripts/platformkit/basketball_relabel_image_px.py`, `scripts/platformkit/g103_g68_tile_recipe.py`,
  `scripts/platformkit/g110_tile_nonreproducibility.py`,
  `scripts/platformkit/g126_g111_label_audit.py`, `scripts/platformkit/g137_qualifying_frame_scale.py`

Retention cannot be automated until there is a KEEP-LIST of the clips those readers actually need.
**The orchestrator has already deleted 23 corpus sources (about 22.9 GB) across two manual passes
before that survey existed**, gating only on a durability test. This row produces the keep-list AND
the honest accounting of what that deletion cost. Both halves are required.

DO THIS:
  (a) For each of the seven readers, determine which corpus clips it actually names or enumerates.
      Some hardcode a clip; some glob the whole corpus. **Distinguish those two cases sharply** -- a
      reader that globs needs a POLICY (e.g. "keep N per sport"), a reader that names a clip needs
      THAT clip. Quote the naming or globbing line with file:line for each.
  (b) Produce the keep-list: every clip filename any reader names explicitly, deduplicated, with the
      readers that need it. State the ELIGIBLE DENOMINATOR (clips examined) for any share.
  (c) THE ACCOUNTING, and do not soften it. Cross-check the keep-list against what is on the pod NOW
      (`data/footage_corpus/`) and against the committed evidence that records what was deleted. For
      every clip a reader names: is it still present, or was it deleted? **Report the count and the
      names of any reader-required clip that is GONE.** If the answer is zero, say so plainly -- that
      would mean the deletion was lucky rather than safe, and the distinction matters.
  (d) For any clip that is gone and needed, say whether it is re-fetchable: is it still in a
      `data/footage_queue_*.json`? Note that `g110_tile_nonreproducibility` exists because a
      re-download is NOT guaranteed byte-identical, so "re-fetchable" is not "recoverable" -- say
      which it is for each.
  (e) Recommend the keep-list rule in one or two sentences. Do NOT implement retention; G180 already
      established that landing it is out of scope until this list exists.

DO NOT delete anything. Do not modify any reader. Do not change a threshold, bar, the coordinate
contract, the eligibility definition, or a verdict. Do not touch `src/` (human-gated).

ACCEPTANCE RULE:
  metric        = per reader, the quoted naming/globbing line and the clips it needs; the deduplicated
                  keep-list; the present-vs-deleted cross-check with names of any missing required
                  clip; the re-fetchable-versus-recoverable call for each
  before        = seven readers are known to depend on corpus sources; WHICH clips is unmeasured, and
                  the cost of 23 already-deleted sources is unquantified
  bar           = NO pass bar. Success is the keep-list plus the honest accounting. **"Some required
                  clips are gone" is a FULL SUCCESS and is the outcome to report faithfully** -- it is
                  the orchestrator's error to own, not something to minimise.
  n             = all 7 readers (CONSTRUCT, exhaustive); state the clips examined
  eye check     = replaced by REPRODUCTION (Q7): quote each naming line and each pod listing command
  must not move = every reader, every footage file, every threshold and bar, the coordinate contract,
                  and every verdict
EVIDENCE: docs/evidence/tracking/g183_corpus_keeplist_2026-09-03.md with the per-reader table, the
keep-list, the accounting, and a NOT VERIFIED list. **COMMIT THE MEMO BEFORE YOU REPORT (A7).**
TEST: one per-file test only if you add code; run it alone. NEVER a full pytest.
COMMIT: explicit pathspec only, in a2, no push. Report the sha, the keep-list size, and how many
required clips are gone.
NEVER PARK.
