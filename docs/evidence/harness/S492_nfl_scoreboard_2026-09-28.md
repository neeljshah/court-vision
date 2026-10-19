# S492 NFL scoreboard build memo

Candidate implemented; 20/20 numbered constructs pass. FIX r4 final tests: 721 passed across 28 separate per-file invocations; zero failures. This is fixture/construct evidence only; independent verifier acceptance is pending. Machine: local Windows worktree C:/Users/neelj/nba-harness-h141; no network, archive run, or pod. Binding source: docs/evidence/tracking/specs/S492_spec.md, AMENDMENTS 1/2/3/4/5 and dispatch override. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md B1-B11, Q1-Q9, A9, A12, S1/S2/S4.

## Before-condition, executed before coding

The initial build inspected the supplied fixture; Amendment 3(b) requires an archive-wide census at landing. Every fixture line was visited. Exact output of the initial read-only fixture census:

```text
fixture=2026-09-25 total_ticks=34 by_status={'final': 2, 'live': 30, 'pre': 2} usable_live_ticks=29 usable_live_games=1 bytes=35790 sha256=b23d5557030398e9b1a4b6f4e7e91f3a6a8340c7f33dcaa830150bd26d262e2b
```

The completed probe reproduces that census using actual tick encoding and eligibility: `invalid_rows=0`, `feature_reason_counts={'missing_state:possession_is_home': 1}`. This is not an archive-wide census. No live archive file was opened. The NFL fixture is 34 verbatim rows of game_key 401872948 (2 pre, 30 live, 2 final) from data/cache/ingame_capture_view_v2/state/nfl/2026-09-25.jsonl source lines 1..7761 in order. Fixture SHA256: b23d5557030398e9b1a4b6f4e7e91f3a6a8340c7f33dcaa830150bd26d262e2b.

## Change and activation contract

NFL registration, diagnostic encoding, feature parsing, phase dispatch, and all three history allowlists are implemented. The allowlist with None preserves None. Its module remains 295 lines with zero net added lines. All required fields come from one receipt. Six missing football fields yield six independent reasons. B/C require a complete tick; A survives where otherwise valid. D remains unavailable with null model inputs. Counts require source integers; malformed possession types are counted refusals, while unknown team strings remain missingness. Q1/Q2/Q3/Q4 clocks use [2700,3600]/[1800,2700]/[900,1800]/[0,900]; OT uses [0,600]. The extracted nfl_state body substitutes NFL_FIELDS for FEATURES['nfl'] only; bounds are moved unchanged. A function-local state_fields import avoids an import-time cycle. Existing compatibility exports remain present. Reader survey: nfl_state_completeness.py:17 imports NFL_BOUNDS/nfl_state (uses :22/:77); nfl_state_field_census.py:34 imports FEATURES/nfl_state/timestamp (nfl_state call :127). Both continue through baseline_four_arm_features.py:13. No other runtime readers were found in scripts/platformkit/ingame.

The default amendment payload keeps the historical schema and text. A widened payload records version 2 and seals the NFL helper. Verification derives the canonical sport list from the committed payload, reconstructs its identities, and returns only after verification. The prospective date is a parameter: E >= max(actual seal commit UTC day + 1, latest indexed amendment date + 1). E is 2026-10-01. Commit A' already contains the real seal, byte-identical to the construct seal; its UTC commit day is September 29. The committed SEALS table is the only seal-selection path; construct tests append entries to their temporary tables. SEALS now preserves that prefix and appends the exact October 1 tuple. Amendment 5 replaces the earlier two-path commit A with seal-only commit A'; commit B contains the table/code changes. Production activation remains pending.

MANDATORY DISCLOSURE: two legacy identity files changed. Both old amendments consequently fail amendment_mismatch. The night selector refuses BEFORE scoring/output; there is no A-only fallback for this mismatch. Commit B lands code after the E-1 successful receipt and before night E; commit A' leaves the entire selector unchanged. Also require absence of the first history production for 2026-10-04, or coordinate an explicit rebuild. The probe's --history-rows and --history-manifest parameters reject either existing history artifact as history_already_produced. A cached pre-S492 empty artifact otherwise returns already_present: the construct proves this and blocks the landing check. If such a cache exists, stop landing and coordinate an explicit rebuild preserving the archived sources; no silent invalidation is implemented.

## Exact imported interfaces read before coding

