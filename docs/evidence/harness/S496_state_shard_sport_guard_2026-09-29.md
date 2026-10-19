# S496 - candidate complete: 20/20 CONSTRUCT

Local worktree: `C:/Users/neelj/nba-harness-h160`. Construct inputs only.
Binding spec: `docs/evidence/tracking/specs/S496_spec.md`, including AMENDMENTS 1, 2 and 3.
The spec was read first. The supplied dispatch census satisfies the archive prerequisite.
S485 AMENDMENT 3(a) is RESOLVED; independent verdict: ACCEPT WITH CORRECTIONS (AMENDMENT 2).

## Binding before-condition

Orchestrator dispatch output, quoted verbatim (supplied by the user; not rerun in this lane):

```text
ORCHESTRATOR DISPATCH CENSUS (this satisfies the spec's census-at-dispatch requirement; you have no archive -- quote this verbatim in the memo and do NOT block on it): re-run by the orchestrator 2026-09-29T17:34:40Z..17:35:32Z with the spec's script s496_census.py over every file in the state archive: rows whose sport != shard directory -- mlb 0 of 49,462 (7 files); nba 0 of 2,709 (8); ncaaf 0 of 48,891 (8); nfl 0 of 52,449 (8); soccer 0 of 2,309 (8); tennis 0 of 2,940,891 (8); wnba 0 of 1,503 (3). Every directory holds exactly one sport label equal to its name. The previous build attempt stopped on this census; it is now supplied -- BUILD THE FULL CANDIDATE per the spec and AMENDMENT 1 (a)-(g), all construct cases, per-file tests, preflight, memo. The existing memo docs/evidence/harness/S496_state_shard_sport_guard_2026-09-29.md in this worktree is a stub from the stopped attempt: rewrite it.
```

The local construct before-condition was run before production edits:

```text
python -m pytest tests/platformkit/ops/test_forward_qualification_cross_sport.py::test_s496_current_cross_shard_pass_without_own_state_is_pinned -q -p no:cacheprovider
1 passed in 454.43s (0:07:34)
```

Its assertions establish NBA PASS, 720 decisions, 240 NBA-labelled rows in the MLB shard,
and no NBA state shard. This is the defect, not a candidate acceptance result.

## Owned implementation and imported contracts

Production edits are limited to `scripts/platformkit/execution/forward_replay_io.py`
and the AMENDMENT 1(a) authorized call in
`scripts/platformkit/execution/forward_capture_stream.py`.
The shared reader receives the already parsed Decimal cutoff. For exact state shard paths,
it applies receipt precedence, validates the receipt, counts future rows and invalid receipts,
then counts and drops visible string sport mismatches before either loader deduplicates.
It emits each accepted row unchanged. Clean runs never insert the new counter.
Mismatches do not themselves add unreadable_state or a global linkage failure.

Read before coding and relied on these exact landed signatures:

```python
parse_venue_time(value: object) -> float | None
stamp(value: object) -> Decimal
iso(value: Decimal) -> str
read_jsonl(paths: Iterable[Path], *, state: bool = False) -> Iterator[dict]
_native_input(paths: Iterable[Path], source: str, counts: Counter) -> Iterator[dict]
native_rows(paths: Iterable[Path], source: str, as_of: object, counts: Counter) -> list[dict]
chronological(events: Iterable[dict], as_of: object, counts: Counter) -> Iterator[dict]
load_native(books_paths: list[Path], state_paths: list[Path], trade_paths: list[Path],
            supervisor_journals: list[Path], schedule: list[dict], *,
            as_of: object = None) -> NativeEvidence
load_native_streamed(books_paths: list[Path], state_paths: list[Path],
                     trade_paths: list[Path], supervisor_journals: list[Path],
                     schedule: list[dict], *, as_of: object,
                     scratch_dir: Path) -> StreamedEvidence
main(argv: list | None = None) -> int
_snapshots(inputs: dict, root: Path) -> tuple
```

