Reviewed all 48 SPEC blocks and selected 14 new-file components with 41 distinct owned paths. The selected paths do not overlap the inspected `cxp/cxf` changes or the inspected seal-pin declarations. Four selected specifications need the corrections provided below. Sources: `W1` through `W8`; `D/DESK_STATE.md:64-71`; `F/**/PREREG*.json`; `H/S515_live_shadow_quoter_2026-09-29.md:11-19`.

This was a read-only audit. No files were changed, no tests were run, and no network access occurred.

Citation and path conventions:

- All relative paths start at `C:/Users/neelj/nba-ai-system/`.
- `O/` = `.planning/codex_push_2026-10-02/out/`; `W1` through `W10` mean `O/px_w1.md` through `O/px_w10.md`.
- `P/` = `scripts/platformkit/`; `T/` = `tests/platformkit/`.
- `H/` = `docs/evidence/harness/`; `F/` = `docs/evidence/forward/`.
- `E/` = `docs/evidence/`; `K/` = `docs/evidence/paper_desk/`.
- `D/` = `docs/operations/`; `Q/` = `docs/research/organization-sprint/`.
- `R` = `docs/evidence/HARNESS_GAPS_2026-09-03.md`.
- Braces enumerate exact filenames, not wildcards.
- `YES` assesses the written component contract. It does not establish acceptance, remaining attempt allowance, integration, or adoption. Those remain separate requirements. Source: `W9:29`.

## 1. SPEC QUALITY TABLE

### W1: capture and recorder components

| ID | Lane | Buildable as written | Existing branch/register relationship | Owned files |
|---|---|---|---|---|
| S720 | w1/a2 | YES; candidate repair. Attempt allowance UNKNOWN. | Continues `cxp/S720-2026-10-02`, R:S720; absorbs NEW-a2-1. | `P/execution/{capture_book_provenance,book_provenance_replay,book_provenance_publish}.py`; `T/execution/test_s720_repair_controls.py`; `H/S720_wave2_repair.md`; `Q/PROPOSED_S720_wave2_integration.md`. Companion publication module is optional but must be reserved. Source: `W1:75`. |
| S597 | w1/a2 | YES for census code; redispatch held on attempt disposition. | `cxp/S597-2026-10-02` contains evidence/specification, while implementation remains absent; R:S597. Two retained REJECT reports exist. | `P/ingame/trade_tape_latency.py`; `T/ingame/test_trade_tape_latency.py`; `H/S597_census_build.md`. Sources: `W1:112`; `O/px_v_S597.md`; `O/px_v2_S597.md`. |
| S695 | w1/a2 | NEEDS FIX: name a usable continuation base and exact dependency/extraction set. | R:S695; candidate identified in W1, but no dedicated matching `cxp/cxf` branch. Related files occur in the integration branch. | `P/ops/{clock_guard,clock_guard_cli}.py`; `T/ops/test_clock_guard_boundaries.py`; `H/S695_wave2_repair.md`; `Q/PROPOSED_S695_consumer_hook.md`. Source: `W1:147`. |
| S659 | w1/a2 | YES; narrow candidate repair. Attempt allowance UNKNOWN. | Continues `cxf/S659-2026-10-02`, R:S659; S690 inherits its files. | `P/ops/recorder_adopt.py`; `T/ops/test_recorder_adopt_null_progress.py`; `H/S659_wave2_repair.md`. Sources: `W1:183`; `W10:76`. |
| NEW-a2-2 | w1/a2 | YES; offline capacity analyzer. | Master-plan NEW11; complements S523/S600 without owning their producers. No exact owned-path overlap found in inspected cx branches. | `P/ops/capture_capacity_census.py`; `T/ops/test_capture_capacity_census.py`; `D/RECORDER_CAPACITY_MODEL.md`. Sources: `W1:227`; `W9:223`. |
| S681 | w1/a2 | YES; offline transaction component only. | Existing R:S681; consumes S678 interfaces without duplicating its manifest implementation. | `P/ops/{closed_day_mirror,closed_day_restore_check}.py`; `T/ops/test_closed_day_mirror.py`; `H/S681_offline_restore.md`. Source: `W1:273`. |

### W2: night completion and recovery

| ID | Lane | Buildable as written | Existing branch/register relationship | Owned files |
|---|---|---|---|---|
| S714 | w2/a3 | NEEDS FIX: declare master-only component scope, preserve original attempt lineage, and resolve remaining allowance. | Existing `cxp/S714-2026-10-02`, R:S714. Proposed new component files do not duplicate its existing shared-runner changes. | `P/execution/night_step_contract.py`; `T/execution/test_night_step_contract.py`; `Q/W2_S714_PROPOSED.md`; `H/W2_S714_contract_result.md`. Sources: `W2:85`; `O/px_v_S714.md`. |
| S711 | w2/a3 | YES; bounded seed-copy repair. Runtime acceptance and attempt allowance UNKNOWN. | Continues `cxp/S711-2026-10-02`, R:S711. | `P/ops/qualification_runtime_probe.py`; `T/ops/test_qualification_runtime_publication.py`; `H/W2_S711_measurement.md`; optional `Q/W2_S711_PROPOSED.md`. Source: `W2:136`. |
| NEW-a3-1 | w2/a3 | NEEDS FIX: explicit master base, read-only S712 dependency, and separate component-case coverage from master-plan boundary coverage. | Master-plan NEW05; consumes S712 output inventory, but must not create another queue. | `P/execution/night_bundle.py`; `T/execution/test_night_bundle.py`; `Q/W2_NIGHT_BUNDLE_PROPOSED.md`; `H/W2_NIGHT_BUNDLE_result.md`. Sources: `W2:184`; `W9:217`. |
| S713 | w2/a3 | YES; dependent closure integration remains held. Attempt allowance UNKNOWN. | Continues `cxp/S713-2026-10-02`, R:S713; absorbs NEW-a3-5 inventory authority. | `P/ops/{unresolved_nights,night_obligation_store,night_state_import}.py`; `T/ops/test_unresolved_nights.py`; `Q/W2_S713_PROPOSED.md`; `H/W2_S713_conservation.md`. Source: `W2:236`. |
| S716 | w2/a3 | NEEDS FIX: explicit master-only component scope and preserved attempt lineage. | Existing `cxp/S716-2026-10-02`, R:S716. Shared planner integration also intersects S534. | `P/execution/night_shard_coverage.py`; `T/execution/test_night_shard_coverage.py`; `Q/W2_S716_PROPOSED.md`; `H/W2_S716_coverage.md`. Sources: `W2:288`; `W10:73`. |
| S718 | w2/a3 | YES; bounded parser correction. Attempt allowance UNKNOWN. | Continues `cxp/S718-2026-10-02`, R:S718. | `P/ops/registry_e_health_reader.py`; `T/ops/test_registry_e_health_reader.py`; `Q/W2_S718_PROPOSED.md`; `H/W2_S718_reader_result.md`. Source: `W2:340`. |

