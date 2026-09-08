VERDICT: PARTIAL -- five arms are 24/24, A2 is 17/17 applicable with 7 construction exclusions; coordinate_contract rejects every constructed cell (1.000000), A3 is NOT_APPLICABLE on every gate x window because the harness reads no ball table, and every downstream metric gate is NOT_APPLICABLE for 100% of remaining cells (screening: n = 24 sampled windows, below the contract's n >= 30 rail for a sampled metric; the sealed window rule cannot move in place).

# G343 evidence-pipeline attack test (2026-09-08, local basketball_ai)

Contract cited and self-checked: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections A, B, and Q as applicable.
MACHINE: local `basketball_ai`; interpreter `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe`.
No pod, video, GPU, network, registry, flag, or threshold change. Eye check: NONE.
Preregistration: `docs/evidence/tracking/g343_prereg_2026-09-08.md`; LF-normalised seal `8893df131bd1399954484d436081c695b429b319175e601588299e362d525527` (verified unchanged).

## Premise gate table (imported from the harness modules; unchanged from the prereg)

coordinate_contract tracking_schema.py:128,146,155,165,258 (image containment<0.95; unaccepted/absent space; missing calibration) | insufficient_data tracking_harness.py:65,257-263 (<30 frames) | duplicate_frame_identity :350-351 | coverage_attempted_frames / median_track_len :353-354 | oob / jump_max :355-356,363 | attempted_frames / ball_valid_attempted_frames :364-368 | liveness_frozen + 4 liveness sub-gates :370-372, liveness_metrics.py:33-36,63-82. jump_p95 / ball_detected_share / g325_wholly_off_frame are report-only fields, not reached by `evaluate()` -- recorded NOT_APPLICABLE per the prereg.

## Power table (24 sealed windows x 6 arms, imported harness gates only; see power.csv for every cell)

| arm | coordinate_contract | 13 metric gates | any_gate | A0 acceptance |
|---|---|---|---|---|
| A0 unchanged | REJECT 24/24 = 1.000000 | NOT_APPLICABLE, applicable_n=0, all 13 | REJECT 1.000000 | 0.000000 |
| A1 frozen | REJECT 24/24 = 1.000000 | NOT_APPLICABLE, applicable_n=0, all 13 | REJECT 1.000000 | -- |
| A2 same-team merge | REJECT 17/17 = 1.000000 (7/24 NOT_APPLICABLE: arm construction failed, <2 same-team ids) | NOT_APPLICABLE, applicable_n=0, all 13 | REJECT 1.000000 (of 17) | -- |
| A3 ball +30f | NOT_APPLICABLE 24/24: harness reads no ball table | NOT_APPLICABLE, applicable_n=0, all 13 | NOT_APPLICABLE, applicable_n=0 | -- |
| A4 scale/translate | REJECT 24/24 = 1.000000 | NOT_APPLICABLE, applicable_n=0, all 13 | REJECT 1.000000 | -- |
| A5 mirror | REJECT 24/24 = 1.000000 | NOT_APPLICABLE, applicable_n=0, all 13 | REJECT 1.000000 | -- |

Cause: all 356 eligible clips are the NBA-production schema (`x_position`/`y_position`); the sealed every-15th window rule selected 0 of 2 eligible WNBA tables, so all 24 selected windows are NBA (`windows.csv:2-25`). `normalize_tracking_frame` requires a `court_calibration.json` sidecar; zero exist anywhere under `data/tracking` (checked directly). `evaluate()` therefore fails closed at `coordinate_contract` on every constructed arm x window, identically to A0 -- a real, measured finding, not a construction defect.

## MISSING GATES

Per the acceptance rule (name a gate only where an arm's any-gate rejection share is < 0.50): A0/A1/A2/A4/A5 all measure 1.000000, none qualifies; A3 has no rejection share at all (applicable_n=0). The real gap is broader than the rule anticipated: coordinate_contract intercepts 100% of A0/A1/A2/A4/A5 cells, so the corruption-specific power of all 13 downstream metric gates against A1 frozen trajectories, A2 id merge, A4 scale/translate, and A5 mirror is completely UNMEASURED on this corpus, and A3's ball-shift power is unmeasurable by this harness at all (see Corrections). No gate below coordinate_contract has ever been exercised against a known corruption here.

## Fixes (scripts/platformkit/tracking/g343_attack_test.py; minimal; no sealed rule or gate touched)

1. Removed a hard `raise` on an empty windowed table: 6/24 windows have zero tracking rows inside frames 600-659 despite the source's max frame exceeding 659 (sparse sampling); `evaluate()` already fails such a table closed via coordinate_contract (verified on game 0022500036).
2. Wrapped `apply_arm` per arm in try/except `ValueError`: A2 needs 2 same-team identities inside the window and 7/24 windows lack them; recorded NOT_APPLICABLE with the construction reason instead of crashing the run.
3. (fix 1b) Added `cell_statuses()`: routes A3 away from `evaluate()` entirely and separates the arm-construction except-clause from a new evaluate()-exception except-clause (see Corrections).

## A0 byte-identity

`tests/platformkit/test_g343_attack_test.py::test_g343_arms_change_only_the_declared_columns` asserts A0 is frame-identical to the input via `pd.testing.assert_frame_equal`; PASS. Runtime `evaluate()` A0 acceptance share is 0.000000 -- caused by coordinate_contract, not by any construction difference.

## Corrections (fix 1b, 2026-09-08)

Verifier codex-sol REJECTed b10077d60 (`docs/evidence/tracking/G343_VERIFY_2026-09-08.md`); addressed here:
- ARM ROUTE (A3): `evaluate(df, sport, ...)` takes one dataframe; the NBA-production schema hardcodes `ball_telemetry_available=False` (tracking_schema.py:63) and `normalize_tracking_frame` never reads a separate ball file (tracking_schema.py:265-269) -- the harness is ball-blind for this corpus by construction. A3 is now NOT_APPLICABLE on every gate x window, reason `harness reads no ball table`, instead of being silently routed through unshifted tracking data.
- EXCEPTION SEPARATION: `cell_statuses()` catches the `apply_arm` ValueError only around construction; a separate `evaluate()` ValueError is recorded as NOT_APPLICABLE with reason `gate_error:<message>` (not a fourth status token, corrected in fix 1c from a `GATE_ERROR` status), so the sealed PASS/REJECT/NOT_APPLICABLE vocabulary is preserved and a future harness defect stays distinguishable from an arm-construction limit via the reason field (test: `test_evaluate_valueerror_is_not_applicable_gate_error_not_construction_failure`).
- LEDGER (B2/additivity): the PREPARED row at `RESULTS_LEDGER.md:591` (b10077d60^) is restored in place and this PARTIAL result is appended as a new terminal row. (Corrected in fix 1c: this claim was wrong -- see Corrections (fix 1c) below.)
- NEW GAPS (unresolved, for the next preregistration): the sealed ASCII every-15th rule selects 0/2 WNBA tables despite naming cross-league span -- stratify next time (g343_prereg_2026-09-08.md:15-23; windows.csv:2-25). The sampled per-arm denominator (n=24, or 17 for A2) is below the Q7 n>=30 rail; this is expressly a screening sample, not an exhaustive construct (VERIFIER_CONTRACT.md:45).
## Corrections (fix 1c, 2026-09-08)
Verifier codex-sol REJECTed 6b912045d (B2, Q7; `docs/evidence/tracking/G343_VERIFY_2026-09-08.md`): fix 1b's ledger edit wrongly deleted the b10077d60 G343 MEASURED row while claiming no row was rewritten or deleted (memo:46, now corrected); the row is restored byte-exact ahead of the PARTIAL row (`RESULTS_LEDGER.md:592`). The n=24 (n=17 for A2) result is flagged as a below-rail screening sample (memo:1). GATE_ERROR is retired as a status token -- `evaluate()` exceptions are now NOT_APPLICABLE with reason `gate_error:<message>` (memo:45; `g343_attack_test.py`). Windows are stated all-NBA (memo:25).
## NOT VERIFIED

- Whether the same coordinate_contract stop holds on a non-NBA-production basketball schema: all 356 eligible local clips are NBA-production; no normalized-schema basketball table exists locally to contrast.
- Corruption-specific power of oob, jump_max, liveness/frozen, coverage, and ball presence against A1, A2, A4, A5: unmeasured (see MISSING GATES); A3's power against any gate is not measurable by this harness at all, not merely unmeasured on this corpus.
- Court-shrink or mirror ambiguity as geometry: not expressible in image px without validated calibration (G334); 24 windows are a screening sample, not proof a real error would be caught or missed.
- A4/A5 width/height are derived per game from the table's own max `x_position`/`y_position` (no persisted frame width exists for this schema); confirmed not to change any gate outcome, since coordinate_contract stops before any width/height-dependent check runs.

Wall time: 8s (2026-09-08T18:37:44Z to 2026-09-08T18:37:52Z), sealed 24x6 run only.
Tests: `test_g343_attack_test.py` 3 passed; `test_loc_rail_scope.py` 1 passed.
Orchestrator adjudication (2026-09-08, Fable): the fix-1b verifier REJECTED on B2 (the MEASURED ledger row dropped by fix 1b, restored by fix 1c) and Q7 (n = 24 sampled windows, below the n >= 30 rail; the sealed window rule cannot move in place); the row is landed as CLOSED AT LIMIT with both REJECTs recorded; the finding stands: the coordinate contract intercepts every arm x window because no court_calibration.json sidecar exists locally, so no downstream metric gate has been exercised on real tables; a >= 30-window stratified rerun (including the 2 WNBA tables) is deferred until a validated calibration lands (G334).
SHA-256 (LF-normalised, refreshed fix 1c -- unchanged, no GATE_ERROR occurred so power.csv was not regenerated): `windows.csv` 419ae3d5092831420d7591c3c663800b392e08097442d430ca357fa293e43910; `power.csv` eceba5ea8cec30a913e58a0e2191fdc7a90429f7651c7d631a59f9eed372d473.
