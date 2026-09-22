# S347 four-arm calibration preregistration -- SEALED 2026-09-21

SEALED by the orchestrator from the unsealed draft S347_PREREG_DRAFT_r2_2026-09-21.md (which stays in place, unsealed).
This text authorizes ONE charged trial: the four-arm baseline on the MLB revision-3 corpus pinned below.
Nothing was scored before this file was committed. Sign convention, stated once more: every delta is
candidate loss minus arm A loss; NEGATIVE means lower loss than the current mid; the inherited verdict code
maps an interval wholly above zero to BEHIND and wholly below zero to AHEAD.
Vocabulary follows contract Q6; automated scan required.

## Hypotheses and signs

For each of B, C and D versus A, negative paired Brier and log-loss deltas
mean lower loss; positive deltas mean higher loss; zero means NULL.
B may reduce miscalibration in the current mid, or worsen it.
C may reduce loss with state information beyond mid, or worsen it.
D may reduce loss with model probability beyond mid and state, or worsen it.
D-minus-C is the incremental model interpretation; the required reported
comparisons remain B-minus-A, C-minus-A and D-minus-A on identical ticks.
No directional hypothesis is selected after viewing outcomes.

## Arms and features

A: contemporaneous market_prob (current mid), clipped with the inherited EPS rule.
B: logistic regression with intercept and logit(mid) only.
C: logistic regression with intercept, logit(mid) and declared state features.
D: the C features plus model_prob as one additional linear covariate.
No arm fits on a test outcome. All feature scaling and constant-column removal
use only training rows. A constant model_prob is removed, so D equals C exactly.
Use fixed ridge coefficient 1e-3 including the intercept, at most 100 Newton
steps with objective backtracking, and step tolerance 1e-9; no tuning search.
Training fits weight ticks equally; report both tick and equal-game losses.

The only state input is the row state_summary string. Declared features:
- MLB: score_diff, inning, half (top=0/bottom=1), outs (0, 1, 2), and base as
  seven one-hot indicators base_1 through base_7 over integer values 0..7;
  value 0 is the reference. No bit order is assumed and no bits are decoded.
- Soccer: score_diff, minute, home_red_cards, away_red_cards and each side's
  red-card-present indicator. Absent optional counts are zero with indicator zero.
  Only score_diff and minute are required; half is not required for soccer.
- NBA checkpoints: score_diff, quarter, seconds_remaining.

score_diff may be supplied directly or computed from home_score minus away_score
in the same string. Decimal-string scores such as 2.0 parse as numbers and must
be finite. Missing, non-integer or out-of-range MLB base values are excluded
with missing_state:base. bos, re, count, pitch_count and tto are available but
excluded from the features; re is itself a model output. NBA period aliases
quarter; clock=MM:SS may supply seconds_remaining.
A tick is eligible only with finite market_prob strictly inside (0, 1) after
EPS clipping, finite model_prob, an outcome, parseable timezone-aware ts and
close_ts, and every declared state feature under the aliases/defaults above.
Unavailable or invalid declared state inputs are missing_state:<feature>;
nonfinite numeric inputs are nonfinite_value. Other exclusion reasons are
missing_model_prob, missing_market_prob, missing_outcome and unparseable_time.
Exclude each ineligible tick from ALL FOUR arms identically. Report distinct
excluded ticks plus reason histograms per file and game; a tick can have several
reasons, so reason counts need not sum to excluded ticks. All-ineligible games
are explicitly reported with their histograms. Integrity failures still stop:
manifest hash mismatch, unparseable JSON, inconsistent within-game outcomes or
close timestamps, unknown corpus, malformed row or
game identity, duplicate state fields, and ticks after settlement.
No external state enrichment or post-outcome feature is allowed.

Before eligibility and state-transition detection, group by stable (game_id, ts)
key. Compare canonical JSON with sorted keys across EVERY parsed row field,
including unused fields; loader-added provenance is not a parsed field.
IDENTICAL repeats collapse to one row; duplicate_identical counts surplus rows
per file and game. If ANY field differs, EVERY row of that conflicting key is
excluded from ALL FOUR arms and the transition population. Count these excluded
rows as conflicting_duplicate_key per file and game; never keep-first,
keep-last or average a conflicting key. These reasons precede eligibility
reasons. Raw ticks remain in the census denominator, including collapsed repeats.
Integrity checks still cover all rows before any exclusion.
Report distinct unique_keys and conflicting_keys per game. A game with more
than 10 pct conflicting keys is high_conflict_game in the census; it remains
in the population subject to ordinary tick eligibility. This is a visibility
threshold; the prereg can name a population threshold before sealing.

