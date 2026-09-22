# S378 fee certification gate

PREPARE: candidate implemented; independent acceptance remains pending.
Local machine: Windows, C:/Users/neelj/nba-harness-h35, master-based worktree.
All checks are constructed fixtures. No archive, network, or pod was used.

## Binding before-condition

Read `docs/evidence/tracking/specs/S378_spec.md` first, then read the landed
certification module before running the required CLI. Exact output excerpts:

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h35\scripts\platformkit\execution\fee_certification_gate.py' because
it does not exist.
usage: fee_time_certification.py [-h] [--self-check]

S364 dated fee constructs and counts-only capture clock diagnostics.

options:
  -h, --help    show this help message and exit
  --self-check  check dated synthetic fee fixtures
```

The file lookup failed as required; the CLI exited 0. The gate did not exist.
The landed self-check reproduced check_count=39, finding_count=4 with no
exceptions. The denominator includes every whole, partial, and increment-sum
check across the 19 dated fixtures; none was excluded.
No REAL ROW is specified. The first test consumes all landed fixtures through
certify, default refusal, bounded permission, and conservative fee conversion.

## Landed interfaces read before coding

Input source: `scripts/platformkit/execution/fee_time_certification.py`,
11920 bytes. Public function signatures quoted exactly:

```python
def certify_fees(fixtures: Iterable[FeeFixture] = FEE_FIXTURES) -> dict:
def clock_skew_report(rows: Iterable[Mapping]) -> dict:
def main(argv: list[str] | None = None) -> int:
```

Only `certify_fees()` is invoked by the gate. Its report is:

```text
fixture_date: str; schedule_date: str
check_count: int; finding_count: int
checks: list[dict]; findings: list[dict] (every non-PASS check)
exception_counts: dict[str, int]; status: PASS | FINDINGS
check: fixture, stage, expected, actual, status
whole/partial checks additionally cite source_line and rule
partial checks additionally contain increment and expected_increment
ERROR checks contain exception instead of actual
```

The imported fixture dataclass provides name, schedule, contracts, price,
expected, checkpoints, fixture_date, schedule_date; quantities and expectations
are strings. `FEE_FIXTURES` and `RULES` supply coverage and fixture-set identity.
The gate validates their report; it does not implement schedule calculations.

Input source: `scripts/platformkit/execution/venue_fees.py`, 8935 bytes.
Its public signatures, reached indirectly by the landed certification, are:

```python
def fee_kalshi_taker(contracts: float, price: float) -> float:
def fee_kalshi_maker(contracts: float, price: float) -> float:
def fee_polymarket(mode: str, notional: float, price: float) -> float:
def expected_value_after_fees(p_model: float, price: float, side: str,
                                venue: str, mode: str) -> float:
```

The gate imports this module only to locate its source bytes. The landed
certification invokes the first three functions, and converts their outputs
to decimal strings. The fourth interface is included in the owner proposal
to preserve Decimal arithmetic throughout that public call path.
Input resolution is not applicable: both inputs are source text, not video.

## Implementation and identity

New module: `scripts/platformkit/execution/fee_certification_gate.py`.
`certify()` returns an immutable status with strict counts, repeated fixture
ids per failed check, mismatch classes, both hashes, and evaluation time in UTC.
It runs all checks anew, verifies coverage and duplicates, validates partial
chains against fixture expectations, and checks source identity before/after.
Unknown classes refuse bounded use. Source/report failures raise a counted
FeeCertificationError. Default refusal never returns bounded permission.

`require_certified("bounded")` authorizes Decimal("0.01") per order only for
the two known classes. The exact returned label is required for bounded fee
conversion and names both the bound and fee-module SHA-256. Callers must carry
that label with every bounded fee-netted figure. There are no such production
callers added by this PREPARE lane.

`conservative_fee()` uses Decimal(str(value)), rejects nonpositive and
non-finite fees, ceilings to a cent and then adds the authorized bound.
Arithmetic runs in a private Decimal context and the result is revalidated.
The explicit supported domain is at most 100 coefficient digits and positive
magnitudes from 1e-100 through 1e12. Outside-domain inputs or results raise a
counted refusal; they are not clamped. Fees are not converted through floats.
Decimal.is_finite() alone validates finiteness. The gate has no file writer.

Fee source SHA-256:
`ee612ef2190b22f971cd0643cdd429c200f57d242964822e03293c48dc5998ff`.
Fixture-set SHA-256:
`4294da6de91158bb8bfcaf1de0bc73b642ece6995838e13b7cdfb92399d6f811`.
The fixture digest covers canonical ASCII JSON of all dataclass fields sorted
by name plus RULES, with sorted keys and compact separators. A source change
invalidates outstanding status; changed loaded-source identity requires restart.

## Construct evidence and reproduction

Test: `tests/platformkit/execution/test_fee_certification_gate.py`.
Command: `python -m pytest tests/platformkit/execution/test_fee_certification_gate.py -q -p no:cacheprovider`.
Result: 64 passed. Only this per-file test was run (initial 60 passed; final 64).
Cases cover certified and both bounded classes individually/together, unknown
classes, malformed counts, duplicates, missing fields, partial-chain corruption,
NaN/infinity, absurd finite fees, exact cent boundaries, low-context precision,
stale hashes, mid-evaluation changes, both row permutations, labels and CLI.
The hash-change test injects the hash function and changes constructed source
bytes, converting a previously accepted certified verdict into a refusal.

The exact owner correction is in the local-only, gitignored file
`docs/research/organization-sprint/PROPOSED_S378_venue_fees_decimal_correction_2026-09-21.md`.
The local construct check executes its code block in memory through the landed fixtures:
39 checks, 0 mismatches. The unmodified owner module remains at 39 checks,
4 mismatches. The four failing checks are retained below for durable evidence:

| Fixture / stage | Before fee; increment | Corrected fee; increment |
| --- | --- | --- |
| maker_above / whole | 0.07 | 0.08 |
| taker_above / whole | 0.07 | 0.08 |
| sports_fraction / partial_1 | 0.018750000000000003; 0.012500000000000003 | 0.01875; 0.01250 |
| sports_fraction / partial_2 | 0.03125; 0.012499999999999997 | 0.03125; 0.01250 |

CLI: `python -m scripts.platformkit.execution.fee_certification_gate --help`
exited 0; the landed certification --help also exited 0.
CLI: `python -m scripts.platformkit.execution.fee_certification_gate --status`:

```text
{"checks_total": 39, "mismatches_total": 4}
CLI_EXIT=3
```

Read-only review found class-allowlist, partial-chain, and label-validation
defects during construction. All were corrected with regression coverage.
Owner-module diff check exited 0. The proposal remains ignored and must never
be included in lane_commit. Only the four spec-owned files were created.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, B and Q checked.
The shorter contract path in the request is absent in this worktree.
No scored comparison, deployment, reader schema change, or threshold change.
Construct coverage is exhaustive for the enumerated test cases, not a sample.

Preflight command: `python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/fee_certification_gate.py tests/platformkit/execution/test_fee_certification_gate.py docs/research/organization-sprint/PROPOSED_S378_venue_fees_decimal_correction_2026-09-21.md docs/evidence/harness/S378_fee_certification_gate_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S378_spec.md`.
Result: 9 PASS, 0 FAIL. The proposed check reports no --proposed diff supplied;
the owner correction is a replacement code block, not an applied patch.
No production writer exists in this lane; source files are the only outputs.

## FIX 1b

Read `_verdict_s378_1b.md` first and compared the local S378 spec with
`git show master:docs/evidence/tracking/specs/S378_spec.md`; neither has an
AMENDMENT block. This fix changes only the owned gate, test, and this memo.

1. BLOCKING finding 1: removed `import math` and `math.isfinite(number)`
   from `_number`; retained `Decimal.is_finite()` and every other check.
   Extended `test_no_float_arithmetic_in_gate` to reject calls into `math`.
   The verifier's minimal reproduction was run before editing:

   ```python
   import math
   from decimal import Decimal
   class ProbeDecimal(Decimal):
       def __float__(self):
           print('FLOAT_CONVERSION', str(self))
           return super().__float__()
   print(math.isfinite(ProbeDecimal('0.1')))
   ```

   Failing output: `FLOAT_CONVERSION 0.1`, then `True`.
   The extended AST test against the original module produced:
   `AssertionError: math calls can implicitly convert Decimal to float`;
   `1 failed, 63 passed in 1.18s`.
   After the exact module fix, the same per-file command produced
   `64 passed in 0.85s`. With the last probe line replaced by
   `print(ProbeDecimal('0.1').is_finite())`, output was only `True`:
   no conversion occurred. This corrects the earlier finite-validation claim.
2. NOTE finding 2: unknown-disagreement refusal and fixture classification
   were confirmed correct; no changes made to either behavior.
3. NOTE finding 3: source identity, bounded label, and fee refusals were
   confirmed correct; no changes made. The rerun of `--status` prints
   `{"checks_total": 39, "mismatches_total": 4}` and exits 3.
4. NOTE finding 4: reran the unchanged required command before editing:
   `python -m pytest tests/platformkit/execution/test_fee_certification_gate.py -q -p no:cacheprovider`.
   Output: `64 passed in 0.80s`. Python has a usable temporary directory in
   this environment; the verifier's initialization limitation did not recur.
5. NOTE finding 5: protected modules and the owner proposal were left intact.
   Final preflight results are recorded below. NOT VERIFIED remains last.

Both row `--help` commands exited 0. The landed certification `--self-check`
reported 39 checks, 4 known findings, and `exception_counts={}`, exiting 1.
The self-check findings remain in the owner-controlled module.
Only the row's per-file test, construct probes, CLIs and preflight were run.
FIX 1b preflight: the four-path command above passed 9/9, with 0 FAIL;
the verifier verdict file was excluded. No commit was created in this sandbox.

## NOT VERIFIED

- Independent verifier acceptance, production replay integration, and propagation
  of the label by downstream callers have not been exercised.
- The owner correction has not been applied; caller migration and compatibility
  outside the fixture checks have not been tested.
- External schedule accuracy, all possible fee inputs, real fills, and real
  fee-netted figures have not been evaluated.
- Provider-time parsing, as-of filtering, recovery, file-write crash behavior,
  and order queues are outside this module and were not exercised.
- Concurrent external source mutation beyond the before/after hash checks,
  hostile runtime monkeypatching, and environment-wide Decimal changes in
  other threads were not tested.
- No commit or pod action was performed; the pod remains outside this task.
