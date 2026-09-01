# Football Wave 6F: field ROI and resolution integrity

## Field-ROI change

LSD now receives a grayscale image masked by the existing HSV grass support,
modestly dilated to retain white paint. Detected segments must also retain at
least 85 percent sampled support in that mask before angle grouping and family
clustering. This removes ESPN overlay and border segments without relaxing the
cross-ratio gate.

The focused synthetic regression uses a bright, four-edge top graphics bar and
fainter vertical field markings. The selected family is the field family; the
bar lies outside the support mask.

## Identical-input 720p funnel

Each row uses 120 evenly spaced seek positions. `line_detection` means a
length-qualified candidate segment survives the selected extraction mode.
`yard_family` is the unchanged cross-ratio gate; `numerals` is the existing
two-digit contour source gate on that same candidate family.

| Input | Mode | Decoded | Field view | Line detection | Yard family | Numerals | Joint yard + numerals |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `football_wHZt1eY3A9s.f136.mp4` | full frame | 120 | 120 | 120 | 0 | 120 | 0 |
| `football_wHZt1eY3A9s.f136.mp4` | field ROI | 120 | 120 | 120 | 0 | 120 | 0 |
| `reference/football.mp4` (Giants-Jets, 1280x720) | full frame | 120 | 55 | 55 | 0 | 55 | 0 |
| `reference/football.mp4` (Giants-Jets, 1280x720) | field ROI | 120 | 55 | 55 | 0 | 55 | 0 |

The `f136` file identifies as 1280x720 but is only 10,476,460 bytes for a
7,731-second declared duration and emits repeated partial-H264 decode errors.
Its row is retained as an observed diagnostic, not valid calibration evidence.
The readable Giants-Jets 720p control still has zero joint frames. The declared
30-frame gate therefore fails: no line-DLT, NFL 6-ft numeral scale check,
adapter run, or frozen harness run occurred. Scale median/p95/n are undefined
because the scale gate was never entered.

## Honest 1080p re-stage

Cookie-backed `yt-dlp -F` enumerated format 96 as `1920x1080`. A first request
that combined format 96 with the web player client was unavailable; retrying
format `96[height>=1080]` with cookies and the TV HLS client downloaded source
seconds 600-900. Local `ffprobe` measured 1920x1080 and 300.066 seconds before
publication. The bridge published atomically as
`football__giants_jets_format96_1080p.mp4`; remote `ffprobe` independently
measured the same 1920x1080 and 300.066 seconds.

The bridge now accepts `required_height` and calls `ffprobe` both after a
download and immediately before staging. A requested 1080p artifact fails
closed unless its measured height is exactly 1080, preventing a mislabeled 720p
file from being staged as a control again.
