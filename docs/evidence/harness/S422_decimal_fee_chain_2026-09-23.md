# S422 -- Decimal fee chain (build memo, 2026-09-23)

Result: a Decimal fee facade (scripts/platformkit/execution/venue_fees_decimal.py) agrees with the landed float
Kalshi schedules on every cell of the three enumerated grids, and the five boundary cells the spec lists are asserted as divergence.
They are a pinned sample, not a closed set of divergent inputs. Opt-in Decimal fields exist in quote_engine, tape_fill_sim and markout.
With default flags, every landed fixture replays byte-identical against master. venue_fees.py and every landed test are
unchanged. Fees are in payout units; markouts are in probability points.

Interpreter: Python 3.10.0 (C:/Users/neelj/AppData/Local/Programs/Python/Python310/python). Worktree harness-h78, base
master 8d54daad9 at independent verification. The before-condition was captured at 360775901 and re-checked
unchanged at 8d54daad9. FIX 1b began with HEAD d65e79970; the master ref continued advancing during checks.

## BINDING BEFORE-CONDITION (captured at 360775901; re-checked at 8d54daad9)

`git show master:<file> | sed -n <lines>p` printed:

    venue_fees.py 68,71,73,85,100,114,117,122,138,153,180:
    _PRICE_EPS = 1e-9  # float-noise tolerance around the [0, 1] bounds
    def _ceil_to_cent(dollars: float) -> float:
        return math.ceil(round(dollars * 100.0, 6)) / 100.0
            p = float(price)  # type: ignore[arg-type]
            n = float(size)  # type: ignore[arg-type]
        return _ceil_to_cent(coef * n * p * (1.0 - p))
    def fee_kalshi_taker(contracts: float, price: float) -> float:
    def fee_kalshi_maker(contracts: float, price: float) -> float:
    def fee_polymarket(mode: str, notional: float, price: float) -> float:
        return shares * rate * p * (1.0 - p)
        p_true = float(p_model) if s == "yes" else (1.0 - float(p_model))
    quote_engine.py 77,82:
            fee = Decimal(str(fee_kalshi_maker(qty, price / 100))) * 100
                return price, float(fee)
    tape_fill_sim.py 21,240,243,252:
        result = float(value)
                    cumulative_fee = fee_kalshi_maker(cumulative, Decimal(q["price"]) / 100)
                    cumulative_fee = Decimal(str(cumulative_fee))
                                  fee_units=float(fee_units),  # Existing JSON numeric field only.
    markout.py 29,49:
            out = float(value)
        cost = _f(fill.get("fee_units") if fee is None else fee) or 0.0
    test_venue_fees.py 19,31,88,99:
        assert F.fee_kalshi_taker(1, 0.50) == 0.02
        assert F.fee_kalshi_taker(10, 0.50) == 0.18
        assert F.fee_kalshi_taker(1, 1.0 + 1e-12) == 0.0
        assert F.fee_polymarket("taker", 100.0, 0.50) == 1.25

Every pinned line matches the spec quote (which cites 871baa498; the lines are unchanged at 360775901 and 8d54daad9).
`git diff --stat master -- tests/ scripts/platformkit/execution/test_venue_fees.py scripts/platformkit/execution/venue_fees.py`
is empty. `git hash-object venue_fees.py` equals `git rev-parse master:.../venue_fees.py` (59e0d183...).

## What was built

- venue_fees_decimal.py (101 LOC): fee_kalshi_taker_decimal, fee_kalshi_maker_decimal, fee_polymarket_decimal and
  expected_value_after_fees_decimal. Coefficients come from venue_fees constants via Decimal(repr(const)) and are read
  at call time. The mode rule is venue_fees._norm_mode. The ceiling is quantize(0.01, ROUND_CEILING). Price bounds are
  exact [0, 1] with no epsilon. bool and float raise TypeError, the owner twin's class. NaN, inf, sNaN, None, unparseable
  text, a negative size and an out-of-range price raise ValueError. A positive size at an interior price that computes
  to 0 raises. Arithmetic runs in a local context sized to the inputs, so the ambient precision cannot change a fee.
  There is no `float(` token in the file.
- quote_engine.py (215 LOC): `_price(..., *, decimal_fees=False)` and `make_quotes(..., *, decimal_fees=False)`. Edits
  sit at master :70, after :81, :83, :87, :175 and after :178. When the flag is literally True, the result gains
  fee_cents_decimal {bid, ask} as cent TEXT such as "4.00", or None for an inactive side. Prices and fee_cents come
  from the landed path.
- tape_fill_sim.py (296 LOC): after :169, q["fee_decimal"] is initialised when params["decimal_fees"] is True. After
  :253 each fill gains fee_units_decimal (TEXT of the increment of the exact cumulative fee). When the exact cumulative
  fee differs from the landed one, the nonzero-only diagnostic fee_ceiling_divergence is bumped. fee_units stays the
  landed value. :21 is unedited.
