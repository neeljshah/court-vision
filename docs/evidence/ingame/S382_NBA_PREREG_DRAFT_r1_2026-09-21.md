# S382 NBA second-corpus preregistration -- DRAFT r1, UNSEALED 2026-09-21

Document only. This draft freezes nothing and authorizes no scoring or fitting.
Section order follows docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md.
Binding design: docs/evidence/harness/ASTRA_NBA_SECOND_CORPUS_AUDIT_2026-09-21.md.
Counts below are attributed to S377 in docs/evidence/RESULTS_LEDGER_SYSTEM.md;
this lane did not open the corpus or reproduce its census.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, Q1-Q6.

## Hypotheses and signs

Delta = candidate loss minus arm A loss. Negative means lower loss; positive
means higher loss; zero means NULL. No direction is selected after outcomes.
PRIMARY: period-stratified C-minus-A Brier on the proposed validation population.
B-minus-A, D-minus-A and D-minus-C are secondary; D is conditional on provenance.
The proposed primary population excludes S86-scored games; the exposure decision
must be resolved at seal, as detailed below. No secondary can replace the primary.

## Arms and features

A: contemporaneous market_prob (current mid), using inherited EPS clipping only
AFTER refusing nonfinite values and values outside the strict interval (0,1).
B: logistic regression with intercept and logit(mid) only.
C: logistic regression with intercept, logit(mid) and declared state features.
D: C plus model_prob as one additional linear covariate.
Fixed ridge 1e-3 including intercept; at most 100 Newton steps with objective
backtracking; tolerance 1e-9. No tuning search. Fits weight training ticks equally.
All scaling and constant-column removal use training rows only. A constant
model covariate is removed, so D equals C on the same paired population.
No arm fits on a held-out outcome.

Only state features: score_diff, quarter, seconds_remaining. Nothing else.
From baseline_four_arm_features.py: `'nba': ('score_diff', 'quarter', 'seconds_remaining')`.
S360 emits home_score, away_score, quarter, seconds_remaining in state_summary;
score_diff is home_score minus away_score. Possession is absent and is not inferred.
Per the audit, seconds_remaining is remaining regulation time in Q1-Q4 and
current-period time in OT. No outcome, close, audit or external enriched field
may become a feature. Missing state is never imputed as zero.

Live eligibility EXCLUDES quarter >= 4 and seconds_remaining == 0, including OT
at zero. S377 reports 244,183 such post-final ticks; they are not live evidence.
Require finite market probability strictly in (0,1), valid declared state,
binary consistent outcome, and parseable timezone-aware ts and close_ts.
Refuse missing, unparseable or nonfinite required inputs with counted reasons.
A model_prob exactly 0 or 1, null, unparseable, nonfinite or outside (0,1) makes
that tick ineligible for D ONLY. Do not clip or impute an invalid model into D.

Within each declared reporting population, compare A/B/C on its FULL eligible
keys regardless of model availability. D uses its eligible paired subset only;
recompute A/B/C on D's subset with identical keys, folds and weights, including
training populations, before comparing D. Never compare subset D to full A/B/C.
Today's select_rows rejects missing model_prob for EVERY arm, accepts finite
model endpoints, clips market values, and lacks this live exclusion. An
eligibility AMENDMENT implementing the stated populations is required before seal.
These intended rules are not represented as already implemented.

The eligibility AMENDMENT also requires these two named changes before sealing:
- Venue-time parser amendment: the scorer's timestamp() must route BOTH ts and
  close_ts through scripts.platformkit.execution.venue_time.parse_venue_time.
  Require regression tests for four- and five-digit fractional seconds on both
  fields, with timezone-aware UTC identity and counted refusals for invalid input.
  The NBA converter writes six-digit fractions today, so this defect is latent
  for this corpus, but it must be closed before a seal. Preserve sub-microsecond
  information wherever a strict boundary depends on it; parser normalization
  alone must not discard that information for strict comparisons.
