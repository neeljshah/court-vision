# S494 NBA regular-season fitting-history policy

Real-row probe: tests/platformkit/ingame/fixtures/s494_legacy_401902644.jsonl is the verbatim first 2026-09-29 row of game 401902644 (status pre, no season keys), copied by the orchestrator; test_verbatim_legacy_probe_fresh_capture proves it reads as unlabelled.

## Binding before-condition

Archive-wide census RE-RUN on the candidate by the orchestrator (2026-09-29 ~21:3xZ, streamed, RSS-capped) over every NBA state shard: 7 shards (09-22 415, 09-23 357, 09-24 293, 09-25 662, 09-26 127, 09-28 456, 09-29 590 rows) = 2,900 rows, exactly one game (401902644), all status pre, 0 rows carrying season keys (the spec writer counted 2,704 earlier the same day; 09-29 grew). The census is quoted, not recomputed by this generator (no archive in the worktree).
The first 2026-09-29 row of 401902644 is supplied verbatim as the real-row probe fixture named above.
- {"day": "20261019", "events": 0, "regular_type_2": 0}
- {"day": "20261020", "events": 3, "regular_type_2": 3}
- {"day": "20261021", "events": 11, "regular_type_2": 11}

## Implementation and before/after

Before: NBA state and schedule entries omitted season fields; fitting history had no regular-only policy marker and accepted pooled NBA entries.
After: event-level labels are captured before the enrichment early return and propagated through schedule sources and writer.
One history enforcement point accepts NBA entries only for integer code 2 with no season reason and no conflicting state label at or before the snapshot.
Any different integer state season code conflicts, including unsupported codes. State diagnostics and eligible_games counts accompany NBA records.
Excluded labels remain in the served schedule. There is no slicing, directory-membership gate, or per-cohort manifest.
New manifests carry regular_only_v1; complete unmarked pairs containing NBA rows refuse legacy_nba_pair.
S490 soccer routing, league fields and path= interfaces are preserved by the candidate. Construct regression results below are the evidence.
Other-sport equality uses pinned pre-change construct records. S482 eligibility remains unchanged.
Forward schedule writing uses extraction rather than deleting assertions to meet the 300-line cap.

## Generated season boundary table

- {"case": "payload_none", "season_reason": "no_payload", "season_type": null, "season_year": null}
- {"case": "empty_payload", "season_reason": "no_event", "season_type": null, "season_year": null}
- {"case": "events_wrong_type", "season_reason": "no_payload", "season_type": null, "season_year": null}
- {"case": "season_missing", "season_reason": "no_season", "season_type": null, "season_year": null}
- {"case": "type_missing", "season_reason": "type_missing", "season_type": null, "season_year": null}
- {"case": "type_bool", "season_reason": "type_invalid", "season_type": null, "season_year": null}
- {"case": "type_string", "season_reason": "type_invalid", "season_type": null, "season_year": null}
- {"case": "type_float", "season_reason": "type_invalid", "season_type": null, "season_year": null}
- {"case": "type_null", "season_reason": "type_invalid", "season_type": null, "season_year": null}
- {"case": "year_bool", "season_reason": "year_invalid", "season_type": null, "season_year": null}
- {"case": "year_missing", "season_reason": null, "season_type": 2, "season_year": null}
- {"case": "code_0", "season_reason": null, "season_type": 0, "season_year": 2027}
- {"case": "code_1", "season_reason": null, "season_type": 1, "season_year": 2027}
- {"case": "code_2", "season_reason": null, "season_type": 2, "season_year": 2027}
- {"case": "code_3", "season_reason": null, "season_type": 3, "season_year": 2027}
- {"case": "code_4", "season_reason": null, "season_type": 4, "season_year": 2027}
- {"case": "code_5", "season_reason": null, "season_type": 5, "season_year": 2027}
- {"case": "code_-1", "season_reason": null, "season_type": -1, "season_year": 2027}
- {"case": "duplicate_event", "season_reason": "duplicate_event", "season_type": null, "season_year": null}

## Validation receipts

- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_dates.py", "summary": "87 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_fix1f.py", "summary": "13 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_game_key.py", "summary": "5 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_io.py", "summary": "4 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_local_date.py", "summary": "fifty-four passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_local_date_e2e.py", "summary": "15 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_soccer.py", "summary": "26 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_sources.py", "summary": "63 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_team_set.py", "summary": "23 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_utc_day.py", "summary": "20 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_forward_schedule_writer.py", "summary": "45 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py", "summary": "8 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_ingame_scoreboard_night_replace.py", "summary": "13 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_nba_season_cohorts.py", "summary": "39 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_paper_night_e_step_e2e.py", "summary": "41 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_paper_night_inputs_e2e.py", "summary": "11 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_paper_night_scoreboard_step.py", "summary": "14 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_paper_night_steps.py", "summary": "56 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_replace_retry.py", "summary": "2 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_s494_evidence.py", "summary": "4 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_schedule_d1.py", "summary": "46 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_scoreboard_history.py", "summary": "36 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_scoreboard_history_e2e.py", "summary": "14 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_scoreboard_history_store.py", "summary": "80 passed"}
- {"exit_code": 0, "path": "tests/platformkit/execution/test_soccer_scoring_s490.py", "summary": "12 passed"}
- {"exit_code": 0, "path": "tests/platformkit/ingame/test_local_capture_writer_atomic_retry.py", "summary": "22 passed"}
- {"exit_code": 0, "path": "tests/platformkit/ingame/test_nba_season_type.py", "summary": "45 passed"}
- {"exit_code": 0, "path": "tests/platformkit/ingame/test_nba_state_enrichment.py", "summary": "80 passed"}
- {"exit_code": 0, "path": "tests/platformkit/ingame/test_nba_state_enrichment_archive.py", "summary": "10 passed"}
- {"exit_code": 0, "path": "tests/platformkit/ingame/test_schedule_pointer_startup_union_1d.py", "summary": "6 passed"}
- {"exit_code": 0, "path": "tests/platformkit/ingame/test_wnba_registration.py", "summary": "45 passed"}
- {"exit_code": 0, "path": "tests/platformkit/ingame/test_wnba_registration_e2e.py", "summary": "12 passed"}
- {"exit_code": 0, "path": "tests/platformkit/ops/test_capture_supervisor_atomic_retry.py", "summary": "16 passed"}

The receipts list each test path, exit code and reported pass/fail/skip summary. Missing receipts mean NOT RUN.
Any failing test or mandatory skipped case prevents acceptance. Exact construct exclusion counts are reported only when present in these receipts.
No measured calibration conclusion is made.

## Revision metadata

- {"HEAD": "a2c391d9244c42a478c5da3efe079e4131dcaeae", "comparison": "EQUAL", "master": "a2c391d9244c42a478c5da3efe079e4131dcaeae"}
HEAD/master are dispatch metadata only; no check compares against either moving reference.
All sealed identity comparisons below use immutable base cac8864cc662907939b8d551379807559ca75291.

## LF-normalized sealed identities

