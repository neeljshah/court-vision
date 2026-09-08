VERDICT MEASURED -- attempt 2. Census exhaustive at n=000299 panorama files over 000085 sha256 groups: one group of 000211 files claiming 000206 distinct videos is byte-identical to `resources/pano_enhanced.png`. Cause re-read from the producer. 3 sections x 2 arms delivered on the route's OWN stateful matcher with a held-out split: held-out inlier ratios 6/721, 4/394 and 7/359 against in-sample 82/730, 50/400 and 60/367, ARM V NOT BUILDABLE in 2 of 3.
Prereg `g330_prereg_attempt2_2026-09-08.md` sealed and committed ALONE (`65696a800`) before any measurement; seal `5616e3199c863f8ff7dfa6fb3d020762f4a1b23b8759f923f599b2f90614357c`. Attempt 1 (`39ee52eb0`) was REJECTED and every attempt-1 number is EXPLORATORY relative to this seal; attempt-1 files are frozen and untouched. No bar here is a quality bar; no threshold moved; nothing under `src/` edited.
SNAPSHOT BEFORE SEAL held: two of the three sealed sections had already been deleted from the rotating pod corpus by the time the job root was staged, and were restored from the sealed LOCAL copies; all three staged sha256 verified MATCH before any arm ran. This is the exact failure that voided attempt 1.
## Census -- EVERY sha256 group (pod `/workspace/nba-ai-system` 000294 + local a1 worktree `data/**` and `resources/**` 000005), re-taken read-only AFTER the seal
    sha256 group        files    distinct claimed videos   bytes     what it is
    69024f8ef08d1e60    000211   000206                    1865583   == resources/pano_enhanced.png (general fallback)
    d3bc99f4c83f1886    000002   000002                    1237071   identical pair (pano_0022400710, pano_0022400852)
    e58d38f889a633b4    000002   000002                    892339    identical pair (pano_0022500002, pano_0022500757)
    2a91b8c80fd8e25e    000002   000002                    602818    identical pair (pano_0022401194, pano_0022401196)
    ce975e8e58438d71    000002   000000                    1641303   identical general pair (pod + local resources/pano.png)
    (000080 further groups)  000080 files, 000001 claimed video each, no group of size > 1
