# Pregame pricing from public data versus the devigged close

Neel Shah, CourtVision. Calibration readout; paper only. Generated 2026-10-06.

**Summary.** I built pregame forecasters for three sports from public results data only and scored
them against the devigged closing price on the same held-out games. On MLB moneyline and on soccer
Over/Under 2.5 goals the model TRAILS the close: the gap is small but clearly measured, and its
game-clustered 95% interval lies above zero. On NBA moneyline the gap is indistinguishable from zero,
but that sample is underpowered. No row matches or beats the close in a way the sample can resolve.
The result is the point of this paper. What I want to show is the measurement discipline: leak-free
walk-forward models, a stated devig, game-clustered intervals, a verdict rule fixed in advance, and
a published correction when an earlier label did not survive an interval. The soccer per-game file
and its scorer are prepared for public release pending the owner's decision on licence ledger row 7
(football-data.co.uk: all rights reserved; no redistribution right is granted); today they live in the private evidence tree, where the
soccer row reproduces in one command (section 8).

Every number in this paper is copied from one of three places: the canonical figures file
[`docs/evidence/CANONICAL_FIGURES.json`](../evidence/CANONICAL_FIGURES.json), the recompute memo
[`docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`](../evidence/pregame/DM_RECOMPUTE_2026-09-24.md),
or the output of the scorer run on 2026-10-06. Each table names its source and the command
that reproduces it. The page is a surface of the repository's figure-consistency gate
(`scripts/platformkit/eval_gate/claim_consistency.py`), which fails if any interval or verdict here
disagrees with the canonical file.

## 1. The question

Can a pregame model built only from public box scores and results match a sharp devigged closing
price on the probability of a binary outcome?

The close is the right benchmark for three reasons.

- **It is the strongest public forecaster available.** The closing price has absorbed everything the
  market learned before the start: lineups, injuries, weather, and the views of the participants
  whose money moves the price last. Pinnacle's soccer totals close in particular is widely treated
  as a sharp reference.
- **It is scored on the same outcomes.** Each game gets one model probability and one devigged
  close probability, and both are scored against the same result. A paired comparison removes the
  game-to-game variance that dominates any single Brier score.
- **It cannot flatter the model.** Accuracy against outcomes alone is easy to make look good: pick
  the easy games, report the favourable split, or compare against a weak baseline. Measuring the gap
  to the close answers the question a pricing desk actually asks: does this forecaster add anything
  to the price that was already available?

The comparison has three possible honest answers: the model TRAILS the close, it MATCHES the close
within the precision of the sample, or it BEATS it. Section 3.6 fixes which answer each interval
gives.

## 2. Data and licences

| Sport | Market | Model input (public) | Close | Overlap games | Holdout scored | Licence ledger row |
|---|---|---|---|---|---|---|
| MLB | moneyline | game results from the sportsbookreviewsonline.com archive | closing moneyline, same archive | 27,983 | 13,992 | row 13, UNREAD |
| Soccer | O/U 2.5 goals | football-data.co.uk results and match stats | Pinnacle closing O/U 2.5, via football-data.co.uk | 15,115 | 7,558 | row 7, OK |
| NBA | moneyline | ESPN box scores | ESPN odds endpoint (ESPN BET, then DraftKings) | 743 | 372 | row 1, DECIDE |

Source: the reproduction table and the Task B section of
[DM_RECOMPUTE_2026-09-24.md](../evidence/pregame/DM_RECOMPUTE_2026-09-24.md); licence verdicts from
the summary table of [`docs/evidence/LICENCE_LEDGER.md`](../evidence/LICENCE_LEDGER.md).

