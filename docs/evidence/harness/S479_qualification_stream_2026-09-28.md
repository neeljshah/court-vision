# S479 qualification stream - candidate, 2026-09-28

Verdict: ACCEPT against the 26/26 construct rule, including AMENDMENTS 1 and 2.
C17 uses capacity_exhausted, the unchanged landed global-cap counter.

Machine: local Windows worktree C:/Users/neelj/nba-harness-h132; CPU constructs
and committed fixtures only. No archive, network, capture launch, or pod run.
Base: immutable dispatch checkout; generated full identities below. Spec cites
860b9a157 as its older oracle reference; comparisons use the landed code in this
checkout, with the sole bridge change at line 102 (list to generator).
## BINDING BEFORE-CONDITION

Ran the committed night-receipt reader this session. Output columns are date,
step, status, reason, peak bytes, starting available bytes, and wall seconds:

```text
24 qualification KILLED ceiling_exceeded 1638944768 2942418944 23.922
24 fill_realism RAN None 223252480 2888220672 273
24 week RAN None 21680128 3270479872 0.516
24 scoreboard RAN None 144351232 3237814272 13.672
25 qualification REFUSED free_ram_below_floor None 670683136 0
25 fill_realism REFUSED free_ram_below_floor None 670334976 0
25 week REFUSED free_ram_below_floor None 670212096 0
25 scoreboard REFUSED free_ram_below_floor None 670019584 0
docs/evidence/forward/qualification/2026-09-24.json.snapshots ABSENT
vault/S362/position_events.jsonl ABSENT
```

Ran the orchestrator scratchpad s479_stack_probe.py read-only. Its exact summary:

```text
SUM rss 531243008 SUM peak_wset 1077710848 available 2735558656 total 16232906752 at 2026-09-28T17:30:23
```

Nine capture-stack processes matched. Historical stack values are not current
measurements. The historical qualification artifact's reservation is 0 bytes.
The 2026-09-25 operational floor in the recorded budget was 2621440000 bytes.
The archive probes s479_probe.py and s479_slice_probe.py hard-code the main tree.
Read their code, but did not execute them: the dispatch prohibits archive reads.
Consequently before-condition items ii and iv are NOT RUN in this lane; the
full-day row totals, expansion factor, and production ledger size are not
remeasured here. The premise is confirmed by the committed kill receipt and
the landed readers, not by copying the spec's archive measurements.
## Implementation and imported signatures

Read each relied-on landed module before coding. Exact callable signatures:

```python
stamp(value: object) -> Decimal
iso(value: Decimal) -> str
_native_input(paths: Iterable[Path], source: str, counts: Counter) -> Iterator[dict]
chronological(events: Iterable[dict], as_of: object, counts: Counter) -> Iterator[dict]
_common(row: dict) -> None
_book(row: dict) -> None
_text(row: dict, key: str) -> str
_links(book_rows: list, state_rows: list, schedule: list, counts: Counter) -> dict
_tape(rows: list, selected: dict, failures: dict, counts: Counter) -> list
load_native(books_paths: list[Path], state_paths: list[Path], trade_paths: list[Path], supervisor_journals: list[Path], schedule: list[dict], *, as_of: object = None) -> NativeEvidence
_sample_peak(pid: int) -> int
_count(value: object) -> int
_atomic(path: Path, payload: dict) -> None
main(argv: list | None = None) -> int
```

The last main signature is the daily producer. NativeEvidence's fields are
events, counts, failures, as_of. The probe changes only its own temporary
loader/ledger seams, and redirects the landed qualification weekly scratch to
OS temp in the probe harness. Production TARGET_LEDGER remains
vault/S362/position_events.jsonl; every evidence run uses a scratch ledger.

