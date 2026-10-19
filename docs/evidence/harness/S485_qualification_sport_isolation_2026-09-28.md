# S485: remove the missing-shard global refusal

BUILD COMPLETE; AMENDMENT 2 branch (c) applied: the stale mocks were corrected without weakening their assertions, and test_forward_qualification_inputs.py shows 48 passed in FIX r1. Round 1 received ACCEPT and ACCEPT WITH CORRECTIONS; FIX r2 below records Amendment 3 verification.

Machine: local Windows worktree `C:/Users/neelj/nba-harness-h140`, CPU-only construct roots. No network, pod, real archive, registry write, deployment, or feature activation. The lane PREPARES the candidate.
Binding source: `docs/evidence/tracking/specs/S485_spec.md`, including AMENDMENTS 1, 2 and 3; contract `docs/evidence/tracking/VERIFIER_CONTRACT.md` A/B/Q/S clauses.
Pinned base commit: `2132fcf64c7039c4ea51097b7de96b85aa790bbe`. Candidate commit: NOT CREATED; full LF-normalized source SHA-256 identities appear below. No test or identity comparison resolves a moving revision.

## Binding before-condition, run before coding

The in-process probe used only a scratch temporary tree; both D/D+1 kinds were present for MLB, NBA D-state alone was omitted, and the policy ledger pointed inside the scratch root. Output:

```text
before_missing code=3 refused=1 refusal_reason=state_shard_missing scheduled_games_total=2 games_total=0 games=[]
state mlb 2026-09-24 present=True
state nba 2026-09-24 present=False
```

A second single-MLB probe omitted both D+1 files and used `as_of=2026-09-24T00:00:00.000001Z`. Output included:

```text
books mlb 2026-09-25 present=False
state mlb 2026-09-25 present=False
```

The second probe returned code 0, refused 0, refusal_reason None, scheduled_games_total 1, games_total 1. This establishes unconditional D+1 enumeration before the fix; it does not establish usable state.

## Production change and signatures read before coding

`forward_qualification_daily.py` remains 300 lines: initializes the strict integer counter at zero, passes `args.as_of`, and counts each missing D-state sport instead of setting the scalar refusal. The complete schedule still reaches replay.
`forward_qualification_inputs.py` gains required `as_of` and the pure `_needs_next_day(day: date, as_of: str) -> bool`; its parser import is new. The helper reproduces the landed planner's microsecond boundary formula, inclusive at midnight. Invalid unzoned text raises `invalid_time`.
`paper_night_inputs.py` now uses `window["days"]` for qualification presence and emits `global_refusal_expected=None`, retaining `missing_day_d_state`. The stale prediction described in the original spec is FIXED under amendment ownership.

Exact landed entry signatures used:

- `parse_venue_time(value: object) -> float | None` in `scripts/platformkit/execution/venue_time.py`.
- `stamp(value: object) -> Decimal` and `iso(value: Decimal) -> str` in `scripts/platformkit/execution/forward_replay_io.py`.
- `_archives(schedule: list, books_root: Path, state_root: Path, day: date) -> list` before the required `as_of: str` addition.
- `main(argv: list | None = None) -> int` in `scripts/platformkit/ops/forward_qualification_daily.py`.
- `_digest(path: Path, counts: Counter, *, trim_tail: bool = False) -> dict` and `_snapshot(entry: dict, root: Path, relative: str) -> Path` in the owned input module; unchanged.
- `load_native_streamed(books_paths: list[Path], state_paths: list[Path], trade_paths: list[Path], supervisor_journals: list[Path], schedule: list[dict], *, as_of: object, scratch_dir: Path) -> StreamedEvidence`; the existing daily call retains `scratch_dir=snapshots`.
- `input_window(day: str, as_of: str) -> dict`, `plan_inputs(root: Path, day: str, as_of: str, p: dict, budget: dict, *, schedule_rows: list | None = None) -> dict`, `record_inputs(plan: dict, rows: list[dict]) -> dict` in `paper_night_inputs.py`.
- `_steps(root: Path, day: str, as_of: str, nonce: str, budget: dict, context: dict | None = None) -> list[dict]` and `main(argv: list[str] | None = None, *, steps: list[dict] | None = None) -> int` in `paper_night.py`.

Reader survey found one production `_archives` caller, updated here. `global_refusal_expected` is forwarded by `record_inputs`; its asserting readers are the planner tests and `test_paper_night_inputs_e2e.py`. The latter already expects None. No refusal enum, profile bar, schedule field, or qualification threshold changes.

## Enumerated acceptance cases

