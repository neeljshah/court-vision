GAP S257 | sport all | worktree a17 | log cx_s257_event_date_default_v2
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S235 CLOSED AT LIMIT (353d276aa). Attempt 1 wrongly declared the premise falsified; attempt 2 confirmed
  the premise (no-flag calibration_report.py main still walks POSITIONAL order, lines 259-268) and resealed the
  prereg correctly, but was rejected on three exact points the verifier diffed: (a) the no-flag path wrote a new
  _reliability_per_unit_ JSON key instead of the unchanged default key; (b) that redirect moved output away from
  the base path both readers consume (B2, not additive); (c) scoring called the local oof_per_regime, not the
  shared evaluator with purge + symmetric embargo (Q4). This row applies that diff and nothing else.
PREMISE (step 0, INFORMATIONAL): re-run calibration_report.py main with no flags and print which walk it uses;
  reproduce S50's four positional/per-unit after-ECE pairs from the archived JSONs at max abs diff <= 1e-9
  (nba 0.024843/0.026583, mlb 0.008077/0.012666, soccer 0.009302/0.028722, tennis 0.008403/0.015403).
CHANGE (step 1, the verifier's CORRECTION DIFF verbatim): parse args ONCE; no-flag and --per-unit WRITE THE
  BASE KEY (every existing *_reliability_*.json name byte-identical; only the default-run numbers move);
  --positional uses a NEW positional suffix; route BOTH arms through a Q4-compliant evaluator (walk_forward /
  cpcv_evaluate with purge plus symmetric nonzero embargo, the callback producing every scored quantity) before
  regeneration. Seal a prereg FIRST (own commit; seal = SHA-256 of the committed bytes above the seal line, LF,
  verified via git show HEAD). No caller edits; name every caller found. Never write docs/research/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = default-run after-ECE per sport (no flags) written under the UNCHANGED base key
  before        = positional default: nba 0.024843, mlb 0.008077, soccer 0.009302, tennis 0.008403
  bar           = no-flag reproduces S50's per-unit numbers at max abs diff <= 1e-9 under the base key;
                  --positional reproduces the old numbers exactly under the new positional suffix; 0 rows dropped
                  (1,814 / 39,162 / 25,834 / 41,886); both arms scored through the Q4 evaluator (assert printed)
  n             = 4 sports (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns main with no flags and with --positional and diffs
  must not move = the S05 calibration bar; the S34 SYNTHETIC vintage label; data/registry/**; every reader path
NON-TAUTOLOGY: soccer's worse per-unit ECE and the WTA-dominated tennis cost are reported as the honest default;
  the soccer 6-division interleave is named.
EVIDENCE: docs/evidence/harness/S257_event_date_default_v2_2026-09-04.md + regenerated JSONs (new files only where
  a schema changes; base keys unchanged). ASCII only; calibration language only.
TEST: one new per-file test (default vs --positional on all 4 sports, base key unchanged), run only that file.
REPORT: four before/after pairs, caller list, evaluator assertion, seal hashes, test line, SHA. No push. NEVER PARK.
