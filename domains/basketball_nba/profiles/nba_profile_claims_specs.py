"""2025-26-only + additive claim SPECS split out of nba_profile_claims.py to
keep that file under the 300 LOC cap -- pure code move, zero behavior change.
Same _claim() helper, same append order; see nba_profile_claims.py's module
docstring for the validator-grammar contract these formulas must satisfy.

NETWORK: zero. Imported lazily from build_claims() (after nba_profile_claims
has finished module-level execution), so the back-import below is safe.
"""
from __future__ import annotations

from typing import Any

from domains.basketball_nba.composition.zone_geometry import ZONES
from domains.basketball_nba.profiles.attribute_registry import (
    CONCESSION_COLS, CONCESSION_LOWER_IS_BETTER, SHOT_DIET_COLS,
)
from domains.basketball_nba.profiles.nba_profile_claims import (
    SEASONS, _BOX, _claim, _COMPOSITION, _INTERACTIONS, _LINEUPS, _STANDARD_CAVEAT,
)


def build_additive_claims() -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []

    # 2025-26-only sources
    for col in SHOT_DIET_COLS:
        c = _claim(
            claim_id=f"nba_profile_shot_diet_{col}_top15_2025_26",
            question=f"Which NBA teams lead in shot_diet_{col} (2025-26)?",
            src=_COMPOSITION / "shot_diet_2025_26.parquet", entity_key="team_id",
            formula=f"mean({col})", min_sample={"n": 10.0},
            aggregate={"group_by": "team_id", "derived": {"n": "count(game_id)"}},
            caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)

    c = _claim(
        claim_id="nba_profile_pace_proxy_top15_2025_26",
        question="Which NBA teams attempt the most FGA/game, a tempo proxy (2025-26)?",
        src=_COMPOSITION / "shot_diet_2025_26.parquet", entity_key="team_id",
        formula="mean(total_fga)", min_sample={"n": 10.0},
        aggregate={"group_by": "team_id", "derived": {"n": "count(game_id)"}},
        caveats=[_STANDARD_CAVEAT, "Shot-VOLUME tempo proxy, NOT true possessions/48."],
    )
    if c:
        claims.append(c)

    for col in CONCESSION_COLS:
        c = _claim(
            claim_id=f"nba_profile_concession_{col}_top15_2025_26",
            question=f"Which NBA defenses concede the most {col} (2025-26)?",
            src=_COMPOSITION / "concession_2025_26.parquet", entity_key="defense_team_id",
            formula=col, min_sample={"n_shots_faced": 500.0},
            direction=("asc" if col in CONCESSION_LOWER_IS_BETTER else "desc"),
            caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)

    c = _claim(
        claim_id="nba_profile_creation_top15_2025_26",
        question="Which NBA players generate the most eFG lift for teammates they assist (2025-26)?",
        src=_INTERACTIONS / "assist_network_2025_26.parquet", entity_key="assister_id",
        formula="mean(efg_delta)", min_sample={"n": 20.0},
        aggregate={"group_by": "assister_id", "derived": {"n": "sum(n_assists)"}},
        caveats=[_STANDARD_CAVEAT, "assist_network.parquet only built for 2025-26."],
    )
    if c:
        claims.append(c)

    # ---- additive: defense-zone (player) + pf_per36 (player) + box-derived
    # team splits -- the verifiable_by_design=True subset of the defense/
    # rebounding/fouls/team expansion (player_defense_zones.py,
    # player_fouls.py, team_box_splits.py). Top-10, not top-15, per the lane
    # brief. Everything else in that expansion needs a PBP on-court join or a
    # multi-parquet merge -- marked verifiable_by_design=False in the
    # registry and deliberately has no claim here (same precedent as
    # rim_pressure_def/spacing_contribution above).
    _DEF_ZONES = ["rim", "paint", "mid", "corner3", "above_break_3"]
    for season in SEASONS:
        for zone in _DEF_ZONES:
            for metric in ("share_allowed", "efg_allowed"):
                for side in ("on", "off"):
                    col = f"{zone}_{metric}_{side}"
                    c = _claim(
                        claim_id=f"nba_profile_zone_def_{zone}_{metric}_{side}_top10_{season}",
                        question=f"Which NBA players allow the least {zone} {metric.replace('_', ' ')} while {side}-court ({season})?",
                        src=_LINEUPS / f"zone_onoff_{season}.parquet", entity_key="player_id",
                        formula=col, min_sample={"min_on": 750.0, "min_off": 750.0}, direction="asc",
                        top_n=10, caveats=[_STANDARD_CAVEAT],
                    )
                    if c:
                        claims.append(c)

        label = season.replace("_", "-")
        c = _claim(
            claim_id=f"nba_profile_pf_per36_top10_{season}",
            question=f"Which NBA players commit the most personal fouls per 36 minutes ({season})?",
            src=_BOX, entity_key="player_id", formula="sum(pf) / sum(min) * 36", min_sample={"n": 200.0},
            aggregate={"group_by": "player_id", "derived": {"n": "sum(min)"}},
            window_spec={"kind": "season", "season_col": "season", "season": label},
            top_n=10, caveats=[_STANDARD_CAVEAT, "player_boxscores.parquet has no 2023-24 rows."],
        )
        if c:
            claims.append(c)

        for attr, formula in [
            ("oreb_pct_team", "sum(oreb) / (sum(fga) - sum(fgm))"),
            ("ft_rate_team", "sum(fta) / sum(fga)"),
            ("pf_per_game_team", "sum(pf) / count_distinct(game_id)"),
        ]:
            c = _claim(
                claim_id=f"nba_profile_{attr}_top10_{season}",
                question=f"Which NBA teams lead in {attr} ({season})?",
                src=_BOX, entity_key="team", formula=formula, min_sample={"n": 10.0},
                aggregate={"group_by": "team", "derived": {"n": "count_distinct(game_id)"}},
                window_spec={"kind": "season", "season_col": "season", "season": label},
                direction=("asc" if attr == "pf_per_game_team" else "desc"),
                top_n=10, caveats=[_STANDARD_CAVEAT, "player_boxscores.parquet has no 2023-24 rows; entity is team tricode, not numeric team_id."],
            )
            if c:
                claims.append(c)

    # ---- additive: player_offense_events.py (zone/context/clutch) -- 23 of
    # the 24 new offense attributes (clutch_fga_per_game excluded: its
    # n_games denominator needs a conditional distinct-count the aggregate
    # grammar can't express -- see attribute_registry.py's _CLUTCH_ENTRIES).
    # All 23 source the SAME per-season wide table, formulas built the same
    # sum-ratio way as the shot_zone_* claims above.
    _THREE_ZONES = {"corner3", "above_break_3"}
    for season in SEASONS:
        src = _COMPOSITION / f"player_offense_events_{season}.parquet"
        for z in ZONES:
            mult = 1.5 if z in _THREE_ZONES else 1.0
            c = _claim(
                claim_id=f"nba_profile_zone_attempt_share_{z}_top15_{season}",
                question=f"Which NBA players lean most on {z}-zone attempts, share of own FGA ({season})?",
                src=src, entity_key="player_id", formula=f"sum({z}_fga) / sum(total_fga)",
                min_sample={"n": 25.0},
                aggregate={"group_by": "player_id", "derived": {"n": f"sum({z}_fga)"}},
                caveats=[_STANDARD_CAVEAT],
            )
            if c:
                claims.append(c)
            c = _claim(
                claim_id=f"nba_profile_zone_efg_{z}_top15_{season}",
                question=f"Which NBA players shoot the best eFG% from the {z} zone ({season})?",
                src=src, entity_key="player_id", formula=f"(sum({z}_fgm) * {mult}) / sum({z}_fga)",
                min_sample={"n": 25.0},
                aggregate={"group_by": "player_id", "derived": {"n": f"sum({z}_fga)"}},
                caveats=[_STANDARD_CAVEAT],
            )
            if c:
                claims.append(c)
            c = _claim(
                claim_id=f"nba_profile_zone_assisted_share_{z}_top15_{season}",
                question=f"Which NBA players get the most assisted makes from the {z} zone ({season})?",
                src=src, entity_key="player_id", formula=f"sum({z}_assisted) / sum({z}_fgm)",
                min_sample={"n": 25.0},
                aggregate={"group_by": "player_id", "derived": {"n": f"sum({z}_fga)"}},
                caveats=[_STANDARD_CAVEAT],
            )
            if c:
                claims.append(c)

        for prefix in ("transition", "halfcourt", "late_clock"):
            c = _claim(
                claim_id=f"nba_profile_{prefix}_efg_top15_{season}",
                question=f"Which NBA players shoot the best eFG% in {prefix} situations ({season})?",
                src=src, entity_key="player_id",
                formula=f"(sum({prefix}_fgm) + 0.5 * sum({prefix}_fg3m)) / sum({prefix}_fga)",
                min_sample={"n": 25.0},
                aggregate={"group_by": "player_id", "derived": {"n": f"sum({prefix}_fga)"}},
                caveats=[_STANDARD_CAVEAT],
            )
            if c:
                claims.append(c)
            c = _claim(
                claim_id=f"nba_profile_{prefix}_attempt_share_top15_{season}",
                question=f"Which NBA players lean most on {prefix} attempts, share of own FGA ({season})?",
                src=src, entity_key="player_id", formula=f"sum({prefix}_fga) / sum(total_fga)",
                min_sample={"n": 25.0},
                aggregate={"group_by": "player_id", "derived": {"n": f"sum({prefix}_fga)"}},
                caveats=[_STANDARD_CAVEAT],
            )
            if c:
                claims.append(c)

        c = _claim(
            claim_id=f"nba_profile_clutch_efg_top15_{season}",
            question=f"Which NBA players shoot the best clutch eFG%, Q4/OT <=5min <=10pt margin ({season})?",
            src=src, entity_key="player_id",
            formula="(sum(clutch_fgm) + 0.5 * sum(clutch_fg3m)) / sum(clutch_fga)",
            min_sample={"n": 30.0},
            aggregate={"group_by": "player_id", "derived": {"n": "sum(clutch_fga)"}},
            caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)
        c = _claim(
            claim_id=f"nba_profile_clutch_ft_rate_top15_{season}",
            question=f"Which NBA players draw the most clutch free throws per FGA ({season})?",
            src=src, entity_key="player_id", formula="sum(clutch_fta) / sum(clutch_fga)",
            min_sample={"n": 30.0},
            aggregate={"group_by": "player_id", "derived": {"n": "sum(clutch_fga)"}},
            caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)

    return claims