- `tick_row(t: dict, sport: str, close_ts: str, outcome: int, counts: Counter) -> dict | None`
- `state_fields(text: object) -> dict`
- `state_eligibility(text: str, sport: str) -> tuple[dict, list[str]]`
- `nfl_state(state: object, home_abbr: object, away_abbr: object) -> dict`
- `alias(sport: str, abbr: Optional[str]) -> Optional[str]`
- `select_rows(rows: list[dict], corpus: str, *, model_optional: bool = False) -> tuple[list[dict], dict]`
- `settle(sport: str, entry: dict, sr: list, counts: Counter) -> dict`
- `chronology(night: str, lookback: int, embargo: int) -> tuple`
- `produce(root: Path, args, config: dict, nights: list, capture: Path) -> tuple`
- `run(books_root: Path, state_root: Path, schedule: Path, day: str, sports: list, prereg: Path, history: list = (), as_of: str | None = None, arms: tuple = ('A', 'B', 'C', 'D'), model_optional=frozenset()) -> dict`
- `_json(value: object) -> str`; `parse_venue_time(value: object) -> float | None`
- `replace_with_retry(temporary: Path, target: Path, *, durable: bool = True, on_cleanup_error: Callable[[OSError], None] | None = None, on_retry: Callable[[], None] | None = None) -> bool`

## Unchanged generic routes, freshly inspected

In scripts/platformkit/execution/ingame_scoreboard_rules.py: segment:43 already handles NFL; _scores:67 uses the generic home/away keys; _mid:72, ticker_outcome:89, is_home_ticker:108 already use sport aliases; settle:194 selects the maximum parsed final time and is unchanged. Both final-order permutations are tested. In scripts/platformkit/execution/scoreboard_history.py: chronology:31, _encode:62, produce:101 are unchanged; produce dispatches the intersection of scheduled sports and CORPUS keys. The scorer shard loop remains :179-184. Local dates are not computed here; UTC schedule entries retain separate game keys. No S477 policy is changed.

## Acceptance cases

Metric: cases passing / cases enumerated = 20 / 20. Bar: 20 of 20; n = 20 (CONSTRUCT). F = test_baseline_four_arm_features_nfl.py; R = test_ingame_scoreboard_rules_nfl.py; M = test_ingame_scoreboard_amendment_model_optional.py; E = test_s492_e2e.py.

| Case | Coverage | File |
| --- | --- | --- |
| 1 | CORPUS/CORPORA and compatibility exports | F |
| 2 | Six missing fields, pre/final diagnostic encoding | F, R |
| 3 | Missing down, remaining receipt fields retained | F, R |
| 4 | Missing distance | F, R |
| 5 | Missing possession | F, R |
| 6 | Unknown possession abbreviation | R |
| 7 | Home/away/unresolved possession round-trip | R |
| 8 | OT 600 accepted, 601 refused | F, R |
| 9 | Quarter-specific clocks; Q4/3600 refused | F, R |
| 10 | P1..P4/OT and clean foreign-state refusal | F |
| 11 | Malformed/count-type/range refusals | F, R |
| 12 | Distinct same-UTC-day games and actual ticks | E |
| 13 | S(M) and S(M)+1us, conditional later admission | E |
| 14 | Historical default bytes and invalid sports before hashing | M |
| 15 | Generated widened seal, helper-only and payload tampering | M |
| 16 | Historical dates and parameterized appended selection | M |
| 17 | Separate complete dependency graphs, identical fitted MLB/soccer content | E |
| 18 | NFL producer dispatch and one-row history | E |
| 19 | Real fixture to producer file to fresh CLI, held-out B/C and null D | E |
| 20 | Killed partial staging write, no published partial row, next-run recovery | E |

Additional constructs cover as-of filtering before malformed future state validation, both future-row permutations, truncation invariance, whole-tick exclusion census, strict counts, duplicate text fields, short seal/report writes, fresh imports, the stale complete cache, and unsupported tennis dispatch. Raw A/B/C cells cover different populations: A over all ticks, B/C over eligible ticks. Only the C-minus-B contrast is paired on identical (game_id, ts) keys; the scorer is unchanged. The real NFL fixture is unchanged; schedule admission, books, and the later held-out game are constructed. No real fitted-output claim is made.

## Per-file verification

Every invocation was `python -m pytest <one file> -q -p no:cacheprovider` (some add --tb=short or a local --basetemp). No full suite was run. Paths are under tests/platformkit/; F is in ingame/, the probe test in ops/, others in execution/.

