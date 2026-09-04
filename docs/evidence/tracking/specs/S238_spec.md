GAP S238 | sport nba | worktree a13XX | log cx_s238_conformal_band_s123_incumbent
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: simulation_methods_2026-09-04.md section on gap-table rows: "Conformal / honest uncertainty bands --
absent on every `predict_live` path; point Brier/ECE only ... new row (unallocated): split-conformal band around
the S123 incumbent, empirical coverage on held-out ticks, reported beside Brier" -- ranked 7th of 8 by expected
effect and explicitly notes "the conformal-band row carries no S-number" (this row claims it). S101 (LANDED,
`scripts/platformkit/eval_gate/s101_aci_coverage.py`) already builds grouped split-conformal coverage on the S86
series, but `ARMS = ("market", "model")` (line 54) -- it never scores the S123 incumbent
(`foundry/ingame_incumbent_nba.apply_incumbent`), and it reports coverage DEVIATION only, never interval WIDTH
(`grep -rln "interval_width\|band_width\|mean_width"` finds only s101/s97, neither prints width beside coverage).
PREMISE (step 0): reproduce S101's grouped-coverage method (COVERAGE_MIN_GROUP=400, COVERAGE_MAX_GROUPS=50) and
that its ARMS tuple excludes any S123-incumbent series; confirm no module on disk prints interval width beside
coverage for any in-game WP arm.
LIMIT (step 1): if the S123 incumbent series (`apply_incumbent(rows, kind, embargo_days)`) yields fewer than
COVERAGE_MIN_GROUP=400 ticks per fold's cell after the S101 grouping rule, report CLOSED AT LIMIT for that cell
and print the honest cell size, not a synthetic pooled substitute.
CHANGE (step 2): additive-only script `scripts/platformkit/eval_gate/s238_incumbent_conformal_band.py` (<=300
LOC) reusing S101's grouped split-conformal STATIC arm (leak-free, train-calibrated, held fixed on test) applied
to the `apply_incumbent("e4"|"ladder_base")` series instead of `market`/`model`; reports empirical coverage vs
nominal (90 pct, 80 pct) AND mean/median interval half-width per cell, walk-forward (S86's 5-fold game-first-date
blocks, purged, embargoed). No edit to s101_aci_coverage.py, ingame_incumbent_nba.py or aci_online.py (import-only).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = empirical coverage vs nominal (90 pct, 80 pct) AND mean interval half-width, per grouped cell,
                  STATIC arm, S123-incumbent series
  before        = no coverage or width has ever been reported for the S123 incumbent; S101 only covers
                  market/model
  bar           = coverage printed for every cell with >= COVERAGE_MIN_GROUP=400 ticks (a cell below that is
                  ABSENT_BECAUSE, per S101's own convention, not silently dropped); width printed beside every
                  reported coverage cell; the S101 market/model STATIC-arm coverage figures reproduce unchanged
                  to <= 1e-9 as a regression check that this row did not alter shared grouping code
  n             = 465,249 ticks / 1,593 games (S123/S86 denominator), cell counts printed
  eye check     = n/a (S-row); reproduction = verifier reruns the script and diffs every cell's coverage and width
  must not move = COVERAGE_MIN_GROUP, COVERAGE_MAX_GROUPS, the S86 fold/embargo design, every existing threshold
NON-TAUTOLOGY: a cell whose coverage misses its nominal level is printed as a miss, not excluded; width is
reported even where coverage is poor -- a narrow-but-miscalibrated band is the exact failure this row must show.
EVIDENCE: docs/evidence/harness/S238_conformal_band_s123_2026-09-04.md + per-cell coverage/width JSON. ASCII only.
Calibration language only (no dollar, ROI or edge words).
TEST: one new per-file test (grouped coverage+width on a fixture series, all cells present), run only that file.
REPORT: coverage table, width table, regression diff vs S101, test line, SHA. Commit by pathspec, no push.
NEVER PARK.