- markout.py (174 LOC): markout_decimal is appended and added to __all__. It reads fee_units_decimal, then fee_units.
  Decimal, int and str are accepted. A float, bool, NaN, missing value or out-of-[0, 1] mid or price returns None. The
  fee enters as its magnitude. A 0 fee is scored, because a cumulative cent ceiling makes a "0.00" increment legitimate
  (for example fills of 0.5, 1 and 1 at 50 cents give 0.01, 0.00 and 0.01). markout(), :29 and markout_summary are
  unchanged. The landed vocabulary defect at master :8-11 was corrected text-only to AMENDMENT 1(a) wording.

## Grids (test_venue_fees_decimal.py, CONSTRUCT inputs)

For each cell, the test asserts three things. The landed float function gives the same float for float inputs and for
Decimal inputs. Decimal(repr(float_result)) equals the facade. The facade is positive exactly when size > 0 and 0 < p < 1.

| grid | schedule | cells | agree | diverge |
|---|---|---|---|---|
| integer counts 0..1000 x prices 0.00..1.00 by 0.01 | maker | 101,101 | 101,101 | 0 |
| same | taker | 101,101 | 101,101 | 0 |
| integer counts 0..200 x prices 0.000..1.000 by 0.001 | maker | 201,201 | 201,201 | 0 |
| same | taker | 201,201 | 201,201 | 0 |
| 2-dp counts 0.01..100.00 x cent prices 0.01..0.99 | maker | 990,000 | 990,000 | 0 |
| same | taker | 990,000 | 990,000 | 0 |
| Polymarket taker, shares 0..1000 x cent prices 0.00..1.00, after quantize(1e-12) | taker | 101,101 | 101,101 | 0 |
| same, exact (last binary place) | taker | 101,101 | 43,724 | 57,377 |

Polymarket maker is exactly 0 on all 101,101 cells. The example cell is 3 @ 0.01: landed 0.0014850000000000002, facade
0.001485. Twin branch: venue_fees has no *_decimal twins in this worktree, so the facade-only branch ran. The facade ==
twin assertions are present and inactive until the owner diff lands.

## Divergence list (asserted AS DIVERGENCE, test_spec_boundary_fixture_end_to_end)

| schedule | size | price | landed float | facade | exact product |
|---|---|---|---|---|---|
| maker | 892.93 | 0.43 | 3.83 | 3.84 | 3.8300000025 |
| maker | 892.93 | 0.57 | 3.83 | 3.84 | 3.8300000025 |
| maker | 167.46 | 0.47 | 0.73 | 0.74 | 0.7300000050 |
| taker | 4.00000001 | 0.50 | 0.07 | 0.08 | 0.070000000175 |
| maker | 16.00000001 | 0.50 | 0.07 | 0.08 | 0.07000000004375 |

The three 2-dp cells also run through tape_fill_sim with decimal_fees on, as fills of 1 and (size - 1)
(test_cumulative_ceiling_divergence_counted). The landed fee_units sum to the landed value and fee_units_decimal sums
to the facade value. fee_ceiling_divergence == 1. With the new keys stripped, the output equals the flag-off run.

The full 9,900,000-cell 2-dp run (counts 0.01..1000.00) is the orchestrator's. It was NOT run here. The spec writer's
measurement is maker 3 divergent and taker 0; this build does not reproduce it.

## Original build tests (historical record; per file, one at a time, `python -m pytest <file> -q -p no:cacheprovider`)

New:
- tests/platformkit/execution/test_venue_fees_decimal.py: 35 passed (about 33 s).
- tests/platformkit/execution/test_decimal_fee_chain.py: 35 passed. TEST 8 replays every landed fixture through a
  comparator against `git show master:<file>`: quote_engine 38 fixture cases / 240 calls / 0 refusals, and
  tape_fill_sim 71 fixture cases / 117 calls / 4 refusals (refusals compared by type and message). The certification
  reports (certify_fees, certify_polymarket) are byte-identical before and after importing the facade in a fresh
  interpreter.

Landed, unedited: test_venue_fees.py 29; test_quote_engine.py 38; test_tape_fill_sim.py 71; test_markout.py 13;
test_fee_time_certification.py 89; test_polymarket_certification.py 45; test_polymarket_certification_admission.py 12;
test_fee_certification_gate.py 64; test_quote_reservation.py 45; test_tape_fill_time_fees.py 109;
test_markout_causal.py 31; test_markout_identity_units.py 79; test_markout_mark_selection.py 10 (+18 subtests);
test_markout_quantity_decimal.py 76; test_coherence_scanner.py 103. All passed.

## Owner diff status

docs/research/organization-sprint/PROPOSED_venue_fees_decimal_2026-09-23.md in the main tree was READ, not applied.
Its diff block, extracted to scratch, passes `git apply --check` against this worktree (exit 0). Consequence when the
owner applies it: fee_certification_gate hashes venue_fees.py bytes, so a stored CertificationStatus goes stale and
conservative_fee refuses until re-certification. coherence_scanner's venue_fees_sha256 changes too. No fee number
changes. This row does not edit venue_fees.py, so neither hash moves now.

