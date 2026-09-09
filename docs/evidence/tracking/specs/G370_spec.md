GAP G370 | sport all (basketball fixtures first) | worktree a18 | log cx_g370_admission_v0

**TEACHER-ADMISSION ROW (v0 schema + scorer), FROM G359 DONE (evaluated-ticks scoring M1 is the representation),
G366 PARTIAL (M1 is NOT sufficient: tick-ratio median 0.153; stationary rejects 12/59; v2 frozen detection 0/59)
and G368 (held-run attribution, in flight). Astra day review 2026-09-09 section 4. Codex PREPARES, a Claude finisher
MEASURES; the attribution input comes from G368 when it lands (until then the `position_source` field is filled
from the fields the tables carry and UNATTRIBUTED otherwise).** `src/`, `kernel/`, `api/`, `intel/` are READ and
IMPORT only. Build additively in `scripts/platformkit/tracking/g370_*.py` (import `g359_held_position`,
`g358_gate_execution`, `image_space_gates`, `production_schema_adapter`, `g361_source_identity`; copy none). NEVER
write `data/registry/`, never flip a flag, never move a sealed threshold (v2 76.995 is NOT adopted: it failed its
sealed detection test), never touch the register.

**WHERE THIS ROW RUNS:** in the assigned worktree (`python -m` from its root); tables from `data/tracking` (the pod)
or `data/pod_backup_2026-09-08/tracking` (PC, the 34 G358 sealed sections) READ ONLY; fresh stationary controls
and plants on the pod when it is up; no GPU; no detector training.

**PREMISE (step 0, BINDING before-condition):** on the 59 G366 fresh sections + the 34 G358 sealed sections, PRINT:
the two artifact gates' A0 rejection under M1 (expect 0), the stationary rejection (expect 12/59), the tick-ratio
median (expect 0.153), and the share of rows carrying an explicit position-provenance field (expect 0 unless G368
landed one). **If a landed producer field already stamps every row with DETECTION / PREDICTION / HELD, the premise
is FALSE for the provenance part: STOP that part, report, continue the schema part.**

METHOD (sealed before any number):
  1. **SCHEMA (`admission_rows.parquet`, one row per scheduled decoded frame, nullable targets):** provenance
     (source_id, source_uri, requested start/end, source_sha256, byte_size, frame_sha256, table_sha256,
     source_identity_status per G361, alignment_error_native_frames, deploy_manifest_sha256, route_sha256,
     weights_sha256); clock/image (game_id, competition, section_id, frame_index, pts, timebase, decoded_frame_count,
     evaluated_tick_id or null, evaluated_tick_verified, width, height, crop_xywh, pixel_transform_sha256, split,
     inclusion_probability); per-track observation array (track_id, track_generation, bbox_px, xy_px,
     position_source in {DETECTION, PREDICTION, HELD, UNKNOWN}, producer_branch_file_line, attribution_evidence_sha256,
     last_observed_pts, age_s; ball likewise + observed_box_px); calibration (court_presence_label / probability /
     model_sha256, geometry_status, orientation_status, symmetry_class, H_sha256, template_sha256, template_status,
     validation_support_sha256, residual_px, uncertainty_m); decision (gate_scores_m0, gate_scores_m1,
     gate_status_by_task in {PASS, FAIL, ABSENT, NOT_APPLICABLE}, task_mask, reason_codes, evidence_sha256s,
     admission_spec_sha256, admission_status in {ELIGIBLE, PARTIAL, UNVERIFIED}, scorable = false for image-only
     geometry). Missing evidence is ABSENT / UNKNOWN and disables ONLY the corresponding task (B3); it is never a
     bad-frame quarantine.
  2. **SCORER:** score verified evaluated ticks only (M1); keep M0 diagnostics beside; PREDICTION / HELD / UNKNOWN
     positions are never labelled observed; the two confirmed artifact gates + frozen / id-merge detection form
     the v0 gate set; stationary_track_share is DIAGNOSTIC only until controls pass.
  3. **CONTROLS (pod):** >= 30 fresh sections / >= 10 games of independently usable content (blind-rated by
     terra + sol as "usable court play" before any admission score is read) as usable controls; >= 30 planted
     corruptions per type (frozen, coast, id-merge) applied before adaptation; report usable-control rejection
     (bar <= 0.05 per enabled task) and plant detection (bar >= 0.80 where identifiable).
  4. **EXPORT DETERMINISM:** two exports on identical inputs are byte-identical (sha256s archived).
  5. CHANGE NOTHING ELSE; no src hook; no flag.

ACCEPTANCE RULE:
  metric        = 100 pct of sampled frames represented; 0 held / predicted / unattributed positions labelled
                  observed; 0 ABSENT-induced quarantines; usable-control rejection per task; plant detection per
                  type; export byte-identity; task masks verified independently
  before        = no admission record exists; G366's M1 result licenses only the two artifact corrections
  bar           = >= 30 usable-control sections / >= 10 games; rejection <= 0.05 per enabled task; detection >= 0.80
                  per identifiable plant type; two identical exports; an unmet bar DISABLES that task's mask (it is
                  never hidden as a software failure); 0 thresholds moved; 0 src edits
  n             = 59 + 34 diagnostic sections (CONSTRUCT) + >= 30 controls + >= 30 plants per type
  eye check     = REQUIRED: 30 evenly spaced strips incl. refused / unknown cases <= 200 KB
  must not move = every sealed threshold, v2, `src/`, `data/`, `data/registry/`, every flag, the daemon
  verdict       = **DONE** / **PARTIAL** (name the task whose mask stays disabled) / **PREMISE FALSE** (part)
EVIDENCE: `docs/evidence/tracking/g370_admission_v0_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall
time; SHA-256s) + `.../g370_admission_v0_2026-09-09/admission_rows.parquet` (or CSV if pyarrow is absent),
`controls.csv`, `plants.csv`, `decisions.csv`, `denominator_census.csv`, `export_hashes.json`, `strips/`,
`summary.json`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g370_admission_v0.py` alone (schema validation; a HELD position never becomes observed;
ABSENT evidence disables one task only; two exports byte-identical on a fixture; the seal check). **NEVER a full
pytest.** Every new file <= 300 lines (split modules as needed).
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: the schema, the v0 gate set, the control and plant
designs, the bars), the schema module, the scorer, the exporter, the test and the memo skeleton, exits `agent:
PREPARED FOR FINISHER` with `python -m` commands; the Claude finisher replays the 93 diagnostic sections, runs the
blind control ratings (terra + sol) and plants on the pod, and scores (Q1). Vocabulary follows contract Q6;
automated scan required. COMMIT: explicit pathspec only; prereg sealed as its OWN commit first (`SEAL sha256
<hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
