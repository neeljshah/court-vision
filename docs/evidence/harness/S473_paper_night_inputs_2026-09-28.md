# S473 paper-night input isolation -- 2026-09-28

CONSTRUCT result: 21/21 enumerated cases pass. This is not independent acceptance.
FIX 1b applies AMENDMENT 2(a)-(c). Final verification: 345 passed, zero failures in 22 files. No real night ran.
Metric = cases passing / cases enumerated; bar = 21/21; n = 21 (CONSTRUCT); eye check = n/a (S-row).
The three new test files contain 76 passing tests. Every run was per-file with `-q -p no:cacheprovider`.
All edits are in `C:/Users/neelj/nba-harness-h128`; no candidate commit was created.

## Binding before-condition: executed observations and unavailable checks

The initial build's first source read was `docs/evidence/tracking/specs/S473_spec.md`.
Before coding, the local `cmd /c dir /AL data\cache\ingame_capture_view_v2` probe returned:

```text
The system cannot find the file specified.
```

The live process query was attempted later and returned:

```text
Get-CimInstance : Access denied
FullyQualifiedErrorId : HRESULT 0x80041003,Microsoft.Management.Infrastructure.CimCmdlets.GetCimInstanceCommand
```

The user prohibits reading the real archives in this lane. The complete live before-condition and the real-row stat probe are NOT RUN, not a claimed confirmation from this worktree.
The committed evidence present here was read and reproduced these outputs:

```text
docs/evidence/forward/schedules/2026-09-24_maker_forward_full_selection.json 4 ['mlb']
docs/evidence/forward/schedules/2026-09-25_maker_forward_full_selection.json 6 ['mlb']
docs/evidence/forward/schedules/2026-09-26_maker_forward_full_selection.json 6 ['mlb']
24 qualification status=KILLED reason=ceiling_exceeded errors=1 error_type=JSONDecodeError artifact_bytes=[0]
24 fill_realism status=RAN reason=None errors=0 error_type=None artifact_bytes=[914525, 135]
24 week status=RAN reason=None errors=0 error_type=None artifact_bytes=[6646]
24 scoreboard status=RAN reason=None errors=0 error_type=None artifact_bytes=[3443097]
25 qualification status=REFUSED reason=free_ram_below_floor errors=0 error_type=None artifact_bytes=[0]
25 fill_realism status=REFUSED reason=free_ram_below_floor errors=0 error_type=None artifact_bytes=[0, 0]
25 week status=REFUSED reason=free_ram_below_floor errors=0 error_type=None artifact_bytes=[6646]
25 scoreboard status=REFUSED reason=free_ram_below_floor errors=0 error_type=None artifact_bytes=[0]
```

The committed 2026-09-26 run record has argv `--books-root data/cache/ingame_books_local --state-root data/cache/ingame_state_local_v2 --write-pointer`.
Its 09-24 night record has qualification peak 1638944768 against ceiling 1572864000; the 09-25 record has all four free-memory readings below the unchanged floor.
These are reads of committed evidence, not current-process observations.
The spec's live junction targets, stale v1 newest shard, archive row/byte counts, and live PIDs could not be remeasured here.
The quoted fixture distribution is preserved verbatim: `state finals D {822842: 1}, D+1 {823411: 1, 824707: 1, 824866: 1}`.
The first planner test consumes that shape through `_steps` and the record join; the first fill test consumes corresponding constructed records through the real fill child.
The spec supplies counts and identifiers, not raw JSON rows. All additional JSON fields are explicitly constructed, not represented as copied archive records.

## Implementation and imported contracts

The new planner validates the top-level pair, checks canonical containment, enumerates the window, isolates sports, and records dispatch and qualification inputs.
The budget adds only `input_roots` and changes `producer_args.budget_version` to `3`.
History paths also pass through the containment helper so a history junction cannot raise before the week step is considered.
The fill helper registers the paired flags and retains Decimal nanosecond timestamps. Excluded rows never reach indexed rows, identities, or first/last receipts.
Kill handling preserves the child's status, reason, and pre-existing diagnostics, and labels the declared-path digest as an observation.
Injected-step payloads retain their existing fields and fill status. Only production dispatch observations normalize a failed fill to REFUSED.
All writers introduced here use flush/fsync plus replacement; the landed strict `_atomic` remains the night writer.

