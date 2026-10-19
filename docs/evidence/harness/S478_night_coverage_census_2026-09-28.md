# S478 nightly coverage census - FIX 1b - 2026-09-28

CANDIDATE FIXED: all 23 enumerated construct/fixture case groups pass; independent landing verification remains pending. Counts only.
Machine: local Windows laptop, C:/Users/neelj/nba-harness-h127. This fix ran construct/fixture checks only, without network, pod or archive census.
Binding spec: docs/evidence/tracking/specs/S478_spec.md, including AMENDMENT 1(a)-(i) and the overriding AMENDMENT 2(a)-(d).
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, including Q6.
The source provenance below is retained from FIX 1a; FIX 1b read construct/fixture inputs only and did not reopen the source archive.

## FIX 1a
Every numbered finding below was reproduced before its implementation edit. The price-domain ruling supersedes the original requested removal of the ceiling.
- (a), sol 1: D+2 scorer ts returned `{'value': True, 'reason': 'valid_pair_present'} {}`; ts `bad` returned the same. Now both targets validate ts with io.instant, which uses parse_venue_time and exact Decimal fractions. Recheck: D+2 returns `{'value': False, 'reason': 'no_valid_loss'} {'outside_observation_window': 1}`; bad returns false with `{'invalid_timestamp': 1}`. Regression covers before D, D, the last nanosecond before D+2, D+2, one nanosecond later, missing/bad timestamps and reversed pair order.
- (b), sol 2: reproduction printed `b zero: True listed: False` and `b captured: True listed: False`. Both now print `listed: True`. Lists are computed across all reports before the fixed/discovered partition. Regression checks both ncaaf memberships.
- (c), sol 3 / Opus B1: source probe printed `copied fixture references: []`. Case 1 now copies all seven named fixtures to tmp_path and asserts four scheduled/served games, all five stages true, three next-shard finals, sidecar written four and its complete counts, and WNBA's six reasons. Recheck finds all six filename stems (state supplies two files); case 1 passes.
- (d), sol 4 / Opus N1: original all-file preflight printed `FAIL vocab 17 hit(s)`. Deterministic field projections remove unread depth and timestamp metadata. Retained timestamps and numeric values are exact; no retained value rewrite was necessary. After projection: `PASS vocab clean over 13 files`. Source and selected-line hashes are below.
- (e), sol 5: reproduction of (101, 1) returned captured null, reason shard_partial, invalid_price_value 1. AMENDMENT 2(a) overrides the earlier wording: finite 0 <= p <= 100, with 0 a valid empty side. Added the 0, 1, 100, 101 boundary regressions. Results: 0 false/no_two_sided_snapshot; 1 and 100 true/observed; 101 null/shard_partial with invalid_price_value 1. Zero remains a non-two-sided observation without a value-refusal count.
- (f), sol 6: duplicate response_end_ts returned `['invalid_timestamp']`. Now it returns `['duplicate_json_key']`. The shard reader refuses duplicate keys before interpreting timestamps. Regression covers book and state timestamp keys with valid, invalid and future values.
- (g), Opus C1: a scheduled state key produced `'series_unresolved': 1` despite an empty unscheduled list. Now only books increment series_unresolved_book_rows; series_unresolved_state_game_keys is the length of the unresolved unscheduled-state bucket. Recheck: scheduled state count zero; regression adds one unscheduled key and two unresolved book rows and expects counts one and two.
- (h), Opus N2-N4: serializer probe printed `numeric value silently published: 0 {"bad": "0.1"}`. Removed the default conversion; recheck raises `Object of type Decimal is not JSON serializable`. Regression confirms failure before output publication. Existing invalid_count, invalid_price_value, whole-receipt invalidation and configured ncaaf emission are disclosed below.
- (i), Opus C2-C3: memo probe printed `stale slice NOT RUN: True stale base: True`. This regenerated memo records case 1 PASS, every fixture's A9 identity, a fixed base, and the attributed prior archive result. Obsolete copy instructions and absent-source statements were removed.

