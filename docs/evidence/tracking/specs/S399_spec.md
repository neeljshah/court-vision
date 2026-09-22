GAP S399 | sport all (venue) | worktree harness-h60 (master-based) | log cx_s399_polymarket_certification
# Polymarket fee / tick / queue / settlement certification in the S364 style (workstream D; ASTRA_ROUND15 row 10)

SINGLE PROBLEM: scripts/platformkit/execution/venue_fees.py (OWNER file, never edited) models Polymarket as fee = shares * rate * P *
(1 - P) with _POLYMARKET_TAKER_FEE_RATE = 0.05 and _POLYMARKET_MAKER_FEE_RATE = 0.0, while the venue's own market record reports
maker_base_fee 1000 and taker_base_fee 1000 on a live sports market (orchestrator probe 2026-09-22; units unknown), a
minimum_tick_size of 0.001 and a minimum_order_size of 5, plus neg_risk, seconds_delay and end_date_iso fields the execution chain
never reads. The S364 certification covers three Polymarket fee fixtures against the module's OWN cited schedule only, so a fixture
that copies the implementation's assumption can only agree with it. No fee-netted figure on Polymarket can be stated until the
module, the venue metadata and the published schedule are reconciled, and tick, minimum size, matching priority and settlement
semantics are pinned as dated facts or listed as UNVERIFIED.

BINDING BEFORE-CONDITION: quote from master (a) fee_time_certification.py: FeeFixture(name, schedule, contracts, price, expected,
checkpoints=(), fixture_date=FIXTURE_DATE, schedule_date=SCHEDULE_DATE), RULES ('polymarket_taker': (25, ...), 'polymarket_maker':
(28, ...)), certify_fees(fixtures) -> dict, per-check statuses PASS | MISMATCH | ERROR and report status PASS | FINDINGS,
clock_skew_report(rows); (b) venue_fees.fee_polymarket(mode, notional, price) -> float and expected_value_after_fees; (c)
fee_certification_gate.py require_certified(mode) and the two permitted bounded mismatch classes; (d)
coherence_scanner_inputs.batch_fee_decimal; (e) the S397 spec's market_meta row fields (minimum_tick_size, minimum_order_size,
neg_risk, seconds_delay, maker_base_fee, taker_base_fee, end_date_iso, game_start_time, accepting_orders, orderPriceMinTickSize,
orderMinSize, feeSchedule, feeType, feesEnabled, umaResolutionStatuses, resolutionSource).

CHANGE (owned files: NEW scripts/platformkit/execution/polymarket_certification.py, NEW polymarket_certification_fixtures.py, NEW
tests/platformkit/execution/test_polymarket_certification.py, memo; venue_fees.py and fee_time_certification.py are NOT edited):
1. polymarket_certification_fixtures.py (<= 300 LOC): dated fixture tuples of literal decimal STRINGS in the S364 shape whose
   expected values are written INDEPENDENTLY of the implementation (derived by hand from the stated rule text, with the arithmetic
   shown in a comment) for (i) FEES: whole and fractional share counts at prices 0.01 / 0.05 / 0.50 / 0.95 / 0.99, partial-fill
   sequences whose increments must sum to the whole-order fee (exact cumulative arithmetic), taker and maker, each carrying the
   schedule text the module cites AND a second expected value computed from the venue's metadata field under each of the two
   candidate readings (basis points of notional; a multiplier of the parabolic rate), labelled CANDIDATE_READING and never asserted
   as the truth; (ii) TICK: an order price that is not a multiple of minimum_tick_size is refused; 0.001 and 0.01 markets; (iii)
   MINIMUM SIZE: below minimum_order_size refused; (iv) SETTLEMENT: unit payout per share for the resolved outcome, neg_risk markets
   flagged as a distinct settlement class, the umaResolutionStatuses vocabulary recorded, end_date_iso vs gameStartTime vs the state
   archive's final time compared as COUNTS of disagreements; (v) MATCHING: what the venue documents as priority is recorded as a
   QUOTED statement with its date and marked UNVERIFIED (no test can establish queue priority from public data; queue position is
   never estimated without an observation, and a sensitivity bound is the only permitted statement about it).
