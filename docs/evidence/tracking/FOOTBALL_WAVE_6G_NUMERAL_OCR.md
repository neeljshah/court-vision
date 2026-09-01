# Football Wave 6G: numeral-anchored registration

## Input and method

Measured `football__giants_jets_format96_1080p.mp4` on the pod. `ffprobe`
reported 1920x1080 at 30000/1001 fps. The probe sampled 120 evenly spaced
positions with one independent CPU EasyOCR reader at nice 15. It retained the
largest field-paint numeral candidate per field-view frame, read it using the
digits-only allowlist, and accepted only confidence >= 0.60 and values 10, 20,
30, 40, or 50 (including a single 1--5 digit as a split broadcast numeral).

The manifest and five highest/lowest-confidence rendered crops are retained at
`/tmp/codex_football_wave6g/output/` on the pod. They are diagnostic artifacts,
not repository evidence inputs.

## Measured denominators

| Measure | Result |
| --- | ---: |
| requested positions | 120 |
| decodable sampled frames | 118 |
| field-view frames | 68 |
| candidate-line frames | 68 |
| recognized numeral frames | 14 |
| recognized numerals | 14 |
| recognition rate over field-view frames | 14/68 (20.6%) |
| registration frames with >= 4 point correspondences | 0 |
| held-out numeral errors | n=0; median/p95 unavailable |
| 6-ft numeral-height scale errors | n=0; median/p95 unavailable |

## Verdict

**Reject, fail closed.** The run cleared the requested 60-field-view-frame
denominator but did not supply even one frame with two recognized numerals
(four point correspondences). Consequently the `n >= 30`, held-out median
<= 6 ft, and scale-within-10-percent gates are all unmet. The football adapter
and frozen harness were not invoked. There is no ball gate in this decision.
