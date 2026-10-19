# S477 local date timezone - FIX 1b - 2026-09-28

PASS (CONSTRUCT): 15 of 15 enumerated cases covered; 367 tests passed in ten separate per-file commands.
Files remain uncommitted in nba-harness-h126 for independent verification and lane_commit.
Metric = cases passing / cases enumerated; before = three spec probes plus fixture case 2; bar = 15 of 15; n = 15 (CONSTRUCT); eye check = n/a.
Machine: local Windows worktree; constructs and supplied fixtures only. No real archive, network, pod or deployment.

## FIX 1a

AMENDMENT 1(a)-(f) supersedes conflicting earlier spec prose. Only the owned helper, two owned tests, runbook and this memo changed during FIX 1a; previously correct writer/source/D1 candidate edits remain intact.

| Finding | Before reproduction / omission | Exact correction and regression |
| --- | --- | --- |
| (a) Wrong-date linking | `AMENDMENT a: wrong-zone linked other encounter KXMLBGAME-26SEP29TORBAL` | Two constructed adjacent MLB encounters link correctly in Chicago; UTC selects the other encounter. The test pins this known limit; runbook and memo retract the no-wrong-game guarantee. |
| (b) Impossible real archive success | `AMENDMENT b unmodified archive: {'invalid_time': 1} written 0` | Existing case 3 already pins this refusal. Retained the unmodified fixture and separately labelled constructed valid-start derivative; no runtime change was needed. |
| (c) Invalid timezone repaired | Initial regression: `AssertionError: assert (not [{'family': 'maker_forward', 'game_id': 'KXNFLGAME-26SEP28PHICHI', ...}])`; census `written: 1`, `refused_by_reason: {}`, fill count 1 | Helper now returns invalid_local_timezone rows unchanged. Both live and archive refuse missing_identity with fill count 0. Added malformed truthy date, missing home/away after fallback and refused prior regressions; _choose remains unchanged. |
| (d) Incomplete identity oracle | `explicit base-source binding: False`; `D1 clock frozen: False`; `request trace assertion: False`; `MLB/tennis/archive oracle cases: False` | Explicitly bind base fetch callables and assert their globals. Freeze source, writer and D1 clocks. Ten variants compare out/census/stdout bytes and request traces: window off/on for MNF, S430, MLB, tennis and archive. All four diagnostics now True. |
| (e) Overstated hand-off | `unrelated incoming row assertion: False` | Case 14 adds unrelated incoming row beside moved identity; read returns None with pointer_schedule_refused, prior schedule stays equal and unrelated row is absent. Diagnostic now True. |
| (f) Tennis counter overclaim | New full-player-name construct observed `{'missing_directional_team_evidence': 2}`, not the provisional expected `{'no_kalshi_event_for_date_and_team': 2}` | ATP/WTA athlete display names produce zero written and two identity refusals. Compatible supplied abbreviations produce two written. Each flagged run fills two dates and refuses two other-day rows; unflagged rows refuse missing_identity. |

Before the runtime fix, the expanded main test file reported `2 failed, 44 passed`: the timezone defect and the new tennis test's provisional reason expectation. After correcting the helper and pinning the actual tennis reason, it reported `46 passed`; the additional live invalid-zone regression brings the final count to `47 passed`.
The e2e edit initially reported `5 failed, 10 passed` because its newly frozen D1 clock lacked fromtimestamp. Making that clock a datetime subclass fixed the test harness; final result `15 passed`.
Coverage omissions in (d)/(e) were diagnostic failures, not runtime defects. The already-correct refusal in (b) was not changed or presented as a new fix.
Durable lesson: date and team-set agreement does not prove encounter identity. Apply this by retaining the adjacent-rematch regression whenever declared-date linking changes; never infer successful linking from a fill counter.

## FIX 1b

AMENDMENT 2(a)-(c) adjudicates the verifier findings. This pass changes only the owned helper, writer, two tests and this memo. The supplied fixture bytes, sources, D1 module and runbook were left as found.

