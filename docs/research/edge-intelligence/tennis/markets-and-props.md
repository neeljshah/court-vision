# TENNIS -- MARKETS AND PROPS (full surface; what we price vs gaps; which lines are soft)
_Grounded in domains/tennis/markets.py (price_all), match_engine_holds.py, repricer.py, and the
data parquets. ASCII. Coherent surface from ONE finished-match matrix; no fabricated prices._

## What we already PRICE (coherent, from the existing engine -- markets.py:price_all)
All read off the SAME n_sims finished-match matrix (`_sim_matches`), so they are internally
coherent: set scores sum to 1; P(2 sets)==P(straight sets); set-hcap -1.5 == straight-sets; games
O/U monotone in line. Holds (ph1,ph2) are bisected to the calibrated Elo match-win and shaped by the
as-of hold prior (predictor.py:_hold_levels).

| Market | How priced | Coherence anchor |
|---|---|---|
| Match winner (moneyline) | P(sets_p1 > sets_p2) | == predict()'s p1_match_win up to MC noise |
| Total GAMES O/U (any line) | empirical tail + smooth normal fallback (markets._games_ou / _games_ou_normal) | tg_mean/sigma from the matrix |
| Total SETS O/U 2.5 (bo3) | 1 - P(straight sets); base straight_sets 0.594 (postmortem) | == ss_p1 + ss_p2 |
| Set handicap +/-1.5 | jd.prob_spread on sets | -1.5 == straight-sets win |
| Correct set score / set betting | (sets_p1,sets_p2) distribution (2-0,2-1,0-2,1-2) | sums to 1 |
| Game handicap (match game spread) | per-side game tallies via `_per_side_games` resim | coherent with same holds |
| Per-set / first-set winner | per-set prob IMPLIED by match-win (i.i.d.-set APPROXIMATION) | disclosed approximation |

These are CALIBRATED MODEL PRICES (decision-support), NOT proven edges -- no scraped line exists to
score any of them against a close (see data-sources.md gap #1).

## What we CANNOT price honestly (markets.POINT_MODEL_GAPS -- do NOT fake)
The match engine resolves a 6-6 set as a 50/50 coin and stores only per-match game TOTALS, not the
per-set game path. So these need a per-point serve model we do not have:
- tie-break YES/NO (P(any set reaches 6-6))
- total games WITHIN a named set (e.g. set-1 over 9.5)
- exact correct set score BY GAMES (6-4, 7-5, 7-6)
- game handicap WITHIN a single set
Honestly listed as gaps in code; never priced. A per-point serve model (deuce/ad chain) would unlock
all four -- a medium build, only worth it if a scraper proves these lines are scrapeable + soft.

## The prop ladder -- which lines are SOFT/LAZY (the P1 pocket, all BLOCKED on a scraper)
Soft books (PrizePicks / Underdog) post tennis props that are notoriously lazily priced:
- **ACES O/U (player):** the highest-value candidate. match_stats has p1_ace (mean 4.61) + svpt +
  1stIn + SvGms -> a per-player surface-adjusted ace-RATE model is buildable (aces ~ NegBinom on
  serve points faced * surface ace-rate). Books often post a flat ace line that ignores opponent
  return depth and surface. HYPOTHESIS soft. NO line scraped, NO ace model wired.
- **Total GAMES O/U (match):** soft books post a single games line; our engine prices it coherently.
  Candidate, but games totals are reasonably efficient on top-tier matches; softness more likely on
  ATP-250 / Challenger / WTA-lower tiers (low attention => P6).
- **Total SETS / set betting / first-set winner:** moderately soft on lower-tier events.
- **Double faults / 1st-serve-% / break-points:** ingredients in match_stats; lazier still, but
  noisier targets -> likely the rare-event-negative-skill trap (cut-list CUT-4 analog: demote until
  a per-stat leak-free BSS proves otherwise).

## Two-way vs pick'em (the honest pricing distinction, per deep-dive 03)
- PrizePicks tennis = pick'em (no two-sided price) -> edge_basis = `model_view` (|p-0.5|), never a
  priced EV. CLV-vs-close is undefined; prove via P(over) calibration + realized ROI at fixed payout.
- Underdog tennis CAN carry true two-sided decimal odds (`payout_type="sportsbook"`) -> devig + EV
  both sides (edge_basis = `ev_vs_priced`). This is the channel where real CLV could accrue.

## Moneyline line-shopping surface (the only currently-actionable EXECUTION market)
odds.parquet already holds psw/psl (Pinnacle), b365w/l, maxw/l (best-of-N), avgw/l. Overrounds
(n~25.7k): Pinnacle 2.52%, Bet365 5.70%, avg 5.55%, **max 0.33%**. Taking the `max` price beats
Pinnacle on 72.2% of matches by a median +1.59%. This is a model-free best-price surface to expose
on the board NOW (no scraper needed for the historical view; a live multi-book feed needed for live).

## In-game market surface (SET-level only)
repricer.py reprices match-win after each completed set via the analytic race-to-N conditional
(+ a bounded 0.04 games-lean). It does NOT emit live games/sets/props markets -- only match-win.
No game/point live engine exists. In-game props (conditioned on realized serve stats) are the
higher-upside frontier per deep-dive 11 sec 7, but DATA-blocked (no live point feed).

## Summary: priced vs gap vs blocked
- PRICED coherently, calibration-only: match-win, games O/U, sets O/U, set hcap, set score, game
  hcap, first-set winner.
- GAP (need per-point model): tie-break Y/N, within-set games, exact game score, in-set game hcap.
- BLOCKED on a scraper (the real edge prize): ACES O/U, all prop lines, WTA odds, live in-play odds.