## Preflight

contract_preflight reports `PASS vocab clean over 7 files`; all nine checks pass.
Master markout.py:8-11 carried two banned-vocabulary hits: the currency-unit word on :8, and the advantage
and gain words on :10. This landed vocabulary defect was corrected in passing, text-only, to the
AMENDMENT 1(a) wording. Word classes are recorded rather than the prohibited tokens, per AMENDMENT 2(1).

## FIX 1b

All reproductions use CONSTRUCT inputs in this worktree. No archive, network, pod or scored trial was used.
The exact rules below follow AMENDMENT 2, including its refinement of the two verifier memo corrections.

- Tier 1 finding 1 / Tier 2 C1: the old memo said "every check PASSes except vocab" and "APPEND-only".
  The reproduction instead printed `PASS vocab clean over 7 files`; the candidate diff already had the text-only
  docstring correction. Preflight now records that pass and the original line/word classes; What was built names
  the correction. The confirmed-correct docstring wording at :8-11 was left unchanged in FIX 1b.
- Tier 1 finding 2 / Tier 2 C1 base: the old memo printed `master 360775901.`. The base is now identified as
  verifier revision 8d54daad9, with the earlier capture and this fix's HEAD distinguished. Read-only diffs over
  all four execution modules were empty from 360775901 to 8d54daad9 and from 8d54daad9 to master during this run.
- Tier 1 finding 3 / AMENDMENT 2(2): before, the exact probe printed `1e308 1.25E+306` and
  `1e309 ValueError finite decimal required`. The added regression produced `2 failed, 36 passed`, with
  `ValueError: finite decimal required` for exponents 309 and 400. Removed the facade's math.isfinite import
  and all three calls; Decimal.is_finite() and the representation bounds remain. Regression cases cover
  exponents 308, 309 and 400 for both Kalshi schedules and both Polymarket modes, including Decimal return types.
  The quote_engine and tape_fill_sim decimal branches retain their math.isfinite pattern as AMENDMENT 2 permits.
- Tier 1 finding 4 / Tier 2 N4 / AMENDMENT 2(3): before, converting only price on a 10-contract fill printed
  `price-only conversion: 0.05 expected per-contract: 0.095`. The appended function docstring now explicitly
  states that fee_units_decimal is a whole-fill increment and the caller must divide it by qty as well as
  divide the cent price by 100. The regression checks both caller conversion and an explicit per-contract fee
  override produce Decimal("0.095"). No calculation or caller was changed; documentation is the binding fix.
- Tier 2 N1 / AMENDMENT 2(4): the outside-grid size 166.8571439771428571428571429 at 0.50 printed landed
  `0.73` and exact `0.74`. Its cent residue is approximately 4.9e-7. The list is now described as a sample;
  this additional CONSTRUCT case checks fee_ceiling_divergence == 1 and unchanged default output in the existing
  cumulative-fill regression. The counter remains the runtime guard under the opt-in flag.
- Tier 1 finding 5 and Tier 2 N2, N3, N5 were confirmed correct and are unchanged.

Post-fix probe output: `1e308 1.25E+306`, `1e309 1.25E+307`, and `price and fee converted: 0.095`.
FIX 1b ran only these per-file commands, one at a time, with `python -m pytest <file> -q -p no:cacheprovider`:

| file under tests/platformkit/execution/ | passed |
|---|---|
| test_venue_fees_decimal.py | 38 |
| test_decimal_fee_chain.py | 37 |
| test_quote_engine.py | 38 |
| test_tape_fill_sim.py | 71 |
| test_markout.py | 13 |

Total: 197 passed. The original build's longer list above is historical, not a claim of rerunning it in FIX 1b.
The three `python -m scripts.platformkit.execution.<module>` self-checks passed: quote_engine printed
`S342 quote_engine self-check PASS (CONSTRUCT; PREPARE ONLY)`; tape_fill_sim exited 0 without output;
markout printed `markout self-check OK`. These modules have no help parser; the facade has no CLI.
`python -m scripts.platformkit.tracking.contract_preflight --help` exited 0. The required preflight uses
all seven S422 candidate paths (the four execution modules, the two tests and this memo), `--base master`
and `--spec docs/evidence/tracking/specs/S422_spec.md`; the verdict file is excluded.
The owner fee module and the landed tests remain unchanged; read-only diff checks passed.

## NOT VERIFIED

- The owner diff is not applied; the facade == twin branch has never executed.
- Which ceiling the venue actually charges at a residue below 5e-7 cent is unknown. The five cells are a sample. Neither
  side is resolved.
- 4-dp prices x fractional counts are not exhausted. The 9,900,000-cell 2-dp run was not executed by this build.
- The S399 37 mismatches are untouched.
- S411 stays on its float-exact guard until it imports the facade.
- markout_decimal takes price and fee in payout units per contract. Cent-price fills and batch fees must be converted
  by the caller: divide fee_units_decimal by qty and price by 100; converting only price is a unit trap.
  This function does not divide automatically. No caller is wired.
