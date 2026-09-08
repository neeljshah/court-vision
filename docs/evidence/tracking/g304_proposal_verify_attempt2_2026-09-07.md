INSTRUMENT NOT VALIDATED; CLOSED AT LIMIT -- E1 packet 0/60 complete: 0/2 broadcasts meet 20 eligible from >=4 shots plus 10 negatives in 4/3/3; 0/40 E1-ready, 0/20 packet-negative rows, 0/240 correspondences, 2/2 distinct arenas, 2/2 model raters; 0/756 jointly accepted on 63 candidate-eligible frames; kappa -0.007380.
G304 attempt 2, proposal-verify. ADJUDICATOR lane, worktree a11. Sealed prereg `g304_proposal_verify_prereg_2026-09-07.md` at
`d625f272d` (seal 78f1a4f2...41335) plus AMENDMENT 1 at `7ca3a692a` (seal 3d60dcda...2696), both sealed before any proposal was
rated. Measures NO registration, NO calibration, NO tracking quality; states no boundary claim. n = 756 (CONSTRUCT -- enumerated).
## SHEET VALIDATION -- NO VIOLATION FOUND FOR EITHER RATER
Both sheets: 756 rows, one per manifest crop id, in manifest order, exact six-column schema, every decision in {ACCEPT, REJECT}, every
reason_code in the closed seven-token list, ZERO nudges (the <= 8 px cap and the discard-an-unjustified-nudge rule were never
exercised), no coordinates and no prose in any field.
## PER-FAMILY ACCEPTANCE (accept rate A 4/756 = 0.005291; B 9/756 = 0.011905; both-accept 0/756 = 0.000000)
  family          proposals   A ACCEPT   B ACCEPT   BOTH ACCEPT   landmarks after adjudication
  lsd_intersect         378          3          8             0                              0
  shitomasi             378          1          1             0                              0
  semantic                0          -          -             -    provider abstained 63/63 frames
  TOTAL                 756          4          9             0                              0
## AGREEMENT (preregistered statistics only; every denominator named; kappa is a REPORTED FIELD, NEVER a pass condition)
12 proposals per frame on all 63 frames (Gateway Center 29 frames / 348 proposals, Climate Pledge 34 / 408).
  cell                    n   both ACC   A only   B only   both REJ   raw agree   kappa
  TOTAL                 756          0        4        9        743    0.982804   -0.007380
  Gateway Center        348          0        4        9        335    0.962644   -0.016173
  Climate Pledge        408          0        0        0        408    1.000000   UNDEFINED (p_e = 1)
  lsd_intersect         378          0        3        8        367    0.970899   -0.011679
  shitomasi             378          0        1        1        376    0.994709   -0.002653
NOT PREREGISTERED, labelled extras, not pass conditions (the prereg names no CI method and no prevalence adjustment): the
asymptotic 95 pct interval on the total kappa is [-0.012614, -0.002146] (SE 0.002670) -- an UNREGISTERED ADDITIONAL
DIAGNOSTIC, independently reproduced by the verifier (codex-sol) and substituted at landing for this lane's SE 0.276984 and
interval [-0.550269, 0.535509]; prevalence-adjusted bias-adjusted kappa 0.965608. At 743/756 = 98.28 pct both-REJECT the kappa
cell is degenerate and carries no information.
## ADJUDICATION (spec clause 1.5)
13 disagreements, ALL in Gateway Center; Climate Pledge produced none because both raters rejected all 408 of its proposals. All
13 are split ACCEPT/REJECT -- there were no both-accept pairs, so the 4 px co-location test never ran. Adjudicated by a DECLARED
MODEL ADJUDICATOR, Claude Opus 5, viewing the same crops: 10 REJECT, 3 UNRESOLVED, 0 ACCEPT (`g304_adjudication2_2026-09-07.csv`).
The 3 UNRESOLVED sit at a real lane-boundary junction whose L/R side designator cannot be confirmed from a 400 px crop showing no
court end. UNRESOLVED LABELS MEAN INSTRUMENT NOT VALIDATED -- THEY ARE NOT OMITTED FRAMES AND NOT SUCCESSFUL ABSTENTIONS.
AGREEMENT ALONE NEVER ESTABLISHES CORRECTNESS. Robustness, pinned by the test: counting every one of the 13 split accepts as a
landmark, the best-filled frame holds 2 of the 6 required, so NO adjudication outcome could have produced an E1-ready frame; no
frame was dropped and all 63 stay in the manifest UNRESOLVED.
## TIME AND HASHES (SHA-256 over LF-normalized bytes)
Rater A (gpt-5.6-terra) 00:55:00 and rater B (gpt-5.6-sol) 00:31:00, both self-reported, neither independently timed -- 86 minutes
for 1512 judgements, about 3.4 s each. This adjudicator lane: about 15 minutes (first statistic 19:30:54 CDT) to commit.
  g304_ratings_codex_2026-09-07.csv       cc814b9e0ce14de9cd8f6d20df309c3b0668cbe3d10232042f040ed3c7eee30f
  g304_ratings_codex_gpt5_2026-09-07.csv  4ed11b6dd0675a19a9729a64dbc6af230f1e614258bbf17c1679e7c9fa569727
  g304_adjudication2_2026-09-07.csv       d456795dbe09fa93681fdf8c440d5b4b6705f0734c92b529c478ab0f6704373a