| Test file | Before passed | Before failed | FIX r1 passed | FIX r2 passed |
| --- | ---: | ---: | ---: | ---: |
| test_baseline_four_arm_features_nfl.py | 45 | 0 | 45 | 45 |
| test_ingame_scoreboard_rules_nfl.py | 82 | 0 | 82 | 82 |
| test_ingame_scoreboard_amendment_model_optional.py | 25 | 0 | 25 | 26 |
| test_s492_e2e.py | 9 | 0 | 9 | 9 |
| test_s492_landing.py | n/a | n/a | 3 | 3 |
| test_ingame_scoreboard.py | 43 | 0 | 43 | 43 |
| test_ingame_scoreboard_1b.py | 16 | 0 | 16 | 16 |
| test_ingame_scoreboard_1e.py | 4 | 0 | 4 | 4 |
| test_scoreboard_history_store.py | 80 | 0 | 80 | 80 |
| test_scoreboard_history.py | 35 | 1 | 36 | 36 |
| test_ingame_scoreboard_amendment.py | 62 | 7 | 69 | 69 |
| test_ingame_scoreboard_night.py | 31 | 0 | 31 | 31 |
| test_ingame_scoreboard_night_table.py | 104 | 0 | 104 | 104 |
| test_ingame_scoreboard_night_e2e.py | 5 | 3 | 8 | 8 |
| test_ingame_scoreboard_night_replace.py | 0 | 13 | 13 | 13 |
| test_s492_memo_facts.py | n/a | n/a | n/a | 13 |

FIX r1: 568 passed, zero failed across 15 separate per-file invocations; owned tests total 164. All four --help commands exited 0: scoreboard_history, ingame_scoreboard_amendment, ingame_scoreboard_night, s492_memo_facts. The fixture-only s492_memo_facts --identities probe exited 0 and reproduced the identity inventory below. FIX r1 contract_preflight: 9 PASS, 0 FAIL across 20 paths (verdict excluded).

The required --base master argument is used only by that prescribed linter; all tests and memo identity comparisons use full pinned revisions, never a moving ref.

## Identity and input inventory

Pinned dispatch base: 7df1db2f48d84cd6ec156c534f65bb4561509acb. Original spec reference: 2132fcf64c7039c4ea51097b7de96b85aa790bbe, superseded for this session's full-graph comparison by the dispatch base. Candidate landing SHA: NOT CREATED (sandbox). Candidate working content is NOT EQUAL to the pinned base. No candidate full-SHA equality claim is possible before lane_commit; isolated test commits are construct snapshots only. The table below records normalized LF hashes, not mutable working-copy byte-length assertions. FIX r5 correction: 7df1db2f48d84cd6ec156c534f65bb4561509acb is a historical graph base, NOT a no-overlap base. Owned and imported paths changed after it, including the committed seal docs/evidence/forward/scoreboard/PREREG_2026-10-01.json (commit A' d507296d7), and the graph fixture explicitly injects that seal, so the no-overlap stale-SHA exception does not apply to it.

| Path | Base SHA256 | Candidate SHA256 | Equal |
| --- | --- | --- | --- |
| scripts/platformkit/ingame/baseline_four_arm.py | dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2 | dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2 | True |
| scripts/platformkit/ingame/baseline_four_arm_eligibility.py | d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032 | d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032 | True |
| scripts/platformkit/ingame/baseline_four_arm_features.py | 8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade | 9704f9af99aab4053d8923a54399a122ce1fefdfb9c8cd461c1fc4bbc48b1e0d | False |
| scripts/platformkit/execution/ingame_scoreboard.py | 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6 | 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6 | True |
| scripts/platformkit/execution/ingame_scoreboard_rules.py | 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351 | 85c1a6be5645339bbb7a9055b5b36d15759323a264b626cc1c35f0c74fa194be | False |
| scripts/platformkit/eval_gate/walkforward.py | 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9 | 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9 | True |
| scripts/platformkit/execution/scoreboard_history.py | b21ccac74b0acaf524d113e54203cdcc889835562fc3de58c931f80c804d50c7 | b21ccac74b0acaf524d113e54203cdcc889835562fc3de58c931f80c804d50c7 | True |
| scripts/platformkit/execution/paper_night.py | 97399e8e3a8f41ef06053a9cc30907e1225be9597b932eb298c3c633b71e7576 | 97399e8e3a8f41ef06053a9cc30907e1225be9597b932eb298c3c633b71e7576 | True |
| scripts/platformkit/execution/paper_night_steps.py | 2b9bf8371a7e393546b1cb6596129d9866a890571cb4e7af8655e51d01d5b605 | 2b9bf8371a7e393546b1cb6596129d9866a890571cb4e7af8655e51d01d5b605 | True |
| scripts/platformkit/execution/paper_night_budget.json | 1a6aaf42b3f2d8014df30e246c59e2481aadf3de98239acae2a233e92178dac4 | 1a6aaf42b3f2d8014df30e246c59e2481aadf3de98239acae2a233e92178dac4 | True |
| docs/evidence/forward/scoreboard/PREREG_2026-09-24.json | 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b | 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b | True |
| docs/evidence/forward/scoreboard/PREREG_2026-09-29.json | 6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e | 6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e | True |
| docs/evidence/forward/scoreboard/PREREG_2026-09-30.json | 801af61b2755a99f9d5e238acd59bb1b6cf88212d1cb81b11a576ac32877b7aa | 801af61b2755a99f9d5e238acd59bb1b6cf88212d1cb81b11a576ac32877b7aa | True |
| docs/evidence/forward/scoreboard/PREREG_2026-09-24_superseded_2026-09-25.json | 421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d | 421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d | True |