The imported landed modules were read before implementation. Exact relied-on signatures:

```python
parse_venue_time(value: object) -> float | None
stamp(value: object) -> Decimal
iso(value: Decimal) -> str
deadline_ns(budget: dict, name: str) -> int | None
poll_step(child, row: dict, ceiling: int, limit_ns: int | None, start_ns: int, sampler, sleeper) -> None
validate_deadline(budget: dict, template: dict) -> None
runner_lock(directory: Path)
_digest(path: Path, root: Path) -> dict
production_override(budget: dict, template: dict, env: dict, gates: tuple) -> bool
scoreboard_row_updates(out: Path, before: int | None, reason: str | None) -> dict
unknown_declared_steps(ceiling_bytes: dict, names: tuple) -> set
validate_declared(budget: dict, template: dict, names: tuple) -> None
scoreboard_step(root: Path, day: str, as_of: str, sports: list, p: dict, raw: dict) -> dict
repo_relative(path: Path, root: Path) -> str
write_report(path: Path, report: dict, *, check_memory: object = None) -> None
run_files(books: list[Path], trades: list[Path], states: list[Path], *, ttl_s: object, window_s: object, now: object = None, telemetry: dict | None = None, guard: MemoryGuard | None = None, schedule: list | None = None) -> dict
```

The last signature is the base signature; the candidate adds `night: Night | None = None`. `_index` adds the same optional argument.
`scoreboard_step` was read as the argv compatibility contract. Its unchanged resolver can throw; the candidate builds the same argv from its checked history and roots instead of calling that resolver.
The landed `stamp` validates through `parse_venue_time` and reconstructs the exact fractional tail; no strict receipt boundary uses a truncated float fraction.

## Case table: temporary base modules versus candidate

Base modules were loaded from `git show 8fbc31112288e24a28501a361a48b6cd1779dbe6:<path>` into temporary directories outside the worktree. Already-held behavior is identified explicitly.

