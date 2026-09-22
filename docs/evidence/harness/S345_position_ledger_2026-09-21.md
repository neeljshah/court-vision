# S345 position ledger -- FIX 1d -- 2026-09-21

Implementation checks PASS; independent verification is pending.
Authority: `docs/evidence/tracking/specs/S345_spec.md`, AMENDMENT 1 and AMENDMENT 2, items 1-10.
This section supersedes the two rejected submissions and their earlier ACCEPT wording.
All work and checks ran locally in `C:/Users/neelj/nba-harness-h8` on construct events.
No scored corpus, live event stream, network request or deployment was used.

## Premise and authorized scope

The existing row modules contained the reported defaults, fill identity fallback,
nonzero allowance on a prospective breach, reversal misclassification and flat marks.
The original file-absence before-condition is superseded by AMENDMENT 1 item 1:
this repair edits the three row modules and their three tests in place.
FIX 1d adds one row-owned module and its test; nine deliverables include this memo.
The binding spec was read in full and not edited by this lane.

The three lifecycle defects were re-read before generating the scratch proposal.
Exact source excerpts from `scripts/platformkit/execution/executor/lifecycle.py`:

```python
# line 65
    OrderState.EXPIRED: frozenset(),
# lines 188-190
        if not order.idempotency_key:
            order.idempotency_key = idem_key(order.ticker, order.side,
                                             order.price_cents, "")
# lines 263-266 (after self.cancel(order) at line 256)
        if order.state == OrderState.FILLED or remainder <= 0:
            new.reason = "replace skipped: original fully filled before cancel"
            return order, new
        return order, self.submit(new)
```

## FIX 1c -- AMENDMENT 1 (historical; item 4 corrected below)

1. Layout: exactly the three authorized row modules and their corresponding tests.
   Each deliverable stays within 300 lines; Python modules use stdlib and existing
   repository helpers only. Files contain ASCII with LF line endings.
2. Schema: `validate_event` is shared by `new_event`, `append_event`, `read_events`
   and the reducer. Required identifiers are nonempty strings, side is yes/no,
   qty is a positive integer, and priced events require integer price_cents in
   [1, 99]. Priced events are intent, submit, ack, partial_fill and fill; optional
   price_cents on other events is validated when present. A settle requires
   settlement_cents in [0, 100]. Booleans and coerced strings are rejected.
   Errors name the field; disk replay and direct reducer replay name the line.
   Schema-invalid final records also raise. Only malformed final JSON is tolerated;
   malformed interior JSON raises. Reducers no longer default missing event fields.
3. Fill identity: both fill types require a nonempty fill_id. Deduplication uses
   fill_id alone, including a repeat reported under the other fill event type or
   another idempotency_key. Distinct IDs sharing one order key remain distinct.
   Other events use (event type, idempotency_key), retaining intent and submit.
   The incremental reducer and replay both deduplicate; a repeated old fill cannot
   clear a later uncertain cancellation.
4. Caps: FIX 1c refused partial reductions while a cap remained breached.
   AMENDMENT 2 explicitly corrects that rule; FIX 1d below supersedes it.
   Scope keys remain per_order by order_id, per_game by ticker,
   correlated by game_id, and global across all tickers.
5. Marks: `mark_to_market` returns by_ticker, by_game and global. Tickers retain
   signed net_qty, average entry, fee_points and realized_points. Game/global
   aggregates retain signed and absolute inventory, fees, realized and unrealized
   points. A missing mid gives marked=False, unrealized_points=None and an
   unmarked_count of one; only marked values enter unrealized sums. Unmarked
   inventory, fees and realized points remain included. Flat tickers remain visible.
6. Lifecycle proposal: copied the unchanged source to `.tmp/s345_fix1c/lifecycle.py`,
   applied only the three proposed changes there, then generated the patch with
   `git diff --no-index` and replaced the scratch path with the real target path.
   No hunk counts were written manually. The applicable diff and check follow.

Preserved accounting: same-direction fills average costs; opposing fills reduce,
flatten or reverse using the established average-cost step. In particular, 10 YES
at 55 then 4 NO at 40 leaves 6 at average 55 with 20 realized points. Ten contracts
at 50 record 5 fee points. Expire/cancel retain partial-fill inventory. Replay
reproduces live inventory, fees and orders. Signed game/global quantities remain.

## FIX 1d -- AMENDMENT 2

