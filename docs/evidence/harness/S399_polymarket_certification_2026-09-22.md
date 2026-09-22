# S399 Polymarket fee, tick, size and settlement certification -- PREPARE ONLY

Vocabulary follows contract Q6; automated scan required.

Prepared locally in C:/Users/neelj/nba-harness-h60 on 2026-09-22. Every result
below comes from in-memory constructs because this row authorizes preparation
only. No archive was opened, no request left this machine, and the venue data
of record is the orchestrator probe of 2026-09-22 quoted in the S397 and S399
specs. The pod remained OFF.

## Binding before-condition

Run from master before any file was written; the quoted signatures are the
contract this row builds against.

```text
$ git show master:scripts/platformkit/execution/fee_time_certification.py | grep -n ...
21:    "polymarket_taker": (25, "C * 0.05 * P * (1 - P); sports rate at line 27"),
22:    "polymarket_maker": (28, "maker fee is zero"),
27:class FeeFixture:
30:    name: str
31:    schedule: str
32:    contracts: str
33:    price: str
34:    expected: str
35:    checkpoints: tuple[tuple[str, str], ...] = ()
36:    fixture_date: str = FIXTURE_DATE
37:    schedule_date: str = SCHEDULE_DATE
71:    FeeFixture("sports_example", "polymarket_taker", "100", "0.50", "1.25"),
72:    FeeFixture("sports_fraction", "polymarket_taker", "2.5", "0.50", "0.03125",
74:    FeeFixture("sports_maker", "polymarket_maker", "2.5", "0.50", "0"),
103:def certify_fees(fixtures: Iterable[FeeFixture] = FEE_FIXTURES) -> dict:
126:                check.update(actual=str(actual), status="PASS" if matches else "MISMATCH")
141:            "status": "FINDINGS" if findings else "PASS"}
177:def clock_skew_report(rows: Iterable[Mapping]) -> dict:
$ git show master:scripts/platformkit/execution/venue_fees.py | grep -n ...
138:def fee_polymarket(mode: str, notional: float, price: float) -> float:
156:def expected_value_after_fees(p_model: float, price: float, side: str,
$ git show master:scripts/platformkit/execution/fee_certification_gate.py | grep -n ...
90:                "cent_boundary_ceiling", "binary_float_representation"}):
113:        return "cent_boundary_ceiling"
180:    if report["status"] != ("FINDINGS" if failed else "PASS"):
204:def require_certified(mode: str = "refuse") -> CertificationStatus:
211:    known = {"cent_boundary_ceiling", "binary_float_representation"}
$ git show master:scripts/platformkit/execution/coherence_scanner_inputs.py | grep -n ...
83:def batch_fee_decimal(venue: str, mode: str, qty: Decimal, price: Decimal) -> Decimal:
```

The S397 market_meta fields are recorded verbatim in the new fixtures module:
minimum_tick_size, minimum_order_size, neg_risk, seconds_delay, maker_base_fee,
taker_base_fee, end_date_iso, game_start_time, accepting_orders,
orderPriceMinTickSize, orderMinSize, feeSchedule, feeType, feesEnabled,
umaResolutionStatuses and resolutionSource. Only six of them carry a probed
value (minimum_tick_size 0.001, minimum_order_size 5, maker_base_fee 1000,
taker_base_fee 1000, orderPriceMinTickSize 0.001, orderMinSize 5); the rest are
None in the fixture and are never defaulted to a zero or to a guess.

## Two spec conflicts, stated rather than hidden

1. S399 CHANGE item 2 requires "a zero, negative or non-finite fee result is
   refused and counted", while the maker rule it also requires
   (fee_time_certification.py:22, `'polymarket_maker': (28, "maker fee is
   zero")`, implemented at venue_fees.py:62) produces exactly zero. Resolution:
   `module_fee(..., positive)` refuses a zero only when the cited rate and the
   order are both positive, which is the underflow case; zero stays the single
   accepted maker value and a non-zero maker fee is a MISMATCH. Nothing is
   clamped either way.
2. The CHANGE block names one certification module, but its fee path, report
   assembly and CLI plus the four non-fee check families do not fit under the
   shared 300 line rail (tests/platformkit/test_loc_rail_scope.py, LOC_CAP =
   300; contract A12 makes that rail part of the landing). The families that
   never touch a fee therefore live in a sibling,
   polymarket_certification_checks.py, and are re-exported from
   polymarket_certification. This is the split contract_preflight_extra.py
   already uses for the same rail. No landed module was edited.