Both rating CSVs are byte-identical to the raters' own commits (a3 `1cad88f51`, a7 `0a39fefc8`) and their hashes match the two
rater memos. `tests/platformkit/tracking/test_g304_adjudication2.py` -> 5 passed, 0.56 s (per-file only).
## NOT VERIFIED
- BOTH RATERS ARE MODELS (gpt-5.6-terra, gpt-5.6-sol), not humans; no human saw any crop, and their judgements are themselves
  unvalidated because no proposal has independent truth. THE ADJUDICATOR IS ALSO A MODEL (Claude Opus 5) running in the SAME worktree
  that generated the proposals -- a self-assessment, not an independent third party; it added 0 accepts and the frame rule was
  unreachable either way, so it is not load-bearing for the verdict.
- The semantic provider abstained on 63/63 frames: this attempt rested on TWO families, not three. CENTER_CIRCLE_TOP and _BOTTOM
  were preregistered structurally unreachable; LANE_BASE_R and FT_LINE_R needed the family that abstained.
- Crops are LOCAL ONLY (`g304_proposal_crops/`, 756 JPEGs, uncommitted); rater A's 63 contact sheets are local in a3 behind a
  committed sha256 manifest. The numbers behind them are committed here.
- Arena identities are TRANSCRIBED from the a4 inventories, not re-confirmed by eye here; eligibility is as classified by gpt-5.6-sol (a MODEL), not re-derived.
## NEXT STEP
BOTH ALGORITHMIC FAMILIES ARE REJECTED AT ABOUT 99 PERCENT BY BOTH RATERS, so PROPOSAL-VERIFY WITH `lsd_intersect` AND
`shitomasi` CANNOT BUILD THE E1 PACKET. Two attempts are the maximum this spec allows and both are spent, so G304 closes with the
achieved yield (0 landmarks), the kappa above and the annotation burden above. THE REMAINING ROUTES ARE (a) HUMAN ANNOTATION of
the 63 eligible frames -- a USER DECISION, never an agent one, which no agent may schedule; or (b) A WORKING SEMANTIC-LINE
PROPOSER (G307 route-2 territory), the gap this attempt actually exposed, since the one provider that would have carried named
structures abstained on every frame. G306, G307 AND G308 STAY BLOCKED. This is a LIMIT statement about the instrument; it refutes
no registration route.
## CORRECTIONS APPLIED AT LANDING
Verifier `docs/evidence/tracking/G304_VERIFY_ATTEMPT2_2026-09-07.md` returned VERDICT: ACCEPT WITH CORRECTIONS on candidate
`8c83473cb` (verified by codex-sol, contract A/B/Q). All three of its corrections were applied by the lander, none by the
candidate lane:
1. memo:1 -- the verdict line was replaced verbatim with the verifier's line, which carries the 60/40/20 packet, 2-broadcast,
   2-arena, 2-rater and per-broadcast 4/3/3 shot/split denominators the original line omitted (attributed: codex-sol).
2. memo:23-25 -- the candidate's asymptotic kappa SE 0.276984 and interval [-0.550269, 0.535509] were replaced by the
   verifier's independently reproduced SE 0.002670 and interval [-0.012614, -0.002146], explicitly labelled an unregistered
   additional diagnostic reproduced by the verifier (attributed: codex-sol).
3. RESULTS_LEDGER.md -- the status prefix of this row was changed to `CLOSED AT LIMIT (INSTRUMENT NOT VALIDATED; attempt 2 of
   2; ...)` exactly as the verifier wrote it (attributed: codex-sol). The verifier's own proposed ledger line was appended
   alongside it.
OPEN NOTES -- the two NEW GAPs the verifier raised, neither closed at landing:
- `tests/platformkit/tracking/test_g304_adjudication2.py:1-127` does not pin the spec-test requirements for 60/40/20, 4/3/3,
  >=4 shots, the >4 px adjudication test, or p90 <= 12 AND max <= 24. The test pins the adjudication arithmetic only.
- `g304_proposal_verify_prereg_2026-09-07.md:12` contains one restricted prose token outside opaque identifiers. THE PREREG IS
  SEALED AND WAS NOT EDITED -- its two seals (78f1a4f2...41335 original, 3d60dcda...2696 amended) must keep reproducing, so the
  token stands as a recorded defect in a sealed document, not something to fix. The candidate memo and the ledger rows are clean.
