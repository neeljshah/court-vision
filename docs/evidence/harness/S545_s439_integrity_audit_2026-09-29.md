# S545 -- read-only integrity audit of sealed S439 night outputs (build memo, 2026-09-29)

Spec: docs/evidence/tracking/specs/S545_spec.md including AMENDMENT 1 (PRE-BUILD) and AMENDMENT 2 (FIX r1). Worktree nba-harness-h212, base f23706d3ae8b208779df8b9d0396e8c30477712b.
Calibration language only: the audit re-derives sealed Brier / log-loss cells and counts rows; it states no market-beating result.

## BINDING BEFORE-CONDITION (re-run this session, docs/ only)

probe2 (scratchpad s545/probe2.py, landed _summary / _ages over the committed docs/evidence/forward/scoreboard/2026-09-24.json):

```
RSS after import MB 78
cells recomputed equal 48 not equal 0 of 48
ticks 1991 paired rows per target 1991 1991
RSS end MB 94
```

The state-shard probes (probe1 / probe1b / probe3) read data/ and were NOT re-run by this builder (the orchestrator runs the real audit after
landing). Case (8) re-derives the docs-only part through the new CLI: 1991 ticks, 4 games, 48 of 48 sealed cells equal, paired 1966 per target,
missing:B_lag 25 per target, receipt age <= 15 s on 498 and > 15 s on 1493 of 1991 outcome rows -- all equal to the spec.

## CHANGE items built

1. INPUTS: s439_integrity_audit_io.py -- strict night read (duplicate keys, NaN / Infinity tokens refuse, parse_float Decimal), required keys,
   settlement / amendment optional; as_of bound per AMENDMENT 1 item 5 (one RAN scoreboard step, artifacts[0].sha256 == night LF sha256,
   exactly one --as-of equal to the record as_of, record date == night date; else record_mismatch); state shards = sources with
   parent.name == sport and parent.parent.name == 'state'; only the recorded `bytes` prefix is hashed and parsed (source_changed on a
   shorter file or a different prefix; appended bytes pass); 'unavailable' sources counted and skipped; RSS checked every 10,000 lines
   (rss_cap past 400 MB); per game the landed _receipts(rows, response_end_utc, request_start_utc, as_of_us, Counter()) is the sequence.
2. TERMINAL CENSUS + POST_FINAL (s439_integrity_audit.census): MLB frozen whole inner-state dict, T_change closed below / first_final open
   above, status 'live' required; NBA / WNBA period >= 4, rules _number(clock_sec) == 0, margin != 0; no_final_receipt /
   no_live_before_final / not_defined labels; POST_FINAL = any tick at or after first_final, never terminal; per-sport counts by segment
   and arm; gap_us; frozen fields; sealed close_ts vs first_final EQUAL / NOT EQUAL; 8-field key re-check (frozen_key_differences).
3. PAIRED INTERSECTION: present arms per sport-target, missing:<first missing present arm> exclusions, paired / without-terminal /
   fresh (<= 15000000 us) / stale splits through the landed _summary; absent arms listed with the count of THIS sport's ticks whose arm is
   null (AMENDMENT 2 (a); the night-level counts are summed over sports and were mis-scoped on multi-sport nights).
4. RECONCILIATION (AMENDMENT 1 item 4): cell_set, cell_recompute (landed _json, active = arm_order), n_ticks_identity (present and
   absent arms), paired_split_identity (terminal_n counted directly from the paired rows flagged terminal, AMENDMENT 2 (b)), rows_vs_ticks (join on sport, game_key, whole-us ts; orphan or duplicate refuses night_row_invalid),
   arm_null_vs_counts (absent counts key reads 0). RECONCILE_FAILED writes the report and exits 3; any refusal exits 2 and writes nothing.
5. CLI --night --night-record --out-dir (no --as-of, no --test-root); <D>.json strict then <D>.md rendered from the written JSON, both via
   tempfile + fsync + ops/atomic_replace.replace_with_retry; out-dir = exactly docs/evidence/forward/model2/s439_audit or outside the repo;
   scoreboard/, any 'data' part, or an input refuses output_path_refused.
   Non-state sources (books, seal, schedule) are listed with their recorded sha only (`not_read`): the audit derives nothing from them, and
   hashing a 300 MB books shard costs about 300 MB of disk reading per shard.
