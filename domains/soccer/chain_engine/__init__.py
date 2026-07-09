"""domains.soccer.chain_engine -- POSSESSION-CHAIN atomic-unit engine for soccer,
mirroring domains.basketball_nba.sim2 (possession) / domains.mlb.pitch_engine
(pitch) / domains.tennis.point_engine (point): empirical state-cell shot-
frequency model + backoff -> MC chain (possession -> shot -> goal -> match) ->
PIT/CRPS distributional validation, walk-forward, edge_claimed:false.
"""
