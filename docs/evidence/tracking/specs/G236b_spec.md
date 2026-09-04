GAP G236b | sport wnba | worktree a3 | log g236b_reindex_validated_frame
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file** -- `corner_pixel_targets.csv` and every still under `g130_recensus/source_decodes/` are
READ ONLY. Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G225 may be running; N=2 is the measured optimal schedule per
G200/G216). **Check first and say in your memo that you checked and when you began.** The `track_daemon`,
`keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT
residents and the load floor -- never wait for them, never kill or restart them.

**WHY THIS ROW EXISTS -- THREE SEEDED ATTEMPTS HAVE FAILED AND THE REASON IS NOW PRECISE: WE HAVE NEVER
ONCE TESTED A FRAME WHOSE GEOMETRY G196 ACTUALLY VALIDATED.**
  - **G196 eye-checked only FIVE of its seventeen frames** -- indices 0, 4, 8, 12, 16 -- returning
    **3 YES**: `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925`,
    **`wnba__wnba_01_1080p__s01__f001600`**, and `wnba__wnba_07__s08__f016801`; and **2 INDETERMINATE**:
    `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` and
    `wnba__wnba_04__s06__f012223`.
  - **G233** used `wnba__wnba_01_1080p` labels against `wnba__wnba_01.mp4` -- different identifiers,
    and it did not check the frame matched. Gate failed.
  - **G233b** and **G233c** used `IB-_u4gW3ds__s14__f028171`, which **G196 NEVER eye-checked**. G233c
    fixed the index to the G236-verified 46154 (colour MAD 1.865680 against G236's matched frame) and
    the gate still failed -- a clean failure, but on unvalidated geometry.
  - **The uncomfortable structural fact: all three of G196's YES frames come from clip identifiers that
    are NOT in the current corpus, and the one clip that is present it rated INDETERMINATE.**

**THE OPPORTUNITY: `wnba__wnba_01_1080p__s01__f001600` is a G196 YES -- 'The independently visible
three-point curve lands on the painted court' -- and `wnba__wnba_01.mp4` IS in the corpus. They are
different identifiers, but plausibly the same source at different resolutions. G236 proved this exact
question is answerable by scanning.**

THE QUESTION: **does the G196-validated still `wnba__wnba_01_1080p__s01__f001600.jpg` appear anywhere in
`wnba__wnba_01.mp4`, and at which frame?**

METHOD -- **reuse G236's landed harness and method wherever possible; it worked and its numbers are the
comparison standard.**
  1. **Scope: ONE still, ONE video.** Still:
     `docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s01__f001600.jpg`
     (1920x1080, labelled `source_frame` 1600). Video:
     `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` -- **A9: 2,931,985,407 bytes,
     1920x1080, 174,430 frames.** Both are 1920x1080, so **no scale factor is needed** -- state that
     explicitly, since a wrong scale has already cost this programme two rows.
  2. **Scan the whole temporal extent**, as G236 did (it decoded 205,444 of 205,444 frames in 695.960 s
     and retained all 41,089 stride-5 candidates). **Report the stride, the candidate count, the wall
     time, and the fraction scanned.**
  3. **THE SEPARATION CHECK IS THE DELIVERABLE, NOT THE INDEX.** Report the best distance against the
     whole-scan distribution (min, median, p1). **G236's match was a ratio of 0.036661 to the median --
     use that as the standard of what a real match looks like. If your best candidate is not a dramatic
     outlier, you have NOT found it and must say so.**
  4. **Confirm any candidate frame-accurately** at full resolution and report the colour MAD in the same
     units G236 and G233c used, **beside the MAD at the named index 1600** so the two are directly
     comparable.
  5. **Report the index delta** and say whether it is consistent with G236's +17,983 on the other clip
     -- **a shared or systematic offset would be a significant finding; an unrelated one is equally
     worth stating.**
  6. **Do NOT rewrite any label file, do NOT run a seed gate, and do NOT propagate.** This row answers
     one question; a successor owns the gate.

**COST AND DISK, BINDING:** a full decode is expensive; **bound your run and report wall time.** `df` is
NON-AUTHORITATIVE on this pod -- **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~32,350 MB of 50,000), STOP and report if it fails.**
Decode to memory, write no frames beyond committed evidence, delete every temporary artifact and report
bytes freed. **Delete no corpus source.**

**HONEST LIMITATIONS to state, not discover:** one still and one video is an EXISTENCE test. A
downscaled distance can be fooled by a visually similar frame elsewhere in the same broadcast, which is
why the separation check matters more than the index. The still is a JPEG re-encode, so an exact-zero
distance is not expected even for the true frame. **A match here would NOT prove the seed gate passes --
it would only mean the gate can finally be tested on geometry G196 validated, which is a different and
weaker claim.**

ACCEPTANCE RULE:
  metric        = best-match index and distance; the whole-scan distance distribution establishing
                  separation; the frame-accurate colour MAD at the candidate and at index 1600; the
                  index delta and its relation to G236's +17,983; wall time and fraction scanned
  before       = three seeded attempts failed, none of them on a frame G196 eye-checked; G196's three
                 YES frames all come from clip identifiers absent from the corpus
  bar          = NO pass bar. **"The still is not in this file" is a FULL SUCCESS** and would say the
                 validated frames are unreachable, forcing re-labelling from current corpus files.
                 **"It is at index N with clear separation" is the other full success** and would let
                 the seed gate finally be tested on validated geometry. Report no index you cannot
                 separate from the background.
  n            = 1 still, 1 video (EXISTENCE)
  eye check    = commit the best-match frame beside the labelled still so a reader can judge
  must not move = every threshold, bar and verdict, the coordinate contract, the label CSV and every
                  committed still (READ ONLY), `src/` and `domains/` (READ and IMPORT ONLY), the pod
                  daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g236b_reindex_validated_frame_2026-09-04.md with the search method and
metric, the best index and distance, the distribution and separation check, the frame-accurate
confirmation beside the index-1600 baseline, the index delta, wall time and scanned fraction, the
committed comparison images, every disk-guard probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
