# Per-file test sweep triage (2026-09-29/30, quality lead)

Source: data/cache/test_sweep/2026-09-29_master.jsonl (one low-priority, RAM-gated pytest per file over tests/platformkit + tests/domains, 1,123 files; the dispatcher pauses it in RAM windows). Each non-green file was re-run alone (capped runner) or triaged statically when RAM was below the gate. Classes: a = real code regression on master; b = stale test; c = environment-only (gitignored local data/state, local package ABI); d = flaky / over the per-file time budget; r = memory defect (rss_exceeded).

## Counts (regenerated 2026-09-30T04:27Z)

- Files swept so far: 776; green: 726; non-green: 50; triaged non-green: 51.
- Per class: a=2, b=28, c=10, d=7, r=4

## Files

| file | class | evidence | cause group | owner row |
|---|---|---|---|---|
| tests/domains/mlb/test_rung8_state.py | b | FileNotFoundError data/domains/mlb/gumbo_live/822710.jsonl (file now in gumbo_live/_archive/ after sidecar_retention) | G5 loader ignores retention _archive | S574 LANDED 9c0d0bfd0 |
| tests/platformkit/autonomy/test_autonomy_monitor_reaper_wire.py | b | KeyError 'reaper_status' on the m5_autonomy_monitor row added by _apply_m5fix (test :150) | G2 autonomy tests read real m5 heartbeat | S571 LANDED aab5b6f36 |
| tests/platformkit/autonomy/test_autonomy_monitor_runner.py | b | overall 'degraded' vs 'ok': m5fix reads real data/cache/daemon_heartbeats/m5_autonomy_monitor.txt, future vs fake NOW (test :63, :81) | G2 autonomy tests read real m5 heartbeat | S571 LANDED aab5b6f36 |
| tests/platformkit/answers/test_qa_bank.py | r | rss_exceeded 1500 MB (5.2 GB earlier); SMOKE run -> intel_query/ask.py unbounded load_verified_claims over 4.2 GB claims stores | G4 qa smoke unbounded claims load | S573 LANDED ced4ab86a (memory fixed; stays red on 5 data-age refusals + 2 pre-existing schema failures) |
| tests/platformkit/canary/test_stack_canary.py | b | 'DEGRADED' == 'READY': _FakePred.produced_at pinned 2026-06-20 vs 24 h PREDICTION_STALE_SEC with now=time.time() | G1 wall-clock date pins | S570 LANDED fac4118de |
| tests/platformkit/claims/test_card_grader.py | b | 'STARVED' == 'OPEN': cards registered 2026-07-14, grade_card now defaults to real clock, 45-day starve rule (card_grader.py:205) | G1 wall-clock date pins | S570 LANDED fac4118de |
| tests/platformkit/evidence/test_exec_evidence_series.py | b | KeyError 'moneyline' (:100): rows dated 2026-07-14/15 outside days=30 window (exec_evidence_series.py:231) | G1 wall-clock date pins | S570 LANDED fac4118de |
| tests/platformkit/execution/test_capture_book_adapter.py | b | DID NOT RAISE KeyError (:52): S370 d11488ae6 made missing ts a book_time_invalid diagnostic after S373 pinned KeyError | G3 intentional code change not propagated to older test | S572 LANDED e9c9cfa11 |
| tests/platformkit/execution/test_focus_window_admission.py | b | memo tail != 3 bullets (:299): S410 AMENDMENT 5 ac0d247b4 appended a section after NOT VERIFIED | G3 test pins a mutable doc tail | S572 LANDED e9c9cfa11 |
| tests/platformkit/execution/test_forward_capture_stream_integration.py | d | c18_c19[s389] failed in sweep; capped re-run 8 passed (96.9 s) | G6 load-sensitive subprocess tests | S579 RECORDED (flaky, not reproducible) |
| tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py | d | policy_fresh_process_byte_identity failed in sweep; capped re-run 8 passed (47.5 s) | G6 load-sensitive subprocess tests | S579 RECORDED (M1(a): no night-path regression) |
| tests/platformkit/execution/test_live_shadow_fills_memo.py | b | case22 inventory: pinned .gitattributes bytes (2234 -> 2418) moved by S550 caf56d81e after S516 pinned them | OWNER orchestrator 4 (S516) / execution 2.0 lead (S550) | S635 RESERVED / EXEC-LIVE lead (S516) |
| tests/platformkit/execution/test_paper_account.py | b | frozen sha of fill_realism.py 62a68538 (CRLF working copy) moved by S473 bfd526163 | G3 -> S572 LANDED e9c9cfa11 | S572 LANDED e9c9cfa11 |
| tests/platformkit/execution/test_touch_queue_sensitivity.py | b | type(fill_ts) is int (:114) but S370 d11488ae6 venue parser returns float 12.0 | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/foundry/test_foundry_runner_s16.py | c | StaleCorpusError: data/cache/combo/gate_corpus_nba built ~09-02, nba sources regenerated 09-14 (tiers.py:216 -> corpus_cache.py:127) | G7 tests read gitignored local state | S576 LANDED b4a1250fb |
| tests/platformkit/foundry/test_tiers.py | c | same StaleCorpusError via run_tier T0 (:137) | G7 tests read gitignored local state | S576 LANDED b4a1250fb |
| tests/platformkit/improve/test_daemon_seen_ids_no_candidate.py | b | live data/cache/improve/PIPELINE_ENABLED present (armed Jun 19) -> _pipeline_armed advances cursor (selfimprove_daemon.py:82-92,177-187); static triage (capped runner denied by classifier) | G7 tests read gitignored local state | S576 LANDED b4a1250fb |
| tests/platformkit/improve/test_ledger_reconcile.py | b | 17 fail: test asserts status/n_drift/drift_flags; module (ledger_reconcile.py:250-285) returns verdict/n_orphan_*; never aligned (0d6db3cfc vs b1f55adc6); static | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/improve/test_prop_line_distance_calib.py | c | timeout 300 s twice: test_none_input (:482) reads real data/cache/pregame_oof.parquet (356,678 rows) through O(n^2) _compute_rolling_sigma | G7 tests read gitignored local state | S576 LANDED b4a1250fb (+ revealed red test_empty_stats_list -> S631) |
| tests/platformkit/improve/test_selfimprove_ratchet_sandbox_proof.py | b | 4 fail: asserts live PIPELINE_ENABLED sentinel absent (:118-125, :239-245); it exists; static | G7 tests read gitignored local state | S576 LANDED b4a1250fb |
| tests/platformkit/ingame/test_four_arm_output_audit.py | d | timeout in sweep; re-runs 94 passed in 261.6 s and 299.25 s (function-scoped fixture recomputes 2000-iter bootstrap per test) | G6 slow/load-sensitive | S578 LANDED ca6f67866 |
| tests/platformkit/ingame/test_nba_checkpoints_to_joined.py | b | assert 4 == 1 (:75), 2 == 1 (:150): select_rows keeps NBA ticks without model_prob since S387 c6600afd1 (model-optional arm D) | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/ingame/test_nba_seal_package_pins.py | b | placeholder lines [94,101,...] != pinned [91,98,...] (:20) after S402 028e495f4 draft amendment; do_not_seal count 8 -> 11 next | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/ingame/test_nba_four_arm_output_audit_exposure.py | d | timeout 300 s twice; ~84 tests x nba.audit ~4 s (N_BOOT 2000 python bootstrap) | G6 slow over cap | S578 LANDED ca6f67866 |
| tests/platformkit/ingame/test_nba_four_arm_output_audit_fix1h.py | d | timeout 300 s in sweep; same audit bootstrap cost (static) | G6 slow over cap | S578 LANDED ca6f67866 |
| tests/platformkit/ingame/test_nba_four_arm_primary_contrast.py | d | timeout 300 s in sweep; 278 tests, repeated 2000-draw bootstraps (static) | G6 slow over cap | S578 LANDED ca6f67866 |
| tests/platformkit/ledger_audit/test_dup_key_detector.py | b | 'abc-123/open' == 'abc-123'; n_dups 0 vs 8: status-aware _row_key (dup_key_detector.py:42-59) vs open/settled-twin fixture (snapshot b1f55adc6) | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/ledger_audit/test_dup_runner.py | b | TestRunEightDups n_dups 0 vs 8, same cause | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/live_edge/test_compose.py | r | rss_exceeded 1500 MB: test_run_compose_real_slice_smoke (:110-125) run_compose() on real corpora incl. intel_claims box rate; also writes real data/omni/live_edge/compose/ | G7 tests read gitignored local state | S576 LANDED b4a1250fb |
| tests/platformkit/live_edge/test_gpu_dist.py | c | RuntimeError: Numpy is not available (gpu_dist.py:103): torch 2.2.0 built for NumPy 1.x, NumPy 2.2.6 installed | E1 local numpy/torch ABI (owner env decision) | owner env decision (numpy<2 or torch>=2.3); record only |
| tests/platformkit/live_edge/test_joint_dist.py | c | same RuntimeError at joint.py:87/:142 | E1 local numpy/torch ABI (owner env decision) | owner env decision; record only |
| tests/platformkit/live_edge/test_joint_v2.py | c | same RuntimeError at joint.py:87 | E1 local numpy/torch ABI (owner env decision) | owner env decision; record only |
| tests/platformkit/live_edge/test_shadow.py | r | rss_exceeded 1500 MB: replay smoke reads the whole real data/cache/inplay_odds/nba_price_series.parquet (8,399,632 rows) twice | G7 tests read gitignored local state | S576 LANDED b4a1250fb |
| tests/platformkit/live_edge/test_tick_replay.py | b | TypeError NoneType (:134): survivors.iloc[0] of local claims.parquet is now a structural claim parse_claim returns None for | G7 tests read gitignored local state | S576 LANDED b4a1250fb (+ claims drift -> S633) |
| tests/platformkit/mcp_server/test_envelope_contract.py | a | 5 red W01-W04 OK_ASOF_IS_WALL_CLOCK (win_probability stamps as_of with wall clock), H01 OK_NO_SOURCE_ARTIFACT/OK_NO_AS_OF (_system_health tools.py:87-112); the S71 a5aaa0541 recorded residual | G8 answer envelope residual (code) | S641 OPEN (S71 residual; mcp_server tools.py) |
| tests/platformkit/odds_provider/test_inplay_kalshi.py | b | Extra items 'src_ts' vs _CANON_KEYS (:40): inplay_kalshi.py:160 emits src_ts since 6ff50ea96 | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/odds_provider/test_pinnacle.py | b | 'unsupported' not in "pinnacle: no live league ids for 'cricket'" (:272) since ac9612a0e | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/ops/test_deploy_pathspec.py | b | paper closure scripts 332 != pinned 330 (:20-33, :98); 2 modules entered the closure after S187 | G3b stragglers | S577 LANDED a28225485 |
| tests/platformkit/ops/test_forward_qualification_cross_sport.py | d | timeout 300 s: dense 720-decision tests; quote_reservation.reserve bisection calls position_caps.check_caps which re-walks the Decimal snapshot per probe (S357/S372) | G6 slow over cap (+ perf note to execution lead) | S578 LANDED ca6f67866 (21 fast tests green; 4 dense tests split OVER-CAP, blocked on execution lead replay cost) |
| tests/platformkit/paper/test_settle_sweep.py | b | n_aged_ge_7d 4 == 3 (:160): RECENT_TS 2026-07-13 vs settle_sweep.inventory datetime.now (:152) | G1 wall-clock date pins (round 2) | S636 LANDED aeb504c5c |
| tests/platformkit/progress/test_ci_boundary_invariants.py | c | sentinel_before is False (:248): real data/cache/improve/PIPELINE_ENABLED present | G7 live sentinel (round 2) | S637 OPEN |
| tests/platformkit/progress/test_progress_ledger.py | c | engine_enabled True is False (:43, :101): ci_cadence.py:157 reads the live sentinel | G7 live sentinel (round 2) | S637 OPEN |
| tests/platformkit/showcase/test_rooms_calibration_ledger_replay.py | r | rss_exceeded: replay._load_candidate_rows reads all 13.47M rows of data/cache/inplay_odds/mlb_price_series.parquet (replay.py:25-34) | G7r real-data memory (round 2) | S637 OPEN |
| tests/platformkit/showcase/test_strict_json_exports.py | a | nan is None (:14), 'render must follow serialization' (:60): d175933b3 producer hunk (non-finite p -> None; allow_nan=False before write) lost when 6ad83a813 landed on mechanism_ledger_export.py | G9 lost merge hunk (code) | S634 LANDED 7216e1813 (real regression) |
| tests/platformkit/test_aggregate_clv_to_corpus.py | c | build_corpus_from_grades is None (:121): require_enabled gates on the live sentinel | G7 live sentinel (round 2) | S637 OPEN |
| tests/platformkit/test_bestbets_compute.py | c | route tests: _from_daemon_cache reads live data/frontend/best_bets.json (stale envelope) before the mocked compute_best_bets (bestbets_board_routes.py ~236-243); static (RAM) | G7 live state (round 2) | S637 OPEN |
| tests/platformkit/test_bestbets_compute_runner.py | b | beats.count(42.0) 1 vs >= 2: per-tick _beat() uses a fresh stamp since d7c69c8f4 (bestbets_compute_runner.py:183); static | G3 stale pins (round 3) | S638 LANDED 1d9de93e7 |
| tests/platformkit/test_bestbets_compute_stale.py | b | fresh card dropped: _NOW 2026-06-20 pinned for the suppressor but board_sanitizer.sanitize uses the real clock (board_sanitizer.py:111-128); static | G1 wall-clock date pins (round 2) | S636 LANDED aeb504c5c |
| tests/platformkit/test_clv_ledger_dedup.py | b | 3 fail: status-aware _row_key keeps open+settled twins; seen holds '<id>/open'; _run_concurrency runs _selfheal before the gate; static | G3 stale pins (round 3) | S638 LANDED 1d9de93e7 |
| tests/platformkit/test_clv_ledger_write_path_guard.py | b | gate ok=True on synthetic dup: _run_concurrency self-heals first (run_governance.py ~124-140); static | G3 stale pins (round 3) | S638 LANDED 1d9de93e7 |
| tests/platformkit/execution/test_live_shadow_quoter.py | b | test_pinned_must_not_move_seal (:248): S515 memo seal pins capture_watchdog.py moved by S601 d248930ea + S607 181e18e51 | OWNER EXEC-LIVE lead (S515) -- note in NOW.md 03:2xZ | S635 RESERVED / EXEC-LIVE lead (S515) |

