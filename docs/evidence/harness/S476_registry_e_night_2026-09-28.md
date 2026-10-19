# S476 registry E night caller - 2026-09-28

FIX 1b addresses AMENDMENT 2(a)-(g); validation results are recorded below. E remains UNDECLARED and dormant. Acceptance cases: 21 of 22, with C20 failed on memory in the supplied Opus verifier run. The 22-of-22 bar is not met. This lane used constructs only and did not perform that real-window measurement.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h138, Python 3.10; constructs and an isolated temporary git repository only.
Candidate SHA: NOT CREATED (sandbox); files ready for lane_commit.
Pinned comparison base: 160d7a7ece2ff1917f07836d41e95e8a909eefe0. S488's ingame_scoreboard_night.py alone uses 791539e030861156dd97cbe617a2b7881b34942f. No test compares against a moving branch.

## Original candidate before-condition (prior build record)

The spec has no separately labelled shell command. Before coding, its stated module-absence and orientation premises were executed against the landed is_home_ticker using game 822842 and the quoted home_abbr='TEX', away_abbr='NYM'. Exact output:

```text
module_present= False
bare= KeyError('home_abbr')
enriched= True
```

The bare orientation failure and enriched success were already true, as the spec states. The new caller import was absent. The runner's early return without scoreboard and its missing e declaration were also confirmed before edits.

## Implemented numbered changes

1. Side-effect-free e_step constructs the specified argv plus AMENDMENT 1's --input-root and archive/module skips.
2. Population construction collects the whole window's accepted identities before streaming each required D/D+1 shard once. Only their rows survive exact Decimal as_of and selected_at filters. File order and duplicates reach the landed scorer intact; orientation comes from the first causal state row. Re-listed identities are counted and skipped. All six schedule/orientation counts, complete, and reader_census are retained.
3. Added canonical sealed CALLER_POLICY_E_2026-09-30.json, seven days. September 30 is no earlier than the existing block seal and later than the expected September 28/29 landing. Runtime committed-byte and strict prospective-commit checks remain mandatory; the lane does not backdate any seal.
4. The guarded child calls the landed score in-process, writes the complete private result atomically, then publishes a hashed receipt with a newly computed nightly paired_summary. Same-identity valid pairs remain untouched. Corrupt roots, stale metadata and corrupted private output are republished. An interrupted replace leaves the previous file recoverable.
5. The runner composes e independently of scoreboard/history; _run, NAMES and GATES are untouched.
6. E declaration validation requires all six keys and rejects malformed paths, missing keys, invalid lookback strings and Windows casefold aliases. Legacy budgets remain valid.
7. E is absent from ceiling_bytes and deadline_s until C20 passes AMENDMENT 1's 629145600 B / 900 s bar. All six producer keys remain, including lookback "7". No automatic shrink or ceiling adjustment exists.
8. The exact-budget test requires dormant E. Explicit construct budgets still exercise E and the scoreboard fake child. The orchestrator's existing LF rules cover the two JSON patterns below; this lane did not edit .gitattributes.

Specification reconciliation: _valid_training_rows requires exactly one {date}, while item 7 requires e_input_root to be a constant directory. Validation therefore applies the landed helper to e_input_root + '/{date}_full.json', including its alias comparison with e_out. The production budget retains the exact required constant directory. No private --input file is created. A direct CLI call also refuses an out path aliasing the configured private full-population file before any write.

Duplicate policy: first schedule listing in ascending day/file order is canonical; subsequent listings on the same or later day are counted and skipped. State/book/trade rows retain day/file order, including all same-instant copies, so the landed scorer keeps the first copy and counts subsequent duplicates. Its existing backward-timestamp refusals remain effective. Returned game bundles are sorted by identity.

## Imported landed contracts read before coding