2. polymarket_certification.py (<= 300 LOC): --market-meta <S397 rows or fixture> --self-check --out <json>: runs the S364 fee
   certification for the polymarket schedules unchanged (as a dependency), evaluates every fixture above, and reports per check PASS |
   MISMATCH | ERROR | UNVERIFIED with the module line cited; the report status is FINDINGS when any MISMATCH exists and it prints the
   exact sentence 'a mismatch is a finding for the owner; nothing here changes venue_fees.py'; a MISMATCH REFUSES certification (the
   status handed to S398 / S400 says uncertified) and is never clamped or bounded away; a counts-only clock report over Polymarket
   snapshot rows through clock_skew_report; the one-second trade timestamp resolution is a recorded limitation. Decimal end to end; a
   zero, negative or non-finite fee result is refused and counted; no float in any fee path.
3. Tests: every fixture class; the two candidate readings disagree with the module on the probed market (assert MISMATCH is
   reported, not clamped, and the resulting status is uncertified); tick and size refusals; the report status; the self-check exit
   code; a fixture whose expected value merely calls the module is rejected by a test that greps the fixtures module for any import
   of venue_fees.
4. Memo docs/evidence/harness/S399_polymarket_certification_2026-09-22.md ending with the UNVERIFIED list (queue priority, fee units,
   the published schedule's date) addressed to the OWNER.

CONTROLS: PREPARE only; construct tests; no network; nothing is fetched (the orchestrator's probe facts above are the only venue
data). ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; memo ends with NOT
VERIFIED.

AMENDMENT 1 (2026-09-22 16:4xZ; binding; the Opus build's two conflicts, accepted). (a) A ZERO maker fee is the single accepted
maker value: the module's cited rule is 'maker fee is zero' (fee_time_certification.py:22, venue_fees.py:62 _POLYMARKET_MAKER_FEE_RATE
= 0.0); the refuse-zero rule of CHANGE item 2 applies only when the cited rate and the order are both positive (the underflow case);
a non-zero maker fee is a MISMATCH; nothing is clamped in either direction. (b) The non-fee check families (tick, minimum size,
settlement, matching) may live in a sibling module polymarket_certification_checks.py re-exported from polymarket_certification (the
300-line rail, contract A12); the fee path, report assembly and CLI stay in polymarket_certification.py. (c) MEASURED by the build's
self-check on the spec's probe facts: 78 checks, 39 PASS, 36 MISMATCH, 0 ERROR, 3 UNVERIFIED, status FINDINGS, certification refused
(uncertified): both candidate readings of the venue's maker_base_fee / taker_base_fee 1000 disagree with the module on all 13 fee
fixtures; the S364 polymarket dependency itself reports FINDINGS; 9 fee rows carry the float residue of venue_fees.fee_polymarket.
These are OWNER findings (venue_fees.py is owner-only); nothing in this row changes them.

AMENDMENT 2 (2026-09-22 17:3xZ; binding; after round 2: Opus ACCEPT WITH CORRECTIONS applied, codex sol REJECT on the selected
limits). (a) The SELECTED market's minimum_tick_size and minimum_order_size are the bounds that ADMIT the selected-market rows; a
missing selected limit refuses and never falls back to a fixture limit; the dated fixture rows form a second, labelled family
(check_class tick_fixture / size_fixture, stage cross_limit, counters refusal_<kind>_fixture). (b) MEASURED after the change on
the probe facts: 95 checks, 55 PASS, 37 MISMATCH, 0 ERROR, 3 UNVERIFIED, status FINDINGS, certification uncertified, exit 3
(supersedes the 78 / 39 / 36 headline of AMENDMENT 1(c)): the 17 dated rows now sit beside 17 selected-market rows, and the one
new MISMATCH is tick_001_off_grid, whose price 0.125 is off the 0.01 grid it was written at but ON the probed market's 0.001
grid -- a fixture verdict is not a statement about the selected market, which is exactly the class of defect the change exposes.
(c) The memo's every-except sentence reads 'increments a counter that appears in the report, or re-raises as a Refusal'; the CLI
refusal field is named refusal (value 1), never a tally.
