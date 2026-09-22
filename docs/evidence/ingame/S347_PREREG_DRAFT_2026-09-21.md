# S347 four-arm calibration preregistration DRAFT

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

A: the unchanged contemporaneous market_prob (current mid).
B: logistic regression with intercept and logit(mid) only.
C: logistic regression with intercept, logit(mid) and declared state features.
D: the C features plus model_prob as one additional linear covariate.
No arm fits on a test outcome. All feature scaling and constant-column removal
use only training rows. A constant model_prob is removed, so D equals C exactly.
Use fixed ridge coefficient 1e-3 including the intercept, at most 100 Newton
steps with objective backtracking, and step tolerance 1e-9; no tuning search.
Training fits weight ticks equally; report both tick and equal-game losses.

The only state input is the row state_summary string. Declared features:
- MLB: score_diff, inning, half (top=0/bottom=1), outs, base1/base2/base3.
- Soccer: score_diff, minute, home_red_cards, away_red_cards and each side's
  red-card-present indicator. Absent optional counts are zero with indicator zero.
- NBA checkpoints: score_diff, quarter, seconds_remaining.

score_diff may be supplied directly or computed from home_score minus away_score
in the same string. MLB bases/base_state must be three occupancy bits. NBA
period aliases quarter; clock=MM:SS may supply seconds_remaining.
Missing mandatory fields, nonfinite values, inconsistent outcomes or close
timestamps, duplicate stable ticks and unknown corpus names stop the run.
No external state enrichment or post-outcome feature is allowed.

## Frozen inputs, folds and embargo

The corpus manifest format is {"files": {"relative.jsonl": "sha256hex"}}.
It must enumerate exactly all top-level JSONL files in the supplied corpus.
Every file hash must match; escaping paths and symlinks are rejected.
All nonblank rows must parse and satisfy the shared four-arm eligibility rules;
invalid input stops the entire run instead of silently shrinking a denominator.
The scorer imports the existing gate row loader and clustered bootstrap.
Its pandas dependency is inherited through that reused gate; new estimation
uses numpy and the standard library.

Each game belongs to the UTC date of its first tick. One expanding fold per
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
tick of that game; first ticks are not transitions. Mid-only changes do not count.
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

Stop on any integrity, chronology, schema or evaluator failure. Do not change
bars or exclude failing games to rescue a result. At most two attempts; a second
failed limit attempt is CLOSED AT LIMIT. No retries selected by outcome.
Before a charged future trial, the orchestrator must append its ledger row and
record K at launch under contract Q2; this instrument does not charge that ledger.
An eventual AHEAD needs the independent second corpus and min_corpora_eff at K.
Review input availability and model_prob provenance before enabling that trial.

## Seal protocol (not executed by the builder)

After review, append one final SHA256 line with a lowercase hexadecimal digest
of all bytes above that line after CRLF-to-LF normalization. The separator newline
belongs to the hashed prefix. Commit the sealed file before any scoring.
The scorer requires a valid seal, nonempty git path history, and content matching
HEAD after the same normalization. This draft deliberately has no seal line.
