GAP G103 | sport basketball | worktree a8 | log cx_g103_g68_recipe_and_g93_recall
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. Two halves: make a blocked input durable, then run the
measurement it was blocking. Read
docs/evidence/tracking/g97_g84_render_durability_2026-09-02.md first.
WHERE THIS STANDS, precisely, because two rows have already been spent finding out:
  - G93 preregistered a line-detection-recall protocol (12 degree angle, 12 px perpendicular, 20 px
    endpoint extension, a fixed miss-reason vocabulary) and its test, then honestly REFUSED to
    report a number because a source input was absent. That protocol is already committed on master
    at 98b7d6974 and scripts/platformkit/g93_line_detection_limit.py exists.
  - G97 then established that the 33 G84 renders were NEVER lost -- all committed and readable --
    and that an unchanged rerun on cv2 4.13.0 reproduced all 33 candidate counts AND all 33 JPEG
    bytes exactly, against an original produced on a different OpenCV. The missing input was the 66
    G68 SOURCE CONTACT SHEETS, which live untracked and are recoverable only while one worktree
    survives.
THE DURABILITY DECISION IS ALREADY MADE, implement it: do NOT commit the sheets. They are 116 MB of
JPEG across 11 clip directories in the main checkout, which is why they were never tracked, and
committing them would bloat the repo permanently to preserve something G97 just proved is
regenerable. Instead commit a DETERMINISTIC RECIPE:
  (a) A tracked manifest naming, for each needed tile: the source clip id, the exact frame index,
      the crop or tiling parameters, and a checksum of the tile the recipe produces.
  (b) A small regeneration entry point that reads the manifest and rebuilds the tiles from clips
      pulled off the pod.
  (c) A verification that the rebuilt tiles match the recorded checksums. G97's byte-exact result
      across two OpenCV versions is what makes a checksum a fair test rather than a fragile one --
      cite it, and if your rebuild does NOT match, that is a bigger finding than the missing sheets
      and you should report it and stop.
  Scope the recipe to what G93 needs -- the 33 G84 frames -- not to all 66 sheets. A recipe nobody
  can run in under a few minutes will rot exactly like the sheets did.
THEN RUN G93, UNCHANGED. Use the protocol exactly as committed at 98b7d6974. Do NOT re-choose the
angle tolerance, the distance tolerance or the miss-reason vocabulary now that the data is visible;
that preregistration is the whole reason the number will be trustworthy, and re-picking it after
seeing candidates is B8 self-fit. Deliver what G93 was dispatched for:
  - detection recall on VISIBLE paint lines, overall and per line ROLE (baseline, free-throw, two
    lane lines), with Wilson 95 pct intervals,
  - the visible-line denominator stated exactly (it will be under 132),
  - the miss-reason histogram.
CONTEXT YOU NEED SO THE NUMBER MEANS SOMETHING: G84 measured candidate PRECISION at 11.22 pct over
1,764 audited candidates on these same 33 frames, and found all four paint lines co-present in 0 of
33. G87 falsified the hypothesis that the parallel/orthogonal gate discards them: 11 of 12 true
paint lines PASS that gate. So the loss is upstream of the gate and recall is the missing number. A
low recall is a decisive result, not a disappointing one -- it says basketball court_feet is
detector-limited and names which line to attack first.
DO NOT tune the detector, do not change 28.0 / 5.0 / 10.0, do not touch line_calibration.py, and do
not change the G84 sample or seed.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = paint-line detection recall overall and per role with Wilson 95 pct intervals,
                  plus the miss-reason histogram; and separately, rebuilt-tile checksum matches
  before        = recall unmeasured, blocked on an absent input; precision 11.22 pct known
  bar           = there is NO pass bar on recall. Success is the recipe committed and verified, and
                  the recall reported under the ALREADY-COMMITTED protocol. A checksum mismatch is a
                  valid stopping point and must be reported rather than worked around.
  n             = the 33 G84 frames; state the visible-line denominator exactly
  eye check     = REQUIRED. Recall needs a human decision about which lines are visible. Commit the
                  overlays you judged from.
  must not move = the G93 preregistered protocol at 98b7d6974, the G84 sample and seed,
                  sample_manifest.csv, per_group_labels.csv, every detector parameter,
                  line_calibration.py, the G87 finding, and every harness threshold
EVIDENCE: docs/evidence/tracking/g103_g68_recipe_and_g93_recall_2026-09-0X.md with the recipe, the
checksum verification, the recall table by role, the miss-reason histogram, the overlays, and a
NOT VERIFIED list. Commit under docs/evidence/tracking/g103_recall/ BEFORE reporting (A7).
CAUTION FROM TODAY: two lanes wrote evidence directly into the MAIN working tree and one dropped
two ledger rows another session had appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: READ-ONLY, pull clips only. Never kill anything -- the track daemon and seven footage bridge
lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a8,
no push. Report the sha. Do NOT commit the 116 MB of contact sheets.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
