# G136 Basketball recensus: blind second pass

## 1. Blind self-agreement (reported first)

The fixed seeded re-judge subset has 42 unique frames.  The independent
second-pass table was committed at
`7e7ba78d76d800c3a8a6f977c452490b8266ef81` before the first-pass source
judgements were opened or joined.  Every frame was decoded from its named
source clip at the manifest's zero-based frame index and judged using the
pre-registered visible-corner criterion.

The primary reachability-decision agreement is **28/42 = 66.7%** (Wilson 95%
CI **51.6% to 79.0%**).  Exact agreement on the recorded 0--4 visible-corner
count is **27/42 = 64.3%** (Wilson 95% CI **49.2% to 77.0%**).  The one-row
difference is a partial-corner judgement where both passes remained
unreachable.

The second-pass content is the fixed shuffled manifest in
`g130_recensus/second_pass_source_judgements.csv`.  Its canonical
`reachable_four_corners` field was normalized to the pre-existing `0`/`1`
schema in the follow-up compatibility-only commit
`f89eb2bbfa2b55e5bc66920a81076ca26c9db189`; the source-decoded corner counts
and reachability decisions are unchanged from the pre-join commit.

## 2. First-pass reachability census

The complete first pass contains 210 unique audit IDs, of which 97 have four
visible paint corners.  Its reachability figure is therefore **97/210 =
46.2%** (Wilson 95% CI **39.6% to 52.9%**).

This is not a precise reachability claim.  The independently produced
agreement is below roughly 80%, so the first-pass figure is retained only as
an explicitly caveated census estimate for orchestrator adjudication.

## 3. Required comparison

The 46.2% first-pass census is 20.6 percentage points below the retracted
G111 figure of 66.8%, and 12.4 percentage points above G126's 45-frame
reweighted estimate of 33.8%.  Neither comparison rehabilitates G111; the
blind agreement result above is the controlling reliability evidence.

## Method and recomputation

- The protocol and sample order were fixed in
  `g130_recensus/review_protocol.md` and
  `g130_recensus/rejudge_selection_manifest.json` before the second pass.
- The source rows are in
  `g130_recensus/second_pass_source_judgements.csv`; every one of its 42
  `audit_id` values is unique and belongs to the manifest.
- The complete comparison and numerator/denominator are recomputable from
  `g130_recensus/first_pass_source_judgements.csv` by joining on `audit_id`.
- Wilson intervals use z = 1.959963984540054.  The first-pass count
  distribution is 113 rows with zero visible corners and 97 rows with four;
  the second pass has 29 zero-corner, 8 two-corner, and 5 four-corner rows.
- No threshold, coordinate contract, rung, verdict, sample seed, or source
  clip declaration was changed.  No pod mutation or code deployment occurred.

## NOT VERIFIED

- The 46.2% first-pass figure is not independently established as a precise
  population reachability value because the blind re-judge agreement is below
  80%.
- This lane does not adjudicate or alter the consolidated REACH verdict.
- No additional second reviewer, alternate source corpus, or live pipeline
  behaviour was evaluated.
