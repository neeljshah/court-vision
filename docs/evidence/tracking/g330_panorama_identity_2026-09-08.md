VERDICT MEASURED -- 179 pod panorama files claiming 179 different videos are byte-identical to `resources/pano_enhanced.png` (n=268 files censused, 81 distinct sha256); 181/199 ledgered pod runs that still have a panorama file were registered against that single image; the 3x2 registration proxy is delivered with every denominator, 2 of 3 ARM V being NOT BUILDABLE.
Prereg `docs/evidence/tracking/g330_prereg_2026-09-08.md`, sealed and committed alone before any measurement. Pod read-only throughout (no daemon signalled, nothing written there); build and proxies local, CPU only. No bar here is a quality bar; no threshold was moved; nothing under `src/` was edited.
## Census -- exhaustive, n = every panorama file: pod 000263 (whole /workspace/nba-ai-system tree) + local 000005 (a1 worktree data/** and resources/**) = 000268, over 000081 distinct sha256.
    sha256 group        files    distinct claimed videos   bytes     what it is
    69024f8ef08d1e60    000184   000179                    1865583   == resources/pano_enhanced.png
    d3bc99f4c83f1886    000002   000002                    1237071   identical pair
    2a91b8c80fd8e25e    000002   000002                    602818    identical pair
    e58d38f889a633b4    000002   000002                    892339    identical pair
