# S480 candidate: numeric Arm E and receipt count state

Candidate construct acceptance: 17/17 cases, comprising new C3-C17 15/15 and invariants C1-C2 2/2.
This is a local plumbing proof using committed-format fixture bytes and construct history, not a calibration measurement.
Landing and fixture commit provenance are pending. SHA: NOT CREATED (sandbox); files ready for lane_commit.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h134, repo Python, fresh subprocesses.
No archive, network, pod, or data/ writes. Eye check: n/a (S-row). Denominator: 17 CONSTRUCT cases.
Binding source: docs/evidence/tracking/specs/S480_spec.md; contract B1-B11, Q1-Q9, A9/A12, S1/S2/S4.

## Before-condition, measured before core edits

The named orchestrator scripts were read first. s480_probe_state.py and s480_types.py read full archives;
s480_before.py reads the four full-game scratch slices; s480_slice_probe.py writes extracted slices.
Those routes conflict with this dispatch's fixture-only/no-archive/no-other-worktree-write instruction.
The permitted equivalent below exercised the landed census_features + fit with the exact copied slice and h0/h1 history.
The full-archive totals in the binding spec are supplied orchestrator evidence, not measurements repeated here.
Verbatim fixture-scoped before output:

```text
s480_real_state_822842.jsonl 28405 29 385bbeaada96691c146c6a1191ee9a75c51e02d70f2e722b73209d522381895c
s480_real_book_822842.jsonl 922480 493 ad508674b5f0e68e43d72508ab1abdbdef508c42e55035a8abd1e763b2a5c90a
BEFORE rows 12 real 10 numeric_E 0 refusals {'block_incomplete': 10} micro {'count_refused': 12}
SIMULATED_COUNT_ONLY rows 12 real 10 numeric_E 10 refusals {None: 10} micro {'present': 72}
FIXTURE_STATE live 28 phase_gate 2 terminal 0 active 26
```

The simulation replaced strict_count in memory only and restored it before file edits; production strict_count is unchanged.
The named s480_c7_probe.py was also executed in memory with its foreign sys.path insertion removed, using this worktree.
It preserved both earlier feature rows, added only T3, and counted one duplicate, one out_of_order, one bad receipt.
The reproducible C9 test asserts those complete results on the new blocks as well.

## Interfaces read before coding

Every production import was read by its owning builder before coding. Exact signatures relied on:

```python
strict_count(value: object, *, maximum: int = 1_000_000) -> int
numeric_encoding(values: dict[str, object], fields: tuple[str, ...]) -> dict[str, Decimal]
manifest_hash(selected: tuple[str, ...]) -> str
build_game(entry: dict, state_rows, book_rows=(), trade_rows=(), counts: Counter | None = None) -> dict
adapt_block(game: dict, block: FeatureBlock, event: int, census: Counter, *, freshness_s: Decimal, micro_cache: dict, seen: set | None = None) -> dict[str, Decimal]
_select_state(game: dict, event: int, block: FeatureBlock, census: Counter, seen: set | None = None) -> tuple[dict | None, int | None, bool]
_instant(value: object) -> int
census_features(games, selected: tuple[str, ...], freshness_s: D) -> tuple[list[dict], dict]
fit(rows: list[dict], e_fields: tuple[str, ...], c_fields: tuple[str, ...] = C_FIELDS) -> dict
score(games: list[dict], selected: tuple[str, ...], prereg_path: Path, block_config_path: Path) -> dict
main(argv: list[str] | None = None) -> int
implementation_identity(root: Path, files: tuple[str, ...] = IMPLEMENTATION_FILES) -> str
load_block_config(path: Path, selected: tuple[str, ...], *, root: Path, git_committed: Callable[[Path], bool], committed_at: Callable[[Path], Decimal | float | None] | None = None, latest_input_us: Decimal | int | None = None) -> dict
parse_venue_time(value: object) -> float | None
_case2_game(gk: str, day: int, win: bool) -> dict
_write_seals(tmp_path, *, prereg_over=None, config_over=None, selected=SELECTED)
_state(ts, **state_over)
_entry(gk, ticker=TICKER, **over)
_book(ts, bid="0.60", ask="0.62", ticker=TICKER, game_id="g1")
_final(ts, score_home, score_away)
```

