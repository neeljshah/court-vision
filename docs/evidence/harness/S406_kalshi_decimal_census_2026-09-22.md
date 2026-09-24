# S406 decimal text census - PREPARE

Binding scope: docs/evidence/tracking/specs/S406_spec.md, AMENDMENTS 2 through 7.
FIX 1e supersedes earlier checks; verifier findings are inlined below.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B and Q.
Machine: local Windows assigned worktree; CPU-only constructs.
No real archive was opened. No reader was called or refusal reproduced.

## Before-condition, checked against master

Master was b7e42569af5131c759674907037489b8a2290d39. A git diff against master
for the three quoted source files was empty. Verbatim source excerpts follow;
the two-line read_rows call begins at line 213, not a one-line approximation.
scripts/platformkit/execution/coherence_scanner_inputs.py:213-214:
```python
                row = json.loads(line, parse_float=Decimal, parse_int=Decimal,
                                 parse_constant=Decimal)
```

scripts/platformkit/execution/coherence_scanner_inputs.py:19-25:
```python
    """Accept exact strings/Decimals only; refuse missing and nonfinite values."""
    if not isinstance(value, (str, Decimal)):
        raise ValueError("expected a decimal string")
    number = Decimal(value)
    if not number.is_finite() or not math.isfinite(number):
        raise ValueError("nonfinite number")
    return number
```

scripts/platformkit/ingame/local_capture_runner_row.py:113-121:
```python
    out.update(api_ts=body.get("ts"), yes_bid=yb, no_bid=nb,
               yes_ask=Decimal(1) - nb if nb is not None else None,
               no_ask=Decimal(1) - yb if yb is not None else None,
               yes_bid_size=yes[-1][1] if yes else None, no_bid_size=no[-1][1] if no else None,
               depth_bid=sum((x[1] for x in yes), Decimal(0)),
               depth_ask=sum((x[1] for x in no), Decimal(0)),
               yes_bid_top5_asc=yes[-5:], no_bid_top5_asc=no[-5:], close_time=close_time,
               minutes_to_close=(Decimal(str((close - end).total_seconds())) / Decimal(60)
                                 if close and end else None))
```

scripts/platformkit/ingame/local_capture_writer.py:15-25:
```python
def encode_json(value: Any) -> str:
    """Serialize Decimal as JSON numbers without a binary float conversion."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("nonfinite decimal")
        return str(value)
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + ":" + encode_json(v) for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(encode_json(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=True, allow_nan=False)
```

Integral JSON numbers reach this landed reader as Decimal. The writer serializes
Decimal directly as number text. The superseded reader explanation is withdrawn.
The census neither imports that reader nor attributes any historical refusal.

## Census schema and counting rules

