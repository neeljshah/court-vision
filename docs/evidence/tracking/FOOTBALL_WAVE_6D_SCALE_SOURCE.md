# Football Wave 6D: 720p scale-source audit

Source: `football_wHZt1eY3A9s`, staged as
`data/footage_bridge/football__football_wHZt1eY3A9s.mp4` on the pod. The
source is 1280x720, 29.970 fps, 28,904 decoded frames. On 2026-09-01, 60
evenly spaced frames were decoded at `nice -n 15`; 28 were field views.

| Explicit NFL reference | Clean detections / 60 | Rule-fixed dimension | Result |
| --- | ---: | --- | --- |
| Painted field numeral pair | 27 | 6 ft tall | Most measurable source |
| Adjacent yard-line pairs at two depths | 1 | 15 ft | Insufficient |
| One hash row plus near sideline | 0 | 70 ft 9 in | Unresolved |
| Solid white field border | 8 | 6 ft | Insufficient |

`football_scale_crops/` contains five labelled diagnostic image crops for each
candidate. A crop labelled `resolved` met that candidate's fixed detector;
`not_resolved` records the same field-view sampling funnel rather than hiding
the failure cases.

The numeral candidate is selected by its 27-frame measurability count. It does
not yet produce a usable scale observation: this broadcast pilot never yields
a fresh image-to-field homography with which to map the observed six-foot
numeral height. Therefore the actual scale-consistency sample is `n=0`, with
median and p95 error both `N/A`; it cannot meet the `n >= 30` and p95 <= 10%
gate. The adapter and immutable frozen harness were deliberately not run.

The geometry adapter now contains an explicit-NFL numeral-height check. It
accepts a caller-supplied image-to-field homography and resolved painted
numeral bounding box, returns the percent error from six feet, and returns no
result for non-NFL field levels. The production path remains fail-closed;
neither a league nor a scale is inferred from pixels.

Rule references: the NFL field-marking diagram specifies six-foot playing-field
numerals, and the Rule 1 field-markings text specifies professional hashes at
70 ft 9 in from each sideline and the solid white border at six feet. See the
[NFL Rulebook](https://operations.nfl.com/rules-officiating/2026-nfl-rulebook)
and its [field-markings diagram](https://operations.nfl.com/media/24emxacq/2024-nfl-rulebook.pdf).

Acquisition note: local cookie-backed `yt-dlp -F` recorded a published 1920x1080
format (ID 96) for this video. No new media was downloaded.
