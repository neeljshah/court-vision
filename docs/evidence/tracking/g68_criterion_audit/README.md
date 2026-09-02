# G68 criterion spot-check (orchestrator, 2026-09-02)

An orchestrator spot-check of the basketball paint census, done BEFORE the
aggregation (G68D) declares a verdict and before G75 is dispatched on the result.

## What I did

Opened `g68_paint_census/contact_sheets/wnba__wnba_02/sheet_00.jpg` (3200x1920,
25 tiles, frame indices burned in), then cropped individual tiles at native tile
resolution and upscaled 2x to judge them properly rather than from the
downscaled sheet.

## What I found

| frame | census label | my read |
|---|---|---|
| f192 | PAINT_SOLVABLE | **WRONG.** No paint in the frame at all. Midcourt perimeter action, neither basket in shot. A three-point arc and the centre-court WNBA logo are visible; the baseline, free-throw line and both lane lines are absent. Should be COURT_NO_PAINT. |
| f2112 | PAINT_SOLVABLE | **ARGUABLE, not wrong.** The paint's dark fill IS present and partly bounded, with the basket top-right and the free-throw circle visible. Whether all four lines have fittable extent is genuinely debatable -- the baseline is partly occluded by the scorebug. |
| f1152 | COURT_NO_PAINT | Agree. Centre-court logo, clearly no paint. |

## What this does and does not establish

It establishes **one verified mislabel** in three tiles checked, on a clip whose
census figure is 107/150 = 71.3 pct PAINT_SOLVABLE. It does NOT establish that
the census is uniformly wrong -- one of the three was correct and one was
defensible. The labelling looks PERMISSIVE AT THE MARGIN rather than random.

## Why the existing re-read does not cover this

G68A reported that its seeded 20-tile full-resolution re-read "retained every
label", zero flips. That measures **reliability, not validity**: a criterion that
is uniformly too permissive reproduces itself perfectly on re-read. A repeat of
the same judgement cannot detect a systematically wrong judgement. The re-read
was worth doing and its result is real; it just does not answer this question.

## Consequence

The pooled census must not be turned into a verdict, and G75 (the paint solver's
role-assignment caller) must not be dispatched on it, until the CRITERION is
audited: a sharp written definition of PAINT_SOLVABLE with a rendered positive
and negative example, then a re-label of a seeded sample against that definition,
reporting the disagreement rate with the current labels.

This matters because of what the number is for. The census exists to decide
whether the per-frame paint route is worth building. A permissive criterion
inflates the share and sends a solver lane after geometry that is not actually
in the frames -- which is the expensive failure this whole census was designed
to prevent.