## Frozen inputs, folds and embargo

The corpus manifest format is {"files": {"relative.jsonl": "sha256hex"}}.
It must enumerate exactly all top-level JSONL files in the supplied corpus.
Every file hash must match; escaping paths and symlinks are rejected.
All nonblank rows must parse; integrity checks cover even excluded ticks.
A corpus directory must resolve under the gate DATA_ROOT before input reads.
Both modes use the same hash-verified JSONL loader and eligibility code, retaining
all denominators before exclusion. The clustered bootstrap remains the gate helper.
Its pandas dependency is inherited through that reused gate; new estimation
uses numpy and the standard library.

Each game belongs to the UTC date of its first parseable tick, including excluded ticks. One expanding fold per
first-tick date; all ticks of every held-out game stay out of its training set.
The shared walk_forward evaluator runs once with one state per tick, strict
test-view redaction and unique (game_id, state_ts) keys. Features arrive at the
capture timestamp; evaluator time is one microsecond after capture, explicitly
representing evaluation after receipt rather than invented earlier availability.
Keep shared same-team purge of 48 hours and same-matchup embargo of 3 days.
Additionally purge any training game whose interval intersects the symmetric
[test-date midnight minus 3 days, test-date midnight plus 3 days] embargo.
Only games on earlier first-tick dates with close_ts strictly before the lower
boundary enter training; walk-forward already excludes the future side.
The first folds without training rows are named warmup_keys and excluded from
every scored arm/population equally. No warmup probability is calibration evidence.

## Populations, phases and reporting

Report all eligible scored ticks and state-transition ticks separately.
A transition means the parsed declared state vector changed from the previous
eligible tick of that game; first eligible ticks are not transitions. Mid-only changes do not count.
Report overall and each observed phase; never silently report an unmapped corpus.
Supported families: mlb, mlb_clean, soccer_intl, nba, nba_checkpoints, each with
the empty suffix, _segmented or _segmented_r3. MLB phases 1-3/4-6/7-9+;
soccer phases 0-30/31-60/61-90+; NBA Q1/Q2/Q3/Q4/OT.

Each cell reports paired Brier and log-loss deltas against A with game-clustered
95-percent intervals. Tick weights count each tick once; equal-game weights
average each game's losses first, then average those game means. Bootstrap
whole games with replacement under the chosen weighting, using the reused helper.
Leave-one-game-out ranges remove each game from the reported paired-loss series,
without refitting. Archive each tick's key, cluster, timestamp, fold, state,
training game IDs, predictions and all four paired losses for reconstruction.
Assert per stable key that each output outcome equals the evaluator record.
Report training game and tick counts for every fold, including warmup folds.
Rows have no team identities, so the shared same-team purge is degenerate;
the temporal settlement embargo remains the binding chronology guard.
Weeks use the game's first-tick ISO year/week so a game never splits weeks.

## Bars and stop rule

The following source lines are copied byte-identical from
scripts/platformkit/ingame/gate_a0_ingame_vs_market.py (GATE A0):

```python
EPS = 1e-6
N_BOOT = 2000
SEED = 13
N_MIN_GAMES = 30
ECE_BINS = 10
    if n_games < n_min or (lo <= 0 <= hi):
        return 'UNDERPOWERED'
    return 'BEHIND' if lo > 0 else 'AHEAD'
```

These are unchanged inherited bars. AHEAD from a single supplied corpus is
reported as SINGLE-WINDOW; no cross-corpus calibration conclusion is authorized.
Every scored cell with fewer than 30 distinct games is UNDERPOWERED.
For concentration, divide the largest absolute game or week contribution by
the absolute total paired delta under that weighting. Cancellation can make
shares exceed one. A zero total has undefined shares (null), never a passing share.
The proposed additional single-game rule is share <= 0.5; exceeding it or an
undefined share sets concentration_pass=false and blocks a calibration claim.
This new draft rule is not represented as an inherited GATE A0 threshold.

Stop on any integrity, chronology or evaluator failure; count eligibility exclusions. Do not change
bars or exclude failing games to rescue a result. At most two attempts; a second
failed limit attempt is CLOSED AT LIMIT. No retries selected by outcome.
Before a charged future trial, the orchestrator must append its ledger row and
record K at launch under contract Q2; this instrument does not charge that ledger.
An eventual AHEAD needs the independent second corpus and min_corpora_eff at K.
Review input availability and model_prob provenance before enabling that trial.

