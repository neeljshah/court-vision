GAP G41 | sport all | worktree a2 | log cx_g41_cv2_shape_hardening
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. This is a HARDENING fix with a live incident behind it.
PREMISE (step 0, already measured -- reproduce it, do not re-derive): OpenCV 5 changed
cv2.HoughLinesP to return shape (N, 4); OpenCV 4 returns (N, 1, 4). Every call site in this repo
indexes [:, 0, :] and therefore raises "IndexError: too many indices for array: array is
2-dimensional, but 3 were indexed" under cv2 5. On 2026-09-02 the pod was reallocated, the env
was rebuilt, cv2 5.0.0 landed, and tennis court detection died SILENTLY -- the daemon kept
running and wrote a 5-row table instead of thousands. The pod is now pinned to cv2 4.14.0 so it
works again; this lane makes the CODE immune so the next upgrade cannot repeat it.
Reproduce with: numpy zeros mask, one drawn line, cv2.HoughLinesP -> assert ndim, then confirm
domains/tennis/tracking/court_lines.py court_line_segments returns ~106 segments on
tennis_09 frame 6960 under the pinned cv2.
LIMIT (step 1): the fix is shape normalisation, nothing more. It CANNOT change any detection
result under cv2 4 -- if any downstream number moves, you have broken something; stop and report.
CHANGE (step 2): at every Hough-result indexing site, replace the hard-coded [:, 0, :] (and
[:, 0]) with a shape-agnostic reshape that is correct for BOTH layouts:
    found.reshape(-1, found.shape[-1])
Sites confirmed by grep (verify each is genuinely a Hough/line result before touching it, and
leave anything that is not):
  domains/tennis/tracking/court_lines.py:96
  domains/soccer/tracking/geometry.py:101
  domains/soccer/tracking/keypoints.py:50
  domains/football/tracking/geometry.py:113
  domains/football/tracking/line_probe.py:45
  domains/football/tracking/clustering_diagnostic.py:36
  domains/basketball/tracking/line_calibration.py:62
  scripts/platformkit/football_content_gate.py:53
Also check the remaining HoughLines callers and fix them the same way if they index the result:
  scripts/platformkit/synthcal/solve.py, scripts/platformkit/tennis_camera_lock_measure.py,
  scripts/platformkit/tennis_metric_probe.py, scripts/platformkit/tracking/football_fieldview.py,
  scripts/platformkit/tracking/homography_eligibility.py
DO NOT touch domains/soccer/scoreline_engine.py:132 or court_lines.py:221 -- those are not Hough
results. src/ kernel/ api/ intel/ are HUMAN-GATED: if a site lives there, write a PROPOSED diff
under docs/research/organization-sprint/ instead and say so.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = for each touched site, segment count on a fixed frame BEFORE and AFTER, under
                  the pinned cv2 4.14.0 (denominator = the sites you touched)
  before        = tennis court_line_segments on tennis_09 f6960 = 106 segments, detect_court gate
                  "accepted"
  bar           = byte-identical behaviour under cv2 4: every before/after count EQUAL, and a new
                  test proves both (N,1,4) and (N,4) inputs yield the same segment list
  n             = <number of sites touched> (CONSTRUCT: every Hough site is enumerated)
  eye check     = n/a for shape normalisation; reproduction = the before/after count table
  must not move = every harness threshold, every detection parameter (threshold, minLineLength,
                  maxLineGap, contrast, kernel size), and the pinned cv2 version
NON-TAUTOLOGY: the test must feed BOTH array shapes through the parsing path, not just the one
the installed cv2 happens to return, or it proves nothing about the upgrade case.
EVIDENCE: docs/evidence/tracking/g41_cv2_shape_hardening_2026-09-0X.md -- the site list, the
before/after count table, the test output, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file.
POD: the pod is pinned to cv2 4.14.0 -- do NOT change the pod env, do NOT scp anything.
COMMIT: explicit pathspec, in a2, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