**Holdout.** In every sport the scored games are the second half of the chronological overlap
between model rows and close rows (an n // 2 split). The first half warms up the ratings and, for
soccer, fits the recalibration. No parameter is fitted on the held-out half.

**What is public, what is withheld, and why.**

- **Soccer is available at the row level in the evidence tree; publishing it is an owner decision
  not yet made.** [`docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv`](../evidence/pregame_vs_close/soccer_ou25_holdout.csv)
  holds all 7,558 held-out matches: date, match id, model probability, proportionally devigged close
  probability, devig method, outcome. It contains no raw prices. Its data card
  ([`soccer_ou25_holdout_CARD.md`](../evidence/pregame_vs_close/soccer_ou25_holdout_CARD.md)) gives
  the exclusions, the source-file hashes and the export command. One question remains open and the
  card says so: ledger row 7 was written for a non-published use (football-data.co.uk: all rights reserved; no
  redistribution right is granted), so whether the derived devigged file may be published is an owner decision
  not yet made. Until then the file and the scorer stay in the private evidence tree.
- **MLB is not published at the row level.** The odds archive is ledger row 13, verdict UNREAD.
  Only the aggregate row in section 4 is reported.
- **NBA is not published at the row level.** The close comes from ESPN's odds endpoint, ledger row
  1, verdict DECIDE. The Disney consumer terms recorded there grant no right to make derived data
  available to the public, so the per-game file was not written. Two data gaps would remain even
  with a licence: the odds file has no snapshot timestamp, and it is not established that the cached
  price is the closing price rather than whatever ESPN served when the cache was written.
- **An ATP tennis file is withheld.** Its match spine and outcomes come from the Sackmann corpus,
  ledger row 10, verdict UNREAD.

The private corpora behind all three rows are pinned by sha256 in the recompute memo.

## 3. Method

### 3.1 Models (all walk-forward; nothing after the cut)

- **MLB**: a margin-of-victory-aware Elo, `scripts/platformkit/proof_mlb/beat_the_close_ml.py`.
  The pregame probability is recorded before the game's result updates the ratings. The model does
  not see the starting pitcher.
- **Soccer**: exponentially weighted Poisson attack and defence ratings feeding a bivariate-Poisson
  scoreline engine that gives P(over 2.5), followed by a pooled Platt recalibration fitted on the
  first chronological half only and applied to the second.
  `scripts/platformkit/proof_soccer/beat_the_close_ou.py`.
- **NBA**: a margin-of-victory Elo, `_walk_forward_elo` in `scripts/platformkit/proof_nba/ml_accuracy.py`.

In all three the closing price is a comparison forecaster only. It is never a model input. The
recompute (`scripts/platformkit/eval_gate/dm_recompute_pregame.py`) calls each harness's own
functions with the same sort order, inner joins, split and 1e-6 clip. No model is reimplemented
for the scoring.

### 3.2 Devig

Let imp_i = 1 / (decimal price of side i). The quoted implied probabilities sum to the booksum
B = imp_1 + imp_2 > 1.

- **Proportional** (the primary rows): p_1 = imp_1 / (imp_1 + imp_2).
- **Shin** (the sensitivity rows): Shin's insider-share model. For an insider share z in [0, 1),

      p_i(z) = ( sqrt( z^2 + 4 (1 - z) imp_i^2 / B ) - z ) / ( 2 (1 - z) )

  and z is found by bisection so that sum_i p_i(z) = 1. Implementation:
  `scripts/platformkit/eval_gate/shin.py` (`shin_devig`). It raises on a booksum below 1 rather than
  returning a price, so rows with no valid Shin price are dropped (9 MLB rows and 3 soccer rows).
  Shin matters because proportional devig leaves the favourite-longshot bias in the close, which can
  flatter a model on lopsided markets.

### 3.3 Scores

For each game, with model probability p, devigged close probability q and outcome y in {0, 1}:

- Brier: (p - y)^2 and (q - y)^2.
- Log loss: -[y ln p + (1 - y) ln(1 - p)], likewise for q. Both probabilities are clipped to
  [1e-6, 1 - 1e-6] first.
- Paired difference: d = loss_model - loss_close. **Positive d means the close is sharper.** The
  gap is the mean of d.

### 3.4 Game-clustered Diebold-Mariano interval

The interval on the gap comes from `diebold_mariano(d, cluster_ids)` in
`scripts/platformkit/eval_gate/dm_test.py`. With G clusters and n rows, the variance of the mean is
the cluster-sum estimator

    Var(mean d) = (G / (G - 1)) * sum_g ( sum_{i in g} (d_i - mean d) )^2 / n^2

and the statistic is mean d / SE. The p-value and the 95% interval both use a Student-t reference
with G - 1 degrees of freedom. The critical value is found by bisection on the same t p-value
function the test reports, so the interval and the p-value cannot disagree about significance.
(An earlier version used the normal 1.96 for the interval and the t for the p-value; at small G
that mismatch could flip a verdict, and it was fixed.)

The pregame rows have one row per game, so game clustering reduces to the i.i.d. standard error.
As a sensitivity check the memo also clusters by date, which allows for correlation between games
played on the same day.

### 3.5 Power: the minimum detectable effect

MDE = (z_0.975 + z_0.80) x SE, which the repository writes as 1.429 x the CI half-width (from
[`POWER_PAGE_2026-09-22.md`](../evidence/POWER_PAGE_2026-09-22.md)). It is the smallest true gap
the row would detect at 80% power. A row whose MDE is larger than the gaps seen elsewhere cannot
distinguish parity from a real deficit, and is reported as underpowered.

### 3.6 Verdict rule (applied mechanically)

- MATCHES_CLOSE if the 95% interval includes 0.
- TRAILS_CLOSE if the whole interval lies above 0.
- BEATS_CLOSE if the whole interval lies below 0.

There is no tolerance band and no threshold on the point gap. Section 5.2 explains why that matters.

### 3.7 Floor and refusals

The scorer refuses to print a verdict below 500 rows (`MIN_ROWS` in
`scripts/platformkit/eval_gate/score_vs_close.py`). It also refuses, with a counted reason and exit
code 3, on duplicated match ids, a probability outside (0, 1), a non-binary outcome, a mixed or
mismatched devig method, or a leak signature (any row with |p_model - y| <= 0.001, or a perfect
Brier score). Nothing is silently dropped.

## 4. Results

### 4.1 The three rows

Source: [DM_RECOMPUTE_2026-09-24.md](../evidence/pregame/DM_RECOMPUTE_2026-09-24.md) table and
[CANONICAL_FIGURES.json](../evidence/CANONICAL_FIGURES.json). Reproduce:
`python -m scripts.platformkit.eval_gate.dm_recompute_pregame --json <out.json>` (needs the private
corpora; the fixture tests in section 8 need none).

| Sport | Market | Devig | n (holdout) | Model Brier | Close Brier | Gap | 95% CI | DM p | MDE | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| MLB | moneyline | proportional | 13,992 | 0.2429 | 0.2390 | +0.0039 | [+0.0028, +0.0051] | 3.6e-12 | 0.0016 | TRAILS_CLOSE |
| Soccer | O/U 2.5 | proportional | 7,558 | 0.2465 | 0.2390 | +0.0076 | [+0.0059, +0.0092] | 1.1e-19 | 0.0023 | TRAILS_CLOSE |
| NBA | moneyline | Shin | 372 | 0.1735 | 0.1666 | +0.0069 | [-0.0038, +0.0175] | 0.20 | 0.0152 | MATCHES_CLOSE |
| NBA | moneyline | proportional | 372 | 0.1735 | 0.1672 | +0.0063 | [-0.0042, +0.0168] | 0.237 | 0.0150 | MATCHES_CLOSE |

In words:

- On MLB moneyline the pregame model trails the devigged close by +0.0039 Brier (95% CI [+0.0028, +0.0051], DM p 3.6e-12, n=13,992).
- On soccer O/U 2.5 the pregame model trails the devigged close by +0.0076 Brier (95% CI [+0.0059, +0.0092], DM p 1.1e-19, n=7,558).
- On NBA moneyline the gap to the Shin-devigged close, +0.0069 Brier (95% CI [-0.0038, +0.0175], DM p 0.20, n=372), is indistinguishable from zero and underpowered (MDE 0.0152).

The MLB and soccer gaps are about 2.5 and 3.3 times their MDEs, so the close is measurably sharper
in both. They are still small in relative terms: the model's Brier score is 1.6% worse than the
close's on MLB and 3.2% worse on soccer (memo, plain-English reading). The NBA MDE is more than
twice the NBA point gap. A deficit the size of the MLB or soccer one would not be visible at
n=372, so the NBA row says nothing either way. It is not evidence of parity.

### 4.2 Sensitivity: devig method and clustering

Source: the sensitivity table of the same memo. None changes a verdict.

| Row | Shin-devigged close: n, gap, CI, verdict | Shin DM p / MDE | Date-clustered CI (clusters) |
|---|---|---|---|
| MLB ML | 13,983, +0.0040, [+0.0029, +0.0051], TRAILS_CLOSE | 3.4e-12 / 0.0016 | [+0.0028, +0.0051] (1,170 dates) |
| Soccer O/U | 7,555, +0.0076, [+0.0060, +0.0093], TRAILS_CLOSE | 7.2e-19 / 0.0024 | [+0.0059, +0.0092] (685 dates) |
| NBA ML | 372, +0.0069, [-0.0038, +0.0175], MATCHES_CLOSE | 0.20 / 0.0152 | [-0.0028, +0.0154] (74 dates; proportional devig, date-clustered) |

In the NBA row the date-clustered interval is computed against the proportional-devig close, not the
Shin close named in the second column (the memo's table carries the same ambiguity). Date clustering moves the bounds by at most 0.0015.

### 4.3 The soccer row, reproduced live by the scorer

The scorer reads the per-game CSV, checks every row, and prints JSON. It was run once for this paper,
read-only, on 2026-10-06, with the output written to a scratch directory:

    python -m scripts.platformkit.eval_gate.score_vs_close --csv docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv --devig proportional

Its top-level output, verbatim (the `reliability` block is elided here at `...`; it is tabulated in
4.4 and printed in full in the appendix):

```json
{
  "schema": "score_vs_close/v1",
  "status": "OK",
  "n": 7558,
  "n_clusters": 7558,
  "devig_method": "proportional",
  "model_brier": 0.24653174209394257,
  "close_brier": 0.23895608751999672,
  "gap": 0.007575654573945858,
  "gap_sign": "positive = model trails the close; dm_stat has the same sign as gap",
  "ci95": [
    0.005944816121945759,
    0.009206493025945957
  ],
  "dm_stat": 9.105983862301864,
  "dm_p": 1.0772791656587416e-19,
  "mde": 0.002330468147908141,
  "mde_power": 0.8,
  "model_log_loss": 0.6861514938971582,
  "close_log_loss": 0.6706680132300011,
  ...
  "verdict": "TRAILS_CLOSE",
  "reasons": {},
  "note": "calibration readout, paper only, not a verdict"
}
```

Rounded to four decimals this is the published soccer row: Brier 0.2465 against 0.2390, gap
+0.0076, interval [+0.0059, +0.0092], TRAILS_CLOSE. Log loss tells the same story (0.6862 against
0.6707). No row was refused (`"reasons": {}`). The output is identical to the one pasted in the data
card, which was produced on an earlier day. (The scorer's fixed `note` string says "not a verdict"
because a single run is a readout; the verdict field is the mechanical rule of section 3.6.)

### 4.4 Reliability, soccer O/U 2.5

Source: the `reliability` block of the scorer output above (ten equal-count bins sorted by each
forecaster's own probability, then match id; rounded to three decimals). Descriptive only; no test
is run on these bins.

| Bin | Model mean p | Observed over rate | Count | Close mean p | Observed over rate | Count |
|---|---|---|---|---|---|---|
| 1 | 0.421 | 0.458 | 756 | 0.359 | 0.369 | 756 |
| 2 | 0.455 | 0.423 | 756 | 0.415 | 0.402 | 756 |
| 3 | 0.473 | 0.478 | 756 | 0.444 | 0.399 | 756 |
| 4 | 0.489 | 0.471 | 756 | 0.468 | 0.466 | 756 |
| 5 | 0.504 | 0.522 | 756 | 0.492 | 0.504 | 756 |
| 6 | 0.518 | 0.525 | 756 | 0.516 | 0.505 | 756 |
| 7 | 0.533 | 0.516 | 756 | 0.543 | 0.573 | 756 |
| 8 | 0.551 | 0.541 | 756 | 0.573 | 0.597 | 756 |
| 9 | 0.576 | 0.607 | 755 | 0.613 | 0.638 | 755 |
| 10 | 0.622 | 0.621 | 755 | 0.681 | 0.709 | 755 |

The table shows where the gap comes from. Both forecasters track the observed rate roughly bin by
bin. The difference is **resolution**: the close spreads its probabilities from about 0.36 to 0.68
and the observed rates follow it across that whole range, while the model stays between about 0.42
and 0.62. The model is not badly miscalibrated; it separates high-scoring matches from low-scoring
ones less sharply than the close does.

## 5. What the gaps mean

### 5.1 Information the close has and public box scores do not

The gaps are the size one would expect from what the models cannot see.

- **MLB.** The Elo does not see the starting pitcher. The probable starter is known to the market
  well before first pitch and is among the most important single inputs to a baseball game price.
- **Soccer.** A results-and-match-stats Poisson model sees neither team news (confirmed line-ups,
  injuries, rotation) nor weather, and it is scored against Pinnacle, whose close aggregates the
  final views of the sharpest participants.
- **NBA.** The Elo sees no injuries, rest or lineups. In the NBA these are announced late and move
  the price a great deal, so the expected direction is the same, even though n=372 cannot resolve
  the size.

The common factor is late information. A public-data model fixed hours before the start cannot know
what the market learns in the final hours, and the close is the price after all of it.

### 5.2 Why the earlier label was corrected on 2026-09-24

Before 2026-09-24 the public pages labelled the MLB and soccer rows "MATCH within sampling noise"
(that label is corrected and superseded). It came from the harnesses' fixed tolerance thresholds on
the point gap (MATCH if the gap was at most 0.005 for MLB and 0.012 for soccer). Those thresholds
are not intervals. When the rows were recomputed with the game-clustered DM test, both intervals
excluded zero by a wide margin. The pages were corrected the same day, by adding the new rows and
superseding notes rather than deleting the old text.

The corrected sentence is the one in section 4.1: on MLB moneyline and soccer O/U 2.5 the model
TRAILS the close, and only the NBA row, which is underpowered, cannot be distinguished from it.

The same recompute found two smaller problems, both since fixed: one public page reported the NBA
row with n=743, which is the overlap count rather than the 372 scored games; and two pages gave
different NBA close Brier scores (0.1666 and 0.1672) without saying which devig method each used.
Both values are correct for their method, and section 4.1 shows both with the method named.

### 5.3 In-game: the model also trails the live price

The same conclusion holds in play. Gate A-0
([`GATE_A0_2026-09-14.md`](../evidence/ingame/GATE_A0_2026-09-14.md)) scored the in-game models
against the contemporaneous Kalshi price on identical ticks, with a game-clustered bootstrap
interval (2,000 resamples).

| Sport | Model Brier | Kalshi price Brier | Delta | CI | Games | Reading |
|---|---|---|---|---|---|---|
| MLB win probability | 0.2377 | 0.2067 | +0.0310 | [0.0170, 0.0454] | 227 | BEHIND |
| Soccer (international) | 0.2279 | 0.1427 | +0.0852 | [0.0488, 0.1270] | 51 | BEHIND |

Source: [CANONICAL_FIGURES.json](../evidence/CANONICAL_FIGURES.json) keys `mlb_ingame_vs_kalshi_mid`
and `soccer_ingame_vs_kalshi_mid`. Both corpora later failed a join-integrity check. The 178-game
segmented MLB revision keeps the verdict, and 27 of the 51 soccer files were kept after
segmentation. In both sports the market is closer to the outcome than the model.

## 6. What is not claimed

The repository keeps a do-not-claim list in
[`docs/JOB_EVIDENCE_PACKET.md` section 4](../JOB_EVIDENCE_PACKET.md). The parts that bear on this
paper, in prose:

- **No forecaster here is sharper than the close or the live price.** Every resolved row trails. The
  NBA row is underpowered and is not described as parity.
- **No claim of any return, gain or money result of any kind.** No order has ever been placed on any
  venue. All forward work is paper only.
- **Earlier headline figures are retracted and are not repeated here.** A pregame betting-return
  figure was retracted as a grading artifact: the grader picked each bet's direction from the
  market's own devigged lean and never read the model. An end-of-third-quarter in-play Brier figure
  was retracted because two features peeked at the quarter being predicted. An in-play hit-rate and
  return figure was retracted because it was graded against a soft proxy line rather than real
  closing prices. An aggregate closing-line-value figure was retracted as circular. The retracted
  numbers appear only inside the explicit retraction context of the evidence packet.
- **No closing-line-value reading exists yet.** No forecast has yet been recorded before the close
  and then compared with it in a qualifying way
  ([`docs/CLV_AND_MARKOUT.md`](../CLV_AND_MARKOUT.md) section 3).
- **No candidate signal survived.** All 60 candidate signal classes in the catalogue
  (`scripts/platformkit/eval_gate/spa_catalog_report.txt`) were rejected after the multiplicity
  correction (evidence packet, section 4). That is reported as a result, not hidden.
- **No per-game NBA or MLB data is published**, for the licence reasons in section 2.

## 7. What comes next, prospectively

Everything in sections 4 and 5 is retrospective: the holdouts were scored after the games. The next
step is a record fixed before the games are played. It is **planned, not done**; the spec is
[`S782_FORWARD_FORECAST_LOG_SPEC_2026-10-06.md`](../evidence/harness/S782_FORWARD_FORECAST_LOG_SPEC_2026-10-06.md).

- **What is logged.** Every in-scope NBA regular-season and playoff game gets one home-win
  probability from the same measured Elo function as the NBA row above, imported, not reimplemented.
  There is no selection; every in-scope game is logged.
- **Cut rule.** cut_ts = min(15:00Z on the listing day, earliest start minus 120 minutes). The only
  inputs are box scores dated before the listing day plus that day's schedule. No odds, no Kalshi
  price and no injury feed are inputs.
- **Witness.** Each day's file is committed by explicit pathspec and pushed; the GitHub server-side
  push time, not the commit date, decides whether a row was on time. Late, unwitnessed or edited rows
  are excluded and counted.
- **Comparator.** The proportionally devigged Kalshi mid at the same cut_ts: two-sided, at most 30
  minutes old, spread at most 0.10, with Shin as a sensitivity. The last pre-start mid is reported
  separately as the "close" cell.
- **Weekly scoring.** Every Monday at 13:00Z: Brier and log loss, game-clustered DM interval,
  date-clustered sensitivity, MDE and reliability bins, from the same `dm_test.py`. The first weekly
  file covers 2026-W43 (games of 10-20 to 10-25) and is due on Monday 2026-10-26.
- **Floor.** A verdict is printed only on the cumulative cell, and only once it has at least 150
  paired games (about three weeks). Below that the cell reads INSUFFICIENT with its n and MDE.
- **Seal.** The rules are sealed in a pre-registration file before the first row counts (default
  seal day 2026-10-15, hard limit 2026-10-19 12:00Z, effective from 2026-10-20). Amendments apply
  only to future days.
- **Expected reading, stated in advance.** The model sees no injury, rest or lineup information and
  carries last season's ratings into the new season without regression, so the spec says the early
  rows are expected to read worse than the retrospective holdout.

**The paper maker desk.** Separately, an in-play paper desk rests simulated maker quotes and credits
a fill only when later captured trades deplete the modelled queue ahead of the quote. To 2026-10-04 the paper desk has 10 nights with any receipt (2 COMPLETE), 0 qualified games, and 136 TTL-30 credited paper fills on unqualified tape; every pooled cell is INSUFFICIENT.
Both fill counts carry an uncertainty marker in the source: 136 (?4) TTL-30 and 48 (?4) TTL-5
credited fills, where (?4) means the count is unknown on 4 nights, so the true totals may be higher
(sources: [CANONICAL_FIGURES.json](../evidence/CANONICAL_FIGURES.json) key `paper_desk_fill_counts`
and [cumulative/2026-10-04.md](../evidence/forward/cumulative/2026-10-04.md)). These are
counts, not a verdict. No markout level is published yet (definitions in
[`docs/CLV_AND_MARKOUT.md`](../CLV_AND_MARKOUT.md) section 4).

## 8. Reproduce in five minutes

With Python 3.10+, numpy and pytest, from the repository root. Commands 1 to 4 are from
[`docs/QUANT_BRIEF.md` section 6](../QUANT_BRIEF.md) and their files are on the public allowlist;
they were run for this paper on 2026-10-06 on this (private) checkout, with the outputs shown
(7, 4 and 7 passed), not from a fresh public clone.
Command 5, the scorer on the soccer CSV, runs only in the
private tree until licence ledger row 7 is decided.

| # | Command | Expected | What it checks |
|---|---|---|---|
| 1 | `python -m scripts.platformkit.eval_gate.claim_consistency --repo-root .` | `claim_consistency: 0 finding(s)`, exit 0 | every canonical figure agrees across every tracked page under docs/ plus README and EVIDENCE, this one included; no retracted figure outside retraction framing |
| 2 | `python -m pytest scripts/platformkit/eval_gate/test_claim_consistency.py -q` | `7 passed` | the gate itself |
| 3 | `python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q` | `4 passed` | the game-clustered DM recompute behind section 4.1, on fixtures |
| 4 | `python -m pytest scripts/platformkit/eval_gate/test_shin.py -q` | `7 passed` | the Shin devig of section 3.2 |
| 5 | `python -m scripts.platformkit.eval_gate.score_vs_close --csv docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv --devig proportional` | exit 0; JSON with `"n": 7558`, `"gap": 0.007575654573945858`, `"verdict": "TRAILS_CLOSE"` | the soccer row end to end from the per-game file (section 4.3; private tree until row 7 is decided) |

To check that the CSV is the committed file: the committed blob has sha256
`68084c2d05836e1cbbfb61a96ee7eb676761ec4a90824e2bf8c005c6c48b0105` (710,594 bytes, as on the data
card). On a Windows checkout that converts line endings, the working copy hashes differently; hash
the committed blob instead with
`git show HEAD:docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv | sha256sum`. The scorer
gives the same output either way.

A reviewer who wants to break the scorer can try: duplicate a row, set an outcome to 2, add a row
whose `p_model` equals its outcome, or mix devig methods. Each produces `"status": "REFUSED"` with a
counted reason and exit code 3.

## Appendix: full scorer output (verbatim, 2026-10-06)

```json
{
  "schema": "score_vs_close/v1",
  "status": "OK",
  "n": 7558,
  "n_clusters": 7558,
  "devig_method": "proportional",
  "model_brier": 0.24653174209394257,
  "close_brier": 0.23895608751999672,
  "gap": 0.007575654573945858,
  "gap_sign": "positive = model trails the close; dm_stat has the same sign as gap",
  "ci95": [
    0.005944816121945759,
    0.009206493025945957
  ],
  "dm_stat": 9.105983862301864,
  "dm_p": 1.0772791656587416e-19,
  "mde": 0.002330468147908141,
  "mde_power": 0.8,
  "model_log_loss": 0.6861514938971582,
  "close_log_loss": 0.6706680132300011,
  "reliability": {
    "model": [
      {
        "mean_p": 0.42059991763949955,
        "observed_rate": 0.4576719576719577,
        "count": 756
      },
      {
        "mean_p": 0.45486053690145173,
        "observed_rate": 0.42328042328042326,
        "count": 756
      },
      {
        "mean_p": 0.47345110785673444,
        "observed_rate": 0.4775132275132275,
        "count": 756
      },
      {
        "mean_p": 0.4889054037255056,
        "observed_rate": 0.4708994708994709,
        "count": 756
      },
      {
        "mean_p": 0.5042739974367186,
        "observed_rate": 0.5224867724867724,
        "count": 756
      },
      {
        "mean_p": 0.5183400998465748,
        "observed_rate": 0.5251322751322751,
        "count": 756
      },
      {
        "mean_p": 0.533130455356135,
        "observed_rate": 0.5158730158730159,
        "count": 756
      },
      {
        "mean_p": 0.5512018593544109,
        "observed_rate": 0.541005291005291,
        "count": 756
      },
      {
        "mean_p": 0.5762200101054396,
        "observed_rate": 0.6066225165562914,
        "count": 755
      },
      {
        "mean_p": 0.6223479268849803,
        "observed_rate": 0.6211920529801325,
        "count": 755
      }
    ],
    "close": [
      {
        "mean_p": 0.3592440307772085,
        "observed_rate": 0.36904761904761907,
        "count": 756
      },
      {
        "mean_p": 0.41483845494037697,
        "observed_rate": 0.4021164021164021,
        "count": 756
      },
      {
        "mean_p": 0.44358212122050816,
        "observed_rate": 0.3994708994708995,
        "count": 756
      },
      {
        "mean_p": 0.46838336948163406,
        "observed_rate": 0.4656084656084656,
        "count": 756
      },
      {
        "mean_p": 0.4920839312492464,
        "observed_rate": 0.503968253968254,
        "count": 756
      },
      {
        "mean_p": 0.5162613080544255,
        "observed_rate": 0.5052910052910053,
        "count": 756
      },
      {
        "mean_p": 0.5432832100190249,
        "observed_rate": 0.5727513227513228,
        "count": 756
      },
      {
        "mean_p": 0.57330362517141,
        "observed_rate": 0.5965608465608465,
        "count": 756
      },
      {
        "mean_p": 0.6132617103856215,
        "observed_rate": 0.6384105960264901,
        "count": 755
      },
      {
        "mean_p": 0.6805149923556911,
        "observed_rate": 0.7086092715231788,
        "count": 755
      }
    ]
  },
  "verdict": "TRAILS_CLOSE",
  "reasons": {},
  "note": "calibration readout, paper only, not a verdict"
}
```

---
Generated 2026-10-06. Figures from `docs/evidence/CANONICAL_FIGURES.json` (last changed in commit
5f6205f76) and `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md` (commit 34b9e7f7d); the scorer was
run on the tree at commit f485b1c2a against the CSV committed in f627f2e96. Calibration readout;
paper only.

**Navigate:** [Quant brief](../QUANT_BRIEF.md) - [Methods page](../CLV_AND_MARKOUT.md) - [Kalshi note](../KALSHI_NOTE.md) - [Evidence index](../../EVIDENCE.md) - [Job Evidence Packet](../JOB_EVIDENCE_PACKET.md)