| Case | Observed base result | Candidate construct result |
|---|---|---|
| 1 | Missing pair accepted; any present pair rejected as an unknown budget key. | Missing or altered production pair refuses with zero calls; declared pair accepted. PASS. |
| 2 | Injected legacy accepted, with no input blocks. | Same injected schema; S465 snapshot differs only by the two declared fill flags. PASS. |
| 3 | Junction layout accepted but child paths still name the view. | Child book/state paths name checked live targets; NTFS case-only spelling accepted. PASS. |
| 4 | Single-root plain directories accepted. | Every argv equals base after removing only the new fill flags. PASS. |
| 5 | Stale view target accepted by qualification; fixture fill and scoreboard skip for absent shards. | Three steps refuse input_root_disagrees; week remains eligible; shard observations null. PASS. |
| 6 | Missing pair alone accepted; missing view already archive_absent. | Pair absence named; missing view retains first-match archive_absent. PASS. |
| 7 | Capture/view escape raises ValueError; external declared pair ignored. | All three input escape forms return input_root_outside_repo. PASS. |
| 8 | Escaping sport shard raises ValueError. | Only that sport refuses shard_outside_repo; MLB dispatch remains. PASS. |
| 9 | Full or served schedule escape raises ValueError. | schedule_outside_repo, with week eligible. Escaping history also refuses without raising. PASS. |
| 10 | Nine invalid pair values already exit 2 because the key is unknown. | Nine values fail specific shape validation before spawn. PASS. |
| 11 | One missing soccer book skips both fill and scoreboard for MLB as well. | Four MLB selections dispatched, soccer named book_shard_missing. PASS. |
| 12 | Only-sport missing state/both already makes both steps archive_absent. | Same skip, plus exact per-sport planner reasons. PASS. |
| 13 | Fill always receives D only at all three as-of forms. | Midnight/offset include D+1; preceding microsecond excludes it; absent optional shard is harmless. PASS. |
| 14 | Base accepts pre-window and query-future rows under later wall time; no night keyword. | Inclusive as-of, exclusive D+2, exact nanoseconds, future schema and duplicate isolation; flagless artifact bytes equal base. PASS. |
| 15 | Flagless two-week input raises cross_week_pooling_refused. | Sunday excludes and names Monday rows; real scoreboard reads Monday; Saturday pools Sunday; flagless refusal preserved. PASS. |
| 16 | No dispatch record function or blocks. | REFUSED, KILLED, RAN, absent scoreboard and failed fill observations match contract in both input orders. PASS. |
| 17 | Mixed missing state skips both children globally; no independent qualification-input record. | Healthy sport dispatched; qualification's independent D/D+1 and whole-night missing-state consequence exposed. PASS. |
| 18 | Memory/deadline kills add JSONDecodeError; injected existing diagnostic becomes errors 2 and JSONDecodeError. | Kill preserves errors 0 or the prior counted diagnostic; non-killed empty exit 2 retains parsing refusal. PASS. |
| 19 | Older declared artifact digested, but JSONDecodeError and no resolution label. | Old bytes still observed; reservation remains unclaimed; unknown_child_killed and declared_path labels. PASS. |
| 20 | Mixed MLB/soccer fixture makes both real consumers SKIPPED archive_absent; no input blocks. | Real fill and scoreboard run through main; a fresh strict-JSON process validates blocks and sources. PASS. |
| 21 | Fill failure already leaves scoreboard running, but fill is RAN/child_nonzero_exit with no dispatch metadata. | Night PARTIAL; production fill observation REFUSED beside successful scoreboard dispatch. PASS. |

## Mandatory disclosures and follow-ups

The view remains two hand-made junctions, declared and checked here, never created by production code. Containment assumes no junction is retargeted during a night.
Qualification is unedited: it reads D and D+1 independently of as-of and can refuse the whole night when any sport lacks D state. Named follow-up: qualification per-sport isolation and the same night window; orchestrator assigns its row.
A null scoreboard_dispatch_reason describes dispatch only, not scored coverage; S478 owns coverage.
A killed qualification's reservation and .snapshots tree remain on disk, and its produced artifact remains unknown.
Sunday-night Monday receipts are excluded from fill, counted and named, while the scoreboard reads them.
Before D+2 midnight, window_complete is false; this is partial as-of, not S478's complete population.
The spec estimates about 2.27 times the 09-24 book bytes for fill. NOT PROFILED here; S479 owns that check.
The free-memory floor and all ceilings are untouched; S479 owns their operational assessment.
The single --prereg PREREG_2026-09-24.json pointer is unchanged; S475 owns that follow-up.
No scored comparison, archive performance claim, capture edit, flag change, network call, pod action, or real-night execution occurred.

## FIX 1a (AMENDMENT 1, retained changes)

- test_paper_night.py:199: [archive_absent, not_landed] became [archive_absent, archive_absent].
- ORCHESTRATOR EDIT, same test at :200: names == [fill_realism] became names == []; archive refusal precedes the module probe. Recorded here once; final run is 39 passed.
- test_paper_night_scoreboard_step.py:205: fill skip is None became archive_absent for all three input-consuming steps.
- test_paper_night_scoreboard_step_1c.py:76-78: exact argv comparison permits only --as-of <AS_OF> --night-date <DAY> before --out.
- test_fill_realism_1b.py:101-104: historical S411 byte lengths use git show 249aaffbf67730a374e37b7340f725c053ea7ff3:<path>, not working-copy lengths. Values: fill_realism.py 18642, fill_realism_classify.py 9519, fill_realism_io.py 16327, fill_realism_markout.py 4547 LF bytes.

