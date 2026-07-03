"""domains.basketball_wnba.elo_config -- Elo + walk-forward constants for ratings.py.

WNBA-calibrated values, kept in their own module mirroring
domains/basketball_nba/elo_config.py so basketball_nba's config.py stays
unchanged. Consumed by domains/basketball_wnba/ratings.py (+ the adapter).

Fit method (walk-forward grid search on the REAL 768-game 2024-2026 ESPN corpus,
train-past-only at every step -- each game scored using ONLY strictly-prior
games, ratings updated AFTER scoring, so no peeking forward is possible): grid
K in {10,15,20,25,30} x HFA in {40,55,70,85,100} x SEASON_REGRESS in {0.25,0.35},
scored by mean walk-forward log-loss over all 768 games. Run 2026-07-03:
  argmin = K=30, HFA=40, SEASON_REGRESS=0.35 -> walk-forward logloss 0.6256
  baselines on the same corpus: coin-flip (p=0.5) logloss 0.6931,
  home-prior-only (constant p=0.5534, the corpus home-win rate) logloss 0.6874.
Elo walk-forward BEATS both baselines (0.6256 < 0.6874 < 0.6931) -- this is a
calibration-baseline result (see pregame_gate_verdict.json), NOT a market-edge
claim; no closing-line data exists for WNBA yet to compare against.
"""
from __future__ import annotations

# K-factor: grid-search argmin (see module docstring). WNBA's much shorter season
# (40-44 games/year 2024-2026) than NBA's 82 means each result carries more
# information about current team strength within a season -- a higher K=30 (vs
# NBA's 20) lets ratings move faster per game, consistent with the search result.
ELO_K: float = 30.0

# Prior mean Elo for an unseen franchise (same convention as NBA: 1500 anchor).
ELO_MEAN: float = 1500.0

# Home-court advantage in Elo points. Grid-search argmin on the 2024-2026 ESPN
# corpus (home_win rate ~55.3%) is HFA=40 -- lower than NBA's 76, consistent with
# a smaller measured home-court effect in this corpus.
ELO_HFA: float = 40.0

# Between-season regression toward ELO_MEAN. Grid-search argmin ties at 0.35
# (vs NBA's 0.25) -- consistent with WNBA's higher year-to-year roster turnover
# (shorter guaranteed contracts, smaller rosters) pulling ratings back toward the
# mean faster across an offseason.
SEASON_REGRESS: float = 0.35
