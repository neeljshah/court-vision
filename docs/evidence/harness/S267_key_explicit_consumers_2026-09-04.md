# S267 attempt 1b: CLOSED AT LIMIT

Status: CLOSED AT LIMIT. No schema or consumer change is landed.

Machine: local worktree `C:/Users/neelj/nba-track-a18`; no pod operation occurred.

## Binding precondition

The pre-change reader census confirmed the three named implicit reads:

- `scripts/platformkit/answers/resolver_registry.py:650` read `v["ece_after"]`.
- `scripts/platformkit/eval_gate/test_calibration_report.py:192` compared `report[key]` to the landed artifact.
- `scripts/platformkit/answers/test_calibration_scoreboard_regex.py:50` asserted the resolver-derived value.

The exact sealed preregistration is `docs/evidence/harness/S267_prereg_2026-09-04.md`; its HEAD-byte prefix seal is `2334148630D369F34734A3567C137233F17FC197221A0B5080DDEAA820EF909A`.

## Limit result

The preregistration specified the NBA per-unit fixed target as `0.02658254607099417`. The sealed reproduction command printed:

```
RSS_BEFORE_BYTES=135172096
S267_NBA positional_default=0.0248425418540039432 positional_event=0.0248425418540039432 per_unit_default=0.0265834105558316186 per_unit_event=0.0265834105558316186 positional_equal=True per_unit_equal=True
RSS_AFTER_NBA_BYTES=163254272
```

The per-unit difference is `0.0000008644848374486`, above the specified `1e-9` tolerance. The canonical per-unit calibration inputs were also read one at a time: `nba_reliability_per_unit_2026-09-03.json` (7522 bytes) has `0.02658341055583162`; `mlb_reliability_per_unit_2026-09-03.json` (7419 bytes) has `0.012665595930047123`; `soccer_reliability_per_unit_2026-09-03.json` (8472 bytes) has `0.028722088828783483`; and `tennis_reliability_per_unit_2026-09-03.json` (7585 bytes) has `0.015402723519068535`.

Changing the sealed target after this metric would violate Q3. Therefore the four-sport scored comparison, new JSON evidence, and consumer edit are not valid for this attempt and were not retained. The temporary single-file construct did execute before the discrepancy was isolated and reported `2 passed in 1301.46s`; it is not offered as acceptance evidence.

RSS stayed below 600 MB throughout the observed scoring, including the highest observed 320700416 bytes. No evaluator, calibration source, existing artifact, register, ledger, data path, or pod state was changed.

SHA: 953e31ddd2d9a252840a3f6c07ee7218f26d2d0c

## NOT VERIFIED

- `scripts/platformkit/eval_gate/test_s267_key_explicit_consumers.py` is absent in the candidate and master.
- `scripts/platformkit/eval_gate/test_calibration_report.py` has one pre-existing baseline failure.
- `scripts/platformkit/answers/test_calibration_scoreboard_regex.py` has one pre-existing baseline failure.
