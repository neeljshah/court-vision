# METHOD: Poisson vs Negative-Binomial for count props
_Method library / edge-intelligence corpus. WHEN to use each count model, the test that
decides, the exact conversion math, and the failure mode where a too-tight count model
FABRICATES edge. ASCII only. Grounded in the live dispersion + NegBinom code._

## The one-line decision
Estimate the dispersion index `phi = var/mean` for the stat, LEAK-FREE (only rows before the
event). `phi <= 1` -> Poisson is already wide enough, do NOT widen. `phi > 1` (over-dispersed)
-> Negative-Binomial with the SAME mean and variance = `lam*phi`. `phi < 1` (under-dispersed)
-> NegBinom CANNOT represent it; collapse toward Poisson (large r), do not floor r.

## The math (what each distribution can represent)
- Poisson(lam): mean = var = lam. One parameter. Cannot widen or narrow the tail independently
  of the mean. Correct only when the count's variance equals its mean.
- Negative-Binomial NB(r, lam): parameterised so `nbinom(n=r, p=r/(r+lam))` -> mean = lam,
  `var = lam + lam^2/r`. As `r -> inf`, NB -> Poisson. Smaller r = fatter tail. r is the size /
  dispersion parameter; it ONLY adds variance, never removes it (NB var >= lam always).
- Dispersion index `phi = var/mean`. Scale-free. `phi = 1` is Poisson; `phi > 1` over-dispersed.

## The variance>mean test (the gate that picks the model)
1. Pool the per-event counts for the stat, leak-free (timestamp strictly before the event).
2. Require a minimum N before trusting the empirical fit (the soccer engine uses `_MIN_N = 40`;
   below that fall back to a per-stat PRIOR phi, never a noisy fit -- thin data fits invent shape).
3. Compute `m = mean`, `v = var`. `phi = v/m`.
4. `phi <= 1.0`: use Poisson (the PMF is already at-or-wider than realised). Return r = None.
5. `phi > 1.0`: over-dispersed -> NegBinom. Convert phi to a size r (next section).
6. `phi < 1.0` AND you are using a method-of-moments r: r = `m^2/(v-m)` goes negative/undefined.
   Do NOT floor it to the minimum r (that is MAXIMAL over-dispersion, the wrong direction).
   Return a LARGE r (~Poisson). See `fit_r_mom` `_UNDERDISP_R = 1e6`.

## phi -> r conversion (use phi, not a global r -- the cleaner path)
A single global r is WRONG because the NB size needed for a fixed phi depends on the row's own
mean lam. Calibrate and store the scale-free `phi` per stat; convert to a ROW-SPECIFIC size at
prediction time:

    r_row = lam / (phi - 1)        when phi > 1
    r_row = None (Poisson)         when phi <= 1

This makes `NB var = lam + lam^2/r_row = lam + lam*(phi-1) = lam*phi`, i.e. the realised
over-dispersion is applied at EACH row's own scale. Two equivalent estimators of r from a sample:
- From phi at a representative mean: `r = m_rep / (phi - 1)` (a single representative size).
- Method of moments directly: `r = mean^2 / (var - mean)` (used in the MLB engine).
Clamp r to a sane band (`_R_MIN = 1.0`, `_R_MAX = 50.0` in the soccer engine): r<1 is wildly
over-dispersed (suspect data), r>50 is indistinguishable from Poisson.

## The too-tight-fabricates-edge trap (the whole reason this method exists)
A count model that is TOO TIGHT (Poisson on an over-dispersed stat) puts too little mass in the
tails. The tail O/U or alt-line then looks far more confident than reality, and `ev = p*odds - 1`
spits out an ABSURD edge -- a documented `+131%` "EV" on thin early-tournament soccer shots that
was a pure artifact of under-dispersion, not a real edge. The fix is exactly this method: widen
to NB where `phi > 1`, and additionally FLAG any |EV| above a plausibility ceiling for manual
review rather than betting it. This is one of the canonical overfit traps in proof-standards.md
("TOO-TIGHT DISTRIBUTION"). A fabricated tail edge is the single most common way a counts model
manufactures false money.

