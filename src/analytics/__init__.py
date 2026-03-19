"""Analytics modules for the NBA AI system.

Spatial computation modules (pure, no DB dependency):
  spatial_types          — canonical dataclass contracts
  spacing                — convex hull + avg inter-player distance
  player_defensive_pressure — per-player nearest defender + closing speed
  momentum_events        — possession-segment momentum snapshots
  off_ball_events        — cut / screen / drift detection
  pick_and_roll          — PnR event detection
  passing_network        — directed passing graph
  drive_analysis         — drive mechanics + blow-by probability
  space_control          — radial reach space control model
  defensive_scheme       — zone / man / hybrid classification
  shot_creation          — self / screen / drive / cut / transition
  rebound_positioning    — rebound probability per player
  game_flow              — momentum index + comeback probability
  micro_timing           — catch-to-action decision latency
  lineup_synergy         — 5-man lineup synergy snapshot
  play_recognition       — full play type detection (PnR variants, ISO, etc.)

DataFrame-based analytics (consume tracking_data.csv):
  defense_pressure       — team-level pressure score
  momentum               — per-frame rolling momentum score
  shot_quality           — shot quality score (0–1)
  betting_edge           — CLV / EV backtesting
"""