## FIX 1b
Scope is exactly AMENDMENT 2(a)-(d). The original runtime behavior was correct for these cases; the failures below reproduce missing test protection and stale memo identity. No price code or other confirmed behavior changed.
- (a), sol finding 1 overridden by AMENDMENT 2: before editing, 0 returned `{'value': False, 'reason': 'no_two_sided_snapshot'}` without invalid_price_value; 100 returned true/observed; 101 and -1 returned null/shard_partial with invalid_price_value 1. The requested rejection of zero is superseded. Kept the implementation, corrected the wording, and extended the boundary regression to -1 with exact observation and counter dictionaries. All five price parameters pass. No failing price-code reproduction is claimed.
- (b), sol finding 2, case 7: in-memory mutation reproduction printed `FAIL b: case 7 passed with receipt failure value=False`. The four receipt failures now assert complete dictionaries for both scored targets and both games, including value None, per-game conflict isolation and exact receipt_counts. Recheck: all four mutations are rejected; each prints `PASS b: case 7 rejects value=False for` its refusal reason.
- (b), sol finding 2, case 10: in-memory mutation reproduction printed `FAIL b: case 10 passed with outside_observation_window removed`. The boundary, invalid timestamp and no-final cases now assert exact raw-final dictionaries and complete sport counters, including outside_observation_window 1 or invalid_timestamp 1. Recheck prints `PASS b: case 10 rejects missing outside_observation_window` and `PASS b: case 10 rejects missing invalid_timestamp`.
- (c), sol finding 3: reproduction printed `FAIL c: case 19 passed with unknown zero_coverage changed to False`. The same zero-schedule WNBA sport now has an unreadable shard injected separately for book and state. Both regressions require zero_coverage None, exact shard_read_error 1 and absence from both zero lists. Both mutations are rejected; recheck prints `PASS c: case 19 rejects false zero_coverage for unreadable book` and the same for state.
- The owned census module's observation, receipt_stages and sport_report API docstrings now state the unknown-value and timestamp-counter contracts exercised by (b)-(c). This is the required module edit; executable behavior is unchanged. Test formatting was compacted solely to keep the file at 300 lines.
- (d), sol finding 4 / Opus C1: reproduction printed `FAIL d: memo base df7367408e327fcbbf2151235883940fc99fd4d8 HEAD 7871e08cbd1b611f1aecc23b5d74df1685c2aac2 EQUAL=False`; the old-base full-tree diff exited 1. The identity section below is regenerated against the actual fixed parent. Assertions verify parent equality, no tracked changes and no owned-path overlap through the fast-forward. This memo regeneration is the final edit.
- Verification: 40 unit tests, 13 end-to-end tests, eight mutation checks, CLI help exit 0, and all nine preflight checks pass. Mutation probes ran in memory with construct inputs in system temporary storage; no scratch files were created in the worktree.

## Cases and reproduction
Acceptance bar remains 23 of 23; n = 23 (CONSTRUCT). All 23 groups pass; parametrized tests additionally cover the fix regressions.
| Case | Exercised behavior | Result |
|---|---|---|
| 1 | Seven projected real-row fixtures; four scheduled and served, sidecar counts, all five stages true, three next-shard finals, six WNBA reasons. | PASS |
| 2 | Full price table; bulk snapshot; derivative exclusion. | PASS |
| 3 | Escaped snapshot token and malformed line. | PASS |
| 4 | Duplicate/conflicting identities and tickers; both orders; served refusals; reconciliation. | PASS |
| 5 | One distinct identity, two game-nights with independent observations. | PASS |
| 6 | Mid-only pairs; empty, non-finite and non-string losses. | PASS |
| 7 | Exact observations for both targets, receipt refusal counters and per-game isolation. | PASS |
| 8 | Missing receipt and REFUSED/free_ram_below_floor night context; absent/invalid/missing-step reasons. | PASS |
| 9 | Unknown schedule population; invalid rows; served and census refusals; all document read errors. | PASS |
| 10 | Exact boundary observations and counters, nanosecond preservation and naive-time refusal. | PASS |
| 11 | Absent versus next-day-only book and state observations. | PASS |
| 12 | Unreadable/partial stays unknown; positive evidence wins; other sports isolated. | PASS |
| 13 | Malformed metadata, missing identity, sport mismatch and future-row filtering. | PASS |
| 14 | Exact line cap, cap+1 and generated 200001 identities. | PASS |
| 15 | Generated 250 MiB shard and at least 4 MiB receipt; bounded CLI process peak. | PASS |
| 16 | Growth after fstat, CRLF actual hash and torn tail. | PASS |
| 17 | Overlapping nights reuse one shard and A9 record. | PASS |
| 18 | Configured zero series, tennis prefixes, unresolved soccer and disagreeing book series. | PASS |
| 19 | Imported constants; UCL-only capture; unreadable book/state of the zero-schedule sport is unknown and absent from both zero lists. | PASS |
| 20 | ncaaf discovery, ignored non-sport files and only two shard dates opened. | PASS |
| 21 | Date, range and either existing output refuse before input opens. | PASS |
| 22 | Second output creation failure removes first output. | PASS |
| 23 | Fresh CLI plus independent strict parser, recomputed tallies/markdown, hashes, input immutability, network and write guards. | PASS |

