"""domains.wnba -- WNBA descriptive-depth-widening lane (wnba-atlas).

New, additive package: does NOT touch domains/basketball_wnba (the existing
sport adapter with its own atlas_extract_player.py/atlas_extract_team.py
builders + ingame/pregame gate machinery). This package only WIDENS the
descriptive layer by deriving NEW standalone ranking dimensions from the
atlas parquets basketball_wnba already materialized to data/cache/ -- see
atlas_extract.py's module docstring for the full rationale.
"""