Reconciles exactly: 000219 files in the five groups above + 000080 singleton files = 000299 files; 000005 + 000080 = 000085 groups. Full enumeration in `census.csv` (000299 rows). PREMISE TRUE.
## Trace (read-only; `src/pipeline/unified_pipeline.py`) -- cause carried from attempt 1 and re-cited
The cache key is NOT the defect: `_auto_pano_path` (833-840) already keys on the video stem, and `_load_pano` (858-870) returns that per-video file, printing "Pano cache hit" at 865.
CAUSE, one sentence: `_scan_and_build_pano` stitches a per-clip mosaic, and when that mosaic fails `_pano_valid` (842-856: width at least 2000, ratio 3.0 to 50.0) the builder substitutes `resources/pano_enhanced.png` at 969-985 and then writes THAT substituted image to the per-video cache path at 987-988, so every later run reports a per-video cache hit for a file that is the shared fallback.
Defect, not intended design: the fallback itself is intended (885-888 -- `Rectify1.npy` is calibrated for the fallback's coordinate space), but caching it under a per-video key makes it permanent for that clip and erases the record of what the clip was registered against. Measured here: all three sampled sections fail the width bar or produce a near-featureless mosaic.
PROPOSED fix, NOT applied and local-only (`.gitignore:489` ignores `docs/research/*`): `docs/research/organization-sprint/G330_PROPOSED_pano_cache_key.md`, 40 lines, sha256 `69d50cdae01facc6c44ab5a7897cd6c6fb842c68bae8a3ec1ad7d5f4f9daf395`. Additive guard already shipped: `write_pano_provenance` emits four NEW fields only (`pano_path`, `pano_sha256`, `pano_is_general_fallback`, `video_stem`); its docstring/field mismatch (`g330_panorama_identity.py:101` said three) is fixed.
## Registration proxy -- 3 sections x 2 arms through `UnifiedPipeline._get_homography` (1231-1354), unmodified
Both arms are separate instances of the route's own method with its cut reuse (1262-1274), EMA tiers (1331-1336) and first-frame bootstrap (1304-1309) intact; EVERY decoded frame is fed in order after the route's `TOPCUT` crop, so the route's own counter and cut gate decide where a fit happens. The ONLY difference between arms is the panorama image. FIT = even match indices, HELD-OUT = odd; the homography is fitted on FIT alone and scored on HELD-OUT at the route's own 5.0 px reprojection threshold.
    section                          arm  fits  good   FIT corr  FIT inliers   HELD corr  HELD inliers  HELD median px  valid H  feet inside
    basketball__nbl-WTEUwPcy7X8_s90  F    19    1451   000730    82/730 (IS)   000721     6/721         1026.297        40/40    1/408
    basketball__nbl-WTEUwPcy7X8_s90  V    NOT BUILDABLE: route validity gate rejected 1878x1070
    nba__0022401198_s2784            F    12    0794   000400    50/400 (IS)   000394     4/394         0999.944        40/40    9/313
    nba__0022401198_s2784            V    NOT BUILDABLE: route validity gate rejected 1232x710
    nba__0022500081_s4812            F    14    0735   000367    60/367 (IS)   000359     7/359         1217.711        40/40    0/149
    nba__0022500081_s4812            V    02    0008   000000    0/0    (IS)   000000     0/0           -               10/40    0/60
Denominators: "fits" is the frames on which the route actually called `findHomography`; good, FIT corr and HELD corr are totals over those frames; (IS) marks the IN-SAMPLE ratio from the fitting call's own mask, which is NOT comparable with the held-out column beside it. valid H is over n_frames=000040 evaluation frames per cell (stride 163 offset 81, and 98/49 for the two NBA sections, sealed). Feet inside counts only feet in frames where THAT arm returned a homography, so its denominator is per arm; feet detected over the 40 evaluation frames were 000408, 000313 and 000149. Per-frame values with their n are in `heldout.csv` (000047 rows).
The one ARM V that built (4260x710) yielded only 000027 panorama SIFT keypoints and 000008 surviving matches over its 2 fits, so no frame reached the 4-per-half minimum and its held-out cells are 0/0 -- reported, not dropped.
## Sign convention and what it does not show
Higher is consistent with better registration for good matches, inliers, both inlier ratios, the valid-homography share and the inside-the-court share; LOWER is consistent with better registration for the held-out median reprojection error, the one inverted proxy. Consistency is NOT evidence of correctness: no court landmarks are labelled anywhere in this row, the eye check is NONE, and inliers measure agreement between a frame and a panorama, not agreement between a frame and the court.
What the held-out split changes: in-sample ratios of 82/730, 50/400 and 60/367 collapse to 6/721, 4/394 and 7/359 once the correspondences that fitted the homography are removed, with median held-out reprojection errors near or above a thousand panorama pixels. Attempt 1 counted inliers on the correspondences that fitted the model (B8) and could not see this. Fewer than one detected foot in thirty reaches the court map on the arm the route actually uses.
## Where it ran, and the discarded first execution
Pod CPU scratch inside `/workspace/wt/a1/g330a2/` only (`nice -n 19`, `OMP_NUM_THREADS=2`, `CUDA_VISIBLE_DEVICES=-1`, detached), nothing written outside that job root, `track_daemon` and `vol_guard.py` never signalled, no GPU. PEAK RSS 4159.3 MB -- above the 1.5 GB local ceiling, so this row could not have been scored on the local box.
The first execution of the scored run was DISCARDED and re-run on identical sealed inputs: `MatchRecorder.drain()` rebound `self.calls` to a fresh list while the wrapper closure still held the original, so every fit after the first drain was silently dropped (one arm showed 000000 fits alongside 10/40 valid frames). Fixed to clear in place; a regression test pins it. Only the recorder was changed; no input, no threshold and no arm definition moved.
## NOT VERIFIED
- No court landmarks are labelled and none were created; the eye check is NONE. E1 stays closed at limit.
- The valid-homography column is 40/40 for every ARM F cell because the route's EMA is sticky once bootstrapped; it carries almost no information at this frame count and must not be read as agreement.
- Attempt 1's 181/199 ledger mapping is NOT reproduced here and is NOT claimed: it required a stem list that was never archived.
- ARM V deliberately omits the builder's general-fallback substitution (prereg section 4), so NOT BUILDABLE is a property of the stitch, not of the route's end state.
- Feet inside the court for ARM V is confounded by `Rectify1.npy` being calibrated for the fallback's space (885-888), stated in advance, never read as ARM V being worse.
- Only YOLOv8n person boxes plus the route's foot formula were replicated; `AdvancedFeetDetector` (Kalman, Hungarian, OSNet re-identification) was not instantiated. Each arm is a `__new__` instance carrying only what `_get_homography` and its drift check read; components a full `__init__` builds (OCR, resolver, re-identification) are absent and do not touch that method.
- The census is a snapshot of a tree the running daemon is actively writing (000294 pod files here; attempt 1 measured 000263 hours earlier).
- The four non-fallback identical groups are not explained by this row. kornia is absent on the pod, so the route takes its SIFT path there; a kornia-equipped producer would match through LoFTR instead and is not measured.
- Three sections are a screening sample, not the programme. Q7 applies to the census only.
Wall time: scored proxy run 000547 s on the pod, pod census about 000300 s, whole row about 003400 s. Local video copies deleted; no video committed. Tests: 17 passed (G330), 1 passed (LOC rail).
## SHA-256 (LF-normalised bytes)
    cfa07d6dccf1aecb2cd94b5e0cc259bcf900423bb3f1fb63d345f31b5a15e576  g330_prereg_attempt2_2026-09-08.md
    c72448bba39b53445cbd389bccc3b26c54d727c05f5daf09bb6e311592490ee3  census.csv
    ddd6bad5ee8c981934febd377d712173e56ccb9e7b78409a1d5476fe7fe6128f  proxies.csv
    1650312ba037d29326a806d1d20be15aa7e33faa1cbbeb63ea292d39d98e212f  heldout.csv
    aef963576941b5ef5af5bd36ed1fea1af4dce013ececeb5027b4bbff50d42706  g330_attempt2.py
    6c619fb06beb0f700b77282c866ed5c9a1a95e59a6705545554abbedaccc54b1  g330_run_attempt2.py
    bcef1542626faaeb9c9e5cdfb6d492e1125b6b7e1417b8da7f4ddfd94e06e089  g330_panorama_identity.py
    03075ef884b2e7c259936fd8ec560dea824eba19e3bc538de68e5e08f750d678  test_g330_panorama_identity.py
    69d50cdae01facc6c44ab5a7897cd6c6fb842c68bae8a3ec1ad7d5f4f9daf395  G330_PROPOSED_pano_cache_key.md
## Landing 2026-09-08 (verifier codex-sol: ACCEPT)
- NEW GAP: the local-only PROPOSED file `docs/research/organization-sprint/G330_PROPOSED_pano_cache_key.md:3-5` still carries attempt-1 counts, including the 181/199 mapping this memo disclaims at line 38 as never archived; refresh or remove that prose before reuse.
- NEW GAP: `scripts/platformkit/tracking/g330_panorama_identity.py:217-285` replicates the builder's logic instead of invoking the source builder; the resulting detector/init parity limit is disclosed at lines 39-41 of this landed memo.
- NEW GAP: `tests/platformkit/test_g330_panorama_identity.py:1-3` says the construct uses no cv2, but the tests at `:193-231` import and execute cv2.
Vocabulary follows contract Q6; automated scan required.
