# PROPOSED (NOT APPLIED) -- drop player observations whose box lies wholly outside the frame

Written because G325's sealed rule fired: SITE PINNED at `100` pct. ATTEMPT 2 numbers
(`docs/evidence/tracking/g325_offframe_boxes_attempt2_2026-09-07.md`, prereg seal
`57d7748a2cf7c84e...`); attempt 1's smaller corpus gave the same verdict.
**Nothing under `src/` was edited.** This is a snippet for a human to apply, or not.

PATH DEVIATION, DECLARED: the G325 spec names `docs/research/organization-sprint/` for this file, but
that whole tree is gitignored (`.gitignore:489`, the public-repo doc quarantine), so a diff written
there could be neither landed nor verified. The two PROPOSED artifacts already on master live at
`docs/evidence/tracking/PROPOSED_*.md` and this one follows them. Named here, not quietly dropped.

## What it fixes
`23408/480158` player observations (~4.8751e-02) across 122 pod games carry a bounding box that lies
WHOLLY outside the decoded frame. Every one of them is a Kalman coasting prediction
(`src/tracking/advanced_tracker.py:132-137`, unclamped, `w`/`h` held constant, up to `MAX_LOST = 90`
frames), so the box has no pixels: its team label, its crop features and its footpoint
(`src/tracking/advanced_tracker.py:1411`, `foot_y = y2c`) are derived from nothing.

## Where the guard goes, and why there
`scripts/platformkit/track_daemon_done.py` is NOT the writer -- it fsyncs and adjudicates only. Every
row that reaches `tracking_data.csv` passes through ONE place, the row build at
`src/pipeline/unified_pipeline.py:2690-2692`, before both `_checkpoint_csv` (`:3929`) and
`_export_csv` (`:4020`). One guard there covers both writers; a guard in either writer would have to
be duplicated and would still let the row through the in-memory consumers.

## The diff, against master `946d73a79`
```python
# src/pipeline/unified_pipeline.py, at :2690 (immediately before tracking_rows.append)
                bbox = track["bbox"]  # stored as (y1, x1, y2, x2)
+               # G325: a coasting Kalman box can translate off-frame unclamped
+               # (advanced_tracker.py:132-137). Such a box has no pixels, so its
+               # footpoint and team label are derived from nothing. TOPCUT=60 is
+               # already removed from the frame these coordinates live in.
+               if bbox is not None:
+                   _fw, _fh = float(map_w_src), float(src_h - TOPCUT)
+                   if (bbox[3] <= 0 or bbox[1] >= _fw
+                           or bbox[2] <= 0 or bbox[0] >= _fh):
+                       continue
                tracking_rows.append({
```
`src_h` is the source height already carried into the row as `"source_height"`; `map_w_src` is the
SOURCE frame width, which this scope does not currently hold -- **the applier must thread the decoded
frame width in**, and that is the only non-mechanical part of this change. Until it is threaded, a
vertical-only guard (`bbox[2] <= 0 or bbox[0] >= _fh`) catches `9651` of the `23408` rows (the census
CSV's `n_side_top + n_side_bottom`, which no row satisfies twice) and needs nothing new.

## What it costs, stated before anyone applies it
- Row counts fall by ~`4.8751e-02` per game, so **every denominator computed from
  `tracking_data.csv` row counts moves**, including the harness coverage figures and the ledger's
  `rows`. `docs/evidence/tracking/g325_offframe_boxes_census_2026-09-07.csv` carries the exact
  per-game count to subtract.
- The alternative, blanking the four `bbox_*` cells and keeping the row (the `""`-on-missing
  convention already used at `:2711`), preserves every denominator but leaves `x_position` /
  `y_position` -- which are derived from the same box -- untouched and equally meaningless. That is
  why the skip is proposed instead.
- **Not measured, and not claimed:** whether dropping these rows improves any downstream number.
  G325 measured where they come from, not what they cost. Apply this only behind a re-run of the
  harness denominators.
