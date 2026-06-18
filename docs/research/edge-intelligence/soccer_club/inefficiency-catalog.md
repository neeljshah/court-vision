# SOCCER-CLUB -- inefficiency catalog (beatable pockets + detection + proof)
_Each entry: the pocket, WHY it cracks (edge-theory taxonomy), a DETECTION recipe (how to find
it in our data), and the PROOF method (proof-standards bar). Tags: HYPOTHESIS / CALIBRATION-PROVEN
/ CLV-PROVEN. Most are HYPOTHESIS -- club props are not yet measured at all. ASCII._

## Pocket 1 -- DFS Saves props (GK), deep club history [HYPOTHESIS, WC-analog CALIBRATION-PROVEN]
WHY IT CRACKS: P1 lazy DFS pricing. GK Saves is near-deterministic in shots-on-target faced;
DFS sets a generic projection and is slow to incorporate "this keeper faces a high-SOT opponent
tonight." The WC analog already MEASURED bss +0.3365 (n=662, prop_calibration.json) -- the
strongest skill in the entire prop stack.
DETECTION RECIPE: (1) ingest club per-player GK box (saves) via ESPN summary; (2) build the club
Saves rate via player_rates + team_defense Saves<-opponent shotsOnTarget multiplier
(team_defense.py:72-85); (3) flag lines where model p_over deviates from 0.5-implied DFS by a
margin AND the opponent SOT-for rate (from match_stats.parquet, 25,834 rows) is in the tail.
PROOF: props_eval.backtest_calibration on the CLUB Saves series, leak-free WF; require bss>=0.05
AND >=100 predictions across >=2 independent matchdays (proof-standards #4). Then forward
P(over)-calibration + DFS-line movement (pick'em has no two-way close).
CAVEAT: WC Saves bss is partly inflated because the .5-line is near-trivial for keepers
(deep-dive sec 5); the club proof must use realistic DFS lines (2.5/3.5), not the lam-nearest .5.

## Pocket 2 -- DFS Shots / SOT props, club rate depth [HYPOTHESIS]
WHY IT CRACKS: P1. Highest-volume outfield count; per-player shot rate is one of the most stable
in soccer, but DFS projections lag confirmed minutes/role. WC measured only marginal (Shots
+0.008, SOT +0.005) -- BECAUSE the WC had 1 match/player and the rate rode the club prior. Club
DEEP history is exactly the missing ingredient (deep-dive: rates "only start to exist once
players have 2+ matches").
DETECTION RECIPE: build per-player club Shots rate over multi-season ESPN box; detect lines where
(a) n_eff is high (player_rates n_eff>=5, no longer thin) and (b) model p_over diverges from the
DFS line; cross-check the opponent shots-allowed multiplier.
PROOF: club props_eval cache; compare bss to the WC marginal -- the HYPOTHESIS is that deep club
data lifts Shots from +0.008 to a proven >=0.05. Require >=2 matchday folds + seed/N stability.

## Pocket 3 -- TEAM corners / cards props [HYPOTHESIS, UNPRICED today]
WHY IT CRACKS: P1 + P6. match_stats.parquet has team corners (mean home 5.46) and cards (mean
home yellow 1.84) for ALL 25,834 matches -- a DEEP, never-modeled surface. Books/DFS price
corner/card totals lazily, especially in E1 (Championship, 6,072 matches, lower attention = P6).
DETECTION RECIPE: build a per-team corners-for / corners-against and cards rate (leak-free, like
asof_features), Poisson/NB the team total, price over X.5 corners / cards; detect divergence vs
soft posted totals. Referee is in match_stats -> a referee-cards fixed effect is a known real
signal (some refs card 2x more).
PROOF: WF calibration on the 25,834-match corpus (huge N -> can actually clear proof-standards
#4/#5 unlike the WC). Referee fixed-effect must be validated leak-free (ref's PRIOR matches only).
This is the pocket where club DEPTH most plausibly beats the thin-attention soft line.

## Pocket 4 -- Confirmed-XI / minutes freshness on props [HYPOTHESIS, the freshness lever]
WHY IT CRACKS: P1 lag + the same-day freshness gap. DFS prop lines are set off PROJECTED minutes;
when the starting XI is confirmed ~1h pre-kickoff, a benched/rotated star's prop is briefly
mispriced before the line adjusts (or, in pick'em, can never adjust).
DETECTION RECIPE: scrape confirmed XI near kickoff; recompute player_minutes.expected_minutes
with the lineup known (start_prob -> 0/1); flag props where the confirmed-minutes lam diverges
hard from the projected-minutes lam the line implies.
PROOF: this is an EXECUTION/freshness edge -- prove via forward realized ROI on confirmed-XI-
divergent props + DFS line movement after XI release. Cannot be backtested historically without
a stored XI-release timestamp; build the capture first.
NOTE: the deep-dive flags minute-projection as the biggest UNMEASURED live-board error; this
pocket is also the fix for that error.

## Pocket 5 -- Correlated SGP / joint props [HYPOTHESIS]
WHY IT CRACKS: P5 correlation blindspot. Books price Shots, SOT, and player-goals legs
independently; they are strongly positively correlated (a high-shot game lifts all three).
prop_engine prices them as independent marginals today (no joint).
DETECTION RECIPE: estimate the player-level Shots<->SOT and player-Shots<->team-goals correlation
from the club box; build a copula or shared-latent shot-volume term; compare the joint SGP price
to the product-of-marginals the book uses.
PROOF: validate on the FULL stat-pair surface, not just Shots+SOT (retro full-surface validation
lesson -- joint signals must hold across pairs, else it's selection). Calibration of the joint
over-prob vs realized co-occurrence.

## Pocket 6 -- Live in-game team repricing [HYPOTHESIS, unbuilt for club]
WHY IT CRACKS: P2 information lag -- the decisive combinable lever. After a goal/red-card, the
live 1X2/total lags the new state for seconds-to-minutes.
DETECTION RECIPE: re-feed scoreline_matrix with elapsed-time-scaled remaining lambdas + the
current score offset; reprice live 1X2/total; flag divergence vs the live book.
PROOF: requires a live-odds feed + clock; prove via live calibration (Brier of the in-play 1X2 vs
realized) and CLV vs the live close. No club live path exists yet -- biggest unbuilt ceiling.

## What is NOT a pocket (catalogued so we don't chase it)
- Team mainlines (1X2/O-U/AH/BTTS): EFFICIENT, CUT 1. odds.parquet close proves CLV ~ 0.
- Rare-event props (Goals/Assists/Cards/Offsides): CUT 4, near-irreducible single-match noise;
  WC measured negative skill. Model-view only.
- Momentum/form alignment as a bet driver: CUT 3 (NBA INT-81 momentum worse than random; form is
  a RATE input only).
- Isotonic/over-flexible recal on thin club data: CUT 5; WC isotonic already DEFERRED (overfit
  tell: in-sample Brier -0.0061 vs OOS +0.0039).