### W3: execution-quality evidence

| ID | Lane | Buildable as written | Existing branch/register relationship | Owned files |
|---|---|---|---|---|
| S671 | w3/a4 | YES; two bounded source corrections. Attempt allowance UNKNOWN. | Continues `cxf/S671-2026-10-02`, R:S671; broader protocol disposition remains separate. | `P/execution/{fill_model_incidents,fill_model_latency}.py`; `H/S671_closed_exposure_2026-10-02.md`. Existing regression test is read/run-only. Source: `W3:86`. |
| NEW-a4-1 | w3/a4 | NEEDS FIX: define "valid partial" as a partial fill with complete evidence, preserving exactly three COMPLETE controls. | Master-plan NEW24; complements S550/S551/S670 without replacing their implementations. | `P/execution/execution_record_audit.py`; `T/execution/test_execution_record_audit.py`; `F/execution_v2/record_audit.json`. Sources: `W3:142`; `W9:114`. |
| S724 | w3/a4 | YES; qualified-population evidence repair. Attempt allowance UNKNOWN. | Continues `cxp/S724-2026-10-02`, R:S724. | `P/execution/{queue_sensitivity,queue_sensitivity_evidence}.py`; `T/execution/test_queue_sensitivity_evidence.py`; `F/execution_v2/queue_sensitivity_evidence.json`. Source: `W3:204`. |
| NEW-a4-4 | w3/a4 | YES; arithmetic and applicability remain separate. | Complements S378 certification; existing fee calculators remain read-only. | `P/execution/execution_fee_evidence.py`; `T/execution/test_execution_fee_evidence.py`; `F/execution_v2/fee_manifest.json`. Source: `W3:266`. |
| NEW-a4-5 | w3/a4 | YES; explicit units, lineage, and missingness. | Complements S550/S551; preserves S670 ownership. | `P/execution/execution_markout_evidence.py`; `T/execution/test_execution_markout_evidence.py`; `F/execution_v2/markouts.jsonl`. Source: `W3:322`. |
| S693 | w3/a4 | NEEDS FIX / HOLD: fixture publication cannot establish corrected-model evidence while two newer allocation findings remain unresolved. | Continues `cxf/S693-2026-10-02`, R:S693; S703 inherits fixture code. | `P/execution/core/fixture_night.py`; `T/execution/test_s693_fixture_artifact.py`; `E/S693_fixture_grid_2026-09-30.canonical.json`; `E/S693_fixture_grid_2026-10-02.json`; `H/S693_fixture_publication_2026-10-02.md`. Sources: `W3:383`; `O/px_v2_S693.md:16-31`. |

### W4: calibration preparation

| ID | Lane | Buildable as written | Existing branch/register relationship | Owned files |
|---|---|---|---|---|
| NEW-a5-1 | w4/a5 | YES; retrospective and decision-visible classifications remain separate. | Complements S721/S723; does not own their readers or package initializer. | `P/ingame/paper_calibration_additive/eligibility_witness.py`; `T/ingame/test_eligibility_witness.py`; `H/NEW-a5-1_spec.md`. Source: `W4:96`. |
| NEW-a5-2 | w4/a5 | YES for normalization; empirical replay remains separate. | Extends `cxp/S722-2026-10-02` through a new adapter rather than replacing its replay. | `P/ingame/paper_calibration_additive/stale_snapshot_normalizer.py`; `T/ingame/test_stale_snapshot_normalizer.py`; `H/NEW-a5-2_spec.md`. Source: `W4:140`. |
| NEW-a5-3 | w4/a5 | NEEDS FIX: freeze NEW-a5-1's witness schema or sequence behind it. | Complements S424/S723; does not replace `cxp/S723-2026-10-02`. | `P/ingame/paper_calibration_additive/regime_episode_reader.py`; `T/ingame/test_regime_episode_reader.py`; `H/NEW-a5-3_spec.md`. Source: `W4:185`. |
| S701 | w4/a5 | NEEDS FIX: reconcile already-prepared correction with branch/worktree identity; preserve unchanged-bar disposition. | Existing `cxf/S701-2026-10-02`, R:S701. Today's fix report already describes the timestamp/test correction. | `P/eval_gate/family_decay_monitor.py`; `T/eval_gate/test_s701_unchanged_bar.py`; `H/S701_unchanged_bar_disposition.md`; conditional `Q/S701_compatibility_PROPOSED.diff`. Sources: `W4:228`; `O/px_f_S701.md:1-16`. |
| S546 | w4/a5 | YES; PREPARE only, with authenticated fixture preparation. | Existing R:S546 and `docs/evidence/tracking/specs/S546_spec.md`; no replacement row. | `P/ingame/{nfl_wp,nfl_wp_census}.py`; `T/ingame/{test_s546_nfl_wp,test_s546_census}.py`; `T/ingame/fixtures/s546/nfl_2026-09-29_l3008_l3216_l7040.jsonl`; `H/S546_prepare_review.md`; `Q/S546_fixture_eol_PROPOSED.diff`. Source: `W4:270`. |
| S547 | w4/a5 | YES; PREPARE only, retaining amended parser/projection requirements. | Existing R:S547 and `docs/evidence/tracking/specs/S547_spec.md`. | `P/ingame/soccer_projection.py`; `T/ingame/test_soccer_projection.py`; `T/ingame/fixtures/{s547_mexeng_rows33_35,s547_capture_final_l1}.jsonl`; `H/S547_prepare_review.md`; `Q/S547_fixture_eol_PROPOSED.diff`. Source: `W4:316`. |

### W5: NBA readiness

