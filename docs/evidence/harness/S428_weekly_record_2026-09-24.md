# S428 weekly record

Candidate passes the eight specified construct cases; independent landing verification is pending.
Local Windows worktree: C:/Users/neelj/nba-harness-h85. No captured archive, network, pod or GPU run.
Metric: enumerated construct cases passing. Before: 0, module absent. Bar: all 8. After: 8/8 (CONSTRUCT).
The per-file test collection additionally exercises malformed inputs and write recovery: 53 passed.
Eye check: n/a (S-row). Reproduction uses the explicit CLI and byte comparisons below.

## Binding before-condition

Executed locally before coding using imports, inspect.signature, git ls-files,
the absent durable path, the complete declarations list and a data/** week-file census.
Quoted output (the empty summary is documented separately by its exact schema):

```text
module_absent= True
TARGET_WEEKS= 8 bars= (4, 30, 30)
ledger_signature= (path: 'Path', families_path: 'Path', *, as_of: 'str | None' = None)
families= [('maker_forward_mlb', 4), ('maker_forward_nfl', 4), ('maker_forward_tennis', 4), ('maker_forward_nba', 4), ('maker_forward_soccer', 4)]
durable_ledger_exists= False records= []
tracked_week_data= []
data_week_data= []
daily_artifacts= ['2026-09-22.json']
```

The full ledger source was read: records filters current/future ISO weeks before
row validation; append permits only completed weeks; streak uses the declaration's
weekly_floor; independence preserves both missing and shared-game statuses.
The full causal-summary source was read: it performs no artifact write.
The browser JSON checker only verifies parseability and finite numeric values.
The public copy checker does not currently scan the forward directory.

The four protected files have zero Git diff against master. Raw-byte comparison
against Git blobs initially returned False for all four: this checkout has CRLF
and master blobs have LF. A second probe returned LF_normalized_equal=True for
all four (checkout CRLF counts respectively 235, 293, 262, 62; master counts 0).
No protected file was edited or normalized. Their checkout hashes are below;
literal checkout-to-blob byte equality is not claimed.

## Imported interfaces read before coding

Exact inspected signatures:

```text
FamilyWeekLedger.__init__(self, path: 'Path', families_path: 'Path', *, as_of: 'str | None' = None)
FamilyWeekLedger.records(self) -> 'list[dict]'
FamilyWeekLedger.streak(self, family: 'str') -> 'int'
FamilyWeekLedger.independence(self, iso_year: 'int', iso_week: 'int') -> 'list[dict]'
parse_venue_time(value: 'object') -> 'float | None'
summary_strict(fills: 'Sequence[Dict[str, Any]]', ticks: 'Sequence[Dict[str, Any]]', *, horizons_s: 'Sequence[float]' = (30.0, 120.0, 300.0), max_wait_s: 'float' = 30.0, cluster_key: 'str' = 'game_id', n_intents: 'Optional[int]' = None, intents: 'Optional[Sequence[Any]]' = None, max_book_age_s: 'Optional[float]' = None) -> 'Dict[str, Any]'
```

The renderer imports the two bar modules and the venue parser. Tests additionally
import summary_strict. The first test writes the producer's returned dict verbatim
and consumes it through the CLI. No literal REAL ROW was supplied by S428.
Counts, horizons, nested field sets and nullability are validated without computing
a new mean or interval. The JSON retains every ledger field and the full summary;
Markdown includes the same full record after its readable tables.

## Eight acceptance cases

| Case | Construct evidence | Result |
| --- | --- | --- |
| Zero weeks | test_zero_weeks_and_imported_bars | PASS |
| Completed week and full artifact | test_full_producer_fixture_end_to_end | PASS |
| INSUFFICIENT | test_insufficient_verbatim: zero fills, unscored fill, one cluster | PASS |
| Current week omitted; its file refused | test_current_week_filtered_before_validation_and_file_refused | PASS |
| Shared-game pair | test_not_independent_pair | PASS |
| Two byte-identical renders | test_two_renders_byte_identical | PASS |
| Exact input digests | test_provenance_bytes_and_sha | PASS |
| Forbidden unit token refused | test_forbidden_labels_refuse_without_outputs | PASS |

Additional tests cover strict counts, non-finite and out-of-domain numerics,
duplicate JSON keys, schema changes, absent summaries, chronological ordering,
both row permutations, naive timestamps, sub-microsecond ISO-week boundaries,
input mutation, failed atomic replacement, and large finite delays actually
returned by the landed producer. The latter has no invented upper limit.
Input-order comparisons exclude provenance because changed bytes must change hashes.
Review found and removed one unsupported delay cap; its regression test passes.

## Inputs and provenance

All paths below have prefix C:/Users/neelj/nba-harness-h85/.
These are text inputs; image resolution is not applicable.

| Input | Bytes | SHA256 |
| --- | --- | --- |
| scripts/platformkit/execution/family_week_ledger.py | 11384 | ffa5c7e45775d35c44dcf7fbbf0b0019fc38bad84b29e44ab7f56920adb17618 |
| scripts/platformkit/execution/markout_causal.py | 14975 | f85013fac9ee394049f21bfe9d739669dadc4b769a97e375fe7ce890d64a1415 |
| scripts/platformkit/execution/forward_replay_qualification.py | 14837 | 0170676d9d4e17e1792deb8fb556a490afaeea2ae033369a4148392fcbf1c84e |
| scripts/platformkit/execution/venue_time.py | 2029 | 651d80edc0ef0788ea543b2cf3e9f4ae8c1d5114e67211cf7fcd6047eade79f8 |
| docs/evidence/forward/families_maker_forward.json | 4287 | d9117eed01191e43daf2d45fd272500714295a020ddaf33da38c551db4bf0e31 |
| docs/evidence/tracking/specs/S428_spec.md | 6943 | 55694ea0090df4175a62287355a8a0c55eebca13f7f6b4270cd9f1ae8e4d5d65 |

The absent input is C:/Users/neelj/nba-harness-h85/data/cache/forward/family_week_ledger.jsonl.
There were no markout files opened. The output PROVENANCE blocks give full paths,
byte sizes and digests for every runtime data input and both bar modules.
Construct fixture hashes are checked against the bytes at test time; fixture
definitions are durable in tests/platformkit/execution/test_weekly_record.py.

## Reproduction and local zero-week preview

```text
python -m pytest tests/platformkit/execution/test_weekly_record.py -q -p no:cacheprovider
53 passed
python -m scripts.platformkit.execution.weekly_record --help
exit 0
python -m scripts.platformkit.execution.weekly_record --ledger data/cache/forward/family_week_ledger.jsonl --families docs/evidence/forward/families_maker_forward.json --markouts docs/evidence/forward/markouts --as-of 2026-09-24T00:00:00Z --out-md docs/evidence/forward/WEEKLY_RECORD.md --out-json webapp/public/data/forward/weekly_record.json
0 completed weeks as of 2026-09-24T00:00:00Z
node webapp/scripts/verify-public-json.mjs webapp/public/data/forward
Public JSON scan: 1 files, 0 failures.
```

The preview uses the confirmed absent durable path; it does not process any real
weekly records. The first real populated render remains the orchestrator's task.
Repeated CLI execution is checked against both output files byte-for-byte.
All five owned files are ASCII with LF and at most 300 lines.
The required preflight command names the module, test, both outputs and this memo
with --base master --spec docs/evidence/tracking/specs/S428_spec.md.
Result: 9/9 PASS (vocabulary, CRLF, LOC, schema, head_slice, spec_threshold,
proposed, removed_artifact, row_duplication). CLI help: 1/1 pass. Browser JSON:
1 file, 0 failures. Public copy regex applied directly to both outputs: 2 files,
0 failures. Repeated CLI output comparison: both files identical.
Final line counts: module 240, tests 272, Markdown output 63, JSON output 1.

## Contract self-check

A9: runtime paths, byte sizes and SHA256 are in both outputs. B1-B11 and Q1-Q9:
construct denominator is explicit, no schema removals or protected edits, no
deployment or fitted comparison, no changed bars, and deterministic repetition.
S1: local only. S2: before-condition measured above. S4: completed-week counts
come from FamilyWeekLedger.records; named counts are qualified_games and
fill_bearing_games. Missing evidence is preserved as NULL or MISSING EVIDENCE.

## NOT VERIFIED

- No populated real weekly ledger, live summaries, captured archive or site page was exercised.
- Independent landing verification and orchestration on the full tree remain pending.
- Literal raw-byte equality with master blobs differs solely by existing checkout CRLF.
- Provenance rechecks catch observed input changes, not a concurrent change-and-restore race.
- Each output is atomic independently; failure between replacements can leave different generations.
- The failed-replace test preserves the old file and recoverable temporary bytes; power loss was not simulated.
- No producer fill, fee, queue, model or qualification behavior was changed or validated by this renderer.
- SHA: NOT CREATED (sandbox); files ready for lane_commit.
