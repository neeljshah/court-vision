GAP S345 | sport all (maker channel) | worktree (claude sonnet, isolated) | log cx_s345_position_ledger
# Append-only order/fill event log + restart-safe position and mark-to-market reducers (astra round 10 rank 5)

SINGLE PROBLEM: the stack has a CLV ledger but no position ledger: no inventory, no mark-to-market, no exposure caps that
survive a restart (audit 04 capability #7, milestone M4). Lifecycle defects named by the audit and re-cited by astra:
executor/lifecycle.py:65 leaves EXPIRED terminal with partial fills stranded, :188-190 idempotency key omits the day,
:253-266 can replace after an UNCERTAIN cancellation.

BINDING BEFORE-CONDITION: re-read those three line ranges in scripts/platformkit/execution/executor/lifecycle.py and quote them;
`ls scripts/platformkit/execution/position_ledger.py` fails.

CHANGE (NEW files only; lifecycle.py is NOT edited -- write the three lifecycle fixes as a PROPOSED diff in the memo):
1. scripts/platformkit/execution/position_ledger.py (<= 300 LOC, stdlib, ASCII): append-only JSONL event log
   (intent, submit, ack, partial_fill, fill, cancel_requested, cancel_confirmed, cancel_uncertain, expire, settle) with
   intent-based idempotency keys that include the UTC day; pure reducers `positions(events)` and
   `mark_to_market(positions, mids)` -> per ticker / per game_id / global signed inventory, average entry, fees paid,
   unrealized in probability points; `check_caps(positions, caps)` -> per-order, per-game, correlated (same game_id) and
   global caps; a breached cap returns allowed_new_exposure = 0 (reduce-only), and an event stream containing
   cancel_uncertain blocks any replace on that order until cancel_confirmed or a fill resolves it.
   Writes ONLY to a caller-supplied path (tests use tmp_path); atomic append + the existing ledger_lock pattern from
   scripts/platformkit/clv_ledger.py if importable without side effects.
2. tests/platformkit/execution/test_position_ledger.py: exhaustive partial-fill, restart (rebuild from the log == live state),
   duplicate event, cancellation-race and cap-breach cases; replay reproduces inventory exactly.
3. `_demo()` assert self-check.

CONTROLS: construct tests only, no measured number. No default path under data/. No flag. Units: contracts and probability
points, never currency totals in prose. ACCEPTANCE: per-file tests pass; diff = NEW files only. Vocabulary follows contract Q6;
automated scan required. Memo docs/evidence/harness/S345_position_ledger_2026-09-21.md ends with a NOT VERIFIED list.

AMENDMENT 1 (orchestrator, 2026-09-21, after two verifier REJECTs; binding).
(1) FILE LAYOUT IS AUTHORIZED: position_ledger.py + position_reducers.py + position_caps.py, with one test file per module
    (test_position_ledger.py, test_position_reducers.py, test_position_caps.py), each <= 300 LOC. Do not re-raise the split.
(2) EVENT SCHEMA IS VALIDATED, NEVER DEFAULTED: append_event and the replay path both reject (ValueError naming the field and,
    on replay, the line number) any event with a missing or invalid required field -- event type, idempotency_key, order id,
    ticker, game_id, side in {yes, no}, qty > 0, price in [1, 99] cents for priced events. Reducers carry NO zero or empty
    defaults: a valid-JSON but schema-invalid INTERIOR line is corruption and raises, exactly like malformed JSON.
(3) EVERY FILL HAS A STABLE IDENTITY: a fill or partial_fill event REQUIRES fill_id (venue trade id, or a caller-supplied
    deterministic id for paper fills). De-duplication of fills is on fill_id ONLY, so several distinct fills of one order are
    all kept and only a true repeat is a no-op. A fill without fill_id is rejected at append.
(4) CAPS ARE PROSPECTIVE AND A BREACH MEANS ZERO: for every scope (per-order, per-game, correlated same game_id, global) evaluate
    POST-ORDER exposure; if post > cap the result carries allowed_new_exposure = 0 for that scope (never the old headroom), and
    the order is refused. REDUCE-ONLY means an opposing order whose size does NOT cross through zero: 35 NO against 20 YES is an
    increase through a reversal (ends at -15) and is NOT reduce-only; at most 20 of it reduces. Equality (post == cap) is allowed.
(5) MARK-TO-MARKET RETURNS THREE LEVELS: {"by_ticker": ..., "by_game": ..., "global": ...}, each with signed inventory,
    average entry (ticker level), fee points paid, realized and unrealized probability points; a ticker with no mid is reported
    as unmarked and excluded from the unrealized sums with a count, never marked at zero.
(6) THE PROPOSED LIFECYCLE DIFF MUST APPLY: generate it with `git diff` against a scratch copy (never hand-write hunk counts),
    store it in the memo inside a fenced block AND verify it with `git apply --check` before finishing; paste that check.
    Run contract_preflight WITH --spec docs/evidence/tracking/specs/S345_spec.md so spec-dependent checks are not no-ops.

AMENDMENT 2 (orchestrator, 2026-09-21, after the independent risk review returned PARTIAL; binding; item (7) CORRECTS an ambiguity
in AMENDMENT 1 item 4 that was the orchestrator's wording error).
(7) A GENUINE REDUCING ORDER IS ALWAYS PERMITTED. An opposing order whose size does not cross through zero strictly lowers
    exposure in every scope, so it is permitted even when post-order exposure is STILL above a cap (a breached book must be able
    to de-risk in partial steps). For such an order: permitted = True, reducing = True, allowed_new_exposure = 0 for every
    breached scope. Only the INCREASING part of an order is ever refused: an order that crosses through zero is evaluated as its
    reducing part (always permitted) plus its increasing remainder (subject to every cap); if the remainder breaches, the order
    is refused as submitted and the result reports max_permitted_qty = the reducing part, so the caller can resize.
    Required tests: 1-lot reduce against 20 held with cap 10 -> permitted; 20 NO against 20 YES -> permitted; 35 NO against 20 YES
    with room for only 5 short -> refused with max_permitted_qty = 25 when the cap allows 5 more, = 20 when it allows none.
(8) RESTING ORDERS COUNT. Exposure for every cap scope is WORST-CASE: filled signed inventory plus every open (acknowledged or
    submitted, not yet terminal) order's UNFILLED quantity on the side that would INCREASE absolute exposure. Two resting 8-lot
    YES orders under a per-game cap of 10: the first is permitted, the second is refused (worst case 16). Open orders that would
    reduce exposure are never netted against it (pessimistic). An order in cancel_uncertain still counts as open.
(9) THE FEE CEILING IS PER ORDER, NOT PER FILL. venue_fees.fee_kalshi_maker applies its cent ceiling once to a WHOLE order, so
    partial fills are charged incrementally: fee for this fill = fee(cumulative filled qty of the order, price) minus the fee
    already charged to that order (never negative). 3 + 3 + 4 contracts at 50 must total exactly the fee of 10 at 50 (5 points),
    not 6. Fills of one order at different prices: charge each price bucket on its own cumulative quantity and state that rule.
(10) NON-FINITE MIDS NEVER ENTER A SUM. mark_to_market validates every mid with math.isfinite and a 0 < mid < 100 cents range
    (state the unit); an invalid mid makes that ticker UNMARKED with a reason, counted, and excluded from by_game and global
    unrealized sums. No NaN or inf may appear anywhere in the returned structure; a test asserts it by walking the whole result.