## Notes

- Probe hygiene incident: a triage probe (bare python, fake clock, 20:45Z) wrote the live m5 heartbeat (1970 stamp) and a scanned_at=1e6 orphan report; a S576 verification run on main shipped nba/v0005+v0006 into data/cache/improve/artifacts and moved current.json 4 -> 6 (payload identical to v0004). Neither reverted (owner decision; S632). Rule since: no test or probe runs with the main checkout on sys.path except through the landed, isolated tests.
- Night-path perf finding (S578, execution lead): forward replay cost per game ~O(rows^2) via quote_reservation.reserve -> position_caps.check_caps re-walking all orders.
- Human-gated trees (src/, kernel/, api/, scripts/team_system/, intel/): no non-green file required an edit there.

## Not yet swept (untriaged) at 04:4xZ 2026-09-30: 417 of 1193 files

The dispatcher resumes the sweep 06:00Z-18:00Z (2.5 GB start gate); every file below is still unknown, not green.

- tests/domains/mlb/test_rung8_state_resolver.py
- tests/platformkit/autonomy/test_autonomy_monitor_m5_isolation.py
- tests/platformkit/execution/test_forward_replay_io_shard_sport.py
- tests/platformkit/execution/test_live_shadow_prereg.py
- tests/platformkit/execution/test_nba_season_cohorts.py
- tests/platformkit/execution/test_replace_retry.py
- tests/platformkit/execution/test_s494_evidence.py
- tests/platformkit/execution/test_s551_cancel_policy.py
- tests/platformkit/execution/test_s551_prereg_report.py
- tests/platformkit/execution/test_s551_replay.py
- tests/platformkit/execution/test_s580_nba_consumer_policy.py
- tests/platformkit/execution/test_s584_shadow_midnight.py
- tests/platformkit/execution/test_s584_shadow_midnight_a2.py
- tests/platformkit/execution/test_s611_latest_stream.py
- tests/platformkit/execution/test_s612_team_codes.py
- tests/platformkit/execution/test_schedule_revise.py
- tests/platformkit/execution/test_schedule_revise_e2e.py
- tests/platformkit/execution/test_scoreboard_cumulative.py
- tests/platformkit/execution/test_scoreboard_cumulative_e2e.py
- tests/platformkit/execution/test_scoreboard_cumulative_landed.py
- tests/platformkit/execution/test_scoreboard_cumulative_order.py
- tests/platformkit/execution/test_seal_provenance_1e.py
- tests/platformkit/ingame/test_audit_memo.py
- tests/platformkit/ingame/test_capture_watchdog_s601.py
- tests/platformkit/ingame/test_capture_watchdog_s607.py
- tests/platformkit/ingame/test_corpus_hygiene.py
- tests/platformkit/ingame/test_espn_play_clock.py
- tests/platformkit/ingame/test_espn_play_clock_1b.py
- tests/platformkit/ingame/test_espn_play_clock_realrow.py
- tests/platformkit/ingame/test_gate_a0_rederive.py
- tests/platformkit/ingame/test_local_capture_tail_stream.py
- tests/platformkit/ingame/test_m2_readout.py
- tests/platformkit/ingame/test_m2_readout_e2e.py
- tests/platformkit/ingame/test_m2_readout_history.py
- tests/platformkit/ingame/test_m2_readout_prod.py
- tests/platformkit/ingame/test_nba_four_arm_primary_contrast_endpoints.py
- tests/platformkit/ingame/test_nba_season_type.py
- tests/platformkit/ingame/test_polymarket_heartbeat_ts.py
- tests/platformkit/ingame/test_s439_integrity_audit.py
- tests/platformkit/ingame/test_s439_integrity_audit_e2e.py
- tests/platformkit/ingame/test_s439_integrity_audit_guards.py
- tests/platformkit/ingame/test_s542_anchor_projection.py
- tests/platformkit/ingame/test_s542_replay.py
- tests/platformkit/ingame/test_s542_verdict_e2e.py
- tests/platformkit/ingame/test_state_rollover_carry.py
- tests/platformkit/ingame/test_state_route_deadline.py
- tests/platformkit/ingame/test_state_route_deadline_pacer.py
- tests/platformkit/ingame/test_state_route_deadline_real_caller.py
- tests/platformkit/ingame/test_state_source_latency.py
- tests/platformkit/ingame/test_state_source_latency_cli.py
- tests/platformkit/ingame/test_team_labels.py
- tests/platformkit/ingame/test_team_labels_night.py
- tests/platformkit/intel_query/test_ask_residual_bound.py
- tests/platformkit/ops/test_forward_qualification_cross_sport_dense.py
- tests/platformkit/ops/test_paper_desk_issue_link_s605.py
- tests/platformkit/ops/test_paper_desk_issue_offday.py
- tests/platformkit/ops/test_paper_desk_issue_supervisor.py
- tests/platformkit/ops/test_paper_desk_issue_supervisor_a2.py
- tests/platformkit/ops/test_paper_desk_issue_tick.py
- tests/platformkit/ops/test_paper_desk_legacy_nights.py
- tests/platformkit/ops/test_paper_desk_orphan_grace.py
- tests/platformkit/ops/test_paper_desk_s520_night.py
- tests/platformkit/ops/test_paper_desk_s520_night2.py
- tests/platformkit/ops/test_paper_desk_s520_schedule.py
- tests/platformkit/ops/test_paper_desk_s521_expiry.py
- tests/platformkit/ops/test_paper_desk_schedule_ack.py
- tests/platformkit/ops/test_s496_baseline_clean.py
- tests/platformkit/ops/test_system_fault_matrix.py
- tests/platformkit/test_coherence_audit.py
- tests/platformkit/test_contract_preflight.py
- tests/platformkit/test_crps_market_mlb.py
- tests/platformkit/test_defender_matchup_gate_run.py
- tests/platformkit/test_demo_render.py
- tests/platformkit/test_demo_select.py
- tests/platformkit/test_diff_timing_artifacts.py
- tests/platformkit/test_edge_completion_gate.py
- tests/platformkit/test_espn_pbp_backfill.py
- tests/platformkit/test_espn_spread_total.py
- tests/platformkit/test_eval_gate_ledger_drift.py
- tests/platformkit/test_feature_spec_nba.py
- tests/platformkit/test_feature_spec_tennis.py
- tests/platformkit/test_fill_model_fill_realism.py
- tests/platformkit/test_fill_model_meta_label.py
- tests/platformkit/test_fit_w_surface.py
- tests/platformkit/test_footage_bridge_retention.py
- tests/platformkit/test_freshness.py
- tests/platformkit/test_freshness_serving_guard.py
- tests/platformkit/test_freshness_sidecar_runner.py
- tests/platformkit/test_g141_corner_detector_recall.py
- tests/platformkit/test_g148_two_slot_measure.py
- tests/platformkit/test_g151_quota_fails_loud.py
- tests/platformkit/test_g205_zero_shot_corner_probe.py
- tests/platformkit/test_g208_zero_shot_corner_probe_learned.py
- tests/platformkit/test_g210_court_model_fit_to_lines.py
- tests/platformkit/test_g210b_court_fit_untruncated_search.py
- tests/platformkit/test_g214_learned_corner_probe_pod.py
- tests/platformkit/test_g215_temporal_homography_propagation.py
- tests/platformkit/test_g217_oracle_error_decomposition.py
- tests/platformkit/test_g222_direct_to_seed_propagation.py
- tests/platformkit/test_g223_line_error_structure.py
- tests/platformkit/test_g224_tophat_line_evidence_transfer.py
- tests/platformkit/test_g227_keypoint_provider_probe.py
- tests/platformkit/test_g229_keypoint_gate_funnel.py
- tests/platformkit/test_g233_basketball_seeded_court_coordinates.py
- tests/platformkit/test_g289_implausible_step_decomposition.py
- tests/platformkit/test_g292_jump_endpoint_content.py
- tests/platformkit/test_g294_gap_conditioned_implausibility.py
- tests/platformkit/test_g296_merge.py
- tests/platformkit/test_g296a_extract_frames.py
- tests/platformkit/test_g296b_located_players.py
- tests/platformkit/test_g299_static_track_share.py
- tests/platformkit/test_g303_recall.py
- tests/platformkit/test_g304_adjudication.py
- tests/platformkit/test_g304_e1_packet.py
- tests/platformkit/test_g304_eligibility.py
- tests/platformkit/test_g304_eligibility_ext.py
- tests/platformkit/test_g304_locator_pass1.py
- tests/platformkit/test_g304_locator_pass1_ext.py
- tests/platformkit/test_g304_locator_pass2.py
- tests/platformkit/test_g304_locator_pass2_ext.py
- tests/platformkit/test_g309_multigame_census.py
- tests/platformkit/test_g310_instance_key.py
- tests/platformkit/test_g311_proxies.py
- tests/platformkit/test_g312_coverage_denominator.py
- tests/platformkit/test_g313_ten_id_cap.py
- tests/platformkit/test_g314_ball_inferred_coords.py
- tests/platformkit/test_g315_same_id_step_screen.py
- tests/platformkit/test_g316_scoreboard_clock_liveness.py
- tests/platformkit/test_g318_probe_status.py
- tests/platformkit/test_g319_census_recomputable.py
- tests/platformkit/test_g320_ball_inferred_no_coord.py
- tests/platformkit/test_g322_oversized_boxes.py
- tests/platformkit/test_g323_nonplayer_boxes.py
- tests/platformkit/test_g324_rows.py
- tests/platformkit/test_g325_offframe_boxes.py
- tests/platformkit/test_g326_crlf_safe_hashes.py
- tests/platformkit/test_g326_hash_sink_census.py
- tests/platformkit/test_g327_batch_stability.py
- tests/platformkit/test_g328_daemon_worker_accounting.py
- tests/platformkit/test_g329_degenerate_resume.py
- tests/platformkit/test_g330_panorama_identity.py
- tests/platformkit/test_g331_evaluated_frames_sidecar.py
- tests/platformkit/test_g332_harness_hygiene.py
- tests/platformkit/test_g333_producer_diffs.py
- tests/platformkit/test_g334_court_line_registration.py
- tests/platformkit/test_g336_track_id_continuity.py
- tests/platformkit/test_g338_detector_input_decision.py
- tests/platformkit/test_g339_ball_join.py
- tests/platformkit/test_g340_env_shim.py
- tests/platformkit/test_g341_shot_router.py
- tests/platformkit/test_g342_archive_precision.py
- tests/platformkit/test_g342_court_templates.py
- tests/platformkit/test_g343_attack_test.py
- tests/platformkit/test_g344_ball_shadow_possession.py
- tests/platformkit/test_g345_associate.py
- tests/platformkit/test_g346_footage_census.py
- tests/platformkit/test_g346_footage_liveness.py
- tests/platformkit/test_g347_env_shim_no_regression.py
- tests/platformkit/test_g348_gate_execution.py
- tests/platformkit/test_g349_ball_survival.py
- tests/platformkit/test_g349_input_manifest.py
- tests/platformkit/test_g350_wide_cue_validation.py
- tests/platformkit/test_g351_ball_scale_census.py
- tests/platformkit/test_g352_whole_template_objective.py
- tests/platformkit/test_g353_image_space_gates.py
- tests/platformkit/test_g353_production_translation.py
- tests/platformkit/test_g354_ball_px_fields.py
- tests/platformkit/test_g354_postdeploy_freshness.py
- tests/platformkit/test_g355_shot_router_robustness.py
- tests/platformkit/test_g357_fix1b_census.py
- tests/platformkit/test_g357_px_join.py
- tests/platformkit/test_g358_gate_execution.py
- tests/platformkit/test_g358_production_schema_adapter.py
- tests/platformkit/test_g359_held_position.py
- tests/platformkit/test_g360_court_presence_cue.py
- tests/platformkit/test_g361_source_identity.py
- tests/platformkit/test_g361_strips.py
- tests/platformkit/test_g362_registration_refusal.py
- tests/platformkit/test_g363_ball_coverage.py
- tests/platformkit/test_g364_learned_court_presence.py
- tests/platformkit/test_g365_candidate_b.py
- tests/platformkit/test_g365_fitter_refinement.py
- tests/platformkit/test_g366_gate_confirmation.py
- tests/platformkit/test_g367_init_symmetry.py
- tests/platformkit/test_g368_evaluated_tick_motion.py
- tests/platformkit/test_g369_prospective_identity.py
- tests/platformkit/test_g370_admission_v0.py
- tests/platformkit/test_g371_symmetry_margin.py
- tests/platformkit/test_g372_phase_a.py
- tests/platformkit/test_g372_source_sidecar.py
- tests/platformkit/test_g373_ball_detector_v2.py
- tests/platformkit/test_g374_court_presence_validation.py
- tests/platformkit/test_g375_corpus_sport_purity.py
- tests/platformkit/test_g376_declared_tick_observations.py
- tests/platformkit/test_g377_restore_receipt.py
- tests/platformkit/test_g378_orientation_cue.py
- tests/platformkit/test_g379_broadcast_geometry.py
- tests/platformkit/test_g380_producer_provenance.py
- tests/platformkit/test_g381_memo_digest_census.py
- tests/platformkit/test_g382_court_stroke_specificity.py
- tests/platformkit/test_g384_ball_phase2_receipt.py
- tests/platformkit/test_g385_nonplay_shadow_mask.py
- tests/platformkit/test_g386_pin_copy_one_pass.py
- tests/platformkit/test_g387_paint_localization.py
- tests/platformkit/test_g388_paint_band_protocol.py
- tests/platformkit/test_g389_ball_reference_completion.py
- tests/platformkit/test_g390_ball_a8_sealed_pass.py
- tests/platformkit/test_g391_ball_false_call_audit.py
- tests/platformkit/test_g392_per_rater_paint.py
- tests/platformkit/test_g393_leading_hyphen_game_id.py
- tests/platformkit/test_g394_ball_person_negatives.py
- tests/platformkit/test_g396_third_rater_paint.py
- tests/platformkit/test_g397_mixed_source_producer_census.py
- tests/platformkit/test_g398_a8_high_resolution_dev_shadow.py
- tests/platformkit/test_g399_qualified_paint_larger_sample.py
- tests/platformkit/test_g400_ball_reference_growth.py
- tests/platformkit/test_g401_fps_cap_duration.py
- tests/platformkit/test_g402_mixed_provenance_mask.py
- tests/platformkit/test_g403_ball_rater_controls.py
- tests/platformkit/test_g404_play_gated_growth.py
- tests/platformkit/test_g405_discovery_formats.py
- tests/platformkit/test_g406_target_pixel_audit.py
- tests/platformkit/test_g407_rendition_boundary.py
- tests/platformkit/test_g408_pts_stop_proposal.py
- tests/platformkit/test_g409_box_coordinate_cause.py
- tests/platformkit/test_g410_position_box_frame_consistency.py
- tests/platformkit/test_g411_integer_pts_extent.py
- tests/platformkit/test_g412_box_frame_contract.py
- tests/platformkit/test_g413_native_box_reaudit.py
- tests/platformkit/test_g416_court_point_proposal.py
- tests/platformkit/test_g62_environment_sidecar.py
- tests/platformkit/test_gate_a0_ingame_vs_market.py
- tests/platformkit/test_gate_b_tracking_ablation.py
- tests/platformkit/test_gate_run_mlb_espn_box.py
- tests/platformkit/test_gate_run_nba_possession.py
- tests/platformkit/test_gate_run_soccer_espn28.py
- tests/platformkit/test_gate_run_soccer_statsbomb.py
- tests/platformkit/test_gate_run_tennis_setdetail.py
- tests/platformkit/test_gate_test_asof_return.py
- tests/platformkit/test_gate_test_quarter_shape.py
- tests/platformkit/test_gate_test_xg_proxy.py
- tests/platformkit/test_grade_paper_close.py
- tests/platformkit/test_http_cache_robustness.py
- tests/platformkit/test_improve_ledger_routes.py
- tests/platformkit/test_ingame_boxscore_update.py
- tests/platformkit/test_ingame_brier_soccer.py
- tests/platformkit/test_ingame_compose.py
- tests/platformkit/test_ingame_corpus_suffix_override.py
- tests/platformkit/test_ingame_crossval_nba.py
- tests/platformkit/test_ingame_crps_mlb.py
- tests/platformkit/test_ingame_finegrain_nba.py
- tests/platformkit/test_ingame_gate_generic.py
- tests/platformkit/test_ingame_gate_refresh.py
- tests/platformkit/test_ingame_ladder_mlb.py
- tests/platformkit/test_ingame_ladder_mlb_baseout.py
- tests/platformkit/test_ingame_ladder_nba.py
- tests/platformkit/test_ingame_layer_gate_nba.py
- tests/platformkit/test_ingame_live_loop.py
- tests/platformkit/test_ingame_nba_newsprior.py
- tests/platformkit/test_ingame_nba_winprob.py
- tests/platformkit/test_ingame_pred_tick_runner.py
- tests/platformkit/test_ingame_refresh_runner.py
- tests/platformkit/test_ingame_serve.py
- tests/platformkit/test_ingame_snapshot.py
- tests/platformkit/test_ingame_state.py
- tests/platformkit/test_ingame_wiring.py
- tests/platformkit/test_ingest_manifest.py
- tests/platformkit/test_inplay_aggregate_grade.py
- tests/platformkit/test_inplay_clv_replay.py
- tests/platformkit/test_inplay_espn.py
- tests/platformkit/test_inplay_feed_liquidity.py
- tests/platformkit/test_inplay_history.py
- tests/platformkit/test_inplay_retention.py
- tests/platformkit/test_inplay_snapshot_daemon.py
- tests/platformkit/test_intel_foundry_queue.py
- tests/platformkit/test_intel_pool_asof_census.py
- tests/platformkit/test_io_atomic.py
- tests/platformkit/test_join_rate_floor.py
- tests/platformkit/test_kalshi_book_capture.py
- tests/platformkit/test_ladder_block_predict.py
- tests/platformkit/test_ledger_squash.py
- tests/platformkit/test_line_snapshot_daemon.py
- tests/platformkit/test_line_store.py
- tests/platformkit/test_lines_matrix_routes.py
- tests/platformkit/test_live_grade.py
- tests/platformkit/test_loc_rail_scope.py
- tests/platformkit/test_market_join.py
- tests/platformkit/test_markets.py
- tests/platformkit/test_mcp_http.py
- tests/platformkit/test_mlb_batter_pitcher_line_dist.py
- tests/platformkit/test_mlb_board_uniformity_label.py
- tests/platformkit/test_mlb_parity.py
- tests/platformkit/test_mlb_pregame_gate_eval_honesty.py
- tests/platformkit/test_mlb_states.py
- tests/platformkit/test_nba_travel_gate_run.py
- tests/platformkit/test_new_sport_scaffold.py
- tests/platformkit/test_novel_pitch_repeat_excess.py
- tests/platformkit/test_omni_box_store_refresh.py
- tests/platformkit/test_omni_claim_impact.py
- tests/platformkit/test_omni_claims_backfill.py
- tests/platformkit/test_omni_claims_ledger.py
- tests/platformkit/test_omni_close_lookup.py
- tests/platformkit/test_omni_escalation_intake.py
- tests/platformkit/test_omni_feature_store.py
- tests/platformkit/test_omni_funnel.py
- tests/platformkit/test_omni_k_coverage.py
- tests/platformkit/test_omni_k_minutes_rescore.py
- tests/platformkit/test_omni_k_refresh_job.py
- tests/platformkit/test_omni_k_stage_b.py
- tests/platformkit/test_omni_k_sweep_health.py
- tests/platformkit/test_omni_k_sweep_nba.py
- tests/platformkit/test_omni_k_sweep_opponent.py
- tests/platformkit/test_omni_k_sweep_physical.py
- tests/platformkit/test_omni_k_sweep_playprofile.py
- tests/platformkit/test_omni_k_sweep_synergy.py
- tests/platformkit/test_omni_k_synergy_era_control.py
- tests/platformkit/test_omni_k_synergy_stint.py
- tests/platformkit/test_omni_leak_canary.py
- tests/platformkit/test_omni_lineup_possessions.py
- tests/platformkit/test_omni_native_altitude.py
- tests/platformkit/test_omni_news_knowability.py
- tests/platformkit/test_omni_reject_reaudit.py
- tests/platformkit/test_omni_replay_harness.py
- tests/platformkit/test_omni_signals_orphan_asof.py
- tests/platformkit/test_omni_spine_eval.py
- tests/platformkit/test_omni_spine_nba.py
- tests/platformkit/test_ops_staleness_normalizer.py
- tests/platformkit/test_orphan_hb_check.py
- tests/platformkit/test_p5_api_contract.py
- tests/platformkit/test_parity_matrix.py
- tests/platformkit/test_pm_paper_tick_runner.py
- tests/platformkit/test_pm_trail_browse.py
- tests/platformkit/test_pod_pull_sync.py
- tests/platformkit/test_policy.py
- tests/platformkit/test_polymarket_book_capture.py
- tests/platformkit/test_pool_receiver.py
- tests/platformkit/test_prereg_committed_object_seals.py
- tests/platformkit/test_prop_cards_cache_sla.py
- tests/platformkit/test_prop_game_model.py
- tests/platformkit/test_prop_game_model_matchup.py
- tests/platformkit/test_prop_surface.py
- tests/platformkit/test_proposed_apply.py
- tests/platformkit/test_props_pred_tick_runner.py
- tests/platformkit/test_rb_p0_03_daemon_heartbeats.py
- tests/platformkit/test_realmoney_gate.py
- tests/platformkit/test_realmoney_gate_chaos.py
- tests/platformkit/test_repricer_router.py
- tests/platformkit/test_run_paper_today.py
- tests/platformkit/test_run_paper_today_exec_gate.py
- tests/platformkit/test_s140_loc_rail.py
- tests/platformkit/test_s227_margin_tail_crps.py
- tests/platformkit/test_s229_matchup_player_vs_defender.py
- tests/platformkit/test_s230_pregame_scheme_interaction.py
- tests/platformkit/test_s252_tennis_feed_brief.py
- tests/platformkit/test_s260_mlb_batter_pitcher_line_q4.py
- tests/platformkit/test_s268_distributional_evaluator_route.py
- tests/platformkit/test_s270_ingame_power_feasibility.py
- tests/platformkit/test_s273_mlb_ingame_latency_screen.py
- tests/platformkit/test_s274_mlb_distribution_evaluator_route.py
- tests/platformkit/test_s278_pooled_power_rescreen.py
- tests/platformkit/test_s282_foul_bonus_regime.py
- tests/platformkit/test_s293_tail_metric_rail.py
- tests/platformkit/test_s296_full_boxscore_oof.py
- tests/platformkit/test_s297_minutes_dnp_distribution.py
- tests/platformkit/test_s298_rare_count_mixture.py
- tests/platformkit/test_s308_band_functional_validity.py
- tests/platformkit/test_s309_canonical_loss_audit.py
- tests/platformkit/test_s309_design_evaluators.py
- tests/platformkit/test_s310_tail_beta_offset.py
- tests/platformkit/test_s313_answers_label_survival.py
- tests/platformkit/test_s316_mc_cross_env.py
- tests/platformkit/test_s317_series_schema.py
- tests/platformkit/test_s319_receipt_guard_lf.py
- tests/platformkit/test_s320_state_audit.py
- tests/platformkit/test_s320_state_audit_attempt2.py
- tests/platformkit/test_s322_sim_diagnostics.py
- tests/platformkit/test_s323_adapter_contract.py
- tests/platformkit/test_s327_prestart_m0_controls.py
- tests/platformkit/test_s327_prestart_m0_table.py
- tests/platformkit/test_s328_asof_replay.py
- tests/platformkit/test_s328_run_replay.py
- tests/platformkit/test_scoreboard.py
- tests/platformkit/test_segment_ingame_join_r3.py
- tests/platformkit/test_segment_ingame_join_r3_breaks.py
- tests/platformkit/test_selfimprove_closed_loop.py
- tests/platformkit/test_selfimprove_daemon.py
- tests/platformkit/test_selfimprove_runner_wiring.py
- tests/platformkit/test_settled_finals.py
- tests/platformkit/test_slate_recency_gate.py
- tests/platformkit/test_snapshot.py
- tests/platformkit/test_soccer_intl_parity.py
- tests/platformkit/test_soccer_parity.py
- tests/platformkit/test_soccer_states.py
- tests/platformkit/test_ssac_halflife.py
- tests/platformkit/test_stake_units_normalize.py
- tests/platformkit/test_state_lag_sensitivity.py
- tests/platformkit/test_supervised_runners.py
- tests/platformkit/test_survivor_corners_combo_gate.py
- tests/platformkit/test_tennis_gamestate.py
- tests/platformkit/test_tennis_states.py
- tests/platformkit/test_unattended_readiness_probe.py
- tests/platformkit/test_watchdog_platform.py
- tests/platformkit/test_winprob_feature_challenger.py
- tests/platformkit/test_wp_diagnostics_edges.py
- tests/platformkit/tip_capture/test_daemon.py
- tests/platformkit/tip_capture/test_feature_gate_runner.py
- tests/platformkit/tip_capture/test_ingame_capture.py
- tests/platformkit/tip_capture/test_ingame_features.py
- tests/platformkit/tracking/test_g304_adjudication2.py
- tests/platformkit/tracking/test_g304_proposals.py
- tests/platformkit/tracking/test_g321_semantic_gate.py
- tests/platformkit/tracking/test_g44b_label_ground_truth.py
- tests/platformkit/tracking/test_public_figures_check.py
- tests/platformkit/tracking/test_tennis_calib_eval.py
- tests/platformkit/venue_history/test_nba_wallclock_join_loc.py
- tests/platformkit/venue_history/test_nba_wallclock_join_provenance.py
- tests/platformkit/venue_history/test_nba_wallclock_join_tolerance.py