SEALS SHA256 (json.dumps with sorted keys): 1595166d393a1cc1de5d5879d1e4d593506f82ade749e9e2c8dbb12f91006ba9. Historical prefix SHA256: 17a5ff7a67ad397cfce1ead6ae17e0e617995a382a1a64d4175c33b5d196fc3e; prefix equal: True. Features LOC: base 300; candidate 291; net -9. Every owned Python file is at most 300 lines and ASCII. New helper SHA256: 117561dba781a8ba0b344fe657712023ebdb5aaf8b16cc3760bd2d66125af7c1.

| Input full path | Bytes | SHA256 | Resolution |
| --- | ---: | --- | --- |
| C:/Users/neelj/nba-harness-h141/tests/platformkit/ingame/fixtures/s492_nfl_live_20260925_g401872948.jsonl | 35790 | b23d5557030398e9b1a4b6f4e7e91f3a6a8340c7f33dcaa830150bd26d262e2b | JSONL text |
| C:/Users/neelj/nba-harness-h141/tests/platformkit/execution/fixtures/s474_mlb_822842_books.jsonl | 2855 | f747f78a6ffc1f3dd38272eb88ac3dba5ed87e0ffc0fadce83da6ea8a44e9e2c | JSONL text |
| C:/Users/neelj/nba-harness-h141/tests/platformkit/execution/fixtures/s474_mlb_822842_state.jsonl | 1982 | b2b2c50c37281ad2a26f7b5c5adc43845569cdb6343180656857c136494c05a0 | JSONL text |
| C:/Users/neelj/nba-harness-h141/tests/platformkit/execution/fixtures/s492_prereg_2026-10-01.json | 2180 | a74e955e2fb37825e9249ed5b6280421a7c7a450b71a8239f34d6e8322a3d588 | JSON text |

New .gitattributes patterns:
- `tests/platformkit/ingame/fixtures/s492_nfl_live_20260925_g401872948.jsonl text eol=lf`
- `tests/platformkit/execution/fixtures/s492_prereg_2026-10-01.json text eol=lf`
Existing `docs/evidence/forward/scoreboard/*.json text eol=lf` covers the committed orchestrator seal; r4 adds no JSON/JSONL paths or attribute patterns. The MLB/soccer full-graph construct pins source fixture hashes and the entire generated input-path/hash map; its combined hash is 422bc70803b5477f3782b5626b5de4aa414273ad44a19aae3bdb23f8e017d672.

## Calendar and landing

October 2, 2026 is Friday UTC. Earliest activation remains conditional on actual commit date and current index. For M=2026-10-04, W(M)=[2026-09-27,2026-09-30], B=2026-10-01T00:00:00Z, S=2026-09-30T23:59:59.999999Z. A September 29 final can train only with an admitted schedule, paired complete live ticks, final <= S, and fresh history. A final at S+1us is excluded then and only conditionally admitted later. September 25 capture exists; this lane demonstrates no admitted real NFL history and promises no fitted production night. The successful September 30 receipt and absence of the October 4 history pair are orchestrator landing checks. The real seal is committed in A' (d507296d7b8569ff459dbaa08d54dafd89a91139); r4 verifies its hashes against all seven candidate identity files. Commit B adds the SEALS tuple after the successful September 30 receipt and before the October 1 paper-night run and first relevant history production. No identity-file edit is permitted after A'; a necessary identity change requires stopping and reporting.

## FIX r1 (historical; landing sequence superseded by FIX r4)

Binding findings: _verdict_s492_r1.md and spec AMENDMENT 2(a), (b), (c). (a) Fresh reproduction, before changes: amendment 62 passed/7 failed, night_e2e 5 passed/3 failed, night_replace 13 failed, history 35 passed/1 failed. Exact failure excerpts:

```text
assert len(live) == 6 and live == payload['implementation']
ValueError: amendment_mismatch
AssertionError: assert ['tennis'] == ['nfl', 'tennis']
```

Every edited unowned test is below; file paths are tests/platformkit/execution/. Only the two authorized reason classes changed; original scoring and publication checks remain.

