# S808 -- tennis served rows score nothing: attribute per sport, then resolve or record by cause (PAPER ONLY)

## Premise (register row S808; receipt docs/evidence/forward/scoreboard/2026-10-08.json, read-only)
- 19 served games (11 tennis, 6 nba, 2 mlb). 48 tennis cells are all no_eligible_ticks, arm A included.
- Aggregate counters: tick_refused:orientation_unresolved 1169, book_absent 300, invalid_decimal 826,
  settlement_refused 14685. The receipt has no per-sport attribution.

## Change (owned files only)
- NEW `scripts/platformkit/execution/s808_refusal_attribution.py`: a read-only probe. It calls the SEALED
  `ingame_scoreboard.run()` once per sport on the night's inputs, with history empty because tick refusals are
  decided before any model fit. It prints the per-sport refusal counters and their sum, and writes nothing.
- NEW `tests/platformkit/execution/test_s808_refusal_attribution.py`.
- No scorer, adapter or receipt file is edited. Every orientation input is seal-pinned (see V3), so the
  coverage-receipt record goes back as a PROPOSED diff in the result memo, not as an edit.

## Clauses
- V1 The probe on the 10-08 inputs (as-of 2026-10-09T06:00:00Z, PREREG_2026-09-24) gives per-sport counters.
  Their sum equals the receipt's aggregate for tick_refused:*, settlement_refused and served_games.
- V2 Per-sport table reported: which sport carries orientation_unresolved, invalid_decimal and book_absent.
- V3 Seal check: every file on the tennis orientation path is listed with the seal that pins it. If any file is
  pinned, no edit is made.
- V4 Cause of the tennis zero is named from fresh reads. Each of these gets a measured number:
  (a) the orientation comparison inputs, (b) the settlement inputs, (c) the state statuses.
- V5 Tennis is recorded as unscoreable by cause. Because the coverage receipt files are outside this lane's
  ownership, this is a PROPOSED diff. No new arm, no bar moved, no sealed file touched.
- V6 The probe test passes and kills a probe that drops the per-sport split or sums model counters. LOC <= 300.
- V7 No $/edge language; PAPER ONLY.