| ID | Lane | Buildable as written | Existing branch/register relationship | Owned files |
|---|---|---|---|---|
| NEW-a6-1 | w5/a6 | YES; observed supply and hypothetical capacity remain distinct. | Supports S557 capacity evidence without enforcing its admission policy. | `P/ops/season_calendar_capacity.py`; `T/ops/test_season_calendar_capacity.py`; `H/A6_calendar_capacity_2026-10-02.md`. Source: `W5:83`. |
| NEW-a6-2 | w5/a6 | YES; audit instrument with explicit real-game linkage floor. | Complements S596/S564; does not own source selection or producer changes. | `P/ingame/nba_opening_readiness.py`; `T/ingame/test_nba_opening_readiness.py`; `H/NBA_OPENING_READINESS_2026-10-02.md`. Source: `W5:130`. |
| NEW-a6-3 | w5/a6 | YES; census plus proposal. | Absorbs NEW-a6-5; complements NEW-a5-1 and existing S518/S625 work. | `P/ingame/nba_readiness_terminal_census.py`; `T/ingame/test_nba_readiness_terminal_census.py`; `H/NBA_TERMINAL_READINESS_2026-10-02.md`; `Q/PROPOSED_NBA_LIVE_ELIGIBILITY_2026-10-02.md`. Source: `W5:170`. |
| NEW-a6-4 | w5/a6 | YES; document-only proposed integration. | Proposal portion of S557; S558/S714 and seal-chain integration remain separate. | `Q/PROPOSED_NBA_S551_ADMISSION_2026-10-02.md` only. Source: `W5:208`. |
| S596/S564 | w5/a6 | NEEDS FIX: specify approved resolver/registry routing for the crosswalk; do not make direct pairing an implicit canonical join. | Existing R:S596 and R:S564; a2 retains capture integration. | `P/ingame/nba_state_primary.py`; colocated `P/ingame/test_nba_state_primary.py`; `Q/PROPOSED_S596_NBA_SOURCE_HANDOFF_2026-10-02.md`. Sources: `W5:250`; `W10:68`; `.agents/skills/lane-spawn-rails/SKILL.md`. |
| S532 | w5/a6 | YES for descriptive report and proposed display correction. | Existing R:S532; does not complete S503 scored-reader integration. | `P/ingame/nba_season_cohort_report.py`; `T/ingame/test_nba_season_cohort_report.py`; `Q/PROPOSED_S532_NBA_2026-10-02.md`. Source: `W5:290`. |

### W6: operational safeguards

| ID | Lane | Buildable as written | Existing branch/register relationship | Owned files |
|---|---|---|---|---|
| S676 | w6/a7 | YES; candidate correction. Attempt allowance UNKNOWN. | Continues `cxf/S676-2026-10-02`, R:S676. | `P/ops/{deadman_check,slo_status}.py`; `T/ops/test_s676_schema_legacy_boundaries.py`; `H/S676_checker_boundaries_2026-10-02.md`. Source: `W6:78`. |
| S669 | w6/a7 | YES; transaction correction. Attempt allowance UNKNOWN. | Continues `cxf/S669-2026-10-02`, R:S669. | `P/execution/{risk_receipt_io,risk_receipt_transaction,risk_receipt}.py`; `T/execution/test_risk_receipt_transactions.py`; `H/S669_transactions_2026-10-02.md`. Source: `W6:130`. |
| S667 | w6/a7 | YES; differential tests and archive auditor. Extension/attempt disposition UNKNOWN. | Existing `cxf/S667-2026-10-02`, R:S667; retained report says ACCEPT WITH CORRECTIONS. | `T/execution/test_risk_limits_family.py`; `P/execution/risk_limits_archive_audit.py`; `T/execution/test_risk_limits_archive_audit.py`; `H/S667_archive_audit_2026-10-02.md`. Sources: `W6:173`; `O/px_v_S667.md:1`. |
| S698 | w6/a7 | NEEDS FIX: freeze observation-membership input contract or explicitly limit acceptance to structural binding. | Existing `cxf/S698-2026-10-02`, R:S698; inherited S670 acceptance remains separate. | `P/eval_gate/{stage_gate,stage_calibration_binding}.py`; `D/STRATEGY_STAGES_A7_PROPOSED.json`; `T/eval_gate/test_stage_gate_evidence_binding.py`; `H/S698_evidence_binding_2026-10-02.md`. Source: `W6:220`. |
| S674 | w6/a7 | YES; bounded validation correction. Attempt allowance UNKNOWN. | Continues `cxf/S674-2026-10-02`, R:S674. | `P/governance/{model_card_check,model_card_index}.py`; `T/governance/test_model_card_invalid_inputs.py`; `H/S674_invalid_inputs_2026-10-02.md`. Sources: `W6:259`; `O/px_v_S674.md`. |
| NEW-a7-2 | w6/a7 | YES; pure anchored incident replay. | Addresses a separately acknowledged S698 gap without owning its evaluator or policy. | `P/governance/stage_incidents.py`; `T/governance/test_stage_incidents.py`; `H/NEW_a7_2_stage_incidents_2026-10-02.md`; `D/STAGE_INCIDENTS_A7_PROPOSED.md`. Source: `W6:309`. |

### W7: delivery tooling

| ID | Lane | Buildable as written | Existing branch/register relationship | Owned files |
|---|---|---|---|---|
| NEW-a8-1 | w7/a8 | YES; historical fixture count must not become a live namespace constant. | Complements S679; master-plan NEW02. No exact owned-path overlap found in inspected cx branches. | `P/ops/landing_manifest.py`; `T/ops/test_landing_manifest.py`. Sources: `W7:78`; `W9:214`. |
| NEW-a8-5 | w7/a8 | YES; structured, sequential per-file execution. | Addresses behavior in `tools/desk_bin/run_files.py` without modifying it; master-plan NEW06. | `P/ops/{integration_file_runner,integration_pytest_receipt}.py`; `T/ops/test_integration_file_runner.py`. Sources: `W7:130`; `W9:218`. |
| NEW-a8-2 | w7/a8 | YES; consumes frozen identity contract. | Master-plan NEW03; diagnoses S678/S711 without owning their files. | `P/ops/landing_diff_gate.py`; `T/ops/test_landing_diff_gate.py`. Sources: `W7:182`; `W9:215`. |
| NEW-a8-3 | w7/a8 | YES; multiple byte-identity obligations are explicit. | Master-plan NEW04; complements S683 without rebuilding its interpreter comparison. | `P/ops/landing_eol_audit.py`; `T/ops/test_landing_eol_audit.py`; `H/LANDING_EOL_POLICY_2026-10-02.md`. Sources: `W7:238`; `W9:216`. |
| NEW-a8-8 | w7/a8 | NEEDS FIX: distinguish duplicate snapshot rows from valid same-row event succession; clarify same-ID changed-payload case. | Master-plan NEW08; complements existing S679 parser. | `P/ledger_audit/landing_transition_check.py`; `T/ledger_audit/test_landing_transition_check.py`. Sources: `W7:289`; `W9:220`. |
| NEW-a8-11 | w7/a8 | YES; planning output has no publication authority. | Uses existing `scripts/hooks/prepush_guard.py` grammar without owning hooks or allowlist. | `P/ops/public_export_plan.py`; `T/ops/test_public_export_plan.py`. Source: `W7:343`. |

