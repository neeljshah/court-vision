# S489 FIX r2 - construct acceptance established

Machine: local Windows, C:/Users/neelj/nba-harness-h139. Construct/fixture execution only.
Pinned baseline: 70e299544f0b6817aa6595714d73ea363c8e8b27.
Acceptance: 12/12 enumerated construct cases established against AMENDMENT 2.
Final per-file results: 338 passed, 0 failed, 0 skipped across 14 files.
Orchestrator C20 evidence is recorded below; no real archive was run in this lane.
SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX r1

The root _verdict_s489_r1.md was read first; all ten amendment findings and
adjudications (i)-(iii) bind this fix. The following reproductions were run before
changing the affected code. Existing correct behaviors and protected modules stay intact.

| Finding | Reproduction / failing output before fix | Exact correction and regression |
|---|---|---|
| 1. State dependencies | fields: `8 failed, 25 passed, 1 skipped`; state-change assertion differed; three transition cases: `Failed: DID NOT RAISE` | Retain sport/game_key/state_changed for microstructure; half AND outs for transition-sensitive blocks. Missing/null/non-dict tests remain. State-change, three transition and conditional-field tests pass. |
| 2. Canonical ties | snapshots: `AssertionError: assert '0.8' == '0'`; trades: `AssertionError: assert '1' == '9'`, each in both permutations | Compact canonical ranks retain original full-row order within tied receipts. Both permutations, duplicate IDs, tie-key deletion control and exact fractional receipt tests pass. |
| 3. Non-vacuous differential | capacity: `2 failed, 17 passed`; C1: `At index 417 diff: b'3' != b'6'` | Two embargo-eligible opposite-outcome histories plus target; isolated outputs; nonempty C/E predictions in BOTH runs; varied fields, valid prior change and in-window trades. Compare full output and entire receipt after normalizing only isolated output path and verifying its digest. Five deletion controls cover defaults and tie metadata. |
| 4. Parameter collision | Before source signature exposed `selected: tuple[str, ...]`; earlier candidate avoided the collision by renaming schedule locals | Use explicitly authorized selected_blocks parameter; original timestamp locals restored. C11 checks the tuple and unchanged three config reads. |
| 5. Paths | capacity drive case: `Failed: DID NOT RAISE <class 'ValueError'>`; night_1b: `1 failed, 14 passed`, inside-root absolute path raised `ValueError: capture_escape` | Lexical containment with drive/root handling; all seven amended escapes rejected before reader; inside-root absolute and normalized paths accepted; real junction read retains lexical label. |
| 6. Caller compatibility | e_step_e2e: `2 failed, 39 passed`; `AssertionError: expected call not found` (seven expected arguments vs added tuple) | Narrow authorized spy change requires selected_blocks keyword; scalar/path positional assertions and behavior remain. Direct seven-argument calls use None and preserve full rows. |
| 7. Replay | `python -m scripts.platformkit.execution.registry_scorer_e_night_replay --help`: `No module named scripts.platformkit.execution.registry_scorer_e_night_replay` | New owned driver requires its SHA and explicit replay date; validates unchanged seals, records selection/counts/memory/time, rejects empty construction and bypassed scoring. Thirteen construct tests pass. |
| 8. Capacity unestablished | No lane measurement authorized; the old candidate also lacked real C20 evidence | Retain unmeasured status and fixed 629145600-byte/600-second bars. SQLite fallback stays a separate future row if real C20 fails. |
| 9. Activation restriction | Existing pinned-budget regression was already PASS; no defect was reproduced in that correct check | Preserve production budget byte-for-byte; no custom activation path added. Replay directly exercises population/scoring and does not call supervisor or publish a night. |
| 10. Scope/line cap | Original spec said nine while enumerating ten legacy files; AMENDMENT 1 supersedes that contradiction | Ten legacy files exercised. Only owned modules plus the amendment-authorized spy are changed; all changed Python files <=300 physical lines. |

