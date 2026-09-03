# G182b: an independent second run agrees on the wall and refutes the footage explanation

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md) A1, A2, A3, A7, Q9.
Written by the orchestrator. **No code, bar, gate, denominator, solver, lock,
coordinate contract or verdict was changed.** Diagnostic only.

## Why there are two G182 runs

G182 was dispatched twice by orchestrator error: once to worktree a5 and once to
a7. Both completed independently and neither saw the other's work. The
duplication was accidental, but it is kept and archived here (Q9) because the two
runs disagree on the CAUSE of a failure they agree on, and the disagreement is
decision-relevant.

They did not measure the same footage:

| | a5 (landed as G182) | a7 (this memo) |
|---|---|---|
| clip | pod `data/videos/tennis_smoke.mp4` | local `docs/evidence/demo/tennis.mp4` |
| bytes | 38,094,576 (verified on pod) | 1,559,007 |
| decoded frames | 28,773 | 150 |
| reached corner detection | 28,773 / 28,773 | 150 / 150 |
| **returned enough corners** | **2,660 (9.245%)** | **0 (0.000%)** |
| largest single-stage loss | corner detection, 26,113 / 28,773 = **90.755%** | corner detection, 150 / 150 = **100.000%** |

**Both runs independently locate the wall at the same stage: `detect_court_corners`.**
That is the replicated result, and it is now the best-supported fact in the
tennis chain. No later stage is close in either run.

## The correction, and it is the reason this memo exists

G182 (a5) concludes from its five evenly spaced renders that "corner detection is
unrecoverable on this footage for the current contract". Its five samples are all
close-ups or partial-court views, and on its own clip that reading is defensible.

**It does not generalise, and a7 shows why.** a7's evenly spaced sample includes
frame 149, which the orchestrator inspected directly: a wide Wimbledon broadcast
view with the complete doubles rectangle in frame, all four doubles corners
visible and unoccluded, and every baseline, sideline, service line and the net
crisply rendered. `detect_court_corners` returned `None` on it.

So the honest split is:

- **CONFIRMED:** corner detection is the wall. Two independent runs, two clips,
  same stage, no close second.
- **NOT ESTABLISHED:** that footage is the reason. At least one frame carrying
  the full four-corner geometry the adapter asks for also fails. Some share of
  the 90.755% is a detector limitation rather than a footage limitation, and
  neither run measures that share.

This matters because "the footage does not contain the court" closes the tennis
line as a corpus ceiling, while "the detector misses courts that are plainly
present" is a candidate defect with a fix. **The available evidence does not yet
choose between them, and G182's wording leaned toward the first.** That lean is
withdrawn here. The 90.755% measurement itself is untouched and stands.

## What is NOT claimed

- **No rate is claimed for the detector-defect share.** One eye-checked frame is
  an existence proof, not a proportion. n=1.
- 0/150 is not offered as a better estimate than 9.245%. a7's clip is 150 frames,
  and it is a previously rendered demo output with burned-in overlays rather than
  raw broadcast input, which is its own uncontrolled difference.
- Nothing here re-opens the coverage adjudication. Tennis remains CLOSED AT LIMIT
  on the landed record; this changes the suspected reason, not a verdict.
- No remedy is proposed. Locating a defect is not diagnosing it.

## Verification actually performed

- **A2, a5:** every headline recomputed by the orchestrator from
  `g182_funnel/g182_funnel.json` independently of the lane's harness -- 28,773
  records, 28,773 unique, range 0..28,772; corners 2,660; fresh homography 2,098;
  lock returns 2,522; emitting 2,487; loss 26,113/28,773 = 90.755%. All reproduce
  exactly.
- **A3, a5:** the claimed even-sample positions 0 / 6,528 / 13,056 / 19,584 /
  26,112 over the sorted 26,113-frame loss set were recomputed and yield frames
  0 / 7,124 / 14,283 / 21,402 / 28,772, matching the memo. Not a head slice.
- **A1:** `test_g182_calibration_funnel.py` re-run in master, 1 passed.
- **Premise:** the pod clip a5 names exists at exactly the byte size claimed.
- **Eye check by the orchestrator, not delegated:** a5's frame 14,283 (the one
  a5 called closest to calibratable) genuinely lacks the far doubles corners --
  a5 described it accurately and did not overstate. a7's frame 149 genuinely
  carries the full rectangle. Both lane descriptions survive independent viewing.

## NOT VERIFIED

- **a7's counts could not be independently recomputed.** Its artifact stores the
  aggregated funnel only, with no per-frame records, so its 0/150 is read from
  the lane's own aggregate rather than reproduced from raw observations. a5's
  artifact does carry per-frame records and was fully reproduced. Weight the two
  accordingly.
- Why `detect_court_corners` fails on a fully visible court. This memo locates
  the question and does not answer it.
- What share of the 26,113 corner-loss frames contain a usable four-corner court.
  Answering it needs a labelling pass, not a five-frame eye check.
- Whether the demo clip's burned-in overlays contribute to its 0/150.
- Any downstream tracking-quality, coverage or prediction conclusion.
