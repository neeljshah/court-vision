"""domains.basketball_nba.elo_config — Elo + walk-forward constants for ratings.py.

NBA-calibrated values, kept in their own module so domains/basketball_nba/config.py
stays unchanged.  Consumed by domains/basketball_nba/ratings.py (+ the adapter).
"""
from __future__ import annotations

# K-factor: NBA carries ~3-4x more signal per game than MLB; K=20 gives
# meaningful per-game movement while staying stable over an 82-game season.
ELO_K: float = 20.0

# Prior mean Elo for an unseen franchise.
ELO_MEAN: float = 1500.0

# Home-court advantage in Elo points: NBA home win ~59-60% ~= logistic(HFA/400)
# = 0.595 -> HFA ~= 76 Elo pts (applied uniformly across the corpus).
ELO_HFA: float = 76.0

# Between-season regression toward ELO_MEAN: 0.25 retains 75% of earned rating
# (more persistent than MLB=0.33; NBA rosters turn over less year-to-year).
SEASON_REGRESS: float = 0.25