| File:line / tests | Old assertion | New assertion | Reason class |
| --- | --- | --- | --- |
| test_ingame_scoreboard_amendment.py:238,242; test_identity_after_landing_and_later_commit (seven 09-30 variants) | live identities equal retired seal | identities from full pinned 7df1db2f48d84cd6ec156c534f65bb4561509acb equal seal | retired seal |
| test_ingame_scoreboard_night_e2e.py:22,68; tests :128 test_01_real_row_amendment_fresh_process, :169 test_selected_amendment_never_falls_back, :180 test_migration_intervals | second commit uses live identities | second commit uses the same full pinned 7df1db2f48d84cd6ec156c534f65bb4561509acb identities | retired seal |
| test_ingame_scoreboard_night_replace.py:25,36,45,59; twelve publication variants | verify old seal on live root | verify on reconstructed pinned 2ab9640cbc52bfcc0842dc7b020216d93edf6b06 bytes, injected pinned readers | retired seal |
| test_ingame_scoreboard_night_replace.py:151 test_sealed_identities_and_table_unchanged | live identities unchanged and old seal verifies | historical seal/table unchanged; old seal verifies pinned bytes and refuses candidate amendment_mismatch | retired seal |
| test_scoreboard_history.py:217-219 test_unsupported_sports_and_budget | unsupported NFL/tennis, both sources absent | unsupported tennis only; NFL source present, tennis absent | NFL registration |

The twelve publication variants are case1_no_lock (:83), case2_two_locks [32,5] (:96), case3_exhaustion (:105), case4_other_permission [None,13,33] (:127), case5_other_oserror (:139), cleanup_failure (:165), retry_stage_sync_failure (:188), source_stage_locked (:205), and first_publication_sync_failure (:227). After the first history assertion was updated, its adjacent source assertion reproduced `E assert False`; it was corrected under the same NFL-registration class. After: 69/8/13/36 passed, respectively.

(b) Missing construct generation first reproduced `AttributeError: module 'scripts.platformkit.ops.probes.s492_memo_facts' has no attribute 'construct_seal'`. The owned probe now implements construct_seal via the extended amendment CLI with an injected clock. Its regression passed first (1 passed); the completed landing file passes 3 tests. Seal: tests/platformkit/execution/fixtures/s492_prereg_2026-10-01.json (ASCII JSON, generated, never hand-written). SHA256: a74e955e2fb37825e9249ed5b6280421a7c7a450b71a8239f34d6e8322a3d588. Payload SHA256: 275f5d143dade6e99eecb5e633664851defb680233ddf497cbca88e1088010c5. Complete isolated graphs come from pinned 7df1db2f48d84cd6ec156c534f65bb4561509acb, with no candidate import leakage. Commit A has the constructed baseline as parent; its Git tree diff contains exactly the selector entry and new JSON. Its unchanged table prefix and last-entry date prove all earlier selection intervals unchanged; transition dates and the oldest interval are exercised explicitly. Night September 30 selects and verifies its original seal and produces byte-identical MLB/soccer cells/contrasts/ticks, with finite A/B/C/D/B_lag. Commit B is a child of A, dated October 1; the seal retains its September 28 commit date. October 1 and 2 select and verify the candidate's new seal and MLB/NFL/soccer set. Commit A alone refuses it on October 1. Read-only review caught a parentless temporary commit helper. The minimal reproduction printed `commit_A_parent_count=0` then `AssertionError: commit_A_must_preserve_baseline_parent`. The new helper passes explicit parent SHAs; regression assertions check both parent links and the exact two-path A diff. These are construct commits only. The actual receipt gate, commit A/B, and default-index activation remain orchestrator work.

(c) FIX r1 cleanup of .tmp_s492_e2e{,_2,_3,_4} was rejected by automatic approval review (`blocked by policy`). Per Amendment 2(c), these scratch roots stay excluded; no cleanup workaround was attempted. FIX r2 uses only .tmp_s492_r2_* under this worktree; those roots and .s492_verify are never landing paths.

## FIX r2