- registry_scorer_e.py: score(games: list[dict], selected: tuple[str, ...], prereg_path: Path, block_config_path: Path) -> dict
- registry_scorer_e.py: paired_summary(context: dict, *, n_boot: int = BOOTSTRAP["n_boot"], seed: int = BOOTSTRAP["seed"]) -> dict
- registry_scorer_e.py: git_committed(path: Path) -> bool; committed_at(path: Path, *, root: Path | None = None, counts: Counter | None = None) -> D | None; canon_output(value: object) -> object
- registry_scorer_e_config.py: _venue_epoch(value: object) -> Decimal | None
- registry_scorer_e_config.py: load_block_config(path: Path, selected: tuple[str, ...], *, root: Path, git_committed: Callable[[Path], bool], committed_at: Callable[[Path], Decimal | float | None] | None = None, latest_input_us: Decimal | int | None = None) -> dict
- registry_scorer_e_config.py: implementation_identity(root: Path, files: tuple[str, ...] = IMPLEMENTATION_FILES) -> str
- registry_readers.py: _reject_constant(token: str) -> Decimal raises ValueError; its malformed_line convention is reused by the new streaming reader. No whole-shard read_jsonl call remains.
- scoreboard_history.py: _strict(raw: bytes) -> object; _valid_entry(value: object) -> None; history_step(root: Path, day: str, as_of: str, p: dict, raw: dict) -> dict
- paper_night_lock.py: runner_lock(directory: Path)
- venue_time.py: parse_venue_time(value: object) -> float | None; invoked by the reused _venue_epoch, which restores original fractional digits exactly.
- ingame_scoreboard_rules.py: is_home_ticker(sport: str, entry: dict, state: dict) -> bool
- paper_night_steps.py: _valid_training_rows(value: object, scoreboard_out: object) -> bool; _positive_int_str(value: object) -> bool
- paper_night.py: _steps(root: Path, day: str, as_of: str, nonce: str, budget: dict, context: dict | None = None) -> list[dict]; _run(step: dict, root: Path, budget: dict) -> dict

## Per-case evidence

| Case | Before / after evidence | Status |
|---|---|---|
| C1 | Bare KeyError and enriched True already true; first test consumes quoted orientation fixture through main and landed scorer; zero causal states counted | PASS |
| C2 | One bundle across two schedule days, source row order retained, one settlement call; both input permutations | PASS |
| C3 | D+1 settlement included; published windows disjoint | PASS |
| C4 | Effective-day window and clamped five-day window checked | PASS |
| C5 | D-1 microsecond excluded, D and D+1 microsecond included; full census unchanged | PASS |
| C6 | Future final/book/trade perturbations leave population and republished rows/summary identical | PASS |
| C7 | Nanosecond cutoff and inclusive day-end retained; all schedule rows validated before sport and MLB cutoff classification | PASS (FIX 1b) |
| C8 | Uncommitted, nonprospective, strict count types and pre-effective refusal; score/population spies never called | PASS |
| C9 | Fresh interpreter, real temporary git commit, both modules' provenance references explicitly patched, two opposite outcomes, finite target E | PASS |
| C10 | Conditional October 4 derivation below and embargo arithmetic test | PASS (conditional derivation) |
| C11 | Missing and malformed schedule each counted; other day's bundle survives | PASS |
| C12 | Exact empty state/rows, complete is True and six zero counts; populated warmup receipt complete | PASS (FIX 1b) |
| C13 | Same pair bytes/mtime unchanged; partial JSON, null/scalar/list roots and corrupted private output recover | PASS |
| C14 | Existing runner kills fake E child; E-path build_population spy checks exact arguments and excludes the budget mapping | PASS (FIX 1b) |
| C15 | Exact production argv, E declared alone with no scoreboard/history | PASS |
| C16 | Legacy validation and row order unchanged | PASS |
| C17 | Each missing key, invalid path/template, casefold alias and invalid lookback refuses | PASS |
| C18 | E exempt from unknown steps; unrelated unknown name still refused | PASS |
| C19 | Additional hypothetical training_history caller field refused | PASS (construct) |
| C20 | Supplied Opus verifier: peak >=834666496 B (796 MiB) exceeds 629145600 B; wall 352.7 s passes 900 s | FAIL (memory) |
| C21 | Broken JSONL line retains reader filename/line census; duplicate receipts passed intact to landed first-copy handling | PASS |
| C22 | Pinned invariant comparisons below; S488-owned file equals its full S488 commit SHA and is left untouched | PASS |

## C10 warmup

With effective_date 2026-09-30 and EMBARGO 3 days, the earliest training-eligible settlement from September 30 games cannot satisfy a boundary before 2026-10-01T00:00Z. October 4 is the earliest POSSIBLE fitted night, conditional on settled training games representing both outcomes and complete selected-block features. This is not a scheduling or capture guarantee. Four warmup nights are September 30 through October 3.