| Finding | Before reproduction | Exact correction and regression |
| --- | --- | --- |
| (a) Fixture encoding, verifier blocking item 1 | `fixture bytes=23204 sha256=98ba725daf5f6e9048d141a0fa0da927dfefb1f8ff84e14abc214489f84f3919`; `capture_raw_match=False` | Amendment 2 accepts the re-encoding; no bytes restored. Case 3 now asserts canonical SHA-256 `12750b322dfaf5950f58c90195a327f1decc1488ba487f00819144d2f2b32f66`, which passed before and after the runtime fix. Both raw hashes and the encoding reason remain recorded below. |
| (b) D1 oracle, verifier blocking item 2 | `calls_schedule_d1_main=False`; `writer_loop=True`; `d1_only_monkeypatched=True` | Case 1 loads base D1 with base writer and sources explicitly bound and freezes all clocks. Both D1 mains compare exit code, request traces, stdout and every emitted file in ten variants: MNF, S430, MLB, tennis and archive, each with the window off/on. S430 window-on emits five byte-equal files. Final e2e file: 15 passed. |
| (c) Fill condition, verifier note 3 tightened by Amendment 2 | `reason=None filled=True count=1`; `reason=missing_scheduled_time filled=True count=1`; `reason=unknown_reason filled=True count=1`; stored invalid timezone still gave `written: 1` | Helper accepts only `date_reason=missing_local_timezone`. Writer propagates a stored `invalid_local_timezone` when the opt-in archive fallback is consulted, so fill stays blocked. Six allowlist cases cover null, empty, stale, unknown, invalid and allowed reasons; a live fixture regression with invalid stored reason now refuses missing_identity with fill count zero. |

Before the runtime edit, the new regressions reported `5 failed, 49 passed`; the allowlist failures showed `AssertionError: assert True == False`, and the invalid stored reason showed `AssertionError: assert (not [{'family': 'maker_forward', ...}])`. After the helper and writer corrections, all fifty-four tests in that file passed. Valid-start constructed archive rows now explicitly declare missing_local_timezone; the unchanged null-start fixture still refuses invalid_time. Existing tennis outcomes remain unchanged.
D1 final structural checks: `calls_base_and_candidate_d1_main=True`, `writer_loop=True`, `d1_only_monkeypatched=False`. The D1 CLI has neither a window nor an archive switch; the oracle injects a writer wrapper to exercise those writer options through each real D1 main. Archive D1 retains missing_schedule_receipt, MLB/tennis retain discovery_absent, and MNF plus S430 window-off retain nothing_schedulable. The successful S430 case prevents an empty-file comparison from passing alone.
Durable correction: a missing or unrelated date_reason is not permission to derive a date. Apply the explicit allowlist and consult stored invalid-timezone evidence before filling. See [S477 spec](../tracking/specs/S477_spec.md) and [[S477_local_date_tz_2026-09-28]].

## Case table

| Case | Exercised behavior | Test | Result |
| --- | --- | --- | --- |
| 1 | Flag absent: ten writer and ten D1 comparisons, explicit base bindings, fixed clocks, exits, bytes and traces | test_1_legacy_bytes_against_base | PASS |
| 2 | Three before-condition fixture probes | test_02_before_chain | PASS |
| 3 | MNF live success; unchanged archive null-start refusal; constructed archive success | test_03_real_fixture_end_to_end; test_03_04_partition_archive_and_redundancy | PASS |
| 4 | Redundant flags have identical rows, census and requests | test_03_04_partition_archive_and_redundancy | PASS |
| 5 | Zone boundaries including sub-microsecond values | test_05_boundaries | PASS |
| 6 | Invalid zones refuse before requests and output files | test_06_invalid_zone_before_requests | PASS |
| 7 | Payload officialDate remains authoritative | test_07_09_payload_and_archive_precedence; test_10_mlb_listing | PASS |
| 8 | Explicit fill allowlist, stored invalid timezone, malformed date, missing identities, refused prior | test_08_refusal_order; test_08_live_archive_fallback_refusals; test_08_live_invalid_timezone_stays_refused; test_1b_fill_reason_allowlist; test_1b_invalid_archive_reason_blocks_live_fill | PASS |
| 9 | Archive date precedence and conflict refusal | test_07_09_payload_and_archive_precedence | PASS |
| 10 | MLB prior-day listing, legacy refusal, adjacent rematch known limit | test_10_mlb_listing; test_1a_adjacent_rematch_operator_assumption | PASS |
| 11 | ATP/WTA player-name refusal and compatible ticker-identity acceptance, other-day refusal | test_11_tennis_tour_listing | PASS |
| 12 | Exact D1 legacy call, flag keyword, invalid input and argv receipt | test_12_d1_exact_writer_call; test_12_invalid_zone_no_files | PASS |
| 13 | Frozen real D1 caller, strict JSON and fresh-process pointer reader | test_13_real_mnf_d1_and_fresh_reader | PASS |
| 14 | Unchanged carry, moved-start whole-target refusal and unrelated-row exclusion, mixed-day refusal | test_14_next_d1_carry_conflict_and_day_mismatch | PASS |
| 15 | Eight landed test files unchanged and passing separately | Per-file results | PASS |

