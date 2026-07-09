"""domains.basketball_wnba.profiles.attribute_registry -- the ATTRIBUTES
catalog for the WNBA attribute engine: one entry per player/lineup attribute,
PURE METADATA (no data logic -- build_profiles.py's _BUILDERS dict is the
actual dispatch). Mirrors domains/mlb/profiles/attribute_registry.py's shape;
2026 season only (168 games, 4,697 boxscore rows), smaller/looser floors than
an NBA-scale engine.

STATUS values (per attribute, honest):
  VALIDATED_CLAIM -- this attribute's raw_value formula is ALSO independently
      verified (green, 0 mismatch) by data/cache/intel_claims/
      wnba_player_form_claims.jsonl or wnba_lineup_claims.jsonl via a
      genuinely DIFFERENT recompute path (their own aggregate-grammar /
      direct-column formula, not this module's tautological raw_value claim).
  DESCRIPTIVE -- a real, honestly-labeled metric with NO independent claims-
      store corroboration: recent_form's window-delta and matchup_net's /
      minutes_together's melted two-sided-lineup aggregates aren't expressible
      in either of those two stores' existing claim grammar.

FLOOR is a single int compared against each builder's own `n` column (task
spec: player >=300 min for on/off-derived, >=15 games for box-derived,
>=5 games for the last-10-window recent_form; lineup >=50 shots or >=300s).

RATING_2K: rating_2k = 25 + percentile*0.74, percentile in [0,100] -- same
formula/precedent as domains/mlb/profiles/attribute_registry.py.
"""
from __future__ import annotations

from typing import Any

RATING_FLOOR = 25.0
RATING_SPAN = 0.74  # rating_2k = RATING_FLOOR + percentile[0..100] * RATING_SPAN


def rating_2k(percentile: float) -> float:
    """percentile in [0, 100] -> a 25..99 presentation rating. Pure math, no
    clamping needed: percentile is itself already bounded [0, 100]."""
    return RATING_FLOOR + percentile * RATING_SPAN


_ON_OFF_SRC = ["data/cache/team_system/lineups/on_off_wnba_2026.parquet"]
_BOXSCORE_SRC = ["data/domains/wnba/player_boxscores.parquet"]

