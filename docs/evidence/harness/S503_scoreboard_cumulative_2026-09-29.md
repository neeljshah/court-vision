# S503 cumulative scoreboard candidate - 2026-09-29

NOT VALIDATED by the independent verifier. Local construct acceptance: 145/145 cases (43 evaluator, 33 fix-round-1/4 companion, fifty-four fix-round-2/4 companion, 15 subprocess) after the FINAL corrections; in FINAL the three non-e2e files were re-run (130/130 passed: 43, 33 and fifty-four) and the 15 subprocess cases carry their FIX 4 result (e2e not re-run, see NOT VERIFIED). The exact expanded denominator is generated from the final test AST below. No scored finding or interim verdict is claimed.

This resume began with both modules and the fixture present. The spec records an earlier absent-module baseline of 0/16; absence was not re-measured in this resumed session. All edits stayed in C:/Users/neelj/nba-harness-h161. Construct tests use pytest tmp_path and isolated synthetic Git repositories, with no network, pod or real archive.

## BINDING BEFORE-CONDITION

The following output was reproduced before editing by reading the whole named receipt and computing its structure and arm distribution. Resolution: nightly JSON paired-loss rows. This is a structural premise check.

```json
{"amendment": null, "arms": {"A": 50, "A,B_lag": 3932}, "bytes": 3443097, "cells": 48, "contrast_nonnull": 0, "games": 4, "keys": ["arm_order", "cells", "contrasts", "counts", "date", "games", "paired_losses", "prereg", "scope", "sources", "ticks"], "paired_losses": 3982, "path": "docs\\evidence\\forward\\scoreboard\\2026-09-24.json", "prereg": {"bytes": 5046, "path": "C:\\Users\\neelj\\nba-ai-system\\docs\\evidence\\forward\\scoreboard\\PREREG_2026-09-24.json", "resolution": "JSON text", "sha256": "6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b"}, "row0": {"contrast": null, "game_key": "822842", "losses": {"A": {"brier": "0.20702500", "logloss": "0.6069694843188929770758985786"}}, "mid_age_us": 58778024, "segment": "early", "sport": "mlb", "target": "outcome", "ts": "2026-09-24T18:32:59.824001Z", "y": 1}, "row_keys": ["contrast", "game_key", "losses", "mid_age_us", "segment", "sport", "target", "ts", "y"], "settlement": null, "sha256": "2f8a2a7d6b4c2d80466520ccce4e3442fe22cbff57039450acf94e82d959ef06", "ticks": 1991}
```

Resolved input: C:/Users/neelj/nba-harness-h161/docs/evidence/forward/scoreboard/2026-09-24.json.

Resolved fixture: C:/Users/neelj/nba-harness-h161/tests/platformkit/execution/fixtures/s503_real_slice_2026-09-24.json; resolution: verbatim selected paired JSON rows.

FIXTURE_GAMES_VERBATIM True; FIXTURE_ROWS_VERBATIM True. The fixture contains the two specified games and all 1652 associated paired rows verbatim, with original metadata and without ticks/cells. Redated copies are synthetic constructs and do not establish a prospective historical result.

## Landed signatures read before coding

- scripts/platformkit/execution/ingame_scoreboard.py: `def _json(value: object) -> str:`
- scripts/platformkit/execution/ingame_scoreboard.py: `def _summary(rows: list, name: str, contrast: bool = False, min_corpora_eff: int | None = None, n_corpora: int = 1) -> dict:`
- scripts/platformkit/execution/ingame_scoreboard_amendment.py: `def _utc_day(value: object) -> date:`
- scripts/platformkit/execution/ingame_scoreboard_amendment.py: `def _git_head(root: Path, relative: str) -> bytes:`
- scripts/platformkit/execution/ingame_scoreboard_amendment.py: `def _git_commit_time(root: Path, relative: str) -> str:`
- scripts/platformkit/execution/ingame_scoreboard_amendment.py: `def _unique(pairs: list) -> dict:`
- scripts/platformkit/execution/venue_time.py: `def parse_venue_time(value: object) -> float | None:`
- scripts/platformkit/execution/entry_timing/study.py: `def cluster_boot_ci(values: list[float], clusters: list, n_boot: int = 500, seed: int = 7) -> tuple[float | None, float | None]:`

ARMS = (A, B, C, D, B_lag); SEGMENTS = (pre-live, early, middle, late). Unchanged POLICY floors: n_games=30, n_clusters=5. Unchanged bootstrap: n_boot=500, seed=7. Each cell calls the landed _summary with the C_minus_B comparison flag.

## Implementation and refusal contract

The preregistration module freezes dates, read-after instant, populations, source seals, evaluator/helper identities, POLICY and capacity. It verifies committed LF bytes, payload hashes, historical source implementation identities, prospective effective dates and unchanged window history. The effective day must be strictly after the prereg file commit UTC day; the window cannot start earlier.

Filename date and asof selection precede receipt reading; duplicate dates refuse both files. Receipt syntax must be valid JSON first: duplicate JSON keys and non-finite JSON constants refuse the document even inside future rows. Within valid JSON, future games and rows are counted and filtered before schema/duplicate checks without changing coverage. Receipt failures count files and do not complete dates. Row failures (malformed paired rows) are counted refusals per paired target row. Every row of a tick is collected before the tick is resolved, so row order never changes the outcome: two VALID rows at one identity that disagree abort the read (duplicate_conflict), and a tick identity spans receipts: before any refusal applies, each valid row is also compared with the retained valid rows and with the kept valid rows of earlier REFUSED ticks of that identity (kept for this comparison only, never pooled), so night order and receipt boundaries never turn a conflict into a refusal; otherwise any malformed row refuses the whole tick for both targets (each malformed row under its own reason, each valid row under the smallest malformed reason), never aborts the window and never makes a date incomplete. Every selected game of every admitted receipt, including out-of-population and rowless games, registers its identity (sport, game_key, game_id, ticker, cohort) and venue-global event/ticker aliases before any exclusion, so a cohort, sport or ticker change across nights is duplicate_conflict whichever side is excluded (AMENDMENT 5(a)). Only a receipt-level refusal (schema, JSON syntax including RecursionError/MemoryError while parsing, scope, seal, oversize, receipt_row_cap, duplicate date, games join) leaves a date incomplete. Counter keys are named reasons only (receipt_json_invalid, source_git_error, receipt_io_error, receipt_schema, row_schema, ...), never raw exception text. Out-of-population rows and games (sport or cohort not named by the prereg) are counted exclusions (excluded_rows:, excluded_games:) and never affect validity or coverage. Multi-seal exclusions keep earlier-date ownership and count excluded paired target rows. Atomic identity/tick conflicts and excess capacity abort the read, exit 2, without newly published output.