## Per-file results

Each command was `python -m pytest <one file> -q -p no:cacheprovider`, one file at a time. No whole-suite invocation.

| File | Passed |
| --- | ---: |
| tests/platformkit/execution/test_forward_schedule_local_date.py | 5 * 10 + 4 |
| tests/platformkit/execution/test_forward_schedule_local_date_e2e.py | 15 |
| tests/platformkit/execution/test_forward_schedule_sources.py | 63 |
| tests/platformkit/execution/test_forward_schedule_writer.py | 45 |
| tests/platformkit/execution/test_forward_schedule_game_key.py | 5 |
| tests/platformkit/execution/test_forward_schedule_team_set.py | 23 |
| tests/platformkit/execution/test_forward_schedule_fix1f.py | 13 |
| tests/platformkit/execution/test_forward_schedule_dates.py | 83 |
| tests/platformkit/execution/test_forward_schedule_utc_day.py | 20 |
| tests/platformkit/execution/test_schedule_d1.py | 46 |

Both `python -m scripts.platformkit.execution.forward_schedule_writer --help` and `python -m scripts.platformkit.execution.schedule_d1 --help` exited 0 and showed --local-date-tz. The helper and sources have no CLI or self-check command.
Contract preflight passed 9 of 9 checks over the 12 owned paths with --base master --spec docs/evidence/tracking/specs/S477_spec.md; the verdict is excluded. git diff --check passed.

## Before-condition provenance

The three live probes below are quoted verbatim from the binding spec, not rerun by this fixture-only lane. Case 2 reproduces their refusal chain with the supplied fixtures and fake requests.

BINDING BEFORE-CONDITION (live, --sports nfl --family maker_forward --books-root data/cache/ingame_books_local --state-root data/cache/ingame_state_local_v2, --out in the session scratchpad; outputs quoted verbatim): (1) 15:25Z --date 2026-09-28, no flag: `games_seen 1, linked 0, written 0, refused_by_reason {'outside_utc_date': 1}`, url ?dates=20260928, http 200, 23194 bytes, sha256 5412bcb53a25751751f09e1deeed79cb01173aa5d135872e30da6584126792a9; (2) --date 2026-09-29, no flag: `games_seen 0, written 0, refused {}` (?dates=20260929 lists no event); (3) --date 2026-09-29 --utc-day-window: `games_seen 1, linked 0, written 0, refused_by_reason {'missing_identity': 1}`, record_counts listed_on_previous_us_date 1, espn_minute_precision_normalized 1, kept_from {'401872963': '20260928'}; the fetched row: game_key 401872963, home CHI, away PHI, scheduled_start_utc 2026-09-29T00:15:00.000000Z, status pre, date None, date_reason missing_local_timezone. AFTER-PROBE (read-only, in-process, the fill below patched onto the landed fetch, no file written): `written 1`, row game_id KXNFLGAME-26SEP28PHICHI, ticker KXNFLGAME-26SEP28PHICHI-CHI, link_paths team_set, canonical_rules home_alias 1. TONIGHT WITHOUT CODE: NONE EXISTS -- (3) is the only landed route and it refuses; the one no-code alternative (a hand-authored state row carrying date) fabricates a capture record and is ruled out.

## Fixture provenance

