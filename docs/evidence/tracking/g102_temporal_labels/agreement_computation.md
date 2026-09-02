# G102 agreement computation

The G102 blind file uses `true` and `false` for the same binary operational call used by G85: `true` normalizes to `ball_visible`; `false` normalizes to `uncertain`. Clip identity is normalized only for the join: `tennis__tennis_09.mp4` to `tennis_09`, and `tennis__tennis_nyYk2nPZAwY_720p.mp4` to `nyYk_720p`.

`agreement_against_g85_blind_labels.csv` has 29 unique overlapping identities. It contains 24 agreements, so the measured agreement is `24 / 29 = 0.827586` (82.8%). The two-sided 95% Wilson interval uses `z = 1.959963984540054`:

`denominator = 1 + z^2 / n`

`centre = (p + z^2 / (2n)) / denominator`

`half_width = z * sqrt((p(1-p) + z^2/(4n)) / n) / denominator`

For `n = 29` and `p = 24/29`, the interval is `[0.654516, 0.924021]`, or 65.5% to 92.4% after one-decimal percentage rounding.
