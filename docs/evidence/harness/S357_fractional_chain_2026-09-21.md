# S357 fractional chain

ACCEPT for local CONSTRUCT and fixture checks; master verification and landing remain pending.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h15, CPU only.
Vocabulary follows contract Q6; automated scan required.

## Binding before-condition (before edits)

Fresh calls to append_event and make_quotes produced exactly:

```text
(a) append qty "0.53": ValueError: invalid or missing qty
(b) make_quotes inventory 0.53: {'pulled': 'invalid_inventory', 'unresolved_inventory': 0.53}
```

The append used a temporary directory in this worktree. The quote used a fresh
49/51 book, observed-mid anchor, positive rooms, and an open market clock.

## Implementation and retained behavior

The five required modules are edited. Quantities and accounting use Decimal
internally; public quantity/accounting fields are strings and serialize with
json.dumps. Fill input accepts strings or integers, rejects floats and more
than two fractional digits. Order events require positive whole quantities;
integer-valued strings support JSON replay. Schema validation runs at append,
read_events, and reducer replay. Cumulative fills cannot exceed a declared
intent/submit/ack size; errors on replay name the line. Existing fill-only
streams remain supported, with declared_qty=False until a declaration arrives.
Their observed cumulative size is recorded, without inventing an original size.

The row-owned helper scripts/platformkit/execution/position_decimal.py holds
parsing and JSON representation functions to keep every file within 300 lines.
It does not convert price units. replay_units.py is below its 150-line limit.

Average-cost reduction, exact flattening, reversal, mirrored NO-first accounting,
fill_id-only deduplication, schema rejection, restart equality, cancellation
uncertainty, and incremental fee buckets retain their regression assertions.
Live Decimal subtrees are serialized with json_values before replay comparison.
Non-finite or out-of-range mids remain unmarked and excluded from aggregates;
mid units are YES cents, strictly between zero and 100.

Caps retain prospective worst-case resting reservations across all scopes.
Reducing whole orders remain permitted under a breach. Reversals report a
max_permitted_qty floored to an executable whole quantity, after exact Decimal
exposure arithmetic. A zero proposed quantity still inspects current exposure.
Quote construction retains the observed-mid anchor, outward rounding, passive
prices, pull reasons, deadline reduction, and all external room constraints.
Decimal, integer, and string inventory work; float inventory is refused because
binary float noise can alter quantities and room flooring. Fractional residual
inventory remains reported as a string, including when no whole reduction fits.

## Fees and unit boundary

The fractional cumulative filled size of each order/price bucket is passed
directly as a Decimal to venue_fees.fee_kalshi_maker. Its _count helper coerces
that count with float(size), takes its absolute magnitude, and the canonical
function applies its fee ceiling. This unchanged canonical boundary therefore
uses float internally. The returned fee is restored with Decimal(str(...)).
The ledger charges max(cumulative fee minus already charged fee, zero), in
points. Different fill prices accumulate independently in their price buckets.
The constructed 9.47 plus 0.53 fills total the exact canonical fee for 10.

replay_units.fill_to_ledger_event preserves integer cents and the quantity
string, uses quote_id as order_id, and combines trade_id and quote_id for fill_id.
Records become partial_fill because the tape record has no final-fill flag;
the declared quantity determines when no quantity remains open.
replay_units.fill_to_markout_fill converts cents to probability strings,
carries fee_schedule_version, and emits a timezone-aware UTC ISO fill_ts.
Callers supply the final cumulative fee and filled quantity for the order/price
bucket. Per-contract fee is total_fee / total_filled_qty, so each fill's
allocation is that value times its quantity. This avoids treating each
incremental tape fee as a standalone per-contract fee. All adapter outputs
pass json.dumps and reach markout_strict in the fixture chain.

## Reproduction and coverage

Only constructed records and the complete committed public fixture were read.
Fixture: tests/platformkit/execution/fixtures/s341_real_trades_2026-09-21.jsonl;
5184 bytes, eight rows, resolution not applicable. All eight rows are checked.
Constructed prints use its venue field shape and quantities 9.47 and 0.53;
intermediate inventory and the final sum are both asserted without rounding.
There is no archive run or scored measurement. No network, data/ access,
pod action, feature flag, or production deployment occurred. The pod is OFF.

Each command used python -m pytest tests/platformkit/execution/<file> -q
-p no:cacheprovider, run sequentially in this order:

| File | Final result |
| --- | --- |
| test_fractional_chain.py | 26 passed |
| test_position_ledger.py | 83 passed |
| test_position_reducers.py | 40 passed |
| test_position_caps.py | 42 passed |
| test_position_exposure.py | 26 passed |
| test_quote_engine.py | 38 passed |
| test_tape_fill_sim.py | 71 passed |
| test_markout_causal.py | 31 passed |

Total: 357 passing CONSTRUCT/fixture cases. An initial cap run had three
failures: two zero-quantity inspection calls and the demo's old float snapshot.
Those were corrected before the final run. Read-only review also prompted
regressions for an acknowledgment after fills and resubmitting the floored
cap maximum. The final review reported no blocking findings.

The five existing test files retain their behavioral cases. Assertions now
parse string outputs with Decimal; average-cost checks use exact equality.
The old invalid fill-quantity string "2" case now rejects "0.001" instead;
float rejection remains. New tests cover accepted fractional strings and
integer strings, while fractional order quantities remain rejected.

Contract B/Q review: no renamed/removed output field, threshold change,
deployment, sampled metric, model fitting, or performance claim. A source
reader survey under scripts/ and tests/ found no callers outside these modules
and their tests. Changed callers consume the new string quantities explicitly.
The existing tape, causal markout, venue, and lifecycle modules were not edited.

Automated contract_preflight: all nine checks PASS over the 14 paths below,
with --base master and --spec docs/evidence/tracking/specs/S357_spec.md.
The vocabulary scan is clean; all Python files are within 300 lines and ASCII.
Spec-threshold check reports no THRESHOLD/BAR/ACCEPTANCE RULE lines in this
spec; proposed-diff check reports no --proposed given (none required by S357).

## Files for lane_commit

Modified:
- scripts/platformkit/execution/position_ledger.py
- scripts/platformkit/execution/position_reducers.py
- scripts/platformkit/execution/position_caps.py
- scripts/platformkit/execution/position_exposure.py
- scripts/platformkit/execution/quote_engine.py
- tests/platformkit/execution/test_position_ledger.py
- tests/platformkit/execution/test_position_reducers.py
- tests/platformkit/execution/test_position_caps.py
- tests/platformkit/execution/test_position_exposure.py
- tests/platformkit/execution/test_quote_engine.py

Created:
- scripts/platformkit/execution/position_decimal.py
- scripts/platformkit/execution/replay_units.py
- tests/platformkit/execution/test_fractional_chain.py
- docs/evidence/harness/S357_fractional_chain_2026-09-21.md

SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED

- Independent master-worktree reproduction, commit, or landing.
- Real-archive replay, production execution, live fills, or actual queue position.
- Venue completeness and original order-size bounds for fill-only event streams.
- Decimal arithmetic inside the unchanged canonical venue fee function.
- Any deployment, pod behavior, or scored performance result.