## Before/after cases

Before references the full pinned 8f97cad2eefcdd22d1f4d7e5b675d364e221123a implementation.
C1/C2 and C4 execute pinned blobs; C13 repeats the before typing in a fresh process.
Other before failures follow the absent declarations and the encoder's pinned strict_count branch, not a fabricated prior test run.

| Case | Before | After |
|---|---|---|
| C1 | Existing seals and invariant test | PASS: exact H1/H2 only; three LF hashes preserved |
| C2 | Existing block table, C_FIELDS, seven/ten manifests | PASS: unchanged |
| C3 | Decimal integer counts refused | PASS: exact E1 table; direct strict_count still refuses |
| C4 | All 14 old fields refuse exponent-zero Decimal | PASS: all 16 fields checked; adapter and lineup compatibility |
| C5 | half_bottom absent; categories undeclared | PASS: exact category and presence tables |
| C6 | balls/strikes undeclared | PASS: active bounds, terminal, gate precedence, refusal vocabulary |
| C7 | Three blocks absent | PASS: five transition forms refuse, including Middle/2; active form encodes; A/C equal |
| C8 | Microstructure count_refused 3; E absent 3/3 | PASS: encode 3/3, target E numeric; H1 reproduces before |
| C9 | New state blocks absent | PASS: receipt equality, microsecond clock, duplicates/order, future tail |
| C10 | New census blocks absent | PASS: all nine source states, each field and adapter outcome |
| C11 | Count-state path absent | PASS: terminal/next-state sequence and every later-row mutation |
| C12 | New blocks absent | PASS: each block exceeds 0.05 perturbation; constant <=1e-9; echo fails |
| C13 | Real E absent 10/10; microstructure refusals 12 | PASS: 8 active numeric; 2 Middle refused; process outputs equal |
| C14 | No numeric real E | PASS: future outcome changes only outcomes and losses; predictions equal |
| C15 | No numeric real E | PASS: three malformed fields, partial tail, unsettled history counted |
| C16 | New seal absent | PASS: identity, manifest, hash, commit boundary, past-input refusal |
| C17 | Fixtures supplied but no lane gates | PASS: every original/derived size, line count, and hash |

C14 precision: its one-game summary is byte-identical after reversal because intervals remain unestimated;
paired_losses and real_outcome change. C13 summary remains INSUFFICIENT, n_ticks=8, n_games=1.
The emitted state_ts adds one microsecond by landed design; C13 identifies source ticks by event_us.

## New blocks and disclosed semantics

| Block | Fields | Encoding and policy |
|---|---|---|
| half_inning | half_bottom | Top=0, Bottom=1; source half; at_or_before |
| base_occupancy | on_first, on_second, on_third | strict bool bits; at_or_before |
| ball_strike_count | balls, strikes | strict counts 0..3 / 0..2; at_or_before |

All three encodings are NOT PROFILED. base_state is unread. Categories check exact type before lookup.
Presence precedes phase gate; Middle/End or exact integer outs=3 refuses inning_transition.
Balls=4 or strikes=3 refuses terminal_count after that gate. Missing fields never become zero.
The clock is "last observed mid at state receipt": state can postdate its paired book.
The tick's own receipt supplies all four state blocks; future rows cannot supply their fields.
Microstructure retains strict_earlier; S431 file-order first-copy semantics are unchanged.
This spec explicitly requires counting/refusing out-of-order rows; it does not sort arbitrary receipt permutations.

The shared encoder change affects every _COUNT_FIELDS member, including C's inning/outs/score_home/score_away.
C4's matrix checks int unchanged, exponent-zero Decimal newly accepted, exponent-shift/fractional Decimal,
negative/over-bound values, bool, float and numeric string refused. Terminal maxima have the named terminal refusal.
A Decimal-preserving JSON reader accepts literal 7E0 as Decimal exponent zero; it refuses 7.0.
The supplied full-archive census found only int counts in real state and mlb_live, so the count change was inert there.
The fixture's real state types agree; the archive-wide assertion was not rerun by this lane.
No committed seal ever produced numeric E under the old microstructure count-typing path; both old selections require it.