The tie mechanism keeps a compressed canonical full-row ordering key temporarily
on each projected dictionary. After the causal reader has selected accepted rows,
finalize_rows groups states with the immutable adapter rounded-microsecond key;
book/trade groups retain the exact microstructure receipt and record type. Within each tied group it sorts the original canonical keys
and writes fixed-width ranks under a first-sorting reserved key. Every row and its
file position remain; duplicate diagnostics remain possible. It then deletes all
temporary compressed payloads. Non-tied rows have no ordering key. The collector
cannot expose a future row to this ranking. Original receipt strings and Decimal values remain intact; no field value is coerced, defaulted, or repaired.

The old eight field failures, two capacity failures, one night_1b failure and two
e_step_e2e failures are all resolved. The C6 skip was removed. The supplied fixtures
are NEW owned files; source rows were not regenerated or edited. Pattern added to
.gitattributes: `tests/platformkit/execution/fixtures/s489_verbatim_*.jsonl text eol=lf`.
No new persistent JSON seal was created.

## Per-case acceptance

| Case | Result | Runtime regression evidence |
|---|---|---|
| C1 | PASS | Seven-block main differential; nonempty fitted C/E; full output, nested census and receipt equal; five deletion controls differ |
| C2 | PASS | Final state settles with only mid selected |
| C3 | PASS | Selected state sets and declared join keys vary correctly |
| C4 | PASS | Fixed mid book fields survive without microstructure |
| C5 | PASS | Conditional microstructure fields and smaller projected rows |
| C6 | PASS | Nine verbatim rows, three exact source digests and regenerated byte table |
| C7 | PASS | Relative normalization and absolute-inside-root labels |
| C8 | PASS | Seven amended escapes rejected before reader |
| C9 | PASS | Real Windows junction read, lexical label, no skip |
| C10 | PASS | Missing/null/malformed values, refusals, state changes, transition checks, canonical ties and future filtering |
| C11 | PASS | Existing selected tuple threaded once; three existing config reads; legacy compatibility |
| C12 | PASS | Ten legacy files: 218 passed; only permitted e_step spy changed; budget/protected identities checked |

## Verbatim fixtures and reproducible byte table

Command: `python -m scripts.platformkit.execution.registry_scorer_e_night_fixture`.
The reporter validates all source pins and emits every supplied row. Original archive
paths below are provenance only; this lane opened only fixture copies. Source game
822842 NYM@TEX; book ticker KXMLBGAME-26SEP241435NYMTEX-NYM.
Raw-line bytes include LF. Compact columns exclude LF, use the caller's Decimal
parsing and canonical default=str serialization. Retained includes final tie ranks.
AMENDMENT 1 supersedes the original three-row sizes; these values are script-derived.
Resolution: N/A (JSON/text, no media).

| Fixture path | LF bytes | LF SHA256 | Original source path | Lines |
|---|---:|---|---|---|
| tests/platformkit/execution/fixtures/s489_verbatim_state_2026-09-24.jsonl | 2942 | f696e158acc1edf10f029aa0b9de5a87cb4f51c32101d80c6e682064c4804aff | data/cache/ingame_capture_view_v2/state/mlb/2026-09-24.jsonl | 2,29,1951 |
| tests/platformkit/execution/fixtures/s489_verbatim_book_2026-09-24.jsonl | 10926 | 0374ff8520c52fe1af4eae08fac2cf5e2e04dc0f73a850bec5d4fc4a1bc090cf | data/cache/ingame_capture_view_v2/kalshi/mlb/2026-09-24.jsonl | 7296,7297,8274 |
| tests/platformkit/execution/fixtures/s489_verbatim_trade_2026-09-24.jsonl | 3279 | 06ac821d7a9cbe766f75a8ef3e6a9ff340d6b3d9bb48f5c2b637b53e6ce241a6 | data/cache/ingame_capture_view_v2/kalshi/mlb/2026-09-24.jsonl | 1712,1713,1714 |

