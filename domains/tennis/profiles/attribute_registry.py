"""domains.tennis.profiles.attribute_registry -- single source of truth for
the tennis attribute engine's per-attribute status/floor/weight_ledger_family.
build_profiles.py reads this dict for metadata (coverage report, status
column, floor checks); the actual math per attribute lives in
build_profiles.py + ingredients.py as plain functions -- NOT a generic
formula executor (six attributes don't earn one; see ponytail rung 1).

STATUS enum (task-declared, verbatim):
  VALIDATED_MECHANISM -- only pressure_serve: raw_value is literally the
    per-player break-point-vs-baseline delta whose SIGN/SIGNIFICANCE was
    independently REPLICATED (same-sign, p<alpha in BOTH slam_points and
    charting_points 2016+) as H1 in prereg_point_mechanisms.py.
  VALIDATED_CLAIM -- reserved for an attribute whose value is a straight
    passthrough of an ALREADY claims_validator-VERIFIED ("green") claims
    family distinct from pressure_serve's own mechanism designation. No
    attribute below currently qualifies -- pressure_serve is explicitly
    VALIDATED_MECHANISM per the task spec, not this. Kept in the enum so a
    future attribute (e.g. a straight reuse of tennis_pressure_claims'
    bp_save_delta ranking under a new name) has a home without a schema
    change.
  DESCRIPTIVE -- everything else: real, floor-gated, but no prereg/
    replication/independent-validation claim attached.
  BLOCKED -- registered but NOT built; `reason` explains why, so the
    registry stays the single place that documents every attribute the
    task asked for, built or not.

surface_splits emits SIX concrete attribute names (one per direction x
surface); generated below by a plain loop, not a runtime abstraction.
"""
from __future__ import annotations

VALIDATED_MECHANISM = "VALIDATED_MECHANISM"
VALIDATED_CLAIM = "VALIDATED_CLAIM"
DESCRIPTIVE = "DESCRIPTIVE"
BLOCKED = "BLOCKED"

SURFACES = ("Hard", "Clay", "Grass")