- {"base_sha256": "6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b", "candidate_sha256": "6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b", "path": "docs/evidence/forward/scoreboard/PREREG_2026-09-24.json", "status": "EQUAL"}
- {"base_sha256": "421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d", "candidate_sha256": "421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d", "path": "docs/evidence/forward/scoreboard/PREREG_2026-09-24_superseded_2026-09-25.json", "status": "EQUAL"}
- {"base_sha256": "6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e", "candidate_sha256": "6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e", "path": "docs/evidence/forward/scoreboard/PREREG_2026-09-29.json", "status": "EQUAL"}
- {"base_sha256": "801af61b2755a99f9d5e238acd59bb1b6cf88212d1cb81b11a576ac32877b7aa", "candidate_sha256": "801af61b2755a99f9d5e238acd59bb1b6cf88212d1cb81b11a576ac32877b7aa", "path": "docs/evidence/forward/scoreboard/PREREG_2026-09-30.json", "status": "EQUAL"}
- {"base_sha256": "82f729ac54c6be62cef9147e9c17837e88bc3f8e429f941000fe7d69975872cd", "candidate_sha256": "82f729ac54c6be62cef9147e9c17837e88bc3f8e429f941000fe7d69975872cd", "path": "docs/evidence/forward/scoreboard/PREREG_2026-09-30_S490_DEPENDENCY_ADDENDUM.json", "status": "EQUAL"}
- {"base_sha256": "a74e955e2fb37825e9249ed5b6280421a7c7a450b71a8239f34d6e8322a3d588", "candidate_sha256": "a74e955e2fb37825e9249ed5b6280421a7c7a450b71a8239f34d6e8322a3d588", "path": "docs/evidence/forward/scoreboard/PREREG_2026-10-01.json", "status": "EQUAL"}
- {"base_sha256": "a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0", "candidate_sha256": "a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0", "path": "docs/evidence/forward/scoreboard/PREREG_E_2026-09-25.json", "status": "EQUAL"}
- {"base_sha256": "6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9", "candidate_sha256": "6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9", "path": "scripts/platformkit/eval_gate/walkforward.py", "status": "EQUAL"}
- {"base_sha256": "12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6", "candidate_sha256": "12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6", "path": "scripts/platformkit/execution/ingame_scoreboard.py", "status": "EQUAL"}
- {"base_sha256": "207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351", "candidate_sha256": "207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351", "path": "scripts/platformkit/execution/ingame_scoreboard_rules.py", "status": "EQUAL"}
- {"base_sha256": "dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2", "candidate_sha256": "dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2", "path": "scripts/platformkit/ingame/baseline_four_arm.py", "status": "EQUAL"}
- {"base_sha256": "d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032", "candidate_sha256": "d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032", "path": "scripts/platformkit/ingame/baseline_four_arm_eligibility.py", "status": "EQUAL"}
- {"base_sha256": "8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade", "candidate_sha256": "8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade", "path": "scripts/platformkit/ingame/baseline_four_arm_features.py", "status": "EQUAL"}
- {"base_sha256": "1fb9aa085c33c858a61884160706d4292ab70768500c777879b81c9d1f659791", "candidate_sha256": "1fb9aa085c33c858a61884160706d4292ab70768500c777879b81c9d1f659791", "path": "scripts/platformkit/ingame/baseline_four_arm_period.py", "status": "EQUAL"}
- {"base_sha256": "60eac7412421886563f269691e4ad92b76df6d32be3267a44cf207d84f82000b", "candidate_sha256": "60eac7412421886563f269691e4ad92b76df6d32be3267a44cf207d84f82000b", "path": "scripts/platformkit/ingame/local_state_capture.py", "status": "EQUAL"}
- {"base_sha256": "8c6cb8f362879f611a3a64827225eb4d5407e38ad5bd013ec5fb3039fa57f20c", "candidate_sha256": "8c6cb8f362879f611a3a64827225eb4d5407e38ad5bd013ec5fb3039fa57f20c", "path": "scripts/platformkit/ingame/local_state_capture_sources.py", "status": "EQUAL"}

## Candidate inventory

