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
    rim_pressure_def originally wanted (a) opp rim-attempt-share allowed
        on/off-court per PLAYER and (b) rim eFG allowed on/off per PLAYER --
        neither existed (concession_2025_26.parquet was TEAM-level only).
        Both now exist: lineups/zone_onoff.py builds per-(player,team,season)
        defensive on/off zone splits from stints + PBP shot x/y, and the
        composite below folds them in. (c) team DREB rate on-court is STILL
        not cheaply derivable (no DREB column in stints_<season>.parquet, no
        OREB-chance denominator without an extra team-box join) -- dropped.
        The composite is still DESCRIPTIVE, not VALIDATED_MECHANISM/CLAIM:
        having real ingredients doesn't mean the composite predicts anything
        yet -- that's the weight gate's job, not this builder's.
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

from domains.basketball_nba.composition.zone_geometry import ZONES

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
            "Composite defensive rim-deterrence score: this player's own on/off swing in opponent "
            "rim-attempt-share allowed, opponent rim eFG allowed, and team points-against per48 -- each "
            "swing z-scored within the qualified population and summed, so a HIGHER score means more "
            "rim deterrence regardless of each swing's raw scale."
        ),
        "entity": "player",
        "ingredients": [
            {"name": "rim_share_allowed_on", "source": "team_system/lineups/zone_onoff_<season>.parquet"},
            {"name": "rim_share_allowed_off", "source": "team_system/lineups/zone_onoff_<season>.parquet"},
            {"name": "rim_efg_allowed_on", "source": "team_system/lineups/zone_onoff_<season>.parquet"},
            {"name": "rim_efg_allowed_off", "source": "team_system/lineups/zone_onoff_<season>.parquet"},
            {"name": "pts_against_per48_on", "source": "team_system/lineups/stints_<season>.parquet (lineup_key membership)"},
            {"name": "pts_against_per48_off", "source": "team_system/lineups/stints_<season>.parquet (lineup_key membership)"},
            {"name": "team_rim_efg_allowed (context only)", "source": "team_system/composition/concession_2025_26.parquet"},
            {"name": "team_rim_share_allowed (context only)", "source": "team_system/composition/concession_2025_26.parquet"},
        ],
        "formula": (
            "zscore(rim_share_allowed_off - rim_share_allowed_on) "
            "+ zscore(rim_efg_allowed_off - rim_efg_allowed_on) "
            "+ zscore(pts_against_per48_off - pts_against_per48_on), "
            "z-scored within the qualified (>=750 min_on AND min_off) population per window"
        ),
        "status": "DESCRIPTIVE",
        "floor": {"min_on": 750.0, "min_off": 750.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,  # z-score composite of 3 swings, not a bare column/groupby formula
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
# PLAYER offense zone/context/clutch attributes -- 24 entries generated from
# composition/player_offense_events.py's per-(game,player) wide table (one
# PBP pass per season, already zone/transition/late-clock/clutch resolved).
# Programmatic (not hand-duplicated 24x) because the 15 zone entries and 6
# play-context entries are each the SAME shape across zones/buckets -- see
# player_offense_zones.py for the actual compute.
# ---------------------------------------------------------------------------
_OFFENSE_SEASONS = ["2023_24", "2024_25", "2025_26"]
_OFFENSE_SRC = "team_system/composition/player_offense_events_<season>.parquet"
_THREE_ZONES = {"corner3", "above_break_3"}


def _zone_offense_entries() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for z in ZONES:
        mult = "1.5" if z in _THREE_ZONES else "1.0"
        entries[f"zone_attempt_share_{z}"] = {
            "description": f"Share of this player's own season FGA taken from the {z} zone (x/y geometry classifier, 96.7% agreement -- zone_geometry.py).",
            "entity": "player",
            "ingredients": [{"name": f"{z}_fga", "source": _OFFENSE_SRC}, {"name": "total_fga", "source": _OFFENSE_SRC}],
            "formula": f"sum({z}_fga) / sum(total_fga)",
            "status": "DESCRIPTIVE",
            "floor": {f"{z}_fga": 25.0},
            "weight_ledger_family": None,
            "seasons": _OFFENSE_SEASONS,
            "verifiable_by_design": True,
        }
        entries[f"zone_efg_{z}"] = {
            "description": f"eFG% on this player's own {z}-zone attempts.",
            "entity": "player",
            "ingredients": [{"name": f"{z}_fgm", "source": _OFFENSE_SRC}, {"name": f"{z}_fga", "source": _OFFENSE_SRC}],
            "formula": f"(sum({z}_fgm) * {mult}) / sum({z}_fga)",
            "status": "DESCRIPTIVE",
            "floor": {f"{z}_fga": 25.0},
            "weight_ledger_family": None,
            "seasons": _OFFENSE_SEASONS,
            "verifiable_by_design": True,
        }
        entries[f"zone_assisted_share_{z}"] = {
            "description": f"Share of this player's own {z}-zone makes that were assisted (assistPersonId OR 'assist' in description text -- concession_profiles._is_assisted).",
            "entity": "player",
            "ingredients": [{"name": f"{z}_assisted", "source": _OFFENSE_SRC}, {"name": f"{z}_fgm", "source": _OFFENSE_SRC}],
            "formula": f"sum({z}_assisted) / sum({z}_fgm)",
            "status": "DESCRIPTIVE",
            "floor": {f"{z}_fga": 25.0},
            "weight_ledger_family": None,
            "seasons": _OFFENSE_SEASONS,
            "verifiable_by_design": True,
        }
    return entries


def _play_context_entries() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    specs = [
        ("transition", "shots taken within 6s of this player's own team gaining possession (transition_flag.py's window)"),
        ("halfcourt", "shots NOT taken in transition (the complement of transition_flag.py's window)"),
        ("late_clock", "shots taken with <=7s left on shot_clock_proxy.py's derived shot-clock proxy"),
    ]
    for prefix, desc in specs:
        entries[f"{prefix}_efg"] = {
            "description": f"eFG% on {desc}.",
            "entity": "player",
            "ingredients": [
                {"name": f"{prefix}_fgm", "source": _OFFENSE_SRC}, {"name": f"{prefix}_fg3m", "source": _OFFENSE_SRC},
                {"name": f"{prefix}_fga", "source": _OFFENSE_SRC},
            ],
            "formula": f"(sum({prefix}_fgm) + 0.5 * sum({prefix}_fg3m)) / sum({prefix}_fga)",
            "status": "DESCRIPTIVE",
            "floor": {f"{prefix}_fga": 25.0},
            "weight_ledger_family": None,
            "seasons": _OFFENSE_SEASONS,
            "verifiable_by_design": True,
        }
        entries[f"{prefix}_attempt_share"] = {
            "description": f"Share of this player's own season FGA that were {desc}.",
            "entity": "player",
            "ingredients": [{"name": f"{prefix}_fga", "source": _OFFENSE_SRC}, {"name": "total_fga", "source": _OFFENSE_SRC}],
            "formula": f"sum({prefix}_fga) / sum(total_fga)",
            "status": "DESCRIPTIVE",
            "floor": {f"{prefix}_fga": 25.0},
            "weight_ledger_family": None,
            "seasons": _OFFENSE_SEASONS,
            "verifiable_by_design": True,
        }
    return entries


_CLUTCH_ENTRIES: dict[str, dict] = {
    "clutch_efg": {
        "description": "eFG% in clutch time (Q4/OT, <=5min remaining, <=10pt margin).",
        "entity": "player",
        "ingredients": [
            {"name": "clutch_fgm", "source": _OFFENSE_SRC}, {"name": "clutch_fg3m", "source": _OFFENSE_SRC},
            {"name": "clutch_fga", "source": _OFFENSE_SRC},
        ],
        "formula": "(sum(clutch_fgm) + 0.5 * sum(clutch_fg3m)) / sum(clutch_fga)",
        "status": "DESCRIPTIVE",
        "floor": {"clutch_fga": 30.0},
        "weight_ledger_family": None,
        "seasons": _OFFENSE_SEASONS,
        "verifiable_by_design": True,
    },
    "clutch_ft_rate": {
        "description": "Free-throw attempts per field-goal attempt in clutch time (FTA/FGA, not FTA/36 -- see player_offense_zones.py docstring for why).",
        "entity": "player",
        "ingredients": [{"name": "clutch_fta", "source": _OFFENSE_SRC}, {"name": "clutch_fga", "source": _OFFENSE_SRC}],
        "formula": "sum(clutch_fta) / sum(clutch_fga)",
        "status": "DESCRIPTIVE",
        "floor": {"clutch_fga": 30.0},
        "weight_ledger_family": None,
        "seasons": _OFFENSE_SEASONS,
        "verifiable_by_design": True,
    },
    "clutch_fga_per_game": {
        "description": (
            "Clutch FGA per game the player logged >=1 clutch attempt -- a volume proxy substituting for FGA/36 "
            "(true clutch on-court minutes need joint roster+running-score tracking not on disk here; see "
            "player_offense_zones.py docstring)."
        ),
        "entity": "player",
        "ingredients": [
            {"name": "clutch_fga", "source": _OFFENSE_SRC},
            {"name": "game_id (n_games, clutch_fga>0 only)", "source": "team_system/composition/player_offense_events_<season>.parquet"},
        ],
        "formula": "sum(clutch_fga) / count_distinct(game_id | clutch_fga>0)",
        "status": "DESCRIPTIVE",
        "floor": {"clutch_fga": 30.0},
        "weight_ledger_family": None,
        "seasons": _OFFENSE_SEASONS,
        # n_games denominator needs a conditional distinct-count (games WHERE
        # clutch_fga>0) the claims grammar can't express -- no row-filter
        # support in aggregate_recompute.py, same exclusion class as
        # spacing_contribution/rim_pressure_def's own membership-parse gap.
        "verifiable_by_design": False,
    },
}

PLAYER_ATTRIBUTES.update(_zone_offense_entries())
PLAYER_ATTRIBUTES.update(_play_context_entries())
PLAYER_ATTRIBUTES.update(_CLUTCH_ENTRIES)

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

# ---------------------------------------------------------------------------
# ADDITIVE EXPANSION (defense/rebounding/fouls/team) -- appended after the
# hand-written dicts above rather than interleaved, so this whole block is a
# pure append (profiles/player_defense_zones.py, player_rebounding.py,
# player_fouls.py, team_expansion*.py are the builders).
# ---------------------------------------------------------------------------
_DEF_ZONES = ["rim", "paint", "mid", "corner3", "above_break_3"]
for _zone in _DEF_ZONES:
    for _metric in ("share_allowed", "efg_allowed"):
        for _side, _floor_key in (("on", "min_on"), ("off", "min_off")):
            PLAYER_ATTRIBUTES[f"zone_def_{_zone}_{_metric}_{_side}"] = {
                "description": f"Opponent {_zone} {_metric.replace('_', ' ')} while this player's lineup is {_side}-court (lower = better defense).",
                "entity": "player",
                "ingredients": [{"name": f"{_zone}_{_metric}_{_side}", "source": "team_system/lineups/zone_onoff_<season>.parquet"}],
                "formula": f"{_zone}_{_metric}_{_side} verbatim",
                "status": "DESCRIPTIVE",
                "floor": {"min_on": 750.0, "min_off": 750.0},
                "weight_ledger_family": None,
                "seasons": ["2023_24", "2024_25", "2025_26"],
                "verifiable_by_design": True,
            }

PLAYER_ATTRIBUTES["oreb_pct"] = {
    "description": "Offensive-rebound rate: this player's season OREB total / his own team's missed FGA while he was on-court (opportunity proxy, not the official NBA OREB%% formula).",
    "entity": "player",
    "ingredients": [
        {"name": "oreb", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
        {"name": "team_missed_fga_on", "source": "team_system/lineups/stints_<season>.parquet (PBP miss events, attach_lineup_to_shots)"},
    ],
    "formula": "sum(oreb) / team_missed_fga_while_on",
    "status": "DESCRIPTIVE",
    "floor": {"team_missed_fga_on": 200.0},
    "weight_ledger_family": None,
    "seasons": ["2024_25", "2025_26"],
    "verifiable_by_design": False,  # PBP on-court join, not a bare-column/groupby formula
}
PLAYER_ATTRIBUTES["dreb_pct"] = {
    "description": "Defensive-rebound rate: this player's season DREB total / the opponent's missed FGA while he was on-court (opportunity proxy).",
    "entity": "player",
    "ingredients": [
        {"name": "dreb", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
        {"name": "opp_missed_fga_on", "source": "team_system/lineups/zone_onoff_<season>.parquet (opp_fga_on, PBP miss events)"},
    ],
    "formula": "sum(dreb) / opp_missed_fga_while_on",
    "status": "DESCRIPTIVE",
    "floor": {"opp_missed_fga_on": 200.0},
    "weight_ledger_family": None,
    "seasons": ["2024_25", "2025_26"],
    "verifiable_by_design": False,
}
PLAYER_ATTRIBUTES["team_dreb_pct_swing"] = {
    "description": (
        "Boxout-adjacent proxy: this player's TEAM defensive-rebound rate (share of opponent misses "
        "the team recovers) while he's on-court minus while he's off -- the player-level expression of "
        "the replicated h7 stint-continuity-x-DREB mechanism, not itself gate-tested at this grain."
    ),
    "entity": "player",
    "ingredients": [{"name": "is_dreb / lineup_key membership", "source": "team_system/lineups/stints_<season>.parquet (PBP miss+rebound events, nba_hypotheses._load_missed_shots_and_rebounds)"}],
    "formula": "team_dreb_pct_on - team_dreb_pct_off",
    "status": "DESCRIPTIVE",
    "floor": {"min_on": 750.0, "min_off": 750.0},
    "weight_ledger_family": None,
    "seasons": ["2023_24", "2024_25", "2025_26"],
    "verifiable_by_design": False,
}
PLAYER_ATTRIBUTES["pf_per36"] = {
    "description": "Personal fouls committed per 36 minutes.",
    "entity": "player",
    "ingredients": [{"name": "pf", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                     {"name": "min", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
    "formula": "sum(pf) / sum(min) * 36",
    "status": "DESCRIPTIVE",
    "floor": {"min_sum": 200.0},
    "weight_ledger_family": None,
    "seasons": ["2024_25", "2025_26"],
    "verifiable_by_design": True,
}
for _side, _floor_key in (("on", "min_on"), ("off", "min_off")):
    PLAYER_ATTRIBUTES[f"opp_ft_rate_allowed_{_side}"] = {
        "description": f"Opponent FT-attempts-per-FGA while this player's lineup is {_side}-court (lower = fewer free points conceded).",
        "entity": "player",
        "ingredients": [
            {"name": "opp_fta", "source": "team_system/lineups/stints_<season>.parquet (PBP freethrow events, defending-team tagged)"},
            {"name": "opp_fga", "source": "team_system/lineups/zone_onoff_<season>.parquet"},
        ],
        "formula": f"opp_fta_{_side} / opp_fga_{_side}",
        "status": "DESCRIPTIVE",
        "floor": {"min_on": 750.0, "min_off": 750.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,  # 2-parquet merge (freethrow join + zone_onoff), not a bare groupby
    }

_OFF_ZONES = ["rim", "paint", "mid", "corner3", "above_break_3"]
for _zone in _OFF_ZONES:
    for _metric, _desc in (("share", "share of this team's own FGA"), ("efg", "eFG%% on this team's own attempts"), ("fga_per_game", "attempts/game")):
        TEAM_ATTRIBUTES[f"zone_offense_{_zone}_{_metric}"] = {
            "description": f"{_zone} {_desc} (own offense, PBP shot x/y + classify_zone).",
            "entity": "team",
            "ingredients": [{"name": "x/y/zone", "source": "team_system/lineups/stints_<season>.parquet (PBP shot events, classify_zone)"}],
            "formula": f"team {_zone} {_metric}, aggregated per team_id per season",
            "status": "DESCRIPTIVE",
            "floor": {"n_games": 10.0},
            "weight_ledger_family": None,
            "seasons": ["2023_24", "2024_25", "2025_26"],
            "verifiable_by_design": False,  # no persisted per-shot-zone parquet to independently recompute against
        }

for _side in ("home", "away", "home_away_diff"):
    TEAM_ATTRIBUTES[f"net_rating_{_side}"] = {
        "description": f"Net rating per48 in {_side.replace('_', ' ')} games." if _side != "home_away_diff" else "Net rating per48 home minus away (home-court proxy).",
        "entity": "team",
        "ingredients": [{"name": "pts_for/pts_against/elapsed_s", "source": "team_system/lineups/stints_<season>.parquet"},
                         {"name": "home_team/away_team", "source": "data/domains/basketball_nba/games.parquet"}],
        "formula": "(sum(pts_for) - sum(pts_against)) / sum(elapsed_s) * 48*60, split by home/away game_id",
        "status": "DESCRIPTIVE",
        "floor": {"n_games": 10.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,  # home/away conditional split via games.parquet join
    }

for _attr, _desc in (
    ("clutch_net_pts_per_game", "Mean point differential during clutch scoring events per game (last 5min Q4+OT, margin<=10) -- a proxy, NOT a true per-48 rate."),
    ("clutch_off_pts_per_game", "Mean points scored during clutch scoring events per game."),
    ("clutch_def_pts_per_game", "Mean points allowed during clutch scoring events per game."),
):
    TEAM_ATTRIBUTES[_attr] = {
        "description": _desc,
        "entity": "team",
        "ingredients": [{"name": "score deltas / period / clock", "source": "team_system/lineups/stints_<season>.parquet (PBP scoring events, clutch window: period>=4, remaining<=300s, |margin|<=10)"}],
        "formula": f"{_attr} = mean(clutch point differential or side) per game",
        "status": "DESCRIPTIVE",
        "floor": {"n_games": 10.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": False,  # time-windowed PBP walk, not a bare groupby
    }

TEAM_ATTRIBUTES["bench_min_share"] = {
    "description": "Share of total team minutes played by non-starters.",
    "entity": "team",
    "ingredients": [{"name": "min", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                     {"name": "starter", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
    "formula": "sum(min | not starter) / sum(min)",
    "status": "DESCRIPTIVE",
    "floor": {"n_games": 10.0},
    "weight_ledger_family": None,
    "seasons": ["2024_25", "2025_26"],
    "verifiable_by_design": False,  # conditional (starter==False) filter inside the aggregate, not a bare groupby
}

TEAM_ATTRIBUTES["oreb_pct_team"] = {
    "description": "Team offensive-rebound rate: team OREB / team's own missed FGA (opportunity proxy, box-derived).",
    "entity": "team",
    "ingredients": [{"name": "oreb", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                     {"name": "fga", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                     {"name": "fgm", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
    "formula": "sum(oreb) / (sum(fga) - sum(fgm))",
    "status": "DESCRIPTIVE",
    "floor": {"n_games": 10.0},
    "weight_ledger_family": None,
    "seasons": ["2024_25", "2025_26"],
    "verifiable_by_design": True,
}
TEAM_ATTRIBUTES["dreb_pct_team"] = {
    "description": "Team defensive-rebound rate: team DREB / opponent's missed FGA in the same games (opponent box join).",
    "entity": "team",
    "ingredients": [{"name": "dreb", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                     {"name": "opp fga/fgm", "source": "data/domains/basketball_nba/player_boxscores.parquet (opponent's own game row)"}],
    "formula": "sum(dreb) / opponent_missed_fga_same_games",
    "status": "DESCRIPTIVE",
    "floor": {"n_games": 10.0},
    "weight_ledger_family": None,
    "seasons": ["2024_25", "2025_26"],
    "verifiable_by_design": False,  # needs the OPPONENT team's box row in the same game -- a self-join
}
TEAM_ATTRIBUTES["ft_rate_team"] = {
    "description": "Team's own FT-attempts-per-FGA (offense side; concession_ft_rate_allowed is the defense side).",
    "entity": "team",
    "ingredients": [{"name": "fta", "source": "data/domains/basketball_nba/player_boxscores.parquet"},
                     {"name": "fga", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
    "formula": "sum(fta) / sum(fga)",
    "status": "DESCRIPTIVE",
    "floor": {"n_games": 10.0},
    "weight_ledger_family": None,
    "seasons": ["2024_25", "2025_26"],
    "verifiable_by_design": True,
}
TEAM_ATTRIBUTES["pf_per_game_team"] = {
    "description": "Personal fouls committed per team-game.",
    "entity": "team",
    "ingredients": [{"name": "pf", "source": "data/domains/basketball_nba/player_boxscores.parquet"}],
    "formula": "sum(pf) / count_distinct(game_id)",
    "status": "DESCRIPTIVE",
    "floor": {"n_games": 10.0},
    "weight_ledger_family": None,
    "seasons": ["2024_25", "2025_26"],
    "verifiable_by_design": True,
}
TEAM_ATTRIBUTES["avg_defensive_continuity_s"] = {
    "description": (
        "Mean lineup-continuity seconds sampled specifically at defensive-rebound-opportunity moments "
        "(an opponent miss) -- the raw material of the replicated h7 stint-continuity-x-DREB mechanism, "
        "at team grain (lineup_continuity_avg_stint_s is the unconditional version over ALL stints)."
    ),
    "entity": "team",
    "ingredients": [{"name": "continuity_s", "source": "team_system/lineups/stints_<season>.parquet (nba_hypotheses.build_continuity_dreb_tagged)"}],
    "formula": "mean(continuity_s) grouped by team_id, sampled at opponent-miss moments",
    "status": "VALIDATED_MECHANISM",
    "floor": {"n": 50.0},
    "weight_ledger_family": "nba_hypotheses_h7_continuity_dreb",
    "seasons": ["2023_24", "2024_25", "2025_26"],
    "verifiable_by_design": False,  # PBP miss->rebound asof join, not a bare groupby
}

# ---------------------------------------------------------------------------
# BOX-DETAIL as-of family (utilization audit docs/research/utilization_matrix_
# 2026_07_10.md ranked-backlog #1: espn_boxscores.parquet's box-detail columns
# were entirely dark). Each entry is a leak-free season-to-date trailing mean
# from domains/basketball_nba/boxdetail_asof.py -- tagged `family` so it
# AUTO-ENTERS the interaction factory's candidate space (see
# scripts/platformkit/interaction_factory/generator.py's resolve_pool) the
# moment any template declares `{"entity": "team", "family": "box_detail_asof"}`,
# no template edit needed if this list grows.
# ---------------------------------------------------------------------------
_BOXDETAIL_SPECS = [
    ("fast_break_pts_asof", "Season-to-date trailing mean of this team's own fast-break points."),
    ("paint_pts_asof", "Season-to-date trailing mean of this team's own points in the paint."),
    ("tov_pts_asof", "Season-to-date trailing mean of this team's own points scored off opponent turnovers."),
    ("largest_lead_asof", "Season-to-date trailing mean of this team's own largest lead (in-game stat, not a final-score column)."),
    ("foul_trouble_asof", "Season-to-date trailing mean of this team's own technical + flagrant foul count (combined -- both are individually thin/sparse counts)."),
]
for _attr, _desc in _BOXDETAIL_SPECS:
    TEAM_ATTRIBUTES[_attr] = {
        "description": _desc,
        "entity": "team",
        "family": "box_detail_asof",
        "ingredients": [{"name": _attr.replace("_asof", ""), "source": "data/domains/basketball_nba/espn_boxscores.parquet (via boxdetail_asof.py, prior-only walk-forward)"}],
        "formula": f"expanding mean of {_attr.replace('_asof', '')}, strictly prior games, snapshot-before-update",
        "status": "DESCRIPTIVE",
        "floor": {"n_prior": 1.0},
        "weight_ledger_family": None,
        "seasons": ["2025_26"],  # box-detail columns only populated 2026-01-20 onward on this corpus
        "verifiable_by_design": True,
    }

# ---------------------------------------------------------------------------
# CROSS-GAME CARRYOVER as-of family (C4 lane, depth-frontier item 4): yesterday's
# realized load (heavy-minutes fatigue + rest days), LAG-1 (the team's single
# immediately-prior game) not a season-to-date mean -- domains/basketball_nba/
# carryover_asof.py. Tagged `family` so it AUTO-ENTERS the interaction factory's
# candidate space (nba_carryover_self_cross template), same seam as box_detail_asof.
_CARRYOVER_SPECS = [
    ("heavy_min_load_asof", "Team's prior game's total minutes logged by heavy-usage "
                            "(>=30min) players -- a fatigue-carryover proxy."),
    ("rest_days_asof", "Days since the team's prior game (b2b/rest signal)."),
]
for _attr, _desc in _CARRYOVER_SPECS:
    TEAM_ATTRIBUTES[_attr] = {
        "description": _desc,
        "entity": "team",
        "family": "carryover_asof",
        "ingredients": [{"name": "min", "source": "data/domains/basketball_nba/player_boxscores.parquet (via carryover_asof.py, LAG-1 walk-forward)"}],
        "formula": f"LAG-1 (immediately-prior game) {_attr.replace('_asof', '')}, reset per team-season",
        "status": "DESCRIPTIVE",
        "floor": {"n_prior": 1.0},
        "weight_ledger_family": None,
        "seasons": ["2023_24", "2024_25", "2025_26"],
        "verifiable_by_design": True,
    }

ATTRIBUTES: dict[str, dict] = {**PLAYER_ATTRIBUTES, **TEAM_ATTRIBUTES, **LINEUP_ATTRIBUTES}
