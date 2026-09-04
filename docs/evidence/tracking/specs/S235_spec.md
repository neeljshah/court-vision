GAP S235 | sport all | worktree a18 | log cx_s235_event_date_walk_default
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S50 (LANDED, opt-in via `--per-unit`, `calibration_report.py:340-342`) switches the gate-corpus walk from
row order to a true per-`corpus_unit` `event_date` chronology; it is NOT the default and no caller has switched
(docs/evidence/harness/S50_per_unit_chronology_2026-09-03.md: "No caller was switched... `batch_gate.py:193` and
every other consumer... still walk row order"). S50's own measured four-sport table (line 85-88, ECE after,
positional -> per-unit): nba 0.024843 -> 0.026583 (+0.001741); mlb 0.008077 -> 0.012666 (+0.004589); soccer
0.009302 -> 0.028722 (+0.019420, and soccer's per-unit partition test itself returned FALSE -- 6 divisions
interleave under `corpus_unit` grouping); tennis 0.008403 -> 0.015403 (+0.007000, WTA alone 0.023195 -- "the cost
falls almost entirely on WTA, the unit that was being handed a decade of future ATP history").
PREMISE (step 0): reproduce all four positional/per-unit ECE pairs above from the archived S50 JSONs at max abs
diff <= 1e-9; reconfirm `batch_gate.py:193` and every other caller of `calibration_report.build_report`/`main`
still omits `--per-unit` (grep every call site); reconfirm soccer's partition-identity check is False (6-division
interleave) so soccer's per-unit table needs the interleave named, not silently flipped.
LIMIT (step 1): if flipping the default moves ANY of the four sport-level thresholds this program treats as
frozen (S05's calibration bar, S22's mechanism gate), report CLOSED AT LIMIT and name which threshold and by how
much; a worse-calibrated default is still reportable as the honest per-unit number.
CHANGE (step 2): additive-only -- flip `main`'s DEFAULT in `calibration_report.py` so `per_unit=True` unless
`--positional` is newly passed (the old flag, `--per-unit`, stays a no-op alias so no caller string breaks); every
existing `*_reliability_*.json` output key stays byte-identical in name, only the DEFAULT-run numeric values move;
re-publish the four after-ECEs under the corrected default in one memo. No edit to batch_gate.py or any other
caller this row -- name every caller found in the premise and propose their one-line `--per-unit` add as a
PROPOSED snippet under docs/research/organization-sprint/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = default-run after-ECE per sport (no flags passed)
  before        = positional-order default: nba 0.024843, mlb 0.008077, soccer 0.009302, tennis 0.008403
  bar           = the new default reproduces the S50 per-unit numbers above at max abs diff <= 1e-9: nba
                  0.026583, mlb 0.012666, soccer 0.028722, tennis 0.015403; 0 rows dropped (1,814 / 39,162 /
                  25,834 / 41,886); `--positional` reproduces the OLD default numbers exactly, unchanged
  n             = 4 sports (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns `main` with no flags and diffs against S50's archive
  must not move = the S05 calibration bar; the S34 SYNTHETIC vintage label; data/registry/**
NON-TAUTOLOGY: soccer's worsened ECE and the WTA-dominated tennis cost are BOTH reported as the honest default,
not omitted for being unfavorable; the interleave defect is named, not hidden inside a passing partition check.
EVIDENCE: docs/evidence/harness/S235_event_date_walk_default_2026-09-04.md + regenerated JSONs. ASCII only.
Calibration language only (no dollar, ROI or edge words); a worse default ECE is a valid, publishable result.
TEST: one new per-file test (default vs `--positional` on all 4 sports), run only that file.
REPORT: the four before/after pairs, caller list found, test line, SHA. Commit by pathspec, no push. NEVER PARK.