## FIX 1b

Only AMENDMENT 2(a)-(c) changed in this fix. Verdict findings are paired below with this session's reproductions and final results.

(a) Sol BLOCKING 1, Opus note 2: D=2026-09-24, as_of=2026-09-25T00:00:00Z, receipt=2026-09-26T00:00:00Z reproduced `AssertionError: assert 'future_records' == 'outside_night_window'`. The real child likewise emitted `{'future_records': 1}`.
Night.refusal now checks the exclusive window first, future receipts second, and ISO week last. _index bypasses its preliminary future check only when night mode is present. The legacy path is unchanged.
Regression test_amendment2_outside_window_precedes_future covers both helper and real child. Both now pass; the child emits `{'outside_night_window': 1}` and no first/last receipt.

(b) Sol BLOCKING 2 and Opus CORRECTION 1: the post-landing simulation supplied candidate bytes only for the moving-ref request. Both new cases failed: planner `AssertionError: assert not True` for record_inputs; fill `assert 'night' not in ...parameters`.
Both original loaders now request full SHA 8fbc31112288e24a28501a361a48b6cd1779dbe6 for the four baseline files. test_amendment2_post_landing_baselines intercepts the simulated moving ref without reading it, verifies legacy behavior, and asserts both requests use the immutable SHA. Both cases now pass.
The planner file remains 300 lines. No baseline is resolved from current git state in these tests.

(c) Sol CORRECTION 3 and Opus CORRECTION 2: before the fix, the memo had 323 lines, stale 17256 LF bytes/SHA 5a25d981... for test_paper_night.py, and contradictory unresolved-assertion text. This session reproduced current 17298 LF bytes/SHA 45916530586aa42be27f3807b494fb8bbf6f1e62c26f14e902fffb05e66e7c28.
The required test reran using writable external temporary storage: 39 passed. Superseded result tables and unresolved-assertion statements are removed. The generator includes both AMENDMENT 1 test files, defaults to the immutable base, requires a recorded full candidate-parent SHA, and refuses mutable revision arguments.
The existing generator regression now supplies test results, verifies repeat generation is identical, then changes a constructed source and verifies refreshed identity and byte size while NOT VERIFIED stays last. It never queries live git refs.
The final facts are generated after all source/test/memo edits with --test-results, --base 8fbc31112288e24a28501a361a48b6cd1779dbe6 and --candidate-parent bcb1d214f5b85909f9ed94d2b0eadfa1c22129f1 (observed at session start).

Initial reproduction run: 21 passed, 5 failed (four intended new regression failures and one WinError 32 in the unchanged writer). Final fill-night run: 26 passed, zero failures; no writer change. All tests use constructed inputs and external temporary directories, with PYTHONDONTWRITEBYTECODE=1.
No new committed JSON seal or fixture path was added. New .gitattributes patterns: none. Runtime-only JSON fixtures and result logs remain outside the worktree.

Opus notes 1, 3, 4 are disclosed without implementation changes: scoreboard_not_declared's non-RAN/no-reason fallback is unreachable from the current runner; the existing night.as_of assignment in run_files remains equivalent; global fill/scoreboard step observations also appear on undispatched sports, and whole-night refusals report qualification state_shard_missing. These observations remain spec-consistent.

FIX 1c: Added exactly three helper cases in test_fill_realism_night_order.py; ISO week first makes cases 1/2/3 fail with next_iso_week_excluded; ISO week before future makes case 3 fail with next_iso_week_excluded (all mutations executed in memory, helper restored, no implementation edit). Per-file runs: new file 3 passed; test_fill_realism_night.py 26 passed; zero failures. Contract preflight: 9/9 PASS over 16 owned paths including the new file and memo. Facts regenerated with the new test path added to OWNED in memory.

## FIX 1b per-file verification

Every command is python -m pytest tests/platformkit/execution/<file> -q -p no:cacheprovider, one file per invocation. The complete final list follows.

