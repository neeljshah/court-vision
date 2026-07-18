"""2025-26 (atlas-degraded) sibling of quality_validity_gate_claims.py.

Split into its own file purely to keep quality_validity_gate_claims.py under
the 300-LOC/file cap (same reason quality_claim_builders.py was split out of
it originally). atlas_player_*.parquet are single-season 2024-25-era
snapshots with NO season column -- quality_indices.build_factor_table joins
them onto the qualifying pool by player_id alone, so scoring season=2025-26
naively would silently pass off 2024-25 atlas values as this season's. This
module nulls every atlas-sourced raw column first so the existing pillar-
dropout renormalization (quality_indices_score.score_index) drops those
pillars honestly instead, then emits an atlas-degraded ranking claim whose
weights are renormalized over the pillars that DO survive (boxscore-only:
EFFICIENCY+VOLUME for shooter, VOLUME_LOAD+EFFICIENCY for scorer) so
criteria.formula stays exactly recomputable for every ranked row.

Called from quality_validity_gate_claims.run() -- see that module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.basketball_nba.quality_claim_builders import rank_of
from domains.basketball_nba.quality_indices import (
    QUALIFY_MIN_FGA,
    QUALIFY_MIN_GAMES,
    QUALIFY_SEASON,
    load_qualifying_factor_table,
)
from domains.basketball_nba.quality_indices_score import (
    QualityIndexResult,
    build_percentile_table,
    run as run_indices,
    score_index,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_SNAPSHOT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"

# every raw factor column quality_indices.build_factor_table reads from an
# atlas_player_*.parquet file (mirrors its own `out` dict keys verbatim).
ATLAS_DERIVED_COLS = [
    "shot_quality_ts", "usage_rate", "minutes_pg", "drives_per_game",
    "pullup_combined_freq", "pullup_pnr_ppp", "late_clock_shots_pg",
    "unassisted_share_3pm", "unassisted_share_2pm", "off_dribble_3_proxy",
    "iso_poss_pg", "pnr_handler_pg", "and_one_rate",
    "gravity_score", "cs_gravity_efg", "spotup_ppp", "creator_role_z",
    "scheme_robustness", "score_margin_consistency",
    "clutch_scoring_pts_per36", "blowout_gt_pct", "ft_reliability",
]
# pillars built ENTIRELY from ATLAS_DERIVED_COLS -- drop wholesale for any
# non-QUALIFY_SEASON season (never partially null'd across players; ts_pct/
# efg_pct/fga_per_game/fg3a_per_game are boxscore-derived and always survive).
ATLAS_ONLY_PILLARS = {
    "shooter": ["DIFFICULTY", "GRAVITY"],
    "scorer": ["CREATION_DIFFICULTY", "CONTEXT_ROBUSTNESS"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_indices_for_season(season: str) -> QualityIndexResult:
    """quality_indices_score.run(), but for any season other than
    QUALIFY_SEASON the atlas-only raw columns are nulled first (see
    ATLAS_DERIVED_COLS) -- byte-identical to run_indices(season) at
    QUALIFY_SEASON since no nulling happens there."""
    if season == QUALIFY_SEASON:
        return run_indices(season)
    t = load_qualifying_factor_table(season=season)
    for col in ATLAS_DERIVED_COLS:
        if col in t.columns:
            t[col] = float("nan")
    pct = build_percentile_table(t)
    shooter = score_index(t, pct, "shooter").sort_values(
        "shooter_quality_v1", ascending=False, na_position="last"
    ).reset_index(drop=True)
    scorer = score_index(t, pct, "scorer").sort_values(
        "scorer_quality_v1", ascending=False, na_position="last"
    ).reset_index(drop=True)
    return QualityIndexResult(factor_table=t, percentile_table=pct, shooter=shooter, scorer=scorer)


def degraded_ranking_claim(
    claim_id: str, question: str, declared_weights: dict, ranking_df: pd.DataFrame,
    score_col: str, index_name: str, season: str, computed_at: str, n_qualifying: int,
) -> dict[str, Any]:
    """Atlas-degraded sibling of quality_claim_builders.build_ranking_claim:
    ATLAS_ONLY_PILLARS[index_name] are unavailable this season for EVERY
    qualifying player (a season-wide ceiling, not a per-row artifact), so
    coverage caps at the present pillars' combined declared weight.
    min_sample floors on that achieved coverage instead of the full-
    population 1.0 the QUALIFY_SEASON sibling uses."""
    present = [p for p in declared_weights if p not in ATLAS_ONLY_PILLARS[index_name]]
    achieved = round(sum(declared_weights[p] for p in present), 6)
    effective_weights = {p: round(declared_weights[p] / achieved, 6) for p in present}

    qualifying = ranking_df[ranking_df["coverage"] >= achieved - 1e-9].sort_values(
        score_col, ascending=False
    ).reset_index(drop=True)
    n_excluded = n_qualifying - len(qualifying)

    season_id = season.replace("-", "_")
    snap_path = _SNAPSHOT_DIR / f"nba_{index_name}_quality_v1_pillar_snapshot_{season_id}.parquet"
    cols = ["player_id", "player_name", "games", "coverage"] + [f"pillar_{p}" for p in present]
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(ranking_df[cols], preserve_index=False), snap_path)

    ranking = [
        {"rank": i + 1, "player_id": int(row["player_id"]), "player_name": row["player_name"],
         "value": round(float(row[score_col]), 4), "n": int(row["games"]),
         "coverage": round(float(row["coverage"]), 4)}
        for i, row in qualifying.head(10).iterrows()
    ]
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": score_col,
            "formula": " + ".join(f"{w}*pillar_{p}" for p, w in effective_weights.items()),
            "weights": effective_weights,
            "floors": {"min_games": QUALIFY_MIN_GAMES, "min_fga": QUALIFY_MIN_FGA},
            "min_sample": {"coverage": achieved},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
            "window": season,
        },
        "ranking": ranking,
        "face_validity_diagnostic": {
            "type": "reported_never_a_fitting_target",
            "stephen_curry_rank": rank_of(ranking_df, score_col, "Stephen Curry"),
            "keon_ellis_rank": rank_of(ranking_df, score_col, "Keon Ellis"),
            "n_qualifying": n_qualifying,
            "top_decile_cutoff_rank": max(1, n_qualifying // 10),
        },
        "source_files": [str(snap_path.relative_to(REPO_ROOT)).replace("\\", "/")],
        "computed_at": computed_at,
        "n_considered": n_qualifying,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"ATLAS-UNAVAILABLE-2025-26: {', '.join(ATLAS_ONLY_PILLARS[index_name])} pillar(s) need "
            "atlas_player_*.parquet, which are single-season 2024-25-era snapshots with no season "
            "column and cannot be re-harvested (NBA API blocked) -- unavailable for 2025-26, never "
            f"silently reused. Weights renormalized over the present pillar(s) only: {effective_weights}.",
            f"achieved coverage this season: {achieved} (declared full coverage is 1.0) -- the "
            "min_sample floor above reflects that ceiling, not the full-population 1.0 the "
            "2024-25 sibling claim uses; below-ceiling players are counted in n_excluded_below_floor.",
            "Weights DECLARED and FROZEN before scoring (basketball_truth_spec.json) for the "
            "PRESENT pillars; never tuned to a named player's rank.",
            "RECOMPUTABILITY: criteria.formula is the renormalized fixed-weight pillar sum, valid "
            "ONLY for rows at the achieved coverage ceiling (min_sample floor) -- same recomputable-"
            "snapshot pattern as the QUALIFY_SEASON sibling claim's coverage>=1.0 contract.",
        ],
    }


def build_season_claims(weights_by_index: dict[str, dict], season: str = "2025-26") -> list[dict[str, Any]]:
    """One degraded ranking claim per index (shooter, scorer) for `season`."""
    idx = run_indices_for_season(season)
    computed_at = _now_iso()
    n_qualifying = len(idx.factor_table)
    season_id = season.replace("-", "_")
    return [
        degraded_ranking_claim(
            f"nba_shooter_quality_v1_full_season_{season_id}",
            f"Top shooter_quality_v1 (full season {season}, DECLARED/frozen weights, "
            "atlas-degraded, NOT market-fitted)",
            weights_by_index["shooter"], idx.shooter, "shooter_quality_v1", "shooter", season,
            computed_at, n_qualifying,
        ),
        degraded_ranking_claim(
            f"nba_scorer_quality_v1_full_season_{season_id}",
            f"Top scorer_quality_v1 (full season {season}, DECLARED/frozen weights, "
            "atlas-degraded, NOT market-fitted)",
            weights_by_index["scorer"], idx.scorer, "scorer_quality_v1", "scorer", season,
            computed_at, n_qualifying,
        ),
    ]
