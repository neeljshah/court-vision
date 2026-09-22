# S347 four-arm calibration preregistration DRAFT r2 (S355)

UNSEALED. PREPARE ONLY. No real-corpus scoring is authorized by this draft.
The orchestrator reviews, seals and commits the final prereg before scoring.
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

## Pre-seal eligibility census (filled by the orchestrator)

UNFILLED. This builder does not run any real corpus or seal this draft.
After S346 lands and the revision-3 corpus is regenerated, the orchestrator records:
- Revision-3 manifest hash and exact input paths, byte sizes and file hashes.
- Per sport: total files, games and ticks; eligible games and ticks; excluded
  ticks and all-ineligible games with per-file/per-game reason histograms.
- duplicate_identical surplus rows and conflicting_duplicate_key excluded rows,
  per file and game; high_conflict_game with distinct-key denominators.
- State-transition ticks among eligible rows; games per first-tick UTC date;
  eligible games per first-tick UTC date; games without any parseable tick.
- Folds implied by the symmetric 3-day embargo, training sizes and warmup count.
- Whether eligible games >= 30; otherwise declare that sport UNDERPOWERED here.

A sport with fewer than 30 eligible games in the pre-seal census is declared
UNDERPOWERED in the sealed text and reported descriptively only.

The --census-only mode writes census.json with scored=false and fields_read.
It reads outcomes only for presence and within-game consistency, computes no
loss or outcome statistic, fits nothing and does not require a sealed prereg.
The manifest and containment checks still apply. No pre-seal scored claim exists.
Scoring still requires a valid sealed prereg with committed matching bytes.

## Seal protocol (not executed by the builder)

After review, append one final SHA256 line with a lowercase hexadecimal digest
of all bytes above that line after CRLF-to-LF normalization. The separator newline
belongs to the hashed prefix. Commit the sealed file before any scoring.
The scorer requires a valid seal, nonempty git path history, and content matching
HEAD after the same normalization. This draft deliberately has no seal line.