The oracle is landed load_native/native_rows/chronological in the same checkout,
altered only by bridge line 102. index_kalshi_events iterates once in input order
(game_market_link.py:69). Tape's unselected count remains bridge line 157.
Native per-row rules are MIRRORED, a third copy after regime_census.py and
qualification_cause_stream.py, and proven only by E1 differential comparisons.
They use the landed reader exclusively; as-of precedes native schema and keys.
Receipt seconds and nanoseconds are separate SQLite INTEGERs. Native JSON keys
are frozen after native duplicate flags, before adapters; stable ordinals and
landed output positions are stored. Pickle protocol 4 preserves Decimal spelling
and tuples. Numeric native timestamp keys canonicalize equal Decimal values.
One global replay stream retains cross-ticker cap ordering.

OrderedStream adds 11 lines and removes none from forward_replay_io.py.
forward_replay.py remains 300 lines, unchanged. The daily remains 300 lines.
paper_night.py receives exactly two added lines and remains 291 lines; the
concurrent S474 steps and budget are untouched. The two daily doubles alone
gain scratch_dir=None. Every spool closes before removal, including exceptions.
Only paper-night-supervised kills are swept. Normal night rows gain no keys.
SQLite uses temp_store=FILE and cache_size=-2048 with indexed ordered scans.
## Construct cases

| Case | Result and executable coverage |
|---|---|
| C1 | Empty schedule/lists, exact empty counters and failures. |
| C2 | Keyed/keyless absent state, exact LINKAGE_INVALID counts and failures. |
| C3 | All missing paths and decode error in third 8 KiB chunk. |
| C4 | Null, boolean, fractional JSON epoch, ten-digit ISO fraction in all roles. |
| C5 | JSON syntax, array, non-finite prices, unknown kinds; state always becomes state in oracle. |
| C6 | Exact cutoff ISO/int equality and adjacent nanosecond blocks. |
| C7 | Decimal/string representation collisions in both orders, books and states. |
| C8 | Reversed paths and reversed file ordering preserve landed stable ordinals. |
| C9 | All four roles at one receipt. |
| C10 | Native book, trade, and terminal ties. |
| C11 | Identical and conflicting duplicates, snapshot/bulk, zero-valued counters. |
| C12 | Cross-receipt duplicate outputs via a shared tape stub; native duplicates are otherwise suppressed before replay. |
| C13 | Shared books/trades shard, 20 unselected tickers, duplicate/future counts, no discarded trades spooled. |
| C14 | Open/closed tape, gap bounds, invalid time/price/ticker, Decimal spelling; numeric/string ticker collisions in both orders; selected lone-surrogate ticker. |
| C15 | Keyed/keyless, conflicts, unlinked states, duplicate schedule, first-seen series. |
| C16 | Valid/invalid journals and interleaved next-day shards. |
| C17 | PASS under AMENDMENT 1: capacity_exhausted >= 1 for each loader in all four path permutations, with byte-equal artifacts and ledgers. |
| C18 | Fresh landed/streamed daily subprocesses, same paths, empty ledgers, strict parsed and byte equality; parent RAN and digest. |
| C19 | S389 and S421 committed fixture pairs, copied verbatim through C18. |
| C20 | Third decision exception gives equal failure artifacts; linkage exception and spool cleanup. |
| C21 | Real streamed child paused after load, actual SQLite observed, parent deadline kill sweeps tree; survivor/artifact/junction constructs. |
| C22 | Explicit protocol, incidental attributes ignored, one-shot, mismatch, exact exception, exhaustion/early close, iter refusal. |
| C23 | Construct unselected-book volume flatness and landed power check; results below. |
| C24 | Four two-point growth slopes, descriptive only; results below. |
| C25 | Sampler doubles: allocate/free, falling available RAM, exact process match, summed swings. |
| C26 | Committed night derive refusal, added construct completion, verbatim slice and LF inventory. |

C17 asserts capacity_exhausted >= 1 on the oracle and candidate under
AMENDMENT 1. The obsolete reservation_refusals == 0 assertion is removed;
no landed counter was renamed or added.
## Scope and disclosures

