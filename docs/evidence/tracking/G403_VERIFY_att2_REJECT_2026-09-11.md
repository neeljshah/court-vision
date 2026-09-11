VERDICT: REJECT
Candidate: `b8ba5a0d7`; full parent diff, G403 spec, contract A/B/Q, evidence directory, all 30 controls, all round-8 cards, 30-card audit, and 115 disputed crops reviewed read-only.
PREMISE: PASS. Independent replay of the landed G400 bytes found 300 keys, 600 answers/20 archives, 299 paired rows, round 1 n=29, round 8 n=30, 125 centre gaps, 288 diameters, 115 reasons, and 8 redactions; no duplicate or missing binding ids.
REPRODUCED vs claimed: pooled kappa 0.750519; round-8 kappa 0.360465 with 19 agreements/11 disagreements and VISIBLE marginals 16/16; gap median 24.021 px, nearest-rank p90 292.139 px, linear-unrounded p90 287.385 px; diameter median 27.5 px. All match the memo/tables.
ACCEPTANCE-RAW: PASS. Exact 300/299/round counts and confusion integers reproduce; original labels/order/missingness/raw verdicts are unchanged (`G403_spec.md:23`; `answer_binding.csv`; `confusion_by_round.csv`).
ACCEPTANCE-CENTRE: PASS. All 125 gaps and 115 reasons remain, all 288 diameters reproduce, and no large gap is excluded (`G403_spec.md:24`; `gaps.csv`; `reason_categories.csv`).
ACCEPTANCE-CONTROLS: FAIL. The five `ACTIVE_PLUS_BENCH_BALL` renders draw both objects with the same `_ball` primitive and no visible bench/off-court cue (`g403_render.py:43-60`), yet bind VISIBLE to one (`control_answers.csv:4,10,16,22,28`). Under `instructions.md:17-18,25-27`, both are plausible; ambiguity is expressly NOT VALIDATED by `G403_spec.md:25`.
B1 PASS - reported diagnostics use the complete archived population, not a self-defining success subset.
B2 FAIL - `settled_label` previously exposed equal raw labels or `ADJUDICATED`; `g403_package.py:15-32,96-104` silently replaces that status domain with final G400 states. Eight existing cells change and no alias preserves reader behaviour (`shot_claim_audit.csv`; `pre_fix1b/shot_claim_audit.csv`). This is the contract's automatic non-additive-schema reject (`VERIFIER_CONTRACT.md:21`).
B3 PASS - every spec-named artifact exists; 357 input rows and 75 delivered digests resolve with zero mismatch in their declared byte domains.
B4 PASS - numerical headlines were independently rederived from raw archives; controls are labelled CONSTRUCT and not used to prove the raw diagnosis.
B5 PASS - controls are prepared only, unadministered, and no deploy/register/flag action appears in the diff (`G403 memo:22-23,42-44`).
B6 PASS - producer/reader search found no orphan; the only importing test is the focused G403 test.
B7 PASS - full 125-gap and 115-reason populations are retained; shot audit is exactly positions 5/15/25 per round.
B8 PASS - no fit/evaluate loop; constructed answers are explicitly not independent real-ball truth.
B9 PASS - denominators are unique joined observations: gaps 125/125 keys, reasons 115/115 keys, controls 30/30 ids.
B10 PASS - 13.75 px and 0.5-diameter bars are unchanged (`G403_spec.md:11,23-25`; memo:4,14,20).
Q1 PASS - prereg, amendment A1, and instructions seals recompute exactly; seal commits `72d02a0914` and `3580640355` precede measurement commit `d8e299b031`.
Q2 PASS - no scored comparison, trial selection, or charged threshold decision is made.
Q3 PASS - no bar moved and both p90 conventions are separately named.
Q4 PASS - retrospective diagnostic only; no OOS/CPCV claim is made.
Q5 PASS - no AHEAD or multi-corpus claim is made.
Q6 PASS - independent diff/current scan found zero non-opaque hits in candidate-added text, including zero in the added ledger row.
Q7 PASS - construct n is the exact exhaustive 6x5 catalogue; no uncertainty claim is inferred from n=30. Control validity separately fails acceptance above.
Q8 PASS - premise was remeasured first from the external landed G400 source; largest input read was 657,758 bytes.
TEST master `c0d188075`: `python -B -m pytest tests/platformkit/test_g403_ball_rater_controls.py -q -p no:cacheprovider` -> path absent, 0 tests, 0.00s.
TEST candidate: same command -> 11 passed in 0.79s. This is the only test file importing any touched G403 module.
LOC: `g403_build.py` 216; `g403_package.py` 216; `g403_q6_scan.py` 107; focused test 148. All <=300.
REPEAT/RECEIPTS: PASS - two runs return 0; 13 tables and 38 renders are byte-identical; saved repeat and digest manifests independently verify.
MEMO: PASS - begins with a disposition and ends with an explicit NOT VERIFIED section (`g403_ball_rater_failure_controls_2026-09-11.md:1,42-44`).
MINIMAL CORRECTION 1: retain the old `settled_label` semantics and add a new `final_state` column; update the equality test to target `final_state`, preserving an alias/status reader.
MINIMAL CORRECTION 2: add visible bench/off-court context that distinguishes the spare without exposing the answer key, then regenerate controls, repeats, hashes, and receipts.
PROPOSED LEDGER: `2026-09-11 | tracking | G403 | independent verification reproduced premise and diagnostic tables; REJECT because settled_label semantics changed without an alias and one constructed control family is visually ambiguous | REJECT`
NEW GAP: saved `q6_scan.json` has 29 files but overlaps only 10 of the candidate's 19 touched text paths; memo lines 25/27 overstate saved scan scope. Independent verifier scanning closes candidate-added-text risk but not the receipt wording.
NEW GAP: the focused test is absent on master `c0d188075`, contrary to contract A1; candidate-only execution passed and this does not add another rejection basis.
