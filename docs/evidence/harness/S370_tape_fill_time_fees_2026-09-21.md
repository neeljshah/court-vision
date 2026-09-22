# S370: tape fill time and fee input guards

Implemented and locally verified with constructed cases and the existing fixture.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h28, Python 3.10.0.
Local execution is sufficient for these deterministic boundary checks.
No archive, network, or pod access; no scored comparison or measured market result.
Vocabulary follows contract Q6; automated scan required.

Authority: docs/evidence/tracking/specs/S370_spec.md and
docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q. Read S343,
S344 (including amendments 1-3), S345 (including amendments 1-2), S354,
S356, and S357 before editing. Their applicable contracts remain binding.

## Audit findings and before evidence

Source: docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md.
Finding 5: "one venue-time path remains Python-version dependent."
Its reproduction text: "Repro on Python 3.10:
`_ts("2026-09-21T19:20:51.1492Z")` raised `ValueError`; shared
`parse_venue_time` returned `1790018451.1492`."
Finding 7b, the maker-fee portion of finding 7:
"maker fees returned `0.0` for both bad size and bad price."

Before any module edit, ran `_ts(s)` and `parse_venue_time(s)` with
`s = "2026-09-21T19:20:51.1492Z"`; then called
`fee_kalshi_maker("bad", "0.5")` and `fee_kalshi_maker("10", "bad")`.
The exception was caught and printed in this reproduction only:

```text
FAIL simulator: ValueError Invalid isoformat string: '2026-09-21T19:20:51.1492+00:00'
shared: 1790018451.1492
FAIL invalid fee inputs: bad 0.5 returned 0.0
FAIL invalid fee inputs: 10 bad returned 0.0
```

The initial new regression file was also run before the module edit. It had
fifty-four failures and four passes. The timestamp trace included:

```text
E           ValueError: Invalid isoformat string: '2026-09-21T19:20:51.1492+00:00'
```

## Changes and compatibility

Only scripts/platformkit/execution/tape_fill_sim.py, its new regression file
tests/platformkit/execution/test_tape_fill_time_fees.py, and this required memo
are changed. The original simulator test file already has 300 lines.

`_ts` delegates to execution.venue_time.parse_venue_time. Quote submit and
present cancel times, book times, and normalized print times use that parser.
Invalid values refuse the affected record and count a reason. A missing
submit time is refused. An absent cancel_ts means no requested cancellation;
a present None is invalid, never an open-ended live window. A replacement
whose predecessor was refused is also refused and counted, in time order.

Fee calls require finite positive Decimal cumulative size and integer cents
in 1..99. Decimal.is_finite and math.isfinite reject nonfinite values and
finite Decimals outside the fee module's representable range. Quote prices
are normalized to integer cents before validation. Invalid print sizes and
prices are rejected before arithmetic or duplicate identity consumption.
Immediately before a fee call, cumulative size and price are revalidated;
refusal counts fee_input_invalid without consuming the candidate fill quantity.
Quote and book sizes supplied as binary floats are refused; normalized print
sizes must already be Decimal. Exact quantity arithmetic remains Decimal.

The fee function receives cumulative filled size as a Decimal, including
fractional fills. venue_fees coerces that argument to float internally.
Each fill carries fee(cumulative size, limit price) minus the fee already
charged to that order. The existing numeric fee_units field and fee schedule
identifier stay unchanged. Two constructed fills of 9.47 and 0.53 contracts
retain their exact sizes and total the whole-order fee.

Owner finding: venue_fees.fee_kalshi_maker still returns 0.0 for unparseable
size or price. It was not edited. The simulator now validates inputs before
trusting that function; this row does not claim to fix its other callers.

Existing public signatures, fill/unfilled fields, and diagnostic keys remain.
Additional diagnostic counters appear only when nonzero:
quote_submit_ts_invalid, quote_cancel_ts_invalid, book_time_invalid,
print_time_invalid, fee_input_invalid, replacement_refused,
book_size_invalid, and size_parse_invalid. The last counts failed parsing
during precision selection; book_size_invalid counts failed book-size reads
for each quote's eligible latest snapshots. Existing unscored_prints still
counts refused prints. No existing reason string was renamed.

