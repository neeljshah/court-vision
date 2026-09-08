VERDICT: PARTIAL -- court-coordinate premise FALSE (0/603 archived authentic `court_calibration.json` sidecars anywhere under `/workspace/nba-ai-system/data` on the pod, no writer exists in `src/` locally or deployed); the spec's declared image-space fallback is ALSO unreachable through the unchanged harness (`image_px` is corpus-only for every sport, `tracking_schema.py:151-160`); 30 real non-frozen 2s windows across 4 games (incl. both WNBA tables) all REJECT at `coordinate_contract` (30/30, Wilson 95% CI 0.8865-1.0000); every other tracked gate NOT_APPLICABLE on every real arm; the 5 planted defects + C0 are UNIDENTIFIABLE (arm construction needs a sidecar that does not exist).

# G348 gate execution (2026-09-08)

Contract: `VERIFIER_CONTRACT.md` A/B/Q. Spec: `specs/G348_spec.md`. Prereg `g348_prereg_2026-09-08.md`, seal `3ae5ea91047f87bb3f889bc2e7a2ba2dd0c333c99baa48dcbd7279e00627110b` (verified). Eye check: NONE. No `src/`, `data/`, registry, threshold, flag, daemon, or guard changed.

**Premise (pod-wide sidecar census).** Read-only `find` over `/workspace/nba-ai-system/data/tracking`: 603-607 `tracking_data.csv` tables (rotating corpus, `pod_file_listing.txt`), 0 `court_calibration.json`. Widened to every data root (`cache/domains/external/footage_bridge/footage_corpus/frontend/models/nba/tracking/videos`): 0 files matching `*calibration*` anywhere. Writer: NONE -- `grep -rl court_calibration` over the deployed pod `src/` and this worktree's `src/` both return 0 hits; `court_transform.py`'s cited producer doc does not exist on disk. A 20-file header sample is 100% NBA-production schema (`x_position/y_position`, no `cls`/`x`/`y`); where `coordinate_space` exists (602/607 headers) its value is `'image_px'`. Empirically confirmed against the unchanged harness: `evaluate()` REJECTs both an NBA-production row with no sidecar and a normalized row declaring `coordinate_space=image_px` for basketball, because `SPORT_COORDINATE_SPACES` accepts only `court_feet` per sport. G346's 7 frozen video sections do not overlap the games sampled below.

**Fixtures** (`fixtures.csv`, 30 rows, sha256-verified). 30 windows, 4 games (`0022400909`, `0022401198` NBA; `wnba_02`, `wnba_05` WNBA), stratified: 12+4 NBA windows (one per pre-segmented `_sNNNN` offset, first 2s each), 7+7 WNBA windows (evenly spaced across each full game). `sidecar_present=0` throughout. `g348_gate_execution.py`'s own pipeline needs a sidecar to build even arm A0 (converts to court feet before any arm), so it cannot run on this corpus; these 30 real windows instead run through the same imported `tracking_harness.evaluate()` + `g343_attack_test.gate_statuses()` (arm A0, unchanged, `source=None`), and `_record`/`aggregate_gates`/`detection_rows` are reused unmodified from `g348_gate_execution.py`.

**Per-gate table** (`gates.csv`, 108 data rows). A0 (n=30 real, unchanged): `coordinate_contract` REJECT 30/30=1.000000; 16 report fields NOT_APPLICABLE 30/30, reason COORDINATE_CONTRACT; `any_gate` REJECT 30/30. A1_FROZEN/A2_ID_MERGE/A3_SCALE_TRANSLATE/A4_MIRROR/A5_BALL_SHIFT/C0_CONTRACT_INVALID: all 15 tracked gates x 30 = UNIDENTIFIABLE, reason "arm construction requires an authentic court-coordinate sidecar; 0/607 pod census."

**Per-defect detection** (`detection.csv`). No planted defect applicable: all 5 (frozen trajectory, id merge, scale/translate, mirror, ball shift) UNIDENTIFIABLE (applicable_n=0) -- corruption cannot be constructed without a sidecar to transform into and out of court feet. Bar (>=0.80) not evaluable for any defect. C0_CONTRACT_INVALID likewise UNIDENTIFIABLE by the same gap; the synthetic pytest control already proves it REFUSES correctly (see Tests).

**Unchanged-arm (A0) false-rejection share:** 30/30 = 1.000000, Wilson 95% CI [0.8865, 1.0000]. Bar (<=0.05) NOT met.

UNIDENTIFIABLE (not detections): A1_FROZEN, A2_ID_MERGE, A3_SCALE_TRANSLATE, A4_MIRROR, A5_BALL_SHIFT, C0_CONTRACT_INVALID.

EYE CHECK: NONE.

**Tests.** `test_g348_gate_execution.py` 4 passed (seal check, synthetic-fixture full-gate PASS, C0 REFUSED-not-detected, denominator sum); `test_loc_rail_scope.py` 1 passed.

2026-09-08 lander: sidecar census restated 0/603 archived (listing 603-607, rotating corpus) and gates.csv accounting 108 data rows per the codex-sol verify memo; NEW GAPS in the ledger (non-A0 arms omit the three REPORT_ONLY rows; master-context test run needs this landing).

## NOT VERIFIED
- Whether any arm would clear the bar once a real sidecar exists; this row cannot construct one (0/607) and does not fabricate one.
- Whether the pod's 602/607 `coordinate_space='image_px'` stamping (no writer found in `src/`) came from a retrofit script rather than the live route; not traced further.
- G346's frozen-section list (57 sampled sections, 7 frozen) is itself a sample of a larger, rotating corpus; 2 pod files vanished mid-session between listing and read (rotation, not this row's fixtures).
- Harness screening only, not coordinate-quality certification; no sidecar's own validity is established anywhere on the corpus (G330).

Wall time: pod census + fetch + local measurement, this session, completed 2026-09-08T20:26:54Z (`date -u`).
SHA-256 (LF-normalised): `fixtures.csv` 9f2d74c8ccc4219e2ee8d9074ab847533ccbd3c18d3ff41346713e4b4e90e020; `gates.csv` 8e8dd77c0f3618c2d4d511712ed3419cf74d7eeada5ad4893a5e77e008bd8d82; `detection.csv` c49af41001556fcb9dc6f27bef62378e29ccaaaecb22921bd3af1d326a4a78de; `pod_file_listing.txt` 21e634d9279e7a0da632d7192546ea4b27dfcb9c5285e0cee157f4701a932d24.
Vocabulary follows contract Q6; automated scan required.
