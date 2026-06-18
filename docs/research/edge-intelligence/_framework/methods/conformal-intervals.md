# METHOD: Conformal prediction intervals + the sigma-too-tight fix
_Method library / edge-intelligence corpus. How to get HONEST coverage on prop intervals, the
split-conformal recipe, the cheaper sigma-inflation fix, and when each applies. Grounded in the
live conformal class + the measured per-stat inflation factors. ASCII only._

## The problem: emitted prop intervals under-cover
A point model predicts a player prop (e.g. 22.5 PTS) and emits an interval / sigma used to size
bets and price alt-lines. VALIDATED defect (n=50,954/stat, walk-forward on `pregame_oof.parquet`):
the emitted per-player `sigma` is systematically TOO NARROW on EVERY stat, so the nominal "90%"
band under-covers. A too-tight interval over-states confidence -> over-aggressive Kelly and a
fabricated tail edge (same family as the too-tight count trap; see poisson-vs-negbin-for-counts).
The fix is to make the interval's COVERAGE match its label, measured out-of-sample.

## The coverage test (always run this first -- it picks the fix)
Coverage = fraction of holdout outcomes that fall inside the nominal-C% interval. Target: a
"90%" interval should realise ~0.90. Diagnose direction:
- Realised < nominal (under-covers): interval TOO TIGHT -> inflate (sigma factor or conformal q).
- Realised > nominal (over-covers): interval TOO WIDE -> the model is too conservative; this is
  why switching a too-tight Gaussian to NegBinom is the WRONG fix (NB realised ~0.96 on blocks).
Pair coverage with WIDTH: a 0.5->collapse-wide interval can hit coverage trivially while being
useless. Want minimal width at the target coverage.

## Fix A -- split conformal (distribution-free, finite-sample guarantee)
Split conformal gives `P(y_true in [y_hat - q, y_hat + q]) >= coverage` for ANY distribution, with
only an exchangeability assumption.
1. Hold out a CALIBRATION set (the engine uses ~10% of training), kept separate from fitting.
2. Compute calibration residuals `|y_cal - y_hat_cal|`.
3. For coverage C, `q = the C-quantile of those |residuals|`. (Finite-sample: use the
   ceil((n+1)*C)/n quantile for the strict guarantee; the live class uses np.quantile, close for
   large n.)
4. Interval = `[y_hat - q, y_hat + q]`; width = `2q`.
WHEN: you want a guaranteed-coverage interval with no Gaussian assumption, and you have enough
calibration residuals per stat. Per-stat residuals (fit one q per prop) respect that blocks spread
much wider than rebounds. Symmetric `|residual|` conformal assumes symmetric error; for skewed
count residuals use signed/quantile-conformal (separate lower/upper q) to avoid biased bounds.

## Fix B -- per-stat sigma inflation (the cheaper, validated production fix)
When the model already emits a Gaussian sigma, just rescale it by the empirically measured factor
so coverage returns to nominal:

    sigma_corrected = sigma_emitted * inflation_factor[stat]

Measured inflation = empirical residual std / emitted sigma (walk-forward, n=50,954/stat):
    blk x1.86 (coverage 0.750 -> 0.914)   pts x1.27   fg3m x1.30   stl x1.26
    ast x1.25   reb x1.20   tov x1.25
Blocks are worst because their residual spread (0.742) is ~1.9x the emitted (0.398). Apply the
factor BEFORE forming intervals / sizing Kelly. This restored ~0.90 coverage. NOTE the explicit
lesson: this was once mis-framed as "blk has fat tails, use NegBinom" -- NegBinom OVER-covers
(0.96), so simple sigma inflation is correct, NOT a distribution swap.

## Conformal vs sigma-inflation (the WHEN)
- Conformal: distribution-free, no Gaussian assumption, formal coverage guarantee, but needs a
  clean per-stat calibration holdout and assumes exchangeability (watch for distribution drift /
  rule changes that break it). Best when residuals are non-Gaussian or you want the guarantee.
- Sigma inflation: trivially cheap, validated in production, preserves the Gaussian shape and the
  emitted center. Best as the first-line fix when you already have a sigma and a measured factor.
- Either way the test is the same: OOS coverage at the nominal level, with width reported.

## Apply where it matters
Honest coverage is most load-bearing in the SOFT-PROP pocket (PrizePicks/Underdog), where the
interval feeds alt-line pricing and stake sizing. A too-tight interval there is the mechanism that
turns model noise into a fabricated tail edge. Wiring guidance in the corpus already says: only
bet when `interval_width < 1.5 * vig_width` -- which is only meaningful once the interval is
honestly calibrated.

## Code pointers
- `src/prediction/conformal_props.py` -- `ConformalPredictor`: `calibrate(y_cal, y_hat_cal)`
  stores `|residuals|` (line 56); `predict_interval(y_hat, coverage)` (59-76) returns
  `[y_hat - q, y_hat + q]`; `interval_width` (78-80) = `2q`; `_quantile` (82-87) is the
  C-quantile of residuals with a wide fallback (5.0) when uncalibrated; `save_residuals` /
  `load_residuals` persist per-stat residual arrays to `data/models/conformal_{stat}_residuals.npy`.
  NOTE: this is a HUMAN-GATED path (`src/**`) -- read-only here; propose changes, do not edit.
- Sigma-inflation artifacts: `data/cache/profiles/_reference/interval_sigma_recommendation.json`
  (the per-stat factors), `scripts/recalibrate_count_intervals.py` (recompute script),
  `data/cache/blk_player_dispersion.parquet` (per-player blk overdispersion, median phi=1.167).
- Count-marginal alternative (genuinely over-dispersed COUNTS, not point intervals):
  poisson-vs-negbin-for-counts.md + `domains/mlb/negbinom_engine.py`.

## Failure modes
- IN-SAMPLE CALIBRATION: computing q or the inflation factor on the data you scored -> always
  looks calibrated, overfits thin data. Use a temporal/walk-forward holdout (proof-standards.md).
- WRONG DIRECTION: switching an under-covering Gaussian to NegBinom -> over-coverage (the blk
  lesson). Run the coverage test to confirm direction before choosing a fix.
- SYMMETRIC q ON SKEWED RESIDUALS -> biased bounds; use signed/quantile-conformal.
- EXCHANGEABILITY BREAK: distribution drift (rule change, role change) voids the conformal
  guarantee; re-calibrate per regime.
- COVERAGE WITHOUT WIDTH: a wide interval trivially covers; always report width too.
- ONE GLOBAL q/factor across stats -> mis-covers; calibrate per stat (blk != reb).

## Proof tier
CALIBRATION-PROVEN method: the sigma-inflation factors are measured leak-free walk-forward
(coverage 0.750 -> 0.914 on blocks), and split conformal carries a finite-sample coverage
guarantee under exchangeability. This is a CALIBRATION fix -- it makes intervals honest, it is not
a $-edge. A bet sized off a now-honest interval still must clear forward CLV to be CLV-PROVEN.