Binding verdict: _verdict_s492_r2.md, resolved exactly by AMENDMENT 3(a)-(g). Sol 1: minimal `sources=['/nfl/x']` reproduction printed `old_source_assertion=False` and `authorized_source_assertion=True`. Amendment 3(a) authorizes the existing stricter assertion; it stays unchanged under class (2), NFL registration, in the FIX r1 edited-test table above. Sol 2: `census([Path('shard_a.jsonl'), Path('shard_b.jsonl')])` first failed with `TypeError: expected str, bytes or os.PathLike object, not list`. The new regression file first produced `13 failed`, including missing `archive_census` and `error: unrecognized arguments: --archive-root`; after the module change it produced `13 passed`. `--archive-root` now refuses non-directories, streams every sorted *.jsonl shard, and emits each census plus aggregate counts, unioning usable games across shards. No whole-shard read is used in archive mode. Three synthetic shards (including empty and malformed-line shards) gave per-shard total_ticks=[4,0,3]; aggregate total_ticks=7, by_status={'final':1,'live':4,'pre':1}, usable_live_ticks=3, usable_live_games=2, invalid_rows=1. Every required football feature is independently tested as missing. The orchestrator must run `python -m scripts.platformkit.ops.probes.s492_memo_facts --archive-root data/cache/ingame_capture_view_v2/state/nfl` read-only and record its real result here at landing. Sol 3: `git diff -- .gitattributes` reproduced exactly the two fixture-pattern additions listed above. Amendment 3(c) requires both to stay; the unchanged-pattern check printed `authorized_s492_lf_patterns=2`. Opus 1: before deletion, `append_amendment_present=True` and `AssertionError: SEALS must be the only selection path`; regression result `2 failed, 24 passed`. Deleted append_amendment and --amendment; after: `append_amendment_present=False`, `26 passed`. CLI rejection and help coverage prevent reintroduction. The fresh-process consumer uses a committed temporary SEALS entry; landing constructs retain commit A's entry when installing commit B's selector. Opus 2: the constructed receipt reproduced `raw_population_sizes={'A':2,'B':1,'C':1}` and `AssertionError: raw A/B/C populations differ`. Corrected the population prose above; scorer bytes unchanged. The regression asserts raw counts A=2/B=1/C=1 and C_minus_B=1 with identical paired keys; `9 passed`. Amendment 3(f): corrected the exact fixture provenance and SHA256 above, with no fixture-byte changes. Amendment 3(g): recorded the exact commit-B tree requirement, retained SEALS line, and regeneration hazard. The stale inventory-base note is non-blocking; all comparisons still use the full pinned base. FIX r2 totals: 582 passed, zero failed; owned tests 178. Four --help commands and fixture --identities exited 0. The synthetic --archive-root CLI also exited 0. All seven protected identity hashes remain as recorded above. FIX r2 contract_preflight: 9 PASS, 0 FAIL across 21 paths; the verdict and all scratch roots were excluded.

## FIX r3

Binding verdict: _verdict_s492_r3.md; the sole open correction is AMENDMENT 4(a)-(d). (a) Before: pinned git-tree inventory gave `before_graph_files=4612`, `before_graph_payload_bytes=158865479`; the size smoke check failed `AssertionError: graph exceeds the required import closure`. The owned s492_memo_facts module now declares the 44-file import/evidence closure; the fixture asserts its exact file set. Pinned base remains 7df1db2f48d84cd6ec156c534f65bb4561509acb. No identity or scoring code changed. Base objects are read through an alternate object directory; `git read-tree` seeds the temporary index from that full SHA. The object-directory lookup resolves storage only, never compares a moving revision. All Git writes stay in temporary roots here. Only six candidate paths and then the seal/selector pair are added; landing reuses the baseline index without a broad add. (b) Before: injected copy failure printed `PermissionError: injected copytree Access is denied`, `whole_build_attempts=1`, then `AssertionError: whole graph build did not retry with a fresh root`. New regressions first gave `14 failed, 13 passed` (missing retry_graph_build); the implementation then gave `27 passed`. The owned retry helper covers the WHOLE build with at most three fresh mktemp roots, counts attempts, and re-raises exhaustion. PermissionError/OSError and all four required Git stderr patterns are covered; unrelated failures immediately re-raise. An actual copytree-failure regression verifies a second fresh graph completes and seals; the expanded probe file gave `28 passed` twice. An intermediate e2e run gave `9 passed`; its next run gave `6 passed, 3 errors`, ending with `error: unable to index file 'scripts/platformkit/execution/coherence_scanner.py'` after three attempts. That prompted the pinned-object/read-tree change above. Final e2e runs: `9 passed`, `9 passed`, `9 passed`; landing: `3 passed`. (c) Exported fixture: 44 files, 361571 extracted bytes, 409600 tar bytes (local Git archive conversion included). Each final e2e run used one attempt and retained 231 files / 5073384 bytes, including Git metadata and all test outputs. The landing run used one attempt and retained 343 files / 10148392 bytes. Sizes describe these runs, never mutable-byte test pins. Three retained final e2e runs total 15220152 bytes. Scratch roots .tmp_s492_r3_* and .s492_verify are excluded from landing. (d) Changed Python files: probe 218 lines, e2e 300, landing 161, probe tests 152; ASCII and <=300. Four --help commands and the fixture-only --identities self-check exited 0; the pinned identity inventory remains unchanged. No new JSON/JSONL fixture or seal was added in r3; the two exact S492 LF patterns listed above remain the only additions. FIX r3 contract_preflight: 9 PASS, 0 FAIL over all 21 candidate paths; verdict and scratch excluded.

## FIX r4