All four supplied fixtures remain as found at FIX 1a start. The real archive row has date=null, scheduled_start_utc=null and date_reason=missing_scheduled_time; it refuses invalid_time. Archive success uses a separately labelled CONSTRUCTED temporary derivative with a valid ESPN start.
The prior candidate encoded one display string using separate JSON Unicode digit escapes. Original September 28 body: 23194 bytes, sha256 bd7cdd665daa848af0f44d8d7a1eebaeb6ff7d7c37b1baa939a2d66d4bd600a5. Fixture encoding: 23204 bytes, sha256 98ba725daf5f6e9048d141a0fa0da927dfefb1f8ff84e14abc214489f84f3919. FIX 1a and FIX 1b did not modify these bytes. Amendment 2 accepts the JSON Unicode digit escapes so the Q6 token scan remains clean. Canonical JSON uses sort_keys=True, separators=(',', ':'), ensure_ascii=True; its SHA-256 is 12750b322dfaf5950f58c90195a327f1decc1488ba487f00819144d2f2b32f66. The fixture test independently verifies that digest; equality to the original capture is orchestrator evidence from Amendment 2, since this lane did not read a real archive.

## Mandatory operational disclosures

- ZONE-derived dates are operator assumptions and may mislink repeated opponents. They are not payload proof. The adjacent MLB rematch construct selects the other encounter under UTC; independent start or source-ID evidence is absent from the linker call.
- America/New_York and America/Chicago dates differ only for starts in 04:00-05:00Z (EDT) or 05:00-06:00Z (EST).
- Tennis acceptance intentionally widens only for otherwise compatible identities whose missing date the declaration fills. Player names incompatible with ticker codes still refuse; filled dates do not establish schedulability.
- The Kalshi tennis and soccer ticker-date convention is NOT VERIFIED.
- MNF is scored by the 2026-09-29 paper night, which reads capture_root ingame_capture_view_v2, not the live root (S473).
- Hand-off applies only to unchanged starts and capacity-admitted rows. Full selection can retain a row omitted from the served subset.
- A moved MNF start can block every new row that night: conflicting_schedule_rows becomes pointer_schedule_refused at the public reader, retaining the prior schedule and excluding unrelated incoming rows.
- A local window was rejected because scripts/platformkit/ingame/schedule_pointer.py:72-75 requires one UTC day; scripts/platformkit/execution/schedule_d1.py:206-208 refuses invalid_schedule_scope; scripts/platformkit/ingame/local_capture_writer.py:129 writes UTC receipt shards; scripts/platformkit/execution/paper_night.py:94-95 reads day-named input. Changing those consumers would require a capture restart.

## Identity and A9 evidence (LF-normalised)

Base: the pinned pre-S477 commit 2b53bbb59cc3da0ff3154f49700b1529263cdf66 (landing prep, orchestrator 2026-09-28: forward_schedule_writer.py, forward_schedule_sources.py and schedule_d1.py are byte-equal between it and master 8cb4acc0c9d7af6c3e02fceb9533564895bfa4c7). ORCHESTRATOR LANDING EDIT (round 2 Opus correction): the e2e identity test now loads its base files from that pinned sha instead of the moving master ref, so it stays a real comparison after landing; its A9 row below was regenerated for that one-line change. The candidate remains an uncommitted overlay, so there is no candidate commit SHA.
The case table, pass-count table and following A9 table were generated together from the final files as the last edit. Byte counts and SHA-256 values use LF-normalised bytes; JSON resolution is n/a. This memo is excluded from its own hash.
Writer acceptance block :214-220 and source merge body after the sport guard are byte-identical to base (EQUAL). All eight landed tests and protected consumer modules in the table are EQUAL. No threshold changed.

