GAP S275 | sport all | worktree a16 | log cx_s275_key_explicit_consumers_v2
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S267 successor (CLOSED AT LIMIT 270dcc83b): fixed 1e-9 bar missed 4/4 on per-unit ECE, each <= 1e-6:
  nba diff 8.644848374486e-7, mlb diff 5.8880346513337e-7, soccer diff 2.263514300494e-7, tennis diff
  4.5316524594721e-7 (full actual/target values in S267_VERIFY_2026-09-04.md). Positional matched exactly. Three
  implicit consumers still live: resolver_registry.py:650 reads v['ece_after']; test_calibration_report.py:192
  loops report[key]==landed[key]; test_calibration_scoreboard_regex.py:50 hardcodes improved_ece==
  0.024842541854003943 (S267_key_explicit_consumers_2026-09-04.md). build_report() at scripts/platformkit/
  eval_gate/calibration_report.py:94 still emits no 'positional'/'per_unit' keys -- unlanded.
PREMISE (step 0, INFORMATIONAL): re-run the S267 3-site census (confirm still implicit); confirm build_report emits
  no positional/per_unit keys; reprint the four per-unit diffs above from a fresh build_report call, both bases.
CHANGE (step 1): additive. (a) build_report() gains report['positional']/['per_unit'] (S267 design; top-level
  keys byte-identical when order_basis unset); one sealed run over 4 sports x 2 bases publishes those 8 values as
  a NEW dated reference JSON (never overwrites S50). (b) bar: each of 8 values matches S50 to <= 1e-6 AND a
  second, immediately-following fresh run matches the NEW reference to <= 1e-9. (c) resolver_registry.py reads
  v['per_unit']['ece_after'] (alias-fallback to v['ece_after'] on an older artifact); test_calibration_report.py
  adds a report['per_unit'][key] compare beside its existing positional compare; test_calibration_scoreboard_
  regex.py adds result['per_unit_ece'] beside its existing improved_ece assertion. (d) one CONSTRUCT test calls
  build_report twice/sport (order_basis unset vs 'event_date'), diffs report['positional']/['per_unit'] both
  times, and asserts all 3 consumer read-sites are identical on both calls -- proof a future no-flag default flip
  moves zero consumer readings; the flip itself is not made here. Seal a prereg FIRST as its own commit (LF; seal
  = SHA-256 of the STAGED bytes above the seal line via git show :<path>, verified with git show HEAD:<path>).
  Score only through build_report's existing walk_forward/cpcv_evaluate leak contract, untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = report['positional']/['per_unit']['ece_after'] vs S50 (8 values) and vs the NEW reference on a
                  second fresh run (8 values); 3 consumer read-sites; flip-invariance diff
  before        = S267: 0/4 per-unit within 1e-9 (diffs above); positional 4/4 exact; 0/3 consumers explicit
  bar           = all 8 values <= 1e-6 vs S50; all 8 values <= 1e-9 vs the NEW reference (second run); 3/3
                  consumers read the explicit key (alias retained); flip-invariance diff = 0.0 on all 4 sports
  n             = 4 sports x 2 bases = 8 (CONSTRUCT); flip-invariance 4 sports x 2 calls x 3 sites (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns build_report at both bases per sport twice, diffs
                  vs S50 and the NEW reference, greps the 3 consumer sites
  must not move = top-level keys/values when order_basis unset; the S50 numbers; docs/evidence/calibration/*_
                  reliability_2026-09-03.json; cpcv_engine.py/walkforward.py untouched
NON-TAUTOLOGY: covers all 4 sports x 2 bases, none excluded; a single-sport or single-basis pass is circular.
EVIDENCE: docs/evidence/harness/S275_key_explicit_consumers_v2_2026-09-04.md + NEW reference JSON (8 scalars) +
  second-run reproduction JSON + flip-invariance diff table.
TEST: one per-file test: exact 1e-9 match on a synthetic fixture; structural read-site check on the real 3 files.
REPORT: 8+8 value S50/NEW-reference tables, 3-site key confirmation, flip-invariance diffs, SHA. No push. NEVER PARK.