## Scope and provenance

Created files, all new, none of them a pre-existing module:

- scripts/platformkit/execution/polymarket_certification.py (297 lines)
- scripts/platformkit/execution/polymarket_certification_checks.py (258 lines)
- scripts/platformkit/execution/polymarket_certification_fixtures.py (297 lines)
- tests/platformkit/execution/test_polymarket_certification.py (288 lines)
- tests/platformkit/execution/test_polymarket_certification_admission.py (183)
- docs/evidence/harness/S399_polymarket_certification_2026-09-22.md

venue_fees.py and fee_time_certification.py are owner files and were NOT
edited. Inputs opened for this row, relative to C:/Users/neelj/nba-harness-h60;
resolution is not applicable to text source.

| Input | Bytes | Resolution |
| --- | ---: | --- |
| docs/evidence/tracking/specs/S399_spec.md (AMENDMENTS 1-2) | 8236 | n/a |
| docs/evidence/tracking/specs/S397_spec.md (AMENDMENTS 1-4) | 17353 | n/a |
| docs/evidence/tracking/specs/S364_spec.md | 2544 | n/a |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 12532 | n/a |
| scripts/platformkit/execution/venue_fees.py | 8935 | n/a |
| scripts/platformkit/execution/fee_time_certification.py | 11920 | n/a |
| scripts/platformkit/execution/fee_certification_gate.py | 12169 | n/a |
| scripts/platformkit/execution/coherence_scanner_inputs.py | 10294 | n/a |
| scripts/platformkit/execution/venue_time.py | 2029 | n/a |

## Independence of the fixtures

The fixtures module imports `__future__` and `dataclasses` and nothing else; a
test walks its syntax tree to prove it. Every fee expectation is a literal
decimal string derived by hand from the cited schedule text, with the
arithmetic in a comment beside it, and a second test re-derives all of them
with exact Decimal arithmetic from the rate string alone. The S364 fixtures
could only ever agree with the implementation because they were produced from
the same module's own cited text and compared against that module; these are
produced from the text and from the venue metadata independently.

## Construct results

The two per-file test commands passed 45 and 12 tests. `--help` exited 0 and
`--self-check` exited 3. It ran 95 checks over 13 fee fixtures, 17 grid
fixtures in two admission families, 4 settlement fixtures, 5 settlement-time
rows and 2 matching records: 55 PASS, 37 MISMATCH, 0 ERROR and 3 UNVERIFIED.
The status is FINDINGS and the status handed onward is `uncertified`. A
mismatch is a finding for the owner.

| Check | Expected | Observed | Finding |
| --- | --- | --- | --- |
| candidate, 26 rows across both readings | metadata reading of base fee 1000 | the module's 0.05 parabolic rate | Neither reading of the probed metadata agrees with the module on any fixture. |
| candidate, maker rows | non-zero under both readings | 0 | The venue record reports maker_base_fee 1000 while the module charges makers nothing. |
| s364 polymarket_fixtures | PASS | FINDINGS | The landed S364 fixtures already disagree with the module on the fractional partial chain. |
| fee taker_whole_p95 whole | 0.2375 | 0.2375000000000002 | Exact-decimal discrepancy after the module's float conversion. |
| fee taker_whole_p99 whole | 0.0495 | 0.049500000000000044 | Same float residue at the other extreme price. |
| fee taker_fraction_p99, all four stages | 0.0012375 and its chain | 0.0012375000000000012 and its chain | The residue carries through every cumulative stage. |
| fee taker_fraction_p50 partial_1, partial_2 | 0.01875, increment 0.0125 | 0.018750000000000003, increment 0.012499999999999997 | Reproduces the S364 finding on the same chain. |

Eight of the nine fee discrepancies are between 2E-19 and 2E-16 in magnitude;
the ninth, taker_fraction_p50 partial_2, has an exact cumulative value and
disagrees on the increment that reaches it (0.012499999999999997 against
0.0125), which is reported rather than absorbed by the correct total. The
twenty-six candidate discrepancies run from 0.0012374999999999988 to 9.900.
Every one of them is reported at full precision with its exact delta, and none
is rounded, clamped or bounded. Each partial chain's increments sum exactly to the
whole-order fee the module produced for the same fixture, so a correct sum
never erases an intermediate discrepancy.