| Path | LF-normalised bytes | Candidate SHA-256 | Base SHA-256 | Comparison |
| --- | ---: | --- | --- | --- |
| scripts/platformkit/execution/forward_schedule_local_date.py | 2318 | a4456375b8f1dc9ae3d47d7807c9bef95c1a8b7897d452d35ecf7212260aa1a4 | ABSENT | NEW |
| scripts/platformkit/execution/forward_schedule_writer.py | 15745 | a9bdd7f82c3e61dbde1051e7ccc82ba0a921dfc3653540a1766c5f442ac8dfc5 | b35456950e526616f9e93ff5ea6f846cdab8cfe1097e9ab004bd1ba19825c222 | NOT EQUAL |
| scripts/platformkit/execution/forward_schedule_sources.py | 11032 | 67905eb0a17dbc014100811d0caee379f8953d4710c0853597504620b710acb6 | bd55079f3e380cb6e2fcdd0541d7146bfba4be7b1f4c8a1ac04a6cc7e9b56444 | NOT EQUAL |
| scripts/platformkit/execution/schedule_d1.py | 13602 | b1a5e20f31ebf0d8e3eaefe4f906d44141f1de3fb5820c91eeb7dc2a511bf842 | 198501ae39525ca839f2acc99e46bc8d58324a0e4df5bf266806626113156588 | NOT EQUAL |
| docs/operations/FORWARD_SCHEDULE_RUNBOOK.md | 7021 | cddc3f4f6bd8709fc72b939502ff221be548c515ed14935eb600d784705d64ad | 6977244e2f8c76bff4d9355619c6c4be93eb3a922284cecded5d73080626571e | NOT EQUAL |
| tests/platformkit/execution/test_forward_schedule_local_date.py | 17769 | ded1fcb480fc1572a7cc345865e9998aa65c9e1e81ffc1944100c86a9420c49b | ABSENT | NEW |
| tests/platformkit/execution/test_forward_schedule_local_date_e2e.py | 16020 | 1c4d72e3d9572e73663f886fdc427bce5b9ab36a66d24244f69f161a38b987bd | ABSENT | NEW |
| tests/platformkit/execution/fixtures/s477_books_nfl_2026-09-28_lines1-2.jsonl | 10721 | e41812fe72a32a6c3f90587d189c89c2dd3f5bf83b29843158045e2b3ecb565f | ABSENT | NEW |
| tests/platformkit/execution/fixtures/s477_espn_nfl_20260928.json | 23204 | 98ba725daf5f6e9048d141a0fa0da927dfefb1f8ff84e14abc214489f84f3919 | ABSENT | NEW |
| tests/platformkit/execution/fixtures/s477_espn_nfl_20260929.json | 5193 | d32bdedc9f799a39a5728d8bd0c52d81096c889f596fde3cdd8b5d43bf46a8c5 | ABSENT | NEW |
| tests/platformkit/execution/fixtures/s477_state_nfl_2026-09-28_line16.jsonl | 1036 | 5e30e3e431445a7e4c9c4c9accbd20ad5bb6ea1ed3ad8cee5eb99f212fe80898 | ABSENT | NEW |
| docs/evidence/tracking/specs/S477_spec.md | 19165 | d1efa835bab5b90d779357690edfb9400fdf268699164af491fa56801e8199e4 | d1efa835bab5b90d779357690edfb9400fdf268699164af491fa56801e8199e4 | EQUAL |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 12392 | 63d8d126ea26492a12ecab2e74b48d736d30fc626c1162a338acaae6ddb2c341 | 63d8d126ea26492a12ecab2e74b48d736d30fc626c1162a338acaae6ddb2c341 | EQUAL |
| tests/platformkit/execution/fixtures/s430_espn_nfl_atl_gb.json | 749 | 4732455b8e2ccc9559b524522ee567b2a959aad97375e169d34cc5de880c3aba | 4732455b8e2ccc9559b524522ee567b2a959aad97375e169d34cc5de880c3aba | EQUAL |
| scripts/platformkit/ingame/schedule_pointer.py | 14857 | 57acd6eac54d28b777c8c8f71eadbd9876618ca8548ac11230cbce16a72574bd | 57acd6eac54d28b777c8c8f71eadbd9876618ca8548ac11230cbce16a72574bd | EQUAL |
| scripts/platformkit/execution/schedule_pointer_writer.py | 3187 | 60083a06dc144c604e138569e6d7926d813504035dbaffe1c0253931b5a54ad1 | 60083a06dc144c604e138569e6d7926d813504035dbaffe1c0253931b5a54ad1 | EQUAL |
| scripts/platformkit/ingame/capture_schedule_loader.py | 4375 | 84b81a18863ca17d41475a89f6bd9f578bd291b4a1f4a807a24f47691609f359 | 84b81a18863ca17d41475a89f6bd9f578bd291b4a1f4a807a24f47691609f359 | EQUAL |
| scripts/platformkit/ingame/local_capture_runner.py | 18177 | 5dedfaaf962131a433b88b18aef04189d7ede880b94463f05c45f7e2f971cff4 | 5dedfaaf962131a433b88b18aef04189d7ede880b94463f05c45f7e2f971cff4 | EQUAL |
| scripts/platformkit/ingame/local_state_capture_dates.py | 5400 | e86df18af4ced4d28796d9a11f706aebaae689c661dcdffedf1743c193c71475 | e86df18af4ced4d28796d9a11f706aebaae689c661dcdffedf1743c193c71475 | EQUAL |
| scripts/platformkit/ingame/game_market_link.py | 9209 | ae3a396b681024aa75bdeac46c7704531dba4d0dfc44fc524d8d688d477f8eae | ae3a396b681024aa75bdeac46c7704531dba4d0dfc44fc524d8d688d477f8eae | EQUAL |
| scripts/platformkit/execution/venue_time.py | 1972 | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 | EQUAL |
| scripts/platformkit/execution/paper_night.py | 15420 | 52af33074768a030ddac06e921b6a459e3a85cb4cf82942d4a37c4ca571ed32a | 52af33074768a030ddac06e921b6a459e3a85cb4cf82942d4a37c4ca571ed32a | EQUAL |
| scripts/platformkit/execution/paper_night_deadline.py | 14592 | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | EQUAL |
| scripts/platformkit/execution/paper_night_lock.py | 1069 | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | EQUAL |
| scripts/platformkit/execution/paper_night_peak.py | 2378 | 54aa53505a688f7dac8baf45a4aed003c8919c245d908aaff1341f80e9cf77de | 54aa53505a688f7dac8baf45a4aed003c8919c245d908aaff1341f80e9cf77de | EQUAL |
| scripts/platformkit/execution/paper_night_steps.py | 14942 | 3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 | 3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 | EQUAL |
| tests/platformkit/execution/test_forward_schedule_sources.py | 14635 | 76fae8fe5c05ba0433da462415382745811135fc784fbe2eb8706f41fd928a69 | 76fae8fe5c05ba0433da462415382745811135fc784fbe2eb8706f41fd928a69 | EQUAL |
| tests/platformkit/execution/test_forward_schedule_writer.py | 13869 | 4f5ba7baf3d957fff0f274a3e372f8fdf374ddcde863aa359b838fc2f30e1640 | 4f5ba7baf3d957fff0f274a3e372f8fdf374ddcde863aa359b838fc2f30e1640 | EQUAL |
| tests/platformkit/execution/test_forward_schedule_game_key.py | 4014 | 0dc0d8631c357e5db242227dfb9920ba099efdeb99084ddd6d4ee70de209fcc7 | 0dc0d8631c357e5db242227dfb9920ba099efdeb99084ddd6d4ee70de209fcc7 | EQUAL |
| tests/platformkit/execution/test_forward_schedule_team_set.py | 9213 | ad52012335e6ff2fafce43fa9fc686da5363264bcb7f337c618e22c85330039e | ad52012335e6ff2fafce43fa9fc686da5363264bcb7f337c618e22c85330039e | EQUAL |
| tests/platformkit/execution/test_forward_schedule_fix1f.py | 9095 | f3761097ba6d2abf5392e47f86c77d445d4c01848e2044fa98e85da41cbfb631 | f3761097ba6d2abf5392e47f86c77d445d4c01848e2044fa98e85da41cbfb631 | EQUAL |
| tests/platformkit/execution/test_forward_schedule_dates.py | 17802 | 8e8a321a33769e6bfccbf1ba516ffc1763abfd067813f402f3866266de825b53 | 8e8a321a33769e6bfccbf1ba516ffc1763abfd067813f402f3866266de825b53 | EQUAL |
| tests/platformkit/execution/test_forward_schedule_utc_day.py | 12617 | 3edb017ad359b039ffc392ed29b6559a164b005691916cbd801906ea688a61db | 3edb017ad359b039ffc392ed29b6559a164b005691916cbd801906ea688a61db | EQUAL |
| tests/platformkit/execution/test_schedule_d1.py | 13041 | e936d065f38d9073c64ed181299e7db2887e421896fb10d50735a08ed5970a89 | e936d065f38d9073c64ed181299e7db2887e421896fb10d50735a08ed5970a89 | EQUAL |

## NOT VERIFIED

- Live 2026-09-29 D1 publication and its pointer read by the running capture.
- Per-sport link rates under the flag and paper-night scoring of MNF.
- Independent identity evidence for repeated opponents: this design has none at the linking call; the counterexample demonstrates mislinking.
- Real archive-mode success for the supplied null-start row; only the explicitly constructed derivative succeeds.
- Actual tennis and soccer ticker-date conventions; constructed compatible identities are not evidence of real link rates.
- Machine crash or power-loss behavior; landed write durability is unchanged.