## C19

C19 S487 TRANSITION (memo + a construct refusal case): E's two existing seals and this row's caller-policy seal are untouched by S487's own separate training-only history mechanism; a hypothetical S487 history row is never read by this module (no import, no path reference) and can only be consumed after a NEW prospectively-dated caller-policy migration -- fail closed, never silently adopted.

## C20

C20 CAPACITY QUALIFICATION (orchestrator, real archive, before "e" is trusted unattended): the busiest captured 7-day MLB window's bytes/games/ticks, wall time and sampled process-tree peak (paper_night_tree_sampler, reused) recorded in the memo; ceiling_bytes.e/deadline_s.e stay NOT PROFILED in this row's commit and are revised in a FOLLOW-UP row once this number exists, never inferred here.

AMENDMENT 2 records the supplied Opus tier-2 verifier's C20 rerun, not a measurement by this lane. The verifier used the real 2026-09-22..28 MLB window, day 2026-09-28, lookback 7, effective date 2026-09-22 and as_of 2026-09-29T06:00:00Z. Its reported process-tree peak was 796 MiB (at least 834666496 B), above the 629145600 B (600 MiB) bar: FAIL. Wall time was 352.7 s, within 900 s: PASS.

The verifier reported 1150 MiB read, 19 games, 10877 state / 10131 book / 49770 trade retained ticks (70778 rows), 7090 eligible ticks and 7090 output rows. Tonight had zero rows and zero fitted results; schedules for September 27 and 28 were absent, so complete was false. Population construction took 12.2 s and scoring 338.7 s. The population-only attribution probe reached 751 MiB RSS after build_population (752 MiB peak), from a 78 MiB import baseline: approximately 670 MiB was retained full-row population, rather than shard loading.

The C20 result is failed qualification, leaving 21 of 22 cases and the 22-of-22 bar unmet. E stays UNDECLARED in both ceiling_bytes and deadline_s; its producer arguments remain dormant. Follow-up S489 must reduce retained rows to scorer-used fields or spool accepted rows, then rerun C20 within both bars before declaring E. The intended activation is before the October 4 night; the rolling population reads the capture archives directly. This lane opened no real archive and made no capacity measurement. The construct allocation probe does not qualify C20.

## Tests and reproduction

Run one file at a time with python -m pytest <path> -q -p no:cacheprovider:

| tests/platformkit/execution/ file | Passed |
|---|---:|
| test_registry_scorer_e_night.py | 33 |
| test_registry_scorer_e_night_1a.py | 13 |
| test_registry_scorer_e_night_1b.py | 15 |
| test_paper_night_e_step_e2e.py | 41 |
| test_paper_night.py | 39 |
| test_paper_night_steps.py | 56 |
| test_paper_night_scoreboard_step.py | 14 |
| test_paper_night_scoreboard_step_1c.py | 4 |
| test_paper_night_scoreboard_step_1d.py | 2 |
| test_paper_night_scoreboard_step_1e.py | 1 |

Total after FIX 1b: 218 passed across ten files. The first runner batch yielded before completion; its three affected files were rerun serially with 39, 56 and 14 passes. registry_scorer_e_night --help and paper_night --help exited 0. Neither CLI exposes a separate self-check flag; contract_preflight is the row's contract check.
The FIX 1a before/after outputs are recorded below. Temporary construct files and the fresh subprocess git fixture stayed in the system temporary directory; no scratch was created in the worktree.
The subprocess fixture selects mid and team_state with complete features, constructs both training outcomes, and patches committed-byte/time references in BOTH imported modules. It does not replace score or fit. Production argv is asserted independently and never run against the archive.

Existing-test before/after: test_paper_night.py::test_declared_budget_exact now expects five declared producer steps with E's six keys retained. test_paper_night_scoreboard_step.py supplies an e fake child in its explicitly activated construct budget and expects FROZEN_LEGACY_NAMES + ["scoreboard", "history", "e"]. No threshold changes.

