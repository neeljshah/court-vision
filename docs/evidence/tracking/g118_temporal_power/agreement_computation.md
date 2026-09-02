# G118 pooled agreement computation

The decision metric pre-registered in `G118_spec.md` is pooled blind temporal-strip versus G85 agreement. The strip method is BETTER only if the lower endpoint of its two-sided 95% Wilson interval exceeds the still-frame point estimate of 75.0%.

The pool contains every source-available G65/G85 identity: 29 committed G102 blind labels and 11 committed G118 blind labels, for 40 unique source-frame decisions. The 20 `tennis_10` identities are excluded only because their source MP4 is unavailable, as named before labelling in `pre_label_protocol.md`.

`pooled_agreement_against_g85.csv` contains 33 agreements among 40 rows, so the agreement estimate is `33 / 40 = 0.825000` (82.5%). The two-sided 95% Wilson interval uses `z = 1.959963984540054`:

`denominator = 1 + z^2 / n`

`centre = (p + z^2 / (2n)) / denominator`

`half_width = z * sqrt((p(1-p) + z^2/(4n)) / n) / denominator`

For `n = 40` and `p = 33/40`, the interval is `[0.680500, 0.912546]`, or 68.1% to 91.3% after one-decimal percentage rounding. Its lower bound is below 75.0%, so the pre-registered BETTER rule is not met.
