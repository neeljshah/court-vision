# G330 attempt 2 -- preregistration (panorama identity and registration proxy)

Spec: `docs/evidence/tracking/specs/G330_spec.md`, VERSION 2026-09-08b, ATTEMPT 2 block binding.
Worktree a1. Sealed BEFORE any measurement and committed ALONE.

Attempt 1 (`g330_prereg_2026-09-08.md`, candidate `39ee52eb0`) was REJECTED
(`G330_VERIFY_2026-09-08.md`, copy `G330_VERIFY_ATTEMPT1_REJECT_2026-09-08.md`). **Every attempt-1
number is EXPLORATORY relative to this seal.** Attempt-1 files are frozen and are not edited.

## 1. Section selection -- rule and salt, fixed before the copy

SALT (fixed now, never changed): `G330-attempt2-2026-09-08`

Eligible file: a regular `*.mp4` directly under the pod corpus
`/workspace/nba-ai-system/data/footage_corpus/` whose `ffprobe` stream height is at least 720.
Game id: the basename with the trailing `_s<digits>.mp4` removed.

Rank key for an eligible file: `sha256((basename + SALT).encode("ascii")).hexdigest()`, sorted
ascending as a hex string. Walk that order and keep a file only when its game id has not been kept
yet; stop at three distinct game ids. This is a salted permutation of the whole eligible set, not a
head slice of any listing. If a copy had failed mid-transfer the rule would have been re-applied to
the next candidate BEFORE this file was sealed; no copy failed.

Realised: 22 eligible files over 7 distinct game ids; the three kept, with the sha256 of the LOCAL
copy actually scored and its `ffprobe` width, height, average frame rate and container frame count:

    S1  basketball__nbl-WTEUwPcy7X8_s90.mp4
        sha256 225ada2044bf0d6b530ddef7d3cdddec38521b8a546771e6736ac659dca763fb
        1920 x 1080  50/1 fps  6527 frames  89732060 bytes  rank key 005958e35b7c845d...
    S2  nba__0022500081_s4812.mp4
        sha256 03e66b6b172a494f0df5857a9394bbeec15c65868a6db15bcaae03cf9322b997
        1280 x 720   30/1 fps  3941 frames  34065292 bytes  rank key 10efbb5798d8a0b4...
    S3  nba__0022401198_s2784.mp4
        sha256 444325a05cdb375990b621fc8870ddc774d4f0af4dad456f0b329b03a6552485
        1280 x 720   30/1 fps  3957 frames  32712037 bytes  rank key 3985d1cb0dae1b72...

Three different game ids and two different broadcast resolutions, so "different broadcasts" holds by
construction. The scored run reads only a snapshot whose sha256 equals the value above; corpus
rotation can no longer change the sample. The local copies are DELETED at the end and never
committed.

## 2. Where it runs

The proxy runs on the pod as CPU scratch inside the job root `/workspace/wt/a1/g330a2/` only
(`nice -n 19`, `OMP_NUM_THREADS=2`, detached, no GPU). `track_daemon` and `vol_guard.py` are never
signalled and nothing is written outside that job root. The sections are staged into the job root by
a read-only copy from the corpus and each staged file's sha256 is checked against the value sealed
in section 1 before any arm runs. Peak resident set size is measured and reported. The pod census
and the section copies are read-only. Local resources are byte-identical to the pod worktree's
(`resources/Rectify1.npy 19caf48d...`, `resources/2d_map.png 7ae970d0...`,
`resources/pano_enhanced.png 69024f8e...`).

## 3. Census definition (the denominator)

Every regular file whose basename matches `*pano*` or `*panorama*`, case-insensitive, under the pod
tree `/workspace/nba-ai-system` and under the local a1 worktree `data/**` and `resources/**`. For
each file: side, path, bytes, mtime, sha256 of the raw bytes, and the video stem the path claims
(`pano_<stem>.png` gives `<stem>`; a path claiming no video is recorded as `-`). EXHAUSTIVE, not a
sample. Grouped by sha256.

The memo reports EVERY sha256 group, with n = files in the group, distinct claimed videos in the
group, and bytes -- **including groups whose distinct claimed video count is zero**. The census is
re-taken read-only AFTER this file is sealed and committed; any listing taken before the seal is
exploratory.

