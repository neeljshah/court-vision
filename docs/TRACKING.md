# Multi-sport broadcast tracking — status and evidence

**Updated 2026-09-01.** Tracking here is a **training-only teacher**: it exists to
label footage so models can learn from it. It is never used live and never
serves data at inference. That contract shapes every decision below — an honest
empty output beats a plausible fabricated one, because fabricated labels poison
the models downstream.

## The coordinate contract

Every tracking row declares what its coordinates are
(`coordinate_space` / `observation` / `calibration`, defined in
`scripts/platformkit/coordinate_provenance.py`):

- **court space** (`court_feet`, `pitch_metres`) — only from a solved, validated
  homography. Scorable by the quality harness.
- **image space** (`image_px`) — raw detector pixels, preserved as a training
  corpus. The harness **rejects** these by design: a preserved detection corpus
  is never a scorable game.
- **undeclared** — rejected. An omitted declaration used to mean "assume court
  coordinates", which is exactly how pixel data was once scored as court feet.

This contract was earned the hard way. An audit found that **every sport's
adapter clipped its output to the same bounds the harness judged it by**, so the
out-of-bounds metric could never fail; one adapter reused a stale cached
homography for 131 of 132 "accepted" frames; another fitted a broadcast graphic
as a court line. All of that is removed. The gates were never loosened —
producers were fixed or made to fail closed.

## Per-sport status (measured, reference footage)

| Sport | Calibration | Output | Harness | Notes |
|---|---|---|---|---|
| **tennis** | real 4-pt homography; classical registration measured to a 5.28 ft median held-out floor | `court_feet` | **RETRACTED, no pass** (the recorded coverage 0.976 was 99.3% carried-over calibration -- 4 fresh solves propagated over 600 frames; honest coverage 0.0067; see docs/evidence/SESSION_2026-09-01_INDEX.md) | fresh-solve-only adapter + per-frame manifest now enforced; camera-lock (geometric-median lock, 5px drift ceiling) merged, fail-closed, and now MEASURED on accepting sections: 599 decoded -> 50 fresh solves -> 5 locks -> 11 drift-checked reuses (1 drift reject) = 10.18% solved-per-decoded, the first legitimate double-digit coverage (1080p section: 7.04%); the frozen harness still returns passed:false on both runs, and dead sections fail on 0-1 vertical lines vs the unchanged >=2 requirement (see docs/evidence/tracking/tennis_camera_lock_honest_measurement_2026-09-01.md); 0 harness passes stand across all sports -- the honest number |
| **football (american)** | yard-line fit solves ~0/200 frames (sidelines out of broadcast frame); numeral-OCR anchoring measured terminal -- best preprocessing variant read 55/444 crops (12.39%), and only 13/74 field-view frames cleared the joint-numeral gate against a 30/74 requirement, so no correspondence solve, homography, or harness run was attempted (see docs/evidence/tracking/FOOTBALL_WAVE6H_OCR_REPORT.md) | `image_px`, preserved | rejected by contract (correct) | stable identities: 27 tracks, median length 2301 frames |
| **soccer** | landmark framework in place; current detector under-constrains the fit | `image_px`, preserved | rejected by contract (correct) | identity churn is the defect: 660 tracks, median length 102 |
| **baseball (MLB/KBO/NPB)** | field homography measured **impossible** from broadcast (FOV p50 42 ft vs 90 ft infield; 0/24 frames contain both 1B and 3B) | `image_px`, preserved | rejected by contract (correct) | re-detection, not tracking: median track length ~35 frames |
| **basketball (WNBA/NCAA)** | legacy pipeline; per-clip homography solved in memory but not persisted | `image_px` (stamped) | rejected by contract (correct) | output-path bug fixed 2026-09-01 (all games wrote one shared file) |

**Preserved training corpus to date: 1.45M+ detection rows across 30+ games in
five sports** — every row declared, every game correctly rejected for scoring.
Zero fabricated positions.

## How quality is measured

- `scripts/platformkit/tracking_harness.py` — per-game gates (coverage, oob,
  jump_p95, ball_valid, liveness). Thresholds are never moved to make output
  pass.
- `scripts/platformkit/tracking_quality_scan.py` — cross-sport defect
  signatures (tracks/frame, median track length, singleton share, stationary
  share, identity churn), so failures are comparable between sports.
- `scripts/platformkit/tracking_regression.py` — re-tracks retained reference
  clips against a committed baseline; detects regressions, cannot certify
  correctness.
- Physical validation before gate metrics: a calibration fix must place known
  court features at their true coordinates (e.g. a held-out line landing at its
  real distance) before any harness number counts.

## Demo evidence

See `docs/evidence/tracking/` — short clips rendered directly from pipeline
output: image-pixel overlays for preserved-corpus sports, and a top-down
court-feet animation for the calibrated tennis output.

## Architecture (one paragraph)

Footage is downloaded on a residential connection (datacenter IPs are blocked
by the source), a 16-minute mid-game slice at 720p (~12x less transfer than
full games), uploaded via atomic rename to a GPU pod, and tracked by a
concurrency-capped daemon with per-job timeouts, a PID-file watchdog and a
verdict-carrying ledger. Every stage was measured before it was tuned.