- Integral NBA state amendment: quarter, home_score and away_score must be finite
  INTEGRAL values. Refuse booleans and fractional values with counted reasons;
  reject NaN and infinity using math.isfinite. Validate source scores before
  subtraction and quarter before phase assignment or the post-final rule.
  A fractional quarter bypasses that rule: quarter=3.5 seconds_remaining=0
  currently yields reasons=[] and phase=Q3. Regression cases must refuse that
  input and home_score=10.5 away_score=9 quarter=4, cover both booleans,
  fractional and nonfinite values for each of the three fields, and retain valid
  integral states plus the quarter >= 4, seconds_remaining == 0 exclusion.
These are required future amendments, not runtime changes by this document row.
Neither the scorer nor the eligibility module is edited while the sealed MLB
trial is running; the responsible amendment must land and pass tests before seal.

Stable keys are (game_id, ts), with aware UTC identity. Compare canonical JSON
across every parsed field, including unused fields, excluding loader provenance.
Identical duplicate keys collapse; count surplus rows as duplicate_identical.
If any field differs, exclude every row at that key from ALL arms and transitions;
count conflicting_duplicate_key by file and game. Never keep-first or average.
Keep raw tick, unique-key, conflict and exclusion denominators separately.
Stop on manifest, malformed JSON/identity, inconsistent outcome/close,
duplicate-state-field, chronology or evaluator integrity failures.

## Frozen inputs, folds and embargo

Candidate corpus: data/cache/ingame_grade_joined/nba_checkpoints_r1.
Canonical per-file manifest SHA-256: TO-FREEZE-FROM-CENSUS.
S377 reports census manifest prefix 5c4c1d10... and converter-manifest agreement;
a prefix is not a frozen digest. Require the complete canonical manifest and
byte-identical census rerun before sealing. Converter row S360; census row S377.
Manifest enumerates exactly all top-level JSONL inputs, verifies every file hash,
and refuses escaping paths or symlinks. Corpus must resolve under gate DATA_ROOT.
Source archive hashes, converter/scorer/model versions and corpus bytes:
TO-FREEZE-FROM-CENSUS. No archive is read by this document-only lane.

One expanding fold per game's first parseable tick UTC date, including excluded
ticks when assigning dates. Keep whole games together. Use walk_forward with
strict test-view redaction, unique keys and no fitting on held-out outcomes.
Feature capture time is not moved earlier; evaluator receipt is after capture.
Preserve symmetric three-day embargo about test-date midnight: training games
must have earlier first-tick dates and close_ts strictly before midnight minus
three days; exclude every training interval intersecting the embargo window.
Keep shared same-team purge of 48 hours and same-matchup embargo of 3 days.
Absent team identities make the temporal guard binding; do not invent team IDs.
No-training folds are warm-up and excluded identically from compared arms.

S377 full-population counts: 5 warm-up folds, 1,570 post-warm-up games and
217,758 live post-warm-up ticks. Status for these reported denominators:
FROZEN-AT-SEAL-ONLY-IF-CENSUS-RERUN-MATCHES.
Exposure-restricted and D-paired fold/game/tick denominators:
TO-FREEZE-FROM-CENSUS. Do not apply the full-population counts to either subset.

## Populations, phases and reporting

PRIMARY METRIC: PERIOD-STRATIFIED C-minus-A Brier, equal 1/4 weights over Q1-Q4.
For each game-period, average paired tick losses; for each period, average those
game-period means across games with eligible ticks; average the four period means.
A missing game-period is not a zero observation. If a required period has no
eligible games, the primary is unavailable; never renormalize the period weights.
Bootstrap whole games with replacement, preserving all periods and paired keys:
2,000 draws, seed 13, 95 percent interval. S383 must specify and freeze handling
of empty-period bootstrap draws before seal; never silently discard those draws.
The landed scorer computes tick-weighted and equal-game weightings ONLY.
A period-stratified cell is a scorer EXTENSION, row S383, required before sealing.

