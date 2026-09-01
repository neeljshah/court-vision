# Tennis court registration: 360p vs 720p, controlled

Same match (`nyYk2nPZAwY`), same section offset (00:10:00), same 36 seconds of
content, same code (`scripts/platformkit/tennis_gate_funnel.py`), stride 3.
The two arms differ ONLY in source resolution.

360p is what the pipeline actually ingests today; 720p was obtained with
`--cookies` plus HLS format 300, which is the mechanism that makes high
resolution available at all (the `player_client=web` used for section
downloads exposes only itag 18, 640x360).

| stage | 360p (300 frames) | 720p (600 frames) |
|---|---:|---:|
| reached the exactly-5-cluster gate | 15 (5.0%) | 112 (18.7%) |
| severe under-detection, 1-2 clusters | 110 (36.7%) | 51 (8.5%) |
| died at the cross-ratio check | 9 (3.0%) | 102 (17.0%) |
| reached depth-order or later | 6 (2.0%) | 10 (1.7%) |

## What this establishes

1. RESOLUTION IS A REAL AND LARGE FACTOR IN LINE DETECTION. Frames reaching the
   five-cluster gate improve 3.7x, and severe under-detection falls 4.3x. At
   640x360 a tennis line is roughly one pixel wide.

2. RESOLUTION ALONE DOES NOT FIX REGISTRATION. The bottleneck MOVES. At 720p,
   17.0% of frames now die at the cross-ratio check rather than 3.0%, and the
   end-to-end near-solve rate is unchanged at about 2%.

3. THE REMAINING DEFECT IS CLUSTER SELECTION, NOT DETECTION. When five vertical
   clusters are found at 720p the observed cross ratio is p50 1.4784 against a
   target of 1.1667 +/- 0.05, ranging -13.91 to 16.90. Five clusters are being
   found; they are usually not the five court lines.

## Consequence for the design

`detect_court_corners` requires `len(vertical_clusters) != 5 -> reject`, then
checks the cross ratio of whatever those five happen to be. That ordering only
works if the detector returns exactly the court lines and nothing else. It does
not: at 720p, 31.5% of frames yield six or more clusters and are discarded
outright, while many five-cluster frames are five wrong lines.

Selecting the best five clusters CONSISTENT WITH the cross ratio is a different
and more robust design than requiring exactly five and then testing them.

## Method note

An earlier, uncontrolled comparison used two DIFFERENT matches and suggested
360p outperformed 720p. That comparison was confounded by content and lighting
and its conclusion was wrong. Only the same-match, same-offset arms above
support the numbers here.

---

# Anchor variants at 720p, n ~ 260 per arm

The five-cluster gate is not the only thing that was wrong, and the obvious fix
for the other thing is WRONG TOO. Measured on 180 seconds of 720p footage,
0.1 s sampling interval, held-out landmark = the independently OBSERVED
`right_service_t` at (60, 18) ft, which is never used in the fit:

| anchor variant | median ft | p95 ft | n |
|---|---:|---:|---:|
| endpoint (shipped)      |  5.280 | 21.847 | 259 |
| horizontal intersection | 16.333 | 29.142 | 261 |

## The hypothesis this refutes

`detect_court_corners` derives two of its four anchors from Hough SEGMENT
ENDPOINTS -- `far_left` from the top endpoint of the left sideline cluster and
`service_t` from the bottom endpoint of the centre cluster. A segment ends where
line PIXELS run out, not at a court feature, so replacing both with real
intersections against detected horizontal clusters looked like the fix. It is
3x WORSE. The horizontal clusters are evidently not the far baseline and the
service line often enough to be relied on, even at 720p where horizontal line
detection is much better.

Earlier small-sample runs on this comparison gave wildly unstable answers -- the
endpoint arm read 514.628 ft median in one 20-frame window and 7.425 ft in a
0.8-second window, on the same clip and the same variant, at n = 9 and n = 4.
A median over two to nine frames is not a median. Only the n ~ 260 arms above
should be quoted.

## What the real number means

5.28 ft median with a p95 of 21.85 ft, on a court that is 78 x 36 ft. The median
is 6.8% of court length. The p95 is the harder problem: one frame in twenty is
wrong by more than half a service box. Classical Hough registration on this
footage does not reach a usable accuracy, and this is now measured rather than
suspected.