| File | Passed | Failed |
|---|---:|---:|
| test_fill_realism.py | 34 | 0 |
| test_fill_realism_1b.py | 12 | 0 |
| test_fill_realism_1d.py | 6 | 0 |
| test_fill_realism_fills_out.py | 15 | 0 |
| test_fill_realism_fills_out_1h.py | 4 | 0 |
| test_fill_realism_fills_out_1i.py | 4 | 0 |
| test_fill_realism_fills_out_1k.py | 2 | 0 |
| test_fill_realism_io.py | 17 | 0 |
| test_fill_realism_night.py | 26 | 0 |
| test_paper_night.py | 39 | 0 |
| test_paper_night_deadline.py | 20 | 0 |
| test_paper_night_deadline_1b.py | 9 | 0 |
| test_paper_night_deadline_1c.py | 3 | 0 |
| test_paper_night_inputs.py | 40 | 0 |
| test_paper_night_inputs_e2e.py | 10 | 0 |
| test_paper_night_scoreboard_step.py | 14 | 0 |
| test_paper_night_scoreboard_step_1c.py | 4 | 0 |
| test_paper_night_scoreboard_step_1d.py | 2 | 0 |
| test_paper_night_scoreboard_step_1e.py | 1 | 0 |
| test_paper_night_steps.py | 50 | 0 |
| test_paper_night_steps_1d.py | 25 | 0 |
| test_paper_night_steps_1e.py | 8 | 0 |

Total: 345 passed, zero failures. Construct acceptance remains 21/21; the four added regressions refine cases 14 and the immutable baselines.
CLI --help for paper_night, fill_realism and s473_memo_facts: three exit-0 results. These modules expose no separate self-check flag; helper and memo checks run in the per-file tests.
Contract preflight: 9/9 PASS over the 15 owned paths. Command: python -m scripts.platformkit.tracking.contract_preflight --paths <the 15 owned paths including this memo, excluding the verifier file> --base master --spec docs/evidence/tracking/specs/S473_spec.md.

## ORCHESTRATOR COPY

No real slice is needed by the construct cases. The real-row probe is NOT RUN in this lane and remains an orchestrator action. No archive copy is requested.
Source identities below are observations, not assertions about another row's working-copy byte lengths.

