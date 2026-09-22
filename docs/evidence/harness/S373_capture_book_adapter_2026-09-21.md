# S373 capture book adapter -- fixture checks PASS

Vocabulary follows contract Q6; automated scan required.

Scope: audit finding 4; local construct and supplied-fixture checks only.
The adapter is new and opt-in. No existing consumer or public signature changed.
The supplied six-row fixture remains verbatim. No runtime caller was installed.

Authority: docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md, finding 4:

> **BLOCKING ? captured books do not match any downstream schema.**
> Repro: an actual `book_row` yielded `missing_book_clock` from quoting and
> `no_tick_in_window` from mark selection; it has `response_end_ts/yes_bid`, not
> `src_ts/best_bid_cents/yes_home_prob/ts`.
> **Fix:** add one tested capture-book adapter using `response_end_ts`, Decimal
> conversions, and explicit YES-bid/YES-ask/NO-side mapping.

Read contract B and Q and S343/S344/S345/S354/S356/S357, including amendments.
All existing reason codes and schemas remain unchanged. This row adds three
functions in scripts/platformkit/execution/capture_book_adapter.py, covered by
tests/platformkit/execution/test_capture_book_adapter.py. Fixture:
tests/platformkit/execution/fixtures/s341_real_snapshots_2026-09-21.jsonl.

Before implementation, each supplied row was passed directly to make_quotes,
resolve_marks and simulate_fills. The latter used a construct resting quote;
the mark window began at the row's response end. Actual failing output:

```text
BEFORE row=0 quote=missing_book_clock mark=no_tick_in_window
BEFORE row=0 fill=KeyError('ts')
BEFORE row=1 quote=missing_book_clock mark=no_tick_in_window
BEFORE row=1 fill=KeyError('ts')
BEFORE row=2 quote=missing_book_clock mark=no_tick_in_window
BEFORE row=2 fill=KeyError('ts')
BEFORE row=3 quote=missing_book_clock mark=no_tick_in_window
BEFORE row=3 fill=KeyError('ts')
BEFORE row=4 quote=missing_book_clock mark=no_tick_in_window
BEFORE row=4 fill=KeyError('ts')
BEFORE row=5 quote=missing_book_clock mark=no_tick_in_window
BEFORE row=5 fill=KeyError('ts')
```

After adaptation, the same quote and mark consumers succeeded. Construct
touch prints additionally verified the exact queue size and fractional fill
on BOTH sides for every fixture. Actual passing output:

```text
AFTER row=0 quote=quoted mark=selected fill=usable_yes_and_no
AFTER row=1 quote=quoted mark=selected fill=usable_yes_and_no
AFTER row=2 quote=quoted mark=selected fill=usable_yes_and_no
AFTER row=3 quote=quoted mark=selected fill=usable_yes_and_no
AFTER row=4 quote=quoted mark=selected fill=usable_yes_and_no
AFTER row=5 quote=quoted mark=selected fill=usable_yes_and_no
```

The test file retains the original schema-failure reproduction and the fixed
integration cases. All six supplied rows are two-sided and convert without
refusal. No fixture row is excluded. Construct one-sided books assert the
specific one_sided_book refusal; crossed and locked books also refuse.

Availability is response_end_ts ONLY, parsed by venue_time.parse_venue_time
and formatted as an aware UTC string with six fractional digits. This also
serves the existing consumers that use Python 3.10 ISO parsing. Other capture
or scheduling fields never supply a fallback clock. Midpoints use Decimal
probability units; quote and fill prices use Decimal cents, strictly inside
(0, 100). No prices are rounded to a tick. Displayed sizes accept strings,
integers or Decimal; float sizes are refused. Float capture prices are read
through their decimal string representation because the supplied JSON contains
numeric derived prices; raw fixed-point prices are checked too.