Metric: 44 / 44 candidate construct checks, n=44 (CONSTRUCT), eye check n/a. This is 42 new candidate test nodes plus the two amended planner variants in the existing planner file. Source-contract checks and baseline-only tests are additional verification, not extra denominator units. Original case 4 is explicitly split into two kind variants.

| Spec case / amendment | n | Pinned before behavior | Candidate result |
|---|---:|---|---|
| 1, one missing sport | 1 | exit 3, games empty | MLB keyed summary equal under cap 100; NBA FAIL; counter 1 |
| 2, two missing sports | 1 | exit 3, games empty | MLB unchanged under cap 100; counter 2 |
| 3, absent versus empty | 1 | absent globally refuses; empty does not | keyed NBA summaries equal when no other usable state; counters 1/0 |
| 4, state-only and book-only missing | 2 | state refuses; book does not | both return one FAIL in the closed reason set |
| 5, NFL both absent | 1 | exit 3, games empty | exit 0, exactly NFL's one FAIL |
| 6, at midnight | 1 | 4N archives | 4N archives |
| 7, midnight minus 1us | 1 | 4N archives | 2N archives |
| 8, midnight plus 1us | 1 | 4N archives | 4N archives, enumeration equal to case 6 |
| 9, missing D+1 | 1 | missing digest fields are null | unchanged null digest/size and counted absence, no refusal |
| 10, empty D+1 | 1 | present with empty hash and zero sizes | unchanged |
| 11, newline-terminated malformed D+1 | 1 | D+1 enumerated even before midnight | unopened before boundary; afterwards invalid_json=1, unreadable_state=1 and global LINKAGE_INVALID |
| 12, schedule permutation | 1 | missing D still refuses in either order | keyed summaries and archive projections equal; schedule hashes differ |
| 13, real generated child and fresh reader | 1 | RAN, exit 3, child_nonzero_exit, games 0 | RAN, exit 0, reason None, current nonce, resolved r1 artifact, MLB present, counter 1 |
| A1, five sports x absent/empty/unusable state | 15 | absent globally refuses; empty/unusable reach FAIL | all report FAIL, zero decisions/coverage and full-window state gap; strict counter 1/0/0 |
| A1, D missing but D+1 sufficient | 1 | early global refusal | PASS using frozen bars, 720 decisions, full window coverage, state gap 15000ms |
| A2, cap 100 and binding cap 1 | 2 | missing sport globally refuses | non-competing MLB equal; competing MLB decisions change from 0 to 1; both schedule orders checked |
| A3, shared native key | 1 | duplicate state key omits sport | two duplicates refused; both games retain LINKAGE_INVALID, order invariant |
| A3, malformed X | 1 | unreadable state has global effect | MLB gains LINKAGE_INVALID while decisions stay 1; both orders checked |
| A6, healthy and quiet explicit zero | 2 | counter absent | strict integer zero |
| Exact nanosecond and offset boundary | 4 | D+1 always enumerated | both sides distinguished, including offset equivalents |
| Unzoned cutoff | 1 | parser refuses | helper raises invalid_time |
| Receipt equality and later invalid receipt | 1 | replay's existing causal filter | equality contributes to state gap; +1ns counts future_records; both input orders equal |
| A4, planner missing-state and both-missing | 2 | days include NEXT and expected global refusal | days=[D], NEXT presence omitted, missing list retained, expected global refusal null |

Only non-competing conditions support the summary equality claim. Missing D does not force FAIL if eligible D+1 state meets the frozen bars. Shared reservation inventory, native duplicate keys, and malformed-state global effects remain unchanged. Sorting establishes stable projections; it does not make complete artifacts identical.
MANDATORY DISCLOSURE, adjudication (i): even with both NBA state shards absent, 240 NBA-labelled rows in MLB's D+1 shard can yield NBA PASS with 720 decisions. The frozen forward_capture_bridge.py groups by each row's sport. Register row S496 owns the guard requiring row sport to equal shard-directory sport; S485 pins the current behavior.
Run-level diagnostics and input_counts are NOT sport-isolated (X-present vs X-absent changes LINKAGE_INVALID, state_key_absent, no_game_date, state_rows_missing_start, absent_or_unreadable_input and state_shard_missing_sports), while keyed game summaries and archive rows of non-competing sports are unchanged.
D+1 supports cross-midnight books/state and receipt-visible backfill closure. Receipt equality remains visible; a later receipt is counted and filtered before schema validation and de-duplication. The unchanged replay retains exact sub-microsecond fractions.
Books and state missing-file behavior are now symmetric by construction, not through a new shared code path. A future design requiring different state-file treatment must revisit this removed early refusal.