Top-level JSON: notice, groups, shards. The exact notice is:
`counts only; nothing here converts a stored float to text or claims its original precision`
Each group contains record_type, capture_version, rows, and fields. Each field
contains counts for number_integral_text, number_fractional_text,
number_exponent_text, string, null, absent, bool, other; max_fractional_digits;
and more_than_6_fractional_digits. All counts and digit lengths are strict ints.
The denominator for each top-level field is the valid object rows in its group.
Absent equals group rows minus present occurrences, computed after all shards
from the union of field names within that record_type and capture_version.
Each UTF-8 line is decoded once with json.loads(line, parse_float=str,
parse_int=str, parse_constant=str). A lexical pass over the same line retains
quoted versus unquoted value provenance, including ladder cells; scanstring unescapes keys
only. Thus 43 and "43" have different classes without numeric conversion.
Duplicate keys follow json.loads last-value semantics. Nested objects and arrays
are other at the top level. In addition, orderbook yes/no levels contribute
orderbook.yes.price, orderbook.yes.size, orderbook.no.price, orderbook.no.size.
FIX 1d adds book.orderbook_fp.{yes,no}_dollars and {yes,no}_bid_top5_asc
with <ladder>.price / .size / .extra_cells / .empty_ladder. Non-list sides
emit <ladder>.non_list; non-list levels retain their own class (null / other).
Each empty side contributes an empty_ladder count (other; orderbook.empty_ladder
for the legacy sides); cells beyond the second contribute .extra_cells, keeping
their text classes. UNITS: .price / .size / .extra_cells classes count CELLS
(one per level), while absent counts ROWS; never divide a class count by
(class + absent). Ladder absent mixes three cases: a row with no ladder, a row
whose ladder is empty (the real mlb snapshot group's no_dollars .price absent
4,763 equals its empty_ladder 4,763), and a missing cell (a level [] counts
absent under both .price and .size). A null level counts once under .price AND
once under .size. A non-object book.orderbook_fp gets no named count beyond the
top-level book other. Of the 14 ladder fields per real artifact, two are the
top-level top-5 fields yes_bid_top5_asc / no_bid_top5_asc (their other 24,843
is a row presence count) and twelve are per-position (.price, .size and
.empty_ladder at the four AMENDMENT 6(a) locations).
Multiple levels never create negative absent counts. Bare NaN and
Infinity constants are other. Quoted numeric-looking text is always string.
Fractional digit counts include trailing zeros, exclude the point and sign,
and apply only to number_fractional_text. Exponent texts are a separate class.
Text length alone establishes neither numeric origin nor original precision.
Groups use the metadata on each row; no header version is propagated. Missing
and null grouping metadata use distinct <absent> and <null> labels per field.
Headers are counted as their own record_type.
Shard capture_versions is the sorted set of explicitly present decoded values,
including null if explicit; missing versions add nothing to that set.
Each shard reports its path relative to --repo-root (default: the checkout holding the module; forward slashes; a shard outside that root is refused as path_outside_repo_root, exit 3, no artifact), bytes, resolution (not_applicable), lines,
rows (valid objects), unparseable_count, unparseable_lines (one-based line,
zero-based byte_offset, byte_length, reason, raw_repr), first_response_end_ts,
last_response_end_ts, and capture_versions. Reasons are invalid_utf8,
invalid_json, or non_object; raw_repr is repr(raw) truncated to 512 characters.
Timestamps are chronological extrema validated through parse_venue_time;
whole seconds use that parser and fractional digits are preserved separately
as integer nanoseconds. Original text is retained; equal instants use text
as a deterministic tie-break. Rejected non-null timestamps increment the shard's
invalid_response_end_ts count and append interpretation_failures with reason,
line, byte_offset, byte_length and raw_repr (repr(raw) truncated to 512).
They remain counted rows and fields, excluded only from the timestamp bounds.
Null or absent response_end_ts is counted only in the field null / absent class,
never invalid_response_end_ts, and excluded from bounds. Counts and bounds are
order-independent; line-anchored interpretation_failures and unparseable_lines
depend on input line order by design.
Blank, malformed, invalid UTF-8 and non-object lines are counted as unparseable;
none contributes to a group. Offsets include original newline bytes.
Input paths are resolved, deduplicated and sorted. Directories recurse through
*.jsonl. Missing paths and directories without JSONL files return exit 3 with
a reason. Empty files produce zero rows. Output is ASCII JSON; input overwrite
is refused. Output uses a sibling temporary file, flush, fsync and os.replace;
failure removes the temporary file and preserves the previous destination.
Memory retains one line, group counts and error offset metadata,
not the full shard or all decoded rows.

## Construct evidence and checks

Fixture: tests/platformkit/execution/fixtures/s406_kalshi_rows.jsonl
Size: 1408 bytes (LF); resolution: not_applicable. This is constructed data, not a
sample of any live capture. All 11 physical lines are processed: 10 valid object
rows and 1 unparseable line. The real_shape_construct version adds four ladders. Seven snapshot rows share local_capture_runner_v1;
the header and older_construct snapshot are separate groups. That snapshot
group's yes_bid counts are 1 integral, 2 fractional, 1 exponent, 1 string,
1 null and 1 absent; maximum fractional digits is 19, with 1 text exceeding 6.
Temporary test inputs cover cross-file unions, byte offsets, token provenance,
line iteration with a generator-only open, and CLI output and refusals.
Command: python -m pytest tests/platformkit/execution/test_kalshi_decimal_census.py -q -p no:cacheprovider
Original candidate's reported output: `10 passed in 0.67s` (historical;
superseded by the FIX 1b execution below).
Command: python -m scripts.platformkit.execution.kalshi_decimal_census --help
Result: exit 0, usage and notice printed.
Both round-1 independent verdicts were REJECT; their required fixes follow.
Self-check B: additive new files only; every line is accounted for; no deployment,
schema removal, selection filter, threshold change, or production integration.
Self-check Q: descriptive CONSTRUCT census only; no scored comparison, trial,
OOS result or fitted model. Q6 vocabulary applies throughout these artifacts.
Independent master reproduction remains outstanding; orchestrator counts below
are not a builder reproduction.

## FIX 1b
Local construct reproductions ran before module edits (BytesIO shards and an
injected destination writer); the added assertions first reported
`17 failed, 4 passed in 1.31s`.
1. Tier 1 #1 BLOCKING / tier 2 row-reversal CORRECTION: 02Z,01Z rows gave
   `reversal_equal= False`. Fixed chronological extrema keeping original text
   and sub-microsecond digits; test_reversed_rows_identical_artifact compares
   whole artifact bytes for ordinary reversal, zone offsets one nanosecond
   apart, and equal instants with distinct text.
