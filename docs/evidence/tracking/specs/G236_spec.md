GAP G236 | sport ncaa_basketball | worktree a6 | log g236_label_reindex_existence
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. Build
in `scripts/platformkit/tracking/`. **Change NO label file** -- `corner_pixel_targets.csv` and every
still under `g130_recensus/source_decodes/` are READ ONLY.

**HELD UNTIL A POD LANE IS FREE** (G235 and G220c may be running; N=2 is the measured optimal schedule
per G200/G216). **Check first and say in your memo that you checked and when you began.** The
`track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner`
are PERMANENT residents and the load floor -- never wait for them, never kill or restart them.

**WHY THIS ROW EXISTS -- IT IS THE ONE THING BLOCKING THE ONLY CALIBRATION PATH THAT STILL LOOKS OPEN.**
  - Every in-repo classical route to automatic basketball calibration is CLOSED on measurement: LSD and
    M-LSD 0/17 (G205, G208, G210b, G214), top-hat transfer WORSE (G224), error is unstructured scatter
    with no deterministic correction (G223), and the semantic quad provider abstains 17/17 with its best
    candidate at 0.534 of the gate bar (G227, G229).
  - **What still looks open is a HAND-LABELLED seed plus propagation**: G196 showed four hand-labelled
    corners project correctly with the arc landing out-of-sample, and G222 showed direct-to-seed
    propagation holds across all 1,200 frames tested at a flat 0.26-0.38 px reprojection residual.
  - **But BOTH attempts to use a seed failed on PROVENANCE, not geometry.** G233 used clip identifier
    `wnba__wnba_01_1080p`, which does not exist in the corpus at all. G233b used
    `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds`, the ONLY identifier appearing in both the label set
    and the corpus -- and its seed gate still FAILED.
  - **The orchestrator then measured why: the committed still is not the frame it is named for.** A
    **frame-accurate** extract of frame 28171 from the current
    `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` (via `select=eq(n,28171)`, NOT a keyframe seek),
    downscaled to 640x360 and compared against
    `g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg`, gives
    a **mean absolute difference of 61.33 of 255**. The labels were recorded at **640x360** while the
    corpus file is now **1920x1080**, consistent with re-acquisition at higher resolution after
    labelling.

THE QUESTION, deliberately narrow: **does the committed labelled still appear ANYWHERE in the current
corpus video, and if so at which frame index?**

**IF YES, the entire G140 label set is recoverable by RE-INDEXING rather than re-labelling, and the
seeded-calibration path reopens. IF NO, the file is different content and re-labelling from current
corpus files is the only route. Both answers are decisive and this row exists to get one.**

METHOD:
  1. **Scope: ONE clip.** `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` (pod-resident, 1920x1080,
     `nb_frames=205444`, `avg_frame_rate=30000/1001`) against its one committed 640x360 still,
     `..._IB-_u4gW3ds__s14__f028171.jpg`. **This is an EXISTENCE test, not a campaign.** If it succeeds,
     a successor does the other clips.
  2. **Search cheaply and say how.** Decode the video ONCE, downscale each frame hard (something like
     32x18 or 64x36 grayscale), and compare against the identically-downscaled still with a cheap
     distance. **Report the metric you used and why.** **A coarse stride is acceptable for the first
     pass provided you then refine around the best candidate to frame accuracy** -- say what stride and
     what refinement.
  3. **Report the best match: its frame index, its distance, and the distance DISTRIBUTION over the
     whole scan** (min, median, p1). **A true match should be a dramatic outlier against the
     background; if the best match is not clearly separated from the bulk, you have NOT found it and
     must say so.** That separation check is the deliverable, not the index alone.
  4. **Confirm any candidate frame-accurately**: re-extract that exact index at full resolution,
     downscale to 640x360, and report the mean absolute difference against the still, **using the same
     comparison the orchestrator used so the numbers are commensurable with the 61.33 baseline.**
  5. **If a confident match is found, report the INDEX DELTA** from the labelled 28171 and say whether
     it looks like a constant offset (which would suggest a trimmed/re-encoded copy and would transfer
     to other clips) or an arbitrary jump.
  6. **Do NOT rewrite any label file, do NOT re-run the seed gate, and do NOT propagate anything.** This
     row answers one question. G233b owns the gate and a successor owns the re-index.

**COST AND DISK, BINDING:** a full decode of this clip is expensive -- G234 observed a successful
`run_clip` pass over the sibling clip taking 2,552 s. **Bound your run, report the wall time, and say
what fraction of the clip you actually scanned.** `df` is NON-AUTHORITATIVE on this pod: **`dd conv=fsync`
probe before writing, record `du -sm /workspace/nba-ai-system/data` (baseline ~31,960 MB of 50,000),
STOP and report if it fails.** Decode to memory, write no frames to disk beyond what you commit as
evidence, delete every temporary artifact and report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** one clip and one still is an EXISTENCE test; a match here
does not prove the other ten clips re-index, and a miss here does not prove they cannot. A downscaled
distance can be fooled by a visually similar frame elsewhere in the same broadcast -- **which is exactly
why the separation check in step 3 matters more than the index.** The still is a JPEG re-encode, so an
exact-zero distance is not expected even for the true frame.

ACCEPTANCE RULE:
  metric        = best-match frame index and distance; the distance distribution over the scan (min,
                  median, p1) establishing whether the best match is a clear outlier; the frame-accurate
                  mean-absolute-difference confirmation against the 61.33 baseline; the index delta from
                  28171; wall time and fraction of clip scanned
  before        = the committed still is not frame 28171 of the current file (MAD 61.33, frame-accurate);
                  the G140 label set is orphaned from the video corpus and both seeded-calibration
                  attempts failed on that
  bar          = NO pass bar. **"The still is not in this file" is a FULL SUCCESS** and would settle
                 that re-labelling is required, which is a real decision. **"It is at index N with a
                 clear separation" is the other full success** and reopens seeded calibration for the
                 cost of a re-index. Do not report an index you cannot separate from the background.
  n            = 1 clip, 1 still (EXISTENCE)
  eye check    = commit the best-match frame beside the labelled still so a reader can judge
  must not move = every threshold, bar and verdict, the coordinate contract, the label CSV and every
                  committed still (READ ONLY), `src/` and `domains/` (READ and IMPORT ONLY), the pod
                  daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g236_label_reindex_existence_2026-09-04.md with the search method and
metric, the best index and its distance, the distribution and separation check, the frame-accurate
confirmation, the index delta, wall time and scanned fraction, the committed comparison images, every
disk-guard probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