## The OPPOSITE trap (do not over-correct with NegBinom)
NegBinom is not a free "make it safer" knob. On NBA per-player props, validation
(`pregame_oof.parquet`, n=50,954/stat, walk-forward) found NegBinom OVER-covers: a "90%" NB band
realised ~0.96 coverage on blocks. The real defect there was a too-small emitted Gaussian `sigma`,
fixed by a simple per-stat sigma inflation (blk x1.86, pts x1.27, ...), NOT by switching to
NegBinom. RULE: NegBinom is for genuinely over-dispersed COUNT marginals (MLB runs, soccer shots);
for a point model whose interval is too narrow, inflate the residual scale instead (see
conformal-intervals.md). Diagnose direction with a coverage test before reaching for NB.

## WHEN to use each (summary table)
- Poisson: rare/Bernoulli-ish counts where `phi ~ 1` -- soccer Goals/Assists/Cards
  (`_PRIOR_PHI` = 1.00-1.05), any stat measuring `phi <= 1` leak-free.
- NegBinom: measured over-dispersion `phi > 1` -- soccer Shots (prior 1.35), Shots On Target
  (1.25), Fouls (1.20), Saves (1.20); MLB total runs and the run line (lumpy scoring).
- Neither / inflate-sigma: a continuous-ish point prediction whose INTERVAL under-covers ->
  conformal or sigma inflation, not a discrete count law.

## Code pointers (read these, do not reinvent)
- `domains/soccer/dispersion.py` -- the reference per-stat phi calibrator. `stat_dispersion()`
  returns `{r, phi, n, status}`; `_r_from_phi(phi, mean)` (lines 84-98) is the clamp + convert;
  `r_for_lam(phi, lam)` (lines 180-191) is the row-specific size the board calls. Per-stat priors
  `_PRIOR_PHI` and representative means `_REP_MEAN` at lines 54-81. Leak guard via `_prior_rows`.
- `domains/mlb/negbinom_engine.py` -- `fit_r_mom` (lines 59-75) is method-of-moments r with the
  correct under-dispersion handling (`_UNDERDISP_R`, NOT the floor); `_negbinom_pmf` (line 30) is
  the `nbinom(n=r, p=r/(r+lam))` PMF; `runs_matrix_nb` builds the joint; `run_validation` is the
  leak-free first-50%-fit / second-50%-score walk-forward (Poisson vs NB Brier + tail coverage).
- `domains/soccer/player_rates.py` -- supplies the leak-free per-row mean (lam) the dispersion
  module widens around; `CANON_TO_COLS` + `_prior_rows` are shared.

## Failure modes checklist
- Fitting phi on too few rows -> noisy phi -> use the per-stat PRIOR until N >= the minimum.
- Storing a single global r instead of phi -> wrong tail for players with a different lam.
- Flooring r when under-dispersed -> maximal over-dispersion, the exact wrong direction.
- Using NB to "be safe" on a point-model interval -> over-coverage; inflate sigma instead.
- Trusting a tail EV from a Poisson count without a phi check -> the +131% fabricated-edge trap.
- In-sample dispersion fit (fitting r on the same games you score) -> looks great, overfits;
  always first-half-fit / second-half-score (the MLB engine pattern).

## Proof tier
The METHOD is CALIBRATION-PROVEN (the MLB walk-forward shows NB improves tail calibration vs
Poisson, mean-preserving by design; the soccer phi calibrator is leak-free by construction). Any
specific stat's over-dispersion is a per-stat CALIBRATION measurement (`phi`, n) -- never a $ edge.
A tail EV derived from it stays HYPOTHESIS until CLV-proven forward on paper.