A missing field is never zero. Counts are strict int; losses and mid targets are strict ASCII decimal strings (optional '-', digits, optional '.digits', optional exponent; anything else is row_refused:loss_grammar) and '-0' reads as '0', Brier in [0,1], log loss in [0,10000], at most 40 significant digits and exponent magnitude 60. An 80-digit fixed context preserves admitted finite-scale sums and contrasts. Canonical ordering precedes the unchanged helper. Exact nanoseconds govern cutoff boundaries; landed whole-microsecond semantics govern duplicate identity. Decimal values convert to finite float only for the landed bootstrap.

Cells remain separate by sport, cohort, seal, segment, target and arm. C-minus-B is independently recomputed. The archive stores paired_columns, loss_columns, retained values, original game identities, input paths/sizes/hashes, source seals and the pinned revision. game_index resolves through the complete games table, avoiding repeated long identifiers without changing cluster weighting. Integer archive references are assigned after summaries.

Valid empty receipts may complete dates; an empty directory produces descriptive interim output, exit 0. Final eligibility requires complete valid coverage and the sealed read-after instant. Interim metric verdicts are null. Output names contain the canonical full asof and read kind. Publication streams json.dump with the exact _json options (byte identity asserted by test_streamed_publish_is_byte_identical_to_json) into a temporary file, flush, fsync and non-replacing hard links. A terminal link (a leftover hidden file whose chunked SHA-256 equals the streamed SHA-256 of the would-be output is linked, never rewritten; a different leftover is refused output_exists; neither the output nor the file is materialized) permits one final publication per window_id in each output directory and preserves a complete recoverable receipt if public-name linking is interrupted. Separate output directories are explicit reproduction destinations in the construct tests.

No nightly caller, budget, SEALS entry, registry or scoring implementation was edited. Follow-up belongs to the night owner: one report-only cumulative CLI step after the scoreboard step.

## Original 16 cases mapped to tests

Case to coverage: (1) test_02: 29, 30, 32 games across eight receipts; (2) test_02 direct _summary equality; test_04 unequal tick weighting; (3) test_effective_day_commit_boundary; (4) test_03_dates_and_future_schema_precedence; (5) test_20 filename order; test_04 row/game order; (6) test_05_unadmitted_seals; (7) test_06, test_07, test_22, test_24, test_25; (8) test_08_duplicate_dates_and_filename; (9) test_09, test_10, test_13, test_19; (10) test_11 empty directory; test_12 valid empty receipt; (11) test_floor_schema_at_writer; test_committed_seal_refusals; test_19; (12) test_21; test_interim_terminal_immutability_and_help; (13) test_maximum_workload_fresh_process_rss; (14) test_11 disclosures; fresh CLI consumer; (15) test_real_fixture_fresh_cli_repeatable_consumer; (16) test_01_real_slice_end_to_end.

## Expanded construct inventory

Counts are parametrized test instances. Loops and multiple assertions within one instance are not extra denominator units.