Flatness is asserted ONLY for unselected-ticker book volume. Linkage-time state
rows, the largest selected ticker's tape group, oversized one-receipt blocks,
scheduled-game count and replay retention grow. C24 measures construct slopes;
M2 phase marks must be measured by the orchestrator, never replaced by estimates.
forward_replay.py --native and qualification_cause_report still materialize.
Budget values are NOT PROFILED until phase C, so no budget values were edited.
Calibration language only; these are engineering constructs, not model scoring.
No new JSON seals or fixture paths were added. Required new .gitattributes
patterns: none. Existing S389/S421 fixture bytes were reused verbatim.
## ORCHESTRATOR COPY

NOT RUN. The owner reports the protected full-day backup already exists at
data/cache/s479_m2_input/ in the MAIN tree. Preserve it before any daily rerun.
Run from the main tree only after review, with a scratch destination outside any
worktree (the following is an orchestrator command, not a lane action):

```powershell
python -m scripts.platformkit.ops.probes.s479_ram_probe slice --src data/cache/s479_m2_input --out $env:TEMP/s479-m1-input --lo 2026-09-24T18:30:00Z --hi 2026-09-24T18:50:00Z
```

M1 uses the spec's full-selection schedule and explicit 2026-09-28T15:07:55Z
cutoff. M2 uses the full preserved tree with captures live and completion proof.
M3 profiles each exact night step; derive is the sole phase-C value calculator.
M4 is optional pod compute; no full-day equivalence claim exists without it.

## Final construct measurements and verification

Prior construct acceptance: 26/26 under AMENDMENT 1. The measurements below
are retained from the original candidate; FIX 1b records the correction rerun.
C23 final rerun: streamed peaks 50012160 / 49848320 bytes at 1000 / 20000 rows,
delta -163840 bytes (process noise), below 16777216 bytes. Landed peaks
51830784 / 150794240 bytes, delta 98963456 bytes: the recorded power check.
All four ordered SELECT plans use native/output indexes or the rowid scan;
none reports TEMP B-TREE. These are construct subprocess measurements only.

| C24 dimension | Input sizes | Peak bytes | Exact two-point slope, bytes/item |
|---|---|---|---|
| Scheduled state rows | 100 / 1000 | 47742976 / 50114560 | 2371584 / 900 |
| Selected ticker trades | 100 / 1000 | 47783936 / 50454528 | 2670592 / 900 |
| Scheduled games | 1 / 20 | 47513600 / 47869952 | 356352 / 19 |
| One receipt block | 101 / 5000 | 49684480 / 83685376 | 34000896 / 4899 |

Per-file commands: python -m pytest <path> -q -p no:cacheprovider.
Integration measurement output adds -s; every invocation names one file.
All test paths below are under tests/platformkit/; FIX 1b results: 656 passes, 24 files.

| Test file | Passed |
|---|---:|
| execution/test_forward_capture_stream.py | 35 |
| execution/test_forward_capture_stream_integration.py | 8 |
| execution/test_paper_night_scratch.py | 19 |
| ops/test_s479_ram_probe.py | 42 |
| execution/test_forward_capture_bridge.py | 60 |
| execution/test_forward_capture_bridge_keyed.py | 34 |
| execution/test_forward_replay.py | 49 |
| execution/test_forward_replay_qualification.py | 79 |
| ops/test_forward_qualification_daily.py | 31 |
| ops/test_qualification_cause_stream.py | 25 |
| ops/test_qualification_cause_landed.py | 32 |
| ops/test_qualification_cause_report.py | 61 |
| ops/test_qualification_cause_runtime.py | 6 |
| execution/test_paper_night.py | 39 |
| execution/test_paper_night_deadline.py | 20 |
| execution/test_paper_night_deadline_1b.py | 9 |
| execution/test_paper_night_deadline_1c.py | 3 |
| execution/test_paper_night_scoreboard_step.py | 14 |
| execution/test_paper_night_scoreboard_step_1c.py | 4 |
| execution/test_paper_night_scoreboard_step_1d.py | 2 |
| execution/test_paper_night_scoreboard_step_1e.py | 1 |
| execution/test_paper_night_steps.py | 50 |
| execution/test_paper_night_steps_1d.py | 25 |
| execution/test_paper_night_steps_1e.py | 8 |