## Reproduction and test results

Run one file per command: `python -m pytest <path> -q -p no:cacheprovider`. No full-suite invocation.

| File | Result |
|---|---|
| tests/platformkit/ops/test_forward_qualification_sport_isolation.py | 21 passed |
| tests/platformkit/ops/test_forward_qualification_cross_sport.py | 23 passed (FIX r2) |
| tests/platformkit/execution/test_paper_night_qualification_isolation.py | 2 passed (candidate plus pinned baseline) |
| tests/platformkit/ops/test_s485_baseline_contract.py | 4 passed |
| tests/platformkit/ops/test_s485_baseline_cases.py | 22 passed |
| tests/platformkit/ops/test_forward_qualification_daily.py | 31 passed |
| tests/platformkit/execution/test_paper_night_inputs.py | 40 passed |
| tests/platformkit/ops/test_forward_qualification_inputs.py | 48 passed (FIX r1) |
| Same unchanged input test file in full pinned package | 46 passed, 2 failed |

The initial two failures were `test_the_projection_happens_before_anything_reads_the_entry` and `test_a_prefix_rewritten_during_the_run_refuses`. Amendment 2 now authorizes their stale mock signatures to be corrected. FIX r1 below records the reproduction and resolution. The pinned-package result above is historical evidence from the initial build, not a current candidate failure.
Baseline comparison helpers extract all repository dependencies from the full pinned commit into temporary packages, set PYTHONPATH to those packages, and execute from there. Original-case baseline outputs are also exposed as pytest record_property values. No current dependency is silently substituted.
`python -m scripts.platformkit.ops.forward_qualification_daily --help` and `python -m scripts.platformkit.execution.paper_night --help` exit 0. The other modified modules have no CLI.
Preflight: FIX r2 records the exact output using `--base 2132fcf64c7039c4ea51097b7de96b85aa790bbe`, including this memo. All durable identity evidence and tests use that full pinned SHA.

## Must-not-move named tests

The source-contract test compares exact function source against the pinned commit. The daily exception is ONLY the second half of `test_missing_book_is_not_a_refusal_but_missing_state_is`; its first half is byte-identical. Every other daily test below is byte-identical:
- `test_real_production_rows_end_to_end`
- `test_a_live_shard_that_grows_during_the_run_passes`
- `test_missing_schedule_refuses_and_still_hashes`
- `test_schedule_refusals_are_counted`
- `test_a_cleanup_failure_never_masks_a_refusal`
- `test_rerun_never_overwrites_the_date_artifact`
- `test_import_graph_and_artifact_carry_no_scoring_surface`
- `test_served_flag_never_changes_a_verdict`
- `test_a_capture_root_without_both_subtrees_refuses`
- `test_the_ttl_and_tick_come_from_the_declared_profile`
- `test_a_ttl_override_must_equal_the_declared_value`
- `test_unconsumed_supervisor_records_are_counted_never_a_failure`
- `test_a_bad_declared_cap_or_as_of_is_a_usage_error`
- `test_help_exits_zero`
- `test_quiet_day_is_valid_but_unreadable_selection_refuses`
- `test_state_provenance_uses_realpaths_and_snapshot_receipts`
- `test_snapshot_source_errors_are_distinct_from_destination_errors`

All 22 input test functions retain their assertions. Amendment 2(c) authorizes only the two mock signatures and one forwarding call listed in FIX r1; all other function source remains byte-identical:

- `test_counts_and_declared_quantities_refuse_loose_values`
- `test_a_broken_declaration_file_is_an_enumerated_refusal`
- `test_an_absent_declaration_file_refuses_and_still_hashes`
- `test_a_declaration_file_the_cli_cannot_index_refuses`
- `test_every_declared_sport_resolves_to_its_own_family`
- `test_a_poisoned_schedule_entry_never_reaches_the_artifact`
- `test_the_projection_happens_before_anything_reads_the_entry`
- `test_the_declared_caps_are_required_with_no_default`
- `test_an_unenumerated_raise_becomes_an_enumerated_refusal`
- `test_a_bad_report_row_is_an_enumerated_refusal`
- `test_a_prefix_rewritten_during_the_run_refuses`
- `test_a_shard_changed_before_the_copy_refuses`
- `test_the_prefix_check_refuses_a_truncated_input`
- `test_a_failed_write_never_leaves_a_zero_byte_date_claim`
- `test_a_game_key_that_is_not_a_nonempty_string_refuses`
- `test_every_declared_family_including_quiet_ones_is_appended`
- `test_a_family_that_is_not_the_sports_declaration_is_refused`
- `test_a_tie_away_from_the_maximum_as_of_never_decides_the_date`
- `test_two_artifacts_at_the_maximum_as_of`
- `test_the_first_append_creates_the_ledger_parent_directory`
- `test_growth_during_prefix_read_is_counted_from_open_handle`
- `test_torn_tail_is_excluded_from_snapshot_digest_and_prefix`