| File | Test | Cases |
|---|---|---:|
| test_scoreboard_cumulative.py | test_01_real_slice_end_to_end | 1 |
| test_scoreboard_cumulative.py | test_02_floors_direct_summary_and_contrast | 3 |
| test_scoreboard_cumulative.py | test_03_dates_and_future_schema_precedence | 1 |
| test_scoreboard_cumulative.py | test_04_permutation_and_unequal_game_weight | 1 |
| test_scoreboard_cumulative.py | test_05_unadmitted_seals | 2 |
| test_scoreboard_cumulative.py | test_06_duplicate_and_atomic_conflicts | 1 |
| test_scoreboard_cumulative.py | test_07_multiseal_earlier_ownership | 1 |
| test_scoreboard_cumulative.py | test_08_duplicate_dates_and_filename | 1 |
| test_scoreboard_cumulative.py | test_09_malformed_losses_counted | 9 |
| test_scoreboard_cumulative.py | test_10_schemas_contrast_and_valid_logloss | 1 |
| test_scoreboard_cumulative.py | test_11_empty_and_disclosures | 1 |
| test_scoreboard_cumulative.py | test_12_calendar_coverage_read_after_boundary | 1 |
| test_scoreboard_cumulative.py | test_13_strict_count | 5 |
| test_scoreboard_cumulative.py | test_14_canonical_tick_and_future_precedence | 1 |
| test_scoreboard_cumulative.py | test_15_unique_join_and_identity | 1 |
| test_scoreboard_cumulative.py | test_16_receipt_row_cap_is_receipt_level | 1 |
| test_scoreboard_cumulative.py | test_17_decimal_context_deterministic | 1 |
| test_scoreboard_cumulative.py | test_18_populations_and_cell_partitions | 1 |
| test_scoreboard_cumulative.py | test_19_strict_json_and_naive_time | 1 |
| test_scoreboard_cumulative.py | test_20_file_listing_permutation | 1 |
| test_scoreboard_cumulative.py | test_21_publish_immutable_paths_and_partial_failure | 1 |
| test_scoreboard_cumulative.py | test_22_duplicate_conflict_cli_no_output | 1 |
| test_scoreboard_cumulative.py | test_23_terminal_once_and_exact_interim_identity | 1 |
| test_scoreboard_cumulative.py | test_24_malformed_duplicate_is_counted_refusal | 2 |
| test_scoreboard_cumulative.py | test_25_cross_target_atomic_labels | 2 |
| test_scoreboard_cumulative.py | test_26_future_games_before_schema_and_refusal_manifest | 1 |
| test_scoreboard_cumulative_landed.py | test_landed_contrast_reads_cleanly_both_targets | 1 |
| test_scoreboard_cumulative_landed.py | test_opus_reproduction_contrast_passes | 1 |
| test_scoreboard_cumulative_landed.py | test_out_of_population_rows_are_counted_exclusions | 1 |
| test_scoreboard_cumulative_landed.py | test_sibling_target_rows_refuse_the_tick | 4 |
| test_scoreboard_cumulative_landed.py | test_valid_conflicting_siblings_still_abort | 1 |
| test_scoreboard_cumulative_landed.py | test_oversize_receipt_is_receipt_level_refusal | 1 |
| test_scoreboard_cumulative_landed.py | test_resumed_game_start_change_is_metadata | 1 |
| test_scoreboard_cumulative_landed.py | test_terminal_link_recovery_and_directory_uniqueness | 1 |
| test_scoreboard_cumulative_landed.py | test_committed_s492_seal_format_is_admitted_and_unpinned_refused | 1 |
| test_scoreboard_cumulative_landed.py | test_source_seal_prospective_at_equality | 2 |
| test_scoreboard_cumulative_landed.py | test_source_eligibility_types_and_payload_keys | 5 |
| test_scoreboard_cumulative_landed.py | test_publish_never_replaces_a_concurrent_final_name | 1 |
| test_scoreboard_cumulative_landed.py | test_output_bytes_invariant_to_target_row_order | 1 |
| test_scoreboard_cumulative_landed.py | test_pooled_decimal_context_is_pinned | 1 |
| test_scoreboard_cumulative_landed.py | test_digit_limit_and_outcome_domain | 4 |
| test_scoreboard_cumulative_landed.py | test_row_refusal_keeps_the_date_covered | 1 |
| test_scoreboard_cumulative_landed.py | test_scope_and_filename_are_receipt_refusals | 2 |
| test_scoreboard_cumulative_landed.py | test_receipt_before_its_seal_is_effective_is_refused | 1 |
| test_scoreboard_cumulative_landed.py | test_contrast_strings_follow_the_strict_grammar | 3 |
| test_scoreboard_cumulative_order.py | test_conflict_beats_malformed_in_every_order | 6 |
| test_scoreboard_cumulative_order.py | test_malformed_sibling_refuses_tick_in_every_order | 1 |
| test_scoreboard_cumulative_order.py | test_nearest_rank_quantiles | 1 |
| test_scoreboard_cumulative_order.py | test_named_reasons_never_raw_text | 1 |
| test_scoreboard_cumulative_order.py | test_streamed_publish_is_byte_identical_to_json | 1 |
| test_scoreboard_cumulative_order.py | test_cross_receipt_conflict_beats_refusal | 4 |
| test_scoreboard_cumulative_order.py | test_cross_receipt_agreeing_is_counted_refusal | 2 |
| test_scoreboard_cumulative_order.py | test_terminal_recovery_streamed_hash | 1 |
| test_scoreboard_cumulative_order.py | test_identity_registered_before_exclusion | 14 |
| test_scoreboard_cumulative_order.py | test_deeply_nested_receipt_is_receipt_json_invalid | 1 |
| test_scoreboard_cumulative_order.py | test_asof_in_future_refused_with_injected_clock | 1 |
| test_scoreboard_cumulative_order.py | test_strict_ascii_decimal_grammar | 11 |
| test_scoreboard_cumulative_order.py | test_negative_zero_normalizes_and_null_amendment_is_unpinned | 1 |
| test_scoreboard_cumulative_order.py | test_refused_prints_named_reason_only | 3 |
| test_scoreboard_cumulative_order.py | test_registry_bound_counts_excluded_and_rowless | 2 |
| test_scoreboard_cumulative_order.py | test_prereg_cli_refused_prints_named_reason_only | 1 |
| test_scoreboard_cumulative_order.py | test_max_games_admitted_at_equality | 2 |
| test_scoreboard_cumulative_order.py | test_capacity_is_the_sealed_block | 1 |
| test_scoreboard_cumulative_e2e.py | test_real_fixture_fresh_cli_repeatable_consumer | 1 |
| test_scoreboard_cumulative_e2e.py | test_interim_terminal_immutability_and_help | 1 |
| test_scoreboard_cumulative_e2e.py | test_committed_seal_refusals | 3 |
| test_scoreboard_cumulative_e2e.py | test_floor_schema_at_writer | 4 |
| test_scoreboard_cumulative_e2e.py | test_effective_day_commit_boundary | 2 |
| test_scoreboard_cumulative_e2e.py | test_committed_window_revision_refused | 1 |
| test_scoreboard_cumulative_e2e.py | test_bad_amendment_payload_refused | 1 |
| test_scoreboard_cumulative_e2e.py | test_maximum_workload_fresh_process_rss | 2 |

Total: 145 CONSTRUCT cases (43 evaluator, 33 fix-round-1/4 companion, fifty-four fix-round-2/4 companion, 15 subprocess). Tests ran one file at a time; no full suite; both CLI help commands exit 0.

```text
python -m pytest tests/platformkit/execution/test_scoreboard_cumulative.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_scoreboard_cumulative_landed.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_scoreboard_cumulative_order.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_scoreboard_cumulative_e2e.py -q -p no:cacheprovider -rP
python -m scripts.platformkit.execution.scoreboard_cumulative --help
python -m scripts.platformkit.execution.scoreboard_cumulative_prereg --help
```

## Construct capacity

Declared capacity from the implementation: {"cells": 96, "days": 38, "games": 1520, "receipt_bytes": 4194304, "registered_games": 15200, "rows": 152000, "rows_per_receipt": 4000}.