Eight CLI --help checks pass: daily, paper_night, probe and five subcommands.
Contract preflight over all 14 owned files: nine PASS checks, zero FAIL.
B1-B11/Q1-Q9: construct-only denominator; no schema removals, changed bars,
new deployment, model score, or independence claim. Q1/Q2/Q4/Q5 scoring
obligations are not invoked. A12: every owned Python file is <=300 lines;
no LOC allowlist edits required. NOT VERIFIED remains the final section.

## A9 inventory and immutable code identity

Generated by s479_ram_probe inventory from the final candidate. base_sha pins
CURRENT master at FIX 1c; candidate_sha pins the fast-forwarded checkout parent,
not a landing commit. Per-file hashes identify uncommitted contents. No test or memo
identity check resolves a moving branch. The explicitly requested preflight
command alone uses --base master. Paths resolve against the full worktree root
C:/Users/neelj/nba-harness-h132; resolution is n/a for JSON, JSONL and Python.
Bytes/lines below are LF-normalized. NOT EQUAL means a new or owned changed file.
The game_market_link.py context row now records the CURRENT master contents:
S481 changed that file upstream before this worktree was fast-forwarded. It is
EQUAL to the pinned master below; FIX 1c does not edit that file.

```json
{"base_sha": "5e93012ee49485e7d2a21c6abd6e74a4094e8181", "candidate_sha": "8a434bdb5c4ec6dfcd25079ed877bbf4aec5d9d3"}
{"path": "scripts/platformkit/execution/forward_capture_stream.py", "sha256": "12b2fbf9d0a7938a9a3879b392d02d8b10111164e33b690c63b08519b104cb4f", "bytes": 8558, "lines": 195, "comparison": "NOT EQUAL"}
{"path": "scripts/platformkit/execution/forward_capture_stream_sql.py", "sha256": "37489ee296cc50fa4ac28b6b178565d9c8028116bfd8325110b55d2ab6731663", "bytes": 6303, "lines": 131, "comparison": "NOT EQUAL"}
{"path": "scripts/platformkit/execution/paper_night_scratch.py", "sha256": "8364798a87d109f0cc672acacb2045a0356c9ca12eb0642a1925aa7efb63b43f", "bytes": 3432, "lines": 80, "comparison": "NOT EQUAL"}
{"path": "scripts/platformkit/ops/probes/s479_ram_probe.py", "sha256": "a7aa3cb01a09a231756123572d3e333506a306218b8ccec5a5ac162f631ea295", "bytes": 15467, "lines": 300, "comparison": "NOT EQUAL"}
{"path": "scripts/platformkit/execution/forward_replay_io.py", "sha256": "b2ec0afa9d8bcd0ed2d25a3d7a9e796dbaf8f079cd396551da7d8675281c5962", "bytes": 9277, "lines": 206, "comparison": "NOT EQUAL"}
{"path": "scripts/platformkit/execution/forward_capture_bridge.py", "sha256": "549eb23f2c33e764ab1e72be9efecf490cc6790db0c97a5f2af812617355aaa5", "bytes": 14359, "lines": 298, "comparison": "NOT EQUAL"}
{"path": "scripts/platformkit/ops/forward_qualification_daily.py", "sha256": "ada413a1665516303cc2d3de35088d7888a05dd2238c084c40d6e0431797a15e", "bytes": 15212, "lines": 300, "comparison": "NOT EQUAL"}
{"path": "scripts/platformkit/execution/paper_night.py", "sha256": "4416bdefb76c8253eef887c34d609a68c6e9289b9d0125010ca5a50f8d69583c", "bytes": 15507, "lines": 291, "comparison": "NOT EQUAL"}
{"path": "tests/platformkit/ops/test_forward_qualification_daily.py", "sha256": "c4dea30d4e3457ee860a79212ad360df9cecde1b488e848d95dd95fb5080ea85", "bytes": 19364, "lines": 300, "comparison": "NOT EQUAL"}
{"path": "tests/platformkit/execution/test_forward_capture_stream.py", "sha256": "c9fab5d05502083178bb65b0497e0936927aa508c38f22d156eb88926f035e19", "bytes": 16404, "lines": 300, "comparison": "NOT EQUAL"}
{"path": "tests/platformkit/execution/test_forward_capture_stream_integration.py", "sha256": "e5cb01e4bf90e967eac34755614bd172e7ce6215f37f7bafac26beb568fcc50f", "bytes": 15044, "lines": 275, "comparison": "NOT EQUAL"}
{"path": "tests/platformkit/execution/test_paper_night_scratch.py", "sha256": "7063a021782c9b1eb1ae99be75d976ca14c056f5622859b088296b0ea2081517", "bytes": 6496, "lines": 163, "comparison": "NOT EQUAL"}
{"path": "tests/platformkit/ops/test_s479_ram_probe.py", "sha256": "77e03b2fe6dfc7ea7390c38cf2398e5650004fcc8da730b80c34625f4c71bc25", "bytes": 15384, "lines": 273, "comparison": "NOT EQUAL"}
{"path": "scripts/platformkit/execution/forward_replay.py", "sha256": "d88f198aa684b8a96362a3edd6509e30d64f808317989cafdc09e71c3a7ede21", "bytes": 15821, "lines": 300, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/forward_replay_policy.py", "sha256": "e81fed58cbd2772c94d0771e574af3cc8b9268cdc1e4e3d1a05bd5bbc122c71e", "bytes": 11940, "lines": 214, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/forward_replay_qualification.py", "sha256": "0db7fcd48d692e9e90b4c0cfb97d28cbec59299d1f8921d1ec9988e90f9778c8", "bytes": 14575, "lines": 262, "comparison": "EQUAL"}
{"path": "scripts/platformkit/ops/forward_qualification_inputs.py", "sha256": "086fd442b657ef9039ef4b6984a9f2aaf96a3330e30095b8049bd2a481fbe775", "bytes": 12785, "lines": 270, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/fill_realism.py", "sha256": "9101eec1e870e0acf5a26dc88153e321764aecde2eda27459718770befc27f8f", "bytes": 18420, "lines": 298, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/fill_realism_io.py", "sha256": "759a7ab6f3a1c0fd34e67d744be6261dac2e5e95b2956bffa8b6eca0897d231e", "bytes": 16958, "lines": 292, "comparison": "EQUAL"}
{"path": "scripts/platformkit/ops/qualification_cause_report.py", "sha256": "fc2cfeaac3318c90ec666fe47758945e3e370da279d82fae2f750040c4eb8341", "bytes": 18233, "lines": 299, "comparison": "EQUAL"}
{"path": "scripts/platformkit/ops/qualification_cause_stream.py", "sha256": "5de1123eae242ac8efc153bb245ddc9527c25f4a7dac6cacdd5c0167fdf6a72d", "bytes": 10241, "lines": 203, "comparison": "EQUAL"}
{"path": "scripts/platformkit/ops/qualification_cause_runtime.py", "sha256": "d4cd9a87ca320b1870473c1f5d97bd515cbd03782c15563b48e5f24b0c200754", "bytes": 3140, "lines": 73, "comparison": "EQUAL"}
{"path": "scripts/platformkit/ops/regime_census.py", "sha256": "a31c2f51c15d77b5c7385032ed890a97a1d2d3b74b0e3c6c45354fafbcdc5a16", "bytes": 12564, "lines": 263, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/capture_book_adapter.py", "sha256": "d1a3ce8325d0142cf71d87ef0c6cfdc59a66f6e6dada055d968c2a1dcfa35b5a", "bytes": 8018, "lines": 202, "comparison": "EQUAL"}
{"path": "scripts/platformkit/ingame/game_market_link.py", "sha256": "133fa3c8cdfb912d5103abdf69f9b7492523980ae2a8aadc548a75f0b6944deb", "bytes": 9248, "lines": 201, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/paper_night_deadline.py", "sha256": "df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b", "bytes": 14592, "lines": 293, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/paper_night_steps.py", "sha256": "3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780", "bytes": 14942, "lines": 293, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/paper_night_lock.py", "sha256": "1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa", "bytes": 1069, "lines": 33, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/paper_night_inputs.py", "sha256": "e7c5913e9fb956ea045d49981bf6e36067991d4546e058d3e78381e63f01e259", "bytes": 9291, "lines": 169, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/ingame_scoreboard.py", "sha256": "2b1a21ac4e94cce0b30f0f04fd157c82b928b2d664fbce37008a52b48f4d352d", "bytes": 22181, "lines": 298, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/ingame_scoreboard_rules.py", "sha256": "5a58a2217f19124a68d46e1c67f201d6ce051618f413ca9668cff7367bb36fc7", "bytes": 6769, "lines": 135, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/registry_scorer_e.py", "sha256": "55c75aca523c2803dbc65af06a12d5192b613e284543e72d0e2daf24f6b4cdbd", "bytes": 17756, "lines": 297, "comparison": "EQUAL"}
{"path": "scripts/platformkit/ingame/registry_readers.py", "sha256": "17e99577505a99c4687835b3d0812d9f90c7ca56b7406a57d72852fb47371ab3", "bytes": 3669, "lines": 83, "comparison": "EQUAL"}
{"path": "scripts/platformkit/execution/paper_night_budget.json", "sha256": "83d2eb3defef596eaf16bbb9caa5befedcf74b8ab543dafc97e330bf94e3d03b", "bytes": 1505, "lines": 25, "comparison": "EQUAL"}
{"path": "tests/platformkit/execution/fixtures/s389_native_books.jsonl", "sha256": "50754ee5c19e9b532e30b3b84e7670678e0db1ae1814e6da77e324ad0755e649", "bytes": 5597, "lines": 1, "comparison": "EQUAL"}
{"path": "tests/platformkit/execution/fixtures/s389_native_state.jsonl", "sha256": "ff69da1451d72176458f0aa507bdc9e4d90e2a0c4d05e2c1bbe6955773f3fcf0", "bytes": 789, "lines": 1, "comparison": "EQUAL"}
{"path": "tests/platformkit/ops/fixtures/s421_books.jsonl", "sha256": "b98a6f3b5639aa82db22912eb52373a1d02e9d1a64247d16fe158f438fc2f30e", "bytes": 3051, "lines": 8, "comparison": "EQUAL"}
{"path": "tests/platformkit/ops/fixtures/s421_state.jsonl", "sha256": "512f78d39d38538478ef9524ffce4ee16f718c295a344f3410302b03d0c93e5c", "bytes": 801, "lines": 4, "comparison": "EQUAL"}
{"path": "docs/evidence/forward/nights/2026-09-24.json", "sha256": "89010ca0ecc5af12e8d155f18da12e9f89ace1fa5a8a4472e1ac9afb4989c86e", "bytes": 7213, "lines": 207, "comparison": "EQUAL"}
{"path": "docs/evidence/forward/nights/2026-09-25.json", "sha256": "fec12c74bd26f04446c186bc38292f8bfe3af0398c28c520074d69ec947f91b6", "bytes": 6202, "lines": 199, "comparison": "EQUAL"}
{"path": "docs/evidence/forward/families_maker_forward.json", "sha256": "c9dc31ea2bc65ff5f622b8c02dfc35e38e5841c2874649f13c9d30f707ed03ee", "bytes": 4225, "lines": 62, "comparison": "EQUAL"}
{"path": "scripts/platformkit/ingame/forward_capture_profile.json", "sha256": "72f798f22269d6a3a74a25313d5743ee57e00732920b1d546b20d1272f046c46", "bytes": 151, "lines": 7, "comparison": "EQUAL"}
```