PREMISE TRUE. The 184-file group is the general fallback plus 179 per-video cache files claiming 179 distinct videos across nba, ncaa_basketball and wnba; all 3 local per-video panoramas are in it too.
Ledger: 000213 ledgered pod runs, 000199 still have a panorama file, and 181/199 of those match the fallback byte for byte. No ledger row and no surviving producer log records which panorama a run used.
## Trace (read-only; `src/pipeline/unified_pipeline.py` unless noted)
The cache key is NOT the defect: `_auto_pano_path` (834-840) already keys on the video stem. `_load_pano` (858-870) returns a cached per-video panorama, printing "Pano cache hit" at 865.
`_scan_and_build_pano` (899-989) scans for gameplay, stitches a five-second window via `src/tracking/rectify_court.py` `collage` (42-72), center-crops a mosaic wider than 10.0 to 6.0 (963-968), then applies `_pano_valid` (843-856: width at least 2000 and ratio in 3.0-50.0).
CAUSE, one sentence: the stitched per-clip mosaic fails that validity gate (measured here at 2052x710 and 1135x710), so the builder substitutes `resources/pano_enhanced.png` at 975-981 and then writes THAT substituted image to the per-video cache path at 987-988, which every later run reports as a per-video cache hit at 865.
That is a defect, not the intended design: the fallback itself is intended (885-888 -- `Rectify1.npy` is calibrated for the fallback's coordinate space), but caching it under a per-video key makes it permanent for that clip and erases the record of what the clip was registered against.
PROPOSED fix, not applied, and LOCAL-ONLY (`.gitignore` line 489 ignores `docs/research/*`, so it is not in this commit; its sha256 below is over the local file): `docs/research/organization-sprint/G330_PROPOSED_pano_cache_key.md`. Additive guard shipped: `write_pano_provenance` emits NEW fields only (`pano_path`, `pano_sha256`, `pano_is_general_fallback`, `video_stem`), making the census recomputable per run.
## Registration proxy -- 3 sections x 2 arms, single difference = the panorama handed to SIFT
Same section, same frame indices (stride 90, first 40 decoded), same detector output, same matcher constants imported live from the route. All three sections are 1280x720 broadcast, three different game ids.
    section                 arm  good matches  inliers  inlier ratio  valid H  feet inside court
    nba__0022400909_s4453   F    000055        000008   8/55          0/40     0/0
    nba__0022400909_s4453   V    000079        000024   24/79         0/40     0/0
    nba__0022401156_s2491   F    002885        000250   250/2885      39/40    13/199
    nba__0022401156_s2491   V    NOT BUILDABLE: route validity gate rejected 2052x710
    nba__0022401198_s2784   F    002413        000214   214/2413      35/40    14/288
    nba__0022401198_s2784   V    NOT BUILDABLE: route validity gate rejected 1135x710
Denominators: good matches and inliers are totals over n_frames=000040 per cell; valid H is over the same 40; feet inside court counts only feet in frames where THAT arm produced a valid homography, so its denominator is per arm. Feet detected over the 40 frames: 000302, 000199, 000310.
S1's ARM F is the one genuine per-clip panorama on the pod (4260x710) and its ARM V rebuilt at the same 4260x710; ARM F for S2 and S3 is the shared fallback image.
## Sign convention and what it does not show
Higher is consistent with better registration for every proxy. Consistency is NOT correctness: no court landmarks are labelled here, the eye check is NONE, and inliers measure agreement with a panorama, not agreement with the court.
The shared fallback is not the worse arm on agreement -- it is far better (39/40 and 35/40 valid frames against 0/40 for the per-clip pair) -- yet fewer than one foot in ten reaches the court map either way, so panorama identity does not by itself explain where registration fails. Three sections are a screening sample, not the programme.
## NOT VERIFIED
- The pre-registered first section `nba__0022400909_s1588.mp4` was deleted from the pod corpus by the running daemon between the listing and the copy; the SAME rule re-applied to the surviving corpus gave `nba__0022400909_s4453.mp4`. The realized sample deviates from the prereg; the rule does not.
- The census is a snapshot of a tree the daemon is actively writing (000263 pod files here; a listing minutes earlier had 000260). 000014 of the 000213 ledgered runs have no panorama file at all.
- Only YOLOv8n person boxes plus the route's foot formula were replicated; `AdvancedFeetDetector` (Kalman, Hungarian, OSNet re-identification) was not instantiated.
- ARM V deliberately omits the builder's fallback substitution (prereg section 3), so NOT BUILDABLE is a property of the stitch, not of the route's end state.
- P4 for ARM V is confounded by `Rectify1.npy` being calibrated for the fallback; S1's ARM V produced no valid homography, so its P4 is 0/0 and carries no information either way.
- On this box kornia and CUDA are present and `_warp_perspective` (`src/tracking/rectify_court.py` 16-31) hands an OpenCV (width, height) size to kornia's (height, width) argument, so `collage` raises ValueError at line 62; kornia is NOT installed on the pod, so this is not the pod's cause. Left unfixed and unclaimed.
- The 3 non-fallback identical pairs are not explained by this row. LoFTR was disabled (`COURTV_NO_LOFTR=1`); the pod has no kornia so its route uses the same SIFT path, but a kornia-equipped producer would not.
A second driver run reproduced `proxies.csv` byte-identically. Wall time: driver 000115 s, pod census command about 000300 s, whole row about 002400 s. Local video copies deleted; no video committed. Tests: 7 passed (G330), 1 passed (LOC rail).
## SHA-256 (LF-normalised bytes)
    e72c620b1e90815edac1f1379d91148fe2145189f3a5f122b2e4ea71cd16e571  g330_prereg_2026-09-08.md
    b46e21df5b16dc7ff80a2eaaafa7fa18ee5c06bdc81234f66b0eeabc7a82385d  census.csv
    61dfb3be002b4e4a1c122a06c3181a062ecab78881b291b7543a4fddedd7bdbc  proxies.csv
    83ada7fb1b966b2c655ce28257840bc180a0cba2f143513d7b4e0aa24354bec0  g330_panorama_identity.py
    38dcb7fc263d633c9e0650dc2667b044a8e19810104691361318aa6f6351d68b  g330_run.py
    217bfd5147e3996624393abea3580bb1c8edb6cc1e30c2e2ba1f983e5e238a47  test_g330_panorama_identity.py
    69d50cdae01facc6c44ab5a7897cd6c6fb842c68bae8a3ec1ad7d5f4f9daf395  G330_PROPOSED_pano_cache_key.md
Vocabulary follows contract Q6; automated scan required.