PREMISE GATE (binding, step 0): if no two panorama files that claim DIFFERENT videos share a sha256,
the premise is FALSE, the row stops, the memo says PREMISE FALSE, and no arm is run.

## 4. The two arms -- one difference only

Identical for both arms: the section, the decoded frame sequence, the evaluation frame indices, the
detector and its output, the matcher object and every constant read live from
`src/pipeline/unified_pipeline.py`. The ONLY difference is the panorama image handed to SIFT.

    ARM F  the panorama the route actually used for that section. Measured read-only on the pod
           before this seal: the route's per-video cache path exists for S1 and S3 and both are
           byte-identical to `resources/pano_enhanced.png`
           (sha256 69024f8ef08d1e6093ddaf2bda0dd5df8630eab5f1b6b202daa08df8e47e5fff, 1865583
           bytes); S2 has no cache file, so the route's own order (`unified_pipeline.py:858-897`)
           reaches the same general fallback. ARM F is therefore that file for all three sections,
           and its sha256 is printed in every ARM F row.
    ARM V  a panorama built from THAT SECTION's own frames by the route's builder logic
           (`unified_pipeline.py:899-988`: the person gate at `MIN_GAMEPLAY_PERSONS`, the
           five-second stitch window of `_PANO_STITCH_FRAMES` frames,
           `src/tracking/rectify_court.py` `collage`, the wide-crop, then `_pano_valid` at
           842-856). If that validity gate rejects the stitched result, ARM V is recorded
           **NOT BUILDABLE** for that section and the builder's general-fallback substitution
           (`unified_pipeline.py:969-988`) is deliberately NOT applied, because it would make ARM V
           byte-identical to ARM F and destroy the single difference. NOT BUILDABLE is reported,
           never dropped. Nothing is written to any cache path.

No threshold is touched. The ratio gate, `_H_MIN_INLIERS`, the Lowe ratio 0.7 and the RANSAC
reprojection threshold 5.0 are read from the route, never set.

## 5. The route's own stateful matcher -- the path called

Both arms call the production method `UnifiedPipeline._get_homography`
(`src/pipeline/unified_pipeline.py:1231-1354`), unmodified, with its state intact:

  - the sampling counter and the suspension hold at 1248-1253,
  - the camera-cut histogram gate that reuses the cached EMA when there is no cut, at 1262-1274,
  - the SIFT block at 1286-1299 (`FLANN`, Lowe 0.7, `cv2.findHomography(..., cv2.RANSAC, 5.0)`),
  - the first-frame bootstrap that accepts 3 inliers while no EMA exists, at 1304-1309,
  - the hard-reset and EMA blend tiers at 1331-1336,
  - the periodic court-line drift re-anchor at 1346-1352.

Each arm gets its OWN instance, built with `UnifiedPipeline.__new__` and given exactly the
attributes that `__init__` sets for this path (`sift`, `kp1`, `des1`, `pano` as `_load_pano` builds
them at 858-897 including its 100-row black pad; `_kornia_matcher = None`; `_M_ema = None`;
`_sift_frame_counter = 0`; `_sift_last_hist = None`; `_homography_suspended = False`;
`_frames_since_anchor = 0`; `_M1_raw_clip = None`; `M1` from `resources/Rectify1.npy`; `map_2d`
from `resources/2d_map.png`). A full `__init__` is NOT run: it starts a checkpoint thread and builds
OCR, resolver and re-identification components that this row does not use and that would write
outside the job root. Nothing under `src/` is edited and no cache path is written; the builder's
cache write is not reached because ARM V uses the replicated builder logic, which writes nothing.

EVERY decoded frame of the section, cropped by the route's `TOPCUT` exactly as the route does at
`unified_pipeline.py:1689` before it calls the matcher at 1885, is fed to both instances in order.
The route's own counter and cut gate therefore decide where a SIFT fit happens, as in production.

## 6. Held-out split rule (B8)

