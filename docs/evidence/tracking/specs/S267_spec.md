GAP S267 | sport all | worktree a18 | log cx_s267_key_explicit_consumers
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: successor to S257 (CLOSED AT LIMIT 644c24d46). S257_VERIFY B2 FAIL: resolver_registry.py:627-650 is an
  omitted base-path reader; test_calibration_report.py:192 and test_calibration_scoreboard_regex.py:50 fail on the
  changed base value. Verified: resolver_registry.py:627-650 globs '%s_reliability_2*.json', trusting the filename
  to mean positional; test_calibration_report.py:192 loops report[key]==landed[key] over 8 order-basis keys;
  test_calibration_scoreboard_regex.py:50 hardcodes improved_ece==0.024842541854003943. S50 (lines 84-88)
  positional after-ECE: nba 0.024843, mlb 0.008077, soccer 0.009302, tennis 0.008403; per-unit: nba 0.026583,
  mlb 0.012666, soccer 0.028722, tennis 0.015403.
PREMISE (step 0, INFORMATIONAL): confirm the three sites unchanged at those lines; build_report() in
  calibration_report.py emits order_basis + 9 keys (scored_rows/base_rate/ece_before/ece_after/verdict/
  sharpness_before/sharpness_after/murphy_after/reliability_bins_after), all order_basis-argument-dependent today.
CHANGE (step 1): additive only. build_report() gains report['positional'] and report['per_unit'], each the same 9
  keys via an internal call fixed to that basis regardless of the caller's order_basis/--per-unit flag; every
  existing top-level key stays untouched (byte-identical when order_basis is unset). resolver_registry.py:627-650
  reads v['positional']['ece_after'] from the serialized JSON (alias fallback to the top-level key on an older
  artifact) instead of trusting the filename glob. test_calibration_report.py:192 compares report['positional']
  [key] to landed[key] (landed values are today's positional numbers, unchanged). test_calibration_scoreboard_
  regex.py:50 keeps its assertion AND adds result['positional_ece'] from report['positional']['ece_after']. One
  CONSTRUCT test calls build_report twice/sport (order_basis unset vs 'event_date'), asserting report['positional']
  /['per_unit'] byte-identical both times -- proof a future default flip moves zero consumer readings.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = report['positional']/['per_unit']['ece_after'] vs the S50 numbers, 4 sports; flip-invariance
                  diff of report['positional']/['per_unit'] across both order_basis calls
  before        = 0 of 3 consumers reference an explicit key; S257 B2 FAIL (2 test failures) on the changed base
  bar           = all 3 consumers reference report['positional'] (direct or serialized field), zero remaining
                  implicit top-level dependency; positional/per-unit ece_after match S50 to <= 1e-9 per sport;
                  flip-invariance diff = 0.0 exactly; the two existing tests assert the same positional numbers
  n             = 4 sports x 2 sub-dicts = 8 (CONSTRUCT); flip-invariance 4 sports x 2 calls = 8 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns build_report at both order_basis values per sport
                  and diffs report['positional']/['per_unit'] plus the three consumer read-sites
  must not move = top-level keys/values when order_basis is unset; docs/evidence/calibration/*_reliability_2026-
                  09-03.json; the S50 numbers; the 1e-9 tolerance; cpcv_engine.py and walkforward.py untouched
NON-TAUTOLOGY: covers positional/per-unit reproduction + flip-invariance on all 4 sports; none excluded; a
  single-sport pass is circular and rejected.
EVIDENCE: docs/evidence/harness/S267_key_explicit_consumers_2026-09-04.md + one JSON/sport (18 scalars) + the
  flip-invariance diff table.
TEST: one new per-file test scripts/platformkit/eval_gate/test_s267_key_explicit_consumers.py, flip-invariance for
  one sport + the explicit-key read at the three named sites; run only that file.
REPORT: 4-sport reproduction table, flip-invariance diffs, 3-site key-explicit confirmation, SHA. No push. NEVER PARK.