### W8: evidence and inference accounting

| ID | Lane | Buildable as written | Existing branch/register relationship | Owned files |
|---|---|---|---|---|
| NEW-a9-1 | w8/a9 | YES; discovered census and activation are separate. | Master-plan NEW16; complements S682/S721. | `P/evidence/estimand_inventory.py`; `T/evidence/test_estimand_inventory.py`; `K/estimands.json`. Sources: `W8:91`; `W9:228`. |
| S682 | w8/a9 | YES; candidate repair plus fixture-driven adapter. Attempt allowance UNKNOWN. | Continues `cxf/S682-2026-10-02`, R:S682; operational adapter depends on S719. | `P/ops/{power_ledger,power_ledger_input,power_ledger_accrual}.py`; `T/ops/{test_power_ledger_s682_review,test_power_ledger_accrual}.py`; `K/ESTIMAND_SUPPORT_2026-10-02.json`. Source: `W8:147`. |
| S684 | w8/a9 | YES; additive serialized-output consumer. | Existing `cxf/S684-2026-10-02`, R:S684; new files do not replace `subset_census`. | `P/evidence/subset_funnel.py`; `T/evidence/test_subset_funnel.py`; `K/SELECTION_FUNNEL_2026-10-02.json`. Source: `W8:215`. |
| NEW-a9-4 | w8/a9 | YES with explicit fixture adapters; operational proof remains separate. | Master-plan NEW14; consumes S678 and a3 receipts without creating another manifest producer. | `P/evidence/input_availability_receipt.py`; `T/evidence/test_input_availability_receipt.py`; `K/AVAILABILITY_REPRODUCIBILITY_2026-10-02.json`. Sources: `W8:285`; `W9:226`. |
| NEW-a9-2 | w8/a9 | NEEDS FIX: give the alias-chain refusal case explicit missing launch proof; valid aliases alone cannot block readiness. | Complements S675/S721 without changing their arithmetic, partitions, or readers. | `P/evidence/desk_inference_inventory.py`; `T/evidence/test_desk_inference_inventory.py`; `K/INFERENCE_DESIGN_2026-10-02.json`. Source: `W8:350`. |
| S675 | w8/a9 | YES; residual candidate correction with unchanged simulation settings. Attempt allowance UNKNOWN. | Continues `cxf/S675-2026-10-02`, R:S675. | `P/eval_gate/multiplicity_haircut.py`; colocated `P/eval_gate/test_multiplicity_haircut_residual.py`; `H/S675_residual_verification_2026-10-02.md`. Source: `W8:409`. |

## 2. FILE-OWNERSHIP MATRIX

No two of the 48 explicit owned-file lists intersect. Shared proposed integration targets are excluded from those lists and must remain proposals until composed by their designated owner. Sources: CHANGE sections of `W1` through `W8`; `W10:55-81`.

In this matrix, `I` means the existing branch `cxp/integ-2026-10-02`. It is a test-only integration experiment and must not be used as a landing base. Source: `O/integ_windows_tests.md:115`.

| Shared owned files | Spec and existing branches | Resolution |
|---|---|---|
| `P/execution/{capture_book_provenance,book_provenance_replay}.py` | S720; `cxp/S720-2026-10-02` | Sequence one continuation on the existing candidate; merge NEW-a2-1 requirements into S720. Source: `W1:85-90`. |
| `P/ops/{clock_guard,clock_guard_cli}.py` | S695; `I` | Prepare a PROPOSED extraction/repair until a dedicated source base and dependency set are identified. Do not use `I`. Sources: `W1:147`; `O/integ_windows_tests.md:115`. |
| `P/ops/recorder_adopt.py` | S659; `cxf/S659-2026-10-02`; `cxf/S690-2026-10-02`; `I` | Sequence corrected S659 first, then S690's incremental publication work. Source: `W10:76`. |
| `P/ops/qualification_runtime_probe.py`; `T/ops/test_qualification_runtime_publication.py` | S711; `cxp/S711-2026-10-02` | Sequence the bounded repair on the existing candidate; preserve its publication controls and evidence history. Source: `W2:145-152`. |
| `P/ops/unresolved_nights.py`; `T/ops/test_unresolved_nights.py` | S713; `cxp/S713-2026-10-02` | Continue one obligation authority. S712 remains a projection/validator. Sources: `W2:245-256`; `W9:316`. |
| `P/ops/registry_e_health_reader.py`; `T/ops/test_registry_e_health_reader.py` | S718; `cxp/S718-2026-10-02` | Sequence one parser correction; retain shared issue integration as PROPOSED. Source: `W2:349-358`. |
| `P/execution/{fill_model_incidents,fill_model_latency}.py` | S671; `cxf/S671-2026-10-02`; `I` | Sequence the two bounded fixes; preserve existing venue-rule corrections. Source: `W3:100-103`. |
| `P/execution/queue_sensitivity.py` | S724; `cxp/S724-2026-10-02` | Continue the candidate and add its evidence parser; retain legacy metrics with explicit population labels. Source: `W3:218-230`. |
| `P/execution/core/fixture_night.py` | S693; `cxf/S693-2026-10-02`; `cxf/S703-2026-10-02`; `I` | Hold publication acceptance; resolve S693 semantic findings before composing descendant changes. Sources: `W3:397-408`; `O/px_v2_S693.md:16-31`. |
| `P/eval_gate/family_decay_monitor.py` | S701; `cxf/S701-2026-10-02`; `I` | Reconcile the prepared correction first. Do not create a duplicate repair or alter the detection bar. Sources: `W4:237-241`; `O/px_f_S701.md`. |
| `P/ops/{deadman_check,slo_status}.py` | S676; `cxf/S676-2026-10-02`; `I` | Sequence one candidate correction after attempt disposition. Source: `W6:89-95`. |
| `P/execution/{risk_receipt_io,risk_receipt}.py` | S669; `cxf/S669-2026-10-02`; `I` | Sequence transaction correction; keep shared consumer integration PROPOSED. Source: `W6:145-151`. |
| `T/execution/test_risk_limits_family.py` | S667; `cxf/S667-2026-10-02` | Extend the existing test; do not recreate the limits implementation. Source: `W6:189-191`. |
| `P/eval_gate/stage_gate.py` | S698; `cxf/S698-2026-10-02`; `I` | Sequence binding correction after freezing its input contract; do not overwrite inherited S670 files. Source: `W6:231-242`. |
| `P/governance/{model_card_check,model_card_index}.py` | S674; `cxf/S674-2026-10-02`; `I` | Sequence one validation repair; preserve existing cards, INDEX bytes, and PENDING semantics. Source: `W6:275-294`. |
| `P/ops/{power_ledger,power_ledger_input}.py`; `T/ops/test_power_ledger_s682_review.py` | S682; `cxf/S682-2026-10-02`; implementation files also in `I` | Continue the existing candidate, with validation repair before support-adapter integration. Source: `W8:159-179`. |
| `P/eval_gate/multiplicity_haircut.py` | S675; `cxf/S675-2026-10-02`; `I` | Sequence the residual correction; preserve original generator, tests, settings, and sealed verdicts. Source: `W8:418-460`. |