## FIX 1b

- CORRECTION 1 / 2(a): C14 before: `1 failed, 34 passed`; failure was
  `UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800'`.
  SQLite ticker and trade_id now use ASCII JSON; payloads stay unchanged.
  After: `35 passed`; the lone-surrogate case matches all E1 outputs and the
  landed loader's five events. Existing duplicate-identity tests also pass.
- CORRECTION 2 / 2(b): C25 before: child exit `assert 1 == 0`, unrelated
  process exit `assert 2 == 0`; derive with only stack errors `assert 2 == 0`.
  Probe regression file before: `9 failed, 33 passed`; after: `42 passed`.
  Child NoSuchProcess now waits up to one second before counting an error.
  Unrelated disappearing processes add no stack error; identified stack
  failures remain counted. Receipts add child_errors and stack_errors and
  retain aggregate errors. Derive gates on child_errors, conservatively using
  errors for legacy receipts. Missing or malformed counts remain rejected.
  C25 covers benign child exit, wait timeout, stack exit and unrelated exit;
  C26 covers stack-only errors and child-error rejection.
- CORRECTION 3 / 2(c), also tier-1 inventory correction: before `mismatches=1`
  for test_forward_capture_stream_integration.py; regenerated all 42 A9 rows
  with the pinned full SHAs above. Final normalized inventory: `mismatches=0`.
