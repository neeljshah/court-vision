# Basketball SynthCal broadcast samples

These twelve PNGs are deterministic CPU-only evidence renders made with seed
`20260901` and consecutive offsets. The sampler's quantitative guard validates
200 deterministic poses: court-pixel share median >= 0.55, p10 >= 0.30, and
named-landmark visibility median >= 6.

The template uses the NBA Rule 1 94 x 50 ft court, 16 x 19 ft lane, 6 ft
free-throw and centre circles, 23 ft 9 in arc, and 22 ft corner distance.
The high-sideline camera ranges are provisional engineering assumptions: there
is no measured basketball SCCvSD-equivalent prior in this sampler.

Appearance coverage includes a structured upper-bowl crowd band, scorebug and
review graphics decoys, wood hue jitter, and player-like rectangles sampled
inside the two paint rectangles. This is GPU-free preparation only: no
basketball training is run unless the separately pre-registered tennis verdict
passes.