2. Tier 1 #2 / tier 2 atomic-output BLOCKING: an injected third write and a
   serialization TypeError each gave `preserved= False`. Fixed sibling
   temporary output, flush, fsync, os.replace, cleanup and TypeError as exit 3.
   test_atomic_output_failure_and_order covers five injected failures with
   exact previous bytes kept, no temporary left, and flush < fsync < replace.
3. Tier 1 #3 BLOCKING: `notice_equal= False`; module, memo and test now use the
   binding notice verbatim (test_shard_metadata_and_offsets).
4. Tier 1 #4 CORRECTION: bad lines carried exception text and no raw_repr.
   Fixed bounded raw_repr and stable reason codes (test_bad_lines_byte_offsets_
   and_timestamp_order, test_parse_repr_truncation).
5. Tier 2 missing-identities BLOCKING: `identities= [(None, None, 2)]`. Fixed
   per-field <absent>/<null> labels (test_empty_file_and_missing_identity).
6. AMENDMENT 3(f): `ladder_fields= ['orderbook']`. Added positional ladder
   classification with exact token provenance
   (test_ladder_positions_exact_text_and_absence).
7. Tier 1 #5 / tier 2 memo CORRECTION: `not_verified_tail= '\n'` and a wrong
   fixture size. Corrected; the landed BEFORE record was left unchanged.
Only the row-owned kalshi_decimal_census.py changed; tests use constructs only.
After: `21 passed in 0.67s`; continuation 2026-09-23 `21 passed in 0.92s`;
--help exit 0 (no separate self-check CLI); the B/Q self-check applies.
Contract command:
```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/kalshi_decimal_census.py tests/platformkit/execution/test_kalshi_decimal_census.py tests/platformkit/execution/fixtures/s406_kalshi_rows.jsonl docs/evidence/harness/S406_kalshi_decimal_census_2026-09-22.md --base master --spec docs/evidence/tracking/specs/S406_spec.md
```
Result: nine PASS, zero FAIL: vocab, crlf, loc, schema, head_slice,
spec_threshold, proposed, removed_artifact, row_duplication.
Current lengths and ASCII checks are recorded in FIX 1d.
Read-only static review of the requested module/test fixes found no remaining
defects; that reviewer did not execute tests or review real artifacts.
Orchestrator-reported real re-run after FIX 1b (not reproduced by this builder;
2026-09-23 16:5xZ-17:0xZ, from the h67 candidate; the landed BEFORE record
docs/evidence/harness/S406_census_real_2026-09-22.md on master was made while the 2026-09-22 shards were still being
written, so its 446,648 pooled rows are a smaller prefix of the same day): (1) mlb shard alone --shards
data/cache/ingame_books_local/kalshi/mlb/2026-09-22.jsonl (359,982,871 bytes): exit 0, peak working set 80 MB, wall 43 s,
191,416 rows, 0 unparseable, 5 groups (snapshot 24,843 / snapshot_bulk 39,372 / trade 121,060 / trade_backfill_closed 5,900 /
trade_gap 241, all capture_version local_capture_runner_v1), first response_end_ts 2026-09-22T00:00:36.237368Z, last
2026-09-22T23:59:57.121905Z, artifact 47,265 bytes; (2) the four shards of the BEFORE record (mlb, nba, nfl, tennis): exit 0,
rows mlb 191,416 / nba 1,224 / nfl 148,245 / tennis 309,661 = 650,546, 0 unparseable, 5 groups, artifact 48,753 bytes.
AMENDMENT 5 supersedes the FIX 1b delivery passages; only the FIX 1c
forward/census paths and provenance below designate artifacts.
## FIX 1c
1. Tier 1 #1 BLOCKING / tier 2 timestamp BLOCKING, AMENDMENT 4(a): before edits,
   one row with response_end_ts "bad" and yes_bid 43 returned `exit=3,
   stderr='refused: invalid response_end_ts', artifact=False`; naive, empty and
   integer 123 timestamps failed the same way. Rejection now stays local to the
   bounds, with a named count and a bounded raw record. After: `exit=0, rows=1,
   invalid_response_end_ts=1, yes_bid=1, bounds=[None, None]`; three-row cases
   keep bounds 12:00:01Z / 12:00:02Z. The regression also covers a 512-character
   raw_repr, original bytes and offsets, and timestamps 100 nanoseconds apart.