## A9 source identities, LF-normalized

Every relative path below resolves under `C:/Users/neelj/nba-harness-h140/`. Resolution is source text/JSON/JSONL, not imagery. Bytes and both full SHA-256 values are over LF-normalized UTF-8 content. New candidate paths have no baseline object. These are recorded identities, never working-copy byte-length assertions on another row's file.

| Path | LF bytes | Candidate SHA-256 | Base SHA-256 | Equality |
|---|---:|---|---|---|
| `scripts/platformkit/ops/forward_qualification_inputs.py` | 13377 | 4ee9a9c685c81cd2b16b404219bfdcc28b55aea1596ff2e07cc21a43a84d8763 | 086fd442b657ef9039ef4b6984a9f2aaf96a3330e30095b8049bd2a481fbe775 | NOT EQUAL |
| `scripts/platformkit/ops/forward_qualification_daily.py` | 15247 | 317c03ae4d5cb03cf9308d78ba40b2c99581d2022cdcc8dfebd88381710a2835 | ada413a1665516303cc2d3de35088d7888a05dd2238c084c40d6e0431797a15e | NOT EQUAL |
| `scripts/platformkit/execution/paper_night_inputs.py` | 9270 | 252ad7b0dfec5919f6383b1fd6521b0674ec00b4c891c3e14bafe0fd10e28f99 | 4163a4ed8217b9eedb67965cb0b49161594b0b1ab7078bc182b110638d159da9 | NOT EQUAL |
| `tests/platformkit/ops/test_forward_qualification_daily.py` | 19396 | f5f84e42b454d4bbd1950e522bfa3e17d9e19ea6dd76cd6ac876d63f07ffe9c5 | c4dea30d4e3457ee860a79212ad360df9cecde1b488e848d95dd95fb5080ea85 | NOT EQUAL |
| `tests/platformkit/ops/test_forward_qualification_inputs.py` | 17865 | 9723a78bc9057c782f7c764e4f8a42b91206efc6b33111ba9efef477f392b58f | d28638d5e2be187f455f663efb1713cbf695bf1675a69906f9e2b89f79fd2421 | NOT EQUAL |
| `tests/platformkit/execution/test_paper_night_inputs.py` | 15975 | d2ae20ced5011c2ec0345bd689f94bebb7746929590fe4c3a733f72c78b8a453 | 139c9eef41df8acb9607f4995738c0f128e11155847620093bf503fb68c89d17 | NOT EQUAL |
| `tests/platformkit/ops/test_forward_qualification_sport_isolation.py` | 10688 | 6753992079ffee54061b7528e09ce423cabfe7f55ff5698f3283a01ef2c3c465 | NOT PRESENT | NOT EQUAL |
| `tests/platformkit/ops/test_forward_qualification_cross_sport.py` | 10062 | 5d134a3e624fec03114ef55c1baccbd488678b73e2bb45b13603636b51362875 | NOT PRESENT | NOT EQUAL |
| `tests/platformkit/ops/test_s485_baseline_contract.py` | 6910 | 9f9df45e04337d9453a2de3b068320383f1325160a65d1bb5e06cd922015e228 | NOT PRESENT | NOT EQUAL |
| `tests/platformkit/execution/test_paper_night_qualification_isolation.py` | 8974 | 342d50856fd746631a06f92fc895d47734ad37bd3c00dfa48921a9932006e3f7 | NOT PRESENT | NOT EQUAL |
| `tests/platformkit/ops/test_s485_baseline_cases.py` | 6970 | 25a47a2ea807f3bf421c9d74b60faaeef3b69917367167342673374094c64e9a | NOT PRESENT | NOT EQUAL |
| `scripts/platformkit/execution/fill_model/fill_realism.py` | 10561 | 340f52e417dbc3a3c3dbe33baff0ad1e2a9d5033ea03c085f8640f5178aa43b9 | 340f52e417dbc3a3c3dbe33baff0ad1e2a9d5033ea03c085f8640f5178aa43b9 | EQUAL |
| `scripts/platformkit/execution/fill_realism.py` | 18420 | 9101eec1e870e0acf5a26dc88153e321764aecde2eda27459718770befc27f8f | 9101eec1e870e0acf5a26dc88153e321764aecde2eda27459718770befc27f8f | EQUAL |
| `scripts/platformkit/execution/fill_realism_classify.py` | 9519 | bfb4f1b512e810ae345dd91d91e4f31f94ebfeffcdc2a67fe26286d9e079917f | bfb4f1b512e810ae345dd91d91e4f31f94ebfeffcdc2a67fe26286d9e079917f | EQUAL |
| `scripts/platformkit/execution/fill_realism_io.py` | 16958 | 759a7ab6f3a1c0fd34e67d744be6261dac2e5e95b2956bffa8b6eca0897d231e | 759a7ab6f3a1c0fd34e67d744be6261dac2e5e95b2956bffa8b6eca0897d231e | EQUAL |
| `scripts/platformkit/execution/fill_realism_markout.py` | 4547 | bd825edbc49b09e89bbb1dc56f8c807b294a1c02a75f5aaf6c61442332fefb0e | bd825edbc49b09e89bbb1dc56f8c807b294a1c02a75f5aaf6c61442332fefb0e | EQUAL |
| `scripts/platformkit/execution/fill_realism_night.py` | 3121 | 4fbca76da1451a24c092a884b04b4d81d6371b07c4bfd80c34fa470b52ba5e9e | 4fbca76da1451a24c092a884b04b4d81d6371b07c4bfd80c34fa470b52ba5e9e | EQUAL |
| `scripts/platformkit/execution/forward_capture_bridge.py` | 14359 | 549eb23f2c33e764ab1e72be9efecf490cc6790db0c97a5f2af812617355aaa5 | 549eb23f2c33e764ab1e72be9efecf490cc6790db0c97a5f2af812617355aaa5 | EQUAL |
| `scripts/platformkit/execution/forward_capture_stream.py` | 8558 | 12b2fbf9d0a7938a9a3879b392d02d8b10111164e33b690c63b08519b104cb4f | 12b2fbf9d0a7938a9a3879b392d02d8b10111164e33b690c63b08519b104cb4f | EQUAL |
| `scripts/platformkit/execution/forward_replay.py` | 15821 | d88f198aa684b8a96362a3edd6509e30d64f808317989cafdc09e71c3a7ede21 | d88f198aa684b8a96362a3edd6509e30d64f808317989cafdc09e71c3a7ede21 | EQUAL |
| `scripts/platformkit/execution/forward_replay_io.py` | 9277 | b2ec0afa9d8bcd0ed2d25a3d7a9e796dbaf8f079cd396551da7d8675281c5962 | b2ec0afa9d8bcd0ed2d25a3d7a9e796dbaf8f079cd396551da7d8675281c5962 | EQUAL |
| `scripts/platformkit/execution/forward_replay_policy.py` | 11940 | e81fed58cbd2772c94d0771e574af3cc8b9268cdc1e4e3d1a05bd5bbc122c71e | e81fed58cbd2772c94d0771e574af3cc8b9268cdc1e4e3d1a05bd5bbc122c71e | EQUAL |
| `scripts/platformkit/execution/forward_replay_qualification.py` | 14575 | 0db7fcd48d692e9e90b4c0cfb97d28cbec59299d1f8921d1ec9988e90f9778c8 | 0db7fcd48d692e9e90b4c0cfb97d28cbec59299d1f8921d1ec9988e90f9778c8 | EQUAL |
| `scripts/platformkit/execution/ingame_scoreboard.py` | 19914 | 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6 | 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6 | EQUAL |
| `scripts/platformkit/execution/ingame_scoreboard_amendment.py` | 6972 | 2ccc83054d93c4eb098820c869fd66560f0990cebe318e11a8e8bf0ef0604a6b | 2ccc83054d93c4eb098820c869fd66560f0990cebe318e11a8e8bf0ef0604a6b | EQUAL |
| `scripts/platformkit/execution/ingame_scoreboard_night.py` | 9682 | 8a34c4f4fca9f0c4395f8256d97603797d717d744e65df2e656f897a6645da24 | 8a34c4f4fca9f0c4395f8256d97603797d717d744e65df2e656f897a6645da24 | EQUAL |
| `scripts/platformkit/execution/ingame_scoreboard_rules.py` | 9871 | 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351 | 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351 | EQUAL |
| `scripts/platformkit/execution/paper_night.py` | 16437 | 97399e8e3a8f41ef06053a9cc30907e1225be9597b932eb298c3c633b71e7576 | 97399e8e3a8f41ef06053a9cc30907e1225be9597b932eb298c3c633b71e7576 | EQUAL |
| `scripts/platformkit/execution/paper_night_budget.json` | 1942 | 1a6aaf42b3f2d8014df30e246c59e2481aadf3de98239acae2a233e92178dac4 | 1a6aaf42b3f2d8014df30e246c59e2481aadf3de98239acae2a233e92178dac4 | EQUAL |
| `scripts/platformkit/execution/paper_night_deadline.py` | 14592 | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | EQUAL |
| `scripts/platformkit/execution/paper_night_lock.py` | 1069 | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | EQUAL |
| `scripts/platformkit/execution/paper_night_scratch.py` | 3432 | 8364798a87d109f0cc672acacb2045a0356c9ca12eb0642a1925aa7efb63b43f | 8364798a87d109f0cc672acacb2045a0356c9ca12eb0642a1925aa7efb63b43f | EQUAL |
| `scripts/platformkit/execution/paper_night_steps.py` | 15594 | 2b9bf8371a7e393546b1cb6596129d9866a890571cb4e7af8655e51d01d5b605 | 2b9bf8371a7e393546b1cb6596129d9866a890571cb4e7af8655e51d01d5b605 | EQUAL |
| `scripts/platformkit/execution/venue_time.py` | 1972 | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 | EQUAL |
| `scripts/platformkit/ingame/forward_capture_profile.json` | 151 | 72f798f22269d6a3a74a25313d5743ee57e00732920b1d546b20d1272f046c46 | 72f798f22269d6a3a74a25313d5743ee57e00732920b1d546b20d1272f046c46 | EQUAL |
| `docs/evidence/forward/families_maker_forward.json` | 4225 | c9dc31ea2bc65ff5f622b8c02dfc35e38e5841c2874649f13c9d30f707ed03ee | c9dc31ea2bc65ff5f622b8c02dfc35e38e5841c2874649f13c9d30f707ed03ee | EQUAL |
| `tests/platformkit/execution/fixtures/s389_native_books.jsonl` | 5597 | 50754ee5c19e9b532e30b3b84e7670678e0db1ae1814e6da77e324ad0755e649 | 50754ee5c19e9b532e30b3b84e7670678e0db1ae1814e6da77e324ad0755e649 | EQUAL |
| `tests/platformkit/execution/fixtures/s389_native_state.jsonl` | 789 | ff69da1451d72176458f0aa507bdc9e4d90e2a0c4d05e2c1bbe6955773f3fcf0 | ff69da1451d72176458f0aa507bdc9e4d90e2a0c4d05e2c1bbe6955773f3fcf0 | EQUAL |
| `docs/evidence/forward/schedules/2026-09-26_maker_forward_full_selection.json` | 1737 | d2d11baffcdaf8fdc1facad301bc4afa99b8cec18f4910219fcfe11f304afe7d | d2d11baffcdaf8fdc1facad301bc4afa99b8cec18f4910219fcfe11f304afe7d | EQUAL |

