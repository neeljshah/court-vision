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
