"""Prediction-engine ensemble — the signal -> model -> engine -> ONE hierarchy.

ARCHITECTURE (what flows into what):
  THOUSANDS of SIGNALS   (87 attrs x 927 players ~= 80k, + per-min rates, roles, effect spine [rest/
                          def-tier/pace/home-road per player], team four-factors x 30, defense forcing
                          rates, PBP knowledge, recency) -- the raw measured inputs.
        |  v
  HUNDREDS of MODELS     (each per-entity predictor: ~927 player-rating models, 30 team-rating models,
                          per-team factor models [eFG/TOV/OREB/FT], per-matchup facet-edge models). A
                          model maps a SUBSET of signals to a component prediction.
        |  v
  several ENGINES        (each fuses many models into a game prediction by a DIFFERENT methodology, so
                          their views are decorrelated): possession-MC, clock/trajectory, player-impact,
                          four-factors, power-ratings, team-score (NB), attribute-matchup.
        |  v
  ONE fused PREDICTION   (predict_ensemble.py inverse-variance/reliability-weights the engines into a
                          single calibrated win-prob/score, with engine disagreement = the uncertainty).

COMMON INTERFACE every engine module must expose:

    def predict(home_tri="NYK", away_tri="SAS", context=None) -> dict:
        '''context keys (optional): home_b2b, away_b2b, neutral_site, playoffs(bool).
        Returns:
          {
            "engine": "<name>",
            "win_prob_home": float,   # P(home wins) 0..1
            "margin_home": float,     # expected home_pts - away_pts (+ favors home)
            "total": float,           # expected combined points
            "home_pts": float, "away_pts": float,
            "margin_sd": float,       # SD of the margin distribution (drives ensemble uncertainty)
            "n_models": int,          # how many sub-models this engine fused (the hundreds layer)
            "n_signals": int,         # approx raw signals consumed (the thousands layer)
            "notes": str,             # 1-line read of what the engine saw
          }
        '''

Leak-free: a single forward prediction may use the full-season snapshot. Data (data/cache/team_system/):
league_team_game.parquet (30 teams reg season: pts/opp_pts/poss/opp_poss/tov/opp_tov/fga/fta/oreb/dreb/win),
team_defense_league.parquet (tov_force/ft_force/oreb_strength), player_ratings.parquet ('raw'=OVERALL +
SCORING/SHOOTING/PLAYMAKING/CREATION/FINISHING/REBOUNDING/INTERIOR_D/PERIMETER_D, mpg, archetype, 927),
attribute_vault.parquet (87 attrs x 927), recency_rates.parquet (mpg_rec), team_game.parquet (NYK/SAS q1-q4).
Home-court: no is_home in league data -> league home edge ~ +2.7 pts unless context['neutral_site'].
"""