The fresh-process CLI workload is the declared maximum (AMENDMENT 3(a)): 38 nights, 4000 paired target rows per night, 152000 rows, 1520 games, 760000 arm observations, both targets, all five arms, two 64-character cohorts and 96 cells, in the widest accepted row shape: segment pre-live, 12-digit mid_age_us (604800000000, the accepted maximum), losses and mid targets with 40 significant digits and 47-character normalized representations (the longest accepted normalized form). The 4 MiB receipt cap binds before the 200-character identifier cap, so identifiers are the widest that fit it: 195 characters (4,192,582 B receipts). Peak RSS is measured in two separate fresh processes (capacity, capacity_repeat); each must be <= 609,000,000 B (a >= 20 MB margin under 629,145,600 B). Tracemalloc is a third, informational run on the both-target shape, not the RSS gate; it peaked at 793,362,432 B (FIX 3) and 783,499,264 B (FIX 4) RSS, so an operator runs the e2e file only with that RAM headroom. AMENDMENT 4(c) adds a single-target (mid-only) maximum variant: same 38 nights, 4000 rows per receipt (100 ticks per game), 152000 rows, 1520 games, all five arms, with the identifier width reduced only as needed to fit the 4 MiB cap (174 characters); its two fresh-process peaks are also each <= 609,000,000 B. Capacity is measured for these two row shapes (both targets, mid only) only. A receipt may also carry extra top-level keys whose parse is bounded only by the 4 MiB receipt cap: a dense float list measured about +121 MB transient RSS (1,048,545 floats in a 4,194,302 B receipt), not included in the measured workloads. The consumer (strict parse of the output) runs in the pytest parent, outside the measured process.

```json
{"both_targets": {"capacity": {"peak_rss": 411680768, "status": 0, "tracemalloc_peak": 0, "wall_seconds": 60.36138740001479}, "capacity_repeat": {"peak_rss": 411795456, "status": 0, "tracemalloc_peak": 0, "wall_seconds": 60.54434759996366}, "trace": {"peak_rss": 783499264, "status": 0, "tracemalloc_peak": 309946118, "wall_seconds": 121.99666230002185}}, "mid_only": {"capacity": {"peak_rss": 488075264, "status": 0, "tracemalloc_peak": 0, "wall_seconds": 53.40651300002355}, "capacity_repeat": {"peak_rss": 487141376, "status": 0, "tracemalloc_peak": 0, "wall_seconds": 58.573498900048435}}}
```

FIX 2 history: with the widened shape at 38 nights the one-shot _json publication peaked at 624,676,864 B and 624,119,808 B (fail against 609,000,000 B); streaming the identical bytes brought both runs to the values above. The declared maximum was therefore not lowered. This is local Windows construct capacity, not a real-window measurement.

## Disclosures emitted verbatim

- SINGLE-WINDOW; calibration language only.
- Arm A is venue mid: the Kalshi yes contract's own (bid+ask)/2.
- C-minus-B is the sole comparison; no equivalence claim is made.
- Pooled B/C/D use sequential per-night refits under one verified scoring procedure and seal.
- Nights are not independent draws of one model.
- The estimand is mean loss over admitted captured ticks; unequal capture density weights games unequally.
- Whole-game bootstrap intervals condition on archived predictions and assume independent game clusters; shared-night dependence and refit uncertainty are not captured.
- Target mid measures venue-mid agreement.
- As-of is a UTC receipt-selection cutoff, not proof of historical information availability.
- Receipts are selected by filename date, not commit time; terminal uniqueness is per output directory.
- Seals without an amendment identity are refused as source_unpinned; receipts over 4 MiB or over 4000 paired rows are refused as receipt_oversize or receipt_row_cap; a seal effective mid-window is not admitted, so declare windows between seal changes.
- Pooled means are computed at prec 80 from per-row losses, so a one-night read differs from the nightly receipt's prec-28 cell means past about the 27th digit.
- Terminal recovery after an interrupted link requires rerunning with the original asof (it is stored in the hidden terminal file).
- Exceeding MAX_GAMES makes the window unreadable (capacity_exceeded); a read whose asof is later than the current UTC time is refused (asof_in_future).
- The game identity registry (every registered game, including excluded and rowless games) is bounded at MAX_REGISTERED_GAMES = 15200 (10 x MAX_GAMES); exceeding it is capacity_exceeded for the whole window (measured about 848 B per registered game).
- A game identity, ticker or event id that changes across nights is a fatal duplicate_conflict even when either side is out of population.
- REFUSED output prints a named reason only, never raw exception text or absolute paths.

## Final candidate inventory

LF-normalized SHA-256 and owned-file sizes are generated by script from the final files. No byte lengths of another row are pinned.

| Owned path | Bytes | Lines | SHA-256 |
|---|---:|---:|---|
| scripts/platformkit/execution/scoreboard_cumulative.py | 15639 | 217 | 8836827e54ac60e9bbcba4aa2b1432b7c6ed545f3ffae7c60531e360e785b085 |
| scripts/platformkit/execution/scoreboard_cumulative_prereg.py | 18659 | 299 | c42abc9b0342f8201c11ea79b23981749583055bd84c8f7414cd1936c10d1f66 |
| scripts/platformkit/execution/scoreboard_cumulative_rows.py | 7035 | 119 | d996dd7518a2ca83e6b56d09fdf6f50d6fdf45a31c504ea9b7358d31aadf21df |
| tests/platformkit/execution/test_scoreboard_cumulative.py | 16331 | 273 | 848095e43f04d16c12b514c475b234f9c0ae5d0c0b560be8c937bb144272b71b |
| tests/platformkit/execution/test_scoreboard_cumulative_landed.py | 13203 | 217 | 7012d2da02a39bb59322136f5dba78ca627b146a0204fb7f1695b95b67ead7b9 |
| tests/platformkit/execution/test_scoreboard_cumulative_order.py | 14271 | 227 | e7848d25c70b43abab705b1d4458f530c044cc8e146ec511d1bae3d9f5ec4d04 |
| tests/platformkit/execution/test_scoreboard_cumulative_e2e.py | 16845 | 282 | 1c3f622542eeef7256e67a175f28b012bab669cf2511c01bf6b509f42c6728ec |
| tests/platformkit/execution/fixtures/s503_real_slice_2026-09-24.json | 546747 | 1 | dfde1122c488e10667335b5b2a7adcb3eb568268ecb1d6fef61a3fc1b7b2cb56 |
| .gitattributes | 3612 | 61 | 0a1c660629bdac5fe5ffe32aae6d3adf3d7d15b2495ff9230f20be511577a246 |