The parser is in `scripts/platformkit/execution/venue_time.py`; stamp retains the ISO
nanosecond tail exactly. Loader definitions are in forward_capture_bridge.py and
forward_capture_stream.py. The last two signatures are in
`scripts/platformkit/ops/forward_qualification_daily.py`; its streamed import is line 28.
The internal reader now adds keyword-only `end: Decimal`; both callers pass `end=end`.
No public loader signature, dedupe key, accepted payload or threshold changed.

Construct helpers were read from the existing cross-sport tests before import:
`game(sport, name=None, start=NEXT + "T00:00:00Z", key=None)`,
`state(g, seconds=0)`, `book(g, seconds=0)`, `tape(g)`, `jsonl(rows)`, `write(path, payload)`.
The baseline test also read `make(root, sports=("mlb", "nba"), missing=("nba",))`
from test_forward_qualification_sport_isolation.py and the existing populate helper.
The spec supplies no REAL ROW; all evidence here is constructed from those helpers.

## Frozen construct enumeration

The revised denominator was frozen before new tests ran: n = 20 (CONSTRUCT).
Groups 1-14 retain the spec numbering. Groups 15-20 make the amended requirements explicit.
The bar is all 20 groups; parameter instances are reported separately and do not change n.
Test companions: the spec-owned new reader test, AMENDMENT 1(d)'s baseline contract, and
tests/platformkit/ops/test_s496_baseline_clean.py (AMENDMENT 3 split). The original unrelated tests remain intact.

The before column comes from scripted evaluation against full pinned source
`e773b1140e82d5f09bff0ee4ea2b8b710dbd144d`, plus the original daily pin above.
Native counts describe the reader or linkage stage, not a completed daily artifact unless stated.
The after column is exercised by the completed per-file tests below: all 20 groups passed.

| Group | Before observation | Candidate assertion |
|---|---|---|
| 1 mismatch | 1 native row, no mismatch count | 0 rows; mismatch 1; no unlinked_state_row |
| 2 clean | 1 native row; empty native counters | Identical payload; counter absent |
| 3 strict strings | Three combined rows retain three duplicate refusals | All three dropped; mismatch 3; singleton variants tested |
| 4 invalid sport | Existing invalid_sport path | Same refusal; no mismatch count |
| 5 other layouts | Four flat/non-layout variants pass through | Both loaders retain the state row |
| 6 malformed records | invalid_json/invalid_record plus unreadable_state | Same exact counters in both loaders |
| 7 other sources | Six source/layout combinations retain one row | No mismatch counter |
| 8 absent NBA shard | Daily NBA PASS, 720 decisions | Fresh daily JSON: FAIL, 0 decisions, 0 covered_ms; mismatch 240; missing shard 1 |
| 9 mixed MLB shard | Both sports link; 241 state outputs | MLB own-only summary identical; NBA FAIL; mismatch 240 |
| 10 clean artifacts | Full pinned package produces control bytes | 41/41 raw-byte and SHA-256 pairs equal |
| 11 key collision | 2 duplicate refusals; real NBA row cannot link | Real NBA row links; mismatch 1; no duplicate refusal |
| 12 loader differential | 240 mislabelled state outputs | Both loaders: no state outputs, mismatch 240, equal counters |
| 13 mutants | Missing guard fails the new mismatch assertions | Four IO-only mutants killed by groups 1, 3, 5, 4; streamed coverage is differential |
| 14 snapshot layout | Daily source preserves state/sport/date layout | Runtime snapshot spy asserts exact components |
| 15 nanosecond cutoff | Before/cutoff visible; later receipt counted future | Before/cutoff dropped as mismatches; future count unchanged |
| 16 receipt validation | invalid_time 2, unreadable_state 2, future_records 1 | Same diagnostics; only valid visible mismatch adds 1 |
| 17 permutations | Colliding NBA rows cannot link in either order | Reversed shard paths and row/schedule orders produce identical keyed results |
| 18 repeated mismatches | Three native rows all carry duplicate refusals | Each input dropped once; mismatch 3 |
| 19 genuine duplicates | Three same-sport MLB rows, two duplicate refusals | Same two refusals; no mismatch count |
| 20 dense valid both | 480 duplicate refusals; NBA linkage failure; 240 MLB outputs | 480 valid state outputs; mismatch 240; both own-only summaries identical |

