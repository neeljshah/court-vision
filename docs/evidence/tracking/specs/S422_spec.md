GAP S422 | sport all captured (venue) | worktree harness-h78 (master-based) | log cx_s422_decimal_fee_chain
# The fee chain is float end to end; make it Decimal at every boundary without changing one landed number

SINGLE PROBLEM: the harness rail says sizes, quantities, prices and fees are decimal.Decimal end to end and never pass through a float. The landed fee chain predates that rail and is float from the
schedule to the serialized fill. venue_fees.py is owner-only, so no lane may fix it in place. S411 therefore has to accept a float fee under an exact-round-trip guard (its AMENDMENT 1, counted as
fee_source_float_exact). This row gives the harness a Decimal fee path that no float touches, and it changes no landed number, no landed test and no line in the owner's file. Where the exact schedule
and the landed float ceiling disagree, that disagreement is a counted finding. It is never resolved silently in either direction.

BINDING BEFORE-CONDITION (quoted from master 871baa498): (a) venue_fees.py:68 `_PRICE_EPS = 1e-9  # float-noise tolerance around the [0, 1] bounds`; :71 `def _ceil_to_cent(dollars: float) -> float:`;
:73 `return math.ceil(round(dollars * 100.0, 6)) / 100.0`; :85 `p = float(price)  # type: ignore[arg-type]`; :100 `n = float(size)  # type: ignore[arg-type]`; :114 `return _ceil_to_cent(coef * n * p *
(1.0 - p))`; :117 `def fee_kalshi_taker(contracts: float, price: float) -> float:`; :122 `def fee_kalshi_maker(contracts: float, price: float) -> float:`; :138 `def fee_polymarket(mode: str, notional:
float, price: float) -> float:`; :153 `return shares * rate * p * (1.0 - p)`; :180 `p_true = float(p_model) if s == "yes" else (1.0 - float(p_model))`. (b) quote_engine.py:77 `fee =
Decimal(str(fee_kalshi_maker(qty, price / 100))) * 100` and :82 `return price, float(fee)`. (c) tape_fill_sim.py:21 `result = float(value)` (inside _number, which is used for latency seconds :119-120
and the book level match :66, NOT for a fee); :240 `cumulative_fee = fee_kalshi_maker(cumulative, Decimal(q["price"]) / 100)`; :243 `cumulative_fee = Decimal(str(cumulative_fee))`; :252
`fee_units=float(fee_units),  # Existing JSON numeric field only.` (d) markout.py:29 `out = float(value)` and :49 `cost = _f(fill.get("fee_units") if fee is None else fee) or 0.0`. (e) CALLERS (19
production modules; `grep -rln` returns 31 files including the four modules, tests and docstring-only mentions): econ/cost_model.py:62,89,90,115; execution/coherence_audit.py:29,167,168;
coherence_scanner.py:16,147 (sha256 of the fee file); coherence_scanner_inputs.py:11,86-89 (reads the four private constants); fee_certification_gate.py:13,17-18,188-195 (hashes the fee file's bytes);
fee_time_certification.py:12,92,94,99 (passes Decimal); paper_maker.py:11,103; polymarket_certification.py:28,62-63 (passes Decimal and then `if type(raw) is not float:` refuses);
position_reducers.py:22,121 (passes Decimal); quote_engine.py:26,77; tape_fill_sim.py:8,240,279 (passes Decimal); grade_paper_one.py:30,75; pm_trading/validation.py:42,55; quote_reservation.py:26,216
(make_quotes); forward_replay_policy.py:145,151 (via make_quotes_reserved) and :160 (reads `quote["fee_cents"][side]`); touch_queue_sensitivity.py:14,169,187,199,204 (simulate_fills);
markout_causal.py:17 (UNKEYED_CLUSTER only). LINE PINS: polymarket_certification_fixtures.py:23 `IMPL_LINE = SOURCE + ":153"` and fee_time_certification.py:19-22 pin lines 10, 11, 25 and 28. (f)
PINNED FLOATS in the landed test_venue_fees.py: :19 `assert F.fee_kalshi_taker(1, 0.50) == 0.02`; :31 `assert F.fee_kalshi_taker(10, 0.50) == 0.18`; :99 `assert F.fee_polymarket("taker", 100.0, 0.50)
== 1.25`. :88 pins the epsilon: `assert F.fee_kalshi_taker(1, 1.0 + 1e-12) == 0.0`. tests/platformkit/execution/test_tape_fill_sim.py:133-136 pins the WHOLE fill record, so any new key in a default
fill breaks it. (g) CONSEQUENCE, binding: the landed float functions must return float for every input, Decimal included, because (c), (e) and polymarket_certification:63 depend on it. _PRICE_EPS
stays on the float path because of (f):88. The Decimal path is therefore a set of NAMED twins, not a return-type switch.

CHANGE (owned files: NEW scripts/platformkit/execution/venue_fees_decimal.py, NEW tests/platformkit/execution/test_venue_fees_decimal.py, NEW tests/platformkit/execution/test_decimal_fee_chain.py,
EDITS confined to named lines of quote_engine.py and tape_fill_sim.py, an APPEND to markout.py, and the memo. venue_fees.py and every landed test stay byte-identical. The row adds no caller and wires
nothing into a runtime):
1. OWNER DIFF, not authored by the lane: the spec writer drafted PROPOSED_venue_fees_decimal.md (scratch s422/), and the orchestrator places it at docs/research/organization-sprint/. It appends
   fee_kalshi_taker_decimal, fee_kalshi_maker_decimal, fee_polymarket_decimal and expected_value_after_fees_decimal after line 186. They use an exact cent ceiling via quantize(Decimal("0.01"),
   ROUND_CEILING) and exact [0, 1] bounds, and they refuse float, bool, NaN, inf, unparseable input and negative sizes. The float path and lines 1-186 are unchanged. `git apply --check` passes against
   master.
2. venue_fees_decimal.py (<= 300 LOC): the lane's Decimal facade, the functions the harness rows import. It has the same four names, bodies and strict input contract as the owner diff. Its
   coefficients come from venue_fees' constants via Decimal(repr(const)) (the pattern at coherence_scanner_inputs.py:84-89) and are never re-typed. It imports venue_fees._norm_mode for the mode rule.
   No float appears anywhere in it.
3. DIFFERENTIAL (test_venue_fees_decimal.py). Assert Decimal(repr(float_result)) == decimal_result for every cell of each ENUMERATED grid below, for both Kalshi schedules (n = cells, CONSTRUCT), and
   assert the landed function given the same Decimal inputs returns the same float. Grids: integer counts 0..1000 x prices 0.00..1.00 by 0.01 (101,101 cells; divergence is impossible because the maker
   residue is a multiple of 1/40000 cent and the taker residue a multiple of 1/10000 cent, both above the 5e-7 cent that `round(x * 100, 6)` drops); integer counts 0..200 x prices by 0.001 (201,201);
   2-dp counts 0.01..100.00 x cent prices 0.01..0.99 (990,000). BOUNDARY CASES, pinned as an explicit DIVERGENCE LIST (asserted to diverge exactly as recorded, never as agreement): maker (892.93,
   0.43) landed 3.83 vs Decimal 3.84 (exact 3.8300000025); maker (892.93, 0.57) the same; maker (167.46, 0.47) 0.73 vs 0.74 (exact 0.7300000050, a residue of exactly 5e-7 cent); the S364 fixtures
   taker 4.00000001 @ 0.50 at 0.07 vs 0.08 and maker 16.00000001 @ 0.50 at 0.07 vs 0.08 (fee_time_certification.py:58,60 expect 0.08). The spec writer measured these on 2026-09-23 over 2-dp counts
   0.01..1000.00 x cent prices: maker 3 of 9,900,000 cells diverge, taker 0. Polymarket has no ceiling: 57,377 of 101,101 cells (shares 0..1000 x cent prices) differ from the exact value in the last
   binary place (e.g. 3 @ 0.01 gives 0.0014850000000000002 vs 0.001485), so it is compared after quantize(Decimal("1e-12")), where 0 of 101,101 differ. When the owner's twins exist in venue_fees,
   facade == twin exactly on every grid; the memo records which branch ran.
4. quote_engine.py, edits confined to :69-83 and :86-87 and :175-178. Add keyword `decimal_fees: bool = False` to make_quotes. When True, _price also returns fee_kalshi_maker_decimal(qty,
   Decimal(price) / 100) * 100 and the result gains 'fee_cents_decimal' as {side: canonical Decimal TEXT or None}. Prices, 'fee_cents' and every other key come from the landed float path unchanged.
   When False (the default, and every landed caller) the output is byte-identical.
5. tape_fill_sim.py, edits confined to :235-253 and :169. When params.get("decimal_fees") is True, the fee comes from the facade on the Decimal cumulative, tracked in a parallel internal
   q["fee_decimal"], and each fill gains 'fee_units_decimal' (Decimal TEXT of the increment). 'fee_units' stays the landed value. When the two cumulative values differ, a nonzero-only diagnostic
   `fee_ceiling_divergence` is bumped. Default params give byte-identical output. :21 stays UNEDITED: it converts latency and book levels, not fees, and a Decimal there would raise TypeError against
   float timestamps at :163.
6. markout.py: APPEND markout_decimal(fill, later_mid, fee=None) -> Decimal | None (Decimal, int or str only; float, bool, NaN and out-of-[0, 1] mid return None; the fee enters as its magnitude) and
   add it to __all__. markout(), :29 and markout_summary are unchanged.
7. Decimal TEXT means the JSON value is a STRING such as "0.05". It is never a JSON number, which json.loads would read back as a float. Canonical text is str(Decimal) after quantize for Kalshi cents
   and plain str() for Polymarket.
8. Memo docs/evidence/harness/S422_decimal_fee_chain_2026-09-23.md covers every grid with its cell count, agreement count and divergent cells verbatim; the full 9,900,000-cell 2-dp run done by the
   orchestrator (not the test); the owner-diff status; the fee-file hash consequence for fee_certification_gate and coherence_scanner; and a closing NOT VERIFIED list: the owner diff not applied;
   which ceiling the venue actually charges at a sub-5e-7-cent residue; 4-dp prices x fractional counts not exhausted; the S399 37 mismatches untouched; S411 still on its float-exact guard until it
   imports the facade.

TESTS (per file, one at a time; construct inputs only). One test closes each false-PASS risk: (1) a Decimal silently downcast: the test asserts every facade return is `type(x) is Decimal` and a source
scan of venue_fees_decimal.py finds no `float(` token; (2) a fee of exactly 0 accepted: a positive count at an interior price never returns 0 from a Kalshi twin; 0 appears only for count 0, price 0 or
1, or Polymarket maker; (3) NaN or inf: Decimal("NaN"), Decimal("Infinity"), float input and bool each raise; (4) a JSON float emitted: with decimal_fees on, json.dumps of the quote and fill output
contains the new fields only as strings, and json.loads gives back str; (5) the S399 gate's expectations changed: polymarket_certification and fee_time_certification reports computed before and after
importing the facade are byte-identical, and neither module is edited; (6) a landed test edited: `git diff --stat master -- tests/ scripts/platformkit/execution/test_venue_fees.py` is empty (verifier
check); (7) the divergence list is asserted as divergence, so a later "fix" in either direction fails loudly; (8) default-off byte identity: for every landed fixture input of test_quote_engine.py and
test_tape_fill_sim.py, json.dumps(sort_keys=True) of the output with the new code equals the master output recomputed in the same test from `git show master:<file>` loaded into a namespace.

CONTROLS: PREPARE only. No real archive, no capture, no network, no path under data/. venue_fees.py is untouched (the owner-only file; sha256 equals master). Every landed test passes unedited, run per
file. Every landed caller is byte-identical for float inputs and default flags. No caller is added and no runtime wiring. ACCEPTANCE: per-file tests pass one at a time; <= 300 LOC per new module;
quote_engine.py and tape_fill_sim.py stay <= 300 LOC; ASCII; contract Q6 vocabulary (a fee is in payout units, a markout in probability points); the memo reproduces every count and ends with NOT
VERIFIED.

DO NOT: edit venue_fees.py, fee_certification_gate.py, fee_time_certification.py, polymarket_certification*.py or any landed test; retire _PRICE_EPS or change any float return; resolve a ceiling
divergence in either direction; move a fixture expectation or a line pin; write data/registry/; flip a flag; run a trial or any real corpus; state a market advantage or a currency amount; re-print a
retracted number. This row changes how a fee is typed, never what it is.

AMENDMENT 1 (2026-09-23 17:2xZ; binding; from the Opus 5.5 build report). (a) contract_preflight's vocabulary gate FAILS on the
LANDED docstring of markout.py lines 8-11 (two hits on master's own text, which prohibits the very words it names -- the
lesson-31 trap), and the row's owned edit set includes markout.py, so the landing gate could never pass. RULING: the row
corrects that docstring TEXT ONLY (lines 8-11) to Q6 vocabulary with identical meaning ("never a currency amount and never a
return"; "never a claim of market advantage or of a gain"); the correction is part of the owned edit set, the landed
test_markout.py must still pass unedited, and the memo records the two pre-existing hits verbatim as a landed vocabulary defect
corrected in passing. (b) markout_decimal ACCEPTS a fee of exactly 0 and a fee above 1 in payout units (the fill simulator
legitimately records a "0.00" increment on a small fill under the cent ceiling, and a large fill's fee exceeds one unit);
the zero-fee refusal in TEST (2) applies to the Kalshi TWIN fee functions for a positive count at an interior price, never to
markout_decimal's fee argument. (c) The facade raises TypeError for bool and float inputs (matching the owner's proposed
twins) and ValueError for other invalid input; the refusal tests pin both. (d) The build's measured results stand as the
memo records them: the three enumerated grids agree on every cell for both Kalshi schedules; Polymarket agrees on all
101,101 cells after quantize(1e-12) (57,377 differ in the last binary place before it); the five divergence cells are
asserted as divergence; the orchestrator's full 9,900,000-cell 2-dp run is recorded when run.

AMENDMENT 2 (2026-09-23 17:3xZ; binding; from round 1 -- BOTH Opus 5.5 tiers ACCEPT WITH CORRECTIONS; both reproduced the grid
counts, the five divergence cells, default-off byte identity over the landed fixtures and 200 random quotes / fills, and the
vocabulary gate passing over all seven files). (1) THE MEMO'S PREFLIGHT SECTION is rewritten: vocab passes over all seven files;
master's markout.py:8-11 carried two hits (the currency-unit word on :8; the advantage word and the gain word on :10) recorded
BY LINE AND WORD CLASS -- never by quoting the words, which would re-trip the gate (this refines AMENDMENT 1(a)'s "verbatim");
the docstring correction is named in the "What was built" markout bullet; the base revision is stated as 8d54daad9 (the
before-condition captured at 360775901 and re-checked unchanged). (2) math.isfinite on a Decimal converts through float
(venue_fees_decimal.py:28, :55, :61) and refuses a finite 1e309 with a misleading reason: the isfinite clauses are dropped in the
facade and Decimal.is_finite() kept (the digit / exponent bound at :31 limits the arithmetic); the quote_engine / tape_fill_sim
decimal branches may keep their pattern (harmless there) but the memo names it. (3) markout_decimal reads fill["fee_units_decimal"]
as a PER-CONTRACT fee while tape_fill_sim writes the whole-fill increment: no caller exists, so the function's docstring and the
memo's NOT VERIFIED state the unit trap and the rule for any future caller (divide by qty, or convert both price and fee);
no wiring in this row. (4) The divergence list is a SAMPLE over the enumerated grids, not a closed set (a residue of 4.9e-7 cent
outside the grids also diverges); the memo says so and the fee_ceiling_divergence counter is the runtime guard.
