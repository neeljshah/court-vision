# Proposed baseball track-length target

## Measured cut-respecting ceiling (2026-09-01)

Command: `nice -n 15 /workspace/venvs/transnet/bin/python
/tmp/transnet_npb16.py` on RunPod, reading
`data/footage_corpus/npb__npb_01_720p.mp4`.

The genuine NPB section contains 18,001 decoded frames at 30 fps (600.03 s).
The hash-verified TransNetV2 SavedModel at its immutable 0.5 threshold emitted
99 boundaries. Its cut-respecting shot distribution has p50 5.733 s, p90
10.440 s, p95 11.507 s, and max 15.367 s. At source rate this makes the p50
upper ceiling 172 frames; at the tracker’s unchanged stride-three cadence it
is 57 observations. A track cannot cross a verified camera cut, so the median
track cannot be several hundred source frames: 300 source frames is already
above this p50 ceiling. This is a broadcast-physics constraint, not an
association claim.

The matched current detector command found 113 boundaries (not 250) on this
shorter 10-minute 720p section, p50 4.900 s. It confirms that TransNet is the
less fragmenting detector on this source, but it does not make a
several-hundred-frame median physically reachable.

The appropriate baseball image-pixel continuity target is therefore reported
against the measured 57-observation p50 cut ceiling, not the cross-sport S3
several-hundred-frame target. This document proposes no harness or threshold
change.