Final per-file output from this fix session:
```text
python -m pytest tests/platformkit/execution/test_night_coverage_census.py -q -p no:cacheprovider
40 passed in 2.77s
python -m pytest tests/platformkit/execution/test_night_coverage_census_e2e.py -q -p no:cacheprovider
13 passed in 8.31s
```
CLI: python -m scripts.platformkit.execution.night_coverage_census --help exited 0.
Neither owned module defines a self-check command; the IO module has no CLI.
Case 15 uses generated inputs in system temporary storage and passes the unchanged memory bound. No new archive measurement was performed or claimed in FIX 1b.
Final contract_preflight covers all 13 candidate files, excluding the verifier file; all 9 mechanical checks PASS.
Prior FIX 1a peer review is historical; FIX 1b has no new independent review yet.

## Prior independent verifier evidence
The binding verdict and AMENDMENT 1 record Opus's prior real 2026-09-24 archive run: exit 0 in 37 seconds, process_peak_bytes 55799808, four MLB scheduled/served games, all five stages true for all four, and three finals observed only in the next UTC shard.
Those are attributed verifier observations, not a new archive run by this fix lane. The present case 1 independently exercises only the seven projected fixture files.
The earlier verifier's unavailable-temporary-directory note is resolved for this session by both executed per-file results above.

## Deterministic fixture projections
The following projection rules replace the old verbatim-copy requirement under AMENDMENT 1(d).
- Book rows retain sport, ticker, series, record_type, yes_bid, no_bid and response_end_ts.
- State rows retain sport, game_key, status and response_end_utc.
- Full-selection and served rows retain sport, game_key, ticker, game_id and scheduled_start.
- Census rows retain games_seen, linked, written and refused_by_reason for each sport.
- Receipt retains date, counts, games with the schedule identity fields, and the chosen paired_losses rows with sport, game_key, target, ts and losses.
- All other fields are dropped, including order-book depth, selected_at and census refused_team_evidence. This resolves the timestamp-metadata vocabulary hits without changing retained instants.
- Output uses sorted JSON keys, compact separators, ASCII and one LF per object/document. Input numbers are decoded with Decimal and emitted numerically without conversion through float.
Source paths below resolve to those same absolute local paths. Source sizes/hashes and line hashes use actual bytes including original line endings. Line numbers are one-based; receipt array indexes are zero-based.

| Fixture | Full source path / resolved path | Source bytes | Source SHA256 |
|---|---|---|---|
| s478_books_2026-09-24.jsonl | C:/Users/neelj/nba-ai-system/data/cache/ingame_books_local/kalshi/mlb/2026-09-24.jsonl | 242437642 | 40ff81365a0787a9cf6bbf6bc0e89ca9c13d42330259ca53eafca8c7289289c6 |
| s478_census.json | C:/Users/neelj/nba-ai-system/docs/evidence/forward/schedules/2026-09-24_maker_forward_full_selection.json.census.json | 4585 | 3f88691baf275426707120b4add06b7e9118f6525275565f987473187fbfd7ff |
| s478_full_selection.json | C:/Users/neelj/nba-ai-system/docs/evidence/forward/schedules/2026-09-24_maker_forward_full_selection.json | 1159 | 1ee2144f9838baf6a9ce4f175a75d604fb6f82c0bba72f82269d1456e367c846 |
| s478_receipt.json | C:/Users/neelj/nba-ai-system/docs/evidence/forward/scoreboard/2026-09-24.json | 3443097 | 2f8a2a7d6b4c2d80466520ccce4e3442fe22cbff57039450acf94e82d959ef06 |
| s478_served.json | C:/Users/neelj/nba-ai-system/docs/evidence/forward/schedules/2026-09-24_maker_forward.json | 1131 | 686462bba2b0f32e32515ea9b22dafa93ef55c21d4a4fa694b6733d5ddcb7e21 |
| s478_state_2026-09-24.jsonl | C:/Users/neelj/nba-ai-system/data/cache/ingame_state_local_v2/state/mlb/2026-09-24.jsonl | 3357987 | 3a38143b1133abab5fab758da63fc922ca058ba03a9ebb8c0ff3bd4beb483adf |
| s478_state_2026-09-25.jsonl | C:/Users/neelj/nba-ai-system/data/cache/ingame_state_local_v2/state/mlb/2026-09-25.jsonl | 12514458 | 4bc8b4cf619d8052ecb1765d6859897070f2c8e1cc278634f9171924b74adefc |