ATTRIBUTES: dict[str, dict] = {
    "serve_dominance": {
        "description": (
            "Hold-adjacent serve strength: mean of whichever of "
            "{charting service-point win rate, serve_return_profiles.py's "
            "match-aggregate serve_strength} are available for (entity_id, window)."
        ),
        "entity": "player",
        "ingredients": ["charting_svc_win_rate", "match_agg_serve_strength"],
        "formula": "mean(available of [charting_svc_win_rate, match_agg_serve_strength])",
        "status": DESCRIPTIVE,
        "floor": {"charting_svc_n": 1000},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "return_strength": {
        "description": (
            "Return strength: mean of whichever of {charting return-point win "
            "rate, serve_return_profiles.py's match-aggregate return_strength} "
            "are available for (entity_id, window)."
        ),
        "entity": "player",
        "ingredients": ["charting_return_win_rate", "match_agg_return_strength"],
        "formula": "mean(available of [charting_return_win_rate, match_agg_return_strength])",
        "status": DESCRIPTIVE,
        "floor": {"charting_return_n": 1000},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "pressure_serve": {
        "description": (
            "Break-point serve delta vs the player's own baseline serve-win "
            "rate (bp_save_rate - baseline), REUSED verbatim from "
            "pressure_claims.py's snapshot -- the same computation backing "
            "H1's replicated break-point-serve-dip mechanism."
        ),
        "entity": "player",
        "ingredients": ["charting_bp_save_rate", "charting_baseline_serve_win_rate"],
        "formula": "bp_save_rate - baseline",
        "status": VALIDATED_MECHANISM,
        "floor": {"n_bp_faced": 200},
        "weight_ledger_family": "tennis_pressure_serve_mechanism",
    },
    "second_serve_reliability": {
        "description": (
            "Second-serve point win rate (charting is_second_serve split); "
            "first-serve win rate carried as a same-window ingredient for context."
        ),
        "entity": "player",
        "ingredients": ["charting_second_serve_win_rate", "charting_first_serve_win_rate"],
        "formula": "second_serve_win_rate",
        "status": DESCRIPTIVE,
        "floor": {"first_serve_n": 300, "second_serve_n": 300},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "rally_tolerance": {
        "description": "Rally-length-conditioned performance -- NOT BUILT.",
        "entity": "player",
        "ingredients": [],
        "formula": None,
        "status": BLOCKED,
        "floor": {},
        "weight_ledger_family": None,
        "reason": (
            "no usable rally-length signal in either point corpus: "
            "charting_points.rally_length is 100% null by design (verified "
            "this session); slam_points.rally is 78.9% null and the "
            "missingness is not declared random -- neither clears a floor "
            "worth setting."
        ),
    },
    "surface_splits": {
        "description": (
            "Career-only serve/return win rate by surface, joined via "
            "charting-m/w-matches.csv's own Surface column keyed on the same "
            "match_id charting_points.parquet uses (100% coverage, verified). "
            "Emits 6 concrete attribute rows: surface_splits_{serve,return}_"
            "{Hard,Clay,Grass}."
        ),
        "entity": "player",
        "ingredients": ["charting_serve_win_rate_by_surface", "charting_return_win_rate_by_surface"],
        "formula": "serve_won/serve_n (or return_won/return_n) grouped by surface, career window only",
        "status": DESCRIPTIVE,
        "floor": {"n": 300},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
}

# surface_splits concrete attribute names, generated from the one family entry
# above (plain loop -- not a runtime formula engine).
for _direction in ("serve", "return"):
    for _surface in SURFACES:
        ATTRIBUTES[f"surface_splits_{_direction}_{_surface}"] = {
            **{k: v for k, v in ATTRIBUTES["surface_splits"].items() if k != "description"},
            "description": f"Career {_direction} win rate on {_surface} (see surface_splits family entry above).",
        }
del ATTRIBUTES["surface_splits"]  # family entry stays documentation-only; concrete rows are the 6 above


# ---------------------------------------------------------------------------
# EXPANDED attributes (10 -> 49): court side, set-number, momentum, tiebreak,
# second-serve aggression, game-point conversion (11 concrete names, math in
# ingredients_expanded.py/build_profiles_expanded.py), plus MATCH_AGG_METRICS
# x MATCH_AGG_BUCKETS (28 concrete names, one per match_stats window metric x
# surface bucket). All DESCRIPTIVE -- no prereg/replication claim attached.
# Court side IS derivable (within-game point-index parity, verified on real
# data -- see ingredients_expanded.py docstring), so it is NOT registry-
# BLOCKED.
# ---------------------------------------------------------------------------
MATCH_AGG_METRICS = ("ace_rate", "df_rate", "first_serve_in", "first_serve_win",
                      "second_serve_win", "bp_saved", "return_pts_won")
MATCH_AGG_BUCKETS = SURFACES + ("Overall",)
MATCH_AGG_FLOOR = 20  # >=20 matches per (entity, window, bucket) -- task-declared

_EXPANDED: dict[str, dict] = {
    "courtside_serve_deuce": {
        "description": (
            "Server win rate on points served from the deuce (right) court, side "
            "derived from within-game point-index parity (idx%2==0): consecutive "
            "charting_points rows sharing (match_id,set1,set2,gm1,gm2) ARE one "
            "game's points in file order (verified) -- deuce/ad alternation is a "
            "fixed tennis rule independent of score labels."
        ),
        "entity": "player", "ingredients": ["charting_courtside_points"],
        "formula": "won/n where within_game_point_index % 2 == 0",
        "status": DESCRIPTIVE, "floor": {"n": 150},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "courtside_serve_ad": {
        "description": "Server win rate on points served from the ad (left) court (idx%2==1); see courtside_serve_deuce.",
        "entity": "player", "ingredients": ["charting_courtside_points"],
        "formula": "won/n where within_game_point_index % 2 == 1",
        "status": DESCRIPTIVE, "floor": {"n": 150},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "serve_by_set_set1": {
        "description": "Server win rate on points played in set 1 (stamina-proxy family, freshest state).",
        "entity": "player", "ingredients": ["charting_set_bucket_points"],
        "formula": "won/n where set1+set2+1 == 1", "status": DESCRIPTIVE,
        "floor": {"n": 150}, "weight_ledger_family": "tennis_profile_descriptive",
    },
    "serve_by_set_set2": {
        "description": "Server win rate on points played in set 2 (stamina-proxy family, mid-match state).",
        "entity": "player", "ingredients": ["charting_set_bucket_points"],
        "formula": "won/n where set1+set2+1 == 2", "status": DESCRIPTIVE,
        "floor": {"n": 150}, "weight_ledger_family": "tennis_profile_descriptive",
    },
    "serve_by_set_set3plus": {
        "description": "Server win rate on points played in set 3 or later (stamina-proxy family, late-match state).",
        "entity": "player", "ingredients": ["charting_set_bucket_points"],
        "formula": "won/n where set1+set2+1 >= 3", "status": DESCRIPTIVE,
        "floor": {"n": 150}, "weight_ledger_family": "tennis_profile_descriptive",
    },
    "momentum_bounceback": {
        "description": (
            "Hold-rate delta: server's hold rate in service games immediately "
            "following their OWN previous service game being broken, minus their "
            "own baseline hold rate (baseline restricted to service games that HAVE "
            "a preceding own service game in the same match, for an apples-to-apples "
            "comparison)."
        ),
        "entity": "player", "ingredients": ["charting_service_games"],
        "formula": "hold_rate(prev_own_service_game_broken) - hold_rate(baseline)",
        "status": DESCRIPTIVE, "floor": {"n": 15},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "momentum_streakiness": {
        "description": (
            "Point-win-rate delta: rate of winning a point given the SAME player "
            "won the immediately preceding point in the match (serve or return role "
            "either way), minus their unconditional point-win rate. Raw descriptive "
            "share, not a causal claim -- correlates with who's currently serving."
        ),
        "entity": "player", "ingredients": ["charting_point_sequence"],
        "formula": "win_rate(prev_point_won) - win_rate(unconditional)",
        "status": DESCRIPTIVE, "floor": {"n": 200},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "tiebreak_points_won_share": {
        "description": (
            "Share of tiebreak points won (serve or return role either way), over "
            "charting_points rows whose score_state fails the standard 0/15/30/40/AD "
            "parse but both tokens ARE raw integers (declared tiebreak signature; "
            "undercounts each breaker's ambiguous 0-0 opening point by design)."
        ),
        "entity": "player", "ingredients": ["charting_tiebreak_points"],
        "formula": "won/n over tiebreak points", "status": DESCRIPTIVE,
        "floor": {"n": 30}, "weight_ledger_family": "tennis_profile_descriptive",
    },
    "tiebreak_serve_win_rate": {
        "description": "Server win rate on tiebreak points only (server-perspective subset of tiebreak_points_won_share).",
        "entity": "player", "ingredients": ["charting_tiebreak_serve_points"],
        "formula": "won/n over tiebreak points, server perspective", "status": DESCRIPTIVE,
        "floor": {"n": 20}, "weight_ledger_family": "tennis_profile_descriptive",
    },
    "second_serve_aggression_delta": {
        "description": (
            "second_serve_win_rate - first_serve_win_rate, REUSING "
            "ingredients.second_serve_ingredient's own floored rates verbatim (same "
            "floor as second_serve_reliability) -- less negative/positive means less "
            "drop-off going to the second serve."
        ),
        "entity": "player", "ingredients": ["charting_first_serve_win_rate", "charting_second_serve_win_rate"],
        "formula": "second_rate - first_rate", "status": DESCRIPTIVE,
        "floor": {"n": 300}, "weight_ledger_family": "tennis_profile_descriptive",
    },
    "game_point_conversion": {
        "description": (
            "Win-rate delta on the server's OWN game point (score 40-x/AD, one point "
            "from winning the game) vs their baseline serve-win rate -- the mirror of "
            "pressure_serve's break-point-save delta, computed the same descriptive "
            "way (not the VALIDATED_MECHANISM OLS/replication path)."
        ),
        "entity": "player", "ingredients": ["charting_game_point_points"],
        "formula": "win_rate(game_point) - win_rate(baseline)", "status": DESCRIPTIVE,
        "floor": {"n": 200}, "weight_ledger_family": "tennis_profile_descriptive",
    },
}

for _metric in MATCH_AGG_METRICS:
    for _bucket in MATCH_AGG_BUCKETS:
        _EXPANDED[f"match_agg_{_metric}_{_bucket}"] = {
            "description": f"Mean match_stats {_metric} on {_bucket} surface (season/career window, match_stats+matches/wta_matches join, floor >={MATCH_AGG_FLOOR} matches).",
            "entity": "player", "ingredients": [f"match_stats_{_metric}"],
            "formula": f"mean({_metric}) grouped by (entity, window, surface={_bucket})",
            "status": DESCRIPTIVE, "floor": {"n": MATCH_AGG_FLOOR},
            "weight_ledger_family": "tennis_profile_descriptive",
        }

ATTRIBUTES.update(_EXPANDED)


# ---------------------------------------------------------------------------
# WINDOW + OPPONENT-TIER + FORM attributes (49 -> 72 registry keys): per-year
# GAME-DATED match_agg windows (year_YYYY, gate-consumable), opponent-rank-
# tier splits (top20 / outside_top50), and a last-10-matches FORM snapshot.
# Math in ingredients_windows.py/build_profiles_windows.py. All DESCRIPTIVE.
#
# window_<metric> is the PREDICTIONS-FACING multiplier: a year_2024 row can
# condition a 2025 match via the leak-free prior-window gate (see
# ingredients_windows.py's module docstring for the exact regex it matches).
#
# One registry key per METRIC, not per year -- window is a per-row runtime
# value in the parquet (same convention match_agg_{metric}_{bucket} already
# uses for its own per-year rows), so the per-year multiplier does NOT
# explode the registry-key count; build_profiles_windows.main() separately
# reports the distinct (attribute, window) pair count, which DOES grow with
# every year.
# ---------------------------------------------------------------------------
OPPONENT_TIERS = ("top20", "outside_top50")
WINDOW_YEAR_FLOOR = 20   # >=20 matches/year, task-declared
TIER_FLOOR = 15          # >=15 matches/tier, task-declared
FORM_FLOOR = 10          # last-10-matches, task-declared

_WINDOWS: dict[str, dict] = {}
for _metric in MATCH_AGG_METRICS:
    _WINDOWS[f"window_{_metric}"] = {
        "description": (
            f"Per-year mean match_stats {_metric}, window='year_<YYYY>' (2015-2025, "
            f"floor >={WINDOW_YEAR_FLOOR} matches/year) -- GAME-DATED, gate-consumable "
            "(claim_features.window_to_season style='plain' matches ^year_(\\d{4})$). "
            "PREDICTIONS-FACING: a year_2024 row can condition a 2025 match."
        ),
        "entity": "player", "ingredients": [f"match_stats_{_metric}"],
        "formula": f"mean({_metric}) grouped by (entity, year), window='year_<YYYY>'",
        "status": DESCRIPTIVE, "floor": {"n": WINDOW_YEAR_FLOOR},
        "weight_ledger_family": "tennis_profile_window_predictive",
    }
    for _tier in OPPONENT_TIERS:
        _WINDOWS[f"opp_tier_{_metric}_{_tier}"] = {
            "description": (
                f"Career mean match_stats {_metric} restricted to matches vs "
                f"{'top-20-ranked' if _tier == 'top20' else 'outside-top-50-ranked'} "
                "opponents (matches.parquet/wta_matches.parquet p{1,2}_rank of the "
                "OPPONENT; rows with a missing opponent rank are excluded, not "
                f"guessed). Floor >={TIER_FLOOR} matches in the tier."
            ),
            "entity": "player", "ingredients": [f"match_stats_{_metric}", "opponent_rank"],
            "formula": f"mean({_metric}) where opp_rank {'<=20' if _tier == 'top20' else '>50'}, career window",
            "status": DESCRIPTIVE, "floor": {"n": TIER_FLOOR},
            "weight_ledger_family": "tennis_profile_descriptive",
        }
ATTRIBUTES.update(_WINDOWS)

ATTRIBUTES["form_serve_dominance"] = {
    "description": (
        "Mean per-match serve-points-won realized rate (asof_hold._derive_realized, "
        "same formula serve_return_profiles.py uses) over the player's most recent "
        f"{FORM_FLOOR} matches -- rolling FORM snapshot, window='last10'."
    ),
    "entity": "player", "ingredients": ["match_stats_serve_pts_won"],
    "formula": f"mean(serve_pts_won_realized) over last {FORM_FLOOR} matches by date",
    "status": DESCRIPTIVE, "floor": {"n": FORM_FLOOR},
    "weight_ledger_family": "tennis_profile_descriptive",
}
ATTRIBUTES["form_return_strength"] = {
    "description": (
        "Mean per-match return-points-won realized rate (asof_return._derive_realized_return, "
        "same formula serve_return_profiles.py/match_agg_return_pts_won use) over the "
        f"player's most recent {FORM_FLOOR} matches -- window='last10'."
    ),
    "entity": "player", "ingredients": ["match_stats_return_pts_won"],
    "formula": f"mean(return_pts_won_realized) over last {FORM_FLOOR} matches by date",
    "status": DESCRIPTIVE, "floor": {"n": FORM_FLOOR},
    "weight_ledger_family": "tennis_profile_descriptive",
}


def concrete_attributes() -> list[str]:
    """All attribute names that build_profiles.py actually writes rows for (excludes BLOCKED)."""
    return [name for name, spec in ATTRIBUTES.items() if spec["status"] != BLOCKED]


def blocked_attributes() -> dict[str, str]:
    """attribute_name -> reason, for the ones registered but never built."""
    return {name: spec["reason"] for name, spec in ATTRIBUTES.items() if spec["status"] == BLOCKED}