D5 selects, in order: mid, team_state, microstructure, player_pitcher_workload, half_inning, base_occupancy, ball_strike_count.
live_feed, player_encounter_count, team_bullpen_usage, pitcher_hand, current_lineup, appearance_history remain registered,
unselected and FROZEN. Any later selection needs measured adapter-valid coverage and a new prospective seal.
Supplied iii census: 22,618 live rows; phase gate 3,488 (15.4 pct), terminal outside gate 372 (1.6 pct), active 18,758 (82.9 pct).
Supplied September 24 subset: 300 / 35 / 1,645 of 1,980. Fixture: 28 live, 2 phase, 0 terminal, 26 active; 10 mid-eligible.
Supplied mlb_lineup coverage is zero. Nonempty mlb_live: zero on September 22-24, 2,379/4,241 on September 25,
2,318/2,318 on September 26; its three count fields are int on all 4,697 rows. Adapter-valid coverage remains unmeasured.
PREREG_E_2026-09-25's dedup_policy text does not name the new blocks; their policy is in each manifest FeatureBlock.
strict_count, decimal_value, _BOUNDS, all existing BLOCKS, C_FIELDS, the ten-file identity inventory, and old seals are unchanged.

## Seals and landing obligations

| File under docs/evidence/forward/scoreboard/ | LF SHA256 |
|---|---|
| BLOCK_CONFIG_E_2026-09-25.json | 959ca04e325596334dc9120e509e4e1d3e6b95d68cab9af54433d0dab5add744 |
| PREREG_E_2026-09-25.json | a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0 |
| BLOCK_CONFIG_E_2026-09-29.json | cddcac1128e5318085906ff8fcf818ceb28ec3b07dc9da3c1f83184c4c47d0a9 |
| BLOCK_CONFIG_E_2026-09-30.json | f74e50e728bc848f13dbd54177c3d223a740797f9eda5c490e66bae25ee36c18 |

D=2026-09-30T00:00:00.000000Z; landing committer time: NOT CREATED (sandbox).
If landing is at/after D, recompute first UTC midnight strictly after landing, never before September 30, and reseal last.
The September 29 seal retires by implementation identity. Gap nights between landing and D have no live config.
Parsed docs/evidence JSON inventory: no file with block_config_sha256=98dba026bdc64da79544de3e2decdce148d34420d3e55f309db60a92e46337f3.
One unparseable JSON was counted: docs/evidence/forward/qualification/2026-09-24.json.
Expected landing disposition is SUPERSEDED-UNSCORED; final inventory/decision belongs to the orchestrator, including that unreadable file.
No historical scored outputs were rewritten. Fixture-adding commit full SHAs cannot be reported because both copied files are untracked.

Conditional floor from spec, not a forecast measured here: postseason format 32-53 games (41 in 2023, 43 in 2024).
S480 alone requires both classes and the three-day settlement embargo: about 20-37 scoreable games, roughly 25-30 at those lengths;
the 30-game floor is at best late in the World Series. With S480b by D+3, about 24-41 (33-34 at those lengths),
the floor is roughly World Series start. Both need nearly complete books/trades/state/final capture; INSUFFICIENT remains plausible.
The supplied postseason start date is unverified. S480b training-only regular-season history admission is explicitly split and unbuilt.

## Verification and reproducibility

Run each command separately: python -m pytest <one file> -q -p no:cacheprovider.
The two new files cover 17 cases; the following individual file runs passed, with no full-suite run:

| File suffix (execution/ unless qualified) | Passed |
|---|---:|
| test_registry_scorer_e_s480.py | 12 |
| test_registry_scorer_e_s480_real.py | 11 |
| test_registry_scorer_e_s471.py | 5 |
| test_registry_scorer_e_s471_1b.py | 38 |
| test_registry_scorer_e_s471_regressions.py | 46 |
| test_registry_scorer_e.py | 17 |
| test_registry_scorer_e_1d.py | 20 |
| test_registry_scorer_e_1e.py | 13 |
| test_registry_scorer_e_1f.py | 16 |
| test_registry_scorer_e_1g.py | 3 |
| test_registry_scorer_e_fit.py | 15 |
| ingame/test_feature_registry.py | 16 |
| ingame/test_registry_adapters.py | 21 |
| ingame/test_registry_adapters_1d.py | 5 |
| ingame/test_registry_adapters_1g.py | 12 |
| ingame/test_registry_readers.py | 12 |
| ingame/test_mlb_lineup_registry_adapter.py | 13 |
| tests/platformkit/test_loc_rail_scope.py | 1 |

Total: 276 passing tests across 18 individual files. s480_memo_facts --help and registry_scorer_e --help exit zero.
C17 gates only fixture bytes; separate FIX 1a tests exercise the probe and child failure handling. New fixture writes are atomic; existing imported seal-test writers are unchanged.
Preflight result is recorded below. No A12 allowlist edit. All Python files <=300 lines; probe <=150; all new text ASCII.
The exact verbatim book fixture is 493 lines, as required by its binding hash; the generic 300-line rail cannot also apply to that fixture.
.gitattributes patterns: tests/platformkit/execution/fixtures/s480_* text eol=lf; docs/evidence/forward/scoreboard/*.json text eol=lf.
Both existing patterns are unchanged. Fixtures are LF-only (no CR); checkout preserves the gated sha256 values.
Pinned-base test diffs include intervening landings; FIX 1a uses the explicit owned-file inventory below.
The tracked candidate diff has four owned modified files; new paths are all owned. Nothing unrelated was reverted.

## Reproducible disk facts

```text
seal docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-30.json
effective_from 2026-09-30T00:00:00.000000Z
identity f4b5183527fd4148540c0d74f6ba14f51dd872d722ba445a2c51a5088efa70b0 recorded f4b5183527fd4148540c0d74f6ba14f51dd872d722ba445a2c51a5088efa70b0
manifest cfc3bdbdabea6d7b99ebdd23995b0be5953aa38ec6493aebce617c896b5f6e22 recorded cfc3bdbdabea6d7b99ebdd23995b0be5953aa38ec6493aebce617c896b5f6e22
inner ee89183e36572b1441082d50421c5809f9bd9f4d05d2c0789d28232a20218b8e recorded ee89183e36572b1441082d50421c5809f9bd9f4d05d2c0789d28232a20218b8e
file_raw_sha256 f74e50e728bc848f13dbd54177c3d223a740797f9eda5c490e66bae25ee36c18 file_LF_sha256 f74e50e728bc848f13dbd54177c3d223a740797f9eda5c490e66bae25ee36c18
fixture tests/platformkit/execution/fixtures/s480_real_state_822842.jsonl bytes 28405 lines 29 raw_sha256 385bbeaada96691c146c6a1191ee9a75c51e02d70f2e722b73209d522381895c
fixture tests/platformkit/execution/fixtures/s480_real_book_822842.jsonl bytes 922480 lines 493 raw_sha256 ad508674b5f0e68e43d72508ab1abdbdef508c42e55035a8abd1e763b2a5c90a
fixture_tallies {"active": 26, "final": 1, "live": 28, "phase_gate": 2, "terminal": 0}
cases C1 C2 C3 C4 C5 C6 C7 C8 C9 C10 C11 C12 C13 C14 C15 C16 C17
invariants C1-C2 2; new cases C3-C17 15; denominator 17 CONSTRUCT
NOT VERIFIED: No scored real night under any seal.
NOT VERIFIED: No real training history; C13 history is construct.
NOT VERIFIED: New seal real commit time awaits landing and one real-git check.
NOT VERIFIED: Postseason ticker series and capture coverage.
NOT VERIFIED: Adapter-valid coverage of unselected blocks.
NOT VERIFIED: Postseason start date.
NOT VERIFIED: Full-archive before-condition census was not rerun in this fixture-only lane.
```

```text
candidate_HEAD a10bac3ada66e739cda81c7af3c94818f726ecaa (provenance only)
verification_base_pinned_master 8f97cad2eefcdd22d1f4d7e5b675d364e221123a
fixture_adding_commit tests/platformkit/execution/fixtures/s480_real_state_822842.jsonl NOT COMMITTED
fixture_adding_commit tests/platformkit/execution/fixtures/s480_real_book_822842.jsonl NOT COMMITTED
scripts/platformkit/ingame/feature_registry.py LF_bytes 13253 lines 260 sha256 aaa96014496bd0be23d5c4d537c591a1199d46629320f26f75fdaf56d0565019 NOT EQUAL
scripts/platformkit/ingame/registry_adapters.py LF_bytes 14536 lines 299 sha256 44ac53476be8f79ed9f200ff48de670468f9b2aa92bac262e1f6d6522a1170cd NOT EQUAL
scripts/platformkit/execution/registry_scorer_e_ticks.py LF_bytes 12672 lines 235 sha256 a6e751fb2d537560fc99f289f3adaedd3515b25779e58d7bb5b32e564957cc8b NOT EQUAL
scripts/platformkit/ops/probes/s480_memo_facts.py LF_bytes 5423 lines 117 sha256 e78cab96ddf569cd24ab76b1d91b0e9fd0a69e354c9191062bd89ec635fed4a7 NEW (absent at pinned base)
tests/platformkit/execution/test_registry_scorer_e_s471.py LF_bytes 21063 lines 297 sha256 5f0925c1692361f693a24a3d9bff0f09d4cb9eae2e11bac73a24a262c6e8fcbe NOT EQUAL
tests/platformkit/execution/test_registry_scorer_e_s480.py LF_bytes 20359 lines 292 sha256 15f5f5a156aafbf2491a9af8f9928a3200673c970a17a87fff50196ce8813280 NEW (absent at pinned base)
tests/platformkit/execution/test_registry_scorer_e_s480_real.py LF_bytes 15751 lines 294 sha256 2909074e55dba9c820d3e663292ae464d0bb549446b672e9ef0f98c04953e653 NEW (absent at pinned base)
tests/platformkit/execution/fixtures/s480_real_state_822842.jsonl LF_bytes 28405 lines 29 sha256 385bbeaada96691c146c6a1191ee9a75c51e02d70f2e722b73209d522381895c NEW (absent at pinned base)
tests/platformkit/execution/fixtures/s480_real_book_822842.jsonl LF_bytes 922480 lines 493 sha256 ad508674b5f0e68e43d72508ab1abdbdef508c42e55035a8abd1e763b2a5c90a NEW (absent at pinned base)
docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-30.json LF_bytes 771 lines 26 sha256 f74e50e728bc848f13dbd54177c3d223a740797f9eda5c490e66bae25ee36c18 NEW (absent at pinned base)
.gitattributes LF_bytes 1066 lines 18 sha256 f4737f7e6d1b0881f30e02170b8d6663e30e3aaa1c6173bc90d65e6e99b73ff5 NOT EQUAL
scripts/platformkit/ingame/registry_adapters_live_guard.py LF_bytes 5040 lines 94 sha256 30e70ba1f5212274747bd883395da4dcc4d121eefd298f6591e54afde31bbb1e EQUAL
scripts/platformkit/ingame/registry_readers.py LF_bytes 3669 lines 83 sha256 17e99577505a99c4687835b3d0812d9f90c7ca56b7406a57d72852fb47371ab3 EQUAL
scripts/platformkit/execution/registry_scorer_e.py LF_bytes 17756 lines 297 sha256 55c75aca523c2803dbc65af06a12d5192b613e284543e72d0e2daf24f6b4cdbd EQUAL
scripts/platformkit/execution/registry_scorer_e_fit.py LF_bytes 10276 lines 175 sha256 b3dd16d88b82bc087ec7f4be40a931b76ac5c7fd5bffd78c6d2945a776ceb997 EQUAL
scripts/platformkit/execution/registry_scorer_e_config.py LF_bytes 10568 lines 186 sha256 a1cbff0b7ba34e20c6e61c0d66f3331be247446119ea60fc3c962888f09a2ee1 EQUAL
scripts/platformkit/ingame/registry_adapters_lineup.py LF_bytes 9631 lines 202 sha256 6a83ce1c497d2eb0d4b716cb144274f988c71be1f91a3a07f146d318f98ed1f0 EQUAL
scripts/platformkit/ingame/mlb_lineup_registry_adapter.py LF_bytes 9201 lines 146 sha256 a05a40762f83bc0f6af73f319ea818a7651a917d1d5bbdee6c1cbd8943fc1900 EQUAL
```



```text
PASS vocab clean over 11 files
PASS crlf no index-side CRLF over 11 file(s); 7 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-30.json new (no master baseline)
PASS head_slice no head slices
PASS spec_threshold 16 literal(s) matched
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 8 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

## FIX 1a

Binding AMENDMENT 1(a)-(f) supersedes the original verdict where stated.
- (a), sol 1 / Opus correction 1: reproduced `text: set` and `eol: lf` with git check-attr.
  Before: `FAIL memo_attribute_stale=True`. Corrected the memo to the accepted LF pattern above;
  .gitattributes and immutable fixtures were not edited. C17 rechecks all raw and derived gates.
- (b), sol 2: reproduced `summary_equal=True`, `paired_all_differ=True`,
  `features_predictions_equal=True`. C14 now explicitly asserts both INSUFFICIENT verdicts
  and [None, None] intervals; reversal changes losses and outcomes while predictions stay identical.
- (c), sol 3: reproduced two `NOT COMMITTED` fixture records. Amendment assigns commit provenance
  to the lander. Removed commit-provenance assertions from C17; it gates raw/derived bytes only.
- (d), Opus notes 5/6: added Middle with outs=2 to C7 and a direct T+1 us future-only state
  refusal for team_state and all three new blocks in C9. All 12 construct cases pass.
- (e), Opus note 3: the original intermittent child exit was not reproduced. New regression run:
  `5 failed, 5 passed`; failures included `unrecognized arguments: --candidate-sha` and
  `WindowsPath('C:/Users/neelj/nba-harness-h134').is_relative_to(tmp_path)` returning False.
  Child now uses sys.executable, an isolated temp cwd, explicit repo import path, full stdout/stderr,
  and exactly one logged `S480 child retry 1/1` for WinError 32/33 only. Persistent lock fails;
  deterministic ValueError and access-denied errors fail immediately. Final fixture/probe file: 11 passed.
  An intermediate check failed 3 tests because pytest rewrote AssertionError message whitespace;
  explicit raising now preserves the complete diagnostic, asserted against a 1,000-line stderr.
- (f), sol 4 / Opus correction 2: before `FAIL memo_candidate_stale=True`; old b091d9 record
  replaced by the verbatim inventory above using pinned a10bac3ada66e739cda81c7af3c94818f726ecaa.
  s480_memo_facts now requires --candidate-sha (full SHA); fixture log is bounded to that commit.
  Tests reject moving/short refs; comparisons use the full pinned 8f97cad2e baseline above.
  Lander must rerun inventory with its full fixture-adding SHA and record that SHA at landing.
All 18 per-file commands pass: 276 tests; acceptance remains 17/17 (15 new, 2 invariant),
plus 6 FIX 1a regression tests. Help commands and facts exit zero. No sealed module changed
in FIX 1a, so the existing seal remains byte-identical and recomputes without resealing.
The immutable 493-line book fixture is exempt from the source LOC rail per C17.

## NOT VERIFIED

- No scored real night under any seal; no calibration result is claimed.
- No real training history; h0/h1 are constructs.
- The new seal's real commit time and fixture-adding commits await landing; check once with real git.
- Postseason ticker series, capture coverage, and start date.
- Adapter-valid coverage of the frozen unselected blocks.
- The full-archive before-condition census and full-game/slice equivalence were not rerun in this fixture-only lane.
- The original intermittent C15 lock cause was not reproduced; retry coverage uses construct failures.
- The final September 29 scored-output inventory/decision, including the one unparseable JSON, awaits the orchestrator.