REFUSALS/PROFILE/PROFILE_FIELDS/IDENTITY_FIELDS/ALLOWED_SCHEDULE_FIELDS/DECLARATION_FIELDS retain exact source segments. All unchanged refusal paths are covered by the strict three-edit daily source comparison. Construct schedule, archive and artifact paths are generated beneath pytest temporary roots; the daily artifacts record the resolved paths, hash-time byte counts, and digests. Fixture source is retained in the new tests; no real archive bytes were acquired. The fresh-child first test consumes the landed book fixture verbatim end to end.
New retained JSON/JSONL fixture or seal paths: none. `.gitattributes` patterns added: none. Runtime temporary JSON files are outside versioned evidence and reconstructed by the tests.

## Amendment 7: replacement real-window protocol (orchestrator only, NOT RUN)

The original live-file rename recipe is superseded. Copy the relevant archive prefixes into TWO independent temporary roots, with no junctions or symlinks. Keep the complete control copy; omit only the COPIED `state/soccer/2026-09-26.jsonl` in the treatment copy. Never rename or write through the shared capture view. Run both baseline and candidate from isolated package copies so default ledger writes also stay temporary.
Pin the six-row full selection from the baseline commit and append exactly this prospective CONSTRUCT row to both full schedules:

```json
{"family":"maker_forward","game_id":"S485-CONSTRUCT-26SEP26FULMAN","game_key":"401878777","scheduled_start":"2026-09-26T14:00:00Z","selected_at":"2026-09-25T12:00:00Z","sport":"soccer","ticker":"S485-CONSTRUCT-26SEP26FULMAN-FUL"}
```