| Fixture | Fixture line | Source line | Source line bytes | Source line SHA256 |
|---|---|---|---|---|
| s478_books_2026-09-24.jsonl | 1 | 8275 | 5125 | 5124915fe7b3de23524c66a22d26289fc2d01a168e61111ae8e5047e502a4203 |
| s478_books_2026-09-24.jsonl | 2 | 115918 | 5203 | 9ded071beb52a8925a01b236a668e6f2616b6775a045ecd584f9a1ea422b7976 |
| s478_books_2026-09-24.jsonl | 3 | 133838 | 5184 | 5552ae97d15747fdad41636f7a1aa300f92cf419bffb85ea8df83ace5aba8377 |
| s478_books_2026-09-24.jsonl | 4 | 149124 | 5169 | 03278c2aa4f8844e558dfefa9f796dea6996fc1f2d6f823bb580454bf4b1705f |
| s478_state_2026-09-24.jsonl | 1 | 2 | 960 | 247e8ae4f8c5bb47347043ebe85dc83f0d6d34b6387bf0a25c49295362802fdb |
| s478_state_2026-09-24.jsonl | 2 | 9 | 658 | e30a21b2ea4ccae4fd9bab58fa5b6278bd29a2f35b73394fdf62280764da7097 |
| s478_state_2026-09-24.jsonl | 3 | 21 | 658 | 9b6fbe8c4deb1cea4368a3d54300c8e51b6cd7426c202349855e8fa0eff4a9b6 |
| s478_state_2026-09-24.jsonl | 4 | 25 | 658 | 2421b876f8e959e6f4ad33c699a7f9cb88f2afc81d919ab043af265cfaaee0e0 |
| s478_state_2026-09-24.jsonl | 5 | 1951 | 1021 | 208a3c9cd3be42620fabe80778703ea5702040747df26764ec9fc1648e59ee5d |
| s478_state_2026-09-25.jsonl | 1 | 1525 | 1025 | f3c9252d3a81fbacfdf10362538b6f712369d0b3098da00268e4e0e0ad58c76a |
| s478_state_2026-09-25.jsonl | 2 | 2003 | 1025 | 317f2541b18247fc853023534ae7cddec2c0e216a8446b33ded5d2af1d94820a |
| s478_state_2026-09-25.jsonl | 3 | 3186 | 1025 | 10d01f80d4790135aa84500c60b4c58f5934229b0bd758719dbdb7fb1fda9bb8 |

Schedule and census projections use the complete named JSON documents; their exact source hashes are in the source table. The receipt occupies source line 1, whose byte count and SHA256 equal its complete source row above. Its selected pair indexes are:

| game_key | target | paired_losses index | Source line |
|---|---|---|---|
| 822842 | mid | 1 | 1 |
| 822842 | outcome | 0 | 1 |
| 823411 | mid | 521 | 1 |
| 823411 | outcome | 520 | 1 |
| 824707 | mid | 1653 | 1 |
| 824707 | outcome | 1652 | 1 |
| 824866 | mid | 2731 | 1 |
| 824866 | outcome | 2730 | 1 |

## Candidate identity and A9
Generated by one inline Python script from final on-disk artifacts as the last edit. Owned-code hashes are LF-normalised; fixture hashes use actual bytes (already LF). Resolution is the absolute local path.
Pinned base full SHA: 7871e08cbd1b611f1aecc23b5d74df1685c2aac2.
Candidate commit: NOT CREATED (sandbox). Worktree parent equals the pinned base: EQUAL. Candidate files are absent from that base: NOT EQUAL. All pre-existing tracked files compare EQUAL to the pinned base (git diff exit 0).
The worktree fast-forwarded from the previous pin df7367408e327fcbbf2151235883940fc99fd4d8 to this fixed parent. The old pin is an ancestor (exit 0), and git diff over every owned path between these fixed shas exits 0: no owned path overlaps the fast-forward.

