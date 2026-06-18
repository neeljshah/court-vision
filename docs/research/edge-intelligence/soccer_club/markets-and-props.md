# SOCCER-CLUB -- markets + prop ladder (what we price, what's soft, the gaps)
_The full club-soccer market surface, which lines are soft/lazy, what we price today vs gaps.
Grounded in domains/soccer/markets.py, scoreline_engine.py, prop_engine.py. ASCII._

## TEAM market surface (priced TODAY, coherent, EFFICIENT)
markets.full_surface(P) prices the WHOLE catalog off ONE Dixon-Coles scoreline matrix
(scoreline_engine.scoreline_matrix). All probabilities are algebraic read-offs of P, so
cross-market identities hold exactly (1X2 sums to 1; double-chance = its two legs; Asian-0 ==
DNB; totals monotone in line). What it emits (markets.py):
- 1X2 home/draw/away (one_x_two)
- Double chance 1X/12/X2 (double_chance); Draw-no-bet (draw_no_bet)
- BTTS yes/no (btts)
- Total goals O/U at 0.5/1.5/2.5/3.5/4.5, any half-line (totals)
- Team totals O/U home/away (team_totals)
- Asian handicap -1.5..+1.5 incl quarter-lines with correct push split (asian_handicap)
- European 3-way handicap at integer lines (european_handicap)
- Odd/even total (odd_even); Clean sheet home/away (clean_sheet)
- Winning margin buckets (winning_margin); Top-N correct scores (correct_scores)

SOFTNESS: NONE durable. These are the most liquid, most-modeled markets in all of sports;
Pinnacle/exchange closes integrate everything. odds.parquet gives us open AND close on totals
(16,322 matches) -> the close is the YARDSTICK we calibrate to, never beat (cut-list CUT 1).
Soft pockets that occasionally exist (lazy correct-score, exotic margin, lower-league E1) are
thin-volume lottery markets, not a durable program.

## PLAYER prop ladder (the BEATABLE surface -- where to build)
prop_engine.prop_distribution builds lam = per90 x E[min]/90 x opp_mult -> Poisson or NB count
-> p_over(line) + an alt-line ladder (prop_engine.py:99-161; half-integer lines never push,
prop_engine.py:78). The 10 canonical stats (player_rates.CANON_TO_COLS:35-46):

| Prop (canonical) | Distribution | Volume | Soft? | Prop verdict |
|---|---|---|---|---|
| Saves | NB count | high (GK) | DFS lazy | BUILD FIRST -- near-deterministic in shots faced; WC bss +0.337 |
| Shots (totalShots) | NB count | high | DFS lazy | BUILD -- highest-volume outfield count; rate stabilizes with club history |
| Shots On Target | NB count | med | DFS lazy | BUILD (joint w/ Shots) |
| Fouls (yellow+red proxy via foulsCommitted) | NB count | med | DFS lazy | BUILD -- per-player foul rate is stable |
| Fouls Drawn (foulsSuffered) | NB count | med | DFS lazy | BUILD -- dribbler archetype stable |
| Goals (totalGoals) | NB/Bernoulli | low | priced sharp | CUT as bet driver (CUT 4); model-view |
| Assists (goalAssists) | low | low | priced sharp | CUT (CUT 4) |
| Goal+Assist | low | low | priced sharp | CUT (CUT 4) |
| Offsides | low | low | DFS | CUT (CUT 4); near-noise |
| Cards (yellow+red) | Bernoulli-ish | low | DFS | CUT (CUT 4); single-match card is irreducible noise |

### Lines that are SOFT/LAZY (the pocket)
- PrizePicks/Underdog pick'em PROJECTIONS on high-volume outfield stats (Shots, SOT, Fouls) and
  GK Saves: set off a generic season projection, slow to incorporate confirmed-XI/minutes, and
  STRUCTURALLY cannot move much (fixed payout) -> the P1 lazy-pricing crack (edge-theory P1).
- DFS pick'em has NO two-way close -> CLV-vs-close is undefined; prove via P(over) calibration vs
  realized + realized ROI at the fixed payout + DFS-LINE MOVEMENT (edge-theory note on pick'em).
- Lower-league / non-top-5 props: thin bookmaker attention (P6) but ESPN box coverage thins too.

### Ladder mechanics we already price
prop_engine exposes an alt-line ladder; the board does a two-pass (Poisson to learn lam, then
re-distribute with NB r=lam/(phi-1), prop_edge.py:154-165) so the over-prob is dispersion-correct
at each line. half-integer lines never push (the DFS standard).

## What we PRICE today vs GAPS
PRICE TODAY:
- Full team surface (coherent, calibrated, efficient) for all 6 divisions.
- WC player props for 10 stats (tier-gated; only Saves proven).
GAPS (build queue):
1. Club per-player props: the engine is sport/league-blind, but it has NO club per-player rate
   data -- it would ride espn_club_priors (season aggregate) only. Need the club per-match series.
2. Richer stats: tackles/passes/interceptions/key-passes (higher-volume, more-stable, better prop
   candidates than rare Goals/Cards) are not in CANON_TO_COLS yet.
3. Correlated SGP / joint props (P5): Shots+SOT, player-shots + team-total-goals are priced as
   INDEPENDENT marginals today; the joint is a real correlation blindspot books misprice. Needs a
   copula or shared-latent shot-volume term (deep-dive bigger-bet #10), validated on the full
   stat-pair surface (retro full-surface validation lesson), not just the dominant pair.
4. Corners / cards TEAM props: match_stats has team corners (mean home 5.46) and cards (mean home
   yellow 1.84) for 25,834 matches -> a deep, never-modeled team-prop surface (over X.5 corners /
   cards). Currently UNPRICED. Candidate P1 pocket distinct from scoreline markets.

## Honest framing
Team surface = coherent + efficient (calibration/CLV-yardstick only). Player + team-count props
(corners/cards) = the soft surface to model. Nothing here is an edge until measured OOS; today
only WC Saves is calibration-proven and NOTHING club is measured at all.