The pinned-reader attack ran the final reader assertions with the pinned `_native_input`
substituted in both callers (an adapter accepts and ignores only the new cutoff argument):
`11 failed, 28 passed, 4 deselected in 4.49s`. The failures are expected before results;
only the four candidate-specific mutation constructors were deselected.
Reproduce that before attack from the worktree with this Python snippet (exit 1 is expected):

```python
import subprocess, types, pytest
from scripts.platformkit.execution import forward_replay_io as io
from scripts.platformkit.execution import forward_capture_stream as stream
base = "e773b1140e82d5f09bff0ee4ea2b8b710dbd144d"
source = subprocess.check_output([
    "git", "show", base + ":scripts/platformkit/execution/forward_replay_io.py"])
old = types.ModuleType("s496_pinned_io")
exec(compile(source, "<pinned-s496-io>", "exec"), old.__dict__)
def before(paths, source, counts, *, end):
    return old._native_input(paths, source, counts)
io._native_input = stream._native_input = before
class Report:
    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            print("BEFORE_CASE " + report.nodeid.split("::")[-1] + " " + report.outcome)
raise SystemExit(pytest.main([
    "tests/platformkit/execution/test_forward_replay_io_shard_sport.py",
    "-q", "-s", "--tb=no", "-p", "no:cacheprovider", "-k", "not c13"], plugins=[Report()]))
```

A separate scripted native/linkage audit produced these exact counts:

```text
C1 before rows=1 counters={} after rows=0 mismatch=1
C2 before rows=1 counters={} after rows=1 counters={}
C3 before rows=3 refused=3 after rows=0 mismatch=3
C4 before rows=3 refused=3 after rows=3 refused=3; mismatch absent
C9 before state_output=241 both_linked; after state_output=1 NBA LINKAGE_INVALID mismatch=240
C11 before duplicate_native_record=2 state_output=0; after NBA_linked state_output=1 mismatch=1
C12 before rows=240 after rows=0 mismatch=240
C15 before rows=2 future_records=1; after rows=0 future_records=1 mismatch=2
C16 before rows=1 invalid_time=2 unreadable_state=2 future_records=1
C16 after rows=0 invalid_time=2 unreadable_state=2 future_records=1 mismatch=1
C18 before rows=3 refused=3 after rows=0 mismatch=3
C19 before rows=3 refused=2 after rows=3 refused=2
C20 before duplicate_native_record=480 unlinked_state_row=480 state_output=240 NBA LINKAGE_INVALID
C20 after state_output=480 mismatch=240 both_linked
```

## Raw-byte protocol and reproduction

`tests/platformkit/ops/test_s496_baseline_clean.py` (split from the contract test) extracts the full pinned source package,
then invokes pinned and candidate daily code with the SAME input bytes, paths, cwd, profile,
families, arguments, nonce, ledger path and output path. It resets only test-owned output and
ledger files; it verifies input bytes remain unchanged and snapshots have been removed.
Each pair must match raw bytes AND SHA-256 and lack state_row_sport_mismatch in diagnostics.
There is no normalization of result JSON and no comparison against a moving revision.
The historical S485 runner still defaults to its original full SHA.
The S496 IO freeze exemption covers only _native_input and its authorized caller argument; the S501 paper_night hook exemption is also retained.
No other source freeze is removed.

No new committed JSON fixture or seal was needed under AMENDMENT 1(f).
New `.gitattributes` patterns: none. Runtime JSON lives only in test-owned temporary roots.

Recorded raw-artifact SHA-256 pairs (one value means baseline and candidate matched).
Temporary absolute paths are part of the JSON; fresh roots can change these hashes.
The test asserts equality within each controlled pair, not equality across unrelated roots.
All 41 cases below are final, including the focused isolation rerun.

