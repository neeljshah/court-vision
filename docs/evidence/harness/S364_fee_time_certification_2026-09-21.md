# S364 fee and timestamp certification -- PREPARE ONLY

Vocabulary follows contract Q6; automated scan required.

Prepared locally in C:/Users/neelj/nba-harness-h22 on 2026-09-21. All execution
uses in-memory constructs because this row authorizes preparation only.
No archive was opened, no network request was made, and the pod remained OFF.

The binding before-condition was run before construction:

```text
ls scripts/platformkit/execution/fee_time_certification.py
ls : Cannot find path 'C:\Users\neelj\nba-harness-h22\scripts\platformkit\execution\fee_time_certification.py' because
it does not exist.
Exit code: 1
```

## Scope and provenance

The new module imports the landed venue fee functions and venue time parser.
No pre-existing module is edited. The only created files are:

- scripts/platformkit/execution/fee_time_certification.py
- tests/platformkit/execution/test_fee_time_certification.py
- docs/evidence/harness/S364_fee_time_certification_2026-09-21.md

Direct specification and implementation inputs opened for this row are listed
below. Paths are relative to C:/Users/neelj/nba-harness-h22; resolution is not
applicable to text source. Fixture inputs live in the two new Python files,
so reproduction requires no ignored fixture, archive, or external schedule.

| Input | Bytes | Resolution |
| --- | ---: | --- |
| docs/evidence/tracking/specs/S364_spec.md | 2544 | n/a |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 12532 | n/a |
| docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md | 11891 | n/a |
| scripts/platformkit/execution/venue_fees.py | 8935 | n/a |
| scripts/platformkit/execution/venue_time.py | 2029 | n/a |

The fixture date is 2026-09-21; the inherited schedule retrieval date is
2026-09-01. Each fee fixture carries its rule, local source line, quantities,
price, expected whole-order fee, and any cumulative partial checkpoints.
The table covers integer and fractional quantities, zero quantity, prices
at 1, 50 and 99 cents, and immediately below, exactly at, and immediately
above a cent-ceiling boundary. The Polymarket sports example and fractional
sequence check the other schedule cited in the same canonical module.
Expected values are literal strings. Independent Decimal arithmetic in the
test validates the table against that cited text; it is not a runtime fee
calculator. Runtime checks call only the imported canonical functions.

## Construct results and findings for the fee owner

The per-file test command passed 89 tests. The CLI help command exited zero.
The fixture self-check executed 39 checks across 19 fixtures: 35 PASS and
4 MISMATCH, with no caught exceptions. Its exit code is 1 and status is
FINDINGS; this is not certification of the fee implementation.

| Fixture / stage | Expected | Observed | Finding |
| --- | --- | --- | --- |
| maker_above / whole | 0.08 | 0.07 | Intermediate rounding hides the increment above the ceiling boundary. |
| taker_above / whole | 0.08 | 0.07 | Same ceiling discrepancy for the taker coefficient. |
| sports_fraction / partial_1 cumulative | 0.01875 | 0.018750000000000003 | Exact-decimal discrepancy after canonical float conversion. |
| sports_fraction / partial_2 increment | 0.01250 | 0.012499999999999997 | The preceding discrepancy carries into the next increment. |

The partial sequences' increments sum to the expected whole-order amounts.
Every cumulative and incremental discrepancy is still reported; a correct
sum never erases an intermediate mismatch. Exact comparisons intentionally
retain small representation discrepancies and do not equate them with a
cent-level discrepancy. Canonical schedule limitations remain unresolved:
the sports-series exception, the cap, and independent maker-ratio confirmation
are explicitly not certified by these inherited-text constructs.

## Clock semantics

The in-memory report consumes the landed top-level capture fields
request_start_ts, response_end_ts, tick_start_ts, record_type and created_time.
Unsuffixed timing aliases are also accepted. Native fields take precedence
even when missing or invalid. Explicit source selects the source group;
otherwise venue does. Missing source remains a null group, never another venue.

Every input row remains in the total count. Malformed rows, missing fields,
invalid timestamps, and non-finite durations have explicit counts. Missing
receipt times remain in null-hour groups. Empty distributions contain null
durations, never zero. All parsing goes through parse_venue_time.

Trade skew is receipt minus created_time; latency is receipt minus request
start for all record types. Groups use the UTC receipt hour and report count,
minimum, median, nearest-rank p95 and maximum in seconds. Negative skew,
negative latency and request-before-tick each have independent counters.
Drift compares successive available hourly trade-skew medians for the same
source, dividing by elapsed hours across gaps. Absolute drift strictly over
one second per hour is flagged; exactly one is not. This statistic can also
reflect tape age and polling behavior, so it does not isolate physical clock
offset. No prices are accessed or emitted by the clock report.

Constructs cover all flags, both drift directions, threshold equality, gaps,
source isolation, missing and non-finite inputs, four- and five-digit time
fractions, timezone offsets, zero epochs, native-field precedence, and row
permutations. No real clock distribution was computed.

## Finisher commands

Run locally from C:/Users/neelj/nba-harness-h22, one test file at a time:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest tests/platformkit/execution/test_fee_time_certification.py -q -p no:cacheprovider
python -m scripts.platformkit.execution.fee_time_certification --help
python -m scripts.platformkit.execution.fee_time_certification --self-check
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/fee_time_certification.py tests/platformkit/execution/test_fee_time_certification.py docs/evidence/harness/S364_fee_time_certification_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S364_spec.md
```

Self-check exit 1 is expected while the documented canonical discrepancies
remain. Per-file tests verify that the instrument exposes those findings.
Contract preflight passed all nine checks, including vocabulary, line counts,
new-file schema checks, and artifact preservation. Fixture ordering also covers
tied identifiers with different expectations or partial sequences.

Contract B review: additive new files; no gate, threshold, production caller,
schema, deployment, or sampling change. Missing timing evidence is counted
without removing rows from the total. Q review: constructs only; no scored
comparison, trial, or independent-corpus claim. The automated Q6 scan is part
of contract preflight. All row Python files must remain within 300 lines.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED

- Current official fee schedule, sports-series exception, cap, and maker ratio.
- Actual venue fractional-quantity admissibility or per-partial receipt fees.
- Real capture clocks, synchronization drift, or latency distributions.
- Any measured calibration, execution, or subsequent observation result.
- Production integration, deployment, activation, or pod execution.
- Master-side verifier reproduction and lane_commit creation.
