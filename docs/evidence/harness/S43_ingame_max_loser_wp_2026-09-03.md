# S43 -- max-loser-WP on the per-tick in-game stream (2026-09-03)

## What the row said, and what changed

S43: `max_loser_wp` is DEGENERATE on the pregame gate corpora -- one row per
`event_id`, so every "game path" is a single tick and the peak is just that
tick's own probability. The diagnostic needs the per-tick in-game stream. This
lane feeds it that stream. Nothing is gated: the numbers below are DESCRIPTIVE.

Module: `scripts/platformkit/eval_gate/ingame_calibration_report.py`
(`build_ingame_report(ticks, series, outcomes, game_ids, *, bins=10)`), composed
ONLY of existing pieces -- `wp_diagnostics.max_loser_wp` and
`wp_diagnostics.reliability` bound to `calib_decomp.bin_edges` (the ONE S42 bin
rule), `calib_decomp.decompose` (three Murphy terms), `eval_gate.scoring.ece` /
`.sharpness`, and `ingame.gap_effective_n.effective_sample_size`.

Artifact: `docs/evidence/calibration/mlb_ingame_reliability_2026-09-03.json`.

## Corpus

MLB window-1 store `data/cache/ingame_grade_joined`, the S06 scored denominator:
**47,104 ticks / 158 games**, of which **81 games were losses** for the modelled
side -- so 81 real multi-tick loser paths, against the pregame corpora's
single-tick degenerate ones. Series come from the S06 per-tick emission
(`data/cache/eval_gate/s06_stacker_series_2026-09-03.csv`, columns `raw_model`
and `pair_leakfree` = the game-first-date leak-free e4 of S36) joined to the
store's per-tick `market_prob` by `_row_id`; no arm was refit here.

Reproduction (A2): the three Briers reproduce the sealed anchors exactly --
raw_model 0.236683 vs the S06 arm-reproduction target 0.236682901513263, e4
leak-free 0.206786 vs 0.206785778212713, market 0.195387 vs the E4 promotion
artifact's market Brier 0.195387. The report also recomputes its own ECE and
both fitted Murphy terms from its published bins:
`reproduction_max_abs_diff` = 2.03e-15.

## The three series (descriptive)

| series | Brier | ECE | Murphy REL | Murphy RES | Murphy UNC | sharpness |
|---|---|---|---|---|---|---|
| raw_model | 0.236683 | 0.086901 | 0.013128 | 0.024746 | 0.248657 | 0.060027 |
| e4_blend leak-free (game-first-date) | 0.206786 | 0.074150 | 0.009860 | 0.051061 | 0.248657 | 0.061100 |
| market (per-tick `market_prob`) | 0.195387 | 0.066715 | 0.006109 | 0.058095 | 0.248657 | 0.049713 |

Max-loser-WP across the 81 loser games (the largest probability each series ever
put on the eventual LOSER, over that game's own tick path):

| series | p50 | p90 | max | > 0.8 | share > 0.8 | > 0.9 | share > 0.9 |
|---|---|---|---|---|---|---|---|
| raw_model | 0.6582 | 0.9677 | 0.9832 | 34 | 0.4198 | 29 | 0.3580 |
| e4_blend leak-free | 0.6700 | 0.9059 | 0.9797 | 13 | 0.1605 | 9 | 0.1111 |
| market | 0.6200 | 0.8900 | 0.9550 | 12 | 0.1481 | 6 | 0.0741 |

Read: on this window the raw model put >0.8 on the eventual loser in 34 of 81
lost games (0.4198) and >0.9 in 29 (0.3580); the leak-free e4 guard cuts that to
13 (0.1605) / 9 (0.1111), landing near the market's 12 (0.1481) / 6 (0.0741).
The median loser peak is not separated (0.66 / 0.67 / 0.62) -- the difference is
in the tail, which is exactly the premature-confidence failure the diagnostic
exists to see and which the pregame corpora cannot express.

## Effective sample size (labels, not a test)

`gap_effective_n.effective_sample_size` on each series' OWN per-tick residual
loss `(model_prob - outcome) ** 2`, clustered by game (the function's column is
named `loss_differential`; here it carries a level, not a paired difference):

| series | ICC (rho) | design effect | n_eff |
|---|---|---|---|
| raw_model | 0.324834 | 97.517 | 483.03 |
| e4_blend leak-free | 0.361364 | 108.371 | 434.66 |
| market | 0.373770 | 112.057 | 420.36 |

47,104 ticks are worth ~420-483 independent observations, and the loser-peak
distribution has n = 81 games. Any future bar must be set against those, not
against 47,104.

## Descriptive only (Q3, Q6)

No bar, no threshold and no gate is armed by this artifact; `mode` is
`DESCRIPTIVE` and the JSON carries the same statement. Max-loser-WP is REPORTED
here. Before it could gate a promotion it would need its OWN prereg-sealed bar,
fixed and sealed before the first metric (Q3) -- setting one now, after seeing
the table above, is exactly the move the contract forbids. Nothing was charged: this lane
neither imports `_charge_ledger` nor opens the FWER ledger (its 14 rows are
quoted from the lane brief, not read here). Nothing promoted, nothing served.
Calibration language only; no dollar, ROI, profit or edge claim is made or
implied by any number here.

## Test

`scripts/platformkit/eval_gate/test_ingame_calibration_report.py` -- 4 passed:
per-game max-loser-WP taken only over the losers' own probabilities (winners at
0.95 never appear), a calibrated series' Murphy reliability term near zero with
self-reproduction < 1e-9, published bin edges identical to
`calib_decomp.bin_edges(10)` with the bin counts summing to n, and a misaligned
series refused.

## NOT VERIFIED

- Single window (2026-06-28..07-12), one sport. No second corpus; nothing here
  is an AHEAD claim, so Q5 is not engaged.
- `market_prob` is the per-tick captured price from
  `live_grade.capture_pair_once`. This lane did NOT verify how it is devigged;
  it is reported as the captured market series, the same one the E4 trial scored.
- The 81/158 loss split is the modelled side's outcome as carried in the store;
  no independent settlement re-check was run.
- ICC/design-effect are descriptive labels; no interval or test is computed from
  them here.
