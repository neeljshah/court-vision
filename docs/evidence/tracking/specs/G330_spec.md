GAP G330 | sport all | worktree a1 | log cx_g330_panorama_identity

**MEASUREMENT ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only --
`src/pipeline/unified_pipeline.py` (`_build_panorama`, `_compute_homography`) is HUMAN-GATED. You may
IMPORT and RUN it; you may NOT edit it. Build in `scripts/platformkit/tracking/`. NEVER edit a
committed evidence hash, a committed evidence artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`,
or any threshold.**

**WHERE THIS ROW RUNS:** the pod is READ-ONLY for the census (`ssh -F ~/.ssh/config.pod pod`;
NEVER stop, signal or restart `track_daemon` pid 929149 or `vol_guard.py` pid 1039858; NEVER write,
move or delete anything on the pod; copy what you need down with `ssh cat`/`scp`). The build and
registration probes run LOCALLY on at most 3 sections copied from the pod corpus (each ~35 MB, 130 s;
delete the local copies when done). CPU only. No GPU, no daemon interaction.

**WHY THIS ROW EXISTS.** While shipping resources for G310 (2026-09-08), the three files the route
treats as PER-VIDEO panoramas on the pod were found byte-identical. A panorama is the reference the
frame->court homography is matched against (SIFT frame->pano, then pano->court); if every video is
matched against the same foreign panorama, court registration is wrong for every video that was not
shot from that camera, and G03 (map_2d 23.22 pct inside frame, 8/8 games FAIL) and the standing
finding that sports fail at REGISTRATION, not detection, would have a single cause. This row
establishes whether that is so; it fixes nothing in `src/`.

**PREMISE (step 0, BINDING before-condition):** on the pod, enumerate every panorama file the route
can read (`find /workspace/nba-ai-system -iname '*pano*' -o -iname '*panorama*'` restricted to image
files, plus any path the producer names), print path, bytes, mtime, sha256, and which video (if any)
the path claims. **If no two panoramas that claim different videos are byte-identical, the premise is
FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **CENSUS.** The table above for the pod AND the local clone (`data/**`). n = every panorama
     file found (exhaustive). Group by sha256; report groups with size > 1 and the videos they claim.
  2. **TRACE.** Cite with `file:line` (read-only) how `unified_pipeline.py` decides the panorama
     path for a video: `_build_panorama`, the cache key, the fallback (`pano_enhanced.png` or
     otherwise), the ratio gate (broadcast panoramas break SIFT; the 3-10 ratio rule), and what the
     pod daemon route passes. State in one sentence why the files are identical (e.g. every video
     hits the fallback; or the cache key omits the video identity), and whether that is a defect or
     the intended design. If the producer log or the route's sidecars record the panorama choice per
     video, count how many of the ledgered pod games used a fallback panorama (n).
  3. **REGISTRATION PROXY (the measurement).** For 3 sections from 3 different broadcasts (pick by
     ffprobe: different resolution or different game ids; print the choice), run the route's own
     frame->panorama matcher LOCALLY twice per section, ONE difference: ARM F = the panorama the route
     actually used on the pod (the identical file), ARM V = a panorama built from that section itself
     by the route's own builder (`_build_panorama` on the section's frames; if the builder refuses on
     the ratio gate, say so and record ARM V as NOT BUILDABLE for that section -- that is a finding).
     Per section per arm report: SIFT match count, RANSAC inlier count and inlier ratio, share of
     frames with a valid homography, and the share of detected feet whose court coordinate falls
     inside the court polygon (the G03 quantity), each with its denominator (frames evaluated, feet
     evaluated). Same frames, same stride, same detector output, same code path for both arms.
  4. **STATE THE SIGN CONVENTION**: which direction of each proxy is consistent with better
     registration, and say plainly that consistency is not evidence of correctness (no ground-truth
     court landmarks exist here; E1 is closed at limit).
  5. **CHANGE NOTHING ELSE.** No `src/` edit. If the trace shows a cache-key or fallback defect, write
     the fix as a PROPOSED diff under `docs/research/organization-sprint/G330_PROPOSED_pano_cache_key.md`
     (<= 40 lines) and, if an additive harness-side guard is possible under `scripts/platformkit/`
     (e.g. a route sidecar that records the panorama sha per game so the census is recomputable),
     add it with a test.

**HONEST LIMITATIONS to state, not discover:** three sections are a screening sample, not the
programme; inlier counts measure agreement with a panorama, not agreement with the court; a
per-video panorama that fails to build is a limit of the builder on broadcast footage, not proof
that the fallback is right. This row decodes at most 3 x 130 s locally.

ACCEPTANCE RULE:
  metric        = the census table with sha256 groups (n); the trace with `file:line` and the
                  one-sentence cause; the per-section per-arm registration proxy table with
                  denominators; the PROPOSED diff if a defect is named
  before        = the panoramas the route treats as per-video are byte-identical; no sidecar records
                  which panorama a game was registered against
  bar           = the cause is named from the producer code (not guessed) and every proxy cell carries
                  its n; a section where ARM V cannot be built is reported as NOT BUILDABLE, not
                  dropped
  n             = every panorama file (census, exhaustive); 3 sections x 2 arms (screening; Q7 applies
                  to the census only)
  eye check     = NONE. No court landmarks are labelled. Say that.
  must not move = `src/`, `domains/`, `api/`, `kernel/`, `intel/`; every committed artifact; `data/`;
                  anything on the pod; the running daemon and guard; every threshold incl. the ratio
                  gate; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **MEASURED** when the census, trace and 3x2 table are delivered with n;
                  **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g330_panorama_identity_2026-09-08.md` (<= 60 lines) with VERDICT on
line 1, the census table, the trace, the proxy table, the sign convention, a **NOT VERIFIED** list,
wall time and the SHA-256s; plus `docs/evidence/tracking/g330_panorama_identity_2026-09-08/census.csv`
and `proxies.csv` (zero-pad integer cells to 6 digits; shares as fractions). **ADD ONE RESULTS_LEDGER.md
ROW IN THE SAME COMMIT** (one `>>` append). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g330_panorama_identity.py` -- the census grouping and the proxy
arithmetic on a synthetic construct (hand-pinned), plus the sidecar guard if added. Run that ONE
file, and the existing test file of every touched module. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal:
last line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
