"""Single source of truth the builder iterates over. Every attribute names
its real on-disk ingredients -- nothing here is mined fresh, it is all
composition of artifacts domains/basketball_nba/* and scripts/platformkit/*
already wrote.

SHARED SCHEMA (long format, one row per entity+window+attribute), written by
build_profiles.py to the 3 output parquets:
    entity_id (int64, or lineup_key str for lineup rows)
    entity_name        human label ('' where none exists, e.g. lineup rows)
    window              e.g. 'season_2025_26'
    attribute           snake_case, matches an ATTRIBUTES key (or key+col
                         suffix for the pass-through families below)
    raw_value            the real number -- GATES/FITS MUST ALWAYS READ THIS
    percentile          0-100 within the qualified population for that
                         attribute+window (floor already applied)
    rating_2k            25 + percentile*0.74 -- PRESENTATION ONLY, never
                         feed a gate/fit/claim with this column
    n                    the attribute's own sample size
    ingredients          compact json {ingredient_name: value} for THIS row
    status               VALIDATED_MECHANISM | VALIDATED_CLAIM | DESCRIPTIVE
    sources              semicolon-joined artifact paths (repo-relative)

STATUS MEANING:
    VALIDATED_MECHANISM -- built on a mechanism that survived leak-free
        gate-testing + cross-corpus replication (currently: stint continuity,
        domains/basketball_nba/prereg/nba_hypotheses.py's h7, replicated on
        2024-25 + (pending) 2023-24 -- see third_season_2023_24.py).
    VALIDATED_CLAIM -- the family already has a green validate_store verdict
        under a DIFFERENT claim_id (gravity, lineup synergy) -- this profile
        row is a re-presentation of that same verified number, not a new claim.
    DESCRIPTIVE -- a real, honestly-sourced composite/aggregate with no
        causal or gate-tested backing. The default for everything else.

WHERE INGREDIENTS DID NOT EXIST ON DISK (dropped, not faked):
    rim_pressure_def wanted (a) opp rim-attempt-share allowed on/off-court
        per PLAYER and (b) rim eFG allowed on/off per PLAYER -- neither
        exists (concession_2025_26.parquet is TEAM-level only, no on/off
        split by player). (c) team DREB rate on-court is not cheaply
        derivable (no DREB column in stints_<season>.parquet, no OREB-chance
        denominator without an extra team-box join). All three DROPPED;
        replaced with the closest real on-disk substitute -- see the
        attribute's `formula` string below.
    shot_zone_profile wanted rim/mid/three per-36 -- no per-player shot-chart
        zone parquet exists (atlas_player_shot_profile.parquet's own `zones`
        field literally says "DEFER: no per-zone shot-chart parquet in
        repo"). Only the three-point vs two-point (rim+mid combined) split
        is composable from player_boxscores.parquet's fg3m/fg3a/fgm/fga/min.
    pace_proxy wanted true possessions/48 -- pace_possession.parquet exists
        but is keyed by tricode string with no on-disk tricode<->team_id
        bridge in this lane's scope; team_system/composition/shot_diet_
        2025_26.parquet's total_fga/game (a shot-volume tempo proxy, NOT a
        possession count) is used instead and labelled as such.
    transition_rate wanted a clean numeric column -- atlas_team_transition_
        defense.parquet's transition_freq is itself a JSON-string column
        whose own _note caveats it as ~50% opponent-mixed (both teams'
        transition possessions, opponent-only split "deferred pending
        per-player team membership join") -- used as-is, caveat carried in
        ingredients.

FLOORS: declared per attribute below (min_sample). Entities below floor are
OMITTED from the output, never zero-filled.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# PLAYER attributes
# ---------------------------------------------------------------------------
PLAYER_ATTRIBUTES: dict[str, dict] = {
    "gravity": {
        "description": "Teammate eFG lift while this player is on-court vs off.",
        "entity": "player",
        "ingredients": [
            {"name": "teammate_efg_on", "source": "team_system/lineups/gravity_proxy_<season>.parquet"},
            {"name": "teammate_efg_off", "source": "team_system/lineups/gravity_proxy_<season>.parquet"},
        ],
        "formula": "teammate_efg_on - teammate_efg_off",
        "status": "VALIDATED_CLAIM",
        "floor": {"min_on": 300.0},
        "weight_ledger_family": "nba_gravity_proxy_claims",
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "usage_absorption": {
        "description": "Shot-share this player absorbs, averaged across every high-usage teammate whose minutes he shares, when that teammate sits.",
        "entity": "player",
        "ingredients": [
            {"name": "share_delta", "source": "team_system/interactions/usage_redistribution_<season>.parquet"},
            {"name": "teammate_fga_joint", "source": "team_system/interactions/usage_redistribution_<season>.parquet"},
        ],
        "formula": "mean(share_delta) grouped by teammate_id",
        "status": "DESCRIPTIVE",
        "floor": {"teammate_fga_joint_sum": 100.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "creation": {
        "description": "eFG lift this player generates for teammates he assists, averaged across every scorer he feeds.",
        "entity": "player",
        "ingredients": [
            {"name": "efg_delta", "source": "team_system/interactions/assist_network_2025_26.parquet"},
            {"name": "n_assists", "source": "team_system/interactions/assist_network_2025_26.parquet"},
        ],
        "formula": "mean(efg_delta) grouped by assister_id",
        "status": "DESCRIPTIVE",
        "floor": {"n_assists_sum": 20.0},
        "weight_ledger_family": None,
        "seasons": ["2025_26"],  # assist_network only built for 2025-26
        "verifiable_by_design": True,
    },
    "spacing_contribution": {
        "description": "Mean shot-spacing of lineups this player is IN minus lineups (same team) he is NOT in.",
        "entity": "player",
        "ingredients": [
            {"name": "spacing_mean_dist", "source": "team_system/lineups/lineup_spacing_<season>.parquet"},
            {"name": "n_shots", "source": "team_system/lineups/lineup_spacing_<season>.parquet"},
            {"name": "lineup_key membership", "source": "same file -- comma-split, player_id in split"},
        ],
        "formula": "weighted_mean(spacing_mean_dist | player in lineup, w=n_shots) - weighted_mean(spacing_mean_dist | player not in lineup, w=n_shots)",
        "status": "DESCRIPTIVE",
        "floor": {"n_shots_with": 200.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,  # membership-string parse, no simple column formula
    },
    "rim_pressure_def": {
        "description": (
            "Player's own on/off defensive-points-allowed swing (pts_against per48 OFF-court minus "
            "ON-court -- positive means the team concedes fewer points with him on the floor), carrying "
            "the team's rim-defense context (rim_efg_allowed, rim_share_allowed) as ingredients ONLY, "
            "not blended into raw_value (team-level, not individualized -- see registry docstring)."
        ),
        "entity": "player",
        "ingredients": [
            {"name": "pts_against_per48_on", "source": "team_system/lineups/stints_<season>.parquet (lineup_key membership)"},
            {"name": "pts_against_per48_off", "source": "team_system/lineups/stints_<season>.parquet (lineup_key membership)"},
            {"name": "team_rim_efg_allowed (context only)", "source": "team_system/composition/concession_2025_26.parquet"},
            {"name": "team_rim_share_allowed (context only)", "source": "team_system/composition/concession_2025_26.parquet"},
        ],
        "formula": "pts_against_per48_off - pts_against_per48_on",
        "status": "DESCRIPTIVE",
        "floor": {"min_on": 300.0, "min_off": 300.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,
    },
    "shot_zone_three_rate_per36": {
        "description": "Three-point attempts per 36 minutes.",
        "entity": "player",
        "ingredients": [{"name": "fg3a", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                        {"name": "min", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
        "formula": "sum(fg3a) / sum(min) * 36",
        "status": "DESCRIPTIVE",
        "floor": {"min_sum": 200.0},
        "weight_ledger_family": None,
        "seasons": ["2024_25", "2025_26"],  # player_boxscores has no 2023-24 rows
        "verifiable_by_design": True,
    },
    "shot_zone_three_efg": {
        "description": "eFG% on three-point attempts alone (1.5*fg3m/fg3a).",
        "entity": "player",
        "ingredients": [{"name": "fg3m", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                        {"name": "fg3a", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
        "formula": "sum(fg3m) * 1.5 / sum(fg3a)",
        "status": "DESCRIPTIVE",
        "floor": {"min_sum": 200.0},
        "weight_ledger_family": None,
        "seasons": ["2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "shot_zone_two_rate_per36": {
        "description": "Two-point attempts (rim+mid combined -- no zone split on disk) per 36 minutes.",
        "entity": "player",
        "ingredients": [{"name": "fga", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                        {"name": "fg3a", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                        {"name": "min", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
        "formula": "(sum(fga) - sum(fg3a)) / sum(min) * 36",
        "status": "DESCRIPTIVE",
        "floor": {"min_sum": 200.0},
        "weight_ledger_family": None,
        "seasons": ["2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "shot_zone_two_fg_pct": {
        "description": "FG% on two-point attempts alone (rim+mid combined).",
        "entity": "player",
        "ingredients": [{"name": "fgm", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                        {"name": "fg3m", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                        {"name": "fga", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                        {"name": "fg3a", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
        "formula": "(sum(fgm) - sum(fg3m)) / (sum(fga) - sum(fg3a))",
        "status": "DESCRIPTIVE",
        "floor": {"min_sum": 200.0},
        "weight_ledger_family": None,
        "seasons": ["2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "stint_stamina_avg_s": {
        "description": "Mean stint length (seconds on-court before a substitution) this player plays.",
        "entity": "player",
        "ingredients": [{"name": "elapsed_s", "source": "team_system/lineups/stints_<season>.parquet (lineup_key membership)"}],
        "formula": "mean(elapsed_s | player in lineup_key)",
        "status": "DESCRIPTIVE",
        "floor": {"n_stints": 20.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,
    },
    "stint_minutes_load": {
        "description": "Total on-court minutes across all stints this season.",
        "entity": "player",
        "ingredients": [{"name": "elapsed_s", "source": "team_system/lineups/stints_<season>.parquet (lineup_key membership)"}],
        "formula": "sum(elapsed_s | player in lineup_key) / 60",
        "status": "DESCRIPTIVE",
        "floor": {"n_stints": 20.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,
    },
}

# ---------------------------------------------------------------------------
# TEAM attributes -- shot_diet_* / concession_* pass-through columns are one
# entry each below (16 of the 19 team attributes), generated in
# team_attributes.py from these two column lists rather than hand-duplicated.
# ---------------------------------------------------------------------------
SHOT_DIET_COLS = [
    "rim_share", "paint_share", "mid_share", "corner3_share", "above_break_3_share", "assisted_share",
]
CONCESSION_COLS = [
    "overall_efg_allowed", "rim_efg_allowed", "rim_share_allowed", "paint_efg_allowed",
    "mid_efg_allowed", "corner3_efg_allowed", "above_break_3_efg_allowed",
    "share_assisted_allowed", "share_fastbreak_allowed", "ft_rate_allowed",
]
# "_allowed"/"_efg_allowed" etc columns: LOWER is better defense; declared here
# once so build_profiles.py doesn't hand-flip percentile direction per column.
CONCESSION_LOWER_IS_BETTER = {c for c in CONCESSION_COLS if c != "share_assisted_allowed"}

TEAM_ATTRIBUTES: dict[str, dict] = {
    "shot_diet": {
        "description": "Team's own shot-mix shares by zone + assisted share (per-game mean, 2025-26 pbp corpus).",
        "entity": "team",
        "ingredients": [{"name": c, "source": "team_system/composition/shot_diet_2025_26.parquet"} for c in SHOT_DIET_COLS],
        "formula": "mean(<col>) grouped by team_id, per shot_diet column",
        "status": "DESCRIPTIVE",
        "floor": {"n_games": 10.0},
        "weight_ledger_family": None,
        "seasons": ["2025_26"],
        "verifiable_by_design": True,
    },
    "concession": {
        "description": "What the defense concedes, by zone (share/eFG allowed) + assisted/fastbreak/FT-rate allowed.",
        "entity": "team",
        "ingredients": [{"name": c, "source": "team_system/composition/concession_2025_26.parquet"} for c in CONCESSION_COLS],
        "formula": "<col> verbatim (already a team-season aggregate)",
        "status": "DESCRIPTIVE",
        "floor": {"n_shots_faced": 500.0},
        "weight_ledger_family": None,
        "seasons": ["2025_26"],
        "verifiable_by_design": True,
    },
    "transition_rate_allowed": {
        "description": "Mean total PBP transition possessions/game in this team's games (BOTH teams combined -- opponent-only split not on disk, see docstring).",
        "entity": "team",
        "ingredients": [{"name": "opp_transition_pg", "source": "atlas_team_transition_defense.parquet (JSON column)"}],
        "formula": "json.loads(transition_freq)['opp_transition_pg']",
        "status": "DESCRIPTIVE",
        "floor": {"n_games_pbp": 50.0},
        "weight_ledger_family": None,
        "seasons": ["2025_26"],
        "verifiable_by_design": False,  # source column is a JSON string, not a plain numeric column
    },
    "lineup_continuity_avg_stint_s": {
        "description": "Mean stint length (seconds a 5-man unit stays intact before a substitution) -- team-level expression of the h7 stint-continuity mechanism (replicated on 2024-25, pending 2023-24 -- third_season_2023_24.py).",
        "entity": "team",
        "ingredients": [{"name": "elapsed_s", "source": "team_system/lineups/stints_<season>.parquet"}],
        "formula": "mean(elapsed_s) grouped by team_id",
        "status": "VALIDATED_MECHANISM",
        "floor": {"n_games": 10.0},
        "weight_ledger_family": "nba_hypotheses_h7_continuity_dreb",
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "pace_proxy_fga_per_game": {
        "description": "Mean field-goal attempts/game -- a shot-VOLUME tempo proxy, NOT true possessions (pace_possession.parquet exists but has no on-disk tricode<->team_id bridge in this lane).",
        "entity": "team",
        "ingredients": [{"name": "total_fga", "source": "team_system/composition/shot_diet_2025_26.parquet"}],
        "formula": "mean(total_fga) grouped by team_id",
        "status": "DESCRIPTIVE",
        "floor": {"n_games": 10.0},
        "weight_ledger_family": None,
        "seasons": ["2025_26"],
        "verifiable_by_design": True,
    },
}

# ---------------------------------------------------------------------------
# LINEUP attributes -- floor >=100 min OR >=200s, declared per attribute.
# ---------------------------------------------------------------------------
LINEUP_ATTRIBUTES: dict[str, dict] = {
    "spacing": {
        "description": "Mean pairwise shot-location distance for this exact 5-man unit (spread-floor proxy).",
        "entity": "lineup",
        "ingredients": [{"name": "spacing_mean_dist", "source": "team_system/lineups/lineup_spacing_<season>.parquet"},
                        {"name": "n_shots", "source": "team_system/lineups/lineup_spacing_<season>.parquet"}],
        "formula": "spacing_mean_dist verbatim",
        "status": "DESCRIPTIVE",
        "floor": {"n_shots": 100.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "synergy_residual": {
        "description": "5-man unit's actual net rtg/48 minus its individual-talent-sum expectation.",
        "entity": "lineup",
        "ingredients": [{"name": "net_per48", "source": "team_system/interactions/lineup_synergy_<season>.parquet"},
                        {"name": "expected_net_per48", "source": "team_system/interactions/lineup_synergy_<season>.parquet"}],
        "formula": "net_per48 - expected_net_per48",
        "status": "VALIDATED_CLAIM",
        "floor": {"min": 100.0},
        "weight_ledger_family": "nba_lineup_synergy_claims",
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "continuity_s": {
        "description": "Total seconds this exact 5-man unit spent on court together, season cumulative.",
        "entity": "lineup",
        "ingredients": [{"name": "elapsed_s", "source": "team_system/lineups/stints_<season>.parquet"}],
        "formula": "sum(elapsed_s) grouped by lineup_key",
        "status": "DESCRIPTIVE",
        "floor": {"total_s": 200.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": True,
    },
    "matchup_net": {
        "description": "Net points per 300s of court-time (~5min-equivalent) this lineup outscores whichever opposing lineup it overlaps.",
        "entity": "lineup",
        "ingredients": [{"name": "pts_a/pts_b", "source": "team_system/lineups/lineup_matchups_<season>.parquet"},
                        {"name": "overlap_s", "source": "team_system/lineups/lineup_matchups_<season>.parquet"}],
        "formula": "sum(pts_for - pts_against) / sum(overlap_s) * 300",
        "status": "DESCRIPTIVE",
        "floor": {"overlap_s_sum": 200.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,  # two-pass sign-flip (lineup can be side A or B), not a bare column agg
    },
}

ATTRIBUTES: dict[str, dict] = {**PLAYER_ATTRIBUTES, **TEAM_ATTRIBUTES, **LINEUP_ATTRIBUTES}