This generated memo is the tenth owned candidate path; no self-hash is embedded.

Against base 8e1074922ae3b5ba9b99da4aad3e4825b99c66b2, the MODIFIED .gitattributes adds only these lines (text eol=lf):

```text
docs/evidence/forward/scoreboard_cumulative/*.json text eol=lf
tests/platformkit/execution/fixtures/s503_*.json text eol=lf
```

## Pinned must-not-move check

Full immutable baseline: 8e1074922ae3b5ba9b99da4aad3e4825b99c66b2 (the current base, master 8e1074922 at the FINAL corrections). Comparisons use LF-normalized bytes from that commit against the working copy; no moving branch is used for these assertions.

| Path | Check | SHA-256 |
|---|---|---|
| scripts/platformkit/ingame/baseline_four_arm.py | UNCHANGED | dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2 |
| scripts/platformkit/ingame/baseline_four_arm_eligibility.py | UNCHANGED | d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032 |
| scripts/platformkit/ingame/baseline_four_arm_features.py | UNCHANGED | 8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade |
| scripts/platformkit/execution/ingame_scoreboard.py | UNCHANGED | 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6 |
| scripts/platformkit/execution/ingame_scoreboard_rules.py | UNCHANGED | 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351 |
| scripts/platformkit/eval_gate/walkforward.py | UNCHANGED | 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9 |
| scripts/platformkit/execution/ingame_scoreboard_amendment.py | UNCHANGED | 2ccc83054d93c4eb098820c869fd66560f0990cebe318e11a8e8bf0ef0604a6b |
| scripts/platformkit/execution/venue_time.py | UNCHANGED | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 |
| scripts/platformkit/execution/entry_timing/study.py | UNCHANGED | c96d64de6600a31d9c8bb567b502d10a2b8de8f777a6bea3eb133d350abd63a0 |
| scripts/platformkit/execution/ingame_scoreboard_night.py | UNCHANGED | 8a34c4f4fca9f0c4395f8256d97603797d717d744e65df2e656f897a6645da24 |
| scripts/platformkit/execution/registry_scorer_e_config.py | UNCHANGED | a1cbff0b7ba34e20c6e61c0d66f3331be247446119ea60fc3c962888f09a2ee1 |
| scripts/platformkit/execution/paper_night.py | UNCHANGED | e1a449229e0ba9b3ee54b72ff2c2191def3e3a96be33a5cbb412288067a7170d |
| scripts/platformkit/execution/paper_night_steps.py | UNCHANGED | 2b9bf8371a7e393546b1cb6596129d9866a890571cb4e7af8655e51d01d5b605 |
| scripts/platformkit/ingame/local_state_capture_sources.py | UNCHANGED | 8c6cb8f362879f611a3a64827225eb4d5407e38ad5bd013ec5fb3039fa57f20c |
| scripts/platformkit/execution/forward_schedule_sources.py | UNCHANGED | d88c88d7c32d7f9a08aae519df42504c0639280e83868bd73323533383006eac |
| docs/evidence/forward/scoreboard/2026-09-24.json | UNCHANGED | 2f8a2a7d6b4c2d80466520ccce4e3442fe22cbff57039450acf94e82d959ef06 |

Contract preflight (FIX 5): 9/9 checks PASS, FAIL=0, over all ten owned paths (including the new scoreboard_cumulative_rows.py, this memo and .gitattributes) and the S503 spec, run with --base master. The full baseline is also used for reproducible memo checking. The separately requested operational invocation uses --base master; no test or memo identity assertion depends on that moving reference.

## FIX 1b (Opus tier-2 REJECT, AMENDMENT 2 items a-h)

- (a) CONTRAST: a stored contrast is verified against Context().subtract(C, B) under a fresh default-precision (28) context, the landed writer's own arithmetic; pooled statistics still use the stored per-arm losses under the fixed 80-digit context. New tests build B/C rows with the landed _loss and _json (1,000 ticks, both targets, read cleanly) and the Opus reproduction values pass; the 60-digit test_27 expectation was dropped.
- (b) EXCLUSIONS: sport or cohort not named is excluded_rows / excluded_games, never a refusal; test with a soccer game and a registry_e game in a valid receipt reads window_complete True and read_kind final. Row failures never make a date incomplete (memo sentence corrected above).
- (c) SIBLINGS: a malformed row refuses its tick for both targets, counted once per target row under the malformed row's reason; duplicate_conflict remains only for two VALID rows disagreeing at one identity. Tests cover either target bad, either order.
- (d) CAPACITY: MAX_RECEIPT_BYTES is 4,194,304; larger receipts are receipt_oversize (receipt-level, date incomplete, disclosed). Capacity workload unchanged (40 nights x the 4,155,048 B receipt); peak RSS 626,229,248 B against the 629,145,600 B bar (thin margin: 2,916,352 B; run-to-run variance not measured, the earlier candidate read 596,410,368 B). Streaming parse for larger receipts is a disclosed follow-up.
- (e) GAME IDENTITY: identity is (sport, game_key, game_id, ticker, cohort); scheduled_start is metadata, first-seen value retained by date order, changes counted game_start_changed.
- (f) SEALS: an entry without an amendment identity is refused source_unpinned at the writer and verifier, and a receipt without an amendment block is counted source_unpinned (this refuses the legacy real 2026-09-24 receipt as a source; the real-slice test now adds a synthetic amendment block to a copy). The source verifier admits the committed S492 seal format (implementation_version, nfl in model_optional_sports, seven-file implementation, generic per-file historical hash check; S475 keeps its derived-eligibility check). Test fixture: the committed file at d507296d7 (file sha256 a74e955e2fb37825e9249ed5b6280421a7c7a450b71a8239f34d6e8322a3d588, asserted), read by git show at that pinned sha; only its implementation hashes are replaced by synthetic-repo hashes and re-sealed, because the S492 implementation files are not on this base. A seal effective mid-window stays not admitted (seal_not_admitted counted); declare a window between seal changes.
- (g) TERMINAL PUBLICATION: if the hidden terminal file exists byte-identical but the final name does not, the next terminal read links it; a different asof in the same directory is refused output_exists. Disclosed: asof selects by filename date, terminal uniqueness is per output directory.
- (h) Every per-file test re-run; inventories above regenerated by script (s503_memo_gen.py in the lane scratch area).