> (7) A GENUINE REDUCING ORDER IS ALWAYS PERMITTED. An opposing order whose size does not cross through zero strictly lowers
>     exposure in every scope, so it is permitted even when post-order exposure is STILL above a cap (a breached book must be able
>     to de-risk in partial steps). For such an order: permitted = True, reducing = True, allowed_new_exposure = 0 for every
>     breached scope. Only the INCREASING part of an order is ever refused: an order that crosses through zero is evaluated as its
>     reducing part (always permitted) plus its increasing remainder (subject to every cap); if the remainder breaches, the order
>     is refused as submitted and the result reports max_permitted_qty = the reducing part, so the caller can resize.
>     Required tests: 1-lot reduce against 20 held with cap 10 -> permitted; 20 NO against 20 YES -> permitted; 35 NO against 20 YES
>     with room for only 5 short -> refused with max_permitted_qty = 25 when the cap allows 5 more, = 20 when it allows none.

Code: `scripts/platformkit/execution/position_caps.py:33-39` splits at zero;
`position_caps.py:18-23` zeros breached allowances; `position_caps.py:55-71`
permits reductions and sizes the remaining quantity across every scope.
`tests/platformkit/execution/test_position_caps.py` covers partial reductions,
exact flattening and reversal resizing to 25 or 20, with both sides and all scopes.

> (8) RESTING ORDERS COUNT. Exposure for every cap scope is WORST-CASE: filled signed inventory plus every open (acknowledged or
>     submitted, not yet terminal) order's UNFILLED quantity on the side that would INCREASE absolute exposure. Two resting 8-lot
>     YES orders under a per-game cap of 10: the first is permitted, the second is refused (worst case 16). Open orders that would
>     reduce exposure are never netted against it (pessimistic). An order in cancel_uncertain still counts as open.

Code: `scripts/platformkit/execution/position_ledger.py:32-34` defines open and
terminal event classes; `position_reducers.py:99-135` derives unfilled quantities
and preserves terminal status through late fills. New row-owned module
`scripts/platformkit/execution/position_exposure.py:7-24` aggregates each side
separately and takes the largest magnitude. `position_caps.py:29-71` applies it
to every scope, treating an increasing remainder as optional after reduction.
`tests/platformkit/execution/test_position_exposure.py` checks reservations,
cancellation uncertainty, terminal releases, late fills and opposite-side cases.
The proposed qty is additional to existing reservations for the same order_id.

> (9) THE FEE CEILING IS PER ORDER, NOT PER FILL. venue_fees.fee_kalshi_maker applies its cent ceiling once to a WHOLE order, so
>     partial fills are charged incrementally: fee for this fill = fee(cumulative filled qty of the order, price) minus the fee
>     already charged to that order (never negative). 3 + 3 + 4 contracts at 50 must total exactly the fee of 10 at 50 (5 points),
>     not 6. Fills of one order at different prices: charge each price bucket on its own cumulative quantity and state that rule.

Code: `scripts/platformkit/execution/position_reducers.py:122-127` accumulates
quantity and charged fee points per order and price bucket, charging only the
nonnegative increment. Different prices have independent cumulative ceilings.
`tests/platformkit/execution/test_position_reducers.py` checks same-price and
mixed-price fills, distinct orders and duplicate fills; `test_position_ledger.py`
checks incremental state against restart replay, including bucket state.

> (10) NON-FINITE MIDS NEVER ENTER A SUM. mark_to_market validates every mid with math.isfinite and a 0 < mid < 100 cents range
>     (state the unit); an invalid mid makes that ticker UNMARKED with a reason, counted, and excluded from by_game and global
>     unrealized sums. No NaN or inf may appear anywhere in the returned structure; a test asserts it by walking the whole result.

Code: `scripts/platformkit/execution/position_reducers.py:183-219` validates mids
in YES price cents, requires finite values strictly between 0 and 100, records
an unmarked reason/count and excludes invalid marks from unrealized sums.
`tests/platformkit/execution/test_position_reducers.py` walks the entire output
for finite floats and also serializes with allow_nan=False.

All three original row modules and all three original tests were edited.
The new exposure module and its test keep every file within 300 lines.
Average-cost accounting, fill_id-only deduplication, schema checks, signed
inventory and cancellation gating retain their existing regression coverage.
The proposal below is byte-identical to FIX 1c. FIX 1d reran it from the fence:
`git apply --check -` exited 0; stdout and stderr were empty. Source hash unchanged.

## PROPOSED lifecycle diff -- source unchanged