| Kind | Source line | Raw line | Raw compact | Projected | Retained |
|---|---:|---:|---:|---:|---:|
| state | 2 | 960 | 959 | 363 | 363 |
| state | 29 | 961 | 960 | 364 | 364 |
| state | 1951 | 1021 | 1022 | 364 | 364 |
| book | 7296 | 2855 | 2870 | 336 | 359 |
| book | 7297 | 2870 | 2885 | 341 | 364 |
| book | 8274 | 5201 | 5258 | 388 | 388 |
| trade | 1712 | 1093 | 1092 | 305 | 328 |
| trade | 1713 | 1093 | 1092 | 305 | 328 |
| trade | 1714 | 1093 | 1092 | 305 | 328 |

## Full field-citation list (pinned source line numbers)

- registry_scorer_e_ticks.py:46,73 response_end_utc; :70,191 status; :73 settlement.
- ingame_scoreboard_rules.py:94 home_abbr/away_abbr; registry_scorer_e_night.py:141-144 orientation.
- ingame_scoreboard_rules.py:66-68 state.score_home/score_away; :93 unconditional ticker settlement.
- registry_adapters.py:58 ticker; :228 causal response_end_ts.
- ingame_scoreboard_rules.py:76,80-81 event_ticker/venue/yes_bid/yes_ask/raw_market.yes_sub_title.
- registry_scorer_e.py:238 always prepends mid, making these book fields fixed.
- registry_scorer_e_night.py:128 shared response_end_ts filter; :133 ticker dispatch;
  :134 record_type classification precedes projection and alone does not require retention.
- registry_adapters.py:250 recombines book/trade; microstructure_features.py:163,166,171
  reuses sport/record_type after projection, requiring conditional retention.
- registry_scorer_e_ticks.py:92 combines required_fields and join_fields;
  feature_registry.py:100-102 source_key translates half_bottom to half.
- feature_registry.py:181-182 team_state inning/outs plus fixed scores;
  :188-190 player_pitcher_workload pitcher_pitches/pitcher_id/batter_id;
  :89,229 half_inning half; :230 base_occupancy on_first/on_second/on_third;
  :231 ball_strike_count balls/strikes.
- microstructure_features.py:66,70,80,98,110,120,125,163,166,171,177 consumes conditional
  book sport/record_type/capture_ts/no_bid/yes_bid_size/no_bid_size and trade
  sport/record_type/capture_ts/created_time/trade_id/taker_side/count_fp.
- Confirmed missing dependencies: microstructure_features.py:142,146 state_changed;
  feature_registry.py:117 half AND outs; microstructure_features.py:39 entire-row
  canonical JSON, :63 last tied snapshot, :115 first duplicate trade in that order.

## Reproduction and final checks

Every pytest invocation used `python -m pytest tests/platformkit/execution/<file>
-q -p no:cacheprovider`, one file per process, with a unique workspace basetemp.
The FIX r2 counts below cover all 14 files. No suite invocation occurred.

| File | Passed | Failed | Skipped |
|---|---:|---:|---:|
| test_registry_scorer_e_night_fields.py | 52 | 0 | 0 |
| test_registry_scorer_e_night_capacity.py | 33 | 0 | 0 |
| test_registry_scorer_e_night_fixture.py | 16 | 0 | 0 |
| test_registry_scorer_e_night_replay.py | 19 | 0 | 0 |
| test_registry_scorer_e_night.py | 33 | 0 | 0 |
| test_registry_scorer_e_night_1a.py | 13 | 0 | 0 |
| test_registry_scorer_e_night_1b.py | 15 | 0 | 0 |
| test_paper_night_e_step_e2e.py | 41 | 0 | 0 |
| test_paper_night.py | 39 | 0 | 0 |
| test_paper_night_steps.py | 56 | 0 | 0 |
| test_paper_night_scoreboard_step.py | 14 | 0 | 0 |
| test_paper_night_scoreboard_step_1c.py | 4 | 0 | 0 |
| test_paper_night_scoreboard_step_1d.py | 2 | 0 | 0 |
| test_paper_night_scoreboard_step_1e.py | 1 | 0 | 0 |

CLI --help: night, fixture reporter, replay driver each exit 0. Replay --self-check:
PASS, replay_executed=false, ceiling_bytes=629145600, deadline_s=1500. The fields
companion exposes library functions only. Contract preflight over the 14 owned
paths (excluding the verdict), --base master and --spec docs/evidence/tracking/specs/S489_spec.md:
all nine checks PASS. Only this user-required preflight uses the moving base;
all test and memo byte comparisons use the full immutable baseline above.

