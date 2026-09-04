# G254 fixed protocol, written before scoring

Input is exactly G233d's published image-to-court matrix from
`g233d_seed_gate_validated_frame_artifact/g233d_measurement.json`, frame 19599
of the named native 1920x1080 WNBA source. No label is read or altered.

Reporting uses G252 unchanged: its WNBA curve geometry, 4-px projected samples,
Canny low/high 50/150 with 3x3 aperture and L2 gradient, and integer normal
search from -24 through +24 px. Found distances are reported conditionally;
no-candidate samples remain counted, and 24 px is right-censored.

The fit objective is the mean, with equal weight for each visible line type, of
squared `min(Canny_distance_transform_at_projected_sample, 24 px)`. This is a
detector objective only, not independent geometry evidence. The optimiser is a
deterministic four-coordinate pattern search on an image-space similarity
left-multiplied onto the seed forward projection: `(tx px, ty px, degrees,
log-scale)`. Initial steps are `(8, 8, 0.75, 0.005)`; failed sweeps halve all
steps; convergence is every step at or below `(0.0625, 0.0625, 0.005859375,
0.0000390625)`, with bounds `(192, 192, 12, 0.20)` and 240 iterations.

Before any result, `same answer` is fixed as p95 <= 2 px between the refined
and trial forward projections on all reference-refined in-image points of the
5-ft grid spanning 0..50 x 0..94 ft. Two pixels is materially tighter than the
24-px reporting search while permitting subpixel/raster variation.

The full fixed grid has 43 starts: identity; all four cardinal translations at
8, 16, 32, and 64 px; signed rotations at 0.5, 1, 2, 4, and 8 degrees;
scales 0.90, 0.95, 0.975, 1.025, 1.05, and 1.10; and signed joint ladders
`(tx,ty,rotation,scale)` of `(8,8,0.5,1.01)`, `(16,16,1,1.02)`,
`(32,32,2,1.04)`, `(64,64,4,1.08)`, `(96,96,6,1.12)`, plus their signed
reciprocal directions. The objective, detector, convergence rule, and grid
will not be changed after the eye-gate result.