```diff
diff --git a/scripts/platformkit/execution/executor/lifecycle.py b/scripts/platformkit/execution/executor/lifecycle.py
index 8bb355763..b84a4b7d6 100644
--- a/scripts/platformkit/execution/executor/lifecycle.py
+++ b/scripts/platformkit/execution/executor/lifecycle.py
@@ -62,7 +62,7 @@ ALLOWED: Dict[OrderState, frozenset] = {
     OrderState.FILLED: frozenset({OrderState.SETTLED}),
     OrderState.CANCELLED: frozenset({OrderState.SETTLED}),
     OrderState.REJECTED: frozenset(),
-    OrderState.EXPIRED: frozenset(),
+    OrderState.EXPIRED: frozenset({OrderState.SETTLED}),  # partial fills stay accountable
     OrderState.SETTLED: frozenset(),
 }
 
@@ -186,8 +186,9 @@ class OrderExecutor:
     def submit(self, order: ExecOrder) -> ExecOrder:
         """NEW -> SUBMITTED -> ACKED (-> PARTIAL/FILLED if it crossed)."""
         if not order.idempotency_key:
+            day = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
             order.idempotency_key = idem_key(order.ticker, order.side,
-                                             order.price_cents, "")
+                                             order.price_cents, day)
         resp = self._call(lambda: self.exchange.submit(
             order.ticker, order.side, order.qty, order.price_cents,
             idempotency_key=order.idempotency_key),
@@ -263,6 +264,9 @@ class OrderExecutor:
         if order.state == OrderState.FILLED or remainder <= 0:
             new.reason = "replace skipped: original fully filled before cancel"
             return order, new
+        if order.state != OrderState.CANCELLED:
+            new.reason = "replace blocked: cancellation not confirmed"
+            return order, new
         return order, self.submit(new)
 
     def settle(self, order: ExecOrder) -> ExecOrder:
```

The EXPIRED transition now permits settlement of its existing partial fills.
Automatic keys use the injected clock's UTC day. Replacement submission requires
CANCELLED after the existing full-fill guard, so an EXPIRED uncertain cancellation
cannot submit a replacement. The patch remains a proposal for independent review.

Actual check after path normalization (PowerShell invocation via Python subprocess):

```text
git apply --check .tmp/s345_fix1c/lifecycle.proposed.diff
exit code: 0
stdout: (empty)
stderr: (empty)
```

The source SHA-256 before and after the scratch operation is unchanged:
`be3ce9d1e56ba860f2df570aa243f4c9f256f05ad702a8cfc1a1f3994233fe5e`.
The fenced patch is the durable artifact; its scratch copy is disposable.

## Construct reproduction

Ran these four test files separately, in this order, with no additional suite:

```text
python -m pytest tests/platformkit/execution/test_position_ledger.py -q -p no:cacheprovider
83 passed in 0.90s
python -m pytest tests/platformkit/execution/test_position_reducers.py -q -p no:cacheprovider
40 passed in 0.56s
python -m pytest tests/platformkit/execution/test_position_caps.py -q -p no:cacheprovider
42 passed in 0.61s
python -m pytest tests/platformkit/execution/test_position_exposure.py -q -p no:cacheprovider
26 passed in 0.66s
```

n = 191 (CONSTRUCT), counting pytest cases including parameterized cases.
The schema tests enumerate missing required fields, invalid types/values,
all ten lifecycle types, both fill types and disk/direct replay. Cap tests
parameterize equality and one-over across all four scopes, and reductions,
flattening and reversals across both inventory directions. Mark tests include
multiple games, signed inventory, preserved accounting and unmarked counts.
Original average-cost, fees, restart, corruption and cancellation tests also pass.

Required preflight command (all nine deliverables and the binding spec):

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/position_ledger.py scripts/platformkit/execution/position_reducers.py scripts/platformkit/execution/position_caps.py tests/platformkit/execution/test_position_ledger.py tests/platformkit/execution/test_position_reducers.py tests/platformkit/execution/test_position_caps.py scripts/platformkit/execution/position_exposure.py tests/platformkit/execution/test_position_exposure.py docs/evidence/harness/S345_position_ledger_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S345_spec.md
```

FIX 1d preflight exit code: 0. Actual output:

```text
PASS vocab clean over 9 files
PASS crlf no index-side CRLF over 9 file(s); 2 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 4 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

The required --spec was supplied. This spec has no recognized numeric threshold
lines for that mechanical check. The required command has no --proposed argument;
applicability was checked separately above against the exact fenced patch.

## NOT VERIFIED

- Resting orders at the venue that are absent from this log are unmodelled.
  Unreported quantity changes, lost terminal events and fills without a logged
  original order total cannot reconstruct the venue's true unfilled quantities.
  Cap checks do not atomically reserve between competing submitters; callers
  must serialize admission and log submission before checking the next order.
- Independent verifier rerun and acceptance are pending; this is builder evidence.
- The lifecycle proposal passed applicability checking only. It was not applied to
  the real source or executed, and lifecycle tests were not run.
- No live event producer or venue integration was exercised. The tests are constructs.
- No multi-process lock race was exercised; the existing optional ledger_lock path
  was retained. It falls back to single-process behavior if the import is unavailable.
- Maker fee points only; other fee channels were not evaluated.
- Settlement still flattens the entire ticker; relisting after settlement is untested.
- No commit was created in this sandbox; files are ready for lane_commit.