Secondary: tick-weighted Brier; equal-game Brier; log-loss; transition cells;
Q1, Q2, Q3, Q4 and OT cells. Every such table is labelled SECONDARY.
Tick weights count each tick once; equal-game weights average game means.
OT is secondary and is never substituted for a regulation period in the primary.
Transitions compare the declared state vector to the previous eligible tick in
the same population/game; the first eligible tick is not a transition, and
mid-only changes are not transitions. Use the same paired keys for each comparison.
Archive per-tick keys, game clusters, capture times, folds, training game IDs,
states, predictions and paired losses; assert outcome equality with evaluator
records. Report training counts including warm-up, phase support, exclusion
histograms, and leave-one-game-out ranges without refitting. Weeks use each
game's first-tick ISO year/week so that a game never splits weeks.

EXPOSURE DECISION FOR SEAL: recommend EXCLUDE all 797 S86-scored games from any
AHEAD claim. S86 already scored 232,951 ticks once. Report the full eligible
population separately as descriptive and the remaining 796-game population as
the proposed primary validation population. "Never-scored" here means never
scored by S86; the audit also reports S58 scored all 1,593 games at one checkpoint.
Thus these 796 games are NOT asserted to be untouched validation. Freeze game
identities and adjudicate S58 exposure before sealing or claiming independence;
unresolved exposure blocks a confirmatory interpretation. Neither exposure
partition creates an additional independent corpus. D may have no eligible rows
in the proposed primary; report that honestly, never promote its exposed subset.

NBA late-game cohorts are EXPLORATORY, pre-declared here: quarter == 4,
0 < seconds_remaining <= 300, abs(score_diff) <= 6; no OT membership.
Home-side mid price bands inclusive [0.05,0.20] and [0.80,0.95], as in MLB.
Use the first eligible tick per game and band in timestamp order after exclusions;
resolve duplicates by the same key policy. No outcome-based selection.
Retain the cohort helper's 50-game floor; below it report DESCRIPTIVE_ONLY.
Meeting this floor does not make any cohort confirmatory. All cohort counts,
including period support within exposure and D subsets: TO-FREEZE-FROM-CENSUS.
Today's late_game_cohorts.py supports MLB/NFL ONLY and REJECTS NBA with
unsupported_sport. These thresholds are prospective, not an implemented NBA route.

## Bars and stop rule

EPS = 1e-6; minimum 30 scored games; whole-game bootstrap 2,000 draws, seed 13;
95 percent interval. With sufficient games, AHEAD iff upper bound < 0;
BEHIND iff lower bound > 0; otherwise UNDERPOWERED. Fewer than 30 scored games
is UNDERPOWERED. MATCH has no numeric definition and is never printed as a verdict.
A count floor alone does not establish statistical power.

Concentration ratio = maximum absolute single-game contribution divided by
absolute total paired delta, using the cell's declared weighting; require <= 0.5.
Report week concentration too. Cancellation can make ratios exceed one; a zero
total makes the ratio undefined and blocks interpretation. For the primary,
contributions must sum to the period-stratified paired delta.

Maximum two attempts. A defect invalidates and records an attempt; never patch
it into the same result. A failed second limit attempt is CLOSED AT LIMIT.
Stop on integrity, chronology or evaluator failures; count eligibility exclusions.
Do not move bars, tune periods or remove failing games to rescue a result.
ONE trial must be charged BEFORE ANY metric: orchestrator appends the ledger row
and records launch K, family/global bars and min_corpora_eff at that K.
Launch values not yet available: TO-FREEZE-FROM-CENSUS (record at authorized launch).
This draft does not charge or authorize a trial. Q1 requires sealing before scoring;
Q2 requires the charge before metrics; Q3 fixes bars; Q4 requires purged OOS
walk_forward and OOF-only meta-learning with reproduction tolerance 1e-9;
Q5 requires independent corpora for AHEAD; Q6 governs all calibration language.
Any lone-corpus interval below zero is SINGLE-WINDOW, not a cross-corpus conclusion.
MLB and NBA must support the SAME comparison; season splits are not extra corpora.