The 17 grid fixtures are admitted twice: once under the SELECTED limits
(check_class tick / size) and once under their own dated limits (tick_fixture /
size_fixture, stage cross_limit). The dated family passes 17 of 17. The
selected family passes 16 of 17 and reports ONE MISMATCH, tick_001_off_grid,
whose 0.125 is off the 0.01 grid it was written at but ON the probed 0.001
grid. A price off the selected grid or outside the open unit interval is
refused, a size below the selected minimum is refused, and an unparseable or
non-string value is a counted refusal rather than a zero. The counters recorded
refusal_tick 7 and refusal_tick_fixture 8, refusal_size 5 and
refusal_size_fixture 5. The two probed surfaces agree: minimum_tick_size equals
orderPriceMinTickSize and minimum_order_size equals orderMinSize.

Settlement pays one unit payout per share of the resolved outcome and nothing
on the other side, and neg_risk is carried as a distinct settlement class. The
umaResolutionStatuses vocabulary is recorded as UNVERIFIED and empty, never as
"no status exists". The three end-of-market times are compared as counts only:
over 5 construct rows, end_date_iso and game_start_time disagreed 3 times,
end_date_iso and the archive final time disagreed once over 3 comparable pairs,
one naive timestamp was refused by parse_venue_time and counted, and one
missing archive time was counted rather than read as zero.

Matching priority and queue position are both recorded UNVERIFIED with their
probe date and an empty quote, because the probe returned no venue statement
about either and no documentation page was fetched. No queue position is
estimated anywhere in the report; the only statement made about it is the
sensitivity bound, which spans the whole level from front to back.

## Discipline that backs the report

Sizes, prices and fees are `decimal.Decimal` from literal strings end to end.
The single float boundary is the landed calculator itself, which returns a
float at venue_fees.py:153; its value crosses through its exact string exactly
as fee_time_certification.py:100 does, and no float is multiplied or divided in
the new code. Every Decimal scaling is re-validated afterwards: a positive base
fee whose quotient underflows to zero is refused, as is a positive order whose
module fee underflows to zero. Counts are strict ints and refuse bool, float
and numeric strings. A missing metadata field is a counted refusal and an ERROR
check, never a zero. Duplicate market_meta rows at one event_ticker are counted
and refused, never merged. Every `except` clause increments a counter that
appears in the report, or re-raises as a Refusal. The report carries no
wall-clock field, its rows are sorted by class, name and stage, and a test
asserts that permuting the market rows or the fixture table gives an identical
report. The `--out` write goes to a sibling temporary file that is flushed,
fsynced and then replaced atomically.

## Finisher commands