- Tier-1 fixture-setup NOTE: OS temporary directory proved writable. All 24
  files rerun individually with `-q -p no:cacheprovider -s`; counts above.
  Eight --help commands exit 0. No separate self-check CLI is defined.
- Opus-tier M2 measurement, transcribed from AMENDMENT 2; not measured here:
  exit 0, refused 0, games 4/4, exhausted 41582/41582 blocks, 92777 rows;
  wall 174.5 s, peak 138711040 B versus landed kill 1638944768 B.
  Spool 2.01 GB, snapshot tree 2.58 GB, input 567 MB. No M4 comparison.
- Named follow-ups (2(d), disclosure only): S479 disk-capacity precheck
  (about 4.5x input disk use, no free-disk check); S479 manual-daily isolation
  (same-date manual daily concurrent with paper night can lose snapshots).
  No cleanup or disk-policy code changed. No new fixture paths or LF patterns.

## FIX 1c

- C14 adds `test_c14_tape[selected-surrogate]`: the selected schedule ticker,
  book, gap, trade and closure carry the JSON lone-surrogate escape `\ud800x`.
  The shared differential check confirms landed/streamed rows, counters,
  failures, cutoff and receipt-block accounting are equal.
- Native roles now use ASCII-safe json.dumps on insertion and lookup; freeze
  decodes the stored role before checking native duplicate frequencies.
  The unselected-trade spool assertion follows the encoded role format.
- In-memory revert proof: compile the SQL module with both role bindings
  restored to raw role and the freeze decode removed; temporarily replace
  Store.add_native, Store.native and Store.freeze using pytest.MonkeyPatch.
  Run only the new C14 case: `1 failed, 35 deselected`, with UnicodeEncodeError
  at the native INSERT for `trades:\ud800x`. Original methods are restored
  after the run; no on-disk source reversion was performed.
- Final per-file reruns with `-q -p no:cacheprovider`: stream 36 passed,
  integration 8 passed, probe 42 passed; total 86 passes across three files.
  The FIX 1b table above remains the historical wider rerun.
- Regenerated all 42 A9 rows from the final checkout against CURRENT master,
  pinned above. The S481 game_market_link.py context update is upstream,
  not a candidate edit. No other code or probe behavior changed in FIX 1c.

## NOT VERIFIED

Full-day landed/streamed byte equality, M1, M3, M4, phase-C budgets,
archive before-condition items ii/iv, and kills outside paper_night.
Opus-tier M2 is reported evidence only; this lane did not rerun a live stack
or real corpus. No candidate commit was created; landing remains pending.