LF patterns already supplied by the orchestrator, verified present and left unchanged:
- docs/evidence/forward/registry_e/*.json text eol=lf
- docs/evidence/forward/scoreboard/CALLER_POLICY_E_*.json text eol=lf

Contract preflight command: python -m scripts.platformkit.tracking.contract_preflight --paths <the 12 candidate paths listed by git status, excluding the verdict and unchanged .gitattributes> --base master --spec docs/evidence/tracking/specs/S476_spec.md. Only this mechanical command uses the requested branch argument; all invariant tests and memo comparisons use full pinned SHAs. Final result recorded in FIX 1b below.

## A9 and C22 pinned input audit

Sizes and hashes below normalize CRLF to LF. All sources are local text; resolution is Python/JSON text or documentation, not video. Construct input rows are durable inline fixtures in the four owned test files; no archive input was opened. Sizes describe this audit only; no byte-length assertion is embedded in tests for another row's module. The S488 row compares to 791539e030861156dd97cbe617a2b7881b34942f; all other baseline comparisons use 160d7a7ece2ff1917f07836d41e95e8a909eefe0.

| Full input path | LF bytes | Candidate SHA-256 | Versus pinned base |
|---|---:|---|---|
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/registry_scorer_e.py | 17756 | 55c75aca523c2803dbc65af06a12d5192b613e284543e72d0e2daf24f6b4cdbd | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/registry_scorer_e_fit.py | 10276 | b3dd16d88b82bc087ec7f4be40a931b76ac5c7fd5bffd78c6d2945a776ceb997 | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/registry_scorer_e_config.py | 10568 | a1cbff0b7ba34e20c6e61c0d66f3331be247446119ea60fc3c962888f09a2ee1 | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/registry_scorer_e_ticks.py | 12672 | a6e751fb2d537560fc99f289f3adaedd3515b25779e58d7bb5b32e564957cc8b | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/ingame_scoreboard_rules.py | 9871 | 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351 | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/scoreboard_history.py | 13751 | b21ccac74b0acaf524d113e54203cdcc889835562fc3de58c931f80c804d50c7 | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/scoreboard_history_store.py | 14706 | 18c75744234b43bb3988566e8960ef1d7ea2a11e41eeadef67ec4fc52139769f | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/ingame_scoreboard_night.py | 9682 | 8a34c4f4fca9f0c4395f8256d97603797d717d744e65df2e656f897a6645da24 | EQUAL to S488; NOT EQUAL to original base |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/paper_night_deadline.py | 14592 | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/paper_night_lock.py | 1069 | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/execution/venue_time.py | 1972 | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 | EQUAL |
| C:/Users/neelj/nba-harness-h138/scripts/platformkit/ingame/registry_readers.py | 3669 | 17e99577505a99c4687835b3d0812d9f90c7ca56b7406a57d72852fb47371ab3 | EQUAL |
| C:/Users/neelj/nba-harness-h138/docs/evidence/forward/scoreboard/PREREG_E_2026-09-25.json | 1423 | a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0 | EQUAL |
| C:/Users/neelj/nba-harness-h138/docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-30.json | 771 | f74e50e728bc848f13dbd54177c3d223a740797f9eda5c490e66bae25ee36c18 | EQUAL |
| C:/Users/neelj/nba-harness-h138/docs/evidence/tracking/specs/S476_spec.md | 23723 | ceaabaaba2bcc87993417a5dfd4d7232cce758fb8a5d91c64f0ec92440175a46 | NOT EQUAL; binding amendment supplied |

Construct fixture source artifacts (new files; no baseline existed):

| Full path | LF bytes | SHA-256 |
|---|---:|---|
| C:/Users/neelj/nba-harness-h138/tests/platformkit/execution/test_registry_scorer_e_night.py | 14841 | 24e6948595e95763aa81b419a894491660db4001b77ff5e3dccbc13bb87c8cfc |
| C:/Users/neelj/nba-harness-h138/tests/platformkit/execution/test_paper_night_e_step_e2e.py | 13303 | 8772fafeb562d341ce8a9608d9c442c7a789439a1bdb3eb253a237db5d52f415 |
| C:/Users/neelj/nba-harness-h138/tests/platformkit/execution/test_registry_scorer_e_night_1a.py | 8607 | fc0ea52146f42665ce4f74439b54330936bc61e5fd9c67ec02eef6ee6b70a921 |
| C:/Users/neelj/nba-harness-h138/tests/platformkit/execution/test_registry_scorer_e_night_1b.py | 3878 | b34b05f7c2fafbd54df2ed0b40b3b13e7a31e6fcbeacd19b1cbf69d7d967366d |

Protected runner segments (same pinned base):

- NAMES: EQUAL; SHA-256 ff3e60447732a762838e3685ace175937763c7757b70a86d56c7b98725ca3856.
- GATES: EQUAL; SHA-256 f5140811da7cd228386f345de8b296a788249eb0b885f5fee6ab610d7d5eeff0.
- _run: EQUAL; SHA-256 9b1441d6027b88142d7504124ef461d5503e60bc0f69ebab23dce9d2fc0ad1e0.

## ORCHESTRATOR COPY

NOT RUN: a verbatim raw archive slice was not necessary or opened. The spec quotes only game 822842 and its TEX/NYM orientation values; those appear verbatim in REAL_ORIENTATION. Ticker, schedule, timestamps, books, scores and all training cases are explicitly synthetic. No copy command is asserted without a known source path.

## FIX 1a

AMENDMENT 1(a)-(g) only. Before production edits, the new construct file reported `8 failed, 3 passed in 1.37s`; the original integration file reported `1 failed, 40 passed in 2.41s`. Separate trade/path probes used TemporaryDirectory fixtures. The table quotes those observed failures, then names the change and passing regression. No real shard was read to reproduce the capacity failure.

| Amendment / verifier finding | Reproduced failing output | Change / after evidence |
|---|---|---|
| (a) Opus 1, streaming and capacity | `AssertionError: construct peak bytes: [565397, 16133914]`; `assert (16133914 - 565397) < 1000000` | Stream lines with Decimal and _reject_constant; collect identities first; one pass per shard; no whole-shard cache. Fixed retained population at 1 book and 1 state while unrelated lines grow 128 to 4096; peak-growth assertion now passes. C20 remains unqualified, so E declaration removed while producer keys remain. |
| (b) sol 1, inclusive selection | `AssertionError: {'games': 0, 'late_selection': 1}` | selected > end replaces >= end. Exact-boundary case now accepts 1 game with 0 late selections; one nanosecond later rejects. C7 late fixtures corrected. |
| (c) Opus 3, duplicate records | `trade_rows=0, duplicate_trade=2`; state duplicate probe: `assert 0 == 1` | Pass all matching rows in file order to the landed first-copy logic. Tests retain both copies of state/book/trade; tick stream keeps the first, counts the second, and preserves the first final settlement. |
| (c) Opus 7, duplicate listing | `AssertionError: {'duplicate_schedule_listing': 2, 'games': 0}` | First same-day listing retained, one duplicate counted. A later listing with an earlier selected_at cannot replace the first. |
| (d) Opus 4, public paths | `assert 'C:\\Users\\n...\\caller.json' == 'caller.json'`; shard probe returned `shard_absent:C:` prefixes | caller_policy.path is relative to root with POSIX separators. Missing-shard keys are exactly shard_absent:state/mlb/2026-09-25.jsonl and shard_absent:kalshi/mlb/2026-09-25.jsonl. |
| (e) Opus 6, dead input-root | `assert '--input-root' in argv`; `__main__.py: error: unrecognized arguments: --input-root private/custom` | Required child flag now carries the budget value through publication, full-output path validation and idempotence. Custom-directory, corrupt-pair and changed-directory reruns pass. |
| (f) sol 2 / Opus 5, LF rules | Already corrected by the orchestrator before this turn; presence regression passed before edits | No .gitattributes edit. Corrected attribution and wildcard pattern in this memo; presence regression remains passing. No new on-disk JSON fixture added. |
| (g) Opus 2 / sol note 3, S488 inventory | `At index 219 diff: b's' != b't'`; C22 integration file `1 failed, 40 passed` | Re-pinned only ingame_scoreboard_night.py to full S488 SHA 791539e030861156dd97cbe617a2b7881b34942f. Inventory above regenerated against fixed SHAs. Integration file now 41 passed. |

After: regression file 13 passed, original population file 33 passed, integration file 41 passed; all nine required files total 203 passed. The growth probe checks Python allocation growth for synthetic unselected rows, not real process-tree RSS or runtime. Code review found no in-scope blocker. Contract preflight: all nine checks PASS over the 11 candidate files (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication).

## FIX 1b

Only AMENDMENT 2(a)-(g) is addressed. Previously confirmed immutable inventory and contracts remain unchanged. The failure and pass outputs below must come from this lane's construct runs; the Opus C20 results above are attributed supplied evidence.

| Amendment / verifier finding | Required correction | Reproduction / validation |
|---|---|---|
| (a) sol 1, malformed late schedules | Run _valid_entry on the complete list and validate every row identity and timestamp before classification; malformed late rows invalidate the schedule and complete=False. Correct the earlier permissive regression. | `{'schedule_invalid': 0, 'late_selection': 1, 'complete': True}`; After: test_a_validate_entire_schedule_before_classification (8 cases) and corrected C7 pass; schedule_invalid=1, late_selection=0, complete=False. |
| (b) sol 2, sport census ordering | Count valid non-MLB entries as unsupported_sport before MLB selection cutoffs. | `{'late_selection': 1, 'unsupported_sport': 0, 'complete': True}`; After: test_b_unsupported_sport_precedes_mlb_cutoffs (2 cases) passes; unsupported_sport=1, late_selection=0, complete=True. |
| (c) sol 3, shard paths | Resolve under root, refuse escapes, and label with path.relative_to(root).as_posix(), retaining capture_root. | `shard_absent:state/mlb/2026-09-24.jsonl` for capture_root `data/cache/view`; D/D+1 state/kalshi labels all omitted that prefix; After: test_c_shard_labels_keep_resolved_capture_prefix and test_c_capture_escape_refused_before_reader (4 cases) pass; labels include data/cache/view and escapes raise before reading. |
| (d) sol 4, C14 budget isolation | Invoke the E path with a build_population spy; assert exact scalar/path arguments contain no budget mapping. | `build_population spy present = False` (C14 source inspection); After: both C14 kill cases pass and main invokes the spy once with (tmp_path, 2026-09-24, 7, 2026-09-24, {date}.json, Path(capture), 2026-09-25T12:00:00Z), no kwargs or mappings. |
| (e) sol 5, C12 exact assertions | Require complete is True, exact state/rows, all COUNT_KEYS equal zero, and a complete warmup receipt. | `malformed receipt passes old C12 assertion = True` for complete=1, rows=[], counts={}; After: C12 and C1 warmup pass with complete is True; empty state=produced, rows=[], and exactly every COUNT_KEYS value zero. |
| (f) Opus 2, dormant import isolation | Import the E-step module only inside the declared-E branch of paper_night._steps. | `ImportError: synthetic E import failure` with e undeclared; After: test_f_dormant_e_does_not_import_module passes; dormant night returns the legacy steps, while explicit E still raises the synthetic import failure. |
| (g) Opus 1, C20 memo correction | Replace NOT RUN with the supplied Opus numbers and memory FAIL; record dormant E, 21 of 22, and S489 retained-row reduction/spooling plus C20 rerun before activation. | Before: `No archive read or measurement authorized in this lane` / `NOT RUN`. Memo now records the supplied verifier memory FAIL; no lane capacity run. |

Before production edits, the new regression file reported `13 failed, 2 passed in 1.20s`; after the fixes it reported `15 passed in 0.84s`. Final per-file counts are 33, 13, 15, 41, 39, 56, 14, 4, 2 and 1 in the table order above: 218 passed. Both --help commands exited 0; neither exposes a self-check option. contract_preflight passed all nine checks over 12 candidate paths, excluding the verdict and .gitattributes. No new JSON seal or on-disk JSON fixture is added for FIX 1b. The two existing LF patterns listed above remain unchanged; this lane did not edit .gitattributes.

## NOT VERIFIED

- A passing C20 qualification and the 22-of-22 full acceptance bar. The supplied Opus run failed memory; a complete seven-night schedule set remains unmeasured.
- Actual September 30 schedule/capture, settlement clocks and the first unattended night.
- A production run using all seven selected blocks in the existing September 30 block seal; the subprocess construct uses two selected blocks.
- Actual landing commit time and committed status of the new caller seal. Runtime fails closed until it is committed prospectively; landing on/after September 30 needs a newly prospective policy, never a backdate.
- Power-loss durability of directory metadata and physical Windows crash recovery. The simulated replace failure preserves the previous file; fsync and atomic replace are exercised normally.
- A raw 2026-09-24 archive replay. Only the quoted orientation values were used.