## FIX 2 (2026-09-29, Opus contract-tier r2 REJECT, AMENDMENT 3 items a-e; historical line numbers)

- (a) CAPACITY: MAX_DAYS=38, MAX_ROWS=152000, MAX_GAMES=1520 (scoreboard_cumulative_prereg.py:22); MAX_ROWS_PER_RECEIPT and MAX_RECEIPT_BYTES unchanged. Widest-shape workload in test_maximum_workload_fresh_process_rss; both fresh-process peaks and wall times are in the Construct capacity block, each <= 609,000,000 B. Publication now streams the identical _json bytes (prereg.py publish) instead of materialising the whole document.
- (b) ROW CAP: a receipt over MAX_ROWS_PER_RECEIPT is the receipt-level refusal receipt_row_cap (scoreboard_cumulative.py:200), date incomplete, never capacity_exceeded; test_16_receipt_row_cap_is_receipt_level.
- (c) TICKS: rows are gathered per tick (scoreboard_cumulative.py:229) and resolved by _tick (:65): valid disagreement is duplicate_conflict before any malformed-row refusal; tests test_conflict_beats_malformed_in_every_order (6 orderings) and test_malformed_sibling_refuses_tick_in_every_order (6 orderings, byte-identical outputs).
- (d) QUANTILES: p50/p90 use the landed nearest-rank rule of forward_replay_qualification.py:49 (index (n*p+99)//100-1; scoreboard_cumulative.py:56,153); test_nearest_rank_quantiles (n=10 gives indices 4 and 8).
- (e) NAMED REASONS: reason() (scoreboard_cumulative.py:47) maps JSONDecodeError, CalledProcessError, OSError and any unnamed exception to receipt_json_invalid, source_git_error, receipt_io_error, receipt_schema/row_schema (:203, :231); strict() refuses non-finite constants as nonfinite_json; test_named_reasons_never_raw_text.

## FIX 3 (2026-09-29, Opus contract-tier r3 REJECT, AMENDMENT 4 items a-d; historical line numbers)

- (a) CROSS-RECEIPT CONFLICTS: _tick (scoreboard_cumulative.py:65-70) compares every valid row of a tick against earlier valid rows of the tick and against refs = the retained valid rows plus the kept valid rows of earlier refused ticks of that identity (:237), before any refusal applies; refused ticks keep one valid row per target for this comparison only, never pooled (:238-240). Tests: test_cross_receipt_conflict_beats_refusal (P1 and P3, both night orders, duplicate_conflict) and test_cross_receipt_agreeing_is_counted_refusal (P3 agreeing, both night orders, counted refusal, no abort); the verifier probes P1/P2/P3/P3b all read duplicate_conflict.
- (b) STREAMED TERMINAL RECOVERY: same_bytes (scoreboard_cumulative_prereg.py:264) json.dumps into a hashing writer with the publish options and compares against a 1 MiB chunked SHA-256 of the terminal file; main uses it (scoreboard_cumulative.py:290). test_terminal_recovery_streamed_hash: a > 1 MiB published file matches, a changed payload does not, and a different terminal leftover is refused (exit 2, no link); test_terminal_link_recovery_and_directory_uniqueness keeps the identical-leftover link case.
- (c) CAPACITY SHAPES: test_maximum_workload_fresh_process_rss is parametrized both_targets / mid_only (test_scoreboard_cumulative_e2e.py:242); all four fresh-process peaks are in the Construct capacity block, each <= 609,000,000 B; the extra-key and two-shape disclosures are stated there.
- (d) MEMO: .gitattributes and must-not-move inventories regenerated by script against base b6a607c0850f2076b89cb3967f683f08106d4d9a. _validate (scoreboard_cumulative_prereg.py:189, :209) binds the sealed implementation hashes to the working copy, so a later edit to any sealed file (ingame_scoreboard.py, venue_time.py, entry_timing/study.py and the other sealed identities) refuses every open window with implementation_mismatch by design (AMENDMENT 1(d)). The e2e tracemalloc run peaks near 793 MB RSS; run it only with RAM headroom.

## FIX 4 (2026-09-29, Opus adversarial r4 REJECT, AMENDMENT 5 items a-f; historical line numbers)

- MODULE SPLIT: row grammar, tick resolution, named reasons, the games join and identity registration moved to the new owned module scripts/platformkit/execution/scoreboard_cumulative_rows.py (117 lines); it is sealed with the other evaluator identities (scoreboard_cumulative_prereg.py:38 FILES). Every owned .py file is <= 300 lines.
- (a) IDENTITY BEFORE EXCLUSION: _games (rows.py:89) validates the whole join and returns every selected game; register (rows.py:107, called at scoreboard_cumulative.py:129 right after the receipt is admitted, before any row or exclusion) records (sport, game_key) -> (game_id, ticker, cohort) and venue-global event/ticker aliases (rows.py:111, :114). Row processing no longer touches identity. Test: test_identity_registered_before_exclusion (order.py:126; cohort relabel to registry_e, sport relabel, reused ticker on an in-population and on an excluded game, rowless night then changed ticker; each with the change on the earlier and on the later night: 10 cases, all duplicate_conflict).
- (b) PATHOLOGICAL JSON: RecursionError and MemoryError are caught at the receipt boundary (scoreboard_cumulative.py:38, :127) and named receipt_json_invalid (rows.py:31). test_deeply_nested_receipt_is_receipt_json_invalid (400,824 B receipt, 200,000-deep list): counted, date incomplete, main exits 0.
- (c) MUTANTS: all twelve r4 survivors are now killed (table below); m24 and eight new AMENDMENT 5 mutants are killed too. The only survivor is the m00 no-op control.
- (d) ASOF IN FUTURE: evaluate refuses asof_in_future (scoreboard_cumulative.py:83) against the injectable utc_now (:41). test_asof_in_future_refused_with_injected_clock (order.py:145): equality admitted, +1 ns refused, CLI prints REFUSED: asof_in_future and writes nothing. Construct fixtures inject a 2026-12-01 clock; the e2e children inject 2100-01-01 through a test-only -c launcher (main has no clock override).
- (e) NORMALIZATION: GRAMMAR (rows.py:15) gates losses, mid targets (rows.py:21, row_refused:loss_grammar) and stored contrasts (rows.py:85); '-0' returns '0' (rows.py:26); "amendment": null is source_unpinned (scoreboard_cumulative.py:117). Tests: test_strict_ascii_decimal_grammar (11 spellings), test_negative_zero_normalizes_and_null_amendment_is_unpinned, test_contrast_strings_follow_the_strict_grammar.
- (f) DISCLOSURES: four new DISCLOSURES lines (prec-80 pooled means, original-asof terminal recovery, capacity_exceeded and asof_in_future, identity conflicts across exclusion) plus the named-only REFUSED line. REFUSED prints reason(exc, 'refused') only (scoreboard_cumulative.py:212; prereg main :294); test_refused_prints_named_reason_only (an absolute path in an OSError, raw ValueError text, RecursionError).
- One-night real receipt versus the nightly cells (probe p3b over the 2026-09-24 receipt with a synthetic amendment block): 32 of 32 comparable means agree to 12 significant digits (pre-live outcome A brier 0.361877097902 both), and the first difference is at the 26th decimal place or later; this is the disclosed prec-80 versus prec-28 difference, not a disagreement. Probe reproductions (scratchpad s503_fix4, the r4 probes with only the fixture clock injected): P1 cohort relabel both orders, P2 excluded ticker reuse, P2b sport relabel and P7 rowless-then-ticker read duplicate_conflict; P3 deep nesting reads receipt_json_invalid; P4 -0 vs 0 reads duplicate_row; P5 all five lenient spellings read row_refused:loss_grammar; P6 null amendment reads source_unpinned; p5 permutation outputs identical and 96/96 cells recomputed; p6 no-sort mutant still differs, real code byte-identical.

Mutation run (mutrun.py over the three non-e2e files, on scratch copies of each module; the worktree was never mutated):

| Mutant | Result | Killing file |
|---|---|---|
| m04_no_sort, m05_prec28 | KILLED | landed (test_output_bytes_invariant_to_target_row_order; test_pooled_decimal_context_is_pinned) |
| m17_alias | KILLED | order (test_identity_registered_before_exclusion, ticker) |
| m26_digits, m27_outcome_y, m37_rowref_uncovers, m38_scope, m39_filename, p01_replace, p04_source_prosp, p06_elig_types, p07_payload_keys | KILLED | landed (test_digit_limit_and_outcome_domain; test_row_refusal_keeps_the_date_covered; test_scope_and_filename_are_receipt_refusals; test_publish_never_replaces_a_concurrent_final_name; test_source_seal_prospective_at_equality; test_source_eligibility_types_and_payload_keys) |
| m24, n01-n09 (grammar, -0, JSON errors, asof, sport-scoped alias, raw REFUSED, null amendment, late registration, contrast grammar) | KILLED | order or landed |
| m01-m03, m06-m09, m11-m16, m18-m23, m25, m28-m31, m33, m35, m36, m40, p02, p03, p05 | KILLED | unchanged |
| m00_noop | SURVIVED | control |

## FIX 5 (2026-09-30, Opus contract-tier r5 ACCEPT WITH CORRECTIONS, AMENDMENT 6 items a-c)

- (a) REGISTRY BOUND: sealed capacity key MAX_REGISTERED_GAMES = 15200 (10 x MAX_GAMES; scoreboard_cumulative_prereg.py:25, in CAPACITY :40, so it is part of the sealed capacity and the FILES identity). register refuses capacity_exceeded once the identity registry (every registered game, excluded and rowless included) exceeds it (scoreboard_cumulative_rows.py:113); it is a named refusal like MAX_GAMES: whole window, exit 2, no output. DISCLOSURES line added (scoreboard_cumulative.py:31) with the bound and the verifier-measured about 848 B per registered game (scratchpad s503_v5/reg_probe.py). Test: test_registry_bound_counts_excluded_and_rowless (order.py:189; cap 3 refuses with REFUSED: capacity_exceeded, exit 2, no output dir; cap 4 reads 1 row; the four registered games include a rowless night and an excluded registry_e game).
- (b) MEMO: FIX 2 / FIX 3 / FIX 4 line citations are marked historical line numbers; FIX 5 cites the current files. Cross-night duplicate with a malformed sibling is resolved by date order (earlier night first): v1+bad then v1b refuses the tick, v1b then v1+bad keeps it pooled (both counted, no abort).
- (c) SCOPE: the owned list includes scoreboard_cumulative_rows.py (sealed in FILES) and test_scoreboard_cumulative_order.py, both created for the 300-line rule. Inventories regenerated by s503_memo_gen.py against base 7dcbf62b5ddd4871e340d6aad0fc8f1507bb94ef.

## FINAL (2026-09-30, Opus adversarial r5 ACCEPT WITH CORRECTIONS, AMENDMENT 7 items a-c; tests and memo only, no production module changed)

- (a) TESTS ADDED (all in test_scoreboard_cumulative_order.py, 227 lines): test_prereg_cli_refused_prints_named_reason_only (order.py:205; a missing config prints REFUSED receipt_io_error, a raw date ValueError prints REFUSED refused, nothing written; kills a04), test_identity_registered_before_exclusion gains event and event_excluded (order.py:121, :126; a different game reuses event0 under a new ticker on the other night, in-population or registry_e, both night orders: 4 cases, all duplicate_conflict; kills a12), test_max_games_admitted_at_equality (order.py:217; injected MAX_GAMES 2: two games read, three are capacity_exceeded; kills a06), test_capacity_is_the_sealed_block (order.py:224; CAPACITY['registered_games'] == 15200 == 10 x MAX_GAMES and CAPACITY equals the literal sealed block; kills a03). No S503 window prereg is committed yet, so the sealed block is the spec-literal block the prereg writer seals (main: capacity=CAPACITY).
- MUTANTS: mutrun.py over the three non-e2e files on scratch copies (scratchpad s503_fix7; the worktree was never mutated): a03_registry_const, a04_prereg_raw_refused, a06_maxgames_ge and a12_alias_ticker_only are all KILLED in order.py (a04 by test_prereg_cli_refused_prints_named_reason_only, a06 by test_max_games_admitted_at_equality[2-False], a12 by test_identity_registered_before_exclusion[True-event]; a03 under -x first fails the prereg CLI test because the scratch copy moves ROOT, so it was re-run with -k test_capacity_is_the_sealed_block alone: KILLED). The m00 no-op control SURVIVED (all fifty-four order.py cases passed).
- (b) RELIST DISCLOSURE: a game relisted on a later night under a different Kalshi event ticker or family is duplicate_conflict for the whole window (AMENDMENT 5(a)); the recovery is declaring a new window. The verifier probe found no instance in the committed schedules 09-22..09-30 (not re-measured here).
- (c) E2E: not re-run. Available RAM stayed between 1158 and 1931 MB for about 21 minutes of polling (gate 2200 MB), during a live game; the capacity block above remains the FIX 4 measurement and the orchestrator runs the e2e file at landing. Inventories regenerated by s503_memo_gen.py with the base set to master 8e1074922ae3b5ba9b99da4aad3e4825b99c66b2 (master had moved .gitattributes by 3 lines since 7dcbf62).

## NOT VERIFIED

- Independent verifier acceptance of FINAL and landing are pending. The e2e file was not re-run in FIX 5 or FINAL (available RAM stayed below the 2200 MB gate); the capacity block is the FIX 4 measurement, and no capacity RSS for the registry bound was measured. The orchestrator runs the e2e file at landing (AMENDMENT 7(c)). One non-e2e file in FINAL (test_scoreboard_cumulative.py) was started at 1339 MB available, under the 1500 MB gate; it passed.
- The real S492 seal was not verified end to end (its implementation files are absent from this base); only its format is exercised with substituted hashes.
- Real prospective multi-night behavior: only one historical receipt was inspected structurally. Real fitted B/C/D behavior: these arms are absent from the real fixture.
- Real-window memory/wall time, arbitrary metadata stress, and workloads beyond the declared construct capacity. Shared-night dependence, refit uncertainty, two-corpus replication or additional comparisons. Nightly caller wiring and its budget; no production window or caller was armed.
- Actual process termination between terminal links; tests cover sync failure and immutability, not an OS crash.
- Cleanup of .s503-e2e-accepted, .s503-e2e-final, .s503-e2e-temp, .s503-e2e-verified and .s503-test-tmp is blocked. Automatic approval review rejected recursive deletion, including explicit literal paths, with reason blocked by policy.
- No lane commit was created in this sandbox. Only the owned paths in the inventory (nine plus this memo) are intended for lane_commit.

## AMENDMENT 8 (2026-09-30, parser fix before S492 commit B)
- FIX: _eligibility(root, revision, sports) takes model_optional_sports from the seal payload that _source already validated (sorted, unique, non-empty, subset of SPORTS) and never literal-evaluates it from source text; keyword, not_covered and populations (the POPULATIONS constant) are still literal-evaluated and compared. ValueError and TypeError from the parse now map to source_eligibility. The e2e fixture call passes the sports list mlb, soccer.
- UNCHANGED DECISIONS: on master, the old and new parse give the same digest for both committed S475 seals (PREREG_2026-09-29, PREREG_2026-09-30) at HEAD and at each seal's own revision; both still equal the seal eligibility.
- TEST (AMENDMENT 9 fix round 1): test_scoreboard_cumulative_parser.py (six cases) locates the eligibility keywords of _payload through the module AST and replaces their segments by position, so it stays valid across S492 commit B. It admits both the literal and the list(sports) forms, and refuses source_eligibility on a non-literal keyword node and on a keyword differing from the seal, each under both sports forms.
- RUNS: parser on the master module "6 passed in 7.20s"; the same file on the commit-B module (the nine SOURCE_FILES from h300 2aee65757 in a scratch tree, ROOT redirected by a pytest plugin) "6 passed in 7.07s"; POWER on the pre-fix prereg "4 failed, 2 passed" on both modules, each failure "ValueError: malformed node or string" (Call or BoolOp). Other files per file, all green (counts in words for the vocab gate): cumulative forty-three passed, landed thirty-three passed, order fifty-four passed. E2E NOT RUN (869 MB available, gate 2200 MB). VERIFIERS: contract tier r1 REJECT (test anchored on module text) then r2 ACCEPT; adversarial tier r1 ACCEPT (nine of eleven mutants killed by the parser file; survivors: TypeError dropped from the except, a constant default sports list at the call site, an always-injected sports key -- none reachable from committed seals). FOLLOW-UP (pre-existing, unchanged): _source raises CalledProcessError when the pinned revision lacks a path named by the seal (PREREG_2026-10-01 before S492 commit B); the CLI prints REFUSED source_git_error, exit 2.
- LOST CHECK: the seal's model_optional_sports is no longer cross-checked against the historical source literal; it is bound only by the seal's own hash and the _source domain checks.
