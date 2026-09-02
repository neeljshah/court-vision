# G92 calibrated tennis ball criterion card

Use this card only at tiled 2x. `ball_visible` requires a compact, separately
locatable ball-shaped mark with an edge that can be distinguished from the
surface it crosses. A brightness change, a court-line fragment, a diffuse
motion trail, or an object whose compact head cannot be located is
`uncertain`. Do not infer a call from a neighbouring frame.

The 14 committed exemplars were selected outside G85's fixed 60-frame seed;
the G85 blind labels therefore remain a held-out agreement comparison.

## Clear calls

| Call | Frame | Result | Why it is clear |
|---|---|---|---|
| [tennis_09 7028](exemplars/tennis__tennis_09_f07028.jpg) | `7028` | `ball_visible` | Compact high-contrast mark is separately locatable. |
| [tennis_09 7076](exemplars/tennis__tennis_09_f07076.jpg) | `7076` | `ball_visible` | Compact high-contrast mark is separately locatable. |
| [tennis_09 7106](exemplars/tennis__tennis_09_f07106.jpg) | `7106` | `ball_visible` | Compact high-contrast mark is separately locatable. |
| [tennis_09 7118](exemplars/tennis__tennis_09_f07118.jpg) | `7118` | `ball_visible` | Compact high-contrast mark is separately locatable. |
| [tennis_10 4073](exemplars/tennis__tennis_10_f04073.jpg) | `4073` | `uncertain` | No compact head separates from the blur. |
| [tennis_10 4088](exemplars/tennis__tennis_10_f04088.jpg) | `4088` | `uncertain` | No compact head separates from the blur. |
| [tennis_10 4103](exemplars/tennis__tennis_10_f04103.jpg) | `4103` | `uncertain` | No compact head separates from the blur. |
| [tennis_10 4108](exemplars/tennis__tennis_10_f04108.jpg) | `4108` | `uncertain` | No compact head separates from the blur. |

## Boundary adjudications

| Frame | Result | One deciding feature |
|---|---|---|
| [tennis_10 4113](exemplars/tennis__tennis_10_f04113.jpg) | `ball_visible` | A compact approximately 3-pixel head remains distinct from its short blur. |
| [tennis_10 4128](exemplars/tennis__tennis_10_f04128.jpg) | `uncertain` | Motion-blur streak has no separately locatable compact head. |
| [tennis_10 4233](exemplars/tennis__tennis_10_f04233.jpg) | `ball_visible` | The partial-frame object still has a compact closed head before the frame edge. |
| [tennis_10 4248](exemplars/tennis__tennis_10_f04248.jpg) | `uncertain` | Its contrast against the court does not support a distinct compact boundary. |
| [tennis_10 4258](exemplars/tennis__tennis_10_f04258.jpg) | `uncertain` | Motion-blur streak length exceeds the compact head, which is not separable. |
| [tennis_10 4268](exemplars/tennis__tennis_10_f04268.jpg) | `ball_visible` | A compact approximately 4-pixel head is distinct from the court. |

`calibrated_labels.csv` is an add-only, one-pass relabel of exactly the 109
rows that were `uncertain` in G65. It retains no coordinates: this is a
visibility criterion calibration, not a coordinate relabel or a detector
label set.