<!-- S473 GENERATED FACTS -->
## Generated facts (LF-normalised A9 rows)
Candidate parent (recorded): `bcb1d214f5b85909f9ed94d2b0eadfa1c22129f1`. Base commit: `8fbc31112288e24a28501a361a48b6cd1779dbe6`.
Candidate identity is the on-disk SHA-256 per file below; no candidate commit exists.
| Full input path | LF bytes | Resolution | Candidate SHA-256 | Base SHA-256 | Comparison |
|---|---:|---|---|---|---|
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\nights\2026-09-24.json | 7213 | source text; LF-normalised | 89010ca0ecc5af12e8d155f18da12e9f89ace1fa5a8a4472e1ac9afb4989c86e | 89010ca0ecc5af12e8d155f18da12e9f89ace1fa5a8a4472e1ac9afb4989c86e | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\nights\2026-09-25.json | 6202 | source text; LF-normalised | fec12c74bd26f04446c186bc38292f8bfe3af0398c28c520074d69ec947f91b6 | fec12c74bd26f04446c186bc38292f8bfe3af0398c28c520074d69ec947f91b6 | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\schedules\2026-09-24_maker_forward_full_selection.json | 1159 | source text; LF-normalised | 1ee2144f9838baf6a9ce4f175a75d604fb6f82c0bba72f82269d1456e367c846 | 1ee2144f9838baf6a9ce4f175a75d604fb6f82c0bba72f82269d1456e367c846 | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\schedules\2026-09-25_maker_forward_full_selection.json | 1737 | source text; LF-normalised | f8b8cfa7d569dc6a13f190d9e31a7635504a0549fc182e5570dc0c4dfa530996 | f8b8cfa7d569dc6a13f190d9e31a7635504a0549fc182e5570dc0c4dfa530996 | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\schedules\2026-09-26_maker_forward_full_selection.json | 1737 | source text; LF-normalised | d2d11baffcdaf8fdc1facad301bc4afa99b8cec18f4910219fcfe11f304afe7d | d2d11baffcdaf8fdc1facad301bc4afa99b8cec18f4910219fcfe11f304afe7d | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\schedules\2026-09-26_run.json | 2401 | source text; LF-normalised | fc25058a8e62009e71143c1ce735d9f8bc09fa75497a666717b2df02f60023aa | fc25058a8e62009e71143c1ce735d9f8bc09fa75497a666717b2df02f60023aa | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\scoreboard\PREREG_2026-09-24.json | 5046 | source text; LF-normalised | 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b | 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\scoreboard\PREREG_2026-09-24_superseded_2026-09-25.json | 4611 | source text; LF-normalised | 421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d | 421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\forward\scoreboard\PREREG_E_2026-09-25.json | 1423 | source text; LF-normalised | a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0 | a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0 | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\tracking\VERIFIER_CONTRACT.md | 12392 | source text; LF-normalised | 63d8d126ea26492a12ecab2e74b48d736d30fc626c1162a338acaae6ddb2c341 | 63d8d126ea26492a12ecab2e74b48d736d30fc626c1162a338acaae6ddb2c341 | EQUAL |
| C:\Users\neelj\nba-harness-h128\docs\evidence\tracking\specs\S473_spec.md | 21163 | source text; LF-normalised | 2dbdeebcabc1f26eadcb4fa1070814f436a7b067326b8dfb629de4a9e9a23f1d | 4bb09a505e9b021b138be232588ee3dfd64638bb5a2c83bbe8790a5ddf807af5 | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\fill_realism.py | 18420 | source text; LF-normalised | 9101eec1e870e0acf5a26dc88153e321764aecde2eda27459718770befc27f8f | bf3c56b76d2289517a5001e956e4dda534ec32094db7775525f57e28da2d5b42 | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\fill_realism_classify.py | 9519 | source text; LF-normalised | bfb4f1b512e810ae345dd91d91e4f31f94ebfeffcdc2a67fe26286d9e079917f | bfb4f1b512e810ae345dd91d91e4f31f94ebfeffcdc2a67fe26286d9e079917f | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\fill_realism_io.py | 16958 | source text; LF-normalised | 759a7ab6f3a1c0fd34e67d744be6261dac2e5e95b2956bffa8b6eca0897d231e | f952dcd2ae5f3ef8cac95d2fbd7d13228a0a2bee6507cb004572c929d10fdf0f | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\fill_realism_markout.py | 4547 | source text; LF-normalised | bd825edbc49b09e89bbb1dc56f8c807b294a1c02a75f5aaf6c61442332fefb0e | bd825edbc49b09e89bbb1dc56f8c807b294a1c02a75f5aaf6c61442332fefb0e | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\fill_realism_night.py | 3121 | source text; LF-normalised | 4fbca76da1451a24c092a884b04b4d81d6371b07c4bfd80c34fa470b52ba5e9e | ABSENT | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\forward_replay_io.py | 8853 | source text; LF-normalised | b1174d776cd44d928ea95a9b132c106d16a2fea8959c12fcbee1431e97adf07a | b1174d776cd44d928ea95a9b132c106d16a2fea8959c12fcbee1431e97adf07a | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\ingame_scoreboard.py | 22010 | source text; LF-normalised | ba37c375ca62aee6b0eeb9b5cc502ec94c7cb6ad08f234e64990758ac2e85544 | ba37c375ca62aee6b0eeb9b5cc502ec94c7cb6ad08f234e64990758ac2e85544 | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\ingame_scoreboard_rules.py | 6769 | source text; LF-normalised | 5a58a2217f19124a68d46e1c67f201d6ce051618f413ca9668cff7367bb36fc7 | 5a58a2217f19124a68d46e1c67f201d6ce051618f413ca9668cff7367bb36fc7 | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\paper_night.py | 15364 | source text; LF-normalised | 72cb090ed3bb8c2c64b85c66408457d52ac54034e4c73b4223620e12ed6707ec | 52af33074768a030ddac06e921b6a459e3a85cb4cf82942d4a37c4ca571ed32a | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\paper_night_budget.json | 1505 | source text; LF-normalised | 83d2eb3defef596eaf16bbb9caa5befedcf74b8ab543dafc97e330bf94e3d03b | f6f287b5a8889152051a85de70f2ab6b386917c360448c474859bc04a05b0bc3 | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\paper_night_deadline.py | 14592 | source text; LF-normalised | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\paper_night_inputs.py | 9291 | source text; LF-normalised | e7c5913e9fb956ea045d49981bf6e36067991d4546e058d3e78381e63f01e259 | ABSENT | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\paper_night_lock.py | 1069 | source text; LF-normalised | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\paper_night_peak.py | 2378 | source text; LF-normalised | 54aa53505a688f7dac8baf45a4aed003c8919c245d908aaff1341f80e9cf77de | 54aa53505a688f7dac8baf45a4aed003c8919c245d908aaff1341f80e9cf77de | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\paper_night_steps.py | 14942 | source text; LF-normalised | 3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 | 3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\execution\venue_time.py | 1972 | source text; LF-normalised | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\ops\forward_qualification_daily.py | 15053 | source text; LF-normalised | 64a0df634b065b197c4205215931c7997b011b56e353a58022aa4f4d5dfc5bfb | 64a0df634b065b197c4205215931c7997b011b56e353a58022aa4f4d5dfc5bfb | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\ops\forward_qualification_inputs.py | 12785 | source text; LF-normalised | 086fd442b657ef9039ef4b6984a9f2aaf96a3330e30095b8049bd2a481fbe775 | 086fd442b657ef9039ef4b6984a9f2aaf96a3330e30095b8049bd2a481fbe775 | EQUAL |
| C:\Users\neelj\nba-harness-h128\scripts\platformkit\ops\probes\s473_memo_facts.py | 6562 | source text; LF-normalised | 01589d6aa227ba4869df598bb72c0013702d555f474058a1ffd1181cea01bfee | ABSENT | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\fixtures\s465_case1_legacy_snapshot.json | 4274 | source text; LF-normalised | 46ecb1acd3217028e74de5fc48c984e276d115b57c0382c8d27edcefb98b52c3 | 46ecb1acd3217028e74de5fc48c984e276d115b57c0382c8d27edcefb98b52c3 | EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\fixtures\s470_case1_legacy_snapshot.json | 3312 | source text; LF-normalised | 5e3b709129048a9279bddbbb4184025fd282db6e823c7f39298739c585ff8084 | 5e3b709129048a9279bddbbb4184025fd282db6e823c7f39298739c585ff8084 | EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\fixtures\s471_case2_s460_snapshot.json | 4608 | source text; LF-normalised | a7d08a21d541cc6182e6dc572f4f0b0ec5601627f02eb76021216ae4e8ac4031 | a7d08a21d541cc6182e6dc572f4f0b0ec5601627f02eb76021216ae4e8ac4031 | EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\test_fill_realism_1b.py | 7161 | source text; LF-normalised | bd1f6dc9316a70a13f0f3b7fcb5a508bdd3596b42cc2073d2fdb30af67428397 | 289094c7b5b3f16c0b248c6cd114322c664a37ba10ff0d27fb2d7880749865f5 | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\test_fill_realism_night.py | 14843 | source text; LF-normalised | 7ccf7014916e48d8cc98a3f523bd9ee086a1381a4867ddd0598385a8750d2b8a | ABSENT | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\test_fill_realism_night_order.py | 716 | source text; LF-normalised | 49493baeaa4c42efbf300ff3d0aa7d2de8d970f8dfbe9095391aaadabe10f770 | ABSENT | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\test_paper_night.py | 17298 | source text; LF-normalised | 45916530586aa42be27f3807b494fb8bbf6f1e62c26f14e902fffb05e66e7c28 | 43b1f8bf59ad916e16ab43717d02bb30baa5492db65f34613cdb26dc718afaac | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\test_paper_night_inputs.py | 15677 | source text; LF-normalised | bcce044719ac22d2fa6540326eccacc99c21d5b7883877320d541d456e82c5f4 | ABSENT | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\test_paper_night_inputs_e2e.py | 14481 | source text; LF-normalised | b94a1404fffb95d86a84262056fac535e65f7990afc30fd556434c5047f15bde | ABSENT | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\test_paper_night_scoreboard_step.py | 16225 | source text; LF-normalised | 4e5992b908d1fe5471323d6c7fe7931e1b3157d3df7c21ed0dd96a7b4f7546a9 | 0bf3dfc8134ab0f82510b3eab92adc5487582a9e1173361cdc9a7f4e09e5dd9c | NOT EQUAL |
| C:\Users\neelj\nba-harness-h128\tests\platformkit\execution\test_paper_night_scoreboard_step_1c.py | 4951 | source text; LF-normalised | fe9672c5b0a30f82811ca575845a0c7722936b4e508d147c3b5014f126aad988 | 53a68b19c78beced717e122b8d63b39fc723972b9d34ed9265c2a77f70cc3f31 | NOT EQUAL |