- {"bytes": 2639, "lines": 43, "path": "C:\\Users\\neelj\\nba-harness-h152\\.gitattributes", "resolution": "text", "sha256": "1424a6581c2a67d64bc98ac9287ae9dd8f80caebef5f1b6f6254343ff495ac86"}
- {"bytes": 1362, "lines": 35, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\forward_schedule_io.py", "resolution": "Python", "sha256": "a993ab228644b8cc355a3544066f47cd73b0d5ae09a8dbe7fd2894baf3b8fea7"}
- {"bytes": 12456, "lines": 236, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\forward_schedule_sources.py", "resolution": "Python", "sha256": "d88c88d7c32d7f9a08aae519df42504c0639280e83868bd73323533383006eac"}
- {"bytes": 16040, "lines": 291, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\forward_schedule_writer.py", "resolution": "Python", "sha256": "f0cc236adeab9ba12eed344de21ef5090c6f60225eb500d4787021f997438967"}
- {"bytes": 6639, "lines": 140, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\nba_history_filter.py", "resolution": "Python", "sha256": "2aa8064eed893dfaa1bade63b51ca39c99e70a0553cdceef0284121ebc3e53f3"}
- {"bytes": 685, "lines": 17, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\replace_retry.py", "resolution": "Python", "sha256": "46a22c4bcfc336812b22bbaed5d9ec22f8dab38aa99e16cc7f1d1a683a42de04"}
- {"bytes": 7699, "lines": 155, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\s494_constructs.py", "resolution": "Python", "sha256": "ac46496992e14208d5801cb094a0588193e9e0f4e6d61497141b2de486c7484d"}
- {"bytes": 18262, "lines": 266, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\s494_evidence.py", "resolution": "Python", "sha256": "9ee1fc3da46447f7e69f3a02bfe35a975616552e54b2d2c5bc8d12d395e24822"}
- {"bytes": 15109, "lines": 237, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\scoreboard_history.py", "resolution": "Python", "sha256": "e73261c9cd88caf3749f059cae366a3716d23c75f951055c76d20e205d557887"}
- {"bytes": 15289, "lines": 298, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\execution\\scoreboard_history_store.py", "resolution": "Python", "sha256": "b73b0833f73c6f729bd08e5e1796f27b27b321dc2d0568caebc29d922c68a1c8"}
- {"bytes": 1506, "lines": 30, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\ingame\\nba_season_type.py", "resolution": "Python", "sha256": "da4e54ae6aa0daf985c79d6ead15cdbf2fe9abd06035f5dc3352def1e32a5953"}
- {"bytes": 3099, "lines": 59, "path": "C:\\Users\\neelj\\nba-harness-h152\\scripts\\platformkit\\ingame\\nba_state_enrichment.py", "resolution": "Python", "sha256": "81c23b60a660c1a3bf47b46e988a5f5eaccc4cb36f2b58cfbd1cf63625788ee1"}
- {"bytes": 1267, "lines": 1, "path": "C:\\Users\\neelj\\nba-harness-h152\\tests\\platformkit\\execution\\fixtures\\s494_non_nba_baseline.json", "resolution": "JSON", "sha256": "81cfbee35c5a3075c1f6a2a6ef68966f80b70cecbf2352e5dbd089b04a56a60f"}
- {"bytes": 4289, "lines": 167, "path": "C:\\Users\\neelj\\nba-harness-h152\\tests\\platformkit\\execution\\fixtures\\s494_validation.json", "resolution": "JSON", "sha256": "39db935e16379617d36e16969e63a3d9472e2310b834f05989c5b89a0aa0b393"}
- {"bytes": 11591, "lines": 264, "path": "C:\\Users\\neelj\\nba-harness-h152\\tests\\platformkit\\execution\\test_nba_season_cohorts.py", "resolution": "Python", "sha256": "9b0656e1b42c290224204b776ec1e84b312d0c976611f30369b0ea6b07cbd814"}
- {"bytes": 1120, "lines": 39, "path": "C:\\Users\\neelj\\nba-harness-h152\\tests\\platformkit\\execution\\test_replace_retry.py", "resolution": "Python", "sha256": "e9b8f9b92cade6a7b4fbfaf251da413e09e7a1ad36f07cdd638130a9375b2cb7"}
- {"bytes": 2381, "lines": 53, "path": "C:\\Users\\neelj\\nba-harness-h152\\tests\\platformkit\\execution\\test_s494_evidence.py", "resolution": "Python", "sha256": "17d02babcdf73d6795b3a717a53acefc03c2306ddea96411b1031977db61b1fb"}
- {"bytes": 2053, "lines": 1, "path": "C:\\Users\\neelj\\nba-harness-h152\\tests\\platformkit\\ingame\\fixtures\\s494_legacy_401902644.jsonl", "resolution": "JSONL", "sha256": "e4944a8fe278d4ae364547ffc6add9a70a7747c0e1a7d77491c8a65fdc51fedb"}
- {"bytes": 3362, "lines": 142, "path": "C:\\Users\\neelj\\nba-harness-h152\\tests\\platformkit\\ingame\\fixtures\\s494_prechange.json", "resolution": "JSON", "sha256": "16b0e51a8b9eb55c28c69cbb6268507b044bdedb29a019a71b7c813230653c07"}
- {"bytes": 10576, "lines": 228, "path": "C:\\Users\\neelj\\nba-harness-h152\\tests\\platformkit\\ingame\\test_nba_season_type.py", "resolution": "Python", "sha256": "a440a39f1cb66d102461a68b4c80e4e5caf06dba034e1cac6eb827f4817a6492"}

The generated memo excludes itself from its own hash inventory. Bytes are observed sizes, never test pins.
## Exact relied-on signatures

- scripts/platformkit/execution/scoreboard_history_store.py:252  `def validate_pair(rows: Path, manifest: Path, config: dict | None = None) -> dict | None:`
- scripts/platformkit/execution/scoreboard_history_store.py:272  `def _replace(path: Path, raw: bytes) -> None:`
- scripts/platformkit/execution/scoreboard_history_store.py:288  `def publish(rows: Path, manifest: Path, row_bytes: bytes, manifest_dict: dict) -> None:`
- scripts/platformkit/execution/scoreboard_history.py:32  `def chronology(night: str, lookback: int, embargo: int) -> tuple:`
- scripts/platformkit/execution/scoreboard_history.py:43  `def _strict(raw: bytes) -> object:`
- scripts/platformkit/execution/scoreboard_history.py:fifty-four  `def _valid_entry(value: object) -> None:`
- scripts/platformkit/execution/scoreboard_history.py:102  `def produce(root: Path, args, config: dict, nights: list, capture: Path) -> tuple:`
- scripts/platformkit/execution/scoreboard_history.py:179  `def main(argv: list[str] | None = None) -> int:`
- scripts/platformkit/execution/nba_history_filter.py:24  `def exclusion(entry: dict) -> str | None:`
- scripts/platformkit/execution/nba_history_filter.py:36  `def state_conflicts(capture: Path, day: str, snapshot: str, labels: dict,`
- scripts/platformkit/execution/nba_history_filter.py:78  `def regular_schedule(schedule: Path, entries: list, capture: Path, day: str,`
- scripts/platformkit/execution/ingame_scoreboard.py:104  `def _capture(r: dict, end: str, now: int, counts: Counter, identities: set, sport: str) -> dict | None:`
- scripts/platformkit/execution/ingame_scoreboard.py:156  `def run(books_root: Path, state_root: Path, schedule: Path, day: str, sports: list,`
- scripts/platformkit/execution/venue_time.py:45  `def parse_venue_time(value: object) -> float | None:`
- scripts/platformkit/ingame/local_state_capture.py:23  `def _build_row(sport: str, item: dict, request_start: str, response_end: str,`
- scripts/platformkit/ingame/local_state_capture_dates.py:26  `def venue_instant(value: object) -> Decimal | None:`
- scripts/platformkit/ingame/nba_state_enrichment.py:31  `def attach_enrichment(row: dict, item: dict, last_enrichment: dict) -> dict:`
- scripts/platformkit/ingame/nba_season_type.py:5  `def season_of(payload: object, game_key: object) -> dict:`
- scripts/platformkit/ingame/nba_season_type.py:26  `def attach(row: dict, item: dict) -> dict:`
- scripts/platformkit/execution/forward_schedule_sources.py:53  `def _game(raw: dict, official: str | None, sport: str, counts: Counter,`
- scripts/platformkit/execution/forward_schedule_writer.py:168  `def build_schedule(day: str, sports: list[str], books_root: Path, state_root: Path,`

## AMENDMENT 2 failure classification (F1-F4)

- F1 test_paper_night_e_step_e2e test_c22_pinned_must_not_move_bytes for scoreboard_history.py and scoreboard_history_store.py: EXPECTED. S494 (A1, A4) is authorized to move them; the test pins the full sha256 of the LF-normalised S494 content, and non-NBA behaviour is proven byte-identical by tests/platformkit/execution/fixtures/s494_non_nba_baseline.json.
  Arm E is not affected: registry_scorer_e_night.py:109 refuses every sport but mlb (unsupported_sport) and :132 reads state keys for mlb only, and its only scoreboard_history imports are the unchanged _strict and _valid_entry (registry_scorer_e_night.py:21); no landed E path fits NBA (S482 not landed).
- F2 test_scoreboard_history_e2e case17 / case18 (0 rows instead of 2): EXPECTED consequence of A1 (unlabelled NBA entries are excluded); the cases now carry verified regular-season labels and a new case asserts unlabelled entries give nba_season_excluded {'unlabelled': 2}.
- F3 test_nba_state_enrichment_archive (pre-S414 nba bytes; stdlib-only import list): EXPECTED; NBA rows equal the pre-S414 rows plus exactly season_type, season_year, season_reason, and nba_season_type is asserted stdlib-only.
- F4 test_wnba_registration_e2e test_15_nba_schedule_base_bytes: EXPECTED; NBA schedule entry bytes equal base plus exactly the three additive season keys; WNBA and other sports stay exactly pinned.
- Regression found and fixed: the history filter published its temporary schedule through an atomic os.replace, which intermittently raised PermissionError on Windows; it now writes the private temporary file directly, in the SYSTEM temp dir (tempfile default, ignore_cleanup_errors), never under the schedules directory.
- ORCHESTRATOR-AUTHORISED ADDITION outside A4's one-field store edit (disclosed): an intermittent test_nba_season_cohorts failure was root-caused by a captured traceback to the PRE-EXISTING S474 store: scoreboard_history_store._replace -> os.replace of the manifest raised PermissionError [WinError 32] (file in use by another process, an AV/indexer lock). The store now calls replace_retry (scripts/platformkit/execution/replace_retry.py): bounded retry ONLY on PermissionError winerror 32 or 5, 5 attempts (about 2 s), any other error or the last attempt re-raises; tested by test_replace_retry.py. The F1 pinned hash includes it. Before: 3 of 12 whole-file runs red; after: 6 of 6 green.
- Adoption order (contract tier finding 1): schedule_pointer.union_open_rows refuses a pointer update when a carried row and its re-selection differ beyond selected_at, so an old-writer NBA row (no season keys) re-selected by the new writer would refuse the pointer for every sport until that row closes. Today no NBA row is in any served schedule (D1 sports are mlb,nfl), so there is nothing to carry; rule: land and adopt the writer before NBA joins D1, or adopt while no NBA row is carried.
- Deliberate fail-closed choices: one malformed pre-snapshot NBA state row marks every labelled game that night 'conflict' (counted nba_season:state_refused); the history PRODUCER refuses a legacy complete NBA pair (legacy_nba_pair) until an operator removes it, but the nightly scoreboard CONSUMER (paper_night_steps.py:285, validate_pair only) does not yet check the policy marker -> S580 (latent: no training pairs exist in the repo, 0 NBA live rows).

## JSON attributes

```gitattributes
tests/platformkit/ingame/fixtures/s494_*.json text eol=lf
tests/platformkit/ingame/fixtures/s494_*.jsonl text eol=lf
tests/platformkit/execution/fixtures/s494_*.json text eol=lf
```

## NOT VERIFIED

- The archive-wide census was not re-run on the candidate (quoted from the spec writer's 2026-09-29 run).
- Game 401902644 (captured before adoption) stays unlabelled; its season type is not inferred.
- Verbatim preseason code 1, postseason code 3, and play-in payload shapes are not verified.
- Existing capture elapsed time is 55.0 minutes at period 5 clock 5:00; the OT overstatement is a follow-up, unchanged here.
- WNBA rows are not labelled by this NBA-only change.
- No real NBA live row exists yet; every construct uses committed fixtures only.
- No adoption, restart, network, pod, real archive execution, or measured result was exercised.
- Sealed scorer receipt-order behavior remains unchanged; these constructs do not establish archive-wide ordering properties.
- Failed, skipped, or missing mandatory validation receipts prevent acceptance.
