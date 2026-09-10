# PROPOSED (UNAPPLIED): an additive `position_source` column on the player table

Status: PROPOSAL ONLY. Nothing under `src/` was edited by G368. This note is the
artifact the G368 spec section 5 / prereg section 9 requires when the median
`coast_row_share` over the barred corpus is >= 0.20. Applying it is a separate row
and needs the reader survey named at the bottom (A5, B2).

## Why the trigger fired

G368 measured, on the sections this pod holds, that a large share of player rows are
emitted with no detection behind them on that tick (`confidence < 1.0`), and that the
held-run classes `CLAMP_OR_SUBPIXEL`, `COAST_LOST` and `BBOX_FROZEN` cannot be told
apart from a genuinely stationary player by any field `tracking_data.csv` carries.
The numbers are in `docs/evidence/tracking/g368_evaluated_tick_motion_2026-09-09.md`.
`confidence` is a proxy: it recovers "no detection this tick" but it cannot separate
the two clamps (`advanced_tracker.py:636`, `unified_pipeline.py:2033`) from the
integer quantisation at `unified_pipeline.py:2042-2043`, nor either from a player who
did not move. A teacher-admission filter that has to guess this is guessing.

## The change

Stamp the provenance where the position is DECIDED, not inferred downstream. Three
values, ADDITIVE, appended at the END of the field list so no existing column moves
and no existing reader that selects by name is touched:

    DETECTION  -- a detection was matched on this tick and its position was written
    PREDICTION -- no detection this tick; the position came from the Kalman coast or
                  the optical-flow gap fill (P2/P3/P4)
    HELD       -- a position existed but was replaced by the previous one by a clamp
                  (P1 tracker jump clamp, or P5 pipeline 350 px clamp)

PROPOSED diff (NOT applied):

    --- a/src/pipeline/unified_pipeline.py
    +++ b/src/pipeline/unified_pipeline.py
    @@ around 2024
                     x2d, y2d = p.positions[frame_idx]
    +                _src_slot = self.players.index(p)
    +                _lost = self.feet_det._lost_ages.get(_src_slot, 0)
    +                position_source = "DETECTION" if _lost == 0 else "PREDICTION"
    +                if _lost == 0 and self.feet_det._freeze_age.get(_src_slot, 0) > 0:
    +                    position_source = "HELD"   # P1: advanced_tracker.py:636
    @@ around 2033
                         if (dx * dx + dy * dy) > 350 * 350:
                             x2d, y2d = last_pos[0], last_pos[1]
    +                        position_source = "HELD"   # P5
    @@ around 2044 (frame_tracks.append)
    +                    "position_source":  position_source,
    @@ around 2743 (tracking_rows.append)
    +                    "position_source":  track.get("position_source", ""),
    @@ around 4008 (_tracking_csv_fields, LAST entry)
    +            "position_source",   # G368

`_freeze_age` is already maintained at `advanced_tracker.py:637` and reset to 0 at
`:639`, so `> 0` reads as "the last `update_position` for this slot froze". No new
state is introduced and no existing value changes.

## What this proposal deliberately does NOT do

It does not separate P6 (`int(x2d)` at `unified_pipeline.py:2042-2043`) from a
stationary player: sub-unit motion is lost before the row exists, and recovering it
would mean changing the stored precision, which is a schema change to an existing
column and is out of scope here. `DETECTION` therefore still contains stationary
players and sub-unit movers, and the note says so rather than overclaiming.
It does not touch the ball table, which already carries `ball_inferred` (G320), and
it flips no flag, moves no threshold and writes nothing under `data/`.

## Before this may be applied (the separate row's checklist)

1. A5 reader survey: grep every reader of `_tracking_csv_fields()` and of the player
   CSV header (harness adapters, `production_schema_adapter.py`, the teacher emitter,
   every notebook and every gate) and confirm each selects by NAME, not by position
   or by column count. A count-based reader is a B2 break and must be aliased first.
2. A control that the three values are exhaustive: every emitted row carries one.
3. Re-run G368's census on a section tracked by the changed producer and confirm
   `position_source == "DETECTION"` is a strict subset of `confidence == 1.0`.

No monetary or wagering interpretation attaches to anything in this note.