Per-file results: `{"test_fill_realism.py": {"failed": 0, "passed": 34}, "test_fill_realism_1b.py": {"failed": 0, "passed": 12}, "test_fill_realism_1d.py": {"failed": 0, "passed": 6}, "test_fill_realism_fills_out.py": {"failed": 0, "passed": 15}, "test_fill_realism_fills_out_1h.py": {"failed": 0, "passed": 4}, "test_fill_realism_fills_out_1i.py": {"failed": 0, "passed": 4}, "test_fill_realism_fills_out_1k.py": {"failed": 0, "passed": 2}, "test_fill_realism_io.py": {"failed": 0, "passed": 17}, "test_fill_realism_night.py": {"failed": 0, "passed": 26}, "test_fill_realism_night_order.py": {"failed": 0, "passed": 3}, "test_paper_night.py": {"failed": 0, "passed": 39}, "test_paper_night_deadline.py": {"failed": 0, "passed": 20}, "test_paper_night_deadline_1b.py": {"failed": 0, "passed": 9}, "test_paper_night_deadline_1c.py": {"failed": 0, "passed": 3}, "test_paper_night_inputs.py": {"failed": 0, "passed": 40}, "test_paper_night_inputs_e2e.py": {"failed": 0, "passed": 10}, "test_paper_night_scoreboard_step.py": {"failed": 0, "passed": 14}, "test_paper_night_scoreboard_step_1c.py": {"failed": 0, "passed": 4}, "test_paper_night_scoreboard_step_1d.py": {"failed": 0, "passed": 2}, "test_paper_night_scoreboard_step_1e.py": {"failed": 0, "passed": 1}, "test_paper_night_steps.py": {"failed": 0, "passed": 50}, "test_paper_night_steps_1d.py": {"failed": 0, "passed": 25}, "test_paper_night_steps_1e.py": {"failed": 0, "passed": 8}}`.
Orchestrator probe: `{"reason": "orchestrator_main_tree_only", "status": "NOT RUN"}`.

## NOT VERIFIED

- The full live before-condition, real-row probe, actual archives, real nights or ledger, network, and pod execution.
- Qualification's actual reservation-selection and .snapshots workflow; tests construct the reservation and old declared artifact.
- A naturally occurring sampler failure before a kill; tests supply an already-counted diagnostic and exercise the real kill path.
- Resource profiling, full-night completeness, scored coverage, or S475/S478/S479 follow-ups; non-Windows symlink branches.
- Independent acceptance of FIX 1c, deployment, or a candidate git commit.