The following are integration collisions, not permission to expand any builder's owned list:

| Future shared target | Competing requirements | Resolution |
|---|---|---|
| `P/execution/paper_night.py`, S712 callers, E callers | S714, NEW-a3-1, S716, S558 | Keep separate PROPOSED documents; one a3 composition after contracts are accepted. Sources: `W2:95-98,193-196,297-300`; `W10:69`. |
| `P/execution/paper_night_inputs.py` | S716 and S534 | Sequence a composed change in its permitted chain context; do not restore either branch wholesale. Source: `W10:73`. |
| `P/ingame/local_state_capture.py` | S594, S596/S564, source-provenance work | Keep a2 as capture integrator; S596/S564 supplies a PROPOSED handoff. Sources: `W5:259-267`; `W10:68`. |
| `.gitattributes` | S546, S547, later a8 portability work | Retain distinct PROPOSED diffs; apply only after byte audit and applicable chain step. Sources: `W4:283,329`; `W10:71`. |
| `P/ingame/paper_calibration_additive/__init__.py` | Existing S721/S722/S723 branches | One later package assembly; NEW-a5-1/2/3 must not silently claim it. Source: `W10:78`. |
| Register, results ledger, `D/DESK_STATE.md` | All future landings | One serialized metadata applier; NEW-a8-8 validates supplied transitions only. Sources: `W7:289`; `W10:70`. |

## 3. DISPATCH LIST

This is an ordered build queue, not an instruction to launch 14 simultaneous workers. The initial operating recommendation remains two builders with separate review and landing capacity. NEW labels remain specification identifiers; only the register owner allocates S-ids. Sources: `W9:31,305,337`; `R:7,24-26`.

All entries use new files on `master`. Pin its resolved commit at launch; the last directly read master ref was `e48874bd501b24bcc9d68c9ffe0b5e47ad7d2e90`. Source: `.git/refs/heads/master`.

```text
DISPATCH|NEW-a8-1|landingmanifest|gpt-6.1-sol|master|Establish exact candidate and review identities before continuations; O/px_w7.md:78.
DISPATCH|NEW-a8-2|landingdiff|gpt-6.1-sol|master|Consume the identity contract and reject unowned inherited content; O/px_w7.md:182.
DISPATCH|NEW-a8-3|identitybytes|gpt-6-sol|master|Audit byte conventions while preserving every pinned input; O/px_w7.md:238.
DISPATCH|NEW-a8-5|filerunner|gpt-6.1-sol|master|Produce truthful sequential per-file verification receipts; O/px_w7.md:130.
DISPATCH|NEW-a3-1|nightbundle|gpt-6.1-sol|master|Build immutable attempt storage with shared integration held; O/px_w2.md:184.
DISPATCH|NEW-a2-2|capacitycensus|gpt-6-sol|master|Expose missing telemetry and deduplicate process counters; O/px_w1.md:227.
DISPATCH|NEW-a9-1|estimands|gpt-6-sol|master|Establish source-bound study populations and activation states; O/px_w8.md:91.
DISPATCH|NEW-a5-1|eligibilitywitness|gpt-6.1-sol|master|Separate retrospective terminal labels from decision-visible evidence; O/px_w4.md:96.
DISPATCH|NEW-a6-1|seasoncapacity|gpt-6-sol|master|Reconcile supplied schedules and hypothetical capacity without changing selection; O/px_w5.md:83.
DISPATCH|NEW-a6-2|nbareadiness|gpt-6.1-sol|master|Audit resolver-mediated identity and native source compatibility; O/px_w5.md:130.
DISPATCH|NEW-a9-2|launchaccounting|gpt-6.1-sol|master|Consume the estimand inventory and preserve launch-time accounting; O/px_w8.md:350.
DISPATCH|NEW-a4-1|recordintegrity|gpt-6.1-sol|master|Independently reconcile execution records and missing lineage; O/px_w3.md:142.
DISPATCH|NEW-a7-2|incidenthistory|gpt-6.1-sol|master|Build anchored incident replay without changing stage policy; O/px_w6.md:309.
DISPATCH|NEW-a8-8|metadatatransitions|gpt-6.1-sol|master|Validate ordered metadata transitions using the established identity contract; O/px_w7.md:289.
```

For these entries, ownership is exactly the table above, including evidence and proposal files. Existing package initializers, shared helpers, callers, metadata, captures, and seal files are outside ownership. Sources: selected SPEC CHANGE/MUST NOT TOUCH sections in `W1` through `W8`.

## 4. CORRECTED FINAL SPECS

The other ten dispatched blocks remain usable as written, with the source documents' common rails. Sources: `W1:71-73`; `W7:70-76`; their SPEC blocks cited above.

