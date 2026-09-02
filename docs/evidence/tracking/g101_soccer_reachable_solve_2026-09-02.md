# G101 soccer reachable-solve line census

**Verdict: CLOSED AT LIMIT.** This is a measurement and recommendation, not a
solver change. It follows [`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md),
including A7 and the B1-B10 self-check below.

## Fixed sample and method

This reuses G91's committed 100-frame manifest unchanged: seed `9102026`, one
draw from each of 20 equal temporal strata in each of the same five clips. No
frame was added, excluded, or replaced. The preregistered visibility and
independent-direction rules are in
[`g101_soccer_lines/label_protocol.md`](g101_soccer_lines/label_protocol.md).
Every frame was reviewed from the five full-set G91 contact sheets and
full-resolution source renders where identity was unclear. The committed,
recomputable per-frame results are in
[`g101_soccer_lines/frame_census.json`](g101_soccer_lines/frame_census.json).
The exact reviewed frame renders remain the committed G91 evidence tree:
[`g91_soccer_landmarks/renders/`](g91_soccer_landmarks/renders/).

## Recomputed result

| Metric | Frames | Share |
|---|---:|---:|
| Visible named straight lines >= 3 | 25 / 100 | 0.250 |
| Visible named straight lines >= 4 | 0 / 100 | 0.000 |
| Two independent straight-line directions | 25 / 100 | 0.250 |
| More than two independent straight-line directions | 0 / 100 | 0.000 |

The denominator is all 100 unique `(clip, source_frame)` pairs. The raw line
count is not a constraint count: all straight soccer markings in this census
fall in the `lengthwise` and `crosswise` pitch families. The 25 three-line
frames are a penalty-area front plus its two parallel side lines. They span
only two directions. No frame has four named straight correspondences under
the fixed visibility rule; G91's independent point result also remains 0/100
at four points.

## Degeneracy and recommendation

Parallel lines must not be promoted into independent evidence. Two touchlines
and a halfway line, or a penalty-box front plus its two sides, give only the
two pitch-direction families. A solver that feeds raw segment count as four
constraints can converge numerically while remaining projectively
underconstrained and return unusable coordinates. The centre circle is the
only routinely visible nonlinear feature: it appears in 34 G91 point-label
frames, but without a third independent line family or a reliable circle
conic fit it does not make this corpus a justified new solver row. A
circle-plus-lines formulation is worth a future, separately preregistered
row only after collecting footage where the circle arc and at least stable
non-parallel line evidence co-occur; it was not built here.

**Recommendation:** soccer `court_feet` is not reachable from this broadcast
corpus with a straight-line correspondence formulation. Change the corpus
first: use wider framing, a different source mix, or tactical-camera footage.
Do not lower `MIN_LANDMARKS`, alter `MAX_HELDOUT_ERROR_M`, or declare a soccer
coordinate space from this result.

## NOT VERIFIED

- No line, conic, or circle-plus-lines homography was implemented or scored.
- No soccer clip declares `court_feet`.
- No held-out distance error, temporal calibration, or real-world coordinate
  accuracy was measured.
- A detector's ability to recover the manually visible lines was not measured.

## Verifier self-check

- **A7:** every evidence path named above exists in this worktree at memo time.
- **B1:** all fixed 100 frames are included; zero-line and close-up frames were
  retained.
- **B2:** no schema, reader, or production field changed.
- **B3/B4:** no gate or claim path changed.
- **B5:** no pod file was deployed; no pod process was changed.
- **B6:** no module moved, retired, or orphaned.
- **B7:** review spans each frame of every 20-frame temporal-stratum contact
  sheet, not a head slice.
- **B8:** this is an eye-judgement visibility census, not a fit residual.
- **B9:** each metric unit is one unique G91 `(clip, source_frame)` pair.
- **B10:** `MIN_LANDMARKS`, `MAX_HELDOUT_ERROR_M`, all thresholds, and the
  coordinate contract are unchanged.
