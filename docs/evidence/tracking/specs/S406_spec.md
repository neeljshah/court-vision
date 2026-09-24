GAP S406 | sport all captured (venue) | worktree harness-h67 (master-based) | log cx_s406_kalshi_decimal_census
# Kalshi archive decimal census: which fields are floats, per producer version and record type (counts only; astra round 16 candidate 5)

SINGLE PROBLEM: the S398 probe over the real Kalshi mlb shard (2026-09-22) found the snapshot rows carrying FLOAT fields (yes_bid,
no_bid, yes_ask, no_ask, yes_bid_size, no_bid_size, depth_bid, depth_ask, minutes_to_close on all 233 rows of five tickers); the
landed decimal reader refused 45 of them ('expected a decimal string') and admitted the rest as integral floats. A float is not the
venue's number (the same defect S397 AMENDMENT 6 fixed on the Polymarket side). Before anyone changes the landed Kalshi writer, the
contamination must be MEASURED: which producer versions, which record types, which fields, how many rows, and how many bytes of
precision the float encoding could have lost -- without converting anything.

BINDING BEFORE-CONDITION: quote from master (a) the Kalshi snapshot row writer in scripts/platformkit/ingame/local_capture_runner.py
(the fields it writes and the JSON encoding of each -- quote the json.dumps call and any float() conversion); (b)
scripts/platformkit/execution/coherence_scanner_inputs.py decimal_value (what it admits: int, decimal text; what it refuses); (c)
scripts/platformkit/execution/capture_book_adapter.py (the fields it reads and its refusal dict); (d) the capture_version values
present in the shard header rows; (e) S398 AMENDMENT 6 (the measured facts above).