```text
mlb:absent cd983708fbc9388ecccd3eaea47a4f2df5a291d2f501779350950ba222d17311
mlb:empty be146540ccdaddc8e29be2a429b1a26152e46fc993676d5fd90b418ce38ce4de
mlb:unusable 7bff624176ad17e96640aad4e114b4781b9bfd95d561ffaabf2aeb89e8e46efe
nba:absent c8e42631183cb302e1c247080f22c15137cef0a08aa30696eaffecc579e50bbe
nba:empty e2197ca2749f8aca5ae16a101ce3cf73275049632247bda66776b0fd7782566d
nba:unusable f309f889b90ff16dfbe82ecc58c01b96fe6a10819b7ea99947df47593794a68e
nfl:absent 7f98bb981ca0c7b5b70b1908dc296e7d6350b9d5619a1a1e34763bd4c9500459
nfl:empty 9308b8d4def807ed304c14f8bda64659d2fa301049c82f2ee0155f2f3f0e36b8
nfl:unusable e76692db036189c97c5722b9d2a1649b141fa2e21bc03034d787a5a8793a4c9f
soccer:absent b63cbda9093dc08da93cfbbbeb715df7a3a3c3a93bc638a2f6fdc9b71f0f8609
soccer:empty 56f80e4a4b279d4e802c7691be9ec333b77398888ca327e9d8960f74e978e357
soccer:unusable d798840b495a9d1cf53439a373c5f2eb68f1b3e6dc2fdb3648e27d1ae83be614
tennis:absent 3d8dfefb8d8666781c067c4a83b2cd429c18bd25a7e976c84682484b1cdc2087
tennis:empty a92cda0f071632525287b1cecfd9770fe025947bc23ccc92ec597c8b8a6cbb66
tennis:unusable 84982a40996266954ed8e748c13fb69360c3499c5dade7d1f33a0a0ff778478b
dense d932346019d3d8d2a5a41938dc5ad8bf8803528c4b51026c1b6467bfb28889cf
collision 329f2eaf0ef9bb3632e126d3eda9e5af1a28f15eff5011301e9f972d38962028
malformed 36147083572a09e2d22c4f078f79dddf367d4bad258c53dca8220995a7e0b5f9
healthy a8fc35d69001f4ab73b73084883108f5a80d1b8bc9756eacbfc9433bbd26e19d
quiet d60b89b4e20feda976cc1ed22a3954c61eb32f29de769131807de05fdfa9e128
cap:1:yes 2fe8ecf64b5273102bf8ea0b240cf1bf719fe713c5373e7995e9c8df1cab707d
cap:1:no c4a63012ad23f1a9d831f4e1b2ed05f6f601f4751d35c3e78cd83848bac9c494
cap:100:yes 24c8cdfc58afe424c63c59775037cd3fc88acbd03c31a5fac139f4f1219e1e91
cap:100:no f82fa0bd9d16fa2950cfe2b1372d675c1da2c6b75905c16deaae7e0ba3dc142c
isolation:binding d010d7e269e98723e963eb56b6d442677bd6f23e8c659ece38a0a65f5e2d0f22
isolation:two-missing f8045e51ed1d3beb38d19a0a399c1b68fd9543451acba3f5a18a04a5c5673a15
isolation:empty ad926c8363636b2f66bb86e04908432476f358f40fef2066a4881250420f30ab
isolation:no-books 095f0a7f4c359ab5ad5fe9463364b7b4099d2f2c200beeeb9ef8a32a8f8deac8
isolation:no-state 5906fee62ca3ef534093d1cfc8f6929c641646e56025458761577ceada1eb9cc
isolation:neither 0ae573576c8e4753df25f6405c194112c73025b4afe4625d12d97e35d3406313
isolation:before 0811277e842569a8579299872e16a0ad8d4fe832210c683437f1d0e014df1c25
isolation:equal e500959bae04fde9513d4330c098de594fc2d7521e0d7e395da6cbd9914eae4f
isolation:after 766062f62fc12d3bdf75929047d72046740e210bb4c816472359478a22f03491
isolation:next-absent 497a3507c0958a022f942df61a7cdbda78dba209127b5daa5c762c2907bbd348
isolation:next-empty daff5b8657dacdc3f3d6b331da7fc9a9699c2015564b76a19add9d488fcee3c7
isolation:bad-before 1032895718f9bb565085507a32c701fe0a8905dc8c084fc0add391ced7cf21e4
isolation:bad-after ecb016d6df5b8b83eae123daeb60655d6721ec52e34ad6423aa02441c08c0a90
isolation:reverse c39c5844654e23e7970ea413f70f6eae67652b6a5c1081055c759e378f508718
isolation:healthy 37d2bd362b188826a4d59f14176df08d79b700f2ff0736df99f604df8fea9670
isolation:receipt e10507d2a6b8c3035b03d9f582ea525362fc0b82500b0f00dfebab22b039ea3d
isolation:receipt-reverse 8c7045874dccd920a68bf4f7bf666a8869edea03c116edcd1edb077fbd4eec16
```

