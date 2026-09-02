# G82: `jump_p95` tail-blindness measurement

Date: 2026-09-02. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`,
including A7 and section B. This lane is read-only with respect to the harness:
`scripts/platformkit/tracking_harness.py` was imported only. No threshold, gate,
verdict, source row, or production setting changed.

## Scope and physical definition

G38 found the material tennis-selection defect in the physical **10--29 ft**
step band, not in a percentile-defined band. This memo therefore defines an
oversized step as one whose Euclidean consecutive-row displacement is in
10--29 ft, inclusive. That definition precedes and is independent of the p95
being assessed.

The retained local corpus has one tennis `court_feet` table with measurable
player jumps: `G83_tennis_09` (74 steps). G38B records that the four original
G38 tables are no longer retained as rows, so they were not silently replaced
with their historical report values. The real other-sport contrast is the
retained basketball table `0022501165` (35,188 player steps). The full source
inventory is `g82_jump_statistic/corpus_inventory.csv`; its source SHA-256s at
measurement time were `3928D7CF773BC20CCD637383A933F5AB0CF21A356BB7F361E9E72098F83A7555`
(tennis) and `F59952797DB47442C380D069E1D9C3BA6782D8422D0F2E16133D9D06C3B60CAC`
(basketball).

## Independent sweep reproduction

`g82_jump_statistic/reproduced_sweep.csv` independently recreates the audit's
construction: 40-ft teleports inserted among 0.6-ft steps. It agrees on the
decision boundary: 2%, 3.33%, and 5% prevalence remain under the 8-ft p95 bar;
6.67%, 8.33%, 10%, and 12.5% fail it. At the exact 5% row pandas' linear
quantile is 2.57 ft, rather than the audit memo's displayed 0.60 ft, but it is
still a PASS; the audit's conclusion (tail defects below roughly 6% do not
fail) reproduces. This difference is documented rather than rounded away.

## Real-table measurements

`g82_jump_statistic/per_table_statistics.csv` is the durable full-precision
table. `gap-normalized` means `distance / (frame_gap / modal_sampling_stride)`
in ft per nominal sampled step; it is not ft/s, because G83's missing historical
sampling metadata makes a true speed statistic unavailable.

| table | current `jump_p95` ft | max ft | count 10--29 ft | gap-normalized max ft/stride |
|---|---:|---:|---:|---:|
| tennis_09_retained | 1.64 | 2.32 | 0 | 2.32 |
| basketball_0022501165 | 2.16 | 10.21 | 16 | 10.21 |

The current tennis table has no oversized steps, so no real prevalence claim is
invented for it. In the basketball contrast, all **16 / 16 = 100.0%** of the
physically oversized steps are above the 2.16-ft p95 and are invisible to that
summary statistic. Their prevalence is **16 / 35,188 = 0.0455%**, well below
the roughly-6% structural trip point. Thus the real retained contrast falsifies
the proposition that the p95 necessarily reveals rare 10--29-ft defects; it
does not establish prevalence for the unavailable original G38 tennis rows.

The row-versus-frame census is separate from the percentile result:

| table | row diffs | modal stride | diffs above stride | share | largest gap |
|---|---:|---:|---:|---:|---:|
| tennis_09_retained | 74 | 2 frames | 0 | 0.00% | 2 |
| basketball_0022501165 | 35,188 | 3 frames | 4,812 | 13.68% | 1,188 |

Consequently, 4,812 basketball consecutive-*row* differences are not
consecutive sampled-frame steps. They must not be interpreted as instantaneous
movement. The gap-normalized comparison exposes that distinction without
claiming a true time-unit speed.

## Mandatory visual check

The six rows in `g82_jump_statistic/eye_check_selection.csv` are evenly spaced
over the frame-sorted 16-step decision set, not a head slice. Each corresponding
`render_*.png` is a pair of source-table court-coordinate frames, inspected in
this lane. The 0022501165 broadcast source named in its retained `run.log`
(`data/videos/full_games/0022501165.mp4`) is not locally retained, so these are
coordinate renders, not broadcast-pixel assertions.

| render | frames / gap | displacement | inspected classification |
|---|---:|---:|---|
| 01 | 150 -> 153 / 3 | 10.14 ft | teleport class: 3 frames at the logged 29.97 fps is about 0.10 s; not genuine fast movement. |
| 02 | 672 -> 693 / 21 | 10.08 ft | re-appearance across a gap; not a one-step movement claim. |
| 03 | 15141 -> 15144 / 3 | 10.03 ft | teleport class; not genuine fast movement. |
| 04 | 15444 -> 15462 / 18 | 10.05 ft | re-appearance across a gap; not a one-step movement claim. |
| 05 | 17625 -> 17628 / 3 | 10.08 ft | teleport class; not genuine fast movement. |
| 06 | 21576 -> 21579 / 3 | 10.21 ft | teleport class; not genuine fast movement. |

No selected row is labelled a genuine fast movement. Pixel-level identity or
occlusion is **not verified** because the source broadcast is absent; the
classification is limited to the viewed coordinate pairs plus their frame gap.

## Proposal only; no bar move in this row

For future adjudication, replace raw-row `jump_p95` with **gap-adjacent
`jump_max`**: the maximum displacement among pairs whose frame gap equals the
table's observed modal sampling stride. Retain the current sport-specific bars
unchanged (8.0 ft tennis, 6.0 ft basketball). The max sees a single tail event;
the gap condition avoids treating a re-appearance as an instantaneous step.
This is a statistic proposal, not an implementation or a new threshold.

On the two current retained source tables, the proposal's complete full-verdict
impact is in `g82_jump_statistic/verdict_impact.csv`: **0 current PASS tables
would fail; 0 current FAIL tables would pass**. Tennis is currently PASS and
its gap-adjacent max is 2.32 ft, below 8.0. Basketball is currently FAIL the
coordinate contract (missing calibration sidecar) and would remain FAIL; its
quality-only p95 is 2.16 ft below 6.0 while its gap-adjacent max is 10.21 ft,
so the proposed metric would add the intended diagnostic failure without
changing its full verdict. This count includes every retained real table used
by this measurement; the historic G38 reports are not counterfactually scored
because their row tables are absent.

## Verifier self-check

- A7: every path named in this memo exists at report time, except the explicitly
  absent original G38 rows and 0022501165 broadcast, which are not evidence
  paths and are listed as not verified.
- B1: oversized is the named physical 10--29-ft band; no p95 result defines or
  excludes it.
- B2--B4: no schema, reader, claim route, or gate changed.
- B5: no pod, deploy, copy, process, or remote mutation was performed.
- B6: no production module was moved or retired; the new measurement helper is
  additive and has one focused per-file test.
- B7: the six visual checks are evenly selected across the 16-row decision set.
- B8: no fitted or self-fit quantity is presented as independent evidence.
- B9: denominators are literal player-row differences and explicitly reported;
  no recycled identifier is used as a unit count.
- B10: `tracking_harness.py` and all threshold values are unchanged.

## Evidence paths

- docs/evidence/tracking/g82_jump_statistic/corpus_inventory.csv
- docs/evidence/tracking/g82_jump_statistic/per_table_statistics.csv
- docs/evidence/tracking/g82_jump_statistic/reproduced_sweep.csv
- docs/evidence/tracking/g82_jump_statistic/oversized_steps_above_p95.csv
- docs/evidence/tracking/g82_jump_statistic/eye_check_selection.csv
- docs/evidence/tracking/g82_jump_statistic/verdict_impact.csv
- docs/evidence/tracking/g82_jump_statistic/render_01_frames_150_153.png
- docs/evidence/tracking/g82_jump_statistic/render_02_frames_672_693.png
- docs/evidence/tracking/g82_jump_statistic/render_03_frames_15141_15144.png
- docs/evidence/tracking/g82_jump_statistic/render_04_frames_15444_15462.png
- docs/evidence/tracking/g82_jump_statistic/render_05_frames_17625_17628.png
- docs/evidence/tracking/g82_jump_statistic/render_06_frames_21576_21579.png
- scripts/platformkit/g82_jump_statistic_measure.py
- scripts/platformkit/test_g82_jump_statistic_measure.py

## NOT VERIFIED

- The original G38 tennis_02 through tennis_05 row tables are absent, so their
  historical 10--29-ft prevalence cannot be recomputed and is not reported.
- The 0022501165 broadcast file is absent locally, so visual classifications are
  coordinate-render classifications, not source-video identity adjudications.
- G83 has not supplied historical production sampling metadata; no ft/s claim
  is made from either retained table.