```text
=== FINAL SPEC NEW-a3-1 ===
TITLE: Immutable attempt bundles with manifest-last publication.
SOURCE: .planning/codex_push_2026-10-02/out/px_w2.md:184.
MASTER REQUIREMENT: .planning/codex_push_2026-10-02/out/px_w9.md:217.
BASE: master; record its resolved commit before building.
WHERE: isolated local worktree; offline constructs and scratch outputs only.
RAILS: PAPER ONLY; additive; ASCII; <=300 LOC per Python file.
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md B/Q.
OWNED NEW FILES:
scripts/platformkit/execution/night_bundle.py
tests/platformkit/execution/test_night_bundle.py
docs/research/organization-sprint/W2_NIGHT_BUNDLE_PROPOSED.md
docs/evidence/harness/W2_NIGHT_BUNDLE_result.md
PREMISE:
Recheck owned-path absence and current producer argument layouts.
If an equivalent owned-path implementation exists, report its identity.
Read S712 revision_steps at commit 7a8d849edcd569a97679085527f4541055504fcd
as frozen output-inventory context only; do not merge its queue or callers.
CHANGE:
Reserve one unique night/revision/attempt namespace exclusively.
Record intent; prepare outputs inside staging; validate; publish manifest last.
Inventory qualification, fill/resources, week, scoreboard, history rows/manifest,
E receipt/populations, and every producer sidecar.
Bind date, cutoff, requiredness/version, input/code/seal/budget identities,
exact output bytes/digests, semantic outcomes and attempt identity.
A manifest can commit an explicit failed outcome; committed does not mean COMPLETE.
Interrupted pre-manifest work remains uncommitted.
Post-manifest/pre-ledger reconciliation discovers exactly one committed attempt.
Never replace committed names; refuse aliases, escapes and unknown write targets.
Keep semantic validation injectable until S714's accepted contract is available.
Missing semantic evidence cannot establish COMPLETE.
Preserve runner_lock for one acquisition by the eventual integration caller.
Use atomic_replace.replace_with_retry only inside an exclusively reserved namespace.
A false replacement result is a failure.
Produce proposed producer-argument mapping; modify no live runner or S712 file.
COMPONENT ACCEPTANCE:
Enumerate 100 cases: ten named publication boundaries crossed with normal,
owner death, read refusal, write refusal, fsync refusal, replace refusal,
short write, contender, pre-existing target and corrupted bytes.
Declare independent expected outcomes before execution.
Zero invalid manifests committed; zero incomplete outcomes called COMPLETE.
Zero changed original digests; zero duplicate committed attempt identities.
Canonical/r1/r2 outputs coexist for all six steps and every sidecar.
Fresh-process reconciliation returns the same attempt on three repeated reads.
Use actual legacy argv layouts; reject shared week/history destinations.
MASTER-ROW ACCEPTANCE:
The master plan separately requires at least 100 declared interruption boundaries.
The component's 100 cases do not satisfy that distinct-boundary requirement.
Retain that requirement unchanged and report its coverage separately.
Do not close the master row until its boundary and integration requirements pass.
CONTROLS:
Manifest-before-validation and replacement of committed output must each fail.
FUTURE TEST: python -m pytest tests/platformkit/execution/test_night_bundle.py -q
REAL EVIDENCE:
No tracked real immutable bundle was verified; argument templates are constructs.
MUST NOT TOUCH:
Existing outputs, queues, callers, candidate files, seals, thresholds, capture,
flags, registry, shared metadata or original receipts.
No automatic retry, second scheduler, pruning, adoption or live producer execution.
=== END FINAL SPEC ===
```

```text
=== FINAL SPEC NEW-a4-1 ===
TITLE: Independent execution-record integrity and lineage audit.
SOURCE: .planning/codex_push_2026-10-02/out/px_w3.md:142.
BASE: master; record its resolved commit before building.
WHERE: isolated local worktree; offline supplied records and constructs.
RAILS: PAPER ONLY; additive; ASCII; <=300 LOC per Python file.
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md B/Q.
OWNED NEW FILES:
scripts/platformkit/execution/execution_record_audit.py
tests/platformkit/execution/test_execution_record_audit.py
docs/evidence/forward/execution_v2/record_audit.json
PREMISE:
Recheck owned-path absence and the existing record/denominator omissions.
CHANGE:
Accept explicit quote, print, fill, mark/refusal and manifest records.
Require units, source hashes, row locators and identity namespaces.
Partition budgets by policy/scenario/game/ticker/print identity.
Counterfactual policies have separate budgets.
Independently detect duplicate/conflicting identities, unmatched fills,
print over-allocation, order overfill and lifetime/side/price violations.
Through-only requires a strictly through print, never a depleted sentinel.
Reconcile raw, canonical, duplicate, malformed and refused records.
Compute missingness from canonical fills, including fee-invalid fills.
Keep unknown quantities separately counted.
Preserve legacy verdicts; add integrity and missingness fields.
Missing lineage yields UNVERIFIABLE; contradictory evidence yields INVALID.
Neither disposition can produce COMPLETE.
Consume explicit fee/mark component receipts; do not duplicate their algorithms.
Use venue_time.parse_venue_time.
For S551 inputs, use exec_policy_prereg.verify with explicit input/root.
A valid seal does not establish source-manifest or source-byte validity.
Write the output exclusively; refuse aliases and conflicting existing content.
ACCEPTANCE:
Preserve 16 constructs:
valid complete; valid partial fill; valid cross-policy reuse; missing quote;
missing print; identical duplicate; conflicting duplicate; print over-allocation;
order overfill; wrong game; wrong ticker/side; arrival equality; end equality;
through-only touch; missing fee lineage; incomplete marks with favorable legacy label.
"Valid partial fill" means filled quantity below the submitted order quantity,
with complete quote/print/fill/fee/mark lineage and conserved quantities.
It does not mean partial evidence or an incomplete input population.
Exactly the first three constructs may be COMPLETE.
The cross-policy control must satisfy conservation independently in each partition.
Every other construct remains non-COMPLETE under its declared refusal.
Every input record has one disposition and zero unexplained losses.
Supported fills satisfy exact Decimal conservation and strict time eligibility.
Expose missing-quantity share above the unchanged S551 20 percent threshold.
Preserve the original comparison label independently of this diagnostic.
Empty input is INSUFFICIENT; invalid quantity prevents a known-total claim.
No empirical conclusion below thirty unique complete games.
Label all constructs CONSTRUCT.
CONTROLS:
Invert strict-through, invert budget comparison, or omit fee-invalid fills:
each dedicated assertion must fail.
FUTURE TEST: python -m pytest tests/platformkit/execution/test_execution_record_audit.py -q
REAL ROW:
Use docs/evidence/forward/exec_quality/2026-09-22_2026-09-26.json:580
as refusal evidence only, never as a fill or completeness witness.
MUST NOT TOUCH:
Simulators, reducers, reports, historical receipts, seals, thresholds,
capture code/processes, shared callers, registry or flags.
No historical lineage invention, fill allocation, policy selection or adoption.
=== END FINAL SPEC ===
```

