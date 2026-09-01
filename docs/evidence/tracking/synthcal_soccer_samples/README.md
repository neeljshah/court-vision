# Soccer SynthCal broadcast samples

These twelve PNGs are deterministic CPU-only evidence renders made with seed
`20260901` and consecutive offsets.  The sampler's geometry guard validates
200 deterministic poses: pitch-polygon share median >= 0.55, p10 >= 0.30, and
named-landmark visibility median >= 6.

Appearance deltas retained from the orchestrator's tennis real-frame review:

- structured crowd and stand background plates, not unstructured noise;
- hard directional shadows across the pitch; and
- broadcast-graphics decoys, including a scorebug and lower-third.
