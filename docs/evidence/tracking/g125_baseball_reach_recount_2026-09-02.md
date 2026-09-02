# G125 baseball reachability denominator recount

**Verdict: ACCEPT WITH CORRECTIONS.** This additive recount corrects a
published baseball reachability denominator after G117 identified two G104
source clips as quarantined studio/statistics programmes. It follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7 and the section B
self-check below. No G104 label, seed, threshold, coordinate contract,
quarantine decision, or non-baseball verdict is changed.

## Scope and fixed inputs

The source decision set is exactly G104's seeded 120 rows, not a new sample:
its seed, manifest, and labels remain in
[`g104_baseball_reach/sample_manifest.json`](g104_baseball_reach/sample_manifest.json)
and [`g104_baseball_reach/frame_labels.csv`](g104_baseball_reach/frame_labels.csv).
G117 eye-confirmed that the two named clips below are each 0/5 live action and
quarantined them; G117 did not change G104's old metric
([`g117_kbo_studio_quarantine_2026-09-02.md`](g117_kbo_studio_quarantine_2026-09-02.md)).

The exclusion is therefore mechanical and named before recounting: exclude
only the 20 G104 rows from each of these G117-quarantined clips.

- `kbo__kbo_FDSWjM_OaTs.mp4`: slots 1--20
- `kbo__kbo_bGQwZl43E9Y.mp4`: slots 1--20

All 40 rows, including source-frame keys, unchanged content labels, zero
visible-point counts, and exclusion reason, are retained in
[`g125_recount/excluded_frames.csv`](g125_recount/excluded_frames.csv). The
table is a join of the G104 manifest and labels; it is not a relabelling pass.
The remaining 80 rows include the original sole four-point frame:
`mlb__mlb_3Oc4S_1np98.mp4`, slot 14, source frame 25028.

## Recomputed reachability

Intervals are two-sided Wilson 95 percent intervals with
`z = 1.959963984540054`. The exact inputs and unrounded results are committed
in [`g125_recount/metrics.csv`](g125_recount/metrics.csv).

| Population | Reachable at >=4 points | Rate | Wilson 95 pct interval |
|---|---:|---:|---:|
| G104 published all-seeded denominator | 1 / 120 | 0.8 pct | [0.15, 4.57] pct |
| Same seed after the 40 G117-quarantined rows are excluded | 1 / 80 | 1.3 pct | [0.22, 6.75] pct |

The numerator does not move: all excluded rows have zero visible points, and
the surviving positive is the pre-existing MLB whole-infield frame. The
published 1/120 number was thus low in the known direction because two studio
clips supplied one third of its denominator. G104 documented those rows as
non-game programme content rather than hiding them; its mistake was keeping
them in a reachability denominator, not fabricating or concealing evidence.

The correction changes the number but not the conclusion: both one in 120 and
one in 80 are rare-event estimates with wide intervals, and neither supports
a corpus-wide baseball `court_feet` declaration. The 1/80 result is a
quarantine-corrected G104 rate, **not** the as-yet-unmeasured pure
game-footage rate: G104's other 20 commentary/reaction-programme rows remain
in this deliberately limited recount.

## Denominator rule

For a calibration/reachability question, non-game-programme frames should be
excluded from the primary denominator: the question is whether the camera
shows usable field geometry when a contest is on, and a studio desk has no
opportunity to do so. That rule must retain every excluded row in an auditable
side table and name the predicate before aggregation, so it cannot turn into
post-hoc removal of failed game footage. A separate all-decoded-frame rate
should also be reported for throughput and acquisition planning, because it
answers the different end-to-end question of what a delivered clip contains.
The 1/120 G104 value answers that latter whole-clip question; the 1/80 value
answers only the intermediate, named-quarantine correction. Neither should be
misquoted as the future live-game-only measurement.

## Other-sport exposure check

