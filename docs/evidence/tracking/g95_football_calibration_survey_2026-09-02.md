# G95 Football Calibration Survey

**Date:** 2026-09-02
**Verdict:** ACCEPT WITH CORRECTIONS - the requested survey is complete, but four of the nine football-labelled corpus files are soccer footage and must not be treated as football calibration evidence.
**Contract:** `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections A and B.

## Scope and method

This is an eye-labelled feasibility survey only. It creates no solver, field transform, coordinate-space declaration, harness change, verdict change, or deployment.

The fixed seed is **95002**. For each of the nine corpus files listed in `sample_manifest.json`, the procedure was `random.Random(95002).sample(range(floor(0.05*n), floor(0.95*n)+1), 12)`, sorted before rendering. Thus it samples 12 unique frames from the interior 90 percent of each clip: **108 unique frames across all nine clips**. Each sampled frame appears in one of the 27 committed four-up contact-sheet renders. The visual labels are in `g95_football_survey/labels.csv`; the readable yard identity is stored in its `legible_yard_number` column, rather than inferred from a detector score.

## Existing stack survey

`scripts/platformkit/calibration/keypoint_calib.py` has canonical sets for basketball, tennis, and soccer only: **football has no `CANONICAL_LANDMARKS` set**. Neither required detector fills that gap. `scripts/platformkit/tracking/football_fieldview.py` identifies a broad turf/parallel-line shot and emits an image-space, no-location row; `football_snap.py` measures motion/snap events and also emits only image-space rows. Neither emits named geometric landmarks.

Football does have a separate, deliberately fail-closed line path. `domains/football/tracking/geometry.py` can find an unnamed yard-line family and two hash rows, and exposes a generic line homography solver. Before a transform, however, it requires `PaintedYardAnchorProvider`; that provider requires a readable 10/20/30/40/50 numeral **and** nearby directional arrow because `40`, for example, occurs at both ends of a field. Even with two hash rows, `homography_from_yard_lines` returns `independent_scale_unavailable`: it refuses to assume their near/far identity or NCAA/NFL scale. `line_probe.py` measures only family counts, not named correspondences. The chain therefore breaks at named absolute yard identity plus independently established scale; no current detector provides a calibration-ready named set to a solver.

This is not soccer's exact dead end. Soccer has 15 canonical landmarks and a provider that emits only `center_circle` against `MIN_LANDMARKS=5`. Football has no shared canonical set at all, and its purpose-built geometry path has ordinal line evidence but intentionally refuses to promote it without a resolved absolute anchor and scale proof.

## Visibility measurement

All shares use the full 108-frame seeded decision set; no frame was excluded after viewing. A non-football frame is retained in the denominator and receives no football-specific family credit.

| Family / condition | Visible frames | Share of 108 |
|---|---:|---:|
| Sideline | 17 | 15.74% |
| Goal line | 2 | 1.85% |
| End line | 0 | 0.00% |
| Yard-line stripes | 28 | 25.93% |
| Hash marks | 28 | 25.93% |
| Painted yard number | 18 | 16.67% |
| At least one legible yard number | 18 | 16.67% |

The yard-stripe count distribution is 80 frames with 0, 6 with 2, 11 with 3, 7 with 4, and 4 with 5. The `yard_line_stripe_count` column is a frame-local visual count, not a reused identity or a fitted residual.

| Clip | Content in eye check | Football frames / 12 | Stripe-visible | Legible-number |
|---|---|---:|---:|---:|
| `football__football_20pezoC5jRQ.mp4` | football | 12 | 3 | 3 |
| `football__football_34GmmlakBYU.mp4` | soccer | 0 | 0 | 0 |
| `football__football_5x9vPq9HsTI.mp4` | football | 12 | 9 | 6 |
| `football__football_B7znSVfBnM4.mp4` | soccer | 0 | 0 | 0 |
| `football__football_gek9fXGlwas.mp4` | soccer | 0 | 0 | 0 |
| `football__football_h-_3BmAh9po.mp4` | soccer | 0 | 0 | 0 |
| `football__football_wHZt1eY3A9s.mp4` | football | 12 | 5 | 5 |
| `football__football_wHZt1eY3A9s_1080p.mp4` | football | 12 | 5 | 1 |
| `football__giants_jets_format96_1080p.mp4` | football | 12 | 6 | 3 |

The four mislabelled files contribute 48/108 frames. They are retained because this lane is a survey over the specified nine-file corpus, but they are a corpus-content correction, not football geometry evidence.

## Geometry and aliasing

Football is geometrically friendly: its 5-yard stripes, hash marks, sidelines, goal lines, and end lines are high-contrast white markings on a relatively uniform field and, when a wide shot is present, are much denser than court markings in the other surveyed sports. It is also deceptive: the 5-yard stripes are periodic, so a stripe-only solve can move by an integral number of yards while retaining excellent internal residuals. That silent aliasing is the football-specific failure mode. A painted number plus direction arrow, or an independently resolved asymmetric hash-row identity tied to a known field level, must establish **which** yard line is being observed; the current stack has no emitted named correspondence that does so.

**One-sentence answer:** No - football is not calibration-limited in soccer's exact "geometry exists but a <5-landmark detector emits none" shape; it is limited first by 48/108 non-football corpus frames and, in actual football views, by the absent named absolute-yard/scale provider needed to break periodic stripe aliasing, with legible painted numbers present in only 18/108 seeded frames.

## Renders and label artefacts

- Manifest: `docs/evidence/tracking/g95_football_survey/sample_manifest.json`
- Labels: `docs/evidence/tracking/g95_football_survey/labels.csv`
- Renders: `docs/evidence/tracking/g95_football_survey/renders/clip_01_group_1.jpg` through `clip_09_group_3.jpg` (all 27 numbered files exist; each is a four-frame eye-check sheet).

## NOT VERIFIED

- No football homography, calibration, absolute anchor, coordinate space, or `court_feet` output was created or asserted.
- No solver was attempted, so there is no transform accuracy, held-out residual, tracking-quality score, or harness pass/fail claim.
- The eye labels do not establish that a future OCR or classifier can read a number; they establish only what was legible in these rendered broadcast frames.
- The nine-file corpus contains four soccer files despite their football filenames. This survey does not identify the cause or repair the corpus metadata.
- NFL/NCAA field level is not inferred from this survey, and hash-row separation is not treated as scale evidence.

## Verifier self-check

### A7 evidence paths

Before commit, the memo, requested spec, verifier contract, G47 census, calibration strategy, manifest, labels, the render directory, and every one of its 27 `clip_XX_group_Y.jpg` files were checked to exist. A missing path would make this result NOT VALIDATED.

### Section B

- **B1:** The metric includes all 108 seeded labels; the 48 non-football frames are named and retained, not excluded.
- **B2:** No schema, status, or reader changed; labels and renders are additive evidence only.
- **B3:** No gate behavior changed.
- **B4:** No claim, queue, or failure path changed.
- **B5:** The pod was read-only: frames were encoded in memory and streamed to the local evidence bundle; no source, deployment, restart, or pod artifact was written.
- **B6:** No module moved or retired.
- **B7:** Sampling uses a fixed seed across the interior 90 percent of every clip, 12 frames each; it is not a head slice.
- **B8:** No fitted transform or residual is presented as independent evidence.
- **B9:** The denominator is 108 unique `(clip_ordinal, frame)` pairs, not an identifier reused across frames.
- **B10:** No harness threshold, coordinate contract, or gate value changed.
