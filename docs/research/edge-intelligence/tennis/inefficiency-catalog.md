# TENNIS -- INEFFICIENCY CATALOG (beatable pockets + detection recipe + proof method)
_Grounded in the real proofs + parquets. Each pocket: where it is, HOW to detect it in-data, and the
PROOF method that would move it HYPOTHESIS -> CALIBRATION-PROVEN -> CLV-PROVEN. ASCII._

Markets are mostly efficient. These are the SPECIFIC cracks for tennis, ranked by realistic
beatability (the P-taxonomy from _framework/edge-theory.md). Pregame match-win is NOT here -- it is
EFFICIENT (see 00-edge-map: Elo 0.2177 vs Pinnacle 0.2028).

---

## POCKET T1 -- IN-GAME set-conditional repricing lag (P2)  [STRONGEST, CALIBRATION-PROVEN sharpness]
WHERE: match-win probability after each completed set. Tennis is the highest-variance-per-event team
sport we model -- a single set swings the match-win prob enormously (after set 1 the leader wins 80%
of the time: base rate 0.8019 in `ingame_accuracy`).
DETECTION recipe (in-data): reconstruct mid-match states from the score string in matches.parquet /
the set scores in espn_matches.parquet (s1..s5); for each "after set k" state, role = (set leader),
label = match outcome (winner==1, symmetric id-order). Score Brier(conditional repricer) vs
Brier(pregame Elo). Already wired: `proof_tennis/ingame_accuracy.py`.
MEASURED (leak-free, held-out year>2022): after set 1, n=8608, Brier pregame 0.21941 -> score-only
0.16235 -> COMBINED 0.1513 (beats both); ECE 0.04343 -> 0.00631 after a TRAIN/EVAL-split Platt recal.
After set 2 @ 1-1, n=2566, 0.254 -> 0.245 (marginal; 1-1 is near coin-flip).
TIER: CALIBRATION-PROVEN (sharper than the pregame prior). NOT a $-edge -- a live book also sees the
set score. PROOF to advance: forward CLV vs a live in-play tennis close (needs a live odds scraper;
none exists). Until then it is a forecaster-quality win, surfaced on the board, never bet-claimed.

## POCKET T2 -- Moneyline best-price line-shopping (P3)  [MEASURED price fact, execution edge]
WHERE: the spread between the sharpest book (Pinnacle) and the best-available price across books.
DETECTION recipe: on odds.parquet compute per-book overround (1/odds_w + 1/odds_l - 1) and the
fraction max_odds > pinnacle_odds. RESULT: overround Pinnacle 2.52%, max 0.33%; max beats Pinnacle on
72.2% of matches, median +1.59% better winner odds. For live: aggregate ESPN pickcenter + The Odds
API tennis_atp h2h via odds_shop.best_line.
TIER: MEASURED execution edge (a better NUMBER than the sharp book), NOT a predictive edge. Real arbs
are rare/limit-bound (cut-list CUT-6) -- shop the best price, don't architect around arb.
PROOF: this is its own proof (you literally take the better number). CLV is positive BY CONSTRUCTION
when you beat the eventual close. Surface it; do not over-claim size.

## POCKET T3 -- Soft-book ACES O/U prop (P1)  [HIGHEST upside, BLOCKED on a scraper]
WHERE: PrizePicks/Underdog ace lines, posted lazily off a flat per-player number that ignores
opponent return strength and surface ace-rate.
DETECTION recipe (in-data, BUILDABLE today): from match_stats.parquet build a leak-free as-of ace
RATE per player (aces / svpt, overall + per surface; mirror asof_hold.py's snapshot-before-update).
Model match aces ~ NegBinom(mean = asof_ace_rate * expected_serve_points, dispersion phi). Price
P(over line). Detect the pocket = where the model P(over) diverges materially from the implied line.
TIER: HYPOTHESIS (no ace model, no ace line scraped). PROOF method: (1) per-stat leak-free
walk-forward BSS of P(over) vs realized aces on match_stats (calibration-proven if BSS>0, n>=100
independent matches), then (2) once a scraper exists, forward P(over)-calibration + realized ROI at
the fixed pick'em payout (CLV-vs-close undefined for pick'em -- prove via realized + line MOVEMENT).
GUARD: aces are a count stat -- watch the too-tight-Poisson trap (NB + dispersion, FLAG |EV|>0.5),
exactly the soccer-prop discipline in deep-dive 03/05.

## POCKET T4 -- Total GAMES / SETS O/U on LOW-ATTENTION events (P1 + P6)  [BLOCKED]
WHERE: ATP-250 / Challenger / WTA-lower-tier games & sets totals, where book attention is thin.
DETECTION recipe: tag each event by tourney_level (matches.parquet has tourney_level/tourney_name);
restrict the candidate set to lower tiers; price games/sets O/U with markets.price_all; flag rows
where model and (future scraped) line diverge. The straight_sets base rate 0.594 and n_breaks mean
3.73 (postmortem) anchor the games distribution.
TIER: HYPOTHESIS. PROOF: leak-free per-tier calibration of the games/sets price vs realized totals
(postmortem.parquet has realized n_breaks / straight_sets), THEN vs a scraped line. Likely a weaker
pocket than aces; gate hard, expect MATCH on top-tier events.

## POCKET T5 -- WTA softer-close hypothesis (P6)  [UNTESTABLE today]
WHERE: WTA match-win closes (lower attention than ATP) may be softer than ATP's near-perfect close.
DETECTION recipe: need a wta_odds.parquet (does not exist). Once built, run the SAME
beat_the_close_ml test on WTA: WTA Elo Brier vs devigged WTA close.
TIER: HYPOTHESIS, currently UNTESTABLE. Note the headwind: `wta_recal` shows WTA calibration is
data-limited (ECE 0.0546 HONEST FAIL) and the optimal surface blend is 0.0 -- our WTA model itself is
weaker, so even if the WTA close is softer we may not have the model edge to exploit it.

---

## NON-pockets (catalogued so we STOP looking)
- Pregame ATP match-win: EFFICIENT (proof above). The 0.0149 Brier gap is Pinnacle's freshness/news
  edge, structurally invisible to us. CUT.
- Set-streak / momentum bets: cut-list CUT-3 (momentum z_vs_null negative system-wide). Do not build.
- Tie-break / within-set markets: no per-point model -> unpriceable, not a pocket until that model
  exists AND a scraper proves softness.
- Two-book arbitrage as income: cut-list CUT-6. Detect-and-flag only.

## Detection-tooling summary (what exists vs what to build)
- EXISTS: ingame_accuracy.py (T1), odds.parquet book columns (T2), match_stats ace/df/svpt (T3
  ingredients), tourney_level tag (T4), wta_recal (T5 model side).
- TO BUILD: an as-of ace-rate builder (mirror asof_hold.py) for T3; tennis prop scraper for T3/T4
  lines; wta_odds ingest for T5; a live tennis odds channel for T1 CLV.
