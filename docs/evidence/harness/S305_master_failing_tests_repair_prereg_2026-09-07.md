# S305 preregistration: master failing tests repair

Status: SEALED BEFORE S305 premise reproduction and acceptance comparison.

## Scope

This preregistration binds `docs/evidence/tracking/specs/S305_spec.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q1-Q9, including
the B5 NOTE. The measured construct is exactly the two named test-file pass
counts plus the global-key `ece_after` equality. This is not an OOS predictive
comparison, does not create an evaluator state, and does not archive losses;
the shared evaluator's purge and embargo requirements therefore do not apply.

## Before-condition and allowed changes

Run `python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py
-q -p no:cacheprovider` once locally. Run `python -m pytest
scripts/platformkit/answers/test_calibration_scoreboard_regex.py -q -p
no:cacheprovider` once through `C:/Users/neelj/bin/pod_run a19 --`; first check
the pod for an existing `wt/a19` process and launch the pod job once only.

If both binding assertions still fail as specified, copy
`6226fb042^:calibration_report.py::_oof_per_regime` verbatim to the new alias
`_legacy_oof_per_regime`; dispatch to it only when `key_source == "global"`.
Keep every other key-source output byte-identical. In the named answers test,
load `Path(result["source_artifact"])` and compare `improved_ece` to that
artifact's `ece_after`. Add exactly
`tests/platformkit/eval_gate/test_s305_master_failing_tests_repair.py`.

## Acceptance and reporting

The locked bars are 10/10 and 4/4 passing, exact global `ece_after`
`0.039002202208806645`, and a byte-identical before/after capture for all
non-global key-source output. The evidence memo and JSON paths are
`docs/evidence/harness/S305_master_failing_tests_repair_2026-09-04.md` and
`.json`. The memo reports the input paths, test counts, output-diff result,
route-file SHA-256 values, and uses calibration language only. Its delta sign
convention is improvement = baseline loss minus candidate loss; positive means
candidate better. No loss comparison is produced for this construct.

Seal SHA-256 of every LF byte above this line: 2DD1F3E6C53A283A6E5CD3CE7DE8E0DD3A48BC1017F7D9E2BD42EC793E8E0C83
