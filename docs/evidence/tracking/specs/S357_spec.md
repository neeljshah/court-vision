GAP S357 | sport all (maker channel) | worktree harness-h15 (master-based) | log cx_s357_fractional_chain
# Fractional quantities break the landed chain: tape fills are Decimal, the position ledger and the quote engine demand integers

SINGLE PROBLEM (astra round-11 pre-mortem, rank 1): S344 tape_fill_sim emits fills whose size is a Decimal string and is
FRACTIONAL whenever the venue print is (MEASURED: 35,841 of 69,577 archive trades; live count_fp values such as 200.47).
S345 position_ledger.validate_event rejects a non-integer qty, and S342 quote_engine returns pulled = invalid_inventory for a
non-integer inventory. A replay would crash, silently drop fractional fills, or round them -- each corrupts inventory, caps,
fees and the markout weights.

BINDING BEFORE-CONDITION (re-run, quote): (a) a position_ledger append of a fill with qty "0.53" raises; (b)
quote_engine.make_quotes with inventory 0.53 returns pulled = invalid_inventory.

CHANGE (EDIT the row-owned modules created on 2026-09-21: scripts/platformkit/execution/position_ledger.py, position_reducers.py,
position_caps.py, position_exposure.py and quote_engine.py; the module changes are REQUIRED; edit no pre-existing module):
1. QUANTITIES ARE decimal.Decimal END TO END. ORDER quantities (intent / submit) stay positive INTEGERS (we only quote whole
   contracts). FILL quantities are positive Decimals with at most 2 fractional digits (more -> refused with a reason), parsed from a
   string or an int, NEVER from a float: a float qty is refused, because binary floats are how 9.47 becomes 9.4700000001.
   Cumulative filled <= order qty is enforced exactly. Inventory, average cost, realized and unrealized points, exposure and caps
   are exact Decimal arithmetic. JSON output emits every quantity-like value as a STRING, and every result passes json.dumps.
2. quote_engine accepts a Decimal, an int or a numeric string as inventory; the skew uses it exactly; room arithmetic FLOORS the
   available room to a whole number of contracts for NEW orders (never rounds up); unresolved_inventory is returned as a string. A
   float inventory is refused with reason invalid_inventory; say why in the docstring.
3. FEES: venue_fees.fee_kalshi_maker takes a contract count. State in the memo exactly how a fractional cumulative fill is passed
   (the landed S344 passes the Decimal and venue_fees coerces it) and make the ledger incremental per-order rule -- fee of the
   cumulative filled quantity minus the fee already charged, never negative -- hold for fractional cumulative quantities; test that
   9.47 + 0.53 at one price totals exactly the fee of 10.
4. UNIT BOUNDARY in ONE NEW module scripts/platformkit/execution/replay_units.py (<= 150 LOC, pure): fill_to_ledger_event (a
   tape_fill_sim fill record -> a position ledger fill event: cents stay cents, the qty string stays a string, fill_id = trade_id +
   quote_id) and fill_to_markout_fill (cents -> probability for markout_causal; per-contract fee units = the order fee allocated
   pro rata by filled quantity; fee_schedule_version carried through; fill_ts as a timezone-aware ISO string, because the landed
   venue-time parser refuses naive strings). No other module converts units.
5. END-TO-END FIXTURE TEST tests/platformkit/execution/test_fractional_chain.py: prints of 9.47 and 0.53 (use rows shaped like
   tests/platformkit/execution/fixtures/s341_real_trades_2026-09-21.jsonl) -> tape_fill_sim -> fill_to_ledger_event -> positions ->
   check_caps -> quote_engine.make_quotes with that inventory -> fill_to_markout_fill -> markout_causal.markout_strict: nothing
   raises, nothing is dropped or rounded, inventory equals the exact Decimal sum, the fee total equals the whole-order fee, the
   markout fill price is a probability while the ledger price is cents.
6. Every existing test of the five modules still passes; where an existing test asserted that a non-integer FILL qty is rejected,
   rewrite it to the new rule and say so in the memo (ORDER quantities still reject non-integers).

CONTROLS: construct + fixture tests only; no measured number. ACCEPTANCE: every per-file test passes, run one file at a time.
Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals from single digits. Memo
docs/evidence/harness/S357_fractional_chain_2026-09-21.md ends with a NOT VERIFIED list. The pod is OFF.
