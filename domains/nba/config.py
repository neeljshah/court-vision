"""NBA sport-context configuration stub.

This module will hold ALL NBA literal values VERBATIM and assemble the
``NBA_SPORT_CONTEXT`` mapping consumed by the sport-agnostic kernel.
Planned content (to be filled by tasks P0-D-012 through P0-D-017):

- stat_registry       : canonical stat-name → dtype / unit / direction mapping
- clock               : period count, period length, OT length, shot-clock rules
- court               : dimensions, zone polygons, paint / arc / mid-range regions
- roster              : position taxonomy, min/max roster size, two-way limits
- game_state          : score, fouls, timeouts, bonus thresholds
- speed               : pace / possession-length distribution parameters
- pbp_event_map       : raw play-by-play event codes → normalised action tokens
- entity_tables       : team IDs, conference/division memberships (static per season)

No runtime NBA values are defined here yet.  No heavy imports (no nba_api,
no torch, no pandas).  Adding a new sport requires only a new
``domains/<sport>/config.py`` with the same shape.
"""
from __future__ import annotations

__all__: list = []
