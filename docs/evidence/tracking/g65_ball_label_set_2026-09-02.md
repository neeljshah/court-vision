+# G65 tennis ball label-set attempt

Date: 2026-09-02. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`,
including A7 and section B.

## Outcome

This is a durable, detector-independent **review set**, but it is not a usable
coordinate label set: all 150 rows are explicitly uncertain. I reviewed the
renders by eye, did not run `MotionDiffDetector` or any ball detector, and
will not invent ball centres, radii, or false negatives from small/motion-blurred
dots. This is an honest limitation, not a detector result.

## Sampling

Seed: `650913`. Three visually checked continuous wide-court rally windows
were selected before any calls were recorded:

- `tennis__tennis_09.mp4`: [6962, 7257), 1920x1080, 50 frames at
  `6962 + 6*i`.
- `tennis__tennis_nyYk2nPZAwY_720p.mp4`: [33857, 34152), 1280x720,
  50 frames at `33857 + 6*i`.
- `tennis__tennis_10.mp4`: [4043, 4289), 1920x1080, 50 frames at
  `4043 + 5*i`.

The `tennis_10` clip was decoded read-only on the pod and streamed to the
worktree as image renders; no code was copied to the pod and no pod file was
written. The initial close-up-containing range was discarded before labels
were written. The 150 source-frame renders and review sheets are committed
under `g65_ball_labels/renders/`.

Coordinate contract: the CSV's `center_x_image_px`,
`center_y_image_px`, frame dimensions, and radius are all **image_px**.
They are not court_feet. A blank coordinate/radius is deliberate only where
`uncertain=true`.

## Eye review and counts

I saw active wide-court rallies in all three selected windows. The hard cases
were the expected ones: small balls against similarly bright court lines,
motion blur in flight, balls hidden by players/rackets/net, and frames where a
ball may have already left the image. I could not resolve a centre and radius
to the required image-pixel standard without guessing.

- Confirmed visible-ball labels: 0 / 150 (all 150 were uncertain).
- Of confirmed visible labels inside `y < 2/3 * height`: 0 / 0; fraction and
  Wilson interval are not estimable.
- Uncertain: 150 / 150 (100.0%; Wilson 95% 97.5%--100.0%).

Therefore this artifact does **not** independently re-measure G44's published
64% or 52% fractions; it establishes that these particular manually reviewed
renders cannot support a pixel-coordinate measurement by this reviewer
without fabricated labels. No recall, precision, detector change, spatial-rule
proposal, solver change, coordinate-contract change, or threshold change is
made here.

## A7 and B self-check

All memo evidence paths exist: this memo, `labels.csv`, and the
`renders/` directory. The CSV contains 150 unique (clip, source_frame)
pairs across three clips, with every required field present or explicitly
uncertain with a reason. Sampling is seeded and not a head slice. No detector
output informed a label, no schema reader/module/gate changed, no pod deploy
occurred, and no threshold moved. B1--B10 therefore have no applicable
metric, fit, schema, deployment, orphan, head-slice, self-fit, denominator, or
bar-moving violation.

## NOT VERIFIED

- Any resolved image-pixel ball centre/radius in this review set.
- A valid remeasurement of G44's visible-ball or spatial-gate fractions.
- Recall, precision, or any detector evaluation.