# weight_ledger_family ties an attribute back to the MOAT claim->prediction
# weighting ledger family it belongs to (short descriptive token, NOT the
# claims jsonl stem -- same convention as domains/mlb/profiles), or
# "descriptive" for attributes with no backing claim family yet.
ATTRIBUTES: dict[str, dict[str, Any]] = {
    # ---------------------------------------------------------------- player
    "on_court_impact": {
        "description": "Team net rating (pts_for - pts_against per 48 min) while this player is on the floor.",
        "entity": "player",
        "ingredients": ["net_rating_on_per48", "net_rating_off_per48", "min_on", "min_off"],
        "formula": "net_rating_on_per48",
        "status": "VALIDATED_CLAIM",
        "floor": 300,  # min_on minutes, task-declared on/off-derived floor
        "weight_ledger_family": "wnba_net_rating_on",
        "source_files": _ON_OFF_SRC,
    },
    "gravity": {
        "description": "Teammate eFG% lift while this player is on the floor vs off. Compound floor: "
                        "min_on>=300 pre-filtered inside the builder, then teammate_fga>=200 (tighter, "
                        "the registry floor below) -- same precedent as "
                        "scripts/platformkit/intel_validation/wnba_lineup_claims.py's gravity claim.",
        "entity": "player",
        "ingredients": ["teammate_efg_on", "teammate_efg_off", "teammate_fga_on", "teammate_fga_off"],
        "formula": "teammate_efg_on - teammate_efg_off",
        "status": "VALIDATED_CLAIM",
        "floor": 200,  # min(teammate_fga_on, teammate_fga_off)
        "weight_ledger_family": "wnba_gravity",
        "source_files": _ON_OFF_SRC,
    },
    "scoring_per36": {
        "description": "Points per 36 minutes, full 2026 season.",
        "entity": "player",
        "ingredients": ["pts_per36", "games"],
        "formula": "36*sum(pts)/sum(minutes)",
        "status": "VALIDATED_CLAIM",
        "floor": 15,  # games, task-declared box-derived floor
        "weight_ledger_family": "wnba_player_form",
        "source_files": _BOXSCORE_SRC,
    },
    "reb_per36": {
        "description": "Rebounds per 36 minutes, full 2026 season.",
        "entity": "player",
        "ingredients": ["reb_per36", "games"],
        "formula": "36*sum(reb)/sum(minutes)",
        "status": "VALIDATED_CLAIM",
        "floor": 15,
        "weight_ledger_family": "wnba_player_form",
        "source_files": _BOXSCORE_SRC,
    },
    "ast_per36": {
        "description": "Assists per 36 minutes, full 2026 season.",
        "entity": "player",
        "ingredients": ["ast_per36", "games"],
        "formula": "36*sum(ast)/sum(minutes)",
        "status": "VALIDATED_CLAIM",
        "floor": 15,
        "weight_ledger_family": "wnba_player_form",
        "source_files": _BOXSCORE_SRC,
    },
    "efg": {
        "description": "Effective FG% -- (fgm + 0.5*fg3m) / fga, full 2026 season.",
        "entity": "player",
        "ingredients": ["efg_pct", "games"],
        "formula": "(sum(fgm)+0.5*sum(fg3m))/sum(fga)",
        "status": "VALIDATED_CLAIM",
        "floor": 15,
        "weight_ledger_family": "wnba_player_form",
        "source_files": _BOXSCORE_SRC,
    },
    "usage_proxy_per36": {
        "description": "Usage-ingredient rate (fga+0.44*fta+tov) per 36 min -- FALLBACK, not true USG% "
                        "(true USG% needs a per-game team on-court join the shared claims grammar can't "
                        "express; same declared fallback as claims_player_form.py).",
        "entity": "player",
        "ingredients": ["usage_proxy_per36", "games"],
        "formula": "36*(sum(fga)+0.44*sum(fta)+sum(tov))/sum(minutes)",
        "status": "VALIDATED_CLAIM",
        "floor": 15,
        "weight_ledger_family": "wnba_player_form",
        "source_files": _BOXSCORE_SRC,
    },
    "recent_form": {
        "description": "Last-10-games pts_per36 minus full-season pts_per36 (positive = trending up). A "
                        "window DELTA -- not expressible in the shared claims grammar's single-window "
                        "aggregate (same documented limit as claims_player_form.py's window docstring), "
                        "so this stays DESCRIPTIVE regardless of the other two stores.",
        "entity": "player",
        "ingredients": ["last10_pts_per36", "full_pts_per36", "last10_games", "full_games"],
        "formula": "pts_per36(last_10) - pts_per36(full)",
        "status": "DESCRIPTIVE",
        "floor": 5,  # last-10-window games, task-declared floor
        "weight_ledger_family": "descriptive",
        "source_files": _BOXSCORE_SRC,
    },
    # ---------------------------------------------------------------- lineup
    "spacing": {
        "description": "Mean pairwise shot-location distance for this 5-man lineup.",
        "entity": "lineup",
        "ingredients": ["spacing_mean_dist", "n_shots"],
        "formula": "spacing_mean_dist",
        "status": "VALIDATED_CLAIM",
        "floor": 50,  # n_shots, task-declared lineup floor
        "weight_ledger_family": "wnba_spacing",
        "source_files": ["data/cache/team_system/lineups/lineup_spacing_wnba_2026.parquet"],
    },
    "matchup_net": {
        "description": "Net points per 48 min this lineup outscores opponents by, aggregated across "
                        "BOTH matchup sides (melted from the raw team_id_a/b, lineup_key_a/b, pts_a/b "
                        "rows -- no single-sided per-lineup net column exists in the source).",
        "entity": "lineup",
        "ingredients": ["pts_for", "pts_against", "overlap_s"],
        "formula": "(sum(pts_for)-sum(pts_against))/(sum(overlap_s)/60)*48",
        "status": "DESCRIPTIVE",
        "floor": 300,  # overlap_s seconds, task-declared lineup floor
        "weight_ledger_family": "descriptive",
        "source_files": ["data/cache/team_system/lineups/lineup_matchups_wnba_2026.parquet"],
    },
    "minutes_together": {
        "description": "Total minutes this exact 5-man lineup has shared the floor (stint elapsed-time sum).",
        "entity": "lineup",
        "ingredients": ["minutes_together", "n_games"],
        "formula": "sum(elapsed_s)/60",
        "status": "DESCRIPTIVE",
        "floor": 300,  # elapsed_s seconds
        "weight_ledger_family": "descriptive",
        "source_files": ["data/cache/team_system/lineups/stints_wnba_2026.parquet"],
    },
}

ENTITIES = ("player", "lineup")
STATUSES = ("VALIDATED_CLAIM", "DESCRIPTIVE")


def attributes_for(entity: str) -> list[str]:
    return [name for name, spec in ATTRIBUTES.items() if spec["entity"] == entity]