Run locally from C:/Users/neelj/nba-harness-h60, one test file at a time:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest tests/platformkit/execution/test_polymarket_certification.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_polymarket_certification_admission.py -q -p no:cacheprovider
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_fee_time_certification.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_fee_certification_gate.py -q -p no:cacheprovider
python -m scripts.platformkit.execution.polymarket_certification --help
python -m scripts.platformkit.execution.polymarket_certification --self-check
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/polymarket_certification.py scripts/platformkit/execution/polymarket_certification_checks.py scripts/platformkit/execution/polymarket_certification_fixtures.py tests/platformkit/execution/test_polymarket_certification.py tests/platformkit/execution/test_polymarket_certification_admission.py docs/evidence/harness/S399_polymarket_certification_2026-09-22.md --base master --spec docs/evidence/tracking/specs/S399_spec.md
```

A self-check exit of 3 is the expected state while the metadata units are
unreconciled; the per-file tests verify that the instrument exposes the
disagreement rather than hiding it.

Contract B review: additive new files only; no gate, threshold, production
caller, schema, deployment or sampling change; the two owner files are
untouched and their own test files pass unchanged. Contract Q review:
constructs only, no scored comparison, no trial, no corpus claim; the Q6 scan
runs inside contract preflight. All row Python files stay within 300 lines.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX 1b (round 1, five corrections: Opus CORRECTIONS + codex REJECT)

(1) module_fee accepted a float quantity or price (:46-62); it now refuses one
('fee inputs must be Decimal'). (2) candidate_rows passed RULE_RATE > 0 alone
while fee_rows passed the three-part underflow predicate (:95-96 vs :137-138);
positive_order is now read by both. (3) BLOCKING: 0.5 and 500 on both metadata
surfaces still reported 19 of 19 rows PASS; each agreement row now also
requires the selected limit to be a dated fixture limit (after: both MISMATCH,
with an uncovered_<kind>_limit count). (4) BLOCKING: candidate_fee returned
-0.05 for base -1000, quantity 1, price 0.5; a negative base fee, quantity or
computed fee now raises an exact reason, counted as refusal_candidate. (5) The
stale spec byte count was re-measured in fix 1f.

## FIX 1d (codex round 2: the remaining BLOCKING item -- admission)

checks:96 admitted with the FIXTURE's limit, not the selected one. MEASURED
before, selected tick 0.01: row tick_0001_on_grid (price 0.123) reported PASS /
'admitted' under rule 'limit 0.001'. Admission now uses the SELECTED limits (a
missing one refuses, never falls back); the dated table keeps its verdicts in a
labelled family (tick_fixture / size_fixture, cross_limit). MEASURED after,
same row: MISMATCH (OFF_GRID), refusal_tick 8 -> 9, tick_fixture still PASS.
The headline moved 78 -> 95 checks and 39 / 36 -> 55 / 37 (see Construct
results); the new MISMATCH is tick_001_off_grid, which AMENDMENT 2 ratifies.

## FIX 1e-1h (round 3: the bound, finiteness, ERROR vs MISMATCH, divisibility)

1e (Opus). MEASURED before: minimum_tick_size "0" reached value % bound and
raised an uncaught decimal.InvalidOperation, so the CLI died at exit 1;
"-0.001" silently ADMITTED 3 of 10 tick rows (Decimal modulo takes the
dividend's sign) and "-5" admitted 3 of 7 size rows. One guard after the parse
now returns 'selected <kind> limit is not positive'; after: 0 admitted,
refusal_tick 10, refusal_size 7, exit 3 with the report. 1f (codex).
decimal_string also asked math.isfinite(), which coerces to float: MEASURED
before, '1e10000' was refused 'non-finite decimal' though it is finite.
Finiteness is now Decimal.is_finite() alone; NaN / Infinity / -Infinity still
refuse.

1g (Opus). A broken SELECTED limit rendered as a venue MISMATCH: MEASURED
before, minimum_tick_size None gave 10 MISMATCH selected rows with ERROR 1. A
reason starting 'selected limit: ', or naming a limit that is not positive, is
now ERROR (after: 10 ERROR, report ERROR 11 / MISMATCH 36); the admission path
reads the limit through require_field (missing count 1 -> 2); and
select_market's two unreachable counters are dropped, the CLI JSON carrying the
reason.

1h (codex). A finite POSITIVE selected tick could still crash instead of
deciding: MEASURED before, limit '1e-1000000' with value '0.123' passed
is_finite() and then raised decimal.InvalidOperation (DivisionImpossible) at
value % bound, leaving no verdict. Divisibility is now the context-free integer
test (vn * bd) % (bn * vd) == 0 over Decimal.as_integer_ratio() -- the module's
only Decimal modulo deciding a verdict. MEASURED after: that bound ADMITS 0.123
(123e-3 is an exact multiple of 1e-1000000), bound '1e10000' refuses it
OFF_GRID with refusal_tick 1, neither raises, and certification completes at 95
checks; the headline is unchanged.

## NOT VERIFIED

Addressed to the owner of venue_fees.py and fee_time_certification.py.

- The UNITS of maker_base_fee and taker_base_fee. The probed sports market
  reports 1000 for both. Neither candidate reading -- basis points of notional
  or a rate in units of 1e-4 -- reproduces the module's numbers, and nothing in
  the probe says which, if either, the venue means. No fee-netted figure on
  this venue can be stated until the owner pins this.
- The DATE and content of the published Polymarket fee schedule. The module
  cites a page retrieved 2026-09-01 with a sports rate of 0.05 and a zero maker
  fee; the 2026-09-22 probe was not a documentation fetch and cannot confirm,
  refresh or retire that citation. The maker rebate the module names is also
  unconfirmed.
- QUEUE PRIORITY and matching semantics. No public statement was retrieved and
  no test can establish priority from public data. Queue position is not
  estimated anywhere; only the sensitivity bound is stated.
- The unit of minimum_order_size, and whether the tick grid applies to both
  sides and to every market of a neg_risk event.
- The umaResolutionStatuses vocabulary, resolutionSource, feeSchedule, feeType,
  feesEnabled, seconds_delay, accepting_orders, end_date_iso and
  game_start_time VALUES: the probe returned the field names only.
- The settlement and end-of-market time rows are CONSTRUCTS. No resolved
  Polymarket market, no state archive final time and no real disagreement rate
  was measured; the counts describe the fixture, not the venue.
- The one-second trade timestamp resolution is recorded from the S397 payload
  facts and was not re-measured here.
- Whether any of this is reproduced on master by the verifier, and lane_commit
  creation.
