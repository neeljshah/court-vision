# S384: exact decimal inventory quantity

Status: FIX 1b implemented and locally validated; construct evidence only.
AMENDMENT 1 accepts every exactly-zero recorded fee; no policy conflict remains.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h44.
Owned paths: scripts/platformkit/execution/markout_causal.py,
tests/platformkit/execution/test_markout_quantity_decimal.py, and this memo.
Binding spec: docs/evidence/tracking/specs/S384_spec.md.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, sections B and Q.
The shorter contract path in the dispatch does not exist in this checkout.

## Original candidate before-condition (prior lane evidence)

Ran the spec's Python inspect command, using PowerShell Select-String with
LineNumber in place of unavailable grep. Its complete float( match output was:

```text
286:    assert markout_strict(fill, {"ts": float("nan"), "mid": 0.70}).reason == "mark_ts_missing"
```

There is no literal float( conversion of a quantity, fee or size in this module.
The indirect conversions are these exact original source lines:

```text
132:    fee = finite(fill.get("fee_units"))
158:    price, mid = finite(price), finite(mid)
166:    return MarkoutResult(gross - abs(fee), None, None, finite(fill.get("qty")))
```

The read dependency markout_causal_windows.py implements finite with
`out = float(value)` at line 42. A constructed fill with qty="1e-999",
fee_units="0.01", price="0.55", side="yes", ticker="T1", fill_ts=0,
fee_schedule_version="construct", and mark {ticker:"T1",ts:30,mid:"0.6"}
returned this before editing:

```text
MarkoutResult(value=0.03999999999999993, reason=None, exit_fee_units=None, remaining_inventory_qty=0.0)
```

No REAL ROW is supplied by S384; the new first test uses the literal "1e-999"
from its reproduction in an explicitly constructed fixture.
Baseline commands: python -m pytest <path> -q -p no:cacheprovider, separately:

| Row | Path under tests/platformkit/execution/ | Before |
| --- | --- | --- |
| S343 | test_markout_causal.py | 31 passed |
| S354 | test_venue_time.py | 65 passed |
| S356 | test_markout_mark_selection.py | 10 passed, 18 subtests passed |
| S369 | test_markout_identity_units.py | 79 passed |

## Landed imports read before coding

Read the full modules markout_causal.py, markout_causal_windows.py,
venue_time.py, markout.py and entry_timing/study.py under
scripts/platformkit/execution/. Exact relied-on definitions:

```python
# entry_timing/study.py
def cluster_boot_ci(values: list[float], clusters: list, n_boot: int = 500,
                     seed: int = 7) -> tuple[float | None, float | None]:
# markout.py
UNKEYED_CLUSTER = "__unkeyed__"
# venue_time.py
def parse_venue_time(value: object) -> float | None:
# markout_causal_windows.py
def delay_summary(delays: Sequence[float], n_fills: int) -> Dict[str, Optional[float]]:
def finite(value: Any) -> Optional[float]:
def partition_windows(fill_ts: float, horizons: Sequence[float],
                       max_wait_s: float) -> List[Tuple[float, float, bool]]:
def probability_decimal(value: Any) -> Optional[Decimal]:
def same_identity(fill: Dict[str, Any], tick: Dict[str, Any]) -> bool:
def select_candidate(ticks: Sequence[Dict[str, Any]], times: Sequence[Optional[float]],
                      indices: List[int], max_book_age_s: Optional[float]) -> Tuple[Optional[int], Optional[str]]:
def validate_horizons(horizons_s: Sequence[float]) -> Tuple[float, ...]:
def validate_max_wait_s(max_wait_s: float) -> float:
def validate_book_age_s(value: Optional[float]) -> Optional[float]:
```

## Reader audit

Direct readers found in the causal module and test_markout_causal.py,
test_markout_mark_selection.py, test_markout_identity_units.py and
test_fractional_chain.py. The latter requires JSON serialization and the legacy
float field. No external fixed-length unpacking or positional constructors found
in the scoped scripts/tests search. New fields must therefore remain JSON-safe.

## Implemented behavior

- Added remaining_inventory_qty_dec (exact decimal string) and float_field_lossy
  (integer 0/1) to MarkoutResult, retaining the four existing fields and defaulting
  the additions. Decimal.from_float compares the final legacy quantity exactly;
  decimal "200.47" is correctly flagged because binary float cannot represent it.
- Quantity and fee parsing uses Decimal(str(x)) through the read shared parser.
  Invalid inputs produce reason codes counted by summary_strict. Extra parser
  exceptions increment _PARSE_REFUSALS and become counted summary refusals.
- Prices and fees are subtracted in an isolated Decimal context. The existing
  value remains a float converted only after subtraction. Nonzero results that
  underflow to a legacy zero are refused as markout_unrepresentable.
- Fee magnitude above one probability unit is refused; quantity overflow of the
  finite legacy float is refused. Decimal arithmetic requiring more than 10000
  digits is refused as decimal_precision_unsupported. Nothing is clamped.
- n_float_field_lossy counts scored fill-horizon observations, not unique fills.
  n_intents now requires a non-negative int, excluding bool, float and strings.
- No mark selection, horizon, ordering, identity or time parser was changed.
  No quantity scaling or accumulation is performed by this API; tests accumulate
  its exact string outputs with Decimal in both fill orders.

## Amendment 1

Read AMENDMENT 1 via `git show master:docs/evidence/tracking/specs/S384_spec.md`;
the worktree's spec copy lacks the amendment. Recorded fee inputs accept every
exact zero, including signed zero and any exponent form. Negative, non-finite,
boolean and unparseable fees remain refused and counted. Existing zero
quantities remain valid under S384's negative-only quantity exclusion.

## Final construct validation

Each command was run separately with python -m pytest <path> -q -p no:cacheprovider.
All four baseline test files are unchanged.

| File under tests/platformkit/execution/ | Final result |
| --- | --- |
| test_markout_quantity_decimal.py | 76 passed |
| test_markout_causal.py | 31 passed |
| test_venue_time.py | 65 passed |
| test_markout_mark_selection.py | 10 passed, 18 subtests passed |
| test_markout_identity_units.py | 79 passed |

Total: 261 test cases plus 18 subtests, all constructed inputs.
The 76 new cases cover tiny/fractional quantities, exact sums in both orders,
binary loss, JSON compatibility, invalid/missing amounts and reason counts,
finite overflow, huge integers, exact fee arithmetic, isolated Decimal context,
legacy result underflow, bounded precision, strict/large intent counts, and
10 recorded-zero fee representations.
Earlier new-test runs passed 62 and 63 cases before review cases were added.

CLI checks: python -m scripts.platformkit.execution.markout_causal --help exits 0
and prints "markout_causal self-check OK". It is an existing demo entry point,
not an argument parser; no CLI was added. contract_preflight --help exits 0
and displays its usage. The module without arguments also prints the self-check
success message and exits 0. git diff --check exits 0.

Line counts using len(text.splitlines()): module 293, new tests 202.
Both Python files and this memo are ASCII. Only the three owned paths changed.
Contract preflight: 9 PASS, 0 FAIL across the three owned paths.
Checks: vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact and row_duplication.

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/markout_causal.py tests/platformkit/execution/test_markout_quantity_decimal.py docs/evidence/harness/S384_markout_quantity_decimal_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S384_spec.md
```

## FIX 1b

1. BLOCKING: the verifier's encoded-zero defect reproduced before the fix:

   ```text
   input fee_units='0' -> reason=None, count={}
   input fee_units='0e-10001' -> reason='decimal_precision_unsupported', count={'decimal_precision_unsupported': 1}
   ```

   The code now canonicalizes zero-valued price, mid and fee operands to
   Decimal(0) before calculating precision. Nonzero arithmetic and the existing
   precision limit are unchanged. After the fix the same reproduction prints:

   ```text
   input fee_units='0' -> reason=None, count={}
   input fee_units='0e-10001' -> reason=None, count={}
   ```

2. CORRECTION: reproduced the obsolete memo claims at lines 3, 108-115 and 155.
   Before: `Status: NOT VALIDATED pending the zero-fee policy conflict below.`
   The presence check printed `memo Amendment 1 recorded: False`.
   Recorded AMENDMENT 1, removed the conflict section and zero-fee NOT VERIFIED
   bullet, and documented the reproduced defect and its fix above. After:
   `memo Amendment 1 recorded: True`; `obsolete zero-fee claims absent: True`.

3. NOTE: added test_recorded_zero_fee_scores_without_refusal with 10 cases:
   ordinary, fractional and exponent-encoded strings; large positive and
   negative exponents as strings and Decimal inputs; and signed zeros.
   Every case must score and have an empty refusal count, including the
   required fee_units="0e-10001" case. The exact per-file command first printed
   `6 failed, 70 passed`; after the code fix it printed `76 passed`.
   The original tiny-positive-fee test and all confirmed behavior remain intact.

The before-fix inspect scan found legacy_qty = float(qty) at line 159,
legacy_net = float(net) at 162, Decimal.from_float at 166, and the demo's NaN
timestamp at 283. The first two remain final compatibility conversions;
no quantity or fee is parsed through a float by this fix.

All five prescribed pytest commands ran with repository fixtures enabled,
one file at a time using -q -p no:cacheprovider. No temporary-directory
workaround or fixture exclusion was needed. Only the three owned files changed.

## NOT VERIFIED

- No real archive, network, pod, deployment or measured diagnostic was exercised.
- test_fractional_chain.py was surveyed as a reader but not executed: validation
  was restricted to the new file and four acceptance files.
- Existing time-parser sub-microsecond truncation and mark-mid float conversion
  were not changed; this row freezes mark, window, ordering and identity logic.
- No as-of query, deduplication, recovery, file writing or scaling path exists in
  the changed API, so new tests do not exercise those operations.
- External or deployed readers beyond the scoped repository search were not run.
- The FIX 1b candidate has not had a further independent verifier pass.
- No commit was created; files remain on disk for lane_commit.