2. Tier 2 memo CORRECTION / AMENDMENT 4(b): `scratch_label=True,
   artifact_paths=False, sha256=False, builder_scope=False` before; AMENDMENT 5
   supersedes the earlier path and hash statements; artifacts recorded below.
3. AMENDMENT 4 NOTES: empty-yes / no-[43,2,99] returned `empty_ladder_present=
   False, extra_cells_present=False`; after: `empty_ladder=1, extra_cells=1`.
Before the fix the per-file run returned `7 failed, 21 passed in 1.09s`; after:
`28 passed in 0.71s`. --help exit 0; preflight nine PASS, zero FAIL.
Historical original bytes from orchestrator real re-runs after FIX 1c (2026-09-23 18:2xZ, from the h67 candidate; AMENDMENT 4(b) as corrected by AMENDMENT 5: artifacts committed under docs/evidence/forward/census/ because docs/evidence/harness/ tracks only .md files):
  docs/evidence/forward/census/S406_census_real_2026-09-22_fix1c_mlb.json: 47338 bytes, sha256 424eb3dd25fb5a82472c603a56cda6738caa284c3843f7fda194f02d5d71a885; shards (sport, rows, unparseable, invalid_response_end_ts) [["mlb", 191416, 0, 0]]; rows total 191416; groups 5
  docs/evidence/forward/census/S406_census_real_2026-09-22_fix1c_4shards.json: 49045 bytes, sha256 7ae2cbd825ff4ed1f5dad691574b081fbc965f7ad554d3f87286673c0b273286; shards (sport, rows, unparseable, invalid_response_end_ts) [["mlb", 191416, 0, 0], ["nba", 1224, 0, 0], ["nfl", 148245, 0, 0], ["tennis", 309661, 0, 0]]; rows total 650546; groups 5

## FIX 1d

Before edits, new per-file regressions returned `12 failed in 0.79s`.
1. Tier 1 #1 BLOCKING: the real-shape probe returned only `book: other=1` and
   `yes_bid_top5_asc: other=1` (`KeyError: 'book.orderbook_fp.yes_dollars.price'`).
   Added traversal of all four AMENDMENT 6(a) locations with token provenance,
   empty ladders and extra cells, plus one real-shape fixture row.
2. Tier 2 C2: `no: "abc"` / `no: {"x":1}` returned only `orderbook: other=1`;
   named .non_list counts now cover every location (test_non_list_sides_are_named).
3. Tier 2 C3: null/object levels returned price/size `absent=1`; they now keep
   null/other (test_malformed_levels_keep_own_class).
4. Tier 1 #3 / tier 2 N2: `path_is_absolute= True`. Paths became relative to the
   module checkout (superseded by FIX 1e item 1); FIX 1c artifacts were
   reserialized with relative paths only, all other values asserted unchanged.
5. Tier 1 #2 / tier 2 C1: six stale-memo probes returned True; corrected and
   pinned by test_memo_corrections and test_existing_artifact_paths_are_relative.
Current FIX 1c bytes after path normalization (builder hashes; original hashes
above are historical, not current-file hashes):
- docs/evidence/forward/census/S406_census_real_2026-09-22_fix1c_4shards.json: 27493 bytes; SHA-256 bc8758ca8fdb60191fcecc48083134c0a3bac4dde13e310589b7bb9a54cbc056.
- docs/evidence/forward/census/S406_census_real_2026-09-22_fix1c_mlb.json: 26266 bytes; SHA-256 13dd2604d4ae75c29bcec65a5a3185c658525d82110e188db1b52dd7b0163a80.
Validation: existing file `28 passed in 0.63s`; FIX 1d file `12 passed in 0.59s`.
--help: exit 0; no separate self-check CLI. B/Q construct self-check holds.
Preflight: nine PASS, zero FAIL. Seven files ASCII and <=300 lines; Python LOC 262/299/101.
Orchestrator real re-runs after FIX 1d (2026-09-23 17:43:38Z-17:46:25Z, from the h67 candidate; AMENDMENT 6(a)) recorded
shard paths as "../nba-ai-system/data/cache/..." (outside the worktree root; see FIX 1e item 1). AMENDMENT 7(a): the orchestrator
regenerated both fix1d artifacts with --repo-root <main checkout> on 2026-09-23 18:02-18:05Z; recorded below.
  docs/evidence/forward/census/S406_census_real_2026-09-22_fix1d_mlb.json: 52324 bytes, sha256 625b8e4ebcc088ac89c0fe0fa7bae439397a63e4c5b1f6ddb0fbf2b48741c010; shards [path, rows, unparseable, invalid_response_end_ts] [["data/cache/ingame_books_local/kalshi/mlb/2026-09-22.jsonl", 191416, 0, 0]]; rows total 191416; groups 5
  docs/evidence/forward/census/S406_census_real_2026-09-22_fix1d_4shards.json: 53921 bytes, sha256 75feac4b4873cb412b2f6b9b0624de3ea18315fb18b1d5061b680af943f6396c; shards (path under data/cache/ingame_books_local/kalshi/<sport>/2026-09-22.jsonl, rows, unparseable, invalid_response_end_ts) mlb 191416 / nba 1224 / nfl 148245 / tennis 309661, 0, 0; rows total 650546; groups 5
  Ladder fields censused per artifact (14): the two top-level top-5 presence fields no_bid_top5_asc and yes_bid_top5_asc, and twelve per-position fields: .price, .size and .empty_ladder under book.orderbook_fp.yes_dollars, book.orderbook_fp.no_dollars, yes_bid_top5_asc and no_bid_top5_asc.
  READING (counts only): every row total equals the fix-1c run (191,416; 650,546; 0 unparseable; 0 invalid timestamps); the fix-1d artifacts add the per-position ladder classes the fix-1c artifacts lacked. The fix-1c artifacts stay as the BEFORE record (AMENDMENT 6).

