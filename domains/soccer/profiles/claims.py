"""domains.soccer.profiles.claims -- writes the profile snapshot parquets +
top-10 ranking claims (validator-recomputable via the same whitelist
sum/mean/count/count_distinct grammar as claims_validator_batch). Split out
of build_profiles.py for the <=300 LOC/file rail.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from domains.soccer.profiles.attribute_registry import REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[3]
_CLAIMS_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_PATH = _CLAIMS_DIR / "soccer_profile_claims.jsonl"

# criteria.aggregate.derived per attribute -- "n" is always the min_sample
# floor column (see attribute_registry floor_basis for what it counts).
_DERIVED: dict[str, dict[str, str]] = {
    "counter_threat": {"n": "count_distinct(match_id)", "counter_xg_sum": "sum(counter_xg)", "total_n": "count(xg)"},
    "buildup_quality": {"n": "count_distinct(match_id)", "regular_poss_n": "count(regular_xg)"},
    "set_piece_threat": {"n": "count_distinct(match_id)", "set_piece_xg_sum": "sum(set_piece_xg)", "total_xg_sum": "sum(xg)"},
    "defensive_solidity": {"n": "count_distinct(match_id)", "opponent_poss_n": "sum(poss)"},
    "formation_flexibility": {"n": "count_distinct(match_id)", "n_distinct_formations": "count_distinct(formation)",
                               "share_primary": "mean(is_primary)"},
    "finishing_overperformance": {"n": "count(diff)"},
    "home_strength": {"n": "count(pts)"},
}
# criteria.formula -- algebraically identical to what build_profiles.py computes
# directly in pandas for the presentation parquet (independent recompute paths).
_FORMULA: dict[str, str] = {
    "counter_threat": "sum(counter_xg) / count(xg)",
    "buildup_quality": "mean(regular_xg)",
    "set_piece_threat": "sum(set_piece_xg) / sum(xg)",
    "defensive_solidity": "sum(xg) / sum(poss)",
    "formation_flexibility": "1 - mean(is_primary)",
    "finishing_overperformance": "mean(diff)",
    "home_strength": "mean(pts) / 3",
}


def write_snapshots(snaps: dict[str, pd.DataFrame], out_dir: Path = _CLAIMS_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "counter_threat": ("soccer_possession_profile_source.parquet", snaps["counter_threat"]),
        "buildup_quality": ("soccer_possession_profile_source.parquet", snaps["counter_threat"]),
        "set_piece_threat": ("soccer_possession_profile_source.parquet", snaps["counter_threat"]),
        "defensive_solidity": ("soccer_defensive_profile_source.parquet", snaps["defensive_solidity"]),
        "formation_flexibility": ("soccer_formation_profile_source.parquet", snaps["formation_flexibility"]),
        "finishing_overperformance": ("soccer_finishing_profile_source.parquet", snaps["finishing_overperformance"]),
        "home_strength": ("soccer_homestrength_profile_source.parquet", snaps["home_strength"]),
    }
    written: dict[str, str] = {}
    seen: dict[str, Path] = {}
    for attr, (name, frame) in files.items():
        path = out_dir / name
        if name not in seen:
            frame.to_parquet(path, index=False)
            seen[name] = path
        written[attr] = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    return written


def _best_window(profile_df: pd.DataFrame, attr: str) -> Optional[str]:
    """Window with the most floor-qualifying entities (ties -> lexicographically
    latest, i.e. the most recent season for footballdata_<season> windows)."""
    sub = profile_df[profile_df["attribute"] == attr]
    if sub.empty:
        return None
    counts = sub.groupby("window").size().sort_values(ascending=False)
    top = counts.iloc[0]
    return max(counts[counts == top].index)


def build_claims(raw_df: pd.DataFrame, profile_df: pd.DataFrame, snapshot_paths: dict[str, str]) -> list[dict[str, Any]]:
    claims = []
    for attr, reg in REGISTRY.items():
        window = _best_window(profile_df, attr)
        if window is None:
            continue
        considered = raw_df[(raw_df["attribute"] == attr) & (raw_df["window"] == window)]
        qualifiers = profile_df[(profile_df["attribute"] == attr) & (profile_df["window"] == window)]
        ranked = qualifiers.sort_values("raw_value", ascending=not reg["higher_is_better"]).head(10)
        ranking = [
            {"rank": i, "entity_id": r.entity_id, "entity_name": r.entity_name,
             "value": round(float(r.raw_value), 4), "n": int(r.n)}
            for i, r in enumerate(ranked.itertuples(index=False), start=1)
        ]
        criteria: dict[str, Any] = {
            "metric": attr, "formula": _FORMULA[attr],
            "aggregate": {"group_by": "entity_id", "derived": _DERIVED[attr]},
            "window": window, "min_sample": {"n": reg["floor"]},
            "direction": "desc" if reg["higher_is_better"] else "asc",
            "value_precision": 4, "entity_key": "entity_id",
        }
        if reg["corpus"] == "footballdata_season":
            season = int(window.rsplit("_", 1)[-1])
            criteria["window_spec"] = {"kind": "season", "season_col": "season", "season": season}
        claims.append({
            "claim_id": f"soccer_profile_{attr}", "kind": "ranking",
            "question": f"Which teams rank highest on {attr} ({reg['description']}) -- window={window}?",
            "criteria": criteria, "ranking": ranking, "source_files": [snapshot_paths[attr]],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "n_considered": int(len(considered)), "n_excluded_below_floor": int(len(considered) - len(qualifiers)),
            "edge_claimed": False,
            "caveats": [f"status={reg['status']}; floor_basis={reg['floor_basis']}>={reg['floor']}; "
                        f"DESCRIPTIVE unless status says otherwise -- no market/$ edge claimed."],
        })
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for c in claims:
            f.write(json.dumps(c) + "\n")
    return out_path