## Scope, corpus pins and provenance (filled by the orchestrator before sealing)

Only candidate NBA corpus: data/cache/ingame_grade_joined/nba_checkpoints_r1.
Converter S360 and readiness census S377 are documentary sources, not new runs.
The audit says: "UNKNOWN for historical parameter selection"; the S86 model-side
parameter provenance is UNKNOWN (elo_config constants). Chronological replay does
not establish parameter vintage, unrevised archive inputs or contemporaneous receipt.
The converter's close_ts is the maximum observed timestamp, not verified settlement.
Arm D is CONDITIONAL on the provenance memo in S385 and its clearance; until then
D is descriptive only in any later separately authorized run. No run occurs here.

The landed corpus mapping includes nba and nba_checkpoints with suffixes
('', '_segmented', '_segmented_r3'); nba_checkpoints_r1 is NOT mapped.
Resolve that compatibility defect before sealing; never silently rename the corpus.
Unknown complete source/model/version hashes: TO-FREEZE-FROM-CENSUS.

## Pre-seal eligibility census (counts only; scorer --census-only, scored = false, run 2026-09-21)

The heading follows the MLB template. These are S377's reported counts from
2026-09-21, not a scorer run or newly frozen census by this lane:
- 1,593 games; 465,249 ticks; 465,249 unique keys; 0 conflicting duplicates.
- Post-final ticks: 244,183; 1,592 games repeat final state.
- Live-eligible: 221,066 ticks in 1,593 games.
- 5 warm-up folds; 1,570 post-warm-up games; 217,758 live post-warm-up ticks.
- model_prob exactly 0 or 1: 116,459 ticks; refused for D only.
- Model coverage per game: all 26 / some 771 / none 796.
- S86 exposure: 797 games / 232,951 ticks scored once.
- Raw period ticks Q1/Q2/Q3/Q4/OT: 44,428 / 68,825 / 52,645 / 284,586 / 14,765.
These period counts INCLUDE post-final rows; they are not live primary denominators.
All stated census counts are FROZEN-AT-SEAL-ONLY-IF-CENSUS-RERUN-MATCHES.
Files/bytes, full hashes, identical-duplicate counts, per-file/game/reason
histograms, live period/transition/cohort counts, date folds and training sizes,
exposure-subset and D-paired denominators: TO-FREEZE-FROM-CENSUS.
Rerun must reproduce S377's manifest and matching census bytes; the amended
population tables must be reconciled explicitly before freezing. A disagreement
stops sealing; do not silently substitute counts or claim statistical power.

## Seal

UNSEALED. No seal line is present. Only the orchestrator may add it after review.
Do not seal until ALL of the following are resolved:
- S383 period-stratified scorer extension landed and its bootstrap behavior frozen.
- Eligibility amendment landed: live exclusion, strict probabilities, full A/B/C
  population and identical-key D-paired comparisons; r1 corpus mapping resolved.
- Venue-time parser amendment landed: timestamp() routes ts and close_ts through
  scripts.platformkit.execution.venue_time.parse_venue_time; four- and five-digit
  fraction regressions pass for both fields. Today's six-digit NBA output makes
  the defect latent for this corpus, not grounds to seal with it unresolved.
- Integral NBA state amendment landed: quarter, home_score and away_score are
  finite INTEGRAL values; booleans and fractions are refused with counted reasons.
  Regressions cover the fractional-quarter post-final bypass and fractional
  source scores, plus all state-validation cases specified in eligibility above.
- S385 provenance memo available and D's permitted interpretation resolved.
- Census rerun byte-identical, complete manifest pinned and amended denominators
  reconciled; exposure identities and S58/S86 decision frozen without new scores.
- MLB trial verdict read and its auditor S379 available; comparable MLB/NBA
  estimands and exposure constraints reviewed before a two-corpus conclusion.
- The orchestrator reviews this draft and commits the eventual seal before metrics;
  ONE trial is charged and launch K is recorded before any authorized score.
No lane adds a seal. This document remains DRAFT r1 and freezes nothing.