The served schedules are identically the pinned six MLB rows; the full schedules are those six plus the row above. Use date `2026-09-26`, cutoff `2026-09-28T00:00:00Z`, global cap `100`, max order quantity `1`, and the pinned profile's reservation lifetime `5`. Use separate nonces `s485-real-control` and `s485-real-missing`, and independent empty supervisor directories. SHA-seal every copied prefix and both schedule files BEFORE execution; retain copies until verification. This protocol fixes the complete row and constants; the prospective row is not claimed to be a real venue identity.
Assertions: pinned baseline treatment has state_shard_missing/global refusal; candidate treatment has refused=0/counter=1; candidate control has counter=0; all six keyed MLB summaries compare equal between copied candidate roots. Failure of equality is reported, never discarded. Per the binding amendment, soccer 401878777 has final-state rows and no matching FUL/MAN books; this is mixed real/construct evidence for the missing-shard branch, not a healthy soccer degradation claim. All five D+1 state shards are reported absent in the amendment; this protocol cannot validate populated D+1 behavior. This lane did not remeasure those archive statements.

## FIX r1

Binding finding: Amendment 2 adds the two failing input tests to scope and requires preserved rewrite refusal with the changed path named. Branch (c) applies: stale mocks, not removed production detection.

Before any edits, `python -m pytest tests/platformkit/ops/test_forward_qualification_inputs.py -q -p no:cacheprovider` produced `2 failed, 46 passed`. Failing output excerpts:

- Projection, test file line 94: `E       assert (3 == 0)`.
- Rewrite, test file line 141: `E       AssertionError: assert (3 == 3 and [] ==` and `Right contains one more item: ...2026-09-21.jsonl`.

Root cause: `scripts/platformkit/ops/forward_qualification_daily.py:28` binds `load_native_streamed` as `load_native`; line 130 passes `scratch_dir=snapshots`. `scripts/platformkit/execution/forward_capture_stream.py:176-179` requires that keyword. The mocks at input test lines 88 and 132 rejected it before either body executed. The daily exception handler at lines 263-265 counted TypeError and emitted qualification_failed, so the rewrite never occurred. The post-run original-prefix check remains at daily lines 260-262 and inputs `_prefix`; it was not lost.

Exact old and new mock lines (same test file):

```python
# Projection signature, old / new:
def spy(books, states, trades, supervisor, schedule, as_of=None):
def spy(books, states, trades, supervisor, schedule, as_of=None, *, scratch_dir):
# Projection forwarding call, old / new:
return original(books, states, trades, supervisor, schedule, as_of=as_of)
return original(books, states, trades, supervisor, schedule, as_of=as_of, scratch_dir=scratch_dir)
# Rewrite signature, old / new:
def rewrite(books, states, trades, supervisor, schedule, as_of=None):
def rewrite(books, states, trades, supervisor, schedule, as_of=None, *, scratch_dir):
```

After: the same full input test file reports `48 passed`. All eight requested files now pass: 21 + 22 + 2 + 4 + 22 + 31 + 40 + 48 = 190 tests. The two new streamed-loader cases are additional regression coverage, outside the original acceptance-case denominator. No assertion was weakened, skipped, or deleted. The rewrite still requires exit 3, input_changed_during_run, exactly the live shard path, and snapshot cleanup; the projection still requires exit 0, a populated observation, and only allowed fields.

Owned module edit: `forward_qualification_inputs.py` documents the required post-stream check of original live paths rather than snapshot copies. Executable production behavior stays unchanged because branch (c) found the guard intact. No artificial runtime fix was introduced for a mock-interface failure.

Added regression `test_streamed_loader_checks_original_prefix_after_snapshot` in the owned cross-sport companion: paired unchanged/rewrite constructs invoke the real streamed loader with its actual scratch directory, assert snapshot-only reader inputs and OrderedStream evidence, then require exit 0 versus exit 3 with the original path named. Both require snapshot cleanup. This supplements the original synthetic-evidence rewrite test. The pinned source-contract test permits exactly the three mock-line replacements and the module contract clarification; every other frozen source assertion remains enforced.

New retained JSON/JSONL fixtures or seals: none. New `.gitattributes` patterns: none. Baseline remains the full pinned `2132fcf64c7039c4ea51097b7de96b85aa790bbe`; no test or memo check resolves a moving ref.

## FIX r2

Scope: the r2 verdict and AMENDMENT 3 explicitly prohibit production edits. This round adds one owned cross-sport pinning test and corrects this memo; the existing S485 production candidate remains intact.