| Owned artifact | Resolved path | Bytes | Lines | SHA256 | Base comparison |
|---|---|---|---|---|---|
| scripts/platformkit/execution/night_coverage_census.py | C:/Users/neelj/nba-harness-h127/scripts/platformkit/execution/night_coverage_census.py | 19145 | 286 | b3e039f1446ad0dae10ad53f62119f7ff236ee830da635fe506ab0ab4ebf9bfe | ABSENT / NOT EQUAL |
| scripts/platformkit/execution/night_coverage_census_io.py | C:/Users/neelj/nba-harness-h127/scripts/platformkit/execution/night_coverage_census_io.py | 11706 | 290 | 643a40be5ddbeab6a38f10eb6643f720449917b29c9999c3b5fad3d5b7f5f909 | ABSENT / NOT EQUAL |
| tests/platformkit/execution/test_night_coverage_census.py | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/test_night_coverage_census.py | 20686 | 300 | 82740b306ef0203f8a8edbb7d2ff707852bec6b004d288cf91bd59751793a945 | ABSENT / NOT EQUAL |
| tests/platformkit/execution/test_night_coverage_census_e2e.py | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/test_night_coverage_census_e2e.py | 13690 | 290 | b45def79f3b6f8c6eed2c3807aca46e05e2ca3ba0366c7aaa9a80dfd47a45d25 | ABSENT / NOT EQUAL |
| tests/platformkit/execution/fixtures/s478_books_2026-09-24.jsonl | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/fixtures/s478_books_2026-09-24.jsonl | 744 | 4 | 7eef2ee76ef4e4a9628bd861dd8b1c6b4b7809bfedf3f1bb09301761b5cb6399 | ABSENT / NOT EQUAL |
| tests/platformkit/execution/fixtures/s478_census.json | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/fixtures/s478_census.json | 235 | 1 | 6b5fd015f701b728bf4c4e9b1a17a1537e386588138078fbf44f93dbd86774fa | ABSENT / NOT EQUAL |
| tests/platformkit/execution/fixtures/s478_construct.json | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/fixtures/s478_construct.json | 385 | 7 | dade38cb2fc1dedec84c1875b05bf13a929ab617d7fd177d250ca7efcd8badcc | ABSENT / NOT EQUAL |
| tests/platformkit/execution/fixtures/s478_full_selection.json | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/fixtures/s478_full_selection.json | 670 | 1 | 211dae51e06e5e3437671536eecfb4cbcbcc43fbc164542ae5bc446bd0348c48 | ABSENT / NOT EQUAL |
| tests/platformkit/execution/fixtures/s478_receipt.json | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/fixtures/s478_receipt.json | 2165 | 1 | 5bc12c77fa604961ea0c874e0d9624cafe1a8b2130ca02cb6d079994e88947b7 | ABSENT / NOT EQUAL |
| tests/platformkit/execution/fixtures/s478_served.json | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/fixtures/s478_served.json | 670 | 1 | 211dae51e06e5e3437671536eecfb4cbcbcc43fbc164542ae5bc446bd0348c48 | ABSENT / NOT EQUAL |
| tests/platformkit/execution/fixtures/s478_state_2026-09-24.jsonl | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/fixtures/s478_state_2026-09-24.jsonl | 503 | 5 | 29f19c544b1263c8136914ddfbdab6733f11496e32e5a2798648341ec23821ef | ABSENT / NOT EQUAL |
| tests/platformkit/execution/fixtures/s478_state_2026-09-25.jsonl | C:/Users/neelj/nba-harness-h127/tests/platformkit/execution/fixtures/s478_state_2026-09-25.jsonl | 306 | 3 | 7979524eed23020cd58bc2ba62594d0e1f33ce71547185c6dfbb2b196df88902 | ABSENT / NOT EQUAL |
The memo has no self-hash because that would be circular. No candidate SHA is invented.

## Mandatory disclosures
Observations are at read time within recorded byte boundaries. raw_final_status_observed is not settlement: scorer deduplication, outcome extraction and conflict checks are not reproduced; tennis cancellation is final. scored_* means valid pairs are present, not a calibration result.
The observation window is [D, D+2); paper-night fill reads D only. The capture view is a junction pair described by the binding spec. The current state producer polls EPL only for soccer, so its other leagues have no state rows. Counts only.
invalid_count refuses provided capture_sequence or http_status values that are not nonnegative integers. Missing optional counter fields are not synthesized as zero. invalid_price_value refuses non-finite, negative or above-100 numeric prices; zero is a valid empty side; nonnumeric prices use invalid_price_type. A non-integer or negative value anywhere in receipt counts makes the whole receipt invalid.
Every configured WINNER_SERIES sport is emitted, including ncaaf even without a discovered directory. It is partitioned into other_sports while still participating in both zero lists.
Every caught exception in the owned route counts a refusal, records a reason, or re-raises. No landed module, input schedule, original receipt, night record, feature flag or registry file was changed.

## NOT VERIFIED
- Real 2026-09-23 through 2026-09-25 archive run and publication under docs/evidence/forward/census; the prior single-day run is attributed above.
- Observations beyond the exclusive D+2 boundary, settlement, calibration, network providers and any pod route.
- Power loss or process termination between publications; tests inject caught write failures. Concurrent writers remain outside the single-writer contract.
- Native junction failure and dangling-link creation; existing tests inject resolution failures and use regular files for output refusals.
- Independent landing verification and a committed candidate.