The YES and NO fill ladders both contain resting bids. A NO bid at p maps to
a YES ask at 100-p. Raw yes_bid_size_fp overrides the matching YES touch size;
raw yes_ask_size_fp overrides the complementary NO touch size. Deeper levels
retain their own ladder sizes. An absent raw size falls back to a known ladder
size; when neither exists the level is omitted, retaining the simulator's
unknown-queue policy. Explicit zero remains distinct from missing. Conflicting
touch prices and duplicate levels with differing sizes refuse. Validation and
output sorting are deterministic, including malformed input order.

Suspension and terminal metadata and supplied game_id are carried through.
book_age_sec is Decimal zero at capture; unchanged mids remain usable marks.
Refusals contain reason, refused=True and refusal_count=1. Every caught parsing
exception is re-raised or counted at that boundary. Inputs are not mutated.
Consumer outputs retain their existing serialization behavior; the adapter's
in-memory Decimal payload is intentionally passed directly to the consumers.

Validation command (one file, no cache provider):
`python -m pytest tests/platformkit/execution/test_capture_book_adapter.py -q -p no:cacheprovider`

Actual progression: `97 passed in 0.91s`; expanded review regressions then
reported `11 failed, 105 passed in 1.53s`. The failing assertions exposed
order-dependent malformed ladders and unchecked raw touch prices. Both module
paths were corrected; the final expanded run reported `116 passed in 0.93s`.
No prior test was weakened. Only this new module was touched, with one test file.

Contract preflight uses all four deliverable paths, --base master and
--spec docs/evidence/tracking/specs/S373_spec.md. Actual output (all nine pass):

```text
PASS vocab clean over 4 files
PASS crlf no index-side CRLF over 4 file(s); 4 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 5 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

Infrastructure only: no scored comparison, trial, or threshold edit.

## FIX 1b

Binding inputs: root verifier verdict and S373_spec.md; the worktree spec and
`git show master:docs/evidence/tracking/specs/S373_spec.md` contain no amendments.
All checks in this fix pass ran locally in nba-harness-h31.

Finding 1 (BLOCKING): a positive Decimal price underflowed to zero during
scaling. `_price` now checks the scaled result for finiteness and requires
strictly 0 < result < 100, retaining the existing refusal reason codes.
The price-refusal parameter list now includes `1e-999999999` for all three
adapters. No mapping, size, clock, fixture, or consumer behavior was edited.

The verifier's exact minimal input was reproduced before changing the module:

```python
row = {"ticker": "T", "response_end_ts": "2026-09-21T00:00:00Z",
       "yes_bid": "1e-999999999", "yes_ask": "0.51"}
result = to_quote_book(row)
assert result == {"refused": True, "reason": "price_out_of_range", "refusal_count": 1}
```

Failing output (exit 1):

```text
AssertionError: {'src_ts': '2026-09-21T00:00:00.000000+00:00', 'best_bid_cents': Decimal('0E-1000026'), 'best_ask_cents': Decimal('51.00')}
```

The per-file regression run before the module fix reported:

```text
E       AssertionError: assert 'inconsistent_touch' == 'price_out_of_range'
3 failed, 116 passed in 2.08s
```

After the module fix, the identical minimal reproduction passed (exit 0):

```text
{'refused': True, 'reason': 'price_out_of_range', 'refusal_count': 1}
PASS minimal reproduction: 1/1
```

The same per-file command documented above then reported:

```text
119 passed in 0.98s
```

Finding 2 (NOTE): the verifier confirmed YES/NO mapping and all six mirrored
fixtures. No change was requested or made to these paths.
Finding 3 (NOTE): the verifier reported unrelated temporary-directory setup
limitations. No change was requested or made; this local test run needed no
collection isolation or temporary-directory workaround.
The row module is a pure-function library with no CLI, --help, or self-check
entry point; its per-file tests are the executable row checks.

NOT VERIFIED:
- Live capture completeness, queue position, cancellation ordering or fills.
- Runtime adoption of this opt-in adapter; no service or pod was used.
- Python 3.12 execution; the shared parser and fixture checks ran locally.
- Other audit findings, including downstream identity and fee behavior.
- Landing and commit creation; files remain on disk for lane_commit.
