# Football Wave 6H OCR measurement

## Result

Terminal OCR-path rejection. The required joint-numeral gate did not pass, so
no numeral correspondence solve, homography, independent scale check, adapter
run, or frozen-harness run was performed.

## Run contract

- Input: atomically staged `football__giants_jets_format96_1080p.mp4`
- Pod command: `nice -n 15 python /tmp/codex_football_wave6h.py ... --positions 120`
- Sampled/decoded frames: 118
- Field-view frames: 74 (minimum 60)
- Candidate crops: 444 (minimum 40), capped at six per frame
- OCR confidence floor: 0.60; valid painted values: 10, 20, 30, 40, 50

## Preprocessing sweep

| Variant | Valid reads | Denominator | Valid-read rate |
|---|---:|---:|---:|
| raw | 47 | 444 | 10.59% |
| grayscale plus Otsu | 55 | 444 | 12.39% |
| 3x upscale | 49 | 444 | 11.04% |
| grayscale plus Otsu plus 3x upscale | 34 | 444 | 7.66% |

Winner: grayscale plus Otsu (55/444, 12.39%).

## Winning-variant field-view distribution

| Valid reads in frame | Frames | Denominator |
|---|---:|---:|
| 0 | 41 | 74 |
| 1 | 15 | 74 |
| 2 | 14 | 74 |
| 3 | 4 | 74 |

Frames with at least two valid reads naming different yard lines: 13/74. The
minimum is 30/74, so this gate fails. The 2- and 3-read rows are not assumed
to contain different values; the independently measured distinct-value count
is the sole gate numerator.

## Evidence

Machine-readable denominators and rates: `football_wave6h_ocr/ocr_sweep.json`.
The directory also contains the required ten best and ten worst rendered crop
frames (`best_01.jpg` through `best_10.jpg`, `worst_01.jpg` through
`worst_10.jpg`).
