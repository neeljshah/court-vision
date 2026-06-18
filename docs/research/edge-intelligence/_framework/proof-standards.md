# PROOF STANDARDS -- how a candidate edge becomes a trusted one (and the traps that fake it)
_Part of the edge-intelligence corpus. The bar every lever/edge must clear before we trust it
or risk money. Grounded in the project's eval-gate + its hard-won anti-overfit lessons. ASCII._

## The bar (in order; a claim must clear each to advance a tier)
1. LEAK-FREE construction. To predict event E, use ONLY data with timestamp < E. Separate
   train/inference builders; verify a feature is actually read at inference (train/inference
   parity -- the most expensive bug class: new features silently read 0.0 at inference).
2. WALK-FORWARD out-of-sample. No in-sample scoring. Each prediction uses only its past.
   Temporal train/test split for any fitted calibrator (e.g. isotonic recal must be fit on
   earlier matches, tested on later -- in-sample isotonic ALWAYS looks good and overfits thin
   data; that's why WC recal was DEFERRED).
3. PROPER SCORING. Brier + ECE (paired with sharpness so collapse-to-0.5 isn't "calibrated")
   + log-loss; Brier-Skill-Score vs the devigged close (BSS>0 = sharper than market). For
   significance, cluster-robust Diebold-Mariano (games are correlated; naive t-tests lie).
4. >= 2 INDEPENDENT corpora / folds agree. A single good fold of four is usually a SELECTION
   ARTIFACT -- do not promote. (Project-wide: many single-fold "lifts" reverted.)
5. SEED / N stability. A big jump from one seed or tiny-N -> run multi-seed + larger-N before
   shipping. Small-N ROI is noise (e.g. -47% on 7 bets means nothing).
6. FORWARD CLV. The final bar for real money: positive closing-line value accrued FORWARD on
   paper at a meaningful sample. Calibration proves sharpness; CLV proves it pays.

## The overfit traps (how fake edges sneak in -- watch for each)
- TOO-TIGHT DISTRIBUTION: under-dispersed Poisson on count stats invents fat tails -> absurd
  EVs (saw +131%). FIX: NB where overdispersed + conformal width; FLAG implausible |EV|.
- IN-SAMPLE CALIBRATION: fitting a recalibrator on the same data you score. ALWAYS test OOS.
- MARKET-FOLLOW ARTIFACT: a model that tracks the line will look profitable on flat-payout
  backtests with vig ignored. (Source of the retracted +18.38%.) Always devig + use real prices.
- SELECTION: reporting the best stat/fold/segment after looking at all of them. Pre-commit, or
  bonferroni/penalize, or require independent replication.
- THIN-DATA CONFIDENCE: 1 match/player -> "reliable" only if a strong PRIOR backs it (club/
  season stats); else it's model-view, not actionable. The confidence/tier label enforces this.
- TEAMMATE/CONTEXT LEAK in counting stats (RBIs/Runs depend on others) -> own-rate models
  miscalibrate; measure per-stat and demote the leaky ones.

## The gate (operational)
- The real leak-free eval-gate (scripts/platformkit/eval_gate/ + props_eval*) is the ONLY
  arbiter. A lever's verdict is SHIP / HOLD / REJECT / INSUFFICIENT_DATA from the gate, never
  a hand-wave. Mirror it; never build a parallel stub that can drift from the real gate.
- The ratchet: a change ships only if it does NOT regress vs the frozen baseline AND beats it
  beyond tolerance OOS. Only-improve-or-hold. Rejections are recorded (they're knowledge).
- Cold start: < ~60 settled outcomes -> INSUFFICIENT_DATA; accrue before judging.

## Evidence tiers (restate; used corpus-wide)
HYPOTHESIS -> CALIBRATION-PROVEN (leak-free OOS BSS>0) -> CLV-PROVEN (forward paper CLV>0).
Every edge file states its tier + the artifact (which gate run / which backtest) that earns it.

## Honesty contract (binding)
No fabricated $-edge. Never reprint retracted artifact numbers as current (+18.38% / endQ3
0.119 / +54% / 78.11). A REJECT or NULL is a SUCCESS -- it saves effort. Calibration is the
claim we make; profit is the claim we only make after CLV proves it, on paper, gated.