Conflicting valid duplicate prints are ordered by venue time, identity,
ticker, side, price, and Decimal count before identity consumption. Identical
duplicates retain the existing counted deduplication. Invalid rows never
consume identity. Latest-book refusal counts are independent of input order.
No input is mutated. Valid outputs remain JSON-serializable with size strings.

Reader survey found simulator calls in test_tape_fill_sim.py and
test_fractional_chain.py; no production simulate_fills caller was found.
execution/replay_units.py consumes the existing fill fields unchanged, and
execution/markout_causal.py consumes the converted fee schedule identifier.
No production reader of simulator diagnostics was found.

## After evidence

Re-ran the timestamp reproduction and constructed invalid-input simulations:

```text
PASS simulator: 1790018451.1492 shared: 1790018451.1492
PASS simulator invalid input: fills= 0 fee_input_invalid= 1
PASS simulator invalid input: fills= 0 fee_input_invalid= 1
Owner finding unchanged: 0.0 0.0
```

Every pytest command ran one file at a time with
`python -m pytest <file> -q -p no:cacheprovider` and bytecode writes disabled.
Final results:

| File under tests/platformkit/execution/ | Quoted output |
| --- | --- |
| test_tape_fill_time_fees.py | 63 passed in 0.69s |
| test_tape_fill_sim.py | 71 passed in 0.68s |
| test_fractional_chain.py | 26 passed in 0.72s |
| test_tape_fill_adapters.py | 52 passed in 0.72s |

The new cases cover fractional times, malformed/missing/nonfinite times,
invalid fee size and price, cumulative overflow, whole-order fractional fees,
replacement refusal, duplicate identity, and input permutations. The adapter
tests exercise every row of the committed eight-row fixture. No existing test
was weakened or rewritten. A separate read-only diff review found no blocker.
Fixture input: C:/Users/neelj/nba-harness-h28/tests/platformkit/execution/fixtures/s341_real_trades_2026-09-21.jsonl,
5184 bytes; resolution not applicable (JSONL). All other test data is constructed
inline in the named test files; no external dataset was opened.

Ran `python -m scripts.platformkit.tracking.contract_preflight --paths
scripts/platformkit/execution/tape_fill_sim.py
tests/platformkit/execution/test_tape_fill_time_fees.py
docs/evidence/harness/S370_tape_fill_time_fees_2026-09-21.md
--base master --spec docs/evidence/tracking/specs/S370_spec.md`:

