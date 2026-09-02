# G107 preregistration: jump-statistic policy measurement

Date: 2026-09-02. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`,
including A7 and section B. This preregistration is committed before the first
pod metric is read. It authorizes a read-only calculation only; it does not
change `tracking_harness.py`, any bar, any verdict, the coordinate contract, a
pod file, or a pod process.

## Population and eligibility, fixed before scoring

The population is every readable, nonempty `tracking_data.csv` in the pod
`data/tracking/*/` corpus at one read-only snapshot. A report is **eligible for
the jump-gate denominator** only if the current harness reaches the spatial
jump-statistic computation: it has at least 30 distinct frames, declares
`coordinate_space=court_feet`, has usable player `track_id`, `frame`, `x`, and
`y` values, and has a unique positive modal same-track frame stride with at
least one pair at that stride. Coordinate-contract rejections,
`INSUFFICIENT_DATA`, metric-local tables, empty tables, and tied/no-pair modal
stride cases are separately enumerated but excluded because their jump statistic
is not computed. Eligibility never depends on a displacement, a candidate
result, or a present/past harness verdict.

The impact denominator is the eligible-report count, separately stated beside
the total pulled. The row is not complete unless this count is at least 10.

## Fixed pair and bars

For every eligible table, a pair is a consecutive row after sorting player rows
by `track_id, frame`, restricted to a positive frame gap equal to that table's
unique modal positive same-track gap. Its value is the Euclidean court-feet
displacement. The physical exceedance bar is the existing sport-specific jump
bar: basketball 6 ft; tennis, soccer, and football 8 ft; baseball-family 10 ft.
These are analysis labels only; this row moves none of them.

## Candidates and decision rules, fixed before scoring

All candidates are measured on the same eligible population. "Flags" means the
candidate reports the table as either a candidate failure or an explicit warning;
the candidate table records which. Verdict impact is compared with the current
pod harness verdict reconstructed on the same source table, and is reported as
PASS-to-FAIL, FAIL-to-PASS, unchanged PASS, and unchanged FAIL over eligible
reports.

| ID | Candidate | Pre-registered rule |
|---|---|---|
| C0 | Legacy p95 | Candidate FAIL when modal-stride pair p95 exceeds the existing sport bar. This is a diagnostic counterfactual only; legacy raw-row p95 remains separately described where available. |
| C1 | High quantile p99.9 | Candidate FAIL when modal-stride pair p99.9 exceeds the existing sport bar. |
| C2 | Max with tolerated exceedances | Candidate FAIL when more than four modal-stride pairs exceed the existing sport bar (equivalently, fifth-largest pair exceeds the bar). |
| C3 | Count gate | Candidate FAIL when five or more modal-stride pairs exceed the existing sport bar. This is intentionally equivalent to C2 and tests the count interpretation directly. |
| C4 | Rate gate | Candidate FAIL when at least 0.50 percent of modal-stride pairs exceed the existing sport bar. |
| C5 | Warning max plus rate verdict | Emit WARNING when the modal-stride maximum exceeds the existing sport bar; candidate FAIL only when C4's 0.50 percent rate condition holds. |

No candidate may be selected because of its pod impact. A candidate is
**disqualified** if it does not flag both known-real defects: (1) G96 nyYk's
56.389551-ft modal-stride coordinate defect and (2) G82 basketball's 16 real
10--29-ft oversized steps, at 0.0455 percent prevalence. C5's WARNING counts
as its flag for this disqualification check; its rate verdict is reported
separately. The recommendation rule is: among non-disqualified candidates,
prefer a policy that leaves isolated coordinate defects visible as explicit
warnings and uses a rate-based verdict only for broad contamination. If none
both flags the known defects and separates isolated from broad contamination,
recommend no gate change.

## Required durable outputs

The final memo will name this preregistration, list every eligible and excluded
pod table with its deterministic reason, show candidate results per eligible
table, state the total pulled and eligible denominator, score each candidate on
both known defects, state one recommendation, and include A7 and B1--B10
self-checks plus a NOT VERIFIED list.