Binding finding: _verdict_s492_r4.md, AMENDMENT 5(a)-(e). Only the owned night selector and authorized test/memo conversions changed in r4; all seven sealed identity hashes matched before and after.
Commit A' is d507296d7b8569ff459dbaa08d54dafd89a91139, seal-only, UTC 2026-09-29T00:30:03Z. Seal SHA256: a74e955e2fb37825e9249ed5b6280421a7c7a450b71a8239f34d6e8322a3d588. FIX r5 (AMENDMENT 5(d)): the real-committed-seal regression reads the seal and its commit time through the literal worktree ref HEAD (b26fe5bd0105a004870e04ff900cb3d677209444 today, commit B after landing; both contain A'), never a fixed SHA and never master.
The orchestrator's h143 trial (spec evidence, not rerun here) kept production selection correct but broke 21 tests/collection sites; its seal-only A' alternative had 225 passing tests over five files. Commit B must follow the successful September 30 receipt and precede the October 1 run; September 30 on candidate identities refuses before scoring.

(b,d) Before the selector edit, the new real-committed-seal regression produced `ValueError: amendment_mismatch` on October 1 (`1 failed, 3 passed`). Added the exact fourth SEALS tuple. The regression now selects/verifies the real seal for October 1 and 2, asserts MLB/NFL/soccer, and requires September 30 `amendment_mismatch`. It verifies committed bytes and the UTC commit day through the literal worktree HEAD (FIX r5). An initial test-date assertion compared local date text; it was corrected to the existing venue-time-based UTC helper before the target failure was reproduced.
(c) With the fourth entry present, reproduced the verifier's four failures before test edits: night collection `ValueError: too many values to unpack (expected 3)`; table `ValueError: seal_index_invalid` (`1 failed, 103 passed`); night_e2e `ValueError: seal_index_invalid` (`7 failed, 1 passed`); replace `CalledProcessError` for the absent October 1 path at pinned 2ab9640cbc52bfcc0842dc7b020216d93edf6b06 (`13 errors`).

| Authorized conversion (tests/platformkit/execution/) | Change preserving the original property |
| --- | --- |
| test_ingame_scoreboard_night.py:14,29,77 | Unpack historical prefix, assert exact fourth tuple, supply fourth seal, protect its output path too. |
| test_ingame_scoreboard_night_table.py:198,233 | Keep historical prefix/hash; pin fourth tuple and read its bytes at full d507296d7b8569ff459dbaa08d54dafd89a91139; assert October 1 selection. |
| test_ingame_scoreboard_night_e2e.py:59,199 | Commit pinned fourth seal in fixture; keep historical September 30 verification, require October dates to refuse on historical identities. |
| test_ingame_scoreboard_night_replace.py:21,155 | Read new seal at its own full commit; assert prefix equality plus exact fourth tuple; retired-seal checks explicitly use entry 2. |
| test_ingame_scoreboard_amendment_model_optional.py:123 | Index-date refusal now includes October 1; October 2 generation passes. Before: `ValueError: amendment_not_after_latest`, `1 failed, 25 passed`. |
| test_s492_e2e.py:74 | Supply/commit pinned production seal before constructing later seal; before: `CalledProcessError`, `6 passed, 3 errors`. |
| test_s492_landing.py:22,44,77 | Add real-seal regression; scope historical generation to prefix; model A' as seal-only and B as code/table; before: `1 failed, 1 passed, 2 errors`. |

The landing fixture asserts A' has exactly one changed path, explicit parent links, unchanged selector, and identical fitted September 30 content; B preserves the historical table prefix and adds the sole fourth tuple. A transitional test compared the whole B selector to old code and failed on inherited short-write checks; the corrected assertion compares the table, preserving those previously verified checks. Final landing: 4 passed.
(e) All final commands used `python -m pytest <one file> -q -p no:cacheprovider`, sequentially. The following are all 28 scoreboard/S492 files; paths follow the earlier table, except latency/prospective in ingame/, S167 and memo facts in ops/, SLA in sla/, and G316/test_scoreboard at tests/platformkit/.

