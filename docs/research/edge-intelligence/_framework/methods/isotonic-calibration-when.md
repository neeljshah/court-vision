# METHOD: Isotonic calibration -- when it helps, when it OVERFITS, how to test it
_Part of the edge-intelligence method library (B). Reusable recipe. ASCII only.
Code pointers: domains/soccer/prop_recal.py (the reference impl + the WC DEFER),
scripts/platformkit/eval_gate/walkforward.py (the leak-free split that must feed it),
scripts/platformkit/props_eval.py::backtest_pairs (the leak-free pair generator)._

## What it is (the math)
Isotonic regression fits a MONOTONE NON-DECREASING map g: p_raw -> p_calibrated by
Pool-Adjacent-Violators (PAVA). Given pairs (p_i, y_i) sorted by p_i (y in {0,1}):
  1. Pool exact-duplicate p into one point with the mean outcome.
  2. Walk left->right; whenever block mean[k-1] > block mean[k], MERGE the two blocks
     into their (weighted) mean. Repeat until the sequence is monotone non-decreasing.
  3. The result is a step function; we store it as sorted knots (x, y) and apply by
     piecewise-linear interpolation, clamped to [0,1] and to the knot range.
Reference: prop_recal.py::pava (pure-python PAVA) + ::recalibrate (interp + clamp).
It is NONPARAMETRIC -- it makes NO shape assumption (unlike Platt/sigmoid). That is its
strength on a systematically-biased regime (e.g. a model under-confident on rare events)
and its WEAKNESS: with few points it will happily carve the noise into "calibration."

## Why it OVERFITS on thin data (the core failure)
Isotonic has effectively as many free parameters as it has distinct (p, y) blocks. On a
small N it can drive IN-SAMPLE Brier/ECE to near-zero by memorizing the empirical
frequency of each little bin -- a map that does NOT generalize. Two consequences:
  - In-sample calibration ALWAYS looks good. It is not evidence of anything.
  - The flat tails (clamp to first/last knot) extrapolate a single noisy extreme bin to
    every future out-of-range prediction.
This is exactly why the World Cup recal was DEFERRED: ~24 WC matches yields too few
(p, outcome) pairs per stat for the fitted map to be trustworthy OOS. prop_recal.py
encodes the guard literally: `MIN_N = 150` pairs/stat, else the stat is SKIPPED
(identity map), plus the file's own honesty note: "isotonic recal on ~24 WC matches is
THIN/approximate; improves in-sample calibration only; re-fit as data grows + validate
OOS. calibration != edge." (prop_recal.py lines 26-28, 43, 187-189.)

## The temporal-split test (the ONLY way to trust it)
Never score a calibrator on the data it was fit on. Use a TEMPORAL (not random) split,
because a random K-fold leaks future matches into the training of the map.
  Recipe:
  1. Generate leak-free (p_raw, y) pairs via the SAME walk-forward loop the readout
     scores -- props_eval.backtest_pairs, where each match builds its distribution from
     data strictly before it (prop_recal.py lines 18-22, 157-164). Tag each pair with its
     event timestamp.
  2. Split by time: fit g on the EARLIER fraction (e.g. first 70% of matches by date),
     freeze it, apply to the LATER 30%.
  3. Score the later fold TWICE: with identity (raw p) and with g(p). Metrics: Brier,
     ECE (paired with a sharpness check so collapse-to-0.5 isn't read as "calibrated"),
     log-loss. Accept g ONLY if it improves OOS Brier/ECE on the held-out later fold
     beyond noise -- and replicates on >=2 such splits / corpora (proof-standards.md bar 4).
  4. Cluster-robust significance: differences are correlated within a match/player; use
     eval_gate/dm_test.py::diebold_mariano clustering on game_id/match before claiming a
     win. A naive i.i.d. SE runs ~3x too narrow and manufactures fake significance.
  Decision: SHIP only if OOS-improves-and-replicates; else DEFER (keep identity) and
  record the reject -- a DEFER is a success, it saves us from shipping noise.

## When isotonic is SAFE to use
  - N is large per bin: rule of thumb MIN_N >= 150 pairs PER stat (the prop_recal.py
    threshold); more is better. Thin per-stat data -> skip that stat, don't fit noise.
  - The bias is SYSTEMATIC and monotone (e.g. model uniformly under-confident on the low
    regime) -- the case prop_recal.py targets; a monotone map is the right tool.
  - You can run the temporal-split test above and it OOS-improves on >=2 splits.
  - You re-fit as data grows (the map is not frozen forever) and re-validate each refit.
  - Public functions degrade to IDENTITY on any failure / missing file (recalibrate()
    returns clamped raw p) so a bad/absent calibrator can never make predictions worse.

## When to PREFER an alternative
  - Very thin data with a known shape: a 1-parameter Platt/logistic (temperature) scaling
    overfits far less than isotonic -- fewer DOF. Use it as the thin-data default; reach
    for isotonic only once N supports it.
  - Strong prior available (club/season rates for a player with 1 WC match): blend the
    prior in BEFORE calibrating; don't let isotonic invent a per-player map from 1 game.

## Failure modes to watch (each has bitten this project)
  - IN-SAMPLE SCORING reported as a win (proof-standards.md trap #2). The map will always
    look great in-sample. Disregard in-sample calibration entirely.
  - RANDOM K-fold instead of temporal split -> future leaks into the map's training.
  - FLAT-TAIL extrapolation: a single noisy extreme bin sets g for all out-of-range future
    p. Inspect the knot endpoints; consider widening the trusted middle and shrinking tails.
  - SELECTION across stats: fitting all stats, reporting only the ones that improved.
    Pre-commit the stat list or penalize; require independent replication.
  - DRIFT: a calibrator fit on last season's pricing/scoring environment goes stale.
    Re-fit on a rolling window; treat the map as a cache, not a constant.

## Evidence-tier reminder
A passing temporal-split is CALIBRATION-PROVEN (sharper OOS), NOT a $-edge. calibration
!= edge: a better-calibrated P(over) does not imply beating the line. CLV (clv-computation.md)
is the separate, later bar before any real money. The WC recal sits at: HYPOTHESIS/DEFERRED
(thin N); promote only after the temporal-split test passes on grown data.
