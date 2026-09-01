# Football Wave 6E 1080p resolution control

Source: `football_wHZt1eY3A9s` (Giants at Jets), same source window as Wave
6D. The cookie-backed HLS format 96 fetch was bounded to 600-900 seconds and
produced a 300.066-second, 1920x1080, 29.970-fps MP4 (148,362,741 bytes).
Frames at 60, 120, 180, and 240 seconds were rendered before staging; each was
the same ESPN Giants-Jets NFL broadcast. The file was published with
`footage_bridge.push_staged`, which uploaded `<name>.mp4.part` then atomically
renamed it in `data/footage_bridge/` on the pod.

The pod run used `nice -n 15`. It selected 120 positions evenly across the
five-minute clip; 118 decoded and 68 were field views. The 720p counts are the
prior Wave 6D 60-position measurement; its 28 field views are the appropriate
denominator for its 27 numeral and one yard-family survivors.

| Funnel stage | 720p (60 positions) | 1080p (120 positions) |
| --- | ---: | ---: |
| Decoded samples | 60 | 118 |
| Field view | 28 | 68 |
| LSD line detection | 28 | 68 |
| Yard-line family clustering | 1 | 0 |
| Numeral source candidate | 27 | 68 |
| Two hash-row detection | 0 | 0 |

The 1080p frame probe has no yard-family survivor, hence no hash-row pair,
line-DLT correspondence, or independent scale observation. Numeral visibility
alone does not establish image-to-field scale. The joint `>= 30` yard-cluster
and numeral gate fails: `0` and `68`, respectively.

Scale `n=0`; median and p95 scale error are not defined. The adapter and
frozen harness were intentionally not run. This is a resolution-control
rejection, not a court-feet tracking result.