CHANGE (owned files: NEW scripts/platformkit/execution/kalshi_decimal_census.py, NEW
tests/platformkit/execution/test_kalshi_decimal_census.py, NEW tests/platformkit/execution/fixtures/s406_kalshi_rows.jsonl,
memo docs/evidence/harness/S406_kalshi_decimal_census_2026-09-22.md):
1. kalshi_decimal_census.py (<= 300 LOC): --shards <paths or archive directories> --out <json>. Streams every line (never loads a
   shard into memory; the mlb shard is 197 MB); for every row counts, keyed by (record_type, capture_version, field): the JSON
   type of the value as decoded with parse_float=str (so a JSON number with a fractional part or an exponent is distinguishable
   from an integer and from a string WITHOUT float rounding: json_type in {int, float_text, str, null, bool, other}); for
   float_text values: integral (the text has only zeros after the point) vs fractional, and the maximum number of fractional
   digits seen; for every field that the landed reader consumes (capture_book_adapter's list) the reader's verdict on the row
   (admitted / refused with the reason text) so the census reproduces the S398 refusal count; per shard: rows, unparseable
   lines (counted, bytes preserved by offset), first and last response_end_ts; original bytes never rewritten. Output: strict-int
   counts, ASCII JSON, plus the NOTICE 'counts only; nothing here converts a stored float to text or claims its original
   precision'. Refuses (exit 3, reason) a missing shard or a shard directory with no jsonl files.
2. Tests: fixture rows built from the real shapes (a snapshot row with float fields, one with int fields, one with text fields, a
   header row with capture_version, an unparseable line): the type census per field; integral vs fractional; the max fractional
   digits; the reader verdict counts equal to a direct call of the landed reader on the same rows; streaming (a 10,000-row
   construct through the same code path with a bounded-memory assertion is NOT required -- assert only that the file is read
   line by line, by monkeypatching open to a generator); order independence over files; the refusals.
3. Memo: before-condition quotes with file:line, the census schema, ends with NOT VERIFIED.

CONTROLS: PREPARE only -- construct tests; no network; no real shard run by the builder (the orchestrator runs it on the real mlb,
nba, nfl, tennis and soccer shards and records the counts); never edit local_capture_runner.py or any landed module (the writer
change is a later row, after this census); never touch the live captures or any STOP file. ACCEPTANCE: per-file tests pass one at
a time; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; memo ends with NOT VERIFIED.


AMENDMENT 1 (2026-09-22 19:1xZ; binding; the premise corrected after the first codex build lane stopped at the before-condition).
MEASURED BY THE LANE against master: coherence_scanner_inputs.decimal_value (line 19) accepts ONLY str and Decimal -- it rejects
int AND float; local_capture_runner_row.py:113 constructs snapshot prices and sizes as Decimal and local_capture_writer.py:15
serializes them as JSON NUMBERS (no binary-float conversion at write time); the json.dumps call lives in local_capture_writer.py.
Therefore the orchestrator's 'float fields' reading in S398 AMENDMENT 6 was an artifact of the PROBE's decoding (json.loads with
the default parse_float turns every JSON number into a float); the archive holds the Decimal's number text. The S398 scan's 45
refusals are then explained by the READER: a JSON number written WITHOUT a fractional part (an integral Decimal such as 43)
decodes as int under any parse_int default and decimal_value rejects int; a number with a fractional part decodes as str only
when the reader passes parse_float=str (quote coherence_scanner_inputs.read_rows's exact json.loads arguments in the memo).
RE-SCOPED CHANGE (counts only, still nothing converted): the census decodes every line ONCE with parse_float=str and
parse_int=str (so every JSON number arrives as its exact text) and classifies, per (record_type, capture_version, field):
number_integral_text (no point, no exponent), number_fractional_text (with the max fractional digits seen and a count of texts
whose fractional digits exceed 6 -- evidence of a float-origin Decimal such as 0.4300000000000000155), number_exponent_text,
string, null, bool, other; then, for every field capture_book_adapter consumes, the verdict of the LANDED reader path exactly
as cross_venue_scan / coherence_scanner_inputs would see it (decode the same line with read_rows's own arguments and call
decimal_value), reproducing the 45-row refusal with its reason text; per shard rows, unparseable lines, first / last
response_end_ts. The before-condition quotes are the three lines above plus read_rows. The reader change that would admit an
integral JSON number as an exact decimal is NOT this row (allocated separately after the census); cross_venue_scan.py is the
unlanded S398 candidate and is not an input here.


AMENDMENT 2 (2026-09-22 19:2xZ; binding; the second codex lane stopped correctly again). MEASURED BY THE LANE: read_rows decodes
with json.loads(line, parse_float=Decimal, parse_int=Decimal, parse_constant=Decimal) (coherence_scanner_inputs.py:213), so an
integral JSON number reaches decimal_value as a Decimal and is ADMITTED; the landed reader path therefore cannot reproduce the
45 refusals, and AMENDMENT 1's reader explanation is withdrawn. The 45 rows were refused by the UNLANDED S398 candidate's own
quote() (cross_venue_scan.py, not an input here) with decimal_value's message for a value that is neither str nor Decimal --
most plausibly a null field (a snapshot row with no NO-side book, or an older capture_version lacking a field). RULING: this row
does NOT reproduce any refusal through any reader. The census is the TEXT CLASS census only, decoded once with parse_float=str,
parse_int=str, parse_constant=str: per (record_type, capture_version, field) -> number_integral_text, number_fractional_text (max
fractional digits; count with more than 6), number_exponent_text, string, null, ABSENT (the field missing from the row), bool,
other; plus the per-shard rows, unparseable lines with byte offsets, first / last response_end_ts, and the set of
capture_version values seen. The S398 memo attributes its 45 refusals by field from this census's null / absent counts. Before-
condition quotes: read_rows line 213 (verbatim), decimal_value line 19, local_capture_runner_row.py:113, local_capture_writer.py:15.
Everything else in CHANGE items 1-3 stands (streaming, strict-int counts, NOTICE, exit 3 on a missing shard, tests, memo).

AMENDMENT 3 (2026-09-23 16:5xZ; binding; from the round-1 verification of the third build -- sol REJECT (three blockers) and
astra REJECT (two blockers), every item MEASURED on constructs). (a) ATOMIC WRITE: kalshi_decimal_census.py:161 opens the
destination with "w"; an injected serialization failure left partial JSON and the previous artifact was not preserved.
RULING: sibling temp file + flush + fsync + os.replace; on failure the temp is removed and a pre-existing destination is
byte-identical; tested with an injected failure. (b) CHRONOLOGICAL FIRST / LAST: input 02Z,01Z gave first 02Z / last 01Z
(:112); reversed rows changed bytes. RULING: first and last are the chronological minimum and maximum through parse_venue_time
(the original timestamp TEXT retained); reversed-row test pins byte identity. (c) THE NOTICE IS VERBATIM: the constant at :11
says 'stored number'; the binding text is 'counts only; nothing here converts a stored float to text or claims its original
precision' -- fix the constant, memo and test. (d) MISSING AND NULL IDENTITIES ARE DISTINCT GROUPS: {} and {"record_type":
null, "capture_version": null} merged into one (None, None) group (:117); the producer identity field is capture_version.
RULING: an absent key groups as "<absent>" and an explicit null as "<null>", per field, never merged. (e) UNPARSEABLE RECORDS
CARRY repr: add raw_repr (repr truncated to 512 characters) and stable reasons invalid_utf8 / invalid_json / non_object,
asserted explicitly. (f) LADDER CONTENTS ARE CENSUSED BY POSITION: orderbook yes / no arrays were counted once as 'other'
(:124). RULING: each [price, size] level's price text and size text are classified and counted under orderbook.yes.price,
orderbook.yes.size, orderbook.no.price, orderbook.no.size (per producer version and record type), never lumped. (g) Memo:
the NOT VERIFIED heading gets its list (the real-shard run, independent test execution, real artifact values); the fixture
size is the actual 1180 bytes. The landed real census record docs/evidence/harness/S406_census_real_2026-09-22.md stays as
the BEFORE record; the fix's real re-run by the orchestrator is recorded beside it.

AMENDMENT 4 (2026-09-23 17:5xZ; binding; from round 2 on fix 1b -- codex astra REJECT and codex sol REJECT on the SAME single blocker;
sol confirmed every AMENDMENT 3 item closed on constructs). (a) ONE INVALID TIMESTAMP MUST NOT ABORT THE CENSUS: three-row constructs with a
naive timestamp, an empty string, or the integer 123 in response_end_ts returned exit 3 'refused: invalid response_end_ts' and
no report (kalshi_decimal_census.py:160); the spec's accounting rule ('a row the report cannot interpret is counted under a
named reason with its raw text recorded, never dropped') applies to a field the census cannot interpret as much as to a line it
cannot parse. RULING: a row whose response_end_ts parse_venue_time refuses is COUNTED under invalid_response_end_ts (with
raw_repr truncated to 512) and excluded from the first / last bounds only; the census continues; exit 3 is reserved for a
missing shard or an unwritable artifact; a construct with one bad timestamp among three rows yields a report with rows 3,
invalid_response_end_ts 1, and bounds over the two good rows. (b) The orchestrator's real-run artifacts are committed beside
the memo at landing as docs/evidence/harness/S406_census_real_2026-09-22_fix1b_mlb.json and _4shards.json with their SHA-256
recorded in the memo (identifiable evidence, never 'scratch'); the memo states that its NOT VERIFIED list describes the
builder's verification scope. NOTES: an empty ladder is counted under orderbook.empty_ladder by name (not only orderbook.other);
a level with more than two cells counts the extra cells as orderbook.<side>.extra_cells; bare-token inputs and the
absent / null / empty-string grouping reproduced as designed.

AMENDMENT 5 (2026-09-23 18:3xZ; binding; path correction to AMENDMENT 4(b)). docs/evidence/harness/** is gitignored except
.md (the landed BEFORE record's JSON was never tracked either), so the orchestrator's real-run artifacts are committed at
docs/evidence/forward/census/S406_census_real_2026-09-22_fix1c_mlb.json and _4shards.json (counts of number-text classes only;
no price values) with their SHA-256 in the memo; the memo names those paths.

AMENDMENT 6 (2026-09-23 18:5xZ; binding; from round 3 on fix 1c -- Opus tier 1 REJECT and Opus tier 2 ACCEPT WITH CORRECTIONS; tier 2
confirmed the AMENDMENT 4 closures, the artifact hashes and the 73-byte-per-shard delta versus fix 1b). Tier 1 confirmed every AMENDMENT 4 closure on constructs (naive / empty / integer / NaN / list / 900-character
timestamps each counted invalid_response_end_ts 1 with bounds over the good rows; exit 3 only for a missing shard or an
unwritable output; the committed artifacts' SHA-256 and row totals reconciled) and found ONE blocker FROM THE REAL ARTIFACT:
(a) THE LADDER CENSUS NEVER RAN ON REAL ROWS: kalshi_decimal_census.py:97 reads a top-level `orderbook` key that no real Kalshi
row carries -- the writer stores ladders under `book.orderbook_fp.yes_dollars` / `.no_dollars` as [[price_text, size_text], ...]
(local_capture_runner_row.py:63) and the top-5 arrays under `yes_bid_top5_asc` / `no_bid_top5_asc`; the committed fix1c_mlb.json
shows zero orderbook.* fields and `book`, `yes_bid_top5_asc`, `no_bid_top5_asc` each {'other': 24843} -- the very lumping
AMENDMENT 3(f) forbade, on every real snapshot row. RULING: the ladder census classifies cells BY POSITION at the REAL locations,
under book.orderbook_fp.yes_dollars.price / .size, book.orderbook_fp.no_dollars.price / .size, yes_bid_top5_asc.price / .size and
no_bid_top5_asc.price / .size (per producer version and record type), keeping empty_ladder and extra_cells; the fixture gains a
row in the real shape (a construct built from the real key layout, never a real row); the real census is run again and the
AFTER artifacts committed. (b) REPO-RELATIVE PATHS IN COMMITTED ARTIFACTS: shards[].path (emitted at :136) carries absolute
local paths, and docs/evidence/forward/ is exported publicly through the allowlist's `+ docs/`; every path an artifact under
docs/ records is repo-relative (resolved from the repo root), and the artifacts are regenerated. (c) The memo is made
self-consistent: line 3 cites AMENDMENTS 2-6, the fix1b passages that name docs/evidence/harness/ paths and 'SHA-256 NOT
AVAILABLE' / 'BLOCKED' are superseded by the AMENDMENT 5 paths and hashes, the NOT VERIFIED entry about outstanding fix1b
artifacts is removed, the gitignored _verdict file is not cited, and a null or absent response_end_ts is stated to be left out
of the bounds and counted only in the field's null / absent class (AMENDMENT 4(a) as implemented).
(d) Tier 2's corrections: a non-list ladder side ('no': 'abc' or a dict) is counted by name orderbook.<side>.non_list, never
left as the top-level field's 'other'; a null or non-list LEVEL is classified by its own value (null / other), never as
the ABSENT of a row with no ladder; an explicit null response_end_ts is stated in the memo to be counted in the field's
null class and left out of the bounds (never invalid_response_end_ts); the memo's '238/277 lines' sentence is corrected to
the current counts. The evidence lists (interpretation_failures, unparseable_lines) carry line numbers by design and are
the only order-dependent part of the artifact; counts and bounds are order-independent (stated in the memo).

AMENDMENT 7 (2026-09-23 20:0xZ; binding; from round 4 on fix 1d -- Opus tier 1 ACCEPT WITH CORRECTIONS; the tier 2 verdict is folded
in below when it arrives). Tier 1 confirmed AMENDMENT 6(a) on the committed artifacts (14 ladder fields per shard; in the mlb
snapshot group 897,542 yes-side and 903,266 no-side orderbook_fp cells classified as string text, 100,238 / 100,237 top-5 cells as
fractional number text with at most 4 price and 2 size digits; absent plus empty-ladder rows summing to 24,843; every non-ladder
field identical to fix 1c; the AMENDMENT 3-4 closures unregressed). ONE CORRECTION, RULED: (a) THE RELATIVE PATH MUST NEVER LEAVE THE
ROOT: the orchestrator runs the census FROM THE WORKTREE against data under the main tree, so os.path.relpath(path, REPO_ROOT) at
:144 wrote "../nba-ai-system/data/cache/..." into both fix1d artifacts (memo line 295 'paths are repo-relative' is untrue). RULING:
an optional CLI flag --repo-root (default: the checkout root the module lives in); every recorded path is relpath(path, repo_root)
with forward slashes; a result beginning with ".." is REFUSED by name (path_outside_repo_root, exit 3, no artifact); the
orchestrator's real runs carry --repo-root C:/Users/neelj/nba-ai-system so the committed artifacts read data/cache/...; both
fix1d artifacts are regenerated and re-hashed and the memo lines 293-295 updated. (b) test_kalshi_decimal_census_fix1d.py:95
looks at every S406*_fix1*_*.json artifact (asserting the count) and adds the outside-root refusal and the under-root relative
form. (c) The memo's NOT VERIFIED item saying the orchestrator must still re-run is removed (the re-run is recorded), and the memo
is trimmed to <= 300 lines. NOTES kept as the memo's wording: ladder price / size classes count CELLS while absent counts ROWS
(memo :88); the top-level book and top-5 fields' 'other' 24,843 is a presence count beside the per-cell classes.
