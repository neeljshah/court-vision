GAP G112 | sport all | worktree a3 | log cx_g112_wide_footage_acquisition
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This row acts on the consolidated reachability verdict. Read the REACH row in
TRACKING_GAPS_2026-09-01.md first.
THE VERDICT THIS FOLLOWS. Five seeded eye-checked censuses established that broadcast footage does
not support a court_feet solve for four of five sports, and that the constraint is the CAMERA: a
planar homography needs four point correspondences or four independent line constraints, and soccer
caps at two independent directions (0/100 frames with >=4 points or >=4 lines), football caps at two
(a third direction in 0/60, an absolute-yard reference in 0/60), and baseball reaches it in 1/120
frames. No detector improvement changes any of those numbers. The programme therefore redirects to
FOOTAGE, and this row asks the only question that matters next: can better footage actually be got?
THE QUESTION: for soccer, football and baseball, does publicly obtainable footage exist that WOULD
be reachable -- tactical/wide camera, overhead, all-22, skycam, stadium fixed-camera -- and can the
existing bridge acquire it?
  (a) For each of the three sports, identify at least 3 candidate SOURCE TYPES (not individual
      videos): what the camera is called, who publishes it, and whether it is public. Tactical or
      all-22 feeds for soccer and football, and centre-field-high or overhead for baseball, are the
      obvious starts; do not stop at the obvious.
  (b) For each candidate type, obtain ONE example if it is public, and run the SAME reachability
      census on >= 20 seeded frames using the G101/G104 method: identifiable points, named lines,
      and INDEPENDENT DIRECTIONS. That last number is the whole point -- a wide shot that still
      shows only two independent directions buys nothing.
  (c) Report per candidate: independent-direction distribution, >= 4 point share, and a plain
      verdict on whether it clears the four-constraint requirement.
  (d) SAY WHAT THE BRIDGE WOULD NEED. If a promising source is not a plain public video, state what
      acquisition would require and stop -- do NOT build a new downloader, do not add credentials,
      and do not touch cookies or any secret. Never commit a credential.
  (e) HONEST NULL IS A FULL RESULT: "no publicly obtainable footage for these sports clears four
      independent constraints" would close the calibration programme for them decisively, and that
      is worth more than an optimistic maybe.
DO NOT change any threshold, the coordinate contract, any queue file, or the bridge. Do not mass
download; one example per candidate type is the budget.
ACCEPTANCE RULE:
  metric        = per candidate source type, the independent-direction distribution and >= 4 point
                  share on >= 20 seeded frames
  before        = broadcast measured unreachable for three sports; alternative footage never tested
  bar           = NO pass bar. Success is >= 3 candidate types per sport identified, every publicly
                  obtainable one censused with the same method, and a plain verdict each. A null is
                  a full success.
  n             = >= 20 seeded frames per obtained example; state the seed and say which candidates
                  you could NOT obtain and why
  eye check     = REQUIRED, same as every other reachability row. Commit the frames you judged.
  must not move = every threshold, the coordinate contract, the bridge, every queue file, the
                  cookie jar, and every prior reachability result
EVIDENCE: docs/evidence/tracking/g112_wide_footage_acquisition_2026-09-0X.md with the candidate
table, the per-candidate census, the acquisition requirements, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g112_wide_footage/ BEFORE reporting (A7). NEVER commit a cookie file, a
token, or any credential.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