```text
PASS vocab clean over 3 files
PASS crlf no index-side CRLF over 3 file(s); 2 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 4 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

ASCII decoding passed for all three changed files. The module has 270 lines
and the new test file has 164. `git diff --check` exited 0. Final git status
listed only the three owned paths. No commit was created in this sandbox.

Contract checks: no scored comparison, ledger charge, corpus claim, threshold
change, deployment, renamed field, or retired module. B/Q clauses concerning
those operations are not exercised. No data or registry writes or flag changes.

## FIX 1b (historical verification)

Binding review: _verdict_s370_1b.md, finding 1 (BLOCKING); no CORRECTION.
Zero returned fees, including real Decimal("1e-1000") underflow, were accepted.
Before: `mock_zero fills= 1 fees= [0.0] fee_input_invalid= 0` and
`real_underflow fills= 1 fees= [0.0] fee_input_invalid= 0`.
The regression run before the module edit reported `24 failed, 64 passed`.
Added finite-positive returned-fee validation and a counted exception boundary.
After: `mock_zero fills= 0 fees= [] fee_input_invalid= 1` and
`real_underflow fills= 0 fees= [] fee_input_invalid= 1`.
The 25 added cases covered invalid returns, underflow, exceptions, continuation,
and a positive unchanged cumulative fee producing a zero incremental fee.
Findings 2/3 were NOTE; confirmed behavior was retained.
Per-file results: test_tape_fill_time_fees.py `88 passed in 1.07s`;
test_tape_fill_sim.py `71 passed in 0.98s`. Both module commands exited 0;
contract_preflight: nine PASS, zero FAIL. No commit was created.

## FIX 1c (historical verification)

Binding review: _verdict_s370_1c.md, finding 1 (BLOCKING); no CORRECTION.
Touch queue depletion consumed trade budget before fee validation.
Reproduction: a_queue=5, b_queue=0, budget=10, fees=[0.0,0.05];
quotes a/b submit at 10/11, snapshots at 9/10.5, touch print at 12.
Before: `fills=[('b', '5')]`, `fee_input_invalid=1`;
regression run: `3 failed, 91 passed in 1.07s`.
Prospective queue, budget and external-volume state now remain local until
fee validation; queue-only prints retain their existing behavior.
After: `fills=[('b', '10')]`, `fee_input_invalid=1`.
Continuation tests cover touch/through, zero/nonzero queues, invalid returns
and exceptions, and quote/print permutations. Findings 2/3 needed no fixes.
Per-file results: test_tape_fill_time_fees.py `94 passed in 0.71s`;
test_tape_fill_sim.py `71 passed in 0.65s`. Both module commands exited 0;
contract_preflight: nine PASS, zero FAIL. No commit was created.

## FIX 1d

Binding review: _verdict_s370_1d.md. Finding 1 is BLOCKING; no CORRECTION.
Local and master specs were read; neither contains AMENDMENT blocks.
All work ran locally in C:/Users/neelj/nba-harness-h28.

Finding 1: returned Decimal fees crashed during subtraction after state was
committed, and decreasing positive cumulative fees produced negative charges.
Before editing the module, ran both minimal reproductions with a price-50,
ten-contract quote submitted at 10 and through prints at 12/13:

```text
decimal TypeError: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'
decreasing fills=[('5', 0.05), ('5', -0.04)] refusals=0
```

Inputs were respectively [Decimal("0.05")] for one ten-contract fill and
[0.05, 0.01] for two five-contract fills. The new per-file regressions ran
before the module edit: `8 failed, 99 passed in 1.68s`.

Exact fix: reject booleans and nonnumeric returns; normalize int/float/Decimal
returns locally to Decimal. Require Decimal.is_finite, math.isfinite, positive
value, and cumulative fee >= prior fee. Prior fee starts as Decimal(0).
Price passed to the fee function is now Decimal. Fee comparisons, cumulative
state, subtraction and rounding use Decimal. Prepare fee_units and the complete
record inside the counted exception boundary, before committing queue, budget,
remaining, filled, fee or the fill list. Any preparation exception counts
fee_input_invalid. The final fee_units field retains its existing JSON number
conversion for compatibility; it is never fed back into fee arithmetic.
The unedited venue fee implementation still converts inputs internally.

Added 15 constructed cases: four invalid return types; five positive/mixed
numeric-return sequences; four decreasing-fee touch/through cases (including
a difference below binary-float precision); two preparation-failure cases.
Continuation checks assert preserved remaining quantity, cumulative fee-call
inputs, shared budget and queue state. All print permutations are checked for
decreasing-fee continuation. Equal positive cumulative fees remain accepted.
During test authoring, a misplaced assertion caused two NameError failures;
it was restored to its original test before the final passing run.
Findings 2 and 3 are NOTE: prospective queue handling and shared timestamp
parsing were left intact. No adapters, fee module, or other modules changed.

The same minimal reproductions now assert their complete expected outcomes:

```text
decimal fills=[('10', 0.05)] refusals=0
decreasing fills=[('5', 0.05)] refusals=1
PASS both minimal reproductions
```

Final per-file runs, separately with `-q -p no:cacheprovider`:
- test_tape_fill_time_fees.py: `109 passed in 0.99s`.
- test_tape_fill_sim.py: `71 passed in 0.84s`.
PYTHONDONTWRITEBYTECODE=1; TEMP/TMP pointed inside this worktree.
Both `python -m scripts.platformkit.execution.tape_fill_sim --help` and
`python -m scripts.platformkit.execution.tape_fill_sim` exited 0.
The module has no help parser; both invoke its existing _demo self-check.
Construct/fixture checks only; no archive, network, pod, or scored result.

The recorded contract_preflight command passed all nine checks, zero FAIL,
over the three owned paths, excluding the verdict. ASCII/line checks passed:
module 284, regression file 293, memo 260 lines. `git diff --check` passed.
Git status contains only those three owned paths. No commit was created.
NOT VERIFIED remains the final section.

## NOT VERIFIED

- The fee module's invalid-input behavior for other callers; assigned to its owner.
- Execution on another Python version; this run used Python 3.10.0.
- Real archive completeness, live queue position, cancellation ordering, or live fills.
- Current venue fee exceptions, eligibility, and internal float-coercion precision.
- Pod execution, deployment, and commit creation; files remain on disk for lane_commit.