## Scope, corpus pins and provenance (filled by the orchestrator before sealing)

PRIMARY AND ONLY SCORED CORPUS: data/cache/ingame_grade_joined/mlb_segmented_r3 -- 176 files, 15669023 bytes, produced on
2026-09-21 by scripts.platformkit.segment_ingame_join_r3 (row S346, commit b79efca2f). Segmenter manifest
data/cache/ingame_grade_joined/_segmented_r3_manifest.json, SHA-256
7d9e8001e276ef5a4a20a94f99ae45aff6d7bb075fc288c0a31d3516ba1f782f. Per-file hash manifest in canonical compact JSON
(sorted keys, separators "," and ":"), SHA-256 f3b5e3f9364f7627404cac7e8f51ffbf95fa56ffc72e20020629958aac3f72b1; the
scorer refuses to run unless every listed file hash matches. Scorer code: commit 531f0525d (rows S347 + S355).
SOCCER IS DECLARED UNDERPOWERED HERE, BEFORE ANY SCORE: soccer_intl_segmented_r3 holds 26 games (canonical manifest SHA-256
803ffa7b951283728caf64e2295400e8d0f53ada97e718b24fcbf90af15db9e6), below the 30-game bar, and 5 of its date folds are
warm-up. It may be run for a DESCRIPTIVE table only, labelled UNDERPOWERED in every cell; no verdict is drawn from it.
CONSEQUENCE, STATED IN ADVANCE: with one powered corpus no AHEAD conclusion is authorized by this trial. Any cell whose
interval lies wholly below zero is reported as SINGLE-WINDOW and needs an independent second corpus; the purpose of this
trial is the corrected MLB baseline that isolates what the mid, the state and the model probability each contribute.
model_prob PROVENANCE (reviewed): per scripts/platformkit/ingame/ticker_settlement_join.py the (model_prob, market_prob)
pair of every row was written by the LIVE capture at tick time (live_grade.capture_pair_once); the join only attaches
outcome and close fields and re-derives nothing. model_prob is therefore as-of the tick. NOT VERIFIED: that the live
model's own inputs were as-of at capture time (its feature freshness is outside this instrument).
The fields outcome, close_prob, close_ts, close_source and segment_audit are post-outcome or audit fields; no arm may read them
as features (the feature parser reads state_summary only; an independent review confirmed it with adversarial strings).

## Pre-seal eligibility census (counts only; scorer --census-only, scored = false, run 2026-09-21)

mlb_segmented_r3: 176 files, 176 games, 31433 ticks. ELIGIBLE: 29887 ticks in 176 games. Excluded 1546 distinct ticks;
reason counts (a tick can carry several): missing_state:half 1410, missing_state:base 700, missing_state:outs 700,
missing_state:inning 668, missing_state:score_diff 668, conflicting_duplicate_key 104, duplicate_identical 0.
high_conflict_game: none. Games without a parseable tick: none. State-transition ticks among eligible rows: 12339.
Date folds: 15, of which 4 are warm-up and 11 are scored; training grows from 19 games (first scored fold, 2026-07-02)
to 113 games (last fold, 2026-07-12). Eligible games per first-tick UTC date: 06-27 5, 06-28 15, 06-30 8, 07-01 13,
07-02 9, 07-03 8, 07-04 14, 07-05 17, 07-06 6, 07-07 13, 07-08 14, 07-09 10, 07-10 10, 07-11 18, 07-12 16.
Eligible games >= 30: yes. These denominators are frozen by this seal; a run whose census differs from them is an
integrity failure and stops.
KNOWN POPULATION LIMIT, stated in advance: 49 of the 227 source files carry no stated game state and were quarantined by the
segmenter as no_anchor; the scored population is games whose live feed carried state, not all games.

ATTEMPTS: at most two, as drafted; a defect found in the instrument invalidates the attempt and is recorded, never patched
into the same result. The Q2 trial charge is appended to the ledger by the orchestrator BEFORE launch.

## Seal

The final line of this file is SHA256 followed by the lowercase hexadecimal digest of all bytes above that line after
CRLF-to-LF normalization; the separator newline belongs to the hashed prefix. The scorer requires a valid seal, a
nonempty git path history for this file, and content matching HEAD after the same normalization.
SHA256: 18b45d85983ab60af438acb066ce4940213ece8652538e464004a7cda750361f