Scratch .s489_tmp/ and .s489_verify/ remains untracked and is excluded from
lane_commit inputs, as AMENDMENT 2(f) directs. No cleanup was attempted in r2.

## Orchestrator C20 evidence (supplied; not rerun in this lane)

The driver validates the original block seal before changing effective_from only
in its temporary in-memory return value. Original effective_from is recorded in
its report. No seal, caller policy, supervisor or budget is rewritten. Fixed replay
window 2026-09-22..28, as_of 2026-09-29T06:00:00Z. Selected tuple:
(mid, team_state, microstructure, player_pitcher_workload, half_inning,
base_occupancy, ball_strike_count). Populated state/book/trade and actual scoring/fit
invocations plus eligible/output counts must be nonempty. RSS sample errors fail
the qualification. Sampling interval is 0.01 seconds, recorded explicitly.

```text
python -m scripts.platformkit.execution.registry_scorer_e_night_replay --orchestrator-replay --capture-root data/cache/ingame_capture_view_v2 --served-schedule "docs/evidence/forward/schedules/{date}_maker_forward.json" --prereg-e docs/evidence/forward/scoreboard/PREREG_E_2026-09-25.json --block-config-e docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-30.json --replay-effective-date 2026-09-22 --expected-driver-sha256 459d20c3185a28f84a41221826b409f7c2eb5de0e01e97a370334419668e1943 --out .s489_c20/s489_c20_replay.json
```

The command above is the actual pre-r2 command stored in
`.s489_c20/s489_c20_replay.json`, with its original driver hash unchanged.
It recorded 243822592 bytes, 510.17532390000997 seconds (510.2 rounded),
19 identities and fitted_rows={"C":0,"E":0}. AMENDMENT 2(d) confirms 5-of-7-day
coverage: no served schedules for September 27 and 28. About 27 games projects
to about 725 seconds; that is a projection, not a full-window measurement.
AMENDMENT 2 revises the wall bar to 1500 seconds; memory stays 629145600 bytes.
The separate orchestrator budget declaration uses deadline "1800"; this lane
keeps paper_night_budget.json byte-pinned and does not declare e.
AMENDMENT 2(c) supplies the Opus fitted-path probe: September 22-25, 13 games,
C=571/E=427 fitted rows, 232 MiB peak, 6..16 MiB above unfitted. Its embargo
was patched to -3 days only in the probe; this is not production-embargo evidence.
AMENDMENT 2(d) supplies the September 24 profile: census 113 seconds including
85 seconds in microstructure; _tape reparses created_time per tick, with 14.9M
venue_time._parse calls on one game. The sealed-module cost belongs to S498.
These probe/profile numbers are attributed to the binding amendment; this lane
did not rerun them. New replay reports explicitly expose fitted_rows_zero.
For a future run, the r2 driver hash is
`2bea4db0feca7f85a6e9fc1753b7e3851f15b2bbc1bd08484b051b920df08b8c`;
the historical command above intentionally retains its historical hash.

## A9 and immutable baseline comparison

All paths are relative to C:/Users/neelj/nba-harness-h139. Resolution N/A.
LF-normalized bytes and hashes below were recomputed from this worktree.
No test pins another row's working-copy length. The only expected legacy test
difference is the explicitly authorized selected_blocks spy update.