Prior candidate results (not FIX 1b reruns); commands use `python -m pytest <one file> -q -p no:cacheprovider`:

| Test file under tests/platformkit/ | Result |
|---|---|
| execution/test_forward_replay_io_shard_sport.py | 43 passed in 5.36s (final file) |
| execution/test_forward_capture_stream.py | 36 passed in 7.91s |
| execution/test_forward_capture_bridge.py | 60 passed in 3.45s |
| ops/test_forward_qualification_sport_isolation.py | 21 passed in 133.42s |
| ops/test_s485_baseline_cases.py | 22 passed in 48.84s |
| ops/test_forward_qualification_daily.py | 31 passed in 3.60s |
| ops/test_forward_qualification_cross_sport.py | 25 passed in 3280.99s |
| ops/test_s485_baseline_contract.py (pre-split) | 45 passed in 857.23s; post-split: contract 4 + s496_baseline_clean 41 |

An initial cross-sport run was interrupted after 16 passing cases to use the explicitly
permitted sparse own-only equality in group 9. It is not counted as a completed test run.
A second incomplete run was interrupted to isolate the new permutation test's output ledger.
The final test atomically empties only its own ledger before the reverse run; both permutations
therefore start with the same inventory/history input. Evidence remains fully dense for both
NBA and MLB in group 20. No persistence operation is mocked.
The baseline file's 17 isolation fixtures were finalized while the first run was active.
Its focused rerun (`-s -k 'isolation or not clean_artifact'`) passed those 17 variants
and four source freezes, with 24 unchanged cases deselected. All 45 final cases are covered.

CLI help exits 0: forward_qualification_daily, forward_replay, and contract_preflight.
The two production modules changed here expose no CLI of their own.
Required contract preflight: 9/9 PASS over the seven owned paths; the final memo is checked again.
The eight reproduction files cover 283 distinct passing test instances (pre-split counts; bridge is now 61). The focused 21-case
baseline rerun is a subset, not an additional denominator. The original before pin passed once;
the pinned-reader attack's 11 failures are expected before results, not candidate failures.
Source review found no blocking defect; that review ran no tests.
An all-Python search of scripts/platformkit and tests/platformkit found exactly two production
_native_input callers (IO and stream); both pass end=end. No caller was missed.
Production source SHA-256 values (UTF-8/ASCII with LF, no moving git reference):
forward_replay_io.py: `b8749925a78d2f9f349332d8d920ceed7b9db244ab8aab57588da6eaec4ac246`.
forward_capture_stream.py: `b4cfb197f6819949fc89247c909d0a3fc0bdda4420531defd7cf9a66e1498bbc`.

## REAL-DAY

Orchestrator probe supplied in AMENDMENT 2(c), quoted verbatim; not rerun in this lane:

```text
2026-09-24, forward_qualification_daily with master code and with the candidate, identical args, capture root, nonce and out path; both exit 0, wall 128.7 s / 129.0 s, peak RSS 137,793,536 B / 137,637,888 B; artifacts differ only by the code-root string in declared_constants.capture_profile_path (2 occurrences, the two checkouts live at different paths, so AMENDMENT 1(e)'s identical-path condition was met for every input path but not for the code root); after substituting that string the candidate is byte-equal, sha256 520647b3b5448358f13bf4082e8ee7be63b348a764d52996e848872c05866f6a (9,574 B). Script scratchpad/s496_realday.py (orchestrator-owned, not tracked).
```

