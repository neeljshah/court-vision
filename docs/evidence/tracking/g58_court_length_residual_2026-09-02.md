# G58: tennis court-length residual -- diagnostic only

Date: 2026-09-02. This row names evidence; it does **not** apply a scale
factor, alter the solver, change any threshold, camera lock, 5.28 ft anchor or
coordinate contract, or deploy anything.

## Premise reproduced first

I parsed the terminal `length ratio` cell of every one of the 91 per-frame
rows in `g46_court_scale_premise_2026-09-02.md` before doing the diagnostic.
It reproduces G46 exactly: n=91, median=0.9878, mean=0.9884, sample
sd=0.0058, min=0.9664, max=1.0101. The four G46 per-clip medians are nyYk
0.9864, 459 0.9897, 06 0.9879 and 3x3 0.9906. G46 already falsified the
far-baseline-mislabel explanation; this row does not re-run it.

## Same-environment diagnostic arm and provenance

All new decoded-frame work was one read-only pod environment: Python 3.12.3,
cv2 4.14.0, NumPy 2.1.2, Linux, and the unchanged production G46 probe path.
The full stamped payload, seven selected frame ratios, source hashes and
position diagnostic are in
[`g58_measurement.json`](g58_renders/g58_measurement.json). The pod checkout
does not have `scripts/platformkit/tracking/run_environment.py`; copying it
would violate this row's no-deploy rule. Therefore the artifact records the
same additive stamp schema inline from the process that decoded the frames and
explicitly records that limitation. No local/pod numerical arms are compared.

The bounded visual/position sample has two evenly separated accepted G46 frames
in each multi-frame clip plus the sole accepted 3x3 frame: nyYk (0, 43942),
459 (76, 6882), 06 (498, 6249), and 3x3 (9053). Its ratios are respectively
0.992258/0.992563, 0.987653/0.992558, 0.990770/0.989118, and 0.990632.
This is an independent diagnostic sample, not a replacement headline for the
91-frame premise.

## Mandatory eye check

Each image below is a 16x nearest-neighbour pair: raw paint on the left,
identical crop with the production fitted far-baseline row in magenta on the
right. All seven were viewed.

- `g58_renders/g58_nyYk_0_paint_vs_fit.png`
- `g58_renders/g58_nyYk_43942_paint_vs_fit.png`
- `g58_renders/g58_459_76_paint_vs_fit.png`
- `g58_renders/g58_459_6882_paint_vs_fit.png`
- `g58_renders/g58_06_498_paint_vs_fit.png`
- `g58_renders/g58_06_6249_paint_vs_fit.png`
- `g58_renders/g58_3x3_9053_paint_vs_fit.png`

Observed in all seven: the far-baseline fit lies at the image-upward edge of
the bright paint band, not its centre. In the behind-near-baseline broadcasts
used here, image-upward is the court-exterior side of that far baseline. Thus
the observed far side is the opposite of the **inward** far edge required by
the proposed "inner edge at both ends" shortening mechanism. The renders do
not establish the near-baseline edge, so they do not prove an alternative
two-end mechanism.

## Hypotheses tested before any correction

| Rank | hypothesis | quantitative prediction vs 0.9878 | evidence and result |
|---:|---|---|---|
| 1 (survives, weak) | (b) unmodelled lens distortion | A pure homography error should covary with court image position/scale; no fixed ratio follows without a lens model. | In the seven-frame same-environment sample, ratio-vs-centre-y r=-0.302 and ratio-vs-court-height r=-0.295. Within clips the direction is inconsistent: 459 rises by 0.00491 as centre-y rises, while 06 falls by 0.00165. This is not the predicted monotone dependence, but n=7 is not enough to rule distortion out. |
| 2 (contradicted) | (a) line centre versus edge, specifically inward edges at both ends | Two 2-inch baseline widths remove 4 in from 78 ft: `1 - 4/936 = 0.9957` (0.43% short). Matching 0.9878 would require about 11.4 in total, or 5.7 in at each end. | The size is 2.85x too small for the stated 2-inch paint, and all seven far-line eye checks put the fit on the exterior, not inward, edge. It predicts a persistent sign but is not supported as the named mechanism. |
| 3 (not viable under stated conventions) | (c) incorrect singles/doubles court constant | Singles and doubles have the same 78 ft baseline-to-baseline length, so that convention predicts ratio 1.000 in this length axis; a 27/36 width mix-up predicts 0.750 or 1.333 in width, not 0.9878 in length. | The 1.2% length residual is not explained by the stated singles/doubles alternative. A nonstandard venue length is unmeasured, not established. |

## Conclusion

**No hypothesis is supported strongly enough to name a cause.** Lens distortion
is the only survivor, but only because the bounded position check does not
eliminate it; it is not confirmed. The leading inward-edge explanation is
quantitatively too small and conflicts with the visible far-edge side. No
correction factor is proposed or applied.

## What would distinguish the survivors

- A surveyed or high-resolution centre-to-centre baseline reference, with both
  near and far paint edges marked, would test the complete two-end edge model.
- A calibrated radial-distortion solve or deliberately varied court placement
  in the image would test whether residual tracks radial position.
- Venue documentation or a physical survey would test a nonstandard length.

## NOT VERIFIED

- The exhaustive new 200-frame-per-clip pod scan did not return before the
  terminal's 30-second execution window; it was not polled. The headline remains
  the exactly reproduced 91-frame G46 premise, not a new exhaustive claim.
- The near-baseline paint side is not rendered here.
- The bounded n=7 position test is insufficient to falsify lens distortion.
- The pod's missing `run_environment.py` means the attached stamp is
  schema-equivalent inline provenance rather than an import of that helper.
- No held-out correction test exists, because no correction is warranted.

## Verifier self-check (A7 and section B)

- **A7:** Every path named in the mandatory-eye-check list and the measurement
  JSON exists at write time; this was checked before commit.
- **B1:** No rows were excluded after a failing metric; the 91-row premise is
  fully parsed, and the seven visual frames are named explicitly.
- **B2-B6:** No production schema, gate, claim state, module, test, import or
  deployment changed.
- **B7:** Visual frames span every G46 clip and use separated frames, not a
  head slice.
- **B8:** No correction is fitted or scored on these frames.
- **B9:** The metric is the nonconstant solved-length ratio from G46.
- **B10:** No harness threshold or gate value changed.