| Path | LF bytes | LF SHA256 | Versus pinned baseline |
|---|---:|---|---|
| scripts/platformkit/execution/registry_scorer_e.py | 17756 | 55c75aca523c2803dbc65af06a12d5192b613e284543e72d0e2daf24f6b4cdbd | EQUAL |
| scripts/platformkit/execution/registry_scorer_e_fit.py | 10276 | b3dd16d88b82bc087ec7f4be40a931b76ac5c7fd5bffd78c6d2945a776ceb997 | EQUAL |
| scripts/platformkit/execution/registry_scorer_e_config.py | 10568 | a1cbff0b7ba34e20c6e61c0d66f3331be247446119ea60fc3c962888f09a2ee1 | EQUAL |
| scripts/platformkit/execution/registry_scorer_e_ticks.py | 12672 | a6e751fb2d537560fc99f289f3adaedd3515b25779e58d7bb5b32e564957cc8b | EQUAL |
| scripts/platformkit/execution/ingame_scoreboard_rules.py | 9871 | 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351 | EQUAL |
| scripts/platformkit/execution/scoreboard_history.py | 13751 | b21ccac74b0acaf524d113e54203cdcc889835562fc3de58c931f80c804d50c7 | EQUAL |
| scripts/platformkit/execution/scoreboard_history_store.py | 14706 | 18c75744234b43bb3988566e8960ef1d7ea2a11e41eeadef67ec4fc52139769f | EQUAL |
| scripts/platformkit/execution/ingame_scoreboard_night.py | 9682 | 8a34c4f4fca9f0c4395f8256d97603797d717d744e65df2e656f897a6645da24 | EQUAL |
| scripts/platformkit/execution/paper_night_deadline.py | 14592 | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | EQUAL |
| scripts/platformkit/execution/paper_night_lock.py | 1069 | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | EQUAL |
| scripts/platformkit/execution/paper_night_budget.json | 1942 | 1a6aaf42b3f2d8014df30e246c59e2481aadf3de98239acae2a233e92178dac4 | EQUAL |
| scripts/platformkit/ingame/registry_readers.py | 3669 | 17e99577505a99c4687835b3d0812d9f90c7ca56b7406a57d72852fb47371ab3 | EQUAL |
| docs/evidence/forward/scoreboard/PREREG_E_2026-09-25.json | 1423 | a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0 | EQUAL |
| docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-30.json | 771 | f74e50e728bc848f13dbd54177c3d223a740797f9eda5c490e66bae25ee36c18 | EQUAL |
| tests/platformkit/execution/test_registry_scorer_e_night.py | 14841 | 24e6948595e95763aa81b419a894491660db4001b77ff5e3dccbc13bb87c8cfc | EQUAL |
| tests/platformkit/execution/test_registry_scorer_e_night_1a.py | 8607 | fc0ea52146f42665ce4f74439b54330936bc61e5fd9c67ec02eef6ee6b70a921 | EQUAL |
| tests/platformkit/execution/test_registry_scorer_e_night_1b.py | 3878 | b34b05f7c2fafbd54df2ed0b40b3b13e7a31e6fcbeacd19b1cbf69d7d967366d | EQUAL |
| tests/platformkit/execution/test_paper_night_e_step_e2e.py | 13414 | 4c9e4b072936ddf7882ff86312b0fdd3581c2603999c8dcfdd5556ce3cc9c84f | NOT EQUAL (authorized spy) |
| tests/platformkit/execution/test_paper_night.py | 17439 | 1914742aead942601a173d78e4c16c63eb7d5dfb8ca995254c42640dbfde0105 | EQUAL |
| tests/platformkit/execution/test_paper_night_steps.py | 15701 | 3d87bdf86600a8fe07c13fe0121f85a17eac80dfcc4ebf0e50551005ea97fa93 | EQUAL |
| tests/platformkit/execution/test_paper_night_scoreboard_step.py | 17002 | 8fc3fb2c774d6ea585952e26d868cae74cf02d9a6dac1f7849af0bf552aba372 | EQUAL |
| tests/platformkit/execution/test_paper_night_scoreboard_step_1c.py | 5070 | b6f9505cd08831da2af0b33074d332a9ff9d6c963be74aaf768764682cd2fedb | EQUAL |
| tests/platformkit/execution/test_paper_night_scoreboard_step_1d.py | 2147 | 1c92d1faffd9dc799957da97af29e499da83afbd20419655815629b6e53a473d | EQUAL |
| tests/platformkit/execution/test_paper_night_scoreboard_step_1e.py | 1255 | e8d9c87342324927bf6bffd61725a5908d113ceb70f9efae7ad8cc9b43db719e | EQUAL |
| scripts/platformkit/ingame/feature_registry.py | 13253 | aaa96014496bd0be23d5c4d537c591a1199d46629320f26f75fdaf56d0565019 | EQUAL |
| scripts/platformkit/ingame/microstructure_features.py | 13920 | f286633c34eb138c6d4dd2c2f41b74d56427555bb0f10a576993110560a95090 | EQUAL |
| scripts/platformkit/ingame/registry_adapters.py | 14536 | 44ac53476be8f79ed9f200ff48de670468f9b2aa92bac262e1f6d6522a1170cd | EQUAL |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 12392 | 63d8d126ea26492a12ecab2e74b48d736d30fc626c1162a338acaae6ddb2c341 | EQUAL |