This is equality after the stated substitution, not an unmodified raw-byte match.

## FIX 1b

- (a) Retained both existing exemptions: S501 paper_night and S496 _native_input. Restricted rebased rerun results are recorded below; other per-file reruns belong to the orchestrator.
- (b) Added regime_census.py:55-76 as the third unguarded mirror and expanded the follow-up request in NOT VERIFIED.
- (c) Recorded the supplied REAL-DAY probe verbatim, including the code-root mismatch and substitution.
- (d) Corrected group 19 to same-sport MLB duplicates; cross-sport coverage is test_native_state_key_collision_remains_cross_sport and CLEAN_CASES collision. c13 monkeypatches forward_replay_io._native_input only; differential tests protect the streamed loader.
- (e) NOTE: <root>/state/state/x.jsonl is treated as shard "state" because the guard keys on the grandparent name; no daily layout produces it.
- (f) Memo-only correction. No code or regression test change was requested; no failing reproduction was supplied by this verdict. No additional executable probes were run.

FIX 1b tests used `python -m pytest <one file> -q -p no:cacheprovider`:
- ops/test_s485_baseline_contract.py: `2 failed, 43 passed in 724.98s (0:12:04)`.
- Both failures (isolation:next-absent, isolation:healthy) quoted: `PermissionError: [WinError 32] The process cannot access the file because it is being used by another process`; candidate daily `_atomic`, `os.replace`, artifact.json.
- Same file retried with `-k 'isolation:next-absent or isolation:healthy'`: `2 passed, 43 deselected in 32.15s`. All 45 cases passed across these runs; the full run itself was not green. Lock owner is unknown; no code changed.
- execution/test_forward_replay_io_shard_sport.py: `43 passed in 4.55s`.
ORCHESTRATOR (AMENDMENT 3): the S496 clean-construct block moved verbatim to tests/platformkit/ops/test_s496_baseline_clean.py (contract file 181 lines, new file 134); no assertion changed.
Orchestrator per-file runs on the rebased tree (master 5a2d1f7d7 + candidate): shard_sport 43; bridge 61; bridge_keyed 34; capture_stream 36; replay 49; replay_qualification 79; cross_sport 25 (4346 s); daily 31; inputs 48; sport_isolation 21; s485_baseline_cases 22; qualification_cause_stream 25; s485_baseline_contract 4; s496_baseline_clean 41 (916 s). All green.
No new JSON fixture or seal; new `.gitattributes` patterns: none.

## NOT VERIFIED

- No real-day run occurred in this lane. The supplied orchestrator result is recorded above;
  unmodified raw-byte equality under identical code-root paths remains unverified.
- qualification_cause_report.py and qualification_cause_stream.py still group by row sport
  without guarded shard provenance. A third mirror, scripts/platformkit/ops/regime_census.py:55-76,
  selects state rows by game_key only, ignoring shard sport: an nba-labelled row in state/mlb/
  reaches its index while native_rows counts state_row_sport_mismatch 1 (verifier finding).
  All three can disagree diagnostically with qualification. FOLLOW-UP REQUEST FOR ORCHESTRATOR:
  register and own a separate provenance guard for all three routes; registration is not verified.
- Run-level diagnostics remain not sport-isolated (S485 AMENDMENT 3(d)).
- A mismatched row is dropped, not quarantined or repaired.
- Absent/invalid sport is refused by the pre-existing path, not by the mismatch counter.
- Correctly labelled cross-sport native key collisions remain refused because dedupe keys
  deliberately exclude sport; test_native_state_key_collision_remains_cross_sport and the
  CLEAN_CASES collision case cover this. Group 19 covers same-sport MLB duplicates only.
- No real state archive, network, pod, service restart or deployment was exercised.
- No git commit was created; git metadata is read-only under this sandbox.
