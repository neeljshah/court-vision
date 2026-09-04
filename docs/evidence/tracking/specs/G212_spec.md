GAP G212 | sport all | worktree a7 | log g212_corpus_keeplist
**ANALYSIS AND A KEEP-LIST ONLY. DELETE NOTHING. This row must not remove a single byte.**
`src/` is HUMAN-GATED: READ only. Build in `scripts/platformkit/`.

**S1 MACHINE: LOCAL for the code analysis; light READ-ONLY pod queries are fine** (`ls`, `stat`,
`du`). G203 is running on the pod, so **no decode, no inference, no `run_clip.py`, no `-count_frames`.**
**Never kill, restart or deploy over the pod daemon or keeper.**

**S3 DEPENDENCY, and this row exists to unblock a refusal that was CORRECT.**
  - **G180 REFUSED TO LAND a retention pass, and the refusal was the result.** An exhaustive A5 survey
    found **SEVEN readers that re-measure from corpus sources**: `tracking_corpus_ab.py`,
    `tracking/footage_census.py`, `basketball_relabel_image_px.py`, `g103_g68_tile_recipe.py`,
    `g110_tile_nonreproducibility.py`, `g126_g111_label_audit.py`, `g137_qualifying_frame_scale.py`.
    Deleting a source breaks each one's ability to regenerate its evidence.
  - **The orchestrator had ALREADY deleted 23 sources, about 22.9 GB, across two manual passes before
    that survey existed**, using a durability test alone (table + verdict present) and never asking
    what else reads those files. **The clips are gone. `g110_tile_nonreproducibility` exists precisely
    because a re-download is not guaranteed byte-identical.** Manual deletion has been stopped since.
  - **G180 named the unblock: a keep-list covering the clips those seven readers cite. This row builds
    that keep-list. It does not delete anything.**

**WHY IT IS URGENT NOW:** the footage bridge was restarted and the corpus is growing again (11 -> 12
clips, pod `data/` **29 GB -> 34.7 GB**). Bytes only move sideways -- the daemon MOVES a source from
`footage_bridge` to `footage_corpus` -- so **the volume grows monotonically until something is
deleted**. The earlier quota crisis began at 40 GB against a ~50 GB working figure, and a full volume
makes daemon writes fail **SILENTLY**, which is the failure that froze the old pod's ledger.

METHOD:
  1. **Re-derive the reader set yourself (A5); do not trust G180's list of seven.** Search the repo
     exhaustively for anything that opens a corpus source. Report readers G180 missed, and readers
     that no longer exist. **Name your search method so the survey is reproducible.**
  2. For each reader, determine **which specific clips it cites or would need**, by reading the code
     and any manifest or evidence file it depends on. Where a reader enumerates the corpus
     dynamically rather than naming clips, **say so -- that reader needs EVERY source and that is a
     decisive constraint**, not a detail to smooth over.
  3. Cross it with durability: which sources have a nonempty `tracking_data.csv` AND a
     `harness_verdict.json` sidecar. **Durability alone is NOT sufficient for deletion -- that was the
     exact error made before -- it is one necessary condition among several.**
  4. **Emit a keep-list and a candidate-list as committed files**, with a per-clip reason. A clip is a
     deletion CANDIDATE only if: durably tracked, cited by no reader, and not one of the two protected
     thin games (`wnba__wnba_01`, `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds`, which G181 showed
     are unfinished for a NAMED reason and whose deletion would be B3 fall-through loss).
  5. Report the **bytes recoverable** if every candidate were deleted, and the resulting pod usage.
     **State plainly whether that is enough headroom to matter**, or whether the corpus simply
     outgrows this volume and the real answer is an infrastructure decision for the user.

**DO NOT DELETE. DO NOT WRITE A SCRIPT THAT DELETES BY DEFAULT.** If you build tooling, it is
dry-run-only in this row, and the memo must state that no byte was removed.

ACCEPTANCE RULE:
  metric        = the re-derived reader set with the search method; per-reader clip requirements; the
                  keep-list and candidate-list with per-clip reasons; bytes recoverable
  before        = G180 correctly refused to land retention because seven readers re-measure from
                  sources and no keep-list exists; 23 sources were already destroyed before that was
                  known; the corpus is growing again and the volume fills monotonically
  bar           = NO pass bar. **"Every clip is cited by some reader, so nothing is safely deletable"
                  is a FULL SUCCESS** and would mean the honest answer is more storage or a different
                  retention policy, which is the user's decision and not ours to pre-empt. Do not
                  manufacture deletion candidates to create headroom.
  n             = every corpus source (CONSTRUCT, exhaustive) x every reader found; name exclusions
  eye check     = none
  must not move = the corpus (DELETE NOTHING), every threshold and verdict, `src/` (READ ONLY), the
                  pod daemon and keeper, the bridge and its watchdog (do not stop or start either)
EVIDENCE: docs/evidence/tracking/g212_corpus_keeplist_2026-09-03.md plus the committed keep-list and
candidate-list files, with the reader survey and its method, per-clip reasons, recoverable bytes, an
explicit statement that nothing was deleted, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any tooling added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