| Test file | FIX r4 passed |
| --- | ---: |
| test_baseline_four_arm_features_nfl.py | 45 |
| test_g316_scoreboard_clock_liveness.py | 6 |
| test_ingame_scoreboard.py | 43 |
| test_ingame_scoreboard_1b.py | 16 |
| test_ingame_scoreboard_1e.py | 4 |
| test_ingame_scoreboard_amendment.py | 69 |
| test_ingame_scoreboard_amendment_model_optional.py | 26 |
| test_ingame_scoreboard_model_optional.py | 16 |
| test_ingame_scoreboard_night.py | 32 |
| test_ingame_scoreboard_night_e2e.py | 8 |
| test_ingame_scoreboard_night_replace.py | 13 |
| test_ingame_scoreboard_night_table.py | 104 |
| test_ingame_scoreboard_rules_nfl.py | 82 |
| test_latency_scoreboard.py | 5 |
| test_paper_night_scoreboard_step.py | 14 |
| test_paper_night_scoreboard_step_1c.py | 4 |
| test_paper_night_scoreboard_step_1d.py | 2 |
| test_paper_night_scoreboard_step_1e.py | 1 |
| test_prospective_scoreboard.py | 8 |
| test_s167_calibration_scoreboard_no_write.py | 1 |
| test_s492_e2e.py | 9 |
| test_s492_landing.py | 4 |
| test_s492_memo_facts.py | 28 |
| test_scoreboard.py | 26 |
| test_scoreboard_history.py | 36 |
| test_scoreboard_history_e2e.py | 13 |
| test_scoreboard_history_store.py | 80 |
| test_sla_scoreboard.py | 26 |

Total: 721 passed, zero failed/errors in the final runs. Four module --help commands and fixture-only --identities self-check exited 0. No real archive was opened. Read-only r4 review found no additional defect.
The two existing S492 .gitattributes LF patterns and the production scoreboard JSON pattern listed above remain sufficient; no fixture/seal bytes changed. All landing files remain ASCII and <=300 lines. Scratch .tmp_s492_r4_logs/, .tmp_s492_r4_temp/, .s492_verify/ and all earlier scratch roots are excluded from landing and preflight.
FIX r4 contract_preflight: 9 PASS, 0 FAIL over all 23 candidate paths, using the prescribed --base master and --spec arguments; verdict and scratch excluded. Final sealed-identity recheck: 7/7 MATCH. SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED

- Full archive-wide NFL census, future September 29 capture, or any live archive query.
- Real settled NFL history, real non-null B/C output, live OT, or a production scoreboard receipt.
- Successful September 30 receipt, actual commit-B landing timing, or production activation; the dated A' seal commit is verified.
- Independent verification and production acceptance remain pending; all listed construct regressions now pass.
- No candidate landing SHA was created; no whole suite, network, pod, or deployed service was exercised.

## COMMIT-B REBASE (readiness lead R1, 2026-09-30; prep only, the improve run lands)
- Rebased from h141 (base b26fe5bd0, never modified) onto master 05554a7f7391654815db0d014b487186fad625c1 in worktree nba-harness-h300 (branch harness-h300). Candidate code applied cleanly; .gitattributes merged as a union (two S492 eol lines appended).
- The 7 PREREG_2026-10-01 identity files hash (LF-normalised) exactly to the committed seal; select() on the candidate: 2026-09-29 and 2026-09-30 refuse amendment_mismatch (expected: land only after the 2026-09-30 receipt), 2026-10-01 and 2026-10-02 select PREREG_2026-10-01 [mlb, nfl, soccer].
- Test conversions forced by rows landed after b26fe5bd0 (all re-pins or authorized flips, no production edit): test_s485_baseline_contract.py keeps S501 0914898a0b5a and S496 27ae6b756dde edits and pins ingame_scoreboard_amendment/night/rules to their LF sha256 (S492_REPIN); test_paper_night_e_step_e2e.py S492_PINNED (rules, history store, night; overrides the S494 store pin); test_microstructure_features.py and test_nfl_state_ingest.py expect the one nfl corpus; test_soccer_scoring_s490.py and test_soccer_s490_evidence.py check PREREG_2026-09-30 against its own seal commit 55e93081b3ee instead of the working copy; test_s492_e2e.py construct graphs overlay the S494/S580 history pair at DRIFT_SHA c9f00a98af4c (s492_memo_facts.overlay_drift; test_s492_memo_facts expects GRAPH_PATHS plus DRIFT_PATHS).
- NOT VERIFIED here: the S490 dependency addendum (effective 2026-10-09) binds the PREREG_2026-09-30 sha while soccer nights from 2026-10-01 select PREREG_2026-10-01 after commit B (S534 scope, soccer-readiness lead). The S545 must_not_move landing check (env-gated skip) pins the pre-S492 rules/night/features bytes and will differ at landing.
- R1 verifier (Opus, contract + adversarial combined, 2026-09-30 ~00:35Z): ACCEPT WITH CORRECTIONS, 0 blocking; 65 unmodified consumer test files per file green except 4 pre-existing or environmental (identical on the base). Notes folded: the S545 must_not_move fixture (S545_LANDING=1 only; S545 already landed) still pins pre-S492 rules/night bytes, a stale landing-only pin for a follow-up; the construct graphs keep BASE bytes for cross_venue_link, forward_replay_io, game_market_link and nba_state_enrichment (identical in both graphs, so the base-vs-candidate delta is still S492-only, but master's current versions of those four are not exercised there).
