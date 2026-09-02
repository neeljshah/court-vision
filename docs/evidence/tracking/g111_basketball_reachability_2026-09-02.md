# G111 basketball court reachability census

**Verdict: CLOSED (reachability census complete).** This is a seeded,
eye-judged visibility census only. It follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7 and the B1-B10
self-check below. No solver, detector, `line_calibration.py`, threshold,
coordinate declaration, existing G84/G87 finding, pod file, or pod process
changed.

## Fixed sample and method

At measurement start, the read-only pod inventory contained exactly 11
basketball source encodes: six `ncaa_basketball` and five `wnba`. With global
seed `1112026`, `random.Random(1112026)` made one uniform draw from every one
of 20 equal-sized temporal strata in **each** clip. This retains 220 decoded
frames, not a head slice. All clips were pulled locally only for decoding and
review; nothing was copied to the pod.

The exact draw, decoded-frame count, dimensions, slot, and render path for
every frame are in
[`g111_basketball_reach/sample_manifest.json`](g111_basketball_reach/sample_manifest.json).
The pre-review counting rules are in
[`g111_basketball_reach/label_protocol.md`](g111_basketball_reach/label_protocol.md).
Every one of the 11 contact sheets was reviewed by eye, and the full-resolution
render was available for each tile. The positive-slot decisions are preserved
in [`g111_basketball_reach/manual_decisions.json`](g111_basketball_reach/manual_decisions.json);
the resulting complete 220-row per-frame judgment is in
[`g111_basketball_reach/frame_labels.csv`](g111_basketball_reach/frame_labels.csv).
All 220 individual renders and 11 contact sheets are committed under
[`g111_basketball_reach/final_renders/`](g111_basketball_reach/final_renders/)
and [`g111_basketball_reach/contact_sheets/`](g111_basketball_reach/contact_sheets/).

| Family | Clip | Sampled | Frames with >=4 points |
|---|---|---:|---:|
| NCAA | `IB-_u4gW3ds` | 20 | 10 |
| NCAA | `IB-_u4gW3ds_1080p` | 20 | 11 |
| NCAA | `WFl3V7ZY4ss` | 20 | 13 |
| NCAA | `sRtHQbywiTE` | 20 | 13 |
| NCAA | `tiUvyvWOCxo` | 20 | 12 |
| NCAA | `zqBCKovJCQU` | 20 | 17 |
| WNBA | `wnba_01` | 20 | 14 |
| WNBA | `wnba_01_1080p` | 20 | 14 |
| WNBA | `wnba_02` | 20 | 13 |
| WNBA | `wnba_04` | 20 | 15 |
| WNBA | `wnba_05` | 20 | 15 |
| **Total** | **11 clips** | **220** | **147** |

## Recomputed visibility result

The primary denominator is all 220 unique `(clip, source_frame, slot)`
draws. A point is a named physical court landmark under the predeclared
protocol, not an extrapolated line crossing. The four-point rows identify all
four corners of one visible paint rectangle: two baseline/lane intersections
and two free-throw-line/lane intersections.

| Visible identifiable point features | Frames / 220 | Share |
|---|---:|---:|
| >= 2 | 161 | 0.732 |
| >= 3 | 147 | 0.668 |
| >= 4 | 147 | 0.668 |

The complete point-count distribution is 59 frames with zero, 0 with one, 14
with two, 0 with three, and 147 with four. This is intentionally conservative:
no three-point-arc or centre-circle landmarks were credited, even when partly
visible, because the four paint corners alone answer the reachability question.

### Named straight lines and independent directions

The 147 four-point frames each expose the named baseline, free-throw line, and
two lane sides; the 14 two-point frames expose a baseline plus the two lane
sides. That gives 59 frames with zero named straight lines, 14 with three,
and 147 with four. Parallel lane sides are one direction and the baseline plus
free-throw line are the other, so raw line count is not promoted into extra
constraints.

| Independent straight-line directions | Frames / 220 | Share |
|---|---:|---:|
| 0 | 59 | 0.268 |
| 1 | 0 | 0.000 |
| 2 | 161 | 0.732 |
| >= 3 | 0 | 0.000 |

The three-point arc and centre circle were not converted into fictitious
straight directions. They are nonlinear geometry and were not necessary for
the four-point visibility result.

## G84 overlap retained separately

G84's 33 frames were selected only from `PAINT_SOLVABLE` rows and are therefore
positive-biased. This census did not reuse that slice: just **1/220** seeded
draws overlaps it, `ncaa_basketball__ncaa_basketball_zqBCKovJCQU` frame
`28032` (slot 19). It remains in the primary 220-frame denominator and is not
reported as a separate supporting result. The other 219 draws are independent
of the G84 selection.

## Decision

**Basketball `court_feet` is geometrically reachable from this corpus in
147/220 seeded frames (66.8%) through four visible named paint-corner points;
the other 73 frames do not expose four such points.**

This answers the visibility/reachability hole only. It does not contradict
G84's 0/33 four-paint-line detector co-occurrence or G87's 11/12 true-input
gate pass: those are separate detector and gate measurements. A visible
four-point frame makes a solve geometrically possible; it does not establish
that the existing detector can recover the landmarks or that a solve would be
accurate.

## NOT VERIFIED

- No point, line, conic, or mixed homography was implemented, fitted, or
  scored.
- No detector's recovery, role assignment, or localization precision on these
  visible landmarks was measured.
- No `court_feet` coordinate declaration, held-out distance error, temporal
  calibration, or downstream tracking behavior was produced.
- This is the then-current 11-clip pod basketball corpus, not a claim about
  all basketball broadcasts, venues, leagues, cameras, or future corpus
  intake.
- The judgments are one-observer visual labels; no independent blind
  relabelling or inter-rater agreement measurement was performed.

## Verifier self-check

- **A7:** every evidence path named in this memo exists at report time:
  protocol, manifest, manual decisions, 220-row labels, summary,
  220 individual renders, and 11 contact sheets. The recomputable counts are
  also in [`g111_basketball_reach/summary.json`](g111_basketball_reach/summary.json).
- **B1 circular metric:** clear. Every seeded frame remains in the 220-frame
  denominator, including 59 frames with zero and 14 with only two points.
- **B2 non-additive schema:** clear. No production schema, reader, field, or
  status value changed.
- **B3 fall-through loss / B4 re-claim loop:** clear. No gate, quarantine, or
  claim behavior changed.
- **B5 pre-verification deploy:** clear. Pod access was read-only; no pod file
  or process changed.
- **B6 orphans:** clear. No module, import, command, or test was moved or
  retired.
- **B7 head-slice evidence:** clear. Every source clip contributes one seeded
  draw from every one of 20 temporal strata, and all 220 reviewed renders are
  committed.
- **B8 self-fit as independent:** clear. This is an eye-judged visibility
  census, not a fit residual or solver validation.
- **B9 degenerate denominator:** clear. The manifest-to-label join asserts 220
  unique `(clip, source_frame, slot)` units.
- **B10 moved bar:** clear. No threshold, coordinate contract, existing
  verdict, or G84/G87 result changed.