```text
=== FINAL SPEC NEW-a8-8 ===
TITLE: Offline validation of immutable landing-metadata transitions.
SOURCE: .planning/codex_push_2026-10-02/out/px_w7.md:289.
BASE: master; record its resolved commit before building.
WHERE: isolated local worktree; supplied byte snapshots and fixture events.
RAILS: PAPER ONLY; additive; ASCII; <=300 LOC per Python file.
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md B/Q.
OWNED NEW FILES:
scripts/platformkit/ledger_audit/landing_transition_check.py
tests/platformkit/ledger_audit/test_landing_transition_check.py
PREMISE:
Recheck owned-path absence; report existing implementation identity if present.
Actual activity of the existing ledger hook remains UNKNOWN.
CHANGE:
Implement a pure validator over before/after bytes and immutable event records.
Record schema, stable event ID, row ID, expected predecessor digest,
base/candidate/review/landing identities, evidence digests and proposed ledger append.
Reuse NEW-a8-1 identity encoding.
Keep code presence, post-landing verification, metadata completion and adoption separate.
Each row ID occurs once within each supplied register/handoff snapshot.
Multiple ordered events for the same row are valid when predecessor digests chain.
Reject ambiguous extraction and duplicate snapshot rows.
Preserve unrelated register/handoff bytes and the exact historical ledger prefix.
Check identical already-applied replay before predecessor comparison.
Exact replay is a no-op even after another event advances the row.
The same event ID with different content always refuses.
Every genuinely new event requires its expected predecessor.
Partial application is PENDING_RECONCILIATION, never CLOSED.
Status text and valid reviewer syntax cannot supply missing identity evidence.
Emit proposed transitions or reason-coded refusals; write no live metadata.
Do not copy S679's parser; its future lint_text interface remains candidate-only.
Hook/applier coordination remains separately owned PROPOSED integration.
ACCEPTANCE:
Preserve 100 CONSTRUCT schedules: ten event patterns x ten delivery patterns.
Event patterns:
disjoint rows; same-row succession; exact replay; same-ID changed payload;
stale predecessor; duplicate snapshot row; stale review; missing evidence;
contradictory closure; malformed identity.
Enumerate ten delivery/interruption patterns explicitly in the fixture.
Cover both orders, repeated first/second/both events and interruption/resumption.
All 100 match an independent reference oracle.
Accepted disjoint events survive once; valid same-row succession is accepted.
Exact replay adds no event; conflicting replay refuses.
Accepted proposals preserve historical ledger and unrelated bytes exactly.
Zero incomplete transactions become CLOSED.
Source fixture bytes remain unchanged.
CONTROLS:
Invert predecessor equality; check predecessor before replay;
delete a historical byte; omit one required metadata effect.
Each dedicated assertion must fail.
FUTURE TEST: python -m pytest tests/platformkit/ledger_audit/test_landing_transition_check.py -q
REAL ROWS:
Preserve both records at docs/evidence/RESULTS_LEDGER_SYSTEM.md:10-11.
They do not themselves establish authenticated independent acceptance.
MUST NOT TOUCH:
Actual register, results ledger, DESK_STATE, hook, S679 files, seals,
thresholds, capture code/processes, registry or flags.
No live writer, locks, new ledger, history rewrite or filesystem publication.
Actual writer concurrency, reviewer authentication and crash durability remain UNKNOWN.
=== END FINAL SPEC ===
```

```text
=== FINAL SPEC NEW-a9-2 ===
TITLE: Complete family, look and launch-accounting provenance.
SOURCE: .planning/codex_push_2026-10-02/out/px_w8.md:350.
BASE: master; record its resolved commit before building.
WHERE: isolated local worktree; frozen inputs and offline constructs.
RAILS: PAPER ONLY; additive; ASCII; <=300 LOC per Python file.
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md B/Q.
OWNED NEW FILES:
scripts/platformkit/evidence/desk_inference_inventory.py
tests/platformkit/evidence/test_desk_inference_inventory.py
docs/evidence/paper_desk/INFERENCE_DESIGN_2026-10-02.json
PREMISE:
Recheck implementation absence.
The reference ledger alone does not provide immutable launch proof.
CHANGE:
Consume NEW-a9-1 inventory, explicit frozen family specification and launch receipts.
Enumerate contrast/corpus/horizon/direction/look and retain endpoint roles.
Retain unavailable, abandoned, unevaluable and unmapped members.
Distinguish K-declared, K-evaluable, observed ledger count and evidenced K-at-launch.
Missing launch evidence is UNKNOWN, never zero.
Resolve aliases through the existing family reader; bind that reader's identity.
Unknown mappings stay PROPOSED/UNMAPPED.
A valid alias is not independently a readiness failure.
Preserve each sealed study's local family and look rule.
Require a source-bound premetric charge/launch receipt for readiness.
Bind seal, family version, input snapshot, candidate and exact metric invocation.
Later ledger reconstruction remains descriptive.
Report coverage separately from readiness.
Reuse family_bars.resolve_family and load_families with explicit frozen inputs.
Use ledger.load_fwer only after proving the supplied snapshot exists/readably parses.
Never invoke charging functions or a default live-ledger path.
ACCEPTANCE:
Every declared member receives exactly one disposition; coverage is 100 percent.
Preserve superseded identities; dates and alias spelling cannot reset K.
Preserve twelve CONSTRUCT cases:
1 valid prelaunch receipt using a recognized alias;
2 missing receipt; 3 postmetric receipt; 4 wrong seal; 5 wrong family pin;
6 split family; 7 dropped unavailable arm; 8 reset date count;
9 recognized alias chain without proved prelaunch evidence;
10 unknown family; 11 missing ledger; 12 descriptive-only read.
Case 1 establishes readiness only with all required valid evidence.
Cases 2-11 cannot establish complete launch readiness.
Case 9 refuses for missing launch proof, not for having an alias chain.
Case 12 records no new inferential look.
Preserve S551's first qualifying look and S519's D* rule byte-faithfully.
Same-game observations from two venues remain overlapping cohorts.
S721's unfinished family/look fields remain PROPOSED.
All sealed thresholds and frozen partition bytes remain unchanged.
CONTROLS:
Treat postmetric reconstruction as launch proof, drop unavailable membership,
or reset K by date: each dedicated assertion must fail.
FUTURE TEST: python -m pytest tests/platformkit/evidence/test_desk_inference_inventory.py -q
REAL ROW:
scripts/platformkit/eval_gate/reference_runs/fwer_backtest_ledger.jsonl:1.
Missing launch/family/seal provenance remains UNKNOWN.
MUST NOT TOUCH:
Family specification/aliases, charging code, live ledger, sealed studies,
historical verdicts, S675 arithmetic, S721 reader, pins, registry or flags.
No partition changes, historical regrading, scoring, sealing or adoption.
=== END FINAL SPEC ===
```

## 5. HOLD LIST

Every non-dispatched SPEC block is accounted for below.