Candidate identities (recorded, not asserted as working-copy byte lengths):

| Path | LF bytes | Lines | LF SHA256 |
|---|---:|---:|---|
| .gitattributes | 1393 | 23 | 6eb5c4422d9b14050ff623d9db87e169186ead1d8573e7e2c450511f1297fcf2 |
| scripts/platformkit/execution/registry_scorer_e_night.py | 15582 | 266 | 1d2a8e40e546d6bf0fae11243a6125484763075ae72ef565a7ebba7c983c2d69 |
| scripts/platformkit/execution/registry_scorer_e_night_fields.py | 4850 | 106 | a1dad9e37bf2efcd1e01e847b6b533c599075b73095e827d2102612cc52e03d5 |
| scripts/platformkit/execution/registry_scorer_e_night_fixture.py | 3453 | 74 | 6d1f5facee243e8e8a08d98b123c5fad95be89023ab0782270e55f49de55707f |
| scripts/platformkit/execution/registry_scorer_e_night_replay.py | 8072 | 179 | 2bea4db0feca7f85a6e9fc1753b7e3851f15b2bbc1bd08484b051b920df08b8c |
| tests/platformkit/execution/test_registry_scorer_e_night_fields.py | 10983 | 203 | 42e41b1d3cf7c28d1869d6bba4c3ac3c2e97b1b3a6e4b308c97069f42c34d42e |
| tests/platformkit/execution/test_registry_scorer_e_night_capacity.py | 13946 | 264 | 572b00d3b76a30513d3b4d034f1b07385e1473e925739f7c1ebf6fba1c9eaeb6 |
| tests/platformkit/execution/test_registry_scorer_e_night_fixture.py | 3679 | 95 | a8536ceecde7cb8412b50fd000487e7f8506f8da1038cb57dda82bc13380a1bc |
| tests/platformkit/execution/test_registry_scorer_e_night_replay.py | 9075 | 196 | 8b18c1ea89ed8a1295460b90e7b7913076494bf6379e5b5a6a83655ef9b93c32 |

The owned night caller differs from the pinned baseline by its import, selected_blocks
signature/threading, lexical shard path, projection append and tie finalization.
The protected paper_night _run, NAMES and GATES pass the pinned AST-source check.

## FIX r2

Read _verdict_s489_r2.md first; AMENDMENT 2 governs conflicts. Before edits,
fields regressions returned `15 failed, 37 passed`; replay regressions returned
`11 failed, 8 passed`. After fixes: fields 52 passed; replay 19 passed.