7. AMENDMENT 2 (c): a shard row with an unhashable game_key is counted receipt_refused (as the scorer's _capture does); a paired row with B
   and C losses but a null contrast, and a sealed cell missing brier or logloss (or any of n_ticks / n_games / mean / ci95 / verdict), refuse
   night_row_invalid (exit 2, nothing written) instead of a traceback.
6. MUST NOT EDIT: no item-6 file edited (table below recomputed from disk as the last step).

## Case inventory (generated from the test files)

cases enumerated: 16 (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16); bar 16 of 16. Plus 13 AMENDMENT 2 (d) guard cases (g01-g13).
- tests/platformkit/ingame/test_s439_integrity_audit.py: test_case2_frozen_one_us_before_final_and_state_change, test_case3_live_at_final_instant_after_final_is_duplicate, test_case4_live_before_final_at_same_instant, test_case5_tick_at_t_change_is_terminal_one_us_earlier_not, test_case6_nba_wnba_and_post_final, test_case7_paired_intersection, test_case9_receipt_age_boundary_and_invalid_ages, test_case10_strict_night_refusals, test_case11_source_prefix, test_case12_out_dir_refusals, test_case13_settlement_shape_and_close_vs_first_final, test_case14_record_mismatch, test_case15_md_regenerates_byte_identically
- tests/platformkit/ingame/test_s439_integrity_audit_e2e.py: test_case1_e2e_real_rows_through_landed_producer, test_case8_committed_night_and_tamper_mutants, test_case16_must_not_move_at_landing
- tests/platformkit/ingame/test_s439_integrity_audit_guards.py: test_g01_mlb_terminal_needs_live_pre_blip_excluded, test_g02_c_minus_b_absent_when_c_absent, test_g03_as_of_value_mismatch, test_g04_record_date_mismatch, test_g05_partial_line_inside_recorded_prefix, test_g06_arm_null_vs_counts_mismatch_exits_3, test_g07_duplicate_tick_join_key, test_g08_duplicate_paired_join_key, test_g09_mlb_live_after_final_is_post_final_t_change_unchanged, test_g10_rss_guard, test_g11_cell_set, test_g12_absent_counts_per_sport, test_g13_malformed_rows_named

Case (1) exact tick count re-derived from the landed producer: 5 ticks, all late (equals the spec).

## Fixture provenance (byte-exact, streamed, RSS-capped; copied from the main checkout)

- fixtures/s545/state/mlb/2026-09-25.jsonl: source data/cache/ingame_capture_view_v2/state/mlb/2026-09-25.jsonl lines 3128, 3133, 3154, 3160, 3165, 3186 (as named, all matched the description); 6078 bytes; sha256 5e1b065201cdb36e542a987b996824ed982ad07241bda5d39edb186b610bb244
- fixtures/s545/kalshi/mlb/2026-09-25.jsonl: source data/cache/ingame_capture_view_v2/kalshi/mlb/2026-09-25.jsonl lines 35439, 43106 (as named, all matched the description); 5738 bytes; sha256 ae1c362ec79a6898e95470a48e67fa3eb5b5e430fd6ba8ffc7a36a793ce465aa
- fixtures/s545/must_not_move.json: generated from disk at build time; every hash equals the spec value.
- The 824866 schedule object is read at test time from the committed docs/evidence/forward/schedules/2026-09-24_maker_forward.json.
- The state fixture carries raw minute fields that the preflight vocabulary scanner flags; per the Q6 NOTE (verbatim data) and the S510
  precedent the two verbatim .jsonl fixtures are excluded from the preflight --paths (they cannot change without breaking byte-exactness).

.gitattributes (+3, appended): docs/evidence/forward/model2/s439_audit/*.json, docs/evidence/forward/model2/s439_audit/*.md,
tests/platformkit/ingame/fixtures/s545/** -- each text eol=lf.

## Mandatory disclosures

(a) The MLB terminal set is an UPPER bound on post-last-out ticks: when the feed freezes at 2 outs (823411, 824707) ticks between the true
    final out and the last state change are indistinguishable.
(b) Receipt age is ours (state receipt minus used book receipt), not the venue's staleness.
(c) max(finals) moves only the reported close_ts (EQUAL / NOT EQUAL is printed per game).
(d) No NBA / WNBA live row exists yet; WNBA is unscorable under the sealed segment() (regulation_unavailable).
(e) 09-24 has 4 games: every cell verdict is INSUFFICIENT.
(f) POST_FINAL counts are reported per night, per sport and game, by segment and by arm (the real 09-24 counts come from the orchestrator run).
    paired-without-terminal keeps POST_FINAL rows; POST_FINAL is reported as its own class.
(g) A single sparse fitted arm shrinks the paired intersection; the missing:<arm> counts are quoted per sport-target (09-24: missing:B_lag 25).
(h) Whole-dict frozen-state equality is re-checked against the 8-field key on each audited night (frozen_key_differences per sport).
(i) The E2E depends on ingame_scoreboard.POLICY matching PREREG_2026-09-24.json; a later POLICY edit must update this test in the same row.
    A later S439 rules re-seal (e.g. S492 commit B) may also require updating the E2E expected numbers in the same row.

## Must-not-move (LF sha256 recomputed from disk as the last step; case 16 runs only under S545_LANDING=1)

- docs/evidence/forward/scoreboard/2026-09-24.json: 2f8a2a7d6b4c2d80466520ccce4e3442fe22cbff57039450acf94e82d959ef06 (EQUAL to must_not_move.json)
- scripts/platformkit/eval_gate/walkforward.py: 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9 (EQUAL to must_not_move.json)
- scripts/platformkit/execution/ingame_scoreboard.py: 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6 (EQUAL to must_not_move.json)
- scripts/platformkit/execution/ingame_scoreboard_night.py: 8a34c4f4fca9f0c4395f8256d97603797d717d744e65df2e656f897a6645da24 (EQUAL to must_not_move.json)
- scripts/platformkit/execution/ingame_scoreboard_rules.py: 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351 (EQUAL to must_not_move.json)
- scripts/platformkit/ingame/baseline_four_arm.py: dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2 (EQUAL to must_not_move.json)
- scripts/platformkit/ingame/baseline_four_arm_eligibility.py: d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032 (EQUAL to must_not_move.json)
- scripts/platformkit/ingame/baseline_four_arm_features.py: 8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade (EQUAL to must_not_move.json)
- scripts/platformkit/ingame/baseline_four_arm_period.py: 1fb9aa085c33c858a61884160706d4292ab70768500c777879b81c9d1f659791 (EQUAL to must_not_move.json)

## Test and gate results

```
tests/platformkit/ingame/test_s439_integrity_audit.py: 13 passed in 2.89s
tests/platformkit/ingame/test_s439_integrity_audit_e2e.py: 2 passed, 1 skipped in 6.90s
S545_LANDING=1 case16: 1 passed (hand run)
python -m scripts.platformkit.ingame.s439_integrity_audit --help: exit 0
contract_preflight (code, tests, must_not_move.json, .gitattributes, memo): see final line below
0 FAIL
```

LOC: scripts/platformkit/ingame/s439_integrity_audit.py 269; scripts/platformkit/ingame/s439_integrity_audit_io.py 213; tests/platformkit/ingame/test_s439_integrity_audit.py 281; tests/platformkit/ingame/test_s439_integrity_audit_e2e.py 116; tests/platformkit/ingame/test_s439_integrity_audit_guards.py 142

## Mutation re-run after FIX r1 (AMENDMENT 2 (d); orchestrator-generated from vscratch_fix_s545/summary.txt)

Harness: the adversarial tier's mut.py over all three test files, 45 mutants incl. the no-op; 36 KILLED, 9 SURVIVED.

| mutant | result | note |
|---|---|---|
| M01_tchange_lt | KILLED |  |
| M02_postfinal_gt | SURVIVED | equivalent: no tick can sit exactly at the first final instant |
| M03_term_ignores_post | KILLED |  |
| M04_mlb_no_live_check | KILLED |  |
| M05_present_identity_true | SURVIVED | redundant with cell_recompute |
| M06_absent_identity_true | SURVIVED | redundant with cell_recompute |
| M07_cmb_present_B_only | KILLED |  |
| M08_has_cmb_from_B | KILLED |  |
| M09_asof_value_unchecked | KILLED |  |
| M10_artifact_sha_unchecked | KILLED |  |
| M11_prefix_not_truncated | KILLED |  |
| M12_short_file_ok | SURVIVED | unreachable: a shorter file cannot match the recorded prefix sha |
| M13_outdir_data_ok | KILLED |  |
| M14_outdir_scoreboard_ok | KILLED |  |
| M15_outdir_inrepo_ok | KILLED |  |
| M16_loss_via_float | KILLED |  |
| M17_loss_type_unchecked | SURVIVED | round-1 equivalent/unreachable class |
| M18_nba_clock_raw | KILLED |  |
| M19_nba_margin_any | KILLED |  |
| M20_nba_period5 | KILLED |  |
| M21_tchange_last_only | KILLED |  |
| M22_no_cell_recompute | KILLED |  |
| M23_no_rows_vs_ticks | KILLED |  |
| M24_no_arm_null_counts | KILLED |  |
| M25_fresh_lt | KILLED |  |
| M26_rss_never | KILLED |  |
| M27_partial_line_raises | KILLED |  |
| M28_outdir_input_ok | KILLED |  |
| M29_dup_tick_ok | KILLED |  |
| M30_dup_row_ok | KILLED |  |
| M31_lives_after_final | KILLED |  |
| M32_first_final_is_last | KILLED |  |
| M33_mid_age_bool_ok | KILLED |  |
| M34_status_always_reconciled | KILLED |  |
| M35_seg_mismatch_ok | SURVIVED | round-1 equivalent/unreachable class |
| M36_record_date_unchecked | KILLED |  |
| M37_state_parent_any | SURVIVED | round-1 equivalent/unreachable class |
| M38_ran_unchecked | KILLED |  |
| M39_cellset_unchecked | KILLED |  |
| M40_split_identity_zero | KILLED |  |
| M00_noop | SURVIVED | no-op control |
| M41_absent_cross_sport | KILLED |  |
| M42_contrast_null_ok | KILLED |  |
| M43_cell_shape_unchecked | SURVIVED | TEST GAP (follow-up): a sealed cell missing brier/logloss is unreachable from the landed scorer; the refusal exists in code but no test isolates it |
| M44_unhashable_escapes | KILLED |  |

## NOT VERIFIED

- The real audits (09-24 now, 09-30 onward) were not run by the builder; the probe1 numbers (terminal 9 all late, gaps 62 / 67 / 63 / 26 s,
  sha_equal on both shards) are reproduced only when the orchestrator runs the CLI on the real night after landing.
- The rss_cap refusal is tested only with a sampler double over the cap (g10); a real 300 MB shard stream was not exercised (constructs are a few KB).
- Top-level `contrasts` are not re-derived (only the cells are reconciled).
- Per-row loss vs `y` vs tick outcome are not cross-checked (outside this row's scope; a follow-up row if the fitted nights need it).
- Tennis-scale served nights may refuse rss_cap (all served state rows of a sport are held at once; the 09-29 tennis shard is 1.1 GB).
- Case 16 was run once by hand with S545_LANDING=1 (passed); by default it skips.
- No NBA / WNBA real live row exists, so the NBA terminal rule is exercised on constructs only.
- A game whose settlement census row exists but whose ticks are absent uses the settlement close_ts; no construct covers that fallback.
- Real-run .md / .json outputs quote raw timestamps; the preflight vocabulary scanner may flag minute fields in them (verbatim data).
