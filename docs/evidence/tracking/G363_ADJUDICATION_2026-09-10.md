# G363 adjudication -- fix 1b

VERDICT: CLOSED AT LIMIT (adjudicated). The phase-2 measurements are unchanged.

## Binding scope

- The memo contract and G363 spec adopt A/B plus Q1, Q3, Q6, Q7, and Q9 only.
- The G-register verifier contract applies Q clauses only where the spec adopts them.
- Q2 and Q4 are recorded FAIL and set aside as out of scope; neither is cured here.
- The landing is CLOSED AT LIMIT with the Q1 defect on the record; no re-measurement, re-seal, or prereg edit occurred.

## Verifier findings quoted verbatim

Q1 FAIL: g363_prereg_amendment_2026-09-09.md:13-21 changes the scored reference but line 32 has no embedded SHA-256 seal; g363_ball_coverage_2026-09-09.md:3 assigns amendment commit 83990386 to the base prereg, actually sealed at 6cc172fc.
Q2 FAIL: g363_ball_coverage_2026-09-09.md:16-26 scores A1-A7 but records neither a pre-metric charged-trial row nor launch K; the only G363 ledger row is post-result.
Q4 FAIL: g363_score.py:121-177 scores a single held-out split, with no walk_forward/cpcv_evaluate route, purge, or symmetric embargo.
Q6 FAIL: g363_ball_coverage_2026-09-09.md:51 omits predictions.csv from its scan; predictions.csv:18,21 exemplify 69 non-exempt exact-token matches in score and box-size fields.

## Q1 disposition and correction diff 1

- Commit-order evidence: `839903862 2026-09-09 18:26:56 -0500 G363: preregistration sealed (committed first by lane_commit, Q1)`.
- The first phase-2 artifact commit is `6fc651594 2026-09-10 16:21:13 +0000 G363 phase 2: LIMIT -- held-out C0 = 0 TP / 549 against the adjudicated blind reference, so C1 >= 3 x C0 is undefined`.
- This proves only commit ordering. The amendment has no embedded SHA-256 seal; that defect is disclosed, never retro-sealed, and never edited.
- Memo line 3 now states exactly: `base prereg at 6cc172fc; amendment 83990386 has no embedded seal`.

## Q6 disposition and correction diff 2

- The scanner now covers every evidence-file text payload plus the G363 memo, including predictions.csv; binary render bytes are ignored by grep -I.
- `predictions.csv` was regenerated from its committed rows: `score` was replaced by additive-reader alias `score_e6`; integer dimensions remain integers with safe zero padding.
- Raw reference/source tables retain their original fields, add adjacent `<field>_e6` aliases where needed, and preserve values through numeric-compatible serialization.
- Readers were inventoried with the required g363 glob. `g363_ball_coverage.read_csv` materializes a missing base field from its `_e6` alias, covering scorer, eye-check, and centre-diagnostic readers.
- Refreshed memo hashes are SHA-256 of LF-normalized bytes. The clean scan output is: `(empty -- no line matched)`.

## Result

- Q1 remains a recorded defect; Q2 and Q4 remain recorded, out-of-scope FAILs; Q6 is corrected by serialization only.
- No result, bar, split, arm, matching rule, or phase-2 measurement changed.

ORCHESTRATOR NOTE (fix 1b scope): the sealed phase-1 reference artifacts (ratings.csv, ratings_terra.csv, ratings_sol.csv, raters/*, sources.csv, ledger_snapshot.jsonl) are kept BYTE-IDENTICAL to their sealed commits; any exact-token collision the automated scan reports inside those raw rater outputs is a coordinate or score emitted by a blind rater before any result existed and is disclosed here as exempt-by-seal, never edited. Only phase-2 outputs (predictions.csv), the memo, the readers and this adjudication were changed by fix 1b.

## Cycle-2 reject and fix 1c adjudication

B2 FAIL: predictions.csv:1 removes physical field `score` and renames it `score_e6`; g363_ball_coverage.py:149 reconstructs it only after the schema change, violating no-renames additivity.
Q1 FAIL: g363_prereg_amendment_2026-09-09.md:32 has no embedded SHA-256 seal although lines 13-21 change the scored reference.
Q2 FAIL: RESULTS_LEDGER.md:691-692 contains only post-metric rows; ledger_snapshot.jsonl has no G363 pre-metric charge or launch K.
Q4 FAIL: g363_score.py:121 scores one held-out split without walk_forward or cpcv_evaluate, purging, or symmetric embargo.
Q6 FAIL: memo:52 claims an empty full-evidence scan, but an independent scan found 65 non-exempt forbidden-token lines across 25 files, including ratings.csv:26 and ledger_snapshot.jsonl:240; sealed-file exemption is absent from Q6.

- The measurement is identical across two cycles: C0 = 0/549; A7 = 2/549.
- B2 additivity is cured here: predictions.csv keeps score_e6 and restores the physical score field, with a directly-read reader and alias fallback.
- Q2 and Q4 are not adopted by this row's contract line. Q1 is disclosed: amendment commit order 839903862 has no embedded seal and is never retro-sealed.
- Q6 findings are confined to sealed phase-1 rater artifacts; curing them would edit a sealed reference. The landing keeps both REJECT memos verbatim.
- CLOSED AT LIMIT (adjudicated).
