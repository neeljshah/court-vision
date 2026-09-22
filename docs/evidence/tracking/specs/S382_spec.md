GAP S382 | sport nba | worktree harness-h42 (master-based) | log cx_s382_nba_prereg_draft
# NBA second-corpus prereg DRAFT r1 (UNSEALED; document only) from the readiness census and the leak audit

SINGLE PROBLEM: a second powered calibration corpus needs a prereg written in the exact shape of the sealed MLB one BEFORE any
scorer change or score. The denominators now exist (row S377) and the design audit exists (ASTRA_NBA_SECOND_CORPUS_AUDIT); nobody
has written the document. This row writes the DRAFT and freezes nothing.

BINDING BEFORE-CONDITION: `ls docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md` fails. Read, in this order, and quote
what you rely on: docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md (the template: reproduce its SECTION ORDER exactly),
docs/evidence/harness/ASTRA_NBA_SECOND_CORPUS_AUDIT_2026-09-21.md (binding design: period-stratified primary, whole-game bootstrap,
post-final exclusion, model arm D conditional on provenance, identical-key populations), the S377 ledger line in
docs/evidence/RESULTS_LEDGER_SYSTEM.md (grep "S377 |") for the REAL census denominators, scripts/platformkit/ingame/
baseline_four_arm_features.py (FEATURES['nba'] = score_diff, quarter, seconds_remaining; phase cells Q1-Q4 / OT; the corpus name
mapping) and baseline_four_arm_eligibility.py (what select_rows refuses today), scripts/platformkit/ingame/late_game_cohorts.py
(it REJECTS nba today: say so and pre-declare the NBA cohort thresholds as exploratory), docs/evidence/VERIFIER_CONTRACT.md Q1-Q6.

CHANGE (NEW file only): docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md, ASCII, contract Q6 vocabulary, in the MLB
seal's section order, with these binding contents:
1. Corpus: data/cache/ingame_grade_joined/nba_checkpoints_r1; manifest SHA-256 TO-FREEZE-FROM-CENSUS (the S377 census manifest is
   5c4c1d10...; the converter manifest agrees); converter row S360; readiness census row S377.
2. Eligibility: live rule EXCLUDES post-final rows (quarter >= 4 and seconds_remaining == 0) -- 244,183 ticks; identical duplicate
   keys collapse; conflicting keys excluded from ALL arms; finite probabilities in (0,1); a model_prob of exactly 0 or 1 or null
   makes the tick ineligible for arm D ONLY, and arms A / B / C are compared on the FULL eligible population while D is compared
   against A / B / C recomputed on D's paired subset (the audit's rule; state that today's select_rows rejects a missing model for
   every arm, so an eligibility AMENDMENT is a precondition of sealing and is listed under do-not-seal-until).
3. Arms exactly as MLB (A market, B recalibrated market, C market + state, D = C + model), ridge 1e-3, 100 Newton steps, 1e-9;
   state features = score_diff, quarter, seconds_remaining and NOTHING else (possession is absent from the converter output).
4. Folds: one expanding fold per first-tick UTC date, whole games, symmetric three-day embargo -- 5 warm-up folds, 1,570
   post-warm-up games, 217,758 live post-warm-up ticks (from the census; marked FROZEN-AT-SEAL-ONLY-IF-CENSUS-RERUN-MATCHES).
5. PRIMARY METRIC: PERIOD-STRATIFIED C-minus-A Brier (equal 1/4 weights over Q1-Q4, tick losses averaged within game-period then
   across games), whole-game bootstrap 2,000 draws seed 13, 95 percent interval; state that the landed scorer computes tick and
   equal-game weightings ONLY and that a period-stratified cell is a scorer EXTENSION (row S383) that must land before sealing;
   secondaries: tick-weighted, equal-game, log-loss, transitions, Q1-Q4 and OT, each labelled secondary.
6. Bars: EPS 1e-6, minimum 30 scored games, AHEAD iff upper bound < 0, BEHIND iff lower bound > 0, else UNDERPOWERED; MATCH has no
   numeric definition and is never printed; concentration ratio <= 0.5; maximum two attempts; ONE trial charged before any metric.
7. Exposure disclosure: 797 games / 232,951 ticks were scored once by S86; the draft must state whether they are excluded from the
   validation population (recommend: EXCLUDE them from any AHEAD claim -- report the full population AND the never-scored 796-game
   population separately, with the never-scored population primary) and mark this a decision for the seal.
8. Provenance: the S86 model side's parameter provenance is UNKNOWN (elo_config constants); arm D is CONDITIONAL on a provenance
   memo (row S385) and is reported descriptively until then.
9. Cohorts: NBA late-game cells pre-declared as EXPLORATORY with thresholds you propose (e.g. Q4 with <= 300 s remaining and
   absolute score_diff <= 6; price bands as MLB) and counts TO-FREEZE-FROM-CENSUS.
10. Do-not-seal-until list: S383 landed; eligibility amendment landed; S385 memo; census re-run byte-identical; the MLB trial's
    verdict read and its auditor (S379) available; then the seal line is added by the orchestrator, never by a lane.
Every number that cannot be known now is written as TO-FREEZE-FROM-CENSUS. No score, no loss, no fit. Memo: docs/evidence/harness/
S382_nba_prereg_draft_2026-09-21.md (short; NOT VERIFIED last). No seal line anywhere (the S355 self-check asserts drafts are unsealed).

CONTROLS: document only, NEW files only, no code, no real archive, no network. ACCEPTANCE: contract preflight passes; ASCII; the
draft carries no `SHA256: ` line; the memo ends with a NOT VERIFIED list.
