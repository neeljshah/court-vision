# G287: Unconditioned content at the detector footpoint

## Verdict

ACCEPT, measurement only. On the fixed unconditioned G273 sample, 15/72 =
0.208 detector-box observations have the centre-cross footpoint on a player's
feet. The denominator is all 72 sampled retained detector-box observations,
not authenticated players, not visible-player slots, and not the subset with
a nearby player.

G273's 43/72 = 0.597 PLAYER crop-neighbourhood verdict overstates a
point-level claim that the detection is on a player's feet by 28/72 = 0.389:
the direct centre-cross feet fraction is 15/72 = 0.208.

This pass judges what is under the red centre cross, not what is visible
somewhere in the 512x640 crop. That is the material distinction from G273's
coarse PLAYER verdict, which only established that a player appeared in the
crop neighbourhood.

## Inputs, local execution, and blind seal

Everything ran locally in `C:\Users\neelj\nba-track-a5`. No pod, decode,
re-detection, re-render, re-sampling, re-cropping, `src/`, or `domains/`
path was touched.

The 72 inputs opened for the visual pass are the committed JPEGs under
`C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g273_detector_precision_blind_sample_artifact\blind_renders\`.
Their exact full paths, individual byte sizes, native widths, native heights,
and SHA-256 values are in
`docs/evidence/tracking/g287_unconditioned_footpoint_content_artifact/input_manifest.csv`:
72 JPEGs, 3,746,759 bytes total, each 512x640. The only post-seal tabulation
input was G273's committed
`C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g273_detector_precision_blind_sample_artifact\blind_verdicts.csv`
(1,022 bytes, SHA-256
`10585aa34bd93757917770dce90d35595c88fb67e9b76270bf96e61fd2f76613`).
After the seal, its companion presentation-order CSV (2,315 bytes, SHA-256
`b91e291a01c4b14347b3167c46e3cd70e7ae697dfa5ce4c2f0d327e1a70a43b9`) and
unblind map (24,296 bytes, SHA-256
`4e623b906931cd11e0befc989ed901704c5e96d0b68a93d2416dc686bf661881`) were
opened only to confirm the committed blind-index convention; neither supplies
or revises a G287 verdict.

Fresh order seed `28720260904`, all 72 opaque filenames, all seven-category
verdicts, free text, and their SHA-256 commitments are in
`g287_unconditioned_footpoint_content_artifact/blind_presentation_order.csv`,
`blind_verdicts.csv`, and `blind_order_commitment.json`. They were committed
in `de3b44032a6dfe99fbcf3b34e01b25f6b6c0a7fa` before G273's verdict CSV or
unblind map was opened. This fresh order is independent of G273's committed
presentation order; it does not change the 72 committed JPEG inputs.

The local additive summary route is
`scripts/platformkit/tracking/g287_unconditioned_footpoint_content.py`, 7,374
bytes, SHA-256
`df5da260ec23388d7f4cbb11cc761b613efac225075368f403fe7f6b3ea102d4`.
Its output is `measurement_summary.json` (892 bytes, SHA-256
`67fa44d7b6b839a76e4da4f9a22eb96e346d84e3b3ba1b836643d5167aa0889b).

## Centre-cross categories

All fractions below use the same unconditioned denominator: 72 sampled
retained detector-box observations from one non-deterministic detector draw.
G remains separate, and the two F rows retain their free text in the sealed
verdict CSV.

| Category at the red centre cross | Count / 72 | Fraction |
| --- | ---: | ---: |
| (a) Player's feet | 15 | 0.208 |
| (b) Player's body, not feet | 17 | 0.236 |
| (c) Bare court or floor | 17 | 0.236 |
| (d) Broadcast graphic or score ticker | 13 | 0.181 |
| (e) Person not a player in play | 8 | 0.111 |
| (f) Something else | 2 | 0.028 |
| (g) Cannot judge | 0 | 0.000 |

The (f) detail values are `basketball` and `camera equipment`; neither is
merged into graphics, floor, or cannot judge.

## Cross-tab against G273's committed coarse verdicts

Rows are G273's committed crop-neighbourhood verdicts. Columns are this
pass's centre-cross categories. Each row and column sums to the named count;
the grand total is all 72 detector-box observations.

| G273 verdict | Feet (a) | Body (b) | Floor (c) | Graphic (d) | Other person (e) | Something else (f) | Cannot judge (g) | Row total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PLAYER | 13 | 15 | 12 | 2 | 0 | 1 | 0 | 43 |
| PERSON NOT PLAYER IN PLAY | 0 | 0 | 1 | 2 | 6 | 0 | 0 | 9 |
| NOT A PERSON | 1 | 0 | 4 | 8 | 2 | 0 | 0 | 15 |
| CANNOT JUDGE | 1 | 2 | 0 | 1 | 0 | 1 | 0 | 5 |
| Column total | 15 | 17 | 17 | 13 | 8 | 2 | 0 | 72 |

The decisive G273 PLAYER row is therefore 13 feet, 15 body-not-feet, 12
floor, and 2 graphic, out of its 43 crop-neighbourhood PLAYER verdicts.

## Required comparisons

G286's graphics/ticker share was 29/79 = 0.367, but its 79 observations were
conditioned on a located player already being inside the crop. G287's
unconditioned graphics/ticker share is 13/72 = 0.181, much lower by 0.186;
that lower share is the expected direction under the changed conditioning,
not a surprising increase.

The point-level person total is (a)+(b)+(e) = 40/72 = 0.556. G273's coarse
crop-level PLAYER plus PERSON NOT PLAYER IN PLAY total was 52/72 = 0.722, a
0.166 difference. THIS IS A RE-JUDGE BY THE SAME LABELLER, SO IT MEASURES
CATEGORY REFINEMENT, NOT INDEPENDENT CORRECTNESS. The divergence is retained
as a label-stability finding, not reconciled away.

## Limits and NOT VERIFIED

- One shot of one clip, 72 crops, one labeller, and one non-deterministic
  detector draw. Per G278, the span is measurably friendlier than the clip:
  0.836 versus 0.656, p = 0.0078. This is not clip-wide.
- The population is detector-box observations, not authenticated players.
  These point categories do not establish detector precision, player identity,
  association correctness, or a population rate beyond this fixed sample.
- A footpoint is a POINT: this row observes what is at it and can only infer
  box geometry, never measure it.
- Same-labeller agreement is repeatability plus refinement, not validation;
  no independent correctness or inter-labeller reliability is verified.
- Not verified: replication across clips, shots, draws, arenas, sports, or
  labellers; why a point was floor, graphic, or a person; any detector-box
  extent; and any filter, threshold, gate, retrain, or production change.

## Verifier-contract self-check

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. B1: all 72
sealed rows, including G = 0, remain in every count and table. B2-B6: this is
additive evidence plus a local reader only; no schema reader, lifecycle,
deployment, module move, or production path changed. B7: the fixed G273
sample covers its full 72-bin decision set and was freshly shuffled before
review, not head-sliced. B8: no fitted residual is offered. B9: every unit is
one retained detector-box observation; G273 records 72 distinct source frames.
B10: no threshold, gate, or bar exists or moved. Q does not apply. The local
route is 173 lines, below the 300-line rail, so A12 requires no allowlist
change.

```text
python -m pytest scripts/platformkit/tracking/test_g287_unconditioned_footpoint_content.py -q -p no:cacheprovider
2 passed
```
