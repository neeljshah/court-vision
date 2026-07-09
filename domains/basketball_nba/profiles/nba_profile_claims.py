"""TOP-15 ranking claims for every profiles/ attribute whose formula fits
claims_validator.py's independent-recompute grammar (row-wise column
arithmetic, OR groupby + sum/mean/count/count_distinct aggregate exprs --
see scripts/platformkit/intel_validation/safe_formula.py). Mirrors
nba_player_interaction_claims.py's criteria shape exactly so validate_store
recomputes every row with zero import of this module's own compute code.

Attributes registry.py marks verifiable_by_design=False (spacing_
contribution, rim_pressure_def, stint_stamina/minutes_load, transition_rate_
allowed, matchup_net) are DELIBERATELY excluded here -- their formulas need
lineup_key string-membership parsing or a JSON-string source column, neither
of which the validator's grammar supports. Documented in attribute_registry.py,
not silently skipped.

NETWORK: zero. edge_claimed hard-wired False on every row.
CLI: python -m domains.basketball_nba.profiles.nba_profile_claims
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_nba.composition.zone_geometry import ZONES
from domains.basketball_nba.profiles.attribute_registry import (
    CONCESSION_COLS, CONCESSION_LOWER_IS_BETTER, SHOT_DIET_COLS,
)
from domains.basketball_nba.profiles.profile_compute import REPO_ROOT

_LINEUPS = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_INTERACTIONS = REPO_ROOT / "data" / "cache" / "team_system" / "interactions"
_COMPOSITION = REPO_ROOT / "data" / "cache" / "team_system" / "composition"
_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_profile_claims.jsonl"

TOP_N = 15
SEASONS = ["2023_24", "2024_25", "2025_26"]


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT)).replace("\\", "/")


def _claim(
    *, claim_id: str, question: str, src: Path, entity_key: str, formula: str,
    min_sample: dict[str, Any], direction: str = "desc", aggregate: dict[str, Any] | None = None,
    window_spec: dict[str, Any] | None = None, caveats: list[str], top_n: int = TOP_N,
) -> dict[str, Any] | None:
    if not src.exists():
        return None
    from scripts.platformkit.intel_validation.safe_formula import FormulaError
    df = pd.read_parquet(src)
    try:
        if aggregate:
            from scripts.platformkit.intel_validation.aggregate_recompute import recompute_aggregate
            criteria_probe = {"aggregate": aggregate, "formula": formula}
            if window_spec:
                criteria_probe["window_spec"] = window_spec
            pool = recompute_aggregate(df, criteria_probe)
        else:
            pool = df.copy()
            pool["_value"] = _apply_rowwise(formula, pool)
    except FormulaError:
        return None  # e.g. no rows for this window (player_boxscores has no 2023-24)
    n_considered = len(pool)
    mask = pd.Series(True, index=pool.index)
    for col, floor in min_sample.items():
        mask &= pool[col] >= floor
    survivors = pool[mask & pool["_value"].notna()].copy()
    survivors = survivors.sort_values("_value", ascending=(direction == "asc")).head(top_n).reset_index(drop=True)

    ranking = []
    for i, row in survivors.iterrows():
        n_val = float(row.get("n", row["_value"]))
        ranking.append({
            "rank": i + 1, entity_key: (str(row[entity_key]) if isinstance(row[entity_key], str) else int(row[entity_key])),
            "value": round(float(row["_value"]), 4), "n": n_val,
            "text": f"{row[entity_key]}: {formula} = {round(float(row['_value']), 4)} (n={n_val:.0f})",
        })
    criteria: dict[str, Any] = {
        "metric": formula, "formula": formula, "window": src.stem, "min_sample": min_sample,
        "direction": direction, "value_precision": 4, "entity_key": entity_key,
    }
    if aggregate:
        criteria["aggregate"] = aggregate
    if window_spec:
        criteria["window_spec"] = window_spec
    return {
        "claim_id": claim_id, "kind": "ranking", "question": question, "criteria": criteria,
        "ranking": ranking, "source_files": [_rel(src)], "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": int((~mask).sum()),
        "edge_claimed": False, "caveats": caveats,
    }


def _apply_rowwise(formula: str, df: pd.DataFrame) -> pd.Series:
    from scripts.platformkit.intel_validation.safe_formula import evaluate_formula_vectorized
    return evaluate_formula_vectorized(formula, df)


_STANDARD_CAVEAT = (
    "DESCRIPTIVE composition of an on-disk artifact ONLY -- see domains/basketball_nba/profiles/"
    "attribute_registry.py for the full ingredient list. NOT causal, NOT a gate, no market/$ edge claimed."
)


def build_claims() -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for season in SEASONS:
        c = _claim(
            claim_id=f"nba_profile_gravity_top15_{season}",
            question="Which NBA players show the strongest on-court eFG gravity ({season})?".format(season=season),
            src=_LINEUPS / f"gravity_proxy_{season}.parquet", entity_key="player_id",
            formula="gravity_proxy", min_sample={"min_on": 300.0}, caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)

        c = _claim(
            claim_id=f"nba_profile_usage_absorption_top15_{season}",
            question=f"Which NBA players absorb the most shot-share, averaged across every teammate they play with ({season})?",
            src=_INTERACTIONS / f"usage_redistribution_{season}.parquet", entity_key="teammate_id",
            formula="mean(share_delta)", min_sample={"n": 100.0},
            aggregate={"group_by": "teammate_id", "derived": {"n": "sum(teammate_fga_joint)"}},
            caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)

        for attr, formula in [
            ("three_rate_per36", "sum(fg3a) / sum(min) * 36"),
            ("three_efg", "sum(fg3m) * 1.5 / sum(fg3a)"),
            ("two_rate_per36", "(sum(fga) - sum(fg3a)) / sum(min) * 36"),
            ("two_fg_pct", "(sum(fgm) - sum(fg3m)) / (sum(fga) - sum(fg3a))"),
        ]:
            label = season.replace("_", "-")
            c = _claim(
                claim_id=f"nba_profile_shot_zone_{attr}_top15_{season}",
                question=f"Which NBA players lead in shot_zone_{attr} ({season})?",
                src=_BOX, entity_key="player_id", formula=formula, min_sample={"n": 200.0},
                aggregate={"group_by": "player_id", "derived": {"n": "sum(min)"}},
                window_spec={"kind": "season", "season_col": "season", "season": label},
                caveats=[_STANDARD_CAVEAT, "player_boxscores.parquet has no 2023-24 rows."],
            )
            if c:
                claims.append(c)

        c = _claim(
            claim_id=f"nba_profile_lineup_spacing_top15_{season}",
            question=f"Which NBA lineups play with the most floor spacing ({season})?",
            src=_LINEUPS / f"lineup_spacing_{season}.parquet", entity_key="lineup_key",
            formula="spacing_mean_dist", min_sample={"n_shots": 100.0}, caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)

        c = _claim(
            claim_id=f"nba_profile_lineup_synergy_top15_{season}",
            question=f"Which NBA lineups beat their talent-sum expectation the most ({season})?",
            src=_INTERACTIONS / f"lineup_synergy_{season}.parquet", entity_key="lineup_key",
            formula="net_per48 - expected_net_per48", min_sample={"min": 100.0}, caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)

        c = _claim(
            claim_id=f"nba_profile_lineup_continuity_s_top15_{season}",
            question=f"Which NBA 5-man units log the most cumulative on-court seconds together ({season})?",
            src=_LINEUPS / f"stints_{season}.parquet", entity_key="lineup_key",
            formula="sum(elapsed_s)", min_sample={"_value": 200.0},
            aggregate={"group_by": "lineup_key", "derived": {"n": "count(elapsed_s)"}},
            caveats=[_STANDARD_CAVEAT],
        )
        if c:
            claims.append(c)

        c = _claim(
            claim_id=f"nba_profile_team_continuity_top15_{season}",
            question=f"Which NBA teams keep 5-man units intact the longest, mean stint length ({season})?",
            src=_LINEUPS / f"stints_{season}.parquet", entity_key="team_id",
            formula="mean(elapsed_s)", min_sample={"n": 10.0},
            aggregate={"group_by": "team_id", "derived": {"n": "count_distinct(game_id)"}},
            caveats=[
                "VALIDATED_MECHANISM -- team-level expression of the h7 stint-continuity mechanism "
                "(domains/basketball_nba/prereg/nba_hypotheses.py, replicated on 2024-25).",
            ],
        )
        if c:
            claims.append(c)

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


def write_claims(claims: list[dict[str, Any]], out_path: Path = _OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    claims = build_claims()
    out_path = write_claims(claims)
    for claim in claims:
        print(f"{claim['claim_id']}: n_considered={claim['n_considered']} n_ranked={len(claim['ranking'])}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