| Specs | Hold reason and release condition |
|---|---|
| S720, S659, S711, S713, S718, S671, S724 | These are existing candidate continuations. Reconcile exact current candidate, outstanding correction, and remaining attempt allowance before another build. Allowance is UNKNOWN from retained reports alone; a new branch or companion module must not reset history. Sources: their quality-table citations; `W9:29`; `D/cloud/desk-improve.prompt.txt:53-57`. |
| S597 | Two retained REJECT reports and absent implementation require an explicit attempt disposition before redispatch. Do not silently restart it as a new row. Sources: `O/px_v_S597.md`; `O/px_v2_S597.md`; `W1:112`. |
| S695 | No dedicated matching cx continuation base was established. Freeze a permissible candidate/extraction set; do not build from the integration experiment. Sources: `W1:147`; `O/integ_windows_tests.md:115`. |
| S714, S716 | Resolve master-only companion scope and original attempt allowance first. Shared caller changes remain proposals; existing failures and row history persist. Sources: `W2:85,288`; `O/px_v_S714.md`; `O/px_v_S716.md`; `W9:29`. |
| S693 | Latest independent report still identifies two allocation defects outside this fixture-publication spec's ownership. Correct-model publication acceptance remains held. Source: `O/px_v2_S693.md:16-31`. |
| S701 | The correction is already reported prepared, while branch evidence needs reconciliation. Preserve the unchanged detection requirement and its recorded limit disposition. Sources: `O/px_f_S701.md:1-16`; `W4:228`; `W9:268`. |
| S676, S669, S674, S675, S682 | Existing candidate corrections require exact-identity and attempt reconciliation. S682 additionally depends on accepted S719 output for operational use. Sources: `W6:74,78,130,259`; `W8:147,409`; `O/px_v2_S682.md`; `O/px_v2_S719.md`. |
| S667 | Existing ACCEPT WITH CORRECTIONS candidate; classify the archive-auditor extension and remaining verification before adding another lane. Sources: `W6:173`; `O/px_v_S667.md`. |
| S698 | Freeze observation-membership contract and retain unresolved S670 dependency. Structural binding acceptance cannot imply integrated stage readiness. Source: `W6:220-256`. |
| NEW-a5-3 | Sequence behind a fixed NEW-a5-1 witness schema. Source: `W4:194-215`. |
| S596/S564 | Resolve approved crosswalk routing. Live adoption additionally retains its original measured-game, completeness, latency, and resource requirements. Sources: `W5:250-284`; `docs/evidence/tracking/specs/S596_spec.md:9-14`. |
| S681, NEW-a9-4 | Safe offline alternates, deferred behind the first 14. S678 dependency acceptance and actual restore/prospective-read evidence remain separate milestones. Sources: `W1:273`; `W8:285`. |
| S684 | Safe additive consumer, deferred until its input interfaces are stabilized; operational acceptance needs corrected S719 and independent baseline S684 acceptance. Source: `W8:215-282`. |
| NEW-a4-4, NEW-a4-5 | Safe next-batch execution-evidence components. Keep fee applicability, mark lineage, and empirical completeness separate from construct acceptance. Sources: `W3:266,322`. |
| NEW-a5-2 | Safe next-batch normalizer; preserve existing S722 ownership and separate real-corpus replay requirements. Source: `W4:140`. |
| S546, S547 | PREPARE components deferred behind operational evidence work. Authenticate exact private-source fixtures before fixture acceptance; no scoring or integration implied. Sources: `W4:270,316`; `W9:280`. |
| NEW-a6-3, NEW-a6-4, S532 | Safe subsequent census/proposal work. Scored-reader, display, admission, and seal changes remain separately owned integration steps. Sources: `W5:170,208,290`. |
| NEW-a8-11 | Safe next-batch export planner; publication authority and exporter integration remain excluded. Source: `W7:343-400`. |

Additional inherited holds remain binding:

- Do not land `cxp/integ-2026-10-02` wholesale. Source: `O/integ_windows_tests.md:115`.
- Do not use S691 descendant content as accepted core evidence while the latest S691 report remains REJECT. Source: `O/px_v2_S691.md`.
- Do not treat S664's newer ACCEPT WITH CORRECTIONS as proof of live clock collection, hook adoption, or downstream S695 behavior. Source: `O/px_v3_S664.md`.
- Preserve the receipt-gated seal chain and serialized capture adoption sequence. Sources: `D/DESK_STATE.md:49-78`; `W10:261-279`.
- NEW-a3-1 component acceptance does not close the master plan's distinct interruption-boundary requirement. Sources: `W2:184`; `W9:217`.

## 6. NOT VERIFIED

- All ten explicitly named wave files existed. The final filename census found 20 `px_b_S*.md` files and 66 `px_v*_S*.md` files. The directory changed during the audit; this is not an atomic repository snapshot. Sources: `O/px_w1.md` through `O/px_w10.md`; `O/px_v2_S691.md`; `O/px_v2_S693.md`; `O/px_v3_S664.md`.
- Matching builder reports were absent for several candidate-only rows, including S659, S671, S681, S693 and S695. No matching `px_v*_S695.md` or `px_v*_S681.md` was found. Their specification and available branch evidence were used; missing report contents are UNKNOWN.
- Current running-process identities, installed tasks, capture continuity, recorder adoption, and actual platform behavior are UNKNOWN.
- Original attempt histories and remaining correction allowance are UNKNOWN where identified above. Filename suffixes alone do not establish a complete attempt history. Sources: `W9:29`; `D/cloud/desk-improve.prompt.txt:53-57`.
- Builder/verifier test outcomes are documentary evidence only; this audit did not reproduce them. Sources: the cited `O/px_b_S*.md` and `O/px_v*_S*.md` reports.
- Complete transitive seal closure and cryptographic recomputation of every pin are UNKNOWN. The selected owned paths are new, absent from the inspected checkout, and excluded from the inspected pin declarations; existing files remain outside ownership. Sources: selected SPEC ownership lists; `D/DESK_STATE.md:64-71`; `F/**/PREREG*.json`.
- Exact membership/provenance of NEW-a8-1's historical 125-entry fixture remains UNKNOWN unless the builder can supply its frozen snapshot. Do not fabricate historical members or treat that count as the current namespace size. Source: `W7:101`.
- Semantic duplicates under unrelated filenames, non-cx candidate content, and later ref movement are not exhaustively excluded. Sources: `W7:17,418`; inspected local cx branch deltas.
- Real capacity telemetry, authenticated historical prefixes, prospective availability bundles, private S546/S547 fixture bytes, and full operational integration remain unverified where their specs explicitly require them. Sources: `W1:227,273`; `W4:96,270,316`; `W8:285`.
- External documentation, current provider semantics, and network state are UNKNOWN under this local-only audit.