Within one frame, the route's surviving Lowe matches are indexed in the order the route builds them.
Match indices 0, 2, 4, ... are the FIT set; match indices 1, 3, 5, ... are the HELD-OUT set. A frame
contributes a split only when both halves hold at least 4 correspondences.

  - The homography is fitted on the FIT set alone with the route's own call,
    `cv2.findHomography(frame_pts_fit, pano_pts_fit, cv2.RANSAC, 5.0)`.
  - HELD-OUT inlier: a held-out correspondence whose frame point, projected through that fitted
    homography, lands within the route's own RANSAC reprojection threshold 5.0 pixels of its
    panorama point. Reported per frame as inliers over held-out correspondences, and summed per
    cell with both totals.
  - HELD-OUT median reprojection error: the median over the held-out correspondences of that frame,
    in panorama pixels; summarised per cell as the median over the frames that contributed a split.
  - The FIT-set inlier ratio from the fitting call's own mask is ALSO reported, explicitly labelled
    IN-SAMPLE, and is not comparable with the held-out number.

Per-frame values with their n are archived in `heldout.csv`.

## 7. Proxies and their denominators

Evaluation frames per section: `stride = nb_frames // 40`, `offset = stride // 2`, then the indices
`offset, offset + stride, ..., offset + 39 * stride`. Sealed per section from the frame counts in
section 1: S1 stride 163 offset 81; S2 stride 98 offset 49; S3 stride 98 offset 49. These span the
whole section; they are not its first frames. `n_frames` is how many of the 40 decoded and is
printed in every cell.

  P1 good matches: matches surviving the route's Lowe ratio, summed over the frames on which the
     route ran a fit, with the count of those frames.
  P2 held-out inliers and held-out ratio, per section 6, with the held-out correspondence total.
  P2b in-sample FIT-set inlier ratio, labelled as such, with the FIT correspondence total.
  P3 valid-homography share: evaluation frames at which that arm's matcher returned a homography,
     over `n_frames`.
  P4 feet inside the court polygon (the G03 quantity): the detector runs ONCE per evaluation frame
     and its feet points are shared by both arms. A foot is evaluated only in a frame where THAT arm
     returned a homography. The court point is `M1 @ (M @ [x, y, 1])` exactly as
     `unified_pipeline.py:3084` applies it. Inside means the projected coordinates fall within the
     2D map. Reported as a fraction, inside over feet evaluated; the denominator is per arm because
     the valid-homography frame sets differ. Feet detected over all evaluation frames is printed
     once per section.

Every integer cell in the CSV files is zero-padded to six digits; every share is written as a
fraction.

## 8. Sign convention, and its stated confound

Higher is consistent with better registration for every proxy: more good matches, more held-out
inliers, a higher held-out ratio, a larger valid-homography share, a larger inside-the-court share.
The held-out median reprojection error is the one proxy where LOWER is consistent with better
registration.

Consistency is NOT evidence of correctness. No ground-truth court landmarks are labelled anywhere
in this row and none are created; the eye check is NONE. Inlier counts measure agreement between a
frame and a panorama, not agreement between a frame and the court.

Stated in advance, not discovered: P4 is confounded for ARM V. `M1` (`Rectify1.npy`) is calibrated
for the general fallback panorama's coordinate space (`unified_pipeline.py:885-888`), so for a
per-section panorama P4 measures the arm together with a mismatched `M1`, not registration alone. A
low ARM V P4 is expected and is reported as such, never read as ARM V being worse. Three sections
are a screening sample, not the programme; a section whose ARM V will not build is a limit of the
builder on broadcast footage, not proof that the shared panorama is right.

## 9. Verdict rule

MEASURED when all three are delivered: the exhaustive census with every sha256 group and its n; the
trace with `file:line` and the one-sentence cause read from the producer code; and the three-section
by two-arm proxy table with every denominator, held-out and in-sample columns present and NOT
BUILDABLE reported where it applies. PARTIAL, with the explicit list of what is missing, otherwise.
PREMISE FALSE stops the row before any arm is run.

**No bar in this row is a quality bar.** Nothing passes or fails on any number here. The row names a
cause from the producer code and measures agreement; it ships no fix, changes no `src/` file, moves
no threshold, and makes no claim about tracking quality. Any code fix is written only as a PROPOSED
diff under `docs/research/organization-sprint/`, which is not tracked; its sha256 is carried in the
memo.

## 10. Seal rule

The last line of this file is `SEAL sha256 <hex>`. The hex is the SHA-256 of every byte of this file
ABOVE that line, up to and including the newline that ends the line before it, after replacing every
CRLF with a single LF.
SEAL sha256 5616e3199c863f8ff7dfa6fb3d020762f4a1b23b8759f923f599b2f90614357c
