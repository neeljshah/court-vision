# S236 season-block partition premise result

Verdict: FALSIFIED under Q8. No season-block module, caller-side proposal,
season-block metric, or scored calibration comparison was produced.

## Sealed protocol

The preregistration was sealed before the live-corpus premise measurement:
`docs/evidence/harness/S236_season_block_partition_prereg_2026-09-04.md`.
Its pre-seal SHA-256 is
`C26751B85E039209C93B2B1890176267A32DB438A1B03E05C163EA73A89986FC`.
The measured distribution is archived in
`docs/evidence/harness/S236_season_block_partition_2026-09-04.json`.

## Q8 premise reproduction

Each read-only gate corpus was opened separately and every `corpus_unit` value
was counted. No row was filtered or dropped.

| sport | all gate rows | stated unit counts | measured unit counts | result |
|---|---:|---|---|---|
| NBA | 1814 | 2024-25: 1225; 2025-26: 589 | 2024-25: 1225; 2025-26: 589 | reproduced |
| MLB | 39162 | era_2010_2021: 27983; era_2022_2026: 11179 | era_2010_2021: 27983; era_2022_2026: 11179 | reproduced |
| soccer | 25834 | D1: 3366; E0: 4180; E1: 6072; F1: 3856; I1: 4180; SP1: 4180 | D1: 3366; E0: 4180; E1: 6072; F1: 3856; I1: 4180; SP1: 4180 | reproduced |
| tennis | 41886 | ATP: 25764; WTA: 8002 | ATP: 30616; WTA: 11270 | falsified |

The shared read-only function
`scripts/platformkit/combo/fwer_budget.py:77-90` caps its floor at the supplied
`n_corpora` for `n_corpora >= 2`; inputs 0 or 1 return the floor 2. All four
measured corpora retain the stated unit cardinalities of 2, 2, 6, and 2.
However, the spec explicitly required the listed live-gate
value counts to be reproduced. Tennis does not reproduce them, so Q8 closes
this row before a change or season-block measurement.

## S03 and s81 reconciliation

S03's 25764 ATP and 8002 WTA values are distinct rows with valid close joins
after ambiguous event identifiers are excluded. They are subset numerators,
not the full `corpus_unit` denominators. S03 itself records those denominators
as ATP 30616 and WTA 11270, which are the values in the live S202 tennis gate.

Likewise, `scripts/platformkit/eval_gate/s81_market_move.py:198` calls
`era_2022_2026` a one-unit corpus only inside its modern-close move-model
calculation. It does not describe the full MLB gate corpus. The full gate is
the two-unit 27983/11179 distribution reproduced above, consistent with S50's
full-corpus reading.

## Named inputs and code identity

All inputs are tabular, so resolution is not applicable.

| input | bytes | SHA-256 |
|---|---:|---|
| C:/Users/neelj/nba-track-a17/data/cache/combo/gate_corpus_nba.parquet | 201706 | 716F6F5F3F2181051E352936EFA60D616C9DE029A026B85CC585D6ED20CB0AAF |
| C:/Users/neelj/nba-track-a17/data/cache/combo/gate_corpus_mlb.parquet | 1645142 | AC60C9CB18958C20FF53D7D0B698700375B6A0CE15E7EF0ECD20FB730E0903BD |
| C:/Users/neelj/nba-track-a17/data/cache/combo/gate_corpus_soccer.parquet | 6053712 | E0D2F13E7A53B3ED578E81E38DB82F14BB6D3A71E31A9C7CB636D5B4C7E92BC6 |
| C:/Users/neelj/nba-track-a17/data/cache/combo/gate_corpus_tennis.parquet | 2745405 | 22D006F2B4F7A7186876E133508E1E9DDF14AF3570F1D20A73D73D1D3669D700 |

Read-only route identities: `scripts/platformkit/combo/fwer_budget.py`
(8726 bytes, SHA-256
073F81443820CE36741EF815B4F79B90FDAE5C6464FEFDEBF00B165977E6DD9F),
`scripts/platformkit/eval_gate/s81_market_move.py` (16538 bytes, SHA-256
5867A94F8312F83B5A9FCFB0D45058BD09B830E4C8FEA46B47CF6ED82CB8E6FF), and
`scripts/platformkit/eval_gate/s202_two_way_neff.py` (11845 bytes, SHA-256
A6690E56291EE8C0C3999AC732B9D68D5E64D67854FC5C116D771FAB086620AB).

## Contract self-check

- B1-B10: no schema, route, threshold, deployment, or data store changed.
- Q1: the protocol seal predates the premise measurement.
- Q2: no charged trial exists; no ledger was opened or written.
- Q3: the S236 bars were not changed or evaluated after the false premise.
- Q4 and Q9: not applicable because no scored calibration comparison was run.
- Q5: no AHEAD verdict exists.
- Q6: calibration language only.
- Q7: the four sports are the complete construct denominator.
- Q8: the false tennis value-count premise is named and closes the row.

No focused test was added or run because Q8 stops the specified change before
implementation. No register or ledger was touched.

## NOT VERIFIED

- Season-block counts and effective corpus counts were not measured.
- No CPCV audit was run.
- No season-block module was implemented.
- No caller-side proposal was produced.
- No focused S236 test was added or run.