| Verifier finding | Reproduced failure / exact correction and passing regression |
|---|---|
| sol 1 / 2(a), state ties | Minimal probe: `adapter_instants=[1790251200000000,1790251200000000], raw_inning=1, slim_inning=9, rank_keys=[False,False]`; four regressions: `assert 1 == 9`. Reuse adapter _instant for state groups; both input orders and two fractional precisions now select inning 1. Exact strict boundary remains excluded; temporary keys released. Book/trade exact-instant tests preserved. |
| Opus 1 / 2(b), unmodelled sources | Eleven selected blocks returned `Failed: DID NOT RAISE`. slim_row now refuses sources outside state/book/book+tape+state with slim_unsupported_block before projection. All eleven refusal tests pass, covering all three refused sources; production seven-block fixture and fitted differential pass. |
| sol 2 / Opus 4 / 2(c), zero-fit visibility | Supplied replay has C=0/E=0; new construct checks failed with `KeyError: 'fitted_rows_zero'`. Report now marks all-zero fits true and fitted constructs false; both pass. Amendment-supplied fitted probe recorded above supersedes the requested real replay in this construct-only lane. |
| Opus 2 / 2(d), wall bar | Regression showed `assert 600 == 1500` and `assert 2 == 0` at 1500 seconds. Driver uses amended 1500 bar; 1499 and 1500 pass, 1500.001 refuses. Five-day coverage, projection, profile and separate 1800 budget deadline recorded above. |
| sol 3 / Opus 3 / 2(e), output and memo | Old path resolved under C:/Users/neelj/nba-ai-system and raised `is not in the subpath`; .s489_c20 path was contained. Driver maps containment failure to replay_out_outside_root without weakening resolve-based write checks. Direct outside and real outside-junction regressions pass; local .s489_c20 construct passes. Actual command and supplied results replace stale NOT RUN text. |
| sol 4 / 2(f), candidate inventory | Inventory reproduced untracked scratch (2623 .s489_tmp files and 334 .s489_verify files at probe time); staged path list was empty. Amendment explicitly authorizes the existing fixture .gitattributes line. Scratch and verdicts are excluded by explicit owned pathspec, never staged; no deletion required. |

No new JSON seal/fixture path was added in r2. Authorized LF pattern:
`tests/platformkit/execution/fixtures/s489_verbatim_*.jsonl text eol=lf`.
Landing inputs are .gitattributes; the four registry_scorer_e_night modules
(base, fields, fixture, replay); their four S489 test files (fields, capacity,
fixture, replay); test_paper_night_e_step_e2e.py; the three s489_verbatim fixtures;
and this memo. No scratch, verdict, production budget or spec is a landing input.

## NOT VERIFIED

- No post-r2 real-archive C20 rerun or production-embargo fitted capacity run here.
- Supplied fitted probe/profile were not independently rerun in this lane.
- Real archive junction layout; construct tests use actual synthetic junctions.
- Separate orchestrator budget declaration and SQLite fallback, if needed.
- Network, pod, production fitted night, deployment, commit and landing were not run.

## C20 FINAL (orchestrator, final r2 driver, real window)

Run by the orchestrator on the final r2 candidate in this worktree (data/cache is a junction to the main checkout's
archive; --out is a plain directory inside the worktree). Every number below is read from the report JSON
(.s489_c20/s489_c20_replay_r2.json, untracked) and the external sampler line by a script.

- Command: `-m scripts.platformkit.execution.registry_scorer_e_night_replay --orchestrator-replay --capture-root data/cache/ingame_capture_view_v2 --served-schedule docs/evidence/forward/schedules/{date}_maker_forward.json --prereg-e docs/evidence/forward/scoreboard/PREREG_E_2026-09-25.json --block-config-e docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-30.json --replay-effective-date 2026-09-22 --expected-driver-sha256 2bea4db0feca7f85a6e9fc1753b7e3851f15b2bbc1bd08484b051b920df08b8c --out .s489_c20/s489_c20_replay_r2.json`
- driver_sha256 2bea4db0feca7f85a6e9fc1753b7e3851f15b2bbc1bd08484b051b920df08b8c; state PASS; window 2026-09-22..2026-09-28 (served schedules exist for 5 of these 7 days).
- Population: 19 games; state 10877 / book 10131 / trade 49770; eligible_ticks 7090; output_rows 7090.
- Peak memory: driver process_tree_peak_bytes 244432896 (sampled every 0.01 s, sampler_errors {}); external psutil tree sampler (0.05 s) peak_tree_rss_B 245051392, peak_wset_root_B 245268480; bar 629145600 B -> PASS.
- Wall: driver wall_s 508.3 (external 509.3 s) vs deadline_s 1500 -> PASS (a full 7-day ~27-game window projects to ~725 s; the orchestrator declares e with deadline "1800").
- Fitting: scoring_calls {'config_effective_override': 1, 'fit': 1}; fitted_rows {'C': 0, 'E': 0}; fitted_rows_zero true -> the fitted path's memory is covered only by the Opus probe (232 MiB, embargo patched in the probe only).
