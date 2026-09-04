**GATE: FAIL BEFORE FIT (n=1 pod clip identity-checked, 0 re-screened samples, 0 fitted frames, 0 identity crops, 0 withheld-geometry renders, 0 eye-gate judgements).** The claimed one-touchline joint system has a continuous unidentifiable degree of freedom, so no width, homography, residual, degeneracy value, or independent-geometry verdict is reported.

# G262: Soccer Width as an Unknown

**Verdict: CLOSED AT LIMIT (DOF premise false; full success).** This measurement-only result executes [G262](specs/G262_spec.md) and follows [the verifier contract](VERIFIER_CONTRACT.md). Its required first action was to verify the claimed degrees-of-freedom accounting and stop if it was wrong. It is wrong, so the required re-screen, manual inputs, and fit were not begun. No production module, `IMAGE_SPACE`, coordinate contract, label, threshold, pitch model, G253 harness, G259 survey, `src/`, or `domains/` file changed.

## Pod lane, source, and disk guard

Before pod access, an executable-and-complete-argument process listing was limited to `python` and `python3`, excluding the remote shell, its parent, and the `ps` checker. It returned no active Python measurement process. No resident process, including any G260 work, was interrupted.

The pod-only source was checked before the disk probe and before any decode. It matched the specified identity exactly:

| Field | Measured value |
|---|---|
| Source | `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4` |
| Bytes | 2,341,768,743 |
| SHA-256 | `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e` |
| Video stream | 1920x1080, 30/1 fps, 179,250 frames, 5,975.000000 s |

`df` was not used. `du -sm /workspace/nba-ai-system/data` was 33,191 MB. The binding command `dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g262_disk_probe.bin bs=1M count=1 conv=fsync status=none` created exactly 1,048,576 bytes; its size was verified, then that exact probe file was removed successfully. No corpus source or either abandoned `footage_bridge` partial was touched. Bytes freed: 1,048,576 (the probe only). No decode was started.

## DOF verification: the one-touchline claim is false

Use centre-anchored homogeneous pitch coordinates `(x, y, z)` with centre circle

`x^2 + y^2 = r^2 z^2`, where `r = 9.15 m`,

and halfway line `x = 0`. The image conic contributes five generic constraints and the halfway line contributes two, leaving the familiar one-dimensional stabilizer of the circle-plus-halfway configuration. The nominal count through this point is therefore correct: 7 constraints on an 8-DOF homography.

The error is treating a single unknown-width touchline as one additional independent constraint. For every real `t`, the projective transformation

`S_t = [[1, 0, 0], [0, cosh(t), r*sinh(t)], [0, sinh(t)/r, cosh(t)]]`

preserves both the circle and the halfway line. A touchline `y = w z` stays in the same unknown-width family under it:

`w_t = (cosh(t)*w + r*sinh(t)) / ((sinh(t)/r)*w + cosh(t))`.

As a direct numerical algebra check with `r=9.15`, `t=0.73`, and `w=31.0`, the maximum entrywise error in `S_t.T Q S_t - Q` for `Q=diag(1,1,-r^2)` was `1.421e-14`; the transformed touchline ratio differed from `w_t` by `0.000e+00`, and a point on `x=0` retained `x=0` to `0.000e+00`. This is a check of the stated invariance, not a fit or an image-derived metric.

Consequently, if `(H, w)` matches an observed circle, halfway line, and one observed touchline, then `(S_t H, w_t)` matches exactly the same three observed features for a continuum of `t`. The transformation changes the recovered width while leaving every fitted observation unchanged. The nominal arithmetic is 9 parameters and 9 scalar observations, but one of those observations is not independent in this special circle/diameter/parallel-line geometry; the local system has an unresolved one-dimensional gauge.

Thus a single touchline cannot determine the homography and half-width jointly, and any returned width would be initialization or regularization dependent rather than an objective plausibility check. Two symmetric touchlines can break this particular gauge because, generically, `S_t` does not map the pair `y = +/-w z` to another symmetric pair for nonzero `t`. That is a different, two-touchline configuration; it was not screened or fitted because G262 requires stopping when its stated accounting is wrong.

## Consequences of the mandated early stop

G259's committed 1,195-sample survey was deliberately not re-screened: the premise failure occurs before its result could create a legal one-touchline solve. Frame 5,400 was not admitted as a fit input, even though G256b records its centre circle and halfway line. Therefore there are no fitted line or conic identity crops, no observed arc fraction, no image line angle, no system condition number, no recovered pitch width, and no withheld penalty-box, goal-area, penalty-arc, or second-touchline render.

The width check and the eye gate are separate evidence channels, but both are **NOT MEASURED** here: the first has no identifiable width, and the second has no projection to judge. In particular, no fit residual is offered as a substitute for either channel. This preserves the G257 limit: a future eye PASS would only bound error at roughly its 20-pixel resolution and would not certify correctness.

## Contract self-check and limitations

A7: the on-tree evidence named by this memo is this memo, the pre-existing [G259 survey manifest](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_manifest.json), and the referenced [G256b memo](g256b_soccer_line_conic_calibration_2026-09-04.md); all exist. B1: no screened or fitted denominator is hidden--the theoretical stop gives 0 re-screened samples and 0 fits. B2-B6: no schema, reader, claim lifecycle, deployment, or module move changed. B7: no render sample is presented. B8: no self-fit quantity is offered as independent evidence. B9: no recycled metric denominator exists. B10: no threshold, bar, coordinate contract, `IMAGE_SPACE`, or harness setting moved. Q does not apply to this tracking measurement row. No harness was added, so no test or A12 allowlist change applies.

**NOT VERIFIED:** the G259 re-screen counts for circle plus halfway line plus one or both touchlines; feature identity for a fitted line or conic; a homography; a pitch width or Laws-range plausibility verdict; circle coverage, image angle, or condition number for a legal fit; an independent-geometry eye gate; G252 offsets; any pitch coordinates; propagation; detection; tracking; automatic calibration (still 0/17); or production behavior. This remains one clip and one camera plan only; the four soccer negatives describe this broadcast rather than soccer footage generally. A future two-touchline experiment would still consume manual geometry and would not be automatic calibration. A plausible width, if a legal configuration were later found, would be necessary but not sufficient and never a stadium measurement.
