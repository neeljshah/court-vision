8. **S687: HOLD**

   - **Future or excluded labels choose the audit method:** `scripts/platformkit/eval_gate/conformal_coverage_audit.py:95` detects kind before cleaning or splitting. `scripts/platformkit/eval_gate/conformal_coverage_core.py:114` examines the entire outcome column. Adding an invalid-date row with `y=2` switches otherwise binary evidence to regression, although cleaning subsequently discards that row.
     **Fix:** determine kind from declared task metadata or cleaned calibration-side rows; freeze it for the test side. Add excluded-row and future-label method-invariance cases.
   - **Reference disagreement does not refuse a verdict:** `scripts/platformkit/eval_gate/conformal_coverage_audit.py:108` stores `reference_agrees`, but line 113 assigns a coverage verdict regardless. The required agreement is merely diagnostic.
     **Fix:** refuse unexpected reference disagreement before producing a verdict, preserving the explicitly allowed regression off-by-one case. Test a forced disagreement.
   - **Fixture generator bypasses the registry guard:** `scripts/platformkit/eval_gate/conformal_coverage_fixture.py:67` writes arbitrary destinations; only the audit CLI checks registry paths.
     **Fix:** apply the registry refusal to the fixture CLI before directory creation.

   `tests/platformkit/eval_gate/test_conformal_coverage_audit.py:90` tests future-label invariance only for a regression fixture, so it misses the method-switch defect.

| branch | verdict | must-land-after | top defect | fix size (S/M/L) |
|---|---|---|---|---|
| private/cloud/S687-2026-09-30 | HOLD | None | Outcome-dependent method and fail-open agreement | M |

**LANDING ORDER:** Land S679 now. After corrections and fresh per-file Windows verification, use S678, S682, S683, S684, S685, S686, S687. There is no mandatory runtime dependency between these eight branches; coordinate the shared oracle initializer.
