GAP S400 | sport all (maker channel) | worktree harness-h61 (master-based) | log cx_s400_paper_sizing
# Fee-aware PAPER sizing policy under calibration uncertainty (workstream E; ASTRA_ROUND15 row 12)

SINGLE PROBLEM: the only sizer in the tree (scripts/platformkit/execution/sizing.py: stake_for(tier, market_type) -> float, flat tier
units, one caller inplay_daytrader_maker.py) returns a binary float, knows nothing about fees, intervals, caps, family streaks or
certification, and cannot be wired into the Decimal-only execution chain (position_decimal.number refuses floats). Nothing today can
say HOW MUCH to quote in paper under a stated calibration uncertainty, and nothing says ZERO when the evidence does not license a
size -- which, under the S347 result (every cell UNDERPOWERED) and an unsealed second corpus, is the honest size everywhere.

BINDING BEFORE-CONDITION: quote from master (a) position_caps.check_caps(positions_snapshot, caps, *, order_id, ticker, game_id,
side, qty) -> dict and order_permitted(report), the caps dict shape and the per-scope report keys (current, post, cap, breached,
allowed_new_exposure, reducing, permitted, max_permitted_qty), and the statement that resting orders count toward exposure (worst
case); (b) quote_reservation.reserve(positions_snapshot, caps, ticker, game_id) -> Reservation and its bid_room / ask_room Decimal
strings; (c) position_decimal.number(value, field='quantity') -> Decimal; (d) fee_certification_gate.require_certified(mode='refuse')
-> CertificationStatus and conservative_fee(module_fee, status) -> Decimal; (e) family_week_ledger.FamilyWeekLedger.streak(family) ->
int and TARGET_WEEKS; (f) the S347 summary cell schema in baseline_four_arm.py (point, ci95 [lo, hi], verdict, n_games,
leave_one_game_out_range, largest_absolute_share, concentration_pass) and gate_a0_ingame_vs_market.verdict(lo, hi, n_games, n_min);
(g) venue_fees.fee_kalshi_maker(contracts, price) -> float (returns the whole order's fee, lesson S345); (h) quote_engine.py's quote
quantity inputs.

CHANGE (owned files: NEW scripts/platformkit/execution/paper_sizing_policy.py, NEW paper_sizing_inputs.py, NEW
tests/platformkit/execution/test_paper_sizing_policy.py, memo; sizing.py is NOT edited and NOT imported; nothing is wired into any
runtime -- no caller is added):
1. paper_sizing_inputs.py (<= 300 LOC): frozen dataclasses built ONLY from Decimal strings or ints -- CalibrationEvidence (family,
   corpus_count, verdict, point, ci_lo, ci_hi, n_games, concentration_pass, sealed_prereg_sha256 per corpus, result_artifact_path),
   FeeEvidence (the CertificationStatus label and fee_module_sha256 plus the fee per contract as conservative_fee output),
   FamilyEvidence (streak weeks from the landed ledger, required weeks = TARGET_WEEKS), Quote (ticker, game_id, side, price_cents,
   p_model, p_market_mid), Rooms (from reserve(); outstanding correlated and resting quantities already counted by the caps).
   Every constructor refuses floats, non-finite values, probabilities outside (0, 1) and prices outside [1, 99] cents with a counted
   reason.
2. paper_sizing_policy.py (<= 300 LOC): size_paper(quote, calibration, fees, family, rooms, params) -> SizingDecision with quantity
   (whole contracts, Decimal string), fraction_used, reasons (tuple, closed vocabulary), and the arithmetic in this ORDER, each step
   able to return zero with its reason: (i) LICENSE: verdict must be AHEAD with corpus_count >= 2 and a sealed prereg per corpus, else
   quantity 0 reason verdict_not_licensed (SINGLE-WINDOW and UNDERPOWERED both give zero); family streak >= required weeks else zero
   reason family_streak_short; fee status certified in refuse mode else zero reason fee_uncertified; (ii) KELLY IN CALIBRATION TERMS:
   for a YES contract at cost c (cents / 100) with model probability p, the full-Kelly fraction of unit stake is (p - c_net) / (1 -
   c_net) where c_net = c + the fee per contract (conservative_fee); a non-positive fraction is zero reason no_positive_expectation;
   (iii) FRACTIONAL: multiply by params.kelly_fraction (a Decimal in (0, 1], default '0.25'); (iv) UNCERTAINTY CAP, sealed and
   DECREASING: multiply by max(0, 1 - width / params.width_reference) where width = ci_hi - ci_lo of the licensing cell and
   width_reference is a declared Decimal; a wider interval can never increase the size (a test asserts monotonicity over a grid of
   widths) and the point is never used to enlarge it; (v) CONCENTRATION: if the licensing cell's concentration_pass is False, zero
   reason concentration_fail; (vi) ROOM: the quantity is the floor of fraction * params.paper_bankroll_units / c_net in whole
   contracts, then the minimum with the reservation's room for that side and with check_caps' max_permitted_qty computed
   PROSPECTIVELY on the snapshot (never after the fact); (vii) whole contracts only; zero is a valid decision and is never rounded up
   to one. Deterministic, pure, no I/O, no clock; the decision carries every intermediate Decimal as a string for the audit trail.
   The unit is 'paper_bankroll_units'.
3. Tests: the S347 all_tick overall B_brier cell (point -0.003363, ci95 [-0.010776, +0.004000], UNDERPOWERED, n_games 135, quoted
   verbatim) yields quantity 0 with reason verdict_not_licensed; a synthetic licensed AHEAD family with a narrow interval yields a
   positive whole quantity equal to the hand computation of (ii)-(vi) at each step; widening the interval past width_reference yields
   zero and the size is non-increasing over a width grid; a stale fee-module sha in the CertificationStatus is refused; a caps room
   smaller than the Kelly quantity wins; floats are refused; the order of reasons is stable; a price of 99 cents with p 0.995 and a
   fee gives zero when c_net >= 1.
4. Memo docs/evidence/harness/S400_paper_sizing_2026-09-22.md stating that under today's evidence the policy returns zero everywhere.

CONTROLS: PREPARE only; pure functions; construct tests; no real ledger and no real result file read by the builder (the S347 cell is
quoted in the test as literals); no network; no runtime activation. ACCEPTANCE: per-file tests pass one at a time; <= 300 LOC; ASCII;
contract Q6 vocabulary (no words for betting advantage, gains, return on investment or the currency unit anywhere: 'expectation' and
'fraction' only); memo ends with NOT VERIFIED.

AMENDMENT 1 (2026-09-22 18:5xZ; binding; from the Opus round-4 verdict). (a) OWNED SET WIDENED: fix 1c split the candidate for the
300-LOC rail; the owned files are scripts/platformkit/execution/paper_sizing_inputs.py, paper_sizing_policy.py,
paper_sizing_validate.py, tests/platformkit/execution/test_paper_sizing_inputs.py, test_paper_sizing_policy.py and the memo --
six files, additive, nothing else touched; sizing.py and venue_fees.py stay byte-identical to master and unimported by any S400
file. (b) THE LICENCE IS A DECLARATION: sealed_prereg_sha256 values are checked for FORMAT (64 hex) and distinctness only; nothing
in this row resolves a seal to a preregistration artifact, so licensed() turns on any two distinct well-formed digests. That is
by design for S400 (the row sizes under a DECLARED calibration licence; the resolution of a seal against its sealed artifact is
the S395 auditor's job and lands separately) and the memo's NOT VERIFIED list states it in those words. (c) p_market_mid is
either carried into an AUDIT_KEYS entry (audit only, reaching the audit output and never a size) or the 'audit only' comment is
removed; the memo's 'neither edited nor imported' sentence is scoped to S400 files (inplay_daytrader_maker.py imports sizing.py
on master and is not this row's).