## FIX 1e

Round 4: both Opus tiers ACCEPT WITH CORRECTIONS; AMENDMENT 7 rules on each item.
1. Tier 1 #1 / tier 2 C1 CORRECTION, AMENDMENT 7(a): before edits, a census of a
   scratchpad shard returned exit 0 with path
   `../AppData/Local/Temp/claude/.../scratchpad/a.jsonl`, and `--repo-root` gave
   `error: unrecognized arguments` (exit 2). Added optional --repo-root (default:
   the checkout holding the module). Every shard path is relpath(path, root) with
   forward slashes; a result starting with ".." (or a path on another drive) is
   refused before any scan: `refused: path_outside_repo_root: ...`, exit 3, no
   artifact. After: the same shard with --repo-root at its directory recorded
   `a.jsonl`; the orchestrator root maps the mlb shard to
   `data/cache/ingame_books_local/kalshi/mlb/2026-09-22.jsonl`.
   The fix1d artifacts were NOT regenerated by this builder (AMENDMENT 7(a)).
2. Tier 1 #2 CORRECTION, AMENDMENT 7(b): the artifact test globbed only fix1c.
   test_existing_artifact_paths_are_relative now globs S406*_fix1*_*.json,
   asserts 4 artifacts and data/cache/ paths; before regeneration it FAILS on
   the two fix1d artifacts (`'../nba-ai-system/data/cache/...'.startswith`),
   which is the defect it pins. Added test_outside_root_refused_by_name (CLI exit
   3, the name on stderr, no artifact; census() raises) and
   test_under_root_relative_form (`data/cache/x.jsonl`). The first test file
   pins its tmp_path constructs under the drive root with an autouse fixture.
3. Tier 1 #3 / tier 2 C2-C3 CORRECTION, AMENDMENT 7(c): memo was 305 lines,
   with a stale rerun bullet and a false repo-relative claim on the fix1d lines.
   Removed both, kept fix1c as the BEFORE record, condensed FIX 1b, and put
   placeholders on the fix1d byte and hash lines; the memo is <= 300 lines.
4. Tier 2 C4 CORRECTION, AMENDMENT 7(d): byte probes showed the module with 104
   of 262 lines CRLF and the fixture with 9 of 11 CRLF (1417-byte file). Both are
   now LF; the fixture is 1408 bytes. test_owned_files_are_lf pins module,
   fixture and memo.
5. Tier 2 N1-N2 / tier 1 N4-N5: the 14-field split (2 top-level, 12
   per-position), the mixed absent cases, the non-object orderbook_fp case and
   the null-level double count are spelled out in the counting rules above.
Validation: test_kalshi_decimal_census.py `28 passed`; FIX 1d file `15 passed` (after the orchestrator regenerated both fix1d artifacts with --repo-root on 2026-09-23 18:02-18:05Z from the candidate worktree; the one failure before regeneration was the artifact-path test); --help exit 0;
preflight nine PASS, zero FAIL; Python 3.10. Owned files ASCII, LF, <= 300 lines.

NOT VERIFIED
This list describes the builder's verification scope.
- The builder did not produce the real census or its hashes; the orchestrator
  did (above).
- Independent test execution and reproduction in master after FIX 1e.
- Real-shard values, timings, memory use and the landed BEFORE record
  docs/evidence/harness/S406_census_real_2026-09-22.md were not recomputed.