This check uses `non-game programme` in the contamination sense at issue here:
a frame from studio/statistics/commentary programming rather than coverage of
the sampled sport contest. It does not redefine isolated in-game close-ups,
replays, crowd views, or broadcast graphics, which G113 separately classifies
as non-live for its own live-action-share question.

| Census | Sampled frames | Non-game-programme frames | Exposure |
|---|---:|---:|---|
| Soccer G101 | 100 | 0 | No; [`G101`](g101_soccer_reachable_solve_2026-09-02.md) reuses the five G91 [contact sheets](g91_soccer_landmarks/renders/), which show soccer contest coverage across the fixed sample. |
| Football G106 | 60 football-only | 0 | No; [`G106`](g106_football_reachability_2026-09-02.md) retains only the 60 G95 [`football` rows](g95_football_survey/labels.csv). The 48 named soccer rows were already excluded from its football-only denominator, not silently retained. |
| Basketball G111 | 220 | 0 | No; [`G111`](g111_basketball_reachability_2026-09-02.md) retains eleven [contact sheets](g111_basketball_reach/contact_sheets/) showing basketball contest coverage across the fixed sample. |

The auditable counts and bases are in
[`g125_recount/cross_sport_exposure.csv`](g125_recount/cross_sport_exposure.csv).
They leave the G101, G106, and G111 verdicts unchanged. G113's separate,
three-interior-frame-per-clip live-action census reported 98/105 non-baseball
live-action frames, but it is not substituted for these different fixed
decision sets ([`g113_nongame_content_share_2026-09-02.md`](g113_nongame_content_share_2026-09-02.md)).

## NOT VERIFIED

- The 1/80 rate is not a new game-footage-only baseball measurement; the 20
  surviving G104 commentary/reaction rows remain outside this clip-quarantine
  correction.
- No new baseball sample was drawn, no G104 row was relabelled, and no
  landmark, line, or solver was implemented or scored.
- This recount does not estimate detector recovery, coordinate accuracy,
  temporal calibration, or the duration-weighted share of usable baseball
  footage.
- The other-sport check rules out this studio/non-game-programme contamination
  in their fixed censuses. It does not replace G113's broader live-action
  taxonomy or estimate each sport's all-broadcast non-live share.

## Verifier self-check

- **A2/A4:** rejoining G104's manifest and frame labels yields 120 rows, 120
  unique `(clip, slot)` pairs, and 120 unique `(clip, source_frame)` pairs.
  The named exclusion table has 40 rows (20 per G117 clip), all with zero
  visible points; the retained set has 80 rows and its sole `>=4` row is the
  named MLB slot above. The two Wilson rows reproduce
  `1/120` and `1/80`. **A3/B7:** no new head slice was drawn or reviewed;
  G104's fixed sample retains one seeded frame from each of 20 temporal strata
  per source clip. **A5:** this diff is documentation and additive CSV
  evidence only; no production field or reader changed. **A6:** this lane
  commits explicit evidence paths in its own worktree and does not land to
  master. **A7:** every evidence path named in this memo exists at report
  time, including the three G125 tables, G104 inputs, G117 memo, G101/G106/
  G111 evidence trees, G113 memo, and this verifier contract.
- **B1 circular metric:** clear. The excluded set is fixed solely by the two
  named prior G117 quarantines, before the G104 reachability aggregation; all
  excluded rows and their zero counts are retained in the committed table.
- **B2 non-additive schema:** clear. No schema, field, status, or reader was
  changed.
- **B3 fall-through loss / B4 re-claim loop:** clear. No gate, quarantine,
  queue, or claim behavior changed.
- **B5 pre-verification deploy:** clear. No pod file was copied, deployed, or
  modified.
- **B6 orphans:** clear. No module, test, import, or command moved or retired.
- **B8 self-fit as independent:** clear. This is a recount of eye labels, not
  a fitted residual or solver validation. **B9 degenerate denominator:**
  clear; every unit is a unique seeded frame. **B10 moved bar:** clear; no
  threshold, gate value, coordinate contract, sample seed, or existing
  verdict moved.
