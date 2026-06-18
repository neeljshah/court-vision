# MLB INEFFICIENCY CATALOG -- beatable pockets + detection recipe + proof method
_Part of the edge-intelligence corpus. Each pocket = where MLB markets plausibly crack, HOW to detect
it in-data, and the PROOF bar before trusting it. All HYPOTHESIS until a real backtest scores them --
the prop corpus is n=0 today. ASCII only._

## POCKET 1 -- Soft/DFS per-opportunity props (P1, primary)
**Thesis:** DFS apps price non-star Pitcher-Ks / Hits / Walks / Outs lazily off a stale projection;
per-PA/per-BF Bernoulli counts are exactly the shape our EB-shrunk rate x exposure engine models well.
**Detect:** after the gamelog backfill, run `props_eval_mlb.backtest_calibration_mlb` per stat; for each
DFS line, compute engine `p_over(line)` vs the implied 0.5 (pick'em) -- flag |p_over-0.5| > threshold on
the SOUND stats only (Ks/Hits/Walks/Outs). Cross-check the engine `lam` against the DFS projection; a
large lam-vs-line gap on a thin-prior player is suspicious (could be our error), on a deep-prior player
is a candidate.
**Proof:** P(over)-vs-realized calibration (Brier/ECE with sharpness pairing, `score_prop_predictions`),
BSS vs base rate per stat over >=100 INDEPENDENT player-games; then realized ROI at the fixed DFS payout
+ DFS-line movement (no two-way close -> CLV undefined). `prop_tiering.classify`: proven iff bss>=0.05 AND
n>=100 of independent events (not correlated rows). Tier today: HYPOTHESIS (n=0).

## POCKET 2 -- In-game team repricing lag (P2, decisive lever)
**Thesis:** live books lag the realized run/inning state; our `repricer.reprice(state)` reprices the
remaining-runs NegBinom off an empirical per-inning curve faster than a slow book updates.
**Detect:** replay linescores through `predict_live`; compare our live win-prob/total to the live book
line at each half-inning; flag persistent gaps that the book closes a beat later.
**Proof:** the static->conditional Brier improvement is already a clean NULL on recal (held-out ECE
0.0085, slope 0.98 -- a fitted Platt WORSENS it, so identity ships). So the calibration is GOOD; the
edge, if any, is pure TIMING/execution, provable only by forward live CLV on a fast feed -- not by the
static number. Tier: CALIBRATION-PROVEN (the number is right); edge is HYPOTHESIS (timing-bound).
**Honesty:** the per-inning curve (`repricer._INNING_SHARES`) and `F5_FRACTION=0.521` are IN-SAMPLE
(`markets.py:46`); replace with OOS versions (`proof_mlb/curve_oos.py`) before trusting late-inning edges.

## POCKET 3 -- Starting-pitcher mispricing on soft books (P1/P3)
**Thesis:** who is pitching is the biggest single-game MLB variable; a soft book or DFS app slow to
reflect a confirmed/changed SP, or one ignoring SP first-6 form, is exploitable.
**Detect:** `asof_sp_form.build_sp_form_features` (`:170`, EW alpha 0.35, MIN_PRIOR_STARTS=3, strips
bullpen IP) emits `sp_first6_diff_ew`; `sp_elo_offset` turns it into a win-prob delta `w*z_sp`. Flag
games where our SP-adjusted p_home diverges materially from the book ML, especially after a same-day SP
change the book hasn't repriced.
**Proof:** the SP offset weight w is fitted leak-free (bounded scalar log-loss min, `sp_elo_offset.py:133`)
and measured in the proof layer (`fusion_mlb`/`calibration_scoreboard`). To claim edge: re-score the
SP-adjusted predictor vs the devigged close (BSS, cluster-robust DM) -- if BSS>0 here but ~0 on pure Elo,
SP is real signal the close already had; if it merely matches close, it is calibration, not edge. Tier:
CALIBRATION-relevant (validated lever), edge HYPOTHESIS. **Action: wire into `MLBPredictor` first.**

## POCKET 4 -- Multi-outcome props mispriced BY US (anti-pocket / trap)
**Thesis:** Total Bases / RBIs / Runs / H+R+RBI are where a too-tight or mis-shaped Poisson FABRICATES
fake edges -- the trap, not the pocket (proof-standards.md "too-tight distribution" + cut-list CUT 4).
**Detect:** in the per-stat backtest, watch for these stats showing LOW Brier but extreme implied EVs, or
ECE spiking with overconfident tails -- the signature of mis-specification, not skill.
**Proof:** require a COMPOUND model (hit-count x base-value, or per-event 1B/2B/3B/HR categorical) to
beat the single-Poisson on tail calibration OOS before any of these is bettable. Until then: model-view
only. Tier: HYPOTHESIS (negative expected).

## POCKET 5 -- Correlated same-game prop mispricing (P5, later)
**Thesis:** books price SGP legs independently; HR+TB and the H/R/RBI components are positively
correlated, so the joint is mispriced.
**Detect:** measure realized pairwise correlation of (HR,TB), (Hits,Runs), etc. on the backfilled
gamelogs; compare a copula/shared-latent joint p to the product-of-marginals the book implies.
**Proof:** joint calibration on the full stat-pair surface (retro-full-surface validation -- not just the
dominant pair); then SGP-level realized ROI. Tier: HYPOTHESIS; blocked on the marginal calibration + a
joint model that does not exist yet.

## POCKET 6 -- Prediction-market vs sportsbook divergence (P4)
**Thesis:** Kalshi MLB game markets and sportsbook ML can diverge (different crowds).
**Detect:** keyless Kalshi pull vs devigged book ML per game; flag persistent divergence.
**Proof:** which side is closer to realized? calibration of each vs outcome over a season. Tier:
HYPOTHESIS, unwired for MLB.

## Cross-cutting detection discipline
- Every pocket runs through the REAL leak-free gate (`scripts/platformkit/eval_gate/` +
  `props_eval_mlb`), never a parallel stub.
- Cold start: < ~60 settled outcomes -> INSUFFICIENT_DATA; the prop ratchet is at n=0/12 today.
- Single good stat/fold is a SELECTION ARTIFACT -- require >=2 independent corpora/folds + cluster-robust
  DM clustered by game before promoting (proof-standards.md).
