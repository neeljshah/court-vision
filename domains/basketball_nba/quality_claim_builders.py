"""Claim-row builders for the 3a gate + quality-index rankings (split out of
quality_validity_gate_claims.py purely to stay under the 300-LOC/file cap --
that module keeps write_claims/write_answers_md/run() orchestration).

build_gate_claim: kind="gate_verdict" (see its own PROVENANCE caveat for why
this stays UNVERIFIABLE by construction rather than fabricating a field to
fit either sibling validator's contract).

build_ranking_claim: kind="ranking", made independently recomputable via
quality_claims_snapshot.py -- see that module's docstring for the full
provenance-contract rationale (a fixed-weight pillar sum over a snapshot of
quality_indices_score.score_index()'s own pillar_<PILLAR> output columns).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from domains.basketball_nba.quality_claims_snapshot import build_pillar_formula, write_pillar_snapshot
from domains.basketball_nba.quality_indices import BOXSCORE_PATH, QUALIFY_MIN_FGA, QUALIFY_MIN_GAMES
from domains.basketball_nba.quality_validity_gate import GateResult, VERDICT_PATH

VERDICT_FILE = VERDICT_PATH  # relative path string, matches quality_validity_gate.VERDICT_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ranking_rows(df: pd.DataFrame, score_col: str, top_n: int = 10) -> list[dict]:
    rows = []
    for i, row in df.head(top_n).iterrows():
        rows.append({
            "rank": int(i) + 1,
            "player_id": int(row["player_id"]),
            "player_name": row["player_name"],
            "value": round(float(row[score_col]), 4),
            "n": int(row["games"]),
            "coverage": round(float(row["coverage"]), 4),
        })
    return rows


def rank_of(df: pd.DataFrame, score_col: str, name: str) -> int:
    ranked = df.sort_values(score_col, ascending=False, na_position="last").reset_index(drop=True)
    match = ranked[ranked["player_name"] == name]
    return int(match.index[0]) + 1 if len(match) else -1


def write_verdict(g: GateResult, path: str = VERDICT_PATH) -> dict:
    """data/domains/*/*_verdict.json convention (see build_gate_claim's
    PROVENANCE caveat for why this has no planted_null_passed field)."""
    doc = {
        "component": "quality_validity_gate_3a_shooter_quality_v1_vs_naive",
        "sport": "basketball_nba",
        "hypothesis": "shooter_quality_v1 (declared/frozen weights) predicts future TS% "
                       "better than the naive composite (pre-registered walk-forward gate)",
        "verdict": g.verdict,
        "mean_rho_shooter_quality_v1": g.mean_rho_shooter,
        "mean_rho_naive": g.mean_rho_naive,
        "bootstrap_delta_ci": g.bootstrap,
        "sign_holds_folds": g.sign_holds_folds,
        "n_folds": g.n_folds,
        "per_cutoff": g.per_cutoff,
        "replication_2025_26": g.replication,
        "generated_at": _now_iso(),
        "honest_note": "predictive-validity comparison only; naive composite "
                        "(0.55*TS%+0.30*eFG%+0.15*FT%) stays canonical unless "
                        "verdict=SHIP_RICHER_INDEX; REJECT is a recorded success, not a failure",
        "edge_claimed": False,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1), encoding="ascii")
    return doc


def build_gate_claim(gate: GateResult, computed_at: str) -> dict:
    """kind stays "gate_verdict" -- see the returned claim's PROVENANCE caveat
    for why neither sibling validator's contract fits without fabricating a
    field."""
    return {
        "claim_id": "nba_quality_predictive_validity_gate_3a",
        "kind": "gate_verdict",
        "question": "Does shooter_quality_v1 predict future TS% better than the naive composite (pre-registered walk-forward gate)?",
        "criteria": {
            "gate": "3a_predictive_validity",
            "primary_target": "realized_ts_pct over [T, T+30d], forward_games>=8, on 329-qualifier pool",
            "comparison_statistic": "mean Spearman rho across cutoffs; paired bootstrap clustered by player on rho(shooter)-rho(naive)",
            "win_rule": "CI excludes 0 in favor AND sign holds >=3/4 folds AND replicates in 2025-26",
        },
        "verdict_file": VERDICT_FILE,
        "verdict": gate.verdict,
        "mean_rho_shooter_quality_v1": round(gate.mean_rho_shooter, 4) if not np.isnan(gate.mean_rho_shooter) else None,
        "mean_rho_naive": round(gate.mean_rho_naive, 4) if not np.isnan(gate.mean_rho_naive) else None,
        "bootstrap_delta_ci": (
            {k: (round(v, 4) if isinstance(v, float) else v) for k, v in gate.bootstrap.items()}
            if gate.bootstrap else None
        ),
        "sign_holds_folds": f"{gate.sign_holds_folds}/{gate.n_folds}",
        "per_cutoff": gate.per_cutoff,
        "replication_2025_26": gate.replication,
        "source_files": [
            BOXSCORE_PATH,
            "data/cache/atlas_player_catch_shoot_vs_pullup.parquet",
            "data/cache/atlas_player_spacing_gravity.parquet",
            "data/cache/atlas_player_scoring_creation.parquet",
        ],
        "computed_at": computed_at,
        "caveats": [
            "Honest-null clause is BINDING: if the gate REJECTs, the naive composite "
            "(0.55*TS%+0.30*eFG%+0.15*FT%) stays canonical. REJECT is a recorded SUCCESS, not a failure.",
            "DIFFICULTY/GRAVITY pillars at each pre-T cutoff use same-season atlas style-share "
            "fields (playtype mix, gravity_score) as stable style descriptors, not efficiency; "
            "EFFICIENCY/VOLUME pillars are recomputed exactly from pre-T boxscore rows only.",
            "PROVENANCE: this claim is intentionally UNVERIFIABLE by neither sibling validator's "
            "contract (see build_gate_claim docstring) -- a walk-forward paired-bootstrap CI has "
            "no criteria.formula, and this gate has no planted-null step to report. The numbers "
            f"above are persisted verbatim to {VERDICT_FILE} (verdict_file above) for a citable, "
            "independently-diffable on-disk source; this is a structural non-fit, not a bug.",
        ],
    }


def build_ranking_claim(claim_id: str, question: str, weights: dict, ranking_df: pd.DataFrame,
                         score_col: str, ellis_rank: int, curry_rank: int, n_qualifying: int,
                         source_files: list[str], extra_caveat: str, computed_at: str,
                         index_name: str, season: str) -> dict:
    snapshot_path = write_pillar_snapshot(ranking_df, weights, index_name)
    n_full_coverage = int((ranking_df["coverage"] >= 1.0).sum())
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": score_col,
            "formula": build_pillar_formula(weights),
            "weights": weights,
            "floors": {"min_games": QUALIFY_MIN_GAMES, "min_fga": QUALIFY_MIN_FGA},
            "min_sample": {"coverage": 1.0},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
            # window: real single-season vintage (idx.shooter/idx.scorer are
            # scored over quality_indices_score.run(season=...), same season
            # this claim was computed from) -- resolves via
            # intel_weighting.claim_features.window_to_season() so the
            # relevance gate can use this as a prior-season feature.
            "window": season,
        },
        "ranking": _ranking_rows(ranking_df, score_col),
        "face_validity_diagnostic": {
            "type": "reported_never_a_fitting_target",
            "stephen_curry_rank": curry_rank,
            "keon_ellis_rank": ellis_rank,
            "n_qualifying": n_qualifying,
            "top_decile_cutoff_rank": max(1, n_qualifying // 10),
        },
        "source_files": [snapshot_path],
        "computed_at": computed_at,
        "n_considered": n_qualifying,
        "n_excluded_below_floor": n_qualifying - n_full_coverage,
        "caveats": [
            "Weights DECLARED and FROZEN before scoring (basketball_truth_spec.json); "
            "never tuned to a named player's rank.",
            extra_caveat,
            "RECOMPUTABILITY: criteria.formula is the fixed-weight pillar sum, valid ONLY for "
            "coverage>=1.0 rows (min_sample floor) -- the ORIGINAL 329-player factor build "
            f"(source: {', '.join([BOXSCORE_PATH] + source_files)}) is still the one true "
            "computation; this claim's source_files points at a DERIVED per-player snapshot of "
            "quality_indices_score.score_index()'s own pillar_<PILLAR> output columns (not raw "
            "atlas data) so the independent validator can recompute the declared weighted sum "
            "without re-deriving the upstream percentile ranks/joins, which its whitelist "
            "formula grammar (row-wise/aggregate arithmetic only) cannot express.",
        ],
    }
