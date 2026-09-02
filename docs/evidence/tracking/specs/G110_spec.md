GAP G110 | sport basketball | worktree a8 | log cx_g110_tile_nonreproducibility
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. Read
docs/evidence/tracking/g103_g68_recipe_and_g93_recall_2026-09-02.md and
g97_g84_render_durability_2026-09-02.md first.
THE CONTRADICTION TO EXPLAIN, and it is a genuine one:
  - G97 rebuilt the 33 G84 candidate RENDERS on cv2 4.13.0 against originals made on a different
    OpenCV and reproduced **33/33 candidate counts AND 33/33 JPEG bytes exactly**.
  - G103 rebuilt the upstream G68 SOURCE TILES those renders derive from and reproduced **0/33**.
Derived artifacts reproduce byte-exactly; their inputs do not. Both cannot be true of the same
pipeline unless the two stages differ in some specific way, and naming that difference is this row.
G103 was right to stop rather than ship tiles that do not match, and G93's recall measurement is
still blocked behind it.
FIND THE CAUSE. Candidates worth testing, and do not stop at the first plausible one:
  (a) FRAME SEEKING. Decoding to frame N by seeking is not always exact on a long H.264 file with
      B-frames; sequential decode to N and a seek to N can land on different frames. If the tile
      recipe seeks and the render pipeline did not, that alone explains it. Test by decoding the
      same index both ways and comparing.
  (b) A DIFFERENT SOURCE FILE. G96 hit exactly this on tennis_10: the surviving public stream was a
      6,145 s 23.98 fps re-encode, not the original 25 fps clip. If a clip has been re-acquired
      since G68 ran, frame index N is a different picture and no recipe can fix that. Compare
      durations, frame counts and fps against whatever G68 recorded.
  (c) ENCODER OR COLOUR CONVERSION on the tile write path (JPEG quality, subsampling, BGR/RGB).
      This would give visually identical tiles with different bytes -- distinguish it from (a) and
      (b) by comparing PIXELS, not just checksums. A pixel-identical tile with different bytes is a
      completely different diagnosis from a tile showing a different frame.
  DO (c) FIRST as a triage: if the rebuilt tiles are pixel-identical, the problem is an encoding
  detail and is cheap; if they show different content, it is (a) or (b) and it is expensive.
THEN UNBLOCK G93, or state honestly that it cannot be unblocked. G93's protocol is already
committed and must not be re-chosen. Ask whether its recall measurement actually needs the SOURCE
tiles at all, given the 33 G84 renders reproduce exactly and are committed. If the renders carry
enough for a human to judge which paint lines are visible, G93 can run off them and the tile
question becomes irrelevant to it. Say which, and if the renders suffice, run G93 unchanged and
report the recall by line role with Wilson intervals and the miss-reason histogram.
DO NOT change the G93 protocol, the G84 sample or seed, any detector parameter,
line_calibration.py, or any threshold. Do not commit the 116 MB of contact sheets.
ACCEPTANCE RULE:
  metric        = the named cause of the 0/33 mismatch, supported by a pixel-level comparison; and
                  if G93 is unblocked, its recall by line role with Wilson intervals
  before        = renders 33/33 byte-identical, source tiles 0/33, cause unknown, G93 blocked
  bar           = there is NO pass bar. Success is the cause identified with evidence and a clear
                  statement of whether G93 can run. "The source clips were re-acquired and the old
                  frames are gone" is a full success and a permanent NOT VERIFIED for those tiles.
  n             = all 33 tiles for the triage; state how many are pixel-identical versus different
                  content
  eye check     = REQUIRED. Look at a rebuilt tile beside its original. Checksums cannot tell you
                  whether the picture changed and that is the whole question.
  must not move = the G93 protocol at 98b7d6974, the G84 sample and seed, every detector parameter,
                  line_calibration.py, every threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g110_tile_nonreproducibility_2026-09-0X.md with the triage result,
the named cause, the side-by-side comparison, the G93 disposition and its recall if run, and a NOT
VERIFIED list. Commit under docs/evidence/tracking/g110_tiles/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session had appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a8, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