- (a), Opus 1: construct reproduction placed 240 NBA-labelled rows in MLB's D+1 shard with NBA D and D+1 both absent. Exact output: `nba_D_exists=False`, `nba_D1_exists=False`, `mlb_D1_nba_rows=240 verdict=PASS qualified_decisions=720`, followed by `AssertionError: S496 guard absent: expected FAIL, actual PASS`. The deliberate FAIL expectation exposed the deferred defect. `test_s496_current_cross_shard_pass_without_own_state_is_pinned` records the required current PASS and 720 decisions, verifies both missing archive entries and counter 1. The adjudication (i) disclosure above and NOT VERIFIED name S496; no guard repair is claimed.
- (b), Opus 2: before correction the memo audit printed `b_summary_current: FAIL`; line 3 still claimed two candidate failures. It now states AMENDMENT 2 branch (c) and the corrected input file's 48 passed; the unmodified assertions remain covered by the pinned source contract.
- (c), Opus 3: before correction the audit printed `c_pinned_preflight_recorded: FAIL`. The prior preflight paragraph lacked pinned-command output. The exact pinned-base command and output are recorded below.
- (d), Opus 4: before correction the audit printed `d_run_level_disclosure: FAIL`; the required run-level non-isolation sentence is now in the adjudication paragraph.
- (e), Opus 9: `tests/platformkit/ops/test_forward_capture_stream_integration.py::test_c21_real_streamed_daily_hard_kill` fails identically on the pinned base per the binding verifier. This pre-existing issue belongs to register row S497, outside S485; it was neither changed nor rerun in this lane.
- (f): `.s485_verify/` is excluded from the file list and never staged. No staging or commit was performed.

The added behavior pin is separate from the original n=44 acceptance denominator and the two FIX r1 streamed-loader regressions. All checks use local construct/fixture data. No retained JSON seal or fixture was added; new `.gitattributes` patterns: none.
After correction, the memo audit reports `b_summary_current: PASS`, `c_pinned_preflight_recorded: PASS`, `d_run_level_disclosure: PASS`, `a_S496_disclosed: PASS`, and `e_S497_disclosed: PASS`. The full cross-sport file reports `23 passed in 475.99s (0:07:55)`; the new test intentionally asserts the observed PASS rather than claiming S496 is fixed.
FIX r2 reran all eight files individually with `-q -p no:cacheprovider`: sport isolation 21, cross-sport 23, fresh-child isolation 2, baseline contract 4, baseline cases 22, daily 31, planner inputs 40, qualification inputs 48; total 191 passed. Both documented `--help` commands exited 0; the other owned production modules expose no CLI or self-check. Byte-hash comparisons against the start of r2 confirmed all three production modules unchanged (3/3).

Pinned preflight command (full 12-file candidate, excluding the verdict and `.s485_verify/`):
`python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/paper_night_inputs.py scripts/platformkit/ops/forward_qualification_daily.py scripts/platformkit/ops/forward_qualification_inputs.py tests/platformkit/execution/test_paper_night_inputs.py tests/platformkit/execution/test_paper_night_qualification_isolation.py tests/platformkit/ops/test_forward_qualification_daily.py tests/platformkit/ops/test_forward_qualification_inputs.py tests/platformkit/ops/test_forward_qualification_sport_isolation.py tests/platformkit/ops/test_forward_qualification_cross_sport.py tests/platformkit/ops/test_s485_baseline_cases.py tests/platformkit/ops/test_s485_baseline_contract.py docs/evidence/harness/S485_qualification_sport_isolation_2026-09-28.md --base 2132fcf64c7039c4ea51097b7de96b85aa790bbe --spec docs/evidence/tracking/specs/S485_spec.md`

Exact output (exit 0):
```text
PASS vocab clean over 12 files
PASS crlf no index-side CRLF over 12 file(s); 6 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold 5 literal(s) matched
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 6 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

## NOT VERIFIED

- The orchestrator-only copied real-window protocol, real archive distributions, or production nights.
- Full reservation isolation across sports; the construct demonstrates an expected binding-cap difference.
- Elimination of shared native duplicate keys or malformed-state global effects; both remain observable.
- S496 shard-directory/row-sport validation: zero own NBA state files still allow PASS from NBA-labelled MLB-shard rows, as the new construct pins. Run-level counters and diagnostics remain shared.
- S497's pre-existing hard-kill failure; the identical pinned-base failure is a verifier finding, not a fresh lane measurement.
- Full night execution beyond the injected real qualification step; no network, pod, live captures, or real execution observations.
- Crash injection or new persistence semantics; production persistence code was unchanged.
- Independent verifier acceptance or a created commit. SHA: NOT CREATED (sandbox); files ready for lane_commit
